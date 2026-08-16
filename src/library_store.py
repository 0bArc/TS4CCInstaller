from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

from config import CURRENT_DIR
from logger import logger

LIBRARY_PATH = Path(CURRENT_DIR) / "library.json"
_lock = threading.Lock()


def _empty() -> dict:
    return {"items": {}}


def _load() -> dict:
    if not LIBRARY_PATH.exists():
        return _empty()
    try:
        data = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _empty()
        items = data.get("items")
        if not isinstance(items, dict):
            data["items"] = {}
        return data
    except (OSError, json.JSONDecodeError):
        return _empty()


def _save(data: dict) -> None:
    LIBRARY_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def list_installed() -> list[dict[str, Any]]:
    with _lock:
        data = _load()
        items = list(data.get("items", {}).values())
    items.sort(key=lambda x: float(x.get("installed_at") or 0), reverse=True)
    # prune missing files from view but keep record until uninstall
    for item in items:
        files = item.get("files") or []
        item["files_existing"] = sum(1 for f in files if f and os.path.isfile(f))
        item["files_total"] = len(files)
    return items


def get_installed(item_id: int) -> Optional[dict[str, Any]]:
    with _lock:
        return _load().get("items", {}).get(str(item_id))


def record_install(
    *,
    item_id: int,
    title: str,
    artist: str = "",
    category: str = "",
    size: str = "",
    thumbnail_url: str | None = None,
    url: str = "",
    files: list[str],
) -> dict[str, Any]:
    with _lock:
        data = _load()
        key = str(item_id)
        prev = data["items"].get(key) or {}
        merged_files = []
        seen = set()
        for f in list(prev.get("files") or []) + list(files or []):
            if not f:
                continue
            norm = str(Path(f))
            if norm in seen:
                continue
            seen.add(norm)
            merged_files.append(norm)

        entry = {
            "item_id": item_id,
            "title": title or prev.get("title") or f"Item {item_id}",
            "artist": artist or prev.get("artist") or "",
            "category": category or prev.get("category") or "",
            "size": size or prev.get("size") or "",
            "thumbnail_url": thumbnail_url or prev.get("thumbnail_url"),
            "url": url or prev.get("url") or f"https://www.thesimsresource.com/downloads/{item_id}",
            "files": merged_files,
            "installed_at": time.time(),
        }
        data["items"][key] = entry
        _save(data)
        logger.info(f"Library recorded item {item_id} ({len(merged_files)} files)")
        return entry


def uninstall(item_id: int) -> dict[str, Any]:
    with _lock:
        data = _load()
        key = str(item_id)
        entry = data.get("items", {}).get(key)
        if not entry:
            return {"ok": False, "error": "not installed", "removed": []}

        removed = []
        failed = []
        for f in entry.get("files") or []:
            try:
                p = Path(f)
                if p.is_file():
                    p.unlink()
                    removed.append(str(p))
            except OSError as e:
                failed.append({"path": f, "error": str(e)})

        del data["items"][key]
        _save(data)
        logger.info(f"Uninstalled item {item_id}: removed {len(removed)} files")
        return {
            "ok": True,
            "item_id": item_id,
            "removed": removed,
            "failed": failed,
            "title": entry.get("title"),
        }
