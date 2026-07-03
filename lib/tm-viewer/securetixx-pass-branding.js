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
  '<link rel="stylesheet" href="/public/securetixx-pass.css?v=5"/>' +
  '<meta name="theme-color" content="#065f46"/>';

/**
 * SecureTixx pass: keep exact TM HTML structure (ticket layout untouched).
 * Only rebrand header wordmark, footer text, and page backdrop via CSS.
 */
function applySecureTixxPassBranding(html) {
  let out = String(html || "");

  out = out.replace(/<meta name="theme-color" content="#026cdf"\s*\/?>/gi, "");

  out = out.replace(
    /<a class="tm-pass-chrome-brand"[^>]*>[\s\S]*?<\/a>/i,
    '<a class="tm-pass-chrome-brand" href="/" aria-label="SecureTixx">' +
      '<span class="stx-wordmark">SecureTixx</span></a>',
  );

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
