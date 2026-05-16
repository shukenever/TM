"use strict";

const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const outFile = path.join(root, "tm_viewer_mail_api_base.js");

/** Stubby TM viewer proxy (e.g. http://HOST:9440) — same routes as stubby /api/tm-viewer/*. */
const mail = (process.env.TM_VIEWER_MAIL_API_BASE || process.env.TM_VIEWER_EMAIL_BACKEND_URL || "")
  .trim()
  .replace(/\/+$/, "");

const body =
  "/* Build: TM_VIEWER_MAIL_API_BASE or TM_VIEWER_EMAIL_BACKEND_URL → transfer host (stubby :9440). " +
  "Empty = use TM_VIEWER_API_BASE / origin (may use Vercel serverless). */\n" +
  `window.TM_VIEWER_MAIL_API_BASE = ${JSON.stringify(mail)};\n`;

fs.writeFileSync(outFile, body, "utf8");
console.log(
  "[write-viewer-mail-api-base] wrote tm_viewer_mail_api_base.js →",
  mail || "(empty → fallback to TM_VIEWER_API_BASE)",
);
