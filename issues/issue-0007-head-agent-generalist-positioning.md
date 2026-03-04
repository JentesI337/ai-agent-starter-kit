# Issue 0007 — Head-Agent als Generalist erzwingen (kein Coding-Agent-Framing)

## Kontext
Der Head-Agent soll als Generalist/Orchestrator auftreten. Im Repo gibt es jedoch mehrere Artefakte, die weiterhin ein Coding-Framing transportieren oder implizit „Head = Coding“ nahelegen.

## Problem
Aktuell ist die Trennung zwar technisch vorhanden (`head-agent`, `coder-agent`, `review-agent`), aber an mehreren Stellen wird weiterhin Coding-zentrierte Sprache, Legacy-Namensgebung oder Testsemantik verwendet. Das erhöht das Risiko, dass der Head-Agent konzeptionell wieder als „Coder“ wahrgenommen oder konfiguriert wird.

## Gefundene Artefakte (priorisiert)

### P0 — Produkt-/Dokumentationstext mit explizitem Head-Coding-Framing
- `README.md` enthält explizit: „head coding agent foundation“.
  - Fundstelle: `README.md` (Abschnitt „Goal support“)

### P1 — Laufzeit-/UX-Texte mit Coding-Profil-Suggestion für Head-Flows
- Blocked-Message empfiehlt „switch to a coding-capable profile“ (kann Head-Agent-Kontext falsch framet).
  - Datei: `backend/app/services/tool_execution_manager.py`

### P1 — Legacy-Aliasse/Namen, die Head↔Coder historisch vermischen
- Alias `head-coder -> head-agent` in Routing.
  - Datei: `backend/app/main.py`
- Legacy-Klassenalias `HeadCodingAgent = HeadAgent`.
  - Datei: `backend/app/agent.py`
- Adapter-Export enthält `HeadCoderAgentAdapter` Alias.
  - Datei: `backend/app/agents/__init__.py`
  - Datei: `backend/app/agents/head_agent_adapter.py`

### P1 — Testnamen/Semantik, die Head-Coding-Delegation als Kernstory betonen
- Tests mit Namen wie `head_agent_routes_coding_intent_to_coder` und Assertions auf Delegationsmessage zu `coder-agent`.
  - Dateien:
    - `backend/tests/test_backend_e2e.py`
    - `backend/tests/test_ws_handler.py`

### P2 — Monitoring-Artefakte reproduzieren das alte Framing
- Benchmark/Event-Logs enthalten Delegations-Status „Head agent delegated this request to coder-agent“.
  - Pfad: `backend/monitoring/benchmarks/**`
- Golden Suite referenziert explizit Coding-Intent-Routing-Tests.
  - Datei: `backend/monitoring/eval_golden_suite.json`

## Gewünschtes Zielbild
- Head-Agent bleibt **Generalist/Orchestrator**.
- Coding-Aufgaben werden als capability-routing zu `coder-agent` behandelt, ohne Head als Coding-Agent zu labeln.
- Legacy-Begriffe (`head-coder`, `HeadCodingAgent*`) werden entweder entfernt oder klar als deprecated isoliert.

## Akzeptanzkriterien
1. Keine produktnahen Texte/Dokumentation framen den Head-Agent als Coding-Agent.
2. User-facing Fehlermeldungen nennen neutrale Optionen (z. B. „required tool permission“ oder „select specialist agent“) statt „coding-capable profile“.
3. Legacy-Aliasse sind entfernt oder hinter klar dokumentierter Deprecation-Grenze (mit Sunset-Datum).
4. Testnamen beschreiben Capability-Routing neutral (z. B. „routes code requests to coder-agent“) ohne Head-Coder-Konnotation.
5. Monitoring-/Eval-Referenzen sind aktualisiert oder bewusst als historische Artefakte markiert.

## Umsetzungsvorschlag (inkrementell)
1. **Docs/UX-Text bereinigen** (`README.md`, `tool_execution_manager.py`).
2. **Legacy-Aliasse abbauen** (`main.py`, `agent.py`, `head_agent_adapter.py`, Exporte).
3. **Tests umbenennen/neu formulieren** (gleiches Verhalten, neutralere Benennung).
4. **Benchmark-/Golden-Suite Referenzen aktualisieren**.
5. Optional: Guardrail-Test ergänzen, der verbietet, dass Head-Agent im Prompt/Status als Coding-Agent bezeichnet wird.

## Hinweis
Die technischen Capability-Mechanismen sind bereits weitgehend korrekt (Head als `general_reasoning/coordination`, Coder als `code_*` in `agent_resolution.py`). Das Ticket fokussiert auf verbleibende Framing-/Legacy-Artefakte.
