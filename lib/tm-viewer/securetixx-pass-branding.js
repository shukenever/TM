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

/** Inlined so layout/bg work even if external CSS is slow or cached stale. */
const STX_CRITICAL_STYLE =
  "<style id=\"stx-pass-critical\">" +
  "html.stx-pass-html,html.stx-pass-html body.stx-pass-app.stx-pass-app{" +
  "background:linear-gradient(165deg,#011a14 0%,#064e3b 42%,#047857 100%)!important;" +
  "min-height:100vh;min-height:100dvh;margin:0;color:#ecfdf5}" +
  "html.stx-pass-html.tm-html-ticket-viewport body.stx-pass-app.tm-shell-ticket-minimal{" +
  "display:flex!important;flex-direction:column!important;align-items:center!important;" +
  "justify-content:flex-start!important;height:auto!important;max-height:none!important;" +
  "overflow-x:hidden!important;overflow-y:auto!important;background:linear-gradient(165deg,#011a14 0%,#064e3b 42%,#047857 100%)!important}" +
  ".tm-arrival-warning,.tm-arrival-warning--sg,.tm-pass-chrome-bar,.tm-site-footer--pass-minimal{display:none!important}" +
  ".stx-pass-shell{width:100%;max-width:430px;margin:0 auto;flex:1 0 auto;padding:0 14px 20px;box-sizing:border-box}" +
  ".stx-pass-alert{display:flex;gap:10px;align-items:flex-start;padding:12px 14px;margin:12px 0 10px;border-radius:12px;" +
  "background:rgba(0,0,0,.22);border:1px solid rgba(255,255,255,.14)}" +
  ".stx-pass-alert-badge{flex-shrink:0;width:22px;height:22px;border-radius:50%;background:#fbbf24;color:#78350f;" +
  "font-size:12px;font-weight:800;display:flex;align-items:center;justify-content:center}" +
  ".stx-pass-alert-title{margin:0 0 4px;font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#fde68a}" +
  ".stx-pass-alert-body{margin:0;font-size:12px;line-height:1.45;color:rgba(255,255,255,.92)}" +
  "body.stx-pass-app main.stx-pass-main{max-width:100%!important;width:100%!important;margin:0!important;padding:0!important;background:transparent!important}" +
  "</style>";

const STX_PASS_HEAD =
  STX_CRITICAL_STYLE +
  '<link rel="preconnect" href="https://fonts.googleapis.com"/>' +
  '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>' +
  '<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap" rel="stylesheet"/>' +
  '<link rel="stylesheet" href="/public/securetixx-pass.css?v=3"/>' +
  '<meta name="theme-color" content="#064e3b"/>';

const STX_PASS_BG =
  '<div class="stx-pass-bg" aria-hidden="true">' +
  '<div class="stx-pass-bg-glow stx-pass-bg-glow--a"></div>' +
  '<div class="stx-pass-bg-glow stx-pass-bg-glow--b"></div>' +
  '<div class="stx-pass-bg-mesh"></div>' +
  "</div>";

const STX_SHELL_OPEN =
  '<div class="stx-pass-shell">';

const STX_SHELL_CLOSE = "</div>";

const STX_PASS_HEADER =
  '<header class="stx-pass-header" role="banner">' +
  '<div class="stx-pass-header-inner">' +
  '<a class="stx-pass-mark" href="/" aria-label="SecureTixx home">SecureTixx</a>' +
  '<a class="stx-pass-wallet-link" href="/my-tickets">My tickets</a>' +
  "</div></header>";

const STX_PASS_FOOTER =
  '<footer class="stx-pass-footer" role="contentinfo">' +
  '<p>SecureTixx verified delivery</p>' +
  "</footer>";

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

function stripTmArrivalWarnings(html) {
  let out = html;
  out = out.replace(
    /<div class="tm-arrival-warning[^"]*"[^>]*>[\s\S]*?<\/div>\s*<\/div>/gi,
    "",
  );
  out = out.replace(
    /<style>[^<]*\.tm-arrival-warning[^<]*<\/style>\s*/gi,
    "",
  );
  return out;
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
    /<img([^>]*?)src="https:\/\/upload\.wikimedia\.org\/wikipedia\/commons\/7\/7d\/TicketMaster_wordmark\.svg"([^>]*?)>/gi,
    '<span class="stx-hero-watermark" aria-hidden="true">SecureTixx</span>',
  );
  return out;
}

function applySecureTixxPassBranding(html) {
  let out = String(html || "");

  out = out.replace(/<meta name="theme-color" content="#026cdf"\s*\/?>/gi, "");

  const alertBody = extractArrivalWarningBody(out);
  out = stripTmArrivalWarnings(out);

  out = out.replace(
    /<header class="tm-pass-chrome-bar[^>]*>[\s\S]*?<\/header>/i,
    STX_PASS_HEADER,
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

  if (!out.includes('class="stx-pass-shell"')) {
    out = out.replace(
      STX_PASS_HEADER,
      STX_PASS_HEADER + STX_SHELL_OPEN + buildStxAlert(alertBody),
    );
    out = out.replace(
      /(<\/main>)\s*(<footer class="stx-pass-footer")/i,
      "$1" + STX_SHELL_CLOSE + "$2",
    );
  }

  out = greenifyTicketCard(out);

  out = out.replace(/<body(\s[^>]*)?>/i, (m, attrs) => {
    const a = attrs || "";
    if (/class="/i.test(a)) {
      return m
        .replace(/class="([^"]*)"/i, 'class="$1 stx-pass-app"')
        .replace(">", ">" + STX_PASS_BG);
    }
    return `<body class="stx-pass-app"${a}>${STX_PASS_BG}`;
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
    out = out.replace(/<style id="stx-pass-critical">[\s\S]*?<\/style>/i, "");
    out = out.replace(
      /<link rel="stylesheet" href="\/public\/securetixx-pass\.css[^"]*"\s*\/?>/i,
      "",
    );
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
