from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class VisionRequest:
    image_base64: str
    image_mime_type: str
    prompt: str
    max_tokens: int


class VisionService:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        provider: str = "auto",
    ):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.model = (model or "").strip()
        self.api_key = (api_key or "").strip() or None
        self.provider = (provider or "auto").strip().lower() or "auto"

    async def analyze_image(
        self,
        image_base64: str,
        image_mime_type: str = "image/png",
        prompt: str = "Describe this image in detail.",
        max_tokens: int = 1000,
    ) -> str:
        normalized_image = (image_base64 or "").strip()
        if not normalized_image:
            raise ValueError("image_base64 must not be empty")

        normalized_mime_type = (image_mime_type or "").strip().lower() or "image/png"
        normalized_prompt = (prompt or "").strip() or "Describe this image in detail."
        normalized_tokens = max(32, min(int(max_tokens), 4096))
        request = VisionRequest(
            image_base64=normalized_image,
            image_mime_type=normalized_mime_type,
            prompt=normalized_prompt,
            max_tokens=normalized_tokens,
        )

        provider = self._resolve_provider()
        if provider == "ollama":
            return await self._analyze_ollama(request)
        if provider == "openai":
            return await self._analyze_openai(request)
        if provider == "gemini":
            return await self._analyze_gemini(request)
        raise ValueError(f"Unknown vision provider: {provider}")

    def _resolve_provider(self) -> str:
        if self.provider in {"ollama", "openai", "gemini"}:
            return self.provider
        lowered_url = self.base_url.lower()
        lowered_model = self.model.lower()
        if "generativelanguage.googleapis.com" in lowered_url or lowered_model.startswith("gemini"):
            return "gemini"
        if "/v1" in lowered_url:
            return "openai"
        return "ollama"

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: dict | None = None,
    ) -> dict:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.request(method=method, url=url, headers=headers, json=json_body)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Vision provider returned non-object response")
        return payload

    async def _analyze_ollama(self, request: VisionRequest) -> str:
        if not self.base_url:
            raise ValueError("VISION_BASE_URL is required for ollama provider")
        payload = await self._request_json(
            "POST",
            f"{self.base_url}/api/generate",
            json_body={
                "model": self.model,
                "prompt": request.prompt,
                "images": [request.image_base64],
                "stream": False,
                "options": {"num_predict": request.max_tokens},
            },
        )
        text = str(payload.get("response", "")).strip()
        if not text:
            raise ValueError("Vision provider returned empty response")
        return text

    async def _analyze_openai(self, request: VisionRequest) -> str:
        if not self.base_url:
            raise ValueError("VISION_BASE_URL is required for openai provider")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = await self._request_json(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=headers,
            json_body={
                "model": self.model,
                "max_tokens": request.max_tokens,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": request.prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{request.image_mime_type};base64,{request.image_base64}"
                                },
                            },
                        ],
                    }
                ],
            },
        )
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("Vision provider returned no choices")
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first.get("message"), dict) else {}
        text = str(message.get("content", "")).strip()
        if not text:
            raise ValueError("Vision provider returned empty content")
        return text

    async def _analyze_gemini(self, request: VisionRequest) -> str:
        api_key = self.api_key
        if not api_key:
            raise ValueError("VISION_API_KEY is required for gemini provider")
        model_name = self.model or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        payload = await self._request_json(
            "POST",
            url,
            json_body={
                "contents": [
                    {
                        "parts": [
                            {"text": request.prompt},
                            {
                                "inline_data": {
                                    "mime_type": request.image_mime_type,
                                    "data": request.image_base64,
                                }
                            },
                        ]
                    }
                ],
                "generationConfig": {"maxOutputTokens": request.max_tokens},
            },
        )
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("Vision provider returned no candidates")
        first = candidates[0] if isinstance(candidates[0], dict) else {}
        content = first.get("content") if isinstance(first.get("content"), dict) else {}
        parts = content.get("parts") if isinstance(content.get("parts"), list) else []
        texts = [str(item.get("text", "")).strip() for item in parts if isinstance(item, dict)]
        combined = "\n".join(part for part in texts if part)
        if not combined:
            raise ValueError("Vision provider returned empty content")
        return combined
