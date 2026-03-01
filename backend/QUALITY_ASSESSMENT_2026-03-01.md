# Quality Assessment – Backend

Stand: 2026-03-01  
Scope: `backend/app/` inkl. Tests  
Methode: Unabhängige Code-Analyse (keine Vorkenntnisse aus architecture.md genutzt)

---

## Zusammenfassung

Das Backend ist funktional und zeigt sorgfältige Arbeit in mehreren Bereichen (strukturierte Lifecycle-Events, Policy-Layering, Fehler-Mapping, WebSocket-Sequencing). Es gibt aber vier kritische Problembereiche, die das System bei Wachstum oder Produktionsbetrieb ernsthaft belasten werden:

| Bereich | Bewertung |
|---|---|
| Funktionale Korrektheit | ⚠️ 1 Test-Fehler (echter Bug) |
| Code-Struktur | ❌ zwei God-Files mit zusammen ~5100 Zeilen |
| Testbarkeit | ⚠️ DI fehlt in Kernkomponenten |
| Produktionsreife | ❌ stub-Auth, unbounded In-Memory-Registries |
| Config-Qualität | ⚠️ verschachtelte Fallback-Ketten schwer nachvollziehbar |

---

## 1. Laufende Tests

```
1 failed, 144 passed
```

### 1.1 Echter Bug: `test_real_api_subrun_spawn_and_agent_workflow_smoke`

**Fehler:**
```
assert run_status in {"completed", "failed"}
AssertionError: assert 'error' in {'completed', 'failed'}
```

**Ursache:** Das System gibt `run_status = 'error'` zurück. Der Test erwartet nur `'completed'` oder `'failed'` als Terminal-States. Es gibt zwei mögliche Ursachen:

1. Das System emittiert einen Status `'error'`, der kein offiziell registered Terminal-State ist (Bug im System).
2. Der Test deckt nicht alle gültigen Terminal-States ab (Bug im Test).

**Empfehlung:** Prüfen welche `run_status`-Werte im `state_store` wirklich als terminal gelten. `'error'` muss entweder als Terminal-State registriert werden **oder** die Code-Pfade, die `'error'` setzen, müssen auf `'failed'` normalisiert werden. Konsistenter Terminal-State-Vertrag ist Pflicht.

---

## 2. Code-Struktur

### 2.1 God-Files ❌

| Datei | Zeilen |
|---|---|
| `app/main.py` | **2934** |
| `app/agent.py` | **2194** |
| `app/orchestrator/subrun_lane.py` | 652 |
| `app/ws_handler.py` | 498 |

`main.py` vereinigt: FastAPI-App-Wiring, CORS-Konfiguration, alle REST-Endpoint-Handler, Lifespan-Logik, Startup-Cleanup, DI-Wiring, Runtime-Switch-Logik, Subrun-Spawn-Handler, Guardrail-/Policy-Auflösung, Idempotency-Registry-Verwaltung und diverse Helper-Funktionen. Das ist keine Routing-Datei, sondern eine monolithische Catch-All-Datei.

`agent.py` enthält `HeadAgent` (plus `CoderAgent` und `ReviewAgent` als offensichtliche Ableitungen/Varianten) mit einem `run()`-Methode, die Guardrail-Check, Memory-Update, Context-Reduktion, Planning, Tool-Selection, Tool-Execution, Synthese und Lifecycle-Emission in einer Methode orchestriert – mit hunderten von Zeilen Inline-Logik.

**Konsequenzen:**
- Pull-Requests auf diese Dateien sind schwer zu reviewen.
- Merge-Konflikte bei paralleler Arbeit sind unvermeidbar.
- Kognitive Last beim Debuggen ist hoch.

**Empfehlung:** `main.py` aufteilen: Endpoint-Gruppen in eigene Router-Dateien, DI-Container in eigene Datei, Startup-/Shutdown-Logik isolieren. `agent.py`-Methode `run()` in diskrete Step-Methoden aufteilen, die jeweils testbar sind.

---

### 2.2 `WsHandlerDependencies` – Überbreiter Dependency-Bag ⚠️

```python
@dataclass
class WsHandlerDependencies:
    logger: Any
    settings: Any
    agent: Any
    agent_registry: dict[str, Any]
    runtime_manager: Any
    state_store: Any
    subrun_lane: Any
    sync_custom_agents: Callable[[], None]
    normalize_agent_id: Callable[...]
    resolve_tool_policy_with_preset: Callable[...]
    looks_like_review_request: Callable[[str], bool]
    looks_like_coding_request: Callable[[str], bool]
    resolve_agent: Callable[...]
    state_append_event_safe: Callable[...]
    state_mark_failed_safe: Callable[...]
    state_mark_completed_safe: Callable[...]
    lifecycle_status_from_stage: Callable[...]
    primary_agent_id: str
    coder_agent_id: str
    review_agent_id: str
```

19 Felder, davon viele `Any`-typed Callables. Der WS-Handler kennt die interne Struktur von `main.py` implizit. Änderungen an `main.py`-Infrastruktur erfordern Änderungen am `WsHandlerDependencies`-Dataclass. Typ-Safety ist faktisch aufgehoben.

**Empfehlung:** Smallere, typsichere Interfaces schneiden. Callables durch ein typed Protocol ersetzen.

---

### 2.3 `HeadAgent` – Kein Dependency Injection ⚠️

```python
class HeadAgent:
    def __init__(self, name: str | None = None, role: str = "head-agent"):
        self.client = LlmClient(base_url=settings.llm_base_url, model=settings.llm_model)
        self.memory = MemoryStore(max_items_per_session=settings.memory_max_items, ...)
        self.tools = AgentTooling(workspace_root=settings.workspace_root, ...)
        self.model_registry = ModelRegistry()
        self.context_reducer = ContextReducer()
```

Alle Abhängigkeiten werden intern instantiiert, direkt aus `settings`. Kein DI. Unit-Tests müssen Umgebungsvariablen setzen oder intern mocken – was spröde ist.

`configure_runtime()` löst dieses Problem nicht, sondern fügt einen zweiten Konstruktionspfad hinzu, der zusätzlich alle Sub-Agents neu baut:

```python
def configure_runtime(self, base_url: str, model: str) -> None:
    self.client = LlmClient(base_url=base_url, model=model)
    self._build_sub_agents()  # ← rebuilds planner, tool_selector, synthesizer komplett
```

Das bedeutet: jeder Runtime-Switch des LLM-Clients löst eine komplette Neukonstruktion aller Sub-Agents aus. Seiteneffekte bei laufenden Requests sind möglich, wenn `configure_runtime` concurrent aufgerufen wird.

---

### 2.4 `AgentContract.constraints` – Class-Level-Attribute ⚠️

```python
class HeadAgentAdapter(AgentContract):
    constraints = AgentConstraints(
        max_context=settings.max_user_message_length,  # ← read at class definition time
        temperature=0.3,
        ...
    )
```

`settings.max_user_message_length` wird beim Klassenimport ausgewertet. Wenn Settings per Env-Override geändert werden und die Klasse bereits importiert ist, wird der neue Wert nicht angewandt. `constraints` ist ein geteiltes Klassenattribut – alle Instanzen teilen dasselbe Objekt.

---

## 3. Konfiguration (`config.py`)

### 3.1 Verschachtelte Fallback-Ketten ⚠️

```python
head_agent_plan_prompt: str = os.getenv(
    "HEAD_AGENT_PLAN_PROMPT",
    os.getenv(
        "HEAD_AGENT_SYSTEM_PROMPT",
        os.getenv(
            "AGENT_PLAN_PROMPT",
            os.getenv(
                "AGENT_SYSTEM_PROMPT",
                "You are a neutral head agent...",
            ),
        ),
    ),
)
```

Einige Felder haben 4-stufige `os.getenv()`-Fallback-Ketten. Welcher Env-Var tatsächlich wirkt, ist aus dem Code nicht sofort ersichtlich. Das macht operatives Debugging ("welcher Prompt ist aktiv?") aufwändig.

**Empfehlung:** Fallback-Ketten in einer dedizierten Funktion wie `_resolve_prompt(primary, ...)` zusammenfassen und dokumentieren. Optional: ein `/api/debug/settings`-Endpoint (nur in `development`) der die tatsächlich aufgelösten Werte zurückgibt.

### 3.2 `settings` singleton at import time

```python
settings = Settings()  # ← Modul-Level, bei Import ausgewertet
```

Env-Variablen müssen gesetzt sein, **bevor** das Modul importiert wird. In Tests muss deshalb `os.environ` vor dem Import manipuliert werden (z.B. im `conftest.py`). `monkeypatch.setenv` nach dem Import hat keinen Effekt auf bereits ausgewertete Felder.

---

## 4. Produktionsreife / Sicherheit

### 4.1 Stub-Authentifizierung ❌

```python
class RuntimeManager:
    def is_runtime_authenticated(self) -> bool:
        return True  # ← immer True

    async def ensure_api_runtime_authenticated(self) -> None:
        return  # ← tut nichts
```

Beide Methoden sind stubs. Wenn das System in `api`-Mode betrieben wird, gibt es keine tatsächliche Auth-Prüfung. Auch wenn externe Modelle nicht direkt Credentials erfordern – diese Stubs können dazu verleiten, falsche Annahmen über den Auth-Status zu treffen.

### 4.2 Unbounded In-Memory Idempotency-Registry ❌

```python
def idempotency_register(*, idempotency_key: str | None, ..., registry: dict[str, dict], ...):
    registry[idempotency_key] = { "fingerprint": ..., "created_at": ... }
    # Kein TTL, kein Eviction
```

Die Registries wachsen unbegrenzt. Bei kontinuierlichem Betrieb führt dies zu stetig steigendem Speicherverbrauch. Bei Neustart gehen alle Idempotency-Einträge verloren (keine Persistenz), was bei Rolling Deploys zu falschen "first-time"-Antworten führen kann.

### 4.3 CORS-Credentials-Logik dupliziert

In `config.py` wird `cors_allow_credentials` gesetzt. In `main.py` wird er dann nochmals überschrieben:

```python
# config.py
cors_allow_credentials: bool = os.getenv("CORS_ALLOW_CREDENTIALS", ...).strip().lower() in {...}

# main.py
cors_allow_credentials = settings.cors_allow_credentials
if "*" in cors_origins:
    cors_allow_credentials = False  # ← override
```

Zwei Orte kontrollieren dieselbe Einstellung. Das Override in `main.py` ist korrekt (CORS-Spec erlaubt keine Credentials mit Wildcard-Origin), aber die Logik gehört in `config.py` oder in eine dedizierte CORS-Config-Funktion.

---

## 5. Error-Handling

### 5.1 Bare Exception-Klassen

```python
class GuardrailViolation(Exception): pass
class ToolExecutionError(Exception): pass
class LlmClientError(Exception): pass
class RuntimeSwitchError(Exception): pass
```

Alle vier Fehlertypen haben keine Felder, keine Error-Codes, keine strukturierten Metadaten. Fehler werden als freier String transportiert. Das macht programmatisches Error-Handling (z.B. unterschiedliche Retry-Strategien je Error-Code) schwierig.

**Empfehlung:**
```python
@dataclass
class ToolExecutionError(Exception):
    message: str
    tool_name: str | None = None
    error_code: str | None = None
```

---

## 6. Persistenz und Skalierung

### 6.1 `StateStore.list_runs()` – Vollscan ⚠️

```python
def list_runs(self, limit: int = 200) -> list[dict]:
    for run_file in sorted(
        self.runs_dir.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ):
```

Für jeden `list_runs()`-Aufruf werden alle `.json`-Dateien im Run-Verzeichnis gelesen und nach `mtime` sortiert. Bei 10.000 Runs ist das ein O(n)-Filesystem-Scan. Das trifft jeden Request, der eine Run-Liste aufbaut.

### 6.2 Thread-Safety in `MemoryStore._load_from_disk()` ⚠️

Im Konstruktor wird `_load_from_disk()` aufgerufen, bevor der `RLock` initialisiert ist – tatsächlich wird `self._lock = RLock()` vor `_load_from_disk()` gesetzt. Jedoch: `_load_from_disk()` modifiziert `self._store` ohne Lock. Im Konstruktor ist das unkritisch, da noch kein anderer Thread-Zugriff möglich ist. Es aber inkonsistent gegenüber allen anderen Methoden, die den Lock korrekt verwenden.

---

## 7. Test-Qualität

### 7.1 `test_backend_e2e_real_api.py` – kein Skip bei fehlendem API-Zugang

Der Test verbindet sich gegen eine echte API. Ohne verfügbares API-Backend f­ährt der Test durch bis `run_status == 'error'`. Es gibt keinen `pytest.mark.skipif`-Guard für nicht-vorhandene API-Credentials.

**Empfehlung:**
```python
@pytest.mark.skipif(
    not os.getenv("REAL_API_ENABLED"),
    reason="Skipped: REAL_API_ENABLED not set"
)
def test_real_api_subrun_spawn_and_agent_workflow_smoke(...):
```

### 7.2 Test-Abdeckung der Routers ⚠️

Die modularen Control-Plane-Router (`routers/control_runs.py`, `control_sessions.py`, `control_tools.py`, `control_workflows.py`) werden indirekt über `test_control_plane_contracts.py` getestet. Es gibt keine dedizierten Unit-Tests für die Routers-Logik in Isolation. Fehler in diesen Klassen werden nur entdeckt, wenn der Full-Stack-Test fehlschlägt.

### 7.3 Stärken ✅

- `test_ws_handler.py`, `test_subrun_lane.py`, `test_control_plane_contracts.py`, `test_backend_e2e.py` zeigen konsequentes Test-Design mit sauberen Mocks.
- Idempotency-Testhälle sind eigenständig abgedeckt.
- Thread-Safety (`test_memory_store_thread_safety.py`) und Context-Reducer (`test_context_reducer.py`) sind gezielt getestet.
- 144 Tests grün ohne externe Abhängigkeiten – gute CI-Fähigkeit.

---

## 8. Priorisierte Handlungsempfehlungen

### P0 – Bug beheben (sofort)

| # | Issue | Aktion |
|---|---|---|
| 1 | `run_status = 'error'` als nicht-terminal State | Terminal-State-Vertrag klären, `'error'` normalisieren oder als Terminal-State registrieren |
| 2 | Real-API-Test ohne Skip-Guard | `pytest.mark.skipif(not os.getenv("REAL_API_ENABLED"), ...)` ergänzen |

### P1 – Produktionsreife (kurzfristig)

| # | Issue | Aktion |
|---|---|---|
| 3 | Unbounded Idempotency-Registry | TTL-basierte Eviction implementieren (z.B. `expiringdict` oder eigene Eviction) |
| 4 | Stub-Auth in `RuntimeManager` | Klare Exception/Warning wenn `api`-Mode ohne Auth-Check genutzt wird |

### P2 – Strukturverbesserungen (mittelfristig)

| # | Issue | Aktion |
|---|---|---|
| 5 | `main.py` (2934 Zeilen) aufteilen | Endpoint-Logik in dedizierte Router-Module auslagern |
| 6 | `HeadAgent` DI einführen | `LlmClient`, `MemoryStore`, `AgentTooling` als optionale Konstruktorparameter |
| 7 | Structured Exception-Types | `ToolExecutionError`, `LlmClientError` mit Feldern versehen |
| 8 | `configure_runtime` – Sub-Agent-Rebuild vermeiden | Nur `self.client` updaten, Sub-Agents lazy bei Bedarf neu bauen |

### P3 – Tech Debt (längerfristig)

| # | Issue | Aktion |
|---|---|---|
| 9 | Config-Fallback-Ketten vereinfachen | `_resolve_prompt()`-Helfer, Debug-Endpoint für aufgelöste Werte |
| 10 | `list_runs()` Skalierbarkeit | In-Memory-Index oder DB-backed Store langfristig |
| 11 | `WsHandlerDependencies Any`-Felder | Typed Protocols statt `Any` |

---

## 9. Gesamturteil

Das Backend ist **gut durchdacht in seiner Ausgestaltung der Einzelkomponenten** (Lifecycle-Events, Policy-Layering, MemoryStore-Thread-Safety, Subrun-Depth-Guards). Die kritischen Schwachstellen liegen in der **Datei-/Klassen-Granularität** und **Produktionsreife einzelner Querschnittsthemen** (Auth-Stubs, In-Memory-Registries, unklarer Terminal-State-Vertrag). Mit gezielten P0/P1-Fixes ist das System testbar und auslieferbar; für skalierten Produktionsbetrieb sind die P2-Maßnahmen realistisch einzuplanen.

---

## 10. Status seit Assessment (Update)

Stand dieses Addendums: 2026-03-01 (nach Umsetzung mehrerer P0/P1/P2/P3-Maßnahmen)

### 10.1 Umsetzungsstand der priorisierten Punkte

| Priorität | # | Status | Kurzfazit |
|---|---:|---|---|
| P0 | 1 | ✅ erledigt | Terminal-State-Vertrag ist konsistent (`runStatus=error` im Contract), Tests entsprechend angepasst. |
| P0 | 2 | ✅ erledigt | Real-API-E2E ist opt-in (`REAL_API_ENABLED`) und skippt sauber ohne externe API. |
| P1 | 3 | ✅ erledigt | Idempotency-Registries haben TTL + Max-Entries-Pruning. |
| P1 | 4 | ✅ erledigt | RuntimeManager-Auth-Guard implementiert; klarer Fehlerpfad bei fehlender API-Auth. |
| P2 | 5 | 🟡 teilweise | `main.py` wurde spürbar entlastet (Router-Extraktion), ist aber weiterhin groß. |
| P2 | 6 | ✅ erledigt | `HeadAgent` unterstützt optionale DI im Konstruktor. |
| P2 | 7 | ✅ erledigt | Strukturierte Fehlerbasis (`AppError`) inkl. Metadaten eingeführt. |
| P2 | 8 | ✅ erledigt | `configure_runtime` re-konfiguriert Sub-Agents in-place statt Rebuild. |
| P3 | 9 | ✅ erledigt | Prompt-Fallbacks zentralisiert (`_resolve_prompt`) + Debug-Endpoint für aufgelöste Prompts. |
| P3 | 10 | 🟡 teilweise | `list_runs()` per In-Memory-Index optimiert; DB-backed Store weiterhin offen. |
| P3 | 11 | ✅ erledigt | `WsHandlerDependencies` auf typed Protocols umgestellt. |

### 10.2 Ergänzende Beobachtungen

- Zusätzlich adressiert: `AgentContract.constraints` in den zentralen Agent-Adaptern ist instanzgebunden statt importzeitgebunden.
- Weiterhin relevant: `settings = Settings()` bleibt als Importzeit-Singleton bestehen; dies ist dokumentierte Restschuld.

### 10.3 Offene Restarbeit (kurz)

1. Weitere Zerlegung von `app/main.py` in kleinere, thematische Router-/Service-Module.
2. Mittelfristig persistente Query-/Store-Strategie für Runs/Sessions (statt rein dateibasiert + In-Memory-Index).
3. ✅ erledigt: dedizierte Router-Unit-Tests zusätzlich zu den bestehenden Contract-/E2E-Suiten ergänzt.
