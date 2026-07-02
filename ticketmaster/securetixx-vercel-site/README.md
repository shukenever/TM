# SecureTixx Vercel site (frontend clone)

1:1 copy of `ticketmaster/tm-vercel-site` with SecureTixx branding (emerald palette, securetixx.com).

**Same backend / database as Tixx** — deploy as a second Vercel project from this repo root:

```bash
npm run build:securetixx
```

Set Vercel **Build Command** to `npm run build:securetixx` and add domains `securetixx.com` / `www.securetixx.com`.

Env (shared with Tixx): shop DB, Redis, `TM_PASSES_STATIC_URL`, etc. Optional:

- `TICKETS_PUBLIC_ORIGIN=https://securetixx.com`

## Refresh from Tixx template

```bash
python scripts/setup_securetixx_site.py
```

Re-runs clone + rebrand from `tm-vercel-site`.
