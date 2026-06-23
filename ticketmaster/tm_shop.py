#!/usr/bin/env python3
"""
Tixx shop — list inventory from links.txt and sell tickets on tixx.pw.

Used by tm_viewer_link_registry HTTP API:
  GET  /api/shop/listings
  POST /api/shop/purchase   { listing_id, buyer_email, buyer_name? }
  POST /api/shop/checkout   Stripe Checkout (optional, needs STRIPE_SECRET_KEY)

Env:
  TM_LINKS_FILE / TM_VIEWER_LINKS_TXT — links.txt location (first path only; no merge)
  TM_STUBHUB_STOCK_CSV parent — default links.txt beside stock CSV dir
  SHOP_DISCOUNT — fraction of face value (default 0.5 = 50% off face)
  SHOP_DEFAULT_PRICE_USD — when face unknown (default 35)
  SHOP_PURCHASE_SECRET — optional; if set, POST purchase/checkout require header X-Shop-Secret
  STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET — optional card payments
  TM_RESEND_API_KEY — delivery email (same as viewer OTP)
  TM_DISCOVERY_CONSUMER_KEY — Ticketmaster Discovery API key for event poster images
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

_STOCK_LOCK = threading.Lock()
_MEDIA_CACHE_LOCK = threading.Lock()
_TM_APP_BASE = "https://app.ticketmaster.com"
_RE_VIEWER = re.compile(
    r"https?://[^\s\"'<>\[\]]+/tickets/(\d+)/([^\s\"'<>\[\]/\.]+)",
    re.I,
)
_RE_USD = re.compile(r"(\d+(?:\.\d+)?)")


def _import_marketplace_db():
    try:
        from ticketmaster import tixx_marketplace_db as mdb  # type: ignore
        return mdb
    except ImportError:
        pass
    try:
        import tixx_marketplace_db as mdb  # type: ignore
        return mdb
    except ImportError:
        return None


def _db_upsert_listings_async(listings: list[dict]) -> None:
    mdb = _import_marketplace_db()
    if not mdb or not listings:
        return

    def _work():
        try:
            mdb.init_db()
            mdb.upsert_listings_cache(listings)
        except Exception:
            pass

    threading.Thread(target=_work, daemon=True).start()


def _db_stats() -> dict | None:
    mdb = _import_marketplace_db()
    if not mdb:
        return None
    try:
        mdb.init_db()
        return mdb.marketplace_stats()
    except Exception:
        return None


def _db_record_order(row: dict, buyer_email: str, buyer_name: str, *, payment_method: str = "email") -> None:
    mdb = _import_marketplace_db()
    if not mdb:
        return
    try:
        mdb.init_db()
        venue = _venue_label(row.get("venue") or "")
        mdb.insert_order(
            {
                "buyer_email": buyer_email,
                "buyer_name": buyer_name,
                "listing_id": row.get("listing_id") or row.get("slug"),
                "event_name": row.get("event_name"),
                "event_key": _event_group_key({**row, "venue": venue}),
                "event_date": row.get("event_date"),
                "venue": venue,
                "section": row.get("section"),
                "row": row.get("row"),
                "seat": row.get("seat"),
                "price_usd": row.get("price_usd"),
                "face_value_usd": row.get("face_value_usd"),
                "ticket_link": row.get("link"),
                "payment_method": payment_method,
                "email_sent": True,
            }
        )
    except Exception:
        pass


def _script_roots() -> list[Path]:
    here = Path(__file__).resolve().parent
    return [
        here,
        here.parent,
        Path(r"C:\Users\Administrator\Desktop\Stubhub\stubhub"),
    ]


def _resolve_stock_path() -> Path:
    for key in ("TM_STUBHUB_STOCK_CSV", "SECURE_PASS_STOCK_FILE"):
        v = (os.environ.get(key) or "").strip()
        if v:
            p = Path(v).expanduser()
            if p.is_file():
                return p.resolve()
    for root in _script_roots():
        for cand in (
            root / "secure_pass_stock.csv",
            root.parent / "secure_pass_stock.csv",
            root / "tm.bz" / "secure_pass_stock.csv",
        ):
            if cand.is_file():
                return cand.resolve()
    return _script_roots()[0].parent / "secure_pass_stock.csv"


def _resolve_links_txt() -> Path:
    """Single inventory file: links.txt only (one path — no CSV, no multi-file merge)."""
    for key in ("TM_LINKS_FILE", "TM_VIEWER_LINKS_TXT"):
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        first = re.split(r"[;|,]+", raw)[0].strip()
        if first:
            return _resolve_links_txt_path(Path(first))

    stock_parent = _resolve_stock_path().parent
    for cand in (
        stock_parent / "links.txt",
        stock_parent / "tm.bz" / "links.txt",
        Path.cwd() / "links.txt",
    ):
        if cand.is_file():
            return cand.resolve()

    for root in _script_roots():
        for cand in (root / "links.txt", root.parent / "links.txt"):
            if cand.is_file():
                return cand.resolve()

    extra = (os.environ.get("TM_VIEWER_LINKS_EXTRA") or "").strip()
    if extra:
        first = re.split(r"[;,\n|]+", extra)[0].strip()
        if first:
            return _resolve_links_txt_path(Path(first))

    return stock_parent / "links.txt"


def _resolve_links_txt_path(p: Path) -> Path:
    try:
        r = p.expanduser().resolve()
    except OSError:
        r = p.expanduser()
    if r.is_dir():
        return r / "links.txt"
    return r


def _stock_data_dir() -> Path:
    return _resolve_links_txt().parent


def _extract_viewer_link(text: str) -> str:
    m = _RE_VIEWER.search(text or "")
    return m.group(0) if m else ""


def _pick_link_from_cells(cells: list[str], line: str) -> str:
    if len(cells) > 11:
        link = (cells[11] or "").strip()
        if link.startswith("http") and _RE_VIEWER.search(link):
            return link
    for cell in reversed(cells):
        c = (cell or "").strip()
        if c.startswith("http") and _RE_VIEWER.search(c):
            return c
    return _extract_viewer_link(line)


def _shop_log_path() -> Path:
    return _stock_data_dir() / "shop_orders.jsonl"


def _discount() -> float:
    try:
        return float(os.environ.get("SHOP_DISCOUNT") or "0.5")
    except ValueError:
        return 0.5


def _default_price() -> float:
    try:
        return float(os.environ.get("SHOP_DEFAULT_PRICE_USD") or "35")
    except ValueError:
        return 35.0


def _parse_usd(text: str) -> float | None:
    s = (text or "").strip().replace("$", "").replace(",", "")
    m = _RE_USD.search(s)
    if not m:
        return None
    try:
        return round(float(m.group(1)), 2)
    except ValueError:
        return None


def _csv_split(s: str) -> list[str]:
    cells: list[str] = []
    cur = ""
    in_q = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == '"':
            if in_q and i + 1 < len(s) and s[i + 1] == '"':
                cur += '"'
                i += 2
                continue
            in_q = not in_q
        elif c == "," and not in_q:
            cells.append(cur)
            cur = ""
            i += 1
            continue
        else:
            cur += c
        i += 1
    cells.append(cur)
    return cells


_RE_ISO_DATE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?",
)


def _format_event_date(raw: str) -> tuple[str, str, int]:
    """Return (display_label, sort_key YYYY-MM-DD, epoch_ms for sorting)."""
    s = (raw or "").strip()
    if not s:
        return ("Date TBA", "9999-12-31", 9999999999999)
    m = _RE_ISO_DATE.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh, mm = m.group(4), m.group(5)
        try:
            if hh is not None and mm is not None:
                dt = datetime(y, mo, d, int(hh), int(mm))
                label = dt.strftime("%a, %b %d · %I:%M %p").replace(" 0", " ")
            else:
                dt = datetime(y, mo, d)
                label = dt.strftime("%a, %b %d, %Y")
            sort_key = f"{y:04d}-{mo:02d}-{d:02d}"
            return (label, sort_key, int(dt.timestamp() * 1000))
        except ValueError:
            pass
    return (s[:48], s[:10], 9999999999998)


def _infer_category(event_name: str, venue: str) -> str:
    name = f"{event_name} {venue}".lower()
    if any(k in name for k in ("parking", "park pass", "garage", "lot ", " valet")):
        return "parking"
    if any(
        k in name
        for k in (
            " vs ",
            " vs. ",
            "nba",
            "nfl",
            "mlb",
            "nhl",
            "soccer",
            "football",
            "basketball",
            "baseball",
            "hockey",
            "stadium",
            "arena parking",
        )
    ):
        return "sports"
    if any(k in name for k in ("tour", "concert", "live", "festival", "music")):
        return "concerts"
    return "events"


def _event_group_key(row: dict) -> str:
    return "|".join(
        [
            (row.get("event_name") or "").strip().lower(),
            (row.get("event_date") or "").strip()[:10],
            (row.get("venue") or "").strip().lower(),
        ]
    )


def _venue_label(raw: str) -> str:
    v = (raw or "").strip()
    if not v or v.lower() in ("unknown", "n/a", "na", "-"):
        return "Venue TBA"
    return v


def _shop_event_images_cache_path() -> Path:
    return _stock_data_dir() / "shop_event_images.json"


def _event_media_cache_paths() -> list[Path]:
    stock_parent = _stock_data_dir()
    paths: list[Path] = [
        _shop_event_images_cache_path(),
        stock_parent / "results" / "tm_event_media.json",
    ]
    for root in _script_roots():
        paths.extend(
            [
                root / "results" / "tm_event_media.json",
                root.parent / "results" / "tm_event_media.json",
                root / "draft" / "results" / "tm_event_media.json",
            ]
        )
    out: list[Path] = []
    seen: set[str] = set()
    for p in paths:
        key = str(p.resolve()) if p.is_file() else str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _load_event_media_cache() -> dict:
    merged: dict = {}
    for path in _event_media_cache_paths():
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(raw, dict):
            continue
        for k, v in raw.items():
            if isinstance(v, dict) and k not in merged:
                merged[k] = v
    return merged


def _save_shop_event_images_cache(cache: dict) -> None:
    path = _shop_event_images_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def _normalize_event_name(name: str) -> str:
    s = re.sub(r"\s+", " ", (name or "").strip().lower())
    for prefix in ("parking - ", "parking – ", "parking: "):
        if s.startswith(prefix):
            s = s[len(prefix) :].strip()
            break
    return s


def _discovery_keyword(event_name: str) -> str:
    s = (event_name or "").strip()
    if not s:
        return ""
    for prefix in ("Parking - ", "Parking – ", "Parking: ", "parking - ", "parking – ", "parking: "):
        if s.lower().startswith(prefix.lower()):
            s = s[len(prefix) :].strip()
            break
    s = re.sub(r"\s*\([^)]*parking[^)]*\)\s*$", "", s, flags=re.I).strip()
    s = re.sub(r"\s*\+\s*", " ", s)
    if ":" in s:
        s = s.split(":", 1)[0].strip() or s
    return s[:120]


def _discovery_consumer_key() -> str:
    return (os.environ.get("TM_DISCOVERY_CONSUMER_KEY") or "").strip()


def _discovery_best_image_url(images: object) -> str | None:
    if not isinstance(images, list):
        return None
    best_u, best_w = "", -1
    for im in images:
        if not isinstance(im, dict):
            continue
        u = (im.get("url") or "").strip()
        if not (u.startswith("http://") or u.startswith("https://")):
            continue
        try:
            w = int(im.get("width") or 0)
        except (TypeError, ValueError):
            w = 0
        if w >= best_w:
            best_w = w
            best_u = u
    return best_u or None


def _fetch_event_image_discovery(keyword: str, *, api_key: str, timeout: float = 20.0) -> str | None:
    kw = (keyword or "").strip()[:160]
    if not kw or not api_key:
        return None
    params = urllib.parse.urlencode(
        {
            "apikey": api_key,
            "keyword": kw,
            "size": "8",
            "countryCode": "US",
            "locale": "*",
        }
    )
    url = f"{_TM_APP_BASE}/discovery/v2/events.json?{params}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "tixx-shop/1.0 (event images)", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    emb = data.get("_embedded") or {}
    events = emb.get("events") if isinstance(emb, dict) else None
    if not isinstance(events, list):
        return None
    for ev in events:
        if not isinstance(ev, dict):
            continue
        u = _discovery_best_image_url(ev.get("images"))
        if u:
            return u
    return None


def _lookup_cached_image(
    event_name: str,
    event_id: str,
    event_key: str,
    cache: dict | None = None,
) -> str | None:
    cache = cache if cache is not None else _load_event_media_cache()
    ek = (event_key or "").strip()
    if ek:
        ent = cache.get(ek)
        if isinstance(ent, dict):
            u = (ent.get("image_url") or "").strip()
            if u.startswith("http"):
                return u
    eid = (event_id or "").strip().upper()
    if eid:
        ent = cache.get(eid)
        if isinstance(ent, dict):
            u = (ent.get("image_url") or "").strip()
            if u.startswith("http"):
                return u
    name_norm = _normalize_event_name(event_name)
    if not name_norm:
        return None
    for ent in cache.values():
        if not isinstance(ent, dict):
            continue
        if _normalize_event_name(str(ent.get("event_name") or "")) == name_norm:
            u = (ent.get("image_url") or "").strip()
            if u.startswith("http"):
                return u
    return None


def _resolve_event_image(
    event_name: str,
    event_id: str,
    event_key: str,
    *,
    cache: dict | None = None,
    allow_discovery: bool = False,
) -> str | None:
    hit = _lookup_cached_image(event_name, event_id, event_key, cache=cache)
    if hit:
        return hit
    if not allow_discovery:
        return None
    api_key = _discovery_consumer_key()
    if not api_key:
        return None
    kw = _discovery_keyword(event_name)
    if not kw:
        return None
    img = _fetch_event_image_discovery(kw, api_key=api_key)
    if not img and event_id:
        img = _fetch_event_image_discovery(event_id, api_key=api_key)
    if img and event_key:
        with _MEDIA_CACHE_LOCK:
            shop_cache = _load_shop_event_images_cache()
            shop_cache[event_key] = {
                "event_name": event_name,
                "event_id": event_id,
                "image_url": img,
                "updated_unix": int(time.time()),
            }
            _save_shop_event_images_cache(shop_cache)
    return img


def _load_shop_event_images_cache() -> dict:
    path = _shop_event_images_cache_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _attach_cached_images(listings: list[dict]) -> None:
    cache = _load_event_media_cache()
    by_key: dict[str, str] = {}
    for row in listings:
        ek = row.get("event_key") or ""
        if ek in by_key:
            row["image_url"] = by_key[ek]
            continue
        url = _resolve_event_image(
            row.get("event_name") or "",
            row.get("event_id") or "",
            ek,
            cache=cache,
            allow_discovery=False,
        )
        if url:
            by_key[ek] = url
            row["image_url"] = url


def shop_resolve_event_images(body: dict) -> dict:
    events = body.get("events")
    if not isinstance(events, list):
        return {"ok": False, "error": "invalid_events"}
    try:
        limit = min(max(int(body.get("limit") or 12), 1), 25)
    except (TypeError, ValueError):
        limit = 12
    cache = _load_event_media_cache()
    images: dict[str, str] = {}
    resolved = 0
    for item in events:
        if resolved >= limit:
            break
        if not isinstance(item, dict):
            continue
        ek = str(item.get("event_key") or "").strip()
        name = str(item.get("event_name") or "").strip()
        eid = str(item.get("event_id") or "").strip()
        if not ek or not name:
            continue
        url = _resolve_event_image(name, eid, ek, cache=cache, allow_discovery=True)
        if url:
            images[ek] = url
            cache[ek] = {"event_name": name, "event_id": eid, "image_url": url}
            resolved += 1
            time.sleep(0.08)
    return {"ok": True, "images": images, "resolved": len(images)}


def _parse_stock_line(raw_line: str, *, source: str = "") -> dict | None:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None
    if " | " not in line:
        return None
    combo, payload = line.split(" | ", 1)
    cells = _csv_split(payload)
    if len(cells) < 12:
        return None
    link = _pick_link_from_cells(cells, line)
    if not link.startswith("http"):
        return None
    m = _RE_VIEWER.search(link)
    if not m:
        return None
    gid, slug = m.group(1), m.group(2)
    face = _parse_usd(cells[9] if len(cells) > 9 else "")
    disc = _discount()
    if face is not None:
        price = round(face * disc, 2)
    else:
        price = _default_price()
    return {
        "raw_line": raw_line.rstrip("\n\r") + "\n",
        "combo": combo.strip(),
        "event_id": cells[0].strip(),
        "event_name": cells[1].strip(),
        "event_date": cells[2].strip(),
        "venue": cells[3].strip(),
        "section": cells[6].strip(),
        "row": cells[7].strip(),
        "seat": cells[8].strip(),
        "face_value_usd": face,
        "price_usd": price,
        "link": link,
        "gid": gid,
        "slug": slug,
        "listing_id": slug,
        "source_file": source,
    }


def _public_listing(row: dict) -> dict:
    date_label, date_sort, date_ts = _format_event_date(row.get("event_date") or "")
    venue = _venue_label(row.get("venue") or "")
    category = _infer_category(row.get("event_name") or "", venue)
    event_key = _event_group_key({**row, "venue": venue})
    search_blob = " ".join(
        [
            row.get("event_name") or "",
            venue,
            row.get("section") or "",
            row.get("row") or "",
            row.get("seat") or "",
            date_label,
            category,
        ]
    ).lower()
    return {
        "listing_id": row["listing_id"],
        "event_key": event_key,
        "event_id": row.get("event_id") or "",
        "event_name": row["event_name"],
        "event_date": row["event_date"],
        "event_date_display": date_label,
        "event_date_sort": date_sort,
        "event_date_ts": date_ts,
        "venue": venue,
        "venue_raw": row.get("venue") or "",
        "section": row["section"],
        "row": row["row"],
        "seat": row["seat"],
        "price_usd": row["price_usd"],
        "face_value_usd": row.get("face_value_usd"),
        "discount_label": "50% off face value",
        "category": category,
        "search_blob": search_blob,
        "path": f"tickets/{row['gid']}/{row['slug']}",
        "image_url": "",
    }


def _event_summaries(listings: list[dict]) -> list[dict]:
    groups: dict[str, dict] = {}
    for row in listings:
        ek = str(row.get("event_key") or row.get("event_name") or "")
        if not ek:
            continue
        if ek not in groups:
            groups[ek] = {
                "event_key": ek,
                "event_name": row.get("event_name") or "",
                "event_id": row.get("event_id") or "",
                "event_date_display": row.get("event_date_display") or "",
                "venue": row.get("venue") or "",
                "category": row.get("category") or "events",
                "image_url": row.get("image_url") or "",
                "ticket_count": 0,
                "min_price_usd": row.get("price_usd") or 0,
            }
        g = groups[ek]
        g["ticket_count"] += 1
        price = row.get("price_usd") or 0
        if price and (not g["min_price_usd"] or price < g["min_price_usd"]):
            g["min_price_usd"] = price
        if not g["image_url"] and (row.get("image_url") or "").startswith("http"):
            g["image_url"] = row["image_url"]
        if not g["event_id"] and row.get("event_id"):
            g["event_id"] = row["event_id"]
    out = list(groups.values())
    out.sort(key=lambda x: (-(x.get("ticket_count") or 0), x.get("event_name") or ""))
    return out


def _load_listings(*, limit: int = 500) -> tuple[list[dict], Path, str | None]:
    path = _resolve_links_txt()
    if not path.is_file():
        return [], path, "links_txt_not_found"
    listings: list[dict] = []
    seen_ids: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return [], path, f"links_txt_read_failed: {e}"
    src = str(path)
    for line in text.splitlines():
        row = _parse_stock_line(line, source=src)
        if not row:
            continue
        lid = (row.get("listing_id") or row.get("slug") or "").strip()
        if not lid or lid in seen_ids:
            continue
        seen_ids.add(lid)
        pub = _public_listing(row)
        listings.append(pub)
    listings.sort(key=lambda x: (x.get("event_date") or "", x.get("event_name") or ""))
    if limit > 0:
        listings = listings[:limit]
    return listings, path, None


def shop_listings(limit: int = 500) -> dict:
    listings, path, err = _load_listings(limit=limit)
    if err and not listings:
        return {
            "ok": False,
            "error": err.split(":")[0] if err else "links_txt_not_found",
            "detail": err,
            "links_txt": str(path),
            "listings": [],
            "count": 0,
            "event_count": 0,
        }
    _attach_cached_images(listings)
    _db_upsert_listings_async(listings)
    stats = _db_stats()
    events = _event_summaries(listings)
    return {
        "ok": True,
        "links_txt": str(path),
        "stock_path": str(path),
        "count": len(listings),
        "event_count": len(events),
        "events": events,
        "listings": listings,
        "shop_email": "ezy.dev.bot@gmail.com",
        "email_purchase_enabled": (os.environ.get("SHOP_ALLOW_EMAIL_PURCHASE") or "").strip().lower()
        in ("1", "true", "yes"),
        "stripe_enabled": bool((os.environ.get("STRIPE_SECRET_KEY") or "").strip()),
        "marketplace": stats,
    }


def _normalize_email(em: str) -> str:
    return (em or "").strip().lower()


def _valid_email(em: str) -> bool:
    em = _normalize_email(em)
    if not em or "@" not in em:
        return False
    dom = em.rsplit("@", 1)[-1]
    return "." in dom


def _append_shop_log(entry: dict) -> None:
    p = _shop_log_path()
    try:
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _send_purchase_email(to_email: str, buyer_name: str, row: dict) -> tuple[bool, str]:
    name = (buyer_name or "").strip() or to_email.split("@", 1)[0] or "there"
    link = row["link"]
    ev = row["event_name"]
    subj = f"Your Tixx ticket — {ev}"
    html = f"""<!DOCTYPE html><html><body style="font-family:system-ui,sans-serif;color:#121212;line-height:1.5">
<p>Hi {name},</p>
<p>Thanks for your purchase on <strong>Tixx</strong>.</p>
<p><strong>{ev}</strong><br/>
{row.get("event_date") or ""}<br/>
{row.get("venue") or ""}<br/>
Sec {row.get("section")} · Row {row.get("row")} · Seat {row.get("seat")}</p>
<p><a href="{link}" style="display:inline-block;background:#026cdf;color:#fff;padding:12px 22px;
text-decoration:none;border-radius:8px;font-weight:700">Open your ticket</a></p>
<p style="color:#64748b;font-size:14px">Or copy this link:<br/><a href="{link}">{link}</a></p>
<p>Questions? Email <a href="mailto:ezy.dev.bot@gmail.com">ezy.dev.bot@gmail.com</a></p>
</body></html>"""
    api_key = (os.environ.get("TM_RESEND_API_KEY") or "").strip()
    if not api_key:
        return False, "TM_RESEND_API_KEY not configured"
    from_hdr = (os.environ.get("TM_RESEND_FROM") or "").strip() or "Ticketmaster <noreply@tixx.pw>"
    payload = json.dumps(
        {
            "from": from_hdr,
            "to": [to_email],
            "subject": subj,
            "html": html,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if 200 <= resp.status < 300:
                return True, "sent"
            body = resp.read(400).decode("utf-8", errors="replace")
            return False, f"Resend HTTP {resp.status}: {body}"
    except Exception as e:
        return False, str(e)


def _pop_listing_by_id(listing_id: str) -> tuple[dict | None, str | None]:
    lid = (listing_id or "").strip()
    if not lid:
        return None, "listing_id_required"
    path = _resolve_links_txt()
    if not path.is_file():
        return None, "links_txt_not_found"
    with _STOCK_LOCK:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        except OSError as e:
            return None, f"links_txt_read_failed: {e}"
        found_idx: int | None = None
        found_row: dict | None = None
        for idx, line in enumerate(lines):
            row = _parse_stock_line(line, source=str(path))
            if not row:
                continue
            if row["listing_id"] == lid or row["slug"] == lid:
                found_idx = idx
                found_row = row
                break
        if found_idx is None or found_row is None:
            return None, "listing_not_found"
        popped_line = lines[found_idx]
        new_lines = lines[:found_idx] + lines[found_idx + 1 :]
        try:
            path.write_text("".join(new_lines), encoding="utf-8")
        except OSError as e:
            return None, f"links_txt_write_failed: {e}"
        sold = path.parent / "sold_secure.txt"
        try:
            with sold.open("a", encoding="utf-8") as fh:
                fh.write(f"SHOP {datetime.now().isoformat()} | {popped_line.strip()}\n")
        except OSError:
            pass
        return found_row, None


def shop_purchase(listing_id: str, buyer_email: str, buyer_name: str = "") -> tuple[int, dict]:
    allow_free = (os.environ.get("SHOP_ALLOW_EMAIL_PURCHASE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not allow_free:
        return 403, {
            "ok": False,
            "error": "email_purchase_disabled",
            "hint": "Use Pay with card or email ezy.dev.bot@gmail.com",
        }
    if not _valid_email(buyer_email):
        return 400, {"ok": False, "error": "invalid_email"}
    row, err = _pop_listing_by_id(listing_id)
    if err:
        code = 404 if err == "listing_not_found" else 503
        return code, {"ok": False, "error": err}
    ok, detail = _send_purchase_email(buyer_email, buyer_name, row)
    entry = {
        "at": datetime.now().isoformat(),
        "listing_id": listing_id,
        "buyer_email": _normalize_email(buyer_email),
        "event_name": row.get("event_name"),
        "link": row.get("link"),
        "price_usd": row.get("price_usd"),
        "email_ok": ok,
        "email_detail": detail,
    }
    _append_shop_log(entry)
    if not ok:
        # restore line on email failure
        restore_path = Path(row["source_file"]) if row.get("source_file") else _resolve_links_txt()
        try:
            with restore_path.open("a", encoding="utf-8") as fh:
                fh.write(row["raw_line"])
        except OSError:
            pass
        return 502, {
            "ok": False,
            "error": "email_failed",
            "detail": detail,
            "restored_to_stock": True,
        }
    _db_record_order(row, buyer_email, buyer_name, payment_method="email")
    return 200, {
        "ok": True,
        "message": "Ticket sent to your email.",
        "buyer_email": _normalize_email(buyer_email),
        "event_name": row.get("event_name"),
    }


def shop_checkout(listing_id: str, buyer_email: str, buyer_name: str = "") -> tuple[int, dict]:
    """Stripe Checkout session (optional). Fulfillment via webhook or manual."""
    stripe_key = (os.environ.get("STRIPE_SECRET_KEY") or "").strip()
    if not stripe_key:
        return 503, {
            "ok": False,
            "error": "stripe_not_configured",
            "hint": "Set STRIPE_SECRET_KEY or use POST /api/shop/purchase for email delivery.",
            "contact": "ezy.dev.bot@gmail.com",
        }
    if not _valid_email(buyer_email):
        return 400, {"ok": False, "error": "invalid_email"}
    # Reserve: verify listing exists without popping yet
    path = _resolve_links_txt()
    if not path.is_file():
        return 404, {"ok": False, "error": "links_txt_not_found"}
    row: dict | None = None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 503, {"ok": False, "error": "links_txt_read_failed"}
    for line in text.splitlines():
        parsed = _parse_stock_line(line, source=str(path))
        if parsed and (parsed["listing_id"] == listing_id or parsed["slug"] == listing_id):
            row = parsed
            break
    if not row:
        return 404, {"ok": False, "error": "listing_not_found"}
    site = (os.environ.get("SHOP_PUBLIC_BASE") or os.environ.get("TM_VIEWER_PUBLIC_SITE") or "https://tixx.pw").rstrip("/")
    success_url = f"{site}/shop.html?paid=1"
    cancel_url = f"{site}/shop.html?cancelled=1"
    cents = int(round(float(row["price_usd"]) * 100))
    if cents < 50:
        cents = 50
    payload = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "customer_email": _normalize_email(buyer_email),
        "line_items": [
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": cents,
                    "product_data": {
                        "name": row["event_name"][:120],
                        "description": f"Sec {row['section']} Row {row['row']} Seat {row['seat']}",
                    },
                },
                "quantity": 1,
            }
        ],
        "metadata": {
            "listing_id": row["listing_id"],
            "buyer_email": _normalize_email(buyer_email),
            "buyer_name": (buyer_name or "")[:80],
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=data,
        headers={
            "Authorization": f"Bearer {stripe_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            url = body.get("url") or ""
            if not url:
                return 502, {"ok": False, "error": "stripe_no_url", "detail": body}
            return 200, {"ok": True, "checkout_url": url, "session_id": body.get("id")}
    except Exception as e:
        return 502, {"ok": False, "error": "stripe_failed", "detail": str(e)}


def shop_orders_for_email(email: str, limit: int = 50) -> dict:
    em = _normalize_email(email)
    if not em:
        return {"ok": False, "error": "invalid_email", "orders": []}
    mdb = _import_marketplace_db()
    if mdb:
        try:
            mdb.init_db()
            orders = mdb.list_orders_for_email(em, limit=limit)
            if orders:
                return {"ok": True, "orders": orders, "count": len(orders), "source": "database"}
        except Exception:
            pass
    path = _shop_log_path()
    if not path.is_file():
        return {"ok": True, "orders": [], "count": 0, "source": "legacy"}
    orders: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return {"ok": False, "error": "orders_read_failed", "detail": str(e), "orders": []}
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if _normalize_email(str(row.get("buyer_email") or "")) != em:
            continue
        if row.get("email_ok") is False:
            continue
        orders.append(
            {
                "at": row.get("at") or "",
                "listing_id": row.get("listing_id") or "",
                "event_name": row.get("event_name") or "",
                "price_usd": row.get("price_usd"),
                "link": row.get("link") or "",
            }
        )
        if limit > 0 and len(orders) >= limit:
            break
    return {"ok": True, "orders": orders, "count": len(orders), "source": "legacy"}


def shop_account_get(email: str) -> dict:
    mdb = _import_marketplace_db()
    if not mdb:
        return {"ok": False, "error": "database_unavailable"}
    try:
        mdb.init_db()
        return mdb.get_account(_normalize_email(email))
    except Exception as e:
        return {"ok": False, "error": "account_read_failed", "detail": str(e)}


def shop_account_save(email: str, body: dict) -> dict:
    mdb = _import_marketplace_db()
    if not mdb:
        return {"ok": False, "error": "database_unavailable"}
    try:
        mdb.init_db()
        return mdb.save_account(_normalize_email(email), body if isinstance(body, dict) else {})
    except Exception as e:
        return {"ok": False, "error": "account_save_failed", "detail": str(e)}


def shop_sync_inventory(*, image_batch: int = 20) -> dict:
    try:
        from ticketmaster.tixx_shop_sync import run_sync  # type: ignore
    except ImportError:
        try:
            from tixx_shop_sync import run_sync  # type: ignore
        except ImportError as e:
            return {"ok": False, "error": "sync_module_missing", "detail": str(e)}
    return run_sync(image_batch=image_batch)


def shop_check_secret(headers: dict) -> bool:
    need = (os.environ.get("SHOP_PURCHASE_SECRET") or "").strip()
    if not need:
        return True
    got = (headers.get("X-Shop-Secret") or headers.get("x-shop-secret") or "").strip()
    return got and secrets.compare_digest(got, need)
