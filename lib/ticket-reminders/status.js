"use strict";

const { getRedis } = require("./redis");
const {
  refKeyForTicket,
  listLegacyLookupKeys,
} = require("./ref-keys");
const { writeJson, corsOptions } = require("../tm-viewer/http");

/**
 * GET /api/ticket-reminders/status?gid=&slug=
 * Returns whether this ticket already has a reminder registration (server-side).
 * Does not expose the email address.
 */
module.exports = async (req, res) => {
  try {
    if (req.method === "OPTIONS") {
      return corsOptions(res, "GET, OPTIONS", "Content-Type");
    }
    if (req.method !== "GET") {
      return writeJson(res, 405, { ok: false, error: "method_not_allowed" });
    }

    const redis = getRedis();
    if (!redis) {
      return writeJson(res, 503, {
        ok: false,
        error: "redis_not_configured",
      });
    }

    const host = req.headers.host || "localhost";
    const u = new URL(req.url || "/", `http://${host}`);

    const gid = String(u.searchParams.get("gid") || "").replace(/\D/g, "").slice(0, 12) || "";
    const slug = String(u.searchParams.get("slug") || "")
      .trim()
      .replace(/[^a-zA-Z0-9_.-]/g, "")
      .slice(0, 180);

    if (!gid || !slug) {
      return writeJson(res, 400, { ok: false, error: "missing_gid_or_slug" });
    }

    const rk = refKeyForTicket(gid, slug);
    const refSub = await redis.get(rk);
    if (refSub) {
      return writeJson(res, 200, { ok: true, hasRegistered: true });
    }

    const legacyKeys = await listLegacyLookupKeys(redis, gid, slug);
    return writeJson(res, 200, {
      ok: true,
      hasRegistered: legacyKeys.length > 0,
    });
  } catch (e) {
    const msg = (e && e.message) || String(e);
    return writeJson(res, 500, {
      ok: false,
      error: "status_failed",
      detail: msg.slice(0, 200),
    });
  }
};
