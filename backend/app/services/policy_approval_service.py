from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import uuid

from app.config import settings


APPROVAL_DECISIONS = {"allow_once", "allow_always", "deny"}
ALLOW_ALWAYS_SCOPES = {
    "tool_resource",
    "tool",
    "session_tool_resource",
    "session_tool",
}


@dataclass
class ApprovalDecision:
    allowed: bool | None = None
    decided_at: str | None = None


class PolicyApprovalService:
    def __init__(self, allow_always_store_file: str | None = None):
        self._lock = asyncio.Lock()
        self._records: dict[str, dict] = {}
        self._events: dict[str, asyncio.Event] = {}
        default_file = Path(settings.orchestrator_state_dir) / "policy_allow_always_rules.json"
        self._allow_always_store_file = Path(allow_always_store_file).resolve() if allow_always_store_file else default_file
        self._allow_always_rules: list[dict[str, str]] = []
        self._restore_allow_always_rules()

    async def create(
        self,
        *,
        run_id: str,
        session_id: str,
        agent_name: str,
        tool: str,
        resource: str,
        display_text: str,
    ) -> dict:
        approval_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        record = {
            "approval_id": approval_id,
            "run_id": run_id,
            "session_id": session_id,
            "agent_name": agent_name,
            "tool": tool,
            "resource": resource,
            "display_text": display_text,
            "status": "pending",
            "decision": None,
            "options": ["allow_once", "allow_always", "deny"],
            "created_at": created_at,
            "updated_at": created_at,
        }
        async with self._lock:
            self._records[approval_id] = record
            self._events[approval_id] = asyncio.Event()
        return dict(record)

    def _normalize_scope(self, scope: str | None) -> str:
        candidate = (scope or "tool_resource").strip().lower()
        if candidate not in ALLOW_ALWAYS_SCOPES:
            return "tool_resource"
        return candidate

    def _normalize_rule(
        self,
        *,
        scope: str,
        tool: str,
        resource: str,
        session_id: str | None,
    ) -> dict[str, str] | None:
        normalized_scope = self._normalize_scope(scope)
        normalized_tool = (tool or "").strip().lower()
        normalized_resource = (resource or "").strip()
        normalized_session = (session_id or "").strip()
        if not normalized_tool:
            return None

        rule: dict[str, str] = {
            "scope": normalized_scope,
            "tool": normalized_tool,
        }
        if normalized_scope in {"tool_resource", "session_tool_resource"} and normalized_resource:
            rule["resource"] = normalized_resource
        if normalized_scope in {"session_tool", "session_tool_resource"} and normalized_session:
            rule["session_id"] = normalized_session

        if normalized_scope in {"tool_resource", "session_tool_resource"} and "resource" not in rule:
            return None
        if normalized_scope in {"session_tool", "session_tool_resource"} and "session_id" not in rule:
            return None
        return rule

    def _rule_matches(self, *, rule: dict[str, str], tool: str, resource: str, session_id: str | None) -> bool:
        rule_scope = self._normalize_scope(rule.get("scope"))
        normalized_tool = (tool or "").strip().lower()
        normalized_resource = (resource or "").strip()
        normalized_session = (session_id or "").strip()

        if rule.get("tool") != normalized_tool:
            return False
        if rule_scope in {"tool_resource", "session_tool_resource"} and rule.get("resource") != normalized_resource:
            return False
        if rule_scope in {"session_tool", "session_tool_resource"} and rule.get("session_id") != normalized_session:
            return False
        return True

    def _persist_allow_always_rules(self) -> None:
        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "rules": self._allow_always_rules,
        }
        try:
            self._allow_always_store_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._allow_always_store_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._allow_always_store_file)
        except Exception:
            return

    def _restore_allow_always_rules(self) -> None:
        try:
            if not self._allow_always_store_file.exists():
                return
            payload = json.loads(self._allow_always_store_file.read_text(encoding="utf-8"))
            items = payload.get("rules") if isinstance(payload, dict) else None
            if not isinstance(items, list):
                return
            rules: list[dict[str, str]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                normalized = self._normalize_rule(
                    scope=str(item.get("scope") or "tool_resource"),
                    tool=str(item.get("tool") or ""),
                    resource=str(item.get("resource") or ""),
                    session_id=str(item.get("session_id") or "") or None,
                )
                if normalized is not None and normalized not in rules:
                    rules.append(normalized)
            self._allow_always_rules = rules
        except Exception:
            return

    async def is_preapproved(self, *, tool: str, resource: str, session_id: str | None = None) -> bool:
        async with self._lock:
            return any(
                self._rule_matches(
                    rule=rule,
                    tool=tool,
                    resource=resource,
                    session_id=session_id,
                )
                for rule in self._allow_always_rules
            )

    async def decide(self, approval_id: str, decision: str, scope: str | None = None) -> dict | None:
        normalized_decision = (decision or "").strip().lower()
        if normalized_decision not in APPROVAL_DECISIONS:
            raise ValueError(f"Unsupported approval decision: {decision}")
        normalized_scope = self._normalize_scope(scope)

        async with self._lock:
            record = self._records.get(approval_id)
            if record is None:
                return None
            now = datetime.now(timezone.utc).isoformat()

            if normalized_decision in {"allow_once", "allow_always"}:
                record["status"] = "approved"
            else:
                record["status"] = "denied"

            record["decision"] = normalized_decision
            record["updated_at"] = now
            record["scope"] = normalized_scope

            if normalized_decision == "allow_always":
                normalized_rule = self._normalize_rule(
                    scope=normalized_scope,
                    tool=str(record.get("tool") or ""),
                    resource=str(record.get("resource") or ""),
                    session_id=str(record.get("session_id") or "") or None,
                )
                if normalized_rule is not None and normalized_rule not in self._allow_always_rules:
                    self._allow_always_rules.append(normalized_rule)
                    self._persist_allow_always_rules()

            event = self._events.get(approval_id)
            if event is not None:
                event.set()
            return dict(record)

    async def allow(self, approval_id: str) -> dict | None:
        return await self.decide(approval_id, "allow_once")

    async def deny(self, approval_id: str) -> dict | None:
        return await self.decide(approval_id, "deny")

    async def allow_always(self, approval_id: str, scope: str | None = None) -> dict | None:
        return await self.decide(approval_id, "allow_always", scope=scope)

    async def wait_for_decision(self, approval_id: str, timeout_seconds: float) -> str | None:
        async with self._lock:
            record = self._records.get(approval_id)
            event = self._events.get(approval_id)
            if record is None or event is None:
                return None
            if record.get("status") in {"approved", "denied"}:
                decision = str(record.get("decision") or "").strip().lower()
                return decision or None

        try:
            await asyncio.wait_for(event.wait(), timeout=max(0.1, float(timeout_seconds)))
        except asyncio.TimeoutError:
            async with self._lock:
                record = self._records.get(approval_id)
                if record is not None and record.get("status") == "pending":
                    record["status"] = "expired"
                    record["decision"] = "timeout"
                    record["updated_at"] = datetime.now(timezone.utc).isoformat()
            return "timeout"

        async with self._lock:
            record = self._records.get(approval_id)
            if not record:
                return None
            decision = str(record.get("decision") or "").strip().lower()
            return decision or None

    async def wait_for_allow(self, approval_id: str, timeout_seconds: float) -> bool:
        decision = await self.wait_for_decision(approval_id, timeout_seconds)
        return decision in {"allow_once", "allow_always"}

    async def list_pending(self, *, run_id: str | None = None, session_id: str | None = None, limit: int = 100) -> list[dict]:
        normalized_run_id = (run_id or "").strip() or None
        normalized_session_id = (session_id or "").strip() or None
        effective_limit = max(1, min(500, int(limit)))
        async with self._lock:
            items = []
            for record in self._records.values():
                if record.get("status") != "pending":
                    continue
                if normalized_run_id and record.get("run_id") != normalized_run_id:
                    continue
                if normalized_session_id and record.get("session_id") != normalized_session_id:
                    continue
                items.append(dict(record))
            items.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
            return items[:effective_limit]
