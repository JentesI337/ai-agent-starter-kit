"""Browser automation tool operations."""
from __future__ import annotations

import base64
import json

from app.config import settings
from app.errors import ToolExecutionError
from app.browser.pool import BrowserPool, validate_browser_url


class BrowserToolMixin:
    """Mixin with browser automation tool implementations."""

    def _require_browser_pool(self) -> BrowserPool:
        if not settings.browser_enabled:
            raise ToolExecutionError("Browser tools are disabled (BROWSER_ENABLED=false).")
        if self._browser_pool is None:
            raise ToolExecutionError(
                "Browser pool not available. "
                "Ensure Playwright is installed: pip install playwright && python -m playwright install chromium"
            )
        return self._browser_pool

    async def browser_open(self, url: str, session_id: str | None = None) -> str:
        """Open a URL in the browser. Returns the page title and visible text."""
        pool = self._require_browser_pool()
        validated_url = validate_browser_url(url)
        sid = session_id or "default"
        _, page = await pool.get_context(sid)
        try:
            await page.goto(validated_url, wait_until="domcontentloaded")
        except Exception as exc:
            raise ToolExecutionError(f"Navigation failed: {exc}") from exc
        title = await page.title()
        max_chars = settings.browser_max_page_text_chars
        try:
            text = await page.inner_text("body")
        except Exception:
            text = ""
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... [text truncated]"
        return f"Title: {title}\n\nVisible text:\n{text}"

    async def browser_click(self, selector: str, session_id: str | None = None) -> str:
        """Click an element identified by CSS selector. Returns updated page text."""
        pool = self._require_browser_pool()
        sid = session_id or "default"
        _, page = await pool.get_context(sid)
        try:
            await page.click(selector, timeout=10_000)
        except Exception as exc:
            raise ToolExecutionError(f"Click failed for selector '{selector}': {exc}") from exc
        # Wait briefly for network activity to settle
        try:
            await page.wait_for_load_state("networkidle", timeout=5_000)
        except Exception:
            pass  # Best-effort wait
        max_chars = settings.browser_max_page_text_chars
        try:
            text = await page.inner_text("body")
        except Exception:
            text = ""
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... [text truncated]"
        title = await page.title()
        return f"Clicked '{selector}'.\n\nTitle: {title}\n\nVisible text:\n{text}"

    async def browser_type(self, selector: str, text: str, session_id: str | None = None) -> str:
        """Type text into an input element identified by CSS selector."""
        pool = self._require_browser_pool()
        sid = session_id or "default"
        _, page = await pool.get_context(sid)
        try:
            await page.fill(selector, text, timeout=10_000)
        except Exception:
            try:
                await page.type(selector, text, timeout=10_000)
            except Exception as exc:
                raise ToolExecutionError(f"Type failed for selector '{selector}': {exc}") from exc
        # Read back the value for confirmation
        try:
            value = await page.input_value(selector, timeout=3_000)
        except Exception:
            value = text
        return f"Typed into '{selector}'. Current value: '{value}'"

    def emit_visualization(self, viz_type: str, code: str, title: str | None = None) -> str:
        """Emit a visualization to the user's UI.

        Supported viz_type values: 'mermaid', 'svg'.
        For mermaid, provide valid Mermaid diagram syntax (flowchart, sequence, etc.).
        """
        viz_type = (viz_type or "").strip().lower()
        if viz_type not in ("mermaid", "svg"):
            raise ToolExecutionError(
                f"Unsupported viz_type '{viz_type}'. Use 'mermaid' or 'svg'."
            )
        code = (code or "").strip()
        if not code:
            raise ToolExecutionError("Visualization code must not be empty.")
        return json.dumps({
            "type": "visualization",
            "viz_type": viz_type,
            "code": code,
            "title": (title or "").strip() or None,
        })

    async def browser_screenshot(self, session_id: str | None = None) -> str:
        """Take a screenshot of the current page. Returns Base64-encoded PNG."""
        pool = self._require_browser_pool()
        sid = session_id or "default"
        _, page = await pool.get_context(sid)
        png_bytes = await page.screenshot(type="png", full_page=False)
        b64 = base64.b64encode(png_bytes).decode("ascii")
        return json.dumps({"type": "image", "format": "png", "data": b64})

    async def browser_read_dom(self, selector: str | None = None, session_id: str | None = None) -> str:
        """Read structured text from the DOM. Extracts text, links, and form fields."""
        pool = self._require_browser_pool()
        sid = session_id or "default"
        _, page = await pool.get_context(sid)
        target = selector or "body"
        max_chars = settings.browser_max_page_text_chars

        # Extract visible text
        try:
            text = await page.inner_text(target)
        except Exception as exc:
            raise ToolExecutionError(f"DOM read failed for selector '{target}': {exc}") from exc
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... [text truncated]"

        # Extract links
        links = await page.evaluate(
            """(sel) => {
                const root = sel === 'body' ? document.body : document.querySelector(sel);
                if (!root) return [];
                return Array.from(root.querySelectorAll('a[href]')).slice(0, 50).map(a => ({
                    text: (a.textContent || '').trim().substring(0, 100),
                    href: a.href
                }));
            }""",
            target,
        )

        # Extract form fields
        fields = await page.evaluate(
            """(sel) => {
                const root = sel === 'body' ? document.body : document.querySelector(sel);
                if (!root) return [];
                return Array.from(root.querySelectorAll('input, select, textarea')).slice(0, 30).map(el => ({
                    tag: el.tagName.toLowerCase(),
                    type: el.type || '',
                    name: el.name || '',
                    id: el.id || '',
                    value: (el.value || '').substring(0, 200),
                    placeholder: el.placeholder || '',
                    ariaLabel: el.getAttribute('aria-label') || ''
                }));
            }""",
            target,
        )

        parts = [f"Text content ({target}):", text]
        if links:
            parts.append("\nLinks:")
            for link in links:
                parts.append(f"  [{link['text']}]({link['href']})")
        if fields:
            parts.append("\nForm fields:")
            for f in fields:
                label = f.get("ariaLabel") or f.get("placeholder") or f.get("name") or f.get("id") or ""
                parts.append(f"  <{f['tag']} type='{f['type']}' name='{f['name']}' id='{f['id']}'> label='{label}' value='{f['value']}'")
        return "\n".join(parts)

    async def browser_evaluate_js(self, code: str, session_id: str | None = None) -> str:
        """Execute JavaScript in the page context and return the result as JSON."""
        pool = self._require_browser_pool()
        sid = session_id or "default"
        _, page = await pool.get_context(sid)
        try:
            result = await page.evaluate(code)
        except Exception as exc:
            raise ToolExecutionError(f"JS evaluation failed: {exc}") from exc
        output = json.dumps(result, ensure_ascii=False, default=str)
        if len(output) > 50_000:
            output = output[:50_000] + "\n... [output truncated]"
        return output
