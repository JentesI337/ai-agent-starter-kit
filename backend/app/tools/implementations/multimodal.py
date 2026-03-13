"""Multimodal tool mixin — provides parse_pdf, transcribe_audio, generate_image, export_pdf, analyze_image."""
from __future__ import annotations

import base64
import json
import logging
import mimetypes

from app.config import settings
from app.errors import ToolExecutionError
from app.media.audio_service import AudioService
from app.media.image_gen_service import ImageGenService
from app.media.pdf_service import PdfService
from app.media.vision_service import VisionService

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

    async def analyze_image(
        self,
        image_path: str,
        prompt: str = "Describe this image in detail.",
    ) -> str:
        if not bool(settings.vision_enabled):
            raise ToolExecutionError("analyze_image is disabled (VISION_ENABLED=false).")

        normalized_path = (image_path or "").strip()
        if not normalized_path:
            raise ToolExecutionError("analyze_image requires non-empty image_path.")

        target = self._resolve_workspace_path(normalized_path)
        if not target.exists() or not target.is_file():
            raise ToolExecutionError(f"Image file not found: {target}")

        data = target.read_bytes()
        if not data:
            raise ToolExecutionError("Image file is empty.")
        if len(data) > 8_000_000:
            raise ToolExecutionError("Image file too large for analyze_image (max 8MB).")

        image_base64 = base64.b64encode(data).decode("ascii")
        guessed_mime, _ = mimetypes.guess_type(target.name)
        image_mime_type = (guessed_mime or "application/octet-stream").strip().lower()
        if not image_mime_type.startswith("image/"):
            image_mime_type = "application/octet-stream"
        service = VisionService(
            base_url=settings.vision_base_url,
            model=settings.vision_model,
            api_key=settings.vision_api_key,
            provider=settings.vision_provider,
        )

        try:
            response_text = await service.analyze_image(
                image_base64=image_base64,
                image_mime_type=image_mime_type,
                prompt=prompt,
                max_tokens=int(settings.vision_max_tokens),
            )
        except ValueError as exc:
            raise ToolExecutionError(f"analyze_image configuration error: {exc}") from exc
        except Exception as exc:
            raise ToolExecutionError(f"analyze_image failed: {exc}") from exc

        normalized_response = (response_text or "").strip()
        if not normalized_response:
            raise ToolExecutionError("analyze_image returned empty response.")
        return normalized_response
