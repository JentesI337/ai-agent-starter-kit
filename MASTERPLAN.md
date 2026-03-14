# Recipe-Based Workflow System — Full Implementation Plan

## Context

The current workflow system is a traditional graph-based engine (10 step types, DAG execution, visual canvas builder). It competes with n8n/Temporal/Airflow but can't match their maturity. The key advantage of this app is its intelligent agent with 64 tools and a full reasoning pipeline.

**Goal:** Replace the rigid graph engine with a recipe-based system where the agent IS the execution engine. Workflows become "recipes" — structured intent + constraints + checkpoints — and the agent figures out the execution path dynamically. A strict mode provides deterministic linear sequences for cases that need reproducibility.

**Outcome:** A workflow system that no traditional engine can replicate — one where intelligence is in the execution, not the definition.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    RECIPE                            │
│  goal + constraints + checkpoints + tool_policy      │
│  mode: adaptive | strict                             │
└──────────────┬──────────────────────────┬────────────┘
               │                          │
       ┌───────▼────────┐        ┌────────▼───────────┐
       │ ADAPTIVE MODE  │        │   STRICT MODE       │
       │ Agent reasons  │        │ Linear step list    │
       │ through goal,  │        │ executed in order,  │
       │ uses tools,    │        │ deterministic,      │
       │ hits check-    │        │ template-resolved   │
       │ points         │        │ params between      │
       └───────┬────────┘        │ steps               │
               │                 └────────┬────────────┘
               │                          │
       ┌───────▼──────────────────────────▼────────────┐
       │              RECIPE RUNNER                     │
       │  - Wraps AgentRunner (adaptive)                │
       │  - Wraps StepExecutor (strict)                 │
       │  - Checkpoint validation                       │
       │  - Budget enforcement                          │
       │  - SSE event emission                          │
       │  - Pause/resume for human-in-the-loop          │
       └───────┬──────────────────────────┬────────────┘
               │                          │
       ┌───────▼──────────────────────────▼────────────┐
       │           EXISTING INFRA                       │
       │  AgentRunner, ToolExecutionManager,            │
       │  ToolPolicy, LoopState, LongTermMemory,        │
       │  SSE streaming, SqliteStore                    │
       └───────────────────────────────────────────────┘
```

---

## Milestone 1: Recipe Data Model & Storage

**Goal:** Define the recipe model and persistence layer. No execution yet — just CRUD.

### Backend

**1.1 — Recipe models** (`backend/app/workflows/recipe_models.py`)

```python
class RecipeCheckpoint:
    id: str
    label: str                          # human-readable milestone
    verification: str                   # assertion or rubric for evaluation
    verification_mode: "assert" | "agent"  # concrete check vs agent-evaluated
    required: bool = True               # must pass to continue
    order: int                          # sequence position

class RecipeConstraints:
    max_duration_seconds: int | None
    max_tool_calls: int | None
    max_llm_tokens: int | None
    tools_allowed: list[str] | None     # whitelist (None = all)
    tools_denied: list[str] | None      # blacklist
    require_human_approval_before: list[str]  # tool names needing approval

class StrictStep:
    id: str
    label: str
    instruction: str                    # what to do
    tool: str | None                    # specific tool to use (None = agent decides)
    tool_params: dict | None            # fixed params (supports {{prev.output}} templates)
    timeout_seconds: int | None
    retry_count: int = 0

class RecipeDef:
    id: str
    name: str
    description: str
    goal: str                           # natural language intent
    mode: "adaptive" | "strict"
    constraints: RecipeConstraints
    checkpoints: list[RecipeCheckpoint] # adaptive mode milestones
    strict_steps: list[StrictStep] | None  # strict mode only
    agent_id: str | None                # override agent (None = default head-agent)
    triggers: list[WorkflowTrigger]     # reuse existing trigger model
    version: int = 1
    created_at: str
    updated_at: str

class RecipeRunState:
    recipe_id: str
    run_id: str
    session_id: str
    status: "pending" | "running" | "paused" | "completed" | "failed" | "cancelled"
    mode: "adaptive" | "strict"
    # Adaptive mode tracking
    checkpoints_reached: dict[str, CheckpointResult]
    # Strict mode tracking
    step_results: dict[str, StepResult]  # reuse existing StepResult
    current_step_id: str | None
    # Shared
    context: dict                       # accumulated data
    pause_reason: str | None            # why paused (human approval, etc.)
    pause_data: dict | None             # approval context
    started_at: str
    completed_at: str | None
    budget_used: BudgetSnapshot         # tokens, tool_calls, duration

class CheckpointResult:
    checkpoint_id: str
    reached_at: str
    verification_passed: bool
    verification_output: str            # assertion result or agent evaluation
    artifacts: dict                     # data captured at checkpoint

class BudgetSnapshot:
    tokens_used: int
    tool_calls_used: int
    duration_seconds: float
```

**1.2 — Recipe store** (`backend/app/workflows/recipe_store.py`)

- Extend or create new SQLite store (new table `recipes` alongside existing `workflows`)
- CRUD: create, get, list, update, delete
- Recipe run store: save/get/list runs (new table `recipe_runs`)
- Reuse existing patterns from `SqliteWorkflowStore` (WAL, threading.Lock, JSON serialization)
- Audit store: reuse `SqliteWorkflowAuditStore` with entry_type "recipe_step" / "recipe_checkpoint"

**1.3 — Recipe API endpoints** (`backend/app/transport/routers/recipes.py`)

New endpoints (coexist with old workflow endpoints during migration):
- `POST /api/control/recipes.list`
- `POST /api/control/recipes.get`
- `POST /api/control/recipes.create`
- `POST /api/control/recipes.update`
- `POST /api/control/recipes.delete`
- `POST /api/control/recipes.validate`

**1.4 — Recipe handlers** (`backend/app/workflows/recipe_handlers.py`)

- Request validation, idempotency (reuse existing patterns from `handlers.py`)
- Validate checkpoint ordering, constraint sanity checks
- Validate strict steps if mode=strict

### Frontend

**1.5 — Recipe service** (`frontend/src/app/services/recipe.service.ts`)

- TypeScript interfaces mirroring backend models
- HTTP methods for all CRUD endpoints

**1.6 — Recipe list view** (new component or extend workflows page)

- Card grid showing recipes (name, description, mode badge, checkpoint count, trigger icons)
- Search/filter
- Create button → opens recipe editor

**1.7 — Recipe editor — basic form**

- Name, description, goal (textarea)
- Mode toggle: adaptive / strict
- Constraints panel (duration, tool calls, tool allow/deny)
- For adaptive: checkpoint list (add/remove/reorder)
- For strict: step list (add/remove/reorder with instruction fields)
- Triggers section (reuse existing trigger UI)
- Save / delete actions

### Files to modify/create:
- `backend/app/workflows/recipe_models.py` (new)
- `backend/app/workflows/recipe_store.py` (new)
- `backend/app/workflows/recipe_handlers.py` (new)
- `backend/app/transport/routers/recipes.py` (new)
- `backend/app/transport/router_wiring.py` (add recipe router)
- `frontend/src/app/services/recipe.service.ts` (new)
- `frontend/src/app/pages/recipes-page/` (new components)
- `frontend/src/app/app.routes.ts` (add recipe routes)

---

## Milestone 2: Adaptive Recipe Execution

**Goal:** The agent can execute adaptive recipes — reasoning through goals, hitting checkpoints, respecting constraints.

### Backend

**2.1 — Recipe runner** (`backend/app/workflows/recipe_runner.py`)

Core execution engine for adaptive mode:
- Accepts `RecipeDef` + initial message
- Builds a recipe-specific system prompt injected into AgentRunner:
  ```
  You are executing a recipe: "{name}"
  Goal: {goal}

  Checkpoints you must reach (in order):
  1. {checkpoint.label} — verified by: {checkpoint.verification}
  2. ...

  Constraints:
  - Tools available: {tools_allowed}
  - Max duration: {max_duration}

  After completing each checkpoint, emit a checkpoint signal by calling
  the `recipe_checkpoint` tool with the checkpoint_id and your evidence.
  ```
- Wraps `AgentRunner.run()` with:
  - Custom `ToolPolicyDict` built from recipe constraints
  - Budget enforcement via `LoopState` limits (map recipe constraints → runner limits)
  - Checkpoint tracking: intercept `recipe_checkpoint` tool calls to validate
- Returns `RecipeRunState` with all checkpoint results

**2.2 — Checkpoint tool** (`backend/app/tools/implementations/recipe.py`)

New tool: `recipe_checkpoint`
- Called BY the agent during execution to signal checkpoint completion
- Args: `checkpoint_id`, `evidence` (what the agent did to reach this point)
- The runner intercepts this, runs verification:
  - `assert` mode: evaluate expression against context (reuse `transforms.py` safe AST evaluator)
  - `agent` mode: quick LLM call to evaluate rubric against evidence
- Returns pass/fail to the agent so it can adjust

**2.3 — Checkpoint evaluator** (`backend/app/workflows/checkpoint_eval.py`)

- `evaluate_assert(expression, context) -> bool` — reuse safe AST from transforms.py
- `evaluate_agent(rubric, evidence, context) -> (bool, explanation)` — single LLM call with structured output
- Captures artifacts from context at checkpoint time

**2.4 — Human-in-the-loop pause/resume**

- When agent tries to use a tool in `require_human_approval_before`:
  - Run state → `paused`, `pause_reason` = "approval_required"
  - SSE event: `recipe_approval_needed` with tool name + context
  - New endpoint: `POST /api/control/recipes.runs.approve` (approve/deny)
  - On approval: resume AgentRunner from where it left off
  - Reuse existing `PolicyApprovalService` patterns from the agent system

**2.5 — Budget enforcement**

- Map `RecipeConstraints` → AgentRunner limits:
  - `max_duration_seconds` → `runner_time_budget_seconds`
  - `max_tool_calls` → `runner_max_tool_calls`
  - `max_llm_tokens` → tracked via `LoopState.total_tokens_used`
- On budget exceeded: graceful stop, mark run as failed with reason

**2.6 — Execution API**

- `POST /api/control/recipes.execute` → returns `run_id`
- `GET /api/control/recipes.execute.stream` → SSE stream (reuse pattern from workflow router)
- `POST /api/control/recipes.runs.list`
- `POST /api/control/recipes.runs.get`
- `POST /api/control/recipes.runs.approve` (human-in-the-loop)

### Frontend

**2.7 — Recipe execution view**

- Click "Run" on a recipe → navigates to execution view
- **Checkpoint timeline** (vertical, left panel):
  - Each checkpoint as a node: pending → active → passed/failed
  - Animated connector between checkpoints
  - Current agent activity shown between checkpoints (tool calls, reasoning snippets)
- **Live agent log** (right panel):
  - Real-time SSE feed showing what the agent is doing
  - Tool calls with inputs/outputs
  - Agent reasoning snippets
  - Checkpoint verification results
- **Budget meter** (top bar):
  - Progress bars for tokens, tool calls, duration
  - Visual warning when approaching limits
- **Approval modal**:
  - When `recipe_approval_needed` event arrives
  - Shows tool name, context, what the agent wants to do
  - Approve / Deny buttons

**2.8 — Recipe result view**

- Post-execution summary
- Checkpoint timeline with pass/fail status and evidence
- Full tool call log (expandable)
- Budget consumption summary
- "Re-run" button

### Files to modify/create:
- `backend/app/workflows/recipe_runner.py` (new)
- `backend/app/workflows/checkpoint_eval.py` (new)
- `backend/app/tools/implementations/recipe.py` (new — recipe_checkpoint tool)
- `backend/app/tools/catalog.py` (register recipe_checkpoint)
- `backend/app/tools/implementations/base.py` (add RecipeToolMixin)
- `backend/app/workflows/recipe_handlers.py` (add execution handlers)
- `backend/app/transport/routers/recipes.py` (add execution endpoints)
- `frontend/src/app/pages/recipes-page/recipe-execution/` (new)
- `frontend/src/app/pages/recipes-page/recipe-result/` (new)
- `frontend/src/app/services/recipe-execution.service.ts` (new)

---

## Milestone 3: Strict Recipe Execution

**Goal:** Deterministic linear step execution for cases requiring reproducibility.

### Backend

**3.1 — Strict step executor** (extend `recipe_runner.py`)

- Iterates `strict_steps` in order
- For each step:
  - Resolve `{{templates}}` in `tool_params` using context (reuse `transforms.py`)
  - If `tool` specified: invoke directly via `ToolExecutionManager`
  - If `tool` is None: run agent with constrained instruction (single-step, no loop)
  - Capture output → context for next step
  - Handle timeout + retry
- No agent reasoning between steps — purely mechanical
- Same SSE event emission pattern as adaptive mode

**3.2 — Strict mode validation**

- Validate all referenced tools exist in catalog
- Validate template references point to valid step IDs
- Validate step order is achievable (no forward references in templates)

### Frontend

**3.3 — Strict mode execution view**

- Step list (vertical timeline) instead of checkpoint timeline
- Each step: pending → running → success/failed
- Shows tool call + output for each step
- No agent reasoning panel (deterministic = no reasoning to show)
- Same budget meter and result view

**3.4 — Strict mode editor enhancements**

- Step list with:
  - Instruction field
  - Optional tool selector (dropdown from catalog)
  - Optional params editor (JSON with template autocomplete)
  - Timeout / retry fields
- Drag-to-reorder
- "Test step" button (run single step in isolation)

### Files to modify/create:
- `backend/app/workflows/recipe_runner.py` (extend with strict executor)
- `backend/app/workflows/recipe_handlers.py` (add strict validation)
- `frontend/src/app/pages/recipes-page/recipe-execution/` (extend for strict mode)
- `frontend/src/app/pages/recipes-page/recipe-editor/` (extend for strict steps)

---

## Milestone 4: Chat-to-Recipe & Visual Preview

**Goal:** Users describe workflows in chat, the agent creates recipes and generates visual previews for trust/verification.

### Backend

**4.1 — Recipe creation tool** (extend `backend/app/tools/implementations/recipe.py`)

New tools for the agent:
- `create_recipe`: Agent creates a RecipeDef from conversation context
  - Args: name, goal, mode, checkpoints/steps (structured), constraints
  - Saves via recipe_store
  - Returns recipe_id + visual preview data
- `update_recipe`: Modify existing recipe based on user feedback
  - "swap step 2 and 3", "add a checkpoint after metrics collection"

**4.2 — Visual preview generation**

When agent creates/updates a recipe, generate a visualization payload:
- For adaptive: checkpoint timeline data (ordered list with labels + verification summaries)
- For strict: step sequence data (ordered list with labels + tool names)
- Return as structured data that frontend renders (not Mermaid — custom component)

**4.3 — Recipe suggestion from history** (stretch goal)

- Analyze recent chat sessions via `MemoryStore`
- Detect repeated patterns (same tools used in similar order)
- Agent proactively suggests: "I notice you do this often. Want me to save it as a recipe?"
- Uses `LongTermMemoryStore` success patterns as signal

### Frontend

**4.4 — Chat-embedded recipe preview**

When the agent sends a recipe preview in chat:
- Render an inline **recipe card** (similar to how Mermaid diagrams render inline)
- Shows: name, goal, mode, checkpoint/step timeline preview
- Action buttons: "Save Recipe", "Edit First", "Discard"
- "Edit First" opens the recipe editor pre-filled

**4.5 — Recipe editor ↔ chat integration**

- From recipe editor: "Ask Agent" button that opens chat with recipe context
- User can say "make this run every Monday" → agent updates triggers
- User can say "add error handling for when the API is down" → agent adds checkpoint or adjusts goal
- Bidirectional: changes in chat reflect in editor, changes in editor available to agent

### Files to modify/create:
- `backend/app/tools/implementations/recipe.py` (extend with create/update tools)
- `backend/app/tools/catalog.py` (register new tools)
- `frontend/src/app/pages/chat-page.component.ts` (add recipe card rendering)
- `frontend/src/app/components/recipe-preview-card/` (new component)
- `frontend/src/app/pages/recipes-page/recipe-editor/` (add "Ask Agent" integration)

---

## Milestone 5: Long-Running Recipes & Scheduling

**Goal:** Recipes that can pause, wait for external events, and run on schedules.

### Backend

**5.1 — Durable pause/resume**

- On pause (human approval, wait-for-event, scheduled delay):
  - Serialize full agent context (messages, memory, checkpoint state) to run store
  - Release agent resources (no LLM context held open)
  - Set run status = "paused"
- On resume trigger:
  - Deserialize context
  - Rebuild AgentRunner state
  - Continue from last checkpoint/step
- Pause triggers:
  - `require_human_approval_before` (milestone 2 basic version)
  - `wait_for_webhook` — new: recipe pauses until webhook received
  - `scheduled_delay` — pause for N minutes/hours (different from strict delay step)

**5.2 — Webhook resume endpoint**

- `POST /api/control/recipes.runs.webhook/{run_id}` — external system triggers resume
- Validates webhook secret if configured
- Injects webhook payload into recipe context
- Resumes execution

**5.3 — Recipe scheduler** (extend existing `scheduler.py`)

- Add recipe support alongside existing workflow scheduler
- Scan recipes with schedule triggers
- Fire `recipes.execute` on cron match
- Reuse croniter logic

**5.4 — Run lifecycle management**

- Auto-cancel runs exceeding max_duration by 2x (safety net)
- Cleanup old paused runs after configurable TTL
- Run history retention policy

### Frontend

**5.5 — Paused run management**

- Recipe list shows "paused" badge with pause reason
- Click → shows approval modal or wait status
- Manual resume button for admin override

**5.6 — Schedule configuration UI**

- Cron builder (visual, not raw cron strings)
- Next-run preview
- Run history per schedule

### Files to modify/create:
- `backend/app/workflows/recipe_runner.py` (extend with pause/resume serialization)
- `backend/app/workflows/recipe_store.py` (extend run store for pause state)
- `backend/app/transport/routers/recipes.py` (webhook endpoint)
- `backend/app/workflows/scheduler.py` (extend for recipes)
- `frontend/src/app/pages/recipes-page/` (paused state UI)

---

## Milestone 6: Migration & Cleanup

**Goal:** Migrate existing workflows to recipes, deprecate old system.

### 6.1 — Migration script

- Convert existing `WorkflowRecord` → `RecipeDef`:
  - Linear workflows → strict mode recipes (steps become StrictSteps)
  - Complex graphs (fork/join/condition) → adaptive mode with extracted checkpoints
  - Preserve triggers, tool_policy
- Dry-run mode: show what would be migrated without writing

### 6.2 — UI transition

- Replace workflow routes with recipe routes
- Update navigation sidebar
- Remove old canvas builder components
- Keep old workflow API endpoints as deprecated (read-only) for one version cycle

### 6.3 — Code cleanup

- Remove: `engine.py`, `chain_resolver.py`, `contracts.py` (graph-specific code)
- Remove: old workflow handler functions that are fully replaced
- Remove: frontend canvas builder, node palette, connection drawing code
- Keep: `transforms.py` (template resolution — used by strict mode)
- Keep: `store.py` patterns (reused in recipe_store)
- Keep: SSE streaming patterns

### Files to modify/remove:
- `backend/app/workflows/engine.py` (remove)
- `backend/app/workflows/chain_resolver.py` (remove)
- `backend/app/workflows/contracts.py` (remove)
- `backend/app/workflows/models.py` (deprecate, keep for migration period)
- `backend/app/workflows/handlers.py` (deprecate endpoints)
- `frontend/src/app/pages/workflows-page/` (remove canvas builder)
- `frontend/src/app/app.routes.ts` (update routes)
- `frontend/src/app/services/workflow.service.ts` (deprecate)

---

## Execution Order & Session Breakdown

Each milestone is roughly 1-2 sessions of work:

| Session | Milestone | Deliverable |
|---------|-----------|-------------|
| 1-2     | M1: Models & Storage | Recipe CRUD works end-to-end (backend + frontend list/editor) |
| 3-4     | M2: Adaptive Execution | Agent executes adaptive recipes with checkpoints, live UI |
| 5       | M3: Strict Execution | Deterministic step execution with live UI |
| 6-7     | M4: Chat-to-Recipe | Create recipes from chat, inline preview cards |
| 8       | M5: Long-Running | Pause/resume, webhooks, scheduling |
| 9       | M6: Migration | Convert old workflows, remove legacy code |

---

## Verification Strategy

After each milestone, verify:

1. **M1:** Create a recipe via API → see it in the list → edit it → delete it
2. **M2:** Create adaptive recipe "search the web for X and summarize" → run it → watch checkpoints pass in live UI → see final result
3. **M3:** Create strict recipe with 3 tool steps → run it → verify identical output on re-run
4. **M4:** Tell agent in chat "every morning, check my API health and email me" → agent creates recipe → inline preview appears → save it → verify it's in recipe list
5. **M5:** Create recipe with human approval step → run it → verify it pauses → approve → verify it resumes and completes
6. **M6:** Run migration on existing workflows → verify all convert correctly → verify old endpoints return deprecation warnings

---

## Key Design Decisions

1. **Recipes coexist with workflows during migration** — no big bang cutover
2. **Adaptive mode uses the existing AgentRunner** — no new execution engine
3. **Strict mode does NOT support branching** — linear only, use adaptive for complex flows
4. **Checkpoint verification has two modes** — concrete assertions for testable conditions, agent evaluation for fuzzy milestones
5. **The `recipe_checkpoint` tool is called by the agent**, not by the engine — the agent decides when a checkpoint is reached, the engine just validates
6. **Visual preview is a custom component**, not Mermaid — more control over interactivity and styling
7. **Human-in-the-loop uses pause/resume**, not blocking — no LLM context held open while waiting
