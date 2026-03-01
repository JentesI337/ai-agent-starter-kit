# OpenClaw-Übernahmen für unser Agentensystem

## Ziel
Dieses Dokument beschreibt, welche bewährten Orchestrierungs- und Agent-Management-Muster aus OpenClaw wir sinnvoll in unseren Stack übernehmen sollten.

Der Fokus liegt auf:
- operativer Stabilität unter Last,
- sauberer Delegation (Subruns/Subagents),
- sicherer Tool- und Session-Governance,
- robuster API/WS-Semantik für produktive Clients.

---

## Kurzfazit
Wir haben bereits eine starke Basis (deterministische Pipeline, Tool-Policy deny-wins, Subrun-Spawn, Announce-Back).

Der größte Hebel liegt jetzt in fünf Bereichen:
1. Session-Lanes (pro Session serialisieren)
2. Wait-Semantik (Run-Ausführung von Wait entkoppeln)
3. Subrun-Management-API (spawn/list/info/log/kill)
4. Depth-aware Delegation-Policy (Orchestrator vs Worker)
5. Announce-Reliability (idempotent + retry/backoff)

Mittelfristig liefern vier zusätzliche Muster viel Wert:
- Hook-Punkte,
- Result-Persist-Transform,
- Reply-Shaping-Regeln,
- Session-Visibility-Scope.

---

## Ist-Stand bei uns (Stand heute)

### Bereits vorhanden
- Deterministische Pipeline Plan -> Tool Select/Execute -> Synthesize
- Model Routing mit Fallback
- Tool Policy Layer (allow/deny, deny-wins) inklusive Frontend-Steuerung
- Asynchroner Subrun-Spawn mit Status-Events und Announce-Back
- Persistenter Run-State inkl. Task-Graph/Snapshots

### Noch offen
- Keine echte Session-Lane-Serialisierung (Race-Risiko bei parallelen Requests auf gleicher Session)
- Kein standardisiertes Wait-API (status ok/error/timeout für bereits laufende Runs)
- Subrun-Operations fehlen (list/info/log/kill)
- Delegations-Tiefe nicht hart modelliert (Depth 1 Orchestrator, Depth 2 Worker)
- Announce aktuell best-effort ohne idempotente Zustellung + Retry-Strategie

---

## Top-Übernahmen (jetzt priorisieren)

## 1) Session-Lanes statt nur globaler Parallelität

### Warum
OpenClaw serialisiert pro Session (und optional global). Das verhindert Inkonsistenzen bei:
- Tool-Execution,
- Memory/Persistenz,
- Verlauf/Lifecycle-Reihenfolge.

### Was wir übernehmen
- Session-Key-basierte Lane: pro session_id gleichzeitig nur ein aktiver Run
- Optionaler globaler Concurrency-Cap als zusätzlicher Schutz
- Queue-Mode pro Session (später): collect/steer/followup-ähnliche Modi

### Konkrete Umsetzung bei uns
- Neue Komponente: SessionLaneManager
- Enqueue in Request-Ingress (REST + WS user_message + subrun relay)
- Laufender Run pro Session erhält Lock; weitere Runs warten
- Lifecycle-Stages ergänzen: queued, dequeued, lane_acquired, lane_released

### Acceptance Criteria
- Zwei gleichzeitige Nachrichten auf derselben Session laufen deterministisch nacheinander
- Tool- und Final-Events bleiben in der richtigen Reihenfolge
- Keine doppelte/überlappende Memory-Schreibkonkurrenz pro Session

---

## 2) Saubere Wait-Semantik für Runs

### Warum
OpenClaw trennt klar:
- Run wird gestartet und läuft weiter,
- Client wartet optional nur X Sekunden.

Das ist robust bei Reconnects, mobilen Clients und langen Tasks.

### Was wir übernehmen
- Start-API liefert sofort accepted + run_id
- Wait-API blockiert optional bis terminal status oder timeout
- Timeout betrifft den Wait-Aufruf, nicht automatisch die Run-Ausführung

### Konkrete Umsetzung bei uns
- REST:
  - POST /api/runs/start -> { runId, acceptedAt }
  - GET /api/runs/{runId}/wait?timeoutMs=... -> { status: ok|error|timeout, startedAt, endedAt, error? }
- WS:
  - run_started sofort
  - run_status terminal separat

### Acceptance Criteria
- Verbindungsabbruch während Wait beendet den Run nicht
- Neuer Client kann später via wait/status denselben Run verfolgen
- Einheitliche terminal statuses: completed, failed, timed_out, aborted

---

## 3) Subrun-Management-API

### Warum
Spawn allein reicht operativ nicht. OpenClaw bietet list/info/log/kill für echte Steuerbarkeit.

### Was wir übernehmen
- list: aktive + letzte Subruns je Parent/Session
- info: Metadaten, Dauer, Ergebnisstatus, Child-Session
- log: Lifecycle/Tool-Auszüge
- kill: einzelner Run oder alle Runs eines Parents

### Konkrete Umsetzung bei uns
- REST-Endpunkte:
  - GET /api/subruns?parentRequestId=...
  - GET /api/subruns/{runId}
  - GET /api/subruns/{runId}/log?limit=...
  - POST /api/subruns/{runId}/kill
  - POST /api/subruns/kill-all?parentRequestId=...
- WS-Commands optional nachziehen

### Acceptance Criteria
- Jeder Spawn ist später eindeutig auffindbar
- Kill setzt Run in terminal aborted und emittiert Event
- Logs enthalten mindestens lifecycle + error + summary

---

## 4) Depth-aware Delegation-Policy

### Warum
OpenClaw trennt klar:
- Depth 1 kann orchestrieren,
- Depth 2 ist Worker-only,
- begrenzte Fan-out-Kontrolle.

Das verhindert Delegations-Explosion und Tool-Missbrauch.

### Was wir übernehmen
- Depth im Run-Kontext
- maxSpawnDepth (default 1 oder 2)
- maxChildrenPerParent
- Depth-basierte Tool-Sets

### Konkrete Umsetzung bei uns
- RunContext erweitern um:
  - depth,
  - parent_run_id,
  - root_run_id
- Policy:
  - Depth 0/1: sessions_spawn erlaubt (konfigurierbar)
  - Depth >= 2: sessions_spawn denied
- Cascade Stop:
  - stop parent -> stop alle children rekursiv

### Acceptance Criteria
- Depth-Überschreitung wird früh und nachvollziehbar geblockt
- Parent-Kill stoppt Kinder zuverlässig
- Keine unkontrollierte rekursive Spawn-Kette

---

## 5) Announce-Reliability (idempotent + retry/backoff)

### Warum
Aktuell best-effort ist gut, aber nicht ausreichend für Produktionsflüsse.
OpenClaw setzt auf robustere Zustellungspfade.

### Was wir übernehmen
- Idempotency-Key pro Announce
- Retry-Policy mit Exponential Backoff und Obergrenze
- Zustellstatus persistieren

### Konkrete Umsetzung bei uns
- AnnounceStore:
  - key,
  - attempts,
  - next_retry_at,
  - status: pending|sent|failed|dead_letter
- Worker/Timer für Retries
- Duplicate-Guard über idempotency key

### Acceptance Criteria
- Doppelte Zustellung bei Retries wird verhindert
- Temporäre Zustellfehler werden automatisch erneut versucht
- Dead-letter Fälle sind operativ sichtbar

---

## Sehr wertvoll (mittelfristig)

## 6) Hook-Punkte vor/nach Tool-Call und vor Prompt-Build

### Nutzen
- Policy-Enforcement ohne Core-Umbau
- Audit/Telemetry
- dynamisches Sanitizing/Redaction

### Vorschlag
- before_prompt_build(context)
- before_tool_call(tool, args, context)
- after_tool_call(tool, result, context)
- agent_end(run_summary)

---

## 7) Result-Persist-Transform

### Nutzen
Tool-Ergebnisse zentral vor Persistenz kürzen/redigieren:
- Secrets entfernen,
- Binär-/Riesenpayloads clampen,
- einheitliche Log-Qualität.

### Vorschlag
- Persist-Pipeline: raw -> transform -> store
- Regeln konfigurierbar pro Tool-Klasse

---

## 8) Reply-Shaping-Regeln

### Nutzen
Interne Turns (z. B. Steuernachrichten) nicht an User durchreichen.

### Vorschlag
- reservierte Tokens:
  - NO_REPLY
  - ANNOUNCE_SKIP
- final shaping:
  - Tool-Confirmations deduplizieren
  - leere/irrelevante Antworten unterdrücken

---

## 9) Session-Visibility-Scope für session-nahe Tools

### Nutzen
Saubere Begrenzung von Cross-Session-Zugriffen.

### Scope-Modell
- self: nur aktuelle Session
- tree: aktuelle Session + eigene Child-Sessions
- agent: alle Sessions derselben Agent-ID
- all: global (nur für vertrauenswürdige Profile)

### Default-Empfehlung
- Standard: tree
- für sandboxed/untrusted strikt auf tree oder self klemmen

---

## Ergänzende Erkenntnisse aus OpenClaw-Patterns

### A) Event-Contract als Produkt-API behandeln
OpenClaw nutzt klare Streams (lifecycle, assistant, tool). Für uns heißt das:
- Eventschema versionieren
- terminal states strikt standardisieren
- clientseitig keine impliziten Heuristiken nötig

### B) Queue + Timeout klar trennen
- Queue/Run-Timeout ist Runtime-Thema
- Wait-Timeout ist Client-Thema

### C) Governance first, then features
Neue Agent-Features immer mit:
- Sichtbarkeits-Scope,
- Tool-Policy,
- Audit-Trail,
- Kill/Cleanup-Semantik.

### D) Operative Diagnose früh bauen
Unverzichtbar:
- run list/filter,
- stage timeline,
- retry counters,
- dead-letter view.

---

## Priorisierte Roadmap (empfohlen)

## Phase 1 (kurz, hoher Hebel)
1. Session-Lane-Manager
2. Start/Wait-Semantik
3. Subrun list/info/log/kill

## Phase 2
4. Depth-aware Delegation + max children + cascade stop
5. Announce idempotency + retry/backoff

## Phase 3
6. Hooks
7. Persist transform
8. Reply shaping
9. Session visibility scopes

---

## Risiken und Gegenmaßnahmen

- Risiko: Mehr Komplexität in Run-State
  - Maßnahme: einheitliches RunContext-Schema + zentrale Zustandsmaschine

- Risiko: Event-Breaking-Changes im Frontend
  - Maßnahme: Event-Versionierung + Rückwärtskompatible Felder

- Risiko: Retry-Stürme bei Announce
  - Maßnahme: Exponential Backoff, max attempts, jitter, dead-letter

- Risiko: Depth-Policy blockiert legitime Flows
  - Maßnahme: feature flags + per-agent overrides

---

## Konfigurationsvorschlag (Zielbild)

```json
{
  "orchestration": {
    "sessionLanes": {
      "enabled": true,
      "globalMaxConcurrent": 8
    },
    "wait": {
      "defaultTimeoutMs": 30000
    },
    "subruns": {
      "maxConcurrent": 4,
      "maxSpawnDepth": 2,
      "maxChildrenPerParent": 5,
      "defaultTimeoutSeconds": 900,
      "announce": {
        "retry": {
          "enabled": true,
          "maxAttempts": 5,
          "baseDelayMs": 500,
          "maxDelayMs": 10000,
          "jitter": true
        }
      }
    },
    "sessions": {
      "visibility": "tree"
    }
  }
}
```

---

## Nächster sinnvoller Implementierungsschritt
Empfehlung: Phase 1 vollständig umsetzen (Session-Lanes + Wait + Subrun-Management), da diese drei Punkte sofort Stabilität, Operabilität und UX verbessern, ohne tiefe Prompt- oder Modelländerungen zu erzwingen.
