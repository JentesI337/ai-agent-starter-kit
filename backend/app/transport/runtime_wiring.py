"""Runtime component building, initialization, lazy proxies and utility functions.

Extracted from main.py (Phase 16) — everything related to building and
initializing the runtime lives here so that main.py can remain a slim
entry-point.
"""
from __future__ import annotations

import contextlib
import logging
import re
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

from app.agent import HeadAgent
from app.agent.adapter import UnifiedAgentAdapter
from app.agent.factory_defaults import CODER_AGENT_ID, PRIMARY_AGENT_ID, REVIEW_AGENT_ID
from app.agent.resolution import (
    capability_route_agent,
    effective_orchestrator_agent_ids as _effective_orchestrator_agent_ids_impl,
    looks_like_coding_request,
    normalize_agent_id as _normalize_agent_id_impl,
    resolve_agent as _resolve_agent_impl,
    sync_custom_agents as _sync_custom_agents_impl,
)
from app.agent.store import UnifiedAgentStore
from app.app_state import ControlPlaneState, LazyMappingProxy, LazyObjectProxy, LazyRuntimeRegistry, RuntimeComponents
from app.browser.pool import BrowserPool
from app.config import settings, validate_environment_config
from app.config_service import init_config_service
from app.connectors.connector_store import get_connector_store, init_connector_store
from app.connectors.credential_store import get_credential_store, init_credential_store
from app.connectors.registry import ConnectorRegistry
from app.contracts import OrchestratorApi
from app.contracts.agent_contract import AgentContract
from app.errors import GuardrailViolation, PolicyApprovalCancelledError
from app.llm.health_tracker import ModelHealthTracker
from app.orchestration.events import build_lifecycle_event
from app.orchestration.subrun_lane import SubrunLane
from app.policy.agent_isolation import AgentIsolationPolicy, resolve_agent_isolation_profile
from app.policy.approval_service import PolicyApprovalService
from app.policy.circuit_breaker import CircuitBreakerConfig, CircuitBreakerRegistry
from app.runtime_manager import RuntimeManager
from app.sandbox.repl_session_manager import ReplSessionManager
from app.session.query_service import SessionQueryService
from app.shared.idempotency.manager import IdempotencyManager
from app.startup_tasks import run_shutdown_sequence, run_startup_sequence
from app.state import SqliteStateStore, StateStore
from app.tools.registry.config_store import init_tool_config_store
from app.transport.routers import integrations as integration_handlers

logger = logging.getLogger("app.main")

# Manifest path for agent store bootstrap
_MANIFEST_PATH = Path(__file__).resolve().parent.parent / "agent" / "manifest.json"

control_plane_state = ControlPlaneState()
idempotency_mgr = IdempotencyManager(
    ttl_seconds=settings.idempotency_registry_ttl_seconds,
    max_entries=settings.idempotency_registry_max_entries,
)


# ---------------------------------------------------------------------------
# Sanitization helpers
# ---------------------------------------------------------------------------

def _sanitize_delegation_scope_metadata(payload: dict[str, Any] | None) -> dict[str, Any]:
    source_agent_id = str((payload or {}).get("source_agent_id") or "head-agent").strip().lower() or "head-agent"
    target_agent_id = str((payload or {}).get("target_agent_id") or source_agent_id).strip().lower() or source_agent_id
    reason = str((payload or {}).get("reason") or "scope_match").strip().lower() or "scope_match"
    allowed = bool((payload or {}).get("allowed", False))
    return {
        "source_agent_id": source_agent_id,
        "target_agent_id": target_agent_id,
        "allowed": allowed,
        "reason": reason,
    }


def _sanitize_handover_contract(payload: dict[str, Any] | None) -> dict[str, Any]:
    candidate = payload or {}
    terminal_reason = str(candidate.get("terminal_reason") or "subrun-accepted").strip() or "subrun-accepted"
    confidence_raw = candidate.get("confidence", 0.0)
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    result_value = candidate.get("result")
    if result_value is None:
        result: str | None = None
    else:
        result = str(result_value)[:2000]
    sanitized: dict[str, Any] = {
        "terminal_reason": terminal_reason,
        "confidence": confidence,
        "result": result,
    }
    # Fix 5: propagate synthesis quality so the parent agent can detect subrun failures
    raw_synthesis_valid = candidate.get("synthesis_valid")
    if raw_synthesis_valid is not None:
        sanitized["synthesis_valid"] = bool(raw_synthesis_valid)
    return sanitized


# ---------------------------------------------------------------------------
# Startup / shutdown sequences
# ---------------------------------------------------------------------------

def _startup_sequence() -> None:
    # R1: Initialize ConfigService before anything else
    init_config_service(settings)
    logger.info("config_service_initialized")

    # R2: AgentConfigStore removed — UnifiedAgentStore initialized in _build_runtime_components
    logger.info("unified_agent_store will be initialized during runtime component build")

    # R3: Initialize ToolConfigStore
    _tool_cfg_path = Path(settings.workspace_root) / "tool_configs.json"
    init_tool_config_store(persist_path=_tool_cfg_path)
    logger.info("tool_config_store_initialized persist_path=%s", _tool_cfg_path)

    # R3b+R3c: Initialize SQLite workflow stores (definitions + runs + audit)
    from app.workflows.store import init_workflow_sqlite_stores
    _workflow_db_path = Path(settings.workspace_root) / "workflow_store.sqlite3"
    init_workflow_sqlite_stores(db_path=_workflow_db_path)
    logger.info("workflow_sqlite_stores_initialized db_path=%s", _workflow_db_path)

    # R4: Initialize ConnectorStore and CredentialStore
    _connector_cfg_path = Path(settings.workspace_root) / "connectors.json"
    _connector_cred_path = Path(settings.workspace_root) / "connector_credentials.json"
    _connector_store = init_connector_store(persist_path=_connector_cfg_path)
    _credential_store = init_credential_store(persist_path=_connector_cred_path)
    _connector_registry = ConnectorRegistry()
    integration_handlers.configure(
        connector_store=_connector_store,
        credential_store=_credential_store,
        connector_registry=_connector_registry,
    )
    logger.info("connector_stores_initialized")

    config_validation = validate_environment_config(settings)
    if not bool(config_validation.get("is_valid", True)):
        unknown_keys = list(config_validation.get("unknown_keys") or [])
        preview = ", ".join(unknown_keys[:10])
        suffix = "" if len(unknown_keys) <= 10 else f" (+{len(unknown_keys) - 10} more)"
        raise RuntimeError(f"Strict config validation failed: unknown keys detected ({preview}{suffix}).")
    if str(config_validation.get("validation_status") or "") == "warning":
        logger.warning(
            "config_validation_warning unknown_keys=%s strict_mode=%s",
            config_validation.get("unknown_keys") or [],
            config_validation.get("strict_mode"),
        )
    run_startup_sequence(
        settings=settings,
        logger=logger,
        ensure_runtime_components_initialized=_ensure_runtime_components_initialized,
    )

    # Start workflow scheduler for cron-based triggers
    from app.workflows.scheduler import start_workflow_scheduler
    try:
        start_workflow_scheduler()
    except Exception:
        logger.warning("workflow_scheduler_start_failed", exc_info=True)


def _shutdown_sequence() -> None:
    # Stop workflow scheduler
    from app.workflows.scheduler import stop_workflow_scheduler
    stop_workflow_scheduler()

    # Persist model health snapshots before shutdown
    try:
        _rc = _get_runtime_components()
        _ht = getattr(_rc, "model_health_tracker", None)
        if _ht is not None:
            _ht.persist_sync()
            logger.info("model_health_tracker_persisted_on_shutdown")
    except Exception:
        logger.debug("model_health_tracker_persist_on_shutdown_skipped", exc_info=True)
    # Shutdown all persistent REPL sessions
    if _repl_session_manager is not None:
        import asyncio as _aio
        try:
            loop = _aio.get_event_loop()
            if loop.is_running():
                loop.create_task(_repl_session_manager.shutdown_all())  # noqa: RUF006
            else:
                loop.run_until_complete(_repl_session_manager.shutdown_all())
        except Exception:
            logger.debug("repl_session_manager_shutdown_error", exc_info=True)
    # Shutdown browser pool
    if _browser_pool is not None:
        import asyncio as _aio2
        try:
            loop = _aio2.get_event_loop()
            if loop.is_running():
                loop.create_task(_browser_pool.shutdown())  # noqa: RUF006
            else:
                loop.run_until_complete(_browser_pool.shutdown())
        except Exception:
            logger.debug("browser_pool_shutdown_error", exc_info=True)
    run_shutdown_sequence(active_run_tasks=control_plane_state.active_run_tasks, logger=logger)


# ---------------------------------------------------------------------------
# Runtime component building
# ---------------------------------------------------------------------------

def _build_runtime_components() -> RuntimeComponents:
    agent_store = UnifiedAgentStore(
        persist_dir=Path(settings.agents_dir),
        manifest_path=_MANIFEST_PATH,
    )
    base_agent_registry: dict[str, AgentContract] = {}
    for record in agent_store.list_enabled():
        if record.origin == "custom":
            continue  # custom agents are synced separately
        delegate = HeadAgent(name=record.display_name, role=record.agent_id, agent_record=record)
        base_agent_registry[record.agent_id] = UnifiedAgentAdapter(record, delegate)
    logger.info("unified_agent_store_initialized agents=%d", len(base_agent_registry))

    # Build agent roster string for system prompt injection
    roster_lines: list[str] = []
    for record in agent_store.list_enabled():
        if record.origin == "custom":
            continue
        desc = record.description or record.specialization or record.display_name
        caps = ", ".join(record.capabilities[:5]) if record.capabilities else ""
        line = f"- **{record.display_name}** (`{record.agent_id}`): {desc}"
        if caps:
            line += f" | Capabilities: {caps}"
        roster_lines.append(line)

    if roster_lines:
        agent_roster = (
            "You can delegate tasks to specialist agents using the `spawn_subrun` tool.\n"
            "Choose the right agent based on the task — don't do everything yourself.\n\n"
            + "\n".join(roster_lines)
            + "\n\nTo delegate, use `spawn_subrun` with the agent's ID as `agent_id` "
            "and a fully self-contained prompt describing the task."
        )
        for adapter in base_agent_registry.values():
            if hasattr(adapter, "_delegate"):
                adapter._delegate._agent_roster = agent_roster
                adapter._delegate._build_sub_agents()

    runtime = RuntimeManager()
    if settings.orchestrator_state_backend == "sqlite":
        store = SqliteStateStore(persist_dir=settings.orchestrator_state_dir)
    else:
        store = StateStore(persist_dir=settings.orchestrator_state_dir)
    query_service = SessionQueryService(state_store=store)
    policy_approval_svc = PolicyApprovalService()

    # T2.1: ModelHealthTracker (in-memory ring-buffer + JSON-persist)
    health_tracker: ModelHealthTracker | None = None
    if settings.model_health_tracker_enabled:
        _persist_path = Path(settings.orchestrator_state_dir) / "model_health_snapshots.json"
        health_tracker = ModelHealthTracker(
            ring_buffer_size=max(1, int(settings.model_health_tracker_ring_buffer_size)),
            min_samples=max(1, int(settings.model_health_tracker_min_samples)),
            stale_after_seconds=max(1, int(settings.model_health_tracker_stale_after_seconds)),
            persist_path=_persist_path,
        )
        health_tracker.load_persisted()
        logger.info(
            "model_health_tracker_enabled ring_buffer_size=%d min_samples=%d stale_after=%ds",
            settings.model_health_tracker_ring_buffer_size,
            settings.model_health_tracker_min_samples,
            settings.model_health_tracker_stale_after_seconds,
        )

    # T2.2: CircuitBreakerRegistry (rein in-memory)
    circuit_breaker: CircuitBreakerRegistry | None = None
    if settings.circuit_breaker_enabled:
        circuit_breaker = CircuitBreakerRegistry(
            config=CircuitBreakerConfig(
                failure_threshold=max(1, int(settings.circuit_breaker_failure_threshold)),
                failure_window_seconds=max(1, int(settings.circuit_breaker_failure_window_seconds)),
                recovery_timeout_seconds=max(1, int(settings.circuit_breaker_recovery_timeout_seconds)),
                success_threshold=max(1, int(settings.circuit_breaker_success_threshold)),
            )
        )
        logger.info(
            "circuit_breaker_enabled threshold=%d window=%ds recovery=%ds",
            settings.circuit_breaker_failure_threshold,
            settings.circuit_breaker_failure_window_seconds,
            settings.circuit_breaker_recovery_timeout_seconds,
        )

    orchestrators: dict[str, OrchestratorApi] = {
        agent_id: OrchestratorApi(
            agent=agent_instance,
            state_store=store,
            health_tracker=health_tracker,
            circuit_breaker=circuit_breaker,
        )
        for agent_id, agent_instance in base_agent_registry.items()
    }
    return RuntimeComponents(
        agent_registry=base_agent_registry,
        runtime_manager=runtime,
        state_store=store,
        session_query_service=query_service,
        policy_approval_service=policy_approval_svc,
        orchestrator_registry=orchestrators,
        agent_store=agent_store,
        model_health_tracker=health_tracker,
        circuit_breaker=circuit_breaker,
    )


# Module-level reference for shutdown cleanup
_repl_session_manager: ReplSessionManager | None = None
_browser_pool: BrowserPool | None = None


def _initialize_runtime_components(components: RuntimeComponents) -> None:
    global _repl_session_manager
    global _browser_pool

    _sync_custom_agents(components)

    # Create ReplSessionManager if persistent REPL is enabled
    repl_manager: ReplSessionManager | None = None
    if settings.repl_enabled:
        sandbox_base = settings.repl_sandbox_dir or None
        repl_manager = ReplSessionManager(
            max_sessions=settings.repl_max_sessions,
            timeout_seconds=settings.repl_timeout_seconds,
            max_memory_mb=settings.repl_max_memory_mb,
            max_output_chars=settings.repl_max_output_chars,
            sandbox_base=sandbox_base,
        )
        _repl_session_manager = repl_manager
        logger.info(
            "repl_session_manager_created max_sessions=%d timeout=%ds",
            settings.repl_max_sessions,
            settings.repl_timeout_seconds,
        )

    # Create BrowserPool if browser control is enabled
    browser_pool: BrowserPool | None = None
    if settings.browser_enabled:
        browser_pool = BrowserPool(
            max_contexts=settings.browser_max_contexts,
            navigation_timeout_ms=settings.browser_navigation_timeout_ms,
            context_ttl_seconds=settings.browser_context_ttl_seconds,
        )
        _browser_pool = browser_pool
        logger.info(
            "browser_pool_created max_contexts=%d ttl=%ds",
            settings.browser_max_contexts,
            settings.browser_context_ttl_seconds,
        )

    for _agent in components.agent_registry.values():
        _delegate = getattr(_agent, "_delegate", _agent)
        _tools = getattr(_delegate, "tools", None)
        if _tools is not None and hasattr(_tools, "set_repl_manager") and repl_manager is not None:
            _tools.set_repl_manager(repl_manager)
        if _tools is not None and hasattr(_tools, "set_browser_pool") and browser_pool is not None:
            _tools.set_browser_pool(browser_pool)

    # Wire connector services to agent tooling (enables api_call, api_list_connectors, api_auth)
    if settings.api_connectors_enabled:
        try:
            _cs = get_connector_store()
            _crs = get_credential_store()
            _cr = ConnectorRegistry()
            for _agent in components.agent_registry.values():
                _delegate = getattr(_agent, "_delegate", _agent)
                _tools = getattr(_delegate, "tools", None)
                if _tools is not None and hasattr(_tools, "set_connector_services"):
                    _tools.set_connector_services(_cs, _crs, _cr)
            logger.info("connector_services_wired_to_agents")
        except Exception:
            logger.warning("connector_services_wiring_failed", exc_info=True)

    components.agent = components.agent_registry[PRIMARY_AGENT_ID]
    components.orchestrator_api = components.orchestrator_registry[PRIMARY_AGENT_ID]
    components.subrun_lane = SubrunLane(
        orchestrator_api=components.orchestrator_api,
        state_store=components.state_store,
        max_concurrent=settings.subrun_max_concurrent,
        max_spawn_depth=settings.subrun_max_spawn_depth,
        max_children_per_parent=settings.subrun_max_children_per_parent,
        announce_retry_max_attempts=settings.subrun_announce_retry_max_attempts,
        announce_retry_base_delay_ms=settings.subrun_announce_retry_base_delay_ms,
        announce_retry_max_delay_ms=settings.subrun_announce_retry_max_delay_ms,
        announce_retry_jitter=settings.subrun_announce_retry_jitter,
        leaf_spawn_depth_guard_enabled=settings.subrun_leaf_spawn_depth_guard_enabled,
        orchestrator_agent_ids=list(_effective_orchestrator_agent_ids(components)),
        restore_orphan_reconcile_enabled=settings.subrun_restore_orphan_reconcile_enabled,
        restore_orphan_grace_seconds=settings.subrun_restore_orphan_grace_seconds,
        lifecycle_delivery_error_grace_enabled=settings.subrun_lifecycle_delivery_error_grace_enabled,
    )

    async def _on_subrun_complete_announce(
        *,
        parent_session_id: str,
        run_id: str,
        child_agent_id: str,
        terminal_reason: str,
        child_output: str | None,
    ) -> None:
        announce_text = (
            f"[subrun_announce] spawned_subrun_id={run_id} agent_id={child_agent_id} terminal_reason={terminal_reason}"
        )
        if child_output:
            announce_text = f"{announce_text}\n[child_output_summary] {child_output[:500]}"

        components.agent.memory.add(parent_session_id, "tool:spawn_subrun_announce", announce_text)

    components.subrun_lane.set_completion_callback(_on_subrun_complete_announce)

    # Multi-Agency Phase 1: Wire CoordinationBridge for confidence-based routing
    if settings.multi_agency_enabled:
        from app.multi_agency.coordination_bridge import CoordinationBridge

        bridge = CoordinationBridge(session_id="global")
        components.subrun_lane.set_coordination_bridge(bridge)
        logger.info("multi_agency_coordination_bridge_wired")

    async def _spawn_subrun_from_agent(
        *,
        parent_request_id: str,
        parent_session_id: str,
        user_message: str,
        model: str | None,
        timeout_seconds: int,
        tool_policy,
        send_event,
        agent_id: str,
        mode: str,
        source_agent_id: str | None = None,
        orchestration_context: dict | None = None,  # Fix 6: inherited delegation context
    ) -> dict:
        _sync_custom_agents(components)
        runtime_state = components.runtime_manager.get_state()
        selected_model = (model or "").strip() or runtime_state.model
        if runtime_state.runtime == "local":
            selected_model = await components.runtime_manager.ensure_model_ready(
                send_event, parent_session_id, selected_model
            )
        else:
            selected_model = await components.runtime_manager.resolve_api_request_model(selected_model)
        normalized_agent_id = _normalize_agent_id(agent_id)
        selected_orchestrator = components.orchestrator_registry.get(normalized_agent_id)
        if selected_orchestrator is None:
            raise GuardrailViolation(f"Unsupported subrun agent: {agent_id}")

        source_id = _normalize_agent_id(source_agent_id or normalized_agent_id)
        definitions = {item.id: item for item in components.custom_agent_store.list()}
        source_profile = resolve_agent_isolation_profile(
            agent_id=source_id,
            custom_definition=definitions.get(source_id),
        )
        target_profile = resolve_agent_isolation_profile(
            agent_id=normalized_agent_id,
            custom_definition=definitions.get(normalized_agent_id),
        )
        isolation_policy = AgentIsolationPolicy.from_settings(settings)
        isolation_decision = isolation_policy.evaluate(
            source_agent_id=source_id,
            target_agent_id=normalized_agent_id,
            source_profile=source_profile,
            target_profile=target_profile,
        )
        await send_event(
            build_lifecycle_event(
                request_id=parent_request_id,
                session_id=parent_session_id,
                stage="subrun_isolation_checked",
                details=isolation_decision.as_details(),
            )
        )
        if not isolation_decision.allowed:
            await send_event(
                build_lifecycle_event(
                    request_id=parent_request_id,
                    session_id=parent_session_id,
                    stage="subrun_isolation_blocked",
                    details=isolation_decision.as_details(),
                )
            )
            raise GuardrailViolation(
                "Subrun isolation blocked: cross-scope delegation requires explicit allowlist pair."
            )

        effective_timeout = max(0, int(timeout_seconds))
        if effective_timeout == 0:
            effective_timeout = int(settings.subrun_timeout_seconds)
        run_id = await components.subrun_lane.spawn(
            parent_request_id=parent_request_id,
            parent_session_id=parent_session_id,
            user_message=user_message,
            runtime=runtime_state.runtime,
            model=selected_model,
            timeout_seconds=effective_timeout,
            tool_policy=tool_policy,
            preset=None,
            send_event=send_event,
            agent_id=normalized_agent_id,
            # SubrunLane.spawn only accepts "run" / "session"; "wait" is handled
            # by this function after spawn returns (await wait_for_completion below).
            mode="run" if mode == "wait" else mode,
            orchestrator_agent_ids=sorted(_effective_orchestrator_agent_ids(components)),
            orchestrator_api=selected_orchestrator,
        )
        # Fix: for non-blocking spawn modes, wait until any pending policy-approval gate
        # is decided before returning control to the parent agent.  This prevents the
        # parent from synthesising while a spawned subrun is blocked on a policy gate.
        if mode != "wait":
            _ph_timeout = float(effective_timeout) + float(settings.policy_approval_wait_seconds) + 5.0
            with contextlib.suppress(TimeoutError):
                await components.subrun_lane.wait_for_policy_hold_clear_or_complete(run_id, timeout=_ph_timeout)
        # mode="wait": warte auf Abschluss des Kind-Runs, bevor Handover-Status gelesen wird.
        # Ohne diesen Wait liefert get_handover_contract immer "subrun-accepted" zurück,
        # weil der asyncio.Task noch nicht gestartet / abgeschlossen hat.
        if mode == "wait":
            wait_timeout = max(5.0, float(effective_timeout) + 5.0)
            with contextlib.suppress(TimeoutError):
                await components.subrun_lane.wait_for_completion(run_id, timeout=wait_timeout)
        handover = _sanitize_handover_contract(components.subrun_lane.get_handover_contract(run_id))
        # Fix 5: surface synthesis_valid at the top level of the result dict so agent.py
        # can read it from spawn_result without digging into the handover sub-dict.
        result: dict[str, Any] = {
            "run_id": run_id,
            "mode": mode,
            "agent_id": normalized_agent_id,
            "handover": handover,
            "delegation_scope": _sanitize_delegation_scope_metadata(isolation_decision.as_details()),
        }
        if "synthesis_valid" in handover:
            result["synthesis_valid"] = handover["synthesis_valid"]
        return result

    async def _request_policy_override_from_agent(
        *,
        send_event,
        session_id: str,
        request_id: str,
        agent_name: str,
        tool: str,
        resource: str,
        display_text: str,
    ) -> bool:
        if await components.policy_approval_service.is_preapproved(tool=tool, resource=resource, session_id=session_id):
            return True
        approval = await components.policy_approval_service.create(
            run_id=request_id,
            session_id=session_id,
            agent_name=agent_name,
            tool=tool,
            resource=resource,
            display_text=display_text,
        )
        approval_status = str(approval.get("status") or "").strip().lower()
        approval_reused = bool(approval.get("idempotent_reuse"))
        if approval_status == "pending":
            await send_event(
                {
                    "type": "policy_approval_required",
                    "agent": agent_name,
                    "request_id": request_id,
                    "session_id": session_id,
                    "approval": {
                        "approval_id": approval["approval_id"],
                        "tool": tool,
                        "resource": resource,
                        "display_text": display_text,
                        "options": ["allow_once", "allow_session", "cancel"],
                        "scope": "session_tool",
                        "status": "pending",
                        "idempotent_reuse": approval_reused,
                    },
                }
            )
            await send_event(
                {
                    "type": "lifecycle",
                    "agent": agent_name,
                    "stage": "policy_approval_requested",
                    "request_id": request_id,
                    "session_id": session_id,
                    "details": {
                        "approval_id": approval["approval_id"],
                        "tool": tool,
                        "resource": resource,
                        "idempotent_reuse": approval_reused,
                    },
                }
            )
            # Propagate policy hold to parent run so its spawning coroutine can pause
            # until the user makes a decision (fix: race condition for mode='run' spawns).
            if components.subrun_lane.is_subrun(request_id):
                components.subrun_lane.mark_policy_hold(request_id)

        decision = str(approval.get("decision") or "").strip().lower() or None
        if decision is None:
            decision = await components.policy_approval_service.wait_for_decision(
                approval_id=approval["approval_id"],
                timeout_seconds=settings.policy_approval_wait_seconds,
            )
        # Release policy hold regardless of decision outcome (no-op if not a subrun).
        components.subrun_lane.release_policy_hold(request_id)
        await send_event(
            {
                "type": "lifecycle",
                "agent": agent_name,
                "stage": "policy_approval_decision",
                "request_id": request_id,
                "session_id": session_id,
                "details": {
                    "approval_id": approval["approval_id"],
                    "tool": tool,
                    "resource": resource,
                    "decision": decision,
                    "idempotent_reuse": approval_reused,
                },
            }
        )
        if decision == "cancel":
            raise PolicyApprovalCancelledError(
                "Command execution was cancelled by user.",
                error_code="policy_approval_cancelled",
                details={
                    "approval_id": approval["approval_id"],
                    "tool": tool,
                    "resource": resource,
                },
            )
        return decision in {"allow_once", "allow_always", "allow_session"}

    for owner_agent_id, agent_instance in components.agent_registry.items():
        set_handler = getattr(agent_instance, "set_spawn_subrun_handler", None)
        if callable(set_handler):

            async def _bound_spawn_subrun_handler(*, _owner_agent_id: str = owner_agent_id, **kwargs):
                if "source_agent_id" not in kwargs or kwargs.get("source_agent_id") is None:
                    kwargs["source_agent_id"] = _owner_agent_id
                return await _spawn_subrun_from_agent(**kwargs)

            set_handler(_bound_spawn_subrun_handler)
        set_policy_handler = getattr(agent_instance, "set_policy_approval_handler", None)
        if callable(set_policy_handler):
            set_policy_handler(_request_policy_override_from_agent)

    components.policy_approval_handler = _request_policy_override_from_agent


# ---------------------------------------------------------------------------
# Lazy runtime registry + proxy exports
# ---------------------------------------------------------------------------

_runtime_registry = LazyRuntimeRegistry(builder=_build_runtime_components, initializer=_initialize_runtime_components)


def _get_runtime_components() -> RuntimeComponents:
    return _runtime_registry.get_components()


def _ensure_runtime_components_initialized() -> RuntimeComponents:
    return _runtime_registry.ensure_initialized()


agent_registry: MutableMapping[str, AgentContract] = LazyMappingProxy(lambda: _get_runtime_components().agent_registry)
runtime_manager = LazyObjectProxy(lambda: _get_runtime_components().runtime_manager)
state_store = LazyObjectProxy(lambda: _get_runtime_components().state_store)
session_query_service = LazyObjectProxy(lambda: _get_runtime_components().session_query_service)
policy_approval_service = LazyObjectProxy(lambda: _get_runtime_components().policy_approval_service)
orchestrator_registry: MutableMapping[str, OrchestratorApi] = LazyMappingProxy(
    lambda: _get_runtime_components().orchestrator_registry
)
agent_store = LazyObjectProxy(lambda: _get_runtime_components().agent_store)
custom_agent_store = LazyObjectProxy(lambda: _get_runtime_components().custom_agent_store)
agent = LazyObjectProxy(lambda: _get_runtime_components().agent)
orchestrator_api = LazyObjectProxy(lambda: _get_runtime_components().orchestrator_api)
subrun_lane = LazyObjectProxy(lambda: _get_runtime_components().subrun_lane)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _get_tool_telemetry():
    """Lazy accessor for the ToolTelemetry instance inside the agent's TEM."""
    try:
        a = _get_runtime_components().agent
        tem = getattr(a, "_tool_execution_manager", None)
        return getattr(tem, "_telemetry", None) if tem else None
    except Exception:
        return None


def _normalize_agent_id(agent_id: str | None) -> str:
    return _normalize_agent_id_impl(
        agent_id,
        primary_agent_id=PRIMARY_AGENT_ID,
        legacy_agent_aliases={},
    )


def _effective_orchestrator_agent_ids(components: RuntimeComponents | None = None) -> set[str]:
    if components is None:
        components = _get_runtime_components()
    return _effective_orchestrator_agent_ids_impl(
        configured_agent_ids=settings.subrun_orchestrator_agent_ids,
        primary_agent_id=PRIMARY_AGENT_ID,
        custom_orchestrator_agent_ids=components.custom_orchestrator_agent_ids,
    )


def _sync_custom_agents(components: RuntimeComponents | None = None) -> None:
    if components is None:
        components = _get_runtime_components()

    # Build connector services tuple if connectors are enabled
    _conn_services: tuple | None = None
    if settings.api_connectors_enabled:
        try:
            _conn_services = (get_connector_store(), get_credential_store(), ConnectorRegistry())
        except Exception:
            _conn_services = None

    _sync_custom_agents_impl(
        components=components,
        normalize_agent_id_fn=_normalize_agent_id,
        primary_agent_id=PRIMARY_AGENT_ID,
        coder_agent_id=CODER_AGENT_ID,
        review_agent_id=REVIEW_AGENT_ID,
        effective_orchestrator_agent_ids_fn=_effective_orchestrator_agent_ids,
        browser_pool=_browser_pool,
        repl_manager=_repl_session_manager,
        connector_services=_conn_services,
    )
    if components.policy_approval_handler is not None:
        for agent_instance in components.agent_registry.values():
            set_policy_handler = getattr(agent_instance, "set_policy_approval_handler", None)
            if callable(set_policy_handler):
                set_policy_handler(components.policy_approval_handler)


def _resolve_agent(agent_id: str | None):
    return _resolve_agent_impl(
        agent_id=agent_id,
        sync_custom_agents_fn=_sync_custom_agents,
        normalize_agent_id_fn=_normalize_agent_id,
        agent_registry=agent_registry,
        orchestrator_registry=orchestrator_registry,
    )


def _route_agent_for_message(
    *,
    requested_agent_id: str | None,
    message: str,
    preset: str | None,
) -> tuple[str, str | None, tuple[str, ...], list[dict[str, object]]]:
    _sync_custom_agents()
    normalized_requested = _normalize_agent_id(requested_agent_id)
    effective_agent_id, reason, required_capabilities, ranked_matches = capability_route_agent(
        requested_agent_id=normalized_requested,
        message=message,
        preset=preset,
        primary_agent_id=PRIMARY_AGENT_ID,
        agent_registry=agent_registry,
    )
    ranked_payload = [
        {
            "agent_id": item.agent_id,
            "score": item.score,
            "matched_capabilities": list(item.matched_capabilities),
        }
        for item in ranked_matches[:5]
    ]
    return effective_agent_id, reason, required_capabilities, ranked_payload


def _looks_like_review_request(message: str) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return False

    review_keywords = (
        "review",
        "code review",
        "audit",
        "critique",
        "quality check",
        "security review",
        "find issues",
        "what is wrong",
        "smell",
    )
    if not any(marker in text for marker in review_keywords):
        return False

    evidence_patterns = (
        r"https?://",
        r"```",
        r"diff\s+--git",
        r"\b[a-f0-9]{7,40}\b",
        r"\b[\w./-]+\.(py|ts|js|java|go|rs|json|yml|yaml|md|html|css)\b",
        r"\b(\+\+\+|---|@@)\b",
    )
    has_evidence = any(re.search(pattern, text, re.IGNORECASE) for pattern in evidence_patterns)
    if not has_evidence:
        return False

    execution_or_research_markers = (
        "orchestrate",
        "research",
        "fact check",
        "fact-check",
        "write",
        "save",
        "create",
        "build",
        "implement",
        "run",
        "execute",
        "generate",
    )
    return not any(marker in text for marker in execution_or_research_markers)


# Re-export for backward compat (used by test_main_startup_config_validation via monkeypatch)
looks_like_coding_request = looks_like_coding_request  # noqa: PLW0127
