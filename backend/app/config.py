from pydantic import BaseModel
from dotenv import load_dotenv
import os
from collections.abc import Mapping
from typing import Any

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


def _parse_int_mapping_env(value: str | None) -> dict[str, int]:
    parsed: dict[str, int] = {}
    for entry in (value or "").split(","):
        part = entry.strip()
        if not part or ":" not in part:
            continue
        key, raw_value = part.split(":", 1)
        normalized_key = key.strip()
        if not normalized_key:
            continue
        try:
            parsed[normalized_key] = int(raw_value.strip())
        except (TypeError, ValueError):
            continue
    return parsed


def _parse_str_mapping_env(value: str | None) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for entry in (value or "").split(","):
        part = entry.strip()
        if not part or ":" not in part:
            continue
        key, raw_value = part.split(":", 1)
        normalized_key = key.strip()
        normalized_value = raw_value.strip()
        if not normalized_key or not normalized_value:
            continue
        parsed[normalized_key] = normalized_value
    return parsed


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
        (
            "You are a highly capable autonomous agent. "
            "For every user request, follow this internal reasoning protocol:\n"
            "1. UNDERSTAND: Restate the user's goal in one sentence. Identify ambiguity.\n"
            "2. DECOMPOSE: Break complex problems into 2-5 independent sub-problems.\n"
            "3. PLAN: For each sub-problem, identify which tools or knowledge you need.\n"
            "4. EXECUTE: Work through sub-problems systematically.\n"
            "5. VERIFY: After generating your answer, check: Does this actually solve the stated goal?\n"
            "6. REFINE: If the answer is incomplete or could be wrong, state what's uncertain.\n\n"
            "Principles:\n"
            "- Think step-by-step before acting.\n"
            "- When uncertain, state your confidence level.\n"
            "- If you lack information, explain what you'd need to find out.\n"
            "- Prefer depth over breadth — a thorough answer to the right question beats a shallow answer to many.\n"
            "- Be concise in output but thorough in reasoning."
        ),
        "HEAD_AGENT_SYSTEM_PROMPT",
        "AGENT_SYSTEM_PROMPT",
    )
    head_agent_plan_prompt: str = _resolve_prompt(
        (
            "You are a planning agent. Your job is to create execution plans.\n\n"
            "Planning protocol:\n"
            "1. CLASSIFY the request: Is this trivial (greeting, yes/no), moderate (single task), or complex (multi-step)?\n"
            "2. For TRIVIAL: Return 'direct_answer' — no tools needed.\n"
            "3. For MODERATE: Return 1-3 actionable steps with specific tool calls.\n"
            "4. For COMPLEX: Return a dependency graph:\n"
            "   - Which steps can run in parallel?\n"
            "   - Which steps depend on results from earlier steps?\n"
            "   - What's the fallback if a step fails?\n\n"
            "Each step must specify:\n"
            "- WHAT to do (concrete action)\n"
            "- WHY (how it serves the goal)\n"
            "- TOOL (which tool to use, or 'none')\n"
            "- DEPENDS_ON (which earlier step, or 'none')\n\n"
            "If the request is ambiguous, add a 'CLARIFICATION_NEEDED' flag with what you'd ask the user."
        ),
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
        (
            "You are a synthesis agent generating the final answer.\n\n"
            "Before writing your answer, internally verify:\n"
            "1. Does the answer address the user's ACTUAL question (not a related one)?\n"
            "2. Is every factual claim grounded in tool outputs or stated knowledge?\n"
            "3. Are there gaps? If yes, explicitly state them.\n"
            "4. Could the answer be misunderstood? If yes, add clarification.\n\n"
            "Output rules:\n"
            "- Lead with the most important information.\n"
            "- For coding tasks: include runnable code, not pseudo-code.\n"
            "- For research: cite your sources (from tool outputs).\n"
            "- For analysis: show your reasoning chain.\n"
            "- End with concrete next steps the user can take.\n"
            "- If tool outputs contradicted your initial assumption, say so."
        ),
        "HEAD_AGENT_FINAL_PROMPT",
        "HEAD_AGENT_SYSTEM_PROMPT",
        "AGENT_FINAL_PROMPT",
        "AGENT_SYSTEM_PROMPT",
    )
    coder_agent_system_prompt: str = _resolve_prompt(
        (
            "You are a highly capable autonomous coding agent. "
            "For every user request, follow this internal reasoning protocol:\n"
            "1. UNDERSTAND: Restate the user's goal in one sentence. Identify ambiguity.\n"
            "2. DECOMPOSE: Break complex problems into 2-5 independent sub-problems.\n"
            "3. PLAN: For each sub-problem, identify which tools or knowledge you need.\n"
            "4. EXECUTE: Work through sub-problems systematically.\n"
            "5. VERIFY: After generating your answer, check: Does this actually solve the stated goal?\n"
            "6. REFINE: If the answer is incomplete or could be wrong, state what's uncertain.\n\n"
            "Principles:\n"
            "- Think step-by-step before acting.\n"
            "- When uncertain, state your confidence level.\n"
            "- If you lack information, explain what you'd need to find out.\n"
            "- Prefer depth over breadth — a thorough answer to the right question beats a shallow answer to many.\n"
            "- Be concise in output but thorough in reasoning."
        ),
        "CODER_AGENT_SYSTEM_PROMPT",
    )
    coder_agent_plan_prompt: str = _resolve_prompt(
        (
            "You are a planning agent. Your job is to create execution plans.\n\n"
            "Planning protocol:\n"
            "1. CLASSIFY the request: Is this trivial (greeting, yes/no), moderate (single task), or complex (multi-step)?\n"
            "2. For TRIVIAL: Return 'direct_answer' — no tools needed.\n"
            "3. For MODERATE: Return 1-3 actionable steps with specific tool calls.\n"
            "4. For COMPLEX: Return a dependency graph:\n"
            "   - Which steps can run in parallel?\n"
            "   - Which steps depend on results from earlier steps?\n"
            "   - What's the fallback if a step fails?\n\n"
            "Each step must specify:\n"
            "- WHAT to do (concrete action)\n"
            "- WHY (how it serves the goal)\n"
            "- TOOL (which tool to use, or 'none')\n"
            "- DEPENDS_ON (which earlier step, or 'none')\n\n"
            "If the request is ambiguous, add a 'CLARIFICATION_NEEDED' flag with what you'd ask the user."
        ),
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
        (
            "You are a synthesis agent generating the final answer.\n\n"
            "Before writing your answer, internally verify:\n"
            "1. Does the answer address the user's ACTUAL question (not a related one)?\n"
            "2. Is every factual claim grounded in tool outputs or stated knowledge?\n"
            "3. Are there gaps? If yes, explicitly state them.\n"
            "4. Could the answer be misunderstood? If yes, add clarification.\n\n"
            "Output rules:\n"
            "- Lead with the most important information.\n"
            "- For coding tasks: include runnable code, not pseudo-code.\n"
            "- For research: cite your sources (from tool outputs).\n"
            "- For analysis: show your reasoning chain.\n"
            "- End with concrete next steps the user can take.\n"
            "- If tool outputs contradicted your initial assumption, say so."
        ),
        "CODER_AGENT_FINAL_PROMPT",
        "CODER_AGENT_SYSTEM_PROMPT",
    )
    agent_system_prompt: str = _resolve_prompt(
        (
            "You are a highly capable autonomous agent. "
            "For every user request, follow this internal reasoning protocol:\n"
            "1. UNDERSTAND: Restate the user's goal in one sentence. Identify ambiguity.\n"
            "2. DECOMPOSE: Break complex problems into 2-5 independent sub-problems.\n"
            "3. PLAN: For each sub-problem, identify which tools or knowledge you need.\n"
            "4. EXECUTE: Work through sub-problems systematically.\n"
            "5. VERIFY: After generating your answer, check: Does this actually solve the stated goal?\n"
            "6. REFINE: If the answer is incomplete or could be wrong, state what's uncertain.\n\n"
            "Principles:\n"
            "- Think step-by-step before acting.\n"
            "- When uncertain, state your confidence level.\n"
            "- If you lack information, explain what you'd need to find out.\n"
            "- Prefer depth over breadth — a thorough answer to the right question beats a shallow answer to many.\n"
            "- Be concise in output but thorough in reasoning."
        ),
        "AGENT_SYSTEM_PROMPT",
    )
    agent_plan_prompt: str = _resolve_prompt(
        (
            "You are a planning agent. Your job is to create execution plans.\n\n"
            "Planning protocol:\n"
            "1. CLASSIFY the request: Is this trivial (greeting, yes/no), moderate (single task), or complex (multi-step)?\n"
            "2. For TRIVIAL: Return 'direct_answer' — no tools needed.\n"
            "3. For MODERATE: Return 1-3 actionable steps with specific tool calls.\n"
            "4. For COMPLEX: Return a dependency graph:\n"
            "   - Which steps can run in parallel?\n"
            "   - Which steps depend on results from earlier steps?\n"
            "   - What's the fallback if a step fails?\n\n"
            "Each step must specify:\n"
            "- WHAT to do (concrete action)\n"
            "- WHY (how it serves the goal)\n"
            "- TOOL (which tool to use, or 'none')\n"
            "- DEPENDS_ON (which earlier step, or 'none')\n\n"
            "If the request is ambiguous, add a 'CLARIFICATION_NEEDED' flag with what you'd ask the user."
        ),
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
        (
            "You are a synthesis agent generating the final answer.\n\n"
            "Before writing your answer, internally verify:\n"
            "1. Does the answer address the user's ACTUAL question (not a related one)?\n"
            "2. Is every factual claim grounded in tool outputs or stated knowledge?\n"
            "3. Are there gaps? If yes, explicitly state them.\n"
            "4. Could the answer be misunderstood? If yes, add clarification.\n\n"
            "Output rules:\n"
            "- Lead with the most important information.\n"
            "- For coding tasks: include runnable code, not pseudo-code.\n"
            "- For research: cite your sources (from tool outputs).\n"
            "- For analysis: show your reasoning chain.\n"
            "- End with concrete next steps the user can take.\n"
            "- If tool outputs contradicted your initial assumption, say so."
        ),
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
    skills_snapshot_cache_ttl_seconds: float = float(os.getenv("SKILLS_SNAPSHOT_CACHE_TTL_SECONDS", "15"))
    skills_snapshot_cache_use_mtime: bool = _parse_bool_env("SKILLS_SNAPSHOT_CACHE_USE_MTIME", True)
    reliable_retrieval_enabled: bool = _parse_bool_env("RELIABLE_RETRIEVAL_ENABLED", True)
    reliable_retrieval_max_sources: int = int(os.getenv("RELIABLE_RETRIEVAL_MAX_SOURCES", "4"))
    reliable_retrieval_min_score: float = float(os.getenv("RELIABLE_RETRIEVAL_MIN_SCORE", "0.02"))
    reliable_retrieval_cache_ttl_seconds: float = float(os.getenv("RELIABLE_RETRIEVAL_CACHE_TTL_SECONDS", "30"))
    reliable_retrieval_default_source_trust: float = float(
        os.getenv("RELIABLE_RETRIEVAL_DEFAULT_SOURCE_TRUST", "0.8")
    )
    orchestrator_state_reset_on_startup: bool = _parse_bool_env(
        "ORCHESTRATOR_STATE_RESET_ON_STARTUP",
        _default_reset_on_startup(app_env),
    )
    run_state_violation_hard_fail_enabled: bool = _parse_bool_env(
        "RUN_STATE_VIOLATION_HARD_FAIL_ENABLED",
        False,
    )
    config_strict_unknown_keys_enabled: bool = _parse_bool_env("CONFIG_STRICT_UNKNOWN_KEYS_ENABLED", False)
    config_strict_unknown_keys_allowlist: list[str] = _parse_csv_env(
        os.getenv("CONFIG_STRICT_UNKNOWN_KEYS_ALLOWLIST", ""),
        [],
    )
    queue_mode_default: str = os.getenv("QUEUE_MODE_DEFAULT", "wait").strip().lower()
    prompt_mode_default: str = os.getenv("PROMPT_MODE_DEFAULT", "full").strip().lower()
    session_inbox_max_queue_length: int = int(os.getenv("SESSION_INBOX_MAX_QUEUE_LENGTH", "100"))
    session_inbox_ttl_seconds: int = int(os.getenv("SESSION_INBOX_TTL_SECONDS", "600"))
    session_follow_up_max_deferrals: int = int(os.getenv("SESSION_FOLLOW_UP_MAX_DEFERRALS", "2"))
    command_timeout_seconds: int = int(os.getenv("COMMAND_TIMEOUT_SECONDS", "60"))
    web_search_provider: str = os.getenv("WEB_SEARCH_PROVIDER", "duckduckgo").strip().lower()
    web_search_api_key: str = os.getenv("WEB_SEARCH_API_KEY", "")
    web_search_base_url: str = os.getenv("WEB_SEARCH_BASE_URL", "")
    web_search_max_results: int = max(1, min(10, int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))))
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
    agent_isolation_enabled: bool = _parse_bool_env("AGENT_ISOLATION_ENABLED", True)
    agent_isolation_allowed_scope_pairs: list[str] = _parse_csv_env(
        os.getenv("AGENT_ISOLATION_ALLOWED_SCOPE_PAIRS", ""),
        [],
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
    hook_contract_version: str = os.getenv("HOOK_CONTRACT_VERSION", "hook-contract.v2").strip()
    hook_timeout_ms_default: int = int(os.getenv("HOOK_TIMEOUT_MS_DEFAULT", "1500"))
    hook_timeout_ms_overrides: dict[str, int] = _parse_int_mapping_env(os.getenv("HOOK_TIMEOUT_MS_OVERRIDES", ""))
    hook_failure_policy_default: str = os.getenv("HOOK_FAILURE_POLICY_DEFAULT", "soft_fail").strip().lower()
    hook_failure_policy_overrides: dict[str, str] = _parse_str_mapping_env(
        os.getenv("HOOK_FAILURE_POLICY_OVERRIDES", "")
    )
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
    reflection_enabled: bool = _parse_bool_env("REFLECTION_ENABLED", True)
    reflection_threshold: float = max(0.0, min(1.0, float(os.getenv("REFLECTION_THRESHOLD", "0.6"))))
    structured_planning_enabled: bool = _parse_bool_env("STRUCTURED_PLANNING_ENABLED", False)
    plan_max_steps: int = max(1, min(20, int(os.getenv("PLAN_MAX_STEPS", "7"))))
    plan_root_cause_replan_enabled: bool = _parse_bool_env("PLAN_ROOT_CAUSE_REPLAN_ENABLED", True)
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
    adaptive_inference_enabled: bool = _parse_bool_env("ADAPTIVE_INFERENCE_ENABLED", True)
    adaptive_inference_cost_budget_max: float = float(os.getenv("ADAPTIVE_INFERENCE_COST_BUDGET_MAX", "0.8"))
    adaptive_inference_latency_budget_ms: int = int(os.getenv("ADAPTIVE_INFERENCE_LATENCY_BUDGET_MS", "2400"))
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


CONFIG_ENV_KEY_PREFIXES: tuple[str, ...] = (
    "APP_",
    "LOG_LEVEL",
    "LLM_",
    "AGENT_",
    "HEAD_AGENT_",
    "CODER_AGENT_",
    "REVIEW_AGENT_",
    "WORKSPACE_ROOT",
    "MEMORY_",
    "ORCHESTRATOR_",
    "CUSTOM_AGENTS_",
    "SKILLS_",
    "RUN_STATE_",
    "QUEUE_",
    "PROMPT_",
    "SESSION_",
    "HOOK_",
    "COMMAND_",
    "WEB_SEARCH_",
    "WEB_FETCH_",
    "STRUCTURED_",
    "PLAN_",
    "CORS_",
    "LOCAL_MODEL",
    "API_",
    "OLLAMA_",
    "RUNTIME_STATE_FILE",
    "SUBRUN_",
    "AGENT_ISOLATION_",
    "POLICY_",
    "IDEMPOTENCY_",
    "TOOL_",
    "CONTEXT_",
    "PIPELINE_",
    "PERSIST_",
    "CONFIG_",
)

CONFIG_ENV_KEY_ALIASES: frozenset[str] = frozenset({"OLLAMA_API_KEY"})


def _is_scoped_config_env_key(env_key: str) -> bool:
    key = str(env_key or "").strip().upper()
    if not key:
        return False
    return any(key == prefix or key.startswith(prefix) for prefix in CONFIG_ENV_KEY_PREFIXES)


def _known_config_env_keys() -> set[str]:
    known = {str(field_name).upper() for field_name in Settings.model_fields.keys()}
    known.update(CONFIG_ENV_KEY_ALIASES)
    return known


def validate_environment_config(
    current_settings: Settings | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    strict_unknown_keys_enabled: bool | None = None,
    allowlist: list[str] | None = None,
) -> dict[str, Any]:
    selected_settings = current_settings or settings
    env_map = dict(environ or os.environ)
    strict_mode = (
        bool(strict_unknown_keys_enabled)
        if strict_unknown_keys_enabled is not None
        else bool(getattr(selected_settings, "config_strict_unknown_keys_enabled", False))
    )
    raw_allowlist = (
        allowlist
        if allowlist is not None
        else list(getattr(selected_settings, "config_strict_unknown_keys_allowlist", []) or [])
    )
    allowlisted = {str(item).strip().upper() for item in raw_allowlist if str(item).strip()}

    known_keys = _known_config_env_keys() | allowlisted
    scoped_keys = sorted(key for key in env_map.keys() if _is_scoped_config_env_key(str(key)))
    unknown_keys = sorted(key for key in scoped_keys if str(key).upper() not in known_keys)

    def _require_int_range(field: str, *, minimum: int, maximum: int) -> str | None:
        raw_value = getattr(selected_settings, field, None)
        if not isinstance(raw_value, int):
            return f"{field} must be int"
        if raw_value < minimum or raw_value > maximum:
            return f"{field} out of range [{minimum}, {maximum}]"
        return None

    def _require_float_range(field: str, *, minimum: float, maximum: float) -> str | None:
        raw_value = getattr(selected_settings, field, None)
        if not isinstance(raw_value, (float, int)):
            return f"{field} must be float"
        normalized = float(raw_value)
        if normalized < minimum or normalized > maximum:
            return f"{field} out of range [{minimum}, {maximum}]"
        return None

    config_errors: list[str] = []
    config_warnings: list[str] = []

    for maybe_error in (
        _require_int_range("command_timeout_seconds", minimum=1, maximum=3600),
        _require_int_range("session_inbox_max_queue_length", minimum=1, maximum=5000),
        _require_int_range("session_inbox_ttl_seconds", minimum=1, maximum=86400),
        _require_int_range("session_follow_up_max_deferrals", minimum=1, maximum=100),
        _require_int_range("run_tool_call_cap", minimum=1, maximum=256),
        _require_float_range("run_tool_time_cap_seconds", minimum=1.0, maximum=3600.0),
        _require_int_range("tool_loop_warn_threshold", minimum=1, maximum=200),
        _require_int_range("tool_loop_critical_threshold", minimum=2, maximum=400),
        _require_int_range("tool_loop_circuit_breaker_threshold", minimum=3, maximum=800),
        _require_int_range("max_user_message_length", minimum=1, maximum=200000),
    ):
        if maybe_error:
            config_errors.append(maybe_error)

    if int(getattr(selected_settings, "tool_loop_critical_threshold", 0)) <= int(
        getattr(selected_settings, "tool_loop_warn_threshold", 0)
    ):
        config_errors.append("tool_loop_critical_threshold must be greater than tool_loop_warn_threshold")
    if int(getattr(selected_settings, "tool_loop_circuit_breaker_threshold", 0)) <= int(
        getattr(selected_settings, "tool_loop_critical_threshold", 0)
    ):
        config_errors.append("tool_loop_circuit_breaker_threshold must be greater than tool_loop_critical_threshold")

    queue_mode_default = str(getattr(selected_settings, "queue_mode_default", "wait") or "wait").strip().lower()
    if queue_mode_default not in {"wait", "follow_up", "steer"}:
        config_errors.append("queue_mode_default must be one of: wait, follow_up, steer")

    prompt_mode_default = str(getattr(selected_settings, "prompt_mode_default", "full") or "full").strip().lower()
    if prompt_mode_default not in {"full", "minimal", "subagent"}:
        config_errors.append("prompt_mode_default must be one of: full, minimal, subagent")

    hook_failure_policy_default = str(
        getattr(selected_settings, "hook_failure_policy_default", "soft_fail") or "soft_fail"
    ).strip().lower()
    if hook_failure_policy_default not in {"soft_fail", "hard_fail", "skip"}:
        config_errors.append("hook_failure_policy_default must be one of: soft_fail, hard_fail, skip")

    prompt_compaction_ratio = float(getattr(selected_settings, "pipeline_runner_prompt_compaction_ratio", 0.7) or 0.7)
    if prompt_compaction_ratio <= 0.0 or prompt_compaction_ratio >= 1.0:
        config_errors.append("pipeline_runner_prompt_compaction_ratio must be > 0 and < 1")

    if config_errors:
        status = "error"
    elif not unknown_keys:
        status = "ok"
    elif strict_mode:
        status = "error"
    else:
        status = "warning"

    warnings: list[str] = []
    errors: list[str] = []
    warnings.extend(config_warnings)
    errors.extend(config_errors)
    if unknown_keys and strict_mode:
        errors.append("Unknown config keys detected in strict mode.")
    elif unknown_keys:
        warnings.append("Unknown config keys detected; strict mode disabled.")

    return {
        "schema_version": "config.v1",
        "strict_mode": strict_mode,
        "validation_status": status,
        "is_valid": len(errors) == 0,
        "unknown_keys": unknown_keys,
        "warnings": warnings,
        "errors": errors,
        "allowlist": sorted(allowlisted),
        "known_key_count": len(_known_config_env_keys()),
        "scoped_key_count": len(scoped_keys),
    }


def resolved_prompt_settings(current_settings: Settings) -> dict[str, str]:
    return {key: str(getattr(current_settings, key)) for key in PROMPT_SETTING_KEYS}
