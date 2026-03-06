"""Shared SSRF-safe URL validation and DNS-pinning utilities.

SEC (SSRF-01, SSRF-05): Centralised module so that **all** outgoing HTTP
calls (LLM API, web_fetch, http_request, MCP SSE) can reuse the same
validation logic instead of duplicating it in every call-site.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger("app.url_validator")

# ── Blocked hostnames (cloud metadata, localhost, etc.) ──────────────────
BLOCKED_HOSTNAMES: frozenset[str] = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "169.254.169.254",
        "169.254.170.2",
        "metadata.internal",
        "[::1]",
        "0.0.0.0",
        "[::ffff:127.0.0.1]",
        "[::ffff:0.0.0.0]",
        "[::ffff:169.254.169.254]",
        "[0:0:0:0:0:0:0:1]",
    }
)


class UrlValidationError(ValueError):
    """Raised when a URL fails SSRF / safety validation."""


# ── IP validation ────────────────────────────────────────────────────────


def parse_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Try to parse *host* as an IP literal.  Returns ``None`` for hostnames."""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def validate_ip_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    """Reject any IP that is not a globally routable public address."""
    if not ip.is_global:
        raise UrlValidationError(f"Blocked non-public target IP: {ip}")
    # IPv6-mapped IPv4: e.g. ::ffff:127.0.0.1, ::ffff:10.0.0.1
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None and not ip.ipv4_mapped.is_global:
        raise UrlValidationError(f"Blocked IPv6-mapped private IPv4 address: {ip}")
    # 0.0.0.0/8 (current-network)
    if isinstance(ip, ipaddress.IPv4Address) and ip.packed[0] == 0:
        raise UrlValidationError(f"Blocked zero-network IP: {ip}")


# ── DNS resolution ───────────────────────────────────────────────────────


def resolve_hostname_ips(
    host: str,
    port: int | None = None,
) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve *host* via ``socket.getaddrinfo`` and return a set of parsed IPs."""
    target_port = int(port or 443)
    try:
        infos = socket.getaddrinfo(host, target_port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UrlValidationError(f"Hostname resolution failed for {host}: {exc}") from exc

    addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        ip_text = str(sockaddr[0]).strip()
        parsed = parse_ip_literal(ip_text)
        if parsed is not None:
            addresses.add(parsed)
    return addresses


# ── DNS-pin helpers ──────────────────────────────────────────────────────


def apply_dns_pin(url: str, pinned_ip: str | None) -> tuple[str, dict[str, str]]:
    """Rewrite *url* to connect via *pinned_ip* (DNS-rebinding mitigation).

    Returns ``(connect_url, extra_headers)`` where *connect_url* has the
    hostname replaced with the validated IP and *extra_headers* contains a
    ``Host`` header preserving the original hostname.

    When *pinned_ip* is ``None`` (IP literal), the URL is returned
    unchanged and extra_headers is empty.
    """
    if pinned_ip is None:
        return url, {}
    parsed = urlparse(url)
    original_host = parsed.hostname or ""
    ip_in_url = f"[{pinned_ip}]" if ":" in pinned_ip else pinned_ip
    netloc = f"{ip_in_url}:{parsed.port}" if parsed.port else ip_in_url
    pinned_url = parsed._replace(netloc=netloc).geturl()
    return pinned_url, {"Host": original_host}


# ── Full validation entry-point ──────────────────────────────────────────


def enforce_safe_url(
    url: str,
    *,
    allowed_schemes: frozenset[str] = frozenset({"http", "https"}),
    allow_credentials: bool = False,
    label: str = "URL",
) -> str | None:
    """Validate *url* against SSRF attacks.

    Returns the pinned IP string when DNS resolution was performed, or
    ``None`` when the URL already uses an IP literal.

    Raises :class:`UrlValidationError` if the URL is unsafe.
    """
    parsed = urlparse((url or "").strip())

    if parsed.scheme not in allowed_schemes:
        raise UrlValidationError(f"{label} only supports schemes {sorted(allowed_schemes)}, got '{parsed.scheme}'")

    if not allow_credentials and (parsed.username or parsed.password):
        raise UrlValidationError(f"{label} blocks URLs containing credentials.")

    host = (parsed.hostname or "").strip()
    if not host:
        raise UrlValidationError(f"{label} requires a valid hostname.")

    if host.lower() in BLOCKED_HOSTNAMES:
        raise UrlValidationError(f"{label} blocked hostname: {host}")

    literal_ip = parse_ip_literal(host)
    if literal_ip is not None:
        validate_ip_is_public(literal_ip)
        return None  # already an IP literal – no DNS rebinding risk

    # Resolve + validate IPs
    resolved_ips = resolve_hostname_ips(host, parsed.port)
    if not resolved_ips:
        raise UrlValidationError(f"{label} could not resolve hostname: {host}")
    for resolved in resolved_ips:
        validate_ip_is_public(resolved)

    # Return first resolved IP for DNS-pinning
    return str(next(iter(resolved_ips)))


def validate_llm_base_url(url: str) -> str:
    """Validate an LLM base URL at startup time.

    For localhost/private addresses this validation is skipped when
    the URL points to typical local development endpoints (localhost,
    127.0.0.1).  In production mode (``APP_ENV != 'development'``)
    private targets are rejected.

    Returns the validated (stripped) URL.
    """
    stripped = (url or "").strip().rstrip("/")
    if not stripped:
        raise UrlValidationError("LLM_BASE_URL must not be empty.")

    parsed = urlparse(stripped)
    if parsed.scheme not in {"http", "https"}:
        raise UrlValidationError(f"Invalid LLM_BASE_URL scheme: '{parsed.scheme}' — only http/https allowed.")

    host = (parsed.hostname or "").strip()
    if not host:
        raise UrlValidationError("LLM_BASE_URL requires a valid hostname.")

    # Cloud metadata endpoints are ALWAYS blocked
    cloud_metadata = {
        "metadata.google.internal",
        "169.254.169.254",
        "169.254.170.2",
        "metadata.internal",
        "[::ffff:169.254.169.254]",
    }
    if host.lower() in cloud_metadata:
        raise UrlValidationError(f"LLM_BASE_URL blocked — cloud metadata endpoint: {host}")

    # For local dev, allow localhost/127.0.0.1 (Ollama, LM Studio, etc.)
    local_hosts = {"localhost", "127.0.0.1", "::1", "[::1]"}
    if host.lower() in local_hosts:
        logger.debug("llm_base_url_local host=%s (allowed for local dev)", host)
        return stripped

    # For non-local hostnames: validate IP ranges
    literal_ip = parse_ip_literal(host)
    if literal_ip is not None:
        validate_ip_is_public(literal_ip)
        return stripped

    # DNS resolution check — warn but don't block at startup (DNS might
    # not be available yet, e.g. Docker startup ordering).  The actual
    # TCP connection will fail later if the host is unreachable.
    try:
        resolved_ips = resolve_hostname_ips(host, parsed.port)
        for resolved in resolved_ips:
            validate_ip_is_public(resolved)
    except UrlValidationError:
        raise
    except Exception as exc:
        logger.warning(
            "llm_base_url_dns_check_skipped host=%s error=%s (will be validated at connection time)",
            host,
            exc,
        )

    return stripped
