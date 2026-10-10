"""Detect StubHub / marketplace sale emails and format admin alerts."""
from __future__ import annotations

import re
from typing import Any

_SALE_SUBJECT = re.compile(
    r"\b(sold|sale|order\s+confirm|you\s+sold|payout|payment|transfer|deliver|fulfil)",
    re.I,
)
_SALE_FROM = re.compile(r"stubhub|viagogo|tixstock|tickpick|seatgeek|vivid|gametime", re.I)
_SALE_BODY = re.compile(
    r"\b(your\s+.{0,40}\s+sold|sale\s+confirm|order\s+#|order\s+number|"
    r"congratulations.{0,30}sold|tickets?\s+sold|payment\s+on\s+the\s+way)\b",
    re.I,
)

_EVENT_LINE = re.compile(r"^EVENT:\s*(.+)$", re.I | re.M)
_DATE_LINE = re.compile(r"^DATE:\s*(.+)$", re.I | re.M)
_VENUE_LINE = re.compile(r"^VENUE:\s*(.+)$", re.I | re.M)
_SEC_ROW = re.compile(
    r"Sec(?:tion)?\s*[:.]?\s*(\S+)\s+Row\s*[:.]?\s*(\S+)\s+(?:Seat|Seats)\s*[:.]?\s*(.+)$",
    re.I | re.M,
)
_ORDER = re.compile(r"(?:order\s*(?:#|number|id)[:\s]*)([A-Z0-9\-]+)", re.I)
_MONEY = re.compile(r"\$\s*[\d,]+(?:\.\d{2})?")


def is_sale_email(subject: str, body: str, from_addr: str = "") -> bool:
    sub = subject or ""
    blob = f"{sub}\n{body or ''}"
    if _SALE_FROM.search(from_addr or ""):
        if _SALE_SUBJECT.search(sub) or _SALE_BODY.search(blob):
            return True
    if _SALE_SUBJECT.search(sub) and _SALE_BODY.search(blob):
        return True
    if re.search(r"stubhub", blob, re.I) and re.search(r"\bsold\b", blob, re.I):
        return True
    return False


def parse_sale_hints(subject: str, body: str) -> dict[str, Any]:
    text = f"{subject or ''}\n{body or ''}"
    hints: dict[str, Any] = {"subject": (subject or "").strip()}
    m = _EVENT_LINE.search(text)
    if m:
        hints["event"] = m.group(1).strip()
    m = _DATE_LINE.search(text)
    if m:
        hints["event_date"] = m.group(1).strip()
    m = _VENUE_LINE.search(text)
    if m:
        hints["venue"] = m.group(1).strip()
    seats: list[str] = []
    for sm in _SEC_ROW.finditer(text):
        seats.append(f"Sec {sm.group(1)}  Row {sm.group(2)}  Seat(s) {sm.group(3).strip()}")
    if seats:
        hints["seats_from_email"] = seats
    m = _ORDER.search(text)
    if m:
        hints["order_id"] = m.group(1).strip()
    money = _MONEY.findall(text)
    if money:
        hints["amounts"] = money[:5]
    return hints


def format_sale_alert(
    account: dict,
    msg: dict,
    listings: list[dict],
    hints: dict[str, Any],
) -> str:
    phrase = str(account.get("recovery_phrase") or "").strip()
    email = str(account.get("email") or "")
    acct_event = str(account.get("event") or "").strip()
    lines = [
        "🎟️  TICKET SOLD",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "📧  Worm account",
        f"    {email}",
        "",
        "🔑  Recovery phrase",
        f"    {phrase or '(none on file)'}",
        "",
    ]
    if acct_event:
        lines.extend(["📋  Listed as (account event)", f"    {acct_event}", ""])

    if listings:
        lines.append("🪑  Seats from bot (listed on this account)")
        by_event: dict[str, list[dict]] = {}
        for row in listings:
            key = f"{row.get('event_name')}|{row.get('event_date')}|{row.get('venue')}"
            by_event.setdefault(key, []).append(row)
        for _key, rows in by_event.items():
            first = rows[0]
            lines.append(f"    {first.get('event_name') or 'Event'}")
            if first.get("event_date"):
                lines.append(f"    📅 {first['event_date']}")
            if first.get("venue"):
                lines.append(f"    📍 {first['venue']}")
            for r in rows:
                lines.append(
                    f"       • Sec {r.get('section')}  Row {r.get('row_name')}  Seat {r.get('seat')}"
                )
        lines.append("")
    elif hints.get("seats_from_email"):
        lines.append("🪑  Seats (from sale email)")
        for s in hints["seats_from_email"]:
            lines.append(f"    • {s}")
        lines.append("")

    if hints.get("event"):
        lines.extend(["🎪  Event (email)", f"    {hints['event']}", ""])
    if hints.get("order_id"):
        lines.append(f"🧾  Order: {hints['order_id']}")
    if hints.get("amounts"):
        lines.append(f"💰  Amount: {', '.join(hints['amounts'])}")
    lines.extend(
        [
            "",
            "📬  Inbox subject",
            f"    {hints.get('subject') or msg.get('subject') or '—'}",
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"Account #{account.get('id')} · status {account.get('status')}",
        ]
    )
    return "\n".join(lines)


def format_generic_mail(account: dict, msg: dict, body_preview: str) -> str:
    phrase = str(account.get("recovery_phrase") or "").strip()
    return (
        f"📨  New mail — #{account.get('id')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📧  {account.get('email')}\n"
        f"🔑  {phrase or '(no phrase)'}\n"
        f"From: {msg.get('from') or '—'}\n"
        f"Subject: {msg.get('subject') or '—'}\n\n"
        f"{body_preview}"
    )
