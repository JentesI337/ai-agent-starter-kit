from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GateThresholds:
    overall_success_rate_min: float
    replan_success_rate_min: float
    tool_loop_success_rate_min: float
    invalid_final_rate_max: float


def _resolve_default_suite_path() -> Path:
    return Path("backend/monitoring/eval_golden_suite.json")


def _resolve_thresholds() -> GateThresholds:
    return GateThresholds(
        overall_success_rate_min=float(os.getenv("EVAL_GATE_OVERALL_SUCCESS_RATE_MIN", "1.0")),
        replan_success_rate_min=float(os.getenv("EVAL_GATE_REPLAN_SUCCESS_RATE_MIN", "1.0")),
        tool_loop_success_rate_min=float(os.getenv("EVAL_GATE_TOOL_LOOP_SUCCESS_RATE_MIN", "1.0")),
        invalid_final_rate_max=float(os.getenv("EVAL_GATE_INVALID_FINAL_RATE_MAX", "0.0")),
    )


def _load_suite_manifest(path: Path) -> tuple[dict[str, list[str]], GateThresholds]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tests = payload.get("tests")
    if not isinstance(tests, dict):
        raise ValueError("eval suite manifest must include object field 'tests'")

    normalized_tests: dict[str, list[str]] = {}
    for category, entries in tests.items():
        if not isinstance(category, str) or not isinstance(entries, list):
            continue
        nodeids = [str(item).strip() for item in entries if str(item).strip()]
        if nodeids:
            normalized_tests[category.strip()] = nodeids

    if not normalized_tests:
        raise ValueError("eval suite manifest contains no tests")

    thresholds_from_manifest = payload.get("thresholds")
    if isinstance(thresholds_from_manifest, dict):
        thresholds = GateThresholds(
            overall_success_rate_min=float(
                thresholds_from_manifest.get(
                    "overall_success_rate_min",
                    os.getenv("EVAL_GATE_OVERALL_SUCCESS_RATE_MIN", "1.0"),
                )
            ),
            replan_success_rate_min=float(
                thresholds_from_manifest.get(
                    "replan_success_rate_min",
                    os.getenv("EVAL_GATE_REPLAN_SUCCESS_RATE_MIN", "1.0"),
                )
            ),
            tool_loop_success_rate_min=float(
                thresholds_from_manifest.get(
                    "tool_loop_success_rate_min",
                    os.getenv("EVAL_GATE_TOOL_LOOP_SUCCESS_RATE_MIN", "1.0"),
                )
            ),
            invalid_final_rate_max=float(
                thresholds_from_manifest.get(
                    "invalid_final_rate_max",
                    os.getenv("EVAL_GATE_INVALID_FINAL_RATE_MAX", "0.0"),
                )
            ),
        )
    else:
        thresholds = _resolve_thresholds()

    return normalized_tests, thresholds


def _build_nodeid_category_map(golden_tests: dict[str, list[str]]) -> dict[str, str]:
    index: dict[str, str] = {}
    for category, tests in golden_tests.items():
        for nodeid in tests:
            index[nodeid] = category
    return index


def _run_pytest(nodeids: list[str], junitxml: Path) -> int:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        *nodeids,
        "--junitxml",
        str(junitxml),
        "--maxfail=1",
        "-o",
        "faulthandler_timeout=20",
    ]
    completed = subprocess.run(command, check=False)
    return int(completed.returncode)


def _normalize_nodeid(file_attr: str, class_attr: str, name_attr: str) -> str:
    normalized_file = str(file_attr or "").replace("\\", "/").strip()
    if not normalized_file and class_attr:
        class_path = str(class_attr).replace(".", "/").strip()
        normalized_file = f"{class_path}.py"
    if normalized_file.startswith("./"):
        normalized_file = normalized_file[2:]
    if normalized_file and not normalized_file.startswith("backend/"):
        normalized_file = f"backend/{normalized_file}"
    return f"{normalized_file}::{name_attr}"


def _parse_junit_results(junitxml: Path, golden_tests: dict[str, list[str]]) -> dict[str, object]:
    tree = ET.parse(junitxml)
    root = tree.getroot()

    by_nodeid: dict[str, str] = {}
    for testcase in root.iter("testcase"):
        nodeid = _normalize_nodeid(
            testcase.attrib.get("file", ""),
            testcase.attrib.get("classname", ""),
            testcase.attrib.get("name", ""),
        )
        if testcase.find("failure") is not None or testcase.find("error") is not None:
            by_nodeid[nodeid] = "failed"
        elif testcase.find("skipped") is not None:
            by_nodeid[nodeid] = "skipped"
        else:
            by_nodeid[nodeid] = "passed"

    category_map = _build_nodeid_category_map(golden_tests)
    category_stats: dict[str, dict[str, int]] = {
        category: {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
        for category in golden_tests.keys()
    }

    for expected_nodeid, category in category_map.items():
        status = by_nodeid.get(expected_nodeid, "failed")
        stats = category_stats[category]
        stats["total"] += 1
        if status == "passed":
            stats["passed"] += 1
        elif status == "skipped":
            stats["skipped"] += 1
        else:
            stats["failed"] += 1

    total = sum(item["total"] for item in category_stats.values())
    passed = sum(item["passed"] for item in category_stats.values())
    failed = sum(item["failed"] for item in category_stats.values())
    skipped = sum(item["skipped"] for item in category_stats.values())

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "categories": category_stats,
    }


def _rate(passed: int, total: int) -> float:
    return float(passed) / float(total) if total > 0 else 0.0


def _evaluate_gates(results: dict[str, object], thresholds: GateThresholds) -> tuple[bool, dict[str, object]]:
    categories = results["categories"]

    overall_success_rate = _rate(int(results["passed"]), int(results["total"]))
    replan_success_rate = _rate(categories["replan"]["passed"], categories["replan"]["total"])
    tool_loop_success_rate = _rate(categories["tool_loop"]["passed"], categories["tool_loop"]["total"])
    invalid_final_success_rate = _rate(categories["invalid_final"]["passed"], categories["invalid_final"]["total"])
    invalid_final_rate = 1.0 - invalid_final_success_rate

    checks = {
        "overall_success_rate": {
            "value": overall_success_rate,
            "min_required": thresholds.overall_success_rate_min,
            "ok": overall_success_rate >= thresholds.overall_success_rate_min,
        },
        "replan_success_rate": {
            "value": replan_success_rate,
            "min_required": thresholds.replan_success_rate_min,
            "ok": replan_success_rate >= thresholds.replan_success_rate_min,
        },
        "tool_loop_success_rate": {
            "value": tool_loop_success_rate,
            "min_required": thresholds.tool_loop_success_rate_min,
            "ok": tool_loop_success_rate >= thresholds.tool_loop_success_rate_min,
        },
        "invalid_final_rate": {
            "value": invalid_final_rate,
            "max_allowed": thresholds.invalid_final_rate_max,
            "ok": invalid_final_rate <= thresholds.invalid_final_rate_max,
        },
    }

    gate_ok = all(bool(item.get("ok")) for item in checks.values())
    return gate_ok, checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Run backend golden eval gates.")
    parser.add_argument(
        "--suite-path",
        default=str(_resolve_default_suite_path()),
        help="Path to eval golden suite manifest JSON.",
    )
    parser.add_argument(
        "--report-json",
        default="backend/monitoring/eval_gate_report.json",
        help="Path to write JSON report.",
    )
    args = parser.parse_args()

    suite_path = Path(args.suite_path)
    if not suite_path.exists():
        print(f"eval_gates_failed: suite manifest not found at {suite_path}", file=sys.stderr)
        return 2

    try:
        golden_tests, thresholds = _load_suite_manifest(suite_path)
    except Exception as exc:
        print(f"eval_gates_failed: invalid suite manifest: {exc}", file=sys.stderr)
        return 2

    nodeids = [nodeid for group in golden_tests.values() for nodeid in group]

    with tempfile.TemporaryDirectory(prefix="eval-gates-") as temp_dir:
        junitxml = Path(temp_dir) / "eval_gates.junit.xml"
        pytest_exit = _run_pytest(nodeids=nodeids, junitxml=junitxml)

        if not junitxml.exists():
            print("eval_gates_failed: junit xml not produced", file=sys.stderr)
            return 2

        results = _parse_junit_results(junitxml, golden_tests)
        gate_ok, checks = _evaluate_gates(results=results, thresholds=thresholds)

    report = {
        "schema": "eval.gates.v1",
        "suite_path": str(suite_path).replace("\\", "/"),
        "pytest_exit_code": pytest_exit,
        "golden_tests": golden_tests,
        "summary": results,
        "checks": checks,
        "gate_passed": gate_ok and pytest_exit == 0,
    }

    report_path = Path(args.report_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))

    if not report["gate_passed"]:
        print("eval_gates_failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
