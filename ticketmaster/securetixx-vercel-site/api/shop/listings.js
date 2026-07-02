"use strict";

const { getUpstreamBase } = require("../tm-viewer/_upstream");
const { writeJson, writeText, corsOptions } = require("../tm-viewer/_http");

module.exports = async (req, res) => {
  try {
    if (req.method === "OPTIONS") {
      return corsOptions(res, "GET, OPTIONS", "Content-Type");
    }
    if (req.method !== "GET") {
      return writeJson(res, 405, { ok: false, error: "method_not_allowed" });
    }
    const base = getUpstreamBase();
    if (!base) {
      return writeJson(res, 503, {
        ok: false,
        error: "proxy_misconfigured",
        detail: "Set TM_VIEWER_BACKEND_URL on Vercel",
      });
    }
    const r = await fetch(`${base}/api/shop/listings?events_only=1&limit=0`, { method: "GET" });
    const text = await r.text();
    const ct = r.headers.get("content-type") || "application/json; charset=utf-8";
    return writeText(res, r.status, text, ct);
  } catch (e) {
    return writeJson(res, 502, {
      ok: false,
      error: "upstream_unreachable",
      detail: (e && e.message) || String(e),
    });
  }
};
