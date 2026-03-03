from __future__ import annotations

from collections.abc import Awaitable, Callable
from weakref import WeakMethod

from app.contracts.agent_contract import SendEvent

ExecuteToolsFn = Callable[[str, str, str, str, str, SendEvent, str | None, set[str], Callable[[], bool] | None], Awaitable[str]]


class LegacyRunnerBinding:
    def __init__(self, execute_tools_fn: ExecuteToolsFn):
        is_bound_method = getattr(execute_tools_fn, "__self__", None) is not None and getattr(
            execute_tools_fn,
            "__func__",
            None,
        ) is not None
        if is_bound_method:
            self._runner: ExecuteToolsFn | WeakMethod = WeakMethod(execute_tools_fn)
        else:
            self._runner = execute_tools_fn

    def resolve(self) -> ExecuteToolsFn | None:
        if isinstance(self._runner, WeakMethod):
            return self._runner()
        return self._runner
