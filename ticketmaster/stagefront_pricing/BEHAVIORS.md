# StageFront portal behaviors (from `portal.stagefront.com.har`)

## Auth

| Step | Endpoint | Notes |
|------|----------|--------|
| Login page | `GET /Account/Login?ReturnUrl=%2F` | `__RequestVerificationToken` in HTML |
| Login | `POST /Account/Login?ReturnUrl=%2F` | `UserName`, `Password`, `RememberMe` → `302 /` |
| 2FA | `.AspNet.TwoFactorCookie` | Password login stops here; use browser **Cookie** header |

## Pricing inventory

| Step | Endpoint | Body / params |
|------|----------|----------------|
| Companies | `GET /api/Pricing/ListCompanies` | JSON array of company names |
| Events | `POST /api/Pricing/QueryEvents` | `EventFromDate`, `EventToDate` (MM/DD/YYYY), `limit: 99999`, `ShowSold: true` |
| Inventory | `POST /api/Pricing/QueryEventInventoryAll` | `eventId`, `companyName` → `EventInventory[]` (one row per seat) |
| Comparables | `POST /api/Marketplace/SeatGeek/GetLowestComparables` | `application/x-www-form-urlencoded` with `rules[...]` + `SF_Listing[...]` |
| Set price | `POST /api/Pricing/UpdateListingPrices` | `[{"listing_id", "price"}]` |
| Auto-pricer rules | `POST /api/AutoPricer/SetListingRules` | Optional; HAR used `AmountUnder: 0.11` (script uses % undercut instead) |

## Sharing (“shu”)

| Step | Endpoint | Notes |
|------|----------|--------|
| List rules | `GET /api/Pricing/ListSavedSharingRules?venueId=` | Match `Rule_Name` **shu** (id **3612** in HAR) |
| Load rule | `GET /api/Pricing/GetSavedSharingRule?ruleId=3612` | `ShareOutSettings` → all export destinations `Visibility: SHOW` |
| Apply | `POST /api/Pricing/UpdateListingsSharing` | `ListingIds` + `ShareOutSettings` |

## Script pricing logic

- Lowest comp = min `Price` where not `IsOwnInventory` / `IsIgnored`.
- New price = `lowest - max(lowest × pct%, $0.11)` (default **3%**, **5%** on ~15% of listings).
- After each price update, apply sharing rule **shu** so listings export everywhere in that rule.

## Concurrency

- Parallel **events** (`--event-workers`) and **listings per event** (`--listing-workers`).
- Each thread keeps its own `StagefrontClient` with the same session cookie.
- All HTTP traffic uses **`STAGEFRONT_PROXY`** (US), not local IP.
