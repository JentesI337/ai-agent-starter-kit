from __future__ import annotations

import re


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
        *,
        final_text: str,
        tool_results: str | None,
        tool_markers: set[str],
    ) -> tuple[str, bool, str | None, list[str], int]:
        text = (final_text or "").strip()
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
            sorted_markers = tuple(sorted(tool_markers))
            for line in lines:
                lowered = line.lower()
                is_tool_confirmation = (
                    any(marker in lowered for marker in sorted_markers)
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
                return "", True, "irrelevant_ack_after_tools", removed_tokens, deduped_lines

        if not text:
            reason = "empty_after_shaping"
            if "NO_REPLY" in removed_tokens:
                reason = "no_reply_token"
            elif "ANNOUNCE_SKIP" in removed_tokens:
                reason = "announce_skip_token"
            return "", True, reason, removed_tokens, deduped_lines

        return text, False, None, removed_tokens, deduped_lines
