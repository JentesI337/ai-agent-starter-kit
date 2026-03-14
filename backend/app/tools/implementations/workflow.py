"""Workflow management tools — explore_connector (build_workflow deprecated).

Mixin that gives agents the ability to inspect connector capabilities.
The build_workflow tool has been deprecated in favour of recipes.
"""
from __future__ import annotations

import json
import logging

from app.shared.errors import ToolExecutionError

logger = logging.getLogger(__name__)


class WorkflowToolMixin:
    """Tool mixin for connector exploration (workflow creation deprecated)."""

    async def build_workflow(
        self,
        *,
        name: str = "",
        description: str = "",
        steps_description: str = "",
        execution_mode: str = "sequential",
        **_kwargs,
    ) -> str:
        """DEPRECATED — use create_recipe instead."""
        return json.dumps({
            "status": "deprecated",
            "message": "build_workflow is deprecated. Use create_recipe to create a recipe instead.",
        })

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
