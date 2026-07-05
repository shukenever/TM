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

const TM_WORDMARK =
  "https://upload.wikimedia.org/wikipedia/commons/7/7d/TicketMaster_wordmark.svg";

const STX_HEAD =
  '<link rel="preconnect" href="https://fonts.googleapis.com"/>' +
  '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>' +
  '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet"/>' +
  '<link rel="stylesheet" href="/public/securetixx-pass.css?v=17"/>' +
  '<meta name="theme-color" content="#051605"/>';

const STX_LOGO =
  '<svg class="stx-logo-ico" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">' +
  '<path fill="currentColor" d="M12 2 4 5v6c0 5 3.4 9.7 8 11 4.6-1.3 8-6 8-11V5l-8-3Zm-1 13-3-3 1.4-1.4L11 12.2l4.6-4.6L17 9l-6 6Z"/></svg>';

const STX_SHIELD =
  '<svg class="stx-shield-ico" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">' +
  '<path fill="none" stroke="currentColor" stroke-width="1.8" d="M12 3 5 6v5c0 4.2 2.8 8.1 7 9.4 4.2-1.3 7-5.2 7-9.4V6l-7-3Z"/>' +
  '<path fill="currentColor" d="M10.2 12.6 8.8 11.2l-1.4 1.4 2.8 2.8 5.4-5.4-1.4-1.4-4 4Z"/></svg>';

const STX_SVG_CAL =
  '<svg class="stx-meta-svg" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">' +
  '<rect x="3" y="5" width="18" height="16" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/>' +
  '<path d="M3 10h18M8 3v4M16 3v4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';

const STX_SVG_PIN =
  '<svg class="stx-meta-svg" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">' +
  '<path d="M12 21s6-5.2 6-10a6 6 0 1 0-12 0c0 4.8 6 10 6 10Z" fill="none" stroke="currentColor" stroke-width="1.8"/>' +
  '<circle cx="12" cy="11" r="2.2" fill="currentColor"/></svg>';

const STX_SVG_TIX =
  '<svg class="stx-meta-svg" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">' +
  '<path d="M3 8h18v3H3V8Zm0 5h12v3H3v-3Z" fill="currentColor" opacity=".85"/></svg>';

function escHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function toTitleCase(s) {
  return String(s || "")
    .toLowerCase()
    .replace(/\b[a-z]/g, (c) => c.toUpperCase());
}

function extractBackHref(html) {
  const m = html.match(/<a class="tm-pass-menu" href="([^"]*)"/i);
  return m && m[1] ? m[1] : "/";
}

function stripLegacyShell(html) {
  return html
    .replace(/<style id="stx-pass-critical">[\s\S]*?<\/style>/gi, "")
    .replace(/<div class="stx-ticket-app"><div class="stx-ticket-app__bg"[^>]*><\/div>/gi, "")
    .replace(/<div class="stx-ticket-app__scroll">/gi, "")
    .replace(/<\/div>\s*<\/div>\s*(?=<\/body>)/gi, "")
    .replace(/<p class="stx-event-venue">[\s\S]*?<\/p>/gi, "")
    .replace(/<p class="tm-pass-sub stx-event-sub--hidden">[\s\S]*?<\/p>/gi, "")
    .replace(/<div class="stx-meta-grid">[\s\S]*?<\/div>\s*(?=<div class="tm-pass-seats">)/gi, "")
    .replace(/<div class="stx-pass-bottom">/gi, "")
    .replace(/<div class="stx-entry-gate"[^>]*>[\s\S]*?<\/div>\s*(?=<div class="tm-pass-actions">)/gi, "")
    .replace(/\s*stx-app-notice/gi, "")
    .replace(/class="tm-site-footer tm-site-footer--pass-minimal stx-app-foot"/gi, 'class="tm-site-footer tm-site-footer--pass-minimal"');
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

function parseEventStart(html) {
  const m = html.match(/<meta name="tm-event-start" content="([^"]+)"/i);
  if (!m) return { dateLine: "", timeLine: "" };
  const d = new Date(m[1]);
  if (Number.isNaN(d.getTime())) return { dateLine: "", timeLine: "" };
  return {
    dateLine: d.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
    }),
    timeLine: d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }),
  };
}

function parsePassMeta(html) {
  const titleM = html.match(/<h4 class="tm-pass-title">([^<]*)<\/h4>/i);
  const title = toTitleCase(titleM ? titleM[1].trim() : "Event");
  const subs = [];
  const subRe = /<span class="tm-pass-sub-line"[^>]*>([^<]*)<\/span>/gi;
  let sm;
  while ((sm = subRe.exec(html))) subs.push(sm[1].trim());

  const kindM = html.match(/<strong class="tm-pass-kind">([^<]*)<\/strong>/i);
  const detailM = html.match(/<span class="tm-pass-type-detail">([^<]*)<\/span>/i);
  const kind = kindM ? kindM[1].trim() : "Standard";
  const detail = detailM ? detailM[1].trim() : "Admission";

  const start = parseEventStart(html);
  let dateLine = start.dateLine;
  let timeLine = start.timeLine;
  let venueLine = "";

  for (const line of subs) {
    if (/^\d+x\s+tickets?$/i.test(line)) continue;
    if (!dateLine && /\d{4}|(?:mon|tue|wed|thu|fri|sat|sun)/i.test(line)) {
      const parts = line.split(/\s*[·•|]\s*/);
      dateLine = parts[0] || line;
      if (!timeLine && parts[1]) timeLine = parts[1].trim();
      continue;
    }
    if (!venueLine && line.length > 4 && !/^\d+x\s+tickets?$/i.test(line)) {
      venueLine = line;
    }
  }

  if (!venueLine) venueLine = "Event venue";

  let locMain = venueLine;
  let locSub = "Venue";
  const parts = venueLine.split(",").map((p) => p.trim()).filter(Boolean);
  if (parts.length >= 3) {
    locSub = parts.slice(0, -2).join(", ");
    locMain = parts.slice(-2).join(", ");
  } else if (parts.length === 2) {
    locSub = parts[0];
    locMain = parts[1];
  }

  return {
    title,
    dateLine: dateLine || "Event date",
    timeLine: timeLine || "Showtime",
    venueLine,
    locMain,
    locSub,
    kind,
    detail,
  };
}

function buildMetaGrid(meta) {
  return (
    '<div class="stx-meta-grid">' +
    '<div class="stx-meta-grid__cell">' +
    STX_SVG_CAL +
    `<span class="stx-meta-grid__main">${escHtml(meta.dateLine)}</span>` +
    `<span class="stx-meta-grid__sub">${escHtml(meta.timeLine)}</span></div>` +
    '<div class="stx-meta-grid__cell">' +
    STX_SVG_PIN +
    `<span class="stx-meta-grid__main">${escHtml(meta.locMain)}</span>` +
    `<span class="stx-meta-grid__sub">${escHtml(meta.locSub)}</span></div>` +
    '<div class="stx-meta-grid__cell">' +
    STX_SVG_TIX +
    `<span class="stx-meta-grid__main">${escHtml(meta.kind.replace(/\s*Ticket\s*$/i, ""))}</span>` +
    `<span class="stx-meta-grid__sub">${escHtml(meta.detail)}</span></div>` +
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

function enhanceBarcodeRow(html) {
  return html.replace(
    /<div class="tm-pass-screen-row">([\s\S]*?)<\/div>/i,
    (m, inner) =>
      '<div class="tm-pass-screen-row stx-bc-row">' +
      '<span class="stx-bc-warn">Screenshots won&apos;t get you in</span>' +
      `<img class="stx-bc-tm" src="${TM_WORDMARK}" alt="Ticketmaster" width="88" height="14" loading="lazy" decoding="async"/>` +
      '<span class="stx-bc-refresh"><span class="stx-bc-refresh-txt">Refresh barcode</span><span class="tm-pass-refresh" title="Rotating barcode">↻</span></span>' +
      "</div>",
  );
}

function injectPassDecorations(html) {
  const meta = parsePassMeta(html);
  let out = html;

  out = out.replace(
    /<div class="tm-pass-head-center">([\s\S]*?)<\/div>/i,
    () =>
      '<div class="tm-pass-head-center">' +
      `<h4 class="tm-pass-title">${escHtml(meta.title)}</h4>` +
      `<p class="stx-event-venue">${escHtml(meta.venueLine)}</p>` +
      "</div>",
  );

  out = enhanceBarcodeRow(out);

  out = out.replace(/<div class="tm-pass-seats">/i, buildMetaGrid(meta) + '<div class="stx-pass-bottom"><div class="tm-pass-seats">');
  out = out.replace(/<div class="tm-pass-actions">/i, buildEntryGate() + '<div class="tm-pass-actions">');

  out = out.replace(
    /(<div class="tm-pass-actions">[\s\S]*?<\/div>)(\s*<\/div>)/i,
    "$1</div>$2",
  );

  return out;
}

function applySecureTixxPassBranding(html) {
  let out = String(html || "");
  if (!out.includes("tm-shell-ticket-minimal") && !out.includes("tm-pass-chrome-bar")) {
    return out;
  }
  if (out.includes("stx-ticket-app")) {
    out = stripLegacyShell(out);
  }

  out = out.replace(/<meta name="theme-color" content="#(?:026cdf|031a14|059669|0a1f14)"\s*\/?>/gi, "");

  const backHref = extractBackHref(out);

  out = out.replace(
    /<header class="(?:tm-pass-chrome-bar tm-pass-chrome-bar--app|stx-(?:layout-nav|wallet__nav|portal__top|app-bar))[^"]*"[^>]*>[\s\S]*?<\/header>/i,
    buildAppBar(backHref),
  );

  out = out.replace(
    /<div class="tm-arrival-warning[\s\S]*?<\/div>\s*<\/div>\s*<\/div>\s*(?=\s*<main)/i,
    "",
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
    return open + '<div class="stx-ticket-app"><div class="stx-ticket-app__bg" aria-hidden="true"></div>';
  });

  out = out.replace(
    /(<header class="stx-app-bar"[\s\S]*?<\/header>)/i,
    '$1<div class="stx-ticket-app__scroll">',
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
    out = out.replace(/<link rel="stylesheet" href="\/public\/securetixx-pass\.css[^"]*"\s*\/?>/gi, "");
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
