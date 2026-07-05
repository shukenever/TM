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

  '<link rel="preconnect" href="https://fonts.googleapis.com"/>' +

  '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>' +

  '<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@500;600;700;800&display=swap" rel="stylesheet"/>' +

  '<link rel="stylesheet" href="/public/securetixx-pass.css?v=10"/>' +

  '<meta name="theme-color" content="#059669"/>';



const STX_MARK = '<span class="stx-mark" aria-hidden="true">ST</span>';



function extractChromeTag(html) {

  const m = html.match(

    /<span class="tm-pass-chrome-tag tm-pass-chrome-tag--app[^"]*">([^<]*)<\/span>/i,

  );

  return m ? m[1].trim() : "My ticket";

}



function stripLegacyShell(html) {

  return html

    .replace(/<div class="stx-wallet"><div class="stx-wallet__ambient"[^>]*><\/div>/gi, "")

    .replace(/<div class="stx-wallet__device">/gi, "")

    .replace(/<div class="stx-wallet__bezel">[\s\S]*?<\/div>/gi, "")

    .replace(/<div class="stx-wallet__screen">/gi, "")

    .replace(/<\/div>\s*<\/div>\s*(?=<footer)/gi, "")

    .replace(/<\/div>\s*<\/div>\s*(?=<\/body>)/gi, "")

    .replace(/class="tm-arrival-warning stx-wallet__alert"/gi, 'class="tm-arrival-warning"')

    .replace(/class="tm-site-footer tm-site-footer--pass-minimal stx-wallet__dock"/gi, 'class="tm-site-footer tm-site-footer--pass-minimal"')

    .replace(/<div class="stx-wallet__dock-grid">[\s\S]*?<div class="stx-wallet__dock-copy">/gi, "")

    .replace(/<div class="stx-layout"><div class="stx-layout__shell">/gi, "")

    .replace(/<aside class="stx-layout__sidebar"[^>]*>/gi, "")

    .replace(/<\/aside>\s*<div class="stx-layout__stage">/gi, "")

    .replace(/class="tm-site-footer tm-site-footer--pass-minimal stx-layout-foot"/gi, 'class="tm-site-footer tm-site-footer--pass-minimal"')

    .replace(/<div class="stx-layout-foot__grid">[\s\S]*?<div class="stx-layout-foot__legal">/gi, "")

    .replace(/class="stx-wallet__nav"/gi, 'class="stx-portal__top"')

    .replace(/class="stx-portal__top stx-wallet__nav"/gi, 'class="stx-portal__top"');

}



function buildPortalHeader(tagLabel) {

  return (

    '<header class="stx-portal__top" role="banner">' +

    '<div class="stx-portal__top-inner">' +

    '<a class="stx-portal__brand" href="/" aria-label="SecureTixx">' +

    STX_MARK +

    '<span class="stx-portal__brand-copy">' +

    '<span class="stx-portal__brand-text">SecureTixx</span>' +

    '<span class="stx-portal__brand-sub">Verified passes</span>' +

    '</span>' +

    "</a>" +

    '<span class="stx-portal__tag">' +

    tagLabel +

    "</span>" +

    "</div></header>"

  );

}



/**

 * SecureTixx portal shell — cream editorial layout aligned with homepage.

 * TM ticket card (.tm-pass-card) HTML is never modified.

 */

function applySecureTixxPassBranding(html) {

  let out = String(html || "");

  if (!out.includes("tm-shell-ticket-minimal") && !out.includes("tm-pass-chrome-bar")) {

    return out;

  }

  if (out.includes("stx-portal")) {

    return out;

  }



  out = stripLegacyShell(out);

  out = out.replace(/<meta name="theme-color" content="#026cdf"\s*\/?>/gi, "");

  out = out.replace(/<meta name="theme-color" content="#031a14"\s*\/?>/gi, "");



  const tagLabel = extractChromeTag(out);



  out = out.replace(

    /<header class="(?:tm-pass-chrome-bar tm-pass-chrome-bar--app|stx-layout-nav|stx-wallet__nav|stx-portal__top)[^"]*"[^>]*>[\s\S]*?<\/header>/i,

    buildPortalHeader(tagLabel),

  );



  out = out.replace(

    /<div class="tm-arrival-warning(?: stx-(?:wallet__alert|portal__notice|shell-alert))?([^"]*)" role="alert"/i,

    '<div class="tm-arrival-warning stx-portal__notice$1" role="alert"',

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

    /<footer class="tm-site-footer tm-site-footer--pass-minimal(?: stx-(?:wallet__dock|layout-foot|portal__foot))?" role="contentinfo">([\s\S]*?)<\/footer>/i,

    (m, inner) => {

      const legal = inner

        .replace(/<div class="stx-(?:wallet__dock|layout-foot)__[^"]*">[\s\S]*?<\/div>/gi, "")

        .trim();

      return (

        '<footer class="tm-site-footer tm-site-footer--pass-minimal stx-portal__foot" role="contentinfo">' +

        '<div class="stx-portal__foot-inner">' +

        legal +

        "</div></footer>"

      );

    },

  );



  out = out.replace(/<body(\s[^>]*)?>/i, (m, attrs) => {

    const a = attrs || "";

    const open = /class="/i.test(a)

      ? m.replace(/class="([^"]*)"/i, 'class="$1 stx-pass-app"')

      : `<body class="stx-pass-app"${a}>`;

    return open + '<div class="stx-portal"><div class="stx-portal__ribbon" aria-hidden="true"></div>';

  });



  out = out.replace(

    /(<header class="stx-portal__top"[\s\S]*?<\/header>)/i,

    '$1<div class="stx-portal__canvas">',

  );



  out = out.replace(/<main>/i, '<div class="stx-portal__stage"><main>');

  out = out.replace(/<\/main>/i, "</main></div>");



  out = out.replace(

    /(<footer class="tm-site-footer tm-site-footer--pass-minimal stx-portal__foot"[\s\S]*?<\/footer>)/i,

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

    if (/class="/i.test(a)) {

      return /stx-pass-app/.test(a)

        ? m

        : m.replace(/class="([^"]*)"/i, 'class="$1 stx-pass-app"');

    }

    return `<body class="stx-pass-app"${a}>`;

  });



  const hm = out.match(/<head[^>]*>/i);

  if (hm) {

    out = out.replace(/<link rel="stylesheet" href="\/public\/securetixx-pass\.css[^"]*"\s*\/?>/i, "");

    out = out.replace(

      /<link href="https:\/\/fonts\.googleapis\.com\/css2\?family=Outfit[^"]*"\s*\/?>/i,

      "",

    );

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

