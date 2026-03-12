from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import AsyncGenerator, Awaitable, Callable

import httpx

from app.config import settings
from app.errors import LlmClientError, LlmResourceExhaustedError, LlmTimeoutError
from app.url_validator import UrlValidationError, validate_llm_base_url

logger = logging.getLogger("app.llm_client")

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
# N-3: Basis für exponentielles Backoff (0.8s, 1.6s, 3.2s …) + 20 % Jitter
# verhindert thundering-herd bei gleichzeitigen Rate-Limit-Antworten.
RETRY_BASE_DELAY_SECONDS = 0.8
RETRY_MAX_DELAY_SECONDS = 30.0


def _retry_delay(attempt: int) -> float:
    """Exponentielles Backoff: base * 2^(attempt-1), gekappt auf max, +20%-Jitter."""
    delay = min(RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)), RETRY_MAX_DELAY_SECONDS)
    delay += random.uniform(0.0, delay * 0.2)
    return delay


# Patterns in error bodies that indicate a permanent resource constraint.
# These should NOT be retried on the same model — the model simply can't run.
_RESOURCE_EXHAUSTED_PATTERNS: tuple[str, ...] = (
    "requires more system memory",
    "out of memory",
    "insufficient memory",
    "not enough memory",
    "oom",
    "cuda out of memory",
    "gpu memory",
)


def _is_resource_exhausted(body_text: str) -> bool:
    """Return True if the error body indicates a permanent resource constraint."""
    lower = body_text.lower()
    return any(pattern in lower for pattern in _RESOURCE_EXHAUSTED_PATTERNS)


class LlmClient:
    def __init__(self, base_url: str, model: str):
        # SEC (SSRF-01): Validate the base URL against SSRF attacks.
        # Blocks cloud-metadata endpoints, validates IP ranges, and
        # allows localhost for local dev (Ollama, LM Studio).
        try:
            self.base_url = validate_llm_base_url(base_url)
        except UrlValidationError as exc:
            raise LlmClientError(f"LLM base URL validation failed: {exc}") from exc
        self.model = model

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        # SEC (OE-04): Use dedicated LLM API key — never fall back to
        # the internal auth token to avoid leaking it to external LLM providers.
        auth_token = (settings.llm_api_key or "").strip()
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        return headers

    def _is_native_ollama_api(self) -> bool:
        base = self.base_url.lower().rstrip("/")
        return base.endswith("/api")

    @property
    def supports_function_calling(self) -> bool:
        return not self._is_native_ollama_api()

    def _require_non_empty_completion(self, *, content: str, model: str, endpoint: str) -> str:
        text = (content or "").strip()
        if text:
            return text
        raise LlmClientError(f"LLM returned empty completion content (model={model}, endpoint={endpoint}).")

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
                async with (
                    httpx.AsyncClient(timeout=settings.llm_request_timeout_seconds) as client,
                    client.stream("POST", url, headers=headers, json=payload) as response,
                ):
                    if response.status_code >= 400:
                        body = await response.aread()
                        body_text = body.decode(errors="ignore")
                        logger.warning(
                            "llm_stream_http_error url=%s model=%s status=%s attempt=%s body=%s",
                            url,
                            active_model,
                            response.status_code,
                            attempt,
                            body_text[:300],
                        )
                        if _is_resource_exhausted(body_text):
                            raise LlmResourceExhaustedError(
                                f"Model requires more resources than available: {body_text[:600]}"
                            )
                        if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                            await asyncio.sleep(_retry_delay(attempt))
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
                            delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            continue
                    return
        except GeneratorExit:
            # The consumer (e.g. asyncio.wait_for timeout) closed the generator.
            # Return cleanly so the surrounding async-with blocks can run their
            # __aexit__ and close the HTTP connection without propagating
            # GeneratorExit into httpcore's instrumentation path.
            return
        except httpx.TimeoutException as exc:
            logger.warning("llm_stream_timeout base_url=%s model=%s error=%s", self.base_url, active_model, exc)
            raise LlmTimeoutError(f"LLM timeout: {exc}") from exc
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
                async with (
                    httpx.AsyncClient(timeout=settings.llm_request_timeout_seconds) as client,
                    client.stream("POST", url, headers=headers, json=payload) as response,
                ):
                    if response.status_code >= 400:
                        body = await response.aread()
                        body_text = body.decode(errors="ignore")
                        logger.warning(
                            "llm_native_stream_http_error url=%s model=%s status=%s attempt=%s body=%s",
                            url,
                            active_model,
                            response.status_code,
                            attempt,
                            body_text[:300],
                        )
                        if _is_resource_exhausted(body_text):
                            raise LlmResourceExhaustedError(
                                f"Model requires more resources than available: {body_text[:600]}"
                            )
                        if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                            await asyncio.sleep(_retry_delay(attempt))
                            continue
                        raise LlmClientError(f"LLM stream request failed ({response.status_code}): {body_text[:600]}")

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
        except GeneratorExit:
            # Same as above: clean up on consumer cancellation without
            # leaking GeneratorExit into the httpcore connection machinery.
            return
        except httpx.TimeoutException as exc:
            logger.warning("llm_native_stream_timeout base_url=%s model=%s error=%s", self.base_url, active_model, exc)
            raise LlmTimeoutError(f"LLM timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "llm_native_stream_httpx_error base_url=%s model=%s error=%s", self.base_url, active_model, exc
            )
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
                async with httpx.AsyncClient(timeout=settings.llm_request_timeout_seconds) as client:
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
                        if _is_resource_exhausted(response.text):
                            raise LlmResourceExhaustedError(
                                f"Model requires more resources than available: {response.text[:600]}"
                            )
                        if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                            await asyncio.sleep(_retry_delay(attempt))
                            continue
                        raise LlmClientError(f"LLM request failed ({response.status_code}): {response.text[:600]}")
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return self._require_non_empty_completion(
                        content=content,
                        model=active_model,
                        endpoint="chat/completions",
                    )
        except httpx.TimeoutException as exc:
            logger.warning("llm_complete_timeout base_url=%s model=%s error=%s", self.base_url, active_model, exc)
            raise LlmTimeoutError(f"LLM timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            logger.warning("llm_complete_httpx_error base_url=%s model=%s error=%s", self.base_url, active_model, exc)
            raise LlmClientError(f"LLM HTTP error: {exc}") from exc

    async def complete_chat_with_tools(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        allowed_tools: list[str],
        tool_definitions: list[dict] | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> list[dict]:
        if not self.supports_function_calling:
            return []

        active_model = model or self.model
        normalized_temperature = self._normalize_temperature(temperature)
        resolved_tool_definitions = [item for item in (tool_definitions or []) if isinstance(item, dict)]
        if not resolved_tool_definitions:
            resolved_tool_definitions = [
                {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": f"Execute tool '{tool_name}'",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": True,
                        },
                    },
                }
                for tool_name in allowed_tools
                if isinstance(tool_name, str) and tool_name.strip()
            ]

        if not resolved_tool_definitions:
            return []

        payload = {
            "model": active_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "tools": resolved_tool_definitions,
            "tool_choice": "auto",
        }
        if normalized_temperature is not None:
            payload["temperature"] = normalized_temperature

        headers = self._build_headers()
        url = f"{self.base_url}/chat/completions"

        try:
            for attempt in range(1, MAX_RETRIES + 1):
                async with httpx.AsyncClient(timeout=settings.llm_request_timeout_seconds) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    if response.status_code >= 400:
                        logger.warning(
                            "llm_tools_http_error url=%s model=%s status=%s attempt=%s body=%s",
                            url,
                            active_model,
                            response.status_code,
                            attempt,
                            response.text[:300],
                        )
                        if _is_resource_exhausted(response.text):
                            raise LlmResourceExhaustedError(
                                f"Model requires more resources than available: {response.text[:600]}"
                            )
                        if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                            await asyncio.sleep(_retry_delay(attempt))
                            continue
                        raise LlmClientError(f"LLM request failed ({response.status_code}): {response.text[:600]}")

                    data = response.json()
                    choices = data.get("choices") if isinstance(data, dict) else None
                    if not isinstance(choices, list) or not choices:
                        return []
                    message = (choices[0] or {}).get("message")
                    if not isinstance(message, dict):
                        return []
                    tool_calls = message.get("tool_calls")
                    if not isinstance(tool_calls, list):
                        return []

                    actions: list[dict] = []
                    for tool_call in tool_calls:
                        if not isinstance(tool_call, dict):
                            continue
                        function_payload = tool_call.get("function")
                        if not isinstance(function_payload, dict):
                            continue
                        tool_name = str(function_payload.get("name", "")).strip()
                        if not tool_name:
                            continue
                        raw_arguments = function_payload.get("arguments")
                        parsed_args: dict = {}
                        if isinstance(raw_arguments, str) and raw_arguments.strip():
                            try:
                                parsed = json.loads(raw_arguments)
                            except Exception:
                                parsed = {}
                            if isinstance(parsed, dict):
                                parsed_args = parsed
                        actions.append({"tool": tool_name, "args": parsed_args})

                    return actions
        except httpx.TimeoutException as exc:
            logger.warning("llm_tools_timeout base_url=%s model=%s error=%s", self.base_url, active_model, exc)
            raise LlmTimeoutError(f"LLM timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            logger.warning("llm_tools_httpx_error base_url=%s model=%s error=%s", self.base_url, active_model, exc)
            raise LlmClientError(f"LLM HTTP error: {exc}") from exc
        return []

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
                async with httpx.AsyncClient(timeout=settings.llm_request_timeout_seconds) as client:
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
                        if _is_resource_exhausted(response.text):
                            raise LlmResourceExhaustedError(
                                f"Model requires more resources than available: {response.text[:600]}"
                            )
                        if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                            await asyncio.sleep(_retry_delay(attempt))
                            continue
                        raise LlmClientError(f"LLM request failed ({response.status_code}): {response.text[:600]}")
                    data = response.json()
                    content = (data.get("message") or {}).get("content") or ""
                    return self._require_non_empty_completion(
                        content=content,
                        model=active_model,
                        endpoint="chat",
                    )
        except httpx.TimeoutException as exc:
            logger.warning(
                "llm_native_complete_timeout base_url=%s model=%s error=%s", self.base_url, active_model, exc
            )
            raise LlmTimeoutError(f"LLM timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "llm_native_complete_httpx_error base_url=%s model=%s error=%s", self.base_url, active_model, exc
            )
            raise LlmClientError(f"LLM HTTP error: {exc}") from exc

    # ------------------------------------------------------------------
    # AgentRunner: Streaming with function calling (Continuous Tool Loop)
    # ------------------------------------------------------------------

    async def stream_chat_with_tools(
        self,
        *,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        on_text_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> "StreamResult":
        """Stream an LLM response, collecting text and tool_calls.

        Accepts a full messages array (not just system+user like older methods).
        Streams text via *on_text_chunk* callback while accumulating tool_calls.
        Returns a structured ``StreamResult``.

        For providers that don't support streaming (native Ollama API) a
        non-streaming fallback is used automatically.
        """
        from app.agent_runner_types import StreamResult, ToolCall

        active_model = model or self.model
        normalized_temperature = self._normalize_temperature(temperature)

        # ── Ollama native: non-streaming fallback ──
        if self._is_native_ollama_api():
            return await self._stream_chat_with_tools_ollama_fallback(
                messages=messages,
                model=active_model,
                temperature=normalized_temperature,
                on_text_chunk=on_text_chunk,
            )

        payload: dict = {
            "model": active_model,
            "stream": True,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if normalized_temperature is not None:
            payload["temperature"] = normalized_temperature

        headers = self._build_headers()
        url = f"{self.base_url}/chat/completions"

        collected_text: list[str] = []
        collected_tool_calls: dict[int, dict] = {}  # index → {id, name, arguments_str}
        finish_reason = "stop"
        usage: dict = {}

        try:
            for attempt in range(1, MAX_RETRIES + 1):
                async with (
                    httpx.AsyncClient(timeout=settings.llm_request_timeout_seconds) as client,
                    client.stream("POST", url, headers=headers, json=payload) as response,
                ):
                    if response.status_code >= 400:
                        body = await response.aread()
                        body_text = body.decode(errors="ignore")
                        logger.warning(
                            "llm_stream_tools_http_error url=%s model=%s status=%s attempt=%s body=%s",
                            url, active_model, response.status_code, attempt, body_text[:300],
                        )
                        if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                            await asyncio.sleep(_retry_delay(attempt))
                            continue
                        raise LlmClientError(
                            f"LLM stream request failed ({response.status_code}): {body_text[:600]}"
                        )

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line.removeprefix("data:").strip()
                        if data_str == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data_str)
                        except Exception:
                            continue

                        choice = (chunk.get("choices") or [{}])[0]
                        delta = choice.get("delta") or {}
                        chunk_finish = choice.get("finish_reason")

                        # Text content
                        if delta.get("content"):
                            text_piece = delta["content"]
                            collected_text.append(text_piece)
                            if on_text_chunk:
                                await on_text_chunk(text_piece)

                        # Tool calls (arrive in chunks)
                        if "tool_calls" in delta:
                            for tc in delta["tool_calls"]:
                                idx = tc.get("index", 0)
                                if idx not in collected_tool_calls:
                                    collected_tool_calls[idx] = {
                                        "id": tc.get("id", ""),
                                        "name": (tc.get("function") or {}).get("name", ""),
                                        "arguments_str": "",
                                    }
                                func = tc.get("function") or {}
                                if func.get("name"):
                                    collected_tool_calls[idx]["name"] = func["name"]
                                if tc.get("id"):
                                    collected_tool_calls[idx]["id"] = tc["id"]
                                if func.get("arguments"):
                                    collected_tool_calls[idx]["arguments_str"] += func["arguments"]

                        if chunk_finish:
                            finish_reason = chunk_finish

                        if "usage" in chunk and isinstance(chunk["usage"], dict):
                            usage = chunk["usage"]

                    # Successful response processed
                    break

        except httpx.TimeoutException as exc:
            logger.warning(
                "llm_stream_tools_timeout base_url=%s model=%s error=%s",
                self.base_url, active_model, exc,
            )
            raise LlmTimeoutError(f"LLM timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "llm_stream_tools_httpx_error base_url=%s model=%s error=%s",
                self.base_url, active_model, exc,
            )
            raise LlmClientError(f"LLM HTTP error: {exc}") from exc

        # Parse collected tool calls
        parsed_tool_calls: list[ToolCall] = []
        for idx in sorted(collected_tool_calls.keys()):
            tc = collected_tool_calls[idx]
            try:
                args = json.loads(tc["arguments_str"]) if tc["arguments_str"] else {}
            except (json.JSONDecodeError, ValueError):
                args = {"_raw": tc["arguments_str"]}
            if not isinstance(args, dict):
                args = {"_raw": tc["arguments_str"]}
            parsed_tool_calls.append(
                ToolCall(id=tc["id"], name=tc["name"], arguments=args)
            )

        # Normalize finish_reason for tool calls
        if finish_reason == "tool_calls" or (parsed_tool_calls and finish_reason != "length"):
            finish_reason = "tool_calls"

        return StreamResult(
            text="".join(collected_text),
            tool_calls=tuple(parsed_tool_calls),
            finish_reason=finish_reason,
            usage=usage,
        )

    async def _stream_chat_with_tools_ollama_fallback(
        self,
        *,
        messages: list[dict],
        model: str,
        temperature: float | None = None,
        on_text_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> "StreamResult":
        """Non-streaming fallback for Ollama native API."""
        from app.agent_runner_types import StreamResult

        payload: dict = {
            "model": model,
            "stream": False,
            "messages": messages,
        }
        if temperature is not None:
            payload["options"] = {"temperature": temperature}

        headers = self._build_headers()
        url = f"{self.base_url}/chat"

        try:
            for attempt in range(1, MAX_RETRIES + 1):
                async with httpx.AsyncClient(timeout=settings.llm_request_timeout_seconds) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    if response.status_code >= 400:
                        logger.warning(
                            "llm_native_tools_http_error url=%s model=%s status=%s attempt=%s body=%s",
                            url, model, response.status_code, attempt, response.text[:300],
                        )
                        if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                            await asyncio.sleep(_retry_delay(attempt))
                            continue
                        raise LlmClientError(
                            f"LLM request failed ({response.status_code}): {response.text[:600]}"
                        )
                    data = response.json()
                    content = (data.get("message") or {}).get("content") or ""
                    if content and on_text_chunk:
                        await on_text_chunk(content)

                    return StreamResult(
                        text=content,
                        tool_calls=(),
                        finish_reason="stop",
                        usage={},
                    )
        except httpx.TimeoutException as exc:
            logger.warning(
                "llm_native_tools_timeout base_url=%s model=%s error=%s",
                self.base_url, model, exc,
            )
            raise LlmTimeoutError(f"LLM timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "llm_native_tools_httpx_error base_url=%s model=%s error=%s",
                self.base_url, model, exc,
            )
            raise LlmClientError(f"LLM HTTP error: {exc}") from exc
