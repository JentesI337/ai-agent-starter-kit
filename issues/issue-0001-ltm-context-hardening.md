# LTM Context Hardening & Relevance-Driven Injection

## Meta
- ID: issue-0001
- Status: open
- Priorität: high
- Owner: unassigned
- Erstellt: 2026-03-04
- Zuletzt aktualisiert: 2026-03-04

## Kontext
Im aktuellen Plan für die Memory-Integration (Block 7d in `backend/INTELLIGENCE_LAYER_REFACTORING_PLAN.md`) wird `ltm_context` aus ähnlichen Failures und semantischen Facts aufgebaut und in den `ContextReducer` injiziert.

Dabei bestehen folgende Risiken:
1. **Prompt-Budget-Risiko**: Kontextmenge ist nicht global hart gedeckelt (nur per Feld-Substring wie `[:100]`).
2. **Relevanz-Risiko**: Semantische Fakten werden global über `get_all_semantic()` geladen statt query-bezogen.
3. **Injection/Formatting-Risiko**: Unbereinigte Inhalte (Steuerzeichen, Delimiter, Markdown-Strukturen) können Prompt-Struktur stören.
4. **Priorisierungs-Risiko**: Kein expliziter Vorrang für Fehler-Learnings vor allgemeinen Präferenzen.
5. **Blindes Tuning**: Fehlende Metriken zur Wirksamkeit und Kosten des injizierten LTM-Kontexts.

Ziel ist eine robuste, budgetierte und nachvollziehbare LTM-Kontext-Injektion mit klarer Priorisierung und Observability.

## Anforderungen (Scope)
- Kontext hart begrenzen, z. B. via `max_chars` und/oder `max_lines` für den finalen `ltm_context`.
- Relevanz statt globaler Faktenabfrage: `get_all_semantic()` durch `search_semantic(user_message, limit=...)` ersetzen.
- Sanitizing von Memory-Inhalten (Steuerzeichen/Delimiter normalisieren), bevor sie in Prompts landen.
- Priorisierung: zuerst ähnliche Failures, danach Top-N semantische Facts mit Confidence-Schwelle.
- Observability: Lifecycle-Metriken ergänzen (`ltm_items_used`, `ltm_chars`) für Tuning.

## Akzeptanzkriterien
- [ ] `ltm_context` wird durch harte Limits begrenzt (konfigurierbar oder klar dokumentierte Defaults).
- [ ] Semantische Facts werden query-basiert via `search_semantic(...)` geladen; kein ungebremstes `get_all_semantic()` im Planing-Path.
- [ ] Alle injizierten Memory-Strings werden vor Nutzung sanitiziert (inkl. Entfernung/Normalisierung von Steuerzeichen und problematischen Delimitern).
- [ ] Kontextaufbau priorisiert Failures vor semantischen Facts; semantische Facts respektieren `confidence >= threshold` und `top_n`.
- [ ] Lifecycle/Telemetry enthält mind. `ltm_items_used` und `ltm_chars` pro Request.
- [ ] Bestehende Tests bleiben grün; neue Tests decken Budgetierung, Relevanz, Sanitizing und Priorisierung ab.

## Umsetzung
1. **API/Store-Erweiterung (Long-Term Memory)**
   - Methode ergänzen: `search_semantic(query: str, limit: int, min_confidence: float) -> list[SemanticEntry]`.
   - Ranking heuristisch (z. B. token overlap/FTS falls verfügbar) und deterministisch bei Score-Gleichstand.

2. **Sanitizing Utility einführen**
   - Neue Helper-Funktion(en), z. B. in `agent.py` oder separatem Modul:
     - Steuerzeichen entfernen/ersetzen (`\x00`–`\x1f`, `\x7f`),
     - Markdown-Block-Delimiter/Prompt-Delimiter entschärfen (z. B. ``` , XML-artige Delimiter),
     - Whitespace normalisieren, Zeilen kürzen.

3. **Hard-Limits im Kontextaufbau**
   - Limits beim Rendern von `ltm_context`:
     - `max_failure_items`,
     - `max_semantic_items`,
     - `max_lines_total`,
     - `max_chars_total`.
   - Truncation explizit und nachvollziehbar anwenden (ggf. mit `…`).

4. **Priorisierte Reihenfolge + Confidence-Gate**
   - Reihenfolge: `[Past failures]` zuerst, `[Known user preferences]` danach.
   - Semantics nur wenn `entry.confidence >= min_confidence`.

5. **Observability/Lifecycle erweitern**
   - Lifecycle-Details ergänzen, z. B. im Planning-Abschnitt:
     - `ltm_items_used` (gesamt und optional pro Kategorie),
     - `ltm_chars` (nach Sanitizing/Truncation),
     - optional: `ltm_failures_used`, `ltm_semantic_used`.

6. **Config ergänzen**
   - Neue Settings (Vorschlag):
     - `LTM_CONTEXT_MAX_CHARS` (Default z. B. 1200)
     - `LTM_CONTEXT_MAX_LINES` (Default z. B. 40)
     - `LTM_FAILURE_LIMIT` (Default 2)
     - `LTM_SEMANTIC_LIMIT` (Default 5)
     - `LTM_SEMANTIC_MIN_CONFIDENCE` (Default 0.6)

## Verifikation
- Unit-Tests:
  - Sanitizer entfernt Steuerzeichen/gefährliche Delimiter und bleibt idempotent.
  - Hard-Limits werden strikt eingehalten (`max_chars`, `max_lines`).
  - Priorisierung korrekt (Failures vor Semantics).
  - Confidence-Filter greift für Semantics.
  - Relevanzabfrage `search_semantic()` liefert erwartete Top-N.

- Integration-Tests:
  - `agent.py` injiziert bei vorhandener LTM nur budgetierten, sanitizten Kontext.
  - Lifecycle-Events enthalten `ltm_items_used` und `ltm_chars`.

- Regression:
  - Relevante bestehende Backend-Tests (`backend/tests`) bleiben grün.

## Risiken & Entscheidungen
- Zu aggressive Sanitization kann nützliche Struktur entfernen → konservative Normalisierung bevorzugen.
- Zu niedrige Limits können Nutzen reduzieren → über Metriken iterativ tunen.
- `search_semantic`-Relevanz ohne Embeddings bleibt heuristisch → ausreichend für Phase 1, später kombinierbar mit Embedding-Ranking.

## Out of Scope
- Vollständige semantische Re-Ranking-Pipeline mit Embeddings (Block 8).
- Änderungen am Frontend.
- Umfassende Refaktorierung außerhalb des LTM-Kontextaufbaus.

## Betroffene Dateien (voraussichtlich)
- `backend/app/agent.py`
- `backend/app/services/long_term_memory.py` (oder äquivalentes Memory-Modul)
- `backend/app/config.py`
- `backend/tests/...` (neue/angepasste Unit- und Integration-Tests)

## Notizen
- Diese Issue konkretisiert die Hardening- und Qualitätsanforderungen aus Block 7d (Memory-Context Injection) des Refactoring-Plans.
- Bei Umsetzung sollte auf minimale, rückwärtskompatible Änderung der bestehenden Pipeline geachtet werden (Feature-Flags respektieren).