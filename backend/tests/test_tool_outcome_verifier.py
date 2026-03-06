"""Tests for ToolOutcomeVerifier."""

import pytest

from app.services.tool_outcome_verifier import OutcomeVerdict, ToolOutcomeVerifier


@pytest.fixture
def verifier():
    return ToolOutcomeVerifier()


class TestRunCommand:
    def test_success_exit_zero(self, verifier):
        v = verifier.verify(tool="run_command", result="output text", args={"command": "ls"})
        assert v.status == "verified"

    def test_failure_exit_nonzero(self, verifier):
        v = verifier.verify(tool="run_command", result="exit code: 1\nerror output", args={"command": "false"})
        assert v.status == "failed"

    def test_stderr_warning_suspicious(self, verifier):
        v = verifier.verify(tool="run_command", result="stderr: WARNING something", args={"command": "gcc"})
        # No error keywords in stderr → verified
        assert v.status == "verified"

    def test_traceback_in_output(self, verifier):
        output = "Traceback (most recent call last):\n  File x\nNameError: name 'y'"
        v = verifier.verify(tool="run_command", result=output, args={"command": "python script.py"})
        assert v.status == "suspicious"
        assert v.error_category is not None

    def test_exit_code_none_verified(self, verifier):
        v = verifier.verify(tool="run_command", result="done", args={"command": "echo ok"})
        assert v.status == "verified"


class TestWriteFile:
    def test_success(self, verifier):
        v = verifier.verify(tool="write_file", result="File written successfully", args={"path": "test.txt"})
        assert v.status == "verified"

    def test_file_not_found(self, verifier):
        v = verifier.verify(tool="write_file", result="Error: file not found /path/to/dir", args={"path": "x.txt"})
        assert v.status == "failed"

    def test_no_match(self, verifier):
        v = verifier.verify(tool="apply_patch", result="No match found for the given patch", args={"path": "x.py"})
        assert v.status == "failed"


class TestWebFetch:
    def test_success(self, verifier):
        v = verifier.verify(tool="web_fetch", result="A" * 200, args={"url": "https://example.com"})
        assert v.status == "verified"

    def test_http_error(self, verifier):
        v = verifier.verify(tool="web_fetch", result="HTTP error 404: Not Found", args={"url": "https://example.com/missing"})
        assert v.status in ("failed", "suspicious")

    def test_short_response_suspicious(self, verifier):
        v = verifier.verify(tool="web_fetch", result="OK", args={"url": "https://example.com"})
        assert v.status == "suspicious"


class TestCodeExecute:
    def test_success(self, verifier):
        v = verifier.verify(tool="code_execute", result="42\n", args={"code": "print(6*7)"})
        assert v.status == "verified"

    def test_traceback(self, verifier):
        output = "Traceback (most recent call last):\n  File '<string>'\nZeroDivisionError: division by zero"
        v = verifier.verify(tool="code_execute", result=output, args={"code": "1/0"})
        assert v.status == "failed"


class TestUnknownTool:
    def test_unknown_tool_verified(self, verifier):
        v = verifier.verify(tool="some_random_tool", result="result", args={"arg": "val"})
        assert v.status == "verified"

    def test_unknown_tool_empty_suspicious(self, verifier):
        v = verifier.verify(tool="some_random_tool", result="", args={"arg": "val"})
        assert v.status == "suspicious"


class TestOutcomeVerdict:
    def test_fields(self):
        v = OutcomeVerdict(status="verified", reason="OK", error_category=None)
        assert v.status == "verified"
        assert v.reason == "OK"
        assert v.error_category is None
