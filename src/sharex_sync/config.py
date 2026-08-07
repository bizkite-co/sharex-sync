"""Read/write ShareX JSON configs and control the ShareX process."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from . import defaults
from .ffmpeg import find_sharex_exe

APP_CONFIG = "ApplicationConfig.json"
HOTKEYS_CONFIG = "HotkeysConfig.json"

_FFMPEG_PATH_KEYS = ("DefaultTaskSettings", "CaptureSettings", "FFmpegOptions")
_CAPTURE_PATH_KEYS = ("DefaultTaskSettings", "CaptureSettings")

# Graceful-exit wait before giving up (ShareX writes configs on exit).
_STOP_TIMEOUT_S = 20.0


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as fh:
        return json.load(fh)


def save_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _navigate(doc: dict, keys: tuple[str, ...]) -> dict:
    node: dict = doc
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            raise KeyError(f"Missing config key path: {'.'.join(keys)}")
        node = node[key]
    return node


def get_ffmpeg_options(app_config: dict) -> dict:
    return _navigate(app_config, _FFMPEG_PATH_KEYS)


def get_audio_source(app_config: dict) -> str:
    return str(get_ffmpeg_options(app_config).get("AudioSource", ""))


def set_audio_source(app_config: dict, device_name: str) -> None:
    get_ffmpeg_options(app_config)["AudioSource"] = device_name


def apply_settings_overlay(app_config: dict) -> dict[str, object]:
    """Apply the tracked non-personal settings onto a loaded ApplicationConfig.

    Preserves everything else (AudioSource, folders, uploaders, ...) and
    returns a dict of changed keys (path -> old value) for reporting.
    """
    ffmpeg = get_ffmpeg_options(app_config)
    capture = _navigate(app_config, _CAPTURE_PATH_KEYS)
    changed: dict[str, object] = {}

    for key, value in defaults.FFMPEG_SETTINGS.items():
        if key == "AudioSource":
            continue
        if key not in ffmpeg or ffmpeg[key] != value:
            changed[f"FFmpegOptions.{key}"] = ffmpeg.get(key)
            ffmpeg[key] = value

    for key, value in defaults.CAPTURE_SETTINGS.items():
        if key not in capture or capture[key] != value:
            changed[f"CaptureSettings.{key}"] = capture.get(key)
            capture[key] = value

    return changed


def write_with_backup(path: Path, data: dict) -> Path | None:
    """Write JSON to ``path``, backing up any previous file with a .bak suffix."""
    backup: Path | None = None
    if path.is_file():
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_bytes(path.read_bytes())
    save_json(path, data)
    return backup


def is_sharex_running() -> bool:
    if find_sharex_exe() is None:
        return False
    try:
        proc = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq ShareX.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return "ShareX.exe" in proc.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


def stop_sharex(timeout: float = _STOP_TIMEOUT_S) -> bool:
    """Gracefully exit ShareX (it saves its configs on close) and wait.

    Returns True if ShareX is confirmed stopped.
    """
    exe = find_sharex_exe()
    if exe is None or not is_sharex_running():
        return True
    try:
        subprocess.run([str(exe), "-ExitShareX"], timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        pass

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_sharex_running():
            return True
        time.sleep(0.5)
    return not is_sharex_running()


def start_sharex() -> bool:
    """Launch ShareX silently. Returns True if the process was spawned."""
    exe = find_sharex_exe()
    if exe is None:
        return False
    try:
        subprocess.Popen([str(exe), "-silent"])
        return True
    except OSError:
        return False


def ensure_sharex_running(wait_s: float = 5.0) -> bool:
    """Start ShareX if it is not running; wait until it appears (or timeout).

    Returns True if ShareX is confirmed running. Hotkeys only work while it runs.
    """
    if is_sharex_running():
        return True
    if not start_sharex():
        return False
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if is_sharex_running():
            return True
        time.sleep(0.25)
    return is_sharex_running()
