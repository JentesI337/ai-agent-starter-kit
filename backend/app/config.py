from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


def _parse_csv_env(value: str, fallback: list[str]) -> list[str]:
    entries = [item.strip() for item in (value or "").split(",") if item.strip()]
    return entries or fallback


def _parse_optional_csv_env(value: str | None) -> list[str] | None:
    entries = [item.strip() for item in (value or "").split(",") if item.strip()]
    return entries or None


class Settings(BaseModel):
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
    llm_model: str = os.getenv("LLM_MODEL", "llama3.3:70b-instruct-q4_K_M")
    agent_name: str = os.getenv("AGENT_NAME", "head-agent")
    coder_agent_name: str = os.getenv("CODER_AGENT_NAME", "coder-agent")
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
    workspace_root: str = os.getenv("WORKSPACE_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
    memory_max_items: int = int(os.getenv("MEMORY_MAX_ITEMS", "30"))
    memory_persist_dir: str = os.getenv("MEMORY_PERSIST_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "memory_store")))
    memory_reset_on_startup: bool = os.getenv("MEMORY_RESET_ON_STARTUP", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    orchestrator_state_dir: str = os.getenv("ORCHESTRATOR_STATE_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "state_store")))
    orchestrator_state_reset_on_startup: bool = os.getenv("ORCHESTRATOR_STATE_RESET_ON_STARTUP", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    command_timeout_seconds: int = int(os.getenv("COMMAND_TIMEOUT_SECONDS", "60"))
    max_user_message_length: int = int(os.getenv("MAX_USER_MESSAGE_LENGTH", "8000"))
    local_model: str = os.getenv("LOCAL_MODEL", os.getenv("LLM_MODEL", "llama3.3:70b-instruct-q4_K_M"))
    api_model: str = os.getenv("API_MODEL", "minimax-m2:cloud")
    api_supported_models: list[str] = _parse_csv_env(
        os.getenv("API_SUPPORTED_MODELS", "minimax-m2:cloud,gpt-oss:20b-cloud,qwen3-coder:480b-cloud"),
        ["minimax-m2:cloud", "gpt-oss:20b-cloud", "qwen3-coder:480b-cloud"],
    )
    api_base_url: str = os.getenv("API_BASE_URL", "http://localhost:11434/api")
    ollama_bin: str = os.getenv("OLLAMA_BIN", "")
    runtime_state_file: str = os.getenv("RUNTIME_STATE_FILE", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "runtime_state.json")))
    agent_tools_allow: list[str] | None = _parse_optional_csv_env(os.getenv("AGENT_TOOLS_ALLOW"))
    agent_tools_deny: list[str] = _parse_csv_env(os.getenv("AGENT_TOOLS_DENY", ""), [])
    subrun_max_concurrent: int = int(os.getenv("SUBRUN_MAX_CONCURRENT", "2"))
    subrun_timeout_seconds: int = int(os.getenv("SUBRUN_TIMEOUT_SECONDS", "900"))
    subrun_max_spawn_depth: int = int(os.getenv("SUBRUN_MAX_SPAWN_DEPTH", "2"))
    subrun_max_children_per_parent: int = int(os.getenv("SUBRUN_MAX_CHILDREN_PER_PARENT", "5"))
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
    session_visibility_default: str = os.getenv("SESSION_VISIBILITY_DEFAULT", "tree")
    persist_transform_max_string_chars: int = int(os.getenv("PERSIST_TRANSFORM_MAX_STRING_CHARS", "8000"))
    persist_transform_redact_secrets: bool = os.getenv("PERSIST_TRANSFORM_REDACT_SECRETS", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


settings = Settings()
