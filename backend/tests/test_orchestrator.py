"""
Tests for the orchestrator system.

Covers:
  - Agent contracts & validation
  - State store CRUD
  - Task graph (dependencies, topological order, cycle detection)
  - Context reducer (budget enforcement, priority ordering)
  - Capability router (tier selection, escalation, budget constraints)
  - Snapshot creation & rehydration
"""
from __future__ import annotations

import json
import pytest

from app.orchestrator.contracts.schemas import (
    AgentConstraints,
    AgentContract,
    AgentRole,
    CoderInput,
    CoderOutput,
    ModelCapabilityProfile,
    ModelTier,
    PlannerInput,
    PlannerOutput,
    PlanStep,
    ReviewerInput,
    ReviewerOutput,
    RoutingRequest,
    TaskComplexity,
    TaskEnvelope,
    TaskStatus,
)
from app.orchestrator.contracts.validators import (
    ContractValidationError,
    validate_contract,
    validate_input,
    validate_output,
)
from app.orchestrator.state.store import StateStore
from app.orchestrator.state.task_graph import CyclicDependencyError, TaskGraph
from app.orchestrator.state.context_reducer import (
    ContextChunk,
    ContextReducer,
    ReducedContext,
)
from app.orchestrator.state.snapshots import SnapshotManager, StateSnapshot
from app.orchestrator.routing.capability_router import CapabilityRouter
from app.orchestrator.agents.planner import PlannerAgent
from app.orchestrator.agents.coder import CoderAgent
from app.orchestrator.agents.reviewer import ReviewerAgent


# ======================================================================
# Contract & Validation Tests
# ======================================================================

class TestSchemas:
    def test_planner_input_creation(self):
        inp = PlannerInput(user_message="Create a hello world app")
        assert inp.user_message == "Create a hello world app"
        assert inp.task_complexity == TaskComplexity.SIMPLE

    def test_planner_output_creation(self):
        out = PlannerOutput(
            steps=[PlanStep(step_id=1, description="Create main.py")],
            estimated_complexity=TaskComplexity.SIMPLE,
        )
        assert len(out.steps) == 1
        assert out.steps[0].step_id == 1

    def test_coder_output_with_changes(self):
        out = CoderOutput(
            changes=[{"path": "main.py", "action": "write", "content": "print('hi')"}],
            success=True,
        )
        assert out.success
        assert len(out.changes) == 1

    def test_model_capability_profile(self):
        profile = ModelCapabilityProfile(
            model_id="test-7b",
            tier=ModelTier.SMALL,
            max_context=4096,
        )
        assert profile.tier == ModelTier.SMALL
        assert profile.reflection_passes == 0

    def test_task_envelope_defaults(self):
        env = TaskEnvelope(task_id="t-1")
        assert env.status == TaskStatus.PENDING
        assert env.agent_role == AgentRole.PLANNER
        assert env.retries == 0


class TestValidators:
    def test_validate_planner_input_success(self):
        result = validate_input(AgentRole.PLANNER, {"user_message": "Hello"})
        assert isinstance(result, PlannerInput)

    def test_validate_planner_input_missing_field(self):
        with pytest.raises(ContractValidationError) as exc_info:
            validate_input(AgentRole.PLANNER, {})
        assert exc_info.value.direction == "input"

    def test_validate_planner_output_success(self):
        data = {
            "steps": [{"step_id": 1, "description": "test"}],
            "estimated_complexity": "simple",
        }
        result = validate_output(AgentRole.PLANNER, data)
        assert isinstance(result, PlannerOutput)

    def test_validate_coder_output_success(self):
        data = {"changes": [], "success": True}
        result = validate_output(AgentRole.CODER, data)
        assert isinstance(result, CoderOutput)

    def test_validate_contract_warnings(self):
        contract = AgentContract(
            role=AgentRole.PLANNER,
            constraints=AgentConstraints(max_context_tokens=256, temperature=1.5, max_reflection_passes=2),
        )
        issues = validate_contract(contract)
        assert len(issues) >= 1  # Low context + high temp with reflection


# ======================================================================
# State Store Tests
# ======================================================================

class TestStateStore:
    def test_create_and_get_task(self):
        store = StateStore()
        env = TaskEnvelope(task_id="t-1", agent_role=AgentRole.CODER)
        store.create_task(env)
        retrieved = store.get_task("t-1")
        assert retrieved is not None
        assert retrieved.task_id == "t-1"

    def test_create_duplicate_raises(self):
        store = StateStore()
        env = TaskEnvelope(task_id="t-1")
        store.create_task(env)
        with pytest.raises(ValueError):
            store.create_task(env)

    def test_update_task(self):
        store = StateStore()
        store.create_task(TaskEnvelope(task_id="t-1"))
        updated = store.update_task("t-1", status=TaskStatus.COMPLETED)
        assert updated.status == TaskStatus.COMPLETED

    def test_update_nonexistent_raises(self):
        store = StateStore()
        with pytest.raises(KeyError):
            store.update_task("nonexistent", status=TaskStatus.ACTIVE)

    def test_delete_task(self):
        store = StateStore()
        store.create_task(TaskEnvelope(task_id="t-1"))
        assert store.delete_task("t-1")
        assert store.get_task("t-1") is None

    def test_list_tasks_by_status(self):
        store = StateStore()
        store.create_task(TaskEnvelope(task_id="t-1", status=TaskStatus.PENDING))
        store.create_task(TaskEnvelope(task_id="t-2", status=TaskStatus.COMPLETED))
        store.create_task(TaskEnvelope(task_id="t-3", status=TaskStatus.PENDING))
        pending = store.list_tasks(status=TaskStatus.PENDING)
        assert len(pending) == 2

    def test_metadata(self):
        store = StateStore()
        store.set_meta("key1", "value1")
        assert store.get_meta("key1") == "value1"
        assert store.get_meta("missing", "default") == "default"

    def test_task_slice(self):
        store = StateStore()
        store.create_task(TaskEnvelope(task_id="t-1", agent_role=AgentRole.CODER))
        s = store.get_task_slice("t-1")
        assert s["task_id"] == "t-1"
        assert s["agent_role"] == "coder"
        assert "input_data" in s

    def test_session_summary(self):
        store = StateStore()
        store.create_task(TaskEnvelope(task_id="t-1", status=TaskStatus.PENDING))
        store.create_task(TaskEnvelope(task_id="t-2", status=TaskStatus.COMPLETED))
        summary = store.get_session_summary()
        assert summary["total_tasks"] == 2
        assert summary["by_status"]["pending"] == 1

    def test_clear(self):
        store = StateStore()
        store.create_task(TaskEnvelope(task_id="t-1"))
        store.set_meta("k", "v")
        store.clear()
        assert store.count_tasks() == 0
        assert store.get_meta("k") is None


# ======================================================================
# Task Graph Tests
# ======================================================================

class TestTaskGraph:
    def test_add_task_no_deps(self):
        graph = TaskGraph()
        graph.add_task("t-1")
        assert graph.get_status("t-1") == TaskStatus.PENDING

    def test_ready_tasks_no_deps(self):
        graph = TaskGraph()
        graph.add_task("t-1")
        graph.add_task("t-2")
        ready = graph.get_ready_tasks()
        assert set(ready) == {"t-1", "t-2"}

    def test_dependency_blocks_task(self):
        graph = TaskGraph()
        graph.add_task("t-1")
        graph.add_task("t-2", depends_on=["t-1"])
        ready = graph.get_ready_tasks()
        assert ready == ["t-1"]
        assert "t-2" in graph.get_blocked_tasks()

    def test_completing_dep_unblocks(self):
        graph = TaskGraph()
        graph.add_task("t-1")
        graph.add_task("t-2", depends_on=["t-1"])
        graph.set_status("t-1", TaskStatus.COMPLETED)
        ready = graph.get_ready_tasks()
        assert "t-2" in ready

    def test_cycle_detection(self):
        graph = TaskGraph()
        graph.add_task("t-1")
        graph.add_task("t-2", depends_on=["t-1"])
        with pytest.raises(CyclicDependencyError):
            graph.add_dependency("t-1", "t-2")

    def test_self_dependency_rejected(self):
        graph = TaskGraph()
        graph.add_task("t-1")
        with pytest.raises(CyclicDependencyError):
            graph.add_dependency("t-1", "t-1")

    def test_topological_order(self):
        graph = TaskGraph()
        graph.add_task("t-1")
        graph.add_task("t-2", depends_on=["t-1"])
        graph.add_task("t-3", depends_on=["t-2"])
        order = graph.topological_order()
        assert order.index("t-1") < order.index("t-2")
        assert order.index("t-2") < order.index("t-3")

    def test_is_complete(self):
        graph = TaskGraph()
        graph.add_task("t-1")
        graph.add_task("t-2")
        assert not graph.is_complete()
        graph.set_status("t-1", TaskStatus.COMPLETED)
        graph.set_status("t-2", TaskStatus.COMPLETED)
        assert graph.is_complete()

    def test_has_failures(self):
        graph = TaskGraph()
        graph.add_task("t-1")
        graph.set_status("t-1", TaskStatus.FAILED)
        assert graph.has_failures()

    def test_remove_task(self):
        graph = TaskGraph()
        graph.add_task("t-1")
        graph.add_task("t-2", depends_on=["t-1"])
        graph.remove_task("t-1")
        assert graph.get_status("t-1") is None
        assert graph.task_count == 1

    def test_summary(self):
        graph = TaskGraph()
        graph.add_task("t-1")
        graph.add_task("t-2", depends_on=["t-1"])
        s = graph.summary()
        assert s["total"] == 2
        assert "pending" in s["by_status"]

    def test_load_from_envelopes(self):
        graph = TaskGraph()
        envelopes = [
            TaskEnvelope(task_id="t-1", status=TaskStatus.COMPLETED),
            TaskEnvelope(task_id="t-2", status=TaskStatus.PENDING, depends_on=["t-1"]),
        ]
        graph.load_from_envelopes(envelopes)
        assert graph.task_count == 2
        assert "t-2" in graph.get_ready_tasks()  # t-1 completed


# ======================================================================
# Context Reducer Tests
# ======================================================================

class TestContextReducer:
    def test_all_fit(self):
        reducer = ContextReducer(default_budget=1000)
        chunks = [
            ContextChunk(label="a", content="Hello world", priority=5.0),
            ContextChunk(label="b", content="Short text", priority=3.0),
        ]
        result = reducer.reduce(chunks)
        assert result.dropped_chunks == 0
        assert len(result.chunks) == 2

    def test_priority_ordering(self):
        reducer = ContextReducer(default_budget=1000)
        chunks = [
            ContextChunk(label="low", content="x" * 100, priority=1.0),
            ContextChunk(label="high", content="y" * 100, priority=10.0),
        ]
        result = reducer.reduce(chunks)
        assert result.chunks[0].label == "high"
        assert result.chunks[1].label == "low"

    def test_budget_drops_low_priority(self):
        reducer = ContextReducer(default_budget=100)
        chunks = [
            ContextChunk(label="important", content="x" * 400, priority=10.0),
            ContextChunk(label="optional", content="y" * 400, priority=1.0),
        ]
        result = reducer.reduce(chunks)
        assert result.dropped_chunks >= 1
        assert "optional" in result.dropped_labels

    def test_truncation(self):
        reducer = ContextReducer(default_budget=50)
        chunks = [
            ContextChunk(label="big", content="a" * 1000, priority=10.0),
        ]
        result = reducer.reduce(chunks)
        assert len(result.chunks) == 1
        assert "[truncated]" in result.chunks[0].content

    def test_estimate_tokens(self):
        reducer = ContextReducer()
        tokens = reducer.estimate_tokens("Hello world! This is a test.")
        assert tokens > 0

    def test_build_agent_context(self):
        reducer = ContextReducer()
        result = reducer.build_agent_context(
            task_slice={"task_id": "t-1", "status": "pending"},
            evidence="Some evidence data",
            token_budget=2000,
        )
        assert result.total_tokens > 0
        assert "task" in result.text


# ======================================================================
# Capability Router Tests
# ======================================================================

class TestCapabilityRouter:
    def _make_router(self) -> CapabilityRouter:
        router = CapabilityRouter(
            models_config_path="nonexistent.json",
            routing_rules_path="nonexistent.json",
        )
        # Register test profiles
        router.register_profile(ModelCapabilityProfile(
            model_id="test-small", tier=ModelTier.SMALL, max_context=4096,
            cost_per_1k_tokens=0.0,
        ))
        router.register_profile(ModelCapabilityProfile(
            model_id="test-mid", tier=ModelTier.MID, max_context=16384,
            reflection_passes=1, combine_steps=True, cost_per_1k_tokens=0.01,
        ))
        router.register_profile(ModelCapabilityProfile(
            model_id="test-high", tier=ModelTier.HIGH, max_context=128000,
            reflection_passes=3, combine_steps=True, cost_per_1k_tokens=0.03,
        ))
        return router

    def test_simple_task_routes_small(self):
        router = self._make_router()
        result = router.route(RoutingRequest(
            task_complexity=TaskComplexity.SIMPLE,
            context_size=1000,
        ))
        assert result.selected_model.tier == ModelTier.SMALL

    def test_moderate_routes_mid(self):
        router = self._make_router()
        result = router.route(RoutingRequest(
            task_complexity=TaskComplexity.MODERATE,
            context_size=1000,
        ))
        assert result.selected_model.tier == ModelTier.MID

    def test_complex_routes_high(self):
        router = self._make_router()
        result = router.route(RoutingRequest(
            task_complexity=TaskComplexity.COMPLEX,
            context_size=1000,
        ))
        assert result.selected_model.tier == ModelTier.HIGH

    def test_context_too_large_escalates(self):
        router = self._make_router()
        result = router.route(RoutingRequest(
            task_complexity=TaskComplexity.SIMPLE,
            context_size=8000,  # Too big for small (4096)
        ))
        # Should escalate beyond small
        assert result.selected_model.max_context >= 8000

    def test_budget_constraint_downgrades(self):
        router = self._make_router()
        result = router.route(RoutingRequest(
            task_complexity=TaskComplexity.COMPLEX,
            context_size=1000,
            budget_threshold=0.005,  # Too cheap for high tier (0.03)
        ))
        # Should fallback to cheaper tier
        assert result.selected_model.cost_per_1k_tokens <= 0.005

    def test_fallback_model_provided(self):
        router = self._make_router()
        result = router.route(RoutingRequest(
            task_complexity=TaskComplexity.COMPLEX,
            context_size=1000,
        ))
        # High tier selected → should have mid or small fallback
        assert result.fallback_model is not None or result.selected_model.tier == ModelTier.SMALL

    def test_no_profiles_raises(self):
        router = CapabilityRouter(
            models_config_path="nonexistent.json",
            routing_rules_path="nonexistent.json",
        )
        with pytest.raises(RuntimeError, match="No model profiles"):
            router.route(RoutingRequest(
                task_complexity=TaskComplexity.SIMPLE,
                context_size=100,
            ))


# ======================================================================
# Snapshot Tests
# ======================================================================

class TestSnapshots:
    def test_create_snapshot(self):
        mgr = SnapshotManager()
        tasks = [
            TaskEnvelope(task_id="t-1", status=TaskStatus.COMPLETED),
            TaskEnvelope(task_id="t-2", status=TaskStatus.PENDING),
        ]
        snap = mgr.create_snapshot("snap-1", tasks)
        assert snap.snapshot_id == "snap-1"
        assert len(snap.tasks) == 2
        assert "Tasks: 2" in snap.summary_text

    def test_get_latest_snapshot(self):
        mgr = SnapshotManager()
        mgr.create_snapshot("snap-1", [])
        mgr.create_snapshot("snap-2", [])
        latest = mgr.get_latest_snapshot()
        assert latest is not None
        assert latest.snapshot_id == "snap-2"

    def test_rehydration_context(self):
        mgr = SnapshotManager()
        tasks = [
            TaskEnvelope(task_id="t-1", status=TaskStatus.COMPLETED, agent_role=AgentRole.CODER),
            TaskEnvelope(task_id="t-2", status=TaskStatus.FAILED, agent_role=AgentRole.CODER),
        ]
        mgr.create_snapshot("snap-1", tasks)
        ctx = mgr.get_rehydration_context("snap-1")
        assert "snap-1" in ctx
        assert "done" in ctx or "error" in ctx

    def test_snapshot_roundtrip(self):
        snap = StateSnapshot(
            snapshot_id="snap-rt",
            timestamp="2026-01-01T00:00:00Z",
            tasks=[{"task_id": "t-1", "status": "completed"}],
        )
        data = snap.to_dict()
        restored = StateSnapshot.from_dict(data)
        assert restored.snapshot_id == snap.snapshot_id
        assert restored.tasks == snap.tasks

    def test_max_snapshots_enforced(self):
        mgr = SnapshotManager(max_snapshots=3)
        for i in range(5):
            mgr.create_snapshot(f"snap-{i}", [])
        assert len(mgr.list_snapshots()) == 3


# ======================================================================
# Agent Tests (prompt building & output parsing)
# ======================================================================

class TestPlannerAgent:
    def test_build_prompt(self):
        agent = PlannerAgent()
        inp = PlannerInput(user_message="Create a REST API")
        system, user = agent.build_prompt(inp)
        assert "planning agent" in system.lower()
        assert "Create a REST API" in user

    def test_parse_valid_output(self):
        agent = PlannerAgent()
        raw = json.dumps({
            "steps": [{"step_id": 1, "description": "Create main.py"}],
            "estimated_complexity": "simple",
            "reasoning": "Single file creation",
        })
        result = agent.parse_output(raw)
        assert len(result.steps) == 1

    def test_parse_with_markdown_fences(self):
        agent = PlannerAgent()
        raw = '```json\n{"steps": [{"step_id": 1, "description": "test"}], "estimated_complexity": "simple"}\n```'
        result = agent.parse_output(raw)
        assert len(result.steps) == 1

    def test_parse_fallback_on_garbage(self):
        agent = PlannerAgent()
        result = agent.parse_output("This is not JSON at all")
        assert len(result.steps) == 1  # Fallback single step
        assert "fallback" in result.reasoning.lower()


class TestCoderAgent:
    def test_build_prompt(self):
        agent = CoderAgent()
        inp = CoderInput(
            plan_step=PlanStep(step_id=1, description="Write hello.py"),
        )
        system, user = agent.build_prompt(inp)
        assert "coding agent" in system.lower()
        assert "Write hello.py" in user

    def test_parse_valid_output(self):
        agent = CoderAgent()
        raw = json.dumps({
            "changes": [{"path": "hello.py", "action": "write", "content": "print('hi')"}],
            "success": True,
            "reasoning": "Created file",
        })
        result = agent.parse_output(raw)
        assert result.success
        assert len(result.changes) == 1

    def test_parse_failure_output(self):
        agent = CoderAgent()
        result = agent.parse_output("not json")
        assert not result.success


class TestReviewerAgent:
    def test_build_prompt(self):
        agent = ReviewerAgent()
        inp = ReviewerInput(
            plan=PlannerOutput(
                steps=[PlanStep(step_id=1, description="test")],
                estimated_complexity=TaskComplexity.SIMPLE,
            ),
            coder_output=CoderOutput(success=True),
            original_request="Create a test",
        )
        system, user = agent.build_prompt(inp)
        assert "review" in system.lower()
        assert "Create a test" in user

    def test_parse_valid_output(self):
        agent = ReviewerAgent()
        raw = json.dumps({
            "approved": True,
            "confidence_score": 0.9,
            "issues": [],
            "reasoning": "Looks good",
        })
        result = agent.parse_output(raw)
        assert result.approved
        assert result.confidence_score == 0.9
