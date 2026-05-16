"use strict";

/**
 * POST /api/ticket-reminders/register
 *
 * One subscriber record per ticket reference (gid + slug). The email field always
 * reflects the latest submission — reminders go to that address only, never every
 * historical address for the same link.
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
  refKeyForTicket,
  listLegacyLookupKeys,
  subIdsFromLegacyKeys,
  pickKeeperSubId,
  mergedSentFlags,
  legacyLookupKey,
} = require("./ref-keys");
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

    const registerSecret =
      (process.env.REMINDER_REGISTER_SECRET || "").trim() ||
      (process.env.TM_REMINDER_REGISTER_SECRET || "").trim();
    if (registerSecret) {
      const hdr = String(req.headers.authorization || "").trim();
      const tok = hdr.startsWith("Bearer ") ? hdr.slice(7).trim() : "";
      if (tok !== registerSecret) {
        return writeJson(res, 401, { ok: false, error: "unauthorized" });
      }
    }

    const rk = refKeyForTicket(gid, slug);
    const legacyKeys = await listLegacyLookupKeys(redis, gid, slug);
    const fromLegacy = await subIdsFromLegacyKeys(redis, legacyKeys);
    const refSub = await redis.get(rk);

    const candidateSet = new Set();
    if (refSub) candidateSet.add(refSub);
    for (const id of fromLegacy) candidateSet.add(id);

    const candidates = [...candidateSet].filter(Boolean);

    let mergeSent = null;
    let subId = null;

    if (candidates.length === 0) {
      subId = null;
    } else if (candidates.length === 1) {
      subId = candidates[0];
    } else {
      mergeSent = await mergedSentFlags(redis, candidates);
      subId = await pickKeeperSubId(redis, candidates);
      for (const id of candidates) {
        if (id !== subId) {
          await redis.del(`reminder:sub:${id}`);
          await redis.zrem("reminder:index", id);
        }
      }
    }

    for (const key of legacyKeys) {
      await redis.del(key);
    }

    let existing =
      subId && typeof subId === "string"
        ? await redis.hgetall(`reminder:sub:${subId}`)
        : null;

    if (subId && (!existing || !existing.email)) {
      await redis.del(`reminder:sub:${subId}`);
      await redis.zrem("reminder:index", subId);
      await redis.del(rk);
      subId = null;
      existing = null;
    }

    let unsubToken = crypto.randomBytes(24).toString("hex");
    if (existing && existing.unsubToken) {
      unsubToken = String(existing.unsubToken);
    }

    const sameEvent =
      existing &&
      String(existing.eventStartMs || "") === String(eventMs);

    let sent24 = "0";
    let sent3 = "0";
    let sent1 = "0";
    let unsubscribed = "0";

    if (existing && sameEvent) {
      if (mergeSent) {
        sent24 = mergeSent.sent24;
        sent3 = mergeSent.sent3;
        sent1 = mergeSent.sent1;
        unsubscribed = mergeSent.unsubscribed;
      } else {
        sent24 = String(existing.sent24 || "0");
        sent3 = String(
          existing.sent3 === "1" || existing.sent6 === "1" ? "1" : "0",
        );
        sent1 = String(existing.sent1 || "0");
        unsubscribed = String(existing.unsubscribed || "0");
      }
    }

    const fields = {
      email,
      gid,
      slug,
      eventStartMs: String(eventMs),
      eventTitle,
      ticketUrl,
      sent24,
      sent3,
      sent1,
      unsubToken,
      unsubscribed,
      updatedMs: String(Date.now()),
    };

    if (!subId || !existing || !existing.email) {
      subId = crypto.randomBytes(16).toString("hex");
      fields.createdMs = String(Date.now());
      fields.sent24 = "0";
      fields.sent3 = "0";
      fields.sent1 = "0";
      fields.unsubscribed = "0";
      await redis.hset(`reminder:sub:${subId}`, fields);
      await redis.zadd("reminder:index", { score: eventMs, member: subId });
    } else {
      if (!sameEvent) {
        fields.sent24 = "0";
        fields.sent3 = "0";
        fields.sent1 = "0";
      }
      await redis.hset(`reminder:sub:${subId}`, fields);
      await redis.zadd("reminder:index", { score: eventMs, member: subId });
    }

    await redis.set(rk, subId);
    await redis.set(legacyLookupKey(gid, slug, email), subId);

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
