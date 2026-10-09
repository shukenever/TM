"""
Fulfill Victory Live mobile orders: barcodes from okaysec.txt + tm_claimed_links.txt + barcodeTransferMobileFulfill.
"""
import argparse
import base64
import json
import os
import re
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from vl_auth import APP_BASE

BASE = APP_BASE
OKAYSEC_PATH = Path(__file__).resolve().parent / "okaysec.txt"


def _default_date_range() -> tuple[str, str]:
    """Order create-date window (VL rejects huge event-date spans)."""
    now = datetime.now()
    start = now - timedelta(days=int(os.environ.get("VL_SEARCH_DAYS_BACK", "89")))
    return (
        start.strftime("%m/%d/%Y 12:00:00 am"),
        now.strftime("%m/%d/%Y 11:59:59 pm"),
    )


DATE_FROM, DATE_TO = _default_date_range()


def load_session(use_proxy=True):
    """Same cookie session as /list, sync, and listings (vl_inventory_sync.load_session)."""
    from vl_inventory_sync import load_session as _vl_load_session

    s = _vl_load_session(use_proxy=use_proxy)
    s.headers.update(
        {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": BASE,
            "Referer": f"{BASE}/v2/OrderManager",
        }
    )
    return s


def validate_session(session):
    r = session.get(f"{BASE}/api/security/profile", timeout=15)
    ct = r.headers.get("Content-Type", "")
    if "json" not in ct:
        raise RuntimeError(
            "SESSION EXPIRED - API returned login page, not JSON.\n"
            "Re-run to login again via vl_auth."
        )
    r.raise_for_status()
    return True


def clean_section(s):
    s = str(s).strip()
    for prefix in (
        "Upper Concourse ",
        "Lower Concourse ",
        "Middle ",
        "Upper ",
        "Lower Level ",
        "Lower ",
        "Grandstand ",
        "Section ",
        "Floor ",
        "FLOOR ",
    ):
        s = s.replace(prefix, "")
    s = re.sub(r"^SEC", "", s, flags=re.I)
    s = re.sub(r"\s+", "", s)
    return s.strip()


def _barcode_from_secure_token(token: str) -> str:
    raw = str(token or "").strip()
    if raw.lower().startswith("securetoken:"):
        raw = raw.split(":", 1)[1].strip()
    if not raw or not raw.startswith("ey"):
        return ""
    try:
        padded = raw + "=" * (-len(raw) % 4)
        try:
            decoded = base64.b64decode(padded).decode("utf-8")
        except Exception:
            decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
        data = json.loads(decoded)
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    b = str(data.get("b") or "").strip()
    if not b or b.lower() in ("demo", "regen"):
        return ""
    return b


def barcode_usable(bc: str | None) -> bool:
    s = clean_barcode(str(bc or "").strip()) if bc else ""
    if not s or len(s) <= 2:
        return False
    low = s.lower()
    if low in {
        "not",
        "nobarc",
        "no barc",
        "none",
        "n/a",
        "no barcode",
        "securetoken",
        "securetoken:",
        "token",
    }:
        return False
    if low.startswith("securetoken:") and "ey" not in low:
        return False
    return True


def clean_barcode(bc):
    bc = str(bc or "").strip()
    if not bc:
        return ""
    low = bc.lower()
    if low in ("securetoken", "securetoken:", "token") or low.startswith("securetoken:"):
        extracted = _barcode_from_secure_token(bc)
        if extracted:
            bc = extracted
        elif low.startswith("securetoken:"):
            return ""
    elif bc.startswith("ey"):
        extracted = _barcode_from_secure_token(bc)
        if extracted:
            bc = extracted
    if bc.endswith("C") or bc.endswith("a"):
        return bc[:-1]
    return bc


def _fulfill_strict_stock() -> bool:
    return os.environ.get("VL_FULFILL_LOOSE_STOCK", "").strip().lower() not in (
        "1",
        "true",
        "yes",
    )


def _fulfill_replace_vl_barcodes() -> bool:
    return os.environ.get("VL_FULFILL_REPLACE_VL", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def find_barcode(
    section,
    row,
    seat,
    df,
    allow_adjacent=True,
    order=None,
    *,
    strict: bool | None = None,
):
    if strict is None:
        strict = _fulfill_strict_stock()
    if strict:
        allow_adjacent = False
    if "_sec" in df.columns:
        try:
            from list_unfulfilled import parse_event_date, seat_match

            event_date = None
            venue = None
            if order:
                event_date = parse_event_date(order.get("ProductionDateTime") or "")
                venue = order.get("VenueName")
            hit = seat_match(
                df,
                section,
                row,
                seat,
                event_date,
                venue,
                event_name=(order or {}).get("ProductionName"),
                strict=strict,
            )
            if hit is not None:
                bc = hit.get("_bc") or hit.get("Barcodes")
                seat_s = str(seat).strip()
                try:
                    sn = int(seat_s)
                except ValueError:
                    sn = seat_s
                return clean_barcode(bc), sn
        except Exception:
            pass
    sc = clean_section(section)
    seat_s = str(seat).strip()
    m = df[
        (df["Section"].astype(str).str.strip() == sc)
        & (df["Row"].astype(str).str.strip().str.upper() == str(row).upper())
        & (df["Seat"].astype(str).str.strip() == seat_s)
    ]
    if len(m):
        return clean_barcode(m.iloc[0]["Barcodes"]), int(seat_s)
    if allow_adjacent:
        try:
            sn = int(seat_s)
            for off in (1, -1, 2, -2):
                adj = sn + off
                m = df[
                    (df["Section"].astype(str).str.strip() == sc)
                    & (df["Row"].astype(str).str.strip().str.upper() == str(row).upper())
                    & (df["Seat"].astype(str).str.strip() == str(adj))
                ]
                if len(m):
                    return clean_barcode(m.iloc[0]["Barcodes"]), adj
        except ValueError:
            pass
    return None, None


def search_orders(session, date_from: str | None = None, date_to: str | None = None, *, search_event_date: bool | None = None):
    if os.environ.get("VL_DATE_FROM"):
        date_from = date_from or os.environ["VL_DATE_FROM"]
    if os.environ.get("VL_DATE_TO"):
        date_to = date_to or os.environ["VL_DATE_TO"]
    date_from = date_from or DATE_FROM
    date_to = date_to or DATE_TO
    if search_event_date is None:
        search_event_date = os.environ.get("VL_SEARCH_EVENT_DATE", "").lower() in ("1", "true", "yes")
    all_orders: list = []
    page = 1
    total = None
    while True:
        params = [
            ("IsInHandOnly", "false"),
            ("Page", str(page)),
            ("PageSize", "100"),
            ("RowSequence", "0"),
            ("SearchDateFrom", date_from),
            ("SearchDateTo", date_to),
            ("SearchEventDate", "true" if search_event_date else "false"),
            ("SearchText", ""),
            ("ShowPosOrders", "true"),
            ("SortDescending", "true"),
            ("SortField", "CreateDateTime"),
            ("page", str(page)),
            ("pageSize", "100"),
            ("skip", str((page - 1) * 100)),
            ("sort", '{"field":"CreateDateTime","dir":"desc"}'),
            ("take", "100"),
        ]
        r = session.get(f"{BASE}/api/orders/search", params=params, timeout=90)
        if r.status_code != 200:
            raise RuntimeError(f"orders/search HTTP {r.status_code}: {(r.text or '')[:300]}")
        data = r.json().get("Data") or {}
        batch = data.get("Orders") or []
        all_orders.extend(batch)
        total = data.get("TotalOrders") or len(all_orders)
        if len(all_orders) >= total or not batch:
            break
        page += 1
        if page > 80:
            break
    return all_orders


def search_orders_all_chunks(session, *, search_event_date: bool = False, chunk_days: int = 89):
    """VL allows max ~90 days per search — walk backward in chunks."""
    end = datetime.now()
    chunks_back = int(os.environ.get("VL_SEARCH_CHUNKS", "4"))
    seen: set = set()
    merged: list = []
    for i in range(chunks_back):
        chunk_end = end - timedelta(days=i * chunk_days)
        chunk_start = chunk_end - timedelta(days=chunk_days)
        dfrom = chunk_start.strftime("%m/%d/%Y 12:00:00 am")
        dto = chunk_end.strftime("%m/%d/%Y 11:59:59 pm")
        print(f"  Fetch chunk {i + 1}/{chunks_back}: {dfrom} — {dto}")
        try:
            batch = search_orders(session, dfrom, dto, search_event_date=search_event_date)
        except RuntimeError as e:
            if "400" in str(e):
                print(f"    skip chunk: {e}")
                continue
            raise
        for o in batch:
            rid = o.get("RexOrderId")
            if rid in seen:
                continue
            seen.add(rid)
            merged.append(o)
    return merged


def ticket_payload(ticket, barcode):
    return {
        "TicketGroupUploadId": ticket["TicketGroupUploadId"],
        "TicketUploadId": ticket["TicketUploadId"],
        "Seat": str(ticket["Seat"]),
        "Section": ticket["Section"],
        "Row": ticket["Row"],
        "Barcode": barcode,
        "HasPdf": ticket.get("HasPdf", False),
        "IsPlaceholder": ticket.get("IsPlaceholder", False),
        "DocumentId": ticket.get("DocumentId"),
        "HasPosSaveFailure": ticket.get("HasPosSaveFailure", False),
        "RequiresPosSave": False,
        "SeasonSeatId": ticket.get("SeasonSeatId"),
        "RemoveBarcodeFromPos": False,
        "PrimaryPurchaseTicketId": ticket.get("PrimaryPurchaseTicketId"),
        "PrimaryTicketId": ticket.get("PrimaryTicketId"),
        "PrimarySourceId": ticket.get("PrimarySourceId"),
        "HasTransferUrl": ticket.get("HasTransferUrl", False),
        "TransferUrl": ticket.get("TransferUrl"),
    }


def _needs_pm_transfer(ma_data: dict, tickets: list) -> bool:
    if ma_data.get("AllTicketsFound"):
        return True
    if ma_data.get("IsPurchaseEnabled"):
        return True
    for t in tickets:
        if t.get("SeasonSeatId") or t.get("PrimaryPurchaseTicketId"):
            return True
    return False


def fulfill_order_with_fallback(session, order, df):
    """Barcode fulfill with Purchase Manager / compleMobileTransfer retries."""
    from vl_fulfill_pm import pm_error_message, try_comple_mobile_transfer, try_purchase_mapping_for_order

    rid = order["RexOrderId"]
    ma = session.get(f"{BASE}/api/orders/mobileAttributes", params={"sellOrderId": rid}, timeout=30)
    ma.raise_for_status()
    ma_data = ma.json().get("Data") or {}
    tickets = ma_data.get("Tickets") or []
    if ma_data.get("AllTicketsFound") and tickets:
        ok, msg = try_comple_mobile_transfer(session, rid)
        if ok:
            return True, msg

    success, msg = fulfill_order(session, order, df, ma_data=ma_data)
    if success:
        return True, msg
    if not pm_error_message(msg):
        return False, msg

    print(f"  PM fallback after: {msg[:80]}")
    try_purchase_mapping_for_order(session, order)
    ok, msg2 = try_comple_mobile_transfer(session, rid)
    if ok:
        return True, msg2
    success2, msg3 = fulfill_order(session, order, df)
    if success2:
        return True, msg3
    return False, msg3 or msg2 or msg


def fulfill_order(session, order, df, *, ma_data: dict | None = None):
    rid = order["RexOrderId"]
    inv = order.get("InvoiceNumber") or "N/A"
    pos = order.get("SourcePosExchangeId")

    print(f"\n{'='*90}")
    print(f"Inv {inv} | Order {rid} | {order.get('ProductionName','')[:30]}")
    print(f"Sec {order.get('Section')} Row {order.get('Row')} Seats {order.get('Seats')}")
    print(f"{'='*90}")

    # Step 1: mobileAttributes
    if ma_data is None:
        ma = session.get(f"{BASE}/api/orders/mobileAttributes", params={"sellOrderId": rid}, timeout=30)
        ma.raise_for_status()
        ma_data = ma.json().get("Data") or {}
    tickets = ma_data.get("Tickets") or []
    if not tickets:
        return False, "no tickets"
    use_pm_fulfill = _needs_pm_transfer(ma_data, tickets)

    empty = [t for t in tickets if not barcode_usable(t.get("Barcode"))]
    if not empty:
        print("  Barcodes already set - calling fulfill only")
    else:
        print(f"  {len(empty)}/{len(tickets)} tickets missing barcodes")

    # Step 2: tmandata
    if pos:
        session.get(f"{BASE}/api/orders/tmandata", params={"sellOrderId": rid, "sourcePosExchangeId": pos}, timeout=30)

    # Step 3: barcodes — keep VL when already set; stock only fills empty seats (strict match)
    strict_stock = _fulfill_strict_stock()
    replace_vl = _fulfill_replace_vl_barcodes()
    payload = []
    seen_bc: dict[str, str] = {}
    for t in tickets:
        vl_bc = t.get("Barcode")
        vl_clean = clean_barcode(vl_bc) if barcode_usable(vl_bc) else None
        found, src = find_barcode(
            t.get("Section") or order.get("Section"),
            t.get("Row") or order.get("Row"),
            t.get("Seat"),
            df,
            order=order,
            strict=strict_stock,
        )
        seat_label = str(t.get("Seat"))
        if vl_clean:
            if (
                replace_vl
                and found
                and clean_barcode(found) != vl_clean
            ):
                bc = found
                print(f"    Seat {seat_label}: {bc} (stock replaces VL)")
            else:
                bc = vl_clean
                if found and clean_barcode(found) != vl_clean:
                    print(f"    Seat {seat_label}: keep VL barcode (ignored stock mismatch)")
                else:
                    print(f"    Seat {seat_label}: {bc} (on VL)")
        elif found:
            bc = found
            try:
                seat_n = int(seat_label)
                src_n = int(src) if src is not None else seat_n
                note = f" (from seat {src})" if src_n != seat_n else ""
            except (TypeError, ValueError):
                note = ""
            print(f"    Seat {seat_label}: {bc}{note} (from stock)")
        else:
            return False, (
                f"no strict stock match for seat {seat_label} "
                f"sec {t.get('Section')} row {t.get('Row')}"
            )
        prev_seat = seen_bc.get(bc)
        if prev_seat and prev_seat != seat_label:
            return False, f"duplicate barcode {bc} for seats {prev_seat} and {seat_label}"
        seen_bc[bc] = seat_label
        payload.append(ticket_payload(t, bc))

    def _ticket_bc(ticket: dict) -> str:
        b = ticket.get("Barcode")
        return clean_barcode(b) if b else ""

    needs_update = any(
        clean_barcode(p["Barcode"]) != _ticket_bc(tickets[i])
        for i, p in enumerate(payload)
    )
    if needs_update:
        r = session.post(f"{BASE}/api/tickets/barcodes/update", json={"Tickets": payload}, timeout=90)
        if r.status_code != 200:
            return False, f"update failed {r.status_code}: {r.text[:150]}"
        print("  > barcodes/update OK")
        time.sleep(0.5)

        ma2 = session.get(f"{BASE}/api/orders/mobileAttributes", params={"sellOrderId": rid}, timeout=30)
        if "json" not in ma2.headers.get("Content-Type", ""):
            return False, "session expired mid-run"
        still_empty = [
            t for t in ma2.json()["Data"]["Tickets"] if not barcode_usable(t.get("Barcode"))
        ]
        if still_empty:
            return False, f"barcodes still empty: seats {[t['Seat'] for t in still_empty]}"

    # Step 4: fulfill (PM-linked orders use compleMobileTransfer, not barcode queue)
    if use_pm_fulfill:
        from vl_fulfill_pm import try_comple_mobile_transfer

        ok, pm_msg = try_comple_mobile_transfer(session, rid)
        if not ok:
            return False, pm_msg
    else:
        r = session.post(f"{BASE}/api/orders/barcodeTransferMobileFulfill", json={"SellOrderId": rid}, timeout=90)
        if r.status_code != 200:
            return False, f"fulfill HTTP {r.status_code}"
        body = r.json()
        data = body.get("Data") or {}
        if not data.get("IsSuccessful"):
            pm_msg = str(data.get("Message") or body)[:200]
            return False, pm_msg or f"fulfill rejected: {body}"

    time.sleep(0.5)
    updated = next((o for o in search_orders(session) if o["RexOrderId"] == rid), order)
    msg = updated.get("StatusMessage") or ""
    btn = updated.get("ButtonToShow")
    os_key = (updated.get("OrderStatus") or {}).get("Key")
    print(f"  > Done: OrderStatus={os_key} btn={btn}")
    if msg:
        print(f"  > Msg: {msg[:70]}")

    if "not matched" in msg.lower() or "unable to transfer" in msg.lower():
        return False, msg[:80]
    if os_key == "Fulfilled" or "Tickets Acquired" in msg or btn == "mobileTransfer":
        return True, msg or os_key
    return True, f"updated btn={btn}"


def collect_targets(session, orders):
    from list_unfulfilled import is_unfulfilled

    targets = []
    for o in orders:
        if not o.get("IsMobileEnabled"):
            continue
        try:
            ma = session.get(
                f"{BASE}/api/orders/mobileAttributes",
                params={"sellOrderId": o["RexOrderId"]},
                timeout=20,
            ).json()["Data"]
            tickets = ma.get("Tickets", [])
            if not tickets:
                continue
            if is_unfulfilled(o, tickets):
                targets.append(o)
        except Exception:
            pass
    return targets


def main():
    ap = argparse.ArgumentParser(description="Fulfill Victory Live mobile orders")
    ap.add_argument("--from", dest="date_from", default=None, help="SearchDateFrom")
    ap.add_argument("--to", dest="date_to", default=None, help="SearchDateTo")
    ap.add_argument("--no-proxy", action="store_true", help="Skip Lightning proxy")
    ap.add_argument("--event-date", action="store_true", help="Search by event date (default: order create date)")
    ap.add_argument("--dry-run", action="store_true", help="List targets only")
    args = ap.parse_args()
    search_ev = args.event_date

    session = load_session(use_proxy=not args.no_proxy)
    validate_session(session)
    from fulfill_vl_all_unfulfilled import load_stock_df

    df = load_stock_df()
    print(f"Stock inventory rows: {len(df)} (okaysec.txt + tm_claimed_links.txt)")
    dfrom = args.date_from or DATE_FROM
    dto = args.date_to or DATE_TO
    mode = "event date" if search_ev else "order create date"
    print(f"Session OK | Search {mode}: {dfrom} — {dto}\n")

    orders = search_orders_all_chunks(session, search_event_date=search_ev)
    print(f"Orders in range (all pages): {len(orders)}")
    targets = collect_targets(session, orders)
    print(f"Mobile unfulfilled to process: {len(targets)}")
    if args.dry_run:
        for o in targets:
            print(
                f"  Inv {o.get('InvoiceNumber')} | {o.get('ProductionName','')[:40]} | "
                f"btn={o.get('ButtonToShow')} | {(o.get('OrderStatus') or {}).get('Key')}"
            )
        return

    ok = fail = 0
    failed_list = []
    for o in targets:
        try:
            success, msg = fulfill_order(session, o, df)
            if success:
                ok += 1
            else:
                fail += 1
                failed_list.append((o.get("InvoiceNumber"), msg))
        except Exception as e:
            fail += 1
            failed_list.append((o.get("InvoiceNumber"), str(e)))
            print(traceback.format_exc()[:200])
        time.sleep(0.8)

    print(f"\n{'='*90}")
    print(f"SUCCESS: {ok} | FAILED: {fail}")
    if failed_list:
        print("\nFailed:")
        for inv, msg in failed_list:
            print(f"  Inv {inv}: {msg}")


if __name__ == "__main__":
    main()
