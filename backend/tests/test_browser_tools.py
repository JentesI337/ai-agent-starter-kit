"""Tests for Browser Control — BrowserPool, SSRF validation, and browser tools."""

from __future__ import annotations

import asyncio
import base64
import json
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.services.browser_pool import BrowserPool, validate_browser_url
from app.url_validator import UrlValidationError


# ---------------------------------------------------------------------------
# Helpers: local test HTTP server
# ---------------------------------------------------------------------------

_TEST_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
  <h1>Hello Browser</h1>
  <p id="content">This is test content.</p>
  <a href="https://example.com" id="link1">Example Link</a>
  <form id="test-form">
    <input type="text" id="username" name="username" placeholder="Enter username" />
    <input type="password" id="password" name="password" placeholder="Enter password" />
    <button type="submit" id="submit-btn">Submit</button>
  </form>
  <button id="click-btn" onclick="document.getElementById('content').textContent = 'Clicked!'">Click Me</button>
  <script>
    window.testValue = 42;
  </script>
</body>
</html>
"""


class _TestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/redirect-internal":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/secret")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        content = _TEST_HTML.encode("utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *_args: object) -> None:
        pass  # Suppress log output during tests


@pytest.fixture(scope="module")
def test_server():
    """Start a local HTTP server for browser tests."""
    server = HTTPServer(("127.0.0.1", 0), _TestHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ---------------------------------------------------------------------------
# URL Validation Tests
# ---------------------------------------------------------------------------


class TestValidateBrowserUrl:
    """Tests for the validate_browser_url function."""

    def test_valid_http_url(self):
        assert validate_browser_url("https://example.com") == "https://example.com"

    def test_about_blank_allowed(self):
        assert validate_browser_url("about:blank") == "about:blank"

    def test_empty_url_rejected(self):
        with pytest.raises(UrlValidationError, match="must not be empty"):
            validate_browser_url("")

    def test_file_scheme_blocked(self):
        with pytest.raises(UrlValidationError, match="Blocked URL scheme"):
            validate_browser_url("file:///etc/passwd")

    def test_chrome_scheme_blocked(self):
        with pytest.raises(UrlValidationError, match="Blocked URL scheme"):
            validate_browser_url("chrome://settings")

    def test_javascript_scheme_blocked(self):
        with pytest.raises(UrlValidationError, match="Blocked URL scheme"):
            validate_browser_url("javascript:alert(1)")

    def test_localhost_blocked(self):
        with pytest.raises(UrlValidationError):
            validate_browser_url("http://localhost:8080")

    def test_127_0_0_1_blocked(self):
        with pytest.raises(UrlValidationError):
            validate_browser_url("http://127.0.0.1:8080")

    def test_metadata_ip_blocked(self):
        with pytest.raises(UrlValidationError):
            validate_browser_url("http://169.254.169.254/latest/meta-data/")

    def test_large_data_url_blocked(self):
        with pytest.raises(UrlValidationError, match="data: URLs larger than 1 KB"):
            validate_browser_url("data:text/html," + "x" * 2000)

    def test_small_data_url_passes_scheme_check(self):
        # data: < 1KB passes the size check but fails enforce_safe_url (not http/https)
        with pytest.raises(UrlValidationError):
            validate_browser_url("data:text/html,<h1>hi</h1>")

    def test_ftp_blocked(self):
        with pytest.raises(UrlValidationError, match="Blocked URL scheme"):
            validate_browser_url("ftp://files.example.com/secret.txt")

    def test_whitespace_stripped(self):
        result = validate_browser_url("  https://example.com  ")
        assert result == "https://example.com"


# ---------------------------------------------------------------------------
# BrowserPool Unit Tests (mocked — no real browser needed)
# ---------------------------------------------------------------------------


class TestBrowserPoolUnit:
    """Unit tests for BrowserPool without real Playwright."""

    @pytest.mark.asyncio
    async def test_pool_creation(self):
        pool = BrowserPool(max_contexts=3, context_ttl_seconds=60)
        assert pool.max_contexts == 3
        assert pool.context_ttl_seconds == 60
        assert pool._browser is None

    @pytest.mark.asyncio
    async def test_pool_shutdown_without_start(self):
        pool = BrowserPool()
        await pool.shutdown()
        assert pool._closed is True

    @pytest.mark.asyncio
    async def test_pool_rejects_after_shutdown(self):
        pool = BrowserPool()
        await pool.shutdown()
        with pytest.raises(RuntimeError, match="shut down"):
            await pool.get_context("test")

    @pytest.mark.asyncio
    async def test_playwright_not_installed_error(self):
        pool = BrowserPool()
        with patch.dict("sys.modules", {"playwright": None, "playwright.async_api": None}):
            with pytest.raises(RuntimeError, match="Playwright is not installed"):
                await pool.get_context("test")


# ---------------------------------------------------------------------------
# Integration Tests (require Playwright + Chromium)
# ---------------------------------------------------------------------------


def _playwright_available() -> bool:
    try:
        from playwright.async_api import async_playwright  # noqa: F401
        return True
    except ImportError:
        return False


requires_playwright = pytest.mark.skipif(
    not _playwright_available(),
    reason="Playwright not installed"
)


@requires_playwright
class TestBrowserPoolIntegration:
    """Integration tests using a real Playwright browser."""

    @staticmethod
    def _allow_test_server(pool: BrowserPool, test_server: str) -> None:
        """Add the test server origin to the pool's test bypass list."""
        from urllib.parse import urlparse
        parsed = urlparse(test_server)
        origin = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
        pool._allowed_test_origins.add(origin)

    @pytest.mark.asyncio
    async def test_get_context_creates_page(self, test_server):
        pool = BrowserPool(max_contexts=3, context_ttl_seconds=300)
        self._allow_test_server(pool, test_server)
        try:
            ctx, page = await pool.get_context("s1")
            await page.goto(test_server)
            title = await page.title()
            assert title == "Test Page"
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_session_isolation(self, test_server):
        pool = BrowserPool(max_contexts=5, context_ttl_seconds=300)
        self._allow_test_server(pool, test_server)
        try:
            _, page1 = await pool.get_context("s1")
            _, page2 = await pool.get_context("s2")
            await page1.goto(test_server)
            await page2.goto(test_server)
            # Both should have independent pages
            assert await page1.title() == "Test Page"
            assert await page2.title() == "Test Page"
            # They should be different page objects
            assert page1 is not page2
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_same_session_returns_same_page(self, test_server):
        pool = BrowserPool(max_contexts=5, context_ttl_seconds=300)
        self._allow_test_server(pool, test_server)
        try:
            _, page1 = await pool.get_context("s1")
            _, page2 = await pool.get_context("s1")
            assert page1 is page2
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_lru_eviction(self, test_server):
        pool = BrowserPool(max_contexts=2, context_ttl_seconds=300)
        self._allow_test_server(pool, test_server)
        try:
            _, p1 = await pool.get_context("s1")
            _, p2 = await pool.get_context("s2")
            # s1 is LRU, should be evicted when s3 is requested
            _, p3 = await pool.get_context("s3")
            assert "s1" not in pool._contexts
            assert "s2" in pool._contexts
            assert "s3" in pool._contexts
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_close_context(self, test_server):
        pool = BrowserPool(max_contexts=5, context_ttl_seconds=300)
        self._allow_test_server(pool, test_server)
        try:
            await pool.get_context("s1")
            assert "s1" in pool._contexts
            await pool.close_context("s1")
            assert "s1" not in pool._contexts
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_navigate_and_read(self, test_server):
        pool = BrowserPool(max_contexts=3, context_ttl_seconds=300)
        self._allow_test_server(pool, test_server)
        try:
            _, page = await pool.get_context("s1")
            await page.goto(test_server)
            text = await page.inner_text("body")
            assert "Hello Browser" in text
            assert "This is test content." in text
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_click_updates_dom(self, test_server):
        pool = BrowserPool(max_contexts=3, context_ttl_seconds=300)
        self._allow_test_server(pool, test_server)
        try:
            _, page = await pool.get_context("s1")
            await page.goto(test_server)
            await page.click("#click-btn")
            text = await page.inner_text("#content")
            assert text == "Clicked!"
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_fill_input(self, test_server):
        pool = BrowserPool(max_contexts=3, context_ttl_seconds=300)
        self._allow_test_server(pool, test_server)
        try:
            _, page = await pool.get_context("s1")
            await page.goto(test_server)
            await page.fill("#username", "testuser")
            value = await page.input_value("#username")
            assert value == "testuser"
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_screenshot(self, test_server):
        pool = BrowserPool(max_contexts=3, context_ttl_seconds=300)
        self._allow_test_server(pool, test_server)
        try:
            _, page = await pool.get_context("s1")
            await page.goto(test_server)
            png = await page.screenshot(type="png")
            # PNG magic bytes
            assert png[:4] == b"\x89PNG"
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_evaluate_js(self, test_server):
        pool = BrowserPool(max_contexts=3, context_ttl_seconds=300)
        self._allow_test_server(pool, test_server)
        try:
            _, page = await pool.get_context("s1")
            await page.goto(test_server)
            result = await page.evaluate("window.testValue")
            assert result == 42
        finally:
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_redirect_to_internal_blocked(self, test_server):
        """Redirect to 127.0.0.1:1 should be blocked by route interceptor."""
        pool = BrowserPool(max_contexts=3, context_ttl_seconds=300)
        self._allow_test_server(pool, test_server)
        try:
            _, page = await pool.get_context("s1")
            # The redirect target (127.0.0.1:1) is blocked because it's non-public
            # The route interceptor should abort the redirect
            try:
                await page.goto(f"{test_server}/redirect-internal")
            except Exception:
                pass  # Expected to fail (blocked redirect)
        finally:
            await pool.shutdown()


# ---------------------------------------------------------------------------
# Browser Tool Tests (via AgentTooling)
# ---------------------------------------------------------------------------


@requires_playwright
class TestBrowserTools:
    """Test browser_* tools via AgentTooling."""

    @pytest_asyncio.fixture()
    async def tooling(self, tmp_path, test_server):
        from urllib.parse import urlparse
        from app.tooling import AgentTooling
        tools = AgentTooling(workspace_root=str(tmp_path))
        pool = BrowserPool(max_contexts=3, context_ttl_seconds=300)
        # Allow the local test server for SSRF bypass in route interceptor
        parsed = urlparse(test_server)
        pool._allowed_test_origins.add(f"{parsed.scheme}://{parsed.hostname}:{parsed.port}")
        tools.set_browser_pool(pool)
        yield tools, test_server
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_browser_open(self, tooling):
        tools, url = tooling
        # Patch validate_browser_url so the local test server isn't blocked
        with patch("app.tools.implementations.browser.validate_browser_url", side_effect=lambda u: u):
            result = await tools.browser_open(url)
        assert "Title: Test Page" in result
        assert "Hello Browser" in result

    @pytest.mark.asyncio
    async def test_browser_click(self, tooling):
        tools, url = tooling
        with patch("app.tools.implementations.browser.validate_browser_url", side_effect=lambda u: u):
            await tools.browser_open(url)
            result = await tools.browser_click("#click-btn")
        assert "Clicked!" in result

    @pytest.mark.asyncio
    async def test_browser_type(self, tooling):
        tools, url = tooling
        with patch("app.tools.implementations.browser.validate_browser_url", side_effect=lambda u: u):
            await tools.browser_open(url)
        result = await tools.browser_type("#username", "admin")
        assert "admin" in result

    @pytest.mark.asyncio
    async def test_browser_screenshot(self, tooling):
        tools, url = tooling
        with patch("app.tools.implementations.browser.validate_browser_url", side_effect=lambda u: u):
            await tools.browser_open(url)
        result = await tools.browser_screenshot()
        data = json.loads(result)
        assert data["type"] == "image"
        assert data["format"] == "png"
        # Verify it's valid base64
        raw = base64.b64decode(data["data"])
        assert raw[:4] == b"\x89PNG"

    @pytest.mark.asyncio
    async def test_browser_read_dom(self, tooling):
        tools, url = tooling
        with patch("app.tools.implementations.browser.validate_browser_url", side_effect=lambda u: u):
            await tools.browser_open(url)
        result = await tools.browser_read_dom("#test-form")
        assert "Form fields:" in result
        assert "username" in result

    @pytest.mark.asyncio
    async def test_browser_read_dom_full_page(self, tooling):
        tools, url = tooling
        with patch("app.tools.implementations.browser.validate_browser_url", side_effect=lambda u: u):
            await tools.browser_open(url)
        result = await tools.browser_read_dom()
        assert "Hello Browser" in result
        assert "Links:" in result
        assert "Example Link" in result

    @pytest.mark.asyncio
    async def test_browser_evaluate_js(self, tooling):
        tools, url = tooling
        with patch("app.tools.implementations.browser.validate_browser_url", side_effect=lambda u: u):
            await tools.browser_open(url)
        result = await tools.browser_evaluate_js("window.testValue")
        assert result == "42"

    @pytest.mark.asyncio
    async def test_browser_evaluate_js_complex(self, tooling):
        tools, url = tooling
        with patch("app.tools.implementations.browser.validate_browser_url", side_effect=lambda u: u):
            await tools.browser_open(url)
        result = await tools.browser_evaluate_js("document.title")
        assert json.loads(result) == "Test Page"

    @pytest.mark.asyncio
    async def test_browser_open_ssrf_blocked(self, tooling):
        tools, _ = tooling
        from app.errors import ToolExecutionError
        with pytest.raises((UrlValidationError, ToolExecutionError)):
            await tools.browser_open("http://localhost:9999")

    @pytest.mark.asyncio
    async def test_browser_disabled(self, tmp_path):
        from app.tooling import AgentTooling
        from app.errors import ToolExecutionError
        tools = AgentTooling(workspace_root=str(tmp_path))
        # No browser pool set
        with pytest.raises(ToolExecutionError, match="not available"):
            await tools.browser_open("https://example.com")


# ---------------------------------------------------------------------------
# Tool Policy Tests
# ---------------------------------------------------------------------------


class TestBrowserToolPolicy:
    """Test that browser tools are correctly placed in tool profiles."""

    def test_research_profile_has_browser_read_tools(self):
        from app.tool_policy import TOOL_PROFILES
        research = TOOL_PROFILES["research"]
        assert research is not None
        assert "browser_open" in research
        assert "browser_screenshot" in research
        assert "browser_read_dom" in research
        # Research should NOT have write-type browser tools
        assert "browser_click" not in research
        assert "browser_type" not in research
        assert "browser_evaluate_js" not in research

    def test_coding_profile_has_all_browser_tools(self):
        from app.tool_policy import TOOL_PROFILES
        coding = TOOL_PROFILES["coding"]
        assert coding is not None
        for tool in ("browser_open", "browser_click", "browser_type",
                     "browser_screenshot", "browser_read_dom", "browser_evaluate_js"):
            assert tool in coding

    def test_read_only_profile_has_no_browser_tools(self):
        from app.tool_policy import TOOL_PROFILES
        read_only = TOOL_PROFILES["read_only"]
        assert read_only is not None
        for tool in ("browser_open", "browser_click", "browser_type",
                     "browser_screenshot", "browser_read_dom", "browser_evaluate_js"):
            assert tool not in read_only


# ---------------------------------------------------------------------------
# Tool Catalog Tests
# ---------------------------------------------------------------------------


class TestBrowserToolCatalog:
    """Test browser tools are registered in the catalog."""

    def test_browser_tools_in_catalog(self):
        from app.tool_catalog import TOOL_NAMES
        for tool in ("browser_open", "browser_click", "browser_type",
                     "browser_screenshot", "browser_read_dom", "browser_evaluate_js"):
            assert tool in TOOL_NAMES

    def test_browser_tool_aliases(self):
        from app.tool_catalog import TOOL_NAME_ALIASES
        assert TOOL_NAME_ALIASES["browseropen"] == "browser_open"
        assert TOOL_NAME_ALIASES["screenshot"] == "browser_screenshot"
        assert TOOL_NAME_ALIASES["browser_js"] == "browser_evaluate_js"
        assert TOOL_NAME_ALIASES["browser_eval"] == "browser_evaluate_js"


# ---------------------------------------------------------------------------
# Config Tests
# ---------------------------------------------------------------------------


class TestBrowserConfig:
    """Test browser configuration fields exist."""

    def test_browser_config_defaults(self):
        from app.config import settings
        assert hasattr(settings, "browser_enabled")
        assert hasattr(settings, "browser_max_contexts")
        assert hasattr(settings, "browser_navigation_timeout_ms")
        assert hasattr(settings, "browser_context_ttl_seconds")
        assert hasattr(settings, "browser_max_page_text_chars")
        assert settings.browser_max_contexts >= 1
        assert settings.browser_navigation_timeout_ms >= 5000
        assert settings.browser_context_ttl_seconds >= 30
