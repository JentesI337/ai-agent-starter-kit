"""File upload endpoint for multimodal inputs."""
from __future__ import annotations

import logging
import mimetypes
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import settings

logger = logging.getLogger(__name__)

_ALLOWED_MIME_PREFIXES = ("application/pdf", "audio/", "image/")


def _sanitize_filename(name: str) -> str:
    """Remove unsafe characters from filename."""
    safe = re.sub(r'[^\w\-.]', '_', name)
    return safe[:200] if safe else "upload"


def build_uploads_router() -> APIRouter:
    router = APIRouter(prefix="/api", tags=["uploads"])

    @router.post("/uploads")
    async def upload_file(file: UploadFile = File(...)):
        max_bytes = settings.multimodal_upload_max_bytes

        # Validate MIME type
        content_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
        if not any(content_type.startswith(prefix) for prefix in _ALLOWED_MIME_PREFIXES):
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type: {content_type}. Accepted: PDF, audio, image.",
            )

        # Read and validate size
        data = await file.read()
        if len(data) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large: {len(data)} bytes (max {max_bytes}).",
            )

        # Save to workspace
        safe_name = _sanitize_filename(file.filename or "upload")
        upload_name = f"{uuid.uuid4().hex[:12]}_{safe_name}"
        upload_dir = Path(settings.workspace_root) / "_uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / upload_name
        dest.write_bytes(data)

        logger.info("upload_saved path=%s size=%d mime=%s", dest, len(data), content_type)
        return {
            "path": f"_uploads/{upload_name}",
            "mime_type": content_type,
            "size_bytes": len(data),
        }

    return router
