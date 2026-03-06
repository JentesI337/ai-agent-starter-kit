from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from threading import RLock


@dataclass
class MemoryItem:
    role: str
    content: str


class MemoryStore:
    def __init__(self, max_items_per_session: int = 20, persist_dir: str | None = None):
        self.max_items_per_session = max_items_per_session
        self._store: dict[str, deque[MemoryItem]] = {}
        self._lock = RLock()
        self.persist_dir = Path(persist_dir).resolve() if persist_dir else None
        if self.persist_dir:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def add(self, session_id: str, role: str, content: str) -> None:
        key = self._normalize_session_id(session_id)
        with self._lock:
            if key not in self._store:
                self._store[key] = deque(maxlen=self.max_items_per_session)
            self._store[key].append(MemoryItem(role=role, content=content))
            self._append_to_disk(session_id=key, role=role, content=content)

    def render_context(self, session_id: str) -> str:
        key = self._normalize_session_id(session_id)
        with self._lock:
            items = list(self._store.get(key, deque()))
        if not items:
            return "(no previous context)"
        lines = [f"- {item.role}: {item.content}" for item in items]
        return "\n".join(lines)

    def get_items(self, session_id: str) -> list[MemoryItem]:
        key = self._normalize_session_id(session_id)
        with self._lock:
            items = self._store.get(key, deque())
            return list(items)

    def repair_orphaned_tool_calls(self, session_id: str) -> int:
        key = self._normalize_session_id(session_id)
        with self._lock:
            items = list(self._store.get(key, deque()))
            if not items:
                return 0

            repaired = 0
            pending_tool_calls: set[str] = set()
            repaired_items: list[MemoryItem] = []

            for item in items:
                if item.role == "assistant":
                    pending_tool_calls.update(self._extract_tool_call_ids(item.content))
                    repaired_items.append(item)
                    continue

                if item.role.startswith("tool:"):
                    call_id = self._extract_tool_call_id(item.content)
                    if call_id and call_id in pending_tool_calls:
                        pending_tool_calls.discard(call_id)
                    repaired_items.append(item)
                    continue

                if item.role == "user" and pending_tool_calls:
                    for orphan_id in sorted(pending_tool_calls):
                        synthetic_item = MemoryItem(
                            role="tool:__synthetic__",
                            content=json.dumps(
                                {
                                    "tool_call_id": orphan_id,
                                    "role": "tool",
                                    "isError": True,
                                    "content": "[tool execution was interrupted — no result available]",
                                },
                                ensure_ascii=False,
                            ),
                        )
                        repaired_items.append(synthetic_item)
                        repaired += 1
                    pending_tool_calls.clear()

                repaired_items.append(item)

            if pending_tool_calls:
                for orphan_id in sorted(pending_tool_calls):
                    synthetic_item = MemoryItem(
                        role="tool:__synthetic__",
                        content=json.dumps(
                            {
                                "tool_call_id": orphan_id,
                                "role": "tool",
                                "isError": True,
                                "content": "[tool execution was interrupted — no result available]",
                            },
                            ensure_ascii=False,
                        ),
                    )
                    repaired_items.append(synthetic_item)
                    repaired += 1
                pending_tool_calls.clear()

            if repaired > 0:
                self._store[key] = deque(repaired_items, maxlen=self.max_items_per_session)
                self._rewrite_session_file(session_id=key)

            return repaired

    def sanitize_session_history(self, session_id: str) -> int:
        key = self._normalize_session_id(session_id)
        with self._lock:
            items = list(self._store.get(key, deque()))
            if not items:
                return 0

            original_len = len(items)
            valid_items: list[MemoryItem] = []
            last_conversation_role: str | None = None

            for item in items:
                if item.role in ("user", "assistant"):
                    if item.role == last_conversation_role:
                        continue
                    last_conversation_role = item.role
                elif item.role.startswith("tool:") or item.role == "plan":
                    last_conversation_role = None
                valid_items.append(item)

            removed = original_len - len(valid_items)
            if removed > 0:
                self._store[key] = deque(valid_items, maxlen=self.max_items_per_session)
                self._rewrite_session_file(session_id=key)
            return removed

    def clear_all(self, *, caller_session_id: str | None = None) -> None:
        """Clear all in-memory sessions and optionally remove persisted files.

        SEC (MEM-02): *caller_session_id* is accepted for audit logging.
        In a multi-user setup this would enforce authorization; in the
        current single-user POC it is logged for traceability.
        """
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            "memory.clear_all invoked (caller_session=%s)",
            caller_session_id or "<unknown>",
        )
        with self._lock:
            self._store.clear()
            if not self.persist_dir:
                return
            for file_path in self.persist_dir.glob("*.jsonl"):
                try:
                    file_path.unlink(missing_ok=True)
                except Exception:
                    continue

    def _load_from_disk(self) -> None:
        if not self.persist_dir:
            return

        with self._lock:
            for file_path in self.persist_dir.glob("*.jsonl"):
                session_id: str | None = None
                for line in file_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        payload = json.loads(line)
                        # SEC (MEM-03): Prefer session_id embedded in record
                        # for hashed-filename recovery; fall back to file stem.
                        if session_id is None:
                            session_id = str(payload.get("session_id", "")).strip() or file_path.stem
                        role = str(payload.get("role", "")).strip()
                        content = str(payload.get("content", ""))
                        if not role:
                            continue
                        if session_id not in self._store:
                            self._store[session_id] = deque(maxlen=self.max_items_per_session)
                        self._store[session_id].append(MemoryItem(role=role, content=content))
                    except Exception:
                        continue

    def _append_to_disk(self, session_id: str, role: str, content: str) -> None:
        if not self.persist_dir:
            return

        # SEC (MEM-03): Hash session ID for filenames to prevent enumeration
        file_path = self.persist_dir / f"{self._hash_session_id(session_id)}.jsonl"
        # Embed session_id in record so _load_from_disk can recover the mapping
        record = json.dumps(
            {"session_id": session_id, "role": role, "content": content},
            ensure_ascii=False,
        )
        with file_path.open("a", encoding="utf-8") as handle:
            handle.write(record + "\n")

        self._trim_file(file_path)

    def _normalize_session_id(self, session_id: str) -> str:
        safe_session_id = "".join(ch for ch in session_id if ch.isalnum() or ch in ("-", "_", "."))
        return safe_session_id or "session"

    def _trim_file(self, file_path: Path) -> None:
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return

        if len(lines) <= self.max_items_per_session:
            return

        trimmed = lines[-self.max_items_per_session :]
        file_path.write_text("\n".join(trimmed) + "\n", encoding="utf-8")

    @staticmethod
    def _extract_tool_call_ids(content: str) -> set[str]:
        source = str(content or "")
        try:
            payload = json.loads(source)
        except Exception:
            payload = None

        if isinstance(payload, dict):
            tool_calls = payload.get("tool_calls")
            if isinstance(tool_calls, list):
                ids = {
                    str(item.get("id", "")).strip()
                    for item in tool_calls
                    if isinstance(item, dict)
                }
                return {item for item in ids if item}

        tool_calls_match = re.search(r'"tool_calls"\s*:\s*\[(.*?)\]', source, flags=re.DOTALL)
        if not tool_calls_match:
            return set()

        ids = set(re.findall(r'"id"\s*:\s*"([^"]+)"', tool_calls_match.group(1)))
        return {item.strip() for item in ids if item.strip()}

    @staticmethod
    def _extract_tool_call_id(content: str) -> str | None:
        source = str(content or "")
        match = re.search(r'"tool_call_id"\s*:\s*"([^"]+)"', source)
        if match:
            return match.group(1).strip() or None
        return None

    def _rewrite_session_file(self, *, session_id: str) -> None:
        if not self.persist_dir:
            return

        # SEC (MEM-03): Use hashed filename
        file_path = self.persist_dir / f"{self._hash_session_id(session_id)}.jsonl"
        items = list(self._store.get(session_id, deque()))
        if not items:
            file_path.unlink(missing_ok=True)
            return

        lines = [
            json.dumps(
                {"session_id": session_id, "role": item.role, "content": item.content},
                ensure_ascii=False,
            )
            for item in items
        ]
        file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _hash_session_id(session_id: str) -> str:
        """SEC (MEM-03): Hash session ID for filenames to prevent enumeration."""
        return hashlib.sha256(session_id.encode()).hexdigest()[:16]
