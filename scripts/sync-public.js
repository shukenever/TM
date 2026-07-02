"use strict";

/**
 * Vercel expects a "public" output directory. Copy deployable assets from repo root → public/.
 */
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const pub = path.join(root, "public");
const siteSrc = path.join(root, "ticketmaster", "tm-vercel-site");

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

/** Prefer ticketmaster/tm-vercel-site for Tixx marketplace pages. */
function resolveSourcePath(name) {
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

// Tixx static assets (logo, settings, favicons)
const sitePublic = path.join(siteSrc, "public");
if (fs.existsSync(sitePublic) && fs.statSync(sitePublic).isDirectory()) {
  sources["public/tixx-site"] = sitePublic;
}

fs.rmSync(pub, { recursive: true, force: true });
fs.mkdirSync(pub, { recursive: true });

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

if (sources["public/tixx-site"]) {
  const dstPub = path.join(pub, "public");
  fs.mkdirSync(dstPub, { recursive: true });
  fs.cpSync(sources["public/tixx-site"], dstPub, { recursive: true });
  console.log("[sync-public] copied ticketmaster/tm-vercel-site/public → public/public");
}

// Optional local hero assets from tm_hit_viewer --download-event-images
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

/** Local-only stub: real /tickets/:gid/:slug path for previewing the email gate (not a real TM pass). */
const localSlugSrc = path.join(root, "local-demo-pass.html");
const localSlugDst = path.join(pub, "tickets", "0", "temp-email-preview.html");
if (fs.existsSync(localSlugSrc)) {
  fs.mkdirSync(path.dirname(localSlugDst), { recursive: true });
  fs.copyFileSync(localSlugSrc, localSlugDst);
  console.log("[sync-public] wrote slug preview", localSlugDst);
}

console.log("[sync-public] wrote", pub);
