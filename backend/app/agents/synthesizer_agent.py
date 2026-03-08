from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable

from app.config import settings
from app.contracts.agent_contract import AgentConstraints, AgentContract, SendEvent
from app.contracts.schemas import SynthesizerInput, SynthesizerOutput
from app.errors import LlmClientError
from app.llm_client import LlmClient
from app.services.dynamic_temperature import DynamicTemperatureResolver
from app.services.prompt_ab_registry import PromptAbRegistry
from app.services.prompt_kernel_builder import PromptKernelBuilder
from app.services.reply_shaper import ReplyShaper
from app.services.request_normalization import normalize_prompt_mode
from app.tool_policy import ToolPolicyDict

EmitLifecycleFn = Callable[[SendEvent, str, str, str, dict | None], Awaitable[None]]


class SynthesizerAgent(AgentContract):
    role = "synthesizer-agent"
    input_schema = SynthesizerInput
    output_schema = SynthesizerOutput
    constraints = AgentConstraints(
        max_context=8192,
        temperature=0.3,
        reasoning_depth=2,
        reflection_passes=1,
        combine_steps=True,
    )

    def __init__(
        self,
        *,
        client: LlmClient,
        agent_name: str,
        emit_lifecycle_fn: EmitLifecycleFn,
        system_prompt: str,
        stream_timeout_seconds: float = 600.0,
        reply_shaper: ReplyShaper | None = None,
        temperature_resolver: DynamicTemperatureResolver | None = None,
        prompt_ab_registry: PromptAbRegistry | None = None,
    ):
        self.client = client
        self.agent_name = agent_name
        self._emit_lifecycle_fn = emit_lifecycle_fn
        self.system_prompt = system_prompt
        self.stream_timeout_seconds = max(0.01, float(stream_timeout_seconds))
        self._reply_shaper = reply_shaper or ReplyShaper()
        self._kernel_builder = PromptKernelBuilder()
        self._temperature_resolver = temperature_resolver
        self._ab_registry = prompt_ab_registry
        self._last_prompt_variant_id: str | None = None

    @property
    def name(self) -> str:
        return "synthesizer-agent"

    def configure_runtime(self, base_url: str, model: str) -> None:
        self.client = LlmClient(base_url=base_url, model=model)

    @property
    def last_prompt_variant_id(self) -> str | None:
        return self._last_prompt_variant_id

    @staticmethod
    def _requires_hard_research_structure(user_message: str) -> bool:
        normalized = (user_message or "").lower()
        has_structured_section_markers = (
            "architektur-risiken" in normalized
            and "performance-hotspots" in normalized
            and "guardrail-lücken" in normalized
            and ("priorisierte maßnahmen" in normalized or "top 10" in normalized)
            and ("messbare kpis" in normalized or "kpi" in normalized)
            and ("rollout-plan" in normalized or "rollout plan" in normalized)
        )
        if has_structured_section_markers:
            return True

        has_legacy_hard_markers = (
            "architektur-risiken" in normalized
            and "performance-hotspots" in normalized
            and "guardrail-lücken" in normalized
            and ("rollout-plan" in normalized or "rollout plan" in normalized)
            and "3 phasen" in normalized
        )
        if has_legacy_hard_markers:
            return True

        depth_markers = (
            "tiefe technische research-analyse" in normalized
            or "research-analyse" in normalized
            or "rein textuell" in normalized
        )
        phase_markers = "rollout-plan" in normalized and "3 phasen" in normalized
        kpi_markers = "kpi" in normalized or "messbare" in normalized
        tool_ban_markers = "keine tools" in normalized and "keine shell/systemkommandos" in normalized
        return depth_markers and phase_markers and kpi_markers and tool_ban_markers

    def _build_final_prompt(
        self, payload: SynthesizerInput, *, task_type: str, session_id: str
    ) -> tuple[str, str | None]:
        instructions = (
            "User request:\n"
            "Generate a concise, helpful final answer.\n"
            "For general requests, respond naturally without forcing implementation steps.\n"
            "For coding/technical requests, include concrete next implementation steps.\n"
            "If Tool outputs include web_fetch data, you MUST ground the answer in that data.\n"
            "When web_fetch data exists, do not claim browsing is unavailable and do not ignore fetched content.\n"
            "Include a short 'Sources used' section with source_url values found in tool outputs when available.\n"
            "Do not emit tool directives, no [TOOL_CALL] blocks, and no pseudo tool syntax.\n"
            "Only report completed actions and clear next steps."
        )
        sections = {
            "instructions": instructions,
            "user_request": payload.user_message,
            "plan": payload.plan_text,
            "tool_outputs": payload.tool_results or "(no tool outputs)",
            "relevant_memory": payload.reduced_context,
        }

        prompt_variant_id: str | None = None
        if self._ab_registry is not None and settings.prompt_ab_enabled:
            variant = self._ab_registry.select(
                group=f"synthesizer_{task_type}",
                session_id=session_id,
            )
            if variant is not None:
                prompt_variant_id = variant.variant_id
                sections["instructions"] = variant.prompt_text
                sections["prompt_variant"] = prompt_variant_id

        if task_type == "hard_research":
            sections["hard_contract"] = (
                "Mandatory output schema for this response (strict):\n"
                "1) Architektur-Risiken\n"
                "2) Performance-Hotspots\n"
                "3) Guardrail-Lücken\n"
                "4) Priorisierte Maßnahmen (Top 10)\n"
                "5) Messbare KPIs\n"
                "6) Rollout-Plan\n\n"
                "Additional hard constraints:\n"
                "- In 'Priorisierte Maßnahmen (Top 10)' include numbered items 1. to 10.\n"
                "- In 'Rollout-Plan' include exactly: Phase 1, Phase 2, Phase 3.\n"
                "- For rollout phases, use plain lines that start with exactly: 'Phase 1', 'Phase 2', 'Phase 3' (no markdown prefix like # or ###).\n"
                "- In 'Messbare KPIs' include at least two KPI lines with a number and unit (% or ms or s).\n"
                "- Each KPI line must contain both the word 'KPI' and its numeric target on the same line (e.g., 'KPI: latency <= 120 ms').\n"
                "- Keep output text-only; no tool calls, no pseudo code blocks."
            )
        else:
            sections["section_contract"] = self._build_section_contract_prompt(task_type).strip()

        kernel = self._kernel_builder.build(
            prompt_type="synthesis",
            prompt_mode=normalize_prompt_mode(payload.prompt_mode, default="full"),
            sections=sections,
        )
        return kernel.rendered, prompt_variant_id

    def _resolve_task_type(self, payload: SynthesizerInput) -> str:
        hinted = (payload.task_type or "").strip().lower()
        # Alle gültigen Hint-Typen werden direkt respektiert.
        # Neuer Typen orchestration_failed und orchestration_pending ergänzt,
        # damit agent.py sie als Hint übergeben kann und der Synthesizer
        # NICHT auf eigenes Keyword-Matching zurückfällt.
        if hinted in {
            "hard_research",
            "research",
            "orchestration",
            "orchestration_failed",
            "orchestration_pending",
            "implementation",
            "general",
        }:
            return hinted

        user_message = (payload.user_message or "").lower()
        tool_results = (payload.tool_results or "").lower()

        if self._requires_hard_research_structure(payload.user_message):
            return "hard_research"

        # Evidence-first: spawned_subrun_id= belegt ausgeführten spawn_subrun-Call.
        # Terminal-Reason entscheidet über die Unterart.
        if "spawned_subrun_id=" in tool_results:
            if "subrun-complete" in tool_results:
                return "orchestration"
            if any(s in tool_results for s in ("subrun-error", "subrun-timeout", "subrun-cancelled")):
                return "orchestration_failed"
            return "orchestration_pending"

        # Keyword-Scan nur als letzter Ausweg.
        if any(marker in user_message for marker in ("orchestrate", "delegate", "spawn subrun", "multi-agent")):
            return "orchestration"
        if "subrun_announce" in tool_results:
            return "orchestration"

        if any(
            marker in user_message
            for marker in (
                "implement",
                "fix",
                "refactor",
                "test",
                "code",
                "bug",
                "feature",
                "function",
                "class",
            )
        ):
            return "implementation"

        if any(
            marker in user_message
            for marker in ("search the web", "search on the web", "latest", "news", "find online")
        ):
            return "research"
        if "source_url" in tool_results or "[web_fetch]" in tool_results:
            return "research"

        return "general"

    def _build_section_contract_prompt(self, task_type: str) -> str:
        section_headers = self._required_sections_for_task(task_type)
        headers_text = "\n".join(f"- {header}" for header in section_headers)
        return (
            "\n\n"
            "Mandatory output schema for this response (section contract):\n"
            "Use exactly these section headers in this order:\n"
            f"{headers_text}\n"
            "Each section must contain at least one concise bullet item."
        )

    def _required_sections_for_task(self, task_type: str) -> tuple[str, ...]:
        contracts: dict[str, tuple[str, ...]] = {
            "hard_research": (
                "Architektur-Risiken",
                "Performance-Hotspots",
                "Guardrail-Lücken",
                "Priorisierte Maßnahmen (Top 10)",
                "Messbare KPIs",
                "Rollout-Plan",
            ),
            "research": (
                "Summary",
                "Findings",
                "Evidence",
                "Risks/Limitations",
                "Next steps",
                "Sources used",
            ),
            "orchestration": (
                "Goal",
                "Delegation outcome",
                "Child handover",
                "Parent decision",
                "Next steps",
            ),
            # Explizite Fehler-Sektion für fehlgeschlagene Delegation:
            # verhindert, dass der LLM eine Erfolgs-Narration generiert.
            "orchestration_failed": (
                "Goal",
                "Delegation failure",
                "Failure reason",
                "Recovery options",
                "Next steps",
            ),
            # Pending = fire-and-forget, kein Outcome bekannt:
            # transparente Kommunikation an den Nutzer.
            "orchestration_pending": (
                "Goal",
                "Delegation initiated",
                "Pending status",
                "What to expect",
                "Next steps",
            ),
            "implementation": (
                "Outcome",
                "What changed",
                "Validation",
                "Risks",
                "Next steps",
            ),
            # BUG-7: "general" carries no mandatory sections — free-form
            # conversational replies must not be forced into a rigid scaffold.
            # Leaving this empty also eliminates the repair LLM call (BUG-1
            # compound) for the most common task type.
            "general": (),
        }
        return contracts.get(task_type, contracts["general"])

    def _validate_hard_research_contract(self, final_text: str) -> list[str]:
        text = final_text or ""
        failures: list[str] = [
            f"missing_section:{header}"
            for header in (
                "Architektur-Risiken",
                "Performance-Hotspots",
                "Guardrail-Lücken",
                "Priorisierte Maßnahmen (Top 10)",
                "Messbare KPIs",
                "Rollout-Plan",
            )
            if header.lower() not in text.lower()
        ]
        if not all(f"{idx}." in text for idx in range(1, 11)):
            failures.append("missing_top10_numbering")
        failures.extend(
            f"missing_phase:{phase}" for phase in ("Phase 1", "Phase 2", "Phase 3") if phase.lower() not in text.lower()
        )
        phase_line_matches = len(re.findall(r"(?im)^\s*phase\s*[1-3]\b", text))
        if phase_line_matches < 3:
            failures.append("phase_line_format_invalid")
        kpi_line_matches = len(re.findall(r"(?i)kpi[^\n]{0,80}\b(\d+\s*%|\d+\s*ms|\d+\s*s)", text))
        if kpi_line_matches < 2:
            failures.append("kpi_line_format_invalid")
        return failures

    def _validate_semantic_truth(self, *, task_type: str, tool_results: str, final_text: str) -> list[str]:
        failures: list[str] = []
        normalized_results = (tool_results or "").lower()
        normalized_text = (final_text or "").lower()

        if task_type == "orchestration":
            has_spawn = "spawned_subrun_id=" in normalized_results
            has_completed = "subrun-complete" in normalized_results
            if has_spawn and not has_completed:
                failures.append("semantic_truth_missing:orchestration:no_completed_subrun_evidence")

        if task_type in {"orchestration_pending", "orchestration_failed"}:
            success_claim_markers = (
                "successfully delegated",
                "delegation successful",
                "delegation succeeded",
                "delegated successfully",
                "✅ successful",
            )
            if any(marker in normalized_text for marker in success_claim_markers):
                failures.append(f"semantic_truth_conflict:{task_type}:success_claim_without_success_evidence")

        return failures

    def _build_self_check_repair_prompt(
        self,
        *,
        task_type: str,
        required_sections: tuple[str, ...],
        failing_reasons: list[str],
        draft_text: str,
    ) -> str:
        failures_text = "\n".join(f"- {item}" for item in failing_reasons)
        section_text = "\n".join(f"- {item}" for item in required_sections)
        return (
            "Repair this draft so it satisfies the response contract.\n"
            "Keep the same language and preserve meaning.\n"
            "Output only the repaired final answer text.\n\n"
            f"Task type: {task_type}\n"
            "Required sections (in order):\n"
            f"{section_text}\n\n"
            "Validation failures:\n"
            f"{failures_text}\n\n"
            "Draft:\n"
            f"{draft_text}"
        )

    async def _run_synthesis_self_check(
        self,
        *,
        payload: SynthesizerInput,
        final_text: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None,
    ) -> str:
        if not (payload.task_type or "").strip():
            return final_text

        task_type = self._resolve_task_type(payload)
        required_sections = self._required_sections_for_task(task_type)

        await self._emit_lifecycle_fn(
            send_event,
            "synthesis_contract_check_started",
            request_id,
            session_id,
            {
                "task_type": task_type,
                "required_sections": list(required_sections),
            },
        )

        validation = self._reply_shaper.validate_section_contract(final_text, required_sections)
        failures = list(validation.failures)
        if task_type == "hard_research":
            failures.extend(self._validate_hard_research_contract(final_text))
        failures.extend(
            self._validate_semantic_truth(
                task_type=task_type,
                tool_results=payload.tool_results or "",
                final_text=final_text,
            )
        )

        if not failures:
            await self._emit_lifecycle_fn(
                send_event,
                "synthesis_contract_check_completed",
                request_id,
                session_id,
                {
                    "task_type": task_type,
                    "valid": True,
                    "correction_applied": False,
                },
            )
            return final_text

        repair_prompt = self._build_self_check_repair_prompt(
            task_type=task_type,
            required_sections=required_sections,
            failing_reasons=failures,
            draft_text=final_text,
        )
        repaired_text = await self.client.complete_chat(
            self.system_prompt,
            repair_prompt,
            model=model,
            temperature=0.1,
        )
        repaired_text = (repaired_text or "").strip()

        repaired_validation = self._reply_shaper.validate_section_contract(repaired_text, required_sections)
        repaired_failures = list(repaired_validation.failures)
        if task_type == "hard_research":
            repaired_failures.extend(self._validate_hard_research_contract(repaired_text))
        repaired_failures.extend(
            self._validate_semantic_truth(
                task_type=task_type,
                tool_results=payload.tool_results or "",
                final_text=repaired_text,
            )
        )

        resolved = not repaired_failures
        # Accept the repaired text if it fully resolves the contract OR if it
        # makes a measurable improvement (fewer failures than the original).
        # Previously the code discarded the repaired text on any remaining
        # failure, causing failure_count_before == failure_count_after == N even
        # after the LLM produced a better (but still imperfect) response.
        improved = len(repaired_failures) < len(failures)
        await self._emit_lifecycle_fn(
            send_event,
            "synthesis_contract_check_completed",
            request_id,
            session_id,
            {
                "task_type": task_type,
                "valid": resolved,
                "correction_applied": True,
                "failure_count_before": len(failures),
                "failure_count_after": len(repaired_failures),
            },
        )

        if repaired_text and (resolved or improved):
            return repaired_text
        return final_text

    async def execute(
        self,
        payload: SynthesizerInput,
        *,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None,
    ) -> SynthesizerOutput:
        task_type = self._resolve_task_type(payload)
        final_prompt, prompt_variant_id = self._build_final_prompt(
            payload,
            task_type=task_type,
            session_id=session_id,
        )
        self._last_prompt_variant_id = prompt_variant_id

        effective_system_prompt = self.system_prompt
        if payload.injection_suspect:
            from app.agents.planner_agent import _ANTI_INJECTION_DIRECTIVE
            effective_system_prompt = _ANTI_INJECTION_DIRECTIVE + "\n\n" + self.system_prompt

        effective_temperature = self.constraints.temperature
        if settings.dynamic_temperature_enabled and self._temperature_resolver is not None:
            effective_temperature = self._temperature_resolver.resolve(
                task_type=task_type,
                reasoning_level=getattr(payload, "reasoning_level", None),
            )

        await self._emit_lifecycle_fn(
            send_event,
            "streaming_started",
            request_id,
            session_id,
            None,
        )

        output_parts: list[str] = []
        effective_stream_timeout = self.stream_timeout_seconds

        async def _consume_stream() -> None:
            async for token in self.client.stream_chat_completion(
                effective_system_prompt,
                final_prompt,
                model=model,
                temperature=effective_temperature,
            ):
                output_parts.append(token)
                await send_event({"type": "token", "agent": self.agent_name, "token": token})

        try:
            await asyncio.wait_for(_consume_stream(), timeout=effective_stream_timeout)
        except TimeoutError as exc:
            partial_text = "".join(output_parts).strip()
            await self._emit_lifecycle_fn(
                send_event,
                "streaming_timeout",
                request_id,
                session_id,
                {
                    "timeout_seconds": effective_stream_timeout,
                    "partial_output_chars": len(partial_text),
                },
            )
            raise LlmClientError(f"Synthesizer streaming timeout after {effective_stream_timeout:.2f}s") from exc

        final_text = "".join(output_parts).strip()
        final_text = await self._run_synthesis_self_check(
            payload=payload,
            final_text=final_text,
            send_event=send_event,
            session_id=session_id,
            request_id=request_id,
            model=model,
        )
        await self._emit_lifecycle_fn(
            send_event,
            "streaming_completed",
            request_id,
            session_id,
            {"output_chars": len(final_text)},
        )

        return SynthesizerOutput(final_text=final_text)

    async def run(
        self,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None = None,
        tool_policy: ToolPolicyDict | None = None,
        prompt_mode: str | None = None,
    ) -> str:
        payload = SynthesizerInput.model_validate_json(user_message)
        if prompt_mode:
            payload = payload.model_copy(update={"prompt_mode": prompt_mode})
        result = await self.execute(
            payload,
            send_event=send_event,
            session_id=session_id,
            request_id=request_id,
            model=model,
        )
        return json.dumps(result.model_dump(), ensure_ascii=False)
