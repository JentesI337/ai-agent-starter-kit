"""Unit tests for EnvironmentSnapshot (L4.5)."""

from __future__ import annotations

import asyncio
import json

from app.monitoring.environment_snapshot import (
    EnvironmentSnapshot,
    _parse_npm_list,
    _parse_pip_freeze,
)


class TestParsePipFreeze:
    def test_basic(self):
        raw = "requests==2.31.0\nnumpy==1.26.0\n"
        pkgs = _parse_pip_freeze(raw)
        assert pkgs == {"requests": "2.31.0", "numpy": "1.26.0"}

    def test_empty(self):
        assert _parse_pip_freeze("") == {}

    def test_with_noise(self):
        raw = "WARNING: pip is old\nflask==3.0.0\n"
        pkgs = _parse_pip_freeze(raw)
        assert "flask" in pkgs

    def test_normalises_case(self):
        raw = "Flask==3.0.0\n"
        pkgs = _parse_pip_freeze(raw)
        assert "flask" in pkgs


class TestParseNpmList:
    def test_basic(self):
        data = {"dependencies": {"lodash": {"version": "4.17.21"}, "express": {"version": "4.18.0"}}}
        pkgs = _parse_npm_list(json.dumps(data))
        assert pkgs == {"lodash": "4.17.21", "express": "4.18.0"}

    def test_empty_json(self):
        assert _parse_npm_list("{}") == {}

    def test_invalid_json(self):
        assert _parse_npm_list("not json") == {}


class TestCapture:
    def test_pip_capture(self):
        async def fake_run(cmd: str) -> str:
            if "pip freeze" in cmd:
                return "requests==2.31.0\nflask==3.0.0\n"
            return ""

        snap = asyncio.run(EnvironmentSnapshot.capture(scope="pip", run_command=fake_run))
        assert snap.scope == "pip"
        assert len(snap.packages) == 2
        assert snap.timestamp > 0

    def test_npm_capture(self):
        data = {"dependencies": {"lodash": {"version": "4.17.21"}}}

        async def fake_run(cmd: str) -> str:
            if "npm list" in cmd:
                return json.dumps(data)
            return ""

        snap = asyncio.run(EnvironmentSnapshot.capture(scope="npm", run_command=fake_run))
        assert snap.scope == "npm"
        assert "lodash" in snap.packages

    def test_unknown_scope(self):
        async def fake_run(cmd: str) -> str:
            return ""

        snap = asyncio.run(EnvironmentSnapshot.capture(scope="cargo", run_command=fake_run))
        assert snap.packages == {}


class TestRollback:
    def test_rollback_removes_added_packages(self):
        snap = EnvironmentSnapshot(scope="pip", packages={"requests": "2.31.0"})
        commands_run: list[str] = []

        async def fake_run(cmd: str) -> str:
            commands_run.append(cmd)
            if "pip freeze" in cmd:
                return "requests==2.31.0\nnewpkg==1.0.0\n"
            return ""

        removed = asyncio.run(snap.rollback(run_command=fake_run))
        assert "newpkg" in removed
        assert any("pip uninstall -y newpkg" in c for c in commands_run)

    def test_rollback_nothing_to_remove(self):
        snap = EnvironmentSnapshot(scope="pip", packages={"requests": "2.31.0"})

        async def fake_run(cmd: str) -> str:
            if "pip freeze" in cmd:
                return "requests==2.31.0\n"
            return ""

        removed = asyncio.run(snap.rollback(run_command=fake_run))
        assert removed == []

    def test_rollback_with_provided_current(self):
        snap = EnvironmentSnapshot(scope="pip", packages={})
        commands_run: list[str] = []

        async def fake_run(cmd: str) -> str:
            commands_run.append(cmd)
            return ""

        removed = asyncio.run(
            snap.rollback(
                run_command=fake_run,
                current_packages={"newpkg": "1.0.0"},
            )
        )
        assert "newpkg" in removed


class TestToDict:
    def test_keys(self):
        snap = EnvironmentSnapshot(scope="pip", packages={"a": "1"}, timestamp=123.0)
        d = snap.to_dict()
        assert d["scope"] == "pip"
        assert d["package_count"] == 1
        assert d["timestamp"] == 123.0
