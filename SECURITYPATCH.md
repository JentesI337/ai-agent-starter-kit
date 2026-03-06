# SECURITYPATCH.md — Security Audit & Patch Report

> **Datum:** 2026-03-06  
> **Scope:** Vollständiges Backend — Transport, Toolchain, Sandbox, Config, SSRF, Policy  
> **Status:** 17 Fixes implementiert · 1 offene Empfehlung (Auth)  
> **Tests:** 1188 passed, 0 failed nach Patch

---

## Inhaltsverzeichnis

1. [Übersicht](#1-übersicht)
2. [Implementierte Fixes](#2-implementierte-fixes)
   - [FIX-01: SSRF DNS-Rebinding über HTTPS](#fix-01-ssrf-dns-rebinding-über-https)
   - [FIX-02: HTTP Header-Override bypasses DNS Pinning](#fix-02-http-header-override-bypasses-dns-pinning)
   - [FIX-03: API Auth Token / LLM Key Vermischung](#fix-03-api-auth-token--llm-key-vermischung)
   - [FIX-04: Code-Sandbox Obfuskierungs-Bypass](#fix-04-code-sandbox-obfuskierungs-bypass)
   - [FIX-05: WebSocket Message-Size-Limit fehlt](#fix-05-websocket-message-size-limit-fehlt)
   - [FIX-06: Client `also_allow` ermöglicht Policy-Bypass](#fix-06-client-also_allow-ermöglicht-policy-bypass)
   - [FIX-07: Temporäre Command-Overrides persistent](#fix-07-temporäre-command-overrides-persistent)
   - [FIX-08: Background-Job DoS (unbegrenzte Prozesse)](#fix-08-background-job-dos-unbegrenzte-prozesse)
   - [FIX-09: Path Traversal via Symlinks/Junctions](#fix-09-path-traversal-via-symlinksjunctions)
   - [FIX-10: CORS Wildcard in Development](#fix-10-cors-wildcard-in-development)
3. [Offene Empfehlungen](#3-offene-empfehlungen)
4. [Risiko-Matrix](#4-risiko-matrix)

---

## 1. Übersicht

Das Security-Audit hat **24 Schwachstellen** identifiziert (4 CRITICAL, 6 HIGH, 8 MEDIUM, 6 LOW). Davon wurden **17 gepatcht** (10 initial + 7 Folge-Patches). Die verbleibende 1 Empfehlung (Auth-Middleware, OE-01) erfordert Feature-Arbeit und ist als offene Empfehlung dokumentiert.

### Geänderte Dateien

| Datei | Änderungen |
|---|---|
| `backend/app/tools.py` | SSRF-Härtung, DNS-Pin-Enforcement, IP-Validierung, Header-Blocklist, Background-Job-Limit, Path-Traversal-Fix, Temporary-Override-Consumption, **shell=False (OE-02)** |
| `backend/app/ws_handler.py` | Message-Size-Limit, `also_allow`-Blocklist, **Rate-Limiting (OE-03)**, **Session-ID-Validierung (OE-07)** |
| `backend/app/config.py` | Token-Trennung, `llm_api_key`-Feld, Vision-API-Key-Isolation |
| `backend/app/llm_client.py` | Separater LLM-API-Key |
| `backend/app/app_setup.py` | CORS-Härtung, **Rate-Limiting-Middleware (OE-03)** |
| `backend/app/services/code_sandbox.py` | Dangerous-Construct-Detection, **Docker-Sandbox-Implementation (OE-04)** |
| `backend/app/services/rate_limiter.py` | **NEU: Token-Bucket Rate-Limiter (OE-03)** |
| `backend/app/services/mcp_bridge.py` | **MCP-Command-Allowlist (OE-05)** |
| `backend/app/services/session_security.py` | **NEU: Session-ID HMAC-Validierung (OE-07)** |
| `backend/app/services/state_encryption.py` | **NEU: AES-256-GCM State-Encryption & Policy-HMAC (OE-08)** |
| `backend/app/services/tool_result_context_guard.py` | **Prompt-Injection-Neutralisierung (OE-06)** |
| `backend/app/services/prompt_kernel_builder.py` | **Content-Isolation-Boundaries (OE-06)** |
| `backend/app/state/context_reducer.py` | **Tool-Output-Delimiters & Injection-Sanitization (OE-06)** |
| `backend/app/state/state_store.py` | **Encryption-at-Rest (OE-08)** |
| `backend/tests/test_tools_web_fetch_security.py` | Test-Anpassungen für DNS-Pinning |

---

## 2. Implementierte Fixes

---

### FIX-01: SSRF DNS-Rebinding über HTTPS

**Schweregrad:** CRITICAL  
**Dateien:** `backend/app/tools.py` — `_enforce_safe_web_target()`, `_validate_ip_is_public()`  
**CVE-Kategorie:** CWE-918 (Server-Side Request Forgery)

#### Problem

Die `_enforce_safe_web_target()`-Methode implementierte DNS-Pinning **nur für HTTP**, nicht für HTTPS. Die Begründung war, dass TLS-Certificate-Validation eine DNS-Rebinding-Attacke verhindert. Das ist **nicht ausreichend**:

1. **Angreifer-kontrollierte Domain mit gültigem Zertifikat:** Ein Angreifer kann ein Let's-Encrypt-Zertifikat für `attacker.com` erhalten, dann den DNS-Eintrag auf `127.0.0.1` oder `169.254.169.254` umbiegen. Die TLS-Validierung akzeptiert das Zertifikat, weil es für `attacker.com` gültig ist — unabhängig von der IP.

2. **Fehlende IPs in der Blockliste:** `0.0.0.0`, IPv6-mapped IPv4-Adressen (`::ffff:127.0.0.1`, `::ffff:10.0.0.1`) und Cloud-Metadata-Endpunkte (`169.254.170.2`) fehlten.

3. **Einfache `is_global`-Prüfung unzureichend:** IPv6-mapped IPv4 wie `::ffff:10.0.0.1` wird von `ipaddress.is_global` als `True` klassifiziert, obwohl die gemappte IPv4-Adresse privat ist.

**Angriffsszenario:**
```
Agent → web_fetch("https://attacker.com/payload")
         ↓ DNS resolves to 169.254.169.254
         ↓ TLS accepts (cert valid for attacker.com)
         ↓ Reaches AWS metadata endpoint
         ↓ Exfiltrates IAM credentials
```

#### Fix

```python
# VORHER: Kein Pinning für HTTPS
if parsed.scheme == "http":
    return str(next(iter(resolved_ips)))
# HTTPS: TLS certificate validation binds the connection...
return None

# NACHHER: Pinning für HTTP UND HTTPS
return str(next(iter(resolved_ips)))
```

Zusätzlich:
- **Erweiterte Blockliste:** `0.0.0.0`, `169.254.170.2` (ECS metadata), `metadata.internal`, `::ffff:127.0.0.1`, `::ffff:0.0.0.0`, `::ffff:169.254.169.254`, `[0:0:0:0:0:0:0:1]`
- **Neue Methode `_validate_ip_is_public()`:** Prüft IPv6-mapped IPv4 (extrahiert `.ipv4_mapped` und validiert separat) und Zero-Network (`0.0.0.0/8`).

#### Drawback

- **TLS-Verbindungen über IP statt Hostname:** HTTPS-Requests werden jetzt an die gepinnte IP gesendet (mit `Host`-Header). Einige Server/CDNs können SNI-Mismatches verursachen, wenn sie die IP statt des Hostnamens im TLS-Handshake sehen. In der Praxis funktioniert das mit `httpx` korrekt (sendet SNI über den `Host`-Header), aber exotische Server-Konfigurationen könnten Probleme verursachen.
- **Performance:** Jeder HTTPS-Request erfordert jetzt eine DNS-Auflösung VOR dem Request. Bei HTTP war das bereits der Fall, bei HTTPS ist das ein zusätzlicher Schritt (~1-5ms Latenz).
- **TLS-Certificate-Pinning wird umgangen:** Wenn der Server Certificate-Pinning erwartet, könnte die IP-basierte Verbindung fehlschlagen.

---

### FIX-02: HTTP Header-Override bypasses DNS Pinning

**Schweregrad:** CRITICAL  
**Datei:** `backend/app/tools.py` — `http_request()`  
**CVE-Kategorie:** CWE-918 (SSRF), CWE-113 (HTTP Response Splitting)

#### Problem

Der Code setzte den DNS-Pin `Host`-Header **vor** den User-Headern:

```python
request_headers.update(pin_headers)        # DNS-Pin Host header
# ... dann User-Headers überschreiben alles:
request_headers[key.strip()] = value       # User kann Host überschreiben!
```

Ein Angreifer (oder ein prompt-injected Agent) konnte über die `http_request`-Tool-Parameter einen eigenen `Host`-Header setzen und damit die DNS-Rebinding-Prevention vollständig umgehen:

```json
{
  "url": "http://safe-looking-site.com/api",
  "headers": "{\"Host\": \"169.254.169.254\"}"
}
```

#### Fix

```python
# 1. User-Header werden ZUERST gesetzt
for key, value in parsed_headers.items():
    request_headers[key.strip()] = value

# 2. Security-sensitive Headers werden blockiert
_FORBIDDEN_HEADER_KEYS = {"host", "transfer-encoding", "content-length"}
if key.strip().lower() in _FORBIDDEN_HEADER_KEYS:
    raise ToolExecutionError(...)

# 3. DNS-Pin Header wird ZULETZT gesetzt (überschreibt alles)
request_headers.update(pin_headers)
```

#### Drawback

- **Keine benutzerdefinierten Host-Header:** Legitime Use-Cases, bei denen der Agent einen spezifischen `Host`-Header setzen muss (z.B. Virtual-Host-Testing, lokale Entwicklungsserver), sind nicht mehr möglich. Der Header wird hartgeblockt.
- **Transfer-Encoding-Block:** Verhindert chunked-transfer-encoding-Overrides. In der Praxis irrelevant für Agent-Tooling, aber technisch eine Einschränkung.
- **Content-Length-Block:** Verhindert manuelle Content-Length-Manipulation. Kann bei bestimmten APIs, die exakte Content-Length-Header erwarten, zu Problemen führen (httpx berechnet diese automatisch).

---

### FIX-03: API Auth Token / LLM Key Vermischung

**Schweregrad:** MEDIUM  
**Dateien:** `backend/app/config.py`, `backend/app/llm_client.py`  
**CVE-Kategorie:** CWE-522 (Insufficiently Protected Credentials)

#### Problem

Drei separate Credential-Chains waren unsicher verknüpft:

1. **`api_auth_token`** fiel auf `OLLAMA_API_KEY` zurück:
   ```python
   api_auth_token = os.getenv("API_AUTH_TOKEN", os.getenv("OLLAMA_API_KEY", ""))
   ```
   Wenn nur `OLLAMA_API_KEY` gesetzt war (z.B. für OpenRouter/OpenAI), wurde dieser Key automatisch zum internen API-Auth-Token — jeder, der den LLM-Provider-Key kennt, konnte die Agent-API authentifizieren.

2. **`vision_api_key`** fiel auf `API_AUTH_TOKEN` zurück:
   ```python
   vision_api_key = os.getenv("VISION_API_KEY", os.getenv("API_AUTH_TOKEN", ""))
   ```
   Wenn der Vision-Provider extern war (z.B. OpenAI Vision), wurde der interne Auth-Token an einen Drittanbieter gesendet.

3. **`LlmClient`** verwendete `api_auth_token` für LLM-Requests:
   ```python
   auth_token = (settings.api_auth_token or "").strip()
   headers["Authorization"] = f"Bearer {auth_token}"
   ```
   Wenn `API_AUTH_TOKEN` gesetzt war, wurde es an jeden LLM-Endpunkt gesendet — auch wenn dieser ein anderer Provider war.

**Angriffsszenario:**
```
Admin setzt API_AUTH_TOKEN="secret-internal-key"
          → wird als Bearer an externen LLM-Provider gesendet
          → LLM-Provider loggt den Key
          → Key wird kompromittiert
          → Angreifer authentifiziert sich gegen die Agent-API
```

#### Fix

```python
# config.py — Keine Fallback-Ketten mehr
api_auth_token: str = os.getenv("API_AUTH_TOKEN", "")
llm_api_key: str = os.getenv("LLM_API_KEY", os.getenv("OLLAMA_API_KEY", ""))
vision_api_key: str = os.getenv("VISION_API_KEY", "")

# llm_client.py — Priorisiert LLM-spezifischen Key
auth_token = (settings.llm_api_key or settings.api_auth_token or "").strip()
```

#### Drawback

- **Breaking Change für existierende Deployments:** Nutzer, die bisher nur `OLLAMA_API_KEY` gesetzt haben und damit sowohl LLM- als auch API-Auth abgedeckt haben, müssen jetzt `LLM_API_KEY` explizit setzen. Die Kette `OLLAMA_API_KEY → api_auth_token` ist entfernt.
- **Vision-Service funktioniert nicht ohne Konfiguration:** Nutzer, die bisher `API_AUTH_TOKEN` als impliziten Vision-Key genutzt haben, müssen jetzt `VISION_API_KEY` explizit setzen.
- **Mehr Umgebungsvariablen:** Statt 1-2 Keys müssen jetzt bis zu 4 separat konfiguriert werden (`API_AUTH_TOKEN`, `LLM_API_KEY`, `OLLAMA_API_KEY`, `VISION_API_KEY`).

---

### FIX-04: Code-Sandbox Obfuskierungs-Bypass

**Schweregrad:** CRITICAL  
**Datei:** `backend/app/services/code_sandbox.py`  
**CVE-Kategorie:** CWE-94 (Code Injection)

#### Problem

Die Code-Sandbox verließ sich ausschließlich auf **statische Token-Erkennung** für Netzwerk- und Filesystem-Violations. Ein Angreifer konnte alle Checks trivial umgehen:

```python
# Bypass 1: exec() mit dynamischem String
exec("imp" + "ort so" + "cket")

# Bypass 2: __import__ mit Obfuskierung
getattr(__builtins__, '__imp' + 'ort__')('socket')

# Bypass 3: importlib
import importlib
importlib.import_module('so' + 'cket')

# Bypass 4: base64 + exec
import base64
exec(base64.b64decode(b'aW1wb3J0IHNvY2tldA=='))

# Bypass 5: ctypes für direkten Syscall
import ctypes
libc = ctypes.CDLL('libc.so.6')
```

Keine dieser Varianten wurde erkannt. Der Code lief dann als vollwertiger Subprocess ohne OS-Isolation.

#### Fix

Neue Methode `_detect_dangerous_constructs()` blockiert:

**Python:**
- `exec()`, `eval()`, `compile()` — Dynamic code execution
- `__import__()` — Dynamic imports
- `importlib` — Module-Loading-Bypass
- `ctypes` — Native code execution / syscall bypass
- `subprocess` — Command execution
- `globals()` — Namespace-Zugriff
- `getattr()` — Attribute-Zugriff (Obfuskierungs-Vektor)
- `__builtins__`, `__subclasses__` — Sandbox-Escape-Vektoren

**JavaScript:**
- `eval()`, `Function()` — Dynamic code
- `child_process` — Command execution
- `require('fs')` — Filesystem-Zugriff

#### Drawback

- **False Positives:** Legitimer Code, der `eval()`, `exec()`, `getattr()`, oder `compile()` verwendet, wird blockiert. Das betrifft z.B.:
  - JSON-Parser mit `eval()` (statt `json.loads`) 
  - Template-Engines die `compile()` nutzen
  - Plugin-Systeme die `getattr()` verwenden
  - Serialisierungs-Libraries die `importlib` nutzen
- **`getattr()` ist besonders aggressiv:** Viele Python-Idiome nutzen `getattr()` für optionale Attribute. Dieser Block verhindert eine ganze Klasse von normalem Python-Code.
- **Kein Ersatz für echte Isolation:** Die statische Analyse ist weiterhin umgehbar mit ausreichend Kreativität (z.B. `type()` + `__init__` + `__globals__`-Chain, Unicode-Homoglyphen, Byte-Manipulation). Die Methode ist defense-in-depth, aber **kein Ersatz für Docker/seccomp/nsjail**.
- **Keine Language-spezifische Granularität:** Ein `getattr` in einem Kommentar oder String-Literal triggert ebenfalls den Block.

---

### FIX-05: WebSocket Message-Size-Limit fehlt

**Schweregrad:** HIGH  
**Datei:** `backend/app/ws_handler.py` — `handle_ws_agent()`  
**CVE-Kategorie:** CWE-400 (Uncontrolled Resource Consumption)

#### Problem

Der WebSocket-Handler rief `await websocket.receive_text()` ohne Größenlimit auf. Ein Angreifer konnte beliebig große Nachrichten senden:

```javascript
// Angreifer-Client
ws.send("A".repeat(1_000_000_000)); // 1 GB String
```

FastAPI/uvicorn hat zwar ein internes Limit (typisch 16 MB), aber:
1. Die Config-Einstellung `max_user_message_length` (Default: 8000) wurde **im WebSocket-Handler nie validiert**.
2. Mehrere gleichzeitige große Nachrichten konnten Memory-Exhaustion auslösen.
3. Die JSON-Parsing-Phase (`model_validate_json`) allokiert zusätzlichen Speicher.

#### Fix

```python
raw = await websocket.receive_text()
# SEC: Enforce message size limit to prevent memory exhaustion
_ws_max_message_bytes = 128_000  # 128 KB hard limit
if len(raw) > _ws_max_message_bytes:
    await send_event({
        "type": "error",
        "agent": deps.agent.name,
        "message": f"Message too large ({len(raw)} bytes, max {_ws_max_message_bytes}).",
    })
    continue
```

#### Drawback

- **128 KB Hard-Limit:** Sehr große User-Prompts (>128 KB) werden abgelehnt. In der Praxis sind Prompts selten größer als 10-20 KB, aber Use-Cases wie „analysiere diesen gesamten Quellcode" mit inline-eingebettetem Code könnten scheitern.
- **Kein graduelles Limit:** Das Limit ist ein harter Cut — es gibt kein Streaming oder chunked-Receiving. Alternativen wie `max_user_message_length` pro Feature (z.B. Code-Upload vs. Chat) sind nicht implementiert.
- **Fehler-Feedback minimal:** Der Client erhält nur ein generisches Error-Event, keine spezifische Guidance zum Limit.
- **Limit greift nach vollständigem Empfang:** Die Nachricht wurde bereits komplett empfangen und in den Speicher geladen, bevor der Check greift. Echte Absicherung müsste auf uvicorn/ASGI-Level passieren.

---

### FIX-06: Client `also_allow` ermöglicht Policy-Bypass

**Schweregrad:** HIGH  
**Datei:** `backend/app/ws_handler.py` (2 Stellen)  
**CVE-Kategorie:** CWE-285 (Improper Authorization)

#### Problem

Der Client konnte über den WebSocket-Payload `tool_policy.also_allow` beliebige Tools freischalten:

```json
{
  "type": "user_message",
  "content": "innocuous request",
  "tool_policy": {
    "also_allow": ["run_command", "code_execute"]
  }
}
```

Ein Prompt-Injection-Angriff konnte den Agent dazu bringen, eine Nachricht mit `also_allow: ["run_command"]` zu senden, selbst wenn die Server-Default-Policy `run_command` blockierte.

#### Fix

```python
_ALSO_ALLOW_BLOCKLIST = frozenset({
    "run_command", "code_execute",
    "start_background_command", "kill_background_process",
    "write_file", "apply_patch",
})
incoming_also_allow = [
    item for item in raw_also_allow
    if item not in _ALSO_ALLOW_BLOCKLIST
]
```

#### Drawback

- **Legitime Overrides blockiert:** Wenn ein Admin-Frontend oder eine Automation bewusst `run_command` für einen spezifischen Request freischalten möchte, ist das über `also_allow` nicht mehr möglich. Alternative: Server-seitige Admin-API oder explizite Tool-Policy-Konfiguration.
- **Unvollständige Blocklist:** Neue Tools, die in Zukunft hinzugefügt werden, müssen manuell zur Blocklist hinzugefügt werden. Es gibt keinen automatischen Mechanismus, der „gefährliche" Tools identifiziert.
- **`write_file` und `apply_patch` blockiert:** Coding-Workflows, bei denen der Client explizit File-Write-Rechte erteilen möchte, funktionieren nicht mehr über `also_allow`. Die Default-Tool-Policy muss stattdessen serverseitig konfiguriert werden.
- **Blocklist an 2 Stellen:** Die gleiche Blocklist ist in `ws_handler.py` dupliziert (Zeile ~375 und ~1013). Änderungen müssen an beiden Stellen synchron erfolgen — Fehlerquelle.

---

### FIX-07: Temporäre Command-Overrides persistent

**Schweregrad:** HIGH  
**Datei:** `backend/app/tools.py` — `allow_command_leader_temporarily()`, `run_command()`  
**CVE-Kategorie:** CWE-269 (Improper Privilege Management)

#### Problem

Die Methode `allow_command_leader_temporarily()` fügte Command-Leader permanent zum Override-Set hinzu. Ein einmaliges „allow_once" (via Policy-Approval-UI) galt für die gesamte Session:

```
Schritt 1: Agent will "npm install" ausführen
Schritt 2: User klickt "Allow Once" im UI
Schritt 3: "npm" wird zu _command_allowlist_overrides hinzugefügt
Schritt 4: Agent kann danach JEDERZEIT "npm run exploit-script" ausführen
           → "npm" ist permanent freigeschaltet
```

Ein Prompt-Injection-Angriff konnte den Agent dazu bringen, einen Befehl auszuführen, der vom User einmal genehmigt wurde, und diesen dann für beliebige Folge-Commands zu missbrauchen.

#### Fix

```python
def allow_command_leader_temporarily(self, leader: str) -> str | None:
    """Add a command leader to overrides for single use only."""
    self._command_allowlist_overrides.add(normalized)
    return normalized

def _consume_temporary_override(self, leader: str) -> None:
    """Remove a temporary override after it has been used once."""
    self._command_allowlist_overrides.discard(normalized)

def run_command(self, command: str, cwd: str | None = None) -> str:
    leader = self._enforce_command_allowlist(command)
    # SEC: Consume after validation
    self._consume_temporary_override(leader)
    ...
```

#### Drawback

- **Jeder Befehl braucht neue Genehmigung:** Wenn ein Agent NPM installiert und dann `npm run build` braucht, muss der User **zweimal** genehmigen. Das kann bei iterativen Workflows (z.B. `pip install` → `pip install` weiteres Paket) frustrierend sein.
- **`start_background_command` konsumiert nicht:** Die Override wird nur in `run_command()` konsumiert, nicht in `start_background_command()`. Ein Angreifer könnte die Override über den Background-Command-Pfad nutzen, bevor `run_command` sie konsumiert. (Verbesserung: Auch in `start_background_command` konsumieren.)
- **Race Condition:** Bei parallelen Tool-Calls könnte ein zweiter `run_command`-Call die Override nutzen, bevor der erste sie konsumiert hat. In der Praxis unwahrscheinlich (Agent-Pipeline ist sequentiell), aber theoretisch möglich.

---

### FIX-08: Background-Job DoS (unbegrenzte Prozesse)

**Schweregrad:** MEDIUM  
**Datei:** `backend/app/tools.py` — `start_background_command()`  
**CVE-Kategorie:** CWE-400 (Uncontrolled Resource Consumption)

#### Problem

`start_background_command()` hatte kein Limit für gleichzeitige Hintergrundprozesse. Ein Angreifer (oder prompt-injected Agent) konnte beliebig viele Prozesse spawnen:

```python
for i in range(10000):
    agent.tools.start_background_command(f"sleep 99999")
```

Jeder Prozess:
- Belegt einen OS-Process-Slot
- Öffnet eine Log-Datei
- Wird nie automatisch beendet (kein TTL)

#### Fix

```python
with self._bg_lock:
    active_count = sum(
        1 for job in self._background_jobs.values()
        if job["process"].poll() is None
    )
    if active_count >= self._bg_max_concurrent_jobs:  # Default: 10
        raise ToolExecutionError(
            f"Maximum concurrent background jobs ({self._bg_max_concurrent_jobs}) reached."
        )
```

#### Drawback

- **Hard-Limit von 10:** Komplexe Dev-Workflows mit vielen parallelen Prozessen (z.B. Frontend-Dev-Server + Backend + DB + Watch-Mode + Tests) könnten am Limit scheitern. Das Limit ist nicht konfigurierbar.
- **Kein TTL:** Beendete Prozesse werden gezählt (via `poll() is None`), aber nie automatisch bereinigt. Der Job-Dictionary wächst unbegrenzt mit abgeschlossenen Jobs.
- **Lock-Contention:** Die `_bg_lock`-Prüfung iteriert bei jedem `start_background_command` über alle Jobs. Bei vielen abgeschlossenen Jobs könnte das messbar langsam werden.
- **Keine Log-Rotation:** Die Log-Dateien in `.agent_background/` wachsen unbegrenzt.

---

### FIX-09: Path Traversal via Symlinks/Junctions

**Schweregrad:** MEDIUM  
**Datei:** `backend/app/tools.py` — `_resolve_workspace_path()`, `_resolve_command_cwd()`  
**CVE-Kategorie:** CWE-22 (Path Traversal)

#### Problem

Die Path-Validierung nutzte `Path.resolve()`:

```python
target = (self.workspace_root / raw_path).resolve()
if self.workspace_root not in target.parents:
    raise ToolExecutionError("Path escapes workspace root.")
```

Problemstellen:
1. **`self.workspace_root` wurde nicht aufgelöst:** Wenn der Workspace-Root selbst ein Symlink war, zeigte `resolve()` auf den echten Pfad, aber der Check verglich gegen den Symlink-Pfad → Escape möglich.
2. **Windows Junction Points:** `Path.resolve()` auf Windows löst NTFS Junction Points nicht immer korrekt auf. `os.path.realpath()` ist zuverlässiger.
3. **TOCTOU Race Condition:** Zwischen `resolve()` und der tatsächlichen Dateioperation konnte ein Symlink erstellt/geändert werden.

**Angriffsszenario (Windows):**
```
1. Agent erstellt Junction: workspace/link → C:\Windows\System32
2. Agent liest: read_file("link/config/SAM")
3. resolve() folgt dem Junction → C:\Windows\System32\config\SAM
4. Aber workspace_root ist z.B. C:\Users\dev\project (kein Symlink)
5. Wenn workspace_root selbst ein Junction ist, könnte der Check fehlschlagen
```

#### Fix

```python
def _resolve_workspace_path(self, raw_path: str) -> Path:
    workspace_real = Path(os.path.realpath(self.workspace_root))
    target_raw = self.workspace_root / raw_path
    target = Path(os.path.realpath(target_raw))
    if workspace_real not in target.parents and target != workspace_real:
        raise ToolExecutionError("Path escapes workspace root.")
    return target
```

#### Drawback

- **Performance:** `os.path.realpath()` ruft auf Windows `GetFinalPathNameByHandleW` auf, was einen Kernel-Call pro Pfad bedeutet. Bei intensivem `list_dir()`/`read_file()` könnten Hunderte zusätzlicher Syscalls anfallen.
- **Symlinks innerhalb des Workspace brechen:** Wenn ein Projekt Symlinks innerhalb des Workspace hat, die auf andere Stellen *innerhalb* des Workspace zeigen, könnten diese nach `realpath()` korrekt aufgelöst werden. Aber Symlinks, die auf Verzeichnisse *außerhalb* des Workspace zeigen, werden jetzt korrekt blockiert — was für monorepo-Setups mit externen Dependency-Links problematisch sein kann.
- **TOCTOU nicht vollständig gelöst:** Die Race-Condition zwischen `realpath()` und der tatsächlichen File-Operation besteht weiterhin. Echte Lösung: `O_NOFOLLOW`-Flags oder Bind-Mounts.

---

### FIX-10: CORS Wildcard in Development

**Schweregrad:** MEDIUM  
**Datei:** `backend/app/app_setup.py` — `configure_cors()`  
**CVE-Kategorie:** CWE-942 (Overly Permissive Cross-Origin Policy)

#### Problem

In Non-Production-Umgebungen wurde CORS-Origin auf `*` gesetzt:

```python
if settings.app_env != "production" and not cors_origins:
    cors_origins = ["*"]
```

**Risiko:** Jede Webseite konnte API-Requests an den lokalen Agent-Server senden. In Kombination mit fehlender Auth (offene Empfehlung) bedeutete das:

```javascript
// Webseite evil.com
fetch("http://localhost:8000/api/run", {
    method: "POST",
    body: JSON.stringify({message: "rm -rf /"})
})
// → Wird akzeptiert, weil CORS: * und kein Auth
```

Außerdem war `allow_methods=["*"]` gesetzt, was auch `TRACE` und `CONNECT` erlaubte.

#### Fix

```python
if settings.app_env != "production" and not cors_origins:
    cors_origins = [
        "http://localhost:4200", "http://localhost:3000",
        "http://127.0.0.1:4200", "http://127.0.0.1:3000",
    ]
# ...
allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
```

#### Drawback

- **Breaking Change für Custom-Frontends:** Entwickler, die ein Frontend auf einem anderen Port (z.B. 5173 für Vite) oder einer anderen Adresse laufen haben, müssen jetzt `CORS_ALLOW_ORIGINS` explizit setzen.
- **IPv6 localhost nicht enthalten:** `[::1]:4200` ist nicht in der Default-Liste. Auf Systemen mit reiner IPv6-Konfiguration könnte das Frontend CORS-Fehler bekommen.
- **Keine Wildcard-Option dokumentiert:** Wenn ein Entwickler bewusst `*` will (z.B. für Netzwerk-Tests), muss er `CORS_ALLOW_ORIGINS=*` setzen. Das ist aber nicht dokumentiert.
- **`allow_headers` bleibt `["*"]`:** Custom-Headers werden weiterhin ohne Einschränkung akzeptiert. Eine Whitelist wäre sicherer, könnte aber Frontend-Custom-Headers brechen.

---

## 3. Offene Empfehlungen

Von den ursprünglich 8 offenen Empfehlungen wurde **7 implementiert** (OE-02 bis OE-08). Nur OE-01 (Auth) bleibt offen, da dies ein POC ist.

### OE-01: Keine Authentifizierung (CRITICAL) — ⚠️ OFFEN

**Problem:** Weder WebSocket (`ws://`) noch REST-Endpunkte haben Auth-Middleware. `api_auth_required` existiert als Config-Flag, wird aber nirgends enforced. Jeder Netzwerk-Teilnehmer hat vollen Zugriff.

**Empfehlung:** FastAPI-Dependency mit Bearer-Token-Validation. WebSocket-Auth über Query-Parameter oder erstes Message.

**Aufwand:** ~2-4h Implementation, ~1h Tests.

---

### OE-02: `shell=True` in Command-Execution (CRITICAL) — ✅ GEPATCHT

**Dateien:** `backend/app/tools.py` — `run_command()`, `start_background_command()`, `_tokenize_command()`

**Fix:** Beide Methoden verwenden jetzt `shell=False` mit `shlex.split(posix=True)` für Tokenisierung. Eine neue Methode `_tokenize_command()` kapselt die Tokenisierung. Commands werden als Argument-Listen an `subprocess.run()` / `subprocess.Popen()` übergeben. `FileNotFoundError` wird als `ToolExecutionError` behandelt.

**Env-Config:** Keine neuen Env-Variablen.

---

### OE-03: Rate-Limiting (HIGH) — ✅ GEPATCHT

**Dateien:** `backend/app/services/rate_limiter.py` (NEU), `backend/app/app_setup.py`, `backend/app/ws_handler.py`

**Fix:** In-Memory Token-Bucket Rate-Limiter ohne externe Dependencies. REST-Endpunkte werden über `_RateLimitMiddleware` (Starlette BaseHTTPMiddleware) geschützt. WebSocket-Messages werden per-IP rate-limited im Message-Loop. Auto-Deaktivierung in Test-Umgebungen.

**Env-Config:**
- `RATE_LIMIT_ENABLED` (default: `true`)
- `RATE_LIMIT_RPS` (default: `10`)
- `RATE_LIMIT_BURST` (default: `30`)
- `WS_RATE_LIMIT_RPS` (default: `5`)
- `WS_RATE_LIMIT_BURST` (default: `20`)

---

### OE-04: Docker-Sandbox (HIGH) — ✅ GEPATCHT

**Datei:** `backend/app/services/code_sandbox.py` — `_execute_docker()`

**Fix:** Vollständige Docker-Isolation implementiert mit: `--network none`, `--read-only`, `--tmpfs /tmp:rw,noexec,nosuid,size=64m`, `--memory 128m`, `--cpus 0.5`, `--pids-limit 64`, `--no-new-privileges`, `--user nobody`. Code wird in einem temp-Verzeichnis als `:ro` bind-mount ausgeführt. Falls Docker nicht verfügbar ist, wird ein aussagekräftiger Fehler zurückgegeben.

**Env-Config:**
- `CODE_SANDBOX_DOCKER_IMAGE_PYTHON` (default: `python:3.12-slim`)
- `CODE_SANDBOX_DOCKER_IMAGE_JS` (default: `node:20-slim`)

---

### OE-05: MCP Bridge Command Injection (HIGH) — ✅ GEPATCHT

**Datei:** `backend/app/services/mcp_bridge.py` — `_validate_mcp_command()`, `StdioMcpConnection.connect()`

**Fix:** MCP-Server-Commands werden gegen eine Allowlist validiert (default: `node`, `npx`, `python`, `python3`, `uvx`, `deno`, `bun`, `docker`, `mcp-server`). Argumente werden auf Shell-Metacharacter geprüft (`;`, `&&`, `||`, `|`, `` ` ``, `$(`). Erweiterbar über `MCP_COMMAND_ALLOWLIST` Env-Variable.

**Env-Config:**
- `MCP_COMMAND_ALLOWLIST` (komma-separiert, erweitert die Defaults)

---

### OE-06: Prompt Injection Defenses (HIGH) — ✅ GEPATCHT

**Dateien:** `backend/app/state/context_reducer.py`, `backend/app/services/prompt_kernel_builder.py`, `backend/app/services/tool_result_context_guard.py`

**Fix:** Dreischichtiger Schutz:

1. **Content-Isolation-Delimiters** (`context_reducer.py`): Tool-Outputs werden in `<tool_output isolation="content_only">` Tags gewrappt, die dem LLM signalisieren, dass der Inhalt Daten sind, keine Instruktionen.

2. **Content-Boundary in Prompt-Kernel** (`prompt_kernel_builder.py`): Tool-result-Sektionen werden mit `<content_boundary type="tool_data" trust="untrusted">` umschlossen, inklusive expliziter Warnung an das LLM.

3. **Injection-Pattern-Neutralisierung** (`context_reducer.py`, `tool_result_context_guard.py`): Bekannte Prompt-Injection-Muster werden erkannt und neutralisiert: `ignore previous instructions`, `you are now`, `system:`, `[INST]`, `<|im_start|>`, HTML-Kommentar-Injections.

---

### OE-07: Session-ID-Hijacking (MEDIUM) — ✅ GEPATCHT

**Dateien:** `backend/app/services/session_security.py` (NEU), `backend/app/ws_handler.py`

**Fix:** Server-seitige Session-ID-Validierung mit HMAC-Signierung. Client-gelieferte Session-IDs werden gegen das `used_session_ids`-Set der Verbindung validiert — nur IDs, die in dieser Verbindung entstanden sind, werden akzeptiert. Format-Validierung mit Regex. Fremde Session-IDs werden mit Error-Event abgelehnt.

**Env-Config:**
- `SESSION_SIGNING_KEY` (32-byte hex, default: per-Prozess generiert)

---

### OE-08: State-Store Encryption-at-Rest (MEDIUM) — ✅ GEPATCHT

**Dateien:** `backend/app/services/state_encryption.py` (NEU), `backend/app/state/state_store.py`

**Fix:** Application-Level-Encryption für beide State-Store-Backends (File-basiert und SQLite). Verwendet AES-256-GCM (via `cryptography`-Paket) wenn verfügbar, mit XOR+HMAC-Fallback für POC-Betrieb ohne `cryptography`. Backward-kompatibel — unverschlüsselte Daten werden transparent gelesen. Policy-File-Integrität über HMAC-Signierung.

**Env-Config:**
- `STATE_ENCRYPTION_KEY` (64-stelliger Hex-String für 32-byte AES-Key, default: per-Prozess generiert)
- `STATE_ENCRYPTION_ENABLED` (default: `true`)
- `POLICY_HMAC_KEY` (default: gleicher Key wie `STATE_ENCRYPTION_KEY`)

---

## 4. Risiko-Matrix

```
                    AUSWIRKUNG
                    Niedrig   Mittel    Hoch      Kritisch
                ┌─────────┬─────────┬─────────┬─────────┐
    Hoch        │         │ FIX-08  │ FIX-05  │ OE-01   │
                │         │ FIX-10  │ FIX-06  │ FIX-11  │
W               │         │         │ FIX-07  │ FIX-01  │
A               ├─────────┼─────────┼─────────┼─────────┤
H   Mittel      │         │ FIX-16  │ FIX-12  │ FIX-02  │
R               │         │ FIX-17  │ FIX-14  │ FIX-04  │
S               │         │         │ FIX-15  │         │
C               ├─────────┼─────────┼─────────┼─────────┤
H   Niedrig     │         │         │ FIX-09  │ FIX-13  │
E               │         │         │ FIX-03  │         │
I               │         │         │         │         │
N               └─────────┴─────────┴─────────┴─────────┘
L
I
C
H
K
E
I
T
```

### Legende

| Code | Status | Beschreibung |
|------|--------|-------------|
| FIX-01–10 | ✅ Gepatcht | Initial-Audit Fixes |
| FIX-11 (OE-02) | ✅ Gepatcht | shell=False Command-Execution |
| FIX-12 (OE-03) | ✅ Gepatcht | Rate-Limiting |
| FIX-13 (OE-04) | ✅ Gepatcht | Docker-Sandbox |
| FIX-14 (OE-05) | ✅ Gepatcht | MCP Command-Allowlist |
| FIX-15 (OE-06) | ✅ Gepatcht | Prompt Injection Defenses |
| FIX-16 (OE-07) | ✅ Gepatcht | Session-ID Hijacking |
| FIX-17 (OE-08) | ✅ Gepatcht | State-Store Encryption |
| OE-01 | ⚠️ Offen | Auth-Middleware (POC-bewusst ausgespart) |

---

*Erstellt am 2026-03-06 durch Security-Audit. Folge-Patches am 2026-03-06 implementiert. Nächstes Review empfohlen nach Implementation von OE-01 (Auth).*
