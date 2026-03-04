# Benchmark Summary

- started_at: 2026-03-04T09:30:24.510659+00:00
- finished_at: 2026-03-04T09:32:24.534660+00:00
- total_runs: 1
- passed_runs: 0
- failed_runs: 1
- success_rate: 0.0%
- gated_total_runs: 0
- gated_passed_runs: 0
- gated_failed_runs: 0
- gated_success_rate: 0.0%
- duration_ms p50/p95: 120015.0 / 120015.0
- first_token_ms p50/p95: None / None

## Level Overview

- mid: overall 0/1 (0.0%), gated 0/0 (0.0%)

## Latency Overview

- mid: duration p50/p95=120015.0/120015.0, first_token p50/p95=None/None

## Run Details

| Case | Level | Run | Gate | Pass | Duration ms | Events | Final chars | Reason |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| mid_code_execute_diagnostic | mid | 1 | diag | ❌ | 120015 | 24 | 0 | missing_completion_stage:request_completed;final_too_short_lt_30;missing_substring:Ergebnis:;missing_substring:4;missing_substring:Sicherheit:;missing_regex:(?im)^\s*ergebnis:.*\b4\b;missing_regex:(?im)^\s*sicherheit:.*(sandbox|isoliert);missing_lifecycle:tool_started;missing_lifecycle:tool_completed;missing_lifecycle:request_completed;missing_lifecycle_details:tool_completed:{'tool': 'code_execute', 'status': 'ok'} |
