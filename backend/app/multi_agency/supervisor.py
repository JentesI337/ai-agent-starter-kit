"""Supervisor/Coordinator: Distributes work instead of leaving it to the LLM.

This is the key missing piece. Currently, the LLM decides everything —
which agent to use, when to delegate, how to combine results. The Supervisor
replaces that with structured, deterministic coordination logic:

- Task decomposition based on capability matching (not LLM guessing)
- Work distribution to best-fit agents
- Progress monitoring with timeout/retry
- Result aggregation and quality gating
- Conflict resolution between agents
- Re-delegation when confidence is too low
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Callable, Awaitable
from uuid import uuid4

from app.multi_agency.agent_identity import AgentIdentityCard, AgentRegistry
from app.multi_agency.agent_message_bus import AgentMessageBus, MessageType, MessagePriority
from app.multi_agency.blackboard import Blackboard

logger = logging.getLogger(__name__)


class TaskStatus(StrEnum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"
    NEEDS_REVIEW = "needs_review"


class SupervisorStrategy(StrEnum):
    """How the supervisor distributes work."""
    SEQUENTIAL = "sequential"       # One agent at a time, in order
    PARALLEL = "parallel"           # All independent tasks simultaneously
    PIPELINE = "pipeline"           # Output of one feeds into next
    COMPETITIVE = "competitive"     # Multiple agents solve same task, best wins
    HIERARCHICAL = "hierarchical"   # Supervisor delegates to sub-supervisors


@dataclass
class SupervisorTask:
    """A unit of work managed by the supervisor."""
    task_id: str
    description: str
    required_capabilities: set[str]
    assigned_agent_id: str | None = None
    status: str = TaskStatus.PENDING
    result: Any = None
    confidence: float = 0.0
    error: str | None = None
    depends_on: list[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 2
    timeout_seconds: float = 120.0
    created_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    quality_score: float | None = None   # post-review score
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SupervisorDecision:
    """A decision made by the supervisor."""
    decision_type: str    # "assign", "retry", "redelegate", "escalate", "complete", "reject", "parallel_fanout"
    task_id: str
    agent_id: str | None
    reason: str
    confidence: float
    alternatives: list[str] = field(default_factory=list)  # alternative agent_ids considered
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CoordinationSession:
    """Tracks all tasks and agents in a coordination session."""
    session_id: str
    tasks: dict[str, SupervisorTask] = field(default_factory=dict)
    decisions: list[SupervisorDecision] = field(default_factory=list)
    active_agents: set[str] = field(default_factory=set)
    strategy: str = SupervisorStrategy.PARALLEL
    overall_confidence: float = 0.0
    status: str = "active"    # "active", "completed", "failed"
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class SupervisorCoordinator:
    """The brain of multi-agent coordination.
    
    Architecture:
    1. Receives a high-level task
    2. Decomposes into sub-tasks with capability requirements
    3. Matches sub-tasks to best-fit agents using AgentRegistry
    4. Distributes work via AgentMessageBus
    5. Monitors progress via Blackboard
    6. Quality-gates results using confidence scores
    7. Re-delegates on failure or low confidence
    8. Aggregates final result
    """

    def __init__(
        self,
        *,
        agent_registry: AgentRegistry,
        message_bus: AgentMessageBus,
        blackboard: Blackboard,
        min_confidence: float = 0.6,
        re_delegation_threshold: float = 0.4,
        max_parallel_tasks: int = 5,
    ):
        self._registry = agent_registry
        self._bus = message_bus
        self._blackboard = blackboard
        self._min_confidence = max(0.0, min(1.0, min_confidence))
        self._re_delegation_threshold = max(0.0, min(1.0, re_delegation_threshold))
        self._max_parallel = max(1, max_parallel_tasks)
        self._sessions: dict[str, CoordinationSession] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        session_id: str,
        strategy: str = SupervisorStrategy.PARALLEL,
    ) -> CoordinationSession:
        """Create a new coordination session."""
        session = CoordinationSession(
            session_id=session_id,
            strategy=strategy,
        )
        async with self._lock:
            self._sessions[session_id] = session
        return session

    async def decompose_and_assign(
        self,
        *,
        session_id: str,
        task_descriptions: list[dict[str, Any]],
    ) -> list[SupervisorDecision]:
        """Decompose tasks and assign to optimal agents.
        
        Each task_description should have:
        - "description": str
        - "required_capabilities": list[str]
        - "depends_on": list[str] (task_ids)
        - "timeout_seconds": float (optional)
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise ValueError(f"No coordination session: {session_id}")

        decisions: list[SupervisorDecision] = []

        for task_desc in task_descriptions:
            task_id = str(uuid4())[:8]
            required_caps = set(task_desc.get("required_capabilities", []))
            depends_on = list(task_desc.get("depends_on", []))
            timeout = float(task_desc.get("timeout_seconds", 120.0))

            task = SupervisorTask(
                task_id=task_id,
                description=str(task_desc.get("description", "")),
                required_capabilities=required_caps,
                depends_on=depends_on,
                timeout_seconds=timeout,
            )

            # Find best agent for this task
            decision = await self._assign_task(task, session)
            decisions.append(decision)

            async with self._lock:
                session.tasks[task_id] = task
                session.decisions.append(decision)

        return decisions

    async def _assign_task(
        self,
        task: SupervisorTask,
        session: CoordinationSession,
    ) -> SupervisorDecision:
        """Find and assign the best agent for a task."""
        # Get all agents that could handle this task
        candidates: list[tuple[AgentIdentityCard, float]] = []
        for identity in self._registry.list_all():
            if not identity.can_receive_delegation:
                continue
            score = identity.capability_score(task.required_capabilities)
            if score > 0:
                candidates.append((identity, score))

        candidates.sort(key=lambda x: x[1], reverse=True)

        if not candidates:
            task.status = TaskStatus.FAILED
            task.error = "No agent found with required capabilities"
            return SupervisorDecision(
                decision_type="reject",
                task_id=task.task_id,
                agent_id=None,
                reason=f"No agent matches capabilities: {task.required_capabilities}",
                confidence=0.0,
                alternatives=[],
            )

        best_agent, best_score = candidates[0]
        alternative_ids = [c[0].agent_id for c in candidates[1:4]]

        # Check if agent is already overloaded
        active_tasks_for_agent = sum(
            1 for t in session.tasks.values()
            if t.assigned_agent_id == best_agent.agent_id
            and t.status in {TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS}
        )
        if active_tasks_for_agent >= best_agent.capability_profile.max_concurrent_tasks:
            # Try next best agent
            for alt_agent, alt_score in candidates[1:]:
                alt_active = sum(
                    1 for t in session.tasks.values()
                    if t.assigned_agent_id == alt_agent.agent_id
                    and t.status in {TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS}
                )
                if alt_active < alt_agent.capability_profile.max_concurrent_tasks:
                    best_agent = alt_agent
                    best_score = alt_score
                    break

        task.assigned_agent_id = best_agent.agent_id
        task.status = TaskStatus.ASSIGNED
        session.active_agents.add(best_agent.agent_id)

        # Write assignment to blackboard
        await self._blackboard.write(
            section="assignments",
            key=task.task_id,
            value={
                "task": task.description,
                "agent": best_agent.agent_id,
                "capabilities_matched": list(best_agent.matches_capabilities(task.required_capabilities)),
                "score": best_score,
            },
            author_agent_id="supervisor",
            confidence=best_score,
            tags=("assignment",),
        )

        # Send assignment message to agent
        await self._bus.send(
            sender="supervisor",
            recipient=best_agent.agent_id,
            payload={
                "type": "task_assignment",
                "task_id": task.task_id,
                "description": task.description,
                "required_capabilities": list(task.required_capabilities),
                "timeout_seconds": task.timeout_seconds,
                "depends_on": task.depends_on,
            },
            message_type=MessageType.COORDINATION,
            priority=MessagePriority.HIGH,
        )

        return SupervisorDecision(
            decision_type="assign",
            task_id=task.task_id,
            agent_id=best_agent.agent_id,
            reason=f"Best capability match ({best_score:.2f}) for {task.required_capabilities}",
            confidence=best_score,
            alternatives=alternative_ids,
        )

    async def report_result(
        self,
        *,
        session_id: str,
        task_id: str,
        result: Any,
        confidence: float,
        agent_id: str,
    ) -> SupervisorDecision:
        """An agent reports a task result. Supervisor evaluates and decides next action."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise ValueError(f"No coordination session: {session_id}")
            task = session.tasks.get(task_id)
            if task is None:
                raise ValueError(f"No task: {task_id}")

        confidence = max(0.0, min(1.0, float(confidence)))

        # Write result to blackboard
        await self._blackboard.write(
            section="results",
            key=task_id,
            value=result,
            author_agent_id=agent_id,
            confidence=confidence,
            tags=("result", f"task:{task_id}"),
        )

        # Quality gate: is the confidence high enough?
        if confidence < self._re_delegation_threshold and task.retry_count < task.max_retries:
            # Re-delegate to a different agent
            return await self._redelegate(task, session, reason=f"Low confidence: {confidence:.2f}")

        if confidence < self._min_confidence:
            # Mark as needs review
            task.status = TaskStatus.NEEDS_REVIEW
            task.result = result
            task.confidence = confidence
            task.completed_at = datetime.now(timezone.utc).isoformat()

            decision = SupervisorDecision(
                decision_type="escalate",
                task_id=task_id,
                agent_id=agent_id,
                reason=f"Confidence {confidence:.2f} below minimum {self._min_confidence:.2f}",
                confidence=confidence,
            )
            async with self._lock:
                session.decisions.append(decision)
            return decision

        # Accept the result
        task.status = TaskStatus.COMPLETED
        task.result = result
        task.confidence = confidence
        task.completed_at = datetime.now(timezone.utc).isoformat()

        decision = SupervisorDecision(
            decision_type="complete",
            task_id=task_id,
            agent_id=agent_id,
            reason=f"Accepted with confidence {confidence:.2f}",
            confidence=confidence,
        )
        async with self._lock:
            session.decisions.append(decision)

        # Check if all tasks are complete
        await self._check_session_completion(session)

        return decision

    async def _redelegate(
        self,
        task: SupervisorTask,
        session: CoordinationSession,
        reason: str,
    ) -> SupervisorDecision:
        """Re-delegate a task to a different agent."""
        task.retry_count += 1
        task.status = TaskStatus.RETRYING
        previous_agent = task.assigned_agent_id

        # Find alternative agent (exclude the one that failed)
        candidates = [
            (card, card.capability_score(task.required_capabilities))
            for card in self._registry.list_all()
            if card.can_receive_delegation
            and card.agent_id != previous_agent
            and card.capability_score(task.required_capabilities) > 0
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)

        if not candidates:
            task.status = TaskStatus.FAILED
            task.error = f"No alternative agents for re-delegation. {reason}"
            decision = SupervisorDecision(
                decision_type="reject",
                task_id=task.task_id,
                agent_id=None,
                reason=f"Re-delegation failed: no alternatives. {reason}",
                confidence=0.0,
            )
            async with self._lock:
                session.decisions.append(decision)
            return decision

        new_agent = candidates[0][0]
        new_score = candidates[0][1]

        task.assigned_agent_id = new_agent.agent_id
        task.status = TaskStatus.ASSIGNED
        session.active_agents.add(new_agent.agent_id)

        # Notify new agent
        await self._bus.send(
            sender="supervisor",
            recipient=new_agent.agent_id,
            payload={
                "type": "task_reassignment",
                "task_id": task.task_id,
                "description": task.description,
                "required_capabilities": list(task.required_capabilities),
                "timeout_seconds": task.timeout_seconds,
                "reason": reason,
                "previous_agent": previous_agent,
                "retry_count": task.retry_count,
            },
            message_type=MessageType.COORDINATION,
            priority=MessagePriority.HIGH,
        )

        decision = SupervisorDecision(
            decision_type="redelegate",
            task_id=task.task_id,
            agent_id=new_agent.agent_id,
            reason=f"Re-delegated from {previous_agent}: {reason}",
            confidence=new_score,
            alternatives=[c[0].agent_id for c in candidates[1:3]],
        )
        async with self._lock:
            session.decisions.append(decision)

        # Write to blackboard
        await self._blackboard.write(
            section="redelegations",
            key=task.task_id,
            value={
                "from_agent": previous_agent,
                "to_agent": new_agent.agent_id,
                "reason": reason,
                "retry_count": task.retry_count,
            },
            author_agent_id="supervisor",
            confidence=new_score,
        )

        return decision

    async def _check_session_completion(self, session: CoordinationSession) -> None:
        """Check if all tasks in a session are complete."""
        all_tasks = list(session.tasks.values())
        if not all_tasks:
            return

        completed = all(t.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED} for t in all_tasks)
        has_any_completed = any(t.status == TaskStatus.COMPLETED for t in all_tasks)
        failed = any(t.status == TaskStatus.FAILED for t in all_tasks)

        if completed and has_any_completed:
            session.status = "completed"
            # Calculate overall confidence as weighted average
            confidences = [t.confidence for t in all_tasks if t.status == TaskStatus.COMPLETED]
            if confidences:
                session.overall_confidence = sum(confidences) / len(confidences)

            # Write completion to blackboard
            await self._blackboard.write(
                section="coordination",
                key="session_status",
                value={
                    "status": "completed",
                    "overall_confidence": session.overall_confidence,
                    "task_count": len(all_tasks),
                    "completed_count": len([t for t in all_tasks if t.status == TaskStatus.COMPLETED]),
                },
                author_agent_id="supervisor",
                confidence=session.overall_confidence,
            )

            # Broadcast completion
            await self._bus.send(
                sender="supervisor",
                recipient="*",
                payload={
                    "type": "session_completed",
                    "session_id": session.session_id,
                    "overall_confidence": session.overall_confidence,
                },
                message_type=MessageType.BROADCAST,
            )

        elif completed and not has_any_completed:
            # All tasks cancelled, none completed — treat as failed
            session.status = "failed"

        elif failed and not any(t.status in {TaskStatus.PENDING, TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.RETRYING} for t in all_tasks):
            session.status = "failed"

    async def get_session_status(self, session_id: str) -> dict[str, Any]:
        """Get the status of a coordination session."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return {"error": f"No session: {session_id}"}

        tasks_summary = []
        for task in session.tasks.values():
            tasks_summary.append({
                "task_id": task.task_id,
                "description": task.description[:100],
                "status": task.status,
                "assigned_to": task.assigned_agent_id,
                "confidence": task.confidence,
                "retry_count": task.retry_count,
            })

        return {
            "session_id": session.session_id,
            "status": session.status,
            "strategy": session.strategy,
            "overall_confidence": session.overall_confidence,
            "active_agents": list(session.active_agents),
            "tasks": tasks_summary,
            "decision_count": len(session.decisions),
        }

    async def get_decisions(self, session_id: str) -> list[SupervisorDecision]:
        """Get all decisions made for a session."""
        async with self._lock:
            session = self._sessions.get(session_id)
            return list(session.decisions) if session else []

    async def cancel_task(self, session_id: str, task_id: str, reason: str = "cancelled") -> None:
        """Cancel a specific task."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            task = session.tasks.get(task_id)
            if task is None:
                return
            task.status = TaskStatus.CANCELLED
            task.error = reason

        # Notify assigned agent
        if task.assigned_agent_id:
            await self._bus.send(
                sender="supervisor",
                recipient=task.assigned_agent_id,
                payload={
                    "type": "task_cancelled",
                    "task_id": task_id,
                    "reason": reason,
                },
                message_type=MessageType.COORDINATION,
                priority=MessagePriority.HIGH,
            )
