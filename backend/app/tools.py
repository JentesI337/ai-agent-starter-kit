from __future__ import annotations

import base64
import mimetypes
import fnmatch
from html import unescape
import ipaddress
import json
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
from app.services.code_sandbox import CodeSandbox
from app.services.vision_service import VisionService
from app.services.web_search import WebSearchService
from app.tool_catalog import TOOL_NAMES


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
    (r"\bcurl\b.*\|\s*(?:ba)?sh\b", "curl pipe-to-shell execution is blocked"),
    (r"\bwget\b.*\|\s*(?:ba)?sh\b", "wget pipe-to-shell execution is blocked"),
    (r"\bwget\b.*&&\s*(?:ba)?sh\b", "wget chained shell execution is blocked"),
    (r"python[23]?\s+-c\b", "python -c execution is blocked"),
    (r"\bpowershell(?:\.exe)?\b[^\n]*\s-(?:enc|encodedcommand)\b", "encoded PowerShell commands are blocked"),
    (r"\bnc\s+-[lp]\b", "netcat listen/connect flags are blocked"),
    (r"\b(?:curl|wget)\b[^\n]*\b(?:metadata\.google\.internal|169\.254\.169\.254)\b", "metadata endpoints are blocked"),
    (r"\bcmd(?:\.exe)?\b[^\n]*\s/c\s+del\b", "destructive cmd /c del is blocked"),
    (r"\bcmd(?:\.exe)?\b[^\n]*\s/(?:c|k)\b[^\n]*\b(?:rd|rmdir)\b", "destructive cmd rd/rmdir is blocked"),
    (r"\b(?:powershell|pwsh)(?:\.exe)?\b[^\n]*\b(?:iex|invoke-expression)\b", "PowerShell expression execution is blocked"),
    (r"\b(?:bash|sh|zsh)\b[^\n]*\s-c\b", "shell -c execution is blocked"),
    (r"\becho\b[^\n]*\|\s*(?:bash|sh|pwsh|powershell|cmd)\b", "pipe-to-shell execution is blocked"),
    (r"\|\|?|&&|;|`|\$\(", "shell chaining and command substitution are blocked"),
)


def find_command_safety_violation(command: str) -> str | None:
    lowered = (command or "").strip().lower()
    if not lowered:
        return "empty command is blocked"

    for pattern, reason in COMMAND_SAFETY_PATTERNS:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
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


class AgentTooling:
    def __init__(self, workspace_root: str, command_timeout_seconds: int = 60):
        self.workspace_root = Path(workspace_root).resolve()
        self.command_timeout_seconds = command_timeout_seconds
        self._command_allowlist_enabled = settings.command_allowlist_enabled
        self._command_allowlist = self._build_command_allowlist()
        self._command_allowlist_overrides: set[str] = set()
        self._background_jobs: dict[str, dict] = {}
        self._bg_lock = threading.Lock()
        self._web_fetch_max_redirects = 3
        self._web_fetch_max_download_bytes = max(1_000, int(settings.web_fetch_max_download_bytes))
        self._web_fetch_blocked_content_types = tuple(
            item.strip().lower() for item in settings.web_fetch_blocked_content_types if item.strip()
        )
        self._http_request_max_body_bytes = 1_000_000
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
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=run_cwd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )
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

    async def web_fetch(self, url: str, max_chars: int = 12000) -> str:
        requested_url = (url or "").strip()
        if not requested_url:
            raise ToolExecutionError("web_fetch requires non-empty URL.")

        limit = max(1000, min(int(max_chars), 100000))
        current_url = requested_url
        redirects = 0
        content_type = "unknown"
        text = ""

        try:
            async with httpx.AsyncClient(
                timeout=15.0,
                follow_redirects=False,
                headers={"User-Agent": "ai-agent-starter-kit/1.0"},
            ) as client:
                while True:
                    pinned_ip = self._enforce_safe_web_target(current_url)
                    connect_url, extra_headers = self._apply_dns_pin(current_url, pinned_ip)

                    async with client.stream("GET", connect_url, headers=extra_headers) as response:
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
                        lowered_content_type = content_type.lower()
                        if any(blocked in lowered_content_type for blocked in self._web_fetch_blocked_content_types):
                            raise ToolExecutionError(
                                f"web_fetch blocked content-type: {content_type}"
                            )

                        content_length_header = str(response.headers.get("Content-Length", "")).strip()
                        if content_length_header:
                            try:
                                content_length = int(content_length_header)
                            except ValueError:
                                content_length = 0
                            if content_length > self._web_fetch_max_download_bytes:
                                raise ToolExecutionError(
                                    "web_fetch response too large: "
                                    f"{content_length} bytes "
                                    f"(max {self._web_fetch_max_download_bytes})"
                                )

                        chunks: list[bytes] = []
                        total = 0
                        async for chunk in response.aiter_bytes():
                            if not chunk:
                                continue
                            if total + len(chunk) > self._web_fetch_max_download_bytes:
                                raise ToolExecutionError(
                                    "web_fetch response exceeded max download size "
                                    f"({self._web_fetch_max_download_bytes} bytes)"
                                )
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

    async def web_search(self, query: str, max_results: int = 5) -> str:
        normalized_query = (query or "").strip()
        if not normalized_query:
            raise ToolExecutionError("web_search requires non-empty query.")

        requested_max_results = max_results if isinstance(max_results, int) else settings.web_search_max_results
        bounded_max_results = max(1, min(int(requested_max_results), 10))

        service = WebSearchService(
            provider=settings.web_search_provider,
            api_key=settings.web_search_api_key,
            base_url=settings.web_search_base_url,
        )
        try:
            response = await service.search(normalized_query, max_results=bounded_max_results)
        except ValueError as exc:
            raise ToolExecutionError(f"web_search configuration error: {exc}") from exc
        except Exception as exc:
            raise ToolExecutionError(f"web_search failed for query='{normalized_query}': {exc}") from exc

        lines = [
            f"query: {response.query}",
            f"provider: {response.provider}",
            f"total_results: {response.total_results}",
            f"search_time_ms: {response.search_time_ms}",
        ]
        if not response.results:
            lines.append("results: (none)")
            return "\n".join(lines)

        lines.append("results:")
        for index, result in enumerate(response.results, start=1):
            lines.append(f"{index}. title: {result.title}")
            lines.append(f"   source_url: {result.url}")
            lines.append(f"   snippet: {result.snippet}")
            lines.append(f"   source: {result.source}")
            lines.append(f"   relevance_score: {result.relevance_score}")
        return "\n".join(lines)

    async def analyze_image(
        self,
        image_path: str,
        prompt: str = "Describe this image in detail.",
    ) -> str:
        if not bool(settings.vision_enabled):
            raise ToolExecutionError("analyze_image is disabled (VISION_ENABLED=false).")

        normalized_path = (image_path or "").strip()
        if not normalized_path:
            raise ToolExecutionError("analyze_image requires non-empty image_path.")

        target = self._resolve_workspace_path(normalized_path)
        if not target.exists() or not target.is_file():
            raise ToolExecutionError(f"Image file not found: {target}")

        data = target.read_bytes()
        if not data:
            raise ToolExecutionError("Image file is empty.")
        if len(data) > 8_000_000:
            raise ToolExecutionError("Image file too large for analyze_image (max 8MB).")

        image_base64 = base64.b64encode(data).decode("ascii")
        guessed_mime, _ = mimetypes.guess_type(target.name)
        image_mime_type = (guessed_mime or "application/octet-stream").strip().lower()
        if not image_mime_type.startswith("image/"):
            image_mime_type = "application/octet-stream"
        service = VisionService(
            base_url=settings.vision_base_url,
            model=settings.vision_model,
            api_key=settings.vision_api_key,
            provider=settings.vision_provider,
        )

        try:
            response_text = await service.analyze_image(
                image_base64=image_base64,
                image_mime_type=image_mime_type,
                prompt=prompt,
                max_tokens=int(settings.vision_max_tokens),
            )
        except ValueError as exc:
            raise ToolExecutionError(f"analyze_image configuration error: {exc}") from exc
        except Exception as exc:
            raise ToolExecutionError(f"analyze_image failed: {exc}") from exc

        normalized_response = (response_text or "").strip()
        if not normalized_response:
            raise ToolExecutionError("analyze_image returned empty response.")
        return normalized_response

    async def http_request(
        self,
        url: str,
        method: str = "GET",
        headers: str | None = None,
        body: str | None = None,
        content_type: str = "application/json",
        max_chars: int = 100000,
    ) -> str:
        requested_url = (url or "").strip()
        if not requested_url:
            raise ToolExecutionError("http_request requires non-empty URL.")

        normalized_method = (method or "GET").strip().upper()
        allowed_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        if normalized_method not in allowed_methods:
            raise ToolExecutionError(
                "http_request method must be one of: GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS"
            )

        pinned_ip = self._enforce_safe_web_target(requested_url)
        _, pin_headers = self._apply_dns_pin(requested_url, pinned_ip)

        limit = max(1, min(int(max_chars), 100000))
        request_headers: dict[str, str] = {"User-Agent": "ai-agent-starter-kit/1.0"}
        # Apply DNS-pin Host header before user headers so the user can override
        request_headers.update(pin_headers)
        if headers:
            try:
                parsed_headers = json.loads(headers)
            except Exception as exc:
                raise ToolExecutionError(f"http_request headers must be valid JSON object: {exc}") from exc
            if not isinstance(parsed_headers, dict):
                raise ToolExecutionError("http_request headers must be a JSON object.")
            for key, value in parsed_headers.items():
                if not isinstance(key, str) or not key.strip():
                    raise ToolExecutionError("http_request headers keys must be non-empty strings.")
                if not isinstance(value, str):
                    raise ToolExecutionError("http_request headers values must be strings.")
                request_headers[key.strip()] = value

        request_content: bytes | None = None
        request_json: object | None = None
        if body is not None:
            body_bytes = body.encode("utf-8")
            if len(body_bytes) > self._http_request_max_body_bytes:
                raise ToolExecutionError(
                    f"http_request body too large ({len(body_bytes)} bytes; max {self._http_request_max_body_bytes})"
                )
            try:
                parsed_body = json.loads(body)
            except Exception:
                parsed_body = None

            if isinstance(parsed_body, (dict, list)):
                request_json = parsed_body
            else:
                request_content = body_bytes

            has_content_type = any(key.lower() == "content-type" for key in request_headers)
            normalized_content_type = (content_type or "application/json").strip() or "application/json"
            if not has_content_type:
                request_headers["Content-Type"] = normalized_content_type

        content_type_value = "unknown"
        response_url = requested_url
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
                connect_url, _ = self._apply_dns_pin(requested_url, pinned_ip)
                async with client.stream(
                    normalized_method,
                    connect_url,
                    headers=request_headers,
                    content=request_content,
                    json=request_json,
                ) as response:
                    content_type_value = str(response.headers.get("Content-Type", "")).strip() or "unknown"
                    response_url = str(response.url)
                    chunks: list[bytes] = []
                    max_download_bytes = max(limit + 1, self._web_fetch_max_download_bytes)
                    total = 0
                    truncated = False
                    async for chunk in response.aiter_bytes():
                        if not chunk:
                            continue
                        remaining = max_download_bytes - total
                        if remaining <= 0:
                            truncated = True
                            break
                        if len(chunk) > remaining:
                            chunks.append(chunk[:remaining])
                            total += remaining
                            truncated = True
                            break
                        chunks.append(chunk)
                        total += len(chunk)
                    raw = b"".join(chunks)
                    encoding = response.encoding or "utf-8"
                    body_text = raw.decode(encoding, errors="replace")
                    normalized_body = self._normalize_web_text(text=body_text, max_chars=limit)
                    if truncated and len(normalized_body) < limit:
                        normalized_body = f"{normalized_body}\n...[truncated:response exceeded read limit]"

                    header_lines = [
                        f"{name}: {value}"
                        for name, value in sorted(response.headers.items(), key=lambda item: item[0].lower())[:50]
                    ]
                    rendered_headers = "\n".join(header_lines) if header_lines else "(none)"
                    return (
                        f"status: {int(response.status_code)}\n"
                        f"method: {normalized_method}\n"
                        f"source_url: {response_url}\n"
                        f"content_type: {content_type_value}\n"
                        f"headers:\n{rendered_headers}\n"
                        f"body:\n{normalized_body or '(empty response)'}"
                    )
        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError(
                f"http_request failed for method={normalized_method} url={requested_url}: {exc}"
            ) from exc

    def _enforce_safe_web_target(self, url: str) -> str | None:
        """Validate URL.  Returns a validated IP string for DNS-pinning (HTTP
        scheme only) or ``None`` when the URL already uses an IP literal or is
        HTTPS (where TLS certificate validation prevents DNS-rebinding
        exploitation).

        Callers should replace the hostname in the URL with the returned IP and
        set the ``Host`` header to the original hostname to close the TOCTOU
        gap between this validation and the actual TCP connect.
        """
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
            return None  # already an IP literal – no DNS rebinding risk

        resolved_ips = self._resolve_hostname_ips(host, parsed.port)
        if not resolved_ips:
            raise ToolExecutionError(f"web_fetch could not resolve hostname: {host}")
        for resolved in resolved_ips:
            if not resolved.is_global:
                raise ToolExecutionError(f"web_fetch blocked non-public resolved IP: {resolved}")

        if parsed.scheme == "http":
            return str(next(iter(resolved_ips)))
        # HTTPS: TLS certificate validation binds the connection to the
        # legitimate server; DNS rebinding to an internal host would cause a
        # certificate mismatch → connection refused.  No pinning needed.
        return None

    def _parse_ip_literal(self, host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
        try:
            return ipaddress.ip_address(host)
        except ValueError:
            return None

    @staticmethod
    def _apply_dns_pin(url: str, pinned_ip: str | None) -> tuple[str, dict[str, str]]:
        """Rewrite *url* to connect via *pinned_ip* (DNS-rebinding mitigation).

        Returns ``(connect_url, extra_headers)`` where *connect_url* has the
        hostname replaced with the validated IP (for HTTP) and *extra_headers*
        contains a ``Host`` header preserving the original hostname.

        When *pinned_ip* is ``None`` (IP literal or HTTPS), the URL is returned
        unchanged and extra_headers is empty.
        """
        if pinned_ip is None:
            return url, {}
        parsed = urlparse(url)
        original_host = parsed.hostname or ""
        ip_in_url = f"[{pinned_ip}]" if ":" in pinned_ip else pinned_ip
        if parsed.port:
            netloc = f"{ip_in_url}:{parsed.port}"
        else:
            netloc = ip_in_url
        pinned_url = parsed._replace(netloc=netloc).geturl()
        return pinned_url, {"Host": original_host}

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
        leader = self._enforce_command_allowlist(command)

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
        self._raise_if_env_missing(command=command, leader=leader, returncode=completed.returncode, output=output)
        return f"exit_code={completed.returncode}\n{output[:12000]}"

    async def code_execute(
        self,
        code: str,
        language: str = "python",
        timeout: int = 30,
        max_output_chars: int = 10000,
        strategy: str = "process",
    ) -> str:
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

    def _build_command_allowlist(self) -> set[str]:
        values: list[str] = []
        values.extend(settings.command_allowlist or [])
        values.extend(settings.command_allowlist_extra or [])
        return {item.strip().lower() for item in values if isinstance(item, str) and item.strip()}

    def allow_command_leader_temporarily(self, leader: str) -> str | None:
        normalized = (leader or "").strip().lower()
        if not normalized:
            return None
        self._command_allowlist_overrides.add(normalized)
        return normalized

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
        normalized = (output or "").strip().lower()
        env_missing_signals = (
            "is not recognized as an internal or external command",
            "command not found",
            "not found",
            "no such file or directory",
        )
        if any(signal in normalized for signal in env_missing_signals):
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
        if self.workspace_root not in candidate.parents and candidate != self.workspace_root:
            raise ToolExecutionError("Command cwd escapes workspace root.")
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
