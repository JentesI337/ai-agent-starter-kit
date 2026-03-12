"""State persistence domain.
Only imports from shared/ and config/ — no other domain imports.
"""
from app.state.encryption import decrypt_state, encrypt_state, sign_policy_file, verify_policy_file
from app.state.snapshots import build_summary_snapshot
from app.state.state_store import SqliteStateStore, StateStore
from app.state.task_graph import TaskGraph, TaskNode, TaskStatus

__all__ = [
    "SqliteStateStore",
    "StateStore",
    "TaskGraph",
    "TaskNode",
    "TaskStatus",
    "build_summary_snapshot",
    "decrypt_state",
    "encrypt_state",
    "sign_policy_file",
    "verify_policy_file",
]
