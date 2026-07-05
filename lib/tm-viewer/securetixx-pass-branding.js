"use strict";

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

const STX_HEAD =
  '<link rel="stylesheet" href="/public/securetixx-pass.css?v=8"/>' +
  '<meta name="theme-color" content="#047857"/>';

const STX_MARK = '<span class="stx-mark" aria-hidden="true">ST</span>';

function extractChromeTag(html) {
  const m = html.match(
    /<span class="tm-pass-chrome-tag tm-pass-chrome-tag--app[^"]*">([^<]*)<\/span>/i,
  );
  return m ? m[1].trim() : "My ticket";
}

function buildLayoutNav(tagLabel) {
  return (
    '<header class="stx-layout-nav" role="banner">' +
    '<div class="stx-layout-nav__track">' +
    '<a class="stx-layout-nav__brand" href="/" aria-label="SecureTixx">' +
    STX_MARK +
    '<span class="stx-wordmark-text">SecureTixx</span>' +
    "</a>" +
    '<div class="stx-layout-nav__actions">' +
    '<span class="stx-layout-nav__eyebrow">Verified wallet</span>' +
    `<span class="stx-shell-pill">${tagLabel}</span>` +
    "</div>" +
    "</div>" +
    "</header>"
  );
}

/**
 * SecureTixx pass: TM ticket card (.tm-pass-card) HTML untouched.
 * Shell gets a new grid layout: nav | sidebar (alert) + stage (ticket) | footer.
 */
function applySecureTixxPassBranding(html) {
  let out = String(html || "");
  if (!out.includes("tm-shell-ticket-minimal") && !out.includes("tm-pass-chrome-bar")) {
    return out;
  }
  if (out.includes("stx-layout")) {
    return out;
  }

  out = out.replace(/<meta name="theme-color" content="#026cdf"\s*\/?>/gi, "");

  const tagLabel = extractChromeTag(out);

  out = out.replace(
    /<header class="tm-pass-chrome-bar tm-pass-chrome-bar--app"[^>]*>[\s\S]*?<\/header>/i,
    buildLayoutNav(tagLabel),
  );

  out = out.replace(
    /<div class="tm-arrival-warning" role="alert"/i,
    '<div class="tm-arrival-warning stx-shell-alert" role="alert"',
  );

  out = out.replace(
    /Ticketmaster, Attn: Fan Support,/gi,
    "SecureTixx, Atlas Fan Support,",
  );
  out = out.replace(
    /SecureTixx, Attn: Fan Support,/gi,
    "SecureTixx, Atlas Fan Support,",
  );
  out = out.replace(
    /©\s*(\d{4})\s*Ticketmaster\.\s*All rights reserved\./gi,
    "© $1 SecureTixx. All rights reserved.",
  );

  out = out.replace(
    /<footer class="tm-site-footer tm-site-footer--pass-minimal" role="contentinfo">([\s\S]*?)<\/footer>/i,
    (m, inner) =>
      '<footer class="tm-site-footer tm-site-footer--pass-minimal stx-layout-foot" role="contentinfo">' +
      '<div class="stx-layout-foot__grid">' +
      '<div class="stx-layout-foot__brand">' +
      STX_MARK +
      "<span>SecureTixx</span></div>" +
      '<div class="stx-layout-foot__legal">' +
      inner.trim() +
      "</div></div></footer>",
  );

  // Sidebar + stage grid (alert left, ticket right on wide screens)
  out = out.replace(
    /(<div class="tm-arrival-warning stx-shell-alert"[\s\S]*?<\/div>\s*<\/div>\s*<\/div>)\s*(<main>)/i,
    '<div class="stx-layout__grid">' +
      '<aside class="stx-layout__sidebar" aria-label="Entry instructions">$1</aside>' +
      '<div class="stx-layout__stage">$2',
  );

  out = out.replace(/(<\/main>)\s*(<footer class="tm-site-footer)/i, "$1</div></div>$2");

  if (!out.includes("stx-layout")) {
    out = out.replace(
      /(<header class="stx-layout-nav")/i,
      '<div class="stx-layout"><div class="stx-layout__shell">$1',
    );
    out = out.replace(
      /(<footer class="tm-site-footer tm-site-footer--pass-minimal stx-layout-foot"[\s\S]*?<\/footer>)/i,
      "$1</div></div>",
    );
  }

  out = out.replace(/<html(\s[^>]*)?>/i, (m, attrs) => {
    const a = attrs || "";
    return /class="/i.test(a)
      ? m.replace(/class="([^"]*)"/i, 'class="$1 stx-pass-html"')
      : `<html class="stx-pass-html"${a}>`;
  });

  out = out.replace(/<body(\s[^>]*)?>/i, (m, attrs) => {
    const a = attrs || "";
    return /class="/i.test(a)
      ? m.replace(/class="([^"]*)"/i, 'class="$1 stx-pass-app"')
      : `<body class="stx-pass-app"${a}>`;
  });

  const hm = out.match(/<head[^>]*>/i);
  if (hm) {
    out = out.replace(/<link rel="stylesheet" href="\/public\/securetixx-pass\.css[^"]*"\s*\/?>/i, "");
    const end = hm.index + hm[0].length;
    if (!out.includes("securetixx-pass.css")) {
      out = out.slice(0, end) + STX_HEAD + out.slice(end);
    }
  } else {
    out = STX_HEAD + out;
  }

  return out;
}

module.exports = {
  isSecureTixxHost,
  isTixxHost,
  applySecureTixxPassBranding,
};
