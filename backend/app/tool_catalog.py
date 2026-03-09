from __future__ import annotations

from app.config import settings

TOOL_NAMES: tuple[str, ...] = (
    "list_dir",
    "read_file",
    "write_file",
    "run_command",
    "code_execute",
    "code_reset",
    "apply_patch",
    "file_search",
    "grep_search",
    "list_code_usages",
    "get_changed_files",
    "start_background_command",
    "get_background_output",
    "kill_background_process",
    "web_search",
    "web_fetch",
    "http_request",
    "analyze_image",
    "browser_open",
    "browser_click",
    "browser_type",
    "browser_screenshot",
    "browser_read_dom",
    "browser_evaluate_js",
    "rag_ingest",
    "rag_query",
    "rag_collections",
    "spawn_subrun",
    "create_workflow",
    "delete_workflow",
)

# Feature-gated tool groups — removed from the active set when disabled.
_BROWSER_TOOLS: frozenset[str] = frozenset({
    "browser_open", "browser_click", "browser_type",
    "browser_screenshot", "browser_read_dom", "browser_evaluate_js",
})
_RAG_TOOLS: frozenset[str] = frozenset({
    "rag_ingest", "rag_query", "rag_collections",
})
_REPL_TOOLS: frozenset[str] = frozenset({
    "code_execute", "code_reset",
})


def _build_active_tool_set() -> set[str]:
    """Return the set of tool names filtered by feature toggles."""
    active = set(TOOL_NAMES)
    if not settings.browser_enabled:
        active -= _BROWSER_TOOLS
    if not settings.rag_enabled:
        active -= _RAG_TOOLS
    if not settings.repl_enabled:
        active -= _REPL_TOOLS
    return active


TOOL_NAME_SET: set[str] = _build_active_tool_set()

TOOL_NAME_ALIASES: dict[str, str] = {
    "createfile": "write_file",
    "writefile": "write_file",
    "readfile": "read_file",
    "listdir": "list_dir",
    "runcommand": "run_command",
    "codeexecute": "code_execute",
    "codereset": "code_reset",
    "code_interpreter_reset": "code_reset",
    "applypatch": "apply_patch",
    "filesearch": "file_search",
    "grepsearch": "grep_search",
    "listcodeusages": "list_code_usages",
    "getchangedfiles": "get_changed_files",
    "startbackgroundcommand": "start_background_command",
    "getbackgroundoutput": "get_background_output",
    "killbackgroundprocess": "kill_background_process",
    "websearch": "web_search",
    "search_web": "web_search",
    "search": "web_search",
    "webfetch": "web_fetch",
    "httprequest": "http_request",
    "http_request_tool": "http_request",
    "analyzeimage": "analyze_image",
    "vision": "analyze_image",
    "image_analysis": "analyze_image",
    "spawnsubrun": "spawn_subrun",
    "createworkflow": "create_workflow",
    "deleteworkflow": "delete_workflow",
    "browseropen": "browser_open",
    "open_browser": "browser_open",
    "browserclick": "browser_click",
    "browsertype": "browser_type",
    "browserscreenshot": "browser_screenshot",
    "screenshot": "browser_screenshot",
    "browserreaddom": "browser_read_dom",
    "browser_dom": "browser_read_dom",
    "browserevaluatejs": "browser_evaluate_js",
    "browser_js": "browser_evaluate_js",
    "browser_eval": "browser_evaluate_js",
    "ragingest": "rag_ingest",
    "ingest": "rag_ingest",
    "ragquery": "rag_query",
    "rag_search": "rag_query",
    "ragcollections": "rag_collections",
    "rag_list": "rag_collections",
}
