from __future__ import annotations

import asyncio
import contextlib
import json
import random
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from app.contracts.agent_contract import SendEvent
from app.errors import GuardrailViolation
from app.interfaces.orchestrator_api import OrchestratorApi
from app.interfaces.request_context import RequestContext
from app.state import StateStore
from app.tool_policy import ToolPolicyDict

# Multi-agency integration (lazy import to avoid circular)
_coordination_bridge_type = None
def _get_bridge_type():
    global _coordination_bridge_type
    if _coordination_bridge_type is None:
        from app.multi_agency.coordination_bridge import CoordinationBridge
        _coordination_bridge_type = CoordinationBridge
    return _coordination_bridge_type


TERMINAL_STATUSES = {"completed", "failed", "timed_out", "cancelled"}
SubrunCompletionCallback = Callable[..., Awaitable[None]]


@dataclass(frozen=True)
class SubrunSpec:
    run_id: str
    parent_request_id: str
    parent_session_id: str
    child_session_id: str
    user_message: str
    runtime: str
    model: str
    tool_policy: ToolPolicyDict | None
    preset: str | None
    timeout_seconds: int
    depth: int
    parent_run_id: str | None
    root_run_id: str
    agent_id: str
    mode: str
    orchestrator_agent_ids: list[str] | None
    orchestrator_api: OrchestratorApi


class SubrunLane:
    def __init__(
        self,
        *,
        orchestrator_api: OrchestratorApi,
        state_store: StateStore,
        max_concurrent: int,
        max_spawn_depth: int,
        max_children_per_parent: int,
        announce_retry_max_attempts: int,
        announce_retry_base_delay_ms: int,
        announce_retry_max_delay_ms: int,
        announce_retry_jitter: bool,
        leaf_spawn_depth_guard_enabled: bool = False,
        orchestrator_agent_ids: list[str] | None = None,
        restore_orphan_reconcile_enabled: bool = True,
        restore_orphan_grace_seconds: int = 0,
        lifecycle_delivery_error_grace_enabled: bool = True,
        max_retained_terminal_runs: int = 2000,
        max_retained_run_entries: int = 4000,
    ):
        self._orchestrator_api = orchestrator_api
        self._state_store = state_store
        self._semaphore = asyncio.Semaphore(max(1, max_concurrent))
        self._max_spawn_depth = max(1, int(max_spawn_depth))
        self._max_children_per_parent = max(1, int(max_children_per_parent))
        self._announce_retry_max_attempts = max(1, int(announce_retry_max_attempts))
        self._announce_retry_base_delay_ms = max(10, int(announce_retry_base_delay_ms))
        self._announce_retry_max_delay_ms = max(self._announce_retry_base_delay_ms, int(announce_retry_max_delay_ms))
        self._announce_retry_jitter = bool(announce_retry_jitter)
        self._restore_orphan_reconcile_enabled = bool(restore_orphan_reconcile_enabled)
        self._restore_orphan_grace_seconds = max(0, int(restore_orphan_grace_seconds))
        self._lifecycle_delivery_error_grace_enabled = bool(lifecycle_delivery_error_grace_enabled)
        self._max_retained_terminal_runs = max(1, int(max_retained_terminal_runs))
        self._max_retained_run_entries = max(self._max_retained_terminal_runs, int(max_retained_run_entries))
        self._leaf_spawn_depth_guard_enabled = bool(leaf_spawn_depth_guard_enabled)
        self._orchestrator_agent_ids = {
            str(item).strip().lower()
            for item in (orchestrator_agent_ids or ["head-agent"])
            if isinstance(item, str) and str(item).strip()
        }
        self._run_tasks: dict[str, asyncio.Task] = {}
        self._run_status: dict[str, dict] = {}
        self._announce_status: dict[str, dict] = {}
        self._run_specs: dict[str, SubrunSpec] = {}
        self._children_by_parent: dict[str, set[str]] = defaultdict(set)
        self._parent_by_child: dict[str, str] = {}
        self._children_by_session: dict[str, set[str]] = defaultdict(set)
        self._completion_callback: SubrunCompletionCallback | None = None
        self._coordination_bridge: object | None = None  # CoordinationBridge instance
        self._lock = asyncio.Lock()
        self._registry_file = Path(self._state_store.persist_dir) / "subrun_registry.json"
        self._restore_registry()

    def set_completion_callback(self, callback: SubrunCompletionCallback | None) -> None:
        self._completion_callback = callback

    def set_coordination_bridge(self, bridge: object | None) -> None:
        """Attach a CoordinationBridge for confidence-based routing on completion."""
        self._coordination_bridge = bridge

    async def spawn(
        self,
        *,
        parent_request_id: str,
        parent_session_id: str,
        user_message: str,
        runtime: str,
        model: str,
        timeout_seconds: int,
        tool_policy: ToolPolicyDict | None,
        send_event: SendEvent,
        agent_id: str | None = None,
        mode: str | None = None,
        preset: str | None = None,
        orchestrator_agent_ids: list[str] | None = None,
        orchestrator_api: OrchestratorApi | None = None,
    ) -> str:
        run_id = str(uuid.uuid4())
        selected_mode = self._normalize_spawn_mode(mode)
        child_session_id = (
            parent_session_id if selected_mode == "session" else f"{parent_session_id}-subrun-{run_id[:8]}"
        )
        selected_agent_id = (agent_id or "").strip() or "head-agent"
        normalized_selected_agent_id = selected_agent_id.lower()
        selected_orchestrator = orchestrator_api or self._orchestrator_api

        if self._leaf_spawn_depth_guard_enabled and normalized_selected_agent_id not in self._orchestrator_agent_ids:
            raise GuardrailViolation(
                f"Subrun depth policy blocked request: leaf agent '{selected_agent_id}' cannot spawn child runs."
            )

        async with self._lock:
            parent_spec = self._run_specs.get(parent_request_id)
            depth = (parent_spec.depth + 1) if parent_spec else 1
            if depth > self._max_spawn_depth:
                raise GuardrailViolation(
                    f"Subrun depth limit exceeded: requested depth {depth}, max {self._max_spawn_depth}."
                )

            existing_children = len(self._children_by_parent.get(parent_request_id, set()))
            if existing_children >= self._max_children_per_parent:
                raise GuardrailViolation(
                    f"Subrun child limit exceeded for parent {parent_request_id}: "
                    f"{existing_children}/{self._max_children_per_parent}."
                )

            parent_run_id = parent_spec.run_id if parent_spec else None
            root_run_id = parent_spec.root_run_id if parent_spec else parent_request_id

            spec = SubrunSpec(
                run_id=run_id,
                parent_request_id=parent_request_id,
                parent_session_id=parent_session_id,
                child_session_id=child_session_id,
                user_message=user_message,
                runtime=runtime,
                model=model,
                tool_policy=tool_policy,
                preset=(preset or "").strip().lower() or None,
                timeout_seconds=max(0, int(timeout_seconds)),
                depth=depth,
                parent_run_id=parent_run_id,
                root_run_id=root_run_id,
                agent_id=selected_agent_id,
                mode=selected_mode,
                orchestrator_agent_ids=orchestrator_agent_ids,
                orchestrator_api=selected_orchestrator,
            )

            self._run_specs[run_id] = spec
            self._children_by_parent[parent_request_id].add(run_id)
            self._parent_by_child[run_id] = parent_request_id
            if child_session_id != parent_session_id:
                self._children_by_session[parent_session_id].add(child_session_id)

        self._state_store.init_run(
            run_id=run_id,
            session_id=child_session_id,
            request_id=run_id,
            user_message=user_message,
            runtime=runtime,
            model=model,
            meta={
                "subrun": True,
                "depth": depth,
                "parent_run_id": parent_run_id,
                "root_run_id": root_run_id,
                "parent_request_id": parent_request_id,
                "parent_session_id": parent_session_id,
                "agent_id": selected_agent_id,
                "mode": selected_mode,
            },
        )
        self._state_store.set_task_status(run_id=run_id, task_id="request", label="request", status="pending")

        await self._set_status(
            run_id=run_id,
            status="accepted",
            details={
                "parent_request_id": parent_request_id,
                "parent_session_id": parent_session_id,
                "child_session_id": child_session_id,
                "depth": depth,
                "parent_run_id": parent_run_id,
                "root_run_id": root_run_id,
                "agent_id": selected_agent_id,
                "mode": selected_mode,
            },
        )

        await send_event(
            {
                "type": "subrun_status",
                "run_id": run_id,
                "parent_request_id": parent_request_id,
                "parent_session_id": parent_session_id,
                "child_session_id": child_session_id,
                "status": "accepted",
                "depth": depth,
                "agent_id": selected_agent_id,
                "mode": selected_mode,
            }
        )

        async with self._lock:
            # M-15: register placeholder BEFORE create_task to prevent zombie tasks
            self._run_tasks[run_id] = None  # type: ignore[assignment]
        task = asyncio.create_task(self._run(spec=spec, send_event=send_event))
        async with self._lock:
            self._run_tasks[run_id] = task
        self._persist_registry_safe()
        return run_id

    async def wait_for_completion(self, run_id: str, timeout: float = 10.0) -> dict | None:
        async with self._lock:
            task = self._run_tasks.get(run_id)
        if task is None:
            self._prune_retained_statuses()
            self._persist_registry_safe()
            return self._run_status.get(run_id)

        try:
            done, _ = await asyncio.wait({task}, timeout=timeout)
            if not done:
                # Timeout elapsed but task continues running (NOT cancelled)
                pass
        except Exception:
            pass
        self._prune_retained_statuses()
        self._persist_registry_safe()
        return self._run_status.get(run_id)

    def get_status(self, run_id: str) -> dict | None:
        return self._run_status.get(run_id)

    def list_runs(
        self,
        parent_session_id: str | None = None,
        parent_request_id: str | None = None,
        requester_session_id: str | None = None,
        visibility_scope: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        normalized_scope = self._normalize_visibility_scope(visibility_scope)
        entries: list[dict] = []
        for run_id, snapshot in self._run_status.items():
            spec = self._run_specs.get(run_id)
            if parent_session_id and spec and spec.parent_session_id != parent_session_id:
                continue
            if parent_request_id and spec and spec.parent_request_id != parent_request_id:
                continue
            if requester_session_id and spec:
                allowed, _ = self.evaluate_visibility(
                    run_id,
                    requester_session_id=requester_session_id,
                    visibility_scope=normalized_scope,
                )
                if not allowed:
                    continue
            entry = {
                "run_id": run_id,
                "status": snapshot.get("status"),
                "updated_at": snapshot.get("updated_at"),
            }
            if spec:
                entry.update(
                    {
                        "parent_request_id": spec.parent_request_id,
                        "parent_session_id": spec.parent_session_id,
                        "child_session_id": spec.child_session_id,
                        "model": spec.model,
                        "runtime": spec.runtime,
                        "depth": spec.depth,
                        "parent_run_id": spec.parent_run_id,
                        "root_run_id": spec.root_run_id,
                        "agent_id": spec.agent_id,
                        "mode": spec.mode,
                    }
                )
            entries.append(entry)

        entries.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        return entries[: max(1, int(limit))]

    def evaluate_visibility(
        self,
        run_id: str,
        *,
        requester_session_id: str,
        visibility_scope: str | None,
    ) -> tuple[bool, dict]:
        spec = self._run_specs.get(run_id)
        if spec is None:
            return False, {
                "allowed": False,
                "reason": "run_not_found",
                "scope": self._normalize_visibility_scope(visibility_scope),
                "requester_session_id": requester_session_id,
            }

        scope = self._normalize_visibility_scope(visibility_scope)
        requester = (requester_session_id or "").strip()
        if not requester:
            return False, {
                "allowed": False,
                "reason": "missing_requester_session",
                "scope": scope,
                "requester_session_id": requester,
                "target_parent_session_id": spec.parent_session_id,
                "target_child_session_id": spec.child_session_id,
            }

        if scope == "all":
            return True, {
                "allowed": True,
                "reason": "scope_all",
                "scope": scope,
                "requester_session_id": requester,
                "target_parent_session_id": spec.parent_session_id,
                "target_child_session_id": spec.child_session_id,
            }

        if scope == "agent":
            return True, {
                "allowed": True,
                "reason": "scope_agent_single_agent_mode",
                "scope": scope,
                "requester_session_id": requester,
                "target_parent_session_id": spec.parent_session_id,
                "target_child_session_id": spec.child_session_id,
            }

        if scope == "self":
            allowed = requester in {spec.parent_session_id, spec.child_session_id}
            return allowed, {
                "allowed": allowed,
                "reason": "scope_self_match" if allowed else "scope_self_mismatch",
                "scope": scope,
                "requester_session_id": requester,
                "target_parent_session_id": spec.parent_session_id,
                "target_child_session_id": spec.child_session_id,
            }

        visible_sessions = self._collect_visible_sessions(requester)
        allowed = spec.parent_session_id in visible_sessions or spec.child_session_id in visible_sessions
        return allowed, {
            "allowed": allowed,
            "reason": "scope_tree_match" if allowed else "scope_tree_mismatch",
            "scope": scope,
            "requester_session_id": requester,
            "target_parent_session_id": spec.parent_session_id,
            "target_child_session_id": spec.child_session_id,
            "visible_sessions_count": len(visible_sessions),
        }

    def _collect_visible_sessions(self, requester_session_id: str) -> set[str]:
        visible: set[str] = set()
        queue = [requester_session_id]
        while queue:
            current = queue.pop()
            if current in visible:
                continue
            visible.add(current)
            children = self._children_by_session.get(current, set())
            queue.extend(child for child in children if child not in visible)
        return visible

    def _normalize_visibility_scope(self, visibility_scope: str | None) -> str:
        scope = (visibility_scope or "tree").strip().lower()
        if scope not in {"self", "tree", "agent", "all"}:
            return "tree"
        return scope

    def get_info(self, run_id: str) -> dict | None:
        status = self._run_status.get(run_id)
        if status is None:
            return None

        details = status.get("details") or {}
        handover = details.get("handover") if isinstance(details, dict) else None
        if not isinstance(handover, dict):
            handover = self._build_handover_contract(
                status=str(status.get("status") or ""),
                result_text=None,
                notes=details.get("notes") if isinstance(details, dict) else None,
            )

        spec = self._run_specs.get(run_id)
        info = {
            "run_id": run_id,
            "status": status.get("status"),
            "updated_at": status.get("updated_at"),
            "details": details,
            "handover": handover,
            "running": run_id in self._run_tasks,
            "announce_delivery": self._announce_status.get(run_id),
        }
        if spec:
            info.update(
                {
                    "parent_request_id": spec.parent_request_id,
                    "parent_session_id": spec.parent_session_id,
                    "child_session_id": spec.child_session_id,
                    "user_message": spec.user_message,
                    "runtime": spec.runtime,
                    "model": spec.model,
                    "timeout_seconds": spec.timeout_seconds,
                    "tool_policy": spec.tool_policy,
                    "depth": spec.depth,
                    "parent_run_id": spec.parent_run_id,
                    "root_run_id": spec.root_run_id,
                    "agent_id": spec.agent_id,
                    "mode": spec.mode,
                }
            )
        return info

    def get_log(self, run_id: str) -> list[dict] | None:
        run_state = self._state_store.get_run(run_id)
        if run_state is None:
            return None
        return run_state.get("events") or []

    def get_handover_contract(self, run_id: str) -> dict | None:
        status_snapshot = self._run_status.get(run_id)
        if status_snapshot is None:
            return None

        details = status_snapshot.get("details") or {}
        handover = details.get("handover") if isinstance(details, dict) else None
        if isinstance(handover, dict):
            return dict(handover)

        return self._build_handover_contract(
            status=str(status_snapshot.get("status") or ""),
            result_text=None,
            notes=details.get("notes") if isinstance(details, dict) else None,
        )

    async def kill(self, run_id: str, *, cascade: bool = True) -> bool:
        async with self._lock:
            task = self._run_tasks.get(run_id)
        if task is None:
            return False

        if cascade:
            for child_id in self._collect_descendants(run_id):
                await self._cancel_task(child_id)

        await self._cancel_task(run_id)
        return True

    async def kill_all(
        self,
        parent_session_id: str | None = None,
        parent_request_id: str | None = None,
        cascade: bool = True,
    ) -> int:
        async with self._lock:
            if parent_request_id:
                direct_children = list(self._children_by_parent.get(parent_request_id, set()))
                if cascade:
                    run_ids = []
                    for child_id in direct_children:
                        run_ids.append(child_id)
                        run_ids.extend(self._collect_descendants(child_id))
                else:
                    run_ids = direct_children
                run_ids = [run_id for run_id in run_ids if run_id in self._run_tasks]
            elif parent_session_id:
                run_ids = [
                    run_id
                    for run_id, spec in self._run_specs.items()
                    if spec.parent_session_id == parent_session_id and run_id in self._run_tasks
                ]
            else:
                run_ids = list(self._run_tasks.keys())

        killed = 0
        seen: set[str] = set()
        for run_id in run_ids:
            if run_id in seen:
                continue
            seen.add(run_id)
            if await self._cancel_task(run_id):
                killed += 1
        return killed

    def _collect_descendants(self, run_id: str) -> list[str]:
        descendants: list[str] = []
        stack = [run_id]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            children = list(self._children_by_parent.get(current, set()))
            for child in children:
                if child in seen:
                    continue
                seen.add(child)
                descendants.append(child)
                stack.append(child)
        return descendants

    async def _cancel_task(self, run_id: str) -> bool:
        async with self._lock:
            task = self._run_tasks.get(run_id)
        if task is None:
            return False

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        return True

    async def _run(self, *, spec: SubrunSpec, send_event: SendEvent) -> None:
        started_at = monotonic()
        started_at_ts = datetime.now(UTC).isoformat()
        final_text = ""
        status = "failed"
        notes: str | None = None

        try:
            await self._set_status(
                run_id=spec.run_id,
                status="running",
                details={"started_at": started_at_ts},
            )
            self._state_store.set_task_status(run_id=spec.run_id, task_id="request", label="request", status="active")

            await send_event(
                {
                    "type": "subrun_status",
                    "run_id": spec.run_id,
                    "parent_request_id": spec.parent_request_id,
                    "parent_session_id": spec.parent_session_id,
                    "child_session_id": spec.child_session_id,
                    "status": "running",
                    "depth": spec.depth,
                    "agent_id": spec.agent_id,
                    "mode": spec.mode,
                    "started_at": started_at_ts,
                }
            )

            async with self._semaphore:
                if spec.timeout_seconds > 0:
                    final_text = await asyncio.wait_for(
                        self._run_subrun(spec=spec, send_event=send_event),
                        timeout=spec.timeout_seconds,
                    )
                else:
                    final_text = await self._run_subrun(spec=spec, send_event=send_event)
                status = "completed"
                self._state_store.mark_completed(run_id=spec.run_id)
        except TimeoutError:
            status = "timed_out"
            notes = f"Subrun timed out after {spec.timeout_seconds}s."
            self._state_store.mark_failed(run_id=spec.run_id, error=notes)
        except asyncio.CancelledError:
            status = "cancelled"
            notes = "Subrun cancelled."
            self._state_store.mark_failed(run_id=spec.run_id, error=notes)
        except Exception as exc:
            status = "failed"
            notes = str(exc)
            self._state_store.mark_failed(run_id=spec.run_id, error=notes)

        elapsed = round(max(0.0, monotonic() - started_at), 3)
        ended_at_ts = datetime.now(UTC).isoformat()
        handover = self._build_handover_contract(status=status, result_text=final_text, notes=notes)

        try:
            await self._set_status(
                run_id=spec.run_id,
                status=status,
                details={
                    "started_at": started_at_ts,
                    "ended_at": ended_at_ts,
                    "duration_seconds": elapsed,
                    "notes": notes,
                    "result_chars": len(final_text),
                    "handover": handover,
                },
            )

            await send_event(
                {
                    "type": "subrun_status",
                    "run_id": spec.run_id,
                    "parent_request_id": spec.parent_request_id,
                    "parent_session_id": spec.parent_session_id,
                    "child_session_id": spec.child_session_id,
                    "status": status,
                    "duration_seconds": elapsed,
                    "agent_id": spec.agent_id,
                    "mode": spec.mode,
                    "started_at": started_at_ts,
                    "ended_at": ended_at_ts,
                }
            )

            await self._emit_announce_with_retry(
                spec=spec,
                send_event=send_event,
                payload={
                    "type": "subrun_announce",
                    "run_id": spec.run_id,
                    "parent_request_id": spec.parent_request_id,
                    "parent_session_id": spec.parent_session_id,
                    "child_session_id": spec.child_session_id,
                    "status": status,
                    "result": (final_text or "(not available)")[:2000],
                    "notes": notes,
                    "stats": {
                        "started_at": started_at_ts,
                        "ended_at": ended_at_ts,
                        "duration_seconds": elapsed,
                        "result_chars": len(final_text),
                    },
                    "usage": None,
                    "agent_id": spec.agent_id,
                    "mode": spec.mode,
                    "handover": handover,
                },
            )

            completion_callback = self._completion_callback
            if completion_callback is not None:
                with contextlib.suppress(Exception):
                    await completion_callback(
                        parent_session_id=spec.parent_session_id,
                        run_id=spec.run_id,
                        child_agent_id=spec.agent_id,
                        terminal_reason=str(handover.get("terminal_reason") or "subrun-unknown"),
                        child_output=(final_text or None),
                    )

            # Multi-agency: evaluate confidence via CoordinationBridge
            bridge = self._coordination_bridge
            if bridge is not None:
                try:
                    BridgeType = _get_bridge_type()
                    if isinstance(bridge, BridgeType):
                        confidence_decision = await bridge.on_subrun_completed(
                            parent_session_id=spec.parent_session_id,
                            run_id=spec.run_id,
                            child_agent_id=spec.agent_id,
                            terminal_reason=str(handover.get("terminal_reason") or "subrun-unknown"),
                            child_output=(final_text or None),
                            handover_contract=handover,
                        )
                        # Attach confidence decision to handover for upstream use
                        handover["confidence_decision"] = {
                            "action": confidence_decision.action,
                            "confidence": confidence_decision.confidence,
                            "reason": confidence_decision.reason,
                            "selected_agent_id": confidence_decision.selected_agent_id,
                        }
                except Exception:
                    pass  # Multi-agency evaluation must never crash a subrun
        except Exception:
            pass
        finally:
            async with self._lock:
                self._run_tasks.pop(spec.run_id, None)
            self._prune_retained_statuses()
            self._persist_registry_safe()

    async def _run_subrun(self, *, spec: SubrunSpec, send_event: SendEvent) -> str:
        async def relay(payload: dict) -> None:
            forwarded = dict(payload)
            forwarded["subrun_id"] = spec.run_id
            forwarded["parent_request_id"] = spec.parent_request_id
            forwarded["parent_session_id"] = spec.parent_session_id
            forwarded["subrun"] = True

            if forwarded.get("type") == "lifecycle":
                stage = str(forwarded.get("stage", ""))
                self._state_store.append_event(
                    run_id=spec.run_id,
                    event={
                        "stage": stage,
                        "session_id": spec.child_session_id,
                        "details": forwarded.get("details") or {},
                    },
                )

            await self._send_with_lifecycle_error_grace(
                run_id=spec.run_id,
                send_event=send_event,
                payload=forwarded,
            )

        return await spec.orchestrator_api.run_user_message(
            user_message=spec.user_message,
            send_event=relay,
            request_context=RequestContext(
                session_id=spec.child_session_id,
                request_id=spec.run_id,
                runtime=spec.runtime,
                model=spec.model,
                tool_policy=spec.tool_policy,
                agent_id=spec.agent_id,
                depth=spec.depth,
                preset=spec.preset,
                orchestrator_agent_ids=spec.orchestrator_agent_ids,
                queue_mode="wait",
                prompt_mode="subagent",
            ),
        )

    async def _set_status(self, *, run_id: str, status: str, details: dict | None = None) -> None:
        snapshot = {
            "run_id": run_id,
            "status": status,
            "details": details or {},
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self._run_status[run_id] = snapshot
        self._prune_retained_statuses()
        self._persist_registry_safe()

    def _build_handover_contract(self, *, status: str, result_text: str | None, notes: str | None) -> dict:
        normalized_status = str(status or "").strip().lower()
        terminal_reason = self._resolve_terminal_reason(normalized_status)
        confidence = self._resolve_handover_confidence(
            status=normalized_status,
            result_text=result_text,
            notes=notes,
        )
        result = (result_text or "").strip() or None
        if isinstance(result, str):
            result = result[:2000]
        return {
            "terminal_reason": terminal_reason,
            "confidence": confidence,
            "result": result,
        }

    def _resolve_terminal_reason(self, status: str) -> str:
        mapping = {
            "accepted": "subrun-accepted",
            "running": "subrun-running",
            "completed": "subrun-complete",
            "failed": "subrun-error",
            "timed_out": "subrun-timeout",
            "cancelled": "subrun-cancelled",
        }
        return mapping.get(status, "subrun-unknown")

    def _resolve_handover_confidence(self, *, status: str, result_text: str | None, notes: str | None) -> float:
        if status == "completed":
            return 0.85 if (result_text or "").strip() else 0.70
        if status == "timed_out":
            return 0.20
        if status == "failed":
            lowered_notes = (notes or "").lower()
            if "guardrail" in lowered_notes:
                return 0.25
            return 0.15
        if status == "cancelled":
            return 0.10
        if status in {"running", "accepted"}:
            return 0.0
        return 0.05

    def _prune_retained_statuses(self) -> None:
        if not self._run_status:
            return

        active_run_ids = {
            run_id
            for run_id, task in self._run_tasks.items()
            if task is not None and not task.done()
        }
        terminal_candidates: list[tuple[str, str]] = []
        terminal_count = 0
        for run_id, snapshot in self._run_status.items():
            status = str(snapshot.get("status") or "").strip().lower()
            if status not in TERMINAL_STATUSES:
                continue
            terminal_count += 1
            if run_id in active_run_ids:
                continue
            if not self._can_evict_run(run_id, active_run_ids=active_run_ids):
                continue
            terminal_candidates.append((str(snapshot.get("updated_at") or ""), run_id))

        total_overflow = max(0, len(self._run_status) - self._max_retained_run_entries)
        terminal_overflow = max(0, terminal_count - self._max_retained_terminal_runs)
        evict_count = max(total_overflow, terminal_overflow)
        if evict_count <= 0:
            return

        for _, run_id in sorted(terminal_candidates)[:evict_count]:
            self._evict_retained_run(run_id)

    def _can_evict_run(self, run_id: str, *, active_run_ids: set[str]) -> bool:
        if run_id in active_run_ids:
            return False
        snapshot = self._run_status.get(run_id)
        if not isinstance(snapshot, dict):
            return False
        status = str(snapshot.get("status") or "").strip().lower()
        if status not in TERMINAL_STATUSES:
            return False

        children = self._children_by_parent.get(run_id, set())
        for child_id in children:
            child_snapshot = self._run_status.get(child_id)
            child_status = str((child_snapshot or {}).get("status") or "").strip().lower()
            if child_id in active_run_ids:
                return False
            if child_status and child_status not in TERMINAL_STATUSES:
                return False
        return True

    def _evict_retained_run(self, run_id: str) -> None:
        self._run_status.pop(run_id, None)
        self._announce_status.pop(run_id, None)

        spec = self._run_specs.pop(run_id, None)
        if spec is None:
            return

        parent_id = self._parent_by_child.pop(run_id, None)
        if parent_id:
            siblings = self._children_by_parent.get(parent_id)
            if siblings is not None:
                siblings.discard(run_id)
                if not siblings:
                    self._children_by_parent.pop(parent_id, None)

        if spec.child_session_id != spec.parent_session_id:
            sessions = self._children_by_session.get(spec.parent_session_id)
            if sessions is not None:
                sessions.discard(spec.child_session_id)
                if not sessions:
                    self._children_by_session.pop(spec.parent_session_id, None)

    async def _send_with_lifecycle_error_grace(self, *, run_id: str, send_event: SendEvent, payload: dict) -> None:
        is_lifecycle = str(payload.get("type") or "") == "lifecycle"
        if not is_lifecycle:
            await send_event(payload)
            return

        if not self._lifecycle_delivery_error_grace_enabled:
            await send_event(payload)
            return

        try:
            await send_event(payload)
        except Exception as exc:
            try:
                self._state_store.append_event(
                    run_id=run_id,
                    event={
                        "type": "lifecycle_delivery_deferred",
                        "stage": str(payload.get("stage") or ""),
                        "error": str(exc),
                    },
                )
            except Exception:
                return

    def _build_announce_idempotency_key(self, run_id: str) -> str:
        return f"subrun:{run_id}:announce:v1"

    def _normalize_spawn_mode(self, mode: str | None) -> str:
        normalized = (mode or "run").strip().lower()
        if normalized not in {"run", "session"}:
            raise GuardrailViolation(f"Unsupported subrun mode: {mode}")
        return normalized

    async def _record_announce_delivery_event(
        self,
        *,
        run_id: str,
        idempotency_key: str,
        status: str,
        attempt: int,
        error: str | None = None,
    ) -> None:
        self._announce_status[run_id] = {
            "idempotency_key": idempotency_key,
            "status": status,
            "legacy_status": self._to_legacy_announce_status(status),
            "attempt": attempt,
            "error": error,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self._prune_retained_statuses()
        self._persist_registry_safe()
        try:
            self._state_store.append_event(
                run_id=run_id,
                event={
                    "type": "announce_delivery",
                    "idempotency_key": idempotency_key,
                    "status": status,
                    "legacy_status": self._to_legacy_announce_status(status),
                    "attempt": attempt,
                    "error": error,
                },
            )
        except Exception:
            return

    async def _emit_announce_with_retry(self, *, spec: SubrunSpec, send_event: SendEvent, payload: dict) -> None:
        idempotency_key = self._build_announce_idempotency_key(spec.run_id)
        current = self._announce_status.get(spec.run_id)
        if current and current.get("status") == "announced":
            return

        base_delay = self._announce_retry_base_delay_ms / 1000.0
        max_delay = self._announce_retry_max_delay_ms / 1000.0

        for attempt in range(1, self._announce_retry_max_attempts + 1):
            enriched = dict(payload)
            enriched["idempotency_key"] = idempotency_key
            enriched["attempt"] = attempt
            enriched["announce_status"] = "announced"
            enriched["announce_legacy_status"] = self._to_legacy_announce_status("announced")
            try:
                await send_event(enriched)
                await self._record_announce_delivery_event(
                    run_id=spec.run_id,
                    idempotency_key=idempotency_key,
                    status="announced",
                    attempt=attempt,
                    error=None,
                )
                return
            except Exception as exc:
                await self._record_announce_delivery_event(
                    run_id=spec.run_id,
                    idempotency_key=idempotency_key,
                    status=(
                        "announce_retrying" if attempt < self._announce_retry_max_attempts else "announce_failed"
                    ),
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt >= self._announce_retry_max_attempts:
                    return

                delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
                if self._announce_retry_jitter:
                    delay = delay * random.uniform(0.75, 1.25)
                await asyncio.sleep(max(0.01, delay))

    def _to_legacy_announce_status(self, status: str) -> str:
        mapping = {
            "announced": "sent",
            "announce_retrying": "retrying",
            "announce_failed": "dead_letter",
        }
        return mapping.get(status, status)

    def _serialize_spec(self, spec: SubrunSpec) -> dict:
        return {
            "run_id": spec.run_id,
            "parent_request_id": spec.parent_request_id,
            "parent_session_id": spec.parent_session_id,
            "child_session_id": spec.child_session_id,
            "user_message": spec.user_message,
            "runtime": spec.runtime,
            "model": spec.model,
            "tool_policy": spec.tool_policy,
            "preset": spec.preset,
            "timeout_seconds": spec.timeout_seconds,
            "depth": spec.depth,
            "parent_run_id": spec.parent_run_id,
            "root_run_id": spec.root_run_id,
            "agent_id": spec.agent_id,
            "mode": spec.mode,
            "orchestrator_agent_ids": spec.orchestrator_agent_ids,
        }

    def _deserialize_spec(self, payload: dict) -> SubrunSpec | None:
        try:
            run_id = str(payload.get("run_id", "")).strip()
            if not run_id:
                return None
            return SubrunSpec(
                run_id=run_id,
                parent_request_id=str(payload.get("parent_request_id", "")).strip(),
                parent_session_id=str(payload.get("parent_session_id", "")).strip(),
                child_session_id=str(payload.get("child_session_id", "")).strip(),
                user_message=str(payload.get("user_message", "")),
                runtime=str(payload.get("runtime", "")).strip() or "local",
                model=str(payload.get("model", "")).strip() or "",
                tool_policy=payload.get("tool_policy") if isinstance(payload.get("tool_policy"), dict) else None,
                preset=(str(payload.get("preset") or "").strip().lower() or None),
                timeout_seconds=max(0, int(payload.get("timeout_seconds") or 0)),
                depth=max(1, int(payload.get("depth") or 1)),
                parent_run_id=(str(payload.get("parent_run_id") or "").strip() or None),
                root_run_id=str(payload.get("root_run_id", "")).strip() or run_id,
                agent_id=str(payload.get("agent_id", "")).strip() or "head-agent",
                mode=self._normalize_spawn_mode(str(payload.get("mode") or "run")),
                orchestrator_agent_ids=(
                    payload.get("orchestrator_agent_ids")
                    if isinstance(payload.get("orchestrator_agent_ids"), list)
                    else None
                ),
                orchestrator_api=self._orchestrator_api,
            )
        except Exception:
            return None

    def _persist_registry_safe(self) -> None:
        payload = {
            "version": 1,
            "updated_at": datetime.now(UTC).isoformat(),
            "run_specs": {run_id: self._serialize_spec(spec) for run_id, spec in self._run_specs.items()},
            "run_status": self._run_status,
            "announce_status": self._announce_status,
        }
        try:
            self._registry_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._registry_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._registry_file)
        except Exception:
            return

    def _restore_registry(self) -> None:
        try:
            if not self._registry_file.exists():
                return
            payload = json.loads(self._registry_file.read_text(encoding="utf-8"))
        except Exception:
            return

        run_specs_payload = payload.get("run_specs") if isinstance(payload, dict) else None
        if isinstance(run_specs_payload, dict):
            for run_id, raw_spec in run_specs_payload.items():
                if not isinstance(raw_spec, dict):
                    continue
                spec = self._deserialize_spec(raw_spec)
                if spec is None:
                    continue
                self._run_specs[str(run_id)] = spec

        run_status_payload = payload.get("run_status") if isinstance(payload, dict) else None
        if isinstance(run_status_payload, dict):
            for run_id, snapshot in run_status_payload.items():
                if isinstance(snapshot, dict):
                    self._run_status[str(run_id)] = snapshot

        announce_status_payload = payload.get("announce_status") if isinstance(payload, dict) else None
        if isinstance(announce_status_payload, dict):
            for run_id, snapshot in announce_status_payload.items():
                if isinstance(snapshot, dict):
                    self._announce_status[str(run_id)] = snapshot

        self._children_by_parent.clear()
        self._parent_by_child.clear()
        self._children_by_session.clear()
        for run_id, spec in self._run_specs.items():
            self._children_by_parent[spec.parent_request_id].add(run_id)
            self._parent_by_child[run_id] = spec.parent_request_id
            if spec.child_session_id != spec.parent_session_id:
                self._children_by_session[spec.parent_session_id].add(spec.child_session_id)

        self._reconcile_orphaned_runs_after_restore()
        self._prune_retained_statuses()
        self._persist_registry_safe()

    def _reconcile_orphaned_runs_after_restore(self) -> None:
        if not self._restore_orphan_reconcile_enabled:
            return

        reconciled_at = datetime.now(UTC).isoformat()
        now_ts = datetime.now(UTC).timestamp()
        for run_id, snapshot in list(self._run_status.items()):
            if not isinstance(snapshot, dict):
                continue
            status = str(snapshot.get("status") or "").strip().lower()
            if status in TERMINAL_STATUSES:
                continue
            if status not in {"accepted", "running"}:
                continue

            if self._restore_orphan_grace_seconds > 0:
                updated_raw = str(snapshot.get("updated_at") or "").strip()
                if updated_raw:
                    try:
                        updated_ts = datetime.fromisoformat(updated_raw).timestamp()
                        age_seconds = max(0.0, now_ts - updated_ts)
                        if age_seconds < self._restore_orphan_grace_seconds:
                            continue
                    except Exception:
                        pass

            details = snapshot.get("details") if isinstance(snapshot.get("details"), dict) else {}
            reconciled_snapshot = {
                "run_id": run_id,
                "status": "failed",
                "details": {
                    **details,
                    "reconciled": True,
                    "reconciled_at": reconciled_at,
                    "reconcile_reason": "orphaned_after_restore",
                },
                "updated_at": reconciled_at,
            }
            self._run_status[run_id] = reconciled_snapshot

            with contextlib.suppress(Exception):
                self._state_store.mark_failed(run_id=run_id, error="Subrun orphaned after restore.")
            with contextlib.suppress(Exception):
                self._state_store.append_event(
                    run_id=run_id,
                    event={
                        "type": "subrun_orphan_reconciled",
                        "status_before": status,
                        "status_after": "failed",
                        "reason": "orphaned_after_restore",
                        "reconciled_at": reconciled_at,
                    },
                )

        self._persist_registry_safe()
