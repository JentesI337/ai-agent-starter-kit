"""Tests for the workflow contracts registry and type compatibility."""
from __future__ import annotations

from app.workflows.contracts import (
    NODE_CONTRACTS,
    DataType,
    get_contract,
    type_compatible,
)
from app.workflows.models import WorkflowStepDef


class TestNodeContracts:
    def test_all_node_types_have_contracts(self):
        """Every type literal in WorkflowStepDef should have a matching contract."""
        expected_types = {
            "agent", "connector", "transform", "condition", "delay",
            "fork", "join", "loop", "trigger", "end",
        }
        assert set(NODE_CONTRACTS.keys()) == expected_types

    def test_get_contract_found(self):
        c = get_contract("agent")
        assert c is not None
        assert c.node_type == "agent"

    def test_get_contract_missing(self):
        assert get_contract("nonexistent") is None

    def test_trigger_has_no_inputs(self):
        c = NODE_CONTRACTS["trigger"]
        assert len(c.inputs) == 0
        assert len(c.outputs) == 1

    def test_end_has_no_outputs(self):
        c = NODE_CONTRACTS["end"]
        assert len(c.inputs) == 1
        assert len(c.outputs) == 0

    def test_condition_has_two_outputs(self):
        c = NODE_CONTRACTS["condition"]
        names = {p.name for p in c.outputs}
        assert names == {"on_true", "on_false"}

    def test_fork_output_is_dynamic(self):
        c = NODE_CONTRACTS["fork"]
        assert c.outputs[0].dynamic is True

    def test_join_input_is_dynamic(self):
        c = NODE_CONTRACTS["join"]
        assert c.inputs[0].dynamic is True

    def test_loop_allows_back_edge(self):
        c = NODE_CONTRACTS["loop"]
        assert c.allow_back_edge is True

    def test_non_loop_disallows_back_edge(self):
        for name, c in NODE_CONTRACTS.items():
            if name != "loop":
                assert c.allow_back_edge is False, f"{name} should not allow back edges"


class TestTypeCompatibility:
    def test_any_accepts_anything(self):
        for dt in DataType:
            assert type_compatible(dt, DataType.ANY) is True
            assert type_compatible(DataType.ANY, dt) is True

    def test_passthrough_accepts_anything(self):
        for dt in DataType:
            assert type_compatible(dt, DataType.PASSTHROUGH) is True
            assert type_compatible(DataType.PASSTHROUGH, dt) is True

    def test_void_rejects_all(self):
        for dt in DataType:
            if dt not in (DataType.ANY, DataType.PASSTHROUGH):
                assert type_compatible(DataType.VOID, dt) is False

    def test_same_type_compatible(self):
        assert type_compatible(DataType.TEXT, DataType.TEXT) is True
        assert type_compatible(DataType.JSON, DataType.JSON) is True

    def test_different_concrete_types_incompatible(self):
        assert type_compatible(DataType.TEXT, DataType.JSON) is False
        assert type_compatible(DataType.NUMBER, DataType.BOOL) is False


class TestExistingStepDeserializes:
    def test_old_step_json_without_new_fields(self):
        """Old step JSON without fork/join/loop fields still parses."""
        old_json = {
            "id": "step-1",
            "type": "agent",
            "label": "Test Step",
            "instruction": "Do something",
            "next_step": "step-2",
        }
        step = WorkflowStepDef.model_validate(old_json)
        assert step.id == "step-1"
        assert step.type == "agent"
        assert step.next_steps is None
        assert step.wait_for is None
        assert step.join_from is None
        assert step.loop_condition is None
        assert step.loop_body_entry is None
        assert step.loop_max_iterations == 100

    def test_new_step_with_fork_fields(self):
        step = WorkflowStepDef(
            id="fork-1", type="fork",
            next_steps=["branch-a", "branch-b"],
        )
        assert step.next_steps == ["branch-a", "branch-b"]
        assert step.next_step is None

    def test_new_step_with_loop_fields(self):
        step = WorkflowStepDef(
            id="loop-1", type="loop",
            loop_condition="counter < 5",
            loop_body_entry="body-step",
            loop_max_iterations=50,
        )
        assert step.loop_condition == "counter < 5"
        assert step.loop_body_entry == "body-step"
        assert step.loop_max_iterations == 50
