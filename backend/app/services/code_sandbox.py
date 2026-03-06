from __future__ import annotations

import asyncio
import os
import re
import signal
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodeExecutionResult:
    success: bool
    strategy: str
    language: str
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool
    duration_ms: int
    error_type: str | None = None
    error_message: str | None = None


class CodeSandbox:
    def __init__(
        self,
        *,
        strategy: str = "process",
        workspace_root: str | Path | None = None,
        default_timeout: int = 30,
        default_max_output_chars: int = 10_000,
        allow_network: bool = False,
    ):
        self.strategy = (strategy or "process").strip().lower()
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        self.default_timeout = max(1, int(default_timeout))
        self.default_max_output_chars = max(500, int(default_max_output_chars))
        self.allow_network = bool(allow_network)

    async def execute(
        self,
        *,
        code: str,
        language: str = "python",
        timeout: int | None = None,
        max_output_chars: int | None = None,
    ) -> CodeExecutionResult:
        normalized_language = (language or "python").strip().lower()
        if normalized_language not in {"python", "javascript", "js"}:
            return self._error_result(
                strategy=self.strategy,
                language=normalized_language,
                error_type="unsupported_language",
                error_message="language must be one of: python, javascript",
            )

        normalized_language = "javascript" if normalized_language == "js" else normalized_language
        effective_timeout = max(1, int(timeout or self.default_timeout))
        effective_limit = max(500, int(max_output_chars or self.default_max_output_chars))

        if not self.allow_network:
            violation = self._detect_network_violation(code=code, language=normalized_language)
            if violation:
                return self._error_result(
                    strategy=self.strategy,
                    language=normalized_language,
                    error_type="network_blocked",
                    error_message=violation,
                )

        fs_violation = self._detect_filesystem_escape_violation(code=code)
        if fs_violation:
            return self._error_result(
                strategy=self.strategy,
                language=normalized_language,
                error_type="filesystem_blocked",
                error_message=fs_violation,
            )

        # SEC: Block dynamic code execution constructs that can bypass
        # the static token/regex checks above (exec, eval, ctypes, etc.)
        dangerous = self._detect_dangerous_constructs(code=code, language=normalized_language)
        if dangerous:
            return self._error_result(
                strategy=self.strategy,
                language=normalized_language,
                error_type="dangerous_construct_blocked",
                error_message=dangerous,
            )

        if self.strategy == "docker":
            return await self._execute_docker(
                code=code,
                language=normalized_language,
                timeout=effective_timeout,
                max_output_chars=effective_limit,
            )
        if self.strategy == "direct":
            return await self._execute_direct(
                code=code,
                language=normalized_language,
                timeout=effective_timeout,
                max_output_chars=effective_limit,
            )
        return await self._execute_process(
            code=code,
            language=normalized_language,
            timeout=effective_timeout,
            max_output_chars=effective_limit,
        )

    async def _execute_process(
        self,
        *,
        code: str,
        language: str,
        timeout: int,
        max_output_chars: int,
    ) -> CodeExecutionResult:
        return await self._run_code_with_temp_jail(
            strategy="process",
            code=code,
            language=language,
            timeout=timeout,
            max_output_chars=max_output_chars,
        )

    async def _execute_direct(
        self,
        *,
        code: str,
        language: str,
        timeout: int,
        max_output_chars: int,
    ) -> CodeExecutionResult:
        return await self._run_code_with_temp_jail(
            strategy="direct",
            code=code,
            language=language,
            timeout=timeout,
            max_output_chars=max_output_chars,
        )

    async def _execute_docker(
        self,
        *,
        code: str,
        language: str,
        timeout: int,
        max_output_chars: int,
    ) -> CodeExecutionResult:
        """SEC (OE-04): Execute code inside a Docker container with isolation.

        Isolation features:
        - ``--network none``: No network access
        - ``--read-only``: Read-only root filesystem
        - ``--tmpfs /tmp``: Writable /tmp in memory (noexec)
        - ``--memory 128m``: Memory limit to prevent OOM
        - ``--cpus 0.5``: CPU limit
        - ``--pids-limit 64``: Fork-bomb protection
        - ``--no-new-privileges``: No privilege escalation
        - ``--security-opt no-new-privileges``: Double enforcement
        - Temporary workspace bind-mounted read-only
        """
        start = time.monotonic()

        # Verify Docker is available
        docker_path = shutil.which("docker")
        if not docker_path:
            return self._error_result(
                strategy="docker",
                language=language,
                error_type="docker_unavailable",
                error_message="docker executable not found in PATH",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        # Create temp dir with script
        temp_dir = Path(tempfile.mkdtemp(prefix="code-sandbox-docker-", dir=str(self.workspace_root)))
        script_name = "snippet.py" if language == "python" else "snippet.js"
        script_path = temp_dir / script_name
        script_path.write_text(code, encoding="utf-8")

        # Select Docker image
        if language == "python":
            image = os.getenv("CODE_SANDBOX_DOCKER_IMAGE_PYTHON", "python:3.12-slim")
            cmd_in_container = ["python", "-I", "-B", f"/sandbox/{script_name}"]
        elif language == "javascript":
            image = os.getenv("CODE_SANDBOX_DOCKER_IMAGE_JS", "node:20-slim")
            cmd_in_container = ["node", f"/sandbox/{script_name}"]
        else:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return self._error_result(
                strategy="docker",
                language=language,
                error_type="unsupported_language",
                error_message=f"Docker sandbox does not support language '{language}'",
            )

        docker_args = [
            docker_path, "run", "--rm",
            "--network", "none",
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--memory", "128m",
            "--cpus", "0.5",
            "--pids-limit", "64",
            "--no-new-privileges",
            "--security-opt", "no-new-privileges",
            "--user", "nobody",
            "-v", f"{str(temp_dir)}:/sandbox:ro",
            "-w", "/sandbox",
            image,
            *cmd_in_container,
        ]

        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *docker_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._build_sandbox_env(),
                creationflags=self._creationflags_for_platform(),
                start_new_session=(os.name != "nt"),
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=timeout + 10  # extra grace for Docker overhead
                )
                timed_out = False
            except asyncio.TimeoutError:
                timed_out = True
                await self._terminate_process_tree(process)
                stdout_bytes, stderr_bytes = await process.communicate()

            raw_stdout = stdout_bytes.decode("utf-8", errors="replace")
            raw_stderr = stderr_bytes.decode("utf-8", errors="replace")
            stdout, stderr, truncated = self._limit_output(raw_stdout, raw_stderr, max_output_chars)
            exit_code = process.returncode
            duration_ms = int((time.monotonic() - start) * 1000)

            return CodeExecutionResult(
                success=(not timed_out) and (exit_code == 0),
                strategy="docker",
                language=language,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
                truncated=truncated,
                duration_ms=duration_ms,
                error_type="timeout" if timed_out else None,
                error_message=(f"execution exceeded timeout of {timeout}s" if timed_out else None),
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            return self._error_result(
                strategy="docker",
                language=language,
                error_type="execution_error",
                error_message=str(exc),
                duration_ms=duration_ms,
            )
        finally:
            if process is not None and process.returncode is None:
                await self._terminate_process_tree(process)
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def _run_code_with_temp_jail(
        self,
        *,
        strategy: str,
        code: str,
        language: str,
        timeout: int,
        max_output_chars: int,
    ) -> CodeExecutionResult:
        start = time.monotonic()
        temp_dir = Path(tempfile.mkdtemp(prefix="code-sandbox-", dir=str(self.workspace_root)))
        script_name = "snippet.py" if language == "python" else "snippet.js"
        script_path = temp_dir / script_name
        script_path.write_text(code, encoding="utf-8")

        command = self._build_execution_command(language=language, script_path=script_path)
        if command is None:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return self._error_result(
                strategy=strategy,
                language=language,
                error_type="runtime_unavailable",
                error_message=f"runtime for language '{language}' is not available",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(temp_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._build_sandbox_env(),
                creationflags=self._creationflags_for_platform(),
                start_new_session=(os.name != "nt"),
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout)
                timed_out = False
            except asyncio.TimeoutError:
                timed_out = True
                await self._terminate_process_tree(process)
                stdout_bytes, stderr_bytes = await process.communicate()

            raw_stdout = stdout_bytes.decode("utf-8", errors="replace")
            raw_stderr = stderr_bytes.decode("utf-8", errors="replace")
            stdout, stderr, truncated = self._limit_output(raw_stdout, raw_stderr, max_output_chars)
            exit_code = process.returncode
            duration_ms = int((time.monotonic() - start) * 1000)

            return CodeExecutionResult(
                success=(not timed_out) and (exit_code == 0),
                strategy=strategy,
                language=language,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
                truncated=truncated,
                duration_ms=duration_ms,
                error_type="timeout" if timed_out else None,
                error_message=(f"execution exceeded timeout of {timeout}s" if timed_out else None),
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            return self._error_result(
                strategy=strategy,
                language=language,
                error_type="execution_error",
                error_message=str(exc),
                duration_ms=duration_ms,
            )
        finally:
            if process is not None and process.returncode is None:
                await self._terminate_process_tree(process)
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _build_execution_command(self, *, language: str, script_path: Path) -> tuple[str, ...] | None:
        if language == "python":
            runtime = shutil.which("python")
            if not runtime:
                return None
            return (runtime, "-I", "-B", str(script_path))
        if language == "javascript":
            runtime = shutil.which("node")
            if not runtime:
                return None
            return (runtime, str(script_path))
        return None

    def _build_sandbox_env(self) -> dict[str, str]:
        safe_keys = {
            "PATH", "PATHEXT", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE",
            "HOMEDRIVE", "HOMEPATH", "COMSPEC", "SHELL", "LANG", "LC_ALL",
            "VIRTUAL_ENV", "CONDA_PREFIX", "PYTHONPATH", "PYTHONHOME",
            "NODE_PATH", "GOPATH", "GOROOT", "JAVA_HOME",
            "TERM", "COLORTERM", "PROGRAMFILES", "PROGRAMFILES(X86)",
            "COMMONPROGRAMFILES", "APPDATA", "LOCALAPPDATA",
            "WINDIR", "SYSTEMDRIVE", "USERNAME", "LOGNAME", "USER",
        }
        env: dict[str, str] = {}
        for key, value in os.environ.items():
            if key.upper() in {k.upper() for k in safe_keys}:
                env[key] = value
        env["NO_PROXY"] = "*"
        env["no_proxy"] = "*"
        env["HTTP_PROXY"] = ""
        env["HTTPS_PROXY"] = ""
        env["http_proxy"] = ""
        env["https_proxy"] = ""
        env["ALL_PROXY"] = ""
        env["all_proxy"] = ""
        env["CODE_SANDBOX_NETWORK"] = "disabled" if not self.allow_network else "enabled"
        return env

    @staticmethod
    def _limit_output(stdout: str, stderr: str, max_output_chars: int) -> tuple[str, str, bool]:
        total = len(stdout) + len(stderr)
        if total <= max_output_chars:
            return stdout, stderr, False

        budget_stderr = min(len(stderr), max_output_chars // 2)
        budget_stdout = max_output_chars - budget_stderr
        if budget_stdout < 0:
            budget_stdout = 0

        truncated_stdout = stdout[:budget_stdout]
        truncated_stderr = stderr[:budget_stderr]
        return truncated_stdout, truncated_stderr, True

    @staticmethod
    async def _terminate_process_tree(process: asyncio.subprocess.Process) -> None:
        pid = int(process.pid or 0)
        if pid <= 0:
            return

        if os.name == "nt":
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/F",
                "/T",
                "/PID",
                str(pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.communicate()
        else:
            try:
                os.killpg(pid, signal.SIGKILL)
            except Exception:
                process.kill()
            try:
                await process.wait()
            except Exception:
                pass

    @staticmethod
    def _creationflags_for_platform() -> int:
        if os.name != "nt":
            return 0
        return int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))

    @staticmethod
    def _detect_network_violation(*, code: str, language: str) -> str | None:
        lowered = (code or "").lower()
        if language == "python":
            blocked_tokens = (
                "import socket",
                "from socket",
                "urllib.request",
                "import requests",
                "from requests",
                "http.client",
                "__import__('socket",
                '__import__("socket',
                "__import__(\"socket",
                "importlib.import_module",
                "import aiohttp",
                "from aiohttp",
                "import httpx",
                "from httpx",
                "import urllib3",
                "from urllib3",
            )
        else:
            blocked_tokens = (
                "require('http'",
                'require("http"',
                "require('https'",
                'require("https"',
                "fetch(",
                "xmlhttprequest",
            )

        for token in blocked_tokens:
            if token in lowered:
                return "network access is disabled by sandbox policy"
        return None

    @staticmethod
    def _detect_filesystem_escape_violation(*, code: str) -> str | None:
        lowered = (code or "").lower()
        blocked_patterns = (
            r"\bopen\(\s*['\"](?:[a-z]:\\\\|/etc/|/proc/|/var/|/root/|/home/)",
            r"\bpath\(\s*['\"](?:[a-z]:\\\\|/etc/|/proc/|/var/|/root/|/home/)",
            r"\bos\.listdir\(\s*['\"](?:/|[a-z]:\\\\)",
            r"\bpathlib\.path\(\s*['\"](?:/|[a-z]:\\\\)",
            r"\.{2}[/\\\\]",
            r"\bchr\(\s*\d+\s*\)\s*\+\s*chr\(",
            r"\bbase64\.b64decode\b",
            r"\bbytes\(\s*\[",
            r"\bcodecs\.decode\b",
            r"\bbytearray\(\s*\[",
        )
        for pattern in blocked_patterns:
            if re.search(pattern, lowered, flags=re.IGNORECASE):
                return "filesystem access outside sandbox jail is blocked by policy"
        return None

    @staticmethod
    def _detect_dangerous_constructs(*, code: str, language: str) -> str | None:
        """Detect dynamic code execution patterns that can bypass static analysis.

        This is a defense-in-depth layer: ``exec()``, ``eval()``,
        ``compile()``, ``ctypes``, and ``importlib`` with dynamic strings
        can all be used to circumvent the token-based network/filesystem
        checks above.
        """
        lowered = (code or "").lower()
        if language == "python":
            dangerous_patterns = (
                (r"\bexec\s*\(", "exec() is blocked in sandbox"),
                (r"\beval\s*\(", "eval() is blocked in sandbox"),
                (r"\bcompile\s*\(", "compile() is blocked in sandbox"),
                (r"\b__import__\s*\(", "__import__() is blocked in sandbox"),
                (r"\bimportlib\b", "importlib is blocked in sandbox"),
                (r"\bctypes\b", "ctypes is blocked in sandbox"),
                (r"\bsubprocess\b", "subprocess is blocked in sandbox"),
                (r"\bglobals\s*\(\s*\)", "globals() is blocked in sandbox"),
                (r"\bgetattr\s*\(", "getattr() is blocked in sandbox"),
                (r"\b__builtins__\b", "__builtins__ access is blocked in sandbox"),
                (r"\b__subclasses__\b", "__subclasses__ access is blocked in sandbox"),
            )
        elif language == "javascript":
            dangerous_patterns = (
                (r"\beval\s*\(", "eval() is blocked in sandbox"),
                (r"\bFunction\s*\(", "Function() constructor is blocked in sandbox"),
                (r"child_process", "child_process is blocked in sandbox"),
                (r"\brequire\s*\(\s*['\"]fs", "fs module is blocked in sandbox"),
            )
        else:
            return None

        for pattern, reason in dangerous_patterns:
            if re.search(pattern, lowered, flags=re.IGNORECASE):
                return reason
        return None

    @staticmethod
    def _error_result(
        *,
        strategy: str,
        language: str,
        error_type: str,
        error_message: str,
        duration_ms: int = 0,
    ) -> CodeExecutionResult:
        return CodeExecutionResult(
            success=False,
            strategy=strategy,
            language=language,
            exit_code=None,
            stdout="",
            stderr="",
            timed_out=False,
            truncated=False,
            duration_ms=duration_ms,
            error_type=error_type,
            error_message=error_message,
        )