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

import csv
import gzip
import hashlib
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
_AI_LOCK = threading.Lock()
_AI_RUNNING = False
_MEDIA_CACHE_LOCK = threading.Lock()
_LISTINGS_MEM_CACHE: dict[str, tuple[float, int, list[dict], dict]] = {}
_LISTINGS_WARMING: set[str] = set()
_REGISTRY_SEAT_INDEX: dict[tuple[str, str, str, str], str] | None = None
_REGISTRY_SRS_BUCKETS: dict[tuple[str, str, str], list[tuple[str, str]]] | None = None
_REGISTRY_SEAT_LOCK = threading.Lock()
_TM_APP_BASE = "https://app.ticketmaster.com"
_RE_VIEWER = re.compile(
    r"https?://[^\s\"'<>\[\],]+/tickets/(\d+)/([^\s\"'<>\[\]/\.,]+)",
    re.I,
)
_RE_USD = re.compile(r"(\d+(?:\.\d+)?)")
_SHOP_PUBLIC_BASE = (
    os.environ.get("SHOP_PUBLIC_BASE") or os.environ.get("TM_VIEWER_PUBLIC_SITE") or "https://tixx.pw"
).rstrip("/")


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
    shop_dir = Path(__file__).resolve().parent
    if (shop_dir / "links.txt").is_file():
        return (shop_dir / "links.txt").resolve()
    for key in ("TM_LINKS_FILE", "TM_VIEWER_LINKS_TXT"):
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        first = re.split(r"[;|,]+", raw)[0].strip()
        if first:
            return _resolve_links_txt_path(Path(first))

    stock_parent = _resolve_stock_path().parent
    here = Path(__file__).resolve().parent
    for cand in (
        stock_parent / "links.txt",
        stock_parent / "tm.bz" / "links.txt",
        stock_parent.parent / "tm.bz" / "links.txt",
        Path.cwd() / "links.txt",
        Path.cwd() / "tm.bz" / "links.txt",
        here.parent / "tm.bz" / "links.txt",
        here.parent / "tm.bz" / "links.txt",
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

    for cand in (
        here / "stock.txt",
        here.parent / "stock.txt",
        stock_parent / "stock.txt",
    ):
        if cand.is_file():
            return cand.resolve()

    return stock_parent / "links.txt"


def _inventory_paths() -> list[Path]:
    """All stock files merged for shop listings (links.txt + stock.txt + env overrides)."""
    out: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        if not p.is_file():
            return
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key in seen:
            return
        seen.add(key)
        out.append(p)

    add(_resolve_links_txt())
    for env_key in ("TM_SHOP_STOCK_FILE", "TM_STOCK_FILE"):
        raw = (os.environ.get(env_key) or "").strip()
        if raw:
            add(Path(raw).expanduser())
    here = Path(__file__).resolve().parent
    add(here / "stock.txt")
    add(here.parent / "stock.txt")
    add(_resolve_stock_path().parent / "stock.txt")
    return out


def _inventory_fingerprint() -> str:
    parts: list[str] = []
    for p in _inventory_paths():
        mtime, size = _links_file_fingerprint(p)
        try:
            name = str(p.resolve())
        except OSError:
            name = str(p)
        parts.append(f"{name}:{mtime}:{size}")
    return "|".join(parts) if parts else "empty"


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


def _import_reslug_map():
    try:
        from ticketmaster import tm_reslug_map as rsm  # type: ignore

        return rsm
    except ImportError:
        pass
    try:
        import tm_reslug_map as rsm  # type: ignore

        return rsm
    except ImportError:
        return None


def _reslug_search_dirs() -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()

    def _add(p: Path) -> None:
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)

    for cand in (
        _stock_data_dir(),
        _stock_data_dir().parent,
        Path(__file__).resolve().parent,
    ):
        _add(cand)
    root = _passes_static_root()
    if root:
        _add(root)
        _add(root.parent)
    links = (os.environ.get("TM_VIEWER_LINKS_TXT") or os.environ.get("TM_LINKS_FILE") or "").strip()
    if links:
        try:
            _add(Path(links.split(";")[0].split(",")[0].strip()).expanduser().resolve().parent)
        except OSError:
            pass
    return out


def _reslug_redirects() -> dict[str, str]:
    rsm = _import_reslug_map()
    if not rsm:
        return {}
    try:
        return rsm.load_reslug_redirects(*_reslug_search_dirs())
    except Exception:
        return {}


def _passes_static_root() -> Path | None:
    raw = (os.environ.get("TM_VIEWER_PASSES_STATIC_DIR") or "").strip()
    if raw:
        try:
            p = Path(raw).expanduser().resolve()
            if p.is_dir():
                return p
        except OSError:
            pass
    stock = _stock_data_dir()
    for cand in (
        stock / "tm-vercel-site",
        stock.parent / "tm-vercel-site",
        Path(__file__).resolve().parent / "tm-vercel-site",
    ):
        try:
            if (cand / "tickets").is_dir():
                return cand.resolve()
        except OSError:
            continue
    return None


def _pass_slug_alias_target(root: Path, slug: str) -> Path | None:
    slug = (slug or "").strip()
    rsm = _import_reslug_map()
    if rsm:
        hit = rsm.redirect_target_path(root, slug, _reslug_redirects())
        if hit is not None:
            return hit
    alias_path = root / "tm_viewer_pass_slug_aliases.json"
    if alias_path.is_file():
        try:
            raw = json.loads(alias_path.read_text(encoding="utf-8", errors="replace"))
            rel = (raw.get("redirects") or {}).get(slug) if isinstance(raw, dict) else None
            if rel:
                rel = str(rel).strip().replace("\\", "/")
                if not rel.lower().endswith(".html"):
                    rel = f"{rel}.html"
                cand = (root / rel).resolve()
                cand.relative_to(root.resolve())
                if cand.is_file():
                    return cand
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return None


def _pass_html_resolves(gid: str, slug: str) -> bool:
    """True if tickets/<gid>/<slug>.html exists locally (or unique slug match / alias)."""
    if not (gid or "").strip() or not (slug or "").strip():
        return False
    root = _passes_static_root()
    if not root:
        return True
    g = str(gid).strip()
    s = str(slug).strip()
    primary = root / "tickets" / g / f"{s}.html"
    if primary.is_file():
        return True
    if g == "1" and (root / "tickets" / "0" / f"{s}.html").is_file():
        return True
    alias = _pass_slug_alias_target(root, s)
    if alias is not None:
        return True
    try:
        troot = root / "tickets"
        if troot.is_dir():
            matches = [p for p in troot.glob(f"*/{s}.html") if p.is_file()]
            if len(matches) == 1:
                return True
    except OSError:
        pass
    return False


def _validate_passes_enabled() -> bool:
    return (os.environ.get("SHOP_VALIDATE_PASSES") or "").strip().lower() in ("1", "true", "yes")


def _find_links_txt_viewer_url(slug: str) -> str:
    slug = (slug or "").strip()
    if not slug:
        return ""
    path = _resolve_links_txt()
    if not path.is_file():
        return ""
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if slug not in line:
                    continue
                m = _RE_VIEWER.search(line)
                if m and m.group(2) == slug:
                    return m.group(0)
    except OSError:
        pass
    return ""


def _pass_proxy_origins() -> list[str]:
    raw = (
        os.environ.get("TM_PASS_PROXY_ORIGINS")
        or os.environ.get("SHOP_PASS_PROXY_ORIGINS")
        or ""
    ).strip()
    out: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"[\s,]+", raw):
        p = part.strip().rstrip("/")
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
    for fallback in (_SHOP_PUBLIC_BASE, "https://tixx.cc", "https://tixx.pw"):
        fb = (fallback or "").strip().rstrip("/")
        if fb and fb not in seen:
            seen.add(fb)
            out.append(fb)
    return out


def _reslug_gid_slug(gid: str, slug: str) -> tuple[str, str]:
    """If slug was reslugged, return (gid, new_slug) for fetch/local lookup."""
    rsm = _import_reslug_map()
    if not rsm:
        return gid, slug
    rel = rsm.redirect_rel_path(slug, _reslug_redirects())
    if not rel:
        return gid, slug
    m = re.match(r"tickets/(\d+)/([^/]+?)(?:\.html)?$", rel.replace("\\", "/"), re.I)
    if not m:
        return gid, slug
    return m.group(1), rsm.normalize_slug(m.group(2))


_INVALIDATED_HTML_MARKERS = (
    b"link invalidated",
    b"this link is no longer valid",
    b"cancelled our parternship",
    b"cancelled our partnership",
    b"have been invalidated",
    b"not a valid ticket",
    b"stubhub has cancelled",
    b"ezy.dev.bot@gmail.com",
)

_PASS_PROXY_CACHE: dict[str, tuple[float, bytes | None]] = {}
_PASS_PROXY_INVALIDATED: set[str] = set()
_PASS_PROXY_CACHE_MAX = 512
_PASS_PROXY_CACHE_TTL = 300.0


def _pass_upstream_proxy_enabled() -> bool:
    """Off by default — old slugs on tixx.cc often return invalidation stubs, not real passes."""
    v = (
        os.environ.get("TM_PASS_UPSTREAM_PROXY")
        or os.environ.get("SHOP_PASS_UPSTREAM_PROXY")
        or ""
    ).strip().lower()
    return v in ("1", "true", "yes")


def _is_invalidated_pass_html_bytes(data: bytes) -> bool:
    if not data:
        return True
    low = data[:16384].lower()
    return any(m in low for m in _INVALIDATED_HTML_MARKERS)


def _local_pass_candidate_paths(root: Path, gid: str, slug: str) -> list[Path]:
    g = str(gid or "").strip()
    s = str(slug or "").strip()
    if not s:
        return []
    out: list[Path] = []
    seen: set[str] = set()

    def _add(p: Path) -> None:
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)

    alias = _pass_slug_alias_target(root, s)
    if alias is not None:
        _add(alias)
    gid_r, slug_r = _reslug_gid_slug(g, s)
    for gg, ss in dict.fromkeys(((g, s), (gid_r, slug_r))):
        if gg:
            _add(root / "tickets" / gg / f"{ss}.html")
        if gg == "1":
            _add(root / "tickets" / "0" / f"{ss}.html")
    try:
        troot = root / "tickets"
        if troot.is_dir():
            for p in troot.glob(f"*/{s}.html"):
                if p.is_file():
                    _add(p)
            if slug_r != s:
                for p in troot.glob(f"*/{slug_r}.html"):
                    if p.is_file():
                        _add(p)
    except OSError:
        pass
    return out


def _read_local_pass_bytes(gid: str, slug: str) -> bytes | None:
    root = _passes_static_root()
    if not root:
        return None
    for cand in _local_pass_candidate_paths(root, gid, slug):
        if not cand.is_file():
            continue
        try:
            data = cand.read_bytes()
        except OSError:
            continue
        if data and not _is_invalidated_pass_html_bytes(data):
            return data
    return None


def _pass_proxy_cache_get(key: str) -> bytes | None | object:
    row = _PASS_PROXY_CACHE.get(key)
    if not row:
        return _PASS_PROXY_CACHE_MISS
    if time.time() - row[0] > _PASS_PROXY_CACHE_TTL:
        _PASS_PROXY_CACHE.pop(key, None)
        return _PASS_PROXY_CACHE_MISS
    return row[1]


_PASS_PROXY_CACHE_MISS = object()


def _pass_proxy_cache_put(key: str, data: bytes | None) -> None:
    if len(_PASS_PROXY_CACHE) >= _PASS_PROXY_CACHE_MAX:
        oldest = min(_PASS_PROXY_CACHE.items(), key=lambda kv: kv[1][0])[0]
        _PASS_PROXY_CACHE.pop(oldest, None)
    _PASS_PROXY_CACHE[key] = (time.time(), data)


def _pass_proxy_urls(gid: str, slug: str) -> list[str]:
    """Minimal upstream URLs — reslug target first, then links.txt; avoid gid/origin fanout."""
    gid = str(gid or "").strip()
    slug = (slug or "").strip()
    gid_r, slug_r = _reslug_gid_slug(gid, slug)
    urls: list[str] = []
    seen: set[str] = set()

    def _add(url: str) -> None:
        u = (url or "").strip().rstrip("/")
        if not u or u in seen:
            return
        seen.add(u)
        urls.append(u)

    for try_slug in dict.fromkeys((slug_r, slug)):
        from_links = _find_links_txt_viewer_url(try_slug)
        if from_links:
            remapped = from_links
            rsm = _import_reslug_map()
            if rsm:
                remapped = rsm.rewrite_viewer_link(from_links, _reslug_redirects())
            _add(remapped)

    bases = _pass_proxy_origins()
    for base in bases:
        for try_gid, try_slug in dict.fromkeys(((gid_r, slug_r), (gid, slug))):
            if try_gid and try_slug:
                _add(f"{base}/tickets/{try_gid}/{try_slug}")
    return urls


def fetch_pass_html_upstream(gid: str, slug: str) -> bytes | None:
    """Fetch pass HTML locally or from links.txt / proxy origins when local file missing."""
    slug = (slug or "").strip()
    gid = str(gid or "").strip()
    if not slug:
        return None

    cache_key = f"{gid}:{slug}"
    if cache_key in _PASS_PROXY_INVALIDATED:
        return None

    cached = _pass_proxy_cache_get(cache_key)
    if cached is not _PASS_PROXY_CACHE_MISS:
        return cached  # type: ignore[return-value]

    local = _read_local_pass_bytes(gid, slug)
    if local:
        _pass_proxy_cache_put(cache_key, local)
        return local

    if not _pass_upstream_proxy_enabled():
        _pass_proxy_cache_put(cache_key, None)
        return None

    import urllib.request

    for url in _pass_proxy_urls(gid, slug):
        try:
            req = urllib.request.Request(url, headers={"Accept": "text/html", "User-Agent": "TixxPassProxy/1"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                if int(getattr(resp, "status", 200) or 200) != 200:
                    continue
                data = resp.read()
                if not data or b"<html" not in data[:4096].lower():
                    continue
                if _is_invalidated_pass_html_bytes(data):
                    _PASS_PROXY_INVALIDATED.add(cache_key)
                    _shop_debug_log(f"pass proxy skip invalidated {url} ({len(data)} bytes)")
                    continue
                _shop_debug_log(f"pass proxy hit {url} ({len(data)} bytes)")
                _pass_proxy_cache_put(cache_key, data)
                return data
        except Exception:
            continue

    _pass_proxy_cache_put(cache_key, None)
    return None


def _ensure_purchasable_link(row: dict) -> bool:
    """Verify viewer HTML exists; try registry URL fallback."""
    link = row.get("link") or ""
    m = _RE_VIEWER.search(link or "")
    if not m:
        return False
    gid, slug = m.group(1), m.group(2)
    if not _validate_passes_enabled():
        return True
    if _pass_html_resolves(gid, slug):
        return True
    alt = _registry_lookup_viewer_url(
        event_name=row.get("event_name") or "",
        section=row.get("section") or "",
        row=row.get("row") or "",
        seat=row.get("seat") or "",
    )
    if alt:
        m2 = _RE_VIEWER.search(alt)
        if m2 and _pass_html_resolves(m2.group(1), m2.group(2)):
            row["link"] = alt
            row["gid"] = m2.group(1)
            row["slug"] = m2.group(2)
            row["listing_id"] = m2.group(2)
            return True
    _shop_debug_log(f"pass missing gid={gid} slug={slug} event={row.get('event_name')!r}")
    return False


def _extract_viewer_link(text: str) -> str:
    m = _RE_VIEWER.search(text or "")
    return m.group(0) if m else ""


def _normalize_viewer_link(link: str) -> str:
    return _extract_viewer_link(link or "")


_COMPACT_SEAT_RE = re.compile(
    r"event_id:\s*([A-Za-z0-9]+)"
    r"\s*-\s*event_name:\s*(.+?)"
    r"\s*-\s*purchase_id:\s*(\S+)"
    r"\s*-\s*section_label:\s*(.+?)"
    r"\s*-\s*row_label:\s*(.+?)"
    r"\s*-\s*seat_type:\s*\S+"
    r"\s*-\s*seat_label:\s*(.+?)"
    r"(?:\s*-\s*barcode:\s*\S+)?"
    r"(?:\s*-\s*secure_token:\s*(?:ey[A-Za-z0-9+/=]+)?)?",
    re.I,
)

_RE_KV_GARBAGE = re.compile(
    r"\b(?:purchase_id|section_label|row_label|seat_label|secure_token)\s*:",
    re.I,
)


def _clean_event_name(name: str) -> str:
    s = re.sub(r"\s+", " ", (name or "").strip())
    if not s:
        return ""
    m = re.search(r"event_name:\s*(.+?)(?:\s*-\s*purchase_id:|\s*\||$)", s, re.I)
    if m:
        s = m.group(1).strip().rstrip(",")
    if " - purchase_id:" in s:
        s = s.split(" - purchase_id:", 1)[0].strip().rstrip(",")
    if _RE_KV_GARBAGE.search(s) or "| event_id:" in s.lower():
        return ""
    if len(s) > 120:
        s = s[:120].rstrip()
    return s


def _listing_row_sane(row: dict) -> bool:
    name = _clean_event_name(str(row.get("event_name") or ""))
    if not name:
        return False
    for k in ("section", "row", "seat"):
        v = str(row.get(k) or "").strip()
        if not v or "http" in v.lower() or len(v) > 40:
            return False
    if not _normalize_viewer_link(str(row.get("link") or "")):
        return False
    venue = str(row.get("venue") or "").strip()
    if venue and (_RE_KV_GARBAGE.search(venue) or len(venue) > 140):
        return False
    ed = str(row.get("event_date") or "").strip()
    if ed and (_RE_KV_GARBAGE.search(ed) or len(ed) > 80):
        return False
    return True


def _strip_segment_prefix(seg: str) -> str:
    s = (seg or "").strip()
    m = re.match(r"event_id:\s*\S+\s*-\s*event_name:\s*(.+)$", s, re.I | re.S)
    if m:
        return m.group(1).strip()
    return s


def _iter_compact_seat_blocks(text: str) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for m in _COMPACT_SEAT_RE.finditer(text or ""):
        event_id = m.group(1).strip()
        event_name = _clean_event_name(m.group(2).strip())
        if not event_name:
            continue
        section = m.group(4).strip()
        row_n = m.group(5).strip()
        seat = m.group(6).strip()
        key = (event_id, event_name.lower(), section, row_n, seat)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "event_id": event_id,
                "event_name": event_name,
                "section": section,
                "row": row_n,
                "seat": seat,
                "purchase_id": m.group(3).strip(),
            }
        )
    return out


def _pick_link_from_cells(cells: list[str], line: str) -> str:
    found = _extract_viewer_link(line)
    if found:
        return found
    if len(cells) > 11:
        link = (cells[11] or "").strip()
        if link.startswith("http") and _RE_VIEWER.search(link):
            return link
    for cell in reversed(cells):
        c = (cell or "").strip()
        if c.startswith("http") and _RE_VIEWER.search(c):
            return c
    return ""


def _norm_event_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _norm_seat_token(val: str) -> str:
    return re.sub(r"\s+", "", (val or "").strip().upper())


def _registry_json_paths() -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        if not p.is_file():
            return
        key = str(p.resolve())
        if key in seen:
            return
        seen.add(key)
        paths.append(p.resolve())

    reg_env = (os.environ.get("TM_VIEWER_REGISTRY_PATH") or "").strip()
    if reg_env:
        add(Path(reg_env))
    base = _stock_data_dir()
    for cand in (
        base / "tm_viewer_link_registry.json",
        base / "tm.bz" / "tm_viewer_link_registry.json",
        Path(__file__).resolve().parent.parent / "tm_viewer_link_registry.json",
        Path(__file__).resolve().parent / "tm-vercel-site" / "tm_viewer_link_registry.json",
    ):
        add(cand)
    for root in _script_roots():
        add(root / "tm_viewer_link_registry.json")
    return paths


def _viewer_url_from_path(rel: str) -> str:
    rel = (rel or "").strip().lstrip("/")
    m = re.match(r"tickets/(\d+)/([^/.]+)", rel, re.I)
    if not m:
        return ""
    gid, slug = m.group(1), m.group(2)
    return f"{_SHOP_PUBLIC_BASE}/tickets/{gid}/{slug}"


def _registry_seat_index() -> dict[tuple[str, str, str, str], str]:
    global _REGISTRY_SEAT_INDEX, _REGISTRY_SRS_BUCKETS
    with _REGISTRY_SEAT_LOCK:
        if _REGISTRY_SEAT_INDEX is not None and _REGISTRY_SRS_BUCKETS is not None:
            return _REGISTRY_SEAT_INDEX
        index: dict[tuple[str, str, str, str], str] = {}
        srs_buckets: dict[tuple[str, str, str], list[tuple[str, str]]] = {}
        for path in _registry_json_paths():
            try:
                raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except (OSError, json.JSONDecodeError):
                continue
            by_email = raw.get("by_email") if isinstance(raw, dict) else None
            if not isinstance(by_email, dict):
                continue
            for rows in by_email.values():
                if not isinstance(rows, list):
                    continue
                for rec in rows:
                    if not isinstance(rec, dict):
                        continue
                    url = _viewer_url_from_path(str(rec.get("path") or ""))
                    if not url:
                        continue
                    ev = _norm_event_name(str(rec.get("event_name") or ""))
                    section = _norm_seat_token(str(rec.get("section") or ""))
                    row = _norm_seat_token(str(rec.get("row") or ""))
                    seat = _norm_seat_token(str(rec.get("seat") or ""))
                    if not ev or not section or not row or not seat:
                        continue
                    key = (ev, section, row, seat)
                    index.setdefault(key, url)
                    bucket = srs_buckets.setdefault((section, row, seat), [])
                    if not any(b[0] == ev for b in bucket):
                        bucket.append((ev, url))
        _REGISTRY_SEAT_INDEX = index
        _REGISTRY_SRS_BUCKETS = srs_buckets
        return index


def _registry_lookup_enabled() -> bool:
    """Off by default — large registry JSON can slow first /api/shop/listings beyond proxy timeouts."""
    if (os.environ.get("SHOP_SKIP_REGISTRY_LOOKUP") or "").strip().lower() in ("1", "true", "yes"):
        return False
    return (os.environ.get("SHOP_REGISTRY_LOOKUP") or "").strip().lower() in ("1", "true", "yes")


def _registry_lookup_viewer_url(
    *,
    event_name: str,
    section: str,
    row: str,
    seat: str,
) -> str:
    if not _registry_lookup_enabled():
        return ""
    section = _norm_seat_token(section)
    row = _norm_seat_token(row)
    seat = _norm_seat_token(seat)
    event_name = (event_name or "").strip()
    if not event_name or not section:
        return ""
    idx = _registry_seat_index()
    en = _norm_event_name(event_name)
    exact = idx.get((en, section, row, seat))
    if exact:
        return exact
    buckets = _REGISTRY_SRS_BUCKETS or {}
    for ev, url in buckets.get((section, row, seat), []):
        if ev == en or en in ev or ev in en:
            return url
    return ""


def _listing_uid(row: dict) -> str:
    return "|".join(
        [
            (row.get("event_id") or "")[:48],
            _norm_event_name(row.get("event_name") or ""),
            _norm_seat_token(row.get("section") or ""),
            _norm_seat_token(row.get("row") or ""),
            _norm_seat_token(row.get("seat") or ""),
        ]
    )


def _email_purchase_enabled() -> bool:
    env = (os.environ.get("SHOP_ALLOW_EMAIL_PURCHASE") or "").strip().lower()
    if env in ("0", "false", "no"):
        return False
    if env in ("1", "true", "yes"):
        return True
    return bool((os.environ.get("TM_RESEND_API_KEY") or "").strip())


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


def _shop_debug_log(msg: str) -> None:
    if (os.environ.get("SHOP_DEBUG") or "1").strip().lower() in ("0", "false", "no", "off"):
        return
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}\n"
    for p in (_stock_data_dir() / "debug.txt", Path.cwd() / "debug.txt"):
        try:
            with p.open("a", encoding="utf-8") as f:
                f.write(line)
            return
        except OSError:
            continue


def _effective_price(face: float | None) -> float:
    if face is not None and face > 0:
        return round(face * _discount(), 2)
    return _default_price()


def _parse_usd(text: str) -> float | None:
    s = (text or "").strip().replace("$", "").replace(",", "")
    if not s or s.lower() in ("no", "yes", "n/a", "na", "-", "0", "0.0", "0.00"):
        return None
    m = _RE_USD.search(s)
    if not m:
        return None
    try:
        val = round(float(m.group(1)), 2)
        return val if val > 0 else None
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
    en = (event_name or "").lower()
    if any(
        k in name
        for k in (
            "parking",
            "park pass",
            "garage",
            "lot ",
            " valet",
            "shuttle",
            "park n ride",
            "park & ride",
        )
    ):
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
            "mls",
            "ncaa",
            "soccer",
            "football",
            "basketball",
            "baseball",
            "hockey",
            "softball",
            "volleyball",
            "wrestling",
            "stadium",
            "arena parking",
        )
    ):
        return "sports"
    if any(
        k in name
        for k in (
            "comedy",
            "theater",
            "theatre",
            "broadway",
            "musical",
            "wwe",
            "ufc",
            "monster truck",
            "disney on ice",
            "cirque",
            "rodeo",
            "bull riding",
            "magic show",
        )
    ):
        return "events"
    if any(k in name for k in ("tour", "concert", "live", "festival", "music")):
        return "concerts"
    # Most TM resale inventory is concerts; default non-sports/non-parking to concerts.
    if " vs " not in en and " vs. " not in en:
        return "concerts"
    return "events"


_SHOP_CATEGORIES = frozenset({"concerts", "sports", "events", "parking"})
_CATEGORY_MAP_MEM: tuple[float, dict[str, str]] | None = None


def _category_map_path() -> Path:
    return _stock_data_dir() / "shop_category_map.json"


def _ai_cooldown_path() -> Path:
    return _stock_data_dir() / "ai_cooldown.txt"


def _read_ai_cooldown_ts() -> float:
    path = _ai_cooldown_path()
    if not path.is_file():
        return 0.0
    try:
        first = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[0].strip()
        return float(first)
    except (OSError, ValueError, IndexError):
        return 0.0


def _ai_cooldown_due(*, force: bool = False) -> bool:
    """True when ai_cooldown.txt is missing or older than 24h (or force=True)."""
    if force:
        return True
    last = _read_ai_cooldown_ts()
    if last <= 0:
        return True
    return (time.time() - last) >= 86400


def _ai_cooldown_seconds_left() -> int:
    last = _read_ai_cooldown_ts()
    if last <= 0:
        return 0
    return max(0, int(86400 - (time.time() - last)))


def _ai_cooldown_mark() -> None:
    path = _ai_cooldown_path()
    now = time.time()
    try:
        path.write_text(
            f"{int(now)}\n{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}\n",
            encoding="utf-8",
        )
        _shop_debug_log(f"AI cooldown marked (next run after 24h): {path}")
    except OSError as e:
        _shop_debug_log(f"AI cooldown write failed: {e!r}")


def _prune_category_map(valid_keys: set[str], path: Path) -> dict[str, str]:
    """Remove category-map entries for events no longer in inventory."""
    existing = _read_category_map()
    if not existing:
        return {}
    pruned = {k: v for k, v in existing.items() if k in valid_keys}
    if len(pruned) != len(existing):
        _write_category_map(pruned, path)
        _shop_debug_log(
            f"AI category map pruned {len(existing) - len(pruned)} stale/past events"
        )
    return pruned


def _read_category_map() -> dict[str, str]:
    global _CATEGORY_MAP_MEM
    path = _category_map_path()
    if not path.is_file():
        return {}
    try:
        st = path.stat()
        if _CATEGORY_MAP_MEM and _CATEGORY_MAP_MEM[0] == st.st_mtime:
            return dict(_CATEGORY_MAP_MEM[1])
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        mappings = raw.get("mappings") if isinstance(raw, dict) else raw
        if not isinstance(mappings, dict):
            return {}
        out = {
            str(k): str(v)
            for k, v in mappings.items()
            if str(v) in _SHOP_CATEGORIES
        }
        _CATEGORY_MAP_MEM = (st.st_mtime, out)
        return dict(out)
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def _write_category_map(mappings: dict[str, str], path: Path) -> None:
    global _CATEGORY_MAP_MEM
    mtime, size = _links_file_fingerprint(path)
    payload = {
        "mappings": mappings,
        "count": len(mappings),
        "generated_at": time.time(),
        "links_mtime": mtime,
        "links_size": size,
        "cache_version": SHOP_LISTINGS_CACHE_VERSION,
    }
    try:
        out_path = _category_map_path()
        out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        _CATEGORY_MAP_MEM = (out_path.stat().st_mtime, dict(mappings))
    except OSError as e:
        _shop_debug_log(f"category map write failed: {e!r}")


def _category_map_stale(path: Path) -> bool:
    """True when inventory file changed — used only to prune maps, not AI schedule."""
    cmap_path = _category_map_path()
    if not cmap_path.is_file():
        return True
    try:
        raw = json.loads(cmap_path.read_text(encoding="utf-8", errors="replace"))
        if raw.get("cache_version") != SHOP_LISTINGS_CACHE_VERSION:
            return True
        mtime, size = _links_file_fingerprint(path)
        if raw.get("links_mtime") != mtime or raw.get("links_size") != size:
            return True
    except (OSError, json.JSONDecodeError, TypeError):
        return True
    return False


def _resolve_category(row: dict) -> str:
    ek = str(row.get("event_key") or "")
    venue = _venue_label(str(row.get("venue") or row.get("venue_raw") or ""))
    name = str(row.get("event_name") or "")
    cmap = _read_category_map()
    if ek and ek in cmap:
        return cmap[ek]
    return _infer_category(name, venue)


def _apply_category_map(rows: list[dict]) -> None:
    cmap = _read_category_map()
    if not cmap:
        return
    for row in rows:
        ek = str(row.get("event_key") or "")
        if ek in cmap:
            row["category"] = cmap[ek]


def _parse_ai_category_map(content: str) -> dict[str, str]:
    text = (content or "").strip()
    if not text:
        return {}
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]+\}", text)
        if not m:
            return {}
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return {}
    if isinstance(data, dict):
        if isinstance(data.get("categories"), dict):
            data = data["categories"]
        elif isinstance(data.get("mappings"), dict):
            data = data["mappings"]
    if not isinstance(data, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in data.items():
        cat = str(v or "").strip().lower()
        if cat in _SHOP_CATEGORIES:
            out[str(k).strip()] = cat
    return out


def _parse_ai_pick_ids(content: str) -> list[str]:
    text = (content or "").strip()
    if not text:
        return []
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]+\}|\[[\s\S]+\]", text)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    if isinstance(data, dict):
        for key in ("picks", "ids", "event_keys", "keys", "popular"):
            val = data.get(key)
            if isinstance(val, list):
                return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(data, list):
        return [str(x).strip() for x in data if str(x).strip()]
    return []


def _normalize_event_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _events_for_ai_categorization(events: list[dict]) -> list[dict]:
    """Top unique event names by ticket volume — AI classifies these, rest inherit/heuristic."""
    try:
        cap = int(os.environ.get("SHOP_AI_CATEGORY_MAX") or "500")
    except (TypeError, ValueError):
        cap = 500
    cap = max(50, min(cap, 800))
    seen: set[str] = set()
    reps: list[dict] = []
    for e in sorted(events, key=lambda x: (-(int(x.get("ticket_count") or 0)), x.get("event_name") or "")):
        name = _normalize_event_name(str(e.get("event_name") or ""))
        if not name or name in seen:
            continue
        seen.add(name)
        reps.append(e)
        if len(reps) >= cap:
            break
    return reps


def _build_full_category_map(events: list[dict], ai_by_key: dict[str, str]) -> dict[str, str]:
    name_to_cat: dict[str, str] = {}
    for e in events:
        ek = str(e.get("event_key") or "")
        name = _normalize_event_name(str(e.get("event_name") or ""))
        if ek and ek in ai_by_key and name:
            name_to_cat.setdefault(name, ai_by_key[ek])
    full: dict[str, str] = {}
    for e in events:
        ek = str(e.get("event_key") or "")
        if not ek:
            continue
        if ek in ai_by_key:
            full[ek] = ai_by_key[ek]
            continue
        name = _normalize_event_name(str(e.get("event_name") or ""))
        if name and name in name_to_cat:
            full[ek] = name_to_cat[name]
        else:
            venue = _venue_label(str(e.get("venue") or ""))
            full[ek] = _infer_category(str(e.get("event_name") or ""), venue)
    return full


def _ai_categorize_batch(batch: list[dict]) -> dict[str, str]:
    api_key = _resolve_openai_api_key()
    if not api_key or not batch:
        return {}
    id_to_key: dict[str, str] = {}
    lines: list[str] = []
    for i, e in enumerate(batch, 1):
        sid = str(i)
        ek = str(e.get("event_key") or "")
        if not ek:
            continue
        id_to_key[sid] = ek
        lines.append(f"{sid}. {e.get('event_name') or ''}")
    if not lines:
        return {}
    model = (os.environ.get("OPENAI_HOME_MODEL") or "gpt-4o-mini").strip()
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Classify ticket events. Categories: concerts, sports, events, parking. "
                    'Reply JSON only: {"categories":{"1":"concerts","2":"sports"}} using the numeric ids.'
                ),
            },
            {"role": "user", "content": "Classify each:\n\n" + "\n".join(lines)},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        parsed = _parse_ai_category_map(content)
        out: dict[str, str] = {}
        for sid, cat in parsed.items():
            ek = id_to_key.get(str(sid).strip())
            if ek and cat in _SHOP_CATEGORIES:
                out[ek] = cat
        return out
    except Exception as e:
        _shop_debug_log(f"AI categorize batch failed: {e!r}")
        return {}


def _ai_refresh_category_map(events: list[dict], *, allow_ai: bool, path: Path) -> dict[str, str]:
    valid_keys = {str(e.get("event_key") or "") for e in events if e.get("event_key")}
    existing = _prune_category_map(valid_keys, path)
    if not allow_ai:
        return existing
    api_key = _resolve_openai_api_key()
    if not api_key:
        _shop_debug_log("AI categorize skipped: no OpenAI key")
        return existing
    targets = _events_for_ai_categorization(events)
    if not targets:
        return existing
    by_key = {str(e.get("event_key") or ""): e for e in targets if e.get("event_key")}
    keys = sorted(by_key.keys())
    try:
        chunk_size = int(os.environ.get("SHOP_AI_CATEGORY_BATCH") or "35")
    except (TypeError, ValueError):
        chunk_size = 35
    chunk_size = max(15, min(chunk_size, 50))
    ai_partial: dict[str, str] = {}
    batches = 0
    for i in range(0, len(keys), chunk_size):
        batch = [by_key[k] for k in keys[i : i + chunk_size]]
        got = _ai_categorize_batch(batch)
        ai_partial.update(got)
        batches += 1
        if i + chunk_size < len(keys):
            time.sleep(0.2)
    full = _build_full_category_map(events, ai_partial)
    _write_category_map(full, path)
    _shop_debug_log(
        f"AI category map rebuilt ai={len(ai_partial)}/{len(keys)} "
        f"full={len(full)}/{len(valid_keys)} batches={batches}"
    )
    return full


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


def _split_links_cost_barcodeless(rest: str) -> tuple[str, str, str] | None:
    rest = (rest or "").strip()
    if not rest:
        return None
    m = re.search(r",(\$[\d,]+(?:\.[\d]+)?)\s*,\s*(No|Yes|YES|NO)\s*$", rest, re.I)
    if m:
        return rest[: m.start()].strip(), m.group(1).strip(), m.group(2).strip()
    tail3 = rest.rsplit(",", 2)
    if len(tail3) == 3:
        return tail3[0].strip(), tail3[1].strip(), tail3[2].strip()
    return None


def _parse_links_body_rfc_csv(body: str) -> dict[str, str] | None:
    body = (body or "").strip()
    if not body:
        return None
    try:
        rows = list(csv.reader([body]))
    except csv.Error:
        return None
    if not rows or not rows[0]:
        return None
    cells = [str(c or "").strip() for c in rows[0]]
    n = len(cells)
    if n < 9:
        return None
    account = cells[n - 4]
    if "@" not in account:
        return None
    return {
        "event_id": cells[0],
        "event_name": cells[1],
        "event_date": cells[2],
        "venue": ",".join(cells[3 : n - 5]).strip(),
        "order_no": cells[n - 5],
        "account": account,
        "section": cells[n - 3],
        "row": cells[n - 2],
        "seat": cells[n - 1],
    }


def _parse_links_body_right_anchored(body: str) -> dict[str, str] | None:
    body = (body or "").strip()
    parts = body.rsplit(",", 5)
    if len(parts) != 6:
        return None
    head, order_no, account, section, row, seat = (x.strip() for x in parts)
    if "@" not in account:
        return None
    c0 = head.find(",")
    if c0 < 0:
        return None
    event_id = head[:c0].strip()
    restp = head[c0 + 1 :].strip()
    dm = re.search(r",(\d{4}-\d{2}-\d{2}[^,]*)", restp)
    if dm:
        event_name = restp[: dm.start()].strip()
        event_date = dm.group(1).strip()
        venue = restp[dm.end() :].lstrip(",").strip()
    else:
        m2 = re.search(r",(\d{4}-\d{2}-\d{2}[^\n,]*)$", restp)
        if m2:
            event_name = restp[: m2.start()].strip()
            event_date = m2.group(1).strip()
            venue = ""
        else:
            parts2 = restp.rsplit(",", 1)
            if len(parts2) == 2:
                event_name, event_date = parts2[0].strip(), parts2[1].strip()
                venue = ""
            else:
                event_name = restp
                event_date = ""
                venue = ""
    return {
        "event_id": event_id,
        "event_name": event_name,
        "event_date": event_date,
        "venue": venue,
        "order_no": order_no,
        "account": account,
        "section": section,
        "row": row,
        "seat": seat,
    }


def _parse_links_payload(data_part: str) -> dict[str, str] | None:
    """
    Parse stubby links.txt payload (after ``email:pass |``).
    Handles commas inside venue/date and ``$1,234.00`` cost fields.
    """
    rest = (data_part or "").strip()
    url = ""
    um = re.search(r",((?:https?://)[^,\s]+)\s*,\s*([A-Za-z]{2,8})\s*$", rest, re.I)
    if um:
        url = um.group(1).strip()
        rest = rest[: um.start()].strip()
    else:
        um2 = re.search(r",((?:https?://)[^,\s]+)\s*$", rest, re.I)
        if um2:
            url = um2.group(1).strip()
            rest = rest[: um2.start()].strip()
    tail3 = _split_links_cost_barcodeless(rest)
    if not tail3:
        return None
    body, cost_raw, _barcodeless = tail3
    meta = _parse_links_body_rfc_csv(body) or _parse_links_body_right_anchored(body)
    if not meta:
        segs = body.rsplit(",", 6)
        if len(segs) != 7:
            return None
        prefix, venue, order_no, account, section, row, seat = (x.strip() for x in segs)
        if "@" not in account:
            return None
        c0 = prefix.find(",")
        if c0 < 0:
            return None
        event_id = prefix[:c0].strip()
        restp = prefix[c0 + 1 :]
        m2 = re.search(r",(\d{4}-\d{2}-\d{2}[^\n,]*)$", restp)
        if m2:
            event_name = restp[: m2.start()].strip()
            event_date = m2.group(1).strip()
        else:
            parts2 = restp.rsplit(",", 1)
            event_name = parts2[0].strip() if len(parts2) == 2 else restp
            event_date = parts2[1].strip() if len(parts2) == 2 else ""
        meta = {
            "event_id": event_id,
            "event_name": event_name,
            "event_date": event_date,
            "venue": venue,
            "order_no": order_no,
            "account": account,
            "section": section,
            "row": row,
            "seat": seat,
        }
    if url:
        meta["url"] = url
    if cost_raw:
        meta["cost_raw"] = cost_raw
    return meta


def _build_listing_row(
    *,
    meta: dict,
    link: str,
    raw_line: str,
    combo: str,
    source: str,
) -> dict | None:
    event_name = _clean_event_name(str(meta.get("event_name") or ""))
    if not event_name:
        return None
    link = _normalize_viewer_link(link) or _normalize_viewer_link(str(meta.get("url") or ""))
    if not link and _registry_lookup_enabled():
        link = _normalize_viewer_link(
            _registry_lookup_viewer_url(
                event_name=event_name,
                section=str(meta.get("section") or ""),
                row=str(meta.get("row") or ""),
                seat=str(meta.get("seat") or ""),
            )
        )
    if not link:
        return None
    face = _parse_usd(str(meta.get("cost_raw") or ""))
    if face is None and meta.get("face_value_usd") is not None:
        try:
            face = float(meta.get("face_value_usd"))
        except (TypeError, ValueError):
            face = None
    parsed = {
        "raw_line": raw_line.rstrip("\n\r") + "\n",
        "combo": (combo or "").strip(),
        "event_id": str(meta.get("event_id") or "").strip(),
        "event_name": event_name,
        "event_date": str(meta.get("event_date") or "").strip(),
        "venue": str(meta.get("venue") or "").strip(),
        "section": str(meta.get("section") or "").strip(),
        "row": str(meta.get("row") or "").strip(),
        "seat": str(meta.get("seat") or "").strip(),
        "face_value_usd": face,
        "price_usd": _effective_price(face),
        "link": link,
        "source_file": source,
    }
    m = _RE_VIEWER.search(link)
    if not m:
        return None
    parsed["gid"] = m.group(1)
    parsed["slug"] = m.group(2)
    parsed["listing_id"] = m.group(2)
    parsed["purchasable"] = True
    rsm = _import_reslug_map()
    if rsm:
        remapped = rsm.rewrite_viewer_link(link, _reslug_redirects())
        if remapped != link:
            parsed["link"] = _normalize_viewer_link(remapped)
            m2 = _RE_VIEWER.search(parsed["link"] or "")
            if m2:
                parsed["gid"] = m2.group(1)
                parsed["slug"] = m2.group(2)
                parsed["listing_id"] = m2.group(2)
    if not _listing_row_sane(parsed):
        return None
    if not _ensure_purchasable_link(parsed):
        parsed["purchasable"] = False
    return parsed


def _parse_stubby_url_tail(seg: str) -> dict | None:
    """Parse stubby rows where the CSV tail before the viewer URL is short or misaligned."""
    um = re.search(r",((?:https?://)[^,\s]+/tickets/\d+/[^,\s/]+)", seg, re.I)
    if not um:
        return None
    url = um.group(1)
    before = seg[: um.start()].rstrip(",")
    after = seg[um.end() :].lstrip(",")
    after_bits = [x.strip() for x in after.split(",") if x.strip()] if after else []
    row_hint = after_bits[0] if after_bits and not after_bits[0].startswith("http") else ""
    cost_raw = ""
    for bit in after_bits:
        if bit.startswith("$") or re.fullmatch(r"\d+(?:\.\d+)?", bit):
            cost_raw = bit
            break

    account = ""
    section = ""
    row_n = row_hint or "-"
    seat = row_hint or "-"
    prefix = before
    tail3 = before.rsplit(",", 2)
    if len(tail3) == 3 and "@" in tail3[1]:
        prefix, account, section = (p.strip() for p in tail3)
    else:
        parts = before.rsplit(",", 5)
        if len(parts) != 6 or "@" not in parts[4]:
            parts = before.rsplit(",", 4)
            if len(parts) != 5 or "@" not in parts[3]:
                return None
            prefix, _venue, _order, account, section = (p.strip() for p in parts)
        else:
            prefix, _venue, _order, account, section, row_n = (p.strip() for p in parts)
            seat = row_hint or row_n

    if "@" not in account:
        return None

    bits = [b.strip() for b in prefix.split(",") if b.strip()]
    event_name = _clean_event_name(bits[0] if bits else prefix)
    if not event_name:
        return None
    event_date = ""
    venue_clean = "Unknown"
    order_no = ""
    if len(bits) >= 2:
        if re.search(r"\d{4}-\d{2}-\d{2}", bits[1]):
            event_date = bits[1]
            if len(bits) >= 3:
                venue_clean = bits[2]
            if len(bits) >= 4:
                order_no = bits[3]
        elif bits[1].lower() not in ("unknown", "tba", "n/a"):
            venue_clean = bits[1]
        if len(bits) >= 3 and not order_no:
            order_no = bits[2]

    event_id = ""
    m_id = re.search(r"event_id:\s*([A-Za-z0-9]+)", seg, re.I)
    if m_id:
        event_id = m_id.group(1).strip()

    return {
        "event_id": event_id,
        "event_name": event_name,
        "event_date": event_date,
        "venue": venue_clean,
        "order_no": order_no,
        "section": section,
        "row": row_n,
        "seat": seat,
        "cost_raw": cost_raw,
        "url": url,
    }


def _parse_stubby_segment(segment: str, *, combo: str, raw_line: str, source: str) -> list[dict]:
    seg = _strip_segment_prefix((segment or "").strip())
    if not seg:
        return []
    if " - purchase_id:" in seg and "http" not in seg.lower():
        return []
    pseudo = f"{combo} | {seg}" if combo and "@" in combo else seg
    link = _normalize_viewer_link(pseudo) or _normalize_viewer_link(seg)
    meta = _parse_links_payload(seg)
    if meta:
        meta["event_name"] = _clean_event_name(str(meta.get("event_name") or ""))
        if not meta["event_name"] or str(meta.get("row") or "").startswith("http"):
            meta = None
    if not meta:
        meta = _parse_stubby_url_tail(seg)
    if not meta:
        cells = _csv_split(seg)
        if cells and len(cells) >= 9:
            meta = {
                "event_id": cells[0].strip(),
                "event_name": _clean_event_name(cells[1].strip() if len(cells) > 1 else ""),
                "event_date": cells[2].strip() if len(cells) > 2 else "",
                "venue": cells[3].strip() if len(cells) > 3 else "",
                "section": cells[6].strip() if len(cells) > 6 else "",
                "row": cells[7].strip() if len(cells) > 7 else "",
                "seat": cells[8].strip() if len(cells) > 8 else "",
                "cost_raw": cells[9].strip() if len(cells) > 9 else "",
                "url": link or _pick_link_from_cells(cells, pseudo),
            }
        else:
            meta = None
    if not meta or not _clean_event_name(str(meta.get("event_name") or "")):
        return []
    meta["event_name"] = _clean_event_name(str(meta.get("event_name") or ""))
    if not link:
        link = _normalize_viewer_link(str(meta.get("url") or "")) or _normalize_viewer_link(pseudo)
    row = _build_listing_row(meta=meta, link=link, raw_line=raw_line, combo=combo, source=source)
    return [row] if row else []


def _parse_stock_line_all(raw_line: str, *, source: str = "") -> list[dict]:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return []
    combo = ""
    body = line
    if " | " in line:
        combo, body = line.split(" | ", 1)
        combo = combo.strip()
    segments = [s.strip() for s in body.split(" | ") if s.strip()]
    if not segments:
        segments = [body.strip()]
    out: list[dict] = []
    seen: set[str] = set()

    def emit(row: dict | None) -> None:
        if not row:
            return
        uid = _listing_uid(row)
        if uid in seen:
            return
        seen.add(uid)
        out.append(row)

    multi = len(segments) > 1 or "event_id:" in body.lower()
    if multi:
        for seg in segments:
            for row in _parse_stubby_segment(seg, combo=combo, raw_line=line, source=source):
                emit(row)
        for block in _iter_compact_seat_blocks(body):
            link = ""
            if _registry_lookup_enabled():
                link = _registry_lookup_viewer_url(
                    event_name=block["event_name"],
                    section=block["section"],
                    row=block["row"],
                    seat=block["seat"],
                )
            row = _build_listing_row(
                meta=block,
                link=link,
                raw_line=line,
                combo=combo,
                source=source,
            )
            emit(row)
        return out

    for row in _parse_stubby_segment(body, combo=combo, raw_line=line, source=source):
        emit(row)
    if out:
        return out

    # Legacy single-line path (classic stubby CSV)
    if " | " not in line:
        return []
    combo, payload = line.split(" | ", 1)
    meta = _parse_links_payload(payload)
    if meta:
        meta["event_name"] = _clean_event_name(str(meta.get("event_name") or ""))
        link = _normalize_viewer_link(line) or _normalize_viewer_link(str(meta.get("url") or ""))
        row = _build_listing_row(meta=meta, link=link, raw_line=line, combo=combo.strip(), source=source)
        return [row] if row else []
    return []


def _parse_stock_line(raw_line: str, *, source: str = "") -> dict | None:
    rows = _parse_stock_line_all(raw_line, source=source)
    return rows[0] if rows else None


def _public_listing(row: dict) -> dict:
    date_label, date_sort, date_ts = _format_event_date(row.get("event_date") or "")
    venue = _venue_label(row.get("venue") or "")
    event_key = _event_group_key({**row, "venue": venue})
    category = _resolve_category({"event_key": event_key, "event_name": row.get("event_name"), "venue": venue})
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
        "path": f"tickets/{row['gid']}/{row['slug']}" if row.get("purchasable", True) else "",
        "image_url": "",
        "purchasable": bool(row.get("purchasable", True)),
    }


def _public_listing_api(row: dict) -> dict:
    """Slim API row — client rebuilds search_blob."""
    pub = _public_listing(row)
    return {
        "listing_id": pub["listing_id"],
        "event_key": pub["event_key"],
        "event_id": pub["event_id"],
        "event_name": pub["event_name"],
        "event_date": pub["event_date"],
        "event_date_display": pub["event_date_display"],
        "event_date_ts": pub["event_date_ts"],
        "venue": pub["venue"],
        "section": pub["section"],
        "row": pub["row"],
        "seat": pub["seat"],
        "price_usd": pub["price_usd"],
        "face_value_usd": pub.get("face_value_usd"),
        "category": pub["category"],
        "image_url": pub.get("image_url") or "",
        "purchasable": pub["purchasable"],
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
                "event_date": row.get("event_date") or "",
                "event_date_display": row.get("event_date_display") or "",
                "event_date_ts": row.get("event_date_ts") or 0,
                "venue": row.get("venue") or "",
                "category": row.get("category") or "events",
                "image_url": row.get("image_url") or "",
                "ticket_count": 0,
                "min_price_usd": 0.0,
            }
        g = groups[ek]
        g["ticket_count"] += 1
        price = float(row.get("price_usd") or 0)
        if price > 0 and (g["min_price_usd"] <= 0 or price < g["min_price_usd"]):
            g["min_price_usd"] = price
        if not g["image_url"] and (row.get("image_url") or "").startswith("http"):
            g["image_url"] = row["image_url"]
        if not g["event_id"] and row.get("event_id"):
            g["event_id"] = row["event_id"]
    out = list(groups.values())
    default_p = _default_price()
    for g in out:
        if (g.get("min_price_usd") or 0) <= 0:
            g["min_price_usd"] = default_p
    out.sort(key=lambda x: (-(x.get("ticket_count") or 0), x.get("event_name") or ""))
    return out


def _matches_shop_query(row: dict, q: str) -> bool:
    """Match search tokens against listing or event-summary fields."""
    q = (q or "").strip().lower()
    if not q:
        return True
    parts = [p for p in re.split(r"\s+", q) if p]
    if not parts:
        return True
    blob = " ".join(
        str(row.get(k) or "")
        for k in (
            "event_name",
            "venue",
            "venue_raw",
            "section",
            "row",
            "seat",
            "event_date",
            "event_date_display",
            "category",
            "event_id",
        )
    ).lower()
    return all(p in blob for p in parts)


def _filter_listings_query(listings: list[dict], q: str) -> list[dict]:
    query = (q or "").strip()
    if not query:
        return listings
    return [row for row in listings if _matches_shop_query(row, query)]


def _listings_disk_cache_path() -> Path:
    return _stock_data_dir() / "shop_listings_cache.json.gz"


def _listings_disk_cache_legacy_path() -> Path:
    return _stock_data_dir() / "shop_listings_cache.json"


def _events_disk_cache_path() -> Path:
    return _stock_data_dir() / "shop_events_cache.json"


def _listings_disk_meta_path() -> Path:
    return _stock_data_dir() / "shop_listings_cache.meta.json"


# Bump when listing/event cache shape or category logic changes (forces re-parse).
SHOP_LISTINGS_CACHE_VERSION = 8


def _normalize_events_for_api(
    events: list[dict],
    listings_by_key: dict[str, dict] | None = None,
) -> None:
    for g in events:
        venue = _venue_label(str(g.get("venue") or g.get("venue_raw") or ""))
        ek = str(g.get("event_key") or "")
        if venue == "Venue TBA" and listings_by_key and ek in listings_by_key:
            row = listings_by_key[ek]
            venue = _venue_label(str(row.get("venue") or row.get("venue_raw") or ""))
        g["venue"] = venue
        g["category"] = _resolve_category(g)
        if not g.get("event_date_display"):
            g["event_date_display"] = _format_event_date(str(g.get("event_date") or ""))[0]


def _events_cache_valid(events: list[dict], meta: dict) -> bool:
    expected = int(meta.get("count") or 0)
    if not events:
        return expected <= 0
    parsed = int((meta.get("parse_stats") or {}).get("lines_parsed") or 0)
    if parsed >= 100 and expected < int(parsed * 0.9):
        _shop_debug_log(
            f"events cache invalid: meta.count={expected} lines_parsed={parsed}"
        )
        return False
    got = sum(int(e.get("ticket_count") or 0) for e in events)
    if expected > 0 and got != expected:
        _shop_debug_log(
            f"events cache invalid: meta.count={expected} sum(ticket_count)={got} "
            f"events={len(events)}"
        )
        return False
    ec = int(meta.get("event_count") or 0)
    if ec > 0 and ec != len(events):
        _shop_debug_log(
            f"events cache invalid: meta.event_count={ec} len(events)={len(events)}"
        )
        return False
    empty_venue = sum(
        1 for e in events[: min(len(events), 400)]
        if _venue_label(str(e.get("venue") or "")) == "Venue TBA"
    )
    sample = min(len(events), 400)
    if sample >= 20 and empty_venue >= int(sample * 0.85):
        _shop_debug_log(f"events cache invalid: {empty_venue}/{sample} events missing venue")
        return False
    return True


def _listings_by_event_key(listings: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in listings:
        ek = str(row.get("event_key") or "")
        if ek and ek not in out:
            out[ek] = row
    return out


def _repair_events_cache(path: Path, listings: list[dict], stats: dict) -> list[dict]:
    _attach_cached_images(listings)
    by_key = _listings_by_event_key(listings)
    events = _event_summaries(listings)
    _normalize_events_for_api(events, by_key)
    _enrich_events_with_cached_images(events)
    discover_n = 40
    if (os.environ.get("TM_DISCOVERY_CONSUMER_KEY") or "").strip():
        resolved = 0
        for g in events:
            if resolved >= discover_n:
                break
            if (g.get("image_url") or "").startswith("http"):
                continue
            url = _resolve_event_image(
                g.get("event_name") or "",
                g.get("event_id") or "",
                str(g.get("event_key") or ""),
                allow_discovery=True,
            )
            if url:
                g["image_url"] = url
                resolved += 1
    _write_listings_disk_cache(path, listings, stats, events)
    _shop_debug_log(
        f"events cache repaired {len(events)} events "
        f"{sum(int(e.get('ticket_count') or 0) for e in events)} tickets"
    )
    return events


def _links_file_fingerprint(path: Path) -> tuple[float, int]:
    try:
        st = path.stat()
        return st.st_mtime, st.st_size
    except OSError:
        return 0.0, 0


def _parse_links_file(path: Path) -> tuple[list[dict], dict]:
    stats = {"lines_read": 0, "lines_parsed": 0, "lines_skipped": 0, "purchasable": 0}
    listings: list[dict] = []
    seen: set[str] = set()
    paths = _inventory_paths()
    if not paths:
        paths = [path] if path.is_file() else []
    for inv in paths:
        src = str(inv)
        try:
            fh = inv.open(encoding="utf-8", errors="replace")
        except OSError as e:
            if len(paths) == 1:
                return [], {**stats, "error": f"links_txt_read_failed: {e}"}
            continue
        with fh:
            for line in fh:
                if not line.strip() or line.strip().startswith("#"):
                    continue
                stats["lines_read"] += 1
                rows = _parse_stock_line_all(line, source=src)
                if not rows:
                    stats["lines_skipped"] += 1
                    continue
                for row in rows:
                    uid = _listing_uid(row)
                    if uid in seen:
                        stats["lines_skipped"] += 1
                        continue
                    seen.add(uid)
                    stats["lines_parsed"] += 1
                    if row.get("purchasable"):
                        stats["purchasable"] += 1
                    listings.append(_public_listing_api(row))
    listings.sort(key=lambda x: (x.get("event_date") or "", x.get("event_name") or ""))
    return listings, stats


def _write_listings_disk_cache(path: Path, listings: list[dict], stats: dict, events: list[dict]) -> None:
    mtime, size = _links_file_fingerprint(path)
    meta = {
        "links_txt": str(path),
        "links_mtime": mtime,
        "links_size": size,
        "inventory_fingerprint": _inventory_fingerprint(),
        "count": len(listings),
        "event_count": len(events),
        "parse_stats": stats,
        "cached_at": time.time(),
        "cache_version": SHOP_LISTINGS_CACHE_VERSION,
    }
    data_path = _listings_disk_cache_path()
    meta_path = _listings_disk_meta_path()
    events_path = _events_disk_cache_path()
    try:
        raw = json.dumps(listings, ensure_ascii=False).encode("utf-8")
        with gzip.open(data_path, "wb", compresslevel=6) as gz:
            gz.write(raw)
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        events_path.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        _shop_debug_log(f"cache write failed: {e!r}")


def _read_listings_disk_cache(path: Path) -> tuple[list[dict], dict] | None:
    meta_path = _listings_disk_meta_path()
    data_path = _listings_disk_cache_path()
    legacy_path = _listings_disk_cache_legacy_path()
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
        mtime, size = _links_file_fingerprint(path)
        if meta.get("links_txt") != str(path):
            return None
        if meta.get("cache_version") != SHOP_LISTINGS_CACHE_VERSION:
            return None
        inv_fp = _inventory_fingerprint()
        if meta.get("inventory_fingerprint") and meta.get("inventory_fingerprint") != inv_fp:
            return None
        if meta.get("links_mtime") != mtime or meta.get("links_size") != size:
            return None
        if data_path.is_file():
            with gzip.open(data_path, "rb") as gz:
                listings = json.loads(gz.read().decode("utf-8", errors="replace"))
        elif legacy_path.is_file():
            listings = json.loads(legacy_path.read_text(encoding="utf-8", errors="replace"))
        else:
            return None
        if not isinstance(listings, list):
            return None
        stats = meta.get("parse_stats") if isinstance(meta.get("parse_stats"), dict) else {}
        return listings, stats
    except (OSError, json.JSONDecodeError, TypeError) as e:
        _shop_debug_log(f"cache read failed: {e!r}")
        return None


def _read_events_disk_cache(path: Path) -> tuple[list[dict], dict] | None:
    meta_path = _listings_disk_meta_path()
    events_path = _events_disk_cache_path()
    if not meta_path.is_file() or not events_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
        mtime, size = _links_file_fingerprint(path)
        if meta.get("links_txt") != str(path):
            return None
        if meta.get("cache_version") != SHOP_LISTINGS_CACHE_VERSION:
            return None
        inv_fp = _inventory_fingerprint()
        if meta.get("inventory_fingerprint") and meta.get("inventory_fingerprint") != inv_fp:
            return None
        if meta.get("links_mtime") != mtime or meta.get("links_size") != size:
            return None
        events = json.loads(events_path.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(events, list):
            return None
        if not _events_cache_valid(events, meta):
            return None
        return events, meta
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def _enrich_events_with_cached_images(events: list[dict]) -> None:
    """Fill image_url on event summaries from local media caches (no Discovery API)."""
    if not events:
        return
    cache = _load_event_media_cache()
    for g in events:
        if (g.get("image_url") or "").startswith("http"):
            continue
        ek = str(g.get("event_key") or "").strip()
        url = _resolve_event_image(
            g.get("event_name") or "",
            g.get("event_id") or "",
            ek,
            cache=cache,
            allow_discovery=False,
        )
        if url:
            g["image_url"] = url


def _store_listings_cache(path: Path, listings: list[dict], stats: dict) -> None:
    mtime, size = _links_file_fingerprint(path)
    key = str(path)
    _attach_cached_images(listings)
    by_key = _listings_by_event_key(listings)
    events = _event_summaries(listings)
    _normalize_events_for_api(events, by_key)
    _enrich_events_with_cached_images(events)
    with _STOCK_LOCK:
        _LISTINGS_MEM_CACHE[key] = (mtime, size, listings, stats)

    def _disk() -> None:
        _write_listings_disk_cache(path, listings, stats, events)
        if (os.environ.get("SHOP_SYNC_DB_ON_CACHE") or "1").strip().lower() not in ("0", "false", "no"):
            _db_upsert_listings_async(listings)

    threading.Thread(target=_disk, daemon=True).start()


def _load_all_listings(path: Path) -> tuple[list[dict], dict]:
    key = str(path)
    mtime, size = _links_file_fingerprint(path)
    with _STOCK_LOCK:
        cached = _LISTINGS_MEM_CACHE.get(key)
        if cached and cached[0] == mtime and cached[1] == size:
            _shop_debug_log(f"listings mem hit {len(cached[2])} rows")
            listings, stats = cached[2], cached[3]
            _apply_category_map(listings)
            return listings, stats

    disk = _read_listings_disk_cache(path)
    if disk:
        listings, stats = disk
        _apply_category_map(listings)
        with _STOCK_LOCK:
            _LISTINGS_MEM_CACHE[key] = (mtime, size, listings, stats)
        _shop_debug_log(f"listings disk hit {len(listings)} rows")
        if not _read_events_disk_cache(path):
            _repair_events_cache(path, listings, stats)
        return listings, stats

    t0 = time.time()
    listings, stats = _parse_links_file(path)
    _shop_debug_log(f"listings parsed {len(listings)} rows in {time.time() - t0:.2f}s")
    _apply_category_map(listings)
    if listings:
        _store_listings_cache(path, listings, stats)
    return listings, stats


def warm_shop_listings_cache() -> None:
    """Parse links.txt (or load disk cache) in background — call on registry startup."""
    path = _resolve_links_txt()
    key = str(path)
    with _STOCK_LOCK:
        if key in _LISTINGS_WARMING:
            return
        _LISTINGS_WARMING.add(key)

    def _work() -> None:
        try:
            if not path.is_file():
                print(f"[tm-shop] warm skip — links.txt not found: {path}", flush=True)
                return
            t0 = time.time()
            listings, stats = _load_all_listings(path)
            if listings and not _read_events_disk_cache(path):
                _repair_events_cache(path, listings, stats)
            print(
                f"[tm-shop] warmed {len(listings)} listings from {path} "
                f"({stats.get('lines_read', 0)} lines) in {time.time() - t0:.1f}s",
                flush=True,
            )
            shop_ai_if_due()
        except Exception as e:
            print(f"[tm-shop] warm failed: {e!r}", flush=True)
        finally:
            with _STOCK_LOCK:
                _LISTINGS_WARMING.discard(key)

    threading.Thread(target=_work, daemon=True, name="tm-shop-warm").start()


def _cached_event_count(path: Path) -> int:
    ev_disk = _read_events_disk_cache(path)
    if ev_disk:
        return len(ev_disk[0])
    meta_path = _listings_disk_meta_path()
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
        mtime, size = _links_file_fingerprint(path)
        if meta.get("links_txt") != str(path):
            return 0
        if meta.get("links_mtime") != mtime or meta.get("links_size") != size:
            return 0
        return int(meta.get("event_count") or 0)
    except (OSError, json.JSONDecodeError, TypeError):
        return 0


def _load_listings(*, limit: int = 10000) -> tuple[list[dict], Path, str | None, dict]:
    path = _resolve_links_txt()
    stats = {"lines_read": 0, "lines_parsed": 0, "lines_skipped": 0, "purchasable": 0}
    if not path.is_file():
        return [], path, "links_txt_not_found", stats
    listings, stats = _load_all_listings(path)
    if "error" in stats and not listings:
        return [], path, str(stats.get("error")), stats
    if limit > 0:
        listings = listings[:limit]
    return listings, path, None, stats


def _sanitize_shop_response(body: dict) -> dict:
    """Strip internal fields from JSON sent to browsers."""
    if not body.get("ok"):
        _shop_debug_log(f"shop API error: {body.get('error')} | {body.get('detail')}")
        return {
            "ok": False,
            "error": "unavailable",
            "message": "Events are temporarily unavailable. Please try again shortly.",
            "count": 0,
            "event_count": 0,
            "events": [],
            "listings": [],
            "email_purchase_enabled": _email_purchase_enabled(),
            "stripe_enabled": bool((os.environ.get("STRIPE_SECRET_KEY") or "").strip()),
        }
    allow = (
        "ok",
        "count",
        "event_count",
        "events",
        "listings",
        "returned_count",
        "has_more",
        "limit",
        "offset",
        "events_only",
        "shop_email",
        "email_purchase_enabled",
        "stripe_enabled",
        "q",
        "catalog_count",
        "event_key",
    )
    return {k: body[k] for k in allow if k in body}


def shop_listings(
    limit: int = 2500,
    *,
    offset: int = 0,
    events_only: bool = False,
    q: str = "",
    event_key: str = "",
) -> dict:
    t0 = time.time()
    path = _resolve_links_txt()
    query = (q or "").strip()
    ek_filter = (event_key or "").strip()
    req_limit = int(limit or 0)
    if not events_only:
        if req_limit <= 0:
            limit = 2000
        else:
            limit = min(req_limit, 2000)
        if req_limit > 2000:
            _shop_debug_log(f"limit clamped {req_limit} -> {limit}")
    if not path.is_file():
        return _sanitize_shop_response({
            "ok": False,
            "error": "links_txt_not_found",
            "detail": "links_txt_not_found",
            "links_txt": str(path),
            "listings": [],
            "count": 0,
            "event_count": 0,
            "parse_stats": {"lines_read": 0, "lines_parsed": 0, "lines_skipped": 0, "purchasable": 0},
        })

    if events_only:
        ev_disk = _read_events_disk_cache(path)
        if not ev_disk:
            listings, stats = _load_all_listings(path)
            if listings:
                events = _repair_events_cache(path, listings, stats)
                meta_count = len(listings)
                parse_stats = stats
            else:
                events, meta_count, parse_stats = [], 0, stats
        else:
            events, meta = ev_disk
            meta_count = int(meta.get("count") or 0)
            parse_stats = meta.get("parse_stats") if isinstance(meta.get("parse_stats"), dict) else {}
        if events:
            catalog_count = meta_count
            if query:
                events = [e for e in events if _matches_shop_query(e, query)]
            _normalize_events_for_api(events)
            _enrich_events_with_cached_images(events)
            ticket_count = sum(int(e.get("ticket_count") or 0) for e in events) if query else catalog_count
            ms = int((time.time() - t0) * 1000)
            _shop_debug_log(
                f"GET events_only {len(events)} events count={catalog_count} q={query!r} {ms}ms"
            )
            return _sanitize_shop_response({
                "ok": True,
                "links_txt_exists": True,
                "registry_lookup": _registry_lookup_enabled(),
                "count": ticket_count,
                "catalog_count": catalog_count,
                "returned_count": 0,
                "limit": limit,
                "offset": offset,
                "events_only": True,
                "cached": bool(ev_disk),
                "event_count": len(events),
                "events": events,
                "listings": [],
                "parse_stats": parse_stats,
                "shop_email": "ezy.dev.bot@gmail.com",
                "email_purchase_enabled": _email_purchase_enabled(),
                "stripe_enabled": bool((os.environ.get("STRIPE_SECRET_KEY") or "").strip()),
                "marketplace": _db_stats(),
                "timing_ms": ms,
                "q": query,
            })
        ms = int((time.time() - t0) * 1000)
        _shop_debug_log(f"GET events_only empty q={query!r} {ms}ms")
        return _sanitize_shop_response({
            "ok": True,
            "links_txt_exists": path.is_file(),
            "count": 0,
            "catalog_count": 0,
            "event_count": 0,
            "events": [],
            "listings": [],
            "events_only": True,
            "timing_ms": ms,
            "email_purchase_enabled": _email_purchase_enabled(),
            "stripe_enabled": bool((os.environ.get("STRIPE_SECRET_KEY") or "").strip()),
        })

    all_listings, parse_stats = _load_all_listings(path)
    catalog_count = len(all_listings)
    if ek_filter:
        all_listings = [r for r in all_listings if str(r.get("event_key") or "") == ek_filter]
    elif query:
        all_listings = _filter_listings_query(all_listings, query)
    total_count = len(all_listings)
    off = max(0, int(offset or 0))
    page_limit = limit if not events_only else 0
    if not events_only and page_limit > 0:
        page_limit = min(page_limit, 2000)
    if page_limit <= 0:
        page = all_listings[off:]
    else:
        page = all_listings[off : off + page_limit]
    err = None
    if "error" in parse_stats and not all_listings:
        err = str(parse_stats.get("error"))
    if err and not all_listings:
        return _sanitize_shop_response({
            "ok": False,
            "error": err.split(":")[0] if err else "links_txt_not_found",
            "detail": err,
            "links_txt": str(path),
            "listings": [],
            "count": 0,
            "event_count": 0,
            "parse_stats": parse_stats,
        })
    event_count = _cached_event_count(path)
    stats = _db_stats()
    ms = int((time.time() - t0) * 1000)
    has_more = off + len(page) < total_count
    _shop_debug_log(
        f"GET events_only={events_only} limit={limit} offset={off} q={query!r} "
        f"event_key={ek_filter!r} total={total_count} returned={len(page)} has_more={has_more} {ms}ms"
    )
    return _sanitize_shop_response({
        "ok": True,
        "links_txt": str(path),
        "links_txt_exists": path.is_file(),
        "registry_lookup": _registry_lookup_enabled(),
        "stock_path": str(path),
        "count": total_count,
        "catalog_count": catalog_count,
        "returned_count": len(page),
        "has_more": has_more,
        "limit": limit,
        "offset": off,
        "events_only": events_only,
        "event_count": event_count,
        "events": [],
        "listings": page,
        "parse_stats": parse_stats,
        "timing_ms": ms,
        "shop_email": "ezy.dev.bot@gmail.com",
        "email_purchase_enabled": _email_purchase_enabled(),
        "stripe_enabled": bool((os.environ.get("STRIPE_SECRET_KEY") or "").strip()),
        "marketplace": stats,
        "q": query,
        "event_key": ek_filter,
    })


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
    if not _email_purchase_enabled():
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
    if not row.get("purchasable", True) or not (row.get("link") or "").strip():
        return 400, {"ok": False, "error": "listing_not_purchasable"}
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


HOME_SNAPSHOT_TTL_SEC = 86400
HOME_POPULAR_LIMIT = 14
HOME_CAROUSEL_LIMIT = 24
HOME_SHOWS_GRID_LIMIT = 24

_FAMOUS_KEYWORDS = (
    "taylor swift",
    "beyonce",
    "drake",
    "bad bunny",
    "ed sheeran",
    "coldplay",
    "u2",
    "metallica",
    "harry styles",
    "billie eilish",
    "olivia rodrigo",
    "zach bryan",
    "my chemical romance",
    "florence",
    "chris stapleton",
    "madison beer",
    "paul mccartney",
    "billy joel",
    "bruce springsteen",
    "adele",
    "disney on ice",
    "bailey zimmerman",
    "forrest frank",
    "the weeknd",
    "post malone",
    "morgan wallen",
    "luke combs",
    "travis scott",
    "kendrick lamar",
    "sabrina carpenter",
)


def _home_snapshot_path() -> Path:
    return _stock_data_dir() / "shop_home_snapshot.json"


def _resolve_openai_api_key() -> str:
    """Same key sources as STUB.py: env STUBBY_OPENAI_API_KEY / OPENAI_API_KEY, then STUB.py fallback."""
    for name in ("STUBBY_OPENAI_API_KEY", "OPENAI_API_KEY"):
        key = (os.environ.get(name) or "").strip()
        if key:
            return key
    for root in _script_roots():
        for stub in (root.parent / "STUB.py", root / "STUB.py", root.parent.parent / "STUB.py"):
            if not stub.is_file():
                continue
            try:
                text = stub.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            m = re.search(r'_STUBBY_OPENAI_API_KEY[\s\S]*?\bor\s+"(sk-[^"]+)"', text)
            if m:
                key = m.group(1).strip()
                if key.startswith("sk-"):
                    return key
    return ""


def _fame_score(name: str) -> int:
    n = (name or "").lower()
    for kw in _FAMOUS_KEYWORDS:
        if kw in n:
            return 50
    return 0


def _popularity_score(event: dict) -> float:
    tc = int(event.get("ticket_count") or 0)
    fame = _fame_score(str(event.get("event_name") or ""))
    ts = int(event.get("event_date_ts") or 0)
    recency = 0.0
    if ts > 0:
        days = (ts - time.time()) / 86400.0
        if 0 <= days <= 90:
            recency = 15.0
        elif -14 <= days < 0:
            recency = 12.0
    img = 5.0 if str(event.get("image_url") or "").startswith("http") else 0.0
    return float(tc) + fame + recency + img


def _slim_home_event(event: dict) -> dict:
    return {
        "event_key": event.get("event_key") or "",
        "event_name": event.get("event_name") or "",
        "event_id": event.get("event_id") or "",
        "event_date_display": event.get("event_date_display") or "",
        "venue": event.get("venue") or "",
        "category": event.get("category") or "events",
        "image_url": event.get("image_url") or "",
        "ticket_count": int(event.get("ticket_count") or 0),
        "min_price_usd": float(event.get("min_price_usd") or 0),
    }


def _home_events_to_cards(events: list[dict]) -> list[dict]:
    out: list[dict] = []
    for e in events:
        slim = _slim_home_event(e)
        slim["count"] = slim["ticket_count"]
        slim["min_price"] = slim["min_price_usd"]
        out.append(slim)
    return out


def _category_catalog_totals(events: list[dict]) -> dict[str, dict[str, int]]:
    totals = {
        "concerts": {"tickets": 0, "events": 0},
        "sports": {"tickets": 0, "events": 0},
        "events": {"tickets": 0, "events": 0},
    }
    for e in events:
        cat = str(e.get("category") or "events")
        if cat == "parking":
            continue
        bucket = cat if cat in totals else "events"
        totals[bucket]["tickets"] += int(e.get("ticket_count") or 0)
        totals[bucket]["events"] += 1
    return totals


def _parse_ai_event_keys(content: str) -> list[str] | None:
    text = (content or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[[^\]]+\]", text, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if isinstance(data, dict):
        keys = data.get("event_keys") or data.get("keys") or data.get("popular")
        if isinstance(keys, list):
            return [str(k).strip() for k in keys if str(k).strip()]
        return None
    if isinstance(data, list):
        return [str(k).strip() for k in data if str(k).strip()]
    return None


def _ai_rank_popular_event_keys(candidates: list[dict], *, limit: int = HOME_POPULAR_LIMIT) -> list[str] | None:
    api_key = _resolve_openai_api_key()
    if not api_key or len(candidates) < limit:
        if not api_key:
            _shop_debug_log("AI popular rank skipped: no OpenAI key (set STUBBY_OPENAI_API_KEY)")
        return None
    top = sorted(candidates, key=_popularity_score, reverse=True)[:80]
    id_to_key: dict[str, str] = {}
    lines: list[str] = []
    for i, e in enumerate(top, 1):
        sid = str(i)
        ek = str(e.get("event_key") or "")
        if not ek:
            continue
        id_to_key[sid] = ek
        lines.append(
            f"{sid}. {e.get('event_name')} ({int(e.get('ticket_count') or 0)} tickets)"
        )
    if len(id_to_key) < limit:
        return None
    model = (os.environ.get("OPENAI_HOME_MODEL") or "gpt-4o-mini").strip()
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Pick the most famous mainstream events for a ticket homepage. "
                    f'Reply JSON only: {{"picks":["1","2",...]}} with {limit} numeric ids from the list.'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Pick the {limit} most famous events:\n\n" + "\n".join(lines)
                ),
            },
        ],
        "temperature": 0.15,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        ids = _parse_ai_pick_ids(content)
        if not ids:
            return None
        picked: list[str] = []
        for sid in ids:
            ek = id_to_key.get(str(sid).strip())
            if ek and ek not in picked:
                picked.append(ek)
        if picked:
            _shop_debug_log(f"AI popular rank ok picked={len(picked)} model={model}")
        return picked[:limit] if len(picked) >= min(limit, 3) else None
    except Exception as e:
        _shop_debug_log(f"AI popular rank failed: {e!r}")
        return None


def _home_snapshot_stale(snap: dict, path: Path) -> bool:
    if not snap.get("ok"):
        return True
    if float(snap.get("expires_at") or 0) <= time.time():
        return True
    mtime, size = _links_file_fingerprint(path)
    if snap.get("links_mtime") != mtime or snap.get("links_size") != size:
        return True
    if snap.get("cache_version") != SHOP_LISTINGS_CACHE_VERSION:
        return True
    return False


def _pick_popular_events(
    events: list[dict],
    *,
    allow_ai: bool = True,
    prev_popular_keys: list[str] | None = None,
) -> tuple[list[dict], str]:
    by_key = {str(e.get("event_key") or ""): e for e in events if e.get("event_key")}
    ranking = "heuristic"
    popular: list[dict] = []
    seen: set[str] = set()

    if allow_ai:
        ai_keys = _ai_rank_popular_event_keys(events, limit=HOME_POPULAR_LIMIT)
        if ai_keys:
            ranking = "ai"
            for key in ai_keys:
                row = by_key.get(key)
                if row and key not in seen:
                    popular.append(row)
                    seen.add(key)
    elif prev_popular_keys:
        for key in prev_popular_keys:
            if len(popular) >= HOME_POPULAR_LIMIT:
                break
            row = by_key.get(key)
            if row and key not in seen:
                popular.append(row)
                seen.add(key)
        if popular:
            ranking = "ai_cached"

    scored = sorted(events, key=_popularity_score, reverse=True)
    for row in scored:
        if len(popular) >= HOME_POPULAR_LIMIT:
            break
        key = str(row.get("event_key") or "")
        if key and key not in seen:
            popular.append(row)
            seen.add(key)
    return popular[:HOME_POPULAR_LIMIT], ranking


def _prev_popular_keys_from_snap(snap: dict | None) -> list[str]:
    if not snap:
        return []
    sec = (snap.get("sections") or {}).get("popular") or {}
    rows = sec.get("events") if isinstance(sec, dict) else []
    if not isinstance(rows, list):
        return []
    out: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            k = str(row.get("event_key") or "").strip()
            if k:
                out.append(k)
    return out


def shop_build_home_snapshot(*, force: bool = False, skip_ai: bool = False, _ai_lock_held: bool = False) -> dict:
    t0 = time.time()
    path = _resolve_links_txt()
    if not path.is_file():
        return {"ok": False, "error": "links_txt_not_found", "detail": str(path)}
    snap_path = _home_snapshot_path()
    prev_snap: dict | None = None
    if snap_path.is_file():
        try:
            prev_snap = json.loads(snap_path.read_text(encoding="utf-8", errors="replace"))
            ai_due = _ai_cooldown_due(force=force)
            if (
                isinstance(prev_snap, dict)
                and not force
                and not _home_snapshot_stale(prev_snap, path)
                and (not ai_due or skip_ai)
            ):
                prev_snap["cached"] = True
                if skip_ai and ai_due:
                    prev_snap["ai_pending"] = True
                prev_snap["timing_ms"] = int((time.time() - t0) * 1000)
                return prev_snap
        except (OSError, json.JSONDecodeError, TypeError):
            prev_snap = None

    ev_disk = _read_events_disk_cache(path)
    if not ev_disk:
        listings, stats = _load_all_listings(path)
        if not listings:
            return {"ok": False, "error": "no_events", "parse_stats": stats}
        events = _repair_events_cache(path, listings, stats)
        catalog_count = len(listings)
    else:
        events, meta = ev_disk
        catalog_count = int(meta.get("count") or 0)
    _normalize_events_for_api(events)
    _enrich_events_with_cached_images(events)

    allow_ai = _ai_cooldown_due(force=force) and not skip_ai
    owns_ai_lock = False
    if allow_ai and not _ai_lock_held:
        with _AI_LOCK:
            if _AI_RUNNING:
                _shop_debug_log("AI categorize skipped — pipeline already running")
                allow_ai = False
            else:
                _AI_RUNNING = True
                owns_ai_lock = True
    ai_attempted = False
    ai_ok = False
    try:
        if allow_ai:
            ai_attempted = True
            if not _resolve_openai_api_key():
                _shop_debug_log("AI run due but no OpenAI key — cooldown not marked")
            else:
                _shop_debug_log("AI cooldown due — rebuilding categories + popular picks")
        cmap: dict[str, str] = {}
        if allow_ai and _resolve_openai_api_key():
            cmap = _ai_refresh_category_map(events, allow_ai=True, path=path)
            _apply_category_map(events)
            ai_ok = len(cmap) >= max(50, int(len(events) * 0.5))
        elif not allow_ai:
            _prune_category_map(
                {str(e.get("event_key") or "") for e in events if e.get("event_key")}, path
            )
            _apply_category_map(events)

        prev_keys = _prev_popular_keys_from_snap(prev_snap if isinstance(prev_snap, dict) else None)
        popular, ranking = _pick_popular_events(
            events,
            allow_ai=allow_ai and bool(_resolve_openai_api_key()),
            prev_popular_keys=prev_keys if not allow_ai else None,
        )
        if allow_ai and ranking in ("ai", "ai_cached"):
            ai_ok = True
        ai_ranked_at = _read_ai_cooldown_ts() or time.time()
        if ai_attempted and ai_ok and _resolve_openai_api_key():
            _ai_cooldown_mark()
            ai_ranked_at = _read_ai_cooldown_ts() or time.time()
        elif ai_attempted and allow_ai and cmap and not ai_ok:
            _shop_debug_log("AI pipeline finished but quality low — cooldown not marked")
        concerts = sorted(
            [e for e in events if e.get("category") == "concerts"],
            key=lambda x: (-(x.get("ticket_count") or 0), x.get("event_name") or ""),
        )[:HOME_CAROUSEL_LIMIT]
        sports = sorted(
            [e for e in events if e.get("category") == "sports"],
            key=lambda x: (-(x.get("ticket_count") or 0), x.get("event_name") or ""),
        )[:HOME_CAROUSEL_LIMIT]
        shows = sorted(
            [e for e in events if e.get("category") == "events"],
            key=lambda x: (-(x.get("ticket_count") or 0), x.get("event_name") or ""),
        )[:HOME_SHOWS_GRID_LIMIT]
        cat_totals = _category_catalog_totals(events)
        hero = popular[0] if popular else (events[0] if events else {})
        mtime, size = _links_file_fingerprint(path)
        now = time.time()
        snapshot = {
            "ok": True,
            "generated_at": now,
            "expires_at": now + HOME_SNAPSHOT_TTL_SEC,
            "links_mtime": mtime,
            "links_size": size,
            "cache_version": SHOP_LISTINGS_CACHE_VERSION,
            "count": catalog_count,
            "event_count": len(events),
            "ranking": ranking,
            "ai_ranked_at": ai_ranked_at,
            "hero_event_key": str(hero.get("event_key") or ""),
            "hero_image_url": str(hero.get("image_url") or ""),
            "hero_event_name": str(hero.get("event_name") or ""),
            "category_totals": cat_totals,
            "sections": {
                "popular": {"events": _home_events_to_cards(popular)},
                "concerts": {"events": _home_events_to_cards(concerts)},
                "sports": {"events": _home_events_to_cards(sports)},
                "shows": {"events": _home_events_to_cards(shows)},
            },
            "cached": False,
            "timing_ms": int((time.time() - t0) * 1000),
        }
        try:
            snap_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            _shop_debug_log(
                f"home snapshot built ranking={ranking} allow_ai={allow_ai} ai_ok={ai_ok} "
                f"popular={len(popular)} events={len(events)} tickets={catalog_count} "
                f"{snapshot['timing_ms']}ms"
            )
        except OSError as e:
            _shop_debug_log(f"home snapshot write failed: {e!r}")
        return snapshot
    finally:
        if owns_ai_lock:
            with _AI_LOCK:
                _AI_RUNNING = False


def _sanitize_home_response(body: dict) -> dict:
    if not body.get("ok"):
        return {
            "ok": False,
            "error": "unavailable",
            "message": "Events are temporarily unavailable. Please try again shortly.",
            "count": 0,
            "event_count": 0,
            "sections": {},
        }
    allow = (
        "ok",
        "count",
        "event_count",
        "sections",
        "category_totals",
        "generated_at",
        "expires_at",
        "ranking",
        "hero_event_key",
        "hero_image_url",
        "hero_event_name",
        "cached",
        "timing_ms",
    )
    return {k: body[k] for k in allow if k in body}


def _schedule_ai_pipeline(*, force: bool = False) -> bool:
    global _AI_RUNNING
    with _AI_LOCK:
        if _AI_RUNNING:
            _shop_debug_log("AI pipeline already running — skip duplicate start")
            return False
        _AI_RUNNING = True

    def _work() -> None:
        global _AI_RUNNING
        try:
            _shop_debug_log("AI pipeline background start")
            shop_build_home_snapshot(force=force, skip_ai=False, _ai_lock_held=True)
        except Exception as e:
            _shop_debug_log(f"AI pipeline background failed: {e!r}")
        finally:
            with _AI_LOCK:
                _AI_RUNNING = False
            _shop_debug_log("AI pipeline background done")

    threading.Thread(target=_work, daemon=True, name="tm-shop-ai").start()
    return True


def shop_ai_if_due(*, force: bool = False) -> dict:
    """Run AI categorization + homepage snapshot when ai_cooldown.txt is missing or 24h old."""
    if not _ai_cooldown_due(force=force):
        left = _ai_cooldown_seconds_left()
        _shop_debug_log(f"AI cooldown active — {left}s until next run")
        snap_path = _home_snapshot_path()
        if snap_path.is_file():
            try:
                snap = json.loads(snap_path.read_text(encoding="utf-8", errors="replace"))
                if isinstance(snap, dict) and snap.get("ok"):
                    snap["ai_skipped"] = True
                    snap["ai_cooldown_sec_left"] = left
                    return snap
            except (OSError, json.JSONDecodeError, TypeError):
                pass
        return {"ok": True, "ai_skipped": True, "ai_cooldown_sec_left": left}
    if force:
        return shop_build_home_snapshot(force=True, skip_ai=False)
    _schedule_ai_pipeline(force=False)
    path = _resolve_links_txt()
    snap_path = _home_snapshot_path()
    if snap_path.is_file():
        try:
            snap = json.loads(snap_path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(snap, dict) and snap.get("ok") and not _home_snapshot_stale(snap, path):
                snap["cached"] = True
                snap["ai_pending"] = True
                return snap
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return shop_build_home_snapshot(force=False, skip_ai=True)


def shop_home(*, refresh: bool = False) -> dict:
    path = _resolve_links_txt()
    snap_path = _home_snapshot_path()
    ai_due = _ai_cooldown_due(force=refresh)
    if snap_path.is_file():
        try:
            snap = json.loads(snap_path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(snap, dict) and snap.get("ok") and not _home_snapshot_stale(snap, path):
                if not refresh:
                    if ai_due:
                        _schedule_ai_pipeline(force=refresh)
                        snap["ai_pending"] = True
                    snap["cached"] = True
                    snap["age_sec"] = int(max(0, time.time() - float(snap.get("generated_at") or 0)))
                    return _sanitize_home_response(snap)
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    built = shop_ai_if_due(force=refresh)
    return _sanitize_home_response(built)


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
