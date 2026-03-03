from __future__ import annotations

from typing import TypeAlias

from pydantic import BaseModel

ToolPolicyDict: TypeAlias = dict[str, list[str]]


class ToolPolicyPayload(BaseModel):
    allow: list[str] | None = None
    deny: list[str] | None = None
    also_allow: list[str] | None = None

    def to_policy_dict(self, *, include_also_allow: bool = True) -> ToolPolicyDict | None:
        payload: ToolPolicyDict = {}
        if self.allow:
            payload["allow"] = [item for item in self.allow if isinstance(item, str) and item.strip()]
        if self.deny:
            payload["deny"] = [item for item in self.deny if isinstance(item, str) and item.strip()]
        if include_also_allow and self.also_allow:
            payload["also_allow"] = [item for item in self.also_allow if isinstance(item, str) and item.strip()]
        return payload or None


def tool_policy_to_dict(
    value: ToolPolicyPayload | ToolPolicyDict | None,
    *,
    include_also_allow: bool = True,
) -> ToolPolicyDict | None:
    if value is None:
        return None
    if isinstance(value, ToolPolicyPayload):
        return value.to_policy_dict(include_also_allow=include_also_allow)

    payload: ToolPolicyDict = {}
    for key in ("allow", "deny", "also_allow"):
        if key == "also_allow" and not include_also_allow:
            continue
        values = value.get(key)
        if not isinstance(values, list):
            continue
        normalized = [item for item in values if isinstance(item, str) and item.strip()]
        if normalized:
            payload[key] = normalized
    return payload or None
