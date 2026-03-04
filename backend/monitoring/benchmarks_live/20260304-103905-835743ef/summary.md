# Benchmark Summary

- started_at: 2026-03-04T09:39:07.379319+00:00
- finished_at: 2026-03-04T09:41:01.787371+00:00
- total_runs: 1
- passed_runs: 0
- failed_runs: 1
- success_rate: 0.0%
- gated_total_runs: 0
- gated_passed_runs: 0
- gated_failed_runs: 0
- gated_success_rate: 0.0%
- duration_ms p50/p95: 114388.0 / 114388.0
- first_token_ms p50/p95: 27876.0 / 27876.0

## Level Overview

- mid: overall 0/1 (0.0%), gated 0/0 (0.0%)

## Latency Overview

- mid: duration p50/p95=114388.0/114388.0, first_token p50/p95=27876.0/27876.0

## Run Details

| Case | Level | Run | Gate | Pass | Duration ms | Events | Final chars | Reason |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| mid_code_execute_diagnostic | mid | 1 | diag | ❌ | 114388 | 185 | 212 | missing_lifecycle:tool_started;missing_lifecycle:tool_completed;missing_lifecycle_details:tool_completed:{'tool': 'code_execute', 'status': 'ok'} |
