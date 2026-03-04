# Critical Bugs

Stand: 2026-03-04

## 1) Valides leeres Tool-JSON wird als Fehler behandelt
- **Severity:** Critical
- **Bereich:** Tool-Selection / Recovery
- **Datei:** `backend/app/agent.py`
- **Fundstelle:** `_extract_actions`

### Problem
Ein valider Parser-Output mit leerer Aktionliste (`{"actions":[]}`) wird aktuell als Parse-Fehler (`invalid_tool_json`) umdefiniert, sobald der Raw-Text nicht leer ist.

### Impact
- Erzwingt unnötige Repair-Calls.
- Erzeugt irreführende Error-Events (`tool_selection_parse_failed`).
- Kann zu falscher Steuerung führen, obwohl das Modell korrekt "keine Aktion" signalisiert.

### Reproduktion
1. Tool-Selector liefert `{"actions":[]}`.
2. Parser gibt `actions=[]` und `parse_error=None` zurück.
3. `_extract_actions` setzt dennoch `parse_error="invalid_tool_json"`.

### Root Cause
In `HeadAgent._extract_actions` wird `not actions` fälschlich wie ein Parse-Fehler behandelt, obwohl die API von `ActionParser` eine leere Liste explizit erlaubt.

### Fix (empfohlen)
- `invalid_tool_json` nur setzen, wenn wirklich JSON-Parsing scheitert.
- Leere Action-Liste ohne Error durchlassen.
- Optional: getrennte Lifecycle-Info `tool_selection_empty` statt Error.

---

## 2) Stale Failure-Retriever nach Feature-Disable möglich
- **Severity:** High
- **Bereich:** Long-Term-Memory / Planner
- **Datei:** `backend/app/agent.py`
- **Fundstelle:** `_refresh_long_term_memory_store`

### Problem
Bei `long_term_memory_enabled=false` oder leerem DB-Pfad werden interne Felder auf `None` gesetzt, aber `planner_agent._failure_retriever` nicht in allen Pfaden zurückgesetzt.

### Impact
- Planner kann veralteten Failure-Kontext verwenden, obwohl Feature deaktiviert ist.
- Inkonsistentes Laufzeitverhalten nach Feature-Toggles.

### Fix (empfohlen)
- In allen frühen `return`-Pfaden zusätzlich:
  - `if hasattr(self, "planner_agent"): self.planner_agent._failure_retriever = None`

---

## 3) Kalibrierungs-Empfehlung wird ohne passenden Strategy-Hit erzeugt
- **Severity:** High
- **Bereich:** Calibration / Runtime Tuning
- **Datei:** `backend/app/services/benchmark_calibration.py`
- **Fundstelle:** `_recommend_from_recovery_metrics`

### Problem
`MODEL_SCORE_RUNTIME_BONUS` wird immer empfohlen, auch wenn die beste Strategie **nicht** `fallback_retry` ist. Dann bleiben `current=1.0` und `recommended=1.0`, es wird aber trotzdem ein Recommendation-Objekt erzeugt.

### Impact
- Irreführende Empfehlungsliste.
- Potenziell unnötige/fehlerhafte `env_patch`-Ausgaben.

### Fix (empfohlen)
- Empfehlung nur erstellen, wenn tatsächlich ein Parameter-Delta oder ein qualifizierter Strategy-Match vorliegt.
- Sonst `[]` zurückgeben.

---

## Akzeptanzkriterien für den Fix
- `{"actions":[]}` führt **nicht** zu Parse-Error.
- Nach Deaktivierung von LTM ist `planner_agent._failure_retriever is None` garantiert.
- `MODEL_SCORE_RUNTIME_BONUS` wird nur empfohlen, wenn eine belastbare Recovery-Strategie mit relevantem Effekt vorliegt.
