"""Workflow management tools — build_workflow and explore_connector.

Mixin that gives agents the ability to create workflows from natural
language descriptions and inspect connector capabilities.
"""
from __future__ import annotations

import json
import logging

from app.shared.errors import ToolExecutionError

logger = logging.getLogger(__name__)


class WorkflowToolMixin:
    """Tool mixin for workflow creation and connector exploration."""

    async def build_workflow(
        self,
        *,
        name: str,
        description: str = "",
        steps_description: str,
        execution_mode: str = "sequential",
        **_kwargs,
    ) -> str:
        """Create a workflow from a natural language description.

        The agent decomposes *steps_description* into concrete workflow steps
        and creates the workflow via the internal API.
        """
        # Parse steps from the description — each line becomes a step
        raw_lines = [
            line.strip().lstrip("-•*0123456789.) ")
            for line in steps_description.strip().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not raw_lines:
            raise ToolExecutionError("steps_description must contain at least one step")

        steps = [line for line in raw_lines if line]

        try:
            from app.shared.control_models import ControlWorkflowsCreateRequest
            from app.workflows import handlers as workflow_handlers

            request = ControlWorkflowsCreateRequest(
                name=name,
                description=description,
                steps=steps,
                execution_mode=execution_mode if execution_mode in ("parallel", "sequential") else "sequential",
            )
            result = workflow_handlers.api_control_workflows_create(
                request_data=request.model_dump(),
                idempotency_key_header=None,
            )
            workflow_id = result.get("workflow", {}).get("id", "unknown")
            step_count = result.get("workflow", {}).get("step_count", len(steps))
            return json.dumps({
                "status": "created",
                "workflow_id": workflow_id,
                "name": name,
                "step_count": step_count,
                "steps": steps,
                "message": f"Workflow '{name}' created with {step_count} steps. Open it in the Workflows page to configure and run.",
            })
        except Exception as exc:
            raise ToolExecutionError(f"Failed to create workflow: {exc}") from exc

    async def explore_connector(
        self,
        *,
        connector_id: str,
        **_kwargs,
    ) -> str:
        """List all available methods and parameters for a configured connector."""
        try:
            from app.connectors.connector_store import get_connector_store
            from app.connectors.credential_store import get_credential_store
            from app.connectors.registry import ConnectorRegistry

            store = get_connector_store()
            cred_store = get_credential_store()
            registry = ConnectorRegistry()

            config = store.get(connector_id)
            if config is None:
                return json.dumps({"error": f"Connector '{connector_id}' not found"})

            connector_type = config.get("type") if isinstance(config, dict) else getattr(config, "type", None)
            connector_cls = registry.get(connector_type)
            if connector_cls is None:
                return json.dumps({
                    "connector_id": connector_id,
                    "type": connector_type,
                    "error": f"No connector implementation found for type '{connector_type}'",
                })

            # Try to get available methods
            try:
                instance = connector_cls(config=config, credential_store=cred_store)
                methods = instance.available_methods() if hasattr(instance, "available_methods") else []
            except Exception:
                methods = []

            method_list = []
            for m in methods:
                if isinstance(m, dict):
                    method_list.append(m)
                elif isinstance(m, str):
                    method_list.append({"name": m})
                else:
                    method_list.append({"name": str(m)})

            return json.dumps({
                "connector_id": connector_id,
                "type": connector_type,
                "method_count": len(method_list),
                "methods": method_list,
            })
        except ImportError:
            return json.dumps({"error": "Connector system not available"})
        except Exception as exc:
            raise ToolExecutionError(f"Failed to explore connector: {exc}") from exc
