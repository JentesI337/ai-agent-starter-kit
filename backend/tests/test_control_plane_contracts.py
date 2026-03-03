from __future__ import annotations

import os
from pathlib import Path
import shutil
import uuid

os.environ.setdefault("OLLAMA_BIN", "python")

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app, agent, agent_registry, runtime_manager, state_store
from app.runtime_manager import RuntimeState


def _set_local_runtime() -> None:
    runtime_manager._state = RuntimeState(
        runtime="local",
        base_url="http://localhost:11434/v1",
        model="llama3.3:70b-instruct-q4_K_M",
    )


def test_control_run_start_and_wait_contract(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"echo:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    start = client.post("/api/control/run.start", json={"message": "hello"})
    assert start.status_code == 200
    start_payload = start.json()
    assert start_payload["schema"] == "run.start.v1"
    assert start_payload["status"] == "accepted"
    assert start_payload["idempotency"]["reused"] is False
    run_id = start_payload["runId"]

    wait = client.post(
        "/api/control/run.wait",
        json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert wait.status_code == 200
    payload = wait.json()
    assert payload["schema"] == "run.wait.v1"
    assert payload["status"] == "ok"
    assert payload["runStatus"] == "completed"
    assert payload["run_status"] == "completed"
    assert isinstance(payload.get("startedAt"), str)
    assert isinstance(payload.get("endedAt"), str)
    assert payload["final"] == "echo:hello"


def test_control_agent_run_and_wait_contract(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"echo:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    start = client.post("/api/control/agent.run", json={"message": "hello-agent"})
    assert start.status_code == 200
    start_payload = start.json()
    assert start_payload["schema"] == "agent.run.v1"
    assert start_payload["status"] == "accepted"
    run_id = start_payload["runId"]

    wait = client.post(
        "/api/control/agent.wait",
        json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert wait.status_code == 200
    payload = wait.json()
    assert payload["schema"] == "agent.wait.v1"
    assert payload["status"] == "ok"
    assert payload["runStatus"] == "completed"
    assert payload["run_status"] == "completed"
    assert isinstance(payload.get("startedAt"), str)
    assert isinstance(payload.get("endedAt"), str)
    assert payload["final"] == "echo:hello-agent"


def test_control_run_start_idempotency_reuses_same_run(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"echo:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    first = client.post(
        "/api/control/run.start",
        headers={"Idempotency-Key": "contract-key-1"},
        json={"message": "same-request"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/control/run.start",
        headers={"Idempotency-Key": "contract-key-1"},
        json={"message": "same-request"},
    )
    assert second.status_code == 200

    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["runId"] == second_payload["runId"]
    assert second_payload["idempotency"]["reused"] is True


def test_control_run_start_idempotency_rejects_changed_payload(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"echo:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    first = client.post(
        "/api/control/run.start",
        headers={"Idempotency-Key": "contract-key-2"},
        json={"message": "v1"},
    )
    assert first.status_code == 200

    changed = client.post(
        "/api/control/run.start",
        headers={"Idempotency-Key": "contract-key-2"},
        json={"message": "v2"},
    )
    assert changed.status_code == 409


def test_control_sessions_list_minimal(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"echo:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    run1 = client.post("/api/control/run.start", json={"message": "a", "session_id": "sess-a"})
    run2 = client.post("/api/control/run.start", json={"message": "b", "session_id": "sess-b"})
    assert run1.status_code == 200
    assert run2.status_code == 200

    wait1 = client.post(
        "/api/control/run.wait",
        json={"run_id": run1.json()["runId"], "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    wait2 = client.post(
        "/api/control/run.wait",
        json={"run_id": run2.json()["runId"], "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert wait1.status_code == 200
    assert wait2.status_code == 200

    sessions = client.post("/api/control/sessions.list", json={"limit": 10, "active_only": False})
    assert sessions.status_code == 200
    payload = sessions.json()
    assert payload["schema"] == "sessions.list.v1"
    assert isinstance(payload["items"], list)
    ids = {item["session_id"] for item in payload["items"]}
    assert "sess-a" in ids
    assert "sess-b" in ids


def test_control_sessions_resolve_minimal(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"echo:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    created = client.post("/api/control/run.start", json={"message": "resolve", "session_id": "sess-resolve"})
    assert created.status_code == 200

    waited = client.post(
        "/api/control/run.wait",
        json={"run_id": created.json()["runId"], "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert waited.status_code == 200

    resolve = client.post("/api/control/sessions.resolve", json={"session_id": "sess-resolve"})
    assert resolve.status_code == 200
    payload = resolve.json()
    assert payload["schema"] == "sessions.resolve.v1"
    assert payload["session"]["session_id"] == "sess-resolve"
    assert payload["session"]["runs_count"] >= 1

    not_found = client.post("/api/control/sessions.resolve", json={"session_id": "does-not-exist"})
    assert not_found.status_code == 404


def test_control_sessions_history_minimal(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"echo:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    run1 = client.post("/api/control/run.start", json={"message": "h1", "session_id": "sess-history"})
    run2 = client.post("/api/control/run.start", json={"message": "h2", "session_id": "sess-history"})
    assert run1.status_code == 200
    assert run2.status_code == 200

    for run_id in (run1.json()["runId"], run2.json()["runId"]):
        wait = client.post(
            "/api/control/run.wait",
            json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
        )
        assert wait.status_code == 200

    history = client.post("/api/control/sessions.history", json={"session_id": "sess-history", "limit": 10})
    assert history.status_code == 200
    payload = history.json()
    assert payload["schema"] == "sessions.history.v1"
    assert payload["session_id"] == "sess-history"
    assert payload["count"] >= 2
    assert isinstance(payload["items"], list)
    assert payload["items"][0]["run_id"]
    assert "final" in payload["items"][0]


def test_lifecycle_event_schema_v1_is_persisted(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": "done",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return "done"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    start = client.post("/api/control/run.start", json={"message": "schema-check"})
    assert start.status_code == 200
    run_id = start.json()["runId"]

    wait = client.post(
        "/api/control/run.wait",
        json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert wait.status_code == 200

    run_state = state_store.get_run(run_id)
    assert run_state is not None
    lifecycle_events = [event for event in run_state.get("events", []) if event.get("type") == "lifecycle"]
    assert lifecycle_events

    first = lifecycle_events[0]
    assert first["schema"] == "lifecycle.v1"
    assert isinstance(first.get("event_id"), str)
    assert first.get("run_id") == run_id
    assert first.get("phase") in {"start", "progress", "end", "error"}


def test_control_tools_catalog_contract() -> None:
    client = TestClient(app)

    response = client.post("/api/control/tools.catalog", json={})
    assert response.status_code == 200
    payload = response.json()

    assert payload["schema"] == "tools.catalog.v1"
    assert isinstance(payload["agents"], list)
    assert any(item.get("id") == "head-agent" for item in payload["agents"])
    assert isinstance(payload["tools"], list)
    assert "read_file" in payload["tools"]


def test_control_tools_profile_contract() -> None:
    client = TestClient(app)

    response = client.post("/api/control/tools.profile", json={})
    assert response.status_code == 200
    payload = response.json()

    assert payload["schema"] == "tools.profile.v1"
    ids = {item.get("id") for item in payload.get("profiles") or []}
    assert "minimal" in ids
    assert "coding" in ids
    assert "review" in ids


def test_control_tools_profile_rejects_unknown_profile() -> None:
    client = TestClient(app)

    response = client.post("/api/control/tools.profile", json={"profile_id": "unknown-profile"})
    assert response.status_code == 400


def test_control_tools_policy_matrix_contract() -> None:
    client = TestClient(app)

    response = client.post("/api/control/tools.policy.matrix", json={"agent_id": "head-agent"})
    assert response.status_code == 200
    payload = response.json()

    assert payload["schema"] == "tools.policy.matrix.v1"
    assert payload["agent_id"] == "head-agent"
    assert isinstance(payload["base_tools"], list)
    assert "read_file" in payload["base_tools"]
    assert "profiles" in payload
    assert "presets" in payload
    assert "by_provider" in payload
    assert "by_model" in payload
    assert payload["resolution_order"] == [
        "global",
        "profile",
        "preset",
        "provider",
        "model",
        "agent_depth",
        "request",
    ]


def test_control_tools_policy_matrix_rejects_unknown_agent() -> None:
    client = TestClient(app)

    response = client.post("/api/control/tools.policy.matrix", json={"agent_id": "unknown-agent"})
    assert response.status_code == 400


def test_control_skills_list_contract(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    skill_dir = skills_root / "demo-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: demo-skill\n"
        "description: Demo skill for contract test\n"
        "---\n"
        "# Demo\n",
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/api/control/skills.list",
        json={
            "skills_dir": str(skills_root),
            "max_discovered": 10,
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["schema"] == "skills.list.v1"
    assert payload["count"] == 1
    assert payload["discovered_count"] == 1
    assert payload["eligible_count"] == 1
    assert isinstance(payload["items"], list)
    assert payload["items"][0]["name"] == "demo-skill"


def test_control_skills_preview_contract(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    skill_dir = skills_root / "preview-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: preview-skill\n"
        "description: Preview skill for contract test\n"
        "---\n"
        "# Preview\n",
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/api/control/skills.preview",
        json={
            "skills_dir": str(skills_root),
            "max_discovered": 10,
            "max_prompt_chars": 5000,
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["schema"] == "skills.preview.v1"
    snapshot = payload["snapshot"]
    assert snapshot["discovered_count"] == 1
    assert snapshot["eligible_count"] == 1
    assert snapshot["selected_count"] == 1
    assert snapshot["truncated"] is False
    assert isinstance(snapshot["prompt"], str)
    assert "preview-skill" in snapshot["prompt"]


def test_control_skills_check_contract(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)

    ok_skill = skills_root / "ok-skill"
    ok_skill.mkdir(parents=True, exist_ok=True)
    (ok_skill / "SKILL.md").write_text(
        "---\n"
        "name: ok-skill\n"
        "description: Eligible skill\n"
        "---\n"
        "# OK\n",
        encoding="utf-8",
    )

    bad_skill = skills_root / "bad-skill"
    bad_skill.mkdir(parents=True, exist_ok=True)
    (bad_skill / "SKILL.md").write_text(
        "---\n"
        "name: bad-skill\n"
        "description: Ineligible skill\n"
        "requires_env: NEVER_SET_ENV_ABC123\n"
        "---\n"
        "# BAD\n",
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/api/control/skills.check",
        json={
            "skills_dir": str(skills_root),
            "max_discovered": 10,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema"] == "skills.check.v1"
    assert payload["discovered_count"] == 2
    assert payload["eligible_count"] == 1
    assert payload["ineligible_count"] == 1
    assert "bad-skill" in payload["rejected"]
    assert payload["rejected"]["bad-skill"].startswith("missing_env:")


def test_control_skills_sync_dry_run_contract(tmp_path) -> None:
    source_root = tmp_path / "skills-src"
    source_root.mkdir(parents=True, exist_ok=True)
    skill_dir = source_root / "sync-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: sync-skill\n"
        "description: Sync dry run\n"
        "---\n"
        "# Sync\n",
        encoding="utf-8",
    )

    target_root = Path(settings.workspace_root) / f".tmp-skills-sync-{uuid.uuid4().hex[:8]}"
    shutil.rmtree(target_root, ignore_errors=True)

    try:
        client = TestClient(app)
        response = client.post(
            "/api/control/skills.sync",
            json={
                "source_skills_dir": str(source_root),
                "target_skills_dir": str(target_root),
                "apply": False,
                "max_discovered": 10,
            },
        )
        assert response.status_code == 200
        payload = response.json()

        assert payload["schema"] == "skills.sync.v1"
        assert payload["mode"] == "dry_run"
        assert payload["planned_count"] == 1
        assert payload["applied_count"] == 0
        assert isinstance(payload["audit"], dict)
        assert isinstance(payload["audit"]["duration_ms"], int)
        assert payload["audit"]["duration_ms"] >= 0
        assert payload["actions"][0]["skill_name"] == "sync-skill"
        assert payload["actions"][0]["action"] in {"create", "update"}
    finally:
        shutil.rmtree(target_root, ignore_errors=True)


def test_control_skills_sync_apply_contract(tmp_path) -> None:
    source_root = tmp_path / "skills-src-apply"
    source_root.mkdir(parents=True, exist_ok=True)
    skill_dir = source_root / "apply-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: apply-skill\n"
        "description: Sync apply\n"
        "---\n"
        "# Apply\n",
        encoding="utf-8",
    )
    (skill_dir / "notes.txt").write_text("hello", encoding="utf-8")

    target_root = Path(settings.workspace_root) / f".tmp-skills-sync-apply-{uuid.uuid4().hex[:8]}"
    shutil.rmtree(target_root, ignore_errors=True)

    try:
        client = TestClient(app)
        response = client.post(
            "/api/control/skills.sync",
            json={
                "source_skills_dir": str(source_root),
                "target_skills_dir": str(target_root),
                "apply": True,
                "max_discovered": 10,
            },
        )
        assert response.status_code == 200
        payload = response.json()

        assert payload["schema"] == "skills.sync.v1"
        assert payload["mode"] == "apply"
        assert payload["planned_count"] == 1
        assert payload["applied_count"] == 1
        assert isinstance(payload["audit"], dict)
        assert isinstance(payload["audit"]["duration_ms"], int)
        assert payload["audit"]["duration_ms"] >= 0

        copied_skill_dir = target_root / "apply-skill"
        assert copied_skill_dir.exists()
        assert (copied_skill_dir / "SKILL.md").exists()
        assert (copied_skill_dir / "notes.txt").exists()
    finally:
        shutil.rmtree(target_root, ignore_errors=True)


def test_control_skills_sync_clean_target_dry_run_contract(tmp_path) -> None:
    source_root = tmp_path / "skills-src-clean"
    source_root.mkdir(parents=True, exist_ok=True)
    skill_dir = source_root / "keep-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: keep-skill\n"
        "description: Keep and sync\n"
        "---\n"
        "# Keep\n",
        encoding="utf-8",
    )

    target_root = Path(settings.workspace_root) / f".tmp-skills-sync-clean-{uuid.uuid4().hex[:8]}"
    shutil.rmtree(target_root, ignore_errors=True)
    stale_skill = target_root / "stale-skill"
    stale_skill.mkdir(parents=True, exist_ok=True)
    (stale_skill / "SKILL.md").write_text("# stale", encoding="utf-8")
    non_skill_dir = target_root / "keep-this-dir"
    non_skill_dir.mkdir(parents=True, exist_ok=True)
    (non_skill_dir / "README.txt").write_text("not a skill", encoding="utf-8")

    try:
        client = TestClient(app)
        response = client.post(
            "/api/control/skills.sync",
            json={
                "source_skills_dir": str(source_root),
                "target_skills_dir": str(target_root),
                "apply": False,
                "clean_target": True,
                "max_discovered": 10,
            },
        )
        assert response.status_code == 200
        payload = response.json()

        assert payload["schema"] == "skills.sync.v1"
        assert payload["clean_target"] is True
        assert payload["planned_delete_count"] == 1
        assert isinstance(payload["audit"], dict)
        assert isinstance(payload["audit"]["duration_ms"], int)
        assert payload["audit"]["duration_ms"] >= 0
        delete_actions = [item for item in payload["actions"] if item["action"] == "delete"]
        assert len(delete_actions) == 1
        assert Path(delete_actions[0]["target_dir"]).name == "stale-skill"
    finally:
        shutil.rmtree(target_root, ignore_errors=True)


def test_control_skills_sync_clean_target_apply_requires_confirmation(tmp_path) -> None:
    source_root = tmp_path / "skills-src-clean-apply"
    source_root.mkdir(parents=True, exist_ok=True)
    skill_dir = source_root / "apply-clean-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: apply-clean-skill\n"
        "description: apply clean\n"
        "---\n"
        "# Apply clean\n",
        encoding="utf-8",
    )

    target_root = Path(settings.workspace_root) / f".tmp-skills-sync-clean-apply-{uuid.uuid4().hex[:8]}"
    shutil.rmtree(target_root, ignore_errors=True)
    stale_skill = target_root / "obsolete-skill"
    stale_skill.mkdir(parents=True, exist_ok=True)
    (stale_skill / "SKILL.md").write_text("# obsolete", encoding="utf-8")

    try:
        client = TestClient(app)

        rejected = client.post(
            "/api/control/skills.sync",
            json={
                "source_skills_dir": str(source_root),
                "target_skills_dir": str(target_root),
                "apply": True,
                "clean_target": True,
            },
        )
        assert rejected.status_code == 400

        accepted = client.post(
            "/api/control/skills.sync",
            json={
                "source_skills_dir": str(source_root),
                "target_skills_dir": str(target_root),
                "apply": True,
                "clean_target": True,
                "confirm_clean_target": True,
            },
        )
        assert accepted.status_code == 200
        payload = accepted.json()

        assert payload["schema"] == "skills.sync.v1"
        assert payload["mode"] == "apply"
        assert payload["applied_delete_count"] == 1
        assert not stale_skill.exists()
    finally:
        shutil.rmtree(target_root, ignore_errors=True)


def test_control_skills_sync_rejects_target_outside_workspace(tmp_path) -> None:
    source_root = tmp_path / "skills-src-outside"
    source_root.mkdir(parents=True, exist_ok=True)
    skill_dir = source_root / "outside-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: outside-skill\n"
        "description: should fail on target guardrail\n"
        "---\n"
        "# Outside\n",
        encoding="utf-8",
    )

    target_outside = tmp_path / "outside-target"

    client = TestClient(app)
    response = client.post(
        "/api/control/skills.sync",
        json={
            "source_skills_dir": str(source_root),
            "target_skills_dir": str(target_outside),
            "apply": False,
        },
    )
    assert response.status_code == 400


def test_control_workflows_list_contract() -> None:
    client = TestClient(app)

    create = client.post(
        "/api/custom-agents",
        json={
            "name": f"Workflow Contract {uuid.uuid4().hex[:8]}",
            "base_agent_id": "head-agent",
            "description": "workflow test",
            "workflow_steps": ["analyze", "implement", "verify"],
        },
    )
    assert create.status_code == 200
    created_id = create.json()["id"]

    try:
        response = client.post(
            "/api/control/workflows.list",
            json={"limit": 50, "base_agent_id": "head-agent"},
        )
        assert response.status_code == 200
        payload = response.json()

        assert payload["schema"] == "workflows.list.v1"
        assert isinstance(payload["items"], list)
        match = next((item for item in payload["items"] if item.get("id") == created_id), None)
        assert match is not None
        assert match["base_agent_id"] == "head-agent"
        assert match["version"] == 1
        assert match["step_count"] == 3
    finally:
        _ = client.delete(f"/api/custom-agents/{created_id}")


def test_control_workflows_create_contract() -> None:
    client = TestClient(app)
    created_id = None

    try:
        response = client.post(
            "/api/control/workflows.create",
            json={
                "name": f"Workflow Create {uuid.uuid4().hex[:8]}",
                "base_agent_id": "head-agent",
                "description": "create contract",
                "steps": ["plan", "implement", "verify"],
            },
        )
        assert response.status_code == 200
        payload = response.json()

        assert payload["schema"] == "workflows.create.v1"
        assert payload["status"] == "created"
        assert payload["workflow"]["base_agent_id"] == "head-agent"
        assert payload["workflow"]["step_count"] == 3
        assert payload["idempotency"]["reused"] is False
        created_id = payload["workflow"]["id"]
    finally:
        if created_id:
            _ = client.delete(f"/api/custom-agents/{created_id}")


def test_control_workflows_create_idempotency_replay_and_conflict() -> None:
    client = TestClient(app)
    created_id = None

    try:
        first = client.post(
            "/api/control/workflows.create",
            headers={"Idempotency-Key": "workflow-create-key-1"},
            json={
                "name": "Workflow Idempotent",
                "base_agent_id": "head-agent",
                "steps": ["a", "b"],
            },
        )
        assert first.status_code == 200
        first_payload = first.json()
        created_id = first_payload["workflow"]["id"]

        replay = client.post(
            "/api/control/workflows.create",
            headers={"Idempotency-Key": "workflow-create-key-1"},
            json={
                "name": "Workflow Idempotent",
                "base_agent_id": "head-agent",
                "steps": ["a", "b"],
            },
        )
        assert replay.status_code == 200
        replay_payload = replay.json()
        assert replay_payload["workflow"]["id"] == created_id
        assert replay_payload["idempotency"]["reused"] is True

        conflict = client.post(
            "/api/control/workflows.create",
            headers={"Idempotency-Key": "workflow-create-key-1"},
            json={
                "name": "Workflow Idempotent Changed",
                "base_agent_id": "head-agent",
                "steps": ["a", "b"],
            },
        )
        assert conflict.status_code == 409
    finally:
        if created_id:
            _ = client.delete(f"/api/custom-agents/{created_id}")


def test_control_workflows_update_contract() -> None:
    client = TestClient(app)
    created_id = None

    try:
        created = client.post(
            "/api/control/workflows.create",
            json={
                "name": f"Workflow Update {uuid.uuid4().hex[:8]}",
                "base_agent_id": "head-agent",
                "steps": ["a", "b"],
            },
        )
        assert created.status_code == 200
        created_id = created.json()["workflow"]["id"]

        updated = client.post(
            "/api/control/workflows.update",
            json={
                "id": created_id,
                "name": "Workflow Updated Name",
                "steps": ["a", "b", "c"],
            },
        )
        assert updated.status_code == 200
        payload = updated.json()

        assert payload["schema"] == "workflows.update.v1"
        assert payload["status"] == "updated"
        assert payload["workflow"]["id"] == created_id
        assert payload["workflow"]["name"] == "Workflow Updated Name"
        assert payload["workflow"]["version"] == 2
        assert payload["workflow"]["step_count"] == 3
    finally:
        if created_id:
            _ = client.delete(f"/api/custom-agents/{created_id}")


def test_control_workflows_update_idempotency_replay_and_conflict() -> None:
    client = TestClient(app)
    created_id = None

    try:
        created = client.post(
            "/api/control/workflows.create",
            json={
                "name": f"Workflow Update Idemp {uuid.uuid4().hex[:8]}",
                "base_agent_id": "head-agent",
                "steps": ["x"],
            },
        )
        assert created.status_code == 200
        created_id = created.json()["workflow"]["id"]

        first = client.post(
            "/api/control/workflows.update",
            headers={"Idempotency-Key": "workflow-update-key-1"},
            json={
                "id": created_id,
                "name": "Updated Once",
                "steps": ["x", "y"],
            },
        )
        assert first.status_code == 200
        first_payload = first.json()
        assert first_payload["idempotency"]["reused"] is False

        replay = client.post(
            "/api/control/workflows.update",
            headers={"Idempotency-Key": "workflow-update-key-1"},
            json={
                "id": created_id,
                "name": "Updated Once",
                "steps": ["x", "y"],
            },
        )
        assert replay.status_code == 200
        replay_payload = replay.json()
        assert replay_payload["workflow"]["id"] == created_id
        assert replay_payload["idempotency"]["reused"] is True

        conflict = client.post(
            "/api/control/workflows.update",
            headers={"Idempotency-Key": "workflow-update-key-1"},
            json={
                "id": created_id,
                "name": "Updated Twice",
                "steps": ["x", "y"],
            },
        )
        assert conflict.status_code == 409
    finally:
        if created_id:
            _ = client.delete(f"/api/custom-agents/{created_id}")


def test_control_workflows_execute_contract(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"exec:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"exec:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent_registry["head-agent"], "run", fake_run)

    client = TestClient(app)
    created_id = None

    try:
        created = client.post(
            "/api/control/workflows.create",
            json={
                "name": f"Workflow Execute {uuid.uuid4().hex[:8]}",
                "base_agent_id": "head-agent",
                "steps": ["analyze", "execute"],
            },
        )
        assert created.status_code == 200
        created_id = created.json()["workflow"]["id"]

        execute = client.post(
            "/api/control/workflows.execute",
            json={
                "workflow_id": created_id,
                "message": "execute-this",
            },
        )
        assert execute.status_code == 200
        execute_payload = execute.json()
        assert execute_payload["schema"] == "workflows.execute.v1"
        assert execute_payload["status"] == "accepted"
        assert execute_payload["execution"]["engine"] == "workflow.revision_flow.v1"
        assert execute_payload["execution"]["mode"] == "subrun_graph"
        assert execute_payload["workflow"]["step_count"] == 2
        assert isinstance(execute_payload["execution"]["steps"], list)
        assert "budgets" in execute_payload["execution"]
        assert execute_payload["execution"]["budgets"]["step_total"] == 2
        assert execute_payload["execution"]["budgets"]["step_executed"] <= execute_payload["execution"]["budgets"]["step_total"]
        run_id = execute_payload["runId"]

        waited = client.post(
            "/api/control/run.wait",
            json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
        )
        assert waited.status_code == 200
        wait_payload = waited.json()
        assert wait_payload["status"] == "ok"
        assert "execute-this" in (wait_payload.get("final") or "")
    finally:
        if created_id:
            _ = client.delete(f"/api/custom-agents/{created_id}")


def test_control_workflows_execute_idempotency_replay_and_conflict(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": "done",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return "done"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent_registry["head-agent"], "run", fake_run)

    client = TestClient(app)
    created_id = None

    try:
        created = client.post(
            "/api/control/workflows.create",
            json={
                "name": f"Workflow Execute Idemp {uuid.uuid4().hex[:8]}",
                "base_agent_id": "head-agent",
                "steps": ["x"],
            },
        )
        assert created.status_code == 200
        created_id = created.json()["workflow"]["id"]

        first = client.post(
            "/api/control/workflows.execute",
            headers={"Idempotency-Key": "workflow-execute-key-1"},
            json={
                "workflow_id": created_id,
                "message": "same-message",
            },
        )
        assert first.status_code == 200
        first_payload = first.json()
        assert first_payload["idempotency"]["reused"] is False

        replay = client.post(
            "/api/control/workflows.execute",
            headers={"Idempotency-Key": "workflow-execute-key-1"},
            json={
                "workflow_id": created_id,
                "message": "same-message",
            },
        )
        assert replay.status_code == 200
        replay_payload = replay.json()
        assert replay_payload["runId"] == first_payload["runId"]
        assert replay_payload["idempotency"]["reused"] is True

        conflict = client.post(
            "/api/control/workflows.execute",
            headers={"Idempotency-Key": "workflow-execute-key-1"},
            json={
                "workflow_id": created_id,
                "message": "changed-message",
            },
        )
        assert conflict.status_code == 409
    finally:
        if created_id:
            _ = client.delete(f"/api/custom-agents/{created_id}")


def test_control_workflows_get_contract() -> None:
    client = TestClient(app)
    created_id = None

    try:
        created = client.post(
            "/api/control/workflows.create",
            json={
                "name": f"Workflow Get {uuid.uuid4().hex[:8]}",
                "base_agent_id": "head-agent",
                "description": "get contract",
                "steps": ["discover", "implement"],
            },
        )
        assert created.status_code == 200
        created_id = created.json()["workflow"]["id"]

        response = client.post(
            "/api/control/workflows.get",
            json={"workflow_id": created_id},
        )
        assert response.status_code == 200
        payload = response.json()

        assert payload["schema"] == "workflows.get.v1"
        assert payload["workflow"]["id"] == created_id
        assert payload["workflow"]["base_agent_id"] == "head-agent"
        assert payload["workflow"]["step_count"] == 2
    finally:
        if created_id:
            _ = client.delete(f"/api/custom-agents/{created_id}")


def test_control_workflows_get_rejects_unknown_id() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/control/workflows.get",
        json={"workflow_id": "does-not-exist"},
    )
    assert response.status_code == 404


def test_control_workflows_delete_contract() -> None:
    client = TestClient(app)

    created = client.post(
        "/api/control/workflows.create",
        json={
            "name": f"Workflow Delete {uuid.uuid4().hex[:8]}",
            "base_agent_id": "head-agent",
            "steps": ["cleanup"],
        },
    )
    assert created.status_code == 200
    created_id = created.json()["workflow"]["id"]

    deleted = client.post(
        "/api/control/workflows.delete",
        json={"workflow_id": created_id},
    )
    assert deleted.status_code == 200
    payload = deleted.json()
    assert payload["schema"] == "workflows.delete.v1"
    assert payload["status"] == "deleted"
    assert payload["workflow"]["id"] == created_id

    get_after = client.post(
        "/api/control/workflows.get",
        json={"workflow_id": created_id},
    )
    assert get_after.status_code == 404


def test_control_workflows_delete_idempotency_replay_and_conflict() -> None:
    client = TestClient(app)

    created = client.post(
        "/api/control/workflows.create",
        json={
            "name": f"Workflow Delete Idemp {uuid.uuid4().hex[:8]}",
            "base_agent_id": "head-agent",
            "steps": ["x"],
        },
    )
    assert created.status_code == 200
    created_id = created.json()["workflow"]["id"]

    first = client.post(
        "/api/control/workflows.delete",
        headers={"Idempotency-Key": "workflow-delete-key-1"},
        json={"workflow_id": created_id},
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["idempotency"]["reused"] is False

    replay = client.post(
        "/api/control/workflows.delete",
        headers={"Idempotency-Key": "workflow-delete-key-1"},
        json={"workflow_id": created_id},
    )
    assert replay.status_code == 200
    replay_payload = replay.json()
    assert replay_payload["workflow"]["id"] == created_id
    assert replay_payload["idempotency"]["reused"] is True

    other = client.post(
        "/api/control/workflows.create",
        json={
            "name": f"Workflow Delete Other {uuid.uuid4().hex[:8]}",
            "base_agent_id": "head-agent",
            "steps": ["y"],
        },
    )
    assert other.status_code == 200
    other_id = other.json()["workflow"]["id"]

    try:
        conflict = client.post(
            "/api/control/workflows.delete",
            headers={"Idempotency-Key": "workflow-delete-key-1"},
            json={"workflow_id": other_id},
        )
        assert conflict.status_code == 409
    finally:
        _ = client.delete(f"/api/custom-agents/{other_id}")


def test_control_tools_policy_preview_applies_preset_and_deny() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/control/tools.policy.preview",
        json={
            "agent_id": "head-agent",
            "preset": "research",
            "tool_policy": {
                "allow": ["web_fetch", "run_command"],
                "deny": ["grep_search"],
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["schema"] == "tools.policy.preview.v1"
    assert payload["agent_id"] == "head-agent"
    assert payload["preset"] == "research"
    assert "web_fetch" in payload["effective_allow"]
    assert "run_command" not in payload["effective_allow"]
    assert "run_command" in payload["effective_deny"]
    assert "grep_search" in payload["effective_deny"]
    conflict = payload["explain"]["conflict_resolution"]
    assert conflict["strategy"] == "deny_overrides_allow"
    assert "run_command" in conflict["conflicted_tools"]
    assert "run_command" not in conflict["effective_allow_after_conflicts"]
    assert "run_command" in conflict["effective_deny_after_conflicts"]


def test_control_tools_policy_preview_supports_profile_and_also_allow() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/control/tools.policy.preview",
        json={
            "agent_id": "head-agent",
            "profile": "minimal",
            "preset": "research",
            "tool_policy": {
                "allow": ["read_file"],
                "deny": [],
            },
            "also_allow": ["web_fetch", "run_command"],
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["schema"] == "tools.policy.preview.v1"
    assert payload["profile"] == "minimal"
    assert "read_file" in payload["effective_allow"]
    assert "web_fetch" in payload["effective_allow"]
    assert "run_command" not in payload["effective_allow"]
    assert "run_command" in payload["effective_deny"]


def test_control_tools_policy_preview_supports_provider_and_model_scopes() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/control/tools.policy.preview",
        json={
            "agent_id": "head-agent",
            "provider": "api",
            "model": "minimax-m2:cloud",
            "tool_policy": {
                "allow": ["start_background_command", "read_file"],
                "deny": [],
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["schema"] == "tools.policy.preview.v1"
    assert payload["provider"] == "api"
    assert payload["model"] == "minimax-m2:cloud"
    assert "start_background_command" in payload["effective_deny"]
    assert "start_background_command" not in payload["effective_allow"]
    assert "read_file" in payload["effective_allow"]
    assert payload["explain"]["order"] == [
        "global",
        "profile",
        "preset",
        "provider",
        "model",
        "agent_depth",
        "request",
    ]
    assert isinstance(payload["explain"].get("layers"), list)
    assert isinstance(payload["explain"].get("final_allow"), list)
    assert isinstance(payload["explain"].get("final_deny"), list)
    assert payload["explain"]["conflict_resolution"]["strategy"] == "deny_overrides_allow"


def test_control_tools_policy_preview_explain_is_deterministic() -> None:
    client = TestClient(app)

    body = {
        "agent_id": "head-agent",
        "profile": "minimal",
        "preset": "research",
        "provider": "api",
        "model": "minimax-m2:cloud",
        "tool_policy": {
            "allow": ["read_file", "web_fetch"],
            "deny": ["grep_search"],
        },
        "also_allow": ["web_fetch"],
    }

    first = client.post("/api/control/tools.policy.preview", json=body)
    second = client.post("/api/control/tools.policy.preview", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["explain"] == second_payload["explain"]


def test_control_tools_policy_preview_conflict_snapshot_payload() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/control/tools.policy.preview",
        json={
            "agent_id": "head-agent",
            "tool_policy": {
                "allow": ["read_file", "web_fetch"],
                "deny": ["grep_search", "web_fetch"],
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()

    explain = payload["explain"]
    assert explain["order"] == [
        "global",
        "profile",
        "preset",
        "provider",
        "model",
        "agent_depth",
        "request",
    ]
    assert explain["final_allow"] == ["read_file", "web_fetch"]
    assert explain["final_deny"] == ["grep_search", "web_fetch"]
    assert explain["conflict_resolution"] == {
        "strategy": "deny_overrides_allow",
        "conflicted_tools": ["web_fetch"],
        "effective_allow_after_conflicts": ["read_file"],
        "effective_deny_after_conflicts": ["grep_search", "web_fetch"],
    }

    layers = explain["layers"]
    layer_names = [item.get("layer") for item in layers]
    assert layer_names == [
        "global",
        "profile",
        "preset",
        "provider",
        "model",
        "agent_depth",
        "request",
    ]
    request_layer = next(item for item in layers if item.get("layer") == "request")
    assert request_layer["toolPolicy"] == {
        "allow": ["read_file", "web_fetch"],
        "deny": ["grep_search", "web_fetch"],
    }


def test_control_tools_policy_preview_layer_ids_and_scopes_are_stable() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/control/tools.policy.preview",
        json={
            "agent_id": "head-agent",
            "profile": "minimal",
            "preset": "research",
            "provider": "api",
            "model": "minimax-m2:cloud",
            "tool_policy": {
                "allow": ["read_file"],
                "deny": ["grep_search"],
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()

    layers = payload["explain"]["layers"]
    layer_by_name = {item["layer"]: item for item in layers}
    assert layer_by_name["profile"]["id"] == "minimal"
    assert layer_by_name["preset"]["id"] == "research"
    assert layer_by_name["provider"]["id"] == "api"
    assert layer_by_name["model"]["id"] == "minimax-m2:cloud"
    assert layer_by_name["agent_depth"]["id"] == "head-agent:0"
    assert layer_by_name["request"]["toolPolicy"] == {
        "allow": ["read_file"],
        "deny": ["grep_search"],
    }

    assert payload["scoped"]["provider"] == {
        "deny": ["start_background_command", "kill_background_process"],
    }
    assert payload["scoped"]["model"] == {
        "deny": ["start_background_command", "kill_background_process"],
    }


def test_control_tools_policy_preview_rejects_unknown_provider() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/control/tools.policy.preview",
        json={"agent_id": "head-agent", "provider": "unknown-provider"},
    )
    assert response.status_code == 400


def test_control_tools_policy_preview_rejects_unknown_agent() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/control/tools.policy.preview",
        json={"agent_id": "unknown-agent"},
    )
    assert response.status_code == 400


def test_lifecycle_emits_tool_policy_decision(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": "done",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return "done"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    start = client.post(
        "/api/control/run.start",
        json={
            "message": "policy-event",
            "preset": "research",
            "tool_policy": {
                "allow": ["web_fetch"],
                "deny": ["grep_search"],
            },
        },
    )
    assert start.status_code == 200
    run_id = start.json()["runId"]

    wait = client.post(
        "/api/control/run.wait",
        json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert wait.status_code == 200

    run_state = state_store.get_run(run_id)
    assert run_state is not None
    lifecycle_events = [event for event in run_state.get("events", []) if event.get("type") == "lifecycle"]
    policy_event = next((event for event in lifecycle_events if event.get("stage") == "tool_policy_decision"), None)

    assert policy_event is not None
    details = policy_event.get("details") or {}
    assert details.get("preset") == "research"
    assert "requested" in details
    assert "resolved" in details
    assert "web_fetch" in (details.get("resolved") or {}).get("allow", [])
    assert "grep_search" in (details.get("resolved") or {}).get("deny", [])


def test_lifecycle_emits_agent_depth_policy_applied(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": "done",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return "done"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    start = client.post(
        "/api/control/run.start",
        json={
            "message": "depth-policy-event",
            "tool_policy": {
                "allow": ["spawn_subrun", "read_file"],
            },
        },
    )
    assert start.status_code == 200
    run_id = start.json()["runId"]

    wait = client.post(
        "/api/control/run.wait",
        json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert wait.status_code == 200

    run_state = state_store.get_run(run_id)
    assert run_state is not None
    lifecycle_events = [event for event in run_state.get("events", []) if event.get("type") == "lifecycle"]
    depth_event = next((event for event in lifecycle_events if event.get("stage") == "agent_depth_policy_applied"), None)

    assert depth_event is not None
    details = depth_event.get("details") or {}
    assert details.get("depth") == 0
    assert details.get("agent_id") == "head-agent"
    assert "resolved" in details
    assert isinstance(details.get("depth_layer"), dict)


def test_control_runs_get_returns_run_summary(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": "summary",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return "summary"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    start = client.post(
        "/api/control/run.start",
        json={
            "session_id": "session-runs-get",
            "message": "Generate a concise project summary.",
        },
    )
    assert start.status_code == 200
    run_id = start.json()["runId"]

    wait = client.post(
        "/api/control/run.wait",
        json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert wait.status_code == 200

    get_response = client.post("/api/control/runs.get", json={"run_id": run_id})
    assert get_response.status_code == 200
    payload = get_response.json()

    assert payload["schema"] == "runs.get.v1"
    run = payload["run"]
    assert run["run_id"] == run_id
    assert run["session_id"] == "session-runs-get"
    assert run["status"] in {"completed", "error"}
    assert isinstance(run["event_count"], int)
    assert isinstance(run["lifecycle_count"], int)


def test_control_runs_get_unknown_run_returns_404() -> None:
    client = TestClient(app)

    response = client.post("/api/control/runs.get", json={"run_id": "missing-run"})
    assert response.status_code == 404


def test_control_runs_status_normalizes_failed_to_error(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def failing_run(user_message, send_event, session_id, request_id, model=None, tool_policy=None):
        raise RuntimeError("forced failure")

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", failing_run)

    client = TestClient(app)

    start = client.post(
        "/api/control/run.start",
        json={"session_id": "runs-status-map", "message": "fail me"},
    )
    assert start.status_code == 200
    run_id = start.json()["runId"]

    wait = client.post(
        "/api/control/run.wait",
        json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert wait.status_code == 200
    assert wait.json()["status"] == "error"
    assert wait.json()["runStatus"] == "error"

    get_response = client.post("/api/control/runs.get", json={"run_id": run_id})
    assert get_response.status_code == 200
    assert get_response.json()["run"]["status"] == "error"


def test_control_runs_list_returns_items(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": "listed",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return "listed"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    first = client.post(
        "/api/control/run.start",
        json={"session_id": "runs-list-a", "message": "first"},
    )
    assert first.status_code == 200
    second = client.post(
        "/api/control/run.start",
        json={"session_id": "runs-list-b", "message": "second"},
    )
    assert second.status_code == 200

    response = client.post("/api/control/runs.list", json={"limit": 10})
    assert response.status_code == 200
    payload = response.json()

    assert payload["schema"] == "runs.list.v1"
    assert isinstance(payload["items"], list)
    assert payload["count"] == len(payload["items"])
    assert any(item.get("run_id") == first.json()["runId"] for item in payload["items"])
    assert any(item.get("run_id") == second.json()["runId"] for item in payload["items"])


def test_control_runs_list_filters_by_session(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": "filtered",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return "filtered"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    included = client.post(
        "/api/control/run.start",
        json={"session_id": "runs-list-target", "message": "include"},
    )
    assert included.status_code == 200

    excluded = client.post(
        "/api/control/run.start",
        json={"session_id": "runs-list-other", "message": "exclude"},
    )
    assert excluded.status_code == 200

    response = client.post(
        "/api/control/runs.list",
        json={"session_id": "runs-list-target", "limit": 10},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["schema"] == "runs.list.v1"
    assert payload["count"] >= 1
    assert all(item.get("session_id") == "runs-list-target" for item in payload["items"])
    assert any(item.get("run_id") == included.json()["runId"] for item in payload["items"])
    assert not any(item.get("run_id") == excluded.json()["runId"] for item in payload["items"])


def test_control_runs_events_returns_items(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": "events",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return "events"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    start = client.post(
        "/api/control/run.start",
        json={"session_id": "runs-events", "message": "emit events"},
    )
    assert start.status_code == 200
    run_id = start.json()["runId"]

    wait = client.post(
        "/api/control/run.wait",
        json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert wait.status_code == 200

    response = client.post(
        "/api/control/runs.events",
        json={"run_id": run_id, "limit": 50},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["schema"] == "runs.events.v1"
    assert payload["run_id"] == run_id
    assert payload["count"] >= 1
    assert isinstance(payload["items"], list)
    assert any(event.get("type") == "final" for event in payload["items"])


def test_control_runs_events_unknown_run_returns_404() -> None:
    client = TestClient(app)

    response = client.post("/api/control/runs.events", json={"run_id": "missing-run"})
    assert response.status_code == 404


def test_control_runs_audit_returns_telemetry(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": "audit",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return "audit"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    start = client.post(
        "/api/control/run.start",
        json={"session_id": "runs-audit", "message": "collect audit"},
    )
    assert start.status_code == 200
    run_id = start.json()["runId"]

    wait = client.post(
        "/api/control/run.wait",
        json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert wait.status_code == 200

    response = client.post("/api/control/runs.audit", json={"run_id": run_id})
    assert response.status_code == 200
    payload = response.json()

    assert payload["schema"] == "runs.audit.v1"
    assert payload["run"]["run_id"] == run_id
    assert isinstance(payload["telemetry"]["event_count"], int)
    assert isinstance(payload["telemetry"]["lifecycle_count"], int)
    assert isinstance(payload["telemetry"]["lifecycle_stages"], dict)
    assert isinstance(payload["telemetry"]["guardrail_summary"], dict)
    assert isinstance(payload["telemetry"]["guardrail_summary"]["tool_audit"], dict)


def test_control_runs_audit_includes_blocked_with_reason_details(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "lifecycle",
                "stage": "tool_selection_empty",
                "request_id": request_id,
                "session_id": session_id,
                "details": {
                    "reason": "policy_block",
                    "blocked_with_reason": "run_command_not_allowed",
                },
            }
        )
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": "blocked",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return "blocked"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    start = client.post(
        "/api/control/run.start",
        json={"session_id": "runs-audit-blocked", "message": "run blocked command"},
    )
    assert start.status_code == 200
    run_id = start.json()["runId"]

    wait = client.post(
        "/api/control/run.wait",
        json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert wait.status_code == 200

    response = client.post("/api/control/runs.audit", json={"run_id": run_id})
    assert response.status_code == 200
    payload = response.json()

    telemetry = payload["telemetry"]
    assert telemetry["blocked_with_reason"].get("run_command_not_allowed", 0) >= 1
    assert telemetry["tool_selection_empty_reasons"].get("policy_block", 0) >= 1
    assert telemetry["guardrail_summary"]["loop_warn_count"] >= 0
    assert telemetry["guardrail_summary"]["loop_blocked_count"] >= 0
    assert telemetry["guardrail_summary"]["budget_exceeded_count"] >= 0


def test_control_runs_audit_guardrail_summary_from_tool_audit_event(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "lifecycle",
                "stage": "tool_audit_summary",
                "request_id": request_id,
                "session_id": session_id,
                "details": {
                    "tool_calls": 3,
                    "tool_errors": 1,
                    "loop_blocked": 1,
                    "budget_blocked": 2,
                    "elapsed_ms": 1234,
                    "call_cap": 8,
                    "time_cap_seconds": 90.0,
                    "loop_warn_threshold": 2,
                    "loop_critical_threshold": 3,
                },
            }
        )
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": "audit-summary",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return "audit-summary"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    start = client.post(
        "/api/control/run.start",
        json={"session_id": "runs-audit-summary", "message": "collect guardrail summary"},
    )
    assert start.status_code == 200
    run_id = start.json()["runId"]

    wait = client.post(
        "/api/control/run.wait",
        json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert wait.status_code == 200

    response = client.post("/api/control/runs.audit", json={"run_id": run_id})
    assert response.status_code == 200
    payload = response.json()

    guardrail = payload["telemetry"]["guardrail_summary"]
    assert guardrail["tool_audit"] == {
        "tool_calls": 3,
        "tool_errors": 1,
        "loop_blocked": 1,
        "budget_blocked": 2,
        "elapsed_ms": 1234,
        "call_cap": 8,
        "time_cap_seconds": 90.0,
        "loop_warn_threshold": 2,
        "loop_critical_threshold": 3,
    }


def test_control_runs_audit_unknown_run_returns_404() -> None:
    client = TestClient(app)

    response = client.post("/api/control/runs.audit", json={"run_id": "missing-run"})
    assert response.status_code == 404


def test_control_sessions_send_contract(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"echo:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    send = client.post(
        "/api/control/sessions.send",
        json={"session_id": "sess-send", "message": "hello"},
    )
    assert send.status_code == 200
    payload = send.json()
    assert payload["schema"] == "sessions.send.v1"
    assert payload["status"] == "accepted"
    assert payload["sessionId"] == "sess-send"
    assert payload["idempotency"]["reused"] is False

    run_id = payload["runId"]
    wait = client.post(
        "/api/control/run.wait",
        json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert wait.status_code == 200
    assert wait.json()["status"] == "ok"


def test_control_sessions_send_idempotency_replay_and_conflict(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"echo:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    first = client.post(
        "/api/control/sessions.send",
        headers={"Idempotency-Key": "sess-send-key-1"},
        json={"session_id": "sess-send-idem", "message": "same"},
    )
    assert first.status_code == 200

    replay = client.post(
        "/api/control/sessions.send",
        headers={"Idempotency-Key": "sess-send-key-1"},
        json={"session_id": "sess-send-idem", "message": "same"},
    )
    assert replay.status_code == 200
    assert replay.json()["schema"] == "sessions.send.v1"
    assert replay.json()["idempotency"]["reused"] is True
    assert replay.json()["runId"] == first.json()["runId"]

    conflict = client.post(
        "/api/control/sessions.send",
        headers={"Idempotency-Key": "sess-send-key-1"},
        json={"session_id": "sess-send-idem", "message": "changed"},
    )
    assert conflict.status_code == 409


def test_control_sessions_spawn_contract(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"echo:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    spawn = client.post(
        "/api/control/sessions.spawn",
        json={"parent_session_id": "parent-sess", "message": "spawn now"},
    )
    assert spawn.status_code == 200
    payload = spawn.json()

    assert payload["schema"] == "sessions.spawn.v1"
    assert payload["status"] == "accepted"
    assert payload["parentSessionId"] == "parent-sess"
    assert payload["sessionId"] != "parent-sess"
    assert payload["idempotency"]["reused"] is False

    run_id = payload["runId"]
    run_state = state_store.get_run(run_id)
    assert run_state is not None
    assert (run_state.get("meta") or {}).get("parent_session_id") == "parent-sess"

    wait = client.post(
        "/api/control/run.wait",
        json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert wait.status_code == 200
    assert wait.json()["status"] == "ok"


def test_control_sessions_spawn_idempotency_replay_and_conflict(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"echo:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    first = client.post(
        "/api/control/sessions.spawn",
        headers={"Idempotency-Key": "sess-spawn-key-1"},
        json={"parent_session_id": "parent-idem", "message": "same"},
    )
    assert first.status_code == 200

    replay = client.post(
        "/api/control/sessions.spawn",
        headers={"Idempotency-Key": "sess-spawn-key-1"},
        json={"parent_session_id": "parent-idem", "message": "same"},
    )
    assert replay.status_code == 200
    assert replay.json()["schema"] == "sessions.spawn.v1"
    assert replay.json()["idempotency"]["reused"] is True
    assert replay.json()["runId"] == first.json()["runId"]
    assert replay.json()["sessionId"] == first.json()["sessionId"]

    conflict = client.post(
        "/api/control/sessions.spawn",
        headers={"Idempotency-Key": "sess-spawn-key-1"},
        json={"parent_session_id": "parent-idem", "message": "changed"},
    )
    assert conflict.status_code == 409


def test_control_sessions_status_returns_session_state(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"echo:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    start = client.post(
        "/api/control/sessions.send",
        json={"session_id": "sess-status", "message": "status me"},
    )
    assert start.status_code == 200
    run_id = start.json()["runId"]

    wait = client.post(
        "/api/control/run.wait",
        json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert wait.status_code == 200

    status_response = client.post("/api/control/sessions.status", json={"session_id": "sess-status"})
    assert status_response.status_code == 200
    payload = status_response.json()

    assert payload["schema"] == "sessions.status.v1"
    session = payload["session"]
    assert session["session_id"] == "sess-status"
    assert session["latest_run_id"] == run_id
    assert session["runs_count"] >= 1
    assert session["active_runs_count"] == 0
    assert session["latest_final"] == "echo:status me"


def test_control_sessions_status_unknown_session_returns_404() -> None:
    client = TestClient(app)

    response = client.post("/api/control/sessions.status", json={"session_id": "unknown-session"})
    assert response.status_code == 404


def test_control_sessions_get_returns_session_state(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"echo:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    start = client.post(
        "/api/control/sessions.send",
        json={"session_id": "sess-get", "message": "status me"},
    )
    assert start.status_code == 200
    run_id = start.json()["runId"]

    wait = client.post(
        "/api/control/run.wait",
        json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert wait.status_code == 200

    get_response = client.post("/api/control/sessions.get", json={"session_id": "sess-get"})
    assert get_response.status_code == 200
    payload = get_response.json()

    assert payload["schema"] == "sessions.get.v1"
    session = payload["session"]
    assert session["session_id"] == "sess-get"
    assert session["latest_run_id"] == run_id
    assert session["runs_count"] >= 1
    assert session["latest_final"] == "echo:status me"


def test_control_sessions_get_unknown_session_returns_404() -> None:
    client = TestClient(app)

    response = client.post("/api/control/sessions.get", json={"session_id": "unknown-session"})
    assert response.status_code == 404


def test_control_sessions_patch_updates_latest_run_meta(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"echo:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    start = client.post(
        "/api/control/sessions.send",
        json={"session_id": "sess-patch", "message": "prepare patch"},
    )
    assert start.status_code == 200
    run_id = start.json()["runId"]

    wait = client.post(
        "/api/control/run.wait",
        json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert wait.status_code == 200

    patch_response = client.post(
        "/api/control/sessions.patch",
        json={"session_id": "sess-patch", "meta": {"title": "Session A", "owner": "team-x"}},
    )
    assert patch_response.status_code == 200
    payload = patch_response.json()

    assert payload["schema"] == "sessions.patch.v1"
    assert payload["session"]["session_id"] == "sess-patch"
    assert payload["session"]["latest_run_id"] == run_id
    assert payload["session"]["meta"]["title"] == "Session A"
    assert payload["session"]["meta"]["owner"] == "team-x"
    assert payload["idempotency"]["reused"] is False


def test_control_sessions_patch_idempotency_replay_and_conflict(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"echo:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)
    seed = client.post(
        "/api/control/sessions.send",
        json={"session_id": "sess-patch-idem", "message": "seed"},
    )
    assert seed.status_code == 200

    first = client.post(
        "/api/control/sessions.patch",
        headers={"Idempotency-Key": "sess-patch-key-1"},
        json={"session_id": "sess-patch-idem", "meta": {"title": "T1"}},
    )
    assert first.status_code == 200

    replay = client.post(
        "/api/control/sessions.patch",
        headers={"Idempotency-Key": "sess-patch-key-1"},
        json={"session_id": "sess-patch-idem", "meta": {"title": "T1"}},
    )
    assert replay.status_code == 200
    assert replay.json()["schema"] == "sessions.patch.v1"
    assert replay.json()["idempotency"]["reused"] is True

    conflict = client.post(
        "/api/control/sessions.patch",
        headers={"Idempotency-Key": "sess-patch-key-1"},
        json={"session_id": "sess-patch-idem", "meta": {"title": "T2"}},
    )
    assert conflict.status_code == 409


def test_control_sessions_patch_unknown_session_returns_404() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/control/sessions.patch",
        json={"session_id": "missing-session", "meta": {"title": "x"}},
    )
    assert response.status_code == 404


def test_control_sessions_reset_clears_latest_run_meta(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"echo:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    start = client.post(
        "/api/control/sessions.send",
        json={"session_id": "sess-reset", "message": "prepare reset"},
    )
    assert start.status_code == 200
    run_id = start.json()["runId"]

    wait = client.post(
        "/api/control/run.wait",
        json={"run_id": run_id, "timeout_ms": 3000, "poll_interval_ms": 50},
    )
    assert wait.status_code == 200

    patched = client.post(
        "/api/control/sessions.patch",
        json={"session_id": "sess-reset", "meta": {"title": "to-be-cleared", "owner": "ops"}},
    )
    assert patched.status_code == 200
    assert patched.json()["session"]["meta"]["title"] == "to-be-cleared"

    reset = client.post(
        "/api/control/sessions.reset",
        json={"session_id": "sess-reset"},
    )
    assert reset.status_code == 200
    payload = reset.json()
    assert payload["schema"] == "sessions.reset.v1"
    assert payload["session"]["session_id"] == "sess-reset"
    assert payload["session"]["latest_run_id"] == run_id
    assert payload["session"]["meta"] == {}
    assert payload["idempotency"]["reused"] is False


def test_control_sessions_reset_idempotency_replay_and_conflict(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"echo:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)
    seed = client.post(
        "/api/control/sessions.send",
        json={"session_id": "sess-reset-idem", "message": "seed"},
    )
    assert seed.status_code == 200

    first = client.post(
        "/api/control/sessions.reset",
        headers={"Idempotency-Key": "sess-reset-key-1"},
        json={"session_id": "sess-reset-idem"},
    )
    assert first.status_code == 200

    replay = client.post(
        "/api/control/sessions.reset",
        headers={"Idempotency-Key": "sess-reset-key-1"},
        json={"session_id": "sess-reset-idem"},
    )
    assert replay.status_code == 200
    assert replay.json()["schema"] == "sessions.reset.v1"
    assert replay.json()["idempotency"]["reused"] is True

    conflict = client.post(
        "/api/control/sessions.reset",
        headers={"Idempotency-Key": "sess-reset-key-1"},
        json={"session_id": "sess-reset-idem-other"},
    )
    assert conflict.status_code == 409


def test_control_sessions_reset_unknown_session_returns_404() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/control/sessions.reset",
        json={"session_id": "missing-session"},
    )
    assert response.status_code == 404
