from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Deque


@dataclass
class MemoryItem:
    role: str
    content: str


class MemoryStore:
    def __init__(self, max_items_per_session: int = 20, persist_dir: str | None = None):
        self.max_items_per_session = max_items_per_session
        self._store: dict[str, Deque[MemoryItem]] = {}
        self.persist_dir = Path(persist_dir).resolve() if persist_dir else None
        if self.persist_dir:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def add(self, session_id: str, role: str, content: str) -> None:
        key = self._normalize_session_id(session_id)
        if key not in self._store:
            self._store[key] = deque(maxlen=self.max_items_per_session)
        self._store[key].append(MemoryItem(role=role, content=content))
        self._append_to_disk(session_id=key, role=role, content=content)

    def render_context(self, session_id: str) -> str:
        key = self._normalize_session_id(session_id)
        items = self._store.get(key, deque())
        if not items:
            return "(no previous context)"
        lines = [f"- {item.role}: {item.content}" for item in items]
        return "\n".join(lines)

    def _load_from_disk(self) -> None:
        if not self.persist_dir:
            return

        for file_path in self.persist_dir.glob("*.jsonl"):
            session_id = file_path.stem
            for line in file_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                    role = str(payload.get("role", "")).strip()
                    content = str(payload.get("content", "")).strip()
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

        file_path = self.persist_dir / f"{session_id}.jsonl"
        record = json.dumps({"role": role, "content": content}, ensure_ascii=False)
        with file_path.open("a", encoding="utf-8") as handle:
            handle.write(record + "\n")

        self._trim_file(file_path)

    def _normalize_session_id(self, session_id: str) -> str:
        safe_session_id = "".join(ch for ch in session_id if ch.isalnum() or ch in ("-", "_"))
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
