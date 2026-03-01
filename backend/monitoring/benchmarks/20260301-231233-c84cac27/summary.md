# Benchmark Summary

- started_at: 2026-03-01T22:12:33.893036+00:00
- finished_at: 2026-03-01T22:26:15.009287+00:00
- total_runs: 9
- passed_runs: 5
- failed_runs: 4
- success_rate: 55.6%

## Level Overview

- easy: 3/3 (100.0%)
- mid: 2/3 (66.7%)
- hard: 0/3 (0.0%)

## Run Details

| Case | Level | Run | Pass | Duration ms | Events | Final chars | Reason |
|---|---:|---:|---:|---:|---:|---:|---|
| easy_ping_ok | easy | 1 | ✅ | 7323 | 29 | 2 | ok |
| easy_ping_ok | easy | 2 | ✅ | 3944 | 29 | 2 | ok |
| easy_ping_ok | easy | 3 | ✅ | 16480 | 29 | 2 | ok |
| mid_architecture_plan | mid | 1 | ✅ | 76433 | 199 | 1092 | ok |
| mid_architecture_plan | mid | 2 | ✅ | 86897 | 244 | 1235 | ok |
| mid_architecture_plan | mid | 3 | ❌ | 90004 | 42 | 0 | missing_request_completed;final_too_short_lt_300;missing_substring:1.;missing_substring:5;missing_lifecycle:request_completed;error_event_or_exception |
| hard_orchestrated_research | hard | 1 | ❌ | 180010 | 627 | 0 | missing_request_completed;final_too_short_lt_1200;missing_substring:Top 10;missing_substring:KPI;missing_substring:Phase;missing_lifecycle:request_completed;error_event_or_exception |
| hard_orchestrated_research | hard | 2 | ❌ | 180012 | 128 | 0 | missing_request_completed;final_too_short_lt_1200;missing_substring:Top 10;missing_substring:KPI;missing_substring:Phase;missing_lifecycle:request_completed;error_event_or_exception |
| hard_orchestrated_research | hard | 3 | ❌ | 180003 | 923 | 1362 | missing_request_completed;missing_substring:Top 10;missing_substring:KPI;missing_substring:Phase;missing_lifecycle:request_completed;error_event_or_exception |
