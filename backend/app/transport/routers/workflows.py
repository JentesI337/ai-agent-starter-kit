from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import StreamingResponse

JsonDict = dict
logger = logging.getLogger(__name__)


def _maybe_await(result):
    if inspect.isawaitable(result):
        return result
    return None


def build_control_workflows_router(
    *,
    workflows_list_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    workflows_get_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    workflows_create_handler: Callable[[JsonDict, str | None], JsonDict | Awaitable[JsonDict]],
    workflows_update_handler: Callable[[JsonDict, str | None], JsonDict | Awaitable[JsonDict]],
    workflows_execute_handler: Callable[[JsonDict, str | None], JsonDict | Awaitable[JsonDict]],
    workflows_delete_handler: Callable[[JsonDict, str | None], JsonDict | Awaitable[JsonDict]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/control/workflows.list")
    async def control_workflows_list(request: JsonDict = Body(...)):
        result = workflows_list_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/workflows.get")
    async def control_workflows_get(request: JsonDict = Body(...)):
        result = workflows_get_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/workflows.create")
    async def control_workflows_create(
        request: JsonDict = Body(...),
        idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        result = workflows_create_handler(request, idempotency_key_header)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/workflows.update")
    async def control_workflows_update(
        request: JsonDict = Body(...),
        idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        result = workflows_update_handler(request, idempotency_key_header)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/workflows.execute")
    async def control_workflows_execute(
        request: JsonDict = Body(...),
        idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        result = workflows_execute_handler(request, idempotency_key_header)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/workflows.delete")
    async def control_workflows_delete(
        request: JsonDict = Body(...),
        idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        result = workflows_delete_handler(request, idempotency_key_header)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    # ── Contracts + Validation ──────────────────────────

    @router.post("/api/control/workflows.contracts")
    async def control_workflows_contracts():
        """Return node contracts registry."""
        from app.workflows.handlers import api_control_workflows_contracts
        return api_control_workflows_contracts()

    @router.post("/api/control/workflows.validate")
    async def control_workflows_validate(request: JsonDict = Body(...)):
        """Validate a workflow graph and return resolved chain + warnings."""
        from app.workflows.handlers import api_control_workflows_validate
        return api_control_workflows_validate(request_data=request)

    # ── Workflow Runs: list + get + SSE stream ──────────

    @router.post("/api/control/workflows.runs.list")
    async def control_workflows_runs_list(request: JsonDict = Body(...)):
        try:
            from app.workflows.store import get_workflow_run_store
            store = get_workflow_run_store()
        except RuntimeError:
            return {"schema": "workflows.runs.list.v1", "items": [], "count": 0}

        workflow_id = request.get("workflow_id", "")
        limit = min(int(request.get("limit", 50)), 200)
        runs = store.list_runs(workflow_id, limit=limit)
        return {"schema": "workflows.runs.list.v1", "items": runs, "count": len(runs)}

    @router.post("/api/control/workflows.runs.get")
    async def control_workflows_runs_get(request: JsonDict = Body(...)):
        try:
            from app.workflows.store import get_workflow_run_store
            store = get_workflow_run_store()
        except RuntimeError:
            return {"error": "Run store not initialized"}

        workflow_id = request.get("workflow_id", "")
        run_id = request.get("run_id", "")
        state = store.get(workflow_id, run_id)
        if state is None:
            return {"error": "Run not found"}
        return {
            "schema": "workflows.runs.get.v1",
            "run": state.model_dump(mode="json"),
        }

    @router.get("/api/control/workflows.execute.stream")
    async def control_workflows_execute_stream(
        run_id: str = Query(...),
    ):
        """SSE endpoint for real-time workflow step progress."""
        try:
            from app.workflows.store import get_workflow_run_store
            store = get_workflow_run_store()
        except RuntimeError:
            async def _error():
                yield f"data: {json.dumps({'type': 'error', 'message': 'Run store not initialized'})}\n\n"
            return StreamingResponse(_error(), media_type="text/event-stream")

        queue = store.subscribe(run_id)

        async def event_stream():
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue

                    event_type = event.get("type", "message")
                    yield f"event: {event_type}\ndata: {json.dumps(event, default=str)}\n\n"

                    if event_type in ("workflow_completed", "workflow_failed"):
                        break
            finally:
                store.unsubscribe(run_id, queue)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # ── Workflow Run Audit ──────────────────────────────────

    @router.post("/api/control/workflows.runs.audit")
    async def control_workflows_runs_audit(request: JsonDict = Body(...)):
        """Return the audit trail for a workflow run."""
        from app.workflows.handlers import api_control_workflows_run_audit
        run_id = request.get("run_id", "")
        if not run_id:
            return {"error": "run_id is required"}
        result = api_control_workflows_run_audit(run_id)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    # ── Template endpoints ────────────────────────────────

    @router.post("/api/control/workflows.templates.list")
    async def workflow_templates_list():
        """Return all available workflow templates."""
        from pathlib import Path as _Path
        import json as _json

        templates_dir = _Path(__file__).resolve().parent.parent.parent / "workflow_templates"
        items = []
        if templates_dir.is_dir():
            for f in sorted(templates_dir.glob("*.json")):
                try:
                    data = _json.loads(f.read_text(encoding="utf-8"))
                    items.append({
                        "id": data.get("id", f.stem),
                        "name": data.get("name", f.stem),
                        "description": data.get("description", ""),
                        "category": data.get("category", "general"),
                        "required_connectors": data.get("required_connectors", []),
                        "step_count": data.get("step_count", len(data.get("steps", []))),
                    })
                except Exception:
                    logger.debug("template_load_failed file=%s", f.name, exc_info=True)
        return {"schema": "workflows.templates.list.v1", "items": items, "count": len(items)}

    @router.post("/api/control/workflows.templates.instantiate")
    async def workflow_templates_instantiate(
        body: dict = Body(...),
        x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    ):
        """Create a workflow from a template."""
        from pathlib import Path as _Path
        import json as _json

        template_id = body.get("template_id", "")
        overrides = body.get("overrides", {})

        templates_dir = _Path(__file__).resolve().parent.parent.parent / "workflow_templates"
        template_file = templates_dir / f"{template_id}.json"
        if not template_file.is_file():
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

        data = _json.loads(template_file.read_text(encoding="utf-8"))

        create_payload = {
            "name": overrides.get("name", data.get("name", template_id)),
            "description": overrides.get("description", data.get("description", "")),
            "base_agent_id": overrides.get("base_agent_id", data.get("base_agent_id", "head-agent")),
            "steps": data.get("steps", []),
            "execution_mode": data.get("execution_mode", "sequential"),
            "triggers": data.get("triggers", []),
        }

        result = workflows_create_handler(create_payload, x_idempotency_key)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
