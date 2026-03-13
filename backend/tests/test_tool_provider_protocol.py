from __future__ import annotations

from app.contracts.tool_protocol import ToolProvider
from app.tools.implementations.base import AgentTooling


def test_agent_tooling_implements_tool_provider_protocol(tmp_path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    assert isinstance(tooling, ToolProvider)
