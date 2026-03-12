"""Unified agent adapter — single data-driven adapter for all agents.

Replaces the 15 concrete adapter subclasses in ``head_agent_adapter.py``
with one class that derives all behavior from a :class:`UnifiedAgentRecord`.
"""
from __future__ import annotations

import re
from collections.abc import Callable

from app.agent import HeadAgent
from app.agent.record import UnifiedAgentRecord
from app.config import settings
from app.contracts.agent_contract import AgentConstraints, AgentContract, SendEvent
from app.contracts.schemas import AgentInput, CoderAgentOutput, HeadAgentOutput
from app.tool_policy import ToolPolicyDict

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_BASE_WRITE_DENY: frozenset[str] = frozenset(
    {
        "write_file",
        "apply_patch",
        "run_command",
        "code_execute",
        "start_background_command",
        "kill_background_process",
    }
)

# ---------------------------------------------------------------------------
# Standalone behavioral helpers (ported from head_agent_adapter.py)
# ---------------------------------------------------------------------------


def has_review_evidence(text: str) -> bool:
    """Check whether user message contains concrete review evidence."""
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


def build_read_only_policy(
    incoming: ToolPolicyDict | None,
    mandatory_deny: frozenset[str] | set[str] | None = None,
) -> ToolPolicyDict:
    """Build a deny-heavy tool policy for read-only agents."""
    deny_set = set(mandatory_deny or _BASE_WRITE_DENY)
    requested_allow: list[str] = []
    if isinstance(incoming, dict):
        for item in incoming.get("allow") or []:
            if isinstance(item, str) and item.strip():
                requested_allow.append(item.strip())
        for item in incoming.get("deny") or []:
            if isinstance(item, str) and item.strip():
                deny_set.add(item.strip())
    payload: ToolPolicyDict = {"deny": sorted(deny_set)}
    if requested_allow:
        payload["allow"] = requested_allow
    return payload


# ---------------------------------------------------------------------------
# Unified adapter
# ---------------------------------------------------------------------------


class UnifiedAgentAdapter(AgentContract):
    """Single adapter class that derives all behavior from a UnifiedAgentRecord."""

    input_schema = AgentInput

    def __init__(self, record: UnifiedAgentRecord, delegate: HeadAgent) -> None:
        self._record = record
        self._delegate = delegate
        self.role = record.agent_id
        self.output_schema = (
            CoderAgentOutput if record.agent_id == "coder-agent" else HeadAgentOutput
        )
        self.constraints = AgentConstraints(
            max_context=record.constraints.max_context or settings.max_user_message_length,
            temperature=record.constraints.temperature,
            reasoning_depth=record.constraints.reasoning_depth,
            reflection_passes=record.constraints.reflection_passes,
            combine_steps=record.constraints.combine_steps,
        )

    @property
    def name(self) -> str:
        return self._delegate.name

    @property
    def record(self) -> UnifiedAgentRecord:
        return self._record

    def configure_runtime(self, base_url: str, model: str) -> None:
        self._delegate.configure_runtime(base_url=base_url, model=model)

    def set_spawn_subrun_handler(self, handler) -> None:
        self._delegate.set_spawn_subrun_handler(handler)

    def set_policy_approval_handler(self, handler) -> None:
        self._delegate.set_policy_approval_handler(handler)

    def set_source_agent_context(self, source_agent_id: str | None):
        return self._delegate.set_source_agent_context(source_agent_id)

    def reset_source_agent_context(self, token) -> None:
        self._delegate.reset_source_agent_context(token)

    # ------------------------------------------------------------------
    # Tool policy
    # ------------------------------------------------------------------

    def normalize_tool_policy(self, tool_policy: ToolPolicyDict | None) -> ToolPolicyDict | None:
        tp = self._record.tool_policy
        behavior = self._record.behavior

        # Read-only agents: full deny enforcement
        if tp.read_only:
            # Build effective mandatory deny, removing relaxed tools
            effective_deny = set(tp.mandatory_deny or _BASE_WRITE_DENY)
            for tool in behavior.relaxed_deny:
                effective_deny.discard(tool)
            return build_read_only_policy(tool_policy, effective_deny)

        # Agents with custom deny override (e.g. test-agent, doc-agent, industrytech-agent)
        if behavior.custom_deny_override is not None:
            deny = set(behavior.custom_deny_override)
            if isinstance(tool_policy, dict):
                for item in tool_policy.get("deny") or []:
                    if isinstance(item, str) and item.strip():
                        deny.add(item.strip())
            return {"deny": sorted(deny)}

        # Default: pass through
        return tool_policy

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

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
        behavior = self._record.behavior

        # Review evidence gate
        if behavior.require_review_evidence and not has_review_evidence(user_message):
            message = (
                "I can review this, but I need concrete evidence first. "
                "Please provide one of: file paths, code snippet, diff/patch, commit hash, or source URLs."
            )
            await send_event({"type": "final", "agent": self.name, "message": message})
            return message

        normalized_policy = self.normalize_tool_policy(tool_policy)
        payload = self.input_schema(
            user_message=user_message,
            session_id=session_id,
            request_id=request_id,
            model=model,
            tool_policy=normalized_policy,
        )
        final_text = await self._delegate.run(
            payload.user_message,
            send_event,
            session_id=payload.session_id,
            request_id=payload.request_id,
            model=payload.model,
            tool_policy=payload.tool_policy,
            prompt_mode=prompt_mode,
            should_steer_interrupt=should_steer_interrupt,
        )
        output = self.output_schema(final_text=final_text)
        return output.final_text
