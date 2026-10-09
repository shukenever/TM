"""Purchase Manager / season-seat fallbacks for VL mobile fulfill."""
from __future__ import annotations

import json
import time
from datetime import date, timedelta

from vl_auth import APP_BASE

try:
    from vl_listing_api import find_matching_po, submit_mapping
except ImportError:
    find_matching_po = None  # type: ignore
    submit_mapping = None  # type: ignore


def _mapping_search_production_id(session, po_id: int, po: dict) -> int | None:
    params_list = [
        {"PrimaryPurchaseOrderId": po_id},
        {"VenueName": po.get("VenueName")},
        {"ProductionName": po.get("ProductionName")},
        {
            "VenueName": po.get("VenueName"),
            "ProductionName": po.get("ProductionName"),
            "ProductionDate": po.get("ProductionDate"),
        },
    ]
    for params in params_list:
        r = session.get(f"{APP_BASE}/api/purchase/mapping/search", params=params, timeout=60)
        if r.status_code != 200:
            continue
        data = r.json().get("Data") or []
        if not data:
            continue
        for item in data:
            pid = item.get("ProductionId") or item.get("Id")
            if pid:
                return int(pid)
    return None


def try_purchase_mapping_for_order(session, order: dict) -> bool:
    """Link a Purchase Manager PO to the sell order (venue mapping)."""
    rid = order.get("RexOrderId")
    inv = order.get("InvoiceNumber")
    pos_id = order.get("SourcePosExchangeId")
    print(f"  PM mapping Inv {inv} pos={pos_id}")

    po = None
    if find_matching_po is not None:
        seats = str(order.get("Seats") or "").strip()
        start_seat = seats.split("-")[0].strip() if seats else None
        for lookback in (3, 14, 45):
            po = find_matching_po(
                session,
                production_name=str(order.get("ProductionName") or ""),
                venue=str(order.get("VenueName") or ""),
                section=str(order.get("Section") or ""),
                row=str(order.get("Row") or ""),
                start_seat=start_seat,
                lookback_days=lookback,
            )
            if po:
                break

    if not po:
        r = session.get(
            f"{APP_BASE}/api/purchase/purchaseOrders",
            params={
                "OrderDateBegin": (date.today() - timedelta(days=120)).isoformat(),
                "OrderDateEnd": date.today().isoformat(),
                "page": 1,
                "pageSize": 250,
            },
            timeout=90,
        )
        if not r.ok:
            return False
        pos = r.json().get("Data", {}).get("PurchaseOrders") or []
        for p in pos:
            if pos_id and str(p.get("SourcePosExchangeId") or "") == str(pos_id):
                po = p
                break
        if not po:
            sec = str(order.get("Section") or "").upper()
            row = str(order.get("Row") or "")
            for p in pos:
                for tg in p.get("TicketGroups") or []:
                    if str(tg.get("Section") or "").upper() in sec or sec in str(tg.get("Section") or "").upper():
                        if str(tg.get("Row") or "") == row:
                            po = p
                            break
                if po:
                    break

    if not po:
        print("  no matching PO")
        return False

    po_id = po.get("PrimaryPurchaseOrderId")
    print(f"  PO {po_id}: {(po.get('ProductionName') or '')[:40]}")

    production_id = _mapping_search_production_id(session, int(po_id), po)
    if not production_id:
        print("  no ProductionId from mapping search")
        return False

    if submit_mapping is not None:
        submit_mapping(session, production_id, int(po_id))
    else:
        r = session.post(
            f"{APP_BASE}/api/purchase/mapping/submit",
            json={"ProductionId": production_id, "PrimaryPurchaseOrderId": po_id},
            timeout=60,
        )
        if r.status_code != 200:
            print(f"  mapping/submit failed {r.status_code}")
            return False

    for payload in (
        {"SellOrderId": rid, "PrimaryPurchaseOrderId": po_id},
        {"sellOrderId": rid, "PrimaryPurchaseOrderId": po_id},
    ):
        lr = session.post(f"{APP_BASE}/api/orders/selectMobileTickets/", json=payload, timeout=60)
        if lr.status_code == 200:
            print(f"  selectMobileTickets ok")
            break

    time.sleep(0.5)
    return True


def try_comple_mobile_transfer(session, rid: int) -> tuple[bool, str]:
    """VL UI 'found tickets' / Purchase Manager transfer (not barcode queue)."""
    r = session.get(
        f"{APP_BASE}/api/orders/compleMobileTransfer",
        params={"orderId": rid},
        timeout=90,
    )
    if r.status_code != 200:
        return False, f"compleMobileTransfer HTTP {r.status_code}: {(r.text or '')[:120]}"
    try:
        body = r.json()
    except json.JSONDecodeError:
        return False, "compleMobileTransfer: non-JSON response"
    data = body.get("Data") or {}
    if data.get("IsSuccessful"):
        return True, str(data.get("Message") or "compleMobileTransfer OK")
    return False, str(data.get("Message") or body)[:200]


def pm_error_message(msg: str) -> bool:
    m = (msg or "").lower()
    return any(
        x in m
        for x in (
            "purchase manag",
            "season seat",
            "barcodes detected",
            "unable to transfer",
        )
    )
