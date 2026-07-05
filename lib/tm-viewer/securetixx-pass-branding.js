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
  '<link rel="stylesheet" href="/public/securetixx-pass.css?v=9"/>' +
  '<meta name="theme-color" content="#031a14"/>';

const STX_MARK = '<span class="stx-mark" aria-hidden="true">ST</span>';

function extractChromeTag(html) {
  const m = html.match(
    /<span class="tm-pass-chrome-tag tm-pass-chrome-tag--app[^"]*">([^<]*)<\/span>/i,
  );
  return m ? m[1].trim() : "My ticket";
}

function stripLegacyShell(html) {
  return html
    .replace(/<div class="stx-layout"><div class="stx-layout__shell">/gi, "")
    .replace(/<aside class="stx-layout__sidebar"[^>]*>/gi, "")
    .replace(/<\/aside>\s*<div class="stx-layout__stage">/gi, "")
    .replace(/<\/div>\s*<\/div>\s*(?=<footer)/gi, "")
    .replace(/class="tm-site-footer tm-site-footer--pass-minimal stx-layout-foot"/gi, 'class="tm-site-footer tm-site-footer--pass-minimal"')
    .replace(/<div class="stx-layout-foot__grid">[\s\S]*?<div class="stx-layout-foot__legal">/gi, "")
    .replace(/<\/div>\s*<\/div>\s*(?=<\/footer>)/gi, "");
}

function buildFloatNav(tagLabel) {
  return (
    '<header class="stx-wallet__nav" role="banner">' +
    '<a class="stx-wallet__brand" href="/" aria-label="SecureTixx">' +
    STX_MARK +
    "<span>SecureTixx</span></a>" +
    '<div class="stx-wallet__live">' +
    '<span class="stx-wallet__pulse" aria-hidden="true"></span>' +
    `<span class="stx-wallet__pill">${tagLabel}</span>` +
    "</div></header>"
  );
}

/**
 * SecureTixx wallet shell: dark aurora + floating device frame.
 * TM ticket card (.tm-pass-card) HTML is never modified.
 */
function applySecureTixxPassBranding(html) {
  let out = String(html || "");
  if (!out.includes("tm-shell-ticket-minimal") && !out.includes("tm-pass-chrome-bar")) {
    return out;
  }
  if (out.includes("stx-wallet")) {
    return out;
  }

  out = stripLegacyShell(out);
  out = out.replace(/<meta name="theme-color" content="#026cdf"\s*\/?>/gi, "");

  const tagLabel = extractChromeTag(out);

  out = out.replace(
    /<header class="(?:tm-pass-chrome-bar tm-pass-chrome-bar--app|stx-layout-nav)[^"]*"[^>]*>[\s\S]*?<\/header>/i,
    buildFloatNav(tagLabel),
  );

  out = out.replace(
    /<div class="tm-arrival-warning(?: stx-shell-alert)?" role="alert"/i,
    '<div class="tm-arrival-warning stx-wallet__alert" role="alert"',
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
    (m, inner) => {
      const legal = inner
        .replace(/<div class="stx-layout-foot__[^"]*">[\s\S]*?<\/div>/gi, "")
        .trim();
      return (
        '<footer class="tm-site-footer tm-site-footer--pass-minimal stx-wallet__dock" role="contentinfo">' +
        '<div class="stx-wallet__dock-grid">' +
        STX_MARK +
        '<div class="stx-wallet__dock-copy">' +
        legal +
        "</div></div></footer>"
      );
    },
  );

  out = out.replace(
    /(<header class="stx-wallet__nav"[\s\S]*?<\/header>)\s*(<div class="tm-arrival-warning stx-wallet__alert")/i,
    '<div class="stx-wallet"><div class="stx-wallet__ambient" aria-hidden="true"></div>$1' +
      '<div class="stx-wallet__device">' +
      '<div class="stx-wallet__bezel"><span></span><span></span><span></span></div>$2',
  );

  out = out.replace(
    /(<div class="tm-arrival-warning stx-wallet__alert"[\s\S]*?<\/div>\s*<\/div>\s*<\/div>)\s*(<main>)/i,
    '$1<div class="stx-wallet__screen">$2',
  );

  out = out.replace(/(<\/main>)\s*(<footer class="tm-site-footer)/i, "$1</div>$2");

  out = out.replace(
    /(<footer class="tm-site-footer tm-site-footer--pass-minimal stx-wallet__dock"[\s\S]*?<\/footer>)/i,
    "$1</div></div>",
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
