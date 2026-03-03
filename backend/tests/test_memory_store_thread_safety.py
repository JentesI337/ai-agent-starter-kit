from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.memory import MemoryStore


def test_memory_store_add_is_thread_safe(tmp_path) -> None:
    store = MemoryStore(max_items_per_session=1000, persist_dir=str(tmp_path))
    session_id = "thread-safe-session"
    workers = 8
    per_worker = 50

    def _write_batch(worker_id: int) -> None:
        for index in range(per_worker):
            store.add(session_id, "user", f"w{worker_id}-{index}")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(_write_batch, range(workers)))

    items = store.get_items(session_id)
    assert len(items) == workers * per_worker

    persisted_file = tmp_path / f"{session_id}.jsonl"
    assert persisted_file.exists()
    lines = [line for line in persisted_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == workers * per_worker
