"""StageFront AutoPricer flow (HAR): SetListingRules + optional price push + sharing."""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from .client import StagefrontClient, StagefrontConfig
except ImportError:
    from client import StagefrontClient, StagefrontConfig

log = logging.getLogger("stagefront.autopricer")

RESULTS_PATH = Path(__file__).resolve().parent / "autopricer_results.jsonl"


@dataclass
class AutoPricerConfig:
    amount_under: float = 0.11
    notes: str = "AutoPricer 2.0"
    allow_price_increase: bool = True
    use_default_splits: bool = True
    trait_exclusions: str = "1,102"
    floor_pct_of_sg: float = 0.88
    ceiling_mult: float = 3.6
    min_floor: float = 10.0
    default_ceiling: float = 5000.0
    force_reprice: bool = True


def _sg_price(row: dict[str, Any]) -> float | None:
    v = row.get("SG_Price")
    if v is None or float(v) < 0:
        return None
    return float(v)


def _derive_floor_ceiling(row: dict[str, Any], ap: AutoPricerConfig) -> tuple[float, float]:
    floor = row.get("Floor_Price")
    ceiling = row.get("Ceiling_Price")
    if floor is not None and ceiling is not None:
        return float(floor), float(ceiling)

    rules = row.get("_listing_rules") or {}
    if rules.get("FloorPrice") and rules.get("CeilingPrice"):
        return float(rules["FloorPrice"]), float(rules["CeilingPrice"])

    price = float(row.get("Item_Price") or 0)
    sg = _sg_price(row)
    base = sg or price or ap.min_floor
    floor_val = max(ap.min_floor, round(base * ap.floor_pct_of_sg, 2))
    if price > 0:
        floor_val = min(floor_val, round(price * 0.95, 2))
    ceiling_val = round(max(price, base) * ap.ceiling_mult, 2) if base else ap.default_ceiling
    ceiling_val = max(ceiling_val, floor_val + 1)
    return floor_val, ceiling_val


def build_set_rules_payload(
    row: dict[str, Any],
    venue_id: int,
    ap: AutoPricerConfig,
) -> dict[str, Any]:
    lid = int(row["Listing_ID"])
    section = str(row.get("Section") or "")
    row_name = str(row.get("Row") or "")
    qty = int(row.get("Quantity") or 1)
    floor, ceiling = _derive_floor_ceiling(row, ap)
    return {
        "listingIdFloors": [{"ListingId": lid, "FloorPrice": floor, "CeilingPrice": ceiling}],
        "rules": {
            "CompareToEverything": False,
            "FloorNotification": False,
            "CeilingNotification": False,
            "AllowPriceIncrease": ap.allow_price_increase,
            "CompareAgainstOwnInventory": False,
            "FloorPrice": floor,
            "CeilingPrice": ceiling,
            "Notes": ap.notes,
            "TicketSplit": str(qty),
            "RowRangeStart": None,
            "RowRangeEnd": None,
            "AllRows": False,
            "Position": None,
            "AmountUnder": ap.amount_under,
            "MinutesPerCycle": None,
            "Zones": None,
            "Sections": [section],
            "Rows": [row_name],
            "TraitExclusions": ap.trait_exclusions,
            "Exclude_Outliers": 0,
            "NoComparablesNotification": False,
            "Delivery_Exclusions": "",
            "PctUnder": None,
            "UseDefaultSplits": ap.use_default_splits,
            "IgnoredListings": [],
            "Ignored_Listings": [],
            "SuggestedSection": None,
            "SuggestedSections": [],
            "ListingId": lid,
            "SeatGeekListingId": row.get("SeatGeek_Listing_ID"),
            "MasterRuleId": None,
            "venueId": venue_id,
        },
        "ignores": [],
    }


def _append_result(record: dict[str, Any]) -> None:
    with threading.Lock():
        with RESULTS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")


def apply_sharing(client: StagefrontClient, venue_id: int, listing_ids: list[int]) -> bool:
    rid = client.sharing_rule_id(venue_id)
    if not rid or not listing_ids:
        return False
    share = client.share_out_settings(rid)
    if not share:
        return False
    client.update_listings_sharing(listing_ids, share)
    return True


def price_from_sg_under(row: dict[str, Any], ap: AutoPricerConfig) -> float | None:
    """HAR step before SetListingRules: UpdateListingPrices at SG − AmountUnder."""
    sg = _sg_price(row)
    if sg and sg > 0:
        return max(round(sg - ap.amount_under, 2), 0.01)
    if ap.force_reprice:
        old = float(row.get("Item_Price") or 0)
        if old > 0:
            return max(round(old - ap.amount_under, 2), 0.01)
    return None


_thread_local = threading.local()


def _worker_client(cfg: StagefrontConfig, cookie: str, rule_id: int | None) -> StagefrontClient:
    c = getattr(_thread_local, "client", None)
    if c is None:
        c = StagefrontClient(cfg)
        c.set_cookie(cookie)
        if rule_id:
            c.set_default_sharing_rule_id(rule_id)
        _thread_local.client = c
    return c


def process_listing(
    cfg: StagefrontConfig,
    cookie: str,
    rule_id: int | None,
    row: dict[str, Any],
    venue_id: int,
    ap: AutoPricerConfig,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    client = _worker_client(cfg, cookie, rule_id)
    lid = int(row["Listing_ID"])
    event_id = int(row.get("Event_ID") or 0)
    rec: dict[str, Any] = {
        "listing_id": lid,
        "event_id": event_id,
        "section": row.get("Section"),
        "row": row.get("Row"),
        "qty": row.get("Quantity"),
        "old_price": float(row.get("Item_Price") or 0),
        "is_autopriced": bool(row.get("Is_AutoPriced")),
    }
    try:
        rules = client.get_json(f"/api/AutoPricer/GetListingRules?listingId={lid}") or {}
        row["_listing_rules"] = rules
    except Exception:
        row["_listing_rules"] = {}

    payload = build_set_rules_payload(row, venue_id, ap)
    rec["floor"] = payload["listingIdFloors"][0]["FloorPrice"]
    rec["ceiling"] = payload["listingIdFloors"][0]["CeilingPrice"]

    new_price = price_from_sg_under(row, ap)
    rec["target_price"] = new_price
    rec["priced"] = False
    if new_price is not None and not dry_run:
        if ap.force_reprice or rec["old_price"] <= 0:
            client.update_listing_prices(lid, new_price)
            rec["priced"] = True

    if dry_run:
        rec["status"] = "dry_run"
        return rec

    ok = client.post_json("/api/AutoPricer/SetListingRules", payload)
    rec["autopricer_set"] = bool(ok)
    rec["shared"] = apply_sharing(client, venue_id, [lid])
    rec["status"] = "ok" if rec.get("autopricer_set") else "rules_failed"
    _append_result(rec)
    return rec


def fetch_event_autopricer_rows(
    client: StagefrontClient,
    event_id: int,
    company: str,
) -> list[dict[str, Any]]:
    """One call per event — AutoPricer inventory rows (eligible listings)."""
    payload = {
        "EventFromDate": None,
        "EventToDate": None,
        "CategoryId": None,
        "EventHeadlinerId": None,
        "EventId": event_id,
        "VenueId": None,
        "ListingId": None,
        "IsAutoPriced": None,
        "IsAtFloor": None,
        "IsAtCeiling": None,
        "IsNoComparables": None,
        "IsError": None,
        "Sections": None,
        "Row": None,
        "Quantity": None,
        "AutoPricerUser": None,
        "CompanyName": company,
        "ForceRefresh": True,
        "page": 1,
        "startIndex": 0,
        "limit": 99999,
    }
    data = client.post_json("/api/AutoPricer/QueryInventory", payload) or {}
    return list(data.get("Inventory") or [])


def fetch_event_pricing_rows(
    client: StagefrontClient,
    event_id: int,
    company: str,
) -> list[dict[str, Any]]:
    """Fallback: pricing grid inventory merged by listing for listings missing from AP."""
    inv = client.query_event_inventory(event_id, company)
    by_lid: dict[int, dict[str, Any]] = {}
    for r in inv:
        lid = int(r["Listing_ID"])
        if lid not in by_lid:
            by_lid[lid] = {
                "Listing_ID": lid,
                "Event_ID": event_id,
                "Section": r.get("Section"),
                "Row": r.get("Row"),
                "Quantity": 0,
                "Item_Price": float(r.get("Item_Price") or 0),
                "Floor_Price": r.get("Floor_Price"),
                "Ceiling_Price": r.get("Ceiling_Price"),
                "SG_Price": -1.0,
                "Is_AutoPriced": r.get("Is_AutoPriced"),
                "SeatGeek_Listing_ID": r.get("SeatGeek_Listing_ID"),
            }
        by_lid[lid]["Quantity"] = int(by_lid[lid]["Quantity"]) + 1
    return list(by_lid.values())


def merge_event_listings(
    ap_rows: list[dict[str, Any]],
    pricing_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_lid = {int(r["Listing_ID"]): dict(r) for r in pricing_rows}
    for r in ap_rows:
        lid = int(r["Listing_ID"])
        base = by_lid.get(lid, {})
        merged = {**base, **r}
        by_lid[lid] = merged
    return list(by_lid.values())


def process_event(
    cfg: StagefrontConfig,
    cookie: str,
    rule_id: int | None,
    company: str,
    event: dict[str, Any],
    ap: AutoPricerConfig,
    *,
    listing_workers: int,
    dry_run: bool,
) -> list[dict[str, Any]]:
    client = _worker_client(cfg, cookie, rule_id)
    event_id = int(event["Event_ID"])
    venue_id = int(event.get("Venue_ID") or 0)
    name = (event.get("Event_Name") or "")[:60]

    ap_rows = fetch_event_autopricer_rows(client, event_id, company)
    pricing_rows = fetch_event_pricing_rows(client, event_id, company)
    rows = merge_event_listings(ap_rows, pricing_rows)
    if not rows:
        return [{"event_id": event_id, "status": "no_inventory", "event": name}]

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, listing_workers)) as pool:
        futs = [
            pool.submit(
                process_listing,
                cfg,
                cookie,
                rule_id,
                row,
                venue_id,
                ap,
                dry_run=dry_run,
            )
            for row in rows
        ]
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as exc:
                log.exception("listing failed on event %s", event_id)
                results.append({"status": "error", "error": str(exc)})

    ok = sum(1 for r in results if r.get("status") in ("ok", "dry_run"))
    ap_on = sum(1 for r in results if r.get("autopricer_set"))
    log.info(
        "event %s %s: %d listings, autopricer %d, ok %d",
        event_id,
        name,
        len(results),
        ap_on,
        ok,
    )
    return results
