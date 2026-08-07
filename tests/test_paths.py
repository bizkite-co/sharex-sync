"""Unit tests for ShareX config folder discovery (paths.py)."""

from __future__ import annotations

from pathlib import Path

from sharex_sync.paths import _expand_folder_variables, _guid_bytes, _read_personal_path_cfg


class TestGuidBytes:
    def test_documents_guid(self):
        assert _guid_bytes("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}") == bytes.fromhex(
            "FDD39AD0238F46AFADB46C85480369C7"
        )

    def test_desktop_guid(self):
        assert _guid_bytes("{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}") == bytes.fromhex(
            "B4BFCC3ADB2C424CB0297FE99A87C641"
        )


class TestExpandFolderVariables:
    def test_documents_var(self, tmp_path):
        assert _expand_folder_variables(
            "{MyDocuments}\\ShareX", tmp_path
        ) == tmp_path / "ShareX"

    def test_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SHAREX_HOME", r"C:\Custom\ShareX")
        assert _expand_folder_variables("%SHAREX_HOME%\\config", tmp_path) == Path(
            r"C:\Custom\ShareX\config"
        )


class TestReadPersonalPathCfg:
    def test_found_in_documents(self, tmp_path):
        sharex_dir = tmp_path / "ShareX"
        sharex_dir.mkdir()
        (sharex_dir / "PersonalPath.cfg").write_text(
            "{MyDocuments}\\CustomShareX", encoding="utf-8"
        )
        result = _read_personal_path_cfg(tmp_path)
        assert result is not None
        assert result == tmp_path / "CustomShareX"

    def test_missing(self, tmp_path):
        assert _read_personal_path_cfg(tmp_path) is None
