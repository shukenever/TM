#!/usr/bin/env python3
"""Fix duplicate IDs/blocks after patch_securetixx_ui.py."""
from __future__ import annotations

import re
from pathlib import Path

fp = Path(__file__).resolve().parent.parent / "ticketmaster" / "securetixx-vercel-site" / "index.html"
t = fp.read_text(encoding="utf-8")

# Strip guest/signed from legacy topbar (stx-header keeps the live IDs)
t = re.sub(
    r'(<header class="topbar topbar--tm topbar--simple"[^>]*>.*?<nav class="tm-nav-links tm-home-nav"[^>]*>.*?</nav>)'
    r'<div id="tm-topbar-guest"[^>]*>.*?</div>\s*'
    r'<div id="tm-topbar-signed"[^>]*>.*?</div>\s*</div>\s*</div>\s*</header>',
    r"\1</div></header>",
    t,
    count=1,
    flags=re.DOTALL,
)

# Remove duplicate trust + category grid + nested home-discover opener
t = re.sub(
    r'(<p id="home-load" class="home-load">Loading events…</p>)'
    r'<div class="home-trust"[\s\S]*?</section>\s*'
    r'<div id="home-discover" class="home-discover">\s*'
    r'<p id="home-load" class="home-load">Loading events…</p>',
    r"\1",
    t,
    count=1,
)

fp.write_text(t, encoding="utf-8", newline="\n")
print("fixed index.html")
