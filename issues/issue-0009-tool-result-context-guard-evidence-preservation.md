# Issue-0009 — Tool-Result Context Guard kann Orchestrierungs-Evidenz wegkürzen (silent semantic fail)

**Stand:** 2026-03-04  
**Status:** Open  
**Schweregrad:** Hoch (Korrektheit)  
**Betroffene Bereiche:** `backend/app/services/tool_result_context_guard.py`, `backend/app/agent.py`, Orchestration-Evidence-Gates

---

## Kurzbeschreibung

Der neue Hard-Budget-Cap im Tool-Result-Context-Guard hält das Zeichenbudget korrekt ein, kann aber bei kleinem Budget kritische Evidenzmarker (z. B. `spawned_subrun_id=...`, `terminal_reason=subrun-complete`) vollständig entfernen.

Dadurch können nachgelagerte Gates in `agent.py` fehlende Evidenz diagnostizieren, obwohl die Evidenz im ursprünglichen Tool-Output vorhanden war.

---

## Beobachteter Befund

### 1) Guard läuft vor Task-Type-Resolution und Evidence-Gates

In `backend/app/agent.py` wird `enforce_tool_result_context_budget(...)` vor

- `_resolve_synthesis_task_type(...)`
- `_has_orchestration_evidence(...)`

aufgerufen. Damit arbeiten diese Entscheidungen auf den **bereits gekürzten** Tool-Results.

### 2) Extrem kleine Budgets schneiden Marker komplett ab

Bei sehr kleinen Context-Budgets (z. B. in Extrem-/Fehlkonfigurationen) bleibt teils nur ein abgeschnittener Prefix des Truncation-Hinweises (`"\n\n[tr..."`) übrig.

In einem Probe-Run war bei `context_window_tokens in {50,80,120,200}` jeweils:

- `spawned_subrun_id=` **nicht mehr enthalten**
- `subrun-complete` **nicht mehr enthalten**
- `reason=context_budget`

### 3) Tests können „grün“ sein, obwohl Semantik kippt

Aktuelle Guard-Tests prüfen primär Budget-/Längeninvarianten und Modifikation, aber nicht systematisch die Erhaltung semantischer Marker unter harten Truncation-Fällen.

---

## Risiko / Impact

- **False negative bei Orchestration-Evidence**: erfolgreicher Subrun wird als „nicht belegt“ gewertet.
- **Falsche User-Nachricht**: Gate kann auf „delegation not completed“ umschwenken, obwohl Child-Run erfolgreich war.
- **Silent fail**: keine Exception, kein offensichtlicher Testfehler in Standardpfaden; fachlicher Fehler erst im Ergebnis sichtbar.

---

## Reproduktion (Kurzform)

1. Tool-Result enthält echte Orchestrierungsmarker:
   - `spawned_subrun_id=run-1`
   - `terminal_reason=subrun-complete`
2. Guard mit sehr kleinem effektiven Budget anwenden (kleine `context_window_tokens`, geringe Headroom/Share).
3. Prüfen, ob Marker im `guarded_tool_results` noch vorkommen.
4. `_has_orchestration_evidence(...)` auf dem gekürzten String liefert `False`.

---

## Erwartetes Verhalten

Der Guard darf budgetieren, muss aber kritische Evidenzmarker für nachgelagerte Korrektheits-Gates robust erhalten (oder separat transportieren), damit fachliche Entscheidungen nicht durch Truncation verfälscht werden.

---

## Konkrete Lösungsvorschläge

### Option A (bevorzugt): Evidence Preservation im Guard

Im Guard vor finaler Truncation kritische Marker extrahieren und als reservierten Block voranstellen, z. B.:

- `spawned_subrun_id=...`
- `terminal_reason=...`
- ggf. `subrun_announce`-Zeilen

Wenn Budget sehr knapp ist, zuerst Markerblock behalten, danach Rest kürzen.

### Option B: Entscheidungen auf ungekürzter Evidenz

Task-Type-Resolution und Evidence-Gates auf einer ungekürzten/side-channel Evidenzbasis treffen (z. B. separater strukturierter Evidence-Snapshot), während Synthesis weiter mit gekürztem Text arbeitet.

### Option C: Telemetrie-Härtung

Lifecycle-Event um Marker-Verlustindikator erweitern, z. B.:

- `evidence_markers_present_before`
- `evidence_markers_present_after`
- `evidence_markers_dropped`

---

## Akzeptanzkriterien

1. Bei Truncation bleibt Orchestrierungs-Evidenz für Gate-Entscheidungen erhalten.
2. `_has_orchestration_evidence(...)` liefert bei ursprünglich vorhandenem `subrun-complete` kein False-Negative wegen Guard-Truncation.
3. Neue Regressionstests decken Extrembudgets ab (inkl. Marker-Erhalt).
4. Guard hält weiterhin Hard-Budget (`len(output) <= max_input_chars`).

---

## Testvorschläge

- `test_tool_result_context_guard_preserves_orchestration_evidence_markers_under_hard_truncation`
- `test_orchestration_evidence_gate_uses_preserved_markers_after_guard`
- `test_tool_result_context_guard_still_enforces_hard_budget_with_preserved_markers`

---

## Hinweis

Der Hard-Cap-Fix an sich ist korrekt (Budgettreue). Das Issue betrifft die **Semantik-Sicherheit** bei starker Kürzung, nicht die reine Budget-Implementierung.