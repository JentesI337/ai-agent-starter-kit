# Benchmark Summary

- started_at: 2026-03-03T11:04:27.214746+00:00
- finished_at: 2026-03-03T11:09:14.723889+00:00
- total_runs: 3
- passed_runs: 1
- failed_runs: 2
- success_rate: 33.3%
- gated_total_runs: 2
- gated_passed_runs: 0
- gated_failed_runs: 2
- gated_success_rate: 0.0%
- duration_ms p50/p95: 56908.0 / 167713.3
- first_token_ms p50/p95: 29972.0 / 38657.9

## Level Overview

- hard: overall 1/3 (33.3%), gated 0/2 (0.0%)

## Latency Overview

- hard: duration p50/p95=56908.0/167713.3, first_token p50/p95=29972.0/38657.9

## Run Details

| Case | Level | Run | Gate | Pass | Duration ms | Events | Final chars | Reason |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| hard_reasoning_format | hard | 1 | gate | ❌ | 50573 | 286 | 1160 | missing_substring:Top 10;missing_regex:(?i)guardrail-l\u00fccken;missing_regex:(?i)priorisierte ma\u00dfnahmen;missing_regex:(?i)messbare kpis;missing_regex:(?i)rollout-plan;regex_count_below:(?m)^\s*([1-9]|10)\.:expected>=8:got=0 |
| hard_reasoning_depth | hard | 1 | gate | ❌ | 180025 | 604 | 0 | missing_completion_stage:request_completed;final_too_short_lt_1200;missing_substring:Phase;missing_substring:KPI;regex_count_below:(?im)^\s*phase\s*[1-3]\b:expected>=3:got=0;regex_count_below:(?i)kpi[^\n]{0,80}\b(\d+\s*%|\d+\s*ms|\d+\s*s):expected>=2:got=0;missing_lifecycle:request_completed;error_event_or_exception |
| hard_tools_diagnostic | hard | 1 | diag | ✅ | 56908 | 294 | 1126 | ok |
