# Title
P2: Reliability improvements (MemoryStore concurrency, backend CI workflow, smoke runbook)

# Body
## Summary
Improve operational reliability and delivery confidence for backend runtime and testing.

## Why
Backend behavior is stable in local runs, but reliability under concurrency and long-term maintainability need explicit guardrails in CI and docs.

## Scope
1. MemoryStore concurrency safety:
   - Add synchronization around in-memory mutation and persistence writes.
   - Validate with targeted tests for concurrent `add` calls.
2. CI workflow for backend:
   - Add GitHub Actions workflow that runs backend tests on Python 3.12.
   - Include dependency install and clear test output artifacts.
3. Smoke runbook:
   - Add concise operational runbook for local smoke checks and troubleshooting.

## Acceptance Criteria
- [ ] MemoryStore is safe under concurrent writes and tested.
- [ ] CI runs backend tests on Python 3.12 and is green.
- [ ] Smoke runbook exists and is linked from README.
- [ ] No regression in existing backend tests.

## References
- `backend/app/memory.py`
- `backend/tests`
- `.github/workflows/`
- `README.md`
