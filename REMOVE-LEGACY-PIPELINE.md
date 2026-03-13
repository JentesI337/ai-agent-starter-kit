# Plan: Remove Legacy Pipeline Code

**Goal:** Eliminate `HeadAgent` as a delegation wrapper and all other remnants of the old
3-phase pipeline, leaving `AgentRunner` as the single, authoritative execution engine.

---

## Context

The 3-phase sub-agents (`PlannerAgent`, `ToolSelectorAgent`, `SynthesizerAgent`) were already
deleted in DDD-Phase 12. What remains is a layer of scaffolding that was never cleaned up:

| Remnant | Location | Problem |
|---------|----------|---------|
| `HeadAgent` class | `app/agent/head_agent.py` (84 KB, 1 768 lines) | Its only real job today is `self._agent_runner.run()`. Everything else is infrastructure that belongs elsewhere. |
| Deprecated proxy files | `app/agent_runner.py`, `app/agent_runner_types.py` | Thin shims pointing at `app.agent.runner` — pure noise. |
| `USE_CONTINUOUS_LOOP` feature flag | `runner.py` docstring + any remaining `settings` references | The loop is no longer optional; the flag is a dead concept. |
| `REASONING-PIPELINE.md` | repo root | Still describes the 3-phase model as authoritative. |
| `scripts/cleanup_agent.py` | `backend/scripts/` | One-shot migration script that has already been run. |

---

## Phases

### Phase 1 — Audit & Inventory

Goal: produce a precise list of every symbol and file that must change before touching code.

1. Run a full-text search for `HeadAgent` across `backend/` — record every import site,
   every test that constructs it, and every factory/adapter that returns it.
2. Run the same search for `use_continuous_loop` / `USE_CONTINUOUS_LOOP`.
3. Run the same search for `agent_runner.py` and `agent_runner_types.py` (the old top-level
   proxy files, not the package paths).
4. Check `app/agent/__init__.py` for any re-exports that hide `HeadAgent` behind a public
   alias used by downstream callers.
5. Enumerate the 15 agent records in `factory_defaults.py` — confirm none still pass a
   factory argument that creates `HeadAgent` directly.

Deliverable: a checklist of ~30–50 touch-points, grouped by layer (transport, adapter,
resolution, tests, docs).

---

### Phase 2 — Absorb HeadAgent responsibilities into AgentRunner

`HeadAgent` holds several genuine responsibilities that must live *somewhere*.
Before deleting it, each must be migrated.

#### 2a — Pre-run bootstrap (currently in `HeadAgent.__init__` / `_build_sub_agents`)

The construction of `LlmClient`, `MemoryStore`, `ToolRegistry`, `ReflectionService`,
`VerificationService` is currently done in `HeadAgent`. Move this to the `AgentRunner`
constructor so callers hydrate `AgentRunner` directly.

- Signature change: `AgentRunner.__init__` receives the same dependencies that `HeadAgent`
  currently accepts from its callers.
- No new logic — a pure move.

#### 2b — Guardrails (`_validate_guardrails`)

Five cheap checks (empty message, max length, session ID format, charset, model name).
Move into `AgentRunner.run()` as the very first lines, before `_build_initial_messages`.

#### 2c — Tool-policy resolution (`_resolve_effective_allowed_tools`)

Currently a method on `HeadAgent`, called by the transport layer and then passed into
`AgentRunner`. Move it into `AgentRunner._resolve_effective_allowed_tools` and call it
from the top of `run()`.

#### 2d — MCP initialisation (`_init_mcp_tools`)

Fire-and-forget async setup, currently in `HeadAgent`. Move to AgentRunner's `run()`
pre-loop block where it is already invoked via `self._head_ref` today.

#### 2e — Hook system (`register_hook` / `_invoke_hooks`)

Used for `agent_end`, `tool_start`, etc. Either:
- Move into `AgentRunner` as-is (simplest), or
- Promote to a standalone `HookBus` class in `app/agent/hooks.py` that both
  `AgentRunner` and future callers can import.

Prefer the standalone class — it keeps `AgentRunner` focused and allows hooks to be
registered before `AgentRunner` is created.

#### 2f — `configure_runtime()` hot-swap

Swaps the LLM client and system prompt mid-session. Move as a method on `AgentRunner`.

#### 2g — Policy-override request (`_request_policy_override`)

Human-in-the-loop check for `run_command` / `code_execute` / `spawn_subrun`. Currently
lives in `HeadAgent` and is called via `_runner_execute_tool`. Move into
`ToolExecutionManager` or a new `app/policy/approval.py` — it has nothing to do with
the agent orchestration loop itself.

#### 2h — LTM distillation (`_distill_session_knowledge`)

Fire-and-forget background task. Already triggered by `runner.py` via the head-ref
callback. Replace the callback with a direct call to `LongTermMemoryStore.distill()`
inside `AgentRunner.run()` at the post-loop stage.

---

### Phase 3 — Update the public interface layer

`HeadAgent` is the named type in:

| File | Symbol | Change |
|------|--------|--------|
| `app/agent/adapter.py` | `from app.agent import HeadAgent` | Import `AgentRunner` instead; update constructor call |
| `app/agent/resolution.py` | type annotations referencing `HeadAgent` | Change to `AgentRunner` |
| `app/transport/runtime_wiring.py` | factory that creates `HeadAgent(...)` | Create `AgentRunner(...)` directly |
| `app/agent/__init__.py` | re-exports `HeadAgent` | Re-export `AgentRunner` under the same public name, or remove the alias |

The goal is that no file outside `app/agent/` ever mentions `HeadAgent`.

---

### Phase 4 — Delete dead files

Once all callers are migrated:

1. **Delete** `backend/app/agent/head_agent.py`
2. **Delete** `backend/app/agent_runner.py` (deprecated proxy)
3. **Delete** `backend/app/agent_runner_types.py` (deprecated proxy)
4. **Delete** `backend/scripts/cleanup_agent.py` (already-run migration script)
5. **Conditionally delete** `backend/app/agent/factory_defaults.py` entries for any
   agents whose only purpose was to wrap the old pipeline — verify first.

---

### Phase 5 — Remove the `USE_CONTINUOUS_LOOP` feature flag

1. Find every reference to `use_continuous_loop` in `app/config/` and `runner.py`.
2. Delete the config key and its default.
3. Remove any `if settings.use_continuous_loop:` branches — the continuous loop is always
   on; there is no longer an alternative code path.
4. Update the `AgentRunner` docstring to remove mentions of the flag and the old pipeline.

---

### Phase 6 — Update tests

Tests currently construct `HeadAgent` and then assert on its `AgentRunner`-delegated
behaviour. After Phase 3, they should construct `AgentRunner` directly.

| Test file | Change |
|-----------|--------|
| `test_agent_runner_integration.py` | Replace `HeadAgent(...)` with `AgentRunner(...)` |
| `test_agent_runner_integration_events.py` | Same |
| All other `test_agent_runner_*.py` | Already import `AgentRunner` — verify they still pass |

No new test logic should be needed; the observable behaviour is identical.

---

### Phase 7 — Update documentation

1. **Delete or archive** `REASONING-PIPELINE.md` — it describes a pipeline that no longer
   exists. Replace with a short `AGENT-EXECUTION-MODEL.md` that documents the
   `AgentRunner` continuous loop honestly (the table in Phase 2 of that doc is a good
   skeleton).
2. **Update** `ARCHITECTURE.md` — remove all mentions of Planner/ToolSelector/Synthesizer
   and the 3-phase model.
3. **Update** `DDD_STRUCTURE_PLAN.md` — mark the HeadAgent removal phase as complete.
4. **Update** `ddd-refactoring/PHASE_12_AGENT.md` — note that the HeadAgent wrapper is
   now dissolved.

---

## Execution order

```
Phase 1  (audit)          → no code changes, just a verified checklist
Phase 2  (absorb)         → all changes inside app/agent/runner.py (and one new file for hooks)
Phase 3  (interface)      → adapter, resolution, runtime_wiring, __init__
Phase 4  (delete)         → head_agent.py and proxy files gone
Phase 5  (feature flag)   → config + runner cleanup
Phase 6  (tests)          → integration tests updated
Phase 7  (docs)           → README/ARCHITECTURE updated
```

Phases 2 and 3 should be done in a single PR so the delete in Phase 4 is always a
clean, passing state. Phases 5–7 can be separate follow-up PRs.

---

## What does NOT need to change

- `AgentRunner` logic — no behavioural changes, only new responsibilities moved in.
- `ToolExecutionManager` — its interface stays the same; `HeadAgent._execute_tools` was
  already just a thin pass-through.
- `ReflectionService`, `VerificationService`, `ReplyShaper` — called by `AgentRunner`
  today; nothing changes.
- `app/agent/runner_types.py` (`LoopState`, `PlanStep`, `PlanTracker`, `ToolCall`,
  `ToolResult`) — stays as-is.
- `app/agent/store.py`, `record.py`, `manifest.json` — unrelated to pipeline.
- The 15 agent definitions in `factory_defaults.py` — only the factory wiring changes,
  not the definitions.

---

## Risk & mitigation

| Risk | Mitigation |
|------|-----------|
| A caller still imports `HeadAgent` after Phase 4 | Phase 1 audit + `grep -r HeadAgent` CI check |
| `AgentRunner` constructor becomes too large | Create a `AgentRunnerConfig` dataclass in `runner_types.py` to bundle all deps |
| Hook registrations scattered across transport layer become hard to find | Centralise in `HookBus` (Phase 2e) with a module-level singleton |
| Tests break because `HeadAgent` provided default mocks | Update test fixtures once in `conftest.py` to build `AgentRunner` directly |
