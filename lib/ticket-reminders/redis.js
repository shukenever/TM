"use strict";

const { Redis } = require("@upstash/redis");

function getRedis() {
  const url = (process.env.UPSTASH_REDIS_REST_URL || "").trim();
  const token = (process.env.UPSTASH_REDIS_REST_TOKEN || "").trim();
  if (!url || !token) return null;
  return new Redis({ url, token });
}

module.exports = { getRedis };
