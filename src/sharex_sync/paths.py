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


def _guid_bytes(folder_guid: str) -> bytes:
    """Parse a ``{XXXXXXXX-...-...}`` KNOWNFOLDERID into its 16 raw bytes."""
    return (
        bytes.fromhex(folder_guid[1:9])
        + bytes.fromhex(folder_guid[10:14])
        + bytes.fromhex(folder_guid[15:19])
        + bytes.fromhex(folder_guid[20:24] + folder_guid[25:37])
    )


def _known_folder(folder_guid: str) -> Path | None:
    """Resolve a Windows KNOWNFOLDERID via SHGetKnownFolderPath."""
    if os.name != "nt":
        return None
    try:
        import ctypes
    except ImportError:
        return None

    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    try:
        g = _GUID()
        ctypes.memmove(ctypes.byref(g), _guid_bytes(folder_guid), ctypes.sizeof(g))
        p = ctypes.c_void_p()
        hr = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(g), 0, None, ctypes.byref(p)
        )
        if hr != 0:
            return None
        try:
            return Path(ctypes.wstring_at(p))
        finally:
            ctypes.windll.ole32.CoTaskMemFree(p)
    except Exception:
        return None


def _registry_documents() -> Path | None:
    """Read the Documents ("Personal") shell folder from the registry.

    ``SHGetKnownFolderPath`` can fail on setups where Documents is redirected
    via OneDrive (returns E_FILE_NOT_FOUND), while the registry value the API
    resolves internally is present and correct. This mirrors that resolution.
    """
    if os.name != "nt":
        return None
    import winreg

    for sub in (
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
    ):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub) as key:
                value, _ = winreg.QueryValueEx(key, "Personal")
        except OSError:
            continue
        value = os.path.expandvars(value) if isinstance(value, str) else ""
        if value and os.path.isabs(value):
            return Path(value)
    return None


def my_documents() -> Path:
    return (
        _known_folder(_FOLDERID_DOCUMENTS)
        or _registry_documents()
        or Path.home()
    )


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


def _has_app_config(folder: Path) -> bool:
    try:
        return (folder / "ApplicationConfig.json").is_file()
    except OSError:
        return False


def _candidate_personal_folders(documents: Path) -> list[Path]:
    """Possible ShareX personal folders when Documents is redirected/mis-resolved."""
    home = Path.home()
    userprofile = Path(os.environ.get("USERPROFILE", str(home)))
    localapp = Path(os.environ.get("LOCALAPPDATA", ""))
    ordered: list[Path] = [
        documents / APP_NAME,
        userprofile / "OneDrive" / "Documents2" / APP_NAME,
        userprofile / "OneDrive" / "Documents" / APP_NAME,
        home / "OneDrive" / "Documents2" / APP_NAME,
        home / "OneDrive" / "Documents" / APP_NAME,
        userprofile / "Documents" / APP_NAME,
        home / "Documents" / APP_NAME,
        localapp / APP_NAME,
        home / APP_NAME,
    ]
    # de-dupe while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for p in ordered:
        key = str(p).casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def discover_personal_path(override: str | None = None) -> Path:
    """Return the ShareX personal config folder.

    ``override`` takes precedence (used by ``--config-dir`` and for testing).

    When Documents resolution fails (common with OneDrive renames like
    ``Documents2``), search known locations for an existing
    ``ApplicationConfig.json`` instead of inventing ``%USERPROFILE%\\ShareX``.
    """
    if override:
        return _expand_folder_variables(override, my_documents())

    documents = my_documents()

    registry_path = _read_registry_personal_path()
    if registry_path:
        resolved = _expand_folder_variables(registry_path, documents)
        if _has_app_config(resolved) or resolved.is_dir():
            return resolved

    cfg_path = _read_personal_path_cfg(documents)
    if cfg_path is not None:
        if _has_app_config(cfg_path) or cfg_path.is_dir():
            return cfg_path

    default = documents / APP_NAME
    if _has_app_config(default):
        return default

    for candidate in _candidate_personal_folders(documents):
        if _has_app_config(candidate):
            return candidate

    return default


def config_files(personal_path: Path) -> dict[str, Path]:
    """Map of ShareX config file names to their paths under the personal folder."""
    return {
        "ApplicationConfig.json": personal_path / "ApplicationConfig.json",
        "HotkeysConfig.json": personal_path / "HotkeysConfig.json",
    }
