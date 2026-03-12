from app.services.control_fingerprints import (
    build_run_start_fingerprint,
    build_session_patch_fingerprint,
    build_session_reset_fingerprint,
    build_workflow_create_fingerprint,
    build_workflow_delete_fingerprint,
    build_workflow_execute_fingerprint,
)
from app.services.idempotency_service import (
    idempotency_lookup_or_raise,
    idempotency_register,
    prune_idempotency_registry,
)
from app.services.prompt_kernel_builder import PromptKernel, PromptKernelBuilder
from app.services.request_normalization import normalize_prompt_mode, normalize_queue_mode
from app.services.session_inbox_service import InboxMessage, SessionInboxService
from app.services.session_query_service import SessionQueryService

# tool_policy_service exports are lazy-loaded via __getattr__ below
# to avoid circular import: policy_service → app.config → app.services.__init__

__all__ = [
    "PRESET_TOOL_POLICIES",
    "TOOL_POLICY_BY_MODEL",
    "TOOL_POLICY_BY_PROVIDER",
    "TOOL_POLICY_RESOLUTION_ORDER",
    "TOOL_PROFILES",
    "InboxMessage",
    "PolicyApprovalService",
    "PromptKernel",
    "PromptKernelBuilder",
    "SessionInboxService",
    "SessionQueryService",
    "build_run_start_fingerprint",
    "build_session_patch_fingerprint",
    "build_session_reset_fingerprint",
    "build_workflow_create_fingerprint",
    "build_workflow_delete_fingerprint",
    "build_workflow_execute_fingerprint",
    "idempotency_lookup_or_raise",
    "idempotency_register",
    "merge_tool_policy",
    "normalize_policy_values",
    "normalize_prompt_mode",
    "normalize_queue_mode",
    "policy_payload",
    "prune_idempotency_registry",
    "resolve_tool_policy",
    "resolve_tool_policy_with_preset",
]


_TOOL_POLICY_SERVICE_NAMES = {
    "PRESET_TOOL_POLICIES",
    "TOOL_POLICY_BY_MODEL",
    "TOOL_POLICY_BY_PROVIDER",
    "TOOL_POLICY_RESOLUTION_ORDER",
    "TOOL_PROFILES",
    "merge_tool_policy",
    "normalize_policy_values",
    "policy_payload",
    "resolve_tool_policy",
    "resolve_tool_policy_with_preset",
}


def __getattr__(name: str):  # noqa: N807
    if name == "PolicyApprovalService":
        from app.policy.approval_service import PolicyApprovalService
        return PolicyApprovalService
    if name in _TOOL_POLICY_SERVICE_NAMES:
        from app.tools.provisioning import policy_service as _m
        return getattr(_m, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
