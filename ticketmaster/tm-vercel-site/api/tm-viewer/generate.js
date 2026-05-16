"use strict";

const { getUpstreamBase } = require("./_upstream");
const { writeJson, writeBuffer, corsOptions, readRequestBody } = require("./_http");

/** Proxy full POST body to registry host. */
module.exports = async (req, res) => {
  try {
    if (req.method === "OPTIONS") {
      return corsOptions(res, "POST, OPTIONS", "Content-Type, Authorization");
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
    const ct = (req.headers["content-type"] || "application/json").split(";")[0].trim();

    const r = await fetch(`${base}/api/tm-viewer/generate`, {
      method: "POST",
      headers: { "Content-Type": ct },
      body: buf,
    });
    const out = Buffer.from(await r.arrayBuffer());
    const rct = r.headers.get("content-type") || "application/octet-stream";
    return writeBuffer(res, r.status, out, {
      "Content-Type": rct,
      "Access-Control-Allow-Origin": "*",
    });
  } catch (e) {
    return writeJson(res, 502, {
      ok: false,
      error: "upstream_unreachable",
      detail: (e && e.message) || String(e),
    });
  }
};
