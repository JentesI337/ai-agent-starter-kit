from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    session_id: str
    request_id: str
    runtime: str
    model: str
