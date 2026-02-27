from __future__ import annotations

import os
from pathlib import Path
import subprocess

from app.errors import ToolExecutionError


class AgentTooling:
    def __init__(self, workspace_root: str, command_timeout_seconds: int = 60):
        self.workspace_root = Path(workspace_root).resolve()
        self.command_timeout_seconds = command_timeout_seconds

    def list_dir(self, path: str | None = None) -> str:
        target = self._resolve_workspace_path(path or ".")
        if not target.exists() or not target.is_dir():
            raise ToolExecutionError(f"Directory not found: {target}")
        entries = sorted([item.name + ("/" if item.is_dir() else "") for item in target.iterdir()])
        return "\n".join(entries) or "(empty)"

    def read_file(self, path: str) -> str:
        target = self._resolve_workspace_path(path)
        if not target.exists() or not target.is_file():
            raise ToolExecutionError(f"File not found: {target}")
        return target.read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> str:
        if len(content) > 300_000:
            raise ToolExecutionError("Content too large for write_file tool.")
        target = self._resolve_workspace_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote file: {target}"

    def run_command(self, command: str, cwd: str | None = None) -> str:
        if not command.strip():
            raise ToolExecutionError("Command must not be empty.")
        if len(command) > 1000:
            raise ToolExecutionError("Command is too long.")

        run_cwd = self._resolve_command_cwd(cwd)
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=run_cwd,
                capture_output=True,
                text=True,
                timeout=self.command_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolExecutionError(
                f"Command timeout after {self.command_timeout_seconds}s: {exc.cmd}"
            ) from exc

        output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
        output = output.strip() or "(no output)"
        return f"exit_code={completed.returncode}\n{output[:12000]}"

    def _resolve_workspace_path(self, raw_path: str) -> Path:
        target = (self.workspace_root / raw_path).resolve()
        if self.workspace_root not in target.parents and target != self.workspace_root:
            raise ToolExecutionError("Path escapes workspace root.")
        return target

    def _resolve_command_cwd(self, cwd: str | None) -> Path:
        if not cwd:
            return self.workspace_root

        candidate = Path(cwd)
        if not candidate.is_absolute():
            candidate = (self.workspace_root / candidate).resolve()
        else:
            candidate = candidate.resolve()

        if not candidate.exists() or not candidate.is_dir():
            raise ToolExecutionError(f"Command cwd does not exist: {candidate}")
        return candidate

    def check_toolchain(self) -> tuple[bool, dict]:
        workspace_ok = self.workspace_root.exists() and self.workspace_root.is_dir()
        shell_ok = bool(os.environ.get("COMSPEC")) if os.name == "nt" else Path("/bin/sh").exists()
        ok = workspace_ok and shell_ok
        details = {
            "workspace_root": str(self.workspace_root),
            "workspace_ok": workspace_ok,
            "shell_ok": shell_ok,
            "tools": ["list_dir", "read_file", "write_file", "run_command"],
        }
        return ok, details
