"use strict";

/**
 * Serves /tm_viewer_mail_api_base.js via rewrite so pass pages never 404 this script.
 * Browser: set TM_VIEWER_MAIL_API_BASE on Vercel only if it is https:// (e.g. TLS stubby).
 * Do NOT echo TM_VIEWER_EMAIL_BACKEND_URL here (often http:// — mixed content on https sites).
 */
module.exports = (req, res) => {
  const baked = (process.env.TM_VIEWER_MAIL_API_BASE || "").trim().replace(/\/+$/, "");
  const body =
    "/* Vercel function: TM_VIEWER_MAIL_API_BASE env, or empty → same-origin transfer */\n" +
    `window.TM_VIEWER_MAIL_API_BASE = ${JSON.stringify(baked)};\n`;
  res.setHeader("Content-Type", "application/javascript; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.status(200).send(body);
};
