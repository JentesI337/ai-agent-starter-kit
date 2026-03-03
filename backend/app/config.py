from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

APP_DIR = os.path.abspath(os.path.dirname(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(APP_DIR, ".."))
DEFAULT_WORKSPACE_ROOT = os.path.abspath(os.path.join(BACKEND_DIR, ".."))


def _parse_csv_env(value: str, fallback: list[str]) -> list[str]:
    entries = [item.strip() for item in (value or "").split(",") if item.strip()]
    return entries or fallback


def _parse_optional_csv_env(value: str | None) -> list[str] | None:
    entries = [item.strip() for item in (value or "").split(",") if item.strip()]
    return entries or None


def _resolve_workspace_root(value: str | None) -> str:
    candidate = (value or "").strip() or DEFAULT_WORKSPACE_ROOT
    if not os.path.isabs(candidate):
        candidate = os.path.abspath(os.path.join(BACKEND_DIR, candidate))
    return os.path.abspath(candidate)


def _resolve_path_from_workspace(path_value: str | None, workspace_root: str, fallback_relative: str) -> str:
    raw_value = (path_value or "").strip() or fallback_relative
    candidate = raw_value if os.path.isabs(raw_value) else os.path.join(workspace_root, raw_value)
    return os.path.abspath(candidate)


def _parse_bool_env(var_name: str, default: bool) -> bool:
    raw = os.getenv(var_name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _default_reset_on_startup(app_env: str) -> bool:
    return app_env != "production"


def _resolve_prompt(default: str, *env_keys: str) -> str:
    for env_key in env_keys:
        value = os.getenv(env_key)
        if value is not None:
            return value
    return default


PROMPT_SETTING_KEYS: tuple[str, ...] = (
    "head_agent_system_prompt",
    "head_agent_plan_prompt",
    "head_agent_tool_selector_prompt",
    "head_agent_tool_repair_prompt",
    "head_agent_final_prompt",
    "coder_agent_system_prompt",
    "coder_agent_plan_prompt",
    "coder_agent_tool_selector_prompt",
    "coder_agent_tool_repair_prompt",
    "coder_agent_final_prompt",
    "agent_system_prompt",
    "agent_plan_prompt",
    "agent_tool_selector_prompt",
    "agent_tool_repair_prompt",
    "agent_final_prompt",
)


class Settings(BaseModel):
    app_env: str = os.getenv("APP_ENV", "development").strip().lower()
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
    llm_model: str = os.getenv("LLM_MODEL", "llama3.3:70b-instruct-q4_K_M")
    agent_name: str = os.getenv("AGENT_NAME", "head-agent")
    coder_agent_name: str = os.getenv("CODER_AGENT_NAME", "coder-agent")
    review_agent_name: str = os.getenv("REVIEW_AGENT_NAME", "review-agent")
    head_agent_system_prompt: str = _resolve_prompt(
        "You are a neutral head agent. Be concise, factual, and adapt naturally to user intent.",
        "HEAD_AGENT_SYSTEM_PROMPT",
        "AGENT_SYSTEM_PROMPT",
    )
    head_agent_plan_prompt: str = _resolve_prompt(
        "You are a neutral head agent. Return a minimal, context-appropriate plan only when needed.",
        "HEAD_AGENT_PLAN_PROMPT",
        "HEAD_AGENT_SYSTEM_PROMPT",
        "AGENT_PLAN_PROMPT",
        "AGENT_SYSTEM_PROMPT",
    )
    head_agent_tool_selector_prompt: str = _resolve_prompt(
        "You select tools for user tasks. Strictly follow output format requirements.",
        "HEAD_AGENT_TOOL_SELECTOR_PROMPT",
        "AGENT_TOOL_SELECTOR_PROMPT",
        "HEAD_AGENT_SYSTEM_PROMPT",
    )
    head_agent_tool_repair_prompt: str = _resolve_prompt(
        "You repair malformed tool selection output into strict JSON only.",
        "HEAD_AGENT_TOOL_REPAIR_PROMPT",
        "AGENT_TOOL_REPAIR_PROMPT",
        "HEAD_AGENT_SYSTEM_PROMPT",
    )
    head_agent_final_prompt: str = _resolve_prompt(
        "You are a neutral head agent. Return a concise, directly helpful final answer.",
        "HEAD_AGENT_FINAL_PROMPT",
        "HEAD_AGENT_SYSTEM_PROMPT",
        "AGENT_FINAL_PROMPT",
        "AGENT_SYSTEM_PROMPT",
    )
    coder_agent_system_prompt: str = _resolve_prompt(
        "You are a senior coding agent. Think step-by-step, break tasks into actionable implementation steps, and produce precise developer output.",
        "CODER_AGENT_SYSTEM_PROMPT",
    )
    coder_agent_plan_prompt: str = _resolve_prompt(
        "You are a senior coding agent. Return a short actionable implementation plan.",
        "CODER_AGENT_PLAN_PROMPT",
        "CODER_AGENT_SYSTEM_PROMPT",
    )
    coder_agent_tool_selector_prompt: str = _resolve_prompt(
        "You select tools for a coding task. Strictly follow output format requirements.",
        "CODER_AGENT_TOOL_SELECTOR_PROMPT",
        "AGENT_TOOL_SELECTOR_PROMPT",
    )
    coder_agent_tool_repair_prompt: str = _resolve_prompt(
        "You repair malformed tool selection output into strict JSON only.",
        "CODER_AGENT_TOOL_REPAIR_PROMPT",
        "AGENT_TOOL_REPAIR_PROMPT",
    )
    coder_agent_final_prompt: str = _resolve_prompt(
        "You are a senior coding agent. Return a concise final answer with practical next steps.",
        "CODER_AGENT_FINAL_PROMPT",
        "CODER_AGENT_SYSTEM_PROMPT",
    )
    agent_system_prompt: str = _resolve_prompt(
        "You are a senior head agent. Think step-by-step and return practical plans.",
        "AGENT_SYSTEM_PROMPT",
    )
    agent_plan_prompt: str = _resolve_prompt(
        "You are a senior head agent. Think step-by-step and return practical plans.",
        "AGENT_PLAN_PROMPT",
        "AGENT_SYSTEM_PROMPT",
    )
    agent_tool_selector_prompt: str = _resolve_prompt(
        "You are a senior head agent. Think step-by-step and return practical plans.",
        "AGENT_TOOL_SELECTOR_PROMPT",
        "AGENT_SYSTEM_PROMPT",
    )
    agent_tool_repair_prompt: str = _resolve_prompt(
        "You are a senior head agent. Think step-by-step and return practical plans.",
        "AGENT_TOOL_REPAIR_PROMPT",
        "AGENT_SYSTEM_PROMPT",
    )
    agent_final_prompt: str = _resolve_prompt(
        "You are a senior head agent. Think step-by-step and return practical plans.",
        "AGENT_FINAL_PROMPT",
        "AGENT_SYSTEM_PROMPT",
    )
    workspace_root: str = _resolve_workspace_root(os.getenv("WORKSPACE_ROOT"))
    memory_max_items: int = int(os.getenv("MEMORY_MAX_ITEMS", "30"))
    memory_persist_dir: str = _resolve_path_from_workspace(
        os.getenv("MEMORY_PERSIST_DIR"),
        workspace_root,
        "memory_store",
    )
    memory_reset_on_startup: bool = _parse_bool_env(
        "MEMORY_RESET_ON_STARTUP",
        _default_reset_on_startup(app_env),
    )
    orchestrator_state_dir: str = _resolve_path_from_workspace(
        os.getenv("ORCHESTRATOR_STATE_DIR"),
        workspace_root,
        "state_store",
    )
    orchestrator_state_backend: str = os.getenv("ORCHESTRATOR_STATE_BACKEND", "file").strip().lower()
    custom_agents_dir: str = _resolve_path_from_workspace(
        os.getenv("CUSTOM_AGENTS_DIR"),
        workspace_root,
        "custom_agents",
    )
    skills_dir: str = _resolve_path_from_workspace(
        os.getenv("SKILLS_DIR"),
        workspace_root,
        "skills",
    )
    skills_engine_enabled: bool = _parse_bool_env("SKILLS_ENGINE_ENABLED", False)
    skills_canary_enabled: bool = _parse_bool_env("SKILLS_CANARY_ENABLED", False)
    skills_canary_agent_ids: list[str] = _parse_csv_env(
        os.getenv("SKILLS_CANARY_AGENT_IDS", "head-agent"),
        ["head-agent"],
    )
    skills_canary_model_profiles: list[str] = _parse_csv_env(
        os.getenv("SKILLS_CANARY_MODEL_PROFILES", "*"),
        ["*"],
    )
    skills_mandatory_selection: bool = _parse_bool_env("SKILLS_MANDATORY_SELECTION", False)
    skills_max_discovered: int = int(os.getenv("SKILLS_MAX_DISCOVERED", "150"))
    skills_max_prompt_chars: int = int(os.getenv("SKILLS_MAX_PROMPT_CHARS", "30000"))
    orchestrator_state_reset_on_startup: bool = _parse_bool_env(
        "ORCHESTRATOR_STATE_RESET_ON_STARTUP",
        _default_reset_on_startup(app_env),
    )
    command_timeout_seconds: int = int(os.getenv("COMMAND_TIMEOUT_SECONDS", "60"))
    web_fetch_max_download_bytes: int = int(os.getenv("WEB_FETCH_MAX_DOWNLOAD_BYTES", str(5 * 1024 * 1024)))
    web_fetch_blocked_content_types: list[str] = _parse_csv_env(
        os.getenv(
            "WEB_FETCH_BLOCKED_CONTENT_TYPES",
            "application/octet-stream,application/x-executable,application/x-sharedlib,application/zip,application/gzip,application/x-tar",
        ),
        [
            "application/octet-stream",
            "application/x-executable",
            "application/x-sharedlib",
            "application/zip",
            "application/gzip",
            "application/x-tar",
        ],
    )
    cors_allow_origins: list[str] = _parse_csv_env(
        os.getenv(
            "CORS_ALLOW_ORIGINS",
            "http://localhost:4200,http://127.0.0.1:4200,http://localhost:5173,http://127.0.0.1:5173",
        ),
        [
            "http://localhost:4200",
            "http://127.0.0.1:4200",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
    )
    cors_allow_credentials: bool = os.getenv(
        "CORS_ALLOW_CREDENTIALS",
        "false" if os.getenv("APP_ENV", "development").strip().lower() == "production" else "true",
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    command_allowlist_enabled: bool = os.getenv("COMMAND_ALLOWLIST_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    command_allowlist: list[str] = _parse_csv_env(
        os.getenv(
            "COMMAND_ALLOWLIST",
            "python,py,pip,pytest,uvicorn,git,npm,node,npx,yarn,pnpm,pwsh,powershell,cmd,bash,sh,make,cmake,docker,docker-compose,java,javac,mvn,gradle,go,rustc,cargo,dotnet,ls,dir,cat,type,echo,findstr,rg,grep,sed,awk,head,tail,wc,sort,uniq,cp,mv,mkdir,touch,chmod,chown,tar,zip,unzip",
        ),
        [
            "python",
            "py",
            "pip",
            "pytest",
            "uvicorn",
            "git",
            "npm",
            "node",
            "npx",
            "yarn",
            "pnpm",
            "pwsh",
            "powershell",
            "cmd",
            "bash",
            "sh",
            "make",
            "cmake",
            "docker",
            "docker-compose",
            "java",
            "javac",
            "mvn",
            "gradle",
            "go",
            "rustc",
            "cargo",
            "dotnet",
            "ls",
            "dir",
            "cat",
            "type",
            "echo",
            "findstr",
            "rg",
            "grep",
            "sed",
            "awk",
            "head",
            "tail",
            "wc",
            "sort",
            "uniq",
            "cp",
            "mv",
            "mkdir",
            "touch",
            "chmod",
            "chown",
            "tar",
            "zip",
            "unzip",
        ],
    )
    command_allowlist_extra: list[str] = _parse_csv_env(os.getenv("COMMAND_ALLOWLIST_EXTRA", ""), [])
    max_user_message_length: int = int(os.getenv("MAX_USER_MESSAGE_LENGTH", "8000"))
    local_model: str = os.getenv("LOCAL_MODEL", os.getenv("LLM_MODEL", "llama3.3:70b-instruct-q4_K_M"))
    api_model: str = os.getenv("API_MODEL", "minimax-m2:cloud")
    api_supported_models: list[str] = _parse_csv_env(
        os.getenv("API_SUPPORTED_MODELS", "minimax-m2:cloud,gpt-oss:20b-cloud,qwen3-coder:480b-cloud"),
        ["minimax-m2:cloud", "gpt-oss:20b-cloud", "qwen3-coder:480b-cloud"],
    )
    api_base_url: str = os.getenv("API_BASE_URL", "http://localhost:11434/api")
    ollama_bin: str = os.getenv("OLLAMA_BIN", "")
    runtime_state_file: str = _resolve_path_from_workspace(
        os.getenv("RUNTIME_STATE_FILE"),
        workspace_root,
        "runtime_state.json",
    )
    agent_tools_allow: list[str] | None = _parse_optional_csv_env(os.getenv("AGENT_TOOLS_ALLOW"))
    agent_tools_deny: list[str] = _parse_csv_env(os.getenv("AGENT_TOOLS_DENY", ""), [])
    subrun_max_concurrent: int = int(os.getenv("SUBRUN_MAX_CONCURRENT", "2"))
    subrun_timeout_seconds: int = int(os.getenv("SUBRUN_TIMEOUT_SECONDS", "900"))
    subrun_max_spawn_depth: int = int(os.getenv("SUBRUN_MAX_SPAWN_DEPTH", "2"))
    subrun_max_children_per_parent: int = int(os.getenv("SUBRUN_MAX_CHILDREN_PER_PARENT", "5"))
    subrun_leaf_spawn_depth_guard_enabled: bool = os.getenv(
        "SUBRUN_LEAF_SPAWN_DEPTH_GUARD_ENABLED",
        "false",
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    subrun_orchestrator_agent_ids: list[str] = _parse_csv_env(
        os.getenv("SUBRUN_ORCHESTRATOR_AGENT_IDS", "head-agent"),
        ["head-agent"],
    )
    subrun_announce_retry_max_attempts: int = int(os.getenv("SUBRUN_ANNOUNCE_RETRY_MAX_ATTEMPTS", "5"))
    subrun_announce_retry_base_delay_ms: int = int(os.getenv("SUBRUN_ANNOUNCE_RETRY_BASE_DELAY_MS", "500"))
    subrun_announce_retry_max_delay_ms: int = int(os.getenv("SUBRUN_ANNOUNCE_RETRY_MAX_DELAY_MS", "10000"))
    subrun_announce_retry_jitter: bool = os.getenv("SUBRUN_ANNOUNCE_RETRY_JITTER", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    subrun_restore_orphan_reconcile_enabled: bool = _parse_bool_env(
        "SUBRUN_RESTORE_ORPHAN_RECONCILE_ENABLED",
        True,
    )
    subrun_restore_orphan_grace_seconds: int = int(os.getenv("SUBRUN_RESTORE_ORPHAN_GRACE_SECONDS", "0"))
    subrun_lifecycle_delivery_error_grace_enabled: bool = _parse_bool_env(
        "SUBRUN_LIFECYCLE_DELIVERY_ERROR_GRACE_ENABLED",
        True,
    )
    policy_approval_wait_seconds: float = float(os.getenv("POLICY_APPROVAL_WAIT_SECONDS", "30"))
    session_lane_global_max_concurrent: int = int(os.getenv("SESSION_LANE_GLOBAL_MAX_CONCURRENT", "8"))
    run_wait_default_timeout_ms: int = int(os.getenv("RUN_WAIT_DEFAULT_TIMEOUT_MS", "30000"))
    run_wait_poll_interval_ms: int = int(os.getenv("RUN_WAIT_POLL_INTERVAL_MS", "200"))
    idempotency_registry_ttl_seconds: int = int(os.getenv("IDEMPOTENCY_REGISTRY_TTL_SECONDS", "86400"))
    idempotency_registry_max_entries: int = int(os.getenv("IDEMPOTENCY_REGISTRY_MAX_ENTRIES", "5000"))
    run_tool_call_cap: int = int(os.getenv("RUN_TOOL_CALL_CAP", "8"))
    run_tool_time_cap_seconds: float = float(os.getenv("RUN_TOOL_TIME_CAP_SECONDS", "90"))
    tool_result_max_chars: int = int(os.getenv("TOOL_RESULT_MAX_CHARS", "6000"))
    tool_result_smart_truncate_enabled: bool = _parse_bool_env("TOOL_RESULT_SMART_TRUNCATE_ENABLED", True)
    tool_execution_parallel_read_only_enabled: bool = _parse_bool_env(
        "TOOL_EXECUTION_PARALLEL_READ_ONLY_ENABLED",
        False,
    )
    tool_selection_function_calling_enabled: bool = _parse_bool_env(
        "TOOL_SELECTION_FUNCTION_CALLING_ENABLED",
        True,
    )
    run_max_replan_iterations: int = int(os.getenv("RUN_MAX_REPLAN_ITERATIONS", "1"))
    run_empty_tool_replan_max_attempts: int = int(os.getenv("RUN_EMPTY_TOOL_REPLAN_MAX_ATTEMPTS", "1"))
    run_error_tool_replan_max_attempts: int = int(os.getenv("RUN_ERROR_TOOL_REPLAN_MAX_ATTEMPTS", "1"))
    tool_loop_warn_threshold: int = int(os.getenv("TOOL_LOOP_WARN_THRESHOLD", "2"))
    tool_loop_critical_threshold: int = int(os.getenv("TOOL_LOOP_CRITICAL_THRESHOLD", "3"))
    tool_loop_circuit_breaker_threshold: int = int(os.getenv("TOOL_LOOP_CIRCUIT_BREAKER_THRESHOLD", "6"))
    tool_loop_detector_generic_repeat_enabled: bool = _parse_bool_env("TOOL_LOOP_DETECTOR_GENERIC_REPEAT_ENABLED", True)
    tool_loop_detector_ping_pong_enabled: bool = _parse_bool_env("TOOL_LOOP_DETECTOR_PING_PONG_ENABLED", True)
    tool_loop_detector_poll_no_progress_enabled: bool = _parse_bool_env(
        "TOOL_LOOP_DETECTOR_POLL_NO_PROGRESS_ENABLED",
        True,
    )
    tool_loop_poll_no_progress_threshold: int = int(os.getenv("TOOL_LOOP_POLL_NO_PROGRESS_THRESHOLD", "3"))
    tool_loop_warning_bucket_size: int = int(os.getenv("TOOL_LOOP_WARNING_BUCKET_SIZE", "10"))
    context_window_guard_enabled: bool = _parse_bool_env("CONTEXT_WINDOW_GUARD_ENABLED", True)
    context_window_warn_below_tokens: int = int(os.getenv("CONTEXT_WINDOW_WARN_BELOW_TOKENS", "8000"))
    context_window_hard_min_tokens: int = int(os.getenv("CONTEXT_WINDOW_HARD_MIN_TOKENS", "4000"))
    pipeline_runner_max_attempts: int = int(os.getenv("PIPELINE_RUNNER_MAX_ATTEMPTS", "16"))
    pipeline_runner_context_overflow_fallback_retry_enabled: bool = _parse_bool_env(
        "PIPELINE_RUNNER_CONTEXT_OVERFLOW_FALLBACK_RETRY_ENABLED",
        False,
    )
    pipeline_runner_context_overflow_fallback_retry_max_attempts: int = int(
        os.getenv("PIPELINE_RUNNER_CONTEXT_OVERFLOW_FALLBACK_RETRY_MAX_ATTEMPTS", "1")
    )
    pipeline_runner_compaction_failure_recovery_enabled: bool = _parse_bool_env(
        "PIPELINE_RUNNER_COMPACTION_FAILURE_RECOVERY_ENABLED",
        False,
    )
    pipeline_runner_compaction_failure_recovery_max_attempts: int = int(
        os.getenv("PIPELINE_RUNNER_COMPACTION_FAILURE_RECOVERY_MAX_ATTEMPTS", "1")
    )
    pipeline_runner_truncation_recovery_enabled: bool = _parse_bool_env(
        "PIPELINE_RUNNER_TRUNCATION_RECOVERY_ENABLED",
        False,
    )
    pipeline_runner_truncation_recovery_max_attempts: int = int(
        os.getenv("PIPELINE_RUNNER_TRUNCATION_RECOVERY_MAX_ATTEMPTS", "1")
    )
    pipeline_runner_prompt_compaction_enabled: bool = _parse_bool_env(
        "PIPELINE_RUNNER_PROMPT_COMPACTION_ENABLED",
        False,
    )
    pipeline_runner_prompt_compaction_max_attempts: int = int(
        os.getenv("PIPELINE_RUNNER_PROMPT_COMPACTION_MAX_ATTEMPTS", "1")
    )
    pipeline_runner_prompt_compaction_ratio: float = float(
        os.getenv("PIPELINE_RUNNER_PROMPT_COMPACTION_RATIO", "0.7")
    )
    pipeline_runner_prompt_compaction_min_chars: int = int(
        os.getenv("PIPELINE_RUNNER_PROMPT_COMPACTION_MIN_CHARS", "200")
    )
    pipeline_runner_payload_truncation_enabled: bool = _parse_bool_env(
        "PIPELINE_RUNNER_PAYLOAD_TRUNCATION_ENABLED",
        False,
    )
    pipeline_runner_payload_truncation_max_attempts: int = int(
        os.getenv("PIPELINE_RUNNER_PAYLOAD_TRUNCATION_MAX_ATTEMPTS", "1")
    )
    pipeline_runner_payload_truncation_target_chars: int = int(
        os.getenv("PIPELINE_RUNNER_PAYLOAD_TRUNCATION_TARGET_CHARS", "1200")
    )
    pipeline_runner_payload_truncation_min_chars: int = int(
        os.getenv("PIPELINE_RUNNER_PAYLOAD_TRUNCATION_MIN_CHARS", "120")
    )
    pipeline_runner_context_overflow_priority_local: list[str] = _parse_csv_env(
        os.getenv(
            "PIPELINE_RUNNER_CONTEXT_OVERFLOW_PRIORITY_LOCAL",
            "prompt_compaction,overflow_fallback_retry",
        ),
        ["prompt_compaction", "overflow_fallback_retry"],
    )
    pipeline_runner_context_overflow_priority_api: list[str] = _parse_csv_env(
        os.getenv(
            "PIPELINE_RUNNER_CONTEXT_OVERFLOW_PRIORITY_API",
            "overflow_fallback_retry,prompt_compaction",
        ),
        ["overflow_fallback_retry", "prompt_compaction"],
    )
    pipeline_runner_truncation_priority_local: list[str] = _parse_csv_env(
        os.getenv(
            "PIPELINE_RUNNER_TRUNCATION_PRIORITY_LOCAL",
            "payload_truncation,truncation_fallback_retry",
        ),
        ["payload_truncation", "truncation_fallback_retry"],
    )
    pipeline_runner_truncation_priority_api: list[str] = _parse_csv_env(
        os.getenv(
            "PIPELINE_RUNNER_TRUNCATION_PRIORITY_API",
            "truncation_fallback_retry,payload_truncation",
        ),
        ["truncation_fallback_retry", "payload_truncation"],
    )
    pipeline_runner_recovery_priority_flip_enabled: bool = _parse_bool_env(
        "PIPELINE_RUNNER_RECOVERY_PRIORITY_FLIP_ENABLED",
        True,
    )
    pipeline_runner_recovery_priority_flip_threshold: int = int(
        os.getenv("PIPELINE_RUNNER_RECOVERY_PRIORITY_FLIP_THRESHOLD", "2")
    )
    pipeline_runner_signal_priority_enabled: bool = _parse_bool_env(
        "PIPELINE_RUNNER_SIGNAL_PRIORITY_ENABLED",
        True,
    )
    pipeline_runner_signal_low_health_threshold: float = float(
        os.getenv("PIPELINE_RUNNER_SIGNAL_LOW_HEALTH_THRESHOLD", "0.55")
    )
    pipeline_runner_signal_high_latency_ms: int = int(
        os.getenv("PIPELINE_RUNNER_SIGNAL_HIGH_LATENCY_MS", "2500")
    )
    pipeline_runner_signal_high_cost_threshold: float = float(
        os.getenv("PIPELINE_RUNNER_SIGNAL_HIGH_COST_THRESHOLD", "0.75")
    )
    pipeline_runner_strategy_feedback_enabled: bool = _parse_bool_env(
        "PIPELINE_RUNNER_STRATEGY_FEEDBACK_ENABLED",
        True,
    )
    pipeline_runner_persistent_priority_enabled: bool = _parse_bool_env(
        "PIPELINE_RUNNER_PERSISTENT_PRIORITY_ENABLED",
        True,
    )
    pipeline_runner_persistent_priority_min_samples: int = int(
        os.getenv("PIPELINE_RUNNER_PERSISTENT_PRIORITY_MIN_SAMPLES", "3")
    )
    pipeline_runner_recovery_backoff_enabled: bool = _parse_bool_env(
        "PIPELINE_RUNNER_RECOVERY_BACKOFF_ENABLED",
        False,
    )
    pipeline_runner_recovery_backoff_base_ms: int = int(
        os.getenv("PIPELINE_RUNNER_RECOVERY_BACKOFF_BASE_MS", "150")
    )
    pipeline_runner_recovery_backoff_max_ms: int = int(
        os.getenv("PIPELINE_RUNNER_RECOVERY_BACKOFF_MAX_MS", "2000")
    )
    pipeline_runner_recovery_backoff_multiplier: float = float(
        os.getenv("PIPELINE_RUNNER_RECOVERY_BACKOFF_MULTIPLIER", "2.0")
    )
    pipeline_runner_recovery_backoff_jitter: bool = _parse_bool_env(
        "PIPELINE_RUNNER_RECOVERY_BACKOFF_JITTER",
        False,
    )
    pipeline_runner_persistent_priority_decay_enabled: bool = _parse_bool_env(
        "PIPELINE_RUNNER_PERSISTENT_PRIORITY_DECAY_ENABLED",
        True,
    )
    pipeline_runner_persistent_priority_decay_half_life_seconds: int = int(
        os.getenv("PIPELINE_RUNNER_PERSISTENT_PRIORITY_DECAY_HALF_LIFE_SECONDS", "86400")
    )
    pipeline_runner_persistent_priority_window_size: int = int(
        os.getenv("PIPELINE_RUNNER_PERSISTENT_PRIORITY_WINDOW_SIZE", "50")
    )
    pipeline_runner_persistent_priority_window_max_age_seconds: int = int(
        os.getenv("PIPELINE_RUNNER_PERSISTENT_PRIORITY_WINDOW_MAX_AGE_SECONDS", "604800")
    )
    session_visibility_default: str = os.getenv("SESSION_VISIBILITY_DEFAULT", "tree")
    api_auth_required: bool = _parse_bool_env("API_AUTH_REQUIRED", False)
    api_auth_token: str = os.getenv("API_AUTH_TOKEN", os.getenv("OLLAMA_API_KEY", ""))
    persist_transform_max_string_chars: int = int(os.getenv("PERSIST_TRANSFORM_MAX_STRING_CHARS", "8000"))
    persist_transform_redact_secrets: bool = os.getenv("PERSIST_TRANSFORM_REDACT_SECRETS", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


settings = Settings()


def resolved_prompt_settings(current_settings: Settings) -> dict[str, str]:
    return {key: str(getattr(current_settings, key)) for key in PROMPT_SETTING_KEYS}
