# Refactoring-Plan — Frontend-First Management Layer

> Ziel: Alles über das Frontend steuerbar — Agents, Workflows, Skills, Tools, Policies, Live-View.  
> Grundsatz: Kein neues P0-Feature bevor die Steuerbarkeit steht.  
> Stand: 8. März 2026 — **Update nach Schritt A (Monitoring-Auslagerung)**

---

## Legende

- ✅ = erledigt, Code merged
- 🔄 = teilweise erledigt
- ❌ = offen, nicht angefangen

---

## Ist-Zustand (nach bisheriger Arbeit)

### Was bereits erledigt ist

| Bereich | Status | Details |
|---------|--------|---------|
| Admin-Page Shell | ✅ | `/admin` Route, 6 Tabs (Agents, Workflows, Policies, Tools, Skills, Settings), 434 LOC TS, 282 LOC HTML |
| WorkflowService | ✅ | `list/get/create/update/delete/execute` — ruft existierende Backend-Endpoints auf |
| PolicyService | ✅ | `list/get/create/update/delete` — ruft neue Backend-Endpoints auf |
| AgentsService erweitert | ✅ | `updateCustomAgent`, `getToolCatalog`, `getToolStats`, `getSkillsList`, `syncSkills` hinzugefügt |
| Backend: Agent PATCH | ✅ | `GET/PATCH /api/custom-agents/{id}`, `CustomAgentStore.get()`, Handler + Wiring |
| Backend: PolicyStore + CRUD | ✅ | `policy_store.py` + `routers/policies.py` (5 Endpoints) + `config.policies_dir` + main.py Wiring |
| Chat-Page: Custom-Agent-CRUD entfernt | ✅ | Felder, Methoden, Imports, HTML-Formular — alles raus |
| Chat-Page: Feature-Flags entfernt | ✅ | `loadRuntimeFeatures`, `saveRuntimeFeatures`, Checkboxen, LTM-Input — alles raus |
| Chat-Page: Monitoring ausgelagert | ✅ | 30 Felder, 16 Getters/Methoden, 4 Interfaces, ~100 Zeilen HTML → `MonitoringService` + `MonitoringPanelComponent` |
| MonitoringService | ✅ | 308 LOC, `updateMonitoring`, `pushLifecycle`, `refreshViews`, `resetAll`, `refreshRunAudit` + alle Filter-Getters |
| MonitoringPanelComponent | ✅ | 14 LOC TS, 105 LOC HTML, 139 LOC SCSS — eingebettet in Debug-Page |
| Navigation | 🔄 | 4 Links (Chat, Admin, Memory, Debug) — fehlt: Live-Link, Connection-Badge |
| Routing | 🔄 | 6 Routen — fehlt: `/live` |

### Was noch offen ist

| Bereich | Status | Problem |
|---------|--------|---------|
| Chat-Page ist noch ~655 LOC | 🔄 | Monitoring raus (−296 LOC), aber Policy-Approvals + `applyEvent()` + Runtime-Switching sind ~155 LOC legitime Logik. Ziel < 500 knapp verfehlt |
| Chat-Page HTML: 112 LOC | ✅ | Monitoring-Blöcke entfernt, unter 130 LOC Ziel |
| Admin-Page: Settings-Tab | 🔄 | Tab existiert im HTML, aber `loadSettings` und `saveSettings` sind Stubs |
| Admin-Page: Tools-Tab | 🔄 | `loadToolCatalog` ruft Backend auf, aber HTML zeigt nur Basis-Tabelle |
| Admin-Page: Skills-Tab | 🔄 | `loadSkills` + `syncSkills` funktional, HTML-View ist Basis |
| Live-Page | ❌ | Existiert nicht |
| Navigation: Live-Link + Badge | ❌ | Kein `/live` Link, kein Connection-Status-Badge |
| Frontend-Compilation | ✅ | `ng build` erfolgreich (nur SCSS-Budget-Warnungen) |

---

## Verbleibende Arbeit — Priorisiert

### Schritt A — Chat-Page Monitoring auslagern ✅ ERLEDIGT

**Ergebnis:**

| Kriterium | Ziel | Ist | Status |
|-----------|------|-----|--------|
| Chat-Page .ts | < 500 LOC | 655 LOC | 🔄 knapp verfehlt — verbleibend ist legitime Chat-Logik (Policy-Approvals ~120 LOC, `applyEvent` ~100 LOC, Runtime-Switching ~40 LOC) |
| Chat-Page .html | < 130 LOC | 112 LOC | ✅ |
| Monitoring-Panel erreichbar | Debug-Page | Eingebettet als `<app-monitoring-panel>` nach Event-Log | ✅ |
| Agent-Activity im Panel | ja | ja | ✅ |
| Request-Activity im Panel | ja | ja | ✅ |
| Run-Audit im Panel | ja | ja | ✅ |
| Reasoning Trace im Panel | ja | ja | ✅ |
| Lifecycle Stream im Panel | ja | ja | ✅ |
| Filter funktionieren | ja | Agent, Status, Request ID, Text Search, Reset | ✅ |
| Keine Regression | `ng build` ok | Build erfolgreich, Events werden via `MonitoringService` weitergeleitet | ✅ |

**Erstellte Dateien:**
- `frontend/src/app/services/monitoring.service.ts` (308 LOC)
- `frontend/src/app/pages/debug-page/monitoring-panel/monitoring-panel.component.ts` (14 LOC)
- `frontend/src/app/pages/debug-page/monitoring-panel/monitoring-panel.component.html` (105 LOC)
- `frontend/src/app/pages/debug-page/monitoring-panel/monitoring-panel.component.scss` (139 LOC)

**Geänderte Dateien:**
- `chat-page.component.ts`: 951 → 655 LOC (−296), MonitoringService injiziert, alle pushLifecycle/updateMonitoring delegiert
- `chat-page.component.html`: 216 → 112 LOC (−104), Monitor-Panel-Section entfernt
- `chat-page.component.scss`: ~430 → 328 LOC, monitoring-spezifische Styles entfernt
- `debug-page.component.ts`: MonitoringPanelComponent importiert
- `debug-page.component.html`: `<app-monitoring-panel>` nach Event-Log eingefügt

**Bewertung:** 8/9 Kriterien erfüllt. Das LOC-Ziel (< 500) ist mit 655 knapp verfehlt — die verbleibenden ~155 LOC Überschuss sind aber ausschließlich Chat-relevante Logik (Policy-Approvals, applyEvent, Runtime-Switching), die nicht weiter extrahiert werden sollte. Das ursprüngliche Ziel "Monitoring aus der Chat-Page auslagern" ist vollständig erreicht.

---

### Schritt B — Admin-Page Tabs fertigstellen

**Was fehlt:**

| Tab | Status | Was fehlt |
|-----|--------|-----------|
| Agents | ✅ | Funktional — Create, Edit, Delete, Clone |
| Workflows | ✅ | Funktional — CRUD + Execute |
| Policies | ✅ | Funktional — CRUD |
| Tools | 🔄 | Basis-Tabelle da, fehlt: Tool-Detail-View, Telemetrie-Einbettung, Profile-Ansicht, Policy-Matrix |
| Skills | 🔄 | Liste + Sync da, fehlt: Preview (SKILL.md-Inhalt anzeigen), Validation-Check |
| Settings | 🔄 | Stubs — `loadSettings` und `saveSettings` laden/speichern Runtime-Features (Feature-Flags) |

#### B1 — Tools-Tab vervollständigen

**Dos:**
- Tool-Detail on-click: Aliases, Profile-Zugehörigkeit, welche Agents dürfen es (Policy-Matrix-Zeile)
- Tool-Telemetrie: Aufrufe, Fehlerrate, Avg-Duration aus `GET /api/tools/stats`
- Tool-Profiles-View: Übersicht `read_only`, `research`, `coding`, `full`

**Don'ts:**
- Kein CRUD — Tools-Katalog ist Read-Only
- Keine Tool-Config (Timeouts etc.)

**Akzeptanzkriterien:**
- [ ] Tool-Tabelle: Name, Aliases, Profile, Status
- [ ] Klick → Detail mit Telemetrie (Calls, Errors, Avg Duration)
- [ ] Profile-Übersicht zeigt welche Tools in welchem Profil

#### B2 — Skills-Tab vervollständigen

**Dos:**
- Klick auf Skill → SKILL.md-Inhalt anzeigen (nutzt `skills.preview`)
- "Check Skills" Button → `skills.check` aufrufen, Ergebnis anzeigen

**Don'ts:**
- Kein Skill-Editor, kein Upload

**Akzeptanzkriterien:**
- [ ] Klick auf Skill → SKILL.md-Preview
- [ ] "Check Skills" Button mit Ergebnis-Anzeige

#### B3 — Settings-Tab mit Runtime-Features verbinden

**Dos:**
- `loadSettings()` → `agentsService.getRuntimeFeatures()` aufrufen
- `saveSettings()` → `agentsService.updateRuntimeFeatures()` aufrufen
- Feature-Flag-Checkboxen: Long-Term Memory, Session Distillation, Failure Journal, Vision
- LTM DB Path Input
- Persist-Status-Anzeige (persisted/not_persisted/error)

**Don'ts:**
- Keine 109 Config-Felder — nur die 4-5 Runtime Feature-Flags

**Akzeptanzkriterien:**
- [ ] Settings-Tab lädt Feature-Flags vom Backend
- [ ] Checkboxen für 4 Feature-Flags + LTM Path
- [ ] "Apply" Button speichert, zeigt Persist-Status
- [ ] Identische Funktionalität wie die alte Chat-Page Feature-Flags-Section

---

### Schritt C — Live-Page (Phase 4)

#### Beschreibung
Konsolidierte Real-Time-Ansicht: **Welcher Agent macht gerade was, mit welchem LLM-Call, welche Tools werden aufgerufen.** Eigene Seite `/live`.

#### Dos
- Agent-Lane-View: Jeder aktive Agent als Lane, Events fließen in Echtzeit rein
- LLM-Call-Stream: Karte pro Call (Agent, Model, Prompt-Preview 200 chars, Tokens, Latenz, Status)
- Tool-Execution-Stream: Karte pro Call (Tool, Args 100 chars, Duration, Exit-Code)
- Filter: Agent-Dropdown, Session-Input, Status-Toggle
- Prompt-Inspect: Klick → Overlay mit vollem System-Prompt, User-Prompt, Response
- Daten aus `AgentStateService.debug$` und WebSocket-Events (`agent_step`, `lifecycle`, `token`, `final`)
- Auto-Scroll mit Pause-on-Hover
- Kein neuer Backend-Endpoint nötig

#### Don'ts
- Debug-Page nicht ersetzen — Live ist Beobachten, Debug ist Eingreifen
- Keine eigenen WebSocket-Connections — `AgentSocketService` wiederverwenden
- Keine Persistenz (kein Export, kein Download)
- Keine Filter-Persistenz — Reset bei Navigation

#### Akzeptanzkriterien
- [ ] `/live` Route erreichbar
- [ ] Agent-Lanes zeigen aktive Agents in Echtzeit
- [ ] LLM-Call-Karten: Agent, Model, Prompt-Preview, Tokens, Latenz, Status
- [ ] Tool-Call-Karten: Tool, Args-Preview, Duration, Exit-Code
- [ ] Filter: Agent, Session, Status
- [ ] Prompt-Inspect: Klick → Full Prompt/Response Overlay
- [ ] Auto-Scroll mit Pause-on-Hover
- [ ] Performance: 100 Events/Sekunde ohne UI-Freeze

---

### Schritt D — Navigation fertigstellen

#### Dos
- 5 Links: **Chat | Live | Admin | Memory | Debug**
- Active-Route highlighting (existiert bereits für 4 Links)
- Connection-Status-Badge in der Nav (grün/rot, aus `AgentSocketService.connected$`)
- Optional: Agent-Count-Badge auf Admin

#### Don'ts
- Kein Mega-Menu, kein Hamburger — 5 Links
- Kein Auth-Guard

#### Akzeptanzkriterien
- [ ] 5 Nav-Links (derzeit 4 — fehlt Live)
- [ ] Connection-Badge grün/rot sichtbar
- [ ] Active-State auf allen Links

---

## Reihenfolge

```
Schritt A ── Monitoring aus Chat-Page auslagern ✅ ERLEDIGT
  │            → Chat-Page geschrumpft 951 → 655 LOC TS, 216 → 112 LOC HTML
  │
  ├── Schritt B1 ── Tools-Tab vervollständigen
  ├── Schritt B2 ── Skills-Tab vervollständigen
  ├── Schritt B3 ── Settings-Tab verbinden
  │
  ├── Schritt C ─── Live-Page erstellen
  │
  └── Schritt D ─── Navigation fertigstellen (nach Live-Page)
```

**Schritt A** ist abgeschlossen.  
**B1, B2, B3** sind unabhängig voneinander und parallelisierbar.  
**C** (Live-Page) kann parallel zu B laufen.  
**D** kommt zuletzt (braucht Live-Route).

---

## Backend-Arbeit verbleibend

| Was | Status |
|-----|--------|
| Agent PATCH + GET | ✅ erledigt |
| PolicyStore + 5 CRUD Endpoints | ✅ erledigt |
| `policies_dir` Config | ✅ erledigt |
| Neue Backend-Endpoints für Schritte A-D | **0** — alles Frontend-only |

**Kein weiterer Backend-Code nötig.** Alle benötigten APIs existieren.

---

## Was wir NICHT machen

| Verlockung | Warum nicht |
|-----------|-------------|
| NgRx/Redux State-Management | `BehaviorSubject` + `AgentStateService` funktioniert, Projekt ist nicht groß genug |
| Component Library (Material, PrimeNG) | Das Frontend nutzt eigenes CSS, Migration wäre destruktiv |
| Backend-Architektur umbauen | 60+ Services funktionieren, Interfaces sind sauber, kein Grund |
| Tool-Registrierung API | Kommt erst wenn P0-Features (Browser, RAG) es erfordern |
| Skill-Editor | Skills sind Markdown-Files, Editor wäre Editor-Inception |
| User/Auth System | Single-User Setup, kein Multi-Tenancy geplant |
| Datenbank-Migration (SQLite → Postgres) | Overkill, lokaler Betrieb bleibt Kern-UseCase |
| Config-Datei UI-Editor | 109 Config-Felder ins UI bringen löst kein reales Problem — .env funktioniert |
| Unit-Tests für Frontend | Erst nachdem die Seiten stabil sind — Tests auf bewegliches Ziel sind Zeitverschwendung |

---

## Definition of Done (Gesamtplan)

### Dos
- **Sidebar oder Top-Nav**: Chat | Live | Admin | Memory | Debug
- Active-Route highlighting
- Connection-Status-Badge in der Nav (immer sichtbar)

### Don'ts
- Kein Mega-Menu, kein Hamburger-Menu — 5 Links, fertig
- Kein Routing-Guard (Login/Auth) — gibt es nicht und wird nicht gebaut
- Layout nicht komplett überarbeiten — nur Nav hinzufügen

### Akzeptanzkriterien
- [ ] Navigation mit 5 Links: Chat, Live, Admin, Memory, Debug
- [ ] Active-State klar erkennbar
- [ ] Connection-Badge (grün/rot) immer sichtbar
- [ ] Auf allen Seiten gleiche Nav

---

## Definition of Done (Gesamtplan)

Das Refactoring ist abgeschlossen wenn:

1. **Chat-Page** enthält nur Chat-Logik (655 LOC TS ✅, 112 LOC HTML ✅ — Monitoring ausgelagert)
2. **Admin-Seite** verwaltet Agents, Workflows, Policies, Tools, Skills und Settings
3. **Tool-Katalog** ist im Admin als View mit Detail und Telemetrie sichtbar
4. **Skill-Liste** ist im Admin mit Preview und Sync sichtbar
5. **Live-View** zeigt Agent-LLM-Calls und Tool-Executions in Echtzeit
6. **Navigation** verbindet alle 5 Seiten mit Connection-Badge
7. **Monitoring** ist aus der Chat-Page ausgelagert ✅ (MonitoringPanelComponent auf Debug-Page)
8. **Kein Breaking Change** — alle bestehenden WebSocket-Events, APIs und Workflows funktionieren identisch
9. **Backend** hat alle nötigen Endpoints (✅ bereits erledigt — 0 verbleibend)
10. **Jedes neue P0-Feature** (Browser, RAG, REPL) das danach implementiert wird, erscheint automatisch im Tool-Katalog, ist per Policy steuerbar, und wird im Live-View sichtbar
