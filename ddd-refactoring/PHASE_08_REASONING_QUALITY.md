# PHASE 08 — `reasoning/` + `quality/` Domains

> **Session-Ziel:** Die Reasoning-Pipeline und Quality-Control-Schicht aus `services/` in dedizierte Domänen migrieren. `reasoning/` nutzt `llm/` (via contracts), `shared/`. `quality/` nutzt `reasoning/`, `memory/`, `shared/`.
>
> **Voraussetzung:** PHASE_05 (llm/) + PHASE_07 (memory/) abgeschlossen
> **Folge-Phase:** PHASE_09_TOOLS_CORE.md
> **Geschätzter Aufwand:** ~2–3 Stunden
> **Betroffene Quelldateien:** 16 Dateien

---

## Dateien-Übersicht

### `reasoning/` (10 Dateien)

| Quelldatei | Zieldatei |
|------------|-----------|
| `services/action_parser.py` | `reasoning/action_parser.py` |
| `services/action_augmenter.py` | `reasoning/action_augmenter.py` |
| `services/intent_detector.py` | `reasoning/intent_detector.py` |
| `services/directive_parser.py` | `reasoning/directive_parser.py` |
| `services/request_normalization.py` | `reasoning/request_normalization.py` |
| `services/dynamic_temperature.py` | `reasoning/dynamic_temperature.py` |
| `services/output_parsers.py` | `reasoning/output_parsers.py` |
| `services/reply_shaper.py` | `reasoning/reply_shaper.py` |
| `services/plan_graph.py` | `reasoning/plan_graph.py` |
| `services/prompt_kernel_builder.py` | `reasoning/prompt/kernel_builder.py` |
| `services/prompt_ab_registry.py` | `reasoning/prompt/ab_registry.py` |

### `quality/` (6 Dateien)

| Quelldatei | Zieldatei |
|------------|-----------|
| `services/reflection_service.py` | `quality/reflection_service.py` |
| `services/verification_service.py` | `quality/verification_service.py` |
| `services/execution_contract.py` | `quality/execution_contract.py` |
| `services/execution_pattern_detector.py` | `quality/execution_pattern_detector.py` |
| `services/self_healing_loop.py` | `quality/self_healing_loop.py` |
| `services/graceful_degradation.py` | `quality/graceful_degradation.py` |

---

## 1. `reasoning/` Domain

### 1.1 Basis-Dateien kopieren (8 Dateien auf `reasoning/`-Ebene)

```powershell
$files = @(
    "action_parser", "action_augmenter", "intent_detector", "directive_parser",
    "request_normalization", "dynamic_temperature", "output_parsers",
    "reply_shaper", "plan_graph"
)
foreach ($f in $files) {
    Copy-Item "backend/app/services/$f.py" "backend/app/reasoning/$f.py"
    Write-Host "Copied: $f.py"
}
```

**Imports aller Dateien prüfen:**
```powershell
Select-String -Path "backend/app/reasoning/*.py" -Pattern "^from app\." | Where-Object { $_.Line -notmatch "app\.(shared|config|llm|contracts)" }
```

Erlaubt in `reasoning/`:
- `from app.shared.*`
- `from app.config.*`
- `from app.llm.*` (via contracts, nicht direkter Agent-Import)
- `from app.contracts.*`

Verboten: `from app.agent.*`, `from app.tools.*`, `from app.transport.*`

**Häufige interne Querverweise die gefixt werden müssen:**
- `from app.services.action_parser import ...` → `from app.reasoning.action_parser import ...`
- `from app.services.output_parsers import ...` → `from app.reasoning.output_parsers import ...`
- `from app.services.prompt_kernel_builder import ...` → `from app.reasoning.prompt.kernel_builder import ...`

---

### 1.2 Prompt-Unterverzeichnis

#### `services/prompt_kernel_builder.py` → `reasoning/prompt/kernel_builder.py`

```powershell
Copy-Item "backend/app/services/prompt_kernel_builder.py" "backend/app/reasoning/prompt/kernel_builder.py"
```

**Imports prüfen:** Änderungen:
- `from app.services.prompt_ab_registry import ...` → `from app.reasoning.prompt.ab_registry import ...`

#### `services/prompt_ab_registry.py` → `reasoning/prompt/ab_registry.py`

```powershell
Copy-Item "backend/app/services/prompt_ab_registry.py" "backend/app/reasoning/prompt/ab_registry.py"
```

---

### 1.3 Prompt-Templates migrieren

Die Prompt-Templates liegen aktuell unter `app/prompts/`:
```powershell
Get-ChildItem "backend/app/prompts" -Name
```

Diese werden nach `reasoning/prompt/templates/` verschoben:
```powershell
# Inhalt prüfen
Get-ChildItem "backend/app/prompts" -Recurse -Name

# Dateien kopieren (nicht löschen — original bleibt als Symlink/Stub bis Phase 18)
Copy-Item "backend/app/prompts" "backend/app/reasoning/prompt/templates" -Recurse
```

> **HINWEIS:** Wenn `kernel_builder.py` auf `prompts/` mit `Path(__file__).parent / ".." / "prompts"` verweist, muss dieser Pfad auf den neuen Ort angepasst werden: `Path(__file__).parent / "templates"`

---

### 1.4 Stubs für alle `services/` Originale

```powershell
$stubs = @{
    "action_parser" = "app.reasoning.action_parser"
    "action_augmenter" = "app.reasoning.action_augmenter"
    "intent_detector" = "app.reasoning.intent_detector"
    "directive_parser" = "app.reasoning.directive_parser"
    "request_normalization" = "app.reasoning.request_normalization"
    "dynamic_temperature" = "app.reasoning.dynamic_temperature"
    "output_parsers" = "app.reasoning.output_parsers"
    "reply_shaper" = "app.reasoning.reply_shaper"
    "plan_graph" = "app.reasoning.plan_graph"
    "prompt_kernel_builder" = "app.reasoning.prompt.kernel_builder"
    "prompt_ab_registry" = "app.reasoning.prompt.ab_registry"
}

foreach ($orig in $stubs.Keys) {
    $new = $stubs[$orig]
    $content = "# DEPRECATED: moved to $new`nfrom $new import *  # noqa: F401, F403"
    Set-Content "backend/app/services/$orig.py" $content
    Write-Host "Stub created: $orig.py"
}
```

---

### 1.5 `reasoning/__init__.py` befüllen

```python
# backend/app/reasoning/__init__.py
"""
Reasoning and prompt processing domain.
Imports allowed from: llm/ (via contracts), shared/, config/
"""
from app.reasoning.action_parser import ActionParser
from app.reasoning.action_augmenter import ActionAugmenter
from app.reasoning.intent_detector import IntentDetector
from app.reasoning.directive_parser import DirectiveParser
from app.reasoning.request_normalization import RequestNormalizer
from app.reasoning.dynamic_temperature import DynamicTemperature
from app.reasoning.output_parsers import OutputParser
from app.reasoning.reply_shaper import ReplyShaper
from app.reasoning.plan_graph import PlanGraph

__all__ = [
    "ActionParser", "ActionAugmenter", "IntentDetector", "DirectiveParser",
    "RequestNormalizer", "DynamicTemperature", "OutputParser", "ReplyShaper", "PlanGraph",
]
```

### 1.6 `reasoning/prompt/__init__.py`

```python
# backend/app/reasoning/prompt/__init__.py
from app.reasoning.prompt.kernel_builder import PromptKernelBuilder
from app.reasoning.prompt.ab_registry import PromptAbRegistry

__all__ = ["PromptKernelBuilder", "PromptAbRegistry"]
```

---

## 2. `quality/` Domain

### 2.1 Alle 6 Dateien kopieren

```powershell
$qualityFiles = @(
    "reflection_service", "verification_service", "execution_contract",
    "execution_pattern_detector", "self_healing_loop", "graceful_degradation"
)
foreach ($f in $qualityFiles) {
    Copy-Item "backend/app/services/$f.py" "backend/app/quality/$f.py"
    Write-Host "Copied: $f.py"
}
```

**Imports aller quality/-Dateien prüfen:**
```powershell
Select-String -Path "backend/app/quality/*.py" -Pattern "^from app\." | Where-Object { $_.Line -notmatch "app\.(shared|config|reasoning|memory)" }
```

Erlaubt in `quality/`:
- `from app.shared.*`
- `from app.config.*`
- `from app.reasoning.*`
- `from app.memory.*`

Verboten: `from app.agent.*`, `from app.tools.*`, `from app.transport.*`

**Häufige Imports die gefixt werden müssen:**
- `from app.services.reflection_service import ...` (intern zwischen quality-Dateien) → `from app.quality.reflection_service import ...`
- `from app.services.reflection_feedback_store import ...` → `from app.memory.reflection_store import ...`
- `from app.services.action_parser import ...` → `from app.reasoning.action_parser import ...`

---

### 2.2 Stubs für quality/ Originale

```powershell
$qualityStubs = @{
    "reflection_service" = "app.quality.reflection_service"
    "verification_service" = "app.quality.verification_service"
    "execution_contract" = "app.quality.execution_contract"
    "execution_pattern_detector" = "app.quality.execution_pattern_detector"
    "self_healing_loop" = "app.quality.self_healing_loop"
    "graceful_degradation" = "app.quality.graceful_degradation"
}

foreach ($orig in $qualityStubs.Keys) {
    $new = $qualityStubs[$orig]
    $content = "# DEPRECATED: moved to $new`nfrom $new import *  # noqa: F401, F403"
    Set-Content "backend/app/services/$orig.py" $content
}
```

---

### 2.3 `quality/__init__.py` befüllen

```python
# backend/app/quality/__init__.py
"""
Quality control and self-healing domain.
Imports allowed from: reasoning/, memory/, shared/, config/
"""
from app.quality.reflection_service import ReflectionService
from app.quality.verification_service import VerificationService
from app.quality.execution_contract import ExecutionContract
from app.quality.execution_pattern_detector import ExecutionPatternDetector
from app.quality.self_healing_loop import SelfHealingLoop
from app.quality.graceful_degradation import GracefulDegradation

__all__ = [
    "ReflectionService", "VerificationService", "ExecutionContract",
    "ExecutionPatternDetector", "SelfHealingLoop", "GracefulDegradation",
]
```

---

## 3. Verifikation

```powershell
# Dateien prüfen
$checks = @(
    "backend/app/reasoning/action_parser.py",
    "backend/app/reasoning/action_augmenter.py",
    "backend/app/reasoning/intent_detector.py",
    "backend/app/reasoning/directive_parser.py",
    "backend/app/reasoning/request_normalization.py",
    "backend/app/reasoning/dynamic_temperature.py",
    "backend/app/reasoning/output_parsers.py",
    "backend/app/reasoning/reply_shaper.py",
    "backend/app/reasoning/plan_graph.py",
    "backend/app/reasoning/prompt/kernel_builder.py",
    "backend/app/reasoning/prompt/ab_registry.py",
    "backend/app/quality/reflection_service.py",
    "backend/app/quality/verification_service.py",
    "backend/app/quality/execution_contract.py",
    "backend/app/quality/execution_pattern_detector.py",
    "backend/app/quality/self_healing_loop.py",
    "backend/app/quality/graceful_degradation.py"
)
foreach ($f in $checks) {
    if (Test-Path $f) { Write-Host "OK: $f" } else { Write-Host "MISSING: $f" }
}

cd backend
python -c "
from app.reasoning import ActionParser, IntentDetector, ReplyShaper, PlanGraph
from app.reasoning.prompt import PromptKernelBuilder
from app.quality import ReflectionService, VerificationService, SelfHealingLoop
print('reasoning/ + quality/ OK')
"

# Stubs prüfen
python -c "
from app.services.action_parser import ActionParser
from app.services.reflection_service import ReflectionService
print('Stubs OK')
"
```

---

## 4. Commit

```bash
git add -A
git commit -m "refactor(ddd): migrate reasoning/ and quality/ domains — Phase 08"
```

---

## Status-Checkliste

- [ ] `reasoning/` alle 9 Basis-Dateien kopiert, Imports bereinigt
- [ ] `reasoning/prompt/kernel_builder.py` erstellt, Prompt-Pfad gefixt
- [ ] `reasoning/prompt/ab_registry.py` erstellt
- [ ] Prompt-Templates nach `reasoning/prompt/templates/` kopiert
- [ ] Stubs für alle 11 reasoning/-Originale erstellt
- [ ] `reasoning/__init__.py` + `reasoning/prompt/__init__.py` befüllt
- [ ] `quality/` alle 6 Dateien kopiert, Imports bereinigt
- [ ] Stubs für alle 6 quality/-Originale erstellt
- [ ] `quality/__init__.py` befüllt
- [ ] Smoke-Test erfolgreich
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_09_TOOLS_CORE.md](./PHASE_09_TOOLS_CORE.md)
