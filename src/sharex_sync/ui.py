"""Rich-based terminal output: borderless tables, subtle background per group.

Shared house style - no box-drawn borders; a logical section is set off by a
faint background band on its header row instead of ruled lines.
"""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.table import Table
from rich.theme import Theme

THEME = Theme(
    {
        "group": "bold white on grey19",
        "cmd": "bold cyan",
        "ok": "green",
        "bad": "bold red",
        "muted": "grey62",
    }
)

console = Console(theme=THEME, highlight=False)

# Command groups for the top-level help screen, in display order.
_HELP_GROUPS = [
    ("Recording", ["status", "start", "mic", "recctl", "keys"]),
    ("Apply settings", ["config", "hotkeys"]),
    ("Editing", ["cut"]),
]

# health.Report check names, grouped for `status`.
_STATUS_GROUPS = [
    ("Config files", ["config-dir", "application-config", "hotkeys-config"]),
    ("Runtime", ["sharex-installed", "ffmpeg", "sharex-running"]),
    ("Audio", ["mic"]),
]

# defaults.HOTKEYS job names, grouped for `keys`.
_KEYS_GROUPS = [
    ("Capture", ["RectangleRegion", "ActiveWindow"]),
    (
        "Recording",
        [
            "ScreenRecorder",
            "ScreenRecorderGIF",
            "ScreenRecorderActiveWindow",
            "PauseScreenRecording",
            "StopScreenRecording",
            "AbortScreenRecording",
        ],
    ),
]


def _subcommand_help(parser: argparse.ArgumentParser) -> dict[str, str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return {a.dest: (a.help or "") for a in action._choices_actions}
    return {}


def print_help(parser: argparse.ArgumentParser) -> None:
    """Render the top-level help screen: grouped commands, no boxes."""
    prog = parser.prog
    help_by_name = _subcommand_help(parser)

    console.print(f"[bold]{prog}[/bold] [muted]- keep ShareX settings, hotkeys, and the mic in sync[/muted]")
    console.print(f"[muted]Usage: {prog} [--config-dir DIR] [--ffmpeg PATH] [--verbose] <command> ...[/muted]\n")

    table = Table(box=None, show_header=False, padding=(0, 1, 0, 1))
    table.add_column(style="cmd", no_wrap=True, min_width=12)
    table.add_column()

    seen = set()
    for group_name, names in _HELP_GROUPS:
        table.add_row(f" {group_name} ", "", style="group")
        for name in names:
            if name in help_by_name:
                seen.add(name)
                table.add_row(f"  {name}", help_by_name[name])
    for name, help_text in help_by_name.items():
        if name not in seen:
            table.add_row(f"  {name}", help_text)

    console.print(table)
    console.print("\n[muted]Run any command with --help for full options.[/muted]")


def print_status(report) -> None:
    """Render a health.Report as a borderless, grouped table."""
    table = Table(box=None, show_header=False, padding=(0, 1, 0, 1))
    table.add_column(no_wrap=True, width=4)
    table.add_column(style="cmd", no_wrap=True)
    table.add_column(overflow="fold")

    by_name = {c.name: c for c in report.checks}
    seen = set()
    for group_name, names in _STATUS_GROUPS:
        table.add_row("", f" {group_name} ", "", style="group")
        for name in names:
            check = by_name.get(name)
            if check is None:
                continue
            seen.add(name)
            mark = "[ok]OK[/]" if check.ok else "[bad]!![/]"
            table.add_row(mark, check.name, check.detail)
    for check in report.checks:
        if check.name not in seen:
            mark = "[ok]OK[/]" if check.ok else "[bad]!![/]"
            table.add_row(mark, check.name, check.detail)

    console.print(table)


def print_keys(displays: list[dict]) -> None:
    """Render the tracked hotkey cheat sheet as a borderless, grouped table."""
    table = Table(box=None, show_header=True, padding=(0, 1, 0, 1), header_style="bold")
    table.add_column("Action", overflow="fold")
    table.add_column("Keycaps", style="cmd", no_wrap=True)
    table.add_column("Windows chord", style="muted", no_wrap=True)

    by_job = {d["job"]: d for d in displays}
    seen = set()
    for group_name, jobs in _KEYS_GROUPS:
        table.add_row(f" {group_name} ", "", "", style="group")
        for job in jobs:
            d = by_job.get(job)
            if d is None:
                continue
            seen.add(job)
            table.add_row(d["description"], d["keycap"], d["windows_chord"])
    for d in displays:
        if d["job"] not in seen:
            table.add_row(d["description"], d["keycap"], d["windows_chord"])

    console.print(table)
