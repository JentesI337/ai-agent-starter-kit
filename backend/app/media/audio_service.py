"""Audio transcription service."""
from __future__ import annotations

import asyncio
import io
import json
import logging
import wave
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
_MAX_DURATION_DEFAULT = 600  # 10 minutes

# Default piper voice when the configured model is not a valid piper voice name.
_DEFAULT_PIPER_VOICE = "en_US-lessac-medium"

# Directory where piper voice models are cached.
_PIPER_VOICES_DIR: Path | None = None


def _get_piper_voices_dir() -> Path:
    global _PIPER_VOICES_DIR
    if _PIPER_VOICES_DIR is None:
        _PIPER_VOICES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "assets" / "voices"
        _PIPER_VOICES_DIR.mkdir(parents=True, exist_ok=True)
    return _PIPER_VOICES_DIR


class AudioService:
    """Transcribe audio files via OpenAI API or local whisper CLI."""

    def __init__(
        self,
        provider: str = "openai",
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "whisper-1",
        max_duration_seconds: int = _MAX_DURATION_DEFAULT,
        voice: str = "alloy",
    ):
        self.provider = (provider or "local").strip().lower()
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "https://api.openai.com/v1").strip().rstrip("/")
        self.model = (model or "whisper-1").strip()
        self.max_duration_seconds = max_duration_seconds
        self.voice = (voice or "alloy").strip()

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

        segments = [
            {
                "start": float(seg.get("start", 0)),
                "end": float(seg.get("end", 0)),
                "text": str(seg.get("text", "")),
            }
            for seg in data.get("segments", [])
        ]

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

        segments = [
            {
                "start": float(seg.get("start", 0)),
                "end": float(seg.get("end", 0)),
                "text": str(seg.get("text", "")),
            }
            for seg in data.get("segments", [])
        ]

        return {
            "text": str(data.get("text", "")),
            "segments": segments,
        }

    # ── Text-to-Speech ──────────────────────────────────────────────────

    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        """Synthesize speech from text. Returns audio bytes (WAV for local, MP3 for OpenAI)."""
        clean_text = (text or "").strip()
        if not clean_text:
            raise ValueError("TTS text must not be empty")
        if len(clean_text) > 4096:
            raise ValueError(f"TTS text too long: {len(clean_text)} chars (max 4096)")

        effective_voice = (voice or self.voice).strip()

        if self.provider == "openai":
            return await self._synthesize_openai(clean_text, effective_voice)
        if self.provider == "local":
            return await self._synthesize_local(clean_text, effective_voice)
        raise ValueError(f"TTS not supported for provider: {self.provider}")

    async def _synthesize_local(self, text: str, voice: str) -> bytes:
        """Synthesize via piper Python API (preferred) or espeak CLI fallback."""
        # Try piper first
        try:
            return await self._synthesize_piper(text)
        except Exception as exc:
            logger.warning("Piper TTS failed: %s — trying espeak fallback", exc)

        # Fallback to espeak CLI
        try:
            proc = await asyncio.create_subprocess_exec(
                "espeak", "-v", voice, "--stdout",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate(input=text.encode("utf-8"))
            if proc.returncode == 0 and stdout:
                return stdout
        except FileNotFoundError:
            pass

        raise ValueError(
            "No local TTS engine found. Install 'piper-tts' or 'espeak', or use provider='openai'."
        )

    async def _synthesize_piper(self, text: str) -> bytes:
        """Synthesize using piper Python API. Auto-downloads voice model if needed."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._synthesize_piper_sync, text)

    def _synthesize_piper_sync(self, text: str) -> bytes:
        """Blocking piper synthesis — runs in executor."""
        import numpy as np
        from piper.voice import PiperVoice

        model_path = self._resolve_piper_model()
        piper_voice = PiperVoice.load(str(model_path))

        # Collect audio chunks
        audio_arrays = []
        sample_rate = 22050
        for chunk in piper_voice.synthesize(text):
            sample_rate = chunk.sample_rate
            audio_arrays.append(chunk.audio_float_array)

        if not audio_arrays:
            raise ValueError("Piper produced no audio output")

        # Concatenate and convert float32 -> int16
        audio = np.concatenate(audio_arrays)
        audio_int16 = (audio * 32767).astype(np.int16)

        # Write WAV to memory
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_int16.tobytes())
        return buf.getvalue()

    def _resolve_piper_model(self) -> Path:
        """Resolve piper voice model path, downloading if necessary."""
        import re

        voices_dir = _get_piper_voices_dir()

        # If self.model looks like a piper voice name (e.g. en_US-lessac-medium), use it.
        # Otherwise fall back to the default.
        piper_pattern = re.compile(r"^[a-z]{2}_[A-Z]{2}-\w+-\w+$")
        voice_name = self.model if piper_pattern.match(self.model) else _DEFAULT_PIPER_VOICE

        model_file = voices_dir / f"{voice_name}.onnx"
        if model_file.exists():
            return model_file

        # Auto-download the voice model
        logger.info("Downloading piper voice model: %s", voice_name)
        try:
            from piper.download_voices import download_voice
            download_voice(voice_name, voices_dir)
        except Exception as exc:
            raise ValueError(
                f"Failed to download piper voice '{voice_name}': {exc}. "
                f"Download manually with: python -m piper.download_voices {voice_name} --download-dir {voices_dir}"
            ) from exc

        if not model_file.exists():
            raise ValueError(
                f"Piper voice model not found after download: {model_file}"
            )
        return model_file

    async def _synthesize_openai(self, text: str, voice: str) -> bytes:
        """Synthesize via OpenAI TTS API."""
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/audio/speech",
                headers=headers,
                json={
                    "model": self.model,
                    "input": text,
                    "voice": voice,
                    "response_format": "mp3",
                },
            )
            response.raise_for_status()
            return response.content
