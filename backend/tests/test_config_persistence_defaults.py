from __future__ import annotations

from pathlib import Path

from app.config import _default_reset_on_startup, _resolve_path_from_workspace, _resolve_prompt, _resolve_workspace_root


def test_default_reset_on_startup_is_env_aware() -> None:
    assert _default_reset_on_startup("development") is True
    assert _default_reset_on_startup("staging") is True
    assert _default_reset_on_startup("production") is False


def test_workspace_root_resolution_is_absolute() -> None:
    resolved = _resolve_workspace_root(".")
    assert Path(resolved).is_absolute()


def test_relative_persist_path_resolves_from_workspace_root() -> None:
    workspace_root = str(Path.cwd())
    resolved = _resolve_path_from_workspace("./state_store", workspace_root, "fallback")
    assert Path(resolved).is_absolute()
    assert resolved == str((Path(workspace_root) / "state_store").resolve())


def test_resolve_prompt_uses_first_defined_env_key(monkeypatch) -> None:
    monkeypatch.delenv("PROMPT_PRIMARY", raising=False)
    monkeypatch.setenv("PROMPT_FALLBACK", "fallback-value")

    resolved = _resolve_prompt("default-value", "PROMPT_PRIMARY", "PROMPT_FALLBACK")

    assert resolved == "fallback-value"
