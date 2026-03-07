# VIEW-01 Pipeline Overview — Detaillierter Implementierungsplan

> Erstellt: 07.03.2026  
> Basis: IST-Analyse aller Frontend- und Backend-Dateien  
> Prinzip: **Keine Backend-Änderungen nötig** — alle benötigten Events existieren bereits.

---

## 0. Executive Summary

Die Pipeline-Übersicht existiert bereits als `PipelineCanvasComponent` +
`PhaseNodeComponent` mit 9 Phasen, animierten Kanten, LLM-Branch-Nodes,
Agent-Token und Breakpoint-System.

**Bestehend & funktional:**  
Phase-Status-Tracking (6 Zustände), LLM-Call-Count pro Phase, Tool-Count,
Breakpoints (set/hit/resume), Kanten-Animationen, Agent-Token-Position,
Edge-Event-Pills, Policy-Pause/Resume.

**Gaps zum Spec (VIEW-01-PIPELINE-OVERVIEW.md):**  
5 konkrete Lücken, davon 4 reine Frontend-Änderungen und 1 Bug-Fix.

---

## 1. IST-Zustand Analyse

### 1.1 Dateien

| Datei | Zeilen | Zustand |
|-------|--------|---------|
| `pipeline-canvas.component.ts` | 98 | ✅ Vollständig |
| `pipeline-canvas.component.html` | 65 | ✅ Vollständig |
| `pipeline-canvas.component.scss` | 200 | ✅ Vollständig |
| `phase-node.component.ts` | 221 | ✅ Vollständig |
| `debug-page.component.ts` | 150+ | ✅ Vollständig |
| `agent-state.service.ts` (applyDebugEvent) | ~230 Zeilen | ✅ Vollständig |
| `debug.types.ts` | 26 | ✅ Vollständig |

### 1.2 Feature-Matrix (IST vs. SOLL)

| Feature | IST | SOLL | Gap? |
|---------|-----|------|------|
| 9 Phasen-Knoten | ✅ routing→response | ✅ | — |
| 6 Phase-States (idle/active/paused/completed/error/skipped) | ✅ | ✅ | — |
| Phase-Status aus `DebugSnapshot.phaseStates` | ✅ | ✅ | — |
| Animierter Agent-Token | ✅ translateY-Tracking | ✅ | — |
| LLM-Call-Count Badge pro Phase | ✅ `meta-badge--llm` | ✅ | — |
| Tool-Count Badge | ✅ nur bei `tool_selection` | ✅ | — |
| LLM-Branch-Nodes (Planning/Tool/Synthesis/Reflection) | ✅ 4 Branches | ✅ | — |
| LLM-Latenz in Branch-Node | ✅ `getLlmLatency()` | ✅ | — |
| Kanten-Animation (idle/active/completed) | ✅ CSS-Animation | ✅ | — |
| Edge-Event-Pills | ✅ letzte 2 Events pro Phase | ✅ | — |
| Breakpoint setzen (Right-Click) | ✅ `contextmenu` → `breakpointToggle` | ✅ | — |
| Breakpoint-Hit pausiert visuell | ✅ `debug_breakpoint_hit` → `paused` | ✅ | — |
| Breakpoint-Dot (roter Punkt) | ✅ `.bp-dot` | ✅ | — |
| Click → `selectDebugPhase()` | ✅ `phaseClick.emit()` | ✅ | — |
| Dark-Mode über CSS Custom Properties | ✅ `--c-*` vars | ✅ | — |
| `prefers-reduced-motion` | ✅ Animation-Override | ✅ | — |
| Responsive (max-width: 768px) | ✅ LLM-Branch hidden | ✅ | — |
| ARIA role="list"/role="listitem" | ✅ Canvas + Node | ✅ | — |
| **Phase-Dauer** | ⚠ Fehlerhaft | ✅ | **GAP-1** |
| **Hover-Tooltip** (Start/End/Dauer/Events) | ❌ fehlt | ✅ | **GAP-2** |
| **Keyboard-Navigation** (Tab/Arrow) | ❌ fehlt | ✅ | **GAP-3** |
| **Response-Phase activation** | ⚠ nur bei `run_completed` → `completed` | ✅ active → completed | **GAP-4** |
| **`reflection_failed` handling** | ❌ fehlt | ✅ error state | **GAP-5** |

---

## 2. Backend Events — Vollständige Abdeckung (KEINE Änderungen nötig)

### 2.1 Mapping: Spec-Requirement → Existierendes Event

| Spec-Requirement | Backend-Event | Emittiert in | Status |
|------------------|---------------|-------------|--------|
| Phase "Routing" aktivieren | `run_started` | agent.py:589 | ✅ |
| Phase "Guardrails" abschließen | `guardrails_passed` | agent.py:600 | ✅ |
| Phase "Context" aktivieren | `memory_updated`, `context_segmented`, `context_reduced` | agent.py:686,708 | ✅ |
| Phase "Planning" aktivieren | `planning_started` | agent.py:799 | ✅ |
| Phase "Planning" abschließen | `planning_completed` | agent.py:814 | ✅ |
| Phase "Tool Loop" aktivieren | `tool_started` | tool_execution_manager.py | ✅ |
| Phase "Tool Loop" Details | `tool_completed`, `tool_execution_detail` | tool_execution_manager.py | ✅ |
| Phase "Synthesis" aktivieren | `synthesis_started` | agent.py:1258 | ✅ |
| Phase "Reflection" abschließen | `reflection_completed` | agent.py:1342 | ✅ |
| Phase "Reflection" überspringen | `reflection_skipped` | agent.py:1400 | ✅ |
| Phase "Reflection" Fehler | `reflection_failed` | agent.py:1319 | ✅ |
| Phase "Reply Shaping" aktivieren | `reply_shaping_started` | agent.py:1429 | ✅ |
| Phase "Reply Shaping" abschließen | `reply_shaping_completed` | agent.py:1437 | ✅ |
| Phase "Response" abschließen | `run_completed` | agent.py:1562 | ✅ |
| Error an aktueller Phase | `run_error` | agent.py:1581 | ✅ |
| Breakpoint hit | `debug_breakpoint_hit` | agent.py:3186 | ✅ |
| LLM-Call gestartet | `debug_prompt_sent` | agent.py (4×) | ✅ |
| LLM-Call beendet | `debug_llm_response` | agent.py (4×) | ✅ |
| Policy-Pause | `policy_approval_required` | ws_handler.py | ✅ |
| Policy-Resume | `policy_approval_updated` | ws_handler.py | ✅ |
| Timestamps in jedem Event | `ts` Feld (ISO 8601) | events.py:80 | ✅ |

**Ergebnis: Alle 20 benötigten Event-Typen sind bereits implementiert.**  
Es gibt **keinen Grund**, das Backend anzufassen.

---

## 3. Implementierungsplan — 5 Gaps

### GAP-1: Phase-Dauer-Berechnung ist fehlerhaft

**Problem:**  
`getPhaseDuration()` in `pipeline-canvas.component.ts:86-93` filtert nach
`event.details?.['phase'] === phaseId`.  Das funktioniert nur für Events die
ein `phase`-Feld in `details` haben (z.B. `debug_prompt_sent`).  Die meisten
Lifecycle-Events haben **kein** `phase`-Feld in details — stattdessen signalisiert
der `stage`-Name die Phase (z.B. `planning_started` → `planning_completed`).

**Aktuelle (fehlerhafte) Implementierung:**
```typescript
// pipeline-canvas.component.ts:86-93
getPhaseDuration(phaseId: PipelinePhase): number | null {
    const events = this.eventLog.filter(e => e.details?.['phase'] === phaseId);
    if (events.length < 2) return null;
    const start = new Date(events[0].timestamp).getTime();
    const end = new Date(events[events.length - 1].timestamp).getTime();
    return end - start || null;
}
```

**Fix:**  
Statt nach `details.phase` zu filtern, die Start/End-Events der jeweiligen Phase
direkt per `stage`-Name matchen.

**Neue Implementierung:**
```typescript
private static readonly PHASE_EVENTS: Record<string, [start: string, end: string]> = {
    routing:        ['run_started',             'guardrails_passed'],
    guardrails:     ['run_started',             'guardrails_passed'],     // Same events — guardrails is instant
    context:        ['memory_updated',          'planning_started'],
    planning:       ['planning_started',        'planning_completed'],
    tool_selection: ['tool_started',            'synthesis_started'],
    synthesis:      ['synthesis_started',        'reflection_completed'],
    reflection:     ['reflection_completed',     'reflection_completed'],  // Single event — use latencyMs from llmCalls
    reply_shaping:  ['reply_shaping_started',   'reply_shaping_completed'],
    response:       ['reply_shaping_completed', 'run_completed'],
};

getPhaseDuration(phaseId: PipelinePhase): number | null {
    const pair = PipelineCanvasComponent.PHASE_EVENTS[phaseId];
    if (!pair) return null;
    const [startStage, endStage] = pair;
    const startEvt = this.eventLog.find(e => e.stage === startStage);
    const endEvt = this.eventLog.find(e => e.stage === endStage);
    if (!startEvt || !endEvt) return null;
    if (startStage === endStage) return null;  // Can't compute duration from single event
    const ms = new Date(endEvt.timestamp).getTime() - new Date(startEvt.timestamp).getTime();
    return ms > 0 ? ms : null;
}
```

**Datei:** `pipeline-canvas.component.ts`  
**Aufwand:** Ersetze `getPhaseDuration()` Methode + füge `PHASE_EVENTS` Map hinzu  
**Risiko:** Niedrig — rein additive Logik-Änderung

---

### GAP-2: Hover-Tooltip mit Phase-Details

**Problem:**  
Laut Spec soll ein Hover-Tooltip zeigen: Start-Zeit, End-Zeit, Dauer,
Event-Count.  Aktuell gibt es keinen Tooltip auf den Phase-Nodes.

**Lösung:**  
Einen berechneten Tooltip-String als neuen `@Input()` an `PhaseNodeComponent`
übergeben und dort als `[title]` binden.

**Änderungen:**

**(a) `pipeline-canvas.component.ts`** — neue Methode:
```typescript
getPhaseTooltip(phaseId: PipelinePhase): string {
    const pair = PipelineCanvasComponent.PHASE_EVENTS[phaseId];
    if (!pair) return '';
    const [startStage, endStage] = pair;
    const startEvt = this.eventLog.find(e => e.stage === startStage);
    const endEvt = this.eventLog.find(e => e.stage === endStage);
    const eventCount = this.eventLog.filter(e => {
        const startIdx = this.eventLog.indexOf(startEvt!);
        const endIdx = this.eventLog.indexOf(endEvt!);
        const idx = this.eventLog.indexOf(e);
        return startIdx >= 0 && endIdx >= 0 && idx >= startIdx && idx <= endIdx;
    }).length;
    const parts: string[] = [];
    if (startEvt) parts.push('Start: ' + startEvt.timestamp);
    if (endEvt && endEvt !== startEvt) parts.push('End: ' + endEvt.timestamp);
    const dur = this.getPhaseDuration(phaseId);
    if (dur) parts.push('Dauer: ' + (dur < 1000 ? dur + 'ms' : (dur/1000).toFixed(1) + 's'));
    if (eventCount > 0) parts.push('Events: ' + eventCount);
    return parts.join('\n');
}
```

**(b) `phase-node.component.ts`** — neuer `@Input()`:
```typescript
@Input() tooltip = '';
```
Und im Template:
```html
<div class="phase-node" ... [title]="tooltip">
```

**(c) `pipeline-canvas.component.html`** — neues Binding auf `<app-phase-node>`:
```html
[tooltip]="getPhaseTooltip(phase.id)"
```

**Aufwand:** 3 Dateien, je 2-5 Zeilen  
**Risiko:** Niedrig

---

### GAP-3: Keyboard-Navigation (Tab + Arrow Keys)

**Problem:**  
Phase-Nodes sind per `cursor: pointer` klickbar, aber nicht per Tastatur
navigierbar.  Es fehlen `tabindex`, `keydown`-Handler und Focus-Management.

**Lösung:**

**(a) `phase-node.component.ts`** — `tabindex="0"` und `keydown`-Handler:
```html
<div class="phase-node"
     ...
     tabindex="0"
     (keydown.enter)="breakpointToggle.emit()"
     (keydown.space)="$event.preventDefault(); breakpointToggle.emit()">
```

> Hinweis: Click auf den Node triggert `phaseClick` (vom Parent gehandled),
> Enter/Space triggert den Breakpoint-Toggle — analog zum Right-Click.
> Das ist sinnvoll, weil Click → Phase-Selection der häufigere Use-Case ist
> und per Tab+Enter erreichbar sein sollte.

Korrektur: Der `(click)` liegt auf dem Parent (`pipeline-canvas.component.html`),
nicht auf `phase-node`.  Also brauchen wir im `phase-node`:
```html
tabindex="0"
(keydown.enter)="$event.stopPropagation()"
(keydown.space)="$event.preventDefault()"
```
Und der Parent bindet einen `(keydown.enter)` auf dem `<app-phase-node>`:
Das ist nicht nötig — Angular propagiert `(click)` auch bei Enter auf
fokussierte Elemente mit `tabindex="0"`. Also reicht:

**Minimale Änderung in `phase-node.component.ts`:**
```html
<div class="phase-node" ... tabindex="0">
```

Angular's Event-System löst `click` bei Enter auf fokussierbaren Elementen aus.
Space für Breakpoint-Toggle ist optional (Right-Click-Replacement).

**Aufwand:** 1 Attribut hinzufügen  
**Risiko:** Niedrig

---

### GAP-4: Response-Phase wird nie "active"

**Problem:**  
Im `applyDebugEvent()` gibt es keinen Event, der die `response`-Phase auf
`'active'` setzt.  `run_completed` setzt sie direkt auf `'completed'`.
Das bedeutet: der Agent-Token springt nie zur `response`-Phase, und die
Kante von `reply_shaping` zu `response` wird nie als `active` animiert.

**Idealer Auslöser:**  
Der beste Zeitpunkt für `response: active` ist, wenn `reply_shaping_completed`
eintrifft — dann ist Reply Shaping fertig und die Response-Phase beginnt.

**Fix in `agent-state.service.ts`:**

```typescript
case 'reply_shaping_completed':
    next = {
        ...next,
        phaseStates: new Map(d.phaseStates)
            .set('reply_shaping', 'completed')
            .set('response', 'active'),          // ← NEU
        currentPhase: 'response' as PipelinePhase, // ← NEU
    };
    break;
```

**Datei:** `agent-state.service.ts`  
**Aufwand:** 2 Zeilen ändern  
**Risiko:** Niedrig — rein additive State-Transition

---

### GAP-5: `reflection_failed` setzt keinen Error-State

**Problem:**  
`applyDebugEvent()` hat keinen `case 'reflection_failed'`.  Wenn die Reflection
fehlschlägt (LLM-Timeout, Parse-Error), bleibt die `reflection`-Phase als
`active` hängen.

Events im Backend: `reflection_failed` wird emittiert mit
`{"pass": int, "error": str}` (agent.py:1319-1328).

**Fix in `agent-state.service.ts`:**

```typescript
case 'reflection_failed':
    next = {
        ...next,
        phaseStates: new Map(d.phaseStates)
            .set('synthesis', 'completed')
            .set('reflection', 'error'),
    };
    break;
```

Einfügen nach dem bestehenden `case 'reflection_skipped'`.

**Datei:** `agent-state.service.ts`  
**Aufwand:** 7 Zeilen  
**Risiko:** Niedrig — rein additive Case-Behandlung

---

## 4. Zusammenfassung der Änderungen

### 4.1 Dateien mit Änderungen

| # | Datei | Änderung | Lines |
|---|-------|----------|-------|
| 1 | `frontend/.../pipeline-canvas.component.ts` | `PHASE_EVENTS` Map + `getPhaseDuration()` Fix + `getPhaseTooltip()` | ~30 |
| 2 | `frontend/.../pipeline-canvas.component.html` | `[tooltip]` Binding auf `<app-phase-node>` | 1 |
| 3 | `frontend/.../phase-node.component.ts` | `@Input() tooltip` + `[title]` + `tabindex="0"` | 3 |
| 4 | `frontend/.../agent-state.service.ts` | `reply_shaping_completed` erweitern + `reflection_failed` Case | 12 |

### 4.2 Dateien OHNE Änderungen

| Datei | Warum nicht? |
|-------|-------------|
| `pipeline-canvas.component.scss` | Alle CSS-Klassen/Animationen existieren bereits |
| `debug-page.component.ts` | Projiziert bereits alle benötigten Felder |
| `debug-page.component.html` | Bindings sind vollständig |
| `debug.types.ts` | Keine neuen Types nötig |
| **Alle Backend-Dateien** | **Alle Events existieren bereits** |

### 4.3 Backend-Änderungen: KEINE

Alle 20 benötigten Event-Typen werden bereits emittiert:
- `run_started`, `guardrails_passed`, `memory_updated`, `context_segmented`,
  `context_reduced`, `planning_started`, `planning_completed`,
  `tool_started`, `tool_completed`, `tool_execution_detail`,
  `synthesis_started`, `reflection_completed`, `reflection_skipped`,
  `reflection_failed`, `reply_shaping_started`, `reply_shaping_completed`,
  `run_completed`, `run_error`, `debug_prompt_sent`, `debug_llm_response`,
  `debug_breakpoint_hit`

Timestamps (`ts` Feld) sind in jedem Event vorhanden (ISO 8601).
Latenz-Daten sind in `debug_llm_response` und `tool_completed` enthalten.

---

## 5. Implementierungsreihenfolge

| Step | Gap | Beschreibung | Abhängigkeiten |
|------|-----|-------------|----------------|
| 1 | GAP-5 | `reflection_failed` Case in `applyDebugEvent` | — |
| 2 | GAP-4 | `response` Phase activation bei `reply_shaping_completed` | — |
| 3 | GAP-1 | `PHASE_EVENTS` Map + `getPhaseDuration()` Fix | — |
| 4 | GAP-2 | `getPhaseTooltip()` + `@Input() tooltip` + Template-Binding | GAP-1 (nutzt `PHASE_EVENTS`) |
| 5 | GAP-3 | `tabindex="0"` auf Phase-Node | — |

Steps 1, 2, 5 sind unabhängig voneinander.  
Step 3 muss vor Step 4 abgeschlossen sein.

---

## 6. Test-Strategie

### 6.1 Manuell

| Test | Erwartung | Gap |
|------|-----------|-----|
| Run starten, alle 9 Phasen beobachten | Alle Phasen durchlaufen idle → active → completed | GAP-4 |
| Phase-Dauer-Badges prüfen | Realistische Werte (Planning: ~3s, Synthesis: ~5s) | GAP-1 |
| Hover über Phase-Node | Tooltip mit Start/End/Dauer/Events | GAP-2 |
| Tab-Taste durch alle Nodes | Focus-Ring wandert, Enter selektiert Phase | GAP-3 |
| Reflection-Fehler provozieren (z.B. LLM offline) | Reflection-Phase zeigt Error (rot) | GAP-5 |
| Response-Phase "active" prüfen | Kante reply_shaping→response animiert, dann completed | GAP-4 |

### 6.2 Unit-Tests (optional, empfohlen)

| Test | Datei |
|------|-------|
| `getPhaseDuration('planning')` mit mock eventLog | `pipeline-canvas.component.spec.ts` |
| `applyDebugEvent({stage:'reflection_failed'})` setzt error | `agent-state.service.spec.ts` |
| `applyDebugEvent({stage:'reply_shaping_completed'})` setzt response active | `agent-state.service.spec.ts` |

---

## 7. Definition of Done

- [ ] Alle 9 Phasen zeigen korrekte Dauer-Badges (GAP-1)
- [ ] Hover-Tooltip zeigt Start, End, Dauer, Event-Count (GAP-2)
- [ ] Tab-Taste navigiert durch alle Phase-Nodes (GAP-3)
- [ ] Response-Phase wird `active` bevor sie `completed` wird (GAP-4)
- [ ] `reflection_failed` setzt Reflection-Phase auf `error` (GAP-5)
- [ ] Build erfolgreich (`ng build --configuration=development`)
- [ ] Keine neuen TypeScript-Fehler
- [ ] Keine Backend-Änderungen nötig
