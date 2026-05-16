"use strict";

/**
 * Single function for /api/ticket-reminders/{cron|register|unsubscribe} (Hobby 12-fn limit).
 */
const { writeJson } = require("../../lib/tm-viewer/http");
const { normalizeBackendUrl } = require("../../lib/tm-viewer/upstream");

const cron = require("../../lib/ticket-reminders/cron");
const register = require("../../lib/ticket-reminders/register");
const status = require("../../lib/ticket-reminders/status");
const unsubscribe = require("../../lib/ticket-reminders/unsubscribe");

const REMINDER_ONLY_BACKEND = "http://104.194.11.195:3919";

function backendOrigins() {
  // Force reminder traffic to .195 only.
  // Keep this hard-pinned so writes never drift to another backend.
  const only = normalizeBackendUrl(REMINDER_ONLY_BACKEND);
  return only ? [only] : [];
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
  let last = null;

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
      const maybeHtmlError = /^text\/html\b/i.test(ctype) && r.status >= 400;
      const retryableStatus = r.status === 404 || r.status >= 500;
      if (retryableStatus || maybeHtmlError) {
        last = { status: r.status, text, ctype };
        continue;
      }
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
  if (last) {
    res.writeHead(last.status, {
      "content-type": last.ctype,
      "cache-control": "no-store",
    });
    res.end(last.text);
    return true;
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
    return writeJson(res, 502, {
      ok: false,
      error: "reminder_backend_unreachable",
      backend: REMINDER_ONLY_BACKEND,
    });
  }
  if (action === "cron") return cron(req, res);
  if (action === "register") return register(req, res);
  if (action === "status") return status(req, res);
  if (action === "unsubscribe") return unsubscribe(req, res);
  return writeJson(res, 404, { ok: false, error: "not_found", action });
};
