"use strict";

/** True when request Host is securetixx.com (not tixx.pw). */
function isSecureTixxHost(host) {
  const h = String(host || "")
    .split(":")[0]
    .trim()
    .toLowerCase();
  return h === "securetixx.com" || h === "www.securetixx.com";
}

function isTixxHost(host) {
  const h = String(host || "")
    .split(":")[0]
    .trim()
    .toLowerCase();
  return h === "tixx.pw" || h === "www.tixx.pw" || h === "tixx.cc" || h === "www.tixx.cc";
}

const STX_PASS_HEAD =
  '<link rel="preconnect" href="https://fonts.googleapis.com"/>' +
  '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>' +
  '<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@500;600;700;800&display=swap" rel="stylesheet"/>' +
  '<link rel="stylesheet" href="/public/securetixx-pass.css"/>' +
  '<meta name="theme-color" content="#047857"/>';

const STX_PASS_HEADER =
  '<header class="stx-pass-header" role="banner">' +
  '<div class="stx-pass-header-inner">' +
  '<span class="stx-pass-header-side" aria-hidden="true"></span>' +
  '<a class="stx-pass-mark" href="/" aria-label="SecureTixx home">SecureTixx</a>' +
  '<a class="stx-pass-wallet-link" href="/my-tickets">My tickets</a>' +
  "</div></header>";

const STX_PASS_FOOTER =
  '<footer class="stx-pass-footer" role="contentinfo">' +
  '<div class="stx-pass-footer-inner">' +
  '<p class="stx-pass-footer-brand">SecureTixx</p>' +
  '<p class="stx-pass-footer-line">Verified mobile pass delivery</p>' +
  '<p class="stx-pass-footer-line stx-pass-footer-muted">Attn: Fan Support · 7060 Hollywood Blvd, Los Angeles, CA 90028</p>' +
  '<p class="stx-pass-footer-copy">&copy; SecureTixx. All rights reserved.</p>' +
  '<p class="stx-pass-footer-note">Ticket shown above is issued via Ticketmaster.</p>' +
  "</div></footer>";

const DEFAULT_ALERT_BODY =
  '<span class="stx-pass-alert-em">This ticket self-invalidates 15 min before showtime</span> &mdash; ' +
  "this is a live rotating SafeTix&trade; barcode that goes permanently dead if not scanned in time. " +
  "Be at the gate with this page <strong>already open, full brightness</strong>, " +
  "<strong>45 min early</strong>. Scan immediately at the front. " +
  "<strong>No screenshots &mdash; they won&rsquo;t scan. Do not close this page.</strong>";

function extractArrivalWarningBody(html) {
  const m = html.match(
    /<div class="tm-arrival-warning__body"[^>]*>([\s\S]*?)<\/div>/i,
  );
  if (!m) return null;
  let body = m[1].trim();
  body = body.replace(/class="tm-warn-red"/gi, 'class="stx-pass-alert-em"');
  return body || null;
}

function buildStxAlert(bodyHtml) {
  const body = bodyHtml || DEFAULT_ALERT_BODY;
  return (
    '<aside class="stx-pass-alert" role="alert" aria-live="polite">' +
    '<div class="stx-pass-alert-inner">' +
    '<div class="stx-pass-alert-head">' +
    '<span class="stx-pass-alert-icon" aria-hidden="true">' +
    '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" xmlns="http://www.w3.org/2000/svg">' +
    '<path d="M12 9v4m0 3h.01" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>' +
    '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/>' +
    "</svg></span>" +
    '<div class="stx-pass-alert-titles">' +
    '<p class="stx-pass-alert-kicker">Time-critical</p>' +
    '<p class="stx-pass-alert-title">Read before opening</p>' +
    "</div></div>" +
    '<div class="stx-pass-alert-body">' +
    body +
    "</div></div></aside>"
  );
}

/**
 * SecureTixx pass shell: custom header, alert, footer, and stage.
 * Ticket card (.tm-pass-card / .safetix-slot) is left unchanged.
 */
function applySecureTixxPassBranding(html) {
  let out = String(html || "");

  out = out.replace(/<meta name="theme-color" content="#026cdf"\s*\/?>/gi, "");

  const alertBody = extractArrivalWarningBody(out);

  out = out.replace(
    /<header class="tm-pass-chrome-bar[^>]*>[\s\S]*?<\/header>/i,
    STX_PASS_HEADER,
  );

  out = out.replace(
    /<div class="tm-arrival-warning[^"]*"[^>]*>[\s\S]*?<\/div>\s*<\/div>/i,
    buildStxAlert(alertBody),
  );

  if (!out.includes('class="stx-pass-alert"')) {
    out = out.replace(STX_PASS_HEADER, STX_PASS_HEADER + buildStxAlert(null));
  }

  out = out.replace(
    /<footer class="tm-site-footer tm-site-footer--pass-minimal[^>]*>[\s\S]*?<\/footer>/i,
    STX_PASS_FOOTER,
  );

  out = out.replace(/<main(\s[^>]*)?>/i, (m, attrs) => {
    const a = attrs || "";
    if (/class="/i.test(a)) {
      if (/stx-pass-main/.test(a)) return m;
      return m.replace(/class="([^"]*)"/i, 'class="$1 stx-pass-main"');
    }
    return '<main class="stx-pass-main"' + a + ">";
  });

  out = out.replace(/<html(\s[^>]*)?>/i, (m, attrs) => {
    const a = attrs || "";
    if (/class="/i.test(a)) {
      return m.replace(/class="([^"]*)"/i, 'class="$1 stx-pass-html"');
    }
    return `<html class="stx-pass-html"${a}>`;
  });

  out = out.replace(/<body(\s[^>]*)?>/i, (m, attrs) => {
    const a = attrs || "";
    if (/class="/i.test(a)) {
      return m.replace(/class="([^"]*)"/i, 'class="$1 stx-pass-app"');
    }
    return `<body class="stx-pass-app"${a}>`;
  });

  const hm = out.match(/<head[^>]*>/i);
  if (hm) {
    const end = hm.index + hm[0].length;
    if (!out.includes("securetixx-pass.css")) {
      out = out.slice(0, end) + STX_PASS_HEAD + out.slice(end);
    }
  } else {
    out = STX_PASS_HEAD + out;
  }

  return out;
}

module.exports = {
  isSecureTixxHost,
  isTixxHost,
  applySecureTixxPassBranding,
};
