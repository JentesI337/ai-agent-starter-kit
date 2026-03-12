# PHASE 06 — Infrastructure Layer: `mcp/`, `media/`, `sandbox/`, `browser/`, `monitoring/`

> **Session-Ziel:** Fünf Infrastruktur-Domänen aus `services/` migrieren. Diese Module sind Blatt-Domänen — sie haben keine gegenseitigen Abhängigkeiten (außer `shared/` und `config/`).
>
> **Voraussetzung:** PHASE_05 abgeschlossen
> **Folge-Phase:** PHASE_07_MEMORY_SESSION.md
> **Geschätzter Aufwand:** ~2–3 Stunden
> **Betroffene Quelldateien:** 13 Dateien

---

## Dateien-Übersicht

| Quelldatei | Zieldatei |
|------------|-----------|
| `app/mcp_types.py` | `app/mcp/types.py` |
| `app/services/mcp_bridge.py` | `app/mcp/bridge.py` |
| `app/services/audio_service.py` | `app/media/audio_service.py` |
| `app/services/audio_deps_service.py` | `app/media/audio_deps.py` |
| `app/services/vision_service.py` | `app/media/vision_service.py` |
| `app/services/image_gen_service.py` | `app/media/image_gen_service.py` |
| `app/services/pdf_service.py` | `app/media/pdf_service.py` |
| `app/services/code_sandbox.py` | `app/sandbox/code_sandbox.py` |
| `app/services/persistent_repl.py` | `app/sandbox/persistent_repl.py` |
| `app/services/repl_session_manager.py` | `app/sandbox/repl_session_manager.py` |
| `app/services/browser_pool.py` | `app/browser/pool.py` |
| `app/services/visualization.py` | `app/monitoring/visualization.py` |
| `app/services/environment_snapshot.py` | `app/monitoring/environment_snapshot.py` |
| `app/services/platform_info.py` | `app/monitoring/platform_info.py` |

---

## 1. `mcp/` — Model Context Protocol

### 1.1 `app/mcp_types.py` → `app/mcp/types.py`

```powershell
Copy-Item "backend/app/mcp_types.py" "backend/app/mcp/types.py"
```

**Imports prüfen:** Nur typing/stdlib — kein App-Import erwartet.

**Stub:**
```python
# backend/app/mcp_types.py — DEPRECATED → app.mcp.types
from app.mcp.types import *  # noqa: F401, F403
```

---

### 1.2 `services/mcp_bridge.py` → `mcp/bridge.py`

```powershell
Copy-Item "backend/app/services/mcp_bridge.py" "backend/app/mcp/bridge.py"
```

**Imports prüfen:**
```powershell
Select-String -Path "backend/app/mcp/bridge.py" -Pattern "^from app\."
```

Erlaubt: `contracts/`, `shared/`, `config/`  
Falls `from app.mcp_types import ...` → ändern zu `from app.mcp.types import ...`

**Stub:**
```python
# backend/app/services/mcp_bridge.py — DEPRECATED → app.mcp.bridge
from app.mcp.bridge import *  # noqa: F401, F403
```

### 1.3 `mcp/__init__.py`

```python
# backend/app/mcp/__init__.py
from app.mcp.types import *
from app.mcp.bridge import McpBridge

__all__ = ["McpBridge"]
```

---

## 2. `media/` — Audio, Vision, Image, PDF

### 2.1 alle 5 Dateien kopieren

```powershell
Copy-Item "backend/app/services/audio_service.py" "backend/app/media/audio_service.py"
Copy-Item "backend/app/services/audio_deps_service.py" "backend/app/media/audio_deps.py"
Copy-Item "backend/app/services/vision_service.py" "backend/app/media/vision_service.py"
Copy-Item "backend/app/services/image_gen_service.py" "backend/app/media/image_gen_service.py"
Copy-Item "backend/app/services/pdf_service.py" "backend/app/media/pdf_service.py"
```

**Imports in allen 5 Dateien prüfen:**
```powershell
Select-String -Path "backend/app/media/*.py" -Pattern "^from app\." | Where-Object { $_.Line -notmatch "app\.(shared|config|mcp|policy)" }
```

> Falls `audio_service.py` auf `code_sandbox.py` verweist o.ä. → das muss via `sandbox/` erfolgen. Doku für Phase 18.

**Stubs für alle Originale:**
```python
# backend/app/services/audio_service.py — DEPRECATED → app.media.audio_service
from app.media.audio_service import *  # noqa: F401, F403
```
```python
# backend/app/services/audio_deps_service.py — DEPRECATED → app.media.audio_deps
from app.media.audio_deps import *  # noqa: F401, F403
```
```python
# backend/app/services/vision_service.py — DEPRECATED → app.media.vision_service
from app.media.vision_service import *  # noqa: F401, F403
```
```python
# backend/app/services/image_gen_service.py — DEPRECATED → app.media.image_gen_service
from app.media.image_gen_service import *  # noqa: F401, F403
```
```python
# backend/app/services/pdf_service.py — DEPRECATED → app.media.pdf_service
from app.media.pdf_service import *  # noqa: F401, F403
```

### 2.2 `media/__init__.py`

```python
# backend/app/media/__init__.py
"""Media processing infrastructure (audio, vision, image generation, PDF)."""
from app.media.audio_service import AudioService
from app.media.audio_deps import AudioDepsService
from app.media.vision_service import VisionService
from app.media.image_gen_service import ImageGenService
from app.media.pdf_service import PdfService

__all__ = ["AudioService", "AudioDepsService", "VisionService", "ImageGenService", "PdfService"]
```

---

## 3. `sandbox/` — Code-Execution Sandbox

### 3.1 alle 3 Dateien kopieren

```powershell
Copy-Item "backend/app/services/code_sandbox.py" "backend/app/sandbox/code_sandbox.py"
Copy-Item "backend/app/services/persistent_repl.py" "backend/app/sandbox/persistent_repl.py"
Copy-Item "backend/app/services/repl_session_manager.py" "backend/app/sandbox/repl_session_manager.py"
```

**Imports in allen 3 Dateien prüfen:**
```powershell
Select-String -Path "backend/app/sandbox/*.py" -Pattern "^from app\." | Where-Object { $_.Line -notmatch "app\.(shared|config|policy)" }
```

> `sandbox/` darf `policy/` nutzen (für Policy-Checks). Verboten: `agent/`, `tools/`, `transport/`.

**Interne Querverweise fixieren:**
- `repl_session_manager.py` referenziert `persistent_repl.py`:  
  `from app.services.persistent_repl import ...` → `from app.sandbox.persistent_repl import ...`
- `code_sandbox.py` referenziert evtl. `repl_session_manager.py`:  
  falls ja → `from app.sandbox.repl_session_manager import ...`

**Stubs:**
```python
# backend/app/services/code_sandbox.py — DEPRECATED → app.sandbox.code_sandbox
from app.sandbox.code_sandbox import *  # noqa: F401, F403
```
```python
# backend/app/services/persistent_repl.py — DEPRECATED → app.sandbox.persistent_repl
from app.sandbox.persistent_repl import *  # noqa: F401, F403
```
```python
# backend/app/services/repl_session_manager.py — DEPRECATED → app.sandbox.repl_session_manager
from app.sandbox.repl_session_manager import *  # noqa: F401, F403
```

### 3.2 `sandbox/__init__.py`

```python
# backend/app/sandbox/__init__.py
"""Code execution sandbox infrastructure."""
from app.sandbox.code_sandbox import CodeSandbox
from app.sandbox.persistent_repl import PersistentRepl
from app.sandbox.repl_session_manager import ReplSessionManager

__all__ = ["CodeSandbox", "PersistentRepl", "ReplSessionManager"]
```

---

## 4. `browser/` — Browser-Automatisierung

### 4.1 `services/browser_pool.py` → `browser/pool.py`

```powershell
Copy-Item "backend/app/services/browser_pool.py" "backend/app/browser/pool.py"
```

**Imports prüfen:** Erlaubt `policy/`, `shared/`, `config/`.

**Stub:**
```python
# backend/app/services/browser_pool.py — DEPRECATED → app.browser.pool
from app.browser.pool import *  # noqa: F401, F403
```

### 4.2 `browser/__init__.py`

```python
# backend/app/browser/__init__.py
"""Browser automation infrastructure."""
from app.browser.pool import BrowserPool

__all__ = ["BrowserPool"]
```

---

## 5. `monitoring/` — Observability

### 5.1 alle 3 Dateien kopieren

```powershell
Copy-Item "backend/app/services/visualization.py" "backend/app/monitoring/visualization.py"
Copy-Item "backend/app/services/environment_snapshot.py" "backend/app/monitoring/environment_snapshot.py"
Copy-Item "backend/app/services/platform_info.py" "backend/app/monitoring/platform_info.py"
```

**Imports prüfen:**
```powershell
Select-String -Path "backend/app/monitoring/*.py" -Pattern "^from app\." | Where-Object { $_.Line -notmatch "app\.(shared|config)" }
```

> Monitoring darf NICHTS aus anderen Domänen importieren (nur `shared/`, `config/`).

**Stubs:**
```python
# backend/app/services/visualization.py — DEPRECATED → app.monitoring.visualization
from app.monitoring.visualization import *  # noqa: F401, F403
```
```python
# backend/app/services/environment_snapshot.py — DEPRECATED → app.monitoring.environment_snapshot
from app.monitoring.environment_snapshot import *  # noqa: F401, F403
```
```python
# backend/app/services/platform_info.py — DEPRECATED → app.monitoring.platform_info
from app.monitoring.platform_info import *  # noqa: F401, F403
```

### 5.2 `monitoring/__init__.py`

```python
# backend/app/monitoring/__init__.py
"""Observability and monitoring infrastructure."""
from app.monitoring.visualization import Visualization
from app.monitoring.environment_snapshot import EnvironmentSnapshot
from app.monitoring.platform_info import PlatformInfo

__all__ = ["Visualization", "EnvironmentSnapshot", "PlatformInfo"]
```

---

## 6. Verifikation

```powershell
$checks = @(
    "backend/app/mcp/types.py", "backend/app/mcp/bridge.py",
    "backend/app/media/audio_service.py", "backend/app/media/audio_deps.py",
    "backend/app/media/vision_service.py", "backend/app/media/image_gen_service.py",
    "backend/app/media/pdf_service.py",
    "backend/app/sandbox/code_sandbox.py", "backend/app/sandbox/persistent_repl.py",
    "backend/app/sandbox/repl_session_manager.py",
    "backend/app/browser/pool.py",
    "backend/app/monitoring/visualization.py", "backend/app/monitoring/environment_snapshot.py",
    "backend/app/monitoring/platform_info.py"
)
foreach ($f in $checks) {
    if (Test-Path $f) { Write-Host "OK: $f" } else { Write-Host "MISSING: $f" }
}

cd backend
python -c "
from app.mcp import McpBridge
from app.media import AudioService, VisionService
from app.sandbox import CodeSandbox, PersistentRepl
from app.browser import BrowserPool
from app.monitoring import Visualization, PlatformInfo
print('infrastructure OK')
"
```

---

## 7. Commit

```bash
git add -A
git commit -m "refactor(ddd): migrate infrastructure domains (mcp, media, sandbox, browser, monitoring) — Phase 06"
```

---

## Status-Checkliste

- [ ] `mcp/types.py` + `mcp/bridge.py` erstellt, Stubs in Originalen
- [ ] `media/` alle 5 Dateien, Stubs in Originalen
- [ ] `sandbox/` alle 3 Dateien, interne Querverweise gefixt, Stubs
- [ ] `browser/pool.py` erstellt, Stub
- [ ] `monitoring/` alle 3 Dateien, Stubs
- [ ] Alle 5 `__init__.py` befüllt
- [ ] Smoke-Test erfolgreich
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_07_MEMORY_SESSION.md](./PHASE_07_MEMORY_SESSION.md)
