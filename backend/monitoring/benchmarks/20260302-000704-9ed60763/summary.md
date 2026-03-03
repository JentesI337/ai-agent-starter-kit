# Benchmark Summary

- started_at: 2026-03-01T23:07:05.538620+00:00
- finished_at: 2026-03-01T23:10:44.048988+00:00
- total_runs: 2
- passed_runs: 0
- failed_runs: 2
- success_rate: 0.0%
- gated_total_runs: 1
- gated_passed_runs: 0
- gated_failed_runs: 1
- gated_success_rate: 0.0%

## Level Overview

- hard: overall 0/2 (0.0%), gated 0/1 (0.0%)

## Run Details

| Case | Level | Run | Gate | Pass | Duration ms | Events | Final chars | Reason |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| hard_reasoning_research | hard | 1 | gate | ❌ | 38505 | 26 | 179 | final_too_short_lt_1200;missing_substring:Top 10;missing_substring:KPI;missing_substring:Phase;missing_regex:(?i)architektur-risiken;missing_regex:(?i)performance-hotspots;missing_regex:(?i)guardrail-l\u00fccken;missing_regex:(?i)priorisierte ma\u00dfnahmen;missing_regex:(?i)messbare kpis;missing_regex:(?i)rollout-plan;regex_count_below:(?m)^\s*([1-9]|10)\.:expected>=8:got=0;regex_count_below:(?im)^\s*phase\s*[1-3]\b:expected>=3:got=0;regex_count_below:(?i)kpi[^\n]{0,80}\b(\d+\s*%|\d+\s*ms|\d+\s*s):expected>=2:got=0 |
| hard_tools_diagnostic | hard | 1 | diag | ❌ | 180003 | 43 | 0 | missing_request_completed;final_too_short_lt_300;missing_lifecycle:request_completed;error_event_or_exception |
