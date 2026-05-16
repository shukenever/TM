"use strict";

const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const outFile = path.join(root, "tm_viewer_login_url.js");

const DEFAULT = "/login";
const raw = (process.env.TM_VIEWER_LOGIN_URL || "").trim();
const url = raw || DEFAULT;
const escaped = JSON.stringify(url);

const body =
  "/* Generated at build time. Override with Vercel env TM_VIEWER_LOGIN_URL. */\n" +
  `window.TM_VIEWER_LOGIN_URL = ${escaped};\n`;

fs.writeFileSync(outFile, body, "utf8");
console.log("[write-viewer-login-url] wrote tm_viewer_login_url.js →", url);
