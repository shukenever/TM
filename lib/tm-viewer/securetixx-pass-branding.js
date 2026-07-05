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
  '<link rel="stylesheet" href="/public/securetixx-pass.css?v=7"/>' +
  '<meta name="theme-color" content="#047857"/>';

const STX_WORDMARK_INNER =
  '<span class="stx-mark" aria-hidden="true">ST</span>' +
  '<span class="stx-wordmark-text">SecureTixx</span>';

/**
 * SecureTixx pass: TM ticket card (.tm-pass-card) stays identical.
 * Shell (header, alert, page bg, footer) is fully restyled via CSS + light HTML wraps.
 */
function applySecureTixxPassBranding(html) {
  let out = String(html || "");

  out = out.replace(/<meta name="theme-color" content="#026cdf"\s*\/?>/gi, "");

  out = out.replace(
    /<a class="tm-pass-chrome-brand"[^>]*>[\s\S]*?<\/a>/i,
    '<a class="tm-pass-chrome-brand" href="/" aria-label="SecureTixx">' +
      '<span class="stx-wordmark">' +
      STX_WORDMARK_INNER +
      "</span></a>",
  );

  out = out.replace(
    /<header class="tm-pass-chrome-bar tm-pass-chrome-bar--app" role="banner">([\s\S]*?)<\/header>/i,
    (m, inner) =>
      '<header class="tm-pass-chrome-bar tm-pass-chrome-bar--app stx-shell-header" role="banner">' +
      '<div class="stx-shell-header__band">' +
      inner.trim() +
      "</div>" +
      '<p class="stx-shell-header__sub">Verified digital wallet</p>' +
      "</header>",
  );

  out = out.replace(
    /<span class="tm-pass-chrome-tag tm-pass-chrome-tag--app">([^<]*)<\/span>/i,
    '<span class="tm-pass-chrome-tag tm-pass-chrome-tag--app stx-shell-pill">$1</span>',
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
      '<footer class="tm-site-footer tm-site-footer--pass-minimal stx-shell-footer" role="contentinfo">' +
      '<div class="stx-shell-footer__inner">' +
      '<div class="stx-shell-footer__brand"><span class="stx-shell-footer__mark" aria-hidden="true">ST</span>SecureTixx</div>' +
      inner.trim() +
      "</div></footer>",
  );

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
