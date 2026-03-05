"""Parallel Fan-Out/Fan-In Executor: Strategic parallel agent execution.

Replaces the current sequential-only execution model with:
- Fan-Out: Distribute independent tasks to multiple agents simultaneously
- Fan-In: Aggregate results when all (or enough) agents complete
- DAG Execution: Execute PlanGraph steps respecting dependency order
- Race Mode: First agent to complete wins (for competitive strategies)
- Quorum: Accept result when N out of M agents agree
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Callable, Awaitable
from uuid import uuid4

logger = logging.getLogger(__name__)

AgentExecutor = Callable[[str, str, dict[str, Any]], Awaitable[dict[str, Any]]]
# AgentExecutor(agent_id, task_description, context) -> {"result": ..., "confidence": float}


class FanOutMode(StrEnum):
    ALL = "all"           # Wait for all agents to complete
    RACE = "race"         # First agent to complete wins
    QUORUM = "quorum"     # Accept when N agree
    BEST = "best"         # Wait for all, pick highest confidence


@dataclass
class FanOutTask:
    """A single task in a fan-out execution."""
    task_id: str
    agent_id: str
    description: str
    context: dict[str, Any]
    status: str = "pending"       # pending, running, completed, failed, cancelled
    result: Any = None
    confidence: float = 0.0
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: float = 0.0


@dataclass(frozen=True)
class FanOutResult:
    """The aggregated result of a fan-out execution."""
    mode: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    results: list[dict[str, Any]]     # [{agent_id, result, confidence}, ...]
    best_result: dict[str, Any] | None  # highest confidence result
    aggregate_confidence: float
    duration_ms: float
    consensus_reached: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DAGStep:
    """A step in a dependency graph with agent assignment."""
    step_id: str
    agent_id: str
    description: str
    depends_on: list[str]
    context: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    result: Any = None
    confidence: float = 0.0
    error: str | None = None
    can_parallel: bool = False     # True if this step can run in parallel with peers


class ParallelFanOutExecutor:
    """Executes multiple agent tasks in parallel with various aggregation strategies.
    
    Key capabilities:
    - Fan-Out/Fan-In: Send same or different tasks to multiple agents simultaneously
    - DAG Execution: Execute a dependency graph of tasks, parallelizing where possible
    - Race Mode: First agent to complete wins
    - Quorum: Accept when enough agents agree on the same result
    - Best-of-N: Run all agents, pick the result with highest confidence
    """

    def __init__(
        self,
        *,
        executor: AgentExecutor,
        max_concurrent: int = 5,
        default_timeout: float = 120.0,
        quorum_threshold: int = 2,    # number of agreeing agents for quorum
    ):
        self._executor = executor
        self._semaphore = asyncio.Semaphore(max(1, max_concurrent))
        self._default_timeout = max(1.0, default_timeout)
        self._quorum_threshold = max(1, quorum_threshold)

    async def fan_out(
        self,
        *,
        tasks: list[dict[str, Any]],
        mode: str = FanOutMode.ALL,
        timeout: float | None = None,
    ) -> FanOutResult:
        """Execute multiple tasks in parallel and aggregate results.
        
        Each task should have:
        - "agent_id": str
        - "description": str
        - "context": dict (optional)
        """
        effective_timeout = timeout or self._default_timeout
        start_time = asyncio.get_running_loop().time()

        fan_tasks: list[FanOutTask] = []
        for task_dict in tasks:
            fan_tasks.append(FanOutTask(
                task_id=str(uuid4())[:8],
                agent_id=str(task_dict.get("agent_id", "")),
                description=str(task_dict.get("description", "")),
                context=dict(task_dict.get("context", {})),
            ))

        if mode == FanOutMode.RACE:
            result = await self._execute_race(fan_tasks, timeout=effective_timeout)
        elif mode == FanOutMode.QUORUM:
            result = await self._execute_quorum(fan_tasks, timeout=effective_timeout)
        elif mode == FanOutMode.BEST:
            result = await self._execute_best(fan_tasks, timeout=effective_timeout)
        else:
            result = await self._execute_all(fan_tasks, timeout=effective_timeout)

        elapsed = (asyncio.get_running_loop().time() - start_time) * 1000
        return FanOutResult(
            mode=mode,
            total_tasks=len(fan_tasks),
            completed_tasks=sum(1 for t in fan_tasks if t.status == "completed"),
            failed_tasks=sum(1 for t in fan_tasks if t.status == "failed"),
            results=[
                {
                    "agent_id": t.agent_id,
                    "task_id": t.task_id,
                    "result": t.result,
                    "confidence": t.confidence,
                    "status": t.status,
                    "duration_ms": t.duration_ms,
                }
                for t in fan_tasks
            ],
            best_result=result,
            aggregate_confidence=self._aggregate_confidence(fan_tasks),
            duration_ms=elapsed,
            consensus_reached=self._check_consensus(fan_tasks),
        )

    async def execute_dag(
        self,
        *,
        steps: list[DAGStep],
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a dependency graph of tasks, parallelizing independent steps.
        
        This is the PlanGraph executor that's missing from the current system.
        The PlanGraph has depends_on fields but is currently converted to a string
        and executed sequentially. This executes it as a real DAG.
        """
        effective_timeout = timeout or self._default_timeout
        completed_ids: set[str] = set()
        all_results: list[dict[str, Any]] = []
        step_map = {s.step_id: s for s in steps}

        while True:
            # Find steps whose dependencies are all satisfied
            ready = [
                s for s in steps
                if s.status == "pending"
                and all(dep in completed_ids for dep in s.depends_on)
            ]

            if not ready:
                # Check if we're done or stuck
                still_pending = [s for s in steps if s.status in ("pending", "running")]
                if not still_pending:
                    break
                # If running tasks exist, wait for them
                running = [s for s in steps if s.status == "running"]
                if not running:
                    # Stuck: dependencies can never be satisfied
                    for stuck in still_pending:
                        stuck.status = "failed"
                        stuck.error = f"Dependency deadlock: depends_on={stuck.depends_on}"
                    break
                await asyncio.sleep(0.1)
                continue

            # Execute all ready steps in parallel
            async_tasks = []
            for step in ready:
                step.status = "running"
                # Inject results of dependencies into context
                dep_results = {}
                for dep_id in step.depends_on:
                    dep_step = step_map.get(dep_id)
                    if dep_step and dep_step.result is not None:
                        dep_results[dep_id] = dep_step.result
                step.context["dependency_results"] = dep_results

                async_tasks.append(self._execute_single_step(step, timeout=effective_timeout))

            step_results = await asyncio.gather(*async_tasks, return_exceptions=True)

            for step, step_result in zip(ready, step_results):
                if isinstance(step_result, Exception):
                    step.status = "failed"
                    step.error = str(step_result)
                else:
                    completed_ids.add(step.step_id)

                all_results.append({
                    "step_id": step.step_id,
                    "agent_id": step.agent_id,
                    "status": step.status,
                    "result": step.result,
                    "confidence": step.confidence,
                    "error": step.error,
                })

        return all_results

    async def _execute_single(
        self,
        task: FanOutTask,
        timeout: float,
    ) -> dict[str, Any] | None:
        """Execute a single fan-out task with semaphore and timeout."""
        async with self._semaphore:
            task.status = "running"
            task.started_at = datetime.now(timezone.utc).isoformat()
            start = asyncio.get_running_loop().time()

            try:
                result = await asyncio.wait_for(
                    self._executor(task.agent_id, task.description, task.context),
                    timeout=timeout,
                )
                task.status = "completed"
                task.result = result.get("result")
                task.confidence = float(result.get("confidence", 0.0))
                task.completed_at = datetime.now(timezone.utc).isoformat()
                task.duration_ms = (asyncio.get_running_loop().time() - start) * 1000
                return {
                    "agent_id": task.agent_id,
                    "result": task.result,
                    "confidence": task.confidence,
                }
            except asyncio.TimeoutError:
                task.status = "failed"
                task.error = "timeout"
                task.duration_ms = (asyncio.get_running_loop().time() - start) * 1000
                return None
            except asyncio.CancelledError:
                task.status = "cancelled"
                raise
            except Exception as exc:
                task.status = "failed"
                task.error = str(exc)
                task.duration_ms = (asyncio.get_running_loop().time() - start) * 1000
                logger.exception("Fan-out task failed: agent=%s", task.agent_id)
                return None

    async def _execute_single_step(
        self,
        step: DAGStep,
        timeout: float,
    ) -> dict[str, Any] | None:
        """Execute a single DAG step."""
        async with self._semaphore:
            start = asyncio.get_running_loop().time()
            try:
                result = await asyncio.wait_for(
                    self._executor(step.agent_id, step.description, step.context),
                    timeout=timeout,
                )
                step.status = "completed"
                step.result = result.get("result")
                step.confidence = float(result.get("confidence", 0.0))
                return result
            except asyncio.TimeoutError:
                step.status = "failed"
                step.error = "timeout"
                return None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                step.status = "failed"
                step.error = str(exc)
                return None

    async def _execute_all(
        self,
        tasks: list[FanOutTask],
        timeout: float,
    ) -> dict[str, Any] | None:
        """Execute all tasks and wait for all to complete."""
        results = await asyncio.gather(
            *[self._execute_single(task, timeout) for task in tasks],
            return_exceptions=True,
        )

        valid_results = [r for r in results if isinstance(r, dict)]
        if valid_results:
            # Return the one with highest confidence
            return max(valid_results, key=lambda r: r.get("confidence", 0.0))
        return None

    async def _execute_race(
        self,
        tasks: list[FanOutTask],
        timeout: float,
    ) -> dict[str, Any] | None:
        """Execute all tasks, return first to complete successfully."""
        done_event = asyncio.Event()
        winner: dict[str, Any] | None = None

        async def race_task(task: FanOutTask) -> None:
            nonlocal winner
            result = await self._execute_single(task, timeout)
            if result is not None and winner is None:
                winner = result
                done_event.set()

        async_tasks = [asyncio.create_task(race_task(t)) for t in tasks]

        try:
            await asyncio.wait_for(done_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

        # Cancel remaining tasks
        for at in async_tasks:
            if not at.done():
                at.cancel()
        await asyncio.gather(*async_tasks, return_exceptions=True)

        # Mark non-completed tasks as cancelled
        for t in tasks:
            if t.status == "running":
                t.status = "cancelled"

        return winner

    async def _execute_quorum(
        self,
        tasks: list[FanOutTask],
        timeout: float,
    ) -> dict[str, Any] | None:
        """Execute all tasks, accept when quorum_threshold agents agree."""
        # Run all tasks
        await self._execute_all(tasks, timeout)

        # Check for agreement (simplified: compare result strings)
        result_groups: dict[str, list[FanOutTask]] = {}
        for task in tasks:
            if task.status == "completed" and task.result is not None:
                key = str(task.result)[:200]
                result_groups.setdefault(key, []).append(task)

        for group_key, group_tasks in result_groups.items():
            if len(group_tasks) >= self._quorum_threshold:
                best = max(group_tasks, key=lambda t: t.confidence)
                return {
                    "agent_id": best.agent_id,
                    "result": best.result,
                    "confidence": best.confidence,
                    "quorum_size": len(group_tasks),
                }

        # No quorum reached — return highest confidence
        completed = [t for t in tasks if t.status == "completed"]
        if completed:
            best = max(completed, key=lambda t: t.confidence)
            return {
                "agent_id": best.agent_id,
                "result": best.result,
                "confidence": best.confidence,
                "quorum_size": 1,
            }
        return None

    async def _execute_best(
        self,
        tasks: list[FanOutTask],
        timeout: float,
    ) -> dict[str, Any] | None:
        """Execute all tasks, return the one with highest confidence."""
        return await self._execute_all(tasks, timeout)

    @staticmethod
    def _aggregate_confidence(tasks: list[FanOutTask]) -> float:
        """Calculate aggregate confidence from all completed tasks."""
        completed = [t for t in tasks if t.status == "completed"]
        if not completed:
            return 0.0
        return sum(t.confidence for t in completed) / len(completed)

    @staticmethod
    def _check_consensus(tasks: list[FanOutTask]) -> bool:
        """Check if all completed tasks agree on the result."""
        completed = [t for t in tasks if t.status == "completed" and t.result is not None]
        if len(completed) < 2:
            return len(completed) == 1

        first_result = str(completed[0].result)[:200]
        return all(str(t.result)[:200] == first_result for t in completed[1:])
