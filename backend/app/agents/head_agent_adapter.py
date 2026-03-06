from __future__ import annotations

import re
from collections.abc import Callable

from app.agent import (
    ArchitectAgent,
    CoderAgent,
    DevOpsAgent,
    DocAgent,
    ECommerceAgent,
    FinTechAgent,
    HeadAgent,
    HealthTechAgent,
    IndustryTechAgent,
    LegalTechAgent,
    RefactorAgent,
    ResearcherAgent,
    ReviewAgent,
    SecurityAgent,
    TestAgent,
)
from app.config import settings
from app.contracts.agent_contract import AgentConstraints, AgentContract, SendEvent
from app.contracts.schemas import AgentInput, CoderAgentOutput, HeadAgentOutput
from app.tool_policy import ToolPolicyDict

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_BASE_WRITE_DENY: frozenset[str] = frozenset({
    "write_file",
    "apply_patch",
    "run_command",
    "code_execute",
    "start_background_command",
    "kill_background_process",
})


def _build_constraints(
    *,
    temperature: float,
    reflection_passes: int,
    reasoning_depth: int = 2,
    max_context: int | None = None,
) -> AgentConstraints:
    return AgentConstraints(
        max_context=max_context or settings.max_user_message_length,
        temperature=temperature,
        reasoning_depth=reasoning_depth,
        reflection_passes=reflection_passes,
        combine_steps=False,
    )


# ---------------------------------------------------------------------------
# Shared base classes
# ---------------------------------------------------------------------------

class _ReadOnlyAgentAdapterMixin:
    """Mixin that provides _build_read_only_policy for read-only agents.

    Subclasses may narrow ``_MANDATORY_DENY`` (e.g. SecurityAgent allows
    ``run_command`` for ``pip audit``).
    """

    _MANDATORY_DENY: frozenset[str] = _BASE_WRITE_DENY

    def _build_read_only_policy(self, incoming: ToolPolicyDict | None) -> ToolPolicyDict:
        requested_allow: list[str] = []
        requested_deny: list[str] = []
        if isinstance(incoming, dict):
            requested_allow = [item.strip() for item in (incoming.get("allow") or []) if isinstance(item, str) and item.strip()]
            requested_deny = [item.strip() for item in (incoming.get("deny") or []) if isinstance(item, str) and item.strip()]
        deny = set(requested_deny) | self._MANDATORY_DENY
        payload: ToolPolicyDict = {"deny": sorted(deny)}
        if requested_allow:
            payload["allow"] = requested_allow
        return payload


class _BaseSpecialistAdapter(AgentContract):
    """Common adapter scaffold — subclasses only set role, delegate class,
    constraints, and optional overrides."""

    input_schema = AgentInput
    output_schema = HeadAgentOutput

    def __init__(self, delegate: HeadAgent | None = None):
        self._delegate = delegate or self._create_delegate()
        self.constraints = self._build_agent_constraints()

    # --- Subclass hooks ---

    def _create_delegate(self) -> HeadAgent:
        raise NotImplementedError

    def _build_agent_constraints(self) -> AgentConstraints:
        return _build_constraints(temperature=0.3, reflection_passes=0)

    # --- AgentContract implementation ---

    @property
    def name(self) -> str:
        return self._delegate.name

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
        effective_policy = self.normalize_tool_policy(tool_policy)
        payload = self.input_schema(
            user_message=user_message,
            session_id=session_id,
            request_id=request_id,
            model=model,
            tool_policy=effective_policy,
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


# ---------------------------------------------------------------------------
# Core agents (original three)
# ---------------------------------------------------------------------------


class HeadAgentAdapter(_BaseSpecialistAdapter):
    role = "head-agent"

    def __init__(self, delegate: HeadAgent | None = None):
        super().__init__(delegate)

    def _create_delegate(self) -> HeadAgent:
        return HeadAgent()

    def _build_agent_constraints(self) -> AgentConstraints:
        return _build_constraints(temperature=0.3, reflection_passes=0)


class CoderAgentAdapter(_BaseSpecialistAdapter):
    role = "coding-agent"
    output_schema = CoderAgentOutput

    def __init__(self, delegate: CoderAgent | None = None):
        super().__init__(delegate)

    def _create_delegate(self) -> HeadAgent:
        return CoderAgent()

    def _build_agent_constraints(self) -> AgentConstraints:
        return _build_constraints(temperature=0.3, reflection_passes=0)


class ReviewAgentAdapter(_ReadOnlyAgentAdapterMixin, _BaseSpecialistAdapter):
    role = "review-agent"

    def __init__(self, delegate: ReviewAgent | None = None):
        super().__init__(delegate)

    def _create_delegate(self) -> HeadAgent:
        return ReviewAgent()

    def _build_agent_constraints(self) -> AgentConstraints:
        return _build_constraints(temperature=0.2, reflection_passes=1)

    def normalize_tool_policy(self, tool_policy: ToolPolicyDict | None) -> ToolPolicyDict | None:
        return self._build_read_only_policy(tool_policy)

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
        if not self._has_review_evidence(user_message):
            message = (
                "I can review this, but I need concrete evidence first. "
                "Please provide one of: file paths, code snippet, diff/patch, commit hash, or source URLs."
            )
            await send_event({"type": "final", "agent": self.name, "message": message})
            return message
        return await super().run(
            user_message,
            send_event,
            session_id=session_id,
            request_id=request_id,
            model=model,
            tool_policy=tool_policy,
            prompt_mode=prompt_mode,
            should_steer_interrupt=should_steer_interrupt,
        )

    @staticmethod
    def _has_review_evidence(text: str) -> bool:
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


# ---------------------------------------------------------------------------
# Wave 1: Core Specialist Agents
# ---------------------------------------------------------------------------


class ResearcherAgentAdapter(_ReadOnlyAgentAdapterMixin, _BaseSpecialistAdapter):
    """Read-only research specialist — breadth-first, fact-oriented, source-citing."""

    role = "researcher-agent"

    def _create_delegate(self) -> HeadAgent:
        return ResearcherAgent()

    def _build_agent_constraints(self) -> AgentConstraints:
        return _build_constraints(
            temperature=0.25,
            reflection_passes=1,
            reasoning_depth=3,
            max_context=16384,
        )

    def normalize_tool_policy(self, tool_policy: ToolPolicyDict | None) -> ToolPolicyDict | None:
        return self._build_read_only_policy(tool_policy)


class ArchitectAgentAdapter(_ReadOnlyAgentAdapterMixin, _BaseSpecialistAdapter):
    """Read-only architecture specialist — ADR-format, trade-off analysis."""

    role = "architect-agent"

    def _create_delegate(self) -> HeadAgent:
        return ArchitectAgent()

    def _build_agent_constraints(self) -> AgentConstraints:
        return _build_constraints(
            temperature=0.35,
            reflection_passes=2,
            reasoning_depth=4,
            max_context=12288,
        )

    def normalize_tool_policy(self, tool_policy: ToolPolicyDict | None) -> ToolPolicyDict | None:
        return self._build_read_only_policy(tool_policy)


class TestAgentAdapter(_BaseSpecialistAdapter):
    """Test specialist — deterministic, test-runner focused, verify-first."""

    role = "test-agent"

    _ALLOWED_COMMANDS_RE = re.compile(
        r"^\s*(pytest|python\s+-m\s+pytest|npm\s+test|npx\s+jest|cargo\s+test|go\s+test|dotnet\s+test)",
        re.IGNORECASE,
    )

    # Test agent can read + execute tests, but NOT write_file/apply_patch
    _MANDATORY_DENY: frozenset[str] = _BASE_WRITE_DENY - {"run_command", "code_execute"}

    def _create_delegate(self) -> HeadAgent:
        return TestAgent()

    def _build_agent_constraints(self) -> AgentConstraints:
        return _build_constraints(
            temperature=0.15,
            reflection_passes=1,
            reasoning_depth=2,
        )

    def normalize_tool_policy(self, tool_policy: ToolPolicyDict | None) -> ToolPolicyDict | None:
        requested_deny: list[str] = []
        if isinstance(tool_policy, dict):
            requested_deny = [item.strip() for item in (tool_policy.get("deny") or []) if isinstance(item, str) and item.strip()]
        deny = set(requested_deny) | self._MANDATORY_DENY
        return {"deny": sorted(deny)}


# ---------------------------------------------------------------------------
# Wave 2: Specialist Agents
# ---------------------------------------------------------------------------


class SecurityAgentAdapter(_ReadOnlyAgentAdapterMixin, _BaseSpecialistAdapter):
    """Read-only security reviewer — depth-first, deterministic, SARIF-style output."""

    role = "security-agent"

    # Security agent can additionally run pip audit / npm audit — allow run_command
    _MANDATORY_DENY: frozenset[str] = _BASE_WRITE_DENY - {"run_command"}

    def _create_delegate(self) -> HeadAgent:
        return SecurityAgent()

    def _build_agent_constraints(self) -> AgentConstraints:
        return _build_constraints(
            temperature=0.1,
            reflection_passes=2,
            reasoning_depth=3,
        )

    def normalize_tool_policy(self, tool_policy: ToolPolicyDict | None) -> ToolPolicyDict | None:
        return self._build_read_only_policy(tool_policy)


class DocAgentAdapter(_BaseSpecialistAdapter):
    """Documentation specialist — creative, markdown-focused, read+write .md only."""

    role = "doc-agent"

    def _create_delegate(self) -> HeadAgent:
        return DocAgent()

    def _build_agent_constraints(self) -> AgentConstraints:
        return _build_constraints(
            temperature=0.4,
            reflection_passes=1,
            reasoning_depth=2,
        )

    def normalize_tool_policy(self, tool_policy: ToolPolicyDict | None) -> ToolPolicyDict | None:
        # Doc agent can read, write (limited to .md), grep, list — no command/patch
        deny = {
            "apply_patch",
            "run_command",
            "code_execute",
            "start_background_command",
            "kill_background_process",
        }
        if isinstance(tool_policy, dict):
            for item in tool_policy.get("deny") or []:
                if isinstance(item, str) and item.strip():
                    deny.add(item.strip())
        return {"deny": sorted(deny)}


class RefactorAgentAdapter(_BaseSpecialistAdapter):
    """Refactoring specialist — plan-execute, safe-transformation, test-validated.

    Intentionally unrestricted — requires full file + command access for
    rename / move / inline / extract refactorings and test validation.
    """

    role = "refactor-agent"

    def _create_delegate(self) -> HeadAgent:
        return RefactorAgent()

    def _build_agent_constraints(self) -> AgentConstraints:
        return _build_constraints(
            temperature=0.2,
            reflection_passes=2,
            reasoning_depth=3,
        )


class DevOpsAgentAdapter(_BaseSpecialistAdapter):
    """DevOps specialist — CI/CD, containerization, infrastructure.

    Intentionally unrestricted — requires full file + command access for
    pipeline configuration, container builds, and deployment scripts.
    """

    role = "devops-agent"

    def _create_delegate(self) -> HeadAgent:
        return DevOpsAgent()

    def _build_agent_constraints(self) -> AgentConstraints:
        return _build_constraints(
            temperature=0.2,
            reflection_passes=1,
            reasoning_depth=2,
        )


# ---------------------------------------------------------------------------
# Industry Expert Agents
# ---------------------------------------------------------------------------


class FinTechAgentAdapter(_ReadOnlyAgentAdapterMixin, _BaseSpecialistAdapter):
    """FinTech specialist — compliance-aware, PCI-DSS / PSD2, audit-trail focused.

    Read-only — no file writes; analyses payment flows, ledger designs, fraud patterns.
    """

    role = "fintech-agent"

    def _create_delegate(self) -> HeadAgent:
        return FinTechAgent()

    def _build_agent_constraints(self) -> AgentConstraints:
        return _build_constraints(
            temperature=0.15,
            reflection_passes=2,
            reasoning_depth=4,
            max_context=16384,
        )

    def normalize_tool_policy(self, tool_policy: ToolPolicyDict | None) -> ToolPolicyDict | None:
        return self._build_read_only_policy(tool_policy)


class HealthTechAgentAdapter(_ReadOnlyAgentAdapterMixin, _BaseSpecialistAdapter):
    """HealthTech specialist — HIPAA / DSGVO / MDR, HL7 FHIR, clinical workflows.

    Strictly read-only — highest security tier; no file writes, no command execution.
    """

    role = "healthtech-agent"

    def _create_delegate(self) -> HeadAgent:
        return HealthTechAgent()

    def _build_agent_constraints(self) -> AgentConstraints:
        return _build_constraints(
            temperature=0.1,
            reflection_passes=2,
            reasoning_depth=4,
            max_context=16384,
        )

    def normalize_tool_policy(self, tool_policy: ToolPolicyDict | None) -> ToolPolicyDict | None:
        return self._build_read_only_policy(tool_policy)


class LegalTechAgentAdapter(_ReadOnlyAgentAdapterMixin, _BaseSpecialistAdapter):
    """LegalTech specialist — DSGVO / CCPA / AI-Act, license scanning, DPIA.

    Read-only — analyses compliance posture, scans for license violations.
    """

    role = "legaltech-agent"

    def _create_delegate(self) -> HeadAgent:
        return LegalTechAgent()

    def _build_agent_constraints(self) -> AgentConstraints:
        return _build_constraints(
            temperature=0.15,
            reflection_passes=2,
            reasoning_depth=3,
            max_context=12288,
        )

    def normalize_tool_policy(self, tool_policy: ToolPolicyDict | None) -> ToolPolicyDict | None:
        return self._build_read_only_policy(tool_policy)


class ECommerceAgentAdapter(_BaseSpecialistAdapter):
    """E-Commerce specialist — catalog, checkout, order processing, SEO.

    Read + write access for implementing catalog models, checkout flows,
    and structured data markup.
    """

    role = "ecommerce-agent"

    def _create_delegate(self) -> HeadAgent:
        return ECommerceAgent()

    def _build_agent_constraints(self) -> AgentConstraints:
        return _build_constraints(
            temperature=0.25,
            reflection_passes=1,
            reasoning_depth=3,
        )


class IndustryTechAgentAdapter(_BaseSpecialistAdapter):
    """IndustryTech specialist — IoT, MQTT/OPC-UA, predictive maintenance, digital twins.

    Read + restricted command access for sensor-data analysis and protocol inspection.
    """

    role = "industrytech-agent"

    # Allow run_command for data-analysis tools, deny file writes
    _MANDATORY_DENY: frozenset[str] = _BASE_WRITE_DENY - {"run_command", "code_execute"}

    def _create_delegate(self) -> HeadAgent:
        return IndustryTechAgent()

    def _build_agent_constraints(self) -> AgentConstraints:
        return _build_constraints(
            temperature=0.2,
            reflection_passes=1,
            reasoning_depth=3,
            max_context=16384,
        )

    def normalize_tool_policy(self, tool_policy: ToolPolicyDict | None) -> ToolPolicyDict | None:
        requested_deny: list[str] = []
        if isinstance(tool_policy, dict):
            requested_deny = [item.strip() for item in (tool_policy.get("deny") or []) if isinstance(item, str) and item.strip()]
        deny = set(requested_deny) | self._MANDATORY_DENY
        return {"deny": sorted(deny)}
