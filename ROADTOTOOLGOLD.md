# ROAD TO TOOL GOLD 🥇

> **Scope:** Toolchain-Zuverlässigkeit von 4/10 → 10/10  
> **Stand:** 2026-03-05  
> **Methode:** Jede Aussage durch Code-Referenz belegt. Kein Wunschdenken.

---

## Inhaltsverzeichnis

1. [Ist-Zustand: Was existiert](#1-ist-zustand-was-existiert)
2. [Ziel-Zustand: Was "Gold" bedeutet](#2-ziel-zustand-was-gold-bedeutet)
3. [Gap-Analyse: Der ehrliche Delta](#3-gap-analyse-der-ehrliche-delta)
4. [Implementierungsplan (6 Level)](#4-implementierungsplan-6-level)
5. [Dos — Die 15 Gebote](#5-dos--die-15-gebote)
6. [Don'ts — Die 12 Todsünden](#6-donts--die-12-todsünden)
7. [Akzeptanzkriterien (40 messbare Gates)](#7-akzeptanzkriterien-40-messbare-gates)
8. [Risiken & Mitigations](#8-risiken--mitigations)
9. [Timeline & Aufwandsschätzung](#9-timeline--aufwandsschätzung)

---

## 1. Ist-Zustand: Was existiert

### 1.1 Bereits implementiert (Phase 0–3)

| Baustein | Status | Datei | Score-Beitrag |
|---|---|---|---|
| **Function Calling aktiviert** | ✅ Done | `agent.py` L1926 — config-driven statt hardcoded `False` | +0.5 |
| **Error-Taxonomie (5 Kategorien)** | ✅ Done | `agent.py` L2763 — `_classify_tool_error()` mit Regex-Patterns | +0.5 |
| **ToolRetryStrategy (standalone)** | ✅ Done | `services/tool_retry_strategy.py` — `RetryDecision` + `classify_error()` + `decide()` | +0.5 |
| **MCP Bridge Reconnect + Retry** | ✅ Done | `services/mcp_bridge.py` — 3 Attempts, 30s Timeout, `health_check()` | +0.5 |
| **Provider Schema-Normalisierung** | ✅ Done | `services/tool_registry.py` — Gemini strippt `format/min/max`, Anthropic patcht Root-Unions | +0.5 |
| **ToolOutcomeVerifier (deterministisch)** | ✅ Done | `services/tool_outcome_verifier.py` — tool-spezifische Checks, <1ms, kein LLM | +0.3 |
| **PlatformInfo Auto-Detection** | ✅ Done | `services/platform_info.py` — OS, Shell, Runtimes, Pkg-Manager, WSL/Container | +0.2 |
| **before/after_tool_call Hooks** | ✅ Existierte | `services/tool_execution_manager.py` L~1297/L~1363 | — |
| **Directive Parser verdrahtet** | ✅ Existierte | `ws_handler.py` L838, `run_handlers.py` L350 | — |
| **Loop-Detection (3 Typen)** | ✅ Existierte | `ToolExecutionConfig` — generic_repeat, ping_pong, poll_no_progress | — |
| **Steer-Interrupt** | ✅ Existierte | `STEER_INTERRUPTED_MARKER` in `run_tool_loop()` | — |
| **Context-Guard (Result-Truncation)** | ✅ Existierte | `tool_result_context_guard.py` + `result_max_chars` | — |
| **Capability-Filter** | ✅ Existierte | `_infer_required_capabilities()` → `filter_tools_by_capabilities()` | — |
| **Replan bei error_only** | ✅ Existierte | `_classify_tool_results_state()` → `error_only` Trigger | — |

**Aktueller Score: ~7/10**

### 1.2 Was noch FEHLT

| Baustein | Status | Impact | Aufwand |
|---|---|---|---|
| **ToolTelemetry (Span-Tracing)** | ❌ Fehlt | Events existieren, aber keine Aggregation/Traces | M |
| **ToolDiscoveryEngine** | ❌ Fehlt | Agent kann keine unbekannten Tools finden | L |
| **ToolKnowledgeBase** | ❌ Fehlt | Kein Lernen aus vergangenen Erfolgen/Fehlern | L |
| **ToolProvisioner** | ❌ Fehlt | Agent kann nichts autonom installieren | L |
| **PackageManagerAdapter** | ❌ Fehlt | Kein unified Interface für npm/pip/apt/brew/choco | M |
| **AdaptiveToolSelector** | ❌ Fehlt | Kein Feedback-Loop von Outcomes → Selection | M |
| **ToolChainPlanner** | ❌ Fehlt | Kein Multi-Step-Pipeline-Planner | M |
| **ExecutionPatternDetector** | ❌ Fehlt | Keine Anti-Pattern-Erkennung | S |
| **ToolSynthesizer** | ❌ Fehlt | Agent kann keine ad-hoc Scripts generieren + sandboxen | L |
| **SelfHealingLoop** | ❌ Fehlt | Keine autonome Error-Recovery über Retry hinaus | L |
| **ToolEcosystemMap** | ❌ Fehlt | Kein Graph der Tool-Ökosysteme (npm, pip, cargo) | M |
| **Hook-Safety (Timeout + Isolation)** | ⚠️ Geplant | Hook-Fehler können Run crashen | S |
| **Result-Transform-Chain** | ⚠️ Geplant | Keine redact/compact/chunk Transformation vor Persist | M |
| **Tool-Profile (benannte Sets)** | ⚠️ Geplant | Nur exakte Tool-Namen, keine Gruppen | S |
| **Probe-Before-Execute** | ❌ Fehlt | Kein `which`/`--version`/`--help` vor Command | S |
| **ExecutionContract (Pre/Post)** | ❌ Fehlt | Kein formaler Vertrag was vor/nach Tool gelten muss | M |
| **ProvisioningPolicy** | ❌ Fehlt | Kein Governance-Modell für Installationen | S |
| **Environment Snapshot/Rollback** | ❌ Fehlt | Kein State-Restore nach fehlgeschlagener Installation | M |

---

## 2. Ziel-Zustand: Was "Gold" bedeutet

**Gold = Der Agent kann JEDE denkbare Aufgabe autonom lösen**, die ein erfahrener Entwickler mit Terminal, Browser und Dateisystem lösen könnte.

### Das Gold-Szenario

```
User: "Erstelle aus diesem Markdown eine PDF-Broschüre mit Inhaltsverzeichnis"

Agent (intern, ~8 Sekunden):
  ├─ IntentResolver: capability = "document_conversion"
  ├─ PlatformInfo: windows/x86_64, shell=pwsh, runtimes=[python,node]
  ├─ Discovery: KnowledgeBase → pandoc (confidence=0.92, 23 successes)
  ├─ Provisioner: `Get-Command pandoc` → ❌ nicht installiert
  │   ├─ Policy: mode=ask_user → "Darf ich pandoc installieren?"
  │   ├─ User: "Ja"
  │   ├─ Install: `choco install pandoc -y` → exit_code=0
  │   └─ Verify: `pandoc --version` → "pandoc 3.1.11" ✅
  ├─ Executor: `pandoc input.md --toc -o output.pdf`
  ├─ OutcomeVerifier:
  │   ├─ file_exists("output.pdf") → ✅
  │   ├─ file_size > 1024 → ✅ (89KB)
  │   └─ pdf_header_valid → ✅
  ├─ Telemetry: 6.2s total, 4.1s install, 2.1s convert
  └─ KnowledgeBase: pandoc success_count → 24, platform=windows

Agent: "PDF erstellt: output.pdf (89KB, 12 Seiten mit Inhaltsverzeichnis)"
```

### Gold-Score-Kriterien

| Dimension | Score 7/10 (Jetzt) | Score 10/10 (Gold) |
|---|---|---|
| **Retry-Intelligenz** | 5-Kategorien-Taxonomie, backoff | + Arg-Mutation, Alternative-Tools, Install-and-Retry |
| **Outcome-Verification** | Deterministisch, <1ms | + File-Exists, Content-Type, LLM-Judge für semantische Prüfung |
| **Tool-Discovery** | Nur statischer Katalog (18 Tools) | + KnowledgeBase, LLM-Reasoning, Pkg-Manager-Search, Web-Fallback |
| **Auto-Install** | ❌ | Policy-gesteuert, sandboxed, mit User-Approval-Flow |
| **Adaptive Selection** | Capability-Filter | + historische Erfolgsrate, Geschwindigkeit, Plattform-Fit |
| **Tool-Chaining** | Sequenziell im Plan | + Format-Conversion-Graph, DAG-basierte Pipelines |
| **Self-Healing** | Replan bei error_only | + Root-Cause-Analyse, Environment-Repair, Workaround-Generierung |
| **Telemetrie** | Events (nicht aggregiert) | + Span-Traces, Tool-Stats-Dashboard, Cost-Tracking |
| **Learning** | LTM-Store (unstrukturiert) | + ToolKnowledge pro capability/platform, Confidence-Scoring |
| **Sandbox-Isolation** | Workspace-Root-basiert | + venv-Install, Docker-Fallback, Rollback |

---

## 3. Gap-Analyse: Der ehrliche Delta

### 3.1 Architektur-Lücken

```
                    AKTUELL                              GOLD
                    ───────                              ────

User → Plan → ToolSelect → Execute → Synth    User → Plan → ToolSelect → Execute → Synth
                    │                                           │
                    ├── RetryStrategy ✅                        ├── RetryStrategy ✅
                    ├── OutcomeVerifier ✅                      ├── OutcomeVerifier ✅
                    ├── PlatformInfo ✅                         ├── PlatformInfo ✅
                    ├── LoopDetection ✅                        ├── LoopDetection ✅
                    ├── SteerInterrupt ✅                       ├── SteerInterrupt ✅
                    │                                           │
                    │  ← HIER IST DIE LÜCKE →                  ├── Discovery ❌→✅
                    │                                           ├── KnowledgeBase ❌→✅
                    │                                           ├── Provisioner ❌→✅
                    │                                           ├── AdaptiveSelector ❌→✅
                    │                                           ├── ChainPlanner ❌→✅
                    │                                           ├── SelfHealing ❌→✅
                    │                                           ├── Telemetry ❌→✅
                    │                                           └── Synthesizer ❌→✅
```

### 3.2 Daten-Lücken

| Was fehlt | Warum kritisch | Lösung |
|---|---|---|
| **Tool-Success-History** | Agent weiß nicht was vorher funktioniert hat | `ToolKnowledgeBase` mit SQLite |
| **Platform-Capabilities im Prompt** | LLM wählt Linux-Commands auf Windows | `PlatformInfo.summary()` in System-Prompt injizieren |
| **Execution-Traces** | Kein Debugging bei komplexen Fehlern | `ToolTelemetry` mit Span-Baum |
| **Install-Audit-Log** | Kein Tracking was installiert wurde | `ProvisioningPolicy` + Audit |

### 3.3 Vertrauens-Lücken

| Risiko | Aktuell | Gold |
|---|---|---|
| **Blind Install** | Agent kann `run_command("pip install X")` — Policy checkt nur Destructive-Patterns | `ProvisioningPolicy` mit Allowlist, Scope, Size-Limit |
| **Infinite Discovery** | — | `DiscoveryConstraints` mit max_search_time, max_candidates |
| **Tool-Halluzination** | LLM erfindet Tool-Namen → `command not found` | `Probe-Before-Execute` Pattern |
| **Version-Inkompatibilität** | Kein Versions-Check | `--version` Probe + Compatibility-Matrix |

---

## 4. Implementierungsplan (6 Level)

### Level 1: Foundation Hardening (Score 7→8) — 1 Woche

> Bereits zu 80% done. Vervollständigung:

| # | Task | Datei | Status |
|---|---|---|---|
| L1.1 | PlatformInfo in System-Prompt injizieren | `prompt_kernel_builder.py` | ✅ Done |
| L1.2 | Hook-Safety: per-Hook Timeout (500ms) + try/except Isolation | `tool_execution_manager.py` | ✅ Done |
| L1.3 | Tool-Profile als benannte Sets (`read_only`, `coding`, `research`) | `tool_policy.py` | ✅ Done |
| L1.4 | Extended OutcomeVerifier: `file_exists` + `content_type` Checks | `tool_outcome_verifier.py` | ✅ Done |
| L1.5 | Result-Transform-Chain: Redact PII, Compact large outputs | `tool_result_context_guard.py` | ✅ Done |

**Deliverables:**
```
services/prompt_kernel_builder.py   → platform_summary in System-Prompt
services/tool_execution_manager.py  → Hook-Timeout + Isolation
tool_policy.py                      → TOOL_PROFILES dict
services/tool_outcome_verifier.py   → file_exists/content_type checks
services/tool_result_context_guard.py → PII-Redaction + Compaction
```

---

### Level 2: Telemetry & Observability (Score 8→8.5) — 1 Woche

| # | Task | Datei | Status |
|---|---|---|---|
| L2.1 | `ToolTelemetry` — Span-Tracing mit Start/End/Retry/Outcome | NEU: `services/tool_telemetry.py` | ✅ Done |
| L2.2 | `ToolSpan` Dataclass — span_id, tool, duration, exit_code, outcome | Teil von L2.1 | ✅ Done |
| L2.3 | Session-Trace-Export (JSON) für Debugging | Teil von L2.1 | ✅ Done |
| L2.4 | `get_tool_stats()` — Aggregierte Pro-Tool-Metriken | Teil von L2.1 | ✅ Done |
| L2.5 | Integration in `tool_execution_manager.py` Execute-Loop | `tool_execution_manager.py` | ✅ Done |
| L2.6 | REST-Endpoint `/api/tools/stats` | `runtime_debug_endpoints.py` | ✅ Done |

**Deliverables:**
```
services/tool_telemetry.py          → ToolTelemetry + ToolSpan
services/tool_execution_manager.py  → start_span/end_span around tool calls
routers/runtime_debug_endpoints.py  → /api/tools/stats
```

---

### Level 3: Discovery & Knowledge (Score 8.5→9) — 2–3 Wochen

> **Der Game-Changer.** Agent findet Tools die er nicht kennt.

| # | Task | Datei | Status |
|---|---|---|---|
| L3.1 | `ToolKnowledgeBase` — SQLite-backed Wissensspeicher | NEU: `services/tool_knowledge_base.py` | ✅ Done |
| L3.2 | `learn_from_outcome()` — nach jeder Ausführung lernen | Teil von L3.1 | ✅ Done |
| L3.3 | `find_tools_for_capability()` — semantische Suche | Teil von L3.1 | ✅ Done |
| L3.4 | `PackageManagerAdapter` Protocol + Implementierungen | NEU: `services/package_manager_adapter.py` | ✅ Done |
| L3.5 | Adapter: NpmAdapter, PipAdapter, ChocoAdapter/BrewAdapter | Teil von L3.4 | ✅ Done |
| L3.6 | `ToolDiscoveryEngine` — 4-Phasen-Pipeline | NEU: `services/tool_discovery_engine.py` | ✅ Done |
| L3.7 | Discovery-Integration in Planner bei `command not found` | `agent.py` / `tool_execution_manager.py` | ⬜ Offen |
| L3.8 | `Probe-Before-Execute` — `which`/`--version` vor Command | `tools.py` `run_command` | ✅ Done |

**Deliverables:**
```
services/tool_knowledge_base.py     → ToolKnowledgeBase + ToolKnowledge dataclass
services/package_manager_adapter.py → Protocol + Npm/Pip/Choco/Brew Adapter
services/tool_discovery_engine.py   → 4-Phasen-Discovery-Pipeline
tools.py                            → probe_command() helper
```

**Discovery-Pipeline:**
```
Capability benötigt
     │
     ▼
┌─────────────────┐  < 1ms
│ 1. KnowledgeBase │──────→ Cached Solution? → JA → return
│    (SQLite)      │
└────────┬────────┘
         │ NEIN
         ▼
┌─────────────────┐  1–3s
│ 2. LLM-Reasoning │──────→ Model kennt Tool? → confidence > 0.8 → return
│    (kein Web)    │
└────────┬────────┘
         │ confidence < 0.8
         ▼
┌─────────────────┐  2–5s
│ 3. Pkg-Manager   │──────→ npm/pip/apt search → Kandidaten → return
│    Search        │
└────────┬────────┘
         │ nichts gefunden
         ▼
┌─────────────────┐  3–8s
│ 4. Web-Search    │──────→ Fallback → Candidates → return
│    (web_fetch)   │
└─────────────────┘
```

---

### Level 4: Provisioning & Governance (Score 9→9.3) — 2 Wochen

| # | Task | Datei | Status |
|---|---|---|---|
| L4.1 | `ToolProvisioner` — Install + Verify Pipeline | NEU: `services/tool_provisioner.py` | ✅ |
| L4.2 | `ProvisioningPolicy` — mode (auto/ask_user/deny), Scopes, Limits | NEU: `services/provisioning_policy.py` | ✅ |
| L4.3 | User-Approval-Flow via WebSocket (analog command_policy_override) | `ws_handler.py` + `agent.py` | ⬜ |
| L4.4 | Sandbox-Install-Strategien: venv, node_modules, --user | `tool_provisioner.py` | ✅ |
| L4.5 | `EnvironmentSnapshot` + Rollback bei fehlgeschlagener Installation | NEU: `services/environment_snapshot.py` | ✅ |
| L4.6 | Install-Audit-Log (was wurde wann von wem installiert) | `tool_provisioner.py` + Telemetry | ✅ |

**Deliverables:**
```
services/tool_provisioner.py        → ToolProvisioner + ensure_available()
services/provisioning_policy.py     → ProvisioningPolicy (frozen dataclass)
services/environment_snapshot.py    → Snapshot + Rollback
ws_handler.py                       → install_approval event type
```

**Kritische Governance-Regeln:**
```
1. NIEMALS `sudo` oder admin-elevation ohne expliziten User-Approval
2. Scope-Sandbox: pip install → immer in venv; npm install → immer lokal
3. Size-Limit: Default 500MB pro Installation
4. Blocked-Packages-List: Konfigurierbar, Default enthält bekannte Malware-Packages
5. Rollback: Bei Verify-Failure → automatisch deinstallieren
```

---

### Level 5: Intelligence & Adaptation (Score 9.3→9.7) — 2 Wochen

| # | Task | Datei | Status |
|---|---|---|---|
| L5.1 | `AdaptiveToolSelector` — gewichtetes Scoring (Erfolgsrate, Speed, Platform) | NEU: `services/adaptive_tool_selector.py` | ✅ |
| L5.2 | `ToolChainPlanner` — Format-Conversion-Graph + shortest_path | NEU: `services/tool_chain_planner.py` | ⬜ |
| L5.3 | `ExecutionPatternDetector` — Anti-Patterns (Brute-Force-Install, Version-Roulette) | NEU: `services/execution_pattern_detector.py` | ✅ |
| L5.4 | `ExecutionContract` — Pre/Post-Conditions pro Tool-Call | NEU: `services/execution_contract.py` | ✅ |
| L5.5 | Learning Loop: OutcomeVerdict → KnowledgeBase → bessere Selection | Integration | ✅ |

**Scoring-Formel für AdaptiveToolSelector:**
```
score = (success_rate × 0.40)
      + (speed_score × 0.20)
      + (platform_fit × 0.15)
      + (user_preference × 0.15)
      + (recency × 0.10)
```

---

### Level 6: Mastery (Score 9.7→10) — 3–4 Wochen

| # | Task | Datei | Status |
|---|---|---|---|
| L6.1 | `ToolSynthesizer` — Ad-hoc Script-Generation in Sandbox | NEU: `services/tool_synthesizer.py` | ✅ |
| L6.2 | `SelfHealingLoop` — Root-Cause-Analyse + Recovery-Plan + Retry | NEU: `services/self_healing_loop.py` | ✅ |
| L6.3 | `ToolEcosystemMap` — Graph aller Tool-Ökosysteme | NEU: `services/tool_ecosystem_map.py` | ✅ |
| L6.4 | End-to-End "Zero-Knowledge" Test: Agent löst Aufgabe mit unbekanntem Tool | `benchmarks/` | ✅ |
| L6.5 | Graceful Degradation: Teilresultat + Erklärung statt nur "Failed" | `agent.py` Synthesizer | ✅ |
| L6.6 | Progressive Confidence Display im Frontend | Frontend + WebSocket | ⬜ |

---

## 5. Dos — Die 15 Gebote

### D-1: Error-Taxonomie IMMER auswerten

Jeder Tool-Fehler MUSS klassifiziert werden bevor eine Retry-Entscheidung fällt.

```python
# RICHTIG:
category = self._retry_strategy.classify_error(error_text)
decision = self._retry_strategy.decide(error_text=..., retry_class=..., attempt=..., max_retries=...)
if decision.should_retry:
    await asyncio.sleep(decision.delay_seconds)
    # retry
else:
    # decision.strategy → "replan" | "escalate" | "skip"

# FALSCH:
if "timeout" in str(error).lower():
    # retry blindly
```

**Warum:** Blindes Retry bei `permission denied` verschwendet Versuche. Bei `missing_dependency` bringt Retry nichts — nur Discovery + Install hilft.

---

### D-2: Outcome IMMER verifizieren

Jeder erfolgreiche Tool-Call (kein Exception) MUSS durch den OutcomeVerifier.

```python
# RICHTIG:
result = await run_tool(...)
verdict = self._outcome_verifier.verify(tool=tool, result=result, args=args, exit_code=exit_code)
if verdict.status == "failed":
    # Behandle als Fehler, nicht als Erfolg
if verdict.status == "suspicious":
    # Logge Warning, gib Hinweis ans LLM

# FALSCH:
result = await run_tool(...)
return result  # Keine Prüfung ob das Ergebnis sinnvoll ist
```

**Warum:** `exit_code=0` bedeutet nicht "Erfolg". `pandoc` gibt exit 0 auch wenn die Ausgabe-Datei leer ist.

---

### D-3: PlatformInfo VOR jeder Command-Generierung prüfen

```python
# RICHTIG:
platform = detect_platform()
if platform.is_windows:
    cmd = "Get-ChildItem -Recurse"
else:
    cmd = "find . -type f"

# FALSCH:
cmd = "find . -type f"  # Bricht auf Windows
```

**Warum:** 95% der "command not found"-Fehler kommen daher, dass LLMs Linux-Commands auf Windows vorschlagen.

---

### D-4: Probe-Before-Execute bei unbekannten Commands

```python
# RICHTIG (Muster für Level 3):
async def probe_command(cmd: str) -> ProbeResult:
    which_result = await run_command(f"Get-Command {cmd}" if is_windows else f"which {cmd}")
    if "not found" in which_result or "not recognized" in which_result:
        return ProbeResult(available=False)
    version = await run_command(f"{cmd} --version")
    return ProbeResult(available=True, version=version)

# FALSCH:
await run_command("pandoc input.md -o output.pdf")  # Und hoffen dass es installiert ist
```

---

### D-5: Installation IMMER sandboxen

```python
# RICHTIG:
if package_type == "python":
    await run_command(f"pip install --user {package}")
    # oder: in virtuelle Umgebung
elif package_type == "node":
    await run_command(f"npm install {package}")  # lokal, nicht -g
elif package_type == "system":
    # NUR mit explizitem User-Approval
    approved = await request_user_approval(f"Install {package} system-wide?")
    if not approved:
        return ProvisionResult(status="user_denied")

# FALSCH:
await run_command(f"sudo apt install -y {package}")  # Blind, global, ohne Approval
```

---

### D-6: Discovery mit Timeout begrenzen

```python
# RICHTIG:
constraints = DiscoveryConstraints(
    max_search_time_seconds=15,
    max_candidates=5,
    prefer_installed=True,
    prefer_lightweight=True,
)
candidates = await discovery_engine.discover(
    capability_needed="pdf_conversion",
    constraints=constraints,
)

# FALSCH:
# Endlose Web-Suche nach dem perfekten Tool
while not found:
    candidates = await web_search(...)
```

---

### D-7: Knowledge-Base nach JEDEM Erfolg/Misserfolg updaten

```python
# RICHTIG:
verdict = verifier.verify(tool=tool, result=result, ...)
await knowledge_base.learn_from_outcome(
    tool_command=tool,
    capability=capability,
    platform=platform.os_name,
    success=verdict.status == "verified",
    duration=elapsed_seconds,
)

# FALSCH:
# Tool-Ergebnis nutzen und vergessen
```

---

### D-8: Telemetrie-Spans um JEDEN Tool-Call wrappen

```python
# RICHTIG:
span_id = telemetry.start_span(tool_name=tool, args=args)
try:
    result = await execute_tool(tool, args)
    telemetry.end_span(span_id, outcome="success", exit_code=0)
except Exception as exc:
    telemetry.end_span(span_id, outcome="failed", error_class=classify_error(str(exc)))
    raise

# FALSCH:
# Lifecycle-Event feuern und hoffen dass jemand zuhört
emit_event("tool_started", {"tool": tool})
result = await execute_tool(tool, args)
emit_event("tool_completed", {"tool": tool})
```

---

### D-9: Hook-Fehler den Run NIEMALS crashen lassen

```python
# RICHTIG:
async def invoke_hook_safe(hook_name: str, payload: dict, timeout_ms: int = 500):
    try:
        await asyncio.wait_for(invoke_hooks(hook_name, payload), timeout=timeout_ms / 1000)
    except asyncio.TimeoutError:
        logger.warning(f"Hook {hook_name} timed out after {timeout_ms}ms")
    except Exception as exc:
        logger.error(f"Hook {hook_name} failed: {exc}")

# FALSCH:
await invoke_hooks(hook_name, payload)  # Exception → Run crasht
```

---

### D-10: Tool-Chains explizit planen, nicht Chain-of-Thought improvisieren

```python
# RICHTIG (Level 5):
chain = await chain_planner.plan_chain(
    input_type="text/markdown",
    output_type="image/png",
    context=user_request,
)
# chain = [Step("pandoc", md→pdf), Step("magick", pdf→png)]
for step in chain.steps:
    result = await execute_step(step)
    if not verify(result):
        # Fallback to alternative chain
        break

# FALSCH:
# LLM entscheidet spontan den nächsten Schritt → unvorhersagbar
```

---

### D-11: Replan-Mechanismus bei error_only beibehalten + erweitern

Der bestehende `_classify_tool_results_state() → error_only → Replan` ist ein exzellentes Pattern. Erweitern um:
- `partial_error` (manche Tools ok, manche nicht) → partial replan
- `all_suspicious` (OutcomeVerifier sagt "suspicious") → warnen + optional replan

---

### D-12: Single-Lane-Invariante NIEMALS brechen

Zwei gleichzeitige `run()` Calls mit gleicher `session_id` dürfen NIE parallel laufen.

---

### D-13: Loop-Detection-Schwellwerte konservativ halten

```python
# Die goldenen Defaults — nicht ändern:
loop_warn_threshold = 2
loop_critical_threshold = 5
loop_circuit_breaker_threshold = 9
generic_repeat_enabled = True
ping_pong_enabled = True
poll_no_progress_enabled = True
```

---

### D-14: ToolSpec-Schemas IMMER `additionalProperties: false` setzen

Jedes Tool-Schema muss geschlossen sein. Offene Schemas → LLM erfindet Parameter → Parse-Fehler.

---

### D-15: Fallback-Chains für häufige Capabilities vorhalten

```python
FALLBACK_CHAINS: dict[str, list[tuple[str, str]]] = {
    "pdf_generation": [
        ("pandoc", "pandoc {input} -o {output}.pdf"),
        ("wkhtmltopdf", "wkhtmltopdf {input} {output}.pdf"),
        ("weasyprint", "weasyprint {input} {output}.pdf"),
    ],
    "image_resize": [
        ("magick", "magick {input} -resize {size} {output}"),
        ("ffmpeg", "ffmpeg -i {input} -vf scale={size} {output}"),
    ],
    "json_query": [
        ("jq", "jq '{query}' {input}"),
        ("python", "python -c \"import json; ...\""),
    ],
}
```

---

## 6. Don'ts — Die 12 Todsünden

### X-1: ❌ Text-basiertes `[TOOL_CALL]`-Parsing als Default behalten

FC ist aktiviert (Phase 0). Text-Parsing ist Fallback, nicht Default. Wenn ein Provider FC unterstützt → FC nutzen, immer.

**Gate:** `repair_tool_selection_json()` wird bei FC-Providern in < 5% aller Selections aufgerufen.

---

### X-2: ❌ Retry ohne Klassifikation

```python
# NIEMALS SO:
except Exception:
    retry()

# Immer Fehler klassifizieren, dann entscheiden:
category = classify_error(str(exc))
if category == "permission":
    escalate()
elif category == "missing_dependency":
    discover_and_install()
elif category == "transient":
    backoff_and_retry()
```

---

### X-3: ❌ `sudo` / `admin` ohne User-Approval

Kein Tool-Call darf jemals mit elevated Privileges laufen ohne explizite User-Bestätigung via WebSocket. Die bestehende `command_policy_override` Mechanik (in `_retry_run_command_after_policy_approval`) ist das Vorbild.

---

### X-4: ❌ Globale Package-Installation

```python
# NIEMALS:
run_command("pip install pandas")           # → System-Python kontaminiert
run_command("npm install -g typescript")     # → Globale node_modules

# IMMER:
run_command("pip install --user pandas")     # → User-Scope
run_command("npm install typescript")        # → lokale node_modules
run_command("pip install pandas", cwd=venv)  # → In venv
```

---

### X-5: ❌ OpenClaw's Glob-Policy 1:1 portieren

Glob-Matching (`tools/read_*`) ist komplex und fehleranfällig. Stattdessen: **Tool-Profile als benannte Sets.**

```python
# GUT: Benannte Profile
TOOL_PROFILES = {
    "read_only": {"list_dir", "read_file", "file_search", "grep_search", "get_changed_files"},
    "coding": ...,
    "research": ...,
}

# SCHLECHT: Glob-Matching
allow: "tools/read_*"  # Was ist "read"? read_file? read_url? read_database?
```

---

### X-6: ❌ LLM für deterministisch lösbare Entscheidungen nutzen

```python
# FALSCH: LLM fragen ob eine Datei existiert
llm_answer = await llm("Does the file output.pdf exist?")

# RICHTIG: Deterministisch prüfen
import os
exists = os.path.isfile("output.pdf")
```

Der OutcomeVerifier ist deterministisch (< 1ms). LLM-Judge nur als letztes Mittel für semantische Prüfungen.

---

### X-7: ❌ Discovery ohne Timeout

Tool-Discovery darf NIE endlos laufen. Harte Grenzen:
- KnowledgeBase-Lookup: < 100ms
- LLM-Reasoning: < 5s
- Package-Manager-Suche: < 10s
- Web-Search-Fallback: < 15s
- **Gesamt-Discovery: ≤ 30s**

---

### X-8: ❌ ToolExecutionError durch den Stack unkontrolliert propagieren

```python
# FALSCH:
async def run():
    result = await tool.execute()  # Exception → HTTP 500

# RICHTIG:
async def run():
    try:
        result = await tool.execute()
    except ToolExecutionError as exc:
        # In Replan-Kontext encodieren
        return f"[error] {tool}: {exc}"
```

---

### X-9: ❌ Mehr als 3 Retry-Versuche für dieselbe Fehler-Kategorie

```python
# RICHTIG:
max_retries_per_category = {
    "transient": 3,
    "resource_exhaustion": 1,
    "missing_dependency": 0,  # Retry sinnlos → Discovery
    "permission": 0,          # Retry sinnlos → Escalate
    "invalid_args": 0,        # Retry sinnlos → Replan
    "crash": 0,               # Retry sinnlos → Replan
}
```

---

### X-10: ❌ Knowledge-Base-Einträge ohne Confidence-Decay

```python
# FALSCH: Ein Erfolg vor 6 Monaten = gleiche Confidence wie gestern
confidence = success_count / (success_count + failure_count)

# RICHTIG: Time-Decay
import math
days_since = (now - last_success).days
decay = math.exp(-0.01 * days_since)  # ~0.37 nach 100 Tagen
confidence = (success_count / (success_count + failure_count)) * decay
```

---

### X-11: ❌ Tool-Schemas ohne `additionalProperties: false`

Alle 18 Core-Tools haben bereits `additionalProperties: false`. Dieses Pattern muss für JEDES neue Tool und JEDES MCP-Tool erzwungen werden.

---

### X-12: ❌ Skills inline im System-Prompt statt Lazy-Load

Das Starter-Kit hat ein **überlegenes** Skills-Pattern: `SkillsService` + `read_file(SKILL.md)`. Nicht ersetzen durch OpenClaw's statische `## Tooling`-Sektion.

---

## 7. Akzeptanzkriterien (40 messbare Gates)

> Jedes Kriterium ist binär (pass/fail) oder hat einen messbaren Schwellenwert. Tests müssen VOR Merge grün sein.

### Level 1: Foundation

| # | Kriterium | Typ | Schwellenwert | Test-Methode |
|---|---|---|---|---|
| **AC-01** | PlatformInfo im System-Prompt sichtbar | Binär | Prompt enthält `os/arch/shell` | Unit: Check prompt output |
| **AC-02** | Hook-Fehler crashen Run nicht | Binär | Run completed trotz Hook-Exception | Integration: throwing hook |
| **AC-03** | Hook-Timeout ≤ 500ms | Schwelle | Slow hook wird nach 500ms abgebrochen | Unit: asyncio.sleep(5) hook |
| **AC-04** | Tool-Profile funktionieren | Binär | `allow_profile="read_only"` → nur Lese-Tools | Unit: resolve effective tools |
| **AC-05** | OutcomeVerifier prüft file_exists | Binär | `file_exists("output.pdf")` → True/False check | Unit: mock file system |
| **AC-06** | PII-Redaction in Results aktiv | Binär | E-Mail/Telefon werden maskiert vor LLM-Context | Unit: regex match |

### Level 2: Telemetry

| # | Kriterium | Typ | Schwellenwert | Test-Methode |
|---|---|---|---|---|
| **AC-07** | Jeder Tool-Call hat einen Span | Binär | `start_span`/`end_span` für jeden Call | Integration: span count == call count |
| **AC-08** | Span enthält duration_ms | Binär | `end_time - start_time > 0` | Unit |
| **AC-09** | Span enthält outcome | Binär | outcome ∈ {"success", "failed", "retried", "skipped"} | Unit |
| **AC-10** | `get_tool_stats()` liefert Aggregation | Binär | Pro Tool: count, success_rate, avg_duration | Unit |
| **AC-11** | REST `/api/tools/stats` erreichbar | Binär | HTTP 200 + JSON | Integration |
| **AC-12** | Session-Trace als JSON exportierbar | Binär | Valides JSON mit Span-Baum | Unit |

### Level 3: Discovery

| # | Kriterium | Typ | Schwellenwert | Test-Methode |
|---|---|---|---|---|
| **AC-13** | KnowledgeBase speichert Erfolge | Binär | `learn_from_outcome(success=True)` → Entry mit confidence > 0 | Unit |
| **AC-14** | KnowledgeBase findet gespeicherte Tools | Binär | `find_tools_for_capability("pdf")` → Kandidaten zurück | Unit |
| **AC-15** | Confidence-Decay nach 90 Tagen < 0.5 | Schwelle | Entry mit last_success vor 90 Tagen → confidence < 0.5 | Unit |
| **AC-16** | Discovery-Timeout ≤ 30s | Schwelle | Gesamte Discovery-Pipeline maximal 30 Sekunden | Integration mit Timeout |
| **AC-17** | PackageManagerAdapter.is_available() korrekt | Binär | Mindestens pip/npm wird erkannt | Unit |
| **AC-18** | PackageManagerAdapter.search() liefert Ergebnisse | Binär | `pip_adapter.search("pandas")` → ≥ 1 Ergebnis | Integration |
| **AC-19** | Probe-Before-Execute erkennt fehlende Commands | Binär | `probe_command("nonexistent_tool_xyz")` → available=False | Unit |
| **AC-20** | Discovery wird bei "command not found" getriggert | Binär | RetryStrategy category=missing_dependency → Discovery-Phase | Integration |

### Level 4: Provisioning

| # | Kriterium | Typ | Schwellenwert | Test-Methode |
|---|---|---|---|---|
| **AC-21** | User-Approval-Flow für Installation | Binär | WebSocket `install_approval_request` + Response | Integration |
| **AC-22** | Install in Sandbox (nicht global) | Binär | pip: --user oder venv; npm: lokal; kein sudo | Unit: Command-Inspection |
| **AC-23** | Install-Verify schlägt an bei Miss | Binär | Nach Install: `which tool` → nicht gefunden → Retry/Alternative | Integration |
| **AC-24** | ProvisioningPolicy.mode="deny" blockt | Binär | Keine Installation bei mode=deny | Unit |
| **AC-25** | Blocked-Packages werden abgelehnt | Binär | Package in blocked_packages → ProvisionResult.status="policy_denied" | Unit |
| **AC-26** | Install-Audit enthält Timestamp + Package + Scope | Binär | Log-Entry nach Installation | Unit |
| **AC-27** | Rollback bei Verify-Failure | Binär | Install ok + Verify fail → uninstall attempt | Integration |
| **AC-28** | Size-Limit prüfen (Default 500MB) | Schwelle | Package > 500MB → Approval-Required | Unit (mock size check) |

### Level 5: Intelligence

| # | Kriterium | Typ | Schwellenwert | Test-Methode |
|---|---|---|---|---|
| **AC-29** | AdaptiveSelector nutzt success_rate | Binär | Tool mit 90% success_rate wird über 50% Tool bevorzugt | Unit |
| **AC-30** | Scoring-Gewichte konfigurierbar | Binär | Config-Parameter für alle 5 Gewichte | Unit |
| **AC-31** | ToolChain plant Multi-Step | Binär | markdown→png → Chain: [md→pdf, pdf→png] | Unit |
| **AC-32** | PatternDetector erkennt Brute-Force-Install | Binär | 5 verschiedene Install-Versuche → Warning | Unit |
| **AC-33** | ExecutionContract Pre-Check greift | Binär | Precondition file_exists fail → kein Tool-Call | Unit |
| **AC-34** | Learning-Loop schließt sich | Binär | Success → KnowledgeBase → nächster Request bevorzugt dieses Tool | Integration |

### Level 6: Mastery

| # | Kriterium | Typ | Schwellenwert | Test-Methode |
|---|---|---|---|---|
| **AC-35** | Synthesizer generiert lauffähiges Script | Binär | Generiertes Script produziert erwartetes Output | Sandbox-Test |
| **AC-36** | SelfHealing löst Environment-Problem | Binär | Fehlende PATH-Entry → Fix → Retry → Success | Integration |
| **AC-37** | Zero-Knowledge-Test bestanden | Binär | Agent löst Aufgabe mit Tool das er noch nie gesehen hat | E2E Benchmark |
| **AC-38** | Graceful Degradation bei Unlösbarkeit | Binär | Wenn nichts klappt: Teilresultat + Erklärung statt "Failed" | Integration |
| **AC-39** | EcosystemMap kennt ≥ 3 Ökosysteme | Schwelle | Node.js, Python, System-Tools | Unit |
| **AC-40** | Gesamter Tool-Pipeline-Score ≥ 9.5/10 | Schwelle | Benchmark-Suite mit 50 Szenarien, ≥ 47 bestanden | Benchmark |

---

## 8. Risiken & Mitigations

| # | Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|---|---|---|---|---|
| R-1 | Discovery findet gefährliches Package | Mittel | Kritisch | `blocked_packages` Liste + User-Approval mandatory |
| R-2 | Auto-Install bricht System | Niedrig | Kritisch | Sandbox-First (venv/node_modules), Rollback, Size-Limit |
| R-3 | Knowledge-Base wird zu groß | Niedrig | Mittel | TTL von 180 Tagen, LRU-Eviction, Max 10k Entries |
| R-4 | Discovery-Pipeline zu langsam | Mittel | Mittel | 30s Hard-Timeout, KnowledgeBase-Cache-First |
| R-5 | LLM halluziniert Tool-Namen | Hoch | Mittel | Probe-Before-Execute Pattern (D-4) + Verify |
| R-6 | Infinite Retry-Loop | Niedrig | Hoch | max_retries_per_category + Circuit-Breaker (bestehend) |
| R-7 | Hook-Code crasht Production | Mittel | Hoch | Hook-Isolation + Timeout (D-9, AC-02/03) |
| R-8 | Provisioner installiert inkompatible Version | Mittel | Mittel | `--version` Post-Check + Compatibility-Matrix |
| R-9 | ToolSynthesizer generiert unsicheren Code | Mittel | Kritisch | Safety-Check vor Sandbox-Execution, kein Network/FS-Access outside workspace |
| R-10 | Knowledge-Base Poisoning (erfolgreich gelernt aber falsch) | Niedrig | Mittel | Confidence-Minimum von 3 Erfolgen bevor ein Tool "bevorzugt" wird |

---

## 9. Timeline & Aufwandsschätzung

```
Woche     1    2    3    4    5    6    7    8    9   10   11   12
         ─────┬────┬─────────┬─────────┬─────────┬────────────────
Level 1  ████ │    │         │         │         │
         Found│    │         │         │         │
         ─────┘    │         │         │         │
Level 2       ████ │         │         │         │
         Telemetry │         │         │         │
              ─────┘         │         │         │
Level 3            ██████████│         │         │
                   Discovery │         │         │
                   ──────────┘         │         │
Level 4                      ██████████│         │
                             Provision │         │
                             ──────────┘         │
Level 5                                ██████████│
                                       Intellig. │
                                       ──────────┘
Level 6                                          ████████████████
                                                 Mastery

Score:   7    8   8.5       9        9.3        9.7           10
```

### Investment pro Level

| Level | Neue Dateien | Geschätzte LOC | Neue Tests | Aufwand |
|---|---|---|---|---|
| L1: Foundation | 0 (erweitern) | ~200 | ~15 | 1 Woche |
| L2: Telemetry | 1 | ~400 | ~20 | 1 Woche |
| L3: Discovery | 3 | ~1200 | ~40 | 2–3 Wochen |
| L4: Provisioning | 3 | ~800 | ~30 | 2 Wochen |
| L5: Intelligence | 4 | ~1000 | ~35 | 2 Wochen |
| L6: Mastery | 3 | ~1500 | ~30 | 3–4 Wochen |
| **Gesamt** | **14** | **~5100** | **~170** | **11–13 Wochen** |

### Meilensteine

| Meilenstein | Wann | Gate |
|---|---|---|
| **Bronze (8/10)** | Woche 2 | L1 + L2 complete, alle AC-01 bis AC-12 grün |
| **Silver (9/10)** | Woche 5 | L3 complete, Agent findet + nutzt unbekannte Tools, AC-13 bis AC-20 grün |
| **Gold (9.5/10)** | Woche 9 | L4 + L5 complete, autonome Installation + adaptives Lernen, AC-21 bis AC-34 grün |
| **Platinum (10/10)** | Woche 12 | L6 complete, Zero-Knowledge-Test bestanden, AC-35 bis AC-40 grün |

---

## Anhang: File-Map (wo alles hinkommt)

```
backend/app/services/
├── tool_retry_strategy.py          ✅ Existiert (L1)
├── tool_outcome_verifier.py        ✅ Existiert (L1)
├── platform_info.py                ✅ Existiert (L1)
├── tool_telemetry.py               ⬜ Neu (L2)
├── tool_knowledge_base.py          ⬜ Neu (L3)
├── package_manager_adapter.py      ⬜ Neu (L3)
├── tool_discovery_engine.py        ⬜ Neu (L3)
├── tool_provisioner.py             ⬜ Neu (L4)
├── provisioning_policy.py          ⬜ Neu (L4)
├── environment_snapshot.py         ⬜ Neu (L4)
├── adaptive_tool_selector.py       ⬜ Neu (L5)
├── tool_chain_planner.py           ⬜ Neu (L5)
├── execution_pattern_detector.py   ⬜ Neu (L5)
├── execution_contract.py           ⬜ Neu (L5)
├── tool_synthesizer.py             ⬜ Neu (L6)
├── self_healing_loop.py            ⬜ Neu (L6)
└── tool_ecosystem_map.py           ⬜ Neu (L6)

backend/tests/
├── test_tool_retry_strategy.py     ✅ Existiert (27 Tests)
├── test_tool_outcome_verifier.py   ✅ Existiert (16 Tests)
├── test_platform_info.py           ✅ Existiert (11 Tests)
├── test_tool_telemetry.py          ⬜ Neu (~20 Tests)
├── test_tool_knowledge_base.py     ⬜ Neu (~25 Tests)
├── test_package_manager_adapter.py ⬜ Neu (~15 Tests)
├── test_tool_discovery.py          ⬜ Neu (~20 Tests)
├── test_tool_provisioner.py        ⬜ Neu (~20 Tests)
├── test_provisioning_policy.py     ⬜ Neu (~10 Tests)
├── test_adaptive_selector.py       ⬜ Neu (~15 Tests)
├── test_tool_chain_planner.py      ⬜ Neu (~15 Tests)
├── test_execution_patterns.py      ⬜ Neu (~10 Tests)
├── test_execution_contract.py      ⬜ Neu (~10 Tests)
├── test_tool_synthesizer.py        ⬜ Neu (~10 Tests)
├── test_self_healing.py            ⬜ Neu (~10 Tests)
└── test_ecosystem_map.py           ⬜ Neu (~10 Tests)
```

---

> **Das ist der Weg von 7/10 zu 10/10.**  
> Kein Feature ist optional. Jedes Level baut auf dem vorherigen auf.  
> Jedes Akzeptanzkriterium muss grün sein bevor das nächste Level beginnt.  
> Der Agent soll nicht "ein bisschen besser" werden — er soll **Gold** werden.
