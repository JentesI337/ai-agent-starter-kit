"""Tests for output parsers — structured parsing of CLI tool output."""
from __future__ import annotations

import json

from app.services.output_parsers import (
    parse_eslint_json,
    parse_git_blame_porcelain,
    parse_git_log_full,
    parse_git_log_short,
    parse_go_panic,
    parse_jest_json,
    parse_mypy_json,
    parse_node_stacktrace,
    parse_npm_audit_json,
    parse_pip_audit_json,
    parse_pytest_output,
    parse_python_traceback,
    parse_ruff_json,
    parse_tsc_output,
    scan_text_for_secrets,
)


# ── Git parsers ──────────────────────────────────────────────────────


class TestParseGitLogShort:
    def test_parses_multiple_entries(self):
        raw = (
            "abc1234567890abcdef1234567890abcdef123456\n"
            "John Doe\n"
            "2024-01-15 10:30:00 +0100\n"
            "Add feature X\n"
            "---GIT_LOG_ENTRY---\n"
            "def5678901234567890abcdef1234567890abcdef\n"
            "Jane Smith\n"
            "2024-01-14 09:00:00 +0100\n"
            "Fix bug Y\n"
            "---GIT_LOG_ENTRY---\n"
        )
        entries = parse_git_log_short(raw)
        assert len(entries) == 2
        assert entries[0]["author"] == "John Doe"
        assert entries[0]["message"] == "Add feature X"
        assert entries[1]["message"] == "Fix bug Y"

    def test_handles_empty_input(self):
        assert parse_git_log_short("") == []
        assert parse_git_log_short("   \n  ") == []

    def test_skips_incomplete_blocks(self):
        raw = "only two lines\nhash\n---GIT_LOG_ENTRY---\n"
        entries = parse_git_log_short(raw)
        assert len(entries) == 0


class TestParseGitLogFull:
    def test_parses_with_email_and_multiline_message(self):
        raw = (
            "abc123def456\n"
            "John Doe\n"
            "john@example.com\n"
            "2024-01-15 10:30:00 +0100\n"
            "Add feature X\n"
            "With some extra detail\n"
            "---GIT_LOG_ENTRY---\n"
        )
        entries = parse_git_log_full(raw)
        assert len(entries) == 1
        assert entries[0]["email"] == "john@example.com"
        assert "extra detail" in entries[0]["message"]


class TestParseGitBlamePorcelain:
    def test_parses_porcelain_output(self):
        raw = (
            "abc123def456abc123def456abc123def456abc123 1 1\n"
            "author John Doe\n"
            "author-time 1705312200\n"
            "summary Initial commit\n"
            "\tprint('hello')\n"
            "abc123def456abc123def456abc123def456abc123 2 2\n"
            "author Jane Smith\n"
            "author-time 1705398600\n"
            "summary Add greeting\n"
            "\tprint('world')\n"
        )
        entries = parse_git_blame_porcelain(raw)
        assert len(entries) == 2
        assert entries[0]["author"] == "John Doe"
        assert entries[0]["content"] == "print('hello')"
        assert entries[1]["author"] == "Jane Smith"


# ── Test output parsers ──────────────────────────────────────────────


class TestParsePytestOutput:
    def test_parses_summary_line(self):
        raw = (
            "test_foo.py::test_one PASSED\n"
            "test_foo.py::test_two FAILED\n"
            "FAILED test_foo.py::test_two - AssertionError: expected 1\n"
            "====== 1 passed, 1 failed in 0.52s ======\n"
        )
        result = parse_pytest_output(raw)
        assert result["passed"] == 1
        assert result["failed"] == 1
        assert result["duration_seconds"] == 0.52
        assert any("test_two" in e["test"] for e in result["errors"])

    def test_handles_empty_output(self):
        result = parse_pytest_output("")
        assert result["passed"] == 0
        assert result["failed"] == 0

    def test_handles_all_passed(self):
        raw = "5 passed in 1.23s\n"
        result = parse_pytest_output(raw)
        assert result["passed"] == 5
        assert result["failed"] == 0


class TestParseJestJson:
    def test_parses_json_output(self):
        data = {
            "numPassedTests": 10,
            "numFailedTests": 2,
            "numPendingTests": 1,
            "testResults": [{
                "testResults": [
                    {"status": "failed", "fullName": "should work", "failureMessages": ["Expected true"]},
                    {"status": "passed", "fullName": "should pass", "failureMessages": []},
                ],
            }],
        }
        result = parse_jest_json(json.dumps(data))
        assert result["passed"] == 10
        assert result["failed"] == 2
        assert result["skipped"] == 1
        assert len(result["errors"]) == 1
        assert result["errors"][0]["test"] == "should work"

    def test_handles_invalid_json(self):
        result = parse_jest_json("not json")
        assert result["passed"] == 0
        assert "not json" in result["raw_summary"]


# ── Lint parsers ─────────────────────────────────────────────────────


class TestParseEslintJson:
    def test_parses_eslint_output(self):
        data = [{
            "filePath": "/src/app.js",
            "messages": [
                {"line": 10, "column": 5, "severity": 2, "message": "Unexpected var", "ruleId": "no-var"},
                {"line": 20, "column": 1, "severity": 1, "message": "Missing semicolon", "ruleId": "semi"},
            ],
        }]
        result = parse_eslint_json(json.dumps(data))
        assert len(result) == 2
        assert result[0]["severity"] == "error"
        assert result[0]["rule"] == "no-var"
        assert result[1]["severity"] == "warning"


class TestParseRuffJson:
    def test_parses_ruff_output(self):
        data = [
            {"filename": "app.py", "location": {"row": 5, "column": 1}, "message": "unused import", "code": "F401", "fix": {"edits": []}},
            {"filename": "app.py", "location": {"row": 10, "column": 1}, "message": "line too long", "code": "E501", "fix": None},
        ]
        result = parse_ruff_json(json.dumps(data))
        assert len(result) == 2
        assert result[0]["rule"] == "F401"
        assert result[1]["severity"] == "error"  # fix is None → error


class TestParseMypyJson:
    def test_parses_mypy_output(self):
        raw = (
            'app/main.py:42: error: Argument 1 has incompatible type "int" [arg-type]\n'
            "app/utils.py:10: warning: Unused variable [unused-var]\n"
            "Found 2 errors in 2 files\n"
        )
        result = parse_mypy_json(raw)
        assert len(result) == 2
        assert result[0]["file"] == "app/main.py"
        assert result[0]["line"] == 42
        assert result[0]["severity"] == "error"
        assert result[0]["rule"] == "arg-type"


class TestParseTscOutput:
    def test_parses_tsc_errors(self):
        raw = (
            "src/app.ts(15,3): error TS2345: Argument of type 'string' is not assignable.\n"
            "src/utils.ts(7,10): error TS2304: Cannot find name 'foo'.\n"
        )
        result = parse_tsc_output(raw)
        assert len(result) == 2
        assert result[0]["file"] == "src/app.ts"
        assert result[0]["line"] == 15
        assert result[0]["rule"] == "TS2345"


# ── Error parsers ────────────────────────────────────────────────────


class TestParsePythonTraceback:
    def test_parses_standard_traceback(self):
        raw = (
            "Traceback (most recent call last):\n"
            '  File "app/main.py", line 42, in run\n'
            "    result = process(data)\n"
            '  File "app/utils.py", line 10, in process\n'
            "    raise ValueError('bad data')\n"
            "ValueError: bad data\n"
        )
        result = parse_python_traceback(raw)
        assert result["error_type"] == "ValueError"
        assert result["message"] == "bad data"
        assert len(result["frames"]) == 2
        assert result["frames"][0]["file"] == "app/main.py"
        assert result["frames"][0]["line"] == 42


class TestParseNodeStacktrace:
    def test_parses_node_stack(self):
        raw = (
            "TypeError: Cannot read property 'length' of undefined\n"
            "    at processData (/app/src/handler.js:25:10)\n"
            "    at /app/src/index.js:42:5\n"
        )
        result = parse_node_stacktrace(raw)
        assert result["error_type"] == "TypeError"
        assert "length" in result["message"]
        assert len(result["frames"]) == 2
        assert result["frames"][0]["function"] == "processData"
        assert result["frames"][1]["function"] == "<anonymous>"


class TestParseGoPanic:
    def test_parses_panic(self):
        raw = (
            "goroutine 1 [running]:\n"
            "panic: runtime error: index out of range\n"
            "\n"
            "main.handler()\n"
            "\t/app/main.go:42 +0x123\n"
        )
        result = parse_go_panic(raw)
        assert result["error_type"] == "panic"
        assert "index out of range" in result["message"]
        assert len(result["frames"]) >= 1


# ── Dependency parsers ───────────────────────────────────────────────


class TestParseNpmAudit:
    def test_parses_v2_format(self):
        data = {
            "vulnerabilities": {
                "lodash": {
                    "severity": "high",
                    "title": "Prototype Pollution",
                    "fixAvailable": True,
                    "via": ["Prototype Pollution"],
                },
            },
        }
        result = parse_npm_audit_json(json.dumps(data))
        assert len(result) == 1
        assert result[0]["package"] == "lodash"
        assert result[0]["severity"] == "high"


class TestParsePipAudit:
    def test_parses_pip_audit_json(self):
        data = [{
            "name": "flask",
            "version": "1.0",
            "vulns": [{
                "id": "CVE-2023-1234",
                "description": "XSS vulnerability",
                "fix_versions": ["2.0"],
            }],
        }]
        result = parse_pip_audit_json(json.dumps(data))
        assert len(result) == 1
        assert result[0]["package"] == "flask"
        assert result[0]["id"] == "CVE-2023-1234"


# ── Secrets scanner ──────────────────────────────────────────────────


class TestScanTextForSecrets:
    def test_detects_aws_key(self):
        text = 'AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE1234"\n'
        findings = scan_text_for_secrets(text, "config.py")
        assert len(findings) >= 1
        assert findings[0]["type"] == "AWS key"

    def test_detects_private_key(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAK\n"
        findings = scan_text_for_secrets(text, "key.pem")
        assert len(findings) >= 1
        assert findings[0]["type"] == "Private key"

    def test_clean_file_no_findings(self):
        text = "def hello():\n    return 'world'\n"
        findings = scan_text_for_secrets(text, "app.py")
        assert len(findings) == 0
