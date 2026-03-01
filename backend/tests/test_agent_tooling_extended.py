from __future__ import annotations

from pathlib import Path
import sys
from urllib.error import HTTPError

from app.tools import AgentTooling


def test_apply_patch_replaces_single_match(tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))
    target = tmp_path / "demo.txt"
    target.write_text("hello world\nsecond line\n", encoding="utf-8")

    result = tooling.apply_patch(path="demo.txt", search="hello world", replace="hi world")

    assert "replacements=1" in result
    assert target.read_text(encoding="utf-8") == "hi world\nsecond line\n"


def test_file_and_grep_search_find_expected_entries(tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "a.py").write_text("def my_symbol():\n    return 1\n", encoding="utf-8")
    (tmp_path / "src" / "b.py").write_text("print('hello')\n", encoding="utf-8")

    file_matches = tooling.file_search(pattern="src/*.py", max_results=10)
    grep_matches = tooling.grep_search(query="my_symbol", include_pattern="src/*.py", is_regexp=False, max_results=10)
    usage_matches = tooling.list_code_usages(symbol="my_symbol", include_pattern="src/*.py", max_results=10)

    assert "src/a.py" in file_matches
    assert "src/b.py" in file_matches
    assert "src/a.py" in grep_matches
    assert "src/a.py" in usage_matches


def test_background_process_start_read_and_kill(tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    command = f'"{sys.executable}" -c "import time; print(\"started\"); time.sleep(5); print(\"done\")"'
    started = tooling.start_background_command(command=command)
    job_id = started.split("job_id=")[1].split()[0]

    output_before = tooling.get_background_output(job_id=job_id, tail_lines=20)
    assert f"job_id={job_id}" in output_before

    killed = tooling.kill_background_process(job_id=job_id)
    assert job_id in killed


def test_web_fetch_formats_html_with_source_metadata(monkeypatch, tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    class _FakeResponse:
        def __init__(self) -> None:
            self.headers = {"Content-Type": "text/html; charset=utf-8"}

        def read(self, _size: int) -> bytes:
            return (
                b"<html><head><title>Best LLMs 2026</title><style>.x{}</style></head>"
                b"<body><script>ignored()</script><h1>Rankings</h1><p>Model A leads.</p></body></html>"
            )

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.tools.urlopen", lambda *_args, **_kwargs: _FakeResponse())

    result = tooling.web_fetch("https://example.com/models", max_chars=4000)

    assert "source_url: https://example.com/models" in result
    assert "content_type: text/html; charset=utf-8" in result
    assert "Best LLMs 2026" in result
    assert "Model A leads." in result
    assert "<script>" not in result


def test_web_fetch_rejects_non_http_scheme(tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    try:
        tooling.web_fetch("file:///etc/passwd")
        assert False, "Expected ToolExecutionError"
    except Exception as exc:
        assert "http/https" in str(exc)


def test_web_fetch_error_contains_source_url(monkeypatch, tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    def _raise_http_error(*_args, **_kwargs):
        raise HTTPError(url="https://example.com/missing", code=404, msg="Not Found", hdrs=None, fp=None)

    monkeypatch.setattr("app.tools.urlopen", _raise_http_error)

    try:
        tooling.web_fetch("https://example.com/missing")
        assert False, "Expected ToolExecutionError"
    except Exception as exc:
        text = str(exc)
        assert "web_fetch failed for url=https://example.com/missing" in text
        assert "404" in text
