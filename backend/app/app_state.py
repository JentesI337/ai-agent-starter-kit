from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator, MutableMapping
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class RuntimeComponents:
    agent_registry: dict[str, Any]
    runtime_manager: Any
    state_store: Any
    session_query_service: Any
    policy_approval_service: Any
    orchestrator_registry: dict[str, Any]
    agent_store: Any
    custom_agent_ids: set[str] = field(default_factory=set)
    custom_orchestrator_agent_ids: set[str] = field(default_factory=set)
    agent: Any | None = None
    orchestrator_api: Any | None = None
    subrun_lane: Any | None = None
    model_health_tracker: Any | None = None
    circuit_breaker: Any | None = None
    policy_approval_handler: Any | None = None
    _custom_agent_store_compat: Any | None = field(default=None, repr=False)

    @property
    def custom_agent_store(self) -> Any:
        """Backward-compatible accessor — wraps UnifiedAgentStore."""
        if self._custom_agent_store_compat is None:
            from app.agents.agent_store import CustomAgentStoreCompat
            self._custom_agent_store_compat = CustomAgentStoreCompat(self.agent_store)
        return self._custom_agent_store_compat


@dataclass
class ControlPlaneState:
    active_run_tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    workflow_version_registry: dict[str, int] = field(default_factory=dict)
    workflow_version_lock: Lock = field(default_factory=Lock)


class LazyObjectProxy:
    def __init__(self, resolver: Callable[[], Any]):
        object.__setattr__(self, "_resolver", resolver)

    def _resolve(self):
        return object.__getattribute__(self, "_resolver")()

    def __getattr__(self, item):
        return getattr(self._resolve(), item)

    def __setattr__(self, key, value):
        setattr(self._resolve(), key, value)

    def __repr__(self) -> str:
        return repr(self._resolve())


class LazyMappingProxy(MutableMapping):
    def __init__(self, resolver: Callable[[], MutableMapping]):
        self._resolver = resolver

    def _mapping(self) -> MutableMapping:
        return self._resolver()

    def __getitem__(self, key):
        return self._mapping()[key]

    def __setitem__(self, key, value):
        self._mapping()[key] = value

    def __delitem__(self, key):
        del self._mapping()[key]

    def __iter__(self) -> Iterator:
        return iter(self._mapping())

    def __len__(self) -> int:
        return len(self._mapping())

    def __repr__(self) -> str:
        return repr(dict(self._mapping()))


class LazyRuntimeRegistry:
    def __init__(
        self,
        *,
        builder: Callable[[], RuntimeComponents],
        initializer: Callable[[RuntimeComponents], None] | None = None,
    ):
        self._builder = builder
        self._initializer = initializer
        self._components: RuntimeComponents | None = None
        self._lock = Lock()

    def get_components(self) -> RuntimeComponents:
        if self._components is not None:
            return self._components

        with self._lock:
            if self._components is None:
                components = self._builder()
                if self._initializer is not None:
                    self._initializer(components)
                self._components = components

        return self._components

    def ensure_initialized(self) -> RuntimeComponents:
        return self.get_components()
