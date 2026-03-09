# Agent Quality Refactoring Plan

> **Ziel:** Antwortqualität des Agents auf das Niveau von OpenClaw bringen.
> **Grundsatz:** Architektur, Toolchain und Pipeline bleiben — nur gezielte Lücken schließen.
> **Stand:** 9. März 2026 — **ALLE 5 PUNKTE IMPLEMENTIERT**
> **Quelle:** Side-by-side Code-Analyse beider Repos

---

## Legende

- ✅ = erledigt
- 🔄 = in Arbeit
- ❌ = offen

---

## Übersicht der Schwachstellen

| # | Problem | Schwere | Aufwand | Status |
|---|---------|---------|---------|--------|
| 1 | Kein Datum/Uhrzeit im System Prompt | **P0 Kritisch** | Klein (~20 LOC) | ✅ |
| 2 | Keine "search before answering"-Regel | **P0 Kritisch** | Klein (~30 LOC Prompt) | ✅ |
| 3 | Kein External Content Security Wrapping | **P1 Wichtig** | Mittel (~80 LOC) | ✅ |
| 4 | Primitive Compaction (Trunkierung statt Summarisierung) | **P1 Wichtig** | Groß (neuer Service) | ✅ |
| 5 | Statisches Reasoning-Level | **P2 Moderat** | Mittel | ✅ |

---

## Sprint 1 — Die Quick Wins (P0)

### 1. Datum & Uhrzeit im System Prompt

**Problem:**
Der Agent weiß nicht, welches Jahr/Datum es ist. Auf die Frage "Was ist die neueste GPT-Version?"
antwortet er mit "GPT-4o" — weil er auf seinen Training-Cutoff zurückfällt.

**Ist-Zustand:**
- `build_unified_system_prompt()` in `agent_runner.py` hat keinen Datum-Parameter
- `_build_initial_messages()` injiziert kein Datum in den System Prompt
- `datetime` wird nur intern für Timestamps verwendet (Memory, Events) — nie dem LLM mitgeteilt
- `PlatformInfo.summary()` enthält OS/Shell/Runtime — **kein Datum**

**Soll-Zustand:**
- Der System Prompt enthält immer eine `## Current date & time`-Sektion
- Format: `Current date: Monday, 9 March 2026, 14:32 CET`
- Timezone wird aus System-Locale gelesen oder aus Config (`USER_TIMEZONE` env var)
- Die Sektion wird bei jedem Request dynamisch generiert (nicht gecacht)

**Betroffene Dateien:**
- `backend/app/agent_runner.py` → `build_unified_system_prompt()` bekommt `current_datetime` Parameter
- `backend/app/agent_runner.py` → `_build_initial_messages()` oder Runner-Init injiziert das Datum
- `backend/app/config.py` → optional: `user_timezone: str` Setting

**Dos:**
- ✅ `datetime.now(tz)` mit expliziter Timezone verwenden — nie naive datetimes
- ✅ Format muss für das LLM eindeutig sein: Wochentag + volles Datum + Uhrzeit + Timezone
- ✅ Bei jedem Request frisch generieren (nicht aus Cache)
- ✅ Timezone aus System-Locale lesen als Default, überschreibbar per `USER_TIMEZONE` env var
- ✅ In Tests: Freeze-time verwenden (`freezegun` oder `unittest.mock.patch`)

**Don'ts:**
- ❌ Nicht nur das Datum ohne Uhrzeit injizieren — LLM braucht beides
- ❌ Nicht die Timezone hardcoden — User können in verschiedenen Zeitzonen sein
- ❌ Nicht `time.time()` oder Unix-Timestamps — LLM versteht menschliche Formate besser
- ❌ Kein `datetime.now()` ohne Timezone (naive datetime) — führt zu falschen Ergebnissen in Containern

**Akzeptanzkriterien:**
1. Agent antwortet auf "Welches Datum ist heute?" korrekt ohne Tool-Nutzung
2. Agent antwortet auf "Was ist die neueste GPT-Version?" mit einem Verweis auf sein Wissens-Cutoff ODER nutzt `web_search`
3. System Prompt enthält aktuelle Zeit im Format `Weekday, DD Month YYYY, HH:MM TZ`
4. Unit-Test: `build_unified_system_prompt()` mit `current_datetime` Parameter → Sektion vorhanden
5. Unit-Test: Timezone-Fallback (kein env var → System-Locale)

---

### 2. "Search before answering"-Regel im System Prompt

**Problem:**
Der Agent hat `web_search` und `web_fetch` als Tools — aber der System Prompt sagt ihm nie,
dass er sie **proaktiv** nutzen soll. Das LLM entscheidet allein basierend auf Tool-Descriptions,
ob es sucht — und entscheidet sich meist dagegen, weil es "schon weiß" (aus Training-Cutoff).

**Ist-Zustand:**
- `build_unified_system_prompt()` hat eine generische "How you work"-Sektion
- Tool-Descriptions in `tool_catalog.py` beschreiben die Tools, geben aber keine Nutzungs-Policy
- Der Agent kann `web_search` aufrufen, tut es aber fast nie von sich aus
- `tool_routing.md` hat eine Referenz für `web_search` — aber nur "when to use / when not"

**Soll-Zustand:**
- Neue Sektion `## When to search` im System Prompt
- Explizite Regeln wann der Agent `web_search` benutzen MUSS
- Explizite Regeln wann der Agent sich auf Modellwissen verlassen DARF

**Betroffene Dateien:**
- `backend/app/agent_runner.py` → Neue Sektion in `build_unified_system_prompt()`
- ODER `backend/app/prompts/agent_rules.md` → Neue Sektion (bevorzugt, da dort alle Regeln sind)
- `backend/app/config.py` → Ggf. Prompt-Default anpassen

**Prompt-Text (Vorschlag):**

```markdown
## When to search the web

Use `web_search` BEFORE answering when the user's question involves:
- Current events, news, recent developments (anything after your knowledge cutoff)
- Software versions, release dates, changelogs
- Prices, availability, stock, live data
- People's current roles, recent actions, latest statements
- Regulations, laws, policies that may have changed
- Any question containing "latest", "newest", "current", "today", "recently"

You MAY answer from model knowledge when:
- The question is about well-established facts (math, physics, history before 2024)
- The question is about code syntax, language features, or algorithms
- The user explicitly says "from what you know" or "without searching"
- The question is about the current project/workspace (use file tools instead)

When in doubt: **search first, then verify against your knowledge.**
State explicitly when your answer is based on model knowledge vs. search results.
```

**Dos:**
- ✅ Regeln als harte MUST-Instruktionen formulieren — nicht als Vorschläge
- ✅ Explizite Trigger-Wörter listen, die eine Suche erzwingen ("latest", "current", etc.)
- ✅ Klare Unterscheidung: "search-pflichtig" vs. "Modellwissen OK"
- ✅ Dem LLM eine Escape-Hatch geben wenn der User explizit keine Suche will
- ✅ In `agent_rules.md` integrieren — damit es für alle Agent-Typen gilt

**Don'ts:**
- ❌ Nicht "always search" fordern — das verschwendet API-Calls bei trivialen Fragen
- ❌ Nicht die Tool-Description in `tool_catalog.py` als Ersatz verwenden — die ist für Schema, nicht Policy
- ❌ Nicht `web_search` als Pflicht bei Code-Fragen zum aktuellen Projekt einbauen — dafür gibt es `read_file`/`grep_search`
- ❌ Nicht die `tool_routing.md` duplizieren — Referenz dort, Policy in `agent_rules.md`

**Akzeptanzkriterien:**
1. Agent benutzt `web_search` bei "Was ist die neueste Version von Node.js?"
2. Agent benutzt `web_search` bei "Was ist heute passiert?"
3. Agent benutzt NICHT `web_search` bei "Was ist eine for-Schleife in Python?"
4. Agent benutzt NICHT `web_search` bei "Lies die Datei config.py"
5. Agent sagt explizit wenn eine Antwort auf Modellwissen basiert und möglicherweise veraltet ist

---

## Sprint 2 — Security & Robustheit (P1)

### 3. External Content Security Wrapping

**Problem:**
Web-Ergebnisse von `web_search` und `web_fetch` kommen unmarkiert ins Context Window.
Das LLM kann nicht unterscheiden ob Content aus dem User-Prompt, aus Tools oder von einer
externen Website stammt. Das ist sowohl ein Security-Problem (Prompt Injection via Web Content)
als auch ein Qualitätsproblem (LLM kann Quellen nicht trennen).

**Ist-Zustand:**
- `web_search` gibt Ergebnisse als Plain-Text zurück
- `web_fetch` gibt HTML→Text-Konvertierung als Plain-Text zurück
- Keine Markierung von externem Content
- Keine Prompt-Injection-Detection für Web-Inhalte
- `_sanitize_tool_output` in `context_reducer.py` strip nur Secrets — nicht Injection-Patterns

**Soll-Zustand:**
- Alle Web-Tool-Ergebnisse werden in Security-Boundary-Marker gewrapped
- Randomisierte Boundary-IDs (gegen Marker-Spoofing)
- Prompt-Injection-Detection auf Web-Inhalte (Warning-Flag, nicht Blocking)
- System Prompt erklärt dem LLM die Marker-Bedeutung

**Betroffene Dateien:**
- `backend/app/tools.py` → `web_search()` und `web_fetch()` wrappen ihre Ergebnisse
- Neues Modul: `backend/app/content_security.py` (oder in `tools.py` inline)
- `backend/app/prompts/agent_rules.md` → Sektion über External Content Marker

**Format der Marker:**

```
<<<EXTERNAL_CONTENT source="web_search" id="a4f2b8c1">>>
[Inhalt]
<<<END_EXTERNAL_CONTENT id="a4f2b8c1">>>
```

**Dos:**
- ✅ Boundary-IDs randomisiert generieren (hex, 8+ Zeichen)
- ✅ Source-Typ in den Marker aufnehmen (`web_search`, `web_fetch`, `http_request`)
- ✅ Marker im System Prompt erklären: "Content between these markers comes from external sources"
- ✅ Suspicious-Pattern-Detection als Warning (nicht blockieren — false positives möglich)
- ✅ Unit-Tests für Marker-Wrapping und Spoofing-Detection

**Don'ts:**
- ❌ Nicht blockieren wenn Suspicious Patterns gefunden werden — nur Warning im Marker
- ❌ Nicht statische Boundary-Strings verwenden — Angreifer können sie vorhersagen
- ❌ Nicht alle Tool-Outputs wrappen — nur externe Web-Quellen (nicht `read_file`, `run_command`)
- ❌ Nicht die Marker zu lang/komplex machen — kostet Tokens
- ❌ Kein Unicode-Normalisierung vergessen — Homoglyphen-Angriffe auf Marker abfangen

**Akzeptanzkriterien:**
1. `web_search` Output enthält Boundary-Marker mit randomisierter ID
2. `web_fetch` Output enthält Boundary-Marker mit randomisierter ID
3. Marker-IDs sind bei jedem Call unterschiedlich
4. Suspicious Patterns (z.B. "ignore all previous instructions") werden mit `⚠ SUSPICIOUS` markiert
5. System Prompt enthält Erklärung der Marker
6. Unit-Test: Marker-Wrapping korrekt
7. Unit-Test: Spoofed Marker im Content wird entschärft (escaped/entfernt)

---

### 4. LLM-basierte Conversation Compaction

**Problem:**
Eure `_compact_messages()` trunckiert einfach nur Text:
- Tool-Results > 500 chars → Head 200 + Tail 100
- Assistant-Msgs > 300 → Head 200 + "..."

Das zerstört Kontext. In langen Sessions verliert der Agent:
- Was der User ursprünglich wollte
- Welche Entscheidungen getroffen wurden
- Welche Dateien bereits bearbeitet wurden
- Progress bei mehrstufigen Aufgaben

**Ist-Zustand:**
- `_compact_messages()` ist rein textbasiert (string slicing)
- Trigger: nur wenn `finish_reason == "length"` (Context Overflow)
- Kein Token-Counting vor dem Overflow
- Kein Summary der gelöschten Nachrichten
- Kein Schutz für kritische Identifier (UUIDs, Pfade, etc.)

**Soll-Zustand:**
- LLM-basierte Summarisierung älterer Nachrichten
- Proaktives Token-Counting VOR dem Overflow
- Identifier-Preservation (Pfade, IDs, Hashes bleiben exakt)
- Progressive Fallback: LLM-Summary → Text-Summary → Trunkierung
- Summary wird als `[CONTEXT SUMMARY]` Message in die History eingefügt

**Betroffene Dateien:**
- `backend/app/agent_runner.py` → `_compact_messages()` ersetzt oder ergänzt
- Neuer Service: `backend/app/services/compaction_service.py`
- `backend/app/config.py` → Compaction-Settings
- `backend/app/llm_client.py` → Ggf. Token-Estimation-Methode

**Architektur:**

```
┌─────────────────────────────────────────┐
│           CompactionService              │
├──────────────────────────────────────────┤
│ estimate_tokens(messages) → int          │
│ needs_compaction(messages, limit) → bool │
│ compact(messages, budget) → messages     │
│   ├── try: llm_summarize(old_messages)   │
│   ├── fallback: text_summarize()         │
│   └── fallback: truncate() (existing)    │
│ preserve_identifiers(summary) → summary  │
└──────────────────────────────────────────┘
```

**Konstanten (Vorschlag):**

```python
COMPACTION_CHUNK_RATIO = 0.4          # 40% des Context Windows pro Chunk
COMPACTION_SAFETY_MARGIN = 1.2        # 20% Buffer für Token-Schätzungs-Ungenauigkeit
COMPACTION_OVERHEAD_TOKENS = 4096     # Reserve für Summarisierung selbst
COMPACTION_TRIGGER_RATIO = 0.85       # Compaction ab 85% Context-Auslastung
```

**Summary-Instructions (im Compaction-Prompt):**

```
Summarize the conversation above. MUST PRESERVE:
- Active tasks and their current status
- The last thing the user requested
- Decisions made and their rationale
- All file paths, UUIDs, hashes, IDs, and identifiers EXACTLY as written
- TODOs, open questions, and constraints
PRIORITIZE recent context over older history.
```

**Dos:**
- ✅ Token-Estimation via `len(text) / 4` als grobe Heuristik (oder tiktoken wenn verfügbar)
- ✅ Proaktiv compacten BEVOR Context Overflow → bessere Summaries wenn noch Budget da ist
- ✅ System-Message immer behalten (Index 0)
- ✅ Letzte N Nachrichten immer behalten (tail_keep, wie jetzt schon)
- ✅ Summary als eigene `[CONTEXT SUMMARY]` Message einfügen — nicht in System Prompt
- ✅ Progressive Fallback-Kette: LLM → Text → Trunkierung
- ✅ Retry mit Jitter bei LLM-Summary-Fehlern (max 2 Versuche)
- ✅ Identifier-Preservation prüfen (UUIDs, Pfade nicht "zusammenfassen")

**Don'ts:**
- ❌ Nicht den gesamten Kontext in einem LLM-Call zusammenfassen — Chunking verwenden
- ❌ Nicht User-Nachrichten von der Compaction ausschließen — auch die können redundant lang sein
- ❌ Nicht die aktuelle User-Nachricht compacten — nur History
- ❌ Nicht synchron auf LLM-Summary warten wenn Timeout droht — Fallback auf Text-Trunkierung
- ❌ Nicht Compaction bei jeder Nachricht triggern — nur wenn Token-Budget > Schwelle
- ❌ Nicht das Summary-Modell hardcoden — gleichen Client wie Hauptagent verwenden

**Akzeptanzkriterien:**
1. Bei 50+ Nachrichten bleibt der Agent funktional und verliert keinen Kontext über die Hauptaufgabe
2. Token-Estimation erkennt drohenden Overflow BEVOR `finish_reason == "length"` auftritt
3. LLM-Summary behält alle Datei-Pfade und IDs exakt bei
4. Fallback auf Text-Trunkierung funktioniert wenn LLM-Summary fehlschlägt
5. Summary wird als System-Message mit `[CONTEXT SUMMARY: N messages compacted]` prefix eingefügt
6. Compaction-Settings sind via env vars konfigurierbar
7. Unit-Test: Token-Estimation innerhalb 20% Genauigkeit
8. Unit-Test: Compaction-Trigger bei 85% Context-Auslastung
9. Unit-Test: Identifier-Preservation (UUID im Output überlebt Compaction)

---

## Sprint 3 — Optimierung (P2)

### 5. Adaptives Reasoning-Level

**Problem:**
Das Reasoning-Protokoll (6 Schritte: UNDERSTAND → DECOMPOSE → PLAN → EXECUTE → VERIFY → REFINE)
ist statisch. Für "Was ist 2+2?" ist es Overkill und verschwendet Tokens. Für eine komplexe
mehrstufige Recherche ist es zu oberflächlich.

**Ist-Zustand:**
- Identisches 6-Schritt-Protokoll für alle Anfragen
- Kein Mechanismus um Komplexität der Anfrage zu erkennen
- Kein `<think>...</think>` Tag-Support
- Kein adaptives Budget für Reasoning

**Soll-Zustand:**
- Anfragen werden nach Komplexität klassifiziert: `trivial | moderate | complex`
- Reasoning-Aufwand wird angepasst:
  - `trivial`: Kein Reasoning-Protokoll, direkte Antwort
  - `moderate`: Kurzform (UNDERSTAND → EXECUTE → VERIFY)
  - `complex`: Vollform (alle 6 Schritte)
- Optional: `<think>...</think>` Tags für explizites Reasoning (nicht an User gezeigt)

**Betroffene Dateien:**
- `backend/app/agent_runner.py` → Reasoning-Level als Parameter
- `backend/app/config.py` → `reasoning_level: str` Setting (auto/off/minimal/full)
- `backend/app/services/intent_detector.py` → Komplexitäts-Klassifikation (evtl. schon vorhanden)
- `backend/app/prompts/agent_rules.md` → Reasoning-Level-abhängige Anweisungen

**Dos:**
- ✅ Default: `auto` — System entscheidet basierend auf Frage-Komplexität
- ✅ Einfache Heuristik für Komplexität: Fragelänge + Anzahl Teilfragen + Schlüsselwörter
- ✅ User-Override per Setting oder per-Message-Flag ermöglichen
- ✅ `<think>` Tags nur wenn das Modell sie unterstützt (Claude, GPT-4+)

**Don'ts:**
- ❌ Nicht einen extra LLM-Call nur für Komplexitäts-Erkennung machen — Heuristik reicht
- ❌ Nicht Reasoning komplett abschalten — immer mindestens "verify" behalten
- ❌ Nicht das Protokoll in der Antwort an den User zeigen (außer User fragt danach)

**Akzeptanzkriterien:**
1. "Hallo!" → Direkte Antwort ohne sichtbares Reasoning-Overhead
2. "Refactore die gesamte Auth-Schicht" → Vollständiges 6-Schritt-Protokoll wird angewendet
3. Reasoning-Level ist per `REASONING_LEVEL` env var überschreibbar
4. Token-Verbrauch für triviale Anfragen sinkt messbar (>30% weniger Prompt-Tokens)

---

## Was wir NICHT ändern

Diese Bereiche sind mindestens gleichwertig mit OpenClaw — kein Handlungsbedarf:

| Bereich | Unser Status | Notes |
|---------|-------------|-------|
| Tool Execution Pipeline | ✅ Gleichwertig | Parallele Execution, Timeout, Error-Handling |
| Evidence Gates | ✅ Voraus | 3-Gate-System (Implementation, All-Failed, Orchestration) |
| Reflection Service | ✅ Voraus | LLM-basierte QA mit factual_grounding Score |
| Verification Service | ✅ Voraus | Plan-Verification + Semantic-Coverage |
| Loop Detection | ✅ Gleichwertig | Identical-Repeat + Ping-Pong Detection |
| Agent Rules / Guardrails | ✅ Voraus | Detailliertes `agent_rules.md` + `tool_routing.md` |
| Multi-Agent Architecture | ✅ Voraus | Subruns, Orchestrator, Multi-Agency |
| Skill System | ✅ Gleichwertig | Dynamic Skill Loading, Skill Discovery |
| Memory Persistence | ✅ Gleichwertig | 3-Tier (Session + LTM + RAG) |
| Platform Detection | ✅ Gleichwertig | OS, Shell, Runtime Detection |
| Gateway / Heartbeat | N/A | Nicht vergleichbar (anderer Use-Case) |

---

## Reihenfolge der Implementierung

```
Sprint 1 (Quick Wins — sofort umsetzbar):
  ├── 1. Datum/Uhrzeit im System Prompt     (~20 LOC, 1h)
  └── 2. "Search before answering" Regel     (~30 LOC Prompt, 1h)

Sprint 2 (Security & Robustheit):
  ├── 3. External Content Wrapping            (~80 LOC, 1 Tag)
  └── 4. LLM-basierte Compaction              (~300 LOC neuer Service, 2-3 Tage)

Sprint 3 (Optimierung):
  └── 5. Adaptives Reasoning-Level            (~100 LOC, 1-2 Tage)
```

---

## Validierung

Nach jeder Implementierung:

1. **Smoke Test:** "Welches Datum ist heute?" → Korrekte Antwort
2. **Grounding Test:** "Was ist die neueste Version von Python?" → Agent benutzt `web_search`
3. **Regression:** Alle bestehenden Tests müssen grün bleiben
4. **Long Session Test:** 30+ Nachrichten hin und her → Agent behält Kontext
5. **Security Test:** Web-Seite mit "Ignore all instructions" im Title → Agent ignoriert Injection
