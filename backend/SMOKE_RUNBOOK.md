# Backend Smoke Runbook

Kurz-Checkliste nach Setup, Deploy oder Konfigurationsänderungen.

## 1) Backend starten

Windows (PowerShell):

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

Linux/macOS:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Erwartung: Server startet ohne Traceback, Port 8000 ist gebunden.

## 2) Runtime-Status prüfen

```bash
curl http://localhost:8000/api/runtime/status
```

Erwartung:
- HTTP 200
- Felder vorhanden: `runtime`, `baseUrl`, `model`, `apiSupportedModels`

## 3) Agent-Liste prüfen

```bash
curl http://localhost:8000/api/agents
```

Erwartung:
- HTTP 200
- Enthält mindestens `head-agent` und `coder-agent`

## 4) WebSocket-Basisfluss prüfen

- Verbindung zu `ws://localhost:8000/ws/agent` herstellen
- Nachricht senden:

```json
{
  "type": "user_message",
  "content": "ping",
  "agent_id": "head-agent"
}
```

Erwartung:
- Initiales `status` Event
- Danach Lifecycle-Events bis `request_completed`
- Ein `final` Event mit Antworttext

## 5) Persistenz-Defaults prüfen

- In `development` sind standardmäßig aktiv:
  - `MEMORY_RESET_ON_STARTUP=true`
  - `ORCHESTRATOR_STATE_RESET_ON_STARTUP=true`
- In `production` sind sie standardmäßig deaktiviert (`false`), sofern nicht explizit gesetzt.

Schnellcheck:
- `APP_ENV=production` setzen
- Backend neu starten
- Sicherstellen, dass bestehende Dateien in `MEMORY_PERSIST_DIR` und `ORCHESTRATOR_STATE_DIR` nicht automatisch gelöscht werden.

## 6) Test-Sanity (optional, empfohlen)

```bash
pytest backend/tests -q
```

Erwartung: Alle Tests grün.

## 7) Recovery-Telemetrie-Quickcheck (empfohlen)

- Stelle sicher, dass Lifecycle-Events `model_recovery_summary` in Monitoring/Logs verfügbar sind.
- Pflichtfelder in `details` prüfen:
  - `attempts`, `max_attempts`, `failures_total`, `final_outcome`, `final_model`, `final_reason`
  - `reason_counts`, `branch_counts`, `strategy_counts`
  - `signal_priority_applied_vs_not_applied`, `strategy_feedback_applied_vs_not_applied`, `persistent_priority_applied_vs_not_applied`
  - `signal_priority_not_applied_breakdown`, `strategy_feedback_not_applied_breakdown`, `persistent_priority_not_applied_breakdown`

Vertiefung:
- Mapping: `monitoring/RECOVERY_TELEMETRY_MAPPING.md`
- Operatives Vorgehen: `RECOVERY_RUNBOOK.md`
