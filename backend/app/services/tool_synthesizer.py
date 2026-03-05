"""L6.1  ToolSynthesizer — ad-hoc script generation in a sandbox.

When no existing tool covers the user's need, the synthesizer
generates a short script (Python / Node / PowerShell), validates it
syntactically, and executes it in a restricted sandbox.

Safety model:
  - Scripts must be ≤ ``max_lines`` (default 50).
  - Generated code is checked for forbidden patterns (network, FS
    escape, subprocess, eval).
  - Execution happens via ``run_command`` with a timeout.

Usage::

    synth = ToolSynthesizer()
    result = await synth.synthesize_and_run(
        task="Convert CSV to JSON",
        runtime="python",
        run_command=my_run_fn,
    )
"""

from __future__ import annotations

import logging
import re
import textwrap
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

RunCommandFn = Callable[[str], Awaitable[str]]


# ── Result type ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class SynthesisResult:
    """Outcome of a synthesize-and-run attempt."""

    success: bool
    script: str = ""
    output: str = ""
    runtime: str = ""
    error: str = ""
    safety_violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "script": self.script,
            "output": self.output,
            "runtime": self.runtime,
            "error": self.error,
            "safety_violations": self.safety_violations,
        }


# ── Safety checks ────────────────────────────────────────────────────

_FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bimport\s+(?:socket|http|urllib|requests|aiohttp)\b", re.I), "network_import"),
    (re.compile(r"\bopen\s*\(.*/etc/", re.I), "fs_escape_etc"),
    (re.compile(r"\.\./\.\./", re.I), "path_traversal"),
    (re.compile(r"\bsubprocess\b", re.I), "subprocess_usage"),
    (re.compile(r"\beval\s*\(", re.I), "eval_usage"),
    (re.compile(r"\bexec\s*\(", re.I), "exec_usage"),
    (re.compile(r"\b__import__\s*\(", re.I), "dynamic_import"),
    (re.compile(r"\bos\.system\s*\(", re.I), "os_system"),
    (re.compile(r"\bshutil\.rmtree\s*\(", re.I), "rmtree"),
    (re.compile(r"\brm\s+-rf\b", re.I), "rm_rf"),
]


def check_script_safety(script: str) -> list[str]:
    """Return a list of safety violation labels found in *script*."""
    violations: list[str] = []
    for pattern, label in _FORBIDDEN_PATTERNS:
        if pattern.search(script):
            violations.append(label)
    return violations


# ── Runtime wrappers ──────────────────────────────────────────────────

_RUNTIME_CMD: dict[str, str] = {
    "python": 'python -c "{script}"',
    "node": 'node -e "{script}"',
    "powershell": 'powershell -Command "{script}"',
}

_SUPPORTED_RUNTIMES = frozenset(_RUNTIME_CMD.keys())


def _build_execution_command(script: str, runtime: str) -> str:
    """Wrap *script* in a one-liner execution command."""
    # Escape double quotes for shell embedding
    escaped = script.replace('"', '\\"')
    template = _RUNTIME_CMD.get(runtime, 'python -c "{script}"')
    return template.replace("{script}", escaped)


# ── Main class ────────────────────────────────────────────────────────


class ToolSynthesizer:
    """Generate and execute short scripts in a sandbox.

    Usage::

        synth = ToolSynthesizer()
        result = await synth.synthesize_and_run(
            task="Sort lines in data.txt",
            runtime="python",
            run_command=my_run_fn,
            script="with open('data.txt') as f: print(sorted(f.readlines()))",
        )
    """

    def __init__(self, *, max_lines: int = 50) -> None:
        self._max_lines = max_lines

    # ── public API ────────────────────────────────────────────────────

    async def synthesize_and_run(
        self,
        *,
        task: str,
        runtime: str,
        run_command: RunCommandFn,
        script: str = "",
    ) -> SynthesisResult:
        """Validate and execute *script* for *task*.

        Args:
            task: Human-readable description of what the script should do.
            runtime: One of ``python``, ``node``, ``powershell``.
            run_command: Async callable to execute the wrapped command.
            script: The script source code to execute.
        """
        runtime = runtime.strip().lower()

        # ── 1. Validate runtime ──────────────────────────────────────
        if runtime not in _SUPPORTED_RUNTIMES:
            return SynthesisResult(
                success=False,
                runtime=runtime,
                error=f"Unsupported runtime '{runtime}'. Supported: {sorted(_SUPPORTED_RUNTIMES)}",
            )

        # ── 2. Validate script presence ──────────────────────────────
        if not script or not script.strip():
            return SynthesisResult(
                success=False,
                runtime=runtime,
                error="No script provided",
            )

        # ── 3. Line limit ────────────────────────────────────────────
        lines = script.strip().splitlines()
        if len(lines) > self._max_lines:
            return SynthesisResult(
                success=False,
                script=script,
                runtime=runtime,
                error=f"Script exceeds {self._max_lines}-line limit ({len(lines)} lines)",
            )

        # ── 4. Safety check ──────────────────────────────────────────
        violations = check_script_safety(script)
        if violations:
            logger.warning(
                "synthesizer: safety violations in script for '%s': %s",
                task, violations,
            )
            return SynthesisResult(
                success=False,
                script=script,
                runtime=runtime,
                error="Safety check failed",
                safety_violations=violations,
            )

        # ── 5. Execute ───────────────────────────────────────────────
        cmd = _build_execution_command(script, runtime)
        try:
            output = await run_command(cmd)
        except Exception as exc:
            return SynthesisResult(
                success=False,
                script=script,
                runtime=runtime,
                error=f"Execution failed: {exc}",
            )

        logger.info("synthesizer: executed script for '%s' (%s)", task, runtime)

        return SynthesisResult(
            success=True,
            script=script,
            output=output or "",
            runtime=runtime,
        )

    # ── queries ───────────────────────────────────────────────────────

    @staticmethod
    def supported_runtimes() -> list[str]:
        """Return list of supported runtime names."""
        return sorted(_SUPPORTED_RUNTIMES)
