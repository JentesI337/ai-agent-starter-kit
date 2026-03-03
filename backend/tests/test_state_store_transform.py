from __future__ import annotations

from app.config import settings
from app.state import StateStore


def test_state_store_transforms_events_clamp_and_redact(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "persist_transform_max_string_chars", 40)
    monkeypatch.setattr(settings, "persist_transform_redact_secrets", True)

    store = StateStore(persist_dir=str(tmp_path / "state"))
    store.init_run(
        run_id="run-1",
        session_id="s1",
        request_id="run-1",
        user_message="hello",
        runtime="local",
        model="llama",
    )

    store.append_event(
        run_id="run-1",
        event={
            "type": "tool_output",
            "message": f"token=abc12345 bearer qwertyuiopasdfgh {'x' * 120}",
            "nested": {"password": "secret-value-123"},
        },
    )

    run_state = store.get_run("run-1")
    assert run_state is not None
    event = run_state["events"][0]
    assert "[REDACTED]" in event["message"]
    assert "abc12345" not in event["message"]
    assert "secret-value-123" not in event["nested"]["password"]
    assert "[truncated:" in event["message"]


def test_state_store_transforms_input_meta_and_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "persist_transform_max_string_chars", 24)
    monkeypatch.setattr(settings, "persist_transform_redact_secrets", True)

    store = StateStore(persist_dir=str(tmp_path / "state"))
    store.init_run(
        run_id="run-2",
        session_id="s2",
        request_id="run-2",
        user_message="password=verylongsecretvalue",
        runtime="local",
        model="llama",
        meta={"auth": "Bearer abcdefghijklmnop"},
    )

    store.mark_failed("run-2", "token=zyx987654321")
    run_state = store.get_run("run-2")
    assert run_state is not None

    assert "[REDACTED]" in run_state["input"]["user_message"]
    assert "[REDACTED]" in run_state["meta"]["auth"]
    assert "[REDACTED]" in run_state["error"]
