"""L5.4  ExecutionContract — pre/post-conditions for tool calls.

Defines declarative contracts that are checked before and after a tool
executes.  Pre-conditions can prevent invalid calls; post-conditions
detect semantic failures that exit-code alone cannot catch.

Usage::

    contract = ExecutionContract(
        tool="write_file",
        pre_conditions=[FileArgExists("path")],
        post_conditions=[FileExistsAfter("path")],
    )
    pre_result = contract.check_pre(args={"path": "/tmp/out.txt", "content": "hi"})
    # … execute tool …
    post_result = contract.check_post(args={"path": "/tmp/out.txt"}, result="ok")
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContractViolation:
    """One contract violation."""

    phase: str          # "pre" | "post"
    condition: str      # human-readable condition name
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "condition": self.condition,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ContractResult:
    """Outcome of a contract check (pre or post)."""

    passed: bool
    violations: list[ContractViolation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "violations": [v.to_dict() for v in self.violations],
        }


# ── Condition Protocol ────────────────────────────────────────────────


@runtime_checkable
class Condition(Protocol):
    """A single pre- or post-condition check."""

    @property
    def name(self) -> str:
        """Human-readable condition identifier."""
        ...

    def check(self, *, args: dict[str, Any], result: str | None = None) -> str | None:
        """Return ``None`` if satisfied, or an error string if violated."""
        ...


# ── Built-in conditions ──────────────────────────────────────────────


class RequiredArg:
    """Pre-condition: a required argument key must be present and non-empty."""

    def __init__(self, key: str) -> None:
        self._key = key

    @property
    def name(self) -> str:
        return f"required_arg:{self._key}"

    def check(self, *, args: dict[str, Any], result: str | None = None) -> str | None:
        value = args.get(self._key)
        if value is None or (isinstance(value, str) and not value.strip()):
            return f"Required argument '{self._key}' is missing or empty"
        return None


class NoEmptyResult:
    """Post-condition: tool result must not be empty."""

    @property
    def name(self) -> str:
        return "no_empty_result"

    def check(self, *, args: dict[str, Any], result: str | None = None) -> str | None:
        if result is None or (isinstance(result, str) and not result.strip()):
            return "Tool returned empty result"
        return None


class ResultNotError:
    """Post-condition: result must not contain common error markers."""

    _ERROR_MARKERS = ("error:", "traceback", "exception", "fatal", "ENOENT", "not found")

    @property
    def name(self) -> str:
        return "result_not_error"

    def check(self, *, args: dict[str, Any], result: str | None = None) -> str | None:
        if result is None:
            return None
        lower = result.lower()
        for marker in self._ERROR_MARKERS:
            if marker.lower() in lower:
                return f"Result contains error marker: '{marker}'"
        return None


class FileExistsAfter:
    """Post-condition: a file referenced by *arg_key* must exist after execution."""

    def __init__(self, arg_key: str = "path") -> None:
        self._arg_key = arg_key

    @property
    def name(self) -> str:
        return f"file_exists_after:{self._arg_key}"

    def check(self, *, args: dict[str, Any], result: str | None = None) -> str | None:
        path = args.get(self._arg_key, "")
        if not path or not isinstance(path, str):
            return None  # can't check without a path
        if not os.path.isabs(path):
            return None  # only check absolute paths
        if not os.path.exists(path):
            return f"Expected file '{path}' does not exist after execution"
        return None


# ── ExecutionContract ─────────────────────────────────────────────────


class ExecutionContract:
    """Declarative pre/post-condition contract for one tool.

    Usage::

        contract = ExecutionContract(
            tool="write_file",
            pre_conditions=[RequiredArg("path"), RequiredArg("content")],
            post_conditions=[NoEmptyResult()],
        )
        pre = contract.check_pre(args={"path": "/tmp/x"})
        post = contract.check_post(args={"path": "/tmp/x"}, result="ok")
    """

    def __init__(
        self,
        *,
        tool: str,
        pre_conditions: list[Condition] | None = None,
        post_conditions: list[Condition] | None = None,
    ) -> None:
        self._tool = tool
        self._pre = pre_conditions or []
        self._post = post_conditions or []

    @property
    def tool(self) -> str:
        return self._tool

    def check_pre(self, *, args: dict[str, Any]) -> ContractResult:
        """Run all pre-conditions. Returns result with any violations."""
        violations: list[ContractViolation] = []
        for cond in self._pre:
            err = cond.check(args=args, result=None)
            if err:
                violations.append(
                    ContractViolation(phase="pre", condition=cond.name, detail=err)
                )
        return ContractResult(passed=len(violations) == 0, violations=violations)

    def check_post(
        self, *, args: dict[str, Any], result: str | None = None,
    ) -> ContractResult:
        """Run all post-conditions. Returns result with any violations."""
        violations: list[ContractViolation] = []
        for cond in self._post:
            err = cond.check(args=args, result=result)
            if err:
                violations.append(
                    ContractViolation(phase="post", condition=cond.name, detail=err)
                )
        return ContractResult(passed=len(violations) == 0, violations=violations)


# ── Contract registry ────────────────────────────────────────────────


_DEFAULT_CONTRACTS: dict[str, ExecutionContract] = {
    "write_file": ExecutionContract(
        tool="write_file",
        pre_conditions=[RequiredArg("path"), RequiredArg("content")],
        post_conditions=[NoEmptyResult()],
    ),
    "read_file": ExecutionContract(
        tool="read_file",
        pre_conditions=[RequiredArg("path")],
        post_conditions=[NoEmptyResult()],
    ),
    "run_command": ExecutionContract(
        tool="run_command",
        pre_conditions=[RequiredArg("command")],
        post_conditions=[],
    ),
}


def get_contract(tool: str) -> ExecutionContract | None:
    """Look up the default contract for *tool*, or ``None``."""
    return _DEFAULT_CONTRACTS.get(tool)


def register_contract(contract: ExecutionContract) -> None:
    """Add or replace a contract in the default registry."""
    _DEFAULT_CONTRACTS[contract.tool] = contract
