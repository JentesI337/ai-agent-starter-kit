# Security Audit — AI Agent Starter Kit

> **Datum:** 6. März 2026  
> **Scope:** Vollständiger Backend + Frontend Code-Review  
> **Methodik:** Manuelles Source-Code-Audit (White-Box), statische Analyse  
> **Risikobewertung:** OWASP-Severity (CRITICAL / HIGH / MEDIUM / LOW / INFO)

---

## Executive Summary

Das AI Agent Starter Kit weist **98 Findings** auf, verteilt über Backend (Python/FastAPI),
Frontend (Angular) und Infrastruktur. Die kritischsten Risiken liegen in:

1. **Fehlende Authentifizierung** auf allen REST- und WebSocket-Endpunkten
2. **Arbitrary Code Execution** über Self-Healing-Loop und Code-Sandbox-Bypass
3. **Secret-Leakage** über den `config.health`-Endpunkt
4. **Shell-basierte Command-Allowlist** die sich selbst unterminiert

Das Projekt ist als POC deklariert — dennoch sind mehrere Findings auch in
Entwicklungsumgebungen ausnutzbar (z.B. über Prompt Injection → Command Execution).

### Statistik

| Severity | Anzahl | Anteil |
|----------|--------|--------|
| CRITICAL | 9 | 9 % |
| HIGH | 18 | 18 % |
| MEDIUM | 38 | 39 % |
| LOW | 24 | 25 % |
| INFO | 9 | 9 % |
| **Gesamt** | **98** | 100 % |

---

## Inhaltsverzeichnis

1. [Authentifizierung & Autorisierung](#1-authentifizierung--autorisierung)
2. [Command Execution & Code Sandbox](#2-command-execution--code-sandbox)
3. [Prompt Injection & LLM Security](#3-prompt-injection--llm-security)
4. [MCP Bridge (Model Context Protocol)](#4-mcp-bridge-model-context-protocol)
5. [State, Memory & Kryptografie](#5-state-memory--kryptografie)
6. [WebSocket-Sicherheit](#6-websocket-sicherheit)
7. [REST-API & Routing](#7-rest-api--routing)
8. [Configuration & Secrets Management](#8-configuration--secrets-management)
9. [Policy & Approval System](#9-policy--approval-system)
10. [Self-Healing & Learning Loop](#10-self-healing--learning-loop)
11. [Runtime Manager & Subprocesses](#11-runtime-manager--subprocesses)
12. [Frontend-Sicherheit](#12-frontend-sicherheit)
13. [Dependencies & Supply Chain](#13-dependencies--supply-chain)
14. [SSRF & Netzwerk-Sicherheit](#14-ssrf--netzwerk-sicherheit)
15. [Information Disclosure](#15-information-disclosure)
16. [Race Conditions & Concurrency](#16-race-conditions--concurrency)
17. [Positive Befunde](#17-positive-befunde)
18. [Priorisierte Maßnahmen-Roadmap](#18-priorisierte-maßnahmen-roadmap)

---

## 1. Authentifizierung & Autorisierung

### AUTH-01 — Keine WebSocket-Authentifizierung (CRITICAL)

| | |
|---|---|
| **Datei** | `backend/app/ws_handler.py` L147–150 |
| **Severity** | CRITICAL |
| **Beschreibung** | `handle_ws_agent()` ruft sofort `websocket.accept()` auf ohne jegliche Token-Prüfung. Jeder Netzwerk-Client kann eine WebSocket-Verbindung öffnen und Agenten-Befehle senden. `api_auth_required` (Default: `False`) wird auf WebSocket-Ebene nicht geprüft. |
| **Impact** | Unauthentifizierter Zugriff auf alle Agent-Funktionalitäten inkl. Dateioperationen, Command Execution, Session-Manipulation. |
| **Empfehlung** | Token-/API-Key-basierte Auth über Query-Parameter oder First-Message-Handshake. Verbindung bei fehlendem/ungültigem Token ablehnen. |

### AUTH-02 — Keine REST-API-Authentifizierung (CRITICAL)

| | |
|---|---|
| **Datei** | `backend/app/routers/run_api.py` L20–31, `control_runs.py`, `control_sessions.py`, `control_tools.py` |
| **Severity** | CRITICAL |
| **Beschreibung** | Alle REST-Endpunkte (Run-API, Control Plane, Session, Tools, Workflows) sind ohne Auth-Middleware zugänglich. `api_auth_required` existiert als Config-Flag, wird aber nirgends enforced. |
| **Impact** | Jeder Netzwerk-Client kann Runs starten, Sessions manipulieren, Config auslesen, Policy-Regeln ändern. |
| **Empfehlung** | FastAPI-Dependency mit Bearer-Token-Validierung auf allen Routern einführen. |

### AUTH-03 — Keine Cross-Session-Autorisierung (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/handlers/session_handlers.py` L173–215 |
| **Severity** | HIGH |
| **Beschreibung** | `sessions.send` erlaubt das Senden von Nachrichten an beliebige `session_id`s ohne Ownership-Prüfung. |
| **Impact** | Nachrichten-Injection in fremde Sessions, Manipulation laufender Agenten-Konversationen. |
| **Empfehlung** | Session-Ownership-Prüfung (Session ↔ Connection-Binding) implementieren. |

### AUTH-04 — Sessions-Patch ohne Schlüssel-Allowlist (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/handlers/session_handlers.py` L385–420 |
| **Severity** | MEDIUM |
| **Beschreibung** | `sessions.patch` übernimmt beliebige Meta-Felder aus dem Request. Sicherheitsrelevante Felder wie `run_state_hard_failed` können manipuliert werden. |
| **Impact** | Zustandsmanipulation laufender Runs. |
| **Empfehlung** | Allowlist für erlaubte Meta-Schlüssel einführen. |

### AUTH-05 — Session-ID Validierung inkonsistent (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/ws_handler.py` L735–740 |
| **Severity** | MEDIUM |
| **Beschreibung** | Für `SUPPORTED_WS_INBOUND_TYPES`-Nachrichten wird `validate_session_id_format()` nicht aufgerufen — die Validierung greift nur für unsupported Types (Envelope-Pfad). |
| **Empfehlung** | Einheitliche Session-ID-Validierung auf alle Nachrichtentypen anwenden. |

---

## 2. Command Execution & Code Sandbox

### CMD-01 — Sandbox ohne OS-Level-Isolation (CRITICAL)

| | |
|---|---|
| **Datei** | `backend/app/services/code_sandbox.py` L98–111 |
| **Severity** | CRITICAL |
| **Beschreibung** | Die `process`- und `direct`-Strategien führen Code per `subprocess` aus, geschützt nur durch statische Regex-Checks auf den Quelltext. Kein Seccomp, keine Namespaces, keine Cgroups, kein User-Wechsel. |
| **Impact** | Jeder Bypass der statischen Analyse = Full RCE mit Server-Prozess-Rechten. |
| **Empfehlung** | `docker`-Strategie als Default erzwingen. `process`/`direct` nur nach explizitem Opt-in mit Warning. |

### CMD-02 — Statische Code-Analyse trivial umgehbar (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/services/code_sandbox.py` L409–527 |
| **Severity** | HIGH |
| **Beschreibung** | Netzwerk-, Filesystem- und Dangerous-Constructs-Erkennung sind regex-basiert und durch String-Konkatenation (`__import__('sock'+'et')`), `bytes.fromhex()`, `object.__subclasses__()`, `os.system()`, `os.popen()` etc. umgehbar. |
| **Impact** | Sandbox-Escape bei `process`-Strategie. |
| **Empfehlung** | Regex-Analyse nur als zusätzliche Schicht behandeln. Primärer Schutz muss OS-Level sein. |

### CMD-03 — Blocklist-basierter Command-Safety-Filter (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/tools.py` L29–54 |
| **Severity** | MEDIUM |
| **Beschreibung** | Deny-Listen-Regex für gefährliche Befehle. Umgehbar durch Unicode-Homoglyphen, Encoding-Tricks, Variablenexpansion oder unbekannte Befehle. |
| **Impact** | Falsche Sicherheit — neue gefährliche Befehle müssen manuell nachgetragen werden. |
| **Empfehlung** | Allowlist-only-Ansatz (existiert bereits separat) als primären Schutzmechanismus verwenden. |

### CMD-04 — `write_file` ohne Extension-Einschränkung (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/tools.py` L136–142 |
| **Severity** | HIGH |
| **Beschreibung** | Der Agent kann beliebige Dateitypen schreiben: `.exe`, `.bat`, `.ps1`, `.sh`, `.pem`, `.env`. Ein Prompt-Injection-Angriff kann ausführbare Payloads im Workspace ablegen. |
| **Impact** | Malware-Deployment, Credential-Override via `.env`. |
| **Empfehlung** | Extension-Deny-List für executable Formate. Schreiben von `.env`-Dateien separat kontrollieren. |

### CMD-05 — `code_execute` strategy-Parameter nicht validiert (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/tools.py` L858–904 |
| **Severity** | MEDIUM |
| **Beschreibung** | Ein LLM-kontrollierter `strategy="direct"` Parameter kann Code direkt im Prozess-Kontext ausführen und die Sandbox umgehen. |
| **Empfehlung** | Erlaubte Strategien auf `["process", "docker"]` beschränken. |

### CMD-06 — `shlex.split(posix=True)` auf Windows (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/tools.py` L839–845 |
| **Severity** | HIGH |
| **Beschreibung** | `posix=True` behandelt `\` als Escape-Zeichen, was bei Windows-Pfaden wie `C:\Users\...` zu fehlerhaftem Parsing und potentiellem Safety-Check-Bypass führen kann. |
| **Empfehlung** | Plattformabhängige Tokenisierung oder Pfad-Awareness in der Tokenizer-Logik. |

### CMD-07 — Background-Command Log-Dateien ungeschützt (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/tools.py` L274–289 |
| **Severity** | MEDIUM |
| **Beschreibung** | Log-Dateien unter `.agent_background/` werden ohne Zugriffsbeschränkung erstellt und können sensible Command-Outputs enthalten. |
| **Empfehlung** | Permissions auf `0o600` setzen. Tempfile-Modul mit sicherem Verzeichnis nutzen. |

### CMD-08 — Temporary Override per Prompt Injection einsetzbar (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/tools.py` L954–968 |
| **Severity** | MEDIUM |
| **Beschreibung** | `allow_command_leader_temporarily` kann per Prompt-Injection getriggert werden. Ein einzelner Aufruf reicht für Schaden aus (single-use). |
| **Empfehlung** | Explizite User-Bestätigung für temporäre Overrides erzwingen. |

### CMD-09 — Package-Manager Shell-Pipes (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/services/package_manager_adapter.py` L83–84 |
| **Severity** | HIGH |
| **Beschreibung** | Shell-Befehle enthalten Pipes/Redirects (`2>/dev/null | head -c 8192`), die `shell=True` erfordern. Command-Injection über manipulierte Package-Namen (Newlines) möglich. |
| **Impact** | Arbitrary Command Execution über manipulierte Paketnamen. |
| **Empfehlung** | Shell-Pipes entfernen. Output-Truncation im Python-Code. Commands als Argument-Listen. |

### CMD-10 — Package-Name Sanitisierung unvollständig (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/package_manager_adapter.py` L227–228 |
| **Severity** | MEDIUM |
| **Beschreibung** | Deny-List-basierte `_sanitize`-Funktion filtert Newlines, Null-Bytes und Control-Characters nicht. |
| **Empfehlung** | Allowlist: nur `[a-zA-Z0-9._-@/]` erlauben. |

### CMD-11 — Environment-Snapshot Rollback Command Injection (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/services/environment_snapshot.py` L133–138 |
| **Severity** | HIGH |
| **Beschreibung** | `_uninstall_command` konstruiert Shell-Befehle via f-String-Interpolation (`f"pip uninstall -y {package}"`). Package-Namen mit Sonderzeichen ermöglichen Command Injection. |
| **Empfehlung** | Package-Name-Regex (`^[a-zA-Z0-9._-]+$`) und `shlex.quote()`. |

### CMD-12 — Sandbox Temp-Directory im Workspace (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/code_sandbox.py` L286–300 |
| **Severity** | MEDIUM |
| **Beschreibung** | Temp-Verzeichnisse werden innerhalb des Workspace erstellt (`dir=str(self.workspace_root)`). Bei geteiltem Workspace: Symlink-Race auf Script-Dateien möglich. |
| **Empfehlung** | System-Default-Tempdir verwenden oder Permissions auf `0o700` setzen. |

### CMD-13 — Sandbox Env leakt Python-Pfade (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/code_sandbox.py` L386–405 |
| **Severity** | MEDIUM |
| **Beschreibung** | `PYTHONPATH`, `PYTHONHOME`, `CONDA_PREFIX` etc. werden in die Sandbox-Umgebung durchgereicht. Code-Injection über manipulierten `PYTHONPATH` möglich. |
| **Empfehlung** | Nur `PATH`, `SYSTEMROOT`, `TEMP`, `HOME` durchreichen. Python `-I` Flag verwenden. |

---

## 3. Prompt Injection & LLM Security

### PI-01 — Injection-Filter unvollständig (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/state/context_reducer.py` L101–117 |
| **Severity** | MEDIUM |
| **Beschreibung** | `_INJECTION_PATTERNS` erfassen gängige Muster, aber Unicode-Homoglyphen, Base64-kodierte Anweisungen, Character-Splitting und Zero-Width-Characters werden nicht erkannt. |
| **Empfehlung** | Unicode-Normalisierung (NFKC) vor Pattern-Matching. Mehrschichtiger Ansatz mit separatem Classifier. |

### PI-02 — Content-Boundary-Tags nicht deterministisch (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/prompt_kernel_builder.py` L146–161 |
| **Severity** | MEDIUM |
| **Beschreibung** | `<content_boundary>`-Tags sind textbasierte Hinweise, die vom LLM ignoriert werden können. Ein sorgfältig erstellter Prompt in Tool-Output könnte den Boundary-Kontext durchbrechen. |
| **Empfehlung** | Tool-Output in separaten Message-Turns senden (nicht inline). Inhärente Limitation. |

### PI-03 — Memory nicht sanitisiert (LOW)

| | |
|---|---|
| **Datei** | `backend/app/state/context_reducer.py` L100 |
| **Severity** | LOW |
| **Beschreibung** | `_sanitize_tool_output` wird nur für Tool-Outputs aufgerufen, nicht für Memory-Lines. Kompromittierte Memory-Einträge bleiben unsanitisiert. |
| **Empfehlung** | Auch `memory_lines` durch Sanitization laufen lassen. |

### PI-04 — Auto-injizierte Commands bei High-Confidence Intent (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/services/tool_execution_manager.py` L1074–1090 |
| **Severity** | HIGH |
| **Beschreibung** | Bei `intent == "execute_command"` und `confidence == "high"` wird ein `run_command`-Aufruf automatisch injiziert. Per Prompt Injection kann das LLM instruiert werden, einen bestimmten Befehl als "hoch-sicher" auszugeben. |
| **Impact** | Prompt Injection → Automatic Command Execution. |
| **Empfehlung** | Auto-Injection nur nach expliziter User-Bestätigung. Command-Policy bleibt unabhängig aktiv. |

### PI-05 — Context-Guard Injection-Neutralisierung unvollständig (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/tool_result_context_guard.py` L84–113 |
| **Severity** | MEDIUM |
| **Beschreibung** | Identische Schwäche wie PI-01 — Unicode-Varianten, Zero-Width-Characters, Encoding-basierte Umgehungen werden nicht erfasst. |
| **Empfehlung** | Unicode-Normalisierung (NFKC) vor Pattern-Matching anwenden. |

---

## 4. MCP Bridge (Model Context Protocol)

### MCP-01 — Overly Permissive Command Allowlist (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/services/mcp_bridge.py` L18–22 |
| **Severity** | HIGH |
| **Beschreibung** | Allowlist enthält `node`, `npx`, `python`, `python3`, `uvx`, `docker`. Diese erlauben Ausführung beliebigen Codes (`node backdoor.js`, `python malware.py`). |
| **Impact** | Ein bösartiger MCP-Server-Eintrag die der agent sich selbst anlegt in der Config = Full RCE. |
| **Empfehlung** | Auf spezifische MCP-Server-Binaries beschränken. Vollqualifizierte Pfade erfordern. |

### MCP-02 — Shell-Metacharacter-Check unvollständig (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/mcp_bridge.py` L362–367 |
| **Severity** | MEDIUM |
| **Beschreibung** | Prüft nur `;`, `&&`, `||`, `|`, `` ` ``, `$(`. Fehlend: `\n`, `\r`, Null-Bytes, `>`, `<`, `{`, `}`, `!`. |
| **Empfehlung** | Allowlist-Pattern (nur alphanumerisch + definierte Sonderzeichen). |

### MCP-03 — Env-Variablen unvalidiert an MCP-Server (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/mcp_bridge.py` L369–375 |
| **Severity** | MEDIUM |
| **Beschreibung** | MCP-Server-Konfiguration kann `PATH`, `LD_PRELOAD`, `PYTHONSTARTUP` überschreiben. |
| **Impact** | Privilege Escalation über Environment-Manipulation. |
| **Empfehlung** | Env-Variablen-Allowlist. Blockieren: `LD_PRELOAD`, `LD_LIBRARY_PATH`, `PYTHONSTARTUP`. |

### MCP-04 — Keine SSRF-Prüfung für MCP HTTP/SSE-URLs (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/mcp_bridge.py` L401–414 |
| **Severity** | MEDIUM |
| **Beschreibung** | Kein Private-IP-Check, keine Hostname-Validierung. Ein MCP-Server auf `http://169.254.169.254` (Cloud-Metadata) konfigurierbar. |
| **Empfehlung** | SSRF-Schutzlogik aus `tools.py._enforce_safe_web_target()` wiederverwenden. |

### MCP-05 — Keine Auth für MCP HTTP/SSE-Verbindungen (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/mcp_bridge.py` L401–414 |
| **Severity** | MEDIUM |
| **Beschreibung** | Keine TLS-Pflicht, keine Token-Auth. MITM kann bösartige Tool-Definitionen injizieren. |
| **Empfehlung** | TLS-Pflicht für remote MCP-Verbindungen. Optionale API-Key-Authentifizierung. |

### MCP-06 — Kein Content-Size-Limit auf MCP HTTP-Responses (LOW)

| | |
|---|---|
| **Datei** | `backend/app/services/mcp_bridge.py` L441–450 |
| **Severity** | LOW |
| **Beschreibung** | `response.json()` liest die gesamte Response. DoS via oversized Responses möglich. |
| **Empfehlung** | Content-Length-Check oder Stream-basiertes Reading mit Limit. |

### MCP-07 — Allowlist nur erweiterbar, nicht einschränkbar (LOW)

| | |
|---|---|
| **Datei** | `backend/app/services/mcp_bridge.py` L26–31 |
| **Severity** | LOW |
| **Beschreibung** | `MCP_COMMAND_ALLOWLIST` erweitert stets die Default-Liste. Einschränkung nicht möglich. |
| **Empfehlung** | `MCP_COMMAND_ALLOWLIST_OVERRIDE` Mechanismus implementieren. |

---

## 5. State, Memory & Kryptografie

### CRYPTO-01 — Ephemerer Encryption-Key bei fehlendem Env (CRITICAL)

| | |
|---|---|
| **Datei** | `backend/app/services/state_encryption.py` L46–49 |
| **Severity** | CRITICAL |
| **Beschreibung** | Ohne `STATE_ENCRYPTION_KEY` wird ein zufälliger Key pro Prozess generiert. Verschlüsselte Daten überleben keinen Neustart und sind unwiederbringlich verloren. |
| **Impact** | Datenverlust bei jedem Restart. Kein Warn-Log oder Start-Abort. |
| **Empfehlung** | Startup abbrechen wenn kein persistenter Key gesetzt ist (Production). Mindestens WARNING-Log. |

### CRYPTO-02 — Keine Key-Rotation (CRITICAL)

| | |
|---|---|
| **Datei** | `backend/app/services/state_encryption.py` L50 |
| **Severity** | CRITICAL |
| **Beschreibung** | `_ENCRYPTION_KEY` wird als Modul-Seiteneffekt einmalig geladen. Kein Key-Rotations-Mechanismus vorhanden. |
| **Empfehlung** | Key-ID im Ciphertext-Präfix verankern. Rotation unterstützen. |

### CRYPTO-03 — XOR-Fallback kryptographisch schwach (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/services/state_encryption.py` L76–82 |
| **Severity** | HIGH |
| **Beschreibung** | Ohne `cryptography`-Paket: deterministisches XOR-Keystream via HMAC-SHA256. Kein Schutz gegen Known-Plaintext-Angriffe. |
| **Impact** | Nur Obfuskation, keine echte Verschlüsselung. |
| **Empfehlung** | `cryptography` als harte Abhängigkeit. XOR-Fallback entfernen oder laut warnen. |

### CRYPTO-04 — Abgeschnittener HMAC (64 Bit) (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/state_encryption.py` L79, `session_security.py` L74 |
| **Severity** | MEDIUM |
| **Beschreibung** | `hexdigest()[:16]` = 64 Bit. Birthday-Angriffe mit ~2^32 Aufwand. Betrifft State-Encryption und Session-Signing. |
| **Empfehlung** | Mindestens 128 Bit (32 Hex-Zeichen). |

### CRYPTO-05 — AES-GCM ohne Associated Data (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/state_encryption.py` L72 |
| **Severity** | MEDIUM |
| **Beschreibung** | `aesgcm.encrypt(nonce, data, None)` — kein `run_id` als AAD. Ciphertext-Swapping zwischen Runs möglich. |
| **Empfehlung** | `aesgcm.encrypt(nonce, data, run_id.encode())` verwenden. |

### CRYPTO-06 — Policy HMAC Key Reuse (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/state_encryption.py` L143–145 |
| **Severity** | MEDIUM |
| **Beschreibung** | `_POLICY_HMAC_KEY` fällt auf `_ENCRYPTION_KEY` zurück. Zwei Sicherheitsfunktionen am selben Schlüssel. |
| **Empfehlung** | Separaten dedizierten Schlüssel erzwingen. |

### CRYPTO-07 — Ephemerer Session-Signing-Key (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/services/session_security.py` L18–20 |
| **Severity** | HIGH |
| **Beschreibung** | `_SESSION_SIGNING_KEY` wird per `secrets.token_bytes(32)` generiert wenn `SESSION_SIGNING_KEY` nicht gesetzt. Sessions werden nach Neustart ungültig ohne Warn-Mechanismus. |
| **Empfehlung** | Persistenten Key erzwingen oder Sessions bei Neustart explizit invalidieren. |

### CRYPTO-08 — Kein Session-Ablauf (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/session_security.py` L31–33 |
| **Severity** | MEDIUM |
| **Beschreibung** | `validate_session_id()` prüft den Timestamp nicht auf Ablauf. Sessions unbegrenzt gültig. |
| **Empfehlung** | Maximale Session-Lebensdauer konfigurierbar machen. |

### STATE-01 — `run_id` als Dateiname ohne Path-Traversal-Schutz (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/state/state_store.py` L241–244 |
| **Severity** | MEDIUM |
| **Beschreibung** | `_run_file()` nutzt `run_id` in Pfadkonstruktion ohne Prüfung auf `../`. Die `_validate_guardrails()` prüft nur `session_id`, nicht `run_id`. |
| **Empfehlung** | `run_id` auf `[a-zA-Z0-9_-]` beschränken. Resolved-Path gegen `runs_dir` prüfen. |

### STATE-02 — Snapshots nicht verschlüsselt (LOW)

| | |
|---|---|
| **Datei** | `backend/app/state/state_store.py` L273–280 |
| **Severity** | LOW |
| **Beschreibung** | Run-Dateien werden verschlüsselt, Snapshots bleiben Klartext. Inkonsistente Encryption-at-Rest. |
| **Empfehlung** | Snapshots ebenfalls verschlüsseln. |

### MEM-01 — Session-ID Path-Traversal in Memory (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/memory.py` L149–151 |
| **Severity** | HIGH |
| **Beschreibung** | `_normalize_session_id()` erlaubt `..` (zwei Punkte). Potentieller Zugriff auf Dateien außerhalb des Memory-Verzeichnisses. |
| **Empfehlung** | `..`-Sequenzen blockieren. Resultierenden Pfad gegen `persist_dir` resolven. |

### MEM-02 — Memory-Dateien unverschlüsselt (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/memory.py` L142–143 |
| **Severity** | MEDIUM |
| **Beschreibung** | JSONL-Memory-Dateien im Klartext. Kein Encryption-at-Rest. |
| **Empfehlung** | Verschlüsselung analog zum State Store. |

### MEM-03 — Keine Secret-Redaction in Memory (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/memory.py` L139–141 |
| **Severity** | MEDIUM |
| **Beschreibung** | Memory-Einträge werden unverändert auf Disk geschrieben. Secrets in Agent-Konversationen verbleiben in JSONL-Dateien. |
| **Empfehlung** | Sensitive-Content-Redaction analog zum State Store. |

### MEM-04 — Kein Längenlimit für Memory-Content (LOW)

| | |
|---|---|
| **Datei** | `backend/app/memory.py` L31 |
| **Severity** | LOW |
| **Beschreibung** | Keine Obergrenze für einzelne Memory-Einträge. DoS-Vektor. |
| **Empfehlung** | Maximale Content-Länge einführen. |

### LTM-01 — LTM-Datenbank unverschlüsselt (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/long_term_memory.py` L49–50 |
| **Severity** | MEDIUM |
| **Beschreibung** | SQLite-DB enthält Fehlerbeschreibungen, User-Präferenzen, Sessions — alles unverschlüsselt. |
| **Empfehlung** | SQLCipher oder Application-Layer-Encryption. |

### LTM-02 — Kein oberes Limit für Query-Results (LOW)

| | |
|---|---|
| **Datei** | `backend/app/services/long_term_memory.py` L189 |
| **Severity** | LOW |
| **Beschreibung** | `limit`-Parameter erlaubt beliebig große Werte. |
| **Empfehlung** | Obere Grenze (z.B. 500) validieren. |

---

## 6. WebSocket-Sicherheit

### WS-01 — Unbegrenzte WebSocket-Verbindungen (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/ws_handler.py` L147 |
| **Severity** | MEDIUM |
| **Beschreibung** | Kein Connection-Limit. Ein Angreifer kann tausende WS-Verbindungen öffnen → Server-Ressourcen-Erschöpfung. |
| **Empfehlung** | Pro-IP-Verbindungslimit einführen. Maximale gleichzeitige Verbindungen konfigurierbar machen. |

### WS-02 — `base_url` in Events offengelegt (LOW)

| | |
|---|---|
| **Datei** | `backend/app/ws_handler.py` L1139–1145 |
| **Severity** | LOW |
| **Beschreibung** | Interne `base_url` wird über `runtime_switch_done`-Event an den Client gesendet. |
| **Empfehlung** | `base_url` nicht an den Client senden. |

### WS-03 — ALSO_ALLOW_BLOCKLIST hartcodiert und dupliziert (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/ws_handler.py` L380–391, L1062–1073 |
| **Severity** | HIGH |
| **Beschreibung** | Tool-Blockliste ist dupliziert (DRY-Verletzung) und nicht erweiterbar. Neue gefährliche Tools werden nicht automatisch abgefangen. |
| **Empfehlung** | Zentrale, konfigurierbare Blockliste. Allowlist-Ansatz evaluieren. |

---

## 7. REST-API & Routing

### API-01 — Untypisierte Request-Bodys (MEDIUM)

| | |
|---|---|
| **Dateien** | `backend/app/routers/run_api.py` L21–22, `control_runs.py` L33–36 |
| **Severity** | MEDIUM |
| **Beschreibung** | `dict` als Body-Typ erlaubt beliebige JSON-Payloads. Schema-Validierung erst tief im Handler. |
| **Empfehlung** | Pydantic-Request-Models direkt in Routern verwenden. |

### API-02 — `run_id` Path-Parameter unvalidiert (LOW)

| | |
|---|---|
| **Datei** | `backend/app/routers/run_api.py` L29–30 |
| **Severity** | LOW |
| **Beschreibung** | Beliebige Strings als `run_id` akzeptiert (kein UUID-Check). |
| **Empfehlung** | UUID-Format oder Regex-Constraint validieren. |

### API-03 — CSRF-Protection fehlt (HIGH)

| | |
|---|---|
| **Dateien** | Alle POST-Endpunkte |
| **Severity** | HIGH |
| **Beschreibung** | CORS konfiguriert, aber bei `allow_credentials=True` ohne CSRF-Token können Cross-Origin-Requests mit Browser-Cookies durchgeführt werden. |
| **Empfehlung** | CSRF-Token-Mechanismus einführen (`starlette-csrf` oder Custom-Middleware). |

### API-04 — Keine Request-Body-Size-Limits (MEDIUM)

| | |
|---|---|
| **Dateien** | Alle Router |
| **Severity** | MEDIUM |
| **Beschreibung** | REST-Endpunkte haben kein Body-Size-Limit (WebSocket hat 128 KB). Memory-Exhaustion möglich. |
| **Empfehlung** | 1 MB Body-Limit als Middleware setzen. |

### API-05 — Unbegrenztes Polling in `wait_for_run_result` (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/handlers/run_handlers.py` L498–520 |
| **Severity** | MEDIUM |
| **Beschreibung** | `timeout_ms` akzeptiert beliebig große Werte. Erzeugt lang laufende Tasks. |
| **Empfehlung** | Maximalen Timeout-Wert erzwingen (z.B. 5 Minuten). |

---

## 8. Configuration & Secrets Management

### CFG-01 — API-Keys als Plain-Text in Settings (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/config.py` L1461–1465 |
| **Severity** | HIGH |
| **Beschreibung** | `api_auth_token`, `llm_api_key`, `web_search_api_key`, `vision_api_key` als reguläre Strings. Jeder `Settings`-Dump leakt diese. Kein `SecretStr`, kein `repr=False`. |
| **Empfehlung** | Pydantic `SecretStr` verwenden. Serialisierung mit `model_dump(exclude=...)` absichern. |

### CFG-02 — `api_auth_required` Default False (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/config.py` L1460 |
| **Severity** | HIGH |
| **Beschreibung** | Auth ist standardmäßig deaktiviert. Produktion ohne explizites Setzen = offenes System. |
| **Empfehlung** | Default `True` setzen oder an `app_env == "production"` koppeln. |

### CFG-03 — Command-Allowlist enthält Shells (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/config.py` L1082–1085 |
| **Severity** | HIGH |
| **Beschreibung** | Default-Allowlist enthält `powershell`, `cmd`, `bash`, `sh`. Jede dieser Shells erlaubt beliebige Befehle (`bash -c "rm -rf /"`), womit die Allowlist-Einschränkung effektiv umgangen wird. |
| **Impact** | Die gesamte Command-Allowlist-Sicherheit wird unterminiert. |
| **Empfehlung** | Shells aus der Default-Allowlist entfernen. Deep-Parsing-Layer für Shell-Escape-Ketten. |

### CFG-04 — LLM API Key fällt auf Auth-Token zurück (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/llm_client.py` L44–48 |
| **Severity** | HIGH |
| **Beschreibung** | `settings.llm_api_key or settings.api_auth_token` — ohne LLM-Key wird der interne Auth-Token an den externen LLM-Provider gesendet. |
| **Impact** | Internal Auth-Token-Leakage an externen Dienst. |
| **Empfehlung** | Kein Fallback. Wenn `llm_api_key` leer, keinen Authorization-Header senden. |

### CFG-05 — MCP-Config aus unkontrolliertem Dateipfad (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/config.py` L108–120 |
| **Severity** | MEDIUM |
| **Beschreibung** | `_parse_mcp_servers_config` öffnet beliebige JSON-Dateien basierend auf Env-Variable ohne Pfadvalidierung. |
| **Empfehlung** | Pfad gegen `workspace_root` validieren (Prefix-Check). |

### CFG-06 — CORS mit `allow_headers=["*"]` (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/app_setup.py` L57 |
| **Severity** | MEDIUM |
| **Beschreibung** | Alle Custom-Header werden zugelassen. In Kombination mit Credentials zu permissiv. |
| **Empfehlung** | Nur benötigte Header: `["Content-Type", "Authorization", "X-XSRF-TOKEN", "Idempotency-Key"]`. |

### CFG-07 — Model-Name ohne Validierung (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/config.py` L1135–1140 |
| **Severity** | MEDIUM |
| **Beschreibung** | Manipulierte Modellnamen könnten bei Ollama-Pulls zu unerwarteten Downloads führen. |
| **Empfehlung** | Regex-Validierung: `^[a-zA-Z0-9._:/-]+$`. |

---

## 9. Policy & Approval System

### POL-01 — Approval-Regeln ohne Integritätsschutz auf Disk (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/services/policy_approval_service.py` L160–172 |
| **Severity** | HIGH |
| **Beschreibung** | `policy_allow_always_rules.json` kann per Dateisystem-Zugriff manipuliert werden → beliebige Tools dauerhaft freischalten. |
| **Impact** | Policy-Bypass durch Dateisystem-Manipulation. |
| **Empfehlung** | HMAC-Signatur über JSON speichern und beim Lesen verifizieren. |

### POL-02 — Silent Exception bei Persist (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/policy_approval_service.py` L160–172 |
| **Severity** | MEDIUM |
| **Beschreibung** | Fehler beim Schreiben werden verschluckt. Inkonsistenz zwischen In-Memory- und Disk-State möglich. |
| **Empfehlung** | Exception loggen. Warning-Meldung bei Write-Failure. |

### POL-03 — Approval Scope ohne Agent-Level (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/policy_approval_service.py` L85–87, L220–226 |
| **Severity** | MEDIUM |
| **Beschreibung** | Approvals scoped auf `session_id::tool`. Verschiedene Agenten in derselben Session teilen Genehmigungen. |
| **Empfehlung** | Agent-Name in Approval-Scope einbeziehen. |

### POL-04 — `"full"` Profil = Null-Restriction (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/tool_policy.py` L156–163 |
| **Severity** | HIGH |
| **Beschreibung** | `resolve_tool_profile("full")` gibt `None` zurück = keine Einschränkung. Unbekannte Profilnamen fallen ebenfalls auf `None`. |
| **Impact** | Ein Tippfehler im Profilnamen führt zu vollständigem Toolzugriff. |
| **Empfehlung** | Unbekannte Profile → Exception. Oder restriktives Fallback-Profil (`read_only`). |

### POL-05 — `allow_always` überlebt Server-Restarts (INFO)

| | |
|---|---|
| **Datei** | `backend/app/services/policy_approval_service.py` L12 |
| **Severity** | INFO |
| **Beschreibung** | Eine einzige Genehmigung erzeugt permanente Regeln, die Restarts überleben. |
| **Empfehlung** | Admin-Gate für `allow_always`. UI-Hinweis auf Permanenz. |

---

## 10. Self-Healing & Learning Loop

### SHL-01 — Recovery-Commands ohne Validierung (CRITICAL)

| | |
|---|---|
| **Datei** | `backend/app/services/self_healing_loop.py` L133–143 |
| **Severity** | CRITICAL |
| **Beschreibung** | `plan.recovery_commands` werden direkt als Shell-Befehle ausgeführt. `add_plan()` (L181) erlaubt Registration beliebiger Commands ohne Validierung. |
| **Impact** | **Arbitrary Code Execution** über manipulierte Recovery-Plans. |
| **Empfehlung** | Recovery-Commands gegen Command-Allowlist validieren. `add_plan()` mit Auth-Guard versehen. |

### SHL-02 — `add_plan()` ohne Validierung (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/services/self_healing_loop.py` L181–183 |
| **Severity** | HIGH |
| **Beschreibung** | Jeder Code-Pfad mit Zugriff auf `SelfHealingLoop` kann beliebige Recovery-Plans registrieren. |
| **Empfehlung** | Input-Validierung. Audit-Log bei Plan-Registration. |

### SHL-03 — Naive Erfolgs-Heuristik (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/self_healing_loop.py` L152–155 |
| **Severity** | MEDIUM |
| **Beschreibung** | `"not found" not in ...` und `"error" not in ...` — False Positives möglich. Ein fehlgeschlagener Command könnte als "geheilt" gewertet werden. |
| **Empfehlung** | Exit-Code-basierte Erfolgsprüfung. |

### LEARN-01 — Tool-Outcome Poisoning (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/learning_loop.py` L73–76 |
| **Severity** | MEDIUM |
| **Beschreibung** | `on_tool_outcome` akzeptiert beliebige Tool-Namen und Args ohne Validierung. Falsche Outcomes für fremde Tools → Scoring-Vergiftung. |
| **Empfehlung** | Tool-Name gegen TOOL_NAME_SET validieren. Rate-Limiting. |

---

## 11. Runtime Manager & Subprocesses

### RTM-01 — Gesamte Prozess-Umgebung an Ollama vererbt (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/runtime_manager.py` L142–155 |
| **Severity** | HIGH |
| **Beschreibung** | `subprocess.Popen` mit `env=os.environ.copy()` → alle Secrets (API-Keys, DB-Credentials) werden an den Ollama-Subprozess weitergegeben. |
| **Empfehlung** | Nur benötigte Env-Variablen übergeben (`OLLAMA_HOST`, `PATH`). |

### RTM-02 — Model-Name Command Injection (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/runtime_manager.py` L174–190 |
| **Severity** | MEDIUM |
| **Beschreibung** | `subprocess.run([ollama, "pull", candidate])` — Model-Name kommt transitiv vom User. Obwohl `shell=False`, könnte ein manipulierter Name Ollama-spezifische Schwachstellen triggern. |
| **Empfehlung** | Model-Name-Regex: `^[a-zA-Z0-9._:/-]+$`. |

### RTM-03 — API-Token an unkontrollierte URL gesendet (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/runtime_manager.py` L237–248 |
| **Severity** | MEDIUM |
| **Beschreibung** | Auth-Token wird an `base_url` gesendet. Angreifer-kontrollierte `API_BASE_URL` = Token-Exfiltration (SSRF + Token-Leak). |
| **Empfehlung** | URL-Schema-Validierung (`https://` only). Hostname-Allowlist. |

### RTM-04 — Non-Atomic State-File Writes (LOW)

| | |
|---|---|
| **Datei** | `backend/app/runtime_manager.py` L73–78 |
| **Severity** | LOW |
| **Beschreibung** | `_persist_state` ohne `.tmp` + Rename. Race Condition bei gleichzeitigem Lesen/Schreiben. |
| **Empfehlung** | Atomische Writes via temporäre Datei + Rename. |

---

## 12. Frontend-Sicherheit

### FE-01 — WebSocket-URL hardcoded als `ws://` (HIGH)

| | |
|---|---|
| **Datei** | `frontend/src/app/pages/chat-page.component.ts` L149 |
| **Severity** | HIGH |
| **Beschreibung** | `ws://localhost:8000/ws/agent` — Klartext, kein TLS. In Produktion: gesamter Agent-Datenverkehr unverschlüsselt. |
| **Empfehlung** | URL aus Environment-Config. In Produktion `wss://` erzwingen. |

### FE-02 — Kein Content Security Policy (HIGH)

| | |
|---|---|
| **Datei** | `frontend/src/index.html` |
| **Severity** | HIGH |
| **Beschreibung** | Kein CSP-Header oder Meta-Tag. Kein Schutz gegen Inline-Script-Injection. |
| **Empfehlung** | CSP konfigurieren: `default-src 'self'; script-src 'self'; connect-src 'self' wss://...`. |

### FE-03 — Kein CSRF/XSRF auf HttpClient (HIGH)

| | |
|---|---|
| **Datei** | `frontend/src/app/app.config.ts` L10 |
| **Severity** | HIGH |
| **Beschreibung** | `provideHttpClient()` ohne `withXsrfConfiguration()`. Kein XSRF-Cookie-/Header-Mechanismus. |
| **Empfehlung** | `provideHttpClient(withXsrfConfiguration({...}))` verwenden. |

### FE-04 — API-URLs hardcoded (`http://localhost:8000`) (MEDIUM)

| | |
|---|---|
| **Dateien** | `orchestrator.service.ts` L93, `agents.service.ts` L234 |
| **Severity** | MEDIUM |
| **Beschreibung** | Keine Environment-Konfiguration. Production-URL-Anpassung erfordert Code-Änderung. |
| **Empfehlung** | Angular `environment.ts` / `environment.prod.ts` verwenden. |

### FE-05 — Externe Google-Fonts ohne SRI (MEDIUM)

| | |
|---|---|
| **Datei** | `frontend/src/index.html` L10–12 |
| **Severity** | MEDIUM |
| **Beschreibung** | Keine Subresource Integrity. CDN-Compromise → bösartiger Code injectierbar. |
| **Empfehlung** | SRI-Hashes hinzufügen oder Fonts self-hosten. |

### FE-06 — WebSocket Reconnect ohne Backoff (MEDIUM)

| | |
|---|---|
| **Datei** | `frontend/src/app/services/agent-socket.service.ts` L63–69 |
| **Severity** | MEDIUM |
| **Beschreibung** | Reconnect nach 1500 ms ohne Exponential-Backoff oder Max-Retry. Endlosschleife bei Down-Backend. |
| **Empfehlung** | Exponential Backoff mit `maxRetries`. |

### FE-07 — JSON.parse ohne Schema-Validierung (MEDIUM)

| | |
|---|---|
| **Datei** | `frontend/src/app/services/agent-socket.service.ts` L104–107 |
| **Severity** | MEDIUM |
| **Beschreibung** | WebSocket-Nachrichten werden ohne Schema-Validierung als `AgentSocketEvent` propagiert. |
| **Empfehlung** | Schema-Validierung für eingehende Nachrichten (z.B. Zod oder class-validator). |

### FE-08 — Memory-Page zeigt interne Pfade (MEDIUM)

| | |
|---|---|
| **Datei** | `frontend/src/app/pages/memory-page.component.html` L37–49 |
| **Severity** | MEDIUM |
| **Beschreibung** | Backend-Pfade (`memory_store_dir`, `long_term_db.path`) und Feature-Flags im Klartext angezeigt. |
| **Empfehlung** | In Produktion sensible Pfade ausblenden. Admin-Auth erzwingen. |

---

## 13. Dependencies & Supply Chain

### DEP-01 — Irrelevante npm-Deps im Backend (HIGH)

| | |
|---|---|
| **Datei** | `backend/package.json` L13–17 |
| **Severity** | HIGH |
| **Beschreibung** | `react`, `react-dom`, `vue` als Dependencies in einem Python/FastAPI-Backend. Erweitert die Angriffsfläche ohne Nutzen. Potentielle Supply-Chain-Attack-Vektoren. |
| **Empfehlung** | `npm uninstall react react-dom vue` im Backend. |

### DEP-02 — `cryptography` als optionale Dependency (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/requirements.txt` |
| **Severity** | MEDIUM |
| **Beschreibung** | Kommentar "Optional" bei `cryptography>=43.0.0`. Ohne dieses Paket fällt die Verschlüsselung auf unsicheres XOR zurück. |
| **Empfehlung** | Als harte Dependency deklarieren. "Optional"-Kommentar entfernen. |

### DEP-03 — Minimale Python-Dependencies (INFO)

| | |
|---|---|
| **Datei** | `backend/requirements.txt` |
| **Severity** | INFO |
| **Beschreibung** | Nur 6 Kern-Dependencies (fastapi, uvicorn, httpx, pydantic, python-dotenv, cryptography). Positiv: geringe Angriffsfläche. |
| **Empfehlung** | Regelmäßig `pip-audit` ausführen. |

### DEP-04 — Angular `^`-Version-Ranges (LOW)

| | |
|---|---|
| **Datei** | `frontend/package.json` |
| **Severity** | LOW |
| **Beschreibung** | `^21.2.0` erlaubt automatische Minor/Patch-Updates. Reproduzierbarkeit nicht garantiert. |
| **Empfehlung** | `npm ci` mit `package-lock.json`. Regelmäßig `npm audit`. |

---

## 14. SSRF & Netzwerk-Sicherheit

### SSRF-01 — SearXNG Default-URL `http://localhost:8080` (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/web_search.py` L106–108 |
| **Severity** | MEDIUM |
| **Beschreibung** | Ohne `WEB_SEARCH_BASE_URL` werden Requests an localhost gesendet. Per Prompt Injection kontrollierte Queries können interne Dienste proben. |
| **Empfehlung** | Explizite Konfiguration erfordern. |

### SSRF-02 — `follow_redirects=True` in Web-Search (LOW)

| | |
|---|---|
| **Datei** | `backend/app/services/web_search.py` L75–83 |
| **Severity** | LOW |
| **Beschreibung** | Automatisches Follow-Redirects → Open-Redirect-basierte SSRF möglich. |
| **Empfehlung** | `follow_redirects=False` mit manueller URL-Validierung. |

### SSRF-03 — Suchergebnis-URLs nicht validiert (LOW)

| | |
|---|---|
| **Datei** | `backend/app/services/web_search.py` L106–118 |
| **Severity** | LOW |
| **Beschreibung** | URLs aus Suchergebnissen (`javascript:`, `file://`, interne IPs) werden ungeprüft weitergegeben. |
| **Empfehlung** | Schema-Validierung (`http`/`https`). Interne IPs filtern. |

### SSRF-04 — Tavily API-Key-Leakage bei MITM (LOW)

| | |
|---|---|
| **Datei** | `backend/app/services/web_search.py` L120–135 |
| **Severity** | LOW |
| **Beschreibung** | API-Key wird ohne TLS-Pflicht an `base_url` gesendet. |
| **Empfehlung** | `https://`-Pflicht erzwingen. |

### SSRF-05 — `follow_redirects=True` in Vision Service (LOW)

| | |
|---|---|
| **Datei** | `backend/app/services/vision_service.py` L121–123 |
| **Severity** | LOW |
| **Beschreibung** | Externe Dienste können den Request auf beliebige URLs weiterleiten. |
| **Empfehlung** | `follow_redirects=False` oder auf vertrauenswürdige Domains einschränken. |

---

## 15. Information Disclosure

### INFO-01 — `config.health` leakt API-Keys (CRITICAL)

| | |
|---|---|
| **Datei** | `backend/app/handlers/tools_handlers.py` L515–530 |
| **Severity** | CRITICAL |
| **Beschreibung** | Mit `include_effective_values=True` gibt `api_control_config_health()` den vollständigen `settings.model_dump()` zurück: `llm_api_key`, `api_auth_token`, `web_search_api_key`, `vision_api_key`. **Ohne Authentifizierung aufrufbar.** |
| **Impact** | Vollständige Credential-Exfiltration über einen einzigen HTTP-Request. |
| **Empfehlung** | Secrets aus Config-Dump ausschließen. Endpunkt nur nach Admin-Auth freigeben. |

### INFO-02 — Memory-Overview ohne Auth (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/handlers/tools_handlers.py` L784–830 |
| **Severity** | MEDIUM |
| **Beschreibung** | `api_control_memory_overview()` mit `include_content=True` gibt den gesamten Agenten-Verlauf (Memory-Sessions) ohne Auth zurück. |
| **Empfehlung** | Auth erzwingen. `include_content` auf Admin beschränken. |

### INFO-03 — Exception-Details in HTTP-500 an Client (HIGH)

| | |
|---|---|
| **Dateien** | `backend/app/run_endpoints.py` L138–145, `ws_handler.py` L329–339 |
| **Severity** | HIGH |
| **Beschreibung** | `str(exc)` in HTTPExceptions und WebSocket-Fehler-Events. Leakt interne Pfade, DB-Fehler, Stack-Informationen. |
| **Empfehlung** | Generische Fehlermeldungen nach außen. Details nur in Server-Logs. |

### INFO-04 — LLM-Fehlerdetails an Client (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/run_endpoints.py` L130–137 |
| **Severity** | MEDIUM |
| **Beschreibung** | `HTTPException(status_code=502, detail=str(exc))` für LLM-Fehler kann interne API-URLs und Auth-Fehler offenlegen. |
| **Empfehlung** | Generische Meldung: "LLM service temporarily unavailable". |

### INFO-05 — `raw_preview` in Lifecycle-Events (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/services/tool_execution_manager.py` L937–941 |
| **Severity** | MEDIUM |
| **Beschreibung** | Bis zu 300 Zeichen des rohen LLM-Outputs in Events. Kann Prompt-Inhalte leaken. |
| **Empfehlung** | `raw_preview` entfernen oder auf Debug-Logs beschränken. |

### INFO-06 — `http_request` gibt alle Response-Headers zurück (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/tools.py` L556–575 |
| **Severity** | MEDIUM |
| **Beschreibung** | Interne Server können über Response-Headers Infrastrukturdetails leaken (`X-Powered-By`, `Server`, interne IPs). |
| **Empfehlung** | Nur sichere Header-Teilmenge zurückgeben. |

### INFO-07 — `check_toolchain` leakt Workspace-Pfade (LOW)

| | |
|---|---|
| **Datei** | `backend/app/tools.py` L1059–1067 |
| **Severity** | LOW |
| **Beschreibung** | Workspace-Pfad und Tool-Namen in Responses exponiert. |
| **Empfehlung** | Nur boolesche Status-Werte zurückgeben. |

### INFO-08 — Active Env-Overrides sichtbar (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/handlers/tools_handlers.py` L506–510 |
| **Severity** | MEDIUM |
| **Beschreibung** | `active_overrides` in `config.health` listet gesetzte Env-Variablen auf → Deployment-Konfiguration offengelegt. |
| **Empfehlung** | Nur im Admin-/Debug-Modus exponieren. |

### INFO-09 — LLM Response-Body in Logs (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/llm_client.py` L103–107 |
| **Severity** | MEDIUM |
| **Beschreibung** | `body_text[:300]` geloggt ohne Redaction. Kann User-Prompts oder sensible Daten enthalten. |
| **Empfehlung** | Log-Level auf DEBUG oder Redaction anwenden. |

---

## 16. Race Conditions & Concurrency

### RACE-01 — `_active_run_count` nicht atomar (HIGH)

| | |
|---|---|
| **Datei** | `backend/app/agent.py` L576–579 |
| **Severity** | HIGH |
| **Beschreibung** | `self._active_run_count += 1` ist nicht atomar. Race bei `configure_runtime()`, das `_active_run_count > 0` prüft. |
| **Empfehlung** | `asyncio.Lock` oder `asyncio.Semaphore`. |

### RACE-02 — Session-Worker Erzeugung (LOW)

| | |
|---|---|
| **Datei** | `backend/app/ws_handler.py` L640–644 |
| **Severity** | LOW |
| **Beschreibung** | `ensure_session_worker()` prüft und erzeugt Tasks ohne Lock. Doppelte Worker für dieselbe Session möglich. |
| **Empfehlung** | Atomic Guard oder AsyncIO-Lock. |

### RACE-03 — TOCTOU in `_resolve_workspace_path` (LOW)

| | |
|---|---|
| **Datei** | `backend/app/tools.py` L1023–1035 |
| **Severity** | LOW |
| **Beschreibung** | Zwischen `os.path.realpath` und Datei-Operation könnte ein Symlink erstellt werden. |
| **Empfehlung** | `O_NOFOLLOW` oder Post-Open-Pfadprüfung. |

### RACE-04 — `active_run_tasks` Dict ohne Lock (LOW)

| | |
|---|---|
| **Datei** | `backend/app/handlers/run_handlers.py` L472–478 |
| **Severity** | LOW |
| **Beschreibung** | Python-GIL verhindert Korruption, aber keine Atomarität bei Check-and-Set. |
| **Empfehlung** | AsyncIO-Lock für Zugriff. |

### RACE-05 — SQLite `check_same_thread=False` (MEDIUM)

| | |
|---|---|
| **Datei** | `backend/app/state/state_store.py` L300–302 |
| **Severity** | MEDIUM |
| **Beschreibung** | Single Connection mit Multi-Thread-Zugriff. WAL + Locking vorhanden, aber bei vielen gleichzeitigen Zugriffen problematisch. |
| **Empfehlung** | Connection-Pool oder per-Request-Connections. |

---

## 17. Positive Befunde

Die folgenden Maßnahmen sind korrekt implementiert und verdienen Anerkennung:

| ID | Bereich | Beschreibung |
|---|---------|-------------|
| POS-01 | SSRF-Schutz | `_enforce_safe_web_target()` blockiert korrekt: Private IPs, Loopback, Link-Local, IPv6-mapped-IPv4, DNS-Resolution-Verifizierung. |
| POS-02 | Docker-Sandbox | `--network none`, `--read-only`, `--tmpfs` mit noexec, `--memory 128m`, `--pids-limit 64`, `--no-new-privileges`, `--user nobody`, read-only bind-mount. |
| POS-03 | Shell=False | Command-Execution über `shlex.split()` + `shell=False` (seit OE-02 Patch). |
| POS-04 | Rate-Limiter | Token-Bucket-Rate-Limiter für REST und WebSocket implementiert. |
| POS-05 | Gatekeeper | `ToolCallGatekeeper` hat korrekte Schwellenwert-Validierung und Loop-Erkennung. |
| POS-06 | Angular XSS | Kein Einsatz von `innerHTML`, `bypassSecurityTrustHtml` oder `DomSanitizer`. Standard-Escaping durchgehend. |
| POS-07 | .gitignore | `.env`, `memory_store/`, `state_store/`, `runtime_state.json` korrekt ignoriert. |
| POS-08 | CORS-Wildcard | Wenn `"*"` in Origins: `allow_credentials` wird auf `False` erzwungen. |
| POS-09 | State Encryption | AES-256-GCM State-Verschlüsselung implementiert (seit OE-08 Patch). |

---

## 18. Priorisierte Maßnahmen-Roadmap

### Phase 1 — Sofortmaßnahmen (CRITICAL, 1–2 Wochen)

| # | Finding | Aufwand | Beschreibung |
|---|---------|---------|-------------|
| 1 | AUTH-01, AUTH-02 | 2–3d | Auth-Middleware für REST + WebSocket implementieren |
| 2 | INFO-01 | 2h | API-Keys aus `config.health` Dump ausschließen |
| 3 | CRYPTO-01 | 2h | Startup-Abort bei fehlendem `STATE_ENCRYPTION_KEY` |
| 4 | SHL-01 | 4h | Recovery-Commands gegen Allowlist validieren |
| 5 | CMD-01 | 4h | `docker`-Strategie als Default erzwingen |

### Phase 2 — Kurzfristig (HIGH, 2–4 Wochen)

| # | Finding | Aufwand | Beschreibung |
|---|---------|---------|-------------|
| 6 | CFG-03 | 4h | Shells aus Command-Allowlist entfernen |
| 7 | CFG-04 | 1h | LLM-API-Key Fallback auf Auth-Token entfernen |
| 8 | CMD-04 | 4h | Extension-Deny-List für `write_file` |
| 9 | CMD-09, CMD-11 | 4h | Package-Manager auf Argument-Listen umstellen |
| 10 | CRYPTO-03 | 1h | `cryptography` als harte Dependency |
| 11 | POL-01 | 4h | HMAC-Signatur für Approval-Regeln |
| 12 | API-03 | 4h | CSRF-Token-Mechanismus implementieren |
| 13 | FE-01, FE-02 | 4h | `wss://` erzwingen, CSP konfigurieren |
| 14 | DEP-01 | 30min | Irrelevante npm-Deps aus Backend entfernen |
| 15 | INFO-03 | 2h | Exception-Details aus Responses entfernen |

### Phase 3 — Mittelfristig (MEDIUM, 1–2 Monate)

| # | Finding | Aufwand | Beschreibung |
|---|---------|---------|-------------|
| 16 | CRYPTO-05 | 2h | AAD in AES-GCM aufnehmen |
| 17 | CRYPTO-08 | 4h | Session-Ablauf implementieren |
| 18 | MCP-01 | 4h | MCP-Allowlist auf spezifische Binaries einschränken |
| 19 | MCP-04, MCP-05 | 4h | SSRF-Schutz und Auth für MCP HTTP/SSE |
| 20 | MEM-02, MEM-03 | 4h | Memory-Verschlüsselung und Secret-Redaction |
| 21 | WS-01 | 4h | WebSocket Connection-Limit |
| 22 | PI-01, PI-05 | 2d | Unicode-Normalisierung für Injection-Filter |
| 23 | STATE-01 | 2h | `run_id` Path-Traversal-Schutz |
| 24 | CFG-06 | 1h | CORS `allow_headers` einschränken |
| 25 | RTM-01 | 2h | Subprocess-Env auf Whitelist einschränken |

### Phase 4 — Langfristig (LOW/INFO, ongoing)

| # | Finding | Beschreibung |
|---|---------|-------------|
| 26 | RACE-* | AsyncIO-Locks für shared State |
| 27 | SSRF-02..05 | `follow_redirects=False` für alle externen Clients |
| 28 | DEP-04 | `npm ci` + regelmäßige Audits |
| 29 | Alle LOW/INFO | Kontinuierliche Verbesserung und Monitoring |

---

## Anhang A — Audit-Scope

### Geprüfte Dateien (Backend)

| Pfad | Zeilen | Fokus |
|------|--------|-------|
| `app/tools.py` | ~1080 | Command Execution, SSRF, File Ops |
| `app/ws_handler.py` | ~1490 | WebSocket-Sicherheit, Session-Mgmt |
| `app/config.py` | ~1700 | Secrets, Defaults, CORS |
| `app/main.py` | ~915 | App Bootstrap, Routing |
| `app/agent.py` | ~1800 | Agent-Core, Guardrails |
| `app/llm_client.py` | ~120 | LLM-Kommunikation, Key-Mgmt |
| `app/app_setup.py` | ~80 | CORS, Rate-Limiting-MW |
| `app/memory.py` | ~170 | Memory-Persistenz |
| `app/tool_policy.py` | ~190 | Tool-Restriction-Profiles |
| `app/tool_catalog.py` | ~60 | Tool-Registry |
| `app/run_endpoints.py` | ~170 | REST-API-Endpoints |
| `app/control_router_wiring.py` | ~110 | Router-Integration |
| `app/startup_tasks.py` | ~60 | Startup/Shutdown |
| `app/runtime_manager.py` | ~250 | Ollama-Management |
| **Services:** | | |
| `services/code_sandbox.py` | ~550 | Code-Sandbox-Isolation |
| `services/mcp_bridge.py` | ~470 | MCP-Protocol-Bridge |
| `services/tool_execution_manager.py` | ~1200 | Tool-Orchestrierung |
| `services/tool_call_gatekeeper.py` | ~160 | Loop-Detection |
| `services/tool_result_context_guard.py` | ~210 | PII, Injection-Guard |
| `services/prompt_kernel_builder.py` | ~170 | Prompt-Konstruktion |
| `services/state_encryption.py` | ~160 | Encryption-at-Rest |
| `services/session_security.py` | ~75 | Session-Signing |
| `services/rate_limiter.py` | ~140 | Rate-Limiting |
| `services/web_search.py` | ~140 | Web-Search-Provider |
| `services/vision_service.py` | ~170 | Vision-API |
| `services/package_manager_adapter.py` | ~240 | Package-Mgmt |
| `services/environment_snapshot.py` | ~150 | Env-Snapshot/Rollback |
| `services/policy_approval_service.py` | ~230 | Policy-Approvals |
| `services/self_healing_loop.py` | ~190 | Recovery-Loop |
| `services/learning_loop.py` | ~100 | Adaptive-Learning |
| `services/circuit_breaker.py` | ~180 | Circuit-Breaker |
| `services/execution_contract.py` | ~180 | Post-Conditions |
| `services/idempotency_manager.py` | ~50 | Idempotency |
| `services/idempotency_service.py` | ~100 | Idempotency-Service |
| `services/long_term_memory.py` | ~220 | LTM-SQLite |
| **State:** | | |
| `state/state_store.py` | ~480 | File+SQLite State |
| `state/context_reducer.py` | ~195 | Context-Reduktion |
| **Handlers:** | | |
| `handlers/run_handlers.py` | ~530 | Run-Lifecycle |
| `handlers/session_handlers.py` | ~460 | Session-Ops |
| `handlers/tools_handlers.py` | ~840 | Tool/Config/Memory |
| **Routers:** | | |
| `routers/ws_agent_router.py` | ~20 | WS-Route |
| `routers/run_api.py` | ~35 | Run-API-Route |
| `routers/control_runs.py` | ~90 | Control-Runs |
| `routers/control_sessions.py` | ~100 | Control-Sessions |
| `routers/control_tools.py` | ~110 | Control-Tools |

### Geprüfte Dateien (Frontend)

| Pfad | Fokus |
|------|-------|
| `src/app/app.config.ts` | App-Bootstrap, HttpClient |
| `src/app/app.component.ts` | Root-Component |
| `src/app/pages/chat-page.component.ts` | WebSocket, Chat-UI |
| `src/app/services/agent-socket.service.ts` | WS-Client |
| `src/app/services/agents.service.ts` | REST-Client |
| `src/app/services/orchestrator.service.ts` | Orchestrator-Client |
| `src/app/pages/memory-page.component.html` | Memory-Overview |
| `src/index.html` | CSP, SRI |
| `angular.json` | Build-Konfiguration |

### Geprüfte Konfigurations-Dateien

| Datei | Fokus |
|-------|-------|
| `backend/requirements.txt` | Python-Dependencies |
| `backend/package.json` | Backend-npm-Deps |
| `frontend/package.json` | Frontend-Deps |
| `.gitignore` | Secret-Exposure |

---

*Audit durchgeführt mit manueller statischer Code-Analyse. Kein Penetration-Test.*
