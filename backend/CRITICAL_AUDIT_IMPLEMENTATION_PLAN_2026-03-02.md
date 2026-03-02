# Critical Audit – Übertrag in den Ist-Code & Umsetzungsplan

Datum: 2026-03-02  
Scope: `backend/app/**` (Audit-Transfer, `architecture.md` bewusst **nicht** verwendet)

## 1) Ziel dieses Dokuments

Dieses Dokument überträgt das externe Deep-Quality-Audit auf den **tatsächlichen** Codezustand im Backend und definiert einen priorisierten, umsetzbaren Maßnahmenplan.

- Fokus: HeadAgent, Sub-Agents, Tool-Chaining, Hardening, Resilience, Tests
- Ergebnis: verifizierte Findings + konkrete Arbeitspakete mit Abnahmekriterien

---

## 2) Audit-Transfer: Verifiziert vs. Teilweise vs. Nicht bestätigt

## 2.1 Verifiziert (hoch relevant)

1. **HeadAgent-Monolith / God-Class**  
   - Verifiziert: `app/agent.py` hat ~2519 Zeilen und bündelt Pipeline, Policies, Validation, Tool-Dispatch, Intent, Reply-Shaping.

2. **Prozedurale Tool-Argument-Validierung mit Dupplikation**  
   - Verifiziert: `_evaluate_action(...)` enthält umfangreiche if/elif-Validierung pro Tool.

3. **Doppelter Tool-Dispatch (Mismatch-Risiko)**  
   - Verifiziert: `_evaluate_action(...)` und `_invoke_tool(...)` führen getrennte, manuell synchronisierte Tool-Logik.

4. **Fragiles Reply-Shaping via String-Matching**  
   - Verifiziert: `_shape_final_response(...)` suppresses bei hart codierten Tokens (`done`, `completed`, `fertig`, ...).

5. **Regelbasierte Intent-Erkennung**  
   - Verifiziert: `_detect_intent_gate(...)` und `_looks_like_shell_command(...)` arbeiten keyword-/regex-basiert.

6. **`_is_file_creation_task` ist breit und triggeranfällig**  
   - Verifiziert: Marker wie `build`, `html`, `css`, `js` sind sehr allgemein.

7. **Tool-Timeout-Isolation unvollständig (`asyncio.to_thread`)**  
   - Verifiziert: `_run_tool_with_policy(...)` nutzt `wait_for(to_thread(...))`; Worker-Thread kann weiterlaufen.

8. **`web_fetch` ohne SSRF-Härtung**  
   - Verifiziert: `urlopen(...)` mit schema-check (`http/https`), aber ohne private-IP/DNS-Rebinding/Redirect-Limit-Guards.

9. **Command-Ausführung mit `shell=True` + Leader-Allowlist**  
   - Verifiziert: `run_command(...)`/`start_background_command(...)` nutzen `shell=True`; Allowlist prüft primär Leader-Token.

10. **Follow-up Tool Selection nutzt abweichende Prompt-Quelle**  
    - Verifiziert: `_augment_actions_if_needed(...)` verwendet `settings.agent_tool_selector_prompt` statt `self.prompt_profile.tool_selector_prompt`.

11. **PlannerAgent `run()` Interface inkonsistent**  
    - Verifiziert: `PlannerInput.model_validate_json(user_message)` erwartet JSON-String.

12. **ToolSelectorAgent ist Pass-through / Runtime-Config No-Op**  
    - Verifiziert: Delegation 1:1 an Callback; `configure_runtime(...)` ohne Wirkung.

13. **Synthesizer Streaming ohne expliziten Timeout-Guard**  
    - Verifiziert: Token-Loop ohne `wait_for`/Cancellation-Limit auf Agent-Ebene.

14. **Review-Evidence Regex kann false positives haben**  
    - Verifiziert: Hash-Pattern `\b[a-f0-9]{7,40}\b` ist breit.

15. **Adapter-Duplikation (Head/Coder nahezu identisch)**  
    - Verifiziert: `HeadAgentAdapter` und `CoderAgentAdapter` weitgehend copy/paste.

16. **PipelineRunner Recovery-Komplexität sehr hoch**  
    - Verifiziert: viele Recovery-Flags/Counter in `_run_with_fallback(...)`, hohe kognitive Last.

17. **SessionLaneManager Lock-Map ohne Eviction**  
    - Verifiziert: `_session_locks: defaultdict(asyncio.Lock)` wächst potenziell unbegrenzt.

18. **`on_released` kann Originalfehler überlagern**  
    - Verifiziert: `finally` ruft `on_released` ohne Schutz auf.

19. **LLM-Client kann leere Antwort durchreichen**  
    - Verifiziert: `complete_chat(...)` liefert `"".strip()` ohne harte Validierung.

20. **LLM-Tests fehlen als dedizierter Block**  
    - Verifiziert: keine `backend/tests/*llm*` Dateien vorhanden.

21. **Große God-Files zusätzlich zu `agent.py`**  
    - Verifiziert: `main.py` ~2911, `pipeline_runner.py` ~1228, `subrun_lane.py` ~854 Zeilen.

22. **Tool-Policy-Typen inkonsistent über Layer**  
    - Verifiziert: `dict[str, list[str]]` + `ToolPolicyPayload` + weitere raw dict Übergaben.

23. **`WsInboundMessage` als breites Sammelmodell**  
    - Verifiziert: viele optionale Felder in einem Modell, keine diskriminierte Union.

24. **Step-Executor Rückgaben als `str` trotz Output-Schemas**  
    - Verifiziert: `step_executors.py` definiert `Awaitable[str]`-Signaturen.

## 2.2 Teilweise verifiziert / korrigiert

1. **Subrun `_run_tasks` Memory-Leak (Audit-These)**  
   - Teilweise korrigiert: in `_run(...)` wird `self._run_tasks.pop(spec.run_id, None)` ausgeführt.  
   - Rest-Risiko bleibt: langfristiges Wachstum in `_run_status`/`_announce_status` ohne Retention-Policy.

2. **„Keine Deduplizierung bei Tool-Augmentation“**  
   - Teilweise korrigiert: am Ende von `_augment_actions_if_needed(...)` existiert JSON-basierte Deduplizierung.

3. **`_looks_like_shell_command` ohne `poetry`/`tox`/`nox`**  
   - Korrigiert bzgl. `poetry` (vorhanden), aber `tox`/`nox` fehlen weiterhin.

## 2.3 Nicht eindeutig im aktuellen Snapshot bestätigt

1. **`subprocess.run`-Timeout für alle Tools erforderlich**  
   - Für `run_command` vorhanden; für File-I/O nicht sinnvoll via `subprocess`, aber Guard/Size-Limits fehlen.

2. **Token-Vergleich ohne `hmac.compare_digest`**  
   - Direkter serverseitiger Token-Vergleich wurde im gescannten Pfad nicht gefunden; Risiko bleibt als Prüfpunkt offen.

---

## 3) Priorisierter Umsetzungsplan

## P0 (Sofort, Security + Stabilität)

### P0.1 SSRF-Härtung für `web_fetch`

**Ziel**: Kein Zugriff auf interne/private Ziele, kontrollierte Redirects, robust gegen DNS-Rebinding.

**Maßnahmen**
- Neue URL-Sicherheitsprüfung in `app/tools.py`:
  - Nur `http`/`https`
  - DNS-Resolve + Block privater/loopback/link-local/netzinterner Ranges (IPv4/IPv6)
  - Redirect-Limit (z. B. 3), jede Redirect-Location erneut validieren
  - Optional: Blockliste für Hostnames (`localhost`, metadata endpoints)
- `web_fetch(...)` auf sicheren Fetch-Pfad umstellen.

**Abnahme**
- Unit-Tests für erlaubte öffentliche URL + geblockte lokale/private Ziele + Redirect-Kette + DNS-Auflösung.

### P0.2 Command-Injection-Risiko reduzieren

**Ziel**: `run_command`/`start_background_command` nicht nur über Leader-Token absichern.

**Maßnahmen**
- `shell=True` schrittweise ersetzen durch args-basierte Ausführung (`shell=False`) wo möglich.
- Bis zur Migration: zusätzliche Pattern-Blockliste für gefährliche Konstrukte (`;`, `&&`, `| bash`, `powershell -enc`, `python -c` mit `os.system`, etc.).
- Allowlist auf Befehl + erlaubte Argumentmuster erweitern (policy-driven).

**Abnahme**
- Negative Tests für bekannte Bypass-Payloads.
- Positive Tests für legitime Kommandos in Windows/Linux-Szenarien.

### P0.3 Tool-Execution Timeout/Resource-Hardening

**Ziel**: Kein unkontrolliertes Hängen bei großen Dateioperationen / Blockaden.

**Maßnahmen**
- In `AgentTooling.read_file(...)` Dateigrößenlimit (z. B. 1–2 MB) und ggf. max-chars cap.
- In `grep_search(...)` harte Dateigrößen- und Ergebnisgrenzen plus early-abort.
- Optional: Executor mit dediziertem bounded ThreadPool für Tool-Aufrufe.

**Abnahme**
- Tests mit großen Dateien: deterministische, schnelle Fehler statt Hänger.

### P0.4 LLM-Client Test-Suite + leere Antwort behandeln

**Ziel**: zentrale LLM-Schicht verlässlich absichern.

**Maßnahmen**
- Neue Tests `backend/tests/test_llm_client.py`:
  - Retry auf 429/5xx
  - Timeout-Mapping
  - Stream-Parsing
  - Native-Ollama + OpenAI-kompatibel
- `complete_chat(...)`/`_complete_chat_ollama(...)`: leere Inhalte als `LlmClientError` oder klarer Fallback-Status.

**Abnahme**
- >90% Branch-Abdeckung in `llm_client.py`.

---

## P1 (Kurzfristig, Entflechtung & Wartbarkeit)

### P1.1 HeadAgent modularisieren

**Ziel**: Verantwortungen trennen, Testbarkeit erhöhen.

**Target-Extraktionen**
- `tool_argument_validator.py`
- `tool_dispatcher.py` (Single Source of Truth Registry -> Validation + Invoke)
- `intent_detector.py`
- `reply_shaper.py`
- `action_augmentation.py`

**Abnahme**
- `agent.py` reduziert auf Orchestrierung + Komposition.
- Neue Unit-Tests pro extrahierter Komponente.

### P1.2 Tool Registry als einzige Wahrheit

**Ziel**: kein Drift zwischen `_evaluate_action` und `_invoke_tool`.

**Maßnahmen**
- Tool-Metadaten + Arg-Schema + Executor-Callable in gemeinsamer Registry.
- Validierung generisch (typed validator helpers), kein if/elif-Wald.

**Abnahme**
- Neues Tool benötigt nur Registry-Eintrag + Tooling-Methode + Tests.

### P1.3 SessionLaneManager & Subrun-Lebenszyklus härten

**Ziel**: kontrolliertes Memory-Verhalten und sichere Callback-Fehlerpfade.

**Maßnahmen**
- Eviction für `_session_locks` (LRU/TTL) nach Inaktivität.
- `on_released` in eigenen try/except, Originalfehler priorisieren.
- Retention/GC für `_run_status` und `_announce_status` einführen.

**Abnahme**
- Lasttest zeigt stabiles Speicherprofil über lange Laufzeit.

### P1.4 Prompt-Quellen konsolidieren

**Ziel**: einheitliche Prompt-Nutzung.

**Maßnahmen**
- `_augment_actions_if_needed(...)` auf `self.prompt_profile.tool_selector_prompt` umstellen.

**Abnahme**
- Regression-Tests für Tool-Selection bleiben grün.

### P1.5 `main.py` aufteilen

**Ziel**: kleinere, klar getrennte Module.

**Maßnahmen**
- Trennung in: App-Factory/DI, Lifespan, WS-Endpoints, Runtime-Endpoints, Middleware/CORS.

**Abnahme**
- Keine funktionalen Regressionen im WS- und Runtime-Pfad.

---

## P2 (Mittelfristig, Typsicherheit & Architekturkonsistenz)

### P2.1 Einheitlicher Tool-Policy-Typ

**Ziel**: keine 3 Repräsentationen desselben Konzepts.

**Maßnahmen**
- Zentrales Pydantic-Modell (z. B. `ToolPolicy`) als einzige Transport-/Domain-Repräsentation.
- Adapter nur an Grenzen (WS/API), intern strikt typisiert.

### P2.2 WS-Inbound als discriminated union

**Ziel**: typsichere Nachrichtentypen statt God-Model.

**Maßnahmen**
- `WsInboundMessage` in unions aufspalten (`type` als Discriminator).

### P2.3 PipelineRunner Recovery vereinfachen

**Ziel**: weniger Komplexität, mehr Vorhersagbarkeit.

**Maßnahmen**
- Recovery-Flags in eigenes Config-Objekt/Strategy-Objekt auslagern.
- Branches modularisieren, einzelne Recovery-Strategien testbar machen.

### P2.4 AgentConstraints entweder nutzen oder entfernen

**Ziel**: keine toten Abstraktionen.

**Maßnahmen**
- Constraints in LLM-Aufrufe einspeisen (z. B. temperature) oder Felder reduzieren.

### P2.5 Synthesizer Streaming Timeout/Cancellation

**Ziel**: keine unbegrenzten Stream-Hänger.

**Maßnahmen**
- `asyncio.wait_for`/deadline um Token-Loop, kontrollierte Fehleremission.

---

## 4) Test-Strategie (verpflichtend pro Phase)

## Phase P0 Tests
- `test_llm_client.py` neu
- `test_tools_web_fetch_security.py` neu
- `test_tools_run_command_policy.py` neu
- Große-Datei-Tests für `read_file`/`grep_search`

## Phase P1 Tests
- Unit-Tests für `intent_detector`, `reply_shaper`, `tool_argument_validator`, `tool_dispatcher`
- Tests für Session-Lock-Eviction und Callback-Fehlerpriorisierung

## Phase P2 Tests
- Typ-/Schema-Tests für WS-Union + Tool-Policy-Modell
- PipelineRunner-Recovery-Strategie tests (isolierte Strategien statt monolithische Szenarien)

## Coverage-Gate
- `pytest-cov` integrieren
- Startwert: 70% global + Mindest-Coverage auf kritischen Modulen (`llm_client.py`, Tooling, Runner)
- Danach schrittweise anheben

---

## 5) Empfohlene Reihenfolge (4 Arbeitsblöcke)

1. **Block A (P0.1 + P0.2):** Security-Härtung (`web_fetch`, `run_command`)  
2. **Block B (P0.3 + P0.4):** Stabilität + LLM-Tests  
3. **Block C (P1.1 + P1.2 + P1.4):** HeadAgent entflechten + Registry vereinheitlichen  
4. **Block D (P1.3 + P1.5 + P2):** Lane/Main/Typing-Rework

---

## 6) Kurz-Risikoanalyse bei Nicht-Umsetzung

- **Hoch:** SSRF-/Command-Bypass-Risiko bleibt bestehen
- **Hoch:** Tool-Dispatch-Drift führt zu Produktionsfehlern bei neuen Tools
- **Mittel-Hoch:** schwer debuggbarer Betrieb durch monolithische Kernklassen
- **Mittel:** unklare Fehlerbilder bei leeren LLM-Antworten und langen Streams

---

## 7) Definition of Done (gesamt)

- Kritische Security-Lücken (SSRF, Command-Bypass) geschlossen und getestet
- `llm_client.py` hat dedizierte Testabdeckung
- HeadAgent-Tool-Validation/Dispatch ist registry-basiert (Single Source of Truth)
- Session-/Subrun-Lifecycle besitzt Retention/Eviction
- WS-Message-Handling und Tool-Policy intern typsicher vereinheitlicht
- CI hat Coverage-Messung + Mindestschwellen

---

## 8) Umsetzungsstatus (laufend)

Stand: 2026-03-02

### 8.1 Erledigt

- **P0.1** SSRF-Härtung in `web_fetch` (Private-IP/DNS-Block, Redirect-Limit, sichere Redirect-Validierung)
- **P0.2** Command-Härtung (zusätzliche Bypass-Blockregeln, inkl. `python -c`/`powershell -enc`/pipe-to-shell)
- **P0.3** I/O-Härtung (`read_file`-Dateigrößenlimit, `grep_search` Datei- und Gesamt-Scan-Budget)
- **P0.4** `llm_client`-Härtung + dedizierte Tests (`LlmClientError` bei leerer Completion)
- **P1.2** Registry-Refactor in 3 Schritten abgeschlossen:
    - `_invoke_tool` registry-basiert
    - wiederverwendbare Validator-Helper
    - tool-spezifische `validator_registry` statt langer if-Kette
- **P1.4** Prompt-Quelle konsolidiert (`self.prompt_profile.tool_selector_prompt`)
- **P1.3** SessionLaneManager + SubrunLane gehärtet abgeschlossen:
    - Lock-Eviction + Fehlerpriorisierung im SessionLaneManager
    - Retention/GC für `_run_status` / `_announce_status` im `SubrunLane`
- **P2.1** Einheitlicher Tool-Policy-Typ über alle Schichten abgeschlossen:
    - zentrales Tool-Policy-Modul (`tool_policy.py`) als Single Source
    - Boundary-Payload (`ToolPolicyPayload`) + zentrale Normalisierung an API/WS-Eingängen
    - konsolidierte interne Typisierung über `contracts`, `interfaces`, `agents`, `orchestrator`, `services`, `main`
- **P2.2** WS-Inbound als discriminated union abgeschlossen:
    - `WsInboundMessage` in typisierte Varianten aufgeteilt (`user_message`, `subrun_spawn`, `runtime_switch_request`)
    - Parsing auf diskriminierte Union umgestellt; unbekannte Typen bleiben über dedizierten Rejection-Pfad kompatibel
    - gezielte Regression für `request_rejected_unsupported_type` ergänzt
- **P2.3** PipelineRunner-Recovery vereinfacht:
    - reason-spezifische Recovery-Entscheidung aus `_run_with_fallback(...)` in dedizierte Strategy-Methode extrahiert
    - strukturiertes Ergebnisobjekt (`RecoveryStrategyResolution`) für Retry/Branch/Strategy-Status eingeführt
    - bestehende Lifecycle-Events und Verhalten beibehalten, Komplexität im Hauptpfad reduziert
- **P2.4** AgentConstraints konsistent verdrahtet:
    - `LlmClient` erweitert um optionale `temperature`-Übergabe für Completion/Streaming
    - OpenAI-kompatible und native Ollama-Payloads übernehmen `temperature` konsistent
    - Planner- und Synthesizer-Agent nutzen `constraints.temperature` nun direkt in LLM-Aufrufen
- **P2.5** Streaming-Timeout/Cancellation im `SynthesizerAgent` umgesetzt
- **Coverage-Gate** (`pytest-cov`) eingeführt:
        - globale Mindestabdeckung aktiv (`--cov-fail-under=70`)
        - modulbezogene Mindestabdeckung für kritische Module aktiv:
            - `llm_client.py` >= 60%
            - `tools.py` >= 70%
            - `pipeline_runner.py` >= 80%
        - CI-Workflow + lokale Start-Testskripte validieren Coverage verpflichtend

### 8.2 Teilweise erledigt

- **P1.5** `main.py` aufteilen abgeschlossen  
    **Erledigt:**
    - App-Erzeugung/CORS/Lifespan in `app_setup.py` extrahiert.
    - Startup-/Shutdown-Aufgaben in `startup_tasks.py` extrahiert.
    - `/api/test/agent`, `/api/runs/start` und `/api/runs/{run_id}/wait` in `run_endpoints.py` ausgelagert (Main delegiert nur noch).
    - Finale Router-Entkopplung für Run-API umgesetzt (`routers/run_api.py`), direkte `@app`-Dekorator-Endpunkte in `main.py` entfernt.
    - WebSocket-Route `/ws/agent` in dediziertes Router-Modul `routers/ws_agent_router.py` verschoben.
    - Control-Policy-Approval-Endpunkte in `routers/control_policy_approvals.py` ausgelagert.
    - Subrun-Endpunkte in `subrun_endpoints.py` ausgelagert.
    - Runtime-Debug-Endpunkte in `runtime_debug_endpoints.py` ausgelagert.
    - Control-Router-Wiring in `control_router_wiring.py` konsolidiert.


### 8.3 Noch offen

- **P1.1** HeadAgent weiter modularisieren (`intent_detector`, `reply_shaper`, `action_augmentation`, etc.)

### 8.4 Nächste sinnvolle Reihenfolge

1. **P1.1:** verbleibende HeadAgent-Modularisierung gezielt abschließen

Verifiziert durch fokussierte Testläufe:
- `backend/tests/test_tools_web_fetch_security.py`
- `backend/tests/test_tools_command_security.py`
- `backend/tests/test_agent_tooling_extended.py`
- `backend/tests/test_llm_client.py`
- `backend/tests/test_tool_selection_offline_eval.py`
- `backend/tests/test_session_lane_manager.py`
- `backend/tests/test_synthesizer_agent.py`
- `backend/tests/test_backend_e2e.py`
- `backend/tests/test_runtime_manager_auth.py`
- `backend/tests/test_ws_handler.py`
- `backend/tests/test_subrun_lane.py`
- `backend/tests/test_subrun_visibility_scope.py`

Zusätzlich verifiziert nach P2.2-Umstellung:
- `backend/tests/test_ws_handler.py` (**5 passed**, inkl. `unsupported_type`-Rejection-Regression)
- `backend/tests/test_runtime_manager_auth.py` + `backend/tests/test_tool_selection_offline_eval.py` (**44 passed**)
- `backend/tests/test_backend_e2e.py` (**29 passed**)

Zusätzlich verifiziert nach P2.3-Refactor:
- `backend/tests/test_model_router.py` (**30 passed**)
- `backend/tests/test_backend_e2e.py` (**29 passed**)

Zusätzlich verifiziert nach P2.4-Umsetzung:
- `backend/tests/test_llm_client.py` (**7 + 2 neue = 9 passed**)
- `backend/tests/test_synthesizer_agent.py` (**2 passed**)
- `backend/tests/test_tool_selection_offline_eval.py` + `backend/tests/test_model_router.py` (**70 passed**)
- `backend/tests/test_backend_e2e.py` (**29 passed**)

Zusätzlich verifiziert nach Coverage-Gate-Integration:
- `pytest backend/tests -q --cov=backend/app --cov-fail-under=70` (**262 passed, 3 skipped**, global **82.52%**)
- `backend/scripts/check_coverage_thresholds.py` (CI-Pfadformat) **passed**
- `backend/scripts/check_coverage_thresholds.py` (lokales `app/...`-Pfadformat) **passed**

Zusätzlich verifiziert nach P1.5-Restbereinigung:
- `backend/tests/test_runtime_manager_auth.py` + `backend/tests/test_ws_handler.py` (**9 passed**)
- `backend/tests/test_control_plane_contracts.py` + `backend/tests/test_backend_e2e.py` (**96 passed**)

### 8.5 Session-Handover (für nächste Session)

**Kurzstatus**
- Security- und Stabilitäts-Härtungen aus P0 sind abgeschlossen und regressionsgetestet.
- P1.3 ist vollständig abgeschlossen (SessionLaneManager + Subrun-Retention/GC).
- P1.5 ist funktional weitgehend umgesetzt; Restbereinigung in `main.py` ist optional.
- P2.1 ist abgeschlossen (zentraler Tool-Policy-Typ + Boundary-Normalisierung).
- P2.2 und P2.3 sind abgeschlossen (WS-Union + vereinfachte Recovery-Strategie im PipelineRunner).
- P2.4 ist abgeschlossen (AgentConstraints `temperature` wird über Agenten bis zum LLM-Payload durchgereicht).
- Coverage-Gate ist aktiv (global + kritische Module) und in CI/Skripten verdrahtet.
- P1.5 ist nun vollständig abgeschlossen (inkl. finaler Run-API-Router-Entkopplung).

**Letzter validierter Teststand**
- Fokussierte Regressionen: **48 passed**
    - `backend/tests/test_ws_handler.py`
    - `backend/tests/test_runtime_manager_auth.py`
    - `backend/tests/test_tool_selection_offline_eval.py`
- E2E-Regression: **29 passed**
    - `backend/tests/test_backend_e2e.py`

**Empfohlener Einstieg in der nächsten Session**
1. **P1.1** gezielt auf verbleibende HeadAgent-Module abschließen.

**P2.2 Abschluss-Check (erfüllt)**
- Kein breites Sammelmodell mit vielen optionalen Feldern mehr für WS-Inbound.
- Eindeutige, typisierte Message-Varianten pro `type`.
- WS-/Runtime-Regressionen und E2E nach Umstellung grün.
