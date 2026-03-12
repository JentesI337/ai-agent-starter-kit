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
class PlanStep:
    """Single step in a lightweight execution plan."""

    index: int
    description: str
    expected_tools: list[str] = field(default_factory=list)
    status: str = "pending"  # pending | in_progress | completed | failed
    tool_calls_used: list[str] = field(default_factory=list)


@dataclass
class PlanTracker:
    """Tracks plan steps extracted from LLM <plan> blocks."""

    raw_plan_text: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    current_step_index: int = 0
    replan_count: int = 0
    planning_active: bool = False

    @property
    def current_step(self) -> PlanStep | None:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    @property
    def all_completed(self) -> bool:
        return bool(self.steps) and all(s.status in ("completed", "failed") for s in self.steps)

    def advance(self) -> None:
        """Mark current step completed and move to next."""
        if self.current_step:
            self.current_step.status = "completed"
        self.current_step_index += 1
        if self.current_step:
            self.current_step.status = "in_progress"

    def fail_current(self) -> None:
        """Mark current step as failed."""
        if self.current_step:
            self.current_step.status = "failed"


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
    consecutive_empty_web_calls: int = 0
    plan: PlanTracker = field(default_factory=PlanTracker)
