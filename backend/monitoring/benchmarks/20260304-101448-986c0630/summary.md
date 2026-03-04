# Benchmark Summary

- started_at: 2026-03-04T09:14:51.109122+00:00
- finished_at: 2026-03-04T09:19:00.387585+00:00
- total_runs: 3
- passed_runs: 0
- failed_runs: 3
- success_rate: 0.0%
- gated_total_runs: 2
- gated_passed_runs: 0
- gated_failed_runs: 2
- gated_success_rate: 0.0%
- duration_ms p50/p95: 90015.0 / 117016.79999999999
- first_token_ms p50/p95: 16910.0 / 16910.0

## Level Overview

- mid: overall 0/3 (0.0%), gated 0/2 (0.0%)

## Latency Overview

- mid: duration p50/p95=90015.0/117016.79999999999, first_token p50/p95=16910.0/16910.0

## Run Details

| Case | Level | Run | Gate | Pass | Duration ms | Events | Final chars | Reason |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| mid_architecture_plan | mid | 1 | gate | ❌ | 90015 | 24 | 0 | missing_completion_stage:request_completed;final_too_short_lt_300;missing_substring:1.;missing_substring:5;regex_count_below:(?m)^\s*[1-5]\.:expected>=5:got=0;missing_lifecycle:planning_completed;missing_lifecycle:request_completed;error_event_or_exception |
| mid_orchestration_subrun | mid | 1 | gate | ❌ | 120017 | 23 | 0 | missing_completion_stage:request_completed;final_too_short_lt_120;missing_event_type:subrun_status;missing_event_type:final;missing_event_status:subrun_status:accepted;missing_event_status:subrun_status:running;missing_event_fields:subrun_status:{'agent_id': 'head-agent', 'mode': 'run'};missing_lifecycle:planning_completed;missing_lifecycle:request_completed |
| mid_code_execute_diagnostic | mid | 1 | diag | ❌ | 39220 | 194 | 212 | missing_substring:4;missing_lifecycle:tool_completed |
