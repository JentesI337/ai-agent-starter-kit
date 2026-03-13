"""AgentTooling — main tooling class assembled from all tool mixins.

This is the single entry point used by AgentRunner.
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from pathlib import Path

from app.browser.pool import BrowserPool
from app.config import settings
from app.shared.errors import ToolExecutionError
from app.sandbox.repl_session_manager import ReplSessionManager
from app.tools.catalog import TOOL_NAMES
from app.tools.implementations.api_connectors import ApiConnectorToolMixin
from app.tools.implementations.browser import BrowserToolMixin
from app.tools.implementations.code_execution import CodeExecToolMixin
from app.tools.implementations.devops import DevOpsToolMixin
from app.tools.implementations.filesystem import FileSystemToolMixin
from app.tools.implementations.multimodal import MultimodalToolMixin
from app.tools.implementations.shell import (
    COMMAND_SAFETY_PATTERNS,
    ShellToolMixin,
    find_command_safety_violation,
    find_semantic_command_safety_violation,
)
from app.tools.implementations.web import WebToolMixin
from app.tools.implementations.workflow import WorkflowToolMixin

# Re-export for backward compat
__all__ = [
    "COMMAND_SAFETY_PATTERNS",
    "AgentTooling",
    "find_command_safety_violation",
    "find_semantic_command_safety_violation",
]


class AgentTooling(
    FileSystemToolMixin,
    ShellToolMixin,
    WebToolMixin,
    BrowserToolMixin,
    CodeExecToolMixin,
    ApiConnectorToolMixin,
    MultimodalToolMixin,
    DevOpsToolMixin,
    WorkflowToolMixin,
):
    """Assembled tool implementation class.

    Inherits all tool methods from specialized mixins.
    """

    def __init__(self, workspace_root: str, command_timeout_seconds: int = 60):
        self.workspace_root = Path(workspace_root).resolve()
        self.command_timeout_seconds = command_timeout_seconds
        self._command_allowlist_enabled = settings.command_allowlist_enabled
        self._command_allowlist = self._build_command_allowlist()
        self._command_allowlist_overrides: set[str] = set()
        self._background_jobs: dict[str, dict] = {}
        self._bg_lock = threading.Lock()
        self._bg_max_concurrent_jobs = 10
        self._web_fetch_max_redirects = 3
        self._web_fetch_max_download_bytes = max(1_000, int(settings.web_fetch_max_download_bytes))
        self._web_fetch_blocked_content_types = tuple(
            item.strip().lower() for item in settings.web_fetch_blocked_content_types if item.strip()
        )
        self._http_request_max_body_bytes = 1_000_000
        self._read_file_max_bytes = 1_000_000
        self._grep_max_file_bytes = 1_000_000
        self._grep_max_total_scan_bytes = 8_000_000
        self._repl_manager: ReplSessionManager | None = None
        self._browser_pool: BrowserPool | None = None

    def set_repl_manager(self, manager: ReplSessionManager) -> None:
        self._repl_manager = manager

    def set_browser_pool(self, pool: BrowserPool) -> None:
        self._browser_pool = pool

    def _resolve_workspace_path(self, raw_path: str) -> Path:
        # SEC: Use os.path.realpath to resolve all symlinks/junctions,
        # then verify the resolved path is within the resolved workspace root.
        workspace_real = Path(os.path.realpath(self.workspace_root))
        target_raw = self.workspace_root / raw_path
        target = Path(os.path.realpath(target_raw))

        # Auto-correct duplicated workspace directory name: LLMs often prepend
        # the workspace folder name (e.g. "backend/app/file.py") even though
        # workspace_root already IS that folder.  Strip the leading duplicate
        # only when the joined path doesn't exist and the stripped version does.
        if not target.exists():
            ws_dir_name = self.workspace_root.name
            raw_parts = Path(raw_path).parts
            if raw_parts and raw_parts[0].lower() == ws_dir_name.lower():
                stripped = Path(*raw_parts[1:]) if len(raw_parts) > 1 else Path(".")
                candidate_raw = self.workspace_root / stripped
                candidate = Path(os.path.realpath(candidate_raw))
                if candidate.exists() and (workspace_real in candidate.parents or candidate == workspace_real):
                    target = candidate

        if workspace_real not in target.parents and target != workspace_real:
            raise ToolExecutionError("Path escapes workspace root.")
        return target

    def _resolve_command_cwd(self, cwd: str | None) -> Path:
        if not cwd:
            return self.workspace_root

        workspace_real = Path(os.path.realpath(self.workspace_root))
        candidate = Path(cwd)
        if not candidate.is_absolute():
            candidate = self.workspace_root / candidate
        candidate = Path(os.path.realpath(candidate))

        if not candidate.exists() or not candidate.is_dir():
            raise ToolExecutionError(f"Command cwd does not exist: {candidate}")
        if workspace_real not in candidate.parents and candidate != workspace_real:
            raise ToolExecutionError("Command cwd escapes workspace root.")
        return candidate

    def check_toolchain(self) -> tuple[bool, dict]:
        workspace_ok = self.workspace_root.exists() and self.workspace_root.is_dir()
        shell_ok = bool(os.environ.get("COMSPEC")) if os.name == "nt" else Path("/bin/sh").exists()
        ok = workspace_ok and shell_ok
        details = {
            "workspace_root": str(self.workspace_root),
            "workspace_ok": workspace_ok,
            "shell_ok": shell_ok,
            "tools": list(TOOL_NAMES),
        }
        return ok, details

    def create_workflow(
        self,
        name: str,
        description: str,
        steps: str | list,
        base_agent_id: str = "head-agent",
    ) -> str:
        from app.workflows.store import get_workflow_store
        store = get_workflow_store()
        name = (name or "").strip()
        if not name or len(name) > 120:
            raise ToolExecutionError("Workflow name must be 1-120 characters.")
        description = (description or "").strip()
        if len(description) > 500:
            raise ToolExecutionError("Description must not exceed 500 characters.")
        if isinstance(steps, list):
            workflow_steps = [str(s).strip() for s in steps if str(s).strip()]
        else:
            workflow_steps = [s.strip() for s in (steps or "").split(",") if s.strip()]
        if not workflow_steps:
            raise ToolExecutionError("At least one step is required (comma-separated).")
        if len(workflow_steps) > 20:
            raise ToolExecutionError("Maximum 20 workflow steps allowed.")

        workflow_id = re.sub(r"-+", "-", re.sub(r"[^a-z0-9_-]+", "-", f"workflow-{name}-{str(uuid.uuid4())[:8]}".strip().lower())).strip("-")[:80]

        from app.workflows.models import WorkflowRecord
        graph = store._build_linear_graph(workflow_steps)
        record = WorkflowRecord(
            id=workflow_id,
            name=name,
            description=description,
            base_agent_id=base_agent_id,
            workflow_graph=graph,
            execution_mode="sequential",
        )
        created = store.create(record)
        return json.dumps({"status": "created", "id": created.id, "name": created.name}, ensure_ascii=False)

    def delete_workflow(self, workflow_id: str) -> str:
        from app.workflows.store import get_workflow_store
        store = get_workflow_store()
        workflow_id = (workflow_id or "").strip()
        if not workflow_id:
            raise ToolExecutionError("workflow_id is required.")
        deleted = store.delete(workflow_id)
        if deleted:
            return json.dumps({"status": "deleted", "id": workflow_id}, ensure_ascii=False)
        return json.dumps({"status": "not_found", "id": workflow_id}, ensure_ascii=False)
