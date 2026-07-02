"use strict";

/**
 * SecureTixx deploy: copy ticketmaster/securetixx-vercel-site → public/
 * (same layout as sync-public.js, different frontend source).
 */
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const pub = path.join(root, "public");
const siteSrc = path.join(root, "ticketmaster", "securetixx-vercel-site");

const NAMES = [
  "index.html",
  "login.html",
  "my-tickets.html",
  "shop.html",
  "tickets",
  "tm-email-gate.js",
  "tm_viewer_login_url.js",
  "tm_viewer_api_base.js",
  "tm_viewer_mail_api_base.js",
  "tm_viewer_link_registry.json",
];

function resolveSourcePath(name) {
  const fromSite = path.join(siteSrc, name);
  if (fs.existsSync(fromSite)) return fromSite;
  const primary = path.join(root, name);
  if (fs.existsSync(primary)) return primary;
  return null;
}

const includeTickets = /^(1|true|yes|on)$/i.test(
  (process.env.TM_VERCEL_INCLUDE_TICKETS || "").trim(),
);

const sources = {};
for (const name of NAMES) {
  if (name === "tickets" && !includeTickets) continue;
  const src = resolveSourcePath(name);
  if (src) sources[name] = src;
}

const sitePublic = path.join(siteSrc, "public");
if (fs.existsSync(sitePublic) && fs.statSync(sitePublic).isDirectory()) {
  sources["public/securetixx-site"] = sitePublic;
}

fs.rmSync(pub, { recursive: true, force: true });
fs.mkdirSync(pub, { recursive: true });

for (const name of NAMES) {
  if (name === "tickets" && !includeTickets) {
    console.warn("[sync-public-securetixx] skip tickets/");
    continue;
  }
  const src = sources[name];
  if (!src) {
    console.warn("[sync-public-securetixx] skip (missing):", name);
    continue;
  }
  const dst = path.join(pub, name);
  const st = fs.statSync(src);
  if (st.isDirectory()) {
    fs.cpSync(src, dst, { recursive: true });
  } else {
    fs.copyFileSync(src, dst);
  }
}

if (sources["public/securetixx-site"]) {
  const dstPub = path.join(pub, "public");
  fs.mkdirSync(dstPub, { recursive: true });
  fs.cpSync(sources["public/securetixx-site"], dstPub, { recursive: true });
  console.log("[sync-public-securetixx] copied securetixx-vercel-site/public → public/public");
}

const assets = path.join(root, "tm_event_assets");
if (fs.existsSync(assets) && fs.statSync(assets).isDirectory()) {
  fs.cpSync(assets, path.join(pub, "tm_event_assets"), { recursive: true });
}

const localSlugSrc = path.join(siteSrc, "local-demo-pass.html");
const localSlugDst = path.join(pub, "tickets", "0", "temp-email-preview.html");
if (fs.existsSync(localSlugSrc)) {
  fs.mkdirSync(path.dirname(localSlugDst), { recursive: true });
  fs.copyFileSync(localSlugSrc, localSlugDst);
  console.log("[sync-public-securetixx] wrote slug preview", localSlugDst);
}

console.log("[sync-public-securetixx] wrote", pub);
