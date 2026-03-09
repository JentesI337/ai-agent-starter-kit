# Agent Runner Refactoring: 3-Phase Pipeline → Continuous Streaming Tool Loop

## Inhaltsverzeichnis

1. [Problem-Statement](#1-problem-statement)
2. [Ist-Zustand: 3-Phase Pipeline](#2-ist-zustand-3-phase-pipeline)
3. [Soll-Zustand: Continuous Streaming Tool Loop](#3-soll-zustand-continuous-streaming-tool-loop)
4. [Architektur-Vergleich](#4-architektur-vergleich)
5. [Betroffene Dateien & Abhängigkeiten](#5-betroffene-dateien--abhängigkeiten)
6. [Refactoring-Phasen](#6-refactoring-phasen)
7. [Phase A: AgentRunner Grundgerüst](#7-phase-a-agentrunner-grundgerüst)
8. [Phase B: Streaming Tool Loop](#8-phase-b-streaming-tool-loop)
9. [Phase C: Guards & Safety migrieren](#9-phase-c-guards--safety-migrieren)
10. [Phase D: Integration & Cutover](#10-phase-d-integration--cutover)
11. [Phase E: Cleanup & Deprecation](#11-phase-e-cleanup--deprecation)
12. [DOs und DON'Ts](#12-dos-und-donts)
13. [Akzeptanzkriterien](#13-akzeptanzkriterien)
14. [Risiken & Mitigationen](#14-risiken--mitigationen)
15. [Rollback-Strategie](#15-rollback-strategie)

---

## 1. Problem-Statement

### Warum das aktuelle System nicht ideal funktioniert

Der aktuelle `HeadAgent.run()` nutzt eine **3-Phase Pipeline**:

```
User Message
  → LLM Call 1: PlannerAgent (plant was zu tun ist)
  → LLM Call 2: ToolSelectorAgent (wählt Tools aus, führt sie aus)
  → LLM Call 3: SynthesizerAgent (formuliert Antwort)
```

**Kernprobleme:**

| Problem | Auswirkung |
|---|---|
| **3 separate LLM-Calls** pro Request | Hohe Latenz, hoher Token-Verbrauch, höhere Kosten |
| **Planner plant blind** | Kein Feedback von Tool-Ergebnissen → unrealistische Pläne |
| **Künstliche Phasen-Trennung** | LLM kann nicht natürlich zwischen Denken, Tools und Antworten wechseln |
| **Replan = voller Pipeline-Restart** | Teuer: neuer Plan + neue Tool-Selection + neue Synthese |
| **Tool-Ergebnisse erreichen Planner erst beim Replan** | Verschwendete Iterationen, weil Initial-Plan nie Tool-Feedback sieht |
| **Synthesis muss aus möglicherweise veralteten Plan+Tools antworten** | Kann zu inkonsistenten Antworten führen |

### Was OpenClaw anders macht (Referenzarchitektur)

OpenClaw nutzt einen **Continuous Streaming Tool Loop**:

```
User Message
  → EIN LLM Call mit allen Tools als function definitions
    → LLM streamt Response
    → tool_use Block erkannt → Tool sofort ausgeführt
    → Tool-Ergebnis als tool-Message zurück in Conversation
    → Nächster LLM-Call mit aktualisierter History
    → Wiederholt bis finish_reason != "tool_calls"
  → Finale Antwort gestreamt an User
```

Das LLM entscheidet **selbst**, wann es plant, Tools nutzt und antwortet — kein künstlicher 3-Phasen-Zwang.

---

## 2. Ist-Zustand: 3-Phase Pipeline

### Hauptklasse: `HeadAgent` (agent.py, Zeile 66)

```
HeadAgent.__init__() (Zeile 107-223)
  ├─ self.client: LlmClient
  ├─ self.memory: MemoryStore
  ├─ self.tools: AgentTooling
  ├─ self.tool_registry: ToolRegistry
  ├─ self.planner_agent: PlannerAgent
  ├─ self.synthesizer_agent: SynthesizerAgent
  ├─ self.tool_selector_agent: ToolSelectorAgent
  ├─ self._intent: IntentDetector
  ├─ self._action_parser: ActionParser
  ├─ self._reflection_service: ReflectionService
  ├─ self._tool_execution_manager: ToolExecutionManager
  ├─ self.context_reducer: ContextReducer
  ├─ self._verification: VerificationService
  ├─ self._ambiguity_detector: AmbiguityDetector
  └─ 27 weitere State Variables
```

### HeadAgent.run() Flow (Zeile 226-1302, ~1080 Zeilen)

```
run() Entry (Zeile 226)
│
├─ INIT (Zeile 226-251)
│   ├─ Set contextvars (send_event, session_id, request_id)
│   ├─ Acquire _run_lock
│   └─ emit_lifecycle("run_started")
│
├─ PHASE 1: PLANNING (Zeile 252-428)
│   ├─ Guardrail Validation (Zeile 252-269)
│   │   ├─ _validate_guardrails() → 5 checks
│   │   ├─ Prompt injection detection (observe-only)
│   │   └─ _validate_tool_policy()
│   ├─ MCP Init (Zeile 270-276) → _ensure_mcp_tools_registered()
│   ├─ Tool Policy (Zeile 277-287) → _resolve_effective_allowed_tools()
│   ├─ Toolchain Check (Zeile 288-297) → tools.check_toolchain()
│   ├─ Memory Setup (Zeile 298-313) → repair orphaned tool calls
│   ├─ Context Reduction (Zeile 323-349) → context_reducer.reduce(budget="plan")
│   ├─ Ambiguity Detection (Zeile 350-387) → EARLY RETURN möglich
│   ├─ LLM Call: PlannerAgent (Zeile 397-421) → plan_text
│   ├─ Plan Verification (Zeile 407-421)
│   └─ Direct-Answer Detection (Zeile 444-463) → skip_tool_phase?
│
├─ PHASE 2: TOOL SELECTION + EXECUTION (Zeile 429-844)
│   ├─ Replan Loop Setup (Zeile 429-443)
│   │   ├─ max_replan_iterations (default 3)
│   │   ├─ max_empty_tool_replan_attempts (default 2)
│   │   └─ max_error_tool_replan_attempts (default 2)
│   │
│   └─ FOR iteration IN range(total_replan_cycles):
│       ├─ Context Reduction (Zeile 478-495) → budget="tool"
│       ├─ LLM Call: ToolSelectorAgent (Zeile 497-511) → tool_results
│       │   ├─ complete_chat_with_tools() ODER complete_chat()
│       │   ├─ Parse tool_calls / JSON Actions
│       │   ├─ validate_actions() gegen allowed_tools
│       │   └─ ToolExecutionManager.run_tool_loop()
│       │       ├─ Budget checks (time_cap, call_cap)
│       │       ├─ Loop detection (gatekeeper)
│       │       ├─ _run_tool_with_policy() pro Tool
│       │       └─ Result transformation
│       │
│       ├─ _classify_tool_results_state() (Zeile 513)
│       │   → "usable"|"blocked"|"empty"|"error_only"|"steer_interrupted"|...
│       │
│       ├─ IF usable/blocked/steer_interrupted → BREAK
│       │
│       └─ _resolve_replan_reason() (Zeile 516)
│           ├─ IF budget exhausted → BREAK
│           └─ ELSE → Replan:
│               ├─ _build_root_cause_replan_prompt()
│               └─ PlannerAgent erneut → neuer plan_text
│
├─ PHASE 2 EXIT PATHS (Zeile 585-844)
│   ├─ Blocked → EARLY RETURN mit blocked_message
│   ├─ Steer Interrupted → EARLY RETURN mit interrupted_message
│   └─ Web Research Unavailable → EARLY RETURN mit fallback
│
├─ PHASE 3: SYNTHESIS (Zeile 845-1227)
│   ├─ Tool Result Context Guard (Zeile 760-790)
│   ├─ Final Context Reduction (Zeile 791-812) → budget="final"
│   ├─ Task Type Resolution (Zeile 813-827) → synthesis_task_type
│   ├─ LLM Call: SynthesizerAgent (Zeile 836-851) → STREAMING final_text
│   ├─ Reflection Loop (Zeile 852-901) → optional re-synthesis
│   ├─ Evidence Gates (Zeile 1089-1207)
│   │   ├─ Implementation Evidence Gate
│   │   ├─ All-Tools-Failed Gate
│   │   ├─ Orchestration Evidence Gate
│   │   └─ Reply Shaping
│   └─ Final Response → send_event({"type": "final"})
│
└─ FINALLY (Zeile 1228-1302)
    ├─ Distillation hook
    ├─ Memory persistence
    └─ Token reset
```

### Betroffene Sub-Agents & Services

| Komponente | Datei | Wird bei Refactoring... |
|---|---|---|
| `PlannerAgent` | agents/planner_agent.py | **ENTFERNT** (Planung im Haupt-Loop) |
| `ToolSelectorAgent` | agents/tool_selector_agent.py | **ENTFERNT** (Tool-Selection im Haupt-Loop) |
| `SynthesizerAgent` | agents/synthesizer_agent.py | **ENTFERNT** (Synthese im Haupt-Loop) |
| `PlannerStepExecutor` | orchestrator/step_executors.py | **ENTFERNT** |
| `ToolStepExecutor` | orchestrator/step_executors.py | **ENTFERNT** |
| `SynthesizeStepExecutor` | orchestrator/step_executors.py | **ENTFERNT** |
| `ToolExecutionManager` | services/tool_execution_manager.py | **BEHALTEN** — run_tool_loop() wird weiter genutzt |
| `ActionParser` | agents/ oder services/ | **ANGEPASST** — parsed jetzt OpenAI tool_calls Format |
| `LlmClient` | llm_client.py | **ERWEITERT** — neues `stream_with_tools()` |
| `ContextReducer` | services/ | **VEREINFACHT** — nur noch 1 Budget statt 3 |
| `ReflectionService` | services/ | **BEHALTEN** — optional als Post-Loop Check |
| `VerificationService` | services/ | **VEREINFACHT** — kein Plan mehr zu verifizieren |
| `ToolRegistry` | services/tool_registry.py | **UNVERÄNDERT** |
| `AgentTooling` | tools.py | **UNVERÄNDERT** |
| `MemoryStore` | memory.py | **UNVERÄNDERT** |

### Datenverträge die sich ändern

| Contract | Status |
|---|---|
| `PlannerInput` (contracts/schemas.py:9) | **ENTFERNT** |
| `ToolSelectorInput` (contracts/schemas.py:17) | **ENTFERNT** |
| `SynthesizerInput` (contracts/schemas.py:25) | **ENTFERNT** |
| `ToolPolicyPayload` | **UNVERÄNDERT** |
| `WsUserMessage` (models.py) | **UNVERÄNDERT** |

---

## 3. Soll-Zustand: Continuous Streaming Tool Loop

### Neuer AgentRunner Flow

```
AgentRunner.run(user_message, send_event, session_id, ...)
│
├─ PRE-LOOP: Setup & Guards (BLEIBT wie bisher)
│   ├─ Guardrail Validation
│   ├─ MCP Init
│   ├─ Tool Policy Resolution
│   ├─ Toolchain Check
│   ├─ Memory Setup
│   ├─ Context Reduction (EIN Budget, nicht 3)
│   └─ Ambiguity Detection → EARLY RETURN möglich
│
├─ BUILD MESSAGES: Conversation History
│   ├─ system_message: Unified System Prompt
│   │   (bisher 3 separate Prompts: plan_prompt, tool_selector_prompt, final_prompt)
│   ├─ Conversation History aus MemoryStore
│   └─ user_message als letztes
│
├─ BUILD TOOLS: Function Definitions
│   ├─ tool_registry.build_function_calling_tools(allowed_tools)
│   └─ Alle erlaubten Tools als OpenAI-Format tool definitions
│
├─ CONTINUOUS LOOP:
│   │
│   │  ┌──────────────────────────────────────────────┐
│   │  │  while not done:                             │
│   │  │                                              │
│   │  │  1. LLM Call mit Streaming                   │
│   │  │     POST /chat/completions {                 │
│   │  │       messages: conversation_history,        │
│   │  │       tools: tool_definitions,               │
│   │  │       stream: true                           │
│   │  │     }                                        │
│   │  │                                              │
│   │  │  2. Stream Response:                         │
│   │  │     ├─ Text Chunks → send_event() an Client  │
│   │  │     └─ tool_calls → sammeln                  │
│   │  │                                              │
│   │  │  3. IF finish_reason == "tool_calls":        │
│   │  │     ├─ Parse tool_calls Array                │
│   │  │     ├─ Validate & Safety Check               │
│   │  │     ├─ Execute tools (parallel wenn safe)    │
│   │  │     ├─ Append assistant msg + tool results   │
│   │  │     │  zur conversation_history              │
│   │  │     ├─ Loop Detection Check                  │
│   │  │     ├─ Budget Check (time, calls)            │
│   │  │     └─ CONTINUE loop                         │
│   │  │                                              │
│   │  │  4. IF finish_reason == "stop":              │
│   │  │     ├─ final_text = gesammelte Text Chunks   │
│   │  │     └─ BREAK loop → done = True              │
│   │  │                                              │
│   │  └──────────────────────────────────────────────┘
│   │
│   └─ Loop Exit Conditions:
│       ├─ finish_reason == "stop" (LLM fertig)
│       ├─ max_tool_iterations erreicht (Safety)
│       ├─ time_budget überschritten (Safety)
│       ├─ Loop Detection triggered (Safety)
│       └─ Steer Interrupt (neuer User-Message)
│
├─ POST-LOOP: Guards & Finalization
│   ├─ Evidence Gates (Implementation, Orchestration, All-Failed)
│   ├─ Reply Shaping
│   ├─ Reflection (optional, als Post-Check)
│   └─ Final Response → send_event({"type": "final"})
│
└─ FINALLY: Cleanup
    ├─ Memory persistence
    ├─ Distillation hook
    └─ Token reset
```

### Neue Klasse: `AgentRunner`

```python
class AgentRunner:
    """Continuous streaming tool loop — ersetzt HeadAgent.run()."""

    def __init__(
        self,
        client: LlmClient,
        memory: MemoryStore,
        tools: AgentTooling,
        tool_registry: ToolRegistry,
        context_reducer: ContextReducer,
        system_prompt: str,
        # ... Guards & Services
    ):
        pass

    async def run(
        self,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None = None,
        tool_policy: ToolPolicyDict | None = None,
        should_steer_interrupt: Callable[[], bool] | None = None,
    ) -> str:
        """Hauptmethode — ersetzt HeadAgent.run()."""
        pass
```

### Neue LlmClient Methode: `stream_chat_with_tools()`

```python
async def stream_chat_with_tools(
    self,
    *,
    messages: list[dict],        # Vollständige Conversation History
    tools: list[dict],           # OpenAI-Format Tool Definitions
    model: str | None = None,
    temperature: float | None = None,
    on_text_chunk: Callable[[str], Awaitable[None]] | None = None,
) -> StreamResult:
    """
    Streamt LLM-Antwort und gibt strukturiertes Ergebnis zurück.

    Returns StreamResult:
        - text: str (gesammelter Text)
        - tool_calls: list[ToolCall] (geparste tool_calls, leer wenn keine)
        - finish_reason: str ("stop" | "tool_calls" | "length")
        - usage: dict (token counts)
    """
    pass
```

### Conversation History Format

```python
# Messages-Array das an LLM geht:
messages = [
    {"role": "system", "content": unified_system_prompt},
    # ... History aus MemoryStore ...
    {"role": "user", "content": "Erstelle eine REST API für User-Management"},

    # --- LOOP ITERATION 1 ---
    {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_1", "type": "function", "function": {
            "name": "read_file", "arguments": '{"path": "src/main.py"}'
        }}
    ]},
    {"role": "tool", "tool_call_id": "call_1", "content": "# existing main.py content..."},

    # --- LOOP ITERATION 2 ---
    {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_2", "type": "function", "function": {
            "name": "write_file", "arguments": '{"path": "src/users.py", "content": "..."}'
        }}
    ]},
    {"role": "tool", "tool_call_id": "call_2", "content": "File written successfully."},

    # --- LOOP ITERATION 3: Finale Antwort ---
    # LLM antwortet mit Text, keine tool_calls → finish_reason="stop"
]
```

---

## 4. Architektur-Vergleich

### LLM-Calls pro Request

| Szenario | Alt (3-Phase) | Neu (Continuous) |
|---|---|---|
| Einfache Frage (kein Tool) | 3 Calls: Plan + ToolSelect(skip) + Synthesize | 1 Call: LLM antwortet direkt |
| 1 Tool benötigt | 3 Calls: Plan + ToolSelect+Execute + Synthesize | 2 Calls: LLM→Tool→LLM(Antwort) |
| 3 Tools sequentiell | 3 Calls + ggf. Replan | 4 Calls: LLM→T1→LLM→T2→LLM→T3→LLM(Antwort) |
| Fehler + Retry | 3 + 3 (Replan) = 6 Calls | 2-3 Calls: LLM sieht Fehler, passt sofort an |

### Token-Verbrauch

| Phase | Alt | Neu |
|---|---|---|
| System Prompt | 3x geladen (plan, tool, synth) | 1x geladen (unified) |
| User Message | 3x gesendet | 1x + danach in History |
| Context | 3x Budget-berechnet & gesendet | 1x berechnet, in History |
| Tool Results | 1x als Text-Blob an Synthesizer | Natürlich in Conversation |

### Streaming-Verhalten

| Aspekt | Alt | Neu |
|---|---|---|
| Erste Tokens an User | Erst nach Phase 1+2 abgeschlossen, in Phase 3 | Sofort wenn LLM streamt (auch zwischen Tools) |
| Zwischen-Status | Nur "status" Events ("Analyzing...") | Echter Text-Stream + Tool-Status |
| Tool-Feedback | User sieht nur finales Ergebnis | User kann Tool-Ausführung live sehen |

---

## 5. Betroffene Dateien & Abhängigkeiten

### Dateien die NEU erstellt werden

```
backend/app/
  agent_runner.py              ← NEU: AgentRunner Klasse
  agent_runner_types.py        ← NEU: Datentypen (StreamResult, ToolCall, LoopState)
```

### Dateien die GEÄNDERT werden

```
backend/app/
  llm_client.py                ← ERWEITERT: stream_chat_with_tools()
  agent.py                     ← ANGEPASST: HeadAgent.run() delegiert an AgentRunner
  ws_handler.py                ← MINOR: Send-Event Format ggf. neue Event-Types
  run_endpoints.py             ← MINOR: Orchestrator-Call bleibt gleich
  config.py                    ← MINOR: Neue Settings für Loop-Limits

backend/app/contracts/
  schemas.py                   ← VEREINFACHT: PlannerInput/ToolSelectorInput/SynthesizerInput → RunInput

backend/app/orchestrator/
  step_executors.py            ← DEPRECATED: 3 Executors → 1 RunExecutor

backend/app/services/
  tool_execution_manager.py    ← ANGEPASST: run_tool_loop() Signatur vereinfacht
```

### Dateien die NICHT geändert werden

```
backend/app/
  tools.py                     ← AgentTooling bleibt
  tool_catalog.py              ← Tool-Registry bleibt
  tool_policy.py               ← Policy bleibt
  memory.py                    ← MemoryStore bleibt
  models.py                    ← WebSocket Models bleiben
  control_models.py            ← Control Models bleiben
  mcp_types.py                 ← MCP Types bleiben
  url_validator.py             ← URL Validation bleibt
  errors.py                    ← Error Types bleiben

backend/app/services/
  tool_registry.py             ← ToolRegistry bleibt
  mcp_bridge.py                ← MCP Bridge bleibt
```

---

## 6. Refactoring-Phasen

### Übersicht

```
Phase A: AgentRunner Grundgerüst          ━━━━━━━━━━━
Phase B: Streaming Tool Loop              ━━━━━━━━━━━━━━━
Phase C: Guards & Safety migrieren        ━━━━━━━━━
Phase D: Integration & Cutover            ━━━━━━━━━━━
Phase E: Cleanup & Deprecation            ━━━━━━━
```

**WICHTIG:** Bis Phase D existieren BEIDE Pfade (alt + neu) parallel. Feature-Flag `USE_CONTINUOUS_LOOP=true|false` steuert, welcher Pfad aktiv ist. Kein Big-Bang Cutover.

---

## 7. Phase A: AgentRunner Grundgerüst

### A1: StreamResult und ToolCall Datentypen

Erstelle `agent_runner_types.py`:

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolCall:
    """Einzelner Tool-Call aus LLM Response."""
    id: str               # "call_abc123"
    name: str             # "read_file"
    arguments: dict       # {"path": "src/main.py"}


@dataclass(frozen=True)
class StreamResult:
    """Ergebnis eines gestreamten LLM-Calls."""
    text: str                            # Gesammelter Text (kann leer sein wenn tool_calls)
    tool_calls: list[ToolCall]           # Geparste tool_calls (kann leer sein wenn text)
    finish_reason: str                   # "stop" | "tool_calls" | "length"
    usage: dict = field(default_factory=dict)  # Token counts


@dataclass
class ToolResult:
    """Ergebnis einer Tool-Ausführung."""
    tool_call_id: str     # Referenz auf ToolCall.id
    tool_name: str        # "read_file"
    content: str          # Tool-Output
    is_error: bool        # True wenn Fehler
    duration_ms: int = 0  # Ausführungszeit


@dataclass
class LoopState:
    """Tracking-State für den Continuous Loop."""
    iteration: int = 0
    total_tool_calls: int = 0
    total_tokens_used: int = 0
    elapsed_seconds: float = 0.0
    tool_call_history: list[dict] = field(default_factory=list)
    loop_detected: bool = False
    budget_exhausted: bool = False
    steer_interrupted: bool = False
```

### A2: LlmClient erweitern

Neue Methode in `llm_client.py`:

```python
async def stream_chat_with_tools(
    self,
    *,
    messages: list[dict],
    tools: list[dict] | None = None,
    model: str | None = None,
    temperature: float | None = None,
    on_text_chunk: Callable[[str], Awaitable[None]] | None = None,
) -> StreamResult:
    """
    Streamt LLM-Response und sammelt Text + tool_calls.

    WICHTIG: Diese Methode ersetzt die Kombination aus:
      - complete_chat() (Phase 1 Planning)
      - complete_chat_with_tools() (Phase 2 Tool Selection)
      - stream_chat_completion() (Phase 3 Synthesis)

    Unterschied zu den alten Methoden:
      - Akzeptiert vollständige messages-Array (nicht nur system+user)
      - Streamt UND sammelt tool_calls gleichzeitig
      - Gibt strukturiertes StreamResult zurück
    """
```

**Implementierungsdetails:**

```python
async def stream_chat_with_tools(self, *, messages, tools=None, model=None,
                                  temperature=None, on_text_chunk=None):
    effective_model = model or self.model
    payload = {
        "model": effective_model,
        "messages": messages,
        "stream": True,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if temperature is not None:
        payload["temperature"] = temperature

    collected_text = []
    collected_tool_calls: dict[int, dict] = {}  # index → {id, name, arguments_str}
    finish_reason = "stop"
    usage = {}

    # Streaming HTTP Request
    async with self._session.post(
        f"{self.base_url}/chat/completions",
        json=payload,
        headers=self._headers(),
    ) as resp:
        resp.raise_for_status()
        async for line in resp.content:
            line = line.decode("utf-8").strip()
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break

            chunk = json.loads(data_str)
            delta = chunk["choices"][0].get("delta", {})
            chunk_finish = chunk["choices"][0].get("finish_reason")

            # Text-Content sammeln + streamen
            if "content" in delta and delta["content"]:
                text_piece = delta["content"]
                collected_text.append(text_piece)
                if on_text_chunk:
                    await on_text_chunk(text_piece)

            # Tool-Calls sammeln (kommen in Chunks)
            if "tool_calls" in delta:
                for tc in delta["tool_calls"]:
                    idx = tc["index"]
                    if idx not in collected_tool_calls:
                        collected_tool_calls[idx] = {
                            "id": tc.get("id", ""),
                            "name": tc.get("function", {}).get("name", ""),
                            "arguments_str": "",
                        }
                    if tc.get("function", {}).get("name"):
                        collected_tool_calls[idx]["name"] = tc["function"]["name"]
                    if tc.get("id"):
                        collected_tool_calls[idx]["id"] = tc["id"]
                    if tc.get("function", {}).get("arguments"):
                        collected_tool_calls[idx]["arguments_str"] += tc["function"]["arguments"]

            if chunk_finish:
                finish_reason = chunk_finish

            if "usage" in chunk:
                usage = chunk["usage"]

    # Tool-Calls parsen
    parsed_tool_calls = []
    for idx in sorted(collected_tool_calls.keys()):
        tc = collected_tool_calls[idx]
        try:
            args = json.loads(tc["arguments_str"]) if tc["arguments_str"] else {}
        except json.JSONDecodeError:
            args = {"_raw": tc["arguments_str"]}
        parsed_tool_calls.append(ToolCall(
            id=tc["id"],
            name=tc["name"],
            arguments=args,
        ))

    return StreamResult(
        text="".join(collected_text),
        tool_calls=parsed_tool_calls,
        finish_reason=finish_reason,
        usage=usage,
    )
```

### A3: Unified System Prompt

Bisher gibt es 3 separate Prompts:
- `prompt_profile.plan_prompt` (für PlannerAgent)
- `prompt_profile.tool_selector_prompt` (für ToolSelectorAgent)
- `prompt_profile.final_prompt` (für SynthesizerAgent)

Diese werden zu EINEM `unified_prompt` zusammengeführt:

```python
def build_unified_system_prompt(
    role: str,
    plan_prompt: str,
    tool_hints: str,
    final_instructions: str,
    guardrails: str,
) -> str:
    """
    Zusammenführung der 3 Phase-Prompts zu einem Unified Prompt.

    Struktur:
    1. Rolle & Identität (aus plan_prompt)
    2. Arbeitsweise: "Du darfst Tools nutzen um Aufgaben zu erledigen.
       Denke Schritt für Schritt. Nutze Tools wenn nötig.
       Antworte direkt wenn du die Antwort bereits kennst."
    3. Tool-Hinweise (aus tool_selector_prompt)
    4. Antwort-Format (aus final_prompt)
    5. Guardrails & Safety
    """
```

**WICHTIG:** Der Unified Prompt muss dem LLM explizit erlauben selbst zu entscheiden ob und welche Tools es nutzt. Kein "Du MUSST erst planen, dann Tools auswählen, dann antworten".

### A4: AgentRunner Grundstruktur

```python
class AgentRunner:
    """
    Continuous streaming tool loop.
    Ersetzt den 3-Phase run() von HeadAgent.
    """

    def __init__(
        self,
        *,
        client: LlmClient,
        memory: MemoryStore,
        tools: AgentTooling,
        tool_registry: ToolRegistry,
        context_reducer: ContextReducer,
        system_prompt: str,
        reflection_service: ReflectionService | None = None,
        settings: Settings,
    ):
        self.client = client
        self.memory = memory
        self.tools = tools
        self.tool_registry = tool_registry
        self.context_reducer = context_reducer
        self.system_prompt = system_prompt
        self._reflection_service = reflection_service
        self._settings = settings

        # Loop Limits (aus Settings)
        self._max_iterations = settings.runner_max_iterations  # default: 25
        self._max_tool_calls = settings.runner_max_tool_calls  # default: 50
        self._time_budget_seconds = settings.runner_time_budget_seconds  # default: 300
        self._loop_detection_threshold = settings.runner_loop_detection_threshold  # default: 3

    async def run(self, ...) -> str:
        # Implementierung in Phase B
        pass
```

---

## 8. Phase B: Streaming Tool Loop

### B1: Hauptloop Implementierung

```python
async def run(
    self,
    user_message: str,
    send_event: SendEvent,
    session_id: str,
    request_id: str,
    model: str | None = None,
    tool_policy: ToolPolicyDict | None = None,
    should_steer_interrupt: Callable[[], bool] | None = None,
) -> str:

    # ═══════════════════════════════════════════
    # PRE-LOOP: Setup (migriert aus Phase 1)
    # ═══════════════════════════════════════════

    # 1. Guardrails (IDENTISCH zu bisherigem Code)
    self._validate_guardrails(user_message, session_id, model)
    self._validate_tool_policy(tool_policy)

    # 2. MCP + Tool Policy (IDENTISCH)
    await self._ensure_mcp_tools_registered(send_event, request_id, session_id)
    effective_allowed_tools = self._resolve_effective_allowed_tools(tool_policy)

    # 3. Tools check (IDENTISCH)
    toolchain_ok, toolchain_details = self.tools.check_toolchain()

    # 4. Memory setup (IDENTISCH)
    self.memory.add(session_id, "user", user_message)
    self.memory.repair_orphaned_tool_calls(session_id)

    # 5. Context Reduction (VEREINFACHT: nur 1 Budget)
    memory_items = self.memory.get_items(session_id)
    reduced_context = self.context_reducer.reduce(
        budget_tokens=self._settings.runner_context_budget,
        user_message=user_message,
        memory_lines=memory_items,
        tool_outputs=[],
    )

    # 6. Ambiguity Detection (IDENTISCH)
    if self._settings.clarification_protocol_enabled:
        ambiguity = self._ambiguity_detector.assess(user_message, reduced_context.rendered)
        if ambiguity.is_ambiguous and ambiguity.confidence < threshold:
            return ambiguity.clarification_question  # EARLY RETURN

    # ═══════════════════════════════════════════
    # BUILD MESSAGES
    # ═══════════════════════════════════════════

    messages = self._build_initial_messages(
        system_prompt=self.system_prompt,
        memory_items=memory_items,
        reduced_context=reduced_context.rendered,
        user_message=user_message,
    )

    # ═══════════════════════════════════════════
    # BUILD TOOL DEFINITIONS
    # ═══════════════════════════════════════════

    tool_definitions = self.tool_registry.build_function_calling_tools(
        allowed_tools=effective_allowed_tools,
        provider="openai",
    )

    # ═══════════════════════════════════════════
    # CONTINUOUS LOOP
    # ═══════════════════════════════════════════

    loop_state = LoopState()
    start_time = time.monotonic()
    final_text = ""
    all_tool_results = []  # Für Evidence Gates

    while not loop_state.budget_exhausted:
        loop_state.iteration += 1

        # Safety: Max Iterations
        if loop_state.iteration > self._max_iterations:
            loop_state.budget_exhausted = True
            break

        # Safety: Time Budget
        loop_state.elapsed_seconds = time.monotonic() - start_time
        if loop_state.elapsed_seconds > self._time_budget_seconds:
            loop_state.budget_exhausted = True
            break

        # Safety: Steer Interrupt
        if should_steer_interrupt and should_steer_interrupt():
            loop_state.steer_interrupted = True
            break

        # ── LLM CALL MIT STREAMING ──
        emit_lifecycle("loop_iteration_started", {"iteration": loop_state.iteration})

        stream_result = await self.client.stream_chat_with_tools(
            messages=messages,
            tools=tool_definitions if not loop_state.budget_exhausted else None,
            model=model,
            on_text_chunk=lambda chunk: send_event({
                "type": "stream", "content": chunk
            }),
        )

        # ── FINISH REASON: STOP → LLM ist fertig ──
        if stream_result.finish_reason == "stop":
            final_text = stream_result.text
            break

        # ── FINISH REASON: TOOL_CALLS → Tools ausführen ──
        if stream_result.finish_reason == "tool_calls" and stream_result.tool_calls:

            # 1. Assistant Message mit tool_calls zur History
            messages.append({
                "role": "assistant",
                "content": stream_result.text or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        }
                    }
                    for tc in stream_result.tool_calls
                ],
            })

            # 2. Tools validieren & ausführen
            tool_results = await self._execute_tool_calls(
                tool_calls=stream_result.tool_calls,
                effective_allowed_tools=effective_allowed_tools,
                send_event=send_event,
                session_id=session_id,
                request_id=request_id,
            )

            # 3. Tool Results als Messages zur History
            for result in tool_results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": result.tool_call_id,
                    "content": result.content,
                })
                all_tool_results.append(result)

            # 4. Loop State aktualisieren
            loop_state.total_tool_calls += len(tool_results)

            # 5. Safety: Max tool calls
            if loop_state.total_tool_calls > self._max_tool_calls:
                loop_state.budget_exhausted = True
                # Einen letzten LLM-Call OHNE Tools machen
                messages.append({
                    "role": "user",
                    "content": "[SYSTEM] Tool call budget exhausted. "
                               "Please provide your final answer now.",
                })
                tool_definitions = None  # Keine Tools mehr
                continue

            # 6. Loop Detection
            if self._detect_tool_loop(loop_state, stream_result.tool_calls):
                loop_state.loop_detected = True
                messages.append({
                    "role": "user",
                    "content": "[SYSTEM] Loop detected — you are repeating "
                               "the same tool calls. Please try a different "
                               "approach or provide your answer.",
                })
                continue

            # CONTINUE → nächster LLM-Call mit Tool-Ergebnissen
            continue

        # ── FINISH REASON: LENGTH → Context Overflow ──
        if stream_result.finish_reason == "length":
            # Auto-Compaction: Messages kürzen
            messages = self._compact_messages(messages)
            continue

        # Unbekannter finish_reason → sicherheitshalber brechen
        break

    # ═══════════════════════════════════════════
    # POST-LOOP: Guards & Finalization
    # ═══════════════════════════════════════════

    # Budget-Exhaustion Fallback
    if loop_state.budget_exhausted and not final_text:
        # Force letzten LLM Call ohne Tools
        stream_result = await self.client.stream_chat_with_tools(
            messages=messages + [{
                "role": "user",
                "content": "[SYSTEM] Please provide your final answer based on "
                           "what you have accomplished so far.",
            }],
            tools=None,  # Keine Tools → LLM MUSS Text antworten
            model=model,
            on_text_chunk=lambda chunk: send_event({"type": "stream", "content": chunk}),
        )
        final_text = stream_result.text

    # Evidence Gates (migriert aus Phase 3)
    final_text = self._apply_evidence_gates(
        final_text=final_text,
        tool_results=all_tool_results,
        user_message=user_message,
    )

    # Reply Shaping (migriert aus Phase 3)
    final_text = self._shape_final_response(final_text, all_tool_results)

    # Optional Reflection (migriert aus Phase 3)
    if self._reflection_service and self._settings.reflection_passes > 0:
        final_text = await self._run_reflection(
            final_text, user_message, all_tool_results, model, send_event
        )

    # Final Event
    send_event({"type": "final", "message": final_text})

    # Memory Persistence
    self.memory.add(session_id, "assistant", final_text)

    return final_text
```

### B2: Tool Execution im Loop

```python
async def _execute_tool_calls(
    self,
    tool_calls: list[ToolCall],
    effective_allowed_tools: set[str],
    send_event: SendEvent,
    session_id: str,
    request_id: str,
) -> list[ToolResult]:
    """
    Führt Tool-Calls aus.
    Nutzt die BESTEHENDE _run_tool_with_policy() Infrastruktur.
    """
    results = []

    for tc in tool_calls:
        # 1. Tool Name normalisieren (bestehende Logik)
        normalized_name = self._normalize_tool_name(tc.name)

        # 2. Policy Check (bestehende Logik)
        if normalized_name not in effective_allowed_tools:
            results.append(ToolResult(
                tool_call_id=tc.id,
                tool_name=normalized_name,
                content=f"Error: Tool '{normalized_name}' is not in the allowed tools list.",
                is_error=True,
            ))
            continue

        # 3. Safety Check für Befehle (bestehende Logik)
        # COMMAND_SAFETY_PATTERNS check wenn run_command/exec
        if not self._validate_tool_safety(normalized_name, tc.arguments):
            results.append(ToolResult(
                tool_call_id=tc.id,
                tool_name=normalized_name,
                content="Error: Command blocked by safety policy.",
                is_error=True,
            ))
            continue

        # 4. Status Event an Client
        await send_event({
            "type": "tool_start",
            "tool": normalized_name,
            "tool_call_id": tc.id,
        })

        # 5. Tool ausführen (bestehende _run_tool_with_policy)
        start = time.monotonic()
        try:
            policy = self._build_execution_policy(normalized_name)
            result_text = await self._run_tool_with_policy(
                normalized_name, tc.arguments, policy
            )
            is_error = False
        except Exception as e:
            result_text = f"Error executing {normalized_name}: {e}"
            is_error = True

        duration_ms = int((time.monotonic() - start) * 1000)

        # 6. Result Event an Client
        await send_event({
            "type": "tool_end",
            "tool": normalized_name,
            "tool_call_id": tc.id,
            "duration_ms": duration_ms,
            "is_error": is_error,
        })

        results.append(ToolResult(
            tool_call_id=tc.id,
            tool_name=normalized_name,
            content=result_text,
            is_error=is_error,
            duration_ms=duration_ms,
        ))

    return results
```

### B3: Loop Detection

```python
def _detect_tool_loop(
    self,
    state: LoopState,
    tool_calls: list[ToolCall],
) -> bool:
    """
    Erkennt ob der Agent in einer Schleife steckt.

    Prüft:
    1. Identical Repeat: Gleicher Tool-Call (Name + Args) X mal hintereinander
    2. Ping-Pong: Alternierung zwischen 2 Tool-Calls
    3. No Progress: Gleicher Tool-Call mit gleichem Ergebnis
    """
    # Aktuellen Call-Signature hashen
    current_sig = tuple(
        (tc.name, json.dumps(tc.arguments, sort_keys=True))
        for tc in tool_calls
    )
    state.tool_call_history.append({"sig": current_sig, "iteration": state.iteration})

    history = state.tool_call_history
    threshold = self._loop_detection_threshold

    # 1. Identical Repeat
    if len(history) >= threshold:
        recent = [h["sig"] for h in history[-threshold:]]
        if all(s == recent[0] for s in recent):
            return True

    # 2. Ping-Pong (A→B→A→B)
    if len(history) >= 4:
        last4 = [h["sig"] for h in history[-4:]]
        if last4[0] == last4[2] and last4[1] == last4[3] and last4[0] != last4[1]:
            return True

    return False
```

### B4: Message Compaction (Context Overflow Handling)

```python
def _compact_messages(self, messages: list[dict]) -> list[dict]:
    """
    Kürzt die Messages-History wenn Context-Overflow droht.

    Strategie:
    1. System Message BLEIBT immer
    2. Letzte User Message BLEIBT immer
    3. Letzte 2 Tool-Interactions BLEIBEN
    4. Ältere Tool-Results werden zusammengefasst:
       [tool result with 5000 chars] → "[tool_name] executed successfully (result truncated)"
    5. Ältere Assistant Messages werden gekürzt
    """
    if len(messages) <= 5:
        return messages  # Nichts zu komprimieren

    system = messages[0]  # Behalten
    rest = messages[1:]

    # Letzte 4 Messages unangetastet lassen
    keep_tail = rest[-4:]
    to_compact = rest[:-4]

    compacted = []
    for msg in to_compact:
        if msg["role"] == "tool":
            # Tool-Results zusammenfassen
            content = msg["content"]
            if len(content) > 500:
                compacted.append({
                    **msg,
                    "content": content[:200] + "\n... (truncated) ...\n" + content[-100:],
                })
            else:
                compacted.append(msg)
        elif msg["role"] == "assistant" and msg.get("content"):
            # Assistant Text kürzen
            content = msg["content"]
            if len(content) > 300:
                compacted.append({
                    **msg,
                    "content": content[:200] + "...",
                })
            else:
                compacted.append(msg)
        else:
            compacted.append(msg)

    return [system] + compacted + keep_tail
```

### B5: Initial Messages Builder

```python
def _build_initial_messages(
    self,
    system_prompt: str,
    memory_items: list,
    reduced_context: str,
    user_message: str,
) -> list[dict]:
    """
    Baut die initiale Messages-Liste für den LLM-Call.

    Format:
    [
      {"role": "system", "content": unified_system_prompt + context},
      ... (History aus MemoryStore, konvertiert zu messages) ...
      {"role": "user", "content": user_message}
    ]
    """
    messages = []

    # 1. System Message mit Context
    system_content = system_prompt
    if reduced_context:
        system_content += f"\n\n## Context\n{reduced_context}"
    messages.append({"role": "system", "content": system_content})

    # 2. Conversation History aus Memory (letzte N Turns)
    for item in memory_items:
        if item.role in ("user", "assistant"):
            messages.append({"role": item.role, "content": item.content})

    # 3. Aktuelle User Message
    messages.append({"role": "user", "content": user_message})

    return messages
```

---

## 9. Phase C: Guards & Safety migrieren

### C1: Evidence Gates

Die Evidence Gates aus Phase 3 (agent.py Zeile 1089-1207) werden EXAKT übernommen, nur mit dem neuen `list[ToolResult]` statt `str` tool_results:

```python
def _apply_evidence_gates(
    self,
    final_text: str,
    tool_results: list[ToolResult],
    user_message: str,
) -> str:
    """
    Migriert aus HeadAgent Phase 3 (Zeile 1089-1207).
    Alle 4 Gates bleiben IDENTISCH in der Logik.
    """
    # Konvertiere list[ToolResult] zu String für bestehende Gate-Logik
    tool_results_str = self._tool_results_to_string(tool_results)

    synthesis_task_type = self._resolve_synthesis_task_type(
        user_message=user_message,
        tool_results=tool_results_str,
    )

    # Gate 1: Implementation Evidence
    if self._requires_implementation_evidence(
        user_message=user_message,
        synthesis_task_type=synthesis_task_type,
    ):
        if not self._has_implementation_evidence(tool_results_str):
            final_text = (
                "I was unable to complete the implementation. "
                "The required file changes or command executions did not succeed."
            )

    # Gate 2: All-Tools-Failed
    if self._all_tools_failed(tool_results_str):
        if not self._response_acknowledges_failures(final_text):
            final_text = (
                "I encountered errors with all tool executions. "
                "Please review the error details and try again."
            )

    # Gate 3: Orchestration Evidence
    if synthesis_task_type in ("orchestration", "orchestration_pending", "orchestration_failed"):
        if not self._has_orchestration_evidence(tool_results_str):
            if self._has_orchestration_attempted(tool_results_str):
                final_text = "The sub-task was started but did not complete successfully."

    return final_text
```

### C2: Command Safety (bestehend, kein Change)

Die `COMMAND_SAFETY_PATTERNS` und URL-Validation bleiben EXAKT gleich. Sie werden in `_execute_tool_calls()` aufgerufen.

### C3: Guardrails (bestehend, kein Change)

Die 5 Guardrail-Checks bleiben EXAKT gleich. Sie werden im PRE-LOOP aufgerufen.

### C4: Tool Policy (bestehend, kein Change)

`_resolve_effective_allowed_tools()` bleibt EXAKT gleich. Wird im PRE-LOOP aufgerufen.

### C5: Prompt Injection Detection (bestehend, kein Change)

Observe-only Injection Detection bleibt EXAKT gleich. Wird im PRE-LOOP aufgerufen.

---

## 10. Phase D: Integration & Cutover

### D1: Feature Flag

Neues Setting in `config.py`:

```python
# config.py
USE_CONTINUOUS_LOOP: bool = Field(
    default=False,
    description="Feature flag: True = neuer AgentRunner, False = alter HeadAgent.run()"
)
```

### D2: HeadAgent.run() als Router

```python
# agent.py - HeadAgent.run() wird zum Router:
async def run(self, user_message, send_event, session_id, request_id, **kwargs) -> str:
    if self._settings.use_continuous_loop:
        return await self._agent_runner.run(
            user_message=user_message,
            send_event=send_event,
            session_id=session_id,
            request_id=request_id,
            **kwargs,
        )
    else:
        return await self._run_legacy(
            user_message=user_message,
            send_event=send_event,
            session_id=session_id,
            request_id=request_id,
            **kwargs,
        )
```

### D3: HeadAgent.__init__() erweitern

```python
# agent.py - __init__ ergänzen:
if settings.use_continuous_loop:
    self._agent_runner = AgentRunner(
        client=self.client,
        memory=self.memory,
        tools=self.tools,
        tool_registry=self.tool_registry,
        context_reducer=self.context_reducer,
        system_prompt=build_unified_system_prompt(
            role=self.role,
            plan_prompt=self.prompt_profile.plan_prompt,
            tool_hints=self.prompt_profile.tool_selector_prompt,
            final_instructions=self.prompt_profile.final_prompt,
            guardrails=self.prompt_profile.guardrails,
        ),
        reflection_service=self._reflection_service,
        settings=settings,
    )
```

### D4: WebSocket Event Changes

Neue Event-Types die das Frontend kennen muss:

```typescript
// NEUE Events (zusätzlich zu bestehenden):
interface ToolStartEvent {
  type: "tool_start";
  tool: string;
  tool_call_id: string;
}

interface ToolEndEvent {
  type: "tool_end";
  tool: string;
  tool_call_id: string;
  duration_ms: number;
  is_error: boolean;
}

interface LoopIterationEvent {
  type: "loop_iteration";
  iteration: number;
  total_tool_calls: number;
  elapsed_seconds: number;
}

// "stream" Events kommen jetzt AUCH zwischen Tools vor, nicht nur in Phase 3:
interface StreamEvent {
  type: "stream";
  content: string;  // Text-Token vom LLM
}
```

### D5: Frontend Anpassungen

Das Frontend muss auf die neuen Events reagieren:

```
BESTEHEND (bleibt):
  - "status" Events → Status-Anzeige
  - "final" Event → Finale Antwort
  - "stream" Events → Token-Streaming
  - "agent_step" Events → Step-Anzeige

NEU:
  - "tool_start" → Spinner für Tool-Name anzeigen
  - "tool_end" → Spinner stoppen, Dauer anzeigen
  - "loop_iteration" → Iteration-Counter anzeigen
  - "stream" ZWISCHEN Tools → Text anzeigen (LLM "denkt laut nach")
```

### D6: Test-Strategie

```
1. Unit Tests:
   - stream_chat_with_tools() mit Mock-SSE-Server
   - _detect_tool_loop() mit verschiedenen Patterns
   - _compact_messages() mit großen Histories
   - _apply_evidence_gates() mit tool_results list

2. Integration Tests:
   - Simple Question (0 Tools) → 1 LLM Call, direkte Antwort
   - File Read Task → 2 Calls (LLM→read_file→LLM)
   - Multi-Tool Task → N Calls
   - Error Recovery → LLM sieht Fehler, versucht Alternative
   - Loop Detection → Loop wird erkannt und unterbrochen
   - Budget Exhaustion → Finale Antwort wird erzwungen
   - Context Overflow → Messages werden komprimiert

3. Comparison Tests:
   - Gleiche Prompts an alt (3-Phase) UND neu (Continuous)
   - Vergleiche: Latenz, Token-Verbrauch, Antwort-Qualität
   - Feature-Flag toggle Tests

4. Benchmark-Szenarien (scenarios-v4.json):
   - Bestehende Szenarien MÜSSEN mit neuem Runner bestehen
   - Neue Szenarien für Streaming-Verhalten
```

---

## 11. Phase E: Cleanup & Deprecation

### E1: Was entfernt wird (ERST nach stabilem Cutover)

```
ENTFERNEN nach Feature-Flag = true für 2+ Wochen stabil:

Dateien:
  - agents/planner_agent.py          → Nicht mehr nötig
  - agents/tool_selector_agent.py    → Nicht mehr nötig
  - agents/synthesizer_agent.py      → Nicht mehr nötig

Klassen:
  - PlannerStepExecutor              → Nicht mehr nötig
  - ToolStepExecutor                 → Nicht mehr nötig
  - SynthesizeStepExecutor           → Nicht mehr nötig

Contracts:
  - PlannerInput                     → Nicht mehr nötig
  - ToolSelectorInput                → Nicht mehr nötig
  - SynthesizerInput                 → Nicht mehr nötig

Methoden in HeadAgent:
  - _execute_planner_step()
  - _execute_tool_step()
  - _execute_synthesize_step()
  - _is_direct_answer_plan()
  - _classify_tool_results_state()
  - _resolve_replan_reason()
  - _build_root_cause_replan_prompt()
  - _step_budgets() (3-way split)
```

### E2: Was BEHALTEN wird

```
BEHALTEN (wird vom neuen Runner wiederverwendet):

Services:
  - ToolExecutionManager        → _run_tool_with_policy() wird direkt genutzt
  - ToolRegistry                → build_function_calling_tools()
  - ContextReducer              → reduce() für Initial-Context
  - ReflectionService           → Post-Loop Reflection
  - VerificationService         → Evidence Gates
  - AmbiguityDetector           → Pre-Loop Clarification

Infrastruktur:
  - LlmClient                  → stream_chat_with_tools()
  - MemoryStore                → Session History
  - AgentTooling               → Tool Implementations
  - MCP Bridge                 → MCP Tool Execution
  - ToolPolicy                 → Policy Resolution
```

---

## 12. DOs und DON'Ts

### DOs ✅

| # | DO | Warum |
|---|---|---|
| 1 | **Feature-Flag für Cutover nutzen** | Rollback muss jederzeit möglich sein. `USE_CONTINUOUS_LOOP=false` → alter Code. Kein Big-Bang. |
| 2 | **Bestehende Tool-Infrastruktur wiederverwenden** | `_run_tool_with_policy()`, `ToolRegistry`, `AgentTooling`, `MCP Bridge` — ALLES bleibt. Nur die Loop-Orchestrierung ändert sich. |
| 3 | **Evidence Gates 1:1 migrieren** | Die 4 Gates (Implementation, All-Failed, Orchestration, Reply Shaping) sind Safety-Critical. Keine Logik ändern, nur Input-Format anpassen. |
| 4 | **Loop Detection aktiv haben** | LLMs können in Endlosschleifen geraten. 3 Detektoren: Identical Repeat, Ping-Pong, No-Progress. |
| 5 | **Hard Budget Limits setzen** | `max_iterations=25`, `max_tool_calls=50`, `time_budget=300s`. IMMER. Ohne Limits kann ein Request den Server blockieren. |
| 6 | **Tool Results als Messages (nicht als String-Blob)** | Jedes Tool-Ergebnis wird als eigene `{"role": "tool", "tool_call_id": "..."}` Message an das LLM gesendet. Nicht als zusammengebastelter Text-String. |
| 7 | **Streaming ZWISCHEN Tools an Client senden** | Wenn das LLM Text vor/zwischen/nach Tool-Calls generiert, diesen sofort zum Client streamen. Das gibt dem User visuelles Feedback. |
| 8 | **Alte Tests grün halten** | Alle bestehenden Benchmark-Szenarien MÜSSEN mit dem neuen Runner bestehen. Kein Qualitätsverlust. |
| 9 | **Context Overflow graceful handeln** | Wenn `finish_reason="length"`, Messages komprimieren und weiter loopen. Nicht einfach abbrechen. |
| 10 | **Forced Final Answer bei Budget-Exhaustion** | Wenn Loop-Limit erreicht: Letzten LLM-Call OHNE Tools machen. LLM MUSS dann antworten. |
| 11 | **System Prompt klar formulieren: LLM entscheidet** | "Du darfst Tools nutzen wenn nötig. Du darfst auch direkt antworten." NICHT: "Du MUSST erst planen, dann Tools nutzen." |
| 12 | **Lifecycle Events beibehalten** | `emit_lifecycle()` Calls für Monitoring weiter nutzen. Events umbenennen zu loop_iteration_started etc. |

### DON'Ts ❌

| # | DON'T | Warum |
|---|---|---|
| 1 | **NICHT den Plan-Phase als separaten LLM-Call behalten** | Das ist genau das Problem das wir lösen. Der ganze Punkt ist: EIN Loop, KEIN separater Planner. |
| 2 | **NICHT PlannerAgent/ToolSelectorAgent/SynthesizerAgent im neuen Code verwenden** | Diese 3 Sub-Agents sind die Verkörperung des 3-Phase-Modells. Sie werden durch den einzelnen AgentRunner ersetzt. |
| 3 | **NICHT tool_results als String zusammenbauen** | Im alten Code: `tool_results = "[read_file]\ncontent\n\n[write_file]\nsuccess"`. Im neuen Code: Jedes Ergebnis ist eine separate Tool-Message mit `tool_call_id`. |
| 4 | **NICHT den Context 3x reduzieren** | Alter Code: 3 Budget-Splits (plan=25%, tool=30%, synth=45%). Neuer Code: 1 Budget für den gesamten Context. Der Loop managed Context selbst via Compaction. |
| 5 | **NICHT die Loop Detection weglassen** | "Das LLM wird schon aufhören" — NEIN. LLMs geraten regelmäßig in Loops. Explicit Detection ist Pflicht. |
| 6 | **NICHT Tools ohne Tool-Definitions an LLM senden** | IMMER die `tools` Property im API-Call setzen (außer beim Budget-Exhaustion Forced Final). Sonst kann das LLM keine Tools nutzen. |
| 7 | **NICHT beide Pfade (alt + neu) gleichzeitig für einen Request nutzen** | Feature-Flag entscheidet VOR dem Request. Nicht mitten drin switchen. |
| 8 | **NICHT die alten Agent-Dateien löschen bevor Cutover stabil** | PlannerAgent etc. bleiben im Code bis Feature-Flag mindestens 2 Wochen auf `true`. Dann erst entfernen. |
| 9 | **NICHT das Prompt-Format des Unified Prompts "kreativ" gestalten** | Keine langen Instruktionen wie "Schritt 1: Plane. Schritt 2: Überlege welche Tools du brauchst." Das LLM soll NATÜRLICH entscheiden. |
| 10 | **NICHT Tool Results an Client schicken ohne Sanitization** | Tool Results können sensible Daten enthalten (API Keys, Passwörter in Config-Files). Bestehende Redaction-Logik MUSS beibehalten werden. |
| 11 | **NICHT mehrere `[SYSTEM]` Nachrichten injecten** | Max 1 System-Injection pro Loop-Exit (Budget Exhaustion, Loop Detection). Nicht bei jeder Iteration. |
| 12 | **NICHT den alten ToolExecutionManager.run_tool_loop() ersetzen** | Die bestehende Tool-Ausführungs-Logik (Timeouts, Retries, Policy) ist ausgereift. Der neue Loop nutzt `_run_tool_with_policy()` direkt. |
| 13 | **NICHT Streaming für Non-Streaming Providers brechen** | Manche LLM Provider (Ollama lokal) unterstützen kein Streaming. `stream_chat_with_tools()` muss einen Non-Streaming Fallback haben. |
| 14 | **NICHT die WebSocket-Kompatibilität brechen** | Die bestehenden Event-Types ("status", "final", "stream", "agent_step") MÜSSEN weiter funktionieren. Neue Events kommen ZUSÄTZLICH. |

---

## 13. Akzeptanzkriterien

### Funktionale Akzeptanzkriterien

| # | Kriterium | Prüfmethode | Muss/Soll |
|---|---|---|---|
| F1 | **Einfache Frage ohne Tools** wird mit 1 LLM-Call beantwortet | Unit Test: "Was ist 2+2?" → keine tool_calls, direkte Antwort | MUSS |
| F2 | **File-Read Task** nutzt Tool und antwortet korrekt | Integration Test: "Lies die package.json" → read_file → Antwort | MUSS |
| F3 | **Multi-Tool Task** ketten Tools korrekt | Integration Test: "Lies die Datei und erstelle ein Backup" → read_file → write_file → Antwort | MUSS |
| F4 | **Fehler-Recovery**: LLM sieht Tool-Fehler und versucht Alternative | Integration Test: read_file mit falschem Pfad → LLM korrigiert Pfad automatisch | MUSS |
| F5 | **Loop Detection** unterbricht Endlosschleifen | Unit Test: Gleicher Tool-Call 3x hintereinander → Abbruch mit Antwort | MUSS |
| F6 | **Budget Exhaustion** erzwingt finale Antwort | Integration Test: 50+ Tool Calls → "[SYSTEM] Budget exhausted" → LLM antwortet | MUSS |
| F7 | **Time Budget** beendet nach max. N Sekunden | Unit Test: Mock-Tool mit sleep(999) → Timeout nach runner_time_budget_seconds | MUSS |
| F8 | **Steer Interrupt** unterbricht den Loop | Integration Test: should_steer_interrupt() returns True → Loop stoppt | MUSS |
| F9 | **Context Overflow** wird graceful behandelt | Integration Test: Sehr großes Tool-Ergebnis → Messages komprimiert → Loop geht weiter | MUSS |
| F10 | **Evidence Gate: Implementation** blockiert halluzinierten Erfolg | Unit Test: Task "create file" ohne write_file Erfolg → Fehlermeldung statt Erfolg | MUSS |
| F11 | **Evidence Gate: All-Tools-Failed** meldet Fehler ehrlich | Unit Test: Alle Tools fehlgeschlagen → Antwort bestätigt Fehler | MUSS |
| F12 | **Evidence Gate: Orchestration** prüft Subrun-Erfolg | Unit Test: spawn_subrun ohne completion → Warnung | MUSS |
| F13 | **MCP Tools** funktionieren im neuen Loop | Integration Test: MCP Tool wird als function call erkannt und ausgeführt | MUSS |
| F14 | **Feature Flag** schaltet zuverlässig zwischen alt und neu | Integration Test: USE_CONTINUOUS_LOOP=true → neuer Loop, =false → alter Loop | MUSS |
| F15 | **Alle bestehenden Benchmark-Szenarien** bestehen mit neuem Runner | Benchmark-Suite: scenarios-v4.json mit USE_CONTINUOUS_LOOP=true | MUSS |
| F16 | **Ambiguity/Clarification** funktioniert weiter | Integration Test: Mehrdeutige Frage → Rückfrage an User | MUSS |
| F17 | **Parallel Tool Calls** werden korrekt behandelt | Integration Test: LLM gibt 2 tool_calls zurück → Beide ausgeführt | SOLL |
| F18 | **LLM "denkt laut" zwischen Tools** wird gestreamt | Integration Test: Text vor tool_call → wird als stream Event gesendet | SOLL |

### Nicht-Funktionale Akzeptanzkriterien

| # | Kriterium | Prüfmethode | Muss/Soll |
|---|---|---|---|
| NF1 | **Latenz bei einfachen Fragen** mindestens gleich oder besser als 3-Phase | Benchmark: Latenz-Vergleich alt vs. neu für einfache Fragen | MUSS |
| NF2 | **Token-Verbrauch** bei einfachen Fragen niedriger als 3-Phase | Benchmark: Token-Count Vergleich (3x System-Prompt vs. 1x) | MUSS |
| NF3 | **Time-to-first-token** bei einfachen Fragen < 2 Sekunden | Benchmark: Messung von Request-Start bis erster Stream-Event | SOLL |
| NF4 | **Kein Memory Leak** im Loop | Load Test: 100 Requests hintereinander, Memory-Verbrauch bleibt konstant | MUSS |
| NF5 | **WebSocket-Kompatibilität** nicht gebrochen | Frontend-Test: Bestehende Events werden weiter empfangen + neue Events | MUSS |
| NF6 | **Command Safety** identisch zum alten System | Security Test: Alle COMMAND_SAFETY_PATTERNS werden weiter geblockt | MUSS |
| NF7 | **SSRF Protection** identisch zum alten System | Security Test: URL-Validation und DNS-Pinning funktionieren weiter | MUSS |
| NF8 | **Prompt Injection** observe-only Detection funktioniert weiter | Security Test: Injection Patterns werden weiter erkannt und geloggt | MUSS |

### Definition of Done

```
☐ AgentRunner Klasse existiert mit run() Methode
☐ LlmClient.stream_chat_with_tools() implementiert und getestet
☐ Unified System Prompt Builder implementiert
☐ Loop Detection mit 3 Detektoren implementiert und getestet
☐ Message Compaction implementiert und getestet
☐ Evidence Gates migriert und getestet (alle 4)
☐ Feature Flag USE_CONTINUOUS_LOOP in config.py
☐ HeadAgent.run() routet basierend auf Feature Flag
☐ Alle bestehenden Unit Tests grün
☐ Alle bestehenden Benchmark-Szenarien bestehen
☐ Neue Unit Tests für AgentRunner (mindestens 20 Tests)
☐ Integration Tests für den Continuous Loop (mindestens 10 Szenarien)
☐ Frontend empfängt neue Events korrekt
☐ Keine Security-Regression (OWASP Checks)
☐ Latenz-Benchmark zeigt keine Regression
☐ Token-Verbrauch-Benchmark zeigt Verbesserung bei einfachen Fragen
☐ Code Review durchgeführt
☐ Dokumentation aktualisiert (ARCHITECTURE.md)
```

---

## 14. Risiken & Mitigationen

| # | Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|---|---|---|---|---|
| R1 | LLM nutzt Tools exzessiv (Token-Explosion) | Mittel | Hoch | Hard Budget Limits: max_iterations=25, max_tool_calls=50, time_budget=300s |
| R2 | LLM gerät in Endlosschleife | Hoch | Hoch | 3-fache Loop Detection + Budget Limits + Forced Final Answer |
| R3 | Context Overflow bei vielen Tool-Iterationen | Mittel | Mittel | Auto-Compaction von alten Tool-Results + Message Truncation |
| R4 | Unified Prompt schlechter als spezialisierte Phase-Prompts | Mittel | Mittel | AB-Test über Feature Flag: Beide Modes parallel testen, Qualität vergleichen |
| R5 | Provider-Inkompatibilität (nicht alle unterstützen streaming+tools) | Niedrig | Mittel | Non-Streaming Fallback in stream_chat_with_tools() |
| R6 | WebSocket-Schema-Breaking für Frontend | Niedrig | Hoch | Neue Events ADDITIV, bestehende Events NICHT ändern |
| R7 | Evidence Gates falsch migriert | Niedrig | Hoch | 1:1 Migration, gleiche Testfälle, gleiche Assertions |
| R8 | MPC Tools funktionieren nicht im neuen Format | Niedrig | Mittel | MCP Tools werden als normale function definitions registriert — gleiches Format |
| R9 | Regression bei bestehenden Benchmarks | Mittel | Hoch | Feature Flag + Comparison Benchmarks VOR Cutover |
| R10 | ReflectionService funktioniert nicht ohne Plan-Phase | Niedrig | Niedrig | Reflection bekommt als "plan" den gesamten Loop-Verlauf, nicht nur Plan-Text |

---

## 15. Rollback-Strategie

### Sofort-Rollback (< 1 Minute)

```bash
# Environment Variable auf Server setzen:
USE_CONTINUOUS_LOOP=false

# Oder in config.py:
# class Settings:
#     use_continuous_loop: bool = False

# Server Restart → Alter 3-Phase Code aktiv
```

### Warum Rollback sicher ist

1. **Keine DB-Migrationen**: Kein Schema-Change in Memory/State Stores
2. **Keine API-Breaking Changes**: WebSocket empfängt alte Events weiter
3. **Feature Flag ist Request-Level**: Nächster Request nutzt alten Code
4. **Alte Code-Pfade bleiben compiliert**: HeadAgent._run_legacy() existiert parallel
5. **Alte Tests bleiben grün**: CI tested BEIDE Pfade

### Wann Rollback nötig

- Benchmark-Szenarien fallen unter 80% Pass-Rate
- Token-Verbrauch steigt um > 50% gegenüber altem System
- Latenz für einfache Fragen steigt um > 2x
- Evidence Gates produzieren False Positives/Negatives
- Unerklärliche Endlosschleifen trotz Loop Detection
- Frontend kann neue Events nicht verarbeiten

---

## Appendix A: Settings-Referenz

```python
# Neue Settings für AgentRunner (config.py)

# Feature Flag
USE_CONTINUOUS_LOOP: bool = False

# Loop Limits
RUNNER_MAX_ITERATIONS: int = 25          # Max LLM-Calls pro Run
RUNNER_MAX_TOOL_CALLS: int = 50          # Max Tool-Executions pro Run
RUNNER_TIME_BUDGET_SECONDS: int = 300    # Max Laufzeit pro Run (5 Min)
RUNNER_CONTEXT_BUDGET: int = 4096        # Token-Budget für Initial Context

# Loop Detection
RUNNER_LOOP_DETECTION_THRESHOLD: int = 3  # Gleiche Tool-Calls hintereinander
RUNNER_LOOP_DETECTION_ENABLED: bool = True

# Compaction
RUNNER_COMPACTION_ENABLED: bool = True
RUNNER_COMPACTION_TAIL_KEEP: int = 4     # Letzte N Messages nicht komprimieren
RUNNER_TOOL_RESULT_MAX_CHARS: int = 5000 # Max Zeichen pro Tool-Result in History

# Reflection (Post-Loop)
RUNNER_REFLECTION_ENABLED: bool = True
RUNNER_REFLECTION_MAX_PASSES: int = 1    # Max Reflection-Iterationen
```

## Appendix B: Migration Checkliste pro Datei

| Datei | Aktion | Phase | Priorität |
|---|---|---|---|
| `agent_runner_types.py` | NEU erstellen | A | P0 |
| `agent_runner.py` | NEU erstellen | A+B | P0 |
| `llm_client.py` | `stream_chat_with_tools()` hinzufügen | A | P0 |
| `config.py` | Neue Settings hinzufügen | A | P0 |
| `agent.py` | Feature-Flag Router in `run()` | D | P0 |
| `agent.py` | `_run_legacy()` aus altem `run()` | D | P0 |
| `agent.py` | `__init__()` → AgentRunner erstellen | D | P0 |
| `ws_handler.py` | Neue Event-Types unterstützen | D | P1 |
| `contracts/schemas.py` | RunInput (optional) | E | P2 |
| `orchestrator/step_executors.py` | Deprecation Marker | E | P2 |
| `agents/planner_agent.py` | Deprecation Marker | E | P3 |
| `agents/tool_selector_agent.py` | Deprecation Marker | E | P3 |
| `agents/synthesizer_agent.py` | Deprecation Marker | E | P3 |

## Appendix C: Prompt-Vorlage Unified System Prompt

```
Du bist {role_name}, ein KI-Assistent mit Zugriff auf Tools.

## Deine Arbeitsweise
- Analysiere die Anfrage des Users.
- Wenn du die Antwort bereits kennst: Antworte direkt.
- Wenn du Informationen brauchst: Nutze die verfügbaren Tools.
- Wenn du eine Aufgabe ausführen musst: Nutze die passenden Tools.
- Du kannst mehrere Tools hintereinander nutzen.
- Nach jeder Tool-Nutzung entscheide: Brauche ich weitere Tools oder kann ich antworten?

## Verfügbare Tools
Die Tools sind als Function Definitions bereitgestellt. Nutze sie nach Bedarf.

## Antwort-Richtlinien
{final_instructions}

## Sicherheitsrichtlinien
{guardrails}
```

**NICHT in den Prompt schreiben:**
- "Erstelle zuerst einen Plan"
- "Wähle dann die passenden Tools aus"
- "Fasse abschließend zusammen"

Das LLM soll NATÜRLICH arbeiten, nicht nach Schema.
