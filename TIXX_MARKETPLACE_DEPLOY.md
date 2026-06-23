# Tixx Marketplace — Deploy Guide

Production split: **Vercel** (frontend + API proxy) → **VPS registry** (inventory, orders DB, email, OTP).

## Architecture

```
Browser → tixx.pw (Vercel)
            ├─ /, /shop, /login, /my-tickets  (static)
            └─ /api/shop/*, /api/tm-viewer/*    (proxy)
                    ↓
            VPS :3919 tm_viewer_link_registry.py
                    ├─ secure_pass_stock.csv (live inventory)
                    ├─ tixx_marketplace.db (orders, accounts, cache)
                    └─ background sync every 5 min (+ Vercel cron)
```

## 1. VPS — Registry + Database

On your server (same machine as stock CSV):

```powershell
$env:TM_STUBHUB_STOCK_CSV = "C:\path\to\secure_pass_stock.csv"
$env:TIXX_MARKETPLACE_DB = "C:\path\to\tixx_marketplace.db"
$env:SHOP_ALLOW_EMAIL_PURCHASE = "1"
$env:TM_DISCOVERY_CONSUMER_KEY = "your-discovery-api-key"
$env:SHOP_SYNC_INTERVAL_SEC = "300"
$env:SHOP_SYNC_SECRET = "long-random-secret"
$env:TM_RESEND_API_KEY = "re_..."

python tm_viewer_link_registry.py --host 0.0.0.0 --port 3919
```

Open firewall **TCP 3919** for Vercel egress (or put nginx TLS proxy in front).

### Database (SQLite)

Created automatically at `TIXX_MARKETPLACE_DB` or next to stock CSV:

| Table | Purpose |
|-------|---------|
| `orders` | All purchases (email + Stripe) |
| `accounts` | Profile, city, prefs per email |
| `addresses` | Saved shipping addresses |
| `payment_methods` | Last-4 + expiry only |
| `listings_cache` | Snapshot of CSV + images |
| `sync_log` | Inventory sync history |

Manual sync once:

```powershell
python ticketmaster/tixx_shop_sync.py
```

Health check:

```http
GET http://YOUR_VPS:3919/api/shop/health
```

## 2. Vercel — Environment Variables

Project settings → Environment Variables:

| Variable | Example | Required |
|----------|---------|----------|
| `TM_VIEWER_BACKEND_URL` | `http://YOUR_VPS_IP:3919` | Yes |
| `SHOP_SYNC_SECRET` | same as VPS | Yes (for cron) |
| `TM_RESEND_API_KEY` | (optional if only on VPS) | OTP on VPS |

**Do not** append `/api` to `TM_VIEWER_BACKEND_URL`.

## 3. Deploy to Vercel

From repo root:

```bash
npm run build
npx vercel --prod
```

Build copies `ticketmaster/tm-vercel-site/` → `public/` (home, shop, logos, settings).

### Cron (every 5 minutes)

`vercel.json` runs `/api/shop/cron-sync` → VPS `/api/shop/sync` to refresh listings + event images.

## 4. GitHub

```bash
git add ticketmaster/tixx_marketplace_db.py ticketmaster/tixx_shop_sync.py ticketmaster/tm_shop.py
git add tm_viewer_link_registry.py api/shop lib/shop scripts/sync-public.js vercel.json
git add ticketmaster/tm-vercel-site/
git commit -m "feat(marketplace): SQLite orders DB, inventory sync, Vercel shop proxy"
git push origin web-only
```

Connect Vercel project to `web-only` branch (or merge to main).

## 5. API Routes (proxied on Vercel)

| Method | Path | Registry |
|--------|------|----------|
| GET | `/api/shop/listings` | Live CSV inventory |
| POST | `/api/shop/purchase` | Buy + DB order |
| POST | `/api/shop/checkout` | Stripe |
| POST | `/api/shop/event-images` | Discovery posters |
| GET | `/api/shop/orders?token=` | Order history |
| GET/POST | `/api/shop/account?token=` | Profile, addys, cards |
| GET | `/api/shop/sync?secret=` | Force inventory sync |
| GET | `/api/shop/health` | DB stats |

## 6. Account settings sync

Signed-in users: settings modal POSTs profile, addresses, cards to `/api/shop/account` (stored in SQLite on VPS). No GPS — city is manual only.

## Troubleshooting

- **Shop empty on Vercel**: `TM_VIEWER_BACKEND_URL` wrong or port 3919 blocked.
- **Orders missing**: check `tixx_marketplace.db` on VPS; sign in with purchase email.
- **No event images**: set `TM_DISCOVERY_CONSUMER_KEY` on VPS; wait for sync cron.
- **502 upstream**: registry not running or wrong IP.
