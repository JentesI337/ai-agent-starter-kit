"""Browser context pool with session isolation, TTL eviction, and SSRF protection.

Provides a managed pool of Playwright browser contexts for agent browser tools.
Each session gets an isolated BrowserContext (separate cookies, storage, etc.).
Contexts are automatically evicted after a configurable inactivity timeout.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Any
from urllib.parse import urlparse

from app.tools.url_validator import UrlValidationError, enforce_safe_url

logger = logging.getLogger("app.browser.pool")

# Schemes that are never allowed for browser navigation.
_BLOCKED_SCHEMES: frozenset[str] = frozenset(
    {"file", "chrome", "chrome-extension", "javascript", "ftp", "gopher"}
)


def validate_browser_url(url: str) -> str:
    """Validate a URL for browser navigation (SSRF-safe).

    Allows ``http``, ``https``, and ``about:blank``.
    Blocks internal IPs, cloud metadata, file://, chrome://, javascript:, etc.

    Returns the validated URL (stripped).
    Raises :class:`UrlValidationError` on unsafe input.
    """
    stripped = (url or "").strip()
    if not stripped:
        raise UrlValidationError("URL must not be empty.")

    # Allow about:blank for initial state
    if stripped.lower() == "about:blank":
        return stripped

    parsed = urlparse(stripped)
    scheme = (parsed.scheme or "").lower()

    if scheme in _BLOCKED_SCHEMES:
        raise UrlValidationError(f"Blocked URL scheme for browser navigation: {scheme}://")

    if scheme == "data" and len(stripped) > 1024:
        raise UrlValidationError("data: URLs larger than 1 KB are blocked.")

    # Delegate to the shared SSRF validator for http/https
    enforce_safe_url(
        stripped,
        allowed_schemes=frozenset({"http", "https"}),
        label="browser_open",
    )
    return stripped


class _ContextEntry:
    """Internal wrapper holding a BrowserContext and its metadata."""

    __slots__ = ("context", "last_used", "page", "session_id")

    def __init__(self, context: Any, page: Any, session_id: str) -> None:
        self.context = context
        self.page = page
        self.session_id = session_id
        self.last_used = time.monotonic()

    def touch(self) -> None:
        self.last_used = time.monotonic()


class BrowserPool:
    """Manages a pool of isolated Playwright browser contexts.

    Parameters
    ----------
    max_contexts : int
        Maximum number of simultaneous browser contexts.
    navigation_timeout_ms : int
        Default timeout for page.goto() in milliseconds.
    context_ttl_seconds : int
        Inactivity timeout after which a context is auto-closed.
    """

    def __init__(
        self,
        *,
        max_contexts: int = 5,
        navigation_timeout_ms: int = 30_000,
        context_ttl_seconds: int = 300,
    ) -> None:
        self.max_contexts = max(1, max_contexts)
        self.navigation_timeout_ms = max(5_000, navigation_timeout_ms)
        self.context_ttl_seconds = max(30, context_ttl_seconds)

        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._contexts: OrderedDict[str, _ContextEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._ttl_task: asyncio.Task[None] | None = None
        self._closed = False
        # For testing only: origins that bypass SSRF checks (e.g. local test server)
        self._allowed_test_origins: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _ensure_browser(self) -> None:
        """Lazy-start Playwright and Chromium on first use."""
        if self._browser is not None:
            return
        try:
            from playwright.async_api import async_playwright  # type: ignore[import-untyped]
        except ImportError:
            raise RuntimeError(
                "Playwright is not installed. "
                "Run: pip install playwright && python -m playwright install chromium"
            ) from None

        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.launch(headless=True)
        except Exception as exc:
            error_msg = str(exc)
            if "Executable doesn't exist" in error_msg or "browserType.launch" in error_msg:
                logger.info("chromium_not_found — auto-installing via playwright install chromium")
                installed = await self._auto_install_chromium()
                if installed:
                    self._browser = await self._playwright.chromium.launch(headless=True)
                else:
                    raise RuntimeError(
                        "Chromium browser not found and auto-install failed. "
                        "Run manually: python -m playwright install chromium"
                    ) from exc
            else:
                raise
        logger.info("browser_pool_started browser=chromium headless=true")

        # Start background TTL eviction task
        if self._ttl_task is None:
            self._ttl_task = asyncio.create_task(self._eviction_loop())

    @staticmethod
    async def _auto_install_chromium() -> bool:
        """Attempt to install Chromium via ``playwright install chromium``."""
        import subprocess
        import sys

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                logger.info("chromium_auto_install_success")
                return True
            logger.warning(
                "chromium_auto_install_failed exit_code=%d stderr=%s",
                result.returncode,
                result.stderr[:500],
            )
            return False
        except Exception as e:
            logger.warning("chromium_auto_install_error: %s", e)
            return False

    async def _eviction_loop(self) -> None:
        """Periodically close contexts that have been idle too long."""
        while not self._closed:
            await asyncio.sleep(30)
            await self._evict_stale()

    async def _evict_stale(self) -> None:
        """Close contexts that exceeded their TTL."""
        now = time.monotonic()
        to_close: list[_ContextEntry] = []
        async with self._lock:
            stale_ids = [
                sid
                for sid, entry in self._contexts.items()
                if (now - entry.last_used) > self.context_ttl_seconds
            ]
            for sid in stale_ids:
                entry = self._contexts.pop(sid)
                to_close.append(entry)

        for entry in to_close:
            await self._close_entry(entry)
            logger.info("browser_context_evicted session_id=%s", entry.session_id)

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------

    async def get_context(self, session_id: str) -> tuple[Any, Any]:
        """Return ``(context, page)`` for *session_id*, creating if needed.

        If the pool is at capacity, the least-recently-used context is evicted.
        """
        async with self._lock:
            if self._closed:
                raise RuntimeError("BrowserPool is shut down.")

            await self._ensure_browser()

            if session_id in self._contexts:
                entry = self._contexts[session_id]
                entry.touch()
                self._contexts.move_to_end(session_id)
                return entry.context, entry.page

            # Evict LRU if at capacity
            while len(self._contexts) >= self.max_contexts:
                oldest_id, oldest_entry = self._contexts.popitem(last=False)
                await self._close_entry(oldest_entry)
                logger.info(
                    "browser_context_evicted_lru session_id=%s", oldest_id
                )

            # Create new context + page
            context = await self._browser.new_context(  # type: ignore[union-attr]
                viewport={"width": 1280, "height": 720},
                ignore_https_errors=False,
            )

            # Block file downloads
            context.on("page", self._block_downloads_on_page)

            page = await context.new_page()
            page.set_default_navigation_timeout(self.navigation_timeout_ms)
            page.set_default_timeout(10_000)

            # Intercept requests to validate redirect targets
            await page.route("**/*", self._intercept_request)

            entry = _ContextEntry(context, page, session_id)
            self._contexts[session_id] = entry
            logger.info("browser_context_created session_id=%s", session_id)
            return context, entry.page

    def _block_downloads_on_page(self, page: Any) -> None:
        """Attach download-blocking handler to a page."""
        page.on("download", lambda dl: dl.cancel())

    async def _intercept_request(self, route: Any) -> None:
        """Validate each navigation request URL against SSRF rules."""
        request = route.request
        url = request.url

        # Allow data: URIs up to 1KB (for inline SVG etc.)
        if url.startswith("data:"):
            if len(url) <= 1024:
                await route.continue_()
            else:
                await route.abort("blockedbyclient")
            return

        # Allow about:blank
        if url.lower().startswith("about:"):
            await route.continue_()
            return

        # Allow blob: URLs (generated by page JS)
        if url.lower().startswith("blob:"):
            await route.continue_()
            return

        parsed = urlparse(url)
        scheme = (parsed.scheme or "").lower()

        if scheme in _BLOCKED_SCHEMES:
            logger.warning("browser_request_blocked url=%s reason=blocked_scheme", url)
            await route.abort("blockedbyclient")
            return

        # For http/https, validate against SSRF
        if scheme in ("http", "https"):
            # Check test-only bypass list
            origin = f"{scheme}://{parsed.hostname}:{parsed.port}" if parsed.port else f"{scheme}://{parsed.hostname}"
            if origin in self._allowed_test_origins:
                await route.continue_()
                return
            try:
                enforce_safe_url(url, allowed_schemes=frozenset({"http", "https"}), label="browser_redirect")
            except UrlValidationError:
                logger.warning("browser_request_blocked url=%s reason=ssrf", url)
                await route.abort("blockedbyclient")
                return

        await route.continue_()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def close_context(self, session_id: str) -> None:
        """Close and remove the context for *session_id*."""
        async with self._lock:
            entry = self._contexts.pop(session_id, None)
        if entry is not None:
            await self._close_entry(entry)
            logger.info("browser_context_closed session_id=%s", session_id)

    async def shutdown(self) -> None:
        """Shut down all contexts and the browser."""
        self._closed = True
        if self._ttl_task is not None:
            self._ttl_task.cancel()
            self._ttl_task = None

        entries: list[_ContextEntry] = []
        async with self._lock:
            entries = list(self._contexts.values())
            self._contexts.clear()

        for entry in entries:
            await self._close_entry(entry)

        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

        logger.info("browser_pool_shutdown")

    @staticmethod
    async def _close_entry(entry: _ContextEntry) -> None:
        """Safely close a context entry."""
        try:
            await entry.context.close()
        except Exception:
            logger.debug("browser_context_close_error session_id=%s", entry.session_id, exc_info=True)
