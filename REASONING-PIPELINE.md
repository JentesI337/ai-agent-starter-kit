# Reasoning Pipeline — End-to-End Reference

> Source of truth for the reasoning pipeline from initial WebSocket message
> to final streamed answer.  All line numbers reference `backend/app/`.
> Last verified: 2026-03-08.  Python 3.13.5.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture at a Glance](#2-architecture-at-a-glance)
3. [Phase 0 — WebSocket Entry & Agent Routing](#3-phase-0--websocket-entry--agent-routing)
4. [Phase 1 — Guardrails & Init](#4-phase-1--guardrails--init)
5. [Phase 2 — Memory & Context Budgeting](#5-phase-2--memory--context-budgeting)
6. [Phase 3 — Planning](#6-phase-3--planning)
7. [Phase 4 — Tool Selection & Execution Loop](#7-phase-4--tool-selection--execution-loop)
8. [Phase 5 — Synthesis](#8-phase-5--synthesis)
9. [Phase 6 — Reflection](#9-phase-6--reflection)
10. [Phase 7 — Evidence Gates & Reply Shaping](#10-phase-7--evidence-gates--reply-shaping)
11. [Phase 8 — Response & Distillation](#11-phase-8--response--distillation)
12. [LLM Call Budget](#12-llm-call-budget)
13. [Configuration Reference](#13-configuration-reference)
14. [Lifecycle Events](#14-lifecycle-events)
15. [Tool Catalog](#15-tool-catalog)
16. [Model Routing](#16-model-routing)
17. [Prompt Chain](#17-prompt-chain)

---

## 1. Overview

A single user request flows through **eight sequential phases** before a final
answer is streamed back via WebSocket.  Each phase is implemented as a
dedicated sub-agent or service, orchestrated by `HeadAgent.run()` in
`agent.py`.

```
User ──WS──▸ ws_handler ──▸ HeadAgent.run()
                              │
         ┌────────────────────┼────────────────────────┐
         ▼                    ▼                         ▼
   0. Routing           1. Guardrails            2. Memory/Context
         │                    │                         │
         ▼                    ▼                         ▼
   3. Planning ──▸ 4. Tool Loop ──▸ 5. Synthesis ──▸ 6. Reflection
                                                        │
                                          ┌─────────────┤
                                          ▼             ▼
                                   7. Reply Shaping  8. Response
                                                     + Distillation
```

**Typical request:** 6–8 LLM calls, ~10–25 seconds.
**Max theoretical:** 15 LLM calls (complex task with full replanning + reflection retries).
**Trivial request** ("Hi", "Thanks"): 2 LLM calls (plan → direct answer), <3 seconds.

---

## 2. Architecture at a Glance

| Component | File | Role |
|-----------|------|------|
| WebSocket handler | `ws_handler.py` | Parses envelope, routes to agent |
| HeadAgent | `agent.py` (~3500 LOC) | Main orchestrator, owns the `run()` loop |
| PlannerAgent | `agents/planner_agent.py` | Creates execution plans |
| ToolSelectorAgent | `agents/tool_selector_agent.py` | Picks tools + arguments |
| SynthesizerAgent | `agents/synthesizer_agent.py` | Generates final answer from plan + tool results |
| ReflectionService | `services/reflection_service.py` | LLM-based QA scoring |
| ReplyShaper | `services/reply_shaper.py` | Cleans, dedupes, validates answer format |
| ToolCallGatekeeper | `services/tool_call_gatekeeper.py` | Detects tool-call loops |
| ContextReducer | `services/context_reducer.py` | Budget-aware context assembly |
| MemoryStore | `memory.py` | Per-session conversation memory |
| ToolCatalog | `tool_catalog.py` | Canonical tool definitions |
| ModelRegistry | `model_routing/model_registry.py` | Model capability profiles |
| PolicyApprovalService | `services/policy_approval_service.py` | Human-in-the-loop gates |
| Step Executors | `orchestrator/step_executors.py` | Frozen wrappers for plan/tool/synth steps |

### Step Executor Pattern

All three core phases (plan, tool-select, synthesize) follow a frozen-dataclass
wrapper pattern defined in `orchestrator/step_executors.py`:

| Executor | Input Dataclass | Output |
|----------|-----------------|--------|
| `PlannerStepExecutor` | `PlannerInput(user_message, reduced_context, prompt_mode)` | `plan_text: str` |
| `ToolStepExecutor` | `ToolSelectorInput(user_message, plan_text, reduced_context, prompt_mode)` | `tool_results: str` |
| `SynthesizeStepExecutor` | `SynthesizerInput(user_message, plan_text, tool_results, reduced_context, prompt_mode, task_type)` | `final_text: str` |

---

## 3. Phase 0 — WebSocket Entry & Agent Routing

### 3.1 Envelope

Every message arrives as a JSON `WsInboundEnvelope` (`models.py`):

```python
class WsInboundEnvelope(BaseModel):
    type: str                           # "user_message" | "policy_decision" | ...
    content: str                        # User's message text (max 200 000 chars)
    agent_id: str | None                # Explicit agent request (optional)
    mode: str | None                    # Operating mode
    preset: str | None                  # Preset override
    model: str | None                   # Model override
    session_id: str | None              # Conversation session
    runtime_target: str | None          # Runtime backend target
    queue_mode: str | None              # Queue behavior
    prompt_mode: str | None             # Prompt variant
    tool_policy: ToolPolicyPayload | None
    reasoning_level: str | None         # Reasoning depth override
    reasoning_visibility: str | None    # Whether to show reasoning steps
```

**Supported message types:** `user_message`, `subrun_spawn`,
`runtime_switch_request`, `clarification_response`, `policy_decision`.

### 3.2 Agent Routing

`route_agent_for_message()` selects the agent in this priority order:

1. **Explicit request** — if `agent_id` is set, use that agent directly.
2. **Preset routing** — e.g. preset `"review"` → `review-agent`.
3. **Capability matching** — the message is scored against capability keywords
   (`code_reasoning`, `review_analysis`, `deep_research`, `architecture_analysis`,
   `test_generation`, `security_review`, `documentation`, `refactoring`, `ci_cd`,
   plus domain-specific).  The agent with the best capability score wins.
4. **Default** — if no match, route to `head-agent`.

**15 registered agents:**
`head-agent` (primary), `coder-agent`, `review-agent`, `researcher-agent`,
`architect-agent`, `test-agent`, `security-agent`, `doc-agent`,
`refactor-agent`, `devops-agent`, `fintech-agent`, `healthtech-agent`,
`legaltech-agent`, `ecommerce-agent`, `industrytech-agent`.

### 3.3 Request ID

```python
request_id = str(uuid.uuid4())   # ws_handler.py
```

After routing, `ws_handler` calls `agent.run(user_message, send_event, session_id, request_id, model, ...)`.

---

## 4. Phase 1 — Guardrails & Init

**`agent.py` lines ~1961–2060.**

`_validate_guardrails()` runs five checks — **always active, no env toggle**:

| # | Check | Rejection |
|---|-------|-----------|
| 1 | Empty message (`len(strip()) == 0`) | `GuardrailViolation` |
| 2 | Message length > `max_user_message_length` (default 8000) | `GuardrailViolation` |
| 3 | Session ID length > 120 | `GuardrailViolation` |
| 4 | Session ID non-alphanumeric (`[^A-Za-z0-9_-]`) | `GuardrailViolation` |
| 5 | Model name length > 120 | `GuardrailViolation` |

After guardrails pass:

- **Tool policy** is resolved from the envelope payload.  The policy uses a
  **deny-only architecture**: tools are allowed by default; only tools
  explicitly listed in the `deny` set are blocked.  There are no `allow` lists.
- **MCP tools** are registered if configured (`_ensure_mcp_tools_registered()`).
- **Toolchain check** verifies tool definitions are consistent.

**Lifecycle events emitted:**
`run_started` → `guardrails_passed` → `tool_policy_resolved` → `toolchain_checked`.

---

## 5. Phase 2 — Memory & Context Budgeting

**`agent.py` lines ~537–566 (long-term memory), ~1882–1960 (context budgeting).**

### 5.1 Memory

`MemoryStore` (`memory.py`) maintains a per-session conversation history as a
bounded deque (default `max_items_per_session = 20`).

**Operations at run start:**
1. `repair_orphaned_tool_calls(session_id)` — fixes tool-call items without matching responses.
2. `sanitize_session_history(session_id)` — removes malformed entries.
3. `add(session_id, "user", user_message)` — stores the current message.

**Persistence:** JSONL files in `memory_store/` with hashed filenames.

**Lifecycle events:** `memory_updated`, `orphaned_tool_calls_repaired`,
`session_history_sanitized`.

### 5.2 Context Budgeting (ContextReducer)

`services/context_reducer.py` assembles the prompt context within a token budget:

| Segment | Budget Share | Purpose |
|---------|-------------|---------|
| Task/System prompt | first 20% | The user message + system instructions |
| Tool outputs | 40% | Results from tool calls |
| Memory | 30% | Conversation history |
| Snapshot | 10% | Workspace/project state |

**Security:** Sensitive patterns are redacted before context assembly:
- Bearer tokens: `r"(?i)(Bearer\s+)[A-Za-z0-9\-_.]{12,}"`
- API keys, private keys, passwords

**Context isolation:** Tool outputs are wrapped in
`<tool_output isolation="content_only">...</tool_output>` tags.

**Lifecycle event:** `context_segmented` — emitted three times (planning, tool, synthesis)
with detailed breakdown:
```json
{
  "phase": "planning|tool|synthesis",
  "budget_tokens": 4096,
  "used_tokens": 2800,
  "segments": {
    "system_prompt": {"tokens_est": 512, "chars": 2048, "share_pct": 18},
    "user_payload": {"tokens_est": 256, "chars": 1024, "share_pct": 9},
    "memory": {"tokens_est": 800, "chars": 3200, "share_pct": 29},
    "tool_results": {"tokens_est": 1100, "chars": 4400, "share_pct": 39}
  }
}
```

---

## 6. Phase 3 — Planning

**`agent.py` lines ~1762–1795.  LLM call #1.**

The `PlannerStepExecutor` calls `PlannerAgent` to classify the request and
produce an execution plan.

### 6.1 Classification

The planner categorizes the request:

| Category | Action |
|----------|--------|
| **Trivial** | Greeting, yes/no → `direct_answer`, no tools needed |
| **Moderate** | Single task → 1–3 steps with specific tools |
| **Complex** | Multi-step → dependency graph with parallel/sequential steps |

### 6.2 Plan Format

Each step specifies:
- **WHAT** — concrete action
- **WHY** — how it serves the goal
- **TOOL** — which tool to use, or `none`
- **DEPENDS_ON** — which prior step, or `none`

**Fallback rule:** If a step uses `run_command` to scaffold/install (npm, ng,
pip), the plan must include a fallback step using `write_file` in case the
command times out or is blocked.

### 6.3 Direct-Answer Short-Circuit

After planning, `_is_direct_answer_plan()` checks whether the plan is a
trivial/greeting response that needs no tools.  The classifier rejects
`direct_answer` when the plan contains **multiple bullet points or numbered
steps** (`re.findall(r'^\s*(?:\d+[.)\-]|[-*•])\s', text, re.MULTILINE) > 1`),
preventing multi-step plans from being short-circuited.

### 6.4 Plan Verification

After planning, `VerificationService.verify_plan()` checks the plan
for structural validity and returns `(status, reason, details)`.

**Lifecycle events:** `planning_started` → `planning_completed` →
`verification_plan` → `verification_plan_semantic`.

---

## 7. Phase 4 — Tool Selection & Execution Loop

**`agent.py` lines ~2144–2298.  LLM calls #2–N.**

This is the core execution loop.  It selects tools, executes them, and
optionally replans based on results.

> **Removed: Intent Gate.**  An earlier version used `IntentDetector` to
> classify user intent (e.g. `execute_command`) before tool selection.  This
> single-intent classifier blocked multi-tool pipelines when any step
> contained command-like language.  The gate has been neutralized:
> `_detect_intent_gate()` returns a no-op (`intent=None`), and
> `select_and_execute_tools()` no longer accepts `detect_intent_gate` or
> `request_policy_override` parameters.  Tool selection is now fully
> LLM-driven.

### 7.1 Tool Selection (LLM call)

`ToolSelectorAgent` receives the plan + context and returns a JSON action list:

```json
{
  "actions": [
    {"tool": "list_dir", "args": {"path": "/workspace/src"}},
    {"tool": "read_file", "args": {"path": "/workspace/src/main.py"}}
  ]
}
```

**Agent constraints:** `max_context=4096`, `temperature=0.1`,
`reasoning_depth=1`, `reflection_passes=0`.

**System prompt:** Base prompt + `_TOOL_ROUTING_APPENDIX` (loaded from
`prompts/tool_routing.md`).  This appendix contains per-tool routing
rules with "When to use" / "When NOT to use" / caveats.

### 7.2 Action Parsing & Repair

If the LLM output is not valid JSON:

1. `extract_json_candidate(raw)` — finds first balanced `{...}` block
   (max 3000 chars).
2. **Repair LLM call** — a dedicated repair prompt converts malformed output
   into strict `{"actions": [...]}` JSON.  This is an extra LLM call only
   when parsing fails.
3. Re-parse the repaired output.

### 7.3 Tool Execution

Each action is executed sequentially through `tools.py`:

**Command safety pipeline (for `run_command`):**

1. **Allowlist check** — the executable must be in `COMMAND_ALLOWLIST`
   (37 defaults: `python`, `pip`, `pytest`, `git`, `npm`, `node`, `make`,
   `docker`, `ls`, `grep`, `rg`, etc.).
2. **Safety pattern check** — 15+ regex patterns block destructive commands:
   `rm -rf`, `del /f`, `format`, `shutdown`, `mkfs`, `dd`, pipe-to-shell
   (`curl | sh`), `python -c`, PowerShell `-enc`, netcat listeners, metadata
   endpoint access (`169.254.169.254`), shell chaining (`||`, `&&`, `;`,
   backticks, `$()`).
3. **Policy approval** — if the command is not on the allowlist,
   `PolicyApprovalService` sends a `policy_decision` event to the frontend
   and waits for user approval.  Approval keys are
   `(run_id, session_id, tool, resource)` — idempotent.
4. **Execution** — `subprocess.run(shell=False)` with the command split into
   an argument list.

**Platform constraint:** Because `shell=False`, OS shell builtins (`dir`,
`type`, `echo`, `findstr` on Windows; `cat` without a real binary) are **not
available**.  The prompts explicitly direct the LLM to use `list_dir`,
`read_file`, `grep_search` instead.

**Workspace path auto-correction:** `_resolve_workspace_path()` detects and
corrects duplicated workspace directory prefixes (e.g.
`backend/backend/app/config.py` → `backend/app/config.py`).  This compensates
for LLMs that prepend the workspace root when it is already the cwd.
`grep_search` applies the same auto-correction to its `include_pattern`
argument.

**Glob matching:** `file_search` and `grep_search` use
`PurePosixPath(rel).match(pattern)` instead of `fnmatch.fnmatch()` because
`fnmatch` does not treat `**` as a recursive glob.  `PurePosixPath.match()`
(Python 3.12+) handles `**` correctly.

**Caps:**

| Cap | Default | Env var |
|-----|---------|---------|
| Max tool calls per run | 8 | `RUN_TOOL_CALL_CAP` |
| Time cap (seconds) | 90 | `RUN_TOOL_TIME_CAP_SECONDS` |
| Result max chars | 6000 | `TOOL_RESULT_MAX_CHARS` |
| Smart truncate | enabled | `TOOL_RESULT_SMART_TRUNCATE_ENABLED` |
| Context guard | enabled | `TOOL_RESULT_CONTEXT_GUARD_ENABLED` |

### 7.4 Tool Call Gatekeeper (Loop Detection)

`ToolCallGatekeeper` monitors the tool-call stream for degenerate patterns:

| Detector | Threshold | Action |
|----------|-----------|--------|
| Generic repeat (same signature) | warn=2, critical=3 | Warn → block |
| Ping-pong (A→B→A→B alternation) | enabled | Warn → block |
| Poll-no-progress (same result) | 3 identical results | Block |
| Circuit breaker | ≥6 repeats | **Break entire run** |

`ToolLoopDecision` returned by the gatekeeper:
```python
@dataclass
class ToolLoopDecision:
    blocked: bool
    break_run: bool
    rejection_message: str | None
    lifecycle_events: list[tuple[str, dict]]
```

### 7.5 Replanning

After tool execution, `_classify_tool_results_state()` evaluates the results:

| Classification | Action |
|---------------|--------|
| `"usable"` | Results are good → exit loop, proceed to synthesis |
| `"blocked"` | Policy-blocked → exit loop, synthesize with partial results |
| `"steer_interrupted"` | User-initiated interrupt → exit loop |
| `"empty"` | No tool output → replan (up to `run_empty_tool_replan_max_attempts`) |
| `"error"` | Tool execution error → replan (up to `run_error_tool_replan_max_attempts`) |

**Max replan cycles** = `run_max_replan_iterations` (1) +
`run_empty_tool_replan_max_attempts` (1) + `run_error_tool_replan_max_attempts` (1) = **3 max**.

**Lifecycle events:** `replanning_started` → `replanning_completed` /
`replanning_exhausted`.

---

## 8. Phase 5 — Synthesis

**`agent.py` lines ~1840–1882.  LLM call (streaming).**

`SynthesizeStepExecutor` calls `SynthesizerAgent` to generate the final answer.

**Agent constraints:** `max_context=8192`, `temperature=0.3`,
`reasoning_depth=2`, `reflection_passes=1`, `combine_steps=True`.

**System prompt:** Base synthesis prompt + `_AGENT_RULES_APPENDIX` (loaded from
`prompts/agent_rules.md`).  The synthesis prompt instructs:

1. Verify: Does the answer address the user's ACTUAL question?
2. Is every factual claim grounded in tool outputs?
3. Are there gaps?  State them explicitly.
4. Could the answer be misunderstood?
5. Lead with the most important information.
6. For code: include runnable code, not pseudo-code.
7. End with concrete next steps.

**Task type classification:**
The synthesizer determines a `task_type` string used for reflection thresholds
and section contracts:

| Task Type | Section Contract | Reflection Threshold |
|-----------|-----------------|---------------------|
| `hard_research` | topic-specific sections | 0.75 |
| `research` | topic-specific sections | 0.70 |
| `implementation` | code-specific sections | 0.65 |
| `orchestration` | status sections | 0.60 |
| `general` | *(none — empty tuple)* | 0.35 |
| `trivial` | *(none)* | 0.40 |

**Section contracts:** For non-trivial task types, the synthesizer requires
specific markdown sections (e.g. `## Analysis`, `## Implementation`).
`ReplyShaper.validate_section_contract()` checks that these sections exist
and contain bullet points.  For `general` and `trivial`, no sections are
enforced.

---

## 9. Phase 6 — Reflection

**`agent.py` → `services/reflection_service.py`.  LLM call (conditional).**

If `reflection_enabled=True` (default) and `reflection_passes > 0` (default 1)
and `final_text >= 8 chars`, the `ReflectionService` evaluates the answer.

### 9.1 Scoring

The reflection LLM scores three dimensions:

| Dimension | What it measures |
|-----------|-----------------|
| `goal_alignment` (0.0–1.0) | Does the answer solve the user's actual intent? |
| `completeness` (0.0–1.0) | Are all parts of the question addressed? |
| `factual_grounding` (0.0–1.0) | Are all facts verbatim from tool outputs? |

**Overall score** = weighted combination.

### 9.2 Retry Logic

```
should_retry = (score < effective_threshold) OR hard_factual_fail
hard_factual_fail = (factual_grounding < 0.4)
```

If `should_retry`:
- The reflection issues + suggested fix are fed back as feedback.
- A **re-synthesis** LLM call generates a corrected answer.
- Maximum `reflection_passes` iterations (default 1).

### 9.3 Thresholds by Task Type

```python
_REFLECTION_THRESHOLDS_BY_TASK_TYPE = {
    "hard_research":         0.75,
    "research":              0.70,
    "implementation":        0.65,
    "orchestration":         0.60,
    "orchestration_failed":  0.55,
    "orchestration_pending": 0.55,
    "general":               0.35,
    "trivial":               0.40,
}
```

**Key design decision:** `general` has threshold 0.35 because prose answers
without tool-grounded facts naturally score ~0.4 on `factual_grounding`.
A higher threshold would cause every general-knowledge answer to trigger a
wasteful retry.

### 9.4 Sanitization

Before being fed to the reflection LLM:
- Tool results are capped at `reflection_tool_results_max_chars` (8000).
- Plan text is capped at `reflection_plan_max_chars` (2000).
- Prompt injection patterns are neutralized:
  `r"(?i)(return\s+json|you\s+must|ignore\s+previous|disregard|override|system\s*:)"`

**Lifecycle events:** `reflection_completed` (with score details) /
`reflection_skipped` / `reflection_failed`.

---

## 10. Phase 7 — Evidence Gates & Reply Shaping

**`agent.py` lines ~2725–2824.**

### 10.1 Evidence Gates

Three verification gates can modify or reject the answer:

| Gate | Trigger | Action |
|------|---------|--------|
| Implementation evidence | Code task but no code in answer | Emit `implementation_evidence_missing` warning |
| Orchestration evidence | Orchestration task but no status/results | Emit `orchestration_evidence_missing` warning |
| All-tools-failed | Every tool call errored | Prepend failure notice, emit `all_tools_failed_gate_applied` |

### 10.2 Reply Shaping

`ReplyShaper.shape()` applies these transformations in order:

| # | Transformation | Detail |
|---|---------------|--------|
| 1 | Token removal | Strip `NO_REPLY`, `ANNOUNCE_SKIP` tokens |
| 2 | TOOL_CALL block removal | `r"\[TOOL_CALL\].*?\[/TOOL_CALL\]"` |
| 3 | Tool-hash syntax removal | `r"^\s*\{\s*tool\s*=>[^\n]*\}\s*$"` |
| 4 | Newline collapse | 3+ consecutive newlines → 2 |
| 5 | Deduplication | Remove consecutive "done/completed + tool" ack lines |
| 6 | Suppression check | If only boilerplate ack after tools → suppress entirely |

**Output:** `ReplyShapeResult(text, was_suppressed, suppression_reason,
dedup_lines_removed, removed_tokens)`.

**Lifecycle events:** `reply_shaping_started` → `reply_shaping_completed` /
`reply_suppressed`.

---

## 11. Phase 8 — Response & Distillation

### 11.1 Response

The final answer is sent to the frontend as a WebSocket `final` event:

```json
{
  "type": "final",
  "agent": "head-agent",
  "message": "...",
  "request_id": "uuid",
  "session_id": "sess-123"
}
```

**Lifecycle event:** `run_completed` with timing and phase summary.

### 11.2 Distillation (Background)

If `session_distillation_enabled=True` (default) and the answer has ≥10 chars,
a **non-blocking background task** distills the interaction into long-term
memory.

**Distillation prompt (hard-coded):**
```
Summarize this interaction in 2-3 sentences.
Extract key facts about the user's preferences/project.
Return JSON: {"summary": "...", "key_facts": [{"key": "...", "value": "..."}], "tags": ["..."]}
```

**Storage targets:**
- **Summary** → `_long_term_memory.add_episodic(session_id, summary, outcome="success", tags=tags)`
- **Key facts** → `_long_term_memory.add_semantic(key, value, confidence=0.7, source_sessions=[session_id])`

**This is the final LLM call** and runs in the `finally` block of `run()`,
so it executes even if synthesis/reflection encountered errors.

---

## 12. LLM Call Budget

| Call # | Phase | When | Notes |
|--------|-------|------|-------|
| 1 | Planning | Always | Classifies request, produces plan |
| 2 | Tool selection | If tools needed | Picks tools + args |
| 3* | Tool repair | Only if #2 output is malformed | Extra call, rare |
| 4 | Tool selection (replan) | Only if first tool round failed | Max 1 replan |
| 5 | Synthesis | Always | Generates final answer (streaming) |
| 6 | Reflection | If enabled + non-trivial answer | Scores quality |
| 7 | Re-synthesis | Only if reflection says retry | Corrected answer |
| 8 | Distillation | Background, if enabled | Extracts memories |

**Typical request:** Calls 1, 2, 5, 6, 8 = **5 LLM calls**.
**With tools + no issues:** Calls 1, 2, 5, 6, 8 = **5 LLM calls**.
**Code task with replan:** Calls 1, 2, 4, 5, 6, 8 = **6 LLM calls**.
**Worst case:** Calls 1, 2, 3, 4, 5, 6, 7, 8 = **8 LLM calls**.
**Trivial ("Hi"):** Calls 1, 5, 8 = **3 LLM calls** (no tools, reflection skipped).

---

## 13. Configuration Reference

All settings in `config.py` → `AppSettings`, overridable via environment
variables.

### Core

| Setting | Default | Env Var |
|---------|---------|---------|
| `local_model` | `llama3.3:70b-instruct-q4_K_M` | `LOCAL_MODEL` |
| `api_model` | `minimax-m2:cloud` | `API_MODEL` |
| `max_user_message_length` | 8000 | `MAX_USER_MESSAGE_LENGTH` |

### Reflection

| Setting | Default | Env Var |
|---------|---------|---------|
| `reflection_enabled` | `True` | `REFLECTION_ENABLED` |
| `reflection_threshold` | 0.6 | `REFLECTION_THRESHOLD` |
| `reflection_factual_grounding_hard_min` | 0.4 | `REFLECTION_FACTUAL_GROUNDING_HARD_MIN` |
| `reflection_tool_results_max_chars` | 8000 | `REFLECTION_TOOL_RESULTS_MAX_CHARS` |
| `reflection_plan_max_chars` | 2000 | `REFLECTION_PLAN_MAX_CHARS` |

### Tool Execution

| Setting | Default | Env Var |
|---------|---------|---------|
| `run_tool_call_cap` | 8 | `RUN_TOOL_CALL_CAP` |
| `run_tool_time_cap_seconds` | 90.0 | `RUN_TOOL_TIME_CAP_SECONDS` |
| `tool_result_max_chars` | 6000 | `TOOL_RESULT_MAX_CHARS` |
| `tool_result_smart_truncate_enabled` | `True` | `TOOL_RESULT_SMART_TRUNCATE_ENABLED` |
| `tool_result_context_guard_enabled` | `True` | `TOOL_RESULT_CONTEXT_GUARD_ENABLED` |

### Replanning

| Setting | Default | Env Var |
|---------|---------|---------|
| `run_max_replan_iterations` | 1 | `RUN_MAX_REPLAN_ITERATIONS` |
| `run_empty_tool_replan_max_attempts` | 1 | `RUN_EMPTY_TOOL_REPLAN_MAX_ATTEMPTS` |
| `run_error_tool_replan_max_attempts` | 1 | `RUN_ERROR_TOOL_REPLAN_MAX_ATTEMPTS` |

### Loop Detection

| Setting | Default | Env Var |
|---------|---------|---------|
| `tool_loop_warn_threshold` | 2 | `TOOL_LOOP_WARN_THRESHOLD` |
| `tool_loop_critical_threshold` | 3 | `TOOL_LOOP_CRITICAL_THRESHOLD` |
| `tool_loop_circuit_breaker_threshold` | 6 | `TOOL_LOOP_CIRCUIT_BREAKER_THRESHOLD` |
| `tool_loop_detector_generic_repeat_enabled` | `True` | `TOOL_LOOP_DETECTOR_GENERIC_REPEAT_ENABLED` |
| `tool_loop_detector_ping_pong_enabled` | `True` | `TOOL_LOOP_DETECTOR_PING_PONG_ENABLED` |
| `tool_loop_detector_poll_no_progress_enabled` | `True` | `TOOL_LOOP_DETECTOR_POLL_NO_PROGRESS_ENABLED` |
| `tool_loop_poll_no_progress_threshold` | 3 | `TOOL_LOOP_POLL_NO_PROGRESS_THRESHOLD` |

### Command Safety

| Setting | Default | Env Var |
|---------|---------|---------|
| `command_allowlist_enabled` | `True` | `COMMAND_ALLOWLIST_ENABLED` |
| `command_allowlist` | 43 executables (see §15) | `COMMAND_ALLOWLIST` |
| `command_allowlist_extra` | `[]` | `COMMAND_ALLOWLIST_EXTRA` |

### Distillation

| Setting | Default | Env Var |
|---------|---------|---------|
| `session_distillation_enabled` | `True` | `SESSION_DISTILLATION_ENABLED` |

### Model Scoring

| Setting | Default | Env Var |
|---------|---------|---------|
| `model_score_weight_health` | 100.0 | `MODEL_SCORE_WEIGHT_HEALTH` |
| `model_score_weight_latency` | 0.01 | `MODEL_SCORE_WEIGHT_LATENCY` |
| `model_score_weight_cost` | 10.0 | `MODEL_SCORE_WEIGHT_COST` |
| `model_score_runtime_bonus` | 6.0 | `MODEL_SCORE_RUNTIME_BONUS` |

---

## 14. Lifecycle Events

Every phase emits structured lifecycle events via `_emit_lifecycle()`.
These are forwarded to the frontend as WebSocket `lifecycle` messages and can
be used for debugging, monitoring, and UI state tracking.

### Complete Event Catalog

**Initialization:**
`run_started`, `guardrails_passed`, `tool_policy_resolved`, `toolchain_checked`,
`orphaned_tool_calls_repaired`, `session_history_sanitized`

**Memory & Context:**
`memory_updated`, `context_reduced`, `context_segmented` (×3: planning, tool, synthesis)

**Planning:**
`clarification_auto_resolved`, `clarification_needed`,
`planning_started`, `planning_completed`,
`verification_plan`, `verification_plan_semantic`

**Tool Loop:**
`terminal_wait_started`, `terminal_wait_completed`,
`replanning_started`, `replanning_completed`, `replanning_exhausted`,
`tool_selection_empty`

**Verification:**
`verification_tool_result`, `verification_final`

**Early Exits:**
`response_emitted`, `run_interrupted`, `web_research_sources_unavailable`

**Synthesis:**
`tool_result_context_guard_applied`

**Reflection:**
`reflection_completed`, `reflection_failed`, `reflection_skipped`

**Gates & Shaping:**
`implementation_evidence_missing`, `orchestration_evidence_missing`,
`reply_shaping_started`, `reply_shaping_completed`,
`all_tools_failed_gate_applied`, `reply_suppressed`

**Hooks & MCP:**
`hook_invoked`, `hook_timeout`, `hook_skipped`, `hook_failed`,
`mcp_tools_initialized`, `mcp_tools_failed`

**Completion:**
`run_completed`, `policy_override_decision`

---

## 15. Tool Catalog

**18 tools** defined in `tool_catalog.py`:

| Tool | Category | Shell Required |
|------|----------|---------------|
| `list_dir` | File system | No |
| `read_file` | File system | No |
| `write_file` | File system | No |
| `apply_patch` | File system | No |
| `file_search` | Search | No |
| `grep_search` | Search | No |
| `list_code_usages` | Search | No |
| `get_changed_files` | Git | No |
| `run_command` | Execution | Yes (subprocess) |
| `code_execute` | Execution | Yes (subprocess) |
| `start_background_command` | Execution | Yes (subprocess) |
| `get_background_output` | Execution | No |
| `kill_background_process` | Execution | No |
| `web_search` | Web | No |
| `web_fetch` | Web | No |
| `http_request` | Web | No |
| `analyze_image` | Analysis | No |
| `spawn_subrun` | Orchestration | No |

**Default command allowlist (43 entries):**
`awk`, `cargo`, `cat`, `chmod`, `chown`, `cmake`, `cp`, `docker`,
`docker-compose`, `dotnet`, `git`, `go`, `gradle`, `grep`, `head`, `java`,
`javac`, `ls`, `make`, `mkdir`, `mv`, `mvn`, `node`, `npm`, `npx`, `pip`,
`pnpm`, `py`, `pytest`, `python`, `rg`, `rustc`, `sed`, `sort`, `tail`,
`tar`, `touch`, `uniq`, `unzip`, `uvicorn`, `wc`, `yarn`, `zip`.

**Safety patterns blocked (tools.py):**
`rm -rf`, `del /f`, `format`, `shutdown`, `reboot`, `mkfs`, `dd`,
`chmod 777 /`, pipe-to-shell (`curl|sh`, `wget|sh`), `python -c`,
PowerShell `-enc`, `nc -l`, metadata endpoints, shell chaining
(`||`, `&&`, `;`, backticks, `$()`).

---

## 16. Model Routing

`ModelRegistry` maps model IDs to capability profiles:

| Model | max_context | reasoning_depth | reflection_passes |
|-------|-------------|-----------------|-------------------|
| `llama3.3:70b-instruct-q4_K_M` (local) | 8000 | 2 | 0 |
| `minimax-m2:cloud` (api) | 16000 | 2 | 0 |
| `gpt-oss:20b-cloud` | 24000 | 3 | 1 |
| `qwen3-coder:480b-cloud` | 64000 | 4 | 2 |

**Model scoring formula:**
```
score = health × 100 − latency / 100 − cost × 10 + runtime_bonus
```

---

## 17. Prompt Chain

The system uses two appendix files loaded at startup and injected into
multiple prompts:

### 17.1 `_TOOL_ROUTING_APPENDIX` (from `prompts/tool_routing.md`)

Appended to all **tool selector** system prompts:
- `head_agent_tool_selector_prompt`
- `coder_agent_tool_selector_prompt`
- `agent_tool_selector_prompt`

Contains per-tool routing rules: when to use, when NOT to use, output notes,
and cautions.  Includes platform awareness (shell builtins not available
with `subprocess(shell=False)`).

### 17.2 `_AGENT_RULES_APPENDIX` (from `prompts/agent_rules.md`)

Appended to all **synthesis/final** system prompts:
- `head_agent_final_prompt`
- `coder_agent_final_prompt`
- `agent_final_prompt`

Contains factual grounding rules, tool output usage rules, command execution
safety rules, answer completeness checks, project structure reference,
common operations, and coding style guidelines.

### 17.3 Prompt Resolution

All prompts use the `_resolve_prompt(fallback, *env_keys)` pattern:

```python
head_agent_plan_prompt = _resolve_prompt(
    "You are a planning agent...",              # Fallback
    "HEAD_AGENT_PLAN_PROMPT",                   # First env var to check
    "AGENT_PLAN_PROMPT",                        # Second fallback env var
    "HEAD_AGENT_SYSTEM_PROMPT",                 # Third fallback env var
)
```

First non-empty env var wins; if none set, the hardcoded fallback is used.
