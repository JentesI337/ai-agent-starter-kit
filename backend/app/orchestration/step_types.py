from __future__ import annotations

from enum import StrEnum


class PipelineStep(StrEnum):
    PLAN = "plan"
    TOOL_SELECT = "tool_select"
    TOOL_EXECUTE = "tool_execute"
    SYNTHESIZE = "synthesize"
