#!/usr/bin/env python3
"""
Secure-Pass stock CSV helpers: barcode scrape from pass HTML, inject into stock lines,
normalize viewer URLs to tixx.cc gateway.

Used by tm_hit_viewer --reslug-secure-pass-stock and reslug_secure_pass_stock.py.
"""

from __future__ import annotations

import base64
import html
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

_RE_STOCK_URL = re.compile(
    r"(https?://(?:tixx\.(?:cc|pw|lol)|[^/\s]+)/tickets/(?P<gid>\d+)/(?P<slug>[^/?#\s,]+))",
    re.I,
)
_RE_COST_BARCODE_URL = re.compile(
    r"(,\s*)(\$[\d,]+(?:\.[\d]+)?)(\s*,\s*)([^,]+)(\s*,\s*(https?://))",
    re.I,
)
_SAFETIX = re.compile(r'data-tm-safetix\s*=\s*(["\'])(.*?)\1', re.I | re.S)
_BARCODELESS = frozenset({"no", "yes"})


def _iter_safetix_attr_values(doc: str) -> Iterator[str]:
    """Parse data-tm-safetix values without regex backtracking on megabyte lines."""
    marker = "data-tm-safetix"
    pos = 0
    doc = doc or ""
    while True:
        idx = doc.find(marker, pos)
        if idx < 0:
            break
        pos = idx + len(marker)
        eq = doc.find("=", pos)
        if eq < 0 or eq - pos > 24:
            continue
        pos = eq + 1
        while pos < len(doc) and doc[pos] in " \t\n\r":
            pos += 1
        if pos >= len(doc):
            break
        q = doc[pos]
        if q not in ('"', "'"):
            continue
        pos += 1
        start = pos
        while pos < len(doc) and doc[pos] != q:
            pos += 1
        if pos > start:
            yield doc[start:pos]
        pos += 1


def _norm_seat(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _norm_loose_field(s: str, *, numeric: bool = False) -> str:
    v = _norm_seat(s)
    if numeric and v.isdigit():
        return str(int(v))
    return v


def _norm_section(s: str) -> str:
    v = _norm_seat(s)
    if not v:
        return v
    for _ in range(4):
        before = v
        for prefix in (
            "SECTION",
            "SECTOR",
            "SEC",
            "ORCHESTRA",
            "ORCH",
            "FLOOR",
            "FLR",
            "LAWN",
            "PIT",
            "BALCONY",
            "BALC",
            "MEZZ",
            "LOGE",
            "CLUB",
            "SUITE",
            "BSTAND",
            "STAND",
            "LOWER",
            "UPPER",
        ):
            if v.startswith(prefix) and len(v) > len(prefix):
                v = v[len(prefix) :]
                break
        if v == before:
            break
    return v


def _checker_seat_key(email: str, section: str, row: str, seat: str) -> tuple[str, str, str, str]:
    return (
        (email or "").strip().lower(),
        _norm_seat(section),
        _norm_seat(row),
        _norm_seat(seat),
    )


def _checker_seat_key_variants(
    email: str, section: str, row: str, seat: str
) -> set[tuple[str, str, str, str]]:
    em = (email or "").strip().lower()
    if not em:
        return set()
    secs = {_norm_seat(section), _norm_section(section)}
    row_n = _norm_seat(row)
    seat_n = _norm_seat(seat)
    rows = {row_n, _norm_loose_field(row, numeric=row_n.isdigit())}
    seats = {seat_n, _norm_loose_field(seat, numeric=True)}
    out: set[tuple[str, str, str, str]] = set()
    for sec in secs:
        for rw in rows:
            for st in seats:
                if sec or rw or st:
                    out.add((em, sec, rw, st))
    return out


def _norm_order(s: str) -> str:
    return re.sub(r"[^A-Z0-9/]", "", (s or "").upper())


@dataclass
class CheckerBarcodeStore:
    """Recovery barcode index with exact + fuzzy (email/row/seat/order) lookups."""

    exact: dict[tuple[str, str, str, str], str] = field(default_factory=dict)
    loose: dict[tuple[str, str, str], str] = field(default_factory=dict)
    loose_ambiguous: set[tuple[str, str, str]] = field(default_factory=set)
    by_order: dict[tuple[str, str, str, str], str] = field(default_factory=dict)
    order_ambiguous: set[tuple[str, str, str, str]] = field(default_factory=set)
    by_order_seat: dict[tuple[str, str], str] = field(default_factory=dict)
    order_seat_ambiguous: set[tuple[str, str]] = field(default_factory=set)
    email_seat: dict[tuple[str, str], str] = field(default_factory=dict)
    email_seat_ambiguous: set[tuple[str, str]] = field(default_factory=set)
    seat_count: int = 0
    _canonical: set[tuple[str, str, str, str]] = field(default_factory=set, repr=False)

    def __len__(self) -> int:
        return self.seat_count

    def register(
        self,
        email: str,
        section: str,
        row: str,
        seat: str,
        bc: str,
        *,
        purchase_id: str = "",
    ) -> None:
        bc = (bc or "").strip()
        if not bc or bc.lower() in _BARCODELESS:
            return
        em = (email or "").strip().lower()
        if not em:
            return
        row_loose = _norm_loose_field(row, numeric=_norm_seat(row).isdigit())
        seat_loose = _norm_loose_field(seat, numeric=True)
        canon = (
            em,
            _norm_section(section) or _norm_seat(section),
            row_loose,
            seat_loose,
        )
        if canon not in self._canonical:
            self._canonical.add(canon)
            self.seat_count += 1
        for key in _checker_seat_key_variants(em, section, row, seat):
            self.exact.setdefault(key, bc)
        lk = (em, row_loose, seat_loose)
        if lk in self.loose and self.loose[lk] != bc:
            self.loose_ambiguous.add(lk)
        else:
            self.loose.setdefault(lk, bc)
        esk = (em, seat_loose)
        if esk in self.email_seat and self.email_seat[esk] != bc:
            self.email_seat_ambiguous.add(esk)
        else:
            self.email_seat.setdefault(esk, bc)
        oid = _norm_order(purchase_id)
        if oid:
            ok = (em, oid, row_loose, seat_loose)
            if ok in self.by_order and self.by_order[ok] != bc:
                self.order_ambiguous.add(ok)
            else:
                self.by_order.setdefault(ok, bc)
            osk = (oid, seat_loose)
            if osk in self.by_order_seat and self.by_order_seat[osk] != bc:
                self.order_seat_ambiguous.add(osk)
            else:
                self.by_order_seat.setdefault(osk, bc)

    def lookup(
        self,
        email: str,
        section: str,
        row: str,
        seat: str,
        *,
        order_no: str = "",
    ) -> tuple[str, str]:
        em = (email or "").strip().lower()
        row_loose = _norm_loose_field(row, numeric=_norm_seat(row).isdigit())
        seat_loose = _norm_loose_field(seat, numeric=True)
        if em:
            for key in _checker_seat_key_variants(em, section, row, seat):
                bc = self.exact.get(key)
                if bc:
                    return bc, "exact"
            lk = (em, row_loose, seat_loose)
            if lk not in self.loose_ambiguous:
                bc = self.loose.get(lk)
                if bc:
                    return bc, "loose"
            esk = (em, seat_loose)
            if esk not in self.email_seat_ambiguous:
                bc = self.email_seat.get(esk)
                if bc:
                    return bc, "email_seat"
        oid = _norm_order(order_no)
        if oid and em:
            ok = (em, oid, row_loose, seat_loose)
            if ok not in self.order_ambiguous:
                bc = self.by_order.get(ok)
                if bc:
                    return bc, "order"
        if oid:
            osk = (oid, seat_loose)
            if osk not in self.order_seat_ambiguous:
                bc = self.by_order_seat.get(osk)
                if bc:
                    return bc, "order_seat"
        return "", ""

    def lookup_line(self, line: str, stock_seats: dict[str, str]) -> tuple[str, str]:
        sec = stock_seats.get("section", "")
        row = stock_seats.get("row", "")
        seat = stock_seats.get("seat", "")
        order_no = stock_line_order_no(line)
        emails: list[str] = []
        for em in (stock_line_email(line), stock_line_account_email(line)):
            if em and em not in emails:
                emails.append(em)
        for em in emails:
            bc, how = self.lookup(em, sec, row, seat, order_no=order_no)
            if bc:
                return bc, how
        if order_no:
            bc, how = self.lookup("", sec, row, seat, order_no=order_no)
            if bc:
                return bc, how
        return "", ""

def _decode_safetix_cfg(attr: str) -> dict | None:
    try:
        s = html.unescape((attr or "").strip())
        raw = base64.b64decode(s + "=" * (-len(s) % 4))
        d = json.loads(raw.decode("utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _jwt_payload(token: str) -> dict[str, Any]:
    parts = (token or "").strip().split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    try:
        d = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _strip_bc(b: str) -> str:
    return re.sub(r"[A-Fa-f]+$", "", (b or "").strip())


def barcode_display_from_safetix_cfg(cfg: dict) -> str:
    platform = str(cfg.get("platform") or "").lower()
    if platform == "sg":
        return str(cfg.get("v") or "").strip()
    b = str(cfg.get("b") or "").strip()
    if b and b.lower() not in ("demo", "regen"):
        return _strip_bc(b) or b
    t = str(cfg.get("t") or cfg.get("rawToken") or "").strip()
    if not t:
        return ""
    if t.startswith("eyJ") and "." not in t[:40]:
        bc = barcode_from_checker_token(t)
        if bc:
            return bc
    pl = _jwt_payload(t)
    b = str(pl.get("b") or "").strip()
    if b and b.lower() not in ("demo", "regen"):
        return _strip_bc(b) or b
    return ""


_RE_INLINE_SEAT_BC = re.compile(
    r"seat_label:\s*(\S+)\s*-\s*barcode:\s*(\S+)\s*-\s*secure_token:\s*(\S+)",
    re.I,
)
_RE_INLINE_BC = re.compile(
    r"-\s*barcode:\s*(\S+)\s*-\s*secure_token:\s*(\S+)",
    re.I,
)
_COMPACT_SEAT_RE = re.compile(
    r"event_id:\s*([A-Za-z0-9]+)"
    r"\s*-\s*event_name:\s*(.+?)"
    r"\s*-\s*purchase_id:\s*(\S+)"
    r"\s*-\s*section_label:\s*(.+?)"
    r"\s*-\s*row_label:\s*(.+?)"
    r"\s*-\s*seat_type:\s*\S+"
    r"\s*-\s*seat_label:\s*(.+?)"
    r"\s*-\s*barcode:\s*(\S+)"
    r"\s*-\s*secure_token:\s*(\S+)",
    re.I,
)
_UPCOMING_LINE_MARKER = re.compile(
    r"Events:\s*\[|\bBARCODES\s*:",
    re.I,
)
_TICKET_BLOCK_HDR = re.compile(r"^\s*={2,3}\s*(.+?)\s*={2,3}\s*$")
_RECOVERY_BARCODE_BASENAMES = frozenset({
    "tickets.txt",
    "links.txt",
    "tickets",
    "links",
    "custom",
    "unknown",
    "pm",
    "upcoming",
    "upcoming.txt",
    "hits",
    "found_hits",
    "found hits",
    "debug_scan",
    "transfers",
    "recheck hits",
    "weirdhits",
    "success.txt",
    "success",
})
_RECOVERY_DUMP_RE = re.compile(
    r"^(?:upcoming|tickets|pm|hits|found_hits|found hits|debug_scan|transfers|links|"
    r"custom|unknown|weirdhits|recheck hits)"
    r"(?:\s*\(\d+\))?(?:\.txt)?$",
    re.I,
)
_RECOVERY_SKIP_BASENAMES = frozenset({
    "cookiesdb",
    "used_paypal",
    "fresh_paypal",
    "filter_pp.py",
})
_RECOVERY_NOISE_PATH_RE = re.compile(r"\.txt\s*-\s*\d{4}-\d{2}-\d{2}", re.I)


def _is_noise_recovery_path(p: Path) -> bool:
    """Skip accidental export folders like ``azzz....txt - 2026-04-29-12-51-15``."""
    try:
        path_s = str(p)
    except Exception:
        return False
    return bool(_RECOVERY_NOISE_PATH_RE.search(path_s))


def _read_barcode_source_text(path: Path) -> str:
    raw = path.read_bytes()
    if not raw.strip():
        return ""
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace")
    return raw.decode("utf-8", errors="replace")


def _ingest_compact_seat_blocks(
    index: dict[tuple[str, str, str, str], str],
    stripped: str,
    put,
) -> None:
    left = stripped.split("|", 1)[0].strip()
    if "@" not in left:
        return
    email = _line_account_email(left)
    if not email:
        return
    low = stripped.lower()
    if "event_id:" not in low or "section_label:" not in low:
        return
    for m in _COMPACT_SEAT_RE.finditer(stripped):
        sec = m.group(4).strip()
        row = m.group(5).strip()
        seat = m.group(6).strip()
        barcode = m.group(7).strip()
        token = m.group(8).strip()
        bc = barcode if barcode and barcode.lower() not in _BARCODELESS else ""
        if not bc or bc in ("-", ""):
            bc = barcode_from_checker_token(token)
        if bc:
            put(email, sec, row, seat, bc, m.group(3).strip())


def _line_account_email(combo: str) -> str:
    """email:pass, email:pass → Event, or bare email@x.com."""
    s = (combo or "").strip()
    if not s or "@" not in s:
        return ""
    if "→" in s:
        s = s.split("→", 1)[0].strip()
    elif "->" in s:
        s = s.split("->", 1)[0].strip()
    if ":" in s:
        return s.split(":", 1)[0].strip().lower()
    return s.strip().lower()


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


def _normalize_upcoming_pipe_line(line: str) -> str:
    """Normalize Barcodes/BARCODES tail (brackets, casing) before compact parse."""
    line = (line or "").strip().rstrip("|").strip()
    if not line:
        return ""
    line = re.sub(r"\|\s*BARCODES:\s*", "| Barcodes: ", line, flags=re.I)
    m = re.search(r"\|\s*Barcodes:\s*(.*)$", line, re.I)
    if m:
        tail = m.group(1).strip().rstrip("|").strip()
        while tail.startswith("["):
            inner = tail[1:].lstrip()
            if inner.startswith("[") and not re.match(r"event_id\s*:", inner, re.I):
                tail = inner
                continue
            break
        if tail and not tail.startswith("["):
            tail = f"[{tail}"
        if tail and not tail.endswith("]"):
            tail = tail.rstrip("|").strip() + "]"
        line = line[: m.start()] + f"| Barcodes: {tail}"
    return line


def _split_compact_barcodes_payload(payload: str) -> list[str]:
    payload = (payload or "").strip()
    if not payload:
        return []
    if re.fullmatch(r"no\s+secure\s+token", payload.strip(), re.I):
        return []
    chunks = re.split(r"\s*\|\s*(?=event_id\s*:)", payload, flags=re.I)
    out: list[str] = []
    for c in chunks:
        c = c.strip().lstrip("|").strip().lstrip("[").strip()
        c = c.rstrip("|").strip().rstrip("]").strip()
        if re.match(r"event_id\s*:", c, re.I):
            out.append(c)
        elif re.search(r"no\s+secure\s+token", c, re.I):
            continue
        elif "section_label:" in c.lower():
            out.append(c)
    return out


def _ingest_upcoming_pipe_line(stripped: str, put) -> None:
    """
    Upcoming/pm/hits one-liner (tm_hit_viewer compact batch format)::

      email:pass | Events: [...] | ... | BARCODES: event_id: ... - barcode: ... - secure_token: ...
    """
    stripped = _normalize_upcoming_pipe_line(stripped) or stripped
    if not _UPCOMING_LINE_MARKER.search(stripped):
        return
    combo = stripped.split("|", 1)[0].strip()
    email = _line_account_email(combo)
    if not email:
        return

    bc_m = re.search(r"BARCODES\s*:\s*(.*)$", stripped, re.I)
    bc_payload = bc_m.group(1).strip() if bc_m else ""

    chunks = _split_compact_barcodes_payload(bc_payload)
    if not chunks and "event_id:" in stripped.lower():
        em = re.search(r"event_id\s*:", stripped, re.I)
        if em:
            chunks = _split_compact_barcodes_payload(stripped[em.start() :])

    for chunk in chunks:
        fields = _parse_compact_barcode_fields(chunk)
        sec = fields.get("section_label", "")
        row = fields.get("row_label", "")
        seat = fields.get("seat_label", "")
        barcode = (fields.get("barcode") or "").strip()
        token = (fields.get("secure_token") or "").strip()
        bc = barcode if barcode and barcode.lower() not in _BARCODELESS and barcode not in ("-", "") else ""
        if not bc:
            bc = barcode_from_checker_token(token)
        if bc:
            put(email, sec, row, seat, bc, fields.get("purchase_id", ""))


def parse_barcode_from_stock_line(line: str, stock_seats: dict[str, str] | None = None) -> str:
    """
    Some stock rows embed checker output inline:
    ... seat_label: 19 - barcode: 325944... - secure_token: eyJ...
    """
    seat = _norm_seat((stock_seats or {}).get("seat", ""))
    hits: list[tuple[str, str]] = []
    for m in _RE_INLINE_SEAT_BC.finditer(line):
        sl, bc, st = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        if bc.lower() in _BARCODELESS or bc in ("-", ""):
            bc = barcode_from_checker_token(st)
        if bc:
            hits.append((_norm_seat(sl), bc))
    if not hits:
        for m in _RE_INLINE_BC.finditer(line):
            bc, st = m.group(1).strip(), m.group(2).strip()
            if bc.lower() in _BARCODELESS or bc in ("-", ""):
                bc = barcode_from_checker_token(st)
            elif len(bc) < 4:
                bc = barcode_from_checker_token(st)
            if bc:
                hits.append(("", bc))
    if not hits:
        for m in re.finditer(r"secure_token:\s*(\S+)", line, re.I):
            bc = barcode_from_checker_token(m.group(1))
            if bc:
                hits.append(("", bc))
    if not hits:
        return ""
    if seat and len(hits) > 1:
        for sl, bc in hits:
            if sl == seat:
                return bc
    return hits[0][1]


def _title_seats(doc: str) -> dict[str, str]:
    m = re.search(r"<title>([^<]+)</title>", doc, re.I)
    if not m:
        return {}
    bits = [x.strip() for x in re.split(r"\s*[\u00b7\u2022|]\s*", html.unescape(m.group(1)))]
    out: dict[str, str] = {"event": bits[0] if bits else ""}
    for b in bits[1:]:
        bl = b.lower()
        if bl.startswith("sec "):
            out["section"] = b[4:].strip()
        elif bl.startswith("row "):
            out["row"] = b[4:].strip()
        elif bl.startswith("seat "):
            out["seat"] = b[5:].strip()
        elif re.match(r"^\d+$", b):
            out["seat"] = b
    return out


def _body_seats(doc: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for lbl, key in (("SECTION", "section"), ("ROW", "row"), ("SEAT", "seat")):
        sm = re.search(
            rf'<span class="tm-pass-lbl">{lbl}</span>\s*<b>([^<]*)</b>',
            doc,
            re.I,
        )
        if sm:
            val = html.unescape(sm.group(1).strip())
            if val and val not in ("-", "\u2014", "\u2013"):
                out[key] = val
    return out


def is_dead_pass_page(doc: str) -> str | None:
    """Return reason if this HTML is not a live rotating pass."""
    low = (doc or "").lower()
    if "link invalidated" in low or "this link is no longer valid" in low:
        return "invalidated_stub"
    if "your barcode has been killed" in low:
        return "invalidated_stub"
    if "this ticket was transferred" in low:
        return "transferred_stub"
    if "cancelled our parternship" in low:
        return "invalidated_stub"
    if "no rotating barcode" in low and "safetix-slot" not in low:
        return "no_pass"
    return None


def pass_html_has_safetix(doc: str) -> bool:
    if "data-tm-safetix" not in (doc or ""):
        return False
    for _ in _iter_safetix_attr_values(doc):
        return True
    return bool(_SAFETIX.search(doc or ""))


def _first_safetix_cfg(doc: str) -> dict | None:
    for raw in _iter_safetix_attr_values(doc):
        cfg = _decode_safetix_cfg(raw)
        if cfg:
            return cfg
    sm = _SAFETIX.search(doc or "")
    if sm:
        return _decode_safetix_cfg(sm.group(2))
    return None


def extract_barcode_and_seats_from_doc(doc: str, *, html_path: str = "") -> dict[str, Any] | None:
    if is_dead_pass_page(doc):
        return None
    cfg = _first_safetix_cfg(doc)
    if not cfg:
        return None
    barcode = barcode_display_from_safetix_cfg(cfg)
    if not barcode:
        return None
    seats = _body_seats(doc)
    if not seats.get("section"):
        seats.update(_title_seats(doc))
    return {"barcode": barcode, **seats, "html": html_path}


def extract_barcode_and_seats_from_pass_html(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    doc = path.read_text(encoding="utf-8", errors="replace")
    return extract_barcode_and_seats_from_doc(doc, html_path=str(path))


@dataclass
class PassBarcodeIndex:
    """One-time scan of tickets/; O(1) lookups during CSV backfill."""

    by_gid_slug: dict[tuple[str, str], dict[str, Any]]
    by_slug: dict[str, list[dict[str, Any]]]
    by_seat: dict[tuple[str, str, str], list[dict[str, Any]]]
    file_count: int = 0
    with_safetix_attr: int = 0
    rotating_only: int = 0
    with_display_barcode: int = 0

    @classmethod
    def build(
        cls,
        tickets_root: Path,
        *,
        progress: bool = True,
        progress_every: int = 500,
    ) -> PassBarcodeIndex:
        by_gid_slug: dict[tuple[str, str], dict[str, Any]] = {}
        by_slug: dict[str, list[dict[str, Any]]] = {}
        by_seat: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        if not tickets_root.is_dir():
            return cls(by_gid_slug, by_slug, by_seat, 0, 0, 0, 0)

        with_safetix_attr = 0
        rotating_only = 0
        with_display_barcode = 0

        paths = sorted(
            hp
            for gid_dir in tickets_root.iterdir()
            if gid_dir.is_dir()
            for hp in gid_dir.glob("*.html")
            if not hp.name.startswith(".")
        )
        total = len(paths)
        if progress:
            print(f"[*] Indexing {total} pass HTML files (one-time)...", flush=True)

        for i, hp in enumerate(paths, 1):
            if progress and (i == 1 or i % progress_every == 0 or i == total):
                print(f"    {i}/{total} passes indexed", flush=True)
            try:
                doc = hp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "data-tm-safetix" not in doc:
                continue
            if is_dead_pass_page(doc):
                continue
            cfg = _first_safetix_cfg(doc)
            if not cfg:
                continue
            with_safetix_attr += 1
            barcode = barcode_display_from_safetix_cfg(cfg)
            if not barcode:
                rotating_only += 1
                continue
            with_display_barcode += 1
            ex = extract_barcode_and_seats_from_doc(doc, html_path=str(hp))
            if not ex:
                continue
            gid = hp.parent.name
            slug = hp.stem
            rec = {
                "path": hp,
                "gid": gid,
                "slug": slug,
                "barcode": ex["barcode"],
                "section": ex.get("section", ""),
                "row": ex.get("row", ""),
                "seat": ex.get("seat", ""),
            }
            by_gid_slug[(gid, slug)] = rec
            by_slug.setdefault(slug, []).append(rec)
            sk = (
                _norm_seat(rec["section"]),
                _norm_seat(rec["row"]),
                _norm_seat(rec["seat"]),
            )
            if any(sk):
                by_seat.setdefault(sk, []).append(rec)

        if progress:
            print(
                f"[*] Index ready: {len(by_gid_slug)} with display barcode | "
                f"{with_safetix_attr} have data-tm-safetix | "
                f"{rotating_only} rotating-only (regen, no static barcode in HTML)",
                flush=True,
            )
        return cls(
            by_gid_slug,
            by_slug,
            by_seat,
            total,
            with_safetix_attr,
            rotating_only,
            with_display_barcode,
        )

    def lookup(
        self,
        gid: str,
        slug: str,
        stock_seats: dict[str, str],
        alias_map: dict[str, str],
        registry_by_slug: dict[str, list[Path]],
        tickets_root: Path,
    ) -> tuple[dict[str, Any] | None, str | None, str]:
        """Return (record, new_slug, how)."""
        direct = tickets_root / gid / f"{slug}.html"
        if direct.is_file():
            try:
                doc = direct.read_text(encoding="utf-8", errors="replace")
                dead = is_dead_pass_page(doc)
                if dead == "invalidated_stub":
                    tgt = alias_map.get(slug)
                    if tgt:
                        pair = _slug_from_alias_target(tgt)
                        if pair:
                            rec = self.by_gid_slug.get(pair)
                            if rec:
                                return rec, pair[1], "alias"
                    return None, None, "invalidated_stub"
                if dead:
                    return None, None, dead
            except OSError:
                pass

        tried: set[tuple[str, str]] = set()

        def try_key(g: str, s: str) -> tuple[dict[str, Any] | None, str]:
            key = (g, s)
            if key in tried:
                return None, ""
            tried.add(key)
            rec = self.by_gid_slug.get(key)
            if rec:
                how = ""
                if g == "0" and gid != "0":
                    how = "gid0"
                elif g != gid or s != slug:
                    how = "registry"
                return rec, how
            return None, ""

        rec, how = try_key(gid, slug)
        if rec:
            ns = rec["slug"] if rec["slug"] != slug else None
            return rec, ns, how

        if gid != "0":
            rec, how = try_key("0", slug)
            if rec:
                ns = rec["slug"] if rec["slug"] != slug else None
                return rec, ns, how or "gid0"

        for rp in registry_by_slug.get(slug, []):
            g = rp.parent.name
            rec, how = try_key(g, slug)
            if rec:
                ns = rec["slug"] if rec["slug"] != slug else None
                return rec, ns, how or "registry"

        tgt = alias_map.get(slug)
        if tgt:
            pair = _slug_from_alias_target(tgt)
            if pair:
                rec, how = try_key(pair[0], pair[1])
                if rec:
                    return rec, pair[1], "alias"

        sec = stock_seats.get("section", "")
        row = stock_seats.get("row", "")
        seat = stock_seats.get("seat", "")
        if sec or row or seat:
            sk = (_norm_seat(sec), _norm_seat(row), _norm_seat(seat))
            matches = self.by_seat.get(sk, [])
            if len(matches) == 1:
                rec = matches[0]
                ns = rec["slug"] if rec["slug"] != slug else None
                return rec, ns, "seat_scan"

        if direct.is_file():
            try:
                doc = direct.read_text(encoding="utf-8", errors="replace")
                if is_dead_pass_page(doc):
                    return None, None, is_dead_pass_page(doc) or "dead"
                if _first_safetix_cfg(doc):
                    return None, None, "rotating_only"
                if "safetix-slot" in doc or "bwip-js" in doc:
                    return None, None, "no_safetix"
            except OSError:
                pass
        return None, None, "no_html"


def resolve_live_pass_html(
    tickets_root: Path,
    gid: str,
    slug: str,
    stock_seats: dict[str, str],
    alias_map: dict[str, str],
    registry_by_slug: dict[str, list[Path]] | None = None,
    index: PassBarcodeIndex | None = None,
) -> tuple[Path | None, str | None, str]:
    """
    Find live pass HTML for a stock slug.
    Returns (path, new_slug_if_resolved, skip_reason).
    """
    registry_by_slug = registry_by_slug or {}
    if index is not None:
        rec, new_slug, how = index.lookup(
            gid, slug, stock_seats, alias_map, registry_by_slug, tickets_root
        )
        if rec:
            return rec["path"], new_slug, how
        return None, None, how

    # Slow fallback (no index): candidates only, no full-site scan.
    direct = tickets_root / gid / f"{slug}.html"
    if direct.is_file():
        doc = direct.read_text(encoding="utf-8", errors="replace")
        dead = is_dead_pass_page(doc)
        if dead == "invalidated_stub":
            tgt = alias_map.get(slug)
            if tgt:
                pair = _slug_from_alias_target(tgt)
                if pair:
                    ng, ns = pair
                    cand = tickets_root / ng / f"{ns}.html"
                    if cand.is_file():
                        ex = extract_barcode_and_seats_from_pass_html(cand)
                        if ex:
                            return cand, ns, "alias"
            return None, None, "invalidated_stub"
        if dead:
            return None, None, dead

    for cand in _pass_path_candidates(tickets_root, gid, slug, alias_map, registry_by_slug):
        try:
            doc = cand.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if is_dead_pass_page(doc):
            continue
        if not pass_html_has_safetix(doc):
            continue
        ex = extract_barcode_and_seats_from_doc(doc, html_path=str(cand))
        if not ex:
            continue
        new_slug = cand.stem if cand.stem != slug else None
        how = ""
        if cand != direct:
            if cand.parent.name == "0" and gid != "0":
                how = "gid0"
            elif any(cand == rp for rp in registry_by_slug.get(slug, [])):
                how = "registry"
            elif alias_map.get(slug):
                how = "alias"
        return cand, new_slug, how

    if direct.is_file():
        doc = direct.read_text(encoding="utf-8", errors="replace")
        if is_dead_pass_page(doc):
            return None, None, is_dead_pass_page(doc) or "dead"
        if "safetix-slot" in doc or "bwip-js" in doc:
            return None, None, "no_safetix"
    return None, None, "no_html"


def load_slug_alias_map(vercel_site: Path) -> dict[str, str]:
    """old_slug -> tickets/gid/newslug.html"""
    p = vercel_site / "tm_viewer_pass_slug_aliases.json"
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return {}
    red = raw.get("redirects") if isinstance(raw, dict) else None
    if not isinstance(red, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in red.items():
        ks, vs = str(k).strip(), str(v).strip().replace("\\", "/")
        if ks and vs:
            out[ks] = vs
    return out


def _slug_from_alias_target(target: str) -> tuple[str, str] | None:
    m = re.search(r"tickets/(\d+)/([^/]+)\.html", target.replace("\\", "/"), re.I)
    if not m:
        return None
    return m.group(1), m.group(2)


def load_registry_slug_paths(vercel_site: Path) -> dict[str, list[Path]]:
    """slug -> canonical pass HTML paths from tm_viewer_link_registry.json."""
    p = vercel_site / "tm_viewer_link_registry.json"
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return {}
    by_email = raw.get("by_email") if isinstance(raw, dict) else None
    if not isinstance(by_email, dict):
        return {}
    out: dict[str, list[Path]] = {}
    seen: set[str] = set()
    for entries in by_email.values():
        if not isinstance(entries, list):
            continue
        for ent in entries:
            if not isinstance(ent, dict):
                continue
            rel = str(ent.get("path") or "").strip().replace("\\", "/")
            if not rel.endswith(".html"):
                continue
            slug = rel.rsplit("/", 1)[-1][:-5]
            if not slug:
                continue
            key = rel.lower()
            if key in seen:
                continue
            seen.add(key)
            out.setdefault(slug, []).append(vercel_site / rel)
    return out


def _pass_path_candidates(
    tickets_root: Path,
    gid: str,
    slug: str,
    alias_map: dict[str, str],
    registry_by_slug: dict[str, list[Path]],
) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []

    def add(p: Path) -> None:
        s = str(p)
        if s in seen or not p.is_file():
            return
        seen.add(s)
        out.append(p)

    add(tickets_root / gid / f"{slug}.html")
    if gid != "0":
        add(tickets_root / "0" / f"{slug}.html")
    for rp in registry_by_slug.get(slug, []):
        add(rp)
    tgt = alias_map.get(slug)
    if tgt:
        pair = _slug_from_alias_target(tgt)
        if pair:
            ng, ns = pair
            add(tickets_root / ng / f"{ns}.html")
    return out


def replace_stock_line_slug(
    line: str,
    gid: str,
    old_slug: str,
    new_slug: str,
    public_base: str = "https://tixx.cc",
) -> str:
    if old_slug == new_slug:
        return normalize_stock_line_viewer_url(line, public_base)
    gid_esc = re.escape(gid)
    old_esc = re.escape(old_slug)
    nl = re.sub(
        rf"(https?://[^\s,\"'<>\[\]]+/tickets/{gid_esc}/){old_esc}(?:\.html)?",
        rf"\g<1>{new_slug}",
        line,
        flags=re.I,
    )
    if nl == line:
        nl = re.sub(
            rf"(https?://[^\s,\"'<>\[\]]+/tickets/\d+/){old_esc}(?:\.html)?",
            rf"\g<1>{new_slug}",
            line,
            flags=re.I,
        )
    return normalize_stock_line_viewer_url(nl, public_base)


def stock_line_ticket_ref(line: str) -> tuple[str, str, str] | None:
    m = _RE_STOCK_URL.search(line)
    if not m:
        return None
    return m.group("gid"), m.group("slug"), m.group(0).rstrip(".,)")


def normalize_stock_line_viewer_url(line: str, public_base: str = "https://tixx.cc") -> str:
    base = (public_base or "https://tixx.cc").rstrip("/")

    def _repl(m: re.Match) -> str:
        gid, slug = m.group("gid"), m.group("slug")
        return f"{base}/tickets/{gid}/{slug}"

    return _RE_STOCK_URL.sub(_repl, line)


def stock_line_barcode_field(line: str) -> str:
    m = _RE_COST_BARCODE_URL.search(line)
    return m.group(4).strip() if m else ""


def set_stock_line_barcode_field(line: str, barcode: str) -> str:
    bc = (barcode or "").strip()
    if not bc or bc.lower() in _BARCODELESS:
        return line
    if "," in bc:
        return line

    m = _RE_COST_BARCODE_URL.search(line)
    if not m:
        return line
    cur = m.group(4).strip()
    if cur == bc:
        return line
    if cur.lower() not in _BARCODELESS and len(cur) >= 8:
        return line
    return line[: m.start(4)] + bc + line[m.end(4) :]


def _seat_field_match(stock_val: str, html_val: str) -> bool:
    sv = (stock_val or "").strip()
    hv = (html_val or "").strip()
    if not sv or not hv:
        return True
    if "+" in sv:
        segs = [_norm_seat(x) for x in re.split(r"\s*\+\s*", sv) if x.strip()]
        return _norm_seat(hv) in segs
    return _norm_seat(sv) == _norm_seat(hv)


def stock_line_email(line: str) -> str:
    left = line.split("|", 1)[0].strip()
    if "@" in left and ":" in left:
        return left.split(":", 1)[0].strip().lower()
    return ""


def stock_line_order_no(line: str) -> str:
    """OrderNo column in stock CSV (e.g. 32-27623/ATL)."""
    if "|" not in line:
        return ""
    payload = line.split("|", 1)[1].strip()
    um = re.search(r",((?:https?://)[^,\s]+)", payload)
    if um:
        payload = payload[: um.start()].strip()
    m = re.search(r",(\$[\d,]+(?:\.[\d]+)?)\s*,\s*(?:No|Yes|[^,]+)\s*$", payload, re.I)
    if m:
        payload = payload[: m.start()].strip()
    parts = [p.strip() for p in payload.split(",")]
    if len(parts) >= 5:
        return parts[4]
    return ""


def stock_line_account_email(line: str) -> str:
    """Account column in stock CSV (may differ from combo email on some rows)."""
    if "|" not in line:
        return ""
    payload = line.split("|", 1)[1].strip()
    um = re.search(r",((?:https?://)[^,\s]+)", payload)
    if um:
        payload = payload[: um.start()].strip()
    m = re.search(r",(\$[\d,]+(?:\.[\d]+)?)\s*,\s*(?:No|Yes|[^,]+)\s*$", payload, re.I)
    if m:
        payload = payload[: m.start()].strip()
    parts = [p.strip() for p in payload.split(",")]
    if len(parts) >= 6 and "@" in parts[5]:
        return parts[5].split(":", 1)[0].strip().lower()
    return ""

def _decode_secure_token_b64(token_b64: str) -> dict | None:
    try:
        raw = base64.b64decode((token_b64 or "").strip() + "=" * (-len(token_b64.strip()) % 4)).decode("utf-8")
        d = json.loads(raw)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def barcode_from_checker_token(st: str) -> str:
    """Display barcode from checker Secure Token (JWT or base64 JSON wrapper)."""
    st = (st or "").strip()
    if not st:
        return ""
    if st.startswith("eyJ"):
        pl = _jwt_payload(st)
        b = str(pl.get("b") or "").strip()
        if b and b.lower() not in ("demo", "regen"):
            return _strip_bc(b) or b
    tok = _decode_secure_token_b64(st)
    if tok:
        inner_t = str(tok.get("t") or "").strip()
        pl = _jwt_payload(inner_t) if inner_t.startswith("eyJ") else {}
        b = str(pl.get("b") or tok.get("b") or "").strip()
        if b and b.lower() not in ("demo", "regen"):
            return _strip_bc(b) or b
    return ""


def ingest_barcode_text_into_store(text: str, store: CheckerBarcodeStore) -> tuple[int, int]:
    """
    Parse mixed checker/recovery text into ``store``.
    Returns (new_unique_seats_added, barcodes_parsed_from_file).
    """
    before = store.seat_count
    parsed = 0

    def put(
        email: str,
        sec: str,
        row: str,
        seat: str,
        bc: str,
        purchase_id: str = "",
    ) -> None:
        nonlocal parsed
        parsed += 1
        store.register(email, sec, row, seat, bc, purchase_id=purchase_id)

    text = (text or "").strip()
    if text.startswith("{") or text.startswith("["):
        try:
            json.loads(text)
            _ingest_json_barcode_text(text, put)
            return store.seat_count - before, parsed
        except json.JSONDecodeError:
            pass

    # Upcoming/pm/hits compact pipe format (primary — matches tm_hit_viewer)
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("="):
            continue
        if stripped.startswith("{") and '"results"' in stripped:
            _ingest_json_barcode_text(stripped, put)
            continue
        _ingest_upcoming_pipe_line(stripped, put)

    # Legacy regex pass for inline stock-style event_id blocks
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("="):
            continue
        if _UPCOMING_LINE_MARKER.search(stripped):
            continue
        _ingest_compact_seat_blocks({}, stripped, put)

    # === email:pass | Ticket N === blocks (2 or 3 equals)
    i = 0
    lines = text.splitlines()
    while i < len(lines):
        m = _TICKET_BLOCK_HDR.match(lines[i])
        if not m:
            i += 1
            continue
        combo = m.group(1).split("|", 1)[0].strip()
        email = combo.split(":", 1)[0].strip().lower() if "@" in combo else ""
        i += 1
        sec = row = seat = purchase_id = ""
        barcode = secure = ""
        while i < len(lines) and not _TICKET_BLOCK_HDR.match(lines[i]):
            s = lines[i].strip()
            if s.startswith("---") and len(s) >= 3:
                i += 1
                break
            for part in re.split(r"\s*\|\s*", s):
                part = part.strip()
                sm = re.match(r"^Section:\s*(.+)$", part, re.I)
                if sm:
                    sec = sm.group(1).strip()
                rm = re.match(r"^Row:\s*(.+)$", part, re.I)
                if rm:
                    row = rm.group(1).strip()
                sem = re.match(r"^Seat:\s*(.+)$", part, re.I)
                if sem:
                    seat = sem.group(1).strip()
                pm = re.match(r"^(?:Purchase(?:\s+ID)?|Order(?:\s+No)?):\s*(\S+)$", part, re.I)
                if pm:
                    purchase_id = pm.group(1).strip()
            bm = re.match(r"^Barcode:\s*(\S+)$", s, re.I)
            if bm:
                v = bm.group(1).strip()
                if v and v not in ("-", ""):
                    barcode = v
            bvm = re.match(r"^Barcode Value:\s*(\S+)$", s, re.I)
            if bvm:
                barcode = bvm.group(1).strip()
            pm = re.match(r"^(?:Purchase(?:\s+ID)?|Order(?:\s+No)?):\s*(\S+)$", s, re.I)
            if pm:
                purchase_id = pm.group(1).strip()
            tm = re.match(r"^Secure Token:\s*(\S+)$", s, re.I)
            if tm:
                secure = tm.group(1).strip()
            i += 1
        bc = barcode or barcode_from_checker_token(secure)
        if email and bc:
            put(email, sec, row, seat, bc, purchase_id)

    # Pipe rows: email:pass | event | sec/row/seat | ... | barcode? | secure_token
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("="):
            continue
        if re.search(r"Events:\s*\[|BARCODES:", s, re.I):
            continue
        parts = [p.strip() for p in s.split("|")]
        if len(parts) < 7:
            continue
        combo = parts[0]
        if "@" not in combo or ":" not in combo:
            continue
        email = combo.split(":", 1)[0].strip().lower()
        seat_bits = [x.strip() for x in (parts[2] or "").split("/") if x.strip()]
        sec = seat_bits[0] if len(seat_bits) > 0 else ""
        row = seat_bits[1] if len(seat_bits) > 1 else ""
        seat = seat_bits[2] if len(seat_bits) > 2 else ""
        bc = ""
        if len(parts) > 5 and parts[5] and parts[5].lower() not in _BARCODELESS and len(parts[5]) >= 6:
            bc = parts[5]
        secure = parts[6] if len(parts) > 6 else ""
        if not bc:
            bc = barcode_from_checker_token(secure)
        if bc:
            put(email, sec, row, seat, bc)

    # Stock CSV / links.txt rows: email:pass | EventId,...,Sec,Row,Seat,$Cost,No,URL
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or raw.startswith("="):
            continue
        if "@" not in raw or "|" not in raw:
            continue
        if re.search(r"Events:\s*\[|BARCODES:", raw, re.I):
            continue
        seats = parse_stock_seat_fields(raw)
        if not any(seats.values()):
            continue
        email = stock_line_email(raw)
        if not email:
            continue
        bc = parse_barcode_from_stock_line(raw, seats)
        if bc:
            put(
                email,
                seats.get("section", ""),
                seats.get("row", ""),
                seats.get("seat", ""),
                bc,
                stock_line_order_no(raw),
            )

    return store.seat_count - before, parsed


def _ingest_json_barcode_text(blob: str, put) -> None:
    """SMP my-events JSON (whole file or one line) → compact pipe ingest."""
    blob = (blob or "").strip()
    if not blob:
        return
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return
    items: list[dict] = []
    if isinstance(data, dict):
        items = [data]
    elif isinstance(data, list):
        items = [x for x in data if isinstance(x, dict)]
    for item in items:
        results = item.get("results") or item.get("events") or []
        if not isinstance(results, list):
            continue
        creds = (
            str(item.get("email") or item.get("account") or item.get("creds") or "")
            .strip()
        )
        if not creds or "@" not in creds:
            creds = "unknown@local"
        for ev in results:
            if not isinstance(ev, dict):
                continue
            tickets = ev.get("tickets") or []
            if not isinstance(tickets, list):
                continue
            eid = str(ev.get("eventId") or ev.get("event_id") or "").strip()
            ename = str(ev.get("eventName") or ev.get("event_name") or "Event").strip()
            for t in tickets:
                if not isinstance(t, dict):
                    continue
                sec = str(
                    t.get("section_label")
                    or t.get("section")
                    or t.get("sectionName")
                    or ""
                ).strip()
                row = str(t.get("row_label") or t.get("row") or t.get("rowName") or "").strip()
                seat = str(t.get("seat_label") or t.get("seat") or t.get("seatName") or "").strip()
                bc = str(t.get("barcode") or t.get("barcodeValue") or "").strip()
                token = str(
                    t.get("secure_token")
                    or t.get("secureToken")
                    or t.get("token")
                    or ""
                ).strip()
                if not bc or bc.lower() in _BARCODELESS:
                    bc = barcode_from_checker_token(token)
                if not bc:
                    continue
                em = creds.split(":", 1)[0].strip().lower() if "@" in creds else creds.lower()
                pid = str(t.get("purchase_id") or t.get("purchaseId") or t.get("orderId") or "").strip()
                put(em, sec, row, seat, bc, pid or "")


def load_barcode_index_from_text(text: str) -> dict[tuple[str, str, str, str], str]:
    """Legacy dict view (exact keys only). Prefer ``load_checker_barcode_index``."""
    store = CheckerBarcodeStore()
    ingest_barcode_text_into_store(text, store)
    return dict(store.exact)


def load_checker_barcode_index(tickets_path: Path) -> CheckerBarcodeStore:
    """Load barcode index from a recovery/checker file path."""
    store = CheckerBarcodeStore()
    if tickets_path.is_file():
        ingest_barcode_text_into_store(_read_barcode_source_text(tickets_path), store)
    return store


def resolve_recovery_root(site_dir: Path, data_dir: Path) -> Path | None:
    """tm.bz/Data_for_recovery (or STUBBY_RECOVERY_ROOT env)."""
    env = (os.environ.get("STUBBY_RECOVERY_ROOT") or "").strip()
    if env:
        p = Path(env).expanduser()
        return p if p.is_dir() else None
    for cand in (
        site_dir / "Data_for_recovery",
        data_dir / "tm.bz" / "Data_for_recovery",
        site_dir.parent / "Data_for_recovery",
        data_dir / "Data_for_recovery",
    ):
        if cand.is_dir():
            return cand
    return None


def _is_recovery_barcode_file(p: Path) -> bool:
    if not p.is_file():
        return False
    name = p.name.lower()
    if name in _RECOVERY_SKIP_BASENAMES:
        return False
    if name.endswith(".py"):
        return False
    if name in _RECOVERY_BARCODE_BASENAMES:
        return True
    if _RECOVERY_DUMP_RE.match(p.name.strip()):
        return True
    if name.endswith(".txt") and any(
        x in name for x in ("ticket", "link", "hit", "upcoming", "transfer", "pm", "found", "debug")
    ):
        return True
    if any(x in name for x in ("found_hits", "found hits", "debug_scan")):
        return True
    return False


def find_recovery_barcode_files(recovery_root: Path | None) -> list[Path]:
    """
    Barcode sources under Data_for_recovery:
    - Total Results: pm, upcoming, upcoming (2), hits, ...
    - dated folders: tickets, tickets (3), tickets.txt, links.txt, ...
    """
    if not recovery_root or not recovery_root.is_dir():
        return []
    try:
        root_r = recovery_root.resolve()
    except OSError:
        return []
    seen: set[str] = set()
    found: list[tuple[float, Path]] = []

    def add(p: Path) -> None:
        if _is_noise_recovery_path(p):
            return
        if not _is_recovery_barcode_file(p):
            return
        try:
            if p.stat().st_size > 400_000_000:
                return
        except OSError:
            return
        try:
            p.resolve().relative_to(root_r)
        except (OSError, ValueError):
            return
        key = str(p.resolve())
        if key in seen:
            return
        seen.add(key)
        try:
            mt = p.stat().st_mtime
        except OSError:
            mt = 0.0
        found.append((mt, p))

    try:
        for p in recovery_root.rglob("*"):
            if p.is_file():
                add(p)
    except OSError:
        pass

    found.sort(key=lambda x: -x[0])
    out = [p for _, p in found]
    dump_hits = [p for p in out if _RECOVERY_DUMP_RE.match(p.name.strip()) or "upcoming" in p.name.lower()]
    if dump_hits:
        print(f"    recovery dumps matched: {len(dump_hits)} file(s)", flush=True)
        upcoming_hits = [p for p in dump_hits if "upcoming" in p.name.lower()]
        if upcoming_hits:
            print(f"      upcoming: {len(upcoming_hits)} file(s)", flush=True)
        for p in dump_hits[:25]:
            print(f"      - {p}", flush=True)
        if len(dump_hits) > 25:
            print(f"      ... and {len(dump_hits) - 25} more", flush=True)
    return out


def _is_barcode_dump_name(name: str) -> bool:
    nm = (name or "").strip()
    if not nm:
        return False
    if nm.lower() in ("tickets.txt", "links.txt", "tickets", "links"):
        return True
    return bool(_RECOVERY_DUMP_RE.match(nm))


def _barcode_source_priority(p: Path) -> tuple[int, float]:
    """Lower tier = merged first (upcoming/pm/hits before tickets.txt)."""
    name = p.name.lower()
    if "upcoming" in name:
        tier = 0
    elif name in ("pm", "hits", "transfers", "recheck hits", "weirdhits") or _RECOVERY_DUMP_RE.match(
        p.name.strip()
    ):
        tier = 1
    elif name in ("tickets.txt", "tickets", "links.txt", "links"):
        tier = 3
    else:
        tier = 2
    try:
        mt = -p.stat().st_mtime
    except OSError:
        mt = 0.0
    return tier, mt


def _path_under_root(p: Path, root: Path | None) -> bool:
    if not root:
        return False
    try:
        p_case = os.path.normcase(str(p.resolve()))
        r_case = os.path.normcase(str(root.resolve()))
        return p_case == r_case or p_case.startswith(r_case + os.sep)
    except OSError:
        return False


def find_checker_tickets_files(*roots: Path) -> list[Path]:
    """Find checker/recovery barcode dumps under tm.bz / stubhub (incl. upcoming.txt anywhere)."""
    seen: set[str] = set()
    found: list[tuple[tuple[int, float], Path]] = []

    def add(p: Path) -> None:
        if not p.is_file():
            return
        if not _is_recovery_barcode_file(p) and not _is_barcode_dump_name(p.name):
            return
        try:
            if p.stat().st_size > 400_000_000:
                return
        except OSError:
            return
        key = str(p.resolve())
        if key in seen:
            return
        seen.add(key)
        found.append((_barcode_source_priority(p), p))

    for root in roots:
        if not root:
            continue
        root = Path(root)
        if not root.is_dir():
            continue
        for rel in (
            "tickets.txt",
            "upcoming",
            "upcoming.txt",
            "pm",
            "hits",
            "transfers",
            "results/tickets.txt",
            "results/upcoming.txt",
            "results/upcoming",
            "results/checker/tickets.txt",
            "checker/tickets.txt",
            "checker/upcoming.txt",
            "archive/tickets.txt",
            "archive/upcoming.txt",
            "xt/results/tickets.txt",
            "tm-fcap-makefast/checker/results/tickets.txt",
            "Total Results/upcoming",
            "Total Results/upcoming.txt",
            "Total Results/pm",
            "Total Results/hits",
        ):
            add(root / rel)
        try:
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                nl = p.name.lower()
                if nl in ("tickets.txt", "links.txt"):
                    add(p)
                elif _RECOVERY_DUMP_RE.match(p.name.strip()):
                    add(p)
                elif "upcoming" in nl and nl.endswith(".txt"):
                    add(p)
        except OSError:
            pass

    found.sort(key=lambda x: x[0])
    return [p for _, p in found]


def merge_checker_barcode_indices(
    paths: list[Path],
    *,
    recovery_root: Path | None = None,
) -> CheckerBarcodeStore:
    store = CheckerBarcodeStore()
    rec_root: Path | None = None
    if recovery_root:
        try:
            rec_root = recovery_root.resolve()
        except OSError:
            rec_root = recovery_root

    ordered = sorted(paths, key=_barcode_source_priority)
    upcoming_n = sum(1 for p in ordered if "upcoming" in p.name.lower())
    dump_n = sum(
        1
        for p in ordered
        if _RECOVERY_DUMP_RE.match(p.name.strip()) or "upcoming" in p.name.lower()
    )
    if dump_n:
        print(
            f"[*] Merging barcode dumps: {upcoming_n} upcoming, {dump_n} total pm/upcoming/hits/...",
            flush=True,
        )

    empty_dumps: list[Path] = []
    empty_upcoming_nonempty: list[tuple[Path, int]] = []
    dup_upcoming: list[tuple[Path, int]] = []
    loaded = 0
    upcoming_loaded = 0
    parsed_total = 0
    for p in ordered:
        if not p.is_file():
            continue
        new_added, parsed = ingest_barcode_text_into_store(_read_barcode_source_text(p), store)
        parsed_total += parsed
        is_dump = _RECOVERY_DUMP_RE.match(p.name.strip()) or "upcoming" in p.name.lower()
        is_upcoming = "upcoming" in p.name.lower()
        under_rec = _path_under_root(p, rec_root)
        tag = "recovery" if under_rec else "checker"
        if parsed <= 0:
            if is_dump:
                empty_dumps.append(p)
            if is_upcoming:
                try:
                    sz = p.stat().st_size
                except OSError:
                    sz = 0
                if sz > 80:
                    empty_upcoming_nonempty.append((p, sz))
            continue
        loaded += 1
        if is_upcoming:
            upcoming_loaded += 1
        if new_added <= 0:
            dup_upcoming.append((p, parsed))
            print(
                f"    {tag} source: {p} (0 new, {parsed} barcodes parsed — already in index)",
                flush=True,
            )
        else:
            print(
                f"    {tag} source: {p} (+{new_added} new seats, {parsed} parsed)",
                flush=True,
            )
    if empty_dumps:
        print(
            f"    skipped {len(empty_dumps)} empty/unparseable dump file(s)",
            flush=True,
        )
        for p in empty_dumps[:8]:
            print(f"      - {p.name} ({p.parent.name})", flush=True)
        if len(empty_dumps) > 8:
            print(f"      ... and {len(empty_dumps) - 8} more", flush=True)
    if upcoming_loaded:
        print(f"    upcoming files with barcodes: {upcoming_loaded}", flush=True)
    if dup_upcoming:
        print(
            f"    upcoming scanned (duplicate seats, still parsed): {len(dup_upcoming)} file(s)",
            flush=True,
        )
        for p, n in dup_upcoming[:5]:
            print(f"      - {p.name} ({n} barcodes)", flush=True)
    if loaded:
        print(
            f"    loaded {loaded} file(s) with barcodes ({parsed_total} total barcodes parsed)",
            flush=True,
        )
    if empty_upcoming_nonempty:
        print(
            f"    [!] {len(empty_upcoming_nonempty)} upcoming file(s) have data but 0 barcodes parsed "
            f"(event-only / no secure_token lines?)",
            flush=True,
        )
        for p, sz in empty_upcoming_nonempty[:5]:
            print(f"      - {p} ({sz} bytes)", flush=True)
    if store.seat_count:
        print(
            f"    merged index: {store.seat_count} unique seats | "
            f"{len(store.exact)} lookup keys | "
            f"{len(store.loose)} email/row/seat fallbacks"
            + (f" | {len(store.loose_ambiguous)} ambiguous loose keys skipped" if store.loose_ambiguous else ""),
            flush=True,
        )
    return store


def build_checker_barcode_index_for_layout(
    site_dir: Path,
    data_dir: Path,
    *,
    include_checker_paths: bool = False,
    extra_paths: list[Path] | None = None,
) -> tuple[CheckerBarcodeStore, list[Path]]:
    """
    Merge barcode text from ``Data_for_recovery`` (upcoming, pm, hits, found_hits, …)
    and optionally live checker paths under tm.bz. ``tickets.txt`` is not required.
    """
    recovery_root = resolve_recovery_root(site_dir, data_dir)
    sources: list[Path] = list(find_recovery_barcode_files(recovery_root))
    if recovery_root:
        print(
            f"[*] Data_for_recovery: {recovery_root} ({len(sources)} barcode source file(s))",
            flush=True,
        )
    elif (os.environ.get("STUBBY_RECOVERY_ROOT") or "").strip():
        print("[!] STUBBY_RECOVERY_ROOT set but folder missing", flush=True)
    else:
        print(
            "[!] Data_for_recovery not found under tm.bz — set STUBBY_RECOVERY_ROOT or place "
            "upcoming/pm/hits dumps in tm.bz/Data_for_recovery",
            flush=True,
        )

    if include_checker_paths or (
        (os.environ.get("STUBBY_BARCODE_INCLUDE_CHECKER") or "").strip().lower()
        in ("1", "true", "yes")
    ):
        checker_paths = find_checker_tickets_files(
            site_dir,
            data_dir,
            site_dir.parent if site_dir.parent != site_dir else site_dir,
            site_dir / "tm-vercel-site" if (site_dir / "tm-vercel-site").is_dir() else site_dir,
        )
        seen_src: set[str] = {str(p.resolve()) for p in sources if p.is_file()}
        added = 0
        for p in checker_paths:
            key = str(p.resolve()) if p.is_file() else str(p)
            if key in seen_src:
                continue
            seen_src.add(key)
            sources.append(p)
            added += 1
        if added:
            print(f"[*] +{added} live checker path(s) (STUBBY_BARCODE_INCLUDE_CHECKER)", flush=True)

    for p in extra_paths or []:
        pp = Path(p).expanduser()
        if not pp.is_file():
            continue
        key = str(pp.resolve())
        if key not in {str(x.resolve()) for x in sources if x.is_file()}:
            sources.append(pp)

    sources.sort(key=_barcode_source_priority)
    store = merge_checker_barcode_indices(sources, recovery_root=recovery_root)
    if store:
        print(
            f"[*] Barcode index: {store.seat_count} seats from {len(sources)} source file(s)",
            flush=True,
        )
    elif sources:
        print(f"[!] Found {len(sources)} source file(s) but parsed 0 barcodes", flush=True)
    return store, sources


def lookup_checker_barcode(
    store: CheckerBarcodeStore | dict[tuple[str, str, str, str], str],
    line: str,
    stock_seats: dict[str, str],
) -> str:
    if isinstance(store, CheckerBarcodeStore):
        bc, _how = store.lookup_line(line, stock_seats)
        return bc
    email = stock_line_email(line)
    acct = stock_line_account_email(line)
    sec = stock_seats.get("section", "")
    row = stock_seats.get("row", "")
    seat = stock_seats.get("seat", "")
    for em in (email, acct):
        if not em:
            continue
        for key in _checker_seat_key_variants(em, sec, row, seat):
            bc = store.get(key)
            if bc:
                return bc
    return ""


def lookup_checker_barcode_detailed(
    store: CheckerBarcodeStore | dict[tuple[str, str, str, str], str],
    line: str,
    stock_seats: dict[str, str],
) -> tuple[str, str]:
    if isinstance(store, CheckerBarcodeStore):
        return store.lookup_line(line, stock_seats)
    return lookup_checker_barcode(store, line, stock_seats), ""


def parse_stock_seat_fields(line: str) -> dict[str, str]:
    payload = line.split("|", 1)[1].strip() if "|" in line else line.strip()
    um = re.search(r",((?:https?://)[^,\s]+)", payload)
    if um:
        payload = payload[: um.start()].strip()
    m = re.search(r",(\$[\d,]+(?:\.[\d]+)?)\s*,\s*(?:No|Yes|[^,]+)\s*$", payload, re.I)
    if m:
        payload = payload[: m.start()].strip()
    parts = payload.rsplit(",", 3)
    if len(parts) >= 3:
        return {"section": parts[-3].strip(), "row": parts[-2].strip(), "seat": parts[-1].strip()}
    return {}


@dataclass
class BackfillReport:
    total: int = 0
    updated_barcode: int = 0
    updated_url: int = 0
    updated_slug: int = 0
    skipped_no_html: int = 0
    skipped_no_safetix: int = 0
    skipped_rotating_only: int = 0
    skipped_invalidated_stub: int = 0
    skipped_transferred_stub: int = 0
    skipped_seat_mismatch: int = 0
    skipped_already: int = 0
    resolved_via_alias: int = 0
    resolved_via_seat_scan: int = 0
    resolved_via_gid0: int = 0
    resolved_via_registry: int = 0
    updated_from_checker: int = 0
    updated_from_checker_fuzzy: int = 0
    updated_from_checker_order: int = 0
    updated_from_stock_inline: int = 0
    errors: list[str] = field(default_factory=list)


def _tally_checker_match(report: BackfillReport, how: str) -> None:
    if how in ("order", "order_seat"):
        report.updated_from_checker_order += 1
    elif how in ("loose", "email_seat"):
        report.updated_from_checker_fuzzy += 1


def backfill_stock_barcodes(
    stock_path: Path,
    vercel_site: Path,
    *,
    confirm: bool = False,
    public_base: str = "https://tixx.cc",
    verify_seats: bool = True,
    no_backup: bool = False,
    tickets_path: Path | None = None,
    checker_idx: CheckerBarcodeStore | dict[tuple[str, str, str, str], str] | None = None,
    pass_index: PassBarcodeIndex | None = None,
) -> BackfillReport:
    report = BackfillReport()
    if not stock_path.is_file():
        report.errors.append(f"stock missing: {stock_path}")
        return report

    tickets_root = vercel_site / "tickets"
    alias_map = load_slug_alias_map(vercel_site)
    registry_by_slug = load_registry_slug_paths(vercel_site)
    site_dir = vercel_site.parent
    data_dir = site_dir.parent if site_dir.parent != site_dir else site_dir
    if checker_idx is None:
        if tickets_path and tickets_path.is_file():
            checker_idx = load_checker_barcode_index(tickets_path)
        else:
            checker_idx, _src = build_checker_barcode_index_for_layout(site_dir, data_dir)
    elif isinstance(checker_idx, CheckerBarcodeStore) and not len(checker_idx):
        auto_idx, _src = build_checker_barcode_index_for_layout(site_dir, data_dir)
        if len(auto_idx):
            checker_idx = auto_idx
    if tickets_path and isinstance(checker_idx, CheckerBarcodeStore) and not len(checker_idx) and tickets_path.is_file():
        report.errors.append(f"checker tickets empty or unparseable: {tickets_path}")

    def _checker_lookup(nl: str, seats: dict[str, str]) -> tuple[str, str]:
        return lookup_checker_barcode_detailed(checker_idx, nl, seats) if checker_idx else ("", "")
    if pass_index is None:
        pass_index = PassBarcodeIndex.build(tickets_root)
    lines = stock_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    out: list[str] = []
    changed: list[str] = []

    for line in lines:
        report.total += 1
        if report.total == 1 or report.total % 1000 == 0:
            print(f"    stock lines: {report.total}/{len(lines)}", flush=True)
        raw = line.rstrip("\r\n")
        if not raw.strip() or raw.lstrip().startswith("#"):
            out.append(line)
            continue

        nl = normalize_stock_line_viewer_url(raw, public_base)
        url_changed = nl != raw

        ref = stock_line_ticket_ref(nl)
        if not ref:
            if url_changed:
                report.updated_url += 1
                changed.append(nl)
            out.append(nl + ("\n" if line.endswith("\n") else ""))
            continue

        gid, slug, _url = ref
        stock_seats = parse_stock_seat_fields(nl)
        inline_bc = parse_barcode_from_stock_line(raw, stock_seats)
        pass_rec, new_slug, resolve_how = pass_index.lookup(
            gid, slug, stock_seats, alias_map, registry_by_slug, tickets_root
        )
        html_path = pass_rec["path"] if pass_rec else None

        if new_slug and new_slug != slug:
            nl2 = replace_stock_line_slug(nl, gid, slug, new_slug, public_base)
            if nl2 != nl:
                nl = nl2
                report.updated_slug += 1
                url_changed = True
            if resolve_how == "alias":
                report.resolved_via_alias += 1
            elif resolve_how == "seat_scan":
                report.resolved_via_seat_scan += 1
            elif resolve_how == "gid0":
                report.resolved_via_gid0 += 1
            elif resolve_how == "registry":
                report.resolved_via_registry += 1
        elif resolve_how == "gid0":
            report.resolved_via_gid0 += 1
        elif resolve_how == "registry":
            report.resolved_via_registry += 1

        if not html_path and not inline_bc:
            checker_bc, checker_how = _checker_lookup(nl, stock_seats)
            if checker_bc:
                cur_bc = stock_line_barcode_field(nl)
                if cur_bc != checker_bc:
                    nl = set_stock_line_barcode_field(nl, checker_bc)
                    report.updated_barcode += 1
                    report.updated_from_checker += 1
                    _tally_checker_match(report, checker_how)
                    changed.append(nl)
                if url_changed:
                    report.updated_url += 1
                out.append(nl + ("\n" if line.endswith("\n") else ""))
                continue
            if resolve_how == "invalidated_stub":
                report.skipped_invalidated_stub += 1
            elif resolve_how == "transferred_stub":
                report.skipped_transferred_stub += 1
            elif resolve_how == "no_safetix":
                report.skipped_no_safetix += 1
            elif resolve_how == "rotating_only":
                report.skipped_rotating_only += 1
            elif resolve_how == "no_html":
                report.skipped_no_html += 1
            else:
                report.skipped_no_safetix += 1
            if url_changed:
                report.updated_url += 1
                changed.append(nl)
            out.append(nl + ("\n" if line.endswith("\n") else ""))
            continue

        extracted = None
        if pass_rec:
            extracted = {
                "barcode": pass_rec["barcode"],
                "section": pass_rec.get("section", ""),
                "row": pass_rec.get("row", ""),
                "seat": pass_rec.get("seat", ""),
            }
        bc = (extracted or {}).get("barcode") or ""
        bc_src = "html" if bc else ""
        if not bc and inline_bc:
            bc = inline_bc
            bc_src = "stock_inline"
        if not bc:
            checker_bc, checker_how = _checker_lookup(nl, stock_seats)
            if checker_bc:
                bc = checker_bc
                bc_src = "checker"
                checker_match_how = checker_how
            else:
                checker_match_how = ""
        else:
            checker_match_how = ""
        if not bc:
            if resolve_how == "rotating_only":
                report.skipped_rotating_only += 1
            else:
                report.skipped_no_safetix += 1
            if url_changed:
                report.updated_url += 1
                changed.append(nl)
            out.append(nl + ("\n" if line.endswith("\n") else ""))
            continue

        if (
            verify_seats
            and stock_seats
            and extracted
            and bc_src == "html"
            and not (
                _seat_field_match(stock_seats.get("section", ""), extracted.get("section", ""))
                and _seat_field_match(stock_seats.get("row", ""), extracted.get("row", ""))
                and _seat_field_match(stock_seats.get("seat", ""), extracted.get("seat", ""))
            )
        ):
            report.skipped_seat_mismatch += 1
            report.errors.append(
                f"seat mismatch {gid}/{slug}: stock {stock_seats} vs html "
                f"sec={extracted.get('section')} row={extracted.get('row')} seat={extracted.get('seat')}"
            )
            if url_changed:
                report.updated_url += 1
            out.append(nl + ("\n" if line.endswith("\n") else ""))
            continue

        cur_bc = stock_line_barcode_field(nl)
        if cur_bc == bc:
            report.skipped_already += 1
        else:
            nl = set_stock_line_barcode_field(nl, bc)
            report.updated_barcode += 1
            if bc_src == "stock_inline":
                report.updated_from_stock_inline += 1
            elif bc_src == "checker":
                report.updated_from_checker += 1
                _tally_checker_match(report, checker_match_how)
            changed.append(nl)

        if url_changed:
            report.updated_url += 1

        out.append(nl + ("\n" if line.endswith("\n") else ""))

    if not confirm:
        return report

    if changed and not no_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(stock_path, stock_path.with_suffix(f".csv.bak_barcode_{ts}"))

    stock_path.write_text("".join(out), encoding="utf-8")
    return report


def print_backfill_report(report: BackfillReport, stock_path: Path, *, dry_run: bool) -> None:
    mode = "DRY RUN (add --confirm to write + rotate slugs)" if dry_run else "APPLIED"
    print(f"\n[*] Barcode backfill ({mode}) -> {stock_path}")
    print(f"    lines scanned              : {report.total}")
    print(f"    barcodes injected          : {report.updated_barcode}")
    print(f"    slugs fixed (alias/scan)   : {report.updated_slug}")
    print(f"    URLs -> tixx.cc            : {report.updated_url}")
    print(f"    already had barcode        : {report.skipped_already}")
    print(f"    no pass HTML               : {report.skipped_no_html}")
    print(f"    invalidated old slug stub  : {report.skipped_invalidated_stub}")
    print(f"    transferred stub           : {report.skipped_transferred_stub}")
    print(f"    live pass, no safetix      : {report.skipped_no_safetix}")
    print(f"    rotating-only (need txt)   : {report.skipped_rotating_only}")
    print(f"    resolved via slug alias    : {report.resolved_via_alias}")
    print(f"    resolved via seat scan     : {report.resolved_via_seat_scan}")
    print(f"    resolved via gid/0 fallback: {report.resolved_via_gid0}")
    print(f"    resolved via registry path : {report.resolved_via_registry}")
    print(f"    barcodes from recovery index: {report.updated_from_checker}")
    print(f"      (fuzzy seat match)         : {report.updated_from_checker_fuzzy}")
    print(f"      (order / order+seat match) : {report.updated_from_checker_order}")
    print(f"    barcodes from stock inline : {report.updated_from_stock_inline}")
    print(f"    seat mismatch (skip)       : {report.skipped_seat_mismatch}")
    if report.skipped_rotating_only > 100 and report.updated_from_checker == 0:
        print(
            "\n    [!] Most passes are rotating SafeTix (regen) - static barcode is NOT stored in HTML.\n"
            "        Put checker dumps in tm.bz/Data_for_recovery (upcoming, pm, hits, found_hits, …)\n"
            "        and re-run, or barcodes stay empty."
        )
    if report.skipped_invalidated_stub > 100 and report.updated_barcode == 0:
        print(
            "\n    [!] Most lines hit INVALIDATED old-slug pages - stock URLs are stale.\n"
            "        Run: python tm_hit_viewer.py --reslug-secure-pass-stock --confirm\n"
            "        That rotates slugs + syncs CSV to new tixx.cc links + backfills barcodes."
        )
    if dry_run and (report.updated_barcode or report.updated_url or report.updated_slug):
        print("\n    [!] Dry run - nothing saved. Re-run with --confirm to apply.")
    if report.errors:
        show = report.errors[:10]
        print(f"    warnings ({len(report.errors)}):")
        for e in show:
            print(f"      - {e}")
        if len(report.errors) > 10:
            print(f"      ... and {len(report.errors) - 10} more")
