from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


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

    # Tools that are safe to retry on transient errors (idempotent / read-only).
    # Mutating tools like run_command are excluded — they must NOT be blindly retried.
    _TRANSIENT_RETRY_TOOLS: frozenset[str] = frozenset({
        "web_fetch", "web_search", "http_request",
        "list_dir", "read_file", "file_search", "grep_search",
        "list_code_usages", "get_changed_files", "get_background_output",
        "analyze_image",
    })

    def build_execution_policy(self, name: str, *, retry_class: str | None = None) -> ToolExecutionPolicy:
        spec = self._specs[name]
        resolved_retry_class = retry_class
        if resolved_retry_class is None:
            resolved_retry_class = "transient" if name in self._TRANSIENT_RETRY_TOOLS else "none"
        # Read-only tools and network tools get at least 2 retries if spec says 0
        resolved_max_retries = spec.max_retries
        if resolved_retry_class == "transient" and resolved_max_retries == 0:
            resolved_max_retries = 2
        # MCP tools always get transient retry
        if name.startswith("mcp_") and resolved_retry_class == "none":
            resolved_retry_class = "transient"
            resolved_max_retries = max(resolved_max_retries, 2)
        return ToolExecutionPolicy(
            retry_class=resolved_retry_class,
            timeout_seconds=spec.timeout_seconds,
            max_retries=resolved_max_retries,
        )

    def build_function_calling_tools(
        self,
        *,
        allowed_tools: set[str] | None = None,
        provider: str = "openai",
    ) -> list[dict[str, Any]]:
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
        if provider == "gemini":
            return [self._normalize_schema_gemini(d) for d in definitions]
        if provider in ("anthropic", "claude"):
            return [self._normalize_schema_anthropic(d) for d in definitions]
        return definitions

    # ── Provider-specific schema normalization ─────────────────────────
    _GEMINI_STRIP_KEYS: frozenset[str] = frozenset({
        "format", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
        "minLength", "maxLength", "minItems", "maxItems", "pattern",
    })

    @classmethod
    def _normalize_schema_gemini(cls, tool_def: dict[str, Any]) -> dict[str, Any]:
        """Strip JSON Schema fields that Gemini rejects."""
        import copy
        result = copy.deepcopy(tool_def)
        params = result.get("function", {}).get("parameters")
        if isinstance(params, dict):
            cls._strip_keys_recursive(params, cls._GEMINI_STRIP_KEYS)
        return result

    @classmethod
    def _strip_keys_recursive(cls, schema: dict[str, Any], keys_to_strip: frozenset[str]) -> None:
        for key in list(schema.keys()):
            if key in keys_to_strip:
                del schema[key]
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for prop_schema in properties.values():
                if isinstance(prop_schema, dict):
                    cls._strip_keys_recursive(prop_schema, keys_to_strip)
        items = schema.get("items")
        if isinstance(items, dict):
            cls._strip_keys_recursive(items, keys_to_strip)
        for key in ("anyOf", "oneOf", "allOf"):
            variants = schema.get(key)
            if isinstance(variants, list):
                for variant in variants:
                    if isinstance(variant, dict):
                        cls._strip_keys_recursive(variant, keys_to_strip)

    @staticmethod
    def _normalize_schema_anthropic(tool_def: dict[str, Any]) -> dict[str, Any]:
        """Patch root-level anyOf/oneOf unions that Anthropic rejects."""
        import copy
        result = copy.deepcopy(tool_def)
        params = result.get("function", {}).get("parameters")
        if isinstance(params, dict):
            # Anthropic doesn't accept root-level anyOf — take the first object variant
            for union_key in ("anyOf", "oneOf"):
                variants = params.get(union_key)
                if isinstance(variants, list) and variants:
                    # Find the first object-type variant
                    for variant in variants:
                        if isinstance(variant, dict) and variant.get("type") == "object":
                            params.clear()
                            params.update(variant)
                            break
                    else:
                        # No object variant found — wrap as object
                        params.clear()
                        params.update({"type": "object", "properties": {}, "required": []})
                    break
        return result

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
            optional_args=("encoding",),
            timeout_seconds=10.0,
            max_retries=0,
            description="Write complete content to a file path.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "content": {"type": "string"},
                    "encoding": {
                        "type": "string",
                        "enum": ["utf-8", "base64"],
                        "description": "Use 'utf-8' (default) for text, 'base64' for binary files.",
                    },
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
            optional_args=("language", "timeout", "max_output_chars", "strategy", "persistent", "session_id"),
            timeout_seconds=45.0,
            max_retries=0,
            description=(
                "Execute code in a sandboxed environment. "
                "Supports python and javascript with timeout and output limits. "
                "Python code runs in a persistent REPL by default — variables, imports, "
                "and function definitions survive across calls. Use session_id for separate state contexts."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "minLength": 1},
                    "language": {"type": "string", "enum": ["python", "javascript", "js"]},
                    "timeout": {"type": "integer", "minimum": 1, "maximum": 60},
                    "max_output_chars": {"type": "integer", "minimum": 500, "maximum": 20000},
                    "strategy": {"type": "string", "enum": ["process", "direct", "docker"]},
                    "persistent": {
                        "type": "boolean",
                        "description": "Use persistent REPL where state survives across calls (default true)",
                    },
                    "session_id": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Session ID for separate state contexts (default: 'default')",
                    },
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
        "parse_pdf": ToolSpec(
            name="parse_pdf",
            required_args=("path",),
            optional_args=(),
            timeout_seconds=30.0,
            max_retries=0,
            description=(
                "Parse a PDF file and extract text, tables, and metadata. "
                "Returns structured content including markdown-formatted tables."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Path to the PDF file (relative to workspace or absolute)",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            capabilities=("pdf_parsing", "document_analysis", "table_extraction"),
        ),
        "transcribe_audio": ToolSpec(
            name="transcribe_audio",
            required_args=("path",),
            optional_args=(),
            timeout_seconds=120.0,
            max_retries=0,
            description=(
                "Transcribe an audio file to text with timestamps. "
                "Supports common audio formats. Max 20 MB, 10 min duration."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Path to the audio file (relative to workspace or absolute)",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            capabilities=("audio_transcription", "speech_to_text"),
        ),
        "generate_image": ToolSpec(
            name="generate_image",
            required_args=("prompt",),
            optional_args=("size",),
            timeout_seconds=60.0,
            max_retries=0,
            description=(
                "Generate an image from a text prompt using DALL-E or StabilityAI. "
                "Returns a JSON object with base64-encoded image data."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 1000,
                        "description": "Text description of the image to generate",
                    },
                    "size": {
                        "type": "string",
                        "description": "Image size (e.g. '1024x1024', '512x512'). Defaults to config.",
                    },
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
            capabilities=("image_generation", "creative"),
        ),
        "generate_audio": ToolSpec(
            name="generate_audio",
            required_args=("text",),
            optional_args=("voice",),
            timeout_seconds=60.0,
            max_retries=0,
            description=(
                "Generate spoken audio from text using text-to-speech. "
                "Returns a JSON object with base64-encoded MP3 audio data."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 4096,
                        "description": "The text to convert to speech.",
                    },
                    "voice": {
                        "type": "string",
                        "enum": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
                        "description": "Voice to use. Defaults to config setting (alloy).",
                    },
                },
                "required": ["text"],
                "additionalProperties": False,
            },
            capabilities=("audio_generation", "text_to_speech", "creative"),
        ),
        "export_pdf": ToolSpec(
            name="export_pdf",
            required_args=("content",),
            optional_args=("path",),
            timeout_seconds=30.0,
            max_retries=0,
            description=(
                "Export markdown content to a PDF file. "
                "Supports tables, code blocks, and basic formatting."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Markdown content to convert to PDF",
                    },
                    "path": {
                        "type": "string",
                        "description": "Output PDF path (relative to workspace). Defaults to 'export.pdf'.",
                    },
                },
                "required": ["content"],
                "additionalProperties": False,
            },
            capabilities=("pdf_generation", "document_export"),
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
        "create_workflow": ToolSpec(
            name="create_workflow",
            required_args=("name", "description", "steps"),
            optional_args=("base_agent_id",),
            timeout_seconds=10.0,
            max_retries=0,
            description="Create a new workflow agent at runtime. The agent is persisted and immediately available for use.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "minLength": 1, "description": "Human-readable workflow name."},
                    "description": {"type": "string", "minLength": 1, "description": "What the workflow does."},
                    "steps": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": 1,
                        "description": "Ordered list of step instructions for the workflow.",
                    },
                    "base_agent_id": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Base agent to derive from. Defaults to head-agent.",
                    },
                },
                "required": ["name", "description", "steps"],
                "additionalProperties": False,
            },
            capabilities=("workflow_management",),
        ),
        "delete_workflow": ToolSpec(
            name="delete_workflow",
            required_args=("workflow_id",),
            optional_args=(),
            timeout_seconds=5.0,
            max_retries=0,
            description="Delete a previously created workflow agent by its ID.",
            parameters={
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "minLength": 1, "description": "The workflow agent ID to delete."},
                },
                "required": ["workflow_id"],
                "additionalProperties": False,
            },
            capabilities=("workflow_management",),
        ),
        # ------------------------------------------------------------------
        # build_workflow (NL → workflow)
        # ------------------------------------------------------------------
        "build_workflow": ToolSpec(
            name="build_workflow",
            required_args=("name", "steps_description"),
            optional_args=("description", "execution_mode"),
            timeout_seconds=15.0,
            max_retries=0,
            description="Create a workflow from a natural language description. Each line in steps_description becomes a workflow step.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "minLength": 1, "description": "Workflow name."},
                    "description": {"type": "string", "description": "Optional description of the workflow."},
                    "steps_description": {
                        "type": "string", "minLength": 1,
                        "description": "Multi-line description of steps. Each line becomes a step.",
                    },
                    "execution_mode": {
                        "type": "string", "enum": ["parallel", "sequential"],
                        "description": "Execution mode. Defaults to sequential.",
                    },
                },
                "required": ["name", "steps_description"],
                "additionalProperties": False,
            },
            capabilities=("workflow_management",),
        ),
        # ------------------------------------------------------------------
        # explore_connector
        # ------------------------------------------------------------------
        "explore_connector": ToolSpec(
            name="explore_connector",
            required_args=("connector_id",),
            optional_args=(),
            timeout_seconds=10.0,
            max_retries=0,
            description="List all available methods and parameters for a configured API connector.",
            parameters={
                "type": "object",
                "properties": {
                    "connector_id": {
                        "type": "string", "minLength": 1,
                        "description": "The connector ID to explore (e.g. 'my-github').",
                    },
                },
                "required": ["connector_id"],
                "additionalProperties": False,
            },
            capabilities=("api_integration",),
        ),
        # ------------------------------------------------------------------
        # code_reset
        # ------------------------------------------------------------------
        "code_reset": ToolSpec(
            name="code_reset",
            required_args=(),
            optional_args=("session_id",),
            timeout_seconds=10.0,
            max_retries=0,
            description="Reset the persistent Python REPL, clearing all state.",
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "minLength": 1},
                },
                "required": [],
                "additionalProperties": False,
            },
            capabilities=("code_execution",),
        ),
        # ------------------------------------------------------------------
        # Browser Control Tools
        # ------------------------------------------------------------------
        "browser_open": ToolSpec(
            name="browser_open",
            required_args=("url",),
            optional_args=("session_id",),
            timeout_seconds=30.0,
            max_retries=1,
            description="Open a URL in the browser. Returns the page title and visible text.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "minLength": 1},
                    "session_id": {"type": "string", "minLength": 1},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            capabilities=("browser_automation", "web_retrieval"),
        ),
        "browser_click": ToolSpec(
            name="browser_click",
            required_args=("selector",),
            optional_args=("session_id",),
            timeout_seconds=15.0,
            max_retries=0,
            description="Click an element identified by CSS selector. Returns updated page text.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "minLength": 1},
                    "session_id": {"type": "string", "minLength": 1},
                },
                "required": ["selector"],
                "additionalProperties": False,
            },
            capabilities=("browser_automation",),
        ),
        "browser_type": ToolSpec(
            name="browser_type",
            required_args=("selector", "text"),
            optional_args=("session_id",),
            timeout_seconds=15.0,
            max_retries=0,
            description="Type text into an input field identified by CSS selector.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "minLength": 1},
                    "text": {"type": "string"},
                    "session_id": {"type": "string", "minLength": 1},
                },
                "required": ["selector", "text"],
                "additionalProperties": False,
            },
            capabilities=("browser_automation",),
        ),
        "browser_screenshot": ToolSpec(
            name="browser_screenshot",
            required_args=(),
            optional_args=("session_id",),
            timeout_seconds=15.0,
            max_retries=0,
            description="Capture a screenshot of the current browser page as Base64 PNG.",
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "minLength": 1},
                },
                "required": [],
                "additionalProperties": False,
            },
            capabilities=("browser_automation", "vision"),
        ),
        "browser_read_dom": ToolSpec(
            name="browser_read_dom",
            required_args=(),
            optional_args=("selector", "session_id"),
            timeout_seconds=15.0,
            max_retries=0,
            description="Read DOM content, optionally filtered by CSS selector.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "minLength": 1},
                    "session_id": {"type": "string", "minLength": 1},
                },
                "required": [],
                "additionalProperties": False,
            },
            capabilities=("browser_automation", "web_retrieval"),
        ),
        "browser_evaluate_js": ToolSpec(
            name="browser_evaluate_js",
            required_args=("code",),
            optional_args=("session_id",),
            timeout_seconds=15.0,
            max_retries=0,
            description="Execute JavaScript in the browser context and return the result.",
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "minLength": 1},
                    "session_id": {"type": "string", "minLength": 1},
                },
                "required": ["code"],
                "additionalProperties": False,
            },
            capabilities=("browser_automation", "code_execution"),
        ),
        # ── Visualization ──────────────────────────────────────────────
        "emit_visualization": ToolSpec(
            name="emit_visualization",
            required_args=("viz_type", "code"),
            optional_args=("title",),
            timeout_seconds=5.0,
            max_retries=0,
            description=(
                "Render a diagram or visualization in the user's UI. "
                "Use viz_type='mermaid' with valid Mermaid syntax. "
                "IMPORTANT: Always wrap node labels in double quotes to avoid parse errors, "
                'e.g. A["My Label"] not A[My Label]. '
                "Supported diagram types: flowchart, sequenceDiagram, classDiagram, erDiagram, gantt, pie. "
                "The diagram is rendered live and the source code is returned for embedding in files."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "viz_type": {
                        "type": "string",
                        "enum": ["mermaid", "svg"],
                        "description": "Visualization format: 'mermaid' for Mermaid diagrams, 'svg' for raw SVG markup.",
                    },
                    "code": {
                        "type": "string",
                        "minLength": 1,
                        "description": "The diagram source code (Mermaid syntax or SVG markup).",
                    },
                    "title": {
                        "type": "string",
                        "description": "Optional title for the visualization.",
                    },
                },
                "required": ["viz_type", "code"],
                "additionalProperties": False,
            },
            capabilities=("visualization", "diagramming"),
        ),
        # ── DevOps: Git tools ────────────────────────────────────────
        "git_log": ToolSpec(
            name="git_log",
            required_args=(),
            optional_args=("path", "max_count", "author", "since", "format"),
            timeout_seconds=15.0,
            max_retries=1,
            description="Show git commit history with optional file, author, and date filters. Returns structured output.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Filter history to a specific file or directory"},
                    "max_count": {"type": "integer", "default": 20, "maximum": 100, "description": "Number of commits to return"},
                    "author": {"type": "string", "description": "Filter by author name or email"},
                    "since": {"type": "string", "description": "Date filter like '2 weeks ago' or '2024-01-01'"},
                    "format": {"type": "string", "enum": ["oneline", "short", "full"], "default": "short"},
                },
                "required": [],
                "additionalProperties": False,
            },
            capabilities=("git_inspection", "code_inspection", "knowledge_retrieval"),
        ),
        "git_diff": ToolSpec(
            name="git_diff",
            required_args=(),
            optional_args=("target", "base", "stat_only"),
            timeout_seconds=15.0,
            max_retries=1,
            description="Show the diff between git refs, or working tree changes. Returns unified diff output.",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "File path, commit hash, or ref like HEAD~3"},
                    "base": {"type": "string", "description": "Base ref to compare against (default: working tree)"},
                    "stat_only": {"type": "boolean", "default": False, "description": "Show only file change stats"},
                },
                "required": [],
                "additionalProperties": False,
            },
            capabilities=("git_inspection", "code_inspection", "knowledge_retrieval"),
        ),
        "git_blame": ToolSpec(
            name="git_blame",
            required_args=("path",),
            optional_args=("start_line", "end_line"),
            timeout_seconds=15.0,
            max_retries=1,
            description="Show line-level git authorship for a file, with optional line range.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1, "description": "File path to blame"},
                    "start_line": {"type": "integer", "description": "Start line number"},
                    "end_line": {"type": "integer", "description": "End line number"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            capabilities=("git_inspection", "code_inspection", "knowledge_retrieval"),
        ),
        "git_show": ToolSpec(
            name="git_show",
            required_args=("ref",),
            optional_args=("stat_only",),
            timeout_seconds=15.0,
            max_retries=1,
            description="Show the details and diff of a specific git commit.",
            parameters={
                "type": "object",
                "properties": {
                    "ref": {"type": "string", "minLength": 1, "description": "Commit hash or ref to inspect"},
                    "stat_only": {"type": "boolean", "default": False, "description": "Show only stat summary"},
                },
                "required": ["ref"],
                "additionalProperties": False,
            },
            capabilities=("git_inspection", "code_inspection", "knowledge_retrieval"),
        ),
        "git_stash": ToolSpec(
            name="git_stash",
            required_args=("action",),
            optional_args=("message",),
            timeout_seconds=15.0,
            max_retries=0,
            description="Manage git stash: save, pop, list, or drop stashed changes.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["save", "pop", "list", "drop"]},
                    "message": {"type": "string", "description": "Stash message (for save action)"},
                },
                "required": ["action"],
                "additionalProperties": False,
            },
            capabilities=("git_inspection", "code_modification"),
        ),
        # ── DevOps: Testing tools ────────────────────────────────────
        "run_tests": ToolSpec(
            name="run_tests",
            required_args=(),
            optional_args=("runner", "path", "filter", "verbose"),
            timeout_seconds=120.0,
            max_retries=0,
            description=(
                "Run test suite with structured output. Auto-detects pytest, jest, mocha, go test, "
                "or cargo test. Returns pass/fail counts, failed test names, and error messages."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "runner": {"type": "string", "enum": ["auto", "pytest", "jest", "mocha", "go", "cargo"], "default": "auto"},
                    "path": {"type": "string", "description": "Specific test file or directory"},
                    "filter": {"type": "string", "description": "Test name pattern (-k for pytest, --testNamePattern for jest)"},
                    "verbose": {"type": "boolean", "default": False},
                },
                "required": [],
                "additionalProperties": False,
            },
            capabilities=("build_and_test", "code_inspection", "command_execution"),
        ),
        "test_coverage": ToolSpec(
            name="test_coverage",
            required_args=(),
            optional_args=("runner", "path"),
            timeout_seconds=180.0,
            max_retries=0,
            description="Run tests with coverage collection. Returns overall and per-file coverage percentages.",
            parameters={
                "type": "object",
                "properties": {
                    "runner": {"type": "string", "enum": ["auto", "pytest", "jest"], "default": "auto"},
                    "path": {"type": "string", "description": "File or directory to measure coverage for"},
                },
                "required": [],
                "additionalProperties": False,
            },
            capabilities=("build_and_test", "code_inspection"),
        ),
        # ── DevOps: Linting tools ────────────────────────────────────
        "lint_check": ToolSpec(
            name="lint_check",
            required_args=(),
            optional_args=("tool", "path", "fix"),
            timeout_seconds=60.0,
            max_retries=0,
            description=(
                "Run linter or type checker with structured diagnostics. Auto-detects eslint, ruff, "
                "mypy, pyright, tsc, or flake8. Returns file, line, severity, message, and rule for each issue."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "tool": {"type": "string", "enum": ["auto", "eslint", "ruff", "flake8", "mypy", "pyright", "tsc"], "default": "auto"},
                    "path": {"type": "string", "description": "File or directory to lint"},
                    "fix": {"type": "boolean", "default": False, "description": "Auto-fix issues where supported"},
                },
                "required": [],
                "additionalProperties": False,
            },
            capabilities=("code_inspection", "static_analysis", "build_and_test"),
        ),
        # ── DevOps: Dependency tools ─────────────────────────────────
        "dependency_audit": ToolSpec(
            name="dependency_audit",
            required_args=(),
            optional_args=("manager", "severity"),
            timeout_seconds=60.0,
            max_retries=0,
            description="Check for known vulnerabilities in project dependencies using npm audit or pip-audit.",
            parameters={
                "type": "object",
                "properties": {
                    "manager": {"type": "string", "enum": ["auto", "npm", "pip"], "default": "auto"},
                    "severity": {"type": "string", "enum": ["low", "moderate", "high", "critical"], "default": "moderate"},
                },
                "required": [],
                "additionalProperties": False,
            },
            capabilities=("security_analysis", "dependency_management"),
        ),
        "dependency_outdated": ToolSpec(
            name="dependency_outdated",
            required_args=(),
            optional_args=("manager",),
            timeout_seconds=60.0,
            max_retries=0,
            description="List outdated packages with current vs latest versions.",
            parameters={
                "type": "object",
                "properties": {
                    "manager": {"type": "string", "enum": ["auto", "npm", "pip"], "default": "auto"},
                },
                "required": [],
                "additionalProperties": False,
            },
            capabilities=("dependency_management", "code_inspection"),
        ),
        "dependency_tree": ToolSpec(
            name="dependency_tree",
            required_args=(),
            optional_args=("manager", "package"),
            timeout_seconds=60.0,
            max_retries=0,
            description="Show the dependency tree, optionally for a specific package.",
            parameters={
                "type": "object",
                "properties": {
                    "manager": {"type": "string", "enum": ["auto", "npm", "pip"], "default": "auto"},
                    "package": {"type": "string", "description": "Show tree for a specific package"},
                },
                "required": [],
                "additionalProperties": False,
            },
            capabilities=("dependency_management", "code_inspection"),
        ),
        # ── DevOps: Debug tools ──────────────────────────────────────
        "parse_errors": ToolSpec(
            name="parse_errors",
            required_args=("error_text",),
            optional_args=("language",),
            timeout_seconds=5.0,
            max_retries=0,
            description=(
                "Parse error output or stack traces into structured format: error type, message, "
                "file locations, call chain. Supports Python, JavaScript/Node, Go, and Rust."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "error_text": {"type": "string", "minLength": 1, "description": "Raw error/stacktrace text to parse"},
                    "language": {"type": "string", "enum": ["auto", "python", "javascript", "go", "rust"], "default": "auto"},
                },
                "required": ["error_text"],
                "additionalProperties": False,
            },
            capabilities=("debugging", "code_inspection", "static_analysis"),
        ),
        # ── DevOps: Security tools ───────────────────────────────────
        "secrets_scan": ToolSpec(
            name="secrets_scan",
            required_args=(),
            optional_args=("path", "tool"),
            timeout_seconds=120.0,
            max_retries=0,
            description="Scan for hardcoded secrets and credentials. Uses gitleaks if available, falls back to built-in regex patterns.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File or directory to scan (default: workspace root)"},
                    "tool": {"type": "string", "enum": ["auto", "gitleaks", "builtin"], "default": "auto"},
                },
                "required": [],
                "additionalProperties": False,
            },
            capabilities=("security_analysis", "code_inspection"),
        ),
        "security_check": ToolSpec(
            name="security_check",
            required_args=(),
            optional_args=("tool", "path", "severity"),
            timeout_seconds=180.0,
            max_retries=0,
            description="Run lightweight SAST analysis using bandit (Python) or semgrep (general). Returns structured security findings.",
            parameters={
                "type": "object",
                "properties": {
                    "tool": {"type": "string", "enum": ["auto", "bandit", "semgrep"], "default": "auto"},
                    "path": {"type": "string", "description": "File or directory to analyze"},
                    "severity": {"type": "string", "enum": ["low", "medium", "high"], "description": "Minimum severity to report"},
                },
                "required": [],
                "additionalProperties": False,
            },
            capabilities=("security_analysis", "static_analysis", "code_inspection"),
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
