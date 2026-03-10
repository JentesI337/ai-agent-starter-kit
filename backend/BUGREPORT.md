# P3 Bug Report — Premium Workflow & Automation Engine

Comprehensive audit of all code written in Phases 0–6.

---

## CRITICAL

### BUG-001: Webhook authentication bypass — missing signature allows unauthenticated access

**File:** `app/routers/webhooks.py:64`

```python
if secret and x_webhook_signature:
```

When a webhook has a `webhook_secret` configured but the caller omits the `X-Webhook-Signature` header, validation is **silently skipped**. Any attacker can trigger any secret-protected webhook by simply not sending the header.

**Fix:** Reject requests that are missing the signature when a secret is configured:
```python
if secret:
    if not x_webhook_signature:
        raise HTTPException(status_code=401, detail="Webhook signature required")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    sig = x_webhook_signature.removeprefix("sha256=")
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
```

---

### BUG-002: Frontend sends `type: "step"` but backend expects `type: "agent"`

**File:** `frontend/.../workflows-page.component.ts:767` and `backend/app/orchestrator/workflow_models.py:13`

The canvas uses `'step'` as the node type for agent steps (line 32 of component, line 163 palette item). When `buildWorkflowGraph()` serializes to `WorkflowGraphDef`, it casts with `node.type as WorkflowStepDef['type']` (line 767), but the backend Pydantic model has:

```python
type: Literal["agent", "connector", "transform", "condition", "delay"]
```

The value `"step"` is not in the Literal. Pydantic validation will **reject every sequential workflow saved from the UI** because the graph contains steps with `type: "step"` instead of `type: "agent"`.

**Fix:** Map `'step'` → `'agent'` in `buildWorkflowGraph()`:
```typescript
type: (node.type === 'step' ? 'agent' : node.type) as WorkflowStepDef['type'],
```

---

### BUG-003: SSE event broadcasting persists stale pre-state instead of actual execution state

**File:** `app/handlers/workflow_handlers.py:457-462` and `app/services/workflow_run_store.py:100-109`

`make_send_event(run_id, _pre_state)` captures a reference to `_pre_state` (an empty `WorkflowExecutionState`). Inside `make_send_event`, the `send_event` closure calls `store.save(state)` where `state` is that empty `_pre_state` — **not** the real `execution_state` that the engine is populating with step results.

Every intermediate save (after each step completion) writes the **empty pre-state** to disk, overwriting the initial save. The final `run_store.save(execution_state)` at line 484-485 does save the correct state, but:
- If the engine crashes mid-execution, the persisted state has no step results
- SSE subscribers see events but the disk has stale data

**Fix:** Pass a mutable reference or use the engine's state object:
```python
# Option A: let the engine's state be the same object
execution_state = _pre_state  # reuse same reference
execution_state = await engine.execute(...)  # but engine creates its own...
```
The real fix is to change `WorkflowEngine.execute()` to accept an existing state object, or change `make_send_event` to use a wrapper that always saves the latest state from a mutable container.

---

### BUG-004: Docstring claims "No eval()" but `evaluate_condition` uses `eval()`

**File:** `app/orchestrator/workflow_transforms.py:6-7, 207`

Module docstring says:
> No `eval()` or `exec()` — templates use regex extraction + dot-path traversal, conditions use `ast` whitelisting.

But line 207:
```python
result = eval(code, {"__builtins__": {}}, namespace)  # noqa: S307
```

While the AST whitelist reduces attack surface, the `__builtins__: {}` sandbox is bypassable in CPython (well-known `().__class__.__bases__[0].__subclasses__()` escape). The whitelist allows `ast.Attribute` and `ast.Subscript`, enabling attribute chain traversal on arbitrary objects in the namespace.

**Risk:** An attacker who controls a condition expression (e.g. via workflow config) could potentially escape the sandbox.

**Fix:** Either remove the misleading docstring, or replace `eval()` with a recursive AST interpreter that resolves values without executing arbitrary Python.

---

## HIGH

### BUG-005: No error recovery for sequential execution — orphaned run state

**File:** `app/handlers/workflow_handlers.py:468-485`

```python
_pre_state = _WES(...)
if run_store is not None:
    run_store.save(_pre_state)   # saved with status="running"

execution_state = await engine.execute(...)  # can raise

if run_store is not None:
    run_store.save(execution_state)  # never reached on exception
```

If `engine.execute()` throws an unhandled exception, the run remains in `status="running"` on disk forever. No `try/finally` block ensures the state is updated to `"failed"`.

**Fix:** Wrap in try/finally:
```python
try:
    execution_state = await engine.execute(...)
except Exception:
    _pre_state.status = "failed"
    if run_store: run_store.save(_pre_state)
    raise
if run_store: run_store.save(execution_state)
```

---

### BUG-006: Webhook error handler leaks internal exception details to caller

**File:** `app/routers/webhooks.py:90-92`

```python
except Exception as exc:
    raise HTTPException(status_code=500, detail=str(exc))
```

Stack traces, file paths, and internal error messages are returned verbatim to the external caller.

**Fix:** Return a generic message: `detail="Workflow execution failed"`

---

### BUG-007: Idempotency fingerprint for workflow updates omits key fields

**File:** `app/handlers/workflow_handlers.py:354-363`

`build_workflow_create_fingerprint()` for updates does not include `execution_mode`, `workflow_graph`, or `triggers`. Two updates with identical name/description/steps but different execution mode or triggers will be deduplicated incorrectly — the second update returns the first's cached response.

**Fix:** Include all mutable fields in the fingerprint.

---

### BUG-008: `workflow_failed` SSE event never received by frontend

**File:** `frontend/.../workflow-execution.service.ts:64-69, 78`

The `eventTypes` array registers listeners for:
```typescript
['workflow_step_started', 'workflow_step_completed', 'workflow_step_failed', 'workflow_completed']
```

Missing: `'workflow_failed'`. But line 78 checks for it:
```typescript
if (eventType === 'workflow_completed' || eventType === 'workflow_failed') {
```

The `workflow_failed` condition is dead code — no listener is registered for that event type, so it will never fire. The EventSource will never close on workflow failure; instead the `onerror` handler at line 89 will eventually fire.

**Fix:** Add `'workflow_failed'` to the `eventTypes` array.

---

### BUG-009: Memory leak — agent subscription never unsubscribed

**File:** `frontend/.../workflows-page.component.ts:178-180`

```typescript
this.agentsService.getAgents().subscribe({
    next: (a) => { this.agents = a; this.cdr.markForCheck(); },
});
```

This subscription is never stored or unsubscribed in `ngOnDestroy()`. If the component is created/destroyed repeatedly (route navigation), each instance leaks a subscription.

**Fix:** Store the subscription and unsubscribe in `ngOnDestroy()`.

---

### BUG-010: Copy URL button does nothing

**File:** `frontend/.../workflows-page.component.html:514`

```html
<button class="btn-copy" (click)="$event.preventDefault()" title="Copy URL">⧉</button>
```

The click handler only calls `preventDefault()` — no clipboard copy logic. The button is non-functional.

**Fix:** Add a `copyToClipboard(text: string)` method and wire it up.

---

## MEDIUM

### BUG-011: `_subscribers` dict in WorkflowRunStore accessed without synchronization

**File:** `app/services/workflow_run_store.py:28, 77-98`

The `_subscribers` dict is modified by `subscribe()`, `unsubscribe()`, and iterated by `broadcast()` — all potentially from different async contexts. The existing `self._lock` (threading.Lock) is only used for file I/O. Concurrent modification during iteration can cause `RuntimeError` or lost items.

**Fix:** Use an `asyncio.Lock` for subscriber operations, or at minimum iterate over a snapshot (`list(subs)` in broadcast).

---

### BUG-012: SSE subscriber queues never cleaned up on client disconnect

**File:** `app/services/workflow_run_store.py:77-80`

If a client disconnects without the SSE endpoint reaching its `finally` block (e.g. network drop), the queue remains in `_subscribers` indefinitely. With many disconnects, memory grows unbounded.

**Fix:** Add a TTL or periodic cleanup for stale subscribers. Alternatively, use weak references.

---

### BUG-013: Cron schedule drifts — next_run_at computed from wall clock, not ideal schedule

**File:** `app/services/workflow_scheduler.py:108`

```python
new_next = _next_cron_time(cron_expr, now)
```

If execution takes 5 minutes, the next scheduled run is computed from `now` (post-execution), not the original scheduled time. For "every hour" cron, runs gradually drift later. Over time this compounds.

**Fix:** Compute next from the original `next_dt` (the time it was supposed to fire), not `now`:
```python
new_next = _next_cron_time(cron_expr, next_dt)
```

---

### BUG-014: Redundant double-await in template instantiation

**File:** `app/routers/control_workflows.py:206-208`

```python
result = await workflows_create_handler(create_payload, x_idempotency_key)
if inspect.isawaitable(result):
    result = await result
```

The result is already awaited on line 206. The `isawaitable` check is dead code that never triggers.

**Fix:** Remove lines 207-208.

---

### BUG-015: `[class.open]="selectedNode || true"` — always true

**File:** `frontend/.../workflows-page.component.html:337`

```html
<div class="props-panel" [class.open]="selectedNode || true">
```

The `|| true` makes this always evaluate to `true`. The `.open` class is permanently applied, so the panel never closes.

**Fix:** `[class.open]="!!selectedNode"` or remove the class binding.

---

### BUG-016: Connector step calls `connector_registry.create()` which may not exist

**File:** `app/orchestrator/workflow_engine.py:279`

```python
connector = self._connector_registry.create(config)
```

The `ConnectorRegistry` class uses `.get()` to look up connector classes (as seen in `tools_workflow.py:96`). There is no `.create()` method visible in the registry interface. This will raise `AttributeError` at runtime when a connector step executes.

**Fix:** Use the actual registry API to instantiate the connector.

---

### BUG-017: `WorkflowUpdatePayload` missing `allow_subrun_delegation` field

**File:** `frontend/.../workflow.service.ts:71-83`

The `WorkflowUpdatePayload` interface does not include `allow_subrun_delegation`, but the backend accepts it. If the user toggles subrun delegation and saves, the field is silently dropped from the update.

**Fix:** Add `allow_subrun_delegation?: boolean` to `WorkflowUpdatePayload`.

---

### BUG-018: Hardcoded `http://localhost:8000` API base URL

**Files:** `frontend/.../workflow.service.ts:119`, `frontend/.../workflow-execution.service.ts:47`

Both services hardcode the API URL. This breaks in any non-localhost environment (Docker, production, different port).

**Fix:** Use `environment.ts` config or derive from `window.location.origin`.

---

### BUG-019: Silent exception swallowing on connector import in sequential handler

**File:** `app/handlers/workflow_handlers.py:440-441`

```python
except Exception:
    pass
```

Catches **all** exceptions (including `TypeError`, `AttributeError`, genuine bugs) and silently ignores them. A misspelled function name or wrong argument would be invisible.

**Fix:** Catch `ImportError` and `RuntimeError` specifically, log others at warning level.

---

### BUG-020: Transform step wraps expression in `resolve_templates()` but doesn't use `{{…}}` syntax

**File:** `app/orchestrator/workflow_engine.py:296`

```python
expr = step_def.transform_expr or ""
resolved = resolve_templates(expr, state.context)
```

If the user enters `step1.output.data` (without `{{…}}` wrappers), `resolve_templates` won't match anything — it only matches `{{…}}` patterns. The expression passes through unchanged and then `json.loads` on a dot-path string fails.

The UI placeholder text says `"e.g. step1.output.data"` (without braces), reinforcing the wrong expectation.

**Fix:** Either auto-wrap the expression: `resolve_templates("{{" + expr + "}}", state.context)`, or update the UI placeholder to show `"e.g. {{step1.output.data}}"`.

---

## LOW

### BUG-021: Unused loop variable in scheduler

**File:** `app/services/workflow_scheduler.py:64`

```python
for idx, t in enumerate(triggers):
```

`idx` is never used. Use `for t in triggers:` instead.

---

### BUG-022: Missing `trackBy` functions in Angular `*ngFor` loops

**File:** `frontend/.../workflows-page.component.html` — lines 49, 104, 143, 278, 485, 570

Six `*ngFor` loops lack `trackBy` functions. With `OnPush` change detection and frequent re-renders (canvas dragging, execution monitoring), this causes unnecessary DOM recycling.

**Fix:** Add `trackBy` returning node/edge/entry IDs.

---

### BUG-023: `first`/`last` filters return original value for non-list inputs

**File:** `app/orchestrator/workflow_transforms.py:29-30`

```python
"first": lambda v: v[0] if isinstance(v, (list, tuple)) and v else v,
```

Applying `| first` to a dict or string silently returns the whole value. For strings, `v[0]` would make sense but doesn't trigger. For dicts, returning the dict is confusing.

---

### BUG-024: `generate_image` filter chain only splits on first `|`

**File:** `app/orchestrator/workflow_transforms.py:100`

```python
path_part, filter_part = expr.split("|", 1)
```

Multiple filters like `{{data | upper | strip}}` work because `_apply_filters` re-splits on `|`. But the path extraction on `split("|", 1)` means the path part only gets the first segment before `|` — this is correct behavior. No bug, just noting the non-obvious two-level split design.

---

### BUG-025: Inconsistent color variable fallbacks in SCSS

**File:** `frontend/.../workflows-page.component.scss`

Some places use `var(--c-green, #22c55e)` (with fallback), others use bare `var(--c-green)` (no fallback). If the host page doesn't define `--c-green`, those rules silently fail.

---

### BUG-026: `openEdit` called twice on card-action edit button click

**File:** `frontend/.../workflows-page.component.html:81`

```html
<button class="card-action" title="Edit" (click)="openEdit(wf); $event.stopPropagation()">
```

The button is inside `.wf-card` which also has `(click)="openEdit(wf)"`. `stopPropagation()` prevents the parent handler, but the button handler itself calls `openEdit(wf)`. Since the parent click also calls the same function, and `stopPropagation` does prevent parent — this is actually fine. False alarm.

---

## Summary

| ID | Severity | Category | Component |
|----|----------|----------|-----------|
| 001 | CRITICAL | Security | webhooks.py |
| 002 | CRITICAL | Type mismatch | frontend ↔ backend |
| 003 | CRITICAL | Data integrity | workflow_run_store / handlers |
| 004 | CRITICAL | Security | workflow_transforms.py |
| 005 | HIGH | Data integrity | workflow_handlers.py |
| 006 | HIGH | Info disclosure | webhooks.py |
| 007 | HIGH | Business logic | workflow_handlers.py |
| 008 | HIGH | Dead code | workflow-execution.service.ts |
| 009 | HIGH | Memory leak | workflows-page.component.ts |
| 010 | HIGH | Missing feature | workflows-page.component.html |
| 011 | MEDIUM | Race condition | workflow_run_store.py |
| 012 | MEDIUM | Memory leak | workflow_run_store.py |
| 013 | MEDIUM | Business logic | workflow_scheduler.py |
| 014 | MEDIUM | Dead code | control_workflows.py |
| 015 | MEDIUM | UI logic | workflows-page.component.html |
| 016 | MEDIUM | Wrong API call | workflow_engine.py |
| 017 | MEDIUM | Missing field | workflow.service.ts |
| 018 | MEDIUM | Hardcoded config | workflow.service.ts, workflow-execution.service.ts |
| 019 | MEDIUM | Error handling | workflow_handlers.py |
| 020 | MEDIUM | UX mismatch | workflow_engine.py / HTML |
| 021 | LOW | Dead code | workflow_scheduler.py |
| 022 | LOW | Performance | workflows-page.component.html |
| 023 | LOW | Semantics | workflow_transforms.py |
| 024 | LOW | — | workflow_transforms.py (not a bug) |
| 025 | LOW | CSS | workflows-page.component.scss |
