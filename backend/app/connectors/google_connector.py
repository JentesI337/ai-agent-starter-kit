"""Google API connector (Calendar, Drive, Sheets)."""
from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector, ConnectorConfig, ConnectorCredentials

_DEFAULT_BASE = "https://www.googleapis.com"

_METHOD_MAP: dict[str, tuple[str, str]] = {
    "calendar.list": ("GET", "/calendar/v3/users/me/calendarList"),
    "drive.list": ("GET", "/drive/v3/files"),
    "sheets.get": ("GET", "/v4/spreadsheets/{spreadsheet_id}"),
}


class GoogleConnector(BaseConnector):

    def __init__(self, config: ConnectorConfig, credentials: ConnectorCredentials | None = None) -> None:
        if not config.base_url:
            config = config.model_copy(update={"base_url": _DEFAULT_BASE})
        super().__init__(config, credentials)

    def build_request(
        self, method: str, params: dict[str, Any]
    ) -> tuple[str, str, dict[str, str], Any]:
        spec = _METHOD_MAP.get(method)
        if spec is None:
            raise ValueError(f"Unknown Google method '{method}'. Available: {list(_METHOD_MAP)}")

        http_method, path_template = spec
        spreadsheet_id = params.pop("spreadsheet_id", None) or ""
        path = path_template.replace("{spreadsheet_id}", spreadsheet_id)

        base = self.config.base_url.rstrip("/")
        url = f"{base}{path}"
        return http_method, url, {}, params or None

    def available_methods(self) -> list[dict[str, Any]]:
        return [
            {"name": "calendar.list", "description": "List calendars"},
            {"name": "drive.list", "description": "List Drive files", "params": ["q", "pageSize"]},
            {"name": "sheets.get", "description": "Get a spreadsheet", "params": ["spreadsheet_id"]},
        ]
