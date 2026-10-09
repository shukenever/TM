"""Drop priced StageFront listings 10%, unshare, wait 30s, share everywhere.

Matches portal.stagefront.com3.har / portal JS:

- Price commit (Global.js SavePricing):
  POST /api/Pricing/UpdateListingPrices
  [{listing_id, price, face: null}]
- Unshare (HAR click):
  POST /api/Pricing/UpdateListingsSharing
  {ListingIds, ShareOutSettings: []}
- Share everywhere (CommonListingCtl when every destination is selected):
  ShareOutSettings: [{Export_Destination_ID, AllowedSplits: 1, Visibility: "SHOW"}, ...]

Listings at $0 or with no export destinations are written to a text file and left alone.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from .auth import cookie_from_har
    from .client import StagefrontClient, StagefrontConfig
    from .pricer import parse_proxy
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from auth import cookie_from_har
    from client import StagefrontClient, StagefrontConfig
    from pricer import parse_proxy

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HAR = ROOT / "portal.stagefront.com3.har"
DEFAULT_PROXY = "http://96.126.176.73:8749"


def _proxy() -> str:
    raw = os.environ.get("STAGEFRONT_PROXY", "").strip()
    if raw:
        return parse_proxy(raw)
    cfg_path = ROOT / "vl_inventory_bot.config.json"
    user = os.environ.get("VL_PROXY_USER", "").strip()
    password = os.environ.get("VL_PROXY_PASS", "")
    if cfg_path.is_file():
        import json

        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        user = user or str(cfg.get("vl_proxy_user") or "").strip()
        password = password or str(cfg.get("vl_proxy_pass") or "")
        base = str(cfg.get("vl_proxy_url") or DEFAULT_PROXY).strip()
    else:
        base = DEFAULT_PROXY
    if user and "://" in base and "@" not in base.split("://", 1)[-1]:
        import urllib.parse

        scheme, hostpart = base.split("://", 1)
        return (
            f"{scheme}://{urllib.parse.quote(user, safe='')}:"
            f"{urllib.parse.quote(password, safe='')}@{hostpart}"
        )
    return base


def _price(row: dict) -> float:
    try:
        return float(row.get("Listing_Price") or 0)
    except (TypeError, ValueError):
        return 0.0


def _shared(row: dict) -> bool:
    csv = str(row.get("Export_Destination_ID_CSV") or "").strip()
    shared_to = row.get("Shared_To")
    if shared_to is None or str(shared_to).strip().lower() in ("", "none", "null"):
        return bool(csv)
    return bool(csv) or str(shared_to).strip().upper() in ("CUSTOM", "EVERYWHERE")


def _date(row: dict) -> str:
    raw = str(row.get("Event_Date") or "")
    return raw[:10]


def _reason(row: dict) -> str:
    bits = []
    if _price(row) <= 0:
        bits.append("price_0")
    if not _shared(row):
        bits.append("unshared")
    return ",".join(bits)


def _line(row: dict) -> str:
    return " | ".join(
        [
            str(int(row.get("Listing_ID") or 0)),
            str(row.get("Event_Name") or "").replace("|", "/"),
            _date(row),
            str(row.get("Event_Time") or "").strip(),
            str(row.get("Venue_Name") or "").replace("|", "/"),
            str(row.get("Section") or ""),
            str(row.get("Row") or ""),
            str(row.get("Seats") or ""),
            str(row.get("Quantity") or ""),
            f"{_price(row):.2f}",
            str(row.get("Shared_To") or ""),
            str(row.get("Export_Destination_ID_CSV") or ""),
            str(row.get("Company_Name") or "").replace("|", "/"),
            str(int(row.get("Event_ID") or 0)),
            _reason(row),
        ]
    )


HEADER = (
    "listing_id | event | date | time | venue | section | row | seats | qty | "
    "price | shared_to | export_destinations | company | event_id | reason"
)


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


# Portal labels Shared_To EVERYWHERE only when 12 destinations are saved.
# ListExportDestinations includes 128 (TM External), which the share API drops.
# Destination 122 is not in that list, but saving it plus the other 11 is what
# the inventory grid stores as EVERYWHERE (see listing 27200832).
EVERYWHERE_DEST_IDS = (104, 105, 106, 115, 116, 117, 118, 120, 121, 122, 126, 127)


def _share_everywhere(client: StagefrontClient | None = None) -> list[dict]:
    del client
    return [
        {
            "Listing_ID": None,
            "Export_Destination_ID": int(dest_id),
            "AllowedSplits": 1,
            "Visibility": "SHOW",
        }
        for dest_id in EVERYWHERE_DEST_IDS
    ]


def _say(msg: str) -> None:
    print(msg, flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Drop priced StageFront listings 10% and reshare")
    ap.add_argument("--har", default=str(DEFAULT_HAR))
    ap.add_argument("--pct", type=float, default=10.0)
    ap.add_argument("--wait", type=int, default=30)
    ap.add_argument("--chunk", type=int, default=40)
    ap.add_argument("--out", default=str(ROOT / "stagefront_zero_unshared.txt"))
    ap.add_argument("--applied", default=str(ROOT / "stagefront_drop10_applied.txt"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--direct", action="store_true", help="Skip proxy; use the HAR cookie directly")
    ap.add_argument(
        "--restore-applied",
        action="store_true",
        help="Set prices back to the old column in the applied file, then share everywhere",
    )
    args = ap.parse_args(argv)

    har = Path(args.har)
    _say(f"loading cookie from {har.name}")
    cookie = cookie_from_har(har)
    proxy = None if args.direct else _proxy()
    _say(f"cookie from {har.name} ({len(cookie)} chars), proxy {'off' if args.direct else 'set'}")

    cfg = StagefrontConfig(proxy_url=proxy, event_from="", event_to="")
    client = StagefrontClient(cfg)
    client.set_cookie(cookie)
    client.ensure_api_session()
    _say("portal session OK")

    if args.restore_applied:
        applied_path = Path(args.applied)
        updates: list[tuple[int, float]] = []
        for line in applied_path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#") or line.startswith("listing_id"):
                continue
            parts = [p.strip() for p in line.split("|")]
            lid = int(parts[0])
            old = float(parts[-2])
            updates.append((lid, old))
        _say(f"restoring {len(updates)} prices to the single 10% drop")
        for chunk in _chunks(updates, args.chunk):
            payload = [{"listing_id": lid, "price": price, "face": None} for lid, price in chunk]
            client.post_json("/api/Pricing/UpdateListingPrices", payload, retries=8)
            _say(f"restored {len(payload)} (through listing {payload[-1]['listing_id']})")
        share_out = _share_everywhere()
        ids = [lid for lid, _ in updates]
        _say("sharing everywhere " + ",".join(str(s["Export_Destination_ID"]) for s in share_out))
        for chunk in _chunks(ids, args.chunk):
            client.post_json(
                "/api/Pricing/UpdateListingsSharing",
                {"ListingIds": chunk, "ShareOutSettings": share_out},
                retries=8,
            )
            _say(f"shared {len(chunk)} (through listing {chunk[-1]})")
        _say(f"restore done n={len(updates)}")
        return 0

    rows = client.query_inventory(None)
    _say(f"inventory rows {len(rows)}")

    priced = []
    parked = []
    for row in rows:
        lid = int(row.get("Listing_ID") or 0)
        if not lid:
            continue
        if _price(row) > 0:
            priced.append(row)
        if _price(row) <= 0 or not _shared(row):
            parked.append(row)

    parked.sort(key=lambda r: (_date(r), str(r.get("Event_Name") or ""), int(r.get("Listing_ID") or 0)))
    out_path = Path(args.out)
    lines = [
        f"# StageFront listings at $0 or unshared — {datetime.now().isoformat(timespec='seconds')}",
        f"# source inventory {len(rows)} | saved {len(parked)} | priced-for-drop {len(priced)}",
        HEADER,
    ]
    lines.extend(_line(r) for r in parked)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _say(f"saved {len(parked)} zero/unshared rows -> {out_path.name}")

    factor = 1.0 - (args.pct / 100.0)
    updates: list[tuple[dict, float, float]] = []
    for row in priced:
        old = _price(row)
        new = round(old * factor, 2)
        if new <= 0:
            new = 0.01
        if new >= old:
            continue
        updates.append((row, old, new))

    _say(f"price drops {len(updates)} by {args.pct:g}%")
    applied_path = Path(args.applied)
    applied = [
        f"# StageFront {args.pct:g}% drop — {datetime.now().isoformat(timespec='seconds')}",
        "listing_id | event | date | venue | section | row | seats | old_price | new_price",
    ]
    for row, old, new in updates:
        applied.append(
            " | ".join(
                [
                    str(int(row["Listing_ID"])),
                    str(row.get("Event_Name") or "").replace("|", "/"),
                    _date(row),
                    str(row.get("Venue_Name") or "").replace("|", "/"),
                    str(row.get("Section") or ""),
                    str(row.get("Row") or ""),
                    str(row.get("Seats") or ""),
                    f"{old:.2f}",
                    f"{new:.2f}",
                ]
            )
        )
    applied_path.write_text("\n".join(applied) + "\n", encoding="utf-8")
    _say(f"wrote drop list -> {applied_path.name}")

    if args.dry_run:
        _say("dry-run: no price or share changes sent")
        return 0
    if not updates:
        _say("nothing to drop")
        return 0

    ids = [int(row["Listing_ID"]) for row, _, _ in updates]
    for chunk in _chunks(updates, args.chunk):
        payload = [
            {"listing_id": int(row["Listing_ID"]), "price": new, "face": None}
            for row, _old, new in chunk
        ]
        client.post_json("/api/Pricing/UpdateListingPrices", payload, retries=12)
        _say(f"priced {len(payload)} (through listing {payload[-1]['listing_id']})")

    for chunk in _chunks(ids, args.chunk):
        client.post_json(
            "/api/Pricing/UpdateListingsSharing",
            {"ListingIds": chunk, "ShareOutSettings": []},
            retries=12,
        )
        _say(f"unshared {len(chunk)} (through listing {chunk[-1]})")

    _say(f"waiting {args.wait}s before share-everywhere")
    time.sleep(args.wait)

    share_out = _share_everywhere(client)
    names = ",".join(str(s["Export_Destination_ID"]) for s in share_out)
    _say(f"share everywhere destinations {names}")
    for chunk in _chunks(ids, args.chunk):
        client.post_json(
            "/api/Pricing/UpdateListingsSharing",
            {"ListingIds": chunk, "ShareOutSettings": share_out},
            retries=12,
        )
        _say(f"shared {len(chunk)} (through listing {chunk[-1]})")

    _say(f"done drops={len(updates)} parked={len(parked)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
