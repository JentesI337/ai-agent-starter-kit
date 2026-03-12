"""Quality domain — verification, contracts, pattern detection, and degradation."""

from app.quality.execution_contract import (
    ContractResult,
    ContractViolation,
    ExecutionContract,
    get_contract,
    register_contract,
)
from app.quality.execution_pattern_detector import ExecutionPatternDetector, PatternAlert
from app.quality.graceful_degradation import (
    DegradationResponse,
    FailedAttempt,
    GracefulDegradation,
)
from app.quality.verification_service import VerificationResult, VerificationService


# Lazy imports for modules with heavy dependency chains.
def __getattr__(name: str):  # noqa: N807
    if name in ("ReflectionService", "ReflectionVerdict"):
        from app.quality import reflection_service as _rs

        return getattr(_rs, name)

    if name in ("SelfHealingLoop", "HealingResult", "RecoveryPlan"):
        from app.quality import self_healing_loop as _shl

        return getattr(_shl, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ContractResult",
    "ContractViolation",
    "DegradationResponse",
    "ExecutionContract",
    "ExecutionPatternDetector",
    "FailedAttempt",
    "GracefulDegradation",
    "HealingResult",
    "PatternAlert",
    "RecoveryPlan",
    "ReflectionService",
    "ReflectionVerdict",
    "SelfHealingLoop",
    "VerificationResult",
    "VerificationService",
    "get_contract",
    "register_contract",
]
