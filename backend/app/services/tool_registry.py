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
            resolved_retry_class = "transient" if name in {"run_command", "web_fetch"} else "none"
        return ToolExecutionPolicy(
            retry_class=resolved_retry_class,
            timeout_seconds=spec.timeout_seconds,
            max_retries=spec.max_retries,
        )


def _default_tool_specs(*, command_timeout_seconds: int) -> dict[str, ToolSpec]:
    return {
        "list_dir": ToolSpec(
            name="list_dir",
            required_args=(),
            optional_args=("path",),
            timeout_seconds=6.0,
            max_retries=0,
        ),
        "read_file": ToolSpec(
            name="read_file",
            required_args=("path",),
            optional_args=(),
            timeout_seconds=8.0,
            max_retries=0,
        ),
        "write_file": ToolSpec(
            name="write_file",
            required_args=("path", "content"),
            optional_args=(),
            timeout_seconds=10.0,
            max_retries=0,
        ),
        "run_command": ToolSpec(
            name="run_command",
            required_args=("command",),
            optional_args=("cwd",),
            timeout_seconds=float(max(3, command_timeout_seconds)),
            max_retries=1,
        ),
        "apply_patch": ToolSpec(
            name="apply_patch",
            required_args=("path", "search", "replace"),
            optional_args=("replace_all",),
            timeout_seconds=10.0,
            max_retries=0,
        ),
        "file_search": ToolSpec(
            name="file_search",
            required_args=("pattern",),
            optional_args=("max_results",),
            timeout_seconds=6.0,
            max_retries=0,
        ),
        "grep_search": ToolSpec(
            name="grep_search",
            required_args=("query",),
            optional_args=("include_pattern", "is_regexp", "max_results"),
            timeout_seconds=8.0,
            max_retries=0,
        ),
        "list_code_usages": ToolSpec(
            name="list_code_usages",
            required_args=("symbol",),
            optional_args=("include_pattern", "max_results"),
            timeout_seconds=8.0,
            max_retries=0,
        ),
        "get_changed_files": ToolSpec(
            name="get_changed_files",
            required_args=(),
            optional_args=(),
            timeout_seconds=8.0,
            max_retries=0,
        ),
        "start_background_command": ToolSpec(
            name="start_background_command",
            required_args=("command",),
            optional_args=("cwd",),
            timeout_seconds=6.0,
            max_retries=0,
        ),
        "get_background_output": ToolSpec(
            name="get_background_output",
            required_args=("job_id",),
            optional_args=("tail_lines",),
            timeout_seconds=5.0,
            max_retries=0,
        ),
        "kill_background_process": ToolSpec(
            name="kill_background_process",
            required_args=("job_id",),
            optional_args=(),
            timeout_seconds=5.0,
            max_retries=0,
        ),
        "web_fetch": ToolSpec(
            name="web_fetch",
            required_args=("url",),
            optional_args=("max_chars",),
            timeout_seconds=20.0,
            max_retries=1,
        ),
        "spawn_subrun": ToolSpec(
            name="spawn_subrun",
            required_args=("message",),
            optional_args=("mode", "agent_id", "model", "timeout_seconds", "tool_policy"),
            timeout_seconds=6.0,
            max_retries=0,
        ),
    }


class ToolRegistryFactory:
    @staticmethod
    def build(
        *,
        tooling: object | None,
        allowed_tools: set[str] | None,
        command_timeout_seconds: int,
    ) -> ToolRegistry:
        specs = _default_tool_specs(command_timeout_seconds=command_timeout_seconds)
        registry = ToolRegistry()
        for name, spec in specs.items():
            if allowed_tools is not None and name not in allowed_tools:
                continue
            dispatcher = getattr(tooling, name, None) if tooling is not None else None
            registry.register(spec, dispatcher=dispatcher)
        return registry


def build_default_tool_registry(*, command_timeout_seconds: int) -> ToolRegistry:
    return ToolRegistryFactory.build(
        tooling=None,
        allowed_tools=None,
        command_timeout_seconds=command_timeout_seconds,
    )
