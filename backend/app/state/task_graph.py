from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Literal

TaskStatus = Literal["pending", "active", "completed", "failed"]


@dataclass
class TaskNode:
    task_id: str
    label: str
    status: TaskStatus = "pending"
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now


class TaskGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, TaskNode] = {}

    def ensure_task(self, task_id: str, label: str, created_at: str | None = None) -> TaskNode:
        node = self._nodes.get(task_id)
        if node is None:
            node = TaskNode(task_id=task_id, label=label)
            if created_at:
                node.created_at = created_at
            self._nodes[task_id] = node
        else:
            node.label = label
        return node

    def set_status(self, task_id: str, status: TaskStatus) -> None:
        node = self._nodes.get(task_id)
        if node is None:
            node = TaskNode(task_id=task_id, label=task_id)
            self._nodes[task_id] = node
        node.status = status
        node.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "nodes": [asdict(node) for node in self._nodes.values()],
        }
