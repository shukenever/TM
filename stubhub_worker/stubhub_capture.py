"""Parse ticket-stock TSV and worker seat replies for capture queue."""
from __future__ import annotations

import csv
import io
import re
from typing import Any

_BARCODE_RE = re.compile(r"^\d{8,}$")


def parse_readable_export(text: str) -> list[dict[str, Any]]:
    """Parse ticket_stock_*_readable.txt blocks."""
    raw = (text or "").replace("\r\n", "\n")
    blocks = re.split(r"-{20,}", raw)
    out: list[dict[str, Any]] = []
    header_re = re.compile(
        r"^(?P<cred>[^|]+)\|\s*(?P<app>[^|]*)\|\s*(?P<event>[^|]*)\|\s*(?P<date>[^|]*)\|\s*(?P<venue>.*)$"
    )
    for block in blocks:
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines or lines[0].startswith("#"):
            continue
        head = lines[0]
        if "@" not in head or "|" not in head:
            continue
        m = header_re.match(head)
        if not m:
            continue
        cred = m.group("cred").strip()
        if ":" not in cred:
            continue
        email, password = cred.split(":", 1)
        email = email.strip().lower()
        password = password.strip()
        if "@" not in email:
            continue
        section = row = seat = ""
        qty = 1
        for ln in lines[1:]:
            low = ln.lower()
            if low.startswith("section:"):
                section = ln.split(":", 1)[1].strip()
            elif low.startswith("row:"):
                row = ln.split(":", 1)[1].strip()
            elif low.startswith("seats:") or low.startswith("seat:"):
                seat = ln.split(":", 1)[1].strip()
            elif low.startswith("quantity:"):
                try:
                    qty = max(1, int(ln.split(":", 1)[1].strip() or "1"))
                except ValueError:
                    qty = 1
        for ch in ("—", "-", "n/a", "none"):
            if section.lower() == ch:
                section = ""
            if row.lower() == ch:
                row = ""
            if seat.lower() == ch:
                seat = ""
        out.append(
            {
                "email": email,
                "password": password,
                "app_login": m.group("app").strip(),
                "event_name": m.group("event").strip(),
                "event_date": m.group("date").strip(),
                "venue": m.group("venue").strip(),
                "qty_expected": qty,
                "_section": section,
                "_row": row,
                "_seat": seat,
            }
        )
    return out


def parse_import_file(text: str) -> list[dict[str, Any]]:
    """TSV stock export or readable blocks."""
    rows = parse_stock_tsv(text)
    if rows:
        return rows
    return parse_readable_export(text)


def parse_stock_tsv(text: str) -> list[dict[str, Any]]:
    """Rows from ticket_stock_*.txt (tab headers)."""
    raw = (text or "").replace("\r\n", "\n").strip()
    if not raw:
        return []
    lines = [ln for ln in raw.split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    raw = "\n".join(lines)
    reader = csv.DictReader(io.StringIO(raw), delimiter="\t")
    if not reader.fieldnames:
        return []
    fields = {f.lower().strip(): f for f in reader.fieldnames if f}

    def col(row: dict, name: str) -> str:
        key = fields.get(name)
        return (row.get(key) or "").strip() if key else ""

    out: list[dict[str, Any]] = []
    for row in reader:
        email = col(row, "email").lower()
        password = col(row, "password")
        event = col(row, "event")
        if not email or "@" not in email or not event:
            continue
        qty = 1
        try:
            qty = max(1, int(col(row, "qty") or "1"))
        except ValueError:
            qty = 1
        out.append(
            {
                "email": email,
                "password": password,
                "app_login": col(row, "app"),
                "event_name": event,
                "event_date": col(row, "date"),
                "venue": col(row, "venue"),
                "qty_expected": qty,
            }
        )
    return out


def parse_seat_reply(text: str, qty_expected: int) -> tuple[list[dict[str, str]], str | None]:
    """
    Accept:
      section: 109\\nrow: C\\nseats: 15,16,17
    or one line per seat:
      109 | C | 15
    """
    lines = [ln.strip() for ln in (text or "").replace("\r\n", "\n").split("\n") if ln.strip()]
    if not lines:
        return [], "Send section, row, and seat(s)."

    block_sec = block_row = ""
    block_seats: list[str] = []
    line_rows: list[dict[str, str]] = []

    for line in lines:
        low = line.lower()
        if low.startswith("section:"):
            block_sec = line.split(":", 1)[1].strip()
            continue
        if low.startswith("row:"):
            block_row = line.split(":", 1)[1].strip()
            continue
        if low.startswith("seats:") or low.startswith("seat:"):
            part = line.split(":", 1)[1]
            for chunk in re.split(r"[,;/\s]+", part):
                if chunk.strip():
                    block_seats.append(chunk.strip())
            continue
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                line_rows.append(
                    {"section": parts[0], "row_name": parts[1], "seat": parts[2], "barcode": ""}
                )
                if len(parts) >= 4 and _BARCODE_RE.match(parts[3].strip()):
                    line_rows[-1]["barcode"] = parts[3].strip()
            continue
        m = re.match(r"sec(?:tion)?\s+(\S+)\s+row\s+(\S+)\s+seat\s+(\S+)", line, re.I)
        if m:
            line_rows.append(
                {
                    "section": m.group(1),
                    "row_name": m.group(2),
                    "seat": m.group(3),
                    "barcode": "",
                }
            )

    if block_sec and block_row and block_seats:
        for s in block_seats:
            line_rows.append(
                {"section": block_sec, "row_name": block_row, "seat": s, "barcode": ""}
            )

    cleaned: list[dict[str, str]] = []
    for r in line_rows:
        sec = (r.get("section") or "").strip()
        row = (r.get("row_name") or "").strip()
        seat = (r.get("seat") or "").strip()
        if not sec or not row or not seat:
            continue
        cleaned.append(
            {
                "section": sec,
                "row_name": row,
                "seat": seat,
                "barcode": (r.get("barcode") or "").strip(),
            }
        )

    if not cleaned:
        return [], "Could not parse seats. Use:\nsection: 109\nrow: C\nseats: 15,16\n\nor one per line:\n109 | C | 15"

    if qty_expected and len(cleaned) != qty_expected:
        return (
            cleaned,
            f"Expected {qty_expected} seat(s), got {len(cleaned)}. Fix and send again, or /capture to release.",
        )
    return cleaned, None


def format_job_card(job: dict, seats: list[dict] | None = None) -> str:
    lines = [
        f"CAPTURE #{job['id']}",
        f"{job['email']}:{job['password']}",
        f"app: {job.get('app_login') or '—'}",
        f"event: {job.get('event_name') or ''}",
        f"date: {job.get('event_date') or '—'}",
        f"venue: {job.get('venue') or '—'}",
        f"qty: {job.get('qty_expected') or 1}",
    ]
    if seats:
        lines.append("— seats —")
        for s in seats:
            bc = f" bc {s['barcode']}" if s.get("barcode") else ""
            lines.append(f"  {s['section']} / {s['row_name']} / {s['seat']}{bc}")
    return "\n".join(lines)
