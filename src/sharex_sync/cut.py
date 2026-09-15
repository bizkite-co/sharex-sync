"""Editing pipeline: silence detection + cut-list generation for editors.

The pipeline is tool-agnostic: one ffmpeg ``silencedetect`` pass produces a
list of silent ranges, which is inverted into "keep" segments (with optional
padding). Those segments are then emitted for any supported editor ("plugin"):

  losslesscut  -> ``.llc`` v2 project (JSON5). LosslessCut auto-loads
                  ``{video stem}-proj.llc`` when the media file is opened.
  shotcut      -> ``.mlt`` project (MLT XML) with one producer per kept
                  segment on the V1 timeline, ready to open and export.
  ffmpeg       -> direct lossless (``-c copy``) cuts + concat, no editor.

Stdlib-only so ``uv tool install`` keeps zero runtime dependencies.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .logutil import LOGGER_NAME

log = logging.getLogger(LOGGER_NAME)

_LLC_SUFFIX = "-proj.llc"
_MLT_SUFFIX = ".mlt"

_SILENCE_START_RE = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*(-?[\d.]+)")
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_RESOLUTION_RE = re.compile(r"Video:.*?(\d{2,5})x(\d{2,5})")
_DAR_RE = re.compile(r"DAR (\d+):(\d+)")
_FPS_RE = re.compile(r",\s*(\d+/\d+|\d+(?:\.\d+)?)\s*fps")
_TBR_RE = re.compile(r",\s*(\d+/\d+)\s*tbr")

DEFAULT_NOISE_DB = -30.0
DEFAULT_MIN_SILENCE_S = 1.0
DEFAULT_MARGIN_S = 0.2


class CutError(Exception):
    """Raised when the editing pipeline cannot proceed."""


@dataclass
class Segment:
    start: float
    end: float | None = None


@dataclass
class VideoInfo:
    width: int
    height: int
    fps_num: int
    fps_den: int
    duration: float
    dar_num: int
    dar_den: int

    @property
    def fps(self) -> float:
        return self.fps_num / self.fps_den


def _reduce(num: int, den: int) -> tuple[int, int]:
    if den == 0:
        return (num, 1)
    g = math.gcd(abs(num), abs(den))
    return (num // g, den // g)


def _parse_fps(line: str) -> tuple[int, int]:
    m = _FPS_RE.search(line)
    tok = m.group(1) if m else None
    if tok is None:
        m = _TBR_RE.search(line)
        tok = m.group(1) if m else None
    if tok is None:
        raise CutError("could not determine frame rate from ffmpeg probe")
    if "/" in tok:
        num, den = tok.split("/", 1)
        return int(num), int(den)
    val = float(tok)
    if val.is_integer():
        return int(val), 1
    return round(val * 1001), 1001  # approximate NTSC-family frame rates


def parse_silence_output(text: str) -> list[Segment]:
    """Parse ffmpeg ``silencedetect`` stderr into silent ranges.

    A trailing ``silence_start`` with no matching ``silence_end`` means the
    recording ends in silence; that segment gets ``end=None``.
    """
    starts = [float(x) for x in _SILENCE_START_RE.findall(text)]
    ends = [float(x) for x in _SILENCE_END_RE.findall(text)]
    return [Segment(s, ends[i] if i < len(ends) else None) for i, s in enumerate(starts)]


def parse_probe_output(text: str) -> VideoInfo:
    """Parse ``ffmpeg -i`` output into the properties an editor project needs."""
    dur_m = _DURATION_RE.search(text)
    if dur_m is None:
        raise CutError("could not read duration from ffmpeg probe")
    hours, minutes, seconds = (float(g) for g in dur_m.groups())
    duration = hours * 3600 + minutes * 60 + seconds

    video_line = next(
        (ln for ln in text.splitlines() if "Video:" in ln and "Stream #" in ln), None
    )
    if video_line is None:
        raise CutError("no video stream found in ffmpeg probe")

    res = _RESOLUTION_RE.search(video_line)
    if res is None:
        raise CutError("could not read resolution from ffmpeg probe")
    width, height = int(res.group(1)), int(res.group(2))

    dar = _DAR_RE.search(video_line)
    if dar is not None:
        dar_num, dar_den = int(dar.group(1)), int(dar.group(2))
    else:
        dar_num, dar_den = _reduce(width, height)

    fps_num, fps_den = _parse_fps(video_line)
    return VideoInfo(width, height, fps_num, fps_den, duration, dar_num, dar_den)


def detect_silence(
    ffmpeg: Path,
    video: Path,
    threshold_db: float = DEFAULT_NOISE_DB,
    min_duration: float = DEFAULT_MIN_SILENCE_S,
) -> list[Segment]:
    """Return silent ranges in ``video`` via ffmpeg ``silencedetect``."""
    cmd = [
        str(ffmpeg),
        "-hide_banner",
        "-nostats",
        "-i",
        str(video),
        "-af",
        f"silencedetect=noise={threshold_db:g}dB:d={min_duration:g}",
        "-f",
        "null",
        "-",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, errors="replace", timeout=3600
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CutError(f"ffmpeg silence detection failed: {exc}") from exc

    output = (proc.stderr or "") + (proc.stdout or "")
    silences = parse_silence_output(output)
    if proc.returncode != 0 and not silences:
        tail = "\n".join(output.strip().splitlines()[-5:])
        raise CutError(f"ffmpeg failed (exit {proc.returncode}): {tail}")
    return silences


def probe_video(ffmpeg: Path, video: Path) -> VideoInfo:
    """Probe a video's profile via ``ffmpeg -i`` (no ffprobe needed)."""
    cmd = [str(ffmpeg), "-hide_banner", "-i", str(video)]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, errors="replace", timeout=60
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CutError(f"ffmpeg probe failed: {exc}") from exc
    output = (proc.stderr or "") + (proc.stdout or "")
    return parse_probe_output(output)


def keep_segments(
    duration: float, silences: list[Segment], margin: float = DEFAULT_MARGIN_S
) -> list[Segment]:
    """Invert silent ranges into the segments to keep, with padding.

    ``margin`` seconds are kept on each side of a kept segment so cuts are not
    right on top of speech. Segments shorter than a frame are dropped, and
    overlapping kept segments (from silences closer than 2*margin) are merged.
    """
    if not silences:
        return [Segment(0.0, duration)]

    kept: list[Segment] = []
    prev = 0.0
    for silence in silences:
        cut_start = max(0.0, silence.start - margin)
        raw_end = silence.end if silence.end is not None else duration
        cut_end = min(duration, raw_end + margin)
        if cut_start > prev + 1e-9:
            kept.append(Segment(prev, cut_start))
        prev = max(prev, cut_end)

    if duration - prev > 1e-9:
        kept.append(Segment(prev, duration))

    merged: list[Segment] = []
    for seg in kept:
        if seg.end is None or seg.end - seg.start < 0.04:
            continue
        if merged and seg.start <= merged[-1].end:
            merged[-1] = Segment(merged[-1].start, max(merged[-1].end, seg.end))
        else:
            merged.append(seg)
    return merged


def to_timecode(seconds: float, fps_num: int, fps_den: int) -> str:
    """Format a time as Shotcut's ``HH:MM:SS.mmm`` timecode, frame-aligned."""
    fps = fps_num / fps_den
    frames = round(seconds * fps)
    ms = round(frames * 1000 / fps)
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def format_clock(seconds: float) -> str:
    seconds = max(0.0, seconds)
    seconds = round(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_clock(text: str) -> float:
    """Parse a clock string ("10:24", "1:02:03") or bare seconds into float seconds."""
    text = text.strip()
    if ":" not in text:
        try:
            return float(text)
        except ValueError:
            raise CutError(f"invalid timestamp: {text!r}") from None
    parts = text.split(":")
    if len(parts) > 3:
        raise CutError(f"invalid timestamp: {text!r}")
    try:
        values = [float(p) for p in parts]
    except ValueError:
        raise CutError(f"invalid timestamp: {text!r}") from None
    seconds = 0.0
    for value in values:
        seconds = seconds * 60 + value
    return seconds


def llc_project_path(video: Path, out_dir: Path | None = None) -> Path:
    base = out_dir or video.parent
    return base / (video.stem + _LLC_SUFFIX)


def mlt_project_path(video: Path, out_dir: Path | None = None) -> Path:
    base = out_dir or video.parent
    return base / (video.stem + _MLT_SUFFIX)


def generate_llc(video: Path | str, segments: list[Segment]) -> str:
    """Build a LosslessCut v2 project (JSON, which is valid JSON5)."""
    video = Path(video)
    doc = {
        "version": 2,
        "mediaFileName": video.name,
        "cutSegments": [
            {
                "start": round(seg.start, 6),
                "end": round(seg.end, 6),
                "name": f"segment {i + 1}",
            }
            for i, seg in enumerate(segments)
            if seg.end is not None
        ],
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def generate_mlt(video: Path | str, segments: list[Segment], info: VideoInfo) -> str:
    """Build a Shotcut project (MLT XML) with one producer per kept segment.

    Mirrors the structure Shotcut writes itself: producers carry in/out
    timecodes and playlist entries reference them without trimming.
    """
    video = Path(video)
    resource = str(video.resolve()).replace("\\", "/")
    total_tc = to_timecode(info.duration, info.fps_num, info.fps_den)
    project_out = to_timecode(segments[-1].end or 0.0, info.fps_num, info.fps_den) if segments else "00:00:00.000"

    mlt = ET.Element(
        "mlt",
        {
            "LC_NUMERIC": "C",
            "version": "7.0.0",
            "title": "sharex-sync",
            "producer": "main_bin",
        },
    )
    ET.SubElement(
        mlt,
        "profile",
        {
            "description": "automatic",
            "width": str(info.width),
            "height": str(info.height),
            "progressive": "1",
            "sample_aspect_num": "1",
            "sample_aspect_den": "1",
            "display_aspect_num": str(info.dar_num),
            "display_aspect_den": str(info.dar_den),
            "frame_rate_num": str(info.fps_num),
            "frame_rate_den": str(info.fps_den),
            "colorspace": "709",
        },
    )

    main_bin = ET.SubElement(mlt, "playlist", {"id": "main_bin"})
    ET.SubElement(main_bin, "property", {"name": "xml_retain"}).text = "1"

    bg = ET.SubElement(mlt, "producer", {"id": "bg"})
    for prop in (
        ("length", total_tc),
        ("eof", "pause"),
        ("resource", "#000000"),
        ("mlt_service", "color"),
        ("mlt_image_format", "rgba"),
        ("aspect_ratio", "1"),
    ):
        ET.SubElement(bg, "property", {"name": prop[0]}).text = prop[1]

    background = ET.SubElement(mlt, "playlist", {"id": "background"})
    ET.SubElement(
        background,
        "entry",
        {"producer": "bg", "in": "00:00:00.000", "out": project_out},
    )

    for i, seg in enumerate(segments):
        if seg.end is None:
            continue
        producer = ET.SubElement(
            mlt,
            "producer",
            {"id": f"producer{i}", "in": to_timecode(seg.start, info.fps_num, info.fps_den), "out": to_timecode(seg.end, info.fps_num, info.fps_den)},
        )
        for prop in (
            ("length", total_tc),
            ("eof", "pause"),
            ("resource", resource),
            ("mlt_service", "avformat"),
        ):
            ET.SubElement(producer, "property", {"name": prop[0]}).text = prop[1]

    playlist0 = ET.SubElement(mlt, "playlist", {"id": "playlist0"})
    ET.SubElement(playlist0, "property", {"name": "shotcut:video"}).text = "1"
    ET.SubElement(playlist0, "property", {"name": "shotcut:name"}).text = "V1"
    for i, seg in enumerate(segments):
        if seg.end is not None:
            ET.SubElement(playlist0, "entry", {"producer": f"producer{i}"})

    tractor = ET.SubElement(
        mlt,
        "tractor",
        {"id": "tractor0", "in": "00:00:00.000", "out": project_out},
    )
    ET.SubElement(tractor, "property", {"name": "shotcut"}).text = "1"
    ET.SubElement(tractor, "property", {"name": "shotcut:projectAudioChannels"}).text = "2"
    ET.SubElement(tractor, "track", {"producer": "background"})
    ET.SubElement(tractor, "track", {"producer": "playlist0"})

    body = ET.tostring(mlt, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"


def cut_lossless(
    ffmpeg: Path,
    video: Path,
    segments: list[Segment],
    out_path: Path,
    reencode: bool = False,
) -> Path:
    """Cut each kept segment and concatenate into ``out_path``.

    Lossless copy cuts are keyframe-aligned (the start rounds back to the
    previous keyframe, which can be several seconds with ShareX's default
    x264 GOP). Pass ``reencode=True`` for frame-accurate cuts.
    """
    if not segments:
        raise CutError("no segments to cut")

    parts_dir = out_path.parent / f"{out_path.stem}_parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    suffix = video.suffix or ".mp4"

    for i, seg in enumerate(segments):
        if seg.end is None:
            continue
        duration = seg.end - seg.start
        if duration <= 0:
            continue
        part = parts_dir / f"part{i:03d}{suffix}"
        if reencode:
            cmd = [
                str(ffmpeg), "-y", "-ss", f"{seg.start:g}", "-i", str(video),
                "-t", f"{duration:g}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", str(part),
            ]
        else:
            cmd = [
                str(ffmpeg), "-y", "-ss", f"{seg.start:g}", "-i", str(video),
                "-t", f"{duration:g}", "-c", "copy",
                "-avoid_negative_ts", "make_zero", str(part),
            ]
        log.debug("running: %s", " ".join(cmd))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=3600)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CutError(f"ffmpeg cut failed: {exc}") from exc
        if proc.returncode != 0:
            tail = "\n".join((proc.stderr or "").strip().splitlines()[-5:])
            raise CutError(f"ffmpeg cut failed (exit {proc.returncode}): {tail}")
        if not part.is_file() or part.stat().st_size == 0:
            raise CutError(f"ffmpeg produced no output for segment {i + 1}")
        parts.append(part)

    if not parts:
        raise CutError("no parts produced")

    concat_list = parts_dir / "concat.txt"
    concat_list.write_text(
        "".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8"
    )
    concat_cmd = [
        str(ffmpeg), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c", "copy", "-movflags", "+faststart", str(out_path),
    ]
    log.debug("running: %s", " ".join(concat_cmd))
    try:
        proc = subprocess.run(concat_cmd, capture_output=True, text=True, errors="replace", timeout=3600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CutError(f"ffmpeg concat failed: {exc}") from exc
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-5:])
        raise CutError(f"ffmpeg concat failed (exit {proc.returncode}): {tail}")

    shutil.rmtree(parts_dir, ignore_errors=True)
    return out_path


def find_app(name: str) -> Path | None:
    """Locate an editor executable on PATH or in common install locations.

    Accepts an install dir that is prefixed with the app name (e.g. a
    `LosslessCut-win-x64` folder for "LosslessCut").
    """
    on_path = shutil.which(name)
    if on_path:
        return Path(on_path)
    exe = Path(f"{name}.exe" if os.name == "nt" else name)
    bases = [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        bases.append(Path(local) / "Programs")
    candidates = []
    for base in bases:
        if not base:
            continue
        base = Path(base)
        candidates.append(base / name / exe)
        candidates.extend(match / exe for match in sorted(base.glob(f"{name}*")) if match.is_dir())
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None
