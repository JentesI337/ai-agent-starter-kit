from __future__ import annotations

import asyncio

from app.services.code_sandbox import CodeSandbox


def test_sandbox_blocks_network_access_by_default(tmp_path) -> None:
    sandbox = CodeSandbox(strategy="process", workspace_root=tmp_path)

    result = asyncio.run(
        sandbox.execute(
            code="import socket\nprint('network test')",
            language="python",
        )
    )

    assert result.success is False
    assert result.error_type == "network_blocked"


def test_sandbox_blocks_filesystem_escape_pattern(tmp_path) -> None:
    sandbox = CodeSandbox(strategy="process", workspace_root=tmp_path)

    result = asyncio.run(
        sandbox.execute(
            code="with open('/etc/passwd', 'r', encoding='utf-8') as f:\n    print(f.readline())",
            language="python",
        )
    )

    assert result.success is False
    assert result.error_type == "filesystem_blocked"
