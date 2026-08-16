from __future__ import annotations

import json
import os
import sys
import typing
from pathlib import Path

CONFIG_DICT = typing.TypedDict(
    "Config Dict",
    {
        "downloadDirectory": str,
        "maxActiveDownloads": int,
        "saveDownloadQueue": bool,
        "debug": bool,
        "setupComplete": bool,
    },
)


def _bundle_dir() -> str:
    """Read-only assets (templates/static). Inside _MEIPASS when frozen."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.abspath(__file__))


def _data_dir() -> str:
    """Writable preferences / cache under %APPDATA%\\CCInstaller."""
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    path = Path(base) / "CCInstaller"
    legacy = Path(base) / "TSRCommunityModManager"
    # Keep using the old folder if the user already has data there.
    if not path.exists() and legacy.exists():
        path = legacy
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


BUNDLE_DIR = _bundle_dir()
CURRENT_DIR = _data_dir()
CONFIG_PATH = os.path.join(CURRENT_DIR, "config.json")

DEFAULTS: CONFIG_DICT = {
    "downloadDirectory": "",
    "maxActiveDownloads": 4,
    "saveDownloadQueue": True,
    "debug": False,
    "setupComplete": False,
}


def suggested_download_dir() -> str:
    return str(
        Path.home()
        / "Documents"
        / "Electronic Arts"
        / "The Sims 4"
        / "Mods"
    )


def _normalize(data: dict) -> CONFIG_DICT:
    out: CONFIG_DICT = dict(DEFAULTS)  # type: ignore[assignment]
    out.update({k: data[k] for k in DEFAULTS if k in data})
    out["maxActiveDownloads"] = int(out.get("maxActiveDownloads") or 4)
    out["saveDownloadQueue"] = bool(out.get("saveDownloadQueue"))
    out["debug"] = bool(out.get("debug"))
    out["setupComplete"] = bool(out.get("setupComplete"))
    out["downloadDirectory"] = str(out.get("downloadDirectory") or "").strip()
    return out


def load_config() -> CONFIG_DICT:
    if not os.path.isfile(CONFIG_PATH):
        return dict(DEFAULTS)  # type: ignore[return-value]
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return _normalize(json.load(f))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return dict(DEFAULTS)  # type: ignore[return-value]


def save_config(data: dict) -> CONFIG_DICT:
    merged = _normalize({**CONFIG, **data})
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=4)
        f.write("\n")
    CONFIG.clear()
    CONFIG.update(merged)
    return merged


def needs_onboarding(cfg: CONFIG_DICT | None = None) -> bool:
    c = cfg or CONFIG
    path = (c.get("downloadDirectory") or "").strip()
    if not c.get("setupComplete"):
        return True
    if not path or path in (".", "./"):
        return True
    return not os.path.isdir(os.path.abspath(path))


def resolve_download_dir(cfg: CONFIG_DICT | None = None) -> str:
    c = cfg or CONFIG
    path = (c.get("downloadDirectory") or "").strip() or suggested_download_dir()
    return str(Path(path).expanduser().resolve())


CONFIG: CONFIG_DICT = load_config()
