# PHASE 23 — Test-Suite aktualisieren

> **Session-Ziel:** Alle Tests auf die neuen DDD-Pfade aktualisieren. Veraltete Mock-Paths reparieren, fehlende Tests für neue Domains hinzufügen, Test-Coverage-Baseline herstellen.
>
> **Voraussetzung:** PHASE_22 (Import-Verifikation, 0 ruff-Fehler)
> **Folge-Phase:** PHASE_24_E2E_VERIFICATION.md
> **Geschätzter Aufwand:** ~4–6 Stunden
> **Betroffene Verzeichnisse:** `backend/tests/`

---

## Ist-Zustand

```powershell
cd backend

# Teststruktur inventarisieren
Get-ChildItem tests/ -Recurse -Filter "*.py" | Select-Object FullName
```

Erwartete Struktur (wird beim Lauf sichtbar):
```
tests/
├── conftest.py
├── test_agent.py
├── test_agent_runner.py
├── test_tools.py
├── test_memory.py
├── test_state.py
├── test_orchestration.py
├── test_routers.py
└── ...
```

---

## Schritt 1: Test-Import-Audit

```powershell
cd backend

# Alle veralteten Imports in Tests
Select-String -Path "tests/**/*.py" -Pattern "from app\.(services|routers|handlers|orchestrator|interfaces|model_routing|tool_modules|agents)\." -Recurse |
    Select-Object Filename, LineNumber, Line |
    Format-Table -AutoSize |
    Tee-Object -FilePath "../test_import_audit.txt"

# Anzahl betroffener Test-Dateien
(Select-String -Path "tests/**/*.py" -Pattern "from app\.(services|routers|handlers|orchestrator|interfaces)\." -Recurse | 
    Select-Object Filename -Unique).Count
```

---

## Schritt 2: Import-Path-Ersetzungen in Tests

Für jede betroffene Test-Datei:

### Alte → Neue Import-Paths

| Alter Import | Neuer Import |
|---|---|
| `from app.services.agent_service import` | `from app.agent.head_agent import` |
| `from app.services.memory_service import` | `from app.memory.memory_service import` |
| `from app.services.state_service import` | `from app.state.state_store import` |
| `from app.services.tool_service import` | `from app.tools.execution.executor import` |
| `from app.orchestrator.pipeline_runner import` | `from app.orchestration.pipeline_runner import` |
| `from app.interfaces.request_context import` | `from app.contracts.request_context import` |
| `from app.model_routing.router import` | `from app.llm.routing.router import` |
| `from app.routers.X import router` | `from app.transport.routers.X import router` |

### Automatische Ersetzung (PowerShell)

```powershell
cd backend/tests

# Vorsichtig: Nur auf Test-Verzeichnis beschränkt!
$replacements = @{
    "from app.services.agent_service"   = "from app.agent.head_agent"
    "from app.services.memory_service"  = "from app.memory.memory_service"
    "from app.services.state_service"   = "from app.state.state_store"
    "from app.orchestrator."            = "from app.orchestration."
    "from app.interfaces."              = "from app.contracts."
    "from app.model_routing."           = "from app.llm.routing."
}

Get-ChildItem -Filter "*.py" -Recurse | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    $modified = $false
    foreach ($old in $replacements.Keys) {
        if ($content -match [regex]::Escape($old)) {
            $content = $content -replace [regex]::Escape($old), $replacements[$old]
            $modified = $true
        }
    }
    if ($modified) {
        Set-Content $_.FullName -Value $content -NoNewline
        Write-Host "Updated: $($_.Name)"
    }
}
```

---

## Schritt 3: Mock-Patch-Paths reparieren

Mocks die `patch()` verwenden, zeigen auf alte Pfade:

```python
# ALT (kaputt nach Migration)
@patch("app.services.agent_service.AgentService.run")
def test_agent_run(mock_run): ...

# NEU
@patch("app.agent.head_agent.HeadAgent.run")
def test_agent_run(mock_run): ...
```

```powershell
cd backend

# Mock-Patch-Paths mit alten Pfaden
Select-String -Path "tests/**/*.py" -Pattern "@patch\(['\"]app\.(services|orchestrator|interfaces|routers|handlers|model_routing)" -Recurse |
    Select-Object Filename, LineNumber, Line
```

Jeden Fund manuell auf den neuen Pfad aktualisieren.

---

## Schritt 4: `conftest.py` prüfen und aktualisieren

```powershell
cd backend

Get-Content tests/conftest.py
```

Typische `conftest.py`-Updates:

```python
# ALT
@pytest.fixture
def agent_service():
    from app.services.agent_service import AgentService
    return AgentService()

# NEU
@pytest.fixture
def head_agent():
    from app.agent.head_agent import HeadAgent
    from app.config.settings import get_settings
    return HeadAgent(settings=get_settings())

# ALT
@pytest.fixture
def db_state():
    from app.services.state_service import StateService
    return StateService()

# NEU  
@pytest.fixture
def state_store():
    from app.state.state_store import StateStore
    return StateStore(":memory:")
```

---

## Schritt 5: Test-Coverage-Check

```powershell
cd backend

# Coverage für neue DDD-Domains
pip install pytest-cov

python -m pytest tests/ \
    --cov=app \
    --cov-report=term-missing \
    --cov-report=html:../coverage_phase23 \
    -q \
    2>&1 | Tee-Object -FilePath "../coverage_phase23.txt"

# Coverage-Zusammenfassung
Select-String -Path "../coverage_phase23.txt" -Pattern "TOTAL|app/" |
    Select-Object -Last 20
```

---

## Schritt 6: Fehlende Tests für neue Domains

Prüfen welche neuen DDD-Domains noch keine Tests haben:

```powershell
cd backend

$ddd_domains = @("shared", "contracts", "config", "policy", "state", "llm", "memory", "session", "reasoning", "quality", "tools", "agent", "orchestration", "multi_agency", "workflows", "skills", "connectors", "transport")

foreach ($domain in $ddd_domains) {
    $test_exists = Test-Path "tests/test_$domain.py"
    $test_dir = Test-Path "tests/$domain/"
    if (-not $test_exists -and -not $test_dir) {
        Write-Host "⚠️  NO TESTS: $domain"
    } else {
        Write-Host "✅ Tests exist: $domain"
    }
}
```

Für jede Domain ohne Tests: Minimaler Smoke-Test erstellen.

---

## Schritt 7: Minimal-Tests für kritische Domains

Falls noch keine Tests für eine Domain vorhanden sind, Minimal-Tests erstellen:

### `tests/test_agent_ddd.py` (Beispiel)

```python
"""Smoke tests for the refactored agent/ domain."""
import pytest
from app.agent.head_agent import HeadAgent


def test_head_agent_import():
    """HeadAgent can be imported without errors."""
    assert HeadAgent is not None


def test_head_agent_instantiation(test_settings):
    """HeadAgent can be instantiated with valid settings."""
    agent = HeadAgent(settings=test_settings)
    assert agent is not None
```

### `tests/test_tools_ddd.py` (Beispiel)

```python
"""Smoke tests for the refactored tools/ domain."""
import pytest
from app.tools.registry.tool_registry import ToolRegistry


def test_tool_registry_import():
    """ToolRegistry can be imported."""
    assert ToolRegistry is not None


def test_tool_registry_empty():
    """Empty registry returns empty list."""
    registry = ToolRegistry()
    assert registry.list_tools() == []
```

---

## Schritt 8: Tests ausführen

```powershell
cd backend

# Alle Tests
python -m pytest tests/ -v --tb=short 2>&1 | Tee-Object -FilePath "../test_results_phase23.txt"

# Nur Failures zeigen
Select-String -Path "../test_results_phase23.txt" -Pattern "FAILED|ERROR" | Select-Object Line
```

---

## Schritt 9: Bekannte Test-Fehler dokumentieren

Falls Tests nach korrekten Reparaturen noch fehlschlagen weil **Funktionalität in der DDD-Migration fehlt** (nicht wegen falscher Imports):

Datei `backend/TEST_BASELINE.md` aktualisieren:

```markdown
## Phase 23 Baseline — nach DDD-Migration

### Bekannte fehlgeschlagene Tests:
- `test_X` — Funktionalität noch nicht in agent/ implementiert (TODO: Phase X)
- `test_Y` — Integration mit LLM benötigt Mock-Setup

### Neue Test-Abdeckung:
- agent/: 45%
- tools/: 62%
- orchestration/: 38%
- transport/: 71%
```

---

## Commit

```bash
git add -A
git commit -m "test: update test imports to DDD paths, add missing domain tests — Phase 23"
```

---

## Status-Checkliste

- [ ] Test-Import-Audit durchgeführt
- [ ] Alle alten Import-Paths in Tests ersetzt
- [ ] Mock-Patch-Paths aktualisiert
- [ ] `conftest.py` aktualisiert (Fixtures auf neue Domains)
- [ ] Coverage-Report erstellt
- [ ] Fehlende Tests für neue Domains identifiziert
- [ ] Minimal-Smoke-Tests für wichtige Domains erstellt
- [ ] Tests ausführen bestanden (oder Failures dokumentiert)
- [ ] `TEST_BASELINE.md` aktualisiert
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_24_E2E_VERIFICATION.md](./PHASE_24_E2E_VERIFICATION.md)
