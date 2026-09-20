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
$env:STAGEFRONT_SHARING_RULE_ID = "3612"

# Fresh HAR export (or paste cookie)
python pricer.py --cookie-from-har "..\..\portal.stagefront.com.har" --dry-run --event-id 334782109

# Or one login + OTP in terminal; same cookie is copied to all worker threads
$env:STAGEFRONT_USER = "..."
$env:STAGEFRONT_PASSWORD = "..."
python pricer.py --login

python pricer.py --cookie-from-har "..\..\portal.stagefront.com.har" --event-workers 5 --listing-workers 4
```

**Proxy is required** (`STAGEFRONT_PROXY`). Requests are capped (`--max-inflight 12`, 50ms gap) so the portal is not hammered.

**Pricing (default `--price-strategy portal`)** matches HAR AutoPricer: **$0.11 under** lowest comp when comp ≥ $50; cheaper seats use **2.5%** under. Skips updates when already within $0.02.

Options: `--pct 2`, `--to-date 12/31/2028`, `--company "Cash Resale Tickets (...)"`.

## Threading

- `--event-workers` — events in parallel.
- `--listing-workers` — listings per event in parallel.
- Each worker thread uses its own HTTP session with the same auth cookie.
