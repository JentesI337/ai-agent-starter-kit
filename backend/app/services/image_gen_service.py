"""Image generation service."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_MAX_PROMPT_LENGTH = 1000


class ImageGenService:
    """Generate images via AUTOMATIC1111/Forge sd-webui, OpenAI DALL-E, or StabilityAI."""

    def __init__(
        self,
        provider: str = "sd-webui",
        api_key: str = "",
        base_url: str = "http://localhost:7860",
        model: str = "",
        default_size: str = "1024x1024",
    ):
        self.provider = (provider or "sd-webui").strip().lower()
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "http://localhost:7860").strip().rstrip("/")
        self.model = (model or "").strip()
        self.default_size = (default_size or "1024x1024").strip()

    async def generate(self, prompt: str, size: str | None = None) -> str:
        """Generate an image and return base64 PNG data."""
        clean_prompt = (prompt or "").strip()[:_MAX_PROMPT_LENGTH]
        if not clean_prompt:
            raise ValueError("Image generation prompt must not be empty")

        effective_size = (size or self.default_size).strip() or self.default_size

        if self.provider == "sd-webui":
            return await self._generate_sd_webui(clean_prompt, effective_size)
        if self.provider == "openai":
            return await self._generate_openai(clean_prompt, effective_size)
        if self.provider == "stabilityai":
            return await self._generate_stability(clean_prompt, effective_size)
        raise ValueError(f"Unknown image generation provider: {self.provider}")

    async def _generate_sd_webui(self, prompt: str, size: str) -> str:
        """Generate via AUTOMATIC1111 / Forge sd-webui API."""
        parts = size.split("x")
        width = int(parts[0]) if len(parts) == 2 else 1024
        height = int(parts[1]) if len(parts) == 2 else 1024

        payload: dict = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "steps": 20,
            "batch_size": 1,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/sdapi/v1/txt2img",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        images = data.get("images", [])
        if not images:
            raise ValueError("sd-webui returned no images")
        return str(images[0])

    async def _generate_openai(self, prompt: str, size: str) -> str:
        """Generate via OpenAI DALL-E API."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/images/generations",
                headers=headers,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "n": 1,
                    "size": size,
                    "response_format": "b64_json",
                },
            )
            response.raise_for_status()
            data = response.json()

        items = data.get("data", [])
        if not items:
            raise ValueError("Image generation returned no results")
        return str(items[0].get("b64_json", ""))

    async def _generate_stability(self, prompt: str, size: str) -> str:
        """Generate via StabilityAI API."""
        # Parse size
        parts = size.split("x")
        width = int(parts[0]) if len(parts) == 2 else 1024
        height = int(parts[1]) if len(parts) == 2 else 1024

        headers: dict[str, str] = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/generation/{self.model}/text-to-image",
                headers=headers,
                json={
                    "text_prompts": [{"text": prompt}],
                    "width": width,
                    "height": height,
                    "samples": 1,
                },
            )
            response.raise_for_status()
            data = response.json()

        artifacts = data.get("artifacts", [])
        if not artifacts:
            raise ValueError("StabilityAI returned no artifacts")
        return str(artifacts[0].get("base64", ""))
