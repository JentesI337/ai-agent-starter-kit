# Roadmap to Autonomy

> **Scope:** LLM→Tool-Pipeline-Vergleich OpenClaw ↔ ai-agent-starter-kit  
> **Ziel:** Präzise Diff-Karte, Dos/Don'ts und messbare Akzeptanzkriterien für den Weg zu production-grade Tool-Use-Zuverlässigkeit  
> **Quellen:** Code-Archäologie beider Codebases; keine Annahmen, nur belegte Fakten

---

## 1. Vollständige Differenz-Karte (alle belegten Unterschiede)

### 1.1 Architektur & Hauptschleife

| Dimension | OpenClaw | Starter-Kit | Implikation |
|---|---|---|---|
| **Schleifentyp** | Einzelner stateful LLM-Loop; pi-sdk handelt Tool-Calls intern | Explizite 3-Stufen-Pipeline: Plan → `_execute_tools` → Synthesize | Starter-Kit erzwingt explizite Übergabeverträge; macht Debugging einfacher, aber auch mehr Bruchstellen |
| **Tool-Call-Mechanismus Default** | Native Function Calling immer aktiv; kein Text-Parsing | `select_actions_with_repair()` nutzt **text-basiertes** `[TOOL_CALL]`-Parsing per Default; Function Calling ist `tool_selection_function_calling_enabled=False` in `agent.py` | **Kritischer Unterschied**: Text-Parsing ist fehleranfälliger als natives FC; Repair-Loop ist Kompensation |
| **Repair-Schleife** | Nicht nötig (natives FC) | `select_actions_with_repair()` + `repair_tool_selection_json()` fangen ungültige JSON-Actions auf | FC-Aktivierung würde Repair-Loop überflüssig machen |
| **Session-Serialisierung** | Eine Lane pro Session (durch pi-sdk sichergestellt) | `SessionInboxService` + WS-Receive/Execute-Split; Queue-Modi `wait/follow_up/steer` | ✅ Beide haben das Pattern; Starter-Kit hat es sogar explizit modelliert |
| **Steer-Interrupt** | Nach jedem Tool-Call Inbox-Check; neuer Input bricht restliche Actions ab | `should_steer_interrupt` Callback in `run_tool_loop()` | ✅ Beide implementiert |

---

### 1.2 Tool-Assembly & Katalog

| Dimension | OpenClaw | Starter-Kit | Implikation |
|---|---|---|---|
| **Tool-Katalog** | `createOpenClawCodingTools()` — dynamische Factory per Session; 7 pi-sdk Basis-Tools + 18 OpenClaw-Tools + Plugin-Tools + MCP-Tools | `TOOL_NAMES` Tuple (18 Einträge) in `tool_catalog.py` — statisch zur Compile-Zeit | OpenClaw erweitert Tool-Set dynamisch; Starter-Kit ergänzt MCP via `McpBridge` aber Kern-Katalog ist statisch |
| **Plugin-Tools** | Vollständiges Plugin-Registry; jedes Plugin kann Tools registrieren; `optional` Tools brauchen explizite Allowlist | `McpBridge` für externe MCP-Tools; keine native Plugin-Registry für Code-First-Tools | Starter-Kit muss MCP-Tools manuell in `tool_registry` registrieren um Policy/Schema-Pipeline zu durchlaufen |
| **Skill-basiertes Wissen** | Skills über Prompt-Sektionen (`## Tooling`); kein explizites Lazy-Loading von Skill-Docs | `SkillsService` + `ReliableRetrievalService` (RAG); Lazy-Load von SKILL.md per `read_file`-Aufruf | ✅ Starter-Kit hat hier ein **überlegenes** Pattern: Skills werden tatsächlich bei Bedarf geladen |
| **Fähigkeits-Vorauswahl** | Keine explizite Capability-Preselection dokumentiert | `_infer_required_capabilities()` → `filter_tools_by_capabilities()` reduziert Tool-Set vor LLM-Call | ✅ Starter-Kit hat das; OpenClaw verlässt sich auf Policy-Ebene |

---

### 1.3 Policy-System

| Dimension | OpenClaw | Starter-Kit | Implikation |
|---|---|---|---|
| **Policy-Schichten** | 9 Schichten mit Glob-Matching: `profile → providerProfile → global → globalProvider → agent → agentProvider → group → sandbox → subagent` | 5 Schichten als Mengen-Operationen: `base_catalog → config_allow (∩) → request_allow (∩) → deny (−) → also_allow (∪) → per-agent-override` | OpenClaw: Glob-Matching ermöglicht `tools/*`-Patterns; Starter-Kit: exakte Namen only |
| **Glob-Support** | ✅ Vollständig (`tools/read_*`, `tools/write_*` etc.) | ❌ Nicht vorhanden; nur exakte Tool-Namen | Starter-Kit-Policy ist gröber; keine Grouping-Wildcards |
| **Profile-Konzept** | Tool-Profile (`minimal/coding/messaging/full`) mit vordefinierten Erlaubnislisten | `prompt_mode` (`full/minimal/subagent`) existiert, aber kein äquivalentes Tool-Profil-Konzept | Starter-Kit hat kein dediziertes "Nur-Lesen-Profil" o.ä. |
| **Read-Only-Parallelität** | Explizit in `tool-split.ts`; read-only Tools werden parallel ausgeführt | `ToolExecutionManager.READ_ONLY_TOOLS` Set vorhanden; `parallel_read_only_enabled` Setting | ✅ Beide haben das Pattern; Starter-Kit ist konfigurierbar |
| **Subagent-Deny** | Automatische Deny-Erweiterung bei Spawn-Tiefe | `ReviewAgentAdapter._MANDATORY_DENY = {write_file, apply_patch, run_command, code_execute, start_background_command, kill_background_process}` — hardcoded Read-Only | ✅ Beide erzwingen Subagent-Isolation; OpenClaw ist konfigurierbar, Starter-Kit hardcoded |

---

### 1.4 Schema-Normalisierung

| Dimension | OpenClaw | Starter-Kit | Implikation |
|---|---|---|---|
| **Provider-spez. Bereinigung** | TypeBox-Schema pro Provider: Gemini strippt `format/minimum/maximum`; Anthropic patcht Root-Unions | Einheitliches OpenAI-Format; keine Provider-spezifische Normalisierung | **Open-Bug-Klasse**: Starter-Kit bricht silently bei Non-OpenAI-Providern (Gemini/Anthropic) die strict-Schema-Validation betreiben |
| **Schema-Typ** | TypeBox `Type.*` zur Compile-Zeit; stark typisiert | `ToolSpec.parameters` als freier `dict`; `additionalProperties` oft ungesetzt | Starter-Kit hat unstrenge Schemas; Modell bekommt unklares Action-Space-Signal |
| **Schema-Kompaktierung** | Explizite Schema-Verkleinerung für Token-Budget | `tool_schema_token_share` als KPI geplant (s. `fahrplan.md`) aber noch nicht implementiert | Starter-Kit Token-Budget für Tool-Schemas unkontrolliert |

---

### 1.5 Fehlerkontrakt & Zuverlässigkeit

| Dimension | OpenClaw | Starter-Kit | Implikation |
|---|---|---|---|
| **Error-Contract** | `toToolDefinitions()` fängt ALLE Fehler; gibt `{status:"error", tool, error}` zurück — niemals throw | `ToolExecutionError` wird geraised; in `run_tool_loop()` als `[error]` Text encodiert | Beide enden mit "LLM sieht Fehler als Text"; OpenClaw ist strikter (strukturiertes JSON) |
| **Replan bei Fehler** | Kein separater Replan-Mechanismus nötig (pi-sdk korrigiert inline) | `_classify_tool_results_state()` erkennt `error_only` → Replan-Trigger | ✅ Starter-Kit hat expliziten Replan-Mechanismus — sehr gut |
| **Loop-Detection** | `tool-loop-detection.ts`: `generic_repeat`, `ping_pong`, `poll_no_progress` mit Call-Fingerprinting | `ToolExecutionConfig`: `loop_warn_threshold`, `loop_critical_threshold`, `loop_circuit_breaker_threshold`, `generic_repeat_enabled`, `ping_pong_enabled`, `poll_no_progress_enabled` | ✅ **Starter-Kit hat gleichwertiges Pattern** — bitte beibehalten und nicht schwächen |
| **Cancellation** | AbortSignal wird in jedes Tool-Wrap injiziert; cooperatives Cancellation | asyncio-Cancellation implizit; kein explizites AbortSignal-Äquivalent per Tool | Starter-Kit kann einzelne Tools nicht granular canceln ohne den ganzen Task zu canceln |
| **Context-Budget pro Result** | `tool-result-context-guard.ts` — pro Tool-Result wird Größe vor Context-Append geprüft | `ToolExecutionConfig.result_max_chars` + `smart_truncate_enabled`; `tool_result_context_guard.py` | ✅ Beide implementiert |

---

### 1.6 Hook/Middleware-System

| Dimension | OpenClaw | Starter-Kit | Implikation |
|---|---|---|---|
| **Hook-Granularität** | `wrapToolWithBeforeToolCallHook` wraps JEDES einzelne Tool; Hooks: `before_tool_call`, `after_tool_call`, `tool_result_persist`, `before_prompt_build`, `before_transcript_append`, Message-Hooks, Session-Hooks | `_invoke_hooks()` an Lifecycle-Punkten; implementierte Hookpoints: `before_prompt_build`, `before_transcript_append`, `agent_end` | `before_tool_call`/`after_tool_call` Hookpoints fehlen im Starter-Kit; kein Per-Tool-Wrap |
| **Hook-Safety** | Hooks können AbortSignal auslösen | Per-Hook Timeout + Fehler-Isolation geplant (s. `fahrplan.md` P4.2) | ❌ Noch nicht implementiert |
| **Result-Transform** | `tool_result_persist` Hook transformiert vor Context-Persist (redact/compact/chunk) | Result-Transform-Chain geplant (s. `fahrplan.md` P4.3) | ❌ Noch nicht implementiert |

---

### 1.7 System-Prompt & Tooling-Injection

| Dimension | OpenClaw | Starter-Kit | Implikation |
|---|---|---|---|
| **Tooling-Section im System-Prompt** | `## Tooling` Section listet alle Tools + Descriptions inline | Tool-Liste wird in `build_tool_selector_prompt()` eingebaut; kein fixer `## Tooling` Block im System-Prompt | Starter-Kit baut Tool-Kontext dynamisch je nach allowed_tools — flexibler, aber weniger vorhersagbar |
| **Prompt-Kernel-Versionierung** | Keine explizite Kernel-Versionierung dokumentiert | `PromptKernelBuilder` erzeugt `kernel_version` + `prompt_hash` | ✅ Starter-Kit hat hier ein **überlegenes** Feature |
| **Prompt-Modi** | `promptMode minimal` für Subagents (Sektionen weggelassen) | `prompt_mode = full/minimal/subagent` mit unterschiedlichen Sektions-Mengen | ✅ Gleichwertig |
| **Out-of-Band-Direktiven** | `/think`, `/verbose`, `/reasoning`, `/model`, `/queue` werden aus Prompt gestripped | `DirectiveParser` in `services/directive_parser.py` existiert; Integration-Level unklar | Starter-Kit hat den Parser, aber Verdrahtung in den Haupt-Run unklar (s. `fahrplan.md` P6.1) |

---

### 1.8 Multi-Agent & Delegation

| Dimension | OpenClaw | Starter-Kit | Implikation |
|---|---|---|---|
| **Workspace-Isolation** | Separater `workspaceDir`, `agentDir`, separate Sessions, separate Credentials per Subagent | `agent_isolation.py` existiert; `workspace_root` je Agent optional | ✅ Basis vorhanden; Vollständigkeit unklar |
| **Delegation-Vertrag** | `terminal_reason`, `confidence`, `result_summary`, structured handover; ping-pong mit Max-Rounds | `spawn_subrun` Tool + `mode=wait/fire_and_forget/poll`; `terminal_reason` im Ergebnis | ✅ Gleichwertig |

---

## 2. Dos (präzise Handlungsanweisungen)

### D-1: Native Function Calling aktivieren
```python
# In agent.py, Zeile ~2000: tool_selection_function_calling_enabled=False → True
# NUR wenn client.supports_function_calling == True
tool_selection_function_calling_enabled=self.client.supports_function_calling,
```
**Warum:** Text-Parsing via `[TOOL_CALL]`-Blöcke ist der einzige echte Reliability-Bottleneck in der gesamten Pipeline. Mit nativem FC entfällt die Repair-Schleife fast vollständig.  
**Gate:** Aktivierung schrittweise — zuerst Shadow-Mode (beide Pfade messen), dann Canary.

### D-2: Provider-spezifische Schema-Normalisierung einbauen
```python
# services/tool_registry.py: build_function_calling_tools() erweitern
def build_function_calling_tools(self, allowed_tools: set[str], provider: str = "openai") -> list[dict]:
    tools = self._build_raw_tools(allowed_tools)
    return self._normalize_for_provider(tools, provider)

def _normalize_for_provider(self, tools: list[dict], provider: str) -> list[dict]:
    if provider == "gemini":
        return [self._strip_gemini_unsupported_fields(t) for t in tools]
    if provider in ("anthropic", "claude"):
        return [self._patch_anthropic_root_union(t) for t in tools]
    return tools
```
**Warum:** Gemini lehnt `format`, `minimum`, `maximum` in Tool-Schemas ab. Anthropic hat Root-Union-Einschränkungen. Ohne Normalisierung brechen Calls silently.  
**Zu strippen für Gemini:** `format`, `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum` auf Schema-Property-Ebene.

### D-3: Typed ToolSpec-Schemas härten (additionalProperties: false)
```python
# services/tool_registry.py: ToolSpec.parameters sollte enge Schemas haben
# Beispiel für run_command:
ToolSpec(
    name="run_command",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to run"},
            "timeout": {"type": "integer", "minimum": 1, "maximum": 300}
        },
        "required": ["command"],
        "additionalProperties": False  # ← kritisch
    },
    ...
)
```
**Warum:** Unstrenge Schemas (`additionalProperties: true` oder fehlend) geben dem Modell ein schlechtes Action-Space-Signal. Enge Schemas senken Parse/Repair-Rate nachweislich.

### D-4: `before_tool_call` / `after_tool_call` Hookpoints implementieren
```python
# services/tool_execution_manager.py: run_tool_loop() erweitern
await invoke_hooks("before_tool_call", {
    "tool": action["tool"],
    "args": action,
    "call_count": call_count,
    "session_id": session_id,
})
result = await run_tool_with_policy(...)
await invoke_hooks("after_tool_call", {
    "tool": action["tool"],
    "result_chars": len(result),
    "elapsed_ms": elapsed_ms,
})
```
**Warum:** Ohne diese Hooks ist es unmöglich, Tool-Calls zu intercepten, Args zu normalisieren, gefährliche Calls in letzter Sekunde zu blocken oder Results vor Context-Persist zu transformieren.

### D-5: Loop-Detection-Config schützen
Die bestehende `ToolExecutionConfig` mit `generic_repeat_enabled`, `ping_pong_enabled`, `poll_no_progress_enabled` ist **korrekt und gleichwertig zu OpenClaw**. Diese Konfiguration:
- NIEMALS `loop_circuit_breaker_threshold` auf 0 oder sehr hohe Werte setzen
- `loop_warn_threshold = 2`, `loop_critical_threshold = 5`, `loop_circuit_breaker_threshold = 9` sind gute Defaults
- Alle drei Detektor-Typen aktiviert lassen

### D-6: Steer-Interrupt als First-Class-Feature behalten
```python
# services/tool_execution_manager.py: run_tool_loop()
# NACH jedem Tool-Call prüfen:
if should_steer_interrupt and should_steer_interrupt():
    return STEER_INTERRUPTED_MARKER + tool_results_so_far
```
`STEER_INTERRUPTED_MARKER` bereits implementiert — dieses Pattern beibehalten und ausbauen.

### D-7: Skills als Lazy-Load über read_file beibehalten
Das Starter-Kit hat ein **überlegenes** Skills-Pattern gegenüber OpenClaw: Skills werden nicht in den System-Prompt injiziert, sondern als Lese-Auftrag an den Agenten delegiert (`read_file(SKILL.md)`). Dieses Pattern:
- Hält Basis-Kontext klein
- Gibt dem Modell das Richtige-Tool-Signal
- Reduziert Halluzination über Tool-Details  

**NICHT ersetzen** durch OpenClaw-Variante (alle Skills inline).

### D-8: Replan-Mechanismus bei `error_only` bewahren
`_classify_tool_results_state()` → `error_only` → Replan-Trigger ist ein wichtiges Pattern. Sicherstellen, dass bei nativem FC-Aktivierung dieser Pfad weiterhin greift.

### D-9: Prompt-Kernel-Versionierung ausbauen
`PromptKernelBuilder` mit `kernel_version` + `prompt_hash` ist bereits implementiert. Diesen Hash in den Run-Audit schreiben — ermöglicht exakte Reproduzierbarkeit von Fehlerfällen.

### D-10: MCP-Tools müssen durch Policy+Schema-Pipeline laufen
Wenn `McpBridge` neue Tools hinzufügt, müssen diese:
1. Im `ToolRegistry` registriert werden (inkl. `ToolSpec` mit Parameters)
2. Durch `_resolve_effective_allowed_tools()` Policy-Pipeline laufen
3. In `build_function_calling_tools()` auftauchen

Nicht direkt als Raw-DI in `allowed_tools` injizieren.

---

## 3. Don'ts (was nicht replizieren / nicht einbauen)

### X-1: Text-basiertes `[TOOL_CALL]`-Parsing als dauerhaften Default belassen
Der aktuelle Default (`tool_selection_function_calling_enabled=False`) ist ein pragmatischer Kompromiss für Provider ohne FC-Support. **Kein permanentes Pattern.** Sobald FC verfügbar, aktivieren (D-1).

### X-2: Prototype-Mutation für Tool-Hooks
Keine `SomeClass.prototype.method = ...`-Patterns für Hook-Integration. Explizite Composition über `invoke_hooks`-Callback — das Starter-Kit macht das bereits korrekt.

### X-3: Error-as-Exception durch den Stack werfen lassen
`ToolExecutionError` sollte NIEMALS den gestapelten Run-Kontext zerstören. Immer in `run_tool_loop()` fangen, als `[error]` encodieren, und dem Replan-Mechanismus übergeben. Nie nach oben propagieren bis zur HTTP-Layer.

### X-4: AbortSignal aus OpenClaw 1:1 portieren
OpenClaw's `AbortSignal`-Wrapping per Tool ist ein Node.js/Browser-Konzept. In asyncio ist `asyncio.CancelledError` das Äquivalent. **Nicht** `abort_signal` als Token durch alle Tool-Calls durchschleifen; stattdessen `asyncio.wait_for()` mit Timeout pro Tool (bereits teilweise in `ToolExecutionConfig.time_cap_seconds`).

### X-5: 9-Schichten-Glob-Policy 1:1 portieren
OpenClaw's Glob-Matching (`tools/write_*`) ist mächtig aber komplex. Das Starter-Kit hat eine sauberere Flat-Set-Policy. **Nicht** das Glob-System portieren — stattdessen Tool-Profile (benannte Sets) einführen (s. `fahrplan.md` P3):
```python
TOOL_PROFILES = {
    "read_only": {"list_dir", "read_file", "file_search", "grep_search", "get_changed_files"},
    "coding": TOOL_PROFILES["read_only"] | {"write_file", "apply_patch", "run_command", "code_execute"},
    "research": TOOL_PROFILES["read_only"] | {"web_search", "web_fetch", "http_request"},
}
```

### X-6: `additionalProperties: true` in Tool-Schemas
Kein offenes Schema ohne Required-Felder und enges Properties-Set. Jedes ToolSpec.parameters muss `"additionalProperties": false` haben sobald das Schema bekannt ist.

### X-7: Zwei aktive Executors für dieselbe Session
Die Single-Lane-Invariante ist fundamental. Niemals `run()` ohne Session-Lock ausführen.

### X-8: Direktiven als Rohtext ins Modell durchleiten
`DirectiveParser` existiert — er MUSS aktiv sein bevor der User-Text in den Prompt kommt. Direktiven (`/queue`, `/model`, `/reasoning`) dürfen den LLM nie im Klartext erreichen.

### X-9: OpenClaw's `## Tooling` System-Prompt-Sektion direkt übernehmen
Das Starter-Kit baut Tool-Kontext dynamisch basierend auf `effective_allowed_tools`. Das ist **besser** als alle 18 Tools immer zu listen. Nicht regressieren zu statischer Tool-Liste im System-Prompt.

### X-10: Long-Term-Memory-Writes ohne Policy
`_distill_session_knowledge()` schreibt nach jedem erfolgreichen Run in `LongTermMemoryStore`. Kein unkontrolliertes Schreiben sensitiver Daten. Memory-Write muss Policy-Check durchlaufen (PII-Redaction analog `fahrplan.md` P4.3).

---

## 4. Akzeptanzkriterien

> Alle Kriterien sind binär (pass/fail) oder mit Schwellenwert. Baseline muss VOR Implementierung gemessen werden.

### AC-1: Native Function Calling ist Default bei FC-fähigen Providern
- `tool_selection_function_calling_enabled` ist `True` wenn `client.supports_function_calling == True`
- `repair_tool_selection_json()` wird bei FC ≤ 5% aller Tool-Selections aufgerufen (vs. Baseline-Messung)
- 0 `[TOOL_CALL]`-Parse-Fehler bei Standard-OpenAI-Modellen (gpt-4o, gpt-4-turbo, etc.)

### AC-2: Provider-Schema-Normalisierung schützt gegen Provider-Quirks
- Gemini-Calls mit Tool-Schemas, die `format`, `minimum`, `maximum` enthalten, schlagen NICHT fehl
- Anthropic-Calls mit Root-Union-Schemas schlagen NICHT fehl
- Schema-Normalisierung ist durch einen Unit-Test pro Provider abgedeckt (`test_schema_normalize_gemini`, `test_schema_normalize_anthropic`)

### AC-3: Tool-Schemas sind streng typisiert
- Alle 18 Core-Tools haben `additionalProperties: false` in ihren ToolSpec.parameters
- Schema-Kompaktierung (ohne `format`/`minimum` bei Gemini) reduziert Token-Verbrauch für Tool-Schemas um ≥ 20% (messen via `tool_schema_token_share`)

### AC-4: `before_tool_call` / `after_tool_call` Hooks feuern
- Bei registriertem Hook wird `before_tool_call` für JEDEN Tool-Call aufgerufen
- Hook-Fehler bricht den Run NICHT ab (Isolation)
- Per-Hook Timeout ≤ 500ms (keine Latenz-Regression)

### AC-5: Loop-Detector bleibt vollständig aktiv
- `generic_repeat_enabled = True`
- `ping_pong_enabled = True`
- `poll_no_progress_enabled = True`
- `loop_circuit_breaker_threshold ≤ 9`
- Bestehende Loop-Detection-Tests bestehen weiterhin ohne Änderung

### AC-6: Steer-Interrupt funktioniert zuverlässig
- Neuer User-Input während laufendem Tool-Loop wird innerhalb eines Tool-Call-Zyklus als Steer erkannt
- `steer_interrupt_rate ≥ 90%` in künstlichen Fehlrichtungs-Tests
- `STEER_INTERRUPTED_MARKER` erscheint im tool_results wenn Steer aktiv

### AC-7: Policy-System korrekt
- Deny-Set überschreibt auch_allow und request_allow
- Per-Agent-Override funktioniert isolliert (Agent A-Override beeinflusst nicht Agent B)
- `ReviewAgentAdapter._MANDATORY_DENY` ist nicht umgehbar via `also_allow`
- Unbekannte Tool-Namen in Policy erzeugen eine auditierbare `warning` (nicht silently ignoriert)

### AC-8: Replan bei Tool-Fehler greift
- Bei `error_only` Tool-Results wird Replan-Zyklus ausgelöst (max. `max_error_tool_replan_attempts`)
- `error_tool_replan_attempts_used` wird im Audit-Log erfasst
- Replan-Pfad ist durch Integration-Test abgedeckt

### AC-9: Single-Lane-Invariante
- Zwei gleichzeitige `run()`-Calls mit gleicher `session_id` laufen NICHT parallel
- Zweiter Call wird in Inbox gepuffert oder mit klarem Error abgewiesen
- `lane_queue_wait_ms_p95 ≤ 300ms` unter normaler Last

### AC-10: MCP-Bridge-Tools durchlaufen Policy+Schema-Pipeline
- Tools aus `McpBridge` sind im `ToolRegistry` sichtbar
- Sie erscheinen in `build_function_calling_tools()` Output wenn erlaubt
- Sie werden durch `_resolve_effective_allowed_tools()` Policy gefiltert

### AC-11: Directive-Parser ist aktiv vor Prompt-Build
- `/queue`, `/model`, `/reasoning`, `/verbose` directives werden aus User-Text entfernt bevor der Prompt gebaut wird
- `directive_strip_success_rate ≥ 99.5%`
- Direktiven erscheinen in `run_meta` im Audit (nicht im Prompt-Text)

### AC-12: Typed Error-Contract
- `ToolExecutionError` propagiert nie bis zur HTTP-Response-Layer als 500 wenn der Tool-Loop läuft
- Alle Tool-Fehler sind im tool_results String als `[error]` sichtbar
- `run_state_violation_rate = 0` in Production

---

## 5. Tests

> Präzise Testfälle mit Input, erwarteter Ausgabe und zu mockenden Dependencies.

### T-1: Native Function Calling Aktivierung (Unit)
```python
# test_tool_execution_manager.py
async def test_fc_enabled_skips_text_parsing():
    """Mit FC enabled soll extract_actions() nie aufgerufen werden."""
    extract_actions_mock = Mock(side_effect=AssertionError("should not be called"))
    complete_chat_with_tools_mock = AsyncMock(return_value=[
        {"type": "function", "function": {"name": "list_dir", "arguments": '{"path": "."}'}}
    ])
    manager = ToolExecutionManager(...)
    result = await manager.execute(
        ...,
        complete_chat_with_tools=complete_chat_with_tools_mock,
        supports_function_calling=True,
        tool_selection_function_calling_enabled=True,
        extract_actions=extract_actions_mock,
    )
    # extract_actions wurde nie aufgerufen
    extract_actions_mock.assert_not_called()
```

### T-2: Schema-Normalisierung Gemini (Unit)
```python
# test_tool_registry.py
def test_gemini_schema_strips_unsupported_fields():
    spec = ToolSpec(
        name="read_file",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "format": "uri", "minLength": 1}
            }
        }
    )
    registry = ToolRegistry([spec])
    tools = registry.build_function_calling_tools({"read_file"}, provider="gemini")
    prop = tools[0]["function"]["parameters"]["properties"]["path"]
    # Gemini verträgt weder format noch minLength
    assert "format" not in prop
    assert "minLength" not in prop
    assert prop["type"] == "string"  # type erhalten
```

### T-3: Schema-Normalisierung Anthropic Root-Union (Unit)
```python
def test_anthropic_no_root_anyof():
    spec = ToolSpec(
        name="web_search",
        parameters={
            "anyOf": [
                {"type": "object", "properties": {"query": {"type": "string"}}},
                {"type": "null"}
            ]
        }
    )
    registry = ToolRegistry([spec])
    tools = registry.build_function_calling_tools({"web_search"}, provider="anthropic")
    param = tools[0]["function"]["parameters"]
    # Anthropic erlaubt kein Root-anyOf → patchen auf object
    assert param.get("type") == "object"
    assert "anyOf" not in param
```

### T-4: Loop-Detector Circuit-Breaker (Unit)
```python
async def test_loop_circuit_breaker_stops_at_threshold():
    """Der gleiche Tool-Call N mal → Circuit-Breaker soll bei threshold stoppen."""
    call_count = 0
    async def fake_run_tool(tool, args, **_):
        nonlocal call_count
        call_count += 1
        return f"result_{call_count}"

    config = ToolExecutionConfig(
        call_cap=20,
        loop_circuit_breaker_threshold=3,
        generic_repeat_enabled=True,
        ...
    )
    actions = [{"tool": "read_file", "path": "/same/file.txt"}] * 10  # immer gleich
    result = await manager.run_tool_loop(
        actions=actions,
        config=config,
        run_tool_with_policy=fake_run_tool,
        ...
    )
    assert call_count <= 3  # nach 3 gleichen Calls: Circuit-Breaker
```

### T-5: Steer-Interrupt (Integration)
```python
async def test_steer_interrupt_stops_remaining_actions():
    """Steer nach erstem Tool-Call → restliche 4 Actions werden verworfen."""
    executed_tools: list[str] = []
    call_idx = 0

    async def fake_run_tool(tool, args, **_):
        nonlocal call_idx
        executed_tools.append(tool)
        call_idx += 1
        return "ok"

    interrupt_after_first = [False]
    def should_steer():
        # True ab zweitem Check (nach erstem Tool-Call)
        return len(executed_tools) >= 1

    actions = [
        {"tool": "list_dir", "path": "."},
        {"tool": "read_file", "path": "a.txt"},
        {"tool": "read_file", "path": "b.txt"},
        {"tool": "grep_search", "pattern": "foo"},
        {"tool": "file_search", "pattern": "*.py"},
    ]
    result = await manager.run_tool_loop(
        actions=actions,
        should_steer_interrupt=should_steer,
        run_tool_with_policy=fake_run_tool,
        ...
    )
    assert len(executed_tools) == 1  # nur erster ausgeführt
    assert result.startswith(STEER_INTERRUPTED_MARKER)
```

### T-6: Policy Deny überschreibt also_allow (Unit)
```python
def test_deny_overrides_also_allow():
    agent = HeadAgent(...)
    policy = {
        "deny": ["run_command"],
        "also_allow": ["run_command"],  # Versuch, Deny zu umgehen
    }
    effective = agent._resolve_effective_allowed_tools(policy)
    assert "run_command" not in effective
```

### T-7: ReviewAgentAdapter MANDATORY_DENY nicht umgehbar (Unit)
```python
def test_review_agent_mandatory_deny_not_bypassed():
    adapter = ReviewAgentAdapter(inner_agent=mock_agent)
    policy = {
        "also_allow": list(ReviewAgentAdapter._MANDATORY_DENY)
    }
    result = adapter.resolve_effective_tools(policy)
    for tool in ReviewAgentAdapter._MANDATORY_DENY:
        assert tool not in result
```

### T-8: Replan bei error_only (Integration)
```python
async def test_replan_triggered_on_error_only_results():
    """Wenn alle Tool-Results [error] enthalten → Replan-Zyklus."""
    replan_count = 0
    original_plan = "Step 1: Do something"

    async def mock_plan(payload, model):
        nonlocal replan_count
        replan_count += 1
        return f"Replanned plan {replan_count}"

    async def mock_execute_tools(*args, **kwargs):
        return "[run_command] error: command not found"  # error_only

    agent = HeadAgent(...)
    agent._execute_planner_step = mock_plan
    agent._execute_tool_step = mock_execute_tools

    await agent.run(
        user_message="run npm test",
        session_id="test",
        request_id="req1",
        send_event=AsyncMock(),
        tool_policy={"allow": ["run_command"]},
    )
    assert replan_count >= 1
```

### T-9: MCP-Tool durch Policy-Pipeline (Integration)
```python
async def test_mcp_tool_filtered_by_deny_policy():
    bridge = McpBridge(...)
    bridge.register_tool("my_mcp_tool", spec=ToolSpec(...))
    agent = HeadAgent(mcp_bridge=bridge, ...)
    
    policy = {"deny": ["my_mcp_tool"]}
    effective = agent._resolve_effective_allowed_tools(policy)
    assert "my_mcp_tool" not in effective
    
    # Und im FC-Payload nicht vorhanden
    fc_tools = agent._build_function_calling_tools(effective)
    names = [t["function"]["name"] for t in fc_tools]
    assert "my_mcp_tool" not in names
```

### T-10: Single-Lane-Invariante (Load-Test)
```python
async def test_concurrent_runs_same_session_are_serialized():
    """2 gleichzeitige Runs für dieselbe Session dürfen nicht parallel laufen."""
    run_timeline: list[tuple[str, str]] = []

    async def slow_tool(*args, **kwargs):
        run_timeline.append(("start", kwargs.get("request_id")))
        await asyncio.sleep(0.1)
        run_timeline.append(("end", kwargs.get("request_id")))
        return "ok"

    agent = HeadAgent(...)
    results = await asyncio.gather(
        agent.run(user_message="msg1", session_id="same-session", request_id="req1", ...),
        agent.run(user_message="msg2", session_id="same-session", request_id="req2", ...),
    )
    
    # Validierung: req1 muss vollständig beendet sein bevor req2 beginnt
    starts = [r for e, r in run_timeline if e == "start"]
    ends = [r for e, r in run_timeline if e == "end"]
    assert starts[0] != starts[1]  # nicht gleichzeitig gestartet
    first_run = starts[0]
    first_end_idx = next(i for i, (e, r) in enumerate(run_timeline) if e == "end" and r == first_run)
    second_start_idx = next(i for i, (e, r) in enumerate(run_timeline) if e == "start" and r != first_run)
    assert first_end_idx < second_start_idx
```

### T-11: Directive-Strip vor Prompt-Build (Unit)
```python
def test_directive_stripped_before_prompt():
    from app.services.directive_parser import DirectiveParser
    parser = DirectiveParser()
    raw = "/model gpt-4o /reasoning high Bitte analysiere diese Datei."
    clean, directives = parser.parse(raw)
    assert clean == "Bitte analysiere diese Datei."
    assert directives.get("model") == "gpt-4o"
    assert directives.get("reasoning") == "high"
    # Direktiven nicht im Output-Text
    assert "/model" not in clean
    assert "/reasoning" not in clean
```

### T-12: Tool-Schema Token-Budget (Benchmark)
```python
def test_tool_schema_token_share_under_threshold():
    """Tool-Schemas sollen ≤ 25% des Gesamten Tool-Selector-Prompts ausmachen."""
    registry = build_full_tool_registry()  # alle 18 Tools
    tools = registry.build_function_calling_tools(set(TOOL_NAMES))
    schema_json = json.dumps(tools)
    full_prompt = build_tool_selector_prompt(
        allowed_tools=set(TOOL_NAMES),
        memory_context="[sample 2000 char context]",
        user_message="analyse this project",
        plan_text="1. read files 2. grep patterns",
    )
    schema_chars = len(schema_json)
    total_chars = len(full_prompt) + schema_chars
    assert schema_chars / total_chars <= 0.25, (
        f"Tool schema token share too high: {schema_chars/total_chars:.1%}"
    )
```

---

## 6. Priorisierung (Impakt × Aufwand)

| # | Maßnahme | Impakt | Aufwand | Priorität |
|---|---|---|---|---|
| 1 | Native FC aktivieren (D-1) | ⬛⬛⬛⬛ Kritisch | M | **Sofort** |
| 2 | Provider Schema-Normalisierung (D-2) | ⬛⬛⬛⬛ Kritisch | M | **Sofort** |
| 3 | Typed ToolSpec-Schemas (D-3) | ⬛⬛⬛ Hoch | M | Phase 1 |
| 4 | before/after_tool_call Hooks (D-4) | ⬛⬛⬛ Hoch | S | Phase 1 |
| 5 | Directive-Parser verdrahten (D-8, AC-11) | ⬛⬛⬛ Hoch | S | Phase 1 |
| 6 | MCP durch Policy-Pipeline (D-10) | ⬛⬛ Mittel | M | Phase 2 |
| 7 | Tool-Profile as named sets (X-5) | ⬛⬛ Mittel | S | Phase 2 |
| 8 | Result-Transform Chain (X-10, P4.3) | ⬛⬛ Mittel | L | Phase 3 |
| 9 | Hook-Safety + Timeouts (P4.2) | ⬛ Niedrig | S | Phase 3 |

---

## 7. Was bewusst NICHT portieren

1. **OpenClaw's Glob-Policy** → Stattdessen Profile (X-5)
2. **OpenClaw's statische `## Tooling` System-Prompt-Sektion** → Starter-Kit's dynamischer Build ist besser (X-9)
3. **pi-sdk Abstraktion** → Kein Node.js/TypeScript-Port; Python-native Lösung
4. **AbortSignal per Tool** → asyncio-Idiome (`asyncio.wait_for`, `asyncio.CancelledError`) stattdessen (X-4)
5. **Skills inline im System-Prompt** → Lazy-Load-Pattern beibehalten (D-7)

---

## 8. Quelldateien (Referenz)

| Datei | Rolle |
|---|---|
| `backend/app/agent.py` | Haupt-Orchestrator; `_execute_tools()` Zeile ~1750 |
| `backend/app/services/tool_execution_manager.py` | Haupt-Loop: `execute()`, `select_actions_with_repair()`, `run_tool_loop()` |
| `backend/app/services/tool_registry.py` | `ToolSpec`, `build_function_calling_tools()`, `filter_tools_by_capabilities()` |
| `backend/app/tool_catalog.py` | `TOOL_NAMES` Tuple, `TOOL_NAME_ALIASES` |
| `backend/app/tool_policy.py` | `ToolPolicyDict`, `AgentToolPolicyEntry`, `ExtendedToolPolicyDict` |
| `backend/app/agents/tool_selector_agent.py` | Stage-2-Wrapper; `_resolve_effective_allowed_tools()` |
| `backend/app/agents/head_agent_adapter.py` | `ReviewAgentAdapter._MANDATORY_DENY` |
| `backend/app/agents/fahrplan.md` | Übergeordneter Refactoring-Plan (Epics, KPIs, Sprints) |
| `backend/app/agents/importantPattern.md` | OpenClaw-Pattern-Philosophie (Referenz) |
