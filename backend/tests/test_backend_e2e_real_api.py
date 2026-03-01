from __future__ import annotations

import os
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, runtime_manager
from app.runtime_manager import RuntimeState


def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _is_native_ollama_api(base_url: str) -> bool:
    return base_url.lower().rstrip("/").endswith("/api")


def _upstream_is_transient(text: str) -> bool:
    lowered = (text or "").lower()
    markers = (
        "timeout",
        "timed out",
        "connection",
        "connect",
        "network",
        "429",
        "rate limit",
        "temporary",
        "unavailable",
        "gateway",
    )
    return any(marker in lowered for marker in markers)


def _ensure_real_api_available() -> dict[str, Any]:
    if _env_flag("SKIP_REAL_OLLAMA_API_E2E", "0"):
        pytest.skip("Real API E2E skipped by SKIP_REAL_OLLAMA_API_E2E=1.")

    base_url = (os.getenv("OLLAMA_CLOUD_API_BASE_URL") or os.getenv("API_BASE_URL") or "http://localhost:11434/api").rstrip("/")
    list_url = f"{base_url}/tags" if _is_native_ollama_api(base_url) else f"{base_url}/models"

    try:
        with httpx.Client(timeout=8) as client:
            response = client.get(list_url)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise AssertionError(f"Real API unreachable or model listing failed: {exc}") from exc

    models: list[str] = []
    if _is_native_ollama_api(base_url):
        data = payload.get("models") if isinstance(payload, dict) else None
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    name = item.get("name")
                    if isinstance(name, str) and name.strip():
                        models.append(name.strip())
    else:
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    name = item.get("id")
                    if isinstance(name, str) and name.strip():
                        models.append(name.strip())

    if not models:
        raise AssertionError("Real API reachable, but no models reported.")

    return {
        "base_url": base_url,
        "models": set(models),
        "small_model": os.getenv("OLLAMA_CLOUD_MODEL_SMALL", "minimax-m2:cloud").strip(),
        "large_model": os.getenv("OLLAMA_CLOUD_MODEL_LARGE", "qwen3-coder:480b-cloud").strip(),
    }


def _require_model_available(api_ctx: dict[str, Any], model_name: str) -> None:
    if model_name not in api_ctx["models"]:
        available = ", ".join(sorted(api_ctx["models"]))
        raise AssertionError(
            f"Model '{model_name}' not available on API endpoint {api_ctx['base_url']}. Available: {available}"
        )


@pytest.mark.parametrize(
    "model_kind",
    ["small_model", "large_model"],
)
def test_real_api_orchestration_smoke_for_small_and_large_models(model_kind: str) -> None:
    api_ctx = _ensure_real_api_available()
    model_name = api_ctx[model_kind]
    _require_model_available(api_ctx, model_name)

    previous_state = runtime_manager.get_state()
    runtime_manager._state = RuntimeState(runtime="api", base_url=api_ctx["base_url"], model=model_name)

    client = TestClient(app)
    try:
        response = client.post(
            "/api/test/agent",
            json={
                "message": "Antworte exakt mit OK.",
                "model": model_name,
            },
        )

        if response.status_code >= 500 and _upstream_is_transient(response.text):
            raise AssertionError(
                f"Transient upstream/API failure during strict real API test: {response.status_code} {response.text[:200]}"
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["runtime"] == "api"
        assert payload["model"] == model_name
        assert isinstance(payload.get("eventCount"), int)
        assert payload["eventCount"] > 0
        assert isinstance(payload.get("final"), str)
        assert payload["final"].strip() != ""
    finally:
        runtime_manager._state = previous_state


def test_real_api_subrun_spawn_and_agent_workflow_smoke() -> None:
    api_ctx = _ensure_real_api_available()
    model_name = api_ctx["small_model"]
    _require_model_available(api_ctx, model_name)

    previous_state = runtime_manager.get_state()
    runtime_manager._state = RuntimeState(runtime="api", base_url=api_ctx["base_url"], model=model_name)

    client = TestClient(app)
    try:
        run_id: str | None = None
        parent_session_id: str | None = None

        with client.websocket_connect("/ws/agent") as ws:
            _ = ws.receive_json()
            ws.send_json(
                {
                    "type": "subrun_spawn",
                    "content": "Erledige eine Mini-Aufgabe und antworte kurz mit OK.",
                    "agent_id": "coder-agent",
                    "model": model_name,
                }
            )

            for _ in range(40):
                envelope = ws.receive_json()
                event = envelope.get("event", {})
                if event.get("type") == "subrun_status" and event.get("status") == "accepted":
                    run_id = event.get("run_id")
                    parent_session_id = event.get("parent_session_id")
                    break

        assert run_id
        assert parent_session_id

        wait = client.get(
            f"/api/runs/{run_id}/wait",
            params={
                "timeout_ms": int(os.getenv("REAL_API_E2E_WAIT_TIMEOUT_MS", "120000")),
                "poll_interval_ms": 300,
            },
        )

        assert wait.status_code == 200
        wait_payload = wait.json()

        if wait_payload.get("status") == "timeout":
            raise AssertionError("Subrun did not finish in time (timeout).")

        run_status = wait_payload.get("runStatus")
        assert run_status in {"completed", "failed"}

        log_response = client.get(
            f"/api/subruns/{run_id}/log",
            params={"requester_session_id": parent_session_id, "visibility_scope": "tree"},
        )
        assert log_response.status_code == 200
        events = log_response.json().get("events", [])
        assert isinstance(events, list)
        assert len(events) > 0

        event_types = {
            str(item.get("type", "")).strip().lower()
            for item in events
            if isinstance(item, dict)
        }
        assert any(t for t in event_types)

        if run_status == "completed":
            final_text = wait_payload.get("final")
            assert isinstance(final_text, str)
            assert final_text.strip() != ""
        else:
            error_text = str(wait_payload.get("error", ""))
            if error_text:
                assert not _upstream_is_transient(error_text)
    finally:
        runtime_manager._state = previous_state
