"""Concrete tool implementations."""
__all__ = [
    "COMMAND_SAFETY_PATTERNS",
    "AgentTooling",
    "ApiConnectorToolMixin",
    "BrowserToolMixin",
    "CodeExecToolMixin",
    "DevOpsToolMixin",
    "FileSystemToolMixin",
    "MultimodalToolMixin",
    "ShellToolMixin",
    "WebToolMixin",
    "WorkflowToolMixin",
    "find_command_safety_violation",
    "find_semantic_command_safety_violation",
]

# Lazy imports to avoid circular issues during init
def __getattr__(name):
    if name in (
        "AgentTooling",
        "COMMAND_SAFETY_PATTERNS",
        "find_command_safety_violation",
        "find_semantic_command_safety_violation",
    ):
        from app.tools.implementations.base import (
            COMMAND_SAFETY_PATTERNS,
            AgentTooling,
            find_command_safety_violation,
            find_semantic_command_safety_violation,
        )
        _map = {
            "AgentTooling": AgentTooling,
            "COMMAND_SAFETY_PATTERNS": COMMAND_SAFETY_PATTERNS,
            "find_command_safety_violation": find_command_safety_violation,
            "find_semantic_command_safety_violation": find_semantic_command_safety_violation,
        }
        return _map[name]
    if name == "FileSystemToolMixin":
        from app.tools.implementations.filesystem import FileSystemToolMixin
        return FileSystemToolMixin
    if name == "ShellToolMixin":
        from app.tools.implementations.shell import ShellToolMixin
        return ShellToolMixin
    if name == "WebToolMixin":
        from app.tools.implementations.web import WebToolMixin
        return WebToolMixin
    if name == "BrowserToolMixin":
        from app.tools.implementations.browser import BrowserToolMixin
        return BrowserToolMixin
    if name == "CodeExecToolMixin":
        from app.tools.implementations.code_execution import CodeExecToolMixin
        return CodeExecToolMixin
    if name == "ApiConnectorToolMixin":
        from app.tools.implementations.api_connectors import ApiConnectorToolMixin
        return ApiConnectorToolMixin
    if name == "MultimodalToolMixin":
        from app.tools.implementations.multimodal import MultimodalToolMixin
        return MultimodalToolMixin
    if name == "DevOpsToolMixin":
        from app.tools.implementations.devops import DevOpsToolMixin
        return DevOpsToolMixin
    if name == "WorkflowToolMixin":
        from app.tools.implementations.workflow import WorkflowToolMixin
        return WorkflowToolMixin
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
