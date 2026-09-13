"""Unit tests for the sharex-sync / sharex CLI entry point."""

from __future__ import annotations

from sharex_sync import cli


class TestBareInvocationPrintsHelp:
    def test_no_subcommand_prints_help_and_does_not_run_status(self, monkeypatch, capsys):
        calls = []
        monkeypatch.setattr(cli, "cmd_status", lambda args: calls.append(args) or 0)
        assert cli.main([]) == 0
        assert not calls
        out = capsys.readouterr().out
        assert "usage" in out.lower()
        assert "status" in out


class TestStatusSubcommand:
    def test_status_subcommand_runs(self, monkeypatch):
        calls = []
        monkeypatch.setattr(cli, "cmd_status", lambda args: calls.append(args) or 0)
        assert cli.main(["status"]) == 0
        assert len(calls) == 1

    def test_other_subcommands_unaffected(self, monkeypatch):
        calls = []
        monkeypatch.setattr(cli, "cmd_keys", lambda args: calls.append(args) or 0)
        assert cli.main(["keys"]) == 0
        assert len(calls) == 1
