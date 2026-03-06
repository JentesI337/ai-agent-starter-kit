"""Tests for PlatformInfo detection."""

import pytest

from app.services.platform_info import PlatformInfo, detect_platform


class TestPlatformInfo:
    def test_detect_platform_returns_platforminfo(self):
        info = detect_platform()
        assert isinstance(info, PlatformInfo)

    def test_os_name_valid(self):
        info = detect_platform()
        assert info.os_name in ("windows", "linux", "darwin")

    def test_arch_not_empty(self):
        info = detect_platform()
        assert info.arch

    def test_shell_not_empty(self):
        info = detect_platform()
        assert info.shell

    def test_summary_not_empty(self):
        info = detect_platform()
        summary = info.summary()
        assert info.os_name in summary

    def test_has_runtime_python(self):
        info = detect_platform()
        assert info.has_runtime("python")

    def test_has_package_manager_pip(self):
        info = detect_platform()
        assert info.has_package_manager("pip") or info.has_package_manager("pip3")

    def test_is_properties(self):
        info = detect_platform()
        # Exactly one should be True
        os_props = [info.is_windows, info.is_linux, info.is_macos]
        assert sum(os_props) == 1

    def test_cached(self):
        info1 = detect_platform()
        info2 = detect_platform()
        assert info1 is info2

    def test_frozen(self):
        info = detect_platform()
        with pytest.raises(AttributeError):
            info.os_name = "bsd"  # type: ignore[misc]

    def test_home_dir_not_empty(self):
        info = detect_platform()
        assert info.home_dir
