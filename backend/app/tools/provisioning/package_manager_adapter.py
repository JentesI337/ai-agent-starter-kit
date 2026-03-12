"""L3.4–L3.5  PackageManagerAdapter — Protocol + concrete adapters.

Provides a uniform interface for probing and searching across
package managers (npm, pip, apt, brew, choco).  Each adapter only
*builds* the shell command strings — actual execution is left to
the caller (usually ``ToolDiscoveryEngine``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class PackageCandidate:
    """A candidate package returned by an adapter search."""

    name: str
    version: str = ""
    description: str = ""
    manager: str = ""       # "npm" | "pip" | "apt" | "brew" | "choco"
    install_command: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "manager": self.manager,
            "install_command": self.install_command,
        }


@runtime_checkable
class PackageManagerAdapter(Protocol):
    """Abstract adapter for one package manager."""

    @property
    def manager_name(self) -> str:
        """Human-readable manager identifier, e.g. ``'npm'``."""
        ...

    def probe_command(self) -> str:
        """Shell command to check whether this manager is installed.

        Expected exit code 0 when available.
        """
        ...

    def search_command(self, query: str) -> str:
        """Shell command that searches for *query*.

        The raw stdout is fed into ``parse_search_output`` afterwards.
        """
        ...

    def parse_search_output(self, raw: str) -> list[PackageCandidate]:
        """Parse the raw stdout of the search command into candidates."""
        ...

    def install_command(self, package: str) -> str:
        """Shell command to install *package*."""
        ...


# ── Concrete adapters ─────────────────────────────────────────────────


class NpmAdapter:
    """Adapter for **npm** (Node.js package manager)."""

    @property
    def manager_name(self) -> str:
        return "npm"

    def probe_command(self) -> str:
        return "npm --version"

    def search_command(self, query: str) -> str:
        safe_q = _sanitize(query)
        return f"npm search {safe_q} --json --long 2>/dev/null | head -c 8192"

    def parse_search_output(self, raw: str) -> list[PackageCandidate]:
        import json as _json

        try:
            items = _json.loads(raw)
        except (ValueError, TypeError):
            return []
        if not isinstance(items, list):
            return []
        results: list[PackageCandidate] = []
        for item in items[:20]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            results.append(
                PackageCandidate(
                    name=name,
                    version=str(item.get("version", "")),
                    description=str(item.get("description", ""))[:200],
                    manager="npm",
                    install_command=f"npm install {name}",
                )
            )
        return results

    def install_command(self, package: str) -> str:
        return f"npm install {_sanitize(package)}"


class PipAdapter:
    """Adapter for **pip** (Python package manager)."""

    @property
    def manager_name(self) -> str:
        return "pip"

    def probe_command(self) -> str:
        return "pip --version"

    def search_command(self, query: str) -> str:
        # pip search was removed; use pip index versions as a basic check
        # or fallback to `pip install --dry-run` style.
        # We use a simple `pip index versions` approach (requires pip ≥ 21.2).
        safe_q = _sanitize(query)
        return f"pip index versions {safe_q} 2>&1 | head -c 4096"

    def parse_search_output(self, raw: str) -> list[PackageCandidate]:
        # pip index versions output:  "package_name (1.2.3)"
        candidates: list[PackageCandidate] = []
        for line in raw.splitlines():
            match = re.match(r"^(\S+)\s+\((.+?)\)", line.strip())
            if match:
                name, version = match.group(1), match.group(2)
                candidates.append(
                    PackageCandidate(
                        name=name,
                        version=version,
                        manager="pip",
                        install_command=f"pip install {name}",
                    )
                )
        return candidates

    def install_command(self, package: str) -> str:
        return f"pip install {_sanitize(package)}"


class BrewAdapter:
    """Adapter for **Homebrew** (macOS / Linux)."""

    @property
    def manager_name(self) -> str:
        return "brew"

    def probe_command(self) -> str:
        return "brew --version"

    def search_command(self, query: str) -> str:
        safe_q = _sanitize(query)
        return f"brew search {safe_q} 2>/dev/null | head -c 4096"

    def parse_search_output(self, raw: str) -> list[PackageCandidate]:
        candidates: list[PackageCandidate] = []
        for line in raw.strip().splitlines():
            name = line.strip()
            if name and not name.startswith("="):
                candidates.append(
                    PackageCandidate(
                        name=name,
                        manager="brew",
                        install_command=f"brew install {name}",
                    )
                )
        return candidates[:20]

    def install_command(self, package: str) -> str:
        return f"brew install {_sanitize(package)}"


class ChocoAdapter:
    """Adapter for **Chocolatey** (Windows)."""

    @property
    def manager_name(self) -> str:
        return "choco"

    def probe_command(self) -> str:
        return "choco --version"

    def search_command(self, query: str) -> str:
        safe_q = _sanitize(query)
        return f"choco search {safe_q} --limit-output 2>$null | Select-Object -First 20"

    def parse_search_output(self, raw: str) -> list[PackageCandidate]:
        candidates: list[PackageCandidate] = []
        for line in raw.strip().splitlines():
            parts = line.strip().split("|")
            if len(parts) >= 2:
                name, version = parts[0].strip(), parts[1].strip()
                if name:
                    candidates.append(
                        PackageCandidate(
                            name=name,
                            version=version,
                            manager="choco",
                            install_command=f"choco install {name} -y",
                        )
                    )
        return candidates[:20]

    def install_command(self, package: str) -> str:
        return f"choco install {_sanitize(package)} -y"


# ── helpers ───────────────────────────────────────────────────────────

_UNSAFE_CHARS = re.compile(r"[;&|`$(){}!\[\]<>\"'\\]+")


def _sanitize(value: str) -> str:
    """Strip shell-dangerous characters from user-supplied package names."""
    return _UNSAFE_CHARS.sub("", value).strip()[:128]


def get_platform_adapters() -> list[PackageManagerAdapter]:
    """Return adapters suitable for the current platform.

    Always returns *all* adapters; the caller should use
    ``probe_command()`` to check availability at runtime.
    """
    import sys

    if sys.platform == "win32":
        return [NpmAdapter(), PipAdapter(), ChocoAdapter()]
    if sys.platform == "darwin":
        return [NpmAdapter(), PipAdapter(), BrewAdapter()]
    # linux / other
    return [NpmAdapter(), PipAdapter(), BrewAdapter()]
