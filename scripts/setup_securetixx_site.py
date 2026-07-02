#!/usr/bin/env python3
"""Clone tm-vercel-site → securetixx-vercel-site and apply SecureTixx branding."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "ticketmaster" / "tm-vercel-site"
DST = ROOT / "ticketmaster" / "securetixx-vercel-site"

SKIP_DIRS = {"node_modules", "__pycache__", ".git"}
SKIP_FILES = {".DS_Store"}
SKIP_SUFFIXES = {".rar"}

LOGO_HEADER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 40" fill="none" role="img" aria-label="SecureTixx">
  <defs>
    <linearGradient id="stx-h" x1="2" y1="4" x2="38" y2="36" gradientUnits="userSpaceOnUse">
      <stop stop-color="#34d399"/>
      <stop offset="1" stop-color="#059669"/>
    </linearGradient>
  </defs>
  <rect x="2" y="4" width="34" height="32" rx="8" fill="url(#stx-h)"/>
  <path d="M19 11l8 5v6.5c0 4.4-3.6 7.6-8 8.8-4.4-1.2-8-4.4-8-8.8v-6.5l8-5Z" fill="#fff" opacity=".93"/>
  <path d="M16.5 22l2.2 2.2 4.5-5.2" stroke="#059669" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  <text x="46" y="27" font-family="Sora, Inter, system-ui, sans-serif" font-size="17" font-weight="800" fill="#f8fafc">Secure</text>
  <text x="108" y="27" font-family="Sora, Inter, system-ui, sans-serif" font-size="17" font-weight="800" fill="#34d399">Tixx</text>
</svg>
"""

LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 36" fill="none" role="img" aria-label="SecureTixx">
  <defs>
    <linearGradient id="stx-l" x1="2" y1="2" x2="34" y2="34" gradientUnits="userSpaceOnUse">
      <stop stop-color="#34d399"/>
      <stop offset="1" stop-color="#059669"/>
    </linearGradient>
  </defs>
  <rect x="2" y="2" width="32" height="32" rx="8" fill="url(#stx-l)"/>
  <path d="M18 9l7 4.5v6c0 4-3.2 7-7 8.2-3.8-1.2-7-4.2-7-8.2v-6l7-4.5Z" fill="#fff" opacity=".93"/>
  <text x="42" y="24" font-family="Sora, Inter, system-ui, sans-serif" font-size="15" font-weight="800" fill="#0f172a">Secure</text>
  <text x="98" y="24" font-family="Sora, Inter, system-ui, sans-serif" font-size="15" font-weight="800" fill="#059669">Tixx</text>
</svg>
"""

MARK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none" role="img" aria-label="SecureTixx">
  <defs>
    <linearGradient id="stx-m" x1="4" y1="4" x2="44" y2="44" gradientUnits="userSpaceOnUse">
      <stop stop-color="#34d399"/>
      <stop offset="1" stop-color="#059669"/>
    </linearGradient>
  </defs>
  <rect x="4" y="6" width="40" height="36" rx="10" fill="url(#stx-m)"/>
  <path d="M24 12l10 6v8c0 5.5-4.5 9.5-10 11-5.5-1.5-10-5.5-10-11v-8l10-6Z" fill="#fff" opacity=".92"/>
  <path d="M21 26l3 3 6-7" stroke="#059669" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none">
  <rect width="32" height="32" rx="8" fill="#059669"/>
  <path d="M16 8l7 4.5v5.5c0 3.5-2.8 6-7 7-4.2-1-7-3.5-7-7v-5.5L16 8Z" fill="#fff" opacity=".92"/>
</svg>
"""

COLOR_REPL = [
    ("#026cdf", "#059669"),
    ("#0153a3", "#047857"),
    ("#1a7fe0", "#34d399"),
    ("#0b74e9", "#10b981"),
    ("#0256b8", "#047857"),
    ("#0284f5", "#34d399"),
    ("rgba(2, 108, 223, 0.14)", "rgba(5, 150, 105, 0.14)"),
    ("rgba(2,108,223,.1)", "rgba(5,150,105,.12)"),
    ('content="#0f172a"', 'content="#047857"'),
    ('content="#026cdf"', 'content="#059669"'),
]

TEXT_REPL = [
    ("Tixx — Live events marketplace", "SecureTixx — Live events marketplace"),
    ("Tixx Shop — Verified tickets marketplace", "SecureTixx Shop — Verified tickets marketplace"),
    ("Tixx | Live Ticket Marketplace", "SecureTixx | Live Ticket Marketplace"),
    ("document.title = 'Tixx | Live Ticket Marketplace'", "document.title = 'SecureTixx | Live Ticket Marketplace'"),
    ("Already bought on Tixx?", "Already bought on SecureTixx?"),
    ("Tixx helps fans access tickets", "SecureTixx helps fans access tickets"),
    ('aria-label="Tixx home"', 'aria-label="SecureTixx home"'),
    ('alt="tixx.pw"', 'alt="SecureTixx"'),
    ("https://www.instagram.com/tixxpw/", "https://securetixx.com"),
    ('aria-label="Tixx on Instagram (@tixxpw)"', 'aria-label="SecureTixx website"'),
    ("@tixxpw", "securetixx.com"),
    ("https://tixx.pw", "https://securetixx.com"),
    ('title="Ticketmaster · Sign in"', 'title="SecureTixx · Sign in"'),
    ('<title>Ticketmaster · Sign in</title>', '<title>SecureTixx · Sign in</title>'),
    ('<title>My tickets</title>', '<title>SecureTixx · My tickets</title>'),
    (
        'src="/public/tixx-logo-header-sm.png" srcset="/public/tixx-logo-header-sm.png 1x, /public/tixx-logo-header.png 2x"',
        'src="/public/securetixx-logo-header.svg"',
    ),
    ('src="/public/tixx-logo-sm.png"', 'src="/public/securetixx-logo.svg"'),
    ('src="/public/tixx-mark.svg"', 'src="/public/securetixx-mark.svg"'),
    ('src="/public/tixx-mark.png"', 'src="/public/securetixx-mark.svg"'),
]

GATE_HOST_SNIPPET_OLD = 'h==="tixx.pw"||h==="www.tixx.pw"'
GATE_HOST_SNIPPET_NEW = (
    'h==="securetixx.com"||h==="www.securetixx.com"||h==="tixx.pw"||h==="www.tixx.pw"'
)


def should_skip(path: Path) -> bool:
    if path.name in SKIP_FILES:
        return True
    if path.suffix.lower() in SKIP_SUFFIXES:
        return True
    return any(part in SKIP_DIRS for part in path.parts)


def copy_tree() -> None:
    if DST.exists():
        shutil.rmtree(DST)
    for src_path in SRC.rglob("*"):
        rel = src_path.relative_to(SRC)
        if should_skip(src_path):
            continue
        dst_path = DST / rel
        if src_path.is_dir():
            dst_path.mkdir(parents=True, exist_ok=True)
        else:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)


def patch_text(path: Path, repl: list[tuple[str, str]]) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    orig = text
    for a, b in repl:
        text = text.replace(a, b)
    if text != orig:
        path.write_text(text, encoding="utf-8", newline="\n")
        return True
    return False


def write_logos() -> None:
    pub = DST / "public"
    pub.mkdir(parents=True, exist_ok=True)
    (pub / "securetixx-logo-header.svg").write_text(LOGO_HEADER_SVG, encoding="utf-8", newline="\n")
    (pub / "securetixx-logo.svg").write_text(LOGO_SVG, encoding="utf-8", newline="\n")
    (pub / "securetixx-mark.svg").write_text(MARK_SVG, encoding="utf-8", newline="\n")
    (pub / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8", newline="\n")


def patch_site() -> list[str]:
    changed: list[str] = []
    for fp in sorted(DST.glob("*.html")):
        if patch_text(fp, COLOR_REPL + TEXT_REPL):
            changed.append(str(fp.relative_to(ROOT)))
    for rel in ("public/tixx-settings.js", "local-demo-pass.html"):
        fp = DST / rel
        if patch_text(fp, COLOR_REPL + TEXT_REPL):
            changed.append(str(fp.relative_to(ROOT)))
    for fp in (DST / "api" / "ticket-reminders").glob("*.js"):
        if patch_text(fp, [('"https://tixx.pw"', '"https://securetixx.com"')]):
            changed.append(str(fp.relative_to(ROOT)))
    gate_src = ROOT / "tm-email-gate.js"
    gate_dst = DST / "tm-email-gate.js"
    if gate_src.is_file():
        shutil.copy2(gate_src, gate_dst)
        patch_text(
            gate_dst,
            [
                (
                    "Email gate before barcode on pass URLs: /tickets/:gid/:slug on tixx.pw or localhost (preview).",
                    "Email gate before barcode on pass URLs: /tickets/:gid/:slug on securetixx.com (or legacy tixx.pw) or localhost (preview).",
                ),
                ('h === "tixx.pw"', 'h === "securetixx.com"'),
                ('h === "www.tixx.pw"', 'h === "www.securetixx.com"'),
            ],
        )
        text = gate_dst.read_text(encoding="utf-8")
        if "www.securetixx.com" in text and "www.tixx.pw" not in text.split("isGateHost")[1][:400]:
            text = text.replace(
                'return (\n      h === "securetixx.com" ||\n      h === "www.securetixx.com" ||',
                'return (\n      h === "securetixx.com" ||\n      h === "www.securetixx.com" ||\n      h === "tixx.pw" ||\n      h === "www.tixx.pw" ||',
                1,
            )
            gate_dst.write_text(text, encoding="utf-8", newline="\n")
        changed.append(str(gate_dst.relative_to(ROOT)))
    demo = DST / "local-demo-pass.html"
    if demo.is_file():
        text = demo.read_text(encoding="utf-8")
        text = text.replace(GATE_HOST_SNIPPET_OLD, GATE_HOST_SNIPPET_NEW)
        demo.write_text(text, encoding="utf-8", newline="\n")
    return changed


def write_readme() -> None:
    readme = DST / "README.md"
    readme.write_text(
        """# SecureTixx Vercel site (frontend clone)

1:1 copy of `ticketmaster/tm-vercel-site` with SecureTixx branding (emerald palette, securetixx.com).

**Same backend / database as Tixx** — deploy as a second Vercel project from this repo root:

```bash
npm run build:securetixx
```

Set Vercel **Build Command** to `npm run build:securetixx` and add domains `securetixx.com` / `www.securetixx.com`.

Env (shared with Tixx): shop DB, Redis, `TM_PASSES_STATIC_URL`, etc. Optional:

- `TICKETS_PUBLIC_ORIGIN=https://securetixx.com`

## Refresh from Tixx template

```bash
python scripts/setup_securetixx_site.py
```

Re-runs clone + rebrand from `tm-vercel-site`.
""",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    if not SRC.is_dir():
        raise SystemExit(f"missing source: {SRC}")
    copy_tree()
    write_logos()
    changed = patch_site()
    write_readme()
    print(f"cloned {SRC.relative_to(ROOT)} -> {DST.relative_to(ROOT)}")
    print(f"patched {len(changed)} files")


if __name__ == "__main__":
    main()
