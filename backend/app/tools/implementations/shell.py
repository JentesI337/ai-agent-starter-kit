"""Shell command tool operations."""
from __future__ import annotations

import contextlib
import re
import shlex
import subprocess
import threading
import uuid
from pathlib import Path

from app.errors import ToolExecutionError

COMMAND_SAFETY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\brm\s+-r[f]?\s", "recursive rm is blocked"),
    (r"\bdel\s+/[a-z]*\s*[a-z]:\\", "destructive del against drive roots is blocked"),
    (r"\bformat\s+[a-z]:", "format command is blocked"),
    (r"\bshutdown\b", "shutdown command is blocked"),
    (r"\breboot\b", "reboot command is blocked"),
    (r"\bchmod\s+[0-7]{3,4}\b", "chmod with numeric permissions is blocked"),
    (r"\bchown\b", "chown command is blocked"),
    (r"\bmkfs\b", "filesystem formatting commands are blocked"),
    (r"\bdd\s+if=", "disk write command pattern is blocked"),
    # SEC (CMD-09): Additional destructive patterns
    (r"\bdd\s+.*of=/dev/", "dd writing to block device is blocked"),
    (r">\s*/dev/sd[a-z]", "redirect to block device is blocked"),
    (r"\bchmod\s+-[Rr]\s+777\s+/", "recursive chmod 777 on root is blocked"),
    (r"\bcurl\b.*\|\s*(?:ba)?sh\b", "curl pipe-to-shell execution is blocked"),
    (r"\bwget\b.*\|\s*(?:ba)?sh\b", "wget pipe-to-shell execution is blocked"),
    (r"\bwget\b.*&&\s*(?:ba)?sh\b", "wget chained shell execution is blocked"),
    (r"python[23]?\s+-c\b", "python -c execution is blocked"),
    (r"\bpowershell(?:\.exe)?\b[^\n]*\s-(?:enc|encodedcommand)\b", "encoded PowerShell commands are blocked"),
    (r"\bnc\s+-[lp]\b", "netcat listen/connect flags are blocked"),
    (r"\b(?:curl|wget)\b[^\n]*\b(?:metadata\.google\.internal|169\.254\.169\.254)\b", "metadata endpoints are blocked"),
    (r"\bcmd(?:\.exe)?\b[^\n]*\s/c\s+del\b", "destructive cmd /c del is blocked"),
    (r"\bcmd(?:\.exe)?\b[^\n]*\s/(?:c|k)\b[^\n]*\b(?:rd|rmdir)\b", "destructive cmd rd/rmdir is blocked"),
    (
        r"\b(?:powershell|pwsh)(?:\.exe)?\b[^\n]*\b(?:iex|invoke-expression)\b",
        "PowerShell expression execution is blocked",
    ),
    (r"\b(?:bash|sh|zsh)\b[^\n]*\s-c\b", "shell -c execution is blocked"),
    (r"\becho\b[^\n]*\|\s*(?:bash|sh|pwsh|powershell|cmd)\b", "pipe-to-shell execution is blocked"),
    (r"\|\|?|&&|;|`|\$\(", "shell chaining and command substitution are blocked"),
)


def find_command_safety_violation(command: str) -> str | None:
    lowered = (command or "").strip().lower()
    if not lowered:
        return "empty command is blocked"

    for pattern, reason in COMMAND_SAFETY_PATTERNS:
        if re.search(pattern, lowered):
            return reason

    semantic_reason = find_semantic_command_safety_violation(command)
    if semantic_reason:
        return semantic_reason
    return None


def find_semantic_command_safety_violation(command: str) -> str | None:
    lowered = (command or "").strip().lower()
    if not lowered:
        return None

    has_powershell_inline = bool(
        re.search(r"\b(?:powershell|pwsh)(?:\.exe)?\b[^\n]*\s-(?:c|command)\b", lowered, flags=re.IGNORECASE)
    )
    if not has_powershell_inline:
        return None

    has_remote_pull = any(token in lowered for token in ("downloadstring(", "invoke-webrequest", "irm ", "iwr "))
    has_dynamic_eval = any(
        token in lowered
        for token in (
            "scriptblock]::create",
            "frombase64string(",
            "invoke-expression",
            "iex",
        )
    )

    if has_remote_pull and has_dynamic_eval:
        return "PowerShell inline remote-code execution pattern is blocked"
    if "frombase64string(" in lowered and "scriptblock]::create" in lowered:
        return "PowerShell inline base64 script execution pattern is blocked"

    return None


class ShellToolMixin:
    """Mixin with shell command tool implementations."""

    def get_changed_files(self) -> str:
        status = subprocess.run(
            ["git", "-C", str(self.workspace_root), "status", "--short"],
            capture_output=True,
            text=True,
            timeout=self.command_timeout_seconds,
        )
        if status.returncode != 0:
            raise ToolExecutionError((status.stderr or status.stdout or "git status failed").strip())

        diff_names = subprocess.run(
            ["git", "-C", str(self.workspace_root), "diff", "--name-only"],
            capture_output=True,
            text=True,
            timeout=self.command_timeout_seconds,
        )
        if diff_names.returncode != 0:
            raise ToolExecutionError((diff_names.stderr or diff_names.stdout or "git diff failed").strip())

        status_text = (status.stdout or "").strip() or "(clean)"
        diff_text = (diff_names.stdout or "").strip() or "(no unstaged diff)"
        return f"status:\n{status_text}\n\nunstaged_files:\n{diff_text}"

    def start_background_command(self, command: str, cwd: str | None = None) -> str:
        if not command.strip():
            raise ToolExecutionError("start_background_command requires non-empty 'command'.")
        leader = self._enforce_command_allowlist(command)
        # SEC: Consume temporary override so allow-once can't be reused
        self._consume_temporary_override(leader)
        with self._bg_lock:
            active_count = sum(1 for job in self._background_jobs.values() if job["process"].poll() is None)
            if active_count >= self._bg_max_concurrent_jobs:
                raise ToolExecutionError(
                    f"Maximum concurrent background jobs ({self._bg_max_concurrent_jobs}) reached. "
                    "Kill an existing job before starting a new one."
                )
        run_cwd = self._resolve_command_cwd(cwd)
        job_id = str(uuid.uuid4())[:8]
        log_dir = self.workspace_root / ".agent_background"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{job_id}.log"
        log_file = log_path.open("w", encoding="utf-8")
        # SEC (OE-02): Use shell=False with tokenized args to prevent shell injection
        argv = self._tokenize_command(command)
        try:
            proc = subprocess.Popen(
                argv,
                shell=False,
                cwd=run_cwd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError as exc:
            log_file.close()
            raise ToolExecutionError(f"Command not found: {argv[0] if argv else command}") from exc
        except Exception:
            log_file.close()
            raise
        with self._bg_lock:
            self._background_jobs[job_id] = {
                "process": proc,
                "log_path": log_path,
                "log_file": log_file,
                "command": command,
                "cwd": str(run_cwd),
                # SEC (CMD-12): Track session ownership for kill authorization
                "session_id": getattr(self, "_current_session_id", None),
            }
        return f"job_id={job_id} pid={proc.pid} log={log_path}"

    def get_background_output(self, job_id: str, tail_lines: int = 200) -> str:
        with self._bg_lock:
            job = self._background_jobs.get(job_id)
        if not job:
            raise ToolExecutionError(f"Unknown background job: {job_id}")
        proc = job["process"]
        log_path = job["log_path"]
        try:
            lines = log_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            lines = []
        tail = max(1, min(int(tail_lines), 1000))
        output = "\n".join(lines[-tail:])
        status = "running" if proc.poll() is None else f"exited({proc.returncode})"
        return f"job_id={job_id} status={status}\n{output or '(no output)'}"

    def kill_background_process(self, job_id: str) -> str:
        with self._bg_lock:
            job = self._background_jobs.get(job_id)
        if not job:
            raise ToolExecutionError(f"Unknown background job: {job_id}")

        # SEC (CMD-12): Verify session ownership before killing
        current_session = getattr(self, "_current_session_id", None)
        job_session = job.get("session_id")
        if current_session and job_session and current_session != job_session:
            raise ToolExecutionError("Cannot kill background job from another session.")

        proc = job["process"]
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

        with self._bg_lock:
            maybe_job = self._background_jobs.pop(job_id, None)
        if maybe_job:
            with contextlib.suppress(Exception):
                maybe_job["log_file"].close()
        return f"Killed background job: {job_id}"

    def run_command(self, command: str, cwd: str | None = None) -> str:
        if not command.strip():
            raise ToolExecutionError("Command must not be empty.")
        if len(command) > 1000:
            raise ToolExecutionError("Command is too long.")
        leader = self._enforce_command_allowlist(command)
        # SEC: Consume temporary override after validation so it can't be reused
        self._consume_temporary_override(leader)

        run_cwd = self._resolve_command_cwd(cwd)
        # SEC (OE-02): Use shell=False with tokenized args to prevent shell injection
        argv = self._tokenize_command(command)
        try:
            completed = subprocess.run(
                argv,
                shell=False,
                cwd=run_cwd,
                capture_output=True,
                text=True,
                timeout=self.command_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolExecutionError(f"Command timeout after {self.command_timeout_seconds}s: {exc.cmd}") from exc
        except FileNotFoundError as exc:
            raise ToolExecutionError(f"Command not found: {argv[0] if argv else command}") from exc

        output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
        output = output.strip() or "(no output)"
        # SEC (CMD-11): Truncate command output to prevent memory exhaustion
        _MAX_CMD_OUTPUT = 100_000
        if len(output) > _MAX_CMD_OUTPUT:
            output = output[:_MAX_CMD_OUTPUT] + "\n... [output truncated]"
        self._raise_if_env_missing(command=command, leader=leader, returncode=completed.returncode, output=output)
        return f"exit_code={completed.returncode}\n{output[:12000]}"

    @staticmethod
    def probe_command(command_name: str) -> tuple[bool, str]:
        """Check whether *command_name* is available on the system.

        Returns ``(available, detail)`` where *detail* is the resolved
        path or an error message.  Uses ``shutil.which`` for portability.
        """
        import shutil

        clean = command_name.strip().split()[0] if command_name and command_name.strip() else ""
        if not clean:
            return False, "empty command name"
        path = shutil.which(clean)
        if path:
            return True, path
        return False, f"'{clean}' not found in PATH"

    def _tokenize_command(self, command: str) -> list[str]:
        """Tokenize a command string into a list of arguments.

        SEC (OE-02): Uses shlex.split() instead of shell=True to prevent
        shell-injection attacks via environment variable expansion,
        IFS manipulation, or Unicode homoglyph bypasses.
        On Windows, uses posix=True with manual quote-stripping to handle
        paths with backslashes correctly.
        """
        import sys

        try:
            # On Windows use posix=False to preserve backslashes in paths;
            # on POSIX use posix=True for correct quoting semantics.
            use_posix = sys.platform != "win32"
            tokens = shlex.split(command, posix=use_posix)
            if not use_posix:
                # posix=False preserves surrounding quotes; strip them
                stripped = []
                for t in tokens:
                    tok = t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in ('"', "'") else t
                    stripped.append(tok)
                tokens = stripped
        except ValueError as exc:
            raise ToolExecutionError(f"Cannot tokenize command: {exc}") from exc
        return tokens

    def _build_command_allowlist(self) -> set[str]:
        from app.config import settings
        values: list[str] = []
        values.extend(settings.command_allowlist or [])
        values.extend(settings.command_allowlist_extra or [])
        return {item.strip().lower() for item in values if isinstance(item, str) and item.strip()}

    def allow_command_leader_temporarily(self, leader: str) -> str | None:
        """Add a command leader to overrides for single use only.

        SEC: The override is consumed on first use to prevent permanent
        escalation via prompt-injection-triggered approval.
        """
        normalized = (leader or "").strip().lower()
        if not normalized:
            return None
        self._command_allowlist_overrides.add(normalized)
        return normalized

    def _consume_temporary_override(self, leader: str) -> None:
        """Remove a temporary override after it has been used once."""
        normalized = (leader or "").strip().lower()
        self._command_allowlist_overrides.discard(normalized)

    def extract_command_leader(self, command: str) -> str:
        return self._extract_command_leader(command)

    def _enforce_command_allowlist(self, command: str) -> str:
        leader = self._extract_command_leader(command)
        if not leader:
            self._raise_command_policy_error(
                category="unsupported",
                message="Command must begin with an executable name.",
                leader=leader,
            )

        blocked_leaders = {
            "rm",
            "del",
            "rmdir",
            "format",
            "shutdown",
            "reboot",
            "halt",
            "mkfs",
            "diskpart",
        }
        if leader in blocked_leaders:
            self._raise_command_policy_error(
                category="security",
                message=f"Command '{leader}' is blocked by safety policy.",
                leader=leader,
            )

        self._enforce_command_safety(command=command, leader=leader)

        if not self._command_allowlist_enabled:
            return leader

        if leader not in self._command_allowlist and leader not in self._command_allowlist_overrides:
            self._raise_command_policy_error(
                category="unsupported",
                message=(
                    f"Command '{leader}' is not allowed by command allowlist. "
                    "Set COMMAND_ALLOWLIST_EXTRA to permit it in development."
                ),
                leader=leader,
            )
        return leader

    def _enforce_command_safety(self, *, command: str, leader: str) -> None:
        if not (command or "").strip():
            raise ToolExecutionError("Command must not be empty.")
        reason = find_command_safety_violation(command)
        if reason:
            self._raise_command_policy_error(
                category="security",
                message=f"Command blocked by safety policy: {reason}.",
                leader=leader,
            )

    def _raise_if_env_missing(self, *, command: str, leader: str, returncode: int, output: str) -> None:
        if returncode == 0:
            return
        # Only check the first few lines — shell "command not found" messages
        # appear at the very start.  Checking the full output causes false
        # positives when the *program* itself reports "not found" for a file
        # (e.g. pytest reporting a missing test file).
        first_lines = "\n".join((output or "").strip().splitlines()[:3]).lower()
        env_missing_signals = (
            "is not recognized as an internal or external command",
            "command not found",
            "no such file or directory",
            "not recognized as",
        )
        if any(signal in first_lines for signal in env_missing_signals):
            self._raise_command_policy_error(
                category="env-missing",
                message=(
                    f"Command '{leader or command}' is allowlisted but unavailable in this environment. "
                    "Install/configure the tool in the runtime environment and retry."
                ),
                leader=leader,
            )

    def _raise_command_policy_error(self, *, category: str, message: str, leader: str) -> None:
        category_key = category.strip().lower().replace("_", "-") if category else "unsupported"
        if category_key not in {"security", "unsupported", "env-missing"}:
            category_key = "unsupported"
        code_key = category_key.replace("-", "_")
        raise ToolExecutionError(
            message,
            error_code=f"command_policy_{code_key}",
            details={"category": category_key, "leader": leader},
        )

    def _extract_command_leader(self, command: str) -> str:
        text = (command or "").strip()
        if not text:
            return ""

        if text[0] in {'"', "'"}:
            quote = text[0]
            closing_index = text.find(quote, 1)
            token = text[1:closing_index] if closing_index > 1 else text[1:]
        else:
            token = re.split(r"\s|[|&;<>]", text, maxsplit=1)[0]

        token = token.strip()
        if not token:
            return ""

        name = Path(token).name.lower()
        name = name.removesuffix(".exe")
        name = name.removesuffix(".cmd")
        name = name.removesuffix(".bat")
        return name.removesuffix(".ps1")
