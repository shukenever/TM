# TM — Vercel site (tixx.pw)

This repository is **only** the static + serverless site: `api/`, `scripts/`, `vercel.json`, and `npm run build`.

## Deploy

```bash
npm ci
npm run build
```

In Vercel, use repository **root** as the project root (`outputDirectory`: `public`). Configure env vars in the dashboard (Resend, Upstash, etc.).

## Cron (ticket reminders)

Reminder send times are **computed per subscriber** from `eventStartMs` (stored at registration): when the cron job runs, it sends the **24h / 3h / 1h** emails for anyone whose event is in the matching window and who has not already received that tier.

**Hobby** only allows **one cron invocation per day**. If the job runs once daily, Reminder emails are sent on the **first run after** each ticket crosses into the 24h / 3h / 1h window (not at the exact minute). For **tighter** scheduling, use **Vercel Pro** (shorter cron intervals), or an external scheduler (cron-job.org, etc.) `GET`/`POST` hitting `/api/ticket-reminders/cron` with `Authorization: Bearer $CRON_SECRET` multiple times per day.

**Hobby** also allows **at most 12 Serverless Functions** per deployment. This repo keeps **7** top-level `api/*.js` routes by merging `/api/tm-viewer/*` into `api/tm-viewer/[...slug].js` and `/api/ticket-reminders/*` into `api/ticket-reminders/[action].js`. Shared code lives under `lib/`. Upgrade to **Pro** if you need dozens of separate function files without consolidation.
