from __future__ import annotations
import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from urllib.parse import quote
import requests
from logger import logger

BASE_URL = "https://www.thesimsresource.com"

# (label, browse path)
CATEGORIES: List[Tuple[str, str]] = [
    ("All Sims 4", "/downloads/browse/category/sims4/"),
    ("Featured Creations", "/downloads/browse/category/sims4/featured/1/"),
    ("Accessories", "/downloads/browse/category/sims4-accessories/"),
    ("Clothing", "/downloads/browse/category/sims4-clothing/"),
    ("Eye Colors", "/downloads/browse/category/sims4-eyecolors/"),
    ("Facial Hair", "/downloads/browse/category/sims4-hair-facial/"),
    ("Floors", "/downloads/browse/category/sims4-floors/"),
    ("Hairstyles", "/downloads/browse/category/sims4-hair-hairstyles/"),
    ("Lots", "/downloads/browse/category/sims4-lots/"),
    ("Makeup", "/downloads/browse/category/sims4-makeup/"),
    (
        "Maxis Match",
        "/themes/maxismatch/downloads/browse/category/sims4/skipsetitems/1/",
    ),
    ("Mods", "/downloads/browse/category/sims4-mods/"),
    ("Objects", "/downloads/browse/category/sims4-objects/"),
    ("Pets", "/downloads/browse/category/sims4-pets/"),
    ("Roofs", "/downloads/browse/category/sims4-objects-buildmode-roofs/"),
    ("Rooms", "/downloads/browse/category/sims4-rooms/"),
    ("Sets", "/downloads/browse/category/sims4-sets/"),
    ("Shoes", "/downloads/browse/category/sims4-shoes/"),
    ("Sims", "/downloads/browse/category/sims4-sims/"),
    ("Skintones", "/downloads/browse/category/sims4-skintones/"),
    ("Terrain paints", "/downloads/browse/category/sims4-terrainpaint/"),
    ("Walls", "/downloads/browse/category/sims4-walls/"),
]


@dataclass
class TSRItem:
    item_id: int
    title: str
    category: str
    artist: str
    size: str
    thumbnail_url: Optional[str]
    url: str
    downloads: str = ""
    published: str = ""
    is_vip: bool = False
    artist_slug: str = ""


@dataclass
class BrowsePage:
    items: List[TSRItem]
    total_creations: str
    url: str
    page_count: int = 0
    cnt: int = 0


@dataclass
class TSRItemDetails:
    item_id: int
    title: str
    category: str
    artist: str
    size: str
    description: str
    notes: str
    image_urls: List[str] = field(default_factory=list)
    url: str = ""
    downloads: str = ""
    published: str = ""
    artist_slug: str = ""


def _clean(value: Optional[str]) -> str:
    if value is None:
        return ""
    return html.unescape(value.replace("&amp;", "&")).strip()


def _clean_artist(value: Optional[str]) -> str:
    return re.sub(r"^by\s+", "", _clean(value), flags=re.I).strip()


def _abs_url(path: str) -> str:
    if path.startswith("http"):
        return path
    return BASE_URL + path


def _strip_tags(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _format_unix(ts: str) -> str:
    try:
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        return dt.strftime("%b %d, %Y")
    except (ValueError, OSError, OverflowError):
        return ""


def _format_count(n: str) -> str:
    try:
        return f"{int(n):,}"
    except ValueError:
        return n


def _format_bytes(n: int) -> str:
    if n <= 0:
        return ""
    units = (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024))
    for label, div in units:
        if n >= div:
            val = n / div
            if val >= 10:
                return f"{int(round(val))} {label}"
            text = f"{val:.1f}".rstrip("0").rstrip(".")
            return f"{text} {label}"
    return f"{n} B"


def _size_from_browse_block(block: str) -> str:
    nice = re.search(r'FileSize_nice(?:&quot;|")\s*:\s*(?:&quot;|")([^&"]+)', block)
    if nice:
        return nice.group(1).replace("\\/", "/").strip()
    span = re.search(
        r'<span class="download-size">\s*([^<]+?)\s*</span>', block, re.I
    )
    if span:
        return _clean(span.group(1))
    raw = re.search(r'FileSize(?:&quot;|")\s*:\s*(?:&quot;|")(\d+)', block)
    if raw:
        try:
            return _format_bytes(int(raw.group(1)))
        except ValueError:
            pass
    return ""


def normalize_artist_slug(value: Optional[str]) -> str:
    raw = _clean(value)
    if not raw:
        return ""
    # TSR member URLs use the creatorName field (often underscored).
    if re.fullmatch(r"[A-Za-z0-9_\-.]+", raw):
        return raw
    slug = re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_")
    return slug


def build_artist_browse_url(
    artist_slug: str,
    page: int = 1,
    cnt: int | None = None,
    free_only: bool = False,
    query: str = "",
) -> str:
    slug = normalize_artist_slug(artist_slug)
    path = f"/members/{quote(slug)}/downloads/browse/category/sims4/skipsetitems/1"
    if free_only:
        path = f"{path}/freedownloads/1"
    q = query.strip()
    if q:
        path = f"{path}/search/{quote(q)}"
    if page > 1:
        if cnt and cnt > 0:
            path = f"{path}/page/{page}/cnt/{cnt}"
        else:
            path = f"{path}/page/{page}"
    return BASE_URL + path + "/"


def category_heading(label: str) -> str:
    if label.startswith("All "):
        return f"Download {label} CC"
    return f"Download Sims 4 {label} CC"


def build_browse_url(
    category_path: str,
    query: str = "",
    page: int = 1,
    free_only: bool = False,
) -> str:
    path = category_path.rstrip("/")
    q = query.strip()
    if q:
        path = re.sub(r"/(featured|skipsetitems)/\d+$", "", path)
        path = f"{path}/search/{quote(q)}"
    if free_only:
        path = f"{path}/freedownloads/1"
    if page > 1:
        path = f"{path}/page/{page}"
    return BASE_URL + path + "/"


def _block_is_vip(block: str) -> bool:
    if "VIP Exclusive" in block:
        return True
    for m in re.finditer(r'class="[^"]*early-access[^"]*"[^>]*>', block, re.I):
        tag = m.group(0)
        if "display:none" in tag.replace(" ", "") or "display: none" in tag:
            continue
        return True
    ea = re.search(r"earlyAccessDays&quot;:(null|\d+)", block)
    if ea and ea.group(1) != "null":
        return True
    return False


def fetch_category(url: str, session: requests.Session) -> BrowsePage:
    logger.debug(f"Fetching category page: {url}")
    import http_client

    resp = http_client.get(url, sess=session)
    resp.raise_for_status()
    text = resp.text

    total = ""
    total_m = re.search(r"([\d,]+)\s*Creations", text)
    if total_m:
        total = total_m.group(1)

    cnt = 0
    cnt_m = re.search(r"/page/\d+/cnt/(\d+)", text)
    if cnt_m:
        cnt = int(cnt_m.group(1))
    elif total:
        try:
            cnt = int(total.replace(",", ""))
        except ValueError:
            cnt = 0

    page_count = 0
    pages_js = re.search(r"\btotalPages\s*=\s*(\d+)\s*;", text)
    if pages_js and int(pages_js.group(1)) > 0:
        page_count = int(pages_js.group(1))
    else:
        pages_js = re.search(r"\bPages\s*=\s*(\d+)\s*;", text)
        if pages_js:
            page_count = int(pages_js.group(1))
        else:
            page_m = re.search(r"Page\s*(?:<[^>]+>\s*)*(\d+)\s*/\s*(\d+)", text, re.I)
            if page_m:
                page_count = int(page_m.group(2))
            else:
                pages = [int(p) for p in re.findall(r"/page/(\d+)/cnt/", text)]
                if pages:
                    page_count = max(pages)

    items: List[TSRItem] = []
    for block in text.split('<div class="browse-file"')[1:]:
        try:
            item_id = int(re.search(r'itemId="(\d+)"', block).group(1))
        except (AttributeError, ValueError):
            continue

        title_m = re.search(r'browse-info-title-info">(.*?)</div>', block, re.S)
        if not title_m:
            continue
        title = _clean(title_m.group(1))
        cat_m = re.search(r'browse-info-category">(.*?)</div>', block, re.S)
        category = _clean(cat_m.group(1)) if cat_m else ""
        artist_m = re.search(r'<div class="created-by">\s*(.*?)\s*</div>', block, re.S)
        artist = _clean_artist(artist_m.group(1)) if artist_m else ""
        if not artist:
            creator_m = re.search(r'creator&quot;:&quot;([^&"]+)', block)
            if creator_m:
                artist = _clean_artist(creator_m.group(1))
        slug_m = re.search(r'creatorName&quot;:&quot;([^&"]+)', block)
        artist_slug = normalize_artist_slug(slug_m.group(1) if slug_m else artist)
        size = _size_from_browse_block(block)
        thumb_m = re.search(
            r"class=\"item-image\" style=\"background: url\('([^']+)'\)\"", block
        )
        thumbnail_url = _abs_url(thumb_m.group(1)) if thumb_m else None
        dl_m = re.search(r'downloads&quot;:&quot;(\d+)', block)
        downloads = _format_count(dl_m.group(1)) if dl_m else ""
        pub_m = re.search(r'publishDate&quot;:&quot;(\d+)', block)
        published = _format_unix(pub_m.group(1)) if pub_m else ""

        items.append(
            TSRItem(
                item_id=item_id,
                title=title,
                category=category,
                artist=artist,
                size=size,
                thumbnail_url=thumbnail_url,
                url=f"{BASE_URL}/downloads/{item_id}",
                downloads=downloads,
                published=published,
                is_vip=_block_is_vip(block),
                artist_slug=artist_slug,
            )
        )

    logger.debug(f"Found {len(items)} items")
    return BrowsePage(
        items=items,
        total_creations=total,
        url=url,
        page_count=page_count,
        cnt=cnt,
    )


def fetch_item_details(item_id: int, session: requests.Session) -> TSRItemDetails:
    import http_client

    url = f"{BASE_URL}/downloads/details/id/{item_id}/"
    logger.debug(f"Fetching item details: {url}")
    resp = http_client.get(url, sess=session)
    resp.raise_for_status()
    text = resp.text

    images = [
        _abs_url(src)
        for src in re.findall(
            r'<img class="carousel-image"[^>]*src="([^"]+)"', text
        )
    ]
    seen = set()
    unique_images: List[str] = []
    for src in images:
        if src not in seen:
            seen.add(src)
            unique_images.append(src)

    desc = ""
    desc_m = re.search(
        r'id="info-description"[^>]*>\s*<div class="info-description">(.*?)</div>',
        text,
        re.S | re.I,
    )
    if desc_m:
        desc = _strip_tags(desc_m.group(1))
        for marker in ("Short URL:", "ItemID:", "Filesize:", "Hardware Requirements:"):
            idx = desc.find(marker)
            if idx != -1:
                desc = desc[:idx].rstrip()

    if not desc:
        json_m = re.search(
            r'data-item="\{[^"]*&quot;description&quot;:&quot;(.*?)&quot;',
            text,
        )
        if json_m:
            desc = _clean(
                json_m.group(1).replace("\\n", "\n").replace("\\/", "/")
            )

    notes = ""
    notes_m = re.search(
        r'id="info-notes".*?<ul class="info-attributes[^"]*">(.*?)</ul>',
        text,
        re.S | re.I,
    )
    if notes_m:
        notes = _strip_tags(notes_m.group(1))

    title = ""
    title_m = re.search(r'property="og:title" content="([^"]+)"', text)
    if title_m:
        title = _clean(title_m.group(1))
        parts = [p.strip() for p in title.split(" - ")]
        if len(parts) >= 2:
            title = parts[-1]

    artist = ""
    artist_m = re.search(r'&quot;creator&quot;:&quot;([^&"]+)', text)
    if artist_m:
        artist = _clean_artist(artist_m.group(1))

    artist_slug = ""
    slug_m = re.search(r'&quot;creatorName&quot;:&quot;([^&"]+)', text)
    if slug_m:
        artist_slug = normalize_artist_slug(slug_m.group(1))
    if not artist_slug:
        mem_m = re.search(r"/members/([A-Za-z0-9_\-.]+)/", text)
        if mem_m and mem_m.group(1) not in {"_TRASRAS"}:
            artist_slug = mem_m.group(1)
    if not artist_slug:
        artist_slug = normalize_artist_slug(artist)

    category = ""
    cat_m = re.search(r'&quot;CategoryName_nice&quot;:&quot;([^&"]+)', text)
    if cat_m:
        category = _clean(cat_m.group(1).replace("\\/", "/"))

    size = ""
    size_m = re.search(r"<strong>Filesize:</strong>\s*([^<\n]+)", text, re.I)
    if size_m:
        size = _clean(size_m.group(1))
    else:
        size_m = re.search(r'FileSize_nice&quot;:&quot;([^&"]+)', text)
        if size_m:
            size = size_m.group(1).replace("\\/", "/")

    downloads = ""
    dl_m = re.search(r'downloads&quot;:&quot;(\d+)', text)
    if dl_m:
        downloads = _format_count(dl_m.group(1))

    published = ""
    pub_m = re.search(r'publishDate&quot;:&quot;(\d+)', text)
    if pub_m:
        published = _format_unix(pub_m.group(1))

    if not unique_images:
        og_m = re.search(r'property="og:image" content="([^"]+)"', text)
        if og_m:
            unique_images.append(_abs_url(og_m.group(1)))

    return TSRItemDetails(
        item_id=item_id,
        title=title or f"Item {item_id}",
        category=category,
        artist=artist,
        size=size,
        description=desc,
        notes=notes,
        image_urls=unique_images,
        url=f"{BASE_URL}/downloads/{item_id}",
        downloads=downloads,
        published=published,
        artist_slug=artist_slug,
    )
