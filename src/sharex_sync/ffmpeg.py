"""Locate the ffmpeg binary ShareX uses and enumerate its DirectShow devices."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

_AUDIO_DEVICE_RE = re.compile(r'"([^"]+)" \(audio\)')


def find_ffmpeg(sharex_dir: Path | None = None) -> Path | None:
    """Return a usable ffmpeg path, preferring ShareX's bundled binary.

    Order: ShareX install dir (bundled ffmpeg.exe), then PATH.
    """
    candidates: list[Path] = []
    if sharex_dir is not None:
        candidates.append(Path(sharex_dir) / "ffmpeg.exe")

    program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    candidates.append(program_files / "ShareX" / "ffmpeg.exe")

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    on_path = shutil.which("ffmpeg")
    return Path(on_path) if on_path else None


def find_sharex_exe() -> Path | None:
    """Return the ShareX executable, or None if not installed."""
    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "ShareX" / "ShareX.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "ShareX" / "ShareX.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def list_audio_devices(ffmpeg: Path) -> list[str]:
    """Enumerate DirectShow audio devices (friendly names) via ffmpeg.

    Returns [] on non-Windows or if dshow is unavailable.
    """
    if os.name != "nt":
        return []
    try:
        proc = subprocess.run(
            [
                str(ffmpeg),
                "-hide_banner",
                "-list_devices",
                "true",
                "-f",
                "dshow",
                "-i",
                "dummy",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    output = (proc.stderr or "") + (proc.stdout or "")
    return _AUDIO_DEVICE_RE.findall(output)


def device_present(ffmpeg: Path, device_name: str) -> bool:
    return any(d.casefold() == device_name.casefold() for d in list_audio_devices(ffmpeg))
