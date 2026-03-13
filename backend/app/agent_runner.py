# DEPRECATED: moved to app.agent.runner (Phase 12)
# Proxy module that propagates attribute sets (e.g. from unittest.mock.patch)
# to app.agent.runner so that patch("app.agent_runner.settings") works.
import contextlib
import sys
import types

import app.agent.runner as _real_module

# Snapshot original bindings that may be patched (before any test overrides)
_originals: dict[str, object] = {}
for _name in ("settings",):
    if _name in _real_module.__dict__:
        _originals[_name] = _real_module.__dict__[_name]


class _ProxyModule(types.ModuleType):
    def __getattr__(self, name):
        return getattr(_real_module, name)

    def __setattr__(self, name, value):
        # Store locally so getattr finds it without hitting __getattr__
        super().__setattr__(name, value)
        # Propagate to real module so the actual code sees the change
        setattr(_real_module, name, value)

    def __delattr__(self, name):
        # mock.patch calls delattr on cleanup when the attr was not in __dict__
        # originally. Clean up the proxy and restore the real module's original.
        with contextlib.suppress(AttributeError):
            super().__delattr__(name)
        if name in _originals:
            setattr(_real_module, name, _originals[name])


_proxy = _ProxyModule(__name__)
_proxy.__file__ = __file__
_proxy.__package__ = __package__
sys.modules[__name__] = _proxy
