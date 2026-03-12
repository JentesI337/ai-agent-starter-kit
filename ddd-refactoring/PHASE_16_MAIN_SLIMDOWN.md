# PHASE 16 — `main.py` Slim-down

> **Session-Ziel:** `main.py` (~1144 Zeilen) von einem 1144-Zeilen-Monolithen zu einem schlanken ~50-Zeilen-Entry-Point reduzieren. Alle Handler-Registrierungs-Logik ist bereits in den Routern (Phase 15). Alle Bootstrap-Logik ist in transport/ (Phase 14).
>
> **Voraussetzung:** PHASE_15 (transport/routers/) abgeschlossen
> **Folge-Phase:** PHASE_17_BACKEND_ROOT_CLEANUP.md
> **Geschätzter Aufwand:** ~2–3 Stunden
> **Betroffene Dateien:** `main.py` (rewrite)

---

## Ist-Zustand `main.py`

`main.py` importiert aktuell:
- ~40+ Handler-Funktionen aus `handlers/`
- Alle Router-Instanzen aus `routers/`
- `ControlPlaneState` und alle State-Klassen
- `build_fastapi_app`, `build_lifespan_context`
- Config, Memory, Tools, etc.
- FastAPI `TestClient`, `Request`, `Response` etc.

Das SOLL nach der Refaktorierung so aussehen:

---

## Ziel-`main.py` (~50 Zeilen)

```python
# backend/app/main.py
"""
AI Agent Starter Kit — Application Entry Point.

This is intentionally slim. All domain logic lives in:
  transport/app_factory.py  — FastAPI app creation + middleware
  transport/startup.py      — Lifespan startup/shutdown
  transport/routers/        — All HTTP/WS route handlers
  agent/                    — Core agent domain
"""
from __future__ import annotations

from app.transport.app_factory import build_fastapi_app

# Build the FastAPI application instance.
# All routers, middleware, and startup hooks are registered inside build_fastapi_app().
app = build_fastapi_app()

__all__ = ["app"]
```

---

## Vorgehen

### Schritt 1: Backup des alten main.py

```powershell
Copy-Item "backend/app/main.py" "backend/app/main.py.phase16_backup"
```

### Schritt 2: Sicherstellen dass `build_fastapi_app()` alles erledigt

Öffne `backend/app/transport/app_factory.py` und prüfe:
- [ ] `include_all_routers(app)` wird aufgerufen
- [ ] Middleware wird registriert (CORS, Auth etc.)
- [ ] Lifespan Context (`on_startup`, `on_shutdown`) wird konfiguriert
- [ ] Error Handlers werden registriert

Falls irgendeins fehlt: **Das muss ZUERST in `app_factory.py` implementiert werden**, bevor `main.py` geleert wird.

### Schritt 3: Alle Handler-Registrierungen aus `main.py` extrahieren

```powershell
# Welche Handler-Funktionen aus main.py verwendet werden
Select-String -Path "backend/app/main.py" -Pattern "add_api_route|app\.get|app\.post|app\.put|app\.delete|app\.websocket" | Select-Object LineNumber, Line
```

Für jeden gefundenen direkten Route-Handler in `main.py`:
- Prüfen ob er bereits in einem der neuen `transport/routers/*.py` existiert
- Falls nicht → ZUERST in den richtigen Router verschieben, DANN `main.py` aufräumen

### Schritt 4: Handler-to-Router-Registrierung prüfen

```powershell
# Welche Handler aus main.py kommen?
Select-String -Path "backend/app/main.py" -Pattern "from app.handlers\." | Select-Object LineNumber, Line
```

Alle gefundenen Handler müssen in Phase 15 ihren Router bekommen haben.  
Falls etwas fehlt → Jetzt in den entsprechenden Router einfügen.

### Schritt 5: main.py auf Minimum reduzieren

```python
# backend/app/main.py — NEU (nach Phase 16)
"""
AI Agent Starter Kit — Application Entry Point.
"""
from __future__ import annotations

from app.transport.app_factory import build_fastapi_app

app = build_fastapi_app()

__all__ = ["app"]
```

---

## Verifikation — Vollständiger App-Start

```powershell
cd backend

# 1. Import-Test
python -c "
from app.main import app
print('App imported OK')
print('Routes:', len([r for r in app.routes]))
"

# 2. App starten (ohne zu blockieren — kurzer Check)
python -c "
import uvicorn
from app.main import app
# Nur Config-Check, kein echter Start
config = uvicorn.Config(app, host='127.0.0.1', port=8000)
print('Uvicorn config OK:', config.host, config.port)
"

# 3. Test-Suite ausführen
python -m pytest tests/ -x -q --tb=short 2>&1 | Select-Object -First 50
```

---

## Häufige Probleme und Lösungen

### Problem: `ImportError: cannot import name 'X' from 'app.main'`

**Ursache:** Ein external Script/Test importiert direkt aus `main.py`

**Lösung:** Prüfen wer `from app.main import X` schreibt:
```powershell
Select-String -Path "backend/**/*.py" -Pattern "from app\.main import" -Recurse | Select-Object Filename, Line
```
Diese Imports auf die neuen Quellen umlenken.

---

### Problem: Route ist doppelt registriert

**Ursache:** Handler existiert noch in `main.py` UND im neuen Router

**Lösung:** Aus `main.py` entfernen (der Router registriert es bereits via `include_all_routers`).

---

### Problem: Middleware fehlt nach Slim-down

**Ursache:** Middleware war in `main.py` definiert, nicht in `app_factory.py`

**Lösung:** Middleware in `transport/app_factory.py` verschieben:
```python
def build_fastapi_app() -> FastAPI:
    app = FastAPI(...)
    
    # Middleware
    app.add_middleware(CORSMiddleware, ...)
    app.add_middleware(...)
    
    # Routers
    include_all_routers(app)
    
    return app
```

---

## Commit

```bash
git add -A
git commit -m "refactor(ddd): slim down main.py to entry-point only — Phase 16"
```

---

## Status-Checkliste

- [ ] Backup von `main.py` erstellt
- [ ] `build_fastapi_app()` stellt sicher dass alle Routers, Middleware, Lifespan-Hooks registriert sind
- [ ] Alle direkten Route-Handler aus `main.py` in entsprechende Router verschoben
- [ ] `main.py` auf ~50 Zeilen reduziert
- [ ] `python -c "from app.main import app"` erfolgreich
- [ ] Alle Routes noch vorhanden (Anzahl vergleichen mit Backup)
- [ ] Test-Suite läuft durch (oder bekannte Fehler dokumentiert)
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_17_BACKEND_ROOT_CLEANUP.md](./PHASE_17_BACKEND_ROOT_CLEANUP.md)
