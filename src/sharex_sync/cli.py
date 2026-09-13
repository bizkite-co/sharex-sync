"""Command-line interface for sharex-sync.

Installed as both `sharex-sync` and `sharex` (ShareX itself has no CLI, so the
short name is free). Bare invocation with no subcommand prints this help.

Subcommands:
  status   - report machine readiness
  mic      - (re)select the recording microphone
  config   - apply tracked settings to ApplicationConfig.json
  hotkeys  - apply tracked hotkeys to HotkeysConfig.json
  recctl   - always-on-top recording control panel
  keys     - print the tracked hotkey cheat sheet
  cut      - detect silences and generate editor cut points
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from . import config, cut, defaults, ffmpeg, health, logutil, mic, paths, recctl, ui

_EXIT_OK = 0
_EXIT_CHANGED = 0
_EXIT_ISSUES = 1


class _RichHelpAction(argparse.Action):
    """-h/--help via ui.print_help instead of argparse's plain-text default."""

    def __init__(self, option_strings, dest=argparse.SUPPRESS, default=argparse.SUPPRESS, help=None):
        super().__init__(option_strings=option_strings, dest=dest, default=default, nargs=0, help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        ui.print_help(parser)
        parser.exit()


def _common_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description=__doc__.splitlines()[0], add_help=False)
    parser.add_argument("-h", "--help", action=_RichHelpAction, help="show this help message and exit")
    parser.add_argument("--config-dir", help="override ShareX personal config folder")
    parser.add_argument("--ffmpeg", help="path to ffmpeg.exe (default: ShareX bundled)")
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    return parser


def _sub_parser(subs: argparse._SubParsersAction, name: str, help_text: str) -> argparse.ArgumentParser:
    return subs.add_parser(name, help=help_text)


def cmd_status(args: argparse.Namespace) -> int:
    report = health.run_report(args.config_dir, args.ffmpeg)
    ui.print_status(report)
    # Auto-start ShareX when health is otherwise fine but the app is down
    if not config.is_sharex_running():
        _ensure_sharex()
        report = health.run_report(args.config_dir, args.ffmpeg)
        ui.print_status(report)
    return _EXIT_OK if report.all_ok else _EXIT_ISSUES


def _ensure_sharex(silent: bool = False) -> bool:
    """Start ShareX if needed. Prints status. Returns True if running."""
    if config.is_sharex_running():
        if not silent:
            print("ShareX: already running")
        return True
    print("ShareX: not running — starting…")
    if config.ensure_sharex_running():
        print("ShareX: started")
        return True
    print("ShareX: failed to start (is it installed?)", file=sys.stderr)
    return False


def cmd_start(args: argparse.Namespace) -> int:
    """Ensure ShareX is running (tray / silent)."""
    return _EXIT_OK if _ensure_sharex() else _EXIT_ISSUES


def cmd_mic(args: argparse.Namespace) -> int:
    personal_path = paths.discover_personal_path(args.config_dir)
    status, detail = mic.reconcile(
        personal_path,
        ffmpeg_path=args.ffmpeg,
        preferred=args.preferred,
        apply=args.apply,
        force=args.force,
    )
    print(f"mic: {status} - {detail}")
    if status == "none":
        return _EXIT_ISSUES
    # Mic only helps if ShareX is up to use the config / register dshow.
    if not getattr(args, "silent", False) and not _ensure_sharex():
        return _EXIT_ISSUES
    return _EXIT_OK


def cmd_recctl(args: argparse.Namespace) -> int:
    if not _ensure_sharex():
        return _EXIT_ISSUES
    code = recctl.run_control(paths.discover_personal_path(args.config_dir))
    if code != 0:
        print(
            "recctl: requires tkinter and the tracked recording hotkeys "
            "(ScreenRecorderActiveWindow/Pause/Stop/AbortScreenRecording) - "
            "run `sharex-sync hotkeys --apply` first",
            file=sys.stderr,
        )
    return code


def _apply_settings(args: argparse.Namespace) -> int:
    personal_path = paths.discover_personal_path(args.config_dir)
    app_config_path = personal_path / config.APP_CONFIG

    if not app_config_path.is_file():
        print(f"error: no config at {app_config_path}", file=sys.stderr)
        return _EXIT_ISSUES

    app_config = config.load_json(app_config_path)
    changed = config.apply_settings_overlay(app_config)

    if args.dry_run:
        if changed:
            print("would update:")
            for key, old in changed.items():
                print(f"  {key}: {old!r} -> {defaults.FFMPEG_SETTINGS.get(key, defaults.CAPTURE_SETTINGS.get(key))!r}")
        else:
            print("already in sync (nothing to change)")
        return _EXIT_OK

    if config.is_sharex_running() and not args.silent:
        print("stopping ShareX so it can't overwrite the edits (configs save on exit)")
    config.stop_sharex()

    if changed:
        config.write_with_backup(app_config_path, app_config)
        print("updated:")
        for key, old in changed.items():
            print(f"  {key}: {old!r} -> {defaults.FFMPEG_SETTINGS.get(key, defaults.CAPTURE_SETTINGS.get(key))!r}")
    else:
        print("already in sync (nothing to change)")

    if not args.silent:
        config.start_sharex()
        print("ShareX restarted")
    return _EXIT_OK


def cmd_config(args: argparse.Namespace) -> int:
    if not args.apply and not args.dry_run:
        print("info: pass --apply to write changes (--dry-run shows what would change)")
        return _EXIT_OK
    return _apply_settings(args)


def cmd_hotkeys(args: argparse.Namespace) -> int:
    personal_path = paths.discover_personal_path(args.config_dir)
    hotkeys_path = personal_path / config.HOTKEYS_CONFIG

    if args.dry_run:
        print(f"would write {len(defaults.HOTKEYS)} hotkeys to {hotkeys_path}")
        for entry in defaults.HOTKEYS:
            combo, job, desc, win = defaults._hotkey_parts(entry)
            win_tag = " +Win" if win else ""
            print(f"  {combo + win_tag:<30} {job} ({desc})")
        return _EXIT_OK

    if config.is_sharex_running() and not args.silent:
        print("stopping ShareX so it can't overwrite the edits (configs save on exit)")
    config.stop_sharex()

    config.write_with_backup(hotkeys_path, defaults.hotkeys_config())
    print(f"wrote {len(defaults.HOTKEYS)} hotkeys to {hotkeys_path}")

    if not args.silent:
        config.start_sharex()
        print("ShareX restarted")
    return _EXIT_OK


def cmd_keys(args: argparse.Namespace) -> int:
    ui.print_keys(defaults.hotkey_displays())
    return _EXIT_OK


def _resolve_ffmpeg(override: str | None) -> Path | None:
    if override:
        return Path(override)
    sharex_dir = ffmpeg.find_sharex_exe().parent if ffmpeg.find_sharex_exe() else None
    return ffmpeg.find_ffmpeg(sharex_dir)


def _print_plan(video: Path, info: cut.VideoInfo, silences: list[cut.Segment], segments: list[cut.Segment]) -> None:
    print(f"video: {video}")
    print(f"duration: {cut.format_clock(info.duration)}  ({info.width}x{info.height} @ {info.fps:g} fps)")
    print(f"silences: {len(silences)}")
    for i, silence in enumerate(silences):
        end = cut.format_clock(silence.end) if silence.end is not None else "<end of video>"
        print(f"  {i + 1:>2}. {cut.format_clock(silence.start)} - {end}")
    print(f"keep: {len(segments)} segment(s)")
    for i, seg in enumerate(segments):
        print(f"  {i + 1:>2}. {cut.format_clock(seg.start)} - {cut.format_clock(seg.end)} ({seg.end - seg.start:.1f}s)")


def cmd_cut(args: argparse.Namespace) -> int:
    video = Path(args.video)
    if not video.is_file():
        print(f"error: no such file: {video}", file=sys.stderr)
        return _EXIT_ISSUES

    ffmpeg_path = _resolve_ffmpeg(args.ffmpeg)
    if ffmpeg_path is None or not ffmpeg_path.is_file():
        print("error: ffmpeg not found (is ShareX installed, or pass --ffmpeg)", file=sys.stderr)
        return _EXIT_ISSUES

    try:
        silences = cut.detect_silence(ffmpeg_path, video, args.threshold_db, args.min_silence)
        info = cut.probe_video(ffmpeg_path, video)
        segments = cut.keep_segments(info.duration, silences, args.margin)
    except cut.CutError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_ISSUES

    _print_plan(video, info, silences, segments)

    if not segments:
        print("nothing to keep - the whole recording appears to be silence")
        return _EXIT_ISSUES

    targets = _normalize_targets(args.target)
    if args.dry_run:
        print("dry run - no files written (targets: " + ", ".join(targets) + ")")
        return _EXIT_OK

    out_dir = Path(args.out_dir) if args.out_dir else None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    if "losslesscut" in targets:
        path = cut.llc_project_path(video, out_dir)
        path.write_text(cut.generate_llc(video, segments), encoding="utf-8")
        written.append(path)
        print(f"wrote LosslessCut project: {path}")
    if "shotcut" in targets:
        path = cut.mlt_project_path(video, out_dir)
        path.write_text(cut.generate_mlt(video, segments, info), encoding="utf-8")
        written.append(path)
        print(f"wrote Shotcut project: {path}")
    if "ffmpeg" in targets:
        out_path = Path(args.out) if args.out else (out_dir or video.parent) / f"{video.stem}.cut.mp4"
        try:
            cut.cut_lossless(ffmpeg_path, video, segments, out_path, reencode=args.reencode)
            written.append(out_path)
            print(f"wrote cut: {out_path}")
        except cut.CutError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return _EXIT_ISSUES

    if args.open:
        _open_editor(targets, video, written)

    return _EXIT_OK


def _open_editor(targets: list[str], video: Path, written: list[Path]) -> None:
    if "losslesscut" in targets:
        exe = cut.find_app("LosslessCut")
        if exe is None:
            print("LosslessCut not found - open the video and it will load the .llc project")
        else:
            subprocess.Popen([str(exe), str(video)])
    if "shotcut" in targets:
        exe = cut.find_app("shotcut")
        if exe is None:
            print("Shotcut not found - open the .mlt project manually")
        else:
            mlt = next((p for p in written if p.suffix == ".mlt"), None)
            if mlt is not None:
                subprocess.Popen([str(exe), str(mlt)])


def _normalize_targets(targets: list[str] | None) -> list[str]:
    if not targets:
        return ["losslesscut", "shotcut"]
    result: set[str] = set()
    for target in targets:
        if target == "all":
            result.update(("losslesscut", "shotcut", "ffmpeg"))
        else:
            result.add(target)
    return sorted(result)


def _add_runtime_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true", help="show what would change without writing")
    parser.add_argument("--apply", action="store_true", help="write changes (and restart ShareX)")
    parser.add_argument("--silent", action="store_true", help="don't stop/start ShareX (manual restart required)")


def main(argv: list[str] | None = None) -> int:
    prog = Path(sys.argv[0]).stem if sys.argv else "sharex-sync"
    common = _common_parser(prog)
    subs = common.add_subparsers(dest="command")

    p_status = _sub_parser(subs, "status", "check this machine is ready to record")

    p_start = _sub_parser(subs, "start", "start ShareX if it is not already running")

    p_mic = _sub_parser(subs, "mic", "select the recording microphone")
    p_mic.add_argument("--preferred", action="append", help="preferred mic pattern (repeatable)")
    p_mic.add_argument("--force", action="store_true", help="rewrite even if already correct")
    _add_runtime_flags(p_mic)

    p_recctl = _sub_parser(
        subs, "recctl", "always-on-top recording control (mic, REC state, Record/Pause/Stop/Abort)"
    )

    p_keys = _sub_parser(subs, "keys", "print the tracked hotkey cheat sheet")

    p_config = _sub_parser(subs, "config", "apply tracked capture settings")
    _add_runtime_flags(p_config)

    p_hotkeys = _sub_parser(subs, "hotkeys", "apply tracked hotkeys")
    _add_runtime_flags(p_hotkeys)

    p_cut = _sub_parser(subs, "cut", "detect silences and generate editor cut points")
    p_cut.add_argument("video", help="recording to analyze")
    p_cut.add_argument("--threshold-db", type=float, default=cut.DEFAULT_NOISE_DB,
                       help=f"silence threshold in dB (default: {cut.DEFAULT_NOISE_DB})")
    p_cut.add_argument("--min-silence", type=float, default=cut.DEFAULT_MIN_SILENCE_S,
                       help=f"minimum silence length in seconds (default: {cut.DEFAULT_MIN_SILENCE_S})")
    p_cut.add_argument("--margin", type=float, default=cut.DEFAULT_MARGIN_S,
                       help=f"seconds kept on each side of speech (default: {cut.DEFAULT_MARGIN_S})")
    p_cut.add_argument("--target", action="append", choices=["losslesscut", "shotcut", "ffmpeg", "all"],
                       help="output(s) to generate (repeatable; default: losslesscut,shotcut)")
    p_cut.add_argument("--out", help="output file for the ffmpeg target (default: <video>.cut.mp4)")
    p_cut.add_argument("--out-dir", help="directory for generated project files")
    p_cut.add_argument("--reencode", action="store_true",
                       help="frame-accurate ffmpeg cuts via re-encode (default: lossless -c copy, keyframe-aligned)")
    p_cut.add_argument("--open", action="store_true", help="launch the editor after generating")
    p_cut.add_argument("--dry-run", action="store_true", help="print the cut plan without writing")

    args = common.parse_args(argv)

    if args.command is None:
        ui.print_help(common)
        return _EXIT_OK

    logutil.setup_logging(verbose=args.verbose)

    handlers = {
        "status": cmd_status,
        "start": cmd_start,
        "mic": cmd_mic,
        "recctl": cmd_recctl,
        "keys": cmd_keys,
        "config": cmd_config,
        "hotkeys": cmd_hotkeys,
        "cut": cmd_cut,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
