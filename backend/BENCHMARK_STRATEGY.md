# Backend Benchmark Strategy

Stand: 2026-03-01

## Ziel

Eine reproduzierbare, erweiterbare Benchmark-Pipeline für den echten Agent-Laufzeitpfad (WebSocket + Orchestrierung), nicht nur Smoke-Checks.

## Gewählte Strategie (v2)

Wir nutzen ein **szenariobasiertes WebSocket-Benchmarking** mit drei Schwierigkeitsstufen und zwei Bewertungsmodi:

- `easy`: deterministische Mini-Aufgabe (Antwortqualität + grundlegender Lifecycle)
- `mid`: strukturierte Planungsaufgabe (mehrstufiges Reasoning)
- `hard_reasoning` (gated): umfangreicher Research-Case ohne Shell/Tool-Seiteneffekte
- `hard_tools_diagnostic` (non-gated): tool-lastiger Diagnosefall zur Umgebungs-/Policy-Beobachtung

Zusätzlich ist ein dedizierter Orchestrierungs-Case enthalten:

- `mid_orchestration_subrun` (gated): validiert, dass der Head-Agent bei Research-Anfrage einen Subrun orchestriert.

Warum diese Option:

1. Deckt den produktionsnahen Pfad ab (`/ws/agent`), inkl. Event-Streaming.
2. Liefert detaillierte Rohdaten (JSONL-Events) und aggregierte Auswertung (JSON + Markdown).
3. Ist mit einer Datei erweiterbar (`benchmarks/scenarios/default.json`) ohne Codeänderung.
4. Trennt Qualitätssignal (gated) von Infrastruktur-/Policy-Rauschen (diagnostic).
5. Kann lokal und in CI/CD eingesetzt werden.

## Pipeline-Komponenten

- Runner: `backend/benchmarks/run_benchmark.py`
- Szenario-Datei: `backend/benchmarks/scenarios/default.json`
- Einstieg Windows: `start-benchmark.ps1`
- Einstieg Linux/macOS: `start-benchmark.sh`
- Artefakte: `backend/monitoring/benchmarks/<timestamp-uuid>/`

## Gemessene Signale

Pro Run:

- Pass/Fail + Fehlergrund
- Laufzeit (`duration_ms`)
- `first_event_ms`, `first_token_ms`, `final_received_ms`
- Event-Anzahl und Eventtypen
- beobachtete Lifecycle-Stages
- erforderliche Eventtypen/-status (z. B. `subrun_status: accepted/running/completed`)
- erforderliche Event-Feldwerte (z. B. `subrun_status.agent_id=head-agent`, `mode=run`)
- regex-basierte Qualitätskriterien (Pflicht-Sektionen, Formatmuster, Mindestanzahl strukturierter Punkte)
- Raw Event Stream (`*.events.jsonl`)

Aggregiert:

- Success-Rate gesamt (inkl. Diagnosefälle)
- Gated Success-Rate (nur gating-relevante Cases)
- Success-Rate pro Level (`easy`/`mid`/`hard`) inkl. gated-Sicht
- tabellarische Run-Details

## Pass/Fail-Definition v2

Ein Run gilt als erfolgreich, wenn mindestens erfüllt ist:

- `request_completed` wurde empfangen
- Mindestanzahl Events erreicht
- finale Antwort vorhanden und Mindestlänge erreicht
- geforderte Lifecycle-Stages vorhanden
- geforderte Substrings vorhanden
- geforderte Regex-Muster vorhanden (`required_regex_patterns`)
- Regex-Mindesttreffer erreicht (`regex_min_match_counts`)
- keine Error-Events/Exceptions

Zusätzlich gibt es pro Case ein Flag `gate`:

- `gate=true`: Case beeinflusst pass/fail des Benchmark-Exit-Codes.
- `gate=false`: Case ist diagnostisch und beeinflusst nur die Gesamtstatistik, nicht den Exit-Code.

Optional kann ein Case `allow_errors=true` setzen, wenn primär ein mechanischer Ablauf (z. B. Subrun-Orchestrierung) validiert werden soll und nicht-fatal auftretende Tool-/Web-Fehler den Case nicht sofort als fehlgeschlagen markieren sollen.

Über `completion_stages` kann ein Case alternative gültige Abschlusszustände definieren (z. B. diagnostisch: `request_completed` oder `request_failed_llm`).

## Erweiterbarkeit (v3+)

Nächste sinnvolle Ausbaustufen:

1. Mehrere Runs pro Case + Stabilitätskennzahlen (p50/p95-Latenz, Varianz).
2. Modellvergleich je Case (`small`, `mid`, `large`) in einem Lauf.
3. Replay-Mode gegen gespeicherte Event-Traces.
4. Optionales CI-Gating mit Schwellwerten pro Level.
5. Zusätzliche Qualitätsmetriken (z. B. Struktur-Checks, Schema-Checks).
