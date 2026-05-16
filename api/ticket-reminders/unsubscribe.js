"use strict";

const { getRedis } = require("./_redis");
const { writeText } = require("../tm-viewer/_http");

module.exports = async (req, res) => {
  try {
    if (req.method !== "GET") {
      res.writeHead(405, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Method Not Allowed");
      return;
    }

    let subId = "";
    let token = "";
    try {
      const u = new URL(req.url || "/", "http://localhost");
      subId = String(u.searchParams.get("sub") || "").trim();
      token = String(u.searchParams.get("t") || "").trim();
    } catch {
      subId = "";
      token = "";
    }

    const redis = getRedis();
    if (!redis || !subId || !token) {
      res.writeHead(400, {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
      });
      res.end("<p>Invalid unsubscribe link.</p>");
      return;
    }

    const sub = await redis.hgetall(`reminder:sub:${subId}`);
    if (!sub || String(sub.unsubToken || "") !== token) {
      res.writeHead(403, {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
      });
      res.end("<p>This unsubscribe link is invalid or expired.</p>");
      return;
    }

    await redis.hset(`reminder:sub:${subId}`, {
      unsubscribed: "1",
      updatedMs: String(Date.now()),
    });

    res.writeHead(200, {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
    });
    res.end(
      "<p>You’re unsubscribed from event reminders for this ticket.</p>",
    );
  } catch {
    res.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("error");
  }
};
