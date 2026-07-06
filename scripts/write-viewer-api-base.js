"use strict";

const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const outFile = path.join(root, "tm_viewer_api_base.js");

const publicApi = (process.env.TM_VIEWER_PUBLIC_API || "").trim().replace(/\/+$/, "");
const backend = (process.env.TM_VIEWER_BACKEND_URL || "").trim();
// Only absolute http(s) URLs are used in the browser. Otherwise same-origin /api/tm-viewer/* proxy.
const clientBase =
  publicApi && /^https?:\/\//i.test(publicApi) ? publicApi : backend ? "" : "";
const escaped = JSON.stringify(clientBase);

const body =
  "/* Build: TM_VIEWER_PUBLIC_API = direct API; TM_VIEWER_BACKEND_URL = same-origin proxy (empty = use location.origin). */\n" +
  `window.TM_VIEWER_API_BASE = ${escaped};\n`;

fs.writeFileSync(outFile, body, "utf8");
console.log(
  "[write-viewer-api-base] wrote tm_viewer_api_base.js →",
  clientBase || (backend ? "same-origin (proxy)" : "(empty)")
);
