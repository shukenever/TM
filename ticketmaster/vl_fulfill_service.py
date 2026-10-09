"""Victory Live mobile fulfill by invoice (used by Telegram /fulfill flow)."""
from __future__ import annotations

import os
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

_TICKETMASTER_DIR = Path(__file__).resolve().parent
_ROOT = _TICKETMASTER_DIR.parent
sys.path.insert(0, str(_ROOT))

import fulfill_victory_live as fv  # noqa: E402
from list_unfulfilled import prep_df  # noqa: E402
from vl_auth import APP_BASE  # noqa: E402
from vl_inventory_sync import load_session as vl_load_session  # noqa: E402

DB_PATH = _TICKETMASTER_DIR / "bot_data" / "collector.db"
AUTOFULFILL_WORKERS = max(1, min(8, int(os.environ.get("VL_AUTOFULFILL_WORKERS", "3"))))
_thread_sessions = threading.local()


def _find_order(session, invoice: str) -> dict | None:
    inv = str(invoice).strip()
    if not inv:
        return None
    r = session.get(
        f"{APP_BASE}/api/orders/search",
        params={
            "IsInHandOnly": "false",
            "Page": "1",
            "PageSize": "25",
            "SearchText": inv,
            "ShowPosOrders": "true",
        },
        timeout=90,
    )
    r.raise_for_status()
    for o in r.json().get("Data", {}).get("Orders", []) or []:
        if str(o.get("InvoiceNumber") or "").strip() == inv:
            return o
    return None


def _junk_barcode(bc: str) -> bool:
    from fulfill_victory_live import barcode_usable

    return not barcode_usable(bc)


def _bot_db_stock_rows() -> list[dict]:
    if not DB_PATH.is_file():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        raw = conn.execute(
            """
            SELECT
                e.event_name AS "Event Name",
                e.event_date AS "Event Date",
                '' AS "Venue",
                s.section AS "Section",
                s.row_name AS "Row",
                s.seat AS "Seat",
                COALESCE(
                    NULLIF(TRIM(s.submitted_barcode), ''),
                    NULLIF(TRIM(s.expected_barcode), '')
                ) AS "Barcodes"
            FROM seats s
            JOIN events e ON e.id = s.event_id
            WHERE COALESCE(
                NULLIF(TRIM(s.submitted_barcode), ''),
                NULLIF(TRIM(s.expected_barcode), '')
            ) IS NOT NULL
            """
        ).fetchall()
    finally:
        conn.close()
    out: list[dict] = []
    for row in raw:
        bc = str(row["Barcodes"] or "").strip()
        if _junk_barcode(bc):
            continue
        out.append({k: row[k] for k in row.keys()})
    return out


def _vl_inventory_stock_rows() -> list[dict]:
    """Barcodes from vl_inventory.db (VL bot ticket stock)."""
    try:
        import vl_inventory_db as vldb
    except ImportError:
        return []
    out: list[dict] = []
    for row in vldb.export_stock():
        bc = str(row["barcode"] or "").strip()
        if _junk_barcode(bc):
            continue
        out.append(
            {
                "Event Name": row["event_name"] or "",
                "Event Date": row["event_date"] or "",
                "Venue": row["venue"] or "",
                "Section": row["section"] or "",
                "Row": row["row_name"] or "",
                "Seat": row["seat"] or "",
                "Barcodes": bc,
                "Email": row["email"] or "",
                "Password": row["password"] or "",
            }
        )
    return out


def _fulfill_file_stock_df() -> pd.DataFrame:
    try:
        from vl_fulfill_stock_db import export_fulfill_stock

        rows = export_fulfill_stock()
    except ImportError:
        return prep_df(pd.DataFrame(columns=["Section", "Row", "Seat", "Barcodes", "Event Date", "Venue"]))
    if not rows:
        return prep_df(pd.DataFrame(columns=["Section", "Row", "Seat", "Barcodes", "Event Date", "Venue"]))
    df = prep_df(pd.DataFrame(rows))
    df["_fulfill_file"] = 1
    return df


def load_vl_stock_df() -> pd.DataFrame:
    """Fulfill-file DB (priority) + VL inventory + TM worker + optional local files."""
    from fulfill_vl_all_unfulfilled import load_stock_df

    parts: list[pd.DataFrame] = []
    ff = _fulfill_file_stock_df()
    if ff is not None and len(ff):
        parts.append(ff)
    extras: list[dict] = []
    extras.extend(_vl_inventory_stock_rows())
    extras.extend(_bot_db_stock_rows())
    if extras:
        parts.append(prep_df(pd.DataFrame(extras)))
    file_df = load_stock_df()
    if file_df is not None and len(file_df):
        parts.append(file_df)
    if not parts:
        return prep_df(pd.DataFrame(columns=["Section", "Row", "Seat", "Barcodes", "Event Date", "Venue"]))
    if len(parts) == 1:
        return parts[0]
    return prep_df(pd.concat(parts, ignore_index=True))


def _use_proxy() -> bool:
    return os.environ.get("VL_NO_PROXY", "").strip().lower() not in ("1", "true", "yes")


def _shared_vl_session():
    s = vl_load_session(use_proxy=_use_proxy())
    s.headers.update(
        {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": APP_BASE,
            "Referer": f"{APP_BASE}/v2/OrderManager",
        }
    )
    return s


def _worker_session():
    s = getattr(_thread_sessions, "session", None)
    if s is None:
        s = _shared_vl_session()
        fv.validate_session(s)
        _thread_sessions.session = s
    return s


def run_autofulfill_all_unfulfilled(*, sleep_sec: float = 0.2, on_progress=None) -> dict:
    """
    Scan all open unfulfilled mobile VL orders and fulfill using load_vl_stock_df().
    Returns summary dict with ok, fail, targets, stock_rows, results.
    """
    import time

    from _check_vl_fulfillable_all import all_open_orders
    from fulfill_vl_all_unfulfilled import _likely_unfulfilled, collect_targets
    from vl_autofulfill_tried import filter_new_targets, record_attempt, tried_count, TRIED_PATH

    os.environ.setdefault("VL_AUTOFULFILL_RETRY_FAILED", "1")

    def _p(msg: str) -> None:
        if on_progress:
            try:
                on_progress(msg)
            except Exception:
                pass

    _p("Loading VL session (saved cookies)…")
    t0 = time.time()
    session = _shared_vl_session()
    fv.validate_session(session)
    # Workers reuse the same in-memory cookie session via vl_auth.login().
    _thread_sessions.session = session
    _p("Loading barcode stock…")
    df = load_vl_stock_df()
    _p("Scanning open Victory Live orders…")
    scan_meta: dict = {}
    orders = all_open_orders(session, on_progress=_p, meta=scan_meta)
    _p(f"Found {len(orders)} open orders — checking which need barcodes…")
    mobile_candidates = [
        o for o in orders if o.get("IsMobileEnabled") and _likely_unfulfilled(o)
    ]
    targets = collect_targets(session, orders, on_progress=_p)
    all_targets = len(targets)
    targets, skipped_tried = filter_new_targets(targets)
    if skipped_tried:
        _p(f"Skipping {skipped_tried} already attempted (see {TRIED_PATH.name})")
    results: list[dict] = []
    ok = fail = done = 0
    n = len(targets)
    prog_lock = threading.Lock()
    if all_targets == 0:
        _p("No unfulfilled mobile orders to fulfill.")
    elif n == 0:
        _p(f"All {all_targets} target(s) were attempted before — nothing new.")
    else:
        _p(f"Fulfilling {n} new order(s) ({skipped_tried} skipped) · {AUTOFULFILL_WORKERS} workers…")

    def _fulfill_one(order: dict) -> dict:
        inv = order.get("InvoiceNumber")
        try:
            ws = _worker_session()
            success, msg = fv.fulfill_order_with_fallback(ws, order, df)
            row = {
                "invoice": inv,
                "rex": order.get("RexOrderId"),
                "event": (order.get("ProductionName") or "")[:80],
                "success": success,
                "message": msg,
            }
        except Exception as exc:
            row = {
                "invoice": inv,
                "rex": order.get("RexOrderId"),
                "event": (order.get("ProductionName") or "")[:80],
                "success": False,
                "message": str(exc),
            }
        if sleep_sec > 0:
            time.sleep(sleep_sec)
        return row

    workers = min(AUTOFULFILL_WORKERS, n) if n else 1
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_fulfill_one, o) for o in targets]
        for fut in as_completed(futures):
            row = fut.result()
            record_attempt(row)
            results.append(row)
            with prog_lock:
                done += 1
                if row.get("success"):
                    ok += 1
                else:
                    fail += 1
                    inv = row.get("invoice")
                    _p(f"FAIL {inv}: {str(row.get('message') or '')[:160]}")
                _p(f"Fulfilling {done}/{n} · ok {ok} fail {fail}")

    elapsed = round(time.time() - t0, 1)
    return {
        "ok": ok,
        "fail": fail,
        "open_orders": len(orders),
        "targets": all_targets,
        "targets_new": n,
        "skipped_tried": skipped_tried,
        "tried_total": tried_count(),
        "tried_file": str(TRIED_PATH),
        "mobile_candidates": len(mobile_candidates),
        "scan_windows": scan_meta.get("scan_windows"),
        "orders_merged_from_db": scan_meta.get("orders_merged_from_db", 0),
        "stock_rows": len(df),
        "fulfill_file_rows": int(df["_fulfill_file"].fillna(0).astype(int).sum())
        if "_fulfill_file" in df.columns
        else 0,
        "workers": workers,
        "elapsed_sec": elapsed,
        "results": results,
    }


def fulfill_victory_live_order(invoice_id: str) -> tuple[bool, str]:
    """
    Login (proxy), find VL order by invoice, match barcodes from stock, fulfill API.
    """
    inv = str(invoice_id).strip()
    session = _shared_vl_session()
    fv.validate_session(session)
    order = _find_order(session, inv)
    if not order:
        return False, f"Invoice {inv} not found on Victory Live"
    if not order.get("IsMobileEnabled"):
        return False, "Order is not mobile-enabled on Victory Live"
    df = load_vl_stock_df()
    return fv.fulfill_order(session, order, df)
