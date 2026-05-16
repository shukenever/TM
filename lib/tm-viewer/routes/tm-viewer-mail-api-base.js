"use strict";

/**
 * GET /api/tm-viewer/tm-viewer-mail-api-base — same as /api/tm-viewer-mail-api-base;
 * lives under api/tm-viewer/ so deploy trees match Explorer / Vercel routing.
 */
module.exports = (req, res) => {
  const baked = (process.env.TM_VIEWER_MAIL_API_BASE || "").trim().replace(/\/+$/, "");
  const body =
    "/* Vercel: TM_VIEWER_MAIL_API_BASE env, or empty → same-origin transfer */\n" +
    `window.TM_VIEWER_MAIL_API_BASE = ${JSON.stringify(baked)};\n`;
  res.writeHead(200, {
    "Content-Type": "application/javascript; charset=utf-8",
    "Cache-Control": "no-store",
    "Content-Length": Buffer.byteLength(body),
    "Access-Control-Allow-Origin": "*",
  });
  res.end(body);
};
