"""Web fetch, HTTP, and web search tool operations."""
from __future__ import annotations

import ipaddress
import json
import re
from html import unescape
from urllib.parse import urljoin

import httpx

from app.config import settings
from app.tools.content_security import wrap_external_content
from app.errors import ToolExecutionError
from app.tools.implementations.web_search import WebSearchResponse, WebSearchResult, WebSearchService
from app.tools.url_validator import (
    UrlValidationError,
    apply_dns_pin as _shared_apply_dns_pin,
    enforce_safe_url as _shared_enforce_safe_url,
    parse_ip_literal as _shared_parse_ip_literal,
    resolve_hostname_ips as _shared_resolve_hostname_ips,
    validate_ip_is_public as _shared_validate_ip_is_public,
)

# Re-export for backward compat
__all__ = [
    "WebSearchResponse",
    "WebSearchResult",
    "WebSearchService",
    "WebToolMixin",
]


class WebToolMixin:
    """Mixin with web tool implementations."""

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
                                raise ToolExecutionError(f"web_fetch redirect without location (status={status})")
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
                            raise ToolExecutionError(f"web_fetch blocked content-type: {content_type}")

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

        return wrap_external_content(
            f"source_url: {current_url}\ncontent_type: {content_type}\ncontent:\n{normalized_text}",
            source="web_fetch",
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
        return wrap_external_content("\n".join(lines), source="web_search")

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
            raise ToolExecutionError("http_request method must be one of: GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS")

        pinned_ip = self._enforce_safe_web_target(requested_url)
        _, pin_headers = self._apply_dns_pin(requested_url, pinned_ip)

        limit = max(1, min(int(max_chars), 100000))
        request_headers: dict[str, str] = {"User-Agent": "ai-agent-starter-kit/1.0"}
        if headers:
            try:
                parsed_headers = json.loads(headers)
            except Exception as exc:
                raise ToolExecutionError(f"http_request headers must be valid JSON object: {exc}") from exc
            if not isinstance(parsed_headers, dict):
                raise ToolExecutionError("http_request headers must be a JSON object.")
            # Security-sensitive headers that user input must not override
            _FORBIDDEN_HEADER_KEYS = {"host", "transfer-encoding", "content-length"}
            for key, value in parsed_headers.items():
                if not isinstance(key, str) or not key.strip():
                    raise ToolExecutionError("http_request headers keys must be non-empty strings.")
                if not isinstance(value, str):
                    raise ToolExecutionError("http_request headers values must be strings.")
                if key.strip().lower() in _FORBIDDEN_HEADER_KEYS:
                    raise ToolExecutionError(f"http_request header '{key}' is forbidden for security reasons.")
                request_headers[key.strip()] = value
        # Apply DNS-pin Host header AFTER user headers to prevent SSRF bypass
        request_headers.update(pin_headers)

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
                    return wrap_external_content(
                        f"status: {int(response.status_code)}\n"
                        f"method: {normalized_method}\n"
                        f"source_url: {response_url}\n"
                        f"content_type: {content_type_value}\n"
                        f"headers:\n{rendered_headers}\n"
                        f"body:\n{normalized_body or '(empty response)'}",
                        source="http_request",
                    )
        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError(
                f"http_request failed for method={normalized_method} url={requested_url}: {exc}"
            ) from exc

    def _enforce_safe_web_target(self, url: str) -> str | None:
        try:
            return _shared_enforce_safe_url(url, label="web_fetch")
        except UrlValidationError as exc:
            raise ToolExecutionError(str(exc)) from exc

    def _parse_ip_literal(self, host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
        return _shared_parse_ip_literal(host)

    @staticmethod
    def _validate_ip_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        """Reject any IP that is not a globally routable public address.

        Delegates to the shared ``url_validator`` module.
        """
        try:
            _shared_validate_ip_is_public(ip)
        except UrlValidationError as exc:
            raise ToolExecutionError(str(exc)) from exc

    @staticmethod
    def _apply_dns_pin(url: str, pinned_ip: str | None) -> tuple[str, dict[str, str]]:
        """Rewrite *url* to connect via *pinned_ip* (DNS-rebinding mitigation).

        Delegates to the shared ``url_validator`` module.
        """
        return _shared_apply_dns_pin(url, pinned_ip)

    def _resolve_hostname_ips(
        self,
        host: str,
        port: int | None,
    ) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        try:
            return _shared_resolve_hostname_ips(host, port)
        except UrlValidationError as exc:
            raise ToolExecutionError(str(exc)) from exc

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
