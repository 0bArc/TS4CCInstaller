from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any, Optional

from config import CURRENT_DIR

CACHE_DIR = Path(CURRENT_DIR) / "cache"

# Per-namespace TTL (seconds). Manual clear_all() still wipes everything.
TTL_BY_NAMESPACE = {
    "browse": 8 * 60 * 60,
    "items": 12 * 60 * 60,
    "images": 24 * 60 * 60,
}
DEFAULT_TTL = 12 * 60 * 60


def _ensure_root() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _ttl_for(namespace: str) -> float:
    return float(TTL_BY_NAMESPACE.get(namespace, DEFAULT_TTL))


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _json_path(namespace: str, key: str) -> Path:
    return CACHE_DIR / namespace / f"{_key_hash(key)}.json"


def _bytes_base(namespace: str, key: str) -> Path:
    return CACHE_DIR / namespace / _key_hash(key)


def _is_fresh(cached_at: float, namespace: str) -> bool:
    if cached_at <= 0:
        return False
    return (time.time() - cached_at) < _ttl_for(namespace)


def clear_all() -> None:
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
    _ensure_root()


def maybe_expire() -> bool:
    """No-op whole-tree wipe. Entries expire per-key via TTL on read.

    Kept for API compatibility with older callers.
    """
    _ensure_root()
    return False


def get_json(namespace: str, key: str) -> Optional[Any]:
    _ensure_root()
    path = _json_path(namespace, key)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None

    # New envelope: {"_ts": ..., "v": ...}
    if isinstance(raw, dict) and "_ts" in raw and "v" in raw:
        if not _is_fresh(float(raw.get("_ts") or 0), namespace):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        return raw["v"]

    # Legacy unwrapped payload: treat as stale so sizes/schema refresh once.
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return None


def set_json(namespace: str, key: str, value: Any) -> None:
    _ensure_root()
    folder = CACHE_DIR / namespace
    folder.mkdir(parents=True, exist_ok=True)
    path = _json_path(namespace, key)
    envelope = {"_ts": time.time(), "v": value}
    path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")


def get_bytes(namespace: str, key: str) -> Optional[tuple[bytes, str]]:
    _ensure_root()
    base = _bytes_base(namespace, key)
    data_path = Path(str(base) + ".bin")
    meta_path = Path(str(base) + ".ctype")
    ts_path = Path(str(base) + ".ts")
    if not data_path.exists():
        return None
    try:
        cached_at = 0.0
        if ts_path.exists():
            cached_at = float(ts_path.read_text(encoding="utf-8").strip() or 0)
        if not _is_fresh(cached_at, namespace):
            for p in (data_path, meta_path, ts_path):
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
            return None
        content = data_path.read_bytes()
        ctype = (
            meta_path.read_text(encoding="utf-8").strip()
            if meta_path.exists()
            else "application/octet-stream"
        )
        return content, ctype
    except (OSError, ValueError):
        return None


def set_bytes(namespace: str, key: str, content: bytes, content_type: str) -> None:
    _ensure_root()
    folder = CACHE_DIR / namespace
    folder.mkdir(parents=True, exist_ok=True)
    base = _bytes_base(namespace, key)
    Path(str(base) + ".bin").write_bytes(content)
    Path(str(base) + ".ctype").write_text(
        content_type or "application/octet-stream", encoding="utf-8"
    )
    Path(str(base) + ".ts").write_text(str(time.time()), encoding="utf-8")


def age_hours() -> float:
    """Hours since oldest fresh entry was written (0 if empty)."""
    _ensure_root()
    oldest: Optional[float] = None
    now = time.time()
    for path in CACHE_DIR.rglob("*"):
        if not path.is_file():
            continue
        ts = None
        if path.suffix == ".json":
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and "_ts" in raw:
                    ts = float(raw["_ts"])
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                continue
        elif path.name.endswith(".ts"):
            try:
                ts = float(path.read_text(encoding="utf-8").strip() or 0)
            except (OSError, ValueError):
                continue
        else:
            continue
        if ts and ts > 0:
            oldest = ts if oldest is None else min(oldest, ts)
    if oldest is None:
        return 0.0
    return max(0.0, (now - oldest) / 3600.0)


def ttl_hours_summary() -> dict[str, float]:
    return {k: v / 3600.0 for k, v in TTL_BY_NAMESPACE.items()}
