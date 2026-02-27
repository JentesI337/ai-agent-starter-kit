from __future__ import annotations

from typing import AsyncGenerator
import httpx
import json

from app.errors import LlmClientError


class LlmClient:
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def stream_chat_completion(
        self, system_prompt: str, user_prompt: str, model: str | None = None
    ) -> AsyncGenerator[str, None]:
        payload = {
            "model": model or self.model,
            "stream": True,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        raise LlmClientError(f"LLM stream request failed ({response.status_code}): {body.decode(errors='ignore')[:600]}")

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line.removeprefix("data:").strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = (
                                chunk.get("choices", [{}])[0]
                                .get("delta", {})
                                .get("content", "")
                            )
                            if delta:
                                yield delta
                        except Exception:
                            continue
        except httpx.TimeoutException as exc:
            raise LlmClientError(f"LLM timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LlmClientError(f"LLM HTTP error: {exc}") from exc

    async def complete_chat(
        self, system_prompt: str, user_prompt: str, model: str | None = None
    ) -> str:
        payload = {
            "model": model or self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code >= 400:
                    raise LlmClientError(
                        f"LLM request failed ({response.status_code}): {response.text[:600]}"
                    )
                data = response.json()
                return (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
        except httpx.TimeoutException as exc:
            raise LlmClientError(f"LLM timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LlmClientError(f"LLM HTTP error: {exc}") from exc
