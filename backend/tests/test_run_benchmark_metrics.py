from __future__ import annotations

from benchmarks.run_benchmark import BenchmarkRunResult, _build_latency_summary, _percentile


def _result(*, level: str, duration_ms: int, first_token_ms: int | None) -> BenchmarkRunResult:
    return BenchmarkRunResult(
        case_id=f"case-{level}",
        level=level,
        run_index=1,
        gate=True,
        passed=True,
        reason="ok",
        duration_ms=duration_ms,
        first_event_ms=5,
        first_token_ms=first_token_ms,
        final_received_ms=duration_ms,
        final_text_length=100,
        event_count=10,
        event_type_counts={"final": 1},
        lifecycle_stages=["request_completed"],
        errors=[],
        output_file="out.jsonl",
    )


def test_percentile_handles_empty_and_bounds() -> None:
    assert _percentile([], 50) is None
    assert _percentile([5, 10, 20], 0) == 5.0
    assert _percentile([5, 10, 20], 100) == 20.0


def test_percentile_interpolates_middle_values() -> None:
    values = [100, 200, 300, 400]

    assert _percentile(values, 50) == 250.0
    assert _percentile(values, 95) == 385.0


def test_build_latency_summary_groups_by_level_and_metric() -> None:
    results = [
        _result(level="easy", duration_ms=1000, first_token_ms=300),
        _result(level="easy", duration_ms=1100, first_token_ms=350),
        _result(level="hard", duration_ms=5000, first_token_ms=1200),
        _result(level="hard", duration_ms=7000, first_token_ms=None),
    ]

    summary = _build_latency_summary(results)

    assert summary["duration_ms"]["count"] == 4
    assert summary["first_token_ms"]["count"] == 3
    assert summary["by_level"]["easy"]["duration_ms"]["count"] == 2
    assert summary["by_level"]["hard"]["first_token_ms"]["count"] == 1
