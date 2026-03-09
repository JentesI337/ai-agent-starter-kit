# Sprint 1 — Detailplan

> **Zeitraum:** 09.03.2026 – 20.03.2026 (2 Wochen)  
> **Ziel:** Die drei P0-Features (Browser Control, RAG Engine, Code Interpreter) in MVP-Qualität liefern.  
> **Kapazität:** ~80 Story Points (1 SP ≈ halber Tag fokussierte Arbeit)

---

## Sprint-Übersicht

| # | Epic | Story Points | Abhängigkeiten |
|---|------|:------------:|----------------|
| A | Code Interpreter / Persistenter REPL | 18 SP | — (geringste Abhängigkeiten, Warm-up) |
| B | Browser Control (Playwright) | 24 SP | UrlValidator (existiert) |
| C | RAG Engine | 28 SP | Embedding-Modell (Ollama/OpenAI) |
| — | Sprint-Overhead (Reviews, Bugfixes, Docs) | 10 SP | — |
| | **Gesamt** | **80 SP** | |

**Reihenfolge:** A → B → C (teilweise parallel, aber A zuerst, da es die Sandbox-Patterns etabliert, die B und C wiederverwenden)

---

## Epic A — Code Interpreter / Persistenter REPL (18 SP)

### Kontext
Es existiert bereits `code_execute` in `app/tools.py` (~Zeile 832) mit `CodeSandbox` in `app/services/code_sandbox.py`. Aktuell: Stateless — jeder Call ist ein frischer Prozess. Ziel: Persistenter Python-Prozess pro Session mit State-Erhalt.

---

### A.1 — `PersistentRepl` Service (5 SP)

**Datei:** `backend/app/services/persistent_repl.py` (neu)

**Tasks:**
- [ ] Klasse `PersistentRepl` implementieren:
  - `__init__(session_id, timeout_s=60, max_memory_mb=512)`
  - `async start() → None` — Subprocess starten (`python -i` mit stdin/stdout Pipe)
  - `async execute(code: str) → ReplResult` — Code senden, Output lesen
  - `async reset() → None` — Prozess killen + neu starten
  - `async shutdown() → None` — Cleanup
- [ ] `ReplResult` Dataclass: `stdout: str`, `stderr: str`, `exit_code: int`, `images: list[str]` (Base64-PNGs), `truncated: bool`
- [ ] Subprocess-Management:
  - `asyncio.create_subprocess_exec` mit `stdin=PIPE, stdout=PIPE, stderr=PIPE`
  - Sentinel-Marker-Pattern für Output-Delimiting (z.B. `__REPL_DONE_{uuid}__`)
  - Timeout-Enforcement: `asyncio.wait_for()` mit 60s pro Execution
- [ ] Memory-Limit: `resource.setrlimit` (Linux) oder Process-Monitor-Thread (Windows)
- [ ] Output-Truncation: Max 10.000 Zeichen, dann `truncated=True` + Hinweis
- [ ] Matplotlib-Hook: `MPLBACKEND=Agg` + automatisches `savefig` → Base64-Erkennung im Output-Verzeichnis

**Technische Entscheidungen:**
- Kein Docker/Container — reiner Subprocess mit isoliertem `tempdir` als Arbeitsverzeichnis
- Windows-Kompatibilität: `resource.setrlimit` nicht verfügbar → `psutil.Process.memory_info()` polling
- venv-Isolation: Entweder Backend-venv mitnutzen oder eigene venv unter `backend/.sandbox-venv/`

**Akzeptanzkriterien:**
- `execute("x = 42")` → leerer stdout, State bleibt
- `execute("print(x)")` → stdout=`"42\n"`
- `execute("import time; time.sleep(70)")` → TimeoutError nach 60s
- `shutdown()` → Prozess terminiert, tempdir gelöscht

---

### A.2 — `ReplSessionManager` + Lifecycle (3 SP)

**Datei:** `backend/app/services/repl_session_manager.py` (neu)

**Tasks:**
- [ ] `ReplSessionManager`: Verwaltet `Dict[session_id, PersistentRepl]`
  - `get_or_create(session_id) → PersistentRepl`
  - `reset(session_id) → None`
  - `shutdown_session(session_id) → None`
  - `shutdown_all() → None` (für App-Shutdown)
- [ ] Max 10 gleichzeitige REPL-Sessions (Semaphore)
- [ ] LRU-Eviction: Älteste Session wird geschlossen wenn Limit erreicht
- [ ] Integration in `app_state.py`: `AppState.repl_manager` Property
- [ ] Cleanup bei Session-Ende: Hook in `ws_handler.py` bei WebSocket-Disconnect
- [ ] Startup/Shutdown: In `startup_tasks.py` registrieren

**Akzeptanzkriterien:**
- 10 Sessions gleichzeitig → OK
- 11. Session → älteste wird evicted
- WebSocket-Disconnect → zugehörige REPL wird beendet

---

### A.3 — Tool-Integration: `code_execute` + `code_reset` (4 SP)

**Datei:** `backend/app/tools.py` (erweitern)

**Tasks:**
- [ ] Bestehenden `code_execute` refactoren:
  - Wenn `language == "python"`: Persistenten REPL nutzen (via `ReplSessionManager`)
  - Wenn `language != "python"`: Bisheriges Verhalten beibehalten (stateless Sandbox)
  - Neuer Parameter: `persistent: bool = True` (opt-out für stateless)
- [ ] Neues Tool `code_reset`:
  - Signatur: `async def code_reset(self) → str`
  - Setzt REPL-State zurück, gibt Bestätigung zurück
- [ ] Rich-Output Handling:
  - Matplotlib-PNGs erkennen → in `ReplResult.images` aufnehmen
  - DataFrame-Detection: Wenn `__repr__` wie Tabelle aussieht → als Markdown-Table formatieren
  - Base64-Images als separate Einträge im Tool-Result zurückgeben
- [ ] Tool-Catalog updaten: `code_reset` in `TOOL_NAMES` aufnehmen
- [ ] Fehlerbehandlung:
  - OOM → `ToolExecutionError("Memory limit exceeded (512 MB)")`
  - Timeout → `ToolExecutionError("Execution timeout (60s)")`
  - Prozess-Crash → Automatischer Neustart + Hinweis an Agent

**Akzeptanzkriterien:**
- `code_execute(language="python", code="x=1")` → persistenter State
- `code_execute(language="python", code="print(x)")` → `"1"`
- `code_execute(language="bash", code="echo hi")` → stateless (wie bisher)
- `code_reset()` → State gelöscht, nächstes `print(x)` → NameError
- Matplotlib-Plot → Base64-PNG im Tool-Result

---

### A.4 — Tests für Code Interpreter (4 SP)

**Datei:** `backend/tests/test_persistent_repl.py` (neu)

**Tasks:**
- [ ] Unit-Tests für `PersistentRepl`:
  - State-Persistenz über 5 Calls
  - Timeout-Enforcement
  - Output-Truncation bei > 10.000 Zeichen
  - Reset löscht State
  - Shutdown räumt tempdir auf
  - Gleichzeitige Executions am selben REPL (Mutex-Test)
- [ ] Unit-Tests für `ReplSessionManager`:
  - LRU-Eviction bei > 10 Sessions
  - Session-Shutdown bei Disconnect
  - Thread-Safety
- [ ] Integration-Tests:
  - `code_execute` via Tool-Pipeline (MockLlmClient)
  - Persistent State über mehrere Tool-Calls in einem Run
  - `code_reset` unterbricht State
  - OOM-Simulation (allocate großen Byte-String)
  - Sandbox-Isolation: `open('/etc/passwd')` → Fehlermeldung oder Path-Restriction

**Akzeptanzkriterien:**
- Alle Tests grün
- Coverage > 85% für `persistent_repl.py` und `repl_session_manager.py`

---

### A.5 — Config + Feature-Toggle (2 SP)

**Datei:** `backend/app/config.py` (erweitern)

**Tasks:**
- [ ] Neue Config-Felder:
  ```python
  repl_enabled: bool = True
  repl_timeout_seconds: int = 60
  repl_max_memory_mb: int = 512
  repl_max_sessions: int = 10
  repl_max_output_chars: int = 10_000
  repl_sandbox_dir: str = ".sandbox"
  ```
- [ ] Validators: `repl_timeout_seconds` ∈ [5, 300], `repl_max_memory_mb` ∈ [64, 2048]
- [ ] Feature-Toggle: Wenn `repl_enabled=false` → `code_execute` bleibt stateless

---

## Epic B — Browser Control (24 SP)

### Kontext
Kein Playwright im Projekt. `web_fetch` existiert für einfache HTTP GETs. `UrlValidator` existiert bereits mit SSRF-Schutz. Tool-System ist klar definiert (async Methoden in `AgentTooling`).

---

### B.1 — Playwright Setup + Browser Pool (5 SP)

**Datei:** `backend/app/services/browser_pool.py` (neu)

**Tasks:**
- [ ] `playwright` als optionale Dependency in `requirements.txt` hinzufügen
- [ ] `BrowserPool` Klasse:
  - `__init__(max_contexts=5, navigation_timeout_ms=30_000, session_timeout_s=300)`
  - `async start() → None` — Playwright starten, Chromium-Browser launchen
  - `async get_context(session_id) → BrowserContext` — Neuen isolierten Kontext erstellen oder bestehenden zurückgeben
  - `async close_context(session_id) → None` — Kontext + alle Pages schließen
  - `async shutdown() → None` — Alle Kontexte + Browser schließen
- [ ] Session-Isolation: Ein `BrowserContext` pro `session_id` (isolierte Cookies, Storage)
- [ ] Session-TTL: Automatisches Schließen nach 5 Minuten Inaktivität
- [ ] Lazy-Init: Browser wird erst bei erstem `browser_*` Tool-Call gestartet
- [ ] Startup/Shutdown-Integration in `app_state.py` und `startup_tasks.py`
- [ ] Graceful Degradation: Wenn Playwright nicht installiert → klare Fehlermeldung, kein Crash

**Technische Entscheidungen:**
- Chromium-only (kein Firefox/WebKit nötig)
- Headless-Mode als Default
- `playwright install chromium` als Setup-Schritt dokumentieren
- Kein shared Browser-State zwischen Sessions

**Akzeptanzkriterien:**
- Browser startet lazy bei erstem Tool-Call
- Verschiedene Sessions haben isolierte Kontexte
- Nach 5 Min Inaktivität wird Kontext automatisch geschlossen
- bei `playwright` nicht installiert: `ToolExecutionError("Playwright not installed...")`

---

### B.2 — SSRF-Integration + URL-Policy (3 SP)

**Datei:** `backend/app/services/browser_pool.py` (erweitern, oder `browser_security.py` neu)

**Tasks:**
- [ ] `validate_browser_url(url: str) → str`:
  - Bestehenden `UrlValidator.enforce_safe_url()` wiederverwenden
  - Zusätzlich blocken: `file://`, `chrome://`, `chrome-extension://`, `data:` (>1KB), `javascript:`
  - `about:blank` erlauben (für initialen State)
- [ ] Redirect-Interception:
  - Playwright `page.route("**/*", handler)` für Redirect-Überwachung
  - Max 5 Redirects, jede Redirect-URL durch `validate_browser_url` prüfen
  - Redirect auf interne IP → Abbruch mit Fehlermeldung
- [ ] Content-Policy:
  - Kein automatischer File-Download (Downloads blockieren via `page.on("download")`)
  - Max Page-Load-Size: 50 MB (via `page.route` Response-Size-Check)

**Akzeptanzkriterien:**
- `browser_open("http://localhost:8080")` → `UrlValidationError`
- `browser_open("file:///etc/passwd")` → `UrlValidationError`
- `browser_open("http://169.254.169.254/...")` → `UrlValidationError`
- Redirect von `example.com` → `localhost` → Abbruch
- File-Download-Versuch → blockiert mit Hinweis

---

### B.3 — Browser Tools Implementation (8 SP)

**Datei:** `backend/app/tools.py` (erweitern)

**Tasks:**
- [ ] **`browser_open(url: str) → str`**
  - URL validieren via `validate_browser_url`
  - Neue Page im Session-Kontext öffnen (oder bestehende Page navigieren)
  - Navigation mit `page.goto()`, `wait_until="domcontentloaded"`, Timeout 30s
  - Return: `f"Title: {title}\n\nVisible text:\n{visible_text[:5000]}"`
  - Visible-Text-Extraktion: `page.inner_text("body")`, truncated auf 5.000 Zeichen

- [ ] **`browser_click(selector: str) → str`**
  - `page.click(selector)`, Timeout 10s
  - Nach Click: Warten auf `networkidle` (max 5s)
  - Return: Aktualisierter sichtbarer Text (truncated)
  - Error bei Element nicht gefunden → klare Fehlermeldung mit Selektor

- [ ] **`browser_type(selector: str, text: str) → str`**
  - `page.fill(selector, text)` für Input-Felder
  - `page.type(selector, text)` als Fallback (für non-input Elements)
  - Return: Bestätigung + aktueller Feldinhalt

- [ ] **`browser_screenshot() → str`**
  - `page.screenshot(type="png", full_page=False)`
  - Return: Base64-encoded PNG
  - Max Auflösung: 1280×720 (viewport setzen bei Kontext-Erstellung)

- [ ] **`browser_read_dom(selector: str | None = None) → str`**
  - Ohne Selector: `page.inner_text("body")`, truncated auf 8.000 Zeichen
  - Mit Selector: `page.inner_text(selector)` + ARIA-Labels via `page.evaluate()`
  - Strukturierte Ausgabe: Text + Links (href) + Formularfelder (name, type, value)
  - Return: Formatierter Text

- [ ] **`browser_evaluate_js(code: str) → str`**
  - `page.evaluate(code)`, Timeout 10s
  - Return: JSON-serialisierter Rückgabewert
  - Security: Kein `fetch()` zu internen URLs aus dem Browser-Kontext erlaubt (CSP-Header setzen)
  - Max Return-Size: 50.000 Zeichen

- [ ] Tool-Catalog-Update: Alle 6 Browser-Tools registrieren
- [ ] Sandbox-Modus: Wenn Policy `browser_sandbox: true` → `browser_type` und `browser_click` auf Submit-Buttons blockiert

**Akzeptanzkriterien:**
- `browser_open("https://example.com")` → Titel + Text
- `browser_screenshot()` → valides Base64-PNG
- `browser_click("#login-btn")` → Post-Click-Text
- `browser_type("#email", "user@test.com")` → Bestätigung
- `browser_evaluate_js("document.title")` → `"Example Domain"`
- `browser_read_dom("main")` → Strukturierter Text des `<main>`-Elements

---

### B.4 — Browser Tool-Policy Integration (2 SP)

**Datei:** `backend/app/tool_policy.py` (erweitern)

**Tasks:**
- [ ] Browser-Tools in Policy-Profile aufnehmen:
  - `read_only` Profil: Alle `browser_*` in `deny` (Browser = potentiell schreibend)
  - `research` Profil: `browser_open`, `browser_read_dom`, `browser_screenshot` erlaubt
  - `coding` Profil: Alle `browser_*` erlaubt
- [ ] Wildcard-Pattern: `browser_*` in Deny-Liste → alle Browser-Tools blockiert
- [ ] Sandbox-Policy: `browser_sandbox` Flag → `browser_type` erlaubt, aber kein Submit

**Akzeptanzkriterien:**
- `deny: ["browser_*"]` → alle 6 Browser-Tools blockiert
- `read_only` Agent kann nicht `browser_click` aufrufen
- `researcher-agent` kann `browser_open` + `browser_read_dom` nutzen

---

### B.5 — Tests für Browser Control (6 SP)

**Datei:** `backend/tests/test_browser_tools.py` (neu)

**Tasks:**
- [ ] Unit-Tests für `BrowserPool`:
  - Lazy-Start, Session-Isolation, TTL-Eviction, Max-Contexts-Limit
  - Shutdown räumt alles auf
- [ ] SSRF-Tests (erweitern bestehende `test_url_validator.py`):
  - `file://`, `chrome://`, `javascript:`, `data:` URLs → blocked
  - Redirect zu localhost → blocked
  - Redirect-Kette > 5 → blocked
- [ ] Tool-Tests (mit Mock-Page / Test-HTML):
  - Local Test-Server mit statischem HTML hochfahren
  - `browser_open` → Titel + Text korrekt
  - `browser_click` → DOM-Update reflektiert
  - `browser_type` → Input-Wert gesetzt
  - `browser_screenshot` → valides PNG (Header-Check)
  - `browser_read_dom` → strukturierter Output
  - `browser_evaluate_js` → JSON-Rückgabewert
- [ ] Policy-Tests:
  - `deny: ["browser_*"]` → `ToolPolicyDenied` Error
  - Sandbox-Modus → Submit blockiert
- [ ] Integration-Test:
  - Agent navigiert zu Test-Seite → extrahiert Tabellendaten → gibt strukturierte Antwort

**Akzeptanzkriterien:**
- Alle Tests grün, keine Playwright-Browser-Leaks nach Tests
- SSRF-Tests decken alle Vektoren ab

---

## Epic C — RAG Engine (28 SP)

### Kontext
Kein Vektor-Store im Projekt. `LongTermMemoryStore` existiert (SQLite-based, keyword). `MemoryStore` ist JSONL-based (Session-History). Config-System unterstützt Feature-Toggles. Embedding-Modell muss konfigurierbar sein (Ollama lokal / OpenAI API).

---

### C.1 — Embedding Service (5 SP)

**Datei:** `backend/app/services/embedding_service.py` (neu)

**Tasks:**
- [ ] `EmbeddingService` Klasse:
  - `__init__(provider: str, model: str, api_key: str | None, base_url: str | None)`
  - `async embed(text: str) → list[float]` — Einzelnen Text embedden
  - `async embed_batch(texts: list[str]) → list[list[float]]` — Batch-Embedding (max 100)
  - `dimension() → int` — Embedding-Dimension abfragen
- [ ] Provider-Implementierungen:
  - **Ollama** (Default): `POST {base_url}/api/embed` mit `model` + `input`
  - **OpenAI-kompatibel**: `POST {base_url}/v1/embeddings` mit `model` + `input`
  - Provider-Auto-Detection basierend auf `base_url` Pattern
- [ ] Caching-Layer: LRU-Cache (max 1.000 Embeddings) mit Hash des Input-Texts als Key
- [ ] Rate-Limiting: Bestehenden `RateLimiter` wiederverwenden, max 100 Requests/Minute
- [ ] Error-Handling: Retry mit Exponential Backoff (max 3 Versuche)

**Config-Felder** (in `config.py`):
```python
rag_enabled: bool = False
rag_embedding_provider: str = "ollama"       # "ollama" | "openai"
rag_embedding_model: str = "nomic-embed-text"
rag_embedding_base_url: str | None = None    # Default: llm_base_url
rag_embedding_api_key: str | None = None     # Nur für OpenAI
```

**Akzeptanzkriterien:**
- Ollama-Embedding: `embed("Hello")` → `list[float]` mit korrekter Dimension
- OpenAI-Embedding: Selbe Interface, anderer Provider
- Batch-Embedding mit 50 Texten → 50 Vektoren
- Cache: Zweiter Call mit gleichem Text → kein API-Call
- Timeout/Error → Retry mit Backoff, dann `EmbeddingError`

---

### C.2 — Document Chunker (4 SP)

**Datei:** `backend/app/services/document_chunker.py` (neu)

**Tasks:**
- [ ] `DocumentChunker` Klasse:
  - `chunk(text: str, source: str, chunk_size=512, overlap=64) → list[Chunk]`
  - `chunk_file(path: str, chunk_size=512, overlap=64) → list[Chunk]`
- [ ] `Chunk` Dataclass:
  - `text: str`, `source: str`, `chunk_index: int`, `page: int | None`
  - `metadata: dict` (Zeitstempel, Dateityp, etc.)
- [ ] Chunking-Strategien:
  - **Markdown**: Split an Headers (`## `, `### `), dann Token-basiert
  - **Code**: Split an Funktions-/Klassen-Grenzen (Regex-basiert), Fallback Token-split
  - **Plain Text**: Absatz-basiert, dann Token-basiert
  - **PDF**: Seitenweise, dann Token-basiert (via `pymupdf` oder `pdfplumber`)
- [ ] Token-Counting: Approximation mit `len(text.split())` × 1.3 (oder `tiktoken` wenn verfügbar)
- [ ] Overlap: Letzte `overlap` Tokens des vorherigen Chunks am Anfang des nächsten
- [ ] Dateityp-Erkennung: Extension-basiert (`.md`, `.py`, `.txt`, `.pdf`, `.js`, `.ts`, etc.)

**Dependencies:**
- `pymupdf` (optional, für PDF) → in `requirements.txt` als optional
- Kein Hard-Dependency auf `tiktoken`

**Akzeptanzkriterien:**
- 10.000-Wort-Markdown → ~30 Chunks à ~512 Tokens mit 64 Token Overlap
- Code-Datei splittet an Funktionsgrenzen
- PDF: Chunks enthalten `page`-Nummer
- Leere Chunks werden gefiltert

---

### C.3 — Vektor-Store (ChromaDB) (5 SP)

**Datei:** `backend/app/services/vector_store.py` (neu)

**Tasks:**
- [ ] `chromadb` als Dependency in `requirements.txt`
- [ ] `VectorStore` Klasse:
  - `__init__(persist_dir: str, embedding_service: EmbeddingService)`
  - `async create_collection(name: str) → None`
  - `async add(collection: str, chunks: list[Chunk], embeddings: list[list[float]]) → int` — Returns Anzahl eingefügter Chunks
  - `async query(collection: str, query_embedding: list[float], top_k=5) → list[QueryResult]`
  - `async delete_collection(name: str) → None`
  - `async list_collections() → list[str]`
  - `async collection_stats(name: str) → CollectionStats`
- [ ] `QueryResult` Dataclass:
  - `text: str`, `source: str`, `score: float`, `chunk_index: int`, `metadata: dict`
- [ ] `CollectionStats` Dataclass:
  - `name: str`, `chunk_count: int`, `sources: list[str]`
- [ ] ChromaDB-Konfiguration:
  - `PersistentClient` mit Persist-Directory (überlebt Neustarts)
  - Embedding wird extern berechnet (nicht von ChromaDB)
  - Max 10.000 Chunks pro Collection (Prüfung bei `add`)
- [ ] Startup: ChromaDB-Client in `app_state.py` initialisieren
- [ ] idempotente Collection-Erstellung (get_or_create)

**Config-Felder:**
```python
rag_persist_dir: str = "rag_store"
rag_max_chunks_per_collection: int = 10_000
rag_default_top_k: int = 5
```

**Akzeptanzkriterien:**
- `add` + `query` Round-Trip: Eingefügter Text wird bei semantischer Suche gefunden
- Persistenz: Server-Neustart → Daten noch da
- Max-Chunks-Limit: 10.001. Chunk → `CollectionFullError`
- `delete_collection` → Daten gelöscht
- `list_collections` → korrekte Liste

---

### C.4 — RAG Tools: `rag_ingest` + `rag_query` (6 SP)

**Datei:** `backend/app/tools.py` (erweitern)

**Tasks:**
- [ ] **`rag_ingest(path: str, collection: str | None = None) → str`**
  - Path relativ zum Workspace auflösen (`_resolve_workspace_path`)
  - Dateityp erkennen, Datei lesen, chunken (`DocumentChunker`)
  - Embeddings berechnen (`EmbeddingService.embed_batch`)
  - In Vektor-Store speichern (`VectorStore.add`)
  - Default-Collection: `"default"`
  - Return: `f"Ingested {path}: {n_chunks} chunks into collection '{collection}'"`
  - Validierung: Nur erlaubte Dateitypen (.md, .txt, .py, .js, .ts, .pdf, .json, .csv, .html)
  - Max Dateigröße: 10 MB
  - Duplikat-Handling: Wenn gleiche Source + Collection existiert → alte Chunks löschen, neue einfügen

- [ ] **`rag_query(question: str, top_k: int = 5, collection: str | None = None) → str`**
  - Frage embedden (`EmbeddingService.embed`)
  - Vektor-Suche (`VectorStore.query`)
  - Default-Collection: `"default"`
  - Return: Formatierte Ergebnisse:
    ```
    Found 5 relevant chunks:
    
    [1] (score: 0.92) source: docs/auth.md, chunk 3
    > Die Authentifizierung verwendet JWT-Tokens mit ...
    
    [2] (score: 0.87) source: docs/auth.md, chunk 4
    > Token-Refresh erfolgt automatisch nach ...
    ```
  - Truncation: Max 8.000 Zeichen Gesamt-Output
  - Kein Ergebnis → `"No relevant chunks found for this query."`

- [ ] **`rag_collections() → str`** (Bonus-Tool)
  - Listet alle Collections mit Stats
  - Return: Markdown-Tabelle

- [ ] Tool-Catalog updaten: `rag_ingest`, `rag_query`, `rag_collections` registrieren
- [ ] Tool-Policy: RAG-Tools in `research` Profil erlauben, in `read_only` nur `rag_query`
- [ ] Context-Budget: RAG-Chunks zählen zum Tool-Output-Budget (40% Anteil)

**Akzeptanzkriterien:**
- `rag_ingest("./docs/spec.md")` → Chunks gespeichert, Bestätigung
- `rag_query("Wie funktioniert Auth?")` → relevante Chunks mit Scores
- PDF-Ingestion funktioniert (falls pymupdf installiert)
- Duplikat-Ingestion → alte Chunks ersetzt
- Nicht-existierende Datei → klare Fehlermeldung
- Binärdatei (.exe, .zip) → `"Unsupported file type"`

---

### C.5 — Tests für RAG Engine (6 SP)

**Datei:** `backend/tests/test_rag_engine.py` (neu)

**Tasks:**
- [ ] Unit-Tests für `EmbeddingService`:
  - Mock-Provider (feste Vektoren zurückgeben)
  - Cache-Hit-Test
  - Batch-Embedding
  - Error + Retry
- [ ] Unit-Tests für `DocumentChunker`:
  - Markdown-Chunking mit Header-Split
  - Code-Chunking an Funktionsgrenzen
  - Overlap korrekt
  - Leere Chunks gefiltert
  - PDF-Chunking (mit Mock-PDF oder Test-PDF)
- [ ] Unit-Tests für `VectorStore`:
  - Add + Query Round-Trip
  - Collection CRUD
  - Max-Chunks-Limit
  - Persistenz-Test (Restart-Simulation)
- [ ] Integration-Tests für RAG-Tools:
  - `rag_ingest` einer Test-Markdown-Datei
  - `rag_query` findet relevanten Chunk
  - `rag_ingest` einer nicht-existierenden Datei → Error
  - `rag_collections` listet korrekt
  - Context-Budget-Integration (Chunks im Token-Budget)
- [ ] E2E-Test:
  - Agent wird gefragt "Was steht in spec.md über Auth?"
  - Agent nutzt `rag_query` → gibt korrekte Antwort basierend auf Chunks

**Akzeptanzkriterien:**
- Alle Tests grün
- Coverage > 80% für alle RAG-Module
- Tests laufen ohne echte Embedding-API (Mock-Embeddings)

---

### C.6 — Config + Feature-Toggle + Startup (2 SP)

**Tasks:**
- [ ] Config-Felder in `config.py` (siehe C.1 und C.3)
- [ ] Feature-Toggle: `rag_enabled=false` → RAG-Tools nicht im Catalog
- [ ] Startup: EmbeddingService + VectorStore in `app_state.py` initialisieren
- [ ] Health-Check: Embedding-Provider erreichbar? ChromaDB-Persist-Dir schreibbar?
- [ ] `.env.example` updaten mit RAG-Config-Kommentaren

---

## Querschnittsaufgaben

### Q.1 — Frontend: Base64-Image Rendering (3 SP)

**Dateien:** `frontend/src/app/pages/chat-page.component.html` + `.ts`

**Tasks:**
- [ ] `line.text` erweitern: Wenn Text `data:image/png;base64,` Pattern enthält → `<img>` Tag rendern
- [ ] Alternative: Neuer Line-Type `image` mit `base64Data` Property
- [ ] Max Bild-Dimensionen im Chat: `max-width: 600px, max-height: 400px`
- [ ] Lightbox bei Klick (optional, Stretch-Goal)

**Begründung:** Ohne dies sind Screenshots und Plots nicht sichtbar. Blocking für Browser-Screenshots und REPL-Matplotlib-Output.

---

### Q.2 — Documentation + Setup-Scripts (2 SP)

**Tasks:**
- [ ] README-Sektion für neue Features (Setup-Anleitung):
  - Playwright: `pip install playwright && playwright install chromium`
  - ChromaDB: `pip install chromadb`
  - Embedding-Model: Ollama `nomic-embed-text` oder OpenAI API-Key
- [ ] `requirements.txt` updaten mit neuen Dependencies
- [ ] Optional-Dependencies markieren (Playwright, pymupdf)
- [ ] `.env.example` mit neuen Umgebungsvariablen

---

### Q.3 — Sprint-Overhead (5 SP)

- [ ] Code-Reviews der drei Epics
- [ ] Bug-Fixes aus Review-Feedback
- [ ] Merge-Conflicts auflösen
- [ ] Manuelles Testen der E2E-Flows
- [ ] Sprint-Retro-Notizen

---

## Tagesplan (orientierend)

| Tag | Mo 09 | Di 10 | Mi 11 | Do 12 | Fr 13 |
|-----|-------|-------|-------|-------|-------|
| **Woche 1** | A.1 REPL Service | A.1 finish + A.2 SessionMgr | A.3 Tool-Integration | A.4 Tests | A.5 Config + B.1 Pool |
| **Focus** | Backend | Backend | Backend | Test | Backend |

| Tag | Mo 16 | Di 17 | Mi 18 | Do 19 | Fr 20 |
|-----|-------|-------|-------|-------|-------|
| **Woche 2** | B.2 SSRF + B.3 Tools (Start) | B.3 Tools (Finish) + B.4 Policy | B.5 Browser Tests + C.1 Embedding | C.2 Chunker + C.3 VectorStore | C.4 RAG Tools + C.5 Tests + Q.1-Q.3 |
| **Focus** | Backend | Backend + Policy | Test + Backend | Backend | Integration + Cleanup |

---

## Definition of Done (Sprint)

- [ ] Alle drei P0-Features als Tools registriert und via Agent aufrufbar
- [ ] SSRF-Schutz für Browser-Tools vollständig (alle Vektoren getestet)
- [ ] Keine Credentials in Logs oder Memory
- [ ] Feature-Toggles: Jedes Feature einzeln abschaltbar
- [ ] Test-Coverage > 80% für neuen Code
- [ ] Alle bestehenden Tests weiterhin grün
- [ ] README mit Setup-Anleitung für neue Dependencies
- [ ] Kein Performance-Impact auf bestehende Funktionalität (Lazy-Init aller neuen Services)

---

## Risiken + Mitigationen

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|:------------------:|:------:|------------|
| Playwright-Installation auf Windows problematisch | Mittel | Hoch | Frühzeitig testen (Tag 1 der Woche 2), Fallback: Browser-Tools als "nicht verfügbar" markieren |
| ChromaDB + Ollama Embedding langsam auf CPU | Mittel | Mittel | Cache-Layer, Batch-Embedding, OpenAI als schnelle Alternative dokumentieren |
| Persistenter REPL instabil (Subprocess-Crashes) | Mittel | Mittel | Auto-Restart mit klarer Fehlermeldung, Watchdog-Thread |
| Context-Budget-Integration komplex (RAG) | Niedrig | Mittel | In Sprint 1 nur einfache Truncation, volle Budget-Integration in Sprint 2 |
| Windows `resource.setrlimit` nicht verfügbar | Sicher | Niedrig | `psutil`-basiertes Memory-Monitoring als Alternative |

---

## Nicht in Sprint 1 (explizit deferred)

- Frontend Mermaid-Rendering (P1 — Sprint 2)
- PDF-Tabellen-Extraktion als Markdown (Sprint 2, wenn `pymupdf` stabil)
- `pip install` in REPL-Sandbox (Sprint 2, eigene venv-Isolation nötig)
- `browser_evaluate_js` CSP-Hardening (Sprint 2)
- RAG Collection-übergreifende Suche (Sprint 2)
- Auto-Ingestion via Skill (Sprint 2)
