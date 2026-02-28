from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseModel):
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
    llm_model: str = os.getenv("LLM_MODEL", "llama3.3:70b-instruct-q4_K_M")
    agent_name: str = os.getenv("AGENT_NAME", "head-coder")
    agent_system_prompt: str = os.getenv(
        "AGENT_SYSTEM_PROMPT",
        "You are a senior coding head agent. Think step-by-step and return practical plans.",
    )
    workspace_root: str = os.getenv("WORKSPACE_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
    memory_max_items: int = int(os.getenv("MEMORY_MAX_ITEMS", "30"))
    memory_persist_dir: str = os.getenv("MEMORY_PERSIST_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "memory_store")))
    command_timeout_seconds: int = int(os.getenv("COMMAND_TIMEOUT_SECONDS", "60"))
    max_user_message_length: int = int(os.getenv("MAX_USER_MESSAGE_LENGTH", "8000"))
    local_model: str = os.getenv("LOCAL_MODEL", os.getenv("LLM_MODEL", "llama3.3:70b-instruct-q4_K_M"))
    api_model: str = os.getenv("API_MODEL", "minimax-m2:cloud")
    api_base_url: str = os.getenv("API_BASE_URL", "http://localhost:11434/api")
    ollama_bin: str = os.getenv("OLLAMA_BIN", "")
    runtime_state_file: str = os.getenv("RUNTIME_STATE_FILE", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "runtime_state.json")))


settings = Settings()
