"""Coordination Bridge: Connects the new multi-agency system to the existing architecture.

This is the integration layer that bridges:
- SubrunLane completion → Confidence Router evaluation
- Agent spawn → Supervisor task assignment
- Handover contracts → Blackboard updates
- Agent registry → Identity-based routing
- PlanGraph → Parallel DAG executor

The bridge hooks into existing extension points without modifying the core loop.
"""
from __future__ import annotations

import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.multi_agency.agent_identity import AgentRegistry
from app.multi_agency.agent_message_bus import AgentMessageBus, MessageType
from app.multi_agency.blackboard import Blackboard
from app.multi_agency.confidence_router import ConfidenceRouteDecision, ConfidenceRouter
from app.multi_agency.consensus import ConsensusEngine, VotingStrategy
from app.multi_agency.parallel_executor import DAGStep, FanOutResult, ParallelFanOutExecutor
from app.multi_agency.supervisor import SupervisorCoordinator, SupervisorDecision

logger = logging.getLogger(__name__)

SendEvent = Callable[[dict], Awaitable[None]]


class CoordinationBridge:
    """Bridges new multi-agency subsystem into existing subrun/agent architecture.

    Integration points:
    1. SubrunLane.set_completion_callback → evaluates confidence on subrun completion
    2. Agent._invoke_spawn_subrun_tool → routes through supervisor for task assignment
    3. Handover contracts → written to blackboard for shared state
    4. PlanGraph.ready_steps → fed into parallel DAG executor
    5. agent_resolution.capability_route_agent → enhanced with confidence history
    """

    def __init__(
        self,
        *,
        session_id: str,
        send_event: SendEvent | None = None,
    ):
        self._session_id = session_id
        self._send_event = send_event

        # Core multi-agency components
        self.agent_registry = AgentRegistry()
        self.blackboard = Blackboard(session_id=session_id)
        self.message_bus = AgentMessageBus(session_id=session_id)
        self.confidence_router = ConfidenceRouter(agent_registry=self.agent_registry)
        self.supervisor = SupervisorCoordinator(
            agent_registry=self.agent_registry,
            message_bus=self.message_bus,
            blackboard=self.blackboard,
        )
        self.consensus = ConsensusEngine(agent_registry=self.agent_registry)
        self._parallel_executor: ParallelFanOutExecutor | None = None
        self._initialized = False

    async def initialize(self, agent_executor: Callable | None = None) -> None:
        """Initialize the coordination bridge for a session."""
        if self._initialized:
            return

        # Register built-in agents on the message bus
        for identity in self.agent_registry.list_all():
            await self.message_bus.register_agent(identity.agent_id)

        # Register supervisor
        await self.message_bus.register_agent("supervisor")

        # Create coordination session
        await self.supervisor.create_session(self._session_id)

        # Set up parallel executor if agent_executor provided
        if agent_executor is not None:
            self._parallel_executor = ParallelFanOutExecutor(
                executor=agent_executor,
            )

        # Watch blackboard for coordination events
        self.blackboard.watch_all(self._on_blackboard_change)

        self._initialized = True
        logger.info("CoordinationBridge initialized for session %s", self._session_id)

    # --- Integration Point 1: Subrun Completion Evaluation ---

    async def on_subrun_completed(
        self,
        *,
        parent_session_id: str,
        run_id: str,
        child_agent_id: str,
        terminal_reason: str,
        child_output: str | None,
        handover_contract: dict[str, Any] | None = None,
    ) -> ConfidenceRouteDecision:
        """Called when a subrun completes. Evaluates confidence and decides next action.

        This replaces the current behavior where handover confidence is serialized but ignored.
        Now we use it to drive real routing decisions:
        - Accept: result is good enough, use it
        - Review: result needs review by review-agent
        - Redelegate: result is too low quality, try different agent
        - Reject: result is unusable, fail the task
        """
        effective_handover = handover_contract or {
            "terminal_reason": terminal_reason,
            "confidence": 0.0,
            "result": child_output,
        }

        # Evaluate via confidence router
        decision = self.confidence_router.evaluate_handover(
            handover_contract=effective_handover,
            source_agent_id=child_agent_id,
            task_description=child_output[:200] if child_output else "",
        )

        # Record the outcome for learning
        # Map actions to outcomes: accept→success, review→partial, redelegate/reject→failure
        outcome_map = {"accept": "success", "review": "partial", "redelegate": "failure", "reject": "failure"}
        outcome = outcome_map.get(decision.action, "failure")
        self.confidence_router.record_outcome(
            agent_id=child_agent_id,
            task_description=child_output[:200] if child_output else "",
            confidence=decision.confidence,
            outcome=outcome,
        )

        # Write to blackboard
        await self.blackboard.write(
            section="subrun_results",
            key=run_id,
            value={
                "agent_id": child_agent_id,
                "terminal_reason": terminal_reason,
                "confidence": decision.confidence,
                "action": decision.action,
                "result_preview": (child_output or "")[:500],
            },
            author_agent_id=child_agent_id,
            confidence=decision.confidence,
            tags=("subrun_result", f"agent:{child_agent_id}"),
        )

        # Emit lifecycle event if send_event available
        if self._send_event:
            await self._send_event({
                "type": "lifecycle",
                "stage": "confidence_evaluation",
                "session_id": self._session_id,
                "details": {
                    "run_id": run_id,
                    "agent_id": child_agent_id,
                    "confidence": decision.confidence,
                    "action": decision.action,
                    "reason": decision.reason,
                },
            })

        logger.info(
            "Subrun %s confidence evaluation: action=%s confidence=%.2f agent=%s",
            run_id, decision.action, decision.confidence, child_agent_id,
        )

        return decision

    # --- Integration Point 2: Enhanced Agent Routing ---

    def route_agent(
        self,
        *,
        required_capabilities: set[str],
        preferred_quality: str = "standard",
    ) -> ConfidenceRouteDecision:
        """Route to the best agent using confidence history, not just capability matching.

        This enhances the existing capability_route_agent() with:
        - Historical confidence weighting
        - Agent performance learning
        - Quality tier matching
        """
        return self.confidence_router.route_by_confidence(
            required_capabilities=required_capabilities,
            preferred_quality=preferred_quality,
        )

    # --- Integration Point 3: Supervised Task Assignment ---

    async def assign_tasks(
        self,
        tasks: list[dict[str, Any]],
    ) -> list[SupervisorDecision]:
        """Decompose and assign tasks through the supervisor.

        Each task should have:
        - "description": str
        - "required_capabilities": list[str]
        - "depends_on": list[str] (task_ids, optional)
        """
        return await self.supervisor.decompose_and_assign(
            session_id=self._session_id,
            task_descriptions=tasks,
        )

    # --- Integration Point 4: Parallel DAG Execution ---

    async def execute_plan_parallel(
        self,
        steps: list[dict[str, Any]],
        timeout: float = 120.0,
    ) -> list[dict[str, Any]]:
        """Execute a PlanGraph using parallel DAG execution.

        This replaces the current sequential PlanGraph → text string conversion.
        Steps with satisfied dependencies run in parallel.
        """
        if self._parallel_executor is None:
            raise RuntimeError("Parallel executor not initialized. Call initialize() with agent_executor first.")

        dag_steps = [
            DAGStep(
                step_id=str(step.get("step_id", f"s{i}")),
                agent_id=str(step.get("agent_id", "head-agent")),
                description=str(step.get("description", "")),
                depends_on=list(step.get("depends_on", [])),
                context=dict(step.get("context", {})),
                can_parallel=bool(step.get("can_parallel", True)),
            )
            for i, step in enumerate(steps, 1)
        ]

        return await self._parallel_executor.execute_dag(
            steps=dag_steps,
            timeout=timeout,
        )

    # --- Integration Point 5: Fan-Out Execution ---

    async def fan_out(
        self,
        tasks: list[dict[str, Any]],
        mode: str = "all",
        timeout: float = 120.0,
    ) -> FanOutResult:
        """Execute multiple tasks in parallel across multiple agents.

        Modes: "all", "race", "quorum", "best"
        """
        if self._parallel_executor is None:
            raise RuntimeError("Parallel executor not initialized.")

        return await self._parallel_executor.fan_out(
            tasks=tasks,
            mode=mode,
            timeout=timeout,
        )

    # --- Integration Point 6: Consensus Voting ---

    async def vote_on_results(
        self,
        results: list[dict[str, Any]],
        strategy: str = VotingStrategy.WEIGHTED_CONFIDENCE,
        required_capabilities: set[str] | None = None,
    ):
        """Run a consensus vote on results from multiple agents."""
        return self.consensus.vote(
            votes=results,
            strategy=strategy,
            required_capabilities=required_capabilities,
        )

    # --- Integration Point 7: Agent Communication ---

    async def send_agent_message(
        self,
        *,
        sender: str,
        recipient: str,
        payload: dict[str, Any],
        message_type: str = MessageType.DIRECT,
    ):
        """Send a message from one agent to another."""
        return await self.message_bus.send(
            sender=sender,
            recipient=recipient,
            payload=payload,
            message_type=message_type,
        )

    async def request_from_agent(
        self,
        *,
        sender: str,
        recipient: str,
        payload: dict[str, Any],
        timeout: float = 60.0,
    ):
        """Send a request to an agent and wait for a reply (RPC-style)."""
        return await self.message_bus.request(
            sender=sender,
            recipient=recipient,
            payload=payload,
            timeout=timeout,
        )

    # --- Internal ---

    async def _on_blackboard_change(self, entry) -> None:
        """React to blackboard changes — this is where coordination logic lives."""
        if entry.section == "results" and entry.tags and "result" in entry.tags:
            # A task result was posted — notify supervisor
            for tag in entry.tags:
                if tag.startswith("task:"):
                    task_id = tag[5:]
                    with contextlib.suppress(ValueError, KeyError):
                        await self.supervisor.report_result(
                            session_id=self._session_id,
                            task_id=task_id,
                            result=entry.value,
                            confidence=entry.confidence,
                            agent_id=entry.author_agent_id,
                        )

    async def get_status(self) -> dict[str, Any]:
        """Get the full status of the coordination bridge."""
        blackboard_snapshot = await self.blackboard.snapshot()
        bus_stats = await self.message_bus.stats()
        supervisor_status = await self.supervisor.get_session_status(self._session_id)

        return {
            "session_id": self._session_id,
            "initialized": self._initialized,
            "blackboard": blackboard_snapshot,
            "message_bus": bus_stats,
            "supervisor": supervisor_status,
            "confidence_report": self.confidence_router.get_confidence_report(),
        }
