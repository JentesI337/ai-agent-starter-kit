# Benchmark Summary

- started_at: 2026-03-03T10:53:58.439289+00:00
- finished_at: 2026-03-03T10:58:42.944402+00:00
- total_runs: 3
- passed_runs: 2
- failed_runs: 1
- success_rate: 66.7%
- gated_total_runs: 2
- gated_passed_runs: 1
- gated_failed_runs: 1
- gated_success_rate: 50.0%
- duration_ms p50/p95: 98154.0 / 142894.8
- first_token_ms p50/p95: 32742.0 / 38021.4

## Level Overview

- hard: overall 2/3 (66.7%), gated 1/2 (50.0%)

## Latency Overview

- hard: duration p50/p95=98154.0/142894.8, first_token p50/p95=32742.0/38021.4

## Run Details

| Case | Level | Run | Gate | Pass | Duration ms | Events | Final chars | Reason |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| hard_reasoning_format | hard | 1 | gate | ✅ | 147866 | 942 | 4482 | ok |
| hard_reasoning_depth | hard | 1 | gate | ❌ | 98154 | 436 | 2159 | regex_count_below:(?im)^\s*phase\s*[1-3]\b:expected>=3:got=0;regex_count_below:(?i)kpi[^\n]{0,80}\b(\d+\s*%|\d+\s*ms|\d+\s*s):expected>=2:got=0 |
| hard_tools_diagnostic | hard | 1 | diag | ✅ | 38481 | 235 | 1034 | ok |
