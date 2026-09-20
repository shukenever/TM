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
    comp = row.get("_comp_low")
    if comp is not None and float(comp) > 0:
        low = float(comp)
        floor_val = max(ap.min_floor, round(low * ap.floor_pct_of_sg, 2))
        ceiling_val = max(round(low * ap.ceiling_mult, 2), floor_val + 1)
        return floor_val, ceiling_val

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


def _listing_for_comps(row: dict[str, Any], company: str) -> dict[str, Any]:
    return {
        "listing_id": int(row["Listing_ID"]),
        "section": str(row.get("Section") or ""),
        "row": str(row.get("Row") or ""),
        "quantity": int(row.get("Quantity") or 1),
        "item_price": float(row.get("Item_Price") or 0),
        "company_name": str(row.get("Company_Name") or company),
    }


def _section_floor_price(section: str, section_mins: dict[str, float]) -> float | None:
    s = str(section or "").strip()
    if not s or not section_mins:
        return None
    if s in section_mins:
        return section_mins[s]
    for key, val in section_mins.items():
        if key.split()[0] == s or key.replace(" ", "") == s.replace(" ", ""):
            return val
    return None


def har_target_price(
    client: StagefrontClient,
    event_id: int,
    row: dict[str, Any],
    company: str,
    ap: AutoPricerConfig,
    section_mins: dict[str, float],
) -> tuple[float | None, float | None]:
    """Portal-style: min(row comps, section MinPrice grid) − AmountUnder."""
    listing = _listing_for_comps(row, company)
    candidates: list[float] = []
    sec_low = _section_floor_price(listing["section"], section_mins)
    if sec_low and sec_low > 0:
        candidates.append(sec_low)
    try:
        comparables = client.get_lowest_comparables(event_id, listing)
        for c in comparables:
            if c.get("IsOwnInventory") or c.get("IsIgnored") or not c.get("Price"):
                continue
            candidates.append(float(c["Price"]))
    except Exception as exc:
        log.warning("comps failed listing %s: %s", listing["listing_id"], exc)
    if not candidates:
        return None, None
    low = min(candidates)
    price = max(round(low - ap.amount_under, 2), 0.01)
    return price, low


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
    company: str,
    ap: AutoPricerConfig,
    section_mins: dict[str, float],
    ap_eligible: bool,
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
    new_price, comp_low = har_target_price(client, event_id, row, company, ap, section_mins)
    rec["comp_low"] = comp_low
    row["_comp_low"] = comp_low
    rec["target_price"] = new_price
    rec["priced"] = False
    if new_price is not None and not dry_run:
        client.update_listing_prices(lid, new_price)
        rec["priced"] = True
    elif new_price is None:
        rec["status"] = "no_comps"
        if not dry_run:
            rec["shared"] = apply_sharing(client, venue_id, [lid])
            _append_result(rec)
        return rec

    payload = build_set_rules_payload(row, venue_id, ap)
    rec["floor"] = payload["listingIdFloors"][0]["FloorPrice"]
    rec["ceiling"] = payload["listingIdFloors"][0]["CeilingPrice"]

    if dry_run:
        rec["status"] = "dry_run"
        return rec

    rec["autopricer_set"] = False
    if ap_eligible:
        try:
            ok = client.post_json("/api/AutoPricer/SetListingRules", payload)
            rec["autopricer_set"] = bool(ok)
        except Exception as exc:
            rec["rules_error"] = str(exc)[:200]
            log.warning("SetListingRules %s: %s", lid, exc)
    rec["shared"] = apply_sharing(client, venue_id, [lid])
    if rec.get("priced") and (rec.get("autopricer_set") or not ap_eligible):
        rec["status"] = "ok"
    elif rec.get("autopricer_set"):
        rec["status"] = "ok"
    else:
        rec["status"] = "rules_failed" if ap_eligible else "priced_only"
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

    ap_ids = {int(r["Listing_ID"]) for r in ap_rows}
    try:
        section_mins = client.get_section_min_prices(event_id)
    except Exception:
        section_mins = {}

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
                company,
                ap,
                section_mins,
                int(row["Listing_ID"]) in ap_ids,
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
