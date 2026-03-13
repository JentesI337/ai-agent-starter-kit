---
name: python-best-practices
description: Idiomatisches Python für Backend-Entwicklung mit Typ-Annotationen, Error Handling und Async.
requires_bins: python
os: windows,linux,darwin
user_invocable: true
disable_model_invocation: false
---

# Python Best Practices

Idiomatisches Python für Backend-Entwicklung.

## Instructions

### Typ-Annotationen
- Alle öffentlichen Funktionen vollständig annotieren
- `from __future__ import annotations` für Forward References
- `Optional[X]` → `X | None` (Python 3.10+)

### Error Handling
- Spezifische Exceptions fangen, nie bare `except:`
- Custom Exceptions von Domänen-spezifischen Basisklassen ableiten
- `raise ... from exc` für Exception-Chaining

### Immutability
- `@dataclass(frozen=True)` für Value Objects
- `tuple` statt `list` für feste Sammlungen
- `MappingProxyType` für read-only Dicts

### Async
- `async def` für I/O-Bound-Operationen
- `asyncio.gather()` für parallele Tasks
- `asyncio.wait_for()` mit explizitem Timeout
- Keine sync-Blockierung in async-Funktionen

### Struktur
- Module < 500 Zeilen (Split bei Überschreitung)
- `__all__` definieren für public API
- Relative Imports innerhalb von Packages

### Beispiel

Input: "Erstelle eine async Funktion zum Lesen einer Datei"
Output:
```python
from __future__ import annotations
import aiofiles

async def read_file_content(path: str, *, encoding: str = "utf-8") -> str:
    """Read file content asynchronously."""
    async with aiofiles.open(path, mode="r", encoding=encoding) as f:
        return await f.read()
```
