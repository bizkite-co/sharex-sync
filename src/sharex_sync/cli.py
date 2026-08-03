"""Command-line interface for sharex-sync.

Subcommands:
  health   - report machine readiness
  mic      - (re)select the recording microphone
  config   - apply tracked settings to ApplicationConfig.json
  hotkeys  - apply tracked hotkeys to HotkeysConfig.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config, defaults, ffmpeg, health, logutil, mic, paths

_EXIT_OK = 0
_EXIT_CHANGED = 0
_EXIT_ISSUES = 1


def _common_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description=__doc__.splitlines()[0])
    parser.add_argument("--config-dir", help="override ShareX personal config folder")
    parser.add_argument("--ffmpeg", help="path to ffmpeg.exe (default: ShareX bundled)")
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    return parser


def _sub_parser(subs: argparse._SubParsersAction, name: str, help_text: str) -> argparse.ArgumentParser:
    return subs.add_parser(name, help=help_text)


def cmd_health(args: argparse.Namespace) -> int:
    report = health.run_report(args.config_dir, args.ffmpeg)
    health.print_report(report)
    return _EXIT_OK if report.all_ok else _EXIT_ISSUES


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
    return _EXIT_OK


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
        for combo, job, desc in defaults.HOTKEYS:
            print(f"  {combo:<26} {job} ({desc})")
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


def _add_runtime_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true", help="show what would change without writing")
    parser.add_argument("--apply", action="store_true", help="write changes (and restart ShareX)")
    parser.add_argument("--silent", action="store_true", help="don't stop/start ShareX (manual restart required)")


def main(argv: list[str] | None = None) -> int:
    common = _common_parser("sharex-sync")
    subs = common.add_subparsers(dest="command", required=True)

    p_health = _sub_parser(subs, "health", "check this machine is ready to record")

    p_mic = _sub_parser(subs, "mic", "select the recording microphone")
    p_mic.add_argument("--preferred", action="append", help="preferred mic pattern (repeatable)")
    p_mic.add_argument("--force", action="store_true", help="rewrite even if already correct")
    _add_runtime_flags(p_mic)

    p_config = _sub_parser(subs, "config", "apply tracked capture settings")
    _add_runtime_flags(p_config)

    p_hotkeys = _sub_parser(subs, "hotkeys", "apply tracked hotkeys")
    _add_runtime_flags(p_hotkeys)

    args = common.parse_args(argv)
    logutil.setup_logging(verbose=args.verbose)

    handlers = {
        "health": cmd_health,
        "mic": cmd_mic,
        "config": cmd_config,
        "hotkeys": cmd_hotkeys,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
