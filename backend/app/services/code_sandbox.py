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
        _ = (code, language, timeout, max_output_chars)
        return self._error_result(
            strategy="docker",
            language=language,
            error_type="docker_unavailable",
            error_message="docker strategy is not implemented yet in this phase",
        )

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
        env = dict(os.environ)
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
        )
        for pattern in blocked_patterns:
            if re.search(pattern, lowered, flags=re.IGNORECASE):
                return "filesystem access outside sandbox jail is blocked by policy"
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