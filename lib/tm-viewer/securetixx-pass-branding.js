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
  '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@500;600;700&display=swap" rel="stylesheet"/>' +
  '<link rel="stylesheet" href="/public/securetixx-pass.css"/>' +
  '<meta name="theme-color" content="#ffffff"/>';

const STX_PASS_HEADER =
  '<header class="stx-pass-header" role="banner">' +
  '<div class="stx-pass-header-inner">' +
  '<a class="stx-pass-mark" href="/" aria-label="SecureTixx home">' +
  '<span class="stx-pass-mark-dot" aria-hidden="true"></span>SecureTixx</a>' +
  '<a class="stx-pass-wallet-link" href="/my-tickets">My tickets</a>' +
  "</div></header>";

const STX_PASS_FOOTER =
  '<footer class="stx-pass-footer" role="contentinfo">' +
  '<div class="stx-pass-footer-inner">' +
  "<p>&copy; SecureTixx · Verified pass delivery</p>" +
  "<p>Ticket above issued via Ticketmaster</p>" +
  "</div></footer>";

const DEFAULT_ALERT_BODY =
  '<span class="stx-pass-alert-em">Self-invalidates 15 min before showtime.</span> ' +
  "Live rotating SafeTix&trade; barcode &mdash; be at the gate with this page " +
  "<strong>open and at full brightness, 45 min early</strong>. " +
  "No screenshots. Do not close this page.";

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
    '<p class="stx-pass-alert-label">Time-critical</p>' +
    '<p class="stx-pass-alert-title">Read before opening</p>' +
    '<p class="stx-pass-alert-body">' +
    body +
    "</p></aside>"
  );
}

function wrapPassColumn(out) {
  if (out.includes('class="stx-pass-column"')) return out;

  const withAlert = out.replace(
    /(<aside class="stx-pass-alert"[\s\S]*?<\/aside>)\s*(<main class="stx-pass-main"[^>]*>)/i,
    '<div class="stx-pass-column">$1$2',
  );
  if (withAlert !== out) {
    return withAlert.replace(
      /(<\/main>)\s*(<footer class="stx-pass-footer")/i,
      "$1</div>$2",
    );
  }

  return out.replace(
    /(<main class="stx-pass-main"[^>]*>)/i,
    '<div class="stx-pass-column">' + buildStxAlert(null) + "$1",
  ).replace(
    /(<\/main>)\s*(<footer class="stx-pass-footer")/i,
    "$1</div>$2",
  );
}

/**
 * SecureTixx pass shell: clean column layout; TM ticket card unchanged.
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

  out = wrapPassColumn(out);

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
