# PHASE 09 — `tools/` Core: Catalog, Policy, Content Security + Registry + Execution

> **Session-Ziel:** Die `tools/`-Domäne aufbauen: Top-Level-Dateien + `registry/` + `execution/` (9 Dateien). Die Monolith-Aufteilung (tools.py) kommt in Phase 11.
>
> **Voraussetzung:** PHASE_03 (policy/) + PHASE_06 (sandbox, browser) abgeschlossen
> **Folge-Phase:** PHASE_10_TOOLS_DISCOVERY_PROVISIONING.md
> **Geschätzter Aufwand:** ~3 Stunden
> **Betroffene Quelldateien:** 16 Dateien

---

## Dateien-Übersicht

### Top-Level `tools/` (5 Dateien)

| Quelldatei | Zieldatei |
|------------|-----------|
| `app/tool_catalog.py` | `app/tools/catalog.py` |
| `app/tool_policy.py` | `app/tools/policy.py` |
| `app/content_security.py` | `app/tools/content_security.py` |
| `app/url_validator.py` | `app/tools/url_validator.py` |
| `app/services/tool_telemetry.py` | `app/tools/telemetry.py` |

### `tools/registry/` (2 Dateien)

| Quelldatei | Zieldatei |
|------------|-----------|
| `app/services/tool_registry.py` | `app/tools/registry/registry.py` |
| `app/tool_modules/tool_config_store.py` | `app/tools/registry/config_store.py` |

### `tools/execution/` (9 Dateien)

| Quelldatei | Zieldatei |
|------------|-----------|
| `services/tool_execution_manager.py` | `tools/execution/manager.py` |
| `services/tool_call_gatekeeper.py` | `tools/execution/gatekeeper.py` |
| `services/tool_arg_validator.py` | `tools/execution/arg_validator.py` |
| `services/tool_retry_strategy.py` | `tools/execution/retry_strategy.py` |
| `services/tool_outcome_verifier.py` | `tools/execution/outcome_verifier.py` |
| `services/tool_parallel_executor.py` | `tools/execution/parallel_executor.py` |
| `services/tool_loop_detector.py` | `tools/execution/loop_detector.py` |
| `services/tool_result_processor.py` | `tools/execution/result_processor.py` |
| `services/tool_result_context_guard.py` | `tools/execution/result_context_guard.py` |

---

## 1. Top-Level `tools/` Dateien

### 1.1 `app/tool_catalog.py` → `app/tools/catalog.py`

```powershell
Copy-Item "backend/app/tool_catalog.py" "backend/app/tools/catalog.py"
```

**Imports prüfen:**
```powershell
Select-String -Path "backend/app/tools/catalog.py" -Pattern "^from app\."
```

Erlaubt: `shared/`, `config/`, `contracts/`, `policy/`  
Häufiger Import: `from app.tool_policy import ...` → `from app.tools.policy import ...` (aber erst nach 1.2)

**Stub:**
```python
# backend/app/tool_catalog.py — DEPRECATED → app.tools.catalog
from app.tools.catalog import *  # noqa: F401, F403
```

---

### 1.2 `app/tool_policy.py` → `app/tools/policy.py`

```powershell
Copy-Item "backend/app/tool_policy.py" "backend/app/tools/policy.py"
```

**Imports prüfen:** Nur `shared/`, `config/`, `policy/` erlaubt.

**Stub:**
```python
# backend/app/tool_policy.py — DEPRECATED → app.tools.policy
from app.tools.policy import *  # noqa: F401, F403
```

---

### 1.3 `app/content_security.py` → `app/tools/content_security.py`

```powershell
Copy-Item "backend/app/content_security.py" "backend/app/tools/content_security.py"
```

**Imports prüfen:**  
`content_security.py` enthält SSRF-Schutz. Erlaubt: `shared/`, `config/`, `policy/`.  
Falls `from app.url_validator import ...` → ändern zu `from app.tools.url_validator import ...` (nach 1.4)

**Stub:**
```python
# backend/app/content_security.py — DEPRECATED → app.tools.content_security
from app.tools.content_security import *  # noqa: F401, F403
```

---

### 1.4 `app/url_validator.py` → `app/tools/url_validator.py`

```powershell
Copy-Item "backend/app/url_validator.py" "backend/app/tools/url_validator.py"
```

**Imports prüfen:** Kein App-Import erwartet (reine Utility).

**Stub:**
```python
# backend/app/url_validator.py — DEPRECATED → app.tools.url_validator
from app.tools.url_validator import *  # noqa: F401, F403
```

---

### 1.5 `services/tool_telemetry.py` → `tools/telemetry.py`

```powershell
Copy-Item "backend/app/services/tool_telemetry.py" "backend/app/tools/telemetry.py"
```

**Imports prüfen:** Nur `shared/`, `config/`.

**Stub:**
```python
# backend/app/services/tool_telemetry.py — DEPRECATED → app.tools.telemetry
from app.tools.telemetry import *  # noqa: F401, F403
```

---

## 2. `tools/registry/` Dateien

### 2.1 `services/tool_registry.py` → `tools/registry/registry.py`

```powershell
Copy-Item "backend/app/services/tool_registry.py" "backend/app/tools/registry/registry.py"
```

**Imports prüfen:**
```powershell
Select-String -Path "backend/app/tools/registry/registry.py" -Pattern "^from app\."
```

Erlaubt: `tools/` intern, `shared/`, `config/`, `contracts/`, `policy/`

Falls `from app.tool_catalog import ...` → `from app.tools.catalog import ...`  
Falls `from app.tool_modules.tool_config_store import ...` → `from app.tools.registry.config_store import ...`

**Stub:**
```python
# backend/app/services/tool_registry.py — DEPRECATED → app.tools.registry.registry
from app.tools.registry.registry import *  # noqa: F401, F403
```

---

### 2.2 `tool_modules/tool_config_store.py` → `tools/registry/config_store.py`

```powershell
Copy-Item "backend/app/tool_modules/tool_config_store.py" "backend/app/tools/registry/config_store.py"
```

**Imports prüfen:** Nur `shared/`, `config/` erlaubt.

**Stub:**
```python
# backend/app/tool_modules/tool_config_store.py — DEPRECATED → app.tools.registry.config_store
from app.tools.registry.config_store import *  # noqa: F401, F403
```

### 2.3 `tools/registry/__init__.py`

```python
# backend/app/tools/registry/__init__.py
from app.tools.registry.registry import ToolRegistry
from app.tools.registry.config_store import ToolConfigStore

__all__ = ["ToolRegistry", "ToolConfigStore"]
```

---

## 3. `tools/execution/` Dateien (9 Dateien)

### 3.1 Alle 9 Dateien kopieren

```powershell
$execFiles = @{
    "tool_execution_manager" = "manager"
    "tool_call_gatekeeper" = "gatekeeper"
    "tool_arg_validator" = "arg_validator"
    "tool_retry_strategy" = "retry_strategy"
    "tool_outcome_verifier" = "outcome_verifier"
    "tool_parallel_executor" = "parallel_executor"
    "tool_loop_detector" = "loop_detector"
    "tool_result_processor" = "result_processor"
    "tool_result_context_guard" = "result_context_guard"
}

foreach ($orig in $execFiles.Keys) {
    $dest = $execFiles[$orig]
    Copy-Item "backend/app/services/$orig.py" "backend/app/tools/execution/$dest.py"
    Write-Host "Copied: $orig.py → execution/$dest.py"
}
```

### 3.2 Imports in allen execution/-Dateien prüfen und fixen

```powershell
Select-String -Path "backend/app/tools/execution/*.py" -Pattern "^from app\." | Where-Object { $_.Line -notmatch "app\.(shared|config|policy|contracts|tools)" }
```

**Häufige Imports die gefixt werden müssen (suchen und ersetzen in jedem File):**

| Alt | Neu |
|-----|-----|
| `from app.services.tool_execution_manager import` | `from app.tools.execution.manager import` |
| `from app.services.tool_call_gatekeeper import` | `from app.tools.execution.gatekeeper import` |
| `from app.services.tool_arg_validator import` | `from app.tools.execution.arg_validator import` |
| `from app.services.tool_retry_strategy import` | `from app.tools.execution.retry_strategy import` |
| `from app.services.tool_outcome_verifier import` | `from app.tools.execution.outcome_verifier import` |
| `from app.services.tool_loop_detector import` | `from app.tools.execution.loop_detector import` |
| `from app.services.tool_result_processor import` | `from app.tools.execution.result_processor import` |
| `from app.services.tool_result_context_guard import` | `from app.tools.execution.result_context_guard import` |
| `from app.tool_policy import` | `from app.tools.policy import` |
| `from app.tool_catalog import` | `from app.tools.catalog import` |
| `from app.errors import` | `from app.shared.errors import` (oder `from app.policy.errors import`) |

### 3.3 Stubs für alle 9 Originale

```powershell
$execStubs = @{
    "tool_execution_manager" = "app.tools.execution.manager"
    "tool_call_gatekeeper" = "app.tools.execution.gatekeeper"
    "tool_arg_validator" = "app.tools.execution.arg_validator"
    "tool_retry_strategy" = "app.tools.execution.retry_strategy"
    "tool_outcome_verifier" = "app.tools.execution.outcome_verifier"
    "tool_parallel_executor" = "app.tools.execution.parallel_executor"
    "tool_loop_detector" = "app.tools.execution.loop_detector"
    "tool_result_processor" = "app.tools.execution.result_processor"
    "tool_result_context_guard" = "app.tools.execution.result_context_guard"
}

foreach ($orig in $execStubs.Keys) {
    $new = $execStubs[$orig]
    $content = "# DEPRECATED: moved to $new`nfrom $new import *  # noqa: F401, F403"
    Set-Content "backend/app/services/$orig.py" $content
}
```

### 3.4 `tools/execution/__init__.py`

```python
# backend/app/tools/execution/__init__.py
"""Tool execution pipeline."""
from app.tools.execution.manager import ToolExecutionManager
from app.tools.execution.gatekeeper import ToolCallGatekeeper
from app.tools.execution.arg_validator import ToolArgValidator
from app.tools.execution.retry_strategy import ToolRetryStrategy
from app.tools.execution.outcome_verifier import ToolOutcomeVerifier
from app.tools.execution.parallel_executor import ToolParallelExecutor
from app.tools.execution.loop_detector import ToolLoopDetector
from app.tools.execution.result_processor import ToolResultProcessor
from app.tools.execution.result_context_guard import ToolResultContextGuard

__all__ = [
    "ToolExecutionManager", "ToolCallGatekeeper", "ToolArgValidator",
    "ToolRetryStrategy", "ToolOutcomeVerifier", "ToolParallelExecutor",
    "ToolLoopDetector", "ToolResultProcessor", "ToolResultContextGuard",
]
```

---

## 4. `tools/__init__.py` — Vorläufig (wird in Phase 11 vervollständigt)

```python
# backend/app/tools/__init__.py
"""
Tool ecosystem domain.
Imports allowed from: policy/, sandbox/, browser/, media/, monitoring/, shared/, contracts/, config/
"""
from app.tools.catalog import ToolCatalog
from app.tools.policy import ToolPolicy
from app.tools.content_security import ContentSecurity
from app.tools.url_validator import UrlValidator
from app.tools.telemetry import ToolTelemetry
from app.tools.registry import ToolRegistry
from app.tools.execution import ToolExecutionManager

__all__ = [
    "ToolCatalog", "ToolPolicy", "ContentSecurity", "UrlValidator",
    "ToolTelemetry", "ToolRegistry", "ToolExecutionManager",
]
```

---

## 5. Verifikation

```powershell
$checks = @(
    "backend/app/tools/catalog.py", "backend/app/tools/policy.py",
    "backend/app/tools/content_security.py", "backend/app/tools/url_validator.py",
    "backend/app/tools/telemetry.py",
    "backend/app/tools/registry/registry.py", "backend/app/tools/registry/config_store.py",
    "backend/app/tools/execution/manager.py", "backend/app/tools/execution/gatekeeper.py",
    "backend/app/tools/execution/arg_validator.py", "backend/app/tools/execution/retry_strategy.py",
    "backend/app/tools/execution/outcome_verifier.py", "backend/app/tools/execution/parallel_executor.py",
    "backend/app/tools/execution/loop_detector.py", "backend/app/tools/execution/result_processor.py",
    "backend/app/tools/execution/result_context_guard.py"
)
foreach ($f in $checks) {
    if (Test-Path $f) { Write-Host "OK: $f" } else { Write-Host "MISSING: $f" }
}

cd backend
python -c "
from app.tools import ToolCatalog, ToolPolicy, ContentSecurity, ToolRegistry, ToolExecutionManager
from app.tools.execution import ToolCallGatekeeper, ToolArgValidator, ToolLoopDetector
print('tools/ core OK')
"
```

---

## 6. Commit

```bash
git add -A
git commit -m "refactor(ddd): migrate tools/ core (catalog, policy, registry, execution) — Phase 09"
```

---

## Status-Checkliste

- [ ] `tools/catalog.py` erstellt, Stub
- [ ] `tools/policy.py` erstellt, Stub
- [ ] `tools/content_security.py` erstellt, Stub
- [ ] `tools/url_validator.py` erstellt, Stub
- [ ] `tools/telemetry.py` erstellt, Stub
- [ ] `tools/registry/registry.py` erstellt, interne Imports gefixt, Stub
- [ ] `tools/registry/config_store.py` erstellt, Stub
- [ ] `tools/registry/__init__.py` befüllt
- [ ] `tools/execution/` alle 9 Dateien erstellt, Imports bereinigt, Stubs
- [ ] `tools/execution/__init__.py` befüllt
- [ ] `tools/__init__.py` vorläufig befüllt
- [ ] Smoke-Test erfolgreich
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_10_TOOLS_DISCOVERY_PROVISIONING.md](./PHASE_10_TOOLS_DISCOVERY_PROVISIONING.md)
