from __future__ import annotations

import argparse
import json
from pathlib import Path


def _normalize(path_value: str) -> str:
    return str(path_value or "").replace("\\", "/").strip().lower()


def _find_file_coverage(files_payload: dict[str, dict], module_path: str) -> float | None:
    wanted = _normalize(module_path)
    if not wanted:
        return None

    for key, value in files_payload.items():
        normalized_key = _normalize(key)
        if normalized_key == wanted or normalized_key.endswith(f"/{wanted}") or wanted.endswith(f"/{normalized_key}"):
            summary = value.get("summary") if isinstance(value, dict) else None
            if isinstance(summary, dict):
                percent = summary.get("percent_covered")
                if isinstance(percent, (int, float)):
                    return float(percent)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate coverage thresholds from coverage.json")
    parser.add_argument("--coverage-json", required=True, help="Path to coverage json report")
    parser.add_argument("--global-min", type=float, default=70.0, help="Minimum global coverage percent")
    parser.add_argument(
        "--module-min",
        action="append",
        default=[],
        metavar="PATH:PERCENT",
        help="Minimum coverage for a module path, e.g. backend/app/llm_client.py:60",
    )
    args = parser.parse_args()

    report_path = Path(args.coverage_json)
    if not report_path.exists():
        raise SystemExit(f"Coverage report not found: {report_path}")

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    totals = payload.get("totals") if isinstance(payload, dict) else None
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(totals, dict) or not isinstance(files, dict):
        raise SystemExit("Invalid coverage.json payload")

    total_percent = float(totals.get("percent_covered", 0.0) or 0.0)
    failures: list[str] = []

    if total_percent < float(args.global_min):
        failures.append(f"Global coverage {total_percent:.2f}% < required {float(args.global_min):.2f}%")

    for item in args.module_min:
        raw = str(item or "").strip()
        if not raw or ":" not in raw:
            failures.append(f"Invalid --module-min entry: {raw!r}")
            continue
        module_path, threshold_text = raw.rsplit(":", 1)
        module_path = module_path.strip()
        try:
            threshold = float(threshold_text.strip())
        except ValueError:
            failures.append(f"Invalid threshold in --module-min: {raw!r}")
            continue

        value = _find_file_coverage(files, module_path)
        if value is None:
            failures.append(f"Coverage data not found for module: {module_path}")
            continue
        if value < threshold:
            failures.append(f"{module_path} coverage {value:.2f}% < required {threshold:.2f}%")

    if failures:
        print("Coverage gate failed:")
        for item in failures:
            print(f"- {item}")
        return 1

    print("Coverage gate passed")
    print(f"- Global: {total_percent:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
