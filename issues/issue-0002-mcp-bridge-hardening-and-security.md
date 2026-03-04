# MCP Bridge Hardening: Transport-Compliance, Security Isolation, Config-Observability, Lifecycle Cleanup

## Meta
- ID: issue-0002
- Status: open
- Priorität: critical
- Owner: unassigned
- Erstellt: 2026-03-04
- Zuletzt aktualisiert: 2026-03-04

## Kontext
Die initiale MCP-Bridge-Integration ist funktional, hat aber 5 relevante Risiken in Sicherheit, Protokoll-Kompatibilität und Betriebsstabilität:

1. **Kritisch – SSE-Transport nicht protokollkonform**
   - Aktuell verwenden `sse` und `streamable-http` denselben POST-JSON-RPC-Pfad.
   - Folge: reale SSE-basierte MCP-Server sind häufig inkompatibel.

2. **Kritisch – Read-only-Schutz umgehbar über dynamische MCP-Tools**
   - Review-Policy deny-listet statische Tools, aber nicht pauschal `mcp_*`.
   - Folge: Review-Agent kann potentiell write/execute-nahe MCP-Tools nutzen.

3. **Mittel – MCP-Konfigurationsfehler werden verschluckt**
   - Fehler beim Parsen/Laden führen still zu `[]` statt diagnostizierbarem Signal.
   - Folge: Fehlkonfiguration bleibt unsichtbar, Debugging wird erschwert.

4. **Mittel – Ressourcen-Lifecycle unvollständig**
   - `McpBridge.close()` existiert, wird aber nicht zuverlässig im Shutdown aufgerufen.
   - Folge: Subprocess-/HTTP-Ressourcen können hängenbleiben.

5. **Mittel – Re-Initialize-Leak-Risiko**
   - `initialize()` leert Tool-Metadaten, räumt aber bestehende Verbindungen nicht deterministisch auf.
   - Folge: alte Verbindungen bleiben offen bei Re-Init/Reconfigure.

## Zielbild (SOLL)
Eine MCP-Bridge, die:
- Transport-semantisch korrekt zwischen `stdio`, `sse`, `streamable-http` trennt,
- dynamische MCP-Tools sicher in bestehende Tool-Policy-Modelle integriert,
- Konfigurationsfehler sichtbar und auditierbar macht,
- Verbindungen deterministisch über Run/Shutdown-Lifecycle aufräumt,
- Re-Initialize ohne Ressourcen-Leaks unterstützt.

## Architektur-Entscheidungen

### A) Transport-Verantwortung explizit trennen
- `StdioMcpConnection`: JSON-RPC via stdio (bestehend, beibehalten).
- `SseMcpConnection`: echtes SSE-Handshake/Read-Loop + request channel gemäß MCP-SSE-Konvention.
- `StreamableHttpMcpConnection`: HTTP Streaming/Chunked-Antworten getrennt von SSE behandeln.

**Entscheidung:** Keine gemeinsame „einfach POST JSON“ Fallback-Logik für `sse` und `streamable-http`.

### B) Security-by-default für dynamische Tools
- Neue dynamische Tool-Klasse `mcp_*` wird in restriktiven Agent-Policies standardmäßig als **nicht erlaubt** behandelt.
- Review-Agent blockt `mcp_*` pauschal, es sei denn explizit freigeschaltet.

**Entscheidung:** Deny-by-default für dynamische Quellen in read-only/review-Kontexten.

### C) Konfigurationsfehler transparent machen
- Parse-/Load-Fehler nicht still verschlucken.
- Stattdessen:
  - strukturierte Warnung mit Ursache,
  - Lifecycle-/Startup-Event,
  - optional strict mode (`MCP_CONFIG_STRICT=true`) → Start/Init fail-fast.

**Entscheidung:** Sichtbarkeit vor stiller Deaktivierung.

### D) Deterministischer Connection Lifecycle
- Bridge-Initialisierung ist idempotent.
- Vor Re-Init: bestehende Connections sauber schließen.
- Beim App-/Agent-Shutdown: `close()` garantiert aufrufen.

**Entscheidung:** „Open once, close always“ als Invariante.

## Umsetzung

### Workstream 1: Transport-Compliance (kritisch)
1. `SseMcpConnection` als echten SSE-Client implementieren:
   - Session-Initialisierung (SSE endpoint + optional message endpoint),
   - Event-Parsing (`event:`, `data:`),
   - Korrelierte RPC-Responses über request-id.
2. `StreamableHttpMcpConnection` getrennt implementieren:
   - Streaming-Antworten (chunked/text stream) lesen,
   - Response-Framing robust parsen.
3. Fehlerklassifikation verbessern:
   - transport-specific exceptions (`McpTransportError`, `McpProtocolError`, `McpTimeoutError`).

### Workstream 2: Read-only-Härtung für dynamische MCP-Tools (kritisch)
1. Policy-Layer erweitern um dynamische Tool-Kategorien (`dynamic_tool`, `mcp_tool`).
2. Review-Agent-Policy:
   - Standardmäßig deny auf `mcp_*` oder Capability `mcp_tool`.
3. Optionales granulareres Allowlisting:
   - `MCP_ALLOWED_TOOL_PREFIXES`,
   - `MCP_ALLOWED_SERVERS`.
4. Security-Tests ergänzen:
   - Nachweis, dass `review-agent` MCP-Tools nicht ausführen kann.

### Workstream 3: Config-Observability & Strictness (mittel)
1. `settings.mcp_servers` Fehlerpfad verbessern:
   - Fehlerobjekt/diagnostics erzeugen (Datei, Ursache, Typ).
2. Startup-/Lifecycle-Ereignis ergänzen:
   - `mcp_config_loaded`, `mcp_config_invalid`.
3. Strict-Flag einführen:
   - `MCP_CONFIG_STRICT` (default `false`).
   - Bei `true`: invalid config → fail-fast.
4. Unit-Tests:
   - invalid JSON,
   - nicht vorhandene Datei,
   - ungültige Einträge pro Server.

### Workstream 4: Lifecycle Cleanup (mittel)
1. Agent-/App-Shutdown-Pfad erweitern:
   - `await mcp_bridge.close()` sicher ausführen.
2. Reconfigure/Runtime-Switch prüfen:
   - alte Verbindungen schließen, neue initialisieren.
3. Defensive Guards:
   - mehrfaches `close()` ohne Fehler,
   - cleanup bei init-failure (partial open).

### Workstream 5: Re-Initialize Leak Prevention (mittel)
1. `McpBridge.initialize()` refactor:
   - Schritt 1: neue Verbindungen lokal aufbauen,
   - Schritt 2: bei Erfolg atomar swap,
   - Schritt 3: alte Verbindungen schließen.
2. Fehlerfall:
   - bei Teilfehlern neu eröffnete Partial-Verbindungen schließen,
   - bestehender stabiler Zustand erhalten.
3. Tests:
   - mehrfaches initialize ohne resource growth,
   - partial connect failure → no leaked processes/sockets.

## Akzeptanzkriterien
- [ ] `sse` und `streamable-http` nutzen nicht denselben POST-only Codepfad.
- [ ] Gegen einen echten SSE-MCP-Server ist `initialize -> tools/list -> tools/call` lauffähig.
- [ ] Review-Agent kann ohne explizite Freigabe keine `mcp_*` Tools ausführen.
- [ ] MCP-Config-Fehler sind sichtbar (Events/Logs) und in strict mode fail-fast.
- [ ] Bei App-/Agent-Shutdown werden alle MCP-Verbindungen deterministisch geschlossen.
- [ ] Re-Initialize führt nicht zu offenen Alt-Verbindungen/Prozessen.
- [ ] Bestehende Tests bleiben grün; neue MCP-Hardening-Tests sind grün.

## Verifikation

### Unit
- `test_mcp_sse_transport.py`
  - SSE framing parsing,
  - request/response correlation,
  - timeout handling.
- `test_mcp_streamable_http_transport.py`
  - streaming payload parsing,
  - protocol errors.
- `test_mcp_config_diagnostics.py`
  - invalid JSON/path/schema,
  - strict vs non-strict behavior.
- `test_mcp_bridge_reinitialize.py`
  - no leak on repeated init,
  - rollback on partial failure.

### Integration
- `test_mcp_review_policy_block.py`
  - review-agent deny-by-default für dynamic/mcp tools.
- `test_mcp_shutdown_cleanup.py`
  - close wird im lifecycle/shutdown aufgerufen.

### E2E
- `test_mcp_e2e.py`
  - echter MCP filesystem server (wenn verfügbar),
  - `tools/list` und ein read-only Tool-Call.

## Rollout
1. **Phase A (Shadow):**
   - neue Diagnostik + Events aktiv,
   - strict mode aus.
2. **Phase B (Canary):**
   - transport path split aktiv für ausgewählte MCP-Server.
3. **Phase C (Default):**
   - deny-by-default für `mcp_*` in review profiles,
   - optional strict config in produktiven Environments.

## Risiken & Gegenmaßnahmen
- **Risiko:** SSE-Implementierung variiert je Server.
  - **Mitigation:** adapterfähige Transport-Layer, server-specific integration tests.
- **Risiko:** bestehende Workflows verlassen sich auf dynamische MCP-Tools im Review-Agent.
  - **Mitigation:** explizites Allowlist-Override + klare Breaking-Change-Note.
- **Risiko:** strict mode kann Deploys blockieren.
  - **Mitigation:** stufenweise Aktivierung, zunächst nur Warnungen.

## Out of Scope
- Vollständiger MCP Capability-Support jenseits Tools (Resources/Prompts/Sampling).
- Frontend-UI für MCP-Konfigurationsverwaltung.
- Multi-tenant Credential Management für MCP-Server.

## Betroffene Dateien (voraussichtlich)
- `backend/app/services/mcp_bridge.py`
- `backend/app/agent.py`
- `backend/app/agents/head_agent_adapter.py`
- `backend/app/config.py`
- `backend/app/main.py` oder Startup/Shutdown-Wiring
- `backend/tests/test_mcp_*.py`

## Notizen
- Diese Issue konsolidiert die Hardening-Punkte aus der Block-9-Implementierung und priorisiert Sicherheits- und Betriebsstabilität vor Feature-Erweiterungen.
- Ziel ist nicht nur „funktioniert lokal“, sondern „protokollkonform, sicher, wartbar in Produktion“.
