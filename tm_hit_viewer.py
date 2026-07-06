#!/usr/bin/env python3
"""
TM hit / success.txt → local HTML viewer (SecureMyPass-style dashboard feel).

  python tm_hit_viewer.py hit.txt --tickets tickets.txt   # real barcodes (tm-fcap checker output)
  python tm_hit_viewer.py --demo   # sample hit + zlib-embedded tickets (no tickets.txt)
  python tm_hit_viewer.py myhit.txt --embedded-tickets   # merge built-in embedded dump by email
  python tm_hit_viewer.py export.txt --fetch-barcodes   # uses built-in default proxy unless --no-proxy
  python tm_hit_viewer.py export.txt --fetch-barcodes --proxy host:port:user:pass
  set TM_HIT_VIEWER_PROXY=host:port:user:pass   # overrides default; --no-proxy skips default only
  python tm_hit_viewer.py export.txt --fetch-barcodes     # pull secure_token via TM app API (cookies)
  python tm_hit_viewer.py --demo --fetch-barcodes         # merges draft/results/tm_auth_cookie_string.txt if present
  python tm_hit_viewer.py --demo
  python tm_hit_viewer.py path/to/export.txt
  python tm_hit_viewer.py --no-open
  python tm_hit_viewer.py -o out.html
  python tm_hit_viewer.py --inject-pass-transfer-ui path/to/site --replace-pass-transfer-ui \\
      --inject-mail-api-base http://YOUR_VPS:9440   # refresh old inject + stubby URL for pass pages
  python tm_hit_viewer.py --ignite-stubby path/to/tm-vercel-site --stubby-proxy-url http://VPS:9440
      # one-liner for pipelines: re-inject transfer UI on every pass + write tm_viewer_mail_api_base.js
      # HTTPS live site: omit --stubby-proxy-url; set Vercel TM_VIEWER_EMAIL_BACKEND_URL=http://VPS:9440 (server proxies; browser stays same-origin)
  python tm_hit_viewer.py --refresh-pass-safetix path/to/tm-vercel-site
      # patch all tickets/<gid>/*.html: drop PDF417 debug UI + refresh embedded SafeTix JS (no success.txt regen)
  python tm_hit_viewer.py --regen-all-passes path/to/tm-vercel-site
      # rebuild every tickets/<gid>/*.html with current pass layout (hero/gate/QR sizing); keeps same paths + barcodes
  python tm_hit_viewer.py --inject-ticket-reminders path/to/tm-vercel-site
      # add reminder metas + tm-email-gate.js only (does not touch barcodes / data-tm-safetix)
  python tm_hit_viewer.py --inject-ticket-reminders path/to/tm-vercel-site --replace-ticket-reminders  # refresh prior inject
  python tm_hit_viewer.py --update-reminder-dates path/to/tm-vercel-site --links-txt path/to/links.txt
      # update tm-event-start / tm-reminder-date metas in existing pass HTML from links.txt
  python tm_hit_viewer.py --update-pass-date path/to/tm-vercel-site --only-pass https://tixx.pw/tickets/2878/o6NocVbRJYBYYUuLV88 --event-date 2026-08-01 --event-time 19:00 --event-timezone America/Chicago
      # patch visible pass subtitle + reminder metas (barcodes unchanged); run on host that has tickets/<gid>/*.html

  Stubhub VPS layout (Administrator acct — ``tm.bz`` bundle from screenshots): the argument is always the folder **above**
  ``tickets`` (usually ``tm-vercel-site``), never ``…\\tm-vercel-site\\tickets`` itself::
      cd /d C:\\Users\\Administrator\\Desktop\\Stubhub\\stubhub\\tm.bz
      python tm_hit_viewer.py --refresh-pass-safetix "C:\\Users\\Administrator\\Desktop\\Stubhub\\stubhub\\tm.bz\\tm-vercel-site" --dev-pass
      python tm_hit_viewer.py --refresh-pass-safetix tm-vercel-site --only-pass https://tixx.pw/tickets/19/tsu2grMCGuG9IKgNc4Uu
      python tm_hit_viewer.py --update-pass-date tm-vercel-site --only-pass https://tixx.pw/tickets/2878/o6NocVbRJYBYYUuLV88 --event-date 2026-08-01 --event-time 19:00 --event-timezone America/Chicago
      python tm_hit_viewer.py --inject-ticket-reminders "C:\\Users\\Administrator\\Desktop\\Stubhub\\stubhub\\tm.bz\\tm-vercel-site"
      python tm_hit_viewer.py --inject-ticket-reminders "C:\\Users\\Administrator\\Desktop\\Stubhub\\stubhub\\tm.bz\\tm-vercel-site" --replace-ticket-reminders

  Reslug stubhub stock + inject barcodes from pass HTML (VPS with tm-vercel-site + secure_pass_stock.csv)::
      cd /d C:\\Users\\Administrator\\Desktop\\Stubhub\\stubhub\\tm.bz
      python tm_hit_viewer.py --reslug-secure-pass-stock
      python tm_hit_viewer.py --reslug-secure-pass-stock --confirm
      python tm_hit_viewer.py --backfill-stock-barcodes --confirm
      python tm_hit_viewer.py --backfill-stock-barcodes --confirm --barcode-only

Defaults for delivered links (registry / stubby when env unset): gateway ``https://tixx.cc/tickets/…``,
pass site ``https://tixx.pw`` (``TM_VIEWER_GATEWAY_PUBLIC_BASE``, ``TM_VIEWER_WATCH_PUBLIC_BASE``, ``TM_VIEWER_USE_PASS_GATEWAY``).

Reminder emails (optional): ``--site-dir`` pass HTML includes ``<meta name="tm-reminder-register-url">`` (default HTTPS Vercel API) and ``tm-event-title``;
when a checker upcoming line parses to ``YYYY-MM-DD HH:MM:SS`` (optional ``(America/New_York)`` IANA TZ), emits ``tm-event-start`` UTC ISO for ``/api/ticket-reminders/register``.
Disable head metas: ``TM_VIEWER_REMINDER_METAS=0``. **VPS-only** passes: set ``TM_VIEWER_REMINDER_REGISTER_URL=/api/ticket-reminders/register`` and ``TM_VIEWER_EMBED_EMAIL_GATE=1`` so the gate loads from your pass host and POSTs to the registry, which forwards via ``TM_REMINDER_REGISTER_FORWARD_URL`` (see tm_viewer_link_registry.py).
``TM_VIEWER_EMAIL_GATE_JS_URL`` overrides the deferred script ``src`` (default **``/tm-email-gate.js``** — must exist on the pass host after ``tm-vercel-site`` ``npm run build`` deploy).

Blocks: separated by --- or a line of dashes (same idea as checker success.txt).

Go checker output (important): success.txt from cmd/checker only has combo, name, events, cards — it does not dump cookies or the in-memory accessToken from accounts/exchange. Rotating barcodes for that run are in tickets.txt (Secure Token per ticket). If your paste includes a Cookies: block, that was merged from another source (browser export, stub script, etc.), not from the stock success.txt writer.

Barcodes need TM secure_token (t, ck, ek): either
  • --tickets tickets.txt — primary path for Go checker (same run as success.txt); pipe rows or === email:pass | Ticket N === blocks with Secure Token: lines; matched by email from the hit header.
  • --fetch-barcodes — same API URLs as Go checker, but needs a token acceptable as access-token-host (the checker’s OAuth accessToken). Web id-token in pasted cookies often yields HTTP 401 on events.json even when the account line came from checker success.txt.
  • optional line per block: SecureToken: <base64>

Rotating PDF417: same string as tm-fcap-makefast/barcode.py generate_barcode_data (rawToken::TOTP(ek)::TOTP(ck)::unix), 15s step, HMAC-SHA1 — documented in barcode.py as matching TM presence-secure-entry.js. Browser path uses CryptoJS+bwip-js with the same formula. Run: python tm_hit_viewer.py --verify-crypto

Ticket UI: TM-style mobile pass (hero art, barcode, seats, Wallet / Info). Hero image from (1) TM events.json event_image.url when using --fetch-barcodes, (2) verbose ticket lines Poster: or Event Image: https://…, (3) JSON cache draft/results/tm_event_media.json, (4) --resolve-event-images (Discovery API), (5) gradient fallback.

  **Apple Wallet (optional, --site-dir):** defaults are **hardcoded** near ``_TM_VIEWER_WALLET_HARDCODE_*`` (edit domain/secret there) if env vars are unset. Env vars ``TM_VIEWER_WALLET_PKPASS_BASE``, ``TM_VIEWER_WALLET_PKPASS_SECRET``, ``TM_VIEWER_WALLET_PASS_ORIGIN`` still **override** when set. Pass pages download **signed .pkpass** from your API; Apple certs stay on Vercel — see ``tm-vercel-site/README.md`` and ``api/tm-pkpass.js`` fallbacks. Ticketmaster ``Apple Wallet:`` URLs in ``tickets.txt`` are **ignored** by default unless ``TM_VIEWER_WALLET_ALLOW_TM_PKPASS=1``.

  python tm_hit_viewer.py hit.txt --tickets t.txt --resolve-event-images   # web lookup + save cache
  python tm_hit_viewer.py hit.txt --tickets t.txt --download-event-images  # copy images next to HTML
  With ``--download-event-images``, rows keep ``image_url_remote`` (HTTPS). The pass **prefers that URL** in ``<img src>`` so Vercel works even if ``tm_event_assets/`` is not deployed; set env ``TM_VIEWER_HERO_PREFER=local`` to force ``../../tm_event_assets/…`` only.
  Discovery key: env ``TM_DISCOVERY_CONSUMER_KEY`` (recommended) or constants below — use a **Discovery API** consumer key from developer.ticketmaster.com (the iOS ``TM_API_KEY`` is often rejected with HTTP 401 on ``/discovery/v2/``).

  Barcode row order: after merging ``tickets.txt``, ``barcode_tokens`` are reordered when (1) each row's section/row/seat appears on a **distinct** ``upcoming`` line, or (2) each row's event title matches a **distinct** upcoming line; then rows are **sorted** by event + section + row + seat so ``--one-html-per-seat`` slot index matches TM-style ordering. One-off fix: env ``TM_VIEWER_SAFETIX_SLUG_OVERRIDES`` (JSON: slug without ``.html`` → ``{"t","ek","ck"}``) or ``TM_VIEWER_SAFETIX_SLUG_OVERRIDES_FILE``.

  SafeTix clock vs TM app: the pass uses the viewer device clock by default. For **TM’s HTTP time** (``Date`` on www.ticketmaster.com), deploy Vercel ``api/tm-clock.js`` and set ``TM_VIEWER_SAFETIX_TM_CLOCK_URL=/api/tm-clock`` (or full ``https://your.domain/api/tm-clock``) when generating—browser fetches that JSON and skews to match. The app often **lags** that web/CDN clock, so passes can still look **ahead** until you set Vercel ``TM_CLOCK_UNIX_FUDGE_SEC`` (negative) and/or ``TM_VIEWER_SAFETIX_TIME_SKEW_SEC``. Optional ``TM_VIEWER_SAFETIX_TM_CLOCK_REFRESH_SEC`` (10–600) overrides the default 120s re-pull. ``TM_VIEWER_SAFETIX_SYNC_DATE_HEADER=1`` uses same-origin ``HEAD`` only if ``tm_clock_url`` is unset.

HTML needs network: CryptoJS + bwip-js (CDN). --fetch-barcodes / Discovery / downloads use HTTPS. Keep real exports local; do not commit secrets.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import base64
from datetime import datetime, timezone
import binascii
import os
import subprocess
import gzip
import hashlib
import hmac
import html
import json
import re
import ssl
import struct
import sys
import time
import uuid
import secrets
import zlib
import webbrowser
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def _tm_viewer_debug_enabled() -> bool:
    """Append hero/media lines to debug.txt unless TM_VIEWER_DEBUG=0."""
    v = (os.environ.get("TM_VIEWER_DEBUG") or "1").strip().lower()
    return v not in ("0", "false", "off", "no", "skip")


def _tm_viewer_debug_log_path() -> Path:
    custom = (os.environ.get("TM_VIEWER_DEBUG_LOG") or "").strip()
    if custom:
        return Path(custom).expanduser().resolve()
    return Path(__file__).resolve().parent / "debug.txt"


def _tm_viewer_debug_log(msg: str) -> None:
    if not _tm_viewer_debug_enabled():
        return
    try:
        p = _tm_viewer_debug_log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        line = f"{datetime.now().isoformat(timespec='seconds')} {msg}\n"
        with p.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def _tm_viewer_hero_prefer_local_files() -> bool:
    """If true, pass UI uses ../../tm_event_assets paths; else prefer HTTPS (CDN) when we have it."""
    v = (os.environ.get("TM_VIEWER_HERO_PREFER") or "").strip().lower()
    return v in ("local", "file", "static", "1", "yes", "true")


def _tm_viewer_debug_resolve_asset(base_dir: Path, url_or_rel: str) -> tuple[str, bool]:
    """For debug: site-root path and whether file exists (local assets only)."""
    s = (url_or_rel or "").strip().replace("\\", "/")
    if not s or s.startswith(("http://", "https://", "data:", "//")):
        return "", False
    rel = s.lstrip("./")
    while rel.startswith("../"):
        rel = rel[3:]
    if not rel:
        return "", False
    path = (base_dir / rel).resolve()
    try:
        path.relative_to(base_dir.resolve())
    except ValueError:
        return str(path), False
    return str(path), path.is_file()


def _merge_site_asset_href(prefix: str, path: str) -> str:
    """Prefix stored paths (e.g. tm_event_assets/x.jpg) for use in HTML src/href."""
    s = (path or "").strip()
    pfx = (prefix or "").strip()
    if not s or not pfx:
        return s
    if s.startswith(("http://", "https://", "data:", "/")):
        return s
    return pfx.rstrip("/") + "/" + s.lstrip("/")


def _resolve_pass_asset_under_site_root(site_root: Path, url_or_rel: str) -> Path | None:
    """If url_or_rel is a site-relative asset path, return resolved path under site_root; else None."""
    s = (url_or_rel or "").strip().replace("\\", "/")
    if not s or s.startswith(("http://", "https://", "data:", "//")):
        return None
    if s.startswith("/"):
        rel = s.lstrip("/")
    else:
        rel = s.lstrip("./")
        while rel.startswith("../"):
            rel = rel[3:]
    if not rel:
        return None
    try:
        root = site_root.resolve()
        path = (root / rel).resolve()
        path.relative_to(root)
        return path
    except ValueError:
        return None


def _pass_hero_url_safe_for_img_src(iu: str, *, site_root: Path | None) -> bool:
    """Reject traversal / script URLs in hero src; keep normal https and safe local assets only."""
    s = (iu or "").strip()
    if not s or "\x00" in s:
        return False
    low = s.lower()
    if low.startswith(("javascript:", "vbscript:", "file:")):
        return False
    if s.startswith(("http://", "https://")):
        return True
    if s.startswith("data:"):
        return bool(re.match(r"^data:image/(png|jpe?g|gif|webp|svg\+xml);", s, re.I))
    if s.startswith("//"):
        return False
    if s.startswith("/"):
        if ".." in s:
            return False
        return True
    if site_root is not None:
        return _resolve_pass_asset_under_site_root(site_root, s) is not None
    return not (".." in s or s.startswith("\\"))


# Demo block: success.txt-shaped text + Cookies (checker’s success.txt alone has no Cookies:); zlib+base64 cookie blob + password in header — keep private; rotate secrets if leaked.
_LANDEN_DEMO_CK_B64 = (
    "eJyllseurEgShl/lbmbV4gze9NVZ4E3hCldmg5LE+8IV1GjefeqcuepuzaqlWZAS8X8K/gwiEkzeVkNelT+zHlnnnz/SaobDlk1H3A4QLNXQf/7rHzgOh7VfpkMc0ux99/v7Wuf38g9cfK9pNsOpGr/"
    "gX6I5vFWU74uszeZvCBX5P/giGzQwl79Y7kHBP6QW9MVfHvJt6i/iUi3rHyJBfqAUjv4pD33xVx3BMPYDJ4k/iQ5MTbbo6ReAM3+N2aDL/pb3/u+Ca18tv8Cu+gZ+Cfk0dFoG0mz6iv2eg3bO/lTCOZu+wsu0Zv/++SMb53iu0s+MIAGeYhmNZmyC4cQHxjAkw5IcTn+QAP6zZtbfGF3L98pBDwdqTkUczsslFLXSW3hwv7EoRXPPz++MOfxMkwRnCDJNsIRlCZajUApkaMrmWQIpkkghjrMgJ2gIM5jmeULidI4BQFIY8WYJ+POHoEufCGXxrSlBvIi1sS1tThMrv+usfJDW+nEt2RYAHy2HY8qUh6+kyUMKH9dD8RVv0tUOPapOoykH9zz2zo+v5ucP/50VqJMEMBJxuWvE2qlKRub1tS93M293ROYIfA6yLWYbX1zxWSkwVAiea17LXNSVQmjmjnwGgtKk6+NGiST5buqlG+N3EdOUQ/MM0BhHQQwQLA0SnCMI+C5jBjIKzXFAMO8QzaZ0zrAEQBMKI2HG0XiKkpD5+aMDH2OzTM1ndhjlXfXOt6v9AnhE6fXI6I3hB1gaeJFeOf1cJarySmUFTdVogZrX3kWdtgJI2BIkbak57B7j8vN3UvN/pvBtePnEfhd52VfdPGHSEmUjrg5PnDIyBk88uFR/OrtsJijqVfqUuCb6sip7zpLDUdwV7UXn0unNwHRGwwtXv0ijrK7gOjORG7TZ0FdUzUsc4KBj5djdHxPX2pgBXueErDWL/3aVvmsmG+0u72TOhJjmoaPmNaMSyJHthWEUHJ0j3Eb7/vzGvzpCPxrRwFR2K4ftFfkvUzdEfDyucybWuDkVUn+8IqyXn+q9w27Yg5HrGyJurrvT8CH4caWvBAq5NRqSG+CK77xfPaHQdOzmwryX2oBo4oAwMGPoed7d4qQS+TkoEGXQLR7LbDLQlBc4n24jdoWjuMptf3lubOy010rzBslWyiywUqr6+SOw+ND5zMC8xDjOn/Id314afZzHyrnd98Irz2yqzM1vaqZoS6GPBcr1Ffn57Ur9svXVBokKK6cy/BCVlwBVlFBEDzu4VaZotElnfWmCVYf4GTUkMywDO5APvUc/RLTxlqAQJC3JzFScgkvlTJ4vPrYQaDlrG85EWGpcS2AITn3yChYjCLjbUuTOnG1eBGFADhuFYvO4VZlx2oqroPvE5J3bjnjkJmarQnzgcXyybc+/NQC7oII1nsb3Vg6YTMk8jY2ym03ebL5xPhEnnI44JY6jsiGRHnPnbsAXHsBlbLUjmx7q0L8ukXe/NOrzGYGqzh+xQdOP/nWV0jJUxXxlQ/FxKJFbImIrrhobv3IcMcVLfwKlud3xkMiZMXL1YzWpd/PS2hDt6CSgkZlsWT1PhXM1y2c8Oyt99iO1RIJ4Ke4IAJQTmyt2oeYrvMbMktWYN4letQNnILqXe0Fwy66qV8l/UPH6fgfxk0ljwk1X6X0mQpT/wPias1vhEN/1QPacvFQW6c4KAzG8nhFlqomhTrAtnOoqb9a3E9pRFm/h1MzumL2bkYNZRitSwN6e0HpmLQeUs+k5d/rhLVcFuhK8tbV0Dc1rKCZaUJ5YAO86ZFZZQvMl7uKYm+Snk6eSM+3VjMUXIcZPHTZkgwnfeONs64rFBSa8EsQAQA5PipCy442c25d8txP8bpeis9Cjv99laX3Aotwi+46FtVjAa4Bs7x2nY+EzorHu8sTQJNBCUkIOrb4nwUdhPV22OEecX5XXldzOgnd+Hrh4c/rnVOj9VOHOdU1YFWP/e86BCXRzMDRZ/3+1eXoI0TlZXoOS1bVwoJJwnucJJ2vJOGnr9QZ342LjSlAJu0sJoj7bTBK+j/tMiKX5ahiuoZYWkbfhiRyjmZa7Z9BGVN/7kt4aqaG4zZ1Jtvq8i4iyS5xr7DnxuDFiSacL422bEms3ZEny1Atc2qNrl999KdqElErsskFoJjRtXGiZzJhsSLrntSb46CZ1kDetdCWstO5E7+Ub/X5NRXG1WDWO7qh+s5RJKeRwb2aUOjRIvsZXYrKbaDYFjdam/VQyV0Dm2w1b88VuYpPfOcMcrkxeFnqSqMHDlMqok8nkpp1tMg2r4FFIlhuJl5ggrhO7C8trhnGkvST2Uvleh4brE3T14wYT/qPG1Y2yJ4bxSj0vT1hinFiX/5Ce8SWIHpp47msqPjYmTkTE3hBYbKbEV4A9bcGqgdFSqMVkBvMe3kNfn59Iw5KBnw9C3sjvaZUeTx1mlG7GQi48ziWk3Bszt77uTTTaBdfzVGnSHSzoHMjIBZwwUWgqBnADVmwh5uAn/z1BW8F4WS21zhVcng0Vb7r7KntpYO3zhbFfcAcUXJRe3zB+vBiJoq6R8bSKQIGPqJ6NqeShLj5x/65QmsM6Mo354WIOavX+1J47aQFU21Ki7OkM/nC5Z4Oda5pvtteT296Z9XbxGl3T8ht1slTyNla6lQ7xrp9Eq+jZA0MvljYHxtOx2AvjPtf6tHNnslvCOqm7ZzmfCavIb2cPTe3S3VQizEDB+jYOBsSWNpn8CG3PbcnHhWebSNyMxQE1s3uVCiiVwooHbe8aP2wKNhDozx9zNs/v/2M9/UwoFmSQZRACxTiETCgaYXOaQkgcBzlECSJDwX8AJhbBDA=="
)
_LANDEN_DEMO_CK = zlib.decompress(base64.b64decode(_LANDEN_DEMO_CK_B64)).decode()

EXAMPLE_HIT = (
    "landenmaynard@gmail.com:Sixpak1a | Name: landen maynard | +15203100831 | Upcoming Events: 4 | Past Events: 1\n"
    "Upcoming Events:\n"
    "→ PARKWHIZ DESERT DIAMOND ARENA | 1x tickets | 2026-04-10 19:00:00 (America/Phoenix) | Desert Diamond Arena, Glendale, AZ | Status: ONSALE\n"
    "→ Mercy Me - Wonder + Awe Tour | 0x tickets | 2026-04-10 19:00:00 (America/Phoenix) | Desert Diamond Arena, Glendale, AZ | Status: ONSALE\n"
    "→ Good Kid - Can We Hang Out? Tour | 2x tickets | 2026-05-01 20:00:00 (America/Phoenix) | The Van Buren, Phoenix, AZ | Status: ONSALE\n"
    "→  Alex Warren: Finding Family on the Road | 5x tickets | 2026-06-05 19:30:00 (America/Phoenix) | Mortgage Matchup Center, Phoenix, AZ | Status: ONSALE\n"
    "Past Events:\n"
    '→ Alex Warren: "Cheaper than Therapy" Tour | 1x tickets | 2025-06-06 | The Van Buren\n'
    "Cards: [CREDIT_CARD VISA ****1895 06/2030]\n"
    "Cookies:\n"
    f"  [auth.ticketmaster.com] {_LANDEN_DEMO_CK}\n"
    f"  [app.ticketmaster.com] {_LANDEN_DEMO_CK}\n"
    f"  [www.ticketmaster.com] {_LANDEN_DEMO_CK}\n"
    f"  [payment.ticketmaster.com] {_LANDEN_DEMO_CK}\n"
    f"  [promoted.ticketmaster.com] {_LANDEN_DEMO_CK}\n"
    "-----------------------------------"
)

# zlib+base64 of Go checker multiline tickets dump; merged on --demo or --embedded-tickets (no external tickets.txt).
_EMBEDDED_TICKETS_ZB64 = (
    "eJztm1lz2sgWx99Tle+gp3m5ZdyrpHaVay5YAkMsYUBi0YurpW6BQCwjZDCq++FvCzveyJBklqpkBqdIya0+3X16+f90jvDl5aWW8oWQiznfLXgm/jue8yStRMv5RS95WPEZ5Nr/NC+JZjLXoHZ5efnxg6bZG7nIL7TbavfT4LoZaJbds7ueZjWrTtu1tGrXdqvP9bSrpZAXmk37DUAgUM1ZyTpaak3rQoPVu2B2LxozUdzEwVjdu16u88dbDAAdE1w3DYsATMv2ejLKk+XiQmt6DlSVu8vthdaoGuqyJ7kaEcLlaHcrWRaXFg25kBlPtaqYJ+v13nYk16pSJ9+pPvZVeK6ql1dPbj7a3/JsNpgkRXnjNksiVYRQhQDN71llWTsTMlNN4DOMTETPq91ANXt7n0UTvpZC1QZIPwPoDCIPgAuMLzAMXvXSy3l+v77Qqv1q86Zau7GV9b7N5ztXbef2xvZsq/Qp44t1XHbotr03Nl252A/kddmtmsRkMX5XuezckmmykZnyPZ8kmVBO5jvl3ZxnOz9Ly3l86rzu39SbNzf7zj93sZ/m8Xy/9uq6vszm5aSX7dZ4Fu2X+WmZ7jOpecuZXDzN7NPwNb97c6FN8ny1vjg/3263lXw/G3O+zmVWbrvz+7XMzmW5cdbnQuZqN67P8yfz8/eb4jyxRh0hrzf8nt2deXy1vEvmWTufO0vUM1krHwbRHapeXv4a3/HV6jLP7uUv0XKxVs3fRWrhx8ssketLnqbPxaprscyeytKkLFqlPI+Vt5fJcv2LOi/jez6Wl3Jx5vd+Uc1uErlVZlm5vy5hBVTA8wb5VoeXZeVv9uZgHsoR/PrFkXzRhe+YgVfz9tbxjx/Ovv7z8cPHD5ffpTHoncY4Mot26n/tTBssy22o/UerbsvNdZ8dSMwxhZFjiBf1LylMjSKGqqb5RmGsz/IC9Wd1gS/q0i0Vr29bLwJSv2m3u8rs88+BoPRllsSJFOo4rXkqn26+khKkxgOoSSBkiJnENH9HT/CTnkBSYZD9FZryzXryO1ritGvNfcVj6pEt1U3Vyt16Nw+X6XK8e60nbv3qrtv2ql7Tbdz1Rk6tfdNujF6pzK1VJ9B4ozUUMkNNFmMImRhEh9Ijd62kOV0mrmdTt7Af2t6MOtMmcYqa1Uy2ibhq6s1ZyxshVusOA90dTlpRuur1rieIF+6tGK5uejZFrtWkwmaDEXDdoKgv+rC2crwOcgetfncottzO15207oqB2+tZrZZAo+TmqjXlO9X+1EYOcueONUlHAx8GU1/1P0LBwJ2Xn7bV2QVTB4+8SepOI+RObewgp7RPH+3Vb0U6H01nqG115850TJ2ingbTWeF66cy1AnUdJE7Rga7VSkbTEVTtlPa7vX+L1kY06oAP6GKIXRoOWpuwwRay12LljFVXK7UZB+qsy/xFqdShP1SqfP5wtsqW4nwDz1d8vZbr83fHq9K+td2725uqV293ncrbBapgiojBDARw5brd8yrNdq+Sz8Owoha/QrAwpY5jSbGMEQwpI8oMqn/EAFTHehxG2AihNKEhiNSRlBwQwkNCKJMi/jsw81kZzmfTbWd0I80gW443V0ahf8KI2p+i1vRqvapVV550OxNRbchpuurPXXjHkvmSYHOxmF7tOtWfBD9/1suDefvnYAn/yFgiJyz9SFgCuo4wVkuODAb0I1hyrBFypk7hWJ0HZxpRxwpeY2nY9VOFpdFDmOTZC5bEC5am9U8OrBYdEKDBrLlz0QwIwLZy2Kr150HHR7TL05bv1/1tdyEyZ2qfsKSw9HaBvoIlZhpYVdRDLjgWUIQ0AlxhCfNIhBBC09QNSMxYYJ0KGXEeMT0GQjeAwhUxT1g6YenvwxJ5h6XGcim0T4lQWLriC20gtWs1DK19n//6ZTTV+oAC+BZNs5m5cX9bNqpwYKGzQzQZFFbrRg3b8A2aGlX0kpKBLymZP5qRaVQf4XVArGqWJ2pAt9keWK/yMwRV6Pv8DMVnRDdM/MX8DD2D6AwwDxoXgFwg8C+G1pfzNn9Shd/upHcqzMqHCWIgxjAlxKTIPK7EFDPKDZ0z9dCvYoQIRySmVKLQgEBiZqjAAXBGWQSV7sZcclOJtBkCM2KxiB/d/WuV+OUgvGRuZN24s9qb3za7eVZP73V7sH6wTHu361/fjH+6PNRXvDmYh3+OstIfX1n/cK77pKz/bGU1ITMRZQjoEBg6IpAdV1b1EIyB1OMQxIgSyRDUKScCICRCpc8yhCYFnDNIIyxYSKmOOYYY0phGOopPynpS1u9QVv2dsmrVVD6ok5Bl5dmoJwuhjp9W5/Mk3WnLhZZPpNI+Lg4UdlAFOqBvFVbfgCD0Y9wwajT5wvtEnUJkm7Xau/eJCD4rrPmsr+xIWuVzidazq9636yilFXjwBpGeIYKB8Xs6Cs/gXkchviD4X6yjSKkQNAFBjAJTBeUGOZZamdrE9WziWJ1d2/O3bWuMnSICnV1z3Vx0knbSuur7M9TxfRp5zYzjFvdnE8LVUnRwd+cWYuDNl3SEaN63H64DqzsZDYJhJ023g4ZNeI/tlBguOGjCCPgwGPoP/ryPy/TNCK1V+80Hd+pOg2mVBIN66g5GsG2VCZf+NCg/0zFw5qPCRTYJvBF2p6MHt3CnpX0w2NsjpxhDB9kP7cFoO5qrOo3mLmh0J2V5mWJxiiYNvDRxvNFWleG258DSPnr0bxfi7kQ00vsAskIOYBKih02AZ0nceTx/fxJBb4/aOwQdLtZxBJnqAJiURDzEksRRHGIDhhE0DcF0KJkZCmlwxmKs66aUmIvQVLEAkASVbwEi8tcj6EUpXok2M++sq/Vvt/dKtBkdpHyzbcNGINQEb38+BB335mAe/jkIMn4WBEF4YtCPxCCdAmLqAFNTZ0qwCDKPvXWe+lvXGiPHcpT2j6hjRcS1muQtg/w9g8LCrfeGzwwqXhiU9ru+68jr1JHDtOc0ZpuwHjRHi8kubAT1cFi/7+7ydXi9uuaF+BSmJwZ9ZtDhYh1nEISSQhzpgjIudC51A0HIFZZiJJGKfUwApVARlUQYIBBjSGQUUhMIaOqRjMMTg04M+nYGmT8Ng8CJQT8SgwAGjDJMlbAhgyKglOnYK2Znq+If6hS+0mdfMcXfOZYN3zII7BkkGyIJn+Mg1nxh0KTmDvLuaFBfRNdB7s/rvXDo0l6/bw9SsYys7pUzZ0MHrjj3+3nJoRODnl41HyzWV+IgykNdsAhH1KAC6xBhAyMKCVVRlIqIqGFy9aEs0kmkGol4jJSBCof0kMvHiPjEoBODvo1B7GdhkHFC0I+EIKIjQz0EG5Tppk7UgzA8FgZZI4WRZqHCH9j2RsSddgrH6zy8RpDv1XmJIJF2O4PnMIjZLwgSRa/e5T7qr8Ki2wznrUl/0F+LuY1cO232cSsd1OvAU311QFD0gdicEPSIoMPFOo4grjhjQhmW79IZNwDSAeJmpAIoQ3JumoAwoEsTUskNrmIfAkAoRRzGhoh1FNETgk4I+o6/KQM/C4PME4N+JAbBfVqHIUbUU7VOED76TVvPV9yZqVCoSV2ruVU6DZypg96EQbOVvWeQ3Sm8l1Tc5hWDhnJa+9RLZ9RB8Nq3t0W7P7HdukNVSEW55296M2GN5pN+bzEZBmlanBj0yKDDxTrOIBBLIJlRfqvLCDFCnIQQh6pMcsrVVaxTJDEgcWwCHiIkhIFNwUNKmBFR8jd8I+HEoJ+HQf8HDAMyHw=="
)

# Strip TM-style event bullets (Unicode arrow, ->, >).
_ARROW_PREFIX = re.compile(r"^[\s\u00a0]*(?:\u2192|->|>)\s*")

TOTP_PERIOD = 15
TOTP_DIGITS = 6


# TM iOS app often lags www.ticketmaster.com HTTP Date by ~1–3s (see api/tm-clock.js).
_SAFETIX_DEFAULT_APP_LAG_SEC = -2


def _safetix_time_skew_sec_from_env() -> int | None:
    """Explicit TM_VIEWER_SAFETIX_TIME_SKEW_SEC only; None → use default when tm-clock sync is on."""
    raw = (os.environ.get("TM_VIEWER_SAFETIX_TIME_SKEW_SEC") or "").strip()
    if not raw:
        return None
    try:
        return int(raw, 10)
    except ValueError:
        return None


def _safetix_tm_clock_disabled() -> bool:
    v = (os.environ.get("TM_VIEWER_SAFETIX_NO_TM_CLOCK") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _safetix_sync_date_header_from_env() -> bool:
    v = (os.environ.get("TM_VIEWER_SAFETIX_SYNC_DATE_HEADER") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _safetix_tm_clock_refresh_sec_from_env() -> int | None:
    """Seconds between tm_clock_url re-fetches; None = viewer default (120)."""
    raw = (os.environ.get("TM_VIEWER_SAFETIX_TM_CLOCK_REFRESH_SEC") or "").strip()
    if not raw:
        return None
    try:
        n = int(raw, 10)
    except ValueError:
        return None
    return max(10, min(n, 600))


def _merge_safetix_clock_cfg(cfg_obj: dict) -> None:
    """Add skew_sec, tm_clock_url, sync_date, tm_clock_refresh_sec from env (set at generate time)."""
    tm_clock = (os.environ.get("TM_VIEWER_SAFETIX_TM_CLOCK_URL") or "/api/tm-clock").strip()
    use_tm_clock = bool(tm_clock) and not _safetix_tm_clock_disabled()
    if use_tm_clock:
        cfg_obj["tm_clock_url"] = tm_clock
        ref = _safetix_tm_clock_refresh_sec_from_env()
        if ref is not None:
            cfg_obj["tm_clock_refresh_sec"] = ref
    sk = _safetix_time_skew_sec_from_env()
    if sk is None and (use_tm_clock or _safetix_sync_date_header_from_env()):
        sk = _SAFETIX_DEFAULT_APP_LAG_SEC
    if sk is not None and sk != 0:
        cfg_obj["skew_sec"] = sk
    if _safetix_sync_date_header_from_env():
        cfg_obj["sync_date"] = 1


# Apple Wallet (site-dir): edit these if you do not use env vars. Env always wins when set.
# WARNING: do not commit real secrets to a public repository.
_TM_VIEWER_WALLET_HARDCODE_PKPASS_BASE = "https://tixx.pw/api/tm-pkpass"
_TM_VIEWER_WALLET_HARDCODE_PKPASS_SECRET = (
    "8vItCsvoKLVgPiOmWk_dAQNgD3GZhpi-XJZKPX1Oi9bCKvDeeznimUWAQop9Tx-s"
)
_TM_VIEWER_WALLET_HARDCODE_PASS_ORIGIN = "https://tixx.pw"

# Delivered pass links: gateway on tixx.cc → button → passes on tixx.pw (see tm-link-gateway/gateway.html).
_TM_VIEWER_GATEWAY_PUBLIC_BASE_DEFAULT = "https://tixx.cc"
_TM_VIEWER_PASS_SITE_PUBLIC_BASE_DEFAULT = "https://tixx.pw"
# Deferred email-gate script: same-origin path unless ``TM_VIEWER_EMAIL_GATE_JS_URL`` is set.
_TM_VIEWER_EMAIL_GATE_JS_PATH_DEFAULT = "/tm-email-gate.js"


def _tm_viewer_wallet_pkpass_base_effective() -> str:
    return (
        (os.environ.get("TM_VIEWER_WALLET_PKPASS_BASE") or "").strip()
        or _TM_VIEWER_WALLET_HARDCODE_PKPASS_BASE.strip()
    ).rstrip("/")


def _tm_viewer_wallet_pkpass_secret_effective() -> str:
    return (os.environ.get("TM_VIEWER_WALLET_PKPASS_SECRET") or "").strip() or (
        _TM_VIEWER_WALLET_HARDCODE_PKPASS_SECRET.strip()
    )


def _tm_viewer_wallet_pass_origin_effective() -> str:
    o = (
        (os.environ.get("TM_VIEWER_WALLET_PASS_ORIGIN") or "").strip()
        or (os.environ.get("TM_VIEWER_WALLET_PUBLIC_ORIGIN") or "").strip()
        or _TM_VIEWER_WALLET_HARDCODE_PASS_ORIGIN.strip()
    ).rstrip("/")
    if o:
        return o
    b = _tm_viewer_wallet_pkpass_base_effective()
    if b.startswith("http"):
        try:
            pu = urllib.parse.urlparse(b)
            if pu.scheme and pu.netloc:
                return f"{pu.scheme}://{pu.netloc}".rstrip("/")
        except Exception:
            pass
    return ""


def _tm_viewer_wallet_built_enabled() -> bool:
    """True when site-dir passes should link to our signed /api/tm-pkpass instead of tickets.txt Apple Wallet URL."""
    b = _tm_viewer_wallet_pkpass_base_effective()
    s = _tm_viewer_wallet_pkpass_secret_effective()
    o = _tm_viewer_wallet_pass_origin_effective()
    return bool(b and s and o)


def _tm_wallet_signed_pkpass_href(*, gid: int, fname: str, fields: dict) -> str | None:
    """
    HMAC-signed URL for Vercel ``GET /api/tm-pkpass`` (must match TM_WALLET_* / hardcoded fallback on the server).
    Public origin must match ``TM_WALLET_PASS_PUBLIC_ORIGIN`` (or server fallback) for QR links on the pass.
    """
    base = _tm_viewer_wallet_pkpass_base_effective()
    secret = _tm_viewer_wallet_pkpass_secret_effective()
    if not base or not secret:
        return None
    slug = _ticket_href_clean(fname)
    payload = {
        "v": 1,
        "gid": int(gid),
        "slug": slug,
        "ev": (fields.get("event_name") or "Event")[:200],
        "sec": (fields.get("section") or "")[:64],
        "row": (fields.get("row") or "")[:64],
        "seat": (fields.get("seat") or "")[:64],
        "sub": (fields.get("subtitle") or "")[:300],
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    p = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sig = hmac.new(secret.encode("utf-8"), p.encode("ascii"), hashlib.sha256).hexdigest()
    q = urllib.parse.urlencode({"p": p, "s": sig})
    return f"{base}?{q}"


def _viewer_pkpass_url_allowed(href: str) -> bool:
    """
    ``tickets.txt`` often has ``Apple Wallet: https://app.ticketmaster.com/.../passes/...`` — opening that
    in a browser hits TM’s API without an ``apikey`` and shows JSON errors. We skip those unless
    ``TM_VIEWER_WALLET_ALLOW_TM_PKPASS=1`` (not recommended). Use ``TM_VIEWER_WALLET_PKPASS_*`` + Vercel signing instead.
    """
    raw = (href or "").strip()
    if not raw:
        return False
    if (os.environ.get("TM_VIEWER_WALLET_ALLOW_TM_PKPASS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return True
    try:
        pu = urllib.parse.urlparse(raw)
        host = (pu.netloc or "").lower()
        path = (pu.path or "").lower()
    except Exception:
        host = ""
        path = raw.lower()
    if "ticketmaster" in host or "livenation" in host:
        return False
    if "/tmx-prod/" in path and "/passes" in path:
        return False
    return True


def _hotp(key_bytes: bytes, counter: int, digits: int = 6) -> str:
    counter_bytes = struct.pack(">Q", counter)
    h = hmac.new(key_bytes, counter_bytes, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10**digits)).zfill(digits)


def _totp(key_hex: str, unix_time: int, period: int = TOTP_PERIOD, digits: int = TOTP_DIGITS) -> str:
    key_bytes = binascii.unhexlify(key_hex)
    counter = unix_time // period
    return _hotp(key_bytes, counter, digits)


def _safetix_barcode_payload(raw_token: str, ek: str, ck: str, unix_time: int) -> str:
    """Same string as tm-fcap-makefast/barcode.py generate_barcode_data / TM presence-secure-entry.js."""
    return f"{raw_token}::{_totp(ek, unix_time)}::{_totp(ck, unix_time)}::{unix_time}"


def verify_safetix_crypto_against_barcode_py(script_dir: Path) -> tuple[bool, str]:
    """Runtime check: this module’s payload must match barcode.py byte-for-byte."""
    bc_path = script_dir.parent / "tm-fcap-makefast" / "barcode.py"
    if not bc_path.is_file():
        return False, f"[!] barcode.py not found (expected): {bc_path}"
    spec = importlib.util.spec_from_file_location("_tm_fcap_barcode", bc_path)
    if spec is None or spec.loader is None:
        return False, "[!] could not load barcode.py"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    gen = getattr(mod, "generate_barcode_data", None)
    if not callable(gen):
        return False, "[!] barcode.py missing generate_barcode_data"
    raw_t = "selftest_raw_token"
    ek = "3639fb9684f28931ef9359d46ef6b34542bb6567"
    ck = "163cf08eae5f58366ecfecf842f37a8e6766173c"
    for now in (1700000000, 1735689600, int(time.time())):
        a = _safetix_barcode_payload(raw_t, ek, ck, now)
        b = gen(raw_t, ek, ck, now)
        if a != b:
            return (
                False,
                f"[!] mismatch unix={now}\n  viewer:  {a!r}\n  barcode: {b!r}",
            )
    return True, "[*] SafeTix string matches tm-fcap-makefast/barcode.py (generate_barcode_data)."


def _decode_secure_token_b64(token_b64: str) -> dict | None:
    try:
        raw = base64.b64decode(token_b64.strip()).decode("utf-8")
        d = json.loads(raw)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _redact_password_in_header(header: str, email: str, password: str) -> str:
    if not email or not password:
        return header
    needle = f"{email}:{password}"
    if needle in header:
        dots = "•" * min(len(password), 14)
        return header.replace(needle, f"{email}:{dots}", 1)
    return header


def _split_blocks(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"(?:^|\n)\s*-{3,}\s*(?:\n|$)", text)
    return [p.strip() for p in parts if p.strip()]


def _is_header_line(s: str) -> bool:
    s = s.strip()
    if "@" not in s or ":" not in s:
        return False
    head = s.split("|", 1)[0]
    return "@" in head and ":" in head


def _strip_event_arrow(s: str) -> str:
    return _ARROW_PREFIX.sub("", s).strip()


def _normalize_combo_to_email(combo: str) -> tuple[str, str]:
    """Map ``user:pass`` combo to (email_lower, normalized ``email:pass`` header line)."""
    c = (combo or "").strip().split("|", 1)[0].strip()
    if not c or ":" not in c:
        return "", ""
    user, _, pw = c.partition(":")
    user = user.strip()
    pw = (pw.strip() or "local")
    if not user:
        return "", ""
    if "@" in user:
        em = user.lower()
        return em, f"{user}:{pw}"
    em = f"{user.lower()}@seatgeek.local"
    return em, f"{em}:{pw}"


_COMPACT_TM_BATCH_MARKER = re.compile(r"Events:\s*\[", re.I)


def _text_looks_like_compact_tm_batch(text: str) -> bool:
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        head = s.split("|", 1)[0]
        if "@" in head and ":" in head and _COMPACT_TM_BATCH_MARKER.search(s):
            return True
    return False


def _compact_bracket_field(line: str, key: str) -> str:
    m = re.search(rf"{re.escape(key)}:\s*\[([^\]]*)\]", line, re.I)
    return m.group(1).strip() if m else ""


def _parse_compact_barcode_fields(chunk: str) -> dict[str, str]:
    out: dict[str, str] = {}
    chunk = (chunk or "").strip().lstrip("|").strip()
    if not chunk:
        return out
    key_re = (
        r"(?:event_id|event_name|purchase_id|section_label|row_label|"
        r"seat_type|seat_label|barcode|secure_token)\s*:"
    )
    parts = re.split(rf"(?={key_re})", chunk, flags=re.I)
    for part in parts:
        part = part.strip().lstrip("-").strip()
        if ":" not in part:
            continue
        k, _, v = part.partition(":")
        val = v.strip().rstrip("|").strip().rstrip("-").strip()
        out[k.strip().lower().replace(" ", "_")] = val
    return out


def _split_compact_barcodes_payload(payload: str) -> list[str]:
    payload = (payload or "").strip()
    if not payload or re.search(r"no\s+secure\s+token", payload, re.I):
        return []
    chunks = re.split(r"\s*\|\s*(?=event_id\s*:)", payload, flags=re.I)
    out: list[str] = []
    for c in chunks:
        c = c.strip().lstrip("|").strip().lstrip("[").strip()
        c = c.rstrip("|").strip().rstrip("]").strip()
        if c.lower().startswith("event_id"):
            out.append(c)
    return out


def _format_compact_event_date(iso: str) -> str:
    s = (iso or "").strip()
    if not s:
        return ""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})", s)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return s


def _compact_secure_token_rotating(st: str) -> bool:
    tok = _decode_secure_token_b64((st or "").strip())
    if not tok:
        return False
    raw_t = str(tok.get("t") or tok.get("rawToken") or "").strip()
    ek = str(tok.get("ek") or tok.get("eventKey") or "").strip()
    ck = str(tok.get("ck") or tok.get("customerKey") or "").strip()
    return bool(raw_t and ek and ck)


_SEAT_TYPE_NOT_TICKET_TYPE = frozenset(
    {
        "reserved",
        "ga",
        "general admission",
        "admission",
        "standard",
        "standard admission",
        "standard ticket",
        "mobile ticket",
    }
)


def _normalize_tm_pass_ticket_type(ttype: str) -> str:
    """Batch ``seat_type: RESERVED`` is not the gray line under Verified Ticket."""
    t = (ttype or "").strip()
    if not t or t.lower() in _SEAT_TYPE_NOT_TICKET_TYPE:
        return "Standard Admission"
    return t


def _default_tm_pass_gate(row: dict | None = None) -> str:
    """Black entry pill when checker/batch rows omit ``Gate:`` (override via env)."""
    if isinstance(row, dict):
        g = (row.get("gate") or "").strip()
        if g:
            return g
    env = (os.environ.get("TM_VIEWER_DEFAULT_PASS_GATE") or "").strip()
    if env:
        return env
    return "Main Concourse"


def _parse_compact_tm_batch_line(line: str) -> dict | None:
    """
    One-line TM batch export::

      email:pass | Events: [Show] | Dates: [iso] | Event id: [code] | … | BARCODES: event_id: … - secure_token: eyJ…
    """
    s = (line or "").strip()
    if not s or not _COMPACT_TM_BATCH_MARKER.search(s):
        return None
    combo_part = s.split("|", 1)[0].strip()
    if "@" not in combo_part or ":" not in combo_part:
        return None
    _email, norm_combo = _normalize_combo_to_email(combo_part)
    if not norm_combo:
        return None

    event_name = _compact_bracket_field(s, "Events")
    event_date = _format_compact_event_date(_compact_bracket_field(s, "Dates"))
    event_id = _compact_bracket_field(s, "Event id")
    venue = _compact_bracket_field(s, "Venues")
    try:
        ticket_count = int(_compact_bracket_field(s, "Tickets Counts") or "0")
    except ValueError:
        ticket_count = 0
    price_line = _compact_bracket_field(s, "Prices")

    bc_m = re.search(r"BARCODES:\s*(.*)$", s, re.I)
    bc_payload = bc_m.group(1).strip() if bc_m else ""

    barcode_rows: list[dict] = []
    for chunk in _split_compact_barcodes_payload(bc_payload):
        fields = _parse_compact_barcode_fields(chunk)
        st = (fields.get("secure_token") or "").strip()
        if len(st) < 24 or not _compact_secure_token_rotating(st):
            continue
        ev = (fields.get("event_name") or event_name or "Event").strip()[:140]
        sec = (fields.get("section_label") or "").strip()
        row = (fields.get("row_label") or "").strip()
        seat = (fields.get("seat_label") or "").strip()
        seat_bits: list[str] = []
        if sec:
            seat_bits.append(f"Sec {sec}")
        if row:
            seat_bits.append(f"Row {row}")
        if seat:
            seat_bits.append(f"Seat {seat}")
        seat_str = " · ".join(seat_bits)
        label = f"{ev} · {seat_str}" if seat_str else ev
        row_obj: dict = {
            "secure_token_b64": st,
            "label": label,
            "event_name": ev,
            "section": sec,
            "row": row,
            "seat": seat,
        }
        eid = (fields.get("event_id") or event_id or "").strip()
        if eid:
            row_obj["event_code"] = eid
        pid = (fields.get("purchase_id") or "").strip()
        if pid:
            row_obj["order_id"] = pid
        stype = (fields.get("seat_type") or "").strip()
        row_obj["ticket_type"] = _normalize_tm_pass_ticket_type(stype or "Standard Admission")
        if price_line:
            row_obj["price"] = price_line
        row_obj["gate"] = _default_tm_pass_gate(row_obj)
        barcode_rows.append(row_obj)

    upcoming: list[str] = []
    if event_name:
        upcoming.append(
            f"→ {event_name} | {ticket_count}x tickets | {event_date} | {venue} | Status: ONSALE"
        )

    return {
        "header": norm_combo,
        "upcoming": upcoming,
        "past": [],
        "cards": "",
        "cookies_lines": [],
        "secure_token_b64": "",
        "raw": s,
        "barcode_tokens": barcode_rows,
    }


def parse_compact_tm_batch(text: str) -> list[dict]:
    blocks: list[dict] = []
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        block = _parse_compact_tm_batch_line(s)
        if block:
            blocks.append(block)
    return blocks


def compact_tm_batch_text_has_tokens(text: str) -> bool:
    for block in parse_compact_tm_batch(text):
        if block.get("barcode_tokens"):
            return True
    return False


def _random_tm_transfer_url(event_id: str = "") -> str:
    """Synthetic listing URL so stock/group_tickets_for_stock has a link (remapped to tixx after generate)."""
    eid = re.sub(r"[^A-Za-z0-9]", "", (event_id or "").strip()) or secrets.token_hex(8).upper()
    blob = base64.urlsafe_b64encode(secrets.token_bytes(24)).decode("ascii").rstrip("=")
    return (
        f"https://www.ticketmaster.com/user/events/details/transfer/{eid}/"
        f"{blob}?f_app=true&client_platform=ios&language=en-US"
    )


_CHECKER_BLOCK_HDR = re.compile(r"^\s*===\s*(.+?)\s*===\s*$")


def ensure_checker_blocks_have_transfer_urls(text: str) -> str:
    """Add random TM transfer URLs to checker blocks that lack Transfer / Order / Ticket URL."""
    if not (text or "").strip() or "===" not in text:
        return text or ""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        m = _CHECKER_BLOCK_HDR.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        out.append(lines[i])
        i += 1
        body_lines: list[str] = []
        event_code = ""
        has_link = False
        while i < len(lines):
            if _CHECKER_BLOCK_HDR.match(lines[i]):
                break
            s = lines[i]
            ec_m = re.match(r"^\s*Event Code:\s*(\S+)", s, re.I)
            if ec_m:
                event_code = ec_m.group(1).strip()
            if re.match(r"^\s*Transfer URL:\s*https?", s, re.I):
                has_link = True
            elif re.match(r"^\s*(Order URL|Ticket URL):\s*https?", s, re.I):
                has_link = True
            body_lines.append(s)
            i += 1
        if body_lines and not has_link:
            insert_at = len(body_lines)
            for j, bl in enumerate(body_lines):
                if re.match(r"^\s*Secure Token:\s*", bl, re.I):
                    insert_at = j
                    break
            body_lines.insert(
                insert_at,
                f"  Transfer URL: {_random_tm_transfer_url(event_code)}",
            )
        out.extend(body_lines)
    return "\n".join(out)


def _compact_row_to_checker_block(combo: str, idx: int, row: dict) -> str:
    lines = [f"=== {combo} | Ticket {idx} ==="]
    if row.get("event_name"):
        lines.append(f"  Event: {row['event_name']}")
    if row.get("event_code"):
        lines.append(f"  Event Code: {row['event_code']}")
    bits: list[str] = []
    if row.get("section"):
        bits.append(f"Section: {row['section']}")
    if row.get("row"):
        bits.append(f"Row: {row['row']}")
    if row.get("seat"):
        bits.append(f"Seat: {row['seat']}")
    if bits:
        lines.append("  " + " | ".join(bits))
    lines.append(f"  Ticket Type: {_normalize_tm_pass_ticket_type(row.get('ticket_type') or '')}")
    if row.get("order_id"):
        lines.append(f"  Order: {row['order_id']}")
    if row.get("price"):
        lines.append(f"  Price: {row['price']}")
    lines.append(f"  Gate: {_default_tm_pass_gate(row)}")
    lines.append(f"  Transfer URL: {_random_tm_transfer_url(row.get('event_code') or '')}")
    lines.append(f"  Secure Token: {row['secure_token_b64']}")
    lines.append("")
    return "\n".join(lines)


def _compact_block_to_success_chunk(block: dict) -> str:
    lines = [block.get("header") or "", "Upcoming Events:"]
    lines.extend(block.get("upcoming") or [])
    return "\n".join(lines)


def expand_compact_tm_batch_inputs(tickets_text: str, success_text: str) -> tuple[str, str, bool]:
    """
    Expand one-line TM batch rows into Go-checker ``=== … | Ticket N ===`` blocks plus success chunks.
    Returns (tickets_text, success_text, did_expand).
    """
    t = tickets_text or ""
    s = success_text or ""
    if not _text_looks_like_compact_tm_batch(t) and not _text_looks_like_compact_tm_batch(s):
        return t, s, False

    seen_lines: set[str] = set()
    compact_lines: list[str] = []
    for src in (t, s):
        for ln in src.splitlines():
            key = ln.strip()
            if not key or key in seen_lines:
                continue
            if _parse_compact_tm_batch_line(key):
                seen_lines.add(key)
                compact_lines.append(key)

    if not compact_lines:
        return t, s, False

    ticket_parts: list[str] = []
    success_parts: list[str] = []
    for line in compact_lines:
        block = _parse_compact_tm_batch_line(line)
        if not block:
            continue
        combo = block.get("header") or ""
        rows = block.get("barcode_tokens") or []
        for i, row in enumerate(rows, 1):
            ticket_parts.append(_compact_row_to_checker_block(combo, i, row))
        success_parts.append(_compact_block_to_success_chunk(block))

    new_tickets = ensure_checker_blocks_have_transfer_urls("\n".join(ticket_parts))
    new_success = "\n---\n".join(success_parts)
    if not new_tickets.strip():
        return t, s, False
    return new_tickets, new_success, True


def parse_header_meta(header: str) -> dict:
    """Pull Name / phone / counts from the summary line (your export shape)."""
    h = (header or "").strip()
    if h and "@" not in h.split(":", 1)[0] and ":" in h.split("|", 1)[0]:
        _, h = _normalize_combo_to_email(h)
    meta: dict = {
        "email": "",
        "password": "",
        "name": "",
        "phone": "",
        "upcoming_n": None,
        "past_n": None,
    }
    if not h:
        return meta
    m = re.match(r"^([^|\s]+@[^|\s]+):([^\s|]+)", h)
    if m:
        meta["email"] = m.group(1).strip()
        meta["password"] = m.group(2).strip()
    nm = re.search(r"Name:\s*([^|]+?)(?=\s*\|)", h, re.I)
    if nm:
        meta["name"] = nm.group(1).strip()
    ph = re.search(r"\|\s*(\+\d[\d\s\-]{8,}?)\s*\|", h)
    if ph:
        meta["phone"] = re.sub(r"\s+", "", ph.group(1))
    um = re.search(r"Upcoming Events:\s*(\d+)", h, re.I)
    if um:
        meta["upcoming_n"] = int(um.group(1))
    pm = re.search(r"Past Events:\s*(\d+)", h, re.I)
    if pm:
        meta["past_n"] = int(pm.group(1))
    return meta


def parse_block(block: str) -> dict:
    """Parse one account block into structured fields (best-effort)."""
    lines = [ln.rstrip() for ln in block.split("\n")]
    d: dict = {
        "header": "",
        "upcoming": [],
        "past": [],
        "cards": "",
        "cookies_lines": [],
        "secure_token_b64": "",
        "raw": block.strip(),
    }
    mode: str | None = None

    for ln in lines:
        s = ln.strip()
        low = s.lower()

        if not s or s.startswith("#"):
            continue

        mst = re.match(r"^secure[_\s]?tokens?\s*:\s*(\S+)", s, re.I)
        if mst:
            d["secure_token_b64"] = mst.group(1).strip()
            continue

        if _is_header_line(s) and not d["header"]:
            d["header"] = s
            continue

        if low in ("upcoming events:", "upcoming events") or (
            low.startswith("upcoming events:") and len(s) < 40
        ):
            mode = "upcoming"
            continue
        if low in ("past events:", "past events") or (
            low.startswith("past events:") and len(s) < 40
        ):
            mode = "past"
            continue
        if re.match(r"^cards:\s*", s, re.I):
            mode = None
            d["cards"] = re.sub(r"^cards:\s*", "", s, flags=re.I).strip()
            continue
        if re.match(r"^cookies?:\s*", s, re.I):
            mode = "cookies"
            rest = re.sub(r"^cookies?:\s*", "", s, flags=re.I).strip()
            if rest:
                d["cookies_lines"].append(rest)
            continue

        if mode == "upcoming":
            if _ARROW_PREFIX.match(s) or "tickets" in low or "|" in s:
                d["upcoming"].append(_strip_event_arrow(s) if _ARROW_PREFIX.match(s) else s)
            continue
        if mode == "past":
            if _ARROW_PREFIX.match(s):
                d["past"].append(_strip_event_arrow(s))
            elif s:
                d["past"].append(s)
            continue
        if mode == "cookies":
            d["cookies_lines"].append(ln)
            continue

        if not d["header"] and _is_header_line(s):
            d["header"] = s

    if not d["header"] and lines:
        for cand in lines:
            if _is_header_line(cand):
                d["header"] = cand.strip()
                break

    if not d["header"]:
        for cand in lines:
            s = cand.strip()
            if not s or s.startswith("#"):
                continue
            low = s.lower()
            if low.startswith("upcoming") or low.startswith("past") or s.startswith("→"):
                break
            if ":" in s and "|" not in s and not re.match(r"^secure[_\s]?tokens?\s*:", s, re.I):
                _em, norm = _normalize_combo_to_email(s)
                if _em:
                    d["header"] = norm
                    break

    return d


def _load_verbose_checker_tickets(text: str) -> dict[str, list[dict]]:
    """
    Go checker multiline tickets.txt blocks:

      === email:pass | Ticket N ===
        Event: ...
        Secure Token: eyJ...
    """
    out: dict[str, list[dict]] = {}
    header_re = re.compile(r"^\s*===\s*(.+?)\s*===\s*$")
    i = 0
    lines = text.splitlines()
    while i < len(lines):
        m = header_re.match(lines[i])
        if not m:
            i += 1
            continue
        head = m.group(1).strip()
        combo = head.split("|", 1)[0].strip()
        email, _norm_combo = _normalize_combo_to_email(combo)
        if not email:
            i += 1
            continue
        i += 1
        ev, st = "", ""
        sec_v, row_v, seat_v = "", "", ""
        seat_bits: list[str] = []
        event_date_v, venue_v = "", ""
        ttype, gate_v, pkpass, order_url, poster_url, event_img_line, event_code = "", "", "", "", "", "", ""
        sg_otp, sg_barcode, sg_interval, sg_platform, sg_ticket_url, sg_event_id, sg_ticket_id = (
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        )
        sg_ticket_group_id, sg_pass_instance = "", ""
        while i < len(lines):
            raw = lines[i]
            if header_re.match(raw):
                break
            s = raw.strip()
            if s.startswith("---") and len(s) >= 3:
                i += 1
                break
            lm = re.match(r"^Event:\s*(.+)$", s, re.I)
            if lm:
                ev = lm.group(1).strip()[:140]
            edm = re.match(r"^Event Date:\s*(.+)$", s, re.I)
            if edm:
                event_date_v = edm.group(1).strip()[:120]
            vm = re.match(r"^Venue:\s*(.+)$", s, re.I)
            if vm:
                venue_v = vm.group(1).strip()[:120]
            if re.match(r"^Event Code:", s, re.I):
                for part in re.split(r"\s*\|\s*", s):
                    part = part.strip()
                    em = re.match(r"^Event Code:\s*(\S+)", part, re.I)
                    if em:
                        event_code = em.group(1).strip()[:32]
            for part in re.split(r"\s*\|\s*", s):
                part = part.strip()
                sm = re.match(r"^Section:\s*(.+)$", part, re.I)
                if sm:
                    v = sm.group(1).strip()
                    sec_v = v
                    seat_bits.append(f"Sec {v}")
                rm = re.match(r"^Row:\s*(.+)$", part, re.I)
                if rm:
                    v = rm.group(1).strip()
                    row_v = v
                    seat_bits.append(f"Row {v}")
                sem = re.match(r"^Seat:\s*(.+)$", part, re.I)
                if sem:
                    v = sem.group(1).strip()
                    seat_v = v
                    seat_bits.append(f"Seat {v}")
            ttm = re.match(r"^Ticket Type:\s*(.+)$", s, re.I)
            if ttm:
                ttype = ttm.group(1).strip()[:100]
            gm = re.match(r"^Gate:\s*(.+)$", s, re.I)
            if gm:
                gate_v = gm.group(1).strip()[:100]
            apm = re.match(r"^Apple Wallet:\s*(\S+)$", s, re.I)
            if apm:
                pkpass = apm.group(1).strip()[:500]
            oum = re.match(r"^Order URL:\s*(\S+)$", s, re.I)
            if oum:
                order_url = oum.group(1).strip()[:500]
            posm = re.match(r"^Poster:\s*(\S+)$", s, re.I)
            if posm:
                poster_url = posm.group(1).strip()[:500]
            eimgm = re.match(r"^Event Image:\s*(\S+)$", s, re.I)
            if eimgm:
                event_img_line = eimgm.group(1).strip()[:500]
            tm = re.match(r"^Secure Token:\s*(\S+)$", s, re.I)
            if tm:
                st = tm.group(1).strip()
            om = re.match(r"^OTP Secret:\s*(\S+)$", s, re.I)
            if om:
                sg_otp = om.group(1).strip()
            bm = re.match(r"^Barcode Value:\s*(\S+)$", s, re.I)
            if bm:
                sg_barcode = bm.group(1).strip()
            im = re.match(r"^Interval:\s*(\d+)$", s, re.I)
            if im:
                sg_interval = im.group(1).strip()
            pm = re.match(r"^Platform:\s*(\S+)$", s, re.I)
            if pm:
                sg_platform = pm.group(1).strip()
            tum = re.match(r"^Ticket URL:\s*(\S+)$", s, re.I)
            if tum:
                sg_ticket_url = tum.group(1).strip()[:500]
            eidm = re.match(r"^Event ID:\s*(\S+)$", s, re.I)
            if eidm:
                sg_event_id = eidm.group(1).strip()[:32]
            tidm = re.match(r"^Ticket ID:\s*(\S+)$", s, re.I)
            if tidm:
                sg_ticket_id = tidm.group(1).strip()[:80]
            tgidm = re.match(r"^Ticket Group ID:\s*(\S+)$", s, re.I)
            if tgidm:
                sg_ticket_group_id = tgidm.group(1).strip()[:80]
            pim = re.match(r"^Pass Instance:\s*(\S+)$", s, re.I)
            if pim:
                sg_pass_instance = pim.group(1).strip()[:80]
            i += 1
        sg_ok = sg_platform.upper() == "SG" and len(sg_otp) >= 8 and len(sg_barcode) >= 8
        if sg_ok:
            seat = " · ".join(seat_bits)[:120]
            label = f"{ev} · {seat}" if seat else (ev or "Ticket")
            row_obj = {
                "sg_barcode": True,
                "barcode_value": sg_barcode,
                "otp_secret": sg_otp,
                "interval": int(sg_interval or 30),
                "label": label,
            }
            if ev:
                row_obj["event_name"] = ev
            if sec_v:
                row_obj["section"] = sec_v
            if row_v:
                row_obj["row"] = row_v
            if seat_v:
                row_obj["seat"] = seat_v
            if ttype:
                row_obj["ticket_type"] = ttype
            if sg_ticket_url:
                row_obj["ticket_url"] = sg_ticket_url
                row_obj["order_url"] = sg_ticket_url
            if sg_event_id:
                row_obj["event_id"] = sg_event_id
            if sg_ticket_id:
                row_obj["ticket_id"] = sg_ticket_id
            if sg_ticket_group_id:
                row_obj["ticket_group_id"] = sg_ticket_group_id
            if sg_pass_instance:
                row_obj["pass_instance"] = sg_pass_instance
            if event_date_v:
                row_obj["event_date"] = event_date_v
            if venue_v:
                row_obj["venue"] = venue_v
            hero_u = (poster_url or event_img_line or "").strip()
            if hero_u:
                row_obj["image_url"] = hero_u
                if hero_u.startswith("http://") or hero_u.startswith("https://"):
                    row_obj["image_url_remote"] = hero_u
            out.setdefault(email, []).append(row_obj)
        elif len(st) >= 24:
            seat = " · ".join(seat_bits)[:120]
            label = f"{ev} · {seat}" if seat else (ev or "Ticket")
            row_obj: dict = {"secure_token_b64": st, "label": label}
            if ev:
                row_obj["event_name"] = ev
            if sec_v:
                row_obj["section"] = sec_v
            if row_v:
                row_obj["row"] = row_v
            if seat_v:
                row_obj["seat"] = seat_v
            if ttype:
                row_obj["ticket_type"] = ttype
            if gate_v:
                row_obj["gate"] = gate_v
            if pkpass:
                row_obj["pkpass_url"] = pkpass
            if order_url:
                row_obj["order_url"] = order_url
            hero_u = (poster_url or event_img_line or "").strip()
            if hero_u:
                row_obj["image_url"] = hero_u
            if event_code:
                row_obj["event_code"] = event_code
            out.setdefault(email, []).append(row_obj)
        continue
    return out


def parse_tickets_text(text: str) -> dict[str, list[dict]]:
    """
    Checker / recovery ticket text:
      • Upcoming/pm/hits compact: email:pass | Events: [...] | ... | BARCODES: event_id: … - secure_token: …
      • Pipe rows: email:pass | event | section/row/seat | type | transfer | barcode | secure_token | ...
      • Or Go checker blocks: === email:pass | Ticket N === … Secure Token: …
    Returns email(lower) -> [{secure_token_b64, label}, ...].
    """
    out: dict[str, list[dict]] = {}
    seen: set[str] = set()

    def add_row(email: str, row: dict) -> None:
        tok = (row.get("secure_token_b64") or "").strip()
        if row.get("sg_barcode"):
            otp = (row.get("otp_secret") or "").strip()
            val = (row.get("barcode_value") or "").strip()
            if not (otp and val):
                return
            key = f"{email}|sg|{val}|{otp}"
        elif tok:
            key = f"{email}|{tok}"
        else:
            return
        if key in seen:
            return
        seen.add(key)
        out.setdefault(email, []).append(row)

    if _text_looks_like_compact_tm_batch(text):
        for block in parse_compact_tm_batch(text):
            header = block.get("header") or ""
            em = (parse_header_meta(header).get("email") or "").strip().lower()
            if not em and "@" in header:
                em = header.split(":", 1)[0].strip().lower()
            if not em:
                continue
            for row in block.get("barcode_tokens") or []:
                add_row(em, row)

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 7:
            continue
        combo = parts[0]
        if "@" not in combo or ":" not in combo:
            continue
        email = combo.split(":", 1)[0].strip().lower()
        st = parts[6].strip()
        if len(st) < 24:
            continue
        ev = (parts[1] or "Event").strip()[:140]
        seat = (parts[2] or "").strip()[:100]
        label = f"{ev} · {seat}" if seat else ev
        row_obj: dict = {"secure_token_b64": st, "label": label, "event_name": ev}
        sp = [x.strip() for x in seat.split("/") if x.strip()]
        if len(sp) >= 1:
            row_obj["section"] = sp[0]
        if len(sp) >= 2:
            row_obj["row"] = sp[1]
        if len(sp) >= 3:
            row_obj["seat"] = sp[2]
        if len(parts) > 3 and (parts[3] or "").strip():
            row_obj["ticket_type"] = (parts[3] or "").strip()[:100]
        if len(parts) > 9:
            iu = (parts[9] or "").strip()
            if iu.startswith("http://") or iu.startswith("https://"):
                row_obj["image_url"] = iu[:500]
        add_row(email, row_obj)

    for email, rows in _load_verbose_checker_tickets(text).items():
        for row in rows:
            add_row(email, row)
    return out


def load_tickets_by_email(path: Path) -> dict[str, list[dict]]:
    if not path.is_file():
        return {}
    try:
        from secure_pass_stock_ops import _read_barcode_source_text
        raw = _read_barcode_source_text(path)
    except ImportError:
        raw = path.read_text(encoding="utf-8", errors="replace")
    return parse_tickets_text(raw)


def resolve_barcode_ticket_source_paths(arg: str, stubby_dir: Path) -> list[Path]:
    """
    Resolve --tickets PATH:
      auto  -> all upcoming/pm/hits/… dumps under tm.bz/Data_for_recovery
      DIR   -> same scan inside that folder
      FILE  -> single file (upcoming (4).txt, tickets.txt, found_hits, …)
    """
    raw = (arg or "").strip()
    if not raw:
        return []
    if raw.lower() == "auto":
        try:
            from secure_pass_stock_ops import find_recovery_barcode_files, resolve_recovery_root
        except ImportError:
            print("[!] secure_pass_stock_ops missing — cannot use --tickets auto", file=sys.stderr)
            return []
        site_dir = stubby_dir
        data_dir = stubby_dir.parent if stubby_dir.parent != stubby_dir else stubby_dir
        recovery_root = resolve_recovery_root(site_dir, data_dir)
        paths = find_recovery_barcode_files(recovery_root)
        if recovery_root and paths:
            print(
                f"[*] --tickets auto: {len(paths)} source file(s) under {recovery_root}",
                flush=True,
            )
        elif not recovery_root:
            print(
                "[!] --tickets auto: Data_for_recovery not found (set STUBBY_RECOVERY_ROOT)",
                file=sys.stderr,
            )
        return paths
    p = Path(raw).expanduser()
    if p.is_dir():
        try:
            from secure_pass_stock_ops import find_recovery_barcode_files
            return find_recovery_barcode_files(p)
        except ImportError:
            return sorted(x for x in p.rglob("*") if x.is_file() and x.suffix.lower() == ".txt")
    if p.is_file():
        return [p]
    print(f"[!] --tickets path not found: {p}", file=sys.stderr)
    return []


def load_tickets_maps_from_sources(paths: list[Path]) -> dict[str, list[dict]]:
    maps: list[dict[str, list[dict]]] = []
    for p in paths:
        tmap = load_tickets_by_email(p)
        if tmap:
            maps.append(tmap)
            print(f"[*] Loaded {sum(len(v) for v in tmap.values())} token row(s) from {p.name}", flush=True)
    return merge_tickets_maps(*maps) if maps else {}


def merge_tickets_maps(*maps: dict[str, list[dict]]) -> dict[str, list[dict]]:
    seen: set[str] = set()
    out: dict[str, list[dict]] = {}
    for m in maps:
        for email, rows in m.items():
            el = email.strip().lower()
            for row in rows:
                if row.get("sg_barcode"):
                    otp = (row.get("otp_secret") or "").strip()
                    val = (row.get("barcode_value") or "").strip()
                    if not (otp and val):
                        continue
                    key = f"{el}|sg|{val}|{otp}"
                else:
                    tok = (row.get("secure_token_b64") or "").strip()
                    if len(tok) < 24:
                        continue
                    key = f"{el}|{tok}"
                if key in seen:
                    continue
                seen.add(key)
                out.setdefault(el, []).append(row)
    return out


def load_embedded_tickets_map() -> dict[str, list[dict]]:
    b64 = (_EMBEDDED_TICKETS_ZB64 or "").strip().replace("\n", "").replace(" ", "")
    if not b64:
        return {}
    raw = zlib.decompress(base64.b64decode(b64)).decode("utf-8")
    return parse_tickets_text(raw)


def merge_tickets_into_blocks(blocks: list[dict], tickets_map: dict[str, list[dict]]) -> None:
    """Attach barcode_tokens to each block when header email matches tickets.txt rows."""
    for b in blocks:
        h = b.get("header") or ""
        em = (parse_header_meta(h).get("email") or "").strip().lower()
        if not em:
            continue
        rows = tickets_map.get(em)
        if rows:
            b["barcode_tokens"] = list(rows)
            _reorder_barcode_tokens_by_upcoming(b)
            _reorder_barcode_tokens_by_upcoming_event(b)
            _sort_barcode_tokens_by_seat_locator(b)


def _upcoming_line_matches_seat(line: str, sec: str, rowv: str, seat: str) -> bool:
    """True if an upcoming-events line mentions this section, row, and seat (checker / TM phrasing)."""
    s = _strip_event_arrow(line)
    low = s.lower()
    compact = re.sub(r"[\s_\-]+", "", low)

    def hit_text(val: str) -> bool:
        v = (val or "").strip()
        if not v:
            return True
        vl = v.lower()
        if len(vl) >= 1 and vl in compact:
            return True
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(vl) + r"(?![a-z0-9])", low, re.I))

    def hit_seat(val: str) -> bool:
        v = (val or "").strip()
        if not v:
            return True
        if v.isdigit():
            return bool(re.search(r"(^|[^0-9])" + re.escape(v) + r"($|[^0-9])", low))
        return hit_text(v)

    return hit_text(sec) and hit_text(rowv) and hit_seat(seat)


def _reorder_barcode_tokens_by_upcoming(block: dict) -> None:
    """Align barcode_tokens order to success.txt upcoming lines so each seat gets the matching Secure Token."""
    rows = block.get("barcode_tokens") or []
    upcoming = block.get("upcoming") or []
    if len(rows) <= 1 or not upcoming:
        return
    idxs: list[int] = []
    for r in rows:
        sec = (r.get("section") or "").strip()
        rowv = (r.get("row") or "").strip()
        seat = (r.get("seat") or "").strip()
        if not (sec or rowv or seat):
            return
        found: int | None = None
        for i, line in enumerate(upcoming):
            if _upcoming_line_matches_seat(line, sec, rowv, seat):
                found = i
                break
        if found is None:
            return
        idxs.append(found)
    if len(set(idxs)) != len(idxs):
        return
    order = sorted(range(len(rows)), key=lambda j: idxs[j])
    block["barcode_tokens"] = [rows[j] for j in order]


def _reorder_barcode_tokens_by_upcoming_event(block: dict) -> None:
    """When each ticket row matches a different upcoming line by event title, align order to that list."""
    rows = block.get("barcode_tokens") or []
    upcoming = block.get("upcoming") or []
    if len(rows) <= 1 or not upcoming:
        return
    ar_lines = [_strip_event_arrow(x) for x in upcoming]
    idxs: list[int] = []
    for r in rows:
        ev = (r.get("event_name") or "").strip()
        if not ev:
            pe, _, _, _ = _parse_label_seat((r.get("label") or "").strip())
            ev = pe
        if not ev:
            return
        found: int | None = None
        for i, line in enumerate(ar_lines):
            if _match_upcoming_subtitle(ev, [line]):
                found = i
                break
        if found is None:
            return
        idxs.append(found)
    if len(set(idxs)) != len(idxs):
        return
    order = sorted(range(len(rows)), key=lambda j: idxs[j])
    block["barcode_tokens"] = [rows[j] for j in order]


def _sort_barcode_tokens_by_seat_locator(block: dict) -> None:
    """Stable TM-like order: event name, section, row, then seat (numeric seats sort numerically)."""
    rows = block.get("barcode_tokens") or []
    if len(rows) <= 1:
        return

    def seat_key(r: dict) -> tuple:
        ev = (r.get("event_name") or r.get("label") or "").lower()
        sec = (r.get("section") or "").lower()
        rowv = (r.get("row") or "").lower()
        seat = (r.get("seat") or "").strip().lower()
        if seat.isdigit():
            st = (0, int(seat))
        else:
            st = (1, seat)
        return (ev, sec, rowv, st)

    block["barcode_tokens"] = sorted(rows, key=seat_key)


def _load_tm_viewer_safetix_slug_overrides() -> dict[str, dict]:
    raw = (os.environ.get("TM_VIEWER_SAFETIX_SLUG_OVERRIDES") or "").strip()
    path_s = (os.environ.get("TM_VIEWER_SAFETIX_SLUG_OVERRIDES_FILE") or "").strip()
    if path_s:
        try:
            raw = Path(path_s).expanduser().read_text(encoding="utf-8", errors="replace")
        except OSError:
            if not raw:
                return {}
    if not raw:
        return {}
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(d, dict):
        return {}
    out: dict[str, dict] = {}
    for k, v in d.items():
        slug = str(k).strip()
        if slug.lower().endswith(".html"):
            slug = slug[:-5]
        if slug and isinstance(v, dict):
            out[slug] = v
    return out


def _make_safetix_cfg_b64(raw_t: str, ek: str, ck: str) -> str | None:
    raw_t, ek, ck = raw_t.strip(), ek.strip(), ck.strip()
    if not (raw_t and ek and ck):
        return None
    cfg_obj = {
        "t": raw_t,
        "ek": ek,
        "ck": ck,
        "period": TOTP_PERIOD,
        "digits": TOTP_DIGITS,
    }
    _merge_safetix_clock_cfg(cfg_obj)
    return base64.b64encode(
        json.dumps(cfg_obj, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")


def _safetix_override_cfg_b64_for_slug(overrides: dict[str, dict], slug: str) -> str | None:
    ov = overrides.get((slug or "").strip())
    if not ov:
        return None
    raw_t = str(ov.get("t") or ov.get("rawToken") or "").strip()
    ek = str(ov.get("ek") or ov.get("eventKey") or "").strip()
    ck = str(ov.get("ck") or ov.get("customerKey") or "").strip()
    return _make_safetix_cfg_b64(raw_t, ek, ck)


# ── TM app API (events.json + securetickets) — mirrors tm-fcap-makefast/checker/pkg/tmauth/postlogin.go ──

TM_API_KEY = "5ogzsQ5NWkosR2lQyD2271yQ7R1XQ3Da"
# Discovery `GET /discovery/v2/events.json` (hero images). Defaults to app consumer key — change here only.
TM_DISCOVERY_CONSUMER_KEY = TM_API_KEY
TM_APP_BASE = "https://app.ticketmaster.com"
TM_AUTH_SDK_UA = (
    "com.ticketmaster.ios.TicketmasterApp/272.2 (iPhone; iOS 18.2; Scale/2.00; AuthSDK 3.16.0)"
)
TM_PSDK_UA = "com.ticketmaster.ios.TicketmasterApp/272.2 (iPhone; iOS 18.2; Scale/2.00; PSDK 3.16.0)"
TM_CFNETWORK_UA = "Ticketmaster/1 CFNetwork/3860.400.51 Darwin/25.3.0"
TMX_CLIENT_SDK = "iOS v3.16.0"

# --fetch-barcodes uses this if --proxy and TM_HIT_VIEWER_PROXY are empty. Use --no-proxy to skip.
_DEFAULT_FETCH_PROXY_SPEC = "unlim.flashproxy.io:12000:USERhUAfJA-zone-custom:aSvKuH"


def _row_event_name_for_media(row: dict) -> str:
    n = (row.get("event_name") or "").strip()
    if n:
        return n
    label = (row.get("label") or "").strip()
    if " · " in label:
        return label.split(" · ", 1)[0].strip()
    return label


def _event_media_cache_key(row: dict) -> str:
    c = (row.get("event_code") or "").strip().upper()
    if c and re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{2,31}", c):
        return c
    name = _row_event_name_for_media(row)
    slug = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE)[:56]
    slug = re.sub(r"[\s_]+", "-", slug.strip()).lower().strip("-") or "event"
    # Same slug prefix could be different shows/seats — avoid one tm_event_assets file clobbering another.
    label = (row.get("label") or "").strip()
    st = (row.get("secure_token_b64") or "").strip()[:80]
    h8 = hashlib.sha256(f"{label}|{name}|{st}".encode("utf-8")).hexdigest()[:8]
    return f"n:{slug}-{h8}"


def _default_event_media_cache_path() -> Path:
    """Always ``<this_dir>/results/tm_event_media.json`` (no env)."""
    return Path(__file__).resolve().parent / "results" / "tm_event_media.json"


def _discovery_consumer_key() -> str:
    return (
        (os.environ.get("TM_DISCOVERY_CONSUMER_KEY") or "").strip()
        or (TM_DISCOVERY_CONSUMER_KEY or "").strip()
        or (TM_API_KEY or "").strip()
    )


def _discovery_best_image_url(images: object) -> str | None:
    if not isinstance(images, list):
        return None
    best_u, best_w = "", -1
    for im in images:
        if not isinstance(im, dict):
            continue
        u = (im.get("url") or "").strip()
        if not (u.startswith("http://") or u.startswith("https://")):
            continue
        try:
            w = int(im.get("width") or 0)
        except (TypeError, ValueError):
            w = 0
        if w >= best_w:
            best_w = w
            best_u = u
    return best_u or None


def fetch_event_image_discovery(keyword: str, *, api_key: str, timeout: float = 28.0) -> str | None:
    """First matching Discovery event with an image (US search)."""
    kw = (keyword or "").strip()[:160]
    if not kw or not api_key:
        return None
    params = urllib.parse.urlencode(
        {
            "apikey": api_key,
            "keyword": kw,
            "size": "8",
            "countryCode": "US",
            "locale": "*",
        }
    )
    url = f"{TM_APP_BASE}/discovery/v2/events.json?{params}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "tm-hit-viewer/1.2 (event media cache)", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            print(
                f"[!] Discovery API HTTP {e.code} — set env TM_DISCOVERY_CONSUMER_KEY to your "
                f"**Discovery API** consumer key from https://developer.ticketmaster.com/ "
                f"(the built-in TM_API_KEY is often not valid for /discovery/v2/).",
                file=sys.stderr,
            )
        else:
            print(f"[!] Discovery API HTTP {e.code} for keyword={kw[:48]!r}", file=sys.stderr)
        return None
    except urllib.error.URLError as e:
        print(f"[!] Discovery network error ({keyword[:40]!r}): {e.reason!r}", file=sys.stderr)
        return None
    except (json.JSONDecodeError, TimeoutError, OSError) as e:
        print(f"[!] Discovery error ({keyword[:40]!r}): {e}", file=sys.stderr)
        return None
    if not isinstance(data, dict):
        return None
    emb = data.get("_embedded") or {}
    events = emb.get("events") if isinstance(emb, dict) else None
    if not isinstance(events, list):
        return None
    for ev in events:
        if not isinstance(ev, dict):
            continue
        u = _discovery_best_image_url(ev.get("images"))
        if u:
            return u
    return None


def _download_url_to_file(url: str, dest: Path, timeout: float = 35.0) -> None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "tm-hit-viewer/1.2"},
        method="GET",
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        dest.write_bytes(resp.read())


def _load_event_media_cache(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return {}
    return raw if isinstance(raw, dict) else {}


def enrich_event_media_for_blocks(
    blocks: list[dict],
    *,
    html_out: Path,
    cache_path: Path,
    resolve_discovery: bool,
    download_local: bool,
) -> None:
    """
    Fill ticket row image_url from tm_event_media.json, optional Discovery API,
    and optionally download files to tm_event_assets/ with relative paths in HTML.
    """
    _tm_viewer_debug_log(
        f"enrich START base_dir={html_out.parent} cache={cache_path} "
        f"resolve_discovery={resolve_discovery} download_local={download_local}"
    )
    cache = _load_event_media_cache(cache_path)
    changed = False
    # One debug line per event key when poster art is missing (avoids 10× same Gerry Dee, etc.)
    _empty_art_logged_keys: set[str] = set()
    _discovery_miss_events: set[str] = set()
    _discovery_hit_by_event: dict[str, str] = {}
    api_key = _discovery_consumer_key()
    if resolve_discovery and not api_key:
        print(
            "[!] --resolve-event-images: no Discovery API key (set env TM_DISCOVERY_CONSUMER_KEY).",
            file=sys.stderr,
        )
    base_dir = html_out.parent
    assets_dir = base_dir / "tm_event_assets"

    def rel_to_html(p: Path) -> str:
        try:
            return p.relative_to(base_dir).as_posix()
        except ValueError:
            return p.name

    for block in blocks:
        for row in block.get("barcode_tokens") or []:
            key = _event_media_cache_key(row)
            entry = cache.get(key) if isinstance(cache.get(key), dict) else {}

            if not (row.get("image_url") or "").strip():
                loc = (entry.get("local_relpath") or "").strip().replace("\\", "/")
                if loc and (base_dir / loc).is_file():
                    row["image_url"] = loc
                    u = (entry.get("image_url") or "").strip()
                    if u.startswith("http://") or u.startswith("https://"):
                        row["image_url_remote"] = u
                else:
                    u = (entry.get("image_url") or "").strip()
                    if u.startswith("http://") or u.startswith("https://"):
                        row["image_url"] = u
            elif not (row.get("image_url_remote") or "").strip():
                iu0 = (row.get("image_url") or "").strip()
                if iu0.startswith("http://") or iu0.startswith("https://"):
                    row["image_url_remote"] = iu0
                else:
                    u = (entry.get("image_url") or "").strip()
                    if u.startswith("http://") or u.startswith("https://"):
                        row["image_url_remote"] = u

            if (
                not (row.get("image_url") or "").strip()
                and resolve_discovery
                and api_key
            ):
                name = _row_event_name_for_media(row)
                if not name or name == "Event":
                    continue
                ev_key = name.strip().lower()
                if ev_key in _discovery_miss_events:
                    continue
                if ev_key in _discovery_hit_by_event:
                    row["image_url"] = _discovery_hit_by_event[ev_key]
                    changed = True
                    continue
                print(f"[*] Discovery image lookup: {name[:72]}", file=sys.stderr)
                img = fetch_event_image_discovery(name, api_key=api_key)
                code = (row.get("event_code") or "").strip()
                if not img and code:
                    img = fetch_event_image_discovery(code, api_key=api_key)
                if img:
                    row["image_url"] = img
                    _discovery_hit_by_event[ev_key] = img
                    cache[key] = {
                        "event_name": name,
                        "event_code": code,
                        "image_url": img,
                        "updated_unix": int(time.time()),
                    }
                    changed = True
                else:
                    _discovery_miss_events.add(ev_key)
                    print(f"[!] No Discovery image for event={name[:72]!r}", file=sys.stderr)

            if download_local and row.get("image_url"):
                iu = row["image_url"].strip()
                if not (iu.startswith("http://") or iu.startswith("https://")):
                    continue
                safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", key)[:72].strip("_") or "poster"
                dest = assets_dir / f"{safe}.jpg"
                try:
                    if not dest.is_file():
                        _download_url_to_file(iu, dest)
                    rel = rel_to_html(dest)
                    row["image_url"] = rel
                    row["image_url_remote"] = iu
                    ent = cache.setdefault(key, {})
                    if isinstance(ent, dict):
                        ent["image_url"] = iu
                        ent["local_relpath"] = rel
                        ent["event_name"] = _row_event_name_for_media(row)
                        ent["event_code"] = (row.get("event_code") or "").strip()
                        ent["updated_unix"] = int(time.time())
                    changed = True
                except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as e:
                    print(f"[!] Download failed key={key!r} url={iu[:160]!r}: {e}", file=sys.stderr)
                    _tm_viewer_debug_log(f"enrich DOWNLOAD_FAIL key={key!r} url={iu[:200]!r} err={e!r}")

            fin = (row.get("image_url") or "").strip()
            abp, okf = ("", False)
            if fin:
                abp, okf = _tm_viewer_debug_resolve_asset(base_dir, fin)
                _tm_viewer_debug_log(
                    f"enrich ROW key={key!r} event={_row_event_name_for_media(row)[:70]!r} "
                    f"image_url={fin!r} resolved_local={abp!r} file_exists={okf}"
                )
            elif key not in _empty_art_logged_keys:
                _empty_art_logged_keys.add(key)
                evn = _row_event_name_for_media(row)[:70]
                _tm_viewer_debug_log(
                    f"enrich ROW key={key!r} event={evn!r} — no event poster (image_url empty). "
                    f"NOT an error: pass HTML, barcodes, and registry links still build; hero banner uses gradient. "
                    f"Optional art: set TM_DISCOVERY_CONSUMER_KEY and use --resolve-event-images, or add entries to "
                    f"{cache_path.name}."
                )

    if changed:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"[*] Updated event media cache: {cache_path}")


def _strip_cookie_domain_prefix(s: str) -> str:
    s = (s or "").strip()
    while s.startswith("["):
        m = re.match(r"^\[[^\]]+\]\s*", s)
        if not m:
            break
        s = s[m.end() :].strip()
    return s


def _cookie_jar_from_lines(lines: list[str]) -> dict[str, str]:
    """Flatten [host] cookie lines into name -> value (last wins)."""
    jar: dict[str, str] = {}
    for ln in lines:
        s = _strip_cookie_domain_prefix(ln.strip())
        if not s:
            continue
        for part in s.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            k, _, v = part.partition("=")
            k, v = k.strip(), v.strip()
            if k.startswith("."):
                k = k[1:]
            if k:
                jar[k] = v
    return jar


def _jar_get_ci(jar: dict[str, str], name: str) -> str:
    want = name.lower()
    for k, v in jar.items():
        if k.lower() == want:
            return v
    return ""


def _extract_cookie_value_from_text(text: str, cookie_name: str) -> str:
    """If cookies are embedded oddly (one long line / JSON), pull name=value."""
    if not text:
        return ""
    # id-token value is a JWT; stop before ; or whitespace (unquoted)
    pat = re.compile(
        rf"(?i)(?:^|[\s;])\.?{re.escape(cookie_name)}=([^;\s]+)",
    )
    m = pat.search(text)
    return m.group(1).strip() if m else ""


def _cookie_header_from_jar(jar: dict[str, str], max_len: int = 16384) -> str:
    """Rebuild Cookie header for app.ticketmaster.com calls (checker uses a full jar)."""
    parts = [f"{k}={v}" for k, v in jar.items() if v is not None and k]
    s = "; ".join(parts)
    if len(s) > max_len:
        s = s[:max_len].rsplit(";", 1)[0]
    return s


def _jwt_payload_unverified(token: str) -> dict | None:
    parts = (token or "").strip().split(".")
    if len(parts) < 2:
        return None
    payload = parts[1]
    pad = (-len(payload)) % 4
    if pad:
        payload += "=" * pad
    try:
        raw = base64.urlsafe_b64decode(payload)
        d = json.loads(raw.decode("utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


_JWT_JWS_RE = re.compile(
    r"\b(eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b"
)


def _find_tm_web_id_jwt(jar: dict[str, str], blob: str) -> str:
    """Pick a 3-segment JWS in cookies whose payload looks like TM auth id-token."""
    seen: set[str] = set()
    for src in (blob, *[v for v in jar.values() if isinstance(v, str)]):
        for m in _JWT_JWS_RE.finditer(src):
            j = m.group(1)
            if j in seen:
                continue
            seen.add(j)
            pl = _jwt_payload_unverified(j)
            if not pl:
                continue
            iss = str(pl.get("iss") or "")
            if iss.startswith("https://auth.ticketmaster.com") or pl.get("hmac_user_id") or (
                pl.get("email") and pl.get("sub")
            ):
                return j
    return ""


def normalize_proxy_url(spec: str) -> str | None:
    """
    For --fetch-barcodes HTTP(S) calls. Accepts:
      http://user:pass@host:port  or  https://...
      host:port:user:pass         (residential proxy style)
      host:port
    """
    s = (spec or "").strip()
    if not s:
        return None
    if "://" in s:
        return s
    parts = s.split(":")
    if len(parts) == 2 and parts[1].isdigit():
        return f"http://{parts[0]}:{parts[1]}"
    if len(parts) >= 4:
        host, port, user = parts[0], parts[1], parts[2]
        password = ":".join(parts[3:])
        u = urllib.parse.quote(user, safe="")
        p = urllib.parse.quote(password, safe="")
        return f"http://{u}:{p}@{host}:{port}"
    return None


def _http_get(
    url: str,
    headers: dict[str, str],
    timeout: float = 45.0,
    *,
    proxy_url: str | None = None,
) -> tuple[int, bytes]:
    """GET; prefers curl_cffi (TLS fingerprint) if installed, else urllib."""
    h = {k: v for k, v in headers.items() if v is not None and v != ""}
    curl_kw: dict = {"url": url, "headers": h, "timeout": timeout, "impersonate": "safari_ios"}
    if proxy_url:
        curl_kw["proxies"] = {"http": proxy_url, "https": proxy_url}
    try:
        from curl_cffi import requests as curl_requests

        r = curl_requests.get(**curl_kw)
        return int(r.status_code), r.content
    except ImportError:
        pass
    except Exception:
        pass

    req = urllib.request.Request(url, headers=h, method="GET")
    try:
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    try:
        https_h = urllib.request.HTTPSHandler(context=ctx)
        if proxy_url:
            proxy_h = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
            opener = urllib.request.build_opener(proxy_h, https_h)
        else:
            opener = urllib.request.build_opener(https_h)
        with opener.open(req, timeout=timeout) as resp:
            data = resp.read()
            enc = (resp.headers.get("Content-Encoding") or "").lower()
            if enc == "gzip":
                try:
                    data = gzip.decompress(data)
                except Exception:
                    pass
            elif enc == "br":
                try:
                    import brotli

                    data = brotli.decompress(data)
                except Exception:
                    pass
            return resp.status, data
    except urllib.error.HTTPError as e:
        data = e.read()
        enc = (e.headers.get("Content-Encoding") or "").lower() if e.headers else ""
        if enc == "gzip":
            try:
                data = gzip.decompress(data)
            except Exception:
                pass
        return e.code, data
    except Exception as e:
        return -1, str(e).encode("utf-8", errors="replace")


def merge_cookie_file_into_blocks(blocks: list[dict], path: Path) -> None:
    """
    Merge cookies from file into every block: either one semicolon string (tm_auth_cookie_string.txt)
    or multi-line export with [host] prefixes (cookies_testing-style).
    """
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return
    if "\n" in raw and "[" in raw:
        add: list[str] = []
        for ln in raw.splitlines():
            s = ln.strip()
            if not s or s.startswith("#"):
                continue
            if re.match(r"^\[", s):
                add.append(f"  {s}")
            else:
                add.append(f"  [.ticketmaster.com] {s}")
        for b in blocks:
            b.setdefault("cookies_lines", []).extend(add)
        return
    one = re.sub(r"\s+", " ", raw.replace("\n", "; ").strip().rstrip(";"))
    if not one:
        return
    line = f"  [.ticketmaster.com] {one}"
    if not line.endswith(";"):
        line += ";"
    for b in blocks:
        b.setdefault("cookies_lines", []).append(line)


def _tm_account_details(
    access_token_host: str,
    device_id: str,
    cookie_header: str = "",
    *,
    proxy_url: str | None = None,
) -> tuple[dict | None, int, str]:
    headers = {
        "content-type": "application/json; charset=utf-8",
        "accept": "application/vnd.amgr.v1.2+json",
        "preferred-languages": "[en]",
        "call-source": "TMGlobalApp.LoginManager.getUserManagerReadyOnInitialTry",
        "priority": "u=3",
        "accept-language": "en-US",
        "x-api-key": TM_API_KEY,
        "accept-encoding": "gzip",
        "data-type": "json",
        "user-agent": TM_AUTH_SDK_UA,
        "x-tmx-client-sdk": TMX_CLIENT_SDK,
        "x-tmx-device-id": device_id,
        "access-token-host": access_token_host,
        "x-tmx-service": "HOST",
    }
    if cookie_header:
        headers["cookie"] = cookie_header
    url = f"{TM_APP_BASE}/tmx-prod/v1/member/account/details.json"
    status, body = _http_get(url, headers, proxy_url=proxy_url)
    if status != 200:
        return None, status, body.decode("utf-8", errors="replace")[:400]
    try:
        return json.loads(body.decode("utf-8")), status, ""
    except Exception as e:
        return None, status, str(e)


def _tm_events_json(
    access_token_host: str,
    device_id: str,
    member_id: str,
    email: str,
    global_uid: str,
    cookie_header: str = "",
    *,
    proxy_url: str | None = None,
) -> tuple[dict | None, int, str]:
    headers = {
        "content-type": "application/json",
        "x-host-member-id": member_id,
        "x-tmx-service": "HOST",
        "accept": "application/vnd.amgr.v1.2+json",
        "call-source": "TicketsSDK.EventsViewControllerV2.viewDidLoad.update",
        "preferred-languages": "[en]",
        "x-tmx-email-host": email,
        "priority": "u=3",
        "accept-language": "en-US",
        "x-api-key": TM_API_KEY,
        "x-tmx-global-user-id": global_uid,
        "accept-encoding": "gzip, deflate, br",
        "user-agent": TM_PSDK_UA,
        "x-tmx-client-sdk": TMX_CLIENT_SDK,
        "access-token-host": access_token_host,
        "x-tmx-device-id": device_id,
    }
    if cookie_header:
        headers["cookie"] = cookie_header
    url = f"{TM_APP_BASE}/tmx-prod/v1/events.json"
    status, body = _http_get(url, headers, proxy_url=proxy_url)
    if status != 200:
        return None, status, body.decode("utf-8", errors="replace")[:400]
    try:
        return json.loads(body.decode("utf-8")), status, ""
    except Exception as e:
        return None, status, str(e)


def _tm_securetickets_for_event(
    access_token_host: str,
    device_id: str,
    email: str,
    hmac_member_id: str,
    event_id: str,
    orders: list[dict],
    cookie_header: str = "",
    *,
    proxy_url: str | None = None,
) -> tuple[dict | None, int, str]:
    pairs: list[tuple[str, str]] = []
    for o in orders:
        enc = (o.get("encoded_order_id") or "").strip()
        disp = (o.get("order_id") or "").strip()
        if enc:
            pairs.append(("orderIds[]", enc))
        if disp:
            pairs.append(("tapOrderIds[]", disp))
    pairs.extend(
        [
            ("tapEventIds[]", "null"),
            ("nfcCapableDevice", "true"),
            ("apikey", TM_API_KEY),
        ]
    )
    q = urllib.parse.urlencode(pairs)
    url = f"{TM_APP_BASE}/tmx-prod/v1/events/securetickets/{event_id}.json?{q}"
    headers = {
        "content-type": "application/json; charset=utf-8",
        "accept": "application/vnd.amgr.v1.2+json",
        "authorization": f"Bearer {access_token_host}",
        "x-tmx-email-host": email,
        "priority": "u=3",
        "accept-language": "en-us",
        "x-api-key": TM_API_KEY,
        "member-id": hmac_member_id,
        "data-type": "json",
        "accept-encoding": "gzip",
        "user-agent": TM_CFNETWORK_UA,
        "x-tmx-client-sdk": "iOS v272.2",
        "access-token-host": access_token_host,
        "x-tmx-device-id": device_id,
    }
    if cookie_header:
        headers["cookie"] = cookie_header
    status, body = _http_get(url, headers, proxy_url=proxy_url)
    if status != 200:
        return None, status, body.decode("utf-8", errors="replace")[:400]
    try:
        return json.loads(body.decode("utf-8")), status, ""
    except Exception as e:
        return None, status, str(e)


def fetch_tm_barcode_tokens_for_block(
    acc: dict,
    *,
    proxy_url: str | None = None,
) -> tuple[list[dict], str | None]:
    """
    Call TM /events.json + per-event /securetickets/{id}.json using web id-token + tmpt cookies.
    Returns (rows for barcode_tokens, error_message or None).
    """
    lines = acc.get("cookies_lines") or []
    jar = _cookie_jar_from_lines(lines)
    blob = "\n".join(lines) + "\n" + (acc.get("raw") or "")
    id_token = (
        _jar_get_ci(jar, "id-token")
        or _extract_cookie_value_from_text(blob, "id-token")
        or _find_tm_web_id_jwt(jar, blob)
    )
    if not id_token:
        return [], (
            "no id-token / TM JWS in Cookies — need auth.ticketmaster.com id-token (or equivalent JWS) "
            "for app API; use --cookies-file if missing from the block."
        )

    tmpt = (_jar_get_ci(jar, "tmpt") or _extract_cookie_value_from_text(blob, "tmpt")).strip()
    if not tmpt:
        tmpt = str(uuid.uuid4()).upper()

    cookie_header = _cookie_header_from_jar(jar)

    jwt = _jwt_payload_unverified(id_token) or {}
    email = (jwt.get("email") or "").strip()
    if not email:
        email = (parse_header_meta(acc.get("header") or "").get("email") or "").strip()
    if not email:
        return [], "could not read email from id-token JWT or block header"

    hmac_uid = (jwt.get("hmac_user_id") or jwt.get("hmacUserId") or "").strip()
    global_uid = (jwt.get("encrypted_system_user_id") or jwt.get("sub") or "").strip()

    host, st_d, err_d = _tm_account_details(
        id_token, tmpt, cookie_header, proxy_url=proxy_url
    )
    member_id = ""
    if isinstance(host, dict):
        hm = host.get("hostMember") or host.get("host_member") or {}
        if isinstance(hm, dict):
            member_id = (hm.get("member_id") or "").strip()
            gu = (hm.get("global_user_id") or "").strip()
            if gu:
                global_uid = gu
    if not member_id:
        member_id = hmac_uid
    if not member_id:
        return [], f"account/details failed ({st_d}): {err_d}" if st_d != 200 else "missing member_id"

    ev_json, st_e, err_e = _tm_events_json(
        id_token,
        tmpt,
        member_id,
        email,
        global_uid,
        cookie_header,
        proxy_url=proxy_url,
    )
    # Go checker uses a bare TLS client jar; conflicting web Cookie + web id-token sometimes yields 401.
    if not isinstance(ev_json, dict) and st_e == 401 and cookie_header:
        ev_json, st_e, err_e = _tm_events_json(
            id_token,
            tmpt,
            member_id,
            email,
            global_uid,
            "",
            proxy_url=proxy_url,
        )
    if not isinstance(ev_json, dict):
        msg = f"events.json HTTP {st_e}: {err_e}"
        if st_e == 401:
            msg += (
                " | tm-fcap Go uses iOS OAuth: sign-in → auth code → POST app.ticketmaster.com/tmx-prod/v1/accounts/exchange "
                "→ accessToken (mobile), then events.json with that token — not the browser id-token JWT. "
                "Use --tickets path/to/tickets.txt from the Go checker for barcodes."
            )
        return [], msg

    events = ev_json.get("events") or []
    out_rows: list[dict] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if ev.get("past_event"):
            continue
        eid = (ev.get("event_id") or "").strip()
        if not eid:
            continue
        orders: list[dict] = []
        for ho in ev.get("host_orders") or []:
            if not isinstance(ho, dict):
                continue
            orders.append(
                {
                    "order_id": (ho.get("display_order_id") or "").strip(),
                    "encoded_order_id": (ho.get("order_id") or "").strip(),
                }
            )
        if not orders:
            continue

        ev_image_url = ""
        eimg = ev.get("event_image") or ev.get("eventImage")
        if isinstance(eimg, dict):
            ev_image_url = (eimg.get("url") or "").strip()

        st_data, st_s, st_err = _tm_securetickets_for_event(
            id_token,
            tmpt,
            email,
            hmac_uid or member_id,
            eid,
            orders,
            cookie_header,
            proxy_url=proxy_url,
        )
        if not isinstance(st_data, dict):
            continue
        ev_name = (ev.get("name") or "Event").strip()
        ev_date_raw, ev_venue = _tm_event_date_venue_from_api(ev)
        for t in st_data.get("tickets") or []:
            if not isinstance(t, dict):
                continue
            delivery = t.get("delivery") or {}
            if not isinstance(delivery, dict):
                continue
            stok = (delivery.get("secure_token") or "").strip()
            if len(stok) < 24:
                continue
            sec = (t.get("section_label") or "").strip()
            row = (t.get("row_label") or "").strip()
            seat = (t.get("seat_label") or "").strip()
            seat_bits = "/".join(x for x in (sec, row, seat) if x)
            label = f"{ev_name} · {seat_bits}" if seat_bits else ev_name
            trow: dict = {
                "secure_token_b64": stok,
                "label": label,
                "event_name": ev_name,
                "section": sec,
                "row": row,
                "seat": seat,
            }
            tt = (t.get("ticket_type") or t.get("ticket_type_description") or "").strip()
            if tt:
                trow["ticket_type"] = tt[:100]
            eg = (t.get("entry_gate") or "").strip()
            if eg:
                trow["gate"] = eg[:100]
            if ev_image_url:
                trow["image_url"] = ev_image_url[:800]
            if ev_date_raw:
                trow["event_date"] = ev_date_raw[:120]
            if ev_venue:
                trow["venue"] = ev_venue[:120]
            out_rows.append(trow)

    if not out_rows:
        return [], "no secure_token in API responses (expired id-token, no upcoming orders, or TLS blocked — try: pip install curl_cffi)"
    return out_rows, None


def _block_has_session_cookies_for_fetch(acc: dict) -> bool:
    """True if block looks like it has tmpt + id-token (or mergeable TM session), after normalization."""
    lines = acc.get("cookies_lines") or []
    jar = _cookie_jar_from_lines(lines)
    blob = "\n".join(lines)
    has_tmpt = bool(_jar_get_ci(jar, "tmpt") or _extract_cookie_value_from_text(blob, "tmpt"))
    has_id = bool(
        _jar_get_ci(jar, "id-token")
        or _extract_cookie_value_from_text(blob, "id-token")
        or _find_tm_web_id_jwt(jar, blob)
    )
    return has_tmpt and has_id


def _blocks_have_session_cookies(blocks: list[dict]) -> bool:
    return any(_block_has_session_cookies_for_fetch(b) for b in blocks)


def _block_already_has_barcode_source(acc: dict) -> bool:
    if (acc.get("secure_token_b64") or "").strip():
        return True
    for r in acc.get("barcode_tokens") or []:
        if (r.get("secure_token_b64") or "").strip():
            return True
    return False


def _escape(s: str) -> str:
    return html.escape(s, quote=True)


def _parse_label_seat(label: str) -> tuple[str, str, str, str]:
    """From 'Event · Sec A · Row B · Seat C' extract event + section/row/seat."""
    parts = [p.strip() for p in (label or "").split(" · ")]
    ev = parts[0] if parts else ""
    sec, row, seat = "", "", ""
    for p in parts[1:]:
        low = p.lower()
        if low.startswith("sec "):
            sec = p[4:].strip()
        elif low.startswith("row "):
            row = p[4:].strip()
        elif low.startswith("seat "):
            seat = p[5:].strip()
    return ev, sec, row, seat


def _hero_hue_from_text(s: str) -> int:
    return int(hashlib.sha256((s or "x").encode()).hexdigest()[:8], 16) % 360


def _parse_checker_upcoming_subtitle(line: str, event_title: str = "") -> str:
    """``→ Event | Nx tickets | date | venue | Status`` → ``date\\nvenue`` for pass header."""
    s = _strip_event_arrow((line or "").strip())
    if not s:
        return ""
    parts = [p.strip() for p in s.split("|") if p.strip()]
    if len(parts) >= 4 and re.search(r"\d+x\s+tickets?", parts[1], re.I):
        date_s = _format_pass_event_date_display(parts[2])
        venue_s = parts[3].strip()
        if date_s and venue_s:
            return f"{date_s}\n{venue_s}"
        if date_s:
            return date_s
        if venue_s:
            return venue_s
    if _should_simplify_subtitle(s):
        simp = _simplify_ticket_subtitle(s, event_title)
        if simp:
            if "\n" in simp:
                return simp
            bits = [p.strip() for p in re.split(r"\s*·\s*", simp) if p.strip()]
            if len(bits) >= 2:
                return f"{bits[0]}\n{bits[-1]}"
            return simp
    return s


def _tm_pass_subtitle_from_row(row: dict, upcoming: list[str]) -> str:
    """Date + venue for TM pass header (line 1 date, line 2 venue — like the app)."""
    date_s = _format_pass_event_date_display(str(row.get("event_date") or ""))
    venue_s = (row.get("venue") or "").strip()
    if date_s and venue_s:
        return f"{date_s}\n{venue_s}"
    if date_s:
        return date_s
    if venue_s:
        return venue_s
    ev = (row.get("event_name") or "").strip()
    matched = _match_upcoming_subtitle(ev, upcoming) if ev and upcoming else ""
    if matched:
        parsed = _parse_checker_upcoming_subtitle(matched, ev)
        if parsed and "SafeTix" not in parsed:
            return parsed
    return ""


def _tm_event_date_venue_from_api(ev: dict) -> tuple[str, str]:
    """Pull date + venue strings from TM app ``events.json`` event object."""
    if not isinstance(ev, dict):
        return "", ""
    _v = ev.get("venue")
    venue = (_v.get("name") if isinstance(_v, dict) else _v) or ""
    venue = str(venue).strip()
    _ed = ev.get("event_date") if isinstance(ev.get("event_date"), dict) else {}
    date_s = str(_ed.get("date") or "").strip()
    time_s = str(_ed.get("time") or "").strip()
    utc_s = str(_ed.get("datetime_utc") or "").strip()
    if date_s and time_s:
        ts = time_s.split(".")[0].strip()
        if len(ts) == 5 and ts[2] == ":":
            ts = f"{ts}:00"
        raw = f"{date_s} {ts}"
    elif date_s:
        raw = date_s
    else:
        raw = utc_s
    return raw, venue


def _match_upcoming_subtitle(event_name: str, upcoming: list[str]) -> str:
    if not event_name or not upcoming:
        return ""
    en = event_name.lower().strip()
    toks = [t for t in re.split(r"\W+", en) if len(t) > 3][:5]
    for line in upcoming:
        low = _strip_event_arrow(line).lower()
        if en[:18] in low or (toks and sum(1 for t in toks if t in low) >= 2):
            return _strip_event_arrow(line)
    return ""


def _subtitle_compact_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _should_simplify_subtitle(sub: str) -> bool:
    if not sub or "SafeTix" in sub:
        return False
    return bool(
        re.search(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", sub)
        or re.search(r"\d+x\s+tickets?", sub, re.I)
        or re.search(r"Status:\s*", sub, re.I)
    )


def _simplify_ticket_subtitle(raw: str, event_title: str) -> str:
    """Checker-style upcoming line → short TM-like line: date · time · venue (no ticket counts/status/tz)."""
    s = (raw or "").strip()
    if not s:
        return s
    parts = re.split(r"\s*[•·|]\s*", s)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return s

    ev_c = _subtitle_compact_key(event_title)
    dt_line = ""
    consumed = [False] * len(parts)

    for i, p in enumerate(parts):
        pl = p.lower()
        if re.match(r"^\d+x\s+tickets?$", pl):
            consumed[i] = True
            continue
        if pl.startswith("status:"):
            consumed[i] = True
            continue
        m = re.match(
            r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}):(\d{2}):(\d{2})\s*(\([A-Za-z_/]+\))?$",
            p,
        )
        if m:
            try:
                d = datetime.strptime(
                    f"{m.group(1)} {m.group(2)}:{m.group(3)}:{m.group(4)}",
                    "%Y-%m-%d %H:%M:%S",
                )
                day = d.day
                wk = d.strftime("%a")
                mon = d.strftime("%b")
                h24 = d.hour
                mnt = d.minute
                h12 = h24 % 12 or 12
                suff = "AM" if h24 < 12 else "PM"
                dt_line = f"{wk}, {mon} {day}, {d.year} · {h12}:{mnt:02d} {suff}"
            except ValueError:
                pass
            consumed[i] = True
            continue
        pc = _subtitle_compact_key(p)
        if ev_c and len(pc) > 8 and (pc == ev_c or pc in ev_c or ev_c in pc):
            consumed[i] = True
            continue

    venue = ""
    for i, p in enumerate(parts):
        if consumed[i]:
            continue
        pl = p.lower()
        venue_hints = (
            "arena",
            "center",
            "centre",
            "stadium",
            "theatre",
            "theater",
            "ballroom",
            "pavilion",
            "auditorium",
            "amphitheatre",
            "coliseum",
            "amphitheater",
        )
        if "," in p or any(h in pl for h in venue_hints):
            venue = p

    chunks: list[str] = []
    if dt_line:
        chunks.append(dt_line)
    if venue:
        if len(venue) > 52:
            venue = venue.split(",")[0].strip() + ", …"
        chunks.append(venue)
    if chunks:
        return " · ".join(chunks)

    tail = [parts[i] for i in range(len(parts)) if not consumed[i]]
    if not tail:
        return s
    if len(tail) <= 2:
        return " · ".join(tail)
    return " · ".join(tail[:2]) + " · …"


def _reminder_iso_from_checker_line(raw: str) -> str | None:
    """Checker ``YYYY-MM-DD HH:MM:SS`` (+ optional ``(IANA/Zones)``) → UTC ISO ``…Z`` for reminder API."""
    if not (raw or "").strip():
        return None
    m = re.search(
        r"(\d{4}-\d{2}-\d{2})\s+(\d{2}):(\d{2}):(\d{2})(?:\s*\(([A-Za-z_/]+)\))?",
        raw,
    )
    if not m:
        return None
    ds = f"{m.group(1)} {m.group(2)}:{m.group(3)}:{m.group(4)}"
    try:
        dt_naive = datetime.strptime(ds, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    tznam = (m.group(5) or "").strip()
    if tznam:
        try:
            from zoneinfo import ZoneInfo

            aware = dt_naive.replace(tzinfo=ZoneInfo(tznam))
            return aware.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass
    return dt_naive.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _reminder_date_only_from_checker_line(raw: str) -> str | None:
    if not (raw or "").strip():
        return None
    m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", raw)
    if not m:
        return None
    return m.group(1)


def _reminder_date_slots_enabled() -> bool:
    v = (os.environ.get("TM_VIEWER_REMINDER_DATE_ONLY_SLOTS") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def _primary_barcode_row_for_reminder(acc: dict, only_si: int | None) -> dict:
    slots = _collect_barcode_slots(acc)
    if not slots:
        return {}
    if only_si is not None and 0 <= only_si < len(slots):
        idx = only_si
    else:
        idx = 0
    _cfg, lab, _demo, row = slots[idx]
    r = dict(row)
    r.setdefault("label", lab)
    return r


def _tm_viewer_reminder_fragments(
    acc: dict, *, only_si: int | None
) -> tuple[str, str]:
    """``(head_meta_block, body_script_tail)`` for Resend/Vercel ticket reminders + optional email gate."""
    flag = (os.environ.get("TM_VIEWER_REMINDER_METAS") or "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return "", ""
    row = _primary_barcode_row_for_reminder(acc, only_si)
    upcoming = acc.get("upcoming") or []
    ev = (row.get("event_name") or row.get("label") or "").strip()
    matched = _match_upcoming_subtitle(ev, upcoming) if ev else ""
    source = (matched or "").strip()
    if not source and upcoming:
        source = _strip_event_arrow(upcoming[0])
    iso = _reminder_iso_from_checker_line(source) if source else None
    date_only = None if iso else (_reminder_date_only_from_checker_line(source) if source else None)
    title = (ev or (source[:300] if source else "") or "Your event").strip()
    if len(title) > 500:
        title = title[:500]

    watch = (os.environ.get("TM_VIEWER_WATCH_PUBLIC_BASE") or "").strip().rstrip("/")
    if not watch:
        watch = _TM_VIEWER_PASS_SITE_PUBLIC_BASE_DEFAULT
    reg_url = (os.environ.get("TM_VIEWER_REMINDER_REGISTER_URL") or "").strip().rstrip("/")
    embed_gate = (
        os.environ.get("TM_VIEWER_EMBED_EMAIL_GATE") or ""
    ).strip().lower() in ("1", "true", "yes", "on")
    if not reg_url:
        if embed_gate:
            reg_url = "/api/ticket-reminders/register"
        else:
            reg_url = f"{watch}/api/ticket-reminders/register"

    head_lines = [
        f'  <meta name="tm-reminder-register-url" content="{html.escape(reg_url, quote=True)}"/>',
    ]
    if iso:
        head_lines.append(
            f'  <meta name="tm-event-start" content="{html.escape(iso, quote=True)}"/>',
        )
    elif date_only and _reminder_date_slots_enabled():
        head_lines.append('  <meta name="tm-reminder-mode" content="date_slots"/>')
        head_lines.append(
            f'  <meta name="tm-reminder-date" content="{html.escape(date_only, quote=True)}"/>'
        )
    head_lines.append(
        f'  <meta name="tm-event-title" content="{html.escape(title, quote=True)}"/>',
    )
    head_metas = "\n".join(head_lines) + "\n"

    body_tail = ""
    if embed_gate:
        head_metas += '  <meta name="tm-email-gate-enabled" content="1"/>\n'
        gate_js = (os.environ.get("TM_VIEWER_EMAIL_GATE_JS_URL") or "").strip()
        if not gate_js:
            gate_js = _TM_VIEWER_EMAIL_GATE_JS_PATH_DEFAULT
        body_tail = (
            f'<script defer src="{html.escape(gate_js, quote=True)}"></script>\n'
        )
    return head_metas, body_tail


def _reminder_inject_strip_prior_blocks(html: str) -> str:
    """Remove prior ``<!-- tm-viewer-inject:… -->`` reminder / gate blocks."""
    out = html
    out = re.sub(
        r"<!--\s*tm-viewer-inject:reminders\s+start\s*-->[\s\S]*?<!--\s*tm-viewer-inject:reminders\s+end\s*-->\s*",
        "",
        out,
        flags=re.I,
    )
    out = re.sub(
        r"<!--\s*tm-viewer-inject:email-gate\s+start\s*-->[\s\S]*?<!--\s*tm-viewer-inject:email-gate\s+end\s*-->\s*",
        "",
        out,
        flags=re.I,
    )
    return out


def _reminder_strip_legacy_tm_metas_and_gate_script(html: str) -> str:
    """Remove reminder ``<meta>`` / ``tm-email-gate.js`` tags not wrapped in inject comments (replace mode)."""
    out = html
    for name in (
        "tm-reminder-register-url",
        "tm-event-start",
        "tm-reminder-mode",
        "tm-reminder-date",
        "tm-event-title",
        "tm-email-gate-enabled",
    ):
        out = re.sub(
            rf'<meta\s+[^>]*name=["\']{re.escape(name)}["\'][^>]*>\s*',
            "",
            out,
            flags=re.I,
        )
    out = re.sub(
        r'<script\s+[^>]*src=["\'][^"\']*tm-email-gate\.js[^"\']*["\'][^>]*>\s*</script>\s*',
        "",
        out,
        flags=re.I,
    )
    out = re.sub(
        r'<script\s+[^>]*src=["\'][^"\']*tm-email-gate\.js[^"\']*["\'][^>]*/>\s*',
        "",
        out,
        flags=re.I,
    )
    return out


def _scrape_pass_html_reminder_title(doc: str) -> str:
    m = re.search(
        r'<meta\s+[^>]*name=["\']tm-event-title["\'][^>]*content=["\']([^"\']*)["\']',
        doc,
        re.I,
    )
    if m and (m.group(1) or "").strip():
        s = html.unescape(m.group(1).strip())
        return (s[:500]) if s else "Your event"
    m = re.search(
        r'<h4[^>]*class="[^"]*tm-pass-title[^"]*"[^>]*>([^<]+)</h4>',
        doc,
        re.I,
    )
    if m and (m.group(1) or "").strip():
        s = html.unescape(m.group(1).strip())
        return (s[:500]) if s else "Your event"
    return "Your event"


def _scrape_pass_html_reminder_event_iso(doc: str) -> str | None:
    m = re.search(
        r'<meta\s+[^>]*name=["\']tm-event-start["\'][^>]*content=["\']([^"\']*)["\']',
        doc,
        re.I,
    )
    if m and (m.group(1) or "").strip():
        return (m.group(1).strip())[:80]
    sub_m = re.search(
        r'class="tm-pass-sub"[^>]*>([\s\S]*?)</div>',
        doc,
        re.I,
    )
    blob = sub_m.group(1) if sub_m else doc
    blob_txt = re.sub(r"<[^>]+>", " ", blob)
    return _reminder_iso_from_checker_line(blob_txt)


_RE_STOCK_TICKET_URL = re.compile(
    r"https?://[^,\s|]+/tickets/(?P<gid>\d+)/(?P<slug>[^/,\s?#|]+)", re.I
)
_RE_STOCK_ISO_Z = re.compile(r"(20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)")


def _resolve_links_txt_for_date_update(site_root: Path, explicit_links: str) -> Path | None:
    if (explicit_links or "").strip():
        p = Path(explicit_links.strip()).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
        p = p.resolve()
        return p if p.is_file() else None

    for cand in (site_root / "links.txt", site_root.parent / "links.txt", Path.cwd() / "links.txt"):
        try:
            if cand.is_file():
                return cand.resolve()
        except OSError:
            continue

    envp = (os.environ.get("TM_VIEWER_LINKS_TXT") or "").strip()
    if envp:
        first = re.split(r"[;|]", envp, maxsplit=1)[0].strip()
        if first:
            p = Path(first).expanduser()
            if not p.is_absolute():
                p = Path.cwd() / p
            p = p.resolve()
            if p.is_dir():
                p = p / "links.txt"
            if p.is_file():
                return p
    return None


def _upsert_meta_in_head(doc: str, name: str, content: str) -> str:
    h = doc or ""
    escaped = html.escape(content, quote=True)
    tag = f'  <meta name="{name}" content="{escaped}"/>'
    pat = re.compile(
        rf'<meta\s+[^>]*name=["\']{re.escape(name)}["\'][^>]*>\s*',
        re.I,
    )
    if pat.search(h):
        return pat.sub(tag + "\n", h, count=1)

    head_m = re.search(r"(<head[^>]*>)", h, re.I)
    if not head_m:
        return h
    i = head_m.end()
    return h[:i] + "\n" + tag + "\n" + h[i:]


def _remove_meta_in_head(doc: str, name: str) -> str:
    return re.sub(
        rf'<meta\s+[^>]*name=["\']{re.escape(name)}["\'][^>]*>\s*',
        "",
        doc or "",
        flags=re.I,
    )


def update_reminder_dates_from_links_txt(
    site_dir: Path, *, links_txt: str = ""
) -> tuple[int, list[str]]:
    """
    Update reminder date/time metas in existing pass HTML using links.txt lines.
    Patches only tm-event-start / tm-reminder-mode / tm-reminder-date.
    """
    msgs: list[str] = []
    root = site_dir.expanduser().resolve()
    tdir = root / "tickets"
    if not tdir.is_dir():
        return 0, [f"No tickets/ directory under {root}"]

    lp = _resolve_links_txt_for_date_update(root, links_txt)
    if lp is None:
        return 0, ["No links.txt found (pass --links-txt PATH or set TM_VIEWER_LINKS_TXT)."]

    try:
        raw = lp.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return 0, [f"links.txt read failed: {e}"]

    by_ticket: dict[tuple[str, str], str] = {}
    for ln in raw.splitlines():
        s = (ln or "").strip()
        if not s or s.startswith("#"):
            continue
        m = _RE_STOCK_TICKET_URL.search(s)
        if not m:
            continue
        by_ticket[(m.group("gid"), m.group("slug"))] = s

    if not by_ticket:
        return 0, [f"No /tickets/<gid>/<slug> lines in {lp}"]

    n_ok = 0
    for html_path in sorted(tdir.glob("*/*.html")):
        gid = html_path.parent.name
        slug = html_path.stem
        stock_line = by_ticket.get((gid, slug))
        if not stock_line:
            continue

        payload = stock_line.split("|", 1)[1].strip() if "|" in stock_line else stock_line
        iso = _reminder_iso_from_checker_line(payload)
        if not iso:
            miz = _RE_STOCK_ISO_Z.search(payload)
            if miz:
                iso = miz.group(1)
        date_only = None if iso else _reminder_date_only_from_checker_line(payload)
        if not iso and not date_only:
            continue

        rel = html_path.relative_to(root).as_posix()
        try:
            old = html_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            msgs.append(f"{rel}: read {e}")
            continue

        new = old
        if iso:
            new = _upsert_meta_in_head(new, "tm-event-start", iso)
            new = _remove_meta_in_head(new, "tm-reminder-mode")
            new = _remove_meta_in_head(new, "tm-reminder-date")
        elif date_only and _reminder_date_slots_enabled():
            new = _remove_meta_in_head(new, "tm-event-start")
            new = _upsert_meta_in_head(new, "tm-reminder-mode", "date_slots")
            new = _upsert_meta_in_head(new, "tm-reminder-date", date_only)

        if new == old:
            msgs.append(f"{rel}: no changes")
            continue
        try:
            html_path.write_text(new, encoding="utf-8", newline="\n")
        except OSError as e:
            msgs.append(f"{rel}: write {e}")
            continue
        n_ok += 1
        msgs.append(f"+ updated reminder date {rel}")

    msgs.append(f"links source: {lp}")
    return n_ok, msgs


_RE_YMD = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def _format_pass_subtitle_date_line(event_date: str, event_time: str = "") -> str:
    """Build first ``tm-pass-sub-line`` from YYYY-MM-DD and optional HH:MM (24h)."""
    ymd = (event_date or "").strip()
    if not _RE_YMD.fullmatch(ymd):
        m = _RE_YMD.search(ymd)
        ymd = m.group(1) if m else ymd
    tm = (event_time or "").strip()
    if tm and re.fullmatch(r"\d{1,2}:\d{2}", tm):
        h, mi = tm.split(":", 1)
        raw = f"{ymd} {int(h):02d}:{mi}:00"
        formatted = _format_pass_event_date_display(raw)
        if formatted and formatted != raw:
            return formatted
    try:
        dt = datetime.strptime(ymd, "%Y-%m-%d")
        return dt.strftime("%a, %b %d, %Y")
    except ValueError:
        return ymd


def _extract_venue_from_pass_subtitle(doc: str) -> str:
    """Second subtitle line, or venue text glued after YYYY-MM-DD on one line."""
    sub_lines = re.findall(
        r'<span class="tm-pass-sub-line"[^>]*>([^<]*)</span>',
        doc or "",
        re.I,
    )
    cleaned = [html.unescape(x.strip()) for x in sub_lines if (x or "").strip()]
    if len(cleaned) >= 2:
        for line in cleaned[1:]:
            if not _RE_YMD.search(line) and not re.match(r"^\d+x tickets", line, re.I):
                return line
    if len(cleaned) == 1:
        m = re.match(r"20\d{2}-\d{2}-\d{2}\s*(.+)", cleaned[0])
        if m and (m.group(1) or "").strip():
            return m.group(1).strip()
    return ""


def _patch_pass_subtitle_date_in_html(doc: str, date_line: str, *, venue: str = "") -> str:
    """Replace date portion of ``tm-pass-sub``; preserve venue line when possible."""
    if not (doc or "").strip() or not (date_line or "").strip():
        return doc or ""
    venue_s = (venue or "").strip() or _extract_venue_from_pass_subtitle(doc)
    date_esc = html.escape(date_line.strip(), quote=False)
    venue_esc = html.escape(venue_s, quote=False) if venue_s else ""

    def _rebuild_sub(_: re.Match[str]) -> str:
        parts = [f'<span class="tm-pass-sub-line">{date_esc}</span>']
        if venue_esc:
            parts.append(f'<span class="tm-pass-sub-line">{venue_esc}</span>')
        inner = "".join(parts)
        return f'<p class="tm-pass-sub">{inner}</p>'

    sub_m = re.search(r'<p class="tm-pass-sub"[^>]*>[\s\S]*?</p>', doc, re.I)
    if sub_m:
        return doc[: sub_m.start()] + re.sub(
            r'<p class="tm-pass-sub"[^>]*>[\s\S]*?</p>',
            _rebuild_sub,
            doc[sub_m.start() : sub_m.end()],
            count=1,
            flags=re.I,
        ) + doc[sub_m.end() :]

    lines = re.findall(
        r'(<span class="tm-pass-sub-line"[^>]*>)([^<]*)(</span>)',
        doc,
        re.I,
    )
    if not lines:
        return doc
    out = doc
    replaced = False
    for i, (pre, text, post) in enumerate(lines):
        t = html.unescape(text.strip())
        if replaced:
            break
        if _RE_YMD.search(t) or re.search(
            r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b", t, re.I
        ):
            old = pre + text + post
            new = pre + date_esc + post
            out = out.replace(old, new, 1)
            replaced = True
            if venue_esc and i + 1 < len(lines):
                pre2, _t2, post2 = lines[i + 1]
                out = out.replace(pre2 + lines[i + 1][1] + post2, pre2 + venue_esc + post2, 1)
    return out


def _checker_datetime_line(
    event_date: str, event_time: str = "", event_tz: str = ""
) -> str:
    """Build checker-style datetime text for ISO + pass subtitle formatting."""
    ymd = (event_date or "").strip()
    if not _RE_YMD.fullmatch(ymd):
        m = _RE_YMD.search(ymd)
        ymd = m.group(1) if m else ymd
    tm = (event_time or "").strip()
    if tm and re.fullmatch(r"\d{1,2}:\d{2}", tm):
        h, mi = tm.split(":", 1)
        ds = f"{ymd} {int(h):02d}:{mi}:00"
        tz = (event_tz or "").strip()
        return f"{ds} ({tz})" if tz else ds
    return ymd


def _parse_stock_payload_datetime(payload: str) -> tuple[str, str, str]:
    """Return (ymd, HH:MM, IANA tz) from stock/links line payload if present."""
    raw = (payload or "").strip()
    m = re.search(
        r"(\d{4}-\d{2}-\d{2})\s+(\d{2}):(\d{2}):(\d{2})(?:\s*\(([A-Za-z_/]+)\))?",
        raw,
    )
    if m:
        return m.group(1), f"{m.group(2)}:{m.group(3)}", (m.group(5) or "").strip()
    dm = _RE_YMD.search(raw)
    return (dm.group(1), "", "") if dm else ("", "", "")


def _event_datetime_iso_from_parts(
    event_date: str, event_time: str = "", event_tz: str = ""
) -> str | None:
    line = _checker_datetime_line(event_date, event_time, event_tz)
    if not (event_time or "").strip():
        return None
    return _reminder_iso_from_checker_line(line)


def update_pass_date_in_site_dir(
    site_dir: Path,
    *,
    only_pass_rel: str = "",
    event_date: str = "",
    event_time: str = "",
    event_tz: str = "",
    links_txt: str = "",
) -> tuple[int, list[str]]:
    """
    Patch visible pass subtitle date + reminder metas in existing pass HTML.
    Does not alter SafeTix / barcodes.
    """
    msgs: list[str] = []
    root = site_dir.expanduser().resolve()
    tdir = root / "tickets"
    if not tdir.is_dir():
        return 0, [f"No tickets/ directory under {root}"]

    only_rel = (only_pass_rel or "").strip().replace("\\", "/")
    by_ticket: dict[tuple[str, str], str] = {}
    lp = _resolve_links_txt_for_date_update(root, links_txt)
    if lp is not None:
        try:
            raw_links = lp.read_text(encoding="utf-8", errors="replace")
            for ln in raw_links.splitlines():
                s = (ln or "").strip()
                if not s or s.startswith("#"):
                    continue
                m = _RE_STOCK_TICKET_URL.search(s)
                if m:
                    by_ticket[(m.group("gid"), m.group("slug"))] = s
        except OSError as e:
            msgs.append(f"links.txt read failed: {e}")

    explicit_date = (event_date or "").strip()
    explicit_time = (event_time or "").strip()
    explicit_tz = (event_tz or "").strip()
    n_ok = 0
    for html_path in sorted(tdir.glob("*/*.html")):
        rel = html_path.relative_to(root).as_posix()
        if only_rel and not _pass_rel_matches_only(rel, only_rel):
            continue

        gid = html_path.parent.name
        slug = html_path.stem
        stock_line = by_ticket.get((gid, slug), "")

        ymd = explicit_date
        etime = explicit_time
        etz = explicit_tz
        venue_hint = ""
        if stock_line:
            payload = stock_line.split("|", 1)[1].strip() if "|" in stock_line else stock_line
            parts = [p.strip() for p in payload.split(",") if p.strip()]
            if len(parts) >= 4:
                venue_hint = parts[3].strip()
            if not ymd:
                sy, st, stz = _parse_stock_payload_datetime(payload)
                if sy:
                    ymd, etime, etz = sy, st or etime, stz or etz

        if not ymd:
            msgs.append(f"{rel}: no --event-date and no date in links.txt")
            continue

        checker_line = _checker_datetime_line(ymd, etime, etz)
        date_line = _format_pass_event_date_display(checker_line)
        if not date_line or date_line == checker_line[:120]:
            date_line = _format_pass_subtitle_date_line(ymd, etime)
        iso = _reminder_iso_from_checker_line(checker_line) if etime else None
        date_only = None if iso else ymd

        try:
            old = html_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            msgs.append(f"{rel}: read {e}")
            continue

        new = _patch_pass_subtitle_date_in_html(old, date_line, venue=venue_hint)
        if iso:
            new = _upsert_meta_in_head(new, "tm-event-start", iso)
            new = _remove_meta_in_head(new, "tm-reminder-mode")
            new = _remove_meta_in_head(new, "tm-reminder-date")
        elif date_only and _reminder_date_slots_enabled():
            new = _remove_meta_in_head(new, "tm-event-start")
            new = _upsert_meta_in_head(new, "tm-reminder-mode", "date_slots")
            new = _upsert_meta_in_head(new, "tm-reminder-date", date_only)

        if new == old:
            msgs.append(f"{rel}: no changes")
            continue
        try:
            html_path.write_text(new, encoding="utf-8", newline="\n")
        except OSError as e:
            msgs.append(f"{rel}: write {e}")
            continue
        n_ok += 1
        msgs.append(f"+ updated pass date {rel} -> {date_line}")

    if lp is not None:
        msgs.append(f"links source: {lp}")
    if only_rel and n_ok == 0:
        msgs.append(f"no pass matched {only_rel}")
    return n_ok, msgs


def inject_ticket_reminders_into_site_dir(
    site_dir: Path, *, replace_existing: bool = False
) -> tuple[int, list[str]]:
    """
    Patch **existing** ``tickets/<gid>/*.html``: insert reminder ``<meta>`` tags + optional ``tm-email-gate.js``.

    Does **not** modify ``data-tm-safetix`` or the CryptoJS/bwip/SafeTix script bundle (barcodes unchanged).

    Scrapes **event title** from ``tm-event-title`` meta or ``h4.tm-pass-title``; **event start** from
    ``tm-event-start`` meta or checker-style datetime in ``.tm-pass-sub`` / page text.

    Env: ``TM_VIEWER_WATCH_PUBLIC_BASE``, ``TM_VIEWER_REMINDER_REGISTER_URL``,
    ``TM_VIEWER_EMBED_EMAIL_GATE`` (default ``1`` for this inject), ``TM_VIEWER_EMAIL_GATE_JS_URL``,
    ``TM_VIEWER_REMINDER_METAS`` (set ``0`` to no-op).
    """
    msgs: list[str] = []
    root = site_dir.expanduser().resolve()
    tdir = root / "tickets"
    if not tdir.is_dir():
        msgs.append(f"No tickets/ directory under {root}")
        return 0, msgs

    flag = (os.environ.get("TM_VIEWER_REMINDER_METAS") or "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        msgs.append("TM_VIEWER_REMINDER_METAS=0 — nothing to inject.")
        return 0, msgs

    watch = (os.environ.get("TM_VIEWER_WATCH_PUBLIC_BASE") or "").strip().rstrip("/")
    if not watch:
        watch = _TM_VIEWER_PASS_SITE_PUBLIC_BASE_DEFAULT

    eg_raw = (os.environ.get("TM_VIEWER_EMBED_EMAIL_GATE") or "1").strip().lower()
    embed_gate = eg_raw in ("1", "true", "yes", "on", "")

    reg_url = (os.environ.get("TM_VIEWER_REMINDER_REGISTER_URL") or "").strip().rstrip("/")
    if not reg_url:
        if embed_gate:
            reg_url = "/api/ticket-reminders/register"
        else:
            reg_url = f"{watch}/api/ticket-reminders/register"

    gate_js = (os.environ.get("TM_VIEWER_EMAIL_GATE_JS_URL") or "").strip()
    if not gate_js:
        gate_js = _TM_VIEWER_EMAIL_GATE_JS_PATH_DEFAULT

    n_ok = 0
    for gid_dir in sorted(tdir.iterdir(), key=lambda p: p.name):
        if not gid_dir.is_dir() or gid_dir.name.startswith("."):
            continue
        if not gid_dir.name.isdigit():
            continue
        for html_path in sorted(gid_dir.glob("*.html")):
            rel = html_path.relative_to(root).as_posix()
            try:
                fsize = html_path.stat().st_size
            except OSError:
                fsize = 0
            capped = _read_ticket_html_bytes_capped(html_path)
            if not capped and fsize > 0:
                msgs.append(f"{rel}: read bytes failed, skip")
                continue
            head = capped[:98304] if len(capped) > 98304 else capped
            if _should_skip_ticket_html_as_registry_transfer_stub(
                sample_head=head, full_scan=capped
            ):
                msgs.append(f"{rel}: transfer stub page, skip")
                continue
            try:
                old = html_path.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                msgs.append(f"{rel}: read {e}")
                continue

            has_inject = "<!-- tm-viewer-inject:reminders start -->" in old
            has_legacy_meta = bool(
                re.search(r'<meta\s+[^>]*name=["\']tm-reminder-register-url["\']', old, re.I)
            )
            if not replace_existing and (has_inject or has_legacy_meta):
                msgs.append(
                    f"{rel}: already has reminder metas (use --replace-ticket-reminders to overwrite)"
                )
                continue

            new = old
            if replace_existing:
                new = _reminder_inject_strip_prior_blocks(new)
                new = _reminder_strip_legacy_tm_metas_and_gate_script(new)
            title = _scrape_pass_html_reminder_title(new)
            iso = _scrape_pass_html_reminder_event_iso(new)
            date_only = None if iso else _reminder_date_only_from_checker_line(new)

            head_lines = [
                "<!-- tm-viewer-inject:reminders start -->",
                f'  <meta name="tm-reminder-register-url" content="{html.escape(reg_url, quote=True)}"/>',
            ]
            if iso:
                head_lines.append(
                    f'  <meta name="tm-event-start" content="{html.escape(iso, quote=True)}"/>',
                )
            elif date_only and _reminder_date_slots_enabled():
                head_lines.append('  <meta name="tm-reminder-mode" content="date_slots"/>')
                head_lines.append(
                    f'  <meta name="tm-reminder-date" content="{html.escape(date_only, quote=True)}"/>'
                )
            head_lines.append(
                f'  <meta name="tm-event-title" content="{html.escape(title, quote=True)}"/>',
            )
            if embed_gate:
                head_lines.append('  <meta name="tm-email-gate-enabled" content="1"/>')
            head_lines.append("<!-- tm-viewer-inject:reminders end -->")
            inject_head = "\n".join(head_lines) + "\n"

            body_snip = ""
            if embed_gate:
                body_snip = (
                    "<!-- tm-viewer-inject:email-gate start -->\n"
                    f'<script defer src="{html.escape(gate_js, quote=True)}"></script>\n'
                    "<!-- tm-viewer-inject:email-gate end -->\n"
                )

            tit_m = re.search(r"(</title\s*>)", new, flags=re.I)
            if tit_m:
                ins_at = tit_m.end()
                new = new[:ins_at] + "\n" + inject_head + new[ins_at:]
            else:
                hm = re.search(r"(<head[^>]*>)", new, flags=re.I)
                if hm:
                    ins = hm.end()
                    new = new[:ins] + "\n" + inject_head + new[ins:]
                else:
                    msgs.append(f"{rel}: no <title> or <head> — skip")
                    continue

            if body_snip:
                lb = new.lower().rfind("</body>")
                if lb >= 0:
                    new = new[:lb] + body_snip + new[lb:]
                else:
                    new = new + body_snip

            if new == old:
                msgs.append(f"{rel}: unchanged after inject, skip")
                continue
            try:
                html_path.write_text(new, encoding="utf-8", newline="\n")
            except OSError as e:
                msgs.append(f"{rel}: write {e}")
                continue
            n_ok += 1
            msgs.append(f"+ injected reminders {rel}")

    return n_ok, msgs


# Wallet artwork (PNG); button uses Ticketmaster blue (not black) to match TM web/app CTAs.
_TM_WALLET_BADGE_ICON_URL = "https://securemypass.com/tickets/1/appleIcon.png"


def _tm_wallet_badge_markup() -> str:
    """Two-line 'Add to' / 'Apple Wallet' + wallet icon (Apple pass style)."""
    return (
        f'<span class="tm-pass-wallet-badge-ico">'
        f'<img class="tm-pass-wallet-badge-img" src="{_escape(_TM_WALLET_BADGE_ICON_URL)}" alt="" '
        f'width="40" height="28" loading="lazy" decoding="async" referrerpolicy="no-referrer"/>'
        f"</span>"
        '<span class="tm-pass-wallet-badge-text">'
        '<span class="tm-pass-wallet-l1">Add to</span>'
        '<span class="tm-pass-wallet-l2">Apple Wallet</span>'
        "</span>"
    )


# Wordmark: Wikimedia Commons (vector paths; Ticketmaster® is a trademark).
# https://commons.wikimedia.org/wiki/File:TicketMaster_wordmark.svg
_TM_WORDMARK_WIKIMEDIA_SVG = (
    "https://upload.wikimedia.org/wikipedia/commons/7/7d/TicketMaster_wordmark.svg"
)

_TM_VERIFIED_CHECK_SVG = (
    '<svg class="tm-verified-check" viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" '
    'xmlns="http://www.w3.org/2000/svg"><circle cx="10" cy="10" r="10" fill="#026cdf"/>'
    '<path d="M5.5 10.2 8.2 13l6.3-6.5" fill="none" stroke="#fff" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)

_TM_PASS_MENU_ICON = (
    '<svg class="tm-pass-menu-ico" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" '
    'xmlns="http://www.w3.org/2000/svg"><path d="M15 6l-6 6 6 6" fill="none" stroke="currentColor" '
    'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)

_TM_CAROUSEL_ARROW_L = (
    '<svg class="tm-carousel-arrow-svg" viewBox="0 0 24 24" width="17" height="17" aria-hidden="true" '
    'xmlns="http://www.w3.org/2000/svg"><path d="M14 6l-6 6 6 6" fill="none" stroke="currentColor" '
    'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
_TM_CAROUSEL_ARROW_R = (
    '<svg class="tm-carousel-arrow-svg" viewBox="0 0 24 24" width="17" height="17" aria-hidden="true" '
    'xmlns="http://www.w3.org/2000/svg"><path d="M10 6l6 6-6 6" fill="none" stroke="currentColor" '
    'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)

# Browser console hint when CDN/TM blocks or 404 (debug.txt captures server-side paths).
_TM_HERO_IMG_ONERROR = (
    ' onerror="try{var f=this.getAttribute(&quot;data-fallback&quot;);'
    "if(f&amp;&amp;!this.dataset.fb){this.dataset.fb=1;this.src=f;return}"
    'console.warn(&quot;[tm-pass] hero image failed&quot;,this.src)}catch(e){}"'
)


def _hero_data_uri_from_local_site(
    site_root: Path | None, local_rel: str, *, max_bytes: int = 2_800_000
) -> str:
    """Inline downloaded poster bytes so tixx/Vercel (tickets-only proxy) never 404s tm_event_assets/."""
    if not site_root or not local_rel:
        return ""
    lp = _resolve_pass_asset_under_site_root(site_root, local_rel)
    if not lp or not lp.is_file():
        return ""
    try:
        raw = lp.read_bytes()
    except OSError:
        return ""
    if not raw or len(raw) > max_bytes:
        return ""
    low = local_rel.lower()
    if low.endswith(".png"):
        mime = "image/png"
    elif low.endswith(".webp"):
        mime = "image/webp"
    elif low.endswith(".gif"):
        mime = "image/gif"
    else:
        mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _resolve_pass_hero_img_src(
    *,
    local_u: str,
    remote_u: str,
    relative_asset_prefix: str,
    debug_site_root: Path | None,
) -> tuple[str, str]:
    """Return (primary img src, HTTPS fallback for onerror)."""
    local_rel = (local_u or "").strip()
    remote = (remote_u or "").strip()
    if local_rel.startswith(("http://", "https://")):
        if not remote:
            remote = local_rel
        local_rel = ""

    if local_rel and not local_rel.startswith("data:"):
        embedded = _hero_data_uri_from_local_site(debug_site_root, local_rel)
        if embedded:
            return embedded, remote

    if remote.startswith(("http://", "https://")):
        return remote, ""

    if local_rel and not local_rel.startswith("data:"):
        embedded = _hero_data_uri_from_local_site(debug_site_root, local_rel)
        if embedded:
            return embedded, remote

    if remote.startswith(("http://", "https://")):
        return remote, ""

    # Never ship ../../tm_event_assets in pass HTML — tixx/Vercel only proxies /tickets/.
    return "", remote


def _merged_event_media_cache(site_root: Path | None) -> dict:
    cache: dict = {}
    paths: list[Path] = [_default_event_media_cache_path()]
    if site_root is not None:
        paths.insert(0, site_root / "results" / "tm_event_media.json")
    for cp in paths:
        loaded = _load_event_media_cache(cp)
        if loaded:
            cache.update(loaded)
    return cache


def _lookup_event_poster_urls(
    event_name: str,
    *,
    cache: dict,
    site_root: Path | None,
) -> tuple[str, str]:
    """Return (primary img src, HTTPS fallback for onerror)."""
    en_low = (event_name or "").strip().lower()
    if not en_low:
        return "", ""
    best: dict | None = None
    for ent in cache.values():
        if not isinstance(ent, dict):
            continue
        evn = (ent.get("event_name") or "").strip()
        if not evn:
            continue
        ev_low = evn.lower()
        if ev_low == en_low:
            best = ent
            break
        if en_low in ev_low or ev_low in en_low:
            best = ent
    remote = ""
    local_rel = ""
    if best:
        remote = (best.get("image_url") or "").strip()
        local_rel = (best.get("local_relpath") or "").strip().replace("\\", "/")
    if site_root and local_rel:
        emb = _hero_data_uri_from_local_site(site_root, local_rel)
        if emb:
            fb = remote if remote.startswith(("http://", "https://")) else ""
            return emb, fb
    if site_root and not local_rel:
        slug = re.sub(r"[^\w\s-]", "", event_name, flags=re.UNICODE)[:56]
        slug = re.sub(r"[\s_]+", "-", slug.strip()).lower().strip("-")
        assets = site_root / "tm_event_assets"
        if slug and assets.is_dir():
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                for p in sorted(assets.glob(f"*{slug}*{ext}")):
                    rel = p.relative_to(site_root.resolve()).as_posix()
                    emb = _hero_data_uri_from_local_site(site_root, rel)
                    if emb:
                        return emb, remote if remote.startswith(("http://", "https://")) else ""
    if remote.startswith(("http://", "https://")):
        return remote, ""
    return "", ""


def _hero_img_tag_from_urls(primary: str, fallback: str) -> str:
    fb_attr = (
        f' data-fallback="{html.escape(fallback, quote=True)}"' if fallback else ""
    )
    src_attr = primary if primary.startswith("data:") else _escape(primary)
    return (
        f'<img class="tm-pass-hero-bg" src="{src_attr}" alt="" loading="eager" '
        f'decoding="async" referrerpolicy="no-referrer"{fb_attr}{_TM_HERO_IMG_ONERROR}/>'
    )


_PASS_HERO_PATCH_RE = re.compile(
    r'(<h4[^>]*class="[^"]*tm-pass-title[^"]*"[^>]*>)([^<]+)(</h4>[\s\S]*?)'
    r'(<div class=")(tm-pass-hero[^"]*)(">)([\s\S]*?)'
    r'(</div>\s*</div>\s*<div class="tm-pass-body")',
    re.I,
)


def _patch_pass_hero_images_in_html(html_doc: str, site_root: Path) -> str:
    """Repair gradient-only or broken-relative heroes using cache + tm_event_assets/."""
    cache = _merged_event_media_cache(site_root)

    def _repl(m: re.Match) -> str:
        title_open, title_text, mid, div_open, hero_cls, div_end, hero_inner, body_tail = (
            m.groups()
        )
        event_name = html.unescape(title_text.strip())
        has_img = "tm-pass-hero-bg" in hero_inner
        primary = ""
        fb = ""

        def _hero_cls_out(stripped_grad: bool = False) -> str:
            cls = hero_cls
            if stripped_grad:
                cls = re.sub(r"\s*tm-pass-hero--(?:grad|tmblue)\b", "", cls)
            cls = re.sub(r"\s*tm-pass-hero--poster\b", "", cls)
            if "tm-pass-hero--cover" not in cls:
                cls = (cls + " tm-pass-hero--cover").strip()
            return cls

        if has_img:
            src_m = re.search(
                r'(<img class="tm-pass-hero-bg"[^>]*src=")([^"]+)(")',
                hero_inner,
                re.I,
            )
            if src_m:
                src = html.unescape(src_m.group(2).strip())
                if src.startswith("data:"):
                    return m.group(0)
                if src.startswith(("http://", "https://")) and "--tmblue" not in hero_cls:
                    return m.group(0)
                if not src.startswith(("http://", "https://", "data:")):
                    embedded = _hero_data_uri_from_local_site(site_root, src)
                    if embedded:
                        new_inner = src_m.group(1) + embedded + src_m.group(3)
                        return (
                            f"{title_open}{title_text}{mid}{div_open}"
                            f"{_hero_cls_out(stripped_grad=True)}{div_end}"
                            f"{new_inner}{body_tail}"
                        )
                primary, fb = _lookup_event_poster_urls(
                    event_name, cache=cache, site_root=site_root
                )
        elif "--tmblue" in hero_cls or "--grad" in hero_cls:
            primary, fb = _lookup_event_poster_urls(
                event_name, cache=cache, site_root=site_root
            )

        if not primary:
            return m.group(0)

        img_tag = _hero_img_tag_from_urls(primary, fb)
        return (
            f"{title_open}{title_text}{mid}{div_open}"
            f"tm-pass-hero tm-pass-hero--cover{div_end}"
            f"{img_tag}{body_tail}"
        )

    return _PASS_HERO_PATCH_RE.sub(_repl, html_doc)


def _events_missing_hero_in_pass_html(raw: str) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for m in _PASS_HERO_PATCH_RE.finditer(raw or ""):
        event_name = html.unescape(m.group(2).strip())
        hero_cls = m.group(5)
        hero_inner = m.group(7)
        if not event_name:
            continue
        needs = "tm-pass-hero-bg" not in hero_inner or "--tmblue" in hero_cls
        if not needs:
            continue
        key = event_name.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append({"event_name": event_name})
    return rows

_TM_PASS_PHONE_ALERT_ICON = (
    '<svg class="tm-pass-phone-ico" viewBox="0 0 24 24" width="17" height="17" aria-hidden="true" '
    'xmlns="http://www.w3.org/2000/svg">'
    '<rect x="8" y="3" width="8" height="14" rx="1.5" stroke="currentColor" stroke-width="1.6" fill="none"/>'
    '<path d="M10 17h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
    '<path d="M3 9.5h1.5M3 12h1.5M19.5 8.5H21M19.5 12H21" stroke="currentColor" stroke-width="1.4" '
    'stroke-linecap="round"/></svg>'
)


def _tm_pass_type_detail_html(ticket_type: str) -> str:
    """Gray subtitle under Verified Ticket (TM app pattern)."""
    tt = (ticket_type or "").strip() or "Reserved seat ticket"
    return f'<span class="tm-pass-type-detail">{_escape(tt)}</span>'


def _tm_pass_subtitle_lines_html(sub: str) -> str:
    """Split pass header subtitle into lines for staggered entrance (date/time vs venue)."""
    sub = (sub or "").strip()
    if not sub:
        return ""
    if "\n" in sub:
        lines = [ln.strip() for ln in sub.splitlines() if ln.strip()]
    else:
        parts = [p.strip() for p in sub.split(" · ") if p.strip()]
        if len(parts) <= 1:
            lines = [sub]
        elif len(parts) == 2:
            lines = parts
        else:
            lines = [f"{parts[0]} · {parts[1]}", " · ".join(parts[2:])]
    return "".join(f'<span class="tm-pass-sub-line">{_escape(line)}</span>' for line in lines)


def _tm_type_secondary_html(ticket_type: str) -> str:
    """Ticket type line; resale/verified gets Ticketmaster-style check + blue accent."""
    tt = (ticket_type or "").strip() or "Mobile ticket"
    esc = _escape(tt)
    if re.search(r"resale|verified", tt, re.I):
        return (
            f'<div class="tm-pass-type-secondary tm-pass-type-secondary--verified">'
            f"{_TM_VERIFIED_CHECK_SVG}"
            f'<span class="tm-pass-type-sub tm-pass-type-sub--verified">{esc}</span>'
            f"</div>"
        )
    return f'<span class="tm-pass-type-sub">{esc}</span>'


def _acc_has_sg_barcode(acc: dict) -> bool:
    for row in acc.get("barcode_tokens") or []:
        if row.get("sg_barcode"):
            return True
    return False


def _format_pass_event_date_display(raw: str) -> str:
    """Human-readable date for pass subtitle (ISO or checker text)."""
    s = (raw or "").strip()
    if not s:
        return ""
    if re.search(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b", s, re.I):
        return s[:120]
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        h24 = dt.hour
        h12 = h24 % 12 or 12
        suff = "AM" if h24 < 12 else "PM"
        return f"{dt.strftime('%a, %b %d, %Y')} · {h12}:{dt.minute:02d} {suff}"
    except ValueError:
        return s[:120]


def _sg_pass_subtitle_from_upcoming(event_name: str, upcoming: list[str]) -> str:
    """Parse ``→ Event | date | venue`` lines from success.txt (SG claim format)."""
    ev = (event_name or "").strip()
    matched = _match_upcoming_subtitle(ev, upcoming) if ev and upcoming else ""
    if not matched and upcoming:
        matched = upcoming[0]
    if not matched:
        return ""
    line = _strip_event_arrow(matched)
    chunks = [c.strip() for c in line.split("|") if c.strip()]
    if len(chunks) >= 3:
        return f"{chunks[1]}\n{chunks[2]}"
    if len(chunks) == 2:
        return f"{chunks[0]}\n{chunks[1]}"
    simp = _simplify_ticket_subtitle(line, ev)
    if simp and "SafeTix" not in simp:
        parts = [p.strip() for p in re.split(r"\s*·\s*", simp) if p.strip()]
        if len(parts) >= 2:
            return f"{parts[0]}\n{parts[-1]}"
        return simp
    return ""


def _sg_pass_subtitle_from_row(row: dict, upcoming: list[str]) -> str:
    """Date + venue subtitle for SeatGeek passes (same layout as Ticketmaster)."""
    date_s = _format_pass_event_date_display(str(row.get("event_date") or ""))
    venue_s = (row.get("venue") or "").strip()
    if date_s and venue_s:
        return f"{date_s}\n{venue_s}"
    if date_s:
        return date_s
    if venue_s:
        return venue_s
    from_up = _sg_pass_subtitle_from_upcoming(str(row.get("event_name") or ""), upcoming)
    if from_up:
        return from_up
    ev = (row.get("event_name") or "").strip()
    matched = _match_upcoming_subtitle(ev, upcoming) if ev else ""
    if matched:
        if _should_simplify_subtitle(matched):
            matched = _simplify_ticket_subtitle(matched, ev)
        matched = re.sub(r"\s*\|\s*", " · ", matched)
        matched = re.sub(r"\s*·\s*", " · ", matched)
        if matched.strip():
            return matched.strip()
    return ""


def _ticket_card_fields(row: dict, upcoming: list[str]) -> dict:
    label = (row.get("label") or "").strip()
    ev = (row.get("event_name") or "").strip()
    sec = (row.get("section") or "").strip()
    rowv = (row.get("row") or "").strip()
    seat = (row.get("seat") or "").strip()
    if not ev or not (sec or rowv or seat):
        pe, ps, pr, pst = _parse_label_seat(label)
        ev = ev or pe
        sec = sec or ps
        rowv = rowv or pr
        seat = seat or pst
    if row.get("sg_barcode") and not ev and upcoming:
        line = _strip_event_arrow(upcoming[0])
        head = line.split("|", 1)[0].strip()
        if head:
            ev = head
    ttype = (row.get("ticket_type") or "").strip()
    if row.get("sg_barcode"):
        sub = _sg_pass_subtitle_from_row(row, upcoming)
        if not ttype or ttype.lower() in ("standard ticket", "mobile ticket"):
            ttype = "Standard Admission"
    else:
        ttype = _normalize_tm_pass_ticket_type(ttype or "Standard Admission")
        sub = _tm_pass_subtitle_from_row(row, upcoming)
        if not sub:
            sub = _match_upcoming_subtitle(ev, upcoming)
            if sub and _should_simplify_subtitle(sub):
                sub = _simplify_ticket_subtitle(sub, ev)
                bits = [p.strip() for p in re.split(r"\s*·\s*", sub) if p.strip()]
                if len(bits) >= 2 and "\n" not in sub:
                    sub = f"{bits[0]}\n{bits[-1]}"
        if not sub and ttype and ttype.lower() not in _SEAT_TYPE_NOT_TICKET_TYPE:
            sub = ttype
        if not sub:
            sub = "SafeTix · barcode refreshes every 15 seconds"
    gate = (row.get("gate") or "").strip()
    if not gate and not row.get("sg_barcode"):
        gate = _default_tm_pass_gate(row)
    return {
        "event_name": (ev or "Event").upper(),
        "subtitle": sub,
        "section": sec or "—",
        "row": rowv or "—",
        "seat": seat or "—",
        "ticket_kind": "Standard Ticket",
        "ticket_type": ttype or "Standard Admission",
        "gate": gate,
        "pkpass_url": (row.get("pkpass_url") or "").strip(),
        "order_url": (row.get("order_url") or "").strip(),
        "image_url": (row.get("image_url") or "").strip(),
        "image_url_remote": (row.get("image_url_remote") or "").strip(),
        "hue": _hero_hue_from_text(ev or label),
    }


def _collect_barcode_slots(acc: dict) -> list[tuple[str, str, bool, dict]]:
    """Rows with valid secure_token (TM PDF417) or SeatGeek otp+barcode (QR)."""
    slots: list[tuple[str, str, bool, dict]] = []
    for row in acc.get("barcode_tokens") or []:
        if row.get("sg_barcode"):
            val = str(row.get("barcode_value") or "").strip()
            otp = str(row.get("otp_secret") or "").strip()
            if not (val and otp):
                continue
            try:
                period = int(row.get("interval") or 30)
            except (TypeError, ValueError):
                period = 30
            label = (row.get("label") or "Ticket").strip()
            cfg_obj = {"platform": "sg", "v": val, "otp": otp, "period": period, "digits": 6}
            cfg_b64 = base64.b64encode(
                json.dumps(cfg_obj, separators=(",", ":")).encode("utf-8")
            ).decode("ascii")
            slots.append((cfg_b64, label, False, dict(row)))
            continue
        st = (row.get("secure_token_b64") or "").strip()
        label = (row.get("label") or "Ticket").strip()
        tok = _decode_secure_token_b64(st)
        if not tok:
            continue
        raw_t = str(tok.get("t") or tok.get("rawToken") or "").strip()
        ek = str(tok.get("ek") or tok.get("eventKey") or "").strip()
        ck = str(tok.get("ck") or tok.get("customerKey") or "").strip()
        if not (raw_t and ek and ck):
            continue
        cfg_obj = {
            "t": raw_t,
            "ek": ek,
            "ck": ck,
            "period": TOTP_PERIOD,
            "digits": TOTP_DIGITS,
        }
        _merge_safetix_clock_cfg(cfg_obj)
        cfg_b64 = base64.b64encode(
            json.dumps(cfg_obj, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        is_demo = str(tok.get("b")) == "demo" or raw_t.lower().startswith("demo")
        slots.append((cfg_b64, label, is_demo, dict(row)))
    if not slots:
        st_b64 = (acc.get("secure_token_b64") or "").strip()
        if st_b64:
            tok = _decode_secure_token_b64(st_b64)
            if tok:
                raw_t = str(tok.get("t") or tok.get("rawToken") or "").strip()
                ek = str(tok.get("ek") or tok.get("eventKey") or "").strip()
                ck = str(tok.get("ck") or tok.get("customerKey") or "").strip()
                if raw_t and ek and ck:
                    cfg_obj = {
                        "t": raw_t,
                        "ek": ek,
                        "ck": ck,
                        "period": TOTP_PERIOD,
                        "digits": TOTP_DIGITS,
                    }
                    _merge_safetix_clock_cfg(cfg_obj)
                    cfg_b64 = base64.b64encode(
                        json.dumps(cfg_obj, separators=(",", ":")).encode("utf-8")
                    ).decode("ascii")
                    is_demo = str(tok.get("b")) == "demo" or raw_t.lower().startswith("demo")
                    slots.append((cfg_b64, "Inline SecureToken", is_demo, {"label": "Ticket"}))
    return slots


def _acc_with_single_barcode_slot(acc: dict, slot_index: int) -> dict:
    """Shallow-copy one hit block so exactly one barcode row remains (one pass page per seat).

    Never returns the full multi-row ``acc`` for a bad index — that embedded a bundled carousel inside
    ``--one-html-per-seat`` pages. Out-of-range ``slot_index`` clamps to a valid row.
    """
    bt = acc.get("barcode_tokens") or []
    valid_rows: list[dict] = []
    for row in bt:
        if row.get("sg_barcode"):
            val = str(row.get("barcode_value") or "").strip()
            otp = str(row.get("otp_secret") or "").strip()
            if val and otp:
                valid_rows.append(row)
            continue
        st = (row.get("secure_token_b64") or "").strip()
        if not st:
            continue
        tok = _decode_secure_token_b64(st)
        if not tok:
            continue
        raw_t = str(tok.get("t") or tok.get("rawToken") or "").strip()
        ek = str(tok.get("ek") or tok.get("eventKey") or "").strip()
        ck = str(tok.get("ck") or tok.get("customerKey") or "").strip()
        if raw_t and ek and ck:
            valid_rows.append(row)
    if valid_rows:
        n = len(valid_rows)
        try:
            si = int(slot_index)
        except (TypeError, ValueError):
            si = 0
        if si < 0 or si >= n:
            si = max(0, min(si, n - 1))
        out = dict(acc)
        out["barcode_tokens"] = [copy.deepcopy(valid_rows[si])]
        out.pop("secure_token_b64", None)
        return out
    if (acc.get("secure_token_b64") or "").strip() and slot_index == 0:
        return acc
    return acc


def _tm_home_search_strip_markup() -> str:
    """Decorative TM-style segmented search row (homepage only)."""
    pin = (
        '<svg class="tm-sico" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        '<path d="M12 11.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z" stroke="currentColor" stroke-width="2"/>'
        '<path d="M12 21s7-4.35 7-10a7 7 0 1 0-14 0c0 5.65 7 10 7 10Z" stroke="currentColor" stroke-width="2"/>'
        "</svg>"
    )
    cal = (
        '<svg class="tm-sico" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        '<rect x="3" y="5" width="18" height="16" rx="2" stroke="currentColor" stroke-width="2"/>'
        '<path d="M3 10h18M8 3v4M16 3v4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
        "</svg>"
    )
    mag = (
        '<svg class="tm-sico" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        '<circle cx="10.5" cy="10.5" r="6.5" stroke="currentColor" stroke-width="2"/>'
        '<path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
        "</svg>"
    )
    return (
        '<div class="tm-search-strip-wrap">'
        '<div class="tm-search-strip" role="presentation">'
        f'<div class="tm-search-seg">{pin}'
        '<span class="tm-slab">Location</span>'
        '<span class="tm-sval">City or Zip Code</span></div>'
        f'<div class="tm-search-seg">{cal}'
        '<span class="tm-slab">Date</span>'
        '<span class="tm-sval">All Dates</span></div>'
        f'<div class="tm-search-seg tm-search-seg--grow">{mag}'
        '<span class="tm-slab">Search</span>'
        '<span class="tm-sval">Artist, Event or Venue</span></div>'
        '<button type="button" class="tm-search-go" tabindex="-1" disabled aria-hidden="true">'
        '<svg class="tm-search-go-ico" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="10.5" cy="10.5" r="6.5" stroke="currentColor" stroke-width="2"/>'
        '<path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
        "</svg><span class=\"tm-sr-only\">Search</span></button>"
        "</div></div>"
    )


# Same-origin login page (OTP). Override TM_VIEWER_LOGIN_URL for a different path or external URL.
_DEFAULT_TM_LOGIN_URL = "/login"
# Dedicated ticket list page (clean URL; file on disk my-tickets.html with Vercel cleanUrls).
_DEFAULT_TM_MY_TICKETS_URL = "/my-tickets"

# Inline on viewer pages: persist sign-in in localStorage (sessionStorage was tab-scoped / lost easily).
_TM_VIEWER_AUTH_STORAGE_JS = (
    "  var TOKEN_KEY = 'tm_viewer_session_token';\n"
    "  var EMAIL_KEY = 'tm_viewer_session_email';\n"
    "  function authStore() {\n"
    "    try {\n"
    "      var z = '__tm_vs';\n"
    "      localStorage.setItem(z, '1');\n"
    "      localStorage.removeItem(z);\n"
    "      return localStorage;\n"
    "    } catch (e0) {\n"
    "      try { return sessionStorage; } catch (e1) { return null; }\n"
    "    }\n"
    "  }\n"
    "  var AUTH = authStore();\n"
    "  function migrateLegacyViewerSession() {\n"
    "    if (AUTH !== localStorage) return;\n"
    "    try {\n"
    "      var t = sessionStorage.getItem(TOKEN_KEY);\n"
    "      var em0 = sessionStorage.getItem(EMAIL_KEY);\n"
    "      if (t) {\n"
    "        try {\n"
    "          localStorage.setItem(TOKEN_KEY, t);\n"
    "          sessionStorage.removeItem(TOKEN_KEY);\n"
    "        } catch (eL) {}\n"
    "      }\n"
    "      if (em0) {\n"
    "        try {\n"
    "          localStorage.setItem(EMAIL_KEY, em0);\n"
    "          sessionStorage.removeItem(EMAIL_KEY);\n"
    "        } catch (eM) {}\n"
    "      }\n"
    "    } catch (e2) {}\n"
    "  }\n"
    "  migrateLegacyViewerSession();\n"
    "  function authGet(k) {\n"
    "    if (!AUTH) return null;\n"
    "    try { return AUTH.getItem(k); } catch (e) { return null; }\n"
    "  }\n"
    "  function authSet(k, v) {\n"
    "    if (!AUTH) return;\n"
    "    try {\n"
    "      if (v == null || v === '') AUTH.removeItem(k);\n"
    "      else AUTH.setItem(k, v);\n"
    "    } catch (e) {}\n"
    "  }\n"
    "  function authClearViewer() {\n"
    "    [TOKEN_KEY, EMAIL_KEY].forEach(function (key) {\n"
    "      try { localStorage.removeItem(key); } catch (e0) {}\n"
    "      try { sessionStorage.removeItem(key); } catch (e1) {}\n"
    "    });\n"
    "  }\n"
)


def _tm_viewer_login_url_js_contents(login_url: str) -> str:
    u = (login_url or "").strip() or _DEFAULT_TM_LOGIN_URL
    return (
        "/* Vercel: set TM_VIEWER_LOGIN_URL at build. Or edit the string below. */\n"
        f"window.TM_VIEWER_LOGIN_URL = {json.dumps(u)};\n"
    )


def _tm_viewer_api_base_js_contents(api_base: str) -> str:
    u = (api_base or "").strip().rstrip("/")
    return (
        "/* Vercel: set TM_VIEWER_PUBLIC_API (registry server, e.g. https://host:3919). No trailing slash. */\n"
        f"window.TM_VIEWER_API_BASE = {json.dumps(u)};\n"
    )


def _tm_viewer_mail_api_base_js_contents(mail_base: str) -> str:
    u = (mail_base or "").strip().rstrip("/")
    return (
        "/* Stubby TM viewer proxy (e.g. http://VPS:9440). Env TM_VIEWER_MAIL_API_BASE at build. "
        "Empty = use TM_VIEWER_API_BASE. */\n"
        f"window.TM_VIEWER_MAIL_API_BASE = {json.dumps(u)};\n"
    )


def _tm_viewer_ticket_list_block(login_url_baked: str, *, standalone: bool = False) -> str:
    """Sign-in gate + ticket grid (API session). Embedded on home, or full page when standalone."""
    url = (login_url_baked or "").strip() or _DEFAULT_TM_LOGIN_URL
    baked_js = json.dumps(url)
    wrap_open = ""
    wrap_close = ""
    if standalone:
        wrap_open = (
            '<div class="tm-my-tickets-page">'
            '<nav class="tm-my-tickets-nav" aria-label="Breadcrumb">'
            '<a class="tm-my-tickets-crumb" href="/">Home</a>'
            '<span class="tm-my-tickets-crumb-sep" aria-hidden="true">/</span>'
            '<span class="tm-my-tickets-crumb-here">My tickets</span>'
            "</nav>"
            '<h1 class="tm-my-tickets-title">My tickets</h1>'
        )
        wrap_close = "</div>"
    sec_aria = "My tickets" if standalone else "Sign in"
    return (
        f"{wrap_open}"
        f'<section id="tm-ticket-list" class="tm-ticket-list-section tm-login-gate-section" aria-label="{_escape(sec_aria)}">'
        '<h2 class="tm-section-heading">Sign in required</h2>'
        '<div id="tm-home-login-teaser">'
        '<p class="tm-login-gate-lead">You need to sign in before your passes can be shown on this page.</p>'
        '<p class="tm-email-hint tm-login-gate-hint">Use the button below to open the sign-in page. After you sign in, '
        "your passes will appear here.</p>"
        '<p class="tm-login-gate-actions">'
        f'<a class="tm-login-gate-cta" id="tm-login-redirect" href="{_escape(url)}">Sign in</a>'
        "</p>"
        "</div>"
        '<div id="tm-viewer-ticket-grid" class="tm-ticket-grid" hidden></div>'
        '<div id="tm-viewer-empty-tickets" class="tm-viewer-empty-tickets" hidden>'
        "<p>You&rsquo;re signed in. There are no passes linked to this email yet. "
        "If you just ordered, they may appear after delivery updates.</p>"
        "</div>"
        "</section>"
        '<script src="/tm_viewer_api_base.js"></script>\n'
        '<script src="/tm_viewer_login_url.js"></script>\n'
        "<script>\n"
        "(function () {\n"
        f"  var BAKED = {baked_js};\n"
        f"{_TM_VIEWER_AUTH_STORAGE_JS}"
        "  function loginUrl() {\n"
        "    var u = typeof window.TM_VIEWER_LOGIN_URL === 'string' ? window.TM_VIEWER_LOGIN_URL.trim() : '';\n"
        "    return u || BAKED;\n"
        "  }\n"
        "  function apiBase() {\n"
        "    var b = typeof window.TM_VIEWER_API_BASE === 'string' ? window.TM_VIEWER_API_BASE.trim() : '';\n"
        "    b = b ? b.replace(/\\/+$/, '') : '';\n"
        "    if (b) return b;\n"
        "    try {\n"
        "      if (typeof window.location !== 'undefined' && window.location.origin)\n"
        "        return String(window.location.origin).replace(/\\/+$/, '');\n"
        "    } catch (e0) {}\n"
        "    return '';\n"
        "  }\n"
        "  function goLogin(ev) {\n"
        "    if (ev) ev.preventDefault();\n"
        "    var u = loginUrl();\n"
        "    if (!u) return;\n"
        "    if (u.charAt(0) === '#') {\n"
        "      var id = u.slice(1);\n"
        "      var el = id ? document.getElementById(id) : null;\n"
        "      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });\n"
        "      else { try { location.hash = u; } catch (e1) {} }\n"
        "      return;\n"
        "    }\n"
        "    window.location.href = u;\n"
        "  }\n"
        "  function escHtml(s) {\n"
        "    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;');\n"
        "  }\n"
        "  function escAttr(s) {\n"
        "    return String(s).replace(/&/g,'&amp;').replace(/\"/g,'&quot;').replace(/</g,'&lt;');\n"
        "  }\n"
        "  function applySignedInChrome(email) {\n"
        "    var guest = document.getElementById('tm-topbar-guest');\n"
        "    var signed = document.getElementById('tm-topbar-signed');\n"
        "    if (guest) guest.hidden = true;\n"
        "    if (signed) signed.hidden = false;\n"
        "    var em = (email || '').trim();\n"
        "    if (!em) {\n"
        "      try { em = (authGet(EMAIL_KEY) || '').trim(); } catch (e4) { em = ''; }\n"
        "    }\n"
        "    if (em) {\n"
        "      try { authSet(EMAIL_KEY, em); } catch (e5) {}\n"
        "    }\n"
        "    var label = document.getElementById('tm-topbar-account-label');\n"
        "    var fullEl = document.getElementById('tm-account-menu-email');\n"
        "    var at = em.indexOf('@');\n"
        "    var short = at > 0 ? em.slice(0, at) : (em || 'Account');\n"
        "    if (short.length > 14) short = short.slice(0, 13) + '\\u2026';\n"
        "    if (label) label.textContent = short;\n"
        "    if (fullEl) fullEl.textContent = em || '';\n"
        "  }\n"
        "  function fillTicketGrid(tickets) {\n"
        "    var gridHost = document.getElementById('tm-viewer-ticket-grid');\n"
        "    if (!gridHost) return;\n"
        "    var html = '';\n"
        "    for (var i = 0; i < tickets.length; i++) {\n"
        "      var t = tickets[i];\n"
        "      var path = String((t && t.path) || '').replace(/^\\/+/, '');\n"
        "      if (path.toLowerCase().endsWith('.html')) path = path.slice(0, -5);\n"
        "      if (!path) continue;\n"
        "      html += '<a class=\"tm-ticket-tile tm-ticket-tile--loaded\" href=\"' + escAttr(path) + '\">' +\n"
        "        '<div class=\"tm-tile-ev\">' + escHtml((t && t.event_name) || 'Ticket') + '</div>' +\n"
        "        '<div class=\"tm-tile-meta\">' + escHtml((t && t.subtitle) || '') + '</div>' +\n"
        "        '<div class=\"tm-tile-seat\">Sec ' + escHtml(String((t && t.section) || '')) +\n"
        "        ' · Row ' + escHtml(String((t && t.row) || '')) +\n"
        "        ' · Seat ' + escHtml(String((t && t.seat) || '')) + '</div>' +\n"
        "        '<span class=\"tm-tile-cta\">VIEW TICKET</span></a>';\n"
        "    }\n"
        "    gridHost.innerHTML = html;\n"
        "    gridHost.hidden = html.length === 0;\n"
        "  }\n"
        "  function applySignedInHome(email, tickets) {\n"
        "    var list = tickets || [];\n"
        "    applySignedInChrome(email);\n"
        "    var teaser = document.getElementById('tm-home-login-teaser');\n"
        "    var h2 = document.querySelector('#tm-ticket-list > .tm-section-heading');\n"
        "    var emptyEl = document.getElementById('tm-viewer-empty-tickets');\n"
        "    if (teaser) teaser.hidden = true;\n"
        "    if (h2) h2.textContent = 'Your tickets';\n"
        "    if (list.length) {\n"
        "      if (emptyEl) emptyEl.hidden = true;\n"
        "      fillTicketGrid(list);\n"
        "    } else {\n"
        "      fillTicketGrid([]);\n"
        "      if (emptyEl) emptyEl.hidden = false;\n"
        "    }\n"
        "  }\n"
        "  function tryRestore() {\n"
        "    var base = apiBase();\n"
        "    if (!base) return;\n"
        "    var tok;\n"
        "    try { tok = authGet(TOKEN_KEY); } catch (e3) { tok = null; }\n"
        "    if (!tok) return;\n"
        "    fetch(base + '/api/tm-viewer/tickets?token=' + encodeURIComponent(tok), {\n"
        "      credentials: 'omit',\n"
        "      cache: 'no-store',\n"
        "    })\n"
        "      .then(function (r) {\n"
        "        return r.text().then(function (text) {\n"
        "          var data = null;\n"
        "          try {\n"
        "            data = text ? JSON.parse(text) : null;\n"
        "          } catch (eJ) {\n"
        "            data = null;\n"
        "          }\n"
        "          return { status: r.status, data: data };\n"
        "        });\n"
        "      })\n"
        "      .then(function (packed) {\n"
        "        var data = packed.data;\n"
        "        if (!data || !data.ok) {\n"
        "          if (packed.status === 401 && data && data.error === 'auth_required') {\n"
        "            try { authSet(TOKEN_KEY, ''); } catch (eCA) {}\n"
        "          }\n"
        "          return;\n"
        "        }\n"
        "        var em = (data.email || '').trim();\n"
        "        applySignedInHome(em, data.tickets || []);\n"
        "      })\n"
        "      .catch(function () {});\n"
        "  }\n"
        "  tryRestore();\n"
        "  var cta = document.getElementById('tm-login-redirect');\n"
        "  if (cta) {\n"
        "    cta.addEventListener('click', function (e) {\n"
        "      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;\n"
        "      goLogin(e);\n"
        "    });\n"
        "  }\n"
        "  var topLogin = document.getElementById('tm-topbar-login');\n"
        "  if (topLogin) {\n"
        "    topLogin.addEventListener('click', function (e) {\n"
        "      e.preventDefault();\n"
        "      goLogin(null);\n"
        "    });\n"
        "  }\n"
        "  var menuBtn = document.getElementById('tm-topbar-account-btn');\n"
        "  var menu = document.getElementById('tm-account-menu');\n"
        "  if (menuBtn && menu) {\n"
        "    menuBtn.addEventListener('click', function (e) {\n"
        "      e.stopPropagation();\n"
        "      var open = menu.hidden;\n"
        "      menu.hidden = !open;\n"
        "      menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');\n"
        "    });\n"
        "    document.addEventListener('click', function () {\n"
        "      if (!menu.hidden) {\n"
        "        menu.hidden = true;\n"
        "        menuBtn.setAttribute('aria-expanded', 'false');\n"
        "      }\n"
        "    });\n"
        "    menu.addEventListener('click', function (e) { e.stopPropagation(); });\n"
        "  }\n"
        "  var myTix = document.getElementById('tm-menu-my-tickets');\n"
        "  if (myTix && menu) {\n"
        "    myTix.addEventListener('click', function () {\n"
        "      menu.hidden = true;\n"
        "      if (menuBtn) menuBtn.setAttribute('aria-expanded', 'false');\n"
        "    });\n"
        "  }\n"
        "  var signOut = document.getElementById('tm-menu-sign-out');\n"
        "  if (signOut) {\n"
        "    signOut.addEventListener('click', function () {\n"
        "      try { authClearViewer(); } catch (e6) {}\n"
        "      location.reload();\n"
        "    });\n"
        "  }\n"
        "})();\n"
        "</script>"
        f"{wrap_close}"
    )


def _tm_viewer_login_page_block(*, after_login_url: str = "") -> str:
    """Standalone login page (login.html on disk): email + OTP; redirect after success."""
    dest = (after_login_url or "").strip() or _DEFAULT_TM_MY_TICKETS_URL
    dest_js = json.dumps(dest)
    return (
        '<div class="tm-login-page-inner" style="max-width:640px;margin:0 auto;padding:1.5rem 1rem 2.5rem">'
        '<section class="tm-ticket-list-section tm-login-gate-section" aria-label="Sign in">'
        '<h2 class="tm-section-heading">Sign in</h2>'
        '<p class="tm-login-gate-lead">Enter the email on your ticket order. We will send a one-time code to that address.</p>'
        '<div id="tm-viewer-auth" class="tm-email-gate">'
        '<div class="tm-email-row">'
        '<input type="email" id="tm-viewer-email" name="email" autocomplete="email" placeholder="Email address" />'
        '<button type="button" id="tm-viewer-send-otp">Send code</button>'
        "</div>"
        '<div id="tm-otp-row" class="tm-otp-row" hidden>'
        '<div class="tm-email-row">'
        '<input type="text" id="tm-viewer-otp" inputmode="numeric" pattern="[0-9]*" '
        'maxlength="12" autocomplete="one-time-code" placeholder="6-digit code" />'
        '<button type="button" id="tm-viewer-verify-otp">Verify</button>'
        "</div></div>"
        '<p id="tm-viewer-auth-status" class="tm-email-hint" role="status" style="margin-top:0.75rem"></p>'
        '<p class="tm-muted-inline" style="margin-top:1rem"><a href="/">Back to home</a></p>'
        "</div>"
        "</section></div>"
        '<script src="/tm_viewer_api_base.js"></script>\n'
        "<script>\n"
        "(function () {\n"
        f"{_TM_VIEWER_AUTH_STORAGE_JS}"
        f"  var AFTER_LOGIN_URL = {dest_js};\n"
        "  try {\n"
        "    var _tRedir = authGet(TOKEN_KEY);\n"
        "    if (_tRedir && String(_tRedir).trim()) {\n"
        "      window.location.replace(AFTER_LOGIN_URL);\n"
        "      return;\n"
        "    }\n"
        "  } catch (eRedir) {}\n"
        "  function apiBase() {\n"
        "    var b = typeof window.TM_VIEWER_API_BASE === 'string' ? window.TM_VIEWER_API_BASE.trim() : '';\n"
        "    b = b ? b.replace(/\\/+$/, '') : '';\n"
        "    if (b) return b;\n"
        "    try {\n"
        "      if (typeof window.location !== 'undefined' && window.location.origin)\n"
        "        return String(window.location.origin).replace(/\\/+$/, '');\n"
        "    } catch (e0) {}\n"
        "    return '';\n"
        "  }\n"
        "  function setStatus(msg, isErr) {\n"
        "    var el = document.getElementById('tm-viewer-auth-status');\n"
        "    if (!el) return;\n"
        "    el.textContent = msg || '';\n"
        "    el.style.color = isErr ? '#b91c1c' : '';\n"
        "  }\n"
        "  function mapErr(data) {\n"
        "    if (!data || typeof data !== 'object') return 'Something went wrong.';\n"
        "    var e = data.error;\n"
        "    if (e === 'no_tickets') return 'No tickets found for this email.';\n"
        "    if (e === 'invalid_email') return 'Enter a valid email address.';\n"
        "    if (e === 'rate_limit') return 'Please wait before requesting another code.';\n"
        "    if (e === 'send_failed') return 'Could not send email. Try again later.';\n"
        "    if (e === 'code_expired') return 'Code expired. Request a new one.';\n"
        "    if (e === 'bad_code') return 'Incorrect code. Try again.';\n"
        "    if (e === 'too_many_attempts') return 'Too many attempts. Request a new code.';\n"
        "    if (e === 'proxy_misconfigured') return 'Server missing TM_VIEWER_BACKEND_URL (Vercel env).';\n"
        "    if (e === 'upstream_unreachable') return 'Vercel cannot reach your registry. Check IP, port 3919, firewall.';\n"
        "    return (data.detail && String(data.detail).slice(0, 200)) || 'Something went wrong.';\n"
        "  }\n"
        "  var btnSend = document.getElementById('tm-viewer-send-otp');\n"
        "  var btnVerify = document.getElementById('tm-viewer-verify-otp');\n"
        "  var otpRow = document.getElementById('tm-otp-row');\n"
        "  if (btnSend) {\n"
        "    btnSend.addEventListener('click', function () {\n"
        "      setStatus('');\n"
        "      var base = apiBase();\n"
        "      if (!base) {\n"
        "        setStatus('Open this page from your live site (HTTPS), not as a local file.', true);\n"
        "        return;\n"
        "      }\n"
        "      var inp = document.getElementById('tm-viewer-email');\n"
        "      var email = ((inp && inp.value) || '').trim().toLowerCase();\n"
        "      if (!email || email.indexOf('@') < 0) {\n"
        "        setStatus('Enter the email on your ticket order.', true);\n"
        "        return;\n"
        "      }\n"
        "      btnSend.disabled = true;\n"
        "      fetch(base + '/api/tm-viewer/auth/send-otp', {\n"
        "        method: 'POST',\n"
        "        headers: { 'Content-Type': 'application/json' },\n"
        "        body: JSON.stringify({ email: email })\n"
        "      })\n"
        "        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, status: r.status, j: j }; }); })\n"
        "        .then(function (x) {\n"
        "          btnSend.disabled = false;\n"
        "          if (x.j && x.j.ok) {\n"
        "            if (otpRow) otpRow.hidden = false;\n"
        "            setStatus('Check your email for the code.');\n"
        "            var op = document.getElementById('tm-viewer-otp');\n"
        "            if (op) op.focus();\n"
        "            return;\n"
        "          }\n"
        "          if (x.status === 429 && x.j && x.j.retry_after_sec)\n"
        "            setStatus('Wait ' + x.j.retry_after_sec + 's before another code.', true);\n"
        "          else setStatus(mapErr(x.j), true);\n"
        "        })\n"
        "        .catch(function () {\n"
        "          btnSend.disabled = false;\n"
        "          setStatus('Network error. Is the registry API reachable (HTTPS)?', true);\n"
        "        });\n"
        "    });\n"
        "  }\n"
        "  if (btnVerify) {\n"
        "    btnVerify.addEventListener('click', function () {\n"
        "      setStatus('');\n"
        "      var base = apiBase();\n"
        "      if (!base) return;\n"
        "      var inp = document.getElementById('tm-viewer-email');\n"
        "      var email = ((inp && inp.value) || '').trim().toLowerCase();\n"
        "      var op = document.getElementById('tm-viewer-otp');\n"
        "      var code = ((op && op.value) || '').trim().replace(/\\s/g, '');\n"
        "      if (!code) {\n"
        "        setStatus('Enter the code from your email.', true);\n"
        "        return;\n"
        "      }\n"
        "      btnVerify.disabled = true;\n"
        "      fetch(base + '/api/tm-viewer/auth/verify-otp', {\n"
        "        method: 'POST',\n"
        "        headers: { 'Content-Type': 'application/json' },\n"
        "        body: JSON.stringify({ email: email, code: code })\n"
        "      })\n"
        "        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })\n"
        "        .then(function (x) {\n"
        "          btnVerify.disabled = false;\n"
        "          if (!(x.j && x.j.ok && x.j.token)) {\n"
        "            setStatus(mapErr(x.j), true);\n"
        "            return;\n"
        "          }\n"
        "          try { authSet(TOKEN_KEY, x.j.token); } catch (e2) {}\n"
        "          try {\n"
        "            var emStore = ((x.j && x.j.email) || email || '').trim().toLowerCase();\n"
        "            if (emStore) authSet(EMAIL_KEY, emStore);\n"
        "          } catch (e7) {}\n"
        "          setStatus('Signed in. Redirecting...');\n"
        f"          window.location.href = {dest_js};\n"
        "        })\n"
        "        .catch(function () {\n"
        "          btnVerify.disabled = false;\n"
        "          setStatus('Network error.', true);\n"
        "        });\n"
        "    });\n"
        "  }\n"
        "  var topLogin = document.getElementById('tm-topbar-login');\n"
        "  if (topLogin) {\n"
        "    topLogin.addEventListener('click', function (e) {\n"
        "      e.preventDefault();\n"
        "      var em = document.getElementById('tm-viewer-email');\n"
        "      if (em) em.focus();\n"
        "    });\n"
        "  }\n"
        "})();\n"
        "</script>"
    )


def _html_pass_pager(nav: dict) -> tuple[str, str]:
    """Return (mid-stage prev/next nav HTML, 'All tickets' link below the card)."""
    prev = nav.get("prev") or ""
    home = nav.get("home") or "/"
    nxt = nav.get("next") or ""
    prev_arrow = _TM_CAROUSEL_ARROW_L.replace("tm-carousel-arrow-svg", "tm-pass-dir-svg")
    next_arrow = _TM_CAROUSEL_ARROW_R.replace("tm-carousel-arrow-svg", "tm-pass-dir-svg")
    if prev:
        prev_el = (
            f'<a class="tm-pass-dir tm-pass-dir--prev tm-pass-dir--frost" href="{_escape(prev)}">'
            f'<span class="tm-sr-only">Previous ticket</span>{prev_arrow}</a>'
        )
    else:
        prev_el = (
            f'<span class="tm-pass-dir tm-pass-dir--prev tm-pass-dir--frost tm-pass-dir--disabled" aria-hidden="true">'
            f"{prev_arrow}</span>"
        )
    if nxt:
        next_el = (
            f'<a class="tm-pass-dir tm-pass-dir--next tm-pass-dir--frost" href="{_escape(nxt)}">'
            f'<span class="tm-sr-only">Next ticket</span>{next_arrow}</a>'
        )
    else:
        next_el = (
            f'<span class="tm-pass-dir tm-pass-dir--next tm-pass-dir--frost tm-pass-dir--disabled" aria-hidden="true">'
            f"{next_arrow}</span>"
        )
    mid = (
        f'<nav class="tm-pass-pager tm-pass-pager--card-mid" aria-label="Adjacent tickets">'
        f"{prev_el}{next_el}</nav>"
    )
    home_el = (
        f'<a class="tm-pass-pager__home tm-pass-pager__home--below" href="{_escape(home)}">All tickets</a>'
    )
    return mid, home_el


def _html_barcode_section(
    acc: dict,
    idx: int,
    *,
    only_sub: int | None = None,
    back_href: str | None = None,
    pass_nav: dict | None = None,
    relative_asset_prefix: str = "",
    debug_ticket_file: str = "",
    debug_site_root: Path | None = None,
    viewer_transfer_relpath: str = "",
    safetix_cfg_b64_override: str | None = None,
    wallet_built: tuple[int, str] | None = None,
) -> str:
    """TM-style mobile pass cards + rotating PDF417 (merged tickets and/or inline SecureToken)."""
    slots = _collect_barcode_slots(acc)

    if not slots:
        return (
            "<p class='muted'>No rotating barcode for this account. TM needs <code>Secure Token:</code> "
            "(<code>t</code>/<code>ck</code>/<code>ek</code>); SeatGeek needs <code>OTP Secret</code> + "
            "<code>Barcode Value</code> with <code>Platform: SG</code>.</p>"
            "<p class='muted'>Use: <code>python tm_hit_viewer.py your_hit.txt --tickets tickets.txt</code> "
            "(checker <code>tickets.txt</code> or <code>sg_tickets.txt</code> from <code>sg_tickets_capture.py</code>).</p>"
        )

    if only_sub is not None and (only_sub < 0 or only_sub >= len(slots)):
        return "<p class='muted'>Ticket not found.</p>"

    upcoming = acc.get("upcoming") or []
    slide_parts: list[str] = []
    for sub, (cfg_b64, label, is_demo, row) in enumerate(slots):
        if only_sub is not None and sub != only_sub:
            continue
        eff_cfg = safetix_cfg_b64_override if safetix_cfg_b64_override is not None else cfg_b64
        r = dict(row)
        r.setdefault("label", label)
        f = _ticket_card_fields(r, upcoming)
        warn = ""
        if is_demo:
            warn = (
                '<p class="tm-pass-warn">Demo / test token — not valid for venue entry.</p>'
            )
        cid = f"{idx}-{sub}"
        is_sg = bool(r.get("sg_barcode"))
        bc_cls = "barcode-frame tm-pass-bc" + (" tm-pass-bc--sg" if is_sg else "")
        remote_u = (f.get("image_url_remote") or "").strip()
        local_u = (f["image_url"] or "").strip()
        iu, hero_fb = _resolve_pass_hero_img_src(
            local_u=local_u,
            remote_u=remote_u,
            relative_asset_prefix=relative_asset_prefix,
            debug_site_root=debug_site_root,
        )
        if not _pass_hero_url_safe_for_img_src(iu, site_root=debug_site_root):
            if hero_fb.startswith(("http://", "https://")):
                iu = hero_fb
                hero_fb = ""
            else:
                iu = ""
        hero_img = ""
        hero_cls = "tm-pass-hero"
        hero_style = ""
        if iu:
            fb_attr = (
                f' data-fallback="{html.escape(hero_fb, quote=True)}"' if hero_fb else ""
            )
            src_attr = iu if iu.startswith("data:") else _escape(iu)
            hero_img = (
                f'<img class="tm-pass-hero-bg" src="{src_attr}" alt="" loading="eager" '
                f'decoding="async" referrerpolicy="no-referrer"{fb_attr}{_TM_HERO_IMG_ONERROR}/>'
            )
            hero_style = ""
        else:
            hero_cls += " tm-pass-hero--grad tm-pass-hero--tmblue"
            hero_style = ""
        raw_iu_row = (f["image_url"] or "").strip()
        raw_remote = (f.get("image_url_remote") or "").strip()
        if _tm_viewer_debug_enabled():
            abp_d, ok_d = ("", False)
            if debug_site_root and local_u:
                abp_d, ok_d = _tm_viewer_debug_resolve_asset(debug_site_root, local_u)
            _tm_viewer_debug_log(
                f"HTML hero ticket={debug_ticket_file or 'multi'} idx={idx} sub={sub} "
                f"event={(f.get('event_name') or '')[:55]!r} raw_row_local={raw_iu_row[:120]!r} "
                f"raw_remote={raw_remote[:120]!r} prefer_local={_tm_viewer_hero_prefer_local_files()} "
                f"src_in_html={iu[:120]!r} embedded={'data:' in (iu or '')} "
                f"mode={'IMG' if hero_img else 'GRADIENT'} "
                f"site_root_file={abp_d!r} exists={ok_d}"
            )
        hero_watermark = ""
        if not hero_img:
            hero_watermark = (
                '<div class="tm-pass-hero-watermark" aria-hidden="true">'
                f'<img src="{_TM_WORDMARK_WIKIMEDIA_SVG}" alt="" width="280" height="44" '
                'loading="lazy" decoding="async" referrerpolicy="no-referrer"/>'
                "</div>"
            )
        gate_html = (
            f'<div class="tm-pass-gate">{_escape(f["gate"].upper())}</div>'
            if f["gate"]
            else ""
        )
        wallet_href = ""
        if wallet_built is not None:
            wallet_href = (
                _tm_wallet_signed_pkpass_href(
                    gid=wallet_built[0], fname=wallet_built[1], fields=f
                )
                or ""
            )
        if not wallet_href and _viewer_pkpass_url_allowed(f["pkpass_url"]):
            wallet_href = f["pkpass_url"]
        if wallet_href:
            wallet_btn = (
                f'<a class="tm-pass-btn tm-pass-wallet tm-pass-wallet--badge" href="{_escape(wallet_href)}">'
                f"{_tm_wallet_badge_markup()}</a>"
            )
        else:
            wallet_btn = (
                f'<span class="tm-pass-btn tm-pass-wallet tm-pass-wallet--badge tm-pass-btn--disabled">'
                f"{_tm_wallet_badge_markup()}</span>"
            )
        if f["order_url"]:
            info_btn = (
                f'<a class="tm-pass-btn tm-pass-info" href="{_escape(f["order_url"])}" '
                f'target="_blank" rel="noopener noreferrer">'
                f'<span class="tm-pass-info-ico" aria-hidden="true">i</span>'
                f'<span class="tm-pass-info-label">Ticket info</span></a>'
            )
        else:
            info_btn = (
                '<span class="tm-pass-btn tm-pass-info tm-pass-info--muted tm-pass-btn--ghost">'
                '<span class="tm-pass-info-ico" aria-hidden="true">i</span>'
                '<span class="tm-pass-info-label">Ticket info</span></span>'
            )
        transfer_btn = ""
        if (viewer_transfer_relpath or "").strip():
            transfer_btn = (
                '<button type="button" class="tm-pass-btn tm-pass-transfer tm-pass-transfer-open" '
                'aria-label="Transfer to buyer">'
                '<span class="tm-pass-transfer-stack">'
                '<span class="tm-pass-transfer-label">Transfer</span>'
                "</span></button>"
            )
        if back_href:
            menu_el = (
                f'<a class="tm-pass-menu" href="{_escape(back_href)}" aria-label="Back to tickets">'
                f"{_TM_PASS_MENU_ICON}</a>"
            )
        else:
            menu_el = (
                '<button type="button" class="tm-pass-menu" onclick="history.back();" aria-label="Back">'
                f"{_TM_PASS_MENU_ICON}</button>"
            )
        slide_parts.append(
            f'<div class="tm-carousel-slide">'
            f"{warn}"
            f'<div class="safetix-slot tm-pass-card" id="pass-{cid}">'
            f'<div class="tm-pass-rail" aria-hidden="true"></div>'
            f'<div class="tm-pass-brand-strip" aria-hidden="true">'
            f'<img src="{_TM_WORDMARK_WIKIMEDIA_SVG}" alt="" width="120" height="20" '
            f'loading="eager" decoding="async" referrerpolicy="no-referrer"/></div>'
            f'<div class="tm-pass-head">'
            f"{menu_el}"
            f'<div class="tm-pass-head-center">'
            f'<h4 class="tm-pass-title">{_escape(f["event_name"])}</h4>'
            f'<p class="tm-pass-sub">{_tm_pass_subtitle_lines_html(f["subtitle"])}</p>'
            f'</div><span class="tm-pass-head-spacer" aria-hidden="true"></span></div>'
            f'<div class="tm-pass-visual tm-pass-visual--overlay">'
            f'<div class="{hero_cls} tm-pass-hero--cover"{(f" {hero_style}") if hero_style else ""}>'
            f"{hero_watermark}{hero_img}"
            f'<div class="tm-pass-hero-fx" aria-hidden="true"></div>'
            f'<div class="tm-pass-hero-shade tm-pass-hero-shade--soft" aria-hidden="true"></div>'
            f'<div class="tm-pass-bar-sheet">'
            f'<div class="tm-pass-screen-row">'
            f"<span>Screenshots won&apos;t get you in</span>"
            f"{_TM_PASS_PHONE_ALERT_ICON}"
            f'<button type="button" class="tm-pass-refresh-btn" aria-label="Refresh barcode">'
            f'<span class="tm-pass-refresh-btn__ico" aria-hidden="true">↻</span>'
            f'<span class="tm-pass-refresh-btn__label">Refresh barcode</span>'
            f'<span class="tm-pass-refresh-btn__sec" aria-live="polite">—</span>'
            f"</button>"
            f"</div>"
            f'<div class="{bc_cls}" data-tm-safetix="{html.escape(eff_cfg, quote=True)}">'
            f'<canvas class="safetix-canvas" id="safetix-canvas-{cid}" width="2" height="2"></canvas>'
            f'<div class="tm-scan-line" aria-hidden="true"></div>'
            f'<div class="tm-scan-glow" aria-hidden="true"></div>'
            f"</div>"
            f'<p class="safetix-status tm-pass-status" id="safetix-status-{cid}" '
            f'aria-live="polite"></p>'
            f"</div></div></div>"
            f'<div class="tm-pass-body">'
            f'<div class="tm-pass-type-block">'
            f'<strong class="tm-pass-kind">{_escape(f["ticket_kind"])}</strong>'
            f'<div class="tm-pass-verified-row">{_TM_VERIFIED_CHECK_SVG}'
            f'<span class="tm-pass-verified-txt">Verified Ticket</span></div>'
            f"{_tm_pass_type_detail_html(f['ticket_type'])}"
            f"</div>"
            f'<div class="tm-pass-seats">'
            f'<div><span class="tm-pass-lbl">SECTION</span><b>{_escape(f["section"])}</b></div>'
            f'<div><span class="tm-pass-lbl">ROW</span><b>{_escape(f["row"])}</b></div>'
            f'<div><span class="tm-pass-lbl">SEAT</span><b>{_escape(f["seat"])}</b></div>'
            f"</div>"
            f"{gate_html}"
            f'<div class="tm-pass-actions">{wallet_btn}{info_btn}{transfer_btn}</div>'
            f"</div></div>"
            f"</div>"
        )
    n_slides = len(slide_parts)
    # No peek mode: full-width slides only (avoids wide track + horizontal scrollbar UI).
    carousel_mod = " tm-ticket-carousel--single" if n_slides == 1 else ""
    # Inset barcode sheet when frost arrows show so they don't cover the PDF417.
    side_nav_cls = ""
    nav_html = ""
    counter_html = ""
    if n_slides > 1:
        nav_html = (
            '<button type="button" class="tm-carousel-arrow tm-carousel-prev tm-carousel-arrow--frost" '
            f'aria-label="Previous ticket">{_TM_CAROUSEL_ARROW_L}</button>'
            '<button type="button" class="tm-carousel-arrow tm-carousel-next tm-carousel-arrow--frost" '
            f'aria-label="Next ticket">{_TM_CAROUSEL_ARROW_R}</button>'
        )
        counter_html = (
            f'<div class="tm-carousel-counter" role="status" aria-live="polite">'
            f'<span class="tm-carousel-counter__n">1 of {n_slides}</span></div>'
        )
    track_inner = "".join(slide_parts)
    pager_mid, pager_home = ("", "")
    if pass_nav:
        pager_mid, pager_home = _html_pass_pager(pass_nav)
    elif back_href:
        pager_home = (
            f'<a class="tm-pass-pager__home tm-pass-pager__home--below" href="{_escape(back_href)}">'
            "All tickets</a>"
        )
    if n_slides > 1 or pass_nav:
        side_nav_cls = " tm-ticket-carousel--side-nav"
    return (
        f'<div class="tm-pass-viewport-fit" aria-hidden="false">'
        f'<div class="tm-pass-viewport-fit-inner">'
        f'<div class="tm-ticket-carousel{carousel_mod}{side_nav_cls}" id="tcar-{idx}" data-slides="{n_slides}">'
        f'<div class="tm-carousel-stage">'
        f'<div class="tm-carousel-viewport"><div class="tm-carousel-track">{track_inner}</div></div>'
        f"{nav_html}"
        f"{pager_mid}"
        f"</div>"
        f"{counter_html}"
        f"{pager_home}"
        f"</div></div></div>"
    )


def _render_account(acc: dict, idx: int, **barcode_kw) -> str:
    """Ticket-style layout only (no account email/password/cookies/raw export UI)."""
    barcode_inner = _html_barcode_section(acc, idx, **barcode_kw)
    return f"""
    <article class="acct acct--tickets-only" id="a{idx}">
      <section class="barcode-panel tickets-only-panel">
        {barcode_inner}
      </section>
    </article>
    """


def _safetix_live_barcode_scripts() -> str:
    """CryptoJS HMAC-SHA1 TOTP + bwip-js PDF417 (TM) or QR (SeatGeek); 15s / 30s rotation."""
    return r"""<script src="https://cdnjs.cloudflare.com/ajax/libs/crypto-js/4.2.0/crypto-js.min.js" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/bwip-js@4.5.2/dist/bwip-js-min.js" crossorigin="anonymous"></script>
<script>
(function () {
  /* TM_HIT_VIEWER_SAFETIX_RUNTIME */
  function packU64BE(counter) {
    var arr = new Uint8Array(8);
    var c = counter;
    for (var j = 7; j >= 0; j--) {
      arr[j] = c & 255;
      c = Math.floor(c / 256);
    }
    return arr;
  }
  function u8ToWordArray(u8) {
    var words = [];
    for (var i = 0; i < u8.length; i++) {
      words[i >>> 2] |= u8[i] << (24 - (i % 4) * 8);
    }
    return CryptoJS.lib.WordArray.create(words, u8.length);
  }
  function hexToKeyWA(hex) {
    var h = (hex || "").replace(/\s/g, "");
    if (h.length % 2) h = "0" + h;
    return CryptoJS.enc.Hex.parse(h);
  }
  function hotpHexKey(keyHex, counter, digits) {
    var msg = u8ToWordArray(packU64BE(counter));
    var key = hexToKeyWA(keyHex);
    var mac = CryptoJS.HmacSHA1(msg, key);
    var hex = mac.toString(CryptoJS.enc.Hex);
    var h = new Uint8Array(20);
    for (var i = 0; i < 20; i++) h[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
    var off = h[19] & 15;
    var code = ((h[off] & 127) << 24 | (h[off + 1] << 16) | (h[off + 2] << 8) | h[off + 3]) >>> 0;
    var mod = Math.pow(10, digits);
    var s = String(code % mod);
    while (s.length < digits) s = "0" + s;
    return s;
  }
  function totpHex(keyHex, unixTime, period, digits) {
    return hotpHexKey(keyHex, Math.floor(unixTime / period), digits);
  }
  function pdf417OptsForViewport() {
    var narrow = false;
    try {
      if (typeof window.matchMedia !== "undefined")
        narrow = window.matchMedia("(max-width: 639px)").matches;
    } catch (e0) {}
    /* TM iOS pass ~648×198. Compact modules so bar sheet stays ~110px tall. */
    if (narrow) return { columns: 5, scale: 8, paddingwidth: 4, paddingheight: 3 };
    return { columns: 5, scale: 8, paddingwidth: 4, paddingheight: 3 };
  }
  var TM_BARCODE_MAX_H = 110;
  function fitPdf417Canvas(canvas) {
    if (!canvas) return;
    var w = canvas.width || 0;
    var h = canvas.height || 0;
    if (w < 1 || h < 1) return;
    canvas.style.display = "block";
    canvas.style.width = "100%";
    canvas.style.maxWidth = "100%";
    canvas.style.height = "auto";
    canvas.style.maxHeight = TM_BARCODE_MAX_H + "px";
    canvas.style.aspectRatio = w + " / " + h;
    canvas.style.margin = "0 auto";
    canvas.style.imageRendering = "pixelated";
  }
  function markPassReady(slot) {
    if (slot) slot.classList.add("tm-pass-card--ready");
  }
  function markBarcodeReady(holder) {
    if (!holder) return;
    holder.classList.add("tm-pass-bc--ready");
    markPassReady(holder.closest(".safetix-slot"));
  }
  function drawPdf417(canvas, text) {
    if (typeof bwipjs === "undefined") throw new Error("bwip-js not loaded");
    var o = pdf417OptsForViewport();
    bwipjs.toCanvas(canvas, {
      bcid: "pdf417",
      text: text,
      columns: o.columns,
      scale: o.scale,
      paddingwidth: o.paddingwidth,
      paddingheight: o.paddingheight,
      backgroundcolor: "FFFFFF",
    });
    fitPdf417Canvas(canvas);
    markBarcodeReady(canvas && canvas.closest ? canvas.closest(".tm-pass-bc") : null);
  }
  function drawSgQr(canvas, text) {
    if (typeof bwipjs === "undefined") throw new Error("bwip-js not loaded");
    var narrow = false;
    try {
      if (typeof window.matchMedia !== "undefined" &&
          window.matchMedia("(max-width: 639px)").matches) narrow = true;
    } catch (e0) {}
    /* TM pass bar-sheet footprint: compact centered square (not full card width). */
    var scale = narrow ? 3 : 3;
    bwipjs.toCanvas(canvas, {
      bcid: "qrcode",
      text: text,
      scale: scale,
      paddingwidth: 4,
      paddingheight: 4,
      backgroundcolor: "FFFFFF",
    });
    try {
      var cap = narrow ? 168 : 184;
      canvas.style.width = "auto";
      canvas.style.maxWidth = cap + "px";
      canvas.style.height = "auto";
      canvas.style.display = "block";
      canvas.style.margin = "0 auto";
    } catch (e1) {}
    return Promise.resolve();
  }
  function initArticle(article) {
    article.querySelectorAll(".safetix-slot").forEach(function (slot) {
      var holder = slot.querySelector("[data-tm-safetix]");
      if (!holder) return;
      var st = holder.getAttribute("data-tm-safetix");
      if (!st) return;
      var cfg;
      try {
        cfg = JSON.parse(atob(st));
      } catch (e) {
        var bad = slot.querySelector(".safetix-status");
        if (bad) bad.textContent = "Invalid embedded SecureToken data.";
        markPassReady(slot);
        return;
      }
      var canvas = holder.querySelector("canvas");
      var statusEl = slot.querySelector(".safetix-status");
      var refreshBtn = slot.querySelector(".tm-pass-refresh-btn");
      var refreshSecEl = refreshBtn && refreshBtn.querySelector(".tm-pass-refresh-btn__sec");
      var period = cfg.period || 15;
      var digits = cfg.digits || 6;
      var isSg = cfg.platform === "sg";
      if (isSg) period = cfg.period || 30;
      var lastOtpStep = -1;
      var lastSgStep = -1;
      var remoteSkewSec = 0;
      var clockReady = true;
      var tmClockUrl = (cfg.tm_clock_url || "").trim();
      if (!tmClockUrl) {
        try {
          var _p = window.location.pathname || "";
          if (_p.indexOf("/tickets/") >= 0) tmClockUrl = "/api/tm-clock";
        } catch (ePath) {}
      }
      function skewSec() {
        if (typeof cfg.skew_sec === "number") return cfg.skew_sec;
        return tmClockUrl || cfg.sync_date ? -2 : 0;
      }
      function nowSec() {
        return Math.floor(Date.now() / 1000) + skewSec() + remoteSkewSec;
      }
      function resetDrawState() {
        lastOtpStep = -1;
        lastSgStep = -1;
      }
      function updateRefreshCountdown() {
        if (!refreshSecEl || !clockReady) return;
        var now = nowSec();
        var left = period - (now % period);
        if (left <= 0 || left > period) left = period;
        refreshSecEl.textContent = String(left);
      }
      function forceRefreshBarcode() {
        resetDrawState();
        tick();
        updateRefreshCountdown();
        if (refreshBtn) {
          refreshBtn.classList.add("tm-pass-refresh-btn--spin");
          setTimeout(function () {
            refreshBtn.classList.remove("tm-pass-refresh-btn--spin");
          }, 650);
        }
      }
      if (refreshBtn) {
        refreshBtn.addEventListener("click", function (ev) {
          ev.preventDefault();
          forceRefreshBarcode();
        });
      }
      function finishClockSync() {
        clockReady = true;
        resetDrawState();
        tick();
        updateRefreshCountdown();
      }
      function tick() {
        if (typeof CryptoJS === "undefined") {
          markPassReady(slot);
          if (statusEl) statusEl.textContent = "CryptoJS not loaded (check CDN / offline).";
          return;
        }
        if (!isSg && typeof bwipjs === "undefined") {
          markPassReady(slot);
          if (statusEl) statusEl.textContent = "bwip-js not loaded (check CDN / offline).";
          return;
        }
        if (isSg && typeof bwipjs === "undefined") {
          markPassReady(slot);
          if (statusEl) statusEl.textContent = "bwip-js not loaded (check CDN / offline).";
          return;
        }
        try {
          if (!clockReady) return;
          var now = nowSec();
          updateRefreshCountdown();
          if (isSg) {
            var sgStep = Math.floor(now / period);
            if (sgStep === lastSgStep && lastSgStep >= 0) return;
            lastSgStep = sgStep;
            var sgOtp = totpHex(cfg.otp, now, period, digits);
            var sgPayload = (cfg.v || "") + sgOtp;
            drawSgQr(canvas, sgPayload).then(function () {
              markBarcodeReady(holder);
              if (statusEl) {
                statusEl.textContent =
                  "Hold your phone near the reader when you arrive — you're good to go.";
              }
            }).catch(function (err) {
              markPassReady(slot);
              if (statusEl)
                statusEl.textContent = "Barcode error: " + (err && err.message ? err.message : String(err));
            });
            return;
          }
          /* TM: redraw on 15s OTP steps with fresh unix (not every second — lighter on mobile). */
          var otpStep = Math.floor(now / period);
          if (otpStep === lastOtpStep && lastOtpStep >= 0) return;
          lastOtpStep = otpStep;
          var eo = totpHex(cfg.ek, now, period, digits);
          var co = totpHex(cfg.ck, now, period, digits);
          var payload = cfg.t + "::" + eo + "::" + co + "::" + now;
          drawPdf417(canvas, payload);
          var left = period - (now % period);
          if (statusEl) {
            statusEl.textContent =
              "Hold your phone near the reader when you arrive — you're good to go.";
          }
        } catch (err) {
          markPassReady(slot);
          if (statusEl)
            statusEl.textContent = "Barcode error: " + (err && err.message ? err.message : String(err));
        }
      }
      if (tmClockUrl) {
        function pullTmClock(isFirst) {
          var prevSkew = remoteSkewSec;
          fetch(tmClockUrl, { cache: "no-store", credentials: "omit" })
            .then(function (r) {
              if (!r.ok) throw new Error("tm-clock " + r.status);
              return r.json();
            })
            .then(function (j) {
              if (j && typeof j.unix === "number" && !isNaN(j.unix))
                remoteSkewSec = j.unix - Math.floor(Date.now() / 1000);
            })
            .catch(function () {})
            .finally(function () {
              if (remoteSkewSec !== prevSkew) {
                resetDrawState();
                tick();
              }
              if (isFirst) updateRefreshCountdown();
            });
        }
        pullTmClock(true);
        var tmClockPollMs =
          typeof cfg.tm_clock_refresh_sec === "number" &&
          cfg.tm_clock_refresh_sec > 0
            ? cfg.tm_clock_refresh_sec * 1000
            : 60000;
        setInterval(function () {
          pullTmClock(false);
        }, tmClockPollMs);
      } else if (cfg.sync_date) {
        var syncUrl = window.location.href.split("#")[0];
        var prevSkew = remoteSkewSec;
        fetch(syncUrl, { method: "HEAD", cache: "no-store", credentials: "same-origin" })
          .then(function (r) {
            var dh = r.headers.get("Date");
            if (dh) {
              var sm = Date.parse(dh);
              if (!isNaN(sm))
                remoteSkewSec = Math.floor(sm / 1000) - Math.floor(Date.now() / 1000);
            }
          })
          .catch(function () {})
          .finally(function () {
            if (remoteSkewSec !== prevSkew) {
              resetDrawState();
              tick();
            }
            updateRefreshCountdown();
          });
      }
      setInterval(tick, 1000);
      setInterval(updateRefreshCountdown, 250);
      tick();
      updateRefreshCountdown();
      var rDw;
      window.addEventListener("resize", function () {
        clearTimeout(rDw);
        rDw = setTimeout(function () {
          resetDrawState();
          tick();
        }, 180);
      });
    });
  }
  function initCarousels() {
    document.querySelectorAll(".tm-ticket-carousel").forEach(function (root) {
      var track = root.querySelector(".tm-carousel-track");
      if (!track) return;
      var slides = root.querySelectorAll(".tm-carousel-slide");
      var n = slides.length;
      var prev = root.querySelector(".tm-carousel-prev");
      var next = root.querySelector(".tm-carousel-next");
      var dotBtns = root.querySelectorAll(".tm-carousel-dot");
      var ctr = root.querySelector(".tm-carousel-counter__n");
      var vp = root.querySelector(".tm-carousel-viewport");
      var peek = root.classList.contains("tm-ticket-carousel--peek");
      var i = 0;
      var gapPx = 12;
      function slideStepPx() {
        if (n < 2 || !slides[0]) return vp ? vp.clientWidth : 0;
        var r = slides[0].getBoundingClientRect();
        return r.width + gapPx;
      }
      function layoutPeek() {
        if (!peek || n < 2 || !vp) {
          for (var si = 0; si < slides.length; si++) {
            slides[si].style.flexBasis = "";
            slides[si].style.width = "";
            slides[si].style.minWidth = "";
          }
          return;
        }
        var cw = vp.clientWidth;
        /* Leave a wider strip for the next card (no horizontal scroll / “slider” needed to see it). */
        var slideW = Math.max(240, Math.min(448, cw - 70));
        for (var sj = 0; sj < slides.length; sj++) {
          slides[sj].style.flex = "0 0 " + slideW + "px";
          slides[sj].style.width = slideW + "px";
          slides[sj].style.minWidth = slideW + "px";
        }
        track.style.gap = gapPx + "px";
      }
      function apply() {
        if (n < 2) {
          track.style.transform = "translateX(0)";
        } else {
          var step = slideStepPx();
          track.style.transform = "translateX(-" + i * step + "px)";
        }
        if (prev) prev.disabled = i <= 0;
        if (next) next.disabled = i >= n - 1;
        if (ctr) ctr.textContent = i + 1 + " of " + n;
        dotBtns.forEach(function (b, j) {
          var on = j === i;
          b.classList.toggle("is-active", on);
          b.setAttribute("aria-selected", on ? "true" : "false");
        });
      }
      function go(delta) {
        i = Math.max(0, Math.min(n - 1, i + delta));
        apply();
      }
      function goTo(j) {
        i = Math.max(0, Math.min(n - 1, j));
        apply();
      }
      if (prev) prev.addEventListener("click", function () { go(-1); });
      if (next) next.addEventListener("click", function () { go(1); });
      dotBtns.forEach(function (b, j) {
        b.addEventListener("click", function () { goTo(j); });
      });
      var sx = 0;
      root.addEventListener(
        "touchstart",
        function (e) {
          if (n < 2) return;
          sx = e.changedTouches[0].screenX;
        },
        { passive: true }
      );
      root.addEventListener(
        "touchend",
        function (e) {
          if (n < 2) return;
          var dx = e.changedTouches[0].screenX - sx;
          if (dx > 56) go(-1);
          else if (dx < -56) go(1);
        },
        { passive: true }
      );
      if (n > 1) {
        root.setAttribute("tabindex", "0");
        root.addEventListener("keydown", function (e) {
          if (e.key === "ArrowLeft") {
            e.preventDefault();
            go(-1);
          } else if (e.key === "ArrowRight") {
            e.preventDefault();
            go(1);
          }
        });
      }
      root.addEventListener(
        "wheel",
        function (e) {
          if (Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return;
          e.preventDefault();
        },
        { passive: false }
      );
      layoutPeek();
      apply();
      if (n > 1 && typeof window !== "undefined") {
        var rto;
        window.addEventListener("resize", function () {
          clearTimeout(rto);
          rto = setTimeout(function () {
            layoutPeek();
            i = Math.max(0, Math.min(n - 1, i));
            apply();
            if (typeof window.tmTicketViewportFit === "function") window.tmTicketViewportFit();
          }, 120);
        });
      }
    });
  }
  function tmTicketViewportFit() {
    if (!document.documentElement.classList.contains("tm-html-ticket-viewport")) return;
    var inner = document.querySelector(".tm-pass-viewport-fit-inner");
    if (!inner) return;
    inner.style.transform = "";
    inner.style.marginBottom = "";
  }
  window.tmTicketViewportFit = tmTicketViewportFit;
  function initPassMediaFadeIns() {
    document
      .querySelectorAll(".tm-pass-hero-bg, .tm-pass-brand-strip img")
      .forEach(function (img) {
        function done() {
          img.classList.add("tm-pass-media--loaded");
        }
        if (img.complete && img.naturalWidth > 0) done();
        else {
          img.addEventListener("load", done, { once: true });
          img.addEventListener("error", done, { once: true });
        }
      });
  }
  function boot() {
    initPassMediaFadeIns();
    document.querySelectorAll("article.acct").forEach(initArticle);
    initCarousels();
    tmTicketViewportFit();
    var _vft;
    window.addEventListener("resize", function () {
      clearTimeout(_vft);
      _vft = setTimeout(tmTicketViewportFit, 80);
    });
    setTimeout(tmTicketViewportFit, 120);
    setTimeout(tmTicketViewportFit, 400);
    if (typeof ResizeObserver !== "undefined") {
      var fitInner = document.querySelector(".tm-pass-viewport-fit-inner");
      if (fitInner) {
        var roFit = new ResizeObserver(function () {
          tmTicketViewportFit();
        });
        roFit.observe(fitInner);
      }
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
</script>"""


_SAFETIX_RUNTIME_MARKER = "TM_HIT_VIEWER_SAFETIX_RUNTIME"

_SAFETIX_RUNTIME_SCRIPT_RE = re.compile(
    r'<script\s+src="https://cdnjs\.cloudflare\.com/ajax/libs/crypto-js/[^"]+"[^>]*>\s*</script>\s*'
    r'<script\s+src="https://cdn\.jsdelivr\.net/npm/bwip-js[^"]+"[^>]*>\s*</script>\s*'
    r"<script>\s*\(function\s*\(\)\s*\{[\s\S]*?\}\)\s*\(\)\s*;\s*</script>",
    re.IGNORECASE,
)

_SAFETIX_RUNTIME_LOOSE_RE = re.compile(
    r'<script\s+src="[^"]*crypto-js[^"]*"[^>]*>\s*</script>\s*'
    r'<script\s+src="[^"]*bwip-js[^"]*"[^>]*>\s*</script>\s*'
    r"<script>[\s\S]*?\}\)\(\)\;\s*</script>",
    re.IGNORECASE,
)

_MAX_PASS_REFRESH_BYTES = 50 * 1024 * 1024

# Quick layout test pass on tixx.pw (Chris Stapleton Sec 208 / Row J / Seat 6).
_DEV_TEST_PASS_URL = "https://tixx.pw/tickets/19/tsu2grMCGuG9IKgNc4Uu"


def _normalize_only_pass_rel(spec: str) -> str:
    """Return site-relative path ``tickets/<gid>/<slug>.html`` from URL, slug, or path."""
    s = (spec or "").strip()
    if not s:
        return ""
    m = re.search(
        r"/tickets/(\d+)/([^/?#]+?)(?:\.html)?/?(?:[?#]|$)",
        s,
        re.I,
    )
    if m:
        slug = html.unescape(m.group(2).strip())
        if not slug.lower().endswith(".html"):
            slug += ".html"
        return f"tickets/{m.group(1)}/{slug}"
    s = s.replace("\\", "/").strip().strip("/")
    if not s.lower().endswith(".html"):
        s += ".html"
    if not s.lower().startswith("tickets/"):
        parts = [p for p in s.split("/") if p]
        if len(parts) == 2 and parts[0].isdigit():
            s = f"tickets/{parts[0]}/{parts[1]}"
    return s


def _pass_rel_matches_only(rel: str, only_rel: str) -> bool:
    if not only_rel:
        return True
    a = (rel or "").replace("\\", "/").lower().strip()
    b = only_rel.replace("\\", "/").lower().strip()
    if not b.endswith(".html"):
        b += ".html"
    return a == b


def _resolve_only_pass_filter(
    *,
    only_pass: str = "",
    dev_pass: bool = False,
    all_passes: bool = False,
) -> str:
    if all_passes:
        return ""
    if dev_pass:
        return _normalize_only_pass_rel(_DEV_TEST_PASS_URL)
    return _normalize_only_pass_rel(only_pass)


def _read_pass_html_for_refresh(html_path: Path) -> tuple[bytes, str | None]:
    """Read a full pass HTML for refresh (SafeTix scripts live at EOF after large inline CSS)."""
    try:
        sz = html_path.stat().st_size
    except OSError as e:
        return b"", str(e)
    if sz > _MAX_PASS_REFRESH_BYTES:
        return b"", f"oversize ({sz} bytes > {_MAX_PASS_REFRESH_BYTES})"
    try:
        return html_path.read_bytes(), None
    except OSError as e:
        return b"", str(e)


def _safetix_runtime_block_looks_live(block: str) -> bool:
    b = (block or "").lower()
    return (
        _SAFETIX_RUNTIME_MARKER.lower() in b
        or "initarticle" in b
        or "safetix-slot" in b
        or "data-tm-safetix" in b
        or "drawpdf417" in b
    )


def _replace_safetix_runtime_by_marker(html: str, fresh: str) -> str | None:
    midx = html.find(_SAFETIX_RUNTIME_MARKER)
    if midx < 0:
        return None
    crypto = html.rfind("crypto-js", 0, midx)
    start = html.rfind("<script", 0, crypto if crypto >= 0 else midx)
    if start < 0:
        start = html.rfind("<script", max(0, midx - 800), midx)
    if start < 0:
        return None
    end_m = re.search(r"\}\)\(\)\;\s*</script>", html[midx:], flags=re.IGNORECASE)
    if not end_m:
        return None
    end = midx + end_m.end()
    return html[:start] + fresh + html[end:]


def _upsert_safetix_runtime_scripts(html: str, fresh: str) -> tuple[str, str]:
    """
    Replace or inject CryptoJS+bwip+SafeTix runtime.
    Returns (new_html, status) where status is replaced|injected|noop|no_target.
    """
    if _SAFETIX_RUNTIME_SCRIPT_RE.search(html):
        out = _SAFETIX_RUNTIME_SCRIPT_RE.sub(lambda _m: fresh, html, count=1)
        return out, "replaced" if out != html else "noop"

    by_marker = _replace_safetix_runtime_by_marker(html, fresh)
    if by_marker is not None:
        return by_marker, "replaced" if by_marker != html else "noop"

    for m in _SAFETIX_RUNTIME_LOOSE_RE.finditer(html):
        if not _safetix_runtime_block_looks_live(m.group(0)):
            continue
        out = html[: m.start()] + fresh + html[m.end() :]
        return out, "replaced"

    if re.search(r"data-tm-safetix\s*=", html, re.IGNORECASE):
        ins = re.search(r"</body>", html, re.IGNORECASE)
        if ins:
            pos = ins.start()
            out = html[:pos] + fresh + "\n" + html[pos:]
            return out, "injected"
        return html + "\n" + fresh, "injected"

    return html, "no_target"


_MAX_TICKET_HTML_READ = 10 * 1024 * 1024  # barcode scripts live at EOF on large CSS-heavy passes


def _read_ticket_html_bytes_capped(html_path: Path, max_total: int = _MAX_TICKET_HTML_READ) -> bytes:
    try:
        sz = html_path.stat().st_size
    except OSError:
        return b""
    n = max(0, min(sz, max_total))
    if n == 0:
        return b""
    try:
        return html_path.read_bytes()[:n]
    except OSError:
        return b""


def _bytes_has_viewer_safetix_stack(sample: bytes) -> bool:
    """Live pass pages embed CryptoJS, bwip-js, or ``data-tm-safetix`` (often far below a giant ``<style>``)."""
    if not sample:
        return False
    sl = sample.lower()
    return (
        b"cdnjs.cloudflare.com/ajax/libs/crypto-js" in sl
        or b"cdn.jsdelivr.net/npm/bwip-js" in sl
        or b"/npm/bwip-js" in sl
        or b"data-tm-safetix" in sl
    )


def _bytes_is_tm_registry_transfer_stub(sample: bytes) -> bool:
    """
    Body copy from registry ``_html_transfer_stub_page`` (seller link after transfer).

    Used only together with **lack** of SafeTix CDN tags / ``data-tm-safetix`` so real passes are not skipped.
    """
    if not sample:
        return False
    if b"This ticket was transferred" not in sample:
        return False
    if b"The barcode is no longer valid on this link" not in sample:
        return False
    return True


def _should_skip_ticket_html_as_registry_transfer_stub(
    *, sample_head: bytes, full_scan: bytes
) -> bool:
    """
    Registry stubs are tiny static pages **without** a SafeTix script stack.

    Barcode passes put CryptoJS / bwip-js / ``data-tm-safetix`` near EOF after a large ``<style>`` head;
    scanning only the file prefix used to mark every pass as a stub.
    """
    if _bytes_has_viewer_safetix_stack(full_scan):
        return False
    lo = sample_head.lower()
    if b"<title>ticket transferred</title>" in lo:
        return True
    return _bytes_is_tm_registry_transfer_stub(sample_head)


def _strip_safetix_debug_from_pass_html(html: str) -> str:
    """Remove PDF417 debug label/pre and related CSS from older pass pages."""
    out = re.sub(
        r'<p class="safetix-payload-debug-label"[^>]*>[\s\S]*?</p>\s*'
        r'<pre class="safetix-payload-debug"[^>]*>[\s\S]*?</pre>\s*',
        "",
        html,
        flags=re.IGNORECASE,
    )
    out = re.sub(r"\n\s*\.safetix-payload-debug-label\s*\{[^}]*\}\n", "\n", out, flags=re.DOTALL)
    out = re.sub(r"\n\s*\.safetix-payload-debug\s*\{[^}]*\}\n", "\n", out, flags=re.DOTALL)
    out = re.sub(
        r"\n\s*html\.tm-html-ticket-viewport\s+\.safetix-payload-debug-label\s*\{[^}]*\}\n",
        "\n",
        out,
        flags=re.DOTALL,
    )
    out = re.sub(
        r"\n\s*html\.tm-html-ticket-viewport\s+\.safetix-payload-debug\s*\{[^}]*\}\n",
        "\n",
        out,
        flags=re.DOTALL,
    )
    return out


_PASS_REFRESH_BTN_HTML = (
    '<button type="button" class="tm-pass-refresh-btn" aria-label="Refresh barcode">'
    '<span class="tm-pass-refresh-btn__ico" aria-hidden="true">↻</span>'
    '<span class="tm-pass-refresh-btn__label">Refresh barcode</span>'
    '<span class="tm-pass-refresh-btn__sec" aria-live="polite">—</span>'
    "</button>"
)

_PASS_HERO_FX_HTML = '<div class="tm-pass-hero-fx" aria-hidden="true"></div>'

_PASS_BARCODE_UI_PATCH_STYLE = """
/* TM_HIT_VIEWER_BARCODE_UI_V8 — overlay layout + hero fx + smooth barcode load */
.tm-pass-visual--overlay {
  display: flex !important; flex-direction: column !important; background: #fff !important;
}
.tm-pass-brand-strip {
  display: flex !important; align-items: center !important; justify-content: center !important;
  padding: 7px 12px 6px !important; background: #026cdf !important;
}
.tm-pass-brand-strip img {
  height: 13px !important; width: auto !important; max-width: 132px !important;
  filter: brightness(0) invert(1) !important; opacity: 0 !important;
  transition: opacity 0.4s ease !important;
}
.tm-pass-brand-strip img.tm-pass-media--loaded { opacity: 0.96 !important; }
.tm-pass-hero-bg { opacity: 0 !important; transition: opacity 0.48s ease !important; }
.tm-pass-hero-bg.tm-pass-media--loaded { opacity: 1 !important; }
.tm-pass-visual--overlay .tm-pass-hero-fx {
  position: absolute !important; inset: 0 !important; z-index: 1 !important;
  pointer-events: none !important; overflow: hidden !important;
}
.tm-pass-visual--overlay .tm-pass-hero-shade--soft { z-index: 2 !important; }
.tm-pass-card .tm-pass-bc.barcode-frame { min-height: 88px !important; }
.tm-pass-bc .safetix-canvas { opacity: 0 !important; transition: opacity 0.38s ease !important; }
.tm-pass-bc.tm-pass-bc--ready .safetix-canvas { opacity: 1 !important; }
@keyframes tm-pass-bc-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
.tm-pass-bc:not(.tm-pass-bc--ready)::before {
  content: ""; position: absolute; left: 10px; right: 10px; top: 8px; bottom: 6px; z-index: 0;
  border-radius: 6px; pointer-events: none;
  background: linear-gradient(90deg, #eef0f2 0%, #f8f9fa 45%, #eef0f2 90%);
  background-size: 200% 100%; animation: tm-pass-bc-shimmer 1.4s ease-in-out infinite;
}
.tm-pass-bc.tm-pass-bc--ready::before { display: none !important; }
.tm-pass-bc:not(.tm-pass-bc--ready) .tm-scan-line,
.tm-pass-bc:not(.tm-pass-bc--ready) .tm-scan-glow {
  opacity: 0 !important; visibility: hidden !important; animation: none !important;
}
.tm-pass-bc.tm-pass-bc--ready .tm-scan-line,
.tm-pass-bc.tm-pass-bc--ready .tm-scan-glow {
  opacity: 1 !important; transition: opacity 0.45s ease 0.15s !important;
}
.tm-pass-status { min-height: 1.35em !important; opacity: 0 !important; transition: opacity 0.4s ease 0.08s !important; }
.tm-pass-card.tm-pass-card--ready .tm-pass-status { opacity: 1 !important; }
@keyframes tm-pass-card-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: none; }
}
@keyframes tm-pass-soft-fade {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: none; }
}
html.tm-html-ticket-viewport .safetix-slot.tm-pass-card {
  animation: tm-pass-card-in 0.5s cubic-bezier(0.22, 0.61, 0.36, 1) both !important;
}
html.tm-html-ticket-viewport .tm-pass-rail,
html.tm-html-ticket-viewport .tm-pass-menu,
html.tm-html-ticket-viewport .tm-pass-title,
html.tm-html-ticket-viewport .tm-pass-sub-line {
  animation: tm-pass-soft-fade 0.45s cubic-bezier(0.22, 0.61, 0.36, 1) 0.06s both !important;
}
html.tm-html-ticket-viewport .tm-pass-sub-line:nth-child(n) { animation-delay: 0.06s !important; }
.tm-pass-visual--overlay .tm-pass-hero--cover {
  position: relative !important;
  height: clamp(340px, 78vw, 440px) !important;
  min-height: clamp(340px, 78vw, 440px) !important;
  max-height: none !important; overflow: hidden !important;
}
.tm-pass-visual--overlay .tm-pass-hero--cover .tm-pass-hero-bg {
  position: absolute !important; inset: 0 !important; z-index: 0 !important;
  width: 100% !important; height: 100% !important;
  object-fit: cover !important; object-position: center 16% !important;
}
.tm-pass-visual--overlay .tm-pass-hero--cover.tm-pass-hero--grad,
.tm-pass-visual--overlay .tm-pass-hero--cover.tm-pass-hero--tmblue {
  height: clamp(340px, 78vw, 440px) !important;
  min-height: clamp(340px, 78vw, 440px) !important; max-height: none !important;
}
.tm-pass-visual--overlay .tm-pass-hero-shade--soft {
  position: absolute !important; inset: 0 !important; z-index: 1 !important; pointer-events: none !important;
  background: linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,0.06) 38%,
    rgba(0,0,0,0.22) 72%, rgba(0,0,0,0.34) 100%) !important;
}
.tm-pass-visual--overlay .tm-pass-bar-sheet {
  position: absolute !important; left: 8px !important; right: 8px !important;
  bottom: 8px !important; z-index: 3 !important;
  padding: 10px 10px 8px !important; background: #eceeef !important;
  border-radius: 10px !important;
  box-shadow: inset 0 1px 2px rgba(0,0,0,0.06), 0 4px 14px rgba(0,0,0,0.14) !important;
  border: 1px solid rgba(0,0,0,0.06) !important;
}
.tm-pass-visual--overlay .tm-pass-bc.barcode-frame {
  padding: 6px 8px 4px !important;
}
.tm-pass-visual--overlay .barcode-frame canvas.safetix-canvas {
  width: 100% !important; max-width: 100% !important; height: auto !important;
  max-height: 110px !important; image-rendering: pixelated;
}
html.tm-html-ticket-viewport {
  height: auto !important; min-height: 100% !important; min-height: 100dvh !important;
  overflow-x: hidden !important; overflow-y: auto !important;
}
html.tm-html-ticket-viewport body.tm-shell-ticket-minimal {
  height: auto !important; max-height: none !important;
  overflow-x: hidden !important; overflow-y: auto !important;
}
html.tm-html-ticket-viewport .tm-pass-visual--overlay .tm-pass-hero--cover,
html.tm-html-ticket-viewport .tm-pass-visual--overlay .tm-pass-hero--cover.tm-pass-hero--grad,
html.tm-html-ticket-viewport .tm-pass-visual--overlay .tm-pass-hero--cover.tm-pass-hero--tmblue {
  height: clamp(360px, 82vw, 460px) !important;
  min-height: clamp(360px, 82vw, 460px) !important;
}
html.tm-html-ticket-viewport .tm-pass-visual--overlay .tm-pass-bar-sheet {
  left: 6px !important; right: 6px !important; bottom: 6px !important;
}
html.tm-html-ticket-viewport .tm-pass-visual--overlay .barcode-frame canvas.safetix-canvas {
  max-height: 108px !important;
}
html.tm-html-ticket-viewport .tm-pass-card { overflow: visible !important; max-height: none !important; }
html.tm-html-ticket-viewport .tm-pass-viewport-fit { overflow-y: visible !important; height: auto !important; }
html.tm-html-ticket-viewport .tm-carousel-viewport { overflow: visible !important; }
.tm-pass-refresh-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 9px 4px 7px; margin: 0;
  border: 1px solid rgba(2, 108, 223, 0.38); border-radius: 999px;
  background: #fff; color: #026cdf; font: inherit;
  font-size: 0.625rem; font-weight: 700; letter-spacing: 0.02em;
  cursor: pointer; line-height: 1.1;
  box-shadow: 0 1px 2px rgba(2, 108, 223, 0.12);
}
.tm-pass-refresh-btn:hover { background: rgba(2, 108, 223, 0.06); }
.tm-pass-refresh-btn--spin .tm-pass-refresh-btn__ico {
  animation: tm-pass-spin 0.65s linear;
}
@keyframes tm-pass-spin { to { transform: rotate(360deg); } }
.tm-pass-refresh-btn__sec {
  min-width: 1.35em; height: 1.35em; padding: 0 2px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 0.55rem; font-weight: 800; color: #0153a3;
  background: rgba(2, 108, 223, 0.08); font-variant-numeric: tabular-nums;
}
"""

_PASS_BARCODE_UI_PATCH_STYLE_RE = re.compile(
    r"<style>\s*/\* TM_HIT_VIEWER_BARCODE_UI_V[2345678][\s\S]*?</style>\s*",
    re.I,
)


_PASS_BAR_SHEET_BLOCK_RE = re.compile(
    r'<div class="tm-pass-bar-sheet">[\s\S]*?'
    r'<p class="safetix-status[^"]*"[^>]*>[\s\S]*?</p>\s*</div>',
    re.I,
)
_PASS_HERO_FX_RE = re.compile(
    r'\s*<div class="tm-pass-hero-fx"[^>]*>[\s\S]*?</div>',
    re.I,
)
_PASS_HERO_SHADE_RE = re.compile(
    r'\s*<div class="tm-pass-hero-shade"[^>]*>[\s\S]*?</div>',
    re.I,
)
_PASS_VISUAL_STACK_BODY_RE = re.compile(
    r'<div class="tm-pass-visual">\s*'
    r'(<div class="tm-pass-hero[^"]*"[^>]*>)'
    r'([\s\S]*?)'
    r'</div>\s*</div>\s*(<div class="tm-pass-body")',
    re.I,
)


_PASS_VISUAL_TMSTACK_BODY_RE = re.compile(
    r'<div class="tm-pass-visual tm-pass-visual--tmstack">\s*'
    r'(<div class="tm-pass-brand-strip"[\s\S]*?</div>\s*)?'
    r'(<div class="tm-pass-bar-sheet">[\s\S]*?</div>\s*)'
    r'(<div class="tm-pass-hero[^"]*"[^>]*>)'
    r'([\s\S]*?)'
    r'</div>\s*</div>\s*(<div class="tm-pass-body")',
    re.I,
)


_PASS_BRAND_STRIP_RE = re.compile(
    r'<div class="tm-pass-brand-strip"[\s\S]*?</div>\s*',
    re.I,
)
_PASS_CARD_RAIL_HEAD_RE = re.compile(
    r'(<div class="tm-pass-rail"[^>]*></div>\s*)'
    r'(<div class="tm-pass-head")',
    re.I,
)


def _tm_pass_brand_strip_html() -> str:
    return (
        '<div class="tm-pass-brand-strip" aria-hidden="true">'
        f'<img src="{_TM_WORDMARK_WIKIMEDIA_SVG}" alt="" width="120" height="20" '
        'loading="lazy" decoding="async" referrerpolicy="no-referrer"/></div>'
    )


def _patch_pass_brand_strip_to_card_top(html_doc: str) -> str:
    """Blue TM wordmark sits at top of pass card (after rail, before event header)."""
    if "tm-pass-rail" not in html_doc or "tm-pass-head" not in html_doc:
        return html_doc
    brand_m = _PASS_BRAND_STRIP_RE.search(html_doc)
    brand = brand_m.group(0) if brand_m else _tm_pass_brand_strip_html()
    html_doc = _PASS_BRAND_STRIP_RE.sub("", html_doc)
    return _PASS_CARD_RAIL_HEAD_RE.sub(rf"\1{brand}\2", html_doc, count=1)


def _hero_open_to_cover(hero_open: str) -> str:
    hero_open = re.sub(r"\btm-pass-hero--poster\b", "tm-pass-hero--cover", hero_open)
    if "tm-pass-hero--cover" not in hero_open:
        hero_open = re.sub(
            r'class="(tm-pass-hero[^"]*)"',
            r'class="\1 tm-pass-hero--cover"',
            hero_open,
            count=1,
        )
    return hero_open


def _ensure_pass_hero_fx(html_doc: str) -> str:
    """Re-inject white-spot / glint overlay on hero art if a prior patch stripped it."""
    if "tm-pass-hero-fx" in html_doc:
        return html_doc
    return re.sub(
        r'(<div class="tm-pass-hero-shade[^"]*"[^>]*>)',
        _PASS_HERO_FX_HTML + r"\1",
        html_doc,
        count=0,
        flags=re.I,
    )


def _patch_pass_visual_overlay(html_doc: str) -> str:
    """Reorder stack/legacy layout → TM overlay (hero art + barcode pinned to bottom)."""
    shade = '<div class="tm-pass-hero-shade tm-pass-hero-shade--soft" aria-hidden="true"></div>'

    if "tm-pass-visual--overlay" in html_doc:
        return html_doc

    if "tm-pass-visual--tmstack" in html_doc:

        def _tmstack_repl(m: re.Match) -> str:
            bar_html = m.group(2)
            hero_open = _hero_open_to_cover(m.group(3))
            hero_inner = m.group(4)
            body_open = m.group(5)
            hero_inner = _PASS_HERO_SHADE_RE.sub("", hero_inner)
            hero_inner = _PASS_BAR_SHEET_BLOCK_RE.sub("", hero_inner)
            if "tm-pass-hero-fx" not in hero_inner:
                hero_inner = hero_inner.rstrip() + "\n" + _PASS_HERO_FX_HTML
            return (
                f'<div class="tm-pass-visual tm-pass-visual--overlay">'
                f"{hero_open}{hero_inner}{shade}{bar_html}</div></div>{body_open}"
            )

        return _PASS_VISUAL_TMSTACK_BODY_RE.sub(_tmstack_repl, html_doc)

    def _legacy_repl(m: re.Match) -> str:
        hero_open = _hero_open_to_cover(m.group(1))
        inner = m.group(2)
        body_open = m.group(3)
        bar_m = _PASS_BAR_SHEET_BLOCK_RE.search(inner)
        if not bar_m:
            return m.group(0)
        bar_html = bar_m.group(0)
        hero_inner = inner[: bar_m.start()] + inner[bar_m.end() :]
        hero_inner = _PASS_HERO_SHADE_RE.sub("", hero_inner)
        if "tm-pass-hero-fx" not in hero_inner:
            hero_inner = hero_inner.rstrip() + "\n" + _PASS_HERO_FX_HTML
        return (
            f'<div class="tm-pass-visual tm-pass-visual--overlay">'
            f"{hero_open}{hero_inner}{shade}{bar_html}</div></div>{body_open}"
        )

    return _PASS_VISUAL_STACK_BODY_RE.sub(_legacy_repl, html_doc)

_PASS_SCREEN_ROW_REFRESH_RE = re.compile(
    r'(<div class="tm-pass-screen-row"[^>]*>)([\s\S]*?)(</div>\s*<div class="[^"]*barcode-frame)',
    re.IGNORECASE,
)


def _inject_refresh_button_into_pass_html(html: str) -> str:
    if "tm-pass-refresh-btn" in html:
        return html

    def _repl(m: re.Match) -> str:
        return m.group(1) + m.group(2) + _PASS_REFRESH_BTN_HTML + m.group(3)

    return _PASS_SCREEN_ROW_REFRESH_RE.sub(_repl, html)


def _inject_pass_barcode_ui_patch_style(html: str) -> str:
    if "TM_HIT_VIEWER_BARCODE_UI_V8" in html:
        return html
    html = _PASS_BARCODE_UI_PATCH_STYLE_RE.sub("", html, count=1)
    block = f"<style>\n{_PASS_BARCODE_UI_PATCH_STYLE}\n</style>"
    if "</head>" in html:
        return html.replace("</head>", block + "\n</head>", 1)
    return block + html


def _patch_pass_barcode_ui_html(html: str) -> str:
    out = _patch_pass_visual_overlay(html)
    out = _ensure_pass_hero_fx(out)
    out = _patch_pass_brand_strip_to_card_top(out)
    out = _inject_refresh_button_into_pass_html(out)
    out = _inject_pass_barcode_ui_patch_style(out)
    return out


def _decode_safetix_cfg_attr(attr: str) -> dict | None:
    try:
        s = html.unescape((attr or "").strip())
        pad = (-len(s)) % 4
        raw = base64.b64decode(s + "=" * pad)
        d = json.loads(raw.decode("utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _secure_token_b64_from_safetix_cfg(cfg: dict) -> str | None:
    t = str(cfg.get("t") or cfg.get("rawToken") or "").strip()
    ek = str(cfg.get("ek") or cfg.get("eventKey") or "").strip()
    ck = str(cfg.get("ck") or cfg.get("customerKey") or "").strip()
    if not (t and ek and ck):
        for key in ("st", "secure_token", "secure_token_b64", "token"):
            st = str(cfg.get(key) or "").strip()
            if not st:
                continue
            tok = _decode_secure_token_b64(st)
            if tok:
                t = str(tok.get("t") or tok.get("rawToken") or "").strip()
                ek = str(tok.get("ek") or tok.get("eventKey") or "").strip()
                ck = str(tok.get("ck") or tok.get("customerKey") or "").strip()
                if t and ek and ck:
                    break
    if not (t and ek and ck):
        return None
    fake = {"b": "regen", "t": t, "ck": ck, "ek": ek, "rt": "rotating_symbology"}
    return base64.b64encode(json.dumps(fake, separators=(",", ":")).encode("utf-8")).decode("ascii")


_TM_SAFETIX_ATTR_RE = re.compile(
    r'data-tm-safetix\s*=\s*(["\'])(.*?)\1',
    re.I | re.S,
)


def _pass_html_has_safetix_attr(doc: str) -> bool:
    return bool(_TM_SAFETIX_ATTR_RE.search(doc or ""))


def _scrape_pass_fields_from_html_chunks(top: str, body: str, doc: str) -> dict:
    """Extract event/seat/hero fields from pass HTML fragments."""
    title_m = re.search(
        r'<h4[^>]*class="[^"]*tm-pass-title[^"]*"[^>]*>([^<]+)</h4>',
        top,
        re.I,
    )
    if not title_m:
        title_m = re.search(
            r'<h4[^>]*class="[^"]*tm-pass-title[^"]*"[^>]*>([^<]+)</h4>',
            doc,
            re.I,
        )
    event_name = html.unescape(title_m.group(1).strip()) if title_m else ""

    sub_lines = re.findall(
        r'<span class="tm-pass-sub-line"[^>]*>([^<]*)</span>',
        top,
        re.I,
    )
    subtitle = "\n".join(html.unescape(x.strip()) for x in sub_lines if (x or "").strip())
    if not subtitle:
        sub_m = re.search(r'<p class="tm-pass-sub"[^>]*>([\s\S]*?)</p>', top, re.I)
        if not sub_m:
            sub_m = re.search(r'<p class="tm-pass-sub"[^>]*>([\s\S]*?)</p>', doc, re.I)
        if sub_m:
            subtitle = html.unescape(
                re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", sub_m.group(1))).strip()
            )

    sec = rowv = seat = ""
    for lbl, dest in (("SECTION", "sec"), ("ROW", "rowv"), ("SEAT", "seat")):
        sm = re.search(
            rf'<span class="tm-pass-lbl">{lbl}</span>\s*<b>([^<]*)</b>',
            body,
            re.I,
        )
        if not sm:
            sm = re.search(
                rf'<span class="tm-pass-lbl">{lbl}</span>\s*<b>([^<]*)</b>',
                doc,
                re.I,
            )
        if sm:
            val = html.unescape(sm.group(1).strip())
            if val and val not in ("—", "-", "–"):
                if dest == "sec":
                    sec = val
                elif dest == "rowv":
                    rowv = val
                else:
                    seat = val

    gate_m = re.search(r'<div class="tm-pass-gate"[^>]*>([^<]+)</div>', body, re.I)
    if not gate_m:
        gate_m = re.search(r'<div class="tm-pass-gate"[^>]*>([^<]+)</div>', doc, re.I)
    gate = html.unescape(gate_m.group(1).strip()) if gate_m else ""

    type_m = re.search(r'<span class="tm-pass-type-detail"[^>]*>([^<]*)</span>', body, re.I)
    if not type_m:
        type_m = re.search(r'<span class="tm-pass-type-detail"[^>]*>([^<]*)</span>', doc, re.I)
    ticket_type = html.unescape(type_m.group(1).strip()) if type_m else ""

    hero_src = ""
    for chunk in (top, body, top + body, doc):
        hero_m = re.search(
            r'<img[^>]*class="[^"]*tm-pass-hero-bg[^"]*"[^>]*src="([^"]+)"',
            chunk,
            re.I,
        )
        if not hero_m:
            hero_m = re.search(
                r'<img[^>]*src="([^"]+)"[^>]*class="[^"]*tm-pass-hero-bg[^"]*"',
                chunk,
                re.I,
            )
        if hero_m:
            hero_src = html.unescape(hero_m.group(1).strip())
            break

    return {
        "event_name": event_name,
        "subtitle": subtitle,
        "section": sec,
        "row": rowv,
        "seat": seat,
        "gate": gate,
        "ticket_type": ticket_type,
        "hero_src": hero_src,
    }


def _row_from_safetix_cfg_and_fields(cfg: dict, fields: dict) -> dict | None:
    event_name = fields.get("event_name") or ""
    subtitle = fields.get("subtitle") or ""
    sec = fields.get("section") or ""
    rowv = fields.get("row") or ""
    seat = fields.get("seat") or ""
    gate = fields.get("gate") or ""
    ticket_type = fields.get("ticket_type") or ""
    hero_src = fields.get("hero_src") or ""

    seat_bits: list[str] = []
    if sec:
        seat_bits.append(f"Sec {sec}")
    if rowv:
        seat_bits.append(f"Row {rowv}")
    if seat:
        seat_bits.append(f"Seat {seat}")
    label = f"{event_name} · {' · '.join(seat_bits)}" if seat_bits else event_name

    if str(cfg.get("platform") or "").strip().lower() == "sg":
        val = str(cfg.get("v") or "").strip()
        otp = str(cfg.get("otp") or "").strip()
        if not (val and otp):
            return None
        try:
            period = int(cfg.get("period") or 30)
        except (TypeError, ValueError):
            period = 30
        row_obj: dict = {
            "sg_barcode": True,
            "barcode_value": val,
            "otp_secret": otp,
            "interval": period,
            "label": label or "Ticket",
            "event_name": event_name,
            "section": sec,
            "row": rowv,
            "seat": seat,
            "gate": gate,
            "ticket_type": ticket_type or "Standard Admission",
            "_subtitle": subtitle,
        }
    else:
        st_b64 = _secure_token_b64_from_safetix_cfg(cfg)
        if not st_b64:
            return None
        row_obj = {
            "secure_token_b64": st_b64,
            "label": label or "Ticket",
            "event_name": event_name,
            "section": sec,
            "row": rowv,
            "seat": seat,
            "gate": gate or _default_tm_pass_gate({}),
            "ticket_type": _normalize_tm_pass_ticket_type(ticket_type or "Standard Admission"),
            "_subtitle": subtitle,
        }

    if hero_src:
        _apply_hero_src_to_row(row_obj, hero_src)
    return row_obj


def _scrape_pass_preservation_head_metas(doc: str) -> str:
    """Keep reminder / email-gate metas from an existing pass page across layout regen."""
    names = (
        "tm-event-start",
        "tm-reminder-mode",
        "tm-reminder-date",
        "tm-event-title",
        "tm-reminder-register-url",
        "tm-email-gate-enabled",
    )
    lines: list[str] = []
    for name in names:
        m = re.search(
            rf'<meta\s+[^>]*name=["\']{re.escape(name)}["\'][^>]*>\s*',
            doc or "",
            re.I,
        )
        if m:
            lines.append("  " + m.group(0).strip())
    return ("\n".join(lines) + "\n") if lines else ""


def _apply_hero_src_to_row(row: dict, hero_src: str) -> None:
    hero_src = (hero_src or "").strip()
    if not hero_src:
        return
    if hero_src.startswith("data:"):
        row["image_url"] = hero_src
    elif hero_src.startswith(("http://", "https://")):
        row["image_url_remote"] = hero_src
    else:
        row["image_url"] = hero_src


def _row_hero_needs_restore(row: dict, site_root: Path | None) -> bool:
    local = (row.get("image_url") or "").strip()
    remote = (row.get("image_url_remote") or "").strip()
    if remote.startswith(("http://", "https://")):
        return False
    if local.startswith("data:"):
        return False
    if local and site_root is not None:
        _, ok = _tm_viewer_debug_resolve_asset(site_root, local)
        if ok:
            return False
    return True


def _enrich_scraped_pass_accs_from_site(accs: list[dict], site_root: Path) -> int:
    """Restore hero posters from tm_event_assets + tm_event_media.json by event name (no Discovery API)."""
    cache = _merged_event_media_cache(site_root)
    n = 0
    for acc in accs:
        for row in acc.get("barcode_tokens") or []:
            if not _row_hero_needs_restore(row, site_root):
                continue
            ev = (row.get("event_name") or "").strip()
            if not ev or ev == "Event":
                continue
            primary, fallback = _lookup_event_poster_urls(ev, cache=cache, site_root=site_root)
            if primary:
                _apply_hero_src_to_row(row, primary)
                n += 1
            if fallback and not (row.get("image_url_remote") or "").strip():
                row["image_url_remote"] = fallback
    return n


def _scrape_pass_barcode_rows_from_html(doc: str) -> list[dict]:
    """Rebuild ``barcode_tokens`` rows from live pass HTML (``data-tm-safetix`` + seat fields)."""
    doc = doc or ""
    rows: list[dict] = []
    seen_cfg: set[str] = set()

    def _push_cfg(cfg_raw: str, top: str, body: str) -> None:
        sig = (cfg_raw or "")[:96]
        if sig in seen_cfg:
            return
        cfg = _decode_safetix_cfg_attr(cfg_raw)
        if not cfg:
            return
        fields = _scrape_pass_fields_from_html_chunks(top, body, doc)
        row_obj = _row_from_safetix_cfg_and_fields(cfg, fields)
        if not row_obj:
            return
        seen_cfg.add(sig)
        rows.append(row_obj)

    card_pat = re.compile(
        r'<div class="safetix-slot[^"]*"[^>]*id="pass-[^"]+"[^>]*>([\s\S]*?)'
        r'<div class="tm-pass-body">([\s\S]*?)</div>\s*</div>\s*</div>',
        re.I,
    )
    for m in card_pat.finditer(doc):
        top, body = m.group(1), m.group(2)
        for cfg_m in _TM_SAFETIX_ATTR_RE.finditer(top + body):
            _push_cfg(cfg_m.group(2), top, body)

    if not rows:
        for cfg_m in _TM_SAFETIX_ATTR_RE.finditer(doc):
            pos = cfg_m.start()
            ctx_start = max(0, pos - 15000)
            window = doc[ctx_start:pos + 500]
            tail = doc[pos : min(len(doc), pos + 25000)]
            body_m = re.search(r'<div class="tm-pass-body">([\s\S]*?)</div>', tail, re.I)
            body = body_m.group(1) if body_m else tail
            _push_cfg(cfg_m.group(2), window + tail[:8000], body)

    return rows


def _acc_from_scraped_pass_rows(rows: list[dict]) -> dict:
    upcoming: list[str] = []
    if rows:
        ev = (rows[0].get("event_name") or "Event").strip()
        sub = (rows[0].get("_subtitle") or "").strip()
        venue = ""
        if "\n" in sub:
            parts = [p.strip() for p in sub.splitlines() if p.strip()]
            date_s = parts[0] if parts else sub
            venue = parts[-1] if len(parts) > 1 else ""
        else:
            date_s = sub
        upcoming.append(
            f"→ {ev} | 1x tickets | {date_s} | {venue} | Status: ONSALE"
        )
    clean_rows: list[dict] = []
    for r in rows:
        c = dict(r)
        c.pop("_subtitle", None)
        clean_rows.append(c)
    return {
        "header": "=== _regen@tm-viewer.internal | Ticket 1 ===",
        "upcoming": upcoming,
        "past": [],
        "cards": "",
        "cookies_lines": [],
        "secure_token_b64": "",
        "raw": "",
        "barcode_tokens": clean_rows,
    }


def _pass_site_uses_viewer_api(doc: str, site_root: Path) -> bool:
    if re.search(r"tm-email-gate\.js", doc or "", re.I):
        return True
    if re.search(r'tm-email-gate-enabled', doc or "", re.I):
        return True
    if (site_root / "tm_viewer_api_base.js").is_file():
        return True
    return False


def _mail_api_base_for_site(site_root: Path) -> str:
    js = site_root / "tm_viewer_mail_api_base.js"
    if js.is_file():
        try:
            txt = js.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'TM_VIEWER_MAIL_API_BASE\s*=\s*"([^"]+)"', txt)
            if m and (m.group(1) or "").strip():
                return m.group(1).strip().rstrip("/")
            m = re.search(r"TM_VIEWER_MAIL_API_BASE\s*=\s*'([^']+)'", txt)
            if m and (m.group(1) or "").strip():
                return m.group(1).strip().rstrip("/")
        except OSError:
            pass
    return (
        (os.environ.get("TM_VIEWER_MAIL_API_BASE") or "")
        or (os.environ.get("TM_VIEWER_EMAIL_BACKEND_URL") or "")
    ).strip().rstrip("/")


def _resolve_pass_site_root(site_dir: Path) -> tuple[Path | None, list[str]]:
    """
    Locate the folder that contains ``tickets/<gid>/*.html``.

    When run from ``tm.bz`` (checker ``tickets.txt`` lives here), passes are usually under
    ``tm-vercel-site/`` — not a ``tickets/`` subfolder beside ``tickets.txt``.
    """
    root = site_dir.expanduser()
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    else:
        root = root.resolve()

    candidates: list[tuple[Path, str]] = []

    def _add(p: Path, why: str) -> None:
        try:
            candidates.append((p.expanduser().resolve(), why))
        except OSError:
            pass

    _add(root, "argument")
    _add(root / "tm-vercel-site", "tm-vercel-site/")
    _add(root / "public", "public/")
    env_static = (os.environ.get("TM_VIEWER_PASSES_STATIC_DIR") or "").strip()
    if env_static:
        _add(Path(env_static), "TM_VIEWER_PASSES_STATIC_DIR")

    seen: set[str] = set()
    for cand, why in candidates:
        sk = str(cand)
        if sk in seen or not cand.is_dir():
            continue
        seen.add(sk)
        tdir = cand / "tickets"
        if tdir.is_dir():
            note = (
                f"[*] Resolved pass site → {cand} ({why}; no tickets/ under {root})"
                if cand != root
                else ""
            )
            hints = [note] if note else []
            return cand, hints

    vercel = root / "tm-vercel-site"
    return None, [
        f"No tickets/ directory under {root}.",
        (
            "Checker tickets.txt lives in tm.bz — pass HTML is usually in tm-vercel-site/tickets/, "
            "not a tickets/ folder beside tickets.txt."
        ),
        f"Try: python tm_hit_viewer.py --regen-all-passes \"{vercel}\" --no-open",
    ]


def _render_regen_pass_document(
    *,
    acc: dict,
    raw: str,
    rel: str,
    root: Path,
    gid: int,
    fname: str,
    reg: dict,
    mail_api: str,
) -> str:
    use_api = _pass_site_uses_viewer_api(raw, root)
    link_cap = _registry_link_secret_for_site_pass(reg, gid=gid, fname=fname) if use_api else ""
    if use_api and not link_cap:
        link_cap = _ensure_link_transfer_secret_for_pass_in_registry_file(
            root, gid=str(gid), fname=fname
        )
    preserved_head = _scrape_pass_preservation_head_metas(raw)
    r_head, r_tail = _tm_viewer_reminder_fragments(acc, only_si=None)
    eff_head = preserved_head if preserved_head.strip() else r_head
    ns = len(acc.get("barcode_tokens") or [])
    sub_title = "My ticket" if ns <= 1 else f"{ns} tickets"
    xfer_path = f"tickets/{gid}/{_ticket_href_clean(fname)}" if use_api else ""
    xfer_tail = (
        _tm_pass_transfer_page_inject(
            xfer_path,
            mail_api_base=mail_api,
            link_transfer_secret=link_cap,
        )
        if xfer_path
        else ""
    )
    inner = _render_account(
        acc,
        0,
        back_href="../../index.html",
        pass_nav=None,
        relative_asset_prefix="../../",
        debug_ticket_file=rel,
        debug_site_root=root,
        viewer_transfer_relpath=xfer_path,
    )
    return _tm_html_document(
        doc_title=_ticket_page_doc_title(acc, None),
        fetch_banner="",
        main_inner=inner,
        topbar_subtitle=sub_title,
        shell="ticket_minimal",
        pass_page_transfer_tail=xfer_tail,
        reminder_head_metas=eff_head,
        reminder_body_tail=r_tail,
        pass_is_sg=_acc_has_sg_barcode(acc),
    )


def regen_all_passes_in_site_dir(
    site_dir: Path,
    *,
    resolve_event_images: bool = False,
    download_event_images: bool = False,
    event_media_cache: Path | None = None,
    only_pass_rel: str = "",
) -> tuple[int, list[str]]:
    """
    Re-render every ``tickets/<gid>/*.html`` with the **current** pass template.

    Scrapes ``data-tm-safetix`` + seat/event fields from each file, rebuilds HTML in place
    (same path/slug). Preserves reminder metas, registry ``link_transfer_secret``, and barcode payloads.
    """
    msgs: list[str] = []
    root, resolve_hints = _resolve_pass_site_root(site_dir)
    if root is None:
        return 0, resolve_hints
    msgs.extend(resolve_hints)
    tdir = root / "tickets"
    if only_pass_rel:
        msgs.append(f"+ only pass: {only_pass_rel}")

    reg: dict = {"version": 1, "by_email": {}}
    reg_path = root / "tm_viewer_link_registry.json"
    if reg_path.is_file():
        try:
            reg = json.loads(reg_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError, TypeError):
            reg = {"version": 1, "by_email": {}}

    mail_api = _mail_api_base_for_site(root)
    jobs: list[dict] = []
    skip: dict[str, int] = {
        "read_fail": 0,
        "oversize": 0,
        "stub": 0,
        "decode": 0,
        "no_safetix": 0,
        "scrape_fail": 0,
    }
    n_files = 0

    for gid_dir in sorted(tdir.iterdir(), key=lambda p: p.name):
        if not gid_dir.is_dir() or not gid_dir.name.isdigit():
            continue
        for html_path in sorted(gid_dir.glob("*.html")):
            n_files += 1
            rel = html_path.relative_to(root).as_posix()
            if not _pass_rel_matches_only(rel, only_pass_rel):
                continue
            capped, read_err = _read_pass_html_for_refresh(html_path)
            if read_err == "oversize":
                skip["oversize"] += 1
                if skip["oversize"] <= 5:
                    msgs.append(f"{rel}: {read_err}, skip")
                continue
            if read_err or (not capped and html_path.is_file()):
                skip["read_fail"] += 1
                if skip["read_fail"] <= 5:
                    msgs.append(f"{rel}: {read_err or 'read failed'}, skip")
                continue
            head = capped[:98304] if len(capped) > 98304 else capped
            if _should_skip_ticket_html_as_registry_transfer_stub(
                sample_head=head, full_scan=capped
            ):
                skip["stub"] += 1
                continue
            try:
                raw = capped.decode("utf-8", errors="replace")
            except Exception as e:
                skip["decode"] += 1
                if skip["decode"] <= 5:
                    msgs.append(f"{rel}: decode {e}")
                continue
            rows = _scrape_pass_barcode_rows_from_html(raw)
            if not rows:
                if _pass_html_has_safetix_attr(raw):
                    skip["scrape_fail"] += 1
                    if skip["scrape_fail"] <= 5:
                        msgs.append(f"{rel}: data-tm-safetix present but scrape failed, skip")
                else:
                    skip["no_safetix"] += 1
                    if skip["no_safetix"] <= 5:
                        msgs.append(f"{rel}: no data-tm-safetix, skip")
                continue
            acc = _acc_from_scraped_pass_rows(rows)
            jobs.append(
                {
                    "path": html_path,
                    "rel": rel,
                    "raw": raw,
                    "acc": acc,
                    "gid": int(gid_dir.name),
                    "fname": html_path.name,
                }
            )

    msgs.append(
        f"+ scan: {n_files} html file(s), {len(jobs)} regen job(s), "
        f"skip no_safetix={skip['no_safetix']} scrape_fail={skip['scrape_fail']} "
        f"stub={skip['stub']} oversize={skip['oversize']} read_fail={skip['read_fail']}"
    )
    if skip["scrape_fail"] or skip["no_safetix"]:
        msgs.append(
            "+ tip: run --refresh-pass-safetix SITE --all-passes to patch layout in-place "
            "on passes regen cannot scrape (keeps existing HTML + barcodes)"
        )

    if not jobs:
        return 0, msgs

    cache_path = event_media_cache or _default_event_media_cache_path()
    try:
        n_cache_hero = _enrich_scraped_pass_accs_from_site([j["acc"] for j in jobs], root)
        if n_cache_hero:
            msgs.append(f"+ hero restored from site cache/assets: {n_cache_hero} row(s)")
    except Exception as e:
        msgs.append(f"hero cache restore: {e}")

    if resolve_event_images or download_event_images:
        try:
            enrich_event_media_for_blocks(
                [j["acc"] for j in jobs],
                html_out=root / "index.html",
                cache_path=cache_path,
                resolve_discovery=bool(resolve_event_images),
                download_local=bool(download_event_images),
            )
            msgs.append(f"+ event hero enrich ({len(jobs)} pass(es))")
        except Exception as e:
            msgs.append(f"hero image enrich: {e}")
    else:
        try:
            enrich_event_media_for_blocks(
                [j["acc"] for j in jobs],
                html_out=root / "index.html",
                cache_path=cache_path,
                resolve_discovery=False,
                download_local=False,
            )
        except Exception as e:
            msgs.append(f"hero cache file enrich: {e}")

    n_ok = 0
    n_unchanged = 0
    for job in jobs:
        new_doc = _render_regen_pass_document(
            acc=job["acc"],
            raw=job["raw"],
            rel=job["rel"],
            root=root,
            gid=job["gid"],
            fname=job["fname"],
            reg=reg,
            mail_api=mail_api,
        )
        if new_doc == job["raw"]:
            n_unchanged += 1
            continue
        try:
            job["path"].write_text(new_doc, encoding="utf-8", newline="\n")
        except OSError as e:
            msgs.append(f"{job['rel']}: write {e}")
            continue
        n_ok += 1
        if n_ok <= 8 or n_ok % 5000 == 0:
            msgs.append(f"+ regen {job['rel']}")

    msgs.append(f"+ done: rebuilt={n_ok} unchanged={n_unchanged} jobs={len(jobs)}")
    return n_ok, msgs


def refresh_pass_safetix_runtime_in_site_dir(
    site_dir: Path,
    *,
    resolve_event_images: bool = False,
    download_event_images: bool = False,
    event_media_cache: Path | None = None,
    only_pass_rel: str = "",
) -> tuple[int, list[str]]:
    """
    Patch **existing** ``tickets/<gid>/*.html``: remove PDF417 debug markup, inject refresh-barcode
    button + canvas/hero sizing CSS when missing, repair gradient-only heroes from event media cache,
    and replace the CryptoJS + bwip-js + inline SafeTix IIFE with the current ``_safetix_live_barcode_scripts()``.
    Embedded ``data-tm-safetix`` payloads are unchanged. Skips **registry transfer-stub** pages: no
    CryptoJS/bwip/``data-tm-safetix`` in the file plus stub title or stub body copy (**not** file-prefix
    heuristics — barcode scripts often live at EOF).
    """
    msgs: list[str] = []
    root = site_dir.expanduser().resolve()
    tdir = root / "tickets"
    if not tdir.is_dir():
        return 0, msgs
    if only_pass_rel:
        msgs.append(f"+ only pass: {only_pass_rel}")
    fresh = _safetix_live_barcode_scripts()
    pending: list[tuple[Path, str, str]] = []
    hero_rows: list[dict] = []
    safetix_stats = {"replaced": 0, "injected": 0, "noop": 0, "no_target": 0}

    for gid_dir in sorted(tdir.iterdir(), key=lambda p: p.name):
        if not gid_dir.is_dir() or gid_dir.name.startswith("."):
            continue
        if not gid_dir.name.isdigit():
            continue
        for html_path in sorted(gid_dir.glob("*.html")):
            rel = html_path.relative_to(root).as_posix()
            if not _pass_rel_matches_only(rel, only_pass_rel):
                continue
            capped, read_err = _read_pass_html_for_refresh(html_path)
            if read_err:
                msgs.append(f"{rel}: {read_err}, skip")
                continue
            if not capped:
                msgs.append(f"{rel}: read bytes failed, skip")
                continue
            head = capped[:98304] if len(capped) > 98304 else capped
            if _should_skip_ticket_html_as_registry_transfer_stub(
                sample_head=head, full_scan=capped
            ):
                msgs.append(f"{rel}: transfer stub page, skip")
                continue
            try:
                raw = capped.decode("utf-8", errors="replace")
            except Exception as e:
                msgs.append(f"{rel}: decode {e}")
                continue
            hero_rows.extend(_events_missing_hero_in_pass_html(raw))
            pending.append((html_path, rel, raw))

    if (resolve_event_images or download_event_images) and hero_rows:
        cache_path = event_media_cache or _default_event_media_cache_path()
        try:
            enrich_event_media_for_blocks(
                [{"barcode_tokens": hero_rows, "upcoming": []}],
                html_out=root / "index.html",
                cache_path=cache_path,
                resolve_discovery=bool(resolve_event_images),
                download_local=bool(download_event_images),
            )
            msgs.append(f"+ hero enrich ({len(hero_rows)} event(s) missing poster)")
        except Exception as e:
            msgs.append(f"hero image enrich: {e}")

    n_ok = 0
    for html_path, rel, raw in pending:
        new = _strip_safetix_debug_from_pass_html(raw)
        new = _patch_pass_barcode_ui_html(new)
        new = _patch_pass_hero_images_in_html(new, root)
        new, sfx = _upsert_safetix_runtime_scripts(new, fresh)
        safetix_stats[sfx] = safetix_stats.get(sfx, 0) + 1
        if sfx == "no_target" and re.search(r"data-tm-safetix\s*=", raw, re.IGNORECASE):
            msgs.append(f"{rel}: data-tm-safetix but could not upsert runtime")
        if new == raw:
            continue
        try:
            html_path.write_text(new, encoding="utf-8", newline="\n")
        except OSError as e:
            msgs.append(f"{rel}: write {e}")
            continue
        n_ok += 1
        msgs.append(f"+ refreshed {rel}")
    if pending:
        msgs.append(
            f"+ safetix runtime: {safetix_stats.get('replaced', 0)} replaced, "
            f"{safetix_stats.get('injected', 0)} injected, "
            f"{safetix_stats.get('no_target', 0)} no barcode slot"
        )
    return n_ok, msgs


def _pass_slug_salt_from_row(row: dict | None) -> str:
    """Extra slug material (ticket ids / reclaim run) — does not affect embedded QR config."""
    if not isinstance(row, dict):
        return ""
    parts: list[str] = []
    for key in ("pass_instance", "ticket_group_id", "ticket_id"):
        v = str(row.get(key) or "").strip()
        if v:
            parts.append(v)
    return "\0".join(parts)


def _ticket_standalone_html_name(
    acc_idx: int, sub_idx: int, cfg_b64: str, *, slug_salt: str = ""
) -> str:
    """Stable opaque filename per ticket (SecurePass-style), e.g. tickets/3/XqZmY-hAolLAOPz2hHdm.html."""
    raw = hashlib.sha256(
        f"{acc_idx}\0{sub_idx}\0{cfg_b64}\0{slug_salt or ''}".encode("utf-8")
    ).digest()[:15]
    slug = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{slug}.html"


def _account_bundle_html_name(acc_idx: int, slots: list[tuple[str, str, bool, dict]]) -> str:
    """One HTML file per account: hash all secure_token blobs so the name is stable when seat count changes."""
    if not slots:
        return "empty.html"
    parts = b"\0".join(s[0].encode("utf-8", errors="replace") for s in slots)
    raw = hashlib.sha256(f"{acc_idx}\0".encode("utf-8") + parts).digest()[:15]
    slug = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{slug}.html"


def _ticket_href_clean(fname: str) -> str:
    """URL path segment for links (Vercel cleanUrls: no .html in visible href)."""
    f = (fname or "").strip()
    return f[:-5] if f.lower().endswith(".html") else f


def _tm_chrome_topbar_html(
    shell: str,
    topbar_subtitle: str,
    *,
    home_login_button: bool = False,
    my_tickets_href: str = "",
) -> str:
    my_tix = ((my_tickets_href or "").strip() or _DEFAULT_TM_MY_TICKETS_URL)
    if shell == "ticket_minimal":
        sub = (topbar_subtitle or "").strip() or "My tickets"
        return (
            '<header class="tm-pass-chrome-bar tm-pass-chrome-bar--app" role="banner">'
            '<div class="tm-pass-chrome-inner">'
            '<a class="tm-pass-chrome-brand" href="https://www.ticketmaster.com" target="_blank" '
            'rel="noopener noreferrer" aria-label="Ticketmaster">'
            f'<img class="tm-wordmark-img tm-wordmark-img--chrome-app" src="{_TM_WORDMARK_WIKIMEDIA_SVG}" '
            'width="132" height="22" alt="Ticketmaster" loading="eager" decoding="async" '
            'referrerpolicy="no-referrer"/>'
            "</a>"
            f'<span class="tm-pass-chrome-tag tm-pass-chrome-tag--app">{_escape(sub)}</span>'
            "</div></header>"
        )
    if shell == "retail_full":
        return (
            '<div class="topbar topbar--tm">'
            '<div class="tm-util-bar">'
            '<nav class="tm-util-nav" aria-label="Quick links">'
            '<a href="https://www.ticketmaster.com/h/hotels.html" target="_blank" rel="noopener noreferrer">Hotels</a>'
            '<a href="https://www.ticketmaster.com/sell" target="_blank" rel="noopener noreferrer">Sell</a>'
            '<a href="https://www.ticketmaster.com/giftcards" target="_blank" rel="noopener noreferrer">Gift Cards</a>'
            '<a href="https://help.ticketmaster.com" target="_blank" rel="noopener noreferrer">Help</a>'
            '<a href="https://www.ticketmaster.com/vip" target="_blank" rel="noopener noreferrer">VIP</a>'
            "</nav></div>"
            '<div class="tm-main-nav">'
            '<div class="tm-main-nav-inner">'
            '<a class="tm-brand-lockup" href="https://www.ticketmaster.com" target="_blank" rel="noopener noreferrer" aria-label="Ticketmaster">'
            f'<img class="tm-wordmark-img tm-wordmark-img--light" src="{_TM_WORDMARK_WIKIMEDIA_SVG}" width="200" height="28" alt="Ticketmaster" loading="eager" decoding="async" referrerpolicy="no-referrer"/>'
            "</a>"
            '<nav class="tm-cat-nav" aria-label="Browse categories">'
            '<a href="https://www.ticketmaster.com/discover/concerts" target="_blank" rel="noopener noreferrer">Concerts</a>'
            '<a href="https://www.ticketmaster.com/discover/sports" target="_blank" rel="noopener noreferrer">Sports</a>'
            '<a href="https://www.ticketmaster.com/discover/arts-theater-comedy" target="_blank" rel="noopener noreferrer">Arts &amp; Theater</a>'
            '<a href="https://www.ticketmaster.com/discover/family" target="_blank" rel="noopener noreferrer">Family</a>'
            '<a href="https://www.ticketmaster.com/discover" target="_blank" rel="noopener noreferrer">Cities</a>'
            "</nav>"
            '<div class="tm-nav-user">'
            '<a href="https://www.ticketmaster.com/" target="_blank" rel="noopener noreferrer">'
            '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="7" r="4" stroke="currentColor" stroke-width="2"/></svg>'
            "Sign In</a></div></div>"
            f'<p class="tm-context-line">{_escape(topbar_subtitle)}</p>'
            "</div></div>"
        )
    # retail_simple — one normal blue bar (logo + context or Log in)
    if home_login_button:
        right = (
            '<div id="tm-topbar-guest" class="tm-topbar-account-slot">'
            '<button type="button" class="tm-topbar-login-btn" id="tm-topbar-login">Log in</button>'
            "</div>"
            '<div id="tm-topbar-signed" class="tm-topbar-account-slot" hidden>'
            '<div class="tm-account-wrap">'
            '<button type="button" class="tm-topbar-account-trigger" id="tm-topbar-account-btn" '
            'aria-expanded="false" aria-haspopup="true">'
            '<svg class="tm-account-ico" width="18" height="18" viewBox="0 0 24 24" fill="none" '
            'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
            '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round"/>'
            '<circle cx="12" cy="7" r="4" stroke="currentColor" stroke-width="2"/>'
            "</svg>"
            '<span id="tm-topbar-account-label" class="tm-topbar-account-label">Account</span>'
            "</button>"
            '<div id="tm-account-menu" class="tm-account-menu" hidden role="menu">'
            '<div class="tm-account-menu-header">'
            '<p class="tm-account-menu-email" id="tm-account-menu-email"></p>'
            "</div>"
            '<div class="tm-account-menu-body">'
            f'<a href="{_escape(my_tix)}" class="tm-account-menu-item" id="tm-menu-my-tickets" role="menuitem">'
            "My tickets</a>"
            '<p class="tm-account-menu-hint">More settings soon.</p>'
            "</div>"
            '<div class="tm-account-menu-sep" aria-hidden="true"></div>'
            '<button type="button" class="tm-account-menu-item tm-account-menu-signout" id="tm-menu-sign-out" '
            'role="menuitem">Sign out</button>'
            "</div></div></div>"
        )
    else:
        right = f'<p class="tm-simple-context">{_escape(topbar_subtitle)}</p>'
    return (
        '<header class="topbar topbar--tm topbar--simple" role="banner">'
        '<div class="tm-simple-bar">'
        '<a class="tm-brand-lockup tm-brand-lockup--simple" href="https://www.ticketmaster.com" target="_blank" rel="noopener noreferrer" aria-label="Ticketmaster">'
        f'<img class="tm-wordmark-img tm-wordmark-img--light" src="{_TM_WORDMARK_WIKIMEDIA_SVG}" width="180" height="26" alt="Ticketmaster" loading="eager" decoding="async" referrerpolicy="no-referrer"/>'
        "</a>"
        f"{right}"
        "</div></header>"
    )


def _tm_chrome_footer_html(shell: str) -> str:
    if shell == "ticket_minimal":
        return (
            '<footer class="tm-site-footer tm-site-footer--pass-minimal" role="contentinfo">'
            '<div class="tm-footer-pass-inner">'
            '<p class="tm-footer-pass-line tm-footer-pass-line--strong">'
            "Ticketmaster, Attn: Fan Support,"
            "</p>"
            "<p class=\"tm-footer-pass-line\">7060 Hollywood Blvd, Los Angeles, CA 90028</p>"
            "<p class=\"tm-footer-pass-line tm-footer-pass-line--copy\">"
            "\u00a9 2026 Ticketmaster. All rights reserved."
            "</p></div></footer>"
        )
    return (
        '<footer class="tm-site-footer tm-site-footer--simple" role="contentinfo">'
        '<p class="tm-footer-legal">'
        '<a href="https://www.ticketmaster.com" target="_blank" rel="noopener noreferrer">Ticketmaster.com</a>'
        "</p></footer>"
    )


def _tm_pass_transfer_page_inject(
    transfer_relpath: str,
    *,
    mail_api_base: str = "",
    link_transfer_secret: str = "",
) -> str:
    """Modal + scripts for **Transfer to buyer** on standalone pass pages (viewer API builds only).

    ``mail_api_base`` is baked inline so https sites never depend on fetching ``/tm_viewer_mail_api_base.js``
    (avoids 404 when Vercel rewrite/static is missing). Empty string → browser uses same-origin ``apiBase()``.
    ``link_transfer_secret`` is baked from ``tm_viewer_link_registry.json`` so the holder of the pass page
    can POST ``transfer-to-buyer`` without OTP (same-origin + secret proves access to the pass).
    """
    p = (transfer_relpath or "").strip().replace("\\", "/")
    if not p:
        return ""
    path_js = json.dumps(p)
    mail_js = json.dumps((mail_api_base or "").strip().rstrip("/"))
    cap_js = json.dumps((link_transfer_secret or "").strip())
    core = f"""<style>
.tm-pass-transfer-modal[hidden]{{display:none!important}}
.tm-pass-transfer-modal{{position:fixed;inset:0;z-index:200;display:flex;align-items:center;justify-content:center;padding:max(12px,env(safe-area-inset-top));box-sizing:border-box}}
.tm-pass-transfer-backdrop{{position:absolute;inset:0;background:rgba(15,23,42,.45)}}
.tm-pass-transfer-panel{{position:relative;max-width:420px;width:100%;max-height:90vh;overflow:auto;background:#fff;border-radius:12px;padding:1.1rem 1.15rem 1rem;box-shadow:0 24px 60px rgba(2,18,31,.2)}}
.tm-pass-transfer-panel h3{{margin:0 0 .4rem;font-size:1.05rem}}
.tm-pass-transfer-panel .tm-muted{{margin:0 0 .75rem;font-size:.8125rem;color:#64748b;line-height:1.45}}
.tm-pass-transfer-field{{margin-bottom:.65rem}}
.tm-pass-transfer-field label{{display:block;font-size:.7rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#64748b;margin-bottom:.25rem}}
.tm-pass-transfer-field input,.tm-pass-transfer-field textarea{{width:100%;box-sizing:border-box;border:1px solid #c5ced8;border-radius:8px;padding:.45rem .55rem;font:inherit}}
.tm-pass-transfer-field textarea{{min-height:4.5rem;resize:vertical}}
.tm-pass-transfer-actions{{display:flex;gap:10px;justify-content:flex-end;margin-top:.75rem;flex-wrap:wrap}}  
.tm-pass-transfer-actions button{{font:inherit;padding:.5rem 1rem;border-radius:8px;cursor:pointer;border:none}}
#tm-pass-transfer-cancel{{background:#e2e8f0;color:#0f172a}}
#tm-pass-transfer-send{{background:#026cdf;color:#fff;font-weight:700}}
#tm-pass-transfer-send:disabled{{opacity:.55;cursor:not-allowed}}
#tm-pass-transfer-status{{min-height:1.2rem;font-size:.8rem;margin:.35rem 0 0}}
#tm-pass-transfer-status.tm-ok{{color:#059669}}
#tm-pass-transfer-status.tm-err{{color:#b91c1c;white-space:pre-wrap;max-height:12rem;overflow-y:auto;line-height:1.35;font-size:0.72rem}}
.tm-pass-btn.tm-pass-transfer{{border:1.5px solid #7c3aed;color:#5b21b6;background:linear-gradient(180deg,rgba(124,58,237,.14) 0%,rgba(91,33,182,.09) 100%);flex-direction:column;gap:1px;padding:10px 8px}}
.tm-pass-btn.tm-pass-transfer:hover{{background:linear-gradient(180deg,rgba(124,58,237,.22) 0%,rgba(91,33,182,.15) 100%)}}
.tm-pass-transfer-stack{{display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1.12;text-align:center}}
.tm-pass-transfer-label{{font-size:0.78rem;font-weight:800;color:#4c1d95;letter-spacing:.02em}}
.tm-pass-transfer-line1{{font-size:0.58rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#6d28d9}}
.tm-pass-transfer-line2{{font-size:0.78rem;font-weight:800;color:#4c1d95;letter-spacing:.01em}}
</style>
<div id="tm-pass-transfer-modal" class="tm-pass-transfer-modal" hidden aria-hidden="true">
<div class="tm-pass-transfer-backdrop" id="tm-pass-transfer-backdrop"></div>
<div class="tm-pass-transfer-panel" role="dialog" aria-labelledby="tm-pass-transfer-title">
<h3 id="tm-pass-transfer-title">Transfer</h3>
<p class="tm-muted">You do not need to sign in to transfer: this page includes a private transfer key. After you send, the buyer gets the email with a private link; opening the same URL without that access will only show a transferred notice.</p>
<div class="tm-pass-transfer-field"><label for="tm-pass-transfer-buyer-email">Buyer email</label><input type="email" id="tm-pass-transfer-buyer-email" autocomplete="email" placeholder="buyer@email.com"/></div>
<div class="tm-pass-transfer-field"><label for="tm-pass-transfer-buyer-name">Buyer first name <span style="font-weight:400">(optional)</span></label><input type="text" id="tm-pass-transfer-buyer-name" autocomplete="given-name" placeholder="First name"/></div>
<div class="tm-pass-transfer-field"><label for="tm-pass-transfer-personal-from">Message from <span style="font-weight:400">(optional)</span></label><input type="text" id="tm-pass-transfer-personal-from" maxlength="120" placeholder="Chris" autocomplete="off"/></div>
<div class="tm-pass-transfer-field"><label for="tm-pass-transfer-personal-msg">Personal message <span style="font-weight:400">(optional)</span></label><textarea id="tm-pass-transfer-personal-msg" rows="3" maxlength="4000" placeholder="Enjoy the show!"></textarea></div>
<p id="tm-pass-transfer-status" role="status"></p>
<div class="tm-pass-transfer-actions"><button type="button" id="tm-pass-transfer-cancel">Cancel</button><button type="button" id="tm-pass-transfer-send">Send</button></div>
</div></div>
<script src="/tm_viewer_api_base.js"></script>
<script>/* TM_VIEWER_MAIL_API_BASE inlined — no GET /tm_viewer_mail_api_base.js */
window.TM_VIEWER_MAIL_API_BASE = {mail_js};</script>
<script src="/tm_viewer_login_url.js"></script>
<script>
(function () {{
  var TRANSFER_PATH = {path_js};
  var LINK_TRANSFER_SECRET = {cap_js};
  var TOKEN_KEY = 'tm_viewer_session_token';
  function authGet(k) {{
    try {{ return localStorage.getItem(k); }} catch (e) {{ return null; }}
  }}
  function loginUrl() {{
    var u = typeof window.TM_VIEWER_LOGIN_URL === 'string' ? window.TM_VIEWER_LOGIN_URL.trim() : '';
    return u || '/login';
  }}
  function apiBase() {{
    var b = typeof window.TM_VIEWER_API_BASE === 'string' ? window.TM_VIEWER_API_BASE.trim() : '';
    b = b ? b.replace(/\\/+$/, '') : '';
    if (b) return b;
    try {{
      if (typeof window.location !== 'undefined' && window.location.origin)
        return String(window.location.origin).replace(/\\/+$/, '');
    }} catch (e0) {{}}
    return '';
  }}
  function mailApiBase() {{
    var m = typeof window.TM_VIEWER_MAIL_API_BASE === 'string' ? window.TM_VIEWER_MAIL_API_BASE.trim() : '';
    m = m ? m.replace(/\\/+$/, '') : '';
    try {{
      if (m && typeof window.location !== 'undefined' && window.location.protocol === 'https:' && /^http:\\/\\//i.test(m))
        m = '';
    }} catch (eM) {{}}
    if (m) return m;
    return apiBase();
  }}
  function transferPostUrl() {{
    var b = mailApiBase();
    return b ? String(b).replace(/\\/+$/, '') + '/api/tm-viewer/transfer-to-buyer' : '';
  }}
  var transferModal = document.getElementById('tm-pass-transfer-modal');
  var transferBackdrop = document.getElementById('tm-pass-transfer-backdrop');
  var transferBtnCancel = document.getElementById('tm-pass-transfer-cancel');
  var transferBtnSend = document.getElementById('tm-pass-transfer-send');
  var transferInpEmail = document.getElementById('tm-pass-transfer-buyer-email');
  var transferInpName = document.getElementById('tm-pass-transfer-buyer-name');
  var transferInpFrom = document.getElementById('tm-pass-transfer-personal-from');
  var transferInpMsg = document.getElementById('tm-pass-transfer-personal-msg');
  var transferStatus = document.getElementById('tm-pass-transfer-status');
  function setTransferStatus(msg, ok, err) {{
    if (!transferStatus) return;
    transferStatus.textContent = msg || '';
    transferStatus.className = err ? 'tm-err' : (ok ? 'tm-ok' : '');
  }}
  function closeTransferModal() {{
    if (!transferModal) return;
    transferModal.hidden = true;
    transferModal.setAttribute('aria-hidden', 'true');
  }}
  function openTransferModal() {{
    if (!transferModal) return;
    setTransferStatus('', false, false);
    if (transferInpEmail) transferInpEmail.value = '';
    if (transferInpName) transferInpName.value = '';
    if (transferInpFrom) transferInpFrom.value = '';
    if (transferInpMsg) transferInpMsg.value = '';
    transferModal.hidden = false;
    transferModal.setAttribute('aria-hidden', 'false');
    if (transferInpEmail) transferInpEmail.focus();
  }}
  document.addEventListener('click', function (e) {{
    var t = e.target;
    if (t && t.closest && t.closest('.tm-pass-transfer-open')) {{
      e.preventDefault();
      openTransferModal();
    }}
  }});
  if (transferBackdrop) transferBackdrop.addEventListener('click', closeTransferModal);
  if (transferBtnCancel) transferBtnCancel.addEventListener('click', closeTransferModal);
  if (transferBtnSend) {{
    transferBtnSend.addEventListener('click', function () {{
      var base = apiBase();
      var transferUrl = transferPostUrl();
      var cap = (LINK_TRANSFER_SECRET || '').trim();
      var tok = (authGet(TOKEN_KEY) || '').trim();
      if (!base) {{
        setTransferStatus('Ticket server is not configured (TM_VIEWER_API_BASE / tm_viewer_api_base.js).', false, true);
        return;
      }}
      if (!transferUrl) {{
        setTransferStatus('Cannot reach transfer API (mail API base empty on HTTPS).', false, true);
        return;
      }}
      if (!cap && !tok) {{
        setTransferStatus('This page has no transfer key and you are not signed in. Regenerate or re-inject passes with tm_viewer_link_registry.json next to the site, then sync that JSON to the API server.', false, true);
        return;
      }}
      var em = (transferInpEmail && transferInpEmail.value || '').trim();
      if (!em || em.indexOf('@') < 0) {{
        setTransferStatus('Enter the buyer\\'s email.', false, true);
        return;
      }}
      transferBtnSend.disabled = true;
      setTransferStatus('Sending…', false, false);
      var bodyObj = {{
        to_email: em,
        path: TRANSFER_PATH,
        buyer_name: (transferInpName && transferInpName.value || '').trim(),
        personal_from_name: (transferInpFrom && transferInpFrom.value || '').trim(),
        personal_message: (transferInpMsg && transferInpMsg.value || '').trim(),
        public_base: (window.location.origin || '').replace(/\\/+$/, '')
      }};
      if (cap) bodyObj.link_transfer_secret = cap;
      // Pass-page proof is the baked secret; omit session token so a stale login cannot cause pass_not_found_for_account.
      if (!cap && tok) bodyObj.token = tok;
      fetch(transferUrl, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(bodyObj)
      }})
        .then(function (r) {{ return r.json().then(function (j) {{ return {{ okHttp: r.ok, j: j }}; }}); }})
        .then(function (x) {{
          transferBtnSend.disabled = false;
          var j = x.j || {{}};
          if (j.ok) {{
            setTransferStatus('Transfer sent.', true, false);
            setTimeout(function () {{ window.location.href = '/my-tickets'; }}, 600);
            return;
          }}
          var msg = (j.detail && String(j.detail)) || '';
          if (!msg && j.error === 'upstream_bad_response') {{
            var parts = [];
            if (j.upstream_http_status != null) parts.push('HTTP ' + j.upstream_http_status);
            if (j.upstream_last) parts.push('Last URL: ' + j.upstream_last);
            if (j.upstream_preview) parts.push('Body: ' + String(j.upstream_preview).slice(0, 500));
            if (j.tried_urls && j.tried_urls.length) parts.push('Tried:\\n' + j.tried_urls.join('\\n'));
            if (j.stubby_log_file) parts.push('Log: ' + j.stubby_log_file);
            if (j.fix) parts.push(String(j.fix));
            msg = parts.length ? parts.join('\\n\\n') : 'upstream_bad_response';
          }}
          if (!msg) msg = j.error || 'Transfer failed.';
          if (msg.length > 4000) msg = msg.slice(0, 3997) + '...';
          setTransferStatus(msg, false, true);
        }})
        .catch(function () {{
          transferBtnSend.disabled = false;
          setTransferStatus('Network error.', false, true);
        }});
    }});
  }}
}})();
</script>
"""
    return (
        "<!-- TM_VIEWER_PASS_TRANSFER_UI_BEGIN -->\n"
        + core
        + "\n<!-- TM_VIEWER_PASS_TRANSFER_UI_END -->\n"
    )


def _strip_pass_transfer_inject_block(html: str) -> tuple[str, bool]:
    """Remove a prior pass-page transfer inject. Returns (new_html, removed_ok)."""
    begin = "<!-- TM_VIEWER_PASS_TRANSFER_UI_BEGIN -->"
    end = "<!-- TM_VIEWER_PASS_TRANSFER_UI_END -->"
    if begin in html and end in html:
        i = html.find(begin)
        j = html.find(end, i)
        if j < 0:
            return html, False
        j2 = j + len(end)
        while j2 < len(html) and html[j2] in "\r\n":
            j2 += 1
        return html[:i] + html[j2:], True
    # Legacy injects (no markers): style + modal + scripts ending with }})(); </script>
    pat = re.compile(
        r"<style>\s*\.tm-pass-(?:txfer|transfer)-modal\[hidden\][\s\S]*?\}\)\(\);\s*</script>\s*",
        re.IGNORECASE,
    )
    m = pat.search(html)
    if not m:
        return html, False
    return html[: m.start()] + html[m.end() :], True


def _ensure_link_transfer_secret_for_pass_in_registry_file(
    site_root: Path, *, gid: str, fname: str
) -> str:
    """If ``tm_viewer_link_registry.json`` lists this pass but has no ``link_transfer_secret``, add one and save.

    The transfer API requires ``link_transfer_secret`` (or an OTP session). Inject previously omitted the secret;
    this backfills so holders can transfer without signing in. Copy/sync the updated JSON to the API host.
    """
    reg_path = site_root / "tm_viewer_link_registry.json"
    if not reg_path.is_file():
        return ""
    try:
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(reg, dict):
        return ""
    be = reg.get("by_email")
    if not isinstance(be, dict):
        return ""
    want = f"tickets/{int(gid)}/{fname}"
    new_sec: str | None = None
    for lst in be.values():
        if not isinstance(lst, list):
            continue
        for t in lst:
            if not isinstance(t, dict):
                continue
            p = str(t.get("path") or "")
            if not _registry_paths_ticket_equiv(p, want):
                continue
            cur = str(t.get("link_transfer_secret") or "").strip()
            if cur:
                return cur
            new_sec = secrets.token_urlsafe(32)
            t["link_transfer_secret"] = new_sec
            break
        if new_sec:
            break
    if not new_sec:
        return ""
    try:
        reg_path.write_text(
            json.dumps(reg, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except OSError:
        return ""
    return new_sec


_ARRIVAL_WARNING_MARK = "tm-arrival-warning"
_ARRIVAL_WARNING_CSS = (
    "<style>"
    ".tm-arrival-warning{"
    "display:flex;align-items:flex-start;gap:0.5rem;margin:0;"
    "padding:0.6rem 0.9rem;background:#026cdf;border-bottom:2px solid #0153a3;"
    "font-size:0.74rem;line-height:1.5;color:#fff;flex-shrink:0;"
    "width:100%;box-sizing:border-box;}"
    ".tm-arrival-warning__icon{font-size:1rem;flex-shrink:0;line-height:1.5;}"
    ".tm-arrival-warning__title{display:block;font-size:0.72rem;font-weight:800;"
    "letter-spacing:0.04em;text-transform:uppercase;margin-bottom:0.2rem;color:#fff;}"
    ".tm-arrival-warning__countdown{font-weight:700;color:#fff;}"
    ".tm-arrival-warning__body{font-size:0.72rem;color:rgba(255,255,255,0.92);line-height:1.5;}"
    ".tm-arrival-warning__body strong{color:#fff;font-weight:700;}"
    ".tm-arrival-warning__body .tm-warn-red{color:#ffd0cc;font-weight:700;}"
    "@media(max-width:480px){"
    ".tm-arrival-warning{padding:0.5rem 0.75rem;}"
    ".tm-arrival-warning__title{font-size:0.68rem;}"
    ".tm-arrival-warning__body{font-size:0.68rem;}}"
    "</style>"
)


def inject_arrival_warning_into_site_dir(
    site_dir: Path, *, replace_existing: bool = False
) -> tuple[int, list[str]]:
    """
    Patch **existing** ``tickets/<gid>/*.html`` files: inject the 45-minute arrival warning
    banner immediately before ``<main>`` in each pass page.

    Safe to run on already-generated sites — skips files that already have the banner unless
    ``replace_existing=True``.  Use ``replace_existing`` after updating the banner copy.
    """
    msgs: list[str] = []
    root = site_dir.expanduser().resolve()
    tdir = root / "tickets"
    if not tdir.is_dir():
        msgs.append(f"No tickets/ directory under {root}")
        return 0, msgs
    main_pat = re.compile(r"<main\b", re.IGNORECASE)
    n_ok = 0
    for gid_dir in sorted(tdir.iterdir(), key=lambda p: p.name):
        if not gid_dir.is_dir() or gid_dir.name.startswith(".") or not gid_dir.name.isdigit():
            continue
        for html_path in sorted(gid_dir.glob("*.html")):
            rel = html_path.relative_to(root).as_posix()
            try:
                src = html_path.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                msgs.append(f"{rel}: read error {e}")
                continue
            has_banner = _ARRIVAL_WARNING_MARK in src
            if has_banner and not replace_existing:
                msgs.append(f"{rel}: already has arrival warning, skip (use --replace-arrival-warning to refresh)")
                continue
            if has_banner and replace_existing:
                # Strip old banner div + optional preceding CSS <style> block we injected
                src = re.sub(
                    r'<style>[^<]*\.tm-arrival-warning[^<]*</style>\s*',
                    '',
                    src,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                src = re.sub(
                    r'<div\s+class="tm-arrival-warning"[^>]*>[\s\S]*?</div>\s*</div>\s*',
                    '',
                    src,
                    count=1,
                    flags=re.IGNORECASE,
                )
                msgs.append(f"{rel}: removed old arrival warning")
            m = main_pat.search(src)
            if not m:
                msgs.append(f"{rel}: <main> not found — unexpected template, skip")
                continue
            css_block = "" if ".tm-arrival-warning" in src else _ARRIVAL_WARNING_CSS + "\n"
            banner = _tm_arrival_warning_banner_html()
            src = src[: m.start()] + css_block + banner + "\n" + src[m.start():]
            try:
                html_path.write_text(src, encoding="utf-8")
            except OSError as e:
                msgs.append(f"{rel}: write error {e}")
                continue
            msgs.append(f"+ injected arrival warning {rel}")
            n_ok += 1
    return n_ok, msgs


def inject_pass_transfer_ui_into_site_dir(
    site_dir: Path, *, replace_existing: bool = False, mail_api_base: str = ""
) -> tuple[int, list[str]]:
    """
    Patch **existing** ``tickets/<gid>/*.html`` files: add **Transfer** (third action button) + modal/scripts if missing.

    Use when passes were generated before the viewer API gate was enabled, or copied without transfer tail.
    ``site_dir`` is the site root that contains ``tickets/`` (e.g. ``tm-vercel-site`` or ``public``).

    Pass ``replace_existing=True`` to strip a prior inject and re-insert the current one (needed after
    ``tm_hit_viewer`` updates; a plain inject skips files that already have the modal).
    ``mail_api_base`` is baked into the pass page (no ``/tm_viewer_mail_api_base.js`` request); use ``""``
    for https + same-origin Vercel → stubby.
    """
    msgs: list[str] = []
    root = site_dir.expanduser().resolve()
    tdir = root / "tickets"
    if not tdir.is_dir():
        msgs.append(f"No tickets/ directory under {root}")
        return 0, msgs
    btn = (
        '<button type="button" class="tm-pass-btn tm-pass-transfer tm-pass-transfer-open" '
        'aria-label="Transfer to buyer">'
        '<span class="tm-pass-transfer-stack">'
        '<span class="tm-pass-transfer-label">Transfer</span>'
        "</span></button>"
    )
    _transfer_open_btn_strip_re = re.compile(
        r'<button\s[^>]*\btm-pass-transfer-open\b[^>]*>[\s\S]*?</button>',
        re.IGNORECASE,
    )
    actions_pat = re.compile(r'<div\s+class="tm-pass-actions"\s*>', re.IGNORECASE)
    crypto_anchor = '<script src="https://cdnjs.cloudflare.com/ajax/libs/crypto-js'
    n_ok = 0
    reg: dict = {}
    reg_path = root / "tm_viewer_link_registry.json"
    if reg_path.is_file():
        try:
            _reg_load = json.loads(reg_path.read_text(encoding="utf-8"))
            if isinstance(_reg_load, dict):
                reg = _reg_load
        except (OSError, json.JSONDecodeError, TypeError):
            reg = {}
    for gid_dir in sorted(tdir.iterdir(), key=lambda p: p.name):
        if not gid_dir.is_dir() or gid_dir.name.startswith("."):
            continue
        if not gid_dir.name.isdigit():
            continue
        for html_path in sorted(gid_dir.glob("*.html")):
            rel = html_path.relative_to(root).as_posix()
            try:
                fsize = html_path.stat().st_size
            except OSError:
                fsize = 0
            capped = _read_ticket_html_bytes_capped(html_path)
            if not capped and fsize > 0:
                msgs.append(f"{rel}: read bytes failed, skip")
                continue
            head = capped[:98304] if len(capped) > 98304 else capped
            if _should_skip_ticket_html_as_registry_transfer_stub(
                sample_head=head, full_scan=capped
            ):
                msgs.append(f"{rel}: transfer stub page, skip")
                continue
            try:
                new = capped.decode("utf-8", errors="replace")
            except Exception as e:
                msgs.append(f"{rel}: decode {e}")
                continue
            has_modal = 'id="tm-pass-transfer-modal"' in new or "tm-pass-transfer-modal" in new
            if has_modal and not replace_existing:
                msgs.append(f"{rel}: already has transfer modal, skip (use --replace-pass-transfer-ui to refresh)")
                continue
            if has_modal and replace_existing:
                stripped, ok_strip = _strip_pass_transfer_inject_block(new)
                if not ok_strip:
                    msgs.append(f"{rel}: replace failed (could not find old transfer block), skip")
                    continue
                new = stripped
                msgs.append(f"{rel}: removed old transfer UI")
            matches = list(actions_pat.finditer(new))
            if not matches:
                msgs.append(f"{rel}: no tm-pass-actions — skip (unexpected template)")
                continue
            for m in reversed(matches):
                j = m.end()
                slice_end = new.find("</div>", j)
                if slice_end < 0:
                    continue
                chunk = new[j:slice_end]
                if "tm-pass-transfer-stack" in chunk:
                    continue
                if "tm-pass-transfer-open" in chunk:
                    chunk2 = _transfer_open_btn_strip_re.sub("", chunk)
                    new = new[:j] + chunk2 + btn + new[slice_end:]
                    continue
                new = new[:j] + chunk + btn + new[slice_end:]
            xfer = f"tickets/{gid_dir.name}/{html_path.stem}"
            cap = ""
            if reg:
                cap = _registry_link_secret_for_site_pass(
                    reg, gid=int(gid_dir.name), fname=html_path.name
                )
            if not cap:
                cap = _ensure_link_transfer_secret_for_pass_in_registry_file(
                    root, gid=gid_dir.name, fname=html_path.name
                )
            tail = _tm_pass_transfer_page_inject(
                xfer, mail_api_base=mail_api_base, link_transfer_secret=cap
            )
            if not tail:
                continue
            ins_at = new.find(crypto_anchor)
            if ins_at < 0:
                ins_at = new.lower().rfind("</body>")
            if ins_at < 0:
                msgs.append(f"{rel}: could not find insert point (crypto-js or </body>)")
                continue
            new = new[:ins_at] + tail + "\n" + new[ins_at:]
            try:
                html_path.write_text(new, encoding="utf-8", newline="\n")
            except OSError as e:
                msgs.append(f"{rel}: write {e}")
                continue
            n_ok += 1
            msgs.append(f"+ injected {rel}")
    return n_ok, msgs


def _tm_arrival_warning_banner_html(*, is_sg: bool = False) -> str:
    """Highlighted arrival-notice banner on individual ticket pass pages (ticket_minimal shell)."""
    if is_sg:
        return (
            '<div class="tm-arrival-warning tm-arrival-warning--sg" role="alert" aria-live="polite">'
            '<span class="tm-arrival-warning__icon" aria-hidden="true">⚠️</span>'
            '<div>'
            '<span class="tm-arrival-warning__title">Time-Critical &mdash; Read Before Opening</span>'
            '<div class="tm-arrival-warning__body">'
            'This is a <strong>live rotating QR code</strong> that refreshes every '
            '<strong>30 seconds</strong>. Be at the gate with this page '
            '<strong>already open, full brightness</strong>. '
            '<strong>No screenshots &mdash; they won\'t scan. Do not close this page.</strong>'
            '</div>'
            '</div>'
            '</div>'
        )
    return (
        '<div class="tm-arrival-warning" role="alert" aria-live="polite">'
        '<span class="tm-arrival-warning__icon" aria-hidden="true">⚠️</span>'
        '<div>'
        '<span class="tm-arrival-warning__title">Time-Critical &mdash; Read Before Opening</span>'
        '<div class="tm-arrival-warning__body">'
        '<span class="tm-warn-red">This ticket self-invalidates 15 min before showtime</span> &mdash; '
        'this is a <strong>live rotating SafeTix&trade; barcode</strong> that goes permanently dead if not scanned in time. '
        'Be at the gate with this page <strong>already open, full brightness</strong>, '
        '<strong>45 min early</strong>. Scan immediately at the front. '
        '<strong>No screenshots &mdash; they won\'t scan. Do not close this page.</strong>'
        '</div>'
        '</div>'
        '</div>'
    )


def _tm_html_document(
    *,
    doc_title: str,
    fetch_banner: str,
    main_inner: str,
    topbar_subtitle: str = "My tickets",
    body_class_extra: str = "",
    shell: str = "retail_simple",
    home_topbar_login: bool = False,
    my_tickets_href: str = "",
    pass_page_transfer_tail: str = "",
    reminder_head_metas: str = "",
    reminder_body_tail: str = "",
    pass_is_sg: bool = False,
) -> str:
    demo_note = fetch_banner if fetch_banner else ""
    _body_x = (body_class_extra or "").strip()
    _shell = (shell or "retail_simple").strip()
    _base_cls = "tm-app-body tm-shell-" + _shell.replace("_", "-")
    _body_cls = _base_cls + (f" {_body_x}" if _body_x else "")
    _chrome_top = _tm_chrome_topbar_html(
        _shell,
        topbar_subtitle,
        home_login_button=home_topbar_login,
        my_tickets_href=my_tickets_href,
    )
    _chrome_foot = _tm_chrome_footer_html(_shell)
    _html_viewport_cls = ' class="tm-html-ticket-viewport"' if _shell == "ticket_minimal" else ""
    return f"""<!DOCTYPE html>
<html lang="en"{_html_viewport_cls}>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <meta name="theme-color" content="#026cdf"/>
  <title>{_escape(doc_title)}</title>
{reminder_head_metas}
  <link rel="preconnect" href="https://upload.wikimedia.org"/>
  <link rel="dns-prefetch" href="https://upload.wikimedia.org"/>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet"/>
  <style>
    :root {{
      --tm-blue: #026cdf;
      --tm-blue-mid: #1a7fe0;
      --tm-blue-dark: #0153a3;
      --tm-blue-soft: rgba(2, 108, 223, 0.14);
      --tm-navy: #02121f;
      --tm-navy-panel: #061c2e;
      --tm-navy-deep: #010a12;
      --bg: #ffffff;
      --tm-retail-black: #121212;
      --tm-retail-bar: #000000;
      --tm-page-gray: #f6f7f8;
      --surface: #ffffff;
      --border: #c5ced8;
      --text: #121212;
      --muted: #5c6570;
      --accent: #026cdf;
      --accent2: #059669;
    }}
    * {{ box-sizing: border-box; }}
    html {{
      -webkit-text-size-adjust: 100%;
    }}
    body.tm-app-body {{
      margin: 0;
      font-family: 'Sora', 'Inter', system-ui, sans-serif;
      color: var(--text);
      min-height: 100vh;
      line-height: 1.45;
      background-color: var(--bg);
      display: flex;
      flex-direction: column;
    }}
    .topbar {{
      padding: 0;
      padding-top: env(safe-area-inset-top, 0px);
      background: var(--tm-blue);
      position: sticky;
      top: 0;
      z-index: 20;
      box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
    }}
    .tm-util-bar {{
      background: var(--tm-retail-bar);
      color: #fff;
      font-size: 0.6875rem;
      font-weight: 500;
      letter-spacing: 0.02em;
    }}
    .tm-util-nav {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 0.4rem 1rem;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: center;
      gap: 0.35rem 1rem;
    }}
    .tm-util-nav a {{
      color: rgba(255, 255, 255, 0.92);
      text-decoration: none;
      white-space: nowrap;
    }}
    .tm-util-nav a:hover {{ text-decoration: underline; color: #fff; }}
    .tm-main-nav {{
      background: var(--tm-blue);
      color: #fff;
      padding: 0 0 0.65rem;
    }}
    .tm-main-nav-inner {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 0.65rem 1rem 0;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem 0.75rem;
    }}
    .tm-cat-nav {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: center;
      gap: 0.25rem 0.65rem;
      flex: 1 1 auto;
      font-size: 0.75rem;
      font-weight: 600;
    }}
    .tm-cat-nav a {{
      color: #fff;
      text-decoration: none;
      white-space: nowrap;
      padding: 0.2rem 0;
    }}
    .tm-cat-nav a:hover {{ text-decoration: underline; opacity: 0.95; }}
    .tm-nav-user {{
      display: flex;
      align-items: center;
      gap: 0.35rem;
      font-size: 0.75rem;
      font-weight: 600;
    }}
    .tm-nav-user a {{
      color: #fff;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
    }}
    .tm-nav-user a:hover {{ text-decoration: underline; }}
    .tm-nav-user svg {{ flex-shrink: 0; opacity: 0.95; }}
    .tm-context-line {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 0.35rem 1rem 0;
      font-size: 0.6875rem;
      font-weight: 700;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: rgba(255, 255, 255, 0.78);
      text-align: center;
    }}
    .topbar--simple {{ box-shadow: 0 1px 0 rgba(0, 0, 0, 0.06); }}
    .tm-simple-bar {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 0.7rem 1rem;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem 1rem;
    }}
    .tm-brand-lockup--simple {{ margin-bottom: 0; }}
    .tm-simple-context {{
      margin: 0;
      font-size: 0.6875rem;
      font-weight: 700;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: rgba(255, 255, 255, 0.88);
    }}
    .tm-topbar-login-btn {{
      margin: 0;
      padding: 0.4rem 1rem;
      font-size: 0.6875rem;
      font-weight: 800;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #026cdf;
      background: #fff;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      font-family: inherit;
    }}
    .tm-topbar-login-btn:hover {{ filter: brightness(0.97); }}
    .tm-topbar-account-slot {{
      display: flex;
      align-items: center;
      gap: 0.35rem;
    }}
    #tm-topbar-guest[hidden],
    #tm-topbar-signed[hidden] {{
      display: none !important;
    }}
    .tm-account-wrap {{
      position: relative;
    }}
    .tm-topbar-account-trigger {{
      margin: 0;
      padding: 0.35rem 0.65rem;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.6875rem;
      font-weight: 800;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: #fff;
      background: rgba(255, 255, 255, 0.18);
      border: 1px solid rgba(255, 255, 255, 0.35);
      border-radius: 4px;
      cursor: pointer;
      font-family: inherit;
    }}
    .tm-topbar-account-trigger:hover {{
      background: rgba(255, 255, 255, 0.28);
    }}
    .tm-account-ico {{
      flex-shrink: 0;
      opacity: 0.95;
    }}
    .tm-topbar-account-label {{
      max-width: 120px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .tm-account-menu {{
      position: absolute;
      right: 0;
      top: calc(100% + 8px);
      min-width: 260px;
      max-width: min(320px, calc(100vw - 24px));
      padding: 0;
      background: #fff;
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      box-shadow: 0 12px 40px rgba(2, 18, 31, 0.14), 0 2px 8px rgba(2, 18, 31, 0.06);
      z-index: 50;
      overflow: hidden;
    }}
    .tm-account-menu-header {{
      padding: 0.875rem 1rem 0.7rem;
      border-bottom: 1px solid #f1f5f9;
    }}
    .tm-account-menu-email {{
      margin: 0;
      font-size: 0.8125rem;
      font-weight: 600;
      color: var(--text);
      line-height: 1.45;
      word-break: break-word;
    }}
    .tm-account-menu-body {{
      padding: 0.25rem 0 0.15rem;
    }}
    .tm-account-menu-item {{
      display: flex;
      align-items: center;
      width: 100%;
      margin: 0;
      padding: 0.7rem 1rem;
      font-size: 0.875rem;
      font-weight: 600;
      text-align: left;
      text-decoration: none;
      color: var(--tm-blue);
      background: transparent;
      border: none;
      cursor: pointer;
      font-family: inherit;
      box-sizing: border-box;
      transition: background-color 0.12s ease, color 0.12s ease;
    }}
    .tm-account-menu-item:focus-visible {{
      outline: 2px solid var(--tm-blue);
      outline-offset: -2px;
    }}
    a.tm-account-menu-item:hover,
    a.tm-account-menu-item:focus-visible {{
      background: rgba(2, 108, 223, 0.1);
      color: #0153a3;
    }}
    .tm-account-menu-hint {{
      margin: 0;
      padding: 0.3rem 1rem 0.65rem;
      font-size: 0.75rem;
      color: var(--muted);
      line-height: 1.45;
    }}
    .tm-account-menu-sep {{
      height: 1px;
      margin: 0;
      background: #e8eaed;
    }}
    .tm-account-menu-signout {{
      color: #b91c1c !important;
      padding: 0.75rem 1rem;
    }}
    .tm-account-menu-signout:focus-visible {{
      outline-color: #b91c1c;
    }}
    .tm-account-menu-signout:hover,
    .tm-account-menu-signout:focus-visible {{
      background: rgba(185, 28, 28, 0.09);
      color: #991b1b !important;
    }}
    .tm-viewer-empty-tickets {{
      max-width: 720px;
      margin: 0 auto;
      padding: 0.5rem 1rem 1.25rem;
    }}
    .tm-viewer-empty-tickets p {{
      margin: 0;
      font-size: 0.9rem;
      color: var(--muted);
      line-height: 1.45;
    }}
    .tm-site-footer--simple {{
      padding: 1.1rem 1rem 1.5rem;
      text-align: center;
      border-top: 1px solid #e8eaed;
    }}
    .tm-site-footer--simple .tm-footer-legal {{
      margin: 0;
      font-size: 0.8125rem;
      color: var(--muted);
    }}
    .tm-site-footer--simple a {{
      color: var(--tm-blue);
      font-weight: 700;
      text-decoration: none;
    }}
    .tm-site-footer--simple a:hover {{ text-decoration: underline; }}
    body.tm-shell-ticket-minimal {{
      background: #f4f6f8 !important;
      font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }}
    body.tm-shell-ticket-minimal main {{
      max-width: 468px;
      margin: 0 auto;
      padding: 12px 20px 36px;
      background: transparent;
    }}
    body.tm-shell-ticket-minimal .tm-pass-card {{
      font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }}
    html.tm-html-ticket-viewport {{
      height: auto;
      min-height: 100%;
      min-height: 100dvh;
      overflow-x: hidden;
      overflow-y: auto;
    }}
    @keyframes tm-pass-card-in {{
      from {{ opacity: 0; transform: translateY(8px); }}
      to {{ opacity: 1; transform: none; }}
    }}
    @keyframes tm-pass-soft-fade {{
      from {{ opacity: 0; transform: translateY(4px); }}
      to {{ opacity: 1; transform: none; }}
    }}
    html.tm-html-ticket-viewport .safetix-slot.tm-pass-card {{
      animation: tm-pass-card-in 0.5s cubic-bezier(0.22, 0.61, 0.36, 1) both;
    }}
    html.tm-html-ticket-viewport .tm-pass-rail {{
      animation: tm-pass-soft-fade 0.35s ease both;
    }}
    html.tm-html-ticket-viewport .tm-pass-menu {{
      animation: tm-pass-soft-fade 0.42s cubic-bezier(0.22, 0.61, 0.36, 1) 0.04s both;
    }}
    html.tm-html-ticket-viewport .tm-pass-title,
    html.tm-html-ticket-viewport .tm-pass-sub-line {{
      animation: tm-pass-soft-fade 0.45s cubic-bezier(0.22, 0.61, 0.36, 1) 0.06s both;
    }}
    html.tm-html-ticket-viewport .tm-pass-sub-line:nth-child(1),
    html.tm-html-ticket-viewport .tm-pass-sub-line:nth-child(2),
    html.tm-html-ticket-viewport .tm-pass-sub-line:nth-child(3) {{
      animation-delay: 0.06s;
    }}
    html.tm-html-ticket-viewport body.tm-shell-ticket-minimal {{
      margin: 0;
      min-height: 100%;
      min-height: 100dvh;
      height: auto;
      max-height: none;
      overflow-x: hidden;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      box-sizing: border-box;
    }}
    html.tm-html-ticket-viewport body.tm-shell-ticket-minimal > header.tm-pass-chrome-bar {{
      flex-shrink: 0;
    }}
    html.tm-html-ticket-viewport body.tm-shell-ticket-minimal > .demo-banner {{
      flex-shrink: 0;
    }}
    html.tm-html-ticket-viewport body.tm-shell-ticket-minimal > main {{
      flex: 1 1 0%;
      min-height: 0;
      overflow-x: hidden;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      align-items: stretch;
      padding: 8px 22px 10px;
      box-sizing: border-box;
      width: 100%;
      max-width: 100%;
      -webkit-overflow-scrolling: touch;
    }}
    html.tm-html-ticket-viewport body.tm-shell-ticket-minimal > footer {{
      flex-shrink: 0;
    }}
    html.tm-html-ticket-viewport body.tm-shell-ticket-minimal .acct.acct--tickets-only {{
      flex: 1 1 auto;
      min-height: 0;
      display: flex;
      flex-direction: column;
      overflow-x: hidden;
      overflow-y: visible;
    }}
    html.tm-html-ticket-viewport body.tm-shell-ticket-minimal .tickets-only-panel {{
      flex: 1 1 auto;
      min-height: 0;
      overflow-x: hidden;
      overflow-y: visible;
      display: flex;
      flex-direction: column;
    }}
    /* Touch / narrow viewports: same navigation as desktop (no delayed or swallowed taps). */
    @media (hover: none) and (pointer: coarse), (max-width: 639px) {{
      html.tm-html-ticket-viewport body.tm-shell-ticket-minimal a[href] {{
        touch-action: manipulation;
        -webkit-tap-highlight-color: rgba(2, 108, 223, 0.14);
      }}
      html.tm-html-ticket-viewport body.tm-shell-ticket-minimal button.tm-pass-menu {{
        touch-action: manipulation;
        -webkit-tap-highlight-color: rgba(2, 108, 223, 0.14);
      }}
      html.tm-html-ticket-viewport body.tm-shell-ticket-minimal .tm-carousel-arrow {{
        touch-action: manipulation;
      }}
      .tm-pass-chrome-brand {{
        touch-action: manipulation;
        -webkit-tap-highlight-color: rgba(255, 255, 255, 0.2);
        min-height: 44px;
        min-width: 44px;
        align-items: center;
        justify-content: center;
      }}
      .tm-pass-pager__home--below {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 44px;
        padding: 10px 16px;
        margin-left: auto;
        margin-right: auto;
        box-sizing: border-box;
        touch-action: manipulation;
      }}
      .tm-ticket-carousel:not(.tm-ticket-carousel--single) .tm-carousel-prev,
      .tm-ticket-carousel:not(.tm-ticket-carousel--single) .tm-carousel-next {{
        top: clamp(120px, 28dvh, 220px);
      }}
      body.tm-shell-retail-simple a[href],
      body.tm-shell-retail-full a[href] {{
        touch-action: manipulation;
        -webkit-tap-highlight-color: rgba(2, 108, 223, 0.12);
      }}
    }}
    .tm-pass-viewport-fit {{
      flex: 1 1 auto;
      min-height: 0;
      width: 100%;
      max-width: 468px;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      align-items: stretch;
      justify-content: flex-start;
      overflow-x: hidden;
      overflow-y: visible;
      position: relative;
      box-sizing: border-box;
    }}
    .tm-pass-viewport-fit-inner {{
      transform-origin: top center;
      flex-shrink: 0;
      width: 100%;
      max-width: 100%;
      display: flex;
      flex-direction: column;
      align-items: stretch;
      box-sizing: border-box;
      overflow-x: hidden;
    }}
    .tm-pass-chrome-bar {{
      background: linear-gradient(180deg, #0b74e9 0%, #026cdf 55%, #0256b8 100%);
      box-shadow: 0 2px 8px rgba(2, 60, 174, 0.22);
      padding: 10px 14px 11px;
      padding-top: max(10px, env(safe-area-inset-top, 0px));
    }}
    .tm-pass-chrome-bar--app {{
      background: linear-gradient(180deg, #0b74e9 0%, #026cdf 55%, #0256b8 100%);
      border-top: none;
      border-bottom: 1px solid rgba(0, 0, 0, 0.12);
      box-shadow: 0 2px 8px rgba(2, 60, 174, 0.22);
    }}
    .tm-pass-chrome-inner {{
      max-width: 468px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }}
    .tm-pass-chrome-brand {{
      display: inline-flex;
      align-items: center;
      text-decoration: none;
      flex-shrink: 0;
    }}
    .tm-pass-chrome-brand .tm-wordmark-img {{
      height: 22px;
      width: auto;
      max-width: min(150px, 48vw);
    }}
    .tm-wordmark-img--chrome-app {{
      filter: brightness(0) invert(1);
      height: 20px;
    }}
    .tm-pass-chrome-tag {{
      font-size: 0.65rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: rgba(255, 255, 255, 0.92);
      text-align: right;
      line-height: 1.25;
    }}
    .tm-pass-chrome-tag--app {{
      color: rgba(255, 255, 255, 0.92);
      font-weight: 700;
      letter-spacing: 0.04em;
    }}
    /* Must beat .tm-site-footer (later) — use both classes so blue bar is not overridden by gray retail footer. */
    .tm-site-footer.tm-site-footer--pass-minimal {{
      width: 100%;
      max-width: none;
      margin: 0;
      flex-shrink: 0;
      align-self: stretch;
      box-sizing: border-box;
      text-align: center;
      /* Match .tm-pass-chrome-bar--app (top blue bar): same gradient + shadow family */
      background: linear-gradient(180deg, #0b74e9 0%, #026cdf 55%, #0256b8 100%);
      border-top: 1px solid rgba(0, 0, 0, 0.12);
      border-bottom: 1px solid rgba(0, 0, 0, 0.18);
      box-shadow: 0 -2px 8px rgba(2, 60, 174, 0.18);
      padding: 10px 14px 11px;
      padding-bottom: max(11px, calc(11px + env(safe-area-inset-bottom, 0px)));
      -webkit-font-smoothing: antialiased;
      position: relative;
      z-index: 5;
    }}
    .tm-footer-pass-inner {{
      max-width: 468px;
      margin: 0 auto;
    }}
    .tm-footer-pass-line {{
      margin: 0;
      color: #ffffff;
      font-size: 0.75rem;
      font-weight: 500;
      line-height: 1.4;
      letter-spacing: 0.01em;
      text-shadow: 0 1px 1px rgba(0, 0, 0, 0.18);
    }}
    .tm-footer-pass-line + .tm-footer-pass-line {{
      margin-top: 0.3rem;
    }}
    .tm-footer-pass-line--strong {{
      font-weight: 700;
      font-size: 0.8125rem;
      letter-spacing: 0.02em;
      color: #ffffff;
    }}
    .tm-footer-pass-line--copy {{
      font-size: 0.6875rem;
      font-weight: 600;
      color: #ffffff;
      margin-top: 0.4rem !important;
    }}
    .tm-topbar-inner {{
      max-width: 430px;
      margin: 0 auto;
      padding: 0.85rem 1rem 0.95rem;
      text-align: center;
    }}
    .tm-brand-lockup {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      text-decoration: none;
      margin-bottom: 0.35rem;
    }}
    .tm-wordmark-img {{
      display: block;
      height: 30px;
      width: auto;
      max-width: min(260px, 92vw);
      object-fit: contain;
      image-rendering: -webkit-optimize-contrast;
    }}
    .tm-wordmark-img--light {{
      filter: brightness(0) invert(1);
    }}
    .tm-brand-lockup:hover .tm-wordmark-img {{
      opacity: 0.88;
    }}
    .tm-footer-wordmark {{
      height: 24px;
      margin: 0 auto 0.35rem;
    }}
    .tm-main-nav-inner .tm-brand-lockup {{ margin-bottom: 0; }}
    .topbar--tm h1 {{ display: none; }}
    .topbar p {{ margin: 0.35rem 0 0; color: var(--muted); font-size: 0.9rem; }}
    .tm-site-footer:not(.tm-site-footer--pass-minimal) {{
      margin-top: auto;
      padding: 1.75rem 1.25rem 2rem;
      text-align: center;
      font-size: 0.8125rem;
      color: var(--muted);
      background: var(--tm-page-gray);
      border-top: 1px solid #e8eaed;
    }}
    .tm-site-footer-inner {{
      max-width: 720px;
      margin: 0 auto;
    }}
    .tm-footer-tagline {{
      margin: 0 0 0.65rem;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .tm-wordmark-img--footer {{
      filter: none;
      height: 22px;
      width: auto;
    }}
    .tm-site-footer a {{
      color: var(--tm-blue);
      font-weight: 700;
      text-decoration: none;
    }}
    .tm-site-footer a:hover {{ text-decoration: underline; color: var(--tm-blue-dark); }}
    .tm-footer-legal {{ margin: 0; line-height: 1.55; }}
    body.tm-page--home .demo-banner {{
      max-width: 960px;
      margin-left: auto;
      margin-right: auto;
      margin-bottom: 0.5rem;
    }}
    .demo-banner {{
      margin: 0 1.5rem 0;
      padding: 0.65rem 1rem;
      background: rgba(255, 180, 80, 0.12);
      border: 1px solid rgba(255, 180, 80, 0.35);
      border-radius: 8px;
      color: #e8c48a;
      font-size: 0.88rem;
    }}
    main {{
      max-width: 430px;
      margin: 0 auto;
      padding: 1.25rem 1rem 2rem;
      position: relative;
      z-index: 1;
    }}
    body.tm-page--home main {{
      max-width: none;
      padding: 0;
      width: 100%;
    }}
    body.tm-page--my-tickets main {{
      max-width: 720px;
      padding: 0 1rem 2.5rem;
      width: 100%;
    }}
    .tm-my-tickets-page {{
      padding-top: 0.35rem;
    }}
    .tm-my-tickets-nav {{
      font-size: 0.8125rem;
      margin: 0 0 1rem;
      color: var(--muted);
    }}
    .tm-my-tickets-crumb {{
      color: var(--tm-blue);
      font-weight: 600;
      text-decoration: none;
    }}
    .tm-my-tickets-crumb:hover {{ text-decoration: underline; }}
    .tm-my-tickets-crumb-sep {{ margin: 0 0.35rem; color: #94a3b8; }}
    .tm-my-tickets-crumb-here {{ color: var(--text); font-weight: 600; }}
    .tm-my-tickets-title {{
      margin: 0 0 1.25rem;
      font-size: 1.5rem;
      font-weight: 800;
      letter-spacing: -0.03em;
      color: var(--text);
    }}
    .barcode-panel {{ background: transparent !important; border: none !important; box-shadow: none !important; }}
    .tickets-only-panel {{ padding: 0 !important; }}
    .acct.acct--tickets-only {{
      background: transparent;
      border: none;
      border-radius: 0;
      box-shadow: none;
      margin-bottom: 0;
      overflow: visible;
    }}
    .acct {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      margin-bottom: 1.5rem;
      overflow: hidden;
      box-shadow: 0 12px 40px rgba(0,0,0,0.35);
    }}
    .acct-hd {{
      padding: 1rem 1.25rem;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: flex-start;
      gap: 0.75rem;
      background: linear-gradient(105deg, rgba(79,140,255,0.08), transparent 40%);
    }}
    .acct-hd-inner {{ flex: 1; min-width: 0; }}
    .acct-hd h2 {{
      margin: 0 0 0.35rem;
      font-size: 1.15rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      word-break: break-word;
      color: var(--text);
    }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 0.35rem; margin-bottom: 0.4rem; }}
    .chip {{
      font-size: 0.78rem;
      padding: 0.2rem 0.55rem;
      border-radius: 999px;
      background: rgba(79, 140, 255, 0.2);
      color: #b8d0ff;
    }}
    .chip.dim {{ background: rgba(46, 230, 166, 0.12); color: var(--accent2); }}
    .credline {{ margin: 0 0 0.35rem; font-size: 0.82rem; }}
    .header-full {{
      margin: 0;
      font-size: 0.68rem;
      color: var(--muted);
      word-break: break-all;
      line-height: 1.35;
    }}
    .mono {{ font-family: 'IBM Plex Mono', monospace; }}
    .badge {{
      flex-shrink: 0;
      background: var(--accent);
      color: #061018;
      font-weight: 700;
      font-size: 0.75rem;
      padding: 0.2rem 0.5rem;
      border-radius: 6px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0;
      border-bottom: 1px solid var(--border);
    }}
    @media (max-width: 720px) {{ .grid {{ grid-template-columns: 1fr; }} }}
    .panel {{
      padding: 1rem 1.25rem;
      border-right: 1px solid var(--border);
    }}
    .panel:last-of-type {{ border-right: none; }}
    .panel.full {{ border-right: none; border-top: 1px solid var(--border); }}
    .panel h3 {{
      margin: 0 0 0.65rem;
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--accent2);
      font-weight: 600;
    }}
    .evlist {{
      margin: 0;
      padding-left: 1.1rem;
      color: var(--text);
      font-size: 0.88rem;
    }}
    .evlist li {{ margin-bottom: 0.45rem; }}
    .evlist.past {{ opacity: 0.85; }}
    .muted {{ color: var(--muted); font-size: 0.88rem; margin: 0; }}
    .cards {{
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.82rem;
      background: #0a0c10;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      border: 1px solid var(--border);
    }}
    .tm-ticket-carousel {{
      position: relative;
      max-width: 468px;
      margin: 0 auto 1.5rem;
      width: 100%;
      overflow-x: hidden;
      overflow-y: visible;
    }}
    .tm-carousel-stage {{
      position: relative;
      width: 100%;
      max-width: 100%;
      overflow-x: hidden;
    }}
    .tm-carousel-viewport {{
      overflow: hidden;
      overflow-x: clip;
      width: 100%;
      overscroll-behavior-x: contain;
      /* manipulation: no double-tap-zoom delay; links inside get reliable taps on iOS/Android */
      touch-action: manipulation;
      scrollbar-width: none;
      -ms-overflow-style: none;
    }}
    .tm-carousel-viewport::-webkit-scrollbar {{
      display: none;
      width: 0;
      height: 0;
    }}
    .tm-carousel-track {{
      display: flex;
      align-items: stretch;
      gap: 12px;
      transition: transform 0.38s cubic-bezier(0.25, 0.1, 0.25, 1);
      overflow: visible;
    }}
    .tm-carousel-slide {{
      flex: 0 0 100%;
      width: 100%;
      min-width: 0;
      box-sizing: border-box;
    }}
    .tm-ticket-carousel--peek .tm-carousel-slide {{
      flex: 0 0 auto;
    }}
    .tm-carousel-slide .tm-pass-card {{
      margin: 0;
    }}
    @keyframes tm-frost-ring {{
      0%, 100% {{ box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1), 0 0 0 0 rgba(2, 108, 223, 0); }}
      50% {{ box-shadow: 0 4px 14px rgba(0, 0, 0, 0.12), 0 0 0 5px rgba(2, 108, 223, 0.09); }}
    }}
    @keyframes tm-chevron-nudge-l {{
      0%, 100% {{ transform: translateX(0); }}
      50% {{ transform: translateX(-2.5px); }}
    }}
    @keyframes tm-chevron-nudge-r {{
      0%, 100% {{ transform: translateX(0); }}
      50% {{ transform: translateX(2.5px); }}
    }}
    .tm-carousel-arrow {{
      position: absolute;
      top: 50%;
      transform: translateY(-50%);
      z-index: 12;
      width: 42px;
      height: 42px;
      padding: 0;
      border-radius: 50%;
      font-family: inherit;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      -webkit-tap-highlight-color: transparent;
    }}
    .tm-carousel-arrow--frost {{
      background: #fff;
      border: 1px solid rgba(0, 0, 0, 0.16);
      color: #0f172a;
      box-shadow: 0 2px 14px rgba(0, 0, 0, 0.14), 0 0 0 1px rgba(255, 255, 255, 0.8) inset;
      backdrop-filter: blur(6px);
    }}
    .tm-carousel-arrow--frost:not(:disabled) {{
      animation: tm-frost-ring 2.6s ease-in-out infinite;
    }}
    .tm-carousel-arrow--frost:hover:not(:disabled) {{
      background: #fff;
      border-color: rgba(2, 108, 223, 0.35);
      color: #026cdf;
      animation: none;
      box-shadow: 0 4px 18px rgba(2, 108, 223, 0.2);
    }}
    .tm-carousel-prev:not(:disabled) .tm-carousel-arrow-svg {{
      animation: tm-chevron-nudge-l 1.55s ease-in-out infinite;
    }}
    .tm-carousel-next:not(:disabled) .tm-carousel-arrow-svg {{
      animation: tm-chevron-nudge-r 1.55s ease-in-out infinite;
    }}
    .tm-carousel-arrow-svg {{
      display: block;
      flex-shrink: 0;
    }}
    .tm-carousel-arrow:disabled {{
      opacity: 0.32;
      cursor: default;
      pointer-events: none;
    }}
    .tm-carousel-prev {{ left: 2px; }}
    .tm-carousel-next {{ right: 2px; }}
    .tm-ticket-carousel--single .tm-carousel-arrow,
    .tm-ticket-carousel--single .tm-carousel-counter {{
      display: none;
    }}
    .tm-carousel-counter {{
      text-align: center;
      margin-top: 10px;
    }}
    .tm-carousel-counter__n {{
      display: inline-block;
      padding: 5px 14px;
      border-radius: 999px;
      background: rgba(2, 108, 223, 0.12);
      color: #0256b8;
      font-size: 0.75rem;
      font-weight: 600;
      letter-spacing: 0.02em;
    }}
    .tm-carousel-dots {{
      display: flex;
      justify-content: center;
      gap: 8px;
      margin-top: 12px;
    }}
    .tm-carousel-dot {{
      width: 7px;
      height: 7px;
      padding: 0;
      border: none;
      border-radius: 50%;
      background: #cbd5e1;
      cursor: pointer;
    }}
    .tm-carousel-dot.is-active {{
      background: var(--tm-blue);
      transform: scale(1.2);
    }}
    .tm-pass-card {{
      max-width: 448px;
      margin: 0 auto;
      background: #fff;
      color: #1a1a1a;
      border-radius: 14px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      box-shadow:
        0 4px 24px rgba(2, 108, 223, 0.08),
        0 8px 32px rgba(0, 0, 0, 0.06),
        0 0 0 1px rgba(2, 108, 223, 0.1);
      border: 1px solid rgba(2, 108, 223, 0.12);
      font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }}
    .tm-pass-rail {{
      height: 3px;
      background: #026cdf;
      flex-shrink: 0;
      transform-origin: center;
      animation: tm-pass-rail-in 0.42s cubic-bezier(0.22, 0.61, 0.36, 1) both;
    }}
    .tm-pass-warn {{
      font-size: 0.78rem;
      color: #9a3412;
      background: #fff7ed;
      padding: 8px 12px;
      margin: 0 12px 0;
      border-radius: 8px;
      text-align: center;
      border: 1px solid #fed7aa;
    }}
    @keyframes tm-pass-head-enter-lr {{
      from {{
        opacity: 0;
        transform: translateX(-22px);
      }}
      to {{
        opacity: 1;
        transform: translateX(0);
      }}
    }}
    @keyframes tm-pass-head-fade-up {{
      from {{
        opacity: 0;
        transform: translateY(12px);
      }}
      to {{
        opacity: 1;
        transform: translateY(0);
      }}
    }}
    @keyframes tm-pass-rail-in {{
      from {{
        transform: scaleX(0.35);
        opacity: 0.5;
      }}
      to {{
        transform: scaleX(1);
        opacity: 1;
      }}
    }}
    .tm-pass-head {{
      display: grid;
      grid-template-columns: 44px 1fr 44px;
      align-items: start;
      gap: 0 6px;
      padding: 10px 10px 10px;
      background: #fff;
      border-bottom: 1px solid #e8eaed;
      flex-shrink: 0;
      position: relative;
      z-index: 4;
    }}
    .tm-pass-menu {{
      grid-column: 1;
      justify-self: start;
      border: none;
      background: transparent;
      cursor: pointer;
      color: #1a1a1a;
      width: 40px;
      height: 40px;
      padding: 0;
      margin: 0;
      line-height: 1;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      text-decoration: none;
      -webkit-tap-highlight-color: transparent;
      animation: tm-pass-head-enter-lr 0.48s cubic-bezier(0.25, 0.46, 0.45, 0.94) 0.05s both;
    }}
    a.tm-pass-menu {{ color: #1a1a1a; }}
    .tm-pass-menu:hover {{ background: rgba(0, 0, 0, 0.05); color: #026cdf; }}
    .tm-pass-menu-ico {{ display: block; }}
    .tm-pass-head-center {{
      grid-column: 2;
      text-align: center;
      min-width: 0;
      padding-top: 2px;
    }}
    .tm-pass-head-spacer {{
      grid-column: 3;
      width: 44px;
      height: 1px;
    }}
    .tm-pass-title {{
      margin: 0;
      font-size: 0.9375rem;
      font-weight: 800;
      letter-spacing: 0.02em;
      line-height: 1.2;
      word-break: break-word;
      text-transform: uppercase;
      color: #111;
      animation: tm-pass-head-fade-up 0.52s cubic-bezier(0.22, 0.61, 0.36, 1) 0.1s both;
    }}
    .tm-pass-sub {{
      margin: 6px 0 0;
      font-size: 0.8125rem;
      font-weight: 400;
      color: #666;
      line-height: 1.4;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 3px;
      max-height: 4.5em;
      overflow: hidden;
    }}
    .tm-pass-sub-line {{
      display: block;
      max-width: 100%;
      text-align: center;
      animation: tm-pass-head-fade-up 0.48s cubic-bezier(0.22, 0.61, 0.36, 1) both;
    }}
    .tm-pass-sub-line:nth-child(1) {{ animation-delay: 0.22s; }}
    .tm-pass-sub-line:nth-child(2) {{ animation-delay: 0.36s; }}
    .tm-pass-sub-line:nth-child(3) {{ animation-delay: 0.5s; }}
    .tm-pass-visual {{ position: relative; flex-shrink: 0; }}
    /* TM overlay: event header → tall hero art → barcode sheet pinned to bottom. */
    /* Blue wordmark strip lives on pass card top (rail → brand → head), not above hero. */
    .tm-pass-visual--overlay {{
      display: flex;
      flex-direction: column;
      background: #fff;
    }}
    .tm-pass-brand-strip {{
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 7px 12px 6px;
      background: #026cdf;
      flex-shrink: 0;
    }}
    .tm-pass-brand-strip img {{
      height: 13px;
      width: auto;
      max-width: 132px;
      object-fit: contain;
      filter: brightness(0) invert(1);
      opacity: 0;
      transition: opacity 0.4s ease;
    }}
    .tm-pass-brand-strip img.tm-pass-media--loaded {{
      opacity: 0.96;
    }}
    .tm-pass-visual--overlay .tm-pass-hero--cover {{
      position: relative;
      height: clamp(340px, 78vw, 440px);
      min-height: clamp(340px, 78vw, 440px);
      max-height: none;
      overflow: hidden;
      flex-shrink: 0;
    }}
    .tm-pass-visual--overlay .tm-pass-hero--cover .tm-pass-hero-bg {{
      position: absolute;
      inset: 0;
      z-index: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
      object-position: center 16%;
    }}
    .tm-pass-visual--overlay .tm-pass-hero--cover.tm-pass-hero--grad,
    .tm-pass-visual--overlay .tm-pass-hero--cover.tm-pass-hero--tmblue {{
      height: clamp(340px, 78vw, 440px);
      min-height: clamp(340px, 78vw, 440px);
      max-height: none;
    }}
    .tm-pass-visual--overlay .tm-pass-hero-shade--soft {{
      position: absolute;
      inset: 0;
      z-index: 1;
      pointer-events: none;
      background: linear-gradient(
        180deg,
        rgba(0, 0, 0, 0) 0%,
        rgba(0, 0, 0, 0.06) 38%,
        rgba(0, 0, 0, 0.22) 72%,
        rgba(0, 0, 0, 0.34) 100%
      );
    }}
    .tm-pass-visual--overlay .tm-pass-bar-sheet {{
      position: absolute;
      left: 8px;
      right: 8px;
      bottom: 8px;
      z-index: 3;
      padding: 10px 10px 8px;
      background: #eceeef;
      border-radius: 10px;
      box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.06), 0 4px 14px rgba(0, 0, 0, 0.14);
      border: 1px solid rgba(0, 0, 0, 0.06);
    }}
    .tm-pass-visual--overlay .tm-pass-bc.barcode-frame {{
      padding: 6px 8px 4px;
    }}
    .tm-pass-visual--overlay .barcode-frame canvas.safetix-canvas {{
      max-height: 110px;
    }}
    .tm-pass-visual--overlay .tm-pass-hero-watermark img {{
      opacity: 0.18;
      max-height: 50%;
    }}
    /* Legacy stack layout (pre-V6 passes) */
    .tm-pass-visual--tmstack {{
      display: flex;
      flex-direction: column;
      background: #fff;
    }}
    .tm-pass-brand-strip {{
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 7px 12px 6px;
      background: #026cdf;
      flex-shrink: 0;
    }}
    .tm-pass-brand-strip img {{
      height: 13px;
      width: auto;
      max-width: 132px;
      object-fit: contain;
      filter: brightness(0) invert(1);
      opacity: 0;
      transition: opacity 0.4s ease;
    }}
    .tm-pass-brand-strip img.tm-pass-media--loaded {{
      opacity: 0.96;
    }}
    .tm-pass-visual--tmstack .tm-pass-bar-sheet {{
      position: relative;
      left: auto;
      right: auto;
      bottom: auto;
      z-index: 2;
      padding: 10px 12px 8px;
      background: #eceeef;
      border-radius: 0;
      box-shadow: none;
      border: none;
      border-bottom: 1px solid rgba(0, 0, 0, 0.06);
    }}
    .tm-pass-visual--tmstack .tm-pass-bc.barcode-frame {{
      padding: 6px 8px 4px;
    }}
    .tm-pass-visual--tmstack .barcode-frame canvas.safetix-canvas {{
      max-height: 102px;
    }}
    .tm-pass-visual--tmstack .tm-pass-status {{
      margin-top: 6px;
      margin-bottom: 0;
    }}
    .tm-pass-hero--poster {{
      position: relative;
      height: auto;
      min-height: clamp(200px, 52vw, 320px);
      max-height: none;
      overflow: hidden;
      flex-shrink: 0;
    }}
    .tm-pass-hero--poster .tm-pass-hero-bg {{
      position: relative;
      inset: auto;
      display: block;
      width: 100%;
      height: clamp(200px, 52vw, 320px);
      min-height: clamp(200px, 52vw, 320px);
      object-fit: cover;
      object-position: center 22%;
    }}
    .tm-pass-hero--poster.tm-pass-hero--grad,
    .tm-pass-hero--poster.tm-pass-hero--tmblue {{
      height: clamp(200px, 52vw, 320px);
      min-height: clamp(200px, 52vw, 320px);
      max-height: none;
    }}
    .tm-pass-hero--poster .tm-pass-hero-watermark img {{
      opacity: 0.22;
      max-height: 55%;
    }}
    .tm-pass-hero {{
      position: relative;
      height: 280px;
      min-height: 280px;
      max-height: 280px;
      overflow: hidden;
    }}
    .tm-pass-hero-bg {{
      position: absolute;
      inset: 0;
      z-index: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
      object-position: center 30%;
      opacity: 0;
      transition: opacity 0.48s ease;
    }}
    .tm-pass-hero-bg.tm-pass-media--loaded {{
      opacity: 1;
    }}
    .tm-pass-hero--grad {{
      background: linear-gradient(165deg, hsl(var(--tm-hue) 52% 34%) 0%, hsl(var(--tm-hue) 44% 14%) 100%);
      height: 280px;
      min-height: 280px;
      max-height: 280px;
    }}
    .tm-pass-hero--tmblue {{
      background: linear-gradient(
        160deg,
        #0b74e9 0%,
        #026cdf 34%,
        #03478f 68%,
        #02121f 100%
      ) !important;
    }}
    .tm-pass-hero-watermark {{
      position: absolute;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 0;
      pointer-events: none;
      overflow: hidden;
    }}
    .tm-pass-hero-watermark img {{
      width: min(78%, 260px);
      height: auto;
      max-height: 42%;
      object-fit: contain;
      opacity: 0.14;
      filter: brightness(0) invert(1);
    }}
    @keyframes tm-pass-hero-fx-glint {{
      0%, 100% {{ transform: translate(-14%, -10%) scale(1.02); opacity: 0.72; }}
      28% {{ transform: translate(16%, 4%) scale(1.14); opacity: 0.98; }}
      52% {{ transform: translate(6%, 18%) scale(0.96); opacity: 0.62; }}
      76% {{ transform: translate(-8%, 8%) scale(1.08); opacity: 0.88; }}
    }}
    @keyframes tm-pass-hero-fx-dots {{
      0%, 100% {{ opacity: 0.38; }}
      50% {{ opacity: 0.52; }}
    }}
    .tm-pass-hero-fx {{
      position: absolute;
      inset: 0;
      z-index: 1;
      pointer-events: none;
      overflow: hidden;
    }}
    .tm-pass-hero-fx::before {{
      content: "";
      position: absolute;
      inset: -35%;
      background: radial-gradient(
        ellipse 55% 48% at 50% 50%,
        rgba(255, 255, 255, 0.34) 0%,
        rgba(255, 255, 255, 0.08) 42%,
        transparent 68%
      );
      mix-blend-mode: soft-light;
      animation: tm-pass-hero-fx-glint 16s ease-in-out infinite;
      will-change: transform, opacity;
    }}
    .tm-pass-hero-fx::after {{
      content: "";
      position: absolute;
      inset: 0;
      background-image: radial-gradient(
        circle,
        rgba(255, 255, 255, 0.42) 1.1px,
        transparent 1.65px
      );
      background-size: 10px 10px;
      mix-blend-mode: overlay;
      opacity: 0.44;
      animation: tm-pass-hero-fx-dots 5.5s ease-in-out infinite;
    }}
    .tm-pass-hero-shade {{
      position: absolute;
      inset: 0;
      background: linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,0.22) 55%, rgba(0,0,0,0.45) 100%);
      pointer-events: none;
      z-index: 2;
    }}
    .tm-pass-bar-sheet {{
      position: absolute;
      left: 6px;
      right: 6px;
      bottom: 6px;
      z-index: 3;
      padding: 8px 6px 8px;
      background: #eceeef;
      border-radius: 10px;
      box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.06), 0 4px 14px rgba(0, 0, 0, 0.12);
      border: 1px solid rgba(0, 0, 0, 0.05);
      display: flex;
      flex-direction: column;
      align-items: center;
    }}
    /* ~42px frost controls at stage edges; pull barcode sheet inward so arrows clear the frame */
    .tm-ticket-carousel--side-nav .tm-pass-bar-sheet {{
      left: 52px;
      right: 52px;
    }}
    .tm-pass-screen-row {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      flex-wrap: wrap;
      font-size: 0.625rem;
      font-weight: 700;
      color: #334155;
      margin-bottom: 6px;
      letter-spacing: 0.02em;
      width: 100%;
      text-align: center;
    }}
    .tm-pass-phone-ico {{
      flex-shrink: 0;
      color: #026cdf;
      opacity: 0.9;
    }}
    .tm-pass-refresh-btn {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 4px 9px 4px 7px;
      margin: 0;
      border: 1px solid rgba(2, 108, 223, 0.38);
      border-radius: 999px;
      background: #fff;
      color: #026cdf;
      font: inherit;
      font-size: 0.625rem;
      font-weight: 700;
      letter-spacing: 0.02em;
      cursor: pointer;
      line-height: 1.1;
      box-shadow: 0 1px 2px rgba(2, 108, 223, 0.12);
      transition: background 0.15s ease, border-color 0.15s ease, transform 0.12s ease;
    }}
    .tm-pass-refresh-btn:hover {{
      background: rgba(2, 108, 223, 0.06);
      border-color: rgba(2, 108, 223, 0.55);
    }}
    .tm-pass-refresh-btn:active {{
      transform: scale(0.97);
    }}
    .tm-pass-refresh-btn__ico {{
      font-size: 0.85rem;
      line-height: 1;
      display: inline-block;
    }}
    .tm-pass-refresh-btn--spin .tm-pass-refresh-btn__ico {{
      animation: tm-pass-spin 0.65s linear;
    }}
    .tm-pass-refresh-btn__sec {{
      min-width: 1.35em;
      height: 1.35em;
      padding: 0 2px;
      border-radius: 50%;
      border: 1px solid rgba(2, 108, 223, 0.45);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 0.55rem;
      font-weight: 800;
      color: #0153a3;
      background: rgba(2, 108, 223, 0.08);
      font-variant-numeric: tabular-nums;
    }}
    @keyframes tm-pass-spin {{ to {{ transform: rotate(360deg); }} }}
    .tm-pass-bc {{
      position: relative;
      display: block;
      margin: 0 auto;
      max-width: 100%;
      isolation: isolate;
    }}
    .tm-pass-card .tm-pass-bc.barcode-frame {{
      background: #fff;
      border: 1px solid rgba(0, 0, 0, 0.06);
      padding: 8px 10px 6px;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
      border-radius: 10px;
      margin-top: 2px;
      align-self: stretch;
      width: 100%;
      max-width: 100%;
      box-sizing: border-box;
      margin-left: auto;
      margin-right: auto;
      min-height: 88px;
    }}
    .tm-pass-card .barcode-frame canvas.safetix-canvas {{
      position: relative;
      z-index: 1;
      display: block;
      width: 100% !important;
      max-width: 100% !important;
      height: auto !important;
      margin: 0 auto;
      image-rendering: pixelated;
      image-rendering: crisp-edges;
      opacity: 0;
      transition: opacity 0.38s ease;
    }}
    .tm-pass-bc.tm-pass-bc--ready .safetix-canvas {{
      opacity: 1;
    }}
    @keyframes tm-pass-bc-shimmer {{
      0% {{ background-position: 200% 0; }}
      100% {{ background-position: -200% 0; }}
    }}
    .tm-pass-bc:not(.tm-pass-bc--ready)::before {{
      content: "";
      position: absolute;
      left: 10px;
      right: 10px;
      top: 8px;
      bottom: 6px;
      z-index: 0;
      border-radius: 6px;
      background: linear-gradient(90deg, #eef0f2 0%, #f8f9fa 45%, #eef0f2 90%);
      background-size: 200% 100%;
      animation: tm-pass-bc-shimmer 1.4s ease-in-out infinite;
      pointer-events: none;
    }}
    .tm-pass-bc.tm-pass-bc--ready::before {{
      display: none;
    }}
    .tm-pass-bc:not(.tm-pass-bc--ready) .tm-scan-line,
    .tm-pass-bc:not(.tm-pass-bc--ready) .tm-scan-glow {{
      opacity: 0 !important;
      visibility: hidden;
      animation: none !important;
    }}
    .tm-pass-bc.tm-pass-bc--ready .tm-scan-line,
    .tm-pass-bc.tm-pass-bc--ready .tm-scan-glow {{
      opacity: 1;
      transition: opacity 0.45s ease 0.15s;
    }}
    .tm-pass-bc--sg.barcode-frame {{
      width: 100%;
      max-width: 100%;
      padding: 10px 10px 8px;
      box-sizing: border-box;
      min-height: 120px;
    }}
    .tm-pass-bc--sg canvas.safetix-canvas {{
      width: auto !important;
      max-width: 184px !important;
      min-height: 0;
      height: auto !important;
    }}
    .tm-pass-body {{ background: #fff; padding: 12px 14px 14px; flex-shrink: 0; }}
    @keyframes tm-pass-scan-lead {{
      0% {{ left: 13%; opacity: 1; }}
      38% {{ left: 87%; opacity: 1; }}
      44% {{ left: 87%; opacity: 1; }}
      82% {{ left: 13%; opacity: 1; }}
      100% {{ left: 13%; opacity: 1; }}
    }}
    @keyframes tm-pass-scan-trail {{
      0% {{ left: 6%; opacity: 0.42; }}
      38% {{ left: 87%; opacity: 0.72; }}
      44% {{ left: 87%; opacity: 0.78; }}
      82% {{ left: 6%; opacity: 0.42; }}
      100% {{ left: 6%; opacity: 0.42; }}
    }}
    .tm-scan-line,
    .tm-scan-glow {{
      position: absolute;
      top: -6px;
      bottom: -6px;
      pointer-events: none;
      will-change: left, opacity;
    }}
    .tm-scan-glow {{
      width: 20px;
      margin-left: -10px;
      z-index: 4;
      border-radius: 5px;
      background: linear-gradient(
        90deg,
        transparent 0%,
        rgba(2, 108, 223, 0.12) 22%,
        rgba(2, 108, 223, 0.38) 50%,
        rgba(2, 108, 223, 0.14) 78%,
        transparent 100%
      );
      filter: blur(3px);
      animation: tm-pass-scan-trail 5.6s ease-in-out infinite;
    }}
    .tm-scan-line {{
      width: 3px;
      margin-left: -1.5px;
      z-index: 5;
      border-radius: 1.5px;
      background: linear-gradient(
        180deg,
        rgba(2, 76, 190, 0.15) 0%,
        #0256c4 14%,
        #026cdf 50%,
        #0256c4 86%,
        rgba(2, 76, 190, 0.15) 100%
      );
      box-shadow:
        0 0 4px 1px rgba(2, 108, 223, 0.55),
        0 0 12px 2px rgba(2, 108, 223, 0.28);
      animation: tm-pass-scan-lead 5.6s ease-in-out infinite;
    }}
    .tm-pass-status {{
      align-self: stretch;
      width: 100%;
      text-align: center;
      font-size: 0.625rem !important;
      color: #666 !important;
      margin: 6px 0 0 !important;
      line-height: 1.35 !important;
      min-height: 1.35em;
      opacity: 0;
      transition: opacity 0.4s ease 0.08s;
    }}
    .tm-pass-card.tm-pass-card--ready .tm-pass-status {{
      opacity: 1;
    }}
    /* Bold bar leads; translucent trails; meet at end, then sweep back to start at the same pace (no fast snap). */
    .tm-pass-type-block {{ text-align: center; margin-bottom: 12px; }}
    .tm-pass-kind {{
      display: block;
      font-size: 1rem;
      font-weight: 800;
      color: #111;
      letter-spacing: -0.01em;
    }}
    .tm-pass-verified-row {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      margin-top: 8px;
    }}
    .tm-pass-verified-txt {{
      font-size: 0.8125rem;
      font-weight: 600;
      color: #026cdf;
    }}
    .tm-pass-type-detail {{
      display: block;
      font-size: 0.75rem;
      color: #666;
      margin-top: 6px;
      font-weight: 400;
    }}
    .tm-pass-type-block .tm-pass-type-sub {{
      display: block;
      font-size: 0.8125rem;
      color: var(--muted);
      margin-top: 6px;
      font-weight: 500;
    }}
    .tm-pass-type-secondary {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      margin-top: 8px;
    }}
    .tm-pass-type-sub--verified {{
      color: var(--tm-blue);
      font-weight: 600;
      margin-top: 0;
    }}
    .tm-verified-check {{
      flex-shrink: 0;
      display: block;
    }}
    .tm-pass-seats {{
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 8px 6px;
      text-align: center;
      margin-bottom: 12px;
      padding: 0 2px;
    }}
    .tm-pass-lbl {{
      display: block;
      font-size: 0.5625rem;
      font-weight: 700;
      letter-spacing: 0.12em;
      color: #888;
      margin-bottom: 5px;
    }}
    .tm-pass-seats b {{
      font-size: 1.2rem;
      font-weight: 800;
      color: #111;
      letter-spacing: -0.02em;
    }}
    .tm-pass-gate {{
      display: block;
      width: 100%;
      box-sizing: border-box;
      background: #111;
      color: #fff;
      text-align: center;
      font-size: 0.6875rem;
      font-weight: 800;
      letter-spacing: 0.12em;
      padding: 12px 16px;
      border-radius: 10px;
      margin-bottom: 10px;
      border: none;
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.22);
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .tm-pass-actions {{ display: flex; gap: 10px; align-items: stretch; }}
    .tm-pass-btn {{
      flex: 1;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 12px 10px;
      font-size: 0.6875rem;
      font-weight: 700;
      border-radius: 10px;
      text-decoration: none;
      cursor: pointer;
      border: none;
      text-align: center;
      line-height: 1.25;
      font-family: inherit;
      letter-spacing: 0.02em;
    }}
    .tm-pass-wallet {{
      background: #111 !important;
      background-color: #111 !important;
      color: #fff !important;
      border: none;
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.22);
    }}
    a.tm-pass-wallet:hover {{
      background: #1f1f1f !important;
      background-color: #1f1f1f !important;
      color: #fff !important;
      box-shadow: 0 3px 14px rgba(0, 0, 0, 0.28);
    }}
    .tm-pass-wallet--badge {{
      flex: 1.35;
      justify-content: flex-start;
      padding: 10px 14px 10px 12px;
      gap: 12px;
      border-radius: 10px;
      min-height: 48px;
      background: #111 !important;
      background-color: #111 !important;
      color: #fff !important;
    }}
    .tm-pass-wallet-badge-ico {{
      flex-shrink: 0;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .tm-pass-wallet-badge-img {{
      display: block;
      width: 40px;
      height: auto;
      max-height: 30px;
      object-fit: contain;
    }}
    .tm-pass-wallet-badge-text {{
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      justify-content: center;
      text-align: left;
      line-height: 1.12;
    }}
    .tm-pass-wallet-l1 {{
      font-size: 0.625rem;
      font-weight: 500;
      letter-spacing: 0.03em;
      color: #fff;
      opacity: 0.95;
    }}
    .tm-pass-wallet-l2 {{
      font-size: 0.8125rem;
      font-weight: 600;
      letter-spacing: 0.02em;
      color: #fff;
    }}
    .tm-pass-btn--disabled:not(.tm-pass-wallet--badge) {{
      background: #cbd5e1;
      color: #f8fafc !important;
      cursor: not-allowed;
    }}
    .tm-pass-btn--disabled.tm-pass-wallet--badge {{
      background: #9ca3af;
      color: #f8fafc !important;
      cursor: not-allowed;
      box-shadow: none;
    }}
    .tm-pass-btn--disabled .tm-pass-wallet-badge-img {{
      opacity: 0.7;
    }}
    .tm-pass-info {{
      background: #f2f2f2;
      color: #0a0a0a !important;
      border: 1px solid #6b7280;
      border-radius: 999px;
      box-shadow: none;
      padding: 10px 18px;
      gap: 10px;
      font-weight: 700;
    }}
    .tm-pass-info-label {{
      font-size: 0.8125rem;
      font-weight: 700;
      letter-spacing: 0.01em;
      color: inherit;
    }}
    a.tm-pass-info:hover {{
      background: #e8e8ea;
      border-color: #4b5563;
      color: #0a0a0a !important;
    }}
    .tm-pass-info-ico {{
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: #111;
      color: #fff;
      border: none;
      font-size: 0.68rem;
      font-weight: 700;
      font-style: normal;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      line-height: 1;
    }}
    .tm-pass-info.tm-pass-info--muted {{
      background: #eceef0 !important;
      color: #64748b !important;
      border-color: #94a3b8 !important;
      cursor: default;
    }}
    .tm-pass-info.tm-pass-info--muted .tm-pass-info-ico {{
      background: #64748b;
      color: #fff;
    }}
    .tm-pass-btn--ghost {{ background: #f8fafc; color: #94a3b8 !important; cursor: default; border: 1.5px solid #e2e8f0; }}
    .tm-pass-btn.tm-pass-transfer {{
      border: 1.5px solid #7c3aed;
      color: #5b21b6;
      background: linear-gradient(180deg, rgba(124, 58, 237, 0.14) 0%, rgba(91, 33, 182, 0.09) 100%);
      flex-direction: column;
      gap: 1px;
      padding: 10px 8px;
    }}
    .tm-pass-btn.tm-pass-transfer:hover {{
      background: linear-gradient(180deg, rgba(124, 58, 237, 0.22) 0%, rgba(91, 33, 182, 0.15) 100%);
    }}
    .tm-pass-transfer-stack {{
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      line-height: 1.12;
      text-align: center;
    }}
    .tm-pass-transfer-label {{
      font-size: 0.78rem;
      font-weight: 800;
      color: #4c1d95;
      letter-spacing: 0.02em;
    }}
    .tm-pass-transfer-line1 {{
      font-size: 0.58rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: #6d28d9;
    }}
    .tm-pass-transfer-line2 {{
      font-size: 0.78rem;
      font-weight: 800;
      color: #4c1d95;
      letter-spacing: 0.01em;
    }}
    .barcode-frame {{
      display: inline-block;
      background: #fff;
      padding: 14px 18px;
      border-radius: 10px;
      border: 1px solid var(--border);
      max-width: 100%;
    }}
    .barcode-frame img {{
      display: block;
      max-width: min(100%, 520px);
      height: auto;
    }}
    .barcode-frame canvas.safetix-canvas {{
      display: block;
      max-width: 100%;
      height: auto;
    }}
    .safetix-slot {{ margin-bottom: 0; }}
    .bc-label {{
      margin: 0 0 0.45rem;
      font-size: 0.84rem;
      font-weight: 600;
      color: #b8f5e0;
      line-height: 1.35;
    }}
    .barcode-warn {{
      font-size: 0.85rem;
      color: #ffb86c;
      margin: 0 0 0.75rem;
    }}
    code.tiny {{ font-size: 0.65rem; word-break: break-all; }}
    p.small {{ font-size: 0.78rem; margin: 0.5rem 0 0; }}
    pre.cookies {{
      margin: 0;
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.68rem;
      line-height: 1.35;
      background: #07080c;
      color: #c5d4ea;
      padding: 1rem;
      border-radius: 8px;
      border: 1px solid var(--border);
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-all;
      max-height: 420px;
      overflow-y: auto;
    }}
    details.raw {{
      border-top: 1px solid var(--border);
      padding: 0.75rem 1.25rem;
      font-size: 0.8rem;
    }}
    details.raw summary {{
      cursor: pointer;
      color: var(--muted);
      user-select: none;
    }}
    details.raw pre {{
      margin-top: 0.75rem;
      font-size: 0.65rem;
      white-space: pre-wrap;
      word-break: break-all;
      color: var(--muted);
    }}
    .tm-home-wrap.tm-home-retail {{
      width: 100%;
      padding-bottom: 2.5rem;
    }}
    .tm-retail-hero {{
      position: relative;
      min-height: 260px;
      background: linear-gradient(125deg, #0153a3 0%, var(--tm-blue) 45%, #2088e8 100%);
    }}
    .tm-retail-hero-img {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
      object-position: center 28%;
    }}
    .tm-retail-hero-overlay {{
      position: relative;
      z-index: 1;
      min-height: 260px;
      display: flex;
      flex-direction: column;
      justify-content: flex-end;
      align-items: flex-start;
      padding: 1.5rem 1.25rem 2rem;
      max-width: 1200px;
      margin: 0 auto;
      background: linear-gradient(180deg, rgba(0, 0, 0, 0.12) 0%, rgba(0, 0, 0, 0.55) 100%);
      box-sizing: border-box;
    }}
    .tm-retail-kicker {{
      margin: 0 0 0.4rem;
      font-size: 0.625rem;
      font-weight: 700;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: rgba(255, 255, 255, 0.92);
    }}
    .tm-retail-hero h1 {{
      margin: 0 0 0.5rem;
      font-size: clamp(1.28rem, 4.2vw, 1.85rem);
      font-weight: 800;
      line-height: 1.12;
      color: #fff;
      max-width: 20ch;
    }}
    .tm-retail-sub {{
      margin: 0 0 1rem;
      font-size: 0.875rem;
      line-height: 1.45;
      color: rgba(255, 255, 255, 0.94);
      max-width: 36ch;
    }}
    .tm-retail-cta {{
      display: inline-block;
      padding: 0.55rem 1.35rem;
      border-radius: 4px;
      background: var(--tm-blue);
      color: #fff !important;
      text-decoration: none;
      font-weight: 700;
      font-size: 0.8125rem;
      border: 1px solid rgba(255, 255, 255, 0.4);
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
    }}
    .tm-retail-cta:hover {{ filter: brightness(1.07); }}
    .tm-search-strip-wrap {{
      max-width: 960px;
      margin: -1.25rem auto 0;
      padding: 0 1rem 1.75rem;
      position: relative;
      z-index: 3;
    }}
    .tm-search-strip {{
      display: flex;
      flex-wrap: wrap;
      align-items: stretch;
      background: #fff;
      border-radius: 6px;
      box-shadow: 0 6px 28px rgba(0, 0, 0, 0.14);
      border: 1px solid #e5e7eb;
      overflow: hidden;
    }}
    .tm-search-seg {{
      flex: 1 1 120px;
      padding: 11px 14px 13px;
      display: flex;
      flex-direction: column;
      gap: 3px;
      border-right: 1px solid #e8eaed;
      min-width: 0;
    }}
    .tm-search-seg--grow {{ flex: 2 1 180px; }}
    .tm-sico {{
      width: 18px;
      height: 18px;
      color: var(--tm-blue);
      flex-shrink: 0;
    }}
    .tm-slab {{
      font-size: 0.5625rem;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #6b7280;
    }}
    .tm-sval {{
      font-size: 0.8125rem;
      font-weight: 500;
      color: #9ca3af;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .tm-search-go {{
      flex: 0 0 auto;
      align-self: stretch;
      width: 52px;
      padding: 0;
      border: none;
      background: var(--tm-blue);
      color: #fff;
      font-family: inherit;
      font-weight: 700;
      font-size: 0.8125rem;
      cursor: default;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .tm-search-go-ico {{
      width: 22px;
      height: 22px;
    }}
    .tm-sr-only {{
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }}
    .tm-ticket-list-section {{
      max-width: 720px;
      margin: 0 auto;
      padding: 0.5rem 1rem 0;
    }}
    .tm-email-gate {{
      margin-bottom: 1.25rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid #e8eaed;
    }}
    .tm-email-hint {{
      font-size: 0.875rem;
      color: var(--muted);
      margin: 0 0 0.65rem;
      line-height: 1.4;
    }}
    .tm-email-row {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.5rem;
    }}
    .tm-email-row input {{
      flex: 1 1 220px;
      min-width: 0;
      padding: 0.55rem 0.75rem;
      border: 1px solid #d1d5db;
      border-radius: 4px;
      font-size: 0.9rem;
      font-family: inherit;
    }}
    .tm-email-row button {{
      padding: 0.55rem 1.1rem;
      background: var(--tm-blue);
      color: #fff;
      border: none;
      border-radius: 4px;
      font-weight: 700;
      font-size: 0.8125rem;
      cursor: pointer;
      font-family: inherit;
    }}
    .tm-email-row button:hover {{ filter: brightness(1.06); }}
    .tm-otp-row {{ margin-top: 0.65rem; }}
    .tm-login-gate-section .tm-login-gate-lead {{
      font-size: 1rem;
      font-weight: 600;
      color: var(--text);
      margin: 0 0 0.65rem;
      line-height: 1.45;
    }}
    .tm-login-gate-hint {{
      margin-bottom: 1.1rem;
    }}
    .tm-login-gate-actions {{
      margin: 0;
    }}
    .tm-login-gate-cta {{
      display: inline-block;
      padding: 0.75rem 1.5rem;
      background: var(--tm-blue);
      color: #fff !important;
      font-weight: 800;
      font-size: 0.875rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      text-decoration: none;
      border-radius: 4px;
      border: none;
      cursor: pointer;
      font-family: inherit;
      box-shadow: 0 2px 10px rgba(2, 108, 223, 0.35);
    }}
    .tm-login-gate-cta:hover {{ filter: brightness(1.06); color: #fff !important; }}
    /* display:flex on these classes wins over the [hidden] attribute otherwise */
    .tm-logged-in-bar[hidden],
    #tm-otp-row[hidden],
    #tm-home-login-teaser[hidden] {{
      display: none !important;
    }}
    .tm-ticket-load-err {{
      color: #b91c1c;
      font-size: 0.85rem;
      margin: 0.6rem 0 0;
    }}
    .tm-muted-inline {{
      margin: 0;
      font-size: 0.875rem;
      color: var(--muted);
    }}
    .tm-ticket-tile--loaded {{
      animation: tm-tile-in 0.35s ease both;
    }}
    @keyframes tm-tile-in {{
      from {{ opacity: 0; transform: translateY(6px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    .tm-section-heading {{
      margin: 0 0 1rem;
      font-size: 1.125rem;
      font-weight: 800;
      color: var(--text);
      letter-spacing: -0.02em;
    }}
    .tm-ticket-grid {{
      display: flex;
      flex-direction: column;
      gap: 0.85rem;
    }}
    .tm-ticket-tile {{
      display: block;
      padding: 1rem 1.15rem;
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      text-decoration: none;
      border: 1px solid #e8eaed;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
      touch-action: manipulation;
      -webkit-tap-highlight-color: rgba(2, 108, 223, 0.12);
    }}
    .tm-ticket-tile:hover {{
      border-color: rgba(2, 108, 223, 0.45);
      box-shadow: 0 6px 20px rgba(2, 108, 223, 0.12);
    }}
    .tm-tile-ev {{
      font-weight: 800;
      font-size: 0.92rem;
      line-height: 1.3;
      margin-bottom: 0.35rem;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }}
    .tm-tile-meta {{
      font-size: 0.78rem;
      color: var(--muted);
      margin-bottom: 0.4rem;
    }}
    .tm-tile-seat {{
      font-size: 0.82rem;
      font-weight: 600;
      color: #334155;
    }}
    .tm-tile-cta {{
      display: inline-block;
      margin-top: 0.65rem;
      font-size: 0.75rem;
      font-weight: 700;
      color: var(--tm-blue);
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .tm-pass-pager {{
      margin: 1rem auto 0;
      max-width: 448px;
      padding: 0 0.35rem;
      font-size: 0.82rem;
    }}
    .tm-pass-pager--card-mid {{
      position: absolute;
      left: 2px;
      right: 2px;
      top: 38%;
      transform: translateY(-50%);
      z-index: 14;
      display: flex;
      justify-content: space-between;
      align-items: center;
      pointer-events: none;
      margin: 0;
      padding: 0;
      max-width: none;
      box-sizing: border-box;
    }}
    .tm-pass-pager--card-mid .tm-pass-dir {{
      pointer-events: auto;
    }}
    .tm-pass-dir--frost {{
      width: 42px;
      height: 42px;
      border-radius: 50%;
      background: #fff;
      border: 1px solid rgba(0, 0, 0, 0.16);
      color: #0f172a;
      box-shadow: 0 2px 14px rgba(0, 0, 0, 0.14), 0 0 0 1px rgba(255, 255, 255, 0.8) inset;
      backdrop-filter: blur(8px);
      -webkit-backdrop-filter: blur(8px);
    }}
    .tm-pass-dir--frost:not(.tm-pass-dir--disabled) {{
      animation: tm-frost-ring 2.6s ease-in-out infinite;
    }}
    .tm-pass-dir--frost:hover:not(.tm-pass-dir--disabled) {{
      background: #fff;
      border-color: rgba(2, 108, 223, 0.4);
      color: #026cdf;
      animation: none;
      box-shadow: 0 4px 18px rgba(2, 108, 223, 0.18);
    }}
    .tm-pass-dir--frost.tm-pass-dir--prev:not(.tm-pass-dir--disabled) .tm-pass-dir-svg {{
      animation: tm-chevron-nudge-l 1.55s ease-in-out infinite;
    }}
    .tm-pass-dir--frost.tm-pass-dir--next:not(.tm-pass-dir--disabled) .tm-pass-dir-svg {{
      animation: tm-chevron-nudge-r 1.55s ease-in-out infinite;
    }}
    .tm-pass-dir-svg {{
      display: block;
      flex-shrink: 0;
    }}
    .tm-pass-pager__home--below {{
      display: block;
      text-align: center;
      margin: 12px auto 0;
      max-width: 448px;
      padding: 0 0.35rem;
      color: #64748b;
      font-weight: 700;
      font-size: 0.8125rem;
      text-decoration: none;
      box-sizing: border-box;
    }}
    .tm-pass-pager__home--below:hover {{
      color: #026cdf;
      text-decoration: underline;
    }}
    @media (prefers-reduced-motion: reduce) {{
      .tm-carousel-arrow--frost:not(:disabled),
      .tm-pass-dir--frost:not(.tm-pass-dir--disabled) {{
        animation: none !important;
      }}
      .tm-carousel-prev:not(:disabled) .tm-carousel-arrow-svg,
      .tm-carousel-next:not(:disabled) .tm-carousel-arrow-svg,
      .tm-pass-dir--frost.tm-pass-dir--prev:not(.tm-pass-dir--disabled) .tm-pass-dir-svg,
      .tm-pass-dir--frost.tm-pass-dir--next:not(.tm-pass-dir--disabled) .tm-pass-dir-svg {{
        animation: none !important;
      }}
      .tm-pass-menu,
      .tm-pass-title,
      .tm-pass-sub-line,
      .tm-pass-rail,
      html.tm-html-ticket-viewport .safetix-slot.tm-pass-card {{
        animation: none !important;
        opacity: 1 !important;
        transform: none !important;
      }}
      .tm-pass-bc:not(.tm-pass-bc--ready)::before {{
        animation: none !important;
        background: #f0f2f4 !important;
      }}
      .tm-pass-bc .safetix-canvas {{
        opacity: 1 !important;
        transition: none !important;
      }}
      .tm-pass-hero-bg,
      .tm-pass-brand-strip img {{
        opacity: 1 !important;
        transition: none !important;
      }}
      .tm-pass-status {{
        opacity: 1 !important;
        transition: none !important;
      }}
      .tm-pass-hero-fx::before,
      .tm-pass-hero-fx::after {{
        animation: none !important;
      }}
      .tm-pass-hero-fx::before {{
        transform: none;
        opacity: 0.78;
      }}
      .tm-pass-hero-fx::after {{
        opacity: 0.42;
      }}
      .tm-scan-line,
      .tm-scan-glow {{
        animation: none !important;
        left: 50% !important;
        opacity: 0.65 !important;
      }}
    }}
    .tm-pass-pager--controls {{
      display: flex;
      flex-wrap: nowrap;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
    }}
    .tm-pass-dir {{
      flex-shrink: 0;
      border-radius: 50%;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      text-decoration: none;
      -webkit-tap-highlight-color: transparent;
    }}
    .tm-pass-dir:not(.tm-pass-dir--frost) {{
      width: 36px;
      height: 36px;
      background: #d1d5db;
      color: #fff;
      box-shadow: none;
    }}
    .tm-pass-dir-ico {{
      font-size: 1.25rem;
      font-weight: 400;
      line-height: 1;
      display: block;
      margin-top: -1px;
    }}
    .tm-pass-dir:not(.tm-pass-dir--frost):hover:not(.tm-pass-dir--disabled) {{
      background: #c4c4c4;
    }}
    .tm-pass-dir:focus-visible {{
      outline: 2px solid #026cdf;
      outline-offset: 2px;
    }}
    .tm-pass-dir--disabled {{
      opacity: 0.4;
      pointer-events: none;
    }}
    .tm-pass-pager--controls .tm-pass-pager__home {{
      flex: 1 1 auto;
      text-align: center;
      color: #64748b;
      font-weight: 700;
      font-size: 0.8125rem;
      text-decoration: none;
      padding: 0 0.35rem;
      min-width: 0;
    }}
    .tm-pass-pager--controls .tm-pass-pager__home:hover {{
      color: #026cdf;
      text-decoration: underline;
    }}
    @media (max-width: 639px) {{
      .tm-simple-bar {{
        padding: 0.6rem max(0.75rem, env(safe-area-inset-left, 0px)) 0.6rem max(0.75rem, env(safe-area-inset-right, 0px));
        gap: 0.4rem 0.65rem;
      }}
      .tm-simple-bar .tm-wordmark-img--light {{
        width: auto;
        height: 22px;
        max-width: min(200px, 46vw);
      }}
      .tm-topbar-login-btn,
      .tm-topbar-account-trigger {{
        min-height: 44px;
        padding: 0.4rem 0.75rem;
        -webkit-tap-highlight-color: transparent;
      }}
      .tm-topbar-account-label {{
        max-width: min(120px, 28vw);
      }}
      .tm-account-menu {{
        right: max(0px, env(safe-area-inset-right, 0px));
        max-width: calc(100vw - 0.75rem - env(safe-area-inset-left, 0px) - env(safe-area-inset-right, 0px));
        min-width: 0;
        width: min(300px, 100%);
      }}
      .tm-account-menu-item {{
        min-height: 48px;
        padding-top: 0.85rem;
        padding-bottom: 0.85rem;
      }}
      .tm-retail-hero,
      .tm-retail-hero-overlay {{
        min-height: 200px;
      }}
      .tm-retail-hero-overlay {{
        padding: 1.1rem max(0.85rem, env(safe-area-inset-left, 0px)) 1.5rem max(0.85rem, env(safe-area-inset-right, 0px));
      }}
      .tm-retail-hero h1 {{
        max-width: none;
      }}
      .tm-retail-sub {{
        max-width: none;
        font-size: 0.8125rem;
      }}
      .tm-retail-cta {{
        min-height: 48px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 0.65rem 1.25rem;
      }}
      .tm-search-strip-wrap {{
        margin-top: -1rem;
        padding-left: max(0.65rem, env(safe-area-inset-left, 0px));
        padding-right: max(0.65rem, env(safe-area-inset-right, 0px));
        padding-bottom: 1.35rem;
      }}
      .tm-search-strip {{
        flex-direction: column;
        align-items: stretch;
        border-radius: 8px;
      }}
      .tm-search-seg {{
        flex: none;
        width: 100%;
        min-height: 48px;
        border-right: none;
        border-bottom: 1px solid #e8eaed;
        padding: 12px 14px;
      }}
      .tm-search-go {{
        width: 100%;
        min-height: 48px;
        flex: none;
      }}
      .tm-ticket-list-section {{
        padding-left: max(0.75rem, env(safe-area-inset-left, 0px));
        padding-right: max(0.75rem, env(safe-area-inset-right, 0px));
      }}
      body.tm-page--my-tickets main {{
        padding-left: max(0.75rem, env(safe-area-inset-left, 0px));
        padding-right: max(0.75rem, env(safe-area-inset-right, 0px));
        padding-bottom: calc(1.75rem + env(safe-area-inset-bottom, 0px));
      }}
      .tm-my-tickets-page {{
        padding-top: 0.15rem;
      }}
      .tm-my-tickets-title {{
        font-size: clamp(1.2rem, 5.5vw, 1.45rem);
      }}
      .tm-login-gate-cta {{
        min-height: 48px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding-left: 1.35rem;
        padding-right: 1.35rem;
      }}
      .tm-email-row input {{
        font-size: 16px;
        min-height: 48px;
      }}
      .tm-email-row button {{
        min-height: 48px;
        padding-left: 1rem;
        padding-right: 1rem;
      }}
      .tm-ticket-tile {{
        padding: 1.05rem 1rem;
        min-height: 52px;
      }}
      .tm-viewer-empty-tickets {{
        padding-left: max(0.75rem, env(safe-area-inset-left, 0px));
        padding-right: max(0.75rem, env(safe-area-inset-right, 0px));
      }}
      .tm-site-footer--simple {{
        padding-left: max(1rem, env(safe-area-inset-left, 0px));
        padding-right: max(1rem, env(safe-area-inset-right, 0px));
        padding-bottom: calc(1.25rem + env(safe-area-inset-bottom, 0px));
      }}
      main {{
        padding-bottom: calc(1.75rem + env(safe-area-inset-bottom, 0px));
      }}
      body.tm-page--home main {{
        padding-bottom: env(safe-area-inset-bottom, 0px);
      }}
      /* Sticky topbar is unreliable in WebKit when body is a flex column (Telegram / Safari).
         Fixed bar + body padding ≈ .topbar height (safe area + mobile .tm-simple-bar + 44px controls). */
      body.tm-page--home,
      body.tm-page--login,
      body.tm-page--my-tickets {{
        padding-top: calc(env(safe-area-inset-top, 0px) + 64px);
      }}
      body.tm-page--home > header.topbar.topbar--simple,
      body.tm-page--login > header.topbar.topbar--simple,
      body.tm-page--my-tickets > header.topbar.topbar--simple {{
        position: fixed;
        left: 0;
        right: 0;
        top: 0;
        width: 100%;
        max-width: none;
        box-sizing: border-box;
        z-index: 40;
      }}
      body.tm-shell-ticket-minimal main {{
        padding-left: max(12px, env(safe-area-inset-left, 0px));
        padding-right: max(12px, env(safe-area-inset-right, 0px));
        padding-bottom: calc(28px + env(safe-area-inset-bottom, 0px));
      }}
      html.tm-html-ticket-viewport body.tm-shell-ticket-minimal > main {{
        padding-left: max(6px, env(safe-area-inset-left, 0px));
        padding-right: max(6px, env(safe-area-inset-right, 0px));
        padding-bottom: max(8px, env(safe-area-inset-bottom, 0px));
        overflow-y: auto;
        overflow-x: hidden;
        -webkit-overflow-scrolling: touch;
        overscroll-behavior-y: contain;
        touch-action: pan-y pinch-zoom;
      }}
      html.tm-html-ticket-viewport body.tm-shell-ticket-minimal .acct.acct--tickets-only,
      html.tm-html-ticket-viewport body.tm-shell-ticket-minimal .tickets-only-panel {{
        width: 100%;
        max-width: 100%;
        margin-left: 0;
        margin-right: 0;
        align-self: stretch;
        flex: 0 0 auto;
        min-height: 0;
        overflow-x: hidden;
        overflow-y: visible;
        height: auto;
      }}
      html.tm-html-ticket-viewport .tm-pass-viewport-fit {{
        margin-left: auto;
        margin-right: auto;
        align-self: stretch;
        max-width: 100%;
        width: 100%;
        flex: 0 0 auto;
        min-height: 0;
        overflow-x: hidden;
        overflow-y: visible;
        height: auto;
      }}
      html.tm-html-ticket-viewport body.tm-shell-ticket-minimal > footer.tm-site-footer--pass-minimal {{
        display: none !important;
      }}
      html.tm-html-ticket-viewport .tm-pass-chrome-inner {{
        max-width: 100%;
        width: 100%;
        padding-left: max(10px, env(safe-area-inset-left, 0px));
        padding-right: max(10px, env(safe-area-inset-right, 0px));
        box-sizing: border-box;
      }}
      html.tm-html-ticket-viewport .tm-pass-viewport-fit-inner {{
        width: 100%;
        max-width: 100%;
        overflow-x: hidden;
        overflow-y: visible;
      }}
      html.tm-html-ticket-viewport .tm-ticket-carousel {{
        max-width: 100%;
        width: 100%;
        margin-left: auto;
        margin-right: auto;
      }}
      html.tm-html-ticket-viewport .tm-pass-card {{
        max-width: 100%;
        width: 100%;
      }}
      html.tm-html-ticket-viewport .tm-pass-pager:not(.tm-pass-pager--card-mid) {{
        max-width: 100%;
      }}
      html.tm-html-ticket-viewport .tm-pass-pager__home--below {{
        max-width: 100%;
      }}
      /* TM overlay on phone: tall hero + bottom barcode, page scrolls */
      html.tm-html-ticket-viewport .tm-pass-visual--overlay .tm-pass-hero--cover,
      html.tm-html-ticket-viewport .tm-pass-visual--overlay .tm-pass-hero--cover.tm-pass-hero--grad,
      html.tm-html-ticket-viewport .tm-pass-visual--overlay .tm-pass-hero--cover.tm-pass-hero--tmblue {{
        height: clamp(360px, 82vw, 460px);
        min-height: clamp(360px, 82vw, 460px);
        max-height: none;
      }}
      html.tm-html-ticket-viewport .tm-pass-visual--overlay .tm-pass-bar-sheet {{
        left: 6px;
        right: 6px;
        bottom: 6px;
        padding: 10px 8px 8px;
      }}
      html.tm-html-ticket-viewport .tm-pass-visual--overlay .barcode-frame canvas.safetix-canvas {{
        max-height: 108px !important;
      }}
      html.tm-html-ticket-viewport .tm-pass-card {{
        overflow: visible;
        max-height: none;
      }}
      html.tm-html-ticket-viewport .tm-carousel-viewport {{
        overflow: visible !important;
      }}
      /* Legacy stack layout (pre-V6 passes) */
      html.tm-html-ticket-viewport .tm-pass-visual--tmstack .tm-pass-bar-sheet {{
        left: auto;
        right: auto;
        padding: 10px 10px 8px;
      }}
      html.tm-html-ticket-viewport .tm-pass-hero--poster,
      html.tm-html-ticket-viewport .tm-pass-hero--poster.tm-pass-hero--grad,
      html.tm-html-ticket-viewport .tm-pass-hero--poster.tm-pass-hero--tmblue {{
        height: auto;
        min-height: clamp(210px, 54vw, 340px);
        max-height: none;
      }}
      html.tm-html-ticket-viewport .tm-pass-hero--poster .tm-pass-hero-bg {{
        height: clamp(210px, 54vw, 340px);
        min-height: clamp(210px, 54vw, 340px);
      }}
      html.tm-html-ticket-viewport .tm-pass-visual--tmstack .barcode-frame canvas.safetix-canvas {{
        max-height: 96px !important;
      }}
      /* Legacy overlay layout (pre-stack passes) */
      html.tm-html-ticket-viewport .tm-pass-hero:not(.tm-pass-hero--poster),
      html.tm-html-ticket-viewport .tm-pass-hero--grad:not(.tm-pass-hero--poster),
      html.tm-html-ticket-viewport .tm-pass-hero--tmblue:not(.tm-pass-hero--poster) {{
        height: clamp(220px, 62vw, 280px);
        min-height: clamp(220px, 62vw, 280px);
        max-height: clamp(220px, 62vw, 280px);
      }}
      html.tm-html-ticket-viewport .tm-pass-bar-sheet {{
        left: 4px;
        right: 4px;
        padding: 8px 4px 8px;
      }}
      html.tm-html-ticket-viewport .tm-ticket-carousel--side-nav .tm-pass-bar-sheet {{
        left: 48px;
        right: 48px;
      }}
      html.tm-html-ticket-viewport .tm-pass-card .tm-pass-bc.barcode-frame {{
        padding: 8px 8px 6px;
        max-width: 100%;
        width: 100%;
      }}
      html.tm-html-ticket-viewport .tm-pass-card .barcode-frame canvas.safetix-canvas {{
        max-width: 100% !important;
        width: 100% !important;
        height: auto !important;
      }}
      html.tm-html-ticket-viewport .tm-pass-card .tm-pass-bc--sg canvas.safetix-canvas {{
        max-width: min(168px, 44vw) !important;
        width: auto !important;
      }}
      html.tm-html-ticket-viewport .tm-pass-status {{
        font-size: 0.6875rem !important;
        line-height: 1.4 !important;
        margin-top: 8px !important;
      }}
      html.tm-html-ticket-viewport .tm-pass-screen-row {{
        font-size: 0.6875rem;
        margin-bottom: 8px;
      }}
      html.tm-html-ticket-viewport .tm-pass-body {{
        padding: 16px 12px 18px;
      }}
      html.tm-html-ticket-viewport .tm-pass-type-block {{
        margin-bottom: 14px;
      }}
      html.tm-html-ticket-viewport .tm-pass-kind {{
        font-size: 1.0625rem;
        line-height: 1.2;
      }}
      html.tm-html-ticket-viewport .tm-pass-verified-txt {{
        font-size: 0.875rem;
      }}
      html.tm-html-ticket-viewport .tm-pass-seats {{
        gap: 12px 10px;
        margin-bottom: 14px;
        padding: 0 4px;
      }}
      html.tm-html-ticket-viewport .tm-pass-lbl {{
        font-size: 0.625rem;
        margin-bottom: 6px;
      }}
      html.tm-html-ticket-viewport .tm-pass-seats b {{
        font-size: 1.35rem;
        line-height: 1.15;
      }}
      html.tm-html-ticket-viewport .tm-pass-gate {{
        font-size: 0.75rem;
        padding: 14px 12px;
        white-space: normal;
        line-height: 1.3;
        word-break: break-word;
      }}
      html.tm-html-ticket-viewport .tm-pass-actions {{
        flex-wrap: wrap;
        gap: 10px;
      }}
      html.tm-html-ticket-viewport .tm-pass-btn {{
        font-size: 0.72rem;
        min-height: 50px;
        padding: 12px 10px;
      }}
      html.tm-html-ticket-viewport .tm-pass-wallet--badge {{
        min-height: 52px;
      }}
      html.tm-html-ticket-viewport .tm-carousel-counter {{
        margin-top: 12px;
      }}
      html.tm-html-ticket-viewport .tm-carousel-counter__n {{
        font-size: 0.8125rem;
        padding: 6px 16px;
      }}
      .tm-pass-pager {{
        padding-left: max(0.5rem, env(safe-area-inset-left, 0px));
        padding-right: max(0.5rem, env(safe-area-inset-right, 0px));
        margin-bottom: env(safe-area-inset-bottom, 0px);
      }}
    }}
    .tm-arrival-warning {{
      display: flex;
      align-items: flex-start;
      gap: 0.5rem;
      margin: 0;
      padding: 0.6rem 0.9rem;
      background: #026cdf;
      border-bottom: 2px solid #0153a3;
      font-size: 0.74rem;
      line-height: 1.5;
      color: #fff;
      flex-shrink: 0;
      width: 100%;
      box-sizing: border-box;
    }}
    .tm-arrival-warning__icon {{
      font-size: 1rem;
      flex-shrink: 0;
      line-height: 1.5;
    }}
    .tm-arrival-warning__title {{
      display: block;
      font-size: 0.72rem;
      font-weight: 800;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      margin-bottom: 0.2rem;
      color: #fff;
    }}
    .tm-arrival-warning__body {{
      font-size: 0.72rem;
      color: rgba(255, 255, 255, 0.92);
      line-height: 1.5;
    }}
    .tm-arrival-warning__body strong {{
      color: #fff;
      font-weight: 700;
    }}
    .tm-arrival-warning__body .tm-warn-red {{
      color: #ffd0cc;
      font-weight: 700;
    }}
    @media (max-width: 480px) {{
      .tm-arrival-warning {{
        padding: 0.5rem 0.75rem;
      }}
      .tm-arrival-warning__title {{
        font-size: 0.68rem;
      }}
      .tm-arrival-warning__body {{
        font-size: 0.68rem;
      }}
    }}
  </style>
</head>
<body class="{_body_cls}">
  {_chrome_top}
  {demo_note}
  {"" if _shell != "ticket_minimal" or pass_is_sg else _tm_arrival_warning_banner_html(is_sg=False)}
  <main>
    {main_inner}
  </main>
  {_chrome_foot}
{pass_page_transfer_tail}
{reminder_body_tail}
{_safetix_live_barcode_scripts()}
</body>
</html>
"""


def build_html(
    blocks: list[dict],
    title: str = "TM hits",
    *,
    is_demo: bool = False,
    tickets_merged: bool = False,
    fetch_banner: str = "",
) -> str:
    main_inner = "\n".join(_render_account(b, i) for i, b in enumerate(blocks))
    return _tm_html_document(
        doc_title=title,
        fetch_banner=fetch_banner,
        main_inner=main_inner,
    )


def _ticket_page_doc_title(acc: dict, sub: int | None) -> str:
    slots = _collect_barcode_slots(acc)
    if not slots:
        return "Tickets"
    if sub is not None and (sub < 0 or sub >= len(slots)):
        return "Ticket"
    idx = 0 if sub is None else sub
    _cfg, label, _demo, row = slots[idx]
    r = dict(row)
    r.setdefault("label", label)
    f = _ticket_card_fields(r, acc.get("upcoming") or [])
    ev = (f["event_name"] or "Event")[:52]
    base = f"{ev} · Sec {f['section']} · Row {f['row']} · {f['seat']}"
    if sub is None and len(slots) > 1:
        return f"{ev} · {len(slots)} tickets"
    return base


def _registry_paths_ticket_equiv(a: str, b: str) -> bool:
    """True if both are the same ``tickets/<gid>/<file>.html`` path (ignores ``.html`` case)."""
    def norm(x: str) -> str:
        s = (x or "").replace("\\", "/").strip().strip("/").lower()
        return s if s.endswith(".html") else s + ".html"

    return norm(a) == norm(b)


def _registry_link_secret_for_site_pass(reg: dict, *, gid: int, fname: str) -> str:
    """``link_transfer_secret`` from registry JSON for this pass file (viewer-gated builds only)."""
    want = f"tickets/{int(gid)}/{fname}"
    be = reg.get("by_email") if isinstance(reg.get("by_email"), dict) else {}
    for lst in be.values():
        if not isinstance(lst, list):
            continue
        for t in lst:
            if not isinstance(t, dict):
                continue
            p = str(t.get("path") or "")
            if _registry_paths_ticket_equiv(p, want):
                return str(t.get("link_transfer_secret") or "").strip()
    return ""


def _viewer_registry_payload_for_site(
    blocks: list[dict],
    entries: list[tuple[int, int, str, int | None]],
    *,
    link_transfer_secrets: bool = False,
) -> dict:
    """Map hit header email → ticket card fields + relative path (one path per bundle or per seat)."""
    by_email: dict[str, list[dict]] = {}
    link_sec_by_path: dict[str, str] = {}
    for ent in entries:
        gid, ai, fname = ent[0], ent[1], ent[2]
        only_si = ent[3] if len(ent) > 3 else None
        if ai < 0 or ai >= len(blocks):
            continue
        header = (blocks[ai].get("header") or "").strip()
        em = (parse_header_meta(header).get("email") or "").strip().lower()
        if not em or "@" not in em:
            # Hits without email:pass in header still get static passes — bucket them so registry + link_secret exist.
            em = (
                (os.environ.get("TM_VIEWER_ORPHAN_TICKETS_EMAIL") or "").strip().lower()
                or "_orphan@tm-viewer.internal"
            )
            if "." not in em.rsplit("@", 1)[-1]:
                em = "_orphan@tm-viewer.internal"
        acc = blocks[ai]
        acc_e = _acc_with_single_barcode_slot(acc, only_si) if only_si is not None else acc
        slots = _collect_barcode_slots(acc_e)
        path = f"tickets/{gid}/{fname}"

        def _one_reg_row(_cfg: str, label: str, _demo: bool, row: dict) -> None:
            r = dict(row)
            r.setdefault("label", label)
            f = _ticket_card_fields(r, acc_e.get("upcoming") or [])
            entry = {
                "path": path,
                "event_name": (f.get("event_name") or "Event").strip(),
                "subtitle": (f.get("subtitle") or "").strip(),
                "section": str(f.get("section") or ""),
                "row": str(f.get("row") or ""),
                "seat": str(f.get("seat") or ""),
            }
            if link_transfer_secrets:
                if path not in link_sec_by_path:
                    link_sec_by_path[path] = secrets.token_urlsafe(32)
                entry["link_transfer_secret"] = link_sec_by_path[path]
            by_email.setdefault(em, []).append(entry)

        if only_si is not None:
            # --one-html-per-seat: exactly one registry row per HTML file (path matches one seat).
            if not slots:
                continue
            _cfg, label, _demo, row = slots[0]
            _one_reg_row(_cfg, label, _demo, row)
        else:
            for _cfg, label, _demo, row in slots:
                _one_reg_row(_cfg, label, _demo, row)
    return {"version": 1, "by_email": by_email}


def build_html_site(
    blocks: list[dict],
    *,
    title: str = "Tickets",
    fetch_banner: str = "",
    viewer_api_base: str | None = None,
    viewer_mail_api_base: str | None = None,
    viewer_auth_ui: bool = False,
    viewer_login_url: str | None = None,
    debug_site_root: Path | None = None,
    one_html_per_seat: bool = False,
) -> dict[str, str]:
    """Multi-page site: index.html + tickets/{n}/….html per account (carousel) or per seat (--one-html-per-seat)."""
    account_indices: list[int] = []
    for ai, acc in enumerate(blocks):
        if _collect_barcode_slots(acc):
            account_indices.append(ai)
    if not account_indices:
        return {"index.html": build_html(blocks, title=title, fetch_banner=fetch_banner)}
    entries: list[tuple[int, int, str, int | None]] = []
    gid = 0
    for ai in account_indices:
        acc = blocks[ai]
        slots = _collect_barcode_slots(acc)
        if one_html_per_seat and len(slots) >= 1:
            for si in range(len(slots)):
                _cfg, _lab, _demo, row = slots[si]
                fname = _ticket_standalone_html_name(
                    ai, si, _cfg, slug_salt=_pass_slug_salt_from_row(row)
                )
                entries.append((gid, ai, fname, si))
                gid += 1
        else:
            fname = _account_bundle_html_name(ai, slots)
            entries.append((gid, ai, fname, None))
            gid += 1
    fnames_order = [e[2] for e in entries]
    files: dict[str, str] = {}
    baked_api = (viewer_api_base or "").strip().rstrip("/")
    use_api = bool(baked_api) or bool(viewer_auth_ui)
    baked_login = (viewer_login_url or "").strip() or _DEFAULT_TM_LOGIN_URL
    tiles: list[str] = []
    if not use_api:
        for gid, ai, fname, only_si in entries:
            acc = blocks[ai]
            acc_e = _acc_with_single_barcode_slot(acc, only_si) if only_si is not None else acc
            slots = _collect_barcode_slots(acc_e)
            _c0, lab0, _d0, row0 = slots[0]
            r0 = dict(row0)
            r0.setdefault("label", lab0)
            f = _ticket_card_fields(r0, acc_e.get("upcoming") or [])
            ns = len(slots)
            if ns <= 1:
                seat_line = (
                    f"Sec {_escape(f['section'])} · Row {_escape(f['row'])} · Seat {_escape(f['seat'])}"
                )
            else:
                seat_line = (
                    f"Sec {_escape(f['section'])} · Row {_escape(f['row'])} · {ns} seats"
                )
            tiles.append(
                f'<a class="tm-ticket-tile" href="tickets/{gid}/{_ticket_href_clean(fname)}">'
                f'<div class="tm-tile-ev">{_escape(f["event_name"])}</div>'
                f'<div class="tm-tile-meta">{_escape(f["subtitle"])}</div>'
                f'<div class="tm-tile-seat">{seat_line}</div>'
                f'<span class="tm-tile-cta">VIEW {"TICKETS" if ns > 1 else "TICKET"}</span></a>'
            )
    hero_img = ""
    kicker = "YOUR TICKETS"
    h1 = "Pick a ticket to open your pass"
    sub = "Each event has its own page with a live, rotating barcode."
    if entries:
        _gid0, ai0, _fn0, osi0 = entries[0][0], entries[0][1], entries[0][2], entries[0][3]
        acc0 = blocks[ai0]
        acc0e = _acc_with_single_barcode_slot(acc0, osi0) if osi0 is not None else acc0
        slots0 = _collect_barcode_slots(acc0e)
        if slots0:
            _c0, lab0, _d0, row0 = slots0[0]
            r0 = dict(row0)
            r0.setdefault("label", lab0)
            f0 = _ticket_card_fields(r0, acc0e.get("upcoming") or [])
            kicker = "FEATURED"
            h1 = (f0["event_name"] or h1).strip() or h1
            sub0 = (f0["subtitle"] or "").strip()
            if sub0:
                sub = sub0
            if use_api:
                sub = (
                    "You cannot view your tickets here until you sign in. "
                    "Use Log in (top) or View tickets below, then open the sign-in page."
                )
            rem0 = (f0.get("image_url_remote") or "").strip()
            loc0 = (f0.get("image_url") or "").strip()
            if (
                not _tm_viewer_hero_prefer_local_files()
                and rem0
                and (rem0.startswith("http://") or rem0.startswith("https://"))
            ):
                iu0 = rem0
            else:
                iu0 = loc0
            if not _pass_hero_url_safe_for_img_src(iu0, site_root=debug_site_root):
                iu0 = ""
            if (
                iu0.startswith("http://")
                or iu0.startswith("https://")
                or iu0.startswith("/")
                or iu0.startswith("data:")
            ):
                hero_img = (
                    f'<img class="tm-retail-hero-img" src="{_escape(iu0)}" alt="" '
                    f'loading="eager" decoding="async" referrerpolicy="no-referrer"/>'
                )
            elif iu0:
                hero_img = (
                    f'<img class="tm-retail-hero-img" src="{_escape(iu0)}" alt="" '
                    f'loading="eager" decoding="async" referrerpolicy="no-referrer"/>'
                )
    home_inner = (
        '<div class="tm-home-wrap tm-home-retail">'
        '<section class="tm-retail-hero" aria-label="Featured">'
        f"{hero_img}"
        '<div class="tm-retail-hero-overlay">'
        f'<p class="tm-retail-kicker">{_escape(kicker)}</p>'
        f"<h1>{_escape(h1)}</h1>"
        f'<p class="tm-retail-sub">{_escape(sub)}</p>'
        f'<a class="tm-retail-cta" href="{_escape(_DEFAULT_TM_MY_TICKETS_URL if use_api else "#tm-ticket-list")}">'
        "View tickets</a>"
        "</div></section>"
        f"{_tm_home_search_strip_markup()}"
        + (
            _tm_viewer_ticket_list_block(baked_login, standalone=False)
            if use_api
            else (
                '<section id="tm-ticket-list" class="tm-ticket-list-section" aria-label="Your tickets">'
                '<h2 class="tm-section-heading">Your tickets</h2>'
                '<div class="tm-ticket-grid">'
                f'{"".join(tiles)}'
                "</div></section>"
            )
        )
        + "</div>"
    )
    files["index.html"] = _tm_html_document(
        doc_title=title,
        fetch_banner=fetch_banner,
        main_inner=home_inner,
        topbar_subtitle="" if use_api else "My tickets",
        body_class_extra="tm-page--home",
        shell="retail_simple",
        home_topbar_login=use_api,
    )
    if use_api:
        files["login.html"] = _tm_html_document(
            doc_title="Sign in",
            fetch_banner=fetch_banner,
            main_inner=_tm_viewer_login_page_block(),
            topbar_subtitle="",
            body_class_extra="tm-page--login",
            shell="retail_simple",
            home_topbar_login=True,
        )
        files["my-tickets.html"] = _tm_html_document(
            doc_title="My tickets",
            fetch_banner=fetch_banner,
            main_inner=_tm_viewer_ticket_list_block(baked_login, standalone=True),
            topbar_subtitle="",
            body_class_extra="tm-page--my-tickets",
            shell="retail_simple",
            home_topbar_login=True,
        )
        files["tm_viewer_login_url.js"] = _tm_viewer_login_url_js_contents(baked_login)
        files["tm_viewer_api_base.js"] = _tm_viewer_api_base_js_contents(baked_api)
        files["tm_viewer_mail_api_base.js"] = _tm_viewer_mail_api_base_js_contents(
            (viewer_mail_api_base or "").strip().rstrip("/"),
        )
    # Email → ticket paths for stubby / tm_viewer_link_registry.py (any multi-page build, not only API gate).
    reg: dict = {"version": 1, "by_email": {}}
    if entries:
        reg = _viewer_registry_payload_for_site(
            blocks, entries, link_transfer_secrets=use_api
        )
        files["tm_viewer_link_registry.json"] = json.dumps(reg, indent=2, ensure_ascii=False) + "\n"
    total = len(entries)
    slug_overrides = _load_tm_viewer_safetix_slug_overrides()
    for gid, ai, fname, only_si in entries:
        acc = blocks[ai]
        acc_e = _acc_with_single_barcode_slot(acc, only_si) if only_si is not None else acc
        slots = _collect_barcode_slots(acc_e)
        ns = len(slots)
        if one_html_per_seat and only_si is not None and ns > 1:
            print(
                f"[*] one-html-per-seat: tickets/{gid}/{fname} had {ns} slots after slice — "
                f"re-slicing only_si={only_si}",
                flush=True,
            )
            acc_e = _acc_with_single_barcode_slot(acc, only_si)
            slots = _collect_barcode_slots(acc_e)
            ns = len(slots)
        if one_html_per_seat and only_si is not None and ns > 1:
            bt0 = acc_e.get("barcode_tokens") or []
            if len(bt0) > 1:
                acc_e = dict(acc_e)
                acc_e["barcode_tokens"] = [copy.deepcopy(bt0[0])]
                acc_e.pop("secure_token_b64", None)
                slots = _collect_barcode_slots(acc_e)
                ns = len(slots)
                print(
                    f"[*] one-html-per-seat: truncated tickets/{gid}/{fname} to first barcode_tokens row "
                    f"(was multi-slot)",
                    flush=True,
                )
        prev_href = (
            f"../{gid - 1}/{_ticket_href_clean(fnames_order[gid - 1])}" if gid > 0 else ""
        )
        next_href = (
            f"../{gid + 1}/{_ticket_href_clean(fnames_order[gid + 1])}" if gid < total - 1 else ""
        )
        nav = {
            "home": "../../index.html",
            "prev": prev_href,
            "next": next_href,
        }
        # One account, bundled page: in-page carousel switches seats; multi-page pager links adjacent passes.
        # --one-html-per-seat (restore "individual"): each URL must be a standalone pass — no prev/next to other seats.
        if one_html_per_seat:
            pass_nav_arg = None
        else:
            pass_nav_arg = None if total == 1 else nav
        xfer_path = f"tickets/{gid}/{_ticket_href_clean(fname)}" if use_api else ""
        slug = _ticket_href_clean(fname)
        st_override = (
            _safetix_override_cfg_b64_for_slug(slug_overrides, slug) if one_html_per_seat else None
        )
        wallet_built = (gid, fname) if _tm_viewer_wallet_built_enabled() else None
        inner = _render_account(
            acc_e,
            ai,
            only_sub=None,
            back_href="../../index.html",
            pass_nav=pass_nav_arg,
            relative_asset_prefix="../../",
            debug_ticket_file=f"tickets/{gid}/{fname}",
            debug_site_root=debug_site_root,
            viewer_transfer_relpath=xfer_path,
            safetix_cfg_b64_override=st_override,
            wallet_built=wallet_built,
        )
        if ns > 1:
            sub_title = f"{ns} tickets"
        else:
            sub_title = "My ticket"
        if total > 1 and not one_html_per_seat:
            sub_title = f"{sub_title} · {gid + 1} of {total}"
        baked_mail = (viewer_mail_api_base or "").strip().rstrip("/") if use_api else ""
        link_cap = (
            _registry_link_secret_for_site_pass(reg, gid=gid, fname=fname) if use_api else ""
        )
        xfer_tail = (
            _tm_pass_transfer_page_inject(
                xfer_path,
                mail_api_base=baked_mail,
                link_transfer_secret=link_cap,
            )
            if xfer_path
            else ""
        )
        r_head, r_tail = _tm_viewer_reminder_fragments(acc_e, only_si=only_si)
        files[f"tickets/{gid}/{fname}"] = _tm_html_document(
            doc_title=_ticket_page_doc_title(acc_e, None),
            fetch_banner="",
            main_inner=inner,
            topbar_subtitle=sub_title,
            shell="ticket_minimal",
            pass_page_transfer_tail=xfer_tail,
            reminder_head_metas=r_head,
            reminder_body_tail=r_tail,
            pass_is_sg=_acc_has_sg_barcode(acc_e),
        )
    if entries and _tm_viewer_wallet_built_enabled():
        print(
            "[*] Apple Wallet: pass pages link to signed /api/tm-pkpass — configure Vercel TM_WALLET_* "
            "and Apple signing certs (see tm-vercel-site README).",
            flush=True,
        )
    return files


def _default_stubhub_tm_bz_dir() -> Path:
    here = Path(__file__).resolve().parent
    for cand in (
        Path(os.environ.get("STUBBY_BASE_DIR", "").strip() or ""),
        Path(r"C:\Users\Administrator\Desktop\Stubhub\stubhub\tm.bz"),
        Path(r"C:\Users\Administrator\Desktop\Stubhub\stubhub"),
        here / "ticketmaster",
        here,
    ):
        if not cand:
            continue
        if (cand / "tm-vercel-site" / "tickets").is_dir():
            return cand
        if (cand / "tm.bz" / "tm-vercel-site" / "tickets").is_dir():
            return cand / "tm.bz"
    return here


def run_reslug_secure_pass_stock_cmd(
    stubby_dir: Path,
    *,
    confirm: bool,
    skip_reslug: bool,
    skip_barcodes: bool,
    vercel_site: Path | None = None,
    no_backup: bool = False,
) -> int:
    """Reslug pass HTML + sync secure_pass_stock.csv; scrape barcodes from HTML into each line."""
    here = Path(__file__).resolve().parent
    stubby_dir = stubby_dir.expanduser().resolve()
    os.environ.setdefault("TM_VIEWER_PUBLIC_BASE", _TM_VIEWER_GATEWAY_PUBLIC_BASE_DEFAULT)
    os.environ.setdefault("TM_VIEWER_GATEWAY_PUBLIC_BASE", _TM_VIEWER_GATEWAY_PUBLIC_BASE_DEFAULT)

    reslug_py = here / "ticketmaster" / "reslug_secure_pass_stock.py"
    if not reslug_py.is_file():
        reslug_py = stubby_dir / "reslug_secure_pass_stock.py"
    if not reslug_py.is_file():
        print(f"[!] reslug_secure_pass_stock.py not found (looked under {here / 'ticketmaster'})", file=sys.stderr)
        return 1

    cmd: list[str] = [sys.executable, str(reslug_py), "--stubby-dir", str(stubby_dir)]
    if vercel_site:
        cmd.extend(["--vercel-site", str(vercel_site.expanduser().resolve())])
    if skip_reslug and not skip_barcodes:
        cmd.append("--barcode-backfill-only")
    elif skip_barcodes:
        cmd.append("--skip-barcode-backfill")
    if confirm:
        cmd.append("--confirm")
    if no_backup:
        cmd.append("--no-backup")

    print(f"[*] {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=str(stubby_dir if stubby_dir.is_dir() else here))
    return int(proc.returncode or 0)


def main() -> None:
    os.environ.setdefault(
        "TM_VIEWER_GATEWAY_PUBLIC_BASE", _TM_VIEWER_GATEWAY_PUBLIC_BASE_DEFAULT
    )
    os.environ.setdefault("TM_VIEWER_USE_PASS_GATEWAY", "1")
    if not (os.environ.get("TM_VIEWER_WATCH_PUBLIC_BASE") or "").strip():
        os.environ["TM_VIEWER_WATCH_PUBLIC_BASE"] = (
            _TM_VIEWER_PASS_SITE_PUBLIC_BASE_DEFAULT
        )
    ap = argparse.ArgumentParser(description="Render TM success/hit .txt as HTML and open in browser.")
    ap.add_argument(
        "file",
        nargs="?",
        default="",
        help="Path to .txt (default: draft/results/success.txt next to this script)",
    )
    ap.add_argument(
        "--demo",
        action="store_true",
        help="Render the built-in sample hit (landenmaynard layout you sent)",
    )
    ap.add_argument(
        "--tickets",
        default="",
        metavar="PATH",
        help=(
            "Checker tickets.txt OR upcoming/pm/hits dump. Use PATH to one file "
            "(e.g. Data_for_recovery/upcoming (4).txt), a folder, or auto to merge all "
            "Data_for_recovery dumps (not tickets.txt only)."
        ),
    )
    ap.add_argument(
        "--embedded-tickets",
        action="store_true",
        help="Merge zlib+base64 ticket dump embedded in this script (_EMBEDDED_TICKETS_ZB64)",
    )
    ap.add_argument(
        "--fetch-barcodes",
        action="store_true",
        help="Call TM app API (events + securetickets) using id-token/tmpt from Cookies — same idea as tm-fcap Go checker",
    )
    ap.add_argument(
        "--cookies-file",
        default="",
        metavar="PATH",
        help="Merge this cookie string into every block before --fetch-barcodes (e.g. tm_auth_cookie_string.txt)",
    )
    ap.add_argument(
        "--proxy",
        default="",
        metavar="SPEC",
        help=(
            "HTTP proxy for --fetch-barcodes: host:port:user:pass or http://user:pass@host:port "
            "(else env TM_HIT_VIEWER_PROXY, else built-in default in script)"
        ),
    )
    ap.add_argument(
        "--no-proxy",
        action="store_true",
        help="For --fetch-barcodes: do not use built-in default proxy (still honors --proxy / TM_HIT_VIEWER_PROXY)",
    )
    ap.add_argument("-o", "--out", default="", help="Output .html path (ignored when --site-dir is set)")
    ap.add_argument(
        "--site-dir",
        default="",
        metavar="DIR",
        help=(
            "Write multi-page site: index.html + one bundle under tickets/{n}/ per hit block (all seats = in-page "
            "carousel; side arrows swap seats without a new page). Pass pager only if multiple blocks. "
            "+ tm_event_assets/ with --download-event-images."
        ),
    )
    ap.add_argument(
        "--one-html-per-seat",
        action="store_true",
        help=(
            "Under --site-dir: write one pass HTML per barcode seat (separate URL each) instead of bundling all "
            "seats into one carousel page. Restore / individual links should use this."
        ),
    )
    ap.add_argument(
        "--viewer-api-base",
        default="",
        metavar="URL",
        help=(
            "With --site-dir: still writes tm_viewer_link_registry.json (for optional python API / stubby). "
            "Homepage is a sign-in teaser + login.html for OTP, not an in-page ticket list until signed in."
        ),
    )
    ap.add_argument(
        "--viewer-auth-ui",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "With --site-dir: index teaser + login.html (email/OTP), Log in topbar; "
            "writes tm_viewer_link_registry.json (default: on). Use --no-viewer-auth-ui for static ticket tiles only."
        ),
    )
    ap.add_argument(
        "--viewer-login-url",
        default="",
        metavar="URL",
        help=(
            "With --site-dir + viewer gate: URL for Sign in / Log in (default /login, Vercel cleanUrls). "
            "Env TM_VIEWER_LOGIN_URL if unset."
        ),
    )
    ap.add_argument(
        "--viewer-mail-api-base",
        default="",
        metavar="URL",
        help=(
            "With --site-dir + viewer gate: stubby/public base for buyer transfer POST "
            "(e.g. http://VPS:9440). Bakes tm_viewer_mail_api_base.js. Env TM_VIEWER_MAIL_API_BASE or "
            "TM_VIEWER_EMAIL_BACKEND_URL if unset."
        ),
    )
    ap.add_argument(
        "--stubby-proxy-url",
        default="",
        metavar="URL",
        help=(
            "Same as --viewer-mail-api-base for --site-dir and as --inject-mail-api-base for inject modes, "
            "when those flags are omitted. Use your stubby TM viewer proxy (http://IP:9440). For https:// "
            "ticket pages in production, leave empty and set Vercel TM_VIEWER_EMAIL_BACKEND_URL to this URL."
        ),
    )
    ap.add_argument(
        "--ignite-stubby",
        default="",
        metavar="SITE_DIR",
        help=(
            "Pipeline shorthand: --inject-pass-transfer-ui SITE_DIR --replace-pass-transfer-ui (all passes get "
            "transfer UI). Mail/transfer backend: use --stubby-proxy-url or env TM_VIEWER_MAIL_API_BASE / "
            "TM_VIEWER_EMAIL_BACKEND_URL (see top-of-file HTTPS note)."
        ),
    )
    ap.add_argument("--no-open", action="store_true", help="Do not launch browser")
    ap.add_argument(
        "--resolve-event-images",
        action="store_true",
        help="Fill missing hero images via Ticketmaster Discovery API (TM_DISCOVERY_CONSUMER_KEY in script)",
    )
    ap.add_argument(
        "--event-media-cache",
        default="",
        metavar="PATH",
        help="JSON map event_key → image_url (default: results/tm_event_media.json next to this script)",
    )
    ap.add_argument(
        "--download-event-images",
        action="store_true",
        help="Download http(s) hero images to <output_dir>/tm_event_assets/ and reference them with relative paths",
    )
    ap.add_argument(
        "--verify-crypto",
        action="store_true",
        help="Exit after checking PDF417 payload vs tm-fcap-makefast/barcode.py (same math as TM SafeTix)",
    )
    ap.add_argument(
        "--refresh-pass-safetix",
        default="",
        metavar="SITE_DIR",
        help=(
            "Only patch SITE_DIR/tickets/<gid>/*.html: remove PDF417 debug markup, repair hero posters "
            "(cache/tm_event_assets), inject refresh-barcode + sizing CSS, and replace embedded "
            "SafeTix (CryptoJS+bwip+inline) with this script's current runtime. "
            "Optional with --resolve-event-images --download-event-images. "
            "Use --dev-pass to patch only the tixx test ticket (Chris Stapleton / tickets/19/…). Then exit."
        ),
    )
    ap.add_argument(
        "--only-pass",
        default="",
        metavar="URL_OR_PATH",
        help=(
            "With --refresh-pass-safetix, --regen-all-passes, or --update-pass-date: limit to one pass file "
            "(full tixx URL, tickets/19/slug.html, or 19/slug). Implies single-file mode."
        ),
    )
    ap.add_argument(
        "--dev-pass",
        action="store_true",
        help=(
            f"Shortcut for --only-pass {_DEV_TEST_PASS_URL} "
            "(Chris Stapleton Sec 208 · Row J · Seat 6 — layout testing)."
        ),
    )
    ap.add_argument(
        "--all-passes",
        action="store_true",
        help="With --refresh-pass-safetix / --regen-all-passes: process every pass (ignore --only-pass / --dev-pass).",
    )
    ap.add_argument(
        "--regen-all-passes",
        default="",
        metavar="SITE_DIR",
        help=(
            "Rebuild every SITE_DIR/tickets/<gid>/*.html with the current pass layout (hero overlay, gate pill, "
            "QR/PDF417 sizing, verified-ticket block). Scrapes data-tm-safetix from each file — same URL/slug, "
            "no tickets.txt required. Optional: --resolve-event-images --download-event-images. Then exit."
        ),
    )
    ap.add_argument(
        "--inject-ticket-reminders",
        default="",
        metavar="SITE_DIR",
        help=(
            "Only patch SITE_DIR/tickets/<gid>/*.html: insert tm-reminder metas + optional tm-email-gate.js "
            "(does not alter data-tm-safetix or SafeTix scripts). Skips transfer stubs. "
            "Env: TM_VIEWER_WATCH_PUBLIC_BASE, TM_VIEWER_REMINDER_REGISTER_URL, TM_VIEWER_EMBED_EMAIL_GATE "
            "(default 1), TM_VIEWER_EMAIL_GATE_JS_URL. Then exit."
        ),
    )
    ap.add_argument(
        "--replace-ticket-reminders",
        action="store_true",
        help=(
            "With --inject-ticket-reminders: remove prior inject blocks / legacy reminder metas, then re-insert."
        ),
    )
    ap.add_argument(
        "--update-reminder-dates",
        default="",
        metavar="SITE_DIR",
        help=(
            "Only patch existing SITE_DIR/tickets/<gid>/*.html reminder date metas from links.txt "
            "(tm-event-start for timed events, or tm-reminder-date/date_slots for date-only). Then exit."
        ),
    )
    ap.add_argument(
        "--update-pass-date",
        default="",
        metavar="SITE_DIR",
        help=(
            "Patch visible pass subtitle date (tm-pass-sub) + reminder metas on existing passes. "
            "Requires --only-pass URL. Use --event-date YYYY-MM-DD; optional --event-time HH:MM "
            "and --event-timezone (e.g. America/Chicago). Barcodes unchanged. Run on VPS with tickets/. Then exit."
        ),
    )
    ap.add_argument(
        "--event-date",
        default="",
        metavar="YYYY-MM-DD",
        help="Target event date for --update-pass-date (e.g. 2026-08-01).",
    )
    ap.add_argument(
        "--event-time",
        default="",
        metavar="HH:MM",
        help="Optional 24h show time for --update-pass-date (e.g. 19:00 → Sat, Aug 01, 2026 · 7:00 PM).",
    )
    ap.add_argument(
        "--event-timezone",
        default="",
        metavar="IANA",
        help="Optional IANA tz with --event-time (e.g. America/Chicago for Globe Life Field).",
    )
    ap.add_argument(
        "--links-txt",
        default="",
        metavar="PATH",
        help="links.txt path for --update-reminder-dates / --update-pass-date (optional; auto-detect if omitted).",
    )
    ap.add_argument(
        "--reminder-date-only-slots",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "When reminder metadata has only YYYY-MM-DD (no event time), emit date-slot reminder metas "
            "(12:00 AM, 12:00 PM, 6:00 PM). Disable with --no-reminder-date-only-slots."
        ),
    )
    ap.add_argument(
        "--inject-pass-transfer-ui",
        default="",
        metavar="SITE_DIR",
        help=(
            "Only patch existing pass HTML: scan SITE_DIR/tickets/<gid>/*.html and add Transfer button + "
            "modal/scripts where missing (no success.txt regenerate). Then exit."
        ),
    )
    ap.add_argument(
        "--replace-pass-transfer-ui",
        action="store_true",
        help=(
            "With --inject-pass-transfer-ui: strip old transfer block and insert the latest (required after "
            "tm_hit_viewer updates; without this, already-injected passes are skipped)."
        ),
    )
    ap.add_argument(
        "--inject-mail-api-base",
        default="",
        metavar="URL",
        help=(
            "With --inject-pass-transfer-ui: write SITE_DIR/tm_viewer_mail_api_base.js. For https:// sites "
            "(e.g. Vercel) use empty / omit flag: browser cannot call http:// stubby (mixed content); "
            "transfer uses same-origin /api/... and Vercel TM_VIEWER_EMAIL_BACKEND_URL. Use https:// stubby "
            "or leave empty; http:// only for http:// ticket pages."
        ),
    )
    ap.add_argument(
        "--inject-arrival-warning",
        default="",
        metavar="SITE_DIR",
        help=(
            "Patch existing tickets/<gid>/*.html in SITE_DIR: inject the 45-minute arrival warning banner "
            "immediately before <main> in every pass page. Then exit. "
            "Skip files that already have the banner (use --replace-arrival-warning to overwrite)."
        ),
    )
    ap.add_argument(
        "--replace-arrival-warning",
        action="store_true",
        help="With --inject-arrival-warning: strip the old banner and re-inject the current one.",
    )
    ap.add_argument(
        "--reslug-secure-pass-stock",
        nargs="?",
        const="auto",
        default="",
        metavar="STUBBY_DIR",
        help=(
            "Reslug all live pass HTML (new slugs), sync secure_pass_stock.csv + links to tixx.cc URLs, "
            "and inject display barcodes scraped from data-tm-safetix in each pass file. "
            "Default dir: STUBBY_BASE_DIR or …\\Stubhub\\stubhub\\tm.bz. Dry-run unless --confirm."
        ),
    )
    ap.add_argument(
        "--backfill-stock-barcodes",
        nargs="?",
        const="auto",
        default="",
        metavar="STUBBY_DIR",
        help=(
            "Update secure_pass_stock.csv: normalize URLs to tixx.cc + inject barcodes from "
            "Data_for_recovery + pass HTML. With --confirm: rotate pass HTML slugs first (new links), "
            "then backfill. Use --barcode-only with --confirm to skip slug rotation. Dry-run unless --confirm."
        ),
    )
    ap.add_argument(
        "--barcode-only",
        action="store_true",
        help="With --backfill-stock-barcodes --confirm: update CSV only (no new slugs on disk).",
    )
    ap.add_argument(
        "--confirm",
        action="store_true",
        help="Apply --reslug-secure-pass-stock / --backfill-stock-barcodes (default is dry-run).",
    )
    ap.add_argument(
        "--no-backup",
        action="store_true",
        help="With --confirm: skip .bak backup of stock CSV before reslug/barcode backfill.",
    )
    args = ap.parse_args()
    os.environ["TM_VIEWER_REMINDER_DATE_ONLY_SLOTS"] = (
        "1" if bool(getattr(args, "reminder_date_only_slots", True)) else "0"
    )

    here = Path(__file__).resolve().parent
    _stubby_u = (getattr(args, "stubby_proxy_url", "") or "").strip().rstrip("/")
    if _stubby_u:
        if not (getattr(args, "viewer_mail_api_base", "") or "").strip():
            args.viewer_mail_api_base = _stubby_u
        if not (getattr(args, "inject_mail_api_base", "") or "").strip():
            args.inject_mail_api_base = _stubby_u
    _ignite = (getattr(args, "ignite_stubby", "") or "").strip()
    if _ignite:
        args.inject_pass_transfer_ui = _ignite
        args.replace_pass_transfer_ui = True

    _reslug = (getattr(args, "reslug_secure_pass_stock", "") or "").strip()
    _backfill = (getattr(args, "backfill_stock_barcodes", "") or "").strip()
    if _reslug or _backfill:
        stub = _default_stubhub_tm_bz_dir()
        if _reslug and _reslug != "auto":
            stub = Path(_reslug).expanduser()
        elif _backfill and _backfill != "auto":
            stub = Path(_backfill).expanduser()
        rc = run_reslug_secure_pass_stock_cmd(
            stub,
            confirm=bool(getattr(args, "confirm", False)),
            skip_reslug=bool(
                _backfill
                and not _reslug
                and (
                    getattr(args, "barcode_only", False)
                    or not getattr(args, "confirm", False)
                )
            ),
            skip_barcodes=False,
            no_backup=bool(getattr(args, "no_backup", False)),
        )
        raise SystemExit(rc)

    ref_sfx = (getattr(args, "refresh_pass_safetix", "") or "").strip()
    if ref_sfx:
        site_ref = Path(ref_sfx).expanduser().resolve()
        em_cache_arg = (getattr(args, "event_media_cache", "") or "").strip()
        media_cache_path = Path(em_cache_arg) if em_cache_arg else _default_event_media_cache_path()
        only_rel = _resolve_only_pass_filter(
            only_pass=getattr(args, "only_pass", "") or "",
            dev_pass=bool(getattr(args, "dev_pass", False)),
            all_passes=bool(getattr(args, "all_passes", False)),
        )
        n_rf, rf_msgs = refresh_pass_safetix_runtime_in_site_dir(
            site_ref,
            resolve_event_images=bool(getattr(args, "resolve_event_images", False)),
            download_event_images=bool(getattr(args, "download_event_images", False)),
            event_media_cache=media_cache_path,
            only_pass_rel=only_rel,
        )
        for ln in rf_msgs:
            print(ln, flush=True)
        print(f"[*] SafeTix refresh: updated {n_rf} pass file(s) under {site_ref}", flush=True)
        raise SystemExit(0)

    regen_all = (getattr(args, "regen_all_passes", "") or "").strip()
    if regen_all:
        site_arg = Path(regen_all).expanduser()
        em_cache_arg = (getattr(args, "event_media_cache", "") or "").strip()
        media_cache_path = Path(em_cache_arg) if em_cache_arg else _default_event_media_cache_path()
        only_rel = _resolve_only_pass_filter(
            only_pass=getattr(args, "only_pass", "") or "",
            dev_pass=bool(getattr(args, "dev_pass", False)),
            all_passes=bool(getattr(args, "all_passes", False)),
        )
        n_rg, rg_msgs = regen_all_passes_in_site_dir(
            site_arg,
            resolve_event_images=bool(getattr(args, "resolve_event_images", False)),
            download_event_images=bool(getattr(args, "download_event_images", False)),
            event_media_cache=media_cache_path,
            only_pass_rel=only_rel,
        )
        for ln in rg_msgs:
            if ln:
                print(ln, flush=True)
        resolved, _ = _resolve_pass_site_root(site_arg)
        site_label = resolved or site_arg
        print(
            f"[*] Regen all passes: rebuilt {n_rg} pass file(s) under {site_label}",
            flush=True,
        )
        raise SystemExit(1 if resolved is None else 0)

    inj_rem = (getattr(args, "inject_ticket_reminders", "") or "").strip()
    if inj_rem:
        site_rm = Path(inj_rem).expanduser().resolve()
        rm_rep = bool(getattr(args, "replace_ticket_reminders", False))
        n_rm, rm_msgs = inject_ticket_reminders_into_site_dir(
            site_rm, replace_existing=rm_rep
        )
        for ln in rm_msgs:
            print(ln, flush=True)
        print(f"[*] Ticket reminders: updated {n_rm} pass file(s) under {site_rm}", flush=True)
        raise SystemExit(0)

    upd_rem = (getattr(args, "update_reminder_dates", "") or "").strip()
    if upd_rem:
        site_upd = Path(upd_rem).expanduser().resolve()
        n_upd, upd_msgs = update_reminder_dates_from_links_txt(
            site_upd,
            links_txt=(getattr(args, "links_txt", "") or "").strip(),
        )
        for ln in upd_msgs:
            print(ln, flush=True)
        print(f"[*] Reminder dates: updated {n_upd} pass file(s) under {site_upd}", flush=True)
        raise SystemExit(0)

    upd_pass = (getattr(args, "update_pass_date", "") or "").strip()
    if upd_pass:
        site_pd = Path(upd_pass).expanduser().resolve()
        only_rel = _resolve_only_pass_filter(
            only_pass=getattr(args, "only_pass", "") or "",
            dev_pass=bool(getattr(args, "dev_pass", False)),
            all_passes=bool(getattr(args, "all_passes", False)),
        )
        n_pd, pd_msgs = update_pass_date_in_site_dir(
            site_pd,
            only_pass_rel=only_rel,
            event_date=(getattr(args, "event_date", "") or "").strip(),
            event_time=(getattr(args, "event_time", "") or "").strip(),
            event_tz=(getattr(args, "event_timezone", "") or "").strip(),
            links_txt=(getattr(args, "links_txt", "") or "").strip(),
        )
        for ln in pd_msgs:
            print(ln, flush=True)
        print(f"[*] Pass dates: updated {n_pd} pass file(s) under {site_pd}", flush=True)
        raise SystemExit(0 if n_pd else 1)

    inj_warn = (getattr(args, "inject_arrival_warning", "") or "").strip()
    if inj_warn:
        site_warn = Path(inj_warn).expanduser().resolve()
        warn_replace = bool(getattr(args, "replace_arrival_warning", False))
        n_warn, warn_msgs = inject_arrival_warning_into_site_dir(site_warn, replace_existing=warn_replace)
        for ln in warn_msgs:
            print(ln, flush=True)
        print(f"[*] Arrival warning injected into {n_warn} pass file(s) under {site_warn}", flush=True)
        raise SystemExit(0)

    inj_ui = (getattr(args, "inject_pass_transfer_ui", "") or "").strip()
    if inj_ui:
        site_inj = Path(inj_ui).expanduser().resolve()
        if _ignite:
            print(
                "[*] --ignite-stubby: re-injecting transfer UI on all passes (same as "
                "--inject-pass-transfer-ui + --replace-pass-transfer-ui).",
                flush=True,
            )
        inj_mail = (getattr(args, "inject_mail_api_base", "") or "").strip().rstrip("/")
        if not inj_mail:
            inj_mail = (os.environ.get("TM_VIEWER_MAIL_API_BASE") or "").strip().rstrip("/")
        if not inj_mail:
            inj_mail = (os.environ.get("TM_VIEWER_EMAIL_BACKEND_URL") or "").strip().rstrip("/")
        if inj_mail:
            mp = site_inj / "tm_viewer_mail_api_base.js"
            mp.write_text(
                "/* Written by tm_hit_viewer --inject-mail-api-base */\n"
                f"window.TM_VIEWER_MAIL_API_BASE = {json.dumps(inj_mail)};\n",
                encoding="utf-8",
                newline="\n",
            )
            print(f"[*] Wrote {mp} -> {inj_mail}", flush=True)
        inj_replace = bool(getattr(args, "replace_pass_transfer_ui", False))
        n_inj, inj_lines = inject_pass_transfer_ui_into_site_dir(
            site_inj, replace_existing=inj_replace, mail_api_base=inj_mail
        )
        for ln in inj_lines:
            print(ln, flush=True)
        print(f"[*] Injected transfer UI into {n_inj} pass file(s) under {site_inj}", flush=True)
        if not inj_mail:
            print(
                "[*] Tip: SITE_DIR must be the folder that contains tickets/ (e.g. ...\\tm-vercel-site, not ...\\public, "
                "if that is where your pass HTML lives). For https:// sites, omit --stubby-proxy-url / "
                "--inject-mail-api-base and set Vercel TM_VIEWER_EMAIL_BACKEND_URL=http://YOUR_VPS:9440 so the "
                "server calls stubby; the browser uses same-origin /api/tm-viewer/transfer-to-buyer.",
                flush=True,
            )
        raise SystemExit(0)

    if bool(args.verify_crypto):
        ok, msg = verify_safetix_crypto_against_barcode_py(here)
        print(msg)
        raise SystemExit(0 if ok else 1)
    default_txt = here / "results" / "success.txt"
    is_demo = bool(args.demo)
    tickets_merged = False

    if is_demo:
        text = EXAMPLE_HIT
    else:
        in_path = Path(args.file) if (args.file or "").strip() else default_txt
        if not in_path.is_file():
            print(f"[*] {in_path} not found — using built-in sample (same as --demo).")
            text = EXAMPLE_HIT
            is_demo = True
        else:
            text = in_path.read_text(encoding="utf-8", errors="replace")

    raw_blocks = _split_blocks(text)
    if not raw_blocks:
        raw_blocks = [text.strip()] if text.strip() else []

    if _text_looks_like_compact_tm_batch(text):
        parsed = parse_compact_tm_batch(text)
        tickets_merged = bool(sum(len(b.get("barcode_tokens") or []) for b in parsed))
        print(
            f"[*] Compact TM batch: {len(parsed)} account line(s), "
            f"{sum(len(b.get('barcode_tokens') or []) for b in parsed)} rotating token(s)"
        )
    else:
        parsed = [parse_block(b) for b in raw_blocks]

    cf_arg = (args.cookies_file or "").strip()
    if cf_arg:
        cf_path = Path(cf_arg)
        if cf_path.is_file():
            merge_cookie_file_into_blocks(parsed, cf_path)
            print(f"[*] Merged cookies from {cf_path} into {len(parsed)} block(s)")
        else:
            print(f"[!] --cookies-file not found: {cf_path}", file=sys.stderr)
    elif bool(args.fetch_barcodes) and is_demo:
        candidates = [
            here / "results" / "tm_auth_cookie_string.txt",
            here.parent / "results" / "tm_auth_cookie_string.txt",
        ]
        if _blocks_have_session_cookies(parsed):
            print(
                "[*] Demo block already has session cookies (embedded or in hit text); "
                "skipping auto-merge of tm_auth_cookie_string.txt",
                file=sys.stderr,
            )
        else:
            merged_auto = False
            for auto_ck in candidates:
                if auto_ck.is_file():
                    merge_cookie_file_into_blocks(parsed, auto_ck)
                    print(f"[*] Demo + --fetch-barcodes: merged cookies from {auto_ck}")
                    merged_auto = True
                    break
            if not merged_auto:
                print(
                    "[*] No auto cookie file found. Looked for:\n"
                    f"    - {candidates[0]}\n"
                    f"    - {candidates[1]}\n"
                    "    Create one (checker/tm_direct cookie string) or use --cookies-file PATH",
                    file=sys.stderr,
                )

    t_arg = (args.tickets or "").strip()
    ticket_maps: list[dict[str, list[dict]]] = []
    if t_arg:
        if t_arg.lower() == "auto" or Path(t_arg).is_dir():
            stub = _default_stubhub_tm_bz_dir()
            src_paths = resolve_barcode_ticket_source_paths(t_arg, stub)
            if src_paths:
                ticket_maps.append(load_tickets_maps_from_sources(src_paths))
        else:
            tpath = Path(t_arg)
            if tpath.is_file():
                ticket_maps.append(load_tickets_by_email(tpath))
            else:
                print(f"[!] --tickets file not found: {tpath}", file=sys.stderr)
    use_embedded = bool((_EMBEDDED_TICKETS_ZB64 or "").strip()) and (
        bool(args.embedded_tickets) or is_demo
    )
    if use_embedded:
        ticket_maps.append(load_embedded_tickets_map())
    if ticket_maps:
        tmap = merge_tickets_maps(*ticket_maps)
        merge_tickets_into_blocks(parsed, tmap)
        tickets_merged = True
        ntok = sum(len(b.get("barcode_tokens") or []) for b in parsed)
        src = []
        if t_arg:
            if t_arg.lower() == "auto":
                src.append("Data_for_recovery (auto)")
            elif Path(t_arg).is_dir():
                src.append(f"{Path(t_arg).name}/")
            elif Path(t_arg).is_file():
                src.append(Path(t_arg).name)
            else:
                src.append(t_arg)
        if use_embedded:
            src.append("embedded _EMBEDDED_TICKETS_ZB64")
        print(f"[*] Merged {ntok} ticket secure_token row(s) from {' + '.join(src)}")

    proxy_raw = ""
    if bool(args.fetch_barcodes):
        if args.no_proxy:
            proxy_raw = (args.proxy or "").strip() or os.environ.get("TM_HIT_VIEWER_PROXY", "").strip()
        else:
            proxy_raw = (
                (args.proxy or "").strip()
                or os.environ.get("TM_HIT_VIEWER_PROXY", "").strip()
                or _DEFAULT_FETCH_PROXY_SPEC
            )
    proxy_url = normalize_proxy_url(proxy_raw) if proxy_raw else None
    if proxy_raw and not proxy_url:
        print(
            f"[!] Invalid --proxy / TM_HIT_VIEWER_PROXY (need host:port:user:pass or http://user:pass@host:port)",
            file=sys.stderr,
        )

    fetch_banner = ""
    if bool(args.fetch_barcodes):
        if proxy_url:
            host_part = proxy_raw.split("@")[-1] if "@" in proxy_raw else proxy_raw.split(":")[0]
            print(f"[*] --fetch-barcodes using proxy -> {host_part}...", file=sys.stderr)
        total_tok = 0
        errs: list[str] = []
        for bi, block in enumerate(parsed):
            if _block_already_has_barcode_source(block):
                continue
            rows, err = fetch_tm_barcode_tokens_for_block(block, proxy_url=proxy_url)
            if rows:
                block["barcode_tokens"] = rows
                total_tok += len(rows)
                em = (parse_header_meta(block.get("header") or "").get("email") or f"block#{bi + 1}").strip()
                print(f"[*] --fetch-barcodes: {len(rows)} ticket(s) for {em}")
            elif err:
                em = (parse_header_meta(block.get("header") or "").get("email") or f"block#{bi + 1}").strip()
                errs.append(f"{em}: {err}")
                print(f"[!] --fetch-barcodes [{em}] {err}", file=sys.stderr)
        if total_tok:
            fetch_banner = (
                "<p class='demo-banner' style='border-color:rgba(46,230,166,0.45);background:rgba(46,230,166,0.1);color:#9fe8c9;'>"
                f"Pulled <code>secure_token</code> from Ticketmaster app API (<code>--fetch-barcodes</code>) — "
                f"{total_tok} ticket row(s). Tokens expire; refresh cookies / re-login when barcodes stop updating.</p>"
            )
        elif errs:
            has_sess = _blocks_have_session_cookies(parsed)
            if has_sess:
                fetch_banner = (
                    "<p class='demo-banner'>"
                    "<code>--fetch-barcodes</code> failed (often <strong>401 on <code>events.json</code></strong>). "
                    "The <strong>tm-fcap Go checker</strong> does <em>not</em> use browser cookies: it logs in as the "
                    "<strong>iOS app</strong>, exchanges the OAuth code via <code>POST …/tmx-prod/v1/accounts/exchange</code>, "
                    "and passes that <strong>accessToken</strong> in <code>access-token-host</code> — a different credential than "
                    "the web <code>id-token</code> JWT, so pasted browser exports frequently get 401. "
                    "Fix: run the Go checker and merge <code>--tickets tickets.txt</code>, or implement the same exchange flow. "
                    "Also try fresh <code>id-token</code>, <code>pip install curl_cffi</code>, and proxy/TLS.</p>"
                )
            else:
                fetch_banner = (
                    "<p class='demo-banner'>"
                    "<code>--fetch-barcodes</code> did not return tokens. "
                    "Add a logged-in TM cookie string with <code>id-token=</code> and <code>tmpt=</code>, "
                    "or save <code>tm_auth_cookie_string.txt</code> under <code>draft/results/</code> / "
                    "<code>ticketmaster/results/</code>, or use <code>--cookies-file</code>. "
                    "Optional: <code>pip install curl_cffi</code>.</p>"
                )
        if is_demo and total_tok == 0 and not any(
            _block_already_has_barcode_source(b) for b in parsed
        ):
            if _blocks_have_session_cookies(parsed):
                print(
                    "[*] Session cookies are in the hit/demo block, but TM API still failed. "
                    "401 = refresh id-token (re-export from browser) or try: pip install curl_cffi",
                    file=sys.stderr,
                )
            else:
                print(
                    "[*] Tip: no id-token+tmpt found in Cookies. Save cookie string to "
                    "ticketmaster\\results\\tm_auth_cookie_string.txt or use --cookies-file, then re-run.",
                    file=sys.stderr,
                )

    site_dir_arg = (args.site_dir or "").strip()
    site_root: Path | None = None
    if site_dir_arg:
        site_root = Path(site_dir_arg).resolve()
        site_root.mkdir(parents=True, exist_ok=True)
        html_out_for_media = site_root / "index.html"
    else:
        out = Path(args.out) if (args.out or "").strip() else (here / "results" / "tm_hit_view.html")
        out.parent.mkdir(parents=True, exist_ok=True)
        html_out_for_media = out

    em_cache_arg = (args.event_media_cache or "").strip()
    media_cache_path = Path(em_cache_arg) if em_cache_arg else _default_event_media_cache_path()
    if bool(args.resolve_event_images) or bool(args.download_event_images) or media_cache_path.is_file():
        enrich_event_media_for_blocks(
            parsed,
            html_out=html_out_for_media,
            cache_path=media_cache_path,
            resolve_discovery=bool(args.resolve_event_images),
            download_local=bool(args.download_event_images),
        )

    if site_root is not None:
        vapi = (args.viewer_api_base or "").strip() or (os.environ.get("TM_VIEWER_PUBLIC_API") or "").strip()
        vmail = (getattr(args, "viewer_mail_api_base", None) or "").strip() or (
            os.environ.get("TM_VIEWER_MAIL_API_BASE") or os.environ.get("TM_VIEWER_EMAIL_BACKEND_URL") or ""
        ).strip()
        auth_ui = bool(getattr(args, "viewer_auth_ui", True))
        vlogin = (args.viewer_login_url or "").strip() or (os.environ.get("TM_VIEWER_LOGIN_URL") or "").strip()
        one_per = bool(getattr(args, "one_html_per_seat", False))
        if one_per:
            print("[*] --one-html-per-seat: one pass file + URL per seat (no multi-seat carousel in one file).")
        files = build_html_site(
            parsed,
            title="Tickets",
            fetch_banner=fetch_banner,
            viewer_api_base=vapi or None,
            viewer_mail_api_base=vmail or None,
            viewer_auth_ui=auth_ui,
            viewer_login_url=vlogin or None,
            debug_site_root=site_root,
            one_html_per_seat=one_per,
        )
        if vapi or auth_ui:
            print(f"[*] Homepage sign-in (OTP): baked loginUrl fallback = {vlogin or _DEFAULT_TM_LOGIN_URL}")
            if vapi:
                print(
                    f"[*] tm_viewer_api_base.js → {vapi.rstrip('/')} (set TM_VIEWER_PUBLIC_API on Vercel if different)"
                )
                print(
                    f"[*] tm_viewer_link_registry.json (optional API): {vapi.rstrip('/')} — "
                    "python tm_viewer_link_registry.py --registry <that file>"
                )
            else:
                print(
                    "[*] tm_viewer_api_base.js empty - on Vercel set TM_VIEWER_BACKEND_URL (http://IP:3919) "
                    "for same-origin proxy, or TM_VIEWER_PUBLIC_API for direct HTTPS API"
                )
                print("[*] Wrote tm_viewer_link_registry.json (optional: registry API / stubby)")
            if vmail:
                print(
                    f"[*] tm_viewer_mail_api_base.js → {vmail.rstrip('/')} "
                    "(buyer transfer POST to stubby /api/tm-viewer/transfer-to-buyer)"
                )
        for rel, doc in sorted(files.items()):
            dest = site_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(doc, encoding="utf-8")
            print(f"[*] Wrote {dest}")
        n_rf, rf_msgs = refresh_pass_safetix_runtime_in_site_dir(site_root)
        for ln in rf_msgs:
            print(ln, flush=True)
        if n_rf:
            print(
                f"[*] SafeTix refresh: updated {n_rf} pass file(s) under tickets/ "
                f"(debug stripped + runtime aligned; already-fresh files unchanged)",
                flush=True,
            )
        assets_dir = site_root / "tm_event_assets"
        if assets_dir.is_dir() and any(assets_dir.iterdir()):
            print(
                f"[*] Hero images: {assets_dir} — pass HTML inlines data: URIs or HTTPS "
                f"(local files kept for tm.bz / direct hosting)."
            )
        open_path = site_root / "index.html"
        if not args.no_open:
            webbrowser.open(open_path.as_uri())
            print(f"[*] Opened {open_path.as_uri()}")
    else:
        html_doc = build_html(
            parsed,
            title="Tickets",
            is_demo=is_demo,
            tickets_merged=tickets_merged,
            fetch_banner=fetch_banner,
        )
        out.write_text(html_doc, encoding="utf-8")
        print(f"[*] Wrote {out}")

        if not args.no_open:
            uri = out.as_uri()
            webbrowser.open(uri)
            print(f"[*] Opened {uri}")


if __name__ == "__main__":
    main()
