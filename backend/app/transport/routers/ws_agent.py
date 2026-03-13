from __future__ import annotations

from fastapi import APIRouter, WebSocket

from app.ws_handler import WsHandlerDependencies, handle_ws_agent


def build_ws_agent_router(*, dependencies: WsHandlerDependencies) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/agent")
    async def agent_socket(websocket: WebSocket):
        await handle_ws_agent(websocket, dependencies)

    return router
