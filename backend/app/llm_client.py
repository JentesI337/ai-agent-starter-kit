from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator
import httpx
import json

from app.config import settings
from app.errors import LlmClientError

logger = logging.getLogger("app.llm_client")

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 0.8


class LlmClient:
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        auth_token = (settings.api_auth_token or "").strip()
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        return headers

    def _is_native_ollama_api(self) -> bool:
        base = self.base_url.lower().rstrip("/")
        return base.endswith("/api")

    def _require_non_empty_completion(self, *, content: str, model: str, endpoint: str) -> str:
        text = (content or "").strip()
        if text:
            return text
        raise LlmClientError(
            f"LLM returned empty completion content (model={model}, endpoint={endpoint})."
        )

    def _normalize_temperature(self, temperature: float | None) -> float | None:
        if temperature is None:
            return None
        try:
            value = float(temperature)
        except (TypeError, ValueError):
            return None
        return min(2.0, max(0.0, value))

    async def stream_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float | None = None,
    ) -> AsyncGenerator[str, None]:
        active_model = model or self.model
        normalized_temperature = self._normalize_temperature(temperature)
        logger.info(
            "llm_stream_start base_url=%s model=%s native_api=%s prompt_len=%s",
            self.base_url,
            active_model,
            self._is_native_ollama_api(),
            len(user_prompt or ""),
        )
        if self._is_native_ollama_api():
            async for token in self._stream_chat_completion_ollama(
                system_prompt,
                user_prompt,
                model,
                temperature=normalized_temperature,
            ):
                yield token
            return

        payload = {
            "model": model or self.model,
            "stream": True,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if normalized_temperature is not None:
            payload["temperature"] = normalized_temperature

        headers = self._build_headers()

        url = f"{self.base_url}/chat/completions"

        try:
            for attempt in range(1, MAX_RETRIES + 1):
                async with httpx.AsyncClient(timeout=120) as client:
                    async with client.stream("POST", url, headers=headers, json=payload) as response:
                        if response.status_code >= 400:
                            body = await response.aread()
                            body_text = body.decode(errors='ignore')
                            logger.warning(
                                "llm_stream_http_error url=%s model=%s status=%s attempt=%s body=%s",
                                url,
                                active_model,
                                response.status_code,
                                attempt,
                                body_text[:300],
                            )
                            if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                                await asyncio.sleep(RETRY_DELAY_SECONDS * attempt)
                                continue
                            raise LlmClientError(f"LLM stream request failed ({response.status_code}): {body_text[:600]}")

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
                        return
        except httpx.TimeoutException as exc:
            logger.warning("llm_stream_timeout base_url=%s model=%s error=%s", self.base_url, active_model, exc)
            raise LlmClientError(f"LLM timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            logger.warning("llm_stream_httpx_error base_url=%s model=%s error=%s", self.base_url, active_model, exc)
            raise LlmClientError(f"LLM HTTP error: {exc}") from exc

    async def _stream_chat_completion_ollama(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float | None = None,
    ) -> AsyncGenerator[str, None]:
        active_model = model or self.model
        payload = {
            "model": active_model,
            "stream": True,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        normalized_temperature = self._normalize_temperature(temperature)
        if normalized_temperature is not None:
            payload["options"] = {"temperature": normalized_temperature}
        headers = self._build_headers()
        url = f"{self.base_url}/chat"

        try:
            for attempt in range(1, MAX_RETRIES + 1):
                async with httpx.AsyncClient(timeout=120) as client:
                    async with client.stream("POST", url, headers=headers, json=payload) as response:
                        if response.status_code >= 400:
                            body = await response.aread()
                            body_text = body.decode(errors='ignore')
                            logger.warning(
                                "llm_native_stream_http_error url=%s model=%s status=%s attempt=%s body=%s",
                                url,
                                active_model,
                                response.status_code,
                                attempt,
                                body_text[:300],
                            )
                            if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                                await asyncio.sleep(RETRY_DELAY_SECONDS * attempt)
                                continue
                            raise LlmClientError(
                                f"LLM stream request failed ({response.status_code}): {body_text[:600]}"
                            )

                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            try:
                                chunk = json.loads(line)
                            except Exception:
                                continue
                            delta = (chunk.get("message") or {}).get("content", "")
                            if delta:
                                yield delta
                            if chunk.get("done"):
                                break
                        return
        except httpx.TimeoutException as exc:
            logger.warning("llm_native_stream_timeout base_url=%s model=%s error=%s", self.base_url, active_model, exc)
            raise LlmClientError(f"LLM timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            logger.warning("llm_native_stream_httpx_error base_url=%s model=%s error=%s", self.base_url, active_model, exc)
            raise LlmClientError(f"LLM HTTP error: {exc}") from exc

    async def complete_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        active_model = model or self.model
        normalized_temperature = self._normalize_temperature(temperature)
        if self._is_native_ollama_api():
            return await self._complete_chat_ollama(
                system_prompt,
                user_prompt,
                model,
                temperature=normalized_temperature,
            )

        payload = {
            "model": active_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if normalized_temperature is not None:
            payload["temperature"] = normalized_temperature

        headers = self._build_headers()

        url = f"{self.base_url}/chat/completions"

        try:
            for attempt in range(1, MAX_RETRIES + 1):
                async with httpx.AsyncClient(timeout=120) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    if response.status_code >= 400:
                        logger.warning(
                            "llm_complete_http_error url=%s model=%s status=%s attempt=%s body=%s",
                            url,
                            active_model,
                            response.status_code,
                            attempt,
                            response.text[:300],
                        )
                        if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY_SECONDS * attempt)
                            continue
                        raise LlmClientError(
                            f"LLM request failed ({response.status_code}): {response.text[:600]}"
                        )
                    data = response.json()
                    content = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                    return self._require_non_empty_completion(
                        content=content,
                        model=active_model,
                        endpoint="chat/completions",
                    )
        except httpx.TimeoutException as exc:
            logger.warning("llm_complete_timeout base_url=%s model=%s error=%s", self.base_url, active_model, exc)
            raise LlmClientError(f"LLM timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            logger.warning("llm_complete_httpx_error base_url=%s model=%s error=%s", self.base_url, active_model, exc)
            raise LlmClientError(f"LLM HTTP error: {exc}") from exc

    async def _complete_chat_ollama(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        active_model = model or self.model
        payload = {
            "model": active_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        normalized_temperature = self._normalize_temperature(temperature)
        if normalized_temperature is not None:
            payload["options"] = {"temperature": normalized_temperature}
        headers = self._build_headers()
        url = f"{self.base_url}/chat"

        try:
            for attempt in range(1, MAX_RETRIES + 1):
                async with httpx.AsyncClient(timeout=120) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    if response.status_code >= 400:
                        logger.warning(
                            "llm_native_complete_http_error url=%s model=%s status=%s attempt=%s body=%s",
                            url,
                            active_model,
                            response.status_code,
                            attempt,
                            response.text[:300],
                        )
                        if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY_SECONDS * attempt)
                            continue
                        raise LlmClientError(
                            f"LLM request failed ({response.status_code}): {response.text[:600]}"
                        )
                    data = response.json()
                    content = ((data.get("message") or {}).get("content") or "")
                    return self._require_non_empty_completion(
                        content=content,
                        model=active_model,
                        endpoint="chat",
                    )
        except httpx.TimeoutException as exc:
            logger.warning("llm_native_complete_timeout base_url=%s model=%s error=%s", self.base_url, active_model, exc)
            raise LlmClientError(f"LLM timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            logger.warning("llm_native_complete_httpx_error base_url=%s model=%s error=%s", self.base_url, active_model, exc)
            raise LlmClientError(f"LLM HTTP error: {exc}") from exc
