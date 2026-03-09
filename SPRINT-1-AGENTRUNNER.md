# Sprint 1 — AgentRunner Refactoring: Continuous Streaming Tool Loop

> **Zeitraum:** 09.03.2026 – 23.03.2026 (2 Wochen)  
> **Ziel:** Phase A + Phase B vollständig implementiert und getestet. Feature-Flag `USE_CONTINUOUS_LOOP` erlaubt parallelen Betrieb mit dem altem 3-Phase-Code.  
> **Basis-Dokument:** `AgentRunnerRefactoring.md`  
> **Kapazität:** ~60 Story Points (1 SP ≈ halber Tag fokussierte Arbeit)

---

## Sprint-Strategie

Dieser Sprint deckt **Phase A (Grundgerüst)** und **Phase B (Streaming Tool Loop)** ab — das sind die fundamentalen Bausteine. Phase C–E folgen in Sprint 2.

**Warum A+B zusammen?** Phase A allein ist nicht testbar Ende-zu-Ende. Erst mit Phase B existiert ein funktionsfähiger Loop, der gegen Benchmarks validiert werden kann. Das Feature-Flag wird bereits in Sprint 1 eingebaut, damit jederzeit Rollback möglich ist.

**Nicht in Sprint 1:**
- Phase C (Guards & Safety Migration — kommt in Sprint 2)
- Phase D (Integration & Cutover) — nur das Feature-Flag und der Router-Stub kommen in Sprint 1
- Phase E (Cleanup & Deprecation) — frühestens Sprint 3
- Frontend-Änderungen — neue Events werden gesendet, aber Frontend-UI-Anpassungen sind Sprint 2

---

## Sprint-Übersicht

| # | Ticket | SP | Phase | Prio | Abhängigkeiten |
|---|--------|:--:|:-----:|:----:|----------------|
| S1-01 | Datentypen: `agent_runner_types.py` | 2 | A1 | P0 | — |
| S1-02 | Config: Neue Runner-Settings | 3 | A1 | P0 | — |
| S1-03 | LlmClient: `stream_chat_with_tools()` | 8 | A2 | P0 | S1-01 |
| S1-04 | Unified System Prompt Builder | 5 | A3 | P0 | — |
| S1-05 | AgentRunner Grundstruktur + `__init__` | 4 | A4 | P0 | S1-01, S1-02 |
| S1-06 | AgentRunner: Pre-Loop Setup | 6 | B1 | P0 | S1-05, S1-03 |
| S1-07 | AgentRunner: Continuous Loop Kern | 8 | B1 | P0 | S1-06 |
| S1-08 | AgentRunner: `_execute_tool_calls()` | 6 | B2 | P0 | S1-07 |
| S1-09 | Loop Detection (3 Detektoren) | 3 | B3 | P0 | S1-07 |
| S1-10 | Message Compaction | 3 | B4 | P1 | S1-07 |
| S1-11 | Feature-Flag Router in `HeadAgent.run()` | 4 | D1/D2 | P0 | S1-07 |
| S1-12 | Unit Tests: Datentypen + LlmClient | 4 | — | P0 | S1-01, S1-03 |
| S1-13 | Integration Tests: AgentRunner End-to-End | 6 | — | P0 | S1-08 |
| — | Puffer (Reviews, Bugfixes, Nachjustierung) | 4 | — | — | — |
| | **Gesamt** | **66** | | | |

---

## Reihenfolge & Parallelisierung

```
Woche 1 (09.03 – 13.03):
  ┌─ S1-01 Datentypen ──────────────────────────── (Tag 1)
  ├─ S1-02 Config Settings ─────────────────────── (Tag 1, parallel zu S1-01)
  ├─ S1-04 Unified Prompt Builder ──────────────── (Tag 1-2, parallel zu S1-01/02)
  │
  ├─ S1-03 LlmClient stream_chat_with_tools ────── (Tag 2-4, braucht S1-01)
  ├─ S1-05 AgentRunner Grundstruktur ───────────── (Tag 2-3, braucht S1-01 + S1-02)
  │
  └─ S1-12 Unit Tests Datentypen + LlmClient ──── (Tag 4-5, braucht S1-01 + S1-03)

Woche 2 (16.03 – 20.03):
  ┌─ S1-06 Pre-Loop Setup ─────────────────────── (Tag 6-7, braucht S1-05 + S1-03)
  ├─ S1-07 Continuous Loop Kern ────────────────── (Tag 7-9, braucht S1-06)
  ├─ S1-08 _execute_tool_calls ─────────────────── (Tag 8-9, braucht S1-07)
  ├─ S1-09 Loop Detection ─────────────────────── (Tag 9, braucht S1-07)
  ├─ S1-10 Message Compaction ──────────────────── (Tag 9-10, braucht S1-07)
  ├─ S1-11 Feature-Flag Router ─────────────────── (Tag 10, braucht S1-07)
  └─ S1-13 Integration Tests ──────────────────── (Tag 10-12, braucht S1-08)
```

---

## Ticket-Details

---

### S1-01 — Datentypen: `agent_runner_types.py` (2 SP)

**Datei:** `backend/app/agent_runner_types.py` (NEU)

**Aufgaben:**
- [ ] `ToolCall` Dataclass erstellen (frozen): `id`, `name`, `arguments: dict`
- [ ] `StreamResult` Dataclass erstellen (frozen): `text`, `tool_calls: list[ToolCall]`, `finish_reason`, `usage: dict`
- [ ] `ToolResult` Dataclass erstellen: `tool_call_id`, `tool_name`, `content`, `is_error`, `duration_ms`
- [ ] `LoopState` Dataclass erstellen: `iteration`, `total_tool_calls`, `total_tokens_used`, `elapsed_seconds`, `tool_call_history: list[dict]`, `loop_detected`, `budget_exhausted`, `steer_interrupted`

**Akzeptanz:**
- Alle Dataclasses importierbar und instanziierbar
- `ToolCall` und `StreamResult` sind `frozen=True`
- Kein Import von externen Packages (nur stdlib `dataclasses`, `typing`)

**Referenz:** AgentRunnerRefactoring.md → Phase A1

---

### S1-02 — Config: Neue Runner-Settings (3 SP)

**Datei:** `backend/app/config.py` (ÄNDERN)

**Aufgaben:**
- [ ] Feature-Flag hinzufügen:
  ```python
  use_continuous_loop: bool = False
  ```
- [ ] Loop-Limits hinzufügen:
  ```python
  runner_max_iterations: int = 25
  runner_max_tool_calls: int = 50
  runner_time_budget_seconds: int = 300
  runner_context_budget: int = 4096
  ```
- [ ] Loop-Detection-Settings:
  ```python
  runner_loop_detection_threshold: int = 3
  runner_loop_detection_enabled: bool = True
  ```
- [ ] Compaction-Settings:
  ```python
  runner_compaction_enabled: bool = True
  runner_compaction_tail_keep: int = 4
  runner_tool_result_max_chars: int = 5000
  ```
- [ ] Post-Loop-Settings:
  ```python
  runner_reflection_enabled: bool = True
  runner_reflection_max_passes: int = 1
  ```

**Akzeptanz:**
- Alle Settings haben sinnvolle Defaults
- Settings sind per Env-Variable überschreibbar (Pydantic-Standard)
- Bestehende Settings unverändert
- `pytest` Konfigurationstests grün

**Referenz:** AgentRunnerRefactoring.md → Appendix A

---

### S1-03 — LlmClient: `stream_chat_with_tools()` (8 SP)

**Datei:** `backend/app/llm_client.py` (ÄNDERN)

**Aufgaben:**
- [ ] Neue Methode `stream_chat_with_tools()` implementieren:
  ```python
  async def stream_chat_with_tools(
      self, *,
      messages: list[dict],
      tools: list[dict] | None = None,
      model: str | None = None,
      temperature: float | None = None,
      on_text_chunk: Callable[[str], Awaitable[None]] | None = None,
  ) -> StreamResult
  ```
- [ ] SSE-Streaming-Parser: `data: [DONE]` und `data: {json}` korrekt verarbeiten
- [ ] Tool-Call-Chunks akkumulieren (tool_calls kommen in Teilen über mehrere Chunks)
- [ ] Gleichzeitig Text-Content sammeln UND streamen (via `on_text_chunk` Callback)
- [ ] `finish_reason` korrekt erkennen: `"stop"`, `"tool_calls"`, `"length"`
- [ ] `usage` aus finalem Chunk extrahieren (wenn Provider es liefert)
- [ ] Tool-Call-Arguments JSON parsen mit Fallback bei Parse-Error (`{"_raw": raw_string}`)
- [ ] Non-Streaming-Fallback für Provider ohne Streaming-Support (Ollama native):
  - Erkennung via `_is_native_ollama_api()`
  - Bei Ollama: Non-Streaming-Request, Ergebnis in `StreamResult` umwandeln
- [ ] Bestehende Retry-Logik (`RETRYABLE_STATUS_CODES`, exponentielles Backoff) wiederverwenden
- [ ] **Keine** bestehenden Methoden ändern oder entfernen

**Technische Details:**
- Die neue Methode akzeptiert ein vollständiges `messages`-Array (nicht nur system_prompt + user_prompt wie die alten Methoden)
- `tools` im OpenAI-Format: `[{"type": "function", "function": {"name": "...", "parameters": {...}}}]`
- `tool_choice: "auto"` wenn `tools` gesetzt, sonst nicht im Payload
- Nutzt `self._session` (bestehende `aiohttp.ClientSession`) für HTTP-Requests
- Import von `StreamResult`, `ToolCall` aus `agent_runner_types`

**Akzeptanz:**
- Bestehende Tests in `test_llm_client.py` weiterhin grün
- Neue Methode funktioniert mit OpenAI-kompatiblen APIs
- Neue Methode funktioniert mit Ollama (Non-Streaming-Fallback)
- Tool-Call-Chunks werden korrekt zu vollständigen ToolCalls zusammengesetzt
- Text wird sowohl gesammelt (in `StreamResult.text`) als auch live gestreamt (via Callback)
- Bei JSON-Parse-Fehler in Tool-Arguments: kein Crash, sondern `{"_raw": "..."}`

**Referenz:** AgentRunnerRefactoring.md → Phase A2

**Risiko:** Dies ist das technisch anspruchsvollste Ticket — SSE-Parsing mit fragmentierten Tool-Calls erfordert sorgfältiges Testen mit realen Provider-Responses.

---

### S1-04 — Unified System Prompt Builder (5 SP)

**Datei:** `backend/app/agent_runner.py` (NEU, oder eigene Datei `backend/app/prompt_builder.py`)

**Aufgaben:**
- [ ] Funktion `build_unified_system_prompt()` implementieren:
  ```python
  def build_unified_system_prompt(
      role: str,
      plan_prompt: str,
      tool_hints: str,
      final_instructions: str,
      guardrails: str,
  ) -> str
  ```
- [ ] Prompt-Struktur gemäß Appendix C:
  1. Rolle & Identität (extrahiert aus `plan_prompt`)
  2. Arbeitsweise (LLM entscheidet selbst ob/welche Tools)
  3. Tool-Hinweise (aus `tool_selector_prompt`)
  4. Antwort-Format (aus `final_prompt`)
  5. Guardrails & Safety
- [ ] **NICHT** in den Prompt schreiben: "Erstelle zuerst einen Plan", "Wähle dann Tools aus" — das LLM soll natürlich arbeiten
- [ ] Prompt mit `PromptProfile` kompatibel machen — nimmt die 3 existierenden Prompt-Felder und fusioniert sie
- [ ] Skills-Prompt-Abschnitt berücksichtigen (aus `SkillSnapshot.prompt` — wird als optionaler Parameter durchgereicht)
- [ ] Bestehende `agent_rules.md` und `tool_routing.md` aus `prompts/` weiterhin berücksichtigen

**Akzeptanz:**
- Generierter Prompt ist kürzer als die Summe der 3 Einzel-Prompts (kein Duplikat-Content)
- Prompt enthält keine Phasen-Anweisungen ("erst planen, dann Tools, dann antworten")
- Prompt funktioniert für alle 13 Agent-Rollen (head, coder, researcher, architect, test, security, doc, refactor, devops, fintech, healthtech, legaltech, ecommerce, industrytech)
- Unit Test: Prompt enthält Rolle, Tool-Hinweise, Antwort-Richtlinien und Guardrails

**Referenz:** AgentRunnerRefactoring.md → Phase A3 + Appendix C

---

### S1-05 — AgentRunner Grundstruktur + `__init__` (4 SP)

**Datei:** `backend/app/agent_runner.py` (NEU)

**Aufgaben:**
- [ ] Klasse `AgentRunner` erstellen mit `__init__`:
  ```python
  class AgentRunner:
      def __init__(
          self, *,
          client: LlmClient,
          memory: MemoryStore,
          tools: AgentTooling,
          tool_registry: ToolRegistry,
          context_reducer: ContextReducer,
          system_prompt: str,
          reflection_service: ReflectionService | None = None,
          tool_execution_manager: ToolExecutionManager,
          arg_validator: ToolArgValidator,
          settings: Settings,
      ):
  ```
- [ ] Loop-Limits aus Settings übernehmen: `_max_iterations`, `_max_tool_calls`, `_time_budget_seconds`, `_loop_detection_threshold`
- [ ] Stub-Methoden anlegen (werden in S1-06 bis S1-10 implementiert):
  - `async def run(...) -> str`
  - `def _build_initial_messages(...) -> list[dict]`
  - `async def _execute_tool_calls(...) -> list[ToolResult]`
  - `def _detect_tool_loop(...) -> bool`
  - `def _compact_messages(...) -> list[dict]`
  - `def _apply_evidence_gates(...) -> str` (Stub — wird in Sprint 2 Phase C befüllt)
  - `def _shape_final_response(...) -> str` (Stub — wird in Sprint 2 Phase C befüllt)
- [ ] Lifecycle-Event Helper: `_emit_lifecycle()` — wrapper um bestehende Event-Emission
- [ ] Referenzen auf bestehende Infrastruktur:
  - Nutzt `ToolExecutionManager._run_tool_with_policy()` für Tool-Ausführung
  - Nutzt `ToolRegistry.build_function_calling_tools()` für OpenAI-Format Tool-Definitionen
  - Nutzt `ContextReducer.reduce()` für Token-Budget
  - Nutzt `ToolArgValidator` für Safety-Validierung

**Akzeptanz:**
- `AgentRunner` ist instanziierbar mit allen Dependencies
- Stub-Methoden werfen `NotImplementedError` (markiert als TODO)
- Keine Änderung an bestehenden Dateien
- Import-Graph: `agent_runner.py` importiert nur aus bestehenden Modulen + `agent_runner_types.py`

**Referenz:** AgentRunnerRefactoring.md → Phase A4

---

### S1-06 — AgentRunner: Pre-Loop Setup (6 SP)

**Datei:** `backend/app/agent_runner.py` (ÄNDERN)

**Aufgaben:**
- [ ] `run()` Methode: Pre-Loop-Block implementieren (Migration aus `HeadAgent.run()` Zeilen 566–750):
  1. **Run-Lock / Concurrency Guard** — Semantisch gleich wie `HeadAgent._run_lock` + `_active_run_count`
  2. **Lifecycle Event** — `run_started` emittieren
  3. **Guardrail Validation** — Aufruf bestehender Validation-Logik (Prompt-Injection observe-only, Tool-Policy)
  4. **MCP Init** — `_ensure_mcp_tools_registered()` aufrufen (delegiert an bestehende McpBridge)
  5. **Tool Policy Resolution** — `_resolve_effective_allowed_tools()` (bestehende Logik)
  6. **Toolchain Check** — `tools.check_toolchain()` (bestehend)
  7. **Memory Setup** — `memory.add(session_id, "user", user_message)` + `repair_orphaned_tool_calls()`
  8. **Context Reduction** — `context_reducer.reduce()` mit **einem** Budget (nicht 3-fach wie bisher)
  9. **Ambiguity Detection** — Early Return wenn Rückfrage nötig

- [ ] `_build_initial_messages()` implementieren:
  - System Message: Unified Prompt + reduzierter Context
  - Conversation History aus MemoryStore (role/content Paare)
  - Aktuelle User Message als letztes

- [ ] `_build_tool_definitions()` implementieren:
  - `tool_registry.build_function_calling_tools(allowed_tools)` aufrufen
  - Ergebnis im OpenAI-Format zurückgeben

**Wichtige Entscheidungen:**
- Die Guard-Methoden (`_validate_guardrails`, `_validate_tool_policy`, `_resolve_effective_allowed_tools`) werden **aus HeadAgent extrahiert** als statische oder standalone Funktionen, die sowohl vom alten als auch neuen Pfad nutzbar sind. Alternative: AgentRunner erhält Referenz auf HeadAgent für diese Methoden (zu klären beim Implementieren).
- Context-Reduction: **Ein** Budget (`runner_context_budget`), nicht 3 Splits wie bisher.

**Akzeptanz:**
- Pre-Loop Setup führt alle 9 Schritte korrekt aus
- Ambiguity-Detection-Early-Return funktioniert
- `_build_initial_messages()` erzeugt korrektes OpenAI-Messages-Format
- Bestehende Guards werden 1:1 aufgerufen (keine Logik-Änderung)

**Referenz:** AgentRunnerRefactoring.md → Phase B1 (PRE-LOOP + BUILD MESSAGES + BUILD TOOLS)

---

### S1-07 — AgentRunner: Continuous Loop Kern (8 SP)

**Datei:** `backend/app/agent_runner.py` (ÄNDERN)

**Aufgaben:**
- [ ] Continuous `while`-Loop in `run()` implementieren:
  ```
  while not loop_state.budget_exhausted:
      1. Safety Checks (max_iterations, time_budget, steer_interrupt)
      2. LLM Call: stream_chat_with_tools()
      3. Switch auf finish_reason:
         - "stop" → final_text = text, BREAK
         - "tool_calls" → execute tools, append to messages, CONTINUE
         - "length" → compact messages, CONTINUE
      4. Budget-Exhaustion-Fallback: letzter Call OHNE Tools
  ```
- [ ] `finish_reason == "stop"` Handling:
  - Text sammeln → `final_text`
  - Loop beenden
- [ ] `finish_reason == "tool_calls"` Handling:
  - Assistant-Message mit `tool_calls` zur History appenden (OpenAI-Format)
  - `_execute_tool_calls()` aufrufen (Ticket S1-08)
  - Tool-Results als `{"role": "tool", "tool_call_id": "...", "content": "..."}` zur History appenden
  - Loop-State aktualisieren (`total_tool_calls`, `tool_call_history`)
  - Budget-Check: wenn `total_tool_calls > max_tool_calls` → `[SYSTEM]`-Nachricht injecten, `tool_definitions = None`, CONTINUE
  - Loop-Detection-Check: wenn Schleife erkannt → `[SYSTEM]`-Hinweis injecten, CONTINUE
  - CONTINUE → nächster LLM-Call
- [ ] `finish_reason == "length"` Handling:
  - `_compact_messages()` aufrufen (Ticket S1-10)
  - CONTINUE
- [ ] Budget-Exhaustion-Fallback:
  - Wenn Loop mit `budget_exhausted=True` endet und kein `final_text`:
  - Einen letzten LLM-Call OHNE Tools senden mit `[SYSTEM] Please provide your final answer...`
- [ ] Post-Loop:
  - Evidence Gates aufrufen (Stub in Sprint 1, echte Migration in Sprint 2)
  - Reply Shaping aufrufen (Stub in Sprint 1)
  - Optional: Reflection (Stub in Sprint 1)
  - `send_event({"type": "final", "message": final_text})` senden
  - `memory.add(session_id, "assistant", final_text)` speichern
- [ ] Lifecycle Events emittieren:
  - `loop_iteration_started` bei jeder Iteration
  - `loop_completed` am Ende mit Loop-Statistiken

**Akzeptanz (Kernkriterien):**
- Einfache Frage (0 Tools): 1 LLM-Call → direkte Antwort → F1 erfüllt
- File-Read Task: LLM → tool_call(read_file) → Tool-Result → LLM antwortet → F2 erfüllt
- Budget Exhaustion: Nach max_tool_calls → Forced Answer → F6 erfüllt
- Time Budget: Nach max_seconds → Loop beendet → F7 erfüllt
- Steer Interrupt: Callback returns True → Loop stoppt → F8 erfüllt
- Unbekannter finish_reason → Loop bricht sicher ab (kein Hang)

**Referenz:** AgentRunnerRefactoring.md → Phase B1 (CONTINUOUS LOOP + POST-LOOP)

**Risiko:** Dies ist das **Herzstück** des gesamten Refactorings. Präzise Implementierung und gründliches Testen sind kritisch.

---

### S1-08 — AgentRunner: `_execute_tool_calls()` (6 SP)

**Datei:** `backend/app/agent_runner.py` (ÄNDERN)

**Aufgaben:**
- [ ] `_execute_tool_calls()` implementieren:
  ```python
  async def _execute_tool_calls(
      self,
      tool_calls: list[ToolCall],
      effective_allowed_tools: set[str],
      send_event: SendEvent,
      session_id: str,
      request_id: str,
  ) -> list[ToolResult]
  ```
- [ ] Pro Tool-Call:
  1. **Tool-Name normalisieren** — bestehende Normalisierungs-Logik aus HeadAgent
  2. **Policy-Check** — `normalized_name in effective_allowed_tools`? Wenn nein → `ToolResult(is_error=True, content="Tool not allowed")`
  3. **Safety-Check** — `ToolArgValidator` für Command-Safety (COMMAND_SAFETY_PATTERNS). Wenn blockiert → `ToolResult(is_error=True, content="Command blocked by safety policy")`
  4. **Status Event** — `send_event({"type": "tool_start", "tool": name, "tool_call_id": id})`
  5. **Tool ausführen** — via bestehende `_run_tool_with_policy()` oder direkt über `ToolExecutionManager`
  6. **Result Event** — `send_event({"type": "tool_end", "tool": name, "duration_ms": ms, "is_error": bool})`
  7. **ToolResult** erstellen und zurückgeben

- [ ] Bestehende Tool-Infrastruktur wiederverwenden:
  - `ToolRegistry` für Tool-Lookup und Dispatch
  - `ToolExecutionManager` für Timeout, Retry, Gatekeeper
  - `ToolArgValidator` für Argument-Validierung und Command-Safety
  - MCP-Tools über `McpBridge` (gleicher Dispatch-Pfad)

- [ ] Tool-Result Sanitization:
  - Maximale Zeichenlänge (`runner_tool_result_max_chars`) — truncate wenn nötig
  - Bestehende Redaction-Logik für sensible Daten beibehalten

**Akzeptanz:**
- Erlaubte Tools werden korrekt ausgeführt
- Nicht-erlaubte Tools geben Fehlermeldung zurück (kein Crash)
- Command-Safety blockiert gefährliche Befehle (z.B. `rm -rf /`)
- MCP-Tools werden korrekt dispatched
- Tool-Events (start/end) werden an Client gesendet
- Bestehende Security-Tests (`test_tools_command_security.py`, `test_tools_path_traversal.py`) bleiben grün

**Referenz:** AgentRunnerRefactoring.md → Phase B2

---

### S1-09 — Loop Detection (3 Detektoren) (3 SP)

**Datei:** `backend/app/agent_runner.py` (ÄNDERN)

**Aufgaben:**
- [ ] `_detect_tool_loop()` implementieren mit 3 Detektoren:

  1. **Identical Repeat** — Gleiche Tool-Call-Signatur (Name + Args) X mal hintereinander
     ```
     Beispiel: read_file("a.py") → read_file("a.py") → read_file("a.py") → LOOP
     Threshold: runner_loop_detection_threshold (default 3)
     ```

  2. **Ping-Pong** — Alternierung zwischen 2 verschiedenen Tool-Calls
     ```
     Beispiel: read_file("a") → write_file("b") → read_file("a") → write_file("b") → LOOP
     Erkennung: letzte 4 Calls bilden A-B-A-B Pattern mit A≠B
     ```

  3. **No-Progress** (optional, P1) — Gleicher Tool-Call mit identischem Result
     ```
     Beispiel: web_search("query") → gleiches Result → web_search("query") → gleiches Result
     Erkennung: Call-Signature + Result-Hash für letzte N Iterationen vergleichen
     ```

- [ ] Tool-Call-Signatur-Hashing:
  ```python
  sig = tuple((tc.name, json.dumps(tc.arguments, sort_keys=True)) for tc in tool_calls)
  ```
- [ ] Signatur-History in `LoopState.tool_call_history` speichern
- [ ] Wenn Loop erkannt: `[SYSTEM]`-Nachricht wird von Loop-Kern (S1-07) injected

**Akzeptanz:**
- Identical Repeat: 3x gleicher Call → erkannt → F5 erfüllt
- Ping-Pong: A→B→A→B → erkannt
- Keine False Positives bei legitimem Re-Read (z.B. read_file mit unterschiedlichen Pfaden)
- Deaktivierbar via `runner_loop_detection_enabled = False`

**Referenz:** AgentRunnerRefactoring.md → Phase B3

---

### S1-10 — Message Compaction (3 SP)

**Datei:** `backend/app/agent_runner.py` (ÄNDERN)

**Aufgaben:**
- [ ] `_compact_messages()` implementieren:
  ```python
  def _compact_messages(self, messages: list[dict]) -> list[dict]
  ```
- [ ] Compaction-Strategie:
  1. System Message → **IMMER behalten** (Index 0)
  2. Letzte N Messages → **IMMER behalten** (`runner_compaction_tail_keep`, default 4)
  3. Ältere Tool-Results → kürzen auf `content[:200] + "...(truncated)..." + content[-100:]`
  4. Ältere Assistant-Messages → kürzen auf `content[:200] + "..."`
  5. User-Messages → unverändert lassen

- [ ] Compaction nur wenn `runner_compaction_enabled = True`
- [ ] Compaction nur ausführen wenn `len(messages) > runner_compaction_tail_keep + 2` (min. etwas zum Kürzen da)

**Akzeptanz:**
- Kurze Conversations (<5 Messages): keine Veränderung
- Lange Conversations: ältere Tool-Results werden gekürzt
- System-Message bleibt immer vollständig
- Letzte 4 Messages bleiben vollständig
- `finish_reason == "length"` → Compaction → Loop geht weiter → F9 erfüllt

**Referenz:** AgentRunnerRefactoring.md → Phase B4

---

### S1-11 — Feature-Flag Router in `HeadAgent.run()` (4 SP)

**Dateien:** `backend/app/agent.py` (ÄNDERN), `backend/app/config.py` (bestätigen)

**Aufgaben:**
- [ ] `HeadAgent.__init__()` erweitern:
  - Wenn `settings.use_continuous_loop == True`:
    - `AgentRunner` instanziieren mit allen Dependencies
    - Unified System Prompt über `build_unified_system_prompt()` generieren
  - `self._agent_runner: AgentRunner | None` Attribut hinzufügen

- [ ] `HeadAgent.run()` als Router umbauen:
  ```python
  async def run(self, user_message, send_event, session_id, request_id, **kwargs):
      if settings.use_continuous_loop and self._agent_runner is not None:
          return await self._agent_runner.run(...)
      else:
          return await self._run_legacy(...)
  ```
- [ ] Bestehenden `run()` Code in `_run_legacy()` umbenenen (reine Umbenennung, keine Logik-Änderung)
- [ ] `configure_runtime()` erweitern: wenn `_agent_runner` existiert, auch dessen LlmClient aktualisieren

**Akzeptanz:**
- `USE_CONTINUOUS_LOOP=false` (Default) → exakt das bestehende Verhalten, keine Regression
- `USE_CONTINUOUS_LOOP=true` → AgentRunner wird verwendet
- Rollback: Env-Variable auf `false` → sofort alter Code aktiv → F14 erfüllt
- Alle bestehenden Tests grün (laufen mit `USE_CONTINUOUS_LOOP=false`)
- `configure_runtime()` funktioniert für beide Pfade

**Referenz:** AgentRunnerRefactoring.md → Phase D1, D2, D3

---

### S1-12 — Unit Tests: Datentypen + LlmClient (4 SP)

**Dateien:** `backend/tests/test_agent_runner_types.py` (NEU), `backend/tests/test_llm_client_streaming.py` (NEU)

**Aufgaben:**

**test_agent_runner_types.py:**
- [ ] ToolCall Instantiation + Immutability (frozen)
- [ ] StreamResult mit tool_calls und ohne (text-only)
- [ ] StreamResult mit finish_reason Varianten
- [ ] ToolResult mit is_error=True/False
- [ ] LoopState Tracking (iteration increment, budget_exhausted Flag)

**test_llm_client_streaming.py:**
- [ ] Mock SSE Server für `stream_chat_with_tools()`:
  - Text-only Response (finish_reason=stop)
  - Tool-Call Response (finish_reason=tool_calls)
  - Mixed: Text + Tool-Calls
  - Multi-Tool-Call Response (2+ tool_calls in einem Response)
  - Fragmentierte Tool-Call-Chunks (Arguments über mehrere Chunks verteilt)
  - JSON Parse Error in Tool-Arguments → `{"_raw": "..."}`
  - `finish_reason=length` (Context Overflow)
  - `on_text_chunk` Callback wird korrekt aufgerufen
  - Usage-Extraktion aus Stream
- [ ] Non-Streaming Fallback (Ollama) Test

**Akzeptanz:**
- Mindestens 15 Unit Tests
- 100% Line-Coverage für `agent_runner_types.py`
- Kernpfade in `stream_chat_with_tools()` abgedeckt
- Tests sind schnell (kein realer API-Call, alles gemockt)

---

### S1-13 — Integration Tests: AgentRunner End-to-End (6 SP)

**Datei:** `backend/tests/test_agent_runner_integration.py` (NEU)

**Aufgaben:**
- [ ] Test-Fixture: AgentRunner mit Mock-LlmClient, Mock-Tools, In-Memory-MemoryStore
- [ ] **Test: Simple Question (0 Tools)** — LLM antwortet direkt, 1 Call, kein Tool
- [ ] **Test: Single Tool Call** — LLM → read_file → LLM antwortet
- [ ] **Test: Multi-Tool Sequential** — LLM → read_file → LLM → write_file → LLM antwortet
- [ ] **Test: Tool Error Recovery** — LLM → Tool-Fehler → LLM sieht Fehler → alternativer Ansatz
- [ ] **Test: Loop Detection** — Gleicher Tool-Call 3x → Loop-Warnung → LLM antwortet
- [ ] **Test: Budget Exhaustion** — 50+ Tool-Calls → Forced Final Answer
- [ ] **Test: Time Budget** — Mock-Tool mit Verzögerung → Timeout → Loop beendet
- [ ] **Test: Steer Interrupt** — Callback returns True → Loop stoppt
- [ ] **Test: Context Overflow** — finish_reason=length → Compaction → Loop fortgesetzt
- [ ] **Test: Feature Flag Off** — USE_CONTINUOUS_LOOP=false → alter Code wird genutzt

**Akzeptanz:**
- Mindestens 10 Integration Tests
- Alle Tests bestehen mit gemockten Dependencies (kein realer LLM-Call)
- Tests validieren F1–F9, F14 aus der Akzeptanzkriterien-Tabelle
- Test-Ausführungszeit < 30 Sekunden für die gesamte Suite

---

## Definition of Done — Sprint 1

```
☐ agent_runner_types.py existiert mit ToolCall, StreamResult, ToolResult, LoopState
☐ LlmClient.stream_chat_with_tools() implementiert + Ollama-Fallback
☐ Unified System Prompt Builder implementiert
☐ AgentRunner Klasse mit vollständigem Continuous Loop
☐ _execute_tool_calls() delegiert an bestehende Tool-Infrastruktur
☐ Loop Detection mit Identical-Repeat + Ping-Pong Detektor
☐ Message Compaction bei Context Overflow
☐ Feature Flag USE_CONTINUOUS_LOOP in config.py
☐ HeadAgent.run() routet basierend auf Feature Flag
☐ HeadAgent._run_legacy() enthält unveränderten alten Code
☐ Alle bestehenden Tests grün (keine Regression)
☐ 15+ neue Unit Tests (Typen + LlmClient)
☐ 10+ neue Integration Tests (AgentRunner E2E)
☐ Code Reviews für alle PRs abgeschlossen
```

---

## Was Sprint 1 NICHT macht (→ Sprint 2)

| Thema | Warum nicht in Sprint 1? | Sprint |
|-------|--------------------------|--------|
| Evidence Gates (Implementation, All-Failed, Orchestration) | Safety-Critical, braucht eigene Ticket-Fokussierung | Sprint 2, Phase C |
| Reply Shaping | Hängt an Evidence Gates | Sprint 2, Phase C |
| Reflection Service Post-Loop | Braucht funktionierende Evidence Gates als Input | Sprint 2, Phase C |
| Guardrails 1:1-Migration (Prompt Injection, Command Safety) | Funktioniert via Stubs in Sprint 1, vollständige Migration in Sprint 2 | Sprint 2, Phase C |
| Frontend: Neue Event-UI (tool_start/end Spinner, Iteration Counter) | Backend muss zuerst stabil sein | Sprint 2, Phase D |
| Benchmark Comparison (alt vs. neu) | Braucht vollständig migrierten Runner mit Guards | Sprint 2, Phase D |
| Cleanup: PlannerAgent, ToolSelectorAgent, SynthesizerAgent entfernen | Frühestens nach 2 Wochen stabilem Flag=true | Sprint 3, Phase E |
| ContextReducer Vereinfachung (1 Budget statt 3) | Nicht-funktionale Verbesserung, nicht blockierend | Sprint 3 |

---

## Risiken Sprint 1

| # | Risiko | Mitigation |
|---|--------|------------|
| R1 | `stream_chat_with_tools()` SSE-Parsing ist komplex mit fragmentierten Tool-Calls | S1-03 hat 8 SP, ausführliche Unit Tests in S1-12 mit realen Chunk-Patterns |
| R2 | Guard-Methoden sind tief in HeadAgent verschachtelt, schwer extrahierbar | Sprint 1 nutzt Stubs für Evidence Gates; Guard-Extraction wird in Sprint 2 (Phase C) sauber gemacht |
| R3 | Unified Prompt ist schlechter als 3 spezialisierte Prompts | Feature-Flag erlaubt sofortiges Rollback; AB-Test geplant für Sprint 2 |
| R4 | Integration Tests brauchen aufwändige Mocks | Mock-Fixtures aus bestehenden Tests wiederverwenden (test_backend_e2e.py Pattern) |
| R5 | `ToolExecutionManager` Kopplung an HeadAgent | AgentRunner erhält explizite Referenz auf `ToolExecutionManager` + `ToolArgValidator` in `__init__` |

---

## Abnahme-Szenario

Am Ende von Sprint 1 muss folgendes manuell funktionieren:

1. **Server starten** mit `USE_CONTINUOUS_LOOP=false` → altes Verhalten, alle bestehenden Tests grün
2. **Server starten** mit `USE_CONTINUOUS_LOOP=true` → neuer AgentRunner aktiv
3. **Einfache Frage** ("Was ist Python?") → 1 LLM-Call, direkte Antwort, kein Tool
4. **File-Read** ("Lies die README.md") → LLM ruft `read_file` auf → antwortet mit Inhalt
5. **Multi-Step** ("Lies die package.json und sage mir die Version") → read_file → Antwort
6. **Rollback** → ENV auf `false` → nächster Request nutzt alten 3-Phase Code
