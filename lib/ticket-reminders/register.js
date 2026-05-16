"use strict";

/**
 * POST /api/ticket-reminders/register
 *
 * Env:
 * - UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN — subscriber storage (free tier OK).
 * - RESEND_API_KEY, RESEND_FROM — sends reminders via Resend (verified domain).
 * - TICKETS_PUBLIC_ORIGIN — optional, base URL for unsubscribe links (default https://tixx.pw).
 * - REMINDER_REGISTER_SECRET or TM_REMINDER_REGISTER_SECRET — optional server-to-server auth only:
 *   if set, POST must send Authorization: Bearer <same>. Leave unset for normal browser registration from the gate.
 *
 * Pass HTML should include:
 * <meta name="tm-event-start" content="2026-08-01T20:00:00Z" />
 * <meta name="tm-event-title" content="Artist — Venue" />
 */

const crypto = require("crypto");
const { getRedis } = require("./redis");
const {
  writeJson,
  corsOptions,
  readRequestBody,
} = require("../tm-viewer/http");

function looksLikeEmail(s) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(s || "").trim());
}

function normalizeEmail(e) {
  return String(e || "").trim().toLowerCase();
}

module.exports = async (req, res) => {
  try {
    if (req.method === "OPTIONS") {
      return corsOptions(res, "POST, OPTIONS", "Content-Type");
    }
    if (req.method !== "POST") {
      return writeJson(res, 405, { ok: false, error: "method_not_allowed" });
    }

    const redis = getRedis();
    if (!redis) {
      return writeJson(res, 503, {
        ok: false,
        error: "redis_not_configured",
        detail:
          "Set UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN on Vercel.",
      });
    }

    const raw = await readRequestBody(req);
    let body = {};
    try {
      body = JSON.parse(raw.length ? raw.toString("utf8") : "{}");
    } catch {
      return writeJson(res, 400, { ok: false, error: "invalid_json" });
    }

    const email = normalizeEmail(body.email);
    const eventStartIso = String(body.eventStartIso || "").trim();
    const eventTitle = String(body.eventTitle || "Your event").trim().slice(0, 500);
    const gid = String(body.gid || "").replace(/\D/g, "").slice(0, 12) || "0";
    const slug = String(body.slug || "")
      .trim()
      .replace(/[^a-zA-Z0-9_.-]/g, "")
      .slice(0, 180);
    const ticketUrl = String(body.ticketUrl || "").trim().slice(0, 2048);

    if (!looksLikeEmail(email)) {
      return writeJson(res, 400, { ok: false, error: "invalid_email" });
    }
    const eventMs = Date.parse(eventStartIso);
    if (!Number.isFinite(eventMs)) {
      return writeJson(res, 400, { ok: false, error: "invalid_event_start" });
    }

    const secret =
      (process.env.REMINDER_REGISTER_SECRET || "").trim() ||
      (process.env.TM_REMINDER_REGISTER_SECRET || "").trim();
    if (secret) {
      const hdr = String(req.headers.authorization || "").trim();
      const tok = hdr.startsWith("Bearer ") ? hdr.slice(7).trim() : "";
      if (tok !== secret) {
        return writeJson(res, 401, { ok: false, error: "unauthorized" });
      }
    }

    const lookupKey = `reminder:lookup:${gid}:${slug}:${crypto.createHash("sha256").update(email).digest("hex").slice(0, 32)}`;

    let subId = await redis.get(lookupKey);
    let unsubToken = crypto.randomBytes(24).toString("hex");

    const existing =
      subId && typeof subId === "string"
        ? await redis.hgetall(`reminder:sub:${subId}`)
        : null;

    if (existing && existing.unsubToken) {
      unsubToken = String(existing.unsubToken);
    }

    const sameEvent =
      existing &&
      String(existing.eventStartMs || "") === String(eventMs) &&
      String(existing.email || "") === email;

    const fields = {
      email,
      gid,
      slug,
      eventStartMs: String(eventMs),
      eventTitle,
      ticketUrl,
      sent24: sameEvent ? String(existing.sent24 || "0") : "0",
      sent6: sameEvent ? String(existing.sent6 || "0") : "0",
      sent1: sameEvent ? String(existing.sent1 || "0") : "0",
      unsubToken,
      unsubscribed: sameEvent ? String(existing.unsubscribed || "0") : "0",
      updatedMs: String(Date.now()),
    };

    if (subId && typeof subId === "string") {
      await redis.hset(`reminder:sub:${subId}`, fields);
      await redis.zadd("reminder:index", { score: eventMs, member: subId });
    } else {
      subId = crypto.randomBytes(16).toString("hex");
      fields.createdMs = String(Date.now());
      fields.sent24 = "0";
      fields.sent6 = "0";
      fields.sent1 = "0";
      fields.unsubscribed = "0";
      await redis.hset(`reminder:sub:${subId}`, fields);
      await redis.set(lookupKey, subId);
      await redis.zadd("reminder:index", { score: eventMs, member: subId });
    }

    return writeJson(res, 200, {
      ok: true,
      reminderId: subId,
      scheduled: true,
    });
  } catch (e) {
    const msg = (e && e.message) || String(e);
    return writeJson(res, 500, {
      ok: false,
      error: "register_failed",
      detail: msg.slice(0, 200),
    });
  }
};
