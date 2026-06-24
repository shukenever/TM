"use strict";

const { getUpstreamBase } = require("../tm-viewer/upstream");
const { writeJson, writeText, corsOptions } = require("../tm-viewer/http");

const PUBLIC_MSG = "Events are temporarily unavailable. Please try again shortly.";

function sanitizeShopPayload(text) {
  try {
    const data = JSON.parse(text);
    if (!data || typeof data !== "object") return text;
    const allow = new Set([
      "ok",
      "count",
      "event_count",
      "events",
      "listings",
      "returned_count",
      "has_more",
      "limit",
      "offset",
      "events_only",
      "shop_email",
      "email_purchase_enabled",
      "stripe_enabled",
      "message",
      "error",
      "checkout_url",
      "order_id",
      "q",
      "catalog_count",
      "images",
      "resolved",
      "event_key",
      "sections",
      "category_totals",
      "generated_at",
      "expires_at",
      "ranking",
      "hero_event_key",
      "hero_image_url",
      "hero_event_name",
      "cached",
      "timing_ms",
    ]);
    if (!data.ok) {
      return JSON.stringify({
        ok: false,
        error: "unavailable",
        message: PUBLIC_MSG,
        count: 0,
        event_count: 0,
        events: [],
        listings: [],
      });
    }
    const out = {};
    for (const k of Object.keys(data)) {
      if (allow.has(k)) out[k] = data[k];
    }
    return JSON.stringify(out);
  } catch {
    return text;
  }
}

async function proxy(req, res, upstreamPath, { methods = "GET, POST, OPTIONS", allowBody = false, cacheControl = "" } = {}) {
  if (req.method === "OPTIONS") {
    return corsOptions(res, methods, "Content-Type, X-Shop-Secret, Authorization");
  }
  const base = getUpstreamBase();
  if (!base) {
    return writeJson(res, 503, {
      ok: false,
      error: "unavailable",
      message: PUBLIC_MSG,
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
  const r = await fetch(target, {
    method: req.method,
    headers,
    body,
    signal: AbortSignal.timeout(55000),
  });
  const text = await r.text();
  const ct = r.headers.get("content-type") || "application/json; charset=utf-8";
  const safe = ct.includes("json") ? sanitizeShopPayload(text) : text;
  if (cacheControl) {
    res.setHeader("Cache-Control", cacheControl);
  }
  return writeText(res, r.status, safe, ct);
}

module.exports = { proxy };
