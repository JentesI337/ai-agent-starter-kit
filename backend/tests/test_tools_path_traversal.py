from __future__ import annotations

from pathlib import Path

import pytest

from app.errors import ToolExecutionError
from app.tooling import AgentTooling


def _tooling(tmp_path: Path) -> AgentTooling:
    return AgentTooling(workspace_root=str(tmp_path))


def test_resolve_workspace_path_allows_simple_relative_path(tmp_path: Path) -> None:
    tooling = _tooling(tmp_path)
    (tmp_path / "docs").mkdir()

    resolved = tooling._resolve_workspace_path("docs")

    assert resolved == (tmp_path / "docs").resolve()


def test_resolve_workspace_path_blocks_dotdot_escape(tmp_path: Path) -> None:
    tooling = _tooling(tmp_path)

    with pytest.raises(ToolExecutionError, match="Path escapes workspace root"):
        tooling._resolve_workspace_path("..")


def test_resolve_workspace_path_blocks_absolute_outside_workspace(tmp_path: Path) -> None:
    tooling = _tooling(tmp_path)
    outside = tmp_path.parent / "outside.txt"

    with pytest.raises(ToolExecutionError, match="Path escapes workspace root"):
        tooling._resolve_workspace_path(str(outside))


def test_resolve_workspace_path_allows_workspace_root(tmp_path: Path) -> None:
    tooling = _tooling(tmp_path)

    resolved = tooling._resolve_workspace_path(".")

    assert resolved == tmp_path.resolve()


def test_resolve_workspace_path_allows_deep_nested_path(tmp_path: Path) -> None:
    tooling = _tooling(tmp_path)
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)

    resolved = tooling._resolve_workspace_path("a/b/c")

    assert resolved == nested.resolve()


def test_resolve_workspace_path_allows_dotdot_within_workspace(tmp_path: Path) -> None:
    tooling = _tooling(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "lib").mkdir()

    resolved = tooling._resolve_workspace_path("src/../lib")

    assert resolved == (tmp_path / "lib").resolve()


def test_resolve_workspace_path_blocks_windows_backslash_traversal(tmp_path: Path) -> None:
    tooling = _tooling(tmp_path)

    with pytest.raises(ToolExecutionError, match="Path escapes workspace root"):
        tooling._resolve_workspace_path("..\\..\\Windows")
