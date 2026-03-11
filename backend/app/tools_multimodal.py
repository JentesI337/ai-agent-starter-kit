"""Multimodal tool mixin — provides parse_pdf, transcribe_audio, generate_image, export_pdf."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import settings
from app.errors import ToolExecutionError
from app.services.pdf_service import PdfService
from app.services.audio_service import AudioService
from app.services.image_gen_service import ImageGenService

logger = logging.getLogger(__name__)

_pdf_service = PdfService()


def _get_audio_service() -> AudioService:
    return AudioService(
        provider=settings.multimodal_audio_provider,
        api_key=settings.multimodal_audio_api_key,
        base_url=settings.multimodal_audio_base_url,
        model=settings.multimodal_audio_model,
        max_duration_seconds=settings.multimodal_audio_max_duration_seconds,
    )


def _get_tts_service() -> AudioService:
    return AudioService(
        provider=settings.multimodal_tts_provider,
        api_key=settings.multimodal_tts_api_key,
        base_url=settings.multimodal_tts_base_url,
        model=settings.multimodal_tts_model,
        voice=settings.multimodal_tts_voice,
    )


def _get_image_gen_service() -> ImageGenService:
    return ImageGenService(
        provider=settings.multimodal_image_gen_provider,
        api_key=settings.multimodal_image_gen_api_key,
        base_url=settings.multimodal_image_gen_base_url,
        model=settings.multimodal_image_gen_model,
        default_size=settings.multimodal_image_gen_default_size,
    )


class MultimodalToolMixin:
    """Mixin providing multimodal tools for AgentTooling."""

    async def parse_pdf(self, *, path: str, **_kwargs) -> str:
        """Parse a PDF file and return extracted text, tables, and metadata."""
        if not settings.multimodal_tools_enabled or not settings.multimodal_pdf_enabled:
            raise ToolExecutionError("PDF parsing is not enabled. Set MULTIMODAL_TOOLS_ENABLED=true and MULTIMODAL_PDF_ENABLED=true.")

        resolved = self._resolve_workspace_path(path)
        try:
            result = await _pdf_service.parse(resolved)
            return json.dumps(result, indent=2, default=str)
        except FileNotFoundError as exc:
            raise ToolExecutionError(str(exc)) from exc
        except Exception as exc:
            raise ToolExecutionError(f"PDF parse failed: {exc}") from exc

    async def transcribe_audio(self, *, path: str, **_kwargs) -> str:
        """Transcribe an audio file to text with timestamps."""
        if not settings.multimodal_tools_enabled or not settings.multimodal_audio_enabled:
            raise ToolExecutionError("Audio transcription is not enabled. Set MULTIMODAL_TOOLS_ENABLED=true and MULTIMODAL_AUDIO_ENABLED=true.")

        resolved = self._resolve_workspace_path(path)
        try:
            svc = _get_audio_service()
            result = await svc.transcribe(resolved)
            return json.dumps(result, indent=2, default=str)
        except (FileNotFoundError, ValueError) as exc:
            raise ToolExecutionError(str(exc)) from exc
        except Exception as exc:
            raise ToolExecutionError(f"Audio transcription failed: {exc}") from exc

    async def generate_image(self, *, prompt: str, size: str | None = None, **_kwargs) -> str:
        """Generate an image from a text prompt. Returns JSON with base64 image data."""
        if not settings.multimodal_tools_enabled or not settings.multimodal_image_gen_enabled:
            raise ToolExecutionError("Image generation is not enabled. Set MULTIMODAL_TOOLS_ENABLED=true and MULTIMODAL_IMAGE_GEN_ENABLED=true.")

        try:
            svc = _get_image_gen_service()
            b64_data = await svc.generate(prompt, size)
            return json.dumps({"type": "image", "format": "png", "data": b64_data})
        except ValueError as exc:
            raise ToolExecutionError(str(exc)) from exc
        except Exception as exc:
            raise ToolExecutionError(f"Image generation failed: {exc}") from exc

    async def generate_audio(self, *, text: str, voice: str | None = None, **_kwargs) -> str:
        """Generate spoken audio from text using text-to-speech."""
        if not settings.multimodal_tools_enabled or not settings.multimodal_tts_enabled:
            raise ToolExecutionError(
                "Text-to-speech is not enabled. Set MULTIMODAL_TOOLS_ENABLED=true and MULTIMODAL_TTS_ENABLED=true."
            )

        try:
            import base64
            svc = _get_tts_service()
            audio_bytes = await svc.synthesize(text, voice)
            b64_data = base64.b64encode(audio_bytes).decode("ascii")
            fmt = "mp3" if svc.provider == "openai" else "wav"
            return json.dumps({"type": "audio", "format": fmt, "data": b64_data})
        except ValueError as exc:
            raise ToolExecutionError(str(exc)) from exc
        except Exception as exc:
            raise ToolExecutionError(f"Audio generation failed: {exc}") from exc

    async def export_pdf(self, *, content: str, path: str | None = None, **_kwargs) -> str:
        """Export markdown content to a PDF file."""
        if not settings.multimodal_tools_enabled or not settings.multimodal_pdf_enabled:
            raise ToolExecutionError("PDF export is not enabled. Set MULTIMODAL_TOOLS_ENABLED=true and MULTIMODAL_PDF_ENABLED=true.")

        if not path:
            path = "export.pdf"
        resolved = self._resolve_workspace_path(path)
        try:
            result_path = await _pdf_service.export(content, resolved)
            return json.dumps({"path": str(result_path), "size_bytes": result_path.stat().st_size})
        except Exception as exc:
            raise ToolExecutionError(f"PDF export failed: {exc}") from exc

    def _resolve_workspace_path(self, path: str) -> Path:
        """Resolve a path relative to the workspace root."""
        p = Path(path)
        if p.is_absolute():
            return p
        return Path(settings.workspace_root) / path
