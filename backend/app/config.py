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


class Settings(BaseModel):
    app_env: str = os.getenv("APP_ENV", "development").strip().lower()
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
    llm_model: str = os.getenv("LLM_MODEL", "llama3.3:70b-instruct-q4_K_M")
    agent_name: str = os.getenv("AGENT_NAME", "head-agent")
    coder_agent_name: str = os.getenv("CODER_AGENT_NAME", "coder-agent")
    review_agent_name: str = os.getenv("REVIEW_AGENT_NAME", "review-agent")
    head_agent_system_prompt: str = os.getenv(
        "HEAD_AGENT_SYSTEM_PROMPT",
        os.getenv(
            "AGENT_SYSTEM_PROMPT",
            "You are a neutral head agent. Be concise, factual, and adapt naturally to user intent.",
        ),
    )
    head_agent_plan_prompt: str = os.getenv(
        "HEAD_AGENT_PLAN_PROMPT",
        os.getenv(
            "HEAD_AGENT_SYSTEM_PROMPT",
            os.getenv(
                "AGENT_PLAN_PROMPT",
                os.getenv(
                    "AGENT_SYSTEM_PROMPT",
                    "You are a neutral head agent. Return a minimal, context-appropriate plan only when needed.",
                ),
            ),
        ),
    )
    head_agent_tool_selector_prompt: str = os.getenv(
        "HEAD_AGENT_TOOL_SELECTOR_PROMPT",
        os.getenv(
            "AGENT_TOOL_SELECTOR_PROMPT",
            os.getenv(
                "HEAD_AGENT_SYSTEM_PROMPT",
                "You select tools for user tasks. Strictly follow output format requirements.",
            ),
        ),
    )
    head_agent_tool_repair_prompt: str = os.getenv(
        "HEAD_AGENT_TOOL_REPAIR_PROMPT",
        os.getenv(
            "AGENT_TOOL_REPAIR_PROMPT",
            os.getenv(
                "HEAD_AGENT_SYSTEM_PROMPT",
                "You repair malformed tool selection output into strict JSON only.",
            ),
        ),
    )
    head_agent_final_prompt: str = os.getenv(
        "HEAD_AGENT_FINAL_PROMPT",
        os.getenv(
            "HEAD_AGENT_SYSTEM_PROMPT",
            os.getenv(
                "AGENT_FINAL_PROMPT",
                os.getenv(
                    "AGENT_SYSTEM_PROMPT",
                    "You are a neutral head agent. Return a concise, directly helpful final answer.",
                ),
            ),
        ),
    )
    coder_agent_system_prompt: str = os.getenv(
        "CODER_AGENT_SYSTEM_PROMPT",
        "You are a senior coding agent. Think step-by-step, break tasks into actionable implementation steps, and produce precise developer output.",
    )
    coder_agent_plan_prompt: str = os.getenv(
        "CODER_AGENT_PLAN_PROMPT",
        os.getenv("CODER_AGENT_SYSTEM_PROMPT", "You are a senior coding agent. Return a short actionable implementation plan."),
    )
    coder_agent_tool_selector_prompt: str = os.getenv(
        "CODER_AGENT_TOOL_SELECTOR_PROMPT",
        os.getenv("AGENT_TOOL_SELECTOR_PROMPT", "You select tools for a coding task. Strictly follow output format requirements."),
    )
    coder_agent_tool_repair_prompt: str = os.getenv(
        "CODER_AGENT_TOOL_REPAIR_PROMPT",
        os.getenv("AGENT_TOOL_REPAIR_PROMPT", "You repair malformed tool selection output into strict JSON only."),
    )
    coder_agent_final_prompt: str = os.getenv(
        "CODER_AGENT_FINAL_PROMPT",
        os.getenv("CODER_AGENT_SYSTEM_PROMPT", "You are a senior coding agent. Return a concise final answer with practical next steps."),
    )
    agent_system_prompt: str = os.getenv(
        "AGENT_SYSTEM_PROMPT",
        "You are a senior head agent. Think step-by-step and return practical plans.",
    )
    agent_plan_prompt: str = os.getenv(
        "AGENT_PLAN_PROMPT",
        os.getenv(
            "AGENT_SYSTEM_PROMPT",
            "You are a senior head agent. Think step-by-step and return practical plans.",
        ),
    )
    agent_tool_selector_prompt: str = os.getenv(
        "AGENT_TOOL_SELECTOR_PROMPT",
        os.getenv(
            "AGENT_SYSTEM_PROMPT",
            "You are a senior head agent. Think step-by-step and return practical plans.",
        ),
    )
    agent_tool_repair_prompt: str = os.getenv(
        "AGENT_TOOL_REPAIR_PROMPT",
        os.getenv(
            "AGENT_SYSTEM_PROMPT",
            "You are a senior head agent. Think step-by-step and return practical plans.",
        ),
    )
    agent_final_prompt: str = os.getenv(
        "AGENT_FINAL_PROMPT",
        os.getenv(
            "AGENT_SYSTEM_PROMPT",
            "You are a senior head agent. Think step-by-step and return practical plans.",
        ),
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
    custom_agents_dir: str = _resolve_path_from_workspace(
        os.getenv("CUSTOM_AGENTS_DIR"),
        workspace_root,
        "custom_agents",
    )
    orchestrator_state_reset_on_startup: bool = _parse_bool_env(
        "ORCHESTRATOR_STATE_RESET_ON_STARTUP",
        _default_reset_on_startup(app_env),
    )
    command_timeout_seconds: int = int(os.getenv("COMMAND_TIMEOUT_SECONDS", "60"))
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
    session_lane_global_max_concurrent: int = int(os.getenv("SESSION_LANE_GLOBAL_MAX_CONCURRENT", "8"))
    run_wait_default_timeout_ms: int = int(os.getenv("RUN_WAIT_DEFAULT_TIMEOUT_MS", "30000"))
    run_wait_poll_interval_ms: int = int(os.getenv("RUN_WAIT_POLL_INTERVAL_MS", "200"))
    run_tool_call_cap: int = int(os.getenv("RUN_TOOL_CALL_CAP", "8"))
    run_tool_time_cap_seconds: float = float(os.getenv("RUN_TOOL_TIME_CAP_SECONDS", "90"))
    tool_loop_warn_threshold: int = int(os.getenv("TOOL_LOOP_WARN_THRESHOLD", "2"))
    tool_loop_critical_threshold: int = int(os.getenv("TOOL_LOOP_CRITICAL_THRESHOLD", "3"))
    session_visibility_default: str = os.getenv("SESSION_VISIBILITY_DEFAULT", "tree")
    persist_transform_max_string_chars: int = int(os.getenv("PERSIST_TRANSFORM_MAX_STRING_CHARS", "8000"))
    persist_transform_redact_secrets: bool = os.getenv("PERSIST_TRANSFORM_REDACT_SECRETS", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


settings = Settings()
