"""Session domain — inbox, query, security, and compaction services."""

from app.session.inbox_service import InboxMessage, SessionInboxService
from app.session.security import (
    generate_session_id,
    validate_session_id,
    validate_session_id_format,
)

# Lazy imports for modules with heavy dependency chains (config, state).
# Access via app.session.compaction or app.session.query_service directly.


def __getattr__(name: str):  # noqa: N807
    if name in (
        "CHARS_PER_TOKEN",
        "COMPACTION_SAFETY_MARGIN",
        "COMPACTION_TRIGGER_RATIO",
        "CompactionService",
        "estimate_messages_tokens",
        "estimate_tokens",
    ):
        from app.session import compaction as _compaction

        return getattr(_compaction, name)

    if name == "SessionQueryService":
        from app.session.query_service import SessionQueryService

        return SessionQueryService

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CHARS_PER_TOKEN",
    "COMPACTION_SAFETY_MARGIN",
    "COMPACTION_TRIGGER_RATIO",
    "CompactionService",
    "InboxMessage",
    "SessionInboxService",
    "SessionQueryService",
    "estimate_messages_tokens",
    "estimate_tokens",
    "generate_session_id",
    "validate_session_id",
    "validate_session_id_format",
]
