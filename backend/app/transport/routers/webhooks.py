"""Webhook trigger endpoint for workflows (deprecated).

The old workflow webhook endpoint is preserved for backward compatibility
but returns a deprecation notice.  Recipe webhook resume is available at
POST /api/control/recipes.runs.webhook/{run_id}.
"""
from __future__ import annotations

import logging

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
        """DEPRECATED — workflow webhooks are no longer supported.

        Use the recipe webhook resume endpoint instead:
        POST /api/control/recipes.runs.webhook/{run_id}
        """
        raise HTTPException(
            status_code=410,
            detail=(
                "Workflow webhook triggers are deprecated. "
                "Use POST /api/control/recipes.runs.webhook/{run_id} for recipe webhook resume."
            ),
        )

    return router
