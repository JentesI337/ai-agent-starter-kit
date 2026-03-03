# Backend Test Baseline

## Status
- Updated on 2026-03-01 after Phase 1-4 + quick wins implementation.
- Legacy baseline (`50 passed in 5.11s`) is archived by this update.

## Runtime
- Python: 3.12.x
- Virtualenv: `backend/.venv`

## Verified command
- `./.venv/Scripts/python.exe -m pytest tests/test_control_plane_contracts.py tests/test_backend_e2e.py tests/test_subrun_lane.py -q`

## Result
- `91 passed in 14.95s`

## Notes
- This baseline intentionally focuses on contract/e2e/subrun paths most affected by current refactoring.
- `pytest.ini` at repository root provides `pythonpath = backend`.
