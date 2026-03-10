from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ReplyShapeResult:
    text: str
    was_suppressed: bool
    suppression_reason: str | None
    dedup_lines_removed: int
    removed_tokens: list[str]


@dataclass(frozen=True)
class SectionContractValidation:
    is_valid: bool
    missing_sections: list[str]
    sections_without_bullets: list[str]

    @property
    def failures(self) -> list[str]:
        items: list[str] = []
        items.extend(f"missing_section:{section}" for section in self.missing_sections)
        items.extend(f"missing_bullet:{section}" for section in self.sections_without_bullets)
        return items


class ReplyShaper:
    def sanitize(self, final_text: str) -> str:
        text = (final_text or "").strip()
        if not text:
            return text

        sanitized = re.sub(r"\[TOOL_CALL\].*?\[/TOOL_CALL\]", "", text, flags=re.IGNORECASE | re.DOTALL)
        sanitized = re.sub(
            r"^\s*\{\s*tool\s*=>[^\n]*\}\s*$",
            "",
            sanitized,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        return re.sub(r"\n{3,}", "\n\n", sanitized).strip()

    def shape(
        self,
        raw_response: str | None = None,
        tool_results: str | None = None,
        *,
        final_text: str | None = None,
        tool_markers: set[str] | None = None,
    ) -> ReplyShapeResult:
        source_text = final_text if final_text is not None else raw_response
        text = (source_text or "").strip()

        text = self.sanitize(text)

        deduped_lines = 0
        lines = [line.rstrip() for line in text.splitlines() if line.strip()]
        if lines:
            shaped_lines: list[str] = []
            sorted_markers = tuple(sorted(tool_markers or set()))
            previous_confirmation_key: str | None = None
            in_fenced_block = False
            for line in lines:
                if line.strip().startswith("```"):
                    in_fenced_block = not in_fenced_block
                    shaped_lines.append(line)
                    previous_confirmation_key = None
                    continue

                lowered = line.lower()
                is_tool_confirmation = (
                    not in_fenced_block
                    and bool(sorted_markers)
                    and any(marker in lowered for marker in sorted_markers)
                    and any(keyword in lowered for keyword in ("done", "completed", "finished", "erfolgreich"))
                )
                if is_tool_confirmation:
                    confirmation_key = self._normalize_confirmation_line(lowered)
                    if confirmation_key and previous_confirmation_key == confirmation_key:
                        deduped_lines += 1
                        continue
                    previous_confirmation_key = confirmation_key
                else:
                    previous_confirmation_key = None
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
                    removed_tokens=[],
                )

        if not text:
            return ReplyShapeResult(
                text="",
                was_suppressed=True,
                suppression_reason="empty_after_shaping",
                dedup_lines_removed=deduped_lines,
                removed_tokens=[],
            )

        return ReplyShapeResult(
            text=text,
            was_suppressed=False,
            suppression_reason=None,
            dedup_lines_removed=deduped_lines,
            removed_tokens=[],
        )

    def validate_section_contract(
        self, final_text: str, required_sections: tuple[str, ...]
    ) -> SectionContractValidation:
        text = (final_text or "").strip()
        if not required_sections:
            return SectionContractValidation(is_valid=True, missing_sections=[], sections_without_bullets=[])

        lines = [line.rstrip() for line in text.splitlines()]
        section_positions: dict[str, int] = {}

        for section in required_sections:
            position = self._find_section_line(lines=lines, section=section)
            if position >= 0:
                section_positions[section] = position

        missing_sections = [section for section in required_sections if section not in section_positions]
        sections_without_bullets: list[str] = []

        ordered_found_sections = [section for section in required_sections if section in section_positions]
        for index, section in enumerate(ordered_found_sections):
            section_line = section_positions[section]
            next_line = len(lines)
            if index + 1 < len(ordered_found_sections):
                next_section = ordered_found_sections[index + 1]
                next_line = section_positions[next_section]
            if not self._has_bullet_between(lines=lines, start=section_line + 1, end=next_line):
                sections_without_bullets.append(section)

        return SectionContractValidation(
            is_valid=not missing_sections and not sections_without_bullets,
            missing_sections=missing_sections,
            sections_without_bullets=sections_without_bullets,
        )

    def _find_section_line(self, *, lines: list[str], section: str) -> int:
        escaped = re.escape(section)
        # BUG-1: Patterns previously required the header to sit alone on its
        # line (anchored with $).  LLMs routinely write inline content after
        # the header (e.g. "**Answer**: The root cause is …").  The trailing
        # anchor is removed; \b prevents false prefix matches (e.g.
        # "Answering" would not match "Answer").
        patterns = (
            re.compile(rf"^\s*{escaped}\b\s*:?", flags=re.IGNORECASE),
            re.compile(rf"^\s*\*\*{escaped}\s*:?\*\*\s*:?", flags=re.IGNORECASE),
            re.compile(rf"^\s*#+\s*{escaped}\b", flags=re.IGNORECASE),
        )
        for idx, line in enumerate(lines):
            candidate = line.strip()
            if not candidate:
                continue
            if any(pattern.match(candidate) for pattern in patterns):
                return idx
        return -1

    def _has_bullet_between(self, *, lines: list[str], start: int, end: int) -> bool:
        bullet_pattern = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+.+")
        for idx in range(max(0, start), min(len(lines), end)):
            candidate = lines[idx].strip()
            if not candidate:
                continue
            if bullet_pattern.match(candidate):
                return True
        return False

    def _normalize_confirmation_line(self, line: str) -> str:
        compact = re.sub(r"[^a-z0-9\s]", "", line.lower())
        return re.sub(r"\s+", " ", compact).strip()
