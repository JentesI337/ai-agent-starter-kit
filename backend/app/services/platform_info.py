"""Auto-detect platform capabilities for adaptive tool behaviour.

Provides a frozen snapshot of the current execution environment:
OS, architecture, shell, available package managers, installed runtimes.
The agent uses this to choose the right commands and skip tools that
won't work on the current platform.
"""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class PlatformInfo:
    """Immutable snapshot of the execution environment."""

    os_name: str  # "windows", "linux", "darwin"
    os_version: str
    arch: str  # "x86_64", "arm64", "aarch64"
    shell: str  # "powershell", "bash", "zsh", "sh", "cmd"
    package_managers: tuple[str, ...]  # e.g. ("pip", "npm", "cargo")
    installed_runtimes: tuple[str, ...]  # e.g. ("python", "node", "go")
    is_wsl: bool = False
    is_container: bool = False
    home_dir: str = ""

    @property
    def is_windows(self) -> bool:
        """Return True if running on Windows."""
        return self.os_name == "windows"

    @property
    def is_linux(self) -> bool:
        """Return True if running on Linux."""
        return self.os_name == "linux"

    @property
    def is_macos(self) -> bool:
        """Return True if running on macOS."""
        return self.os_name == "darwin"

    @property
    def uses_powershell(self) -> bool:
        """Return True if the default shell is PowerShell."""
        return "powershell" in self.shell.lower() or "pwsh" in self.shell.lower()

    def has_runtime(self, name: str) -> bool:
        """Check whether a runtime is available."""
        return name.lower() in self.installed_runtimes

    def has_package_manager(self, name: str) -> bool:
        """Check whether a package manager is available."""
        return name.lower() in self.package_managers

    def summary(self) -> str:
        """One-line platform summary for LLM context."""
        parts = [
            f"{self.os_name}/{self.arch}",
            f"shell={self.shell}",
        ]
        if self.is_wsl:
            parts.append("WSL")
        if self.is_container:
            parts.append("container")
        if self.installed_runtimes:
            parts.append(f"runtimes=[{','.join(self.installed_runtimes)}]")
        if self.package_managers:
            parts.append(f"pkg=[{','.join(self.package_managers)}]")
        return " | ".join(parts)


def _detect_shell() -> str:
    """Detect the default shell."""
    shell_env = os.environ.get("SHELL", "")
    comspec = os.environ.get("COMSPEC", "")

    if platform.system() == "Windows":
        # Check for PowerShell
        if shutil.which("pwsh"):
            return "pwsh"
        if "powershell" in comspec.lower() or shutil.which("powershell"):
            return "powershell"
        return "cmd"

    if shell_env:
        return os.path.basename(shell_env)

    # Fallback
    for sh in ("bash", "zsh", "sh"):
        if shutil.which(sh):
            return sh
    return "sh"


def _detect_package_managers() -> tuple[str, ...]:
    """Detect available package managers."""
    candidates = [
        "pip",
        "pip3",
        "npm",
        "yarn",
        "pnpm",
        "cargo",
        "gem",
        "apt",
        "apt-get",
        "brew",
        "choco",
        "winget",
        "scoop",
        "dnf",
        "yum",
        "pacman",
    ]
    found = [cmd for cmd in candidates if shutil.which(cmd)]
    return tuple(found)


def _detect_runtimes() -> tuple[str, ...]:
    """Detect installed programming runtimes."""
    candidates = [
        ("python3", "python"),
        ("python", "python"),
        ("node", "node"),
        ("deno", "deno"),
        ("bun", "bun"),
        ("go", "go"),
        ("rustc", "rust"),
        ("javac", "java"),
        ("dotnet", "dotnet"),
        ("ruby", "ruby"),
        ("php", "php"),
        ("gcc", "gcc"),
        ("g++", "g++"),
        ("clang", "clang"),
    ]
    found: list[str] = []
    seen: set[str] = set()
    for cmd, name in candidates:
        if name not in seen and shutil.which(cmd):
            found.append(name)
            seen.add(name)
    return tuple(found)


def _detect_wsl() -> bool:
    """Detect if running inside WSL."""
    if platform.system() != "Linux":
        return False
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def _detect_container() -> bool:
    """Detect if running inside a container."""
    # Docker
    if os.path.exists("/.dockerenv"):
        return True
    # cgroup check
    try:
        with open("/proc/1/cgroup") as f:
            content = f.read()
            if "docker" in content or "containerd" in content or "kubepods" in content:
                return True
    except OSError:
        pass
    # Kubernetes
    return bool(os.environ.get("KUBERNETES_SERVICE_HOST"))


@lru_cache(maxsize=1)
def detect_platform() -> PlatformInfo:
    """Build a PlatformInfo snapshot of the current environment.

    Cached — safe to call repeatedly without overhead.
    """
    sys_name = platform.system().lower()
    if sys_name == "darwin":
        os_name = "darwin"
    elif sys_name == "windows":
        os_name = "windows"
    else:
        os_name = "linux"

    machine = platform.machine().lower()
    # Normalize arch names
    arch_map = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}
    arch = arch_map.get(machine, machine)

    return PlatformInfo(
        os_name=os_name,
        os_version=platform.version(),
        arch=arch,
        shell=_detect_shell(),
        package_managers=_detect_package_managers(),
        installed_runtimes=_detect_runtimes(),
        is_wsl=_detect_wsl(),
        is_container=_detect_container(),
        home_dir=os.path.expanduser("~"),
    )
