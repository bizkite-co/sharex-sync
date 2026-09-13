"""Tracked ShareX settings.

Edit this file to change what ``sharex-sync config`` and ``sharex-sync hotkeys``
apply on a machine. Only non-personal settings live here; the microphone is
resolved per-machine by ``sharex-sync mic``.
"""

from __future__ import annotations

# Machine-independent FFmpeg capture options, applied to
# DefaultTaskSettings.CaptureSettings.FFmpegOptions.
# "AudioSource" is intentionally absent - managed by `sharex-sync mic`.
FFMPEG_SETTINGS = {
    "OverrideCLIPath": False,
    "CLIPath": "",
    "VideoSource": "gdigrab",
    "VideoCodec": "libx264",
    "AudioCodec": "libvoaacenc",
    "UserArgs": "",
    "UseCustomCommands": False,
    "CustomCommands": "",
    "x264_Preset": "ultrafast",
    "x264_CRF": 28,
    "x264_Use_Bitrate": False,
    "x264_Bitrate": 3000,
    "VPx_Bitrate": 3000,
    "XviD_QScale": 10,
    "NVENC_Preset": "p4",
    "NVENC_Tune": "ll",
    "NVENC_Bitrate": 3000,
    "GIFStatsMode": "full",
    "GIFDither": "sierra2_4a",
    "GIFBayerScale": 2,
    "AMF_Usage": "lowlatency",
    "AMF_Quality": "speed",
    "AMF_Bitrate": 3000,
    "QSV_Preset": "fast",
    "QSV_Bitrate": 3000,
    "AAC_Bitrate": 128,
    "Opus_Bitrate": 128,
    "Vorbis_QScale": 3,
    "MP3_QScale": 4,
}

# Non-personal capture settings adjacent to FFmpegOptions, applied to
# DefaultTaskSettings.CaptureSettings.
CAPTURE_SETTINGS = {
    "ScreenRecordFPS": 30,
    "ScreenRecordShowCursor": True,
    "ScreenRecordAutoStart": True,
    "ScreenRecordFixedDuration": False,
    "ScreenRecordTwoPassEncoding": False,
}

# Mic selection order. The first detected device whose friendly name contains
# one of these patterns (case-insensitive) is chosen. Override at runtime with
# `--mic-pattern`.
PREFERRED_MIC_PATTERNS = ["pd100u"]

# Fallback patterns tried if no preferred pattern matches a device.
FALLBACK_MIC_PATTERNS = ["microphone", "mic"]

# Hotkey combos and the ShareX job they trigger.
# Each entry: (hotkey_string, job, description, win_modifier=False)
# ShareX stores the Windows key as HotkeyInfo.Win, not in the Hotkey string.
# Keychron on THIS machine (Windows mode — legends ≠ Mac defaults):
#   Left Option → Win (opens Start alone)
#   Command     → Alt
#   Right Option → RAlt
#   Control     → Ctrl
#
# Whole recording suite uses the SAME physical modifiers: Control+Option+key
# = Ctrl+Win+key (Hotkey string + Win:true). Not a mix of Option and Command.
HOTKEYS = [
    ("PrintScreen, Control", "RectangleRegion", "Capture region", False),
    ("W, Control", "ActiveWindow", "Capture active window", True),  # Control+Option+W
    ("PrintScreen, Shift", "ScreenRecorder", "Start/Stop screen recording", False),
    ("PrintScreen, Shift, Control", "ScreenRecorderGIF", "Start/Stop screen recording (GIF)", False),
    ("R, Control", "ScreenRecorderActiveWindow", "Record active window", True),  # Control+Option+R
    # Ctrl+Win+P is reserved by Windows (fails ShareX registration). Use B = break/pause.
    ("B, Control", "PauseScreenRecording", "Pause/Resume screen recording", True),  # Control+Option+B
    ("X, Control", "StopScreenRecording", "Stop screen recording", True),        # Control+Option+X
    ("A, Control", "AbortScreenRecording", "Abort screen recording", True),      # Control+Option+A
]


def _hotkey_parts(entry: tuple) -> tuple[str, str, str, bool]:
    """Normalize HOTKEYS entry to (combo, job, description, win)."""
    if len(entry) == 4:
        combo, job, description, win = entry
        return combo, job, description, bool(win)
    combo, job, description = entry
    return combo, job, description, False


def _task_settings(job: str, description: str) -> dict:
    return {
        "Description": description,
        "Job": job,
        "UseDefaultAfterCaptureJob": True,
        "AfterCaptureJob": "CopyImageToClipboard, SaveImageToFile",
        "UseDefaultAfterUploadJob": True,
        "AfterUploadJob": "CopyURLToClipboard",
        "UseDefaultDestinations": True,
        "ImageDestination": "Imgur",
        "ImageFileDestination": "Dropbox",
        "TextDestination": "Pastebin",
        "TextFileDestination": "Dropbox",
        "FileDestination": "Dropbox",
        "URLShortenerDestination": "BITLY",
        "URLSharingServiceDestination": "Email",
        "OverrideFTP": False,
        "FTPIndex": 0,
        "OverrideCustomUploader": False,
        "CustomUploaderIndex": 0,
        "OverrideScreenshotsFolder": False,
        "ScreenshotsFolder": "",
        "UseDefaultGeneralSettings": True,
        "GeneralSettings": None,
        "UseDefaultImageSettings": True,
        "ImageSettings": None,
        "UseDefaultCaptureSettings": True,
        "CaptureSettings": None,
        "UseDefaultUploadSettings": True,
        "UploadSettings": None,
        "UseDefaultActions": True,
        "ExternalPrograms": None,
        "UseDefaultToolsSettings": True,
        "ToolsSettings": None,
        "UseDefaultAdvancedSettings": True,
        "AdvancedSettings": None,
        "WatchFolderEnabled": False,
        "WatchFolderList": [],
    }


def _modifier_labels(modifiers: list[str], win: bool) -> tuple[list[str], list[str]]:
    """Split a combo's modifiers into (keycap labels, Windows-chord labels).

    Keycap labels use THIS machine's Keychron Windows-mode legends (see the
    HOTKEYS comment above): Left Option -> Win, Command -> Alt, Control -> Ctrl.
    """
    keycap, windows = [], []
    if "Control" in modifiers:
        keycap.append("Control")
        windows.append("Ctrl")
    if "Shift" in modifiers:
        keycap.append("Shift")
        windows.append("Shift")
    if "Alt" in modifiers:
        keycap.append("Command")
        windows.append("Alt")
    if win:
        keycap.append("Option")
        windows.append("Win")
    return keycap, windows


def hotkey_displays() -> list[dict]:
    """Human-readable keycap + Windows-chord label for every tracked hotkey.

    Each item: {"job", "description", "keycap", "windows_chord"}.
    """
    displays = []
    for entry in HOTKEYS:
        combo, job, description, win = _hotkey_parts(entry)
        parts = [p.strip() for p in combo.split(",")]
        main_key, modifiers = parts[0], parts[1:]
        keycap_mods, windows_mods = _modifier_labels(modifiers, win)
        displays.append(
            {
                "job": job,
                "description": description,
                "keycap": "+".join(keycap_mods + [main_key]),
                "windows_chord": "+".join(windows_mods + [main_key]),
            }
        )
    return displays


def keycap_for_job(job: str) -> str | None:
    """Keycap chord (Keychron legends) for a tracked ShareX job, if any."""
    for display in hotkey_displays():
        if display["job"] == job:
            return display["keycap"]
    return None


def hotkeys_config() -> dict:
    """Build the full HotkeysConfig.json document."""
    entries = []
    for entry in HOTKEYS:
        combo, job, description, win = _hotkey_parts(entry)
        entries.append(
            {
                "HotkeyInfo": {"Hotkey": combo, "Win": win},
                "TaskSettings": _task_settings(job, description),
            }
        )
    return {
        "Hotkeys": entries,
        "ApplicationVersion": "21.0.0",
    }
