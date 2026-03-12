# tools/ — tool catalog, policy, content security, URL validation,
#           telemetry, registry, and execution subsystems.
#
# All imports are lazy to avoid circular-import issues (catalog and
# registry depend on app.config which may transitively re-enter
# the deprecation stubs during init).

__all__ = [
    "AgentToolPolicyEntry",
    "TOOL_NAME_ALIASES",
    "TOOL_NAME_SET",
    "TOOL_NAMES",
    "TOOL_PROFILES",
    "ToolConfigStore",
    "ToolExecutionConfig",
    "ToolExecutionManager",
    "ToolExecutionPolicy",
    "ToolPolicyDict",
    "ToolPolicyPayload",
    "ToolRegistry",
    "ToolRuntimeConfig",
    "ToolSpec",
    "ToolSpan",
    "ToolTelemetry",
    "UrlValidationError",
    "apply_dns_pin",
    "enforce_safe_url",
    "resolve_tool_profile",
    "tool_policy_to_dict",
    "validate_llm_base_url",
    "wrap_external_content",
]

_CATALOG_NAMES = {"TOOL_NAME_ALIASES", "TOOL_NAME_SET", "TOOL_NAMES"}
_POLICY_NAMES = {
    "AgentToolPolicyEntry", "TOOL_PROFILES", "ToolPolicyDict",
    "ToolPolicyPayload", "resolve_tool_profile", "tool_policy_to_dict",
}
_URL_VALIDATOR_NAMES = {
    "UrlValidationError", "apply_dns_pin", "enforce_safe_url", "validate_llm_base_url",
}
_REGISTRY_NAMES = {
    "ToolConfigStore", "ToolExecutionPolicy", "ToolRegistry",
    "ToolRuntimeConfig", "ToolSpec",
}
_TELEMETRY_NAMES = {"ToolSpan", "ToolTelemetry"}
_EXECUTION_LAZY = {"ToolExecutionManager", "ToolExecutionConfig", "STEER_INTERRUPTED_MARKER"}
_DISCOVERY_NAMES = {
    "CAPABILITY_PATTERNS", "CAPABILITY_TOOLS", "ConversionEdge", "DiscoveryResult",
    "EcoTool", "ToolCapabilityRouter", "ToolDiscoveryEngine", "ToolEcosystemMap",
    "ToolKnowledge", "ToolKnowledgeBase", "detect_linter", "detect_package_manager",
    "detect_test_runner",
}
_PROVISIONING_NAMES = {
    "AuditEntry", "BUILTIN_COMMAND_SAFETY_PATTERNS", "BudgetConfig",
    "PackageCandidate", "PackageManagerAdapter", "PRESET_TOOL_POLICIES",
    "ProvisionResult", "TOOL_POLICY_BY_MODEL", "TOOL_POLICY_BY_PROVIDER",
    "TOOL_POLICY_RESOLUTION_ORDER", "ToolBudgetManager", "ToolProvisioner",
    "add_pattern", "find_command_safety_violation",
    "find_semantic_command_safety_violation", "get_all_patterns",
    "get_extended_patterns", "get_platform_adapters", "merge_tool_policy",
    "normalize_policy_values", "policy_payload", "resolve_tool_policy",
    "resolve_tool_policy_with_preset",
}


def __getattr__(name: str):
    if name in _CATALOG_NAMES:
        from app.tools import catalog as _m
        return getattr(_m, name)
    if name in _POLICY_NAMES:
        from app.tools import policy as _m
        return getattr(_m, name)
    if name == "wrap_external_content":
        from app.tools.content_security import wrap_external_content
        return wrap_external_content
    if name in _URL_VALIDATOR_NAMES:
        from app.tools import url_validator as _m
        return getattr(_m, name)
    if name in _REGISTRY_NAMES:
        from app.tools import registry as _m
        return getattr(_m, name)
    if name in _TELEMETRY_NAMES:
        from app.tools import telemetry as _m
        return getattr(_m, name)
    if name in _EXECUTION_LAZY:
        from app.tools.execution import manager as _m
        return getattr(_m, name)
    if name in _DISCOVERY_NAMES:
        from app.tools import discovery as _m
        return getattr(_m, name)
    if name in _PROVISIONING_NAMES:
        from app.tools import provisioning as _m
        return getattr(_m, name)
    # Backward compat: app.tooling (formerly app.tools module)
    if name in ("AgentTooling", "find_command_safety_violation",
                "find_semantic_command_safety_violation", "COMMAND_SAFETY_PATTERNS"):
        import app.tooling as _m
        return getattr(_m, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
