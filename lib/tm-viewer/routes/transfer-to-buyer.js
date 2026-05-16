"use strict";

const { getUpstreamBase } = require("../upstream");
const { writeJson, corsOptions, readRequestBody } = require("../http");

/** Proxy POST JSON to registry: session token + buyer email + pass path. */
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
        detail: "Set TM_VIEWER_BACKEND_URL on Vercel",
      });
    }
    const buf = await readRequestBody(req);
    const r = await fetch(`${base}/api/tm-viewer/transfer-to-buyer`, {
      method: "POST",
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: buf,
    });
    const text = await r.text();
    const ct = r.headers.get("content-type") || "application/json; charset=utf-8";
    res.writeHead(r.status, {
      "Content-Type": ct,
      "Cache-Control": "no-store",
      "Content-Length": Buffer.byteLength(text),
      "Access-Control-Allow-Origin": "*",
    });
    res.end(text);
  } catch (e) {
    return writeJson(res, 502, {
      ok: false,
      error: "upstream_unreachable",
      detail: (e && e.message) || String(e),
    });
  }
};
