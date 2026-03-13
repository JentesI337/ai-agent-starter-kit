"""Agent management tools — create_agent, list_agents.

Mixin that gives the head-agent the ability to create persistent
specialist agents and list the available agent roster.
"""
from __future__ import annotations

import json
import logging

from app.shared.errors import ToolExecutionError

logger = logging.getLogger(__name__)


class AgentManagementToolMixin:
    """Tool mixin for creating and listing persistent agents/specialists."""

    def create_agent(
        self,
        *,
        name: str,
        description: str,
        role: str = "specialist",
        specialization: str = "",
        capabilities: list[str] | None = None,
        system_prompt: str = "",
        preferred_tools: list[str] | None = None,
        forbidden_tools: list[str] | None = None,
        **_kwargs,
    ) -> str:
        """Create a persistent custom specialist agent.

        The agent is immediately available for delegation via spawn_subrun.
        """
        name = (name or "").strip()
        if not name or len(name) > 120:
            raise ToolExecutionError("Agent name must be 1-120 characters.")
        description = (description or "").strip()
        if not description:
            raise ToolExecutionError("Agent description is required.")
        if len(description) > 500:
            raise ToolExecutionError("Description must not exceed 500 characters.")

        from app.agent.store import UnifiedAgentStore
        from app.config import settings

        store = UnifiedAgentStore(
            persist_dir=settings.agents_dir,
            manifest_path=None,
        )

        record_data: dict = {
            "display_name": name,
            "description": description,
            "origin": "custom",
            "category": "custom",
            "enabled": True,
            "role": role or "specialist",
            "specialization": specialization or "",
            "capabilities": [
                c.strip().lower()
                for c in (capabilities or [])
                if isinstance(c, str) and c.strip()
            ],
            "prompts": {},
            "tool_policy": {},
            "delegation": {
                "delegation_preference": "reluctant",
                "supports_delegation": False,
            },
        }

        if system_prompt and system_prompt.strip():
            record_data["prompts"]["system"] = system_prompt.strip()

        if preferred_tools:
            clean = [t.strip() for t in preferred_tools if isinstance(t, str) and t.strip()]
            if clean:
                record_data["tool_policy"]["preferred_tools"] = clean

        if forbidden_tools:
            clean = [t.strip() for t in forbidden_tools if isinstance(t, str) and t.strip()]
            if clean:
                record_data["tool_policy"]["forbidden_tools"] = clean

        try:
            record = store.create(record_data)
            return json.dumps(
                {
                    "status": "created",
                    "agent_id": record.agent_id,
                    "display_name": record.display_name,
                    "description": record.description,
                    "role": record.role,
                    "specialization": record.specialization,
                    "capabilities": record.capabilities,
                    "message": (
                        f"Agent '{record.display_name}' created with ID '{record.agent_id}'. "
                        f"It is now available for delegation via spawn_subrun(agent_id='{record.agent_id}', message='...')."
                    ),
                },
                ensure_ascii=False,
            )
        except ValueError as exc:
            raise ToolExecutionError(f"Failed to create agent: {exc}") from exc

    def list_agents(self, **_kwargs) -> str:
        """List all available agents (built-in and custom) with their capabilities."""
        from app.agent.store import UnifiedAgentStore
        from app.config import settings

        store = UnifiedAgentStore(
            persist_dir=settings.agents_dir,
            manifest_path=None,
        )

        agents = store.list_enabled()
        result = []
        for agent in agents:
            result.append(
                {
                    "agent_id": agent.agent_id,
                    "display_name": agent.display_name,
                    "origin": agent.origin,
                    "role": agent.role,
                    "specialization": agent.specialization,
                    "description": agent.description,
                    "capabilities": agent.capabilities,
                    "category": agent.category,
                }
            )

        return json.dumps(
            {
                "agent_count": len(result),
                "agents": result,
            },
            ensure_ascii=False,
        )
