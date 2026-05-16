/**
 * Scheduled reminders via Resend (24h / 3h / 1h before each event — uses `eventStartMs` per subscriber).
 *
 * Env: CRON_SECRET — set on Vercel so only Cron invocations pass Authorization: Bearer …
 * (if unset, endpoint is publicly callable — set CRON_SECRET in production).
 */

"use strict";

const { getRedis } = require("./redis");
const { sendResendEmail } = require("./resend");
const { writeJson, writeText } = require("../tm-viewer/http");
const {
  loadReminderDb,
  saveReminderDb,
  removeSub,
} = require("./file-db");

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function publicOrigin() {
  return String(process.env.TICKETS_PUBLIC_ORIGIN || "https://tixx.pw").replace(
    /\/+$/,
    "",
  );
}

function unsubFooter(subId, unsubToken) {
  const base = publicOrigin();
  const href = `${base}/api/ticket-reminders/unsubscribe?sub=${encodeURIComponent(subId)}&t=${encodeURIComponent(unsubToken)}`;
  return `<p style="color:#64748b;font-size:13px;margin-top:24px"><a href="${escapeHtml(href)}">Unsubscribe</a> from these reminders.</p>`;
}

function cronAuthorized(req) {
  const secret = (process.env.CRON_SECRET || "").trim();
  if (!secret) return true;
  const hdr = String(req.headers.authorization || "").trim();
  const bearer = hdr.startsWith("Bearer ") ? hdr.slice(7).trim() : "";
  return bearer === secret;
}

function dateSlotsUtc(reminderDate) {
  const d = String(reminderDate || "").trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return null;
  const at00 = Date.parse(`${d}T00:00:00Z`);
  const at12 = Date.parse(`${d}T12:00:00Z`);
  const at18 = Date.parse(`${d}T18:00:00Z`);
  const end = Date.parse(`${d}T23:59:59Z`);
  if (![at00, at12, at18, end].every(Number.isFinite)) return null;
  return { at00, at12, at18, end };
}

async function sendMilestone({ subId, sub, label }) {
  const email = sub.email;
  const title = escapeHtml(sub.eventTitle || "Your event");
  const when = new Date(Number(sub.eventStartMs)).toUTCString();
  const ticketUrl = sub.ticketUrl
    ? `<p><a href="${escapeHtml(sub.ticketUrl)}">Open your ticket</a></p>`
    : "";
  const unsubTok = String(sub.unsubToken || "");

  let subject;
  let html;

  if (label === "24h") {
    subject = `Reminder: ${sub.eventTitle || "Your event"} is tomorrow`;
    html =
      `<p>Hi,</p>` +
      `<p>This is a heads-up that <strong>${title}</strong> starts soon (<strong>${escapeHtml(when)}</strong>).</p>` +
      `<p>Plan to arrive early: allow time for traffic, parking, and venue security.</p>` +
      `<p>Have your ticket barcode ready before you reach the entrance.</p>` +
      ticketUrl +
      `<p style="color:#64748b;font-size:13px;margin-top:16px">You received this because you entered your email when viewing your ticket online.</p>` +
      unsubFooter(subId, unsubTok);
  } else if (label === "3h") {
    subject = `Soon: ${sub.eventTitle || "Your event"} — doors opening`;
    html =
      `<p>Hi,</p>` +
      `<p><strong>${title}</strong> is coming up in a few hours (${escapeHtml(when)}).</p>` +
      `<p><strong>Be on time.</strong> Doors may close to late arrivals per venue policy. Charge your phone and keep brightness up so scanners can read your barcode quickly.</p>` +
      ticketUrl +
      `<p style="color:#64748b;font-size:13px;margin-top:16px">You received this because you entered your email when viewing your ticket online.</p>` +
      unsubFooter(subId, unsubTok);
  } else if (label === "1h") {
    subject = `URGENT: ${sub.eventTitle || "Your event"} — scan within the hour`;
    html =
      `<p>Hi,</p>` +
      `<p><strong>Final notice.</strong> <strong>${title}</strong> is within about one hour (${escapeHtml(when)}).</p>` +
      `<p style="border-left:4px solid #b91c1c;padding-left:12px;color:#1e293b"><strong>You must reach the venue and have your ticket scanned at least one hour before the scheduled event time.</strong> If you fail to arrive and scan your ticket by then, <strong>your ticket may be deleted or voided</strong> and your seats may be released — entry will not be guaranteed.</p>` +
      `<p>Go to the entrance immediately with your barcode ready to scan.</p>` +
      ticketUrl +
      unsubFooter(subId, unsubTok);
  } else if (label === "date-00") {
    subject = `Reminder: ${sub.eventTitle || "Your event"} is today`;
    html =
      `<p>Hi,</p>` +
      `<p><strong>${title}</strong> is scheduled for today.</p>` +
      `<p>This is your first same-day reminder. Keep your ticket ready and plan your arrival.</p>` +
      ticketUrl +
      unsubFooter(subId, unsubTok);
  } else if (label === "date-12") {
    subject = `Today: ${sub.eventTitle || "Your event"} — midday reminder`;
    html =
      `<p>Hi,</p>` +
      `<p><strong>${title}</strong> is happening today.</p>` +
      `<p>Midday check-in: confirm travel and keep your barcode accessible.</p>` +
      ticketUrl +
      unsubFooter(subId, unsubTok);
  } else if (label === "date-18") {
    subject = `Final same-day reminder: ${sub.eventTitle || "Your event"}`;
    html =
      `<p>Hi,</p>` +
      `<p><strong>${title}</strong> is tonight.</p>` +
      `<p>Final reminder to head out and have your ticket open for scanning.</p>` +
      ticketUrl +
      unsubFooter(subId, unsubTok);
  }

  if (!subject || !html) return;

  await sendResendEmail({
    to: email,
    subject,
    html,
    text: `${subject}\n\n${sub.eventTitle}\n${when}\n${sub.ticketUrl || ""}`,
  });
}

module.exports = async (req, res) => {
  try {
    if (req.method !== "GET" && req.method !== "POST") {
      return writeJson(res, 405, { ok: false, error: "method_not_allowed" });
    }

    if (!cronAuthorized(req)) {
      return writeJson(res, 401, { ok: false, error: "cron_unauthorized" });
    }

    if (
      !(process.env.RESEND_API_KEY || "").trim() ||
      !(process.env.RESEND_FROM || "").trim()
    ) {
      return writeJson(res, 503, {
        ok: false,
        error: "resend_not_configured",
        detail: "Set RESEND_API_KEY and RESEND_FROM on Vercel.",
      });
    }

    const redis = getRedis();
    const fileMode = !redis;

    const now = Date.now();
    const windowPast = 2 * 3600000;
    const windowFuture = 26 * 3600000;
    const minScore = now - windowPast;
    const maxScore = now + windowFuture;

    let ids = [];
    let fileCtx = null;
    if (fileMode) {
      fileCtx = await loadReminderDb();
      ids = Object.keys(fileCtx.db.subs || {});
    } else {
      ids = await redis.zrange("reminder:index", minScore, maxScore, {
        byScore: true,
      });
      if (!Array.isArray(ids)) ids = [];
    }

    let sent24 = 0;
    let sent3 = 0;
    let sent1 = 0;
    let sentDate00 = 0;
    let sentDate12 = 0;
    let sentDate18 = 0;
    let skipped = 0;
    let cleaned = 0;
    let dirty = false;
    let sendErrors = 0;
    const sendErrorSamples = [];

    for (const subId of ids) {
      const sub = fileMode
        ? fileCtx.db.subs[subId]
        : await redis.hgetall(`reminder:sub:${subId}`);
      if (!sub || !sub.email || sub.unsubscribed === "1") {
        skipped++;
        continue;
      }
      const T = Number(sub.eventStartMs);
      if (!Number.isFinite(T)) {
        skipped++;
        continue;
      }

      const msLeft = T - now;
      const reminderMode = String(sub.reminderMode || "event_time");
      const reminderDate = String(sub.reminderDate || "");

      if (reminderMode === "date_slots" && reminderDate) {
        const slots = dateSlotsUtc(reminderDate);
        if (!slots) {
          skipped++;
          continue;
        }

        if (now > slots.end + 2 * 3600000) {
          if (fileMode) {
            removeSub(fileCtx.db, subId);
            dirty = true;
          } else {
            await redis.del(`reminder:sub:${subId}`);
            await redis.zrem("reminder:index", subId);
          }
          cleaned++;
          continue;
        }

        try {
          if (now >= slots.at00 && sub.sentDate00 !== "1") {
            await sendMilestone({ subId, sub, label: "date-00" });
            if (fileMode) {
              sub.sentDate00 = "1";
              dirty = true;
            } else {
              await redis.hset(`reminder:sub:${subId}`, "sentDate00", "1");
            }
            sentDate00++;
          }
          if (now >= slots.at12 && sub.sentDate12 !== "1") {
            await sendMilestone({ subId, sub, label: "date-12" });
            if (fileMode) {
              sub.sentDate12 = "1";
              dirty = true;
            } else {
              await redis.hset(`reminder:sub:${subId}`, "sentDate12", "1");
            }
            sentDate12++;
          }
          if (now >= slots.at18 && sub.sentDate18 !== "1") {
            await sendMilestone({ subId, sub, label: "date-18" });
            if (fileMode) {
              sub.sentDate18 = "1";
              dirty = true;
            } else {
              await redis.hset(`reminder:sub:${subId}`, "sentDate18", "1");
            }
            sentDate18++;
          }
        } catch (e) {
          skipped++;
        }
        continue;
      }

      if (msLeft < -7200000) {
        if (fileMode) {
          removeSub(fileCtx.db, subId);
          dirty = true;
        } else {
          await redis.del(`reminder:sub:${subId}`);
          await redis.zrem("reminder:index", subId);
        }
        cleaned++;
        continue;
      }

      if (msLeft <= 0) continue;

      try {
        if (msLeft <= 24 * 3600000 && sub.sent24 !== "1") {
          await sendMilestone({ subId, sub, label: "24h" });
          if (fileMode) {
            sub.sent24 = "1";
            dirty = true;
          } else {
            await redis.hset(`reminder:sub:${subId}`, "sent24", "1");
          }
          sent24++;
        }
        if (
          msLeft <= 3 * 3600000 &&
          sub.sent3 !== "1" &&
          sub.sent6 !== "1"
        ) {
          await sendMilestone({ subId, sub, label: "3h" });
          if (fileMode) {
            sub.sent3 = "1";
            dirty = true;
          } else {
            await redis.hset(`reminder:sub:${subId}`, "sent3", "1");
          }
          sent3++;
        }
        if (msLeft <= 1 * 3600000 && sub.sent1 !== "1") {
          await sendMilestone({ subId, sub, label: "1h" });
          if (fileMode) {
            sub.sent1 = "1";
            dirty = true;
          } else {
            await redis.hset(`reminder:sub:${subId}`, "sent1", "1");
          }
          sent1++;
        }
      } catch (e) {
        skipped++;
        sendErrors++;
        if (sendErrorSamples.length < 5) {
          const detail =
            (e && (e.code || e.message)) || String(e || "unknown_send_error");
          sendErrorSamples.push(`${subId}:${String(detail).slice(0, 180)}`);
        }
      }
    }

    const summary = {
      ok: true,
      scanned: ids.length,
      sent24,
      sent3,
      sent1,
      sentDate00,
      sentDate12,
      sentDate18,
      skipped,
      cleaned,
      sendErrors,
      at: new Date(now).toISOString(),
      storage: fileMode ? "file_db" : "redis",
    };
    if (sendErrorSamples.length) summary.sendErrorSamples = sendErrorSamples;
    if (fileMode && dirty) {
      await saveReminderDb(fileCtx.filePath, fileCtx.db);
    }

    return writeJson(res, 200, summary);
  } catch (e) {
    const msg = (e && e.message) || String(e);
    return writeText(res, 500, `cron_error: ${msg.slice(0, 400)}`);
  }
};
