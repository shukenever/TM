#!/usr/bin/env python3
"""OIDC login step trace (run on bot VPS). No password output."""
import json
import os
from pathlib import Path

ROOT = Path(r"C:\Users\Administrator\Desktop\ticket management bot")
os.chdir(ROOT)
cfg = json.loads(Path("vl_inventory_bot.config.json").read_text(encoding="utf-8"))
os.environ["VL_PROXY_URL"] = cfg.get("vl_proxy_url") or "http://96.126.176.73:8749"
os.environ["VL_PROXY_USER"] = cfg.get("vl_proxy_user") or "vl"
os.environ["VL_PROXY_PASS"] = cfg.get("vl_proxy_pass") or ""
os.environ["VL_COOKIES_ONLY"] = "1"

import vl_auth
from vl_auth import (
    DEFAULT_VL_PASSWORD,
    DEFAULT_VL_USERNAME,
    _challenge_vl_login_page,
    _continue_after_login_post,
    _has_antiforgery_cookie,
    _login_form_error,
    _login_page_fields,
    _post_login_credentials,
    _return_url,
    _verification_token,
)


def cookie_names(s):
    return sorted({c.name for c in s.cookies})


def run(label: str, use_proxy: bool) -> None:
    print("===", label, "use_proxy=", use_proxy, "===")
    s = vl_auth._base_session(use_proxy=use_proxy)
    try:
        page = _challenge_vl_login_page(s, timeout=90)
    except Exception as e:
        print("challenge_fail", repr(e))
        return
    print("challenge_url", (page.url or "")[:220])
    print("challenge_status", page.status_code)
    print("cookies_after_challenge", cookie_names(s))
    print("has_antiforgery", _has_antiforgery_cookie(s))
    tok = _verification_token(page.text)
    print("has_form_token", bool(tok), "token_len", len(tok or ""))
    err = _login_form_error(page.text)
    if err:
        print("login_page_error", err)
    try:
        token, return_url = _login_page_fields(page.text, page.url)
    except Exception as e:
        print("fields_fail", repr(e))
        return
    print("return_url_len", len(return_url))
    user = os.environ.get("VL_USERNAME") or DEFAULT_VL_USERNAME
    pw = os.environ.get("VL_PASSWORD") or DEFAULT_VL_PASSWORD
    # Refresh login document so antiforgery cookie + form token match (ASP.NET).
    page2 = s.get(page.url, timeout=90)
    token2 = _verification_token(page2.text) or token
    return_url2 = _return_url(page2.text, return_url) or return_url
    print("refresh_status", page2.status_code, "token_refreshed", token2 != token)
    post = _post_login_credentials(s, page.url, return_url2, token2, user, pw, timeout=90)
    print("post_status", post.status_code)
    print("post_location", (post.headers.get("Location") or "")[:160])
    print("cookies_after_post", cookie_names(s))
    if post.status_code == 200 and _verification_token(post.text):
        print("post_body_has_login_form", True)
        print("post_body_error", _login_form_error(post.text))
        low = (post.text or "").lower()
        for needle in (
            "invalid login",
            "incorrect",
            "password",
            "antiforgery",
            "validation",
            "locked",
            "two-factor",
            "mfa",
        ):
            if needle in low:
                print("needle_in_body", needle)
        import re

        title = re.search(r"<title>([^<]+)", post.text or "", re.I)
        print("post_title", (title.group(1).strip() if title else "")[:80])
        for msg in re.findall(
            r"(?:validation-summary-errors|field-validation-error|text-danger)[^>]*>([^<]{3,200})",
            post.text or "",
            re.I,
        ):
            print("validation_msg", msg.strip()[:160])
        out = ROOT / "data" / "vl_login_post_snippet.txt"
        out.write_text((post.text or "")[:8000], encoding="utf-8")
        print("wrote_snippet", str(out))
        inputs = re.findall(r'<input[^>]+name=["\']([^"\']+)["\']', page.text or "", re.I)
        print("login_input_names", sorted(set(inputs))[:20])
    try:
        cont = _continue_after_login_post(s, post, timeout=90)
        print("continue_ok", cont is not None)
        if cont:
            print("final_url", (cont.url or "")[:160])
            print("has_apauth", vl_auth._has_apauth(s))
    except Exception as e:
        print("continue_exc", repr(e))


def main() -> None:
    Path("data/vl_session.json").unlink(missing_ok=True)
    vl_auth.invalidate_vl_session()
    run("direct", False)
    print()
    run("egress", True)


if __name__ == "__main__":
    main()
