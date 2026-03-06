"""Tests for Wave 3 security fixes.

Covers:
  - CFG-05: debug_mode defaults to False
  - DEP-01: No unused frontend deps in backend/package.json
  - INFO-06: Server header stripped (version not disclosed)
  - INFO-08: Swagger/OpenAPI disabled in production
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.app_setup import build_fastapi_app
from app.config import Settings, _parse_bool_env

# ── CFG-05: debug_mode defaults to False ──────────────────────────────


class TestCFG05DebugModeDefault:
    """Verify debug_mode defaults to False and can be toggled via env var."""

    def test_default_debug_mode_is_false(self) -> None:
        s = Settings()
        assert s.debug_mode is False, "debug_mode must default to False"

    def test_debug_mode_enabled_via_env(self, monkeypatch) -> None:
        monkeypatch.setenv("DEBUG_MODE", "true")
        result = _parse_bool_env("DEBUG_MODE", False)
        assert result is True

    def test_debug_mode_disabled_via_env(self, monkeypatch) -> None:
        monkeypatch.setenv("DEBUG_MODE", "false")
        result = _parse_bool_env("DEBUG_MODE", False)
        assert result is False

    def test_debug_mode_unset_falls_back_to_default(self, monkeypatch) -> None:
        monkeypatch.delenv("DEBUG_MODE", raising=False)
        result = _parse_bool_env("DEBUG_MODE", False)
        assert result is False


# ── DEP-01: No unused frontend deps in backend/package.json ──────────


class TestDEP01UnusedDeps:
    """Verify backend/package.json does not contain frontend frameworks."""

    FORBIDDEN_DEPS = {"react", "react-dom", "vue", "webpack", "webpack-cli"}
    PACKAGE_JSON = Path(__file__).resolve().parent.parent / "package.json"

    def test_no_frontend_deps_in_backend(self) -> None:
        assert self.PACKAGE_JSON.exists(), f"Missing {self.PACKAGE_JSON}"
        data = json.loads(self.PACKAGE_JSON.read_text(encoding="utf-8"))
        deps = set(data.get("dependencies", {}).keys())
        dev_deps = set(data.get("devDependencies", {}).keys())
        all_deps = deps | dev_deps
        found = all_deps & self.FORBIDDEN_DEPS
        assert found == set(), (
            f"Backend package.json still contains unused frontend deps: {found}"
        )


# ── INFO-06: Server header does not disclose version ─────────────────


class TestINFO06ServerHeader:
    """Verify the Server header is overwritten and does not leak uvicorn version."""

    def _make_client(self) -> TestClient:
        mock_settings = MagicMock()
        mock_settings.app_env = "development"
        mock_settings.debug_mode = False
        mock_settings.cors_allow_origins = []
        mock_settings.cors_allow_credentials = True
        app = build_fastapi_app(title="test", settings=mock_settings)

        @app.get("/test-info06")
        async def _test_endpoint():
            return {"ok": True}

        return TestClient(app)

    def test_server_header_is_generic(self) -> None:
        client = self._make_client()
        resp = client.get("/test-info06")
        server = resp.headers.get("Server", "")
        assert "uvicorn" not in server.lower(), (
            f"Server header should not contain 'uvicorn', got: {server}"
        )
        assert server == "app", f"Expected Server header 'app', got: {server}"


# ── INFO-08: Swagger/OpenAPI disabled in production ───────────────────


class TestINFO08SwaggerInProd:
    """Verify /docs, /redoc, /openapi.json are disabled in production."""

    def _make_app(self, *, app_env: str, debug_mode: bool = False):
        mock_settings = MagicMock()
        mock_settings.app_env = app_env
        mock_settings.debug_mode = debug_mode
        mock_settings.cors_allow_origins = []
        mock_settings.cors_allow_credentials = True
        return build_fastapi_app(title="test", settings=mock_settings)

    def test_docs_disabled_in_production(self) -> None:
        app = self._make_app(app_env="production")
        client = TestClient(app, raise_server_exceptions=False)
        for path in ["/docs", "/redoc", "/openapi.json"]:
            resp = client.get(path)
            assert resp.status_code == 404, (
                f"{path} should return 404 in production, got {resp.status_code}"
            )

    def test_docs_enabled_in_development(self) -> None:
        app = self._make_app(app_env="development")
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/openapi.json")
        assert resp.status_code == 200, (
            f"/openapi.json should be available in development, got {resp.status_code}"
        )

    def test_docs_enabled_in_production_with_debug_mode(self) -> None:
        app = self._make_app(app_env="production", debug_mode=True)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/openapi.json")
        assert resp.status_code == 200, (
            f"/openapi.json should be available in production+debug_mode, got {resp.status_code}"
        )
