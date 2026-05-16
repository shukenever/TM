"use strict";

const crypto = require("crypto");

function refKeyForTicket(gid, slug) {
  return `reminder:ref:${gid}:${slug}`;
}

function legacyLookupPattern(gid, slug) {
  return `reminder:lookup:${gid}:${slug}:*`;
}

function legacyLookupKey(gid, slug, email) {
  const h = crypto.createHash("sha256").update(email).digest("hex").slice(0, 32);
  return `reminder:lookup:${gid}:${slug}:${h}`;
}

/**
 * Find all Redis keys for legacy per-email lookups for this ticket.
 */
async function listLegacyLookupKeys(redis, gid, slug) {
  const pattern = legacyLookupPattern(gid, slug);
  let cursor = "0";
  const keys = [];
  do {
    const [next, batch] = await redis.scan(cursor, { match: pattern, count: 200 });
    cursor = next;
    if (batch && batch.length) keys.push(...batch);
  } while (cursor !== "0");
  return keys;
}

/**
 * Collect distinct subIds referenced by legacy lookup keys.
 */
async function subIdsFromLegacyKeys(redis, legacyKeys) {
  const ids = new Set();
  for (const key of legacyKeys) {
    const id = await redis.get(key);
    if (id) ids.add(id);
  }
  return ids;
}

async function pickKeeperSubId(redis, candidates) {
  if (candidates.length === 1) return candidates[0];
  let best = candidates[0];
  let bestTs = -1;
  for (const id of candidates) {
    const h = await redis.hgetall(`reminder:sub:${id}`);
    if (!h || !h.email) continue;
    const ts = Number(h.updatedMs || h.createdMs || 0);
    if (ts > bestTs) {
      bestTs = ts;
      best = id;
    }
  }
  return best;
}

/**
 * Merge sent-* flags across duplicates (avoid re-sending after consolidation).
 */
async function mergedSentFlags(redis, candidates) {
  const out = {
    sent24: "0",
    sent3: "0",
    sent1: "0",
    sentDate00: "0",
    sentDate12: "0",
    sentDate18: "0",
    unsubscribed: "0",
  };
  for (const id of candidates) {
    const h = await redis.hgetall(`reminder:sub:${id}`);
    if (!h) continue;
    if (h.sent24 === "1") out.sent24 = "1";
    if (h.sent3 === "1" || h.sent6 === "1") out.sent3 = "1";
    if (h.sent1 === "1") out.sent1 = "1";
    if (h.sentDate00 === "1") out.sentDate00 = "1";
    if (h.sentDate12 === "1") out.sentDate12 = "1";
    if (h.sentDate18 === "1") out.sentDate18 = "1";
    if (h.unsubscribed === "1") out.unsubscribed = "1";
  }
  return out;
}

module.exports = {
  refKeyForTicket,
  legacyLookupPattern,
  legacyLookupKey,
  listLegacyLookupKeys,
  subIdsFromLegacyKeys,
  pickKeeperSubId,
  mergedSentFlags,
};
