from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

SCENARIO_FILE = Path(__file__).resolve().parents[1] / "benchmarks" / "scenarios" / "default.json"


def _hard_case_contract(case_id: str) -> dict:
    payload = json.loads(SCENARIO_FILE.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    for case in cases:
        if case.get("case_id") == case_id:
            return case
    raise AssertionError(f"Case '{case_id}' not found in benchmark scenario")


def _validate_contract(text: str, contract: dict) -> list[str]:
    final_text = text or ""

    failures = [
        f"missing_substring:{expected}"
        for expected in contract.get("required_substrings", [])
        if str(expected).lower() not in final_text.lower()
    ]

    failures.extend(
        f"missing_regex:{pattern}"
        for pattern in contract.get("required_regex_patterns", [])
        if re.search(str(pattern), final_text) is None
    )

    for pattern, min_count in dict(contract.get("regex_min_match_counts", {})).items():
        found = len(re.findall(str(pattern), final_text))
        if found < int(min_count):
            failures.append(f"regex_count_below:{pattern}:expected>={min_count}:got={found}")

    return failures


def _valid_hard_output_sample() -> str:
    return """
Architektur-Risiken
- Risk cluster A: orchestration coupling in hot paths.
- Risk cluster B: fallback branch ambiguity in retries.

Performance-Hotspots
- Token streaming overhead in long responses.
- Tool selection reparsing with repeated validation.

Guardrail-Lücken
- Partial policy mismatch between planner and tool selector.
- Sparse terminal reason taxonomy in some failure modes.

Priorisierte Maßnahmen (Top 10)
1. Normalize contract checks across planner and synthesizer.
2. Add deterministic fallback boundaries and strict cutoffs.
3. Harden schema validation before final emission.
4. Introduce explicit error-class decision matrix.
5. Add telemetry for recovered_successfully and terminal_reason.
6. Split hard benchmark scenarios by failure category.
7. Add p50/p95 latency and quality drift guardrails.
8. Add one-shot replan fallback for empty tool selection.
9. Improve policy diagnostics for unsupported/env-missing.
10. Add release gate with three-run stability requirement.

Messbare KPIs
- KPI: gated_hard_success_rate >= 70 %
- KPI: first_token_p95 <= 12000 ms
- KPI: recovery_success_share >= 60 %

Rollout-Plan
Phase 1
- Tests-first contracts and benchmark split rollout.
Phase 2
- Recovery matrix + bounded replan fallback.
Phase 3
- Telemetry hardening, runbooks, and CI quality gates.
""".strip()


def _invalid_hard_output_sample() -> str:
    return """
Kurze Analyse:
Wir sollten einige Verbesserungen machen.
1. Bessere Struktur
2. Mehr Tests
""".strip()


@pytest.mark.parametrize(
    ("case_id", "min_chars", "min_regex", "min_regex_counts"),
    [
        ("hard_reasoning_format", 1000, 6, 1),
        ("hard_reasoning_depth", 1200, 0, 2),
    ],
)
def test_hard_reasoning_contract_is_present_and_well_formed(
    case_id: str,
    min_chars: int,
    min_regex: int,
    min_regex_counts: int,
) -> None:
    contract = _hard_case_contract(case_id)

    assert contract["gate"] is True
    assert contract["min_final_chars"] >= min_chars
    required_patterns = contract.get("required_regex_patterns", []) or []
    assert isinstance(required_patterns, list)
    assert len(required_patterns) >= min_regex
    assert isinstance(contract.get("regex_min_match_counts"), dict)
    assert len(contract.get("regex_min_match_counts", {})) >= min_regex_counts


@pytest.mark.parametrize("case_id", ["hard_reasoning_format", "hard_reasoning_depth"])
def test_valid_hard_output_sample_satisfies_contract(case_id: str) -> None:
    contract = _hard_case_contract(case_id)
    failures = _validate_contract(_valid_hard_output_sample(), contract)

    assert failures == []


@pytest.mark.parametrize("case_id", ["hard_reasoning_format", "hard_reasoning_depth"])
def test_invalid_hard_output_sample_fails_contract(case_id: str) -> None:
    contract = _hard_case_contract(case_id)
    failures = _validate_contract(_invalid_hard_output_sample(), contract)

    assert failures
    assert any(reason.startswith(("missing_regex:", "regex_count_below:")) for reason in failures)
