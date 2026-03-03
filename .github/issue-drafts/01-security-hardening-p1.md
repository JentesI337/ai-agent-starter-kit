# Title
P1: Harden backend execution surface (shell tools, CORS, persistence defaults)

# Body
## Summary
Implement production-grade hardening for backend execution and exposure paths.

## Why
The backend currently allows powerful tool execution and permissive default transport settings. This is useful for local development but too permissive for production defaults.

## Scope
1. Harden command execution:
   - Reduce/replace `shell=True` usage in `run_command` and `start_background_command` where possible.
   - Move from fragile blocklist checks to explicit allowlist policy for safe command families.
   - Add unit tests for bypass patterns and policy enforcement.
2. Make CORS production-safe by default:
   - Replace wildcard defaults with explicit origin list from config.
   - Ensure `allow_credentials` is only true when valid explicit origins are configured.
3. Safe persistence defaults:
   - Set startup reset flags to safe defaults to avoid accidental data loss.
   - Keep explicit opt-in reset behavior for local dev.

## Acceptance Criteria
- [ ] No command execution path relies on unrestricted shell interpretation in default mode.
- [ ] CORS defaults are explicit and production-safe.
- [ ] Startup reset flags default to non-destructive values.
- [ ] Tests cover hardened behavior and pass in CI.
- [ ] README documents secure/prod configuration.

## References
- `backend/app/tools.py`
- `backend/app/agent.py`
- `backend/app/main.py`
- `backend/app/config.py`
