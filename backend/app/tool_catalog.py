from __future__ import annotations

TOOL_NAMES: tuple[str, ...] = (
    "list_dir",
    "read_file",
    "write_file",
    "run_command",
    "apply_patch",
    "file_search",
    "grep_search",
    "list_code_usages",
    "get_changed_files",
    "start_background_command",
    "get_background_output",
    "kill_background_process",
    "web_fetch",
    "spawn_subrun",
)

TOOL_NAME_SET: set[str] = set(TOOL_NAMES)

TOOL_NAME_ALIASES: dict[str, str] = {
    "createfile": "write_file",
    "writefile": "write_file",
    "readfile": "read_file",
    "listdir": "list_dir",
    "runcommand": "run_command",
    "applypatch": "apply_patch",
    "filesearch": "file_search",
    "grepsearch": "grep_search",
    "listcodeusages": "list_code_usages",
    "getchangedfiles": "get_changed_files",
    "startbackgroundcommand": "start_background_command",
    "getbackgroundoutput": "get_background_output",
    "killbackgroundprocess": "kill_background_process",
    "webfetch": "web_fetch",
    "spawnsubrun": "spawn_subrun",
}
