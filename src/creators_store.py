from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from config import CURRENT_DIR
from TSRCatalog import normalize_artist_slug

STORE_PATH = Path(CURRENT_DIR) / "creators.json"
_lock = threading.Lock()


def _empty() -> dict:
    return {"hidden": {}, "recent": []}


def _load() -> dict:
    if not STORE_PATH.exists():
        return _empty()
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _empty()
        if not isinstance(data.get("hidden"), dict):
            data["hidden"] = {}
        if not isinstance(data.get("recent"), list):
            data["recent"] = []
        return data
    except (OSError, json.JSONDecodeError):
        return _empty()


def _save(data: dict) -> None:
    STORE_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def hidden_slugs() -> set[str]:
    with _lock:
        return set(_load().get("hidden", {}).keys())


def list_hidden() -> list[dict[str, Any]]:
    with _lock:
        items = list(_load().get("hidden", {}).values())
    items.sort(key=lambda x: str(x.get("name") or x.get("slug") or "").lower())
    return items


def is_hidden(slug: str) -> bool:
    key = normalize_artist_slug(slug)
    if not key:
        return False
    with _lock:
        return key in _load().get("hidden", {})


def hide(slug: str, name: str = "") -> dict[str, Any]:
    key = normalize_artist_slug(slug)
    if not key:
        return {"ok": False, "error": "missing slug"}
    with _lock:
        data = _load()
        entry = {
            "slug": key,
            "name": (name or "").strip() or key.replace("_", " ").strip(" _"),
            "hidden_at": time.time(),
        }
        data["hidden"][key] = entry
        # drop from recent
        data["recent"] = [r for r in data.get("recent", []) if r.get("slug") != key]
        _save(data)
        return {"ok": True, "item": entry}


def unhide(slug: str) -> dict[str, Any]:
    key = normalize_artist_slug(slug)
    if not key:
        return {"ok": False, "error": "missing slug"}
    with _lock:
        data = _load()
        removed = data.get("hidden", {}).pop(key, None)
        _save(data)
        if not removed:
            return {"ok": False, "error": "not hidden"}
        return {"ok": True, "item": removed}


def list_recent(limit: int = 24) -> list[dict[str, Any]]:
    with _lock:
        recent = list(_load().get("recent", []))
    return recent[: max(1, limit)]


def remember(slug: str, name: str = "") -> None:
    key = normalize_artist_slug(slug)
    if not key:
        return
    display = (name or "").strip() or key.replace("_", " ").strip(" _")
    with _lock:
        data = _load()
        if key in data.get("hidden", {}):
            return
        recent = [r for r in data.get("recent", []) if r.get("slug") != key]
        recent.insert(0, {"slug": key, "name": display, "seen_at": time.time()})
        data["recent"] = recent[:40]
        _save(data)


def remember_many(items: list[dict[str, Any]]) -> None:
    for item in items:
        slug = item.get("artist_slug") or ""
        name = item.get("artist") or ""
        if slug:
            remember(str(slug), str(name))


def filter_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocked = hidden_slugs()
    if not blocked:
        return items
    out = []
    for item in items:
        slug = normalize_artist_slug(str(item.get("artist_slug") or ""))
        if slug and slug in blocked:
            continue
        out.append(item)
    return out
