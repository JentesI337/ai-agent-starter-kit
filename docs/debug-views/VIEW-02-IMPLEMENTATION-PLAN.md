# VIEW-02 Request & Routing Inspector — Detaillierter Implementierungsplan

> Erstellt: 07.03.2026  
> Basis: IST-Analyse aller Frontend- und Backend-Dateien  
> Prinzip: **Minimale Backend-Änderung** — das `request_dispatched` Event existiert bereits mit fast allen benötigten Daten.

---

## 0. Executive Summary

Der VIEW-02 Spec (`VIEW-02-REQUEST-ROUTING-INSPECTOR.md`) ging davon aus,
dass **zwei neue Backend-Events** nötig sind (`request_envelope_received` +
`agent_routing_decision`).  Die IST-Analyse zeigt, dass das **bereits existierende**
`request_dispatched` Event in `ws_handler.py` **alle Routing-Daten und die meisten
Envelope-Felder** bereits enthält.

**Bestehend & nutzbar:**  
`request_dispatched` liefert: `model`, `requested_agent_id`, `effective_agent_id`,
`routing_reason`, `routing_capabilities`, `routing_matches` (Top-5 mit Score +
matched_capabilities), `preset`, `queue_mode`, `prompt_mode`, `reasoning_level`,
`reasoning_visibility`.

**Fehlend im Event:**  
Nur 2 Envelope-Felder fehlen: `content_length` (für die Metrik ohne Content-Leak)
und `runtime_target`.

**Fehlend im Frontend:**  
Komplett — kein Typ, kein Event-Handler, kein Component.

**Ergebnis: 1 minimale Backend-Erweiterung + 5 Frontend-Gaps.**

---

## 1. IST-Zustand Analyse

### 1.1 Backend

#### `request_dispatched` Event (ws_handler.py:440)

```python
await send_lifecycle(
    stage="request_dispatched",
    request_id=request_id,
    session_id=session_id,
    details={
        "model": model,
        "requested_agent_id": requested_agent_id,
        "effective_agent_id": resolved_agent_id,
        "routing_reason": routing_reason,
        "routing_capabilities": list(required_capabilities),
        "routing_matches": ranked_capability_matches,
        "preset": applied_preset,
        "queue_mode": queue_mode,
        "prompt_mode": prompt_mode,
        "reasoning_level": reasoning_level,
        "reasoning_visibility": reasoning_visibility,
    },
)
```

#### `ranked_capability_matches` Format (main.py:676)

```python
ranked_payload = [
    {
        "agent_id": item.agent_id,
        "score": item.score,
        "matched_capabilities": list(item.matched_capabilities),
    }
    for item in ranked_matches[:5]  # Top 5 only
]
```

#### Routing-Methode-Ableitung

`routing_reason` kann sein:
| Wert | Bedeutung | Routing-Methode |
|------|-----------|----------------|
| `None` | Expliziter Agent oder Default, kein Capability-Match | `explicit` (wenn `requested != primary`) oder `default` |
| `"preset_review"` | Preset `review` → `review-agent` | `preset` |
| `"coding_intent"` | Capability-Match → `coder-agent` | `capability_matching` |
| `"research_intent"` | Capability-Match → `researcher-agent` | `capability_matching` |
| `"review_intent"` | Capability-Match → `review-agent` | `capability_matching` |
| `"architecture_intent"` | Capability-Match → `architect-agent` | `capability_matching` |
| `"*_intent"` | Capability-Match → jeweiliger Agent | `capability_matching` |
| `"capability_match"` | Generischer Capability-Match | `capability_matching` |

**Die Routing-Methode kann im Frontend aus `routing_reason` + `requested_agent_id` abgeleitet werden — kein Backend-Feld nötig.**

### 1.2 Frontend

| Datei | Relevanz für VIEW-02 | Status |
|-------|---------------------|--------|
| `agent-state.service.ts` → `DebugSnapshot` | Hat KEINE Felder für Envelope/Routing | ❌ Gap |
| `agent-state.service.ts` → `applyDebugEvent()` | Hat KEINEN Case für `request_dispatched` | ❌ Gap |
| `debug.types.ts` | Exportiert KEINE Routing-Types | ❌ Gap |
| `debug-page.component.ts` | Projiziert KEINE Routing-Daten | ❌ Gap |
| `debug-page.component.html` | Hat KEINEN Slot für Routing-Inspector | ❌ Gap |
| Routing-Inspector Component | **Existiert nicht** | ❌ Gap |

### 1.3 Spec-Requirement → Existierendes Event (Mapping)

| Spec-Requirement | Quelle | Status |
|------------------|--------|--------|
| Envelope: `type` | **Fehlt** (immer `user_message` bei diesem Handler) | ⚠ Kann hardcoded werden |
| Envelope: `content_length` | **Fehlt** | ⚠ GAP-1 |
| Envelope: `agent_id` | `details.requested_agent_id` | ✅ |
| Envelope: `model` | `details.model` | ✅ |
| Envelope: `preset` | `details.preset` | ✅ |
| Envelope: `session_id` | Top-Level `session_id` | ✅ |
| Envelope: `request_id` | Top-Level `request_id` | ✅ |
| Envelope: `queue_mode` | `details.queue_mode` | ✅ |
| Envelope: `prompt_mode` | `details.prompt_mode` | ✅ |
| Envelope: `reasoning_level` | `details.reasoning_level` | ✅ |
| Envelope: `reasoning_visibility` | `details.reasoning_visibility` | ✅ |
| Envelope: `runtime_target` | **Fehlt** in Event (aber im Job verfügbar) | ⚠ GAP-1 |
| Envelope: `tool_policy` | **Fehlt** in Event | ⚠ Optional — zu komplex für minimal change |
| Routing: gewählter Agent | `details.effective_agent_id` | ✅ |
| Routing: angefragter Agent | `details.requested_agent_id` | ✅ |
| Routing: Grund/Methode | `details.routing_reason` (ableitbar) | ✅ |
| Routing: Capabilities | `details.routing_capabilities` | ✅ |
| Routing: Scores (Top 5) | `details.routing_matches` | ✅ |

**Ergebnis: 14 von 17 Datenpunkten sind bereits vorhanden.  
Nur `content_length` und `runtime_target` fehlen im Event.  
`tool_policy` wird als optional eingestuft (zu komplex für K/V-Darstellung).**

---

## 2. Backend-Änderungen — 1 minimale Erweiterung

### Kein neues Event nötig!

Der Spec schlug 2 neue Events vor (`request_envelope_received`, `agent_routing_decision`).  
Das ist **nicht nötig**, weil `request_dispatched` bereits beide Informationsbereiche abdeckt.

### GAP-1: `content_length` und `runtime_target` zu `request_dispatched` hinzufügen

**Problem:**  
Die Envelope-Metrik `content_length` fehlt im Event.  Ohne sie kann der
Inspector nicht zeigen, wie lang der User-Text war (gemäß Spec wird `content`
**nie** angezeigt — nur die Länge).  `runtime_target` fehlt ebenfalls.

**Aktuelle Zeilen (ws_handler.py:440-455):**
```python
await send_lifecycle(
    stage="request_dispatched",
    request_id=request_id,
    session_id=session_id,
    details={
        "model": model,
        "requested_agent_id": requested_agent_id,
        "effective_agent_id": resolved_agent_id,
        "routing_reason": routing_reason,
        "routing_capabilities": list(required_capabilities),
        "routing_matches": ranked_capability_matches,
        "preset": applied_preset,
        "queue_mode": queue_mode,
        "prompt_mode": prompt_mode,
        "reasoning_level": reasoning_level,
        "reasoning_visibility": reasoning_visibility,
    },
)
```

**Fix:**  
2 Felder zum `details`-Dict hinzufügen:

```python
details={
    "model": model,
    "requested_agent_id": requested_agent_id,
    "effective_agent_id": resolved_agent_id,
    "routing_reason": routing_reason,
    "routing_capabilities": list(required_capabilities),
    "routing_matches": ranked_capability_matches,
    "preset": applied_preset,
    "queue_mode": queue_mode,
    "prompt_mode": prompt_mode,
    "reasoning_level": reasoning_level,
    "reasoning_visibility": reasoning_visibility,
    "content_length": len(content),          # NEU
},
```

**Hinweis:** `runtime_target` ist im `job`-Dict als `job.get("runtime_target")`
verfügbar — wird aber aktuell NICHT in eine lokale Variable extrahiert.
Da `runtime_target` in der Praxis selten gesetzt wird und die Variable
`runtime_target` nicht existiert, wird es **nicht hinzugefügt** um den
Backend-Change minimal zu halten.  Stattdessen wird im Frontend `—` angezeigt.

**Datei:** `backend/app/ws_handler.py`  
**Zeilen:** ~440-455 (Main Handler) + ~1349-1360 (Subrun Handler)  
**Aufwand:** 1 Zeile pro Emit (2 Stellen)  
**Risiko:** Sehr niedrig — rein additiv, kein bestehendes Verhalten geändert

---

## 3. Frontend-Implementierungsplan — 5 Gaps

### GAP-2: Neue Types `RequestEnvelope` + `RoutingDecision` + DebugSnapshot-Erweiterung

**Problem:**  
`DebugSnapshot` hat keine Felder für Request- oder Routing-Daten.  Es gibt
keine TypeScript-Interfaces für diese Strukturen.

**Lösung — neue Interfaces in `agent-state.service.ts`:**

```typescript
export interface RequestEnvelope {
  type: string;
  contentLength: number;
  agentOverride: string | null;
  modelOverride: string | null;
  preset: string | null;
  promptMode: string | null;
  queueMode: string | null;
  reasoningLevel: string | null;
  reasoningVisibility: string | null;
  sessionId: string | null;
  requestId: string | null;
}

export interface RoutingMatch {
  agentId: string;
  score: number;
  matchedCapabilities: string[];
}

export interface RoutingDecision {
  requestedAgentId: string;
  effectiveAgentId: string;
  routingReason: string | null;
  routingMethod: 'explicit' | 'preset' | 'capability_matching' | 'default';
  routingCapabilities: string[];
  routingMatches: RoutingMatch[];
}
```

**Erweiterung von `DebugSnapshot`:**

```typescript
export interface DebugSnapshot {
  // ... bestehende Felder ...
  requestEnvelope: RequestEnvelope | null;   // NEU
  routingDecision: RoutingDecision | null;   // NEU
}
```

**Initial-Wert im `resetDebugRun()`:**

```typescript
requestEnvelope: null,
routingDecision: null,
```

**Datei:** `agent-state.service.ts`  
**Aufwand:** ~35 Zeilen (Typen) + 2 Felder in DebugSnapshot + 2 Felder im Reset  
**Risiko:** Niedrig — rein additiv

---

### GAP-3: `request_dispatched` in `applyDebugEvent()` handeln

**Problem:**  
Der Switch in `applyDebugEvent()` hat keinen Case für `request_dispatched`.
Das Event wird also nur ins `eventLog` geschrieben, aber die Envelope/Routing-Daten
werden nicht extrahiert.

**Lösung — neuer Case nach dem bestehenden `run_started`/`request_started` Case:**

```typescript
case 'request_dispatched': {
  const routingReason = (details['routing_reason'] as string) ?? null;
  const requestedId = (details['requested_agent_id'] as string) ?? '';
  const effectiveId = (details['effective_agent_id'] as string) ?? '';

  // Routing-Methode ableiten
  let routingMethod: RoutingDecision['routingMethod'] = 'default';
  if (routingReason?.endsWith('_intent') || routingReason === 'capability_match') {
    routingMethod = 'capability_matching';
  } else if (routingReason?.startsWith('preset_')) {
    routingMethod = 'preset';
  } else if (requestedId && requestedId !== effectiveId && !routingReason) {
    routingMethod = 'explicit';
  }

  const rawMatches = Array.isArray(details['routing_matches'])
    ? details['routing_matches'] as Array<Record<string, unknown>>
    : [];

  next = {
    ...next,
    requestEnvelope: {
      type: 'user_message',
      contentLength: Number(details['content_length'] ?? 0),
      agentOverride: requestedId || null,
      modelOverride: (details['model'] as string) || null,
      preset: (details['preset'] as string) || null,
      promptMode: (details['prompt_mode'] as string) || null,
      queueMode: (details['queue_mode'] as string) || null,
      reasoningLevel: (details['reasoning_level'] as string) || null,
      reasoningVisibility: (details['reasoning_visibility'] as string) || null,
      sessionId: event.session_id ?? d.requestId,
      requestId: requestId,
    },
    routingDecision: {
      requestedAgentId: requestedId,
      effectiveAgentId: effectiveId,
      routingReason,
      routingMethod,
      routingCapabilities: Array.isArray(details['routing_capabilities'])
        ? (details['routing_capabilities'] as string[])
        : [],
      routingMatches: rawMatches.map(m => ({
        agentId: String(m['agent_id'] ?? ''),
        score: Number(m['score'] ?? 0),
        matchedCapabilities: Array.isArray(m['matched_capabilities'])
          ? (m['matched_capabilities'] as string[]).map(String)
          : [],
      })),
    },
  };
  break;
}
```

**Routing-Methode-Ableitung (Logik):**

| `routing_reason` | `requested_agent_id == effective_agent_id?` | → `routingMethod` |
|-------------------|---------------------------------------------|-------------------|
| `null` + requested ≠ effective | — | `explicit` |
| `"preset_review"` | — | `preset` |
| `"*_intent"` | — | `capability_matching` |
| `"capability_match"` | — | `capability_matching` |
| `null` + requested == effective | — | `default` |

**Datei:** `agent-state.service.ts`  
**Position:** Nach dem `run_started`/`request_started` Case (~Zeile 640)  
**Aufwand:** ~45 Zeilen  
**Risiko:** Niedrig — neuer Case, beeinflusst keine bestehende Logik

---

### GAP-4: Neuer `RequestRoutingInspectorComponent`

**Problem:**  
Kein Component existiert für die Darstellung der Envelope/Routing-Daten.

**Lösung — 3 neue Dateien:**

```
frontend/src/app/pages/debug-page/request-routing-inspector/
├── request-routing-inspector.component.ts
├── request-routing-inspector.component.html
└── request-routing-inspector.component.scss
```

#### Component (`.ts`)

```typescript
@Component({
  selector: 'app-request-routing-inspector',
  standalone: true,
  imports: [],
  templateUrl: './request-routing-inspector.component.html',
  styleUrl: './request-routing-inspector.component.scss',
})
export class RequestRoutingInspectorComponent {
  @Input() requestEnvelope: RequestEnvelope | null = null;
  @Input() routingDecision: RoutingDecision | null = null;

  get summary(): string {
    if (!this.routingDecision) return '';
    const parts: string[] = [
      this.routingDecision.effectiveAgentId,
      `via ${this.routingDecision.routingMethod}`,
    ];
    if (this.requestEnvelope?.modelOverride) {
      parts.push(this.requestEnvelope.modelOverride);
    }
    if (this.requestEnvelope?.sessionId) {
      parts.push(this.requestEnvelope.sessionId.slice(0, 12));
    }
    if (this.requestEnvelope?.contentLength) {
      parts.push(`${this.requestEnvelope.contentLength} chars`);
    }
    return parts.join(' · ');
  }

  get sortedMatches(): RoutingMatch[] {
    if (!this.routingDecision?.routingMatches.length) return [];
    return [...this.routingDecision.routingMatches]
      .sort((a, b) => b.score - a.score);
  }

  get maxScore(): number {
    return this.sortedMatches.length ? this.sortedMatches[0].score : 1;
  }

  getBarWidth(score: number): number {
    return this.maxScore > 0 ? (score / this.maxScore) * 100 : 0;
  }

  get envelopeEntries(): { label: string; value: string | null }[] {
    const e = this.requestEnvelope;
    if (!e) return [];
    return [
      { label: 'Type',                 value: e.type },
      { label: 'Request-ID',           value: e.requestId },
      { label: 'Session-ID',           value: e.sessionId },
      { label: 'Content Length',        value: e.contentLength ? `${e.contentLength} chars` : null },
      { label: 'Agent Override',        value: e.agentOverride },
      { label: 'Model Override',        value: e.modelOverride },
      { label: 'Preset',               value: e.preset },
      { label: 'Prompt Mode',          value: e.promptMode },
      { label: 'Queue Mode',           value: e.queueMode },
      { label: 'Reasoning Level',      value: e.reasoningLevel },
      { label: 'Reasoning Visibility', value: e.reasoningVisibility },
    ];
  }
}
```

#### Template (`.html`)

```html
@if (routingDecision) {
  <section class="routing-inspector">

    <!-- Summary -->
    <div class="routing-summary">{{ summary }}</div>

    <!-- Request Envelope -->
    <details class="inspector-section" open>
      <summary class="section-title">Request Envelope</summary>
      <dl class="kv-grid">
        @for (entry of envelopeEntries; track entry.label) {
          <dt class="kv-label">{{ entry.label }}</dt>
          <dd class="kv-value" [class.kv-value--null]="!entry.value">
            {{ entry.value ?? '—' }}
          </dd>
        }
      </dl>
    </details>

    <!-- Agent Routing -->
    <details class="inspector-section" open>
      <summary class="section-title">Agent Routing</summary>

      <div class="routing-chosen">
        <span class="routing-chosen-check">✓</span>
        Routed to: <strong>{{ routingDecision.effectiveAgentId }}</strong>
        <span class="routing-method-badge">{{ routingDecision.routingMethod }}</span>
      </div>

      @if (routingDecision.routingCapabilities.length) {
        <div class="routing-caps">
          Required:
          @for (cap of routingDecision.routingCapabilities; track cap) {
            <span class="cap-tag">{{ cap }}</span>
          }
        </div>
      }

      @if (sortedMatches.length) {
        <div class="routing-scores" role="list" aria-label="Agent Capability Scores">
          @for (match of sortedMatches; track match.agentId) {
            <div class="score-row" role="listitem"
                 [class.score-row--selected]="match.agentId === routingDecision.effectiveAgentId">
              <div class="score-bar"
                   [style.width.%]="getBarWidth(match.score)"
                   role="progressbar"
                   [attr.aria-valuenow]="match.score"
                   aria-valuemin="0"
                   [attr.aria-valuemax]="maxScore"
                   [attr.aria-label]="match.agentId + ': Score ' + match.score">
              </div>
              <span class="score-agent">{{ match.agentId }}</span>
              <span class="score-value">{{ match.score }}</span>
            </div>
          }
        </div>
      }
    </details>

  </section>
}
```

#### Styles (`.scss`)

```scss
:host {
  display: block;
  overflow-y: auto;
  font-size: 13px;
  color: var(--c-text);
}

.routing-inspector {
  padding: 12px 16px;
}

.routing-summary {
  padding: 8px 12px;
  margin-bottom: 12px;
  font-size: 12px;
  font-family: var(--ff-mono, monospace);
  color: var(--c-text-dim);
  background: var(--c-bg-tab);
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.inspector-section {
  margin-bottom: 12px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  overflow: hidden;
}

.section-title {
  padding: 8px 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--c-text-dim);
  background: var(--c-bg-tab);
  cursor: pointer;
  user-select: none;
}

/* ── Key-Value Grid ─────────────────────────────── */

.kv-grid {
  display: grid;
  grid-template-columns: 160px 1fr;
  margin: 0;
  padding: 0;
}

.kv-label {
  padding: 4px 12px;
  font-weight: 600;
  color: var(--c-text-dim);
  border-bottom: 1px solid var(--c-border);
}

.kv-value {
  padding: 4px 12px;
  font-family: var(--ff-mono, monospace);
  border-bottom: 1px solid var(--c-border);
  word-break: break-all;

  &--null {
    color: var(--c-text-muted, rgba(255,255,255,0.25));
  }
}

/* ── Routing Decision ───────────────────────────── */

.routing-chosen {
  padding: 8px 12px;
  font-size: 13px;

  strong {
    color: var(--c-accent);
  }
}

.routing-chosen-check {
  color: var(--c-accent);
  margin-right: 4px;
}

.routing-method-badge {
  display: inline-block;
  margin-left: 8px;
  padding: 2px 8px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-radius: var(--r-sm, 4px);
  background: var(--c-accent-dim);
  color: var(--c-accent);
  border: 1px solid var(--c-accent-border);
}

.routing-caps {
  padding: 4px 12px 8px;
  font-size: 12px;
  color: var(--c-text-dim);
}

.cap-tag {
  display: inline-block;
  margin: 2px 4px;
  padding: 1px 6px;
  font-size: 10px;
  background: rgba(55, 148, 255, 0.10);
  border: 1px solid rgba(55, 148, 255, 0.25);
  border-radius: var(--r-sm, 4px);
  color: var(--c-info, #3794ff);
}

/* ── Score Bars ─────────────────────────────────── */

.routing-scores {
  padding: 4px 12px 12px;
}

.score-row {
  display: grid;
  grid-template-columns: 1fr 150px 40px;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
  position: relative;
}

.score-row--selected {
  .score-agent { color: var(--c-accent); font-weight: 600; }
  .score-bar { background: var(--c-accent); }
}

.score-bar {
  height: 14px;
  background: var(--c-text-muted, rgba(255,255,255,0.15));
  border-radius: 2px;
  transition: width 300ms ease-out;
  min-width: 2px;
}

.score-agent {
  font-size: 12px;
  font-family: var(--ff-mono, monospace);
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.score-value {
  font-size: 11px;
  font-family: var(--ff-mono, monospace);
  color: var(--c-text-dim);
  text-align: right;
}

/* ── Responsive ─────────────────────────────────── */

@media (max-width: 768px) {
  .kv-grid {
    grid-template-columns: 120px 1fr;
  }
  .score-row {
    grid-template-columns: 1fr 120px 30px;
  }
}
```

**Aufwand:** 3 neue Dateien (~80 + 50 + 130 Zeilen)  
**Risiko:** Niedrig — isolierter, rein lesender Component

---

### GAP-5: Integration in `debug-page`

**Problem:**  
`debug-page.component.ts` projiziert keine Routing-Daten und das Template hat
keinen Slot für den Routing-Inspector.

**Lösung:**

**(a) `debug-page.component.ts`** — neue Imports und Felder:

```typescript
// Neue Imports:
import { RequestRoutingInspectorComponent } from './request-routing-inspector/request-routing-inspector.component';
import { RequestEnvelope, RoutingDecision } from './debug.types';

// In @Component.imports Array:
imports: [
  // ... bestehende ...
  RequestRoutingInspectorComponent,
],

// Neue Template-Felder:
requestEnvelope: RequestEnvelope | null = null;
routingDecision: RoutingDecision | null = null;

// In ngOnInit → debug$.subscribe:
this.requestEnvelope = snap.requestEnvelope;
this.routingDecision = snap.routingDecision;
```

**(b) `debug-page.component.html`** — neuer Component-Slot:

Der Routing-Inspector wird **innerhalb des `debug-workspace` Grid** als
dritte Spalte eingefügt ODER unter dem Pipeline-Canvas als überlappender Panel.

**Empfohlene Positionierung:**  
Da `debug-workspace` ein 2-Column-Grid ist (Pipeline links, Prompt-Inspector rechts),
wird der Routing-Inspector **über dem Prompt-Inspector** als zusammenklappbare
Sektion angezeigt.  Dafür wird das Grid auf **3 Rows** auf der rechten Seite
umgestellt:

Alternativ (einfacher): Der Routing-Inspector wird als **eigene Zeile** zwischen
`debug-workspace` und den Bannern eingefügt:

```html
<!-- Nach </div> (debug-workspace) und vor Pause Banner -->
<app-request-routing-inspector
  [requestEnvelope]="requestEnvelope"
  [routingDecision]="routingDecision">
</app-request-routing-inspector>
```

Oder **innerhalb des debug-workspace Grids** als Teil der rechten Spalte
unter dem Prompt-Inspector.

**Empfehlung: Separater Row zwischen Workspace und Bannern.**  
Das hält das Layout einfach und braucht keine Grid-Umstellung.  
Der Component rendert sich nur wenn `routingDecision` vorhanden ist (`@if`).

**(c) `debug-page.component.scss`** — keine Änderung nötig:  
Der Routing-Inspector bekommt seine eigene Row im `grid-template-rows: auto 1fr auto auto auto auto`.
Da `grid-template-rows` auf `auto` für die neuen Rows steht, brauchen wir nur
die bestehende `auto` um eine weitere `auto` Row zu erweitern:

```scss
// Bestehend:
grid-template-rows: auto 1fr auto auto auto;
// Neu:
grid-template-rows: auto 1fr auto auto auto auto;
```

**Datei:** `debug-page.component.ts`, `debug-page.component.html`, `debug-page.component.scss`  
**Aufwand:** ~10 Zeilen TS, ~5 Zeilen HTML, ~1 Zeile SCSS  
**Risiko:** Niedrig

---

### GAP-6: Re-Exports in `debug.types.ts`

**Problem:**  
Die neuen Types müssen von `debug.types.ts` re-exportiert werden, damit
der Routing-Inspector-Component und die Debug-Page sie importieren können
(konsistent mit dem bestehenden Pattern).

**Lösung:**

```typescript
// In debug.types.ts — bestehende Exports erweitern:
export type {
  DebugEvent,
  DebugState,
  DebugSnapshot,
  LlmCallRecord,
  PhaseState,
  PipelinePhase,
  ReflectionVerdict,
  ToolExecutionRecord,
  RequestEnvelope,     // NEU
  RoutingDecision,     // NEU
  RoutingMatch,        // NEU
} from '../../services/agent-state.service';
```

**Datei:** `debug.types.ts`  
**Aufwand:** 3 Zeilen  
**Risiko:** Niedrig

---

## 4. Abhängigkeiten und Reihenfolge

```
GAP-1 (Backend: content_length)         ─── kann parallel
GAP-2 (Frontend: Types)                 ─┐
GAP-3 (Frontend: applyDebugEvent)        ├── sequentiell (2 → 3 → 6)
GAP-6 (Frontend: Re-Exports)            ─┘
GAP-4 (Frontend: New Component)         ─── nach GAP-2/6
GAP-5 (Frontend: Integration)           ─── nach GAP-4
```

**Empfohlene Implementierungsreihenfolge:**

1. **GAP-1** — Backend: `content_length` hinzufügen (1 Zeile, 2 Stellen)
2. **GAP-2** — Frontend: Types definieren (~35 Zeilen)
3. **GAP-3** — Frontend: Event-Handler (~45 Zeilen)
4. **GAP-6** — Frontend: Re-Exports (~3 Zeilen)
5. **GAP-4** — Frontend: Component erstellen (~260 Zeilen, 3 Dateien)
6. **GAP-5** — Frontend: Integration (~15 Zeilen, 3 Dateien)
7. **Build-Test** — `ng build --configuration=development`

---

## 5. Spec-Abweichungen (bewusst)

| Spec-Forderung | Plan-Entscheidung | Begründung |
|----------------|-------------------|------------|
| 2 neue Backend-Events | 0 neue Events — bestehendes `request_dispatched` reicht | Minimiert Backend-Änderungen |
| `runtime_target` im Envelope | Nicht hinzugefügt | Wird von Clients selten gesetzt, Variable existiert nicht im Scope, Aufwand/Nutzen zu gering |
| `tool_policy` im Envelope | Nicht angezeigt | Zu komplexe Struktur für K/V-Grid; kann in V2 nachgerüstet werden |
| Score-Balken für alle 15 Agents | Top-5 (wie vom Backend geliefert) | Backend liefert `ranked_matches[:5]` — alle 15 zu senden wäre Overhead für wenig Informationsgewinn |
| `type` Feld aus echtem Envelope | Hardcoded `user_message` | Der Handler der `request_dispatched` emittiert, verarbeitet nur `user_message` Typen |

---

## 6. Risiko-Bewertung

| Gap | Risiko | Begründung |
|-----|--------|------------|
| GAP-1 | Sehr niedrig | 1 Zeile additiv, kein Breaking Change |
| GAP-2 | Sehr niedrig | Neue Interfaces, kein bestehender Code betroffen |
| GAP-3 | Niedrig | Neuer Switch-Case, isoliert von anderen Cases |
| GAP-4 | Niedrig | Neuer Component, keine Abhängigkeiten außer Types |
| GAP-5 | Niedrig | Minimale Integration, Component rendert sich nur bei Daten |
| GAP-6 | Sehr niedrig | Nur Re-Exports |

**Gesamtrisiko: Niedrig.**  
Kein bestehender Code wird verändert (außer 1 additive Zeile im Backend).
Alles ist additiv.

---

## 7. Akzeptanzkriterien-Mapping

| Spec-Kriterium | Gap |
|----------------|-----|
| F-01: Alle Envelope-Felder angezeigt | GAP-2 + GAP-3 + GAP-4 |
| F-02: Request-ID und Session-ID korrekt | GAP-3 (aus Event) |
| F-03: Gewählter Agent korrekt | GAP-3 + GAP-4 |
| F-04: Routing-Methode als Badge | GAP-3 (Ableitung) + GAP-4 (Badge-CSS) |
| F-05: Capability-Scores als Balken | GAP-3 + GAP-4 |
| F-06: Scores nach Wert sortiert | GAP-4 (`sortedMatches` Getter) |
| F-07: Live-Update bei neuem Run | GAP-3 (reactive via `debug$`) |
| F-08: Content-Length statt Content | GAP-1 + GAP-3 + GAP-4 |
| V-01: Grid aligned/lesbar | GAP-4 (SCSS Grid) |
| V-02: CSS Custom Properties | GAP-4 (SCSS `var(--c-*)`) |
| V-03: Gewählter Agent hervorgehoben | GAP-4 (`score-row--selected`) |
| V-04: Dark-Theme kompatibel | GAP-4 (durchgehend CSS vars) |
| B-01: Envelope-Event gesendet | ✅ `request_dispatched` existiert + GAP-1 |
| B-02: Routing-Scores im Event | ✅ `routing_matches` existiert |
| B-03: Content NICHT im Event | ✅ Bereits so implementiert |
| A-01: Aria auf Score-Balken | GAP-4 (`role="progressbar"`, `aria-valuenow/min/max`) |
| A-02: K/V als `<dl>/<dt>/<dd>` | GAP-4 (Template) |
