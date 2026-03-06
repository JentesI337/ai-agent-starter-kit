"""Unit tests for ExecutionContract (L5.4)."""

from __future__ import annotations

from app.services.execution_contract import (
    ContractResult,
    ContractViolation,
    ExecutionContract,
    FileExistsAfter,
    NoEmptyResult,
    RequiredArg,
    ResultNotError,
    get_contract,
    register_contract,
)


class TestRequiredArg:
    def test_present(self):
        c = RequiredArg("path")
        assert c.check(args={"path": "/tmp/x"}) is None

    def test_missing(self):
        c = RequiredArg("path")
        err = c.check(args={})
        assert err is not None
        assert "missing" in err

    def test_empty_string(self):
        c = RequiredArg("path")
        err = c.check(args={"path": ""})
        assert err is not None

    def test_whitespace_only(self):
        c = RequiredArg("path")
        err = c.check(args={"path": "   "})
        assert err is not None


class TestNoEmptyResult:
    def test_ok_result(self):
        c = NoEmptyResult()
        assert c.check(args={}, result="some output") is None

    def test_empty_result(self):
        c = NoEmptyResult()
        err = c.check(args={}, result="")
        assert err is not None

    def test_none_result(self):
        c = NoEmptyResult()
        err = c.check(args={}, result=None)
        assert err is not None


class TestResultNotError:
    def test_clean_result(self):
        c = ResultNotError()
        assert c.check(args={}, result="all good") is None

    def test_error_marker(self):
        c = ResultNotError()
        err = c.check(args={}, result="Error: something went wrong")
        assert err is not None

    def test_traceback_marker(self):
        c = ResultNotError()
        err = c.check(args={}, result="Traceback (most recent call last):")
        assert err is not None

    def test_none_result_ok(self):
        c = ResultNotError()
        assert c.check(args={}, result=None) is None


class TestFileExistsAfter:
    def test_no_path_arg_passes(self):
        c = FileExistsAfter("path")
        assert c.check(args={}) is None

    def test_relative_path_skipped(self):
        c = FileExistsAfter("path")
        assert c.check(args={"path": "relative/file.txt"}) is None

    def test_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hi")
        c = FileExistsAfter("path")
        assert c.check(args={"path": str(f)}) is None

    def test_missing_file(self, tmp_path):
        c = FileExistsAfter("path")
        err = c.check(args={"path": str(tmp_path / "does_not_exist.txt")})
        assert err is not None


class TestExecutionContract:
    def test_pre_check_passes(self):
        contract = ExecutionContract(
            tool="write_file",
            pre_conditions=[RequiredArg("path")],
        )
        result = contract.check_pre(args={"path": "/tmp/x"})
        assert result.passed

    def test_pre_check_fails(self):
        contract = ExecutionContract(
            tool="write_file",
            pre_conditions=[RequiredArg("path")],
        )
        result = contract.check_pre(args={})
        assert not result.passed
        assert len(result.violations) == 1
        assert result.violations[0].phase == "pre"

    def test_post_check_passes(self):
        contract = ExecutionContract(
            tool="read_file",
            post_conditions=[NoEmptyResult()],
        )
        result = contract.check_post(args={}, result="content")
        assert result.passed

    def test_post_check_fails(self):
        contract = ExecutionContract(
            tool="read_file",
            post_conditions=[NoEmptyResult()],
        )
        result = contract.check_post(args={}, result="")
        assert not result.passed

    def test_multiple_conditions(self):
        contract = ExecutionContract(
            tool="write_file",
            pre_conditions=[RequiredArg("path"), RequiredArg("content")],
        )
        result = contract.check_pre(args={})
        assert not result.passed
        assert len(result.violations) == 2

    def test_tool_property(self):
        contract = ExecutionContract(tool="test_tool")
        assert contract.tool == "test_tool"


class TestRegistry:
    def test_get_known_contract(self):
        c = get_contract("write_file")
        assert c is not None
        assert c.tool == "write_file"

    def test_get_unknown_contract(self):
        assert get_contract("nonexistent") is None

    def test_register_custom(self):
        custom = ExecutionContract(tool="custom_tool")
        register_contract(custom)
        assert get_contract("custom_tool") is not None


class TestDataclasses:
    def test_violation_to_dict(self):
        v = ContractViolation(phase="pre", condition="required_arg:path", detail="missing")
        d = v.to_dict()
        assert d["phase"] == "pre"

    def test_result_to_dict(self):
        r = ContractResult(passed=True)
        d = r.to_dict()
        assert d["passed"] is True
        assert d["violations"] == []
