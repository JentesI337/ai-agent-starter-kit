from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    required_args: tuple[str, ...]
    optional_args: tuple[str, ...]
    timeout_seconds: float
    max_retries: int
    description: str = ""
    parameters: dict[str, Any] | None = None
    capabilities: tuple[str, ...] = ()

    def function_parameters(self) -> dict[str, Any]:
        if isinstance(self.parameters, dict):
            schema = dict(self.parameters)
        else:
            properties: dict[str, Any] = {}
            for key in self.required_args:
                properties[key] = {"type": "string"}
            for key in self.optional_args:
                properties[key] = {"type": "string"}
            schema = {
                "type": "object",
                "properties": properties,
            }

        schema.setdefault("type", "object")
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            properties = {}
            schema["properties"] = properties

        required = schema.get("required")
        if not isinstance(required, list):
            required = []
        if not required:
            required = list(self.required_args)
        else:
            for name in self.required_args:
                if name not in required:
                    required.append(name)
        schema["required"] = required

        schema.setdefault("additionalProperties", False)
        return schema


@dataclass(frozen=True)
class ToolExecutionPolicy:
    retry_class: str
    timeout_seconds: float
    max_retries: int


class ToolRegistry:
    def __init__(
        self,
        specs: dict[str, ToolSpec] | None = None,
        dispatchers: dict[str, Callable[..., Any]] | None = None,
    ):
        self._specs = dict(specs or {})
        self._dispatchers = dict(dispatchers or {})

    def register(self, spec: ToolSpec, dispatcher: Callable[..., Any] | None = None) -> None:
        self._specs[spec.name] = spec
        if dispatcher is not None:
            self._dispatchers[spec.name] = dispatcher

    def __iter__(self):
        return iter(self._specs)

    def __getitem__(self, key: str) -> ToolSpec:
        return self._specs[key]

    def get(self, key: str) -> ToolSpec | None:
        return self._specs.get(key)

    def get_spec(self, key: str) -> ToolSpec | None:
        return self.get(key)

    def get_dispatcher(self, key: str) -> Callable[..., Any] | None:
        return self._dispatchers.get(key)

    def keys(self):
        return self._specs.keys()

    def items(self):
        return self._specs.items()

    def all_specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def tool_names(self) -> set[str]:
        return set(self._specs.keys())

    def build_execution_policy(self, name: str, *, retry_class: str | None = None) -> ToolExecutionPolicy:
        spec = self._specs[name]
        resolved_retry_class = retry_class
        if resolved_retry_class is None:
            resolved_retry_class = "transient" if name in {"run_command", "web_fetch", "web_search"} else "none"
        return ToolExecutionPolicy(
            retry_class=resolved_retry_class,
            timeout_seconds=spec.timeout_seconds,
            max_retries=spec.max_retries,
        )

    def build_function_calling_tools(self, *, allowed_tools: set[str] | None = None) -> list[dict[str, Any]]:
        selected_names = set(self._specs.keys()) if allowed_tools is None else set(allowed_tools)
        definitions: list[dict[str, Any]] = []
        for name in sorted(selected_names):
            spec = self._specs.get(name)
            if spec is None:
                continue
            definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description or f"Execute tool '{spec.name}'",
                        "parameters": spec.function_parameters(),
                    },
                }
            )
        return definitions

    def capabilities_for_tool(self, name: str) -> tuple[str, ...]:
        spec = self._specs.get(name)
        if spec is None:
            return ()
        return tuple(str(item).strip().lower() for item in (spec.capabilities or ()) if str(item).strip())

    def filter_tools_by_capabilities(
        self,
        *,
        candidate_tools: set[str],
        required_capabilities: set[str] | tuple[str, ...],
    ) -> set[str]:
        required = {
            str(item).strip().lower()
            for item in (required_capabilities or set())
            if str(item).strip()
        }
        if not required:
            return set(candidate_tools)

        matched: set[str] = set()
        for tool_name in candidate_tools:
            tool_caps = set(self.capabilities_for_tool(tool_name))
            if tool_caps & required:
                matched.add(tool_name)
        return matched


def _build_dynamic_dispatcher(dynamic_source: Any, tool_name: str) -> Callable[..., Any]:
    async def _dispatcher(**kwargs: Any) -> Any:
        return await dynamic_source.call_tool(tool_name, dict(kwargs or {}))

    return _dispatcher


def _default_tool_specs(*, command_timeout_seconds: int) -> dict[str, ToolSpec]:
    return {
        "list_dir": ToolSpec(
            name="list_dir",
            required_args=(),
            optional_args=("path",),
            timeout_seconds=6.0,
            max_retries=0,
            description="List directory entries for a workspace-relative or absolute path.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                },
                "required": [],
                "additionalProperties": False,
            },
            capabilities=("filesystem_read", "workspace_navigation", "code_inspection"),
        ),
        "read_file": ToolSpec(
            name="read_file",
            required_args=("path",),
            optional_args=(),
            timeout_seconds=8.0,
            max_retries=0,
            description="Read the contents of a file path.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            capabilities=("filesystem_read", "code_inspection", "knowledge_retrieval"),
        ),
        "write_file": ToolSpec(
            name="write_file",
            required_args=("path", "content"),
            optional_args=(),
            timeout_seconds=10.0,
            max_retries=0,
            description="Write complete content to a file path.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            capabilities=("filesystem_write", "code_modification", "artifact_generation"),
        ),
        "run_command": ToolSpec(
            name="run_command",
            required_args=("command",),
            optional_args=("cwd",),
            timeout_seconds=float(max(3, command_timeout_seconds)),
            max_retries=1,
            description="Execute a shell command, optionally in a specific working directory.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "minLength": 1},
                    "cwd": {"type": "string", "minLength": 1},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
            capabilities=("command_execution", "build_and_test", "environment_interaction"),
        ),
        "code_execute": ToolSpec(
            name="code_execute",
            required_args=("code",),
            optional_args=("language", "timeout", "max_output_chars", "strategy"),
            timeout_seconds=45.0,
            max_retries=0,
            description=(
                "Execute code in a sandboxed environment. "
                "Supports python and javascript with timeout and output limits."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "minLength": 1},
                    "language": {"type": "string", "enum": ["python", "javascript", "js"]},
                    "timeout": {"type": "integer", "minimum": 1, "maximum": 60},
                    "max_output_chars": {"type": "integer", "minimum": 500, "maximum": 20000},
                    "strategy": {"type": "string", "enum": ["process", "direct", "docker"]},
                },
                "required": ["code"],
                "additionalProperties": False,
            },
            capabilities=("code_execution", "calculation", "data_analysis", "testing"),
        ),
        "apply_patch": ToolSpec(
            name="apply_patch",
            required_args=("path", "search", "replace"),
            optional_args=("replace_all",),
            timeout_seconds=10.0,
            max_retries=0,
            description="Apply textual replacement to a file, optionally replacing all matches.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "search": {"type": "string", "minLength": 1},
                    "replace": {"type": "string"},
                    "replace_all": {"type": "boolean"},
                },
                "required": ["path", "search", "replace"],
                "additionalProperties": False,
            },
            capabilities=("filesystem_write", "code_modification", "patching"),
        ),
        "file_search": ToolSpec(
            name="file_search",
            required_args=("pattern",),
            optional_args=("max_results",),
            timeout_seconds=6.0,
            max_retries=0,
            description="Search files by glob pattern.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "minLength": 1},
                    "max_results": {"type": "integer", "minimum": 1},
                },
                "required": ["pattern"],
                "additionalProperties": False,
            },
            capabilities=("filesystem_read", "code_search", "knowledge_retrieval"),
        ),
        "grep_search": ToolSpec(
            name="grep_search",
            required_args=("query",),
            optional_args=("include_pattern", "is_regexp", "max_results"),
            timeout_seconds=8.0,
            max_retries=0,
            description="Search text in files with optional include pattern and regex mode.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "include_pattern": {"type": "string", "minLength": 1},
                    "is_regexp": {"type": "boolean"},
                    "max_results": {"type": "integer", "minimum": 1},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            capabilities=("filesystem_read", "code_search", "knowledge_retrieval"),
        ),
        "list_code_usages": ToolSpec(
            name="list_code_usages",
            required_args=("symbol",),
            optional_args=("include_pattern", "max_results"),
            timeout_seconds=8.0,
            max_retries=0,
            description="List code usages for a symbol.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "minLength": 1},
                    "include_pattern": {"type": "string", "minLength": 1},
                    "max_results": {"type": "integer", "minimum": 1},
                },
                "required": ["symbol"],
                "additionalProperties": False,
            },
            capabilities=("code_search", "static_analysis", "knowledge_retrieval"),
        ),
        "get_changed_files": ToolSpec(
            name="get_changed_files",
            required_args=(),
            optional_args=(),
            timeout_seconds=8.0,
            max_retries=0,
            description="List changed files in git status.",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            capabilities=("git_inspection", "code_inspection", "knowledge_retrieval"),
        ),
        "start_background_command": ToolSpec(
            name="start_background_command",
            required_args=("command",),
            optional_args=("cwd",),
            timeout_seconds=6.0,
            max_retries=0,
            description="Start a background command process.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "minLength": 1},
                    "cwd": {"type": "string", "minLength": 1},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
            capabilities=("command_execution", "async_execution", "build_and_test"),
        ),
        "get_background_output": ToolSpec(
            name="get_background_output",
            required_args=("job_id",),
            optional_args=("tail_lines",),
            timeout_seconds=5.0,
            max_retries=0,
            description="Fetch output from a background process.",
            parameters={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "minLength": 1},
                    "tail_lines": {"type": "integer", "minimum": 1},
                },
                "required": ["job_id"],
                "additionalProperties": False,
            },
            capabilities=("command_execution", "async_execution", "observability"),
        ),
        "kill_background_process": ToolSpec(
            name="kill_background_process",
            required_args=("job_id",),
            optional_args=(),
            timeout_seconds=5.0,
            max_retries=0,
            description="Terminate a background process by job id.",
            parameters={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "minLength": 1},
                },
                "required": ["job_id"],
                "additionalProperties": False,
            },
            capabilities=("command_execution", "async_execution", "process_control"),
        ),
        "web_fetch": ToolSpec(
            name="web_fetch",
            required_args=("url",),
            optional_args=("max_chars",),
            timeout_seconds=20.0,
            max_retries=1,
            description="Fetch and return textual webpage content.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "minLength": 1},
                    "max_chars": {"type": "integer", "minimum": 1},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            capabilities=("web_retrieval", "knowledge_retrieval", "source_grounding"),
        ),
        "web_search": ToolSpec(
            name="web_search",
            required_args=("query",),
            optional_args=("max_results",),
            timeout_seconds=15.0,
            max_retries=1,
            description=(
                "Search the web for information. Returns titles, URLs and snippets. "
                "Use this FIRST when the user asks about current events, facts, documentation, "
                "or anything you're unsure about."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1, "description": "The search query"},
                    "max_results": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "description": "Max results to return (default 5)",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            capabilities=("web_retrieval", "knowledge_retrieval", "source_grounding", "research"),
        ),
        "http_request": ToolSpec(
            name="http_request",
            required_args=("url",),
            optional_args=("method", "headers", "body", "content_type", "max_chars"),
            timeout_seconds=30.0,
            max_retries=1,
            description=(
                "Make an HTTP request with any method (GET/POST/PUT/PATCH/DELETE). "
                "Use for API calls, webhooks, and web services."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "minLength": 1},
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
                    },
                    "headers": {"type": "string", "description": "JSON object of HTTP headers"},
                    "body": {"type": "string", "description": "Request body (JSON string or raw text)"},
                    "content_type": {"type": "string"},
                    "max_chars": {"type": "integer", "minimum": 1},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            capabilities=("web_retrieval", "api_integration", "webhook_execution"),
        ),
        "analyze_image": ToolSpec(
            name="analyze_image",
            required_args=("image_path",),
            optional_args=("prompt",),
            timeout_seconds=30.0,
            max_retries=0,
            description=(
                "Analyze an image file using vision AI. "
                "Describe contents, extract text (OCR), identify UI elements."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Path to the image file",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Specific question about the image (default: general description)",
                    },
                },
                "required": ["image_path"],
                "additionalProperties": False,
            },
            capabilities=("vision", "image_analysis", "ocr", "ui_testing"),
        ),
        "spawn_subrun": ToolSpec(
            name="spawn_subrun",
            required_args=("message",),
            optional_args=("mode", "agent_id", "model", "timeout_seconds", "tool_policy"),
            timeout_seconds=6.0,
            max_retries=0,
            description="Spawn an isolated subrun with optional mode, agent, model, timeout and policy.",
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "minLength": 1},
                    "mode": {"type": "string", "enum": ["run", "wait"]},
                    "agent_id": {"type": "string", "minLength": 1},
                    "model": {"type": "string", "minLength": 1},
                    "timeout_seconds": {"type": "integer", "minimum": 1},
                    "tool_policy": {
                        "type": "object",
                        "description": "Restrict or expand tools available to the spawned subrun. Use 'allow' to whitelist, 'deny' to blacklist tool names.",
                        "properties": {
                            "allow": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Tool names the subrun is allowed to use.",
                            },
                            "deny": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Tool names the subrun must not use.",
                            },
                        },
                        "additionalProperties": False,
                    },
                },
                "required": ["message"],
                "additionalProperties": False,
            },
            capabilities=("agent_delegation", "orchestration", "parallelization"),
        ),
    }


class ToolRegistryFactory:
    @staticmethod
    def build(
        *,
        tooling: object | None,
        allowed_tools: set[str] | None,
        command_timeout_seconds: int,
        mcp_bridge: object | None = None,
    ) -> ToolRegistry:
        specs = _default_tool_specs(command_timeout_seconds=command_timeout_seconds)
        registry = ToolRegistry()
        for name, spec in specs.items():
            if allowed_tools is not None and name not in allowed_tools:
                continue
            dispatcher = getattr(tooling, name, None) if tooling is not None else None
            registry.register(spec, dispatcher=dispatcher)

        if mcp_bridge is not None:
            for spec in mcp_bridge.get_tool_specs():
                if allowed_tools is not None and spec.name not in allowed_tools:
                    continue
                registry.register(spec, dispatcher=_build_dynamic_dispatcher(mcp_bridge, spec.name))
        return registry


def build_default_tool_registry(*, command_timeout_seconds: int) -> ToolRegistry:
    return ToolRegistryFactory.build(
        tooling=None,
        allowed_tools=None,
        command_timeout_seconds=command_timeout_seconds,
        mcp_bridge=None,
    )
