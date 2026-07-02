# SecureTixx Vercel site (frontend clone)

1:1 copy of `ticketmaster/tm-vercel-site` with SecureTixx branding. **Same `vercel.json`, API, and `tm_viewer_link_registry.json` as Tixx.**

## Vercel project (tmnew / securetixx.com)

Use the **same** repo settings as Tixx:

| Setting | Value |
|---------|--------|
| Build Command | `npm run build` |
| Output Directory | `public` |
| Framework | Other |

**Only difference — Vercel env vars:**

```
TM_VERCEL_SITE=securetixx-vercel-site
TICKETS_PUBLIC_ORIGIN=https://securetixx.com
```

Copy all other env from the Tixx project (`TM_VIEWER_BACKEND_URL`, shop DB, `TM_PASSES_STATIC_URL`, Redis, etc.).

## Shared registry (VPS)

One `tm_viewer_link_registry.py` serves both brands. Pass paths in `tm_viewer_link_registry.json` are relative; each domain resolves them on its own origin.

Optional on VPS when generating links for SecureTixx buyers:

```
TM_VIEWER_WATCH_PUBLIC_BASE=https://securetixx.com
```

## Local build

```bash
npm run build:securetixx
# same as: TM_VERCEL_SITE=securetixx-vercel-site npm run build
```

## Refresh branding from Tixx template

```bash
python scripts/setup_securetixx_site.py
```
