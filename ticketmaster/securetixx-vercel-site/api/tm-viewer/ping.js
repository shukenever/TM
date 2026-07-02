"use strict";

const { writeJson, corsOptions } = require("./_http");
const { getUpstreamBase } = require("./_upstream");

/**
 * GET/HEAD — no upstream call. Use to verify the browser hits Vercel Node (JSON), not a static/Python-only host (HTML 404).
 */
module.exports = async (req, res) => {
  if (req.method === "OPTIONS") {
    return corsOptions(res, "GET, HEAD, OPTIONS", "Content-Type");
  }
  if (req.method !== "GET" && req.method !== "HEAD") {
    return writeJson(res, 405, { ok: false, error: "method_not_allowed" });
  }
  const body = JSON.stringify({
    ok: true,
    route: "api/tm-viewer/ping",
    via: "vercel-node",
    ts: Date.now(),
    node: process.version,
    backend_url_configured: !!getUpstreamBase(),
  });
  res.writeHead(200, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "Content-Length": Buffer.byteLength(body),
    "Access-Control-Allow-Origin": "*",
  });
  if (req.method === "HEAD") res.end();
  else res.end(body);
};
