# Refactoring-Plan — Frontend-First Management Layer

> Ziel: Alles über das Frontend steuerbar — Agents, Workflows, Skills, Tools, Policies, Live-View.  
> Grundsatz: Kein neues P0-Feature bevor die Steuerbarkeit steht.  
> Stand: 8. März 2026

---

## Ist-Zustand (Fakten)

### Frontend
| Seite | Zustand | Problem |
|-------|---------|---------|
| Chat Page | ~800 Zeilen Logik | **Monolith** — Agent-CRUD, Policy-Approvals, Feature-Flags, Monitoring, Subrun-Spawning, Runtime-Switch alles in einer Komponente |
| Memory Page | Funktional | Read-Only, kein Editieren/Löschen |
| Debug Page | Exzellent | Pipeline-Breakpoints, LLM-Call-Records, Tool-Execution, Event-Log — aber isoliert vom Rest |
| Admin/Settings | **Existiert nicht** | Keine dedizierte Verwaltungsseite |

- **8 Komponenten**, 5 Services, 4 Routen
- Kein Workflow-Builder, kein Policy-Editor, kein Skill-Manager, kein Tool-Manager

### Backend
| Bereich | API-Status | Lücke |
|---------|-----------|-------|
| Custom Agents | Create + Delete + List | Kein Read-Single, kein Update/Patch |
| Workflows | **Vollständiges CRUD** | Frontend nutzt es nicht |
| Tool-Katalog | Read-Only (Catalog, Profile, Matrix) | Hardcoded 20 Tools, kein dynamisches Registrieren |
| Tool-Policies | Nur Preview | **Kein CRUD** — Policies existieren nur per-Request oder in Custom-Agent-JSON |
| Skills | Discover + Preview + Sync | Kein Create/Edit/Delete |
| Config | Feature-Flags runtime-togglebar | 109+ Felder nur per .env, kein Admin-API |
| Policy-Approvals | Vollständig (Pending, Allow, Decide) | Funktioniert, Frontend nutzt es |

- **50+ Endpoints**, 11 Router-Dateien, 158 Python-Dateien, 60+ Services
- Workflow-CRUD existiert seit langem — hat aber kein Frontend

### Was bereits funktioniert und nicht angefasst werden darf
- WebSocket-basiertes Streaming-Protokoll (18+ Event-Typen)
- Pipeline-Runner State Machine (INIT → SELECT → EXECUTE → SUCCESS/FAILURE → FINALIZE)
- Debug-Pipeline mit Breakpoints und Phase-Stepping
- Policy-Approval-Flow (Human-in-the-Loop)
- Custom-Agent Adapter-Pattern (Base-Agent + Workflow-Steps)
- Session-Lane-Management mit TTL-Eviction
- StateStore/MemoryStore Persistenz-Schicht
- Agent-Routing mit Capability-Matching

---

## Phase 1 — Chat-Page Entkernen

### Beschreibung
Die Chat-Page ist ein Monolith. Agent-Erstellung, Policy-Approvals, Feature-Flags, Monitoring-Tabellen — alles inline. Zuerst muss die Chat-Page reduziert werden auf: **Chat + Agent-Auswahl + Policy-Approvals**. Alles andere wandert in dedizierte Seiten.

### Dos
- Chat-Page behält: Message-Input, Agent-Dropdown, Preset-Dropdown, Inline-Policy-Approvals, Connection-Status
- Agent-Erstellung/Löschung → neue Admin-Seite
- Feature-Flags → neue Admin-Seite
- Monitoring-Tabellen (Agent Activity, Request Activity) → Debug-Page integrieren oder eigene Monitoring-Seite
- Runtime-Switching (Local/API) → Admin-Seite oder Header-Bar
- Tool-Policy CSV-Inputs → bleiben im Chat (per-Request Override), aber Default-Policy kommt aus Admin
- Shared State via `AgentStateService` beibehalten — keine State-Duplikate

### Don'ts
- Keine Funktionalität entfernen — nur verschieben
- Keinen neuen State-Management-Layer einführen (kein NgRx/Redux) — `AgentStateService` + `BehaviorSubject` reicht
- Chat-Page nicht in Sub-Komponenten zerlegen, die trotzdem alle am selben Ort rendern — echte Seiten-Trennung
- Kein eigenes Design-System bauen — bestehende CSS-Klassen und HTML-Struktur beibehalten

### Akzeptanzkriterien
- [ ] Chat-Page enthält nur noch: Message-Thread, Input-Bar, Agent/Preset-Dropdown, Inline-Approvals
- [ ] Monitoring ist auf Debug-Page oder eigenem Tab erreichbar
- [ ] Feature-Flags sind auf Admin-Seite konfigurierbar
- [ ] Custom-Agent Create/Delete ist auf Admin-Seite
- [ ] Keine Regression: Alle bestehende Chat-Funktionalität arbeitet identisch
- [ ] Chat-Page .ts Datei < 400 Zeilen (aktuell ~800)

---

## Phase 2 — Admin-Seite (Agents + Workflows + Policies)

### Beschreibung
Neue Frontend-Seite `/admin` als zentrale Verwaltung. Drei Tabs: **Agents**, **Workflows**, **Policies**. Nutzt existierende Backend-Endpoints wo möglich, erweitert Backend wo nötig.

### 2a — Agent-Management Tab

#### Dos
- System-Agents (15 Built-in) als Read-Only-Karten anzeigen (Name, Rolle, Status)
- Custom-Agents als editierbare Karten: Name, Description, Base-Agent, Workflow-Steps, Tool-Policy, Capabilities
- Inline-Editing für Custom-Agents (kein Modal-Dialog — direkt in der Karte)
- "Clone Agent" Button → erstellt Kopie mit neuem ID
- Agent-Detail-View: Zeige zugewiesene Tool-Policy, aktive Skills, letzte Runs

#### Backend-Änderungen nötig
- `GET /api/custom-agents/{agent_id}` — Read-Single (fehlt)
- `PATCH /api/custom-agents/{agent_id}` — In-Place Update (fehlt, aktuell nur Delete+Recreate)

#### Don'ts
- System-Agents nicht editierbar machen — die kommen aus Code/Config
- Kein Agent-Template-System — Custom-Agents mit Base-Agent + Steps reichen
- Keinen Agent-Status-Lifecycle bauen (draft/active/archived) — oversized für jetzt

#### Akzeptanzkriterien
- [ ] System-Agents: 15 Karten, Read-Only, mit Name/Rolle/Default-Model
- [ ] Custom-Agents: CRUD vollständig (Create, Read, Update, Delete)
- [ ] Edit-Mode: Name, Description, Base-Agent (Dropdown), Workflow-Steps (Textarea), Tool-Policy (Allow/Deny)
- [ ] Clone: Button auf jeder Custom-Agent-Karte
- [ ] Backend: `GET /api/custom-agents/{id}` und `PATCH /api/custom-agents/{id}` implementiert
- [ ] Validierung: Agent-ID unique, Name nicht leer, Base-Agent existiert

### 2b — Workflow-Management Tab

#### Dos
- **Backend-Endpoints existieren bereits** — nur Frontend bauen:
  - `workflows.list` → Tabelle aller Workflows
  - `workflows.get` → Detail-View
  - `workflows.create` → Formular
  - `workflows.update` → Inline-Edit
  - `workflows.delete` → Button mit Confirm
  - `workflows.execute` → "Run" Button
- Workflow-Steps als editierbare Liste (Add/Remove/Reorder)
- Step-Vorschau: Zeige was jeder Step als Prompt macht
- Execution-History: Letzte 10 Runs pro Workflow (via `runs.audit`)

#### Don'ts
- Keinen visuellen Drag-and-Drop Workflow-Builder — Text-basierte Step-Liste reicht für Phase 2
- Kein Condition-Branching (If/Else Steps) — lineare Steps wie bisher
- Keine Workflow-Versioning — save-in-place genügt

#### Akzeptanzkriterien
- [ ] Workflow-Liste: Tabelle mit ID, Name, Steps-Count, Base-Agent, letzte Ausführung
- [ ] Workflow-Create: Formular (Name, Description, Base-Agent Dropdown, Steps-Textarea, Tool-Policy)
- [ ] Workflow-Edit: Inline-Edit aller Felder
- [ ] Workflow-Delete: Button mit Bestätigungs-Dialog
- [ ] Workflow-Execute: "Run" Button → startet Workflow, zeigt Run-ID
- [ ] Service: Neuer `WorkflowService` im Frontend der alle 6 Endpoints aufruft

### 2c — Policy-Management Tab

#### Dos
- Named Policies erstellen/editieren/löschen (z.B. "read-only", "full-access", "code-review")
- Policy besteht aus: Name, Allow-Liste, Deny-Liste, Also-Allow, Agent-Overrides
- Policy-Preview: "Was passiert wenn ich diese Policy auf Agent X anwende?" (nutzt existierenden `tools.policy.preview`)
- Policy-Zuweisung: Dropdown pro Custom-Agent um Default-Policy auszuwählen
- Preset-Integration: Policies werden als Presets im Chat-Dropdown sichtbar

#### Backend-Änderungen nötig
- Neuer `PolicyStore` — JSON-Dateibasiert (analog zu `CustomAgentStore`)
- `POST /api/policies` — Neue Policy anlegen
- `GET /api/policies` — Alle Policies listen
- `GET /api/policies/{policy_id}` — Einzelne Policy lesen
- `PATCH /api/policies/{policy_id}` — Policy aktualisieren
- `DELETE /api/policies/{policy_id}` — Policy löschen

#### Don'ts
- Nicht die bestehende `ToolPolicyPayload`-Struktur ändern — der neue Store speichert benannte Instanzen davon
- Keine Policy-Versioning in Phase 2
- Keine komplexen Rollen/Permissions — eine Policy ist eine Allow/Deny-Liste, fertig
- Policy-Approval-Flow (Human-in-the-Loop) nicht anfassen — der funktioniert

#### Akzeptanzkriterien
- [ ] Policy-Liste: Tabelle mit Name, Allow-Count, Deny-Count, zugewiesene Agents
- [ ] Policy-Create: Formular (Name, Allow Multiselect aus Tool-Katalog, Deny Multiselect, Agent-Overrides)
- [ ] Policy-Edit: Inline
- [ ] Policy-Delete: Mit Warnung falls an Agents zugewiesen
- [ ] Policy-Preview: Zeigt effektive Tool-Liste pro Agent (nutzt `tools.policy.preview`)
- [ ] Backend: `PolicyStore` + 5 neue CRUD-Endpoints
- [ ] Policy im Chat-Dropdown als Preset auswählbar

---

## Phase 3 — Tool & Skill Management (Admin-Seite erweitern)

### 3a — Tool-Katalog View

#### Dos
- Tool-Katalog als Tabelle: Name, Aliases, Profile-Zugehörigkeit (read_only/research/coding/full), aktuelle Policy-Lage
- Tool-Detail: Klick auf Tool → zeige Aliases, in welchen Profilen enthalten, welche Agents dürfen es nutzen
- Tool-Telemetrie einbetten: Aufrufe, Fehlerrate, Durchschnitts-Dauer (existierender `GET /api/tools/stats`)
- Tool-Profiles anzeigen: Welche Profile existieren, welche Tools enthalten sie

#### Backend-Änderungen nötig
- Keine für Read-Only — existierende Endpoints reichen:
  - `tools.catalog` → Katalog
  - `tools.profile` → Profile
  - `tools.policy.matrix` → Matrix
  - `GET /api/tools/stats` → Telemetrie

#### Don'ts
- Keine Tool-Registrierung in Phase 3 — das kommt mit P0-Features (Browser Control etc.)
- Tool-Katalog ist Read-Only (zeigt was da ist), nicht CRUD
- Keine Tool-Konfiguration (Timeouts, Limits) — das ist Backend-Config

#### Akzeptanzkriterien
- [ ] Tool-Tabelle: 20 Tools mit Name, Aliases, Profilen, Status
- [ ] Tool-Detail: Klick → Profile, Agents, Telemetrie (Calls, Errors, Avg Duration)
- [ ] Tool-Profile: Übersicht welche Profile existieren und was sie enthalten
- [ ] Policy-Matrix: Visual Grid Agent × Tool (erlaubt/verboten)

### 3b — Skill-Management Tab

#### Dos
- Skill-Liste: Alle entdeckten Skills mit Name, Pfad, Eligibility-Score, Status (active/inactive)
- Skill-Preview: Klick → zeigt SKILL.md Inhalt (nutzt `skills.preview`)
- Skill-Sync: "Sync Skills" Button (nutzt `skills.sync` mit `apply=true`)
- Skill-Check: Validierung ob Skills korrekt strukturiert sind (nutzt `skills.check`)

#### Backend-Änderungen nötig
- Keine für Phase 3 — existierende Endpoints reichen

#### Don'ts  
- Kein Skill-Editor (SKILL.md inline editieren) — das ist File-System Arbeit
- Kein Skill-Upload — Skills liegen im `skills/` Verzeichnis
- Keine Skill-zu-Agent Zuweisung über UI — läuft über Eligibility-Matching

#### Akzeptanzkriterien
- [ ] Skill-Liste: Tabelle aller entdeckten Skills mit Metadaten
- [ ] Skill-Preview: SKILL.md Inhalt anzeigen
- [ ] Skill-Sync: Button → synchronisiert Skills-Index
- [ ] Skill-Validation: Button → prüft Skill-Struktur

---

## Phase 4 — Live Agent-LLM View

### Beschreibung
Konsolidierte Real-Time-Ansicht die zeigt: **Welcher Agent macht gerade was, mit welchem LLM-Call, welche Tools werden aufgerufen**. Baut auf dem existierenden Debug-Dashboard auf, aber als eigene Seite mit Fokus auf Live-Beobachtung statt Debugging.

### Dos
- Neue Route `/live` — eigenständige Seite
- **Agent-Lane-View**: Jeder aktive Agent als Spalte/Lane, Events fließen in Echtzeit rein
- **LLM-Call-Stream**: Jeder LLM-Call als Karte: Agent, Model, Prompt-Preview (truncated), Tokens, Latenz, Status
- **Tool-Execution-Stream**: Jeder Tool-Call als Karte: Tool, Args-Preview, Duration, Exit-Code, Success/Fail
- **Filter**: Nach Agent, nach Session, nach Status (running/completed/failed)
- **Prompt-Inspect**: Klick auf LLM-Call → Popup mit vollem System-Prompt, User-Prompt, Response
- Daten kommen aus `AgentStateService.debug$` — kein neuer Backend-Endpoint nötig
- Bestehende WebSocket-Events nutzen: `agent_step`, `lifecycle`, `token`, `final`
- Auto-Scroll mit Pause-on-Hover

### Don'ts
- Debug-Page nicht ersetzen — Live-View ist komplementär (Live = Beobachten, Debug = Eingreifen)
- Keine eigenen WebSocket-Connections — `AgentSocketService` wiederverwenden
- Keine Persistenz der Live-View (kein Timeline-Export, kein Log-Download) — das ist Debug-Territory
- Keine Filter-Persistenz — Reset bei Navigation

### Akzeptanzkriterien
- [ ] `/live` Route erreichbar
- [ ] Agent-Lanes zeigen aktive Agents in Echtzeit
- [ ] LLM-Calls: Agent, Model, Prompt (first 200 chars), Tokens, Latenz, Status als Karte
- [ ] Tool-Calls: Tool, Args (first 100 chars), Duration, Exit-Code als Karte
- [ ] Filter: Agent-Dropdown, Session-Input, Status-Toggle
- [ ] Prompt-Inspect: Klick auf LLM-Call → Full Prompt/Response in Overlay
- [ ] Auto-Scroll mit Pause-on-Hover
- [ ] Performance: 100 Events/Sekunde ohne UI-Freeze (virtuelles Scrolling oder DOM-Recycling)

---

## Phase 5 — Navigation & Layout

### Beschreibung
Nachdem alle Seiten existieren, braucht das Frontend eine ordentliche Navigation statt einzelne Routen manuell einzutippen.

### Dos
- **Sidebar oder Top-Nav**: Chat | Live | Admin | Memory | Debug
- Active-Route highlighting
- Connection-Status-Badge in der Nav (immer sichtbar)
- Agent-Count-Badge auf Admin (Anzahl Custom-Agents)

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

## Reihenfolge und Abhängigkeiten

```
Phase 1 ─── Chat-Page Entkernen
  │          (Voraussetzung für alles)
  │
  ├── Phase 2a ─── Agent-Management Tab
  │     │          Backend: +2 Endpoints
  │     │
  │     ├── Phase 2b ─── Workflow-Management Tab
  │     │                 Backend: 0 Änderungen (Endpoints existieren)
  │     │
  │     └── Phase 2c ─── Policy-Management Tab
  │                       Backend: +1 Store, +5 Endpoints
  │
  ├── Phase 3a ─── Tool-Katalog View
  │                 Backend: 0 Änderungen
  │
  ├── Phase 3b ─── Skill-Management Tab
  │                 Backend: 0 Änderungen
  │
  ├── Phase 4 ──── Live Agent-LLM View
  │                 Backend: 0 Änderungen
  │
  └── Phase 5 ──── Navigation & Layout
                    Backend: 0 Änderungen
```

**Parallelisierbar**: Phase 2b, 3a, 3b können parallel zu 2c laufen.  
**Backend-Arbeit total**: 2 Endpoints (Agent Read/Patch) + 1 PolicyStore + 5 Policy-Endpoints = **8 Backend-Änderungen**.  
**Frontend-Arbeit total**: 1 neue Seite (Admin) + 1 neue Seite (Live) + 1 Navigation + Chat-Refactor = **4 größere Frontend-Tasks**.

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

Das Refactoring ist abgeschlossen wenn:

1. **Chat-Page** enthält nur Chat-Logik (< 400 LOC)
2. **Admin-Seite** verwaltet Agents, Workflows und Policies mit vollem CRUD
3. **Tool-Katalog** ist im Admin als Read-Only-View mit Telemetrie sichtbar
4. **Skill-Liste** ist im Admin mit Preview und Sync sichtbar
5. **Live-View** zeigt Agent-LLM-Calls und Tool-Executions in Echtzeit
6. **Navigation** verbindet alle 5 Seiten
7. **Kein Breaking Change** — alle bestehenden WebSocket-Events, APIs und Worflows funktionieren identisch
8. **Backend** hat 8 neue Endpoints (2 Agent, 5 Policy, 1 Policy-Store)
9. **Jedes neue P0-Feature** (Browser, RAG, REPL) das danach implementiert wird, erscheint automatisch im Tool-Katalog, ist per Policy steuerbar, und wird im Live-View sichtbar
