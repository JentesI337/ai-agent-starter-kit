from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.llm_client import LlmClient


@dataclass(frozen=True)
class ReflectionVerdict:
    score: float
    goal_alignment: float
    completeness: float
    factual_grounding: float
    issues: list[str]
    suggested_fix: str | None
    should_retry: bool


class ReflectionService:
    def __init__(self, client: LlmClient, threshold: float = 0.6):
        self.client = client
        self.threshold = max(0.0, min(1.0, float(threshold)))

    async def reflect(
        self,
        *,
        user_message: str,
        plan_text: str,
        tool_results: str,
        final_answer: str,
        model: str | None = None,
    ) -> ReflectionVerdict:
        reflection_prompt = self._build_reflection_prompt(
            user_message=user_message,
            plan_text=plan_text,
            tool_results=tool_results,
            final_answer=final_answer,
        )
        raw_verdict = await self.client.complete_chat(
            system_prompt="You are a quality assurance agent. Evaluate answers critically and objectively.",
            user_prompt=reflection_prompt,
            model=model,
            temperature=0.1,
        )
        return self._parse_verdict(raw_verdict)

    def _build_reflection_prompt(
        self,
        *,
        user_message: str,
        plan_text: str,
        tool_results: str,
        final_answer: str,
    ) -> str:
        return (
            "Evaluate this response. Return JSON with these fields:\n"
            '{"goal_alignment": 0.0-1.0, "completeness": 0.0-1.0, '
            '"factual_grounding": 0.0-1.0, "issues": ["..."], '
            '"suggested_fix": "..." or null}\n\n'
            f"User question: {user_message}\n"
            f"Plan: {plan_text[:500]}\n"
            f"Tool outputs: {tool_results[:1000]}\n"
            f"Final answer: {final_answer}"
        )

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

        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
        return None

    def _parse_verdict(self, raw: str) -> ReflectionVerdict:
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

        return ReflectionVerdict(
            score=score,
            goal_alignment=goal_alignment,
            completeness=completeness,
            factual_grounding=factual_grounding,
            issues=issues,
            suggested_fix=suggested_fix,
            should_retry=score < self.threshold,
        )
