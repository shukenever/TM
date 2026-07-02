#!/usr/bin/env python3
"""Inject SecureTixx distinct home layout + theme on securetixx-vercel-site pages."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "ticketmaster" / "securetixx-vercel-site"

FONT_LINK = (
    '<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700'
    '&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet"/>'
)
THEME_LINK = '<link rel="stylesheet" href="/public/securetixx-theme.css"/>'

STX_HEADER = """<header class="stx-header" role="banner"><div class="stx-header-inner"><a class="stx-logo" href="/" aria-label="SecureTixx home"><img src="/public/securetixx-logo-header.svg" alt="SecureTixx" width="168" height="34"/></a><nav class="stx-nav" aria-label="Primary"><a href="/shop.html">Marketplace</a><a href="/my-tickets">Wallet</a></nav><div class="stx-header-actions"><button type="button" class="tixx-settings-btn-nav" data-tixx-settings title="Settings" aria-label="Settings"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button>"""

# Account block copied from index — guest + signed slots
ACCOUNT_TAIL = """<div id="tm-topbar-guest" class="tm-topbar-account-slot"><button type="button" class="tm-topbar-login-btn" id="tm-topbar-login">Sign in</button></div><div id="tm-topbar-signed" class="tm-topbar-account-slot" hidden><div class="tm-account-wrap"><button type="button" class="tm-topbar-account-trigger" id="tm-topbar-account-btn" aria-expanded="false" aria-haspopup="true"><svg class="tm-account-ico" width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="7" r="4" stroke="currentColor" stroke-width="2"/></svg><span id="tm-topbar-account-label" class="tm-topbar-account-label">Account</span></button><div id="tm-account-menu" class="tm-account-menu" hidden role="menu"><div class="tm-account-menu-header"><p class="tm-account-menu-email" id="tm-account-menu-email"></p></div><div class="tm-account-menu-body"><a href="/my-tickets" class="tm-account-menu-item" id="tm-menu-my-tickets" role="menuitem">My tickets</a><button type="button" class="tm-account-menu-item" data-tixx-settings role="menuitem">Settings</button><p class="tm-account-menu-hint">Account, orders, addresses &amp; preferences.</p></div><div class="tm-account-menu-sep" aria-hidden="true"></div><button type="button" class="tm-account-menu-item tm-account-menu-signout" id="tm-menu-sign-out" role="menuitem">Sign out</button></div></div></div></div></header>"""

MAIN_SHELL_START = """
  <main>
    <div class="stx-shell">
      <aside class="stx-sidebar" aria-label="Browse">
        <div class="stx-sidebar-card">
          <h2>Categories</h2>
          <ul class="stx-cat-list">
            <li><a href="/shop.html"><span class="stx-cat-ico stx-cat-ico--all">🎫</span>All listings</a></li>
            <li><a href="/shop.html?cat=concerts"><span class="stx-cat-ico stx-cat-ico--concerts">🎵</span>Concerts</a></li>
            <li><a href="/shop.html?cat=sports"><span class="stx-cat-ico stx-cat-ico--sports">🏟</span>Sports</a></li>
            <li><a href="/shop.html?cat=events"><span class="stx-cat-ico stx-cat-ico--shows">🎭</span>Theater &amp; shows</a></li>
          </ul>
        </div>
        <div class="stx-sidebar-card">
          <h2>Why SecureTixx</h2>
          <ul class="stx-trust-list">
            <li><svg viewBox="0 0 24 24" fill="none"><path d="M12 2l8 4v6c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6l8-4z" stroke="currentColor" stroke-width="2"/><path d="M9 12l2 2 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>Verified mobile passes</li>
            <li><svg viewBox="0 0 24 24" fill="none"><path d="M4 4h16v16H4z" stroke="currentColor" stroke-width="2"/><path d="m4 8 8 5 8-5" stroke="currentColor" stroke-width="2"/></svg>Instant secure delivery</li>
            <li><svg viewBox="0 0 24 24" fill="none"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>Below face value pricing</li>
          </ul>
        </div>
      </aside>
      <div class="stx-main-col">
        <section class="stx-hero" aria-label="Welcome">
          <div class="stx-hero-copy">
            <p class="stx-kicker">Protected marketplace</p>
            <h1>Tickets you can trust — delivered in seconds</h1>
            <p class="tm-retail-sub">Verified TM passes · Instant email delivery · Up to 50% off face value. Browse concerts, sports, and shows near you.</p>
            <a class="tm-retail-cta" href="#home-discover">Explore events</a>
          </div>
          <div class="stx-hero-art" aria-hidden="true">
            <svg class="stx-hero-shield" viewBox="0 0 64 64" fill="none"><path d="M32 4L54 14v16c0 14.5-10 26.5-22 30C20 46.5 10 34.5 10 30V14L32 4z" stroke="currentColor" stroke-width="3"/><path d="M24 32l6 6 12-14" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <img class="tm-retail-hero-img stx-hero-hidden-img" src="https://images.unsplash.com/photo-1470229722913-7c0e2dbbafd3?auto=format&amp;fit=crop&amp;w=200&amp;q=60" alt="" loading="eager"/>
          </div>
        </section>
        <div class="stx-search-wrap tm-search-strip-wrap">
          <div class="stx-search-card">
            <h2>Find your next event</h2>
            <form class="stx-search-grid" id="tm-home-search-form" action="/shop.html" method="get" role="search">
              <div class="stx-field"><label for="home-loc">Location</label><input id="home-loc" name="location" type="search" placeholder="City or zip" autocomplete="off"/></div>
              <div class="stx-field"><label for="home-date">When</label><select id="home-date" name="date" aria-label="Date filter"><option value="all">Any date</option><option value="week">Next 7 days</option><option value="month">Next 30 days</option><option value="future">Upcoming only</option></select></div>
              <div class="stx-field stx-field--wide"><label for="home-q">Artist, event, or venue</label><input id="home-q" name="q" type="search" placeholder="Search listings…" autocomplete="off"/></div>
              <button type="submit" class="stx-search-submit">Search marketplace</button>
            </form>
          </div>
        </div>
        <div class="home-content">
          <div id="home-discover" class="home-discover">
            <p id="home-load" class="home-load">Loading events…</p>
"""


def inject_theme_head(html: str) -> str:
    if "securetixx-theme.css" not in html:
        html = html.replace(
            "family=IBM+Plex+Mono",
            "family=IBM+Plex+Mono",
        )
        # Replace Sora font link with Outfit+Fraunces if present
        html = re.sub(
            r'<link href="https://fonts\.googleapis\.com/css2\?family=Sora[^"]+" rel="stylesheet"/>',
            FONT_LINK,
            html,
            count=1,
        )
        if FONT_LINK not in html:
            html = html.replace("</head>", f"  {FONT_LINK}\n  {THEME_LINK}\n</head>", 1)
        else:
            html = html.replace(FONT_LINK, FONT_LINK + "\n  " + THEME_LINK, 1)
    return html


def patch_index(html: str) -> str:
    html = inject_theme_head(html)
    html = html.replace(
        'class="tm-app-body tm-shell-retail-simple tm-page--home"',
        'class="tm-app-body stx-app tm-shell-retail-simple tm-page--home"',
    )
    if 'class="stx-header"' not in html:
        # Keep legacy header for JS but hidden via CSS; add stx header before main
        html = re.sub(
            r"(<header class=\"topbar topbar--tm topbar--simple\"[^>]*>.*?</header>\s*)",
            r"\1" + STX_HEADER + ACCOUNT_TAIL + "\n",
            html,
            count=1,
            flags=re.DOTALL,
        )
    if 'class="stx-shell"' not in html:
        html = re.sub(
            r"<main>\s*<div class=\"tm-home-wrap tm-home-retail\">.*?</div><div class=\"home-content\">",
            MAIN_SHELL_START.strip(),
            html,
            count=1,
            flags=re.DOTALL,
        )
        html = html.replace(
            '<div id="home-guest-strip" class="home-guest-strip">',
            '</div></div></div><div id="home-guest-strip" class="home-guest-strip stx-guest-bar">',
            1,
        )
    return html


def patch_shop(html: str) -> str:
    html = inject_theme_head(html)
    if 'class="stx-app stx-shop"' not in html:
        html = html.replace("<body>", '<body class="stx-app stx-shop">', 1)
    if 'class="stx-shop-bar"' not in html:
        bar = (
            '<header class="stx-shop-bar" role="banner"><div class="stx-shop-bar-inner">'
            '<a class="stx-logo" href="/"><img src="/public/securetixx-logo-header.svg" alt="SecureTixx" height="32"/></a>'
            '<nav class="stx-nav"><a href="/shop.html">Marketplace</a><a href="/">Home</a><a href="/my-tickets">Wallet</a></nav>'
            '</div></header>'
        )
        html = html.replace("<body class=\"stx-app stx-shop\">", "<body class=\"stx-app stx-shop\">\n" + bar, 1)
    return html


def patch_login(html: str) -> str:
    html = inject_theme_head(html)
    html = html.replace(
        'class="tm-app-body tm-shell-retail-simple tm-page--login"',
        'class="tm-app-body stx-app stx-login tm-shell-retail-simple tm-page--login"',
    )
    if 'class="stx-header"' not in html:
        bar = (
            '<header class="stx-header" role="banner"><div class="stx-header-inner">'
            '<a class="stx-logo" href="/"><img src="/public/securetixx-logo-header.svg" alt="SecureTixx" height="34"/></a>'
            '<nav class="stx-nav"><a href="/">Home</a><a href="/shop.html">Marketplace</a></nav>'
            '</div></header>'
        )
        html = html.replace("<body ", bar + "\n<body ", 1)
    return html


def patch_my_tickets(html: str) -> str:
    html = inject_theme_head(html)
    html = html.replace(
        'class="tm-app-body tm-shell-retail-simple tm-page--my-tickets"',
        'class="tm-app-body stx-app stx-wallet tm-shell-retail-simple tm-page--my-tickets"',
    )
    if 'class="stx-header"' not in html:
        bar = (
            '<header class="stx-header" role="banner"><div class="stx-header-inner">'
            '<a class="stx-logo" href="/"><img src="/public/securetixx-logo-header.svg" alt="SecureTixx" height="34"/></a>'
            '<nav class="stx-nav"><a href="/">Home</a><a href="/shop.html">Marketplace</a></nav>'
            '</div></header>'
        )
        html = html.replace("<body ", bar + "\n<body ", 1)
    return html


def main() -> None:
    patchers = {
        "index.html": patch_index,
        "shop.html": patch_shop,
        "login.html": patch_login,
        "my-tickets.html": patch_my_tickets,
    }
    for name, fn in patchers.items():
        fp = SITE / name
        if not fp.is_file():
            continue
        text = fp.read_text(encoding="utf-8")
        out = fn(text)
        if out != text:
            fp.write_text(out, encoding="utf-8", newline="\n")
            print("patched", name)
        else:
            print("unchanged", name)


if __name__ == "__main__":
    main()
