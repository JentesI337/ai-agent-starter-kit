"""
Orchestrator — constraint-first, model-agnostic orchestration system.

Core responsibilities:
  - Owns all state (models never do)
  - Routes tasks to models via capability profiles (never hardcoded)
  - Enforces agent contracts (input/output validation)
  - Manages task graph and execution flow
  - Provides structured retry logic (no silent failures)
  - Creates snapshots for state rehydration

Design principles:
  - Logic lives in code — models are reasoning engines only
  - External state is the single source of truth
  - Flows are linear and deterministic (Phase 1)
  - Scale is an upgrade, not a rebuild
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from app.llm_client import LlmClient
from app.orchestrator.agents.coder import CoderAgent
from app.orchestrator.agents.planner import PlannerAgent
from app.orchestrator.agents.reviewer import ReviewerAgent
from app.orchestrator.contracts.schemas import (
    AgentRole,
    CoderInput,
    CoderOutput,
    ModelCapabilityProfile,
    PlannerInput,
    PlannerOutput,
    ReviewerInput,
    ReviewerOutput,
    RoutingRequest,
    TaskComplexity,
    TaskEnvelope,
    TaskStatus,
)
from app.orchestrator.contracts.validators import (
    ContractValidationError,
    validate_input,
    validate_output,
)
from app.orchestrator.routing.capability_router import CapabilityRouter
from app.orchestrator.state.context_reducer import ContextChunk, ContextReducer
from app.orchestrator.state.snapshots import SnapshotManager
from app.orchestrator.state.store import StateStore
from app.orchestrator.state.task_graph import CyclicDependencyError, TaskGraph

logger = logging.getLogger(__name__)

SendEvent = Callable[[dict], Awaitable[None]]


class OrchestratorError(Exception):
    """Raised when the orchestrator encounters an unrecoverable error."""
    pass


class Orchestrator:
    """
    Central orchestration engine.

    The orchestrator:
    1. Receives a user request
    2. Routes to planner agent (model selected by capability, not name)
    3. Decomposes into task graph
    4. Executes tasks via coder agent (model selected per-task)
    5. Optionally reviews via reviewer agent
    6. Manages retries, state, and snapshots throughout

    All state is external. Models receive slices only.
    """

    def __init__(
        self,
        llm_client: LlmClient,
        state_persist_path: str | None = None,
        snapshots_dir: str | None = None,
        models_config_path: str | None = None,
        routing_rules_path: str | None = None,
    ):
        self._llm_client = llm_client

        # State management — fully external, orchestrator-owned
        self._store = StateStore(persist_path=state_persist_path)
        self._graph = TaskGraph()
        self._reducer = ContextReducer()
        self._snapshots = SnapshotManager(persist_dir=snapshots_dir)

        # Capability router — model selection by task, not by name
        self._router = CapabilityRouter(
            models_config_path=models_config_path,
            routing_rules_path=routing_rules_path,
        )

        # Stateless agents — strict contracts, no hidden assumptions  
        self._planner = PlannerAgent()
        self._coder = CoderAgent()
        self._reviewer = ReviewerAgent()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model_override: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute a full orchestration cycle for a user request.

        Returns a result dict with the final output and metadata.
        """
        logger.info(
            "orchestrator_run_start request_id=%s session_id=%s",
            request_id,
            session_id,
        )
        await self._emit(send_event, "orchestrator_started", request_id, session_id)

        try:
            # Phase 1: Planning
            plan = await self._run_planning(
                user_message=user_message,
                send_event=send_event,
                session_id=session_id,
                request_id=request_id,
                model_override=model_override,
            )

            # Phase 2: Build task graph from plan
            task_ids = self._build_task_graph(plan, request_id)

            # Phase 3: Execute tasks
            results = await self._execute_task_graph(
                plan=plan,
                task_ids=task_ids,
                user_message=user_message,
                send_event=send_event,
                session_id=session_id,
                request_id=request_id,
                model_override=model_override,
            )

            # Phase 4: Optional review (only if model tier supports it)
            review = None
            if results and plan.estimated_complexity != TaskComplexity.SIMPLE:
                review = await self._run_review(
                    plan=plan,
                    coder_output=results[-1] if results else CoderOutput(),
                    user_message=user_message,
                    send_event=send_event,
                    session_id=session_id,
                    request_id=request_id,
                    model_override=model_override,
                )

            # Snapshot state
            all_tasks = self._store.list_tasks()
            self._snapshots.create_snapshot(
                snapshot_id=request_id,
                tasks=all_tasks,
                metadata={"user_message": user_message[:200], "session_id": session_id},
                graph_summary=self._graph.summary(),
            )

            await self._emit(send_event, "orchestrator_completed", request_id, session_id)

            return {
                "request_id": request_id,
                "plan": plan.model_dump(mode="json"),
                "results": [r.model_dump(mode="json") for r in results],
                "review": review.model_dump(mode="json") if review else None,
                "graph_summary": self._graph.summary(),
                "success": not self._graph.has_failures(),
            }

        except Exception as exc:
            logger.exception("orchestrator_run_failed request_id=%s", request_id)
            await self._emit(
                send_event,
                "orchestrator_error",
                request_id,
                session_id,
                details={"error": str(exc)},
            )
            raise OrchestratorError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Planning phase
    # ------------------------------------------------------------------

    async def _run_planning(
        self,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model_override: str | None = None,
    ) -> PlannerOutput:
        """Run the planner agent to decompose the user request."""
        await self._emit(send_event, "planning_started", request_id, session_id)

        # Determine complexity hint from message length / structure
        complexity_hint = self._estimate_complexity(user_message)

        # Build and validate input
        planner_input_data = {
            "user_message": user_message,
            "context_summary": self._store.get_session_summary().get("total_tasks", 0)
            and json.dumps(self._store.get_session_summary(), default=str)
            or "",
            "task_complexity": complexity_hint.value,
        }
        validated_input = validate_input(AgentRole.PLANNER, planner_input_data)
        assert isinstance(validated_input, PlannerInput)

        # Route to appropriate model
        routing_result = self._route_task(
            complexity=complexity_hint,
            context_text=user_message,
            model_override=model_override,
        )
        selected_model = routing_result.selected_model

        await self._emit(
            send_event,
            "model_selected",
            request_id,
            session_id,
            details={
                "model": selected_model.model_id,
                "tier": selected_model.tier.value,
                "reason": routing_result.reason,
            },
        )

        # Build prompt and call LLM
        system_prompt, user_prompt = self._planner.build_prompt(validated_input)

        # Reduce context to fit model's budget
        reduced = self._reducer.reduce(
            [ContextChunk(label="user_prompt", content=user_prompt, priority=10.0)],
            token_budget=selected_model.max_context,
            reserve_tokens=self._reducer.estimate_tokens(system_prompt) + 512,
        )

        raw_response = await self._call_llm(
            system_prompt=system_prompt,
            user_prompt=reduced.text,
            model_id=selected_model.model_id if not model_override else model_override,
        )

        # Parse and validate output
        plan = self._planner.parse_output(raw_response)
        validate_output(AgentRole.PLANNER, plan.model_dump(mode="json"))

        await self._emit(
            send_event,
            "planning_completed",
            request_id,
            session_id,
            details={
                "steps": len(plan.steps),
                "complexity": plan.estimated_complexity.value,
            },
        )

        return plan

    # ------------------------------------------------------------------
    # Task graph construction
    # ------------------------------------------------------------------

    def _build_task_graph(self, plan: PlannerOutput, request_id: str) -> list[str]:
        """Convert plan steps into tasks in the state store and graph."""
        task_ids: list[str] = []
        step_to_task: dict[int, str] = {}

        for step in plan.steps:
            task_id = self._store.generate_task_id()
            step_to_task[step.step_id] = task_id

            # Map step dependencies to task_id dependencies
            depends_on = [
                step_to_task[dep_id]
                for dep_id in step.depends_on
                if dep_id in step_to_task
            ]

            envelope = TaskEnvelope(
                task_id=task_id,
                status=TaskStatus.PENDING,
                agent_role=AgentRole.CODER,
                input_data=step.model_dump(mode="json"),
                depends_on=depends_on,
                parent_task_id=request_id,
            )
            self._store.create_task(envelope)
            self._graph.add_task(task_id, depends_on=depends_on)
            task_ids.append(task_id)

        logger.info("task_graph built tasks=%d for request=%s", len(task_ids), request_id)
        return task_ids

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------

    async def _execute_task_graph(
        self,
        plan: PlannerOutput,
        task_ids: list[str],
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model_override: str | None = None,
    ) -> list[CoderOutput]:
        """Execute all tasks in the graph in dependency order."""
        results: list[CoderOutput] = []

        while not self._graph.is_complete():
            ready = self._graph.get_ready_tasks()
            if not ready:
                if self._graph.has_failures():
                    logger.warning("task_graph has failures, stopping execution")
                    break
                # Possible deadlock — all remaining tasks blocked
                blocked = self._graph.get_blocked_tasks()
                if blocked:
                    logger.error("task_graph deadlock blocked=%s", blocked)
                    for tid in blocked:
                        self._graph.set_status(tid, TaskStatus.FAILED)
                        self._store.update_task(tid, status=TaskStatus.FAILED, error="Deadlocked")
                    break
                break

            # Execute ready tasks sequentially (Phase 1: linear flows)
            for task_id in ready:
                result = await self._execute_single_task(
                    task_id=task_id,
                    user_message=user_message,
                    send_event=send_event,
                    session_id=session_id,
                    request_id=request_id,
                    model_override=model_override,
                )
                if result:
                    results.append(result)

        return results

    async def _execute_single_task(
        self,
        task_id: str,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model_override: str | None = None,
    ) -> CoderOutput | None:
        """Execute a single task with structured retry logic."""
        task = self._store.get_task(task_id)
        if task is None:
            return None

        self._graph.set_status(task_id, TaskStatus.ACTIVE)
        self._store.update_task(task_id, status=TaskStatus.ACTIVE)

        await self._emit(
            send_event,
            "task_started",
            request_id,
            session_id,
            details={"task_id": task_id, "step": task.input_data.get("description", "")},
        )

        last_error: str | None = None
        for attempt in range(1, task.max_retries + 2):  # +2 because range is exclusive and we start at 1
            try:
                result = await self._invoke_coder(
                    task=task,
                    user_message=user_message,
                    model_override=model_override,
                )

                if result.success:
                    self._graph.set_status(task_id, TaskStatus.COMPLETED)
                    self._store.update_task(
                        task_id,
                        status=TaskStatus.COMPLETED,
                        output_data=result.model_dump(mode="json"),
                    )
                    await self._emit(
                        send_event,
                        "task_completed",
                        request_id,
                        session_id,
                        details={"task_id": task_id, "attempt": attempt},
                    )
                    return result

                # Coder reported failure — retry if allowed
                last_error = result.error or "Coder reported failure"
                logger.warning(
                    "task_attempt_failed task_id=%s attempt=%d error=%s",
                    task_id,
                    attempt,
                    last_error,
                )

            except ContractValidationError as exc:
                last_error = str(exc)
                logger.warning(
                    "task_contract_violation task_id=%s attempt=%d error=%s",
                    task_id,
                    attempt,
                    last_error,
                )
            except Exception as exc:
                last_error = str(exc)
                logger.exception(
                    "task_execution_error task_id=%s attempt=%d",
                    task_id,
                    attempt,
                )

            self._store.update_task(task_id, retries=attempt)

        # All retries exhausted
        self._graph.set_status(task_id, TaskStatus.FAILED)
        self._store.update_task(
            task_id,
            status=TaskStatus.FAILED,
            error=last_error or "Max retries exhausted",
        )
        await self._emit(
            send_event,
            "task_failed",
            request_id,
            session_id,
            details={"task_id": task_id, "error": last_error},
        )
        return None

    async def _invoke_coder(
        self,
        task: TaskEnvelope,
        user_message: str,
        model_override: str | None = None,
    ) -> CoderOutput:
        """Invoke the coder agent for a single task."""
        from app.orchestrator.contracts.schemas import PlanStep

        step = PlanStep.model_validate(task.input_data)

        # Estimate complexity from step description
        complexity = self._estimate_complexity(step.description)

        # Route model
        routing_result = self._route_task(
            complexity=complexity,
            context_text=step.description,
            model_override=model_override,
        )
        selected_model = routing_result.selected_model

        # Build coder input
        coder_input_data = {
            "plan_step": step.model_dump(mode="json"),
            "context_summary": json.dumps(self._store.get_session_summary(), default=str),
        }
        validated_input = validate_input(AgentRole.CODER, coder_input_data)
        assert isinstance(validated_input, CoderInput)

        # Build prompt
        system_prompt, user_prompt = self._coder.build_prompt(validated_input)

        # Reduce context
        reduced = self._reducer.reduce(
            [ContextChunk(label="coder_prompt", content=user_prompt, priority=10.0)],
            token_budget=selected_model.max_context,
            reserve_tokens=self._reducer.estimate_tokens(system_prompt) + 512,
        )

        raw_response = await self._call_llm(
            system_prompt=system_prompt,
            user_prompt=reduced.text,
            model_id=selected_model.model_id if not model_override else model_override,
        )

        output = self._coder.parse_output(raw_response)
        validate_output(AgentRole.CODER, output.model_dump(mode="json"))
        return output

    # ------------------------------------------------------------------
    # Review phase
    # ------------------------------------------------------------------

    async def _run_review(
        self,
        plan: PlannerOutput,
        coder_output: CoderOutput,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model_override: str | None = None,
    ) -> ReviewerOutput | None:
        """Run the reviewer agent if the model tier supports it."""
        routing_result = self._route_task(
            complexity=plan.estimated_complexity,
            context_text=user_message,
            model_override=model_override,
            require_reflection=True,
        )
        selected_model = routing_result.selected_model

        # Only review if model supports reflection
        if selected_model.reflection_passes < 1:
            logger.info("review_skipped model=%s no_reflection_support", selected_model.model_id)
            return None

        await self._emit(send_event, "review_started", request_id, session_id)

        reviewer_input_data = {
            "plan": plan.model_dump(mode="json"),
            "coder_output": coder_output.model_dump(mode="json"),
            "original_request": user_message[:2000],
        }
        validated_input = validate_input(AgentRole.REVIEWER, reviewer_input_data)
        assert isinstance(validated_input, ReviewerInput)

        system_prompt, user_prompt = self._reviewer.build_prompt(validated_input)

        reduced = self._reducer.reduce(
            [ContextChunk(label="review_prompt", content=user_prompt, priority=10.0)],
            token_budget=selected_model.max_context,
            reserve_tokens=self._reducer.estimate_tokens(system_prompt) + 512,
        )

        raw_response = await self._call_llm(
            system_prompt=system_prompt,
            user_prompt=reduced.text,
            model_id=selected_model.model_id if not model_override else model_override,
        )

        review = self._reviewer.parse_output(raw_response)
        validate_output(AgentRole.REVIEWER, review.model_dump(mode="json"))

        await self._emit(
            send_event,
            "review_completed",
            request_id,
            session_id,
            details={
                "approved": review.approved,
                "confidence": review.confidence_score,
                "issues": len(review.issues),
            },
        )

        return review

    # ------------------------------------------------------------------
    # Model routing
    # ------------------------------------------------------------------

    def _route_task(
        self,
        complexity: TaskComplexity,
        context_text: str,
        model_override: str | None = None,
        confidence: float = 1.0,
        budget: float = float("inf"),
        require_reflection: bool = False,
    ):
        """Route a task to a model via the capability router."""
        context_tokens = self._reducer.estimate_tokens(context_text)

        request = RoutingRequest(
            task_complexity=complexity,
            context_size=context_tokens,
            confidence_score=confidence,
            budget_threshold=budget,
            required_reflection=require_reflection,
        )

        return self._router.route(request)

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        model_id: str | None = None,
    ) -> str:
        """
        Call the LLM and collect the full streamed response.
        The model receives a slice of state — never the full store.
        """
        tokens: list[str] = []
        async for token in self._llm_client.stream_chat_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model_id,
        ):
            tokens.append(token)
        return "".join(tokens)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_complexity(text: str) -> TaskComplexity:
        """
        Quick heuristic to estimate task complexity from text.
        Not a model call — pure code logic.
        """
        text_lower = text.lower()
        length = len(text)

        complex_signals = [
            "refactor",
            "architect",
            "security",
            "audit",
            "redesign",
            "migration",
            "multi-step",
            "complex",
        ]
        moderate_signals = [
            "implement",
            "create",
            "add feature",
            "modify",
            "update",
            "fix bug",
            "dependency",
        ]

        complex_score = sum(1 for s in complex_signals if s in text_lower)
        moderate_score = sum(1 for s in moderate_signals if s in text_lower)

        if complex_score >= 2 or length > 2000:
            return TaskComplexity.COMPLEX
        if moderate_score >= 1 or complex_score >= 1 or length > 800:
            return TaskComplexity.MODERATE
        return TaskComplexity.SIMPLE

    async def _emit(
        self,
        send_event: SendEvent,
        stage: str,
        request_id: str,
        session_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Emit a lifecycle event."""
        event = {
            "type": "orchestrator_lifecycle",
            "stage": stage,
            "request_id": request_id,
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if details:
            event["details"] = details
        try:
            await send_event(event)
        except Exception:
            logger.debug("emit_failed stage=%s", stage)

    # ------------------------------------------------------------------
    # State access for external callers
    # ------------------------------------------------------------------

    @property
    def store(self) -> StateStore:
        return self._store

    @property
    def graph(self) -> TaskGraph:
        return self._graph

    @property
    def router(self) -> CapabilityRouter:
        return self._router

    def get_snapshot_context(self, snapshot_id: str) -> str:
        """Get rehydration context from a snapshot."""
        return self._snapshots.get_rehydration_context(snapshot_id)
