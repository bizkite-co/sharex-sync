"""Unit tests for the recording control (recctl.py)."""

from __future__ import annotations

import pytest

from sharex_sync.recctl import (
    _PANEL_BUTTONS,
    _key_name_to_vk,
    _format_elapsed,
    combo_for_job,
    combo_to_vk,
    ffmpeg_is_running,
    press_hotkey,
)


class TestComboForJob:
    def test_stop(self):
        assert combo_for_job("StopScreenRecording") == ("X", "Control", "Win")

    def test_pause(self):
        # Control+Option+B on Keychron (Ctrl+Win+B); P alone is OS-reserved as Ctrl+Win+P
        assert combo_for_job("PauseScreenRecording") == ("B", "Control", "Win")

    def test_unknown_job(self):
        assert combo_for_job("NoSuchJob") is None

    def test_record(self):
        # Control+Option+R on Keychron (Ctrl+Win+R)
        assert combo_for_job("ScreenRecorderActiveWindow") == ("R", "Control", "Win")

    def test_abort(self):
        assert combo_for_job("AbortScreenRecording") == ("A", "Control", "Win")


class TestPanelButtons:
    def test_every_button_job_has_a_registered_combo(self):
        for _label, job, _while_recording in _PANEL_BUTTONS:
            assert combo_for_job(job) is not None, f"no tracked hotkey for {job!r}"

    def test_record_disabled_while_recording_others_enabled(self):
        # Record should be clickable only when idle; Pause/Stop/Abort only while recording.
        by_job = {job: while_recording for _label, job, while_recording in _PANEL_BUTTONS}
        assert by_job["ScreenRecorderActiveWindow"] is False
        assert by_job["PauseScreenRecording"] is True
        assert by_job["StopScreenRecording"] is True
        assert by_job["AbortScreenRecording"] is True


class TestKeyNameToVk:
    def test_ascii(self):
        assert _key_name_to_vk("x") == 0x58
        assert _key_name_to_vk("A") == 0x41

    def test_digit(self):
        assert _key_name_to_vk("5") == 0x35

    def test_modifiers(self):
        assert _key_name_to_vk("CONTROL") == 0x11
        assert _key_name_to_vk("Alt") == 0x12
        assert _key_name_to_vk("SHIFT") == 0x10
        assert _key_name_to_vk("PrintScreen") == 0x2C

    def test_function_keys(self):
        assert _key_name_to_vk("F1") == 0x70
        assert _key_name_to_vk("F11") == 0x7A
        assert _key_name_to_vk("F24") == 0x87

    def test_invalid(self):
        assert _key_name_to_vk("F0") is None
        assert _key_name_to_vk("F25") is None
        assert _key_name_to_vk("!!") is None


class TestComboToVk:
    def test_stop_combo(self):
        assert combo_to_vk(("X", "Control", "Alt")) == [0x58, 0x11, 0x12]

    def test_unmappable(self):
        with pytest.raises(ValueError):
            combo_to_vk(("X", "Control", "??"))


class TestFfmpegIsRunning:
    def test_running(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            class Proc:
                stdout = "ffmpeg.exe 1234 Console 1 12,345 K\n"
            return Proc()

        monkeypatch.setattr("sharex_sync.recctl.subprocess.run", fake_run)
        assert ffmpeg_is_running() is True

    def test_not_running(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            class Proc:
                stdout = "INFO: No tasks are running which match the specified criteria.\n"
            return Proc()

        monkeypatch.setattr("sharex_sync.recctl.subprocess.run", fake_run)
        assert ffmpeg_is_running() is False

    def test_error(self, monkeypatch):
        def boom(*args, **kwargs):
            raise OSError("no tasklist")

        monkeypatch.setattr("sharex_sync.recctl.subprocess.run", boom)
        assert ffmpeg_is_running() is False


class TestPressHotkey:
    def test_modifiers_pressed_before_main_key_and_released_first(self, monkeypatch):
        # combo_for_job returns the main key first (e.g. ("X", "Control", "Win"));
        # Windows only fires WM_HOTKEY when the main key goes down while
        # modifiers are already held, so press_hotkey must reorder them.
        calls = []
        monkeypatch.setattr("sharex_sync.recctl.os.name", "nt")
        monkeypatch.setattr(
            "sharex_sync.recctl._send_key",
            lambda vk, up: calls.append((vk, up)),
        )

        press_hotkey(("X", "Control", "Win"))

        vk_x, vk_control, vk_win = 0x58, 0x11, 0x5B
        downs = [vk for vk, up in calls if not up]
        ups = [vk for vk, up in calls if up]
        assert downs == [vk_control, vk_win, vk_x]
        assert ups == [vk_x, vk_win, vk_control]


class TestFormatElapsed:
    def test_seconds(self):
        assert _format_elapsed(0) == "00:00:00"
        assert _format_elapsed(65) == "00:01:05"
        assert _format_elapsed(3661) == "01:01:01"
