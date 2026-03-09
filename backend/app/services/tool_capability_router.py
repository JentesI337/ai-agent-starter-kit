"""Extracted capability inference logic from ToolExecutionManager."""
from __future__ import annotations

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Capability -> keywords mapping
CAPABILITY_PATTERNS: dict[str, list[str]] = {
    "web_retrieval": [
        "url", "http", "https", "website", "webpage", "fetch", "download",
        "browse", "search online", "web search", "google",
    ],
    "filesystem_read": [
        "read file", "show file", "list dir", "find file", "search code",
        "grep", "cat ", "show me", "what's in",
    ],
    "filesystem_write": [
        "write file", "create file", "save", "modify", "edit",
        "patch", "update file", "change file",
    ],
    "code_execution": [
        "run", "execute", "script", "command", "terminal",
        "shell", "compile", "build", "test",
    ],
    "code_modification": [
        "refactor", "fix", "implement", "add feature", "change code",
        "update code", "rewrite", "optimize",
    ],
    "analysis": [
        "analyze", "review", "audit", "check", "inspect",
        "explain", "understand", "architecture",
    ],
}

# Capability -> required tools
CAPABILITY_TOOLS: dict[str, set[str]] = {
    "web_retrieval": {"web_fetch", "web_search", "http_request"},
    "filesystem_read": {"list_dir", "read_file", "file_search", "grep_search", "list_code_usages", "get_changed_files"},
    "filesystem_write": {"write_file", "apply_patch"},
    "code_execution": {"run_command", "code_execute", "start_background_command"},
    "code_modification": {"write_file", "apply_patch", "run_command"},
    "analysis": {"read_file", "grep_search", "list_code_usages"},
}


class ToolCapabilityRouter:
    """Infers required capabilities from user messages and plans."""

    def infer_capabilities(self, *, user_message: str, plan_text: str | None = None) -> set[str]:
        """Return set of capability keys inferred from the input."""
        combined = (user_message or "").lower()
        if plan_text:
            combined += " " + plan_text.lower()

        capabilities: set[str] = set()
        for capability, keywords in CAPABILITY_PATTERNS.items():
            for keyword in keywords:
                if keyword in combined:
                    capabilities.add(capability)
                    break
        return capabilities

    def required_tools(self, capabilities: set[str]) -> set[str]:
        """Return the union of tools needed for the given capabilities."""
        tools: set[str] = set()
        for cap in capabilities:
            tools.update(CAPABILITY_TOOLS.get(cap, set()))
        return tools

    def filter_tools(
        self,
        available_tools: set[str],
        *,
        user_message: str,
        plan_text: str | None = None,
    ) -> set[str]:
        """Return filtered tool set based on inferred capabilities.
        Always includes all available tools if no capabilities are detected.
        """
        caps = self.infer_capabilities(user_message=user_message, plan_text=plan_text)
        if not caps:
            return available_tools
        needed = self.required_tools(caps)
        # Always keep analysis tools
        needed.update(CAPABILITY_TOOLS.get("analysis", set()))
        return available_tools & needed if needed else available_tools
