# PHASE 11 — `tools/implementations/` — Monolith-Aufteilung von `tools.py`

> **Session-Ziel:** `tools.py` (~1209 Zeilen), `tools_api_connectors.py`, `tools_devops.py`, `tools_multimodal.py` und `services/web_search.py` in 8 fokussierte Module aufteilen. Dies ist die komplexeste Einzel-Operation — bitte genug Zeit einplanen.
>
> **Voraussetzung:** PHASE_09 abgeschlossen (tools/ Basisstruktur)
> **Folge-Phase:** PHASE_12_AGENT.md
> **Geschätzter Aufwand:** ~4–6 Stunden (die größte Phase!)
> **Betroffene Quelldateien:** 5 Dateien → 8 Zieldateien

---

## Quelldateien

| Datei | Größe | Inhalt |
|-------|-------|--------|
| `app/tools.py` | ~1209 Zeilen | Alle Tool-Methoden als Mixin-Klassen |
| `app/tools_api_connectors.py` | ? | API-Connector-Tools |
| `app/tools_devops.py` | ? | DevOps-Tools |
| `app/tools_multimodal.py` | ? | Multimodal-Tools |
| `app/services/web_search.py` | ? | Web-Search-Service |

## Zielstruktur

```
tools/implementations/
├── __init__.py
├── base.py             ← AgentTooling Assembly (alle Mixins zusammengebaut)
├── filesystem.py       ← FileSystemToolMixin
├── shell.py            ← ShellToolMixin
├── web.py              ← WebToolMixin (tools.py + tools_api_connectors.py + web_search.py)
├── browser.py          ← BrowserToolMixin
├── code_execution.py   ← CodeExecToolMixin
├── multimodal.py       ← MultimodalToolMixin (tools_multimodal.py)
└── devops.py           ← DevOpsToolMixin (tools_devops.py)
```

---

## 1. Vorbereitung: `tools.py` analysieren

### 1.1 Klassen-Struktur lesen

```powershell
# Alle Klassen und Methoden in tools.py auflisten
Select-String -Path "backend/app/tools.py" -Pattern "^class |^    def " | Select-Object LineNumber, Line
```

### 1.2 Methoden-zu-Kategorie Mapping erstellen

Lies `tools.py` durch und erstelle manuell eine Tabelle:

```
Methode                  → Zieldatei
list_dir()               → filesystem.py
read_file()              → filesystem.py
write_file()             → filesystem.py
apply_patch()            → filesystem.py
file_search()            → filesystem.py
grep_search()            → filesystem.py
run_command()            → shell.py
probe_command()          → shell.py
start_background_command() → shell.py
web_fetch()              → web.py
http_request()           → web.py
browser_open()           → browser.py
browser_click()          → browser.py
browser_type()           → browser.py
browser_screenshot()     → browser.py
browser_dom()            → browser.py
browser_js()             → browser.py
code_execute()           → code_execution.py
code_reset()             → code_execution.py
find_command_safety_*    → tools/policy.py (Security-Utils)
```

### 1.3 Imports aus tools.py lesen

```powershell
Select-String -Path "backend/app/tools.py" -Pattern "^from |^import " | Select-Object LineNumber, Line
```

---

## 2. Zieldateien erstellen

### 2.1 `tools/implementations/filesystem.py`

```python
# backend/app/tools/implementations/filesystem.py
"""File system tool operations."""
from __future__ import annotations

# [Imports aus tools.py die für Filesystem-Methoden benötigt werden]
from app.tools.content_security import ContentSecurity  # falls SSRF-Checks
from app.tools.url_validator import UrlValidator


class FileSystemToolMixin:
    """Mixin with file system tool implementations."""

    def list_dir(self, ...):
        # [Code aus tools.py list_dir()]
        ...

    def read_file(self, ...):
        # [Code aus tools.py read_file()]
        ...

    def write_file(self, ...):
        # [Code aus tools.py write_file()]
        ...

    def apply_patch(self, ...):
        # [Code aus tools.py apply_patch()]
        ...

    def file_search(self, ...):
        # [Code aus tools.py file_search()]
        ...

    def grep_search(self, ...):
        # [Code aus tools.py grep_search()]
        ...
```

> **WICHTIG:** Kopiere den EXAKTEN Code aus `tools.py` — kein Rewrite! Nur die Klassendefinition und die Methoden die zu diesem Mixin gehören.

---

### 2.2 `tools/implementations/shell.py`

```python
# backend/app/tools/implementations/shell.py
"""Shell command tool operations."""
from __future__ import annotations

from app.tools.provisioning.command_security import CommandSecurity  # Security-Check!


class ShellToolMixin:
    """Mixin with shell command tool implementations."""

    def run_command(self, ...):
        # [Code aus tools.py run_command()]
        ...

    def probe_command(self, ...):
        # [Code aus tools.py probe_command()]
        ...

    def start_background_command(self, ...):
        # [Code aus tools.py start_background_command()]
        ...
```

> **SICHERHEITS-HINWEIS:** Alle Command-Injection-Prevention-Checks aus `tools.py` MÜSSEN in `shell.py` übernommen werden. Kein Command-Escape entfernen!

---

### 2.3 `tools/implementations/web.py`

Diese Datei enthält Code aus DREI Quellen:
- `tools.py` (web_fetch, http_request)
- `tools_api_connectors.py` (API-spezifische Tools)
- `services/web_search.py` (Web-Search)

```python
# backend/app/tools/implementations/web.py
"""Web fetch, HTTP, and web search tool operations."""
from __future__ import annotations

from app.tools.content_security import ContentSecurity
from app.tools.url_validator import UrlValidator  # SSRF-Schutz MUSS bleiben!


class WebToolMixin:
    """Mixin with web tool implementations."""

    # --- Aus tools.py ---
    def web_fetch(self, ...):
        # [Code aus tools.py web_fetch()]
        # SSRF-Check MUSS retained werden!
        ...

    def http_request(self, ...):
        # [Code aus tools.py http_request()]
        ...

    # --- Aus tools_api_connectors.py ---
    # [Alle Methoden aus ApiConnectorsMixin/Klasse]

    # --- Aus services/web_search.py ---
    def web_search(self, ...):
        # [Code aus services/web_search.py]
        ...
```

**Füge Stubs ein für die Originale:**
```python
# backend/app/tools_api_connectors.py — DEPRECATED → app.tools.implementations.web
from app.tools.implementations.web import *  # noqa: F401, F403
```
```python
# backend/app/services/web_search.py — DEPRECATED → app.tools.implementations.web
from app.tools.implementations.web import *  # noqa: F401, F403
```

---

### 2.4 `tools/implementations/browser.py`

```python
# backend/app/tools/implementations/browser.py
"""Browser automation tool operations."""
from __future__ import annotations

from app.browser import BrowserPool


class BrowserToolMixin:
    """Mixin with browser automation tool implementations."""

    def browser_open(self, ...): ...
    def browser_click(self, ...): ...
    def browser_type(self, ...): ...
    def browser_screenshot(self, ...): ...
    def browser_dom(self, ...): ...
    def browser_js(self, ...): ...
```

---

### 2.5 `tools/implementations/code_execution.py`

```python
# backend/app/tools/implementations/code_execution.py
"""Code execution tool operations."""
from __future__ import annotations

from app.sandbox import CodeSandbox


class CodeExecToolMixin:
    """Mixin with code execution tool implementations."""

    def code_execute(self, ...): ...
    def code_reset(self, ...): ...
```

---

### 2.6 `tools/implementations/multimodal.py`

Inhalt aus `tools_multimodal.py` übernehmen:

```powershell
Copy-Item "backend/app/tools_multimodal.py" "backend/app/tools/implementations/multimodal.py"
```

**Dann Klasse umbenennen falls nötig** (z.B. `MultimodalMixin` → `MultimodalToolMixin`).  
**Imports bereinigen:** `from app.media import ...` statt alter Pfade.

**Stub:**
```python
# backend/app/tools_multimodal.py — DEPRECATED → app.tools.implementations.multimodal
from app.tools.implementations.multimodal import *  # noqa: F401, F403
```

---

### 2.7 `tools/implementations/devops.py`

Inhalt aus `tools_devops.py` übernehmen:

```powershell
Copy-Item "backend/app/tools_devops.py" "backend/app/tools/implementations/devops.py"
```

**Imports bereinigen.**

**Stub:**
```python
# backend/app/tools_devops.py — DEPRECATED → app.tools.implementations.devops
from app.tools.implementations.devops import *  # noqa: F401, F403
```

---

### 2.8 `tools/implementations/base.py` — Assembly

Dies ist die kritischste Datei. Sie assembelt alle Mixins zur `AgentTooling`-Klasse:

```python
# backend/app/tools/implementations/base.py
"""
AgentTooling — main tooling class assembled from all tool mixins.
This is the single entry point used by AgentRunner.
"""
from __future__ import annotations

from app.tools.implementations.filesystem import FileSystemToolMixin
from app.tools.implementations.shell import ShellToolMixin
from app.tools.implementations.web import WebToolMixin
from app.tools.implementations.browser import BrowserToolMixin
from app.tools.implementations.code_execution import CodeExecToolMixin
from app.tools.implementations.multimodal import MultimodalToolMixin
from app.tools.implementations.devops import DevOpsToolMixin


class AgentTooling(
    FileSystemToolMixin,
    ShellToolMixin,
    WebToolMixin,
    BrowserToolMixin,
    CodeExecToolMixin,
    MultimodalToolMixin,
    DevOpsToolMixin,
):
    """
    Assembled tool implementation class.
    Inherits all tool methods from specialized mixins.
    """

    def __init__(self, ...):
        # [Exakter __init__ Code aus dem alten tools.py AgentTooling]
        ...
```

---

## 3. `tools.py` als Stub anlegen

**WICHTIG:** `tools.py` ist die am häufigsten importierte Datei im System. Der Stub muss alles re-exportieren:

```python
# backend/app/tools.py
# DEPRECATED: moved to app.tools.implementations.*
# The AgentTooling class is now assembled in app.tools.implementations.base
# Remove this file in PHASE_18
from app.tools.implementations.base import AgentTooling
from app.tools.implementations.filesystem import FileSystemToolMixin
from app.tools.implementations.shell import ShellToolMixin
from app.tools.implementations.web import WebToolMixin
from app.tools.implementations.browser import BrowserToolMixin
from app.tools.implementations.code_execution import CodeExecToolMixin
from app.tools.implementations.multimodal import MultimodalToolMixin
from app.tools.implementations.devops import DevOpsToolMixin

__all__ = [
    "AgentTooling",
    "FileSystemToolMixin", "ShellToolMixin", "WebToolMixin",
    "BrowserToolMixin", "CodeExecToolMixin", "MultimodalToolMixin", "DevOpsToolMixin",
]
```

---

## 4. `tools/implementations/__init__.py`

```python
# backend/app/tools/implementations/__init__.py
"""Concrete tool implementations."""
from app.tools.implementations.base import AgentTooling
from app.tools.implementations.filesystem import FileSystemToolMixin
from app.tools.implementations.shell import ShellToolMixin
from app.tools.implementations.web import WebToolMixin
from app.tools.implementations.browser import BrowserToolMixin
from app.tools.implementations.code_execution import CodeExecToolMixin
from app.tools.implementations.multimodal import MultimodalToolMixin
from app.tools.implementations.devops import DevOpsToolMixin

__all__ = [
    "AgentTooling",
    "FileSystemToolMixin", "ShellToolMixin", "WebToolMixin",
    "BrowserToolMixin", "CodeExecToolMixin", "MultimodalToolMixin", "DevOpsToolMixin",
]
```

---

## 5. Sicherheits-Checkliste (PFLICHT)

Nach der Migration prüfen:

- [ ] `url_validator.py` wird in `web.py` für SSRF-Checks importiert
- [ ] `command_security.py` wird in `shell.py` für Command-Injection-Prevention importiert
- [ ] `content_security.py` wird in `web.py` für Content-Security-Checks importiert
- [ ] Kein `subprocess.run(shell=True)` ohne vorherigen Security-Check
- [ ] Alle Eingaben werden validiert bevor sie an Shell/Web-Calls übergeben werden

---

## 6. Verifikation

```powershell
$checks = @(
    "backend/app/tools/implementations/__init__.py",
    "backend/app/tools/implementations/base.py",
    "backend/app/tools/implementations/filesystem.py",
    "backend/app/tools/implementations/shell.py",
    "backend/app/tools/implementations/web.py",
    "backend/app/tools/implementations/browser.py",
    "backend/app/tools/implementations/code_execution.py",
    "backend/app/tools/implementations/multimodal.py",
    "backend/app/tools/implementations/devops.py"
)
foreach ($f in $checks) {
    if (Test-Path $f) { Write-Host "OK: $f" } else { Write-Host "MISSING: $f" }
}

cd backend
python -c "
from app.tools.implementations import AgentTooling
from app.tools.implementations.filesystem import FileSystemToolMixin
from app.tools.implementations.shell import ShellToolMixin
from app.tools.implementations.web import WebToolMixin
print('tools/implementations/ OK')
"

# Stubs funktionieren noch für legacy imports
python -c "
from app.tools import AgentTooling
from app.tools_multimodal import MultimodalToolMixin
from app.tools_devops import DevOpsToolMixin
print('Stubs OK')
"
```

---

## 7. Commit

```bash
git add -A
git commit -m "refactor(ddd): split tools.py monolith into tools/implementations/ — Phase 11"
```

---

## Status-Checkliste

- [ ] `tools.py` Methoden-Mapping erstellt (welche Methode → welches Mixin)
- [ ] `implementations/filesystem.py` erstellt mit ALLEN Filesystem-Methoden
- [ ] `implementations/shell.py` erstellt — Command-Security-Checks retained!
- [ ] `implementations/web.py` erstellt — SSRF/URL-Validation retained! + api_connectors + web_search merged
- [ ] `implementations/browser.py` erstellt
- [ ] `implementations/code_execution.py` erstellt
- [ ] `implementations/multimodal.py` erstellt (aus tools_multimodal.py)
- [ ] `implementations/devops.py` erstellt (aus tools_devops.py)
- [ ] `implementations/base.py` erstellt — AgentTooling Assembly
- [ ] `tools.py` Stub erstellt der alles re-exportiert
- [ ] `tools_api_connectors.py` Stub erstellt
- [ ] `tools_multimodal.py` Stub erstellt
- [ ] `tools_devops.py` Stub erstellt
- [ ] `services/web_search.py` Stub erstellt
- [ ] `implementations/__init__.py` befüllt
- [ ] Sicherheits-Checkliste abgehakt
- [ ] Smoke-Test erfolgreich
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_12_AGENT.md](./PHASE_12_AGENT.md)
