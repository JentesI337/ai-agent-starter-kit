from __future__ import annotations

from dataclasses import dataclass

VALID_STEP_STATUSES: set[str] = {"pending", "running", "completed", "failed", "skipped"}
VALID_COMPLEXITIES: set[str] = {"trivial", "moderate", "complex"}


@dataclass
class PlanStep:
    step_id: str
    action: str
    tool: str | None
    depends_on: list[str]
    fallback: str | None
    status: str = "pending"
    result: str | None = None
    error: str | None = None


@dataclass
class PlanGraph:
    goal: str
    complexity: str
    steps: list[PlanStep]
    clarification_needed: str | None = None

    def ready_steps(self) -> list[PlanStep]:
        completed_ids = {step.step_id for step in self.steps if step.status == "completed"}
        return [
            step
            for step in self.steps
            if step.status == "pending" and all(dep in completed_ids for dep in step.depends_on)
        ]

    def is_complete(self) -> bool:
        return all(step.status in {"completed", "skipped"} for step in self.steps)

    def failed_steps(self) -> list[PlanStep]:
        return [step for step in self.steps if step.status == "failed"]

    @classmethod
    def from_dict(cls, payload: dict, *, max_steps: int = 7) -> PlanGraph:
        goal = str(payload.get("goal") or "Execution plan").strip() or "Execution plan"
        raw_complexity = str(payload.get("complexity") or "moderate").strip().lower()
        complexity = raw_complexity if raw_complexity in VALID_COMPLEXITIES else "moderate"

        raw_steps = payload.get("steps")
        parsed_steps: list[PlanStep] = []
        if isinstance(raw_steps, list):
            for index, item in enumerate(raw_steps[: max(1, int(max_steps))], start=1):
                if not isinstance(item, dict):
                    continue
                step_id = str(item.get("step_id") or f"s{index}").strip() or f"s{index}"
                action = str(item.get("action") or "").strip()
                if not action:
                    continue
                raw_tool = item.get("tool")
                tool = str(raw_tool).strip() if isinstance(raw_tool, str) and str(raw_tool).strip() else None
                raw_depends = item.get("depends_on")
                depends_on = [
                    str(dep).strip()
                    for dep in (raw_depends if isinstance(raw_depends, list) else [])
                    if str(dep).strip()
                ]
                fallback = item.get("fallback")
                normalized_fallback = (
                    str(fallback).strip()
                    if isinstance(fallback, str) and str(fallback).strip()
                    else None
                )
                raw_status = str(item.get("status") or "pending").strip().lower()
                status = raw_status if raw_status in VALID_STEP_STATUSES else "pending"
                parsed_steps.append(
                    PlanStep(
                        step_id=step_id,
                        action=action,
                        tool=tool,
                        depends_on=depends_on,
                        fallback=normalized_fallback,
                        status=status,
                    )
                )

        if not parsed_steps:
            parsed_steps = [
                PlanStep(
                    step_id="s1",
                    action="Provide direct answer",
                    tool=None,
                    depends_on=[],
                    fallback="Ask for clarification if request is ambiguous",
                )
            ]

        clarification_needed = payload.get("clarification_needed")
        normalized_clarification = (
            str(clarification_needed).strip()
            if isinstance(clarification_needed, str) and str(clarification_needed).strip()
            else None
        )

        graph = cls(
            goal=goal,
            complexity=complexity,
            steps=parsed_steps,
            clarification_needed=normalized_clarification,
        )
        graph._sanitize_dependencies()
        return graph

    def _sanitize_dependencies(self) -> None:
        known_ids = {step.step_id for step in self.steps}
        for step in self.steps:
            step.depends_on = [dep for dep in step.depends_on if dep in known_ids and dep != step.step_id]

    def to_mermaid(self) -> str:
        """Render this plan graph as a Mermaid flowchart string."""
        from app.services.visualization import plan_graph_to_mermaid

        return plan_graph_to_mermaid(self)

    def as_plan_text(self) -> str:
        lines = [f"Goal: {self.goal}", f"Complexity: {self.complexity}"]
        if self.clarification_needed:
            lines.append(f"Clarification needed: {self.clarification_needed}")
        lines.append("Steps:")
        for step in self.steps:
            tool_label = step.tool or "none"
            depends = ", ".join(step.depends_on) if step.depends_on else "none"
            line = f"- [{step.step_id}] action={step.action}; tool={tool_label}; depends_on={depends}"
            if step.fallback:
                line += f"; fallback={step.fallback}"
            lines.append(line)
        return "\n".join(lines)
