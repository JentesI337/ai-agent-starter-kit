from __future__ import annotations

from dataclasses import dataclass
from typing import Any

VALID_FAILURE_POLICIES = {"soft_fail", "hard_fail", "skip"}


@dataclass(frozen=True)
class HookExecutionContract:
    hook_name: str
    hook_contract_version: str
    timeout_ms: int
    failure_policy: str

    def as_event_details(self) -> dict[str, Any]:
        return {
            "hook_name": self.hook_name,
            "hook_contract_version": self.hook_contract_version,
            "timeout_ms": self.timeout_ms,
            "failure_policy": self.failure_policy,
        }


def resolve_hook_execution_contract(*, settings: Any, hook_name: str) -> HookExecutionContract:
    normalized_hook_name = str(hook_name or "").strip()

    version = str(getattr(settings, "hook_contract_version", "hook-contract.v2") or "hook-contract.v2").strip()
    if not version:
        version = "hook-contract.v2"

    default_timeout = int(getattr(settings, "hook_timeout_ms_default", 1500) or 1500)
    timeout_overrides = getattr(settings, "hook_timeout_ms_overrides", {}) or {}
    override_timeout = timeout_overrides.get(normalized_hook_name, default_timeout)
    timeout_ms = max(1, int(override_timeout))

    default_policy = str(getattr(settings, "hook_failure_policy_default", "soft_fail") or "soft_fail").strip().lower()
    if default_policy not in VALID_FAILURE_POLICIES:
        default_policy = "soft_fail"

    policy_overrides = getattr(settings, "hook_failure_policy_overrides", {}) or {}
    resolved_policy = str(policy_overrides.get(normalized_hook_name, default_policy) or default_policy).strip().lower()
    if resolved_policy not in VALID_FAILURE_POLICIES:
        resolved_policy = "soft_fail"

    return HookExecutionContract(
        hook_name=normalized_hook_name,
        hook_contract_version=version,
        timeout_ms=timeout_ms,
        failure_policy=resolved_policy,
    )
