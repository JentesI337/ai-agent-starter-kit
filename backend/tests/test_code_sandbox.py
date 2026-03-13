from __future__ import annotations

import asyncio
import shutil

from app.sandbox.code_sandbox import CodeSandbox


def test_code_sandbox_python_success(tmp_path) -> None:
    sandbox = CodeSandbox(strategy="process", workspace_root=tmp_path)

    result = asyncio.run(sandbox.execute(code="print('hello sandbox')", language="python", timeout=5))

    assert result.success is True
    assert result.exit_code == 0
    assert "hello sandbox" in result.stdout
    assert result.stderr == ""
    assert result.timed_out is False


def test_code_sandbox_javascript_success_when_node_present(tmp_path) -> None:
    if shutil.which("node") is None:
        return

    sandbox = CodeSandbox(strategy="process", workspace_root=tmp_path)
    result = asyncio.run(sandbox.execute(code="console.log('hello js')", language="javascript", timeout=5))

    assert result.success is True
    assert result.exit_code == 0
    assert "hello js" in result.stdout


def test_code_sandbox_timeout_marks_result(tmp_path) -> None:
    sandbox = CodeSandbox(strategy="process", workspace_root=tmp_path)
    code = "import time\ntime.sleep(2)\nprint('done')"

    result = asyncio.run(sandbox.execute(code=code, language="python", timeout=1))

    assert result.success is False
    assert result.timed_out is True
    assert result.error_type == "timeout"


def test_code_sandbox_truncates_output(tmp_path) -> None:
    sandbox = CodeSandbox(strategy="process", workspace_root=tmp_path)
    code = "print('x' * 5000)"

    result = asyncio.run(sandbox.execute(code=code, language="python", max_output_chars=600))

    assert result.truncated is True
    assert len(result.stdout) + len(result.stderr) <= 600


def test_code_sandbox_rejects_unsupported_language(tmp_path) -> None:
    sandbox = CodeSandbox(strategy="process", workspace_root=tmp_path)

    result = asyncio.run(sandbox.execute(code="puts 'hi'", language="ruby"))

    assert result.success is False
    assert result.error_type == "unsupported_language"


def test_code_sandbox_blocks_network_usage_by_default(tmp_path) -> None:
    sandbox = CodeSandbox(strategy="process", workspace_root=tmp_path)
    code = "import socket\nprint('x')"

    result = asyncio.run(sandbox.execute(code=code, language="python"))

    assert result.success is False
    assert result.error_type == "network_blocked"
