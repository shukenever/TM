"use strict";

/**
 * GET /api/tm-clock
 *
 * Returns `{ unix, source, url, fudge_sec }` using the HTTP `Date` header from a Ticketmaster
 * edge request (same idea as TM web tier clock; not the native app’s internal clock).
 *
 * Env:
 *   TM_CLOCK_HEAD_URL — default https://www.ticketmaster.com/
 *   TM_CLOCK_UNIX_FUDGE_SEC — integer seconds **added** to parsed unix before JSON (use **negative**
 *     values, e.g. **-3**, if passes still rotate **ahead** of the TM **app** — the app often lags
 *     the public site’s HTTP `Date` / your phone clock).
 *
 * Pass pages call this same-origin (set TM_VIEWER_SAFETIX_TM_CLOCK_URL=/api/tm-clock at generate).
 */

function sendJson(res, status, obj) {
  const body = JSON.stringify(obj);
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store, max-age=0");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.writeHead(status);
  res.end(body);
}

module.exports = async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  if (req.method === "OPTIONS") {
    res.setHeader("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");
    res.writeHead(204);
    res.end();
    return;
  }
  if (req.method !== "GET" && req.method !== "HEAD") {
    sendJson(res, 405, { error: "method_not_allowed" });
    return;
  }
  const base = (process.env.TM_CLOCK_HEAD_URL || "https://www.ticketmaster.com/").trim();
  try {
    const r = await fetch(base, { method: "HEAD", redirect: "follow" });
    const dh = r.headers.get("date");
    if (!dh) {
      sendJson(res, 502, { error: "no_date_header", url: base });
      return;
    }
    const ms = Date.parse(dh);
    if (Number.isNaN(ms)) {
      sendJson(res, 502, { error: "bad_date", url: base });
      return;
    }
    let unix = Math.floor(ms / 1000);
    let fudgeApplied = 0;
    const fudgeRaw = (process.env.TM_CLOCK_UNIX_FUDGE_SEC || "").trim();
    if (fudgeRaw !== "") {
      const f = parseInt(fudgeRaw, 10);
      if (!Number.isNaN(f)) {
        unix += f;
        fudgeApplied = f;
      }
    }
    if (req.method === "HEAD") {
      res.setHeader("Cache-Control", "no-store, max-age=0");
      res.setHeader("Access-Control-Allow-Origin", "*");
      res.writeHead(200);
      res.end();
      return;
    }
    sendJson(res, 200, { unix, source: "tm_http_date", url: base, fudge_sec: fudgeApplied });
  } catch (e) {
    const msg = (e && e.message) || String(e);
    sendJson(res, 502, { error: msg.slice(0, 240), url: base });
  }
};
