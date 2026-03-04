# Final Refactoring Plan — Ultimative Härte der Reasoning Pipeline

**Stand:** 2026-03-04  
**Basis:** Evidence-basiertes Delta: openclaw-Pipeline vs. ai-agent-starter-kit  
**Voraussetzung:** Issue-0008 (Fixes 1–5) muss deployed sein  

## Präziser Ist-Stand (2026-03-04)

Dieser Abschnitt dokumentiert ausschließlich bereits umgesetzte Änderungen aus der jüngsten Härtung, ohne neue Tasks abzuleiten.

- Orchestrierungs-Delegation wird bei automatischer `spawn_subrun`-Ergänzung standardmäßig mit `mode="wait"` erzeugt (statt `mode="run"`).
- Zusätzlicher Guard im Agent erzwingt `mode="wait"`, wenn `spawn_subrun` mit Orchestrierungs-Intent und `mode="run"` aufgerufen wird.
- Synthese-Self-Check enthält semantische Truth-Validierung:
    - `task_type="orchestration"` erfordert Evidenz `subrun-complete`.
    - `task_type in {orchestration_pending, orchestration_failed}` verbietet Erfolgsbehauptungen wie „successfully delegated“ ohne passende Evidenz.
- Regression für Single-Release-Verhalten ergänzt: `on_released` wird pro Lane-Run exakt einmal verifiziert.

### Testabdeckung der umgesetzten Punkte

- `backend/tests/test_action_augmenter.py`: prüft Wait-Default für auto-ergänzte `spawn_subrun`-Aktion.
- `backend/tests/test_tool_selection_offline_eval.py`: prüft Wait-Enforcement beim policy-approved `spawn_subrun`-Pfad.
- `backend/tests/test_synthesizer_agent.py`: prüft semantische Invalidierung ohne `subrun-complete` und Konfliktbehandlung bei Pending-Erfolgssprache.
- `backend/tests/test_session_lane_manager.py`: prüft exakt ein `on_released` bei Fehlerpfad.

## Operativer Ausführungs-Runbook (repo-validiert)

Dieser Abschnitt macht den Plan direkt implementierbar gegen den **aktuellen Code-Stand** in diesem Repository.

### Repo-validierte Korrekturen zur Dokument-Basis

- Der Compaction-/Reduktionscode liegt aktuell in `backend/app/state/context_reducer.py` (nicht in `backend/app/services/context_reducer.py`).
- Eine `role_ordering`-Failover-Klassifikation ist derzeit in `backend/app/orchestrator/pipeline_runner.py` **nicht** vorhanden; für Gap 6 muss zuerst die Klassifikation ergänzt werden.
- Tool-Policy hat bereits eine mehrstufige Auflösung in `backend/app/services/tool_policy_service.py` (`global/profile/preset/provider/model/agent_depth/request`), aber noch keine dedizierten `agents.{id}`-Overrides wie in Gap 10 beschrieben.
- Orchestrierungs-Evidenz (`spawned_subrun_id` + `subrun-complete`) ist bereits in `backend/app/agent.py` verdrahtet; fire-and-forget-Evidenz via Parent-Tool-Result fehlt weiterhin.

### Delivery-Strategie (No-Mistake-Modus)

Um Regressionen zu minimieren, in drei Wellen mit klaren Gates liefern:

1. **Welle A – Kritischer Korrektheitskern (Gaps 1, 2, 4)**
     - Ziel: falsche/abgebrochene Antworten und Session-Breaks eliminieren.
     - Merge nur bei grünem A-Gate (siehe Testmatrix).
2. **Welle B – Robustheit unter Last (Gaps 8, 3, 5, 7, 6)**
     - Ziel: Overflow-/Compaction-/Retry-Stabilität und Security-Härtung.
3. **Welle C – Konsistenz + Policy-Granularität (Gaps 9, 10)**
     - Ziel: korrekte Precedence bei Mehrfach-Status und feinere Agent-Policies.

### Umsetzungsreihenfolge mit DoD

#### Welle A (blockierend)

**A1 — Gap 1: Pre-LLM Tool-Result Context Guard**
- Dateien:
    - `backend/app/services/tool_result_context_guard.py` (neu)
    - `backend/app/agent.py` (Integration vor Synthesis)
    - `backend/app/config.py` (Feature-Flags + Ratios)
- Definition of Done:
    - Tool-Results werden **vor** Synthesis budgetiert.
    - Lifecycle-Event bei tatsächlicher Reduktion (`tool_result_context_guard_applied`).
    - Kein Verhaltenseinbruch bei kleinen Tool-Outputs (No-Op).

**A2 — Gap 2: Orphaned Tool-Call Repair**
- Dateien:
    - `backend/app/memory.py`
    - `backend/app/agent.py` (Aufruf direkt nach `memory.add(..., "user", ...)`)
- Definition of Done:
    - Orphaned tool-Calls werden deterministisch mit synthetischem Tool-Result geschlossen.
    - Keine Mutation bei bereits gepaarten tool_use/tool_result-Verläufen.

**A3 — Gap 4: Subrun-Announce als Parent-Tool-Result**
- Dateien:
    - `backend/app/main.py` (Completion-Callback zum Parent-Memory)
    - optional: `backend/app/orchestrator/subrun_lane.py` (falls Callback-API erweitert werden muss)
    - `backend/app/agent.py` (`_has_orchestration_evidence` für announce-Pfad)
- Definition of Done:
    - Fire-and-forget-Subruns liefern verwertbare Evidenz im Parent-Context.
    - Gate `orchestration_evidence_missing` feuert nicht fälschlich bei erfolgreichem Child-Abschluss.

#### Welle B

**B1 — Gap 8: Compaction Security Strip**
- Ziel-Datei (real): `backend/app/state/context_reducer.py`.
- DoD: Sensitive Pattern werden vor Compaction/Reduktion maskiert, ohne normale Inhalte zu zerstören.

**B2 — Gap 3: Identifier Preservation in Compaction Instructions**
- Ziel-Datei (real): `backend/app/state/context_reducer.py`.
- DoD: Prompt/Instruction enthält harte Identifier-Preservation-Regeln (UUID/run_id/session_id/spawned_subrun_id usw.).

**B3 — Gap 5: Context Window Defaults anheben**
- Datei: `backend/app/config.py`.
- DoD: Defaults mindestens auf `WARN=24000`, `HARD_MIN=12000`; bestehende Overrides per ENV bleiben intakt.

**B4 — Gap 7: Compaction Retry + Jitter**
- Primärdateien:
    - `backend/app/config.py`
    - `backend/app/orchestrator/pipeline_runner.py` und/oder `backend/app/orchestrator/fallback_state_machine.py`
- DoD:
    - Mehrere Compaction-Versuche mit exponentiellem Backoff + Jitter.
    - Kein sofortiges Hard-Fail bei transientem 429/503.

**B5 — Gap 6: Session-History-Sanitize bei Role-Ordering**
- Dateien:
    - `backend/app/memory.py` (`sanitize_session_history`)
    - `backend/app/orchestrator/pipeline_runner.py` (Reason-Klassifikation + Retry-Hook)
- DoD:
    - `roles must alternate` / `incorrect role information` werden als eigener Recovery-Reason behandelt.
    - Vor Retry läuft genau ein sanitize-Pass; Lifecycle signalisiert Anzahl entfernter Items.

#### Welle C

**C1 — Gap 9: Ordered Precedence in `_resolve_synthesis_task_type`**
- Datei: `backend/app/agent.py`.
- DoD: Letzter terminaler Subrun-Status gewinnt bei mehreren Status-Fragmenten.

**C2 — Gap 10: Tool-Policy-Granularität (agent overrides)**
- Dateien:
    - `backend/app/tool_policy.py`
    - `backend/app/services/tool_policy_service.py`
- DoD:
    - Agent-spezifische Overrides deterministisch mergebar.
    - Bestehende Auflösung (`global→…→request`) bleibt rückwärtskompatibel.

### Test-Matrix (konkret auf bestehende Suite gemappt)

- Gap 1: **neu** `backend/tests/test_tool_result_context_guard.py`
- Gap 2 + 6: **neu/erweitern** `backend/tests/test_memory_store_thread_safety.py` oder neue `backend/tests/test_memory_store_repair.py`
- Gap 3 + 8: **erweitern** `backend/tests/test_context_reducer.py`
- Gap 4 + 9: **erweitern** `backend/tests/test_tool_selection_offline_eval.py` (HeadAgent-Methoden) + ggf. `backend/tests/test_subrun_lane.py`
- Gap 5 + 7: **erweitern** `backend/tests/test_config_persistence_defaults.py` und `backend/tests/test_pipeline_runner_recovery.py`
- Gap 10: **erweitern** `backend/tests/test_tool_policy_depth.py`

### Merge-/Rollback-Regeln

- Jede Welle in separatem PR mergen (A vor B vor C).
- Pro Welle: zuerst zielgenaue Tests, danach breiter `backend/tests`-Lauf ohne E2E-Real-API.
- Rollback-Strategie:
    - Feature-Flags für neue Guards/Retry-Pfade standardmäßig aktiv, aber ENV-deaktivierbar.
    - Keine destruktiven Datenmigrationen in `memory_store`/`state_store`.

### Akzeptanzkriterien auf Systemebene

- Keine falsche Erfolgssynthese mehr bei fehlender Orchestrierungs-Evidenz.
- Kein Session-Deadlock durch orphaned tool_use oder role-ordering-Historie.
- Context-Overflow-Recovery degradiert kontrolliert statt hart abzubrechen.
- Compaction/Reduktion leakt keine offensichtlichen Secrets in persistente Kontexte.
- Policy bleibt strikt, aber in Multi-Agent-Setups granular steuerbar.

---

## Openclaw E2E Reasoning Pipeline — Referenzarchitektur

```
User Message
      │
      ▼
[Lane Queue]                            Lane-Serialisierung (session: + global)
      │
      ▼
[runEmbeddedAttempt]
  ├─ [1] Workspace Resolution
  ├─ [2] Model-Auflösung + before_model_resolve hook
  ├─ [3] Context Window Guard ← 🔴 HARD_MIN=16k / WARN=32k
  ├─ [4] Auth Profile Resolution (multi-profile + Copilot refresh)
  ├─ [5] Tool Policy Pipeline (7-Stufen-Kaskade)
  ├─ [6] Owner-Only Tool Policy
  ├─ [7] System Prompt Build (Skills, Memory, Safety, Tools, Reasoning Hint)
  ├─ [8] Session Tool-Result Guard (monkey-patched appendMessage)
  │       ├─ sanitizeToolCallInputs (drop unknown tool names)
  │       ├─ capToolResultSize (HARD_MAX Chars)
  │       ├─ orphaned tool_use → synthetische tool_result ← 🔴 FEHLT
  │       └─ before_message_write hook (blockierbar)
  ├─ [9] History Sanitisierung (sanitizeSessionHistory, limitHistoryTurns,
  │       dropThinkingBlocks, pruneProcessedHistoryImages)
  ├─ [10] Tool-Result Context Guard (PRE-LLM)  ← 🔴 FEHLT
  │       CONTEXT_INPUT_HEADROOM_RATIO = 0.75
  │       SINGLE_TOOL_RESULT_CONTEXT_SHARE = 0.5
  └─ [11] LLM Call

[subscribeEmbeddedPiSession]
  ├─ Message-Stream mit stripBlockTags, Monotonie-Guard, Reply-Directives
  ├─ Tool-Events mit Mutation-Tracking, after_tool_call hook
  └─ Compaction-Events mit Retry-Resolution

[Context-Overflow Recovery]
  ├─ stripToolResultDetails() (Security)           ← 🟠 FEHLT
  ├─ identifierPolicy="strict" (UUID/hash preserve) ← 🟠 FEHLT
  ├─ chunked summarization × retry(3, 500ms–5s)    ← 🟠 Schwächer
  └─ truncateOversizedToolResultsInSession (Fallback)

[Final Payload]
  buildEmbeddedRunPayloads()
  → Delivers to caller
```

---

## Evidence-basiertes Delta

### Legende

| Symbol | Bedeutung |
|--------|-----------|
| 🔴 | Kritisch — kann zu falschen/fehlenden Antworten führen |
| 🟠 | Hoch — Robustheitslücke, greift unter Last |
| 🟡 | Mittel — Verbesserung, nicht sofort critical |

---

### Gap 1 — Pre-LLM Tool-Result Context Guard  🔴

**openclaw-Verhalten:**  
_Vor_ dem LLM-Call wird das Context-Budget geprüft:
```typescript
// tool-result-context-guard.ts
CONTEXT_INPUT_HEADROOM_RATIO = 0.75  // 25% Headroom für LLM-Antwort
SINGLE_TOOL_RESULT_CONTEXT_SHARE = 0.5  // max 50% für EIN Tool-Result

// Überschreitende Results werden ersetzt durch:
"[compacted: tool output removed to free context]"
// oder
"[truncated: output exceeded context limit]"
```

**ai-agent-starter-kit aktuell:**  
`_smart_truncate()` in `ToolExecutionManager` kürzt post-execution per `result_max_chars`.  
Diese Grenze ist **absolut**, nicht relativ zum verfügbaren Context-Fenster.  
Ein 50k-Zeichen-Result mit 8k Context-Window wird auf `result_max_chars` (z. B. 8000) gekürzt —  
das reicht aber immer noch, um 50%+ des Fensters zu blockieren wenn der Plan + History bereits Platz fordern.

**Symptom:** LLM bekommt >90% seines Fensters mit Tool-Output belegt, hat kaum Raum für Synthesis  
→ verkürzte/abgebrochene Antworten, Timeout-Cascades.

**Fix — Neues Modul `ToolResultContextGuard`:**

```python
# backend/app/services/tool_result_context_guard.py

CONTEXT_INPUT_HEADROOM_RATIO = 0.75   # max. 75% für Input
SINGLE_TOOL_RESULT_CONTEXT_SHARE = 0.50  # max. 50% für EIN Result

@dataclass
class ToolResultContextGuardResult:
    modified: bool
    original_chars: int
    reduced_chars: int
    reason: str  # "context_budget" | "single_result_share" | "none"

def enforce_tool_result_context_budget(
    *,
    tool_results: str,
    context_window_tokens: int,
    chars_per_token_estimate: float = 4.0,
) -> tuple[str, ToolResultContextGuardResult]:
    """
    Kürzt tool_results auf CONTEXT_INPUT_HEADROOM_RATIO des verfügbaren
    Context-Fensters. Ein einzelnes Result darf nie mehr als
    SINGLE_TOOL_RESULT_CONTEXT_SHARE belegen.
    """
    max_input_chars = int(
        context_window_tokens * chars_per_token_estimate * CONTEXT_INPUT_HEADROOM_RATIO
    )
    max_single_chars = int(
        context_window_tokens * chars_per_token_estimate * SINGLE_TOOL_RESULT_CONTEXT_SHARE
    )
    original = tool_results
    # 1. Kürze einzelne Results die mehr als single-share belegen
    tool_results = _truncate_oversized_single_results(tool_results, max_single_chars)
    # 2. Kürze Gesamtvolumen auf max_input_chars
    if len(tool_results) > max_input_chars:
        tool_results = (
            tool_results[:max_input_chars]
            + f"\n\n[truncated: tool output exceeded context budget ({len(original)} chars)]"
        )
    modified = tool_results != original
    return tool_results, ToolResultContextGuardResult(
        modified=modified,
        original_chars=len(original),
        reduced_chars=len(tool_results),
        reason="context_budget" if modified else "none",
    )
```

**Integration in `agent.py` (`run()`):**
```python
# Nach Tool-Loop, vor Synthesis
if settings.tool_result_context_guard_enabled:
    from app.services.tool_result_context_guard import enforce_tool_result_context_budget
    profile = model_registry.resolve(model_id)
    tool_results, guard_result = enforce_tool_result_context_budget(
        tool_results=tool_results or "",
        context_window_tokens=profile.max_context,
    )
    if guard_result.modified:
        await self._emit_lifecycle(send_event, stage="tool_result_context_guard_applied",
            request_id=request_id, session_id=session_id,
            details={"original_chars": guard_result.original_chars,
                     "reduced_chars": guard_result.reduced_chars})
```

**Config:**
```python
# config.py
tool_result_context_guard_enabled: bool = _parse_bool_env("TOOL_RESULT_CONTEXT_GUARD_ENABLED", True)
tool_result_context_headroom_ratio: float = float(
    os.getenv("TOOL_RESULT_CONTEXT_HEADROOM_RATIO", "0.75")
)
tool_result_single_share: float = float(
    os.getenv("TOOL_RESULT_SINGLE_SHARE", "0.50")
)
```

---

### Gap 2 — Orphaned Tool-Call Synthetic Repair  🔴

**openclaw-Verhalten:**  
`installSessionToolResultGuard()` patcht `appendMessage` und erkennt `tool_use`-Blocks ohne
korrespondierendes `tool_result`. Für jeden orphaned Call wird ein synthetisches `tool_result`
mit `isError=true` generiert — bevor die History dem LLM gezeigt wird.

```typescript
// session-tool-result-guard.ts
// orphaned tool_results (kein passendes tool_use) →
// flushPendingToolResults() synthetisiert fehlende Results
// → verhindert Anthropic API 400 "roles must alternate"
```

**ai-agent-starter-kit aktuell:**  
Kein Analogon. Ein abgebrochener `spawn_subrun` oder ein Timeout-abgebrochenes
`run_command` kann einen ungebundenen `tool_use`-Block in der History hinterlassen.
Die nächste LLM-Anfrage führt zu einem 400-Fehler (role_ordering), der im
`run()`-Loop als `"role_ordering"`-Error erkannt wird — aber nur mit einem Hard-Return,
ohne Repair-Versuch.

**Symptom:** Ein einzelner Tool-Timeout bricht die gesamte Session-History
→ nachfolgende Interaktionen im selben Session scheitern alle mit 400.

**Fix — `repairOrphanedToolCalls()` in `MemoryStore`:**

```python
# backend/app/memory.py

ORPHAN_SYNTHETIC_RESULT = "[tool execution was interrupted — no result available]"

def repair_orphaned_tool_calls(self, session_id: str) -> int:
    """
    Prüft die Session-History auf tool_use-Blocks ohne korrespondierendes
    tool_result und injiziert synthetische Fehler-Results.
    Gibt Anzahl reparierter Orphans zurück.
    """
    with self._lock:
        items = list(self._store.get(session_id, deque()))
        repaired = 0
        # Einfaches Pairing über sequentiellen Scan
        pending_tool_calls: set[str] = set()
        repaired_items: list[MemoryItem] = []
        for item in items:
            if item.role == "assistant" and '"tool_calls"' in item.content:
                # Extrahiere tool_call-IDs aus dem serialisierten Content
                ids = re.findall(r'"id":\s*"([^"]+)"', item.content)
                pending_tool_calls.update(ids)
                repaired_items.append(item)
            elif item.role.startswith("tool:"):
                # tool_result — matched against pending
                call_id = _extract_tool_call_id(item.content)
                if call_id and call_id in pending_tool_calls:
                    pending_tool_calls.discard(call_id)
                repaired_items.append(item)
            else:
                # Wenn beim nächsten non-tool-result user-msg noch pending_calls →
                # synthetische Results einfügen
                if pending_tool_calls and item.role == "user":
                    for orphan_id in pending_tool_calls:
                        synthetic = MemoryItem(
                            role=f"tool:__synthetic__",
                            content=json.dumps({
                                "tool_call_id": orphan_id,
                                "role": "tool",
                                "content": ORPHAN_SYNTHETIC_RESULT,
                            }),
                        )
                        repaired_items.append(synthetic)
                        repaired += 1
                    pending_tool_calls.clear()
                repaired_items.append(item)
        if repaired > 0:
            self._store[session_id] = deque(repaired_items, maxlen=self._max_items)
        return repaired
```

**Integration in `agent.py` (`run()`):**
```python
# Am Beginn von run(), nach memory.add(session_id, "user", ...)
orphans_repaired = memory.repair_orphaned_tool_calls(session_id)
if orphans_repaired > 0:
    await self._emit_lifecycle(send_event, stage="orphaned_tool_calls_repaired",
        request_id=request_id, session_id=session_id,
        details={"count": orphans_repaired})
```

---

### Gap 3 — Compaction Identifier Preservation  🟠

**openclaw-Verhalten:**  
```typescript
// compaction.ts — identifierPolicy="strict" (default)
// MUST PRESERVE:
// - All UUIDs (exactly as-is)
// - All cryptographic hashes
// - All API keys and tokens
// - All hostnames and URLs
// - All version numbers (semver, timestamps)
```

Die Compaction-Instructions enthalten explizit:
```
IDENTIFIER PRESERVATION (strict mode):
Keep these EXACTLY as written in the source: UUIDs, hashes,
API keys, hostnames, file paths with commit shas, version numbers.
```

**ai-agent-starter-kit aktuell:**  
Compaction über `prompt_compaction_ratio=0.7` kürzt den Context-String.
Keine explizite Identifier-Preservation-Instruktion. Ein Subrun-result mit
`spawned_subrun_id=abc-123-def-456` könnte nach Compaction zu einem anderen
(halluzinierten) Wert werden — der dann den `orchestration_evidence_missing` Gate
falsch triggert.

**Symptom:** Nach Compaction stimmen `subrun_id`, `run_id`, `session_id` nicht mehr
mit tatsächlichen IDs überein → nachfolgende Lookups scheitern, Orchestration Gates
feuern fälschlicherweise.

**Fix — Identifier-preserving Compaction Prompt:**

```python
# backend/app/services/context_reducer.py (oder wo Compaction-Prompt gebaut wird)

IDENTIFIER_PRESERVATION_INSTRUCTIONS = """
IDENTIFIER PRESERVATION (strict — do NOT modify these):
  - UUIDs (8-4-4-4-12 format, e.g. a1b2c3d4-e5f6-...)
  - spawned_subrun_id= values
  - run_id= values
  - session_id values
  - terminal_reason= values (subrun-complete, subrun-error, ...)
  - File paths and commit hashes
  - API keys and tokens
  - Hostnames and URLs
Copy these byte-for-byte from the source. Never paraphrase identifiers.
"""

COMPACTION_SUMMARY_INSTRUCTIONS = """
Summarize this conversation context. Preserve all active tasks,
decisions made, progress markers (e.g. '5 of 17 completed'),
TODOs, open questions, and commitments.

""" + IDENTIFIER_PRESERVATION_INSTRUCTIONS
```

**Integration in `ContextReducer.reduce()`:**
```python
def _build_compaction_prompt(self, context: str, *, identifier_preservation: bool = True) -> str:
    instructions = COMPACTION_SUMMARY_INSTRUCTIONS if identifier_preservation else COMPACTION_SUMMARY_INSTRUCTIONS_MINIMAL
    return f"{instructions}\n\n---\n\n{context}"
```

---

### Gap 4 — Subagent-Announce als Tool-Result (Issue B)  🔴

**openclaw-Verhalten:**  
```typescript
// subagent-announce-dispatch.ts + subagent-announce-queue.ts
// wenn Child abschließt:
// → subagentAnnounceQueue.enqueue(parentSessionKey, announcePayload)
// → Dispatch via sessions_announce → erscheint als Tool-Result beim Parent
```

**ai-agent-starter-kit aktuell:**  
`subrun_announce`-Event erreicht den Parent als Lifecycle-Event (WebSocket),
aber NICHT als Tool-Result in `tool_results`-String. Der `orchestration_evidence_missing`
Gate kann deshalb für fire-and-forget-Spawns niemals positiv sein — er feuert immer.

**Symptom:** Jeder `mode="run"` (fire-and-forget) Spawn produziert zwingend
einen `orchestration_evidence_missing`-Hit → Antwort wird durch Gate-Text ersetzt,
obwohl der Subrun evtl. erfolgreich war.

**Fix — Announce-Callback in `SubrunLane`:**

```python
# backend/app/main.py — in _initialize_runtime_components()

async def _on_subrun_complete_announce(
    *,
    parent_session_id: str,
    run_id: str,
    child_agent_id: str,
    terminal_reason: str,
    child_output: str | None,
) -> None:
    """
    Wird vom SubrunLane gefeuert wenn ein Child-Run terminiert.
    Injiziert ein synthetisches 'announce' Tool-Result in die Parent-Session,
    damit orchestration_evidence_missing korrekt entscheiden kann.
    """
    announce_text = (
        f"[subrun_announce] spawned_subrun_id={run_id} "
        f"agent_id={child_agent_id} terminal_reason={terminal_reason}"
    )
    if child_output:
        announce_text += f"\n[child_output_summary] {child_output[:500]}"

    parent_memory = components.agent.memory
    parent_memory.add(parent_session_id, "tool:spawn_subrun_announce", announce_text)

components.subrun_lane.set_completion_callback(_on_subrun_complete_announce)
```

**Gate-Anpassung in `agent.py`:**
```python
def _has_orchestration_evidence(self, tool_results: str | None) -> bool:
    tr = tool_results or ""
    # Fix 4 aus Issue-0008: subrun-complete via mode="wait"
    if "spawned_subrun_id=" in tr and "subrun-complete" in tr:
        return True
    # NEU: fire-and-forget via announce-callback
    if "subrun_announce" in tr and "subrun-complete" in tr:
        return True
    return False
```

---

### Gap 5 — Context Window Hard Min zu niedrig  🟠

**openclaw-Verhalten:**
```typescript
CONTEXT_WINDOW_HARD_MIN_TOKENS = 16_000  // → FailoverError
CONTEXT_WINDOW_WARN_BELOW_TOKENS = 32_000  // → log.warn
```

**ai-agent-starter-kit aktuell:**
```python
# config.py
context_window_warn_below_tokens: int = 8000   # zu niedrig
context_window_hard_min_tokens: int = 4000     # viel zu niedrig
```

Mit 4000 Tokens verbleibendem Fenster ist eine qualitativ hochwertige Synthesis
(inkl. Tool-Results) nahezu unmöglich. Selbst der `general`-Task-Type braucht
den Plan + User Message + mind. einen Tool-Result-Auszug.

**Fix:**
```python
# config.py — Defaults anpassen
context_window_warn_below_tokens: int = int(
    os.getenv("CONTEXT_WINDOW_WARN_BELOW_TOKENS", "24000")   # war 8000
)
context_window_hard_min_tokens: int = int(
    os.getenv("CONTEXT_WINDOW_HARD_MIN_TOKENS", "12000")     # war 4000
)
```

---

### Gap 6 — Session History Repair bei Role-Ordering-Fehlern  🟠

**openclaw-Verhalten:**  
Wenn der LLM-Provider einen `"incorrect role information"` bzw. `"roles must alternate"` Fehler
liefert, greift in openclaw `run.ts` ein spezieller Branch:
```typescript
// Error-Classification in run.ts
if (/incorrect role information|roles must alternate/.test(errorText)) {
    return { kind: "role_ordering" };
}
// → führt zu neuem Attempt mit sanitizeSessionHistory()
```

**ai-agent-starter-kit aktuell:**  
`"role_ordering"` ist als Error-Kind bekannt (recovery_strategy.py), aber es gibt
keine automatische History-Repair vor dem Retry. Der nächste Attempt verwendet
dieselbe fehlerhafte History → gleicher Fehler → Run scheitert.

**Fix — `sanitize_session_history()` in `MemoryStore`:**

```python
# backend/app/memory.py

def sanitize_session_history(self, session_id: str) -> int:
    """
    Repariert ungültige Turn-Strukturen:
    1. Stellt sicher dass user/assistant sich abwechseln
    2. Entfernt überschüssige assistant-Turns am Ende
    3. Gibt Anzahl entfernter Items zurück
    """
    with self._lock:
        items = list(self._store.get(session_id, deque()))
        original_len = len(items)
        # Nur user/assistant/plan-Rollen für Turn-Validierung relevant
        valid_items = []
        last_conversation_role: str | None = None
        for item in items:
            if item.role in ("user", "assistant"):
                if item.role == last_conversation_role:
                    # Duplikat-Rolle: überspringen (Drop)
                    continue
                last_conversation_role = item.role
            valid_items.append(item)
        self._store[session_id] = deque(valid_items, maxlen=self._max_items)
        return original_len - len(valid_items)
```

**Integration in `agent.py` beim `role_ordering`-Retry:**  
```python
# In orchestrator/pipeline_runner.py (wo role_ordering error behandelt wird)
# Vor erneutem run():
repaired = components.agent.memory.sanitize_session_history(session_id)
if repaired > 0:
    await emit_lifecycle("session_history_sanitized", {"removed_items": repaired})
```

---

### Gap 7 — Compaction Retry-Jitter  🟠

**openclaw-Verhalten:**
```typescript
// summarizeChunks() in compaction.ts
const summary = await retryAsync(
    () => generateSummary(chunk, model, ...),
    { attempts: 3, minDelayMs: 500, maxDelayMs: 5000, jitter: 0.2 }
);
```

3 Versuche pro Chunk mit 500ms–5s exponential backoff + 20% Jitter.

**ai-agent-starter-kit aktuell:**
```python
# config.py
pipeline_runner_prompt_compaction_max_attempts: int = 1  # einzelner Versuch
```

Wenn der LLM-Provider beim Compaction-Call 429/503 zurückgibt, schlägt Compaction sofort
fehl → Context-Overflow Recovery-Chain abbricht → Run scheitert.

**Fix:**
```python
# config.py
pipeline_runner_prompt_compaction_max_attempts: int = int(
    os.getenv("PIPELINE_RUNNER_PROMPT_COMPACTION_MAX_ATTEMPTS", "3")  # war 1
)
pipeline_runner_prompt_compaction_retry_base_delay: float = float(
    os.getenv("PIPELINE_RUNNER_PROMPT_COMPACTION_RETRY_BASE_DELAY", "0.5")
)
pipeline_runner_prompt_compaction_retry_max_delay: float = float(
    os.getenv("PIPELINE_RUNNER_PROMPT_COMPACTION_RETRY_MAX_DELAY", "5.0")
)
```

**Retry-Loop im Compaction-Service:**
```python
# backend/app/services/context_reducer.py

async def _compact_with_retry(
    self,
    context: str,
    *,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 5.0,
) -> str:
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await self._compact_once(context)
        except (LlmClientError, asyncio.TimeoutError) as e:
            last_error = e
            if attempt < max_attempts - 1:
                delay = min(base_delay * (2 ** attempt), max_delay)
                delay += random.uniform(0, delay * 0.2)  # 20% jitter
                await asyncio.sleep(delay)
    raise last_error  # type: ignore[misc]
```

---

### Gap 8 — Compaction Security: Tool-Result-Details Strip  🟠

**openclaw-Verhalten:**
```typescript
// compaction.ts
// SECURITY: stripToolResultDetails() bevor Summary-Prompt gebaut wird
const safeMessages = stripToolResultDetails(params.messages);
// → entfernt rohe API-Responses, Credentials aus Tool-Results
// → verhindert dass Compaction-Summary Secrets einbettet
```

**ai-agent-starter-kit aktuell:**  
Compaction sendet den vollen Context-String an den LLM, ohne Pre-Sanitisierung.  
Ein `[web_fetch]`-Result das API-Keys in den Response-Headern enthielt, oder ein  
`[run_command]`-Output mit Credentials wird 1:1 in den Compaction-Prompt übergeben.

**Symptom:** Compaction-Summaries können Secrets einbetten, die dann dauerhaft
in der Session-History verbleiben und bei künftigen Prompts mitgesendet werden.

**Fix — `strip_sensitive_tool_results()` vor Compaction:**

```python
# backend/app/services/context_reducer.py

import re

_SECRET_PATTERNS = [
    # Bearer Token / API Keys  
    r'(Bearer\s+)[A-Za-z0-9\-_\.]{20,}',
    r'(api[_\-]?key["\s:=]+)["\']?[A-Za-z0-9\-_\.]{16,}',
    r'(Authorization:\s*)[^\n]{10,}',
    # Private Keys
    r'-----BEGIN [A-Z ]+KEY-----.*?-----END [A-Z ]+KEY-----',
    # Passwords
    r'(password["\s:=]+)["\']?[^\s"\']{8,}',
]

def strip_sensitive_tool_results(context: str) -> str:
    """Entfernt potenziell sensible Daten aus Tool-Results vor dem Compaction-LLM-Call."""
    result = context
    for pattern in _SECRET_PATTERNS:
        result = re.sub(pattern, r'\1[REDACTED]', result, flags=re.IGNORECASE | re.DOTALL)
    return result
```

---

### Gap 9 — Tool Mutation Error Tracking  🟡

**openclaw-Verhalten:**
```typescript
// handlers/tools.ts — handleToolExecutionEnd()
if (isToolError) {
    ctx.state.lastToolError = { toolName, meta, error, mutatingAction };
} else if (lastToolError?.mutatingAction && isSameToolMutationAction(lastToolError, current)) {
    ctx.state.lastToolError = undefined; // Cleared wenn gleiche Mutation erfolgreich
}
```

Wenn z. B. `write_file` beim ersten Versuch fehlschlägt und beim Retry erfolgreich ist,
wird `lastToolError` gecleart — der Evidence Gate sieht kein Fehler-State mehr.

**ai-agent-starter-kit aktuell:**  
`_classify_tool_results_state()` schaut nur auf den finalen `tool_results`-String.
Wenn ein späterer `[ok]` Entry nach einem `[error]` kommt, ist der State `"usable"`.
Aber `_has_implementation_evidence()` und `_has_orchestration_evidence()` schauen
nur auf Keyword-Presence, nicht auf Reihenfolge.

**Symptom:** Ein fehlgeschlagener `write_file` gefolgt von einem erfolgreichen `write_file`
(Retry via Replan) wird korrekt klassifiziert. Aber: ein fehlgeschlagener
`spawn_subrun(mode="wait")` gefolgt von einem erfolgreichen zeigt `subrun-error` UND
`subrun-complete` im `tool_results` → `_has_orchestration_evidence()` gibt `True` zurück
(korrekt), aber die Synthesizer-task_type-Resolution in Step 2 des Evidence-First-Checks
matcht auf `"subrun-error"` zuerst → `"orchestration_failed"` statt `"orchestration"`.

**Fix — Geordneter Precedence-Check in `_resolve_synthesis_task_type()`:**

```python
def _resolve_synthesis_task_type(self, *, user_message: str, tool_results: str) -> str:
    if self._requires_hard_research_structure(user_message):
        return "hard_research"
    if "spawned_subrun_id=" in (tool_results or ""):
        tr = tool_results or ""
        # WICHTIG: Reihenfolge prüfen — letzter terminaler Status gewinnt
        # Suche das LETZTE Vorkommen eines terminal_reason
        terminal_statuses = [
            (m.start(), m.group(1))
            for m in re.finditer(
                r'terminal_reason=(subrun-complete|subrun-error|subrun-timeout|subrun-cancelled|subrun-running|subrun-accepted)',
                tr
            )
        ]
        if terminal_statuses:
            # Der zeitlich letzte Status ist ausschlaggebend
            _, last_status = max(terminal_statuses, key=lambda x: x[0])
            if last_status == "subrun-complete":
                return "orchestration"
            if last_status in ("subrun-error", "subrun-timeout", "subrun-cancelled"):
                return "orchestration_failed"
            return "orchestration_pending"
        # Fallback: altes Verhalten
        if "subrun-complete" in tr:
            return "orchestration"
        if any(s in tr for s in ("subrun-error", "subrun-timeout", "subrun-cancelled")):
            return "orchestration_failed"
        return "orchestration_pending"
    if self._is_subrun_orchestration_task(user_message):
        return "orchestration"
    if self._is_file_creation_task(user_message):
        return "implementation"
    if self._is_web_research_task(user_message):
        return "research"
    return "general"
```

---

### Gap 10 — Tool Policy Granularität  🟡

**openclaw-Verhalten (7-Stufen-Kaskade):**
```
1. tools.profile.{profile}     → Profil-spezifische Policy
2. tools.byProvider.profile    → Provider-Profil-Policy
3. tools.allow                 → Global-Allowlist
4. tools.byProvider.allow      → Provider-Global-Policy
5. agents.{id}.tools.allow     → Agent-spezifische Policy
6. agents.{id}.tools.byProvider → Agent-Provider-Policy
7. group tools.allow           → Gruppen-Policy (expandiert plugin:groups)
```

**ai-agent-starter-kit aktuell:**  
Flache 3-Key-Policy: `allow / deny / also_allow` auf Request-Ebene.
Keine Per-Agent, keine Per-Provider, keine Profil-basierte Kaskade.

**Symptom:** Für Multi-Agent-Setups (Head → Coder → Reviewer) kann die Policy nicht
unterschiedlich pro Agent gesetzt werden. Ein deny für `run_command` gilt
global für alle Sub-Agents, auch wenn nur der Coder es braucht.

**Fix — Erweitertes `ToolPolicyDict` mit agent_policies:**

```python
# backend/app/tool_policy.py

class AgentToolPolicyEntry(TypedDict, total=False):
    allow: list[str]
    deny: list[str]
    also_allow: list[str]

class ExtendedToolPolicyDict(TypedDict, total=False):
    allow: list[str]           # Global Allowlist
    deny: list[str]            # Global Denylist
    also_allow: list[str]      # Global Additiv
    agents: dict[str, AgentToolPolicyEntry]  # Per-Agent Override

def resolve_effective_tools_for_agent(
    global_policy: ToolPolicyDict | None,
    agent_id: str,
    base_tools: set[str],
) -> set[str]:
    """
    Wendet global policy + agent-spezifischen Override an.
    Agent-Override gewinnt über global-Policy für genannte Tools.
    """
    # ... Implementation
```

---

## Implementierungs-Reihenfolge (Priorisiert)

| Prio | Gap | Aufwand | Impact |
|------|-----|---------|--------|
| 1 | **Gap 1** — Pre-LLM Context Guard | M (1 Datei neu, 1 Integration) | Synthesis-Qualität 🔴 |
| 2 | **Gap 2** — Orphaned Tool-Call Repair | M (MemoryStore + Integration) | Session-Kontinuität 🔴 |
| 3 | **Gap 4** — Announce-Callback Pipeline | L (SubrunLane + main.py) | Orchestration-Korrektheit 🔴 |
| 4 | **Gap 8** — Compaction Security Strip | S (1 Funktion, 1 Integration) | Secrets-Leak 🟠 |
| 5 | **Gap 3** — Identifier Preservation | S (Prompt-Ergänzung) | Orchestration-Stabilität 🟠 |
| 6 | **Gap 5** — Context Window Defaults | XS (Config-Änderung) | Synthese-Qualität 🟠 |
| 7 | **Gap 7** — Compaction Retry | S (Retry-Loop + Config) | Resilienz unter Last 🟠 |
| 8 | **Gap 6** — History Sanitize bei Retry | M (MemoryStore + Integration) | Fehler-Recovery 🟠 |
| 9 | **Gap 9** — Mutation Error Tracking | S (agent.py, 1 Methode) | Korrektheit bei Retries 🟡 |
| 10 | **Gap 10** — Policy Kaskade | L (TypedDict + Resolver) | Multi-Agent-Control 🟡 |

---

## Vollständiges Pipeline-Bild nach diesen Fixes

```
User Message
      │
      ▼
[1] Guardrails + Tool Policy Resolution
      │   agent.py: _validate_guardrails, _resolve_effective_allowed_tools
      │
      ▼
[2] Orphaned Tool-Call Repair                              ← NEU Gap 2
      │   memory.repair_orphaned_tool_calls(session_id)
      │   → synthetische tool_results für verwaiste tool_uses
      │   → verhindert 400-Fehler bei nachfolgenden LLM-Calls
      │
      ▼
[3] Planning (PlannerAgent)
      │
      ▼
[4] Tool Execution Loop (ToolExecutionManager)
      │   ├─ [4a] Capability Preselection (registry verdrahtet — Fix 5, Issue-0008)
      │   ├─ [4b] Skill Retrieval / Grounding
      │   ├─ [4c] Intent Detection → Tool Selection
      │   ├─ [4d] spawn_subrun Ausführung (mode="wait" wartet — Fix 1, Issue-0008)
      │   │       → Announce-Callback bei fire-and-forget ← NEU Gap 4
      │   └─ [4e] Tool Result Classification
      │
      ▼
[5] Pre-LLM Tool-Result Context Guard                     ← NEU Gap 1
      │   enforce_tool_result_context_budget(tool_results, max_context)
      │   CONTEXT_INPUT_HEADROOM_RATIO = 0.75
      │   SINGLE_TOOL_RESULT_CONTEXT_SHARE = 0.50
      │   → Überschreitende Results werden auf Budget gekürzt
      │   → emit "tool_result_context_guard_applied"
      │
      ▼
[6] Task-Type Resolution                                   (Fix 2, Issue-0008)
      │   agent.py: _resolve_synthesis_task_type()
      │   NEU: Letzter terminal_reason gewinnt (Ordered Precedence) ← Gap 9
      │
      ▼
[7] Synthesis (SynthesizerAgent)                          (Fix 3, Issue-0008)
      │   → Section-Contracts per Task-Typ
      │   → Self-Check + Repair-Pass
      │   → Reflection Pass
      │
      ▼
[8] Reply Shaping + Evidence Gates
      │   ├─ implementation_evidence_missing              (Fix 4, Issue-0008)
      │   └─ orchestration_evidence_missing               (Fix 4, Issue-0008)
      │       NEU: auch via announce-callback erhaltene Evidenz ← Gap 4
      │
      ▼
[9] Verification + Final Output
      │
      ▼
[C] Compaction (bei Context-Overflow)
      │   ├─ strip_sensitive_tool_results() (Security)    ← NEU Gap 8
      │   ├─ Identifier-Preservation-Instructions         ← NEU Gap 3
      │   ├─ Chunked Summarization × retry(3, 500ms–5s)   ← NEU Gap 7
      │   └─ truncate_oversized als Fallback
```

---

## Test-Nachweis (neu zu schreiben)

```python
# Gap 1 — Pre-LLM Context Guard
def test_tool_result_context_guard_clips_oversized_result():
    """Ein 200k-Result bei 8k-Context-Window wird auf 75% = 6k Chars geclippt."""

def test_tool_result_context_guard_single_share_enforced():
    """Ein einzelnes Result über 50% wird auf 50% geclippt bevor Gesamtbudget zählt."""

def test_tool_result_context_guard_no_op_for_small_result():
    """Ein Result das Budget nicht überschreitet wird nicht verändert."""

# Gap 2 — Orphaned Repair
def test_orphaned_tool_call_synthetic_result_injected():
    """Eine Session mit orphaned tool_use bekommt synthetisches tool_result."""

def test_orphaned_tool_call_repair_does_not_touch_matched_calls():
    """Eine Session ohne Orphans wird nicht verändert."""

# Gap 3 — Identifier Preservation
def test_compaction_prompt_contains_identifier_preservation_instructions():
    """Compaction-Prompt enthält UUID/hash preservation Instruktion."""

# Gap 4 — Announce-Callback
def test_subrun_complete_announce_injected_as_tool_result():
    """Nach Subrun-Completion wird announce in Parent-Memory injiziert."""

def test_orchestration_evidence_gate_passes_via_announce():
    """_has_orchestration_evidence() ist True wenn announce mit subrun-complete."""

# Gap 5 — Context Window
def test_context_window_hard_min_default_is_12000():
    """Default-Wert für CONTEXT_WINDOW_HARD_MIN_TOKENS ist 12000."""

# Gap 7 — Compaction Retry
def test_compaction_retries_on_llm_rate_limit():
    """Compaction versucht max. 3x bei 429-Fehler mit Backoff."""

# Gap 9 — Ordered Precedence
def test_last_terminal_reason_wins_for_multiple_subruns():
    """subrun-error + späteres subrun-complete → task_type="orchestration"."""
```

---

## Veränderte Dateien (Zusammenfassung)

| Datei | Art | Gap |
|-------|-----|-----|
| `backend/app/services/tool_result_context_guard.py` | **NEU** | Gap 1 |
| `backend/app/memory.py` | Erweitern | Gap 2, Gap 6 |
| `backend/app/agent.py` | Erweitern | Gap 1 Integration, Gap 2 Integration, Gap 4 Gate-Update, Gap 9 ordered precedence |
| `backend/app/main.py` | Erweitern | Gap 4 Announce-Callback |
| `backend/app/services/context_reducer.py` | Erweitern | Gap 3, Gap 7, Gap 8 |
| `backend/app/config.py` | Config-Defaults | Gap 5, Gap 7 |
| `backend/app/tool_policy.py` | Optionale Erweiterung | Gap 10 |
| `backend/tests/test_tool_result_context_guard.py` | **NEU** | Gap 1 |
| `backend/tests/test_memory.py` | Erweitern | Gap 2, Gap 6 |
| `backend/tests/test_agent_orchestration.py` | Erweitern | Gap 4, Gap 9 |
