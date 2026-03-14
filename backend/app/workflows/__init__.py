"""workflows — Workflow & Recipe Domain.

DEPRECATED: The graph-based workflow engine has been removed in favour of
recipes (see recipe_models.py / recipe_store.py / recipe_runner.py).
Workflow models and store are retained for data access during the migration
period.  New code should use recipes exclusively.

Transport layer (HTTP routes) lives in app.transport.routers.workflows
(deprecated, read-only) and app.transport.routers.recipes.
"""

from app.workflows.models import (
    StepResult,
    WorkflowExecutionState,
    WorkflowGraphDef,
    WorkflowRecord,
    WorkflowStepDef,
)
from app.workflows.store import (
    SqliteWorkflowAuditStore,
    SqliteWorkflowRunStore,
    SqliteWorkflowStore,
)

__all__ = [
    "SqliteWorkflowAuditStore",
    "SqliteWorkflowRunStore",
    "SqliteWorkflowStore",
    "StepResult",
    "WorkflowExecutionState",
    "WorkflowGraphDef",
    "WorkflowRecord",
    "WorkflowStepDef",
]
