"""
Task Graph — directed graph of pending, active, completed tasks.

Supports dependency tracking, topological ordering, and cycle detection.
The orchestrator uses this to determine which tasks are ready to execute.
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Any

from app.orchestrator.contracts.schemas import TaskEnvelope, TaskStatus

logger = logging.getLogger(__name__)


class CyclicDependencyError(Exception):
    """Raised when adding an edge would create a cycle."""
    pass


class TaskGraph:
    """
    Directed acyclic graph (DAG) of task dependencies.

    Nodes are task_ids. An edge A → B means "A depends on B"
    (B must complete before A can start).
    """

    def __init__(self) -> None:
        # task_id → set of task_ids it depends on
        self._dependencies: dict[str, set[str]] = defaultdict(set)
        # task_id → set of task_ids that depend on it (reverse edges)
        self._dependents: dict[str, set[str]] = defaultdict(set)
        # task_id → TaskStatus
        self._statuses: dict[str, TaskStatus] = {}

    # ------------------------------------------------------------------
    # Graph mutation
    # ------------------------------------------------------------------

    def add_task(self, task_id: str, depends_on: list[str] | None = None) -> None:
        """Register a task node with optional dependencies."""
        if task_id not in self._statuses:
            self._statuses[task_id] = TaskStatus.PENDING
        for dep in (depends_on or []):
            self.add_dependency(task_id, dep)

    def add_dependency(self, task_id: str, depends_on_id: str) -> None:
        """
        Add an edge: task_id depends on depends_on_id.
        Raises CyclicDependencyError if this would create a cycle.
        """
        if depends_on_id == task_id:
            raise CyclicDependencyError(f"Self-dependency: {task_id}")
        # Check for cycle before adding
        if self._would_create_cycle(task_id, depends_on_id):
            raise CyclicDependencyError(
                f"Adding dependency {task_id} → {depends_on_id} creates a cycle"
            )
        self._dependencies[task_id].add(depends_on_id)
        self._dependents[depends_on_id].add(task_id)
        # Ensure both nodes exist in status map
        self._statuses.setdefault(task_id, TaskStatus.PENDING)
        self._statuses.setdefault(depends_on_id, TaskStatus.PENDING)

    def remove_task(self, task_id: str) -> None:
        """Remove a task and all its edges."""
        for dep in list(self._dependencies.get(task_id, [])):
            self._dependents[dep].discard(task_id)
        for dependent in list(self._dependents.get(task_id, [])):
            self._dependencies[dependent].discard(task_id)
        self._dependencies.pop(task_id, None)
        self._dependents.pop(task_id, None)
        self._statuses.pop(task_id, None)

    # ------------------------------------------------------------------
    # Status management
    # ------------------------------------------------------------------

    def set_status(self, task_id: str, status: TaskStatus) -> None:
        if task_id not in self._statuses:
            raise KeyError(f"Task {task_id} not in graph")
        self._statuses[task_id] = status
        logger.debug("task_graph status_set task_id=%s status=%s", task_id, status.value)

    def get_status(self, task_id: str) -> TaskStatus | None:
        return self._statuses.get(task_id)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_ready_tasks(self) -> list[str]:
        """
        Return task_ids that are PENDING and have all dependencies
        completed (or have no dependencies).
        """
        ready = []
        for task_id, status in self._statuses.items():
            if status != TaskStatus.PENDING:
                continue
            deps = self._dependencies.get(task_id, set())
            if all(self._statuses.get(d) == TaskStatus.COMPLETED for d in deps):
                ready.append(task_id)
        return ready

    def get_blocked_tasks(self) -> list[str]:
        """Return task_ids that are PENDING but have incomplete dependencies."""
        blocked = []
        for task_id, status in self._statuses.items():
            if status != TaskStatus.PENDING:
                continue
            deps = self._dependencies.get(task_id, set())
            if deps and not all(self._statuses.get(d) == TaskStatus.COMPLETED for d in deps):
                blocked.append(task_id)
        return blocked

    def get_dependencies(self, task_id: str) -> set[str]:
        return set(self._dependencies.get(task_id, set()))

    def get_dependents(self, task_id: str) -> set[str]:
        return set(self._dependents.get(task_id, set()))

    def is_complete(self) -> bool:
        """True if all tasks are COMPLETED or FAILED."""
        return all(
            s in (TaskStatus.COMPLETED, TaskStatus.FAILED) for s in self._statuses.values()
        )

    def has_failures(self) -> bool:
        return any(s == TaskStatus.FAILED for s in self._statuses.values())

    def topological_order(self) -> list[str]:
        """
        Return a topological ordering of all tasks.
        Raises CyclicDependencyError if the graph has cycles.
        """
        in_degree: dict[str, int] = {tid: 0 for tid in self._statuses}
        for tid, deps in self._dependencies.items():
            if tid in in_degree:
                in_degree[tid] = len(deps & set(self._statuses.keys()))

        queue: deque[str] = deque(tid for tid, deg in in_degree.items() if deg == 0)
        order: list[str] = []

        while queue:
            current = queue.popleft()
            order.append(current)
            for dependent in self._dependents.get(current, set()):
                if dependent in in_degree:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        if len(order) != len(self._statuses):
            raise CyclicDependencyError("Graph contains a cycle — topological sort impossible")
        return order

    @property
    def task_count(self) -> int:
        return len(self._statuses)

    def summary(self) -> dict[str, Any]:
        """Compact summary for debugging / context injection."""
        by_status: dict[str, int] = {}
        for s in self._statuses.values():
            by_status[s.value] = by_status.get(s.value, 0) + 1
        return {
            "total": self.task_count,
            "by_status": by_status,
            "ready": self.get_ready_tasks(),
            "blocked": self.get_blocked_tasks(),
            "is_complete": self.is_complete(),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _would_create_cycle(self, from_id: str, to_id: str) -> bool:
        """
        Check if adding edge from_id → to_id would create a cycle.
        BFS from to_id through existing edges to see if from_id is reachable.
        """
        visited: set[str] = set()
        queue: deque[str] = deque([to_id])
        while queue:
            current = queue.popleft()
            if current == from_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            for dep in self._dependencies.get(current, set()):
                queue.append(dep)
        return False

    def load_from_envelopes(self, envelopes: list[TaskEnvelope]) -> None:
        """Bulk-load tasks from a list of TaskEnvelopes."""
        for env in envelopes:
            self._statuses[env.task_id] = env.status
        for env in envelopes:
            for dep_id in env.depends_on:
                if dep_id in self._statuses:
                    self._dependencies[env.task_id].add(dep_id)
                    self._dependents[dep_id].add(env.task_id)
