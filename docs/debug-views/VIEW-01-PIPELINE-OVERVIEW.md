# VIEW-01 — Pipeline Overview

> Gesamtübersicht des 8-Phasen-Reasoning-Flows als interaktiver Live-Graph.

---

## 1. Warum brauchen wir diesen View?

Der Pipeline Overview ist der **zentrale Einstiegspunkt** für die Debug-Seite.
Ohne ihn weiß der Nutzer nicht, in welcher Phase sich der Agent gerade
befindet, welche Phasen bereits abgeschlossen sind und wo Probleme auftraten.

- Ein Agent-Run durchläuft bis zu 8 Phasen (Routing → Guardrails → Memory →
  Planning → Tool Loop → Synthesis → Reflection → Response).
- Jede Phase kann idle, active, completed, paused, error oder skipped sein.
- Der Nutzer muss auf einen Blick sehen: **Wo bin ich?  Was dauert wie lange?
  Wo hängt es?**

Ohne diesen View ist die Debug-Seite eine lose Sammlung von Inspektoren ohne
gemeinsamen Kontext.

---

## 2. Datenquellen

| Datenfeld | Herkunft | Lifecycle-Events |
|-----------|----------|------------------|
| Phase-Status | `DebugSnapshot.phaseStates` (Map) | `run_started`, `guardrails_passed`, `planning_started`, `planning_completed`, `tool_started`, `tool_completed`, `synthesis_started`, `reflection_completed`, `run_completed`, `run_error` |
| Aktuelle Phase | `DebugSnapshot.currentPhase` | Wird bei jedem Phase-Wechsel aktualisiert |
| Breakpoints | `DebugSnapshot.activeBreakpoints` (Set) | `debug_breakpoint_hit` |
| Phase-Dauer | Berechnet aus Event-Timestamps (start → completed) | Alle `*_started` / `*_completed` Paare |
| LLM-Call-Zähler pro Phase | `DebugSnapshot.llmCalls` gefiltert nach `phase` | `debug_prompt_sent` |
| Tool-Zähler pro Phase | `DebugSnapshot.toolExecutions.length` | `tool_completed`, `tool_execution_detail` |
| Edge-Events | Events zwischen zwei Phasen | Alle Events im `eventLog` |

---

## 3. UI-Struktur

### 3.1 Phasen-Knoten (9 Stück)

```
[Routing] → [Guardrails] → [Context] → [Planning] → [Tool Selection] →
[Synthesis] → [Reflection] → [Reply Shaping] → [Response]
```

Jeder Knoten zeigt:
- **Icon** — phase-spezifisch (Router, Shield, Brain, Map, Wrench, Sparkle, Mirror, Filter, Send)
- **Label** — Phasenname
- **Status-Badge** — farbig (grau=idle, blau=active spinning, grün=completed, gelb=paused, rot=error)
- **Duration** — Dauer der Phase in ms (nur wenn completed)
- **LLM-Call-Count** — wie viele LLM-Calls in dieser Phase (Bubble oben rechts)
- **Breakpoint-Indikator** — roter Punkt, wenn Breakpoint gesetzt

### 3.2 Kanten (Verbindungen)

- Grau = noch nicht erreicht
- Animierte blaue Linie = Übergang gerade aktiv
- Grün = Übergang abgeschlossen
- Rot = Übergang fehlgeschlagen

### 3.3 Interaktion

- **Click auf Knoten** → `selectDebugPhase(phase)` → andere Inspektoren zeigen Daten dieser Phase
- **Right-Click auf Knoten** → Breakpoint ein/aus Toggle
- **Hover** → Tooltip mit Details: Start-Zeit, End-Zeit, Dauer, Event-Count

---

## 4. Dos

- Phase-Status aus dem zentralisierten `DebugSnapshot` beziehen (nicht lokalen State halten)
- Animationen mit CSS-Transitions (`transition: var(--t)`) — keine JS-Animationen
- `@for` mit `track phase.id` — eindeutige Track-Keys
- `ChangeDetectorRef.detectChanges()` nach jedem `debug$`-Update aufrufen
- ARIA-Labels für jeden Knoten (`role="listitem"`, `aria-label="Phase: Planning, Status: completed"`)
- Responsive: Horizontal-Scroll in einem Container auf kleinen Screens
- Virtualisierung nicht nötig (nur 9 Knoten) — direkt rendern

## 5. Don'ts

- **Keinen** lokalen State für Phasen-Status halten — immer aus `AgentStateService.debug$`
- **Keinen** Timer/Polling für Phase-Dauer — berechne aus Event-Timestamps
- **Keine** hardcodierten Farben — CSS Custom Properties (`--c-accent`, `--c-red`, etc.)
- **Keine** Angular-Lifecycle-Hooks zum Umsetzen von Phase-Status verwenden — nur Subscription
- **Nicht** alle 9 Phasen rendern, wenn die Pipeline noch nicht gestartet hat (idle state: nur Platzhalter)
- **Keine** blockierenden Animationen die den Scrollfluss stören

---

## 6. Akzeptanzkriterien

### Funktional

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| F-01 | Alle 9 Phasen werden als Knoten dargestellt | Visuell: 9 Knoten sichtbar bei idle |
| F-02 | Klick auf Knoten setzt `selectedPhase` im Service | Unit-Test: `selectDebugPhase()` wird aufgerufen |
| F-03 | Phase-Status ändert sich live bei eingehenden Events | E2E: `run_started` → Routing wird `active`, `guardrails_passed` → Guardrails wird `completed` |
| F-04 | Phase-Dauer wird korrekt berechnet und angezeigt | Unit-Test: Differenz zwischen `*_started` und `*_completed` Timestamps |
| F-05 | LLM-Call-Count zeigt korrekte Anzahl pro Phase | Unit-Test: Filtere `llmCalls` nach `phase`, zähle |
| F-06 | Breakpoints können per Klick gesetzt/entfernt werden | E2E: Toggle-Click, prüfe `activeBreakpoints` Set |
| F-07 | Breakpoint-Hit pausiert die Pipeline visuell | E2E: `debug_breakpoint_hit` → Phase zeigt gelben Status |
| F-08 | Error-State wird korrekt angezeigt (rote Phase) | E2E: `run_error` → betroffene Phase zeigt roten Status |

### Visuell

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| V-01 | Dark-Theme: alle Farben über CSS Custom Properties | Code-Review: keine hardcodierten Farbwerte |
| V-02 | Knoten-Größe mindestens 44×44px (Touch-Target) | CSS-Prüfung |
| V-03 | Status-Animationen smooth (keine Sprünge) | Visuell: `transition` auf Status-Änderung |
| V-04 | Kanten-Animation läuft bei Phase-Übergang | Visuell: blaue animierte Linie |

### Performance

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| P-01 | Kein Flackern bei schnellen Phase-Wechseln | Visuell: 5+ Events in <1s dürfen nicht flackern |
| P-02 | Kein Memory-Leak bei Subscription | Code-Review: `ngOnDestroy` unsubscribes |

### Accessibility

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| A-01 | Keyboard-Navigation zwischen Knoten (Tab/Arrow) | Manuell: Tab-Reihenfolge prüfen |
| A-02 | Screen-Reader liest Phase + Status vor | ARIA: `aria-label` auf jedem Knoten |
| A-03 | Focus-Ring sichtbar bei Keyboard-Navigation | CSS: `focus-visible` Outline |

---

## 7. Abhängigkeiten

- `AgentStateService.debug$` — liefert `DebugSnapshot`
- `PipelinePhase` Type — definiert gültige Phasen-IDs
- `PhaseState` Type — definiert gültige Status-Werte
- Backend: `_emit_lifecycle()` muss alle relevanten Events feuern

## 8. Status

**Existiert bereits** als `PipelineCanvasComponent` — muss überprüft und ggf.
erweitert werden für fehlende Metriken (Duration, LLM-Count-Badges).
