from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from app.services.state_encryption import sign_policy_file, verify_policy_file

APPROVAL_DECISIONS = {"allow_once", "allow_always", "allow_session", "deny", "cancel"}
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
    _RECORD_TTL_SECONDS = 3600

    def __init__(self, allow_always_store_file: str | None = None):
        self._lock = asyncio.Lock()
        self._records: dict[str, dict] = {}
        self._events: dict[str, asyncio.Event] = {}
        default_file = Path(settings.orchestrator_state_dir) / "policy_allow_always_rules.json"
        self._allow_always_store_file = Path(allow_always_store_file).resolve() if allow_always_store_file else default_file
        self._allow_always_rules: list[dict[str, str]] = []
        self._session_allow_all: set[str] = set()
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
        normalized_run_id = (run_id or "").strip()
        normalized_session_id = (session_id or "").strip()
        normalized_tool = (tool or "").strip().lower()
        normalized_resource = (resource or "").strip()

        async with self._lock:
            for existing in self._records.values():
                if (
                    str(existing.get("run_id") or "").strip() == normalized_run_id
                    and str(existing.get("session_id") or "").strip() == normalized_session_id
                    and str(existing.get("tool") or "").strip().lower() == normalized_tool
                    and str(existing.get("resource") or "").strip() == normalized_resource
                ):
                    reused = dict(existing)
                    reused["idempotent_reuse"] = True
                    return reused

            approval_id = str(uuid.uuid4())
            created_at = datetime.now(UTC).isoformat()
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
                "options": ["allow_once", "allow_session", "cancel"],
                "created_at": created_at,
                "updated_at": created_at,
            }
            self._records[approval_id] = record
            self._events[approval_id] = asyncio.Event()
            self._evict_stale_records_locked()
            created = dict(record)
            created["idempotent_reuse"] = False
            return created

    def _evict_stale_records_locked(self) -> None:
        now = datetime.now(UTC)
        stale_ids: list[str] = []
        for aid, rec in self._records.items():
            created_str = rec.get("created_at") or ""
            try:
                created_dt = datetime.fromisoformat(created_str)
            except (ValueError, TypeError):
                stale_ids.append(aid)
                continue
            age_seconds = (now - created_dt).total_seconds()
            if rec.get("status") == "pending":
                # Evict stale pending records after 2x TTL
                if age_seconds > self._RECORD_TTL_SECONDS * 2:
                    stale_ids.append(aid)
                continue
            if age_seconds > self._RECORD_TTL_SECONDS:
                stale_ids.append(aid)
        for aid in stale_ids:
            self._records.pop(aid, None)
            self._events.pop(aid, None)

    def _normalize_scope(self, scope: str | None) -> str:
        candidate = (scope or "tool_resource").strip().lower()
        if candidate not in ALLOW_ALWAYS_SCOPES:
            return "tool_resource"
        return candidate

    def _validate_scope(self, scope: str | None) -> str:
        """Like _normalize_scope but raises ValueError for non-empty unknown scopes.

        Bug 14: prevents a misspelled or attacker-controlled scope string from
        silently escalating to a global 'tool_resource' rule when the caller
        explicitly provided a scope value.
        """
        if scope is None or scope.strip() == "":
            return "tool_resource"
        candidate = scope.strip().lower()
        if candidate not in ALLOW_ALWAYS_SCOPES:
            raise ValueError(
                f"Invalid approval scope '{scope}'. "
                f"Allowed values: {sorted(ALLOW_ALWAYS_SCOPES)}"
            )
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
        return not (rule_scope in {"session_tool", "session_tool_resource"} and rule.get("session_id") != normalized_session)

    def _persist_allow_always_rules(self) -> None:
        payload = {
            "version": 1,
            "updated_at": datetime.now(UTC).isoformat(),
            "rules": self._allow_always_rules,
        }
        try:
            self._allow_always_store_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._allow_always_store_file.with_suffix(".tmp")
            raw_content = json.dumps(payload, ensure_ascii=False, indent=2)
            # SEC (POL-01): Sign policy file with HMAC for integrity verification
            signed_content = sign_policy_file(raw_content)
            tmp.write_text(signed_content, encoding="utf-8")
            tmp.replace(self._allow_always_store_file)
        except Exception:
            return

    def _restore_allow_always_rules(self) -> None:
        try:
            if not self._allow_always_store_file.exists():
                return
            raw = self._allow_always_store_file.read_text(encoding="utf-8")
            # SEC (POL-01): Verify HMAC integrity of policy file
            content, sig_valid = verify_policy_file(raw)
            if not sig_valid:
                if settings.policy_require_signature:
                    logging.getLogger(__name__).error(
                        "SEC: Policy file signature invalid or missing — refusing to load: %s",
                        self._allow_always_store_file,
                    )
                    return
                logging.getLogger(__name__).warning(
                    "SEC: Policy file loaded without valid HMAC signature: %s",
                    self._allow_always_store_file,
                )
                content = raw  # Use raw content if no signature present
            payload = json.loads(content)
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
        normalized_session_id = (session_id or "").strip()
        normalized_tool = (tool or "").strip().lower()
        async with self._lock:
            if normalized_session_id and normalized_tool:
                session_tool_key = f"{normalized_session_id}::{normalized_tool}"
                if session_tool_key in self._session_allow_all:
                    return True
            return any(
                self._rule_matches(
                    rule=rule,
                    tool=tool,
                    resource=resource,
                    session_id=session_id,
                )
                for rule in self._allow_always_rules
            )

    async def clear_session_overrides(self, session_id: str | None) -> None:
        normalized_session_id = (session_id or "").strip()
        if not normalized_session_id:
            return
        prefix = f"{normalized_session_id}::"
        async with self._lock:
            # In-memory session-tool keys entfernen
            keys_to_remove = {key for key in self._session_allow_all if key.startswith(prefix)}
            self._session_allow_all -= keys_to_remove
            # Bug 3: Disk-backed session-scoped allow_always rules ebenfalls entfernen.
            # Ohne diesen Schritt überleben session_tool / session_tool_resource Regeln
            # Server-Restarts und bleiben aktiv, obwohl die Session längst beendet ist.
            before = len(self._allow_always_rules)
            self._allow_always_rules = [
                rule for rule in self._allow_always_rules
                if not (
                    rule.get("scope") in {"session_tool", "session_tool_resource"}
                    and rule.get("session_id") == normalized_session_id
                )
            ]
            if len(self._allow_always_rules) != before:
                self._persist_allow_always_rules()

    async def decide(self, approval_id: str, decision: str, scope: str | None = None) -> dict | None:
        normalized_decision = (decision or "").strip().lower()
        if normalized_decision not in APPROVAL_DECISIONS:
            raise ValueError(f"Unsupported approval decision: {decision}")
        # Bug 14: reject invalid scope strings instead of silently promoting to global
        normalized_scope = self._validate_scope(scope)

        async with self._lock:
            record = self._records.get(approval_id)
            if record is None:
                return None

            if record.get("status") != "pending":
                existing_decision = str(record.get("decision") or "").strip().lower()
                record["duplicate_decision"] = True
                record["duplicate_matches_existing"] = existing_decision == normalized_decision
                record["updated_at"] = datetime.now(UTC).isoformat()
                return dict(record)

            now = datetime.now(UTC).isoformat()

            if normalized_decision in {"allow_once", "allow_always", "allow_session"}:
                record["status"] = "approved"
            elif normalized_decision == "cancel":
                record["status"] = "cancelled"
            else:
                record["status"] = "denied"

            record["decision"] = normalized_decision
            record["updated_at"] = now
            record["scope"] = normalized_scope

            if normalized_decision == "allow_session":
                normalized_session_id = str(record.get("session_id") or "").strip()
                normalized_tool = str(record.get("tool") or "").strip().lower()
                if normalized_session_id and normalized_tool:
                    session_tool_key = f"{normalized_session_id}::{normalized_tool}"
                    self._session_allow_all.add(session_tool_key)

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
            if record.get("status") in {"approved", "denied", "cancelled"}:
                decision = str(record.get("decision") or "").strip().lower()
                return decision or None

        try:
            await asyncio.wait_for(event.wait(), timeout=max(0.1, float(timeout_seconds)))
        except TimeoutError:
            async with self._lock:
                record = self._records.get(approval_id)
                if record is not None and record.get("status") == "pending":
                    record["status"] = "expired"
                    record["decision"] = "timeout"
                    record["updated_at"] = datetime.now(UTC).isoformat()
            return "timeout"

        async with self._lock:
            record = self._records.get(approval_id)
            if not record:
                return None
            decision = str(record.get("decision") or "").strip().lower()
            return decision or None

    async def wait_for_allow(self, approval_id: str, timeout_seconds: float) -> bool:
        decision = await self.wait_for_decision(approval_id, timeout_seconds)
        return decision in {"allow_once", "allow_always", "allow_session"}

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
