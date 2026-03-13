"""Tool provisioning and lifecycle management."""
from app.tools.provisioning.budget_manager import BudgetConfig, ToolBudgetManager
from app.tools.provisioning.command_security import (
    BUILTIN_COMMAND_SAFETY_PATTERNS,
    add_pattern,
    find_command_safety_violation,
    find_semantic_command_safety_violation,
    get_all_patterns,
    get_extended_patterns,
)
from app.tools.provisioning.package_manager_adapter import (
    PackageCandidate,
    PackageManagerAdapter,
    get_platform_adapters,
)
from app.tools.provisioning.provisioner import AuditEntry, ProvisionResult, ToolProvisioner

__all__ = [
    "BUILTIN_COMMAND_SAFETY_PATTERNS",
    "AuditEntry",
    "BudgetConfig",
    "PackageCandidate",
    "PackageManagerAdapter",
    "ProvisionResult",
    "ToolBudgetManager",
    "ToolProvisioner",
    "add_pattern",
    "find_command_safety_violation",
    "find_semantic_command_safety_violation",
    "get_all_patterns",
    "get_extended_patterns",
    "get_platform_adapters",
]

# --- Lazy imports for policy_service (has app.config dep → circular risk) ---

_POLICY_SERVICE_NAMES = {
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

__all__ += sorted(_POLICY_SERVICE_NAMES)  # noqa: PLE0605


def __getattr__(name: str):
    if name in _POLICY_SERVICE_NAMES:
        import importlib

        _mod = importlib.import_module("app.tools.provisioning.policy_service")
        return getattr(_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
