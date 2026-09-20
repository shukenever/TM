"""Price all StageFront listings: undercut market, apply sharing rule 'shu'."""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

try:
    from .client import StagefrontClient, StagefrontConfig
except ImportError:
    from client import StagefrontClient, StagefrontConfig

log = logging.getLogger("stagefront.pricer")

_thread_local = threading.local()


def parse_proxy(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    parts = raw.split(":")
    if len(parts) >= 4:
        host, port, user = parts[0], parts[1], parts[2]
        password = ":".join(parts[3:])
        user_q = urllib.parse.quote(user, safe="")
        pass_q = urllib.parse.quote(password, safe="")
        return f"http://{user_q}:{pass_q}@{host}:{port}"
    return raw


def thread_client(cfg: StagefrontConfig, cookie: str, rule_id: int | None) -> StagefrontClient:
    c = getattr(_thread_local, "client", None)
    if c is None:
        c = StagefrontClient(cfg)
        c.set_cookie(cookie)
        c.set_default_sharing_rule_id(rule_id)
        _thread_local.client = c
    return c


def compute_price(lowest: float, pct: float, min_under: float) -> float:
    under = max(lowest * (pct / 100.0), min_under)
    price = round(lowest - under, 2)
    return max(price, 0.01)


def pick_pct(cfg: StagefrontConfig) -> float:
    if random.random() < cfg.aggressive_fraction:
        return cfg.undercut_pct_aggressive
    return cfg.undercut_pct


def price_one_listing(
    cfg: StagefrontConfig,
    cookie: str,
    rule_id: int | None,
    event_id: int,
    venue_id: int,
    listing: dict,
    *,
    dry_run: bool,
) -> dict:
    client = thread_client(cfg, cookie, rule_id)
    lid = listing["listing_id"]
    comparables = client.get_lowest_comparables(event_id, listing)
    prices = [
        float(c["Price"])
        for c in comparables
        if not c.get("IsOwnInventory") and not c.get("IsIgnored") and c.get("Price")
    ]
    if not prices:
        return {"listing_id": lid, "status": "no_comps", "section": listing["section"], "row": listing["row"]}

    low = min(prices)
    pct = pick_pct(cfg)
    new_price = compute_price(low, pct, cfg.min_under_usd)
    old = listing.get("item_price") or 0

    if dry_run:
        return {
            "listing_id": lid,
            "status": "dry_run",
            "low": low,
            "price": new_price,
            "pct": pct,
            "section": listing["section"],
            "row": listing["row"],
            "qty": listing["quantity"],
        }

    client.update_listing_prices(lid, new_price)
    rid = client.sharing_rule_id(venue_id)
    if rid:
        share = client.share_out_settings(rid)
        if share:
            client.update_listings_sharing([lid], share)

    return {
        "listing_id": lid,
        "status": "ok",
        "low": low,
        "price": new_price,
        "old": old,
        "pct": pct,
        "section": listing["section"],
        "row": listing["row"],
        "qty": listing["quantity"],
        "shared": bool(rid),
    }


def process_event(
    cfg: StagefrontConfig,
    cookie: str,
    rule_id: int | None,
    company: str,
    event: dict,
    *,
    listing_workers: int,
    dry_run: bool,
) -> list[dict]:
    client = thread_client(cfg, cookie, rule_id)
    event_id = int(event["Event_ID"])
    venue_id = int(event.get("Venue_ID") or 0)
    name = event.get("Event_Name") or event.get("Event_Headliner") or str(event_id)
    inv = client.query_event_inventory(event_id, company)
    grouped = client.group_listings(inv)
    if not grouped:
        return [{"event_id": event_id, "status": "no_inventory", "event": name}]

    listings = list(grouped.values())
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, listing_workers)) as pool:
        futs = {
            pool.submit(
                price_one_listing,
                cfg,
                cookie,
                rule_id,
                event_id,
                venue_id,
                lst,
                dry_run=dry_run,
            ): lst
            for lst in listings
        }
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as exc:
                lst = futs[fut]
                log.exception("listing %s failed", lst.get("listing_id"))
                results.append(
                    {
                        "listing_id": lst.get("listing_id"),
                        "status": "error",
                        "error": str(exc),
                        "section": lst.get("section"),
                        "row": lst.get("row"),
                    }
                )
    log.info("event %s (%s): %d listings processed", event_id, name[:50], len(results))
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="StageFront auto-pricing (US proxy required)")
    ap.add_argument("--from-date", default="", help="MM/DD/YYYY (default: today US)")
    ap.add_argument("--to-date", default="12/31/2029", help="MM/DD/YYYY event end filter")
    ap.add_argument("--pct", type=float, default=3.0, help="Undercut %% vs lowest comp (default 3)")
    ap.add_argument("--pct-aggressive", type=float, default=5.0, help="Aggressive undercut %%")
    ap.add_argument("--aggressive-fraction", type=float, default=0.15, help="Fraction of listings at aggressive pct")
    ap.add_argument("--min-under", type=float, default=0.11, help="Min $ under lowest (floor on undercut amount)")
    ap.add_argument("--company", default="", help="Company name (default: first from API)")
    ap.add_argument("--sharing-rule", default="shu", help="Saved sharing rule name")
    ap.add_argument("--event-workers", type=int, default=8, help="Parallel events")
    ap.add_argument("--listing-workers", type=int, default=6, help="Parallel listings per event")
    ap.add_argument("--dry-run", action="store_true", help="Do not POST price/share updates")
    ap.add_argument("--max-events", type=int, default=0, help="Limit events (0 = all)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    proxy = os.environ.get("STAGEFRONT_PROXY", "").strip()
    if not proxy:
        log.error("Set STAGEFRONT_PROXY (host:port:user:pass or http://user:pass@host:port)")
        return 2
    proxy_url = parse_proxy(proxy)

    cookie = os.environ.get("STAGEFRONT_COOKIE", "").strip()
    user = os.environ.get("STAGEFRONT_USER", "").strip()
    password = os.environ.get("STAGEFRONT_PASSWORD", "")
    rule_id_env = os.environ.get("STAGEFRONT_SHARING_RULE_ID", "").strip()
    rule_id = int(rule_id_env) if rule_id_env.isdigit() else None

    from_date = args.from_date or datetime.now().strftime("%m/%d/%Y")

    cfg = StagefrontConfig(
        proxy_url=proxy_url,
        company_name=args.company or None,
        sharing_rule_name=args.sharing_rule,
        event_from=from_date,
        event_to=args.to_date,
        undercut_pct=args.pct,
        undercut_pct_aggressive=args.pct_aggressive,
        aggressive_fraction=args.aggressive_fraction,
        min_under_usd=args.min_under,
    )
    bootstrap = StagefrontClient(cfg)
    if rule_id:
        bootstrap.set_default_sharing_rule_id(rule_id)

    if cookie:
        bootstrap.set_cookie(cookie)
        log.info("using STAGEFRONT_COOKIE (%d chars)", len(cookie))
    elif user and password:
        log.info("logging in as %s via proxy", user)
        bootstrap.login(user, password)
    else:
        log.error("Set STAGEFRONT_COOKIE or STAGEFRONT_USER + STAGEFRONT_PASSWORD")
        return 2

    cookie = bootstrap._cookie
    company = bootstrap.resolve_company()
    log.info("company=%r events %s → %s", company, from_date, args.to_date)

    events_all = bootstrap.query_events()
    events = events_all[: args.max_events] if args.max_events > 0 else events_all
    log.info("QueryEvents returned %d events (processing %d)", len(events_all), len(events))
    if not events:
        return 0

    all_results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, args.event_workers)) as pool:
        futs = [
            pool.submit(
                process_event,
                cfg,
                cookie,
                rule_id,
                company,
                ev,
                listing_workers=args.listing_workers,
                dry_run=args.dry_run,
            )
            for ev in events
        ]
        for fut in as_completed(futs):
            try:
                all_results.extend(fut.result())
            except Exception:
                log.exception("event worker failed")

    ok = sum(1 for r in all_results if r.get("status") == "ok")
    dry = sum(1 for r in all_results if r.get("status") == "dry_run")
    skip = sum(1 for r in all_results if r.get("status") == "no_comps")
    err = sum(1 for r in all_results if r.get("status") == "error")
    log.info("done: ok=%d dry=%d no_comps=%d err=%d total_rows=%d", ok, dry, skip, err, len(all_results))

    out = Path(__file__).resolve().parent / "last_run_summary.json"
    out.write_text(json.dumps(all_results, indent=2)[:500000], encoding="utf-8")
    log.info("wrote %s", out)
    return 0 if err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
