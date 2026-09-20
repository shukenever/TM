"""StageFront portal API client (from portal.stagefront.com HAR)."""

from __future__ import annotations

import http.cookiejar
import json
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

BASE = "https://portal.stagefront.com"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": BASE,
}


@dataclass
class StagefrontConfig:
    proxy_url: str | None = None
    company_name: str | None = None
    sharing_rule_name: str = "shu"
    event_from: str = ""
    event_to: str = "12/31/2029"
    undercut_pct: float = 3.0
    undercut_pct_aggressive: float = 5.0
    aggressive_fraction: float = 0.15
    min_under_usd: float = 0.11
    price_strategy: str = "portal"  # portal | percent | blend
    cheap_ticket_pct_threshold: float = 50.0
    max_concurrent_requests: int = 12
    request_gap_sec: float = 0.05
    skip_autopricer: bool = True


class StagefrontClient:
    def __init__(self, config: StagefrontConfig) -> None:
        self.config = config
        self._cookie = ""
        self._ctx = ssl.create_default_context()
        self._jar = http.cookiejar.CookieJar()
        self._opener = self._build_opener()
        self._default_sharing_rule_id: int | None = None
        self._sharing_cache: dict[int, list[dict[str, Any]]] = {}
        self._rule_id_by_name: dict[str, int] = {}
        n = max(1, int(config.max_concurrent_requests))
        self._req_sem = threading.Semaphore(n)
        self._last_req = 0.0
        self._req_gap_lock = threading.Lock()

    def _build_opener(self) -> urllib.request.OpenerDirector:
        handlers: list[Any] = [
            urllib.request.HTTPSHandler(context=self._ctx),
            urllib.request.HTTPCookieProcessor(self._jar),
        ]
        if self.config.proxy_url:
            handlers.append(
                urllib.request.ProxyHandler(
                    {"http": self.config.proxy_url, "https": self.config.proxy_url}
                )
            )
        return urllib.request.build_opener(*handlers)

    def _sync_cookie_string(self) -> None:
        parts: list[str] = []
        for c in self._jar:
            parts.append(f"{c.name}={c.value}")
        self._cookie = "; ".join(parts)

    def set_cookie(self, cookie: str) -> None:
        self._cookie = cookie.strip()
        for part in self._cookie.split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            name, value = part.split("=", 1)
            self._jar.set_cookie(
                http.cookiejar.Cookie(
                    version=0,
                    name=name.strip(),
                    value=value.strip(),
                    port=None,
                    port_specified=False,
                    domain=".stagefront.com",
                    domain_specified=True,
                    domain_initial_dot=True,
                    path="/",
                    path_specified=True,
                    secure=True,
                    expires=None,
                    discard=True,
                    comment=None,
                    comment_url=None,
                    rest={"HttpOnly": None},
                    rfc2109=False,
                )
            )
        self._sync_cookie_string()

    def set_default_sharing_rule_id(self, rule_id: int | None) -> None:
        self._default_sharing_rule_id = rule_id

    def _headers(self, referer: str = f"{BASE}/Pricing") -> dict[str, str]:
        self._sync_cookie_string()
        h = dict(DEFAULT_HEADERS)
        h["Referer"] = referer
        if self._cookie:
            h["Cookie"] = self._cookie
        return h

    def _throttle(self) -> None:
        gap = self.config.request_gap_sec
        if gap <= 0:
            return
        with self._req_gap_lock:
            now = time.monotonic()
            wait = gap - (now - self._last_req)
            if wait > 0:
                time.sleep(wait)
            self._last_req = time.monotonic()

    def _open(self, req: urllib.request.Request, timeout: int = 120) -> tuple[int, str, dict[str, str]]:
        with self._req_sem:
            self._throttle()
            try:
                with self._opener.open(req, timeout=timeout) as resp:
                    body = resp.read().decode("utf-8", "replace")
                    self._sync_cookie_string()
                    loc = resp.headers.get("Location", "")
                    return resp.status, body, {"Location": loc}
            except urllib.error.HTTPError as e:
                self._sync_cookie_string()
                loc = e.headers.get("Location", "") if e.headers else ""
                return e.code, e.read().decode("utf-8", "replace"), {"Location": loc}
            except Exception as e:
                return -1, str(e), {}

    @staticmethod
    def _parse_form_token(html: str) -> str:
        m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html, re.I)
        if not m:
            m = re.search(r'__RequestVerificationToken" type="hidden" value="([^"]+)"', html)
        if not m:
            raise RuntimeError("anti-forgery token not found")
        return m.group(1)

    @staticmethod
    def _parse_hidden(html: str, name: str) -> str:
        m = re.search(rf'name="{re.escape(name)}"[^>]*value="([^"]*)"', html, re.I)
        return m.group(1) if m else ""

    def _get_html(self, path: str, referer: str | None = None) -> str:
        url = path if path.startswith("http") else f"{BASE}{path}"
        req = urllib.request.Request(url, headers=self._headers(referer or f"{BASE}/Account/Login"))
        code, body, _ = self._open(req)
        if code != 200:
            raise RuntimeError(f"GET {path} HTTP {code}: {body[:300]}")
        return body

    def ensure_api_session(self) -> None:
        self.get_json("/api/Pricing/ListCompanies")

    def login(self, username: str, password: str) -> bool:
        """Password step. Returns True if 2FA code entry is required."""
        html = self._get_html("/Account/Login?ReturnUrl=%2F")
        token = self._parse_form_token(html)
        form = urllib.parse.urlencode(
            {
                "__RequestVerificationToken": token,
                "UserName": username,
                "Password": password,
                "RememberMe": "true",
            }
        ).encode("utf-8")
        post_req = urllib.request.Request(
            f"{BASE}/Account/Login?ReturnUrl=%2F",
            data=form,
            headers={
                **self._headers(f"{BASE}/Account/Login"),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        code, body, hdrs = self._open(post_req)
        if code == 302:
            loc = hdrs.get("Location") or "/"
            if not loc.startswith("http"):
                loc = f"{BASE}{loc}"
            body = self._get_html(loc, referer=f"{BASE}/Account/Login")
        self._sync_cookie_string()
        names = {c.name for c in self._jar}
        if ".AspNet.ApplicationCookie" in names:
            self.ensure_api_session()
            return False
        if ".AspNet.TwoFactorCookie" in names or "/Account/VerifyCode" in body:
            return True
        raise RuntimeError(f"login failed HTTP {code}: {body[:300]}")

    def verify_two_factor(self, code: str, remember_browser: bool = True) -> None:
        html = self._get_html("/Account/VerifyCode?ReturnUrl=%2F")
        token = self._parse_form_token(html)
        provider = self._parse_hidden(html, "provider")
        payload = {
            "__RequestVerificationToken": token,
            "provider": provider,
            "Code": code.strip(),
        }
        if remember_browser:
            payload["RememberBrowser"] = "true"
        data = urllib.parse.urlencode(payload).encode("utf-8")
        post_req = urllib.request.Request(
            f"{BASE}/Account/VerifyCode?ReturnUrl=%2F",
            data=data,
            headers={
                **self._headers(f"{BASE}/Account/VerifyCode?ReturnUrl=%2F"),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        code_http, body, hdrs = self._open(post_req)
        if code_http == 302:
            loc = hdrs.get("Location") or "/"
            if not loc.startswith("http"):
                loc = f"{BASE}{loc}"
            self._get_html(loc)
        elif code_http != 200 or "VerifyCode" in body:
            raise RuntimeError("invalid or expired security code")
        self._sync_cookie_string()
        if ".AspNet.ApplicationCookie" not in {c.name for c in self._jar}:
            raise RuntimeError("2FA verify did not establish session")
        self.ensure_api_session()

    def login_interactive(
        self,
        username: str,
        password: str,
        *,
        prompt: Callable[[str], str] | None = None,
    ) -> None:
        if prompt is None:
            prompt = lambda msg: input(msg).strip()
        needs_2fa = self.login(username, password)
        if needs_2fa:
            otp = prompt("StageFront security code from email: ")
            if not otp:
                raise RuntimeError("empty security code")
            self.verify_two_factor(otp)

    def get_json(self, path: str, *, timeout: int = 120) -> Any:
        url = path if path.startswith("http") else f"{BASE}{path}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        code, body, _ = self._open(req, timeout=timeout)
        if code != 200:
            raise RuntimeError(f"GET {path} HTTP {code}: {body[:400]}")
        return json.loads(body) if body else None

    def post_json(self, path: str, payload: Any, *, timeout: int = 120) -> Any:
        url = path if path.startswith("http") else f"{BASE}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={**self._headers(), "Content-Type": "application/json"},
            method="POST",
        )
        code, body, _ = self._open(req, timeout=timeout)
        if code != 200:
            raise RuntimeError(f"POST {path} HTTP {code}: {body[:400]}")
        if not body:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body

    def post_form_pairs(self, path: str, pairs: list[tuple[str, str]], *, timeout: int = 120) -> Any:
        url = path if path.startswith("http") else f"{BASE}{path}"
        data = urllib.parse.urlencode(pairs).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={**self._headers(), "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        code, body, _ = self._open(req, timeout=timeout)
        if code != 200:
            raise RuntimeError(f"POST {path} HTTP {code}: {body[:400]}")
        try:
            return json.loads(body) if body else None
        except json.JSONDecodeError:
            return body

    def post_form(self, path: str, form: dict[str, Any], *, timeout: int = 120) -> Any:
        url = path if path.startswith("http") else f"{BASE}{path}"
        data = urllib.parse.urlencode(form, doseq=True).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={**self._headers(), "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        code, body, _ = self._open(req, timeout=timeout)
        if code != 200:
            raise RuntimeError(f"POST {path} HTTP {code}: {body[:400]}")
        try:
            return json.loads(body) if body else None
        except json.JSONDecodeError:
            return body

    def list_companies(self) -> list[str]:
        data = self.get_json("/api/Pricing/ListCompanies")
        return list(data or [])

    def resolve_company(self) -> str:
        if self.config.company_name:
            return self.config.company_name
        companies = self.list_companies()
        if not companies:
            raise RuntimeError("ListCompanies returned empty")
        return companies[0]

    def query_events(self) -> list[dict[str, Any]]:
        payload = {
            "EventFromDate": self.config.event_from,
            "EventToDate": self.config.event_to,
            "POFromDate": None,
            "POToDate": None,
            "SearchString": None,
            "CategoryId": None,
            "EventHeadlinerId": None,
            "EventId": None,
            "VenueId": None,
            "ListingId": None,
            "POId": None,
            "CompanyName": None,
            "DaysSinceLastUpdate": None,
            "ForceRefresh": True,
            "SearchTag": None,
            "Sections": None,
            "Row": None,
            "Quantity": None,
            "ShowSold": True,
            "page": 1,
            "startIndex": 0,
            "limit": 99999,
        }
        data = self.post_json("/api/Pricing/QueryEvents", payload, timeout=300)
        if not data:
            return []
        return list(data.get("Events") or [])

    def query_event_inventory(self, event_id: int, company_name: str) -> list[dict[str, Any]]:
        data = self.post_json(
            "/api/Pricing/QueryEventInventoryAll",
            {"eventId": event_id, "companyName": company_name, "searchTag": ""},
        )
        return list((data or {}).get("EventInventory") or [])

    def group_listings(self, inventory: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        grouped: dict[int, dict[str, Any]] = {}
        for row in inventory:
            lid = int(row["Listing_ID"])
            g = grouped.get(lid)
            if not g:
                g = {
                    "listing_id": lid,
                    "event_id": int(row["Event_ID"]),
                    "section": str(row.get("Section") or ""),
                    "row": str(row.get("Row") or ""),
                    "company_name": str(row.get("Company_Name") or ""),
                    "seats": [],
                    "item_price": float(row.get("Item_Price") or 0),
                }
                grouped[lid] = g
            g["seats"].append(int(row.get("Seat_Number") or 0))
        for g in grouped.values():
            g["quantity"] = len(g["seats"]) or 1
        return grouped

    def get_lowest_comparables(self, event_id: int, listing: dict[str, Any]) -> list[dict[str, Any]]:
        pairs: list[tuple[str, str]] = [
            ("eventId", str(event_id)),
            ("rules[CompareToEverything]", "false"),
            ("rules[FloorNotification]", "false"),
            ("rules[CeilingNotification]", "false"),
            ("rules[AllowPriceIncrease]", "false"),
            ("rules[CompareAgainstOwnInventory]", "false"),
            ("rules[FloorPrice]", ""),
            ("rules[CeilingPrice]", ""),
            ("rules[Notes]", ""),
            ("rules[TicketSplit]", str(listing["quantity"])),
            ("rules[RowRangeStart]", ""),
            ("rules[RowRangeEnd]", ""),
            ("rules[AllRows]", "false"),
            ("rules[Position]", ""),
            ("rules[AmountUnder]", ""),
            ("rules[MinutesPerCycle]", ""),
            ("rules[Zones]", ""),
            ("rules[Sections][]", listing["section"]),
            ("rules[Rows][]", listing["row"]),
            ("rules[TraitExclusions][]", "1"),
            ("rules[TraitExclusions][]", "102"),
            ("rules[Exclude_Outliers]", ""),
            ("rules[NoComparablesNotification]", ""),
            ("rules[Delivery_Exclusions]", ""),
            ("rules[PctUnder]", ""),
            ("rules[UseDefaultSplits]", ""),
            ("rules[SuggestedSection]", ""),
            ("rules[ListingId]", str(listing["listing_id"])),
            ("rules[SeatGeekListingId]", ""),
            ("rules[MasterRuleId]", ""),
            ("SF_Listing[ListingID]", str(listing["listing_id"])),
            ("SF_Listing[Price]", str(listing.get("item_price") or 0)),
            ("SF_Listing[Row]", listing["row"]),
            ("SF_Listing[Section]", listing["section"]),
            ("SF_Listing[Quantity]", str(listing["quantity"])),
            ("SF_Listing[CompanyName]", listing["company_name"]),
        ]
        data = self.post_form_pairs("/api/Marketplace/SeatGeek/GetLowestComparables", pairs)
        return list(data or [])

    def update_listing_prices(self, listing_id: int, price: float) -> None:
        self.post_json("/api/Pricing/UpdateListingPrices", [{"listing_id": listing_id, "price": price}])

    def sharing_rule_id(self, venue_id: int) -> int | None:
        if self._default_sharing_rule_id:
            return self._default_sharing_rule_id
        name = self.config.sharing_rule_name.strip().lower()
        if name in self._rule_id_by_name:
            return self._rule_id_by_name[name]
        rules = self.get_json(f"/api/Pricing/ListSavedSharingRules?venueId={venue_id}")
        for r in rules or []:
            rid = int(r["Rule_ID"])
            rname = (r.get("Rule_Name") or "").strip().lower()
            self._rule_id_by_name[rname] = rid
        return self._rule_id_by_name.get(name)

    def share_out_settings(self, rule_id: int) -> list[dict[str, Any]]:
        if rule_id in self._sharing_cache:
            return self._sharing_cache[rule_id]
        data = self.get_json(f"/api/Pricing/GetSavedSharingRule?ruleId={rule_id}")
        settings = list(data or [])
        self._sharing_cache[rule_id] = settings
        return settings

    def update_listings_sharing(self, listing_ids: list[int], share_out: list[dict[str, Any]]) -> None:
        self.post_json(
            "/api/Pricing/UpdateListingsSharing",
            {"ListingIds": listing_ids, "ShareOutSettings": share_out},
        )
