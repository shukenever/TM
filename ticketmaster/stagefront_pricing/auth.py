"""StageFront auth: HAR cookie import and interactive 2FA."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable


def cookie_from_har(har_path: str | Path) -> str:
    """Pick Cookie header from the newest authenticated API call in a HAR."""
    path = Path(har_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    cookie = ""
    markers = (
        "/api/Pricing/ListCompanies",
        "/api/Pricing/QueryEvents",
        "/api/Pricing/QueryEventInventoryAll",
    )
    for entry in data.get("log", {}).get("entries", []):
        req = entry.get("request", {})
        url = req.get("url", "")
        if not any(m in url for m in markers):
            continue
        if entry.get("response", {}).get("status") != 200:
            continue
        for h in req.get("headers", []):
            if h.get("name", "").lower() == "cookie":
                val = h.get("value", "")
                if val and ".AspNet.ApplicationCookie" in val:
                    cookie = val
                break
    if not cookie:
        raise RuntimeError(f"no authenticated API cookie found in {path}")
    return cookie
