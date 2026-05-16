# TM — Vercel site (tixx.pw)

This repository is **only** the static + serverless site: `api/`, `scripts/`, `vercel.json`, and `npm run build`.

## Deploy

```bash
npm ci
npm run build
```

In Vercel, use repository **root** as the project root (`outputDirectory`: `public`). Configure env vars in the dashboard (Resend, Upstash, etc.).

## Cron (ticket reminders)

**Hobby** plans only allow **one job per day**. This repo uses `0 12 * * *` (12:00 UTC daily). On **Pro**, you can change `vercel.json` → `crons[0].schedule` to a tighter interval (e.g. every 15 minutes); Hobby deploys will **fail** if the expression runs more than once per day.

**Hobby** also allows **at most 12 Serverless Functions** per deployment. This repo keeps **7** top-level `api/*.js` routes by merging `/api/tm-viewer/*` into `api/tm-viewer/[...slug].js` and `/api/ticket-reminders/*` into `api/ticket-reminders/[action].js`. Shared code lives under `lib/`. Upgrade to **Pro** if you need dozens of separate function files without consolidation.
