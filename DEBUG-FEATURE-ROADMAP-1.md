# Debug Feature Roadmap — Teil 1: Design System, UX & Backend

> Detaillierte Implementierungs-Roadmap für den Pipeline Debugger.
> Companion-Dokument: `DEBUG-FEATURE-ROADMAP-2.md` (Frontend Components & Implementation Steps)

---

## Inhaltsverzeichnis

1. [Neues Color Schema — App-weites Redesign](#1-neues-color-schema)
2. [UX-Anforderungskatalog](#2-ux-anforderungskatalog)
3. [Backend-Implementierung — Best Practices](#3-backend-implementierung)
4. [WebSocket Protocol Extensions](#4-websocket-protocol-extensions)
5. [Animation & AI-Style Micro-Interactions](#5-animation--ai-style-micro-interactions)

---

## 1. Neues Color Schema

### 1.1 Design-Token-Migration

Das gesamte App-Farbschema wird auf ein dunkles, IDE-inspiriertes Theme umgestellt.
Alle Farben werden als CSS Custom Properties in `styles.scss` definiert.

**Alte Tokens → Neue Tokens:**

```scss
// ──────────────────────────────────────────────────────────────
// styles.scss — KOMPLETT NEUE :root Definition
// ──────────────────────────────────────────────────────────────
:root {
  // ── Backgrounds ──────────────────────────────────────────
  --c-bg:              rgb(30, 30, 30);         // Main background (vorher: #060d1a)
  --c-bg-deep:         rgb(22, 22, 22);         // Deepest background (panels, modals)
  --c-bg-window:       rgb(37, 37, 38);         // Tool windows, side panels
  --c-bg-tab:          rgb(45, 45, 48);         // Tab backgrounds, inactive surfaces
  --c-bg-bar:          rgb(62, 62, 66);         // Command bar, top bar background
  --c-surface:         rgba(37, 37, 38, 0.92);  // Glassmorphic surface (vorher: rgba(10,22,46,0.80))
  --c-surface-2:       rgba(45, 45, 48, 0.85);  // Secondary glass surface
  --c-surface-elevated: rgba(62, 62, 66, 0.75); // Elevated cards

  // ── Borders ──────────────────────────────────────────────
  --c-border:          rgba(255, 255, 255, 0.08);  // Standard border
  --c-border-hi:       rgba(255, 255, 255, 0.14);  // Elevated/hovered border
  --c-border-focus:    rgba(0, 204, 122, 0.50);    // Focus ring

  // ── Primary Accent: Highlight Green ──────────────────────
  // Das neue "Gold" — primäre Interaktionsfarbe
  --c-accent:          rgb(0, 204, 122);           // #00CC7A — Highlight
  --c-accent-dim:      rgba(0, 204, 122, 0.18);   // Hintergrund für aktive Elemente
  --c-accent-border:   rgba(0, 204, 122, 0.35);   // Akzent-Rand
  --c-accent-glow:     rgba(0, 204, 122, 0.25);   // Glow-Schatten
  --c-accent-text:     rgb(0, 230, 140);           // Heller Akzent für Text auf dunklem BG

  // ── Secondary Accent: Link Blue ──────────────────────────
  --c-blue:            rgb(55, 148, 255);          // #3794FF — Links, LLM-Nodes
  --c-blue-dim:        rgba(55, 148, 255, 0.18);
  --c-blue-border:     rgba(55, 148, 255, 0.35);
  --c-blue-glow:       rgba(55, 148, 255, 0.20);

  // ── Semantic Colors ──────────────────────────────────────
  --c-red:             #ff5555;                    // Error
  --c-red-dim:         rgba(255, 85, 85, 0.15);
  --c-green:           rgb(0, 204, 122);           // Success (= accent)
  --c-green-dim:       rgba(0, 204, 122, 0.12);
  --c-yellow:          rgb(229, 178, 0);           // Warning / Histogram
  --c-yellow-dim:      rgba(229, 178, 0, 0.12);
  --c-amber:           #ffb347;                    // Paused state

  // ── Selection ────────────────────────────────────────────
  --c-selection:       rgb(38, 120, 79);           // Text-Selektion
  --c-selection-bg:    rgba(38, 120, 79, 0.45);

  // ── Text ─────────────────────────────────────────────────
  --c-text:            rgb(212, 212, 212);         // #D4D4D4 — Primärer Text
  --c-text-dim:        rgb(155, 155, 155);         // #9B9B9B — Sekundärer Text
  --c-text-muted:      rgb(110, 110, 110);         // Tertiärer Text / Placeholder

  // ── Buttons ──────────────────────────────────────────────
  --c-btn:             rgb(63, 63, 70);            // Default button bg
  --c-btn-hover:       rgb(67, 67, 70);            // Hover bg
  --c-btn-pressed:     rgb(63, 63, 70);            // Pressed bg
  --c-btn-disabled:    rgb(45, 45, 48);            // Disabled bg
  --c-btn-border:      rgb(67, 67, 70);            // Border
  --c-btn-hover-border: rgb(0, 204, 122);          // Hover border (accent!)
  --c-btn-text:        rgb(212, 212, 212);         // Button text

  // ── Plot / Charts ───────────────────────────────────────
  --c-plot-lines:      rgb(155, 155, 155);         // Plot/Chart lines
  --c-histogram:       rgb(229, 178, 0);           // Histogram bars

  // ── Elevation (Schatten) ─────────────────────────────────
  --shadow-sm:  0 2px 8px  rgba(0, 0, 0, 0.45);
  --shadow-md:  0 6px 20px rgba(0, 0, 0, 0.55);
  --shadow-lg:  0 14px 44px rgba(0, 0, 0, 0.65);
  --shadow-glow-accent: 0 0 20px rgba(0, 204, 122, 0.15);
  --shadow-glow-blue:   0 0 20px rgba(55, 148, 255, 0.15);

  // ── Border Radii ─────────────────────────────────────────
  --r-sm: 4px;
  --r-md: 8px;
  --r-lg: 12px;
  --r-xl: 16px;
  --r-full: 9999px;

  // ── Transitions ──────────────────────────────────────────
  --t-fast: 100ms ease;
  --t:      160ms ease;
  --t-slow: 300ms ease;
  --t-spring: 300ms cubic-bezier(0.16, 1, 0.3, 1);

  // ── Z-Index Scale ────────────────────────────────────────
  --z-canvas:   1;
  --z-token:    10;
  --z-panel:    20;
  --z-banner:   30;
  --z-toolbar:  40;
  --z-overlay:  50;
  --z-modal:    100;

  // ── Debug-spezifische Tokens ─────────────────────────────
  --c-phase-idle:       rgb(110, 110, 110);
  --c-phase-active:     rgb(0, 204, 122);
  --c-phase-completed:  rgb(0, 204, 122);
  --c-phase-error:      #ff5555;
  --c-phase-paused:     #ffb347;
  --c-phase-skipped:    rgb(80, 80, 80);

  --c-llm-node:         rgb(55, 148, 255);
  --c-llm-glow:         rgba(55, 148, 255, 0.25);

  --c-bp-dot:           #ff4444;
  --c-bp-glow:          rgba(255, 68, 68, 0.30);

  --c-inspector-bg:     rgba(30, 30, 30, 0.95);
  --c-inspector-border: rgba(0, 204, 122, 0.10);
  --c-code-bg:          rgba(0, 0, 0, 0.30);
}
```

### 1.2 Migrations-Checkliste

Folgende Dateien müssen aktualisiert werden, um das neue Schema zu verwenden:

| Datei | Änderungen |
|-------|-----------|
| `frontend/src/styles.scss` | `:root`-Block komplett ersetzen, alle `--c-gold*` → `--c-accent*` |
| `frontend/src/app/app.scss` | `.top-nav` Background → `--c-bg-bar`, Logo-Farbe → `--c-accent`, Active-Tab → `--c-accent` |
| `frontend/src/app/pages/chat-page.component.scss` | Alle `--c-gold*` Referenzen → `--c-accent*`, Panel-BGs → `--c-surface` |
| `frontend/src/app/pages/memory-page.component.scss` | Button-Gradient → `--c-accent`, Active-States → `--c-accent` |

### 1.3 Mapping: Alt → Neu

| Alter Token | Neuer Token | Visueller Effekt |
|-------------|-------------|-----------------|
| `--c-bg: #060d1a` | `--c-bg: rgb(30,30,30)` | Dunkelgrau statt Dunkelblau |
| `--c-bg-deep: #030810` | `--c-bg-deep: rgb(22,22,22)` | Tieferes Schwarz |
| `--c-surface: rgba(10,22,46,0.80)` | `--c-surface: rgba(37,37,38,0.92)` | Neutrales Grau-Glas |
| `--c-gold: #ffd966` | `--c-accent: rgb(0,204,122)` | Gold → Grün Highlight |
| `--c-gold-dim` | `--c-accent-dim` | Korrespondierend |
| `--c-gold-border` | `--c-accent-border` | Korrespondierend |
| `--c-blue: #3b7fff` | `--c-blue: rgb(55,148,255)` | Leicht wärmer |
| `--c-text: #e8f0ff` | `--c-text: rgb(212,212,212)` | Neutrales Weiß statt Bläulich |
| `--c-text-dim: #8aa4ce` | `--c-text-dim: rgb(155,155,155)` | Neutral Grau |
| `--c-text-muted: #4e6a96` | `--c-text-muted: rgb(110,110,110)` | Neutral Grau |

### 1.4 Hintergrund-Gradient

```scss
// ALT — bläulicher Deep-Space-Look:
background: radial-gradient(...) linear-gradient(180deg, #060d1a 0%, #03080f 100%);

// NEU — neutrales Dark-IDE mit subtilen Akzent-Glows:
:host {
  background:
    radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0, 204, 122, 0.03), transparent 70%),
    radial-gradient(ellipse 60% 40% at 80% 100%, rgba(55, 148, 255, 0.02), transparent 60%),
    rgb(30, 30, 30);
}
```

### 1.5 Glasmorphic Panels (Neuer Stil)

```scss
.panel {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  backdrop-filter: blur(16px);
  box-shadow: var(--shadow-sm);
  transition: border-color var(--t), box-shadow var(--t);

  &:hover {
    border-color: var(--c-border-hi);
  }

  // AI-Style: subtiler Glow am oberen Rand bei Aktivität
  &.panel--active {
    border-color: var(--c-accent-border);
    box-shadow:
      var(--shadow-md),
      inset 0 1px 0 rgba(0, 204, 122, 0.08);
  }
}
```

---

## 2. UX-Anforderungskatalog

### 2.1 Kern-Anforderungen (P0 — Must Have)

| ID | Feature | Beschreibung | Akzeptanzkriterium |
|----|---------|--------------|-------------------|
| UX-01 | **Route /debug** | Eigenständige Debug-Seite, lazy-loaded | URL `/debug` zeigt `DebugPageComponent` |
| UX-02 | **Navigation** | "Debug" Link in der Top-Nav zwischen Chat und Memory | Link sichtbar, `routerLinkActive` funktioniert |
| UX-03 | **Pipeline Canvas** | Alle 9 Pipeline-Phasen als verbundene Nodes (vertikal) | Visuell korrekt, responsive |
| UX-04 | **Phase-Status** | Jede Phase zeigt Status: idle/active/paused/completed/error/skipped | Korrekte CSS-Klasse pro Zustand |
| UX-05 | **Agent-Token Animation** | Animierter Token bewegt sich von Phase zu Phase | Smooth transition, 600ms |
| UX-06 | **LLM-Interaktions-Nodes** | Phasen mit LLM-Calls zeigen Cloud-Icon-Branch rechts | Planning, Tool, Synthesis, Reflection haben LLM-Node |
| UX-07 | **Play-Button** | Startet Pipeline-Ausführung / Resumed bei Pause | State → running |
| UX-08 | **Pause-Button** | Pausiert Pipeline an nächster Phase-Grenze | State → paused |
| UX-09 | **Continue-Button** | Rückt genau eine Phase vor, dann Pause | Step-Debugging |
| UX-10 | **Continue-Banner** | Bei Pause: prominentes Full-Width-Banner mit dem Continue-Button | Banner animiert rein, F8/Space reagiert |
| UX-11 | **System-Prompt Inspector** | Zeigt kompletten System-Prompt der aktuellen Phase | Tab "System Prompt" im Inspector |
| UX-12 | **User-Prompt Inspector** | Zeigt assemblierten User-Prompt mit Context | Tab "User Prompt" im Inspector |
| UX-13 | **LLM-Response Inspector** | Zeigt Raw-Antwort vor Post-Processing | Tab "LLM Response" |
| UX-14 | **Parsed-Output Inspector** | Zeigt Post-Processed Output (Plan-JSON, Actions, shaped text) | Tab "Parsed Output" |
| UX-15 | **Tool-Details** | Tool-Name, Args, Result-Preview, Duration, Status | Tab "Tool Details" im Inspector |
| UX-16 | **Reflection-Score** | Goal-Alignment, Completeness, Factual-Grounding als Bars + Verdict | Tab "Reflection" mit Score-Card |
| UX-17 | **Lifecycle-Event-Pills** | Lifecycle-Events als kleine Pills auf den Canvas-Kanten | Durchgehend sichtbar |
| UX-18 | **Shared WebSocket** | Debug-Seite nutzt selbe WS-Verbindung wie Chat | `AgentSocketService` wiederverwendet |
| UX-19 | **Debug-Composer** | Message-Input direkt in der Debug-Seite | Textarea + Send-Button |
| UX-20 | **Dark Theme** | Neues Farbschema konsequent auf allen Seiten | Visuell konsistent |

### 2.2 Erweiterte Anforderungen (P1 — Should Have)

| ID | Feature | Beschreibung | Akzeptanzkriterium |
|----|---------|--------------|-------------------|
| UX-21 | **Breakpoint-Toggle auf Nodes** | Klick auf Phase-Node setzt/entfernt Breakpoint | Roter Dot erscheint/verschwindet |
| UX-22 | **Timeline-Scrubber** | Horizontaler Scrubber am Canvas-Boden für Event-Replay | Slider nach Run-Ende nutzbar |
| UX-23 | **Phase-Dauer** | Zeitangabe auf Canvas-Kanten (z.B. "1.2s") | Duration-Badge nach Phase-Ende |
| UX-24 | **Token-Stream** | Sub-Panel zeigt Streaming-Tokens während Synthesis | Live-Token-Anzeige |
| UX-25 | **Keyboard-Shortcuts** | F5=Play, F6=Pause, F8=Continue, F9=Toggle-Breakpoint | Keys funktionieren, nicht im Composer |
| UX-26 | **Responsive Layout** | Canvas wird vertikal < 768px, Panels stacken < 1024px | Grid-Umbruch |
| UX-27 | **Context-Budget-Visualisierung** | Token-Allocation als Mini-Bar-Chart | Bei `context_segmented` Events |
| UX-28 | **Export** | Debug-Trace als JSON exportieren | Download-Button, valides JSON |

### 2.3 Nice-to-Have (P2)

| ID | Feature | Beschreibung |
|----|---------|--------------|
| UX-29 | **Diff-View** | Before/After bei Reflection-Re-Synthesis |
| UX-30 | **Audio-Cue** | Subtiler Klick/Ping bei Phase-Wechsel |
| UX-31 | **Shareable Debug URL** | URL mit `?run_id=...` für Replay |

---

## 3. Backend-Implementierung — Best Practices

### 3.1 Prinzip: Non-Destructive Observability

**Regel #1:** Debug-Events ÄNDERN NIEMALS die Pipeline-Logik.
Sie sind reine Emissions — Seiteneffekt-frei.

**Regel #2:** Alle `debug_*` Events sind hinter `DEBUG_MODE=true` gated.
In Produktion: Zero Overhead, keine Payload-Bloat.

**Regel #3:** Breakpoints sind cooperative (async Event) — kein Thread-Blocking, keine Deadlocks.

### 3.2 Schritt-für-Schritt Backend-Änderungen

#### 3.2.1 `config.py` — Debug-Mode Setting

```python
# Bereits vorhanden oder hinzufügen:
debug_mode: bool = Field(default=False, description="Enable debug lifecycle events")
# Env: DEBUG_MODE=true
```

#### 3.2.2 `agent.py` — Debug-Infrastruktur (3 neue Attribute + 1 Methode)

**Neue Instanz-Attribute im `__init__`:**

```python
# Debug-Infrastruktur
self._debug_continue_event: asyncio.Event = asyncio.Event()
self._debug_continue_event.set()   # Default: nicht pausiert
self._debug_breakpoints: set[str] = set()
self._debug_mode_active: bool = False
```

**Neue Methode `_debug_checkpoint()`:**

```python
async def _debug_checkpoint(
    self,
    phase: str,
    send_event: SendEvent,
    request_id: str,
    session_id: str,
) -> None:
    """Kooperativer Pause-Punkt. Blockiert nur wenn Breakpoint
    gesetzt oder User Pause gedrückt hat."""
    if not self._debug_mode_active:
        return
    if phase not in self._debug_breakpoints and self._debug_continue_event.is_set():
        return

    self._debug_continue_event.clear()
    await self._emit_lifecycle(
        send_event, "debug_breakpoint_hit", request_id, session_id,
        details={"phase": phase, "breakpoint_id": f"bp-{phase}"},
    )
    await self._debug_continue_event.wait()
```

**7 Checkpoint-Insertions in `run()`:**

| Position | Phase-String | Beschreibung |
|----------|-------------|--------------|
| Nach Guardrails (~L646) | `"guardrails"` | Vor Memory/Context |
| Nach Context-Assembly (~L851) | `"context"` | Vor Planning |
| Vor Planning LLM-Call (~L815) | `"planning"` | Prompt inspizierbar |
| Vor Tool-Selection LLM-Call (~L907) | `"tool_selection"` | Actions inspizierbar |
| Vor Synthesis LLM-Call (~L1265) | `"synthesis"` | Final-Answer inspizierbar |
| Vor Reflection LLM-Call (~L1281) | `"reflection"` | Score inspizierbar |
| Vor Reply-Shaping (~L1386) | `"reply_shaping"` | Output inspizierbar |

#### 3.2.3 `agent.py` — Debug-Event-Emissionen

**Gate in `_emit_lifecycle`:**

```python
async def _emit_lifecycle(self, send_event, stage, request_id, session_id, details=None):
    if stage.startswith("debug_") and not settings.debug_mode:
        return
    await send_event(build_lifecycle_event(...))
```

**Emissions-Pattern an jedem der 6 LLM-Call-Sites:**

```python
# VOR dem LLM-Call:
t0 = time.monotonic()
if settings.debug_mode:
    await self._emit_lifecycle(send_event, "debug_prompt_sent", request_id, session_id, {
        "phase": "<phase_name>",
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "model": model,
        "temperature": temperature,
    })

# LLM-Call ausführen:
raw_response = await self.client.complete_chat(...)

# NACH dem LLM-Call:
if settings.debug_mode:
    await self._emit_lifecycle(send_event, "debug_llm_response", request_id, session_id, {
        "phase": "<phase_name>",
        "raw_response": raw_response,
        "latency_ms": int((time.monotonic() - t0) * 1000),
    })
```

**6 Call-Sites:**

| # | Datei | Methode | Phase-String |
|---|-------|---------|-------------|
| 1 | `agents/planner_agent.py` | `_plan()` | `"planning"` |
| 2 | `agents/tool_selector_agent.py` | `_select()` | `"tool_selection"` |
| 3 | `agents/tool_selector_agent.py` | Repair-Call | `"tool_repair"` |
| 4 | `agents/synthesizer_agent.py` | `_synthesize()` | `"synthesis"` |
| 5 | `services/reflection_service.py` | `reflect()` | `"reflection"` |
| 6 | `agent.py` | `_distill_session_knowledge()` | `"distillation"` |

**Herausforderung:** Sub-Agents haben aktuell keinen Zugriff auf `send_event`.
Der Callback muss durch die Step-Executors durchgereicht werden.
`ToolStepExecutor` macht das bereits — gleiche Pattern auf `PlannerStepExecutor`
und `SynthesizeStepExecutor` anwenden.

#### 3.2.4 `ws_handler.py` — Neue Message-Types

```python
elif msg_type == "debug_continue":
    agent._debug_continue_event.set()

elif msg_type == "debug_pause":
    agent._debug_continue_event.clear()

elif msg_type == "debug_set_breakpoints":
    bp_list = envelope.breakpoints or []
    # Validierung: nur bekannte Phase-Namen zulassen
    valid_phases = {"guardrails", "context", "planning", "tool_selection",
                    "synthesis", "reflection", "reply_shaping"}
    agent._debug_breakpoints = set(bp_list) & valid_phases

elif msg_type == "debug_play":
    agent._debug_breakpoints.clear()
    agent._debug_continue_event.set()
```

#### 3.2.5 `models.py` — Envelope Extension

```python
class WsInboundEnvelope(BaseModel):
    # ... existing fields ...
    breakpoints: list[str] | None = Field(default=None, max_length=20)
```

### 3.3 Sicherheits-Aspekte

| Aspekt | Maßnahme |
|--------|---------|
| **Prompt-Leaking** | `debug_prompt_sent` enthält volle Prompts — nur bei `DEBUG_MODE=true` aktiv, niemals in Prod |
| **DoS via Breakpoints** | Timeout auf `_debug_continue_event.wait()` (z.B. 300s), dann auto-resume |
| **Breakpoint-Injection** | `breakpoints`-Liste wird gegen Whitelist validiert (nur bekannte Phase-Namen) |
| **Event-Flooding** | Debug-Events nur bei `DEBUG_MODE=true` — zero-cost Gate |

### 3.4 Test-Strategie Backend

```
backend/tests/test_debug_checkpoint.py
├── test_checkpoint_noop_when_debug_inactive
├── test_checkpoint_blocks_at_breakpoint
├── test_checkpoint_resumes_on_continue_event
├── test_checkpoint_skips_when_no_breakpoint_set
├── test_debug_prompt_sent_gated_by_debug_mode
├── test_debug_llm_response_includes_latency
├── test_debug_play_clears_breakpoints_and_resumes
├── test_debug_pause_blocks_at_next_checkpoint

backend/tests/test_debug_integration.py
├── test_full_debug_run_emits_all_debug_events
├── test_breakpoint_at_planning_pauses_before_llm_call
├── test_continue_after_pause_resumes_pipeline
├── test_debug_events_not_emitted_when_debug_mode_false
├── test_debug_prompt_includes_full_system_prompt
```

---

## 4. WebSocket Protocol Extensions

### 4.1 Neue Inbound Messages (Frontend → Backend)

```typescript
// Pipeline fortsetzen (nach Breakpoint / Pause)
{ type: "debug_continue", request_id: string }

// Pipeline an nächster Phase-Grenze pausieren
{ type: "debug_pause" }

// Breakpoints setzen (ersetzt vorherige)
{ type: "debug_set_breakpoints", breakpoints: ["planning", "synthesis", "reflection"] }

// Alle Breakpoints löschen + Resume (Free-Run)
{ type: "debug_play" }
```

### 4.2 Neue Outbound Events (Backend → Frontend)

```typescript
// Vor jedem LLM-Call
{
  type: "lifecycle",
  stage: "debug_prompt_sent",
  details: {
    phase: "planning" | "tool_selection" | "tool_repair" | "synthesis" | "reflection" | "distillation",
    system_prompt: string,      // Voller System-Prompt
    user_prompt: string,        // Voller User-Prompt mit Context
    model: string,              // Modell-ID
    temperature: number
  }
}

// Nach jedem LLM-Call
{
  type: "lifecycle",
  stage: "debug_llm_response",
  details: {
    phase: string,
    raw_response: string,       // Vor Post-Processing
    latency_ms: number,
    tokens_est: number
  }
}

// Nach Post-Processing
{
  type: "lifecycle",
  stage: "debug_post_processed",
  details: {
    phase: string,
    parsed_output: string,      // JSON oder Text
    transform: "plan_parse" | "action_parse" | "section_contract" | "reflection_parse"
  }
}

// Breakpoint erreicht — Pipeline wartet
{
  type: "lifecycle",
  stage: "debug_breakpoint_hit",
  details: {
    phase: string,
    breakpoint_id: string       // z.B. "bp-planning"
  }
}

// Tool-Execution Detail (pro Tool-Call)
{
  type: "lifecycle",
  stage: "tool_execution_detail",
  details: {
    tool: string,
    args: object,
    result_preview: string,     // Erste 500 Zeichen
    duration_ms: number,
    exit_code: number,
    blocked: boolean
  }
}

// Context-Budget Detail
{
  type: "lifecycle",
  stage: "context_budget_detail",
  details: {
    phase: string,
    total_budget: number,
    segments: {
      system: { chars: number, tokens_est: number, pct: number },
      tool_results: { chars: number, tokens_est: number, pct: number },
      memory: { chars: number, tokens_est: number, pct: number },
      snapshot: { chars: number, tokens_est: number, pct: number }
    }
  }
}
```

### 4.3 AgentSocketService — Neue Methoden

```typescript
// agent-socket.service.ts — Neue public Methoden

sendDebugContinue(requestId: string): void {
  this.send({ type: 'debug_continue', request_id: requestId });
}

sendDebugPause(): void {
  this.send({ type: 'debug_pause' });
}

sendDebugPlay(): void {
  this.send({ type: 'debug_play' });
}

sendDebugSetBreakpoints(breakpoints: string[]): void {
  this.send({ type: 'debug_set_breakpoints', breakpoints });
}
```

---

## 5. Animation & AI-Style Micro-Interactions

### 5.1 Design-Philosophie

**AI-Style** heißt: Die UI fühlt sich lebendig an, wie ein denkendes System.
Bewegung ist purposeful — jede Animation kommuniziert Status.

| Prinzip | Umsetzung |
|---------|-----------|
| **Atmendes System** | Aktive Phasen pulsieren sanft — das System "denkt" |
| **Energie-Flow** | Der Agent-Token ist ein Energie-Ball, der durch die Pipeline fließt |
| **Glasmorphismus** | Halbtransparente Panels mit Blur — Tiefe und Schichtung |
| **Glow-Effekte** | Aktive Elemente strahlen sanft — Aufmerksamkeitsführung |
| **Snappy Feedback** | Buttons reagieren in < 120ms — direktes Kontrollerlebnis |

### 5.2 Vollständiger Animations-Katalog

#### Agent-Token — Der "Denker"

```scss
.agent-token {
  position: absolute;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--c-accent);
  box-shadow:
    0 0 12px var(--c-accent-dim),
    0 0 30px rgba(0, 204, 122, 0.10);
  transition: transform 600ms cubic-bezier(0.34, 1.56, 0.64, 1);  // Overshoot!
  z-index: var(--z-token);

  // Inneres Icon
  &::after {
    content: '⚡';
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    font-size: 18px;
  }

  // Bei LLM-Interaktion: Farbe wechselt zu Blau
  &.at-llm {
    background: var(--c-blue);
    box-shadow: 0 0 20px var(--c-blue-glow);
    animation: llm-thinking 1.5s ease-in-out infinite;

    &::after { content: '☁'; }
  }

  // Pausiert: sanftes Atmen
  &.paused {
    animation: token-breathe 2s ease-in-out infinite;
  }

  // Trail-Effekt beim Bewegen
  &.moving::before {
    content: '';
    position: absolute;
    inset: 2px;
    border-radius: 50%;
    background: var(--c-accent);
    opacity: 0.3;
    animation: token-trail 600ms ease-out forwards;
  }
}

@keyframes llm-thinking {
  0%, 100% {
    box-shadow: 0 0 12px var(--c-blue-glow);
    transform: scale(1);
  }
  50% {
    box-shadow: 0 0 30px var(--c-blue-glow), 0 0 60px rgba(55, 148, 255, 0.08);
    transform: scale(1.08);
  }
}

@keyframes token-breathe {
  0%, 100% { transform: scale(1); opacity: 0.9; }
  50% { transform: scale(1.12); opacity: 1; }
}

@keyframes token-trail {
  to { transform: scale(2); opacity: 0; }
}
```

#### Phase-Node Pulse (Aktiv)

```scss
@keyframes phase-pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 var(--c-accent-dim);
    border-color: var(--c-accent-border);
  }
  50% {
    box-shadow: 0 0 24px 6px var(--c-accent-dim);
    border-color: var(--c-accent);
  }
}

.phase-node.phase--active {
  animation: phase-pulse 2s ease-in-out infinite;
}
```

#### Phase Completion — Bounce-In Checkmark

```scss
@keyframes check-bounce {
  0%   { transform: scale(0) rotate(-45deg); opacity: 0; }
  60%  { transform: scale(1.3) rotate(5deg); opacity: 1; }
  100% { transform: scale(1) rotate(0deg); }
}

.phase-icon--completed {
  animation: check-bounce 400ms cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
  color: var(--c-accent);
}
```

#### Error Shake

```scss
@keyframes error-shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-5px); }
  40% { transform: translateX(5px); }
  60% { transform: translateX(-3px); }
  80% { transform: translateX(3px); }
}

.phase-node.phase--error {
  animation: error-shake 400ms ease-in-out;
  border-color: var(--c-red);
  box-shadow: 0 0 16px var(--c-red-dim);
}
```

#### Breakpoint Throb

```scss
@keyframes bp-throb {
  0%, 100% {
    transform: scale(1);
    box-shadow: 0 0 4px var(--c-bp-glow);
  }
  50% {
    transform: scale(1.4);
    box-shadow: 0 0 14px var(--c-bp-glow);
  }
}

.bp-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--c-bp-dot);
  animation: bp-throb 1.8s ease-in-out infinite;
}
```

#### Continue-Banner Slide-Up

```scss
@keyframes banner-slide-up {
  from {
    transform: translateY(100%);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

.pause-banner {
  animation: banner-slide-up 300ms cubic-bezier(0.16, 1, 0.3, 1);
}
```

#### Score-Bar Fill (Reflection)

```scss
@keyframes bar-fill {
  from { width: 0; }
}

.score-fill {
  animation: bar-fill 800ms ease-out forwards;
  height: 100%;
  border-radius: var(--r-sm);
  transition: background-color var(--t);

  &.score--good { background: var(--c-accent); }
  &.score--warn { background: var(--c-yellow); }
  &.score--bad  { background: var(--c-red); }
}
```

#### Event-Pill Fade-In

```scss
@keyframes pill-fade-in {
  from {
    opacity: 0;
    transform: translateY(-6px) scale(0.9);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.event-pill {
  animation: pill-fade-in 200ms ease-out forwards;
  padding: 2px 8px;
  border-radius: var(--r-full);
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  background: var(--c-surface-2);
  border: 1px solid var(--c-border);
  color: var(--c-text-dim);
  white-space: nowrap;
}
```

#### Data-Stream-Effekt (Canvas-Kanten)

```scss
// Subtile "Daten fließen"-Animation auf den Verbindungslinien
@keyframes data-flow {
  0% {
    background-position: 0 0;
  }
  100% {
    background-position: 0 20px;
  }
}

.edge-line.edge--active {
  background: repeating-linear-gradient(
    180deg,
    var(--c-accent) 0px,
    var(--c-accent) 4px,
    transparent 4px,
    transparent 8px
  );
  background-size: 2px 8px;
  animation: data-flow 600ms linear infinite;
  width: 2px;
}
```

### 5.3 Reduced Motion Support

```scss
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

### 5.4 Performance-Budget

| Constraint | Limit | Warum |
|-----------|-------|-------|
| Gleichzeitige CSS-Animationen | ≤ 6 | GPU-Compositing-Limit |
| Animation-Dauer (schnellste) | 100ms | Unter Wahrnehmungsschwelle = instant |
| Animation-Dauer (langsamste) | 2000ms | Infinite Pulse — niedrige CPU-Last |
| `will-change` Properties | Nur auf Agent-Token | Vermeidet Layer-Explosion |
| `backdrop-filter: blur()` | ≤ 3 gleichzeitig | Teuer auf Low-End-GPUs |
| DOM-Nodes im Canvas | ≤ 50 | Kein Virtual Scrolling nötig |
