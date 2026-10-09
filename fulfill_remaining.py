#!/usr/bin/env python3
"""Fulfill all remaining VL mobile orders Aug 21 - Sep 12."""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from fulfill_aug22_sep12 import (  # noqa: E402
    BARCODE_FIXES,
    DATE_FROM,
    DATE_TO,
    apply_barcode_fixes,
    count_fulfilled,
    order_needs_work,
    search_orders,
)
import fulfill_victory_live as fv  # noqa: E402
from vl_auth import APP_BASE  # noqa: E402

OUT_PATH = ROOT / "fulfill_remaining_results.json"

# widen to catch Aug 21 orders too
DATE_FROM_WIDE = "08/21/2026 12:00:00 am"
DATE_TO_WIDE = "09/12/2026 11:59:59 pm"


def search_orders_wide(session):
    r = session.get(
        f"{fv.BASE}/api/orders/search",
        params={
            "IsInHandOnly": "false",
            "Page": "1",
            "PageSize": "100",
            "SearchDateFrom": DATE_FROM_WIDE,
            "SearchDateTo": DATE_TO_WIDE,
            "SearchEventDate": "true",
            "SearchText": "",
            "ShowPosOrders": "true",
        },
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()["Data"]
    orders = data.get("Orders") or []
    print(f"orders search: TotalCount={data.get('TotalCount')} rows={len(orders)}")
    return orders


def try_purchase_mapping(session, order) -> bool:
    from vl_fulfill_pm import try_purchase_mapping_for_order

    return try_purchase_mapping_for_order(session, order)


def fulfill_one(session, order, df) -> tuple[bool, str]:
    apply_barcode_fixes(session, order)
    time.sleep(0.5)
    success, msg = fv.fulfill_order(session, order, df)
    if success:
        return True, msg
    if "purchase" in msg.lower() or "season seat" in msg.lower() or "barcodes detected" in msg.lower():
        if try_purchase_mapping(session, order):
            time.sleep(1)
            success2, msg2 = fv.fulfill_order_with_fallback(session, order, df)
            return success2, msg2
    return success, msg


def main() -> int:
    session = fv.load_session()
    fv.validate_session(session)
    df = pd.read_csv(fv.OKAYSEC_PATH, sep="\t", on_bad_lines="skip")
    print(f"Session OK | {DATE_FROM_WIDE} - {DATE_TO_WIDE}\n")

    before = search_orders_wide(session)
    fulfilled_before = count_fulfilled(before)

    targets = []
    for o in before:
        try:
            need, reason = order_needs_work(session, o)
            if need:
                targets.append({"order": o, "reason": reason})
        except Exception as e:
            print(f"skip Inv {o.get('InvoiceNumber')}: {e}")

    print(f"Need fulfillment: {len(targets)}")
    for t in targets:
        o = t["order"]
        print(
            f"  Inv {o.get('InvoiceNumber')} | {(o.get('ProductionName') or '')[:28]} | "
            f"Sec {o.get('Section')} Row {o.get('Row')} Seats {o.get('Seats')} | {t['reason']}"
        )

    if not targets:
        print("Nothing to do.")
        return 0

    ok = fail = 0
    results = []
    for t in targets:
        o = t["order"]
        inv = o.get("InvoiceNumber")
        try:
            success, msg = fulfill_one(session, o, df)
            ok += int(success)
            fail += int(not success)
            results.append(
                {"invoice": inv, "rex_order_id": o.get("RexOrderId"), "success": success, "message": msg}
            )
            print(f"Inv {inv}: {'OK' if success else 'FAIL'} - {msg[:80]}")
        except Exception as e:
            fail += 1
            results.append(
                {"invoice": inv, "rex_order_id": o.get("RexOrderId"), "success": False, "message": str(e)}
            )
            print(traceback.format_exc()[:250])
        time.sleep(0.8)

    after = search_orders_wide(session)
    newly = count_fulfilled(after) - fulfilled_before
    summary = {
        "fulfilled_before": fulfilled_before,
        "fulfilled_after": count_fulfilled(after),
        "newly_fulfilled": newly,
        "ok": ok,
        "fail": fail,
        "results": results,
    }
    OUT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nFulfilled: {fulfilled_before} -> {count_fulfilled(after)} (+{newly} new)")
    print(f"ok/fail: {ok}/{fail}")
    return 0 if newly > 0 else (1 if fail else 0)


if __name__ == "__main__":
    raise SystemExit(main())
