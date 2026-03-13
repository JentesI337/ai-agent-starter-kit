"""
HTTP/WebSocket transport layer.

Imports allowed from: agent/, orchestration/, workflows/, shared/, policy/,
contracts/, config/, session/, state/, memory/
"""
from app.transport.app_factory import build_fastapi_app, build_lifespan_context
from app.transport.app_state import ControlPlaneState

__all__ = ["ControlPlaneState", "build_fastapi_app", "build_lifespan_context"]
