"use strict";

const { getUpstreamBase } = require("../tm-viewer/_upstream");
const { writeJson, writeText, corsOptions, readRequestBody } = require("../tm-viewer/_http");

module.exports = async (req, res) => {
  try {
    if (req.method === "OPTIONS") {
      return corsOptions(res, "POST, OPTIONS", "Content-Type, X-Shop-Secret");
    }
    if (req.method !== "POST") {
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
    const raw = await readRequestBody(req);
    const bodyStr = raw.length ? raw.toString("utf-8") : "{}";
    const headers = { "Content-Type": "application/json" };
    const secret = req.headers["x-shop-secret"];
    if (secret) headers["X-Shop-Secret"] = secret;
    const r = await fetch(`${base}/api/shop/checkout`, {
      method: "POST",
      headers,
      body: bodyStr,
    });
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
