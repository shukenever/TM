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

const STX_PASS_HEADER =
  '<header class="stx-pass-chrome" role="banner">' +
  '<div class="stx-pass-chrome-inner">' +
  '<a class="stx-pass-chrome-brand" href="/" aria-label="SecureTixx home">' +
  '<span class="stx-pass-wordmark">SecureTixx</span>' +
  "</a>" +
  '<span class="stx-pass-chrome-tag">My tickets</span>' +
  "</div></header>";

const STX_PASS_FOOTER =
  '<footer class="stx-pass-footer" role="contentinfo">' +
  '<div class="stx-pass-footer-inner">' +
  '<p class="stx-pass-footer-line"><strong>SecureTixx</strong> — verified mobile pass delivery</p>' +
  '<p class="stx-pass-footer-line stx-pass-footer-muted">Ticket shown below is issued via Ticketmaster.</p>' +
  '<p class="stx-pass-footer-line stx-pass-footer-copy">&copy; SecureTixx. All rights reserved.</p>' +
  "</div></footer>";

const STX_PASS_HEAD =
  '<link rel="stylesheet" href="/public/securetixx-pass.css"/>' +
  '<meta name="theme-color" content="#047857"/>' +
  '<style id="stx-pass-chrome-vars">html.stx-pass-html,:root{--tm-page-gray:#eef6f1}</style>';

/**
 * Rewrite proxied pass HTML for securetixx.com: green chrome, SecureTixx branding.
 * Ticketmaster wordmark on the ticket card (.tm-pass-brand-strip) is left unchanged.
 */
function applySecureTixxPassBranding(html) {
  let out = String(html || "");

  out = out.replace(/<meta name="theme-color" content="#026cdf"\s*\/?>/gi, "");
  out = out.replace(
    /<header class="tm-pass-chrome-bar[^>]*>[\s\S]*?<\/header>/i,
    STX_PASS_HEADER,
  );
  out = out.replace(
    /<footer class="tm-site-footer tm-site-footer--pass-minimal[^>]*>[\s\S]*?<\/footer>/i,
    STX_PASS_FOOTER,
  );

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
    out = out.slice(0, end) + STX_PASS_HEAD + out.slice(end);
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
