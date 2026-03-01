# Backend Test Baseline

## Date
- 2026-03-01

## Runtime
- Python: 3.12.x (via `py -3.12`)
- Virtualenv: `backend/.venv`

## Command
- `backend/.venv/Scripts/python.exe -m pytest backend/tests -q`

## Result
- `50 passed in 5.11s`

## Notes
- `pytest.ini` at repository root configures `pythonpath = backend`, so tests run without manually setting `PYTHONPATH`.
- Previous collection failures on Python 3.14 beta were resolved by pinning to Python 3.12.
