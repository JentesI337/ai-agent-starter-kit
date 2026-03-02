# Backend Refactoring Plan — Detailliert & Priorisiert

**Basiert auf**: Deep Quality Review & Architectural Audit (2. März 2026)  
**Gesamtbewertung vorher**: 6.6/10  
**Zielbewertung nach Refactoring**: 8.5+/10  
**Scope**: 75 Python-Module, ~616 KB Source Code, `agent.py` (2.771 LOC God-Class)

---

## Inhaltsverzeichnis

1. [Strategie](#1-strategie)
2. [Phase 0 — Sicherheitskritische Sofortmaßnahmen (Woche 1)](#2-phase-0--sicherheitskritische-sofortmaßnahmen-woche-1)
3. [Phase 1 — HeadAgent God-Class aufbrechen (Wochen 1–2)](#3-phase-1--headagent-god-class-aufbrechen-wochen-12)
4. [Phase 2 — Test-Coverage für kritische Pfade (Wochen 2–3)](#4-phase-2--test-coverage-für-kritische-pfade-wochen-23)
5. [Phase 3 — Architektur-Bereinigung (Wochen 3–4)](#5-phase-3--architektur-bereinigung-wochen-34)
6. [Phase 4 — Pipeline-Runner Refactoring (Wochen 4–5)](#6-phase-4--pipeline-runner-refactoring-wochen-45)
7. [Phase 5 — Feature-Verbesserungen (Wochen 5–8)](#7-phase-5--feature-verbesserungen-wochen-58)
8. [Risikoanalyse & Abhängigkeiten](#8-risikoanalyse--abhängigkeiten)
9. [Erfolgsmetriken](#9-erfolgsmetriken)
10. [Dateistruktur nach Refactoring](#10-dateistruktur-nach-refactoring)

---

## 1. Strategie

### 1.1 Zwischenstand (02.03.2026)

**Statusüberblick**
- ✅ **Phase 0** umgesetzt: `web_fetch` Content-Safety (Content-Length/Content-Type + Download-Limit) und Reduktion von `_is_file_creation_task` False-Positives.
- ✅ **Phase 1a–1g** umgesetzt: `tool_arg_validator`, `tool_registry`, `intent_detector`, `reply_shaper`, `tool_execution_manager`, `action_parser`, `action_augmenter` sind extrahiert und in `HeadAgent` delegiert.
- ✅ `_execute_tools` ist auf schlanke Delegation reduziert; zentrale Orchestrierung liegt in `ToolExecutionManager.execute(...)`.
- ✅ Fokus-Regressionen grün (zuletzt):
    - 49 passed (`test_tool_execution_manager*`, `test_tool_selection_offline_eval`)
    - 20 passed (Service-Suites: Validator/Parser/Intent/Reply/Registry)
    - 51 passed (inkl. neuem `test_action_augmenter`)

**Offen / Nächster Schritt**
- ✅ **Phase 2.1** umgesetzt: `tests/test_tool_call_gatekeeper.py` ergänzt (Preparation, Policy-Override-Candidates, Generic-Repeat, Ping-Pong, Poll-No-Progress, Summary).
- ✅ **Phase 2.2** umgesetzt: `tests/test_tools_path_traversal.py` ergänzt (`_resolve_workspace_path` inkl. `..`-Escape, absolute Pfade, Backslash-Traversal).
- ✅ **Phase 2.3** umgesetzt: `tests/test_pipeline_runner_recovery.py` ergänzt (`_resolve_recovery_strategy`, Prompt-Compaction, Payload-Truncation, Priority-Flip, Signal/Feedback-Reihenfolge).
- ✅ Phase-2-neue Tests grün: 26 passed (`test_tool_call_gatekeeper.py`, `test_tools_path_traversal.py`, `test_pipeline_runner_recovery.py`).
- ✅ **Phase 2.4** umgesetzt: Coverage-Gate auf Default-Threshold-Profile standardisiert (`--use-default-thresholds`) in CI (`.github/workflows/backend-tests.yml`) und lokalen Runnern (`start-test.ps1`, `start-test.sh`), inkl. README-Dokumentation.
- ✅ **Phase 3.2 (teilweise)** umgesetzt: `contracts/schemas.py` dedupliziert durch `AgentInput` + Backwards-Compatible Aliases (`HeadAgentInput`, `CoderAgentInput`, `HeadCoderInput`).
- ✅ **Phase 3.2 weitergeführt**: Adapter-Layer auf vereinheitlichtes `AgentInput` umgestellt (`app/agents/head_agent_adapter.py`) bei unveränderten Output-Schemas.
- ✅ **Phase 3.1 (Runtime-Pfad)** umgesetzt: Tool-Step-Ausführung im `HeadAgent` läuft direkt über `_execute_tools` statt über den ToolSelector-Wrapper.
- ✅ **Phase 3.1 weitergeführt**: `ToolSelectorAgent` entkoppelt von persistenter `HeadAgent._execute_tools`-Bindung (kein Constructor-Wiring mehr auf Bound-Method-Callback).
- ✅ **Phase 3.1 Adapter-Pfad** weitergeführt: `HeadAgent._execute_tool_step` nutzt wieder `ToolSelectorAgent.execute(...)`, aber mit Inline-Runner (`execute_tools_fn=self._execute_tools`) statt dauerhaftem Callback-Wiring.
- ✅ **Phase 3.3 gestartet**: `ToolExecutionConfig.from_settings(...)` auf typsicheren `Settings`-Zugriff umgestellt (direkte Settings-Felder statt `getattr`).
- ✅ **Phase 3.3 erweitert**: `app/orchestrator/pipeline_runner.py` nutzt im Recovery-Pfad direkte, typsichere `settings`-Felder statt `getattr(settings, ...)`-Fallbacks.
- ✅ **Phase 3.3 abgeschlossen (PipelineRunner-Scope)**: verbleibende `getattr(settings, ...)`-Zugriffe in `app/orchestrator/pipeline_runner.py` vollständig entfernt (inkl. Priority-Listen und Persistent-Metrics-Decay/Window).
- ✅ **Phase 3.4 gestartet**: `_invoke_tool` auf asynchronen Ausführungspfad umgestellt (`async def` + async/sync Tool-Dispatch), `_run_tool_with_policy` unterstützt kompatibel sowohl async als auch sync `_invoke_tool`-Implementierungen.
- ✅ **Phase 3.4 weitergeführt**: `AgentTooling.web_fetch` auf nativen Async-Pfad (`httpx.AsyncClient` + `aiter_bytes`) umgestellt; `ToolProvider`-Contract entsprechend auf `async def web_fetch(...)` angepasst.
- ✅ **Phase 3.4 robustifiziert**: Tool-Dispatch verarbeitet nun auch den Edge-Case „sync aufgerufene Funktion liefert Awaitable“ (in `_run_tool_with_policy` und `_invoke_tool`) deterministisch als Async-Ergebnis.
- ✅ **Phase 3.5 gestartet**: `ToolProvider`-Protocol ergänzt (`app/contracts/tool_protocol.py`) und `HeadAgent` auf protocol-typisierte Tool-Abhängigkeit umgestellt.
- ✅ **Phase 3.5 abgesichert**: `tests/test_tool_provider_protocol.py` ergänzt (`AgentTooling` erfüllt `ToolProvider` zur Laufzeit via `runtime_checkable`-Protocol).
- ✅ **Phase 4 gestartet (6.4.1 Einstieg)**: `RecoveryContext`-Dataclass in `pipeline_runner.py` eingeführt; `_resolve_recovery_strategy(...)` auf `ctx`-basiertes Interface umgestellt und Call-Site/Tests migriert.
- ✅ **Phase 4.6.4.1 fortgeführt**: Recovery-Priority-Metadaten in dedizierten Helper extrahiert (`_resolve_priority_recovery_metadata`) und duplizierte Logik in `context_overflow`/`truncation_required`-Zweigen entfernt.
- ✅ **Phase 4.6.4.2-Einstieg umgesetzt**: Summary-Emission aus `_run_with_fallback` in Klassenmethode `_emit_recovery_summary_event(...)` extrahiert (erster struktureller Entkernungs-Schnitt).
- ✅ **Phase 4.6.4.2 abgeschlossen**: Recovery-/Fallback-Orchestrierung aus `pipeline_runner.py` weiter entkoppelt in dedizierte Module `app/orchestrator/recovery_strategy.py` und `app/orchestrator/fallback_state_machine.py`; `PipelineRunner` delegiert jetzt an diese Komponenten.
- ✅ **Phase 5.7.5.1 umgesetzt**: intelligentes Result-Truncation in `ToolExecutionManager` (konfigurierbar über `tool_result_smart_truncate_enabled` / `tool_result_max_chars`).
- ✅ **Phase 5.7.5.2 umgesetzt**: optional parallele Ausführung von Read-Only-Tools (`parallel_read_only_enabled`) via `asyncio.gather`.
- ✅ **Phase 5.7.5.3 umgesetzt**: Re-Planning-Loop in `HeadAgent.run()` mit iterativer Planvalidierung und begrenzten Iterationen (`run_max_replan_iterations`).
- ✅ **Phase 5.7.5.4 umgesetzt**: strukturierte Tool-Selection via Function-Calling-Pfad in `LlmClient.complete_chat_with_tools(...)` mit Fallback auf JSON-Selection/Repair.
- ✅ **Phase 5.7.5.5 umgesetzt**: `SqliteStateStore` als cross-process-sicherer Drop-in-StateStore inkl. WAL/busy-timeout und konfigurierbarer Backend-Auswahl (`ORCHESTRATOR_STATE_BACKEND=sqlite`).
- ✅ Regressionsstatus nach Phase-3-Schritten: 50 passed (`test_agent_runtime_reconfigure`, `test_tool_selection_offline_eval`, `test_tool_execution_manager`).
- ✅ Session-Handoff vorbereitet: `backend/SESSION_HANDOFF_2026-03-02.md`.
- ✅ Zusätzliche Verifikation nach Adapter-Umstellung: 45 passed (`test_head_agent_adapter_constraints`, `test_agent_runtime_reconfigure`, `test_tool_selection_offline_eval`).
- ✅ Zusätzliche Verifikation nach Protocol-Slice: 52 passed (`test_head_agent_adapter_constraints`, `test_agent_runtime_reconfigure`, `test_tool_execution_manager`, `test_tool_selection_offline_eval`).
- ✅ Zusätzliche Verifikation nach ToolSelector/Settings-Slice: 52 passed (`test_head_agent_adapter_constraints`, `test_agent_runtime_reconfigure`, `test_tool_execution_manager`, `test_tool_selection_offline_eval`).
- ✅ Neue Entkopplungs-Tests ergänzt: `tests/test_tool_selector_agent.py` (Runner-Requirement + Inline-Runner ohne Constructor-Wiring).
- ✅ ToolSelector-Run-Pfad abgesichert: `tests/test_tool_selector_agent.py` um `set_execute_tools_fn`-/`run()`-Pfad erweitert.
- ✅ Legacy-Kompatibilitätsmodus verbessert: `ToolSelectorAgent.run()` berücksichtigt jetzt `tool_policy` (`allow`/`deny`) statt immer volles Default-Toolset.
- ✅ ToolSelector-Restkopplung reduziert: konfigurierte Bound-Runner im `ToolSelectorAgent` werden als `WeakMethod` gehalten (keine starke Referenz auf Owner/HeadAgent im Kompatibilitätsmodus).
- ✅ ToolSelector-Kompatibilitätslayer gekapselt: Legacy-Runner-Verwaltung in dedizierter interner Binding-Schicht gebündelt (`_LegacyRunnerBinding`), Runtime-Protocol-Pfad bleibt primär.
- ✅ ToolSelector-Kompatibilitätslayer weiter isoliert: Legacy-Runner-Code in separates Modul ausgelagert (`app/agents/tool_selector_legacy.py`), `tool_selector_agent.py` fokussiert auf Runtime-Orchestrierung.
- ✅ ToolSelector-Ausführungspfade klar getrennt: Inline-/Runtime-/Legacy-Branches in dedizierte Methoden aufgeteilt; Legacy-Setter als expliziter Compat-Pfad (`set_legacy_execute_tools_fn`) markiert.
- ✅ ToolSelector-Legacy-Run entkoppelt: `ToolSelectorAgent.run()` unterstützt jetzt expliziten Inline-Runner (`execute_tools_fn=...`) und funktioniert damit ohne vorab konfigurierten internen Runner-State.
- ✅ **Phase 3.1 Runtime-Übergabeschnittstelle** ergänzt: `ToolSelectorAgent` unterstützt jetzt ein explizites `ToolSelectorRuntime`-Protocol (`run_tools(...)`) als primären Integrationspfad statt direkter Methoden-Kopplung.
- ✅ Runtime-Contract weiter entkoppelt: `ToolSelectorRuntime` in `app/contracts/tool_selector_runtime.py` extrahiert und als Vertragsoberfläche (`app/contracts/__init__.py`) exportiert.
- ✅ HeadAgent-Wiring auf Runtime-Objekt umgestellt: `_execute_tool_step` nutzt den ToolSelector ohne direkten Callback-Parameter; Aufruf erfolgt über `_HeadToolSelectorRuntime` mit schwacher Owner-Referenz.
- ✅ Policy-Kompatibilität abgesichert: `tests/test_tool_selector_agent.py` um Allow/Deny-Normalisierungsfall erweitert.
- ✅ WeakRef-Kompatibilität abgesichert: `tests/test_tool_selector_agent.py` um Constructor-Runner-Pfad und Expiry-Verhalten bei freigegebenem Bound-Owner erweitert.
- ✅ Inline-Run-Kompatibilität abgesichert: `tests/test_tool_selector_agent.py` um `run(..., execute_tools_fn=...)`-Pfad ergänzt.
- ✅ Deterministische Runner-Präzedenz abgesichert: expliziter Inline-Runner hat Vorrang vor konfiguriertem Runner im `ToolSelectorAgent.run()`-Pfad.
- ✅ Runtime-Pfad abgesichert: `tests/test_tool_selector_agent.py` um Runtime-Ausführung und Präzedenz (Inline-Runner > Runtime) erweitert.
- ✅ Async-Dispatch-Edge-Case abgesichert: `tests/test_tool_selection_offline_eval.py` um Fall „sync `_invoke_tool` liefert Awaitable“ ergänzt.
- ✅ Zusätzliche Verifikation nach ToolSelector-Agent-Test-Slice: 45 passed (`test_tool_selector_agent`, `test_agent_runtime_reconfigure`, `test_tool_selection_offline_eval`).
- ✅ Zusätzliche Verifikation nach Adapter-Pfad-Slice: 53 passed (`test_tool_selector_agent`, `test_agent_runtime_reconfigure`, `test_tool_selection_offline_eval`, `test_tool_execution_manager`).
- ✅ Zusätzliche Verifikation nach PipelineRunner-/Policy-Slices: 56 passed (`test_pipeline_runner_recovery`, `test_tool_execution_manager`, `test_tool_selection_offline_eval`) und 47 passed (`test_tool_selector_agent`, `test_agent_runtime_reconfigure`, `test_tool_selection_offline_eval`).
- ✅ Zusätzliche Verifikation nach vollständigem PipelineRunner-Settings-Sweep: 12 passed (`test_pipeline_runner_recovery`, `test_tool_selector_agent`).
- ✅ Zusätzliche Verifikation nach Async-Invoke-Slice: 50 passed (`test_tool_selection_offline_eval`, `test_tool_execution_manager`, `test_agent_runtime_reconfigure`).
- ✅ Zusätzliche Verifikation nach Async-WebFetch-Slice: 62 passed (`test_tools_web_fetch_security`, `test_agent_tooling_extended`, `test_tool_selection_offline_eval`, `test_tool_execution_manager`).
- ✅ Zusätzliche Verifikation nach ToolSelector-WeakRef-Slice: 49 passed (`test_tool_selector_agent`, `test_agent_runtime_reconfigure`, `test_tool_selection_offline_eval`).
- ✅ Zusätzliche Verifikation nach Inline-Run-Slice: 50 passed (`test_tool_selector_agent`, `test_agent_runtime_reconfigure`, `test_tool_selection_offline_eval`).
- ✅ Zusätzliche Verifikation nach Runner-Präzedenz-Slice: 49 passed (`test_tool_selector_agent`, `test_tool_selection_offline_eval`).
- ✅ Zusätzliche Verifikation nach Async-Dispatch-Härtung: 57 passed (`test_tool_selection_offline_eval`, `test_tool_execution_manager`, `test_tool_selector_agent`).
- ✅ Zusätzliche Verifikation nach Runtime-Protocol-Slice: 61 passed (`test_tool_selector_agent`, `test_agent_runtime_reconfigure`, `test_tool_selection_offline_eval`, `test_tool_execution_manager`).
- ✅ Zusätzliche Verifikation nach Legacy-Binding-Kapselung: 61 passed (`test_tool_selector_agent`, `test_agent_runtime_reconfigure`, `test_tool_selection_offline_eval`, `test_tool_execution_manager`).
- ✅ Zusätzliche Verifikation nach Runtime-Contract-Extraktion: 61 passed (`test_tool_selector_agent`, `test_agent_runtime_reconfigure`, `test_tool_selection_offline_eval`, `test_tool_execution_manager`).
- ✅ Zusätzliche Verifikation nach Legacy-Modul-Extraktion: 61 passed (`test_tool_selector_agent`, `test_agent_runtime_reconfigure`, `test_tool_selection_offline_eval`, `test_tool_execution_manager`).
- ✅ Zusätzliche Verifikation nach Compat-API-/Branch-Slice: 61 passed (`test_tool_selector_agent`, `test_agent_runtime_reconfigure`, `test_tool_selection_offline_eval`, `test_tool_execution_manager`).
- ✅ Zusätzliche Verifikation nach ToolProvider-Conformance-Slice: 18 passed (`test_tool_provider_protocol`, `test_tool_execution_manager`, `test_tool_selector_agent`).
- ✅ Zusätzliche Verifikation nach Phase-4-RecoveryContext-Slice: 57 passed (`test_pipeline_runner_recovery`, `test_tool_execution_manager`, `test_tool_selection_offline_eval`).
- ✅ Zusätzliche Verifikation nach 6.4.1-/6.4.2-Einstiegsslice: 57 passed (`test_pipeline_runner_recovery`, `test_tool_execution_manager`, `test_tool_selection_offline_eval`).
- ⏭️ Nächster Schritt: Validierung mit stabiler Python-Version (3.11/3.12), plus gezielte Tests für neue Module (`test_recovery_strategy.py`, SQLite-StateStore-Tests, command-blocklist-Regressionen).

### Grundprinzipien

1. **Strangler-Fig-Pattern**: Neue Module extrahieren und schrittweise HeadAgent-Methoden darauf umleiten — kein Big-Bang-Rewrite
2. **Grüne Tests zuerst**: Jede Extraktion beginnt mit Tests für den Ist-Zustand (Characterization Tests), dann Refactoring
3. **Backwards-Compatible**: Keine Breaking Changes an `HeadAgent.__init__` oder `HeadAgent.run()` bis Phase 3
4. **Contracts first**: Neue Module definieren zuerst ein Protocol/ABC, dann wird implementiert

### Reihenfolge der Concerns-Extraktion aus HeadAgent (2.771 LOC → ~300 LOC)

```
HeadAgent (2.771 LOC, 75 Methoden, 14 Concerns)
    ├── Phase 0: Security-Fixes (inline, kein Refactoring)
    ├── Phase 1a: ToolArgValidator          ← 14 _validate_*_args Methoden (~350 LOC)
    ├── Phase 1b: ToolRegistry              ← _build_tool_registry + Dispatching (~250 LOC)
    ├── Phase 1c: IntentDetector            ← 8 _is_*_task + _detect_intent_gate (~250 LOC)
    ├── Phase 1d: ReplyShaper               ← _shape_final_response + _sanitize (~120 LOC)
    ├── Phase 1e: ToolExecutionManager      ← _execute_tools (708 LOC → Klasse ~400 LOC)
    ├── Phase 1f: ActionParser              ← JSON-Parse, Repair, Extraction (~150 LOC)
    ├── Phase 1g: ActionAugmenter           ← _augment_actions_if_needed (~120 LOC)
    └── Phase 3:  HeadAgent Core            ← run(), Lifecycle, Hooks (~300 LOC)
```

---

## 2. Phase 0 — Sicherheitskritische Sofortmaßnahmen (Woche 1)

> **Ziel**: Sicherheitslücken schließen, bevor jede andere Arbeit beginnt.

### 2.0.1 Command-Blocklist erweitern

**Datei**: `app/tools.py` → `_enforce_command_safety`  
**Aktueller Zustand**: 5 Regex-Patterns (nur `rm -rf /`, `format`, `shutdown`, `reboot`)  
**Problem**: `rm -rf .`, `chmod 777`, `wget malicious && bash`, ungetestet

**Aktion**:
```python
# VORHER (tools.py _enforce_command_safety):
blocked_patterns = [
    r"\brm\s+-rf\s+/",
    r"\bdel\s+/[a-z]*\s*[a-z]:\\",
    r"\bformat\s+[a-z]:",
    r"\bshutdown\b",
    r"\breboot\b",
]

# NACHHER — erweiterte Blocklist:
blocked_patterns = [
    r"\brm\s+-r[f]?\s",              # jedes recursive rm (nicht nur /)
    r"\bdel\s+/[a-z]*\s*[a-z]:\\",
    r"\bformat\s+[a-z]:",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bchmod\s+[0-7]{3,4}\b",       # chmod mit numerischen Permissions
    r"\bchown\b",                     # Ownership-Änderungen
    r"\bmkfs\b",                      # Filesystem-Formatierung
    r"\bdd\s+if=",                    # Disk-Write
    r"\bcurl\b.*\|\s*(ba)?sh\b",     # curl | bash
    r"\bwget\b.*\|\s*(ba)?sh\b",     # wget | bash
    r"\bwget\b.*&&\s*(ba)?sh\b",     # wget && bash
    r"python[23]?\s+-c\b",           # python -c Injection
    r"powershell\s+-enc",            # Encoded PowerShell
    r"\bnc\s+-[lp]",                 # Netcat listen/connect
]
```

**Tests hinzufügen**: `tests/test_tools_command_security.py` — je ein Testcase pro Pattern

---

### 2.0.2 ~~Path-Traversal-Fix~~ (Bereits implementiert ✓)

Die Analyse zeigt, dass `_resolve_workspace_path` bereits korrekt implementiert ist:
```python
def _resolve_workspace_path(self, raw_path: str) -> Path:
    target = (self.workspace_root / raw_path).resolve()
    if self.workspace_root not in target.parents and target != self.workspace_root:
        raise ToolExecutionError("Path escapes workspace root.")
    return target
```
**Aktion**: Nur fehlende Tests ergänzen (siehe Phase 2).

---

### 2.0.3 `web_fetch` Content-Safety ergänzen

**Datei**: `app/tools.py` → `web_fetch`  
**Problem**: Kein `Content-Length`-Check vor Download, kein Binary-Filter

**Aktion**:
```python
# In web_fetch, nach dem Response-Check:
MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024  # 5 MB

content_length = int(response.headers.get("content-length", 0))
if content_length > MAX_DOWNLOAD_BYTES:
    return f"[web_fetch_error] Response too large: {content_length} bytes (max {MAX_DOWNLOAD_BYTES})"

content_type = response.headers.get("content-type", "")
BLOCKED_CONTENT_TYPES = ("application/octet-stream", "application/x-executable",
                         "application/x-sharedlib", "application/zip",
                         "application/gzip", "application/x-tar")
if any(ct in content_type for ct in BLOCKED_CONTENT_TYPES):
    return f"[web_fetch_error] Blocked content-type: {content_type}"
```

---

### 2.0.4 `_is_file_creation_task` False-Positive reduzieren

**Datei**: `app/agent.py`  
**Problem**: "Explain JavaScript" triggert unnötigen `write_file` Follow-up-Call

**Aktion**:
```python
# VORHER:
def _is_file_creation_task(self, user_message: str) -> bool:
    markers = ("create", "build", "make", "save", "file", "html", "css", "javascript", "js")
    return any(marker in text for marker in markers)

# NACHHER — kontextbewusste Prüfung:
_FILE_CREATION_PHRASES = (
    "create a file", "create file", "create a new file",
    "build a file", "make a file", "save to file", "save as file",
    "write to file", "generate a file", "create an html",
    "create a css", "create a js", "create a javascript",
    "write html", "write css", "write javascript",
)

def _is_file_creation_task(self, user_message: str) -> bool:
    text = user_message.lower()
    return any(phrase in text for phrase in self._FILE_CREATION_PHRASES)
```

---

## 3. Phase 1 — HeadAgent God-Class aufbrechen (Wochen 1–2)

> **Ziel**: HeadAgent von 2.771 LOC / 75 Methoden auf ~300 LOC / ~12 Methoden reduzieren.

### 3.1.a ToolArgValidator extrahieren

**Neue Datei**: `app/services/tool_arg_validator.py`  
**Extrahiert aus**: `agent.py` L2284–L2547 (14 Methoden, ~280 LOC)

```python
# app/services/tool_arg_validator.py

from __future__ import annotations
from typing import Any, Protocol

class ToolArgValidationError(Exception):
    """Raised when tool arguments fail validation."""
    def __init__(self, tool_name: str, message: str):
        self.tool_name = tool_name
        super().__init__(f"{tool_name}: {message}")


class ToolArgValidator:
    """
    Validates tool-call arguments before execution.
    Extraced from HeadAgent to eliminate feature envy.
    """

    def validate(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize args for the given tool. Returns cleaned args."""
        validator = self._validators.get(tool_name)
        if validator:
            validator(args)
        return args

    # --- Alle 14 _validate_*_args-Methoden hierher verschieben ---
    # _require_str_arg
    # _require_bool_arg
    # _optional_int_arg
    # _validate_path_only_tool_args
    # _validate_write_file_args
    # _validate_command_tool_args
    # _validate_apply_patch_args
    # _validate_file_search_args
    # _validate_grep_search_args
    # _validate_list_code_usages_args
    # _validate_get_background_output_args
    # _validate_kill_background_process_args
    # _validate_web_fetch_args
    # _validate_spawn_subrun_args
    # _validate_noop_tool_args
```

**Migrationsstrategie**:
1. Erstelle `ToolArgValidator` mit allen Methoden (Copy)
2. In `HeadAgent.__init__`: `self._arg_validator = ToolArgValidator()`
3. In `HeadAgent._evaluate_action`: Ersetze `self._validate_*` durch `self._arg_validator.validate()`
4. Lösche die 14 Methoden aus `agent.py`
5. **Tests**: Neue Unit-Tests in `tests/test_tool_arg_validator.py` mit je 2-3 Cases pro Tool

**Erwartete LOC-Reduktion in agent.py**: ~280 Zeilen

---

### 3.1.b ToolRegistry extrahieren

**Neue Datei**: `app/services/tool_registry.py`  
**Extrahiert aus**: `agent.py` L2133–L2273 (~140 LOC)

```python
# app/services/tool_registry.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Optional

@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    timeout: float = 30.0
    retryable: bool = False
    max_retries: int = 0

@dataclass(frozen=True)
class ToolExecutionPolicy:
    timeout: float
    retryable: bool
    max_retries: int


class ToolRegistry:
    """
    Central registry for available tools and their specifications.
    Extracted from HeadAgent._build_tool_registry + dispatch logic.
    """

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._dispatchers: dict[str, Callable] = {}
        self._arg_validators: dict[str, Callable] = {}

    def register(self, spec: ToolSpec, dispatcher: Callable,
                 validator: Optional[Callable] = None) -> None:
        self._specs[spec.name] = spec
        self._dispatchers[spec.name] = dispatcher
        if validator:
            self._arg_validators[spec.name] = validator

    def get_spec(self, name: str) -> Optional[ToolSpec]:
        return self._specs.get(name)

    def get_dispatcher(self, name: str) -> Optional[Callable]:
        return self._dispatchers.get(name)

    def all_specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def tool_names(self) -> set[str]:
        return set(self._specs.keys())

    def build_execution_policy(self, name: str) -> ToolExecutionPolicy:
        spec = self._specs[name]
        return ToolExecutionPolicy(
            timeout=spec.timeout,
            retryable=spec.retryable,
            max_retries=spec.max_retries,
        )
```

**Migrationsstrategie**:
1. Erstelle `ToolRegistry` Klasse
2. Verschiebe `ToolSpec`, `ToolExecutionPolicy` Dataclasses dorthin
3. Wandele `HeadAgent._build_tool_registry()` in `ToolRegistryFactory.build(tooling, allowed_tools)` um
4. `HeadAgent` bekommt `self._registry: ToolRegistry` statt `self._tool_specs: dict`
5. **Tests**: `tests/test_tool_registry.py`

**Erwartete LOC-Reduktion**: ~200 Zeilen

---

### 3.1.c IntentDetector extrahieren

**Neue Datei**: `app/services/intent_detector.py`  
**Extrahiert aus**: `agent.py` L1457–L1979 (~520 LOC → ~300 LOC nach Cleanup)

```python
# app/services/intent_detector.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class IntentGateDecision:
    detected_intent: Optional[str]
    confidence: float
    gate_action: str  # "proceed", "skip_tools", "force_tool"
    metadata: dict


class IntentDetector:
    """
    Detects user intent from message text using keyword/pattern matching.
    Extracted from HeadAgent's 8 _is_*_task methods + _detect_intent_gate.

    Future: Replace keyword matching with lightweight classifier or
    structured-output LLM call.
    """

    def detect(self, user_message: str) -> IntentGateDecision:
        """Classify user intent from the message."""
        ...

    # Migrated methods:
    # _detect_intent_gate        → detect()
    # _looks_like_shell_command   → is_shell_command()
    # _extract_explicit_command   → extract_command()
    # _is_web_research_task       → _check_web_research()
    # _is_file_creation_task      → _check_file_creation()  (with improved logic from Phase 0)
    # _is_subrun_orchestration_task → _check_orchestration()
    # _is_weather_lookup_task     → _check_weather()
    # _should_retry_web_fetch_on_404 → should_retry_fetch()
    # _has_successful_web_fetch   → has_successful_fetch()
    # _build_web_research_url     → build_search_url()
    # _build_web_fetch_unavailable_reply → build_fetch_unavailable_reply()
```

**Migrationsstrategie**:
1. Erstelle `IntentDetector` mit allen Intent-Methoden
2. In `HeadAgent.__init__`: `self._intent = IntentDetector()`
3. Ersetze alle `self._is_*_task()` Calls durch `self._intent.*()` Calls
4. `_execute_tools` und `run` delegieren Intent-Checks an `self._intent`
5. Lösche die 8 Methoden aus `agent.py`
6. **Tests**: `tests/test_intent_detector.py` — Positive/Negative-Cases pro Intent-Typ

**Erwartete LOC-Reduktion**: ~350 Zeilen

---

### 3.1.d ReplyShaper extrahieren

**Neue Datei**: `app/services/reply_shaper.py`  
**Extrahiert aus**: `agent.py` L1981–L2062 (~80 LOC)

```python
# app/services/reply_shaper.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass
class ReplyShapeResult:
    text: str
    was_suppressed: bool
    suppression_reason: Optional[str]
    dedup_lines_removed: int


class ReplyShaper:
    """
    Post-processes LLM responses: sanitize tool-call artifacts,
    deduplicate lines, suppress trivial answers.
    """

    def shape(self, raw_response: str, tool_results: list[dict],
              user_message: str) -> ReplyShapeResult:
        sanitized = self.sanitize(raw_response)
        return self._apply_shaping_rules(sanitized, tool_results, user_message)

    def sanitize(self, text: str) -> str:
        """Remove [TOOL_CALL] blocks and other artifacts."""
        ...

    def _apply_shaping_rules(self, text: str, tool_results: list[dict],
                              user_message: str) -> ReplyShapeResult:
        ...
```

**Erwartete LOC-Reduktion**: ~80 Zeilen

---

### 3.1.e ToolExecutionManager extrahieren (das schwierigste Stück)

**Neue Datei**: `app/services/tool_execution_manager.py`  
**Extrahiert aus**: `agent.py` L749–L1455 (708 LOC → ~450 LOC mit besserer Struktur)

Dies ist die **kritischste Extraktion**, da `_execute_tools` die längste Methode ist und fast alle anderen Concerns berührt.

```python
# app/services/tool_execution_manager.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

@dataclass
class ToolExecutionConfig:
    """Replaces scattered getattr(settings, ...) lookups."""
    call_cap: int = 8
    time_cap_seconds: float = 90.0
    result_max_chars: int = 6000
    max_augmentation_rounds: int = 2


@dataclass
class ToolExecutionResult:
    tool_results: list[dict[str, Any]]
    budget_exhausted: bool
    loop_detected: bool
    total_calls: int
    total_time_seconds: float
    audit_summary: dict[str, Any]


class ToolExecutionManager:
    """
    Manages the tool-selection → execution → retry loop.
    Extracted from HeadAgent._execute_tools (708 LOC).

    Decomposed into sub-methods:
    1. _build_tool_selection_prompt()   — Prompt construction
    2. _call_llm_for_selection()        — LLM call + JSON parse
    3. _validate_and_filter()           — Action validation
    4. _execute_action_batch()          — Run tools with policy
    5. _check_loop_conditions()         — Budget + loop detection
    6. _handle_augmentation()           — Action augmentation
    """

    def __init__(
        self,
        config: ToolExecutionConfig,
        registry: "ToolRegistry",
        gatekeeper: "ToolCallGatekeeper",
        intent_detector: "IntentDetector",
        arg_validator: "ToolArgValidator",
        action_parser: "ActionParser",
        action_augmenter: "ActionAugmenter",
        llm_client: "LlmClient",
        send_event: Callable,
    ) -> None:
        ...

    async def execute(
        self,
        user_message: str,
        plan_text: str,
        conversation_history: list[dict],
        allowed_tools: set[str],
        tool_policy: dict,
    ) -> ToolExecutionResult:
        """Main entry point — replaces HeadAgent._execute_tools()."""
        ...

    def _build_tool_selection_prompt(self, ...) -> str: ...
    def _call_llm_for_selection(self, ...) -> list[dict]: ...
    def _validate_and_filter(self, ...) -> list[dict]: ...
    async def _execute_action_batch(self, ...) -> list[dict]: ...
    def _check_loop_conditions(self, ...) -> bool: ...
    def _handle_augmentation(self, ...) -> list[dict]: ...
```

**Migrationsstrategie** (extra vorsichtig):
1. **Characterization Tests zuerst**: Schreibe 10-15 Tests, die das aktuelle Verhalten von `_execute_tools` über den HeadAgent testen (via Mocks)
2. Erstelle `ToolExecutionManager` mit den Sub-Methoden
3. In `HeadAgent._execute_tools`: Delegiere an `self._execution_manager.execute()`
4. Verifiziere, dass alle Characterization Tests noch grün sind
5. Lösche den alten Code aus `agent.py`
6. **Neue Unit-Tests**: `tests/test_tool_execution_manager.py`

**Erwartete LOC-Reduktion**: ~650 Zeilen (die größte Einzelextraktion)

---

### 3.1.f ActionParser extrahieren

**Neue Datei**: `app/services/action_parser.py`  
**Extrahiert aus**: `agent.py` L2064–L2131 (~70 LOC)

```python
# app/services/action_parser.py

class ActionParser:
    """
    Parses and repairs LLM-generated JSON tool-call actions.
    Extracted from HeadAgent._extract_actions, _repair_*, _extract_json_candidate.
    """

    def parse(self, llm_output: str) -> list[dict]:
        """Parse JSON actions from LLM output."""
        ...

    def repair(self, malformed_json: str, llm_client: "LlmClient") -> list[dict]:
        """Attempt to repair malformed JSON via secondary LLM call."""
        ...

    def validate(self, actions: list[dict], allowed_tools: set[str]) -> list[dict]:
        """Filter and validate parsed actions."""
        ...
```

**Erwartete LOC-Reduktion**: ~70 Zeilen

---

### 3.1.g ActionAugmenter extrahieren

**Neue Datei**: `app/services/action_augmenter.py`  
**Extrahiert aus**: `agent.py` L1644–L1765 (~120 LOC)

```python
# app/services/action_augmenter.py

class ActionAugmenter:
    """
    Augments LLM-selected actions with missing tools based on intent.
    E.g., web_fetch for research tasks, write_file for file-creation tasks.

    Uses IntentDetector for decisions instead of inline keyword checks.
    """

    def __init__(self, intent_detector: "IntentDetector"):
        self._intent = intent_detector

    def augment(self, actions: list[dict], user_message: str,
                allowed_tools: set[str]) -> list[dict]:
        ...
```

**Erwartete LOC-Reduktion**: ~120 Zeilen

---

### 3.1 Zusammenfassung Phase 1

| Schritt | Neue Datei | LOC aus agent.py | Neue Tests |
|---------|------------|:----------------:|:----------:|
| 1a | `services/tool_arg_validator.py` | ~280 | ~30 |
| 1b | `services/tool_registry.py` | ~200 | ~15 |
| 1c | `services/intent_detector.py` | ~350 | ~25 |
| 1d | `services/reply_shaper.py` | ~80 | ~10 |
| 1e | `services/tool_execution_manager.py` | ~650 | ~20 |
| 1f | `services/action_parser.py` | ~70 | ~10 |
| 1g | `services/action_augmenter.py` | ~120 | ~10 |
| **Gesamt** | **7 neue Module** | **~1.750** | **~120** |

**agent.py nach Phase 1**: ~1.020 LOC (von 2.771) — davon ~300 LOC Kern + ~720 LOC noch zu bereinigen

---

## 4. Phase 2 — Test-Coverage für kritische Pfade (Wochen 2–3)

> **Ziel**: Von ~40-50% auf >75% Coverage, mit Fokus auf sicherheitskritische Module.

### 4.2.1 `tool_call_gatekeeper.py` — P0 (0 Tests → vollständig getestet)

**Neue Datei**: `tests/test_tool_call_gatekeeper.py`  
**Scope**: 355 LOC, 3 Dataclasses, 2 Funktionen, 1 Klasse

```python
# Testmatrix für ToolCallGatekeeper:

class TestPrepareActionForExecution:
    """Tests für prepare_action_for_execution (L73-L97)"""
    def test_valid_action_passes() -> None: ...
    def test_unknown_tool_name_rejected() -> None: ...
    def test_missing_args_gets_empty_dict() -> None: ...
    def test_tool_name_normalized_via_alias() -> None: ...
    def test_policy_blocked_tool_rejection() -> None: ...

class TestCollectPolicyOverrideCandidates:
    """Tests für collect_policy_override_candidates (L28-L71)"""
    def test_run_command_detected_as_candidate() -> None: ...
    def test_spawn_subrun_detected_as_candidate() -> None: ...
    def test_read_file_not_a_candidate() -> None: ...
    def test_already_approved_tool_excluded() -> None: ...

class TestToolCallGatekeeper:
    """Tests für ToolCallGatekeeper Loop-Detection (L99-L408)"""

    class TestGenericRepeat:
        def test_same_tool_same_args_3x_triggers_block() -> None: ...
        def test_same_tool_different_args_allowed() -> None: ...
        def test_reset_on_new_tool() -> None: ...

    class TestPingPong:
        def test_abab_pattern_detected() -> None: ...
        def test_abac_pattern_not_detected() -> None: ...
        def test_ping_pong_threshold_configurable() -> None: ...

    class TestCircuitBreaker:
        def test_consecutive_errors_trigger_break() -> None: ...
        def test_success_resets_error_count() -> None: ...
        def test_circuit_breaker_threshold() -> None: ...

    class TestPollNoProgress:
        def test_same_result_3x_triggers_break() -> None: ...
        def test_different_results_allowed() -> None: ...

    class TestWarningBuckets:
        def test_warning_emitted_at_50_percent_budget() -> None: ...
        def test_warning_emitted_at_75_percent_budget() -> None: ...
```

**Geschätzter Aufwand**: ~200 LOC Tests, ~4h

---

### 4.2.2 Path-Traversal-Tests ergänzen

**Datei**: `tests/test_tools_path_traversal.py` (neu)

```python
class TestResolveWorkspacePath:
    def test_simple_relative_path() -> None: ...
    def test_dotdot_traversal_blocked() -> None: ...
    def test_absolute_path_outside_workspace_blocked() -> None: ...
    def test_symlink_escape_blocked() -> None: ...
    def test_path_at_workspace_root_allowed() -> None: ...
    def test_deeply_nested_path_allowed() -> None: ...
    def test_dotdot_within_workspace_allowed() -> None: ...  # src/../lib/x.py
    def test_windows_backslash_traversal() -> None: ...
```

---

### 4.2.3 Pipeline-Runner Recovery-Tests

**Datei**: `tests/test_pipeline_runner_recovery.py` (neu)

```python
class TestRecoveryStrategyResolution:
    """Tests für _resolve_recovery_strategy (L714)"""
    def test_context_overflow_triggers_compaction() -> None: ...
    def test_truncation_required_triggers_truncation() -> None: ...
    def test_rate_limited_triggers_model_fallback() -> None: ...
    def test_strategy_feedback_demotes_failed_strategy() -> None: ...
    def test_priority_flip_on_repeated_failure() -> None: ...

class TestPromptCompaction:
    def test_compaction_ratio_reduces_message() -> None: ...
    def test_compaction_preserves_system_prompt() -> None: ...

class TestPayloadTruncation:
    def test_truncation_targets_conversation_history() -> None: ...
    def test_truncation_preserves_last_message() -> None: ...
```

---

### 4.2.4 Coverage-Tooling in CI

**Datei**: `pytest.ini` erweitern:
```ini
[pytest]
addopts = --cov=app --cov-report=html --cov-report=term-missing --cov-fail-under=70
```

**Datei**: Coverage-Thresholds pro Modul in `scripts/check_coverage_thresholds.py`:
```python
THRESHOLDS = {
    "app/services/tool_call_gatekeeper.py": 90,  # Security-critical
    "app/tools.py": 80,
    "app/agent.py": 60,  # Wird in Phase 1 aufgebrochen
    "app/orchestrator/pipeline_runner.py": 65,
    "app/services/tool_arg_validator.py": 95,
}
```

---

## 5. Phase 3 — Architektur-Bereinigung (Wochen 3–4)

### 5.3.1 Sub-Agenten-Architektur reparieren

**Problem**: `ToolSelectorAgent` ist ein Dummy-Wrapper, der nur `HeadAgent._execute_tools()` aufruft.

**Lösung**: `ToolSelectorAgent` bekommt eigene Logik via `ToolExecutionManager`:

```python
# VORHER (tool_selector_agent.py):
class ToolSelectorAgent:
    async def execute(self, payload, **kwargs):
        results = await self._execute_tools_fn(...)  # HeadAgent callback
        return ToolSelectorOutput(tool_results=results)

# NACHHER:
class ToolSelectorAgent:
    def __init__(self, execution_manager: ToolExecutionManager):
        self._manager = execution_manager

    async def execute(self, payload: ToolSelectorInput, **kwargs):
        result = await self._manager.execute(
            user_message=payload.user_message,
            plan_text=payload.plan_text,
            conversation_history=payload.history,
            allowed_tools=payload.allowed_tools,
            tool_policy=payload.tool_policy,
        )
        return ToolSelectorOutput(tool_results=result.tool_results)
```

**Effekt**: Bricht die zirkuläre Abhängigkeit `HeadAgent → ToolSelectorAgent → HeadAgent._execute_tools`.

---

### 5.3.2 Doppelte Schema-Definitionen bereinigen

**Datei**: `app/contracts/schemas.py`

```python
# VORHER:
class HeadAgentInput(BaseModel): ...
class CoderAgentInput(BaseModel): ...  # identisch zu HeadAgentInput
HeadCoderInput = HeadAgentInput

# NACHHER:
class AgentInput(BaseModel):
    """Unified input schema for all agent types."""
    ...

# Aliases für Backwards-Compatibility (deprecated):
HeadAgentInput = AgentInput
CoderAgentInput = AgentInput
HeadCoderInput = AgentInput
```

---

### 5.3.3 Settings-Zugriff vereinheitlichen

**Problem**: `getattr(settings, "key", default)` umgeht Pydantic-Validation.

**Lösung**: Dedizierte Config-Dataclasses pro Concern:

```python
# app/services/tool_execution_manager.py
@dataclass(frozen=True)
class ToolExecutionConfig:
    call_cap: int
    time_cap_seconds: float
    result_max_chars: int

    @classmethod
    def from_settings(cls, settings: "Settings") -> "ToolExecutionConfig":
        return cls(
            call_cap=settings.run_tool_call_cap,
            time_cap_seconds=settings.run_tool_time_cap_seconds,
            result_max_chars=settings.tool_result_max_chars,
        )
```

Jedes extrahierte Modul bekommt seine eigene typensichere Config statt `getattr`-Fallbacks.

---

### 5.3.4 `_invoke_tool` async machen

**Problem**: `_invoke_tool` ist synchron, wird via `asyncio.to_thread` aufgerufen. `web_fetch` nutzt `httpx` (async-fähig), wird aber synchron gestartet.

**Lösung**:
```python
# In ToolExecutionManager:
async def _invoke_tool(self, name: str, args: dict) -> str:
    dispatcher = self._registry.get_dispatcher(name)
    if asyncio.iscoroutinefunction(dispatcher):
        return await dispatcher(**args)
    return await asyncio.to_thread(dispatcher, **args)
```

Zusätzlich: `AgentTooling.web_fetch` auf native `async def` umstellen (httpx.AsyncClient statt httpx.Client).

---

### 5.3.5 Protocol/ABC für AgentTooling

**Neue Datei**: `app/contracts/tool_protocol.py`

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class ToolProvider(Protocol):
    """Contract for tool implementations."""

    def list_dir(self, path: str) -> str: ...
    def read_file(self, path: str, start_line: int = 1, end_line: int = -1) -> str: ...
    def write_file(self, path: str, content: str) -> str: ...
    async def web_fetch(self, url: str, max_chars: int = 10000) -> str: ...
    def run_command(self, command: str, cwd: str | None = None) -> str: ...
    # ... etc
```

---

## 6. Phase 4 — Pipeline-Runner Refactoring (Wochen 4–5)

### 6.4.1 `_resolve_recovery_strategy` aufbrechen

**Problem**: 32 Parameter, ~260 LOC, unlesbar.

**Lösung**: `RecoveryContext` Dataclass:

```python
@dataclass
class RecoveryContext:
    """Encapsulates all state needed for recovery strategy resolution."""
    error: Exception
    failover_reason: str
    attempt: int
    max_attempts: int
    model_name: str
    model_health_score: float
    model_latency_ms: float
    model_cost_tier: int
    previous_strategies: list[str]
    strategy_feedback: dict[str, float]
    persistent_metrics: dict[str, Any]
    # ... (alle 32 Parameter → Felder)


class RecoveryStrategyResolver:
    """Extraced from PipelineRunner._resolve_recovery_strategy."""

    def resolve(self, ctx: RecoveryContext) -> list["RecoveryStep"]:
        steps = self._base_steps(ctx)
        steps = self._apply_signal_priority(steps, ctx)
        steps = self._apply_strategy_feedback(steps, ctx)
        steps = self._apply_persistent_metrics(steps, ctx)
        steps = self._apply_priority_flip(steps, ctx)
        return steps
```

**Effekt**: `pipeline_runner.py` verliert ~300 LOC, wird testbar.

---

### 6.4.2 `_run_with_fallback` aufbrechen

**Problem**: ~600 LOC, 30+ lokale Variablen.

**Lösung**: State-Machine-Pattern:

```python
class FallbackStateMachine:
    """
    Replaces the monolithic _run_with_fallback with a state machine.
    States: INIT → SELECT_MODEL → EXECUTE → CLASSIFY_ERROR → RECOVER → FINALIZE
    """

    class State(Enum):
        INIT = "init"
        SELECT_MODEL = "select_model"
        EXECUTE = "execute"
        CLASSIFY_ERROR = "classify_error"
        RECOVER = "recover"
        FINALIZE = "finalize"

    def __init__(self, config: FallbackConfig, strategy_resolver: RecoveryStrategyResolver):
        ...

    async def run(self, payload: PipelinePayload) -> PipelineResult:
        state = self.State.INIT
        while state != self.State.FINALIZE:
            state = await self._transitions[state]()
        return self._result
```

---

## 7. Phase 5 — Feature-Verbesserungen (Wochen 5–8)

### 7.5.1 Intelligentes Result-Truncation

**Status**: ✅ umgesetzt (`ToolExecutionManager._smart_truncate`, config: `tool_result_smart_truncate_enabled`, `tool_result_max_chars`)

**Problem**: `result[:6000]` clippt hart, wichtige Fehlermeldungen am Ende gehen verloren.

**Lösung**:
```python
def smart_truncate(text: str, max_chars: int = 6000) -> str:
    """Keep first 70% and last 30% of text when truncating."""
    if len(text) <= max_chars:
        return text
    head_size = int(max_chars * 0.7)
    tail_size = max_chars - head_size - 50  # 50 chars for separator
    return (
        text[:head_size]
        + f"\n\n... [{len(text) - max_chars} chars truncated] ...\n\n"
        + text[-tail_size:]
    )
```

---

### 7.5.2 Parallele Read-Only-Tool-Execution

**Status**: ✅ umgesetzt (optionaler Parallelpfad für `READ_ONLY_TOOLS` via `asyncio.gather`)

**Problem**: Alle Tools laufen sequenziell, auch unabhängige `read_file`-Calls.

**Lösung** in `ToolExecutionManager`:
```python
READ_ONLY_TOOLS = {"list_dir", "read_file", "file_search", "grep_search",
                    "list_code_usages", "get_changed_files", "web_fetch"}

async def _execute_action_batch(self, actions: list[dict]) -> list[dict]:
    read_only = [a for a in actions if a["tool"] in self.READ_ONLY_TOOLS]
    mutating = [a for a in actions if a["tool"] not in self.READ_ONLY_TOOLS]

    # Parallel execution for read-only tools
    if read_only:
        read_results = await asyncio.gather(
            *[self._invoke_tool(a["tool"], a["args"]) for a in read_only],
            return_exceptions=True
        )
    # Sequential for mutating tools
    for action in mutating:
        result = await self._invoke_tool(action["tool"], action["args"])
        ...
```

---

### 7.5.3 Re-Planning Loop

**Status**: ✅ umgesetzt (`HeadAgent.run()` iteriert Plan→Tools mit Validierungs-Loop und `run_max_replan_iterations`)

**Problem**: Plan → Tools → Synthesize ohne Feedback-Loop. Wenn Tool-Ergebnisse den Plan invalidieren, gibt es kein Re-Planning.

**Lösung**: In der `HeadAgent.run()` Orchestrierung:
```python
async def run(self, ...):
    plan = await self._execute_planner_step(...)

    for iteration in range(max_replan_iterations):
        tool_results = await self._execute_tool_step(...)

        if self._plan_still_valid(plan, tool_results):
            break

        # Re-plan with tool results as context
        plan = await self._execute_planner_step(
            ...,
            previous_results=tool_results,
            replan_reason="Tool results invalidated original plan"
        )

    synthesis = await self._execute_synthesize_step(...)
```

---

### 7.5.4 Structured Output für Tool-Selection

**Status**: ✅ umgesetzt (`LlmClient.complete_chat_with_tools(...)`, gated via `supports_function_calling` + Feature-Flag)

**Problem**: Tool-Selection ist prompt-only (free-form JSON), führt zu Parse-Errors und Repair-Loops.

**Lösung**: Nutze Function-Calling / Tool-Use APIs des LLM-Providers:
```python
# In ToolExecutionManager:
async def _call_llm_for_selection(self, prompt: str, tools: list[ToolSpec]) -> list[dict]:
    if self._llm_client.supports_function_calling:
        # Use native function calling
        tool_schemas = [spec.to_openai_function_schema() for spec in tools]
        response = await self._llm_client.chat(
            messages=[...],
            tools=tool_schemas,
            tool_choice="auto",
        )
        return response.tool_calls
    else:
        # Fallback: free-form JSON (current behavior)
        return self._action_parser.parse(response.content)
```

---

### 7.5.5 Cross-Process State Locking

**Status**: ✅ umgesetzt (`SqliteStateStore` als Drop-in mit WAL/busy-timeout; Auswahl über `ORCHESTRATOR_STATE_BACKEND`)

**Problem**: File-basiertes Locking ist nur pro-Process, nicht cross-process.

**Lösung** (bei Multi-Worker-Bedarf):
```python
# app/state/state_store.py — Upgrade-Pfad:
import sqlite3

class SqliteStateStore(StateStore):
    """Drop-in replacement using SQLite for cross-process safety."""

    def __init__(self, db_path: Path):
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._create_tables()
```

---

## 8. Risikoanalyse & Abhängigkeiten

### Abhängigkeitsgraph der Extraktionen

```
Phase 0 (Security)     ──── Keine Abhängigkeiten, sofort umsetzbar
    │
Phase 1a (ArgValidator) ── Keine Abhängigkeiten
Phase 1b (Registry)     ── Keine Abhängigkeiten
Phase 1c (Intent)       ── Keine Abhängigkeiten
Phase 1d (ReplyShaper)  ── Keine Abhängigkeiten
Phase 1f (ActionParser) ── Keine Abhängigkeiten
Phase 1g (Augmenter)    ── Abhängig von 1c (IntentDetector)
Phase 1e (ExecManager)  ── Abhängig von 1a, 1b, 1c, 1f, 1g ← LETZTES in Phase 1
    │
Phase 2 (Tests)         ── Abhängig von Phase 1 (testet neue Module)
    │
Phase 3 (Architektur)   ── Abhängig von Phase 1e (nutzt ToolExecutionManager)
    │
Phase 4 (Pipeline)      ── Unabhängig von Phase 1 (kann parallel laufen)
    │
Phase 5 (Features)      ── Abhängig von Phase 1e + Phase 3
```

### Risikomatrix

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|:------------------:|:------:|------------|
| Phase 1e bricht bestehende E2E-Tests | Hoch | Hoch | Characterization Tests VOR Extraktion; Feature-Flag für neuen Code-Pfad |
| Neue Module haben unentdeckte Edge Cases | Mittel | Mittel | 100% Methodenabdeckung in neuen Modulen |
| Settings-Migration übersieht getattr-Fallbacks | Mittel | Niedrig | Grep nach `getattr.*settings` und systematisch ersetzen |
| Parallele Tool-Execution erzeugt Race Conditions | Niedrig | Hoch | Nur Read-Only-Tools parallelisieren; Mutating immer sequenziell |
| LLM Function-Calling nicht von allen Providern unterstützt | Sicher | Mittel | Fallback auf free-form JSON beibehalten |

---

## 9. Erfolgsmetriken

### Quantitative Ziele

| Metrik | Ist | Ziel Phase 1 | Ziel Phase 5 |
|--------|:---:|:------------:|:------------:|
| agent.py LOC | 2.771 | <1.100 | <400 |
| agent.py Methoden | 75 | <30 | <15 |
| Max Methoden-LOC | 708 | <150 | <100 |
| Test-Coverage gesamt | ~40-50% | >70% | >85% |
| tool_call_gatekeeper Coverage | 0% | >90% | >95% |
| Zirkuläre Abhängigkeiten | 1 | 0 | 0 |
| Module >500 LOC | 3 | 2 | 1 |
| Module ohne Tests | ~5 | 1 | 0 |
| Max Parameter pro Methode | 32 | 8 | 6 |

### Qualitative Ziele

- [ ] Jedes extrahierte Modul hat ein klares Single Responsibility
- [ ] Kein Modul importiert mehr als 5 andere `app.*`-Module
- [ ] Tool-Execution ist über `ToolExecutionManager` testbar ohne LLM-Mock
- [ ] Intent-Detection ist austauschbar (Keyword → Classifier → LLM)
- [ ] Pipeline-Runner Recovery ist über `RecoveryContext` testbar
- [ ] Alle Security-Module haben >90% Coverage

---

## 10. Dateistruktur nach Refactoring

```
backend/app/
├── __init__.py
├── agent.py                          ← ~350 LOC (nur Kern: run, lifecycle, hooks)
├── app_setup.py
├── app_state.py
├── config.py
├── custom_agents.py
├── errors.py
├── llm_client.py
├── main.py
├── memory.py
├── models.py
├── tool_catalog.py
├── tool_policy.py
├── tools.py
│
├── agents/
│   ├── __init__.py
│   ├── head_agent_adapter.py
│   ├── planner_agent.py
│   ├── synthesizer_agent.py
│   └── tool_selector_agent.py       ← Mit eigener Logik (nicht mehr Dummy)
│
├── contracts/
│   ├── __init__.py
│   ├── agent_contract.py
│   ├── schemas.py                    ← Bereinigte Schemas (keine Duplikate)
│   └── tool_protocol.py             ← NEU: Protocol für ToolProvider
│
├── interfaces/
│   ├── ...
│
├── model_routing/
│   ├── ...
│
├── orchestrator/
│   ├── __init__.py
│   ├── events.py
│   ├── pipeline_runner.py            ← ~800 LOC (von 1.483)
│   ├── recovery_strategy.py          ← NEU: RecoveryContext + Resolver
│   ├── fallback_state_machine.py     ← NEU: Ersetzt _run_with_fallback
│   ├── session_lane_manager.py
│   ├── step_executors.py
│   ├── step_types.py
│   └── subrun_lane.py
│
├── services/
│   ├── __init__.py
│   ├── action_augmenter.py           ← NEU: Aus agent.py extrahiert
│   ├── action_parser.py              ← NEU: JSON-Parse + Repair
│   ├── control_fingerprints.py
│   ├── idempotency_service.py
│   ├── intent_detector.py            ← NEU: Intent/NLU-Logik
│   ├── policy_approval_service.py
│   ├── reply_shaper.py               ← NEU: Response Post-Processing
│   ├── session_query_service.py
│   ├── tool_arg_validator.py          ← NEU: 14 Validierungs-Methoden
│   ├── tool_call_gatekeeper.py
│   ├── tool_execution_manager.py      ← NEU: 708-LOC-Methode → Klasse
│   ├── tool_policy_service.py
│   └── tool_registry.py              ← NEU: ToolSpec + Registry
│
├── skills/
│   ├── ...
│
└── state/
    ├── ...
```

### Neue Test-Dateien

```
backend/tests/
├── test_tool_arg_validator.py         ← NEU (~200 LOC)
├── test_tool_registry.py             ← NEU (~100 LOC)
├── test_intent_detector.py           ← NEU (~150 LOC)
├── test_reply_shaper.py              ← NEU (~80 LOC)
├── test_tool_execution_manager.py    ← NEU (~300 LOC)
├── test_action_parser.py             ← NEU (~100 LOC)
├── test_action_augmenter.py          ← NEU (~100 LOC)
├── test_tool_call_gatekeeper.py      ← NEU (~200 LOC)
├── test_tools_path_traversal.py      ← NEU (~80 LOC)
├── test_pipeline_runner_recovery.py  ← NEU (~200 LOC)
├── test_recovery_strategy.py         ← NEU (~150 LOC)
└── ... (bestehende Tests)
```

---

## Appendix: Checkliste pro Extraktion

Für jeden Extraktionsschritt (1a–1g, 4.1–4.2):

- [ ] Characterization Tests für Ist-Verhalten schreiben
- [ ] Neue Datei erstellen mit extrahierten Methoden
- [ ] Protocol/Contract definieren (wenn sinnvoll)
- [ ] `HeadAgent` delegiert an neue Klasse
- [ ] Alte Methoden aus `HeadAgent` löschen
- [ ] Alle bestehenden Tests laufen grün
- [ ] Neue Unit-Tests für extrahiertes Modul
- [ ] `getattr(settings, ...)` durch typisierte Config ersetzen
- [ ] Import-Graph prüfen (keine Zyklen)
- [ ] Coverage-Threshold für neues Modul setzen
