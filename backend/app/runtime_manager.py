from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.errors import RuntimeSwitchError

SendEvent = Callable[[dict], Awaitable[None]]


@dataclass
class RuntimeState:
    runtime: str
    base_url: str
    model: str
    features: dict[str, bool] = field(default_factory=dict)


RUNTIME_FEATURE_DEFAULTS: dict[str, bool] = {
    "long_term_memory_enabled": bool(settings.long_term_memory_enabled),
    "session_distillation_enabled": bool(settings.session_distillation_enabled),
    "failure_journal_enabled": bool(settings.failure_journal_enabled),
}


def _normalize_feature_flags(raw_flags: dict[str, object] | None) -> dict[str, bool]:
    merged: dict[str, bool] = dict(RUNTIME_FEATURE_DEFAULTS)
    if not isinstance(raw_flags, dict):
        return merged

    for key, value in raw_flags.items():
        if key not in RUNTIME_FEATURE_DEFAULTS:
            continue
        if isinstance(value, bool):
            merged[key] = value
            continue
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                merged[key] = True
                continue
            if lowered in {"0", "false", "no", "off"}:
                merged[key] = False
                continue
    return merged


class RuntimeManager:
    def __init__(self):
        self.state_file = Path(settings.runtime_state_file)
        if not self.state_file.is_absolute():
            self.state_file = (Path(settings.workspace_root) / self.state_file).resolve()
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        self._state = self._load_state() or RuntimeState(
            runtime="local",
            base_url=settings.llm_base_url,
            model=settings.local_model,
        )
        self._ollama_cmd = self._resolve_ollama_command()
        self._persist_state()

    def get_state(self) -> RuntimeState:
        return self._state

    def get_feature_flags(self) -> dict[str, bool]:
        self._state.features = _normalize_feature_flags(self._state.features)
        return dict(self._state.features)

    def update_feature_flags(self, updates: dict[str, object]) -> dict[str, bool]:
        unknown_keys = sorted(key for key in updates.keys() if key not in RUNTIME_FEATURE_DEFAULTS)
        if unknown_keys:
            raise RuntimeSwitchError(
                f"Unsupported runtime feature flag(s): {', '.join(unknown_keys)}"
            )

        normalized_current = _normalize_feature_flags(self._state.features)
        normalized_updates = _normalize_feature_flags({**normalized_current, **updates})
        self._state.features = normalized_updates
        self._persist_state()
        return dict(self._state.features)

    def set_active_model(self, model: str) -> None:
        self._state.model = model.strip()
        self._persist_state()

    def _is_runtime_authenticated(self, runtime: str | None) -> bool:
        active_runtime = (runtime or "").strip().lower()
        if active_runtime != "api":
            return True
        if not settings.api_auth_required:
            return True
        return bool((settings.api_auth_token or "").strip())

    def is_runtime_authenticated(self) -> bool:
        return self._is_runtime_authenticated(self._state.runtime)

    async def ensure_api_runtime_authenticated(self, runtime: str | None = None) -> None:
        active_runtime = (runtime or self._state.runtime or "").strip().lower()
        if active_runtime != "api":
            return
        if self._is_runtime_authenticated(active_runtime):
            return
        raise RuntimeSwitchError(
            "API runtime authentication required but no token configured. "
            "Set API_AUTH_TOKEN (or OLLAMA_API_KEY) or disable API_AUTH_REQUIRED."
        )

    async def switch_runtime(self, target: str, send_event: SendEvent, session_id: str) -> RuntimeState:
        if target not in ("local", "api"):
            raise RuntimeSwitchError(f"Unsupported runtime target: {target}")

        previous = RuntimeState(**asdict(self._state))
        last_error: Exception | None = None

        for attempt in (1, 2):
            try:
                await self._log(send_event, session_id, "switch_started", attempt, f"Switching to {target}")
                next_state = self._build_target_state(target)

                if target == "api":
                    await self.ensure_api_runtime_authenticated(runtime=target)
                    await self._start_gateway(send_event, session_id, attempt, next_state.base_url)
                    await self._log(send_event, session_id, "api_model_selected", attempt, f"Using API model {settings.api_model}")
                    next_state.model = settings.api_model
                else:
                    await self._start_gateway(send_event, session_id, attempt, next_state.base_url)
                    next_state.model = await self._ensure_model_available(send_event, session_id, attempt, settings.local_model)

                self._state = next_state
                self._state.features = _normalize_feature_flags(previous.features)
                self._persist_state()
                await self._log(send_event, session_id, "switch_committed", attempt, f"Runtime active: {self._state.runtime}")
                return self._state
            except Exception as exc:
                last_error = exc
                await self._log(send_event, session_id, "switch_attempt_failed", attempt, str(exc), level="error")

        self._state = previous
        self._persist_state()
        await self._log(send_event, session_id, "switch_rollback", 2, f"Rollback to {previous.runtime}", level="error")
        raise RuntimeSwitchError(str(last_error) if last_error else "Runtime switch failed")

    async def ensure_model_ready(self, send_event: SendEvent, session_id: str, model_name: str) -> str:
        return await self._ensure_model_available(send_event, session_id, 1, model_name)

    async def resolve_api_request_model(self, model_name: str) -> str:
        await self.ensure_api_runtime_authenticated()
        requested = (model_name or self._state.model or settings.api_model).strip()
        return requested or settings.api_model

    async def get_api_models_summary(self) -> dict:
        if self._state.runtime != "api":
            return {
                "available": None,
                "count": None,
                "error": None,
            }

        try:
            await self.ensure_api_runtime_authenticated()
            models = await self._fetch_available_api_models()
            if models:
                return {
                    "available": True,
                    "count": len(models),
                    "error": None,
                }

            base_url = (self._state.base_url or settings.api_base_url).rstrip("/")
            if self._is_ollama_native_api(base_url):
                return {
                    "available": None,
                    "count": None,
                    "error": None,
                }

            return {
                "available": False,
                "count": 0,
                "error": "API endpoint returned no models.",
            }
        except RuntimeSwitchError as exc:
            return {
                "available": False,
                "count": 0,
                "error": str(exc),
            }

    async def _start_gateway(self, send_event: SendEvent, session_id: str, attempt: int, base_url: str) -> None:
        port = self._extract_port(base_url)
        if not self._is_port_open(port):
            await self._log(send_event, session_id, "start_gateway", attempt, f"Starting gateway on port {port}")
            env = os.environ.copy()
            env["OLLAMA_HOST"] = f"127.0.0.1:{port}"
            if os.name == "nt":
                subprocess.Popen(
                    [self._ollama_cmd, "serve"],
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    env=env,
                )
            else:
                subprocess.Popen(
                    [self._ollama_cmd, "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=env,
                )

        for _ in range(10):
            if self._is_port_open(port):
                await self._log(send_event, session_id, "gateway_ready", attempt, f"Gateway ready on port {port}")
                return
            await asyncio.sleep(0.5)
        raise RuntimeSwitchError(f"Gateway not reachable on port {port}")

    async def _ensure_model_available(self, send_event: SendEvent, session_id: str, attempt: int, model_name: str) -> str:
        candidates = self._candidate_models(model_name)
        await self._log(send_event, session_id, "ensure_model", attempt, f"Ensuring model {model_name}")
        listed = await asyncio.to_thread(
            subprocess.run,
            [self._ollama_cmd, "list"],
            capture_output=True,
            text=True,
        )
        listed_output = listed.stdout or ""

        for candidate in candidates:
            if candidate in listed_output:
                await self._log(send_event, session_id, "model_available", attempt, candidate)
                return candidate

        last_error = ""
        for candidate in candidates:
            await self._log(send_event, session_id, "model_pull_started", attempt, f"Pulling model {candidate}")
            try:
                pull = await asyncio.to_thread(
                    subprocess.run,
                    [self._ollama_cmd, "pull", candidate],
                    capture_output=True,
                    text=True,
                    timeout=900,
                )
            except subprocess.TimeoutExpired:
                await self._log(
                    send_event,
                    session_id,
                    "model_pull_timeout",
                    attempt,
                    f"Model pull timed out for {candidate}",
                    level="error",
                )
                raise RuntimeSwitchError(f"Model pull timed out for {candidate}. Check network or try pulling manually.")
            if pull.returncode == 0:
                await self._log(send_event, session_id, "model_downloaded", attempt, candidate)
                return candidate
            last_error = (pull.stderr or pull.stdout or "").strip()
            await self._log(
                send_event,
                session_id,
                "model_pull_failed",
                attempt,
                f"Pull failed for {candidate}: {last_error[:300]}",
                level="warning",
            )

        raise RuntimeSwitchError(f"Model pull failed for {candidates}: {last_error}")

    def _build_target_state(self, target: str) -> RuntimeState:
        if target == "local":
            return RuntimeState(
                runtime="local",
                base_url=settings.llm_base_url,
                model=settings.local_model,
            )
        return RuntimeState(
            runtime="api",
            base_url=settings.api_base_url,
            model=settings.api_model,
        )

    async def _log(self, send_event: SendEvent, session_id: str, step: str, attempt: int, message: str, level: str = "info") -> None:
        await send_event(
            {
                "type": "runtime_switch_progress",
                "session_id": session_id,
                "step": step,
                "attempt": attempt,
                "level": level,
                "message": message,
            }
        )

    def _is_port_open(self, port: int) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        try:
            sock.connect(("127.0.0.1", port))
            return True
        except Exception:
            return False
        finally:
            sock.close()

    def _extract_port(self, base_url: str) -> int:
        parsed = urlparse(base_url)
        if parsed.port:
            return parsed.port
        return 443 if parsed.scheme == "https" else 80

    def _load_state(self) -> RuntimeState | None:
        if not self.state_file.exists():
            return None
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8-sig"))
            return RuntimeState(
                runtime=data.get("runtime", "local"),
                base_url=data.get("base_url", settings.llm_base_url),
                model=data.get("model", settings.local_model),
                features=_normalize_feature_flags(data.get("features")),
            )
        except Exception:
            return None

    def _persist_state(self) -> None:
        self.state_file.write_text(json.dumps(asdict(self._state), indent=2), encoding="utf-8")

    def _resolve_ollama_command(self) -> str:
        configured = (settings.ollama_bin or "").strip()
        if configured:
            if Path(configured).exists() or shutil.which(configured):
                return configured

        discovered = shutil.which("ollama")
        if discovered:
            return discovered

        if os.name == "nt":
            candidates = [
                Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe",
                Path("C:/Program Files/Ollama/ollama.exe"),
            ]
            for candidate in candidates:
                if candidate.exists():
                    return str(candidate)

        raise RuntimeSwitchError(
            "Ollama CLI not found. Install Ollama (https://ollama.com/download) or set OLLAMA_BIN in backend/.env."
        )

    def _candidate_models(self, model_name: str) -> list[str]:
        model = (model_name or "").strip()
        if not model:
            return []

        aliases: dict[str, list[str]] = {
            "qwen2.5:7b-instruct": ["qwen2.5:7b"],
        }

        candidates = [model]
        candidates.extend(aliases.get(model, []))
        deduped: list[str] = []
        for candidate in candidates:
            if candidate and candidate not in deduped:
                deduped.append(candidate)
        return deduped

    async def _fetch_available_api_models(self) -> list[str]:
        base_url = (self._state.base_url or settings.api_base_url).rstrip("/")
        native_api = self._is_ollama_native_api(base_url)
        url = f"{base_url}/tags" if native_api else f"{base_url}/models"

        headers: dict[str, str] = {}
        auth_token = (settings.api_auth_token or "").strip()
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        try:
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.get(url, headers=headers)
            if response.status_code >= 400:
                raise RuntimeSwitchError(
                    f"API model listing failed ({response.status_code}): {response.text[:300]}"
                )
            payload = response.json()
            models: list[str] = []
            if native_api:
                data = payload.get("models") if isinstance(payload, dict) else None
                if not isinstance(data, list):
                    return []
                for item in data:
                    if isinstance(item, dict):
                        model_id = item.get("name")
                        if isinstance(model_id, str) and model_id.strip():
                            models.append(model_id.strip())
            else:
                data = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(data, list):
                    return []
                for item in data:
                    if isinstance(item, dict):
                        model_id = item.get("id")
                        if isinstance(model_id, str) and model_id.strip():
                            models.append(model_id.strip())
            return models
        except httpx.TimeoutException as exc:
            raise RuntimeSwitchError(f"API model listing timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeSwitchError(f"API model listing failed: {exc}") from exc

    def _is_ollama_native_api(self, base_url: str) -> bool:
        return base_url.lower().rstrip("/").endswith("/api")
