"""
Ticketmaster sign-in & passes — email → ticket paths: JSON registry + small HTTP API.

**Primary listing (stubby Secure-Pass):** when ``tm_viewer_deliveries.jsonl`` contains at least one
ticket-capable row (or ``TM_VIEWER_DELIVERIES_PRIMARY=1``), ticket lists for ``GET /api/tm-viewer/tickets``
come **only** from that file (one JSON object per line: ``telegram_user_id``, ``email``, ``ticket_url``,
``ticket_path``, seat fields, optional ``source``: ``purchase`` / ``restore``, …). Stubby appends on each
successful delivery and restore. **Login audit:** successful OTP verify appends ``{"kind":"website_login","email","at"}``
lines (ignored for ticket tiles; do not flip deliveries-primary by themselves).

**Fallback:** ``tm_viewer_link_registry.json`` from ``tm_hit_viewer.py`` (``--site-dir``) is used only
when the deliveries file is missing or empty and ``TM_VIEWER_DELIVERIES_PRIMARY`` is not forcing
deliveries-only.

Run the API (default port **3919**; VPS bind **0.0.0.0**):

``python tm_viewer_link_registry.py --host 0.0.0.0 --port 3919``

**Standalone** (this file next to ``tm.bz`` / stub-scripts): ``tm_viewer_link_registry.json`` and
``tm_viewer_transfer_state.json`` default to the **same folder as this script** — not ``xt_data/`` and not
``tm-vercel-site/``. HTML is still inferred under ``./tm-vercel-site`` when that tree exists.
Only the copy inside ``ticketmaster/xt/`` uses ``xt_data/`` defaults when ``XT_TM_VIEWER_BUNDLE_DEFAULTS=1``.

**XT friend upload:** ``POST /xt/ingest`` (multipart ``tickets`` + ``success`` files, header ``X-XT-Ingest-Secret``)
same as ``xt_server.py`` — no separate port **9841** required if you only run this registry.
``GET /xt/health`` — JSON probe.

**Debug HTML 404 on POST** (stubby / buyer-email): set ``TM_VIEWER_REGISTRY_HTTP_DEBUG=1`` — logs
``parse_request``, ``do_POST`` path normalization, and a stack trace when ``send_error`` runs for POST.

GET /api/tm-viewer/tickets?token=<session>
→ {"ok": true, "email": "...", "tickets": [...]} — requires OTP sign-in (see below).

After a successful **transfer-to-buyer**, state is stored in ``tm_viewer_transfer_state.json`` (next to the registry).
The **seller's** public path ``/tickets/<gid>/<original-slug>`` becomes a permanent **transferred stub** (no real pass there,
even with a token). The **buyer** email uses a **new secret path** ``/tickets/<gid>/<buyer_pass_slug>?access=<token>`` that
serves the real pass from ``.tm_pass_shadow`` for the original file.
**Link gateway** (``ticketmaster/tm-link-gateway/gateway.html``, often on **tixx.cc**): by default emailed links use
``https://tixx.cc/tickets/<gid>/<slug>`` (override with ``TM_VIEWER_GATEWAY_PUBLIC_BASE``). The button sends the browser to the pass host (default ``https://tixx.pw/tickets/…`` — set meta ``tm-pass-public-origin`` on the gateway page). Disable cross-domain gateway links with ``TM_VIEWER_USE_PASS_GATEWAY=0`` (then optional same-host ``TM_VIEWER_GATEWAY_PREFIX=go`` for ``/go/tickets/…`` on the pass host).
**Re-transfer** overwrites
``tm_viewer_transfer_state.json`` for that path; prior buyer URLs remain valid via ``buyer_pass_history`` (slug+token).
Rows without ``buyer_pass_slug`` keep the legacy rule (token on the original URL) until re-transferred or migrated.
By default, after each transfer the live HTML is **moved to that shadow file** and the public ``.html`` path is overwritten
with the stub so **old naked bookmarks** and static hosts still show “transferred”. Disable with ``TM_VIEWER_TRANSFER_SHADOW_PASS=0``.
**Backfill** transfer stubs on disk: ``python tm_viewer_link_registry.py --materialize-transfer-stubs`` (optional ``--passes-dir``).
Loads merged ``tm_viewer_transfer_state.json``, registry ``transferred_to`` rows, then applies stubs. **Undo mistaken disk-wide stub:**
``python tm_viewer_link_registry.py --undo-disk-materialize-stubs`` restores HTML from ``.tm_pass_shadow/`` and removes
``disk-materialize@local`` state rows. Stub-all-with-no-metadata is **opt-in** via ``TM_MATERIALIZE_DISK_FALLBACK=1`` only.
The **xt bundle** copy may infer ``TM_VIEWER_REGISTRY_PATH`` from ``tm-vercel-site/tm_viewer_link_registry.json`` when
the bundle registry is still ``xt_data/`` and has no transfer state. Standalone layout keeps the registry next to this script.
The pass disappears from the seller's **My tickets** list. Re-transfer to another email is **allowed** by default;
set ``TM_VIEWER_TRANSFER_SINGLE_RECIPIENT_ONLY=1`` to restore legacy **409** after the first distinct buyer.
``TM_VIEWER_TRANSFER_REPEAT_SAME_BUYER=1`` sends a fresh email/link to the same buyer instead of **already_transferred**.
Env: ``TM_VIEWER_TRANSFER_MIN_GAP_SEC`` (default 1.5), ``TM_VIEWER_TRANSFER_MAX_PER_HOUR``
(default 40), ``TM_VIEWER_TRANSFER_MASK_EMAIL=1`` to mask buyer in that stub page.

POST /api/tm-viewer/transfer-to-buyer  (or /api/tm-viewer/send-mail)  JSON {"token": "…", "link_transfer_secret": "…", "to_email": "buyer@…", "path": "tickets/0/slug", …}
→ {"ok": true} — Either **OTP session** ``token`` (path must be on that email’s list) **or** ``link_transfer_secret`` from
``tm_hit_viewer`` registry row (whoever can open the pass page / has the secret may transfer; no sign-in required).
Purple “Message from …” only if ``personal_message`` is set.

POST /api/tm-viewer/auth/send-otp  JSON {"email": "..."}
→ {"ok": true} or {"ok": false, "error": "..."} — sends 6-digit code via Resend for any valid email;
``GET /tickets`` may return an empty list if that email has no passes yet.

POST /api/tm-viewer/auth/verify-otp  JSON {"email": "...", "code": "..."}
→ {"ok": true, "token": "..."} or error — exchanges code for a session token.

**Timed ticket reminders:** pass HTML built with ``tm_hit_viewer.py`` emits metas consumed by ``tm-email-gate.js``.
``POST /api/ticket-reminders/register`` on this registry supports two modes:
1) **Forward mode** (set ``TM_REMINDER_REGISTER_FORWARD_URL``) → proxy JSON to your upstream reminder API.
2) **Local file-db mode** (default when forward URL is unset) → save latest email per ticket in
   ``tm_reminder_db.json`` next to the registry (override via ``TM_REMINDER_FILE_DB``).
Optional **``TM_REMINDER_REGISTER_SECRET``** (or **``REMINDER_REGISTER_SECRET``**) is applied on forward mode.

Env:
TM_VIEWER_REGISTRY_PATH — path to the JSON file (default: next to this script)
TM_VIEWER_DELIVERIES_JSONL — optional extra JSONL path; **reads merge** this file plus registry sibling,
``…/stubhub/tm_viewer_deliveries.jsonl`` when registry is under ``…/stubhub/tm.bz/`` (stubby’s real log),
``STUBBY_BASE_DIR``, and the Windows default path unless ``TM_VIEWER_DELIVERIES_SINGLE_FILE=1``.
STUBBY_BASE_DIR / TM_VIEWER_STUBBY_BASE_DIR — folder containing ``tm_viewer_deliveries.jsonl``.
TM_VIEWER_DELIVERIES_PRIMARY — ``1``/``0``/unset; unset = auto (use deliveries if file has data)
TM_RESEND_FROM — optional mailbox only (e.g. noreply@tixx.pw or Name <addr>); must be verified in Resend.
    Display name sent to customers is always **Ticketmaster**. Default address: noreply@tixx.pw.
    **If Gmail still shows another domain (e.g. ticketmaster.vc), this variable is set on the VPS** — unset it or
    change it to noreply@tixx.pw, then restart stubby or the registry process. On start, this module prints
    ``[tm-viewer] viewer email outbound: …`` with the address actually used.
TM_RESEND_API_KEY — optional; overrides built-in key
**Mailgun (optional):** viewer OTP + buyer-transfer email **defaults to Resend** (tixx.pw). To use Mailgun, set ``TM_VIEWER_EMAIL_PROVIDER=mailgun`` (or ``smtp`` / ``stubby``), plus ``MAILGUN_API_KEY`` + ``MAILGUN_DOMAIN`` and optional ``MAILGUN_FROM`` / ``TM_MAILGUN_FROM``, or ``smtp/mailgun_sender.py`` with credentials.
**Debug:** ``TM_VIEWER_API_DEBUG=1`` logs every POST path to stdout (see why Vercel proxy path does not match).
**Stubby:** ``STUBBY_START_TM_VIEWER_API=1`` starts this HTTP API in a background thread when stubby launches (default host ``0.0.0.0``, port ``TM_VIEWER_API_PORT`` or ``3919``).
    Then point Vercel ``TM_VIEWER_BACKEND_URL`` at ``http://74.0.48.168:3919`` (no ``/api`` suffix; same host as registry).
TM_TRANSFER_EMAIL_TEMPLATE — optional explicit path to ``ticketmaster_template.html``. If unset, the registry looks for
``smtp/ticketmaster_template.html`` or ``SMTP/ticketmaster_template.html`` under (in order) ``TM_VIEWER_SMTP_DIR`` /
``STUBBY_SMTP_DIR``, the **registry JSON parent folder** (e.g. ``tm.bz/smtp/`` next to ``tm_viewer_link_registry.json``),
``cwd``, then this script’s folder — same layout as stubby’s SMTP bundle.
Having ``smtp/mailgun_sender.py`` on disk does **not** switch the viewer to Mailgun; set ``TM_VIEWER_EMAIL_PROVIDER=mailgun`` if you need Mailgun.
TM_VIEWER_SESSIONS_PATH — optional JSON file for login sessions (default: tm_viewer_sessions.json next to registry).
    **Required for stable logins:** without a writable sessions file, every API restart drops all tokens; the browser
    still had localStorage but GET /api/tm-viewer/tickets returns auth_required (looks like a random logout).
    Each successful tickets fetch **extends** the session expiry (sliding ``_SESSION_TTL_SEC`` window).

POST /api/tm-viewer/generate  JSON (large body; call backend directly if Vercel body limit hits)
Auth: same value in JSON ``secret`` or ``Authorization: Bearer …`` as env ``TM_VIEWER_GENERATE_SECRET`` or the built-in default in this file (rotate in production).
Body: ``tickets_text``, ``success_text``, ``public_base`` (e.g. https://tixx.pw), ``format``: ``json`` | ``zip``.
Optional (Vault / bot integration): ``links_append_dir``, ``persist_site_dir``, ``stubhub_stock_csv`` — override env for this run only (stock CSV must match Telegram bot ``VAULT_SECURE_PASS_STOCK_FILE``).
Runs ``tm_hit_viewer`` in a temp dir, builds stubby stock lines with viewer URLs, returns JSON or a ZIP of the site + ``_stubby_stock_lines.txt``.
Env TM_HIT_VIEWER_PY — optional path to tm_hit_viewer.py (default: ./ticketmaster/draft/tm_hit_viewer.py next to this repo).
Env TM_VIEWER_GENERATE_MAX_BYTES — max JSON body size (default 25_000_000).
Event hero images: enabled by default in ``run_generate`` (Discovery + ``tm_event_assets/``). Disable with
``TM_HIT_VIEWER_EVENT_IMAGES=0`` if needed. Discovery key and media JSON path are set in ``tm_hit_viewer.py``.
Env TM_VIEWER_DEBUG_TXT — optional path for pass-HTML debug log (default ``debug.txt`` next to ``tm_viewer_pass_debug.py``).
Env TM_VIEWER_PASSES_STATIC_DIR — directory on this host to merge each generate into (same layout as ``--site-out``).
    Typical Stubhub/Administrator layout: ``C:\\Users\\Administrator\\Desktop\\Stubhub\\stubhub\\tm.bz\\tm-vercel-site``.
    Then ``GET /tickets/<gid>/<slug>`` on this server serves ``…/tickets/<gid>/<slug>.html`` from that folder — no manual copy.
    Point ``TM_PASSES_STATIC_URL`` on Vercel to ``http://74.0.48.168:3919`` (same port as this API) so the pass proxy fetches from here.

**Auto-regenerate when checker files change (no ``--site-out``):** set ``TM_VIEWER_WATCH_DIR`` to the folder that contains
``tickets.txt`` and ``success.txt`` (or set ``TM_VIEWER_WATCH_TICKETS`` + ``TM_VIEWER_WATCH_SUCCESS``). A background thread
polls mtimes; when both files are stable for a few seconds, it runs the same pipeline as POST ``/api/tm-viewer/generate``,
merges into ``TM_VIEWER_PASSES_STATIC_DIR`` (defaults to watch dir if unset), and refreshes ``tm_viewer_link_registry.json`` there.
**Guessing** ``tickets.txt`` next to ``TM_VIEWER_PASSES_STATIC_DIR`` only runs the poll thread when ``TM_VIEWER_FILE_WATCH=1``
(avoids double-generate with stubby ``/restore`` on the same host). Optional: ``TM_VIEWER_WATCH_PUBLIC_BASE`` (default ``https://tixx.pw``), ``TM_VIEWER_WATCH_POLL_SEC`` (default ``10``),
``TM_VIEWER_WATCH_STABLE_POLLS`` (default ``2``). Console noise: ``TM_VIEWER_SIGNIN_VERBOSE=1``. Successful runs append stubby lines to ``secure_pass_stock.csv``
(``TM_STUBHUB_STOCK_CSV`` or Windows ``…\\Stubhub\\stubhub\\secure_pass_stock.csv``) and ``links.txt`` next to
the watched ``tickets.txt`` (or ``TM_VIEWER_LINKS_TXT``). Ticket blocks without checker ``Secure Token:`` are skipped.

**Missing pass file on GET:** if ``GET /tickets/gid/slug`` finds no HTML but ``tickets.txt`` + ``success.txt`` exist
(same paths as watch), the server runs a full generate once, then retries. Slugs change when SafeTix cfg hashes change;
each merge writes ``tm_viewer_pass_slug_aliases.json`` (old slug → current ``tickets/…/….html``) so old customer links keep working.
Disable with ``TM_VIEWER_REGENERATE_ON_PASS_MISS=0``. First open can take minutes; Vercel’s fetch may time out on hobby tier.
**GET** ``/tm_viewer_pass_slug_aliases.json`` serves that file from ``TM_VIEWER_PASSES_STATIC_DIR`` for the Vercel proxy.
**Wrong gid / legacy SMP:** if ``tickets/<gid>/<slug>.html`` is missing but the same ``slug`` exists under another
``tickets/<other>/`` (e.g. requested ``1`` but only ``0`` has the file), that file is served and the event is logged to ``debug.txt``.
**Stale slug (regenerate changed hash):** ``tm_viewer_pass_slug_aliases.json`` maps old slugs to new paths on each merge.
**Per-gid singleton (default off):** if ``tickets/<gid>/`` has exactly **one** ``*.html``, optional miss → serve that file.
Enable only when safe: ``TM_VIEWER_PASS_GID_SINGLETON_FALLBACK=1`` (wrong-show risk if the lone file is another event).
**Site-wide singleton** (default off): if there is exactly one ``tickets/*/*.html`` **anywhere**, any miss can serve it —
set ``TM_VIEWER_PASS_SINGLETON_FALLBACK=1`` only when appropriate (wrong-show risk). Merges **overlay** per gid.

Vercel: add ``api/tm-viewer/generate.js`` and set ``TM_VIEWER_BACKEND_URL``; POST ``/api/tm-viewer/generate`` on your domain proxies to this backend.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Layout: ``ticketmaster/xt/`` = telegram bundle (defaults under xt_data/). Any other folder = standalone
# (e.g. ``tm.bz/tm_viewer_link_registry.py``): registry JSON defaults **next to this script**, not xt_data/.
_XT_BUNDLE_DIR = Path(__file__).resolve().parent
_IN_XT_PACKAGE = _XT_BUNDLE_DIR.name.lower() == "xt"
_REPO_ROOT = _XT_BUNDLE_DIR.parent.parent if _IN_XT_PACKAGE else _XT_BUNDLE_DIR
_XT_DATA_DIR = Path(os.environ.get("XT_DATA_DIR") or str(_XT_BUNDLE_DIR / "xt_data")).expanduser()
if _IN_XT_PACKAGE:
    try:
        _XT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
for _sp in (
    str(_REPO_ROOT),
    str(_REPO_ROOT / "ticketmaster"),
    str(_REPO_ROOT / "ticketmaster" / "draft"),
    str(_XT_BUNDLE_DIR),
):
    if _sp not in sys.path:
        sys.path.insert(0, _sp)
if (
    _IN_XT_PACKAGE
    and os.environ.get("XT_TM_VIEWER_BUNDLE_DEFAULTS", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
):
    os.environ.setdefault(
        "TM_VIEWER_REGISTRY_PATH",
        str(_XT_DATA_DIR / "tm_viewer_link_registry.json"),
    )
    os.environ.setdefault("TM_VIEWER_RUN_DIR", str(_XT_BUNDLE_DIR))
    os.environ.setdefault(
        "TM_VIEWER_PASSES_STATIC_DIR",
        str(_XT_DATA_DIR / "viewer_passes_static"),
    )
    os.environ.setdefault("TM_HIT_VIEWER_PY", str(_XT_BUNDLE_DIR / "tm_hit_viewer.py"))
else:
    for _hv in (
        _XT_BUNDLE_DIR / "tm_hit_viewer.py",
        _REPO_ROOT / "ticketmaster" / "xt" / "tm_hit_viewer.py",
        _REPO_ROOT / "ticketmaster" / "draft" / "tm_hit_viewer.py",
    ):
        try:
            if _hv.is_file():
                os.environ.setdefault("TM_HIT_VIEWER_PY", str(_hv.resolve()))
                break
        except OSError:
            continue

import base64
import csv
import hashlib
import hmac
import json
import random
import re
import secrets
import socket as _py_socket
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from html import escape, unescape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _TmViewerThreadingHTTPServer(ThreadingHTTPServer):
    """
    Windows TCP quirk: without exclusive bind, one process can hold ``127.0.0.1:port`` and another
    ``0.0.0.0:port``; ``127.0.0.1`` then hits the wrong server (HTML 404 while stubby logs the new registry).

    ``SO_EXCLUSIVEADDRUSE`` + ``allow_reuse_address = False`` makes one listener own the port so
    ``0.0.0.0:3919`` and loopback reach the same process.
    """

    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self) -> None:
        if sys.platform == "win32":
            excl = getattr(_py_socket, "SO_EXCLUSIVEADDRUSE", None)
            if excl is not None:
                try:
                    self.socket.setsockopt(_py_socket.SOL_SOCKET, excl, 1)
                except OSError as ex:
                    print(
                        f"[tm-viewer-api] WARN: SO_EXCLUSIVEADDRUSE failed ({ex!r}) — "
                        "Windows may allow a second listener on the same port.",
                        flush=True,
                    )
        super().server_bind()


def _xt_merge_master_links_txt_into_env() -> None:
    """Also append stubby lines to ``<XT_DATA_DIR>/links.txt`` (next to bot stock CSV)."""
    if not _IN_XT_PACKAGE:
        return
    if os.environ.get("XT_TM_VIEWER_BUNDLE_DEFAULTS", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return
    try:
        ml = (_XT_DATA_DIR / "links.txt").resolve()
        ml_s = str(ml)
    except OSError:
        return
    cur = (os.environ.get("TM_VIEWER_LINKS_EXTRA") or "").strip()
    have: set[str] = set()
    if cur:
        for chunk in re.split(r"[;|,\n]+", cur):
            s = chunk.strip()
            if not s:
                continue
            try:
                have.add(str(Path(s).expanduser().resolve()))
            except OSError:
                have.add(s)
    if ml_s not in have:
        os.environ["TM_VIEWER_LINKS_EXTRA"] = (cur + "|" + ml_s) if cur else ml_s


_xt_merge_master_links_txt_into_env()

try:
    from tm_viewer_pass_debug import tm_viewer_debug_log
except ImportError:

    def tm_viewer_debug_log(section: str, body: str = "") -> None:
        try:
            from datetime import datetime, timezone

            p = Path.cwd() / "debug.txt"
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            with open(p, "a", encoding="utf-8") as f:
                f.write(f"\n{'=' * 72}\n[{ts}] {section}\n{'=' * 72}\n")
                f.write((body or "").rstrip() + "\n")
        except OSError:
            pass


_registry_lock = threading.Lock()
_transfer_state_lock = threading.Lock()
_transfer_rl_lock = threading.Lock()
_auth_lock = threading.Lock()
# Per-session token: min gap between transfer POSTs (seconds).
_TRANSFER_RL_TOKEN: dict[str, float] = {}
# Per seller email: timestamps of successful transfers (rolling 1h for cap).
_TRANSFER_RL_SELLER: dict[str, list[float]] = {}
_watch_start_lock = threading.Lock()
_watch_thread_started = False
_generate_pipeline_lock = threading.Lock()


def _tm_viewer_signin_verbose() -> bool:
    return (os.environ.get("TM_VIEWER_SIGNIN_VERBOSE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _tm_viewer_file_watch_poll_enabled() -> bool:
    """Background poll of tickets.txt/success.txt. Off by default — set TM_VIEWER_FILE_WATCH=1 (avoids double-generate with stubby /restore)."""
    return (os.environ.get("TM_VIEWER_FILE_WATCH") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _signin_log(msg: str) -> None:
    if _tm_viewer_signin_verbose():
        print(msg, flush=True)


def _api_trace(msg: str) -> None:
    """Every request trace when TM_VIEWER_API_DEBUG=1 (Vercel vs registry path mismatches)."""
    if (os.environ.get("TM_VIEWER_API_DEBUG") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        print(f"[tm-viewer-api] {msg}", flush=True)


def _registry_http_debug() -> bool:
    """
    Deep request / send_error tracing (stderr + stdout).

    Set ``TM_VIEWER_REGISTRY_HTTP_DEBUG=1`` when POST /api/tm-viewer/send-mail returns HTML 404
    or stubby says "wrong process on :3919": logs parse_request, do_POST routing, and stack on
    ``send_error`` for POST.
    """
    return (os.environ.get("TM_VIEWER_REGISTRY_HTTP_DEBUG") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _normalize_tm_viewer_http_path(parsed_path: str) -> str:
    """
    Canonical route paths for this handler.

    - Collapse ``/api/api/tm-viewer/...`` (bad TM_VIEWER_BACKEND_URL + proxy path).
    - Map ``/tm-viewer/...`` → ``/api/tm-viewer/...`` when a reverse proxy strips ``/api``
    (e.g. ``location /api/ { proxy_pass http://127.0.0.1:3919/; }``).
    - ``unquote``, strip, collapse ``//``, strip BOM / unicode dashes (bad proxies / paste).
    """
    path = urllib.parse.unquote((parsed_path or "/").strip() or "/")
    path = path.replace("\ufeff", "").replace("\u2013", "-").replace("\u2014", "-")
    while "//" in path:
        path = path.replace("//", "/")
    while path.startswith("/api/api/"):
        path = "/api/" + path[9:]
    path = path.rstrip("/")
    if path.startswith("/tm-viewer/"):
        path = "/api" + path
    # Case-insensitive /api/tm-viewer/... (proxies / clients sometimes alter case).
    m_api = re.match(r"^(/api/tm-viewer)(/.*)$", path, re.I)
    if m_api:
        path = m_api.group(1) + m_api.group(2).lower()
    elif re.fullmatch(r"/api/tm-viewer", path, re.I):
        path = "/api/tm-viewer"
    return path


def _post_route_match_transfer(path: str) -> bool:
    """Match buyer-email POST even if underscores / minor typos differ from canonical paths."""
    p = path.replace("_", "-").rstrip("/")
    if p in (
        "/api/tm-viewer/transfer-to-buyer",
        "/api/tm-viewer/send-mail",
    ):
        return True
    low = p.lower()
    # Trailing segment or duplicate prefix from bad proxies
    return low.endswith("/tm-viewer/send-mail") or low.endswith(
        "/tm-viewer/transfer-to-buyer"
    )


_otp_pending: dict[str, dict] = {}
_otp_last_send: dict[str, float] = {}
_sessions: dict[str, dict] = {}
_session_persist_warned: bool = False

# Resend: set TM_RESEND_API_KEY in production instead of editing source.
_RESEND_KEY_DEFAULT = "re_KDTte5XH_NNpT4of9J5xonVm1ZEvfq3Qv"

_OTP_TTL_SEC = 600
_SESSION_TTL_SEC = 86400 * 7
_OTP_RESEND_COOLDOWN_SEC = 55
_OTP_MAX_VERIFY_FAILS = 5

_DEFAULT_REGISTRY = Path(__file__).resolve().parent / "tm_viewer_link_registry.json"

# POST /api/tm-viewer/generate — client sends this in JSON "secret" or Authorization: Bearer …
# Override with env TM_VIEWER_GENERATE_SECRET in production (must match vault_generate_viewer_passes.py).
_TM_VIEWER_GENERATE_SECRET_DEFAULT = (
    "tmgen_Bk9pL2mQ7wR4xY1zA8nC5vF3hJ6tK0dS9eU2wX5yA8zB1cD4eF7hJ0kM3qT6vY9sP2nL5rH8gW1xZ4"
)


def _effective_tm_viewer_generate_secret() -> str:
    return (
        (os.environ.get("TM_VIEWER_GENERATE_SECRET") or "").strip()
        or _TM_VIEWER_GENERATE_SECRET_DEFAULT
    )


def _registry_path() -> Path:
    import os

    p = (os.environ.get("TM_VIEWER_REGISTRY_PATH") or "").strip()
    return Path(p) if p else _DEFAULT_REGISTRY


_WIN_DEFAULT_STUBBY_DELIVERIES = Path(r"C:\Users\Administrator\Desktop\Stubhub\stubhub\tm_viewer_deliveries.jsonl")


def _stubby_base_for_deliveries() -> str | None:
    for k in ("STUBBY_BASE_DIR", "TM_VIEWER_STUBBY_BASE_DIR"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    return None


def _registry_fallback_path_hunt_import_run_generate(
    script_dir_here: str,
    extra_search_roots: tuple[str, ...],
):
    """
    Same hunt as stubby ``_stubby_fallback_path_hunt_import_run_generate`` — keep in sync.
    Used when ``tm_viewer_generate_loader.py`` is not on ``PYTHONPATH``.
    """
    import sys

    roots: list[str] = []
    for env_key in ("TM_VIEWER_GENERATE_API_DIR", "STUBBY_SCRIPT_DIR"):
        v = (os.environ.get(env_key) or "").strip()
        if v:
            ap = os.path.abspath(os.path.expanduser(v))
            if ap not in roots:
                roots.append(ap)
    for x in extra_search_roots:
        s = (x or "").strip()
        if not s:
            continue
        ap = os.path.abspath(os.path.expanduser(s))
        if ap not in roots:
            roots.append(ap)
    here = os.path.abspath(os.path.expanduser((script_dir_here or "").strip()))
    if here and here not in roots:
        roots.append(here)
    tried_dirs: list[str] = []
    for d in roots:
        if not d or not os.path.isdir(d):
            continue
        modp = os.path.join(d, "tm_viewer_generate_api.py")
        if not os.path.isfile(modp):
            continue
        tried_dirs.append(d)
        if d not in sys.path:
            sys.path.insert(0, d)
        try:
            from tm_viewer_generate_api import run_generate

            return run_generate, f"from {d}"
        except ImportError:
            continue
    try:
        from tm_viewer_generate_api import run_generate

        return run_generate, "from sys.path (pre-existing)"
    except ImportError as e:
        hint = (
            "Set TM_VIEWER_GENERATE_API_DIR to the folder containing tm_viewer_generate_api.py, "
            "or place tm_viewer_generate_api.py next to tm_viewer_link_registry.py."
        )
        scanned = ", ".join(tried_dirs[:8]) if tried_dirs else "(no dir with tm_viewer_generate_api.py)"
        return None, f"{e!s}; scanned={scanned}; {hint}"


def _registry_import_run_generate():
    """Same path resolution as stubby local generate: env + this script + optional stubhub base."""
    here = str(Path(__file__).resolve().parent)
    roots: list[str] = [here]
    sb = _stubby_base_for_deliveries()
    if sb:
        bd = os.path.abspath(os.path.expanduser(sb))
        for p in (bd, os.path.dirname(bd), os.path.join(bd, "tm.bz")):
            if p not in roots:
                roots.append(p)
    extra = tuple(roots)
    try:
        from tm_viewer_generate_loader import import_run_generate as _ig

        return _ig(extra_search_roots=extra)
    except ImportError:
        return _registry_fallback_path_hunt_import_run_generate(here, extra)


def _deliveries_jsonl_write_path() -> Path:
    """File used for appends (login audit). Prefer explicit env, then stubby folder, else registry sibling."""
    p = (os.environ.get("TM_VIEWER_DELIVERIES_JSONL") or "").strip()
    if p:
        return Path(p).expanduser().resolve()
    sb = _stubby_base_for_deliveries()
    if sb:
        return Path(sb).expanduser().resolve() / "tm_viewer_deliveries.jsonl"
    return _registry_path().resolve().parent / "tm_viewer_deliveries.jsonl"


def _deliveries_jsonl_read_paths() -> list[Path]:
    """All JSONL sources merged for GET tickets (stubby logs often live beside tm.bz, not inside it)."""
    out: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        if key not in seen:
            seen.add(key)
            out.append(path)

    explicit = (os.environ.get("TM_VIEWER_DELIVERIES_JSONL") or "").strip()
    single_file = (os.environ.get("TM_VIEWER_DELIVERIES_SINGLE_FILE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if explicit:
        add(Path(explicit).expanduser().resolve())
        if single_file:
            return out

    try:
        reg_parent = _registry_path().resolve().parent
    except OSError:
        reg_parent = _registry_path().parent

    add(reg_parent / "tm_viewer_deliveries.jsonl")
    # Registry at …/stubhub/tm.bz/registry.json → stubby writes …/stubhub/tm_viewer_deliveries.jsonl
    try:
        if reg_parent.name.lower() == "tm.bz":
            parent_dl = reg_parent.parent / "tm_viewer_deliveries.jsonl"
            if parent_dl.is_file():
                add(parent_dl)
    except OSError:
        pass

    sb = _stubby_base_for_deliveries()
    if sb:
        add(Path(sb).expanduser().resolve() / "tm_viewer_deliveries.jsonl")

    if os.name == "nt":
        try:
            if _WIN_DEFAULT_STUBBY_DELIVERIES.is_file():
                add(_WIN_DEFAULT_STUBBY_DELIVERIES)
        except OSError:
            pass

    return out


def _deliveries_jsonl_path() -> Path:
    """Backward compat: same as write path."""
    return _deliveries_jsonl_write_path()


def _append_deliveries_jsonl_line(record: dict) -> None:
    """Append one JSON object (audit / delivery / login) to tm_viewer_deliveries.jsonl."""
    path = _deliveries_jsonl_write_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        _signin_log(f"[ticketmaster-signin] WARN deliveries JSONL append {path}: {e!s}")


def _sessions_path() -> Path:
    p = (os.environ.get("TM_VIEWER_SESSIONS_PATH") or "").strip()
    return Path(p) if p else (_registry_path().parent / "tm_viewer_sessions.json")


def _passes_static_root() -> Path | None:
    """Folder containing tickets/… HTML (same as sufg --site-out / TM_VIEWER_PASSES_STATIC_DIR)."""
    p = (os.environ.get("TM_VIEWER_PASSES_STATIC_DIR") or "").strip()
    if not p:
        return None
    try:
        r = Path(p).expanduser().resolve()
    except OSError:
        return None
    return r if r.is_dir() else None


def _pass_html_path_is_live(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        head = path.read_bytes()[:8192]
    except OSError:
        return False
    low = head.lower()
    return (
        b"link invalidated" not in low
        and b"have been invalidated" not in low
        and b"cancelled our parternship" not in low
    )


def _resolve_pass_html_file(root_r: Path, gid: str, slug: str) -> tuple[Path | None, str]:
    """Resolve tickets/<gid>/<slug>.html under root_r; tolerate legacy SMP / wrong gid.

    Secure-Pass checkers used ``/tickets/1/<hash>`` while ``tm_hit_viewer`` numbers accounts from 0,
    so the same slug often lives under ``tickets/0/``. If the primary path is missing, try ``gid 1 → 0``,
    then any ``tickets/*/<slug>.html`` when exactly one match exists (safe multi-account: ambiguous → no match).
    """
    alias = ""

    def _under_root(f: Path) -> Path | None:
        try:
            pr = f.resolve()
            pr.relative_to(root_r)
        except (OSError, ValueError):
            return None
        return pr if pr.is_file() and _pass_html_path_is_live(pr) else None

    primary = root_r / "tickets" / gid / f"{slug}.html"
    hit = _under_root(primary)
    if hit:
        return hit, alias

    if gid == "1":
        hit = _under_root(root_r / "tickets" / "0" / f"{slug}.html")
        if hit:
            return hit, "legacy/wrong gid: requested tickets/1/…, served tickets/0/… (same slug)"

    matches: list[Path] = []
    try:
        troot = root_r / "tickets"
        if troot.is_dir():
            for p in troot.glob(f"*/{slug}.html"):
                ok = _under_root(p)
                if ok:
                    matches.append(ok)
    except OSError:
        pass
    if len(matches) == 1:
        g = matches[0].parent.name
        return matches[0], f"gid mismatch: served tickets/{g}/{slug}.html (only copy of this slug)"

    return None, ""


_PASS_SLUG_REDIRECT_MTIME: dict[str, float] = {}
_PASS_SLUG_REDIRECT_MAP: dict[str, dict[str, str]] = {}
_RESLUG_REDIRECT_MTIME: dict[str, float] = {}
_RESLUG_REDIRECT_MAP: dict[str, dict[str, str]] = {}


def _import_reslug_map_module():
    try:
        from ticketmaster import tm_reslug_map as rsm  # type: ignore

        return rsm
    except ImportError:
        pass
    try:
        import tm_reslug_map as rsm  # type: ignore

        return rsm
    except ImportError:
        return None


def _reslug_map_search_dirs(root_r: Path) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()

    def _add(p: Path) -> None:
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)

    _add(root_r)
    _add(root_r.parent)
    reg = _registry_path()
    if reg:
        _add(reg.parent)
    links = (os.environ.get("TM_VIEWER_LINKS_TXT") or os.environ.get("TM_LINKS_FILE") or "").strip()
    if links:
        try:
            _add(Path(links.split(";")[0].split(",")[0].strip()).expanduser().resolve().parent)
        except OSError:
            pass
    return out


def _reslug_redirects_for_root(root_r: Path) -> dict[str, str]:
    rsm = _import_reslug_map_module()
    if not rsm:
        return {}
    try:
        key = str(root_r.resolve())
    except OSError:
        return {}
    map_path = rsm.find_latest_reslug_map(*_reslug_map_search_dirs(root_r))
    if not map_path:
        _RESLUG_REDIRECT_MAP.pop(key, None)
        _RESLUG_REDIRECT_MTIME.pop(key, None)
        return {}
    try:
        st = map_path.stat().st_mtime
    except OSError:
        return {}
    cache_key = f"{key}|{map_path}"
    if _RESLUG_REDIRECT_MTIME.get(cache_key) == st:
        return _RESLUG_REDIRECT_MAP.get(cache_key, {})
    out = rsm.load_reslug_redirects(*_reslug_map_search_dirs(root_r))
    _RESLUG_REDIRECT_MAP[cache_key] = out
    _RESLUG_REDIRECT_MTIME[cache_key] = st
    return out


def _pass_slug_redirects_for_root(root_r: Path) -> dict[str, str]:
    try:
        key = str(root_r.resolve())
    except OSError:
        return {}

    rsm = _import_reslug_map_module()
    map_path = rsm.find_latest_reslug_map(*_reslug_map_search_dirs(root_r)) if rsm else None
    reslug_st = 0.0
    if map_path:
        try:
            reslug_st = map_path.stat().st_mtime
        except OSError:
            map_path = None

    alias_path = root_r / "tm_viewer_pass_slug_aliases.json"
    alias_st = 0.0
    try:
        alias_st = alias_path.stat().st_mtime
    except OSError:
        pass

    cache_tag = (alias_st, str(map_path or ""), reslug_st)
    if _PASS_SLUG_REDIRECT_MTIME.get(key) == cache_tag:
        return _PASS_SLUG_REDIRECT_MAP.get(key, {})

    merged = dict(_reslug_redirects_for_root(root_r))
    if alias_path.is_file():
        try:
            raw = json.loads(alias_path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(raw, dict):
                r = raw.get("redirects")
                if isinstance(r, dict):
                    for a, b in r.items():
                        if a and b:
                            merged[str(a).strip()] = str(b).strip().replace("\\", "/")
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    _PASS_SLUG_REDIRECT_MAP[key] = merged
    _PASS_SLUG_REDIRECT_MTIME[key] = cache_tag
    return merged


def _resolve_pass_html_via_slug_redirect(root_r: Path, slug: str) -> tuple[Path | None, str]:
    red = _pass_slug_redirects_for_root(root_r)
    rel = red.get(slug) or red.get((slug or "").strip())
    if not rel:
        return None, ""
    if not rel.lower().endswith(".html"):
        rel = f"{rel}.html"
    try:
        cand = (root_r / rel).resolve()
        cand.relative_to(root_r.resolve())
    except (OSError, ValueError):
        return None, ""
    if cand.is_file() and _pass_html_path_is_live(cand):
        return cand, f"slug_redirect {slug!r} → {rel}"
    return None, ""


def _singleton_pass_fallback_enabled() -> bool:
    """Off by default so one Henry Cho pass is not served for every stale URL. Set TM_VIEWER_PASS_SINGLETON_FALLBACK=1 to enable."""
    v = (os.environ.get("TM_VIEWER_PASS_SINGLETON_FALLBACK") or "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    return False


def _find_singleton_pass_html(root_r: Path) -> Path | None:
    if not _singleton_pass_fallback_enabled():
        return None
    try:
        troot = root_r / "tickets"
        if not troot.is_dir():
            return None
        found: list[Path] = []
        for p in troot.glob("*/*.html"):
            try:
                pr = p.resolve()
                pr.relative_to(root_r)
            except (OSError, ValueError):
                continue
            if pr.is_file():
                found.append(pr)
        if len(found) == 1:
            return found[0]
    except OSError:
        pass
    return None


def _gid_folder_singleton_pass_fallback_enabled() -> bool:
    """
    When ``tickets/<gid>/`` contains exactly one ``*.html``, serve it for any ``/tickets/<gid>/<slug>`` miss
    (stale slug after regenerate; same account folder). **Off by default** — a lone unrelated pass in that folder
    would otherwise be shown for every bad slug (wrong event). Enable with ``TM_VIEWER_PASS_GID_SINGLETON_FALLBACK=1``.
    """
    v = (os.environ.get("TM_VIEWER_PASS_GID_SINGLETON_FALLBACK") or "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    return False


def _find_gid_singleton_pass_html(root_r: Path, gid: str) -> Path | None:
    """Sole ``tickets/<gid>/*.html`` on disk, or None if 0 or 2+ files."""
    if not _gid_folder_singleton_pass_fallback_enabled():
        return None
    if not gid or not gid.isdigit():
        return None
    try:
        d = (root_r / "tickets" / gid).resolve()
        d.relative_to(root_r.resolve())
    except (OSError, ValueError):
        return None
    try:
        if not d.is_dir():
            return None
        hits = [p for p in d.glob("*.html") if p.is_file()]
        if len(hits) != 1:
            return None
        return hits[0]
    except OSError:
        return None


def _bundle_default_viewer_passes_static() -> Path:
    return (_XT_DATA_DIR / "viewer_passes_static").resolve()


def _passes_dir_has_ticket_html(root: Path) -> bool:
    """True if ``root/tickets/<gid>/*.html`` exists for some numeric gid."""
    troot = root / "tickets"
    try:
        if not troot.is_dir():
            return False
        for d in troot.iterdir():
            try:
                if not d.is_dir() or not d.name.isdigit():
                    continue
                if any(d.glob("*.html")):
                    return True
            except OSError:
                continue
    except OSError:
        return False
    return False


def _maybe_infer_passes_static_dir() -> None:
    """
    Set TM_VIEWER_PASSES_STATIC_DIR to a folder that actually contains ``tickets/<gid>/*.html``.

    The XT bundle sets a default ``xt_data/viewer_passes_static`` at import; if that path is missing,
    empty, or has no ticket HTML, we **replace** it by searching registry parent, cwd, and script dir
    (including ``<base>/tm-vercel-site`` where Vercel site builds put ``tickets/``).
    """
    cur = (os.environ.get("TM_VIEWER_PASSES_STATIC_DIR") or "").strip()
    if cur:
        try:
            rp = Path(cur).expanduser().resolve()
        except OSError:
            rp = None
        if rp is not None and rp.is_dir() and _passes_dir_has_ticket_html(rp):
            return
        try:
            bundle_def = _bundle_default_viewer_passes_static()
        except OSError:
            bundle_def = None
        try:
            matches_bundle = bundle_def is not None and rp is not None and rp == bundle_def
        except OSError:
            matches_bundle = False
        # Drop useless bundle default (or missing dir) so we can infer e.g. …/tm-vercel-site
        if matches_bundle or rp is None or not rp.is_dir():
            os.environ.pop("TM_VIEWER_PASSES_STATIC_DIR", None)
        else:
            # Custom path: exists but no tickets subtree — still try to find a better root (typical mis-point)
            if not _passes_dir_has_ticket_html(rp):
                os.environ.pop("TM_VIEWER_PASSES_STATIC_DIR", None)
    candidates: list[Path] = []
    try:
        candidates.append(_registry_path().resolve().parent)
    except OSError:
        pass
    try:
        candidates.append(Path.cwd().resolve())
    except OSError:
        pass
    try:
        candidates.append(Path(__file__).resolve().parent)
    except OSError:
        pass
    seen: set[Path] = set()

    for base in candidates:
        try:
            b = base.resolve()
        except OSError:
            continue
        if b in seen:
            continue
        seen.add(b)
        for sub in (b / "tm-vercel-site", b):
            try:
                if _passes_dir_has_ticket_html(sub):
                    os.environ["TM_VIEWER_PASSES_STATIC_DIR"] = str(sub.resolve())
                    _signin_log(
                        f"[ticketmaster-signin] inferred TM_VIEWER_PASSES_STATIC_DIR={sub} (tickets/<gid>/*.html)"
                    )
                    return
            except OSError:
                continue


def _maybe_infer_registry_for_materialize_cli(*, registry_explicit_cli: bool) -> None:
    """
    Default bundle registry is ``xt_data/tm_viewer_link_registry.json`` while HTML lives under
    ``tm-vercel-site/tickets/``. Transfer state is written next to the registry the API uses; materialize
    would otherwise look at xt_data (no ``tm_viewer_transfer_state.json``). When ``--registry`` was not
    passed, the active registry is still that bundle path, passes root is elsewhere, xt_data has no
    non-empty transfer state, and ``tm_viewer_link_registry.json`` exists beside the passes root — point
    ``TM_VIEWER_REGISTRY_PATH`` at the site copy for this process only.
    """
    if registry_explicit_cli:
        return
    root = _passes_static_root()
    if not root:
        return
    try:
        bundle_reg = (_XT_DATA_DIR / "tm_viewer_link_registry.json").resolve()
    except OSError:
        return
    try:
        reg_r = _registry_path().resolve()
        root_r = root.resolve()
    except OSError:
        return
    if reg_r.parent == root_r:
        return
    if reg_r != bundle_reg:
        return
    ts_xt = reg_r.parent / "tm_viewer_transfer_state.json"
    if _transfer_state_json_nonempty_at(ts_xt):
        return
    cand = root_r / "tm_viewer_link_registry.json"
    if not cand.is_file():
        return
    os.environ["TM_VIEWER_REGISTRY_PATH"] = str(cand)
    print(
        f"[tm-viewer] inferred registry (materialize): TM_VIEWER_REGISTRY_PATH={cand}",
        flush=True,
    )


def _checker_tickets_success_paths(*, for_background_poll: bool) -> tuple[Path | None, Path | None]:
    """
    Resolve checker ``tickets.txt`` + ``success.txt``.
    When ``for_background_poll`` is True, only the passes-static parent guess runs if ``TM_VIEWER_FILE_WATCH=1``
    (otherwise stubby /restore + this API would both merge on every deploy).
    """
    wd = (os.environ.get("TM_VIEWER_WATCH_DIR") or "").strip()
    if wd:
        base = Path(wd).expanduser().resolve()
        return base / "tickets.txt", base / "success.txt"
    t = (os.environ.get("TM_VIEWER_WATCH_TICKETS") or "").strip()
    s = (os.environ.get("TM_VIEWER_WATCH_SUCCESS") or "").strip()
    if t and s:
        return Path(t).expanduser().resolve(), Path(s).expanduser().resolve()
    if for_background_poll and not _tm_viewer_file_watch_poll_enabled():
        return None, None
    pd = (os.environ.get("TM_VIEWER_PASSES_STATIC_DIR") or "").strip()
    if pd:
        base = Path(pd).expanduser().resolve()
        for folder in (base.parent, base):
            tt, su = folder / "tickets.txt", folder / "success.txt"
            if tt.is_file() and su.is_file():
                return tt, su
    return None, None


def _watch_input_paths() -> tuple[Path | None, Path | None]:
    return _checker_tickets_success_paths(for_background_poll=True)


def _apply_watch_dir_env_defaults(watch_dir: Path) -> None:
    d = watch_dir.resolve()
    reg_set = bool((os.environ.get("TM_VIEWER_REGISTRY_PATH") or "").strip())
    if not (os.environ.get("TM_VIEWER_PASSES_STATIC_DIR") or "").strip():
        if reg_set:
            rp = Path(os.environ["TM_VIEWER_REGISTRY_PATH"]).expanduser().resolve()
            os.environ["TM_VIEWER_PASSES_STATIC_DIR"] = str(rp.parent)
        else:
            os.environ["TM_VIEWER_PASSES_STATIC_DIR"] = str(d)
    if not reg_set:
        os.environ["TM_VIEWER_REGISTRY_PATH"] = str(d / "tm_viewer_link_registry.json")


def _watch_signature(tickets_p: Path, success_p: Path) -> str | None:
    try:
        if not tickets_p.is_file() or not success_p.is_file():
            return None
        ts = tickets_p.stat()
        ss = success_p.stat()
        return f"{ts.st_mtime_ns}:{ts.st_size}:{ss.st_mtime_ns}:{ss.st_size}"
    except OSError:
        return None


def _watch_run_generate() -> None:
    tpath, spath = _watch_input_paths()
    if not tpath or not spath:
        return
    try:
        tickets_text = tpath.read_text(encoding="utf-8", errors="replace")
        success_text = spath.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        _signin_log(f"[ticketmaster-watch] read error: {e}")
        return
    if not (tickets_text or "").strip() or not (success_text or "").strip():
        _signin_log(
            "[ticketmaster-watch] skip generate: tickets.txt or success.txt is empty (not calling run_generate)"
        )
        return
    pb = (
        (
            os.environ.get("TM_VIEWER_WATCH_PUBLIC_BASE")
            or os.environ.get("TM_VIEWER_AUTO_PUBLIC_BASE")
            or "https://tixx.pw"
        )
        .strip()
        .rstrip("/")
    )
    run_generate, imp_detail = _registry_import_run_generate()
    if run_generate is None:
        _signin_log(f"[ticketmaster-watch] import run_generate failed: {imp_detail}")
        return
    _signin_log("[ticketmaster-watch] tickets/success changed — generating…")
    one_seat = (os.environ.get("TM_VIEWER_ONE_HTML_PER_SEAT") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    persist_d = (os.environ.get("TM_VIEWER_PASSES_STATIC_DIR") or "").strip() or None
    ok, body, _ctype, err = run_generate(
        tickets_text=tickets_text,
        success_text=success_text,
        public_base=pb,
        output_format="json",
        persist_site_dir=persist_d,
        links_append_dir=str(tpath.parent),
        one_html_per_seat=one_seat,
    )
    if not ok:
        _signin_log(f"[ticketmaster-watch] generate failed: {(err or '')[:800]}")
        return
    try:
        meta = json.loads(body.decode("utf-8"))
        lines = meta.get("stock_lines") or []
        mv = meta.get("matched_viewer_urls")
        sk = int(meta.get("skipped_ticket_blocks_no_secure_token") or 0)
        _signin_log(
            f"[ticketmaster-watch] ok — {len(lines)} stock_lines, matched_viewer_urls={mv}, "
            f"skipped_no_secure_token_blocks={sk}"
        )
        if sk > 0:
            _signin_log(
                "[ticketmaster-watch] See [tm-generate] lines above: dropped blocks are listed. "
                "PARKWHIZ/parking drops are normal. For a missing *concert* block, add `Secure Token:` (len>=24) or split files."
            )
    except (json.JSONDecodeError, UnicodeDecodeError):
        _signin_log("[ticketmaster-watch] ok")


def _watch_loop(tickets_p: Path, success_p: Path) -> None:
    poll = float((os.environ.get("TM_VIEWER_WATCH_POLL_SEC") or "10").strip() or "10")
    need_stable = max(1, int((os.environ.get("TM_VIEWER_WATCH_STABLE_POLLS") or "2").strip() or "2"))
    last_done: str | None = None
    pending_sig: str | None = None
    pending_count = 0
    while True:
        time.sleep(max(1.0, poll))
        sig = _watch_signature(tickets_p, success_p)
        if sig is None:
            pending_sig, pending_count = None, 0
            continue
        if sig == last_done:
            continue
        if sig == pending_sig:
            pending_count += 1
        else:
            pending_sig = sig
            pending_count = 1
        if pending_count < need_stable:
            continue
        if not _generate_pipeline_lock.acquire(blocking=False):
            continue
        try:
            sig2 = _watch_signature(tickets_p, success_p)
            if sig2 != pending_sig:
                pending_count = 0
                continue
            _watch_run_generate()
            last_done = sig2
            pending_sig = None
            pending_count = 0
        finally:
            _generate_pipeline_lock.release()


def _regenerate_on_pass_miss_enabled() -> bool:
    if (os.environ.get("TM_VIEWER_REGENERATE_ON_PASS_MISS") or "").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return False
    tpath, spath = _checker_tickets_success_paths(for_background_poll=False)
    if not tpath or not spath:
        return False
    return tpath.is_file() and spath.is_file()


def _start_watch_thread_if_needed() -> None:
    global _watch_thread_started
    with _watch_start_lock:
        if _watch_thread_started:
            return
        tpath, spath = _watch_input_paths()
        if not tpath or not spath:
            return
        _watch_thread_started = True
        poll = (os.environ.get("TM_VIEWER_WATCH_POLL_SEC") or "10").strip() or "10"
        th = threading.Thread(
            target=_watch_loop,
            args=(tpath, spath),
            name="tm-viewer-file-watch",
            daemon=True,
        )
        th.start()
        _signin_log(f"[ticketmaster-watch] watching {tpath} + {spath} (poll {poll}s)")


def _persist_sessions_locked() -> None:
    """Write non-expired sessions to disk. Caller must hold _auth_lock."""
    global _session_persist_warned
    now = time.time()
    out: dict[str, dict[str, float | str]] = {}
    for tok, row in _sessions.items():
        if not isinstance(tok, str) or len(tok) > 400:
            continue
        if not isinstance(row, dict):
            continue
        exp = float(row.get("exp") or 0)
        if exp < now:
            continue
        em = row.get("email")
        if isinstance(em, str) and "@" in em:
            out[tok] = {"email": _normalize_email(em), "exp": exp}
    path = _sessions_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"version": 1, "sessions": out}, ensure_ascii=False, separators=(",", ":"))
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(payload + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError as e:
        if not _session_persist_warned:
            _session_persist_warned = True
            _signin_log(
                f"[ticketmaster-signin] WARNING: cannot persist sessions to {path} ({e!s}). "
                "Tokens are lost on process restart — fix permissions or TM_VIEWER_SESSIONS_PATH."
            )


def _load_sessions_from_disk() -> None:
    """Restore sessions after API restart so browser localStorage tokens keep working."""
    path = _sessions_path()
    if not path.is_file():
        return
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    sess = data.get("sessions")
    if not isinstance(sess, dict):
        return
    now = time.time()
    n = 0
    with _auth_lock:
        for tok, row in sess.items():
            if not isinstance(tok, str) or len(tok) > 400:
                continue
            if not isinstance(row, dict):
                continue
            exp = float(row.get("exp") or 0)
            if exp < now:
                continue
            em = row.get("email")
            if isinstance(em, str) and "@" in em:
                _sessions[tok] = {"email": _normalize_email(em), "exp": exp}
                n += 1
        _persist_sessions_locked()
    if n:
        _signin_log(f"[ticketmaster-signin] restored {n} session(s) from {path}")


def _deliveries_file_has_json_line() -> bool:
    """True when any merged JSONL has at least one ticket-capable row (not login-only audit lines)."""
    for path in _deliveries_jsonl_read_paths():
        try:
            if not path.is_file() or path.stat().st_size == 0:
                continue
            with path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(rec, dict):
                        continue
                    if _delivery_record_to_ticket(rec) is not None:
                        return True
        except OSError:
            continue
    return False


def _use_deliveries_as_primary() -> bool:
    v = (os.environ.get("TM_VIEWER_DELIVERIES_PRIMARY") or "").strip().lower()
    if v in ("0", "false", "no", "registry"):
        return False
    if v in ("1", "true", "yes", "deliveries", "only"):
        return True
    return _deliveries_file_has_json_line()


def _delivery_record_to_ticket(rec: dict) -> dict | None:
    k = (rec.get("kind") or "").strip().lower()
    # Audit / auth lines only — never promote to "My tickets" (even if ticket_path is added later).
    if k in (
        "website_login",
        "login",
        "sign_in",
        "website_transfer_to_buyer",
    ):
        return None
    path = (rec.get("ticket_path") or "").strip().strip("/")
    if not path:
        vp = viewer_relative_path_from_url((rec.get("ticket_url") or "").strip())
        path = vp or ""
    ok_path = registry_ticket_relpath_ok(path)
    if not ok_path:
        return None
    ev = (rec.get("event_name") or "Ticket").strip() or "Ticket"
    sub = ", ".join(
        x
        for x in (
            (rec.get("event_date") or "").strip(),
            (rec.get("venue") or "").strip(),
        )
        if x
    )
    return {
        "path": ok_path,
        "event_name": ev,
        "subtitle": sub,
        "section": str(rec.get("section") or ""),
        "row": str(rec.get("row") or ""),
        "seat": str(rec.get("seat") or ""),
    }


def _list_tickets_from_deliveries_jsonl(email: str) -> list[dict]:
    em = _normalize_email(email)
    # Last line per ticket_path wins across files (later paths in merge order overwrite).
    by_path: dict[str, dict] = {}
    for path in _deliveries_jsonl_read_paths():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            if _normalize_email(str(rec.get("email") or "")) != em:
                continue
            t = _delivery_record_to_ticket(rec)
            if t:
                by_path[str(t.get("path") or "")] = t
    return [
        by_path[k]
        for k in by_path
        if k and not _seller_transferred_pass_away(em, k)
    ]


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


# Static pass pages only — strict path so registry / API cannot smuggle open redirects or traversal.
_REGISTRY_TICKET_PATH_RE = re.compile(
    r"^tickets/(?P<gid>\d{1,8})/(?P<slug>[a-zA-Z0-9_.-]{1,220})\.html$",
    re.I,
)


def registry_ticket_relpath_ok(path: str) -> str | None:
    """Return normalized tickets/<gid>/<slug>.html if safe; else None.

    Accepts cleanUrls-style paths without ``.html`` and normalizes so stock/delivery
    lines and the sign-in API stay consistent with tm_hit_viewer registry entries.
    """
    p = (path or "").strip().strip("/").replace("\\", "/")
    if not p or ".." in p or "//" in p:
        return None
    if not p.lower().endswith(".html"):
        if _REGISTRY_TICKET_PATH_RE.match(p + ".html"):
            p = p + ".html"
        else:
            return None
    m = _REGISTRY_TICKET_PATH_RE.match(p)
    return m.group(0) if m else None


def _ticket_path_registry_key(path_in: str) -> str | None:
    """Stable lowercase key for transfer state (``tickets/<gid>/<slug>.html``)."""
    ok = registry_ticket_relpath_ok(path_in)
    return ok.lower() if ok else None


def _transfer_state_file_path() -> Path:
    return _registry_path().resolve().parent / "tm_viewer_transfer_state.json"


def _transfer_state_json_nonempty_at(path: Path) -> bool:
    """True if ``path`` is a JSON object with at least one key."""
    if not path.is_file():
        return False
    try:
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
        if not raw:
            return False
        data = json.loads(raw)
        return isinstance(data, dict) and len(data) > 0
    except (OSError, json.JSONDecodeError, TypeError):
        return False


def _read_transfer_state_raw_path(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _load_transfer_state_merged_for_materialize() -> tuple[dict, list[str]]:
    """Merge ``xt_data`` + registry-sibling state when they differ (e.g. API used xt_data, site registry on disk)."""
    msgs: list[str] = []
    merged: dict = {}
    try:
        reg_par = _registry_path().resolve().parent
    except OSError:
        reg_par = _registry_path().parent
    try:
        xt_par = _XT_DATA_DIR.resolve()
    except OSError:
        xt_par = _XT_DATA_DIR
    p_reg = reg_par / "tm_viewer_transfer_state.json"
    p_xt = xt_par / "tm_viewer_transfer_state.json"
    sources: list[str] = []
    try:
        same_file = p_xt.resolve() == p_reg.resolve()
    except OSError:
        same_file = str(p_xt) == str(p_reg)
    if not same_file:
        d_xt = _read_transfer_state_raw_path(p_xt)
        if d_xt:
            merged.update(d_xt)
            sources.append(str(p_xt))
    d_reg = _read_transfer_state_raw_path(p_reg)
    if d_reg:
        merged.update(d_reg)
        if str(p_reg) not in sources:
            sources.append(str(p_reg))
    psr = _passes_static_root()
    if psr:
        p_pass = psr / "tm_viewer_transfer_state.json"
        try:
            pass_res = p_pass.resolve()
            reg_res = p_reg.resolve()
            xt_res = p_xt.resolve()
        except OSError:
            pass_res, reg_res, xt_res = p_pass, p_reg, p_xt
        if pass_res != reg_res and pass_res != xt_res:
            d_pass = _read_transfer_state_raw_path(p_pass)
            if d_pass:
                merged.update(d_pass)
                if str(p_pass) not in sources:
                    sources.append(str(p_pass))
    if len(sources) > 1:
        msgs.append(
            "Merged transfer state from multiple files (later path wins on duplicate keys): "
            + "; ".join(sources)
        )
    return merged, msgs


def _registry_json_paths_for_transfer_scan() -> list[Path]:
    """Every plausible ``tm_viewer_link_registry.json`` (main, site, public, tm-vercel-site sibling). Deduped."""
    seen: set[str] = set()
    out: list[Path] = []

    def add(p: Path) -> None:
        if not p.is_file():
            return
        try:
            k = str(p.resolve())
        except OSError:
            k = str(p)
        if k in seen:
            return
        seen.add(k)
        out.append(p)

    add(_registry_path())
    try:
        reg_par = _registry_path().resolve().parent
    except OSError:
        reg_par = _registry_path().parent
    add(reg_par / "tm_viewer_link_registry.json")
    add(reg_par / "tm-vercel-site" / "tm_viewer_link_registry.json")
    add(reg_par / "tm-vercel-site" / "public" / "tm_viewer_link_registry.json")
    add(reg_par / "public" / "tm_viewer_link_registry.json")
    root = _passes_static_root()
    if root:
        add(root / "tm_viewer_link_registry.json")
        add(root / "public" / "tm_viewer_link_registry.json")
    return out


def _collect_transferred_rows_by_path_from_registries() -> dict[str, tuple[str, dict]]:
    """``tickets/.../slug.html`` (lower) -> (seller_norm, ticket_dict). Main registry wins on duplicate path."""
    by_pk: dict[str, tuple[str, dict]] = {}
    for reg_path in _registry_json_paths_for_transfer_scan():
        data = _load_registry_raw_at(reg_path)
        be = data.get("by_email")
        if not isinstance(be, dict):
            continue
        for seller_em, lst in be.items():
            if not isinstance(lst, list):
                continue
            seller_norm = _normalize_email(str(seller_em))
            if not seller_norm:
                continue
            for t in lst:
                if not isinstance(t, dict):
                    continue
                if not (str(t.get("transferred_to") or "")).strip():
                    continue
                ok = registry_ticket_relpath_ok(str(t.get("path") or ""))
                if not ok:
                    continue
                pk = (_ticket_path_registry_key(ok) or ok.lower()).lower()
                if pk in by_pk:
                    continue
                by_pk[pk] = (seller_norm, t)
    return by_pk


def _apply_registry_transferred_synthetic_tokens(data: dict) -> tuple[int, list[str]]:
    """
    When registry rows have ``transferred_to`` but transfer state has no ``buyer_access_token`` for that path,
    mint a token and persist. Scans the active registry and ``<passes-root>/tm_viewer_link_registry.json``.
    """
    from datetime import datetime, timezone

    msgs: list[str] = []
    added = 0
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = _collect_transferred_rows_by_path_from_registries()
    for pk, (seller_norm, t) in rows.items():
        cur = data.get(pk)
        if isinstance(cur, dict) and (str(cur.get("buyer_access_token") or "")).strip():
            continue
        buyer = (str(t.get("transferred_to") or "")).strip()
        parts = _parse_registry_ticket_key_parts(str(pk))
        gid_syn = parts[0] if parts else "0"
        try:
            psr = _passes_static_root()
            root_syn = psr.resolve() if psr else None
        except OSError:
            root_syn = None
        bslug_syn = _new_buyer_pass_slug(root_syn, gid_syn)
        tok_syn = secrets.token_urlsafe(32)
        url_syn = ""
        try:
            pub = _public_site_base_for_pass_urls()
            rel = f"tickets/{gid_syn}/{bslug_syn}.html"
            cand = _append_access_query_to_url(
                _viewer_pass_public_url(pub, rel), tok_syn
            )
            if cand.startswith("http://") or cand.startswith("https://"):
                url_syn = cand
        except Exception:
            pass
        row_syn: dict = {
            "transferred_to": _normalize_email(buyer),
            "transferred_at": (str(t.get("transferred_at") or "")).strip() or now_iso,
            "from_seller": seller_norm,
            "buyer_access_token": tok_syn,
            "buyer_pass_slug": bslug_syn,
        }
        if url_syn:
            row_syn["buyer_pass_url"] = url_syn
        data[pk] = row_syn
        added += 1
    if added:
        extra = ""
        paths = _registry_json_paths_for_transfer_scan()
        if len(paths) > 1:
            extra = f" (scanned {len(paths)} registry JSON path(s): main + site copy under passes root)."
        msgs.append(
            f"Synthesized {added} transfer state row(s) from registry ticket rows with transferred_to{extra} "
            f"Wrote {_transfer_state_file_path()}. "
            "Buyer links emailed before this run need the new path + ?access= — re-send transfer if needed."
        )
        with _transfer_state_lock:
            _save_transfer_state(data)
    return added, msgs


def _load_transfer_state() -> dict:
    path = _transfer_state_file_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_transfer_state(data: dict) -> None:
    path = _transfer_state_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def transfer_state_for_path(path_in: str) -> dict | None:
    """If this pass was transferred, return transfer row (includes ``buyer_access_token``, optional ``buyer_pass_slug``)."""
    key = _ticket_path_registry_key(path_in)
    if not key:
        return None
    with _transfer_state_lock:
        st = _load_transfer_state().get(key)
    return st if isinstance(st, dict) else None


def _transfer_state_effective_row_for_buyer_slug(row: dict, slug: str) -> dict | None:
    """State slice for a minted buyer slug: current row or an entry in ``buyer_pass_history`` (re-transfer)."""
    s = (slug or "").strip()
    if not s:
        return None
    if (str(row.get("buyer_pass_slug") or "")).strip() == s:
        return dict(row)
    hist = row.get("buyer_pass_history")
    if not isinstance(hist, list):
        return None
    for h in hist:
        if not isinstance(h, dict):
            continue
        hs = (str(h.get("buyer_pass_slug") or "")).strip()
        if hs != s:
            continue
        out = dict(row)
        out["buyer_access_token"] = str(h.get("buyer_access_token") or "").strip()
        out["transferred_to"] = str(h.get("transferred_to") or "").strip()
        out["buyer_pass_slug"] = hs
        return out
    return None


def transfer_state_for_buyer_pass_slug(gid: str, slug: str) -> tuple[str, dict] | None:
    """
    Lookup by **buyer-only** URL segment after transfer.

    Returns ``(canonical_registry_path_key, state_dict)`` e.g. ``("tickets/582/original.html", {...})``,
    or ``None`` if ``slug`` is not a minted ``buyer_pass_slug``.

    After a **re-transfer**, older buyer links stay valid: prior ``buyer_pass_slug`` + token pairs are kept in
    ``buyer_pass_history`` on the same path key.

    First matches rows where the URL ``gid`` equals the original ticket folder (``tickets/<gid>/…``).
    If none, matches **any** row with that slug so proxies that rewrite ``gid`` (e.g. to ``0``) still resolve.
    """
    g = (gid or "").strip()
    s = (slug or "").strip()
    if not g.isdigit() or not s or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,220}", s):
        return None
    with _transfer_state_lock:
        data = _load_transfer_state()

    picked: tuple[str, dict] | None = None
    for pk, row in data.items():
        if not isinstance(row, dict):
            continue
        eff = _transfer_state_effective_row_for_buyer_slug(row, s)
        if eff is None:
            continue
        parts = _parse_registry_ticket_key_parts(str(pk))
        if not parts or parts[0] != g:
            continue
        return (str(pk).lower(), eff)
    for pk, row in data.items():
        if not isinstance(row, dict):
            continue
        eff = _transfer_state_effective_row_for_buyer_slug(row, s)
        if eff is None:
            continue
        parts = _parse_registry_ticket_key_parts(str(pk))
        if not parts:
            continue
        picked = (str(pk).lower(), eff)
        break
    return picked


def _new_buyer_pass_slug(root_r: Path | None, gid: str) -> str:
    """Random URL segment; avoid colliding with an existing ``tickets/<gid>/*.html`` filename."""
    g = (gid or "0").strip()
    if not g.isdigit():
        g = "0"
    for _ in range(64):
        raw = secrets.token_urlsafe(16)
        s = raw.replace(".", "_").replace("/", "_").strip("_")
        if len(s) < 12:
            continue
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{12,220}", s):
            continue
        if root_r is None:
            return s
        try:
            cand = (root_r / "tickets" / g / f"{s}.html").resolve()
            cand.relative_to(root_r.resolve())
        except (OSError, ValueError):
            continue
        if not cand.is_file():
            return s
    return secrets.token_urlsafe(24).replace(".", "_").replace("/", "_")[:48]


_TRANSFER_BUYER_HISTORY_MAX = 500


def _transfer_state_set(
    path_key: str,
    *,
    seller: str,
    buyer: str,
    buyer_access_token: str | None = None,
    buyer_pass_slug: str | None = None,
    buyer_pass_url: str | None = None,
) -> str:
    """Persist transfer row. If ``buyer_access_token`` is omitted, a new token is generated.

    On re-transfer with a **new** ``buyer_pass_slug``, the previous slug+token+buyer are appended to
    ``buyer_pass_history`` so older emailed links keep serving the pass (or stub without token).

    ``buyer_pass_url`` is the full emailed link (includes ``?access=``); stored for audit and tooling.
    """
    from datetime import datetime, timezone

    tok = ((buyer_access_token or "").strip() or secrets.token_urlsafe(32))
    bps = (buyer_pass_slug or "").strip()
    bpu = (buyer_pass_url or "").strip()
    rec = {
        "transferred_to": _normalize_email(buyer),
        "transferred_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "from_seller": _normalize_email(seller),
        "buyer_access_token": tok,
    }
    if bps:
        rec["buyer_pass_slug"] = bps
    if bpu:
        rec["buyer_pass_url"] = bpu
    with _transfer_state_lock:
        data = _load_transfer_state()
        prev = data.get(path_key)
        prev_d = dict(prev) if isinstance(prev, dict) else {}
        hist = prev_d.get("buyer_pass_history")
        hist = list(hist) if isinstance(hist, list) else []
        oslug = (str(prev_d.get("buyer_pass_slug") or "")).strip()
        otok = (str(prev_d.get("buyer_access_token") or "")).strip()
        obuy = (str(prev_d.get("transferred_to") or "")).strip()
        ou = (str(prev_d.get("buyer_pass_url") or "")).strip()
        if oslug and otok and bps and oslug != bps:
            he: dict = {
                "buyer_pass_slug": oslug,
                "buyer_access_token": otok,
                "transferred_to": _normalize_email(obuy) if obuy else "",
            }
            if ou:
                he["buyer_pass_url"] = ou
            hist.append(he)
        if len(hist) > _TRANSFER_BUYER_HISTORY_MAX:
            hist = hist[-_TRANSFER_BUYER_HISTORY_MAX :]
        merged = {**prev_d, **rec, "buyer_pass_history": hist}
        data[path_key] = merged
        _save_transfer_state(data)
    return tok


def _append_access_query_to_url(url: str, access_token: str) -> str:
    t = (access_token or "").strip()
    if not t:
        return url
    q = urllib.parse.urlencode({"access": t})
    return f"{url}{'&' if '?' in url else '?'}{q}"


_TRANSFER_STUB_FILE_MARKER = b"This ticket was transferred"

# Synthetic rows written by ``_materialize_stub_all_pass_html_from_disk`` (must not hide real transfers).
_DISK_FALLBACK_TRANSFER_FROM_SELLER = "disk-materialize@local"


def _transfer_shadow_disk_enabled() -> bool:
    """When true (default), completed transfers move live HTML to ``tickets/<gid>/.tm_pass_shadow/`` and write stub HTML on the public path so naked URLs match the transferred state even when files are served without this API."""
    v = (os.environ.get("TM_VIEWER_TRANSFER_SHADOW_PASS") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _transfer_single_recipient_enforced() -> bool:
    """Legacy: after first transfer to buyer A, block transfer to buyer B with HTTP 409."""
    v = (os.environ.get("TM_VIEWER_TRANSFER_SINGLE_RECIPIENT_ONLY") or "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def _transfer_repeat_same_buyer_allowed() -> bool:
    """When true, transfer POST to the same buyer as the last transfer sends a new link instead of already_transferred."""
    v = (os.environ.get("TM_VIEWER_TRANSFER_REPEAT_SAME_BUYER") or "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def _parse_registry_ticket_key_parts(registry_key_lower: str) -> tuple[str, str] | None:
    m = re.match(
        r"^tickets/(\d{1,8})/([a-zA-Z0-9_.-]+)\.html$",
        (registry_key_lower or "").strip(),
        re.I,
    )
    if not m:
        return None
    return m.group(1), m.group(2)


def _transfer_lookup_slug_only(segment: str) -> str:
    x = (segment or "").strip()
    if x.lower().endswith(".html"):
        x = x[:-5]
    return x.strip()


def _transfer_lookup_normalize_slug_arg(raw: str) -> str:
    """Bare slug or full ticket URL → normalized slug for DB lookup."""
    s = (raw or "").strip().strip('"').strip("'")
    if not s:
        return ""
    if "://" in s or s.startswith("//"):
        if s.startswith("//"):
            s = "https:" + s
        u = urllib.parse.urlparse(s)
        path = (u.path or "").strip("/").replace("\\", "/")
        m = re.search(
            r"(?:^|/)tickets/\d{1,8}/([a-zA-Z0-9_.-]+)(?:\.html)?/?$",
            path,
            re.I,
        )
        if m:
            return _transfer_lookup_slug_only(m.group(1))
        segs = [p for p in path.split("/") if p]
        if segs:
            return _transfer_lookup_slug_only(segs[-1])
    return _transfer_lookup_slug_only(s)


def _transfer_lookup_collect(slug: str) -> dict:
    """Scan transfer state + deliveries for slug (original path, buyer slug, or history)."""
    slug = _transfer_lookup_slug_only(slug)
    if not slug:
        return {"ok": False, "error": "empty_slug"}
    pub = _public_site_base_for_pass_urls()
    matches: list[dict] = []
    with _transfer_state_lock:
        data = dict(_load_transfer_state())
    for canon_key, row in data.items():
        if not isinstance(row, dict):
            continue
        ck = str(canon_key or "").replace("\\", "/")
        if not ck:
            continue
        pr = _parse_registry_ticket_key_parts(ck.lower())
        orig_slug = pr[1] if pr else ""
        cur_buy = (str(row.get("buyer_pass_slug") or "")).strip()
        cur_buy_n = _transfer_lookup_slug_only(cur_buy)
        match = orig_slug == slug or cur_buy_n == slug
        hist = row.get("buyer_pass_history")
        if isinstance(hist, list):
            for h in hist:
                if isinstance(h, dict):
                    hs = _transfer_lookup_slug_only(str(h.get("buyer_pass_slug") or ""))
                    if hs == slug:
                        match = True
                        break
        if not match:
            continue
        gid_key = pr[0] if pr else "0"
        if not str(gid_key).isdigit():
            m2 = re.match(r"^tickets/(\d{1,8})/", ck, re.I)
            gid_key = m2.group(1) if m2 else "0"
        tok = (str(row.get("buyer_access_token") or "")).strip()
        bpu = (str(row.get("buyer_pass_url") or "")).strip()
        to_em = (str(row.get("transferred_to") or "")).strip()
        ent: dict = {
            "canonical_key": ck,
            "transferred_to": to_em,
            "transferred_at": row.get("transferred_at"),
            "current": None,
            "history": [],
        }
        if cur_buy_n and tok:
            url = (
                bpu
                if bpu.startswith("http://") or bpu.startswith("https://")
                else _append_access_query_to_url(
                    _viewer_pass_public_url(pub, f"tickets/{gid_key}/{cur_buy_n}.html"),
                    tok,
                )
            )
            ent["current"] = {"pass_url": url, "buyer_pass_slug": cur_buy_n}
        elif to_em:
            ent["note"] = "missing_buyer_slug_or_token_legacy"
        if isinstance(hist, list):
            for h in hist:
                if not isinstance(h, dict):
                    continue
                hs = _transfer_lookup_slug_only(str(h.get("buyer_pass_slug") or ""))
                htok = (str(h.get("buyer_access_token") or "")).strip()
                hu = (str(h.get("buyer_pass_url") or "")).strip()
                hto = (str(h.get("transferred_to") or "")).strip()
                if not hs or not htok:
                    continue
                urlh = (
                    hu
                    if hu.startswith("http://") or hu.startswith("https://")
                    else _append_access_query_to_url(
                        _viewer_pass_public_url(pub, f"tickets/{gid_key}/{hs}.html"),
                        htok,
                    )
                )
                ent["history"].append(
                    {
                        "pass_url": urlh,
                        "transferred_to": hto,
                        "buyer_pass_slug": hs,
                    }
                )
        matches.append(ent)

    deliveries: list[dict] = []
    for jpath in _deliveries_jsonl_read_paths():
        try:
            with open(jpath, encoding="utf-8", errors="replace") as jf:
                for line in jf:
                    line = line.strip()
                    if not line or slug not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("kind") != "website_transfer_to_buyer":
                        continue
                    bps = _transfer_lookup_slug_only(str(rec.get("buyer_pass_slug") or ""))
                    purl = (str(rec.get("pass_url") or "")).strip()
                    opath = (str(rec.get("path") or "")).strip()
                    op_slug = ""
                    opr = registry_ticket_relpath_ok(opath.replace("\\", "/"))
                    if opr:
                        pr2 = _parse_registry_ticket_key_parts(opr.lower())
                        if pr2:
                            op_slug = pr2[1]
                    path_match = slug in opath.replace("\\", "/") or op_slug == slug
                    if bps != slug and slug not in purl and not path_match:
                        continue
                    deliveries.append(
                        {
                            "pass_url": purl,
                            "at": rec.get("at"),
                            "buyer_email": rec.get("buyer_email"),
                            "path": opath,
                        }
                    )
        except OSError:
            continue

    return {
        "ok": True,
        "slug": slug,
        "public_base": pub,
        "matches": matches,
        "deliveries": deliveries,
    }


def transfer_state_and_key_for_pass_url(
    gid: str, slug: str,
) -> tuple[dict | None, str | None]:
    """Resolve transfer state for ``GET /tickets/{gid}/{slug}``.

    Tries the exact key ``tickets/{gid}/{slug}.html`` first. If that misses and ``gid``
    is ``0`` (common for Vercel / clean URLs while state keys use the real event folder),
    falls back to any state row with the same filename slug and non-empty
    ``transferred_to``.

    Returns ``(state_dict, canonical_key)`` for shadow paths; ``(None, None)`` if not
    transferred under this URL.
    """
    g = (gid or "").strip()
    s = (slug or "").strip()
    if not g.isdigit() or not s:
        return None, None
    rel_check = f"tickets/{g}/{s}.html"
    key = _ticket_path_registry_key(rel_check)
    with _transfer_state_lock:
        data = _load_transfer_state()
    if key:
        row = data.get(key)
        if isinstance(row, dict) and (str(row.get("transferred_to") or "")).strip():
            return row, key
    if g != "0":
        return None, None
    s_req = s.lower()
    candidates: list[tuple[str, dict]] = []
    for pk, row in data.items():
        if not isinstance(row, dict):
            continue
        if not (str(row.get("transferred_to") or "")).strip():
            continue
        parts = _parse_registry_ticket_key_parts(str(pk))
        if not parts:
            continue
        _gg, sl = parts
        if sl.lower() != s_req:
            continue
        candidates.append((str(pk).lower(), row))
    if not candidates:
        return None, None
    if len(candidates) == 1:
        pk0, r0 = candidates[0]
        return dict(r0), pk0
    candidates.sort(
        key=lambda it: (
            str(it[1].get("transferred_at") or ""),
            str(it[0]),
        ),
        reverse=True,
    )
    pk0, r0 = candidates[0]
    return dict(r0), pk0


def _shadow_html_path_for_key(root_r: Path, registry_key_lower: str) -> Path | None:
    parts = _parse_registry_ticket_key_parts(registry_key_lower)
    if not parts:
        return None
    g, sl = parts
    try:
        p = (root_r / "tickets" / g / ".tm_pass_shadow" / f"{sl}.html").resolve()
        p.relative_to(root_r)
        return p
    except (OSError, ValueError):
        return None


def _primary_html_path_for_key(root_r: Path, registry_key_lower: str) -> Path | None:
    parts = _parse_registry_ticket_key_parts(registry_key_lower)
    if not parts:
        return None
    g, sl = parts
    try:
        p = (root_r / "tickets" / g / f"{sl}.html").resolve()
        p.relative_to(root_r)
        return p
    except (OSError, ValueError):
        return None


def _transfer_materialize_stub_on_disk(*, registry_relpath: str, buyer_email: str) -> tuple[bool, str]:
    """Move live pass HTML to ``.tm_pass_shadow/`` and write stub at the original path. Returns (ok, reason)."""
    if not _transfer_shadow_disk_enabled():
        return False, "TM_VIEWER_TRANSFER_SHADOW_PASS is off"
    root = _passes_static_root()
    if not root:
        return False, "no passes static root"
    ok = registry_ticket_relpath_ok(registry_relpath)
    if not ok:
        return False, "invalid registry path"
    pk = (_ticket_path_registry_key(ok) or ok.lower()).lower()
    root_r = root.resolve()
    primary = _primary_html_path_for_key(root_r, pk)
    shadow = _shadow_html_path_for_key(root_r, pk)
    if primary is None or shadow is None:
        return False, "path outside passes root"
    buyer_disp = _mask_email_for_display(buyer_email)
    stub = _html_transfer_stub_page(buyer_display=buyer_disp)
    mark = _TRANSFER_STUB_FILE_MARKER
    try:
        shadow.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return False, f"mkdir shadow: {e}"
    try:
        if primary.is_file():
            head = primary.read_bytes()[:2000]
            if mark in head:
                if shadow.is_file():
                    try:
                        tmp = primary.with_suffix(primary.suffix + ".tmp")
                        tmp.write_bytes(stub)
                        tmp.replace(primary)
                    except OSError as e:
                        return False, str(e)
                    return True, ""
                return False, "pass file is already stub but .tm_pass_shadow copy missing"
            if not shadow.is_file():
                primary.rename(shadow)
            else:
                primary.unlink()
        elif not shadow.is_file():
            return False, f"missing {primary.as_posix()} (and no shadow to restore from)"
        tmp = primary.with_suffix(primary.suffix + ".tmp")
        tmp.write_bytes(stub)
        tmp.replace(primary)
        return True, ""
    except OSError as e:
        return False, str(e)


def _restore_pass_primary_from_shadow(*, registry_relpath: str) -> tuple[bool, str]:
    """Replace a transfer-stub primary with the backup in ``.tm_pass_shadow/`` (undo mistaken materialize)."""
    root = _passes_static_root()
    if not root:
        return False, "no passes static root"
    ok = registry_ticket_relpath_ok(registry_relpath)
    if not ok:
        return False, "invalid registry path"
    pk = (_ticket_path_registry_key(ok) or ok.lower()).lower()
    root_r = root.resolve()
    primary = _primary_html_path_for_key(root_r, pk)
    shadow = _shadow_html_path_for_key(root_r, pk)
    if primary is None or shadow is None:
        return False, "path outside passes root"
    mark = _TRANSFER_STUB_FILE_MARKER
    try:
        if not shadow.is_file():
            return False, "no .tm_pass_shadow backup"
        if primary.is_file():
            head = primary.read_bytes()[: max(len(mark) + 200, 2600)]
            if mark not in head:
                return False, "primary is not a transfer stub (refusing to overwrite)"
        data = shadow.read_bytes()
        tmp = primary.with_suffix(primary.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(primary)
        try:
            shadow.unlink()
        except OSError:
            pass
        return True, ""
    except OSError as e:
        return False, str(e)


def _iter_stub_primary_paths_with_shadow(root: Path) -> list[str]:
    """Paths ``tickets/<gid>/<slug>.html`` (lower) where primary is stub and shadow backup exists."""
    tdir = root / "tickets"
    if not tdir.is_dir():
        return []
    out: list[str] = []
    mark = _TRANSFER_STUB_FILE_MARKER
    for gid_dir in sorted(tdir.iterdir(), key=lambda p: p.name):
        if not gid_dir.is_dir() or gid_dir.name.startswith("."):
            continue
        if not gid_dir.name.isdigit():
            continue
        for html in sorted(gid_dir.glob("*.html")):
            try:
                head = html.read_bytes()[: max(len(mark) + 200, 2600)]
            except OSError:
                continue
            if mark not in head:
                continue
            sh = gid_dir / ".tm_pass_shadow" / html.name
            if sh.is_file():
                out.append(f"tickets/{gid_dir.name}/{html.stem}.html".lower())
    return out


def undo_disk_fallback_materialize_on_disk() -> tuple[int, list[str]]:
    """Remove disk-fallback transfer state and restore real HTML from ``.tm_pass_shadow/``."""
    msgs: list[str] = []
    root = _passes_static_root()
    if not root:
        msgs.append("No passes static root — set TM_VIEWER_PASSES_STATIC_DIR or --passes-dir.")
        return 0, msgs
    marker = _normalize_email(_DISK_FALLBACK_TRANSFER_FROM_SELLER)
    n = 0
    with _transfer_state_lock:
        st = dict(_load_transfer_state())
        keys = [
            k
            for k, v in st.items()
            if isinstance(v, dict) and _normalize_email(str(v.get("from_seller") or "")) == marker
        ]
        for pk in keys:
            okp = registry_ticket_relpath_ok(str(pk))
            if not okp:
                msgs.append(f"{pk!r}: invalid key — removed state row only")
                st.pop(pk, None)
                continue
            did, reason = _restore_pass_primary_from_shadow(registry_relpath=okp)
            if did:
                n += 1
                st.pop(pk, None)
            else:
                msgs.append(f"{pk!r}: could not restore ({reason}); left state row so you can retry")
        for pk in _iter_stub_primary_paths_with_shadow(root.resolve()):
            rec = st.get(pk)
            if isinstance(rec, dict):
                fs = _normalize_email(str(rec.get("from_seller") or ""))
                if fs and fs != marker:
                    continue
            okp = registry_ticket_relpath_ok(str(pk))
            if not okp:
                continue
            did, reason = _restore_pass_primary_from_shadow(registry_relpath=okp)
            if did:
                n += 1
                st.pop(pk, None)
            elif reason and pk not in keys:
                msgs.append(f"{pk!r}: orphan stub — {reason}")
        _save_transfer_state(st)
    msgs.insert(
        0,
        f"[tm-viewer] undo disk materialize: restored {n} pass HTML file(s); "
        f"cleaned tm_viewer_transfer_state.json rows from {_DISK_FALLBACK_TRANSFER_FROM_SELLER}.",
    )
    return n, msgs


def _materialize_stub_buyer_display() -> str:
    raw = (os.environ.get("TM_MATERIALIZE_STUB_BUYER") or "recipient@example.com").strip()
    return raw if raw else "recipient@example.com"


def _materialize_stub_all_pass_html_from_disk() -> tuple[int, list[str]]:
    """If there is no transfer state/registry metadata, stub every live ``tickets/<gid>/*.html`` under passes root."""
    from datetime import datetime, timezone

    msgs: list[str] = []
    root = _passes_static_root()
    if not root:
        return 0, msgs
    tdir = root / "tickets"
    if not tdir.is_dir():
        msgs.append("Disk fallback: no tickets/ directory under passes root.")
        return 0, msgs
    buyer_disp = _materialize_stub_buyer_display()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pks: list[str] = []
    for gid_dir in sorted(tdir.iterdir(), key=lambda p: p.name):
        if not gid_dir.is_dir() or gid_dir.name.startswith("."):
            continue
        if not gid_dir.name.isdigit():
            continue
        for html in sorted(gid_dir.glob("*.html")):
            try:
                head = html.read_bytes()[: max(len(_TRANSFER_STUB_FILE_MARKER) + 200, 2600)]
            except OSError as e:
                msgs.append(f"disk fallback: skip read {html.as_posix()}: {e}")
                continue
            if _TRANSFER_STUB_FILE_MARKER in head:
                continue
            pks.append(f"tickets/{gid_dir.name}/{html.stem}.html".lower())
    if not pks:
        msgs.append(
            "Disk fallback: no non-stub .html under tickets/<gid>/ (nothing to write, or passes are already stubs)."
        )
        return 0, msgs
    fake_seller = _DISK_FALLBACK_TRANSFER_FROM_SELLER
    with _transfer_state_lock:
        st_data = dict(_load_transfer_state())
        for pk in pks:
            if isinstance(st_data.get(pk), dict) and (str(st_data[pk].get("buyer_access_token") or "")).strip():
                continue
            st_data[pk] = {
                "transferred_to": _normalize_email(buyer_disp) if "@" in buyer_disp else buyer_disp,
                "transferred_at": now_iso,
                "from_seller": _normalize_email(fake_seller) or fake_seller,
                "buyer_access_token": secrets.token_urlsafe(32),
            }
        _save_transfer_state(st_data)
    msgs.append(
        f"Disk fallback: no transfer metadata — stubbing {len(pks)} pass file(s). "
        f"Stub buyer line: {buyer_disp!r} (TM_MATERIALIZE_STUB_BUYER). "
        "Undo: python tm_viewer_link_registry.py --undo-disk-materialize-stubs"
    )
    nok = 0
    for pk in pks:
        did, reason = _transfer_materialize_stub_on_disk(
            registry_relpath=pk,
            buyer_email=buyer_disp,
        )
        if did:
            nok += 1
        elif reason:
            msgs.append(f"{pk!r}: {reason}")
    return nok, msgs


def materialize_all_transfer_stubs_on_disk() -> tuple[int, list[str]]:
    """One-shot: apply disk stub + shadow for every transferred pass that has ``buyer_access_token``.

    Loads transfer state from ``tm_viewer_transfer_state.json`` next to the active registry, merges in
    ``xt_data/tm_viewer_transfer_state.json`` when that is a different file, then fills gaps from registry
    rows that have ``transferred_to`` (synthetic ``buyer_access_token`` if the state file was never written).
    Optional disk fallback stubs **all** passes when metadata is empty — **off by default**; set
    ``TM_MATERIALIZE_DISK_FALLBACK=1`` to enable (avoid unless you mean to replace every pass with a stub).
    """
    msgs: list[str] = []
    root = _passes_static_root()
    if not root:
        raw = (os.environ.get("TM_VIEWER_PASSES_STATIC_DIR") or "").strip()
        hint = (
            "no usable TM_VIEWER_PASSES_STATIC_DIR — cannot materialize stubs. Fix one of:\n"
            "  • Run from the folder that **contains** tickets/ (inference checks cwd, registry parent, script dir, and **tm-vercel-site**), or\n"
            "  • Pass --passes-dir \"C:\\\\...\\\\tm-vercel-site\" — the folder that **contains** tickets/ (not tickets itself), or\n"
            "  • Set TM_VIEWER_PASSES_STATIC_DIR to that same parent (not inside tickets/)."
        )
        if raw:
            hint += f"\n  (Env currently points to {raw!r} but that path is not a directory with tickets/<gid>/*.html.)"
        msgs.append(hint)
        return 0, msgs
    if not _transfer_shadow_disk_enabled():
        msgs.append("TM_VIEWER_TRANSFER_SHADOW_PASS is off")
        return 0, msgs
    reg_path = _registry_path()
    data, merge_msgs = _load_transfer_state_merged_for_materialize()
    _, syn_msgs = _apply_registry_transferred_synthetic_tokens(data)
    ts_path = _transfer_state_file_path()
    msgs.append(f"Registry JSON: {reg_path}")
    msgs.append(f"Transfer state:  {ts_path} (exists={ts_path.is_file()})")
    msgs.append(f"Passes root:     {root.resolve()}")
    msgs.append(
        "Note: Uses registry + transfer JSON only unless TM_MATERIALIZE_DISK_FALLBACK=1 (stub-all fallback)."
    )
    msgs.extend(merge_msgs)
    msgs.extend(syn_msgs)
    n = 0
    n_rows = len(data)
    eligible = 0
    if n_rows == 0:
        _dfb = (os.environ.get("TM_MATERIALIZE_DISK_FALLBACK") or "0").strip().lower()
        fb_on = _dfb in ("1", "true", "yes", "on")
        if fb_on:
            n_fb, fb_msgs = _materialize_stub_all_pass_html_from_disk()
            msgs.extend(fb_msgs)
            n += n_fb
        if n == 0:
            msgs.append(
                "No transfer metadata to apply. Disk stub-all is off by default — set TM_MATERIALIZE_DISK_FALLBACK=1 "
                "only if you intentionally want every pass replaced with a transferred stub."
            )
        return n, msgs
    for key, st in data.items():
        if not isinstance(st, dict):
            continue
        if not (str(st.get("transferred_to") or "")).strip():
            continue
        if not (str(st.get("buyer_access_token") or "")).strip():
            msgs.append(
                f"skip {key!r}: no buyer_access_token (nothing to move; re-send transfer to issue a token)"
            )
            continue
        ok = registry_ticket_relpath_ok(str(key))
        if not ok:
            msgs.append(f"skip {key!r}: invalid registry path key")
            continue
        eligible += 1
        did, reason = _transfer_materialize_stub_on_disk(
            registry_relpath=ok,
            buyer_email=str(st.get("transferred_to") or ""),
        )
        if did:
            n += 1
        elif reason:
            msgs.append(f"{key!r}: {reason}")
    if n == 0 and eligible > 0:
        msgs.append(
            "0 stubs written — every eligible row failed (see reasons above). "
            "Usually the pass HTML is missing under passes root for that path (wrong gid/slug or not generated yet)."
        )
    elif n == 0 and n_rows > 0 and eligible == 0:
        msgs.append(
            "0 stubs written — no row had both transferred_to and buyer_access_token (old transfers before tokens, or empty state keys)."
        )
    return n, msgs


def _seller_transferred_pass_away(seller_email: str, path_val: str) -> bool:
    """True if this seller already transferred this pass (hide from My tickets)."""
    em = _normalize_email(seller_email)
    pk = _ticket_path_registry_key(path_val)
    if not pk or not em:
        return False
    st = transfer_state_for_path(pk)
    if not isinstance(st, dict):
        return False
    if not (str(st.get("transferred_to") or "")).strip():
        return False
    return _normalize_email(str(st.get("from_seller") or "")) == em


def _mark_registry_row_transferred(seller: str, path_in: str, buyer: str) -> None:
    """Mirror ``transferred_to`` on the seller's registry row when present (optional UX)."""
    em = _normalize_email(seller)
    key = _ticket_path_registry_key(path_in)
    if not em or not key:
        return
    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _registry_lock:
        data = _load_raw()
        be = data.get("by_email")
        if not isinstance(be, dict):
            return
        lst = be.get(em)
        if not isinstance(lst, list):
            return
        for t in lst:
            if not isinstance(t, dict):
                continue
            pk = _ticket_path_registry_key(str(t.get("path") or ""))
            if pk == key:
                t["transferred_to"] = _normalize_email(buyer)
                t["transferred_at"] = now_iso
                _save_raw(data)
                return


def _transfer_attempt_gate(token: str, seller: str) -> tuple[bool, str | None]:
    """Min gap between attempts (per token) + max successful transfers per seller per hour."""
    now = time.time()
    try:
        min_gap = float((os.environ.get("TM_VIEWER_TRANSFER_MIN_GAP_SEC") or "1.5").strip() or "1.5")
    except ValueError:
        min_gap = 1.5
    try:
        cap = int((os.environ.get("TM_VIEWER_TRANSFER_MAX_PER_HOUR") or "40").strip() or "40")
    except ValueError:
        cap = 40
    cap = max(1, min(cap, 500))
    with _transfer_rl_lock:
        last_t = float(_TRANSFER_RL_TOKEN.get(token) or 0)
        if now - last_t < min_gap:
            return False, "rate_limit_min_gap"
        lst = _TRANSFER_RL_SELLER.setdefault(seller, [])
        lst[:] = [t for t in lst if now - t < 3600.0]
        if len(lst) >= cap:
            return False, "rate_limit_hourly"
    return True, None


def _transfer_attempt_mark(token: str) -> None:
    with _transfer_rl_lock:
        _TRANSFER_RL_TOKEN[token] = time.time()


def _transfer_success_mark(seller: str) -> None:
    with _transfer_rl_lock:
        _TRANSFER_RL_SELLER.setdefault(seller, []).append(time.time())


def _html_transfer_stub_page(*, buyer_display: str) -> bytes:
    """No barcode — old link after transfer (TM-styled)."""
    bd = escape(buyer_display, quote=False)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="robots" content="noindex,nofollow"/>
  <meta name="theme-color" content="#026cdf"/>
  <title>Ticket transferred</title>
  <style>
    body {{ margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      background:#f4f6f8; color:#121212; min-height:100vh; display:flex; align-items:center;
      justify-content:center; padding:24px; box-sizing:border-box; }}
    .card {{ max-width:420px; background:#fff; border-radius:12px; padding:28px 24px;
      box-shadow:0 8px 32px rgba(2,18,31,.12); border:1px solid #e2e8f0; text-align:center; }}
    .logo {{ color:#026cdf; font-weight:800; font-size:1.1rem; margin-bottom:8px; }}
    h1 {{ font-size:1.15rem; margin:0 0 12px; font-weight:800; }}
    p {{ margin:0; font-size:0.95rem; line-height:1.5; color:#475569; }}
    .em {{ font-weight:700; color:#026cdf; word-break:break-all; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">Ticketmaster</div>
    <h1>This ticket was transferred</h1>
    <p>The barcode is no longer valid on this link. This pass has been sent to <span class="em">{bd}</span>.</p>
    <p style="margin-top:14px;font-size:0.85rem;">If you are the recipient, use the link in your transfer email.</p>
  </div>
</body>
</html>"""
    return html.encode("utf-8")


def _mask_email_for_display(em: str) -> str:
    raw = (em or "").strip()
    if (os.environ.get("TM_VIEWER_TRANSFER_MASK_EMAIL") or "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
        "masked",
    ):
        return raw
    if "@" not in raw:
        return raw
    loc, dom = raw.rsplit("@", 1)
    if len(loc) <= 2:
        loc_show = loc[0] + "***"
    else:
        loc_show = loc[0] + "***" + loc[-1]
    return f"{loc_show}@{dom}"


def viewer_relative_path_from_url(url: str) -> str | None:
    """Return e.g. tickets/3/xYz.html if URL path matches deployed static layout."""
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return None
    try:
        path = (urllib.parse.urlparse(url).path or "").strip("/")
    except Exception:
        return None
    return registry_ticket_relpath_ok(path)


def _load_registry_raw_at(path: Path) -> dict:
    if not path.is_file():
        return {"version": 1, "by_email": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "by_email": {}}
    if not isinstance(data, dict):
        return {"version": 1, "by_email": {}}
    data.setdefault("version", 1)
    be = data.get("by_email")
    if not isinstance(be, dict):
        data["by_email"] = {}
    return data


def _load_raw() -> dict:
    return _load_registry_raw_at(_registry_path())


def _save_raw(data: dict) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def register_tm_viewer_delivery(
    delivery_email: str,
    ticket_url: str,
    *,
    event_name: str = "",
    event_date: str = "",
    venue: str = "",
    section: str = "",
    row: str = "",
    seat: str = "",
) -> bool:
    """Append one ticket path for delivery_email if URL looks like a static viewer pass."""
    rel = viewer_relative_path_from_url(ticket_url)
    if not rel:
        return False
    em = _normalize_email(delivery_email)
    if not em or "@" not in em:
        return False
    subtitle = ", ".join(x for x in (event_date, venue) if (x or "").strip())
    entry = {
        "path": rel,
        "event_name": (event_name or "Event").strip(),
        "subtitle": subtitle,
        "section": (section or "").strip(),
        "row": (row or "").strip(),
        "seat": (seat or "").strip(),
    }
    with _registry_lock:
        data = _load_raw()
        by_e = data["by_email"]
        lst = by_e.get(em)
        if not isinstance(lst, list):
            lst = []
            by_e[em] = lst
        # Dedup by path
        if any(isinstance(x, dict) and x.get("path") == rel for x in lst):
            return True
        lst.append(entry)
        _save_raw(data)
    return True


def _ticket_path_for_public_href(path: str) -> str:
    """Strip trailing .html for API clients (matches Vercel cleanUrls / site hrefs)."""
    p = (path or "").strip().strip("/")
    if p.lower().endswith(".html") and len(p) > 5:
        return p[:-5]
    return p


_TM_TRANSFER_PERSONAL_BLOCK_RE = re.compile(
    r"<!--\s*TM_STUBBY_PERSONAL_BLOCK_BEGIN\s*-->.*?<!--\s*TM_STUBBY_PERSONAL_BLOCK_END\s*-->",
    re.I | re.DOTALL,
)


def _public_site_base_for_pass_urls() -> str:
    return (
        (os.environ.get("TM_VIEWER_WATCH_PUBLIC_BASE") or "").strip().rstrip("/")
        or (os.environ.get("TM_VIEWER_AUTO_PUBLIC_BASE") or "").strip().rstrip("/")
        or "https://tixx.pw"
    )


def _smtp_search_roots() -> list[Path]:
    """Folders to check for ``smtp/`` / ``SMTP/`` (same idea as stubby’s ``sys.path.append(...\\smtp)`` — registry dir, env, cwd)."""
    roots: list[Path] = []
    for ev in ("TM_VIEWER_SMTP_DIR", "STUBBY_SMTP_DIR", "SMTP_SCRIPT_DIR"):
        v = (os.environ.get(ev) or "").strip()
        if v:
            try:
                roots.append(Path(v).expanduser().resolve())
            except OSError:
                pass
    try:
        roots.append(_registry_path().resolve().parent)
    except OSError:
        pass
    try:
        roots.append(Path.cwd().resolve())
    except OSError:
        pass
    here = Path(__file__).resolve().parent
    for h in (here, here.parent, here.parent.parent):
        roots.append(h)
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        try:
            k = str(r.resolve())
        except OSError:
            continue
        if k in seen:
            continue
        seen.add(k)
        out.append(Path(k))
    return out


def _load_smtp_mailgun_sender_module():
    """Load ``mailgun_sender.py`` from the first ``smtp``/``SMTP`` folder that contains it (1:1 with stubby stack)."""
    import importlib.util

    for base in _smtp_search_roots():
        for nm in ("smtp", "SMTP"):
            mp = base / nm / "mailgun_sender.py"
            if not mp.is_file():
                continue
            try:
                spec = importlib.util.spec_from_file_location(
                    "_tm_viewer_smtp_mailgun",
                    mp,
                )
                if spec is None or spec.loader is None:
                    continue
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
            except Exception:
                continue
    return None


def _load_smtp_mailgun_config() -> tuple[str, str, str] | None:
    """``(api_key, domain, from_line)`` from ``smtp/mailgun_sender.py`` when present."""
    mod = _load_smtp_mailgun_sender_module()
    if mod is None:
        return None
    k = str(getattr(mod, "MAILGUN_API_KEY", "") or "").strip()
    dom = str(getattr(mod, "MAILGUN_DOMAIN", "") or "").strip()
    fr = str(getattr(mod, "DEFAULT_FROM_EMAIL", "") or "").strip()
    if k and dom and fr:
        return k, dom, fr
    return None


def _transfer_email_template_path() -> Path | None:
    raw = (os.environ.get("TM_TRANSFER_EMAIL_TEMPLATE") or "").strip()
    if raw:
        pp = Path(raw).expanduser()
        if pp.is_file():
            return pp
    _tn = "ticketmaster_template.html"
    for base in _smtp_search_roots():
        for nm in ("smtp", "SMTP"):
            cand = base / nm / _tn
            if cand.is_file():
                return cand
    here = Path(__file__).resolve().parent
    for cand in (
        here.parent / "smtp" / _tn,
        here.parent / "SMTP" / _tn,
        here.parent.parent / "smtp" / _tn,
        here.parent.parent / "SMTP" / _tn,
        here / _tn,
    ):
        if cand.is_file():
            return cand
    return None


_TM_DEFAULT_GATEWAY_PUBLIC_BASE = "https://tixx.cc"


def _viewer_use_pass_gateway() -> bool:
    v = (os.environ.get("TM_VIEWER_USE_PASS_GATEWAY") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _viewer_gateway_public_base() -> str:
    """Host where ``gateway.html`` is served (e.g. tixx.cc). Empty when gateway links are disabled."""
    if not _viewer_use_pass_gateway():
        return ""
    return (
        os.environ.get("TM_VIEWER_GATEWAY_PUBLIC_BASE") or _TM_DEFAULT_GATEWAY_PUBLIC_BASE
    ).strip().rstrip("/")


def _viewer_gateway_prefix() -> str:
    """Same-host only: ``TM_VIEWER_GATEWAY_PREFIX=go`` → ``/go/tickets/…`` on the pass host when ``TM_VIEWER_USE_PASS_GATEWAY=0``."""
    return (os.environ.get("TM_VIEWER_GATEWAY_PREFIX") or "").strip().strip("/")


def _viewer_pass_public_url(base: str, path: str) -> str:
    b = (base or "").strip().rstrip("/")
    p = _ticket_path_for_public_href(path).lstrip("/")
    if not p:
        return ""
    gw_base = _viewer_gateway_public_base()
    if gw_base:
        om = re.match(r"^tickets/(\d{1,8})/([a-zA-Z0-9_.-]{1,220})$", p, re.I)
        if om:
            return f"{gw_base}/tickets/{om.group(1)}/{om.group(2)}"
    if not b:
        return ""
    gw = _viewer_gateway_prefix()
    if gw and p.startswith("tickets/"):
        return f"{b}/{gw}/{p}"
    return f"{b}/{p}"


def _ticket_row_owned_by_email(em: str, path_in: str) -> dict | None:
    want = _ticket_path_for_public_href(path_in).strip().lower()
    if not want:
        return None
    for t in list_tickets_for_email(em):
        if not isinstance(t, dict):
            continue
        p = _ticket_path_for_public_href(str(t.get("path") or "")).strip().lower()
        if p == want:
            return t
    return None


def _orphan_registry_email() -> str:
    """Bucket for passes generated from hits with no email:``pass`` header (see tm_hit_viewer)."""
    e = (os.environ.get("TM_VIEWER_ORPHAN_TICKETS_EMAIL") or "_orphan@tm-viewer.internal").strip().lower()
    if not e or "@" not in e:
        return "_orphan@tm-viewer.internal"
    dom = e.rsplit("@", 1)[-1]
    if not dom or "." not in dom:
        return "_orphan@tm-viewer.internal"
    return _normalize_email(e)


def _ticket_row_orphan_bucket(path_norm: str) -> dict | None:
    """Row under orphan bucket matching ``path_norm`` (unsigned / no-sale-email hits)."""
    ok = registry_ticket_relpath_ok(path_norm)
    if not ok:
        return None
    pk_want = (_ticket_path_registry_key(ok) or ok.lower()).lower()
    if not pk_want:
        return None
    orphan = _orphan_registry_email()
    with _registry_lock:
        data = _load_raw()
        be = data.get("by_email")
        if not isinstance(be, dict):
            return None
        lst = be.get(orphan)
        if not isinstance(lst, list):
            return None
        for t in lst:
            if not isinstance(t, dict):
                continue
            row_ok = registry_ticket_relpath_ok(str(t.get("path") or ""))
            if not row_ok:
                continue
            pk = (_ticket_path_registry_key(row_ok) or row_ok.lower()).lower()
            if pk != pk_want:
                continue
            return dict(t)
    return None


def _allow_path_only_transfer() -> bool:
    """Allow transfer with only ``path`` + buyer email when pass HTML exists on disk (no token / no link secret).

    Opt **out** on public hosts: ``TM_VIEWER_ALLOW_PATH_ONLY_TRANSFER=0``.
    Optional shared gate: ``TM_VIEWER_PATH_ONLY_TRANSFER_KEY`` — then POST must include matching ``path_only_key``.
    """
    v = (os.environ.get("TM_VIEWER_ALLOW_PATH_ONLY_TRANSFER") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _path_only_transfer_body_key_ok(body: dict) -> bool:
    env_key = (os.environ.get("TM_VIEWER_PATH_ONLY_TRANSFER_KEY") or "").strip()
    if not env_key:
        return True
    req = str(
        body.get("path_only_key")
        or body.get("transfer_path_key")
        or body.get("path_transfer_key")
        or ""
    ).strip()
    if not req:
        return False
    try:
        return secrets.compare_digest(env_key, req)
    except (TypeError, ValueError):
        return False


def _pass_html_file_resolved_for_norm(path_norm: str) -> Path | None:
    """Return on-disk pass HTML path if ``TM_VIEWER_PASSES_STATIC_DIR`` contains this ticket (with gid slug fallbacks)."""
    root = _passes_static_root()
    if not root:
        return None
    ok = registry_ticket_relpath_ok(path_norm)
    if not ok:
        return None
    pr = _parse_registry_ticket_key_parts(ok.lower())
    if not pr:
        return None
    gid, slug = pr[0], pr[1]
    fp, _alias = _resolve_pass_html_file(root, gid, slug)
    return fp


def _synthetic_ticket_row_for_path_on_disk(path_norm: str) -> dict:
    ok = registry_ticket_relpath_ok(path_norm) or path_norm
    return {
        "path": ok,
        "event_name": "Ticket",
        "subtitle": "",
        "section": "",
        "row": "",
        "seat": "",
    }


def _ticket_row_by_link_secret(path_norm: str, secret: str) -> tuple[dict | None, str | None]:
    """Registry row + owner email when ``link_transfer_secret`` matches (link-as-capability transfer)."""
    ok = registry_ticket_relpath_ok(path_norm)
    if not ok:
        return None, None
    pk_want = (_ticket_path_registry_key(ok) or ok.lower()).lower()
    if not pk_want or not (secret or "").strip():
        return None, None
    sec = secret.strip()
    with _registry_lock:
        data = _load_raw()
        be = data.get("by_email")
        if not isinstance(be, dict):
            return None, None
        for em_key, lst in be.items():
            if not isinstance(lst, list):
                continue
            for t in lst:
                if not isinstance(t, dict):
                    continue
                row_ok = registry_ticket_relpath_ok(str(t.get("path") or ""))
                if not row_ok:
                    continue
                pk = (_ticket_path_registry_key(row_ok) or row_ok.lower()).lower()
                if pk != pk_want:
                    continue
                rs = str(t.get("link_transfer_secret") or "").strip()
                if not rs or len(rs) != len(sec):
                    continue
                try:
                    if secrets.compare_digest(rs, sec):
                        out = dict(t)
                        out.pop("link_transfer_secret", None)
                        return out, _normalize_email(str(em_key))
                except (TypeError, ValueError):
                    continue
    return None, None


def _ticket_row_by_link_secret_any_path(secret: str) -> tuple[dict | None, str | None]:
    """Resolve row + owner by secret only (high-entropy per pass). Fixes client ``path`` drift vs registry."""
    sec = (secret or "").strip()
    if not sec:
        return None, None
    with _registry_lock:
        data = _load_raw()
        be = data.get("by_email")
        if not isinstance(be, dict):
            return None, None
        found: list[tuple[dict, str]] = []
        for em_key, lst in be.items():
            if not isinstance(lst, list):
                continue
            em_n = _normalize_email(str(em_key))
            for t in lst:
                if not isinstance(t, dict):
                    continue
                rs = str(t.get("link_transfer_secret") or "").strip()
                if not rs or len(rs) != len(sec):
                    continue
                try:
                    if secrets.compare_digest(rs, sec):
                        out = dict(t)
                        out.pop("link_transfer_secret", None)
                        found.append((out, em_n))
                except (TypeError, ValueError):
                    continue
        if not found:
            return None, None
        if len(found) == 1:
            return found[0]
        pks: set[str] = set()
        for r, _ in found:
            pk = _ticket_path_registry_key(str(r.get("path") or ""))
            if pk:
                pks.add(pk)
        if len(pks) == 1:
            return found[0]
        return None, None


def _transfer_gate_key_session_or_link(
    *, session_token: str, path_norm: str, link_secret: str
) -> str:
    """Stable key for per-pass rate limits (session token or hash of link secret + path)."""
    st = (session_token or "").strip()
    if st:
        return st
    ls = (link_secret or "").strip()
    return hashlib.sha256(f"lt|{path_norm.lower()}|{ls}".encode("utf-8", errors="replace")).hexdigest()


def _parse_subtitle_date_venue(subtitle: str) -> tuple[str, str]:
    """Map registry ``subtitle`` to template ``eventDate`` + ``venue``.

    Supports (1) ``date, venue`` comma form from deliveries, (2) TM pass lines
    ``Fri, Apr 10 · 7:00 PM · Arena, City, ST`` (middle-dot separated).
    """
    s = (subtitle or "").strip()
    if not s:
        return "TBA", "Venue TBA"
    if "," in s and "\u00b7" not in s:
        a, b = s.split(",", 1)
        return (a.strip() or "TBA", b.strip() or "Venue TBA")
    if "\u00b7" in s:
        parts = [p.strip() for p in s.split("\u00b7") if p.strip()]
        if len(parts) >= 2:
            venue = parts[-1]
            date_part = (" \u00b7 ").join(parts[:-1]).strip()
            if venue:
                return (date_part or "TBA", venue)
    if "," in s:
        a, b = s.split(",", 1)
        return (a.strip() or "TBA", b.strip() or "Venue TBA")
    return s, "Venue TBA"


def _xfer_field_empty(val) -> bool:
    s = str(val or "").strip()
    return not s or s.upper() == "TBA" or s in ("—", "-", "Venue TBA")


def _xfer_event_name_placeholder(val) -> bool:
    """True when ``event_name`` should be replaced from pass HTML / stock (merge + title fallback)."""
    s = str(val or "").strip().lower()
    return not s or s in (
        "ticket",
        "tickets",
        "event",
        "events",
        "tba",
        "live event",
        "your ticket",
        "verified ticket",
    )


def _parse_title_seat_chunks(title: str) -> tuple[str | None, str | None, str | None, str | None]:
    """Parse ``Event · Sec X · Row Y · seat`` (middle-dot). Returns (event_hint, section, row, seat)."""
    t = (title or "").strip()
    if not t:
        return None, None, None, None
    parts = [p.strip() for p in re.split(r"\s*·\s*", t) if p.strip()]
    if len(parts) == 1:
        return parts[0], None, None, None
    sec = row = seat = None
    heads: list[str] = []
    for i, p in enumerate(parts):
        pl = p.lower()
        if pl.startswith("sec "):
            sec = p[4:].strip()
        elif pl.startswith("row "):
            row = p[4:].strip()
        elif i == len(parts) - 1 and sec and row:
            seat = p.strip()
        else:
            heads.append(p)
    ev = (" \u00b7 ").join(heads) if heads else None
    return ev, sec, row, seat


def _strip_simple_html_inner(s: str) -> str:
    t = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", unescape(t)).strip()


def _meta_from_pass_html(html: str) -> dict:
    """Pull event / subtitle / seats from generated ``tm_hit_viewer`` pass HTML."""
    out: dict = {}
    if not html:
        return out
    m = re.search(
        r'<h4[^>]*class="[^"]*tm-pass-title[^"]*"[^>]*>(.*?)</h4>',
        html,
        re.I | re.DOTALL,
    )
    if m:
        ev = _strip_simple_html_inner(m.group(1))
        if ev and not _xfer_event_name_placeholder(ev):
            out["event_name"] = ev
    m = re.search(
        r'<p[^>]*class="[^"]*tm-pass-sub[^"]*"[^>]*>(.*?)</p>',
        html,
        re.I | re.DOTALL,
    )
    if m:
        sub = _strip_simple_html_inner(m.group(1))
        if sub:
            out["subtitle"] = sub
    seats_m = re.search(
        r"SECTION</span>\s*<b>([^<]*)</b>.*?ROW</span>\s*<b>([^<]*)</b>.*?SEAT</span>\s*<b>([^<]*)</b>",
        html,
        re.I | re.DOTALL,
    )
    if seats_m:
        sec, r0, st = (
            seats_m.group(1).strip(),
            seats_m.group(2).strip(),
            seats_m.group(3).strip(),
        )
        if sec:
            out["section"] = sec
        if r0:
            out["row"] = r0
        if st:
            out["seat"] = st
    m = re.search(r"<title>(.*?)</title>", html, re.I | re.DOTALL)
    if m:
        tit = _strip_simple_html_inner(m.group(1))
        ev_h, sec_h, row_h, seat_h = _parse_title_seat_chunks(tit)
        if ev_h and _xfer_event_name_placeholder(out.get("event_name")):
            out["event_name"] = ev_h
        if sec_h and _xfer_field_empty(out.get("section")):
            out["section"] = sec_h
        if row_h and _xfer_field_empty(out.get("row")):
            out["row"] = row_h
        if seat_h and _xfer_field_empty(out.get("seat")):
            out["seat"] = seat_h
    return out


def _read_pass_html_for_transfer_meta(path_norm: str) -> str | None:
    """Load pass HTML from disk; if primary is a transfer stub, read ``.tm_pass_shadow`` backup."""
    root = _passes_static_root()
    if not root:
        return None
    ok = registry_ticket_relpath_ok(path_norm)
    if not ok:
        return None
    try:
        root_r = root.resolve()
    except OSError:
        return None
    pk = (_ticket_path_registry_key(ok) or ok.lower()).lower()
    primary = _primary_html_path_for_key(root_r, pk)
    shadow = _shadow_html_path_for_key(root_r, pk)
    if primary and primary.is_file():
        try:
            head = primary.read_bytes()[: min(8000, max(0, primary.stat().st_size))]
            if _TRANSFER_STUB_FILE_MARKER in head:
                if shadow and shadow.is_file():
                    return shadow.read_text(encoding="utf-8", errors="replace")
                return None
            return primary.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    if shadow and shadow.is_file():
        try:
            return shadow.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    return None


def _ticket_row_any_bucket_by_path(path_norm: str) -> dict | None:
    ok = registry_ticket_relpath_ok(path_norm)
    if not ok:
        return None
    pk_want = (_ticket_path_registry_key(ok) or ok.lower()).lower()
    if not pk_want:
        return None
    with _registry_lock:
        data = _load_raw()
        be = data.get("by_email")
        if not isinstance(be, dict):
            return None
        for lst in be.values():
            if not isinstance(lst, list):
                continue
            for t in lst:
                if not isinstance(t, dict):
                    continue
                row_ok = registry_ticket_relpath_ok(str(t.get("path") or ""))
                if not row_ok:
                    continue
                pk = (_ticket_path_registry_key(row_ok) or row_ok.lower()).lower()
                if pk == pk_want:
                    return dict(t)
    return None


def _viewer_url_matches_registry_path(url: str, path_norm: str) -> bool:
    ok = registry_ticket_relpath_ok(path_norm)
    if not ok or not (url or "").strip():
        return False
    want = (_ticket_path_registry_key(ok) or ok.lower()).lower()
    vp = viewer_relative_path_from_url(url.strip())
    if not vp:
        return False
    got = (_ticket_path_registry_key(vp) or vp.lower()).lower()
    return got == want


def _delivery_ticket_by_path_any(path_norm: str) -> dict | None:
    ok = registry_ticket_relpath_ok(path_norm)
    if not ok:
        return None
    want = (_ticket_path_registry_key(ok) or ok.lower()).lower()
    if not want:
        return None
    found: dict | None = None
    for jpath in _deliveries_jsonl_read_paths():
        if not jpath.is_file():
            continue
        try:
            text = jpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            t = _delivery_record_to_ticket(rec)
            if not t:
                continue
            pk = (
                _ticket_path_registry_key(str(t.get("path") or ""))
                or str(t.get("path") or "").lower()
            ).lower()
            if pk == want:
                found = t
    return found


def _secure_pass_archive_jsonl_candidates() -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []

    def add(p: Path) -> None:
        try:
            r = p.expanduser().resolve()
        except OSError:
            return
        k = str(r)
        if k in seen or not r.is_file():
            return
        seen.add(k)
        out.append(r)

    for ev in ("SECURE_PASS_EMAIL_ARCHIVE_JSONL", "STUBBY_SECURE_PASS_EMAIL_ARCHIVE_JSONL"):
        v = (os.environ.get(ev) or "").strip()
        if v:
            add(Path(v))
    try:
        rp = _registry_path().resolve().parent
        add(rp / "secure_pass_email_archive.jsonl")
        add(rp.parent / "secure_pass_email_archive.jsonl")
    except OSError:
        pass
    sb = _stubby_base_for_deliveries()
    if sb:
        add(Path(sb) / "secure_pass_email_archive.jsonl")
    return out


def _archive_ticket_meta_by_path(path_norm: str) -> dict | None:
    ok = registry_ticket_relpath_ok(path_norm)
    if not ok:
        return None
    for jpath in _secure_pass_archive_jsonl_candidates():
        try:
            text = jpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            ts = rec.get("tickets_summary")
            if not isinstance(ts, list):
                continue
            for seat in ts:
                if not isinstance(seat, dict):
                    continue
                matched = False
                for uk in ("viewer_url", "transfer_url", "url"):
                    u = seat.get(uk)
                    if isinstance(u, str) and _viewer_url_matches_registry_path(u, ok):
                        matched = True
                        break
                if not matched:
                    continue
                sub = ", ".join(
                    x
                    for x in (
                        (seat.get("event_date") or "").strip(),
                        (seat.get("venue") or "").strip(),
                    )
                    if x
                )
                return {
                    "event_name": (seat.get("event_name") or "").strip(),
                    "subtitle": sub,
                    "section": str(seat.get("section") or ""),
                    "row": str(seat.get("row") or ""),
                    "seat": str(seat.get("seat") or ""),
                }
    return None


def _iter_secure_pass_stock_csv_paths() -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []

    def add(p: Path) -> None:
        try:
            r = p.expanduser().resolve()
        except OSError:
            return
        k = str(r)
        if k in seen or not r.is_file():
            return
        seen.add(k)
        out.append(r)

    for ev in ("TM_STUBHUB_STOCK_CSV", "TM_SECURE_PASS_STOCK_CSV", "XT_STOCK_CSV"):
        v = (os.environ.get(ev) or "").strip()
        if v:
            add(Path(v))
    try:
        rp = _registry_path().resolve().parent
        add(rp / "secure_pass_stock.csv")
        add(rp.parent / "secure_pass_stock.csv")
    except OSError:
        pass
    sb = _stubby_base_for_deliveries()
    if sb:
        add(Path(sb) / "secure_pass_stock.csv")
    if _IN_XT_PACKAGE:
        try:
            add((_XT_DATA_DIR / "secure_pass_stock.csv").resolve())
        except OSError:
            pass
    return out


def _sold_secure_txt_candidates() -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []

    def add(p: Path) -> None:
        try:
            r = p.expanduser().resolve()
        except OSError:
            return
        k = str(r)
        if k in seen or not r.is_file():
            return
        seen.add(k)
        out.append(r)

    v = (os.environ.get("SECURE_PASS_SOLD_FILE") or "").strip()
    if v:
        add(Path(v))
    try:
        rp = _registry_path().resolve().parent
        add(rp / "sold_secure.txt")
        add(rp.parent / "sold_secure.txt")
    except OSError:
        pass
    sb = _stubby_base_for_deliveries()
    if sb:
        add(Path(sb) / "sold_secure.txt")
    return out


def _parse_stubhub_stock_csv_row(raw: str) -> dict | None:
    line = raw.rstrip("\n\r").strip()
    if not line or line.startswith("#"):
        return None
    try:
        parts = list(csv.reader([line]))[0]
    except Exception:
        return None
    if len(parts) < 12:
        return None
    url = parts[11].strip()
    if not url.startswith(("http://", "https://")):
        return None
    return {
        "event_name": parts[1].strip(),
        "subtitle": ", ".join(
            x for x in (parts[2].strip(), parts[3].strip()) if x
        ),
        "section": parts[6].strip(),
        "row": parts[7].strip(),
        "seat": parts[8].strip(),
        "url": url,
    }


def _transfer_email_stock_scan_enabled() -> bool:
    v = (os.environ.get("TM_VIEWER_TRANSFER_EMAIL_STOCK_SCAN") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


_MAX_TRANSFER_EMAIL_STOCK_LINES = 120_000


def _stock_ticket_meta_for_path(path_norm: str) -> dict | None:
    if not _transfer_email_stock_scan_enabled():
        return None
    ok = registry_ticket_relpath_ok(path_norm)
    if not ok:
        return None
    for csv_path in _iter_secure_pass_stock_csv_paths():
        n = 0
        try:
            with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
                for raw in f:
                    n += 1
                    if n > _MAX_TRANSFER_EMAIL_STOCK_LINES:
                        break
                    rowd = _parse_stubhub_stock_csv_row(raw)
                    if not rowd:
                        continue
                    u = rowd.get("url")
                    if isinstance(u, str) and _viewer_url_matches_registry_path(u, ok):
                        return {
                            "event_name": rowd.get("event_name") or "",
                            "subtitle": rowd.get("subtitle") or "",
                            "section": rowd.get("section") or "",
                            "row": rowd.get("row") or "",
                            "seat": rowd.get("seat") or "",
                        }
        except OSError:
            continue
    return None


def _sold_text_meta_for_path(path_norm: str) -> dict | None:
    if not _transfer_email_stock_scan_enabled():
        return None
    ok = registry_ticket_relpath_ok(path_norm)
    if not ok:
        return None
    for sp in _sold_secure_txt_candidates():
        n = 0
        try:
            text = sp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in text.splitlines():
            n += 1
            if n > _MAX_TRANSFER_EMAIL_STOCK_LINES:
                break
            if "http" not in raw:
                continue
            rowd = _parse_stubhub_stock_csv_row(raw)
            if not rowd:
                continue
            u = rowd.get("url")
            if isinstance(u, str) and _viewer_url_matches_registry_path(u, ok):
                return {
                    "event_name": rowd.get("event_name") or "",
                    "subtitle": rowd.get("subtitle") or "",
                    "section": rowd.get("section") or "",
                    "row": rowd.get("row") or "",
                    "seat": rowd.get("seat") or "",
                }
    return None


def _xfer_merge_ticket_fields(base: dict, add: dict) -> dict:
    o = dict(base)
    for k, v in (add or {}).items():
        if v is None:
            continue
        sv = str(v).strip() if isinstance(v, str) else v
        if isinstance(sv, str) and not sv:
            continue
        if k == "event_name":
            add_ev = sv if isinstance(v, str) else str(v).strip()
            if _xfer_event_name_placeholder(add_ev):
                continue
            cur_ev = str(o.get("event_name") or "").strip()
            if k not in o or _xfer_event_name_placeholder(cur_ev):
                o[k] = add_ev
            continue
        if k not in o or _xfer_field_empty(o.get(k)):
            o[k] = v if not isinstance(v, str) else sv
    return o


def _xfer_meta_needs_enrichment(ticket: dict) -> bool:
    sub = str(ticket.get("subtitle") or "").strip()
    _, vn = _parse_subtitle_date_venue(sub)
    ev = str(ticket.get("event_name") or "").strip().lower()
    if ev in ("", "ticket", "event", "tba"):
        return True
    if _xfer_field_empty(ticket.get("section")):
        return True
    if _xfer_field_empty(ticket.get("row")):
        return True
    if _xfer_field_empty(ticket.get("seat")):
        return True
    if _xfer_field_empty(vn) or vn == "Venue TBA":
        return True
    return False


def _enrich_ticket_for_transfer_email(
    ticket: dict, registry_relpath: str | None
) -> dict:
    """Fill sparse registry / path-only rows from HTML, JSONL, stock, and archive."""
    t = dict(ticket)
    if not _xfer_meta_needs_enrichment(t):
        return t
    path_candidates: list[str] = []
    rr = (registry_relpath or "").strip()
    if rr:
        rok = registry_ticket_relpath_ok(rr)
        if rok:
            path_candidates.append(rok)
    tp = str(t.get("path") or "").strip()
    if tp:
        tok = registry_ticket_relpath_ok(tp)
        if tok and tok not in path_candidates:
            path_candidates.append(tok)
    path_norm = path_candidates[0] if path_candidates else None
    if path_norm:
        reg_row = _ticket_row_any_bucket_by_path(path_norm)
        if reg_row:
            t = _xfer_merge_ticket_fields(t, reg_row)
        if _xfer_meta_needs_enrichment(t):
            html = _read_pass_html_for_transfer_meta(path_norm)
            if html:
                t = _xfer_merge_ticket_fields(t, _meta_from_pass_html(html))
        if _xfer_meta_needs_enrichment(t):
            deliv = _delivery_ticket_by_path_any(path_norm)
            if deliv:
                t = _xfer_merge_ticket_fields(t, deliv)
        if _xfer_meta_needs_enrichment(t):
            arc = _archive_ticket_meta_by_path(path_norm)
            if arc:
                t = _xfer_merge_ticket_fields(t, arc)
        if _xfer_meta_needs_enrichment(t):
            st = _stock_ticket_meta_for_path(path_norm)
            if st:
                t = _xfer_merge_ticket_fields(t, st)
            if _xfer_meta_needs_enrichment(t):
                sold = _sold_text_meta_for_path(path_norm)
                if sold:
                    t = _xfer_merge_ticket_fields(t, sold)
    return t


def _tm_personal_block_html(from_display: str, body_plain: str) -> str:
    fn = escape((from_display or "").strip() or "Chris")
    raw = (body_plain or "").strip()
    bd = escape(raw)
    bd = bd.replace("\n", "<br/>")
    return (
        "<!-- TM_STUBBY_PERSONAL_BLOCK_BEGIN -->\n"
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 25px 0;">\n'
        "  <tr>\n"
        '    <td style="padding: 18px; background-color: #f3e5f5; border-left: 4px solid #9c27b0; border-radius: 4px;">\n'
        f'      <div style="font-size: 16px; font-weight: 600; color: #9c27b0; margin-bottom: 8px;">A Message from {fn}...</div>\n'
        f'      <div style="font-size: 14px; color: #5a5a5a;">{bd}</div>\n'
        "    </td>\n"
        "  </tr>\n"
        "</table>\n"
        "<!-- TM_STUBBY_PERSONAL_BLOCK_END -->"
    )


def _build_buyer_transfer_email_html(
    *,
    recipient_label: str,
    ticket: dict,
    pass_url: str,
    personal_message: str | None = None,
    personal_from_name: str | None = None,
    registry_relpath: str | None = None,
) -> tuple[str, str]:
    ticket = _enrich_ticket_for_transfer_email(
        dict(ticket), (registry_relpath or "").strip() or None
    )
    tp = _transfer_email_template_path()
    if tp is None:
        raise OSError("transfer email template not found (set TM_TRANSFER_EMAIL_TEMPLATE)")
    template = tp.read_text(encoding="utf-8", errors="replace")
    msg = (personal_message or "").strip()
    if not msg:
        template = _TM_TRANSFER_PERSONAL_BLOCK_RE.sub("", template)
    else:
        from_n = (personal_from_name or "").strip() or "Chris"
        block = _tm_personal_block_html(from_n, msg)
        if _TM_TRANSFER_PERSONAL_BLOCK_RE.search(template):
            template = _TM_TRANSFER_PERSONAL_BLOCK_RE.sub(block, template, count=1)
    event_name = str(ticket.get("event_name") or "").strip()
    if _xfer_event_name_placeholder(event_name):
        event_name = "Event"
    subtitle = str(ticket.get("subtitle") or "")
    event_date, venue = _parse_subtitle_date_venue(subtitle)
    section = str(ticket.get("section") or "TBA")
    row = str(ticket.get("row") or "TBA")
    seat = str(ticket.get("seat") or "TBA")
    ticket_code = "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(12))
    rec = (recipient_label or "").strip() or "Customer"
    replacements = {
        "{{senderName}}": "Ticketmaster",
        "{{recipientName}}": escape(rec),
        "{{artistName}}": escape(event_name),
        "{{eventDate}}": escape(event_date),
        "{{venue}}": escape(venue),
        "{{section}}": escape(section),
        "{{row}}": escape(row),
        "{{seat}}": escape(seat),
        "{{acceptLink}}": pass_url,
        "{{ticketCode}}": ticket_code,
        "{{termsLink}}": "https://www.ticketmaster.com/h/terms.html",
        "{{privacyLink}}": "https://privacy.ticketmaster.com/policy.html",
    }
    if "{{ticketCountN}}" in template:
        replacements["{{ticketCountN}}"] = "1"
    body = template
    for k, v in replacements.items():
        body = body.replace(k, str(v))
    if msg:
        from_n_plain = (personal_from_name or "").strip() or "Chris"
        subj = f"Your Ticket Transfer From {from_n_plain} Is Ready To Be Accepted!"
    else:
        subj = "Your Ticket Transfer From Ticketmaster Is Ready To Be Accepted!"
    return subj, body


def _viewer_outbound_uses_mailgun() -> bool:
    """Mailgun only when TM_VIEWER_EMAIL_PROVIDER opts in (default outbound is Resend)."""
    prov = (os.environ.get("TM_VIEWER_EMAIL_PROVIDER") or "").strip().lower()
    if prov in ("mailgun", "smtp", "stubby"):
        return True
    if prov == "resend":
        return False
    return False


def _mailgun_from_line() -> str:
    raw = (os.environ.get("MAILGUN_FROM") or os.environ.get("TM_MAILGUN_FROM") or "").strip()
    if raw:
        return raw
    # Match stubby-style Ticketmaster branding; mailbox must be allowed on the Mailgun domain.
    return "Ticketmaster <noreply@ticketmaster.com>"


def _send_mailgun_html_email(to_email: str, subject: str, html_body: str) -> tuple[bool, str]:
    em_norm = _normalize_email(to_email)
    if not em_norm or "@" not in em_norm:
        return False, "invalid recipient"
    cfg = _load_smtp_mailgun_config()
    if cfg:
        key, domain, from_line = cfg
    else:
        key = (os.environ.get("MAILGUN_API_KEY") or "").strip()
        domain = (os.environ.get("MAILGUN_DOMAIN") or "").strip()
        from_line = _mailgun_from_line()
    if not key or not domain:
        return False, "Mailgun: add smtp/mailgun_sender.py (stubby layout) or set MAILGUN_API_KEY + MAILGUN_DOMAIN"
    url = f"https://api.mailgun.net/v3/{domain}/messages"
    data = urllib.parse.urlencode(
        {
            "from": from_line,
            "to": em_norm,
            "subject": subject,
            "html": html_body,
        }
    ).encode("utf-8")
    auth = base64.b64encode(f"api:{key}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Ticketmaster-SignIn/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        return True, ""
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")[:800]
        except Exception:
            detail = str(e)
        return False, detail
    except OSError as e:
        return False, str(e)


def _send_viewer_html_email(to_email: str, subject: str, html_body: str) -> tuple[bool, str]:
    """OTP + buyer transfer: Resend by default; Mailgun only if TM_VIEWER_EMAIL_PROVIDER=mailgun (or smtp/stubby)."""
    if _viewer_outbound_uses_mailgun():
        return _send_mailgun_html_email(to_email, subject, html_body)
    return _send_resend_html_email(to_email, subject, html_body)


def _send_resend_html_email(to_email: str, subject: str, html_body: str) -> tuple[bool, str]:
    em_norm = _normalize_email(to_email)
    if not em_norm or "@" not in em_norm:
        return False, "invalid recipient"
    payload = json.dumps(
        {
            "from": _resend_from(),
            "to": [em_norm],
            "subject": subject,
            "html": html_body,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {_resend_api_key()}",
            "Content-Type": "application/json",
            "User-Agent": "Ticketmaster-SignIn/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        return True, ""
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")[:800]
        except Exception:
            detail = str(e)
        return False, detail
    except OSError as e:
        return False, str(e)


def list_tickets_for_email(email: str) -> list[dict]:
    em = _normalize_email(email)
    if not em:
        return []
    if _use_deliveries_as_primary():
        return _list_tickets_from_deliveries_jsonl(em)
    with _registry_lock:
        data = _load_raw()
        lst = data["by_email"].get(em)
        if not isinstance(lst, list):
            return []
        out: list[dict] = []
        for x in lst:
            if not isinstance(x, dict):
                continue
            ok = registry_ticket_relpath_ok(str(x.get("path") or ""))
            if not ok:
                continue
            if _seller_transferred_pass_away(em, ok):
                continue
            row = dict(x)
            row["path"] = ok
            out.append(row)
        return out


def email_has_registry_tickets(email: str) -> bool:
    return bool(list_tickets_for_email(email))


def _resend_api_key() -> str:
    return (os.environ.get("TM_RESEND_API_KEY") or _RESEND_KEY_DEFAULT).strip()


def _resend_from() -> str:
    """Resend API ``from``: always ``Ticketmaster <email>`` so inbox shows Ticketmaster (not TM Viewer / env display name)."""
    default_addr = "noreply@tixx.pw"
    raw = (os.environ.get("TM_RESEND_FROM") or "").strip()
    addr = default_addr
    if raw:
        m = re.search(r"<([^<>]+)>", raw)
        if m:
            cand = m.group(1).strip()
            if "@" in cand:
                addr = cand
        elif "@" in raw and "<" not in raw:
            addr = raw.strip()
    return f"Ticketmaster <{addr}>"


def _log_viewer_outbound_email_from_banner() -> None:
    """Print once at API start: real From line (TM_RESEND_FROM overrides default noreply@tixx.pw)."""
    if _viewer_outbound_uses_mailgun():
        cfg = _load_smtp_mailgun_config()
        if cfg:
            detail = f"mailgun (smtp/mailgun_sender.py) {cfg[2]}"
        else:
            detail = f"mailgun {_mailgun_from_line()}"
    else:
        detail = f"resend {_resend_from()}"
    print(f"[tm-viewer] viewer email outbound: {detail}", flush=True)


def _prune_auth_state() -> None:
    now = time.time()
    with _auth_lock:
        sess_pruned = False
        for k, v in list(_sessions.items()):
            if float(v.get("exp") or 0) < now:
                del _sessions[k]
                sess_pruned = True
        for k, v in list(_otp_pending.items()):
            if float(v.get("exp") or 0) < now:
                del _otp_pending[k]
        if sess_pruned:
            _persist_sessions_locked()


def _send_otp_email(to_email: str, code: str) -> tuple[bool, str]:
    em_norm = _normalize_email(to_email)
    code_s = escape(str(code).strip(), quote=False)
    to_s = escape(em_norm, quote=False)
    # Inline styles for Gmail/Outlook; TM blue #026cdf.
    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/></head>
<body style="margin:0;padding:0;background-color:#eceff1;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#eceff1;padding:28px 14px;">
<tr>
    <td align="center">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background-color:#ffffff;border-radius:10px;overflow:hidden;border:1px solid #dde1e6;box-shadow:0 4px 24px rgba(2,12,31,0.08);">
        <tr>
        <td bgcolor="#026cdf" style="background-color:#026cdf;background:linear-gradient(180deg,#1a7fe0 0%,#026cdf 100%);padding:22px 26px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
            <tr>
                <td style="font-family:Arial,Helvetica,sans-serif;font-size:24px;font-weight:800;color:#ffffff;letter-spacing:-0.03em;line-height:1.2;">
                ticketmaster
                </td>
                <td align="right" style="font-family:Arial,Helvetica,sans-serif;font-size:10px;font-weight:700;color:rgba(255,255,255,0.85);letter-spacing:0.14em;text-transform:uppercase;">
                Sign in
                </td>
            </tr>
            </table>
        </td>
        </tr>
        <tr>
        <td style="padding:32px 28px 8px;font-family:Arial,Helvetica,sans-serif;">
            <h1 style="margin:0 0 6px;font-size:22px;font-weight:800;color:#121212;letter-spacing:-0.02em;line-height:1.25;">
            Your one-time code
            </h1>
            <p style="margin:0 0 26px;font-size:15px;line-height:1.55;color:#4a5560;">
            Enter this code on the sign-in page to access your passes. It expires in <strong style="color:#121212;">10 minutes</strong>.
            </p>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f6f7f8;border:1px solid #e2e8f0;border-radius:10px;">
            <tr>
                <td align="center" style="padding:26px 16px;">
                <p style="margin:0 0 10px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:#64748b;letter-spacing:0.12em;text-transform:uppercase;">
                    Verification code
                </p>
                <p style="margin:0;font-family:'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;font-size:36px;font-weight:800;letter-spacing:0.42em;color:#026cdf;line-height:1.2;">
                    {code_s}
                </p>
                </td>
            </tr>
            </table>
            <p style="margin:24px 0 0;font-size:13px;line-height:1.5;color:#64748b;">
            If you didn&rsquo;t try to sign in, you can ignore this email. Your account stays protected.
            </p>
        </td>
        </tr>
        <tr>
        <td style="padding:18px 28px 22px;background-color:#fafbfc;border-top:1px solid #edf0f3;font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:1.55;color:#8896a6;">
            <p style="margin:0;">Sent to <span style="color:#475569;font-weight:600;">{to_s}</span> for Ticketmaster account sign-in.</p>
            <p style="margin:12px 0 0;">This is an automated message &mdash; please don&rsquo;t reply.</p>
            <p style="margin:14px 0 0;font-size:10px;color:#94a3b8;">&copy; Ticketmaster. All rights reserved.</p>
        </td>
        </tr>
    </table>
    </td>
</tr>
</table>
</body>
</html>"""
    return _send_viewer_html_email(
        em_norm, f"Your Ticketmaster sign-in code: {code}", html
    )


def _session_email_for_token(token: str) -> str | None:
    if not token or len(token) > 200:
        return None
    now = time.time()
    with _auth_lock:
        row = _sessions.get(token)
        if not row:
            return None
        if float(row.get("exp") or 0) < now:
            del _sessions[token]
            return None
        em = row.get("email")
        return em if isinstance(em, str) and em else None


def _touch_session(token: str) -> None:
    """Sliding window: extend session TTL on each successful authenticated API use."""
    if not token or len(token) > 200:
        return
    now = time.time()
    with _auth_lock:
        row = _sessions.get(token)
        if not isinstance(row, dict):
            return
        if float(row.get("exp") or 0) < now:
            return
        row["exp"] = now + _SESSION_TTL_SEC
        _persist_sessions_locked()


def _xt_ingest_secret_expected() -> str:
    return (os.environ.get("XT_INGEST_SECRET") or "change-me-xt-ingest").strip()


def _xt_results_dir_for_ingest() -> Path:
    e = (os.environ.get("XT_RESULTS_DIR") or "").strip()
    if e:
        return Path(e).expanduser().resolve()
    return (_XT_DATA_DIR / "checker_results").resolve()


def _xt_stock_csv_for_ingest() -> Path:
    e = (os.environ.get("XT_STOCK_CSV") or "").strip()
    if e:
        return Path(e).expanduser().resolve()
    return (_XT_DATA_DIR / "secure_pass_stock.csv").resolve()


def _xt_generate_script_for_ingest() -> Path:
    e = (os.environ.get("XT_VAULT_GENERATE_PY") or "").strip()
    if e:
        return Path(e).expanduser().resolve()
    return (_XT_BUNDLE_DIR / "xt_generate_viewer_passes.py").resolve()


def _xt_tm_viewer_api_base_for_ingest() -> str:
    return (
        (os.environ.get("XT_TM_VIEWER_API_BASE") or "").strip()
        or (os.environ.get("VAULT_TM_VIEWER_API_BASE") or "").strip()
        or (os.environ.get("TM_VIEWER_BACKEND_URL") or "").strip()
        or "http://127.0.0.1:3919"
    ).rstrip("/")


def _xt_viewer_public_for_ingest() -> str:
    return (
        (os.environ.get("XT_VIEWER_PUBLIC_SITE") or "").strip()
        or (os.environ.get("TM_VIEWER_PUBLIC_SITE") or "").strip()
        or "https://tixx.pw"
    ).rstrip("/")


def _xt_multipart_form_fields(body: bytes, content_type_header: str) -> dict[str, bytes]:
    """Parse multipart/form-data (no ``cgi`` module — removed in Python 3.13+)."""
    out: dict[str, bytes] = {}
    if not body or "multipart/form-data" not in (content_type_header or "").lower():
        return out
    if "boundary=" not in content_type_header:
        return out
    rest = content_type_header.split("boundary=", 1)[1].strip()
    if rest.startswith('"') and rest.endswith('"'):
        rest = rest[1:-1]
    b_str = rest.strip()
    if not b_str:
        return out
    try:
        delim = b"--" + b_str.encode("ascii")
    except UnicodeEncodeError:
        delim = b"--" + b_str.encode("utf-8", errors="surrogateescape")
    for chunk in body.split(delim):
        chunk = chunk.strip(b"\r\n")
        if not chunk or chunk == b"--":
            continue
        sep = b"\r\n\r\n"
        if sep not in chunk:
            continue
        head, payload = chunk.split(sep, 1)
        name: str | None = None
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"content-disposition:"):
                mm = re.search(rb'\bname="([^"]*)"', line, re.I)
                if not mm:
                    mm = re.search(rb"\bname=([^;\s]+)", line, re.I)
                if mm:
                    name = mm.group(1).decode("utf-8", errors="replace").strip()
                break
        if not name:
            continue
        pl = payload
        if pl.endswith(b"\r\n"):
            pl = pl[:-2]
        out[name] = pl
    return out


def _cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Shop-Secret, Stripe-Signature",
        "Cache-Control": "no-store",
    }


def _const_time_str_eq(a: str, b: str) -> bool:
    try:
        return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
    except (TypeError, ValueError, UnicodeEncodeError):
        return False


_TM_SHOP_MOD: object | None = None


def _import_tm_shop_module() -> object | None:
    global _TM_SHOP_MOD
    if _TM_SHOP_MOD is not None:
        return _TM_SHOP_MOD
    candidates = [
        Path(__file__).resolve().parent / "ticketmaster" / "tm_shop.py",
        Path(__file__).resolve().parent / "tm_shop.py",
    ]
    for p in candidates:
        if not p.is_file():
            continue
        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location("tm_shop", p)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                _TM_SHOP_MOD = mod
                return mod
        except Exception as e:
            print(f"[tm-shop] import failed {p}: {e}", flush=True)
    return None


class _TmViewerApiHandler(BaseHTTPRequestHandler):
    server_version = "TicketmasterSignIn/1.0"

    def log_message(self, fmt: str, *args) -> None:
        return

    def parse_request(self) -> bool:
        ok = super().parse_request()
        if _registry_http_debug():
            print(
                "[tm-viewer-api][http-debug] parse_request "
                f"ok={ok} command={getattr(self, 'command', None)!r} "
                f"path={getattr(self, 'path', None)!r} "
                f"request_version={getattr(self, 'request_version', None)!r}",
                flush=True,
            )
        return ok

    def send_error(
        self,
        code: int,
        message: str | None = None,
        explain: str | None = None,
    ) -> None:
        """
        stdlib ``send_error`` emits HTML; stubby/Vercel probes on POST /api/tm-viewer/send-mail expect JSON.
        Older registry copies also called ``send_error(404)`` for unmatched POST — force JSON for POST.
        """
        cmd = getattr(self, "command", None)
        if _registry_http_debug():
            print(
                "[tm-viewer-api][http-debug] send_error "
                f"code={code} command={cmd!r} path={getattr(self, 'path', None)!r}",
                flush=True,
            )
            if cmd == "POST":
                traceback.print_stack(limit=24, file=sys.stderr)
        if cmd == "POST":
            try:
                p = _normalize_tm_viewer_http_path(self._canonical_request_path())
                self._write_json(
                    code,
                    {
                        "ok": False,
                        "error": "post_http_error",
                        "status": code,
                        "path": p,
                        "raw_path": self.path,
                        "via": "tm_viewer_link_registry",
                        "hint": "POST /api/tm-viewer/send-mail or /api/tm-viewer/transfer-to-buyer with JSON body",
                    },
                )
            except Exception as ex:
                print(
                    "[tm-viewer-api] WARN: POST send_error could not emit JSON "
                    f"({ex!r}); falling back to stdlib HTML. "
                    "Often double-response / headers already sent — check other handlers.",
                    file=sys.stderr,
                    flush=True,
                )
                super().send_error(code, message, explain)
            return
        super().send_error(code, message, explain)

    def _canonical_request_path(self) -> str:
        """
        Path only (no query): same rules as health check.
        Handles absolute-form request-target (``http://host:port/path``) from urllib / aiohttp —
        ``urlparse(self.path).path`` alone is wrong for those and breaks POST routing (HTML 404).

        Must parse ``://`` *before* collapsing ``//`` or ``http://`` becomes ``http:/`` and path is garbage.
        """
        try:
            sp = (self.path or "").replace("\ufeff", "").strip()
            if not sp:
                return "/"
            if "?" in sp:
                sp = sp.split("?", 1)[0]
            if "#" in sp:
                sp = sp.split("#", 1)[0]
            sp = (urllib.parse.unquote(sp) or "/").strip()
            sp = sp.replace("\u2013", "-").replace("\u2014", "-")
            if "://" in sp:
                sp = (urllib.parse.urlparse(sp).path or "/").strip()
            while "//" in sp:
                sp = sp.replace("//", "/")
            if not sp.startswith("/"):
                sp = "/" + sp.lstrip("/")
            return sp or "/"
        except Exception:
            return "/"

    def _read_json_body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            n = 0
        if n <= 0 or n > 65536:
            return {}
        raw = self.rfile.read(n)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _read_json_body_large(self, max_bytes: int) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            n = 0
        if n <= 0 or n > max_bytes:
            return {}
        raw = self.rfile.read(n)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_json(self, status: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for k, v in _cors_headers().items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _handle_shop_listings(self) -> None:
        mod = _import_tm_shop_module()
        if mod is None:
            self._write_json(503, {"ok": False, "error": "shop_module_missing"})
            return
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        try:
            limit = int((qs.get("limit") or ["2000"])[0])
        except (TypeError, ValueError):
            limit = 2000
        try:
            offset = int((qs.get("offset") or ["0"])[0])
        except (TypeError, ValueError):
            offset = 0
        if limit > 0:
            limit = max(1, min(limit, 2000))
        else:
            limit = 2000
        offset = max(0, offset)
        events_only = (qs.get("events_only") or [""])[0].strip().lower() in ("1", "true", "yes")
        q = (qs.get("q") or [""])[0].strip()
        event_key = (qs.get("event_key") or [""])[0].strip()
        self._write_json(
            200,
            mod.shop_listings(
                limit=limit, offset=offset, events_only=events_only, q=q, event_key=event_key
            ),
        )

    def _handle_shop_event_images(self) -> None:
        mod = _import_tm_shop_module()
        if mod is None:
            self._write_json(503, {"ok": False, "error": "shop_module_missing"})
            return
        body = self._read_json_body()
        self._write_json(200, mod.shop_resolve_event_images(body))

    def _handle_shop_orders(self) -> None:
        mod = _import_tm_shop_module()
        if mod is None:
            self._write_json(503, {"ok": False, "error": "shop_module_missing"})
            return
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        token = urllib.parse.unquote((qs.get("token") or [""])[0]).strip()
        em = _session_email_for_token(token)
        if not em:
            self._write_json(
                401,
                {"ok": False, "error": "auth_required", "hint": "Sign in to view order history"},
            )
            return
        _touch_session(token)
        self._write_json(200, mod.shop_orders_for_email(em))

    def _handle_shop_account(self) -> None:
        mod = _import_tm_shop_module()
        if mod is None:
            self._write_json(503, {"ok": False, "error": "shop_module_missing"})
            return
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        token = urllib.parse.unquote((qs.get("token") or [""])[0]).strip()
        em = _session_email_for_token(token)
        if not em:
            self._write_json(401, {"ok": False, "error": "auth_required"})
            return
        _touch_session(token)
        if self.command == "GET":
            self._write_json(200, mod.shop_account_get(em))
            return
        if self.command == "POST":
            body = self._read_json_body()
            self._write_json(200, mod.shop_account_save(em, body))
            return
        self._write_json(405, {"ok": False, "error": "method_not_allowed"})

    def _handle_shop_sync(self) -> None:
        mod = _import_tm_shop_module()
        if mod is None:
            self._write_json(503, {"ok": False, "error": "shop_module_missing"})
            return
        secret = (os.environ.get("SHOP_SYNC_SECRET") or os.environ.get("SHOP_PURCHASE_SECRET") or "").strip()
        if secret:
            got = (self.headers.get("X-Shop-Secret") or self.headers.get("x-shop-secret") or "").strip()
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            qsec = (qs.get("secret") or [""])[0].strip()
            if got != secret and qsec != secret:
                self._write_json(403, {"ok": False, "error": "forbidden"})
                return
        if not hasattr(mod, "shop_sync_inventory"):
            self._write_json(503, {"ok": False, "error": "sync_unavailable"})
            return
        self._write_json(200, mod.shop_sync_inventory())

    def _handle_shop_health(self) -> None:
        mod = _import_tm_shop_module()
        if mod is None:
            self._write_json(503, {"ok": False, "error": "shop_module_missing"})
            return
        stats = None
        try:
            mdb = __import__("tixx_marketplace_db", fromlist=["marketplace_stats"])
            mdb.init_db()
            stats = mdb.marketplace_stats()
        except Exception:
            try:
                from ticketmaster import tixx_marketplace_db as mdb2  # type: ignore
                mdb2.init_db()
                stats = mdb2.marketplace_stats()
            except Exception:
                stats = None
        self._write_json(200, {"ok": True, "marketplace": stats, "shop": bool(mod)})

    def _handle_shop_post(self, action: str) -> None:
        mod = _import_tm_shop_module()
        if mod is None:
            self._write_json(503, {"ok": False, "error": "shop_module_missing"})
            return
        hdrs = {k: v for k, v in self.headers.items()}
        if not mod.shop_check_secret(hdrs):
            self._write_json(403, {"ok": False, "error": "forbidden"})
            return
        body = self._read_json_body()
        lid = str(body.get("listing_id") or body.get("slug") or "").strip()
        email = str(body.get("buyer_email") or body.get("email") or "").strip()
        name = str(body.get("buyer_name") or body.get("name") or "").strip()
        if action == "purchase":
            status, payload = mod.shop_purchase(lid, email, name)
        else:
            status, payload = mod.shop_checkout(lid, email, name)
        self._write_json(status, payload)

    def _reminder_db_path(self) -> Path:
        # Force reminder DB path to tm.bz on .195.
        return Path(
            r"C:\Users\Administrator\Desktop\Stubhub\stubhub\tm.bz\tm_reminder_db.json"
        )

    def _load_reminder_db_local(self) -> dict:
        p = self._reminder_db_path()
        out = {"subs": {}, "refs": {}}
        if not p.is_file():
            return out
        try:
            raw = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            if isinstance(raw, dict):
                if isinstance(raw.get("subs"), dict):
                    out["subs"] = raw.get("subs")
                if isinstance(raw.get("refs"), dict):
                    out["refs"] = raw.get("refs")
        except Exception:
            pass
        return out

    def _save_reminder_db_local(self, db: dict) -> None:
        p = self._reminder_db_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(db, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(p)

    def _reminder_public_origin(self) -> str:
        return (os.environ.get("TICKETS_PUBLIC_ORIGIN") or "https://tixx.pw").strip().rstrip("/")

    def _reminder_unsub_footer(self, sub_id: str, token: str) -> str:
        href = (
            self._reminder_public_origin()
            + "/api/ticket-reminders/unsubscribe?sub="
            + urllib.parse.quote(sub_id, safe="")
            + "&t="
            + urllib.parse.quote(token, safe="")
        )
        return (
            '<p style="color:#64748b;font-size:13px;margin-top:24px">'
            f'<a href="{escape(href, quote=True)}">Unsubscribe</a> from these reminders.</p>'
        )

    def _send_reminder_milestone_local(self, sub_id: str, sub: dict, label: str) -> tuple[bool, str]:
        em = _normalize_email(str(sub.get("email") or ""))
        if not em:
            return False, "missing_email"
        title_raw = str(sub.get("eventTitle") or "Your event")
        title = escape(title_raw, quote=False)
        when = ""
        try:
            from datetime import datetime, timezone

            ms = int(str(sub.get("eventStartMs") or "0"))
            when = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%a, %d %b %Y %H:%M:%S UTC")
        except Exception:
            when = str(sub.get("eventStartMs") or "")
        ticket_url = str(sub.get("ticketUrl") or "").strip()
        ticket_html = (
            f'<p><a href="{escape(ticket_url, quote=True)}">Open your ticket</a></p>' if ticket_url else ""
        )
        tok = str(sub.get("unsubToken") or "")

        subject = ""
        html_body = ""
        if label == "24h":
            subject = f"Reminder: {title_raw or 'Your event'} is tomorrow"
            html_body = (
                "<p>Hi,</p>"
                f"<p>This is a heads-up that <strong>{title}</strong> starts soon (<strong>{escape(when, quote=False)}</strong>).</p>"
                "<p>Plan to arrive early: allow time for traffic, parking, and venue security.</p>"
                "<p>Have your ticket barcode ready before you reach the entrance.</p>"
                + ticket_html
                + self._reminder_unsub_footer(sub_id, tok)
            )
        elif label == "3h":
            subject = f"Soon: {title_raw or 'Your event'} — doors opening"
            html_body = (
                "<p>Hi,</p>"
                f"<p><strong>{title}</strong> is coming up in a few hours ({escape(when, quote=False)}).</p>"
                "<p><strong>Be on time.</strong> Doors may close to late arrivals per venue policy.</p>"
                + ticket_html
                + self._reminder_unsub_footer(sub_id, tok)
            )
        elif label == "1h":
            subject = f"URGENT: {title_raw or 'Your event'} — scan within the hour"
            html_body = (
                "<p>Hi,</p>"
                f"<p><strong>Final notice.</strong> <strong>{title}</strong> is within about one hour ({escape(when, quote=False)}).</p>"
                "<p>You must arrive and have your ticket scanned at least one hour before start.</p>"
                + ticket_html
                + self._reminder_unsub_footer(sub_id, tok)
            )
        elif label == "date-00":
            subject = f"Reminder: {title_raw or 'Your event'} is today"
            html_body = (
                "<p>Hi,</p>"
                f"<p><strong>{title}</strong> is scheduled for today.</p>"
                "<p>This is your first same-day reminder.</p>"
                + ticket_html
                + self._reminder_unsub_footer(sub_id, tok)
            )
        elif label == "date-12":
            subject = f"Today: {title_raw or 'Your event'} — midday reminder"
            html_body = (
                "<p>Hi,</p>"
                f"<p><strong>{title}</strong> is happening today.</p>"
                "<p>Midday check-in reminder.</p>"
                + ticket_html
                + self._reminder_unsub_footer(sub_id, tok)
            )
        elif label == "date-18":
            subject = f"Final same-day reminder: {title_raw or 'Your event'}"
            html_body = (
                "<p>Hi,</p>"
                f"<p><strong>{title}</strong> is tonight.</p>"
                "<p>Final reminder to head out with your barcode ready.</p>"
                + ticket_html
                + self._reminder_unsub_footer(sub_id, tok)
            )
        if not subject or not html_body:
            return False, "bad_label"
        return _send_viewer_html_email(em, subject, html_body)

    def _run_ticket_reminders_cron_local(self) -> None:
        secret = (os.environ.get("CRON_SECRET") or "").strip()
        if secret:
            hdr = (self.headers.get("Authorization") or "").strip()
            tok = hdr[7:].strip() if hdr.lower().startswith("bearer ") else ""
            if not tok or not secrets.compare_digest(tok, secret):
                self._write_json(401, {"ok": False, "error": "cron_unauthorized"})
                return

        db = self._load_reminder_db_local()
        subs = db.get("subs") if isinstance(db.get("subs"), dict) else {}
        now_ms = int(time.time() * 1000)

        sent24 = sent3 = sent1 = 0
        sentDate00 = sentDate12 = sentDate18 = 0
        skipped = cleaned = 0
        dirty = False

        for sub_id in list(subs.keys()):
            sub = subs.get(sub_id)
            if not isinstance(sub, dict):
                skipped += 1
                continue
            if str(sub.get("unsubscribed") or "0") == "1":
                skipped += 1
                continue
            if not _normalize_email(str(sub.get("email") or "")):
                skipped += 1
                continue

            try:
                t_ms = int(str(sub.get("eventStartMs") or "0"))
            except Exception:
                skipped += 1
                continue

            mode = str(sub.get("reminderMode") or "event_time")
            rdate = str(sub.get("reminderDate") or "")

            if mode == "date_slots" and re.match(r"^\d{4}-\d{2}-\d{2}$", rdate):
                from datetime import datetime, timezone

                try:
                    d0 = int(datetime.fromisoformat(rdate + "T00:00:00+00:00").timestamp() * 1000)
                    d12 = int(datetime.fromisoformat(rdate + "T12:00:00+00:00").timestamp() * 1000)
                    d18 = int(datetime.fromisoformat(rdate + "T18:00:00+00:00").timestamp() * 1000)
                    dend = int(datetime.fromisoformat(rdate + "T23:59:59+00:00").timestamp() * 1000)
                except Exception:
                    skipped += 1
                    continue

                if now_ms > dend + 2 * 3600000:
                    subs.pop(sub_id, None)
                    for k in list((db.get("refs") or {}).keys()):
                        if db["refs"].get(k) == sub_id:
                            db["refs"].pop(k, None)
                    cleaned += 1
                    dirty = True
                    continue
                ok, _ = (True, "")
                if now_ms >= d0 and str(sub.get("sentDate00") or "0") != "1":
                    ok, _ = self._send_reminder_milestone_local(sub_id, sub, "date-00")
                    if ok:
                        sub["sentDate00"] = "1"
                        sentDate00 += 1
                        dirty = True
                if now_ms >= d12 and str(sub.get("sentDate12") or "0") != "1":
                    ok, _ = self._send_reminder_milestone_local(sub_id, sub, "date-12")
                    if ok:
                        sub["sentDate12"] = "1"
                        sentDate12 += 1
                        dirty = True
                if now_ms >= d18 and str(sub.get("sentDate18") or "0") != "1":
                    ok, _ = self._send_reminder_milestone_local(sub_id, sub, "date-18")
                    if ok:
                        sub["sentDate18"] = "1"
                        sentDate18 += 1
                        dirty = True
                continue

            ms_left = t_ms - now_ms
            if ms_left < -7200000:
                subs.pop(sub_id, None)
                for k in list((db.get("refs") or {}).keys()):
                    if db["refs"].get(k) == sub_id:
                        db["refs"].pop(k, None)
                cleaned += 1
                dirty = True
                continue
            if ms_left <= 0:
                continue
            if ms_left <= 24 * 3600000 and str(sub.get("sent24") or "0") != "1":
                ok, _ = self._send_reminder_milestone_local(sub_id, sub, "24h")
                if ok:
                    sub["sent24"] = "1"
                    sent24 += 1
                    dirty = True
            if (
                ms_left <= 3 * 3600000
                and str(sub.get("sent3") or "0") != "1"
                and str(sub.get("sent6") or "0") != "1"
            ):
                ok, _ = self._send_reminder_milestone_local(sub_id, sub, "3h")
                if ok:
                    sub["sent3"] = "1"
                    sent3 += 1
                    dirty = True
            if ms_left <= 1 * 3600000 and str(sub.get("sent1") or "0") != "1":
                ok, _ = self._send_reminder_milestone_local(sub_id, sub, "1h")
                if ok:
                    sub["sent1"] = "1"
                    sent1 += 1
                    dirty = True

        if dirty:
            try:
                self._save_reminder_db_local(db)
            except OSError as e:
                self._write_json(500, {"ok": False, "error": "reminder_db_write_failed", "detail": str(e)[:240]})
                return

        self._write_json(
            200,
            {
                "ok": True,
                "storage": "file_db",
                "scanned": len(subs),
                "sent24": sent24,
                "sent3": sent3,
                "sent1": sent1,
                "sentDate00": sentDate00,
                "sentDate12": sentDate12,
                "sentDate18": sentDate18,
                "skipped": skipped,
                "cleaned": cleaned,
            },
        )

    def _handle_ticket_reminders_unsubscribe_local(self, parsed: urllib.parse.ParseResult) -> None:
        qs = urllib.parse.parse_qs(parsed.query)
        sub_id = urllib.parse.unquote((qs.get("sub") or [""])[0]).strip()
        tok = urllib.parse.unquote((qs.get("t") or [""])[0]).strip()
        if not sub_id or not tok:
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"<p>Invalid unsubscribe link.</p>")
            return
        db = self._load_reminder_db_local()
        subs = db.get("subs") if isinstance(db.get("subs"), dict) else {}
        sub = subs.get(sub_id)
        if not isinstance(sub, dict) or str(sub.get("unsubToken") or "") != tok:
            self.send_response(403)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"<p>This unsubscribe link is invalid or expired.</p>")
            return
        sub["unsubscribed"] = "1"
        sub["updatedMs"] = str(int(time.time() * 1000))
        try:
            self._save_reminder_db_local(db)
        except OSError:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"error")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b"<p>You\xe2\x80\x99re unsubscribed from event reminders for this ticket.</p>")

    def _handle_ticket_reminders_status_local(self, parsed: urllib.parse.ParseResult) -> None:
        qs = urllib.parse.parse_qs(parsed.query)
        gid = re.sub(r"\D", "", urllib.parse.unquote((qs.get("gid") or [""])[0]).strip())[:12]
        slug = re.sub(
            r"[^a-zA-Z0-9_.-]",
            "",
            urllib.parse.unquote((qs.get("slug") or [""])[0]).strip(),
        )[:180]
        if not gid or not slug:
            self._write_json(400, {"ok": False, "error": "missing_gid_or_slug"})
            return
        db = self._load_reminder_db_local()
        refs = db.get("refs") if isinstance(db.get("refs"), dict) else {}
        subs = db.get("subs") if isinstance(db.get("subs"), dict) else {}
        sub_id = str(refs.get(f"{gid}:{slug}") or "").strip()
        has_registered = bool(sub_id and isinstance(subs.get(sub_id), dict))
        self._write_json(200, {"ok": True, "hasRegistered": has_registered, "storage": "file_db"})

    def _forward_ticket_reminder_register(self) -> None:
        """Register reminder email: forward to upstream if configured, else save to local file-db."""
        try:
            cl = int(self.headers.get("Content-Length") or "0")
        except (TypeError, ValueError):
            cl = 0
        if cl <= 0 or cl > 2 * 1024 * 1024:
            self._write_json(400, {"ok": False, "error": "bad_content_length"})
            return
        try:
            body = self.rfile.read(cl)
        except OSError as e:
            self._write_json(
                400, {"ok": False, "error": "read_failed", "detail": str(e)[:200]}
            )
            return

        url = (os.environ.get("TM_REMINDER_REGISTER_FORWARD_URL") or "").strip()
        if not url:
            self._save_ticket_reminder_local(body)
            return

        req = urllib.request.Request(url, data=body, method="POST")
        ct_in = (self.headers.get("Content-Type") or "").strip()
        req.add_header("Content-Type", ct_in if ct_in else "application/json")

        secret = (
            (os.environ.get("TM_REMINDER_REGISTER_SECRET") or "").strip()
            or (os.environ.get("REMINDER_REGISTER_SECRET") or "").strip()
        )
        incoming_auth = (self.headers.get("Authorization") or "").strip()
        if secret:
            req.add_header("Authorization", f"Bearer {secret}")
        elif incoming_auth:
            req.add_header("Authorization", incoming_auth)

        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                resp_body = resp.read()
                self.send_response(resp.getcode())
                rct = resp.headers.get("Content-Type") or "application/json; charset=utf-8"
                self.send_header("Content-Type", rct)
                self.send_header("Content-Length", str(len(resp_body)))
                for k, v in _cors_headers().items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp_body)
        except urllib.error.HTTPError as e:
            try:
                payload = e.read()
            except Exception:
                payload = b'{"ok":false,"error":"upstream"}'
            self.send_response(e.code)
            ect = ""
            try:
                ect = e.headers.get("Content-Type") or ""
            except Exception:
                pass
            self.send_header(
                "Content-Type", ect if ect else "application/json; charset=utf-8"
            )
            self.send_header("Content-Length", str(len(payload)))
            for k, v in _cors_headers().items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(payload)
        except Exception as e:
            self._write_json(
                502,
                {
                    "ok": False,
                    "error": "reminder_forward_failed",
                    "detail": str(e)[:400],
                },
            )

    def _save_ticket_reminder_local(self, raw_body: bytes) -> None:
        """Fallback reminder registration storage in local JSON DB (tm.bz)."""
        try:
            body = json.loads(raw_body.decode("utf-8", errors="replace"))
        except Exception:
            self._write_json(400, {"ok": False, "error": "invalid_json"})
            return
        if not isinstance(body, dict):
            self._write_json(400, {"ok": False, "error": "invalid_json"})
            return

        email = _normalize_email(str(body.get("email") or ""))
        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
            self._write_json(400, {"ok": False, "error": "invalid_email"})
            return

        reminder_mode_raw = str(body.get("reminderMode") or "").strip().lower()
        reminder_mode = "date_slots" if reminder_mode_raw == "date_slots" else "event_time"
        reminder_date = str(body.get("reminderDate") or "").strip()
        event_start_iso = str(body.get("eventStartIso") or "").strip()
        event_title = str(body.get("eventTitle") or "Your event").strip()[:500]
        gid = re.sub(r"\D", "", str(body.get("gid") or ""))[:12] or "0"
        slug = re.sub(r"[^a-zA-Z0-9_.-]", "", str(body.get("slug") or "").strip())[:180]
        ticket_url = str(body.get("ticketUrl") or "").strip()[:2048]

        from datetime import datetime, timezone

        event_ms: int | None = None
        schedule_ok = True
        if reminder_mode == "date_slots":
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", reminder_date):
                schedule_ok = False
            try:
                if schedule_ok:
                    dt = datetime.fromisoformat(reminder_date + "T18:00:00+00:00")
                    event_ms = int(dt.timestamp() * 1000)
            except Exception:
                event_ms = None
        else:
            try:
                s = event_start_iso
                dt = datetime.fromisoformat(s.replace("Z", "+00:00") if s.endswith("Z") else s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                event_ms = int(dt.astimezone(timezone.utc).timestamp() * 1000)
            except Exception:
                event_ms = None
        if not isinstance(event_ms, int):
            # Still save email even when schedule metadata is missing; customer can resubmit
            # after date/time patching and we will update in place.
            event_ms = 0
            schedule_ok = False

        db_path_env = (os.environ.get("TM_REMINDER_FILE_DB") or "").strip()
        if db_path_env:
            db_path = Path(db_path_env).expanduser()
            if not db_path.is_absolute():
                db_path = Path.cwd() / db_path
            try:
                db_path = db_path.resolve()
            except OSError:
                db_path = db_path.expanduser()
        else:
            try:
                db_path = _registry_path().resolve().parent / "tm_reminder_db.json"
            except OSError:
                db_path = _registry_path().parent / "tm_reminder_db.json"

        db = {"subs": {}, "refs": {}}
        if db_path.is_file():
            try:
                raw = json.loads(db_path.read_text(encoding="utf-8", errors="replace"))
                if isinstance(raw, dict):
                    db["subs"] = raw.get("subs") if isinstance(raw.get("subs"), dict) else {}
                    db["refs"] = raw.get("refs") if isinstance(raw.get("refs"), dict) else {}
            except Exception:
                pass

        rk = f"{gid}:{slug}"
        sub_id = str(db["refs"].get(rk) or "").strip()
        existing = db["subs"].get(sub_id) if sub_id else None
        if sub_id and not isinstance(existing, dict):
            db["refs"].pop(rk, None)
            sub_id = ""
            existing = None

        now_ms = int(time.time() * 1000)
        same_event = bool(
            existing
            and str(existing.get("eventStartMs") or "0") == str(event_ms)
            and str(existing.get("reminderMode") or "event_time") == reminder_mode
            and str(existing.get("reminderDate") or "")
            == (reminder_date if reminder_mode == "date_slots" else "")
        )
        if not sub_id:
            sub_id = secrets.token_hex(16)

        unsub_token = (
            str(existing.get("unsubToken") or "").strip()
            if isinstance(existing, dict)
            else ""
        ) or secrets.token_hex(24)

        row = {
            "email": email,
            "gid": gid,
            "slug": slug,
            "eventStartMs": str(event_ms),
            "reminderMode": reminder_mode,
            "reminderDate": reminder_date if reminder_mode == "date_slots" else "",
            "eventTitle": event_title,
            "ticketUrl": ticket_url,
            "sent24": str(existing.get("sent24") or "0") if same_event and existing else "0",
            "sent3": (
                "1"
                if same_event
                and existing
                and (str(existing.get("sent3") or "0") == "1" or str(existing.get("sent6") or "0") == "1")
                else "0"
            ),
            "sent1": str(existing.get("sent1") or "0") if same_event and existing else "0",
            "sentDate00": str(existing.get("sentDate00") or "0") if same_event and existing else "0",
            "sentDate12": str(existing.get("sentDate12") or "0") if same_event and existing else "0",
            "sentDate18": str(existing.get("sentDate18") or "0") if same_event and existing else "0",
            "unsubToken": unsub_token,
            "unsubscribed": str(existing.get("unsubscribed") or "0") if same_event and existing else "0",
            "createdMs": (
                str(existing.get("createdMs") or now_ms)
                if isinstance(existing, dict)
                else str(now_ms)
            ),
            "updatedMs": str(now_ms),
        }
        db["subs"][sub_id] = row
        db["refs"][rk] = sub_id

        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = db_path.with_name(db_path.name + ".tmp")
            tmp.write_text(json.dumps(db, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp.replace(db_path)
        except OSError as e:
            self._write_json(500, {"ok": False, "error": "reminder_db_write_failed", "detail": str(e)[:240]})
            return

        self._write_json(
            200,
            {
                "ok": True,
                "scheduled": schedule_ok,
                "reminderId": sub_id,
                "storage": "file_db",
                "db_path": str(db_path),
                "warning": "" if schedule_ok else "saved_without_schedule_metadata",
            },
        )

    def _health_path_key(self) -> str | None:
        """
        GET /xt/health and /api/tm-viewer/health.

        Use suffix checks only (no regex): some Windows/http.server paths retain ``\\r`` or odd
        whitespace; broad ``except`` here previously hid bugs and always fell through to HTML 404.
        """
        try:
            s = (self.path or "").replace("\ufeff", "").strip()
            if not s:
                return None
            s = s.split("?", 1)[0].split("#", 1)[0]
            s = s.replace("\r", "").replace("\n", "").replace("\\", "/").strip()
            if not s:
                return None
            try:
                s = urllib.parse.unquote(s)
            except Exception:
                pass
            s = s.replace("\r", "").replace("\n", "").strip()
            low = s.lower().rstrip("/")
            if low.endswith("api/tm-viewer/health"):
                return "/api/tm-viewer/health"
            if low.endswith("xt/health") or low == "xt/health":
                return "/xt/health"
        except Exception as e:
            try:
                print(f"[tm-viewer-api] _health_path_key error: {e!r} path={self.path!r}", flush=True)
            except Exception:
                pass
            return None
        return None

    def _handle_xt_ingest(self) -> None:
        """Friend-PC upload: same contract as xt_server.py POST /xt/ingest (multipart tickets + success)."""
        got = (self.headers.get("X-XT-Ingest-Secret") or "").strip()
        if not got or got != _xt_ingest_secret_expected():
            self._write_json(401, {"ok": False, "error": "unauthorized"})
            return
        try:
            cl = int(self.headers.get("Content-Length") or "0")
        except (TypeError, ValueError):
            cl = 0
        max_body = 256 * 1024 * 1024
        if cl <= 0 or cl > max_body:
            self._write_json(400, {"ok": False, "error": "bad_content_length"})
            return
        raw = self.rfile.read(cl)
        ct = (self.headers.get("Content-Type") or "").lower()
        tickets_b: bytes | None = None
        success_b: bytes | None = None

        if "multipart/form-data" in ct:
            fields = _xt_multipart_form_fields(raw, self.headers.get("Content-Type", ""))
            tb = fields.get("tickets")
            sb = fields.get("success")
            tickets_b = tb if tb else None
            success_b = sb if sb else None
        else:
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._write_json(400, {"ok": False, "error": "expected multipart or JSON"})
                return
            if not isinstance(data, dict):
                self._write_json(400, {"ok": False, "error": "expected multipart or JSON"})
                return
            try:
                tickets_b = base64.b64decode(data.get("tickets_b64") or "")
                success_b = base64.b64decode(data.get("success_b64") or "")
            except Exception:
                self._write_json(400, {"ok": False, "error": "invalid base64"})
                return
        if not tickets_b or not success_b:
            self._write_json(400, {"ok": False, "error": "missing tickets or success body"})
            return
        rd = _xt_results_dir_for_ingest()
        try:
            rd.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self._write_json(500, {"ok": False, "error": "mkdir_failed", "detail": str(e)[:200]})
            return
        tpath = rd / "tickets.txt"
        spath = rd / "success.txt"
        try:
            tpath.write_bytes(tickets_b)
            spath.write_bytes(success_b)
        except OSError as e:
            self._write_json(500, {"ok": False, "error": "write_failed", "detail": str(e)[:200]})
            return
        print(
            f"[xt-ingest] wrote tickets+success -> {rd} ({len(tickets_b)} + {len(success_b)} B); running generate...",
            flush=True,
        )
        gen_py = _xt_generate_script_for_ingest()
        if not gen_py.is_file():
            self._write_json(
                500,
                {"ok": False, "error": "generate script missing", "path": str(gen_py)},
            )
            return
        csv_abs = str(_xt_stock_csv_for_ingest().resolve())
        try:
            Path(csv_abs).parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        env = os.environ.copy()
        env["VAULT_SECURE_PASS_STOCK_FILE"] = csv_abs
        env["TM_STUBHUB_STOCK_CSV"] = csv_abs
        env["XT_STOCK_CSV"] = csv_abs
        env["XT_DATA_DIR"] = str(_XT_DATA_DIR.resolve())
        static_root = (os.environ.get("TM_VIEWER_PASSES_STATIC_DIR") or "").strip() or str(
            (_XT_DATA_DIR / "viewer_passes_static").resolve()
        )
        env["TM_VIEWER_PASSES_STATIC_DIR"] = static_root
        api_base = _xt_tm_viewer_api_base_for_ingest()
        env["VAULT_TM_VIEWER_API_BASE"] = api_base
        env["TM_VIEWER_BACKEND_URL"] = api_base
        env["TM_VIEWER_PUBLIC_SITE"] = _xt_viewer_public_for_ingest()
        env["TM_VIEWER_LINKS_APPEND_DIR"] = str(rd.resolve())
        # --direct: call run_generate in the child process (no HTTP POST back to this server).
        # Without it, urllib POST to /api/tm-viewer/generate often fails on Windows with
        # ConnectionAbortedError / WinError 10053 while the parent handler is still busy.
        cmd = [
            sys.executable,
            str(gen_py),
            "--direct",
            "--results-dir",
            str(rd.resolve()),
        ]
        cwd = str(gen_py.parent)
        try:
            tout = int(os.environ.get("XT_GENERATE_TIMEOUT_SEC") or "3600")
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=max(60, tout),
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            self._write_json(504, {"ok": False, "error": "generate timeout"})
            return
        tail = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()[-4000:]
        if proc.returncode != 0:
            self._write_json(
                502,
                {
                    "ok": False,
                    "error": "generate_failed",
                    "detail": (tail[-800:] if tail else "unknown"),
                },
            )
            return
        master_links = str((_XT_DATA_DIR / "links.txt").resolve())
        self._write_json(
            200,
            {
                "ok": True,
                "tickets_path": str(tpath),
                "success_path": str(spath),
                "stock_csv": csv_abs,
                "persist_site_dir": static_root,
                "links_txt": [str((rd / "links.txt").resolve()), master_links],
                "log_tail": tail[-800:],
            },
        )

    def _try_serve_pass_html(self, path: str, access_q: str = "") -> bool:
        """Serve GET /tickets/:gid/:slug(.html). Transferred passes: stub unless ``access`` matches buyer token."""
        root = _passes_static_root()
        if not root:
            tm_viewer_debug_log(
                "GET /tickets — NO STATIC ROOT (Vercel will show 'Pass HTML not found on VPS')",
                "TM_VIEWER_PASSES_STATIC_DIR is unset or not a directory on THIS host.\n"
                f"  env raw: {repr((os.environ.get('TM_VIEWER_PASSES_STATIC_DIR') or '').strip())}\n"
                "  Fix: set TM_VIEWER_PASSES_STATIC_DIR to the folder that contains tickets/<gid>/*.html "
                "(same folder as watch / merge). Restart this API.",
            )
            return False
        m = re.match(r"^/tickets/(\d{1,8})/([a-zA-Z0-9_.-]{1,220})(?:\.html)?/?$", path or "")
        if not m:
            return False
        gid, slug = m.group(1), m.group(2)
        if slug.lower().endswith(".html"):
            slug = slug[:-5]
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,220}", slug):
            self.send_error(404)
            return True
        rel_check = f"tickets/{gid}/{slug}.html"
        try:
            root_r = root.resolve()
        except OSError:
            self.send_error(500)
            return True

        def _write_transfer_stub_bytes(buyer_disp: str) -> None:
            data = _html_transfer_stub_page(buyer_display=buyer_disp)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for k, v in _cors_headers().items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        buyer_row = transfer_state_for_buyer_pass_slug(gid, slug)
        if buyer_row:
            pk_buyer, st_buyer = buyer_row
            slug_now = (slug or "").strip()
            with _transfer_state_lock:
                full_row = _load_transfer_state().get(pk_buyer)
            fr = full_row if isinstance(full_row, dict) else {}
            cur_bslug = (str(fr.get("buyer_pass_slug") or "")).strip()
            # Re-transfer: old buyer link + token still matches history, but shadow is the
            # live pass for the *current* buyer — only serve shadow for the active slug.
            slug_superseded = bool(cur_bslug and slug_now != cur_bslug)
            expect_b = str(st_buyer.get("buyer_access_token") or "").strip()
            got_q = (access_q or "").strip()
            b_tok_ok = False
            if expect_b and got_q and len(expect_b) == len(got_q):
                try:
                    b_tok_ok = secrets.compare_digest(expect_b, got_q)
                except (TypeError, ValueError):
                    b_tok_ok = False
            if (not slug_superseded) and b_tok_ok:
                sp_b = _shadow_html_path_for_key(root_r, pk_buyer)
                if sp_b is not None and sp_b.is_file():
                    try:
                        data_b = sp_b.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.send_header("Content-Length", str(len(data_b)))
                        self.send_header("Cache-Control", "no-store")
                        for k, v in _cors_headers().items():
                            self.send_header(k, v)
                        self.end_headers()
                        self.wfile.write(data_b)
                        return True
                    except OSError:
                        pass
            if slug_superseded:
                bd = _mask_email_for_display(str(fr.get("transferred_to") or ""))
            else:
                bd = _mask_email_for_display(str(st_buyer.get("transferred_to") or ""))
            _write_transfer_stub_bytes(bd)
            return True

        ts_early, ts_canonical_pk = transfer_state_and_key_for_pass_url(gid, slug)
        transferred = (
            isinstance(ts_early, dict)
            and (str(ts_early.get("transferred_to") or "")).strip()
        )
        buyer_ok = False
        if transferred:
            expect_tok = str(ts_early.get("buyer_access_token") or "").strip()
            got = (access_q or "").strip()
            if expect_tok and got and len(expect_tok) == len(got):
                try:
                    buyer_ok = secrets.compare_digest(expect_tok, got)
                except (TypeError, ValueError):
                    buyer_ok = False
        slug_split = (
            (str(ts_early.get("buyer_pass_slug") or "")).strip()
            if transferred and isinstance(ts_early, dict)
            else ""
        )
        if transferred and slug_split:
            buyer_disp = _mask_email_for_display(str(ts_early.get("transferred_to") or ""))
            _write_transfer_stub_bytes(buyer_disp)
            return True
        if transferred and not buyer_ok:
            buyer_disp = _mask_email_for_display(str(ts_early.get("transferred_to") or ""))
            _write_transfer_stub_bytes(buyer_disp)
            return True
        if transferred and buyer_ok:
            pk = ts_canonical_pk or _ticket_path_registry_key(rel_check)
            if pk:
                sp = _shadow_html_path_for_key(root_r, pk)
                if sp is not None and sp.is_file():
                    try:
                        data = sp.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.send_header("Content-Length", str(len(data)))
                        self.send_header("Cache-Control", "no-store")
                        for k, v in _cors_headers().items():
                            self.send_header(k, v)
                        self.end_headers()
                        self.wfile.write(data)
                        return True
                    except OSError:
                        pass
            buyer_disp = _mask_email_for_display(str(ts_early.get("transferred_to") or ""))
            _write_transfer_stub_bytes(buyer_disp)
            return True
        try:
            primary = (root_r / "tickets" / gid / f"{slug}.html").resolve()
            primary.relative_to(root_r)
        except (OSError, ValueError):
            self.send_error(403)
            return True
        resolved, alias_note = _resolve_pass_html_file(root_r, gid, slug)
        if resolved is None:
            r_sl, n_sl = _resolve_pass_html_via_slug_redirect(root_r, slug)
            if r_sl is not None:
                resolved, alias_note = r_sl, n_sl
        if resolved is None:
            gonly = _find_gid_singleton_pass_html(root_r, gid)
            if gonly:
                try:
                    rel_g = gonly.relative_to(root_r)
                except ValueError:
                    rel_g = gonly
                resolved = gonly
                alias_note = (
                    f"tickets/{gid}/ singleton: requested slug {slug!r} missing; sole file in folder is "
                    f"{rel_g.as_posix()} — update customer link to that slug after regenerate."
                )
        if resolved is None:
            only = _find_singleton_pass_html(root_r)
            if only:
                try:
                    rel_only = only.relative_to(root_r)
                except ValueError:
                    rel_only = only
                resolved = only
                alias_note = (
                    f"singleton fallback: requested /tickets/{gid}/{slug} (missing/stale); "
                    f"only one pass on disk — served {rel_only.as_posix()}. "
                    f"Update delivery links to https://…/{rel_only.with_suffix('').as_posix()} when possible."
                )
        did_regen = False
        if resolved is None and _regenerate_on_pass_miss_enabled():
            _signin_log(
                f"[ticketmaster-pass] missing tickets/{gid}/{slug}.html — running generate from watch files…"
            )
            with _generate_pipeline_lock:
                _watch_run_generate()
            did_regen = True
            resolved, alias_note = _resolve_pass_html_file(root_r, gid, slug)
            if resolved is None:
                r_sl, n_sl = _resolve_pass_html_via_slug_redirect(root_r, slug)
                if r_sl is not None:
                    resolved, alias_note = r_sl, n_sl
            if resolved is None:
                gonly = _find_gid_singleton_pass_html(root_r, gid)
                if gonly:
                    try:
                        rel_g = gonly.relative_to(root_r)
                    except ValueError:
                        rel_g = gonly
                    resolved = gonly
                    alias_note = f"tickets/{gid}/ singleton after regen: served {rel_g.as_posix()}"
            if resolved is None:
                only = _find_singleton_pass_html(root_r)
                if only:
                    try:
                        rel_only = only.relative_to(root_r)
                    except ValueError:
                        rel_only = only
                    resolved = only
                    alias_note = (
                        f"singleton fallback after regenerate: requested /tickets/{gid}/{slug}; "
                        f"served {rel_only.as_posix()}"
                    )
        if resolved is None:
            shop_mod = _import_tm_shop_module()
            if shop_mod is not None and hasattr(shop_mod, "fetch_pass_html_upstream"):
                try:
                    proxied = shop_mod.fetch_pass_html_upstream(gid, slug)
                except Exception:
                    proxied = None
                if proxied:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(proxied)))
                    self.send_header("Cache-Control", "no-store")
                    for k, v in _cors_headers().items():
                        self.send_header(k, v)
                    self.end_headers()
                    self.wfile.write(proxied)
                    _signin_log(f"[ticketmaster-pass] upstream proxy served /tickets/{gid}/{slug}")
                    return True
            sample = ""
            tdir = root_r / "tickets" / gid
            pass_count = ""
            try:
                n_pass = len(list((root_r / "tickets").glob("*/*.html")))
                pass_count = f"\n  Total pass HTML files under tickets/*/: {n_pass}"
            except OSError:
                pass
            try:
                if tdir.is_dir():
                    names = sorted(p.name for p in tdir.glob("*.html"))[:24]
                    sample = f"\n  Existing HTML in tickets/{gid}/ ({len(names)} shown): {names}"
                else:
                    sample = f"\n  tickets/{gid}/ is not a directory (exists={tdir.exists()})."
            except OSError as e:
                sample = f"\n  (could not list tickets/{gid}/: {e})"
            tm_viewer_debug_log(
                f"404 GET {path} — missing {primary.name}",
                f"This host: merged passes live under:\n  {root_r}\n"
                f"Expected file:\n  {primary}\n"
                f"exists={primary.exists()} is_file={primary.is_file()}\n"
                f"regenerate_on_miss ran: {did_regen}\n"
                f"TM_VIEWER_WATCH_DIR={repr((os.environ.get('TM_VIEWER_WATCH_DIR') or '').strip())}\n"
                f"TM_VIEWER_PASSES_STATIC_DIR={repr((os.environ.get('TM_VIEWER_PASSES_STATIC_DIR') or '').strip())}"
                f"{pass_count}{sample}\n"
                "\nIf you generate on a different PC than this API, Vercel's TM_PASSES_STATIC_URL must point "
                "HERE — copy tickets/ from the generator machine to this folder, or run watch+API on one host.\n"
                "Tip: old Secure-Pass links used /tickets/1/…; tm_hit_viewer uses tickets/0/ for the first account. "
                "After regenerate, merge updates tm_viewer_pass_slug_aliases.json (old slug → new file). "
                "If still 404, registry on disk before that merge had no row for this seat — use links.txt / stock.",
            )
            self.send_error(404)
            return True
        if alias_note:
            try:
                rel_served = resolved.relative_to(root_r)
            except ValueError:
                rel_served = resolved
            tm_viewer_debug_log(
                f"GET {path} — served via path alias",
                f"{alias_note}\n  served: {rel_served}",
            )
        try:
            data = resolved.read_bytes()
        except OSError:
            self.send_error(500)
            return True
        if transferred and buyer_ok and _TRANSFER_STUB_FILE_MARKER in data[:3000]:
            pk2 = _ticket_path_registry_key(rel_check)
            if pk2:
                sp2 = _shadow_html_path_for_key(root_r, pk2)
                if sp2 is not None and sp2.is_file():
                    try:
                        data = sp2.read_bytes()
                    except OSError:
                        pass
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)
        return True

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        for k, v in _cors_headers().items():
            self.send_header(k, v)
        self.end_headers()

    def do_POST(self) -> None:
        _prune_auth_state()
        path_raw = self._canonical_request_path()
        raw_p = path_raw.rstrip("/") or "/"
        if raw_p == "/xt/ingest":
            _api_trace(f"POST /xt/ingest raw={self.path!r}")
            self._handle_xt_ingest()
            return
        path = _normalize_tm_viewer_http_path(path_raw)
        if _registry_http_debug():
            print(
                "[tm-viewer-api][http-debug] do_POST "
                f"raw_path={self.path!r} canon={path_raw!r} norm={path!r} "
                f"transfer_route={_post_route_match_transfer(path)!r}",
                flush=True,
            )
        _api_trace(f"POST path={path!r} raw={self.path!r}")
        if path == "/api/ticket-reminders/register":
            self._forward_ticket_reminder_register()
            return
        if path == "/api/ticket-reminders/cron":
            self._run_ticket_reminders_cron_local()
            return
        if path == "/api/shop/purchase":
            self._handle_shop_post("purchase")
            return
        if path == "/api/shop/checkout":
            self._handle_shop_post("checkout")
            return
        if path == "/api/shop/event-images":
            self._handle_shop_event_images()
            return
        if path == "/api/shop/account":
            self._handle_shop_account()
            return
        if path == "/api/shop/sync":
            self._handle_shop_sync()
            return
        if path == "/api/tm-viewer/auth/send-otp":
            body = self._read_json_body()
            raw_em = (body.get("email") or "").strip()
            em = _normalize_email(raw_em)
            if not em or "@" not in em or "." not in em.rsplit("@", 1)[-1]:
                self._write_json(400, {"ok": False, "error": "invalid_email"})
                return
            now = time.time()
            with _auth_lock:
                last = float(_otp_last_send.get(em) or 0)
                if now - last < _OTP_RESEND_COOLDOWN_SEC:
                    self._write_json(
                        429,
                        {"ok": False, "error": "rate_limit", "retry_after_sec": int(_OTP_RESEND_COOLDOWN_SEC - (now - last)) + 1},
                    )
                    return
                code = f"{random.randint(0, 999999):06d}"
                _otp_pending[em] = {"code": code, "exp": now + _OTP_TTL_SEC, "fails": 0}
                _otp_last_send[em] = now
            ok, err = _send_otp_email(em, code)
            if not ok:
                with _auth_lock:
                    _otp_pending.pop(em, None)
                self._write_json(502, {"ok": False, "error": "send_failed", "detail": err[:500]})
                return
            self._write_json(200, {"ok": True})
            return
        if path == "/api/tm-viewer/generate":
            try:
                max_body = int(os.environ.get("TM_VIEWER_GENERATE_MAX_BYTES") or str(25 * 1024 * 1024))
            except ValueError:
                max_body = 25 * 1024 * 1024
            data = self._read_json_body_large(max_body)
            if not data:
                self._write_json(
                    413,
                    {"ok": False, "error": "body_too_large_or_empty", "max_bytes": max_body},
                )
                return
            auth = (self.headers.get("Authorization") or "").strip()
            bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
            sec_field = data.get("secret")
            sec_in = ((sec_field if isinstance(sec_field, str) else "") or bearer).strip()
            if not sec_in or not _const_time_str_eq(
                sec_in, _effective_tm_viewer_generate_secret()
            ):
                self._write_json(401, {"ok": False, "error": "unauthorized"})
                return
            run_generate, imp_detail = _registry_import_run_generate()
            if run_generate is None:
                self._write_json(
                    500,
                    {"ok": False, "error": "import_failed", "detail": imp_detail[:900]},
                )
                return
            def _s(dk: str, ek: str) -> str:
                v = data.get(dk)
                if isinstance(v, str) and v.strip():
                    return v.strip()
                return (os.environ.get(ek) or "").strip()

            persist_d = _s("persist_site_dir", "TM_VIEWER_PASSES_STATIC_DIR") or None
            links_d = _s("links_append_dir", "TM_VIEWER_LINKS_APPEND_DIR") or None
            stock_ov = (
                (data.get("stubhub_stock_csv") if isinstance(data.get("stubhub_stock_csv"), str) else "")
                or (
                    data.get("tm_stubhub_stock_csv")
                    if isinstance(data.get("tm_stubhub_stock_csv"), str)
                    else ""
                )
                or ""
            ).strip()
            ohs = data.get("one_html_per_seat")
            one_seat = bool(ohs) if isinstance(ohs, bool) else str(ohs).strip().lower() in (
                "1",
                "true",
                "yes",
            )
            old_stock = os.environ.get("TM_STUBHUB_STOCK_CSV")
            try:
                if stock_ov:
                    os.environ["TM_STUBHUB_STOCK_CSV"] = stock_ov
                ok, body, ctype, err = run_generate(
                    tickets_text=str(data.get("tickets_text") or ""),
                    success_text=str(data.get("success_text") or ""),
                    public_base=str(data.get("public_base") or ""),
                    output_format=str(data.get("format") or "json"),
                    persist_site_dir=persist_d,
                    links_append_dir=links_d,
                    one_html_per_seat=one_seat,
                )
            finally:
                if stock_ov:
                    if old_stock is None:
                        os.environ.pop("TM_STUBHUB_STOCK_CSV", None)
                    else:
                        os.environ["TM_STUBHUB_STOCK_CSV"] = old_stock
            if not ok:
                self._write_json(
                    400,
                    {"ok": False, "error": "generate_failed", "detail": (err or "")[:8000]},
                )
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in _cors_headers().items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/tm-viewer/auth/verify-otp":
            body = self._read_json_body()
            raw_em = (body.get("email") or "").strip()
            code_in = str(body.get("code") or "").strip().replace(" ", "")
            em = _normalize_email(raw_em)
            if not em or not code_in.isdigit() or len(code_in) < 4 or len(code_in) > 10:
                self._write_json(400, {"ok": False, "error": "invalid_input"})
                return
            now = time.time()
            with _auth_lock:
                row = _otp_pending.get(em)
                if not row or float(row.get("exp") or 0) < now:
                    _otp_pending.pop(em, None)
                    self._write_json(401, {"ok": False, "error": "code_expired"})
                    return
                if int(row.get("fails") or 0) >= _OTP_MAX_VERIFY_FAILS:
                    _otp_pending.pop(em, None)
                    self._write_json(429, {"ok": False, "error": "too_many_attempts"})
                    return
                if code_in != str(row.get("code") or ""):
                    row["fails"] = int(row.get("fails") or 0) + 1
                    self._write_json(401, {"ok": False, "error": "bad_code"})
                    return
                _otp_pending.pop(em, None)
                tok = secrets.token_urlsafe(32)
                _sessions[tok] = {"email": em, "exp": now + _SESSION_TTL_SEC}
                _persist_sessions_locked()
            try:
                from datetime import datetime, timezone

                _append_deliveries_jsonl_line(
                    {
                        "kind": "website_login",
                        "email": em,
                        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }
                )
            except Exception:
                pass
            self._write_json(200, {"ok": True, "token": tok, "email": em})
            return
        if _post_route_match_transfer(path):
            body = self._read_json_body()
            token = str(body.get("token") or "").strip()
            link_secret = str(
                body.get("link_transfer_secret") or body.get("pass_link_secret") or ""
            ).strip()
            if len(token) > 600:
                self._write_json(400, {"ok": False, "error": "invalid_token"})
                return
            if len(link_secret) > 220:
                self._write_json(400, {"ok": False, "error": "invalid_link_secret"})
                return
            if not token and not link_secret:
                if not _allow_path_only_transfer():
                    self._write_json(
                        400,
                        {
                            "ok": False,
                            "error": "auth_or_link_secret_required",
                            "hint": "Send link_transfer_secret from the pass page, or token after OTP sign-in.",
                        },
                    )
                    return
            to_raw = str(body.get("to_email") or body.get("buyer_email") or "").strip()
            path_raw = str(body.get("path") or "").strip()
            path_in = path_raw.split("#", 1)[0].split("?", 1)[0].strip()
            buyer_name = str(body.get("buyer_name") or "").strip()
            to_buyer = _normalize_email(to_raw)
            if (
                not to_buyer
                or "@" not in to_buyer
                or "." not in to_buyer.rsplit("@", 1)[-1]
            ):
                self._write_json(400, {"ok": False, "error": "invalid_buyer_email"})
                return
            if len(path_in) > 500:
                self._write_json(400, {"ok": False, "error": "invalid_path"})
                return
            if not path_in and not link_secret:
                self._write_json(400, {"ok": False, "error": "invalid_path"})
                return
            path_norm = registry_ticket_relpath_ok(path_in) if path_in else None
            row: dict | None = None
            em_owner: str | None = None
            session_tok: str | None = None
            registry_bucket_email: str = ""
            rate_limit_seller: str = ""
            used_path_only_disk: bool = False
            if link_secret:
                if path_norm:
                    row, em_owner = _ticket_row_by_link_secret(path_norm, link_secret)
                if row is None:
                    row, em_owner = _ticket_row_by_link_secret_any_path(link_secret)
                    if row is not None:
                        pn_row = registry_ticket_relpath_ok(str(row.get("path") or ""))
                        if pn_row:
                            path_norm = pn_row
                if row is not None and em_owner:
                    registry_bucket_email = em_owner
                    rate_limit_seller = em_owner
            if row is None and token:
                em_sess = _session_email_for_token(token)
                if em_sess:
                    if not path_norm:
                        path_norm = registry_ticket_relpath_ok(path_in) if path_in else None
                    if not path_norm:
                        self._write_json(400, {"ok": False, "error": "invalid_path"})
                        return
                    row = _ticket_row_owned_by_email(em_sess, path_norm)
                    if row is not None:
                        registry_bucket_email = em_sess
                        rate_limit_seller = em_sess
                    else:
                        row = _ticket_row_orphan_bucket(path_norm)
                        if row is not None:
                            registry_bucket_email = _orphan_registry_email()
                            rate_limit_seller = em_sess
                    if row is not None:
                        session_tok = token
            if (not row or not rate_limit_seller) and _allow_path_only_transfer():
                if _path_only_transfer_body_key_ok(body):
                    pn = path_norm or (registry_ticket_relpath_ok(path_in) if path_in else None)
                    if pn and _pass_html_file_resolved_for_norm(pn) is not None:
                        row = _synthetic_ticket_row_for_path_on_disk(pn)
                        path_norm = registry_ticket_relpath_ok(str(row.get("path") or pn)) or pn
                        pk_tag = (_ticket_path_registry_key(path_norm) or "").lower()
                        rate_limit_seller = f"pathdisk:{pk_tag}" if pk_tag else "pathdisk:unknown"
                        registry_bucket_email = ""
                        session_tok = None
                        used_path_only_disk = True
            if not row or not rate_limit_seller:
                self._write_json(
                    403,
                    {"ok": False, "error": "pass_not_found_for_account"},
                )
                return
            if not registry_bucket_email and not used_path_only_disk:
                self._write_json(
                    403,
                    {"ok": False, "error": "pass_not_found_for_account"},
                )
                return
            if _normalize_email(to_buyer) == _normalize_email(rate_limit_seller):
                self._write_json(400, {"ok": False, "error": "cannot_transfer_to_self"})
                return
            pk_existing = _ticket_path_registry_key(str(row.get("path") or path_norm))
            ex_tr = transfer_state_for_path(pk_existing) if pk_existing else None
            if isinstance(ex_tr, dict) and (str(ex_tr.get("transferred_to") or "")).strip():
                prev_buyer = _normalize_email(str(ex_tr.get("transferred_to")))
                if prev_buyer == _normalize_email(to_buyer):
                    if not _transfer_repeat_same_buyer_allowed():
                        self._write_json(200, {"ok": True, "already_transferred": True})
                        return
                elif _transfer_single_recipient_enforced():
                    self._write_json(
                        409,
                        {
                            "ok": False,
                            "error": "already_transferred",
                            "detail": "This pass was already sent to another recipient.",
                        },
                    )
                    return
            gate_key = _transfer_gate_key_session_or_link(
                session_token=session_tok or "",
                path_norm=path_norm,
                link_secret=link_secret,
            )
            ok_gate, gate_why = _transfer_attempt_gate(gate_key, rate_limit_seller)
            if not ok_gate:
                ra = int(
                    float((os.environ.get("TM_VIEWER_TRANSFER_MIN_GAP_SEC") or "1.5").strip() or "1.5")
                    + 0.99
                )
                self._write_json(
                    429,
                    {
                        "ok": False,
                        "error": gate_why or "rate_limited",
                        "retry_after_sec": ra,
                    },
                )
                return
            pub_base = _public_site_base_for_pass_urls()
            buyer_tok = secrets.token_urlsafe(32)
            pk_canon = (
                _ticket_path_registry_key(str(row.get("path") or path_norm)) or ""
            ).strip().lower()
            gid_b = "0"
            if pk_canon:
                pr = _parse_registry_ticket_key_parts(pk_canon)
                if pr:
                    gid_b = pr[0]
            try:
                _psr = _passes_static_root()
                _rr_slug = _psr.resolve() if _psr else None
            except OSError:
                _rr_slug = None
            buyer_pass_slug = _new_buyer_pass_slug(_rr_slug, gid_b)
            pass_url = _viewer_pass_public_url(
                pub_base, f"tickets/{gid_b}/{buyer_pass_slug}.html"
            )
            pass_url = _append_access_query_to_url(pass_url, buyer_tok)
            if not pass_url.startswith("http://") and not pass_url.startswith("https://"):
                self._write_json(500, {"ok": False, "error": "bad_public_base"})
                return
            rec_label = (
                buyer_name.strip()
                if buyer_name.strip()
                else (to_buyer.split("@", 1)[0] or "Customer")
            )
            pers_msg = str(
                body.get("personal_message")
                or body.get("personal_note")
                or body.get("message")
                or ""
            ).strip()[:4000]
            pers_from = str(
                body.get("personal_from_name")
                or body.get("message_from_name")
                or ""
            ).strip()[:120]
            try:
                subj, html_b = _build_buyer_transfer_email_html(
                    recipient_label=rec_label,
                    ticket=row,
                    pass_url=pass_url,
                    personal_message=pers_msg or None,
                    personal_from_name=pers_from or None,
                    registry_relpath=str(row.get("path") or path_norm or ""),
                )
            except OSError as e:
                self._write_json(
                    500,
                    {
                        "ok": False,
                        "error": "template_missing",
                        "detail": str(e)[:500],
                    },
                )
                return
            ok_r, det = _send_viewer_html_email(to_buyer, subj, html_b)
            _api_trace(
                f"transfer-to-buyer ok={ok_r} to={to_buyer!r} detail={(det or '')[:200]!r}"
            )
            if not ok_r:
                self._write_json(
                    502,
                    {"ok": False, "error": "send_failed", "detail": det[:600]},
                )
                return
            _transfer_attempt_mark(gate_key)
            _transfer_success_mark(rate_limit_seller)
            pk_done = _ticket_path_registry_key(str(row.get("path") or path_norm))
            if pk_done:
                try:
                    _transfer_state_set(
                        pk_done,
                        seller=rate_limit_seller,
                        buyer=to_buyer,
                        buyer_access_token=buyer_tok,
                        buyer_pass_slug=buyer_pass_slug,
                        buyer_pass_url=pass_url,
                    )
                except Exception:
                    pass
                try:
                    _transfer_materialize_stub_on_disk(
                        registry_relpath=str(row.get("path") or path_norm),
                        buyer_email=to_buyer,
                    )
                except Exception:
                    pass
            if registry_bucket_email:
                try:
                    _mark_registry_row_transferred(registry_bucket_email, path_norm, to_buyer)
                except Exception:
                    pass
            if session_tok:
                _touch_session(session_tok)
            try:
                from datetime import datetime, timezone

                _append_deliveries_jsonl_line(
                    {
                        "kind": "website_transfer_to_buyer",
                        "seller_account_email": rate_limit_seller,
                        "buyer_email": to_buyer,
                        "path": _ticket_path_for_public_href(str(row.get("path") or "")),
                        "buyer_pass_slug": buyer_pass_slug,
                        "buyer_ticket_path": f"tickets/{gid_b}/{buyer_pass_slug}.html",
                        "pass_url": pass_url,
                        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }
                )
            except Exception:
                pass
            self._write_json(200, {"ok": True})
            return
        print(
            f"[tm-viewer-api] POST 404 unmatched path={path!r} raw={self.path!r}",
            file=sys.stderr,
            flush=True,
        )
        _signin_log(
            f"[ticketmaster-signin] POST 404 path={path!r} raw={self.path!r}"
        )
        # JSON (not send_error HTML) so Vercel proxy does not treat this as python http.server 404.
        self._write_json(
            404,
            {
                "ok": False,
                "error": "unknown_post_route",
                "path": path,
                "raw_path": self.path,
            },
        )

    def do_GET(self) -> None:
        _prune_auth_state()
        _hk = self._health_path_key()
        if _hk:
            self._write_json(
                200,
                {
                    "ok": True,
                    "service": "xt_ingest",
                    "via": "tm_viewer_link_registry",
                    "matched": _hk,
                    "paths": ["/xt/health", "/api/tm-viewer/health"],
                },
            )
            return
        parsed = urllib.parse.urlparse(self.path)
        access_q = urllib.parse.unquote(
            (urllib.parse.parse_qs(parsed.query).get("access") or [""])[0]
        ).strip()
        req_path = _normalize_tm_viewer_http_path(self._canonical_request_path())
        if req_path.rstrip("/") == "/api/ticket-reminders/status":
            self._handle_ticket_reminders_status_local(parsed)
            return
        if req_path.rstrip("/") == "/api/ticket-reminders/cron":
            self._run_ticket_reminders_cron_local()
            return
        if req_path.rstrip("/") == "/api/ticket-reminders/unsubscribe":
            self._handle_ticket_reminders_unsubscribe_local(parsed)
            return
        if self._try_serve_pass_html(req_path, access_q):
            return
        if req_path.rstrip("/") == "/tm_viewer_pass_slug_aliases.json":
            root = _passes_static_root()
            if root:
                merged = _pass_slug_redirects_for_root(root)
                if merged:
                    try:
                        payload = json.dumps({"redirects": merged}, ensure_ascii=False).encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.send_header("Content-Length", str(len(payload)))
                        self.send_header("Cache-Control", "no-store")
                        for k, v in _cors_headers().items():
                            self.send_header(k, v)
                        self.end_headers()
                        self.wfile.write(payload)
                        return
                    except OSError:
                        pass
                ap = root / "tm_viewer_pass_slug_aliases.json"
                if ap.is_file():
                    try:
                        data = ap.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.send_header("Content-Length", str(len(data)))
                        self.send_header("Cache-Control", "no-store")
                        for k, v in _cors_headers().items():
                            self.send_header(k, v)
                        self.end_headers()
                        self.wfile.write(data)
                        return
                    except OSError:
                        pass
            self.send_error(404)
            return
        if req_path.rstrip("/") == "/api/tm-viewer/transfer-lookup":
            need = (os.environ.get("TM_VIEWER_TRANSFER_LOOKUP_SECRET") or "").strip()
            if not need:
                self._write_json(
                    503,
                    {
                        "ok": False,
                        "error": "transfer_lookup_disabled",
                        "hint": "Set TM_VIEWER_TRANSFER_LOOKUP_SECRET on this API host (same value in stubby TM_VIEWER_TRANSFER_LOOKUP_SECRET).",
                    },
                )
                return
            qs = urllib.parse.parse_qs(parsed.query)
            key = urllib.parse.unquote((qs.get("key") or [""])[0]).strip()
            slug_arg = urllib.parse.unquote((qs.get("slug") or [""])[0]).strip()
            if not slug_arg:
                self._write_json(400, {"ok": False, "error": "slug_required"})
                return
            if len(key) != len(need) or not secrets.compare_digest(key, need):
                self._write_json(403, {"ok": False, "error": "forbidden"})
                return
            norm = _transfer_lookup_normalize_slug_arg(slug_arg)
            if not norm:
                self._write_json(400, {"ok": False, "error": "invalid_slug"})
                return
            payload = _transfer_lookup_collect(norm)
            self._write_json(200, payload)
            return
        if req_path.rstrip("/") == "/api/shop/listings":
            self._handle_shop_listings()
            return
        if req_path.rstrip("/") == "/api/shop/orders":
            self._handle_shop_orders()
            return
        if req_path.rstrip("/") == "/api/shop/account":
            self._handle_shop_account()
            return
        if req_path.rstrip("/") == "/api/shop/health":
            self._handle_shop_health()
            return
        if req_path.rstrip("/") == "/api/shop/sync":
            self._handle_shop_sync()
            return
        if req_path.rstrip("/") != "/api/tm-viewer/tickets":
            self._write_json(
                404,
                {
                    "ok": False,
                    "error": "not_found",
                    "via": "tm_viewer_link_registry",
                    "path": self.path,
                    "hint": "GET /xt/health or /api/tm-viewer/tickets?token=… or /api/tm-viewer/transfer-lookup?slug=…&key=…",
                },
            )
            return
        qs = urllib.parse.parse_qs(parsed.query)
        token = urllib.parse.unquote((qs.get("token") or [""])[0]).strip()
        em = _session_email_for_token(token)
        if not em:
            self._write_json(
                401,
                {"ok": False, "error": "auth_required", "hint": "POST /api/tm-viewer/auth/send-otp then verify-otp"},
            )
            return
        _touch_session(token)
        tickets = list_tickets_for_email(em)
        tickets_out = []
        for t in tickets:
            if not isinstance(t, dict):
                continue
            row = dict(t)
            row.pop("link_transfer_secret", None)
            raw_path = str(t.get("path") or "")
            pk = _ticket_path_registry_key(raw_path)
            if pk:
                st = transfer_state_for_path(pk)
                if isinstance(st, dict) and (str(st.get("transferred_to") or "")).strip():
                    row["transferred_to"] = st.get("transferred_to")
                    row["transferred_at"] = st.get("transferred_at")
            if "path" in row:
                row["path"] = _ticket_path_for_public_href(raw_path)
            tickets_out.append(row)
        self._write_json(
            200,
            {
                "ok": True,
                "email": em,
                "tickets": tickets_out,
            },
        )


_api_server: ThreadingHTTPServer | None = None
_api_thread: threading.Thread | None = None
_shop_sync_started = False


def _start_shop_sync_loop() -> None:
    global _shop_sync_started
    if _shop_sync_started:
        return
    if (os.environ.get("SHOP_SYNC_DISABLED") or "").strip().lower() in ("1", "true", "yes"):
        return
    try:
        interval = int(os.environ.get("SHOP_SYNC_INTERVAL_SEC") or "300")
    except ValueError:
        interval = 300
    interval = max(60, interval)

    def _loop() -> None:
        time.sleep(15)
        while True:
            mod = _import_tm_shop_module()
            if mod and hasattr(mod, "shop_sync_inventory"):
                try:
                    out = mod.shop_sync_inventory()
                    if isinstance(out, dict) and out.get("ok"):
                        print(
                            f"[tixx-shop-sync] listings={out.get('listings_synced')} images={out.get('images_resolved')}",
                            flush=True,
                        )
                except Exception as e:
                    print(f"[tixx-shop-sync] error: {e!r}", flush=True)
            time.sleep(interval)

    threading.Thread(target=_loop, name="tixx-shop-sync", daemon=True).start()
    _shop_sync_started = True
    print(f"[tixx-shop-sync] background sync every {interval}s", flush=True)


def tm_viewer_tcp_probe_send_mail_returns_json(
    port: int, *, timeout: float = 4.0, presleep: float = 0.2
) -> tuple[bool, bytes]:
    """
    POST ``/api/tm-viewer/send-mail`` with ``{}`` to ``127.0.0.1:port`` (raw TCP).

    Used by stubby and by ``start_tm_viewer_api_background`` to detect the common Windows
    failure mode: this process binds ``0.0.0.0:port`` but another process already holds
    ``127.0.0.1:port``, so loopback traffic never reaches this registry (HTML 404 from old code).
    """
    import socket

    if presleep > 0:
        time.sleep(presleep)
    bod = b"{}"
    req = (
        b"POST /api/tm-viewer/send-mail HTTP/1.1\r\n"
        b"Host: 127.0.0.1\r\nConnection: close\r\n"
        b"Content-Type: application/json\r\nContent-Length: "
        + str(len(bod)).encode("ascii")
        + b"\r\nUser-Agent: tm-viewer-registry-probe\r\n\r\n"
        + bod
    )
    blob = b""
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout) as sock:
            sock.sendall(req)
            while True:
                chunk = sock.recv(8192)
                if not chunk:
                    break
                blob += chunk
                if len(blob) > 65536:
                    break
    except OSError as e:
        return False, f"probe_connect_error:{e!s}".encode("utf-8", errors="replace")
    head, _, body = blob.partition(b"\r\n\r\n")
    jsonish = (
        b"application/json" in head.lower()
        and b"<!DOCTYPE" not in body[:500]
        and (
            b"invalid_token" in body
            or b"auth_required" in body
            or b"tm_viewer_link_registry" in body
            or b"unknown_post_route" in body
            or b"post_http_error" in body
            or b'"ok"' in body
        )
    )
    return jsonish, blob


def _bootstrap_watch_and_sessions() -> None:
    wd = (os.environ.get("TM_VIEWER_WATCH_DIR") or "").strip()
    if wd:
        try:
            _apply_watch_dir_env_defaults(Path(wd).expanduser().resolve())
        except OSError as e:
            _signin_log(f"[ticketmaster-watch] bad TM_VIEWER_WATCH_DIR: {e}")
    _maybe_infer_passes_static_dir()
    _load_sessions_from_disk()
    _start_watch_thread_if_needed()


def start_tm_viewer_api_background(host: str = "0.0.0.0", port: int = 3919) -> bool:
    """Start ThreadingHTTPServer in a daemon thread. Returns False if already running or bind fails."""
    global _api_server, _api_thread
    if _api_server is not None:
        return True
    _bootstrap_watch_and_sessions()
    try:
        srv = _TmViewerThreadingHTTPServer((host, port), _TmViewerApiHandler)
    except OSError as e:
        print(f"[tm-viewer-api] cannot bind http://{host}:{port}/ — {e!r}", flush=True)
        return False
    print(
        f"[tm-viewer-api] listening http://{host}:{port}/ "
        f'(GET /xt/health — use: curl --noproxy "*" http://127.0.0.1:{port}/xt/health)',
        flush=True,
    )
    print(
        "[tm-viewer-api] POST /api/tm-viewer/send-mail errors return JSON (not HTML). "
        "Windows: this server uses SO_EXCLUSIVEADDRUSE so 0.0.0.0:port and 127.0.0.1:port cannot "
        "split across two processes. Trace: TM_VIEWER_REGISTRY_HTTP_DEBUG=1.",
        flush=True,
    )
    _log_viewer_outbound_email_from_banner()

    def run() -> None:
        srv.serve_forever(poll_interval=0.5)

    th = threading.Thread(target=run, name="tm-viewer-api", daemon=True)
    th.start()
    _api_server = srv
    _api_thread = th
    _start_shop_sync_loop()
    try:
        mod = _import_tm_shop_module()
        if mod is not None and hasattr(mod, "warm_shop_listings_cache"):
            mod.warm_shop_listings_cache()
    except Exception:
        pass
    # Windows: 0.0.0.0:port can bind while 127.0.0.1:port is already taken — loopback then hits the other process.
    hnorm = (host or "").strip()
    if hnorm in ("0.0.0.0", "::"):
        j_ok, prev = tm_viewer_tcp_probe_send_mail_returns_json(port, presleep=0.25)
        if not j_ok:
            print(
                f"[tm-viewer-api] FATAL: 127.0.0.1:{port} POST /api/tm-viewer/send-mail is NOT this server "
                f"(got non-registry JSON/HTML). Bound as {host}:{port} but another process likely owns "
                f"127.0.0.1:{port} — stubby/proxy talk to loopback and hit the wrong listener.\n"
                f"  Fix: stop the other service (e.g. netstat -ano | findstr :{port} then taskkill /PID …) "
                f"or set TM_VIEWER_API_HOST=127.0.0.1 for stubby-embedded API so bind fails if loopback is busy.\n"
                f"  Preview: {prev[:280]!r}",
                flush=True,
            )
    return True


def run_tm_viewer_api_forever(host: str = "0.0.0.0", port: int = 3919) -> None:
    """Block and serve (use from __main__)."""
    _bootstrap_watch_and_sessions()
    try:
        srv = _TmViewerThreadingHTTPServer((host, port), _TmViewerApiHandler)
    except OSError as e:
        print(
            f"[tm-viewer-api] FATAL: cannot bind {host}:{port} — {e!r}. "
            f"Another process may own this port (netstat -ano | findstr :{port}).",
            flush=True,
        )
        raise SystemExit(1) from e
    print(
        f"[tm-viewer-api] listening http://{host}:{port}/ — in another CMD: "
        f'curl --noproxy "*" -sS http://127.0.0.1:{port}/xt/health',
        flush=True,
    )
    print(
        "[tm-viewer-api] POST buyer-email routes return JSON on error. "
        "Deep HTTP trace: TM_VIEWER_REGISTRY_HTTP_DEBUG=1",
        flush=True,
    )
    reg = _registry_path()
    dj_reads = _deliveries_jsonl_read_paths()
    dj_write = _deliveries_jsonl_write_path()
    base = f"http://{host}:{port}"
    src = "deliveries" if _use_deliveries_as_primary() else "registry"
    _signin_log(f"[ticketmaster-signin] GET {base}/api/tm-viewer/tickets?token=...")
    _signin_log(f"[ticketmaster-signin] POST {base}/api/tm-viewer/auth/send-otp")
    _signin_log(f"[ticketmaster-signin] POST {base}/api/tm-viewer/auth/verify-otp")
    _signin_log(f"[ticketmaster-signin] POST {base}/api/tm-viewer/generate (bundle) — on")
    _signin_log(f"[ticketmaster-signin] ticket list source: {src}")
    _signin_log(f"[ticketmaster-signin] registry: {reg}")
    _signin_log(f"[ticketmaster-signin] deliveries JSONL read (merge): {', '.join(str(p) for p in dj_reads)}")
    _signin_log(f"[ticketmaster-signin] deliveries JSONL write (audit): {dj_write}")
    _signin_log(f"[ticketmaster-signin] sessions file: {_sessions_path()}")
    if (os.environ.get("TM_VIEWER_WATCH_DIR") or "").strip():
        ps = (os.environ.get("TM_VIEWER_PASSES_STATIC_DIR") or "").strip()
        _signin_log(f"[ticketmaster-signin] auto-watch: TM_VIEWER_WATCH_DIR (passes merge → {ps or '?'})")
    psr = _passes_static_root()
    if psr:
        _signin_log(f"[ticketmaster-signin] GET /tickets/… HTML from: {psr}")
    else:
        _signin_log(
            "[ticketmaster-signin] [!] No pass static root — set TM_VIEWER_PASSES_STATIC_DIR to the folder "
            "that contains tickets/0/*.html (or keep registry + sufg output in the same folder as this script)."
        )
    _log_viewer_outbound_email_from_banner()
    try:
        mod = _import_tm_shop_module()
        if mod is not None and hasattr(mod, "warm_shop_listings_cache"):
            mod.warm_shop_listings_cache()
    except Exception:
        pass
    srv.serve_forever()


if __name__ == "__main__":
    import argparse
    import os

    ap = argparse.ArgumentParser(
        description="Serve tm_viewer_link_registry.json for the Ticketmaster-style site (CORS-enabled)."
    )
    ap.add_argument("--host", default="0.0.0.0", help="Bind address (default 0.0.0.0)")
    ap.add_argument("--port", type=int, default=3919, help="Port (default 3919)")
    ap.add_argument(
        "--registry",
        default="",
        metavar="PATH",
        help="Absolute path to tm_viewer_link_registry.json (copied from site output or --site-dir)",
    )
    ap.add_argument(
        "--deliveries",
        default="",
        metavar="PATH",
        help="tm_viewer_deliveries.jsonl (default: same folder as registry)",
    )
    ap.add_argument(
        "--watch-dir",
        default="",
        metavar="DIR",
        help="Watch DIR/tickets.txt + DIR/success.txt; auto-run generate when they change (sets passes + registry defaults)",
    )
    ap.add_argument(
        "--materialize-transfer-stubs",
        action="store_true",
        help="For each row in tm_viewer_transfer_state.json with buyer_access_token: move live HTML to "
        "tickets/<gid>/.tm_pass_shadow/ and write stub on the public path (fixes old naked links). Then exit.",
    )
    ap.add_argument(
        "--undo-disk-materialize-stubs",
        action="store_true",
        help="Undo mistaken --materialize when disk fallback stubbed all passes: restore HTML from "
        ".tm_pass_shadow/ and remove transfer state rows from disk-materialize@local. Then exit.",
    )
    ap.add_argument(
        "--passes-dir",
        default="",
        metavar="DIR",
        help="Site root containing tickets/<gid>/*.html — sets TM_VIEWER_PASSES_STATIC_DIR (use if materialize says passes dir missing).",
    )
    args = ap.parse_args()
    if (args.passes_dir or "").strip():
        os.environ["TM_VIEWER_PASSES_STATIC_DIR"] = str(
            Path(args.passes_dir.strip()).expanduser().resolve()
        )
    registry_cli = bool((args.registry or "").strip())
    if registry_cli:
        os.environ["TM_VIEWER_REGISTRY_PATH"] = os.path.abspath(args.registry.strip())
    if (args.deliveries or "").strip():
        os.environ["TM_VIEWER_DELIVERIES_JSONL"] = os.path.abspath(args.deliveries.strip())
    if (args.watch_dir or "").strip():
        os.environ["TM_VIEWER_WATCH_DIR"] = str(Path(args.watch_dir.strip()).expanduser().resolve())
    if args.undo_disk_materialize_stubs:
        _bootstrap_watch_and_sessions()
        n, msgs = undo_disk_fallback_materialize_on_disk()
        for line in msgs:
            print(line, flush=True)
        ps = (os.environ.get("TM_VIEWER_PASSES_STATIC_DIR") or "").strip() or "(unset)"
        print(f"[tm-viewer] undo complete under passes root {ps}", flush=True)
        raise SystemExit(0)
    if args.materialize_transfer_stubs:
        _bootstrap_watch_and_sessions()
        if _IN_XT_PACKAGE:
            _maybe_infer_registry_for_materialize_cli(registry_explicit_cli=registry_cli)
        n, msgs = materialize_all_transfer_stubs_on_disk()
        for line in msgs:
            print(line, flush=True)
        ps = (os.environ.get("TM_VIEWER_PASSES_STATIC_DIR") or "").strip() or "(unset)"
        print(f"[tm-viewer] materialized {n} transfer stub(s) on disk under {ps}", flush=True)
        raise SystemExit(0)
    run_tm_viewer_api_forever(host=args.host, port=args.port)
