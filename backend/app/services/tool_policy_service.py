# DEPRECATED: moved to app.tools.provisioning.policy_service (Phase 10)
# Uses lazy __getattr__ to avoid circular import:
# policy_service → app.config → app.services.__init__ → tool_policy_service
import importlib as _importlib


def __getattr__(name):
    _mod = _importlib.import_module("app.tools.provisioning.policy_service")
    return getattr(_mod, name)
