"""Audio transcription service."""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
_MAX_DURATION_DEFAULT = 600  # 10 minutes


class AudioService:
    """Transcribe audio files via OpenAI API or local whisper CLI."""

    def __init__(
        self,
        provider: str = "openai",
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "whisper-1",
        max_duration_seconds: int = _MAX_DURATION_DEFAULT,
    ):
        self.provider = (provider or "local").strip().lower()
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "https://api.openai.com/v1").strip().rstrip("/")
        self.model = (model or "whisper-1").strip()
        self.max_duration_seconds = max_duration_seconds

    async def transcribe(self, path: Path) -> dict:
        """Transcribe an audio file to text with timestamps."""
        if not path.is_file():
            raise FileNotFoundError(f"Audio file not found: {path}")

        file_size = path.stat().st_size
        if file_size > _MAX_FILE_SIZE:
            raise ValueError(f"Audio file too large: {file_size} bytes (max {_MAX_FILE_SIZE})")

        # Check duration via ffprobe if available
        duration = await self._get_duration(path)
        if duration is not None and duration > self.max_duration_seconds:
            raise ValueError(
                f"Audio too long: {duration:.0f}s (max {self.max_duration_seconds}s)"
            )

        if self.provider == "openai":
            return await self._transcribe_openai(path)
        if self.provider == "local":
            return await self._transcribe_local(path)
        raise ValueError(f"Unknown audio provider: {self.provider}")

    async def _get_duration(self, path: Path) -> float | None:
        """Get audio duration via ffprobe. Returns None if ffprobe unavailable."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                info = json.loads(stdout)
                return float(info.get("format", {}).get("duration", 0))
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            pass
        return None

    async def _transcribe_openai(self, path: Path) -> dict:
        """Transcribe via OpenAI Whisper API."""
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=120.0) as client:
            with open(path, "rb") as f:
                response = await client.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers=headers,
                    data={"model": self.model, "response_format": "verbose_json"},
                    files={"file": (path.name, f, "application/octet-stream")},
                )
            response.raise_for_status()
            data = response.json()

        segments = []
        for seg in data.get("segments", []):
            segments.append({
                "start": float(seg.get("start", 0)),
                "end": float(seg.get("end", 0)),
                "text": str(seg.get("text", "")),
            })

        return {
            "text": str(data.get("text", "")),
            "segments": segments,
        }

    async def _transcribe_local(self, path: Path) -> dict:
        """Transcribe via local whisper CLI."""
        proc = await asyncio.create_subprocess_exec(
            "whisper", str(path), "--output_format", "json", "--output_dir", str(path.parent),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"whisper CLI failed: {stderr.decode()[:500]}")

        json_path = path.with_suffix(".json")
        if not json_path.is_file():
            raise RuntimeError("whisper CLI did not produce JSON output")

        data = json.loads(json_path.read_text(encoding="utf-8"))

        segments = []
        for seg in data.get("segments", []):
            segments.append({
                "start": float(seg.get("start", 0)),
                "end": float(seg.get("end", 0)),
                "text": str(seg.get("text", "")),
            })

        return {
            "text": str(data.get("text", "")),
            "segments": segments,
        }
