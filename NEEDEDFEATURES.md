# Needed Features — AI Agent Starter Kit

> Ziel: Den Agent von einem Code-Assistenten zu einem universellen Problemlöser machen.  
> Stand: März 2026 · Prioritäten: P0 (kritisch) → P3 (nice-to-have)

---

## P0 — Browser Control

### Beschreibung
Headless-Browser-Steuerung (Playwright) als eigenständiges Tool im Tool-Katalog. Ermöglicht dem Agent, Webseiten zu öffnen, zu navigieren, DOM-Elemente zu lesen, Formulare auszufüllen, Screenshots zu erstellen und JavaScript im Seitenkontext auszuführen. Ersetzt den bisherigen reinen HTTP-Fetch (`web_fetch`) für alle Fälle, die JS-Rendering oder Interaktion erfordern.

### Dos
- Playwright als Backend nutzen (async API, Chromium-only reicht)
- Eigener Browser-Pool mit Session-Isolation (ein Browser-Kontext pro Agent-Run)
- Definierte Tool-Funktionen: `browser_open`, `browser_click`, `browser_type`, `browser_screenshot`, `browser_read_dom`, `browser_evaluate_js`
- Timeout pro Navigation (max 30s) und pro Gesamt-Session (max 5 min)
- Screenshot-Output als Base64 in Tool-Result, passend zum bestehenden `send_event`-Protokoll
- DOM-Extraktion auf sichtbaren Text + ARIA-Labels beschränken (Tokenlimit)
- Tool-Policy-Integration: Browser-Tools in `allow`/`deny`-Listen aufnehmbar
- Sandbox-Modus: Nur Lesen erlaubt (kein Formular-Submit), schaltbar über Policy

### Don'ts
- Keinen eigenen Browser-Prozess pro Tool-Call starten — Pool wiederverwenden
- Keine Credentials im DOM-Kontext speichern oder loggen
- Keine unbegrenzten Redirects (max 5)
- Kein File-Download auf das Host-Filesystem ohne explizite User-Approval
- Keine Cookie-Persistenz zwischen verschiedenen Runs
- Kein `page.goto()` auf `file://`-, `chrome://`- oder interne Netzwerk-URLs (SSRF-Schutz)

### Akzeptanzkriterien
- [ ] `browser_open(url)` öffnet eine Seite, gibt sichtbaren Text + Seitentitel zurück
- [ ] `browser_screenshot()` liefert Base64-PNG, anzeigbar im Frontend-Chat
- [ ] `browser_click(selector)` klickt Element, gibt aktualisierten sichtbaren Text zurück
- [ ] `browser_type(selector, text)` füllt Eingabefeld, gibt Bestätigung zurück
- [ ] `browser_evaluate_js(code)` führt JS aus, gibt Rückgabewert als JSON zurück
- [ ] `browser_read_dom(selector?)` extrahiert strukturierten Text aus DOM-Bereich
- [ ] SSRF-Validierung blockt `localhost`, `127.0.0.1`, `169.254.x.x`, `file://`
- [ ] Browser-Kontext wird nach Run-Ende oder Timeout automatisch geschlossen
- [ ] Tool-Policy `deny: [browser_*]` verhindert Browser-Zugriff für eingeschränkte Agenten
- [ ] Integration-Test: Agent navigiert zu einer Test-Seite, extrahiert Daten, gibt strukturierte Antwort

---

## P0 — RAG Engine (Retrieval-Augmented Generation)

### Beschreibung
Vektor-basierte Wissensdatenbank, die dem Agent erlaubt, eigene Dokumente (PDF, Markdown, Code, Text) zu embedden, zu indexieren und bei Bedarf semantisch abzurufen. Geht über das bestehende Session-Memory (JSONL) und Long-Term-Memory (SQLite/Keyword) hinaus durch Embedding-basierte Ähnlichkeitssuche.

### Dos
- ChromaDB als Default-Vektorspeicher (lokal, kein externer Service nötig)
- Embedding-Modell konfigurierbar (Default: lokales Modell via Ollama, alternativ OpenAI `text-embedding-3-small`)
- Dokument-Ingestion als eigenes Tool: `rag_ingest(path_or_url, collection?)`
- Retrieval als Tool: `rag_query(question, top_k=5, collection?)`
- Chunking-Strategie: Semantic Splitting mit Overlap (512 Token Chunks, 64 Token Overlap)
- Metadaten pro Chunk: Quelldatei, Seitenzahl, Zeitstempel, Collection
- Collections pro Session oder global konfigurierbar
- In den bestehenden Context-Budget-Mechanismus (Phase 2) integrieren — RAG-Chunks zählen zum Token-Budget

### Don'ts
- Keine automatische Ingestion des gesamten Workspace (nur explizit oder per Skill)
- Kein Embedding von Binärdateien ohne Parser (nur Text, Markdown, PDF, Code)
- Keine unbegrenzte Collection-Größe — Max 10.000 Chunks pro Collection mit LRU-Eviction
- Keinen externen Vektor-Service als Hard-Dependency — ChromaDB muss lokal laufen
- Keine Embeddings im Klartext loggen (können sensible Inhalte enthalten)
- Kein Re-Embedding bei jedem Start — persistente Vektoren auf Disk

### Akzeptanzkriterien
- [ ] `rag_ingest("./docs/spec.md")` chunked das Dokument und speichert Embeddings
- [ ] `rag_query("Wie funktioniert die Authentifizierung?")` gibt Top-5-Chunks mit Score zurück
- [ ] PDF-Ingestion extrahiert Text seitenweise und chunked korrekt
- [ ] Chunks enthalten Metadaten (Quelle, Position, Timestamp)
- [ ] Collection-Isolation: Verschiedene Runs/Sessions können eigene Collections nutzen
- [ ] Context-Budget-Integration: RAG-Chunks werden gegen Token-Budget gerechnet
- [ ] Persistenz: Vektoren überleben Server-Neustarts
- [ ] Performance: Query < 500ms bei 5.000 Chunks
- [ ] Integration-Test: Agent beantwortet Frage korrekt basierend auf ingestiertem Dokument, das nicht im Kontext war

---

## P0 — Code Interpreter / Persistenter REPL

### Beschreibung
Erweiterung der bestehenden `code_execute`-Sandbox um persistenten State über mehrere Tool-Calls hinweg. Der Agent kann Python-Code ausführen, Variablen behalten, DataFrames aufbauen, Plots erzeugen und iterativ arbeiten — wie ein Jupyter-Notebook.

### Dos
- Einen langlebigen Python-Prozess pro Session halten (Subprocess mit stdin/stdout Pipe)
- State bleibt erhalten: Variablen, Imports, definierte Funktionen
- Rich-Output unterstützen: stdout, stderr, Matplotlib-Plots als Base64-PNG, DataFrames als Markdown-Tabelle
- Ressourcenlimits: Max 60s CPU pro Execution, max 512MB RAM, max 50MB Disk-Output
- Auto-Install: `pip install` innerhalb der Sandbox erlaubt (isolierte venv)
- Output-Truncation bei > 10.000 Zeichen (mit Hinweis an Agent)
- Integration mit Visualization Pipeline (P1) für Plot-Output

### Don'ts
- Keinen Zugriff auf Host-Filesystem außerhalb des Sandbox-Verzeichnisses
- Keine Netzwerk-Zugriffe aus der Sandbox (kein `requests`, `urllib` — dafür gibt es `web_fetch`)
- Kein `os.system()`, `subprocess`, `exec()` von User-generierten Strings innerhalb der Sandbox
- Keinen unbegrenzten Speicher — OOM-Kill nach 512MB
- Keine Persistenz des REPL-State über Session-Ende hinaus (Cleanup bei Session-Close)
- Kein Root/Admin-Zugriff innerhalb der Sandbox

### Akzeptanzkriterien
- [ ] Erster `code_execute("x = 42")` → kein Output, aber State gespeichert
- [ ] Zweiter `code_execute("print(x)")` → Output: `42` (State persistiert)
- [ ] `code_execute("import pandas as pd; df = pd.DataFrame(...)") ` → DataFrame als Markdown-Tabelle
- [ ] Matplotlib-Plot: `code_execute("import matplotlib.pyplot as plt; plt.plot([1,2,3]); plt.savefig('out.png')")` → Base64-PNG im Result
- [ ] Timeout nach 60s mit klarer Fehlermeldung
- [ ] OOM nach 512MB mit klarer Fehlermeldung
- [ ] Session-Reset: `code_reset()` löscht allen State
- [ ] Kein Filesystem-Zugriff außerhalb `/sandbox/` möglich
- [ ] Integration-Test: Agent lädt CSV via `web_fetch`, verarbeitet in REPL, erzeugt Plot

---

## P1 — Visualization Pipeline

### Beschreibung
Fähigkeit des Agents, strukturierte Daten als visuelle Outputs zu erzeugen: Charts, Diagramme, Flowcharts, Architektur-Diagramme. Kombiniert Mermaid-Rendering, Matplotlib (via Code Interpreter) und SVG-Generierung.

### Dos
- Mermaid-Diagramme als nativen Output-Typ unterstützen (Frontend rendert Mermaid → SVG)
- Neuer Event-Typ `visualization` im WebSocket-Protokoll mit Payload `{type: "mermaid"|"image"|"svg", data: "..."}`
- Frontend: Mermaid-JS Renderer einbetten, Base64-Bilder inline anzeigen
- Agent kann Plan-Graphen automatisch als Mermaid-Flowchart visualisieren
- Unterstützte Diagrammtypen: Flowchart, Sequenz, Klassen, ER, Gantt, Pie, Mindmap
- Export-Funktion: SVG/PNG Download aus dem Frontend
- Theme-Integration: Diagramme nutzen das Dark-Theme aus dem Design-System

### Don'ts
- Keine serverseitige Mermaid-Rendering (Browser-seitig via mermaid.js)
- Kein automatisches Rendering bei jedem Turn — nur wenn Agent explizit `visualization`-Event sendet
- Keine externen CDN-Abhängigkeiten für Mermaid — Bundle lokal
- Keine Diagramme > 500 Nodes (Performance-Guard)

### Akzeptanzkriterien
- [ ] Agent sendet Mermaid-Code → Frontend rendert als SVG im Chat
- [ ] Agent sendet Base64-PNG (z.B. aus Code Interpreter) → Frontend zeigt Bild inline
- [ ] Neuer WebSocket-Event-Typ `visualization` wird korrekt verarbeitet
- [ ] Mermaid-Flowchart, Sequenz- und ER-Diagramme rendern fehlerfrei
- [ ] Dark-Theme-Styling für Mermaid-Diagramme
- [ ] Export-Button für SVG/PNG-Download
- [ ] Plan-Graph des Reasoning-Pipeline kann als Mermaid angezeigt werden
- [ ] Performance: Diagramme mit 100 Nodes rendern in < 2s

---

## P1 — Structured Data / Database Agent

### Beschreibung
Datenbankzugriff als Tool-Set: SQL-Queries ausführen, Schemas inspizieren, Ergebnisse als Tabellen zurückgeben. Unterstützung für SQLite (lokal), PostgreSQL und MySQL über konfigurierbare Connection-Strings.

### Dos
- Connection-Strings als Environment-Variable oder über Config (verschlüsselt gespeichert)
- Tools: `db_connect(alias)`, `db_query(sql, alias)`, `db_schema(table?, alias)`, `db_tables(alias)`
- Read-Only-Modus als Default — schreibende Queries nur mit expliziter Policy-Freigabe
- Query-Timeout: Max 30s
- Ergebnis-Limit: Max 1.000 Rows pro Query, danach Truncation mit Hinweis
- Parametrisierte Queries erzwingen (SQL-Injection-Schutz)
- Ergebnisse als Markdown-Tabelle im Tool-Result
- SQLite als Zero-Config-Option (Datei-basiert, kein Server nötig)

### Don'ts
- Keine Connection-Strings im Klartext in Logs oder Agent-Memory
- Keine DDL-Statements (`DROP`, `ALTER`, `CREATE`) ohne explizite User-Approval
- Keine direkten String-Interpolationen in SQL — nur parametrisierte Queries
- Keine Verbindung zu Systemen außerhalb des konfigurierten Alias-Sets
- Kein Connection-Pooling ohne Limit (max 5 Connections pro Alias)
- Keine automatische Schema-Exploration bei Connect (nur auf Anfrage)

### Akzeptanzkriterien
- [ ] `db_connect("local")` verbindet zu konfigurierter SQLite-Datei
- [ ] `db_tables("local")` listet alle Tabellen mit Spaltenanzahl
- [ ] `db_schema("users", "local")` zeigt Spalten, Typen, Primary Keys, Foreign Keys
- [ ] `db_query("SELECT * FROM users WHERE age > ?", [18], "local")` gibt Markdown-Tabelle zurück
- [ ] Read-Only-Modus: `INSERT`/`UPDATE`/`DELETE` werden abgelehnt ohne Policy-Override
- [ ] SQL-Injection-Test: `db_query("SELECT * FROM users WHERE name = ?", ["'; DROP TABLE users;--"])` ist sicher
- [ ] Query-Timeout nach 30s mit Fehlermeldung
- [ ] Ergebnis-Truncation bei > 1.000 Rows mit Hinweis
- [ ] Connection-String ist in Logs redacted

---

## P1 — API / Integration Hub

### Beschreibung
Framework für externe API-Anbindungen mit vorgefertigten Connectoren und der Möglichkeit, eigene hinzuzufügen. OAuth2-Flow-Management, Credential-Speicher und standardisierte Request/Response-Verarbeitung.

### Dos
- Connector-Interface definieren: `connect()`, `call(method, params)`, `disconnect()`
- Vorgefertigte Connectoren: GitHub API, Jira, Slack (Webhook), Google, X, REST (generisch)
- OAuth2 Authorization Code Flow mit PKCE für Web-APIs
- Credential-Store (verschlüsselt, AES-256-GCM — bestehende `StateEncryption` nutzen)
- Tools: `api_call(connector, method, params)`, `api_list_connectors()`, `api_auth(connector)`
- Rate-Limiting pro Connector (bestehenden `RateLimiter` wiederverwenden)
- Response-Transformation: JSON → strukturierter Tool-Result mit Truncation

### Don'ts
- Keine Credentials in Agent-Memory oder Chat-History speichern
- Keine API-Calls ohne konfigurierte Connector-Instanz (kein Wildcard-HTTP)
- Keine automatische Token-Refresh ohne explizite Konfiguration
- Keinen OAuth-Redirect-Server auf Port 80/443 (ephemeren Port nutzen)
- Keine API-Calls zu internen/privaten Netzwerken (SSRF-Schutz via `UrlValidator`)
- Kein unbegrenztes Response-Buffering (max 5MB pro Response)

### Akzeptanzkriterien
- [ ] GitHub-Connector: `api_call("github", "list_repos", {org: "..."})` gibt Repos zurück
- [ ] Slack-Connector: `api_call("slack", "send_message", {channel: "...", text: "..."})` sendet Nachricht
- [ ] Generischer REST-Connector: Konfigurierbar mit Base-URL + Auth-Header
- [ ] OAuth2-Flow: Browser öffnet Auth-URL, Token wird gespeichert, Refresh funktioniert
- [ ] Credential-Store: Tokens sind verschlüsselt auf Disk, nicht in Logs sichtbar
- [ ] Rate-Limiting: Zu viele Calls → automatische Wartezeit mit Hinweis an Agent
- [ ] SSRF-Schutz: Calls an `localhost`, `10.x.x.x` etc. werden geblockt
- [ ] Connector kann per Tool-Policy pro Agent erlaubt/verboten werden

---

## P1 — Static Analysis Integration

### Beschreibung
Integration externer Analyse-Tools (Linter, SAST, Type-Checker) als Tool-Aufrufe. Der `security-agent` und `review-agent` können damit werkzeuggestützte Analysen durchführen statt nur LLM-basiert zu urteilen.

### Dos
- Wrapper-Tools: `lint(path, tool?)`, `typecheck(path)`, `security_scan(path)`
- Unterstützte Tools: ESLint, Ruff, mypy, Semgrep (jeweils optional installierbar)
- `EnvironmentSnapshot` nutzen, um verfügbare Tools zu erkennen
- Output-Parsing: Tool-spezifische Ausgaben in einheitliches Format (file, line, severity, message, rule)
- Konfigurationsdateien respektieren (`.eslintrc`, `pyproject.toml`, etc.)
- Ergebnisse in bestehende Reflection-Phase einspeisen (harte Fakten statt LLM-Schätzung)

### Don'ts
- Keine Tools automatisch installieren ohne User-Bestätigung
- Keine Analyse auf Dateien außerhalb des Workspace
- Kein vollständiger Workspace-Scan als Default (nur geänderte Dateien oder explizit angefragte)
- Keine Tool-Ausgaben > 50KB untruncated an den Agent senden
- Kein Fail-Hard wenn ein Analyse-Tool nicht installiert ist — graceful skip mit Hinweis

### Akzeptanzkriterien
- [ ] `lint("src/app.py")` erkennt Ruff falls installiert, gibt Findings zurück
- [ ] `lint("src/index.ts", "eslint")` analysiert TypeScript mit ESLint
- [ ] `typecheck("src/")` führt mypy/tsc aus, gibt Typ-Fehler zurück
- [ ] `security_scan("src/")` führt Semgrep aus, gibt Security-Findings zurück
- [ ] Output ist einheitlich formatiert: `{file, line, severity, message, rule}`
- [ ] Nicht-installierte Tools geben klare Meldung statt Crash
- [ ] Ergebnisse fließen in Reflection-Score ein (harte Findings = Score-Abzug)
- [ ] Tool-Policy: `deny: [security_scan]` verhindert Scan für eingeschränkte Agenten

---

## P2 — Multimodaler I/O

### Beschreibung
Erweiterung der Ein-/Ausgabe über Text hinaus: PDF-Parsing, Audio-Transkription, Bild-Generierung und Video-Frame-Analyse. Baut auf dem bestehenden `analyze_image`-Tool (VisionService) auf.

### Dos
- PDF-Parsing: `parse_pdf(path)` → Text + Tabellen + Metadaten (via `pdfplumber` oder `pymupdf`)
- Audio: `transcribe_audio(path)` → Text (via Whisper API oder lokales Whisper)
- Bild-Generierung: `generate_image(prompt)` → Base64-PNG (via DALL-E API oder Stable Diffusion)
- Dokument-Output: `export_pdf(content, path)` → Markdown → PDF-Export
- Frontend: Datei-Upload im Chat (Drag & Drop) für Bilder, PDFs, Audio
- MIME-Type-Detection für automatische Verarbeitung
- Größenlimits: Max 20MB Upload, max 10 Minuten Audio

### Don'ts
- Keine Video-Verarbeitung in Echtzeit (nur Frame-Extraktion)
- Kein Streaming von Audio (nur File-basiert)
- Keine lokale GPU als Hard-Dependency für Whisper/SD (API-Fallback muss existieren)
- Keine Speicherung von Uploads über Session-Ende hinaus ohne explizites Opt-in
- Keine automatische Bild-Generierung ohne User-Anfrage (Kosten-Kontrolle)

### Akzeptanzkriterien
- [ ] `parse_pdf("report.pdf")` extrahiert Text seitenweise mit Seitennummern
- [ ] PDF-Tabellen werden als Markdown-Tabellen extrahiert
- [ ] `transcribe_audio("meeting.mp3")` gibt Transkript mit Timestamps zurück
- [ ] `generate_image("Ein Architekturdiagramm...")` gibt Base64-PNG zurück
- [ ] Frontend zeigt Bilder, PDFs und Audio-Player inline im Chat
- [ ] Datei-Upload via Drag & Drop funktioniert für unterstützte MIME-Types
- [ ] Größenlimit wird vor Upload-Start geprüft und abgelehnt bei Überschreitung
- [ ] Unsupported MIME-Types geben klare Fehlermeldung

---

## P2 — Scheduled Tasks / Cron-Agent

### Beschreibung
Proaktive Aufgabenausführung: Der Agent kann Aufgaben zeitgesteuert oder event-getriggert ausführen (z.B. täglicher Code-Review, Monitoring-Check, Report-Generierung), ohne dass ein User-Request nötig ist.

### Dos
- Cron-Syntax für Scheduling: `schedule_task(cron, prompt, agent_id?)`
- Event-Trigger: Dateisystem-Watcher (Datei geändert → Task), Webhook-Empfang
- Task-Persistenz in SQLite (überlebt Neustarts)
- Task-Liste: `list_scheduled_tasks()`, `cancel_task(id)`
- Ergebnisse in Session-History schreiben (nachträglich abrufbar)
- Max 10 aktive Schedules gleichzeitig
- Jeder Task läuft mit demselben Pipeline-Flow wie ein normaler Request

### Don'ts
- Keine Tasks mit Intervall < 1 Minute (kein Busyloop)
- Keine automatische Eskalation bei Task-Failure (nur Log + Notification)
- Keine unbegrenzten Retries bei fehlgeschlagenen Tasks (max 3, dann deaktivieren)
- Kein Zugriff auf User-Session-State durch Scheduled Tasks (eigene Session)
- Keine Tasks ohne Ablaufdatum (Standard-TTL: 30 Tage)

### Akzeptanzkriterien
- [ ] `schedule_task("0 9 * * *", "Run security scan on src/")` erstellt täglichen Task
- [ ] Task wird zur konfigurierten Zeit ausgeführt und Ergebnis gespeichert
- [ ] `list_scheduled_tasks()` zeigt alle aktiven Tasks mit nächster Ausführung
- [ ] `cancel_task(id)` deaktiviert Task
- [ ] Task-Ergebnis ist im Frontend abrufbar (eigene Session/History)
- [ ] Server-Neustart: Tasks werden aus DB wiederhergestellt
- [ ] Fehlerfall: Task wird nach 3 Fehlschlägen deaktiviert mit Notification
- [ ] Max-Limit: 11. Task wird abgelehnt mit Hinweis

---

## P2 — Knowledge Graph

### Beschreibung
Automatischer Aufbau eines Wissens-Graphen aus Agent-Interaktionen: Entitäten (Dateien, Personen, Konzepte, APIs), Beziehungen (nutzt, implementiert, hängt_ab_von) und Fakten. Ermöglicht Abfragen wie "Welche Services hängen von der Datenbank ab?" über Sessions hinweg.

### Dos
- Graph-Speicher: NetworkX in-memory + JSON-Export für Persistenz (oder SQLite-backed)
- Entitäten-Extraktion: LLM-basiert nach jedem abgeschlossenen Run (Post-Processing)
- Beziehungstypen: `uses`, `implements`, `depends_on`, `related_to`, `created_by`, `modified_by`
- Query-Tool: `knowledge_query(question)` → Graph-Traversal + LLM-Zusammenfassung
- Ingest-Tool: `knowledge_add(entity, relations[])` → manuelles Hinzufügen
- Visualisierung: Graph als Mermaid-Diagramm exportierbar (Visualization Pipeline nutzen)
- Max 10.000 Nodes, LRU-Eviction für alte/unwichtige Nodes

### Don'ts
- Keine Echtzeit-Extraktion während des Runs (nur Post-Processing)
- Keine PII/Credentials als Entitäten speichern
- Kein vollständiger Codebase-Scan zum Aufbau (inkrementell aus Interaktionen)
- Keine Graph-Datenbank als Dependency (NetworkX + JSON reicht)
- Kein automatisches Sharing des Graphen zwischen Usern (Session-/User-scoped)

### Akzeptanzkriterien
- [ ] Nach einem Run werden Entitäten und Beziehungen automatisch extrahiert
- [ ] `knowledge_query("Welche Files benutzen die UserService-Klasse?")` gibt Graph-basierte Antwort
- [ ] `knowledge_add("AuthService", [{"type": "depends_on", "target": "Database"}])` fügt Relation hinzu
- [ ] Graph überlebt Session-Grenzen (Persistenz)
- [ ] Mermaid-Export: `knowledge_visualize("AuthService", depth=2)` zeigt Subgraph
- [ ] Duplikat-Erkennung: Gleiche Entität wird nicht doppelt angelegt
- [ ] LRU-Eviction: Bei > 10.000 Nodes werden älteste Nodes entfernt
- [ ] PII-Filter: Erkannte PII wird nicht als Entität gespeichert

---

## P2 — Deployment / Infrastructure Agent

### Beschreibung
Erweiterung des bestehenden `devops-agent` mit echten Infrastruktur-Tools: Docker Build/Push, Terraform-Plan/Apply, Kubernetes-Inspection, Cloud-CLI-Wrapper.

### Dos
- Docker-Tools: `docker_build(path, tag)`, `docker_push(tag, registry)`, `docker_status()`
- Terraform-Tools: `terraform_plan(path)`, `terraform_apply(path)` (mit Approval-Gate)
- K8s-Tools: `k8s_get(resource, namespace?)`, `k8s_logs(pod, namespace?)`, `k8s_describe(resource)`
- Alle destruktiven Ops (apply, push, delete) hinter Policy-Approval-Gate
- Dry-Run als Default bei Terraform und K8s-Mutationen
- Bestehende Command-Blocklist erweitern für Infra-Befehle

### Don'ts
- Kein `terraform destroy` ohne doppelte Bestätigung (Approval + Confirm)
- Kein `kubectl delete namespace` ohne explizite User-Freigabe
- Keine Cloud-Credentials im Agent-Memory speichern
- Kein automatisches `docker push` an öffentliche Registries
- Kein direkter SSH-Zugriff auf Produktions-Server

### Akzeptanzkriterien
- [ ] `docker_build(".", "myapp:latest")` baut Image und gibt Build-Log zurück
- [ ] `terraform_plan("infra/")` zeigt geplante Änderungen ohne Ausführung
- [ ] `terraform_apply("infra/")` erfordert Policy-Approval vor Ausführung
- [ ] `k8s_get("pods", "default")` listet Pods im Namespace
- [ ] `k8s_logs("api-pod-xyz", "default")` gibt letzte 100 Log-Zeilen zurück
- [ ] Destruktive Befehle ohne Approval werden abgelehnt
- [ ] Credentials in Logs/Memory sind redacted
- [ ] Nicht-installierte Tools (docker, terraform, kubectl) geben klare Fehlermeldung

---

## P3 — Fine-Tuning / Prompt-Optimierung Pipeline

### Beschreibung
Automatische Verbesserung der Prompts basierend auf Reflection-Scores, User-Feedback und Erfolgs-/Misserfolgsraten. Nutzt das bestehende `PromptAbRegistry` und den `ReflectionFeedbackStore`.

### Dos
- Feedback-Loop: User-Thumbs-Up/Down → Score-Aggregation pro Prompt-Variante
- A/B-Test-Auswertung: Statistische Signifikanz prüfen bevor Prompt geändert wird
- Prompt-Versioning: Jede Änderung als neue Version mit Rollback-Möglichkeit
- Automatische Vorschläge: Bei Score < 0.6 über 10+ Runs → Prompt-Optimierungs-Vorschlag
- Dashboard: Prompt-Performance-Übersicht im Frontend

### Don'ts
- Keine automatischen Prompt-Änderungen ohne User-Review
- Keine Optimierung basierend auf < 10 Datenpunkten
- Kein Fine-Tuning des Basis-Models (nur Prompt-Ebene)
- Keine Speicherung von User-Inhalten für Trainings-Zwecke ohne Consent

### Akzeptanzkriterien
- [ ] User-Feedback (👍/👎) wird pro Run gespeichert und dem Prompt-Variant zugeordnet
- [ ] Nach 20+ Runs zeigt Dashboard Prompt-Performance-Vergleich
- [ ] Bei signifikantem Score-Unterschied wird Variante B automatisch vorgeschlagen
- [ ] Prompt-Rollback auf vorherige Version mit einem Klick
- [ ] Opt-in für automatische Optimierung (default: aus)

---

## P3 — Multi-User / Collaborative Mode

### Beschreibung
Unterstützung für mehrere Benutzer in geteilten oder isolierten Workspaces mit rollenbasierter Zugriffssteuerung.

### Dos
- User-Identifikation (einfach: API-Key pro User, kein Full-Auth-System)
- Rollen: `admin` (voller Zugriff), `developer` (Standard-Tools), `viewer` (Read-Only)
- Per-User Tool-Policy (Admin kann alles, Developer kein `terraform_apply`, Viewer nur Lesen)
- Shared Workspace: Mehrere User können denselben Workspace nutzen (File-Locking)
- Audit-Trail: Wer hat welchen Run gestartet, welche Tools aufgerufen
- Session-Isolation: User sehen nur eigene Sessions (außer Admin)

### Don'ts
- Kein vollständiges Identity-Management bauen (kein LDAP, kein OAuth-Login-Flow)
- Keine Echtzeit-Collaboration (kein Google-Docs-Editing)
- Keine User-Daten an LLM-Provider senden (nur Prompts)
- Kein Sharing von Credentials zwischen Usern

### Akzeptanzkriterien
- [ ] API-Key-basierte User-Identifikation funktioniert
- [ ] Rollen-Zuweisung pro User konfigurierbar
- [ ] Tool-Policy reagiert auf User-Rolle (Viewer kann kein `write_file`)
- [ ] Audit-Log zeigt: User, Timestamp, Action, Tool, Result-Status
- [ ] Session-Isolation: User A sieht nicht Sessions von User B
- [ ] Admin kann alle Sessions einsehen

---

## P3 — Streaming / Real-Time Data

### Beschreibung
Fähigkeit, auf Datenströme zu reagieren: Log-Monitoring, Event-Stream-Verarbeitung, Anomalie-Erkennung in Echtzeit.

### Dos
- Log-Tail-Tool: `tail_log(path, filter?, lines=100)` mit Live-Follow-Modus
- Event-Listener: Webhook-Endpoint der Events an den Agent weiterleitet
- Anomalie-Erkennung: Einfache statistische Abweichung (Z-Score) auf numerische Streams
- Integration mit Background-Commands für langlebige Streams

### Don'ts
- Keine Kafka/RabbitMQ als Hard-Dependency
- Kein unbegrenztes Stream-Buffering (max 1.000 Events, dann Window-Eviction)
- Keine Echtzeit-Garantien (Best-Effort Processing)

### Akzeptanzkriterien
- [ ] `tail_log("/var/log/app.log", "ERROR")` gibt gefilterte Log-Zeilen zurück
- [ ] Webhook-Endpoint empfängt Events und triggert Agent-Task
- [ ] Anomalie-Erkennung: Alert bei > 3 Standardabweichungen in Metrik-Stream
- [ ] Stream-Window: Ältere Events werden bei Überlauf verworfen

---

## Zusammenfassung

| Prio | Feature | Kategorie | Abhängigkeiten |
|------|---------|-----------|----------------|
| P0 | Browser Control | Tool | — |
| P0 | RAG Engine | Infrastruktur | Embedding-Modell |
| P0 | Code Interpreter/REPL | Tool | — |
| P1 | Visualization Pipeline | Frontend + Backend | Code Interpreter (optional) |
| P1 | Structured Data/DB | Tool | — |
| P1 | API/Integration Hub | Infrastruktur | StateEncryption, UrlValidator |
| P1 | Static Analysis | Tool | Externe Linter (optional) |
| P2 | Multimodaler I/O | Tool + Frontend | Visualization Pipeline |
| P2 | Scheduled Tasks | Infrastruktur | — |
| P2 | Knowledge Graph | Infrastruktur | RAG Engine (optional) |
| P2 | Deployment/Infra | Tool | Policy Approval |
| P3 | Fine-Tuning Pipeline | Infrastruktur | ReflectionFeedbackStore, PromptAbRegistry |
| P3 | Multi-User/Collab | Infrastruktur | — |
| P3 | Streaming/Real-Time | Tool | Background Commands |
