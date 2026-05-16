"use strict";

/**
 * Single function for /api/ticket-reminders/{cron|register|unsubscribe} (Hobby 12-fn limit).
 */
const { writeJson } = require("../../lib/tm-viewer/http");
const { normalizeBackendUrl, getUpstreamBase } = require("../../lib/tm-viewer/upstream");

const cron = require("../../lib/ticket-reminders/cron");
const register = require("../../lib/ticket-reminders/register");
const status = require("../../lib/ticket-reminders/status");
const unsubscribe = require("../../lib/ticket-reminders/unsubscribe");

function backendOrigins() {
  const out = [];
  const seen = new Set();
  const add = (raw) => {
    const b = normalizeBackendUrl(raw || "");
    if (!b || seen.has(b)) return;
    seen.add(b);
    out.push(b);
  };

  add(process.env.TM_REMINDER_BACKEND_URL);
  const multi = String(process.env.TM_REMINDER_BACKEND_URLS || "")
    .split(/[,\n;|]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  for (const m of multi) add(m);
  const fallbacks = String(process.env.TM_REMINDER_BACKEND_URL_FALLBACKS || "")
    .split(/[,\n;|]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  for (const m of fallbacks) add(m);

  // Reuse existing viewer backend envs when reminder-specific vars are not set.
  add(getUpstreamBase());
  const passOrigins = [
    ...(String(process.env.TM_PASSES_STATIC_URL || "")
      .split(/[,\n;|]+/)
      .map((s) => s.trim())
      .filter(Boolean)),
    ...(String(process.env.TM_PASSES_STATIC_URL_FALLBACKS || "")
      .split(/[,\n;|]+/)
      .map((s) => s.trim())
      .filter(Boolean)),
  ];
  for (const m of passOrigins) add(m);
  return out;
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks);
}

async function proxyReminder(req, res, action, search) {
  const origins = backendOrigins();
  if (!origins.length) return false;

  const method = String(req.method || "GET").toUpperCase();
  const body = method === "GET" || method === "HEAD" ? null : await readBody(req);
  const baseHeaders = {};
  const ct = String(req.headers["content-type"] || "").trim();
  const auth = String(req.headers.authorization || "").trim();
  if (ct) baseHeaders["content-type"] = ct;
  if (auth) baseHeaders.authorization = auth;

  for (const origin of origins) {
    try {
      const incomingHost = String(req.headers.host || "").toLowerCase();
      const targetHost = new URL(origin).host.toLowerCase();
      if (incomingHost && incomingHost === targetHost) {
        continue;
      }
      const u = `${origin}/api/ticket-reminders/${action}${search || ""}`;
      const r = await fetch(u, {
        method,
        headers: baseHeaders,
        body,
      });
      const text = await r.text();
      const ctype = r.headers.get("content-type") || "application/json; charset=utf-8";
      res.writeHead(r.status, {
        "content-type": ctype,
        "cache-control": "no-store",
      });
      res.end(text);
      return true;
    } catch {
      // try next backend
    }
  }
  return false;
}

module.exports = async (req, res) => {
  const host = req.headers.host || "localhost";
  const url = new URL(req.url || "/", `http://${host}`);
  const m = url.pathname.match(/^\/api\/ticket-reminders\/([^/?]+)/i);
  const action = m ? String(m[1]).toLowerCase() : "";
  if (["cron", "register", "status", "unsubscribe"].includes(action)) {
    const proxied = await proxyReminder(req, res, action, url.search || "");
    if (proxied) return;
  }
  if (action === "cron") return cron(req, res);
  if (action === "register") return register(req, res);
  if (action === "status") return status(req, res);
  if (action === "unsubscribe") return unsubscribe(req, res);
  return writeJson(res, 404, { ok: false, error: "not_found", action });
};
