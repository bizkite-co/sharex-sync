"""Unit tests for the Rich-based terminal output (ui.py).

Rich treats a plain string like "[options]" as markup unless it's escaped -
these guard against dynamic text (help strings, file paths, descriptions)
silently vanishing when it happens to contain square brackets.
"""

from __future__ import annotations

import argparse

from sharex_sync import ui
from sharex_sync.health import Check, Report


class TestPrintSubcommandHelp:
    def _parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="sharex cut", description="detect silences", add_help=False)
        parser.add_argument("video", help="recording to analyze")
        parser.add_argument("--to", help="trim to this point [HH:MM:SS]")
        return parser

    def test_usage_placeholder_not_swallowed(self, capsys):
        ui.print_subcommand_help(self._parser())
        out = capsys.readouterr().out
        assert "<options>" in out
        assert "video" in out

    def test_bracketed_help_text_survives(self, capsys):
        ui.print_subcommand_help(self._parser())
        out = capsys.readouterr().out
        assert "[HH:MM:SS]" in out


class TestPrintStatus:
    def test_bracketed_detail_survives(self, capsys):
        report = Report(checks=[Check("mic", False, "no device [default] found")])
        ui.print_status(report)
        out = capsys.readouterr().out
        assert "[default]" in out


class TestPrintKeys:
    def test_bracketed_description_survives(self, capsys):
        ui.print_keys([{
            "job": "Custom",
            "description": "Do the [special] thing",
            "keycap": "Control+X",
            "windows_chord": "Ctrl+X",
        }])
        out = capsys.readouterr().out
        assert "[special]" in out
