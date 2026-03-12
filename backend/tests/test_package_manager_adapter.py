"""Unit tests for PackageManagerAdapter + concrete adapters."""

from __future__ import annotations

import json

import pytest

from app.tools.provisioning.package_manager_adapter import (
    BrewAdapter,
    ChocoAdapter,
    NpmAdapter,
    PackageCandidate,
    PackageManagerAdapter,
    PipAdapter,
    _sanitize,
    get_platform_adapters,
)


class TestSanitize:
    def test_strips_dangerous_chars(self):
        assert _sanitize("my;package|foo") == "mypackagefoo"

    def test_trims_length(self):
        assert len(_sanitize("a" * 200)) <= 128

    def test_clean_input_unchanged(self):
        assert _sanitize("lodash") == "lodash"


class TestNpmAdapter:
    @pytest.fixture
    def adapter(self):
        return NpmAdapter()

    def test_protocol(self, adapter):
        assert isinstance(adapter, PackageManagerAdapter)

    def test_probe(self, adapter):
        assert "npm" in adapter.probe_command()

    def test_search_command(self, adapter):
        cmd = adapter.search_command("lodash")
        assert "npm search" in cmd
        assert "lodash" in cmd

    def test_parse_json(self, adapter):
        data = json.dumps([
            {"name": "lodash", "version": "4.17.21", "description": "Utility lib"},
            {"name": "underscore", "version": "1.13.6", "description": "JS utils"},
        ])
        results = adapter.parse_search_output(data)
        assert len(results) == 2
        assert results[0].name == "lodash"
        assert results[0].manager == "npm"

    def test_parse_invalid_json(self, adapter):
        assert adapter.parse_search_output("not json") == []

    def test_install(self, adapter):
        assert adapter.install_command("lodash") == "npm install lodash"


class TestPipAdapter:
    @pytest.fixture
    def adapter(self):
        return PipAdapter()

    def test_protocol(self, adapter):
        assert isinstance(adapter, PackageManagerAdapter)

    def test_probe(self, adapter):
        assert "pip" in adapter.probe_command()

    def test_parse_versions(self, adapter):
        raw = "requests (2.31.0)\nflask (3.0.0)\n"
        results = adapter.parse_search_output(raw)
        assert len(results) == 2
        assert results[0].name == "requests"
        assert results[0].version == "2.31.0"

    def test_install(self, adapter):
        assert adapter.install_command("requests") == "pip install requests"


class TestBrewAdapter:
    @pytest.fixture
    def adapter(self):
        return BrewAdapter()

    def test_protocol(self, adapter):
        assert isinstance(adapter, PackageManagerAdapter)

    def test_parse(self, adapter):
        raw = "jq\nwget\ncurl\n"
        results = adapter.parse_search_output(raw)
        assert len(results) == 3
        assert results[0].install_command == "brew install jq"

    def test_parse_ignores_headers(self, adapter):
        raw = "==> Formulae\njq\nwget\n"
        results = adapter.parse_search_output(raw)
        names = [r.name for r in results]
        assert "==> Formulae" not in names


class TestChocoAdapter:
    @pytest.fixture
    def adapter(self):
        return ChocoAdapter()

    def test_protocol(self, adapter):
        assert isinstance(adapter, PackageManagerAdapter)

    def test_parse(self, adapter):
        raw = "jq|1.7.1\nwget|1.21.4\n"
        results = adapter.parse_search_output(raw)
        assert len(results) == 2
        assert results[0].name == "jq"
        assert results[0].version == "1.7.1"
        assert "choco install" in results[0].install_command

    def test_install(self, adapter):
        assert adapter.install_command("jq") == "choco install jq -y"


class TestGetPlatformAdapters:
    def test_returns_list(self):
        adapters = get_platform_adapters()
        assert len(adapters) >= 2
        assert all(isinstance(a, PackageManagerAdapter) for a in adapters)


class TestPackageCandidate:
    def test_to_dict(self):
        pc = PackageCandidate(name="foo", version="1.0", manager="pip", install_command="pip install foo")
        d = pc.to_dict()
        assert d["name"] == "foo"
        assert d["manager"] == "pip"
