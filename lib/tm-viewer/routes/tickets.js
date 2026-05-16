"use strict";

const { getUpstreamBase } = require("../upstream");
const { writeJson, writeText, corsOptions } = require("../http");

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
        detail: "Set TM_VIEWER_BACKEND_URL on Vercel (e.g. http://YOUR_IP:3919)",
      });
    }
    let token = "";
    try {
      const url = new URL(req.url || "/", "http://localhost");
      token = (url.searchParams.get("token") || "").trim();
    } catch {
      token = "";
    }
    const qs = `token=${encodeURIComponent(String(token))}`;
    const r = await fetch(`${base}/api/tm-viewer/tickets?${qs}`, { method: "GET" });
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
