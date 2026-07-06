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
  '<link rel="icon" href="/public/favicon.svg?v=stx2" type="image/svg+xml"/>' +
  '<link rel="icon" href="/public/favicon-32.png?v=stx2" type="image/png" sizes="32x32"/>' +
  '<link rel="shortcut icon" href="/public/favicon-32.png?v=stx2" type="image/png"/>' +
  '<link rel="apple-touch-icon" href="/public/apple-touch-icon.png?v=stx2"/>' +
  '<link rel="preconnect" href="https://fonts.googleapis.com"/>' +
  '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>' +
  '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet"/>' +
  '<link rel="stylesheet" href="/public/securetixx-pass.css?v=58"/>' +
  '<meta name="theme-color" content="#051605"/>';

const STX_WIDTH_LOCK =
  '<style id="stx-width-lock">' +
  ":root{--stx-max:min(calc(100vw - 12px),552px);--stx-card:min(calc(100vw - 16px),520px);--stx-body-x:12px;--stx-dock-x:14px;--stx-hero-h:clamp(240px,62vw,360px)}" +
  "html.stx-pass-html body.stx-pass-app .stx-pass-float{width:min(100%,var(--stx-max))!important;max-width:var(--stx-max)!important;margin-left:auto!important;margin-right:auto!important}" +
  "html.stx-pass-html.tm-html-ticket-viewport body.stx-pass-app.tm-shell-ticket-minimal main," +
  "html.stx-pass-html body.stx-pass-app main," +
  "html.stx-pass-html.tm-html-ticket-viewport body.stx-pass-app .tm-pass-viewport-fit," +
  "html.stx-pass-html.tm-html-ticket-viewport body.stx-pass-app .tm-pass-viewport-fit-inner," +
  "html.stx-pass-html.tm-html-ticket-viewport body.stx-pass-app .tm-ticket-carousel," +
  "html.stx-pass-html.tm-html-ticket-viewport body.stx-pass-app .tm-carousel-stage," +
  "html.stx-pass-html.tm-html-ticket-viewport body.stx-pass-app .tm-carousel-viewport," +
  "html.stx-pass-html.tm-html-ticket-viewport body.stx-pass-app .tm-pass-card," +
  "html.stx-pass-html.tm-html-ticket-viewport body.stx-pass-app .acct.acct--tickets-only," +
  "html.stx-pass-html.tm-html-ticket-viewport body.stx-pass-app .tickets-only-panel{width:100%!important;max-width:100%!important}" +
  "</style>";

const STX_BC_ANIM_LOCK =
  '<style id="stx-bc-anim-lock">' +
  "html.stx-pass-html body.stx-pass-app .tm-pass-bc:not(.tm-pass-bc--ready) canvas.safetix-canvas{" +
  "opacity:0!important;visibility:hidden!important}" +
  "html.stx-pass-html body.stx-pass-app .tm-pass-bc.tm-pass-bc--ready canvas.safetix-canvas{" +
  "opacity:1!important;visibility:visible!important;transition:none!important;" +
  "animation:stx-bc-reveal .44s cubic-bezier(.22,.61,.36,1) both!important}" +
  "html.stx-pass-html body.stx-pass-app .tm-pass-bc:not(.tm-pass-bc--ready)::before{" +
  "content:''!important;display:block!important;opacity:1!important}" +
  "html.stx-pass-html body.stx-pass-app .tm-pass-bc.tm-pass-bc--ready::before{display:none!important}" +
  "</style>";

const STX_BC_REFRESH_LOCK =
  '<style id="stx-bc-refresh-lock">' +
  "html.stx-pass-html body.stx-pass-app .tm-pass-refresh-btn.stx-bc-refresh-btn," +
  "html.stx-pass-html.tm-html-ticket-viewport body.stx-pass-app .tm-pass-refresh-btn.stx-bc-refresh-btn{" +
  "border:1px solid rgba(143,211,86,.58)!important;background:#fff!important;color:#3f6212!important;" +
  "box-shadow:0 1px 2px rgba(63,98,18,.14)!important}" +
  "html.stx-pass-html body.stx-pass-app .tm-pass-refresh-btn.stx-bc-refresh-btn:hover," +
  "html.stx-pass-html.tm-html-ticket-viewport body.stx-pass-app .tm-pass-refresh-btn.stx-bc-refresh-btn:hover{" +
  "color:#2d5016!important;border-color:rgba(143,211,86,.78)!important;background:rgba(143,211,86,.08)!important}" +
  "html.stx-pass-html body.stx-pass-app .tm-pass-refresh-btn.stx-bc-refresh-btn .tm-pass-refresh-btn__ico," +
  "html.stx-pass-html body.stx-pass-app .tm-pass-refresh-btn.stx-bc-refresh-btn .tm-pass-refresh-btn__label," +
  "html.stx-pass-html body.stx-pass-app .tm-pass-refresh-btn.stx-bc-refresh-btn .tm-pass-refresh-btn__sec," +
  "html.stx-pass-html.tm-html-ticket-viewport body.stx-pass-app .tm-pass-refresh-btn.stx-bc-refresh-btn .tm-pass-refresh-btn__ico," +
  "html.stx-pass-html.tm-html-ticket-viewport body.stx-pass-app .tm-pass-refresh-btn.stx-bc-refresh-btn .tm-pass-refresh-btn__sec{" +
  "color:#3f6212!important}" +
  "html.stx-pass-html body.stx-pass-app .tm-pass-refresh-btn.stx-bc-refresh-btn .tm-pass-refresh-btn__sec," +
  "html.stx-pass-html.tm-html-ticket-viewport body.stx-pass-app .tm-pass-refresh-btn.stx-bc-refresh-btn .tm-pass-refresh-btn__sec{" +
  "display:inline-flex!important;border:1px solid rgba(143,211,86,.68)!important;" +
  "background:rgba(143,211,86,.12)!important}" +
  "</style>";

const STX_LOGO =
  '<img class="stx-logo-img" src="/public/securetixx-mark.svg?v=stx2" alt="" width="28" height="28" decoding="async"/>';

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
  '<svg class="stx-transfer-ico tm-pass-transfer-ico" viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">' +
  '<path fill="#0a1406" d="M3.4 20.4 21 12 3.4 3.6l2.8 7.4L16 13l-9.8 1.2 2.8 7.4Z"/></svg>';

const STX_SVG_VERIFIED =
  '<svg class="tm-verified-check stx-verified-check" viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">' +
  '<circle cx="10" cy="10" r="10" fill="#8fd356"/>' +
  '<path d="M5.4 10.1 8.3 13.1 14.9 6.5" fill="none" stroke="#fff" stroke-width="2.2" ' +
  'stroke-linecap="round" stroke-linejoin="round"/></svg>';

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

function stripForeignPassIcons(html) {
  return String(html || "").replace(
    /<link\b[^>]*\brel=["'](?:shortcut\s+icon|icon|apple-touch-icon)["'][^>]*>/gi,
    "",
  );
}

function injectStxPassHead(html) {
  let out = stripForeignPassIcons(html);
  out = out.replace(/<meta name="theme-color" content="[^"]*"\s*\/?>/gi, "");
  out = out.replace(/<link rel="stylesheet" href="\/public\/securetixx-pass\.css[^"]*"\s*\/?>/gi, "");
  out = out.replace(
    /<link href="https:\/\/fonts\.googleapis\.com\/css2\?family=(?:Outfit|Inter)[^"]*"\s*\/?>/gi,
    "",
  );
  out = out.replace(/<title>([\s\S]*?)<\/title>/i, (m, title) => {
    const raw = String(title || "").trim();
    if (/^SecureTixx\b/i.test(raw)) return m;
    const label = raw.split("·").pop()?.trim() || raw;
    return `<title>SecureTixx · ${escHtml(label)}</title>`;
  });

  const hm = out.match(/<head[^>]*>/i);
  if (hm) {
    const end = hm.index + hm[0].length;
    out = out.slice(0, end) + STX_HEAD + out.slice(end);
  } else {
    out = STX_HEAD + out;
  }
  return out;
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

const STX_TICKET_INFO_BTN_INNER =
  '<span class="tm-pass-info-ico" aria-hidden="true">i</span>' +
  '<span class="tm-pass-info-label">Ticket info</span>';

const STX_TICKET_INFO_BTN_MARKUP =
  '<span class="tm-pass-info-ico"[^>]*>[\\s\\S]*?<\\/span>\\s*' +
  '<span class="tm-pass-info-label">[\\s\\S]*?<\\/span>';

function enhanceTicketInfoButton(html) {
  let out = String(html || "");
  out = out.replace(
    new RegExp(
      `<a\\s+class="[^"]*\\btm-pass-info\\b[^"]*"[^>]*href="([^"]*)"[^>]*>\\s*${STX_TICKET_INFO_BTN_MARKUP}\\s*<\\/a>`,
      "gi",
    ),
    (_m, href) =>
      `<button type="button" class="tm-pass-btn tm-pass-info tm-pass-info-open" data-order-url="${escHtml(href)}" aria-haspopup="dialog">${STX_TICKET_INFO_BTN_INNER}</button>`,
  );
  out = out.replace(
    new RegExp(
      `<span\\s+class="[^"]*\\btm-pass-info\\b[^"]*\\btm-pass-info--muted\\b[^"]*"[^>]*>\\s*${STX_TICKET_INFO_BTN_MARKUP}\\s*<\\/span>`,
      "gi",
    ),
    () =>
      `<button type="button" class="tm-pass-btn tm-pass-info tm-pass-info-open tm-pass-info--muted" aria-haspopup="dialog">${STX_TICKET_INFO_BTN_INNER}</button>`,
  );
  out = out.replace(
    new RegExp(
      `<button\\s+class="[^"]*\\btm-pass-info\\b[^"]*"[^>]*>\\s*${STX_TICKET_INFO_BTN_MARKUP}\\s*<\\/button>`,
      "gi",
    ),
    (m) => {
      if (m.includes("tm-pass-info-open")) return m;
      const muted = /\btm-pass-info--muted\b/.test(m) ? " tm-pass-info--muted" : "";
      const orderM = m.match(/data-order-url="([^"]*)"/i);
      const orderAttr = orderM ? ` data-order-url="${orderM[1]}"` : "";
      return `<button type="button" class="tm-pass-btn tm-pass-info tm-pass-info-open${muted}"${orderAttr} aria-haspopup="dialog">${STX_TICKET_INFO_BTN_INNER}</button>`;
    },
  );
  // Legacy bug: muted span regex used to stop at the first inner </span>.
  out = out.replace(
    /(<button[^>]*class="[^"]*\btm-pass-info\b[^"]*"[^>]*>[\s\S]*?<\/button>)\s*<span class="tm-pass-info-label">[\s\S]*?<\/span>\s*(?:<\/span>\s*)?/gi,
    "$1",
  );
  out = out.replace(
    /<span class="tm-pass-info-label">[\s\S]*?<\/span>\s*<\/span>\s*(?=<(?:button|a)\b[^>]*class="[^"]*\btm-pass-transfer\b)/gi,
    "",
  );
  return out;
}

const STX_TICKET_INFO_MODAL =
  '<div id="stx-ticket-info-modal" class="stx-ticket-info-modal" hidden aria-hidden="true">' +
  '<div class="stx-ticket-info-backdrop" id="stx-ticket-info-backdrop"></div>' +
  '<div class="stx-ticket-info-panel" role="dialog" aria-labelledby="stx-ticket-info-title" aria-modal="true">' +
  '<div class="stx-ticket-info-head">' +
  '<h3 id="stx-ticket-info-title">Ticket Info</h3>' +
  '<p class="stx-ticket-info-source">Source: Ticketmaster</p>' +
  "</div>" +
  '<dl class="stx-ticket-info-list" id="stx-ticket-info-list"></dl>' +
  '<div class="stx-ticket-info-foot">' +
  '<a id="stx-ticket-info-order" class="stx-ticket-info-order" href="#" target="_blank" rel="noopener noreferrer" hidden>View order on Ticketmaster</a>' +
  '<button type="button" id="stx-ticket-info-close">Close</button>' +
  "</div></div></div>";

const STX_TICKET_INFO_SCRIPT =
  "<script>(function(){var modal=document.getElementById('stx-ticket-info-modal');" +
  "var backdrop=document.getElementById('stx-ticket-info-backdrop');" +
  "var btnClose=document.getElementById('stx-ticket-info-close');" +
  "var listEl=document.getElementById('stx-ticket-info-list');" +
  "var orderLink=document.getElementById('stx-ticket-info-order');" +
  "function txt(root,sel){var n=root&&root.querySelector(sel);return n?String(n.textContent||'').trim():'';}" +
  "function metaCell(idx,part){var cell=document.querySelector('.stx-meta-grid__cell:nth-child('+idx+')');" +
  "if(!cell)return '';var n=cell.querySelector(part);return n?String(n.textContent||'').trim():'';}" +
  "function seatVal(card,lbl){var blocks=card?card.querySelectorAll('.tm-pass-seats > div'):[];" +
  "for(var i=0;i<blocks.length;i++){var l=blocks[i].querySelector('.tm-pass-lbl');" +
  "if(l&&String(l.textContent||'').trim().toUpperCase()===lbl){var b=blocks[i].querySelector('b');" +
  "return b?String(b.textContent||'').trim():'';}}return '';}" +
  "function clean(v){v=String(v||'').trim();return v&&v!=='—'&&v!=='-'&&v!=='–'?v:'';}" +
  "function activeCard(){var slides=document.querySelectorAll('.tm-carousel-slide');" +
  "var best=null,bestW=0;for(var i=0;i<slides.length;i++){var r=slides[i].getBoundingClientRect();" +
  "if(r.width<=0)continue;var vis=Math.max(0,Math.min(r.right,window.innerWidth)-Math.max(r.left,0));" +
  "if(vis>bestW){bestW=vis;best=slides[i];}}var root=best||document;" +
  "return root.querySelector('.tm-pass-card')||root.querySelector('.safetix-slot')||document.querySelector('.tm-pass-card');}" +
  "function ticketCount(){var subs=document.querySelectorAll('.tm-pass-sub-line');" +
  "for(var i=0;i<subs.length;i++){var t=String(subs[i].textContent||'').trim();" +
  "var m=t.match(/^(\\d+)\\s*x\\s*tickets?$/i);if(m)return m[1]+' ticket'+(m[1]==='1'?'':'s');}return '';}" +
  "function addRow(label,value){value=clean(value);if(!value)return;" +
  "var dt=document.createElement('dt');dt.textContent=label;" +
  "var dd=document.createElement('dd');dd.textContent=value;" +
  "listEl.appendChild(dt);listEl.appendChild(dd);}" +
  "function addDeliveryRow(){if(!listEl)return;" +
  "var dt=document.createElement('dt');dt.textContent='Delivery';" +
  "var dd=document.createElement('dd');dd.className='stx-ticket-info-delivery';" +
  "dd.innerHTML='<span class=\"stx-ticket-info-delivery-main\">SafeTix mobile ticket</span>'+" +
  "'<span class=\"stx-ticket-info-via\">VIA <img class=\"stx-ticket-info-tm-mark\" src=\"" +
  TM_WORDMARK +
  "\" alt=\"Ticketmaster\" width=\"92\" height=\"14\" loading=\"lazy\" decoding=\"async\"/></span>';" +
  "listEl.appendChild(dt);listEl.appendChild(dd);}" +
  "function populateInfo(orderUrl){if(!listEl)return;listEl.innerHTML='';" +
  "var card=activeCard()||document;var doc=document;" +
  "var eventName=txt(card,'.tm-pass-title')||txt(doc,'.tm-pass-title');" +
  "var venue=txt(doc,'.stx-event-venue');" +
  "var dateLine=metaCell(1,'.stx-meta-grid__main');" +
  "var timeLine=metaCell(1,'.stx-meta-grid__sub');" +
  "var locMain=metaCell(2,'.stx-meta-grid__main');" +
  "var locSub=metaCell(2,'.stx-meta-grid__sub');" +
  "var kind=txt(card,'.tm-pass-kind')||metaCell(3,'.stx-meta-grid__main');" +
  "var detail=txt(card,'.tm-pass-type-detail')||metaCell(3,'.stx-meta-grid__sub');" +
  "var section=seatVal(card,'SECTION');var row=seatVal(card,'ROW');var seat=seatVal(card,'SEAT');" +
  "var gate=txt(card,'.tm-pass-gate')||txt(doc,'.tm-pass-gate');" +
  "var entry=txt(doc,'.stx-entry-gate span:last-child')||txt(doc,'.stx-entry-gate');" +
  "var dateTime=[dateLine,timeLine].filter(Boolean).join(' · ');" +
  "if(!venue&&locMain){venue=locSub?locMain+', '+locSub:locMain;}" +
  "addRow('Event',eventName);addRow('Date & time',dateTime);" +
  "addRow('Venue',venue||locMain);addRow('Location',locSub&&locMain?locSub:'');" +
  "addRow('Tickets',ticketCount());addRow('Ticket type',kind);" +
  "addRow('Admission',detail);addRow('Section',section);addRow('Row',row);" +
  "addRow('Seat',seat);addRow('Gate',gate);addRow('Entry',entry);" +
  "addDeliveryRow();addRow('Status','Verified ticket');" +
  "if(orderLink){var ou=String(orderUrl||'').trim();" +
  "if(ou){orderLink.href=ou;orderLink.hidden=false;}else{orderLink.hidden=true;orderLink.removeAttribute('href');}}}" +
  "function closeInfo(){if(!modal)return;modal.hidden=true;modal.setAttribute('aria-hidden','true');}" +
  "function openInfo(orderUrl){if(!modal)return;populateInfo(orderUrl);modal.hidden=false;" +
  "modal.setAttribute('aria-hidden','false');if(btnClose)btnClose.focus();}" +
  "document.addEventListener('click',function(e){var t=e.target;" +
  "var btn=t&&t.closest&&t.closest('.tm-pass-info-open');" +
  "if(btn){e.preventDefault();openInfo(btn.getAttribute('data-order-url')||'');}});" +
  "if(backdrop)backdrop.addEventListener('click',closeInfo);" +
  "if(btnClose)btnClose.addEventListener('click',closeInfo);" +
  "document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!modal.hidden)closeInfo();});})();</script>";

function injectTicketInfoUi(html) {
  if (html.includes('id="stx-ticket-info-modal"')) return html;
  const bundle = STX_TICKET_INFO_MODAL + STX_TICKET_INFO_SCRIPT;
  if (html.includes('id="tm-pass-transfer-modal"')) {
    return html.replace(/(<div id="tm-pass-transfer-modal")/i, bundle + "$1");
  }
  return html.replace(/<\/body>/i, bundle + "</body>");
}

function enhanceVerifiedBadge(html) {
  return html.replace(/<svg class="tm-verified-check"[\s\S]*?<\/svg>/gi, STX_SVG_VERIFIED);
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

function parseGateLabel(html) {
  const m = html.match(/<div class="tm-pass-gate"[^>]*>([^<]*)<\/div>/i);
  return m && m[1] ? m[1].trim() : "Main Concourse";
}

function buildEntryGate(label) {
  const text = label || "Main Concourse";
  return (
    '<div class="stx-entry-gate" aria-hidden="true">' +
    '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">' +
    '<path fill="currentColor" d="M8 3h8v2H8V3Zm-1 4h10v14H7V7Zm2 2v10h6V9H9Zm1.5 2h3v1.5h-3V11Zm0 3h3v1.5h-3V14Z"/></svg>' +
    `<span>${escHtml(text)}</span></div>`
  );
}

function extractRefreshButton(inner) {
  const m = inner.match(/<button[^>]*class="[^"]*tm-pass-refresh-btn[^"]*"[\s\S]*?<\/button>/i);
  if (m) {
    let btn = m[0].replace(
      /class="tm-pass-refresh-btn"/i,
      'class="tm-pass-refresh-btn stx-bc-refresh-btn"',
    );
    if (!/tm-pass-refresh-btn__sec/i.test(btn)) {
      btn = btn.replace(
        /<\/button>/i,
        '<span class="tm-pass-refresh-btn__sec" aria-live="polite">—</span></button>',
      );
    }
    return btn;
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

const STX_HERO_VIBES =
  '<div class="stx-hero-vibes" aria-hidden="true">' +
  '<span class="stx-hero-vibe"></span>' +
  '<span class="stx-hero-vibe"></span>' +
  '<span class="stx-hero-vibe"></span>' +
  "</div>";

function injectHeroVibes(html) {
  return html.replace(
    /(<div class="[^"]*\btm-pass-hero--cover\b[^"]*"[^>]*>)/i,
    `$1${STX_HERO_VIBES}`,
  );
}

function injectPassDecorations(html) {
  const meta = parsePassMeta(html);
  let out = html;

  out = injectHeroVibes(out);

  out = out.replace(
    /<div class="tm-pass-head-center">([\s\S]*?)<\/div>/i,
    () =>
      '<div class="tm-pass-head-center">' +
      `<h4 class="tm-pass-title">${escHtml(meta.title)}</h4>` +
      `<p class="stx-event-venue">${escHtml(meta.venueLine)}</p>` +
      "</div>",
  );

  out = enhanceBarcodeRow(out);

  const gateLabel = parseGateLabel(out);
  out = out.replace(/<div class="tm-pass-seats">/i, buildMetaGrid(meta) + '<div class="stx-pass-bottom"><div class="tm-pass-seats">');
  out = out.replace(/<div class="tm-pass-gate"[^>]*>[\s\S]*?<\/div>\s*/gi, "");
  out = out.replace(/<div class="tm-pass-actions">/i, buildEntryGate(gateLabel) + '<div class="tm-pass-actions">');

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
  out = enhanceVerifiedBadge(out);
  out = enhanceTicketInfoButton(out);
  out = injectTicketInfoUi(out);

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

  out = injectStxPassHead(out);

  out = out.replace(/<style id="stx-width-lock">[\s\S]*?<\/style>/gi, "");
  out = out.replace(/<style id="stx-bc-refresh-lock">[\s\S]*?<\/style>/gi, "");
  out = out.replace(/<style id="stx-bc-anim-lock">[\s\S]*?<\/style>/gi, "");
  out = out.replace(/<\/head>/i, STX_WIDTH_LOCK + STX_BC_REFRESH_LOCK + STX_BC_ANIM_LOCK + "</head>");

  return out;
}

module.exports = {
  isSecureTixxHost,
  isTixxHost,
  applySecureTixxPassBranding,
};
