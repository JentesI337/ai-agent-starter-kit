from __future__ import annotations

from pydantic import BaseModel, Field

from app.tool_policy import ToolPolicyPayload

PRIMARY_AGENT_ID = "head-agent"


class AgentTestRequest(BaseModel):
    message: str = "hi"
    model: str | None = None
    preset: str | None = None
    queue_mode: str | None = None
    prompt_mode: str | None = None
    tool_policy: ToolPolicyPayload | None = None


class RunStartRequest(BaseModel):
    message: str
    session_id: str | None = None
    model: str | None = None
    preset: str | None = None
    queue_mode: str | None = None
    prompt_mode: str | None = None
    tool_policy: ToolPolicyPayload | None = None


class ControlRunStartRequest(BaseModel):
    message: str
    session_id: str | None = None
    model: str | None = None
    preset: str | None = None
    queue_mode: str | None = None
    prompt_mode: str | None = None
    tool_policy: ToolPolicyPayload | None = None
    idempotency_key: str | None = None


class ControlRunWaitRequest(BaseModel):
    run_id: str
    timeout_ms: int | None = None
    poll_interval_ms: int | None = None


class ControlSessionsListRequest(BaseModel):
    limit: int = 100
    active_only: bool = False


class ControlSessionsResolveRequest(BaseModel):
    session_id: str
    active_only: bool = False


class ControlSessionsHistoryRequest(BaseModel):
    session_id: str
    limit: int = 50


class ControlSessionsSendRequest(BaseModel):
    session_id: str
    message: str
    model: str | None = None
    preset: str | None = None
    queue_mode: str | None = None
    prompt_mode: str | None = None
    tool_policy: ToolPolicyPayload | None = None
    idempotency_key: str | None = None


class ControlSessionsSpawnRequest(BaseModel):
    parent_session_id: str
    message: str
    model: str | None = None
    preset: str | None = None
    queue_mode: str | None = None
    prompt_mode: str | None = None
    tool_policy: ToolPolicyPayload | None = None
    idempotency_key: str | None = None


class ControlSessionsStatusRequest(BaseModel):
    session_id: str


class ControlSessionsGetRequest(BaseModel):
    session_id: str


class ControlSessionsPatchRequest(BaseModel):
    session_id: str
    meta: dict[str, object] = Field(default_factory=dict)
    idempotency_key: str | None = None


class ControlSessionsResetRequest(BaseModel):
    session_id: str
    idempotency_key: str | None = None


class ControlToolsCatalogRequest(BaseModel):
    agent_id: str | None = None


class ControlToolsProfileRequest(BaseModel):
    profile_id: str | None = None


class ControlToolsPolicyMatrixRequest(BaseModel):
    agent_id: str | None = None


class ControlSkillsListRequest(BaseModel):
    skills_dir: str | None = None
    max_discovered: int | None = None


class ControlSkillsPreviewRequest(BaseModel):
    skills_dir: str | None = None
    max_discovered: int | None = None
    max_prompt_chars: int | None = None


class ControlSkillsCheckRequest(BaseModel):
    skills_dir: str | None = None
    max_discovered: int | None = None


class ControlSkillsSyncRequest(BaseModel):
    source_skills_dir: str | None = None
    target_skills_dir: str | None = None
    max_discovered: int | None = None
    max_sync_items: int = 200
    apply: bool = False
    clean_target: bool = False
    confirm_clean_target: bool = False


class ControlWorkflowsListRequest(BaseModel):
    limit: int = 100
    base_agent_id: str | None = None


class ControlWorkflowsGetRequest(BaseModel):
    workflow_id: str


class ControlWorkflowsCreateRequest(BaseModel):
    id: str | None = None
    name: str
    description: str = ""
    base_agent_id: str = PRIMARY_AGENT_ID
    steps: list[str] = Field(default_factory=list)
    tool_policy: ToolPolicyPayload | None = None
    allow_subrun_delegation: bool = False
    idempotency_key: str | None = None


class ControlWorkflowsUpdateRequest(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None
    base_agent_id: str | None = None
    steps: list[str] | None = None
    tool_policy: ToolPolicyPayload | None = None
    allow_subrun_delegation: bool | None = None
    idempotency_key: str | None = None


class ControlWorkflowsExecuteRequest(BaseModel):
    workflow_id: str
    message: str
    session_id: str | None = None
    model: str | None = None
    preset: str | None = None
    queue_mode: str | None = None
    prompt_mode: str | None = None
    tool_policy: ToolPolicyPayload | None = None
    idempotency_key: str | None = None


class ControlWorkflowsDeleteRequest(BaseModel):
    workflow_id: str
    idempotency_key: str | None = None


class ControlRunsGetRequest(BaseModel):
    run_id: str


class ControlRunsListRequest(BaseModel):
    limit: int = 100
    session_id: str | None = None


class ControlRunsEventsRequest(BaseModel):
    run_id: str
    limit: int = 200


class ControlRunsAuditRequest(BaseModel):
    run_id: str


class ControlToolsPolicyPreviewRequest(BaseModel):
    agent_id: str | None = None
    profile: str | None = None
    preset: str | None = None
    provider: str | None = None
    model: str | None = None
    tool_policy: ToolPolicyPayload | None = None
    also_allow: list[str] | None = None


class ControlContextListRequest(BaseModel):
    session_id: str | None = None
    limit: int = 50


class ControlContextDetailRequest(BaseModel):
    run_id: str


class ControlConfigHealthRequest(BaseModel):
    include_effective_values: bool = False


class ControlMemoryOverviewRequest(BaseModel):
    session_id: str | None = None
    limit_sessions: int = 200
    limit_entries_per_session: int = 500
    include_content: bool = True
    search_query: str | None = None


class ControlPolicyApprovalsPendingRequest(BaseModel):
    run_id: str | None = None
    session_id: str | None = None
    limit: int = 100


class ControlPolicyApprovalsAllowRequest(BaseModel):
    approval_id: str


class ControlPolicyApprovalsDecideRequest(BaseModel):
    approval_id: str
    decision: str
    scope: str | None = None
