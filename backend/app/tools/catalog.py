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
    "emit_visualization",
    "spawn_subrun",
    "create_workflow",
    # Agent management tools
    "create_agent",
    "list_agents",
    # API connector tools
    "api_call",
    "api_list_connectors",
    "api_auth",
    # Multimodal tools
    "parse_pdf",
    "transcribe_audio",
    "generate_image",
    "generate_audio",
    "export_pdf",
    # Workflow tools
    "build_workflow",
    "explore_connector",
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

# Multimodal tools — feature-gated
_MULTIMODAL_TOOLS: frozenset[str] = frozenset({
    "parse_pdf", "transcribe_audio", "generate_image", "generate_audio", "export_pdf",
})

# API connector tools — feature-gated
_API_CONNECTOR_TOOLS: frozenset[str] = frozenset({
    "api_call", "api_list_connectors", "api_auth",
})


def _build_active_tool_set() -> set[str]:
    """Return the set of tool names filtered by feature toggles."""
    active = set(TOOL_NAMES)
    if not settings.browser_enabled:
        active -= _BROWSER_TOOLS
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
    if not settings.api_connectors_enabled:
        active -= _API_CONNECTOR_TOOLS
    if not settings.multimodal_tools_enabled:
        active -= _MULTIMODAL_TOOLS
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
    "emitvisualization": "emit_visualization",
    "render_diagram": "emit_visualization",
    "mermaid": "emit_visualization",
    "visualize": "emit_visualization",
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
    # API connector aliases
    "apicall": "api_call",
    "api_request": "api_call",
    "list_connectors": "api_list_connectors",
    "apilistconnectors": "api_list_connectors",
    "apiauth": "api_auth",
    "api_authenticate": "api_auth",
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
    # Multimodal aliases
    "parsepdf": "parse_pdf",
    "pdf_parse": "parse_pdf",
    "read_pdf": "parse_pdf",
    "transcribeaudio": "transcribe_audio",
    "speech_to_text": "transcribe_audio",
    "generateimage": "generate_image",
    "create_image": "generate_image",
    "dall_e": "generate_image",
    "generateaudio": "generate_audio",
    "text_to_speech": "generate_audio",
    "tts": "generate_audio",
    "exportpdf": "export_pdf",
    "markdown_to_pdf": "export_pdf",
    # Agent management aliases
    "createagent": "create_agent",
    "new_agent": "create_agent",
    "add_agent": "create_agent",
    "create_specialist": "create_agent",
    "listagents": "list_agents",
    "get_agents": "list_agents",
    "show_agents": "list_agents",
}
