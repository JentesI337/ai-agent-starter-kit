"""Webhook trigger endpoint for workflows."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid

from fastapi import APIRouter, Header, HTTPException, Request

logger = logging.getLogger(__name__)


def build_webhooks_router() -> APIRouter:
    router = APIRouter()

    @router.post("/api/webhooks/{workflow_id}")
    async def webhook_trigger(
        workflow_id: str,
        request: Request,
        x_webhook_signature: str | None = Header(default=None, alias="X-Webhook-Signature"),
    ):
        """Receive a webhook and trigger the corresponding workflow."""
        try:
            body = await request.body()
        except Exception:
            body = b""

        # Look up the workflow
        try:
            from app.handlers import workflow_handlers
            deps = workflow_handlers._require_deps()
        except RuntimeError:
            raise HTTPException(status_code=503, detail="Workflow system not ready")

        deps.sync_custom_agents()
        normalized_id = deps.normalize_agent_id(workflow_id)
        workflow = next(
            (item for item in deps.custom_agent_store.list()
             if deps.normalize_agent_id(item.id) == normalized_id),
            None,
        )
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow not found")

        # Check for webhook trigger and validate signature
        triggers = getattr(workflow, "triggers", []) or []
        webhook_trigger = None
        for t in triggers:
            trigger_type = t.get("type") if isinstance(t, dict) else getattr(t, "type", None)
            if trigger_type == "webhook":
                webhook_trigger = t
                break

        if webhook_trigger is None:
            raise HTTPException(status_code=404, detail="No webhook trigger configured")

        secret = (
            webhook_trigger.get("webhook_secret") if isinstance(webhook_trigger, dict)
            else getattr(webhook_trigger, "webhook_secret", None)
        )

        if secret and x_webhook_signature:
            expected = hmac.new(
                secret.encode(), body, hashlib.sha256
            ).hexdigest()
            sig = x_webhook_signature.removeprefix("sha256=")
            if not hmac.compare_digest(sig, expected):
                raise HTTPException(status_code=401, detail="Invalid webhook signature")

        # Parse body as JSON
        try:
            payload = json.loads(body) if body else {}
        except (json.JSONDecodeError, ValueError):
            payload = {"raw": body.decode("utf-8", errors="replace")}

        # Execute the workflow
        from app.control_models import ControlWorkflowsExecuteRequest
        execute_request = ControlWorkflowsExecuteRequest(
            workflow_id=workflow_id,
            message=json.dumps(payload, default=str),
        )

        try:
            result = await workflow_handlers.api_control_workflows_execute(
                request_data=execute_request.model_dump(),
                idempotency_key_header=None,
            )
        except Exception as exc:
            logger.exception("webhook_trigger_execute_failed workflow_id=%s", workflow_id)
            raise HTTPException(status_code=500, detail=str(exc))

        run_id = result.get("runId") or result.get("run_id") or str(uuid.uuid4())
        return {
            "status": "accepted",
            "run_id": run_id,
            "workflow_id": workflow_id,
        }

    return router
