"""Victory Live OIDC login via requests (no Selenium)."""
import html
import json
import os
import re
import threading
import time
from http.cookiejar import Cookie
from pathlib import Path
from urllib.parse import parse_qs, quote, urljoin, urlparse

import requests

LOGIN_BASE = "https://login.victorylive.com"
APP_BASE = "https://one.victorylive.com"
ROOT = Path(__file__).resolve().parent
HAR_PATH = ROOT / "one.victorylive.com.har"
LOGIN_HAR_PATH = ROOT / "ticketmaster" / "one.victorylive.com.har"
# Logged-in browser export (deploy/one.victorylive.com.har) — no login POST inside; use for .APAUTH cookies.
HAR_SESSION_CANDIDATES = (
    Path(os.environ.get("VL_HAR_SESSION") or ""),
    ROOT / "data" / "vl_har_cookies.json",
    ROOT / "deploy" / "one.victorylive.com.har",
    ROOT / "one.victorylive.com.har",
)

# Victory Live egress: fixed HTTP proxy on your clean IP (deploy/vl_egress_proxy.py).
# Set VL_PROXY_URL=http://96.126.176.73:8749 on the bot VPS — do not use rotating DC
# proxies for VL (new IP per request looks like scraping and breaks cookie sessions).
DEFAULT_VL_PROXY_URL = "http://96.126.176.73:8749"

# Legacy FlashProxy — only if VL_PROXY_URL unset and VL_PROXY_HOST is set explicitly.
PROXY_HOST = os.environ.get("VL_PROXY_HOST") or ""
PROXY_PORT = int(os.environ.get("VL_PROXY_PORT") or "10000")
PROXY_USER = os.environ.get("VL_PROXY_USER") or ""
PROXY_PASS = os.environ.get("VL_PROXY_PASS") or ""

# Fouad Mahmoud / LUXE — Victory Live (hardcoded for VPS bot; env overrides optional)
DEFAULT_VL_USERNAME = "sales@cashresaletickets.com"
DEFAULT_VL_PASSWORD = "Welcome2026!"

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_VL_OIDC_CLIENT = "OIDC-ServicesMembersSite"

SESSION_PATH = Path(os.environ.get("VL_SESSION_FILE") or ROOT / "data" / "vl_session.json")

_LOCK = threading.Lock()
_MEM_SESSION: requests.Session | None = None
_MEM_USERNAME: str | None = None
_LAST_PROFILE_CHECK = 0.0
_PROFILE_CHECK_INTERVAL_SEC = 90.0


def _vl_proxy_url() -> str | None:
    if os.environ.get("VL_NO_PROXY", "").strip().lower() in ("1", "true", "yes"):
        return None
    explicit = (os.environ.get("VL_PROXY_URL") or "").strip()
    if explicit:
        return explicit
    if PROXY_HOST:
        auth = ""
        if PROXY_USER:
            auth = f"{PROXY_USER}:{PROXY_PASS}@"
        return f"http://{auth}{PROXY_HOST}:{PROXY_PORT}"
    return DEFAULT_VL_PROXY_URL


def _proxy_url_with_auth(url: str) -> str:
    user = (os.environ.get("VL_PROXY_USER") or "").strip()
    pw = (os.environ.get("VL_PROXY_PASS") or "").strip()
    if not user:
        return url
    rest = url.split("://", 1)
    if len(rest) != 2 or "@" in rest[1]:
        return url
    scheme, hostpart = rest
    return f"{scheme}://{quote(user, safe='')}:{quote(pw, safe='')}@{hostpart}"


def proxy_dict() -> dict[str, str]:
    url = _vl_proxy_url()
    if not url:
        return {}
    url = _proxy_url_with_auth(url)
    return {"http": url, "https": url}


def cookies_only_mode() -> bool:
    """
    When true, login() prefers mem / disk / HAR cookies and skips proactive OIDC.
    If cookies are missing or invalid, one OIDC login runs **without** egress proxy,
    then cookies are saved and API traffic uses the configured VL proxy (96 egress).
    """
    return os.environ.get("VL_COOKIES_ONLY", "").strip().lower() in ("1", "true", "yes")


def apply_proxy_settings(
    *,
    use_proxy: bool = True,
    proxy_url: str | None = None,
    proxy_user: str | None = None,
    proxy_pass: str | None = None,
    cookies_only: bool | None = None,
    vl_username: str | None = None,
    vl_password: str | None = None,
) -> None:
    """Call once at bot startup from vl_inventory_bot.config.json."""
    if not use_proxy:
        os.environ["VL_NO_PROXY"] = "1"
        os.environ.pop("VL_PROXY_URL", None)
    else:
        os.environ.pop("VL_NO_PROXY", None)
        if proxy_url:
            os.environ["VL_PROXY_URL"] = proxy_url.strip()
        elif "VL_PROXY_URL" not in os.environ:
            os.environ["VL_PROXY_URL"] = DEFAULT_VL_PROXY_URL
        if proxy_user:
            os.environ["VL_PROXY_USER"] = proxy_user
        if proxy_pass:
            os.environ["VL_PROXY_PASS"] = proxy_pass
    if cookies_only is None:
        return
    if cookies_only:
        os.environ["VL_COOKIES_ONLY"] = "1"
    else:
        os.environ.pop("VL_COOKIES_ONLY", None)
    if vl_username and str(vl_username).strip():
        os.environ["VL_USERNAME"] = str(vl_username).strip()
    if vl_password is not None and str(vl_password):
        os.environ["VL_PASSWORD"] = str(vl_password)


def proxy_status_for_log() -> str:
    """Sanitized proxy target for logs (no password)."""
    if os.environ.get("VL_NO_PROXY", "").strip().lower() in ("1", "true", "yes"):
        return "direct (VL_NO_PROXY)"
    url = _vl_proxy_url() or ""
    if "@" in url:
        url = url.split("://", 1)[0] + "://***@" + url.split("@", 1)[1]
    return url or "unset"


def _resolve_har_session_path() -> Path | None:
    for p in HAR_SESSION_CANDIDATES:
        if p and str(p).strip() and p.is_file():
            return p
    return None


def cookies_from_har(har_path: Path) -> list[dict]:
    with open(har_path, encoding="utf-8") as f:
        har = json.load(f)
    merged: dict[tuple[str, str], dict] = {}
    for entry in har.get("log", {}).get("entries") or []:
        for c in entry.get("request", {}).get("cookies") or []:
            name = c.get("name")
            value = c.get("value")
            if not name or value is None:
                continue
            dom = str(c.get("domain") or "")
            if "victorylive" not in dom.lower():
                continue
            merged[(dom, name)] = {
                "name": name,
                "value": value,
                "domain": dom,
                "path": c.get("path") or "/",
                "secure": bool(c.get("secure")),
            }
    return list(merged.values())


def export_har_cookies_json(har_path: Path, out_path: Path) -> int:
    items = cookies_from_har(har_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(items, indent=2), encoding="utf-8")
    return len(items)


def _load_session_from_har_file(path: Path, use_proxy: bool) -> requests.Session | None:
    if path.suffix.lower() == ".json":
        items = json.loads(path.read_text(encoding="utf-8"))
    else:
        items = cookies_from_har(path)
    if not items:
        return None
    s = _base_session(use_proxy=use_proxy)
    _load_cookies(s, items)
    return s if _has_apauth(s) else None


def load_credentials_from_har(har_path=None):
    for candidate in (har_path, LOGIN_HAR_PATH, HAR_PATH, ROOT / "deploy" / "one.victorylive.com.har"):
        if not candidate:
            continue
        p = Path(candidate)
        if not p.is_file():
            continue
        with open(p, encoding="utf-8") as f:
            har = json.load(f)
        break
    else:
        raise RuntimeError("No Victory Live HAR with login POST found")
    for entry in har["log"]["entries"]:
        req = entry["request"]
        if req["method"] != "POST" or "/account/Login" not in req["url"]:
            continue
        params = parse_qs(req["postData"]["text"])
        username = params.get("Username", [""])[0]
        password = params.get("Password", [""])[0]
        if username and password:
            return username, password
    raise RuntimeError("Could not find Username/Password in HAR login POST")


def _parse_hidden_form(html, base_url):
    action_m = re.search(r"<form[^>]+action=['\"]([^'\"]+)['\"]", html, re.I)
    if not action_m:
        return None, {}
    action = urljoin(base_url, action_m.group(1).replace("&amp;", "&"))
    fields = {}
    for name, value in re.findall(
        r"<input[^>]+type=['\"]hidden['\"][^>]+name=['\"]([^'\"]+)['\"][^>]+value=['\"]([^'\"]*)['\"]",
        html,
        re.I,
    ):
        fields[name] = value
    for name, value in re.findall(
        r"<input[^>]+name=['\"]([^'\"]+)['\"][^>]+type=['\"]hidden['\"][^>]+value=['\"]([^'\"]*)['\"]",
        html,
        re.I,
    ):
        fields[name] = value
    for name, value in re.findall(
        r"<input[^>]+type=['\"]hidden['\"][^>]+value=['\"]([^'\"]*)['\"][^>]+name=['\"]([^'\"]+)['\"]",
        html,
        re.I,
    ):
        fields[name] = value
    return action, fields


def _verification_token(html):
    m = re.search(
        r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"',
        html,
        re.I,
    )
    if not m:
        m = re.search(
            r'value="([^"]+)"\s+name="__RequestVerificationToken"',
            html,
            re.I,
        )
    return m.group(1) if m else None


def _return_url(html, fallback):
    m = re.search(r'name="ReturnUrl"\s+type="hidden"\s+value="([^"]+)"', html, re.I)
    if not m:
        m = re.search(r'value="([^"]+)"\s+name="ReturnUrl"', html, re.I)
    return m.group(1) if m else fallback


_BROWSER_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
)


def _apply_browser_login_headers(s: requests.Session) -> None:
    s.headers.update(
        {
            "User-Agent": DEFAULT_UA,
            "Accept": _BROWSER_ACCEPT,
            "Accept-Language": "en-US,en;q=0.9",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
        }
    )
    s.headers.pop("Origin", None)
    s.headers.pop("Referer", None)


def _login_form_error(html: str) -> str | None:
    low = (html or "").lower()
    if re.search(r"invalid\s+(?:username|login)|incorrect\s+password", low):
        return "Victory Live: invalid username or password (check vl_password / VL_PASSWORD)"
    if re.search(r"invalid\s+login\s+attempt", low):
        return "Victory Live: invalid login attempt"
    if re.search(r"locked\s+out|account\s+lock", low):
        return "Victory Live: account lockout"
    if re.search(r"two.?factor|authenticator|mfa", low):
        return "Victory Live: MFA / 2FA required (complete in browser once)"
    for msg in re.findall(
        r"(?:validation-summary-errors|field-validation-error|text-danger|alert-danger)[^>]*>[\s\S]*?<span[^>]*>([^<]{3,200})",
        html or "",
        re.I,
    ):
        t = re.sub(r"\s+", " ", msg).strip()
        if t:
            return t
    for msg in re.findall(
        r"(?:validation-summary-errors|field-validation-error|text-danger)[^>]*>([^<]{3,200})",
        html or "",
        re.I,
    ):
        t = re.sub(r"\s+", " ", msg).strip()
        if t and ("invalid" in t.lower() or len(t) > 8):
            return t
    return None


def _has_antiforgery_cookie(s: requests.Session) -> bool:
    for c in s.cookies:
        if "Antiforgery" in c.name or "antiforgery" in c.name.lower():
            return True
    return False


def _challenge_vl_login_page(s: requests.Session, *, timeout: int) -> requests.Response:
    """Reach login only via one.victorylive.com OIDC redirect (HAR path)."""
    s.cookies.clear()
    _apply_browser_login_headers(s)
    starters = (
        f"{APP_BASE}/v2/OrderManager",
        f"{APP_BASE}/",
        f"{APP_BASE}/api/security/profile",
    )
    last: requests.Response | None = None
    for start in starters:
        try:
            last = s.get(start, allow_redirects=True, timeout=timeout)
        except requests.RequestException:
            continue
        url = last.url or ""
        if "login.victorylive.com" not in url:
            continue
        if _VL_OIDC_CLIENT in url or "connect%2Fauthorize" in url.lower():
            return last
        if "returnurl=" in url.lower():
            return last
    if last and "login.victorylive.com" in (last.url or ""):
        return last
    raise RuntimeError(
        "Victory Live login challenge failed — no OIDC redirect to login.victorylive.com "
        f"(last url={(last.url[:120] if last else 'none')})"
    )


def _unescape_return_url(raw: str) -> str:
    s = (raw or "").strip()
    prev = None
    while s != prev:
        prev = s
        s = html.unescape(s)
    return s


def _login_page_fields(html: str, login_url: str) -> tuple[str, str]:
    token = _verification_token(html)
    if not token:
        raise RuntimeError(f"No __RequestVerificationToken on login page ({login_url})")
    return_url = _unescape_return_url(_return_url(html, "") or "")
    if not return_url:
        parsed = urlparse(login_url)
        return_url = parse_qs(parsed.query).get("ReturnUrl", [""])[0] if parsed.query else ""
        return_url = _unescape_return_url(return_url)
    if not return_url:
        raise RuntimeError("Login page missing ReturnUrl (OIDC challenge incomplete)")
    return token, return_url


def _fetch_login_form(s: requests.Session, *, timeout: int) -> tuple[str, str, str]:
    """OIDC challenge + fresh login document (matched antiforgery cookie + form token)."""
    challenged = _challenge_vl_login_page(s, timeout=timeout)
    login_url = challenged.url or f"{LOGIN_BASE}/account/login"
    page = s.get(login_url, timeout=timeout)
    if page.status_code != 200:
        page = challenged
    token, return_url = _login_page_fields(page.text, login_url)
    return login_url, token, return_url


def _post_login_credentials(
    s: requests.Session,
    login_url: str,
    return_url: str,
    token: str,
    username: str,
    password: str,
    *,
    timeout: int,
    allow_redirects: bool = False,
) -> requests.Response:
    return s.post(
        f"{LOGIN_BASE}/account/Login",
        data={
            "ReturnUrl": return_url,
            "Username": username,
            "Password": password,
            "RememberLogin": "true",
            "__RequestVerificationToken": token,
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": LOGIN_BASE,
            "Referer": login_url,
            "Accept": _BROWSER_ACCEPT,
            "Cache-Control": "max-age=0",
        },
        allow_redirects=allow_redirects,
        timeout=timeout,
    )


def _continue_after_login_post(
    s: requests.Session,
    r: requests.Response,
    *,
    timeout: int,
) -> requests.Response | None:
    if r.status_code in (301, 302, 303, 307, 308):
        callback_url = urljoin(LOGIN_BASE, r.headers.get("Location", ""))
        return s.get(callback_url, allow_redirects=True, timeout=timeout)
    if r.status_code == 200:
        oidc = _post_oidc_hidden_form(s, r.text, r.url, timeout=timeout)
        if oidc is not None:
            return oidc
        if r.headers.get("Location"):
            return s.get(
                urljoin(LOGIN_BASE, r.headers["Location"]),
                allow_redirects=True,
                timeout=timeout,
            )
        err = _login_form_error(r.text)
        if err:
            raise RuntimeError(f"Login failed: {err}")
        if _verification_token(r.text):
            return None  # login form again — caller may retry challenge
        raise RuntimeError(f"Login POST unexpected status {r.status_code}")
    raise RuntimeError(f"Login POST unexpected status {r.status_code}")


def _post_oidc_hidden_form(
    s: requests.Session,
    html: str,
    page_url: str,
    *,
    timeout: int,
) -> requests.Response | None:
    action, fields = _parse_hidden_form(html, page_url)
    if not action or "id_token" not in fields:
        return None
    return s.post(
        action,
        data=fields,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": LOGIN_BASE,
            "Referer": page_url,
            "Accept": _BROWSER_ACCEPT,
        },
        allow_redirects=True,
        timeout=timeout,
    )


def _base_session(use_proxy: bool = True) -> requests.Session:
    s = requests.Session()
    s.trust_env = False  # never honor HTTP_PROXY env on VPS (bypasses egress)
    s.headers.update(
        {
            "User-Agent": DEFAULT_UA,
            "Accept": "application/json, text/plain, */*",
            "Origin": APP_BASE,
            "Referer": f"{APP_BASE}/v2/OrderManager",
        }
    )
    attach_egress_proxy(s, use_proxy=use_proxy)
    return s


def attach_egress_proxy(s: requests.Session, *, use_proxy: bool = True) -> None:
    if not use_proxy or os.environ.get("VL_NO_PROXY", "").strip().lower() in ("1", "true", "yes"):
        s.proxies.clear()
        return
    pd = proxy_dict()
    if pd:
        s.proxies.update(pd)


def verify_egress_public_ip(s: requests.Session, *, timeout: int = 25) -> str:
    """Return public IP as seen when using this session (should be 96.x egress host)."""
    r = s.get("https://api.ipify.org?format=json", timeout=timeout)
    r.raise_for_status()
    return str((r.json() or {}).get("ip") or "").strip()


def probe_egress_public_ip(*, timeout: int = 25) -> str:
    """
    One-shot ipify check through the configured VL proxy (new TCP CONNECT on egress).
    Use before /list so the 96 proxy console always shows traffic even when the
    main session reuses an existing tunnel to one.victorylive.com.
    """
    pd = proxy_dict()
    if not pd:
        r = requests.get(
            "https://api.ipify.org?format=json",
            timeout=timeout,
            headers={"Connection": "close"},
        )
    else:
        r = requests.get(
            "https://api.ipify.org?format=json",
            proxies=pd,
            timeout=timeout,
            headers={"Connection": "close"},
        )
    r.raise_for_status()
    return str((r.json() or {}).get("ip") or "").strip()


def enable_session_http_logging(s: requests.Session, *, logger_name: str = "vl_inventory_bot") -> None:
    """Log each HTTP request on the bot (URLs are visible; body is not)."""
    import logging

    log = logging.getLogger(logger_name)
    if getattr(s, "_vl_http_logging", False):
        return

    def _log_response(r: requests.Response, *args, **kwargs) -> requests.Response:
        try:
            log.info(
                "vl-http %s %s → %s",
                r.request.method if r.request else "?",
                r.request.url if r.request else "?",
                r.status_code,
            )
        except Exception:
            pass
        return r

    s.hooks.setdefault("response", []).append(_log_response)
    s._vl_http_logging = True  # type: ignore[attr-defined]


def _cookies_to_list(session: requests.Session) -> list[dict]:
    out: list[dict] = []
    for c in session.cookies:
        out.append(
            {
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path or "/",
                "secure": bool(c.secure),
                "expires": c.expires,
            }
        )
    return out


def _load_cookies(session: requests.Session, items: list[dict]) -> None:
    for row in items:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        value = row.get("value")
        if not name or value is None:
            continue
        session.cookies.set_cookie(
            Cookie(
                version=0,
                name=str(name),
                value=str(value),
                port=None,
                port_specified=False,
                domain=str(row.get("domain") or "one.victorylive.com"),
                domain_specified=True,
                domain_initial_dot=str(row.get("domain") or "").startswith("."),
                path=str(row.get("path") or "/"),
                path_specified=True,
                secure=bool(row.get("secure")),
                expires=row.get("expires"),
                discard=False,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False,
            )
        )


def _save_session_disk(session: requests.Session, username: str) -> None:
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "username": username,
        "saved_at": time.time(),
        "cookies": _cookies_to_list(session),
    }
    SESSION_PATH.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    _sync_cookies_to_har_json(session)


def _sync_cookies_to_har_json(session: requests.Session) -> None:
    """Refresh data/vl_har_cookies.json after login so HAR fallback stays current."""
    har_json = ROOT / "data" / "vl_har_cookies.json"
    try:
        har_json.parent.mkdir(parents=True, exist_ok=True)
        har_json.write_text(
            json.dumps(_cookies_to_list(session), indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def _load_session_disk(username: str) -> requests.Session | None:
    if not SESSION_PATH.is_file():
        return None
    try:
        payload = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if str(payload.get("username") or "") != username:
        return None
    cookies = payload.get("cookies")
    if not isinstance(cookies, list) or not cookies:
        return None
    s = _base_session(use_proxy=not os.environ.get("VL_NO_PROXY"))
    _load_cookies(s, cookies)
    return s


def _clear_session_disk() -> None:
    try:
        SESSION_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def _has_apauth(session: requests.Session) -> bool:
    return bool(session.cookies.get(".APAUTH", domain="one.victorylive.com") or session.cookies.get(".APAUTH"))


def session_is_valid(session: requests.Session, *, timeout: int = 30, force_check: bool = False) -> bool:
    global _LAST_PROFILE_CHECK
    if not _has_apauth(session):
        return False
    now = time.time()
    if not force_check and (now - _LAST_PROFILE_CHECK) < _PROFILE_CHECK_INTERVAL_SEC:
        return True
    try:
        r = session.get(f"{APP_BASE}/api/security/profile", timeout=timeout, allow_redirects=True)
    except requests.RequestException:
        return False
    if "login.victorylive.com" in (r.url or ""):
        return False
    ctype = (r.headers.get("Content-Type") or "").lower()
    if r.status_code != 200 or "json" not in ctype:
        return False
    _LAST_PROFILE_CHECK = now
    return True


def invalidate_vl_session() -> None:
    global _MEM_SESSION, _MEM_USERNAME, _LAST_PROFILE_CHECK
    with _LOCK:
        _MEM_SESSION = None
        _MEM_USERNAME = None
        _LAST_PROFILE_CHECK = 0.0
    _clear_session_disk()


def _perform_oidc_login(
    s: requests.Session,
    username: str,
    password: str,
    *,
    timeout: int,
) -> requests.Session:
    r_after_login: requests.Response | None = None
    last_err = ""
    for attempt in range(2):
        login_url, token, return_url = _fetch_login_form(s, timeout=timeout)
        if not _has_antiforgery_cookie(s):
            raise RuntimeError(
                "Login page missing antiforgery cookie — proxy or VL blocked Set-Cookie"
            )
        post = _post_login_credentials(
            s, login_url, return_url, token, username, password, timeout=timeout
        )
        form_err = _login_form_error(post.text)
        if form_err:
            raise RuntimeError(f"Login failed: {form_err}")
        try:
            r_after_login = _continue_after_login_post(s, post, timeout=timeout)
            if r_after_login is not None:
                break
            if post.status_code == 200 and _verification_token(post.text):
                last_err = (
                    "login form returned after POST — wrong password or CSRF "
                    f"(user={username})"
                )
            else:
                last_err = f"login POST unexpected (HTTP {post.status_code})"
        except RuntimeError as exc:
            last_err = str(exc)
            if attempt == 0 and "antiforgery" not in last_err.lower():
                raise
    else:
        raise RuntimeError(
            "Victory Live login failed after retry — "
            f"{last_err or 'unknown'}. "
            "Set vl_username/vl_password in vl_inventory_bot.config.json on the VPS, "
            "or export fresh cookies to data/vl_har_cookies.json from a browser login."
        )

    if r_after_login is not None:
        if _post_oidc_hidden_form(s, r_after_login.text, r_after_login.url, timeout=timeout) is None:
            action, fields = _parse_hidden_form(r_after_login.text, r_after_login.url)
            if ("signin-oidc" in r_after_login.text.lower() or "id_token" in r_after_login.text) and not (
                action and "id_token" in fields
            ):
                raise RuntimeError("OIDC callback form found but could not parse hidden fields")

    # Validate session
    s.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Origin": APP_BASE,
        "Referer": f"{APP_BASE}/v2/OrderManager",
    })
    check = s.get(
        f"{APP_BASE}/api/security/profile",
        timeout=timeout,
    )
    if "json" not in check.headers.get("Content-Type", ""):
        raise RuntimeError("Login failed - profile API did not return JSON")

    apauth = s.cookies.get(".APAUTH", domain="one.victorylive.com") or s.cookies.get(".APAUTH")
    if not apauth:
        raise RuntimeError("Login failed - no .APAUTH cookie")

    profile = check.json()
    name = profile.get("Data", {}).get("DisplayName") or profile.get("Data", {}).get("UserName") or username
    print(f"Logged in as {name} (fresh login)")
    return s


def _finish_fresh_login(
    s: requests.Session,
    username: str,
    *,
    use_proxy: bool,
    timeout: int,
) -> requests.Session:
    """Persist cookies, attach egress for API, verify profile through proxy if enabled."""
    global _MEM_SESSION, _MEM_USERNAME
    _save_session_disk(s, username)
    attach_egress_proxy(s, use_proxy=use_proxy)
    if use_proxy and not session_is_valid(s, timeout=timeout, force_check=True):
        raise RuntimeError(
            "Victory Live login succeeded but session is not valid through the egress proxy "
            f"({proxy_status_for_log()})"
        )
    _MEM_SESSION = s
    _MEM_USERNAME = username
    return s


def _oidc_login_direct(
    username: str,
    password: str,
    *,
    use_proxy_after: bool,
    timeout: int,
) -> requests.Session:
    """OIDC without egress (VPS direct); API calls afterward use proxy when requested."""
    print(
        "Victory Live cookies expired — OIDC login direct (no egress), "
        f"then API via {proxy_status_for_log() if use_proxy_after else 'direct'}"
    )
    s = _base_session(use_proxy=False)
    s = _perform_oidc_login(s, username, password, timeout=timeout)
    return _finish_fresh_login(s, username, use_proxy=use_proxy_after, timeout=timeout)


def login(
    username=None,
    password=None,
    use_proxy=True,
    timeout=45,
    *,
    force_relogin: bool = False,
    cookies_only: bool | None = None,
) -> requests.Session:
    if not username:
        username = os.environ.get("VL_USERNAME") or DEFAULT_VL_USERNAME
    if not password:
        password = os.environ.get("VL_PASSWORD") or DEFAULT_VL_PASSWORD

    global _MEM_SESSION, _MEM_USERNAME

    if cookies_only is None:
        cookies_only = cookies_only_mode()

    if force_relogin:
        invalidate_vl_session()

    # Single-flight login: concurrent bot handlers must not each run OIDC (looks
    # like scraping and spams the egress proxy with login.victorylive.com).
    with _LOCK:
        if (
            not force_relogin
            and _MEM_SESSION is not None
            and _MEM_USERNAME == username
            and session_is_valid(_MEM_SESSION, timeout=timeout)
        ):
            attach_egress_proxy(_MEM_SESSION, use_proxy=use_proxy)
            return _MEM_SESSION  # in-memory cookies; profile check at most every ~90s

        if not force_relogin:
            restored = _load_session_disk(username)
            if restored and session_is_valid(restored, timeout=timeout, force_check=True):
                attach_egress_proxy(restored, use_proxy=use_proxy)
                _MEM_SESSION = restored
                _MEM_USERNAME = username
                print("Victory Live session restored from disk (no login)")
                return restored
            if restored:
                _clear_session_disk()

        har_path = _resolve_har_session_path()
        if har_path and not force_relogin:
            try:
                har_sess = _load_session_from_har_file(har_path, use_proxy=use_proxy)
                if har_sess and session_is_valid(har_sess, timeout=timeout, force_check=True):
                    attach_egress_proxy(har_sess, use_proxy=use_proxy)
                    _save_session_disk(har_sess, username)
                    _MEM_SESSION = har_sess
                    _MEM_USERNAME = username
                    print(f"Victory Live session from browser export ({har_path.name})")
                    return har_sess
            except (OSError, json.JSONDecodeError, requests.RequestException):
                pass

        return _oidc_login_direct(
            username,
            password,
            use_proxy_after=use_proxy,
            timeout=timeout,
        )


if __name__ == "__main__":
    sess = login()
    r = sess.get(f"{APP_BASE}/api/orders/search", params={"Page": "1", "PageSize": "1", "ShowPosOrders": "true"})
    print("orders/search:", r.status_code, r.headers.get("Content-Type", ""))
