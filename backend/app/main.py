from __future__ import annotations

import contextlib
import logging
import re
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

from app.agents.head_agent_adapter import (
    ArchitectAgentAdapter,
    CoderAgentAdapter,
    DevOpsAgentAdapter,
    DocAgentAdapter,
    ECommerceAgentAdapter,
    FinTechAgentAdapter,
    HeadAgentAdapter,
    HealthTechAgentAdapter,
    IndustryTechAgentAdapter,
    LegalTechAgentAdapter,
    RefactorAgentAdapter,
    ResearcherAgentAdapter,
    ReviewAgentAdapter,
    SecurityAgentAdapter,
    TestAgentAdapter,
)
from app.app_setup import build_fastapi_app, build_lifespan_context
from app.app_state import ControlPlaneState, LazyMappingProxy, LazyObjectProxy, LazyRuntimeRegistry, RuntimeComponents
from app.config import resolved_prompt_settings, settings, validate_environment_config
from app.contracts.agent_contract import AgentContract
from app.control_models import AgentTestRequest, RunStartRequest
from app.control_router_wiring import include_control_routers
from app.custom_agents import CustomAgentStore
from app.policy_store import PolicyStore
from app.errors import GuardrailViolation, PolicyApprovalCancelledError
from app.handlers import (
    agent_handlers,
    policy_handlers,
    run_handlers,
    session_handlers,
    skills_handlers,
    tools_handlers,
    workflow_handlers,
)
from app.interfaces import OrchestratorApi
from app.orchestrator.events import build_lifecycle_event
from app.orchestrator.subrun_lane import SubrunLane
from app.routers import (
    build_agents_router,
    build_run_api_router,
    build_runtime_debug_router,
    build_subruns_router,
    build_ws_agent_router,
)
from app.routers.run_api import RunApiRouterHandlers
from app.routers.policies import build_policies_router
from app.run_endpoints import (
    AgentTestDependencies,
    RunEndpointsDependencies,
    run_agent_test,
    start_run as run_endpoint_start,
    wait_run as run_endpoint_wait,
)
from app.runtime_debug_endpoints import (
    RuntimeDebugDependencies,
    api_calibration_recommendations,
    api_resolved_prompt_settings,
    api_runtime_features,
    api_runtime_status,
    api_runtime_update_features,
    api_test_ping,
    api_tool_telemetry_stats,
)
from app.runtime_manager import RuntimeManager
from app.services import (
    PolicyApprovalService,
    SessionQueryService,
    build_run_start_fingerprint as _build_run_start_fingerprint,
    build_session_patch_fingerprint as _build_session_patch_fingerprint,
    build_session_reset_fingerprint as _build_session_reset_fingerprint,
    build_workflow_create_fingerprint as _build_workflow_create_fingerprint,
    build_workflow_delete_fingerprint as _build_workflow_delete_fingerprint,
    build_workflow_execute_fingerprint as _build_workflow_execute_fingerprint,
)
from app.services.agent_isolation import AgentIsolationPolicy, resolve_agent_isolation_profile
from app.services.agent_resolution import (
    capability_route_agent,
    effective_orchestrator_agent_ids as _effective_orchestrator_agent_ids_impl,
    looks_like_coding_request,
    normalize_agent_id as _normalize_agent_id_impl,
    resolve_agent as _resolve_agent_impl,
    sync_custom_agents as _sync_custom_agents_impl,
)
from app.services.circuit_breaker import CircuitBreakerConfig, CircuitBreakerRegistry
from app.services.idempotency_manager import IdempotencyManager
from app.services.repl_session_manager import ReplSessionManager
from app.services.browser_pool import BrowserPool
from app.services.embedding_service import EmbeddingService
from app.services.vector_store import VectorStore
from app.services.log_secret_filter import install_secret_filter
from app.services.model_health_tracker import ModelHealthTracker
from app.services.request_normalization import normalize_preset
from app.startup_tasks import run_shutdown_sequence, run_startup_sequence
from app.state import SqliteStateStore, StateStore
from app.subrun_endpoints import (
    SubrunEndpointsDependencies,
    api_subruns_get,
    api_subruns_kill,
    api_subruns_kill_all_async,
    api_subruns_list,
    api_subruns_log,
)
from app.ws_handler import WsHandlerDependencies

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
# SEC (CFG-07): Install secret filter to redact sensitive data from logs
install_secret_filter()
logger = logging.getLogger("app.main")
app = build_fastapi_app(title="AI Agent Starter Kit", settings=settings)
PRIMARY_AGENT_ID = "head-agent"
CODER_AGENT_ID = "coder-agent"
REVIEW_AGENT_ID = "review-agent"
RESEARCHER_AGENT_ID = "researcher-agent"
ARCHITECT_AGENT_ID = "architect-agent"
TEST_AGENT_ID = "test-agent"
SECURITY_AGENT_ID = "security-agent"
DOC_AGENT_ID = "doc-agent"
REFACTOR_AGENT_ID = "refactor-agent"
DEVOPS_AGENT_ID = "devops-agent"
FINTECH_AGENT_ID = "fintech-agent"
HEALTHTECH_AGENT_ID = "healthtech-agent"
LEGALTECH_AGENT_ID = "legaltech-agent"
ECOMMERCE_AGENT_ID = "ecommerce-agent"
INDUSTRYTECH_AGENT_ID = "industrytech-agent"
control_plane_state = ControlPlaneState()
idempotency_mgr = IdempotencyManager(
    ttl_seconds=settings.idempotency_registry_ttl_seconds,
    max_entries=settings.idempotency_registry_max_entries,
)


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


def _startup_sequence() -> None:
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


def _shutdown_sequence() -> None:
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
                loop.create_task(_repl_session_manager.shutdown_all())
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
                loop.create_task(_browser_pool.shutdown())
            else:
                loop.run_until_complete(_browser_pool.shutdown())
        except Exception:
            logger.debug("browser_pool_shutdown_error", exc_info=True)
    # Shutdown embedding service
    if _embedding_service is not None:
        import asyncio as _aio3
        try:
            loop = _aio3.get_event_loop()
            if loop.is_running():
                loop.create_task(_embedding_service.close())
            else:
                loop.run_until_complete(_embedding_service.close())
        except Exception:
            logger.debug("embedding_service_shutdown_error", exc_info=True)
    run_shutdown_sequence(active_run_tasks=control_plane_state.active_run_tasks, logger=logger)


app.router.lifespan_context = build_lifespan_context(
    on_startup=_startup_sequence,
    on_shutdown=_shutdown_sequence,
)


def _build_runtime_components() -> RuntimeComponents:
    base_agent_registry: dict[str, AgentContract] = {
        PRIMARY_AGENT_ID: HeadAgentAdapter(),
        CODER_AGENT_ID: CoderAgentAdapter(),
        REVIEW_AGENT_ID: ReviewAgentAdapter(),
        RESEARCHER_AGENT_ID: ResearcherAgentAdapter(),
        ARCHITECT_AGENT_ID: ArchitectAgentAdapter(),
        TEST_AGENT_ID: TestAgentAdapter(),
        SECURITY_AGENT_ID: SecurityAgentAdapter(),
        DOC_AGENT_ID: DocAgentAdapter(),
        REFACTOR_AGENT_ID: RefactorAgentAdapter(),
        DEVOPS_AGENT_ID: DevOpsAgentAdapter(),
        FINTECH_AGENT_ID: FinTechAgentAdapter(),
        HEALTHTECH_AGENT_ID: HealthTechAgentAdapter(),
        LEGALTECH_AGENT_ID: LegalTechAgentAdapter(),
        ECOMMERCE_AGENT_ID: ECommerceAgentAdapter(),
        INDUSTRYTECH_AGENT_ID: IndustryTechAgentAdapter(),
    }
    runtime = RuntimeManager()
    if settings.orchestrator_state_backend == "sqlite":
        store = SqliteStateStore(persist_dir=settings.orchestrator_state_dir)
    else:
        store = StateStore(persist_dir=settings.orchestrator_state_dir)
    query_service = SessionQueryService(state_store=store)
    policy_approval_service = PolicyApprovalService()

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
    custom_store = CustomAgentStore(persist_dir=settings.custom_agents_dir)
    return RuntimeComponents(
        agent_registry=base_agent_registry,
        runtime_manager=runtime,
        state_store=store,
        session_query_service=query_service,
        policy_approval_service=policy_approval_service,
        orchestrator_registry=orchestrators,
        custom_agent_store=custom_store,
        model_health_tracker=health_tracker,
        circuit_breaker=circuit_breaker,
    )


# Module-level reference for shutdown cleanup
_repl_session_manager: ReplSessionManager | None = None
_browser_pool: BrowserPool | None = None
_embedding_service: EmbeddingService | None = None
_vector_store: VectorStore | None = None


def _initialize_runtime_components(components: RuntimeComponents) -> None:
    global _repl_session_manager  # noqa: PLW0603
    global _browser_pool  # noqa: PLW0603
    global _embedding_service  # noqa: PLW0603
    global _vector_store  # noqa: PLW0603
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

    # Create RAG services if enabled
    embedding_service: EmbeddingService | None = None
    vector_store: VectorStore | None = None
    if settings.rag_enabled:
        embedding_service = EmbeddingService(
            provider=settings.rag_embedding_provider,
            model=settings.rag_embedding_model,
            base_url=settings.rag_embedding_base_url,
            api_key=settings.rag_embedding_api_key or None,
        )
        _embedding_service = embedding_service
        vector_store = VectorStore(
            persist_dir=settings.rag_persist_dir,
            max_chunks_per_collection=settings.rag_max_chunks_per_collection,
        )
        _vector_store = vector_store
        logger.info(
            "rag_services_created provider=%s model=%s persist_dir=%s",
            settings.rag_embedding_provider,
            settings.rag_embedding_model,
            settings.rag_persist_dir,
        )

        # Health-checks for RAG subsystem
        _rag_persist = Path(settings.rag_persist_dir)
        try:
            _rag_persist.mkdir(parents=True, exist_ok=True)
            _probe = _rag_persist / ".write_probe"
            _probe.write_text("ok", encoding="utf-8")
            _probe.unlink()
            logger.info("rag_health_check persist_dir=%s writable=true", _rag_persist)
        except OSError as _exc:
            logger.warning("rag_health_check persist_dir=%s writable=false error=%s", _rag_persist, _exc)

    for _agent in components.agent_registry.values():
        _delegate = getattr(_agent, "_delegate", _agent)
        _tools = getattr(_delegate, "tools", None)
        if _tools is not None and hasattr(_tools, "set_custom_agent_store"):
            _tools.set_custom_agent_store(
                components.custom_agent_store,
                lambda: _sync_custom_agents(components),
            )
        if _tools is not None and hasattr(_tools, "set_repl_manager") and repl_manager is not None:
            _tools.set_repl_manager(repl_manager)
        if _tools is not None and hasattr(_tools, "set_browser_pool") and browser_pool is not None:
            _tools.set_browser_pool(browser_pool)
        if _tools is not None and hasattr(_tools, "set_rag_services") and embedding_service is not None and vector_store is not None:
            _tools.set_rag_services(embedding_service, vector_store)

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
custom_agent_store = LazyObjectProxy(lambda: _get_runtime_components().custom_agent_store)
agent = LazyObjectProxy(lambda: _get_runtime_components().agent)
orchestrator_api = LazyObjectProxy(lambda: _get_runtime_components().orchestrator_api)
subrun_lane = LazyObjectProxy(lambda: _get_runtime_components().subrun_lane)


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
    _sync_custom_agents_impl(
        components=components,
        normalize_agent_id_fn=_normalize_agent_id,
        primary_agent_id=PRIMARY_AGENT_ID,
        coder_agent_id=CODER_AGENT_ID,
        review_agent_id=REVIEW_AGENT_ID,
        effective_orchestrator_agent_ids_fn=_effective_orchestrator_agent_ids,
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


tools_handlers.configure(
    tools_handlers.ToolsHandlerDependencies(
        sync_custom_agents=_sync_custom_agents,
        normalize_agent_id=_normalize_agent_id,
        resolve_agent=_resolve_agent,
        effective_orchestrator_agent_ids=_effective_orchestrator_agent_ids,
        agent_registry=agent_registry,
        state_store=state_store,
    )
)
run_handlers.configure(
    run_handlers.RunHandlerDependencies(
        logger=logger,
        settings=settings,
        runtime_manager=runtime_manager,
        state_store=state_store,
        agent=agent,
        active_run_tasks=control_plane_state.active_run_tasks,
        idempotency_mgr=idempotency_mgr,
        resolve_agent=_resolve_agent,
        effective_orchestrator_agent_ids=_effective_orchestrator_agent_ids,
        build_run_start_fingerprint=_build_run_start_fingerprint,
        extract_also_allow=tools_handlers.extract_also_allow,
    )
)
session_handlers.configure(
    session_handlers.SessionHandlerDependencies(
        runtime_manager=runtime_manager,
        state_store=state_store,
        session_query_service=session_query_service,
        idempotency_mgr=idempotency_mgr,
        build_run_start_fingerprint=_build_run_start_fingerprint,
        build_session_patch_fingerprint=_build_session_patch_fingerprint,
        build_session_reset_fingerprint=_build_session_reset_fingerprint,
        start_run_background=run_handlers.start_run_background,
    )
)
workflow_handlers.configure(
    workflow_handlers.WorkflowHandlerDependencies(
        settings=settings,
        custom_agent_store=custom_agent_store,
        agent_registry=agent_registry,
        idempotency_mgr=idempotency_mgr,
        runtime_manager=runtime_manager,
        subrun_lane=subrun_lane,
        workflow_version_registry=control_plane_state.workflow_version_registry,
        workflow_version_lock=control_plane_state.workflow_version_lock,
        normalize_agent_id=_normalize_agent_id,
        resolve_agent=_resolve_agent,
        sync_custom_agents=_sync_custom_agents,
        effective_orchestrator_agent_ids=_effective_orchestrator_agent_ids,
        start_run_background=run_handlers.start_run_background,
        build_workflow_create_fingerprint=_build_workflow_create_fingerprint,
        build_workflow_execute_fingerprint=_build_workflow_execute_fingerprint,
        build_workflow_delete_fingerprint=_build_workflow_delete_fingerprint,
    )
)
policy_handlers.configure(policy_handlers.PolicyHandlerDependencies(policy_approval_service=policy_approval_service))
skills_handlers.configure(skills_handlers.SkillsHandlerDependencies())
agent_handlers.configure(
    agent_handlers.AgentHandlerDependencies(
        runtime_manager=runtime_manager,
        agent_registry=agent_registry,
        custom_agent_store=custom_agent_store,
        sync_custom_agents=_sync_custom_agents,
        normalize_agent_id=_normalize_agent_id,
        get_agent_tools=tools_handlers.get_agent_tools,
        primary_agent_id=PRIMARY_AGENT_ID,
        coder_agent_id=CODER_AGENT_ID,
        review_agent_id=REVIEW_AGENT_ID,
    )
)
app.include_router(
    build_agents_router(
        agents_list_handler=agent_handlers.api_agents_list,
        presets_list_handler=agent_handlers.api_presets_list,
        custom_agents_list_handler=agent_handlers.api_custom_agents_list,
        custom_agents_create_handler=agent_handlers.api_custom_agents_create,
        custom_agents_update_handler=agent_handlers.api_custom_agents_update,
        custom_agents_delete_handler=agent_handlers.api_custom_agents_delete,
        monitoring_schema_handler=agent_handlers.api_monitoring_schema,
    )
)
_agent_test_dependencies = AgentTestDependencies(
    logger=logger,
    runtime_manager=runtime_manager,
    state_store=state_store,
    agent=agent,
    orchestrator_api=orchestrator_api,
    normalize_preset=normalize_preset,
    extract_also_allow=tools_handlers.extract_also_allow,
    effective_orchestrator_agent_ids=_effective_orchestrator_agent_ids,
    mark_completed=run_handlers.state_mark_completed_safe,
    mark_failed=run_handlers.state_mark_failed_safe,
    primary_agent_id=PRIMARY_AGENT_ID,
)
_run_endpoint_dependencies = RunEndpointsDependencies(
    start_run_background=run_handlers.start_run_background,
    wait_for_run_result=run_handlers.wait_for_run_result,
)
_runtime_debug_dependencies = RuntimeDebugDependencies(
    runtime_manager=runtime_manager,
    settings=settings,
    resolved_prompt_settings=resolved_prompt_settings,
    model_health_tracker=getattr(_get_runtime_components(), "model_health_tracker", None),
)
_subrun_endpoint_dependencies = SubrunEndpointsDependencies(
    subrun_lane=subrun_lane,
    session_visibility_default=settings.session_visibility_default,
    state_append_event_safe=run_handlers.state_append_event_safe,
)
app.include_router(
    build_run_api_router(
        handlers=RunApiRouterHandlers(
            agent_test_handler=lambda request_data: run_agent_test(
                request=AgentTestRequest.model_validate(request_data),
                deps=_agent_test_dependencies,
            ),
            start_run_handler=lambda request_data: run_endpoint_start(
                request=RunStartRequest.model_validate(request_data),
                deps=_run_endpoint_dependencies,
            ),
            wait_run_handler=lambda run_id, timeout_ms, poll_interval_ms: run_endpoint_wait(
                run_id=run_id,
                timeout_ms=timeout_ms,
                poll_interval_ms=poll_interval_ms,
                deps=_run_endpoint_dependencies,
            ),
        )
    )
)
include_control_routers(
    app,
    run_start_handler=run_handlers.api_control_run_start,
    run_wait_handler=run_handlers.api_control_run_wait,
    agent_run_handler=run_handlers.api_control_agent_run,
    agent_wait_handler=run_handlers.api_control_agent_wait,
    runs_get_handler=run_handlers.api_control_runs_get,
    runs_list_handler=run_handlers.api_control_runs_list,
    runs_events_handler=run_handlers.api_control_runs_events,
    runs_audit_handler=run_handlers.api_control_runs_audit,
    policy_approvals_pending_handler=policy_handlers.api_control_policy_approvals_pending,
    policy_approvals_allow_handler=policy_handlers.api_control_policy_approvals_allow,
    policy_approvals_decide_handler=policy_handlers.api_control_policy_approvals_decide,
    sessions_list_handler=session_handlers.api_control_sessions_list,
    sessions_resolve_handler=session_handlers.api_control_sessions_resolve,
    sessions_history_handler=session_handlers.api_control_sessions_history,
    sessions_send_handler=session_handlers.api_control_sessions_send,
    sessions_spawn_handler=session_handlers.api_control_sessions_spawn,
    sessions_status_handler=session_handlers.api_control_sessions_status,
    sessions_get_handler=session_handlers.api_control_sessions_get,
    sessions_patch_handler=session_handlers.api_control_sessions_patch,
    sessions_reset_handler=session_handlers.api_control_sessions_reset,
    workflows_list_handler=workflow_handlers.api_control_workflows_list,
    workflows_get_handler=workflow_handlers.api_control_workflows_get,
    workflows_create_handler=workflow_handlers.api_control_workflows_create,
    workflows_update_handler=workflow_handlers.api_control_workflows_update,
    workflows_execute_handler=workflow_handlers.api_control_workflows_execute,
    workflows_delete_handler=workflow_handlers.api_control_workflows_delete,
    tools_catalog_handler=tools_handlers.api_control_tools_catalog,
    tools_profile_handler=tools_handlers.api_control_tools_profile,
    tools_policy_matrix_handler=tools_handlers.api_control_tools_policy_matrix,
    tools_policy_preview_handler=tools_handlers.api_control_tools_policy_preview,
    skills_list_handler=skills_handlers.api_control_skills_list,
    skills_preview_handler=skills_handlers.api_control_skills_preview,
    skills_check_handler=skills_handlers.api_control_skills_check,
    skills_sync_handler=skills_handlers.api_control_skills_sync,
    context_list_handler=tools_handlers.api_control_context_list,
    context_detail_handler=tools_handlers.api_control_context_detail,
    config_health_handler=tools_handlers.api_control_config_health,
    memory_overview_handler=tools_handlers.api_control_memory_overview,
)
app.include_router(
    build_runtime_debug_router(
        runtime_status_handler=lambda: api_runtime_status(_runtime_debug_dependencies),
        runtime_features_handler=lambda: api_runtime_features(_runtime_debug_dependencies),
        runtime_update_features_handler=lambda payload: api_runtime_update_features(
            _runtime_debug_dependencies, payload
        ),
        resolved_prompts_handler=lambda: api_resolved_prompt_settings(_runtime_debug_dependencies),
        ping_handler=lambda: api_test_ping(_runtime_debug_dependencies),
        calibration_recommendations_handler=lambda: api_calibration_recommendations(_runtime_debug_dependencies),
        tool_telemetry_handler=lambda: api_tool_telemetry_stats(_get_tool_telemetry()),
    )
)
app.include_router(
    build_subruns_router(
        subruns_list_handler=lambda parent_session_id, parent_request_id, requester_session_id, visibility_scope, limit: (
            api_subruns_list(
                parent_session_id=parent_session_id,
                parent_request_id=parent_request_id,
                requester_session_id=requester_session_id,
                visibility_scope=visibility_scope,
                limit=limit,
                deps=_subrun_endpoint_dependencies,
            )
        ),
        subrun_get_handler=lambda run_id, requester_session_id, visibility_scope: api_subruns_get(
            run_id=run_id,
            requester_session_id=requester_session_id,
            visibility_scope=visibility_scope,
            deps=_subrun_endpoint_dependencies,
        ),
        subrun_log_handler=lambda run_id, requester_session_id, visibility_scope: api_subruns_log(
            run_id=run_id,
            requester_session_id=requester_session_id,
            visibility_scope=visibility_scope,
            deps=_subrun_endpoint_dependencies,
        ),
        subrun_kill_handler=lambda run_id, requester_session_id, visibility_scope, cascade: api_subruns_kill(
            run_id=run_id,
            requester_session_id=requester_session_id,
            visibility_scope=visibility_scope,
            cascade=cascade,
            deps=_subrun_endpoint_dependencies,
        ),
        subrun_kill_all_handler=lambda request_data: api_subruns_kill_all_async(
            request_data, _subrun_endpoint_dependencies
        ),
    )
)
ws_handler_dependencies = WsHandlerDependencies(
    logger=logger,
    settings=settings,
    agent=agent,
    agent_registry=agent_registry,
    runtime_manager=runtime_manager,
    policy_approval_service=policy_approval_service,
    state_store=state_store,
    subrun_lane=subrun_lane,
    sync_custom_agents=_sync_custom_agents,
    normalize_agent_id=_normalize_agent_id,
    effective_orchestrator_agent_ids=_effective_orchestrator_agent_ids,
    looks_like_review_request=_looks_like_review_request,
    looks_like_coding_request=looks_like_coding_request,
    route_agent_for_message=_route_agent_for_message,
    resolve_agent=_resolve_agent,
    state_append_event_safe=run_handlers.state_append_event_safe,
    state_mark_failed_safe=run_handlers.state_mark_failed_safe,
    state_mark_completed_safe=run_handlers.state_mark_completed_safe,
    lifecycle_status_from_stage=run_handlers.lifecycle_status_from_stage,
    primary_agent_id=PRIMARY_AGENT_ID,
    coder_agent_id=CODER_AGENT_ID,
    review_agent_id=REVIEW_AGENT_ID,
    repl_session_manager=LazyObjectProxy(lambda: _repl_session_manager),
    browser_pool=LazyObjectProxy(lambda: _browser_pool),
)
app.include_router(build_ws_agent_router(dependencies=ws_handler_dependencies))

# --- Policy CRUD ---
_policy_store = PolicyStore(persist_dir=settings.policies_dir)
app.include_router(build_policies_router(policy_store=_policy_store))
