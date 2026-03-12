"""Audio dependency registry — check & install local audio packages."""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioDep:
    name: str
    label: str
    purpose: str  # "tts" | "transcription" | "audio_probe"
    check_type: str  # "python" | "cli"
    check_target: str  # module name or CLI binary name
    pip_package: str | None  # None → not pip-installable
    auto_install: bool


AUDIO_DEPS: dict[str, AudioDep] = {
    "piper-tts": AudioDep(
        name="piper-tts",
        label="Piper TTS",
        purpose="tts",
        check_type="python",
        check_target="piper",
        pip_package="piper-tts",
        auto_install=True,
    ),
    "openai-whisper": AudioDep(
        name="openai-whisper",
        label="OpenAI Whisper",
        purpose="transcription",
        check_type="python",
        check_target="whisper",
        pip_package="openai-whisper",
        auto_install=True,
    ),
    "espeak": AudioDep(
        name="espeak",
        label="eSpeak NG",
        purpose="tts",
        check_type="cli",
        check_target="espeak",
        pip_package=None,
        auto_install=False,
    ),
    "ffmpeg": AudioDep(
        name="ffmpeg",
        label="FFmpeg",
        purpose="audio_probe",
        check_type="cli",
        check_target="ffprobe",
        pip_package=None,
        auto_install=False,
    ),
}

# Only these packages may be installed via the API (security whitelist).
_INSTALLABLE_WHITELIST = frozenset(
    dep.pip_package for dep in AUDIO_DEPS.values() if dep.auto_install and dep.pip_package
)


def _is_installed(dep: AudioDep) -> bool:
    if dep.check_type == "python":
        return importlib.util.find_spec(dep.check_target) is not None
    # cli
    return shutil.which(dep.check_target) is not None


def check_audio_deps(scope: str | None = None) -> list[dict]:
    """Return status of each known audio dependency, optionally filtered by purpose."""
    results: list[dict] = []
    for dep in AUDIO_DEPS.values():
        if scope and dep.purpose != scope:
            continue
        results.append({
            "name": dep.name,
            "label": dep.label,
            "purpose": dep.purpose,
            "installed": _is_installed(dep),
            "auto_installable": dep.auto_install,
        })
    return results


async def install_audio_dep(package_name: str) -> dict:
    """Install a whitelisted pip package. Returns {name, success, message}."""
    dep = AUDIO_DEPS.get(package_name)
    if dep is None or dep.pip_package not in _INSTALLABLE_WHITELIST:
        return {"name": package_name, "success": False, "message": "Package not in whitelist"}

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", dep.pip_package],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if proc.returncode == 0:
            return {"name": package_name, "success": True, "message": "Installed successfully"}
        return {"name": package_name, "success": False, "message": proc.stderr.strip()[:500]}
    except subprocess.TimeoutExpired:
        return {"name": package_name, "success": False, "message": "Installation timed out"}
    except Exception as exc:  # noqa: BLE001
        return {"name": package_name, "success": False, "message": str(exc)[:500]}
