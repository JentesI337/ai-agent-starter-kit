from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sys
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import websockets


@dataclass(slots=True)
class BenchmarkCase:
    case_id: str
    level: str
    description: str
    prompt: str
    agent_id: str = "head-agent"
    preset: str | None = None
    model: str | None = None
    tool_policy: dict[str, Any] | None = None
    timeout_ms: int = 120_000
    min_final_chars: int = 2
    min_event_count: int = 3
    required_event_types: list[str] = field(default_factory=list)
    required_event_statuses: dict[str, list[str]] = field(default_factory=dict)
    required_event_field_equals: dict[str, dict[str, str]] = field(default_factory=dict)
    required_substrings: list[str] = field(default_factory=list)
    required_regex_patterns: list[str] = field(default_factory=list)
    regex_min_match_counts: dict[str, int] = field(default_factory=dict)
    required_lifecycle_stages: list[str] = field(default_factory=lambda: ["request_received", "request_completed"])
    completion_stages: list[str] = field(default_factory=lambda: ["request_completed"])
    allow_errors: bool = False
    gate: bool = True


@dataclass(slots=True)
class BenchmarkRunResult:
    case_id: str
    level: str
    run_index: int
    gate: bool
    passed: bool
    reason: str
    duration_ms: int
    first_event_ms: int | None
    first_token_ms: int | None
    final_received_ms: int | None
    final_text_length: int
    event_count: int
    event_type_counts: dict[str, int]
    lifecycle_stages: list[str]
    errors: list[str]
    output_file: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_cases_from_json(path: Path) -> list[BenchmarkCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError(f"Scenario file {path} has no non-empty 'cases' list.")

    cases: list[BenchmarkCase] = []
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise ValueError("Each case must be an object.")
        cases.append(
            BenchmarkCase(
                case_id=str(raw["case_id"]),
                level=str(raw["level"]),
                description=str(raw["description"]),
                prompt=str(raw["prompt"]),
                agent_id=str(raw.get("agent_id", "head-agent")),
                preset=raw.get("preset"),
                model=raw.get("model"),
                tool_policy=raw.get("tool_policy"),
                timeout_ms=int(raw.get("timeout_ms", 120_000)),
                min_final_chars=int(raw.get("min_final_chars", 2)),
                min_event_count=int(raw.get("min_event_count", 3)),
                required_event_types=[str(item) for item in raw.get("required_event_types", [])],
                required_event_statuses={
                    str(event_type): [str(status) for status in statuses]
                    for event_type, statuses in dict(raw.get("required_event_statuses", {})).items()
                },
                required_event_field_equals={
                    str(event_type): {str(field_name): str(field_value) for field_name, field_value in dict(required).items()}
                    for event_type, required in dict(raw.get("required_event_field_equals", {})).items()
                },
                required_substrings=[str(item) for item in raw.get("required_substrings", [])],
                required_regex_patterns=[str(item) for item in raw.get("required_regex_patterns", [])],
                regex_min_match_counts={
                    str(pattern): int(min_count)
                    for pattern, min_count in dict(raw.get("regex_min_match_counts", {})).items()
                },
                required_lifecycle_stages=[
                    str(item) for item in raw.get("required_lifecycle_stages", ["request_received", "request_completed"])
                ],
                completion_stages=[str(item) for item in raw.get("completion_stages", ["request_completed"])],
                allow_errors=bool(raw.get("allow_errors", False)),
                gate=bool(raw.get("gate", True)),
            )
        )

    for case in cases:
        for pattern in case.required_regex_patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"Invalid regex in required_regex_patterns for case '{case.case_id}': {pattern} ({exc})") from exc
        for pattern in case.regex_min_match_counts:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"Invalid regex in regex_min_match_counts for case '{case.case_id}': {pattern} ({exc})") from exc

    return cases


async def _wait_for_backend(base_url: str, timeout_ms: int) -> None:
    deadline = time.perf_counter() + (timeout_ms / 1000)
    status_url = f"{base_url.rstrip('/')}/api/runtime/status"

    while time.perf_counter() < deadline:
        try:
            async with httpx.AsyncClient(timeout=4) as client:
                response = await client.get(status_url)
            if response.status_code == 200:
                return
        except Exception:
            pass
        await asyncio.sleep(0.5)

    raise RuntimeError(f"Backend not reachable within {timeout_ms} ms at {status_url}")


def _safe_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)


async def _run_single_case(
    case: BenchmarkCase,
    run_index: int,
    ws_url: str,
    model_override: str | None,
    out_dir: Path,
) -> BenchmarkRunResult:
    case_label = f"{case.case_id}__run{run_index:02d}"
    event_file = out_dir / f"{_safe_filename(case_label)}.events.jsonl"
    started = time.perf_counter()

    event_type_counts: Counter[str] = Counter()
    event_statuses: dict[str, set[str]] = {}
    event_samples: dict[str, list[dict[str, Any]]] = {}
    lifecycle_stages: list[str] = []
    errors: list[str] = []

    event_count = 0
    first_event_ms: int | None = None
    first_token_ms: int | None = None
    final_received_ms: int | None = None
    final_text = ""
    completed = False
    completion_stages = {item.strip() for item in case.completion_stages if str(item).strip()}

    message_payload: dict[str, Any] = {
        "type": "user_message",
        "content": case.prompt,
        "agent_id": case.agent_id,
    }
    if case.preset:
        message_payload["preset"] = case.preset
    if case.tool_policy:
        message_payload["tool_policy"] = case.tool_policy

    effective_model = model_override or case.model
    if effective_model:
        message_payload["model"] = effective_model

    timeout_seconds = max(1.0, case.timeout_ms / 1000)

    try:
        async with websockets.connect(ws_url, max_size=2**24) as ws:
            await asyncio.wait_for(ws.recv(), timeout=8)
            await ws.send(json.dumps(message_payload, ensure_ascii=False))

            with event_file.open("w", encoding="utf-8") as handle:
                while True:
                    elapsed = time.perf_counter() - started
                    remaining = timeout_seconds - elapsed
                    if remaining <= 0:
                        break

                    raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                    now_ms = int((time.perf_counter() - started) * 1000)

                    envelope: dict[str, Any]
                    try:
                        envelope = json.loads(raw)
                    except json.JSONDecodeError:
                        handle.write(json.dumps({"t_ms": now_ms, "raw": raw}) + "\n")
                        continue

                    event = envelope.get("event") if isinstance(envelope, dict) else None
                    if not isinstance(event, dict):
                        handle.write(json.dumps({"t_ms": now_ms, "event": event}, ensure_ascii=False) + "\n")
                        continue

                    event_count += 1
                    event_type = str(event.get("type", "unknown"))
                    event_type_counts[event_type] += 1
                    event_samples.setdefault(event_type, []).append(event)
                    status_value = str(event.get("status", "")).strip()
                    if status_value:
                        event_statuses.setdefault(event_type, set()).add(status_value)

                    if first_event_ms is None:
                        first_event_ms = now_ms

                    if event_type == "token" and first_token_ms is None:
                        first_token_ms = now_ms

                    if event_type == "error":
                        errors.append(str(event.get("message", "")))

                    if event_type == "lifecycle":
                        stage = str(event.get("stage", "")).strip()
                        if stage:
                            lifecycle_stages.append(stage)
                        if stage in completion_stages:
                            completed = True

                    if event_type == "final" and final_received_ms is None:
                        final_received_ms = now_ms
                        final_text = str(event.get("message", ""))

                    handle.write(
                        json.dumps(
                            {
                                "t_ms": now_ms,
                                "seq": envelope.get("seq") if isinstance(envelope, dict) else None,
                                "event": event,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )

                    if completed:
                        break

    except TimeoutError:
        errors.append("timeout_while_waiting_for_events")
    except Exception as exc:
        errors.append(f"exception:{type(exc).__name__}:{exc}")

    duration_ms = int((time.perf_counter() - started) * 1000)

    checks: list[tuple[bool, str]] = [
        (completed, f"missing_completion_stage:{'|'.join(sorted(completion_stages))}"),
        (event_count >= case.min_event_count, f"event_count_below_{case.min_event_count}"),
        (len(final_text.strip()) >= case.min_final_chars, f"final_too_short_lt_{case.min_final_chars}"),
    ]

    for expected in case.required_substrings:
        checks.append((expected.lower() in final_text.lower(), f"missing_substring:{expected}"))

    for pattern in case.required_regex_patterns:
        checks.append((re.search(pattern, final_text) is not None, f"missing_regex:{pattern}"))

    for pattern, min_count in case.regex_min_match_counts.items():
        match_count = len(re.findall(pattern, final_text))
        checks.append((match_count >= min_count, f"regex_count_below:{pattern}:expected>={min_count}:got={match_count}"))

    for event_type in case.required_event_types:
        checks.append((event_type in event_type_counts, f"missing_event_type:{event_type}"))

    for event_type, required_statuses in case.required_event_statuses.items():
        seen_statuses = event_statuses.get(event_type, set())
        for required_status in required_statuses:
            checks.append(
                (
                    required_status in seen_statuses,
                    f"missing_event_status:{event_type}:{required_status}",
                )
            )

    for event_type, required_fields in case.required_event_field_equals.items():
        samples = event_samples.get(event_type, [])
        matched = any(
            all(str(sample.get(field_name)) == str(field_value) for field_name, field_value in required_fields.items())
            for sample in samples
        )
        checks.append((matched, f"missing_event_fields:{event_type}:{required_fields}"))

    for stage in case.required_lifecycle_stages:
        checks.append((stage in lifecycle_stages, f"missing_lifecycle:{stage}"))

    if errors and not case.allow_errors:
        checks.append((False, "error_event_or_exception"))

    failed_reasons = [reason for ok, reason in checks if not ok]
    passed = not failed_reasons
    reason = "ok" if passed else ";".join(failed_reasons)

    return BenchmarkRunResult(
        case_id=case.case_id,
        level=case.level,
        run_index=run_index,
        gate=case.gate,
        passed=passed,
        reason=reason,
        duration_ms=duration_ms,
        first_event_ms=first_event_ms,
        first_token_ms=first_token_ms,
        final_received_ms=final_received_ms,
        final_text_length=len(final_text),
        event_count=event_count,
        event_type_counts=dict(event_type_counts),
        lifecycle_stages=lifecycle_stages,
        errors=errors,
        output_file=str(event_file),
    )


def _group_by_level(results: list[BenchmarkRunResult]) -> dict[str, dict[str, int]]:
    grouped: dict[str, dict[str, int]] = {}
    for result in results:
        bucket = grouped.setdefault(result.level, {"total": 0, "passed": 0, "gated_total": 0, "gated_passed": 0})
        bucket["total"] += 1
        if result.passed:
            bucket["passed"] += 1
        if result.gate:
            bucket["gated_total"] += 1
            if result.passed:
                bucket["gated_passed"] += 1
    return grouped


def _percentile(values: list[int], percentile: int) -> float | None:
    if not values:
        return None
    if percentile <= 0:
        return float(min(values))
    if percentile >= 100:
        return float(max(values))

    ordered = sorted(values)
    rank = (len(ordered) - 1) * (percentile / 100)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(ordered[low])
    fraction = rank - low
    return float(ordered[low] + (ordered[high] - ordered[low]) * fraction)


def _summarize_latency(values: list[int]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "p50": _percentile(values, 50),
        "p95": _percentile(values, 95),
    }


def _build_latency_summary(results: list[BenchmarkRunResult]) -> dict[str, Any]:
    duration_all = [item.duration_ms for item in results]
    first_token_all = [item.first_token_ms for item in results if item.first_token_ms is not None]

    by_level: dict[str, dict[str, dict[str, float | int | None]]] = {}
    for level in sorted({item.level for item in results}):
        level_results = [item for item in results if item.level == level]
        level_duration = [item.duration_ms for item in level_results]
        level_first_token = [item.first_token_ms for item in level_results if item.first_token_ms is not None]
        by_level[level] = {
            "duration_ms": _summarize_latency(level_duration),
            "first_token_ms": _summarize_latency(level_first_token),
        }

    return {
        "duration_ms": _summarize_latency(duration_all),
        "first_token_ms": _summarize_latency(first_token_all),
        "by_level": by_level,
    }


def _render_summary_md(summary: dict[str, Any], results: list[BenchmarkRunResult]) -> str:
    latency = summary.get("latency_ms", {})
    duration_latency = latency.get("duration_ms", {}) if isinstance(latency, dict) else {}
    first_token_latency = latency.get("first_token_ms", {}) if isinstance(latency, dict) else {}
    lines = [
        "# Benchmark Summary",
        "",
        f"- started_at: {summary['started_at']}",
        f"- finished_at: {summary['finished_at']}",
        f"- total_runs: {summary['total_runs']}",
        f"- passed_runs: {summary['passed_runs']}",
        f"- failed_runs: {summary['failed_runs']}",
        f"- success_rate: {summary['success_rate_percent']:.1f}%",
        f"- gated_total_runs: {summary['gated_total_runs']}",
        f"- gated_passed_runs: {summary['gated_passed_runs']}",
        f"- gated_failed_runs: {summary['gated_failed_runs']}",
        f"- gated_success_rate: {summary['gated_success_rate_percent']:.1f}%",
        f"- duration_ms p50/p95: {duration_latency.get('p50')} / {duration_latency.get('p95')}",
        f"- first_token_ms p50/p95: {first_token_latency.get('p50')} / {first_token_latency.get('p95')}",
        "",
        "## Level Overview",
        "",
    ]

    for level, data in summary["by_level"].items():
        total = data["total"]
        passed = data["passed"]
        pct = (passed / total * 100) if total else 0
        gated_total = data.get("gated_total", 0)
        gated_passed = data.get("gated_passed", 0)
        gated_pct = (gated_passed / gated_total * 100) if gated_total else 0
        lines.append(
            f"- {level}: overall {passed}/{total} ({pct:.1f}%), gated {gated_passed}/{gated_total} ({gated_pct:.1f}%)"
        )

    by_level_latency = latency.get("by_level", {}) if isinstance(latency, dict) else {}
    if isinstance(by_level_latency, dict) and by_level_latency:
        lines += [
            "",
            "## Latency Overview",
            "",
        ]
        for level, metrics in by_level_latency.items():
            if not isinstance(metrics, dict):
                continue
            duration = metrics.get("duration_ms", {})
            first_token = metrics.get("first_token_ms", {})
            lines.append(
                f"- {level}: duration p50/p95={duration.get('p50')}/{duration.get('p95')}, "
                f"first_token p50/p95={first_token.get('p50')}/{first_token.get('p95')}"
            )

    lines += [
        "",
        "## Run Details",
        "",
        "| Case | Level | Run | Gate | Pass | Duration ms | Events | Final chars | Reason |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]

    for result in results:
        lines.append(
            f"| {result.case_id} | {result.level} | {result.run_index} | {'gate' if result.gate else 'diag'} | {'✅' if result.passed else '❌'} | "
            f"{result.duration_ms} | {result.event_count} | {result.final_text_length} | {result.reason} |"
        )

    return "\n".join(lines) + "\n"


async def _run(args: argparse.Namespace) -> int:
    script_dir = Path(__file__).resolve().parent
    default_scenario = script_dir / "scenarios" / "default.json"
    scenario_path = Path(args.scenario_file).resolve() if args.scenario_file else default_scenario

    cases = _load_cases_from_json(scenario_path)

    selected_levels = {item.strip().lower() for item in args.levels.split(",") if item.strip()}
    if selected_levels:
        cases = [item for item in cases if item.level.lower() in selected_levels]

    if not cases:
        print("No benchmark cases selected.", file=sys.stderr)
        return 2

    ws_url = args.ws_url or args.base_url.rstrip("/").replace("http://", "ws://").replace("https://", "wss://") + "/ws/agent"

    run_tag = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{uuid.uuid4().hex[:8]}"
    output_root = Path(args.output_dir).resolve() / run_tag
    output_root.mkdir(parents=True, exist_ok=True)

    await _wait_for_backend(args.base_url, timeout_ms=args.backend_wait_timeout_ms)

    started_at = _now_iso()
    results: list[BenchmarkRunResult] = []

    for case in cases:
        for run_index in range(1, args.runs_per_case + 1):
            print(f"[bench] running case={case.case_id} level={case.level} run={run_index}")
            result = await _run_single_case(
                case=case,
                run_index=run_index,
                ws_url=ws_url,
                model_override=args.model,
                out_dir=output_root,
            )
            results.append(result)
            status = "PASS" if result.passed else "FAIL"
            print(
                f"[bench] {status} case={result.case_id} run={result.run_index} "
                f"duration_ms={result.duration_ms} events={result.event_count} reason={result.reason}"
            )

    passed_runs = sum(1 for item in results if item.passed)
    total_runs = len(results)
    failed_runs = total_runs - passed_runs
    gated_total_runs = sum(1 for item in results if item.gate)
    gated_passed_runs = sum(1 for item in results if item.gate and item.passed)
    gated_failed_runs = gated_total_runs - gated_passed_runs

    summary: dict[str, Any] = {
        "started_at": started_at,
        "finished_at": _now_iso(),
        "scenario_file": str(scenario_path),
        "ws_url": ws_url,
        "base_url": args.base_url,
        "model_override": args.model,
        "runs_per_case": args.runs_per_case,
        "total_runs": total_runs,
        "passed_runs": passed_runs,
        "failed_runs": failed_runs,
        "success_rate_percent": (passed_runs / total_runs * 100) if total_runs else 0.0,
        "gated_total_runs": gated_total_runs,
        "gated_passed_runs": gated_passed_runs,
        "gated_failed_runs": gated_failed_runs,
        "gated_success_rate_percent": (gated_passed_runs / gated_total_runs * 100) if gated_total_runs else 0.0,
        "by_level": _group_by_level(results),
        "latency_ms": _build_latency_summary(results),
    }

    results_json = {
        "summary": summary,
        "results": [
            {
                "case_id": item.case_id,
                "level": item.level,
                "run_index": item.run_index,
                "gate": item.gate,
                "passed": item.passed,
                "reason": item.reason,
                "duration_ms": item.duration_ms,
                "first_event_ms": item.first_event_ms,
                "first_token_ms": item.first_token_ms,
                "final_received_ms": item.final_received_ms,
                "final_text_length": item.final_text_length,
                "event_count": item.event_count,
                "event_type_counts": item.event_type_counts,
                "lifecycle_stages": item.lifecycle_stages,
                "errors": item.errors,
                "output_file": item.output_file,
            }
            for item in results
        ],
    }

    (output_root / "results.json").write_text(json.dumps(results_json, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_root / "summary.md").write_text(_render_summary_md(summary, results), encoding="utf-8")

    print(f"[bench] results written to: {output_root}")
    print(
        f"[bench] pass-rate overall: {summary['passed_runs']}/{summary['total_runs']} "
        f"({summary['success_rate_percent']:.1f}%), gated: {summary['gated_passed_runs']}/{summary['gated_total_runs']} "
        f"({summary['gated_success_rate_percent']:.1f}%)"
    )

    if args.fail_on_error and gated_failed_runs > 0:
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scenario-based WebSocket benchmark for backend agent runtime.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL.")
    parser.add_argument("--ws-url", default=None, help="Explicit WebSocket URL. Default derives from --base-url.")
    parser.add_argument("--scenario-file", default=None, help="Path to benchmark scenario JSON.")
    parser.add_argument("--levels", default="easy,mid,hard", help="Comma-separated levels to run.")
    parser.add_argument("--runs-per-case", type=int, default=3, help="Number of runs per benchmark case.")
    parser.add_argument("--model", default=None, help="Override model for all benchmark cases.")
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parents[1] / "monitoring" / "benchmarks"),
        help="Output directory for benchmark artifacts.",
    )
    parser.add_argument("--backend-wait-timeout-ms", type=int, default=20_000, help="Wait timeout for backend health.")
    parser.add_argument("--fail-on-error", action="store_true", default=True, help="Exit with code 1 if any run fails.")
    parser.add_argument("--no-fail-on-error", action="store_false", dest="fail_on_error", help="Always exit 0.")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
