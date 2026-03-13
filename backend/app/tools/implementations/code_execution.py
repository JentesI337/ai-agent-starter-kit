"""Code execution tool operations."""
from __future__ import annotations

import json

from app.config import settings
from app.errors import ToolExecutionError
from app.sandbox.code_sandbox import CodeSandbox


class CodeExecToolMixin:
    """Mixin with code execution tool implementations."""

    async def code_execute(
        self,
        code: str,
        language: str = "python",
        timeout: int = 30,
        max_output_chars: int = 10000,
        strategy: str = "process",
        persistent: bool = True,
        session_id: str | None = None,
    ) -> str:
        # Persistent REPL path for Python when enabled
        norm_lang = (language or "python").strip().lower()
        if (
            norm_lang == "python"
            and persistent
            and settings.repl_enabled
            and self._repl_manager is not None
        ):
            sid = session_id or "default"
            repl = await self._repl_manager.get_or_create(sid)
            result = await repl.execute(code)
            payload = {
                "success": result.exit_code == 0 and not result.timed_out,
                "strategy": "persistent_repl",
                "language": "python",
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "truncated": result.truncated,
                "duration_ms": result.duration_ms,
                "error_type": None,
                "error_message": None,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "images": result.images,
            }
            if result.timed_out:
                payload["error_type"] = "timeout"
                payload["error_message"] = f"Execution timed out after {repl.timeout_seconds}s"
            return json.dumps(payload, ensure_ascii=False)

        # Stateless sandbox path (non-Python or persistent=False)
        sandbox = CodeSandbox(
            strategy=strategy,
            workspace_root=self.workspace_root,
            default_timeout=max(1, min(int(timeout), 60)),
            default_max_output_chars=max(500, min(int(max_output_chars), 20000)),
            allow_network=False,
        )
        result = await sandbox.execute(
            code=code,
            language=language,
            timeout=timeout,
            max_output_chars=max_output_chars,
        )
        payload = {
            "success": result.success,
            "strategy": result.strategy,
            "language": result.language,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "truncated": result.truncated,
            "duration_ms": result.duration_ms,
            "error_type": result.error_type,
            "error_message": result.error_message,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        return json.dumps(payload, ensure_ascii=False)

    async def code_reset(self, session_id: str | None = None) -> str:
        """Reset the persistent Python REPL, clearing all state."""
        if not settings.repl_enabled or self._repl_manager is None:
            return "Persistent REPL is not enabled."
        sid = session_id or "default"
        was_reset = await self._repl_manager.reset(sid)
        if was_reset:
            return f"REPL session '{sid}' has been reset. All variables and state cleared."
        return f"No active REPL session found for '{sid}'."
