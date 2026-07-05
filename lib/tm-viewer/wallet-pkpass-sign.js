"use strict";

const crypto = require("crypto");

function walletEnv() {
  const secret = (
    process.env.TM_WALLET_PKPASS_SECRET ||
    process.env.TM_VIEWER_WALLET_PKPASS_SECRET ||
    ""
  ).trim();
  const passOrigin = (
    process.env.TM_WALLET_PASS_PUBLIC_ORIGIN ||
    process.env.TM_VIEWER_WALLET_PASS_ORIGIN ||
    process.env.TM_VIEWER_WALLET_PUBLIC_ORIGIN ||
    ""
  )
    .trim()
    .replace(/\/+$/, "");
  return { secret, passOrigin };
}

function walletSigningEnabled() {
  const { secret, passOrigin } = walletEnv();
  return Boolean(secret && passOrigin);
}

function b64urlJson(obj) {
  const raw = JSON.stringify(obj);
  return Buffer.from(raw, "utf8")
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function scrapeWalletFields(html) {
  const doc = String(html || "");
  const titleM = doc.match(/<h4 class="tm-pass-title">([^<]*)<\/h4>/i);
  const eventName = titleM ? titleM[1].trim() : "Event";

  const subs = [];
  const subRe = /<span class="tm-pass-sub-line"[^>]*>([^<]*)<\/span>/gi;
  let sm;
  while ((sm = subRe.exec(doc))) subs.push(sm[1].trim());
  const subtitle = subs.join(" · ").slice(0, 300);

  function seat(lbl) {
    const m = doc.match(
      new RegExp(
        `<span class="tm-pass-lbl">${lbl}</span>\\s*<b>([^<]*)</b>`,
        "i",
      ),
    );
    const v = m ? m[1].trim() : "";
    return v && v !== "—" && v !== "-" ? v : "";
  }

  return {
    event_name: eventName.slice(0, 200),
    subtitle: subtitle.slice(0, 300),
    section: seat("SECTION").slice(0, 64),
    row: seat("ROW").slice(0, 64),
    seat: seat("SEAT").slice(0, 64),
  };
}

function signPkpassHref({ gid, slug, fields, pkpassBase, secret }) {
  const payload = {
    v: 1,
    gid: parseInt(String(gid), 10),
    slug: String(slug || "")
      .replace(/[^a-zA-Z0-9_.-]/g, "")
      .slice(0, 200),
    ev: (fields.event_name || "Event").slice(0, 200),
    sec: (fields.section || "").slice(0, 64),
    row: (fields.row || "").slice(0, 64),
    seat: (fields.seat || "").slice(0, 64),
    sub: (fields.subtitle || "").slice(0, 300),
  };
  if (!payload.slug || Number.isNaN(payload.gid)) return null;

  const p = b64urlJson(payload);
  const sig = crypto.createHmac("sha256", secret).update(p, "ascii").digest("hex");
  const q = new URLSearchParams({ p, s: sig });
  const base = String(pkpassBase || "").replace(/\/+$/, "");
  if (!base) return null;
  return `${base}?${q.toString()}`;
}

function escAttr(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;");
}

/**
 * Ensure wallet control is a working <a href=".../api/tm-pkpass?..."> when signing is configured.
 */
function injectWalletPkpassLink(html, { gid, slug, pkpassBase }) {
  if (!walletSigningEnabled()) return html;
  const { secret } = walletEnv();
  const fields = scrapeWalletFields(html);
  const href = signPkpassHref({
    gid,
    slug,
    fields,
    pkpassBase,
    secret,
  });
  if (!href) return html;

  const safeHref = escAttr(href);
  let out = String(html || "");

  out = out.replace(
    /<span class="tm-pass-btn tm-pass-wallet tm-pass-wallet--badge tm-pass-btn--disabled">([\s\S]*?)<\/span>/gi,
    `<a class="tm-pass-btn tm-pass-wallet tm-pass-wallet--badge" href="${safeHref}" rel="noopener">${"$1"}</a>`,
  );

  out = out.replace(
    /<a class="tm-pass-btn tm-pass-wallet tm-pass-wallet--badge" href="[^"]*"/gi,
    `<a class="tm-pass-btn tm-pass-wallet tm-pass-wallet--badge" href="${safeHref}"`,
  );

  if (!out.includes('class="tm-pass-btn tm-pass-wallet tm-pass-wallet--badge"')) {
    return out;
  }

  return out;
}

module.exports = {
  walletEnv,
  walletSigningEnabled,
  scrapeWalletFields,
  signPkpassHref,
  injectWalletPkpassLink,
};
