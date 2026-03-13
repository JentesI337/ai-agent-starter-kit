"""Handlers for config.deps.* control endpoints."""
from __future__ import annotations

from typing import Any

from app.media.audio_deps import check_audio_deps, install_audio_dep


async def handle_deps_check(request: dict[str, Any]) -> dict[str, Any]:
    scope = request.get("scope")  # optional: "tts" | "transcription"
    deps = check_audio_deps(scope)
    return {"dependencies": deps}


async def handle_deps_install(request: dict[str, Any]) -> dict[str, Any]:
    package = str(request.get("package") or "").strip()
    if not package:
        return {"name": "", "success": False, "message": "package is required"}
    return await install_audio_dep(package)
