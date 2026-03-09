"""Pydantic model for runtime-configurable agent parameters."""
from __future__ import annotations
from pydantic import BaseModel, Field


class AgentRuntimeConfig(BaseModel):
    agent_id: str
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    reflection_passes: int = Field(default=0, ge=0, le=10)
    reasoning_depth: int = Field(default=2, ge=0, le=10)
    max_context: int | None = Field(default=None, ge=256)
    combine_steps: bool = False
    read_only: bool = False
    mandatory_deny_tools: list[str] = Field(default_factory=list)
    additional_deny_tools: list[str] = Field(default_factory=list)
    additional_allow_tools: list[str] = Field(default_factory=list)
