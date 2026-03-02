from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import APIRouter


@dataclass(frozen=True)
class RunApiRouterHandlers:
    agent_test_handler: Callable[[dict], Awaitable[dict]]
    start_run_handler: Callable[[dict], dict]
    wait_run_handler: Callable[[str, int | None, int | None], Awaitable[dict]]


def build_run_api_router(*, handlers: RunApiRouterHandlers) -> APIRouter:
    router = APIRouter()

    @router.post("/api/test/agent")
    async def test_agent(request_data: dict) -> dict:
        return await handlers.agent_test_handler(request_data)

    @router.post("/api/runs/start")
    async def start_run(request_data: dict) -> dict:
        return handlers.start_run_handler(request_data)

    @router.get("/api/runs/{run_id}/wait")
    async def wait_run(run_id: str, timeout_ms: int | None = None, poll_interval_ms: int | None = None) -> dict:
        return await handlers.wait_run_handler(run_id, timeout_ms, poll_interval_ms)

    return router
