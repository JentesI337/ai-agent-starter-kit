"""Tests for project tooling auto-detection."""
from __future__ import annotations

import json

from app.tools.discovery.detector import detect_linter, detect_package_manager, detect_test_runner


class TestDetectTestRunner:
    def test_detects_pytest_from_ini(self, tmp_path):
        (tmp_path / "pytest.ini").write_text("[pytest]\n")
        assert detect_test_runner(tmp_path) == "pytest"

    def test_detects_pytest_from_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
        assert detect_test_runner(tmp_path) == "pytest"

    def test_detects_jest_from_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text(json.dumps({
            "devDependencies": {"jest": "^29.0"},
            "scripts": {"test": "jest"},
        }))
        assert detect_test_runner(tmp_path) == "jest"

    def test_detects_mocha(self, tmp_path):
        (tmp_path / "package.json").write_text(json.dumps({
            "devDependencies": {"mocha": "^10.0"},
            "scripts": {"test": "mocha"},
        }))
        assert detect_test_runner(tmp_path) == "mocha"

    def test_detects_go(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/foo\n")
        assert detect_test_runner(tmp_path) == "go"

    def test_detects_cargo(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text("[package]\nname = 'foo'\n")
        assert detect_test_runner(tmp_path) == "cargo"

    def test_returns_none_for_empty_dir(self, tmp_path):
        assert detect_test_runner(tmp_path) is None


class TestDetectLinter:
    def test_detects_ruff_from_toml(self, tmp_path):
        (tmp_path / "ruff.toml").write_text("[lint]\n")
        assert detect_linter(tmp_path) == "ruff"

    def test_detects_ruff_from_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n")
        assert detect_linter(tmp_path) == "ruff"

    def test_detects_eslint(self, tmp_path):
        (tmp_path / ".eslintrc.json").write_text("{}\n")
        assert detect_linter(tmp_path) == "eslint"

    def test_detects_mypy(self, tmp_path):
        (tmp_path / "mypy.ini").write_text("[mypy]\n")
        assert detect_linter(tmp_path) == "mypy"

    def test_detects_tsc(self, tmp_path):
        (tmp_path / "tsconfig.json").write_text("{}\n")
        assert detect_linter(tmp_path) == "tsc"

    def test_fallback_to_ruff_for_python_project(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask\n")
        assert detect_linter(tmp_path) == "ruff"

    def test_returns_none_for_empty_dir(self, tmp_path):
        assert detect_linter(tmp_path) is None


class TestDetectPackageManager:
    def test_detects_npm(self, tmp_path):
        (tmp_path / "package-lock.json").write_text("{}\n")
        assert detect_package_manager(tmp_path) == "npm"

    def test_detects_yarn(self, tmp_path):
        (tmp_path / "yarn.lock").write_text("")
        assert detect_package_manager(tmp_path) == "yarn"

    def test_detects_pip(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask\n")
        assert detect_package_manager(tmp_path) == "pip"

    def test_detects_pipenv(self, tmp_path):
        (tmp_path / "Pipfile").write_text("[packages]\n")
        assert detect_package_manager(tmp_path) == "pipenv"

    def test_returns_none_for_empty_dir(self, tmp_path):
        assert detect_package_manager(tmp_path) is None
