# VIEW-03 — Guardrail Monitor

> Echtzeit-Übersicht über alle Sicherheits- und Validierungsprüfungen vor der Verarbeitung.

---

## 1. Warum brauchen wir diesen View?

Guardrails sind die **erste Verteidigungslinie** gegen ungültige, gefährliche
oder malformierte Requests.  Aktuell sieht der Nutzer nur ein
`guardrails_passed` Event im Log — aber kein Detail darüber:

- **Welche 5 Checks** wurden durchgeführt?
- **Was hat der Check geprüft** (z.B. Message-Länge 847 vs. Limit 8000)?
- **Warum wurde ein Request abgelehnt?** (welcher Check, welcher Grund)
- **Tool Policy Resolution** — welche Policy wurde aufgelöst?
- **Toolchain Check** — sind alle Tool-Definitionen konsistent?
- **MCP Tools** — wurden externe Tools registriert?

**Ohne diesen View** gibt es keine Möglichkeit zu verstehen, warum ein
Request gar nicht erst verarbeitet wurde, oder ob die Tool-Policy korrekt
aufgelöst wurde.

---

## 2. Datenquellen

### 2.1 Guardrail-Checks (5 Stück, aus `_validate_guardrails()`)

| # | Check | Input | Grenzwert | Event |
|---|-------|-------|-----------|-------|
| 1 | Empty message | `len(message.strip())` | `> 0` | Rejektion: `request_failed_guardrail` |
| 2 | Message length | `len(message)` | `≤ 8000` (default) | Rejektion: `request_failed_guardrail` |
| 3 | Session-ID length | `len(session_id)` | `≤ 120` | Rejektion: `request_failed_guardrail` |
| 4 | Session-ID charset | Regex `[^A-Za-z0-9_-]` | Nur alphanum + `_-` | Rejektion: `request_failed_guardrail` |
| 5 | Model name length | `len(model)` | `≤ 120` | Rejektion: `request_failed_guardrail` |

### 2.2 Post-Guardrail-Initialisierung

| Schritt | Event-Stage | Details |
|---------|-------------|---------|
| Tool Policy Resolution | `tool_policy_resolved` | `{ policy_type, allowed_tools, denied_tools }` |
| MCP Tools Registration | `mcp_tools_initialized` / `mcp_tools_failed` | `{ tool_count }` |
| Toolchain Check | `toolchain_checked` | `{ tool_count, issues }` |

### 2.3 Benötigte neue Backend-Events

| Event-Stage | Details | Wann |
|-------------|---------|------|
| `guardrail_check_completed` | `{ checks: [{ name, passed, actual_value, limit, reason? }] }` | Nach `_validate_guardrails()` — Einzelauflistung aller 5 Checks mit Ergebnis |

---

## 3. UI-Struktur

### 3.1 Checklist-View

```
┌─ Guardrails ─────────────────────────────────────┐
│                                                   │
│  ✓  Message not empty       847 chars             │
│  ✓  Message length          847 / 8000            │  ▓▓▓░░░░  10.6%
│  ✓  Session-ID length       8 / 120               │  ▓░░░░░░   6.7%
│  ✓  Session-ID charset      [a-z0-9_-] ✓          │
│  ✓  Model name length       23 / 120              │  ▓░░░░░░  19.2%
│                                                   │
│  Result: ✓ All 5 checks passed                    │
└───────────────────────────────────────────────────┘
```

Jeder Check zeigt:
- **Status-Icon** — ✓ grün oder ✕ rot
- **Check-Name** — beschreibend
- **Aktueller Wert** — z.B. `847 chars`
- **Limit** — z.B. `/ 8000` (wo relevant)
- **Progress-Balken** — visuell wie weit vom Limit (wo relevant)

Bei Rejektion:
- Betroffener Check rot markiert
- Rejection-Reason als roter Hint-Text darunter

### 3.2 Post-Init-Sektion

```
┌─ Initialization ─────────────────────────────────┐
│                                                   │
│  Tool Policy                                      │
│  ├─ Type: envelope_override                       │
│  ├─ Allowed: read_file, list_dir, grep_search     │
│  └─ Denied:  run_command, code_execute            │
│                                                   │
│  MCP Tools                                        │
│  └─ 3 tools registered ✓                          │
│                                                   │
│  Toolchain                                        │
│  └─ 18 tools verified, 0 issues ✓                 │
└───────────────────────────────────────────────────┘
```

### 3.3 Zusammenfassungs-Badge

Einfacher Badge auf dem Pipeline-Knoten:
- `5/5 ✓` (grün) — alle Checks bestanden
- `4/5 ✕` (rot) — ein Check fehlgeschlagen

---

## 4. Dos

- Alle 5 Checks **immer** anzeigen, auch wenn sie bestanden wurden — volle Transparenz
- Aktuelle Werte und Limits anzeigen (nicht nur pass/fail)
- Progress-Balken für numerische Checks (Length-Checks) — visualisiert wie nah am Limit
- Guardrail-Rejektion mit klarer Fehlermeldung + betroffener Check rot
- Tool-Policy als Tree-View rendern (Type → Allowed/Denied)
- Animierter Übergang beim Erscheinen der Check-Ergebnisse (staggered reveal)

## 5. Don'ts

- **Nicht** den Message-Content anzeigen — nur die Länge
- **Keine** Manuell-Override-Buttons — Guardrails sind nicht konfigurierbar zur Laufzeit
- **Nicht** die Checks clientseitig berechnen — immer Backend-Daten verwenden
- **Keine** unterschiedlichen Views für pass/fail — gleiche Struktur, nur Farbe ändert sich
- **Nicht** die MCP-Tool-Liste im Detail aufklappen (gehört in den Tool Catalog View)
- **Kein** Polling — Event-basiert

---

## 6. Akzeptanzkriterien

### Funktional

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| F-01 | Alle 5 Guardrail-Checks werden als Liste angezeigt | Visuell: 5 Zeilen sichtbar |
| F-02 | Jeder Check zeigt Status (pass/fail), aktuellen Wert und Limit | Visuell + Unit-Test |
| F-03 | Bei Rejektion wird der fehlgeschlagene Check rot markiert | E2E: Request mit >8000 chars senden |
| F-04 | Tool-Policy-Resolution wird als Tree angezeigt | Visuell nach `tool_policy_resolved` Event |
| F-05 | MCP-Status wird angezeigt (Tool-Count oder Fehler) | Visuell nach `mcp_tools_initialized`/`failed` |
| F-06 | Toolchain-Check-Ergebnis wird angezeigt | Visuell nach `toolchain_checked` Event |
| F-07 | View aktualisiert live bei neuem Run | E2E: neuen Request senden |

### Visuell

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| V-01 | Progress-Balken für Length-Checks | Visuell: Balken proportional zum Limit |
| V-02 | Grün/Rot-Farbschema konsistent mit rest der App | CSS Custom Properties |
| V-03 | Staggered Animation beim Erscheinen der Checks | Visuell: Checks erscheinen nacheinander |

### Backend-Voraussetzungen

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| B-01 | `guardrail_check_completed` Event mit allen 5 Check-Details | Backend-Event prüfen |
| B-02 | Existing Events (`tool_policy_resolved`, `toolchain_checked`) haben ausreichend Details | Backend-Event prüfen |

### Accessibility

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| A-01 | Checklist als `role="list"` mit `role="listitem"` | Code-Review |
| A-02 | Status per `aria-label` kommuniziert ("Check bestanden" / "Check fehlgeschlagen") | Screen-Reader Test |
| A-03 | Progress-Balken mit `aria-valuenow`/`aria-valuemax` | Code-Review |

---

## 7. Abhängigkeiten

- **Backend-Änderung erforderlich:** Neues `guardrail_check_completed` Event mit Einzelcheck-Details
- `AgentStateService.applyDebugEvent()` — neuer Case für `guardrail_check_completed`
- `DebugSnapshot` — neues Feld `guardrailChecks: GuardrailCheck[]`
- Existing Events `tool_policy_resolved`, `toolchain_checked` müssen parsed werden

## 8. Status

**Existiert nicht.** Komplett neuer View.  Backend-Änderung erforderlich für
detaillierte Check-Ergebnisse (aktuell wird nur `guardrails_passed` gesendet).
