from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.llm.client import LlmClient

# T1.4: Task-type-sensitiver Reflection-Threshold
# hard_research erfordert höhere Qualität als triviale Antworten.
# Werte überschreiben den globalen settings.reflection_threshold wenn task_type übergeben wird.
_REFLECTION_THRESHOLDS_BY_TASK_TYPE: dict[str, float] = {
    "hard_research": 0.75,
    "research": 0.70,
    "implementation": 0.65,
    "orchestration": 0.60,
    "orchestration_failed": 0.55,
    "orchestration_pending": 0.55,
    # BUG-2: Lowered from 0.55 — prose answers without tool grounding cannot
    # score higher than ~0.4 on factual_grounding; the old threshold always
    # triggered a retry, adding ~25 s and a second BUG-1 repair call.
    "general": 0.35,
    "trivial": 0.40,
}

_REFLECTION_SYSTEM_PROMPT = (
    "You are a quality assurance agent. Evaluate answers critically and objectively.\n\n"
    "## CRITICAL: Factual Grounding Scoring\n"
    "Score factual_grounding BELOW 0.4 if ANY of the following is true:\n"
    "  - The answer references a PID, port, IP, hostname, filename, line count,\n"
    "    file size, or timestamp that does NOT appear verbatim in the tool outputs\n"
    "  - The answer extrapolates, estimates, or derives numerical values not\n"
    "    explicitly present in the provided tool output\n"
    "  - The answer states facts about system state (processes, network, files)\n"
    "    that cannot be verified from the tool outputs above\n\n"
    "Score factual_grounding 0.0-0.2 if invented/hallucinated values are present.\n"
    "Score factual_grounding 0.8-1.0 ONLY if every factual claim maps verbatim to\n"
    "the provided tool output.\n\n"
    "## Completeness\n"
    "Score completeness based on whether all parts of the user's question are addressed.\n\n"
    "## Goal Alignment\n"
    "Score goal_alignment based on whether the answer solves the user's actual intent,\n"
    "not just the literal question."
)


@dataclass(frozen=True)
class ReflectionVerdict:
    score: float
    goal_alignment: float
    completeness: float
    factual_grounding: float
    issues: list[str]
    suggested_fix: str | None
    should_retry: bool
    hard_factual_fail: bool = False


class ReflectionService:
    def __init__(
        self,
        client: LlmClient,
        threshold: float = 0.6,
        factual_grounding_hard_min: float = 0.4,
        tool_results_max_chars: int = 8000,
        plan_max_chars: int = 2000,
    ):
        self.client = client
        self.threshold = max(0.0, min(1.0, float(threshold)))
        self.factual_grounding_hard_min = max(0.0, min(1.0, float(factual_grounding_hard_min)))
        self.tool_results_max_chars = max(500, int(tool_results_max_chars))
        self.plan_max_chars = max(200, int(plan_max_chars))

    async def reflect(
        self,
        *,
        user_message: str,
        plan_text: str,
        tool_results: str,
        final_answer: str,
        model: str | None = None,
        task_type: str | None = None,
    ) -> ReflectionVerdict:
        # T1.4: Task-type-sensitiver Threshold — überschreibt globalen settings-Threshold
        effective_threshold = _REFLECTION_THRESHOLDS_BY_TASK_TYPE.get((task_type or "").strip().lower(), self.threshold)
        reflection_prompt = self._build_reflection_prompt(
            user_message=user_message,
            plan_text=plan_text,
            tool_results=tool_results,
            final_answer=final_answer,
        )
        raw_verdict = await self.client.complete_chat(
            system_prompt=_REFLECTION_SYSTEM_PROMPT,
            user_prompt=reflection_prompt,
            model=model,
            temperature=0.1,
        )
        return self._parse_verdict(raw_verdict, threshold=effective_threshold)

    @staticmethod
    def _sanitize_for_prompt(text: str, max_chars: int) -> str:
        sanitized = (text or "")[:max_chars]
        sanitized = sanitized.replace("```", "` ` `")
        return re.sub(
            r"(?i)(return\s+json|you\s+must|ignore\s+previous|disregard|override|system\s*:)",
            r"[\1]",
            sanitized,
        )

    def _build_reflection_prompt(
        self,
        *,
        user_message: str,
        plan_text: str,
        tool_results: str,
        final_answer: str,
    ) -> str:
        safe_tool_results = self._sanitize_for_prompt(tool_results, self.tool_results_max_chars)
        safe_plan = self._sanitize_for_prompt(plan_text, self.plan_max_chars)
        parts = [
            "Evaluate this response. Return JSON with these fields:\n"
            '{"goal_alignment": 0.0-1.0, "completeness": 0.0-1.0, '
            '"factual_grounding": 0.0-1.0, "issues": ["..."], '
            '"suggested_fix": "..." or null}\n\n'
            f"User question: {user_message}",
        ]
        if safe_plan:
            parts.append(f"Plan: {safe_plan}")
        parts.append(f"Tool outputs: {safe_tool_results}")
        parts.append(f"Final answer: {final_answer}")
        return "\n".join(parts)

    @staticmethod
    def _clamp_score(value: object) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, numeric))

    @staticmethod
    def _extract_json_payload(raw: str) -> dict[str, object] | None:
        cleaned = (raw or "").strip()
        if not cleaned:
            return None
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{[\s\S]*?\}", cleaned)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
        return None

    def _parse_verdict(self, raw: str, threshold: float | None = None) -> ReflectionVerdict:
        effective_threshold = threshold if threshold is not None else self.threshold
        payload = self._extract_json_payload(raw)
        if payload is None:
            fallback_issues = ["Unable to parse reflection verdict from model output."]
            return ReflectionVerdict(
                score=0.0,
                goal_alignment=0.0,
                completeness=0.0,
                factual_grounding=0.0,
                issues=fallback_issues,
                suggested_fix=None,
                should_retry=True,
                hard_factual_fail=True,
            )

        goal_alignment = self._clamp_score(payload.get("goal_alignment"))
        completeness = self._clamp_score(payload.get("completeness"))
        factual_grounding = self._clamp_score(payload.get("factual_grounding"))
        score = (goal_alignment + completeness + factual_grounding) / 3

        raw_issues = payload.get("issues")
        if isinstance(raw_issues, list):
            issues = [str(item).strip() for item in raw_issues if str(item).strip()]
        elif isinstance(raw_issues, str) and raw_issues.strip():
            issues = [raw_issues.strip()]
        else:
            issues = []

        raw_suggested_fix = payload.get("suggested_fix")
        suggested_fix = str(raw_suggested_fix).strip() if isinstance(raw_suggested_fix, str) else None
        if suggested_fix == "":
            suggested_fix = None

        hard_factual_fail = factual_grounding < self.factual_grounding_hard_min
        return ReflectionVerdict(
            score=score,
            goal_alignment=goal_alignment,
            completeness=completeness,
            factual_grounding=factual_grounding,
            issues=issues,
            suggested_fix=suggested_fix,
            should_retry=(score < effective_threshold) or hard_factual_fail,
            hard_factual_fail=hard_factual_fail,
        )
