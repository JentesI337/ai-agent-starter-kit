# Agent Capability Gaps — Roadmap zu nahezu universeller Problemlösungsfähigkeit

## Meta
- ID: issue-0004
- Status: open
- Priorität: critical
- Owner: unassigned
- Erstellt: 2026-03-04
- Zuletzt aktualisiert: 2026-03-04

## Kontext

Eine systematische Analyse der aktuellen Architektur zeigt, dass die Plan → Tool-Selection → Execute → Synthesize Pipeline solide fundiert ist, aber 17 strukturelle Lücken den Agenten daran hindern, realistische Probleme autonom zu lösen. Dieses Issue dokumentiert alle Gaps mit exakten Code-Referenzen, bewertet ihren Impact und definiert konkrete Akzeptanzkriterien.

Die bestehende Infrastruktur umfasst: 14 Kern-Tools, MCP Bridge, 72+ Skills, LTM/Episodic Memory, Tool Policy, Session Memory, Fallback-State-Machine, SubrunLane für parallele Sub-Agents.

---

## TIER 1 — Fundamentale Blocker

*Ohne diese Lücken geschlossen zu haben, scheitert die Mehrheit realer Aufgaben — nicht graduell, sondern binär.*

---

### Gap 1 — Isolierte Code-Ausführungs-Sandbox

**Bezug zu:** issue-0003 (offen, ungelöst)

**IST-Zustand:**
`run_command` in [backend/app/tools.py](../backend/app/tools.py) läuft direkt auf dem Host-Prozess. Die Safety-Patterns in [tools.py](../backend/app/tools.py#L27) blockieren alle sinnvollen Ausführungsformen:

```python
# backend/app/tools.py:L27–L53 (COMMAND_SAFETY_PATTERNS)
(r"\bpython[23]?\s+-c\b",             "python -c execution is blocked"),
(r"\b(?:bash|sh|zsh)\b[^\n]*\s-c\b",  "shell -c execution is blocked"),
(r"\|\|?|&&|;|`|\$\(",                 "shell chaining and command substitution are blocked"),
(r"\bcurl\b.*\|\s*(?:ba)?sh\b",        "curl pipe-to-shell execution is blocked"),
```

**Konsequenz:** Der Agent kann selbst generierten Code nicht ausführen und testen. Jede Coding-Aufgabe endet beim Schreiben — es gibt keine Verifikationsschleife.

**SOLL:**
Ein neues Tool `run_code(language, code, stdin?)` mit ephemerem Execution-Jail:
- **Strategie 1:** Docker-Container (`python:3.12-slim`, `node:20-alpine`) — ephemer, kein Netzwerk, CPU/RAM-Limits via `--memory 256m --cpus 0.5`
- **Strategie 2:** `subprocess.run` mit `env={}` (kein PATH, kein HOME), `cwd=tmpdir`, `timeout=30`, `preexec_fn=os.setsid` auf Linux
- **Strategie 3:** `RestrictedPython` als Fallback ohne Systemzugriff

**Akzeptanzkriterien:**
- [ ] `run_code` als `ToolSpec` in [backend/app/services/tool_registry.py](../backend/app/services/tool_registry.py) registriert
- [ ] Ausführung läuft nie unter dem Server-PID-Namespace ohne explizites Flag
- [ ] stdout/stderr getrennt, max 10 000 Zeichen Output
- [ ] Timeout erzwungen, kein Hang möglich
- [ ] Tests: Erfolgsfall, Timeout, Syntaxfehler, Zugriff auf `/etc/passwd` geblockt

---

### Gap 2 — Browser Automation (kein JS-Rendering)

**IST-Zustand:**
`web_fetch` in [backend/app/tools.py](../backend/app/tools.py) nutzt `httpx` für statisches HTML. Die Tool-Spec liegt in [backend/app/services/tool_registry.py](../backend/app/services/tool_registry.py). Dynamisch geladene Inhalte (SPAs, OAuth-Flows, Formulare) sind nicht erreichbar.

```python
# backend/app/tools.py — web_fetch nutzt ausschließlich httpx
# ~70 % des modernen Webs rendert per JavaScript
```

**SOLL:**
Ein neues Tool `browser_action(url, action?, selector?, wait_for?)`:
- Playwright via `asyncio`-Subprocess oder als MCP-Server (`@playwright/mcp`)
- Actions: `navigate`, `click`, `fill`, `screenshot`, `extract_text`
- SSRF-Schutz identisch zu `web_fetch` (private IP-Ranges geblockt)
- Screenshot-Output als Base64 für Multimodal-Pipeline (→ Gap 5)

**Akzeptanzkriterien:**
- [ ] Tool `browser_action` in `tool_registry.py` mit `capabilities=("web_interaction", "web_retrieval")`
- [ ] Playwright optional — bei fehlendem Package `ImportError` → Tool disabled, kein Startup-Crash
- [ ] SSRF-Schutz aus `web_fetch` wiederverwendet
- [ ] Integration in Tool Policy (`browser_interaction` capability)

---

### Gap 3 — Semantische Suche / RAG über Workspace

**IST-Zustand:**
Der Agent navigiert Dateien durch `list_dir` → `read_file` — manuell, linear, ohne Semantik. Bei 500+ Dateien ist dies faktisch unbrauchbar. Es gibt kein Vektor-Index-Tool weder in [backend/app/tool_catalog.py](../backend/app/tool_catalog.py) noch in [backend/app/services/tool_registry.py](../backend/app/services/tool_registry.py).

**SOLL:**
- `semantic_search(query, top_k?, scope?)` als Tool
- Vektor-Index (SQLite-vec oder ChromaDB) über Workspace-Dateien
- Inkrementelles Re-Indexing bei `write_file`-Calls (Hook in [backend/app/tools.py](../backend/app/tools.py))
- Embedding: lokales `nomic-embed-text` (Ollama) oder OpenAI `text-embedding-3-small`

**Akzeptanzkriterien:**
- [ ] `VectorIndexService` in `backend/app/services/`
- [ ] `semantic_search` Tool in `tool_registry.py`
- [ ] Index wird bei Serverstart gebaut (async, blockiert nicht)
- [ ] `write_file` triggert inkrementelles Update
- [ ] Fallback: wenn kein Embedding-Model verfügbar → BM25-Textsuche

---

### Gap 4 — Credential Vault / Secret Manager

**IST-Zustand:**
`CustomAgentDefinition` und `AgentIsolationProfile` definieren `credential_scope`:

```python
# backend/app/custom_agents.py:L25
credential_scope: str | None = Field(default=None, min_length=1, max_length=120)

# backend/app/services/agent_isolation.py:L36
credential_scope: str
```

Das Feld ist aber nur ein String-Label ohne Backing-Implementierung. Es gibt keinen Vault, keinen Secret-Lookup und keine Credential-Injection ins Tool-System. API-Keys müssten im Klartext im Prompt landen.

**SOLL:**
- `CredentialVault` Service mit `keyring`-Backend (oder `.env`-File + verschlüsseltem SQLite)
- `inject_credentials(tool_name, args, credential_scope)` — secrets nie in Prompts
- Tool-System fragt Vault vor Execution (Hook in `ToolExecutionManager`)
- CRUD-API `GET/POST/DELETE /api/credentials` (nur localhost, kein Remote)

**Akzeptanzkriterien:**
- [ ] `CredentialVault` in `backend/app/services/credential_vault.py`
- [ ] `credential_scope` in `agent_isolation.py` ist kein toter Code mehr
- [ ] Secrets erscheinen nie in Event-Streams, Logs oder LTM
- [ ] Tests: Injection, Scope-Isolation, fehlender Credential → klarer Fehler

---

## TIER 2 — Schwerwiegende Einschränkungen

---

### Gap 5 — Multimodal: Bilder, PDFs, Audio

**IST-Zustand:**
`VisionService` in [backend/app/services/vision_service.py](../backend/app/services/vision_service.py) existiert, ist aber auf image-only beschränkt. Es fehlen:

```python
# Nicht vorhanden in backend/app/tools.py oder tool_catalog.py:
# - pdf_extract(path) → PyMuPDF / pdfplumber
# - ocr_image(path)   → Tesseract / EasyOCR
# - transcribe(path)  → faster-whisper / whisper.cpp
```

**SOLL:**
- `read_pdf(path)` Tool mit `PyMuPDF` oder `pdfplumber`
- `transcribe_audio(path)` Tool mit `faster-whisper`
- `describe_image(path_or_url)` — bestehenden `VisionService` als Tool exponieren
- Alle drei als optional (feature-flag per `config.py`, analog zu `vision_enabled`)

**Akzeptanzkriterien:**
- [ ] Je ein neues Tool in `tool_registry.py` pro Format
- [ ] Feature-Flag in [backend/app/config.py](../backend/app/config.py) identisch zu `vision_enabled`-Muster
- [ ] Bei deaktiviertem Flag: Tool aus `allowed_tools` entfernt (analog zu [Vision-Policy-Test](../backend/tests/test_backend_e2e.py))

---

### Gap 6 — Long-Running Tasks / Checkpoint-Resume

**IST-Zustand:**
Alle Agent-Runs sind via `asyncio.Task` an die WebSocket-Verbindung in [backend/app/ws_handler.py](../backend/app/ws_handler.py) gebunden. Getrennte Verbindung = verlorener Run. `SubrunLane` in [backend/app/orchestrator/subrun_lane.py](../backend/app/orchestrator/subrun_lane.py) hat `spawn()`, `kill()`, `list_runs()` — aber kein Resume-Protokoll.

```python
# backend/app/ws_handler.py:L906
run_id = await deps.subrun_lane.spawn(...)
# Kein: await deps.subrun_lane.resume(run_id)
```

**SOLL:**
- Persistenter Job-Queue (SQLite-backed) mit `status ∈ {pending, running, paused, done, failed}`
- `run_id` als primärer Identifier, persistent über Verbindungsabbrüche hinaus
- `GET /api/runs/{run_id}/stream` — SSE-Stream für Reconnect
- Checkpoint-Marker nach jedem abgeschlossenen Plan-Schritt

**Akzeptanzkriterien:**
- [ ] `JobQueueService` in `backend/app/services/`
- [ ] `SubrunLane.resume(run_id)` implementiert
- [ ] Client-seitig: Angular auto-reconnect mit `run_id`-based Resume
- [ ] Test: WS-Disconnect mid-run → Resume liefert korrekte restliche Events

---

### Gap 7 — Strukturierte Daten: SQL / CSV / JSON-Processing

**IST-Zustand:**
Kein `query_database`, kein `process_csv`, kein `jq`-Tool in [backend/app/tool_catalog.py](../backend/app/tool_catalog.py). Datenanalyse ist auf `run_command` angewiesen — das durch Safety-Patterns [tools.py:L44](../backend/app/tools.py#L44) geblockt ist.

**SOLL:**
- `query_csv(path, sql)` — DuckDB in-memory über CSV/Parquet
- `query_sqlite(path, sql)` — beschränkt auf `SELECT` (read-only guard)
- `jq_query(json_str, expression)` — `jq`-Python-Bindings

**Akzeptanzkriterien:**
- [ ] Alle drei als `ToolSpec` in `tool_registry.py`
- [ ] `query_sqlite` erlaubt ausschließlich `SELECT`-Statements (regex guard)
- [ ] DuckDB als optionale Dep in [backend/requirements.txt](../backend/requirements.txt)

---

### Gap 8 — Echter paralleler Multi-Agent-Rückkanal

**IST-Zustand:**
`spawn_subrun` ist fire-and-forget. Der rufende Agent erhält keinen Rückgabewert aus dem Sub-Run:

```python
# backend/app/agent.py:L2187–L2188
if self._spawn_subrun_handler is None:
    raise ToolExecutionError("spawn_subrun is not configured for this runtime.")
# Rückgabe: run_id (string) — kein await auf Ergebnis
```

`PlanGraph` unterstützt `depends_on` Kanten ([backend/app/services/plan_graph.py:L15](../backend/app/services/plan_graph.py#L15)), aber der Executor verfolgt keine echten Parallelausführungen mit Rendezvous.

**SOLL:**
- `spawn_subrun_and_wait(message, timeout?)` — wartet auf `request_completed` des Sub-Runs
- Shared State-Bus zwischen parallelen Agents (SQLite-backed Mailbox)
- `PlanGraph`-Executor startet `depends_on=[]`-Schritte parallel via `asyncio.gather`

**Akzeptanzkriterien:**
- [ ] `spawn_subrun_and_wait` in `tool_registry.py`
- [ ] `SubrunLane.await_result(run_id, timeout)` implementiert
- [ ] DAG-Executor: Steps ohne Abhängigkeiten werden parallel gestartet

---

### Gap 9 — Strukturierter Human-in-the-Loop mid-task

**IST-Zustand:**
`PolicyApprovalHandler` in [backend/app/agent.py:L59](../backend/app/agent.py#L59) ist definiert als:

```python
# backend/app/agent.py:L59
PolicyApprovalHandler = Callable[..., Awaitable[bool]]
# Ausschließlich boolesches Approve/Deny — kein Frage-Antwort-Dialog
```

Es gibt kein Mechanismus für mehrstufige Klärung, Option-Auswahl oder "Pausiere hier, frage Nutzer".

**SOLL:**
- `ask_user(question, options?)` als Tool — blockiert den Agent-Run, wartet auf WS-Response
- Neues WS-Message-Typ `agent_question` / `user_answer`
- Timeout: nach N Sekunden → Default-Antwort oder Abbruch
- `PolicyApprovalHandler` erweitert auf `Callable[..., Awaitable[bool | str | dict]]`

**Akzeptanzkriterien:**
- [ ] `ask_user` Tool in `tool_registry.py`
- [ ] WS-Protokoll um `agent_question`/`user_answer` Envelopes erweitert
- [ ] Frontend: Eingabe-Dialog bei `agent_question`-Event
- [ ] Test: Agent pausiert, Antwort kommt, Run wird fortgesetzt

---

## TIER 3 — Qualitätsmultiplikatoren

---

### Gap 10 — Token-Budget-Kontrolle

**IST-Zustand:**
`ContextReducer` in [backend/app/state/context_reducer.py](../backend/app/state/context_reducer.py) kürzt Kontext per Zeichenanzahl-Heuristik. Es gibt kein kumulatives Token-Tracking über den gesamten Request-Lifecycle. Der Agent kann in einer `max_replan_attempts`-Schleife verschwinden ohne Cost-Ceiling.

```python
# backend/app/state/context_reducer.py:L42
clipped_tools = self._collect_items(tool_outputs, max_chars=max_chars // 2, max_tokens=tool_budget)
# max_chars-Heuristik — kein echter Token-Zähler aus LLM-Responses
```

**SOLL:**
- Token-Zähler aus LLM-Responses (OpenAI: `usage.total_tokens`, Ollama: `eval_count`)
- `RequestBudgetGuard`: bricht Request ab bei `>= budget_tokens_ceiling`
- Konfigurierbar in [backend/app/config.py](../backend/app/config.py) als `max_request_tokens`

**Akzeptanzkriterien:**
- [ ] `RequestBudgetGuard` in `backend/app/services/`
- [ ] LLM-Client gibt `usage` zurück und akkumuliert über Request-Lifecycle
- [ ] Bei Überschreitung: `lifecycle`-Event `request_failed_budget` + Graceful-Synthesis

---

### Gap 11 — Autonome TDD-Schleife

**IST-Zustand:**
`ReflectionService` und `VerificationService` in [backend/app/services/](../backend/app/services/) existieren. Aber es gibt keine closed-loop Sequenz: *Write test → run → assert → fix → repeat*.

Der Agent schreibt Code und Tests getrennt ohne Feedback-Verbindung zwischen beiden.

**SOLL:**
- `tdd_loop(test_path, max_iterations?)` Tool — kombiniert `run_code` + `read_file` + `write_file`
- Stoppt bei grünem Exit-Code oder nach `max_iterations`
- Gibt Iterations-Trace zurück (Fehler pro Iteration)

**Akzeptanzkriterien:**
- [ ] Abhängig von Gap 1 (run_code)
- [ ] `tdd_loop` in `tool_registry.py`
- [ ] Max-Iterations-Limit erzwungen (verhindert infinite loops)

---

### Gap 12 — Zeitbewusstsein / Scheduling

**IST-Zustand:**
Der Agent hat kein Zeitbewusstsein ohne explizite Übergabe. Kein `datetime`-Tool, kein Cron-Scheduler.

**SOLL:**
- `get_current_time(timezone?)` als leichtgewichtiges Tool
- Cron-artiger Scheduler als optionaler Service: `schedule_run(cron_expr, message, agent_id)`

**Akzeptanzkriterien:**
- [ ] `get_current_time` Tool in `tool_registry.py`
- [ ] System-Prompt injiziert aktuelles Datum/Uhrzeit automatisch (analog zu LTM-Kontext)

---

### Gap 13 — Tool-Komposition ohne LLM-Relay

**IST-Zustand:**
Tools sind atomar. Jeder Output geht durch das LLM als Vermittler zurück in den nächsten Tool-Call. Bei mehrfach verketteten Tools akkumulieren sich Parsing-Fehler durch `ActionParser.parse()` / `_repair_tool_selection_json()`:

```python
# backend/app/agent.py:L1995–L1996
async def _repair_tool_selection_json(self, raw: str, model: str | None) -> str:
    return await self._action_parser.repair(...)
```

**SOLL:**
- `pipe(steps: list[{tool, args_template}])` Tool — deklarative Pipeline ohne LLM-Relay
- `args_template` unterstützt `${prev.stdout}` als Variable
- Nur für deterministische Datenflüsse — LLM bleibt Orchestrator für Logik

**Akzeptanzkriterien:**
- [ ] `pipe` Tool in `tool_registry.py`
- [ ] Template-Resolver für `${prev.*}` Variablen
- [ ] Depth-Limit (max 10 Steps) gegen infinite chains

---

### Gap 14 — Skill-Synthese / Selbstverbesserung

**IST-Zustand:**
`LongTermMemoryStore` speichert `FailureEntry` und `EpisodicEntry`:

```python
# backend/app/services/long_term_memory.py:L10
class FailureEntry: ...
# backend/app/services/long_term_memory.py:L31
class EpisodicEntry: ...
```

Der Agent lernt jedoch nicht daraus. LTM ist passiv — kein Mechanismus zur Skill-Generierung, kein Prompt-Tuning, keine Heuristik-Ableitung.

**SOLL:**
- Nightly/On-Demand: `synthesize_skill_from_failures(task_type)` — generiert neue `SKILL.md` aus LTM-Pattern
- `promote_episodic_to_skill(entry_id)` — explizit gelungene Episoden als Skills verankern
- Rückkopplung: generierte Skills landen in `examplerepos/skills/` und werden durch `SkillsService` entdeckt

**Akzeptanzkriterien:**
- [ ] `SkillSynthesisService` in `backend/app/services/`
- [ ] Generierte Skills validiert (SKILL.md-Format) bevor sie gespeichert werden
- [ ] Opt-in per Config-Flag (default: off)

---

## Runde 2 — Strukturelle Architektur-Schwächen

*Diese drei wurden bei erster Analyse unterschätzt und sind orthogonal zu den obigen Gaps.*

---

### Gap A — Fehlendes deterministisches Output-Format pro Tool

**IST-Zustand:**
Das LLM entscheidet frei, wie es Tool-Calls formatiert. `ActionParser` + `_repair_tool_selection_json` ([backend/app/agent.py:L1995](../backend/app/agent.py#L1995)) flicken das im Nachhinein. Bei function-calling-fähigen Modellen funktioniert es besser, aber der Text-Parsing-Fallback ist strukturell brüchig.

```python
# backend/app/agents/tool_selector_agent.py — ToolSelectorAgent nutzt
# ToolSelectorRuntime, die je nach Modell function calling ODER Text-Parsing wählt
# Bei Text-Parsing: Fehler akkumulieren sich bei komplexen verketteten Tasks
```

**SOLL:**
- Strict JSON-Mode erzwingen (OpenAI: `response_format={"type": "json_object"}`)
- Ollama: `format: "json"` in jedem Tool-Selection-Call
- Fallback: XML-basiertes Format (robuster gegen LLM-Freitext-Tendenz)

**Akzeptanzkriterien:**
- [ ] `LlmClient.complete_chat` akzeptiert `force_json: bool` Parameter
- [ ] `ToolSelectorAgent` setzt `force_json=True` wenn Modell es unterstützt
- [ ] Feature-Flag in `config.py`: `tool_selection_strict_json_enabled`

---

### Gap B — Kein Causal Reasoning über Plan-Abhängigkeiten

**IST-Zustand:**
`PlanGraph` unterstützt `depends_on` ([backend/app/services/plan_graph.py:L15](../backend/app/services/plan_graph.py#L15)), aber der `PlannerAgent` befüllt die Kanten nicht zuverlässig:

```python
# backend/app/agents/planner_agent.py:L118
def _parse_structured_plan(self, raw_plan: str) -> PlanGraph:
    # LLM-Output enthält depends_on nur wenn LLM es explizit schreibt
    # Kein deterministischer Dependency-Inference-Pass
```

Plan-Graph-Schritte werden sequenziell ausgeführt, auch wenn Parallelisierung möglich wäre.

**SOLL:**
- Post-Processing Pass nach `_parse_structured_plan`: inferiert `depends_on` aus Schritt-Texten (Tool-Output-Referenzen)
- `PlanGraph.ready_steps()` bereits implementiert ([backend/app/services/plan_graph.py:L34](../backend/app/services/plan_graph.py#L34)) — Executor muss alle `ready_steps()` parallel starten

**Akzeptanzkriterien:**
- [ ] `DependencyInferencePass` in `plan_graph.py`
- [ ] `PipelineRunner` startet parallele `ready_steps()` via `asyncio.gather`
- [ ] Test: Plan mit 2 independenten Schritten → beide starten gleichzeitig

---

### Gap C — Keine Persistente Episodische Identität

**IST-Zustand:**
`EpisodicEntry` existiert in [backend/app/services/long_term_memory.py:L31](../backend/app/services/long_term_memory.py#L31) mit `search_episodic()`. Aber:
- Der Agent schreibt keine Episodic-Entries für erfolgreiche Tasks
- Es gibt kein "Projektgedächtnis": der Agent weiß nicht, dass er letzte Woche an diesem Repo gearbeitet hat
- `_build_long_term_memory_context` in [backend/app/agent.py](../backend/app/agent.py) sucht nur Failures, keine Episodic-Entries für ähnliche frühere Tasks

**SOLL:**
- Nach jedem `request_completed`: schreibe `EpisodicEntry` mit Task, Tools verwendet, Ergebnis-Summary
- `_build_long_term_memory_context` injiziert top-3 ähnliche episodische Einträge
- "Projekt-Scope" als optionaler Kontext: alle Episodic-Entries für `workspace_root`

**Akzeptanzkriterien:**
- [ ] `EpisodicEntry`-Write nach jedem erfolgreichen Request in `ws_handler.py`
- [ ] `_build_long_term_memory_context` erweitert um Episodic-Lookup
- [ ] Test: zweiter Request zu gleichem Task → Episodischer Kontext sichtbar in Prompt

---

## Priorisierungsmatrix

| # | Lücke | Tier | Impact | Aufwand | Priorität |
|---|-------|------|--------|---------|-----------|
| 1 | Code-Execution-Sandbox | T1 | Kritisch | M | **P0** |
| 2 | Browser Automation | T1 | Sehr hoch | M | **P0** |
| 3 | Semantische Suche / RAG | T1 | Sehr hoch | M | **P0** |
| 4 | Credential Vault | T1 | Sehr hoch | S | **P0** |
| 5 | Multimodal (PDF/Audio/Image) | T2 | Hoch | S–M | **P1** |
| 6 | Long-Running Tasks / Resume | T2 | Hoch | L | **P1** |
| 7 | SQL / CSV / JSON Tools | T2 | Hoch | S | **P1** |
| B | DAG-Parallelplanung | Arch | Hoch | M | **P1** |
| 8 | Paralleler Multi-Agent-Kanal | T2 | Hoch | M | **P1** |
| A | Deterministisches Tool-Output-Format | Arch | Mittel | S | **P2** |
| 9 | Structured Human-in-the-Loop | T2 | Mittel | M | **P2** |
| 10 | Token-Budget-Kontrolle | T3 | Mittel | S | **P2** |
| C | Persistente Episodische Identität | Arch | Mittel | M | **P2** |
| 11 | Autonome TDD-Schleife | T3 | Mittel | M | **P2** |
| 12 | Zeitbewusstsein / Scheduling | T3 | Niedrig | S | **P3** |
| 13 | Tool-Komposition ohne LLM-Relay | T3 | Mittel | L | **P3** |
| 14 | Skill-Synthese / Selbstverbesserung | T3 | Niedrig | XL | **P3** |

*Aufwand: S = Stunden–1 Tag · M = 2–5 Tage · L = 1–2 Wochen · XL = Forschungsarbeit*

---

## Abhängigkeitsgraph

```
Gap 1 (run_code)
  └── Gap 11 (TDD-Loop)

Gap 3 (RAG)
  └── Gap C (Episodic Identity — wenn Embedding vorhanden)

Gap 6 (Checkpoint-Resume)
  └── Gap 8 (Multi-Agent Rendezvous)

Gap 4 (Credential Vault)
  └── Gap 2 (Browser Automation — Auth-Flows)

Gap B (DAG-Dependency-Inference)
  └── Gap 8 (Multi-Agent Parallelism)
```

## Notizen

- Gap 1 und Gap 3 sind die höchsten ROI-Investitionen — sie multiplizieren die Nützlichkeit aller anderen Features
- Gap 4 (Credential Vault) hat den niedrigsten Aufwand bei sehr hohem Impact — Quick-Win
- Gap A (deterministisches Tool-Format) sollte parallel zu jedem anderen P0 angegangen werden, da es alle anderen stabilisiert
- `credential_scope` in `custom_agents.py:L25` und `agent_isolation.py:L36` sind dead code bis Gap 4 umgesetzt ist
- `PlanGraph.ready_steps()` in `plan_graph.py:L34` ist bereits korrekt implementiert — der einzige fehlende Teil für Gap B ist der parallele Executor
