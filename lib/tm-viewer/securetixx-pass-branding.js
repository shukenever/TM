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
  '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet"/>' +
  '<link rel="stylesheet" href="/public/securetixx-pass.css?v=11"/>' +
  '<meta name="theme-color" content="#0a1f14"/>';

const STX_LOGO =
  '<svg class="stx-logo-ico" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">' +
  '<path fill="currentColor" d="M12 2 4 5v6c0 5 3.4 9.7 8 11 4.6-1.3 8-6 8-11V5l-8-3Zm-1 13-3-3 1.4-1.4L11 12.2l4.6-4.6L17 9l-6 6Z"/></svg>';

const STX_SHIELD =
  '<svg class="stx-shield-ico" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">' +
  '<path fill="none" stroke="currentColor" stroke-width="1.8" d="M12 3 5 6v5c0 4.2 2.8 8.1 7 9.4 4.2-1.3 7-5.2 7-9.4V6l-7-3Z"/>' +
  '<path fill="currentColor" d="M10.2 12.6 8.8 11.2l-1.4 1.4 2.8 2.8 5.4-5.4-1.4-1.4-4 4Z"/></svg>';

function escHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function extractChromeTag(html) {
  const m = html.match(
    /<span class="tm-pass-chrome-tag tm-pass-chrome-tag--app[^"]*">([^<]*)<\/span>/i,
  );
  return m ? m[1].trim() : "My ticket";
}

function extractBackHref(html) {
  const m = html.match(/<a class="tm-pass-menu" href="([^"]*)"/i);
  if (m && m[1]) return m[1];
  return "/";
}

function stripLegacyShell(html) {
  return html
    .replace(/<div class="stx-ticket-app"><div class="stx-ticket-app__bg"[^>]*><\/div>/gi, "")
    .replace(/<div class="stx-ticket-app__scroll">/gi, "")
    .replace(/<\/div>\s*<\/div>\s*(?=<\/body>)/gi, "")
    .replace(/<div class="stx-portal"><div class="stx-portal__ribbon"[^>]*><\/div>/gi, "")
    .replace(/<div class="stx-portal__canvas">/gi, "")
    .replace(/<div class="stx-portal__stage">/gi, "")
    .replace(/<\/div>\s*<\/div>\s*(?=<footer)/gi, "")
    .replace(/<div class="stx-wallet"><div class="stx-wallet__ambient"[^>]*><\/div>/gi, "")
    .replace(/<div class="stx-wallet__device">/gi, "")
    .replace(/<div class="stx-wallet__bezel">[\s\S]*?<\/div>/gi, "")
    .replace(/<div class="stx-wallet__screen">/gi, "")
    .replace(/class="tm-arrival-warning stx-(?:wallet__alert|portal__notice)[^"]*"/gi, 'class="tm-arrival-warning"')
    .replace(/class="[^"]*stx-portal__foot[^"]*"/gi, 'class="tm-site-footer tm-site-footer--pass-minimal"')
    .replace(/<div class="stx-portal__foot-inner">/gi, "")
    .replace(/<div class="stx-meta-grid">[\s\S]*?<\/div>\s*(?=<div class="tm-pass-seats">)/gi, "")
    .replace(/<div class="stx-entry-gate"[^>]*>[\s\S]*?<\/div>\s*(?=<div class="tm-pass-actions">)/gi, "");
}

function buildAppBar(backHref) {
  return (
    '<header class="stx-app-bar" role="banner">' +
    `<a class="stx-app-bar__back" href="${escHtml(backHref)}" aria-label="Back">` +
    '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">' +
    '<path fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" d="M15 6l-6 6 6 6"/></svg></a>' +
    '<a class="stx-app-bar__brand" href="/" aria-label="SecureTixx">' +
    STX_LOGO +
    "<span>SecureTixx</span></a>" +
    `<span class="stx-app-bar__shield">${STX_SHIELD}</span>` +
    "</header>"
  );
}

function buildSecurityFooter() {
  return (
    '<footer class="tm-site-footer tm-site-footer--pass-minimal stx-app-foot" role="contentinfo">' +
    '<div class="stx-app-foot__inner">' +
    STX_SHIELD +
    "<p>This is a secure ticket. Unauthorized duplication is prohibited.</p>" +
    "</div></footer>"
  );
}

function parsePassMeta(html) {
  const titleM = html.match(/<h4 class="tm-pass-title">([^<]*)<\/h4>/i);
  const title = titleM ? titleM[1].trim() : "Event";
  const subs = [];
  const subRe = /<span class="tm-pass-sub-line"[^>]*>([^<]*)<\/span>/gi;
  let sm;
  while ((sm = subRe.exec(html))) subs.push(sm[1].trim());
  const kindM = html.match(/<strong class="tm-pass-kind">([^<]*)<\/strong>/i);
  const detailM = html.match(/<span class="tm-pass-type-detail">([^<]*)<\/span>/i);
  const kind = kindM ? kindM[1].trim() : "Standard";
  const detail = detailM ? detailM[1].trim() : "Admission";

  let dateLine = "";
  let timeLine = "";
  let venueLine = "";
  for (const line of subs) {
    if (/^\d+x\s+tickets?$/i.test(line)) continue;
    if (/\d{4}|mon|tue|wed|thu|fri|sat|sun|\d{1,2}:\d{2}/i.test(line)) {
      const parts = line.split(/\s*[·•|]\s*/);
      dateLine = parts[0] || line;
      timeLine = parts[1] || "";
      continue;
    }
    if (!venueLine) venueLine = line;
  }
  if (!dateLine && subs.length) {
    dateLine = subs.find((s) => !/^\d+x\s+tickets?$/i.test(s)) || "";
  }
  if (!venueLine) venueLine = "Live event venue";

  return { title, dateLine, timeLine, venueLine, kind, detail };
}

function buildMetaGrid(meta) {
  const dateMain = escHtml(meta.dateLine || "Event date");
  const dateSub = escHtml(meta.timeLine || "Showtime");
  const locMain = escHtml(
    meta.venueLine.length > 28 ? meta.venueLine.slice(0, 28) + "…" : meta.venueLine,
  );
  const locSub = escHtml(meta.venueLine.length > 28 ? meta.venueLine : "Venue");
  const kind = escHtml(meta.kind.replace(/\s*Ticket\s*$/i, ""));
  const detail = escHtml(meta.detail);
  return (
    '<div class="stx-meta-grid">' +
    '<div class="stx-meta-grid__cell">' +
    '<span class="stx-meta-grid__ico" aria-hidden="true">📅</span>' +
    `<span class="stx-meta-grid__main">${dateMain}</span>` +
    `<span class="stx-meta-grid__sub">${dateSub}</span></div>` +
    '<div class="stx-meta-grid__cell">' +
    '<span class="stx-meta-grid__ico" aria-hidden="true">📍</span>' +
    `<span class="stx-meta-grid__main">${locMain}</span>` +
    `<span class="stx-meta-grid__sub">${locSub}</span></div>` +
    '<div class="stx-meta-grid__cell">' +
    '<span class="stx-meta-grid__ico" aria-hidden="true">🎫</span>' +
    `<span class="stx-meta-grid__main">${kind}</span>` +
    `<span class="stx-meta-grid__sub">${detail}</span></div>` +
    "</div>"
  );
}

function buildEntryGate() {
  return (
    '<div class="stx-entry-gate" aria-hidden="true">' +
    '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">' +
    '<path fill="currentColor" d="M8 3h8v2H8V3Zm-1 4h10v14H7V7Zm2 2v10h6V9H9Zm1.5 2h3v1.5h-3V11Zm0 3h3v1.5h-3V14Z"/></svg>' +
    "<span>Main Concourse</span></div>"
  );
}

function injectPassDecorations(html) {
  const meta = parsePassMeta(html);
  let out = html;
  out = out.replace(
    /<div class="tm-pass-head-center">([\s\S]*?)<\/div>/i,
    (m, inner) => {
      const titleM = inner.match(/<h4 class="tm-pass-title">([^<]*)<\/h4>/i);
      const title = titleM ? titleM[1] : meta.title;
      return (
        '<div class="tm-pass-head-center">' +
        `<h4 class="tm-pass-title">${title}</h4>` +
        `<p class="stx-event-venue">${meta.venueLine}</p>` +
        '<p class="tm-pass-sub stx-event-sub--hidden">' +
        inner.replace(/<h4 class="tm-pass-title">[\s\S]*?<\/h4>/i, "") +
        "</p></div>"
      );
    },
  );
  if (!out.includes("stx-meta-grid")) {
    out = out.replace(
      /<div class="tm-pass-seats">/i,
      buildMetaGrid(meta) + '<div class="tm-pass-seats">',
    );
  }
  if (!out.includes("stx-entry-gate")) {
    out = out.replace(/<div class="tm-pass-actions">/i, buildEntryGate() + '<div class="tm-pass-actions">');
  }
  return out;
}

/**
 * SecureTixx dark ticket app — 1:1 mockup shell.
 * Barcode canvas, wallet, and transfer controls stay functional.
 */
function applySecureTixxPassBranding(html) {
  let out = String(html || "");
  if (!out.includes("tm-shell-ticket-minimal") && !out.includes("tm-pass-chrome-bar")) {
    return out;
  }
  if (out.includes("stx-ticket-app")) {
    return out;
  }

  out = stripLegacyShell(out);
  out = out.replace(/<meta name="theme-color" content="#(?:026cdf|031a14|059669)"\s*\/?>/gi, "");

  const backHref = extractBackHref(out);

  out = out.replace(
    /<header class="(?:tm-pass-chrome-bar tm-pass-chrome-bar--app|stx-(?:layout-nav|wallet__nav|portal__top|app-bar))[^"]*"[^>]*>[\s\S]*?<\/header>/i,
    buildAppBar(backHref),
  );

  out = out.replace(
    /<div class="tm-arrival-warning(?:[^"]*)" role="alert"/i,
    '<div class="tm-arrival-warning stx-app-notice" role="alert"',
  );

  out = injectPassDecorations(out);

  out = out.replace(
    /<footer class="tm-site-footer tm-site-footer--pass-minimal[^"]*" role="contentinfo">[\s\S]*?<\/footer>/i,
    buildSecurityFooter(),
  );

  out = out.replace(/<body(\s[^>]*)?>/i, (m, attrs) => {
    const a = attrs || "";
    const open = /class="/i.test(a)
      ? m.replace(/class="([^"]*)"/i, 'class="$1 stx-pass-app"')
      : `<body class="stx-pass-app"${a}>`;
    return (
      open +
      '<div class="stx-ticket-app"><div class="stx-ticket-app__bg" aria-hidden="true"></div>'
    );
  });

  out = out.replace(
    /(<header class="stx-app-bar"[\s\S]*?<\/header>)/i,
    "$1<div class=\"stx-ticket-app__scroll\">",
  );

  out = out.replace(
    /(<footer class="tm-site-footer tm-site-footer--pass-minimal stx-app-foot"[\s\S]*?<\/footer>)/i,
    "$1</div></div>",
  );

  out = out.replace(/<html(\s[^>]*)?>/i, (m, attrs) => {
    const a = attrs || "";
    return /class="/i.test(a)
      ? m.replace(/class="([^"]*)"/i, 'class="$1 stx-pass-html"')
      : `<html class="stx-pass-html"${a}>`;
  });

  const hm = out.match(/<head[^>]*>/i);
  if (hm) {
    out = out.replace(/<link rel="stylesheet" href="\/public\/securetixx-pass\.css[^"]*"\s*\/?>/i, "");
    out = out.replace(
      /<link href="https:\/\/fonts\.googleapis\.com\/css2\?family=(?:Outfit|Inter)[^"]*"\s*\/?>/gi,
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
