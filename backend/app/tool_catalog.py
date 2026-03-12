# DEPRECATED: Moved to app.tools.catalog (Phase 09)
# Lazy re-export to avoid circular imports during app.config init.
import importlib as _importlib


def __getattr__(name: str):
    _mod = _importlib.import_module("app.tools.catalog")
    return getattr(_mod, name)
