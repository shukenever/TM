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
  '<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap" rel="stylesheet"/>' +
  '<link rel="stylesheet" href="/public/securetixx-pass.css"/>' +
  '<meta name="theme-color" content="#064e3b"/>';

const STX_PASS_BG =
  '<div class="stx-pass-bg" aria-hidden="true">' +
  '<div class="stx-pass-bg-glow stx-pass-bg-glow--a"></div>' +
  '<div class="stx-pass-bg-glow stx-pass-bg-glow--b"></div>' +
  '<div class="stx-pass-bg-mesh"></div>' +
  "</div>";

const STX_PASS_HEADER =
  '<header class="stx-pass-header" role="banner">' +
  '<div class="stx-pass-header-inner">' +
  '<a class="stx-pass-mark" href="/" aria-label="SecureTixx home">SecureTixx</a>' +
  '<a class="stx-pass-wallet-link" href="/my-tickets">My tickets</a>' +
  "</div></header>";

const STX_PASS_FOOTER =
  '<footer class="stx-pass-footer" role="contentinfo">' +
  '<div class="stx-pass-footer-inner">' +
  "<span>SecureTixx verified delivery</span>" +
  "</div></footer>";

const STX_BRAND_STRIP =
  '<div class="tm-pass-brand-strip stx-brand-strip" aria-hidden="true">' +
  '<span class="stx-card-brand">SecureTixx</span></div>';

const DEFAULT_ALERT_BODY =
  '<span class="stx-pass-alert-em">Self-invalidates 15 min before showtime.</span> ' +
  "Live SafeTix&trade; barcode &mdash; keep this page <strong>open at full brightness</strong> " +
  "and arrive <strong>45 min early</strong>. No screenshots.";

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
    '<span class="stx-pass-alert-badge">!</span>' +
    '<div class="stx-pass-alert-text">' +
    '<p class="stx-pass-alert-title">Time-critical &mdash; read before opening</p>' +
    '<p class="stx-pass-alert-body">' +
    body +
    "</p></div></aside>"
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

  return out
    .replace(
      /(<main class="stx-pass-main"[^>]*>)/i,
      '<div class="stx-pass-column">' + buildStxAlert(null) + "$1",
    )
    .replace(
      /(<\/main>)\s*(<footer class="stx-pass-footer")/i,
      "$1</div>$2",
    );
}

function greenifyTicketCard(html) {
  let out = html;
  out = out.replace(
    /<div class="tm-pass-brand-strip"[^>]*>[\s\S]*?<\/div>/gi,
    STX_BRAND_STRIP,
  );
  out = out.replace(
    /class="([^"]*\btm-pass-hero--tmblue\b[^"]*)"/gi,
    'class="$1 stx-hero-green"',
  );
  out = out.replace(/fill="#026cdf"/gi, 'fill="#10b981"');
  out = out.replace(
    /<img class="tm-wordmark-img[^"]*"[^>]*alt="Ticketmaster"[^>]*\/>/gi,
    '<span class="stx-hero-watermark" aria-hidden="true">SecureTixx</span>',
  );
  out = out.replace(
    /<img([^>]*?)src="https:\/\/upload\.wikimedia\.org\/wikipedia\/commons\/7\/7d\/TicketMaster_wordmark\.svg"([^>]*?)>/gi,
    '<span class="stx-hero-watermark" aria-hidden="true">SecureTixx</span>',
  );
  return out;
}

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
  out = greenifyTicketCard(out);

  out = out.replace(/<body(\s[^>]*)?>/i, (m, attrs) => {
    const a = attrs || "";
    const inject = STX_PASS_BG;
    if (/class="/i.test(a)) {
      return m.replace(
        /class="([^"]*)"/i,
        'class="$1 stx-pass-app"',
      ).replace(">", ">" + inject);
    }
    return `<body class="stx-pass-app"${a}>${inject}`;
  });

  out = out.replace(/<html(\s[^>]*)?>/i, (m, attrs) => {
    const a = attrs || "";
    if (/class="/i.test(a)) {
      return m.replace(/class="([^"]*)"/i, 'class="$1 stx-pass-html"');
    }
    return `<html class="stx-pass-html"${a}>`;
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
