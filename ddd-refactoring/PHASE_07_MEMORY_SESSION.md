# PHASE 07 — `memory/` + `session/` Domains

> **Session-Ziel:** Langzeit-Memory und Session-Verwaltung in eigene Domänen migrieren. `memory/` nutzt `state/` + `shared/`. `session/` nutzt `memory/` + `state/` + `shared/` + `policy/`.
>
> **Voraussetzung:** PHASE_04 (state/) + PHASE_03 (policy/) abgeschlossen
> **Folge-Phase:** PHASE_08_REASONING_QUALITY.md
> **Geschätzter Aufwand:** ~2 Stunden
> **Betroffene Quelldateien:** 10 Dateien

---

## Dateien-Übersicht

| Quelldatei | Zieldatei |
|------------|-----------|
| `app/memory.py` | `app/memory/session_memory.py` |
| `app/services/long_term_memory.py` | `app/memory/long_term.py` |
| `app/services/failure_retriever.py` | `app/memory/failure_retriever.py` |
| `app/services/reflection_feedback_store.py` | `app/memory/reflection_store.py` |
| `app/services/learning_loop.py` | `app/memory/learning_loop.py` |
| `app/services/adaptive_tool_selector.py` | `app/memory/adaptive_selector.py` |
| `app/services/session_inbox_service.py` | `app/session/inbox_service.py` |
| `app/services/session_query_service.py` | `app/session/query_service.py` |
| `app/services/session_security.py` | `app/session/security.py` |
| `app/services/compaction_service.py` | `app/session/compaction.py` |

---

## 1. `memory/` Domain

### 1.1 `app/memory.py` → `app/memory/session_memory.py`

> **ACHTUNG:** Namenskonflikt! Es gibt das Verzeichnis `app/memory/` (neu) UND die Datei `app/memory.py`.  
> Python kann nicht gleichzeitig `app.memory` als Datei UND Verzeichnis haben.  
> **Die Datei `app/memory.py` muss zuerst als Stub umgewandelt werden, dann das Verzeichnis genutzt werden.**

**Schritt 1:** Inhalt von `app/memory.py` nach `app/memory/session_memory.py` kopieren:
```powershell
Copy-Item "backend/app/memory.py" "backend/app/memory/session_memory.py"
```

**Schritt 2:** `app/memory.py` zu einem Weiterleitungs-Stub machen:
```python
# backend/app/memory.py
# DEPRECATED: moved to app.memory.session_memory
# NOTE: This file conflicts with the app/memory/ directory.
# Python will use the directory (package) over this file once the package has __init__.py
# Remove this file in PHASE_18 after all consumers are updated.
```

> **WICHTIGER HINWEIS:** Sobald `app/memory/__init__.py` existiert (was es tut nach PHASE_00),  
> wird Python `from app.memory import MemoryStore` aus dem Paket lesen, NICHT aus der Datei.  
> Das bedeutet: `app/memory.py` ist ab jetzt effektiv "tot" / wird ignoriert.  
> Konsumenten müssen prüfen ob sie noch `from app.memory import MemoryStore` schreiben  
> (das wird dann aus `app/memory/__init__.py` gelesen — das ist OK!).

**Imports in `session_memory.py` prüfen:**
```powershell
Select-String -Path "backend/app/memory/session_memory.py" -Pattern "^from app\."
```

Erlaubt: `state/`, `shared/`, `config/`  
VERBOTEN: `agent/`, `reasoning/`, `tools/`

---

### 1.2 `services/long_term_memory.py` → `memory/long_term.py`

```powershell
Copy-Item "backend/app/services/long_term_memory.py" "backend/app/memory/long_term.py"
```

**Imports prüfen:** Nur `state/`, `shared/`, `config/`.  
Falls `from app.services.session_inbox_service import ...` → wird in Phase 07 (session/) verfügbar als `from app.session.inbox_service import ...`, aber noch nicht sofort — nutze `TYPE_CHECKING` wenn nötig.

**Stub:**
```python
# backend/app/services/long_term_memory.py — DEPRECATED → app.memory.long_term
from app.memory.long_term import *  # noqa: F401, F403
```

---

### 1.3 `services/failure_retriever.py` → `memory/failure_retriever.py`

```powershell
Copy-Item "backend/app/services/failure_retriever.py" "backend/app/memory/failure_retriever.py"
```

**Imports prüfen:** Darf `state/`, `shared/`, `memory/` intern nutzen.

**Stub:**
```python
# backend/app/services/failure_retriever.py — DEPRECATED → app.memory.failure_retriever
from app.memory.failure_retriever import *  # noqa: F401, F403
```

---

### 1.4 `services/reflection_feedback_store.py` → `memory/reflection_store.py`

> **Namensänderung:** `reflection_feedback_store.py` → `reflection_store.py`

```powershell
Copy-Item "backend/app/services/reflection_feedback_store.py" "backend/app/memory/reflection_store.py"
```

**Stub:**
```python
# backend/app/services/reflection_feedback_store.py — DEPRECATED → app.memory.reflection_store
from app.memory.reflection_store import *  # noqa: F401, F403
```

---

### 1.5 `services/learning_loop.py` → `memory/learning_loop.py`

```powershell
Copy-Item "backend/app/services/learning_loop.py" "backend/app/memory/learning_loop.py"
```

**Imports prüfen:**
```powershell
Select-String -Path "backend/app/memory/learning_loop.py" -Pattern "^from app\."
```

Falls `from app.services.reflection_feedback_store import ...` → ändern zu `from app.memory.reflection_store import ...`

**Stub:**
```python
# backend/app/services/learning_loop.py — DEPRECATED → app.memory.learning_loop
from app.memory.learning_loop import *  # noqa: F401, F403
```

---

### 1.6 `services/adaptive_tool_selector.py` → `memory/adaptive_selector.py`

> **Namensänderung:** `adaptive_tool_selector.py` → `adaptive_selector.py`

```powershell
Copy-Item "backend/app/services/adaptive_tool_selector.py" "backend/app/memory/adaptive_selector.py"
```

**Imports prüfen:**  
Falls `from app.services.learning_loop import ...` → `from app.memory.learning_loop import ...`  
Falls `from app.services.long_term_memory import ...` → `from app.memory.long_term import ...`

**Stub:**
```python
# backend/app/services/adaptive_tool_selector.py — DEPRECATED → app.memory.adaptive_selector
from app.memory.adaptive_selector import *  # noqa: F401, F403
```

---

### 1.7 `memory/__init__.py` befüllen

```python
# backend/app/memory/__init__.py
"""
Memory and learning domain.
Imports allowed from: state/, shared/, config/
"""
from app.memory.session_memory import MemoryStore
from app.memory.long_term import LongTermMemory
from app.memory.failure_retriever import FailureRetriever
from app.memory.reflection_store import ReflectionFeedbackStore
from app.memory.learning_loop import LearningLoop
from app.memory.adaptive_selector import AdaptiveToolSelector

__all__ = [
    "MemoryStore",
    "LongTermMemory",
    "FailureRetriever",
    "ReflectionFeedbackStore",
    "LearningLoop",
    "AdaptiveToolSelector",
]
```

---

## 2. `session/` Domain

### 2.1 `services/session_inbox_service.py` → `session/inbox_service.py`

```powershell
Copy-Item "backend/app/services/session_inbox_service.py" "backend/app/session/inbox_service.py"
```

**Imports prüfen:**
```powershell
Select-String -Path "backend/app/session/inbox_service.py" -Pattern "^from app\."
```

Erlaubt: `memory/`, `state/`, `shared/`, `config/`, `policy/`

**Stub:**
```python
# backend/app/services/session_inbox_service.py — DEPRECATED → app.session.inbox_service
from app.session.inbox_service import *  # noqa: F401, F403
```

---

### 2.2 `services/session_query_service.py` → `session/query_service.py`

```powershell
Copy-Item "backend/app/services/session_query_service.py" "backend/app/session/query_service.py"
```

**Imports prüfen:** Interne session/-Querverweise:
- `from app.services.session_inbox_service import ...` → `from app.session.inbox_service import ...`

**Stub:**
```python
# backend/app/services/session_query_service.py — DEPRECATED → app.session.query_service
from app.session.query_service import *  # noqa: F401, F403
```

---

### 2.3 `services/session_security.py` → `session/security.py`

```powershell
Copy-Item "backend/app/services/session_security.py" "backend/app/session/security.py"
```

**Imports prüfen:** Darf `policy/`, `state/`, `shared/` nutzen.

**Stub:**
```python
# backend/app/services/session_security.py — DEPRECATED → app.session.security
from app.session.security import *  # noqa: F401, F403
```

---

### 2.4 `services/compaction_service.py` → `session/compaction.py`

> **Namensänderung:** `compaction_service.py` → `compaction.py`

```powershell
Copy-Item "backend/app/services/compaction_service.py" "backend/app/session/compaction.py"
```

**Imports prüfen:**  
Falls `from app.memory import MemoryStore` → das funktioniert jetzt (via `app.memory.__init__`).  
Falls `from app.services.compaction_service import` irgendwo intern → nicht zu erwarten.

**Stub:**
```python
# backend/app/services/compaction_service.py — DEPRECATED → app.session.compaction
from app.session.compaction import *  # noqa: F401, F403
```

---

### 2.5 `session/__init__.py` befüllen

```python
# backend/app/session/__init__.py
"""
Session management domain.
Imports allowed from: memory/, state/, shared/, config/, policy/
"""
from app.session.inbox_service import SessionInboxService
from app.session.query_service import SessionQueryService
from app.session.security import SessionSecurity
from app.session.compaction import CompactionService

__all__ = [
    "SessionInboxService",
    "SessionQueryService",
    "SessionSecurity",
    "CompactionService",
]
```

---

## 3. Verifikation

```powershell
$checks = @(
    "backend/app/memory/session_memory.py",
    "backend/app/memory/long_term.py",
    "backend/app/memory/failure_retriever.py",
    "backend/app/memory/reflection_store.py",
    "backend/app/memory/learning_loop.py",
    "backend/app/memory/adaptive_selector.py",
    "backend/app/session/inbox_service.py",
    "backend/app/session/query_service.py",
    "backend/app/session/security.py",
    "backend/app/session/compaction.py"
)
foreach ($f in $checks) {
    if (Test-Path $f) { Write-Host "OK: $f" } else { Write-Host "MISSING: $f" }
}

cd backend
python -c "
from app.memory import MemoryStore, LongTermMemory, LearningLoop, AdaptiveToolSelector
from app.session import SessionInboxService, SessionQueryService, CompactionService
print('memory/ + session/ OK')
"

# app/memory.py Stub-Konflikt prüfen
python -c "
# Das Paket (Verzeichnis) hat Vorrang
import app.memory as m
print('memory package takes precedence:', m.__file__)
"
```

---

## 4. Commit

```bash
git add -A
git commit -m "refactor(ddd): migrate memory/ and session/ domains — Phase 07"
```

---

## Status-Checkliste

- [ ] `memory/session_memory.py` erstellt (aus `memory.py`)
- [ ] `memory/long_term.py` erstellt, Stub in Original
- [ ] `memory/failure_retriever.py` erstellt, Stub
- [ ] `memory/reflection_store.py` erstellt (Namensänderung!), Stub
- [ ] `memory/learning_loop.py` erstellt, interne Imports gefixt, Stub
- [ ] `memory/adaptive_selector.py` erstellt (Namensänderung!), Imports gefixt, Stub
- [ ] `memory/__init__.py` befüllt
- [ ] `session/inbox_service.py` erstellt, Stub
- [ ] `session/query_service.py` erstellt, Imports gefixt, Stub
- [ ] `session/security.py` erstellt, Stub
- [ ] `session/compaction.py` erstellt (Namensänderung!), Stub
- [ ] `session/__init__.py` befüllt
- [ ] `app/memory.py` Paket-Konflikt gelöst (Paket hat Vorrang)
- [ ] Smoke-Test erfolgreich
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_08_REASONING_QUALITY.md](./PHASE_08_REASONING_QUALITY.md)
