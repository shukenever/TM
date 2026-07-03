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

const STX_WORDMARK =
  '<span class="tm-stx-wordmark tm-wordmark-img--chrome-app">SecureTixx</span>';

const STX_PASS_HEAD =
  '<link rel="stylesheet" href="/public/securetixx-pass.css"/>' +
  '<meta name="theme-color" content="#047857"/>';

/**
 * SecureTixx pass rebrand: same TM layout/DOM, green chrome + SecureTixx wordmark.
 * Ticket card (.tm-pass-card) keeps Ticketmaster branding unchanged.
 */
function applySecureTixxPassBranding(html) {
  let out = String(html || "");

  out = out.replace(/<meta name="theme-color" content="#026cdf"\s*\/?>/gi, "");

  // Header — keep tm-pass-chrome-bar structure; swap logo only.
  out = out.replace(
    /<a class="tm-pass-chrome-brand"[^>]*>[\s\S]*?<\/a>/i,
    `<a class="tm-pass-chrome-brand" href="/" aria-label="SecureTixx">${STX_WORDMARK}</a>`,
  );

  // Footer — same lines/format as TM, rebrand text only.
  out = out.replace(
    /Ticketmaster, Attn: Fan Support,/gi,
    "SecureTixx, Attn: Fan Support,",
  );
  out = out.replace(
    /©\s*(\d{4})\s*Ticketmaster\.\s*All rights reserved\./gi,
    "© $1 SecureTixx. All rights reserved.",
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
