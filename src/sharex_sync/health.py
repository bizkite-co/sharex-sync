"""Health report: is this machine ready to record with ShareX?"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import config, defaults, ffmpeg, paths


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(Check(name, ok, detail))


def run_report(personal_path: Path | None = None, ffmpeg_path: Path | None = None) -> Report:
    """Run all health checks and return a Report (never raises)."""
    report = Report()

    if personal_path is None:
        personal_path = paths.discover_personal_path()

    personal_path = Path(personal_path)
    report.add(
        "config-dir",
        personal_path.is_dir(),
        str(personal_path) + (" (missing)" if not personal_path.is_dir() else ""),
    )

    app_config_path = personal_path / config.APP_CONFIG
    if app_config_path.is_file():
        try:
            config.load_json(app_config_path)
            report.add("application-config", True, str(app_config_path))
        except ValueError as exc:
            report.add("application-config", False, f"invalid JSON: {exc}")
    else:
        report.add("application-config", False, f"missing: {app_config_path}")

    hotkeys_path = personal_path / config.HOTKEYS_CONFIG
    if hotkeys_path.is_file():
        try:
            config.load_json(hotkeys_path)
            report.add("hotkeys-config", True, str(hotkeys_path))
        except ValueError as exc:
            report.add("hotkeys-config", False, f"invalid JSON: {exc}")
    else:
        report.add("hotkeys-config", False, f"missing: {hotkeys_path}")

    sharex_exe = ffmpeg.find_sharex_exe()
    report.add("sharex-installed", sharex_exe is not None, str(sharex_exe or "not found"))

    if ffmpeg_path is None:
        sharex_dir = sharex_exe.parent if sharex_exe else None
        ffmpeg_path = ffmpeg.find_ffmpeg(sharex_dir)
    report.add(
        "ffmpeg",
        ffmpeg_path is not None and ffmpeg_path.is_file(),
        str(ffmpeg_path or "not found"),
    )

    running = config.is_sharex_running()
    report.add("sharex-running", running, "running (leave running)" if running else "not running (run `sharex-sync config --apply`)")

    saved_mic = ""
    if app_config_path.is_file():
        try:
            saved_mic = config.get_audio_source(config.load_json(app_config_path))
        except (KeyError, ValueError):
            saved_mic = ""
    if saved_mic:
        if ffmpeg_path is not None and ffmpeg_path.is_file():
            present = ffmpeg.device_present(ffmpeg_path, saved_mic)
            report.add(
                "mic",
                present,
                f"'{saved_mic}' -> {present} (run `sharex-sync mic` to fix)" if not present else f"'{saved_mic}' detected",
            )
        else:
            report.add("mic", False, f"'{saved_mic}' saved but ffmpeg missing - cannot verify")
    else:
        report.add(
            "mic",
            False,
            "no AudioSource configured (recordings will be silent) - run `sharex-sync mic`",
        )

    return report
