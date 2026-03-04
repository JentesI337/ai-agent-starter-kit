from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ReducedContext:
    rendered: str
    used_tokens: int
    budget_tokens: int


class ContextReducer:
    TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", flags=re.UNICODE)
    _IDENTIFIER_HINT = (
        "Identifier preservation: keep UUIDs, spawned_subrun_id, run_id, session_id, URLs,"
        " hashes, versions and file paths exactly as-is."
    )
    _SENSITIVE_PATTERNS: tuple[tuple[str, str], ...] = (
        (r"(?i)(Bearer\s+)[A-Za-z0-9\-_.]{12,}", r"\1[REDACTED]"),
        (r"(?i)(api[_\-]?key[\"'\s:=]+)[A-Za-z0-9\-_.]{8,}", r"\1[REDACTED]"),
        (r"(?i)(Authorization:\s*)[^\n]{8,}", r"\1[REDACTED]"),
        (r"(?is)-----BEGIN [A-Z ]+KEY-----.*?-----END [A-Z ]+KEY-----", "[REDACTED_PRIVATE_KEY]"),
        (r"(?i)(password[\"'\s:=]+)[^\s\"']{6,}", r"\1[REDACTED]"),
    )

    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self.TOKEN_PATTERN.findall(text))

    def reduce(
        self,
        *,
        budget_tokens: int,
        user_message: str,
        memory_lines: list[str],
        tool_outputs: list[str],
        snapshot_lines: list[str] | None = None,
    ) -> ReducedContext:
        budget = max(128, budget_tokens)
        max_chars = budget * 5
        tool_budget = max(32, int(budget * 0.45))
        memory_budget = max(32, int(budget * 0.35))
        snapshot_budget = max(16, int(budget * 0.15))

        sections: list[str] = []
        task_section = "Current task:\n" + self._truncate_to_tokens(user_message.strip(), max(24, int(budget * 0.25)))
        sections.append(task_section)

        if self._contains_identifier_like_content(user_message, memory_lines, tool_outputs, snapshot_lines):
            sections.append(self._IDENTIFIER_HINT)

        if tool_outputs:
            safe_tool_outputs = [self.strip_sensitive_tool_results(item) for item in tool_outputs]
            clipped_tools = self._collect_items(safe_tool_outputs, max_chars=max_chars // 2, max_tokens=tool_budget)
            if clipped_tools:
                sections.append("Tool outputs:\n" + "\n\n".join(clipped_tools))

        if memory_lines:
            clipped_memory = self._collect_items(memory_lines, max_chars=max_chars // 3, max_tokens=memory_budget)
            if clipped_memory:
                sections.append("Memory:\n" + "\n".join(f"- {line}" for line in clipped_memory))

        if snapshot_lines:
            clipped_snapshot = self._collect_items(snapshot_lines, max_chars=max_chars // 6, max_tokens=snapshot_budget)
            if clipped_snapshot:
                sections.append("Snapshot:\n" + "\n".join(f"- {line}" for line in clipped_snapshot))

        rendered = "\n\n".join(part for part in sections if part.strip())
        rendered = self._truncate_to_tokens(rendered, budget)
        if len(rendered) > max_chars:
            rendered = rendered[:max_chars]

        return ReducedContext(
            rendered=rendered or "Current task:\n(no task)",
            used_tokens=self.estimate_tokens(rendered),
            budget_tokens=budget,
        )

    def strip_sensitive_tool_results(self, context: str) -> str:
        sanitized = str(context or "")
        for pattern, replacement in self._SENSITIVE_PATTERNS:
            sanitized = re.sub(pattern, replacement, sanitized)
        return sanitized

    def _collect_items(self, items: list[str], *, max_chars: int, max_tokens: int) -> list[str]:
        result: list[str] = []
        used = 0
        used_tokens = 0
        for raw in items:
            item = (raw or "").strip()
            if not item:
                continue
            if len(item) > 1800:
                item = item[:1800]
            remaining_tokens = max_tokens - used_tokens
            if remaining_tokens <= 0:
                break
            item = self._truncate_to_tokens(item, remaining_tokens)
            if used + len(item) > max_chars:
                remaining = max_chars - used
                if remaining <= 0:
                    break
                item = item[:remaining]
            if not item:
                continue
            result.append(item)
            used += len(item)
            used_tokens += self.estimate_tokens(item)
            if used >= max_chars:
                break
        return result

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        source = (text or "").strip()
        if not source or max_tokens <= 0:
            return ""

        matches = list(self.TOKEN_PATTERN.finditer(source))
        if len(matches) <= max_tokens:
            return source

        end_index = matches[max_tokens - 1].end()
        return source[:end_index]

    @staticmethod
    def _contains_identifier_like_content(
        user_message: str,
        memory_lines: list[str],
        tool_outputs: list[str],
        snapshot_lines: list[str] | None,
    ) -> bool:
        joined = "\n".join([
            user_message or "",
            *(memory_lines or []),
            *(tool_outputs or []),
            *((snapshot_lines or [])),
        ])
        if not joined.strip():
            return False

        patterns = (
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
            r"\b(?:spawned_subrun_id|run_id|session_id)=[^\s]+",
            r"https?://[^\s]+",
            r"\b[a-f0-9]{7,40}\b",
            r"\b\d+\.\d+\.\d+\b",
            r"[A-Za-z]:\\|/[^\s]+/[^\s]+",
        )
        return any(re.search(pattern, joined, flags=re.IGNORECASE) for pattern in patterns)
