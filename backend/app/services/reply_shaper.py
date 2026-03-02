from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ReplyShapeResult:
    text: str
    was_suppressed: bool
    suppression_reason: str | None
    dedup_lines_removed: int
    removed_tokens: list[str]


class ReplyShaper:
    def sanitize(self, final_text: str) -> str:
        text = (final_text or "").strip()
        if not text:
            return text

        sanitized = re.sub(r"\[TOOL_CALL\].*?\[/TOOL_CALL\]", "", text, flags=re.IGNORECASE | re.DOTALL)
        sanitized = re.sub(r"\{\s*tool\s*=>.*?\}", "", sanitized, flags=re.IGNORECASE | re.DOTALL)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
        return sanitized

    def shape(
        self,
        raw_response: str | None = None,
        tool_results: str | None = None,
        user_message: str | None = None,
        *,
        final_text: str | None = None,
        tool_markers: set[str] | None = None,
    ) -> ReplyShapeResult:
        _ = user_message
        source_text = final_text if final_text is not None else raw_response
        text = (source_text or "").strip()
        removed_tokens: list[str] = []

        for token in ("NO_REPLY", "ANNOUNCE_SKIP"):
            if token in text:
                removed_tokens.append(token)
                text = text.replace(token, "")

        text = self.sanitize(text)

        deduped_lines = 0
        lines = [line.rstrip() for line in text.splitlines() if line.strip()]
        if lines:
            seen_tool_confirmation: set[str] = set()
            shaped_lines: list[str] = []
            sorted_markers = tuple(sorted(tool_markers or set()))
            for line in lines:
                lowered = line.lower()
                is_tool_confirmation = (
                    bool(sorted_markers)
                    and any(marker in lowered for marker in sorted_markers)
                    and any(keyword in lowered for keyword in ("done", "completed", "finished", "erfolgreich"))
                )
                if is_tool_confirmation:
                    if lowered in seen_tool_confirmation:
                        deduped_lines += 1
                        continue
                    seen_tool_confirmation.add(lowered)
                shaped_lines.append(line)
            text = "\n".join(shaped_lines).strip()

        if tool_results:
            compact = re.sub(r"\s+", " ", text.lower()).strip()
            if compact in {
                "done",
                "done.",
                "completed",
                "completed.",
                "ok",
                "ok.",
                "fertig",
                "fertig.",
            }:
                return ReplyShapeResult(
                    text="",
                    was_suppressed=True,
                    suppression_reason="irrelevant_ack_after_tools",
                    dedup_lines_removed=deduped_lines,
                    removed_tokens=removed_tokens,
                )

        if not text:
            reason = "empty_after_shaping"
            if "NO_REPLY" in removed_tokens:
                reason = "no_reply_token"
            elif "ANNOUNCE_SKIP" in removed_tokens:
                reason = "announce_skip_token"
            return ReplyShapeResult(
                text="",
                was_suppressed=True,
                suppression_reason=reason,
                dedup_lines_removed=deduped_lines,
                removed_tokens=removed_tokens,
            )

        return ReplyShapeResult(
            text=text,
            was_suppressed=False,
            suppression_reason=None,
            dedup_lines_removed=deduped_lines,
            removed_tokens=removed_tokens,
        )
