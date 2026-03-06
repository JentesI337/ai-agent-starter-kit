"""Tests for the multi-agency subsystem.

Covers: Blackboard, AgentMessageBus, Supervisor, ConfidenceRouter,
ParallelFanOutExecutor, ConsensusEngine, CoordinationBridge, AgentIdentity.

Uses asyncio.run() pattern consistent with the rest of the test suite.
"""
from __future__ import annotations

import asyncio

from app.multi_agency.agent_identity import (
    DEFAULT_AGENT_IDENTITIES,
    AgentCapabilityProfile,
    AgentIdentityCard,
    AgentRegistry,
    AgentRole,
    ReasoningStrategy,
)
from app.multi_agency.agent_message_bus import (
    AgentMessage,
    AgentMessageBus,
    MessagePriority,
    MessageType,
)
from app.multi_agency.blackboard import Blackboard
from app.multi_agency.confidence_router import ConfidenceRouter
from app.multi_agency.consensus import (
    ConsensusEngine,
    VotingStrategy,
)
from app.multi_agency.coordination_bridge import CoordinationBridge
from app.multi_agency.parallel_executor import (
    DAGStep,
    FanOutMode,
    ParallelFanOutExecutor,
)
from app.multi_agency.supervisor import (
    SupervisorCoordinator,
)

# ─── helpers ───────────────────────────────────────────────

def _run(coro):
    """Run an async coroutine synchronously (project convention)."""
    return asyncio.run(coro)


def _make_board() -> Blackboard:
    return Blackboard(session_id="test-session")


async def _make_bus() -> AgentMessageBus:
    b = AgentMessageBus(session_id="test-session")
    await b.register_agent("agent-a")
    await b.register_agent("agent-b")
    await b.register_agent("agent-c")
    return b


async def _make_supervisor() -> SupervisorCoordinator:
    registry = AgentRegistry()
    bus = AgentMessageBus(session_id="test")
    board = Blackboard(session_id="test")
    for identity in registry.list_all():
        await bus.register_agent(identity.agent_id)
    await bus.register_agent("supervisor")

    s = SupervisorCoordinator(
        agent_registry=registry,
        message_bus=bus,
        blackboard=board,
    )
    await s.create_session("test-session")
    return s


# ─── Blackboard ────────────────────────────────────────────

class TestBlackboard:
    def test_write_and_read(self):
        async def _scenario():
            board = _make_board()
            entry = await board.write(
                section="analysis",
                key="security",
                value="No vulnerabilities found",
                author_agent_id="review-agent",
                confidence=0.9,
            )
            assert entry.section == "analysis"
            assert entry.key == "security"
            assert entry.value == "No vulnerabilities found"
            assert entry.author_agent_id == "review-agent"
            assert entry.confidence == 0.9
            assert entry.version == 1

            read_back = await board.read(section="analysis", key="security")
            assert read_back is not None
            assert read_back.entry_id == entry.entry_id
        _run(_scenario())

    def test_version_incrementing(self):
        async def _scenario():
            board = _make_board()
            e1 = await board.write(
                section="plan", key="step1", value="v1",
                author_agent_id="head-agent",
            )
            assert e1.version == 1

            e2 = await board.write(
                section="plan", key="step1", value="v2",
                author_agent_id="head-agent",
            )
            assert e2.version == 2
            assert e2.supersedes == e1.entry_id
        _run(_scenario())

    def test_read_section(self):
        async def _scenario():
            board = _make_board()
            await board.write(section="results", key="a", value=1, author_agent_id="agent-a")
            await board.write(section="results", key="b", value=2, author_agent_id="agent-b")
            section = await board.read_section("results")
            assert len(section) == 2
            assert "a" in section
            assert "b" in section
        _run(_scenario())

    def test_read_by_agent(self):
        async def _scenario():
            board = _make_board()
            await board.write(section="s1", key="k1", value="x", author_agent_id="agent-a")
            await board.write(section="s2", key="k2", value="y", author_agent_id="agent-b")
            entries = await board.read_by_agent("agent-a")
            assert len(entries) == 1
            assert entries[0].value == "x"
        _run(_scenario())

    def test_history(self):
        async def _scenario():
            board = _make_board()
            await board.write(section="s", key="k", value="v1", author_agent_id="a")
            await board.write(section="s", key="k", value="v2", author_agent_id="a")
            await board.write(section="s", key="k", value="v3", author_agent_id="a")
            history = await board.read_history(section="s", key="k")
            assert len(history) == 3
            assert history[0].value == "v1"
            assert history[2].value == "v3"
        _run(_scenario())

    def test_conflict_detection(self):
        async def _scenario():
            board = _make_board()
            board._conflict_window_seconds = 10.0  # wide window for test
            await board.write(section="s", key="k", value="v1", author_agent_id="agent-a")
            await board.write(section="s", key="k", value="v2", author_agent_id="agent-b")
            conflicts = await board.get_conflicts()
            assert len(conflicts) == 1
            assert conflicts[0].agent_a == "agent-a"
            assert conflicts[0].agent_b == "agent-b"
        _run(_scenario())

    def test_no_conflict_same_agent(self):
        async def _scenario():
            board = _make_board()
            board._conflict_window_seconds = 10.0
            await board.write(section="s", key="k", value="v1", author_agent_id="agent-a")
            await board.write(section="s", key="k", value="v2", author_agent_id="agent-a")
            conflicts = await board.get_conflicts()
            assert len(conflicts) == 0
        _run(_scenario())

    def test_watcher(self):
        async def _scenario():
            board = _make_board()
            received = []

            async def on_change(entry):
                received.append(entry)

            board.watch(section="s", key="k", callback=on_change)
            await board.write(section="s", key="k", value="v1", author_agent_id="a")
            assert len(received) == 1
            assert received[0].value == "v1"
        _run(_scenario())

    def test_snapshot(self):
        async def _scenario():
            board = _make_board()
            await board.write(section="s", key="k", value="v", author_agent_id="a", confidence=0.8)
            snapshot = await board.snapshot()
            assert snapshot["session_id"] == "test-session"
            assert "s" in snapshot["sections"]
            assert snapshot["sections"]["s"]["k"]["confidence"] == 0.8
        _run(_scenario())


# ─── Agent Message Bus ────────────────────────────────────

class TestAgentMessageBus:
    def test_direct_message(self):
        async def _scenario():
            bus = await _make_bus()
            await bus.send(
                sender="agent-a",
                recipient="agent-b",
                payload={"task": "review code"},
            )
            msg = await bus.receive("agent-b")
            assert msg is not None
            assert msg.sender_agent_id == "agent-a"
            assert msg.payload["task"] == "review code"
        _run(_scenario())

    def test_broadcast(self):
        async def _scenario():
            bus = await _make_bus()
            await bus.send(
                sender="agent-a",
                recipient="*",
                payload={"announcement": "task complete"},
                message_type=MessageType.BROADCAST,
            )
            msg_b = await bus.receive("agent-b")
            msg_c = await bus.receive("agent-c")
            assert msg_b is not None
            assert msg_c is not None
            assert msg_b.payload["announcement"] == "task complete"

            # Sender should not receive own broadcast
            msg_a = await bus.receive("agent-a")
            assert msg_a is None
        _run(_scenario())

    def test_topic_pubsub(self):
        async def _scenario():
            bus = await _make_bus()
            await bus.subscribe("agent-b", "code_review")
            await bus.subscribe("agent-c", "code_review")

            await bus.publish(
                sender="agent-a",
                topic="code_review",
                payload={"file": "main.py"},
            )

            msg_b = await bus.receive("agent-b")
            msg_c = await bus.receive("agent-c")
            assert msg_b is not None
            assert msg_b.topic == "code_review"
            assert msg_c is not None
        _run(_scenario())

    def test_priority_ordering(self):
        async def _scenario():
            bus = await _make_bus()
            await bus.send(
                sender="agent-a", recipient="agent-b",
                payload={"priority": "low"}, priority=MessagePriority.LOW,
            )
            await bus.send(
                sender="agent-a", recipient="agent-b",
                payload={"priority": "urgent"}, priority=MessagePriority.URGENT,
            )
            msg1 = await bus.receive("agent-b")
            assert msg1 is not None
            assert msg1.payload["priority"] == "urgent"
        _run(_scenario())

    def test_dead_letter_for_unknown_recipient(self):
        async def _scenario():
            bus = await _make_bus()
            await bus.send(
                sender="agent-a",
                recipient="nonexistent-agent",
                payload={"data": "test"},
            )
            stats = await bus.stats()
            assert stats["dead_letters"] == 1
        _run(_scenario())

    def test_request_reply(self):
        async def _scenario():
            bus = await _make_bus()

            async def handler(message):
                return AgentMessage(
                    message_id="reply-1",
                    sender_agent_id="agent-b",
                    recipient_agent_id="agent-a",
                    message_type=MessageType.REPLY,
                    payload={"answer": 42},
                    timestamp="",
                    correlation_id=message.correlation_id,
                )

            bus.set_handler("agent-b", handler)

            reply = await bus.request(
                sender="agent-a",
                recipient="agent-b",
                payload={"question": "what is the answer?"},
                timeout=5.0,
            )
            assert reply is not None
            assert reply.payload["answer"] == 42
        _run(_scenario())

    def test_stats(self):
        async def _scenario():
            bus = await _make_bus()
            await bus.send(sender="agent-a", recipient="agent-b", payload={})
            stats = await bus.stats()
            assert stats["total_sent"] >= 1
            assert "agent-a" in stats["registered_agents"]
        _run(_scenario())


# ─── Agent Identity & Registry ────────────────────────────

class TestAgentIdentity:
    def test_default_identities_exist(self):
        assert "head-agent" in DEFAULT_AGENT_IDENTITIES
        assert "coder-agent" in DEFAULT_AGENT_IDENTITIES
        assert "review-agent" in DEFAULT_AGENT_IDENTITIES

    def test_head_agent_is_coordinator(self):
        head = DEFAULT_AGENT_IDENTITIES["head-agent"]
        assert head.role == AgentRole.COORDINATOR
        assert head.can_delegate
        assert head.reasoning_strategy == ReasoningStrategy.PLAN_EXECUTE

    def test_coder_agent_is_specialist(self):
        coder = DEFAULT_AGENT_IDENTITIES["coder-agent"]
        assert coder.role == AgentRole.SPECIALIST
        assert not coder.can_delegate
        assert "code_reasoning" in coder.capability_profile.capabilities

    def test_review_agent_has_forbidden_tools(self):
        review = DEFAULT_AGENT_IDENTITIES["review-agent"]
        assert "write_file" in review.capability_profile.forbidden_tools
        assert "run_command" in review.capability_profile.forbidden_tools

    def test_capability_score(self):
        coder = DEFAULT_AGENT_IDENTITIES["coder-agent"]
        score = coder.capability_score({"code_reasoning", "debugging", "testing"})
        assert score > 0.5

        score_low = coder.capability_score({"web_retrieval", "research"})
        assert score_low == 0.0

    def test_registry_find_by_capability(self):
        registry = AgentRegistry()
        found = registry.find_by_capability("code_reasoning")
        agent_ids = [c.agent_id for c in found]
        assert "coder-agent" in agent_ids

    def test_registry_find_best_match(self):
        registry = AgentRegistry()
        best = registry.find_best_match({"code_reasoning", "code_modification"})
        assert best is not None
        assert best.agent_id == "coder-agent"

    def test_registry_find_delegatable(self):
        registry = AgentRegistry()
        delegatable = registry.find_delegatable()
        assert len(delegatable) >= 3  # head, coder, review, researcher

    def test_registry_custom_agent(self):
        registry = AgentRegistry()
        custom = AgentIdentityCard(
            agent_id="security-agent",
            display_name="Security Agent",
            role=AgentRole.SPECIALIST,
            reasoning_strategy=ReasoningStrategy.VERIFY_FIRST,
            capability_profile=AgentCapabilityProfile(
                capabilities=("security_analysis", "vulnerability_detection"),
                preferred_tools=("grep_search", "read_file"),
                forbidden_tools=("write_file",),
                preferred_models=("gpt-4o",),
            ),
            system_prompt_key="security_agent_prompt",
        )
        registry.register(custom)
        assert registry.get("security-agent") is not None
        found = registry.find_by_capability("security_analysis")
        assert any(c.agent_id == "security-agent" for c in found)


# ─── Confidence Router ────────────────────────────────────

class TestConfidenceRouter:
    def _make_router(self) -> ConfidenceRouter:
        return ConfidenceRouter(
            agent_registry=AgentRegistry(),
            accept_threshold=0.7,
            review_threshold=0.5,
            reject_threshold=0.3,
        )

    def test_high_confidence_accepted(self):
        router = self._make_router()
        decision = router.evaluate_handover(
            handover_contract={
                "terminal_reason": "subrun-complete",
                "confidence": 0.9,
                "result": "Task completed successfully",
            },
            source_agent_id="coder-agent",
        )
        assert decision.action == "accept"
        assert decision.confidence >= 0.7

    def test_medium_confidence_review(self):
        router = self._make_router()
        decision = router.evaluate_handover(
            handover_contract={
                "terminal_reason": "subrun-complete",
                "confidence": 0.55,
                "result": "Partial result",
            },
            source_agent_id="coder-agent",
        )
        assert decision.action == "review"

    def test_low_confidence_redelegate(self):
        router = self._make_router()
        decision = router.evaluate_handover(
            handover_contract={
                "terminal_reason": "subrun-complete",
                "confidence": 0.35,
                "result": "Weak result",
            },
            source_agent_id="coder-agent",
        )
        assert decision.action == "redelegate"

    def test_very_low_confidence_reject(self):
        router = self._make_router()
        decision = router.evaluate_handover(
            handover_contract={
                "terminal_reason": "subrun-error",
                "confidence": 0.1,
                "result": None,
            },
            source_agent_id="coder-agent",
        )
        assert decision.action == "reject"

    def test_error_terminal_reason_penalized(self):
        router = self._make_router()
        decision = router.evaluate_handover(
            handover_contract={
                "terminal_reason": "subrun-error",
                "confidence": 0.8,
                "result": "Something happened",
            },
            source_agent_id="coder-agent",
        )
        # 0.8 * 0.3 = 0.24, should be below reject threshold of 0.3
        assert decision.confidence < 0.3

    def test_learning_from_outcomes(self):
        router = self._make_router()
        for _ in range(5):
            router.record_outcome(
                agent_id="coder-agent",
                task_description="implement feature",
                confidence=0.9,
                outcome="success",
            )
        for _ in range(5):
            router.record_outcome(
                agent_id="review-agent",
                task_description="review code",
                confidence=0.5,
                outcome="failure",
            )

        report = router.get_confidence_report()
        assert report["coder-agent"]["avg_confidence"] == 0.9
        assert report["review-agent"]["avg_confidence"] == 0.5

    def test_route_by_confidence(self):
        router = self._make_router()
        for _ in range(3):
            router.record_outcome(
                agent_id="coder-agent",
                task_description="code",
                confidence=0.95,
                outcome="success",
            )

        decision = router.route_by_confidence(
            required_capabilities={"code_reasoning", "code_modification"},
        )
        assert decision.action == "accept"
        assert decision.selected_agent_id == "coder-agent"

    def test_confidence_extraction_edge_cases(self):
        assert ConfidenceRouter._extract_confidence({}) == 0.0
        assert ConfidenceRouter._extract_confidence({"confidence": "high"}) == 0.9
        assert ConfidenceRouter._extract_confidence({"confidence": "medium"}) == 0.6
        assert ConfidenceRouter._extract_confidence({"confidence": "low"}) == 0.3
        assert ConfidenceRouter._extract_confidence({"confidence": 1.5}) == 1.0
        assert ConfidenceRouter._extract_confidence({"confidence": -0.5}) == 0.0


# ─── Supervisor ────────────────────────────────────────────

class TestSupervisor:
    def test_assign_coding_task(self):
        async def _scenario():
            supervisor = await _make_supervisor()
            decisions = await supervisor.decompose_and_assign(
                session_id="test-session",
                task_descriptions=[{
                    "description": "Implement a REST endpoint",
                    "required_capabilities": ["code_reasoning", "code_modification"],
                }],
            )
            assert len(decisions) == 1
            assert decisions[0].decision_type == "assign"
            assert decisions[0].agent_id == "coder-agent"
        _run(_scenario())

    def test_assign_review_task(self):
        async def _scenario():
            supervisor = await _make_supervisor()
            decisions = await supervisor.decompose_and_assign(
                session_id="test-session",
                task_descriptions=[{
                    "description": "Review code for security issues",
                    "required_capabilities": ["review_analysis", "security_review"],
                }],
            )
            assert len(decisions) == 1
            assert decisions[0].agent_id == "review-agent"
        _run(_scenario())

    def test_report_result_accepted(self):
        async def _scenario():
            supervisor = await _make_supervisor()
            decisions = await supervisor.decompose_and_assign(
                session_id="test-session",
                task_descriptions=[{
                    "description": "Write code",
                    "required_capabilities": ["code_reasoning"],
                }],
            )
            task_id = decisions[0].task_id

            result_decision = await supervisor.report_result(
                session_id="test-session",
                task_id=task_id,
                result="Code written successfully",
                confidence=0.9,
                agent_id="coder-agent",
            )
            assert result_decision.decision_type == "complete"
        _run(_scenario())

    def test_report_result_low_confidence_redelegates(self):
        async def _scenario():
            supervisor = await _make_supervisor()
            decisions = await supervisor.decompose_and_assign(
                session_id="test-session",
                task_descriptions=[{
                    "description": "General task",
                    "required_capabilities": ["general_reasoning", "coordination"],
                }],
            )
            task_id = decisions[0].task_id

            result_decision = await supervisor.report_result(
                session_id="test-session",
                task_id=task_id,
                result="Weak result",
                confidence=0.2,
                agent_id=decisions[0].agent_id,
            )
            assert result_decision.decision_type in ("redelegate", "reject")
        _run(_scenario())

    def test_session_status(self):
        async def _scenario():
            supervisor = await _make_supervisor()
            await supervisor.decompose_and_assign(
                session_id="test-session",
                task_descriptions=[{
                    "description": "Task 1",
                    "required_capabilities": ["code_reasoning"],
                }],
            )
            status = await supervisor.get_session_status("test-session")
            assert status["status"] == "active"
            assert len(status["tasks"]) == 1
        _run(_scenario())

    def test_no_matching_agent_rejected(self):
        async def _scenario():
            supervisor = await _make_supervisor()
            decisions = await supervisor.decompose_and_assign(
                session_id="test-session",
                task_descriptions=[{
                    "description": "Impossible task",
                    "required_capabilities": ["quantum_computing", "time_travel"],
                }],
            )
            assert decisions[0].decision_type == "reject"
        _run(_scenario())


# ─── Parallel Fan-Out Executor ─────────────────────────────

class TestParallelFanOutExecutor:
    @staticmethod
    async def mock_executor(agent_id: str, description: str, context: dict) -> dict:
        await asyncio.sleep(0.01)
        return {"result": f"{agent_id}: done", "confidence": 0.8}

    def test_fan_out_all(self):
        async def _scenario():
            executor = ParallelFanOutExecutor(executor=self.mock_executor, max_concurrent=5)
            result = await executor.fan_out(
                tasks=[
                    {"agent_id": "agent-a", "description": "task 1"},
                    {"agent_id": "agent-b", "description": "task 2"},
                    {"agent_id": "agent-c", "description": "task 3"},
                ],
                mode=FanOutMode.ALL,
            )
            assert result.total_tasks == 3
            assert result.completed_tasks == 3
            assert result.failed_tasks == 0
            assert result.best_result is not None
        _run(_scenario())

    def test_fan_out_race(self):
        async def _scenario():
            async def fast_or_slow(agent_id, desc, ctx):
                delay = 0.01 if agent_id == "fast" else 5.0
                await asyncio.sleep(delay)
                return {"result": f"{agent_id} finished", "confidence": 0.9}

            executor = ParallelFanOutExecutor(executor=fast_or_slow, max_concurrent=5)
            result = await executor.fan_out(
                tasks=[
                    {"agent_id": "fast", "description": "fast task"},
                    {"agent_id": "slow", "description": "slow task"},
                ],
                mode=FanOutMode.RACE,
                timeout=3.0,
            )
            assert result.best_result is not None
            assert result.best_result["agent_id"] == "fast"
        _run(_scenario())

    def test_dag_execution(self):
        async def _scenario():
            executor = ParallelFanOutExecutor(executor=self.mock_executor, max_concurrent=5)
            steps = [
                DAGStep(step_id="s1", agent_id="agent-a", description="First step", depends_on=[]),
                DAGStep(step_id="s2", agent_id="agent-b", description="Depends on s1", depends_on=["s1"]),
                DAGStep(step_id="s3", agent_id="agent-c", description="Depends on s1", depends_on=["s1"]),
                DAGStep(step_id="s4", agent_id="agent-a", description="Depends on s2,s3", depends_on=["s2", "s3"]),
            ]
            results = await executor.execute_dag(steps=steps, timeout=10.0)
            assert len(results) == 4
            assert all(r["status"] == "completed" for r in results)
        _run(_scenario())

    def test_dag_parallel_independent_steps(self):
        """Steps s1 and s2 have no dependencies and should run in parallel."""
        async def _scenario():
            executor = ParallelFanOutExecutor(executor=self.mock_executor, max_concurrent=5)
            steps = [
                DAGStep(step_id="s1", agent_id="a", description="Independent 1", depends_on=[]),
                DAGStep(step_id="s2", agent_id="b", description="Independent 2", depends_on=[]),
                DAGStep(step_id="s3", agent_id="c", description="Final", depends_on=["s1", "s2"]),
            ]
            results = await executor.execute_dag(steps=steps, timeout=10.0)
            completed = [r for r in results if r["status"] == "completed"]
            assert len(completed) == 3
        _run(_scenario())


# ─── Consensus Engine ──────────────────────────────────────

class TestConsensusEngine:
    def _make_engine(self) -> ConsensusEngine:
        return ConsensusEngine(agent_registry=AgentRegistry())

    def test_majority_vote_agreement(self):
        engine = self._make_engine()
        result = engine.vote(
            votes=[
                {"agent_id": "a", "result": "yes", "confidence": 0.8},
                {"agent_id": "b", "result": "yes", "confidence": 0.7},
                {"agent_id": "c", "result": "no", "confidence": 0.6},
            ],
            strategy=VotingStrategy.MAJORITY,
        )
        assert result.consensus_reached
        assert result.winning_result == "yes"
        assert result.agreement_ratio > 0.5

    def test_majority_vote_no_consensus(self):
        engine = self._make_engine()
        result = engine.vote(
            votes=[
                {"agent_id": "a", "result": "yes", "confidence": 0.8},
                {"agent_id": "b", "result": "no", "confidence": 0.7},
                {"agent_id": "c", "result": "maybe", "confidence": 0.6},
            ],
            strategy=VotingStrategy.MAJORITY,
        )
        assert not result.consensus_reached

    def test_weighted_confidence_vote(self):
        engine = self._make_engine()
        result = engine.vote(
            votes=[
                {"agent_id": "a", "result": "option-A", "confidence": 0.95},
                {"agent_id": "b", "result": "option-B", "confidence": 0.3},
                {"agent_id": "c", "result": "option-B", "confidence": 0.2},
            ],
            strategy=VotingStrategy.WEIGHTED_CONFIDENCE,
        )
        # Agent A has highest weight, so option-A should win
        assert result.winning_result == "option-A"

    def test_best_of_n(self):
        engine = self._make_engine()
        result = engine.vote(
            votes=[
                {"agent_id": "a", "result": "weak", "confidence": 0.3},
                {"agent_id": "b", "result": "strong", "confidence": 0.95},
                {"agent_id": "c", "result": "medium", "confidence": 0.6},
            ],
            strategy=VotingStrategy.BEST_OF_N,
        )
        assert result.winning_result == "strong"
        assert result.winning_agent_id == "b"

    def test_unanimous_all_agree(self):
        engine = self._make_engine()
        result = engine.vote(
            votes=[
                {"agent_id": "a", "result": "same", "confidence": 0.8},
                {"agent_id": "b", "result": "same", "confidence": 0.7},
            ],
            strategy=VotingStrategy.UNANIMOUS,
        )
        assert result.consensus_reached
        assert result.agreement_ratio == 1.0

    def test_unanimous_disagreement(self):
        engine = self._make_engine()
        result = engine.vote(
            votes=[
                {"agent_id": "a", "result": "yes", "confidence": 0.9},
                {"agent_id": "b", "result": "no", "confidence": 0.8},
            ],
            strategy=VotingStrategy.UNANIMOUS,
        )
        assert not result.consensus_reached

    def test_conflict_detection(self):
        engine = self._make_engine()
        result = engine.vote(
            votes=[
                {"agent_id": "a", "result": "completely different answer A", "confidence": 0.8},
                {"agent_id": "b", "result": "totally unrelated response B", "confidence": 0.7},
            ],
            strategy=VotingStrategy.BEST_OF_N,
        )
        assert len(result.conflicts) > 0

    def test_merge_concatenate(self):
        engine = self._make_engine()
        merged = engine.merge_results(
            results=[
                {"agent_id": "a", "result": "Part 1"},
                {"agent_id": "b", "result": "Part 2"},
            ],
            merge_strategy="concatenate",
        )
        assert "Part 1" in merged["merged"]
        assert "Part 2" in merged["merged"]

    def test_merge_deduplicate(self):
        engine = self._make_engine()
        merged = engine.merge_results(
            results=[
                {"agent_id": "a", "result": "Same content here"},
                {"agent_id": "b", "result": "Same content here"},
                {"agent_id": "c", "result": "Different content"},
            ],
            merge_strategy="deduplicate",
        )
        assert merged["unique_count"] == 2

    def test_empty_votes(self):
        engine = self._make_engine()
        result = engine.vote(votes=[], strategy=VotingStrategy.MAJORITY)
        assert not result.consensus_reached
        assert result.vote_count == 0


# ─── Coordination Bridge ──────────────────────────────────

class TestCoordinationBridge:
    def test_initialize(self):
        async def _scenario():
            bridge = CoordinationBridge(session_id="test")
            await bridge.initialize()
            status = await bridge.get_status()
            assert status["initialized"]
            assert status["session_id"] == "test"
        _run(_scenario())

    def test_subrun_completed_high_confidence(self):
        async def _scenario():
            bridge = CoordinationBridge(session_id="test")
            await bridge.initialize()

            decision = await bridge.on_subrun_completed(
                parent_session_id="parent",
                run_id="run-1",
                child_agent_id="coder-agent",
                terminal_reason="subrun-complete",
                child_output="Task completed successfully",
                handover_contract={
                    "terminal_reason": "subrun-complete",
                    "confidence": 0.9,
                    "result": "Task completed successfully",
                },
            )
            assert decision.action == "accept"
        _run(_scenario())

    def test_subrun_completed_low_confidence_redelegates(self):
        async def _scenario():
            bridge = CoordinationBridge(session_id="test")
            await bridge.initialize()

            decision = await bridge.on_subrun_completed(
                parent_session_id="parent",
                run_id="run-2",
                child_agent_id="coder-agent",
                terminal_reason="subrun-complete",
                child_output="Weak result",
                handover_contract={
                    "terminal_reason": "subrun-complete",
                    "confidence": 0.35,
                    "result": "Weak result",
                },
            )
            assert decision.action == "redelegate"
        _run(_scenario())

    def test_route_agent_with_confidence(self):
        async def _scenario():
            bridge = CoordinationBridge(session_id="test")
            await bridge.initialize()

            decision = bridge.route_agent(
                required_capabilities={"code_reasoning", "code_modification"},
            )
            assert decision.selected_agent_id == "coder-agent"
        _run(_scenario())

    def test_assign_tasks_via_supervisor(self):
        async def _scenario():
            bridge = CoordinationBridge(session_id="test")
            await bridge.initialize()

            decisions = await bridge.assign_tasks([
                {
                    "description": "Write unit tests",
                    "required_capabilities": ["code_reasoning", "testing"],
                },
                {
                    "description": "Review security",
                    "required_capabilities": ["security_review", "review_analysis"],
                },
            ])
            assert len(decisions) == 2
            agent_ids = {d.agent_id for d in decisions}
            assert "coder-agent" in agent_ids
            assert "review-agent" in agent_ids
        _run(_scenario())

    def test_agent_communication(self):
        async def _scenario():
            bridge = CoordinationBridge(session_id="test")
            await bridge.initialize()

            await bridge.send_agent_message(
                sender="head-agent",
                recipient="coder-agent",
                payload={"instruction": "implement feature X"},
            )

            msg = await bridge.message_bus.receive("coder-agent")
            assert msg is not None
            assert msg.payload["instruction"] == "implement feature X"
        _run(_scenario())

    def test_blackboard_after_subrun(self):
        async def _scenario():
            bridge = CoordinationBridge(session_id="test")
            await bridge.initialize()

            await bridge.on_subrun_completed(
                parent_session_id="parent",
                run_id="run-x",
                child_agent_id="review-agent",
                terminal_reason="subrun-complete",
                child_output="No issues found",
                handover_contract={
                    "terminal_reason": "subrun-complete",
                    "confidence": 0.85,
                    "result": "No issues found",
                },
            )

            entry = await bridge.blackboard.read(section="subrun_results", key="run-x")
            assert entry is not None
            assert entry.author_agent_id == "review-agent"
            assert entry.confidence == 0.85
        _run(_scenario())
