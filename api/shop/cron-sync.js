"use strict";

/**
 * Vercel cron — triggers inventory sync on VPS registry (every 5 min).
 * Set TM_VIEWER_BACKEND_URL and SHOP_SYNC_SECRET on Vercel.
 */
const { getUpstreamBase } = require("../../lib/tm-viewer/upstream");
const { writeJson } = require("../../lib/tm-viewer/http");

module.exports = async (req, res) => {
  if (req.method !== "GET" && req.method !== "POST") {
    return writeJson(res, 405, { ok: false, error: "method_not_allowed" });
  }
  const base = getUpstreamBase();
  if (!base) {
    return writeJson(res, 503, { ok: false, error: "proxy_misconfigured" });
  }
  const secret = process.env.SHOP_SYNC_SECRET || process.env.SHOP_PURCHASE_SECRET || "";
  const url = `${base}/api/shop/sync${secret ? `?secret=${encodeURIComponent(secret)}` : ""}`;
  try {
    const r = await fetch(url, { method: "GET" });
    const data = await r.json().catch(() => ({}));
    return writeJson(res, r.status, data);
  } catch (e) {
    return writeJson(res, 502, { ok: false, error: "sync_failed", detail: String(e.message || e) });
  }
};
