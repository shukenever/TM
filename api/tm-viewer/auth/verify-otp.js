"use strict";

const { getUpstreamBase } = require("../_upstream");
const { writeJson, writeText, corsOptions, readRequestBody } = require("../_http");

module.exports = async (req, res) => {
  try {
    if (req.method === "OPTIONS") {
      return corsOptions(res, "POST, OPTIONS", "Content-Type");
    }
    if (req.method !== "POST") {
      return writeJson(res, 405, { ok: false, error: "method_not_allowed" });
    }
    const base = getUpstreamBase();
    if (!base) {
      return writeJson(res, 503, {
        ok: false,
        error: "proxy_misconfigured",
        detail: "Set TM_VIEWER_BACKEND_URL on Vercel (e.g. http://YOUR_IP:3919)",
      });
    }
    const raw = await readRequestBody(req);
    const bodyStr = raw.length ? raw.toString("utf-8") : "{}";
    const r = await fetch(`${base}/api/tm-viewer/auth/verify-otp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
