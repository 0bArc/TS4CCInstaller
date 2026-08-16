from __future__ import annotations

import os
import zipfile
from pathlib import Path

from logger import logger

# Mods folder: CAS / build / buy CC and script mods
MODS_EXTS = (".package", ".ts4script")

# Tray folder: lots, rooms, households (Library). Must be flat - no subfolders.
TRAY_EXTS = (
    ".trayitem",
    ".blueprint",
    ".bpi",
    ".room",
    ".rmi",
    ".householdbinary",
    ".sgi",
    ".hhi",
)

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


def tray_dir() -> Path:
    return sims4_documents_dir() / "Tray"


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


def _depth_under_mods(mods_root: Path, target_dir: Path) -> int:
    try:
        rel = target_dir.resolve().relative_to(mods_root.resolve())
    except ValueError:
        return 0
    return len(rel.parts)


def ensure_resource_cfg(mods_dir: Path) -> None:
    mods_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = mods_dir / "Resource.cfg"
    if not cfg_path.exists():
        alt = mods_dir / "resource.cfg"
        cfg_path = alt if alt.exists() else cfg_path

    existing = ""
    if cfg_path.exists():
        existing = cfg_path.read_text(encoding="utf-8", errors="ignore")

    needs_write = False
    text = existing
    if "TSRLibrary/tsrarchive*.package" not in existing:
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


def _ext(name: str) -> str:
    return Path(name).suffix.lower()


def _dest_for(filename: str, mods_folder: Path, mods_root: Path) -> Path | None:
    """Pick Mods vs Tray destination for a single extracted file."""
    ext = _ext(filename)
    if ext in TRAY_EXTS:
        return tray_dir()
    if ext in MODS_EXTS:
        # .ts4script only loads one folder deep under Mods.
        if ext == ".ts4script" and _depth_under_mods(mods_root, mods_folder) > 1:
            return mods_root
        return mods_folder
    return None


def _write_bytes(target: Path, data: bytes) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return str(target)


def install_into_library(download_path: str, file_name: str) -> list[str]:
    """Install a downloaded archive into the correct Sims 4 folders.

    - .package / .ts4script -> chosen Mods folder (scripts stay <= 1 level deep)
    - lot / room / Sim tray files -> Documents/.../The Sims 4/Tray (flat)
    - Mixed zips (lot + CC packages) split automatically
    """
    library = Path(download_path)
    library.mkdir(parents=True, exist_ok=True)
    mods_root = mods_dir_from_library(library)
    ensure_resource_cfg(mods_root)
    tray = tray_dir()
    tray.mkdir(parents=True, exist_ok=True)

    full = library / file_name
    if not full.exists():
        return []

    installed: list[str] = []
    lower = file_name.lower()
    skipped = 0

    def place(base_name: str, data: bytes) -> None:
        nonlocal skipped
        dest_dir = _dest_for(base_name, library, mods_root)
        if dest_dir is None:
            skipped += 1
            return
        target_name = _safe_name(os.path.basename(base_name))
        if not target_name:
            skipped += 1
            return
        path = _write_bytes(dest_dir / target_name, data)
        installed.append(path)
        kind = "Tray" if dest_dir == tray else "Mods"
        logger.info(f"Installed [{kind}] {target_name} -> {dest_dir}")

    if zipfile.is_zipfile(full):
        members: list[str] = []
        with zipfile.ZipFile(full) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                base = os.path.basename(info.filename.replace("\\", "/"))
                if not base or base.startswith("."):
                    continue
                members.append(base)
                if _ext(base) not in MODS_EXTS + TRAY_EXTS:
                    skipped += 1
                    continue
                with zf.open(info) as src:
                    place(base, src.read())
        if installed:
            try:
                full.unlink()
            except OSError:
                pass
        else:
            logger.warning(
                f"No installable Sims files in zip {file_name}. "
                f"Members: {members[:30]}{'...' if len(members) > 30 else ''}. "
                f"Kept archive at {full}"
            )
    elif lower.endswith(MODS_EXTS + TRAY_EXTS):
        data = full.read_bytes()
        # Loose tray file downloaded into Mods path: move to Tray.
        if _ext(file_name) in TRAY_EXTS:
            place(file_name, data)
            try:
                full.unlink()
            except OSError:
                pass
        elif _ext(file_name) == ".ts4script" and _depth_under_mods(mods_root, library) > 1:
            place(file_name, data)
            try:
                full.unlink()
            except OSError:
                pass
        else:
            installed.append(str(full))
    else:
        logger.warning(f"Downloaded file is not a zip/package/tray file: {full}")

    if skipped:
        logger.debug(f"Skipped {skipped} non-game files from {file_name}")
    if not installed:
        logger.warning(f"No installable Sims files found in {file_name}")
    return installed
