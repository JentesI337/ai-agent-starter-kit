"""
State Snapshots — compressed state checkpoints for rehydration.

Allows the orchestrator to:
  - Create snapshots of current state at any point
  - Rehydrate state from a snapshot after interruption
  - Summarize state for handoff between phases
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.orchestrator.contracts.schemas import TaskEnvelope, TaskStatus

logger = logging.getLogger(__name__)


@dataclass
class StateSnapshot:
    """Compressed checkpoint of orchestrator state."""
    snapshot_id: str
    timestamp: str
    tasks: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    graph_summary: dict[str, Any] = field(default_factory=dict)
    summary_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp,
            "tasks": self.tasks,
            "metadata": self.metadata,
            "graph_summary": self.graph_summary,
            "summary_text": self.summary_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateSnapshot:
        return cls(
            snapshot_id=data["snapshot_id"],
            timestamp=data["timestamp"],
            tasks=data.get("tasks", []),
            metadata=data.get("metadata", {}),
            graph_summary=data.get("graph_summary", {}),
            summary_text=data.get("summary_text", ""),
        )


class SnapshotManager:
    """
    Creates and manages state snapshots for rehydration.

    Snapshots are lightweight — they store task envelopes and metadata
    as JSON, not full model outputs.
    """

    def __init__(self, persist_dir: str | None = None, max_snapshots: int = 20):
        self._persist_dir: Path | None = Path(persist_dir) if persist_dir else None
        self._max_snapshots = max_snapshots
        self._snapshots: list[StateSnapshot] = []
        if self._persist_dir:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            self._load_index()

    def create_snapshot(
        self,
        snapshot_id: str,
        tasks: list[TaskEnvelope],
        metadata: dict[str, Any] | None = None,
        graph_summary: dict[str, Any] | None = None,
    ) -> StateSnapshot:
        """
        Create a compressed snapshot of the current orchestrator state.
        Tasks are stored as minimal dicts (not full model outputs).
        """
        task_summaries = []
        for t in tasks:
            task_summaries.append({
                "task_id": t.task_id,
                "status": t.status.value,
                "agent_role": t.agent_role.value,
                "has_output": t.output_data is not None,
                "error": t.error,
                "retries": t.retries,
            })

        # Build human-readable summary
        status_counts: dict[str, int] = {}
        for t in tasks:
            status_counts[t.status.value] = status_counts.get(t.status.value, 0) + 1
        summary_parts = [f"{k}: {v}" for k, v in sorted(status_counts.items())]
        summary_text = f"Tasks: {len(tasks)} ({', '.join(summary_parts)})"

        snapshot = StateSnapshot(
            snapshot_id=snapshot_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            tasks=task_summaries,
            metadata=metadata or {},
            graph_summary=graph_summary or {},
            summary_text=summary_text,
        )

        self._snapshots.append(snapshot)
        self._enforce_limit()
        self._persist_snapshot(snapshot)
        logger.info("snapshot_created id=%s tasks=%d summary=%s", snapshot_id, len(tasks), summary_text)
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> StateSnapshot | None:
        for s in self._snapshots:
            if s.snapshot_id == snapshot_id:
                return s
        return self._load_snapshot_from_disk(snapshot_id)

    def get_latest_snapshot(self) -> StateSnapshot | None:
        if self._snapshots:
            return self._snapshots[-1]
        return None

    def list_snapshots(self) -> list[StateSnapshot]:
        return list(self._snapshots)

    def get_rehydration_context(self, snapshot_id: str) -> str:
        """
        Return a text summary suitable for injecting into a model prompt
        to rehydrate context after an interruption.
        """
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot is None:
            return "(no snapshot available)"

        lines = [
            f"State checkpoint: {snapshot.snapshot_id}",
            f"Timestamp: {snapshot.timestamp}",
            f"Summary: {snapshot.summary_text}",
            "",
            "Task details:",
        ]
        for t in snapshot.tasks:
            status_emoji = {
                "completed": "done",
                "active": "running",
                "pending": "waiting",
                "failed": "error",
                "blocked": "blocked",
            }.get(t.get("status", ""), "?")
            lines.append(
                f"  [{status_emoji}] {t.get('agent_role', '?')}: {t.get('task_id', '?')[:8]}... "
                f"(retries={t.get('retries', 0)}, has_output={t.get('has_output', False)})"
            )
            if t.get("error"):
                lines.append(f"    error: {t['error'][:120]}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_snapshot(self, snapshot: StateSnapshot) -> None:
        if self._persist_dir is None:
            return
        try:
            path = self._persist_dir / f"{snapshot.snapshot_id}.json"
            path.write_text(
                json.dumps(snapshot.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("snapshot_persist_failed id=%s", snapshot.snapshot_id)

    def _load_snapshot_from_disk(self, snapshot_id: str) -> StateSnapshot | None:
        if self._persist_dir is None:
            return None
        path = self._persist_dir / f"{snapshot_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return StateSnapshot.from_dict(data)
        except Exception:
            logger.exception("snapshot_load_failed id=%s", snapshot_id)
            return None

    def _load_index(self) -> None:
        if self._persist_dir is None:
            return
        for path in sorted(self._persist_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._snapshots.append(StateSnapshot.from_dict(data))
            except Exception:
                continue
        logger.info("snapshot_manager loaded %d snapshots", len(self._snapshots))

    def _enforce_limit(self) -> None:
        while len(self._snapshots) > self._max_snapshots:
            oldest = self._snapshots.pop(0)
            if self._persist_dir:
                path = self._persist_dir / f"{oldest.snapshot_id}.json"
                path.unlink(missing_ok=True)
