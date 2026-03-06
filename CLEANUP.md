# CLEANUP — Solo-Dev Survival Plan

## Was schon solide ist (nicht anfassen)

Diese Teile sind produktionsreif. Hier keine Energie verschwenden:

- **LLM Client** (`app/llm_client.py`) — Retry, Backoff, Timeout, Streaming: alles sauber
- **SSRF-Schutz** (`app/url_validator.py`) — Defense-in-depth gegen Cloud-Metadata, DNS-Rebinding
- **State Encryption** (`app/services/state_encryption.py`) — AES-256-GCM, Timing-Attack-safe
- **Pydantic Models** (`app/control_models.py`) — Sauber, minimal, korrekt
- **Dependencies** (`requirements.txt`) — 6 Deps, gelockt, kein Bloat
- **Frontend** (`frontend/src/`) — Aufgeräumt, 2 Pages, 4 Services
- **Testsuite** — 91/91 grün, E2E + Contract-Tests vorhanden

---

## Die 3 Regeln gegen Vibe Coding (für Solo-Devs)

### Regel 1: Kein Dokument ohne Ablaufdatum
Jede .md-Datei die kein README ist → braucht ein `## Status` mit Datum.
Wenn der Status älter als 2 Wochen ist → löschen oder aktualisieren.
Nie eine neue Planungsdatei schreiben, wenn die alte noch offen ist.

### Regel 2: Config hat ein Budget
Neue Config-Felder nur wenn ein realer User sie braucht.
Kein `os.getenv()` für Dinge die sich nie ändern (Agent-Namen, Prompt-Defaults).
Ziel: < 50 konfigurierbare Felder. Alles andere ist Code-Konstante.

### Regel 3: Jede Datei verdient ihren Platz
Vor jedem Commit: Würde ich diese Datei einem neuen Teammitglied erklären können?
Wenn nein → gehört sie nicht ins Repo.

---

## Cleanup-Plan (4 Runden, priorisiert nach Impact)

### Runde 1 — Ballast abwerfen (1 Stunde)

Nur löschen. Kein Code anfassen.

```
# Tote Dateien im Backend
backend/index.html          ← Taschenrechner-HTML, gehört nicht hierher
backend/script.js           ← dito
backend/styles.css          ← dito
backend/-p/                 ← leeres Verzeichnis, Artefakt
backend/runtime_state.json  ← Duplikat (Root-Version ist aktueller)
backend/app/models/         ← leeres Package

# Redundante Planungsdokumente (Root)
FIXROADTOGOLD.md            ← Referenziert ROADTOTOOLGOLD, veraltet
ROADTOTOOLGOLD.md           ← Roadmap erledigt oder obsolet
roadmaptoautonomy.md        ← Dritte Roadmap, nie konsolidiert
REFACTORING.md              ← Refactoring-Plan, nie umgesetzt
SECURITYAUDIT.md            ← Audit abgeschlossen
SECURITY_FIXPLAN.md         ← Fixes daraus sind drin oder irrelevant
SECURITYPATCHBUGREPORT.md   ← dito
QUALITY_ASSESSMENT_BACKEND_PROMPT.md ← Assessment erledigt

# Marketing im Code-Repo
HANDOUT_MARKETING.txt       ← In separates Repo oder Google Doc verschieben
```

**Prüfe vor dem Löschen:** Jede Datei kurz öffnen und bestätigen, dass nichts Wertvolles drin ist, das du verlieren würdest. Dann löschen. Git hat die History — nichts geht verloren.

---

### Runde 2 — Die 3 echten Bugs fixen (2-3 Stunden)

Diese drei Probleme sind die einzigen, die tatsächlich zu Crashes führen:

#### Bug 1: Race Condition auf `_active_run_count` (agent.py)

```python
# VORHER (Zeile ~572 in agent.py)
self._active_run_count += 1

# NACHHER
async with self._run_lock:          # ← asyncio.Lock() im __init__ anlegen
    self._active_run_count += 1
```

Gleiches im `finally`-Block beim Dekrementieren.

#### Bug 2: State-File-Korruption (runtime_manager.py)

```python
# VORHER — schreibt direkt in die Datei
path.write_text(json.dumps(state, indent=2))

# NACHHER — Atomic Write
import tempfile
tmp = path.with_suffix('.tmp')
tmp.write_text(json.dumps(state, indent=2))
tmp.replace(path)   # ← Atomic auf POSIX, fast-atomic auf Windows
```

#### Bug 3: Memory Leak in WebSocket-Handler (ws_handler.py)

```python
# pending_clarifications wächst unbegrenzt
# → Cleanup beim Disconnect hinzufügen:
async def on_disconnect(self, ...):
    self.pending_clarifications.clear()
```

---

### Runde 3 — Config-Diät (2 Stunden)

`config.py` hat 188 Felder. Ziel: ~50.

**Schritt 1:** Prompt-Defaults aus Config entfernen. Sie ändern sich nie per Env-Var.

```python
# STATT:
head_agent_system_prompt: str = os.getenv("HEAD_AGENT_SYSTEM_PROMPT", "Du bist...")

# MACH:
# In einer separaten Datei: app/prompts.py
HEAD_AGENT_SYSTEM_PROMPT = "Du bist..."
```

→ Alle `*_agent_*_prompt`-Felder raus aus Settings → nach `app/prompts.py` als Konstanten.
  Das sind ~80 Felder weniger.

**Schritt 2:** Agent-Namen sind Konstanten, keine Config:

```python
# STATT 15× os.getenv:
agent_name: str = os.getenv("AGENT_NAME", "head-agent")

# MACH:
# In app/agents/registry.py oder direkt als Konstante
AGENT_NAME = "head-agent"
```

→ ~15 Felder weniger.

**Schritt 3:** Pipeline-Runner-Recovery-Flags konsolidieren.
  21 einzelne Flags → 1 Dataclass `PipelineRecoveryConfig` mit sinnvollen Defaults:

```python
class PipelineRecoveryConfig(BaseModel):
    backoff_base_ms: int = 500
    backoff_max_ms: int = 8000
    backoff_multiplier: float = 2.0
    # ... nur die 5-6 die wirklich relevant sind
```

---

### Runde 4 — Copy-Paste eliminieren (1-2 Stunden)

#### Handler-Boilerplate (7× kopiert)

Alle 7 Handler-Dateien haben identisches Pattern:
```python
_deps = None
def configure(deps): global _deps; _deps = deps
def _require_deps(): ...
```

→ Einmalig als Base-Klasse oder Decorator:

```python
# app/handlers/_base.py
from typing import TypeVar, Generic
T = TypeVar("T")

class HandlerModule(Generic[T]):
    def __init__(self) -> None:
        self._deps: T | None = None

    def configure(self, deps: T) -> None:
        self._deps = deps

    @property
    def deps(self) -> T:
        if self._deps is None:
            raise RuntimeError(f"{type(self).__name__} not configured")
        return self._deps
```

#### Error-Taxonomie: 1 Quelle nutzen

`error_taxonomy.py` existiert bereits, wird aber nicht überall verwendet.
→ Imports in `agent.py` und `fallback_state_machine.py` auf `error_taxonomy.py` umbiegen.
→ Lokale Pattern-Definitionen löschen.

---

## Was du NICHT tun solltest

| Versuchung | Warum nicht |
|-----------|-------------|
| agent.py in 10 Dateien aufteilen | Funktioniert, Tests grün. Refactoring ohne Anlass = neues Vibe Coding |
| Mehr Exception-Klassen konsolidieren | Die 7 LLM-Klassen sind hässlich aber funktional. Kein Bug. |
| Test-Dateien umstrukturieren | 113 Dateien, 91 grün. Nicht anfassen solange sie laufen. |
| Skills-System entfernen | Unklar ob genutzt. Im Zweifel lassen, nicht investieren. |
| issues/ aufräumen | Wenn du sie nicht aktiv nutzt, lösch das ganze Verzeichnis. |
| examplerepos/ aufräumen | Entweder du brauchst sie → .gitignore. Oder nicht → löschen. |

---

## Reihenfolge für maximalen Impact

```
Runde 1 (Löschen)          → Sofort, 1h    → Repo wird übersichtlich
Runde 2 (3 Bugs fixen)     → Diese Woche   → App wird stabiler
Runde 3 (Config-Diät)      → Nächste Woche → Wartbarkeit steigt
Runde 4 (Copy-Paste)       → Wenn Lust da  → Code wird sauberer
```

Gesamtaufwand: **~6-8 Stunden** für eine deutlich stabilere und wartbarere Codebase.

---

## Danach: Anti-Vibe-Coding-Checkliste (vor jedem Commit)

- [ ] Habe ich eine neue .md-Datei erstellt? → Brauche ich die wirklich?
- [ ] Habe ich ein neues Config-Feld hinzugefügt? → Wird das je jemand ändern?
- [ ] Habe ich Code kopiert statt wiederverwendet? → Gibt es das Pattern schon?
- [ ] Habe ich eine neue Service-Datei erstellt? → Kann das in eine bestehende?
- [ ] Habe ich Code auskommentiert statt gelöscht? → Git hat die History.
- [ ] Laufen die Tests noch? → `pytest tests/ -q` vor jedem Push.
