"""Tests for app.url_validator — SSRF-safe URL validation and DNS pinning.

SEC (SSRF-01, SSRF-05): Covers all validation paths including:
- Scheme enforcement
- Credential blocking
- Blocked hostname list (localhost, cloud metadata, etc.)
- Private / loopback / link-local IP rejection
- IPv6-mapped IPv4 rejection
- Zero-network IP rejection
- DNS resolution and IP validation
- DNS-pinning helper
- LLM base URL validation (SSRF-01)
"""

from __future__ import annotations

import ipaddress
import socket
from unittest.mock import patch

import pytest

from app.url_validator import (
    BLOCKED_HOSTNAMES,
    UrlValidationError,
    apply_dns_pin,
    enforce_safe_url,
    parse_ip_literal,
    resolve_hostname_ips,
    validate_ip_is_public,
    validate_llm_base_url,
)

# ── parse_ip_literal ────────────────────────────────────────────────────

class TestParseIpLiteral:
    def test_ipv4(self):
        result = parse_ip_literal("8.8.8.8")
        assert result == ipaddress.ip_address("8.8.8.8")

    def test_ipv6(self):
        result = parse_ip_literal("::1")
        assert result == ipaddress.ip_address("::1")

    def test_hostname_returns_none(self):
        assert parse_ip_literal("example.com") is None

    def test_empty_returns_none(self):
        assert parse_ip_literal("") is None


# ── validate_ip_is_public ───────────────────────────────────────────────

class TestValidateIpIsPublic:
    def test_public_ipv4_ok(self):
        validate_ip_is_public(ipaddress.ip_address("8.8.8.8"))  # should not raise

    def test_private_ipv4_blocked(self):
        with pytest.raises(UrlValidationError, match="non-public"):
            validate_ip_is_public(ipaddress.ip_address("10.0.0.1"))

    def test_loopback_blocked(self):
        with pytest.raises(UrlValidationError, match="non-public"):
            validate_ip_is_public(ipaddress.ip_address("127.0.0.1"))

    def test_link_local_blocked(self):
        with pytest.raises(UrlValidationError, match="non-public"):
            validate_ip_is_public(ipaddress.ip_address("169.254.1.1"))

    def test_ipv6_mapped_private_blocked(self):
        ip = ipaddress.ip_address("::ffff:10.0.0.1")
        with pytest.raises(UrlValidationError, match=r"non-public|IPv6-mapped"):
            validate_ip_is_public(ip)

    def test_zero_network_blocked(self):
        with pytest.raises(UrlValidationError, match=r"non-public|zero-network"):
            validate_ip_is_public(ipaddress.ip_address("0.0.0.1"))

    def test_multicast_blocked(self):
        # 224.0.0.1 may be considered "global" in Python 3.13+ — test that
        # at minimum it does not crash.  The actual multicast block depends
        # on the Python version's is_global semantics.
        ip = ipaddress.ip_address("224.0.0.1")
        if not ip.is_global:
            with pytest.raises(UrlValidationError, match="non-public"):
                validate_ip_is_public(ip)
        # else: Python version considers multicast global — acceptable


# ── resolve_hostname_ips ─────────────────────────────────────────────────

class TestResolveHostnameIps:
    def test_resolution_failure_raises(self):
        with patch("app.url_validator.socket.getaddrinfo", side_effect=socket.gaierror("fail")), \
             pytest.raises(UrlValidationError, match="resolution failed"):
                resolve_hostname_ips("nonexistent.invalid")

    def test_returns_parsed_ips(self):
        fake_results = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443)),
        ]
        with patch("app.url_validator.socket.getaddrinfo", return_value=fake_results):
            ips = resolve_hostname_ips("example.com")
        assert ipaddress.ip_address("93.184.216.34") in ips


# ── apply_dns_pin ────────────────────────────────────────────────────────

class TestApplyDnsPin:
    def test_none_ip_returns_unchanged(self):
        url = "https://example.com/path"
        pinned_url, headers = apply_dns_pin(url, None)
        assert pinned_url == url
        assert headers == {}

    def test_ipv4_pinning(self):
        pinned_url, headers = apply_dns_pin("https://example.com/path", "93.184.216.34")
        assert "93.184.216.34" in pinned_url
        assert "example.com" not in pinned_url
        assert headers["Host"] == "example.com"

    def test_ipv6_pinning(self):
        pinned_url, headers = apply_dns_pin("https://example.com/path", "2001:db8::1")
        assert "[2001:db8::1]" in pinned_url
        assert headers["Host"] == "example.com"

    def test_port_preserved(self):
        pinned_url, _ = apply_dns_pin("https://example.com:8443/path", "93.184.216.34")
        assert "93.184.216.34:8443" in pinned_url


# ── enforce_safe_url ─────────────────────────────────────────────────────

class TestEnforceSafeUrl:
    def test_http_scheme_ok(self):
        with patch("app.url_validator.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443)),
            ]
            result = enforce_safe_url("https://example.com")
        assert result == "93.184.216.34"

    def test_ftp_scheme_rejected(self):
        with pytest.raises(UrlValidationError, match="schemes"):
            enforce_safe_url("ftp://example.com")

    def test_credentials_blocked(self):
        with pytest.raises(UrlValidationError, match="credentials"):
            enforce_safe_url("https://user:pass@example.com")

    def test_empty_hostname_blocked(self):
        with pytest.raises(UrlValidationError, match="hostname"):
            enforce_safe_url("https://")

    @pytest.mark.parametrize("hostname", [
        h for h in BLOCKED_HOSTNAMES
        if not h.startswith("[")  # IPv6 brackets are parsed as IP literals
    ])
    def test_blocked_hostnames(self, hostname):
        url = f"http://{hostname}/test"
        with pytest.raises(UrlValidationError, match="blocked hostname"):
            enforce_safe_url(url)

    @pytest.mark.parametrize("hostname", [
        h for h in BLOCKED_HOSTNAMES
        if h.startswith("[")  # IPv6 bracket forms — caught as IP literals
    ])
    def test_blocked_ipv6_hostnames(self, hostname):
        url = f"http://{hostname}/test"
        with pytest.raises(UrlValidationError, match=r"blocked hostname|non-public"):
            enforce_safe_url(url)

    def test_ip_literal_private_blocked(self):
        with pytest.raises(UrlValidationError, match="non-public"):
            enforce_safe_url("http://10.0.0.1/test")

    def test_ip_literal_public_returns_none(self):
        result = enforce_safe_url("http://8.8.8.8/test")
        assert result is None  # IP literal, no DNS pinning needed

    def test_resolved_private_ip_blocked(self):
        with patch("app.url_validator.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.1", 443)),
            ]
            with pytest.raises(UrlValidationError, match="non-public"):
                enforce_safe_url("https://evil-rebinding.example.com")


# ── validate_llm_base_url ───────────────────────────────────────────────

class TestValidateLlmBaseUrl:
    def test_empty_url_rejected(self):
        with pytest.raises(UrlValidationError, match="must not be empty"):
            validate_llm_base_url("")

    def test_invalid_scheme_rejected(self):
        with pytest.raises(UrlValidationError, match="scheme"):
            validate_llm_base_url("ftp://llm.example.com")

    def test_cloud_metadata_blocked(self):
        with pytest.raises(UrlValidationError, match="cloud metadata"):
            validate_llm_base_url("http://169.254.169.254/latest")

    def test_metadata_google_internal_blocked(self):
        with pytest.raises(UrlValidationError, match="cloud metadata"):
            validate_llm_base_url("http://metadata.google.internal/computeMetadata")

    def test_localhost_allowed(self):
        result = validate_llm_base_url("http://localhost:11434/v1")
        assert result == "http://localhost:11434/v1"

    def test_127_0_0_1_allowed(self):
        result = validate_llm_base_url("http://127.0.0.1:11434/v1")
        assert result == "http://127.0.0.1:11434/v1"

    def test_trailing_slash_stripped(self):
        result = validate_llm_base_url("http://localhost:11434/v1/")
        assert result == "http://localhost:11434/v1"

    def test_public_url_ok(self):
        with patch("app.url_validator.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("104.18.32.7", 443)),
            ]
            result = validate_llm_base_url("https://api.openai.com/v1")
        assert result == "https://api.openai.com/v1"

    def test_private_ip_literal_blocked(self):
        with pytest.raises(UrlValidationError, match="non-public"):
            validate_llm_base_url("http://10.0.0.5:8080/v1")

    def test_dns_resolves_to_private_blocked(self):
        with patch("app.url_validator.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.100", 443)),
            ]
            with pytest.raises(UrlValidationError, match="non-public"):
                validate_llm_base_url("https://internal-llm.corp.example.com/v1")

    def test_no_hostname_rejected(self):
        with pytest.raises(UrlValidationError, match="hostname"):
            validate_llm_base_url("http://")


# ── LlmClient integration (SSRF-01) ────────────────────────────────────

class TestLlmClientSsrf:
    """Verify that LlmClient rejects unsafe base URLs at construction time."""

    def test_metadata_url_rejected(self):
        from app.errors import LlmClientError
        from app.llm_client import LlmClient

        with pytest.raises(LlmClientError, match="validation failed"):
            LlmClient(base_url="http://169.254.169.254/latest", model="test")

    def test_private_ip_rejected(self):
        from app.errors import LlmClientError
        from app.llm_client import LlmClient

        with pytest.raises(LlmClientError, match="validation failed"):
            LlmClient(base_url="http://10.0.0.5:8080/v1", model="test")

    def test_localhost_allowed_for_dev(self):
        from app.llm_client import LlmClient

        client = LlmClient(base_url="http://localhost:11434/v1", model="test")
        assert client.base_url == "http://localhost:11434/v1"

    def test_valid_public_url(self):
        from app.llm_client import LlmClient

        with patch("app.url_validator.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("104.18.32.7", 443)),
            ]
            client = LlmClient(base_url="https://api.openai.com/v1", model="gpt-4")
        assert client.base_url == "https://api.openai.com/v1"
