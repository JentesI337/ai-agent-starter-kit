"""Output format dataclasses for validation skill results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckResult:
    """Result of executing a single validation check."""

    check_id: str
    title: str
    severity: str
    status: str  # "pass", "fail", "warning", "not_applicable"
    evidence: str
    recommendation: str = ""


@dataclass(frozen=True)
class ValidationReport:
    """Aggregated report from executing all checks in a validation skill."""

    skill_name: str
    checks: tuple[CheckResult, ...]
    summary: str

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == "pass")

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail")

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c.status == "warning")
