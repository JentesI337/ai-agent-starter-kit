"""LLM-based conversation compaction service.

When the context window fills up, older messages are summarised by the LLM
so that critical context (task status, file paths, decisions) survives while
token usage stays within budget.

The service uses a progressive fallback chain:
1. LLM-based summarisation (best quality)
2. Text-based extraction (headings + identifiers)
3. Simple truncation (last resort — existing behaviour)
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.config import settings

logger = logging.getLogger("app.session.compaction")

# ── Constants ─────────────────────────────────────────────────────────

CHARS_PER_TOKEN = 4  # rough heuristic
COMPACTION_TRIGGER_RATIO = 0.85
COMPACTION_SAFETY_MARGIN = 1.2
IDENTIFIER_RE = re.compile(
    r"(?:"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"  # UUID
    r"|[0-9a-f]{32,64}"  # hex hash
    r"|/[^\s\"']{4,120}"  # file paths
    r"|[A-Za-z]:\\\\[^\s\"']{4,120}"  # Windows paths
    r"|https?://[^\s\"']{4,200}"  # URLs
    r")",
    re.IGNORECASE,
)

_SUMMARY_SYSTEM_PROMPT = (
    "You are a conversation summariser. Produce a concise summary of the "
    "conversation below.\n\n"
    "MUST PRESERVE:\n"
    "- Active tasks and their current status\n"
    "- The last thing the user requested\n"
    "- Decisions made and their rationale\n"
    "- All file paths, UUIDs, hashes, IDs, tokens, hostnames, IPs, ports, "
    "URLs, and file names EXACTLY as written — never shorten or reconstruct\n"
    "- TODOs, open questions, and constraints\n"
    "- Batch operation progress (e.g., '5/17 items completed')\n\n"
    "PRIORITIZE recent context over older history.\n"
    "Output ONLY the summary — no meta-commentary."
)


# ── Token estimation ──────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_messages_tokens(messages: list[dict]) -> int:
    """Estimate total tokens across all messages."""
    total = 0
    for msg in messages:
        content = msg.get("content") or ""
        total += estimate_tokens(str(content))
        # tool_calls in assistant messages add overhead
        if msg.get("tool_calls"):
            total += estimate_tokens(str(msg["tool_calls"]))
    return total


# ── Compaction service ────────────────────────────────────────────────

class CompactionService:
    """LLM-backed conversation compaction with progressive fallback."""

    def __init__(self, llm_client: Any):
        self._client = llm_client
        self._context_window = int(
            getattr(settings, "runner_compaction_context_window", 0)
        ) or 200_000
        self._tail_keep = int(getattr(settings, "runner_compaction_tail_keep", 4))

    # ── Public API ────────────────────────────────────────────────────

    def needs_compaction(self, messages: list[dict]) -> bool:
        """Return True when the conversation approaches the context limit."""
        used = estimate_messages_tokens(messages)
        limit = int(self._context_window / COMPACTION_SAFETY_MARGIN)
        return used >= int(limit * COMPACTION_TRIGGER_RATIO)

    async def compact(self, messages: list[dict]) -> list[dict]:
        """Compact *messages* using the best available strategy.

        Returns a new message list with older turns replaced by a summary.
        System message (index 0) and the last ``tail_keep`` messages are
        always preserved.
        """
        tail_keep = self._tail_keep
        if len(messages) <= tail_keep + 2:
            return messages  # nothing to compact

        system = messages[0]
        rest = messages[1:]
        keep_tail = rest[-tail_keep:]
        to_summarise = rest[:-tail_keep]

        if not to_summarise:
            return messages

        # Try LLM summary → text fallback → truncation fallback
        summary = await self._try_llm_summary(to_summarise)
        if not summary:
            summary = self._text_fallback_summary(to_summarise)

        summary_msg = {
            "role": "user",
            "content": (
                f"[CONTEXT SUMMARY — {len(to_summarise)} earlier messages compacted]\n\n"
                f"{summary}"
            ),
        }
        return [system, summary_msg, *keep_tail]

    # ── LLM-based summary ─────────────────────────────────────────────

    async def _try_llm_summary(self, messages: list[dict]) -> str | None:
        """Attempt to summarise *messages* via the LLM."""
        try:
            conversation_text = self._render_messages(messages)
            # Don't try to summarise if the conversation itself would overflow
            if estimate_tokens(conversation_text) > self._context_window * 0.6:
                return None

            result = await self._client.complete_chat(
                system_prompt=_SUMMARY_SYSTEM_PROMPT,
                user_prompt=conversation_text,
                temperature=0.2,
            )
            text = (result or "").strip()
            if len(text) < 20:
                return None
            # Verify identifiers survived
            self._verify_identifier_preservation(messages, text)
            return text
        except Exception:
            logger.debug("LLM compaction failed, falling back to text summary", exc_info=True)
            return None

    # ── Text-based fallback ───────────────────────────────────────────

    def _text_fallback_summary(self, messages: list[dict]) -> str:
        """Extract key information without LLM — simple but preserves identifiers."""
        fallback_chars = settings.runner_compaction_text_fallback_chars
        parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = str(msg.get("content") or "")
            if not content.strip():
                continue
            ids = set(IDENTIFIER_RE.findall(content))
            id_line = ""
            if ids:
                id_line = f"\n  [identifiers: {', '.join(sorted(ids)[:10])}]"
            # Tool messages: preserve tool metadata
            if role == "tool":
                tool_id = msg.get("tool_call_id", "?")
                is_error = "[ERROR]" in content or "error" in content[:200].lower()
                status = "ERR" if is_error else "OK"
                head = content[:fallback_chars].strip()
                parts.append(f"- tool[{tool_id}] [{status}]: {head}...{id_line}")
            else:
                head = content[:fallback_chars].strip()
                parts.append(f"- {role}: {head}...{id_line}")
        return "\n".join(parts) or "(No summarisable content)"

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _render_messages(messages: list[dict]) -> str:
        """Render messages to a text block for the summariser."""
        head_chars = settings.runner_compaction_tool_render_head_chars
        tail_chars = settings.runner_compaction_tool_render_tail_chars
        threshold = head_chars + tail_chars
        lines: list[str] = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content") or ""
            if role == "tool":
                # Truncate very large tool results to avoid blowing up the summary call
                if len(content) > threshold:
                    content = content[:head_chars] + "\n...(truncated)...\n" + content[-tail_chars:]
                lines.append(f"[tool result] {content}")
            else:
                lines.append(f"[{role}] {content}")
        return "\n\n".join(lines)

    @staticmethod
    def _verify_identifier_preservation(
        original_messages: list[dict],
        summary: str,
    ) -> None:
        """Log a warning if critical identifiers were lost during summarisation."""
        original_ids: set[str] = set()
        for msg in original_messages:
            content = str(msg.get("content") or "")
            original_ids.update(IDENTIFIER_RE.findall(content))

        if not original_ids:
            return

        summary_ids = set(IDENTIFIER_RE.findall(summary))
        lost = original_ids - summary_ids
        if lost:
            logger.warning(
                "Compaction lost %d/%d identifiers: %s",
                len(lost),
                len(original_ids),
                list(lost)[:5],
            )
