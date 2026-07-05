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
  '<link rel="stylesheet" href="/public/securetixx-pass.css?v=26"/>' +
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

const STX_SVG_LOCK =
  '<svg class="stx-trust-ico" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">' +
  '<path fill="currentColor" d="M8 11V8a4 4 0 1 1 8 0v3h1a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1h1Zm2 0h4V8a2 2 0 1 0-4 0v3Z"/></svg>';

const STX_SVG_BOLT =
  '<svg class="stx-trust-ico" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">' +
  '<path fill="currentColor" d="M13 2 3 14h7l-1 8 10-12h-7l1-8Z"/></svg>';

const STX_SVG_PLANE =
  '<svg class="stx-transfer-ico" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">' +
  '<path fill="currentColor" d="m3 11 18-8-8 18-2-7-8-3Z"/></svg>';

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
    .replace(/<div class="stx-ticket-app"><div class="stx-ticket-app__bg"[^>]*>[\s\S]*?<\/div>\s*/gi, "")
    .replace(/<div class="stx-ticket-app__scroll"><div class="stx-pass-float">/gi, "")
    .replace(/<div class="stx-ticket-app__scroll">/gi, "")
    .replace(/<div class="stx-pass-float">/gi, "")
    .replace(/<\/div>\s*<\/div>\s*<\/div>\s*(?=<\/body>)/gi, "")
    .replace(/<\/div>\s*<\/div>\s*(?=<\/body>)/gi, "")
    .replace(/<p class="stx-event-venue">[\s\S]*?<\/p>/gi, "")
    .replace(/<p class="tm-pass-sub stx-event-sub--hidden">[\s\S]*?<\/p>/gi, "")
    .replace(/<div class="stx-meta-grid">[\s\S]*?<\/div>\s*(?=<div class="tm-pass-seats">)/gi, "")
    .replace(/<div class="stx-pass-bottom">/gi, "")
    .replace(/<div class="stx-entry-gate"[^>]*>[\s\S]*?<\/div>\s*(?=<div class="tm-pass-actions">)/gi, "")
    .replace(/\s*stx-app-notice/gi, "")
    .replace(/class="tm-site-footer tm-site-footer--pass-minimal stx-app-foot"/gi, 'class="tm-site-footer tm-site-footer--pass-minimal"');
}

function buildFloatingBg() {
  const specs = [
    [5, 8, 2.5, 0, 0.28],
    [12, 18, 1.5, 1.2, 0.22],
    [22, 6, 2, 2.4, 0.35],
    [34, 14, 1.2, 0.6, 0.18],
    [48, 22, 2.2, 3.1, 0.3],
    [58, 9, 1.6, 1.8, 0.24],
    [71, 16, 2.8, 4.2, 0.32],
    [82, 7, 1.4, 2.2, 0.2],
    [91, 24, 2, 0.4, 0.26],
    [8, 42, 1.8, 2.8, 0.22],
    [16, 58, 2.4, 1.5, 0.3],
    [28, 72, 1.3, 3.6, 0.18],
    [41, 48, 2.6, 0.9, 0.34],
    [55, 64, 1.5, 4.8, 0.21],
    [67, 52, 2.1, 2.6, 0.27],
    [78, 78, 1.7, 1.1, 0.23],
    [88, 62, 2.3, 3.4, 0.29],
    [6, 86, 1.9, 5.2, 0.2],
    [24, 92, 2.5, 2.1, 0.31],
    [52, 88, 1.4, 4.5, 0.19],
    [93, 38, 2.7, 1.7, 0.33],
    [38, 32, 1.6, 3.9, 0.24],
    [63, 34, 2, 0.2, 0.28],
    [76, 44, 1.2, 2.9, 0.17],
  ];
  let stars = "";
  for (let i = 0; i < specs.length; i++) {
    const [x, y, size, delay, op] = specs[i];
    const kind = (i % 3) + 1;
    stars +=
      `<span class="stx-star stx-star--${kind}" style="left:${x}%;top:${y}%;--sz:${size}px;--delay:${delay}s;--op:${op}"></span>`;
  }
  return (
    '<div class="stx-ticket-app__bg" aria-hidden="true">' +
    `<div class="stx-stars">${stars}</div>` +
    "</div>"
  );
}

function buildAppBar(backHref) {
  return (
    '<header class="stx-app-bar" role="banner">' +
    '<div class="stx-app-bar__inner">' +
    `<a class="stx-app-bar__back" href="${escHtml(backHref)}" aria-label="Back">` +
    '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">' +
    '<path fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" d="M15 6l-6 6 6 6"/></svg></a>' +
    '<a class="stx-app-bar__brand" href="/" aria-label="SecureTixx">' +
    STX_LOGO +
    '<span class="stx-app-bar__brand-text"><span class="stx-app-bar__name">SecureTixx</span>' +
    '<span class="stx-app-bar__tag">Verified digital tickets</span></span></a>' +
    `<span class="stx-app-bar__shield">${STX_SHIELD}</span>` +
    "</div></header>"
  );
}

function buildSecurityFooter() {
  return (
    '<footer class="tm-site-footer tm-site-footer--pass-minimal stx-app-foot" role="contentinfo">' +
    '<div class="stx-trust-badges">' +
    '<span class="stx-trust-badge">' +
    STX_SVG_LOCK +
    "Encrypted</span>" +
    '<span class="stx-trust-badge">' +
    STX_SHIELD +
    "SafeTixx™</span>" +
    '<span class="stx-trust-badge">' +
    STX_SVG_BOLT +
    "Live Barcode</span>" +
    "</div></footer>"
  );
}

function enhanceActionButtons(html) {
  return html.replace(
    /<span class="tm-pass-transfer-stack">([\s\S]*?)<\/span>/gi,
    () => `<span class="tm-pass-transfer-stack">${STX_SVG_PLANE}<span class="tm-pass-transfer-label">Transfer</span></span>`,
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

function normalizeVenueLine(s) {
  let v = String(s || "").trim();
  if (!v) return v;
  v = v.replace(/,\s*(?:…|\.\.\.|\.{2,})\s*$/u, "");
  v = v.replace(/\s*(?:…|\.\.\.|\.{2,})\s*$/u, "");
  v = v.replace(/,\s*$/u, "");
  return v.trim();
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
    const cleaned = normalizeVenueLine(line);
    if (!venueLine && cleaned.length > 4 && !/^\d+x\s+tickets?$/i.test(cleaned)) {
      venueLine = cleaned;
    }
  }

  venueLine = normalizeVenueLine(venueLine);
  if (!venueLine) venueLine = "Event venue";

  let locMain = venueLine;
  let locSub = "Venue";
  const parts = venueLine
    .split(",")
    .map((p) => p.trim())
    .filter((p) => p && !/^(?:…|\.\.\.|\.{2,})$/u.test(p));
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

function extractRefreshButton(inner) {
  const m = inner.match(/<button[^>]*class="[^"]*tm-pass-refresh-btn[^"]*"[\s\S]*?<\/button>/i);
  if (m) {
    return m[0].replace(
      /class="tm-pass-refresh-btn"/i,
      'class="tm-pass-refresh-btn stx-bc-refresh-btn"',
    );
  }
  return (
    '<button type="button" class="tm-pass-refresh-btn stx-bc-refresh-btn" aria-label="Refresh barcode">' +
    '<span class="tm-pass-refresh-btn__ico" aria-hidden="true">↻</span>' +
    '<span class="tm-pass-refresh-btn__label">Refresh barcode</span>' +
    '<span class="tm-pass-refresh-btn__sec" aria-live="polite">—</span>' +
    "</button>"
  );
}

function enhanceBarcodeRow(html) {
  return html.replace(/<div class="tm-pass-screen-row">([\s\S]*?)<\/div>/i, (m, inner) =>
    '<div class="tm-pass-screen-row stx-bc-row">' +
    '<span class="stx-bc-warn">Screenshots won&apos;t get you in</span>' +
    `<img class="stx-bc-tm" src="${TM_WORDMARK}" alt="Ticketmaster" width="88" height="14" loading="lazy" decoding="async"/>` +
    extractRefreshButton(inner) +
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
  out = enhanceActionButtons(out);

  out = out.replace(
    /<footer class="tm-site-footer tm-site-footer--pass-minimal[^"]*" role="contentinfo">[\s\S]*?<\/footer>/i,
    buildSecurityFooter(),
  );

  out = out.replace(/<body(\s[^>]*)?>/i, (m, attrs) => {
    const a = attrs || "";
    const open = /class="/i.test(a)
      ? m.replace(/class="([^"]*)"/i, 'class="$1 stx-pass-app"')
      : `<body class="stx-pass-app"${a}>`;
    return open + '<div class="stx-ticket-app">' + buildFloatingBg();
  });

  out = out.replace(
    /(<header class="stx-app-bar"[\s\S]*?<\/header>)/i,
    '$1<div class="stx-ticket-app__scroll"><div class="stx-pass-float">',
  );

  out = out.replace(
    /(<footer class="tm-site-footer tm-site-footer--pass-minimal stx-app-foot"[\s\S]*?<\/footer>)/i,
    "$1</div></div></div>",
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
