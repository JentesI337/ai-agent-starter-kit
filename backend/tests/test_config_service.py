"""Tests for ConfigService (Sprint R1)."""
from __future__ import annotations

import json
import tempfile
from unittest.mock import MagicMock

import pytest

from app.config.sections import SECTION_REGISTRY, field_to_section
from app.config.service import ConfigService


@pytest.fixture
def mock_settings():
    """Create a mock settings object with all fields from section registry."""
    settings = MagicMock()
    for model_cls in SECTION_REGISTRY.values():
        for field_name, field_info in model_cls.model_fields.items():
            default = field_info.default
            if default is None and field_info.default_factory is not None:
                default = field_info.default_factory()
            setattr(settings, field_name, default)
    settings.workspace_root = tempfile.gettempdir()
    return settings


@pytest.fixture
def config_service(mock_settings, tmp_path):
    overrides_path = tmp_path / "config_overrides.json"
    return ConfigService(mock_settings, overrides_path=overrides_path)


class TestSectionRegistry:
    def test_all_sections_present(self):
        assert len(SECTION_REGISTRY) >= 15

    def test_field_to_section_mapping(self):
        assert field_to_section("llm_model") == "llm"
        assert field_to_section("app_env") == "core"
        assert field_to_section("browser_enabled") == "browser"
        assert field_to_section("nonexistent") is None


class TestConfigServiceRead:
    def test_get_section(self, config_service):
        section = config_service.get_section("core")
        assert hasattr(section, "app_env")

    def test_get_section_unknown(self, config_service):
        with pytest.raises(KeyError):
            config_service.get_section("nonexistent")

    def test_get_value_from_settings(self, config_service, mock_settings):
        mock_settings.llm_model = "test-model"
        assert config_service.get_value("llm", "llm_model") == "test-model"

    def test_get_all_sections_metadata(self, config_service):
        meta = config_service.get_all_sections_metadata()
        assert len(meta) >= 15
        keys = [m.key for m in meta]
        assert "core" in keys
        assert "llm" in keys


class TestConfigServiceWrite:
    def test_update_value_persists(self, config_service, tmp_path):
        result = config_service.update_value("tool_execution", "run_tool_call_cap", 12)
        assert result.ok
        assert result.new_value == 12
        assert result.persisted
        overrides = json.loads((tmp_path / "config_overrides.json").read_text())
        assert overrides["tool_execution"]["run_tool_call_cap"] == 12

    def test_update_value_unknown_section(self, config_service):
        result = config_service.update_value("nonexistent", "field", "value")
        assert not result.ok

    def test_update_value_unknown_field(self, config_service):
        result = config_service.update_value("core", "nonexistent_field", "value")
        assert not result.ok

    def test_update_sensitive_field_blocked(self, config_service):
        result = config_service.update_value("llm", "llm_api_key", "secret")
        assert not result.ok
        assert "sensitive" in result.validation_errors[0].lower()

    def test_update_section_batch(self, config_service):
        results = config_service.update_section("tool_execution", {
            "run_tool_call_cap": 15,
            "run_tool_time_cap_seconds": 120.0,
        })
        assert all(r.ok for r in results)

    def test_transient_override_not_persisted(self, config_service, tmp_path):
        result = config_service.update_value("core", "debug_mode", True, persist=False)
        assert result.ok
        assert not result.persisted
        assert config_service.get_value("core", "debug_mode") is True


class TestConfigServiceReset:
    def test_reset_section(self, config_service):
        config_service.update_value("tool_execution", "run_tool_call_cap", 99)
        assert config_service.reset_section("tool_execution")

    def test_reset_unknown_section(self, config_service):
        assert not config_service.reset_section("nonexistent")


class TestConfigServiceDiff:
    def test_export_diff_empty(self, config_service):
        diff = config_service.export_diff()
        assert diff == {}

    def test_export_diff_with_overrides(self, config_service):
        config_service.update_value("core", "debug_mode", True)
        diff = config_service.export_diff()
        assert "core" in diff
        assert "debug_mode" in diff["core"]


class TestConfigServiceSubscription:
    def test_subscribe_and_notify(self, config_service):
        events = []
        config_service.subscribe("core", lambda sk, fn, ov, nv: events.append((fn, ov, nv)))
        config_service.update_value("core", "debug_mode", True)
        assert len(events) == 1
        assert events[0][0] == "debug_mode"


class TestConfigServicePersistence:
    def test_load_on_init(self, mock_settings, tmp_path):
        overrides_path = tmp_path / "config_overrides.json"
        overrides_path.write_text(json.dumps({
            "core": {"debug_mode": True},
        }))
        svc = ConfigService(mock_settings, overrides_path=overrides_path)
        assert svc.get_value("core", "debug_mode") is True

    def test_survives_restart(self, mock_settings, tmp_path):
        overrides_path = tmp_path / "config_overrides.json"
        svc1 = ConfigService(mock_settings, overrides_path=overrides_path)
        svc1.update_value("tool_execution", "run_tool_call_cap", 42)

        svc2 = ConfigService(mock_settings, overrides_path=overrides_path)
        assert svc2.get_value("tool_execution", "run_tool_call_cap") == 42
