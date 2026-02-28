from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from pydantic import BaseModel, Field

SendEvent = Callable[[dict], Awaitable[None]]


class AgentConstraints(BaseModel):
    max_context: int = Field(ge=256)
    temperature: float = Field(ge=0.0, le=2.0)
    reasoning_depth: int = Field(ge=0, le=10)
    reflection_passes: int = Field(ge=0, le=10)
    combine_steps: bool = False


class AgentContract(ABC):
    role: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    constraints: AgentConstraints

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def configure_runtime(self, base_url: str, model: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def run(
        self,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None = None,
    ) -> str:
        raise NotImplementedError
