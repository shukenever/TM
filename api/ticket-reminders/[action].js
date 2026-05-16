"use strict";

/**
 * Single function for /api/ticket-reminders/{cron|register|unsubscribe} (Hobby 12-fn limit).
 */
const { writeJson } = require("../../lib/tm-viewer/http");

const cron = require("../../lib/ticket-reminders/cron");
const register = require("../../lib/ticket-reminders/register");
const unsubscribe = require("../../lib/ticket-reminders/unsubscribe");

module.exports = async (req, res) => {
  const host = req.headers.host || "localhost";
  const url = new URL(req.url || "/", `http://${host}`);
  const m = url.pathname.match(/^\/api\/ticket-reminders\/([^/?]+)/i);
  const action = m ? String(m[1]).toLowerCase() : "";
  if (action === "cron") return cron(req, res);
  if (action === "register") return register(req, res);
  if (action === "unsubscribe") return unsubscribe(req, res);
  return writeJson(res, 404, { ok: false, error: "not_found", action });
};
