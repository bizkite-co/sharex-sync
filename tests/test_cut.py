"""Unit tests for the editing pipeline (cut.py)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from sharex_sync.cut import (
    Segment,
    VideoInfo,
    find_app,
    generate_llc,
    generate_mlt,
    keep_segments,
    parse_probe_output,
    parse_silence_output,
    to_timecode,
)

SAMPLE_PROBE = """\
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'C:\\Users\\me\\rec.mp4':
  Metadata:
    major_brand     : isom
  Duration: 00:12:34.56, start: 0.000000, bitrate: 1051 kb/s
  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(progressive), 1920x1080 [SAR 1:1 DAR 16:9], 30 fps, 30 tbr, 90k tbn (default)
  Stream #0:1[0x1](und): Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, stereo, fltp, 128 kb/s (default)
At least one output file must be specified
"""


class TestParseSilenceOutput:
    def test_pairs(self):
        text = (
            "[silencedetect @ 0x1] silence_start: 10.5\n"
            "[silencedetect @ 0x1] silence_end: 15.2 | silence_duration: 4.7\n"
            "[silencedetect @ 0x1] silence_start: 30\n"
            "[silencedetect @ 0x1] silence_end: 32.5 | silence_duration: 2.5\n"
        )
        silences = parse_silence_output(text)
        assert silences == [Segment(10.5, 15.2), Segment(30.0, 32.5)]

    def test_trailing_silence_has_no_end(self):
        text = "[silencedetect @ 0x1] silence_start: 90.0\n"
        assert parse_silence_output(text) == [Segment(90.0, None)]

    def test_empty(self):
        assert parse_silence_output("nothing here") == []


class TestParseProbeOutput:
    def test_full_probe(self):
        info = parse_probe_output(SAMPLE_PROBE)
        assert info.width == 1920
        assert info.height == 1080
        assert info.duration == pytest.approx(754.56)
        assert (info.fps_num, info.fps_den) == (30, 1)
        assert (info.dar_num, info.dar_den) == (16, 9)

    def test_ntsc_fps_rational(self):
        line = (
            "  Stream #0:0(und): Video: h264 (High) (avc1 / 0x31637661), yuv420p, "
            "1280x720 [SAR 1:1 DAR 16:9], 30000/1001 fps, 30000/1001 tbr, 90k tbn (default)\n"
        )
        text = "Duration: 00:00:10.00, start: 0.000000\n" + line
        info = parse_probe_output(text)
        assert (info.fps_num, info.fps_den) == (30000, 1001)

    def test_ntsc_fps_float(self):
        line = (
            "  Stream #0:0(und): Video: h264 (High) (avc1 / 0x31637661), yuv420p, "
            "1280x720 [SAR 1:1 DAR 16:9], 29.97 fps, 30000/1001 tbr, 90k tbn (default)\n"
        )
        text = "Duration: 00:00:10.00, start: 0.000000\n" + line
        info = parse_probe_output(text)
        assert (info.fps_num, info.fps_den) == (30000, 1001)

    def test_no_dar_derives_from_resolution(self):
        line = (
            "  Stream #0:0(und): Video: h264, yuv420p, 320x240, 30 fps, 30 tbr\n"
        )
        text = "Duration: 00:00:10.00, start: 0.000000\n" + line
        info = parse_probe_output(text)
        assert (info.dar_num, info.dar_den) == (4, 3)

    def test_missing_duration_raises(self):
        with pytest.raises(Exception):
            parse_probe_output("no duration here")


class TestKeepSegments:
    def test_no_silences_keeps_everything(self):
        assert keep_segments(100.0, []) == [Segment(0.0, 100.0)]

    def test_middle_silence_with_margin(self):
        silences = [Segment(10.0, 20.0)]
        assert keep_segments(100.0, silences, margin=0.5) == [
            Segment(0.0, 9.5),
            Segment(20.5, 100.0),
        ]

    def test_leading_silence_dropped(self):
        assert keep_segments(100.0, [Segment(0.0, 5.0)], margin=0.0) == [
            Segment(5.0, 100.0)
        ]

    def test_trailing_silence_dropped(self):
        assert keep_segments(100.0, [Segment(90.0, None)], margin=0.0) == [
            Segment(0.0, 90.0)
        ]

    def test_margin_clamped_at_boundaries(self):
        silences = [Segment(1.0, 2.0)]
        assert keep_segments(100.0, silences, margin=5.0) == [
            Segment(7.0, 100.0),
        ]

    def test_tiny_segment_dropped(self):
        silences = [Segment(0.02, 0.05), Segment(99.0, None)]
        assert keep_segments(100.0, silences, margin=0.0) == [Segment(0.05, 99.0)]

    def test_full_silence_returns_nothing(self):
        assert keep_segments(100.0, [Segment(0.0, None)], margin=0.0) == []


class TestToTimecode:
    def test_zero(self):
        assert to_timecode(0.0, 30, 1) == "00:00:00.000"

    def test_seconds(self):
        assert to_timecode(1.8, 30, 1) == "00:00:01.800"

    def test_long_duration(self):
        assert to_timecode(754.56, 30, 1) == "00:12:34.567"

    def test_ntsc_frame_align(self):
        assert to_timecode(1.0, 30000, 1001) == "00:00:01.001"


class TestGenerateLlc:
    def test_document_shape(self):
        segments = [Segment(0.0, 10.0), Segment(20.0, 30.0)]
        doc = json.loads(generate_llc("C:/videos/rec.mp4", segments))
        assert doc["version"] == 2
        assert doc["mediaFileName"] == "rec.mp4"
        assert len(doc["cutSegments"]) == 2
        assert doc["cutSegments"][0]["start"] == 0.0
        assert doc["cutSegments"][0]["end"] == 10.0
        assert doc["cutSegments"][0]["name"] == "segment 1"

    def test_skips_segments_without_end(self):
        doc = json.loads(generate_llc("rec.mp4", [Segment(5.0, None)]))
        assert doc["cutSegments"] == []


class TestGenerateMlt:
    def _info(self) -> VideoInfo:
        return VideoInfo(1920, 1080, 30, 1, 754.56, 16, 9)

    def test_well_formed_and_structure(self):
        segments = [Segment(0.0, 10.0), Segment(20.0, 30.0)]
        xml_text = generate_mlt("C:\\videos\\rec.mp4", segments, self._info())
        root = ET.fromstring(xml_text)
        assert root.tag == "mlt"

        profile = root.find("profile")
        assert profile.get("width") == "1920"
        assert profile.get("height") == "1080"
        assert profile.get("frame_rate_num") == "30"

        producers = root.findall("producer")
        bg = producers[0]
        assert bg.get("id") == "bg"
        video_producers = [p for p in producers if p.get("id", "").startswith("producer")]
        assert [p.get("in") for p in video_producers] == ["00:00:00.000", "00:00:20.000"]
        assert [p.get("out") for p in video_producers] == ["00:00:10.000", "00:00:30.000"]

        resource = next(p.find('property[@name="resource"]').text for p in video_producers)
        assert resource == "C:/videos/rec.mp4"

        playlist = root.find('playlist[@id="playlist0"]')
        entries = playlist.findall("entry")
        assert [e.get("producer") for e in entries] == ["producer0", "producer1"]

        tractor = root.find('tractor[@id="tractor0"]')
        assert tractor.get("out") == "00:00:30.000"
        assert [t.get("producer") for t in tractor.findall("track")] == [
            "background",
            "playlist0",
        ]

    def test_empty_segments(self):
        xml_text = generate_mlt("rec.mp4", [], self._info())
        root = ET.fromstring(xml_text)
        assert root.find('playlist[@id="playlist0"]').findall("entry") == []


class TestFindApp:
    def test_versioned_install_dir(self, tmp_path, monkeypatch):
        exe_dir = tmp_path / "LosslessCut-win-x64"
        exe_dir.mkdir()
        exe = exe_dir / "LosslessCut.exe"
        exe.write_bytes(b"")
        monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
        monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        assert find_app("LosslessCut") == exe

    def test_missing_app(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
        monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        assert find_app("NonexistentEditor") is None
