"""Discovery of ShareX's personal config folder.

Mirrors ShareX's own resolution order (ShareX/Program.cs, UpdatePersonalPath):

1. ``-portable`` flag / ``Portable`` file  -> portable folder (exe dir)
2. Registry ``HKLM``/``HKCU\\SOFTWARE\\ShareX`` value ``PersonalPath``
3. ``PersonalPath.cfg`` in ``{MyDocuments}\\ShareX`` (legacy: ``%LOCALAPPDATA%\\ShareX``)
4. Default: ``{MyDocuments}\\ShareX``
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "ShareX"

# {FDD39AD0-238F-46AF-ADB4-6C85480369C7} == FOLDERID_Documents
_FOLDERID_DOCUMENTS = "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"

_REGISTRY_KEY = r"SOFTWARE\ShareX"

_FOLDERID_DESKTOP = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"


def _known_folder(folder_guid: str) -> Path | None:
    """Resolve a Windows KNOWNFOLDERID via SHGetKnownFolderPath."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None
    try:
        p = ctypes.c_void_p()
        hr = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.c_wchar_p(folder_guid), 0, None, ctypes.byref(p)
        )
        if hr != 0:
            return None
        try:
            return Path(ctypes.wstring_at(p))
        finally:
            ctypes.windll.ole32.CoTaskMemFree(p)
    except Exception:
        return None


def my_documents() -> Path:
    return _known_folder(_FOLDERID_DOCUMENTS) or Path.home()


def _expand_folder_variables(path: str, documents: Path) -> Path:
    out = path
    for name, guid in (("MyDocuments", _FOLDERID_DOCUMENTS), ("Desktop", _FOLDERID_DESKTOP)):
        resolved = _known_folder(guid) or documents
        out = out.replace("{%s}" % name, str(resolved))
    out = os.path.expandvars(out)
    out = os.path.expanduser(out)
    return Path(out)


def _read_registry_personal_path() -> str | None:
    if os.name != "nt":
        return None
    import winreg

    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, _REGISTRY_KEY) as key:
                value, _ = winreg.QueryValueEx(key, "PersonalPath")
            if isinstance(value, str) and value.strip():
                return value.strip()
        except OSError:
            continue
    return None


def _read_personal_path_cfg(documents: Path) -> Path | None:
    candidates = [
        documents / APP_NAME / "PersonalPath.cfg",
        Path(os.environ.get("LOCALAPPDATA", "")) / APP_NAME / "PersonalPath.cfg",
    ]
    for cfg in candidates:
        try:
            if cfg.is_file():
                raw = cfg.read_text(encoding="utf-8").strip()
                if raw:
                    p = _expand_folder_variables(raw, documents)
                    if not p.is_absolute():
                        p = documents / p
                    return p
        except OSError:
            continue
    return None


def discover_personal_path(override: str | None = None) -> Path:
    """Return the ShareX personal config folder.

    ``override`` takes precedence (used by ``--config-dir`` and for testing).
    """
    if override:
        return _expand_folder_variables(override, my_documents())

    documents = my_documents()

    registry_path = _read_registry_personal_path()
    if registry_path:
        return _expand_folder_variables(registry_path, documents)

    cfg_path = _read_personal_path_cfg(documents)
    if cfg_path is not None:
        return cfg_path

    return documents / APP_NAME


def config_files(personal_path: Path) -> dict[str, Path]:
    """Map of ShareX config file names to their paths under the personal folder."""
    return {
        "ApplicationConfig.json": personal_path / "ApplicationConfig.json",
        "HotkeysConfig.json": personal_path / "HotkeysConfig.json",
    }
