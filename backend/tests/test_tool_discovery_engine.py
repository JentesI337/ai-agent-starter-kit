"""Unit tests for ToolDiscoveryEngine."""

from __future__ import annotations

import asyncio

import pytest

from app.tools.discovery.engine import DiscoveryResult, ToolDiscoveryEngine
from app.tools.discovery.knowledge_base import ToolKnowledgeBase
from app.tools.provisioning.package_manager_adapter import NpmAdapter


@pytest.fixture
def kb():
    return ToolKnowledgeBase()  # in-memory


@pytest.fixture
def engine(kb):
    return ToolDiscoveryEngine(kb=kb, adapters=[], min_confidence=0.8)


class TestPhaseKnowledgeBase:
    def test_kb_hit(self, kb, engine):
        kb.learn_from_outcome(tool="jq", capability="json_processing", install_hint="apt install jq", confidence=0.9)
        result = asyncio.run(engine.discover("json_processing"))
        assert result.found
        assert result.tool == "jq"
        assert result.source == "knowledge_base"

    def test_kb_miss(self, engine):
        result = asyncio.run(engine.discover("nonexistent_capability"))
        assert not result.found

    def test_kb_low_confidence_skipped(self, kb, engine):
        kb.learn_from_outcome(tool="jq", capability="json", confidence=0.3)
        result = asyncio.run(engine.discover("json"))
        assert not result.found


class TestPhasePackageManager:
    def test_adapter_search(self, kb):
        adapter = NpmAdapter()

        async def fake_run_command(cmd: str) -> str:
            if "npm --version" in cmd:
                return "10.2.4"
            if "npm search" in cmd:
                import json
                return json.dumps([{"name": "lodash", "version": "4.17.21", "description": "Utility lib"}])
            return ""

        engine = ToolDiscoveryEngine(kb=kb, adapters=[adapter])
        result = asyncio.run(
            engine.discover("lodash", run_command=fake_run_command)
        )
        assert result.found
        assert result.tool == "lodash"
        assert result.source == "pkg_manager"
        assert kb.count() == 1

    def test_adapter_not_available(self, kb):
        adapter = NpmAdapter()

        async def fake_run_command(cmd: str) -> str:
            if "npm --version" in cmd:
                return "command not found"
            return ""

        engine = ToolDiscoveryEngine(kb=kb, adapters=[adapter])
        result = asyncio.run(
            engine.discover("lodash", run_command=fake_run_command)
        )
        assert not result.found

    def test_adapter_exception_isolated(self, kb):
        adapter = NpmAdapter()

        async def exploding_run_command(cmd: str) -> str:
            raise RuntimeError("boom")

        engine = ToolDiscoveryEngine(kb=kb, adapters=[adapter])
        result = asyncio.run(
            engine.discover("lodash", run_command=exploding_run_command)
        )
        assert not result.found


class TestDiscoveryResult:
    def test_to_dict(self):
        r = DiscoveryResult(found=True, tool="jq", source="knowledge_base", confidence=0.95)
        d = r.to_dict()
        assert d["found"] is True
        assert d["tool"] == "jq"

    def test_not_found(self):
        r = DiscoveryResult(found=False)
        assert r.to_dict()["found"] is False
