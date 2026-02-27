from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
import socket
import subprocess
import time
from typing import Callable, Awaitable
from urllib.parse import urlparse

from app.config import settings
from app.errors import RuntimeAuthRequiredError, RuntimeSwitchError

SendEvent = Callable[[dict], Awaitable[None]]


@dataclass
class RuntimeState:
    runtime: str
    base_url: str
    model: str
    api_key: str


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
            api_key=settings.llm_api_key,
        )
        self._ollama_cmd = self._resolve_ollama_command()
        self._persist_state()

    def get_state(self) -> RuntimeState:
        return self._state

    def set_api_key(self, api_key: str) -> None:
        self._state.api_key = api_key.strip()
        self._persist_state()

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
                    await self._stop_ollama_if_running(send_event, session_id, attempt)
                    await self._verify_ollama_stopped(send_event, session_id, attempt)
                    await self._start_gateway(send_event, session_id, attempt, next_state.base_url)
                    await self._check_auth(send_event, session_id, attempt)
                    await self._ensure_model_available(send_event, session_id, attempt, settings.api_model)
                else:
                    await self._start_gateway(send_event, session_id, attempt, next_state.base_url)
                    await self._ensure_model_available(send_event, session_id, attempt, settings.local_model)

                self._state = next_state
                self._persist_state()
                await self._log(send_event, session_id, "switch_committed", attempt, f"Runtime active: {self._state.runtime}")
                return self._state
            except RuntimeAuthRequiredError:
                raise
            except Exception as exc:
                last_error = exc
                await self._log(send_event, session_id, "switch_attempt_failed", attempt, str(exc), level="error")

        self._state = previous
        self._persist_state()
        await self._log(send_event, session_id, "switch_rollback", 2, f"Rollback to {previous.runtime}", level="error")
        raise RuntimeSwitchError(str(last_error) if last_error else "Runtime switch failed")

    async def _check_auth(self, send_event: SendEvent, session_id: str, attempt: int) -> None:
        auth_key = (self._state.api_key or settings.api_auth_key or "").strip()
        if self._is_valid_api_key(auth_key):
            self._state.api_key = auth_key
            self._persist_state()
            await self._log(send_event, session_id, "auth_ok", attempt, "API auth available")
            return

        auth_url = await self._discover_auth_url(send_event, session_id, attempt)

        await send_event(
            {
                "type": "runtime_auth_required",
                "auth_url": auth_url,
                "session_id": session_id,
                "message": "Login required for API runtime.",
            }
        )
        raise RuntimeAuthRequiredError(auth_url)

    async def _stop_ollama_if_running(self, send_event: SendEvent, session_id: str, attempt: int) -> None:
        await self._log(send_event, session_id, "stop_local_process", attempt, "Stopping local ollama process if running")
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"], capture_output=True, text=True)
            else:
                subprocess.run(["pkill", "-f", "ollama"], capture_output=True, text=True)
        except Exception:
            pass

    async def _verify_ollama_stopped(self, send_event: SendEvent, session_id: str, attempt: int) -> None:
        port = self._extract_port(settings.llm_base_url)
        if self._is_port_open(port):
            raise RuntimeSwitchError(f"Local process still active on port {port}")
        await self._log(send_event, session_id, "verify_local_stopped", attempt, "Local process stopped")

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
            time.sleep(0.5)
        raise RuntimeSwitchError(f"Gateway not reachable on port {port}")

    async def _ensure_model_available(self, send_event: SendEvent, session_id: str, attempt: int, model_name: str) -> None:
        await self._log(send_event, session_id, "ensure_model", attempt, f"Ensuring model {model_name}")
        listed = subprocess.run([self._ollama_cmd, "list"], capture_output=True, text=True)
        if model_name in (listed.stdout or ""):
            await self._log(send_event, session_id, "model_available", attempt, model_name)
            return

        pull = subprocess.run([self._ollama_cmd, "pull", model_name], capture_output=True, text=True)
        if pull.returncode != 0:
            raise RuntimeSwitchError(f"Model pull failed: {pull.stderr or pull.stdout}")
        await self._log(send_event, session_id, "model_downloaded", attempt, model_name)

    async def _discover_auth_url(self, send_event: SendEvent, session_id: str, attempt: int) -> str:
        await self._log(send_event, session_id, "auth_discovery", attempt, "Requesting login URL from Ollama CLI")
        default_url = settings.llama_auth_url

        try:
            login = subprocess.run(
                [self._ollama_cmd, "login"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            output = "\n".join([login.stdout or "", login.stderr or ""]).strip()
            auth_url = self._extract_auth_url(output) or default_url
            await self._log(send_event, session_id, "auth_url_ready", attempt, auth_url)
            return auth_url
        except subprocess.TimeoutExpired:
            await self._log(
                send_event,
                session_id,
                "auth_discovery_timeout",
                attempt,
                "Login URL discovery timed out, using fallback URL",
                level="warning",
            )
            return default_url
        except Exception as exc:
            await self._log(
                send_event,
                session_id,
                "auth_discovery_failed",
                attempt,
                f"Auth URL discovery failed: {exc}",
                level="warning",
            )
            return default_url

    def _build_target_state(self, target: str) -> RuntimeState:
        if target == "local":
            return RuntimeState(
                runtime="local",
                base_url=settings.llm_base_url,
                model=settings.local_model,
                api_key=settings.llm_api_key,
            )
        return RuntimeState(
            runtime="api",
            base_url=settings.api_base_url,
            model=settings.api_model,
            api_key=self._state.api_key or settings.api_auth_key,
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
                api_key=data.get("api_key", settings.llm_api_key),
            )
        except Exception:
            return None

    def _persist_state(self) -> None:
        self.state_file.write_text(json.dumps(asdict(self._state), indent=2), encoding="utf-8")

    def _is_valid_api_key(self, value: str) -> bool:
        return bool(value and value.lower() not in {"not-needed", "none", "null"})

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

    def _extract_auth_url(self, text: str) -> str | None:
        match = re.search(r"https?://[^\s\]\)\"']+", text or "")
        return match.group(0) if match else None
