#!/usr/bin/env python3
"""
Background marketplace sync — refresh listing cache + resolve event images.

Run standalone:
  python ticketmaster/tixx_shop_sync.py

Or triggered by registry every SHOP_SYNC_INTERVAL_SEC (default 300).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

import tixx_marketplace_db as db  # noqa: E402
import tm_shop  # noqa: E402


def run_sync(*, image_batch: int = 20) -> dict:
    db.init_db()
    tm_shop.warm_shop_listings_cache()
    path = tm_shop._resolve_links_txt()
    listings, stats = tm_shop._load_all_listings(path)
    if not listings and stats.get("error"):
        return {"ok": False, "error": stats.get("error"), "detail": stats}
    n = db.upsert_listings_cache(listings)
    images = 0
    try:
        image_batch = max(0, min(int(image_batch), 40))
    except (TypeError, ValueError):
        image_batch = 20
    if image_batch and os.environ.get("TM_DISCOVERY_CONSUMER_KEY", "").strip():
        seen: set[str] = set()
        batch = []
        for row in listings:
            ek = str(row.get("event_key") or "")
            if not ek or ek in seen:
                continue
            if (row.get("image_url") or "").startswith("http"):
                seen.add(ek)
                continue
            seen.add(ek)
            batch.append(
                {
                    "event_key": ek,
                    "event_name": row.get("event_name") or "",
                    "event_id": row.get("event_id") or "",
                    "category": row.get("category") or "events",
                }
            )
            if len(batch) >= image_batch:
                break
        if batch:
            res = tm_shop.shop_resolve_event_images({"events": batch, "limit": image_batch})
            images = int(res.get("resolved") or len(res.get("images") or {}))
            if res.get("images"):
                for row in listings:
                    ek = row.get("event_key")
                    url = res["images"].get(ek)
                    if url:
                        row["image_url"] = url
                db.upsert_listings_cache(listings)
    db.append_sync_log("inventory_sync", f"{n} listings, {images} images", n, images)
    stats = db.marketplace_stats()
    return {"ok": True, "listings_synced": n, "images_resolved": images, "stats": stats}


def main() -> None:
    out = run_sync()
    print(out, flush=True)
    if not out.get("ok"):
        sys.exit(1)


if __name__ == "__main__":
    main()
