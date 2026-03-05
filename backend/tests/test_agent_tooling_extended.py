from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import socket
import subprocess

import pytest

from app.errors import ToolExecutionError
from app.tools import AgentTooling
import app.tools as tools_module


def test_apply_patch_replaces_single_match(tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))
    target = tmp_path / "demo.txt"
    target.write_text("hello world\nsecond line\n", encoding="utf-8")

    result = tooling.apply_patch(path="demo.txt", search="hello world", replace="hi world")

    assert "replacements=1" in result
    assert target.read_text(encoding="utf-8") == "hi world\nsecond line\n"


def test_list_dir_and_write_file_paths(tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    assert tooling.list_dir(".") == "(empty)"

    write_result = tooling.write_file("nested/out.txt", "hello")
    assert "nested" in write_result
    assert "out.txt" in write_result

    listing = tooling.list_dir("nested")
    assert "out.txt" in listing


def test_list_dir_missing_directory_raises(tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    with pytest.raises(ToolExecutionError, match="Directory not found"):
        tooling.list_dir("does-not-exist")


def test_write_file_rejects_too_large_payload(tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    with pytest.raises(ToolExecutionError, match="Content too large"):
        tooling.write_file("large.txt", "x" * 300001)


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

    command = f'"{sys.executable}" -c "print(\"started\")"'
    started = tooling.start_background_command(command=command)
    job_id = started.split("job_id=")[1].split()[0]

    output_before = tooling.get_background_output(job_id=job_id, tail_lines=20)
    assert f"job_id={job_id}" in output_before

    killed = tooling.kill_background_process(job_id=job_id)
    assert job_id in killed


def test_get_changed_files_success_and_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    calls: list[list[str]] = []

    def _fake_run(cmd, capture_output, text, timeout):
        calls.append(cmd)
        if cmd[-2:] == ["status", "--short"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=" M app.py\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="app.py\n", stderr="")

    monkeypatch.setattr(tools_module.subprocess, "run", _fake_run)
    output = tooling.get_changed_files()

    assert "status:" in output
    assert "unstaged_files:" in output
    assert len(calls) == 2

    def _fake_run_fail(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="git failed")

    monkeypatch.setattr(tools_module.subprocess, "run", _fake_run_fail)
    with pytest.raises(ToolExecutionError, match="git failed"):
        tooling.get_changed_files()


def test_web_fetch_formats_html_with_source_metadata(monkeypatch, tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers = {"Content-Type": "text/html; charset=utf-8"}
            self.encoding = "utf-8"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aiter_bytes(self):
            yield (
                b"<html><head><title>Best LLMs 2026</title><style>.x{}</style></head>"
                b"<body><script>ignored()</script><h1>Rankings</h1><p>Model A leads.</p></body></html>"
            )

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            return

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, _method: str, _url: str, **kwargs):
            return _FakeResponse()

    def _public_getaddrinfo(host: str, port: int, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
        ]

    monkeypatch.setattr(tools_module.socket, "getaddrinfo", _public_getaddrinfo)
    monkeypatch.setattr(tools_module.httpx, "AsyncClient", _FakeClient)

    result = asyncio.run(tooling.web_fetch("https://example.com/models", max_chars=4000))

    assert "source_url: https://example.com/models" in result
    assert "content_type: text/html; charset=utf-8" in result
    assert "Best LLMs 2026" in result
    assert "Model A leads." in result
    assert "<script>" not in result


def test_web_fetch_rejects_non_http_scheme(tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    try:
        asyncio.run(tooling.web_fetch("file:///etc/passwd"))
        assert False, "Expected ToolExecutionError"
    except Exception as exc:
        assert "http/https" in str(exc)


def test_web_fetch_error_contains_source_url(monkeypatch, tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    class _FakeResponse:
        status_code = 404
        headers = {}
        encoding = "utf-8"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aiter_bytes(self):
            if False:
                yield b""

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            return

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, _method: str, _url: str, **kwargs):
            return _FakeResponse()

    def _public_getaddrinfo(host: str, port: int, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
        ]

    monkeypatch.setattr(tools_module.socket, "getaddrinfo", _public_getaddrinfo)
    monkeypatch.setattr(tools_module.httpx, "AsyncClient", _FakeClient)

    try:
        asyncio.run(tooling.web_fetch("https://example.com/missing"))
        assert False, "Expected ToolExecutionError"
    except Exception as exc:
        text = str(exc)
        assert "HTTP 404" in text
        assert "404" in text


def test_read_file_blocks_oversized_file(tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))
    target = tmp_path / "large.txt"
    target.write_bytes(b"a" * (tooling._read_file_max_bytes + 1))

    with pytest.raises(ToolExecutionError, match="File too large for read_file tool"):
        tooling.read_file("large.txt")


def test_grep_search_skips_oversized_files(tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "small.txt").write_text("needle\n", encoding="utf-8")
    (tmp_path / "src" / "big.txt").write_bytes(b"needle\n" * (tooling._grep_max_file_bytes + 1))

    matches = tooling.grep_search(query="needle", include_pattern="src/*.txt", is_regexp=False, max_results=10)

    assert "src/small.txt" in matches
    assert "src/big.txt" not in matches


def test_analyze_image_requires_feature_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))
    image_file = tmp_path / "screen.png"
    image_file.write_bytes(b"not-an-image-but-bytes")

    monkeypatch.setattr(tools_module.settings, "vision_enabled", False)

    with pytest.raises(ToolExecutionError, match="disabled"):
        asyncio.run(tooling.analyze_image("screen.png", prompt="Describe"))


def test_analyze_image_uses_vision_service(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))
    image_file = tmp_path / "screen.png"
    image_file.write_bytes(b"fake-image-bytes")

    class _FakeVisionService:
        def __init__(self, base_url: str, model: str, api_key: str | None = None, provider: str = "auto"):
            _ = (base_url, model, api_key, provider)

        async def analyze_image(
            self,
            image_base64: str,
            image_mime_type: str = "image/png",
            prompt: str = "",
            max_tokens: int = 1000,
        ) -> str:
            assert isinstance(image_base64, str)
            assert len(image_base64) > 0
            assert image_mime_type.startswith("image/")
            assert prompt == "Find text"
            assert max_tokens > 0
            return "Detected a login form and a submit button."

    monkeypatch.setattr(tools_module.settings, "vision_enabled", True)
    monkeypatch.setattr(tools_module.settings, "vision_base_url", "http://localhost:11434")
    monkeypatch.setattr(tools_module.settings, "vision_model", "llava:13b")
    monkeypatch.setattr(tools_module.settings, "vision_api_key", "")
    monkeypatch.setattr(tools_module.settings, "vision_provider", "ollama")
    monkeypatch.setattr(tools_module.settings, "vision_max_tokens", 1000)
    monkeypatch.setattr(tools_module, "VisionService", _FakeVisionService)

    result = asyncio.run(tooling.analyze_image("screen.png", prompt="Find text"))

    assert "login form" in result


def test_code_execute_returns_serialized_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    class _FakeResult:
        success = True
        strategy = "process"
        language = "python"
        exit_code = 0
        timed_out = False
        truncated = False
        duration_ms = 12
        error_type = None
        error_message = None
        stdout = "ok"
        stderr = ""

    class _FakeSandbox:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def execute(self, code, language, timeout, max_output_chars):
            assert code == "print('x')"
            assert language == "python"
            assert timeout == 5
            assert max_output_chars == 900
            return _FakeResult()

    monkeypatch.setattr(tools_module, "CodeSandbox", _FakeSandbox)

    payload = asyncio.run(
        tooling.code_execute(
            code="print('x')",
            language="python",
            timeout=5,
            max_output_chars=900,
            strategy="process",
        )
    )

    assert '"success": true' in payload
    assert '"stdout": "ok"' in payload


def test_resolve_command_cwd_validations(tmp_path: Path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    assert tooling._resolve_command_cwd(None) == tmp_path.resolve()

    subdir = tmp_path / "repo"
    subdir.mkdir()
    assert tooling._resolve_command_cwd("repo") == subdir.resolve()

    outside = tmp_path.parent
    with pytest.raises(ToolExecutionError, match="escapes workspace root"):
        tooling._resolve_command_cwd(str(outside))

    with pytest.raises(ToolExecutionError, match="does not exist"):
        tooling._resolve_command_cwd("missing-dir")
