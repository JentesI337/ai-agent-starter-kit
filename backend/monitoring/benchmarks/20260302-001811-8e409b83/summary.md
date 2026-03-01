# Benchmark Summary

- started_at: 2026-03-01T23:18:12.625701+00:00
- finished_at: 2026-03-01T23:21:09.671084+00:00
- total_runs: 2
- passed_runs: 1
- failed_runs: 1
- success_rate: 50.0%
- gated_total_runs: 1
- gated_passed_runs: 0
- gated_failed_runs: 1
- gated_success_rate: 0.0%

## Level Overview

- hard: overall 1/2 (50.0%), gated 0/1 (0.0%)

## Run Details

| Case | Level | Run | Gate | Pass | Duration ms | Events | Final chars | Reason |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| hard_reasoning_research | hard | 1 | gate | ❌ | 68820 | 814 | 4227 | regex_count_below:(?im)^\s*phase\s*[1-3]\b:expected>=3:got=0;regex_count_below:(?i)kpi[^\n]{0,80}\b(\d+\s*%|\d+\s*ms|\d+\s*s):expected>=2:got=0 |
| hard_tools_diagnostic | hard | 1 | diag | ✅ | 108223 | 566 | 2669 | ok |
