"use strict";

/**
 * Fallback when ``public/tm-email-gate.js`` is missing from the static bundle
 * (e.g. bad build output). Rewritten from ``/tm-email-gate.js`` in vercel.json.
 */
const fs = require("fs");
const path = require("path");

module.exports = function handler(_req, res) {
  const candidates = [
    path.join(__dirname, "tm-email-gate.js"),
    path.join(process.cwd(), "tm-email-gate.js"),
    path.join(__dirname, "..", "tm-email-gate.js"),
  ];
  let body = "";
  for (const p of candidates) {
    try {
      body = fs.readFileSync(p, "utf8");
      break;
    } catch (_) {
      // try next
    }
  }
  if (!body) {
    res.status(404).type("text/plain").send("tm-email-gate.js not found on server");
    return;
  }
  res.setHeader("Content-Type", "application/javascript; charset=utf-8");
  res.setHeader("Cache-Control", "public, s-maxage=600, stale-while-revalidate=86400");
  res.status(200).send(body);
};
