# Pipeline Debugger — Feature Specification

> Interactive visual debugger that makes the entire reasoning pipeline
> observable, pausable, and inspectable.  The user sees the agent walk
> through every phase, reads every prompt and LLM response, and controls
> execution with Play / Pause / Step-Continue.

**Route:** `/debug`
**Component:** `DebugPageComponent` (standalone)
**Status:** Proposed — Implementation Guide

---

## Table of Contents

1. [Vision & Goals](#1-vision--goals)
2. [Acceptance Criteria](#2-acceptance-criteria)
3. [Architecture Overview](#3-architecture-overview)
4. [Backend Changes](#4-backend-changes)
5. [Frontend: Component Tree](#5-frontend-component-tree)
6. [Route & Navigation](#6-route--navigation)
7. [The Canvas — Pipeline Visualizer](#7-the-canvas--pipeline-visualizer)
8. [The Continue Button — Breakpoint System](#8-the-continue-button--breakpoint-system)
9. [Prompt Inspector Panel](#9-prompt-inspector-panel)
10. [Animations & Micro-Interactions](#10-animations--micro-interactions)
11. [State Machine](#11-state-machine)
12. [Data Flow](#12-data-flow)
13. [UX / UI Design Specification](#13-ux--ui-design-specification)
14. [Implementation Plan](#14-implementation-plan)
15. [File Manifest](#15-file-manifest)
16. [Testing Strategy](#16-testing-strategy)

---

## 1. Vision & Goals

### The Problem

The reasoning pipeline makes 5–8 LLM calls per request across 8 phases.
Today, the user only sees the final answer and a flat lifecycle log.
There is no way to:

- See which phase the agent is in right now
- Read the prompts being sent to the LLM
- Read the raw LLM response before post-processing
- Pause execution between phases and inspect state
- Understand *why* the agent chose a specific tool or triggered a replan

### The Solution

A dedicated `/debug` route with a canvas-based pipeline visualization where
the user watches the agent walk through bases (phases) in real time.
Every prompt and response is inspectable, and execution can be paused at
configurable breakpoints.

### Design Principles

| Principle | What it means |
|-----------|---------------|
| **Maximum transparency** | Every LLM call, every prompt, every response — visible |
| **Zero guessing** | If the pipeline does something, the user sees *why* |
| **Non-destructive** | Debug mode adds observability; it never changes the pipeline's logic |
| **Progressive disclosure** | Overview is clean; detail expands on demand |
| **Instant feedback** | Sub-100ms UI response to every pipeline event |

---

## 2. Acceptance Criteria

### Must Have (P0)

| ID | Criterion | Verifiable by |
|----|-----------|---------------|
| AC-01 | `/debug` route loads a standalone `DebugPageComponent` | Navigate to `/debug` in browser |
| AC-02 | Navigation bar shows a "Debug" link next to "Chat" and "Memory" | Visual inspection |
| AC-03 | Canvas displays all 8 pipeline phases as connected nodes (bases) | Visual inspection |
| AC-04 | The currently active phase is highlighted with a pulsing animation | Send a message, observe highlight move |
| AC-05 | An animated agent token moves from base to base as the pipeline progresses | Send a message, watch animation |
| AC-06 | The agent token pauses at an "LLM" interaction node when a prompt is sent | Observe during `planning_started` |
| AC-07 | A **Play** button starts/resumes pipeline execution | Click Play, agent begins |
| AC-08 | A **Pause** button stops the agent at the next phase boundary | Click Pause, agent stops before next phase |
| AC-09 | A **Continue (Step)** button advances exactly one phase then pauses again | Click Continue, observe single-step |
| AC-10 | When paused, a prominent "Continue" button with a keyboard shortcut (`F8` or `Space`) is shown | Observe during pause |
| AC-11 | The Prompt Inspector shows the **system prompt** sent to the LLM for the current phase | Click on an LLM node while in planning phase |
| AC-12 | The Prompt Inspector shows the **user prompt** (assembled context) sent to the LLM | Same as above |
| AC-13 | The Prompt Inspector shows the **raw LLM response** before post-processing | After LLM responds |
| AC-14 | The Prompt Inspector shows the **post-processed output** (parsed plan, JSON actions, shaped text) | After post-processing |
| AC-15 | Tool execution details (tool name, args, result, duration) are visible when the tool loop node is active | During tool execution |
| AC-16 | Reflection score (goal_alignment, completeness, factual_grounding, should_retry) is displayed | After reflection phase |
| AC-17 | All existing lifecycle events are rendered as small event pills on the canvas edges | Throughout execution |
| AC-18 | The debug mode uses the same WebSocket connection as the chat page | Network tab shows single WS connection |
| AC-19 | The user can type a message directly in the debug page (built-in composer) | Type message, press Enter |
| AC-20 | All CSS follows the existing design system (CSS custom properties, dark theme) | Visual inspection |

### Should Have (P1)

| ID | Criterion | Verifiable by |
|----|-----------|---------------|
| AC-21 | Breakpoint toggles on individual phase nodes — click a node to toggle breakpoint marker | Click node, see breakpoint dot |
| AC-22 | A timeline scrubber at the bottom lets the user replay past events | Drag scrubber after run completes |
| AC-23 | Phase durations are displayed on the canvas edges (e.g. "1.2s") | After each phase completes |
| AC-24 | A "Token Stream" sub-panel shows streaming tokens during synthesis | During synthesis phase |
| AC-25 | Keyboard shortcuts: `F5` = Play, `F6` = Pause, `F8` = Continue, `F9` = Toggle breakpoint | Key press test |
| AC-26 | Mobile-responsive layout collapses canvas to vertical flow | Resize to <768px |
| AC-27 | Context budget visualization shows the token allocation pie chart | During context_segmented events |
| AC-28 | An export button saves the full debug trace as JSON | Click export, verify download |

### Nice to Have (P2)

| ID | Criterion | Verifiable by |
|----|-----------|---------------|
| AC-29 | A diff view shows the before/after of reflection-triggered re-synthesis | After reflection retry |
| AC-30 | Audio cue (subtle click) when agent arrives at a new base | Enable sound, listen |
| AC-31 | Shareable debug URL with run_id query parameter to replay a specific run | Open URL in new tab |

---

## 3. Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                     DebugPageComponent                       │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                    Debug Toolbar                         │ │
│  │  [▶ Play] [⏸ Pause] [▶▶ Continue] [● Breakpoints ▾]    │ │
│  │  [Session: ___________] [Agent: ▾] [Model: ▾]          │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────┐  ┌──────────────────────────┐│
│  │                            │  │    Prompt Inspector       ││
│  │     Pipeline Canvas        │  │                          ││
│  │                            │  │  ┌─ System Prompt ─────┐ ││
│  │   ○ Routing                │  │  │ You are a planning  │ ││
│  │   │                        │  │  │ agent. Your job...   │ ││
│  │   ◉ Guardrails ✓           │  │  └─────────────────────┘ ││
│  │   │                        │  │                          ││
│  │   ○ Memory ──────┐        │  │  ┌─ User Prompt ────────┐ ││
│  │   │              │        │  │  │ Create a REST API    │ ││
│  │   ◉ Planning ◄───┘ ☁ LLM │  │  │ for user management  │ ││
│  │   │        └─── 1.2s      │  │  └─────────────────────┘ ││
│  │   ○ Tool Loop              │  │                          ││
│  │   │   ├ list_dir ✓        │  │  ┌─ LLM Response ───────┐ ││
│  │   │   ├ read_file ✓       │  │  │ CLASSIFY: complex    │ ││
│  │   │   └ grep_search ✓    │  │  │ Step 1: list_dir ... │ ││
│  │   ○ Synthesis ◄──── ☁ LLM│  │  └─────────────────────┘ ││
│  │   │                        │  │                          ││
│  │   ○ Reflection ◄─── ☁ LLM│  │  ┌─ Parsed Output ──────┐ ││
│  │   │                        │  │  │ task_type: "impl"    │ ││
│  │   ○ Reply Shaping          │  │  │ steps: [...]         │ ││
│  │   │                        │  │  └─────────────────────┘ ││
│  │   ◉ Response ✓             │  │                          ││
│  │                            │  │  ── Event Log ─────────  ││
│  │  [═══════════●════] 12/18 │  │  10:03.1 planning_start  ││
│  │     Timeline Scrubber      │  │  10:04.3 planning_done   ││
│  └────────────────────────────┘  │  10:04.4 tool_sel_start  ││
│                                  └──────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                      Composer                            │ │
│  │  [Type a message to debug...                    ] [Send] │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Backend Changes

### 4.1 New Lifecycle Events

Add these stages to `build_lifecycle_event` calls in `agent.py` and
register them in the `LifecycleStage` enum / monitoring schema:

| New Stage | Emitted At | Details Payload |
|-----------|-----------|-----------------|
| `debug_prompt_sent` | Before each `client.complete_chat()` call | `{ "phase": "planning\|tool_selection\|tool_repair\|synthesis\|reflection\|distillation", "system_prompt": "<full text>", "user_prompt": "<full text>", "model": "...", "temperature": 0.3 }` |
| `debug_llm_response` | After each `client.complete_chat()` returns | `{ "phase": "...", "raw_response": "<full text>", "latency_ms": 1234, "tokens_est": 580 }` |
| `debug_post_processed` | After parsing/shaping the LLM output | `{ "phase": "...", "parsed_output": "<JSON or text>", "transform": "plan_parse\|action_parse\|section_contract\|reflection_parse" }` |
| `debug_breakpoint_hit` | When pipeline reaches a phase with a breakpoint | `{ "phase": "...", "breakpoint_id": "bp-planning" }` |
| `tool_execution_detail` | Per tool call in the tool loop | `{ "tool": "read_file", "args": {...}, "result_preview": "<first 500 chars>", "duration_ms": 45, "exit_code": 0, "blocked": false }` |
| `context_budget_detail` | Alongside `context_segmented` | `{ "phase": "...", "total_budget": 4096, "segments": { "system": { "chars": 2048, "tokens_est": 512, "pct": 18 }, ... } }` |

### 4.2 Debug Mode Gate

All `debug_*` stages are **gated behind `DEBUG_MODE=true`** to avoid
payload bloat in production.  The gate is a single check in `_emit_lifecycle`:

```python
# agent.py — _emit_lifecycle
async def _emit_lifecycle(self, send_event, stage, request_id, session_id, details=None):
    # Gate: debug_* events only when DEBUG_MODE is active
    if stage.startswith("debug_") and not settings.debug_mode:
        return
    await send_event(build_lifecycle_event(...))
```

### 4.3 Breakpoint / Pause Hook

The pipeline needs a **cooperative pause mechanism**.  Since Python is
async, we use an `asyncio.Event` that the `run()` method awaits at each
phase boundary.

```python
# agent.py — new instance attributes
self._debug_continue_event: asyncio.Event = asyncio.Event()
self._debug_continue_event.set()  # Default: not paused
self._debug_breakpoints: set[str] = set()  # Phase names to pause at
self._debug_mode_active: bool = False
```

```python
# agent.py — new method
async def _debug_checkpoint(
    self,
    phase: str,
    send_event: SendEvent,
    request_id: str,
    session_id: str,
) -> None:
    """Cooperative pause point.  If the phase has a breakpoint or
    the user pressed Pause, wait for a 'continue' signal."""
    if not self._debug_mode_active:
        return
    if phase not in self._debug_breakpoints and self._debug_continue_event.is_set():
        return  # No breakpoint, not paused → continue

    self._debug_continue_event.clear()
    await self._emit_lifecycle(
        send_event, "debug_breakpoint_hit", request_id, session_id,
        details={"phase": phase, "breakpoint_id": f"bp-{phase}"},
    )
    # Block until frontend sends 'continue' via WebSocket
    await self._debug_continue_event.wait()
```

**Checkpoint insertion points in `run()`:**

```python
# After guardrails (line ~646)
await self._debug_checkpoint("guardrails", send_event, request_id, session_id)

# After memory/context (line ~851)
await self._debug_checkpoint("context", send_event, request_id, session_id)

# Before planning LLM call (line ~815)
await self._debug_checkpoint("planning", send_event, request_id, session_id)

# Before each tool selection LLM call (line ~907)
await self._debug_checkpoint("tool_selection", send_event, request_id, session_id)

# Before synthesis LLM call (line ~1265)
await self._debug_checkpoint("synthesis", send_event, request_id, session_id)

# Before reflection LLM call (line ~1281)
await self._debug_checkpoint("reflection", send_event, request_id, session_id)

# Before reply shaping (line ~1386)
await self._debug_checkpoint("reply_shaping", send_event, request_id, session_id)
```

### 4.4 New WebSocket Message Types

**Inbound (frontend → backend):**

```json
{ "type": "debug_continue", "request_id": "..." }
```
→ Sets `_debug_continue_event`, unblocking the pipeline.

```json
{ "type": "debug_set_breakpoints", "breakpoints": ["planning", "tool_selection", "synthesis"] }
```
→ Updates `_debug_breakpoints` set.

```json
{ "type": "debug_pause" }
```
→ Clears `_debug_continue_event`, causing next checkpoint to block.

```json
{ "type": "debug_play" }
```
→ Sets `_debug_continue_event` + clears all breakpoints → free-running.

**Add to `WsInboundEnvelope`:**

```python
class WsInboundEnvelope(BaseModel):
    # ... existing fields ...
    breakpoints: list[str] | None = Field(default=None, max_length=20)
```

**Add to `ws_handler.py` message dispatch:**

```python
elif msg_type == "debug_continue":
    agent._debug_continue_event.set()
elif msg_type == "debug_pause":
    agent._debug_continue_event.clear()
elif msg_type == "debug_set_breakpoints":
    agent._debug_breakpoints = set(envelope.breakpoints or [])
elif msg_type == "debug_play":
    agent._debug_breakpoints.clear()
    agent._debug_continue_event.set()
```

### 4.5 Prompt Emission Points

Insert `debug_prompt_sent` + `debug_llm_response` around every
`client.complete_chat()` call.  There are **6 call sites**:

| # | Location | Phase String |
|---|----------|-------------|
| 1 | `planner_agent.py` → `_plan()` | `"planning"` |
| 2 | `tool_selector_agent.py` → `_select()` | `"tool_selection"` |
| 3 | `tool_selector_agent.py` → repair call | `"tool_repair"` |
| 4 | `synthesizer_agent.py` → `_synthesize()` | `"synthesis"` |
| 5 | `reflection_service.py` → `reflect()` | `"reflection"` |
| 6 | `agent.py` → `_distill_session_knowledge()` | `"distillation"` |

**Implementation pattern** (same at each site):

```python
if settings.debug_mode:
    await self._emit_lifecycle(send_event, "debug_prompt_sent", request_id, session_id, {
        "phase": "planning",
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "model": model,
        "temperature": temperature,
    })

raw_response = await self.client.complete_chat(
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    model=model,
    temperature=temperature,
)

if settings.debug_mode:
    await self._emit_lifecycle(send_event, "debug_llm_response", request_id, session_id, {
        "phase": "planning",
        "raw_response": raw_response,
        "latency_ms": int((time.monotonic() - t0) * 1000),
    })
```

**Challenge:** Sub-agents don't currently have access to `send_event`.
The `send_event` callback must be threaded through the step executor → agent
method.  This is already the pattern for `ToolStepExecutor` — extend it to
`PlannerStepExecutor` and `SynthesizeStepExecutor`.

---

## 5. Frontend: Component Tree

```
DebugPageComponent (standalone, route: /debug)
├── DebugToolbarComponent
│   ├── Play / Pause / Continue buttons
│   ├── Breakpoint manager dropdown
│   ├── Session ID input
│   ├── Agent selector
│   └── Model selector
├── PipelineCanvasComponent
│   ├── PhaseNodeComponent (×8, one per pipeline phase)
│   │   ├── Phase icon + label
│   │   ├── Status indicator (idle / active / done / error)
│   │   ├── Breakpoint marker (red dot)
│   │   ├── Duration badge
│   │   └── LLM interaction indicator (cloud icon)
│   ├── AgentTokenComponent (animated avatar)
│   ├── EdgeComponent (connecting lines with event pills)
│   └── TimelineScrubberComponent
├── PromptInspectorComponent
│   ├── Tab: System Prompt
│   ├── Tab: User Prompt (assembled context)
│   ├── Tab: LLM Response (raw)
│   ├── Tab: Parsed Output (post-processed)
│   ├── Tab: Tool Details (during tool loop)
│   └── Tab: Reflection Score (during reflection)
├── EventLogComponent
│   └── Filterable lifecycle event stream
└── DebugComposerComponent
    ├── Message textarea
    └── Send button
```

---

## 6. Route & Navigation

### 6.1 Route Registration

```typescript
// app.routes.ts
import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '',       loadComponent: () => import('./pages/chat-page.component').then(m => m.ChatPageComponent) },
  { path: 'memory', loadComponent: () => import('./pages/memory-page.component').then(m => m.MemoryPageComponent) },
  { path: 'debug',  loadComponent: () => import('./pages/debug-page/debug-page.component').then(m => m.DebugPageComponent) },
  { path: '**',     redirectTo: '' },
];
```

### 6.2 Navigation Bar Update

Add to `app.html`:

```html
<!-- Existing nav links -->
<a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{exact: true}">Chat</a>
<a routerLink="/memory" routerLinkActive="active">Memory</a>

<!-- New: Debug link -->
<a routerLink="/debug" routerLinkActive="active" class="nav-debug">
  <span class="debug-icon">⚙</span> Debug
</a>
```

---

## 7. The Canvas — Pipeline Visualizer

### 7.1 Layout

The canvas renders 8 phase nodes in a **vertical flow** (top to bottom),
connected by edges.  LLM interaction points branch to the right from
phases that make LLM calls.

```
        Pipeline                  LLM Interactions
        ────────                  ────────────────

    ┌─────────────┐
    │  0. Routing  │
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │ 1. Guard-   │
    │    rails    │
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │ 2. Memory   │
    │  & Context  │
    └──────┬──────┘
           │
    ┌──────▼──────┐        ┌─────────┐
    │ 3. Planning │───────▶│ ☁ LLM  │
    │             │◀───────│  #1     │
    └──────┬──────┘  1.2s  └─────────┘
           │
    ┌──────▼──────┐        ┌─────────┐
    │ 4. Tool     │───────▶│ ☁ LLM  │
    │    Loop     │◀───────│  #2     │
    │  ┌────┐     │        └─────────┘
    │  │ 🔧 │×3   │
    │  └────┘     │
    └──────┬──────┘
           │
    ┌──────▼──────┐        ┌─────────┐
    │ 5. Synthe-  │───────▶│ ☁ LLM  │
    │    sis      │◀───────│  #3     │
    └──────┬──────┘        └─────────┘
           │
    ┌──────▼──────┐        ┌─────────┐
    │ 6. Reflec-  │───────▶│ ☁ LLM  │
    │    tion     │◀───────│  #4     │
    └──────┬──────┘        └─────────┘
           │
    ┌──────▼──────┐
    │ 7. Reply    │
    │   Shaping   │
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │ 8. Response │
    │  + Distill  │
    └─────────────┘
```

### 7.2 Node States

Each `PhaseNodeComponent` has five visual states:

| State | Visual | CSS Class |
|-------|--------|-----------|
| `idle` | Dimmed border, muted icon | `.phase--idle` |
| `active` | Gold pulsing border, bright icon, glow shadow | `.phase--active` |
| `paused` | Gold border + amber pause overlay | `.phase--paused` |
| `completed` | Green checkmark, solid border | `.phase--completed` |
| `error` | Red border, error icon | `.phase--error` |
| `skipped` | Dashed border, strikethrough label | `.phase--skipped` |

### 7.3 Agent Token

A small animated avatar that moves along the edges between nodes.
Implemented with CSS `transition` on `transform: translateY()`:

```scss
.agent-token {
  position: absolute;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--c-gold);
  box-shadow:
    0 0 12px var(--c-gold-dim),
    0 0 24px rgba(255, 217, 102, 0.15);
  transition: transform 600ms cubic-bezier(0.34, 1.56, 0.64, 1);
  z-index: 10;

  &::after {
    content: '⚡';
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    font-size: 16px;
  }

  &.at-llm {
    background: var(--c-blue);
    box-shadow: 0 0 16px var(--c-blue-dim);
    animation: llm-pulse 1.5s ease-in-out infinite;
  }

  &.paused {
    animation: paused-breathe 2s ease-in-out infinite;
  }
}
```

### 7.4 Edge Event Pills

Small pills rendered on the connecting edges showing lifecycle events:

```html
<div class="edge-pill" [class.pill--start]="event.phase === 'start'"
     [class.pill--end]="event.phase === 'end'"
     [class.pill--error]="event.phase === 'error'"
     [title]="event.stage">
  {{ event.stage | truncate:20 }}
</div>
```

### 7.5 Canvas Implementation

**Technology choice: CSS Grid + absolute positioning** (no canvas/WebGL).

Rationale:
- Pipeline is a fixed-shape graph (linear + LLM branches), not a
  freeform node editor.
- CSS transitions are smoother and more accessible than canvas animations.
- DOM nodes allow native tooltips, focus management, and screen readers.
- Consistent with the existing SCSS design system.

```scss
.pipeline-canvas {
  display: grid;
  grid-template-columns: 280px 120px 220px;  // phases | edges | LLM nodes
  grid-template-rows: repeat(9, auto);
  gap: 8px 0;
  padding: 24px;
  position: relative;                         // for agent token positioning
  min-height: 100%;

  // Connecting lines drawn with ::before pseudo-elements
  // on edge cells using border-left + border-radius
}
```

---

## 8. The Continue Button — Breakpoint System

### 8.1 User-Facing Controls

```
┌─────────────────────────────────────────────────────┐
│                    Debug Toolbar                     │
│                                                     │
│  [ ▶ Play ]  [ ⏸ Pause ]  [ ▶▶ Continue (F8) ]     │
│                                                     │
│  Breakpoints:  ○ Planning  ● Tool Loop  ○ Synthesis │
│                ○ Reflection  ○ Reply Shaping         │
└─────────────────────────────────────────────────────┘
```

### 8.2 Behavior Matrix

| User Action | Pipeline State | Result |
|-------------|---------------|--------|
| Press **Play** | Idle | Sends message, all breakpoints cleared, runs to completion |
| Press **Play** | Paused | Clears all breakpoints, resumes to completion |
| Press **Pause** | Running | Pauses at next phase boundary |
| Press **Continue** | Paused at breakpoint | Advances to next breakpoint (or completion if none) |
| Press **Continue** | Idle | No effect |
| Toggle breakpoint | Any | Adds/removes phase from breakpoint set |
| Click phase node | Any | Toggles breakpoint on that phase + shows its data in inspector |

### 8.3 The Prominent Continue Button

When the pipeline is paused, a **full-width banner** appears above the
composer:

```
┌─────────────────────────────────────────────────────┐
│  ⏸  Paused at: Planning                            │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │          ▶▶  Continue  (F8 / Space)           │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  Phase 3 of 8  ·  1 LLM call completed  ·  0.8s    │
└─────────────────────────────────────────────────────┘
```

```scss
.pause-banner {
  position: sticky;
  bottom: 0;
  padding: 20px 24px;
  background: linear-gradient(
    135deg,
    rgba(255, 217, 102, 0.08) 0%,
    rgba(10, 22, 46, 0.95) 100%
  );
  border-top: 2px solid var(--c-gold-border);
  backdrop-filter: blur(12px);
  animation: banner-slide-up 300ms cubic-bezier(0.16, 1, 0.3, 1);
  z-index: 20;

  .continue-btn {
    width: 100%;
    padding: 14px 32px;
    font-size: 16px;
    font-weight: 600;
    letter-spacing: 0.5px;
    color: var(--c-bg);
    background: var(--c-gold);
    border: none;
    border-radius: var(--r-md);
    cursor: pointer;
    transition: transform 120ms ease, box-shadow 120ms ease;

    &:hover {
      transform: translateY(-1px);
      box-shadow: 0 6px 20px rgba(255, 217, 102, 0.35);
    }

    &:active {
      transform: translateY(0);
    }

    &:focus-visible {
      outline: 2px solid var(--c-gold);
      outline-offset: 3px;
    }
  }
}

@keyframes banner-slide-up {
  from { transform: translateY(100%); opacity: 0; }
  to   { transform: translateY(0);    opacity: 1; }
}
```

### 8.4 Keyboard Shortcuts

```typescript
@HostListener('document:keydown', ['$event'])
handleKeyboard(event: KeyboardEvent): void {
  if (event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLInputElement) {
    return; // Don't capture when typing in composer
  }

  switch (event.key) {
    case 'F5':
      event.preventDefault();
      this.play();
      break;
    case 'F6':
      event.preventDefault();
      this.pause();
      break;
    case 'F8':
    case ' ':
      event.preventDefault();
      this.continue();
      break;
    case 'F9':
      event.preventDefault();
      this.toggleBreakpointOnActivePhase();
      break;
  }
}
```

---

## 9. Prompt Inspector Panel

### 9.1 Layout

The right panel is a tabbed inspector that updates as the pipeline progresses.
It shows the **currently selected or most recent phase's** prompt data.

### 9.2 Tabs

| Tab | Content | Source Event |
|-----|---------|--------------|
| **System Prompt** | The full system prompt sent to the LLM, syntax-highlighted | `debug_prompt_sent.system_prompt` |
| **User Prompt** | The assembled user prompt with context segments marked | `debug_prompt_sent.user_prompt` |
| **LLM Response** | The raw text returned by the LLM | `debug_llm_response.raw_response` |
| **Parsed Output** | Post-processed structure (plan JSON, action array, shaped text) | `debug_post_processed.parsed_output` |
| **Tool Details** | Table of tool calls with args, results, durations | `tool_execution_detail` events |
| **Reflection** | Score card with progress bars for each dimension | `reflection_completed` event |

### 9.3 Prompt Display Component

```html
<div class="prompt-display">
  <div class="prompt-header">
    <span class="prompt-label">System Prompt</span>
    <span class="prompt-meta">{{ phase }} · {{ charCount | number }} chars · {{ tokenEst }} tokens</span>
    <button class="copy-btn" (click)="copyToClipboard(content)">Copy</button>
  </div>
  <pre class="prompt-content"><code [innerHTML]="content | syntaxHighlight"></code></pre>
</div>
```

### 9.4 Syntax Highlighting

A lightweight pipe that highlights:
- **Markdown headers** (`## ...`) in gold
- **Code blocks** in blue
- **JSON keys** in green
- **Numbers** in cyan
- **"SEARCH/REPLACE" blocks** in red/green diff style

No external library — 15 regex rules in a pure pipe, consistent with the
design system colors.

### 9.5 Reflection Score Card

```html
<div class="reflection-card">
  <div class="score-row">
    <span class="score-label">Goal Alignment</span>
    <div class="score-bar">
      <div class="score-fill" [style.width.%]="goalAlignment * 100"
           [class.score--good]="goalAlignment >= 0.6"
           [class.score--warn]="goalAlignment >= 0.4 && goalAlignment < 0.6"
           [class.score--bad]="goalAlignment < 0.4">
      </div>
    </div>
    <span class="score-value">{{ goalAlignment | number:'1.2-2' }}</span>
  </div>
  <!-- Same for completeness, factualGrounding -->

  <div class="verdict-row">
    <span class="verdict" [class.verdict--retry]="shouldRetry"
          [class.verdict--pass]="!shouldRetry">
      {{ shouldRetry ? '⟳ Retry triggered' : '✓ Accepted' }}
    </span>
    <span class="threshold">Threshold: {{ threshold | number:'1.2-2' }}</span>
  </div>
</div>
```

---

## 10. Animations & Micro-Interactions

### 10.1 Animation Catalog

| Animation | Trigger | Duration | Easing |
|-----------|---------|----------|--------|
| **Agent token moves** | Pipeline enters next phase | 600ms | `cubic-bezier(0.34, 1.56, 0.64, 1)` (overshoot) |
| **Phase node pulse** | Phase becomes active | Infinite loop, 2s cycle | `ease-in-out` |
| **LLM cloud glow** | Prompt sent to LLM | Infinite until response, 1.5s cycle | `ease-in-out` |
| **Breakpoint dot throb** | Breakpoint set on phase | Infinite, 1.8s cycle | `ease-in-out` |
| **Pause banner slide-up** | Pipeline paused | 300ms | `cubic-bezier(0.16, 1, 0.3, 1)` (spring) |
| **Event pill fade-in** | New lifecycle event | 200ms | `ease-out` |
| **Phase check-in** | Phase completes | 400ms | `cubic-bezier(0.34, 1.56, 0.64, 1)` (bounce) |
| **Error shake** | Phase errors | 400ms, 3 oscillations | `ease-in-out` |
| **Tool chip appear** | Tool starts execution | 250ms | `ease-out` |
| **Score bar fill** | Reflection scores display | 800ms | `ease-out` |
| **Token stream characters** | Synthesis streaming | Per-character, 16ms | `linear` |
| **Continue button press** | User clicks continue | 120ms scale down → up | `ease` |
| **Inspector tab switch** | Tab clicked | 200ms crossfade | `ease` |

### 10.2 CSS Keyframe Definitions

```scss
// Phase node active pulse
@keyframes phase-pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 var(--c-gold-dim);
    border-color: var(--c-gold-border);
  }
  50% {
    box-shadow: 0 0 20px 4px var(--c-gold-dim);
    border-color: var(--c-gold);
  }
}

// LLM cloud glow during inference
@keyframes llm-pulse {
  0%, 100% {
    box-shadow: 0 0 8px var(--c-blue-dim);
    opacity: 0.85;
  }
  50% {
    box-shadow: 0 0 24px var(--c-blue-dim), 0 0 48px rgba(59, 127, 255, 0.12);
    opacity: 1;
  }
}

// Paused agent token breathing
@keyframes paused-breathe {
  0%, 100% { transform: scale(1);   opacity: 0.9; }
  50%      { transform: scale(1.1); opacity: 1;   }
}

// Breakpoint red dot throb
@keyframes bp-throb {
  0%, 100% { transform: scale(1);   box-shadow: 0 0 4px var(--c-red-dim); }
  50%      { transform: scale(1.3); box-shadow: 0 0 12px var(--c-red-dim); }
}

// Phase completion checkmark bounce
@keyframes check-bounce {
  0%   { transform: scale(0); }
  60%  { transform: scale(1.2); }
  100% { transform: scale(1); }
}

// Error shake
@keyframes error-shake {
  0%, 100% { transform: translateX(0); }
  25%      { transform: translateX(-4px); }
  75%      { transform: translateX(4px); }
}

// Score bar fill
@keyframes bar-fill {
  from { width: 0; }
}

// Fade in for event pills
@keyframes pill-fade-in {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

### 10.3 Reduced Motion Support

```scss
@media (prefers-reduced-motion: reduce) {
  .agent-token,
  .phase-node,
  .pause-banner,
  .score-fill {
    animation: none !important;
    transition-duration: 0ms !important;
  }
}
```

---

## 11. State Machine

The debug page operates as a finite state machine:

```
                ┌──────────────┐
       ┌───────▶│     IDLE     │◀──────────────┐
       │        │  No run      │               │
       │        └──────┬───────┘               │
       │               │ user sends message    │
       │               ▼                       │
       │        ┌──────────────┐               │
       │   ┌───▶│   RUNNING    │───┐           │
       │   │    │  Pipeline    │   │           │
       │   │    │  executing   │   │           │
       │   │    └──────┬───────┘   │           │
       │   │           │           │           │
       │   │    Pause  │  Breakpoint hit       │
       │   │    pressed│           │           │
       │   │           ▼           ▼           │
       │   │    ┌──────────────┐               │
       │   │    │    PAUSED    │               │
       │   │    │  Waiting for │               │
       │   │    │  Continue    │               │
       │   │    └──────┬───────┘               │
       │   │           │                       │
       │   │    Continue pressed               │
       │   │           │                       │
       │   └───────────┘                       │
       │                                       │
       │        ┌──────────────┐               │
       │        │  COMPLETED   │───────────────┘
       │        │  Run done    │   auto-reset
       │        └──────────────┘   after 2s
       │
       │        ┌──────────────┐
       └────────│    ERROR     │
                │  Run failed  │
                └──────────────┘
```

### TypeScript Definition

```typescript
type DebugState = 'idle' | 'running' | 'paused' | 'completed' | 'error';

interface DebugContext {
  state: DebugState;
  currentPhase: PipelinePhase | null;
  activeBreakpoints: Set<PipelinePhase>;
  phaseStates: Map<PipelinePhase, PhaseState>;
  llmCalls: LlmCallRecord[];
  toolExecutions: ToolExecutionRecord[];
  reflectionVerdict: ReflectionVerdict | null;
  eventLog: DebugEvent[];
  pausedAtPhase: PipelinePhase | null;
  totalDurationMs: number;
  requestId: string | null;
}

type PipelinePhase =
  | 'routing'
  | 'guardrails'
  | 'context'
  | 'planning'
  | 'tool_selection'
  | 'tool_execution'
  | 'synthesis'
  | 'reflection'
  | 'reply_shaping'
  | 'response';

type PhaseState = 'idle' | 'active' | 'paused' | 'completed' | 'error' | 'skipped';

interface LlmCallRecord {
  phase: PipelinePhase;
  systemPrompt: string;
  userPrompt: string;
  rawResponse: string;
  parsedOutput: string;
  model: string;
  temperature: number;
  latencyMs: number;
  tokensEst: number;
  timestamp: string;
}

interface ToolExecutionRecord {
  tool: string;
  args: Record<string, unknown>;
  resultPreview: string;
  durationMs: number;
  exitCode: number;
  blocked: boolean;
  timestamp: string;
}

interface ReflectionVerdict {
  goalAlignment: number;
  completeness: number;
  factualGrounding: number;
  score: number;
  shouldRetry: boolean;
  hardFactualFail: boolean;
  issues: string[];
  suggestedFix: string | null;
  threshold: number;
}
```

---

## 12. Data Flow

### 12.1 Message Lifecycle in Debug Mode

```
User types message in DebugComposer
        │
        ▼
DebugPageComponent.sendDebugMessage()
  ├── Sets state = 'running'
  ├── Sends breakpoints via WS: { type: "debug_set_breakpoints", breakpoints: [...] }
  └── Sends message via AgentSocketService.sendUserMessage()
        │
        ▼
Backend receives message, starts run()
        │
        ├──▸ _emit_lifecycle("run_started", ...)
        │        │
        │        ▼  WebSocket → Frontend
        │    applyDebugEvent(): state = 'running', activatePhase('routing')
        │
        ├──▸ _debug_checkpoint("guardrails", ...)
        │        │ breakpoint set? → emit debug_breakpoint_hit → wait
        │        │                    │
        │        │                    ▼  WebSocket → Frontend
        │        │               applyDebugEvent(): state = 'paused'
        │        │               Show Continue banner
        │        │                    │
        │        │               User presses Continue
        │        │                    │
        │        │                    ▼  WebSocket ← Frontend
        │        │               { type: "debug_continue" }
        │        │                    │
        │        ◀────────────────────┘ _debug_continue_event.set()
        │
        ├──▸ debug_prompt_sent (phase: "planning")
        │        │
        │        ▼  WebSocket → Frontend
        │    applyDebugEvent(): store LLM call record, update inspector
        │
        ├──▸ debug_llm_response (phase: "planning")
        │        │
        │        ▼  WebSocket → Frontend
        │    applyDebugEvent(): complete LLM call record, show response
        │
        ├──▸ debug_post_processed (phase: "planning")
        │        │
        │        ▼  WebSocket → Frontend
        │    applyDebugEvent(): show parsed plan in inspector
        │
        ├──▸ ... (tool selection, tool execution, synthesis, reflection) ...
        │
        └──▸ _emit_lifecycle("run_completed", ...)
                 │
                 ▼  WebSocket → Frontend
            applyDebugEvent(): state = 'completed'
```

### 12.2 Event Routing in Component

```typescript
private applyDebugEvent(event: AgentSocketEvent): void {
  // Always log
  this.debugContext.eventLog.push(this.toDebugEvent(event));

  // Route by event type + stage
  switch (event.type) {
    case 'lifecycle':
      this.handleLifecycleEvent(event);
      break;
  }

  // Route by stage
  switch (event.stage) {
    case 'run_started':
      this.transitionTo('running');
      this.activatePhase('routing');
      break;

    case 'guardrails_passed':
      this.completePhase('guardrails');
      break;

    case 'planning_started':
      this.activatePhase('planning');
      break;

    case 'planning_completed':
      this.completePhase('planning');
      break;

    case 'debug_prompt_sent':
      this.recordPromptSent(event.details as DebugPromptSent);
      break;

    case 'debug_llm_response':
      this.recordLlmResponse(event.details as DebugLlmResponse);
      break;

    case 'debug_post_processed':
      this.recordPostProcessed(event.details as DebugPostProcessed);
      break;

    case 'debug_breakpoint_hit':
      this.transitionTo('paused');
      this.setPausedAtPhase(event.details?.phase as PipelinePhase);
      break;

    case 'tool_started':
      this.activatePhase('tool_execution');
      this.addToolExecution(event.details as ToolExecutionDetail);
      break;

    case 'tool_completed':
    case 'tool_failed':
      this.updateToolExecution(event.details as ToolExecutionDetail);
      break;

    case 'reflection_completed':
      this.setReflectionVerdict(event.details as ReflectionVerdict);
      this.completePhase('reflection');
      break;

    case 'reflection_skipped':
      this.skipPhase('reflection');
      break;

    case 'run_completed':
      this.transitionTo('completed');
      break;
  }
}
```

---

## 13. UX / UI Design Specification

### 13.1 Color Palette (extending existing design system)

```scss
// New debug-specific tokens (added to styles.scss)
--c-debug-bg: rgba(8, 16, 32, 0.92);
--c-debug-surface: rgba(12, 24, 48, 0.85);

// Phase state colors
--c-phase-idle: var(--c-text-muted);       // #4e6a96
--c-phase-active: var(--c-gold);            // #ffd966
--c-phase-completed: var(--c-green);        // #4de88a
--c-phase-error: var(--c-red);              // #ff7575
--c-phase-skipped: var(--c-text-muted);
--c-phase-paused: #ffb347;                  // Amber

// LLM interaction
--c-llm-node: var(--c-blue);                // #3b7fff
--c-llm-glow: rgba(59, 127, 255, 0.25);

// Breakpoint
--c-bp-dot: #ff4444;
--c-bp-glow: rgba(255, 68, 68, 0.3);

// Inspector
--c-inspector-bg: rgba(6, 13, 26, 0.95);
--c-inspector-border: rgba(255, 217, 102, 0.12);
--c-code-bg: rgba(0, 0, 0, 0.3);
```

### 13.2 Typography

```scss
.debug-page {
  // Phase labels
  .phase-label {
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.4px;
    text-transform: uppercase;
  }

  // Inspector content
  .prompt-content {
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
    font-size: 12px;
    line-height: 1.6;
    tab-size: 2;
  }

  // Event log
  .event-text {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--c-text-dim);
  }

  // Duration badges
  .duration-badge {
    font-size: 10px;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
  }
}
```

### 13.3 Layout Grid

```scss
.debug-page {
  display: grid;
  grid-template-rows: 52px 1fr auto;     // toolbar | workspace | composer
  height: 100vh;
  overflow: hidden;

  .debug-workspace {
    display: grid;
    grid-template-columns: 1fr 1fr;       // canvas | inspector
    gap: 1px;
    background: rgba(255, 217, 102, 0.06); // subtle gap line
    overflow: hidden;
  }
}
```

### 13.4 Responsive Breakpoints

```scss
// Tablet (< 1024px)
@media (max-width: 1024px) {
  .debug-workspace {
    grid-template-columns: 1fr;
    grid-template-rows: 1fr 1fr;
  }
}

// Mobile (< 768px)
@media (max-width: 768px) {
  .pipeline-canvas {
    grid-template-columns: 1fr;   // Stacked vertically
    .llm-branch { display: none; } // Hide LLM nodes, show inline
    .phase-node { flex-direction: column; }
  }

  .debug-toolbar {
    flex-wrap: wrap;
    .toolbar-controls { order: 1; width: 100%; }
    .toolbar-config { order: 2; width: 100%; }
  }
}
```

### 13.5 Dark Theme Enhancement

The debug page uses a slightly deeper background than the chat page to
create visual separation and signal "developer mode":

```scss
.debug-page {
  background:
    radial-gradient(ellipse 60% 40% at 20% 0%, rgba(59, 127, 255, 0.04), transparent),
    radial-gradient(ellipse 50% 50% at 80% 100%, rgba(255, 217, 102, 0.03), transparent),
    var(--c-bg-deep);

  // Subtle scan line effect (optional, removable)
  &::before {
    content: '';
    position: fixed;
    inset: 0;
    background: repeating-linear-gradient(
      0deg,
      transparent,
      transparent 2px,
      rgba(255, 255, 255, 0.008) 2px,
      rgba(255, 255, 255, 0.008) 4px
    );
    pointer-events: none;
    z-index: 0;
  }
}
```

### 13.6 Component Visual Specifications

#### Phase Node

```
┌─────────────────────────────┐
│ ◉ ┊  PLANNING        1.2s  │
│   ┊  ☁ LLM #1 · 580 tok   │
└─────────────────────────────┘
  │
  │ ← pill: "planning_completed"
  │
```

```scss
.phase-node {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--c-debug-surface);
  border: 1.5px solid var(--c-phase-idle);
  border-radius: var(--r-md);
  cursor: pointer;
  transition: border-color var(--t), box-shadow var(--t);
  position: relative;
  min-width: 240px;

  &.phase--active {
    border-color: var(--c-phase-active);
    animation: phase-pulse 2s ease-in-out infinite;
  }

  &.phase--completed {
    border-color: var(--c-phase-completed);
  }

  &.phase--paused {
    border-color: var(--c-phase-paused);
    background: rgba(255, 179, 71, 0.06);
  }

  // Breakpoint dot
  .bp-dot {
    position: absolute;
    top: -5px;
    left: -5px;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--c-bp-dot);
    animation: bp-throb 1.8s ease-in-out infinite;
  }

  // Status icon
  .phase-icon {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    border: 2px solid currentColor;
    display: grid;
    place-items: center;
    font-size: 10px;
    flex-shrink: 0;
  }

  // LLM badge
  .llm-badge {
    font-size: 10px;
    color: var(--c-blue);
    opacity: 0.7;
  }
}
```

#### LLM Interaction Node

```scss
.llm-node {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(59, 127, 255, 0.06);
  border: 1px solid var(--c-blue-border);
  border-radius: var(--r-md);
  font-size: 11px;
  color: var(--c-blue);

  &.llm--active {
    animation: llm-pulse 1.5s ease-in-out infinite;
  }

  &.llm--completed {
    border-color: var(--c-phase-completed);
    color: var(--c-phase-completed);
  }

  .llm-icon {
    font-size: 16px;
  }
}
```

#### Continue Banner

```scss
.pause-banner {
  grid-column: 1 / -1;
  padding: 16px 24px;
  background: linear-gradient(
    135deg,
    rgba(255, 179, 71, 0.08) 0%,
    rgba(10, 22, 46, 0.95) 100%
  );
  border-top: 2px solid var(--c-phase-paused);
  backdrop-filter: blur(16px);
  animation: banner-slide-up 300ms cubic-bezier(0.16, 1, 0.3, 1);
  text-align: center;

  .pause-phase {
    font-size: 13px;
    color: var(--c-phase-paused);
    margin-bottom: 12px;
    letter-spacing: 0.3px;
  }

  .continue-btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 12px 48px;
    font-size: 15px;
    font-weight: 600;
    color: var(--c-bg-deep);
    background: linear-gradient(135deg, var(--c-gold), #ffcc33);
    border: none;
    border-radius: var(--r-md);
    cursor: pointer;
    transition: transform 120ms ease, box-shadow 120ms ease;
    box-shadow: 0 4px 16px rgba(255, 217, 102, 0.25);

    &:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 24px rgba(255, 217, 102, 0.35);
    }

    .shortcut-hint {
      font-size: 11px;
      font-weight: 400;
      opacity: 0.7;
      margin-left: 4px;
    }
  }

  .pause-meta {
    font-size: 11px;
    color: var(--c-text-dim);
    margin-top: 10px;
  }
}
```

#### Inspector Tabs

```scss
.inspector-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--c-inspector-border);
  padding: 0 16px;
  background: var(--c-inspector-bg);

  .tab {
    padding: 10px 16px;
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.3px;
    color: var(--c-text-dim);
    border-bottom: 2px solid transparent;
    cursor: pointer;
    transition: color var(--t), border-color var(--t);
    white-space: nowrap;

    &:hover {
      color: var(--c-text);
    }

    &.tab--active {
      color: var(--c-gold);
      border-bottom-color: var(--c-gold);
    }

    &.tab--has-data {
      &::after {
        content: '';
        display: inline-block;
        width: 5px;
        height: 5px;
        background: var(--c-green);
        border-radius: 50%;
        margin-left: 6px;
        vertical-align: middle;
      }
    }
  }
}
```

### 13.7 Iconography

Use Unicode symbols for consistency (no icon library needed):

| Element | Icon | Unicode |
|---------|------|---------|
| Play | ▶ | U+25B6 |
| Pause | ⏸ | U+23F8 |
| Continue / Step | ▶▶ | U+25B6U+25B6 |
| Breakpoint | ● | U+25CF |
| LLM Cloud | ☁ | U+2601 |
| Checkmark | ✓ | U+2713 |
| Error | ✕ | U+2715 |
| Agent Token | ⚡ | U+26A1 |
| Tool | 🔧 | U+1F527 |
| Clock | ⏱ | U+23F1 |
| Export | ↗ | U+2197 |
| Copy | ⎘ | U+2398 |

---

## 14. Implementation Plan

### Phase 1 — Backend Hooks (3 files, ~120 LOC)

| Step | File | Changes |
|------|------|---------|
| 1.1 | `agent.py` | Add `_debug_checkpoint()` method, `_debug_continue_event`, `_debug_breakpoints` attributes |
| 1.2 | `agent.py` | Insert 7 `_debug_checkpoint()` calls at phase boundaries |
| 1.3 | `agent.py` | Add `debug_prompt_sent`, `debug_llm_response`, `debug_post_processed` emissions around LLM calls (gated by `settings.debug_mode`) |
| 1.4 | `ws_handler.py` | Handle `debug_continue`, `debug_pause`, `debug_play`, `debug_set_breakpoints` message types |
| 1.5 | `models.py` | Add `breakpoints: list[str] | None` to `WsInboundEnvelope` |
| 1.6 | `config.py` | Verify `DEBUG_MODE` env var exists (already there) |

### Phase 2 — Frontend Scaffolding (5 files, ~300 LOC)

| Step | File | Changes |
|------|------|---------|
| 2.1 | `app.routes.ts` | Add `/debug` route |
| 2.2 | `app.html` | Add Debug nav link |
| 2.3 | `debug-page.component.ts` | Create standalone component, inject AgentSocketService |
| 2.4 | `debug-page.component.html` | Layout: toolbar + canvas + inspector + composer |
| 2.5 | `debug-page.component.scss` | Full design-system-compliant styles |

### Phase 3 — Pipeline Canvas (4 files, ~500 LOC)

| Step | File | Changes |
|------|------|---------|
| 3.1 | `pipeline-canvas.component.ts` | Phase nodes array, agent token position, state management |
| 3.2 | `pipeline-canvas.component.html` | Node rendering, edges, LLM branches, event pills |
| 3.3 | `pipeline-canvas.component.scss` | All animation keyframes, responsive grid |
| 3.4 | `phase-node.component.ts` | Individual node: status, breakpoint toggle, duration, click handler |

### Phase 4 — Prompt Inspector (3 files, ~350 LOC)

| Step | File | Changes |
|------|------|---------|
| 4.1 | `prompt-inspector.component.ts` | Tabs, content switching, copy-to-clipboard |
| 4.2 | `prompt-inspector.component.html` | Tab bar, prompt displays, reflection card, tool table |
| 4.3 | `syntax-highlight.pipe.ts` | Lightweight regex-based highlighting pipe |

### Phase 5 — Debug Controls & State Machine (2 files, ~250 LOC)

| Step | File | Changes |
|------|------|---------|
| 5.1 | `debug-page.component.ts` | State machine, keyboard shortcuts, WS message routing |
| 5.2 | `debug-toolbar.component.ts` | Play/Pause/Continue buttons, breakpoint manager |

### Phase 6 — Event Log & Timeline (2 files, ~200 LOC)

| Step | File | Changes |
|------|------|---------|
| 6.1 | `event-log.component.ts` | Filterable lifecycle event list |
| 6.2 | `timeline-scrubber.component.ts` | Horizontal scrubber for replaying events |

### Phase 7 — AgentSocketService Extensions (1 file, ~60 LOC)

| Step | File | Changes |
|------|------|---------|
| 7.1 | `agent-socket.service.ts` | Add `sendDebugContinue()`, `sendDebugPause()`, `sendDebugPlay()`, `sendDebugSetBreakpoints()` methods |

### Total Estimated LOC: ~1780

---

## 15. File Manifest

### New Files

```
frontend/src/app/pages/debug-page/
├── debug-page.component.ts          # Main page component + state machine
├── debug-page.component.html        # Top-level layout template
├── debug-page.component.scss        # Page-level styles + CSS custom properties

├── pipeline-canvas/
│   ├── pipeline-canvas.component.ts     # Canvas grid with phases + edges
│   ├── pipeline-canvas.component.html
│   ├── pipeline-canvas.component.scss   # All animation keyframes
│   └── phase-node.component.ts          # Individual phase node (inline template)

├── prompt-inspector/
│   ├── prompt-inspector.component.ts    # Tabbed inspector panel
│   ├── prompt-inspector.component.html
│   ├── prompt-inspector.component.scss

├── debug-toolbar/
│   └── debug-toolbar.component.ts       # Toolbar with controls (inline template)

├── event-log/
│   └── event-log.component.ts           # Filterable event stream (inline template)

├── timeline-scrubber/
│   └── timeline-scrubber.component.ts   # Replay scrubber (inline template)

└── pipes/
    └── syntax-highlight.pipe.ts         # Lightweight code highlighting
```

### Modified Files

```
frontend/src/app/app.routes.ts           # Add /debug route
frontend/src/app/app.html                # Add Debug nav link
frontend/src/app/services/
    agent-socket.service.ts              # Add debug_* send methods
frontend/src/styles.scss                 # Add debug CSS custom properties

backend/app/agent.py                     # Checkpoints, debug emissions
backend/app/ws_handler.py                # Handle debug_* messages
backend/app/models.py                    # breakpoints field on envelope
```

---

## 16. Testing Strategy

### 16.1 Backend Unit Tests

```
tests/test_debug_checkpoint.py
├── test_checkpoint_noop_when_debug_inactive
├── test_checkpoint_blocks_at_breakpoint
├── test_checkpoint_resumes_on_continue_event
├── test_checkpoint_skips_when_no_breakpoint_set
├── test_debug_prompt_sent_gated_by_debug_mode
├── test_debug_llm_response_includes_latency
├── test_debug_play_clears_breakpoints_and_resumes
├── test_debug_pause_blocks_at_next_checkpoint
```

### 16.2 Frontend Unit Tests

```
debug-page.component.spec.ts
├── should create component
├── should start in idle state
├── should transition to running on message send
├── should transition to paused on breakpoint_hit event
├── should show continue banner when paused
├── should send debug_continue on Continue click
├── should send debug_continue on F8 key press
├── should not capture F8 when composer focused
├── should toggle breakpoint on phase node click
├── should display system prompt in inspector
├── should display LLM response in inspector
├── should show reflection scores with correct colors
├── should display tool execution details
├── should transition to completed on run_completed
├── should animate agent token to active phase position
```

### 16.3 Integration Tests

```
tests/test_debug_integration.py
├── test_full_debug_run_emits_all_debug_events
├── test_breakpoint_at_planning_pauses_before_llm_call
├── test_continue_after_pause_resumes_pipeline
├── test_multiple_breakpoints_pause_at_each
├── test_play_clears_all_breakpoints
├── test_debug_events_not_emitted_when_debug_mode_false
├── test_debug_prompt_includes_full_system_prompt
├── test_debug_response_includes_raw_llm_output
```

### 16.4 E2E Tests (optional, Playwright)

```
e2e/debug-page.spec.ts
├── navigate to /debug route
├── send message and see agent token move through phases
├── set breakpoint, send message, verify pause banner appears
├── click continue, verify pipeline resumes
├── verify prompt inspector shows correct content per phase
├── verify keyboard shortcuts work (F5, F6, F8, F9)
├── verify responsive layout at mobile viewport
```
