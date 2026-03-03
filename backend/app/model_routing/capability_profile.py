from __future__ import annotations

from pydantic import BaseModel, Field


class ModelCapabilityProfile(BaseModel):
    model_id: str
    max_context: int = Field(ge=512)
    reasoning_depth: int = Field(ge=0, le=10)
    reflection_passes: int = Field(ge=0, le=10)
    combine_steps: bool = False
    temperature: float = Field(ge=0.0, le=2.0)
    health_score: float = Field(default=0.9, ge=0.0, le=1.0)
    expected_latency_ms: int = Field(default=1200, ge=1)
    cost_score: float = Field(default=0.5, ge=0.0, le=1.0)
