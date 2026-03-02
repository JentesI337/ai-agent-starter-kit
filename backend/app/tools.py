from __future__ import annotations

import fnmatch
from html import unescape
import ipaddress
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
from urllib.parse import urljoin, urlparse
import uuid

import httpx

from app.config import settings
from app.errors import ToolExecutionError
from app.tool_catalog import TOOL_NAMES


class AgentTooling:
    def __init__(self, workspace_root: str, command_timeout_seconds: int = 60):
        self.workspace_root = Path(workspace_root).resolve()
        self.command_timeout_seconds = command_timeout_seconds
        self._command_allowlist_enabled = settings.command_allowlist_enabled
        self._command_allowlist = self._build_command_allowlist()
        self._background_jobs: dict[str, dict] = {}
        self._bg_lock = threading.Lock()
        self._web_fetch_max_redirects = 3
        self._read_file_max_bytes = 1_000_000
        self._grep_max_file_bytes = 1_000_000
        self._grep_max_total_scan_bytes = 8_000_000

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
        if target.stat().st_size > self._read_file_max_bytes:
            raise ToolExecutionError(
                f"File too large for read_file tool (max {self._read_file_max_bytes} bytes): {target}"
            )
        return target.read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> str:
        if len(content) > 300_000:
            raise ToolExecutionError("Content too large for write_file tool.")
        target = self._resolve_workspace_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote file: {target}"

    def apply_patch(self, path: str, search: str, replace: str, replace_all: bool = False) -> str:
        if not search:
            raise ToolExecutionError("apply_patch requires non-empty 'search'.")
        target = self._resolve_workspace_path(path)
        if not target.exists() or not target.is_file():
            raise ToolExecutionError(f"File not found: {target}")
        original = target.read_text(encoding="utf-8")
        hits = original.count(search)
        if hits == 0:
            raise ToolExecutionError("apply_patch search text not found.")
        if hits > 1 and not replace_all:
            raise ToolExecutionError("apply_patch search text is ambiguous; set replace_all=true.")

        updated = original.replace(search, replace) if replace_all else original.replace(search, replace, 1)
        target.write_text(updated, encoding="utf-8")
        return f"Patched file: {target} (replacements={hits if replace_all else 1})"

    def file_search(self, pattern: str, max_results: int = 100) -> str:
        query = (pattern or "**/*").strip()
        cap = max(1, min(int(max_results), 500))
        matches: list[str] = []
        for candidate in self.workspace_root.rglob("*"):
            rel = candidate.relative_to(self.workspace_root).as_posix()
            if fnmatch.fnmatch(rel, query):
                matches.append(rel + ("/" if candidate.is_dir() else ""))
                if len(matches) >= cap:
                    break
        return "\n".join(matches) if matches else "(no matches)"

    def grep_search(
        self,
        query: str,
        include_pattern: str | None = None,
        is_regexp: bool = False,
        max_results: int = 100,
    ) -> str:
        pattern = (query or "").strip()
        if not pattern:
            raise ToolExecutionError("grep_search requires non-empty 'query'.")

        cap = max(1, min(int(max_results), 500))
        include = (include_pattern or "**/*").strip() or "**/*"
        matches: list[str] = []
        total_scanned_bytes = 0

        compiled = re.compile(pattern, re.IGNORECASE) if is_regexp else None
        for candidate in self.workspace_root.rglob("*"):
            if not candidate.is_file():
                continue
            rel = candidate.relative_to(self.workspace_root).as_posix()
            if not fnmatch.fnmatch(rel, include):
                continue
            try:
                file_size = candidate.stat().st_size
            except Exception:
                continue
            if file_size > self._grep_max_file_bytes:
                continue
            total_scanned_bytes += file_size
            if total_scanned_bytes > self._grep_max_total_scan_bytes:
                break
            try:
                text = candidate.read_text(encoding="utf-8")
            except Exception:
                continue
            for idx, line in enumerate(text.splitlines(), start=1):
                hit = bool(compiled.search(line)) if compiled else (pattern.lower() in line.lower())
                if hit:
                    matches.append(f"{rel}:{idx}: {line[:280]}")
                    if len(matches) >= cap:
                        return "\n".join(matches)
        return "\n".join(matches) if matches else "(no matches)"

    def list_code_usages(self, symbol: str, include_pattern: str | None = None, max_results: int = 100) -> str:
        name = (symbol or "").strip()
        if not name:
            raise ToolExecutionError("list_code_usages requires 'symbol'.")
        escaped = re.escape(name)
        regex = rf"\b{escaped}\b"
        return self.grep_search(
            query=regex,
            include_pattern=include_pattern or "**/*.py",
            is_regexp=True,
            max_results=max_results,
        )

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
        self._enforce_command_allowlist(command)
        run_cwd = self._resolve_command_cwd(cwd)
        job_id = str(uuid.uuid4())[:8]
        log_dir = self.workspace_root / ".agent_background"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{job_id}.log"
        log_file = log_path.open("w", encoding="utf-8")
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=run_cwd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        with self._bg_lock:
            self._background_jobs[job_id] = {
                "process": proc,
                "log_path": log_path,
                "log_file": log_file,
                "command": command,
                "cwd": str(run_cwd),
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
            try:
                maybe_job["log_file"].close()
            except Exception:
                pass
        return f"Killed background job: {job_id}"

    def web_fetch(self, url: str, max_chars: int = 12000) -> str:
        requested_url = (url or "").strip()
        if not requested_url:
            raise ToolExecutionError("web_fetch requires non-empty URL.")

        limit = max(1000, min(int(max_chars), 100000))
        current_url = requested_url
        redirects = 0
        content_type = "unknown"
        text = ""

        try:
            with httpx.Client(
                timeout=15.0,
                follow_redirects=False,
                headers={"User-Agent": "ai-agent-starter-kit/1.0"},
            ) as client:
                while True:
                    self._enforce_safe_web_target(current_url)

                    with client.stream("GET", current_url) as response:
                        status = int(response.status_code)

                        if 300 <= status < 400:
                            location = str(response.headers.get("location", "")).strip()
                            if not location:
                                raise ToolExecutionError(
                                    f"web_fetch redirect without location (status={status})"
                                )
                            redirects += 1
                            if redirects > self._web_fetch_max_redirects:
                                raise ToolExecutionError(
                                    f"web_fetch redirect limit exceeded ({self._web_fetch_max_redirects})"
                                )
                            current_url = urljoin(current_url, location)
                            continue

                        if status >= 400:
                            raise ToolExecutionError(f"web_fetch failed with HTTP {status} for url={current_url}")

                        content_type = str(response.headers.get("Content-Type", "")).strip() or "unknown"
                        chunks: list[bytes] = []
                        total = 0
                        for chunk in response.iter_bytes():
                            if not chunk:
                                continue
                            remaining = (limit + 1) - total
                            if remaining <= 0:
                                break
                            chunks.append(chunk[:remaining])
                            total += len(chunks[-1])
                            if total >= (limit + 1):
                                break
                        raw = b"".join(chunks)
                        encoding = response.encoding or "utf-8"
                        text = raw.decode(encoding, errors="replace")
                        break
        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError(f"web_fetch failed for url={requested_url}: {exc}") from exc

        normalized_text = self._normalize_web_text(text=text, max_chars=limit)
        if not normalized_text:
            normalized_text = "(empty response)"

        return (
            f"source_url: {current_url}\n"
            f"content_type: {content_type}\n"
            f"content:\n{normalized_text}"
        )

    def _enforce_safe_web_target(self, url: str) -> None:
        parsed = urlparse((url or "").strip())
        if parsed.scheme not in {"http", "https"}:
            raise ToolExecutionError("web_fetch only supports http/https URLs.")

        if parsed.username or parsed.password:
            raise ToolExecutionError("web_fetch blocks URLs containing credentials.")

        host = (parsed.hostname or "").strip()
        if not host:
            raise ToolExecutionError("web_fetch requires a valid hostname.")

        lowered_host = host.lower()
        blocked_hostnames = {
            "localhost",
            "metadata.google.internal",
            "169.254.169.254",
            "[::1]",
        }
        if lowered_host in blocked_hostnames:
            raise ToolExecutionError(f"web_fetch blocked hostname: {host}")

        literal_ip = self._parse_ip_literal(host)
        if literal_ip is not None:
            if not literal_ip.is_global:
                raise ToolExecutionError(f"web_fetch blocked non-public target IP: {literal_ip}")
            return

        resolved_ips = self._resolve_hostname_ips(host, parsed.port)
        if not resolved_ips:
            raise ToolExecutionError(f"web_fetch could not resolve hostname: {host}")
        for resolved in resolved_ips:
            if not resolved.is_global:
                raise ToolExecutionError(f"web_fetch blocked non-public resolved IP: {resolved}")

    def _parse_ip_literal(self, host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
        try:
            return ipaddress.ip_address(host)
        except ValueError:
            return None

    def _resolve_hostname_ips(
        self,
        host: str,
        port: int | None,
    ) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        target_port = int(port or 443)
        try:
            infos = socket.getaddrinfo(host, target_port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ToolExecutionError(f"web_fetch hostname resolution failed for {host}: {exc}") from exc

        addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
        for info in infos:
            sockaddr = info[4]
            if not sockaddr:
                continue
            ip_text = str(sockaddr[0]).strip()
            parsed = self._parse_ip_literal(ip_text)
            if parsed is not None:
                addresses.add(parsed)
        return addresses

    def _normalize_web_text(self, text: str, max_chars: int) -> str:
        if not text:
            return ""

        looks_html = "<html" in text.lower() or "<body" in text.lower() or "<head" in text.lower()
        cleaned = text
        if looks_html:
            title_match = re.search(r"<title[^>]*>(.*?)</title>", cleaned, flags=re.IGNORECASE | re.DOTALL)
            title = ""
            if title_match:
                title = unescape(re.sub(r"\s+", " ", title_match.group(1))).strip()

            cleaned = re.sub(r"(?is)<script.*?>.*?</script>", " ", cleaned)
            cleaned = re.sub(r"(?is)<style.*?>.*?</style>", " ", cleaned)
            cleaned = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", cleaned)
            cleaned = re.sub(r"(?is)<!--.*?-->", " ", cleaned)
            cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
            cleaned = unescape(cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()

            if title and title.lower() not in cleaned.lower():
                cleaned = f"title: {title}\n{cleaned}"

        if len(cleaned) > max_chars:
            omitted = len(cleaned) - max_chars
            cleaned = f"{cleaned[:max_chars]}...[truncated:{omitted}]"
        return cleaned

    def run_command(self, command: str, cwd: str | None = None) -> str:
        if not command.strip():
            raise ToolExecutionError("Command must not be empty.")
        if len(command) > 1000:
            raise ToolExecutionError("Command is too long.")
        self._enforce_command_allowlist(command)

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

    def _build_command_allowlist(self) -> set[str]:
        values: list[str] = []
        values.extend(settings.command_allowlist or [])
        values.extend(settings.command_allowlist_extra or [])
        return {item.strip().lower() for item in values if isinstance(item, str) and item.strip()}

    def _enforce_command_allowlist(self, command: str) -> None:
        if not self._command_allowlist_enabled:
            return

        leader = self._extract_command_leader(command)
        if not leader:
            raise ToolExecutionError("Command must begin with an executable name.")

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
            raise ToolExecutionError(f"Command '{leader}' is blocked by safety policy.")

        self._enforce_command_safety(command=command, leader=leader)

        if leader not in self._command_allowlist:
            raise ToolExecutionError(
                f"Command '{leader}' is not allowed by command allowlist. "
                "Set COMMAND_ALLOWLIST_EXTRA to permit it in development."
            )

    def _enforce_command_safety(self, *, command: str, leader: str) -> None:
        lowered = (command or "").strip().lower()
        if not lowered:
            raise ToolExecutionError("Command must not be empty.")

        blocked_patterns: tuple[tuple[str, str], ...] = (
            (r"\b(?:curl|wget)\b[^\n]*\b(?:metadata\.google\.internal|169\.254\.169\.254)\b", "metadata endpoints are blocked"),
            (r"\bnc\b[^\n]*\s-l\b", "netcat listen mode is blocked"),
            (r"\bpowershell(?:\.exe)?\b[^\n]*\s-(?:enc|encodedcommand)\b", "encoded PowerShell commands are blocked"),
            (r"\bcmd(?:\.exe)?\b[^\n]*\s/c\s+del\b", "destructive cmd /c del is blocked"),
            (r"\bpython(?:3)?\b[^\n]*\s-c\b[^\n]*\b(?:eval|exec|os\.system|subprocess)\b", "dangerous python -c payload is blocked"),
            (r"\becho\b[^\n]*\|\s*(?:bash|sh|pwsh|powershell|cmd)\b", "pipe-to-shell execution is blocked"),
            (r"\|\|?|&&|;|`|\$\(", "shell chaining and command substitution are blocked"),
        )

        for pattern, reason in blocked_patterns:
            if re.search(pattern, lowered, flags=re.IGNORECASE):
                raise ToolExecutionError(f"Command blocked by safety policy: {reason}.")

    def _extract_command_leader(self, command: str) -> str:
        text = (command or "").strip()
        if not text:
            return ""

        if text[0] in {'"', "'"}:
            quote = text[0]
            closing_index = text.find(quote, 1)
            if closing_index > 1:
                token = text[1:closing_index]
            else:
                token = text[1:]
        else:
            token = re.split(r"\s|[|&;<>]", text, maxsplit=1)[0]

        token = token.strip()
        if not token:
            return ""

        name = Path(token).name.lower()
        if name.endswith(".exe"):
            name = name[:-4]
        if name.endswith(".cmd"):
            name = name[:-4]
        if name.endswith(".bat"):
            name = name[:-4]
        if name.endswith(".ps1"):
            name = name[:-4]
        return name

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
            "tools": list(TOOL_NAMES),
        }
        return ok, details
