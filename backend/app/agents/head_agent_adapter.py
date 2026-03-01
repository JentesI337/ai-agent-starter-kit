from __future__ import annotations

import re

from app.agent import CoderAgent, HeadAgent, ReviewAgent
from app.config import settings
from app.contracts.agent_contract import AgentConstraints, AgentContract, SendEvent
from app.contracts.schemas import CoderAgentInput, CoderAgentOutput, HeadAgentInput, HeadAgentOutput


def _build_constraints(*, temperature: float, reflection_passes: int) -> AgentConstraints:
    return AgentConstraints(
        max_context=settings.max_user_message_length,
        temperature=temperature,
        reasoning_depth=2,
        reflection_passes=reflection_passes,
        combine_steps=False,
    )


class HeadAgentAdapter(AgentContract):
    role = "head-agent"
    input_schema = HeadAgentInput
    output_schema = HeadAgentOutput

    def __init__(self, delegate: HeadAgent | None = None):
        self._delegate = delegate or HeadAgent()
        self.constraints = _build_constraints(temperature=0.3, reflection_passes=0)

    @property
    def name(self) -> str:
        return self._delegate.name

    def configure_runtime(self, base_url: str, model: str) -> None:
        self._delegate.configure_runtime(base_url=base_url, model=model)

    def set_spawn_subrun_handler(self, handler) -> None:
        self._delegate.set_spawn_subrun_handler(handler)

    def set_policy_approval_handler(self, handler) -> None:
        self._delegate.set_policy_approval_handler(handler)

    async def run(
        self,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None = None,
        tool_policy: dict[str, list[str]] | None = None,
    ) -> str:
        payload = self.input_schema(
            user_message=user_message,
            session_id=session_id,
            request_id=request_id,
            model=model,
            tool_policy=tool_policy,
        )
        final_text = await self._delegate.run(
            payload.user_message,
            send_event,
            session_id=payload.session_id,
            request_id=payload.request_id,
            model=payload.model,
            tool_policy=payload.tool_policy,
        )
        output = self.output_schema(final_text=final_text)
        return output.final_text


class CoderAgentAdapter(AgentContract):
    role = "coding-agent"
    input_schema = CoderAgentInput
    output_schema = CoderAgentOutput

    def __init__(self, delegate: CoderAgent | None = None):
        self._delegate = delegate or CoderAgent()
        self.constraints = _build_constraints(temperature=0.3, reflection_passes=0)

    @property
    def name(self) -> str:
        return self._delegate.name

    def configure_runtime(self, base_url: str, model: str) -> None:
        self._delegate.configure_runtime(base_url=base_url, model=model)

    def set_spawn_subrun_handler(self, handler) -> None:
        self._delegate.set_spawn_subrun_handler(handler)

    def set_policy_approval_handler(self, handler) -> None:
        self._delegate.set_policy_approval_handler(handler)

    async def run(
        self,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None = None,
        tool_policy: dict[str, list[str]] | None = None,
    ) -> str:
        payload = self.input_schema(
            user_message=user_message,
            session_id=session_id,
            request_id=request_id,
            model=model,
            tool_policy=tool_policy,
        )
        final_text = await self._delegate.run(
            payload.user_message,
            send_event,
            session_id=payload.session_id,
            request_id=payload.request_id,
            model=payload.model,
            tool_policy=payload.tool_policy,
        )
        output = self.output_schema(final_text=final_text)
        return output.final_text


class ReviewAgentAdapter(AgentContract):
    role = "review-agent"
    input_schema = HeadAgentInput
    output_schema = HeadAgentOutput

    _MANDATORY_DENY = {
        "write_file",
        "apply_patch",
        "run_command",
        "start_background_command",
        "kill_background_process",
    }

    def __init__(self, delegate: ReviewAgent | None = None):
        self._delegate = delegate or ReviewAgent()
        self.constraints = _build_constraints(temperature=0.2, reflection_passes=1)

    @property
    def name(self) -> str:
        return self._delegate.name

    def configure_runtime(self, base_url: str, model: str) -> None:
        self._delegate.configure_runtime(base_url=base_url, model=model)

    def set_spawn_subrun_handler(self, handler) -> None:
        self._delegate.set_spawn_subrun_handler(handler)

    def set_policy_approval_handler(self, handler) -> None:
        self._delegate.set_policy_approval_handler(handler)

    def normalize_tool_policy(self, tool_policy: dict[str, list[str]] | None) -> dict[str, list[str]] | None:
        return self._build_read_only_policy(tool_policy)

    async def run(
        self,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None = None,
        tool_policy: dict[str, list[str]] | None = None,
    ) -> str:
        if not self._has_review_evidence(user_message):
            message = (
                "I can review this, but I need concrete evidence first. "
                "Please provide one of: file paths, code snippet, diff/patch, commit hash, or source URLs."
            )
            await send_event({"type": "final", "agent": self.name, "message": message})
            return message

        payload = self.input_schema(
            user_message=user_message,
            session_id=session_id,
            request_id=request_id,
            model=model,
            tool_policy=self.normalize_tool_policy(tool_policy),
        )
        final_text = await self._delegate.run(
            payload.user_message,
            send_event,
            session_id=payload.session_id,
            request_id=payload.request_id,
            model=payload.model,
            tool_policy=payload.tool_policy,
        )
        output = self.output_schema(final_text=final_text)
        return output.final_text

    def _build_read_only_policy(self, incoming: dict[str, list[str]] | None) -> dict[str, list[str]]:
        requested_allow = []
        requested_deny = []

        if isinstance(incoming, dict):
            for item in incoming.get("allow") or []:
                if isinstance(item, str) and item.strip():
                    requested_allow.append(item.strip())
            for item in incoming.get("deny") or []:
                if isinstance(item, str) and item.strip():
                    requested_deny.append(item.strip())

        deny = set(requested_deny)
        deny |= self._MANDATORY_DENY

        payload: dict[str, list[str]] = {"deny": sorted(deny)}
        if requested_allow:
            payload["allow"] = requested_allow
        return payload

    def _has_review_evidence(self, text: str) -> bool:
        raw = (text or "").strip()
        if not raw:
            return False

        patterns = (
            r"https?://",
            r"```",
            r"diff\s+--git",
            r"\b[a-f0-9]{7,40}\b",
            r"\b[\w./-]+\.(py|ts|js|java|go|rs|json|yml|yaml|md|html|css)\b",
            r"\b(\+\+\+|---|@@)\b",
        )
        return any(re.search(pattern, raw, re.IGNORECASE) for pattern in patterns)


HeadCoderAgentAdapter = HeadAgentAdapter
