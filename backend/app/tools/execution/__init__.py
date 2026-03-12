# tools/execution — tool call execution, gating, retry, validation
from app.tools.execution.arg_validator import ToolArgValidator
from app.tools.execution.gatekeeper import (
    ActionPreparationResult,
    PolicyOverrideCandidate,
    ToolCallGatekeeper,
    ToolLoopDecision,
    collect_policy_override_candidates,
    prepare_action_for_execution,
)
from app.tools.execution.loop_detector import (
    LoopDetectionConfig,
    LoopDetectionState,
    ToolLoopDetector,
)
from app.tools.execution.outcome_verifier import OutcomeVerdict, ToolOutcomeVerifier
from app.tools.execution.parallel_executor import ToolParallelExecutor
from app.tools.execution.result_context_guard import (
    ToolResultContextGuardResult,
    enforce_tool_result_context_budget,
    neutralize_prompt_injections,
    redact_pii,
)
from app.tools.execution.result_processor import (
    ResultProcessingConfig,
    ToolResultProcessor,
)
from app.tools.execution.retry_strategy import (
    RetryDecision,
    RetryStrategy,
    ToolRetryStrategy,
)

__all__ = [
    "ActionPreparationResult",
    "LoopDetectionConfig",
    "LoopDetectionState",
    "OutcomeVerdict",
    "PolicyOverrideCandidate",
    "ResultProcessingConfig",
    "RetryDecision",
    "RetryStrategy",
    "ToolArgValidator",
    "ToolCallGatekeeper",
    "ToolLoopDecision",
    "ToolLoopDetector",
    "ToolOutcomeVerifier",
    "ToolParallelExecutor",
    "ToolResultContextGuardResult",
    "ToolResultProcessor",
    "ToolRetryStrategy",
    "collect_policy_override_candidates",
    "enforce_tool_result_context_budget",
    "neutralize_prompt_injections",
    "prepare_action_for_execution",
    "redact_pii",
]


def __getattr__(name: str):
    if name == "ToolExecutionManager":
        from app.tools.execution.manager import ToolExecutionManager
        return ToolExecutionManager
    if name == "ToolExecutionConfig":
        from app.tools.execution.manager import ToolExecutionConfig
        return ToolExecutionConfig
    if name == "STEER_INTERRUPTED_MARKER":
        from app.tools.execution.manager import STEER_INTERRUPTED_MARKER
        return STEER_INTERRUPTED_MARKER
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
