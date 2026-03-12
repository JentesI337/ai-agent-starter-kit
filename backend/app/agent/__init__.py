"""Agent domain — core agent execution.

Proxy package: propagates attribute sets (e.g. from unittest.mock.patch)
to app.agent.head_agent so that patch("app.agent.settings") works.
"""
import sys
import types


class _AgentPackage(types.ModuleType):
    _head_agent_mod = None
    _originals: dict = {}

    def _ensure_head_agent(self):
        if self._head_agent_mod is None:
            import importlib
            mod = importlib.import_module("app.agent.head_agent")
            object.__setattr__(self, "_head_agent_mod", mod)
            # Snapshot originals for restoration on delattr
            for name in ("settings",):
                if name in mod.__dict__:
                    self._originals[name] = mod.__dict__[name]
        return self._head_agent_mod

    def __getattr__(self, name):
        if name == "HeadAgent":
            return self._ensure_head_agent().HeadAgent
        if name == "settings":
            from app.config import settings
            return settings
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    def __setattr__(self, name, value):
        # Store locally so getattr finds it without hitting __getattr__
        super().__setattr__(name, value)
        if name == "settings":
            # Propagate to head_agent so the actual code sees the change
            try:
                ha = self._ensure_head_agent()
                setattr(ha, "settings", value)
            except Exception:
                pass

    def __delattr__(self, name):
        # mock.patch calls delattr on cleanup when the attr was not in __dict__
        # originally. Clean up the proxy and restore the real module's original.
        try:
            super().__delattr__(name)
        except AttributeError:
            pass
        if name in self._originals:
            try:
                ha = self._ensure_head_agent()
                setattr(ha, "settings", self._originals[name])
            except Exception:
                pass


_pkg = _AgentPackage(__name__)
_pkg.__file__ = __file__
_pkg.__path__ = [__path__[0]] if isinstance(__path__, list) else list(__path__)
_pkg.__package__ = __package__
_pkg.__all__ = ["HeadAgent", "settings"]
sys.modules[__name__] = _pkg
