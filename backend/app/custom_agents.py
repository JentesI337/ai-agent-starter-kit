from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from app.contracts.agent_contract import AgentConstraints, AgentContract, SendEvent
from app.tool_policy import ToolPolicyDict


class CustomAgentDefinition(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    base_agent_id: str = Field(default="head-agent", min_length=1, max_length=80)
    workflow_steps: list[str] = Field(default_factory=list)
    tool_policy: ToolPolicyDict | None = None
    allow_subrun_delegation: bool = False
    workspace_scope: str | None = Field(default=None, min_length=1, max_length=120)
    skills_scope: str | None = Field(default=None, min_length=1, max_length=120)
    credential_scope: str | None = Field(default=None, min_length=1, max_length=120)


class CustomAgentCreateRequest(BaseModel):
    id: str | None = Field(default=None, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    base_agent_id: str = Field(default="head-agent", min_length=1, max_length=80)
    workflow_steps: list[str] = Field(default_factory=list)
    tool_policy: ToolPolicyDict | None = None
    allow_subrun_delegation: bool = False
    workspace_scope: str | None = Field(default=None, min_length=1, max_length=120)
    skills_scope: str | None = Field(default=None, min_length=1, max_length=120)
    credential_scope: str | None = Field(default=None, min_length=1, max_length=120)


class CustomAgentAdapter(AgentContract):
    role = "custom-agent"
    input_schema = CustomAgentDefinition
    output_schema = CustomAgentDefinition
    constraints = AgentConstraints(
        max_context=8192,
        temperature=0.3,
        reasoning_depth=2,
        reflection_passes=0,
        combine_steps=False,
    )

    def __init__(self, definition: CustomAgentDefinition, base_agent: AgentContract):
        self.definition = definition
        self._base_agent = base_agent

    @property
    def name(self) -> str:
        return self.definition.name

    def configure_runtime(self, base_url: str, model: str) -> None:
        self._base_agent.configure_runtime(base_url=base_url, model=model)

    async def run(
        self,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None = None,
        tool_policy: ToolPolicyDict | None = None,
        prompt_mode: str | None = None,
        should_steer_interrupt: Callable[[], bool] | None = None,
    ) -> str:
        flow_instruction = self._build_flow_instruction()
        enriched_user_message = user_message.strip()
        if flow_instruction:
            enriched_user_message = (
                f"{user_message.strip()}\n\n"
                f"Custom workflow to follow:\n{flow_instruction}\n"
                "Execute these steps in order unless blocked by missing context."
            )

        merged_policy = self._merge_tool_policy(tool_policy)
        source_token = None
        context_set = False
        set_source_context = getattr(self._base_agent, "set_source_agent_context", None)
        reset_source_context = getattr(self._base_agent, "reset_source_agent_context", None)
        if callable(set_source_context):
            source_token = set_source_context(self.definition.id)
            context_set = True
        try:
            return await self._base_agent.run(
                user_message=enriched_user_message,
                send_event=send_event,
                session_id=session_id,
                request_id=request_id,
                model=model,
                tool_policy=merged_policy,
                prompt_mode=prompt_mode,
                should_steer_interrupt=should_steer_interrupt,
            )
        finally:
            if context_set and callable(reset_source_context):
                reset_source_context(source_token)

    def _build_flow_instruction(self) -> str:
        lines: list[str] = []
        if self.definition.description.strip():
            lines.append(f"Goal: {self.definition.description.strip()}")
        for index, step in enumerate(self.definition.workflow_steps, start=1):
            text = (step or "").strip()
            if not text:
                continue
            lines.append(f"{index}. {text}")
        return "\n".join(lines)

    def _merge_tool_policy(self, incoming: ToolPolicyDict | None) -> ToolPolicyDict | None:
        base_policy = self.definition.tool_policy or {}
        request_policy = incoming or {}

        allow_values: list[str] = []
        deny_values: list[str] = []

        for item in (base_policy.get("allow") or []) + (request_policy.get("allow") or []):
            if isinstance(item, str) and item.strip() and item not in allow_values:
                allow_values.append(item.strip())

        for item in (base_policy.get("deny") or []) + (request_policy.get("deny") or []):
            if isinstance(item, str) and item.strip() and item not in deny_values:
                deny_values.append(item.strip())

        if not allow_values and not deny_values:
            return None

        payload: ToolPolicyDict = {}
        if allow_values:
            payload["allow"] = allow_values
        if deny_values:
            payload["deny"] = deny_values
        return payload


class CustomAgentStore:
    def __init__(self, persist_dir: str):
        self.persist_dir = Path(persist_dir).resolve()
        self.persist_dir.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[CustomAgentDefinition]:
        items: list[CustomAgentDefinition] = []
        for file_path in sorted(self.persist_dir.glob("*.json")):
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
                item = CustomAgentDefinition.model_validate(payload)
                items.append(item)
            except Exception:
                continue
        return items

    def upsert(self, request: CustomAgentCreateRequest, id_factory: Callable[[str], str] | None = None) -> CustomAgentDefinition:
        source_id = request.id or request.name
        normalized_id = self._normalize_id(source_id)
        if not normalized_id and id_factory is not None:
            normalized_id = self._normalize_id(id_factory(request.name))
        if not normalized_id:
            normalized_id = "custom-agent"

        definition = CustomAgentDefinition(
            id=normalized_id,
            name=request.name.strip(),
            description=request.description.strip(),
            base_agent_id=request.base_agent_id.strip().lower(),
            workflow_steps=[step.strip() for step in request.workflow_steps if isinstance(step, str) and step.strip()],
            tool_policy=request.tool_policy,
            allow_subrun_delegation=bool(request.allow_subrun_delegation),
            workspace_scope=(request.workspace_scope or "").strip() or None,
            skills_scope=(request.skills_scope or "").strip() or None,
            credential_scope=(request.credential_scope or "").strip() or None,
        )
        file_path = self.persist_dir / f"{definition.id}.json"
        file_path.write_text(
            json.dumps(definition.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return definition

    def delete(self, agent_id: str) -> bool:
        target_id = self._normalize_id(agent_id)
        if not target_id:
            return False
        file_path = self.persist_dir / f"{target_id}.json"
        if not file_path.exists():
            return False
        file_path.unlink(missing_ok=True)
        return True

    def _normalize_id(self, raw: str) -> str:
        candidate = (raw or "").strip().lower()
        candidate = re.sub(r"[^a-z0-9_-]+", "-", candidate)
        candidate = re.sub(r"-+", "-", candidate).strip("-")
        return candidate[:80]
