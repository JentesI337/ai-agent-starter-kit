from __future__ import annotations

import os
import time

from app.state import StateStore


def test_list_runs_keeps_newest_order_with_limit(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))

    run_ids = ["run-a", "run-b", "run-c"]
    for run_id in run_ids:
        store.init_run(
            run_id=run_id,
            session_id="sess-1",
            request_id=run_id,
            user_message="hello",
            runtime="local",
            model="llama",
        )

    base = time.time()
    for offset, run_id in enumerate(run_ids, start=1):
        run_file = store._run_file(run_id)
        ts = base + float(offset)
        os.utime(run_file, (ts, ts))

    runs = store.list_runs(limit=2)

    assert len(runs) == 2
    assert runs[0]["run_id"] == "run-c"
    assert runs[1]["run_id"] == "run-b"


def test_list_runs_handles_stale_index_entries(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))

    for run_id in ("run-1", "run-2"):
        store.init_run(
            run_id=run_id,
            session_id="sess-1",
            request_id=run_id,
            user_message="hello",
            runtime="local",
            model="llama",
        )

    _ = store.list_runs(limit=10)

    deleted_path = store._run_file("run-2")
    deleted_path.unlink(missing_ok=True)

    runs = store.list_runs(limit=10)
    run_ids = {item.get("run_id") for item in runs}

    assert "run-2" not in run_ids
    assert "run-1" in run_ids
