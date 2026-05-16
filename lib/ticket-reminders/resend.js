"use strict";

/**
 * Env: RESEND_API_KEY, RESEND_FROM (e.g. "Acme Tickets <notify@yourdomain.com>")
 */
async function sendResendEmail({ to, subject, html, text }) {
  const key = (process.env.RESEND_API_KEY || "").trim();
  const from = (process.env.RESEND_FROM || "").trim();
  if (!key || !from) {
    const err = new Error("resend_not_configured");
    err.code = "resend_not_configured";
    throw err;
  }
  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from,
      to: Array.isArray(to) ? to : [to],
      subject,
      html,
      text: text || stripHtml(html),
    }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const err = new Error(j.message || `resend_http_${r.status}`);
    err.code = "resend_failed";
    err.detail = j;
    throw err;
  }
  return j;
}

function stripHtml(html) {
  return String(html || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

module.exports = { sendResendEmail };
