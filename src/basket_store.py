from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from config import CURRENT_DIR

BASKET_PATH = Path(CURRENT_DIR) / "basket.json"
_lock = threading.Lock()


def load_basket() -> dict[str, Any]:
    with _lock:
        if not BASKET_PATH.exists():
            return {}
        try:
            data = json.loads(BASKET_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError, TypeError):
            return {}


def save_basket(items: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        clean: dict[str, Any] = {}
        if isinstance(items, dict):
            for key, row in items.items():
                if not isinstance(row, dict):
                    continue
                try:
                    item_id = int(row.get("item_id") or key)
                except (TypeError, ValueError):
                    continue
                clean[str(item_id)] = {
                    "item_id": item_id,
                    "title": str(row.get("title") or f"Item {item_id}"),
                    "artist": str(row.get("artist") or ""),
                    "size": str(row.get("size") or ""),
                    "thumbnail_url": row.get("thumbnail_url") or None,
                    "url": str(row.get("url") or f"/item/{item_id}"),
                }
        BASKET_PATH.write_text(
            json.dumps(clean, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return clean
