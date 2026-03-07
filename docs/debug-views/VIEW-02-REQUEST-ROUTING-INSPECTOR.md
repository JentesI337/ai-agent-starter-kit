# VIEW-02 — Request & Routing Inspector

> Vollständige Transparenz über den eingehenden Request und die Agent-Routing-Entscheidung.

---

## 1. Warum brauchen wir diesen View?

Der Agent-Routing-Mechanismus entscheidet **vor** der eigentlichen Verarbeitung,
welcher der 15 spezialisierten Agents den Request bearbeitet.  Diese
Entscheidung ist aktuell **komplett unsichtbar** — der Nutzer sieht nur das
Endergebnis, aber nicht:

- Welche Envelope-Felder der Request hatte (agent_id, model, preset, prompt_mode, etc.)
- Warum ein bestimmter Agent gewählt wurde (explizit, Preset, Capability-Match, Default)
- Wie die Capability-Scores der 15 Agents aussahen
- Ob ein Model-Override oder Preset aktiv war

**Ohne diesen View** kann der Nutzer nicht nachvollziehen, warum sein Request
z.B. beim `head-agent` statt beim `coder-agent` gelandet ist, obwohl er eine
Code-Frage gestellt hat.

---

## 2. Datenquellen

### 2.1 Envelope-Daten (Request-Seite)

Aus dem eingehenden WebSocket-Message (`WsInboundEnvelope` in `models.py`):

| Feld | Typ | Relevanz |
|------|-----|----------|
| `type` | string | `user_message`, `clarification_response`, `policy_decision` |
| `content` | string | Der eigentliche User-Text (bis 200.000 chars) |
| `agent_id` | string? | Expliziter Agent-Wunsch |
| `mode` | string? | Operating-Mode |
| `preset` | string? | Preset-Override (z.B. `review`) |
| `model` | string? | Model-Override |
| `session_id` | string? | Session-Kontext |
| `runtime_target` | string? | Runtime-Backend |
| `queue_mode` | string? | Queue-Verhalten |
| `prompt_mode` | string? | Prompt-Variante |
| `tool_policy` | object? | Tool-Einschränkungen |
| `reasoning_level` | string? | Reasoning-Tiefe-Override |
| `reasoning_visibility` | string? | Reasoning-Steps sichtbar? |

### 2.2 Routing-Entscheidung (Agent-Seite)

Aus `route_agent_for_message()`:

| Datenpunkt | Verfügbar über |
|------------|----------------|
| Gewählter Agent | `run_started` Event `details.agent` |
| Routing-Grund | **Fehlt aktuell** — muss als neues Lifecycle-Event hinzugefügt werden |
| Capability-Scores | **Fehlt aktuell** — muss als neues Lifecycle-Event hinzugefügt werden |
| Request-ID | `run_started` Event `request_id` |
| Session-ID | `run_started` Event `session_id` |

### 2.3 Benötigte neue Backend-Events

| Event-Stage | Details | Wann emittiert |
|-------------|---------|----------------|
| `agent_routing_decision` | `{ agent, reason, routing_method, scores: { agent_name: score }[] }` | Nach `route_agent_for_message()` in `ws_handler.py` |
| `request_envelope_received` | `{ type, agent_id, preset, model, prompt_mode, content_length, session_id }` | Beim Empfang des Envelopes (OHNE `content` — Datenschutz!) |

---

## 3. UI-Struktur

### 3.1 Request-Sektion

```
┌─ Request Envelope ──────────────────────────────┐
│ Type:           user_message                     │
│ Request-ID:     abc-123-def                      │
│ Session-ID:     sess-456                         │
│ Content Length:  847 chars                        │
│ Agent Override:  —                                │
│ Model Override:  gpt-oss:20b-cloud               │
│ Preset:         —                                │
│ Prompt Mode:    —                                │
│ Runtime:        local                            │
│ Tool Policy:    { allow: [...], deny: [...] }    │
└──────────────────────────────────────────────────┘
```

- Felder mit Wert = farbig hervorgehoben
- Felder ohne Wert (`null`) = ausgegraut mit `—`
- `content` wird **nicht** angezeigt (bereits in Chat-View sichtbar, Datenschutz)
- Nur `content_length` als Metrik

### 3.2 Routing-Entscheidung-Sektion

```
┌─ Agent Routing ─────────────────────────────────┐
│ ✓ Routed to: coder-agent                        │
│ Method: capability_matching                      │
│                                                  │
│ Scoring:                                         │
│ ▓▓▓▓▓▓▓▓▓▓░░  coder-agent        0.85          │
│ ▓▓▓▓▓▓▓░░░░░  architect-agent    0.62          │
│ ▓▓▓▓▓░░░░░░░  head-agent         0.45          │
│ ▓▓▓░░░░░░░░░  review-agent       0.28          │
│ ▓░░░░░░░░░░░  researcher-agent   0.12          │
│ ...                                              │
└──────────────────────────────────────────────────┘
```

- Horizontal Bar-Chart für alle 15 Agents, sortiert nach Score
- Gewählter Agent hervorgehoben mit Accent-Farbe
- Routing-Methode als Badge: `explicit` | `preset` | `capability_matching` | `default`

### 3.3 Zusammenfassung

Einzeilige Summary oberhalb:
```
coder-agent via capability_matching · gpt-oss:20b-cloud · sess-456 · 847 chars
```

---

## 4. Dos

- **Content nie anzeigen** — nur `content_length` (Content ist im Chat-View sichtbar)
- Envelope-Felder als Key-Value-Grid rendern (Label links, Wert rechts)
- Scores als horizontale Balken (nur CSS, kein Canvas/SVG)
- Änderungen an der Routing-Logik im Backend als neue Lifecycle-Events exponieren
- Null-Felder sichtbar machen (mit `—`) statt verstecken — Transparenz
- `track agent.name` für die Score-Liste

## 5. Don'ts

- **Niemals** den `content`-Text des Users in diesem View anzeigen
- **Keine** eigene WebSocket-Verbindung — alles über `AgentStateService.debug$`
- **Keine** Agent-Liste hardcoden — dynamisch aus den Score-Daten lesen
- **Nicht** den View rendern bevor `run_started` eingeht — Platzhalter zeigen
- **Kein** Polling für Routing-Daten — Event-basiert
- **Keine** Interaktion die den laufenden Run beeinflusst (read-only View)

---

## 6. Akzeptanzkriterien

### Funktional

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| F-01 | Alle Envelope-Felder werden angezeigt (mit Wert oder `—`) | Visuell: 13 Felder sichtbar |
| F-02 | Request-ID und Session-ID sind korrekt | Vergleich mit `run_started` Event |
| F-03 | Gewählter Agent wird korrekt angezeigt | Vergleich mit `run_started` Event `agent` Feld |
| F-04 | Routing-Methode wird als Badge angezeigt | Backend muss `agent_routing_decision` Event senden |
| F-05 | Capability-Scores aller Agents werden als Balkendiagramm dargestellt | Backend muss Scores im Event mitsenden |
| F-06 | Score-Balken sind nach Wert sortiert (höchster oben) | Visuell überprüfen |
| F-07 | View aktualisiert sich live bei neuem Run | E2E: neuen Request senden → View aktualisiert |
| F-08 | Content-Length wird angezeigt, aber NICHT der Content selbst | Code-Review + visuell |

### Visuell

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| V-01 | Key-Value-Grid ist aligned und lesbar | Visuell |
| V-02 | Score-Balken nutzen CSS Custom Properties für Farben | Code-Review |
| V-03 | Gewählter Agent visuell hervorgehoben (Accent-Farbe) | Visuell |
| V-04 | Dark-Theme kompatibel | Visuell im Dark-Mode prüfen |

### Backend-Voraussetzungen

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| B-01 | `request_envelope_received` Event wird gesendet | Backend-Log oder Event-Timeline |
| B-02 | `agent_routing_decision` Event mit Scores wird gesendet | Backend-Log oder Event-Timeline |
| B-03 | Content ist NICHT im Event enthalten | Code-Review des Backend-Events |

### Accessibility

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| A-01 | Score-Balken haben `aria-valuenow`, `aria-valuemin`, `aria-valuemax` | Code-Review |
| A-02 | Key-Value-Paare als `<dl>/<dt>/<dd>` oder equivalent ARIA | Code-Review |

---

## 7. Abhängigkeiten

- **Backend-Änderung erforderlich:** 2 neue Lifecycle-Events (`request_envelope_received`, `agent_routing_decision`)
- `AgentStateService.debug$` — muss die neuen Events im `DebugSnapshot` speichern
- `applyDebugEvent()` — neuer Switch-Case für die beiden Events
- Routing-Logik in `ws_handler.py` / `route_agent_for_message()` muss Scores exponieren

## 8. Status

**Existiert nicht.** Komplett neuer View.  Backend-Änderung ist Voraussetzung.
