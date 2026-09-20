# StageFront auto-pricing

Prices every listing on the portal using the same APIs captured in `portal.stagefront.com.har`.

## Behavior

1. **QueryEvents** — all events from `--from-date` through `--to-date` (default end `12/31/2029`).
2. **QueryEventInventoryAll** — per event, for your company.
3. **GetLowestComparables** (SeatGeek) — per listing (section/row/qty).
4. **UpdateListingPrices** — sets price to **max(lowest × pct%, $0.11)** under the lowest non-own comp (default **3%**, **5%** on ~15% of listings).
5. **GetSavedSharingRule** + **UpdateListingsSharing** — applies saved rule **`shu`** (or `STAGEFRONT_SHARING_RULE_ID`) so inventory is shared to all destinations in that rule.

## Run

```powershell
cd ticketmaster\stagefront_pricing
$env:STAGEFRONT_PROXY = "host:port:user:pass"
$env:STAGEFRONT_COOKIE = "..."   # from DevTools → Network → any API request → Cookie header
$env:STAGEFRONT_SHARING_RULE_ID = "3612"
python pricer.py --dry-run --max-events 3 -v
python pricer.py --event-workers 10 --listing-workers 8
```

Options: `--pct 2`, `--to-date 12/31/2028`, `--company "Cash Resale Tickets (...)"`.

## Threading

- `--event-workers` — events in parallel.
- `--listing-workers` — listings per event in parallel.
- Each worker thread uses its own HTTP session with the same auth cookie.
