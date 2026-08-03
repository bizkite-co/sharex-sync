"""Automatic microphone selection for ShareX's FFmpeg audio source."""

from __future__ import annotations

from pathlib import Path

from . import config, defaults, ffmpeg
from .logutil import LOGGER_NAME

import logging

log = logging.getLogger(LOGGER_NAME)


def _matches(device: str, patterns: list[str]) -> bool:
    name = device.casefold()
    return any(pattern.casefold() in name for pattern in patterns)


def select_device(devices: list[str], preferred: list[str], fallback: list[str]) -> str | None:
    """Pick the best device. None means no usable device found."""
    for pattern in preferred:
        for device in devices:
            if _matches(device, [pattern]):
                return device
    for device in devices:
        if _matches(device, fallback):
            return device
    return None


def pick_mic_device(ffmpeg_path: Path, preferred: list[str], fallback: list[str]) -> str | None:
    devices = ffmpeg.list_audio_devices(ffmpeg_path)
    if not devices:
        log.warning("No audio devices detected via dshow; is ffmpeg available?")
        return None
    return select_device(devices, preferred, fallback)


def current_audio_source(personal_path: Path) -> str:
    app_config_path = personal_path / config.APP_CONFIG
    if not app_config_path.is_file():
        return ""
    try:
        return config.get_audio_source(config.load_json(app_config_path))
    except (KeyError, ValueError) as exc:
        log.warning("Could not read AudioSource from %s: %s", app_config_path, exc)
        return ""


def reconcile(
    personal_path: Path,
    *,
    ffmpeg_path: Path | None = None,
    preferred: list[str] | None = None,
    fallback: list[str] | None = None,
    apply: bool = False,
    force: bool = False,
) -> tuple[str, str]:
    """Ensure the configured AudioSource matches a currently detected device.

    Returns (status, detail) where status is one of:
      ok          device already correct
      updated     config rewritten with a working device
      stale       saved device missing; a working device exists (apply=False)
      none        no usable device detected at all
      untouched   no working device AND saved value kept (no device found)

    Never raises on a missing/unchosen device - the config is left valid and
    ShareX will simply record without audio rather than crash.
    """
    if preferred is None:
        preferred = defaults.PREFERRED_MIC_PATTERNS
    if fallback is None:
        fallback = defaults.FALLBACK_MIC_PATTERNS

    if ffmpeg_path is None:
        sharex_dir = ffmpeg.find_sharex_exe().parent if ffmpeg.find_sharex_exe() else None
        ffmpeg_path = ffmpeg.find_ffmpeg(sharex_dir)

    if ffmpeg_path is None:
        return "none", "ffmpeg binary not found"

    app_config_path = personal_path / config.APP_CONFIG
    if not app_config_path.is_file():
        return "none", f"config not found: {app_config_path}"

    device = pick_mic_device(ffmpeg_path, preferred, fallback)
    saved = current_audio_source(personal_path)

    if device is None:
        log.warning("No usable audio device detected; leaving config untouched")
        return "none", "no usable audio device detected"

    if saved and saved.casefold() == device.casefold() and not force:
        log.info("AudioSource already set to working device: %s", device)
        return "ok", device

    if not apply:
        log.info("Would set AudioSource to: %s (was: %s)", device, saved or "<empty>")
        return "stale", f"would set '{device}' (was '{saved}')"

    try:
        app_config = config.load_json(app_config_path)
        config.set_audio_source(app_config, device)
        config.write_with_backup(app_config_path, app_config)
        log.info("AudioSource updated to: %s", device)
        return "updated", device
    except (OSError, ValueError) as exc:
        log.error("Failed to update %s: %s", app_config_path, exc)
        return "none", str(exc)
