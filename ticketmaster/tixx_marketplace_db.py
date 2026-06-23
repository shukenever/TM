#!/usr/bin/env python3
"""
Tixx marketplace SQLite store — orders, accounts, addresses, cards, listing cache.

Env:
  TIXX_MARKETPLACE_DB — path to sqlite file (default: next to stock CSV / tixx_marketplace.db)
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_DB_LOCK = threading.Lock()
_CONN: sqlite3.Connection | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_db_path() -> Path:
    explicit = (os.environ.get("TIXX_MARKETPLACE_DB") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    for key in ("TM_STUBHUB_STOCK_CSV", "SECURE_PASS_STOCK_FILE"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return Path(v).expanduser().resolve().parent / "tixx_marketplace.db"
    here = Path(__file__).resolve().parent
    for cand in (here.parent / "tixx_marketplace.db", here / "tixx_marketplace.db"):
        return cand
    return here.parent / "tixx_marketplace.db"


def db_path() -> Path:
    return _default_db_path()


def _connect() -> sqlite3.Connection:
    global _CONN
    if _CONN is not None:
        return _CONN
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _CONN = conn
    return conn


def init_db() -> None:
    with _DB_LOCK:
        c = _connect()
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS orders (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              order_id TEXT UNIQUE NOT NULL,
              created_at TEXT NOT NULL,
              buyer_email TEXT NOT NULL,
              buyer_name TEXT,
              listing_id TEXT,
              event_name TEXT,
              event_key TEXT,
              event_date TEXT,
              venue TEXT,
              section TEXT,
              row TEXT,
              seat TEXT,
              price_usd REAL,
              face_value_usd REAL,
              ticket_link TEXT,
              status TEXT NOT NULL DEFAULT 'completed',
              payment_method TEXT,
              stripe_session_id TEXT,
              email_sent INTEGER NOT NULL DEFAULT 0,
              meta_json TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_orders_email ON orders(buyer_email, created_at DESC);

            CREATE TABLE IF NOT EXISTS accounts (
              email TEXT PRIMARY KEY,
              first_name TEXT,
              last_name TEXT,
              phone TEXT,
              city TEXT,
              region TEXT,
              default_date_filter TEXT,
              email_updates INTEGER NOT NULL DEFAULT 1,
              prefs_json TEXT,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS addresses (
              id TEXT PRIMARY KEY,
              email TEXT NOT NULL,
              label TEXT,
              line1 TEXT NOT NULL,
              line2 TEXT,
              city TEXT,
              state TEXT,
              zip TEXT,
              country TEXT DEFAULT 'US',
              is_default INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_addresses_email ON addresses(email);

            CREATE TABLE IF NOT EXISTS payment_methods (
              id TEXT PRIMARY KEY,
              email TEXT NOT NULL,
              brand TEXT,
              last4 TEXT NOT NULL,
              exp_month TEXT,
              exp_year TEXT,
              name_on_card TEXT,
              is_default INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_cards_email ON payment_methods(email);

            CREATE TABLE IF NOT EXISTS listings_cache (
              listing_id TEXT PRIMARY KEY,
              event_key TEXT,
              event_id TEXT,
              event_name TEXT,
              event_date TEXT,
              venue TEXT,
              section TEXT,
              row TEXT,
              seat TEXT,
              price_usd REAL,
              face_value_usd REAL,
              category TEXT,
              image_url TEXT,
              path TEXT,
              search_blob TEXT,
              event_date_ts INTEGER,
              updated_at TEXT NOT NULL,
              active INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_listings_event ON listings_cache(event_key, active);
            CREATE INDEX IF NOT EXISTS idx_listings_active ON listings_cache(active, event_date);

            CREATE TABLE IF NOT EXISTS sync_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              at TEXT NOT NULL,
              kind TEXT NOT NULL,
              detail TEXT,
              listings_count INTEGER,
              images_resolved INTEGER
            );
            """
        )
        c.commit()


def _norm_email(em: str) -> str:
    return (em or "").strip().lower()


def insert_order(row: dict) -> dict:
    init_db()
    oid = (row.get("order_id") or "").strip() or uuid.uuid4().hex
    with _DB_LOCK:
        c = _connect()
        c.execute(
            """
            INSERT INTO orders (
              order_id, created_at, buyer_email, buyer_name, listing_id,
              event_name, event_key, event_date, venue, section, row, seat,
              price_usd, face_value_usd, ticket_link, status, payment_method,
              stripe_session_id, email_sent, meta_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(order_id) DO UPDATE SET
              status=excluded.status,
              email_sent=excluded.email_sent,
              meta_json=excluded.meta_json
            """,
            (
                oid,
                row.get("created_at") or _utc_now(),
                _norm_email(str(row.get("buyer_email") or "")),
                (row.get("buyer_name") or "")[:120] or None,
                row.get("listing_id"),
                row.get("event_name"),
                row.get("event_key"),
                row.get("event_date"),
                row.get("venue"),
                row.get("section"),
                row.get("row"),
                row.get("seat"),
                row.get("price_usd"),
                row.get("face_value_usd"),
                row.get("ticket_link") or row.get("link"),
                row.get("status") or "completed",
                row.get("payment_method"),
                row.get("stripe_session_id"),
                1 if row.get("email_sent") else 0,
                json.dumps(row.get("meta") or {}, ensure_ascii=False) if row.get("meta") else None,
            ),
        )
        c.commit()
    return {"ok": True, "order_id": oid}


def list_orders_for_email(email: str, limit: int = 50) -> list[dict]:
    init_db()
    em = _norm_email(email)
    if not em:
        return []
    with _DB_LOCK:
        c = _connect()
        rows = c.execute(
            """
            SELECT order_id, created_at AS at, listing_id, event_name, price_usd, ticket_link AS link, status
            FROM orders WHERE buyer_email=? AND status != 'failed'
            ORDER BY created_at DESC LIMIT ?
            """,
            (em, max(1, min(limit, 200))),
        ).fetchall()
    return [dict(r) for r in rows]


def get_account(email: str) -> dict:
    init_db()
    em = _norm_email(email)
    if not em:
        return {"ok": False, "error": "invalid_email"}
    with _DB_LOCK:
        c = _connect()
        acc = c.execute("SELECT * FROM accounts WHERE email=?", (em,)).fetchone()
        addrs = c.execute(
            "SELECT id, label, line1, line2, city, state, zip, country, is_default FROM addresses WHERE email=? ORDER BY is_default DESC, created_at",
            (em,),
        ).fetchall()
        cards = c.execute(
            "SELECT id, brand, last4, exp_month, exp_year, name_on_card, is_default FROM payment_methods WHERE email=? ORDER BY is_default DESC, created_at",
            (em,),
        ).fetchall()
    profile = {}
    if acc:
        profile = {
            "firstName": acc["first_name"] or "",
            "lastName": acc["last_name"] or "",
            "phone": acc["phone"] or "",
            "city": acc["city"] or "",
            "region": acc["region"] or "",
            "defaultDateFilter": acc["default_date_filter"] or "all",
            "emailUpdates": bool(acc["email_updates"]),
        }
        if acc["prefs_json"]:
            try:
                profile["prefs"] = json.loads(acc["prefs_json"])
            except json.JSONDecodeError:
                pass
    return {
        "ok": True,
        "email": em,
        "profile": profile,
        "addresses": [_addr_row(r) for r in addrs],
        "cards": [_card_row(r) for r in cards],
    }


def _addr_row(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "label": r["label"] or "Address",
        "line1": r["line1"],
        "line2": r["line2"] or "",
        "city": r["city"] or "",
        "state": r["state"] or "",
        "zip": r["zip"] or "",
        "country": r["country"] or "US",
        "isDefault": bool(r["is_default"]),
    }


def _card_row(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "brand": r["brand"] or "Card",
        "last4": r["last4"],
        "expMonth": r["exp_month"] or "",
        "expYear": r["exp_year"] or "",
        "name": r["name_on_card"] or "",
        "isDefault": bool(r["is_default"]),
    }


def save_account(email: str, body: dict) -> dict:
    init_db()
    em = _norm_email(email)
    if not em:
        return {"ok": False, "error": "invalid_email"}
    prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
    with _DB_LOCK:
        c = _connect()
        c.execute(
            """
            INSERT INTO accounts (email, first_name, last_name, phone, city, region,
              default_date_filter, email_updates, prefs_json, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(email) DO UPDATE SET
              first_name=excluded.first_name,
              last_name=excluded.last_name,
              phone=excluded.phone,
              city=excluded.city,
              region=excluded.region,
              default_date_filter=excluded.default_date_filter,
              email_updates=excluded.email_updates,
              prefs_json=excluded.prefs_json,
              updated_at=excluded.updated_at
            """,
            (
                em,
                (prof.get("firstName") or "")[:80] or None,
                (prof.get("lastName") or "")[:80] or None,
                (prof.get("phone") or "")[:40] or None,
                (prof.get("city") or "")[:80] or None,
                (prof.get("region") or "")[:40] or None,
                (prof.get("defaultDateFilter") or prof.get("default_date_filter") or "all")[:20],
                1 if prof.get("emailUpdates", True) else 0,
                json.dumps(prof.get("prefs") or {}, ensure_ascii=False) if prof.get("prefs") else None,
                _utc_now(),
            ),
        )
        if isinstance(body.get("addresses"), list):
            c.execute("DELETE FROM addresses WHERE email=?", (em,))
            for a in body["addresses"]:
                if not isinstance(a, dict) or not (a.get("line1") or "").strip():
                    continue
                c.execute(
                    """
                    INSERT INTO addresses (id, email, label, line1, line2, city, state, zip, country, is_default, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        (a.get("id") or uuid.uuid4().hex)[:64],
                        em,
                        (a.get("label") or "Address")[:40],
                        (a.get("line1") or "")[:200],
                        (a.get("line2") or "")[:200] or None,
                        (a.get("city") or "")[:80] or None,
                        (a.get("state") or "")[:40] or None,
                        (a.get("zip") or "")[:20] or None,
                        (a.get("country") or "US")[:2],
                        1 if a.get("isDefault") else 0,
                        _utc_now(),
                    ),
                )
        if isinstance(body.get("cards"), list):
            c.execute("DELETE FROM payment_methods WHERE email=?", (em,))
            for card in body["cards"]:
                if not isinstance(card, dict) or not (card.get("last4") or "").strip():
                    continue
                c.execute(
                    """
                    INSERT INTO payment_methods (id, email, brand, last4, exp_month, exp_year, name_on_card, is_default, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        (card.get("id") or uuid.uuid4().hex)[:64],
                        em,
                        (card.get("brand") or "Card")[:20],
                        str(card.get("last4") or "")[-4:],
                        str(card.get("expMonth") or "")[:2],
                        str(card.get("expYear") or "")[:4],
                        (card.get("name") or card.get("name_on_card") or "")[:80] or None,
                        1 if card.get("isDefault") else 0,
                        _utc_now(),
                    ),
                )
        c.commit()
    return {"ok": True, "email": em}


def upsert_listings_cache(listings: list[dict]) -> int:
    init_db()
    if not listings:
        return 0
    now = _utc_now()
    ids = {str(l.get("listing_id") or "") for l in listings if l.get("listing_id")}
    with _DB_LOCK:
        c = _connect()
        if ids:
            placeholders = ",".join("?" * len(ids))
            c.execute(
                f"UPDATE listings_cache SET active=0, updated_at=? WHERE listing_id NOT IN ({placeholders})",
                [now, *ids],
            )
        n = 0
        for l in listings:
            lid = str(l.get("listing_id") or "")
            if not lid:
                continue
            c.execute(
                """
                INSERT INTO listings_cache (
                  listing_id, event_key, event_id, event_name, event_date, venue,
                  section, row, seat, price_usd, face_value_usd, category, image_url,
                  path, search_blob, event_date_ts, updated_at, active
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                ON CONFLICT(listing_id) DO UPDATE SET
                  event_key=excluded.event_key,
                  event_id=excluded.event_id,
                  event_name=excluded.event_name,
                  event_date=excluded.event_date,
                  venue=excluded.venue,
                  section=excluded.section,
                  row=excluded.row,
                  seat=excluded.seat,
                  price_usd=excluded.price_usd,
                  face_value_usd=excluded.face_value_usd,
                  category=excluded.category,
                  image_url=COALESCE(NULLIF(excluded.image_url,''), listings_cache.image_url),
                  path=excluded.path,
                  search_blob=excluded.search_blob,
                  event_date_ts=excluded.event_date_ts,
                  updated_at=excluded.updated_at,
                  active=1
                """,
                (
                    lid,
                    l.get("event_key"),
                    l.get("event_id"),
                    l.get("event_name"),
                    l.get("event_date"),
                    l.get("venue"),
                    l.get("section"),
                    l.get("row"),
                    l.get("seat"),
                    l.get("price_usd"),
                    l.get("face_value_usd"),
                    l.get("category"),
                    l.get("image_url") or "",
                    l.get("path"),
                    l.get("search_blob"),
                    int(l.get("event_date_ts") or 0),
                    now,
                ),
            )
            n += 1
        c.commit()
    return n


def get_listings_from_cache(limit: int = 500) -> list[dict]:
    init_db()
    with _DB_LOCK:
        c = _connect()
        rows = c.execute(
            """
            SELECT * FROM listings_cache WHERE active=1
            ORDER BY event_date, event_name LIMIT ?
            """,
            (max(1, min(limit, 2000)),),
        ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "listing_id": r["listing_id"],
                "event_key": r["event_key"],
                "event_id": r["event_id"],
                "event_name": r["event_name"],
                "event_date": r["event_date"],
                "event_date_display": r["event_name"],  # caller should enrich
                "event_date_ts": r["event_date_ts"],
                "venue": r["venue"],
                "section": r["section"],
                "row": r["row"],
                "seat": r["seat"],
                "price_usd": r["price_usd"],
                "face_value_usd": r["face_value_usd"],
                "category": r["category"],
                "image_url": r["image_url"] or "",
                "path": r["path"],
                "search_blob": r["search_blob"],
            }
        )
    return out


def append_sync_log(kind: str, detail: str, listings_count: int = 0, images_resolved: int = 0) -> None:
    init_db()
    with _DB_LOCK:
        c = _connect()
        c.execute(
            "INSERT INTO sync_log (at, kind, detail, listings_count, images_resolved) VALUES (?,?,?,?,?)",
            (_utc_now(), kind, detail[:500], listings_count, images_resolved),
        )
        c.commit()


def marketplace_stats() -> dict:
    init_db()
    with _DB_LOCK:
        c = _connect()
        orders = c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        active = c.execute("SELECT COUNT(*) FROM listings_cache WHERE active=1").fetchone()[0]
        last = c.execute(
            "SELECT at, listings_count, images_resolved FROM sync_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return {
        "orders": orders,
        "active_listings": active,
        "last_sync_at": last["at"] if last else None,
        "last_sync_listings": last["listings_count"] if last else 0,
        "last_sync_images": last["images_resolved"] if last else 0,
        "db_path": str(db_path()),
    }
