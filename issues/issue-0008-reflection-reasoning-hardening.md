# Issue-0008 · Reflection Reasoning Hardening

**Ziel:** Drei strukturelle Schwächen der `ReflectionService`-Pipeline beseitigen, die dazu führen, dass faktische Halluzinationen das Quality-Gate passieren, obwohl die KI selbst die Fehler explizit benennt.

---

## Auf einen Blick

| # | Problem | Root Cause | Fix | Risiko |
|---|---------|------------|-----|--------|
| A | `factual_grounding=0.3` → `should_retry=False` | Arithmetisches Mittel dilutiert FG durch hohe GA/C | Hard-Gate: `FG < 0.4 → always retry` | niedrig |
| B | Reflection-LLM sieht netstat-Output nur zu ≤8 % | Hard-coded `tool_results[:1000]` im Prompt | Konfigurierbares Limit, Default 8000 | minimal |
| C | Reflection-LLM ohne explizite Grounding-Direktive | System-Prompt ohne FG-Anweisung | System-Prompt um Zero-Tolerance-Direktive erweitern | minimal |

---

## Inhaltsverzeichnis

1. [Executive Summary](#1-executive-summary)
2. [Hintergrund & Evidenz aus Logdaten](#2-hintergrund--evidenz-aus-logdaten)
3. [Problem A – Factual-Grounding-Dilution durch Averaging](#3-problem-a--factual-grounding-dilution-durch-averaging)
4. [Problem B – Tool-Results-Kontext-Abschneidung im Reflection-Prompt](#4-problem-b--tool-results-kontext-abschneidung-im-reflection-prompt)
5. [Problem C – Reflection System-Prompt ohne Factual-Grounding-Direktive](#5-problem-c--reflection-system-prompt-ohne-factual-grounding-direktive)
6. [Implementierungsplan Problem A](#6-implementierungsplan-problem-a)
7. [Implementierungsplan Problem B](#7-implementierungsplan-problem-b)
8. [Implementierungsplan Problem C](#8-implementierungsplan-problem-c)
9. [Config-Erweiterungen](#9-config-erweiterungen)
10. [Observability-Erweiterungen (Lifecycle-Events)](#10-observability-erweiterungen-lifecycle-events)
11. [Teststrategie](#11-teststrategie)
12. [Reihenfolge & Abhängigkeiten](#12-reihenfolge--abhängigkeiten)
13. [Risiken & Edge-Cases](#13-risiken--edge-cases)
14. [Deployment-Hinweise](#14-deployment-hinweise)
15. [Acceptance Criteria Checkliste](#15-acceptance-criteria-checkliste)

---

## 1. Executive Summary

Der `ReflectionService` bewertet eine Agent-Antwort in drei Dimensionen:

| Dimension          | Bedeutung                                             |
|--------------------|-------------------------------------------------------|
| `goal_alignment`   | Hat die Antwort das Ziel der User-Message erfüllt?    |
| `completeness`     | Sind alle Teile vollständig beantwortet?              |
| `factual_grounding`| Sind alle Fakten in den Tool-Ergebnissen nachweisbar? |

Der `should_retry`-Entscheid fällt aktuell **ausschließlich** über den Durchschnittswert:

```python
score = (goal_alignment + completeness + factual_grounding) / 3
should_retry = score < self.threshold   # threshold = 0.6
```

**Das ist grundlegend falsch** für Faktizitätsgüte:  
Ein Wert von `goal_alignment=0.8, completeness=0.7, factual_grounding=0.3` ergibt
`score = 0.6` → `should_retry = False` – obwohl `factual_grounding=0.3` eine manifeste
Halluzination anzeigt und das Reflection-LLM sogar konkrete PIDs als fehlinformiert markiert.

Zusätzlich wird `tool_results` im Reflection-Prompt auf **1000 Zeichen** abgeschnitten – ein
`netstat -an`-Output oder `tasklist` enthält regelmäßig 5.000–20.000 Zeichen. Die
Qualitätsinstanz sieht damit die relevanten Daten gar nicht und kann `factual_grounding` nicht
korrekt beurteilen.

**Alle drei Probleme sind synergetisch:** Kürzung → LLM kann Halluzination nicht erkennen →
`factual_grounding` zu hoch → Hard-Gate wäre sowieso nicht ausgelöst worden. Zusätzlich fehlt
die explizite Instruktion des Reflection-LLMs, wann `factual_grounding` zwingend niedrig sein
muss. Wir müssen **alle drei** Punkte lösen.

### Entscheidungsfluss nach dem Fix

```
_parse_verdict(raw_llm_output)
        │
        ▼
  payload parsebar? ──Nein──► fallback: score=0.0, FG=0.0,
        │                               hard_factual_fail=True,
        │                               should_retry=True
        │ Ja
        ▼
  GA, C, FG clampen [0,1]
  score = avg(GA, C, FG)
        │
        ▼
  FG < factual_grounding_hard_min? ──Ja──► hard_factual_fail=True
        │                                        │
        │ Nein                                   │
        ▼                                        │
  hard_factual_fail=False                        │
        │                                        │
        └──────────────────►  should_retry = (score < threshold)
                                              or hard_factual_fail
        │
        ▼
  ReflectionVerdict(score, GA, C, FG,
                    should_retry, hard_factual_fail)
```

---

## 2. Hintergrund & Evidenz aus Logdaten

Monitoring-Log: `backend/monitoring/ws_orchestration_monitor_20260301-211350.json`

```json
{
  "stage": "reflection_completed",
  "details": {
    "pass": 1,
    "score": 0.6333,
    "goal_alignment": 0.8,
    "completeness": 0.7,
    "issues": [
      "The response identifies PIDs (10168, 8248, 16200) that are NOT present in the provided netstat output",
      "The response does not use actual data from the tool outputs",
      "Discrepancy between the tool output and the PIDs mentioned in the response"
    ],
    "should_retry": false
  }
}
```

Zu rekonstruieren: `score = 0.8 + 0.7 + x / 3 = 0.6333` → `x = factual_grounding ≈ 0.3`.  
Das Reflection-LLM hat die Halluzination erkannt und `factual_grounding` niedrig eingestuft –
aber `should_retry=false`, weil der Durchschnitt gerade noch über `0.6` lag.

**Warum konnte das Reflection-LLM die PIDs überhaupt nicht vollständig prüfen?**  
`netstat -an` listet alle offenen Ports und Verbindungen – typisch 100–500 Zeilen, 8.000–20.000
Zeichen. Der Reflection-Prompt erhält davon nur `tool_results[:1000]` – also rund
40–80 Zeilen. Mit hoher Wahrscheinlichkeit sind die kritischen PIDs jenseits von Zeichen 1000.

---

## 3. Problem A – Factual-Grounding-Dilution durch Averaging

### 3.1 Betroffene Datei

`backend/app/services/reflection_service.py`, Methode `_parse_verdict()`, Zeilen 107–117.

### 3.2 Aktueller Code (Zeilen 107–117)

```python
goal_alignment = self._clamp_score(payload.get("goal_alignment"))
completeness = self._clamp_score(payload.get("completeness"))
factual_grounding = self._clamp_score(payload.get("factual_grounding"))
score = (goal_alignment + completeness + factual_grounding) / 3

# ...

return ReflectionVerdict(
    score=score,
    goal_alignment=goal_alignment,
    completeness=completeness,
    factual_grounding=factual_grounding,
    issues=issues,
    suggested_fix=suggested_fix,
    should_retry=score < self.threshold,   # ← BUG: kein Hard-Gate
)
```

### 3.3 Bug-Analyse

Das Problem ist ein klassischer **Kompensationseffekt** beim arithmetischen Mittel:

```
should_retry = score < 0.6
             = avg(GA, C, FG) < 0.6
```

Die Formel erlaubt `FG=0.0` (komplette Halluzination), solange `GA + C` ausreichend hoch sind:

| GA  | C   | FG  | score | should_retry |
|-----|-----|-----|-------|--------------|
| 1.0 | 1.0 | 0.0 | 0.667 | **False** ← katastrophal |
| 0.9 | 0.7 | 0.2 | 0.600 | False       |
| 0.8 | 0.7 | 0.3 | 0.600 | False       |
| 0.6 | 0.6 | 0.4 | 0.533 | True        |

**Fazit:** Factual Grounding als Qualitätsdimension ist de facto deaktiviert, wenn die anderen
zwei Dimensionen stark sind. Das ist die Kombination, die bei Tool-basierten Agent-Antworten
am häufigsten auftritt: Ziel klar verstanden (hohe GA), vollständige Antwort (hohe C) –
aber Fakten aus eigenem Modellgedächtnis statt aus Tool-Outputs.

### 3.4 Korrektur-Ansatz

**Hard-Gate**: Wenn `factual_grounding < factual_grounding_hard_min`, dann immer `should_retry = True`,
unabhängig vom gemittelten Score.

```python
hard_factual_fail = factual_grounding < self.factual_grounding_hard_min
should_retry = (score < self.threshold) or hard_factual_fail
```

Warum `0.4` als Default?

- `0.0–0.3`: Das LLM erkennt explizit, dass Fakten nicht in den Tool-Outputs nachweisbar sind
- `0.3–0.5`: Partielle Grounding-Probleme; einige Fakten unklar
- `0.5–1.0`: Grounding ausreichend nachgewiesen

`0.4` ist der konservative Wert:  
Werte darunter → Retry; Werte von 0.4–0.6 → lässt noch den Durchschnitt entscheiden.

---

## 4. Problem B – Tool-Results-Kontext-Abschneidung im Reflection-Prompt

### 4.1 Betroffene Datei

`backend/app/services/reflection_service.py`, Methode `_build_reflection_prompt()`, Zeilen 53–66.

### 4.2 Aktueller Code

```python
def _build_reflection_prompt(
    self,
    *,
    user_message: str,
    plan_text: str,
    tool_results: str,
    final_answer: str,
) -> str:
    return (
        "Evaluate this response. Return JSON with these fields:\n"
        '{"goal_alignment": 0.0-1.0, "completeness": 0.0-1.0, '
        '"factual_grounding": 0.0-1.0, "issues": ["..."], '
        '"suggested_fix": "..." or null}\n\n'
        f"User question: {user_message}\n"
        f"Plan: {plan_text[:500]}\n"
        f"Tool outputs: {tool_results[:1000]}\n"   # ← BUG: hard-coded 1000
        f"Final answer: {final_answer}"
    )
```

### 4.3 Bug-Analyse

Hard-codierte Limits:
- `plan_text[:500]` – abgeschnittener Plan verhindert, dass das Reflection-LLM die
  ursprüngliche Intention vollständig bewertet
- `tool_results[:1000]` – bei Tool-Outputs wie `netstat`, `tasklist`, `ls -la /`, `cat` von
  großen Dateien, usw. gehen die kritischen Daten verloren

Konkrete Rechnung für `netstat -an`:
- Typische Ausgabe: 200 Zeilen × 80 Zeichen = 16.000 Zeichen
- Sichtbar für das Reflection-LLM: nur die ersten ~12 Zeilen
- PIDs stehen typischerweise in Spalte 5 der Zeilen, die nach Zeichen 1000 kommen

**Folge:** Das Reflection-LLM bewertet `factual_grounding` auf Basis eines stark verkürzten
Datensatzes und kann faktische Fehler in der Agent-Antwort nicht aufdecken – selbst wenn es
wollte.

### 4.4 Korrektur-Ansatz

Die Limits aus dem Code entfernen und konfigurierbar machen:

```python
f"Tool outputs: {tool_results[:self.tool_results_max_chars]}\n"
f"Plan: {plan_text[:self.plan_max_chars]}\n"
```

Sinnvolle Defaults:
- `tool_results_max_chars = 8000` (deckt netstat vollständig ab, bleibt im Context-Window)
- `plan_max_chars = 2000` (reicht für alle bisherigen Pläne mit Luft)

**Prompt-Größenvergleich vor/nach dem Fix:**

| Slot | Vorher (hard-coded) | Nachher (Default) | Faktor |
|------|---------------------|-------------------|--------|
| `plan_text` | 500 Zeichen | 2.000 Zeichen | 4× |
| `tool_results` | 1.000 Zeichen | 8.000 Zeichen | 8× |
| `user_message` | unbegrenzt | unbegrenzt | – |
| `final_answer` | unbegrenzt | unbegrenzt | – |
| **Gesamtprompt** | **~2.500–4.000 Zeichen** | **~10.000–14.000 Zeichen** | ~4× |
| **Tokens (÷4)** | **~625–1.000 Tokens** | **~2.500–3.500 Tokens** | 4× |
| **% des 128k-Window** | **< 1 %** | **< 3 %** | – |

Der Zuwachs ist vollständig unkritisch. Das Reflection-LLM hat nach dem Fix genügend Kontext,
um `factual_grounding` korrekt zu beurteilen.

**Context-Window-Überlegung:**  
Das Reflection-LLM (`llama3.3:70b-instruct-q4_K_M`) hat ein Context-Window von 128k Tokens.
Bei 4 Zeichen/Token entsprechen 8000 Zeichen ~2000 Tokens – vollständig unkritisch.
Der Gesamtprompt mit `user_message + plan + tool_results + final_answer` bleibt
bei ≤ 12.000 Zeichen → ~3000 Tokens → weit unter jeder Grenze.

---

## 5. Problem C – Reflection System-Prompt ohne Factual-Grounding-Direktive

### 5.1 Betroffene Datei

`backend/app/services/reflection_service.py`, Methode `reflect()`, Zeilen 42–49.

### 5.2 Aktueller System-Prompt

```python
raw_verdict = await self.client.complete_chat(
    system_prompt="You are a quality assurance agent. Evaluate answers critically and objectively.",
    ...
)
```

### 5.3 Bug-Analyse

Der System-Prompt gibt dem Reflection-LLM keinerlei Instruktion, wie es `factual_grounding`
bewerten soll. Das LLM kann es beliebig interpretieren – typischerweise als „klingt plausibel",
nicht als „ist in den Tool-Outputs nachweisbar".

Das Fehlen einer expliziten Direktive erklärt, warum selbst mit vollständigem Tool-Output
ein LLM `factual_grounding=0.5` setzen könnte, wenn die Antwort „plausibel klingt". In
Kombination mit der Kontext-Abschneidung (Problem B) und dem fehlenden Hard-Gate (Problem A)
ist dies der erste Versagenspunkt in der Kette.

### 5.4 Korrektur-Ansatz

```python
system_prompt=(
    "You are a quality assurance agent. Evaluate answers critically and objectively.\n"
    "IMPORTANT: For factual_grounding, score BELOW 0.4 if any claim in the answer "
    "cannot be directly verified in the provided tool outputs. "
    "Score 0.0–0.2 if critical facts (numbers, IDs, names, ports, file paths) "
    "are not present verbatim in the tool outputs. "
    "Do not give the benefit of the doubt for factual claims."
),
```

Diese Ergänzung instruiert das LLM mit einer Zero-Tolerance-Direktive für unverifiable Fakten.

---

## 6. Implementierungsplan Problem A

### 5.1 Schritt 1 – `ReflectionVerdict` Dataclass erweitern

**Datei:** `backend/app/services/reflection_service.py`, Zeilen 9–17

**Vorher:**
```python
@dataclass(frozen=True)
class ReflectionVerdict:
    score: float
    goal_alignment: float
    completeness: float
    factual_grounding: float
    issues: list[str]
    suggested_fix: str | None
    should_retry: bool
```

**Nachher:**
```python
@dataclass(frozen=True)
class ReflectionVerdict:
    score: float
    goal_alignment: float
    completeness: float
    factual_grounding: float
    issues: list[str]
    suggested_fix: str | None
    should_retry: bool
    hard_factual_fail: bool = False   # True wenn factual_grounding < hard_min, unabhängig von score
```

Das Feld `hard_factual_fail` ist für Observability unverzichtbar – nur so können Monitoring,
Tests und Lifecycle-Events den Unterschied erkennen zwischen "Score zu niedrig" und
"Factual Grounding hard-gefailed".

### 5.2 Schritt 2 – `ReflectionService.__init__` erweitern

**Datei:** `backend/app/services/reflection_service.py`, Zeilen 20–22

**Vorher:**
```python
class ReflectionService:
    def __init__(self, client: LlmClient, threshold: float = 0.6):
        self.client = client
        self.threshold = max(0.0, min(1.0, float(threshold)))
```

**Nachher:**
```python
class ReflectionService:
    def __init__(
        self,
        client: LlmClient,
        threshold: float = 0.6,
        factual_grounding_hard_min: float = 0.4,
    ):
        self.client = client
        self.threshold = max(0.0, min(1.0, float(threshold)))
        self.factual_grounding_hard_min = max(0.0, min(1.0, float(factual_grounding_hard_min)))
```

Beide Parameter werden geclampt auf `[0.0, 1.0]`, konsistent mit `threshold`.

### 5.3 Schritt 3 – `_parse_verdict()` Hard-Gate einbauen

**Datei:** `backend/app/services/reflection_service.py`, Zeilen 107–150

**Vorher (letzter Teil der Methode):**
```python
        return ReflectionVerdict(
            score=score,
            goal_alignment=goal_alignment,
            completeness=completeness,
            factual_grounding=factual_grounding,
            issues=issues,
            suggested_fix=suggested_fix,
            should_retry=score < self.threshold,
        )
```

**Nachher:**
```python
        hard_factual_fail = factual_grounding < self.factual_grounding_hard_min
        return ReflectionVerdict(
            score=score,
            goal_alignment=goal_alignment,
            completeness=completeness,
            factual_grounding=factual_grounding,
            issues=issues,
            suggested_fix=suggested_fix,
            should_retry=(score < self.threshold) or hard_factual_fail,
            hard_factual_fail=hard_factual_fail,
        )
```

**Achtung:** Der Fallback-Pfad bei unparsebarem JSON muss ebenfalls das neue Feld setzen:

**Aktueller Fallback (Zeilen 96–106):**
```python
        if payload is None:
            fallback_issues = ["Unable to parse reflection verdict from model output."]
            return ReflectionVerdict(
                score=0.0,
                goal_alignment=0.0,
                completeness=0.0,
                factual_grounding=0.0,
                issues=fallback_issues,
                suggested_fix=None,
                should_retry=True,
            )
```

**Nachher:**
```python
        if payload is None:
            fallback_issues = ["Unable to parse reflection verdict from model output."]
            return ReflectionVerdict(
                score=0.0,
                goal_alignment=0.0,
                completeness=0.0,
                factual_grounding=0.0,
                issues=fallback_issues,
                suggested_fix=None,
                should_retry=True,
                hard_factual_fail=True,   # 0.0 < jeder sinnvolle hard_min
            )
```

### 5.4 Schritt 4 – `agent.py` konstruiert `ReflectionService` mit Config-Wert

**Datei:** `backend/app/agent.py`, Zeilen 180–181 und 316–317

Beide `ReflectionService(...)` Konstruktor-Aufrufe werden erweitert:

**Vorher:**
```python
self._reflection_service = (
    ReflectionService(client=self.client, threshold=settings.reflection_threshold)
```

**Nachher:**
```python
self._reflection_service = (
    ReflectionService(
        client=self.client,
        threshold=settings.reflection_threshold,
        factual_grounding_hard_min=settings.reflection_factual_grounding_hard_min,
    )
```

### 5.5 Schritt 5 – Lifecycle-Event `reflection_completed` um `hard_factual_fail` erweitern

**Datei:** `backend/app/agent.py`, Zeilen 1049–1053

**Vorher:**
```python
details={
    "pass": reflection_pass + 1,
    "score": verdict.score,
    "goal_alignment": verdict.goal_alignment,
    "completeness": verdict.completeness,
    "issues": verdict.issues[:3],
    "should_retry": verdict.should_retry,
},
```

**Nachher:**
```python
details={
    "pass": reflection_pass + 1,
    "score": verdict.score,
    "goal_alignment": verdict.goal_alignment,
    "completeness": verdict.completeness,
    "factual_grounding": verdict.factual_grounding,
    "issues": verdict.issues[:3],
    "should_retry": verdict.should_retry,
    "hard_factual_fail": verdict.hard_factual_fail,
},
```

Hinweis: `factual_grounding` war bisher nicht im Lifecycle-Event enthalten – das ist ein
weiterer Blind-Spot, der mit diesem Schritt behoben wird. Monitoring, Benchmarks und
Frontend können jetzt reagieren.

---

## 7. Implementierungsplan Problem B

### 6.1 Schritt 1 – `ReflectionService.__init__` Prompt-Limits aufnehmen

**Datei:** `backend/app/services/reflection_service.py`

**Erweitern des Konstruktors** (Folge-Erweiterung aus 5.2):

```python
class ReflectionService:
    def __init__(
        self,
        client: LlmClient,
        threshold: float = 0.6,
        factual_grounding_hard_min: float = 0.4,
        tool_results_max_chars: int = 8000,
        plan_max_chars: int = 2000,
    ):
        self.client = client
        self.threshold = max(0.0, min(1.0, float(threshold)))
        self.factual_grounding_hard_min = max(0.0, min(1.0, float(factual_grounding_hard_min)))
        self.tool_results_max_chars = max(100, int(tool_results_max_chars))
        self.plan_max_chars = max(100, int(plan_max_chars))
```

Minimum-Clamping auf 100 Zeichen verhindert versehentliche Nullwerte.

### 6.2 Schritt 2 – `_build_reflection_prompt()` konfigurierbare Limits verwenden

**Datei:** `backend/app/services/reflection_service.py`, Methode `_build_reflection_prompt()`

**Vorher:**
```python
        f"Plan: {plan_text[:500]}\n"
        f"Tool outputs: {tool_results[:1000]}\n"
```

**Nachher:**
```python
        f"Plan: {plan_text[:self.plan_max_chars]}\n"
        f"Tool outputs: {tool_results[:self.tool_results_max_chars]}\n"
```

Das ist eine minimale, risikoarme Änderung – nur die Slice-Grenze ändert sich.

### 6.3 Schritt 3 – `agent.py` übergibt neue Werte

**Datei:** `backend/app/agent.py`, beide `ReflectionService(...)` Aufrufe

**Final vollständiger Konstruktor-Aufruf:**
```python
self._reflection_service = (
    ReflectionService(
        client=self.client,
        threshold=settings.reflection_threshold,
        factual_grounding_hard_min=settings.reflection_factual_grounding_hard_min,
        tool_results_max_chars=settings.reflection_tool_results_max_chars,
        plan_max_chars=settings.reflection_plan_max_chars,
    )
```

---

## 8. Implementierungsplan Problem C

### 8.1 Schritt 1 – `reflect()` System-Prompt erweitern

**Datei:** `backend/app/services/reflection_service.py`, Methode `reflect()`, Zeilen 42–49.

**Vorher:**
```python
raw_verdict = await self.client.complete_chat(
    system_prompt="You are a quality assurance agent. Evaluate answers critically and objectively.",
    user_prompt=reflection_prompt,
    model=model,
    temperature=0.1,
)
```

**Nachher:**
```python
raw_verdict = await self.client.complete_chat(
    system_prompt=(
        "You are a quality assurance agent. Evaluate answers critically and objectively.\n"
        "IMPORTANT: For factual_grounding, score BELOW 0.4 if any claim in the answer "
        "cannot be directly verified in the provided tool outputs. "
        "Score 0.0–0.2 if critical facts (numbers, IDs, names, ports, file paths) "
        "are not present verbatim in the tool outputs. "
        "Do not give the benefit of the doubt for factual claims."
    ),
    user_prompt=reflection_prompt,
    model=model,
    temperature=0.1,
)
```

Dieser Schritt erfordert keine Config-Variable, keine Änderung an Dataclasses und kein
Update von `agent.py`. Er ist vollständig in `_build_reflection_prompt()` isoliert und
hat null Abhängigkeiten zu den anderen Schritten – er kann als Erstes implementiert werden.

---

## 9. Config-Erweiterungen

**Datei:** `backend/app/config.py`, nach Zeile 643 (nach `reflection_threshold`)

Aktuell:
```python
reflection_enabled: bool = _parse_bool_env("REFLECTION_ENABLED", True)
reflection_threshold: float = max(0.0, min(1.0, float(os.getenv("REFLECTION_THRESHOLD", "0.6"))))
```

Erweitern auf:
```python
reflection_enabled: bool = _parse_bool_env("REFLECTION_ENABLED", True)
reflection_threshold: float = max(0.0, min(1.0, float(os.getenv("REFLECTION_THRESHOLD", "0.6"))))
reflection_factual_grounding_hard_min: float = max(
    0.0, min(1.0, float(os.getenv("REFLECTION_FACTUAL_GROUNDING_HARD_MIN", "0.4")))
)
reflection_tool_results_max_chars: int = max(
    100, int(os.getenv("REFLECTION_TOOL_RESULTS_MAX_CHARS", "8000"))
)
reflection_plan_max_chars: int = max(
    100, int(os.getenv("REFLECTION_PLAN_MAX_CHARS", "2000"))
)
```

### Übersicht aller neuen Umgebungsvariablen

| Variable | Default | Beschreibung |
|---|---|---|
| `REFLECTION_FACTUAL_GROUNDING_HARD_MIN` | `0.4` | Hard-Gate: Schwelle, unterhalb derer `factual_grounding` immer `should_retry=True` erzwingt, unabhängig vom Gesamtscore |
| `REFLECTION_TOOL_RESULTS_MAX_CHARS` | `8000` | Maximale Zeichen für `tool_results` im Reflection-Prompt |
| `REFLECTION_PLAN_MAX_CHARS` | `2000` | Maximale Zeichen für `plan_text` im Reflection-Prompt |

**Um den Hard-Gate zu deaktivieren:** `REFLECTION_FACTUAL_GROUNDING_HARD_MIN=0.0`  
**Um auf altes Verhalten zurückzufallen:** Beide `REFLECTION_*_MAX_CHARS` auf 1000/500 setzen.

---

## 10. Observability-Erweiterungen (Lifecycle-Events)

### 10.1 `reflection_completed` – neue Felder

Nach den Änderungen enthält das Lifecycle-Event:

```json
{
  "type": "lifecycle",
  "stage": "reflection_completed",
  "details": {
    "pass": 1,
    "score": 0.6333,
    "goal_alignment": 0.8,
    "completeness": 0.7,
    "factual_grounding": 0.3,
    "issues": ["PIDs not found in tool output", "..."],
    "should_retry": true,
    "hard_factual_fail": true
  }
}
```

Neu gegenüber aktuell:
- `factual_grounding` (war bisher nicht enthalten!)
- `hard_factual_fail` (neu)

### 10.2 Monitoring-Nutzung

Mit diesen Feldern können Monitoring-Dashboards und Alerts auf `hard_factual_fail: true`
filtern – das ist ein direktes Signal für einen Halluzinationsversuch, den der Agent erkannt
hat, der aber durch das Scoring-System durchgerutscht wäre.

---

## 11. Teststrategie

### 11.1 Unit-Tests für `ReflectionService` – Datei `backend/tests/test_reflection_service.py`

Alle neuen Tests ergänzen die bestehende Datei. Die `_FakeClient`-Klasse ist bereits definiert und muss nicht erneut hinzugefügt werden. Import-Header der Datei bleibt unverändert:
```python
from __future__ import annotations
import asyncio
from app.services.reflection_service import ReflectionService
```

#### Test 1 – Hard-Gate schlägt an bei FG < hard_min, Score > threshold

```python
def test_reflection_hard_factual_gate_triggers_retry_despite_high_score() -> None:
    """
    Score liegt ÜBER dem Threshold (0.6), aber factual_grounding < hard_min (0.4).
    Erwartet: should_retry=True, hard_factual_fail=True.
    Dies ist exakt der logfile-Bug: GA=0.8, C=0.7, FG=0.3 → score=0.60 > 0.6?... nein.
    Präzisere Variante: GA=0.9, C=0.8, FG=0.35 → score=0.683 > 0.6.
    """
    service = ReflectionService(
        client=_FakeClient(
            '{"goal_alignment": 0.9, "completeness": 0.8, '
            '"factual_grounding": 0.35, "issues": ["PIDs not in netstat output"], '
            '"suggested_fix": "Cite actual PIDs from tool result"}'
        ),
        threshold=0.6,
        factual_grounding_hard_min=0.4,
    )
    verdict = asyncio.run(
        service.reflect(
            user_message="Which processes are listening on port 80?",
            plan_text="Run netstat and extract PIDs.",
            tool_results="Proto  Local Address  State\nTCP  0.0.0.0:443  ESTABLISHED",
            final_answer="Port 80 is used by PID 12345 (nginx).",
        )
    )
    expected_score = (0.9 + 0.8 + 0.35) / 3   # ≈ 0.683 > threshold 0.6
    assert abs(verdict.score - expected_score) < 0.001
    assert verdict.score > 0.6                 # Score allein würde NICHT retry
    assert verdict.factual_grounding == 0.35
    assert verdict.hard_factual_fail is True
    assert verdict.should_retry is True        # Hard-Gate erzwingt Retry
```

#### Test 2 – Kein Hard-Gate wenn FG >= hard_min und Score > threshold

```python
def test_reflection_no_false_positive_when_fg_above_hard_min() -> None:
    """
    FG ist 0.5 (> hard_min=0.4) und Score > 0.6 → kein Retry erwartet.
    """
    service = ReflectionService(
        client=_FakeClient(
            '{"goal_alignment": 0.8, "completeness": 0.7, '
            '"factual_grounding": 0.5, "issues": [], "suggested_fix": null}'
        ),
        threshold=0.6,
        factual_grounding_hard_min=0.4,
    )
    verdict = asyncio.run(
        service.reflect(
            user_message="List running processes",
            plan_text="Run tasklist",
            tool_results="svchost.exe  PID 1234",
            final_answer="Svchost is running with PID 1234.",
        )
    )
    assert verdict.hard_factual_fail is False
    assert verdict.should_retry is False
```

#### Test 3 – Hard-Gate deaktivierbar (hard_min=0.0)

```python
def test_reflection_hard_gate_disabled_when_hard_min_zero() -> None:
    """
    Mit hard_min=0.0 soll der Hard-Gate nie auslösen.
    """
    service = ReflectionService(
        client=_FakeClient(
            '{"goal_alignment": 0.9, "completeness": 0.9, '
            '"factual_grounding": 0.0, "issues": [], "suggested_fix": null}'
        ),
        threshold=0.6,
        factual_grounding_hard_min=0.0,  # deaktiviert
    )
    verdict = service._parse_verdict(
        '{"goal_alignment": 0.9, "completeness": 0.9, '
        '"factual_grounding": 0.0, "issues": [], "suggested_fix": null}'
    )
    assert verdict.hard_factual_fail is False
    assert verdict.should_retry is False   # score=0.6 == threshold, nicht < threshold
```

#### Test 4 – `tool_results_max_chars` wird respektiert

```python
def test_reflection_prompt_uses_configured_tool_results_max_chars() -> None:
    """
    Prüft, dass _build_reflection_prompt() tool_results auf tool_results_max_chars kürzt.
    """
    service = ReflectionService(
        client=_FakeClient("{}"),
        tool_results_max_chars=50,
    )
    long_tool_results = "A" * 200
    prompt = service._build_reflection_prompt(
        user_message="test",
        plan_text="plan",
        tool_results=long_tool_results,
        final_answer="answer",
    )
    # Der Prompt darf maximal 50 'A's enthalten
    assert "A" * 51 not in prompt
    assert "A" * 50 in prompt
```

#### Test 5 – `plan_max_chars` wird respektiert

```python
def test_reflection_prompt_uses_configured_plan_max_chars() -> None:
    service = ReflectionService(
        client=_FakeClient("{}"),
        plan_max_chars=30,
    )
    long_plan = "P" * 100
    prompt = service._build_reflection_prompt(
        user_message="test",
        plan_text=long_plan,
        tool_results="output",
        final_answer="answer",
    )
    assert "P" * 31 not in prompt
    assert "P" * 30 in prompt
```

#### Test 6 – Fallback-Verdict enthält `hard_factual_fail=True`

```python
def test_reflection_fallback_verdict_has_hard_factual_fail_true() -> None:
    service = ReflectionService(client=_FakeClient("not-json"), threshold=0.6)
    verdict = service._parse_verdict("not-json")
    assert verdict.hard_factual_fail is True
    assert verdict.should_retry is True
```

#### Test 7 – Regression: Bestehender Test noch grün

Der bestehende Test `test_reflection_service_parses_json_verdict_and_threshold` testet
`FG=0.3, threshold=0.7` → `score=0.6 < 0.7` → `should_retry=True`.
Das bleibt korrekt, weil der Score auch unterhalb des Thresholds liegt.
**Kein Anpassungsbedarf.**

### 11.2 Integration-Test `test_reflection_loop.py`

Der bestehende Test `test_reflection_loop_retries_synthesis_when_score_is_low` verwendet
eine `_FakeReflectionService`—Klasse und setzt `should_retry` self direkt.
**Kein Anpassungsbedarf**, solange `ReflectionVerdict` das neue Feld `hard_factual_fail`
als Default `False` hat.

### 11.3 Neuer Integration-Test – Hard-Gate löst Retry aus

**Datei:** `backend/tests/test_reflection_loop.py`, neuer Test am Ende.

```python
def test_reflection_loop_hard_factual_fail_forces_retry(monkeypatch) -> None:
    """
    Zeigt: Hard-Gate löst Retry aus, obwohl score > threshold (0.6).
    Szenario: Agent nennt PIDs, die nicht in den Tool-Outputs stehen.
    """
    _set_local_runtime()
    # ... (Setup identisch zu bestehendem Test)

    class _FakeReflectionService:
        def __init__(self) -> None:
            self.calls = 0

        async def reflect(self, *, user_message, plan_text, tool_results, final_answer, model=None):
            self.calls += 1
            if self.calls == 1:
                # Score 0.683 > threshold 0.6, ABER factual_grounding=0.35 < hard_min=0.4
                return ReflectionVerdict(
                    score=(0.9 + 0.8 + 0.35) / 3,
                    goal_alignment=0.9,
                    completeness=0.8,
                    factual_grounding=0.35,
                    issues=["PIDs mentioned are not present in netstat output"],
                    suggested_fix="Use only PIDs from tool output.",
                    should_retry=True,       # Hard-Gate aktiv
                    hard_factual_fail=True,
                )
            return ReflectionVerdict(
                score=0.95,
                goal_alignment=0.95,
                completeness=0.95,
                factual_grounding=0.95,
                issues=[],
                suggested_fix=None,
                should_retry=False,
                hard_factual_fail=False,
            )

    # ... assert reflection_service.calls == 2
    # Assert: reflection_completed pass=1 hat hard_factual_fail=True im event
    assert any(
        evt.get("stage") == "reflection_completed"
        and evt.get("details", {}).get("hard_factual_fail") is True
        for evt in events
    )
```

---

## 12. Reihenfolge & Abhängigkeiten

```
Schritt 0:  reflection_service.py
              reflect()  → System-Prompt um FG-Direktive erweitern (Problem C)
              → Isoliert, keine Abhängigkeiten, sofort implementierbar
            ↓
Schritt 1:  config.py
              → 3 neue Config-Felder nach reflection_threshold
            ↓
Schritt 2:  reflection_service.py
              ReflectionVerdict   → hard_factual_fail: bool = False
              __init__            → 4 neue Parameter + Consistency-Warning
              _parse_verdict()    → Hard-Gate-Logik (Problem A)
              _build_prompt()     → self.tool_results_max_chars / plan_max_chars (Problem B)
            ↓
Schritt 3:  agent.py
              Beide ReflectionService()-Aufrufe  → 4 neue kwargs
              reflection_completed-Event         → +factual_grounding, +hard_factual_fail
            ↓
Schritt 4:  Tests
              test_reflection_service.py         → 6 neue Unit-Tests
              test_reflection_loop.py            → 1 neuer Integration-Test
            ↓
Schritt 5:  Verifizierung
              pytest backend/tests/test_reflection_service.py -v
              pytest backend/tests/test_reflection_loop.py -v
              pytest backend/tests/ -q --maxfail=1
```

**Abhängigkeiten:**
- Schritt 0 (Problem C) hat **keine** Abhängigkeiten und kann jederzeit zuerst eingecheckt werden
- Schritt 1 muss vor Schritt 3 abgeschlossen sein
- Schritt 2 muss vollständig vor Schritt 4 fertig sein
- Schritt 3 kann parallel zu Schritt 2 begonnen werden, sobald Schritt 1 fertig ist

---

## 13. Risiken & Edge-Cases

### 13.1 Erhöhte Retry-Rate

**Risiko:** Mit Hard-Gate werden mehr Reflection-Passes ausgelöst. Bei `reflection_passes=2`
und `factual_grounding_hard_min=0.4` könnte jede Antwort auf Basis von Daten aus dem
Modell-Wissen (z.B. allgemeine Netzwerk-Erklärungen) den Gate auslösen, selbst wenn das
korrekt ist.

**Minderung:**
1. `factual_grounding_hard_min=0.4` ist bewusst niedrig gewählt – ein LLM-Richter, der
   FG auf `0.39` setzt, ist sehr unsicher über die Faktizität. Das ist ein legitimer Retry-Grund.
2. Nach dem Retry hat der Synthesizer-LLM den `[REFLECTION FEEDBACK]` im Kontext und wird
   gezielt auf Faktentreue hingewiesen. Die Retry-Antwort wird typischerweise besser.
3. Konfigurierbar: Strenge kann über `REFLECTION_FACTUAL_GROUNDING_HARD_MIN` angepasst werden.

### 13.2 Tool-Results-Parsing im Reflection-Prompt nach Erweiterung auf 8000 Zeichen

**Risiko:** Ein sehr langer Prompt könnte das Reflection-LLM in kleineren Models (z.B. `llama3.2:3b`)
an Context-Limits stoßen lassen.

**Minderung:**
- 8000 Zeichen ≈ 2000 Tokens – unkritisch für `llama3.3:70b`
- Für kleinere Models kann `REFLECTION_TOOL_RESULTS_MAX_CHARS=2000` gesetzt werden
- Konfiguration ist pro-Deployment möglich, kein Code-Eingriff nötig

### 13.3 Reflection-LLM bewertet mit vollem Kontext möglicherweise FG niedriger

**Risiko (Paradox):** Mit mehr Context könnte das Reflection-LLM erkennen, dass Antworten
mehr Fakten beinhalten als der Output belegt → FG sinkt → mehr Retries.

**Bewertung:** Das ist das korrekte Verhalten. Wenn der Agent mehr Fakten behauptet als die
Tool-Outputs belegen, ist das eine Halluzination, die Retry verdient.

### 13.4 Bestehende Tests für `ReflectionVerdict`

`ReflectionVerdict` ist ein `frozen=True` Dataclass. Das neue Feld `hard_factual_fail: bool = False`
hat einen Default-Wert – daher sind alle bestehenden Konstruktor-Aufrufe ohne das Feld
weiterhin valide. **Keine Breaking Changes.**

**Ausnahme:** Wenn irgendwo `ReflectionVerdict(...)` mit den Feldern als Positional-Arguments
aufgerufen wird, bräche das. Suche nach Vorkommen:
- `test_reflection_loop.py`: Verwendet `ReflectionVerdict(...)` mit Keyword-Arguments → ✅ OK
- `reflection_service.py`: Intern, ebenfalls Keyword-Arguments → ✅ OK

### 13.5 `factual_grounding` fehlt im Reflection-JSON des LLMs

**Risiko:** Das Reflection-LLM liefert kein `factual_grounding`-Feld zurück.

**Aktuelles Verhalten:** `self._clamp_score(payload.get("factual_grounding"))` → `_clamp_score(None)` →
`float(None)` → `TypeError` → `return 0.0`.

**Folge mit Hard-Gate:** `factual_grounding=0.0 < 0.4` → `hard_factual_fail=True` → Retry.
Das ist **korrekt und defensiv**: Wenn FG nicht beurteilbar, lieber Retry.

**Alternative:** Explizit auf Missing-Key prüfen und `factual_grounding=0.5` (neutral) setzen.
Hier empfehlen wir **kein** neutrales Fallback – `0.0` als Fallback ist sicherer, da
fehlende Beurteilung nicht als "Grounding OK" interpretiert werden soll.

### 13.6 Hard-Gate und Reflection-Threshold im Verhältnis

Wenn `factual_grounding_hard_min > threshold` gesetzt wird (z.B. `hard_min=0.7, threshold=0.6`),
würde der Hard-Gate bei Werten von `FG=0.61` auslösen, obwohl FG über dem Threshold liegt.
Das ist semantisch inkonsistent.

**Empfehlung:** In `__init__` eine Warning loggen wenn `factual_grounding_hard_min >= threshold`:

```python
if self.factual_grounding_hard_min >= self.threshold:
    import warnings
    warnings.warn(
        f"ReflectionService: factual_grounding_hard_min ({self.factual_grounding_hard_min}) "
        f">= threshold ({self.threshold}). Hard gate is more restrictive than threshold.",
        stacklevel=2,
    )
```

---

## 14. Deployment-Hinweise

### 14.1 Keine Migration nötig

Beide Änderungen sind vollständig rückwärtskompatibel:
- Neue Config-Felder haben Defaults → kein `.env`-Eingriff nötig
- `ReflectionVerdict.hard_factual_fail` hat Default `False` → keine Breaking Changes in Tests
- Verhalten beim alten Stand: `REFLECTION_FACTUAL_GROUNDING_HARD_MIN=0.0` + alte Char-Limits

### 14.2 Empfohlene `.env`-Konfiguration für Produktion

```dotenv
# Reflection Quality Hardening (Issue-0008)
REFLECTION_FACTUAL_GROUNDING_HARD_MIN=0.4
REFLECTION_TOOL_RESULTS_MAX_CHARS=8000
REFLECTION_PLAN_MAX_CHARS=2000
```

### 14.3 Rollback

Um auf altes Verhalten zurückzufallen ohne Code-Deployment:

```dotenv
REFLECTION_FACTUAL_GROUNDING_HARD_MIN=0.0
REFLECTION_TOOL_RESULTS_MAX_CHARS=1000
REFLECTION_PLAN_MAX_CHARS=500
```

### 14.4 Benchmark nach Deployment

Es empfiehlt sich, nach Deployment die Benchmark-Suite zu fahren und insbesondere
`should_retry`-Rate und `hard_factual_fail`-Rate in den Monitoring-Logs zu beobachten.
Eine Baseline vor dem Deployment aus `backend/monitoring/` aufzeichnen.

---

## Änderungsübersicht (alle betroffenen Dateien)

| Datei | Art | Problem | Beschreibung |
|---|---|---|---|
| `backend/app/config.py` | Erweiterung | A+B | 3 neue Config-Felder nach `reflection_threshold` |
| `backend/app/services/reflection_service.py` | Erweiterung | A+B+C | `ReflectionVerdict.hard_factual_fail`; `__init__`-Parameter; `_parse_verdict()` Hard-Gate; `_build_reflection_prompt()` konfigurierbare Limits; `reflect()` System-Prompt |
| `backend/app/agent.py` | Erweiterung | A+B | Beide `ReflectionService(...)`-Aufrufe; `reflection_completed`-Event `+factual_grounding`, `+hard_factual_fail` |
| `backend/tests/test_reflection_service.py` | Tests | A+B | 6 neue Unit-Tests |
| `backend/tests/test_reflection_loop.py` | Tests | A | 1 neuer Integration-Test |

**Gesamtaufwand:** ~90 Zeilen Code + ~130 Zeilen Tests. Kein Refactoring größerer Strukturen.

---

## 15. Acceptance Criteria Checkliste

### Funktionale Korrektheit (Problem A – Hard-Gate)

- [ ] `FG=0.35, GA=0.9, C=0.8, threshold=0.6, hard_min=0.4` → `should_retry=True, hard_factual_fail=True`
- [ ] `FG=0.5, GA=0.9, C=0.8, threshold=0.6, hard_min=0.4` → `should_retry=False, hard_factual_fail=False`
- [ ] `FG=0.0, hard_min=0.0` (Gate deaktiviert) → `hard_factual_fail=False`
- [ ] Unparseable LLM-Output → `hard_factual_fail=True, should_retry=True`

### Funktionale Korrektheit (Problem B – Prompt-Kontext)

- [ ] `tool_results` mit 200 Zeichen, `tool_results_max_chars=50` → Prompt enthält max. 50 Zeichen des Tool-Results-Slots
- [ ] `plan_text` mit 100 Zeichen, `plan_max_chars=30` → Prompt enthält max. 30 Plan-Zeichen
- [ ] Default-Betrieb ohne Env-Vars → effektiv `tool_results_max_chars=8000`, `plan_max_chars=2000`

### Funktionale Korrektheit (Problem C – System-Prompt)

- [ ] `reflect()` übergibt System-Prompt der explizit `factual_grounding BELOW 0.4` für unverifiable Fakten nennt
- [ ] System-Prompt enthält den Begriff `verbatim in the tool outputs`

### Observability

- [ ] `reflection_completed`-Lifecycle-Event enthält `factual_grounding`-Feld
- [ ] `reflection_completed`-Lifecycle-Event enthält `hard_factual_fail`-Feld
- [ ] `hard_factual_fail=True` im Event wenn Hard-Gate ausgelöst hat

### Config

- [ ] `REFLECTION_FACTUAL_GROUNDING_HARD_MIN=0.5` wirkt sich korrekt auf Hard-Gate aus
- [ ] `REFLECTION_TOOL_RESULTS_MAX_CHARS=2000` begrenzt Tool-Results im Prompt auf 2000 Zeichen
- [ ] `REFLECTION_PLAN_MAX_CHARS=500` entspricht altem Verhalten

### Tests

- [ ] `pytest backend/tests/test_reflection_service.py -v` → alle Tests grün (inkl. 6 neue)
- [ ] `pytest backend/tests/test_reflection_loop.py -v` → alle Tests grün (inkl. 1 neuer)
- [ ] `pytest backend/tests/ -q --maxfail=1` → gesamte Testsuite grün

### Backward Compatibility

- [ ] `ReflectionVerdict(...)`-Aufrufe ohne `hard_factual_fail` weiterhin valide (Default `False`)
- [ ] `ReflectionService(client, threshold)` ohne neue Parameter weiterhin valide
- [ ] Config ohne neue Env-Vars → korrekte Default-Werte, kein `KeyError` / `AttributeError`

---

**Drei Sicherheitsebenen nach vollständiger Implementierung:**

```
Ebene 1 (Problem C): System-Prompt mit Zero-Tolerance-Direktive
  → LLM wird explizit instruiert, FG < 0.4 zu setzen wenn Belege fehlen

Ebene 2 (Problem B): Voller Kontext (8× mehr Zeichen im Prompt)
  → LLM kann tatsächlich prüfen ob Fakten im Tool-Output vorhanden sind

Ebene 3 (Problem A): Hard-Gate im Code
  → Selbst wenn LLM FG falsch einschätzt, fängt der Code es ab
```
