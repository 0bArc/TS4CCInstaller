from __future__ import annotations

import os
import zipfile
from pathlib import Path

from logger import logger

PACKAGE_EXTS = (".package", ".ts4script")

RESOURCE_CFG_BODY = """Priority 490
PackedFile TSRLibrary/tsrarchive*.package
Priority 500
PackedFile *.package
PackedFile */*.package
PackedFile */*/*.package
PackedFile */*/*/*.package
PackedFile */*/*/*/*.package
PackedFile */*/*/*/*/*.package
"""


def sims4_documents_dir() -> Path:
    return Path.home() / "Documents" / "Electronic Arts" / "The Sims 4"


def default_tsr_library_dir() -> Path:
    """Default install target: Sims 4 Mods folder (any subfolder is fine)."""
    return sims4_documents_dir() / "Mods"


def mods_dir_from_library(library: Path) -> Path:
    """Resolve the Sims 4 Mods root so Resource.cfg is written in the right place."""
    p = library.resolve()
    for candidate in (p, *p.parents):
        if candidate.name.lower() == "mods":
            return candidate
    return p


def ensure_resource_cfg(mods_dir: Path) -> None:
    mods_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = mods_dir / "Resource.cfg"
    if not cfg_path.exists():
        # Windows folder often uses Resource.cfg casing
        alt = mods_dir / "resource.cfg"
        cfg_path = alt if alt.exists() else cfg_path

    existing = ""
    if cfg_path.exists():
        existing = cfg_path.read_text(encoding="utf-8", errors="ignore")

    needs_write = False
    text = existing
    if "TSRLibrary/tsrarchive*.package" not in existing:
        # prepend CCM-compatible lines if missing
        text = (
            "Priority 490\n"
            "PackedFile TSRLibrary/tsrarchive*.package\n"
            + (existing if existing.strip() else RESOURCE_CFG_BODY.split("Priority 500", 1)[-1])
        )
        if "Priority 500" not in text:
            text = RESOURCE_CFG_BODY
        needs_write = True
    if "PackedFile *.package" not in existing and "PackedFile *.package" not in text:
        text = text.rstrip() + "\nPackedFile *.package\n"
        needs_write = True
    if "PackedFile */*.package" not in existing and "PackedFile */*.package" not in text:
        text = text.rstrip() + "\nPackedFile */*.package\n"
        needs_write = True

    if needs_write or not cfg_path.exists():
        if not text.strip():
            text = RESOURCE_CFG_BODY
        cfg_path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        logger.info(f"Updated resource.cfg at {cfg_path}")


def _safe_name(name: str) -> str:
    return "".join(ch for ch in name if ch not in '<>:"/\\|?*')


def install_into_library(download_path: str, file_name: str) -> list[str]:
    """Extract/copy game files into the chosen download folder.

    Web downloads are zips of .package files. Nested packages load when
    Mods/Resource.cfg includes PackedFile */*.package (and deeper).
    """
    library = Path(download_path)
    library.mkdir(parents=True, exist_ok=True)
    ensure_resource_cfg(mods_dir_from_library(library))

    full = library / file_name
    if not full.exists():
        return []

    installed: list[str] = []
    lower = file_name.lower()

    if zipfile.is_zipfile(full):
        with zipfile.ZipFile(full) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                base = os.path.basename(info.filename)
                if not base.lower().endswith(PACKAGE_EXTS):
                    continue
                target_name = _safe_name(base)
                target = library / target_name
                with zf.open(info) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                installed.append(str(target))
                logger.info(f"Installed {target_name} -> {library}")
        try:
            full.unlink()
        except OSError:
            pass
        return installed

    if lower.endswith(PACKAGE_EXTS):
        installed.append(str(full))
        return installed

    logger.warning(f"Downloaded file is not a zip/package: {full}")
    return installed
