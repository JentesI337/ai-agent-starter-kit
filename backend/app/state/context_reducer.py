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

        if tool_outputs:
            clipped_tools = self._collect_items(tool_outputs, max_chars=max_chars // 2, max_tokens=tool_budget)
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
