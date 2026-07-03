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

const STX_CRITICAL =
  "<style id=\"stx-pass-critical\">" +
  "html.stx-pass-html,html.stx-pass-html body.stx-pass-app{" +
  "background:linear-gradient(165deg,#022c22 0%,#065f46 50%,#047857 100%)!important;" +
  "min-height:100vh;min-height:100dvh}" +
  "html.stx-pass-html.tm-html-ticket-viewport body.stx-pass-app.tm-shell-ticket-minimal{" +
  "height:auto!important;max-height:none!important;overflow-y:auto!important;" +
  "align-items:center!important;background:linear-gradient(165deg,#022c22 0%,#065f46 50%,#047857 100%)!important}" +
  "body.stx-pass-app.tm-shell-ticket-minimal{background:transparent!important}" +
  "body.stx-pass-app.tm-shell-ticket-minimal>main{" +
  "max-width:468px!important;width:100%!important;margin:0 auto!important;flex:0 0 auto!important}" +
  ".tm-arrival-warning,.tm-arrival-warning--sg,.tm-pass-chrome-bar,.tm-site-footer--pass-minimal{display:none!important}" +
  "</style>";

const STX_HEAD =
  STX_CRITICAL +
  '<link rel="stylesheet" href="/public/securetixx-pass.css?v=4"/>' +
  '<meta name="theme-color" content="#065f46"/>';

const STX_BG =
  '<div class="stx-pass-bg" aria-hidden="true"><div class="stx-pass-bg-glow"></div></div>';

const STX_HEADER =
  '<header class="stx-pass-top" role="banner">' +
  '<div class="stx-pass-top-inner">' +
  '<a class="stx-pass-logo" href="/">SecureTixx</a>' +
  '<a class="stx-pass-link" href="/my-tickets">My tickets</a>' +
  "</div></header>";

const STX_FOOTER =
  '<footer class="stx-pass-bottom" role="contentinfo">' +
  "<p>SecureTixx verified delivery</p></footer>";

const DEFAULT_WARN =
  "This ticket self-invalidates 15 min before showtime. Keep this page open at full brightness. No screenshots.";

function extractWarnBody(html) {
  const m = html.match(/<div class="tm-arrival-warning__body"[^>]*>([\s\S]*?)<\/div>/i);
  if (!m) return null;
  return m[1].trim().replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

function buildWarn(text) {
  const t = text || DEFAULT_WARN;
  return (
    '<div class="stx-pass-warn" role="alert">' +
    "<strong>Time-critical</strong><span>" +
    t +
    "</span></div>"
  );
}

function stripTmWarnings(html) {
  return html
    .replace(/<div class="tm-arrival-warning[^"]*"[^>]*>[\s\S]*?<\/div>\s*<\/div>/gi, "")
    .replace(/<style>[^<]*\.tm-arrival-warning[^<]*<\/style>\s*/gi, "");
}

function applySecureTixxPassBranding(html) {
  let out = String(html || "");

  out = out.replace(/<meta name="theme-color" content="#026cdf"\s*\/?>/gi, "");

  const warnText = extractWarnBody(out);
  out = stripTmWarnings(out);

  out = out.replace(/<header class="tm-pass-chrome-bar[^>]*>[\s\S]*?<\/header>/i, STX_HEADER);

  out = out.replace(
    /<footer class="tm-site-footer tm-site-footer--pass-minimal[^>]*>[\s\S]*?<\/footer>/i,
    STX_FOOTER,
  );

  if (!out.includes('class="stx-pass-warn"')) {
    out = out.replace(/<main\b/i, buildWarn(warnText) + "<main");
  }

  out = out.replace(/<html(\s[^>]*)?>/i, (m, attrs) => {
    const a = attrs || "";
    return /class="/i.test(a)
      ? m.replace(/class="([^"]*)"/i, 'class="$1 stx-pass-html"')
      : `<html class="stx-pass-html"${a}>`;
  });

  out = out.replace(/<body(\s[^>]*)?>/i, (m, attrs) => {
    const a = attrs || "";
    const tail = STX_BG;
    return /class="/i.test(a)
      ? m.replace(/class="([^"]*)"/i, 'class="$1 stx-pass-app"').replace(">", ">" + tail)
      : `<body class="stx-pass-app"${a}>${tail}`;
  });

  const hm = out.match(/<head[^>]*>/i);
  if (hm) {
    out = out.replace(/<style id="stx-pass-critical">[\s\S]*?<\/style>/i, "");
    out = out.replace(/<link rel="stylesheet" href="\/public\/securetixx-pass\.css[^"]*"\s*\/?>/i, "");
    const end = hm.index + hm[0].length;
    out = out.slice(0, end) + STX_HEAD + out.slice(end);
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
