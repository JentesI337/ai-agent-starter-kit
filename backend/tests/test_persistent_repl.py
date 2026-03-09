"""Tests for the persistent REPL and session manager."""

from __future__ import annotations

import asyncio
import json
import pytest

from app.services.persistent_repl import PersistentRepl, ReplResult
from app.services.repl_session_manager import ReplSessionManager


# ---------------------------------------------------------------------------
# PersistentRepl — basic lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repl_start_and_shutdown(tmp_path):
    repl = PersistentRepl("test-session", sandbox_base=str(tmp_path))
    await repl.start()
    assert repl.is_alive
    await repl.shutdown()
    assert not repl.is_alive


@pytest.mark.asyncio
async def test_repl_state_persistence(tmp_path):
    """Variables survive across execute() calls."""
    repl = PersistentRepl("test-session", sandbox_base=str(tmp_path))
    await repl.start()
    try:
        r1 = await repl.execute("x = 42")
        assert r1.exit_code == 0
        assert r1.stdout.strip() == ""

        r2 = await repl.execute("print(x)")
        assert r2.exit_code == 0
        assert "42" in r2.stdout
    finally:
        await repl.shutdown()


@pytest.mark.asyncio
async def test_repl_import_persistence(tmp_path):
    """Imports survive across calls."""
    repl = PersistentRepl("test-session", sandbox_base=str(tmp_path))
    await repl.start()
    try:
        await repl.execute("import math")
        r = await repl.execute("print(math.pi)")
        assert "3.14159" in r.stdout
    finally:
        await repl.shutdown()


@pytest.mark.asyncio
async def test_repl_function_persistence(tmp_path):
    """Function definitions survive across calls."""
    repl = PersistentRepl("test-session", sandbox_base=str(tmp_path))
    await repl.start()
    try:
        await repl.execute("def add(a, b): return a + b")
        r = await repl.execute("print(add(3, 4))")
        assert "7" in r.stdout
    finally:
        await repl.shutdown()


@pytest.mark.asyncio
async def test_repl_multiline_state(tmp_path):
    """Multiple state-building calls in sequence."""
    repl = PersistentRepl("test-session", sandbox_base=str(tmp_path))
    await repl.start()
    try:
        await repl.execute("items = []")
        await repl.execute("items.append('a')")
        await repl.execute("items.append('b')")
        await repl.execute("items.append('c')")
        r = await repl.execute("print(len(items), items)")
        assert "3" in r.stdout
        assert "'a'" in r.stdout
    finally:
        await repl.shutdown()


@pytest.mark.asyncio
async def test_repl_error_handling(tmp_path):
    """Syntax/runtime errors are captured in stderr, process survives."""
    repl = PersistentRepl("test-session", sandbox_base=str(tmp_path))
    await repl.start()
    try:
        r = await repl.execute("1/0")
        assert "ZeroDivisionError" in r.stderr

        # Process should still be alive
        assert repl.is_alive
        r2 = await repl.execute("print('still alive')")
        assert "still alive" in r2.stdout
    finally:
        await repl.shutdown()


@pytest.mark.asyncio
async def test_repl_timeout(tmp_path):
    """Long-running code triggers timeout."""
    repl = PersistentRepl(
        "test-session",
        timeout_seconds=3,
        sandbox_base=str(tmp_path),
    )
    await repl.start()
    try:
        r = await repl.execute("import time; time.sleep(30)")
        assert r.timed_out is True
        assert r.exit_code != 0 or r.timed_out
    finally:
        await repl.shutdown()


@pytest.mark.asyncio
async def test_repl_output_truncation(tmp_path):
    """Output exceeding max_output_chars is truncated."""
    repl = PersistentRepl(
        "test-session",
        max_output_chars=500,
        sandbox_base=str(tmp_path),
    )
    await repl.start()
    try:
        r = await repl.execute("print('x' * 2000)")
        assert r.truncated is True
        assert len(r.stdout) <= 550  # 500 + truncation message
    finally:
        await repl.shutdown()


@pytest.mark.asyncio
async def test_repl_reset_clears_state(tmp_path):
    """Reset kills the process and starts fresh."""
    repl = PersistentRepl("test-session", sandbox_base=str(tmp_path))
    await repl.start()
    try:
        await repl.execute("my_var = 'hello'")
        await repl.reset()

        r = await repl.execute("print(my_var)")
        # my_var should not exist after reset
        assert "NameError" in r.stderr
    finally:
        await repl.shutdown()


@pytest.mark.asyncio
async def test_repl_auto_restart_after_crash(tmp_path):
    """If the process dies, next execute() restarts it."""
    repl = PersistentRepl("test-session", sandbox_base=str(tmp_path))
    await repl.start()
    try:
        # Force-kill the subprocess
        await repl._kill_proc()
        assert not repl.is_alive

        # Next call should auto-restart
        r = await repl.execute("print('recovered')")
        assert "recovered" in r.stdout
        assert repl.is_alive
    finally:
        await repl.shutdown()


@pytest.mark.asyncio
async def test_repl_sandbox_dir_cleanup(tmp_path):
    """Shutdown removes the sandbox directory."""
    repl = PersistentRepl("test-session", sandbox_base=str(tmp_path))
    await repl.start()
    sandbox = repl._sandbox_dir
    assert sandbox is not None
    assert sandbox.exists()

    await repl.shutdown()
    assert not sandbox.exists()


# ---------------------------------------------------------------------------
# ReplSessionManager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manager_get_or_create(tmp_path):
    mgr = ReplSessionManager(max_sessions=3, sandbox_base=str(tmp_path))
    try:
        repl = await mgr.get_or_create("s1")
        assert repl.is_alive
        assert mgr.active_count == 1

        # Same session returns same instance
        repl2 = await mgr.get_or_create("s1")
        assert repl2 is repl
    finally:
        await mgr.shutdown_all()


@pytest.mark.asyncio
async def test_manager_session_isolation(tmp_path):
    mgr = ReplSessionManager(max_sessions=3, sandbox_base=str(tmp_path))
    try:
        repl_a = await mgr.get_or_create("a")
        repl_b = await mgr.get_or_create("b")

        await repl_a.execute("val = 'session_a'")
        await repl_b.execute("val = 'session_b'")

        r_a = await repl_a.execute("print(val)")
        r_b = await repl_b.execute("print(val)")

        assert "session_a" in r_a.stdout
        assert "session_b" in r_b.stdout
    finally:
        await mgr.shutdown_all()


@pytest.mark.asyncio
async def test_manager_lru_eviction(tmp_path):
    mgr = ReplSessionManager(max_sessions=2, sandbox_base=str(tmp_path))
    try:
        await mgr.get_or_create("s1")
        await mgr.get_or_create("s2")
        assert mgr.active_count == 2

        # Creating s3 should evict s1 (oldest)
        await mgr.get_or_create("s3")
        assert mgr.active_count == 2
        assert "s1" not in mgr.active_session_ids
        assert "s2" in mgr.active_session_ids
        assert "s3" in mgr.active_session_ids
    finally:
        await mgr.shutdown_all()


@pytest.mark.asyncio
async def test_manager_lru_touch_order(tmp_path):
    """Accessing a session moves it to the end (most recent)."""
    mgr = ReplSessionManager(max_sessions=2, sandbox_base=str(tmp_path))
    try:
        await mgr.get_or_create("s1")
        await mgr.get_or_create("s2")

        # Touch s1 to make it most recent
        await mgr.get_or_create("s1")

        # s2 is now oldest, should be evicted
        await mgr.get_or_create("s3")
        assert "s2" not in mgr.active_session_ids
        assert "s1" in mgr.active_session_ids
        assert "s3" in mgr.active_session_ids
    finally:
        await mgr.shutdown_all()


@pytest.mark.asyncio
async def test_manager_reset_session(tmp_path):
    mgr = ReplSessionManager(max_sessions=3, sandbox_base=str(tmp_path))
    try:
        repl = await mgr.get_or_create("s1")
        await repl.execute("x = 99")

        result = await mgr.reset("s1")
        assert result is True

        repl = await mgr.get_or_create("s1")
        r = await repl.execute("print(x)")
        assert "NameError" in r.stderr
    finally:
        await mgr.shutdown_all()


@pytest.mark.asyncio
async def test_manager_reset_nonexistent(tmp_path):
    mgr = ReplSessionManager(max_sessions=3, sandbox_base=str(tmp_path))
    result = await mgr.reset("does-not-exist")
    assert result is False


@pytest.mark.asyncio
async def test_manager_shutdown_session(tmp_path):
    mgr = ReplSessionManager(max_sessions=3, sandbox_base=str(tmp_path))
    try:
        await mgr.get_or_create("s1")
        assert mgr.active_count == 1

        result = await mgr.shutdown_session("s1")
        assert result is True
        assert mgr.active_count == 0
    finally:
        await mgr.shutdown_all()


@pytest.mark.asyncio
async def test_manager_shutdown_all(tmp_path):
    mgr = ReplSessionManager(max_sessions=5, sandbox_base=str(tmp_path))
    for i in range(4):
        await mgr.get_or_create(f"s{i}")
    assert mgr.active_count == 4

    count = await mgr.shutdown_all()
    assert count == 4
    assert mgr.active_count == 0


# ---------------------------------------------------------------------------
# Tool integration (code_execute with persistent REPL)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_code_execute_persistent_repl(tmp_path, monkeypatch):
    """code_execute with persistent=True uses ReplSessionManager."""
    from app.tools import AgentTooling

    # Enable REPL in settings
    monkeypatch.setattr("app.tools.settings.repl_enabled", True)

    tooling = AgentTooling(workspace_root=str(tmp_path))
    mgr = ReplSessionManager(max_sessions=3, sandbox_base=str(tmp_path))
    tooling.set_repl_manager(mgr)

    try:
        result1 = await tooling.code_execute(
            code="x = 42",
            language="python",
            persistent=True,
            session_id="test",
        )
        data1 = json.loads(result1)
        assert data1["success"] is True
        assert data1["strategy"] == "persistent_repl"

        result2 = await tooling.code_execute(
            code="print(x)",
            language="python",
            persistent=True,
            session_id="test",
        )
        data2 = json.loads(result2)
        assert data2["success"] is True
        assert "42" in data2["stdout"]
    finally:
        await mgr.shutdown_all()


@pytest.mark.asyncio
async def test_code_execute_stateless_fallback(tmp_path, monkeypatch):
    """code_execute with persistent=False falls back to CodeSandbox."""
    from app.tools import AgentTooling

    monkeypatch.setattr("app.tools.settings.repl_enabled", True)

    tooling = AgentTooling(workspace_root=str(tmp_path))
    mgr = ReplSessionManager(max_sessions=3, sandbox_base=str(tmp_path))
    tooling.set_repl_manager(mgr)

    try:
        result = await tooling.code_execute(
            code="print('hello')",
            language="python",
            persistent=False,
        )
        data = json.loads(result)
        assert data["strategy"] != "persistent_repl"
        assert "hello" in data["stdout"]
    finally:
        await mgr.shutdown_all()


@pytest.mark.asyncio
async def test_code_execute_non_python_stays_stateless(tmp_path, monkeypatch):
    """Non-Python languages always use stateless sandbox."""
    from app.tools import AgentTooling

    monkeypatch.setattr("app.tools.settings.repl_enabled", True)

    tooling = AgentTooling(workspace_root=str(tmp_path))
    mgr = ReplSessionManager(max_sessions=3, sandbox_base=str(tmp_path))
    tooling.set_repl_manager(mgr)

    try:
        result = await tooling.code_execute(
            code="console.log('hi')",
            language="javascript",
            persistent=True,
        )
        data = json.loads(result)
        assert data["strategy"] != "persistent_repl"
    finally:
        await mgr.shutdown_all()


@pytest.mark.asyncio
async def test_code_reset_tool(tmp_path, monkeypatch):
    """code_reset clears REPL state."""
    from app.tools import AgentTooling

    monkeypatch.setattr("app.tools.settings.repl_enabled", True)

    tooling = AgentTooling(workspace_root=str(tmp_path))
    mgr = ReplSessionManager(max_sessions=3, sandbox_base=str(tmp_path))
    tooling.set_repl_manager(mgr)

    try:
        await tooling.code_execute(
            code="my_var = 'hello'",
            language="python",
            persistent=True,
            session_id="test",
        )

        reset_result = await tooling.code_reset(session_id="test")
        assert "reset" in reset_result.lower()

        result = await tooling.code_execute(
            code="print(my_var)",
            language="python",
            persistent=True,
            session_id="test",
        )
        data = json.loads(result)
        assert "NameError" in data["stderr"]
    finally:
        await mgr.shutdown_all()


@pytest.mark.asyncio
async def test_code_reset_disabled(tmp_path, monkeypatch):
    """code_reset when REPL is disabled returns info message."""
    from app.tools import AgentTooling

    monkeypatch.setattr("app.tools.settings.repl_enabled", False)

    tooling = AgentTooling(workspace_root=str(tmp_path))
    result = await tooling.code_reset()
    assert "not enabled" in result.lower()
