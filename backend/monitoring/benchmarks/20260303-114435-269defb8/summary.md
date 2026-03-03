# Benchmark Summary

- started_at: 2026-03-03T10:44:36.594730+00:00
- finished_at: 2026-03-03T10:52:38.983788+00:00
- total_runs: 5
- passed_runs: 4
- failed_runs: 1
- success_rate: 80.0%
- gated_total_runs: 4
- gated_passed_runs: 3
- gated_failed_runs: 1
- gated_success_rate: 75.0%
- duration_ms p50/p95: 102396.0 / 157212.59999999998
- first_token_ms p50/p95: 31762.0 / 66794.2

## Level Overview

- mid: overall 2/2 (100.0%), gated 2/2 (100.0%)
- hard: overall 2/3 (66.7%), gated 1/2 (50.0%)

## Latency Overview

- hard: duration p50/p95=124399.0/161314.3, first_token p50/p95=55807.0/68167.6
- mid: duration p50/p95=45086.5/51340.15, first_token p50/p95=27377.5/31323.55

## Run Details

| Case | Level | Run | Gate | Pass | Duration ms | Events | Final chars | Reason |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| mid_architecture_plan | mid | 1 | gate | ✅ | 52035 | 191 | 947 | ok |
| mid_orchestration_subrun | mid | 1 | gate | ✅ | 38138 | 223 | 729 | ok |
| hard_reasoning_format | hard | 1 | gate | ✅ | 165416 | 753 | 3550 | ok |
| hard_reasoning_depth | hard | 1 | gate | ❌ | 102396 | 423 | 2127 | regex_count_below:(?im)^\s*phase\s*[1-3]\b:expected>=3:got=0;regex_count_below:(?i)kpi[^\n]{0,80}\b(\d+\s*%|\d+\s*ms|\d+\s*s):expected>=2:got=0 |
| hard_tools_diagnostic | hard | 1 | diag | ✅ | 124399 | 494 | 2282 | ok |
