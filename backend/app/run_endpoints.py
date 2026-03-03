from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from app.errors import GuardrailViolation, LlmClientError, RuntimeSwitchError, ToolExecutionError
from app.interfaces import RequestContext
from app.config import settings
from app.services.request_normalization import normalize_prompt_mode, normalize_queue_mode
from app.tool_policy import ToolPolicyDict
from app.tool_policy import tool_policy_to_dict


@dataclass(frozen=True)
class AgentTestDependencies:
    logger: logging.Logger
    runtime_manager: Any
    state_store: Any
    agent: Any
    orchestrator_api: Any
    normalize_preset: Callable[[str | None], str]
    extract_also_allow: Callable[[ToolPolicyDict | None], list[str] | None]
    effective_orchestrator_agent_ids: Callable[[], list[str] | set[str] | tuple[str, ...]]
    mark_completed: Callable[[str], None]
    mark_failed: Callable[[str, str], None]
    primary_agent_id: str


@dataclass(frozen=True)
class RunEndpointsDependencies:
    start_run_background: Callable[..., str]
    wait_for_run_result: Callable[..., Awaitable[dict]]


async def run_agent_test(request: Any, deps: AgentTestDependencies) -> dict:
    runtime_state = deps.runtime_manager.get_state()
    session_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    events: list[dict] = []
    deps.logger.info(
        "agent_test_start request_id=%s session_id=%s runtime=%s model=%s message_len=%s",
        request_id,
        session_id,
        runtime_state.runtime,
        request.model or runtime_state.model,
        len(request.message or ""),
    )
    deps.state_store.init_run(
        run_id=request_id,
        session_id=session_id,
        request_id=request_id,
        user_message=request.message or "",
        runtime=runtime_state.runtime,
        model=request.model or runtime_state.model,
    )
    deps.state_store.set_task_status(run_id=request_id, task_id="request", label="request", status="active")

    async def collect_event(payload: dict):
        events.append(payload)

    deps.agent.configure_runtime(
        base_url=runtime_state.base_url,
        model=runtime_state.model,
    )

    selected_model = (request.model or "").strip() or runtime_state.model
    if runtime_state.runtime == "local":
        selected_model = await deps.runtime_manager.ensure_model_ready(collect_event, session_id, selected_model)
    else:
        selected_model = await deps.runtime_manager.resolve_api_request_model(selected_model)

    normalized_tool_policy = tool_policy_to_dict(getattr(request, "tool_policy", None), include_also_allow=True)

    try:
        applied_preset = deps.normalize_preset(request.preset)
        await deps.orchestrator_api.run_user_message(
            user_message=request.message,
            send_event=collect_event,
            request_context=RequestContext(
                session_id=session_id,
                request_id=request_id,
                runtime=runtime_state.runtime,
                model=selected_model,
                tool_policy=normalized_tool_policy,
                also_allow=deps.extract_also_allow(normalized_tool_policy),
                agent_id=deps.primary_agent_id,
                depth=0,
                preset=applied_preset,
                orchestrator_agent_ids=sorted(deps.effective_orchestrator_agent_ids()),
                queue_mode=normalize_queue_mode(
                    getattr(request, "queue_mode", None),
                    default=settings.queue_mode_default,
                ),
                prompt_mode=normalize_prompt_mode(
                    getattr(request, "prompt_mode", None),
                    default=settings.prompt_mode_default,
                ),
            ),
        )
        deps.mark_completed(run_id=request_id)
    except (GuardrailViolation, ToolExecutionError, RuntimeSwitchError) as exc:
        deps.mark_failed(run_id=request_id, error=str(exc))
        deps.logger.warning(
            "agent_test_client_error request_id=%s session_id=%s error=%s",
            request_id,
            session_id,
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LlmClientError as exc:
        deps.mark_failed(run_id=request_id, error=str(exc))
        deps.logger.warning(
            "agent_test_llm_error request_id=%s session_id=%s error=%s",
            request_id,
            session_id,
            exc,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        deps.mark_failed(run_id=request_id, error=str(exc))
        deps.logger.exception(
            "agent_test_unhandled request_id=%s session_id=%s",
            request_id,
            session_id,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    final_event = next((item for item in reversed(events) if item.get("type") == "final"), None)
    return {
        "ok": True,
        "runtime": runtime_state.runtime,
        "model": selected_model,
        "preset": applied_preset,
        "sessionId": session_id,
        "requestId": request_id,
        "eventCount": len(events),
        "final": final_event.get("message") if final_event else None,
    }


def start_run(request: Any, deps: RunEndpointsDependencies) -> dict:
    session_id = request.session_id or str(uuid.uuid4())
    normalized_tool_policy = tool_policy_to_dict(getattr(request, "tool_policy", None), include_also_allow=True)
    run_id = deps.start_run_background(
        agent_id=None,
        message=request.message,
        session_id=session_id,
        model=request.model,
        preset=request.preset,
        queue_mode=getattr(request, "queue_mode", None),
        prompt_mode=getattr(request, "prompt_mode", None),
        tool_policy=normalized_tool_policy,
    )

    return {
        "status": "accepted",
        "runId": run_id,
        "sessionId": session_id,
    }


async def wait_run(
    run_id: str,
    timeout_ms: int | None,
    poll_interval_ms: int | None,
    deps: RunEndpointsDependencies,
) -> dict:
    return await deps.wait_for_run_result(
        run_id,
        timeout_ms=timeout_ms,
        poll_interval_ms=poll_interval_ms,
    )