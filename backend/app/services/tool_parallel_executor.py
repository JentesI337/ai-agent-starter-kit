"""Extracted parallel read-only execution logic from ToolExecutionManager."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

READ_ONLY_TOOLS: frozenset[str] = frozenset({
    "list_dir", "read_file", "file_search", "grep_search",
    "list_code_usages", "get_changed_files", "web_fetch",
})


class ToolParallelExecutor:
    """Handles parallel execution of read-only tool calls."""

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled

    def can_parallelize(self, tool_calls: list[dict[str, Any]]) -> bool:
        """Check if all tool calls in the batch are read-only."""
        if not self.enabled or len(tool_calls) <= 1:
            return False
        return all(
            call.get("name") in READ_ONLY_TOOLS
            for call in tool_calls
        )

    async def execute_parallel(
        self,
        tool_calls: list[dict[str, Any]],
        executor_fn,
    ) -> list[dict[str, Any]]:
        """Execute read-only tool calls in parallel."""
        tasks = [
            asyncio.create_task(executor_fn(call))
            for call in tool_calls
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed.append({
                    "tool_name": tool_calls[i].get("name", "unknown"),
                    "error": str(result),
                })
            else:
                processed.append(result)
        return processed
