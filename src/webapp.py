from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Optional

import requests
from flask import Flask, jsonify, render_template, request, send_file, Response
from werkzeug.serving import make_server

from config import (
    CONFIG,
    CURRENT_DIR,
    BUNDLE_DIR,
    load_config,
    save_config,
    needs_onboarding,
    resolve_download_dir,
    suggested_download_dir,
)
import cache_store
import http_client
from TSRDownload import TSRDownload
from TSRUrl import TSRUrl
from sims_install import ensure_resource_cfg, install_into_library
import library_store
import creators_store
import basket_store
from cache_store import get_json as cache_get_json
from TSRCatalog import (
    CATEGORIES,
    build_browse_url,
    build_artist_browse_url,
    category_heading,
    normalize_artist_slug,
    fetch_category,
    fetch_item_details,
)
from TSRSession import CAPTCHA_IMAGE_PATH, CAPTCHA_IMAGE_MAGIC
from logger import logger

SESSION_FILE = Path(CURRENT_DIR) / "session"
DEFAULT_CATEGORY = "/downloads/browse/category/sims4-clothing/"

app = Flask(
    __name__,
    template_folder=str(Path(BUNDLE_DIR) / "templates"),
    static_folder=str(Path(BUNDLE_DIR) / "static"),
)

_lock = threading.Lock()
_state = {
    "session_id": None,
    "pending_http": None,
    "downloads": {},
}

# Download concurrency (server-side; honors maxActiveDownloads).
_dl_lock = threading.Lock()
_dl_active = 0

# Image origin fetch gate + singleflight.
_image_sem = threading.Semaphore(3)
_image_inflight: dict[str, dict] = {}
_image_inflight_lock = threading.Lock()


def _http() -> requests.Session:
    return http_client.session()


def _set_download_status(item_id: int, status: str) -> None:
    with _lock:
        _state["downloads"][item_id] = status


def _get_download_status(item_id: int) -> str:
    with _lock:
        return str(_state["downloads"].get(item_id, "") or "")


def _acquire_download_slot() -> None:
    """Block until under maxActiveDownloads."""
    global _dl_active
    while True:
        cfg = load_config()
        max_n = max(1, min(16, int(cfg.get("maxActiveDownloads") or 4)))
        with _dl_lock:
            if _dl_active < max_n:
                _dl_active += 1
                return
        time.sleep(0.25)


def _release_download_slot() -> None:
    global _dl_active
    with _dl_lock:
        _dl_active = max(0, _dl_active - 1)


def _fetch_image_origin(url: str) -> tuple[bytes, str]:
    """Fetch image from TSR with concurrency cap and singleflight."""
    with _image_inflight_lock:
        flight = _image_inflight.get(url)
        if flight is None:
            flight = {
                "event": threading.Event(),
                "content": None,
                "ctype": None,
                "err": None,
                "leader": True,
            }
            _image_inflight[url] = flight
            leader = True
        else:
            leader = False

    if not leader:
        flight["event"].wait(timeout=60)
        if flight["err"]:
            raise RuntimeError(flight["err"])
        if flight["content"] is None or flight["ctype"] is None:
            raise RuntimeError("image fetch failed")
        return flight["content"], flight["ctype"]

    try:
        with _image_sem:
            r = http_client.get(url, timeout=(10, 30), retries=2)
            r.raise_for_status()
            flight["content"] = r.content
            flight["ctype"] = r.headers.get("Content-Type", "image/jpeg")
            cache_store.set_bytes("images", url, flight["content"], flight["ctype"])
    except Exception as e:
        flight["err"] = str(e)
    finally:
        flight["event"].set()
        with _image_inflight_lock:
            _image_inflight.pop(url, None)

    if flight["err"]:
        raise RuntimeError(flight["err"])
    if flight["content"] is None or flight["ctype"] is None:
        raise RuntimeError("image fetch failed")
    return flight["content"], flight["ctype"]


def _load_saved_session() -> Optional[str]:
    if SESSION_FILE.exists():
        sid = SESSION_FILE.read_text(encoding="utf-8").strip()
        return sid or None
    return None


def _save_session(session_id: str) -> None:
    SESSION_FILE.write_text(session_id, encoding="utf-8")
    _state["session_id"] = session_id


def _get_ticket(session: requests.Session) -> None:
    http_client.get(
        "https://www.thesimsresource.com/ajax.php"
        "?c=downloads&a=initDownload&itemid=1646133&setItems=&format=zip",
        sess=session,
    )


def _fetch_captcha(session: requests.Session) -> bytes:
    http_client.get(
        "https://www.thesimsresource.com/downloads/session/itemId/1646133",
        sess=session,
    )
    r = http_client.get(
        "https://www.thesimsresource.com/downloads/captcha-image",
        sess=session,
    )
    content_type = r.headers.get("Content-Type", "").lower()
    if r.status_code != 200 or "image" not in content_type:
        raise RuntimeError(
            f"TSR captcha HTTP {r.status_code} ({content_type}). Service may be down."
        )
    if not r.content.startswith(CAPTCHA_IMAGE_MAGIC):
        raise RuntimeError("Captcha response is not a PNG.")
    CAPTCHA_IMAGE_PATH.write_bytes(r.content)
    return r.content


def _try_captcha(session: requests.Session, code: str) -> bool:
    r = http_client.post(
        "https://www.thesimsresource.com/downloads/session/itemId/1646133",
        sess=session,
        data={"captchavalue": code},
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://www.thesimsresource.com",
        },
        allow_redirects=True,
    )
    return (
        r.url
        == "https://www.thesimsresource.com/downloads/download/itemId/1646133"
    )


@app.get("/")
def index():
    return render_template(
        "index.html",
        categories=CATEGORIES,
        default_category=DEFAULT_CATEGORY,
    )


@app.get("/item/<int:item_id>")
def item_page(item_id: int):
    return render_template("item.html", item_id=item_id)


@app.get("/artist/<path:slug>")
def artist_page(slug: str):
    return render_template("artist.html", artist_slug=slug)


@app.get("/api/categories")
def api_categories():
    return jsonify([{"label": label, "path": path} for label, path in CATEGORIES])


@app.get("/api/browse")
def api_browse():
    category = request.args.get("category", DEFAULT_CATEGORY)
    query = request.args.get("q", "")
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1

    label = next((lab for lab, path in CATEGORIES if path == category), "Sims 4")
    url = build_browse_url(category, query, page, free_only=False)
    cache_key = url

    cached = cache_store.get_json("browse", cache_key)
    if cached:
        payload = dict(cached)
        payload["cached"] = True
        items = creators_store.filter_items(list(payload.get("items") or []))
        creators_store.remember_many(items)
        payload["items"] = items
        payload["count"] = len(items)
        return jsonify(payload)

    try:
        result = fetch_category(url, _http())
    except Exception as e:
        logger.exception(e)
        return jsonify({"ok": False, "error": str(e)}), 502

    raw_items = [
        {
            "item_id": i.item_id,
            "title": i.title,
            "category": i.category,
            "artist": i.artist,
            "artist_slug": i.artist_slug,
            "size": i.size,
            "thumbnail_url": i.thumbnail_url,
            "url": i.url,
            "downloads": i.downloads,
            "published": i.published,
        }
        for i in result.items
    ]
    payload = {
        "ok": True,
        "url": result.url,
        "page": page,
        "count": len(raw_items),
        "total_creations": result.total_creations,
        "heading": category_heading(label),
        "category_label": label,
        "items": raw_items,
        "cached": False,
    }
    cache_store.set_json("browse", cache_key, payload)
    items = creators_store.filter_items(raw_items)
    creators_store.remember_many(items)
    out = dict(payload)
    out["items"] = items
    out["count"] = len(items)
    return jsonify(out)


@app.get("/api/item/<int:item_id>")
def api_item(item_id: int):
    cache_key = str(item_id)
    cached = cache_store.get_json("items", cache_key)
    if cached and (cached.get("item") or {}).get("artist_slug"):
        payload = dict(cached)
        payload["cached"] = True
        payload["installed"] = _installed_payload(item_id)
        item = payload.get("item") or {}
        if item.get("artist_slug"):
            creators_store.remember(str(item.get("artist_slug")), str(item.get("artist") or ""))
        return jsonify(payload)

    try:
        details = fetch_item_details(item_id, _http())
    except Exception as e:
        logger.exception(e)
        return jsonify({"ok": False, "error": str(e)}), 502

    payload = {
        "ok": True,
        "item": {
            "item_id": details.item_id,
            "title": details.title,
            "category": details.category,
            "artist": details.artist,
            "artist_slug": details.artist_slug,
            "size": details.size,
            "description": details.description,
            "notes": details.notes,
            "image_urls": details.image_urls,
            "url": details.url,
            "downloads": details.downloads,
            "published": details.published,
        },
        "cached": False,
    }
    cache_store.set_json("items", cache_key, payload)
    if details.artist_slug:
        creators_store.remember(details.artist_slug, details.artist)
    out = dict(payload)
    out["installed"] = _installed_payload(item_id)
    return jsonify(out)


def _installed_payload(item_id: int) -> dict:
    entry = library_store.get_installed(item_id)
    if not entry:
        return {"ok": False, "installed": False}
    files = entry.get("files") or []
    existing = [f for f in files if f and os.path.isfile(f)]
    return {
        "ok": True,
        "installed": True,
        "item_id": item_id,
        "title": entry.get("title"),
        "files": files,
        "files_existing": len(existing),
        "files_total": len(files),
        "folder": str(Path(existing[0]).parent) if existing else (
            str(Path(files[0]).parent) if files else resolve_download_dir(load_config())
        ),
    }


def _category_path_for_label(label: str) -> str:
    text = (label or "").strip().lower()
    if not text:
        return DEFAULT_CATEGORY
    for lab, path in CATEGORIES:
        if lab.lower() == text or lab.lower() in text or text in lab.lower():
            return path
    # TSR detail categories look like "Sims 4 > Clothing"
    for lab, path in CATEGORIES:
        if lab.lower() in text:
            return path
    return DEFAULT_CATEGORY


@app.get("/api/item/<int:item_id>/suggestions")
def api_item_suggestions(item_id: int):
    artist_slug = normalize_artist_slug(request.args.get("artist_slug", ""))
    artist_name = (request.args.get("artist") or "").strip()
    category_hint = request.args.get("category", "")

    items = []
    label = ""
    link = ""
    mode = "category"

    if artist_slug:
        mode = "artist"
        label = artist_name or artist_slug.replace("_", " ").strip(" _")
        url = build_artist_browse_url(artist_slug, page=1)
        link = f"/artist/{artist_slug}"
        try:
            result = fetch_category(url, _http())
            for i in result.items:
                if i.item_id == item_id:
                    continue
                items.append(
                    {
                        "item_id": i.item_id,
                        "title": i.title,
                        "category": i.category,
                        "artist": i.artist,
                        "artist_slug": i.artist_slug or artist_slug,
                        "size": i.size,
                        "thumbnail_url": i.thumbnail_url,
                        "url": i.url,
                    }
                )
                if len(items) >= 8:
                    break
        except Exception as e:
            logger.exception(e)

    if not items:
        mode = "category"
        path = _category_path_for_label(category_hint)
        label = next((lab for lab, p in CATEGORIES if p == path), "Clothing")
        link = f"/?category={path}"
        url = build_browse_url(path, "", 1, free_only=False)
        try:
            result = fetch_category(url, _http())
        except Exception as e:
            logger.exception(e)
            return jsonify({"ok": False, "error": str(e), "items": []}), 502
        for i in result.items:
            if i.item_id == item_id:
                continue
            items.append(
                {
                    "item_id": i.item_id,
                    "title": i.title,
                    "category": i.category,
                    "artist": i.artist,
                    "artist_slug": i.artist_slug,
                    "size": i.size,
                    "thumbnail_url": i.thumbnail_url,
                    "url": i.url,
                }
            )
            if len(items) >= 8:
                break

    items = creators_store.filter_items(items)[:8]
    return jsonify(
        {
            "ok": True,
            "mode": mode,
            "category_label": label,
            "artist_slug": artist_slug,
            "browse_href": link,
            "items": items,
        }
    )


@app.get("/api/artist/<path:slug>")
def api_artist_browse(slug: str):
    artist_slug = normalize_artist_slug(slug)
    if not artist_slug:
        return jsonify({"ok": False, "error": "missing artist"}), 400
    query = (request.args.get("q") or "").strip()
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1
    try:
        cnt = int(request.args.get("cnt", "0") or 0)
    except ValueError:
        cnt = 0

    cache_key = f"artist:{artist_slug}:{page}:{cnt}:{query.lower()}"
    cached = cache_store.get_json("browse", cache_key)
    if cached:
        payload = dict(cached)
        payload["cached"] = True
        payload["hidden"] = creators_store.is_hidden(artist_slug)
        creators_store.remember(artist_slug, str(payload.get("artist") or ""))
        return jsonify(payload)

    # Need cnt for page > 1. Fetch page 1 first if missing.
    if page > 1 and cnt <= 0:
        first_url = build_artist_browse_url(artist_slug, page=1, query=query)
        try:
            first = fetch_category(first_url, _http())
            cnt = first.cnt or 0
        except Exception as e:
            logger.warning(f"artist cnt lookup failed: {e}")

    url = build_artist_browse_url(artist_slug, page=page, cnt=cnt or None, query=query)
    try:
        result = fetch_category(url, _http())
    except Exception as e:
        logger.exception(e)
        return jsonify({"ok": False, "error": str(e)}), 502

    display = artist_slug.replace("_", " ").strip(" _")
    if result.items and result.items[0].artist:
        display = result.items[0].artist

    payload = {
        "ok": True,
        "artist_slug": artist_slug,
        "artist": display,
        "q": query,
        "url": result.url,
        "page": page,
        "count": len(result.items),
        "total_creations": result.total_creations,
        "page_count": result.page_count,
        "cnt": result.cnt or cnt,
        "items": [
            {
                "item_id": i.item_id,
                "title": i.title,
                "category": i.category,
                "artist": i.artist,
                "artist_slug": i.artist_slug or artist_slug,
                "size": i.size,
                "thumbnail_url": i.thumbnail_url,
                "url": i.url,
                "downloads": i.downloads,
                "published": i.published,
            }
            for i in result.items
        ],
        "cached": False,
    }
    cache_store.set_json("browse", cache_key, payload)
    creators_store.remember(artist_slug, display)
    out = dict(payload)
    out["hidden"] = creators_store.is_hidden(artist_slug)
    return jsonify(out)


@app.get("/api/creators/recent")
def api_creators_recent():
    return jsonify({"ok": True, "items": creators_store.list_recent()})


@app.get("/api/creators/hidden")
def api_creators_hidden():
    return jsonify({"ok": True, "items": creators_store.list_hidden()})


@app.post("/api/creators/hide")
def api_creators_hide():
    data = request.get_json(silent=True) or {}
    result = creators_store.hide(
        str(data.get("slug") or ""),
        str(data.get("name") or ""),
    )
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)


@app.post("/api/creators/unhide")
def api_creators_unhide():
    data = request.get_json(silent=True) or {}
    result = creators_store.unhide(str(data.get("slug") or ""))
    if not result.get("ok"):
        return jsonify(result), 404
    return jsonify(result)


@app.get("/api/image")
def api_image():
    url = request.args.get("url", "")
    if not url.startswith("https://www.thesimsresource.com/"):
        return jsonify({"error": "invalid url"}), 400

    cached = cache_store.get_bytes("images", url)
    if cached:
        content, ctype = cached
        return Response(content, content_type=ctype)

    try:
        content, ctype = _fetch_image_origin(url)
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    return Response(content, content_type=ctype)


@app.post("/api/cache/clear")
def api_cache_clear():
    cache_store.clear_all()
    return jsonify({"ok": True})


@app.get("/api/cache/status")
def api_cache_status():
    return jsonify(
        {
            "ok": True,
            "age_hours": round(cache_store.age_hours(), 2),
            "ttl_hours": cache_store.ttl_hours_summary(),
        }
    )


@app.get("/api/session")
def api_session_status():
    sid = _state["session_id"] or _load_saved_session()
    if sid and not _state["session_id"]:
        _state["session_id"] = sid
    return jsonify(
        {
            "ok": True,
            "ready": bool(_state["session_id"]),
            "needs_captcha": _state["pending_http"] is not None,
        }
    )


@app.post("/api/session/start")
def api_session_start():
    with _lock:
        saved = _load_saved_session()
        if saved:
            _state["session_id"] = saved
            _state["pending_http"] = None
            return jsonify({"ok": True, "ready": True, "needs_captcha": False})

        session = http_client.new_session()
        try:
            _get_ticket(session)
            _fetch_captcha(session)
        except Exception as e:
            logger.warning(f"Captcha unavailable: {e}")
            sid = session.cookies.get_dict().get("tsrdlsession")
            if sid:
                _save_session(sid)
                return jsonify({"ok": True, "ready": True, "needs_captcha": False})
            return jsonify(
                {
                    "ok": False,
                    "ready": False,
                    "needs_captcha": False,
                    "error": str(e),
                    "browse_only": True,
                }
            ), 503

        _state["pending_http"] = session
        return jsonify({"ok": True, "ready": False, "needs_captcha": True})


@app.get("/api/captcha.png")
def api_captcha_image():
    if not CAPTCHA_IMAGE_PATH.exists():
        return jsonify({"error": "no captcha"}), 404
    return send_file(CAPTCHA_IMAGE_PATH, mimetype="image/png")


@app.post("/api/session/captcha")
def api_session_captcha():
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "code required"}), 400

    with _lock:
        session = _state.get("pending_http")
        if session is None:
            return jsonify({"ok": False, "error": "no pending captcha"}), 400
        if not _try_captcha(session, code):
            try:
                _fetch_captcha(session)
            except Exception:
                pass
            return jsonify({"ok": False, "error": "invalid captcha", "needs_captcha": True}), 400

        sid = session.cookies.get_dict().get("tsrdlsession")
        if not sid:
            return jsonify({"ok": False, "error": "no session cookie"}), 500
        _save_session(sid)
        _state["pending_http"] = None
        return jsonify({"ok": True, "ready": True})


@app.get("/api/settings")
def api_settings_get():
    cfg = load_config()
    return jsonify(
        {
            "ok": True,
            "settings": cfg,
            "needs_onboarding": needs_onboarding(cfg),
            "suggested_download_directory": suggested_download_dir(),
            "resolved_download_directory": (
                resolve_download_dir(cfg) if cfg.get("downloadDirectory") else ""
            ),
        }
    )


@app.post("/api/settings")
def api_settings_save():
    data = request.get_json(silent=True) or {}
    updates = {}
    if "downloadDirectory" in data:
        updates["downloadDirectory"] = str(data["downloadDirectory"] or "").strip()
    if "maxActiveDownloads" in data:
        try:
            updates["maxActiveDownloads"] = max(1, min(16, int(data["maxActiveDownloads"])))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "invalid maxActiveDownloads"}), 400
    if "saveDownloadQueue" in data:
        updates["saveDownloadQueue"] = bool(data["saveDownloadQueue"])
    if "debug" in data:
        updates["debug"] = bool(data["debug"])
    if "setupComplete" in data:
        updates["setupComplete"] = bool(data["setupComplete"])

    if "downloadDirectory" in updates and updates["downloadDirectory"]:
        path = Path(updates["downloadDirectory"]).expanduser()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return jsonify({"ok": False, "error": f"cannot create folder: {e}"}), 400
        updates["downloadDirectory"] = str(path.resolve())

    cfg = save_config(updates)
    return jsonify(
        {
            "ok": True,
            "settings": cfg,
            "needs_onboarding": needs_onboarding(cfg),
        }
    )


@app.post("/api/settings/pick-folder")
def api_settings_pick_folder():
    try:
        import webview
    except ImportError:
        return jsonify({"ok": False, "error": "folder picker unavailable"}), 501
    if not webview.windows:
        return jsonify({"ok": False, "error": "no app window"}), 400
    result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
    if not result:
        return jsonify({"ok": True, "path": None, "cancelled": True})
    path = result[0] if isinstance(result, (list, tuple)) else str(result)
    return jsonify({"ok": True, "path": path, "cancelled": False})


@app.get("/library")
def library_page():
    return render_template("library.html")


@app.get("/api/basket")
def api_basket_get():
    return jsonify({"ok": True, "items": basket_store.load_basket()})


@app.put("/api/basket")
@app.post("/api/basket")
def api_basket_put():
    data = request.get_json(silent=True) or {}
    items = data.get("items")
    if not isinstance(items, dict):
        return jsonify({"ok": False, "error": "items object required"}), 400
    saved = basket_store.save_basket(items)
    return jsonify({"ok": True, "items": saved, "count": len(saved)})


@app.get("/api/library")
def api_library_list():
    return jsonify({"ok": True, "items": library_store.list_installed()})


@app.get("/api/library/<int:item_id>")
def api_library_get(item_id: int):
    payload = _installed_payload(item_id)
    if not payload.get("installed"):
        return jsonify({"ok": True, "installed": False})
    return jsonify(payload)


@app.post("/api/library/<int:item_id>/reveal")
def api_library_reveal(item_id: int):
    payload = _installed_payload(item_id)
    if not payload.get("installed"):
        return jsonify({"ok": False, "error": "not installed"}), 404

    files = [f for f in (payload.get("files") or []) if f and os.path.isfile(f)]
    target = files[0] if files else payload.get("folder")
    if not target:
        return jsonify({"ok": False, "error": "no folder"}), 404

    try:
        path = Path(target)
        if os.name == "nt":
            import subprocess

            if path.is_file():
                subprocess.Popen(["explorer", f"/select,{path}"])
            else:
                subprocess.Popen(["explorer", str(path)])
        else:
            import subprocess

            folder = path if path.is_dir() else path.parent
            subprocess.Popen(["xdg-open", str(folder)])
        return jsonify({"ok": True, "path": str(path)})
    except OSError as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.delete("/api/library/<int:item_id>")
def api_library_uninstall(item_id: int):
    result = library_store.uninstall(item_id)
    if not result.get("ok"):
        return jsonify(result), 404
    return jsonify(result)


def _library_meta_for(item_id: int) -> dict:
    cached = cache_get_json("items", str(item_id))
    if cached and cached.get("item"):
        it = cached["item"]
        return {
            "title": it.get("title") or f"Item {item_id}",
            "artist": it.get("artist") or "",
            "category": it.get("category") or "",
            "size": it.get("size") or "",
            "thumbnail_url": (it.get("image_urls") or [None])[0]
            or it.get("thumbnail_url"),
            "url": it.get("url") or f"https://www.thesimsresource.com/downloads/{item_id}",
        }
    try:
        details = fetch_item_details(item_id, _http())
        return {
            "title": details.title,
            "artist": details.artist,
            "category": details.category,
            "size": details.size,
            "thumbnail_url": (details.image_urls[0] if details.image_urls else None),
            "url": details.url,
        }
    except Exception as e:
        logger.warning(f"Library meta fetch failed for {item_id}: {e}")
        return {
            "title": f"Item {item_id}",
            "artist": "",
            "category": "",
            "size": "",
            "thumbnail_url": None,
            "url": f"https://www.thesimsresource.com/downloads/{item_id}",
        }


@app.post("/api/download/<int:item_id>")
def api_download(item_id: int):
    sid = _state["session_id"] or _load_saved_session()
    if not sid:
        return jsonify({"ok": False, "error": "session not ready"}), 401
    _state["session_id"] = sid

    cfg = load_config()
    if needs_onboarding(cfg):
        return jsonify({"ok": False, "error": "finish setup first (menu > Settings)"}), 400

    path = resolve_download_dir(cfg)
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        ensure_resource_cfg(
            Path(path).parent if Path(path).name.lower() == "tsrlibrary" else Path(path)
        )
    except OSError as e:
        return jsonify({"ok": False, "error": f"download dir error: {e}"}), 500

    current = _get_download_status(item_id)
    if current in ("Downloading", "Queued") or current.startswith("Downloading "):
        return jsonify({"ok": True, "status": current or "Queued"})
    _set_download_status(item_id, "Queued")

    def run():
        session_id = sid
        _acquire_download_slot()
        try:
            _set_download_status(item_id, "Downloading")
            primary = TSRUrl(f"https://www.thesimsresource.com/downloads/{item_id}")
            queue = [primary]
            try:
                queue.extend(TSRUrl.getRequiredItems(primary))
            except Exception as e:
                logger.warning(f"Required items lookup failed: {e}")

            seen = set()
            for url in queue:
                if url.itemId in seen:
                    continue
                seen.add(url.itemId)
                _set_download_status(
                    item_id,
                    f"Downloading {url.itemId}..."
                    if url.itemId != item_id
                    else "Downloading",
                )
                downloader = TSRDownload(url, session_id)
                downloader.init()
                refreshed = downloader.current_session_id()
                if refreshed and refreshed != session_id:
                    _save_session(refreshed)
                    session_id = refreshed
                file_name = downloader.download(path)
                files = install_into_library(path, file_name)
                if not files:
                    raise RuntimeError(
                        f"Download finished but nothing was installed from {file_name}. "
                        "Lots/rooms/Sims need Tray files; clothing/objects need .package files."
                    )
                meta = _library_meta_for(url.itemId)
                library_store.record_install(
                    item_id=url.itemId,
                    title=meta["title"],
                    artist=meta["artist"],
                    category=meta["category"],
                    size=meta["size"],
                    thumbnail_url=meta["thumbnail_url"],
                    url=meta["url"],
                    files=files,
                )
            _set_download_status(item_id, "Downloaded")
        except Exception as e:
            logger.exception(e)
            _set_download_status(item_id, f"Failed: {e}")
        finally:
            _release_download_slot()

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"ok": True, "status": "Queued"})


@app.get("/api/download/<int:item_id>/status")
def api_download_status(item_id: int):
    return jsonify({"ok": True, "status": _get_download_status(item_id)})


@app.get("/api/legal")
def api_legal():
    candidates = [
        Path(BUNDLE_DIR) / "LICENSE",
        Path(CURRENT_DIR) / "LICENSE",
        Path(BUNDLE_DIR).parent / "LICENSE",
        Path(__file__).resolve().parent.parent / "LICENSE",
    ]
    text = ""
    for path in candidates:
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            break
    return jsonify({"ok": True, "license": text or "MIT License (file not bundled)."})


def _show_fatal(message: str) -> None:
    """Surface launch failures when console is hidden (frozen .exe)."""
    try:
        crash = Path(CURRENT_DIR) / "crash.log"
        crash.write_text(message, encoding="utf-8")
    except OSError:
        pass
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0,
            message[:1000],
            "CC Installer - TSR Community Manager",
            0x10,
        )
    except Exception:
        print(message)


def main(host: str = "127.0.0.1", port: int = 8765):
    try:
        _main_impl(host, port)
    except SystemExit:
        raise
    except Exception as e:
        import traceback

        _show_fatal(
            "App failed to start.\n\n"
            f"{e}\n\n"
            f"Details written to crash.log next to the app.\n\n"
            f"{traceback.format_exc()}"
        )
        raise


def _main_impl(host: str = "127.0.0.1", port: int = 8765):
    import os
    import sys

    # Must run before any window is created (Windows taskbar grouping).
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "CCInstaller.TSRCommunityManager.1"
            )
        except Exception:
            pass

    cache_store.maybe_expire()
    url = f"http://{host}:{port}/"
    server = make_server(host, port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        import webview
    except ImportError as e:
        raise SystemExit(
            "pywebview is required for the desktop app.\n"
            "Install with: pip install pywebview"
        ) from e

    width, height = 1360, 900
    x = y = None
    try:
        import ctypes

        user32 = ctypes.windll.user32
        screen_w = int(user32.GetSystemMetrics(0))
        screen_h = int(user32.GetSystemMetrics(1))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
    except Exception:
        pass

    def force_quit():
        try:
            server.shutdown()
        except Exception:
            pass
        # Hard exit: daemon Flask / download threads otherwise keep process alive.
        os._exit(0)

    class WindowApi:
        def __init__(self):
            self._maximized = False

        def minimize(self):
            if webview.windows:
                webview.windows[0].minimize()

        def toggle_maximize(self):
            if not webview.windows:
                return False
            window = webview.windows[0]
            if self._maximized:
                window.restore()
                self._maximized = False
            else:
                window.maximize()
                self._maximized = True
            return self._maximized

        def is_maximized(self):
            return self._maximized

        def close(self):
            # Destroy first so UI closes immediately, then kill process.
            try:
                if webview.windows:
                    webview.windows[0].destroy()
            except Exception:
                pass
            threading.Thread(target=force_quit, daemon=True).start()

    window = webview.create_window(
        "CC Installer - TSR Community Manager",
        url,
        js_api=WindowApi(),
        width=width,
        height=height,
        min_size=(960, 680),
        background_color="#000000",
        frameless=True,
        easy_drag=False,
        shadow=True,
        x=x,
        y=y,
    )
    try:
        window.events.closed += force_quit
    except Exception:
        pass

    icon_path = Path(BUNDLE_DIR) / "static" / "STCM.ico"
    start_kwargs = {
        # Persist localStorage across launches (default private_mode wipes it).
        "private_mode": False,
        "storage_path": str(Path(CURRENT_DIR) / "webview"),
    }
    if icon_path.is_file():
        start_kwargs["icon"] = str(icon_path)
    webview.start(**start_kwargs)
    force_quit()


if __name__ == "__main__":
    main()
