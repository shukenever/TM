# TM — Vercel site (tixx.pw)

This repository is **only** the static + serverless site: `api/`, `scripts/`, `vercel.json`, and `npm run build`.

## Deploy

```bash
npm ci
npm run build
```

In Vercel, use repository **root** as the project root (`outputDirectory`: `public`). Configure env vars in the dashboard (Resend, Upstash, etc.).
