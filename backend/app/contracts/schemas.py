from __future__ import annotations

from pydantic import BaseModel, Field


class HeadCoderInput(BaseModel):
    user_message: str = Field(min_length=1)
    session_id: str = Field(min_length=1, max_length=120)
    request_id: str = Field(min_length=1)
    model: str | None = Field(default=None, max_length=120)


class HeadCoderOutput(BaseModel):
    final_text: str


class PlannerInput(BaseModel):
    user_message: str = Field(min_length=1)
    reduced_context: str = Field(min_length=1)


class PlannerOutput(BaseModel):
    plan_text: str


class ToolSelectorInput(BaseModel):
    user_message: str = Field(min_length=1)
    plan_text: str
    reduced_context: str = Field(min_length=1)


class ToolSelectorOutput(BaseModel):
    tool_results: str


class SynthesizerInput(BaseModel):
    user_message: str = Field(min_length=1)
    plan_text: str
    tool_results: str
    reduced_context: str = Field(min_length=1)


class SynthesizerOutput(BaseModel):
    final_text: str
