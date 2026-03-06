# Security Patch Bug Report

**Datum:** 2026-03-06  
**Reviewer:** AI Code Review  
**Scope:** Vollständiges Security-Patch-Changeset (Wave 2 + Wave 3)  
**Dateien reviewed:** ~60 geänderte Dateien (Backend + Frontend)

---

## Zusammenfassung

| Schweregrad | Anzahl | Status |
|---|---|---|
| 🔴 Kritisch (Production-Breaking) | 3 | Offen |
| 🟡 Mittel (Funktionale Bugs) | 4 | Offen |
| 🟢 Niedrig (Code Quality / Dead Code) | 3 | Offen |

---

## 🔴 Bug 1: HTTPS DNS-Pinning bricht TLS-Zertifikatsvalidierung

### Betroffene Dateien

- `backend/app/url_validator.py` → `enforce_safe_url()` (Zeilen 118–156)
- `backend/app/tools.py` → `_enforce_safe_web_target()` (Zeilen 675–688)
- `backend/tests/test_tools_web_fetch_security.py` (alle HTTPS-Tests)

### Beschreibung

Die neue zentrale `enforce_safe_url()`-Funktion gibt **immer** eine gepinnte IP-Adresse zurück, wenn der Hostname per DNS aufgelöst wurde — unabhängig davon, ob es sich um HTTP oder HTTPS handelt.

Der **alte Code** in `tools.py` hatte einen expliziten Guard:

```python
# Pin DNS to the validated IP for HTTP to close the TOCTOU gap.
# For HTTPS, TLS certificate validation binds the connection to the
# legitimate hostname, so DNS-pinning would break SNI/cert matching.
if parsed.scheme == "https":
    return None
```

Dieser Guard fehlt in `enforce_safe_url()` komplett. Das bedeutet:

1. `enforce_safe_url("https://example.com")` → gibt `"93.184.216.34"` zurück
2. `apply_dns_pin("https://example.com/path", "93.184.216.34")` → erzeugt `"https://93.184.216.34/path"`
3. `httpx` verbindet sich zu `93.184.216.34:443` und setzt TLS-SNI auf `93.184.216.34`
4. Der Server präsentiert ein Zertifikat für `example.com`, nicht für `93.184.216.34`
5. **TLS-Handshake schlägt fehl** → `ssl.SSLCertVerificationError`

### Warum die Tests das nicht fangen

Die Tests verwenden einen Fake-HTTP-Client (`_FakeClient`), der kein echtes TLS macht. Die Tests wurden sogar aktualisiert, um die gepinnten IPs in den Response-Dictionaries zu erwarten:

```python
# SEC FIX-01: DNS pinning now applies to HTTPS too — URLs are rewritten to pinned IP
responses = {
    "https://93.184.216.34/start": _FakeResponse(...),    # ← test adapted to new behavior
    "https://93.184.216.34/final": _FakeResponse(...),
}
```

Das verdeckt den Bug: Die Tests "beweisen" nur, dass der Code die URL umschreibt — nicht, dass HTTPS danach noch funktioniert.

### Impact

**Jeder `web_fetch()` und `http_request()` Aufruf mit HTTPS-URL schlägt in Production fehl.**  
Das betrifft ~99% aller Web-Requests, da praktisch alle realen URLs HTTPS verwenden.

### Fix-Vorschlag

In `url_validator.py`, `enforce_safe_url()` muss den Scheme prüfen:

```python
# Option A: Kein Pinning für HTTPS (wie vorher)
parsed = urlparse((url or "").strip())
# ... validation ...
if parsed.scheme == "https":
    return None  # TLS cert validation prevents DNS-rebinding
return str(next(iter(resolved_ips)))

# Option B: Pinning + explizites SNI (erfordert httpx-Konfiguration)
# httpx unterstützt kein natives server_hostname-Override ohne Transport-Customization
```

### Pros & Cons des Fixes

**Pros:**
- **Production-kritisch:** Ohne Fix funktioniert kein einziger HTTPS web_fetch/http_request-Aufruf
- Stellt das vorherige, bewährte Verhalten wieder her
- TLS-Zertifikatsvalidierung ist ein wirksamer Schutz gegen DNS-Rebinding bei HTTPS — das Pinning ist dort unnötig
- Alle bestehenden Integrationstests und User-Workflows funktionieren wieder

**Cons:**
- Theoretisches TOCTOU-Fenster bei HTTPS bleibt offen (DNS-Auflösung → TCP-Connect), aber:
  - TLS-Zertifikat bindet die Verbindung an den legitimen Host
  - Ein Angreifer müsste gleichzeitig DNS spoofen UND ein gültiges Zertifikat besitzen
  - Dieses Risiko wurde im alten Code bewusst akzeptiert und kommentiert
- Option B (Pinning + SNI) wäre sicherer, erfordert aber custom httpx-Transport-Konfiguration und ist deutlich komplexer

---

## 🔴 Bug 2: Monkeypatch-Ziel `tools_module.socket` existiert nicht mehr

### Betroffene Dateien

- `backend/tests/test_tools_web_fetch_security.py` (5 Stellen: Zeilen 85, 95, 116, 143, 166)
- `backend/tests/test_agent_tooling_extended.py` (2 Stellen: Zeilen 149, 209)
- `backend/tests/test_http_request_tool.py` (1 Stelle: Zeile 79)

### Beschreibung

Der Security-Patch hat `import socket` aus `backend/app/tools.py` entfernt, weil die DNS-Auflösung jetzt in `url_validator.py` stattfindet. Allerdings verwenden **8 bestehende Tests** weiterhin:

```python
monkeypatch.setattr(tools_module.socket, "getaddrinfo", _public_getaddrinfo)
```

Da `tools_module` (`app.tools`) kein `socket`-Attribut mehr hat, schlägt jeder dieser Tests mit `AttributeError` fehl:

```
AttributeError: module 'app.tools' has no attribute 'socket'
```

### Impact

8 Tests sind komplett kaputt. Die SSRF-Security-Tests, die das Kernverhalten des Patches validieren sollen, laufen nicht mehr durch. Das bedeutet:
- **Die Sicherheitsgarantien des Patches sind nicht verifiziert**
- CI/CD-Pipeline schlägt fehl (sofern Tests geprüft werden)

### Fix-Vorschlag

Alle 8 Stellen müssen auf das neue Modul zeigen:

```python
import app.url_validator as url_validator_module

# statt:
monkeypatch.setattr(tools_module.socket, "getaddrinfo", _public_getaddrinfo)

# neu:
monkeypatch.setattr(url_validator_module.socket, "getaddrinfo", _public_getaddrinfo)
```

### Pros & Cons des Fixes

**Pros:**
- **Ohne Fix sind die 8 SSRF-Tests nicht lauffähig** — keine Validierung der Security-Fixes
- Einfacher, risikoloser Fix (nur Import-Target tauschen)
- CI/CD-Pipeline wird wieder grün
- Das Monkeypatching-Ziel stimmt dann mit dem tatsächlichen Code überein

**Cons:**
- Keiner. Es gibt keinen Grund, diesen Fix nicht zu machen.
- Einziger Aufwand: 8 Zeilen ändern + ggf. Import-Zeile hinzufügen

---

## 🔴 Bug 3: `__import__` statt regulärem Import in `_enforce_safe_web_target`

### Betroffene Dateien

- `backend/app/tools.py` → `_enforce_safe_web_target()` (Zeilen 683–686)

### Beschreibung

```python
def _enforce_safe_web_target(self, url: str) -> str | None:
    try:
        return __import__("app.url_validator", fromlist=["enforce_safe_url"]).enforce_safe_url(
            url, label="web_fetch"
        )
    except UrlValidationError as exc:
        raise ToolExecutionError(str(exc)) from exc
```

Obwohl `UrlValidationError` und vier weitere Symbole (`apply_dns_pin`, `parse_ip_literal`, `resolve_hostname_ips`, `validate_ip_is_public`) bereits am Top-of-File aus `app.url_validator` importiert werden, wird `enforce_safe_url` hier per `__import__()` dynamisch geladen.

### Probleme

1. **`ImportError` wird nicht gefangen:** Wenn `app.url_validator` aus irgendeinem Grund nicht ladbar ist, wirft `__import__` einen `ImportError`, der durch `except UrlValidationError` **nicht** gefangen wird → unkontrollierter Crash
2. **Unmöglich zu mocken:** Tests können `enforce_safe_url` nicht per `monkeypatch.setattr` ersetzen, weil der Code das Modul bei jedem Aufruf neu auflöst
3. **Inkonsistent mit dem Rest der Datei:** Alle anderen Wrapper (`_parse_ip_literal`, `_validate_ip_is_public`, etc.) nutzen die Top-Level-Imports — nur dieser eine nicht
4. **Codeanalyse-Tools** (pyright, mypy, ruff) können den `__import__`-Aufruf nicht statisch analysieren

### Fix-Vorschlag

`enforce_safe_url` zum Top-Level-Import hinzufügen:

```python
from app.url_validator import (
    UrlValidationError,
    apply_dns_pin as _shared_apply_dns_pin,
    enforce_safe_url as _shared_enforce_safe_url,   # ← hinzufügen
    parse_ip_literal as _shared_parse_ip_literal,
    resolve_hostname_ips as _shared_resolve_hostname_ips,
    validate_ip_is_public as _shared_validate_ip_is_public,
)
```

Und in der Methode:

```python
def _enforce_safe_web_target(self, url: str) -> str | None:
    try:
        return _shared_enforce_safe_url(url, label="web_fetch")
    except UrlValidationError as exc:
        raise ToolExecutionError(str(exc)) from exc
```

### Pros & Cons des Fixes

**Pros:**
- Eliminiert den fragilen `__import__`-Call und das `ImportError`-Risiko
- Macht die Funktion testbar/mockbar wie alle anderen Wrapper
- Konsistent mit dem bestehenden Import-Pattern in der gleichen Datei
- Statische Analyse-Tools können den Code wieder validieren
- Null Risiko: `enforce_safe_url` existiert bereits im selben Modul, das ohnehin importiert wird

**Cons:**
- Keiner. Der `__import__`-Aufruf hat keinerlei Vorteil gegenüber einem regulären Import.
- Möglicherweise war die Absicht, einen zirkulären Import zu vermeiden — aber da 5 andere Symbole aus dem gleichen Modul bereits importiert werden, ist das kein Grund.

---

## 🟡 Bug 4: `SecretFilter` bricht dict-basierte Logging-Args

### Betroffene Dateien

- `backend/app/services/log_secret_filter.py` → `SecretFilter.filter()` (Zeilen 24–36)

### Beschreibung

Pythons `logging`-Modul unterstützt zwei Arten von Format-Argumenten:

```python
# Tuple-basiert:
logger.info("user=%s token=%s", username, token)  # record.args = (username, token)

# Dict-basiert:
logger.info("%(user)s logged in", {"user": "admin"})  # record.args = {"user": "admin"}
```

Der `SecretFilter` behandelt `record.args` so:

```python
if record.args:
    sanitized_args: list[object] = []
    for arg in (record.args if isinstance(record.args, tuple) else (record.args,)):
        ...
    record.args = tuple(sanitized_args)
```

Wenn `record.args` ein `dict` ist:
1. `isinstance(record.args, dict)` → False für den `tuple`-Check
2. `(record.args,)` → das dict wird in ein 1-Tupel gewrapt
3. `record.args = tuple(sanitized_args)` → `({"user": "admin"},)` — ein Tuple mit einem Dict

Pythons Formatter erwartet dann ein Dict für `%(user)s`, bekommt aber ein Tuple → `TypeError: not enough arguments for format string`.

### Impact

Jeder Log-Aufruf mit dict-basierten Argumenten crasht, wenn der `SecretFilter` installiert ist. Das betrifft vor allem:
- Structured Logging-Frameworks
- Legacy-Code der dict-basierte Formatierung nutzt
- Third-Party-Libraries

### Fix-Vorschlag

```python
def filter(self, record: logging.LogRecord) -> bool:
    if isinstance(record.msg, str):
        for pattern, replacement in _SECRET_PATTERNS:
            record.msg = pattern.sub(replacement, record.msg)
    if record.args:
        if isinstance(record.args, dict):
            record.args = {
                k: self._sanitize_value(v)
                for k, v in record.args.items()
            }
        elif isinstance(record.args, tuple):
            record.args = tuple(self._sanitize_value(a) for a in record.args)
        else:
            # Single non-tuple arg
            record.args = (self._sanitize_value(record.args),)
    return True

def _sanitize_value(self, value: object) -> object:
    if isinstance(value, str):
        for pattern, replacement in _SECRET_PATTERNS:
            value = pattern.sub(replacement, value)
    return value
```

### Pros & Cons des Fixes

**Pros:**
- Verhindert `TypeError`-Crashes bei dict-basierten Log-Aufrufen
- Der Logging-Filter ist auf dem Root-Logger installiert → betrifft **alle** Logger im Prozess, inkl. Third-Party
- Robusteres Handling für alle drei `record.args`-Typen (tuple, dict, single)

**Cons:**
- Etwas mehr Code-Komplexität im Filter
- Aktuell nutzt die Codebase vermutlich nur tuple-basierte Logging-Args — der Bug tritt also nur bei zukünftigem Code oder Third-Party-Libraries auf
- Wenn man sicher weiß, dass nie dict-basierte Args verwendet werden, ist der Bug harmlos (aber ein Logging-Filter auf dem Root-Logger sollte alle Fälle korrekt behandeln)

---

## 🟡 Bug 5: `@pytest.mark.asyncio` ohne `pytest-asyncio`-Dependency

### Betroffene Dateien

- `backend/tests/test_security_wave2.py` (Zeilen 133, 161 — `TestSHL01RecoveryAllowlist`)
- `backend/requirements-test.txt` — fehlendes Package

### Beschreibung

Zwei Tests in `test_security_wave2.py` verwenden den `@pytest.mark.asyncio`-Dekorator:

```python
class TestSHL01RecoveryAllowlist:
    @pytest.mark.asyncio
    async def test_blocked_recovery_command(self) -> None:
        ...

    @pytest.mark.asyncio
    async def test_allowed_recovery_command(self) -> None:
        ...
```

Das Package `pytest-asyncio` ist aber weder in `requirements-test.txt` noch in `requirements.txt` aufgeführt:

```
# requirements-test.txt
pytest==8.3.5
pytest-cov==7.0.0
ruff>=0.9.0
```

### Verhalten ohne `pytest-asyncio`

Ohne das Plugin erkennt pytest den `asyncio`-Marker nicht. Je nach pytest-Version:
- **Warnung:** `PytestUnknownMarkWarning: Unknown pytest.mark.asyncio`
- **Test wird übersprungen** oder **der Coroutine-Body wird nicht ausgeführt** — pytest gibt "passed" zurück, ohne den Test wirklich zu laufen (False Positive)
- Alternativ: pytest führt den Test synchron aus, bekommt ein Coroutine-Objekt zurück, und gibt ihn als "passed" aus (das Coroutine-Objekt ist truthy)

### Der Rest der Codebase

Alle anderen async-Tests in der Codebase verwenden das Pattern:

```python
def test_something() -> None:
    async def _run():
        ...
    asyncio.run(_run())
```

Dieses Pattern funktioniert ohne `pytest-asyncio`.

### Fix-Vorschlag

**Option A** (konsistent mit Codebase):
```python
def test_blocked_recovery_command(self) -> None:
    async def _run() -> None:
        plan = RecoveryPlan(...)
        healer = SelfHealingLoop(plans=[plan])
        run_fn = AsyncMock(return_value="ok")
        result = await healer.heal_and_retry(...)
        ...
    asyncio.run(_run())
```

**Option B** (pytest-asyncio hinzufügen):
```
# requirements-test.txt
pytest-asyncio>=0.23.0
```

### Pros & Cons des Fixes

**Pros:**
- **Ohne Fix validieren die SHL-01 Recovery-Allowlist-Tests gar nichts** — sie laufen durch, ohne den Test-Body auszuführen
- Die Recovery-Allowlist ist ein Sicherheitsfeature — ein nicht-laufender Test gefährdet die Garantie
- Option A erfordert keine neue Dependency und ist konsistent mit dem Rest der Tests

**Cons:**
- Option A: Etwas mehr Boilerplate (`asyncio.run()`-Wrapper)
- Option B: Neue Dependency (`pytest-asyncio`) für nur 2 Tests ist Over-Engineering
- Option B: `pytest-asyncio` kann Konflikte mit `anyio`-basiertem Test-Handling erzeugen (das Projekt nutzt `anyio` für einige Guards)

**Empfehlung:** Option A (Konsistenz mit Codebase).

---

## 🟡 Bug 6: CSP `connect-src` blockiert jeden Nicht-localhost-Betrieb

### Betroffene Dateien

- `frontend/src/index.html` (Zeile 7 — CSP Meta-Tag)

### Beschreibung

```html
<meta http-equiv="Content-Security-Policy"
  content="default-src 'self';
           script-src 'self';
           style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
           font-src 'self' https://fonts.gstatic.com;
           connect-src 'self' ws://localhost:* http://localhost:* ws://127.0.0.1:* http://127.0.0.1:*;
           img-src 'self' data:;
           object-src 'none';
           base-uri 'self';
           form-action 'self';">
```

**Probleme in der `connect-src`-Direktive:**

1. **Kein `wss://`**: WebSocket-Verbindungen über TLS werden blockiert
2. **Kein `https://`**: API-Requests an ein Remote-Backend (HTTPS) werden blockiert
3. **Nur `localhost` und `127.0.0.1`**: Jede Production-Deployment auf einer anderen Domain/IP ist kaputt
4. **Keine Wildcards für Production-Domains**: z.B. `https://api.example.com` wird blockiert

### Impact

- **Lokale Entwicklung:** Funktioniert (HTTP + WS auf localhost)
- **Production/Staging:** Jeder WebSocket-Connect und jeder API-Call wird vom Browser geblockt
- **HTTPS-Deployment:** Auch lokal mit HTTPS (z.B. via nginx-Reverse-Proxy) schlägt fehl

### Fix-Vorschlag

```html
<!-- Option A: Zur Build-Zeit konfigurierbar machen -->
<!-- angular.json fileReplacements für CSP, oder environment.ts -->

<!-- Option B: Breiter für MVP -->
connect-src 'self'
  ws://localhost:* wss://localhost:*
  http://localhost:* https://localhost:*
  ws://127.0.0.1:* wss://127.0.0.1:*
  http://127.0.0.1:* https://127.0.0.1:*;

<!-- Option C: Server-seitiger CSP-Header statt Meta-Tag (best practice) -->
<!-- CSP als HTTP-Header im Reverse-Proxy konfigurieren -->
```

### Pros & Cons des Fixes

**Pros:**
- Ohne Fix ist das Frontend in **jeder Nicht-localhost-Umgebung** nicht funktionsfähig
- CSP-Fehler sind im Browser nur in der DevTools-Console sichtbar — schwer zu debuggen
- Option C (Server-Header) ist Best Practice, da der Meta-Tag nicht alle CSP-Direktiven unterstützt (z.B. `frame-ancestors`)

**Cons:**
- Option B: `wss://*` wäre zu breit und öffnet Data-Exfiltration-Vektoren
- Option C: Erfordert Server-Konfiguration, die nicht im Frontend-Repo liegt
- Eine zu breite CSP ist schlimmer als keine — besser strict und konfigurierbar
- Der aktuelle Meta-Tag ist für die lokale Entwicklung korrekt und sicher — in Production sollte er durch einen Server-Header ersetzt werden

---

## 🟡 Bug 7: Race-Condition durch async `getItem` in `ngOnInit`

### Betroffene Dateien

- `frontend/src/app/pages/chat-page.component.ts` (Zeilen 164–174)
- `frontend/src/app/services/secure-storage.service.ts`

### Beschreibung

**Vorher (synchron):**
```typescript
ngOnInit(): void {
    this.socketService.connect(this.wsUrl);

    const persistedRuntime = localStorage.getItem('preferredRuntime');  // ← synchron
    if (persistedRuntime === 'local' || persistedRuntime === 'api') {
        this.runtimeTarget = persistedRuntime;                          // ← sofort gesetzt
        this.firstRunChoicePending = false;
    }
    // ... rest of init ...
```

**Nachher (async):**
```typescript
ngOnInit(): void {
    this.socketService.connect(this.wsUrl);  // ← WS sofort geöffnet

    this.secureStorage.getItem('preferredRuntime').then(persistedRuntime => {
        // ← AES-GCM-Entschlüsselung läuft async
        if (persistedRuntime === 'local' || persistedRuntime === 'api') {
            this.runtimeTarget = persistedRuntime;   // ← erst NACH crypto-Operation gesetzt
            this.firstRunChoicePending = false;
        }
        this.cdr.markForCheck();
    });
    // ... rest of init läuft PARALLEL weiter ...
```

### Race-Condition-Szenario

1. `ngOnInit()` startet → WebSocket verbindet sofort
2. `getItem()` startet async crypto-Entschlüsselung (AES-GCM Key-Derivation + Decrypt)
3. Während die Entschlüsselung läuft (~1-5ms), kann der `agentsService.getRuntimeStatus()` HTTP-Call bereits zurückkommen
4. Der Status-Handler liest `this.runtimeTarget`, das noch auf dem Default-Wert steht
5. `runtimeTarget` wird dann überschrieben, nachdem der Status schon verarbeitet wurde

### Impact

- **Worst Case:** Erster Request wird mit falschem Runtime-Target ausgeführt
- **Typisch:** Flickering der UI (Runtime-Choice-Dialog erscheint kurz, obwohl Preference gespeichert ist)
- **Best Case:** AES-GCM ist schnell genug und das Promise resolved vor dem HTTP-Response → kein sichtbares Problem

### Fix-Vorschlag

```typescript
async ngOnInit(): Promise<void> {
    // Lade Preference VOR WebSocket-Connect
    const persistedRuntime = await this.secureStorage.getItem('preferredRuntime');
    if (persistedRuntime === 'local' || persistedRuntime === 'api') {
        this.runtimeTarget = persistedRuntime;
        this.firstRunChoicePending = false;
    } else {
        this.firstRunChoicePending = true;
    }

    this.socketService.connect(this.wsUrl);
    // ... rest of init ...
}
```

Oder, da Angular `ngOnInit` nicht nativ awaited:

```typescript
ngOnInit(): void {
    this.initAsync();
}

private async initAsync(): Promise<void> {
    const persistedRuntime = await this.secureStorage.getItem('preferredRuntime');
    // ... set runtimeTarget ...
    this.socketService.connect(this.wsUrl);
    // ... rest ...
}
```

### Pros & Cons des Fixes

**Pros:**
- Eliminiert die Race-Condition vollständig
- Garantiert, dass `runtimeTarget` korrekt gesetzt ist, bevor der WebSocket geöffnet wird
- Kein UI-Flickering beim Start
- Korrekte Reihenfolge: Preference laden → Runtime setzen → verbinden

**Cons:**
- WebSocket-Connect wird um ~1-5ms verzögert (Key-Derivation + AES-GCM-Decrypt)
- Angular awaited `ngOnInit` nicht nativ — der Fix erfordert ein separates `initAsync()`-Pattern
- Wenn die Crypto-API nicht verfügbar ist (z.B. HTTP statt HTTPS), fällt der Service auf `localStorage.getItem()` zurück (synchron) — aber die Promise-Wrapper-Logik bleibt async
- Für den aktuellen Use Case (nur `preferredRuntime`) ist die Race-Condition in der Praxis selten sichtbar

---

## 🟢 Bug 8: Doppelte Output-Truncation in `run_command`

### Betroffene Dateien

- `backend/app/tools.py` (Zeilen 826–831)

### Beschreibung

```python
output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
output = output.strip() or "(no output)"

# SEC (CMD-11): Truncate command output to prevent memory exhaustion
_MAX_CMD_OUTPUT = 100_000
if len(output) > _MAX_CMD_OUTPUT:
    output = output[:_MAX_CMD_OUTPUT] + "\n... [output truncated]"     # Truncation bei 100K

self._raise_if_env_missing(...)
return f"exit_code={completed.returncode}\n{output[:12000]}"           # Nochmal bei 12K
```

Die 100K-Truncation hat keinen Effekt auf den Return-Wert, weil `output[:12000]` den String ohnehin auf 12K kürzt. Der einzige Ort, wo die 100K-Truncation einen Unterschied macht, ist `_raise_if_env_missing()`, das den vollen `output` bekommt.

### Impact

- Kein Funktionaler Bug
- Die `_MAX_CMD_OUTPUT`-Truncation schützt vor Memory-Exhaustion durch den `output`-String **bevor** er an `_raise_if_env_missing()` übergeben wird — das ist sinnvoll
- Aber der Kommentar "prevent memory exhaustion" ist irreführend, weil der Return-Wert ohnehin bei 12K gekürzt wird

### Pros & Cons des Fixes

**Pros:**
- Klarerer Code: Entweder konsistente Truncation (nur einmal) oder besserer Kommentar
- Die 100K-Truncation schützt tatsächlich die `_raise_if_env_missing()`-Funktion — der Kommentar sollte das widerspiegeln

**Cons:**
- Lower-Priority: Funktional korrekt, nur etwas verwirrend
- Die 100K-Truncation ist nicht nutzlos — sie begrenzt den String, der an `_raise_if_env_missing` übergeben wird
- Keine Dringlichkeit

---

## 🟢 Bug 9: `crossorigin` auf falschem Google Fonts Preconnect

### Betroffene Dateien

- `frontend/src/index.html` (Zeile 12)

### Beschreibung

```html
<link rel="preconnect" href="https://fonts.googleapis.com" crossorigin>   <!-- ← falsch -->
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>      <!-- ← korrekt -->
```

- `fonts.googleapis.com` liefert die **CSS-Datei** — wird mit einem normalen `<link rel="stylesheet">` geladen (kein CORS)
- `fonts.gstatic.com` liefert die **Font-Binaries** — werden per CSS `@font-face` mit `font-display: swap` geladen (CORS)

Das `crossorigin`-Attribut auf dem googleapis-Preconnect erzeugt eine **CORS-Preconnection** (mit `Origin`-Header), aber die tatsächliche CSS-Anfrage wird **ohne CORS** gemacht. Das bedeutet:
1. Der Browser öffnet eine CORS-Verbindung (mit `crossorigin`)
2. Die CSS-Anfrage braucht eine Non-CORS-Verbindung
3. Die CORS-Verbindung wird verworfen → neue Verbindung wird geöffnet
4. **Doppelte TCP+TLS-Handshakes** statt eines einzigen

### Impact

- ~100-300ms zusätzliche Latenz beim Font-Loading (je nach Netzwerk)
- Keine funktionale Auswirkung
- Keine Security-Auswirkung

### Fix

```html
<link rel="preconnect" href="https://fonts.googleapis.com">               <!-- ohne crossorigin -->
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>      <!-- mit crossorigin -->
```

### Pros & Cons des Fixes

**Pros:**
- Eliminiert eine unnötige doppelte TCP+TLS-Verbindung
- Folgt den Google Fonts Best Practices exakt
- Schnellerer Font-Load um ~100-300ms

**Cons:**
- Sehr geringe Priorität — betrifft nur das initiale Font-Loading
- Kein funktionaler Unterschied
- Nur eine Zeile zu ändern

---

## 🟢 Bug 10: Fire-and-Forget `setItem` ohne Error-Handling

### Betroffene Dateien

- `frontend/src/app/pages/chat-page.component.ts` (Zeilen 195, 653, 741, 760)

### Beschreibung

An 4 Stellen wird `setItem` aufgerufen, ohne die returned Promise zu behandeln:

```typescript
this.secureStorage.setItem('preferredRuntime', status.runtime);        // ← Promise ignored
this.secureStorage.setItem('preferredRuntime', target);                // ← Promise ignored
```

`setItem()` gibt eine `Promise<void>` zurück. Wenn die AES-GCM-Verschlüsselung fehlschlägt (z.B. Web Crypto nicht verfügbar auf HTTP), fällt der Service zwar auf plaintext-`localStorage` zurück (per `catch`-Block im Service), aber:

1. Wenn selbst der `localStorage.setItem()`-Fallback fehlschlägt (z.B. `QuotaExceededError`), wird die Exception stillschweigend verschluckt
2. TypeScript/ESLint `no-floating-promises`-Regel (wenn aktiviert) flaggt das als Fehler

### Impact

- Minimal: Die Preference wird nicht gespeichert, User muss Runtime beim nächsten Besuch erneut wählen
- Keine Crash-Gefahr (der Service fängt Fehler intern ab)

### Fix

```typescript
// Option A: void-Operator für bewusstes Ignorieren
void this.secureStorage.setItem('preferredRuntime', status.runtime);

// Option B: catch-Block für Logging
this.secureStorage.setItem('preferredRuntime', status.runtime)
  .catch(err => console.warn('Failed to persist runtime preference:', err));
```

### Pros & Cons des Fixes

**Pros:**
- Explicit intent: `void` zeigt, dass das Ignorieren bewusst ist
- Option B gibt Debugging-Info, wenn Storage fehlschlägt
- Sauberer TypeScript-Stil

**Cons:**
- Sehr geringe Priorität
- Der Service hat bereits internen Fallback — das Problem tritt praktisch nie auf
- Minimal Noise im Code

---

## Zusammenfassung der empfohlenen Prioritäten

| # | Bug | Schweregrad | Empfehlung | Aufwand |
|---|---|---|---|---|
| 1 | HTTPS DNS-Pinning bricht TLS | 🔴 Kritisch | **Sofort fixen** — Production-Breaking | Klein (5 Zeilen in `url_validator.py`) |
| 2 | Monkeypatch-Ziel existiert nicht | 🔴 Kritisch | **Sofort fixen** — 8 Tests kaputt | Klein (8 Zeilen + Import) |
| 3 | `__import__` statt regulärer Import | 🔴 Kritisch | **Sofort fixen** — fragil & untestbar | Trivial (2 Zeilen) |
| 4 | SecretFilter bricht dict-Args | 🟡 Mittel | Vor Merge fixen | Klein (10 Zeilen) |
| 5 | `@pytest.mark.asyncio` ohne Plugin | 🟡 Mittel | Vor Merge fixen — Tests laufen nicht wirklich | Klein (4 Zeilen) |
| 6 | CSP blockiert Nicht-localhost | 🟡 Mittel | Vor Production-Deploy fixen | Mittel (Architektur-Entscheidung) |
| 7 | Race-Condition async `getItem` | 🟡 Mittel | Vor Merge fixen | Klein (10 Zeilen) |
| 8 | Doppelte Output-Truncation | 🟢 Niedrig | Optional — Kommentar verbessern | Trivial |
| 9 | `crossorigin` auf falschem Preconnect | 🟢 Niedrig | Optional — Performance | Trivial (1 Zeile) |
| 10 | Fire-and-Forget `setItem` | 🟢 Niedrig | Optional — Code Quality | Trivial (4 Zeilen) |

---

## Positives am Patch

Trotz der oben genannten Bugs enthält der Security-Patch viele solide Verbesserungen:

1. **Zentralisierte SSRF-Validierung** (`url_validator.py`) — eliminiert Code-Duplikation und stellt konsistente Validierung sicher
2. **WebSocket Origin-Check** (WS-01) — wichtige Defense-in-Depth gegen CSRF via WebSocket
3. **Error-Message-Sanitization** (WS-03) — verhindert Information-Leakage in Production
4. **Background-Job Session-Ownership** (CMD-12) — verhindert Cross-Session Job-Killing
5. **Command-Output-Truncation** (CMD-11) — schützt vor Memory-Exhaustion
6. **Additional Command-Safety-Patterns** (CMD-09) — erweitert die Blocklist sinnvoll
7. **CSP Meta-Tag** (FE-01) — wichtige XSS-Mitigation (trotz connect-src-Problem)
8. **Subresource Integrity** im Angular Build — schützt vor CDN-Kompromittierung
9. **Dependency-Pinning** im Frontend — verhindert unerwartete Breaking Changes
10. **Ruff-Linter-Konfiguration** — verbessert Code-Quality langfristig
11. **Security-Audit CI-Workflow** — automatisierte Vulnerability-Scans
12. **Log-Secret-Filter** (CFG-07) — verhindert Secret-Leakage in Logs (trotz dict-Bug)
13. **`SecureStorageService`** — zukunftssicherer verschlüsselter Storage
14. **Session-ID-Hashing für Dateinamen** (MEM-03) — verhindert Path-Traversal über Session-IDs
15. **Recovery-Command-Allowlist** (SHL-01) — verhindert arbitrary Command-Execution über Self-Healing
