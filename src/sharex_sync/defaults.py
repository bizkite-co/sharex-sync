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
HOTKEYS = [
    ("PrintScreen, Control", "RectangleRegion", "Capture region"),
    ("W, Control, Alt", "ActiveWindow", "Capture active window"),
    ("PrintScreen, Shift", "ScreenRecorder", "Start/Stop screen recording"),
    ("PrintScreen, Shift, Control", "ScreenRecorderGIF", "Start/Stop screen recording (GIF)"),
    ("R, Control, Alt", "ScreenRecorderActiveWindow", "Record active window"),
    ("P, Control, Alt", "PauseScreenRecording", "Pause/Resume screen recording"),
]


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


def hotkeys_config() -> dict:
    """Build the full HotkeysConfig.json document."""
    return {
        "Hotkeys": [
            {
                "HotkeyInfo": {"Hotkey": combo, "Win": False},
                "TaskSettings": _task_settings(job, description),
            }
            for combo, job, description in HOTKEYS
        ],
        "ApplicationVersion": "21.0.0",
    }
