"""Data types for the AgentRunner continuous streaming tool loop."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolCall:
    """Single tool call from an LLM response."""

    id: str  # "call_abc123"
    name: str  # "read_file"
    arguments: dict  # {"path": "src/main.py"}


@dataclass(frozen=True)
class StreamResult:
    """Result of a streamed LLM call."""

    text: str  # Collected text (may be empty when tool_calls present)
    tool_calls: tuple[ToolCall, ...]  # Parsed tool_calls (empty when text-only)
    finish_reason: str  # "stop" | "tool_calls" | "length"
    usage: dict = field(default_factory=dict)  # Token counts


@dataclass
class ToolResult:
    """Result of a tool execution."""

    tool_call_id: str  # Reference to ToolCall.id
    tool_name: str  # "read_file"
    content: str  # Tool output
    is_error: bool  # True if tool failed
    duration_ms: int = 0  # Execution time


@dataclass
class LoopState:
    """Tracking state for the continuous loop."""

    iteration: int = 0
    total_tool_calls: int = 0
    total_tokens_used: int = 0
    elapsed_seconds: float = 0.0
    tool_call_history: list[dict] = field(default_factory=list)
    loop_detected: bool = False
    budget_exhausted: bool = False
    steer_interrupted: bool = False
