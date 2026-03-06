from __future__ import annotations

import asyncio

import pytest

from app.services.vision_service import VisionService


class _StubVisionService(VisionService):
    def __init__(self, provider: str, payload: dict):
        super().__init__(
            base_url="http://localhost:11434",
            model="llava:13b",
            api_key="test-key",
            provider=provider,
        )
        self._payload = payload

    async def _request_json(self, method: str, url: str, *, headers=None, json_body=None) -> dict:
        _ = (method, url, headers, json_body)
        return self._payload


def test_vision_service_openai_response_parsing() -> None:
    service = _StubVisionService(
        "openai",
        {
            "choices": [
                {
                    "message": {
                        "content": "The screenshot shows a dashboard with a sidebar and a chart.",
                    }
                }
            ]
        },
    )

    text = asyncio.run(service.analyze_image("ZmFrZQ==", image_mime_type="image/png", prompt="Describe UI"))

    assert "dashboard" in text


def test_vision_service_ollama_response_parsing() -> None:
    service = _StubVisionService(
        "ollama",
        {
            "response": "A terminal window with a successful test run.",
        },
    )

    text = asyncio.run(service.analyze_image("ZmFrZQ==", image_mime_type="image/png", prompt="What is shown?"))

    assert "terminal" in text


def test_vision_service_empty_image_rejected() -> None:
    service = VisionService(base_url="http://localhost:11434", model="llava:13b", provider="auto")

    with pytest.raises(ValueError, match="image_base64 must not be empty"):
        asyncio.run(service.analyze_image(""))
