from __future__ import annotations

import json

from app.memory import MemoryStore


def test_orphaned_tool_call_synthetic_result_injected(tmp_path) -> None:
    store = MemoryStore(max_items_per_session=50, persist_dir=str(tmp_path))
    session_id = "sess-orphan"

    store.add(
        session_id,
        "assistant",
        json.dumps({"tool_calls": [{"id": "call-1", "name": "run_command"}]}, ensure_ascii=False),
    )
    store.add(session_id, "user", "next message")

    repaired = store.repair_orphaned_tool_calls(session_id)

    assert repaired == 1
    items = store.get_items(session_id)
    synthetic_items = [item for item in items if item.role == "tool:__synthetic__"]
    assert len(synthetic_items) == 1
    assert "call-1" in synthetic_items[0].content


def test_orphaned_tool_call_repair_does_not_touch_matched_calls(tmp_path) -> None:
    store = MemoryStore(max_items_per_session=50, persist_dir=str(tmp_path))
    session_id = "sess-matched"

    store.add(
        session_id,
        "assistant",
        json.dumps({"tool_calls": [{"id": "call-2", "name": "read_file"}]}, ensure_ascii=False),
    )
    store.add(
        session_id,
        "tool:read_file",
        json.dumps({"tool_call_id": "call-2", "content": "ok"}, ensure_ascii=False),
    )
    store.add(session_id, "user", "follow-up")

    repaired = store.repair_orphaned_tool_calls(session_id)

    assert repaired == 0
    items = store.get_items(session_id)
    assert not any(item.role == "tool:__synthetic__" for item in items)


def test_sanitize_session_history_removes_duplicate_conversation_roles(tmp_path) -> None:
    store = MemoryStore(max_items_per_session=50, persist_dir=str(tmp_path))
    session_id = "sess-sanitize"

    store.add(session_id, "user", "u1")
    store.add(session_id, "user", "u2")
    store.add(session_id, "assistant", "a1")
    store.add(session_id, "assistant", "a2")
    store.add(session_id, "tool:read_file", "ok")

    removed = store.sanitize_session_history(session_id)

    assert removed == 2
    items = store.get_items(session_id)
    conversation_roles = [item.role for item in items if item.role in {"user", "assistant"}]
    assert conversation_roles == ["user", "assistant"]


def test_sanitize_session_history_noop_when_alternating(tmp_path) -> None:
    store = MemoryStore(max_items_per_session=50, persist_dir=str(tmp_path))
    session_id = "sess-sanitize-noop"

    store.add(session_id, "user", "u1")
    store.add(session_id, "assistant", "a1")
    store.add(session_id, "user", "u2")

    removed = store.sanitize_session_history(session_id)

    assert removed == 0


def test_orphaned_repair_ignores_generic_id_without_tool_calls(tmp_path) -> None:
    store = MemoryStore(max_items_per_session=50, persist_dir=str(tmp_path))
    session_id = "sess-generic-id"

    store.add(
        session_id,
        "assistant",
        json.dumps({"id": "not-a-tool-call", "message": "normal assistant payload"}, ensure_ascii=False),
    )
    store.add(session_id, "user", "follow-up")

    repaired = store.repair_orphaned_tool_calls(session_id)

    assert repaired == 0
    items = store.get_items(session_id)
    assert not any(item.role == "tool:__synthetic__" for item in items)
