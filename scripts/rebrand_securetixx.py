#!/usr/bin/env python3
"""One-shot SecureTixx frontend rebrand helper."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "ticketmaster" / "tm-vercel-site"

COLOR_REPL = [
    ("#0f766e", "#059669"),
    ("#14b8a6", "#34d399"),
    ("#0d4f4a", "#047857"),
    ("rgba(15, 118, 110, 0.14)", "rgba(5, 150, 105, 0.14)"),
    ("rgba(15,118,110,.1)", "rgba(5,150,105,.12)"),
    ("rgba(15,118,110,.45)", "rgba(5,150,105,.45)"),
    ("#2dd4bf", "#6ee7b7"),
    ("#026cdf", "#059669"),
    ("#0153a3", "#047857"),
    ("#1a7fe0", "#34d399"),
    ('content="#0f172a"', 'content="#047857"'),
]

TEXT_REPL = [
    ("Already bought on Tixx?", "Already bought on SecureTixx?"),
    ("https://www.instagram.com/tixxpw/", "https://securetixx.com"),
    ('aria-label="SecureTixx on Instagram (@tixxpw)"', 'aria-label="SecureTixx website"'),
    ("@tixxpw", "securetixx.com"),
    (' srcset="/public/tixx-logo-header-sm.png 1x, /public/tixx-logo-header.png 2x"', ""),
    ("https://tixx.pw", "https://securetixx.com"),
]


def patch_file(fp: Path) -> bool:
    t = fp.read_text(encoding="utf-8")
    orig = t
    for a, b in COLOR_REPL + TEXT_REPL:
        t = t.replace(a, b)
    if t != orig:
        fp.write_text(t, encoding="utf-8", newline="\n")
        return True
    return False


def main() -> None:
    changed: list[str] = []
    for fp in sorted(SITE.glob("*.html")):
        if patch_file(fp):
            changed.append(str(fp.relative_to(ROOT)))
    for rel in ("public/tixx-settings.js", "local-demo-pass.html"):
        fp = SITE / rel
        if fp.is_file() and patch_file(fp):
            changed.append(str(fp.relative_to(ROOT)))
    for rel in ("tm-email-gate.js", "api/tm-passes-fetch.js", "api/tm-pkpass.js"):
        fp = ROOT / rel
        if fp.is_file() and patch_file(fp):
            changed.append(str(fp.relative_to(ROOT)))
    api_rem = ROOT / "api" / "ticket-reminders"
    for fp in api_rem.rglob("*.js") if api_rem.is_dir() else []:
        if patch_file(fp):
            changed.append(str(fp.relative_to(ROOT)))
    for fp in (SITE / "api" / "ticket-reminders").glob("*.js"):
        if patch_file(fp):
            changed.append(str(fp.relative_to(ROOT)))
    print("patched:", len(changed))
    for c in changed:
        print(" ", c)


if __name__ == "__main__":
    main()
