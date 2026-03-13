"""Tests for DevOps tool mixin — git, testing, linting, dependency, debug, security tools."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.errors import ToolExecutionError
from app.tools.implementations.devops import DevOpsToolMixin

# ── Helpers ──────────────────────────────────────────────────────────


class FakeTooling(DevOpsToolMixin):
    """Minimal AgentTooling stand-in for testing the mixin."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).resolve()
        self.command_timeout_seconds = 30


def _make_tooling(tmp_path: Path) -> FakeTooling:
    return FakeTooling(tmp_path)


def _mock_run(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Create a mock subprocess.run result."""
    result = MagicMock()
    result.stdout = stdout
    result.stderr = stderr
    result.returncode = returncode
    return result


# ── Git tools ────────────────────────────────────────────────────────


class TestGitLog:
    def test_returns_structured_json(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        raw = (
            "abc123\nJohn Doe\n2024-01-15 10:00:00\nAdd feature\n"
            "---GIT_LOG_ENTRY---\n"
        )
        with patch("app.tools.implementations.devops.subprocess.run", return_value=_mock_run(raw)):
            result = tooling.git_log()
        entries = json.loads(result)
        assert len(entries) == 1
        assert entries[0]["author"] == "John Doe"

    def test_oneline_format(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        raw = "abc123 Add feature\ndef456 Fix bug\n"
        with patch("app.tools.implementations.devops.subprocess.run", return_value=_mock_run(raw)):
            result = tooling.git_log(format="oneline")
        assert "abc123" in result

    def test_empty_result(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        with patch("app.tools.implementations.devops.subprocess.run", return_value=_mock_run("")):
            result = tooling.git_log()
        assert "No commits" in result

    def test_max_count_capped(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        with patch("app.tools.implementations.devops.subprocess.run", return_value=_mock_run("")) as mock:
            tooling.git_log(max_count=200)
            args = mock.call_args[0][0]
            assert "--max-count=100" in args


class TestGitDiff:
    def test_returns_diff_output(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        diff = "diff --git a/file.py b/file.py\n+new line\n"
        with patch("app.tools.implementations.devops.subprocess.run", return_value=_mock_run(diff)):
            result = tooling.git_diff()
        assert "+new line" in result

    def test_no_differences(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        with patch("app.tools.implementations.devops.subprocess.run", return_value=_mock_run("")):
            result = tooling.git_diff()
        assert "No differences" in result

    def test_stat_only(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        with patch("app.tools.implementations.devops.subprocess.run", return_value=_mock_run("file.py | 2 +-\n")) as mock:
            tooling.git_diff(stat_only=True)
            args = mock.call_args[0][0]
            assert "--stat" in args


class TestGitBlame:
    def test_returns_structured_blame(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        raw = (
            "abc123def456abc123def456abc123def456abc123 1 1\n"
            "author John Doe\n"
            "\tcode here\n"
        )
        with patch("app.tools.implementations.devops.subprocess.run", return_value=_mock_run(raw)):
            result = tooling.git_blame(path="file.py")
        entries = json.loads(result)
        assert len(entries) == 1

    def test_requires_path(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        with pytest.raises(ToolExecutionError):
            tooling.git_blame(path="")


class TestGitShow:
    def test_returns_commit_details(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        raw = "commit abc123\nAuthor: John\n\nAdd feature\n\ndiff...\n"
        with patch("app.tools.implementations.devops.subprocess.run", return_value=_mock_run(raw)):
            result = tooling.git_show(ref="abc123")
        assert "Add feature" in result

    def test_requires_ref(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        with pytest.raises(ToolExecutionError):
            tooling.git_show(ref="")


class TestGitStash:
    def test_save(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        with patch("app.tools.implementations.devops.subprocess.run", return_value=_mock_run("Saved working directory\n")):
            result = tooling.git_stash(action="save", message="wip")
        assert "Saved" in result

    def test_invalid_action(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        with pytest.raises(ToolExecutionError, match="must be one of"):
            tooling.git_stash(action="invalid")


# ── Testing tools ────────────────────────────────────────────────────


class TestRunTests:
    def test_auto_detect_pytest(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\n")
        tooling = _make_tooling(tmp_path)
        stdout = "2 passed in 0.50s\n"
        with patch("app.tools.implementations.devops.subprocess.run", return_value=_mock_run(stdout)):
            result = tooling.run_tests()
        parsed = json.loads(result)
        assert parsed["passed"] == 2

    def test_no_runner_detected(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        result = tooling.run_tests()
        assert "Could not auto-detect" in result

    def test_explicit_runner(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        stdout = "3 passed, 1 failed in 1.23s\nFAILED test_a.py::test_x - assert False\n"
        with patch("app.tools.implementations.devops.subprocess.run", return_value=_mock_run(stdout, returncode=1)):
            result = tooling.run_tests(runner="pytest")
        parsed = json.loads(result)
        assert parsed["failed"] == 1
        assert parsed["exit_code"] == 1


# ── Lint tools ───────────────────────────────────────────────────────


class TestLintCheck:
    def test_auto_detect_ruff(self, tmp_path):
        (tmp_path / "ruff.toml").write_text("[lint]\n")
        tooling = _make_tooling(tmp_path)
        stdout = json.dumps([
            {"filename": "app.py", "location": {"row": 5, "column": 1}, "message": "unused", "code": "F401", "fix": None},
        ])
        with patch("app.tools.implementations.devops.subprocess.run", return_value=_mock_run(stdout, returncode=1)):
            result = tooling.lint_check()
        parsed = json.loads(result)
        assert parsed["tool"] == "ruff"
        assert parsed["total_issues"] == 1

    def test_no_linter_detected(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        result = tooling.lint_check()
        assert "Could not auto-detect" in result


# ── Error parsing ────────────────────────────────────────────────────


class TestParseErrors:
    def test_python_traceback(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        error = (
            "Traceback (most recent call last):\n"
            '  File "app.py", line 10, in main\n'
            "    raise ValueError('bad')\n"
            "ValueError: bad\n"
        )
        result = tooling.parse_errors(error_text=error)
        parsed = json.loads(result)
        assert parsed["error_type"] == "ValueError"
        assert len(parsed["frames"]) == 1

    def test_node_stacktrace(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        error = (
            "TypeError: undefined is not a function\n"
            "    at handler (/app/src/index.js:10:5)\n"
        )
        result = tooling.parse_errors(error_text=error, language="javascript")
        parsed = json.loads(result)
        assert parsed["error_type"] == "TypeError"

    def test_empty_error_raises(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        with pytest.raises(ToolExecutionError):
            tooling.parse_errors(error_text="")

    def test_auto_detect_language(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        # Python-style error
        error = 'Traceback (most recent call last):\n  File "x.py", line 1\nValueError: x\n'
        result = tooling.parse_errors(error_text=error)
        parsed = json.loads(result)
        assert parsed["error_type"] == "ValueError"


# ── Dependency tools ─────────────────────────────────────────────────


class TestDependencyAudit:
    def test_npm_audit(self, tmp_path):
        (tmp_path / "package-lock.json").write_text("{}\n")
        tooling = _make_tooling(tmp_path)
        audit_json = json.dumps({
            "vulnerabilities": {
                "lodash": {"severity": "high", "title": "Prototype Pollution", "fixAvailable": True, "via": []},
            },
        })
        with patch("app.tools.implementations.devops.subprocess.run", return_value=_mock_run(audit_json, returncode=1)):
            result = tooling.dependency_audit()
        parsed = json.loads(result)
        assert parsed["manager"] == "npm"
        assert parsed["total_vulnerabilities"] == 1

    def test_no_manager_detected(self, tmp_path):
        tooling = _make_tooling(tmp_path)
        result = tooling.dependency_audit()
        assert "Could not detect" in result


class TestDependencyOutdated:
    def test_npm_outdated(self, tmp_path):
        (tmp_path / "package.json").write_text("{}\n")
        tooling = _make_tooling(tmp_path)
        stdout = json.dumps({
            "lodash": {"current": "4.17.19", "wanted": "4.17.21", "latest": "4.17.21"},
        })
        with patch("app.tools.implementations.devops.subprocess.run", return_value=_mock_run(stdout, returncode=1)):
            result = tooling.dependency_outdated()
        parsed = json.loads(result)
        assert len(parsed["outdated"]) == 1
        assert parsed["outdated"][0]["package"] == "lodash"


# ── Security tools ───────────────────────────────────────────────────


class TestSecretsScan:
    def test_builtin_scanner(self, tmp_path):
        (tmp_path / "config.py").write_text('AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE1234"\n')
        tooling = _make_tooling(tmp_path)
        result = tooling.secrets_scan(tool="builtin")
        parsed = json.loads(result)
        assert parsed["tool"] == "builtin_regex"
        assert parsed["total_findings"] >= 1

    def test_clean_codebase(self, tmp_path):
        (tmp_path / "app.py").write_text("def hello():\n    return 'world'\n")
        tooling = _make_tooling(tmp_path)
        result = tooling.secrets_scan(tool="builtin")
        parsed = json.loads(result)
        assert parsed["total_findings"] == 0


# ── Tool arg validators ──────────────────────────────────────────────


class TestDevOpsArgValidators:
    def _make_validator(self):
        from app.tools.execution.arg_validator import ToolArgValidator
        return ToolArgValidator(violates_command_policy=lambda _: False)

    def test_all_devops_tools_have_validators(self):
        validator = self._make_validator()
        devops_tools = [
            "git_log", "git_diff", "git_blame", "git_show", "git_stash",
            "run_tests", "lint_check", "test_coverage",
            "dependency_audit", "dependency_outdated", "dependency_tree",
            "parse_errors", "secrets_scan", "security_check",
        ]
        for tool in devops_tools:
            assert validator.has_validator(tool), f"Missing validator for {tool}"

    def test_git_log_validates_max_count(self):
        validator = self._make_validator()
        args = {"max_count": 200}
        err = validator.validate("git_log", args)
        assert err is not None  # out of range

    def test_git_blame_requires_path(self):
        validator = self._make_validator()
        args = {}
        err = validator.validate("git_blame", args)
        assert err is not None

    def test_run_tests_validates_runner_enum(self):
        validator = self._make_validator()
        args = {"runner": "invalid_runner"}
        err = validator.validate("run_tests", args)
        assert err is not None

    def test_parse_errors_requires_error_text(self):
        validator = self._make_validator()
        args = {}
        err = validator.validate("parse_errors", args)
        assert err is not None

    def test_valid_args_pass(self):
        validator = self._make_validator()
        # git_log with valid args
        args = {"max_count": 10, "format": "short"}
        assert validator.validate("git_log", args) is None
        # run_tests with valid args
        args = {"runner": "pytest", "verbose": True}
        assert validator.validate("run_tests", args) is None


# ── Tool registry integration ────────────────────────────────────────


class TestDevOpsToolRegistration:
    def test_all_devops_tools_registered(self):
        from app.tools.registry.registry import build_default_tool_registry
        registry = build_default_tool_registry(command_timeout_seconds=60)
        devops_tools = [
            "git_log", "git_diff", "git_blame", "git_show", "git_stash",
            "run_tests", "lint_check", "test_coverage",
            "dependency_audit", "dependency_outdated", "dependency_tree",
            "parse_errors", "secrets_scan", "security_check",
        ]
        for tool in devops_tools:
            assert registry.get(tool) is not None, f"Tool {tool} not in registry"

    def test_git_tools_have_correct_capabilities(self):
        from app.tools.registry.registry import build_default_tool_registry
        registry = build_default_tool_registry(command_timeout_seconds=60)
        git_log_spec = registry.get("git_log")
        assert git_log_spec is not None
        assert "git_inspection" in git_log_spec.capabilities
