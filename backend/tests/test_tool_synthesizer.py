"""Unit tests for L6.1 ToolSynthesizer."""

from __future__ import annotations

import asyncio

import pytest

from app.services.tool_synthesizer import (
    SynthesisResult,
    ToolSynthesizer,
    check_script_safety,
    _build_execution_command,
)


# ── check_script_safety ──────────────────────────────────────────────


class TestCheckScriptSafety:
    def test_clean_script_passes(self):
        assert check_script_safety("print('hello')") == []

    def test_network_import_detected(self):
        v = check_script_safety("import socket")
        assert "network_import" in v

    def test_requests_import_detected(self):
        v = check_script_safety("import requests")
        assert "network_import" in v

    def test_subprocess_detected(self):
        v = check_script_safety("import subprocess; subprocess.run()")
        assert "subprocess_usage" in v

    def test_eval_detected(self):
        v = check_script_safety("eval('1+1')")
        assert "eval_usage" in v

    def test_exec_detected(self):
        v = check_script_safety("exec('x=1')")
        assert "exec_usage" in v

    def test_dynamic_import_detected(self):
        v = check_script_safety("__import__('os')")
        assert "dynamic_import" in v

    def test_os_system_detected(self):
        v = check_script_safety("os.system('ls')")
        assert "os_system" in v

    def test_rmtree_detected(self):
        v = check_script_safety("shutil.rmtree('/tmp')")
        assert "rmtree" in v

    def test_rm_rf_detected(self):
        v = check_script_safety("rm -rf /")
        assert "rm_rf" in v

    def test_path_traversal_detected(self):
        v = check_script_safety("open('../../etc/passwd')")
        assert "path_traversal" in v

    def test_fs_escape_etc(self):
        v = check_script_safety("open('/etc/shadow')")
        assert "fs_escape_etc" in v

    def test_multiple_violations(self):
        v = check_script_safety("import subprocess; eval('1'); exec('2')")
        assert "subprocess_usage" in v
        assert "eval_usage" in v
        assert "exec_usage" in v


# ── _build_execution_command ─────────────────────────────────────────


class TestBuildExecutionCommand:
    def test_python_runtime(self):
        cmd = _build_execution_command("print(1)", "python")
        assert "python -c" in cmd
        assert "print(1)" in cmd

    def test_node_runtime(self):
        cmd = _build_execution_command("console.log(1)", "node")
        assert "node -e" in cmd

    def test_powershell_runtime(self):
        cmd = _build_execution_command("Write-Host 1", "powershell")
        assert "powershell -Command" in cmd

    def test_quotes_escaped(self):
        cmd = _build_execution_command('print("hi")', "python")
        assert '\\"' in cmd


# ── SynthesisResult ──────────────────────────────────────────────────


class TestSynthesisResult:
    def test_to_dict(self):
        r = SynthesisResult(success=True, script="x=1", output="ok", runtime="python")
        d = r.to_dict()
        assert d["success"] is True
        assert d["script"] == "x=1"
        assert d["output"] == "ok"
        assert d["runtime"] == "python"
        assert d["error"] == ""
        assert d["safety_violations"] == []

    def test_frozen(self):
        r = SynthesisResult(success=True)
        with pytest.raises(AttributeError):
            r.success = False  # type: ignore[misc]


# ── ToolSynthesizer.synthesize_and_run ───────────────────────────────


class TestSynthesizeAndRun:
    def _make_runner(self, output: str = "ok"):
        async def fake_run(cmd: str) -> str:
            return output
        return fake_run

    def test_success_python(self):
        synth = ToolSynthesizer()
        result = asyncio.run(synth.synthesize_and_run(
            task="Say hello",
            runtime="python",
            script="print('hello')",
            run_command=self._make_runner("hello"),
        ))
        assert result.success
        assert result.output == "hello"
        assert result.runtime == "python"

    def test_unsupported_runtime(self):
        synth = ToolSynthesizer()
        result = asyncio.run(synth.synthesize_and_run(
            task="x", runtime="ruby", script="puts 1",
            run_command=self._make_runner(),
        ))
        assert not result.success
        assert "Unsupported runtime" in result.error

    def test_empty_script(self):
        synth = ToolSynthesizer()
        result = asyncio.run(synth.synthesize_and_run(
            task="x", runtime="python", script="",
            run_command=self._make_runner(),
        ))
        assert not result.success
        assert "No script" in result.error

    def test_whitespace_only_script(self):
        synth = ToolSynthesizer()
        result = asyncio.run(synth.synthesize_and_run(
            task="x", runtime="python", script="   \n  ",
            run_command=self._make_runner(),
        ))
        assert not result.success

    def test_line_limit_exceeded(self):
        synth = ToolSynthesizer(max_lines=3)
        script = "\n".join(f"x{i}=1" for i in range(5))
        result = asyncio.run(synth.synthesize_and_run(
            task="x", runtime="python", script=script,
            run_command=self._make_runner(),
        ))
        assert not result.success
        assert "line limit" in result.error.lower()

    def test_safety_violation_blocks(self):
        synth = ToolSynthesizer()
        result = asyncio.run(synth.synthesize_and_run(
            task="hack", runtime="python",
            script="import subprocess; subprocess.run(['rm', '-rf', '/'])",
            run_command=self._make_runner(),
        ))
        assert not result.success
        assert "subprocess_usage" in result.safety_violations

    def test_execution_error_caught(self):
        async def failing_run(cmd: str) -> str:
            raise RuntimeError("timeout")

        synth = ToolSynthesizer()
        result = asyncio.run(synth.synthesize_and_run(
            task="x", runtime="python", script="print(1)",
            run_command=failing_run,
        ))
        assert not result.success
        assert "timeout" in result.error

    def test_runtime_case_insensitive(self):
        synth = ToolSynthesizer()
        result = asyncio.run(synth.synthesize_and_run(
            task="x", runtime="  Python  ", script="print(1)",
            run_command=self._make_runner(),
        ))
        assert result.success
        assert result.runtime == "python"

    def test_supported_runtimes(self):
        runtimes = ToolSynthesizer.supported_runtimes()
        assert "python" in runtimes
        assert "node" in runtimes
        assert "powershell" in runtimes
