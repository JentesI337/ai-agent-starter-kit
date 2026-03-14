"""Recipe API router — CRUD + validation + run listing endpoints.

Coexists with the old workflow router during migration.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import Awaitable, Callable

import hashlib
import hmac as hmac_mod

from fastapi import APIRouter, Body, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

JsonDict = dict
logger = logging.getLogger(__name__)


def _maybe_await(result):
    if inspect.isawaitable(result):
        return result
    return None


def build_control_recipes_router(
    *,
    recipes_list_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    recipes_get_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    recipes_create_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    recipes_update_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    recipes_delete_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    recipes_validate_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    recipes_execute_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    recipes_resume_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    recipes_migrate_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/control/recipes.list")
    async def control_recipes_list(request: JsonDict = Body(...)):
        result = recipes_list_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/recipes.get")
    async def control_recipes_get(request: JsonDict = Body(...)):
        result = recipes_get_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/recipes.create")
    async def control_recipes_create(request: JsonDict = Body(...)):
        result = recipes_create_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/recipes.update")
    async def control_recipes_update(request: JsonDict = Body(...)):
        result = recipes_update_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/recipes.delete")
    async def control_recipes_delete(request: JsonDict = Body(...)):
        result = recipes_delete_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/recipes.validate")
    async def control_recipes_validate(request: JsonDict = Body(...)):
        result = recipes_validate_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/recipes.execute")
    async def control_recipes_execute(request: JsonDict = Body(...)):
        if recipes_execute_handler is None:
            return {"error": "Recipe execution not configured"}
        result = recipes_execute_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    # ── Resume endpoints ──────────────────────────────

    @router.post("/api/control/recipes.runs.resume")
    async def control_recipes_runs_resume(request: JsonDict = Body(...)):
        if recipes_resume_handler is None:
            return {"error": "Recipe resume not configured"}
        result = recipes_resume_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/recipes.runs.webhook/{run_id}")
    async def control_recipes_runs_webhook_resume(
        run_id: str,
        raw_request: Request,
        x_webhook_signature: str | None = Header(default=None, alias="X-Webhook-Signature"),
    ):
        """External webhook endpoint to resume a paused recipe run."""
        try:
            body = await raw_request.body()
        except Exception:
            body = b""

        try:
            from app.workflows.recipe_store import get_recipe_run_store
            store = get_recipe_run_store()
        except RuntimeError:
            raise HTTPException(status_code=503, detail="Recipe system not ready") from None

        state = store.get_by_run_id(run_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Run not found")
        if state.status != "paused":
            raise HTTPException(status_code=409, detail=f"Run is not paused (status={state.status})")
        if state.pause_reason not in ("webhook", "human_approval"):
            raise HTTPException(status_code=400, detail=f"Run pause reason '{state.pause_reason}' does not support webhook resume")

        # Validate HMAC signature if webhook_secret is set
        pause_data = state.pause_data or {}
        secret = pause_data.get("webhook_secret")
        if secret:
            if not x_webhook_signature:
                raise HTTPException(status_code=401, detail="Webhook signature required")
            expected = hmac_mod.new(
                secret.encode(), body, hashlib.sha256
            ).hexdigest()
            sig = x_webhook_signature.removeprefix("sha256=")
            if not hmac_mod.compare_digest(sig, expected):
                raise HTTPException(status_code=401, detail="Invalid webhook signature")

        # Parse body as JSON
        try:
            payload = json.loads(body) if body else {}
        except (json.JSONDecodeError, ValueError):
            payload = {"raw": body.decode("utf-8", errors="replace")}

        if recipes_resume_handler is None:
            raise HTTPException(status_code=500, detail="Recipe resume not configured")

        result = recipes_resume_handler({"run_id": run_id, "resume_data": payload})
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    # ── Recipe Runs: list + get + SSE stream ──────────

    @router.post("/api/control/recipes.runs.list")
    async def control_recipes_runs_list(request: JsonDict = Body(...)):
        try:
            from app.workflows.recipe_store import get_recipe_run_store
            store = get_recipe_run_store()
        except RuntimeError:
            return {"schema": "recipes.runs.list.v1", "items": [], "count": 0}

        recipe_id = request.get("recipe_id", "")
        limit = min(int(request.get("limit", 50)), 200)
        runs = store.list_runs(recipe_id, limit=limit)
        return {"schema": "recipes.runs.list.v1", "items": runs, "count": len(runs)}

    @router.post("/api/control/recipes.runs.get")
    async def control_recipes_runs_get(request: JsonDict = Body(...)):
        try:
            from app.workflows.recipe_store import get_recipe_run_store
            store = get_recipe_run_store()
        except RuntimeError:
            return {"error": "Recipe run store not initialized"}

        recipe_id = request.get("recipe_id", "")
        run_id = request.get("run_id", "")
        state = store.get(recipe_id, run_id)
        if state is None:
            return {"error": "Run not found"}
        return {
            "schema": "recipes.runs.get.v1",
            "run": state.model_dump(mode="json"),
        }

    @router.get("/api/control/recipes.execute.stream")
    async def control_recipes_execute_stream(
        run_id: str = Query(...),
    ):
        """SSE endpoint for real-time recipe execution progress."""
        try:
            from app.workflows.recipe_store import get_recipe_run_store
            store = get_recipe_run_store()
        except RuntimeError:
            async def _error():
                yield f"data: {json.dumps({'type': 'error', 'message': 'Recipe run store not initialized'})}\n\n"
            return StreamingResponse(_error(), media_type="text/event-stream")

        queue = store.subscribe(run_id)

        async def event_stream():
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    except TimeoutError:
                        yield ": keepalive\n\n"
                        continue

                    event_type = event.get("type", "message")
                    yield f"event: {event_type}\ndata: {json.dumps(event, default=str)}\n\n"

                    if event_type in ("recipe_completed", "recipe_failed"):
                        break
            finally:
                store.unsubscribe(run_id, queue)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # ── Migration ──────────────────────────────────

    @router.post("/api/control/recipes.migrate")
    async def control_recipes_migrate(request: JsonDict = Body(...)):
        if recipes_migrate_handler is None:
            return {"error": "Migration handler not configured"}
        result = recipes_migrate_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
