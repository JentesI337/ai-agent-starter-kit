# Code Execution Sandbox Tool (Block 10a)

## Meta
- ID: issue-0003
- Status: open
- Priorität: high
- Owner: unassigned
- Erstellt: 2026-03-04
- Zuletzt aktualisiert: 2026-03-04

## Problem (IST)
- `run_command` läuft direkt auf dem Host und ist nicht isoliert.
- Für Berechnungen/Code-Validierung fehlt eine sichere Sandbox-Execution.

## Ziel (SOLL)
Ein neues Tool `code_execute`, das Code sicher in einer isolierten Umgebung ausführt und den Output kontrolliert zurückgibt.

## Scope
- Neue Datei: `backend/app/services/code_sandbox.py`
- Integration als Tool: `code_execute`
- ToolSpec in `backend/app/services/tool_registry.py`
- (Folgearbeit) Argument-Validierung, Tooling-Wiring, Tests

## Lösungsvorschlag

### Neue Service-Datei
`backend/app/services/code_sandbox.py`

```python
"""
CodeSandbox — Sichere Code-Ausführung in isolierter Umgebung.

Strategien (nach Verfügbarkeit):
1. Docker: Startet einen Container, führt Code aus, gibt Output zurück
2. Process-Isolation: subprocess mit Ressourcen-Limits (keine Network-Zugriff)
3. Direct: Fallback — wie run_command aber mit strikteren Safety-Checks

Unterstützte Sprachen: Python, JavaScript/Node.js, Shell
"""

class CodeSandbox:
    def __init__(self, strategy: str = "process"):
        self.strategy = strategy

    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout: int = 30,
        max_output_chars: int = 10000,
    ) -> CodeExecutionResult:
        if self.strategy == "docker":
            return await self._execute_docker(code, language, timeout, max_output_chars)
        elif self.strategy == "process":
            return await self._execute_process(code, language, timeout, max_output_chars)
        return await self._execute_direct(code, language, timeout, max_output_chars)

    async def _execute_process(self, code, language, timeout, max_output_chars):
        """
        Erstellt temp-Datei, führt mit subprocess aus.
        - Python: python -u temp.py
        - Node: node temp.js
        - Keine Network-Zugriff (NETWORK_DISABLED env var)
        - Timeout-Enforcement
        - Output-Truncation
        """
        ...
```

### Neue ToolSpec

```python
"code_execute": ToolSpec(
    name="code_execute",
    required_args=("code",),
    optional_args=("language", "timeout"),
    timeout_seconds=45.0,
    max_retries=0,
    description="Execute code in a sandboxed environment. Use for calculations, data processing, testing code snippets. Supported: python, javascript.",
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "minLength": 1, "description": "The code to execute"},
            "language": {"type": "string", "enum": ["python", "javascript"], "description": "Programming language (default: python)"},
            "timeout": {"type": "integer", "minimum": 1, "maximum": 60, "description": "Execution timeout in seconds"},
        },
        "required": ["code"],
        "additionalProperties": False,
    },
    capabilities=("code_execution", "calculation", "data_analysis", "testing"),
),
```

## Akzeptanzkriterien
- [ ] `CodeSandbox`-Service existiert mit Strategien `docker|process|direct`.
- [ ] `code_execute` ist im Tool-Registry als ToolSpec registriert.
- [ ] Python/JavaScript laufen über `process`-Strategie mit Timeout.
- [ ] Output wird auf `max_output_chars` begrenzt.
- [ ] Fehlerfälle liefern strukturierte Fehlermeldungen statt roher Exceptions.

## Sicherheitsanforderungen
- [ ] Kein ungefilterter Host-Zugriff im `process`-Pfad.
- [ ] Netzwerkzugriff im Sandbox-Prozess standardmäßig deaktiviert/unterbunden.
- [ ] Temporäre Dateien werden zuverlässig bereinigt.
- [ ] Harte Timeout-Enforcement ohne hängende Kindprozesse.

## Test-Strategie
- Unit: `test_code_sandbox.py`
  - Python/JS Erfolgspfad
  - Timeout
  - Output-Truncation
  - Unsupported language
- Security: `test_sandbox_isolation.py`
  - blockierter Netzwerkzugriff
  - begrenzter Dateisystemzugriff
- Integration:
  - ToolSpec vorhanden und ausführbar über Tool-Pipeline

## Risiken
- Plattformunterschiede bei Prozess-/Signalhandling (Windows/Linux).
- False sense of security bei `direct`-Fallback.

## Notizen
- `direct` nur als expliziter Fallback mit stark eingeschränkter Ausführung.
- Für produktiven Einsatz ist Docker/Container-Isolation zu bevorzugen.
