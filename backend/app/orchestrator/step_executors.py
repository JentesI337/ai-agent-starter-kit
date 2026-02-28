from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.contracts.schemas import PlannerInput, SynthesizerInput, ToolSelectorInput

PlanFn = Callable[[PlannerInput, str | None], Awaitable[str]]
ToolFn = Callable[[ToolSelectorInput, str, str, Callable[[dict], Awaitable[None]], str | None], Awaitable[str]]
SynthesizeFn = Callable[[SynthesizerInput, str, str, Callable[[dict], Awaitable[None]], str | None], Awaitable[str]]


@dataclass(frozen=True)
class PlannerStepExecutor:
    execute_fn: PlanFn

    async def execute(self, payload: PlannerInput, model: str | None) -> str:
        return await self.execute_fn(payload, model)


@dataclass(frozen=True)
class ToolStepExecutor:
    execute_fn: ToolFn

    async def execute(
        self,
        payload: ToolSelectorInput,
        session_id: str,
        request_id: str,
        send_event: Callable[[dict], Awaitable[None]],
        model: str | None,
    ) -> str:
        return await self.execute_fn(payload, session_id, request_id, send_event, model)


@dataclass(frozen=True)
class SynthesizeStepExecutor:
    execute_fn: SynthesizeFn

    async def execute(
        self,
        payload: SynthesizerInput,
        session_id: str,
        request_id: str,
        send_event: Callable[[dict], Awaitable[None]],
        model: str | None,
    ) -> str:
        return await self.execute_fn(payload, session_id, request_id, send_event, model)
