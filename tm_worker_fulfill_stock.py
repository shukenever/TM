"""Stock for Stagefront matching — same sources as Ticketmaster work checker /fulfill."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
BOT_DIR = ROOT / "ticketmaster"
DEFAULT_COLLECTOR = BOT_DIR / "bot_data" / "tm_worker_collector.db"
FALLBACK_COLLECTOR = BOT_DIR / "bot_data" / "collector.db"

# Import fulfill helpers from work checker bot (same repo).
import sys

sys.path.insert(0, str(BOT_DIR))
import bot as tm_bot  # noqa: E402
from list_unfulfilled import prep_df  # noqa: E402


def _collector_path() -> Path:
    raw = os.environ.get("TM_WORKER_COLLECTOR_DB", "").strip()
    if raw:
        return Path(raw)
    if DEFAULT_COLLECTOR.is_file():
        return DEFAULT_COLLECTOR
    return FALLBACK_COLLECTOR


def _fulfill_db_rows_with_creds() -> list[dict]:
    """collector seats + account email/password (fulfill bot DB without okaysec)."""
    db = _collector_path()
    if not db.is_file():
        return []
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        raw = conn.execute(
            """
            SELECT
                e.event_name,
                e.event_date,
                e.venue,
                s.section,
                s.row_name,
                s.seat,
                a.email,
                a.password,
                COALESCE(
                    NULLIF(TRIM(s.submitted_barcode), ''),
                    NULLIF(TRIM(s.expected_barcode), '')
                ) AS barcode
            FROM seats s
            JOIN events e ON e.id = s.event_id
            JOIN accounts a ON a.id = e.account_id
            WHERE COALESCE(
                NULLIF(TRIM(s.submitted_barcode), ''),
                NULLIF(TRIM(s.expected_barcode), '')
            ) IS NOT NULL
            """
        ).fetchall()
    finally:
        conn.close()

    skip_bc = {
        "nobarc",
        "no barc",
        "none",
        "n/a",
        "-",
        "no barcode",
        "not found",
    }
    out: list[dict] = []
    for row in raw:
        bc = tm_bot._fulfill_clean_barcode(row["barcode"] or "")
        raw_bc = str(row["barcode"] or "").strip().lower()
        if raw_bc in skip_bc or (not bc and raw_bc not in ("securetoken:", "securetoken")):
            if not bc and raw_bc in ("securetoken:", "securetoken"):
                bc = ""
            elif not bc:
                continue
        name = (row["event_name"] or "").strip()
        if not name:
            continue
        date_key, _ = tm_bot._fulfill_parse_date(row["event_date"])
        sec = tm_bot._fulfill_clean_section(row["section"])
        out.append(
            {
                "Event Name": name,
                "Event Date": date_key or (row["event_date"] or ""),
                "Venue": (row["venue"] or "").strip(),
                "Section": sec,
                "Row": str(row["row_name"] or "").strip(),
                "Seat": str(row["seat"] or "").strip(),
                "Barcodes": bc,
                "Email": (row["email"] or "").strip(),
                "Password": tm_bot.normalize_password(row["password"]),
            }
        )
    return out


def load_tm_worker_fulfill_stock_df() -> pd.DataFrame:
    """
    okaysec + claimed + collector (with email:pw), same inventory as /fulfill lookup.
    Set TM_WORKER_COLLECTOR_DB to point at pulled tm_worker_collector.db.
    """
    # Temporarily point bot DB_PATH at worker collector for fulfill_inventory_db_rows overlap.
    collector = _collector_path()
    old_db = tm_bot.DB_PATH
    tm_bot.DB_PATH = collector
    tm_bot._fulfill_rows_cache = None
    tm_bot._fulfill_rows_mtime = 0.0

    okay_env = os.environ.get("TM_WORKER_OKAYSEC", "").strip()
    if okay_env:
        tm_bot.FULFILL_OKAYSEC_PATHS = [Path(okay_env)] + list(tm_bot.FULFILL_OKAYSEC_PATHS)

    rows: list[dict] = []
    for rec in _fulfill_db_rows_with_creds():
        rows.append(rec)

    # okaysec / claimed from bot loader (barcodes only — merge creds from db rows by seat key)
    cred_by_key: dict[tuple, tuple[str, str]] = {}
    for rec in rows:
        key = (
            str(rec.get("Event Name") or "").lower(),
            str(rec.get("Event Date") or "")[:10],
            str(rec.get("Section") or "").upper(),
            str(rec.get("Row") or "").upper(),
            str(rec.get("Seat") or "").strip(),
        )
        em = rec.get("Email") or ""
        pw = rec.get("Password") or ""
        if em and pw:
            cred_by_key[key] = (em, pw)

    for r in tm_bot.load_fulfill_inventory_rows():
        bc = r.get("barcode") or ""
        if not bc:
            continue
        date_key = r.get("date_key") or ""
        key = (
            str(r.get("event_name") or "").lower(),
            date_key[:10],
            str(r.get("section") or "").upper(),
            str(r.get("row") or "").upper(),
            str(r.get("seat") or "").strip(),
        )
        em, pw = cred_by_key.get(key, ("", ""))
        rows.append(
            {
                "Event Name": r.get("event_name") or "",
                "Event Date": date_key,
                "Venue": "",
                "Section": r.get("section") or "",
                "Row": r.get("row") or "",
                "Seat": r.get("seat") or "",
                "Barcodes": bc,
                "Email": em,
                "Password": pw,
            }
        )

    tm_bot.DB_PATH = old_db
    tm_bot._fulfill_rows_cache = None

    if not rows:
        return prep_df(pd.DataFrame(columns=["Section", "Row", "Seat", "Barcodes", "Event Date", "Venue", "Email", "Password"]))
    df = prep_df(pd.DataFrame(rows))
    # de-dupe: prefer rows with email
    df = df.sort_values(by=["Email"], ascending=False, na_position="last")
    df = df.drop_duplicates(subset=["_sec", "_row", "_seat", "_edate", "_bc"], keep="first")
    return prep_df(df.reset_index(drop=True))
