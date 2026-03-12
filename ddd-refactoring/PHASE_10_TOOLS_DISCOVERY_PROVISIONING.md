# PHASE 10 — `tools/` Discovery + Provisioning

> **Session-Ziel:** Die restlichen `tools/`-Subdomänen anlegen: `discovery/` (5 Dateien) und `provisioning/` (4+2 Dateien).
>
> **Voraussetzung:** PHASE_09 abgeschlossen
> **Folge-Phase:** PHASE_11_TOOLS_IMPLEMENTATIONS.md
> **Geschätzter Aufwand:** ~2 Stunden
> **Betroffene Quelldateien:** 11 Dateien

---

## Dateien-Übersicht

### `tools/discovery/` (5 Dateien)

| Quelldatei | Zieldatei |
|------------|-----------|
| `services/tool_discovery_engine.py` | `tools/discovery/engine.py` |
| `services/tool_knowledge_base.py` | `tools/discovery/knowledge_base.py` |
| `services/tool_capability_router.py` | `tools/discovery/capability_router.py` |
| `services/tool_ecosystem_map.py` | `tools/discovery/ecosystem_map.py` |
| `services/tool_detector.py` | `tools/discovery/detector.py` |

### `tools/provisioning/` (5+1 Dateien)

| Quelldatei | Zieldatei |
|------------|-----------|
| `services/tool_provisioner.py` | `tools/provisioning/provisioner.py` |
| `services/tool_budget_manager.py` | `tools/provisioning/budget_manager.py` |
| `services/tool_policy_service.py` | `tools/provisioning/policy_service.py` |
| `tool_modules/command_security.py` | `tools/provisioning/command_security.py` |
| `services/package_manager_adapter.py` | `tools/provisioning/package_manager_adapter.py` |

---

## 1. `tools/discovery/` Domain

### 1.1 Alle 5 Dateien kopieren

```powershell
$discoveryFiles = @{
    "tool_discovery_engine" = "engine"
    "tool_knowledge_base" = "knowledge_base"
    "tool_capability_router" = "capability_router"
    "tool_ecosystem_map" = "ecosystem_map"
    "tool_detector" = "detector"
}

foreach ($orig in $discoveryFiles.Keys) {
    $dest = $discoveryFiles[$orig]
    Copy-Item "backend/app/services/$orig.py" "backend/app/tools/discovery/$dest.py"
    Write-Host "Copied: $orig.py → discovery/$dest.py"
}
```

### 1.2 Imports in allen discovery/-Dateien prüfen

```powershell
Select-String -Path "backend/app/tools/discovery/*.py" -Pattern "^from app\." | Where-Object {
    $_.Line -notmatch "app\.(shared|config|policy|contracts|tools)"
}
```

Erlaubt in `tools/discovery/`:
- `from app.shared.*`
- `from app.config.*`
- `from app.tools.catalog import ...`
- `from app.tools.registry import ...`
- `from app.contracts.*`
- `from app.policy.*`

**Häufige Imports die gefixt werden müssen:**

| Alt | Neu |
|-----|-----|
| `from app.services.tool_discovery_engine import` | `from app.tools.discovery.engine import` |
| `from app.services.tool_knowledge_base import` | `from app.tools.discovery.knowledge_base import` |
| `from app.services.tool_capability_router import` | `from app.tools.discovery.capability_router import` |
| `from app.services.tool_ecosystem_map import` | `from app.tools.discovery.ecosystem_map import` |
| `from app.tool_catalog import` | `from app.tools.catalog import` |
| `from app.services.tool_registry import` | `from app.tools.registry.registry import` |

### 1.3 Stubs für alle 5 Originale

```powershell
$discoveryStubs = @{
    "tool_discovery_engine" = "app.tools.discovery.engine"
    "tool_knowledge_base" = "app.tools.discovery.knowledge_base"
    "tool_capability_router" = "app.tools.discovery.capability_router"
    "tool_ecosystem_map" = "app.tools.discovery.ecosystem_map"
    "tool_detector" = "app.tools.discovery.detector"
}

foreach ($orig in $discoveryStubs.Keys) {
    $new = $discoveryStubs[$orig]
    $content = "# DEPRECATED: moved to $new`nfrom $new import *  # noqa: F401, F403"
    Set-Content "backend/app/services/$orig.py" $content
    Write-Host "Stub: $orig.py"
}
```

### 1.4 `tools/discovery/__init__.py`

```python
# backend/app/tools/discovery/__init__.py
"""Tool discovery and intelligence."""
from app.tools.discovery.engine import ToolDiscoveryEngine
from app.tools.discovery.knowledge_base import ToolKnowledgeBase
from app.tools.discovery.capability_router import ToolCapabilityRouter
from app.tools.discovery.ecosystem_map import ToolEcosystemMap
from app.tools.discovery.detector import ToolDetector

__all__ = [
    "ToolDiscoveryEngine", "ToolKnowledgeBase", "ToolCapabilityRouter",
    "ToolEcosystemMap", "ToolDetector",
]
```

---

## 2. `tools/provisioning/` Domain

### 2.1 Service-Dateien kopieren (3 aus services/)

```powershell
$provFiles = @{
    "tool_provisioner" = "provisioner"
    "tool_budget_manager" = "budget_manager"
    "tool_policy_service" = "policy_service"
}

foreach ($orig in $provFiles.Keys) {
    $dest = $provFiles[$orig]
    Copy-Item "backend/app/services/$orig.py" "backend/app/tools/provisioning/$dest.py"
    Write-Host "Copied: $orig.py → provisioning/$dest.py"
}
```

### 2.2 `tool_modules/command_security.py` → `tools/provisioning/command_security.py`

```powershell
Copy-Item "backend/app/tool_modules/command_security.py" "backend/app/tools/provisioning/command_security.py"
```

**SICHERHEITS-CHECK:** Diese Datei enthält Command-Injection-Prevention.  
```powershell
Get-Content "backend/app/tools/provisioning/command_security.py"
```

Sicherstellen, dass:
- Keine Shell-Escape-Mechanismen entfernt wurden
- `shlex.quote()` oder ähnliche Sanitisierungen intact sind
- Keine `shell=True` ohne Sanitisierung

**Stub in original:**
```python
# backend/app/tool_modules/command_security.py — DEPRECATED → app.tools.provisioning.command_security
from app.tools.provisioning.command_security import *  # noqa: F401, F403
```

---

### 2.3 `services/package_manager_adapter.py` → `tools/provisioning/package_manager_adapter.py`

```powershell
Copy-Item "backend/app/services/package_manager_adapter.py" "backend/app/tools/provisioning/package_manager_adapter.py"
```

**Imports prüfen:**
```powershell
Select-String -Path "backend/app/tools/provisioning/package_manager_adapter.py" -Pattern "^from app\."
```

**Stub:**
```python
# backend/app/services/package_manager_adapter.py — DEPRECATED → app.tools.provisioning.package_manager_adapter
from app.tools.provisioning.package_manager_adapter import *  # noqa: F401, F403
```

---

### 2.4 Imports in allen provisioning/-Dateien prüfen

```powershell
Select-String -Path "backend/app/tools/provisioning/*.py" -Pattern "^from app\." | Where-Object {
    $_.Line -notmatch "app\.(shared|config|policy|contracts|tools)"
}
```

**Häufige Imports die gefixt werden müssen:**

| Alt | Neu |
|-----|-----|
| `from app.services.tool_provisioner import` | `from app.tools.provisioning.provisioner import` |
| `from app.services.tool_budget_manager import` | `from app.tools.provisioning.budget_manager import` |
| `from app.services.tool_policy_service import` | `from app.tools.provisioning.policy_service import` |
| `from app.tool_modules.command_security import` | `from app.tools.provisioning.command_security import` |
| `from app.tool_policy import` | `from app.tools.policy import` |
| `from app.policy_store import` | `from app.policy.store import` |

### 2.5 Stubs für provisioning/-Originale

```powershell
$provStubs = @{
    "tool_provisioner" = "app.tools.provisioning.provisioner"
    "tool_budget_manager" = "app.tools.provisioning.budget_manager"
    "tool_policy_service" = "app.tools.provisioning.policy_service"
}

foreach ($orig in $provStubs.Keys) {
    $new = $provStubs[$orig]
    $content = "# DEPRECATED: moved to $new`nfrom $new import *  # noqa: F401, F403"
    Set-Content "backend/app/services/$orig.py" $content
}
```

### 2.6 `tools/provisioning/__init__.py`

```python
# backend/app/tools/provisioning/__init__.py
"""Tool provisioning and lifecycle management."""
from app.tools.provisioning.provisioner import ToolProvisioner
from app.tools.provisioning.budget_manager import ToolBudgetManager
from app.tools.provisioning.policy_service import ToolPolicyService
from app.tools.provisioning.command_security import CommandSecurity
from app.tools.provisioning.package_manager_adapter import PackageManagerAdapter

__all__ = [
    "ToolProvisioner", "ToolBudgetManager", "ToolPolicyService",
    "CommandSecurity", "PackageManagerAdapter",
]
```

---

## 3. `tools/__init__.py` updaten (erweitern von Phase 09)

```python
# backend/app/tools/__init__.py — ERWEITERT (discovery und provisioning hinzufügen)
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
from app.tools.discovery import ToolDiscoveryEngine
from app.tools.provisioning import ToolProvisioner

__all__ = [
    "ToolCatalog", "ToolPolicy", "ContentSecurity", "UrlValidator",
    "ToolTelemetry", "ToolRegistry", "ToolExecutionManager",
    "ToolDiscoveryEngine", "ToolProvisioner",
]
```

---

## 4. `tool_modules/__init__.py` als Stub anlegen

```python
# backend/app/tool_modules/__init__.py
# DEPRECATED: tool_modules/ merged into app.tools.provisioning and app.tools.registry
from app.tools.provisioning.command_security import *  # noqa: F401, F403
from app.tools.registry.config_store import *  # noqa: F401, F403
```

---

## 5. Verifikation

```powershell
$checks = @(
    "backend/app/tools/discovery/engine.py",
    "backend/app/tools/discovery/knowledge_base.py",
    "backend/app/tools/discovery/capability_router.py",
    "backend/app/tools/discovery/ecosystem_map.py",
    "backend/app/tools/discovery/detector.py",
    "backend/app/tools/provisioning/provisioner.py",
    "backend/app/tools/provisioning/budget_manager.py",
    "backend/app/tools/provisioning/policy_service.py",
    "backend/app/tools/provisioning/command_security.py",
    "backend/app/tools/provisioning/package_manager_adapter.py"
)
foreach ($f in $checks) {
    if (Test-Path $f) { Write-Host "OK: $f" } else { Write-Host "MISSING: $f" }
}

cd backend
python -c "
from app.tools.discovery import ToolDiscoveryEngine, ToolKnowledgeBase, ToolDetector
from app.tools.provisioning import ToolProvisioner, ToolBudgetManager, CommandSecurity
print('tools/discovery + provisioning OK')
"
```

---

## 6. Commit

```bash
git add -A
git commit -m "refactor(ddd): migrate tools/discovery and tools/provisioning — Phase 10"
```

---

## Status-Checkliste

- [ ] `tools/discovery/` alle 5 Dateien, Imports bereinigt, Stubs
- [ ] `tools/discovery/__init__.py` befüllt
- [ ] `tools/provisioning/provisioner.py`, `budget_manager.py`, `policy_service.py` aus services/
- [ ] `tools/provisioning/command_security.py` aus `tool_modules/`, Sicherheits-Check
- [ ] `tools/provisioning/package_manager_adapter.py` aus services/
- [ ] Alle provisioning/-Imports bereinigt
- [ ] Stubs für alle Originale
- [ ] `tools/provisioning/__init__.py` befüllt
- [ ] `tools/__init__.py` erweitert
- [ ] `tool_modules/__init__.py` als Stub
- [ ] Smoke-Test erfolgreich
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_11_TOOLS_IMPLEMENTATIONS.md](./PHASE_11_TOOLS_IMPLEMENTATIONS.md)
