"""Unit tests for the hotkey display helpers in defaults.py."""

from __future__ import annotations

from sharex_sync import defaults


class TestHotkeyDisplays:
    def test_covers_every_tracked_hotkey(self):
        displays = defaults.hotkey_displays()
        assert len(displays) == len(defaults.HOTKEYS)

    def test_stop_screen_recording(self):
        displays = {d["job"]: d for d in defaults.hotkey_displays()}
        stop = displays["StopScreenRecording"]
        assert stop["keycap"] == "Control+Option+X"
        assert stop["windows_chord"] == "Ctrl+Win+X"

    def test_non_win_combo_has_no_option(self):
        displays = {d["job"]: d for d in defaults.hotkey_displays()}
        region = displays["RectangleRegion"]
        assert region["keycap"] == "Control+PrintScreen"
        assert region["windows_chord"] == "Ctrl+PrintScreen"

    def test_shift_control_combo(self):
        displays = {d["job"]: d for d in defaults.hotkey_displays()}
        gif = displays["ScreenRecorderGIF"]
        assert gif["keycap"] == "Control+Shift+PrintScreen"
        assert gif["windows_chord"] == "Ctrl+Shift+PrintScreen"


class TestKeycapForJob:
    def test_known_job(self):
        assert defaults.keycap_for_job("AbortScreenRecording") == "Control+Option+A"

    def test_unknown_job(self):
        assert defaults.keycap_for_job("NoSuchJob") is None
