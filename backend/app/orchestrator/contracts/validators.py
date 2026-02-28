"""
Input / output validation layer per agent.

Every agent call goes through validate_input → agent → validate_output.
All validation errors are structured — no silent failures.
"""
from __future__ import annotations

import logging
from typing import Any, Type

from pydantic import BaseModel, ValidationError

from app.orchestrator.contracts.schemas import (
    AgentContract,
    AgentRole,
    CoderInput,
    CoderOutput,
    PlannerInput,
    PlannerOutput,
    ReviewerInput,
    ReviewerOutput,
)

logger = logging.getLogger(__name__)


class ContractValidationError(Exception):
    """Raised when agent input or output fails schema validation."""

    def __init__(self, agent_role: AgentRole, direction: str, details: str):
        self.agent_role = agent_role
        self.direction = direction  # "input" | "output"
        self.details = details
        super().__init__(f"Contract violation ({direction}) for {agent_role.value}: {details}")


# ---------------------------------------------------------------------------
# Schema registry — maps agent role → (InputModel, OutputModel)
# ---------------------------------------------------------------------------

_SCHEMA_REGISTRY: dict[AgentRole, tuple[Type[BaseModel], Type[BaseModel]]] = {
    AgentRole.PLANNER: (PlannerInput, PlannerOutput),
    AgentRole.CODER: (CoderInput, CoderOutput),
    AgentRole.REVIEWER: (ReviewerInput, ReviewerOutput),
}


def get_input_model(role: AgentRole) -> Type[BaseModel]:
    return _SCHEMA_REGISTRY[role][0]


def get_output_model(role: AgentRole) -> Type[BaseModel]:
    return _SCHEMA_REGISTRY[role][1]


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_input(role: AgentRole, data: dict[str, Any]) -> BaseModel:
    """
    Validate raw dict against the registered input schema for *role*.
    Returns the validated Pydantic model instance on success.
    Raises ContractValidationError on failure.
    """
    model_cls = get_input_model(role)
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        logger.warning("input_validation_failed role=%s errors=%s", role.value, exc.error_count())
        raise ContractValidationError(
            agent_role=role,
            direction="input",
            details=str(exc),
        ) from exc


def validate_output(role: AgentRole, data: dict[str, Any]) -> BaseModel:
    """
    Validate raw dict against the registered output schema for *role*.
    Returns the validated Pydantic model instance on success.
    Raises ContractValidationError on failure.
    """
    model_cls = get_output_model(role)
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        logger.warning("output_validation_failed role=%s errors=%s", role.value, exc.error_count())
        raise ContractValidationError(
            agent_role=role,
            direction="output",
            details=str(exc),
        ) from exc


def validate_contract(contract: AgentContract) -> list[str]:
    """
    Static check: verify that a contract definition itself is well-formed.
    Returns a list of warning / error strings (empty = valid).
    """
    issues: list[str] = []

    if contract.role not in _SCHEMA_REGISTRY:
        issues.append(f"Unknown agent role: {contract.role}")

    c = contract.constraints
    if c.max_context_tokens < 512:
        issues.append(f"max_context_tokens={c.max_context_tokens} is unusually low")

    if c.max_reflection_passes > 0 and c.temperature > 1.0:
        issues.append("High temperature with reflection passes may produce unstable outputs")

    return issues
