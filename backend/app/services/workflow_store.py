"""Dedicated workflow store — one JSON file per workflow, atomic writes."""
from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.orchestrator.workflow_models import WorkflowGraphDef
from app.services.workflow_record import WorkflowRecord, WorkflowToolPolicy

logger = logging.getLogger(__name__)

_instance: WorkflowStore | None = None
_init_lock = threading.Lock()


class WorkflowStore:
    """JSON-file-per-workflow storage with atomic writes and thread safety."""

    def __init__(self, *, persist_dir: str | Path) -> None:
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ── CRUD ──────────────────────────────────────────

    def list(self, *, limit: int = 500) -> list[WorkflowRecord]:
        items: list[WorkflowRecord] = []
        with self._lock:
            for path in sorted(self._persist_dir.glob("*.json")):
                record = self._read_record(path)
                if record is not None:
                    items.append(record)
                    if len(items) >= limit:
                        break
        return items

    def get(self, workflow_id: str) -> WorkflowRecord | None:
        normalized = self._normalize_id(workflow_id)
        if not normalized:
            return None
        with self._lock:
            return self._read_record(self._workflow_path(normalized))

    def create(self, record: WorkflowRecord) -> WorkflowRecord:
        now = datetime.now(timezone.utc).isoformat()
        record = record.model_copy(update={
            "created_at": now,
            "updated_at": now,
            "version": 1,
        })
        with self._lock:
            path = self._workflow_path(record.id)
            if path.exists():
                raise ValueError(f"Workflow already exists: {record.id}")
            self._write_record(record)
        return record

    def update(self, workflow_id: str, record: WorkflowRecord) -> WorkflowRecord:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            existing = self._read_record(self._workflow_path(workflow_id))
            if existing is None:
                raise KeyError(f"Workflow not found: {workflow_id}")
            record = record.model_copy(update={
                "id": workflow_id,
                "created_at": existing.created_at,
                "updated_at": now,
                "version": existing.version + 1,
            })
            self._write_record(record)
        return record

    def delete(self, workflow_id: str) -> bool:
        normalized = self._normalize_id(workflow_id)
        if not normalized:
            return False
        with self._lock:
            path = self._workflow_path(normalized)
            if not path.exists():
                return False
            path.unlink(missing_ok=True)
            return True

    # ── Migration ─────────────────────────────────────

    def migrate_from_agent_store(self, agent_store: Any) -> int:
        """One-time migration from UnifiedAgentStore to WorkflowStore.

        Scans for records with custom_workflow, converts to WorkflowRecord.
        Skips if target file already exists (idempotent).
        Does NOT delete source files.
        Returns count of migrated records.
        """
        count = 0
        try:
            all_records = agent_store.list_all()
        except Exception:
            logger.warning("workflow_migration_failed: could not read agent store", exc_info=True)
            return 0

        for record in all_records:
            if record.custom_workflow is None:
                continue

            wf = record.custom_workflow
            workflow_id = record.agent_id

            with self._lock:
                path = self._workflow_path(workflow_id)
                if path.exists():
                    continue

                # Convert tool policy
                tool_policy = None
                if record.tool_policy.additional_allow or record.tool_policy.additional_deny:
                    tool_policy = WorkflowToolPolicy(
                        allow=list(record.tool_policy.additional_allow),
                        deny=list(record.tool_policy.additional_deny),
                    )

                # Convert workflow_graph
                workflow_graph = None
                if wf.workflow_graph is not None:
                    try:
                        workflow_graph = WorkflowGraphDef.model_validate(wf.workflow_graph)
                    except Exception:
                        logger.debug(
                            "workflow_migration_graph_invalid id=%s", workflow_id, exc_info=True,
                        )
                        # If graph is invalid but we have steps, build linear graph
                        if wf.workflow_steps:
                            workflow_graph = self._build_linear_graph(wf.workflow_steps)
                elif wf.workflow_steps:
                    workflow_graph = self._build_linear_graph(wf.workflow_steps)

                now = datetime.now(timezone.utc).isoformat()
                new_record = WorkflowRecord(
                    id=workflow_id,
                    name=record.display_name,
                    description=record.description,
                    base_agent_id=wf.base_agent_id,
                    execution_mode=wf.execution_mode,
                    workflow_graph=workflow_graph,
                    tool_policy=tool_policy,
                    triggers=list(wf.triggers),
                    allow_subrun_delegation=wf.allow_subrun_delegation,
                    version=record.version,
                    created_at=now,
                    updated_at=now,
                )
                self._write_record(new_record)
                count += 1
                logger.info("workflow_migrated id=%s name=%s", workflow_id, record.display_name)

        return count

    # ── IO Helpers ────────────────────────────────────

    def _workflow_path(self, workflow_id: str) -> Path:
        safe = workflow_id.replace("/", "_").replace("\\", "_")
        return self._persist_dir / f"{safe}.json"

    def _read_record(self, path: Path) -> WorkflowRecord | None:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return WorkflowRecord.model_validate(data)
        except Exception:
            logger.warning("workflow_record_load_failed path=%s", path, exc_info=True)
            return None

    def _write_record(self, record: WorkflowRecord) -> None:
        path = self._workflow_path(record.id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)

    @staticmethod
    def _normalize_id(raw: str) -> str:
        candidate = (raw or "").strip().lower()
        candidate = re.sub(r"[^a-z0-9_-]+", "-", candidate)
        candidate = re.sub(r"-+", "-", candidate).strip("-")
        return candidate[:80]

    @staticmethod
    def _build_linear_graph(steps: list[str]) -> WorkflowGraphDef:
        """Build a linear workflow graph from a flat list of step instructions."""
        from app.orchestrator.workflow_models import WorkflowStepDef

        graph_steps: list[WorkflowStepDef] = []
        for i, instruction in enumerate(steps):
            step_id = f"step-{i + 1}"
            next_id = f"step-{i + 2}" if i + 1 < len(steps) else None
            graph_steps.append(WorkflowStepDef(
                id=step_id,
                type="agent",
                label=f"Step {i + 1}",
                instruction=instruction,
                next_step=next_id,
            ))
        return WorkflowGraphDef(
            steps=graph_steps,
            entry_step_id="step-1",
        )


def init_workflow_store(*, persist_dir: str | Path) -> WorkflowStore:
    global _instance
    with _init_lock:
        _instance = WorkflowStore(persist_dir=persist_dir)
    return _instance


def get_workflow_store() -> WorkflowStore:
    if _instance is None:
        raise RuntimeError("WorkflowStore not initialized")
    return _instance
