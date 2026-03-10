"""Tests for multimodal tools — parse_pdf, transcribe_audio, generate_image, export_pdf."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.errors import ToolExecutionError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tooling(**overrides):
    """Build a minimal AgentTooling-like object with the MultimodalToolMixin."""
    from app.tools_multimodal import MultimodalToolMixin

    class FakeTooling(MultimodalToolMixin):
        def _resolve_workspace_path(self, path: str) -> Path:
            p = Path(path)
            return p if p.is_absolute() else Path("/tmp/workspace") / path

    return FakeTooling()


# ---------------------------------------------------------------------------
# parse_pdf
# ---------------------------------------------------------------------------

class TestParsePdf:
    @pytest.mark.asyncio
    async def test_parse_pdf_valid(self, tmp_path):
        """Parse a small PDF and verify structured output."""
        pdf_path = tmp_path / "test.pdf"
        fake_result = {
            "text": "Hello world",
            "pages": [{"page": 1, "text": "Hello world", "tables": []}],
            "tables": [],
            "metadata": {},
            "page_count": 1,
        }
        tooling = _make_tooling()
        with patch("app.tools_multimodal.settings") as mock_settings, \
             patch("app.tools_multimodal._pdf_service") as mock_svc:
            mock_settings.multimodal_tools_enabled = True
            mock_settings.multimodal_pdf_enabled = True
            mock_settings.workspace_root = str(tmp_path)
            mock_svc.parse = AsyncMock(return_value=fake_result)

            result = await tooling.parse_pdf(path=str(pdf_path))
            parsed = json.loads(result)
            assert parsed["text"] == "Hello world"
            assert parsed["page_count"] == 1

    @pytest.mark.asyncio
    async def test_parse_pdf_not_found(self, tmp_path):
        """Missing PDF raises ToolExecutionError."""
        tooling = _make_tooling()
        with patch("app.tools_multimodal.settings") as mock_settings, \
             patch("app.tools_multimodal._pdf_service") as mock_svc:
            mock_settings.multimodal_tools_enabled = True
            mock_settings.multimodal_pdf_enabled = True
            mock_settings.workspace_root = str(tmp_path)
            mock_svc.parse = AsyncMock(side_effect=FileNotFoundError("not found"))

            with pytest.raises(ToolExecutionError, match="not found"):
                await tooling.parse_pdf(path="/nonexistent/file.pdf")

    @pytest.mark.asyncio
    async def test_parse_pdf_disabled(self):
        """Feature gate blocks parse_pdf when disabled."""
        tooling = _make_tooling()
        with patch("app.tools_multimodal.settings") as mock_settings:
            mock_settings.multimodal_tools_enabled = False
            mock_settings.multimodal_pdf_enabled = True

            with pytest.raises(ToolExecutionError, match="not enabled"):
                await tooling.parse_pdf(path="test.pdf")


# ---------------------------------------------------------------------------
# transcribe_audio
# ---------------------------------------------------------------------------

class TestTranscribeAudio:
    @pytest.mark.asyncio
    async def test_transcribe_audio_valid(self, tmp_path):
        """Mock AudioService and verify output format."""
        audio_path = tmp_path / "audio.mp3"
        fake_result = {"text": "Hello world", "segments": [{"start": 0.0, "end": 1.5, "text": "Hello world"}]}
        tooling = _make_tooling()
        with patch("app.tools_multimodal.settings") as mock_settings, \
             patch("app.tools_multimodal._get_audio_service") as mock_factory:
            mock_settings.multimodal_tools_enabled = True
            mock_settings.multimodal_audio_enabled = True
            mock_settings.workspace_root = str(tmp_path)
            mock_svc = AsyncMock()
            mock_svc.transcribe = AsyncMock(return_value=fake_result)
            mock_factory.return_value = mock_svc

            result = await tooling.transcribe_audio(path=str(audio_path))
            parsed = json.loads(result)
            assert parsed["text"] == "Hello world"
            assert len(parsed["segments"]) == 1

    @pytest.mark.asyncio
    async def test_transcribe_audio_too_large(self, tmp_path):
        """Files exceeding 20 MB are rejected."""
        tooling = _make_tooling()
        with patch("app.tools_multimodal.settings") as mock_settings, \
             patch("app.tools_multimodal._get_audio_service") as mock_factory:
            mock_settings.multimodal_tools_enabled = True
            mock_settings.multimodal_audio_enabled = True
            mock_settings.workspace_root = str(tmp_path)
            mock_svc = AsyncMock()
            mock_svc.transcribe = AsyncMock(side_effect=ValueError("Audio file too large"))
            mock_factory.return_value = mock_svc

            with pytest.raises(ToolExecutionError, match="too large"):
                await tooling.transcribe_audio(path="big_audio.wav")

    @pytest.mark.asyncio
    async def test_transcribe_audio_too_long(self, tmp_path):
        """Audio exceeding max duration is rejected."""
        tooling = _make_tooling()
        with patch("app.tools_multimodal.settings") as mock_settings, \
             patch("app.tools_multimodal._get_audio_service") as mock_factory:
            mock_settings.multimodal_tools_enabled = True
            mock_settings.multimodal_audio_enabled = True
            mock_settings.workspace_root = str(tmp_path)
            mock_svc = AsyncMock()
            mock_svc.transcribe = AsyncMock(side_effect=ValueError("Audio too long: 900s"))
            mock_factory.return_value = mock_svc

            with pytest.raises(ToolExecutionError, match="too long"):
                await tooling.transcribe_audio(path="long_audio.wav")


# ---------------------------------------------------------------------------
# generate_image
# ---------------------------------------------------------------------------

class TestGenerateImage:
    @pytest.mark.asyncio
    async def test_generate_image_valid(self):
        """Mock ImageGenService and verify base64 JSON output."""
        tooling = _make_tooling()
        with patch("app.tools_multimodal.settings") as mock_settings, \
             patch("app.tools_multimodal._get_image_gen_service") as mock_factory:
            mock_settings.multimodal_tools_enabled = True
            mock_settings.multimodal_image_gen_enabled = True
            mock_svc = AsyncMock()
            mock_svc.generate = AsyncMock(return_value="iVBORw0KGgoAAAANSUhEUg==")
            mock_factory.return_value = mock_svc

            result = await tooling.generate_image(prompt="a sunset")
            parsed = json.loads(result)
            assert parsed["type"] == "image"
            assert parsed["format"] == "png"
            assert len(parsed["data"]) > 0

    @pytest.mark.asyncio
    async def test_generate_image_disabled(self):
        """Feature gate blocks generate_image when disabled."""
        tooling = _make_tooling()
        with patch("app.tools_multimodal.settings") as mock_settings:
            mock_settings.multimodal_tools_enabled = True
            mock_settings.multimodal_image_gen_enabled = False

            with pytest.raises(ToolExecutionError, match="not enabled"):
                await tooling.generate_image(prompt="test")


# ---------------------------------------------------------------------------
# export_pdf
# ---------------------------------------------------------------------------

class TestExportPdf:
    @pytest.mark.asyncio
    async def test_export_pdf_valid(self, tmp_path):
        """Verify export_pdf creates a file."""
        output = tmp_path / "output.pdf"
        tooling = _make_tooling()
        with patch("app.tools_multimodal.settings") as mock_settings, \
             patch("app.tools_multimodal._pdf_service") as mock_svc:
            mock_settings.multimodal_tools_enabled = True
            mock_settings.multimodal_pdf_enabled = True
            mock_settings.workspace_root = str(tmp_path)

            # Simulate the export writing a file
            async def fake_export(content, path):
                path.write_text("fake pdf", encoding="utf-8")
                return path

            mock_svc.export = AsyncMock(side_effect=fake_export)

            result = await tooling.export_pdf(content="# Hello", path=str(output))
            parsed = json.loads(result)
            assert "path" in parsed
            assert parsed["size_bytes"] > 0


# ---------------------------------------------------------------------------
# Upload endpoint
# ---------------------------------------------------------------------------

class TestUploadEndpoint:
    @pytest.mark.asyncio
    async def test_upload_valid(self, tmp_path):
        """Upload a small file and verify response."""
        from fastapi.testclient import TestClient
        with patch("app.routers.uploads.settings") as mock_settings:
            mock_settings.multimodal_upload_max_bytes = 20 * 1024 * 1024
            mock_settings.workspace_root = str(tmp_path)

            from app.routers.uploads import build_uploads_router
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(build_uploads_router())
            client = TestClient(app)

            response = client.post(
                "/api/uploads",
                files={"file": ("test.pdf", b"%PDF-1.4 fake content", "application/pdf")},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["mime_type"] == "application/pdf"
            assert data["size_bytes"] > 0
            assert data["path"].startswith("_uploads/")

    @pytest.mark.asyncio
    async def test_upload_too_large(self, tmp_path):
        """Reject files exceeding max size."""
        from fastapi.testclient import TestClient
        with patch("app.routers.uploads.settings") as mock_settings:
            mock_settings.multimodal_upload_max_bytes = 100  # very small limit
            mock_settings.workspace_root = str(tmp_path)

            from app.routers.uploads import build_uploads_router
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(build_uploads_router())
            client = TestClient(app)

            response = client.post(
                "/api/uploads",
                files={"file": ("big.pdf", b"x" * 200, "application/pdf")},
            )
            assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_upload_bad_mime(self, tmp_path):
        """Reject unsupported MIME types."""
        from fastapi.testclient import TestClient
        with patch("app.routers.uploads.settings") as mock_settings:
            mock_settings.multimodal_upload_max_bytes = 20 * 1024 * 1024
            mock_settings.workspace_root = str(tmp_path)

            from app.routers.uploads import build_uploads_router
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(build_uploads_router())
            client = TestClient(app)

            response = client.post(
                "/api/uploads",
                files={"file": ("malware.exe", b"MZ\x90\x00", "application/x-executable")},
            )
            assert response.status_code == 415
