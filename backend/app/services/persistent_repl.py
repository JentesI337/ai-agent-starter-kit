"""Persistent REPL — keeps a long-lived Python subprocess per session.

State (variables, imports, functions) survives across multiple ``execute()``
calls until ``reset()`` or ``shutdown()`` is called.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == "Windows"

# The driver script runs inside the subprocess.  It reads length-prefixed
# JSON commands from stdin and writes length-prefixed JSON results to stdout.
# This avoids all interactive-prompt noise from ``python -i``.
_DRIVER_SCRIPT = r'''
import sys, os, json, traceback, io, struct, subprocess

os.environ["MPLBACKEND"] = "Agg"
_IMG_DIR = os.environ.get("_REPL_IMG_DIR", "")
_INSTALL_DIR = os.environ.get("_REPL_INSTALL_DIR", "")
_GLOBALS = {"__builtins__": __builtins__, "__name__": "__main__"}

# --- Memory limit (Unix only) ---
import platform as _platform
_MAX_MEM = int(os.environ.get("_REPL_MAX_MEMORY_BYTES", "0"))
if _MAX_MEM > 0 and _platform.system() != "Windows":
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (_MAX_MEM, _MAX_MEM))
    except (ImportError, ValueError, OSError):
        pass

# --- Pandas display config ---
try:
    import pandas as _pd
    _pd.set_option("display.max_columns", 50)
    _pd.set_option("display.width", 120)
    _pd.set_option("display.max_rows", 60)
except ImportError:
    pass

# --- Package installation ---
def _install_package(*packages):
    if not _INSTALL_DIR:
        return "Install directory not configured"
    results = []
    for pkg in packages:
        if pkg.startswith("-"):
            results.append(f"Skipped flag: {pkg}")
            continue
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--target", _INSTALL_DIR,
                 "--no-input", "--disable-pip-version-check", pkg],
                capture_output=True, text=True, timeout=120,
            )
            if proc.returncode == 0:
                # Ensure install dir is on sys.path for immediate import
                if _INSTALL_DIR not in sys.path:
                    sys.path.insert(0, _INSTALL_DIR)
                results.append(f"Installed {pkg}")
            else:
                results.append(f"Failed to install {pkg}: {proc.stderr.strip()}")
        except subprocess.TimeoutExpired:
            results.append(f"Timeout installing {pkg}")
        except Exception as e:
            results.append(f"Error installing {pkg}: {e}")
    return "; ".join(results)

_GLOBALS["install"] = _install_package

def _read_msg():
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return None
    length = struct.unpack(">I", raw)[0]
    data = sys.stdin.buffer.read(length)
    return data.decode("utf-8")

def _write_msg(obj):
    payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(struct.pack(">I", len(payload)))
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()

while True:
    code = _read_msg()
    if code is None:
        break

    # --- Handle !pip install syntax ---
    _stripped = code.strip()
    if _stripped.startswith("!pip install ") or _stripped.startswith("!pip3 install "):
        _parts = _stripped.split()[2:]  # skip "!pip" "install"
        _pkgs = [p for p in _parts if not p.startswith("-")]
        _flags = [p for p in _parts if p.startswith("-")]
        _all = _flags + _pkgs
        _result = _install_package(*_all)
        _write_msg({"stdout": _result + "\n", "stderr": "", "images": []})
        continue

    cap_out = io.StringIO()
    cap_err = io.StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = cap_out, cap_err
    images = []
    try:
        # Try eval first (single expressions display their result)
        try:
            compiled = compile(code, "<repl>", "eval")
            result = eval(compiled, _GLOBALS)
            if result is not None:
                _GLOBALS["_"] = result
                try:
                    import pandas as _pd
                    if isinstance(result, _pd.DataFrame):
                        cap_out.write((result.to_markdown() if hasattr(result, "to_markdown") else result.to_string()) + "\n")
                    else:
                        cap_out.write(repr(result) + "\n")
                except ImportError:
                    cap_out.write(repr(result) + "\n")
        except SyntaxError:
            compiled = compile(code, "<repl>", "exec")
            exec(compiled, _GLOBALS)
    except SystemExit:
        pass
    except BaseException:
        traceback.print_exc(file=cap_err)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr

    if _IMG_DIR and os.path.isdir(_IMG_DIR):
        import glob, base64
        for img_path in sorted(glob.glob(os.path.join(_IMG_DIR, "*.png"))):
            try:
                with open(img_path, "rb") as f:
                    images.append(base64.b64encode(f.read()).decode())
                os.remove(img_path)
            except Exception:
                pass

    _write_msg({
        "stdout": cap_out.getvalue(),
        "stderr": cap_err.getvalue(),
        "images": images,
    })
'''


@dataclass(frozen=True)
class ReplResult:
    """Outcome of a single REPL execution."""
    stdout: str
    stderr: str
    exit_code: int
    images: list[str] = field(default_factory=list)  # Base64-encoded PNGs
    truncated: bool = False
    timed_out: bool = False
    duration_ms: int = 0


class PersistentRepl:
    """A persistent Python REPL backed by an ``asyncio`` subprocess.

    One instance per agent session.  The subprocess stays alive so that
    variables, imports and function definitions carry over between calls.
    """

    def __init__(
        self,
        session_id: str,
        *,
        timeout_seconds: int = 60,
        max_memory_mb: int = 512,
        max_output_chars: int = 10_000,
        sandbox_base: str | Path | None = None,
    ):
        self.session_id = session_id
        self.timeout_seconds = max(5, min(timeout_seconds, 300))
        self.max_memory_mb = max(64, min(max_memory_mb, 2048))
        self.max_output_chars = max(500, min(max_output_chars, 100_000))

        self._sandbox_base = Path(sandbox_base) if sandbox_base else Path(tempfile.gettempdir())
        self._sandbox_dir: Path | None = None
        self._img_dir: Path | None = None
        self._driver_path: Path | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._started = False
        self._last_activity: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Spawn the persistent Python subprocess."""
        if self._started and self._proc and self._proc.returncode is None:
            return  # already running

        # Create isolated sandbox directory
        self._sandbox_dir = Path(
            tempfile.mkdtemp(prefix=f"repl_{self.session_id[:8]}_", dir=str(self._sandbox_base))
        )
        self._img_dir = self._sandbox_dir / "images"
        self._img_dir.mkdir(exist_ok=True)

        # Write the driver script to disk
        self._driver_path = self._sandbox_dir / "_repl_driver.py"
        self._driver_path.write_text(_DRIVER_SCRIPT, encoding="utf-8")

        # Package install directory (isolated to sandbox)
        self._install_dir = self._sandbox_dir / "site-packages"
        self._install_dir.mkdir(exist_ok=True)

        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        env["MPLBACKEND"] = "Agg"
        env["_REPL_IMG_DIR"] = str(self._img_dir)
        env["_REPL_MAX_MEMORY_BYTES"] = str(self.max_memory_mb * 1024 * 1024)
        env["_REPL_INSTALL_DIR"] = str(self._install_dir)
        env["PYTHONPATH"] = str(self._install_dir) + os.pathsep + env.get("PYTHONPATH", "")

        if not _IS_WINDOWS:
            env["HOME"] = str(self._sandbox_dir)
            env["TMPDIR"] = str(self._sandbox_dir)

        self._proc = await asyncio.create_subprocess_exec(
            "python",
            "-u",
            str(self._driver_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._sandbox_dir),
            env=env,
        )
        self._started = True
        self._last_activity = time.monotonic()
        logger.info("persistent_repl_started session=%s pid=%s", self.session_id, self._proc.pid)

    async def reset(self) -> None:
        """Kill the subprocess and start a fresh one (clears all state)."""
        await self._kill_proc()
        if self._img_dir and self._img_dir.exists():
            for f in self._img_dir.iterdir():
                f.unlink(missing_ok=True)
        await self.start()

    async def shutdown(self) -> None:
        """Kill subprocess and remove sandbox directory."""
        await self._kill_proc()
        if self._sandbox_dir and self._sandbox_dir.exists():
            shutil.rmtree(self._sandbox_dir, ignore_errors=True)
            self._sandbox_dir = None
        self._started = False
        logger.info("persistent_repl_shutdown session=%s", self.session_id)

    @property
    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    @property
    def last_activity(self) -> float:
        return self._last_activity

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(self, code: str) -> ReplResult:
        """Execute *code* in the persistent subprocess and return the result.

        Automatically restarts the process if it has died.
        """
        async with self._lock:
            if not self.is_alive:
                await self.start()

            self._last_activity = time.monotonic()
            t0 = time.monotonic()

            try:
                raw = await asyncio.wait_for(
                    self._send_and_receive(code),
                    timeout=self.timeout_seconds,
                )
            except asyncio.TimeoutError:
                duration_ms = int((time.monotonic() - t0) * 1000)
                await self._kill_proc()
                return ReplResult(
                    stdout="",
                    stderr=f"Execution timed out after {self.timeout_seconds}s",
                    exit_code=1,
                    timed_out=True,
                    duration_ms=duration_ms,
                )

            duration_ms = int((time.monotonic() - t0) * 1000)

            stdout = raw.get("stdout", "")
            stderr = raw.get("stderr", "")
            images = raw.get("images", [])
            truncated = False

            if len(stdout) > self.max_output_chars:
                stdout = stdout[: self.max_output_chars] + "\n... [output truncated]"
                truncated = True
            if len(stderr) > self.max_output_chars:
                stderr = stderr[: self.max_output_chars] + "\n... [output truncated]"
                truncated = True

            return ReplResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=0,
                images=images,
                truncated=truncated,
                duration_ms=duration_ms,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send_and_receive(self, code: str) -> dict:
        """Send code via length-prefixed protocol and read the response."""
        import json as _json
        import struct

        assert self._proc is not None  # noqa: S101
        assert self._proc.stdin is not None  # noqa: S101
        assert self._proc.stdout is not None  # noqa: S101

        payload = code.encode("utf-8")
        header = struct.pack(">I", len(payload))
        self._proc.stdin.write(header + payload)
        await self._proc.stdin.drain()

        # Read 4-byte length header
        raw_header = await self._proc.stdout.readexactly(4)
        resp_len = struct.unpack(">I", raw_header)[0]

        # Read the JSON payload
        raw_body = await self._proc.stdout.readexactly(resp_len)
        return _json.loads(raw_body.decode("utf-8"))

    async def _kill_proc(self) -> None:
        """Terminate the subprocess tree."""
        if self._proc is None:
            return
        proc = self._proc
        self._proc = None
        if proc.returncode is not None:
            return
        try:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                proc.kill()
                await asyncio.wait_for(proc.wait(), timeout=2)
        except ProcessLookupError:
            pass
        except Exception:
            logger.debug("repl_kill_proc_error session=%s", self.session_id, exc_info=True)
