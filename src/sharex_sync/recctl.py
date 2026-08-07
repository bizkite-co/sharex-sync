"""Always-on-top recording control for ShareX.

ShareX's built-in recording toolbar (Stop/Pause/Abort buttons) can fail to
render on some setups (Avalonia rewrite, multi-monitor, DPI quirks). This module
provides a minimal replacement: a small always-on-top strip that appears while a
recording is active, shows which microphone is in use and the elapsed time, and
offers Pause and Stop buttons that trigger the tracked ShareX hotkeys.

Windows-only (relies on ``tasklist`` and ``SendInput``).
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import time
from pathlib import Path

from . import config, defaults, paths

try:
    import tkinter as tk
except ImportError:  # pragma: no cover
    tk = None

_WORKER_IMAGE = "ffmpeg.exe"
_POLL_MS = 500

# Virtual-key codes for the combos we synthesize. Anything else (single ASCII
# chars, F1-F24, PRINTSCREEN) is derived at runtime.
_VK = {
    "CONTROL": 0x11,
    "ALT": 0x12,
    "SHIFT": 0x10,
    "PRINTSCREEN": 0x2C,
    "WIN": 0x5B,  # LWin — Keychron Command
}

# SendInput constants.
_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002

PUL = ctypes.POINTER(ctypes.c_ulong)


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_ushort),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", _INPUT_UNION)]


def combo_for_job(job: str) -> tuple[str, ...] | None:
    """Return the tracked hotkey combo (as key names) for a ShareX job."""
    for entry in defaults.HOTKEYS:
        combo, job_name, _desc, win = defaults._hotkey_parts(entry)
        if job_name == job:
            parts = [part.strip() for part in combo.split(",")]
            if win:
                parts.append("Win")
            return tuple(parts)
    return None


def _key_name_to_vk(name: str) -> int | None:
    key = name.strip().upper()
    if key in _VK:
        return _VK[key]
    if len(key) == 1 and key.isascii() and key.isprintable():
        return ord(key.upper())
    if len(key) > 1 and key[0] == "F":
        try:
            number = int(key[1:])
        except ValueError:
            return None
        if 1 <= number <= 24:
            return 0x6F + number  # VK_F1..VK_F24
    return None


def combo_to_vk(combo: tuple[str, ...]) -> list[int]:
    """Map a combo (e.g. ``("X", "Control", "Alt")``) to virtual-key codes."""
    codes = []
    for part in combo:
        code = _key_name_to_vk(part)
        if code is None:
            raise ValueError(f"cannot map hotkey key to a virtual key code: {part!r}")
        codes.append(code)
    return codes


def _send_key(vk: int, up: bool) -> None:
    extra = ctypes.c_ulong(0)
    event = _INPUT()
    event.type = _INPUT_KEYBOARD
    event.union.ki.wVk = vk
    event.union.ki.wScan = 0
    event.union.ki.dwFlags = _KEYEVENTF_KEYUP if up else 0
    event.union.ki.time = 0
    event.union.ki.dwExtraInfo = ctypes.pointer(extra)
    ctypes.windll.user32.SendInput(
        1, ctypes.byref(event), ctypes.sizeof(_INPUT)
    )


def press_hotkey(combo: tuple[str, ...]) -> bool:
    """Synthesize a hotkey press via SendInput. Returns False on non-Windows."""
    if os.name != "nt":
        return False
    codes = combo_to_vk(combo)
    for vk in codes:
        _send_key(vk, up=False)
    for vk in reversed(codes):
        _send_key(vk, up=True)
    return True


def ffmpeg_is_running(image: str = _WORKER_IMAGE) -> bool:
    """True if a process named ``image`` (ShareX's recording worker) is running."""
    if not image.casefold().endswith(".exe"):
        image += ".exe"
    try:
        proc = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return image.casefold() in proc.stdout.casefold()
    except (OSError, subprocess.TimeoutExpired):
        return False


def current_mic(personal_path: Path) -> str:
    app_config_path = personal_path / config.APP_CONFIG
    if not app_config_path.is_file():
        return ""
    try:
        return config.get_audio_source(config.load_json(app_config_path))
    except (KeyError, ValueError):
        return ""


def _format_elapsed(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def run_control(personal_path: Path | None = None) -> int:
    """Launch the always-on-top recording control. Returns a process exit code."""
    if tk is None:
        return 1

    if personal_path is None:
        personal_path = paths.discover_personal_path()

    stop_combo = combo_for_job("StopScreenRecording")
    pause_combo = combo_for_job("PauseScreenRecording")
    if stop_combo is None or pause_combo is None:
        return 2

    root = tk.Tk()
    root.title("ShareX recording control")
    root.attributes("-topmost", True)
    root.resizable(False, False)
    root.overrideredirect(True)
    root.attributes("-alpha", 0.92)

    frame = tk.Frame(root, bd=1, relief="solid", padx=8, pady=4)
    frame.pack(fill="both", expand=True)

    status = tk.Label(frame, text="\u25cf IDLE", fg="#666", font=("Segoe UI", 11, "bold"))
    status.pack(side="left", padx=(0, 8))

    mic = tk.Label(frame, text="Mic: -", font=("Segoe UI", 10))
    mic.pack(side="left", padx=(0, 8))

    pause_btn = tk.Button(frame, text="\u23f8 Pause", width=8, state="disabled")
    stop_btn = tk.Button(frame, text="\u23f9 Stop", width=8, bg="#c0392b", fg="white",
                         activebackground="#a93226", activeforeground="white")
    pause_btn.pack(side="left", padx=2)
    stop_btn.pack(side="left", padx=2)

    close_btn = tk.Button(frame, text="\u2715", width=2, relief="flat", command=root.destroy)
    close_btn.pack(side="left", padx=(6, 0))

    def _place() -> None:
        root.update_idletasks()
        x = root.winfo_screenwidth() - root.winfo_reqwidth() - 16
        root.geometry(f"+{x}+12")

    state = {"recording": False, "since": 0.0, "mic": ""}

    def _stop() -> None:
        press_hotkey(stop_combo)
        _poll()

    def _pause() -> None:
        press_hotkey(pause_combo)
        _poll()

    pause_btn.configure(command=_pause)
    stop_btn.configure(command=_stop)

    def _poll() -> None:
        recording = ffmpeg_is_running()

        now = time.monotonic()
        if recording != state["recording"]:
            state["recording"] = recording
            state["since"] = now if recording else 0.0

        mic_text = current_mic(personal_path)
        if mic_text and mic_text != state["mic"]:
            state["mic"] = mic_text
            mic.configure(text=f"Mic: {mic_text}")

        if recording:
            status.configure(text=f"\u25cf REC {_format_elapsed(now - state['since'])}", fg="#c0392b")
            pause_btn.configure(state="normal")
            root.deiconify()
        else:
            status.configure(text="\u25cf IDLE", fg="#666")
            pause_btn.configure(state="disabled")
            root.withdraw()

        root.after(_POLL_MS, _poll)

    _place()
    root.withdraw()
    root.after(_POLL_MS, _poll)
    root.mainloop()
    return 0
