# DEPRECATED: agent code moved to app.agent.* (Phase 12)
# Backward compat re-exports:
from app.agent.adapter import *  # noqa: F401, F403
from app.agent.store import *  # noqa: F401, F403
from app.agent.record import *  # noqa: F401, F403
from app.agent.factory_defaults import *  # noqa: F401, F403

__all__ = [
    "CoderAgentAdapter",
    "HeadAgentAdapter",
]
