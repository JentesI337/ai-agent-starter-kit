# Sprint 2 — AgentRunner Refactoring: Guards, Safety & Reflection

> **Zeitraum:** 24.03.2026 – 06.04.2026 (2 Wochen)  
> **Ziel:** Phase C (Guards & Safety migrieren) vollständig implementiert. Evidence Gates, Reply Shaping, Reflection und Verification in den AgentRunner integriert. Optional: Frontend-Event-Handling (Phase D Teilschritt).  
> **Basis-Dokument:** `AgentRunnerRefactoring.md` (Abschnitte 9–11)  
> **Voraussetzung:** Sprint 1 abgeschlossen (Phase A + B + Feature-Flag Router)  
> **Kapazität:** ~60 Story Points (1 SP ≈ halber Tag fokussierte Arbeit)

---

## Sprint-Strategie

Sprint 1 hat das **Grundgerüst** (Phase A) und den **Streaming Tool Loop** (Phase B) geliefert — inklusive Feature-Flag Router in `HeadAgent.run()`. Allerdings sind die **Safety-kritischen Post-Loop-Schritte** noch Stubs:

- `_apply_evidence_gates()` → gibt `final_text` unverändert zurück
- `_shape_final_response()` → gibt `final_text` unverändert zurück
- Reflection → Constructor akzeptiert `reflection_service`, aber es wird nie aufgerufen
- Verification → nicht im Constructor, wird nicht genutzt

**Ohne diese Schritte ist der AgentRunner nicht produktionsreif**, weil:
1. Halluzinierte Erfolgsantworten nicht abgefangen werden (Evidence Gates)
2. Tool-Marker und Duplikate im Output verbleiben (Reply Shaping)
3. Qualitätsprüfung fehlt (Reflection + Verification)

Dieser Sprint migriert die gesamte Post-Loop-Logik aus `HeadAgent._run_legacy()` (Zeilen 1385–1640) in den `AgentRunner`.

**Nicht in Sprint 2:**
- Phase E (Cleanup & Deprecation — frühestens Sprint 3, nach stabilem Cutover)
- Frontend-UI-Redesign für neue Events (nur Backend-Events in Sprint 2)
- Benchmark-Comparison alt vs. neu (Sprint 3)

---

## Sprint-Übersicht

| # | Ticket | SP | Phase | Prio | Abhängigkeiten |
|---|--------|:--:|:-----:|:----:|----------------|
| S2-01 | Task-Type-Resolution in AgentRunner | 5 | C1 | P0 | — |
| S2-02 | Evidence Gates: Implementation + All-Tools-Failed | 5 | C1 | P0 | S2-01 |
| S2-03 | Evidence Gate: Orchestration | 3 | C1 | P0 | S2-01 |
| S2-04 | Reply Shaping Integration | 4 | C1 | P1 | S2-02 |
| S2-05 | Verification Service Integration | 3 | C1 | P1 | S2-04 |
| S2-06 | Reflection Loop Integration | 6 | C1 | P0 | S2-01, S2-04 |
| S2-07 | ReflectionFeedbackStore Integration | 2 | C1 | P2 | S2-06 |
| S2-08 | Lifecycle Events für Post-Loop-Phasen | 3 | C1 | P1 | S2-02, S2-04, S2-06 |
| S2-09 | Tool-Result Konvertierung: `list[ToolResult]` → String | 2 | C1 | P0 | — |
| S2-10 | Unit Tests: Evidence Gates im AgentRunner | 5 | — | P0 | S2-02, S2-03 |
| S2-11 | Unit Tests: Reply Shaping + Verification im Runner | 4 | — | P0 | S2-04, S2-05 |
| S2-12 | Unit Tests: Reflection Loop im Runner | 4 | — | P0 | S2-06 |
| S2-13 | Integration Tests: Post-Loop End-to-End | 6 | — | P0 | S2-01–S2-08 |
| S2-14 | HeadAgent Constructor: Neue Dependencies an Runner übergeben | 3 | D3 | P0 | S2-01–S2-06 |
| — | Puffer (Reviews, Bugfixes, Nachjustierung) | 5 | — | — | — |
| | **Gesamt** | **60** | | | |

---

## Reihenfolge & Parallelisierung

```
Woche 1 (24.03 – 28.03):
  ┌─ S2-09 Tool-Result Konvertierung ───────────── (Tag 1, Grundlage für alles)
  ├─ S2-01 Task-Type Resolution ────────────────── (Tag 1-2, parallel zu S2-09)
  │
  ├─ S2-02 Evidence Gates: Impl + All-Failed ───── (Tag 2-3, braucht S2-01 + S2-09)
  ├─ S2-03 Evidence Gate: Orchestration ─────────── (Tag 3, braucht S2-01 + S2-09)
  ├─ S2-04 Reply Shaping Integration ──────────── (Tag 3-4, braucht S2-02)
  ├─ S2-05 Verification Service Integration ────── (Tag 4, braucht S2-04)
  │
  └─ S2-10 Unit Tests Evidence Gates ──────────── (Tag 4-5, braucht S2-02 + S2-03)

Woche 2 (31.03 – 04.04):
  ┌─ S2-06 Reflection Loop Integration ─────────── (Tag 6-7, braucht S2-01 + S2-04)
  ├─ S2-07 ReflectionFeedbackStore ─────────────── (Tag 7, braucht S2-06)
  ├─ S2-08 Lifecycle Events Post-Loop ─────────── (Tag 7-8, braucht S2-02 + S2-06)
  ├─ S2-14 HeadAgent Constructor Update ────────── (Tag 8, braucht S2-01–S2-06)
  │
  ├─ S2-11 Unit Tests Reply Shaping + Verif ─────── (Tag 8-9, braucht S2-04 + S2-05)
  ├─ S2-12 Unit Tests Reflection Loop ──────────── (Tag 9, braucht S2-06)
  └─ S2-13 Integration Tests End-to-End ────────── (Tag 9-10, braucht alles)
```

---

## Ticket-Details

---

### S2-01 — Task-Type Resolution in AgentRunner (5 SP)

**Datei:** `backend/app/agent_runner.py` (ÄNDERN)

**Kontext:** Die Evidence Gates und der Reflection-Service brauchen einen `synthesis_task_type` String (`"implementation"`, `"research"`, `"orchestration"`, `"general"`, etc.), um Gate-Schwellwerte und Reflection-Thresholds zu bestimmen. Im Legacy-Code liegt diese Logik in `HeadAgent._resolve_synthesis_task_type()` (agent.py ~L2793). Da diese Methode auf `self._intent` (IntentDetector) und `self.synthesizer_agent` zugreift, muss sie für den Runner entkoppelt werden.

**Aufgaben:**
- [ ] `IntentDetector` als optionale Dependency in `AgentRunner.__init__()` aufnehmen:
  ```python
  intent_detector: Any | None = None,
  ```
- [ ] Neue Methode `_resolve_task_type()` implementieren:
  ```python
  def _resolve_task_type(self, user_message: str, tool_results: list[ToolResult]) -> str:
  ```
  - Konvertiert `list[ToolResult]` zu String via `_tool_results_to_string()` (S2-09)
  - Prüft Orchestration-Evidenz (spawned_subrun_id, terminal_reason) — IDENTISCHE Logik zu HeadAgent
  - Prüft Intent-Keywords via `self._intent_detector` (falls vorhanden):
    - `is_subrun_orchestration_task()` → `"orchestration"`
    - `is_file_creation_task()` → `"implementation"`
    - `is_web_research_task()` → `"research"`
  - Prüft `_IMPLEMENTATION_RE` Regex-Fallback
  - Default: `"general"`
- [ ] Private Regex `_IMPLEMENTATION_RE` aus `agent.py` verfügbar machen (Import oder Kopie in `agent_runner.py`)

**Akzeptanz:**
- `_resolve_task_type("erstelle eine Datei", [])` → `"implementation"`
- `_resolve_task_type("hallo", [])` → `"general"`
- `_resolve_task_type("...", [ToolResult(...content="spawned_subrun_id=abc...subrun-complete")])` → `"orchestration"`
- Ohne IntentDetector: Fallback auf Regex-only Klassifizierung

**Referenz:** AgentRunnerRefactoring.md → Phase C1, agent.py L2793–L2833

---

### S2-02 — Evidence Gates: Implementation + All-Tools-Failed (5 SP)

**Datei:** `backend/app/agent_runner.py` (ÄNDERN)

**Kontext:** Der Stub `_apply_evidence_gates()` wird mit den 2 wichtigsten Gates gefüllt. Die Logik wird 1:1 aus HeadAgent übernommen (agent.py L1522–L1589), nur das Input-Format ändert sich (`list[ToolResult]` statt `str`).

**Aufgaben:**
- [ ] `_apply_evidence_gates()` implementieren — Stub ersetzen:
  ```python
  def _apply_evidence_gates(
      self,
      final_text: str,
      tool_results: list[ToolResult],
      user_message: str,
  ) -> str:
  ```
- [ ] Task-Type via `_resolve_task_type()` (S2-01) bestimmen
- [ ] **Gate 1: Implementation Evidence**
  - Prüft via `_requires_implementation_evidence(user_message, task_type)`
  - Prüft via `_has_implementation_evidence(tool_results)` — scannt ToolResult-Objekte nach erfolgreichen write_file/apply_patch/run_command/code_execute
  - Fallback-Text wenn Evidence fehlt (IDENTISCH zum Legacy-Text)
- [ ] **Gate 2: All-Tools-Failed**
  - Prüft via `_all_tools_failed(tool_results)` — True wenn alle ToolResult.is_error=True und mindestens 1 Result vorhanden
  - Prüft via `_response_acknowledges_failures(final_text)` — IDENTISCHE Keyword-Liste
  - Fallback-Text wenn LLM Fehler ignoriert (IDENTISCH zum Legacy-Text)
- [ ] Helper-Methoden implementieren:
  - `_requires_implementation_evidence(user_message: str, task_type: str) -> bool`
  - `_has_implementation_evidence(tool_results: list[ToolResult]) -> bool`
  - `_all_tools_failed(tool_results: list[ToolResult]) -> bool`
  - `_response_acknowledges_failures(final_text: str) -> bool`

**Wichtig:** Die Logik in `_all_tools_failed` ändert sich: statt String-Parsing (`"[ERROR]"` / `"[OK]"`) wird jetzt direkt `ToolResult.is_error` geprüft. Das ist **sauberer** und **zuverlässiger**.

**Akzeptanz:**
- Implementation Gate feuert wenn task_type="implementation" und kein write_file/apply_patch/run_command/code_execute erfolgreich
- All-Tools-Failed Gate feuert wenn alle Results `is_error=True` und LLM halluziniert Erfolg
- All-Tools-Failed Gate feuert NICHT wenn mindestens 1 Result erfolgreich
- Fallback-Texte sind IDENTISCH zum Legacy-Code

**Referenz:** AgentRunnerRefactoring.md → Phase C1, agent.py L1522–L1589, L2835–L2913

---

### S2-03 — Evidence Gate: Orchestration (3 SP)

**Datei:** `backend/app/agent_runner.py` (ÄNDERN)

**Kontext:** Das Orchestration-Gate prüft, ob ein delegierter Subrun erfolgreich abgeschlossen wurde. Es feuert bei task_type ∈ {"orchestration", "orchestration_failed", "orchestration_pending"}.

**Aufgaben:**
- [ ] Orchestration-Gate in `_apply_evidence_gates()` ergänzen (nach Gate 2):
  ```python
  # Gate 3: Orchestration Evidence
  if task_type in ("orchestration", "orchestration_failed", "orchestration_pending"):
      if not self._has_orchestration_evidence(tool_results):
          ...
  ```
- [ ] Helper-Methoden implementieren:
  - `_has_orchestration_evidence(tool_results: list[ToolResult]) -> bool` — scannt content nach `spawned_subrun_id=` UND `subrun-complete`
  - `_has_orchestration_attempted(tool_results: list[ToolResult]) -> bool` — scannt content nach `spawned_subrun_id=`
- [ ] Zwei Fallback-Pfade (IDENTISCH zum Legacy-Code):
  - Attempted aber nicht completed → Timeout/Allowlist-Hinweis
  - Nicht attempted → "No subrun was executed"-Hinweis

**Akzeptanz:**
- Gate feuert wenn Subrun gestartet aber nicht abgeschlossen
- Gate feuert NICHT wenn Subrun erfolgreich (subrun-complete)
- Gate feuert NICHT bei task_type="general" oder "implementation"
- Fallback-Texte sind IDENTISCH zum Legacy-Code

**Referenz:** agent.py L1592–L1625, L2846–L2870

---

### S2-04 — Reply Shaping Integration (4 SP)

**Datei:** `backend/app/agent_runner.py` (ÄNDERN)

**Kontext:** Der Stub `_shape_final_response()` wird mit der bestehenden `ReplyShaper`-Klasse verbunden. Der ReplyShaper entfernt Tool-Marker, dedupliziert Bestätigungszeilen, erkennt Suppressed-Responses und normalisiert Whitespace.

**Aufgaben:**
- [ ] `ReplyShaper` als Dependency in `AgentRunner.__init__()` aufnehmen:
  ```python
  reply_shaper: ReplyShaper | None = None,
  ```
- [ ] `_shape_final_response()` Stub ersetzen:
  ```python
  def _shape_final_response(
      self,
      final_text: str,
      tool_results: list[ToolResult],
  ) -> str:
  ```
  - Sanitize: `self._reply_shaper.sanitize(final_text)` — entfernt `[TOOL_CALL]` Blöcke
  - Shape: `self._reply_shaper.shape(final_text=..., tool_results=tool_results_str, tool_markers=...)` — Deduplizierung, Suppression
  - Tool-Marker-Set aus `self.tool_registry.keys()` ableiten
  - Bei `was_suppressed=True`: Suppressed-Reply-Text verwenden (nicht leeren String)
  - Rückgabe: `shape_result.text`
- [ ] Reply Shaping muss NACH Evidence Gates und VOR Verification laufen (Reihenfolge in `run()` anpassen falls nötig)

**Akzeptanz:**
- `[TOOL_CALL]...[/TOOL_CALL]` Blöcke werden entfernt
- Duplizierte Tool-Bestätigungszeilen werden dedupliziert
- NO_REPLY / ANNOUNCE_SKIP Tokens werden entfernt
- Suppressed Responses werden zum passenden Fallback-Text

**Referenz:** agent.py L2926–L2943, services/reply_shaper.py

---

### S2-05 — Verification Service Integration (3 SP)

**Datei:** `backend/app/agent_runner.py` (ÄNDERN)

**Kontext:** Die VerificationService prüft ob die finale Antwort mindestens 8 Zeichen hat und grundlegende Qualitätskriterien erfüllt. Im Legacy-Code wird `verify_final()` als allerletzter Check vor der Antwort aufgerufen.

**Aufgaben:**
- [ ] `VerificationService` als optionale Dependency in `AgentRunner.__init__()` aufnehmen:
  ```python
  verification_service: VerificationService | None = None,
  ```
- [ ] Final-Verification nach Reply Shaping in `run()` einfügen:
  ```python
  if self._verification_service:
      final_check = self._verification_service.verify_final(
          user_message=user_message,
          final_text=final_text,
      )
      if not final_check.ok:
          final_text = "No output generated."
  ```
- [ ] Optional: `verify_tool_result()` Call NACH `_execute_tool_calls()` — prüft ob Tool-Results brauchbar sind (analog zu Legacy L1135)

**Akzeptanz:**
- Leere oder zu kurze Antwort (< 8 Zeichen) → `"No output generated."`
- Normale Antwort → unverändert durchgelassen
- Ohne VerificationService (None) → keine Prüfung (graceful degradation)

**Referenz:** agent.py L1625, services/verification_service.py

---

### S2-06 — Reflection Loop Integration (6 SP)

**Datei:** `backend/app/agent_runner.py` (ÄNDERN)

**Kontext:** Die Reflection ist der aufwändigste Post-Loop-Schritt. Der ReflectionService bewertet die finale Antwort auf goal_alignment, completeness und factual_grounding. Bei `should_retry=True` wird ein erneuter LLM-Call mit Feedback ausgeführt. Im neuen Runner gibt es keinen SynthesizerAgent mehr — stattdessen wird der LLM direkt mit Feedback-Messages aufgerufen.

**Aufgaben:**
- [ ] Neue Methode `_run_reflection()` implementieren:
  ```python
  async def _run_reflection(
      self,
      final_text: str,
      user_message: str,
      tool_results: list[ToolResult],
      task_type: str,
      model: str | None,
      send_event: SendEvent,
      request_id: str,
      session_id: str,
      messages: list[dict],
  ) -> str:
  ```
- [ ] Reflection-Passes-Loop:
  ```python
  for reflection_pass in range(max_passes):
      verdict = await self._reflection_service.reflect(
          user_message=user_message,
          plan_text="",  # Kein separater Plan im neuen Modell
          tool_results=tool_results_str,
          final_answer=final_text,
          model=model,
          task_type=task_type,
      )
      if not verdict.should_retry:
          break
      # Feedback-Message an LLM senden für verbesserte Antwort
      feedback_lines = [issue for issue in verdict.issues if issue]
      if verdict.suggested_fix:
          feedback_lines.append(f"Suggested fix: {verdict.suggested_fix}")
      feedback = "\n".join(feedback_lines).strip() or "No specific issues."
      
      # Neuer LLM-Call mit Reflection-Feedback (OHNE Tools)
      messages.append({"role": "user", "content": f"[REFLECTION FEEDBACK]\n{feedback}\n\nPlease revise your answer."})
      stream_result = await self.client.stream_chat_with_tools(
          messages=messages,
          tools=None,
          model=model,
          on_text_chunk=lambda chunk: send_event({"type": "stream", "content": chunk}),
      )
      final_text = stream_result.text
  ```
- [ ] Reflection in `run()` aufrufen — nach Evidence Gates, vor Reply Shaping:
  ```python
  if self._reflection_service and settings.runner_reflection_enabled:
      final_text = await self._run_reflection(...)
  ```
- [ ] Safety: `len(final_text.strip()) >= 8` Mindestlänge-Check vor Reflection (wie Legacy)
- [ ] TypeError-Fallback für ältere ReflectionService-Versionen ohne `task_type` Parameter (wie Legacy)

**WICHTIG:** Im neuen Modell gibt es keinen `plan_text`. Der Legacy-Code übergibt den Planner-Output als `plan_text`. Im Runner wird stattdessen ein leerer String oder eine Zusammenfassung der Tool-Calls übergeben.

**Akzeptanz:**
- Reflection wird aufgerufen wenn `runner_reflection_enabled=True` und ReflectionService vorhanden
- Bei `should_retry=True`: Neuer LLM-Call mit Feedback, Antwort wird ersetzt
- Bei `should_retry=False`: Original-Antwort bleibt
- Max 1 Reflection-Pass (konfigurierbar via `runner_reflection_max_passes`)
- Fehler in Reflection → Log + Original-Antwort beibehalten (kein Crash)

**Referenz:** agent.py L1395–L1513, services/reflection_service.py

---

### S2-07 — ReflectionFeedbackStore Integration (2 SP)

**Datei:** `backend/app/agent_runner.py` (ÄNDERN)

**Kontext:** Die Reflection-Ergebnisse werden für Monitoring und Analyse in einem `ReflectionFeedbackStore` persistiert. Optional, aber wichtig für Qualitätsmonitoring.

**Aufgaben:**
- [ ] `ReflectionFeedbackStore` als optionale Dependency in `AgentRunner.__init__()` aufnehmen:
  ```python
  reflection_feedback_store: Any | None = None,
  ```
- [ ] In `_run_reflection()` nach jedem Verdict speichern:
  ```python
  if self._reflection_feedback_store is not None:
      self._reflection_feedback_store.store(
          ReflectionRecord(
              record_id=f"{request_id}-reflection-{pass + 1}",
              session_id=session_id,
              request_id=request_id,
              task_type=task_type,
              score=verdict.score,
              goal_alignment=verdict.goal_alignment,
              completeness=verdict.completeness,
              factual_grounding=verdict.factual_grounding,
              issues=list(verdict.issues),
              suggested_fix=verdict.suggested_fix,
              model_id=model or settings.llm_model,
              prompt_variant="unified",  # Kein Prompt-Variant im neuen Modell
              retry_triggered=verdict.should_retry,
              timestamp_utc=datetime.now(UTC).isoformat(),
          )
      )
  ```

**Akzeptanz:**
- Wenn Store vorhanden: ReflectionRecord wird nach jedem Verdict gespeichert
- Wenn Store nicht vorhanden (None): Keine Aktion, kein Fehler
- Record enthält korrekte task_type, Scores und Metadata

**Referenz:** agent.py L1469–L1489

---

### S2-08 — Lifecycle Events für Post-Loop-Phasen (3 SP)

**Datei:** `backend/app/agent_runner.py` (ÄNDERN)

**Kontext:** Die Post-Loop-Schritte emittieren Lifecycle Events für Monitoring und Debugging. Im Legacy-Code gibt es Events für `implementation_evidence_missing`, `all_tools_failed_gate_applied`, `orchestration_evidence_missing`, `reply_shaping_started/completed`, `reflection_completed/failed/skipped`, `verification_final`.

**Aufgaben:**
- [ ] In `_apply_evidence_gates()` emittieren:
  - `"implementation_evidence_missing"` wenn Gate 1 feuert
  - `"all_tools_failed_gate_applied"` wenn Gate 2 feuert
  - `"orchestration_evidence_missing"` wenn Gate 3 feuert
- [ ] In `_shape_final_response()` emittieren:
  - `"reply_shaping_started"` mit `input_chars`
  - `"reply_shaping_completed"` mit `original_chars`, `shaped_chars`, `suppressed`, `reason`, `removed_tokens`, `deduped_lines`
- [ ] In `_run_reflection()` emittieren:
  - `"reflection_completed"` mit pass, score, goal_alignment, completeness, factual_grounding, issues, should_retry
  - `"reflection_failed"` bei Fehler
  - `"reflection_skipped"` wenn final_text zu kurz
- [ ] In `run()` nach Verification emittieren:
  - `"verification_final"` mit status, reason, details

**Hinweis:** `_emit_lifecycle` ist bereits als Callback im Constructor vorhanden. Events werden via `send_event` an den Client gesendet.

**Akzeptanz:**
- Alle Post-Loop Events werden korrekt emittiert
- Event-Details enthalten die gleichen Felder wie im Legacy-Code
- Ohne emit_lifecycle_fn (None): Keine Events, kein Fehler

**Referenz:** agent.py L1524–L1640 (alle emit_lifecycle-Calls in der Post-Loop-Phase)

---

### S2-09 — Tool-Result Konvertierung: `list[ToolResult]` → String (2 SP)

**Datei:** `backend/app/agent_runner.py` (ÄNDERN)

**Kontext:** Mehrere bestehende Services (ReflectionService, VerificationService, Evidence-Gate-Helfer) erwarten Tool-Results als String im Format `"[tool_name] result_content\n"`. Der AgentRunner arbeitet intern mit `list[ToolResult]`. Eine Konverter-Methode wird gebraucht.

**Aufgaben:**
- [ ] Neue Methode `_tool_results_to_string()`:
  ```python
  def _tool_results_to_string(self, tool_results: list[ToolResult]) -> str:
      """Konvertiert list[ToolResult] zu Legacy-kompatiblem String-Format.
      
      Format pro Result:
        [tool_name] content        (bei Erfolg)
        [tool_name] [ERROR] content (bei Fehler)
      """
      if not tool_results:
          return ""
      lines = []
      for tr in tool_results:
          prefix = f"[{tr.tool_name}]"
          if tr.is_error:
              lines.append(f"{prefix} [ERROR] {tr.content}")
          else:
              lines.append(f"{prefix} {tr.content}")
      return "\n".join(lines)
  ```
- [ ] Sicherstellen, dass das Format kompatibel ist mit:
  - `_all_tools_failed()` Patterns (wenn Fallback auf String nötig)
  - `ReflectionService.reflect(tool_results=...)` Parameter
  - `ReplyShaper.shape(tool_results=...)` Parameter
  - `_has_orchestration_evidence()` Pattern-Scan

**Akzeptanz:**
- Leere Liste → `""`
- Einzelnes OK-Result → `"[tool_name] content"`
- Einzelnes Error-Result → `"[tool_name] [ERROR] content"`
- Mehrere Results → Newline-separiert
- Kompatibel mit Legacy String-Patterns (`[ERROR]`, `[OK]`, `spawned_subrun_id=`)

**Referenz:** AgentRunnerRefactoring.md → Phase C1

---

### S2-10 — Unit Tests: Evidence Gates im AgentRunner (5 SP)

**Datei:** `backend/tests/test_agent_runner_evidence_gates.py` (NEU)

**Aufgaben:**
- [ ] Test: `_resolve_task_type()` erkennt Implementation-Keywords
- [ ] Test: `_resolve_task_type()` erkennt Orchestration via spawned_subrun_id
- [ ] Test: `_resolve_task_type()` erkennt Research-Keywords
- [ ] Test: `_resolve_task_type()` Default "general"
- [ ] Test: Gate 1 feuert bei Implementation ohne Evidence
- [ ] Test: Gate 1 feuert NICHT bei Implementation MIT Evidence (write_file OK)
- [ ] Test: Gate 1 feuert NICHT bei task_type="general"
- [ ] Test: Gate 2 feuert wenn alle Tools fehlgeschlagen + LLM halluziniert
- [ ] Test: Gate 2 feuert NICHT wenn mindestens 1 Tool OK
- [ ] Test: Gate 2 feuert NICHT wenn LLM acknowledges Failures
- [ ] Test: Gate 3 feuert bei Orchestration ohne Evidence
- [ ] Test: Gate 3 feuert NICHT bei Orchestration mit subrun-complete
- [ ] Test: Gate 3 unterscheidet attempted vs. not attempted
- [ ] Test: `_tool_results_to_string()` Formatierung korrekt
- [ ] Test: Alle 3 Gates zusammen in einem Run (Integration-artiger Unit Test)

**Setup:**
- AgentRunner mit Mock-Dependencies instantiieren (wie in Sprint 1 Tests)
- ToolResult-Objekte mit verschiedenen Konstellationen erstellen

**Akzeptanz:**
- Mindestens 15 Tests
- Alle Tests grün
- Edge Cases abgedeckt: leere tool_results, leerer final_text, gemischte Error/OK Results

**Referenz:** Bestehende Tests in test_head_agent_replan_policy.py als Vorlage

---

### S2-11 — Unit Tests: Reply Shaping + Verification im Runner (4 SP)

**Datei:** `backend/tests/test_agent_runner_reply_shaping.py` (NEU)

**Aufgaben:**
- [ ] Test: `[TOOL_CALL]...[/TOOL_CALL]` werden entfernt
- [ ] Test: NO_REPLY Token wird entfernt und ggf. suppressed
- [ ] Test: ANNOUNCE_SKIP Token wird entfernt
- [ ] Test: Duplizierte Tool-Bestätigungszeilen werden dedupliziert
- [ ] Test: Suppressed Response liefert Fallback-Text
- [ ] Test: Verification feuert bei leerem Text → "No output generated."
- [ ] Test: Verification feuert bei zu kurzem Text (< 8 Zeichen)
- [ ] Test: Verification lässt normalen Text durch
- [ ] Test: Ohne ReplyShaper (None) → original Text returned
- [ ] Test: Ohne VerificationService (None) → keine Prüfung

**Akzeptanz:**
- Mindestens 10 Tests
- Alle Tests grün
- Bestehende ReplyShaper-Tests bleiben grün (keine Regression)

---

### S2-12 — Unit Tests: Reflection Loop im Runner (4 SP)

**Datei:** `backend/tests/test_agent_runner_reflection.py` (NEU)

**Aufgaben:**
- [ ] Test: Reflection wird übersprungen wenn `runner_reflection_enabled=False`
- [ ] Test: Reflection wird übersprungen wenn ReflectionService=None
- [ ] Test: Reflection wird übersprungen wenn final_text < 8 Zeichen
- [ ] Test: Reflection mit should_retry=False → original Text bleibt
- [ ] Test: Reflection mit should_retry=True → LLM Retry-Call → neuer Text
- [ ] Test: Reflection mit max_passes=2 → korrekte Anzahl Durchläufe
- [ ] Test: Reflection Exception → original Text bleibt + kein Crash
- [ ] Test: ReflectionFeedbackStore wird aufgerufen wenn vorhanden
- [ ] Test: ReflectionFeedbackStore wird ignoriert wenn None
- [ ] Test: TypeError-Fallback für ältere ReflectionService-Versionen

**Setup:**
- ReflectionService mocken: `reflect()` → ReflectionVerdict
- LlmClient mocken: `stream_chat_with_tools()` → StreamResult
- ReflectionFeedbackStore mocken: `store()` → None

**Akzeptanz:**
- Mindestens 10 Tests
- Alle Tests grün
- Reflection-Logik verhält sich identisch zum Legacy-Code

---

### S2-13 — Integration Tests: Post-Loop End-to-End (6 SP)

**Datei:** `backend/tests/test_agent_runner_post_loop_integration.py` (NEU)

**Aufgaben:**
- [ ] Test: Einfache Frage → keine Gates, kein Shaping-Effekt, keine Reflection
- [ ] Test: Implementation-Task ohne Tool-Erfolg → Evidence Gate feuert
- [ ] Test: Implementation-Task mit write_file Erfolg → normaler Output
- [ ] Test: Alle Tools fehlgeschlagen → All-Tools-Failed Gate feuert
- [ ] Test: Orchestration ohne subrun-complete → Orchestration Gate feuert
- [ ] Test: Tool-Marker im Output → Reply Shaping entfernt sie
- [ ] Test: Reflection triggered → verbesserter Output
- [ ] Test: Verification bei leerem Output → "No output generated."
- [ ] Test: Full Pipeline: Tool-Calls → Evidence Gates → Reply Shaping → Reflection → Verification
- [ ] Test: Feature-Flag Off → Legacy-Pfad, Feature-Flag On → Runner-Pfad mit Post-Loop

**Setup:**
- HeadAgent mit Mocked Dependencies (ähnlich wie test_agent_runner_integration.py aus Sprint 1)
- USE_CONTINUOUS_LOOP=True
- Mock-LlmClient der Tool-Calls + Text liefert

**Akzeptanz:**
- Mindestens 10 Tests
- Alle Tests grün
- Bestehende 53 Sprint-1 Tests bleiben grün
- Bestehende ~1410 Regressionstests bleiben grün

---

### S2-14 — HeadAgent Constructor: Neue Dependencies an Runner übergeben (3 SP)

**Datei:** `backend/app/agent.py` (ÄNDERN)

**Kontext:** In Sprint 1 wurde `AgentRunner` in `_build_sub_agents()` erstellt, aber ohne IntentDetector, ReplyShaper, VerificationService und ReflectionFeedbackStore. Diese müssen jetzt durchgereicht werden.

**Aufgaben:**
- [ ] In `_build_sub_agents()` die fehlenden Dependencies übergeben:
  ```python
  self._agent_runner = AgentRunner(
      ...  # bestehende Parameter
      intent_detector=self._intent,
      reply_shaper=self._reply_shaper,
      verification_service=self._verification,
      reflection_feedback_store=self._reflection_feedback_store,
  )
  ```
- [ ] `configure_runtime()` erweitern: wenn sich der ReflectionService ändert (Provider-Switch), auch im Runner aktualisieren:
  ```python
  if self._agent_runner is not None:
      self._agent_runner.client = self.client
      self._agent_runner._reflection_service = self._reflection_service
  ```
- [ ] Sicherstellen, dass `_reflection_feedback_store` erst NACH `_refresh_long_term_memory_store()` gesetzt wird (Reihenfolge in `_build_sub_agents()` prüfen)

**Akzeptanz:**
- Im Feature-Flag-On-Modus: Runner hat Zugriff auf alle benötigten Services
- Im Feature-Flag-Off-Modus: `_agent_runner` bleibt None
- Bestehende Integration-Tests bleiben grün
- Neuer Test: AgentRunner hat alle Dependencies wenn USE_CONTINUOUS_LOOP=True

**Referenz:** agent.py L187–L210 (Constructor), L496–L570 (_build_sub_agents)

---

## Reihenfolge der Post-Loop-Schritte in `run()`

Die korrekte Reihenfolge der Post-Loop-Schritte nach dem Loop-Exit ist:

```
1. Budget-Exhaustion Fallback    (bereits implementiert)
2. Steer-Interrupted Fallback    (bereits implementiert)
3. Guard: ensure final_text      (bereits implementiert)
4. Evidence Gates                 (S2-02, S2-03) ← STUB ersetzen
5. Reflection                    (S2-06) ← NEU einfügen
6. Reply Shaping                 (S2-04) ← STUB ersetzen
7. Verification                  (S2-05) ← NEU einfügen
8. Final Event                   (bereits implementiert)
9. Memory Persistence            (bereits implementiert)
10. Lifecycle: runner_completed   (bereits implementiert)
```

**Warum diese Reihenfolge?**
- Evidence Gates VOR Reflection: Verhindert Reflection auf halluzinierte Antworten
- Reflection VOR Reply Shaping: Reflection sieht den unbereinigten Text
- Reply Shaping VOR Verification: Verification prüft den finalen, bereinigten Text
- Verification als allerletzter Check: "No output generated." Fallback

---

## Risiken & Mitigationen

| # | Risiko | Impact | Mitigation |
|---|--------|--------|------------|
| R1 | Evidence Gates 1:1 Migration — subtile Logik-Unterschiede durch ToolResult statt String | Hoch | Unit Tests mit identischen Szenarien wie Legacy-Tests. `_tool_results_to_string()` für Rückwärtskompatibilität. |
| R2 | Reflection ohne Plan-Text — ReflectionService erwartet `plan_text` Parameter | Mittel | Leerer String oder Loop-Zusammenfassung als Ersatz. ReflectionService akzeptiert leere Strings. |
| R3 | Reply Shaping Suppression bei Runner-Output — neues Output-Format könnte False Positives auslösen | Mittel | Tests mit typischen Runner-Outputs (keine `[TOOL_CALL]` Marker, aber möglicherweise Tool-Confirmations). |
| R4 | Reihenfolge Evidence Gates ↔ Reply Shaping ↔ Reflection — falsche Reihenfolge verfälscht Ergebnisse | Hoch | Reihenfolge exakt wie im Legacy-Code (Evidence → Reflection → Shaping → Verification). |
| R5 | ReflectionFeedbackStore nicht initialisiert im Runner-Pfad | Niedrig | Optional (None-Check). Integration Test dass Store-Persistierung funktioniert. |

---

## Definition of Done (Sprint 2)

```
☐ _apply_evidence_gates() implementiert (3 Gates)
☐ _shape_final_response() implementiert (ReplyShaper Integration)
☐ _run_reflection() implementiert (Reflection Loop)
☐ VerificationService integriert (verify_final)
☐ _resolve_task_type() implementiert (Task-Type Resolution)
☐ _tool_results_to_string() implementiert (Konverter)
☐ ReflectionFeedbackStore integriert
☐ Lifecycle Events für alle Post-Loop-Phasen emittiert
☐ HeadAgent._build_sub_agents() übergibt alle neuen Dependencies
☐ Alle Sprint-1-Tests (53) weiterhin grün
☐ Alle Regressionstests (~1410) weiterhin grün
☐ Neue Unit Tests: Evidence Gates (≥15 Tests)
☐ Neue Unit Tests: Reply Shaping + Verification (≥10 Tests)
☐ Neue Unit Tests: Reflection (≥10 Tests)
☐ Neue Integration Tests: Post-Loop E2E (≥10 Tests)
☐ Reihenfolge: Evidence Gates → Reflection → Reply Shaping → Verification korrekt
☐ Keine Security-Regression (Evidence Gates schützen vor Halluzination)
☐ Code Review durchgeführt
```
