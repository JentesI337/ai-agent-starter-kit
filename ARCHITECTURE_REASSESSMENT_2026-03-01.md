# Architecture Reassessment (2026-03-01)

Scope: `backend/` + relevante Root-Artefakte

## 1) Design-Flaws (priorisiert)

1. **God file `main.py`** (hoch)  
   - Problem: Routing, Contracts, Policy-Resolver, Workflow-Ausführung, WS-Loop und Utilities in einer Datei.  
   - Impact: schwer wartbar, hohe Regression-Gefahr bei kleinen Änderungen.  
   - Maßnahme: modulare Router/Service-Aufteilung (`control_runs`, `control_sessions`, `control_workflows`, `ws_handler`, `policy_service`).

2. **Import-Time Side Effects** (hoch)  
   - Problem: globale Initialisierung + Startup-Cleanup beim Import.  
   - Impact: schwer testbar, versteckte Seiteneffekte.  
   - Maßnahme: Initialisierung in FastAPI-Lifespan verlagern.

3. **Idempotency-Registries als unbounded In-Memory Maps** (hoch)  
   - Problem: mehrere `dict`-Stores ohne TTL/Eviction/Persistenz.  
   - Impact: Speicherwachstum, inkonsistente Replays über Restarts hinweg.  
   - Maßnahme: zentrale Idempotency-Registry mit TTL + Max-Entries.

4. **Policy-Logik verteilt über Main/Agent/CustomAgent** (mittel-hoch)  
   - Problem: Merge-/Apply-Logik lebt an mehreren Stellen.  
   - Impact: divergierende Semantik.  
   - Maßnahme: ein zentraler Policy-Service als einzige Merge-Quelle.

5. **Event-Schema inkonsistent persistiert** (mittel)  
   - Problem: teils volle Lifecycle-Events, teils minimierte Event-Objekte.  
   - Impact: Audit/Telemetry-Auswertung kompliziert.  
   - Maßnahme: einheitliches Event-Envelope, Alt-Adapter in Audit.

6. **Session/Run-Abfragen per wiederholtem Vollscan** (mittel)  
   - Problem: häufig `list_runs(limit=2000)` mit Filtern in Python.  
   - Impact: skaliert schlecht bei steigenden Run-Zahlen.  
   - Maßnahme: Query-Helper + leichter Index/Cache.

7. **Reflection auf private Agent-Methoden** (mittel)  
   - Problem: `hasattr(..., "_build_read_only_policy")` auf private API.  
   - Impact: brittle coupling.  
   - Maßnahme: offizielles Contract-Hook-Interface.

8. **RuntimeManager trägt zu viele Verantwortungen** (mittel)  
   - Problem: Runtime-State + Prozesssteuerung + API-Model-Katalog in einer Klasse.  
   - Impact: hohe Kopplung, erschwerte Änderungen.  
   - Maßnahme: Aufspaltung in State/Process/Catalog Services.

## 2) Alte Artefakte / mögliche Cleanup-Kandidaten

1. `backend/index.html`  
2. `backend/styles.css`  
3. `backend/calculator.html`  
4. `runtime_state.json` (Root, wahrscheinlich redundant zu `backend/runtime_state.json`)  
5. `memory_store/` (Root, wahrscheinlich redundant zu `backend/memory_store/`)  
6. `backend/TEST_BASELINE.md` (inhaltlich wahrscheinlich veraltet)

Verifikation vor Löschung:
- repo-weite Referenzsuche,
- kurzer Laufzeittest (wird Datei tatsächlich gelesen/ausgeliefert?),
- bei Zustand-Dateien: Timestamp/Write-Path beim Runtime-Switch prüfen.

## 3) Duplikationen

1. Tool-Listen/Tool-Universum an mehreren Stellen (`main.py`, `agent.py`, `tool_selector_agent.py`, `tools.py`).
2. Policy-Merge-Logik (`main.py`, `custom_agents.py`).
3. Idempotency-Find/Register-Pattern in vielen Endpoints (run/session/workflow).
4. Session/Run-Scan-Pattern mehrfach in `main.py`.
5. Nahezu identische Request-Modelle (`RunStartRequest` vs `ControlRunStartRequest`).
6. LLM-HTTP-Pfade mit ähnlicher Request-/Retry-Struktur in `llm_client.py`.

## 4) Bad Code / Smells

- God file: `backend/app/main.py`
- God class: `backend/app/agent.py` (`HeadAgent`)
- Mutable Defaults in Pydantic-Requests (dict/list Defaults)
- Broad exception swallowing in einigen Safe-Helpern/Stores
- Reflection auf private Methoden
- Lange Dispatcher-/Branch-Blöcke (`_invoke_tool`, WS-Loop)
- In-Memory global state ohne Lebenszyklus-Policy
- Wiederholte Vollscans statt zentralem Query-Service

## 5) Quick Wins (1–2h)

1. Mutable Defaults auf `Field(default_factory=...)` umstellen.
2. Idempotency-Registry als Utility zentralisieren (pilot: `run.start` + `sessions.patch`).
3. Session/Run Query-Helper extrahieren und 2 Endpoints migrieren.
4. Private Policy-Hook in offizielles Contract-Hook überführen.
5. Tool-Katalog als zentrale Konstante auslagern.
6. Event-Append im WS-Pfad auf einheitliches Envelope bringen.
7. Root/Backend State-Pfade beim Startup explizit loggen.
8. Alte HTML/CSS-Dateien als deprecate markieren und nach Verifikation entfernen.
9. TEST_BASELINE aktualisieren/archivieren.
10. RuntimeManager Dead-Code prüfen und entfernen/integrationsklar machen.

## 6) Empfohlene nächste Refactor-Welle (ohne API-Break)

- **Woche 1:** Idempotency-Utility + Query-Service + mutable-default cleanup.
- **Woche 2:** `main.py` modularisieren + Policy-Service vollständige Entkopplung.

### Umsetzungsstand (2026-03-01, durchgeführt)

- **Woche 1 umgesetzt:**
   - Idempotency-Utility zentral als Service ausgelagert und in den Pilotpfaden verdrahtet.
   - Session/Run-Query als Service ausgelagert und in Resolve/Status/Patch/Reset angebunden.
   - Mutable-default cleanup im bisherigen Scope beibehalten (Pydantic-Request-Modelle ohne mutable Defaults).
- **Woche 2 umgesetzt (ohne API-Break):**
   - Policy-Service vollständig aus `main.py` extrahiert (Profiles/Presets/Provider/Model + Resolver + Explain).
   - `main.py` nutzt nur noch Service-Aufrufe für Policy- und Query-Logik.
   - Control-Endpoints in modulare Router aufgeteilt (`control_runs`, `control_sessions`, `control_workflows`, `control_tools`) und in `main.py` per `include_router(...)` eingebunden.
   - Endpunkt-Verträge und Routen unverändert gelassen.
- **Verifikation:**
   - `91 passed` für: `tests/test_control_plane_contracts.py`, `tests/test_backend_e2e.py`, `tests/test_subrun_lane.py`.

