"""StageFront bulk pricing via AutoPricer (HAR flow), not manual SeatGeek loops."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

try:
    from .auth import cookie_from_har
    from .autopricer import (
        RESULTS_PATH,
        AutoPricerConfig,
        process_event,
    )
    from .client import StagefrontClient, StagefrontConfig
except ImportError:
    from auth import cookie_from_har
    from autopricer import RESULTS_PATH, AutoPricerConfig, process_event
    from client import StagefrontClient, StagefrontConfig

log = logging.getLogger("stagefront.pricer")


def parse_proxy(raw: str) -> str:
    import urllib.parse

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


def resolve_session(
    cfg: StagefrontConfig,
    args: argparse.Namespace,
) -> StagefrontClient:
    rule_id_env = os.environ.get("STAGEFRONT_SHARING_RULE_ID", "").strip()
    rule_id = int(rule_id_env) if rule_id_env.isdigit() else None

    bootstrap = StagefrontClient(cfg)
    if rule_id:
        bootstrap.set_default_sharing_rule_id(rule_id)

    cookie = os.environ.get("STAGEFRONT_COOKIE", "").strip()
    if args.cookie_from_har:
        cookie = cookie_from_har(args.cookie_from_har)
        log.info("cookie from HAR %s (%d chars)", args.cookie_from_har, len(cookie))

    user = os.environ.get("STAGEFRONT_USER", "").strip()
    password = os.environ.get("STAGEFRONT_PASSWORD", "")

    if cookie:
        bootstrap.set_cookie(cookie)
        bootstrap.ensure_api_session()
    elif args.login and user and password:
        log.info("login + OTP if required (%s)", user)
        bootstrap.login_interactive(user, password)
    else:
        raise SystemExit("Set STAGEFRONT_COOKIE, --cookie-from-har, or --login with USER/PASSWORD")

    return bootstrap


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="StageFront AutoPricer bulk run (US proxy required)")
    ap.add_argument("--from-date", default="", help="MM/DD/YYYY")
    ap.add_argument("--to-date", default="12/31/2029")
    ap.add_argument("--amount-under", type=float, default=0.11, help="HAR AmountUnder ($)")
    ap.add_argument("--company", default="")
    ap.add_argument("--sharing-rule", default="shu")
    ap.add_argument("--event-workers", type=int, default=10)
    ap.add_argument("--listing-workers", type=int, default=8)
    ap.add_argument("--max-inflight", type=int, default=20)
    ap.add_argument("--request-gap-ms", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-events", type=int, default=0)
    ap.add_argument("--event-id", type=int, default=0)
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--cookie-from-har", default="")
    ap.add_argument("--no-force-reprice", action="store_true", help="Skip UpdateListingPrices on already-priced")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    proxy = os.environ.get("STAGEFRONT_PROXY", "").strip()
    if not proxy:
        log.error("STAGEFRONT_PROXY is required (US proxy)")
        return 2

    from_date = args.from_date or datetime.now().strftime("%m/%d/%Y")
    cfg = StagefrontConfig(
        proxy_url=parse_proxy(proxy),
        company_name=args.company or None,
        sharing_rule_name=args.sharing_rule,
        event_from=from_date,
        event_to=args.to_date,
        max_concurrent_requests=args.max_inflight,
        request_gap_sec=max(0, args.request_gap_ms) / 1000.0,
    )

    bootstrap = resolve_session(cfg, args)
    cookie = bootstrap._cookie
    rule_id = bootstrap._default_sharing_rule_id
    company = bootstrap.resolve_company()
    log.info("AutoPricer run company=%r events %s → %s", company, from_date, args.to_date)

    if not args.dry_run:
        RESULTS_PATH.write_text("", encoding="utf-8")

    ap_cfg = AutoPricerConfig(
        amount_under=args.amount_under,
        force_reprice=not args.no_force_reprice,
    )

    events_all = bootstrap.query_events()
    if args.event_id:
        events_all = [e for e in events_all if int(e.get("Event_ID") or 0) == args.event_id]
    events = events_all[: args.max_events] if args.max_events > 0 else events_all
    log.info("events total %d processing %d", len(events_all), len(events))

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
                ap_cfg,
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
    err = sum(1 for r in all_results if r.get("status") == "error")
    ap_set = sum(1 for r in all_results if r.get("autopricer_set"))
    priced = sum(1 for r in all_results if r.get("priced"))
    log.info(
        "done: autopricer_set=%d priced=%d ok=%d dry=%d err=%d rows=%d",
        ap_set,
        priced,
        ok,
        dry,
        err,
        len(all_results),
    )
    log.info("per-listing log: %s", RESULTS_PATH)

    summary = Path(__file__).resolve().parent / "last_run_summary.json"
    summary.write_text(json.dumps(all_results, indent=2)[:800000], encoding="utf-8")
    return 0 if err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
