"""Handler .configure() calls — wires dependencies into handler modules.

Extracted from main.py (Phase 16).  Called once at application startup
after runtime_wiring has been imported.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.app_state import LazyObjectProxy
from app.config import settings
from app.transport.routers import agents as agent_handlers
from app.transport.routers import policies as policy_handlers
from app.transport.routers import runs as run_handlers
from app.transport.routers import sessions as session_handlers
from app.transport.routers import skills as skills_handlers
from app.transport.routers import tools as tools_handlers
from app.workflows import handlers as workflow_handlers
from app.agent.factory_defaults import CODER_AGENT_ID, PRIMARY_AGENT_ID, REVIEW_AGENT_ID
from app.shared.control_fingerprints import (
    build_run_start_fingerprint as _build_run_start_fingerprint,
    build_session_patch_fingerprint as _build_session_patch_fingerprint,
    build_session_reset_fingerprint as _build_session_reset_fingerprint,
    build_workflow_create_fingerprint as _build_workflow_create_fingerprint,
    build_workflow_delete_fingerprint as _build_workflow_delete_fingerprint,
    build_workflow_execute_fingerprint as _build_workflow_execute_fingerprint,
)
from app.transport.runtime_wiring import (
    _effective_orchestrator_agent_ids,
    _normalize_agent_id,
    _resolve_agent,
    _sync_custom_agents,
    agent,
    agent_registry,
    agent_store,
    control_plane_state,
    custom_agent_store,
    idempotency_mgr,
    orchestrator_registry,
    policy_approval_service,
    runtime_manager,
    session_query_service,
    state_store,
)

logger = logging.getLogger("app.main")


def _get_workflow_store_lazy():
    from app.workflows.store import get_workflow_store, init_workflow_sqlite_stores, _wf_store as _wfs_instance
    if _wfs_instance is None:
        _workflow_db_path = Path(settings.workspace_root) / "workflow_store.sqlite3"
        init_workflow_sqlite_stores(db_path=_workflow_db_path)
    return get_workflow_store()


def _get_workflow_audit_store_lazy():
    from app.workflows.store import get_workflow_audit_store, init_workflow_sqlite_stores, _audit_store as _as_instance
    if _as_instance is None:
        _workflow_db_path = Path(settings.workspace_root) / "workflow_store.sqlite3"
        init_workflow_sqlite_stores(db_path=_workflow_db_path)
    return get_workflow_audit_store()


async def _workflow_run_agent(agent_id: str, message: str, session_id: str) -> str:
    """RunAgentFn callback — bridges workflow engine to agent domain."""
    import uuid as _uuid
    _, _, orch_api = _resolve_agent(agent_id)
    from app.contracts.request_context import RequestContext
    rc = RequestContext(
        session_id=session_id,
        request_id=f"wf-{_uuid.uuid4()}",
        runtime=runtime_manager.get_state().runtime,
        model=runtime_manager.get_state().model,
    )
    return await orch_api.run_user_message(
        user_message=message, send_event=lambda e: None, request_context=rc)


def configure_all_handlers() -> None:
    """Wire dependencies into all handler modules (except integration_handlers,
    which is configured inside _startup_sequence)."""
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
        workflow_handlers.WorkflowDependencies(
            settings=settings,
            workflow_store=LazyObjectProxy(_get_workflow_store_lazy),
            audit_store=LazyObjectProxy(_get_workflow_audit_store_lazy),
            idempotency_mgr=idempotency_mgr,
            run_agent=_workflow_run_agent,
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
            agent_store=agent_store,
        )
    )
