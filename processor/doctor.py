"""Environment checks for dogsound processor."""

from __future__ import annotations

import importlib
import importlib.util
import ctypes.util
import shutil
import subprocess
import sys
from dataclasses import dataclass

from .audio import _find_windows_ffmpeg, _first_directshow_audio_device, _is_wsl


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str


def run_doctor_checks() -> list[DoctorCheck]:
    checks = [
        DoctorCheck(
            name="python",
            status="ok" if sys.version_info >= (3, 10) else "missing",
            detail=sys.version.split()[0],
        ),
        _import_check("sounddevice", "required for live microphone recording and PortAudio access"),
        _wsl_directshow_check(),
        _alsa_check(),
        _module_check("numpy", "recommended for accurate spectral features"),
        _module_check("librosa", "optional for mp3/non-wav tokenization"),
        _module_check("soundfile", "optional fallback for non-wav tokenization"),
        _executable_check("codex", "default coding agent"),
        _executable_check("claude", "optional Claude Code agent"),
    ]
    return checks


def format_doctor_checks(checks: list[DoctorCheck]) -> str:
    lines = []
    for check in checks:
        label = check.status.upper().ljust(7)
        lines.append(f"{label} {check.name}: {check.detail}")
    return "\n".join(lines)


def _module_check(name: str, purpose: str) -> DoctorCheck:
    if importlib.util.find_spec(name) is None:
        return DoctorCheck(name=name, status="missing", detail=purpose)
    return DoctorCheck(name=name, status="ok", detail=purpose)


def _import_check(name: str, purpose: str) -> DoctorCheck:
    if importlib.util.find_spec(name) is None:
        return DoctorCheck(name=name, status="missing", detail=purpose)

    try:
        importlib.import_module(name)
    except Exception as exc:
        return DoctorCheck(name=name, status="missing", detail=f"{purpose}; import failed: {exc}")

    return DoctorCheck(name=name, status="ok", detail=purpose)


def _alsa_check() -> DoctorCheck:
    library_name = ctypes.util.find_library("asound")
    if library_name is None:
        return DoctorCheck(name="alsa", status="missing", detail="fallback microphone backend")
    return DoctorCheck(name="alsa", status="ok", detail=f"fallback microphone backend ({library_name})")


def _wsl_directshow_check() -> DoctorCheck:
    if not _is_wsl():
        return DoctorCheck(name="wsl-directshow", status="missing", detail="only used inside WSL")

    ffmpeg = _find_windows_ffmpeg()
    if ffmpeg is None:
        return DoctorCheck(name="wsl-directshow", status="missing", detail="Windows ffmpeg.exe was not found")

    try:
        device = _first_directshow_audio_device(ffmpeg)
    except Exception as exc:
        return DoctorCheck(name="wsl-directshow", status="missing", detail=f"{ffmpeg}; device probe failed: {exc}")

    if not device:
        return DoctorCheck(name="wsl-directshow", status="missing", detail=f"{ffmpeg}; no DirectShow audio device")

    return DoctorCheck(name="wsl-directshow", status="ok", detail=f"{device} via {ffmpeg}")


def _executable_check(name: str, purpose: str) -> DoctorCheck:
    path = shutil.which(name)
    if path is None:
        return DoctorCheck(name=name, status="missing", detail=purpose)

    version = _read_version(name)
    detail = f"{path}"
    if version:
        detail += f" ({version})"
    return DoctorCheck(name=name, status="ok", detail=detail)


def _read_version(name: str) -> str:
    try:
        completed = subprocess.run(
            [name, "--version"],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except Exception:
        return ""

    output = (completed.stdout or completed.stderr).strip().splitlines()
    return output[0] if output else ""
