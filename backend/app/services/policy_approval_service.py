from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import uuid


@dataclass
class ApprovalDecision:
    allowed: bool | None = None
    decided_at: str | None = None


class PolicyApprovalService:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._records: dict[str, dict] = {}
        self._events: dict[str, asyncio.Event] = {}

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
            "created_at": created_at,
            "updated_at": created_at,
        }
        async with self._lock:
            self._records[approval_id] = record
            self._events[approval_id] = asyncio.Event()
        return dict(record)

    async def allow(self, approval_id: str) -> dict | None:
        async with self._lock:
            record = self._records.get(approval_id)
            if record is None:
                return None
            now = datetime.now(timezone.utc).isoformat()
            record["status"] = "approved"
            record["decision"] = "allow"
            record["updated_at"] = now
            event = self._events.get(approval_id)
            if event is not None:
                event.set()
            return dict(record)

    async def wait_for_allow(self, approval_id: str, timeout_seconds: float) -> bool:
        async with self._lock:
            record = self._records.get(approval_id)
            event = self._events.get(approval_id)
            if record is None or event is None:
                return False
            if record.get("status") == "approved":
                return True

        try:
            await asyncio.wait_for(event.wait(), timeout=max(0.1, float(timeout_seconds)))
        except asyncio.TimeoutError:
            async with self._lock:
                record = self._records.get(approval_id)
                if record is not None and record.get("status") == "pending":
                    record["status"] = "expired"
                    record["decision"] = "timeout"
                    record["updated_at"] = datetime.now(timezone.utc).isoformat()
            return False

        async with self._lock:
            record = self._records.get(approval_id)
            return bool(record and record.get("status") == "approved")

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
