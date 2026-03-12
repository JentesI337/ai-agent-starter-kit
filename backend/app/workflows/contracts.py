"""Workflow node contracts — typed port definitions and compatibility rules.

Each node type declares its input/output ports with data types.
Used by the chain resolver for design-time validation.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class DataType(str, Enum):
    TEXT = "text"
    JSON = "json"
    FILE = "file"
    BOOL = "bool"
    NUMBER = "number"
    LIST = "list"
    ANY = "any"
    VOID = "void"
    PASSTHROUGH = "passthrough"


class EdgeKind(str, Enum):
    DEFAULT = "default"
    TRUE = "true"
    FALSE = "false"
    BRANCH = "branch"
    JOIN = "join"
    LOOP_BACK = "loop_back"
    LOOP_EXIT = "loop_exit"


class PortDef(BaseModel):
    name: str
    data_type: DataType
    required: bool = True
    dynamic: bool = False  # True for fork outputs / join inputs


class NodeContract(BaseModel):
    node_type: str
    inputs: list[PortDef]
    outputs: list[PortDef]
    allow_back_edge: bool = False


def _port(name: str, dt: DataType, *, dynamic: bool = False) -> PortDef:
    return PortDef(name=name, data_type=dt, dynamic=dynamic)


NODE_CONTRACTS: dict[str, NodeContract] = {
    "trigger": NodeContract(
        node_type="trigger",
        inputs=[],
        outputs=[_port("default", DataType.TEXT)],
    ),
    "agent": NodeContract(
        node_type="agent",
        inputs=[_port("default", DataType.ANY)],
        outputs=[_port("default", DataType.TEXT)],
    ),
    "connector": NodeContract(
        node_type="connector",
        inputs=[_port("default", DataType.ANY)],
        outputs=[_port("default", DataType.JSON)],
    ),
    "transform": NodeContract(
        node_type="transform",
        inputs=[_port("default", DataType.ANY)],
        outputs=[_port("default", DataType.ANY)],
    ),
    "condition": NodeContract(
        node_type="condition",
        inputs=[_port("default", DataType.ANY)],
        outputs=[
            _port("on_true", DataType.PASSTHROUGH),
            _port("on_false", DataType.PASSTHROUGH),
        ],
    ),
    "fork": NodeContract(
        node_type="fork",
        inputs=[_port("default", DataType.ANY)],
        outputs=[_port("branch", DataType.PASSTHROUGH, dynamic=True)],
    ),
    "join": NodeContract(
        node_type="join",
        inputs=[_port("branch", DataType.ANY, dynamic=True)],
        outputs=[_port("default", DataType.JSON)],
    ),
    "loop": NodeContract(
        node_type="loop",
        inputs=[_port("default", DataType.ANY)],
        outputs=[
            _port("body", DataType.PASSTHROUGH),
            _port("done", DataType.PASSTHROUGH),
        ],
        allow_back_edge=True,
    ),
    "delay": NodeContract(
        node_type="delay",
        inputs=[_port("default", DataType.ANY)],
        outputs=[_port("default", DataType.PASSTHROUGH)],
    ),
    "end": NodeContract(
        node_type="end",
        inputs=[_port("default", DataType.ANY)],
        outputs=[],
    ),
}


def type_compatible(source: DataType, target: DataType) -> bool:
    """Check if a source data type can connect to a target data type."""
    if source == DataType.ANY or target == DataType.ANY:
        return True
    if source == DataType.PASSTHROUGH or target == DataType.PASSTHROUGH:
        return True
    if source == DataType.VOID:
        return False
    return source == target


def get_contract(node_type: str) -> NodeContract | None:
    """Look up the contract for a node type."""
    return NODE_CONTRACTS.get(node_type)
