"use strict";

const { getUpstreamBase } = require("../tm-viewer/upstream");
const { writeJson, writeText, corsOptions } = require("../tm-viewer/http");

async function proxy(req, res, upstreamPath, { methods = "GET, POST, OPTIONS", allowBody = false } = {}) {
  if (req.method === "OPTIONS") {
    return corsOptions(res, methods, "Content-Type, X-Shop-Secret, Authorization");
  }
  const base = getUpstreamBase();
  if (!base) {
    return writeJson(res, 503, {
      ok: false,
      error: "proxy_misconfigured",
      detail: "Set TM_VIEWER_BACKEND_URL on Vercel",
    });
  }
  const host = req.headers.host || "localhost";
  const url = new URL(req.url || "/", `http://${host}`);
  const qs = url.search || "";
  const target = `${base}${upstreamPath}${qs}`;
  const headers = { Accept: "application/json" };
  if (allowBody && req.method !== "GET" && req.method !== "HEAD") {
    headers["Content-Type"] = req.headers["content-type"] || "application/json";
    if (req.headers["x-shop-secret"]) headers["X-Shop-Secret"] = req.headers["x-shop-secret"];
  }
  let body;
  if (allowBody && req.method !== "GET" && req.method !== "HEAD") {
    body = await new Promise((resolve, reject) => {
      const chunks = [];
      req.on("data", (c) => chunks.push(c));
      req.on("end", () => resolve(Buffer.concat(chunks)));
      req.on("error", reject);
    });
  }
  const r = await fetch(target, { method: req.method, headers, body });
  const text = await r.text();
  const ct = r.headers.get("content-type") || "application/json; charset=utf-8";
  return writeText(res, r.status, text, ct);
}

module.exports = { proxy };
