"use strict";

/** Run the standard Vercel build with TM_VERCEL_SITE set (cross-platform). */
const { execSync } = require("child_process");
const path = require("path");

const site = (process.argv[2] || process.env.TM_VERCEL_SITE || "").trim();
if (!site) {
  console.error("Usage: node scripts/build-with-site.js <tm-vercel-site|securetixx-vercel-site>");
  process.exit(1);
}

process.env.TM_VERCEL_SITE = site;
const root = path.join(__dirname, "..");
const cmd =
  "node scripts/write-viewer-login-url.js && " +
  "node scripts/write-viewer-api-base.js && " +
  "node scripts/write-viewer-mail-api-base.js && " +
  "node scripts/sync-public.js";

console.log("[build-with-site] TM_VERCEL_SITE=" + site);
execSync(cmd, { cwd: root, stdio: "inherit", env: process.env });
