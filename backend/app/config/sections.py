"""Configuration sections — logically grouped Pydantic models for all Settings fields.

Each section groups related settings. The ``SECTION_REGISTRY`` maps section keys
to their model class so the ``ConfigService`` can iterate dynamically.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class CoreSection(BaseModel):
    app_env: str = "development"
    debug_mode: bool = False
    log_level: str = "INFO"
    workspace_root: str = ""
    max_user_message_length: int = 8000
    queue_mode_default: str = "wait"
    prompt_mode_default: str = "full"
    session_visibility_default: str = "tree"
    reasoning_level_default: str = "medium"
    reasoning_visibility_default: str = "off"
    structured_planning_enabled: bool = False
    plan_max_steps: int = 7
    plan_root_cause_replan_enabled: bool = True
    plan_coverage_warn_threshold: float = 0.15
    plan_coverage_fail_threshold: float = 0.0
    prompt_section_limit_minimal: int = 2000
    prompt_section_limit_subagent: int = 900
    dynamic_temperature_reasoning_delta: float = 0.05
    failure_context_enabled: bool = False
    run_state_violation_hard_fail_enabled: bool = False
    config_strict_unknown_keys_enabled: bool = False
    config_strict_unknown_keys_allowlist: list[str] = Field(default_factory=list)
    adaptive_inference_enabled: bool = True
    adaptive_inference_cost_budget_max: float = 0.9
    adaptive_inference_latency_budget_ms: int = 2400
    context_window_guard_enabled: bool = True
    context_window_warn_below_tokens: int = 12000
    context_window_hard_min_tokens: int = 4000
    workflows_audit_enabled: bool = False


class LlmSection(BaseModel):
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "llama3.3:70b-instruct-q4_K_M"
    llm_api_key: str = ""
    local_model: str = "llama3.3:70b-instruct-q4_K_M"
    api_model: str = "minimax-m2:cloud"
    api_base_url: str = "http://localhost:11434/api"
    api_supported_models: list[str] = Field(
        default_factory=lambda: ["minimax-m2:cloud", "gpt-oss:20b-cloud", "qwen3-coder:480b-cloud"]
    )
    ollama_bin: str = ""
    runtime_state_file: str = ""


class AgentNamesSection(BaseModel):
    agent_name: str = "head-agent"
    coder_agent_name: str = "coder-agent"
    review_agent_name: str = "review-agent"
    researcher_agent_name: str = "researcher-agent"
    architect_agent_name: str = "architect-agent"
    test_agent_name: str = "test-agent"
    security_agent_name: str = "security-agent"
    doc_agent_name: str = "doc-agent"
    refactor_agent_name: str = "refactor-agent"
    devops_agent_name: str = "devops-agent"
    fintech_agent_name: str = "fintech-agent"
    healthtech_agent_name: str = "healthtech-agent"
    legaltech_agent_name: str = "legaltech-agent"
    ecommerce_agent_name: str = "ecommerce-agent"
    industrytech_agent_name: str = "industrytech-agent"


class PromptsSection(BaseModel):
    head_agent_system_prompt: str = ""
    head_agent_tool_selector_prompt: str = ""
    head_agent_tool_repair_prompt: str = ""
    head_agent_final_prompt: str = ""
    coder_agent_system_prompt: str = ""
    coder_agent_tool_selector_prompt: str = ""
    coder_agent_tool_repair_prompt: str = ""
    coder_agent_final_prompt: str = ""
    agent_system_prompt: str = ""
    agent_tool_selector_prompt: str = ""
    agent_tool_repair_prompt: str = ""
    agent_final_prompt: str = ""
    researcher_agent_system_prompt: str = ""
    researcher_agent_tool_selector_prompt: str = ""
    researcher_agent_tool_repair_prompt: str = ""
    researcher_agent_final_prompt: str = ""
    architect_agent_system_prompt: str = ""
    architect_agent_tool_selector_prompt: str = ""
    architect_agent_tool_repair_prompt: str = ""
    architect_agent_final_prompt: str = ""
    test_agent_system_prompt: str = ""
    test_agent_tool_selector_prompt: str = ""
    test_agent_tool_repair_prompt: str = ""
    test_agent_final_prompt: str = ""
    security_agent_system_prompt: str = ""
    security_agent_tool_selector_prompt: str = ""
    security_agent_tool_repair_prompt: str = ""
    security_agent_final_prompt: str = ""
    doc_agent_system_prompt: str = ""
    doc_agent_tool_selector_prompt: str = ""
    doc_agent_tool_repair_prompt: str = ""
    doc_agent_final_prompt: str = ""
    refactor_agent_system_prompt: str = ""
    refactor_agent_tool_selector_prompt: str = ""
    refactor_agent_tool_repair_prompt: str = ""
    refactor_agent_final_prompt: str = ""
    devops_agent_system_prompt: str = ""
    devops_agent_tool_selector_prompt: str = ""
    devops_agent_tool_repair_prompt: str = ""
    devops_agent_final_prompt: str = ""
    fintech_agent_system_prompt: str = ""
    fintech_agent_tool_selector_prompt: str = ""
    fintech_agent_tool_repair_prompt: str = ""
    fintech_agent_final_prompt: str = ""
    healthtech_agent_system_prompt: str = ""
    healthtech_agent_tool_selector_prompt: str = ""
    healthtech_agent_tool_repair_prompt: str = ""
    healthtech_agent_final_prompt: str = ""
    legaltech_agent_system_prompt: str = ""
    legaltech_agent_tool_selector_prompt: str = ""
    legaltech_agent_tool_repair_prompt: str = ""
    legaltech_agent_final_prompt: str = ""
    ecommerce_agent_system_prompt: str = ""
    ecommerce_agent_tool_selector_prompt: str = ""
    ecommerce_agent_tool_repair_prompt: str = ""
    ecommerce_agent_final_prompt: str = ""
    industrytech_agent_system_prompt: str = ""
    industrytech_agent_tool_selector_prompt: str = ""
    industrytech_agent_tool_repair_prompt: str = ""
    industrytech_agent_final_prompt: str = ""


class MemorySection(BaseModel):
    memory_max_items: int = 30
    memory_persist_dir: str = ""
    memory_reset_on_startup: bool = True
    long_term_memory_enabled: bool = True
    long_term_memory_db_path: str = ""


class SessionSection(BaseModel):
    session_inbox_max_queue_length: int = 100
    session_inbox_ttl_seconds: int = 600
    session_follow_up_max_deferrals: int = 2
    session_distillation_enabled: bool = True
    session_lane_global_max_concurrent: int = 8


class ToolExecutionSection(BaseModel):
    run_tool_call_cap: int = 8
    run_tool_time_cap_seconds: float = 90.0
    tool_result_max_chars: int = 6000
    tool_result_smart_truncate_enabled: bool = True
    tool_result_context_guard_enabled: bool = True
    tool_result_context_headroom_ratio: float = 0.75
    tool_result_single_share: float = 0.50
    tool_execution_parallel_read_only_enabled: bool = False
    tool_selection_function_calling_enabled: bool = True
    command_timeout_seconds: int = 300
    agent_tools_allow: list[str] | None = None
    agent_tools_deny: list[str] = Field(default_factory=list)
    run_direct_answer_skip_enabled: bool = True
    run_direct_answer_max_chars: int = 500
    run_max_replan_iterations: int = 1
    run_empty_tool_replan_max_attempts: int = 1
    run_error_tool_replan_max_attempts: int = 3


class SecuritySection(BaseModel):
    command_allowlist_enabled: bool = True
    command_allowlist: list[str] = Field(default_factory=list)
    command_allowlist_extra: list[str] = Field(default_factory=list)
    ws_allowed_origins: list[str] = Field(default_factory=list)
    cors_allow_origins: list[str] = Field(default_factory=list)
    cors_allow_credentials: bool = True
    api_auth_required: bool = False
    api_auth_token: str = ""
    policy_require_signature: bool = False
    persist_transform_max_string_chars: int = 8000
    persist_transform_redact_secrets: bool = True


class PipelineSection(BaseModel):
    pipeline_runner_max_attempts: int = 16
    pipeline_runner_context_overflow_fallback_retry_enabled: bool = False
    pipeline_runner_context_overflow_fallback_retry_max_attempts: int = 1
    pipeline_runner_compaction_failure_recovery_enabled: bool = False
    pipeline_runner_compaction_failure_recovery_max_attempts: int = 1
    pipeline_runner_truncation_recovery_enabled: bool = False
    pipeline_runner_truncation_recovery_max_attempts: int = 1
    pipeline_runner_prompt_compaction_enabled: bool = False
    pipeline_runner_prompt_compaction_max_attempts: int = 3
    pipeline_runner_prompt_compaction_ratio: float = 0.7
    pipeline_runner_prompt_compaction_min_chars: int = 200
    pipeline_runner_payload_truncation_enabled: bool = False
    pipeline_runner_payload_truncation_max_attempts: int = 1
    pipeline_runner_payload_truncation_target_chars: int = 1200
    pipeline_runner_payload_truncation_min_chars: int = 120
    pipeline_runner_context_overflow_priority_local: list[str] = Field(
        default_factory=lambda: ["prompt_compaction", "overflow_fallback_retry"]
    )
    pipeline_runner_context_overflow_priority_api: list[str] = Field(
        default_factory=lambda: ["overflow_fallback_retry", "prompt_compaction"]
    )
    pipeline_runner_truncation_priority_local: list[str] = Field(
        default_factory=lambda: ["payload_truncation", "truncation_fallback_retry"]
    )
    pipeline_runner_truncation_priority_api: list[str] = Field(
        default_factory=lambda: ["truncation_fallback_retry", "payload_truncation"]
    )
    pipeline_runner_recovery_priority_flip_enabled: bool = True
    pipeline_runner_recovery_priority_flip_threshold: int = 2
    pipeline_runner_signal_priority_enabled: bool = True
    pipeline_runner_signal_low_health_threshold: float = 0.55
    pipeline_runner_signal_high_latency_ms: int = 2500
    pipeline_runner_signal_high_cost_threshold: float = 0.75
    pipeline_runner_strategy_feedback_enabled: bool = True
    pipeline_runner_persistent_priority_enabled: bool = True
    pipeline_runner_persistent_priority_min_samples: int = 3
    pipeline_runner_recovery_backoff_enabled: bool = True
    pipeline_runner_recovery_backoff_base_ms: int = 500
    pipeline_runner_recovery_backoff_max_ms: int = 5000
    pipeline_runner_recovery_backoff_multiplier: float = 2.0
    pipeline_runner_recovery_backoff_jitter: bool = True
    pipeline_runner_persistent_priority_decay_enabled: bool = True
    pipeline_runner_persistent_priority_decay_half_life_seconds: int = 86400
    pipeline_runner_persistent_priority_window_size: int = 50
    pipeline_runner_persistent_priority_window_max_age_seconds: int = 604800


class ReflectionSection(BaseModel):
    reflection_enabled: bool = True
    reflection_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    reflection_factual_grounding_hard_min: float = Field(default=0.4, ge=0.0, le=1.0)
    reflection_tool_results_max_chars: int = Field(default=8000, ge=500)
    reflection_plan_max_chars: int = Field(default=2000, ge=200)
    dynamic_temperature_enabled: bool = False
    dynamic_temperature_overrides: dict[str, float] = Field(default_factory=dict)
    prompt_ab_enabled: bool = False
    prompt_ab_registry_path: str = ""
    failure_journal_enabled: bool = True


class SubrunSection(BaseModel):
    subrun_max_concurrent: int = 2
    subrun_timeout_seconds: int = 900
    subrun_max_spawn_depth: int = 2
    subrun_max_children_per_parent: int = 5
    subrun_leaf_spawn_depth_guard_enabled: bool = False
    subrun_orchestrator_agent_ids: list[str] = Field(default_factory=lambda: ["head-agent"])
    subrun_announce_retry_max_attempts: int = 5
    subrun_announce_retry_base_delay_ms: int = 500
    subrun_announce_retry_max_delay_ms: int = 10000
    subrun_announce_retry_jitter: bool = True
    subrun_restore_orphan_reconcile_enabled: bool = True
    subrun_restore_orphan_grace_seconds: int = 0
    subrun_lifecycle_delivery_error_grace_enabled: bool = True
    agent_isolation_enabled: bool = True
    agent_isolation_allowed_scope_pairs: list[str] = Field(default_factory=list)
    multi_agency_enabled: bool = False


class BrowserSection(BaseModel):
    browser_enabled: bool = True
    browser_max_contexts: int = 5
    browser_navigation_timeout_ms: int = 30000
    browser_context_ttl_seconds: int = 300
    browser_max_page_text_chars: int = 5000


class ReplSection(BaseModel):
    repl_enabled: bool = True
    repl_timeout_seconds: int = 60
    repl_max_memory_mb: int = 512
    repl_max_sessions: int = 10
    repl_max_output_chars: int = 10000
    repl_sandbox_dir: str = ""


class MultimodalSection(BaseModel):
    multimodal_tools_enabled: bool = True
    multimodal_pdf_enabled: bool = True
    multimodal_audio_enabled: bool = True
    multimodal_audio_provider: str = Field(default="local", json_schema_extra={"choices": ["local", "openai"]})
    multimodal_audio_model: str = "base"
    multimodal_audio_base_url: str = ""
    multimodal_audio_api_key: str = ""
    multimodal_audio_max_duration_seconds: int = 600
    multimodal_image_gen_enabled: bool = True
    multimodal_image_gen_provider: str = Field(default="sd-webui", json_schema_extra={"choices": ["sd-webui", "openai", "stabilityai"]})
    multimodal_image_gen_model: str = ""
    multimodal_image_gen_base_url: str = "http://localhost:7860"
    multimodal_image_gen_api_key: str = ""
    multimodal_image_gen_default_size: str = "1024x1024"
    multimodal_tts_enabled: bool = True
    multimodal_tts_provider: str = Field(default="openai", json_schema_extra={"choices": ["openai", "local"]})
    multimodal_tts_model: str = "tts-1"
    multimodal_tts_voice: str = Field(default="alloy", json_schema_extra={"choices": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]})
    multimodal_tts_base_url: str = "https://api.openai.com/v1"
    multimodal_tts_api_key: str = ""
    multimodal_upload_max_bytes: int = 20 * 1024 * 1024


class VisionWebSection(BaseModel):
    vision_enabled: bool = False
    vision_provider: str = Field(default="ollama", json_schema_extra={"choices": ["ollama", "openai", "gemini", "auto"]})
    vision_model: str = "llava:13b"
    vision_base_url: str = "http://localhost:11434"
    vision_api_key: str = ""
    vision_max_tokens: int = 1000
    web_search_provider: str = Field(default="searxng", json_schema_extra={"choices": ["searxng", "duckduckgo", "tavily", "brave"]})
    web_search_api_key: str = ""
    web_search_base_url: str = "http://localhost:8888"
    web_search_max_results: int = 5
    web_fetch_max_download_bytes: int = 5 * 1024 * 1024
    web_fetch_blocked_content_types: list[str] = Field(
        default_factory=lambda: [
            "application/octet-stream",
            "application/x-executable",
            "application/x-sharedlib",
            "application/zip",
            "application/gzip",
            "application/x-tar",
        ]
    )
    mcp_enabled: bool = False
    mcp_servers_config: str = ""


class ToolLoopSection(BaseModel):
    tool_loop_warn_threshold: int = 2
    tool_loop_critical_threshold: int = 3
    tool_loop_circuit_breaker_threshold: int = 6
    tool_loop_detector_generic_repeat_enabled: bool = True
    tool_loop_detector_ping_pong_enabled: bool = True
    tool_loop_detector_poll_no_progress_enabled: bool = True
    tool_loop_poll_no_progress_threshold: int = 3
    tool_loop_warning_bucket_size: int = 10


class RunnerSection(BaseModel):
    runner_max_iterations: int = 25
    runner_max_tool_calls: int = 50
    runner_time_budget_seconds: int = 300
    runner_context_budget: int = 4096
    runner_loop_detection_enabled: bool = True
    runner_loop_detection_threshold: int = 3
    runner_compaction_enabled: bool = True
    runner_compaction_tail_keep: int = 4
    runner_compaction_context_window: int = 200000
    runner_tool_result_max_chars: int = 5000
    runner_reflection_enabled: bool = True
    runner_reflection_max_passes: int = 1


class SkillsSection(BaseModel):
    skills_engine_enabled: bool = False
    skills_canary_enabled: bool = False
    skills_canary_agent_ids: list[str] = Field(default_factory=lambda: ["head-agent"])
    skills_canary_model_profiles: list[str] = Field(default_factory=lambda: ["*"])
    skills_mandatory_selection: bool = False
    skills_max_discovered: int = 150
    skills_max_prompt_chars: int = 30000
    skills_snapshot_cache_ttl_seconds: float = 15.0
    skills_snapshot_cache_use_mtime: bool = True
    skills_dir: str = ""


class IntegrationsSection(BaseModel):
    api_connectors_enabled: bool = False


class InfraSection(BaseModel):
    orchestrator_state_dir: str = ""
    orchestrator_state_backend: str = "file"
    orchestrator_state_reset_on_startup: bool = True
    custom_agents_dir: str = ""
    policies_dir: str = ""
    policy_approval_wait_seconds: float = 30.0
    run_wait_default_timeout_ms: int = 30000
    run_wait_poll_interval_ms: int = 200
    hook_contract_version: str = "hook-contract.v2"
    hook_timeout_ms_default: int = 1500
    hook_timeout_ms_overrides: dict[str, int] = Field(default_factory=dict)
    hook_failure_policy_default: str = "soft_fail"
    hook_failure_policy_overrides: dict[str, str] = Field(default_factory=dict)
    idempotency_registry_ttl_seconds: int = 86400
    idempotency_registry_max_entries: int = 5000
    reliable_retrieval_enabled: bool = True
    reliable_retrieval_max_sources: int = 4
    reliable_retrieval_min_score: float = 0.02
    reliable_retrieval_cache_ttl_seconds: float = 30.0
    reliable_retrieval_default_source_trust: float = 0.8


class ModelHealthSection(BaseModel):
    model_health_tracker_enabled: bool = False
    model_health_tracker_ring_buffer_size: int = 50
    model_health_tracker_min_samples: int = 10
    model_health_tracker_stale_after_seconds: int = 300
    circuit_breaker_enabled: bool = False
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_failure_window_seconds: int = 60
    circuit_breaker_recovery_timeout_seconds: int = 120
    circuit_breaker_success_threshold: int = 2
    model_score_weight_health: float = 100.0
    model_score_weight_latency: float = 0.01
    model_score_weight_cost: float = 10.0
    model_score_runtime_bonus: float = 6.0


# ---------------------------------------------------------------------------
# Section registry — maps section keys to model classes
# ---------------------------------------------------------------------------

SECTION_REGISTRY: dict[str, type[BaseModel]] = {
    "core": CoreSection,
    "llm": LlmSection,
    "agent_names": AgentNamesSection,
    "prompts": PromptsSection,
    "memory": MemorySection,
    "session": SessionSection,
    "tool_execution": ToolExecutionSection,
    "security": SecuritySection,
    "pipeline": PipelineSection,
    "reflection": ReflectionSection,
    "subrun": SubrunSection,
    "browser": BrowserSection,
    "repl": ReplSection,
    "multimodal": MultimodalSection,
    "vision_web": VisionWebSection,
    "tool_loop": ToolLoopSection,
    "runner": RunnerSection,
    "skills": SkillsSection,
    "integrations": IntegrationsSection,
    "infra": InfraSection,
    "model_health": ModelHealthSection,
}

# ---------------------------------------------------------------------------
# Mapping: field name -> section key  (built once at import time)
# ---------------------------------------------------------------------------

_FIELD_TO_SECTION: dict[str, str] = {}
for _section_key, _model_cls in SECTION_REGISTRY.items():
    for _field_name in _model_cls.model_fields:
        _FIELD_TO_SECTION[_field_name] = _section_key


def field_to_section(field_name: str) -> str | None:
    """Return the section key that owns *field_name*, or ``None``."""
    return _FIELD_TO_SECTION.get(field_name)


# Sensitive fields that should not be writable via the API
SENSITIVE_FIELDS: frozenset[str] = frozenset({
    "api_auth_token",
    "llm_api_key",
    "vision_api_key",
    "web_search_api_key",
    "multimodal_audio_api_key",
    "multimodal_image_gen_api_key",
    "multimodal_tts_api_key",
})
