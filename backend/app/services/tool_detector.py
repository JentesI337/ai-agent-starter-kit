"""Auto-detection of project tooling (test runner, linter, package manager).

Pure functions that inspect the workspace filesystem to determine which
CLI tools are available for the project.
"""
from __future__ import annotations

import json
from pathlib import Path


def detect_test_runner(workspace: Path) -> str | None:
    """Detect the test runner for the project. Returns runner name or None."""
    # Python: pytest
    if (workspace / "pytest.ini").exists():
        return "pytest"
    if (workspace / "setup.cfg").exists():
        try:
            content = (workspace / "setup.cfg").read_text(encoding="utf-8", errors="replace")
            if "[tool:pytest]" in content:
                return "pytest"
        except OSError:
            pass
    pyproject = workspace / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding="utf-8", errors="replace")
            if "[tool.pytest" in content:
                return "pytest"
            # If pyproject.toml exists with any Python content, default to pytest
            if "[project]" in content or "[build-system]" in content:
                return "pytest"
        except OSError:
            pass

    # Node: jest or mocha
    pkg_json = workspace / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            scripts = data.get("scripts", {})
            if "jest" in deps or "jest" in scripts.get("test", ""):
                return "jest"
            if "mocha" in deps or "mocha" in scripts.get("test", ""):
                return "mocha"
            # Default to jest if it's a node project with a test script
            if "test" in scripts:
                return "jest"
        except (OSError, json.JSONDecodeError):
            pass

    # Go
    if (workspace / "go.mod").exists():
        return "go"

    # Rust
    if (workspace / "Cargo.toml").exists():
        return "cargo"

    return None


def detect_linter(workspace: Path) -> str | None:
    """Detect the linter/type-checker for the project. Returns tool name or None."""
    # Python linters
    pyproject = workspace / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding="utf-8", errors="replace")
            if "[tool.ruff" in content:
                return "ruff"
            if "[tool.flake8" in content:
                return "flake8"
            if "[tool.mypy" in content:
                return "mypy"
        except OSError:
            pass
    if (workspace / "ruff.toml").exists() or (workspace / ".ruff.toml").exists():
        return "ruff"
    if (workspace / "mypy.ini").exists() or (workspace / ".mypy.ini").exists():
        return "mypy"

    # Node/TS linters
    for name in (".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml", "eslint.config.js", "eslint.config.mjs"):
        if (workspace / name).exists():
            return "eslint"
    if (workspace / "tsconfig.json").exists():
        return "tsc"

    # Fallback: if it's a Python project, try ruff
    if pyproject.exists() or (workspace / "requirements.txt").exists():
        return "ruff"

    return None


def detect_package_manager(workspace: Path) -> str | None:
    """Detect the package manager for the project. Returns manager name or None."""
    # Node
    if (workspace / "package-lock.json").exists() or (workspace / "package.json").exists():
        return "npm"
    if (workspace / "yarn.lock").exists():
        return "yarn"
    if (workspace / "pnpm-lock.yaml").exists():
        return "pnpm"

    # Python
    if (workspace / "Pipfile").exists() or (workspace / "Pipfile.lock").exists():
        return "pipenv"
    if (workspace / "requirements.txt").exists() or (workspace / "pyproject.toml").exists():
        return "pip"

    return None
