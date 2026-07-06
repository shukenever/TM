"use strict";

/**
 * Vercel expects a "public" output directory. Copy deployable assets from repo root → public/.
 *
 * Env:
 *   TM_VERCEL_SITE — ticketmaster subfolder (default tm-vercel-site). Set securetixx-vercel-site on SecureTixx deploy.
 *   TM_VERCEL_INCLUDE_TICKETS — include static tickets/ tree (offline demo only).
 */
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const pub = path.join(root, "public");

function resolveSiteFolder() {
  const explicit = (process.env.TM_VERCEL_SITE || "").trim();
  if (explicit) return explicit;
  if (process.env.VERCEL === "1") {
    const proj = (process.env.VERCEL_PROJECT_NAME || "").toLowerCase();
    const url = (process.env.VERCEL_URL || "").toLowerCase();
    if (
      proj === "tmnew" ||
      proj.includes("securetixx") ||
      url.includes("securetixx")
    ) {
      return "securetixx-vercel-site";
    }
  }
  return "tm-vercel-site";
}

const siteFolder = resolveSiteFolder();
const siteSrc = path.join(root, "ticketmaster", siteFolder);

const NAMES = [
  "index.html",
  "login.html",
  "help.html",
  "my-tickets.html",
  "shop.html",
  "tickets",
  "tm-email-gate.js",
  "tm_viewer_login_url.js",
  "tm_viewer_api_base.js",
  "tm_viewer_mail_api_base.js",
  "tm_viewer_link_registry.json",
];

/** Shared registry JSON — same file for Tixx and SecureTixx (tm_viewer_link_registry.py). */
function resolveSourcePath(name) {
  if (name === "tm_viewer_link_registry.json") {
    const shared = path.join(root, name);
    if (fs.existsSync(shared)) return shared;
  }
  const fromSite = path.join(siteSrc, name);
  if (fs.existsSync(fromSite)) return fromSite;
  const primary = path.join(root, name);
  if (fs.existsSync(primary)) return primary;
  const fallback = path.join(root, "public", name);
  if (fs.existsSync(fallback)) {
    console.warn("[sync-public] using public/" + name + " (no root copy)");
    return fallback;
  }
  return null;
}

/** Never copy tickets/ into public unless TM_VERCEL_INCLUDE_TICKETS=1 — static files win over rewrites and would bypass transfer stubs / ?access=. */
const includeTickets = /^(1|true|yes|on)$/i.test(
  (process.env.TM_VERCEL_INCLUDE_TICKETS || "").trim(),
);

const sources = {};
for (const name of NAMES) {
  if (name === "tickets" && !includeTickets) {
    continue;
  }
  const src = resolveSourcePath(name);
  if (src) sources[name] = src;
}

const sitePublic = path.join(siteSrc, "public");
if (fs.existsSync(sitePublic) && fs.statSync(sitePublic).isDirectory()) {
  sources["public/site-assets"] = sitePublic;
}

fs.rmSync(pub, { recursive: true, force: true });
fs.mkdirSync(pub, { recursive: true });

console.log("[sync-public] site:", siteFolder);

for (const name of NAMES) {
  if (name === "tickets" && !includeTickets) {
    console.warn(
      "[sync-public] skip tickets/ (set TM_VERCEL_INCLUDE_TICKETS=1 only for fully offline demo builds)",
    );
    continue;
  }
  const src = sources[name];
  if (!src) {
    console.warn("[sync-public] skip (missing):", name);
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

if (sources["public/site-assets"]) {
  const dstPub = path.join(pub, "public");
  fs.mkdirSync(dstPub, { recursive: true });
  fs.cpSync(sources["public/site-assets"], dstPub, { recursive: true });
  console.log("[sync-public] copied ticketmaster/" + siteFolder + "/public → public/public");
  const rootIco = path.join(sources["public/site-assets"], "favicon.ico");
  if (fs.existsSync(rootIco)) {
    fs.copyFileSync(rootIco, path.join(pub, "favicon.ico"));
    console.log("[sync-public] copied favicon.ico → public/favicon.ico");
  }
}

const assets = path.join(root, "tm_event_assets");
if (fs.existsSync(assets) && fs.statSync(assets).isDirectory()) {
  fs.cpSync(assets, path.join(pub, "tm_event_assets"), { recursive: true });
}

const gatewaySrc = path.join(root, "..", "tm-link-gateway", "gateway.html");
if (fs.existsSync(gatewaySrc)) {
  fs.copyFileSync(gatewaySrc, path.join(pub, "gateway.html"));
} else {
  console.warn("[sync-public] skip gateway.html (tm-link-gateway missing)");
}

const localSlugSrc = path.join(siteSrc, "local-demo-pass.html");
const localSlugFallback = path.join(root, "local-demo-pass.html");
const localSlugDst = path.join(pub, "tickets", "0", "temp-email-preview.html");
const localDemo = fs.existsSync(localSlugSrc)
  ? localSlugSrc
  : fs.existsSync(localSlugFallback)
    ? localSlugFallback
    : null;
if (localDemo) {
  fs.mkdirSync(path.dirname(localSlugDst), { recursive: true });
  fs.copyFileSync(localDemo, localSlugDst);
  console.log("[sync-public] wrote slug preview", localSlugDst);
}

console.log("[sync-public] wrote", pub);
