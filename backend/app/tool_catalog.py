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
    # DevOps tools
    "git_log",
    "git_diff",
    "git_blame",
    "git_show",
    "git_stash",
    "run_tests",
    "lint_check",
    "test_coverage",
    "dependency_audit",
    "dependency_outdated",
    "dependency_tree",
    "parse_errors",
    "secrets_scan",
    "security_check",
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

# DevOps tool groups — feature-gated per category
_GIT_TOOLS: frozenset[str] = frozenset({
    "git_log", "git_diff", "git_blame", "git_show", "git_stash",
})
_TESTING_TOOLS: frozenset[str] = frozenset({
    "run_tests", "test_coverage",
})
_LINT_TOOLS: frozenset[str] = frozenset({
    "lint_check",
})
_DEPENDENCY_TOOLS: frozenset[str] = frozenset({
    "dependency_audit", "dependency_outdated", "dependency_tree",
})
_SECURITY_TOOLS: frozenset[str] = frozenset({
    "secrets_scan", "security_check",
})
_DEBUG_TOOLS: frozenset[str] = frozenset({
    "parse_errors",
})
_ALL_DEVOPS_TOOLS: frozenset[str] = (
    _GIT_TOOLS | _TESTING_TOOLS | _LINT_TOOLS | _DEPENDENCY_TOOLS | _SECURITY_TOOLS | _DEBUG_TOOLS
)


def _build_active_tool_set() -> set[str]:
    """Return the set of tool names filtered by feature toggles."""
    active = set(TOOL_NAMES)
    if not settings.browser_enabled:
        active -= _BROWSER_TOOLS
    if not settings.rag_enabled:
        active -= _RAG_TOOLS
    if not settings.repl_enabled:
        active -= _REPL_TOOLS
    # DevOps tools: master gate + per-category gates
    if not settings.devops_tools_enabled:
        active -= _ALL_DEVOPS_TOOLS
    else:
        if not settings.devops_git_tools_enabled:
            active -= _GIT_TOOLS
        if not settings.devops_testing_tools_enabled:
            active -= _TESTING_TOOLS
        if not settings.devops_lint_tools_enabled:
            active -= _LINT_TOOLS
        if not settings.devops_dependency_tools_enabled:
            active -= _DEPENDENCY_TOOLS
        if not settings.devops_security_tools_enabled:
            active -= _SECURITY_TOOLS
        if not settings.devops_debug_tools_enabled:
            active -= _DEBUG_TOOLS
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
    # DevOps aliases
    "gitlog": "git_log",
    "git_history": "git_log",
    "gitdiff": "git_diff",
    "gitblame": "git_blame",
    "gitshow": "git_show",
    "gitstash": "git_stash",
    "runtests": "run_tests",
    "test": "run_tests",
    "lintcheck": "lint_check",
    "lint": "lint_check",
    "testcoverage": "test_coverage",
    "coverage": "test_coverage",
    "dependencyaudit": "dependency_audit",
    "dep_audit": "dependency_audit",
    "dependencyoutdated": "dependency_outdated",
    "dep_outdated": "dependency_outdated",
    "dependencytree": "dependency_tree",
    "dep_tree": "dependency_tree",
    "parseerrors": "parse_errors",
    "parse_stacktrace": "parse_errors",
    "secretsscan": "secrets_scan",
    "securitycheck": "security_check",
}
