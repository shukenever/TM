"""
reslug_tickets.py — Replace viewer pass slugs with fresh random ones and
                    regenerate delivery PDFs.

Scans a folder of delivery PDFs, extracts the viewer URL from each, then:
  1. Renames the HTML pass file in tm-vercel-site/tickets/GID/
  2. Patches slug references inside the HTML
  3. Updates tm_viewer_link_registry.json (inside vercel site)
  4. Updates tm_viewer_deliveries.jsonl (in tm.bz root, if present)
  5. Replaces the old URL in links.txt with the new URL
  6. Regenerates the delivery PDF with a fresh QR code + new URL

Bundled viewer builds can show “N tickets · X of Y” in the header — that is normal for
multi-seat HTML. If a QR opens the wrong *event* (slug/gid points at another show’s HTML),
this script cross-checks ``<title>`` vs ``links.txt`` / the PDF filename and skips instead
of stamping a bad URL.

Usage (run from deleter/ or any PDF folder):
    python reslug_tickets.py
    python reslug_tickets.py <pdf_folder>
    python reslug_tickets.py <pdf_folder> <vercel_site_dir> <links_file>
    python reslug_tickets.py --dry-run

Requirements:
    pip install pdfplumber reportlab qrcode[pil]
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import secrets
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# ── optional deps ──────────────────────────────────────────────────────────────

try:
    import pdfplumber  # type: ignore
    _HAS_PDFPLUMBER = True
except ImportError:
    _HAS_PDFPLUMBER = False
    print("[!] pdfplumber not found — install with: pip install pdfplumber", file=sys.stderr)

try:
    from reportlab.lib import colors  # type: ignore
    from reportlab.lib.enums import TA_CENTER  # type: ignore
    from reportlab.lib.pagesizes import letter  # type: ignore
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore
    from reportlab.lib.units import inch  # type: ignore
    from reportlab.platypus import Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # type: ignore
    import qrcode          # type: ignore
    _HAS_GEN = True
except ImportError:
    _HAS_GEN = False
    print("[!] PDF generation deps missing — install with: pip install reportlab qrcode[pil]",
          file=sys.stderr)


# ── slug helpers ───────────────────────────────────────────────────────────────

def new_slug(length_bytes: int = 14) -> str:
    """Generate a URL-safe base64 slug (no padding), same format as tm_hit_viewer."""
    return base64.urlsafe_b64encode(secrets.token_bytes(length_bytes)).decode().rstrip("=")


_RE_VIEWER_URL = re.compile(
    r"https?://[^\s\"'<>\[\]]+/tickets/(\d+)/([^\s\"'<>\[\]/\.]+)(?:\.html)?",
    re.IGNORECASE,
)


def extract_url_from_pdf(pdf_path: Path) -> tuple[str, str, str] | None:
    """
    Return (full_url_no_html, gid, slug) from the PDF text, or None.
    Strips .html suffix for consistency.
    """
    if not _HAS_PDFPLUMBER:
        return None
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as e:
        print(f"    [!] PDF read error {pdf_path.name}: {e}", file=sys.stderr)
        return None

    for m in _RE_VIEWER_URL.finditer(text):
        full = m.group(0).rstrip(".,)")
        # Normalise: strip .html suffix
        full_clean = re.sub(r"\.html$", "", full, flags=re.IGNORECASE)
        gid  = m.group(1)
        slug = m.group(2).rstrip(".,)")
        return full_clean, gid, slug
    return None


_BOILERPLATE_LINE = re.compile(
    r"^(ticket)\s*$|"
    r"^(reference sheet)\b|"
    r"^(please read)\b|"
    r"^(event details)\b|"
    r"^(open your live ticket)\b|"
    r"^(scan with your phone)\b|"
    r"^(if you cannot scan)\b|"
    r"^(if you have any issues)\b",
    re.I,
)


def extract_text_fields_from_pdf(pdf_path: Path) -> dict:
    """Extract event name, date, venue, seats, event_id, contact from PDF text."""
    out: dict = {}
    if not _HAS_PDFPLUMBER:
        return out
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception:
        return out

    def find(pattern: str) -> str:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else ""

    # Event title sits directly under the blue banner, *before* the long yellow disclaimer.
    event_name = ""
    wm = re.search(r"(?im)^When:\s*", text)
    if wm:
        before = text[: wm.start()]
        candidates = [ln.strip() for ln in before.splitlines() if ln.strip()]
        for ln in candidates:
            if _BOILERPLATE_LINE.match(ln):
                continue
            if len(ln) < 8:
                continue
            ll = ln.lower()
            if "please read" in ll:
                continue
            if "qr code" in ll and "staff" in ll:
                continue
            if "opens your real ticket" in ll:
                continue
            event_name = ln
            break
    if not event_name:
        for ln in text.splitlines():
            ln = ln.strip()
            if len(ln) >= 8 and not _BOILERPLATE_LINE.match(ln):
                event_name = ln
                break

    out["event_name"] = event_name
    out["when"]       = find(r"(?m)^When:\s*(.+)$")
    out["where"]      = find(r"(?m)^Where:\s*(.+)$")
    out["seats"]      = find(r"(?m)^Seats:\s*(.+)$")
    out["event_id"]   = find(r"(?m)^Event ID:\s*(.+)$")
    out["contact"]    = find(r"(?i)contact\s+([^\s]+@[^\s]+)")
    return out


def enrich_fields_from_parsed_links_row(parsed: dict | None, fields: dict) -> None:
    """Prefer authoritative stock row metadata over scraped PDF text."""
    if not parsed:
        return
    ev = (parsed.get("event_name") or "").strip()
    if ev:
        fields["event_name"] = ev
    dt = (parsed.get("event_date") or "").strip()
    if dt:
        fields["when"] = dt
    vn = (parsed.get("venue") or "").strip()
    if vn:
        fields["where"] = vn
    sec = (parsed.get("section") or "").strip()
    rw = (parsed.get("row") or "").strip()
    sts = (parsed.get("seats") or "").strip()
    if sec or rw or sts:
        fields["seats"] = " / ".join(x for x in (sec, rw, sts) if x)
    eid = (parsed.get("event_id") or "").strip()
    if eid:
        fields["event_id"] = eid


def load_slug_redirect_map(site_root: Path) -> dict[str, str]:
    """Old opaque slug -> ``tickets/<gid>/<new>.html`` (same shape as tm_viewer_pass_slug_aliases.json)."""
    p = site_root / "tm_viewer_pass_slug_aliases.json"
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError, TypeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    red = raw.get("redirects")
    if not isinstance(red, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in red.items():
        ks = str(k).strip()
        vs = str(v).strip().replace("\\", "/")
        if ks and vs:
            out[ks] = vs
    return out


def parse_filename_srs(stem: str) -> dict[str, str]:
    """
    Split PDF filename stem into section/row/seat.
    Expected tail: "…EventName SECTION ROW SEAT"
    e.g. "WWE Monday Night RAW 105 12 3"  →  sec=105, row=12, seat=3
         "Whose Live Anyway ORCHC M 214"  →  sec=ORCHC, row=M, seat=214
    """
    tokens = stem.split()
    if len(tokens) >= 3:
        return {
            "section": tokens[-3].upper(),
            "row":     tokens[-2].upper(),
            "seat":    tokens[-1].upper(),
        }
    if len(tokens) == 2:
        return {"section": tokens[-2].upper(), "row": "", "seat": tokens[-1].upper()}
    return {"section": "", "row": "", "seat": ""}


def event_hint_from_pdf_stem(stem: str) -> str:
    """Event name portion of PDF filename — all but the last section/row/seat tokens."""
    parts = stem.split()
    if len(parts) >= 4:
        return " ".join(parts[:-3]).strip()
    return (stem or "").strip()


def _normalize_ev_tokens(s: str) -> list[str]:
    raw = re.sub(r"[^a-zA-Z0-9]+", " ", (s or "").lower())
    return [t for t in raw.split() if len(t) >= 4]


def html_chunk_matches_event_hint(hint: str, html_chunk: str) -> bool:
    """
    If hint is strong (e.g. from links ``event_name``), require TM viewer HTML ``<title>`` to agree.
    Stops regenerate/reslug flows from stamping a QR that opens another show (wrong gid/slug reused).
    Bundled passes still match because the real event name is in ``<title>``.
    """
    hint_toks = _normalize_ev_tokens(hint)
    if len(hint.strip()) < 10 or len(hint_toks) < 2:
        return True
    tm = re.search(r"<title[^>]*>([^<]{1,900})</title>", html_chunk, re.I | re.DOTALL)
    title = ((tm.group(1) if tm else "") or "").replace("\xa0", " ").strip().lower()
    if not title:
        return False
    hint_toks.sort(key=len, reverse=True)
    need = max(2, min(4, len(hint_toks)))
    matched = sum(1 for t in hint_toks if t in title)
    return matched >= need


def _html_title_matches_srs(html_chunk: str, section: str, row: str, seat: str) -> bool:
    """Match TM viewer ``<title>`` ... Sec … Row … seat hints to filename S/R/seat."""
    if not seat:
        return False
    tm = re.search(r"<title[^>]*>([^<]{1,900})</title>", html_chunk, re.I | re.DOTALL)
    title = ((tm.group(1) if tm else "") or "").replace("\xa0", " ").strip().lower()
    if not title:
        return False

    def _has_seat(t: str, st: str) -> bool:
        st = st.strip().lower()
        if not st:
            return False
        if st in t:
            return True
        return bool(re.search(rf"(?:^|[^\d]){re.escape(st)}(?:[^\d]|$)", t))

    if not _has_seat(title, seat):
        return False

    su = section.strip().upper()
    if su:
        if su.lower() not in title and not re.search(rf"sec\.?\s*{re.escape(su)}\b", title, re.I):
            return False
    ru = row.strip().upper()
    if ru:
        if ru.lower() not in title and not re.search(rf"row\s*{re.escape(ru)}\b", title, re.I):
            return False
    return True


def resolve_current_slug_for_regen(
    vercel_site: Path,
    gid: str,
    slug_from_pdf: str,
    pdf_stem: str,
    event_hint: str = "",
) -> tuple[str | None, str]:
    """
    Map the slug embedded in a PDF to the HTML filename stem that exists on disk.
    When ``event_hint`` is set (stock ``event_name`` or parsed filename), refuses HTML whose ``<title>``
    is for a different show — avoids QR/PDF that open Chicago while the sheet says Kid Laroi.
    """
    gid_dir = vercel_site / "tickets" / gid
    if not gid_dir.is_dir():
        return None, "no_gid_dir"

    hint = (event_hint or "").strip()

    def _html_verified(path: Path, chunk: str | None = None) -> bool:
        if not hint:
            return True
        try:
            ch = (
                chunk
                if chunk is not None
                else path.read_text(encoding="utf-8", errors="replace")[:400_000]
            )
        except OSError:
            return False
        return html_chunk_matches_event_hint(hint, ch)

    html_pages = sorted(
        f for f in gid_dir.glob("*.html")
        if not f.name.startswith(".")
    )

    direct = gid_dir / f"{slug_from_pdf}.html"
    if direct.is_file():
        if _html_verified(direct):
            return slug_from_pdf, "slug_matches_pdf_url"
        # Embedded viewer URL points at another event's HTML — ignore and try recovery paths.

    redirs = load_slug_redirect_map(vercel_site)
    tgt = redirs.get(slug_from_pdf)
    if tgt:
        m = re.search(r"(?:^|/)tickets/(\d+)/([^/]+?)\.html", tgt.replace("\\", "/"), re.I)
        if m and m.group(1) == gid:
            stem = m.group(2)
            cand = gid_dir / f"{stem}.html"
            if cand.is_file() and _html_verified(cand):
                return stem, "tm_viewer_pass_slug_aliases.json"

    if len(html_pages) == 1:
        sole = html_pages[0]
        if _html_verified(sole):
            return sole.stem, "single_pass_in_gid_folder"

    fn_srs = parse_filename_srs(pdf_stem)
    sec, row, seat = fn_srs["section"], fn_srs["row"], fn_srs["seat"]
    hits: list[str] = []
    for hp in html_pages:
        try:
            chunk = hp.read_text(encoding="utf-8", errors="replace")[:240_000]
        except OSError:
            continue
        if _html_title_matches_srs(chunk, sec, row, seat) and html_chunk_matches_event_hint(hint, chunk):
            hits.append(hp.stem)

    if len(hits) == 1:
        return hits[0], "matched_html_title_to_filename_seat"
    if len(hits) > 1:
        return None, f"ambiguous:{hits}"

    if direct.is_file() and hint:
        return None, "event_mismatch_pdf_url_wrong_show_regenerate_viewer_pass"
    return None, "no_matching_html"


# ── links.txt parsing & update ─────────────────────────────────────────────────

def _csv_split(s: str) -> list[str]:
    cells: list[str] = []
    cur = ""
    in_q = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == '"':
            if in_q and i + 1 < len(s) and s[i + 1] == '"':
                cur += '"'; i += 2; continue
            in_q = not in_q
        elif c == ',' and not in_q:
            cells.append(cur); cur = ""; i += 1; continue
        else:
            cur += c
        i += 1
    cells.append(cur)
    return cells


def parse_links_line(line: str) -> dict | None:
    line = line.strip()
    if not line or " | " not in line:
        return None
    combo, payload = line.split(" | ", 1)
    cells = _csv_split(payload)
    if len(cells) < 12:
        return None
    return {
        "combo":        combo.strip(),
        "event_id":     cells[0].strip(),
        "event_name":   cells[1].strip(),
        "event_date":   cells[2].strip(),
        "venue":        cells[3].strip(),
        "order_no":     cells[4].strip(),
        "account_email":cells[5].strip().lower(),
        "section":      cells[6].strip().upper(),
        "row":          cells[7].strip().upper(),
        "seats":        cells[8].strip().upper(),
        "cost":         cells[9].strip(),
        "link":         cells[11].strip() if len(cells) > 11 else "",
        "cells":        cells,
    }


def rebuild_links_line(parsed: dict, new_link: str) -> str:
    """Rebuild the links.txt line with the link field replaced."""
    cells = list(parsed["cells"])
    if len(cells) > 11:
        cells[11] = new_link
    return parsed["combo"] + " | " + ",".join(cells) + "\n"


def srs_match_idxs(
    parsed_rows: dict[int, dict],
    section: str, row: str, seat: str,
) -> list[int]:
    """Return links.txt line indices whose section/row/seats match the filename S/R/Seat."""
    if not (section and seat):
        return []
    out: list[int] = []
    for idx, p in parsed_rows.items():
        if p["section"] != section:
            continue
        if row and p["row"] != row:
            continue
        # seats field may be "5+6" (multi-seat) or just "3"
        seat_set = {s.strip().upper() for s in re.split(r"[+,]", p["seats"]) if s.strip()}
        if seat in seat_set or p["seats"].upper() == seat:
            out.append(idx)
    return out


def find_links_file(start: Path) -> Path | None:
    candidates: list[Path] = []
    for anc in [start] + list(start.parents)[:4]:
        candidates += [anc / "links.txt", anc / "links"]
    candidates += [
        Path(__file__).parent / "links.txt",
        Path(__file__).parent / "links",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def find_vercel_site(start: Path) -> Path | None:
    for anc in [start] + list(start.parents)[:4]:
        cand = anc / "tm-vercel-site"
        if cand.is_dir() and (cand / "tickets").is_dir():
            return cand
    return None


# ── registry & deliveries update ───────────────────────────────────────────────

def update_registry(reg_path: Path, old_slug: str, new_slug_val: str, gid: str) -> bool:
    """Replace old slug in tm_viewer_link_registry.json. Returns True if changed."""
    if not reg_path.is_file():
        return False
    try:
        data = json.loads(reg_path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return False

    old_path = f"tickets/{gid}/{old_slug}.html"
    new_path = f"tickets/{gid}/{new_slug_val}.html"
    changed  = False
    text     = reg_path.read_text(encoding="utf-8", errors="replace")

    if old_path in text:
        new_text = text.replace(old_path, new_path)
        reg_path.write_text(new_text, encoding="utf-8")
        changed = True

    return changed


def update_deliveries_jsonl(jsonl_path: Path, old_slug: str, new_slug_val: str,
                            old_url_base: str, new_url_base: str) -> int:
    """Replace old slug/URL in tm_viewer_deliveries.jsonl. Returns count of changed lines."""
    if not jsonl_path.is_file():
        return 0
    lines = jsonl_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    changed = 0
    out_lines: list[str] = []
    for line in lines:
        if old_slug in line:
            new_line = line.replace(old_slug, new_slug_val)
            # Also replace full URL if present (handles both .html and bare slug variants)
            if old_url_base in new_line:
                new_line = new_line.replace(old_url_base, new_url_base)
            out_lines.append(new_line)
            changed += 1
        else:
            out_lines.append(line)
    if changed:
        jsonl_path.write_text("".join(out_lines), encoding="utf-8")
    return changed


def patch_html_file(html_path: Path, old_slug: str, new_slug_val: str) -> bool:
    """Replace all references to old_slug with new_slug_val inside the HTML file."""
    try:
        content = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if old_slug not in content:
        return False
    html_path.write_text(content.replace(old_slug, new_slug_val), encoding="utf-8")
    return True


INVALIDATED_LINK_MESSAGE = (
    "Your barcode has been killed because of StubHub, unfortunately. "
    "You can get free tickets if you file a lawsuit against them immediately."
)


def write_invalidated_slug_html(html_path: Path) -> None:
    """Overwrite a pass HTML file so old buyer links show the invalidation notice."""
    from html import escape

    msg = escape(INVALIDATED_LINK_MESSAGE)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="robots" content="noindex,nofollow"/>
  <meta name="theme-color" content="#991b1b"/>
  <title>Link invalidated</title>
  <style>
    body {{ margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      background: linear-gradient(180deg, #fef2f2 0%, #f4f6f8 100%); color:#121212;
      min-height:100vh; display:flex; align-items:center; justify-content:center;
      padding:24px; box-sizing:border-box; }}
    .card {{ max-width:480px; width:100%; background:#fff; border-radius:14px;
      padding:28px 24px; box-shadow:0 10px 40px rgba(153,27,27,.14);
      border:1px solid #fecaca; text-align:center; }}
    .badge {{ display:inline-flex; align-items:center; gap:8px; padding:6px 12px;
      border-radius:999px; background:#fef2f2; color:#991b1b; font-size:0.78rem;
      font-weight:800; letter-spacing:.06em; text-transform:uppercase; margin-bottom:14px; }}
    .badge svg {{ width:16px; height:16px; flex-shrink:0; }}
    h1 {{ font-size:1.35rem; margin:0 0 14px; font-weight:800; color:#991b1b; line-height:1.25; }}
    p {{ margin:0; font-size:1rem; line-height:1.65; color:#334155; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="badge" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M12 9v4m0 4h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"/>
      </svg>
      Warning
    </div>
    <h1>Your barcode has been killed</h1>
    <p>{msg}</p>
  </div>
</body>
</html>"""
    html_path.write_text(html, encoding="utf-8")


def rotate_slug_html_files(old_html_path: Path, old_slug: str, new_slug_val: str) -> Path:
    """
    Copy pass to new slug; leave old slug URL showing invalidation message (not a live ticket).
    """
    new_html_path = old_html_path.with_name(f"{new_slug_val}.html")
    content = old_html_path.read_text(encoding="utf-8", errors="replace")
    new_html_path.write_text(content.replace(old_slug, new_slug_val), encoding="utf-8")
    write_invalidated_slug_html(old_html_path)
    return new_html_path


# ── PDF generation ─────────────────────────────────────────────────────────────

# ── pdf generation (reportlab-based, StubHub style) ──────────────────────────

def _make_qr_png_bytes(url: str, box_size: int = 6, border: int = 2) -> bytes:
    """Generate QR code PNG bytes using qrcode library."""
    import qrcode
    
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_pdf(
    *,
    event_name: str,
    when: str,
    where: str,
    seats: str,
    event_id: str,
    url: str,
    contact: str = "support@tixx.pw",
    out_path: Path,
) -> None:
    """Generate a delivery reference PDF using reportlab (matches secure_pass_input_to_stubhub_pdf.py style)."""
    buf = io.BytesIO()
    full_w = letter[0] - 108
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=48,
        bottomMargin=54,
    )
    styles = getSampleStyleSheet()
    accent = colors.HexColor("#1e40af")
    accent_dark = colors.HexColor("#1e3a8a")
    
    body = ParagraphStyle(
        name="Body",
        parent=styles["Normal"],
        fontSize=11,
        leading=15,
        spaceAfter=5,
        textColor=colors.HexColor("#1f2937"),
    )
    
    story = []
    esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # Blue header banner
    banner_title = '<b><font size=13>Ticket</font></b>'
    banner_sub = '<font size=9 color="#bfdbfe">Reference sheet — not your venue scan ticket</font>'
    banner_para = Paragraph(
        f"{banner_title}<br/>{banner_sub}",
        ParagraphStyle(
            name="BannerInner",
            parent=styles["Normal"],
            alignment=TA_CENTER,
            textColor=colors.white,
            leading=14,
        ),
    )
    banner_tbl = Table([[banner_para]], colWidths=[full_w])
    banner_tbl.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), accent_dark),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])
    )
    story.append(banner_tbl)
    story.append(Spacer(1, 0.14 * inch))
    
    # Event name
    event_head = Paragraph(
        f'<b><font size=15 color="#111827">{esc(event_name)}</font></b>',
        ParagraphStyle(name="EventTitle", parent=styles["Normal"], spaceAfter=10, leading=18),
    )
    story.append(event_head)
    
    # Yellow warning box
    disclaimer_html = (
        "<b>Please read:</b> The QR code on this page is <i>not</i> what staff scan at the door. "
        "It only <b>opens your real ticket in the browser</b> on your phone. "
        "After you scan it, use the live ticket or barcode shown on that page for entry. "
        "Keep this PDF as a backup reminder of your seats and link."
    )
    disclaimer_para = Paragraph(
        disclaimer_html,
        ParagraphStyle(
            name="Disclaimer",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#78350f"),
        ),
    )
    disc_tbl = Table([[disclaimer_para]], colWidths=[full_w])
    disc_tbl.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef9c3")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#facc15")),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ])
    )
    story.append(disc_tbl)
    story.append(Spacer(1, 0.16 * inch))
    
    # Event details
    detail_label = ParagraphStyle(
        name="DetailLab", parent=styles["Normal"], fontSize=11, leading=15,
        textColor=accent, spaceAfter=2,
    )
    story.append(Paragraph("<b>Event details</b>", detail_label))
    
    lines = []
    if when: lines.append(f'<b><font color="#374151">When:</font></b> {esc(when)}')
    if where: lines.append(f'<b><font color="#374151">Where:</font></b> {esc(where)}')
    if seats: lines.append(f'<b><font color="#374151">Seats:</font></b> {esc(seats)}')
    if event_id: lines.append(f'<b><font color="#374151">Event ID:</font></b> {esc(event_id)}')
    
    detail_block = Paragraph("<br/>".join(lines), body)
    detail_wrap = Table([[detail_block]], colWidths=[full_w])
    detail_wrap.setStyle(
        TableStyle([
            ("LINELEFT", (0, 0), (0, -1), 3, accent),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ])
    )
    story.append(detail_wrap)
    story.append(Spacer(1, 0.22 * inch))
    
    # QR code section
    qr_url = url if url.startswith("http") else f"https://{url}"
    
    story.append(
        Paragraph(
            '<b><font size=12 color="#1e40af">Open your live ticket</font></b>',
            ParagraphStyle(name="QRHead", parent=styles["Normal"], alignment=TA_CENTER, spaceAfter=4),
        )
    )
    story.append(
        Paragraph(
            '<font size=10 color="#4b5563">Scan with your phone camera — you will be taken to your official ticket page.</font>',
            ParagraphStyle(name="QRSub", parent=styles["Normal"], alignment=TA_CENTER, spaceAfter=10),
        )
    )
    
    try:
        png = _make_qr_png_bytes(qr_url)
        qr_img = RLImage(io.BytesIO(png), width=2.5 * inch, height=2.5 * inch)
        qr_tbl = Table([[qr_img]], colWidths=[full_w])
        qr_tbl.setStyle(
            TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#e5e7eb")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ffffff")),
            ])
        )
        story.append(qr_tbl)
    except Exception as e:
        story.append(
            Paragraph(
                f'<font color="red">[QR generation failed: {e}]</font>',
                ParagraphStyle(name="QRError", parent=styles["Normal"], alignment=TA_CENTER),
            )
        )
    
    story.append(Spacer(1, 0.1 * inch))
    story.append(
        Paragraph(
            '<b><font size=9 color="#374151">If you cannot scan the QR code, copy this link into your browser:</font></b>',
            ParagraphStyle(name="UrlHint", parent=styles["Normal"], alignment=TA_CENTER, spaceAfter=3),
        )
    )
    
    safe_url = qr_url.replace("&", "&amp;")
    story.append(
        Paragraph(
            f'<font name="Helvetica" size=7 color="#9ca3af">{safe_url}</font>',
            ParagraphStyle(name="UrlMono", parent=styles["Normal"], alignment=TA_CENTER, fontName="Helvetica"),
        )
    )
    
    story.append(Spacer(1, 0.14 * inch))
    
    # Contact footer
    em = contact.replace("&", "&amp;")
    story.append(
        Paragraph(
            f'<font size=9 color="#4b5563">If you have any issues, contact '
            f'<font color="#1e40af"><b>{em}</b></font> directly.</font>',
            ParagraphStyle(name="SupportFooter", parent=styles["Normal"], alignment=TA_CENTER, spaceAfter=2),
        )
    )
    
    doc.build(story)
    out_path.write_bytes(buf.getvalue())


# ── discovery helpers ──────────────────────────────────────────────────────────

def _slug_from_url_str(url_str: str) -> tuple[str, str] | None:
    """Return (gid, slug) from a full URL string, or None."""
    m = _RE_VIEWER_URL.search(url_str)
    if m:
        return m.group(1), m.group(2).rstrip(".,)")
    return None


def _base_url(full_url: str) -> str:
    """Return URL without slug/filename: https://domain/tickets/<gid>/"""
    return re.sub(r"/[^/]+$", "/", full_url.rstrip("/"))


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Replace viewer pass slugs and regenerate delivery PDFs."
    )
    ap.add_argument("pdf_folder",    nargs="?", default=".",
                    help="Folder of .pdf files (default: current dir)")
    ap.add_argument("vercel_site",   nargs="?", default=None,
                    help="tm-vercel-site folder (auto-detected if omitted)")
    ap.add_argument("links_file",    nargs="?", default=None,
                    help="links / links.txt path (auto-detected if omitted)")
    ap.add_argument("--dry-run",     action="store_true",
                    help="Show plan without writing anything (DEFAULT unless --confirm given)")
    ap.add_argument("--confirm",     action="store_true",
                    help="REQUIRED to actually write changes — without this, always dry-run")
    ap.add_argument("--no-backup",   action="store_true",
                    help="Skip .bak backup of links file")
    ap.add_argument("--contact",     default="",
                    help="Contact email printed in regenerated PDFs")
    ap.add_argument("--regen-only",  action="store_true",
                    help="Only regenerate PDFs using new slugs already in vercel site (skip all reslug logic)")
    ap.add_argument("--recursive",   action="store_true",
                    help="Search for PDFs in subfolders too (not just the top level)")
    args = ap.parse_args()

    # ── regen-only mode: re-make PDFs using current slug in tickets/GID/ ──────
    if args.regen_only:
        if not _HAS_GEN:
            sys.exit("[!] reportlab/qrcode required:  pip install reportlab \"qrcode[pil]\"")
        if not _HAS_PDFPLUMBER:
            sys.exit("[!] pdfplumber required:  pip install pdfplumber")
        pdf_dir = Path(args.pdf_folder).expanduser().resolve()
        vercel = (Path(args.vercel_site).expanduser().resolve()
                  if args.vercel_site else find_vercel_site(pdf_dir))
        if not vercel:
            sys.exit("[!] Could not find tm-vercel-site.")
        _seen: set[str] = set()
        if args.recursive:
            _pdf_iter = sorted(pdf_dir.rglob("*.pdf")) + sorted(pdf_dir.rglob("*.PDF"))
        else:
            _pdf_iter = sorted(pdf_dir.glob("*.pdf")) + sorted(pdf_dir.glob("*.PDF"))
        pdfs2 = [p for p in _pdf_iter
                 if p.is_file() and p.name.lower() not in _seen and not _seen.add(p.name.lower())]
        print(f"[*] Regen-only: {len(pdfs2)} PDF(s) in {pdf_dir}")
        links_opt = find_links_file(pdf_dir)
        slug_to_stock_row: dict[str, dict] = {}
        if links_opt and links_opt.is_file():
            for line in links_opt.read_text(encoding="utf-8", errors="replace").splitlines():
                pr = parse_links_line(line)
                if not pr:
                    continue
                mk = _slug_from_url_str(pr["link"].rstrip("/"))
                if mk:
                    slug_to_stock_row[mk[1]] = pr

        ok = skipped = 0
        for pdf_path in pdfs2:
            result = extract_url_from_pdf(pdf_path)
            if not result:
                print(f"  [!] No URL in {pdf_path.name} — skipped"); skipped += 1; continue
            old_url, gid, old_slug = result
            stock_row = slug_to_stock_row.get(old_slug)
            ev_hint = (
                ((stock_row.get("event_name") or "").strip() if stock_row else "")
                or event_hint_from_pdf_stem(pdf_path.stem)
            )
            new_slug_val, slug_how = resolve_current_slug_for_regen(
                vercel, gid, old_slug, pdf_path.stem, event_hint=ev_hint
            )
            if not new_slug_val:
                print(f"  [!] {pdf_path.name} — cannot resolve slug ({slug_how}), skipped")
                skipped += 1
                continue
            new_url = re.sub(r"/tickets/\d+/[^/\s]+", f"/tickets/{gid}/{new_slug_val}", old_url)
            fields  = extract_text_fields_from_pdf(pdf_path)
            enrich_fields_from_parsed_links_row(
                slug_to_stock_row.get(old_slug) or slug_to_stock_row.get(new_slug_val),
                fields,
            )
            ev      = fields.get("event_name") or pdf_path.stem
            bak_pdf = pdf_path.with_suffix(".pdf.orig")
            import shutil as _sh
            _sh.copy2(pdf_path, bak_pdf)
            try:
                generate_pdf(
                    event_name=ev,
                    when=fields.get("when", ""),
                    where=fields.get("where", ""),
                    seats=fields.get("seats", ""),
                    event_id=fields.get("event_id", ""),
                    url=new_url,
                    contact=args.contact or fields.get("contact", "") or "support@tixx.pw",
                    out_path=pdf_path,
                )
                bak_pdf.unlink(missing_ok=True)
                print(f"  [+] {pdf_path.name}  →  {new_url}  ({slug_how})")
                ok += 1
            except Exception as e:
                _sh.copy2(bak_pdf, pdf_path); bak_pdf.unlink(missing_ok=True)
                print(f"  [!] {pdf_path.name} failed: {e}"); skipped += 1
        print(f"\n[+] Regen done: {ok} regenerated, {skipped} skipped.")
        return

    # Safety: default to dry-run unless --confirm explicitly given
    if not args.confirm:
        args.dry_run = True

    pdf_dir = Path(args.pdf_folder).expanduser().resolve()
    if not pdf_dir.is_dir():
        sys.exit(f"[!] PDF folder not found: {pdf_dir}")

    # Deduplicate: on Windows glob("*.pdf") and glob("*.PDF") both match the
    # same files (case-insensitive FS), which would process every PDF twice.
    _seen_pdf_names: set[str] = set()
    pdfs: list[Path] = []
    if args.recursive:
        _pdf_iter = sorted(pdf_dir.rglob("*.pdf")) + sorted(pdf_dir.rglob("*.PDF"))
    else:
        _pdf_iter = sorted(pdf_dir.glob("*.pdf")) + sorted(pdf_dir.glob("*.PDF"))
    for _p in _pdf_iter:
        if not _p.is_file():
            continue
        if _p.name.lower() not in _seen_pdf_names:
            _seen_pdf_names.add(_p.name.lower())
            pdfs.append(_p)
    if not pdfs:
        sys.exit(f"[!] No .pdf files found in {pdf_dir}")

    vercel_site = (
        Path(args.vercel_site).expanduser().resolve()
        if args.vercel_site
        else find_vercel_site(pdf_dir)
    )

    links_path = (
        Path(args.links_file).expanduser().resolve()
        if args.links_file
        else find_links_file(pdf_dir)
    )

    if not links_path or not links_path.is_file():
        sys.exit("[!] Could not find links/links.txt — pass it explicitly as 3rd argument.")

    if not vercel_site or not vercel_site.is_dir():
        print("[!] Could not find tm-vercel-site — HTML patching and registry update disabled.",
              file=sys.stderr)
        vercel_site = None

    print(f"[*] PDF folder  : {pdf_dir}  ({len(pdfs)} PDF(s))")
    print(f"[*] Links file  : {links_path}")
    print(f"[*] Vercel site : {vercel_site or '(not found)'}")

    # ── Step 1: extract old URLs from each PDF ─────────────────────────────────
    print(f"\n[*] Extracting URLs from {len(pdfs)} PDF(s)...")
    pdf_info: list[tuple[Path, str, str, str]] = []  # (path, full_url, gid, old_slug)

    for pdf_path in pdfs:
        result = extract_url_from_pdf(pdf_path)
        if result:
            full_url, gid, slug = result
            print(f"    {pdf_path.name}  →  gid={gid}  slug={slug}")
            pdf_info.append((pdf_path, full_url, gid, slug))
        else:
            print(f"    [!] No viewer URL found in {pdf_path.name} — skipped")

    if not pdf_info:
        sys.exit("[!] No viewer URLs extracted from any PDF.")

    # ── Step 2: read links.txt and build indexes ───────────────────────────────
    raw_lines = links_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    print(f"\n[*] Loaded {len(raw_lines)} line(s) from {links_path.name}")

    # Primary index: viewer URL slug → line indices
    slug_to_idx: dict[str, list[int]] = {}
    # Secondary index: (section, row, seat) → line indices  (fallback)
    srs_to_idx:  dict[tuple, list[int]] = {}
    # Parsed rows for fallback matching
    parsed_rows: dict[int, dict] = {}

    for idx, line in enumerate(raw_lines):
        p = parse_links_line(line)
        if not p:
            continue
        parsed_rows[idx] = p
        # Primary: slug from link URL
        lk = p["link"].rstrip("/")
        m = _slug_from_url_str(lk)
        if m:
            slug_to_idx.setdefault(m[1], []).append(idx)
        # Secondary: (section, row, seat) — seat field may be "5+6"
        for seat_tok in re.split(r"[+,]", p["seats"]):
            st = seat_tok.strip().upper()
            if st:
                key = (p["section"], p["row"], st)
                srs_to_idx.setdefault(key, []).append(idx)

    print(f"    {len(slug_to_idx)} unique viewer slugs indexed, "
          f"{len(srs_to_idx)} S/R/Seat keys indexed")

    # ── Step 2b: build extra slug index from generate_out.json + stock CSVs ───
    # These files contain stock lines for passes that were generated but never
    # written to links.txt.  We use them to find lines we can append/update.
    extra_slug_lines: dict[str, str] = {}   # old_slug → full stock line (raw)

    def _scan_extra_source(text: str) -> None:
        for line in text.splitlines():
            line = line.strip()
            if not line or " | " not in line:
                continue
            m = _slug_from_url_str(line)
            if m:
                extra_slug_lines.setdefault(m[1], line)

    search_dirs = [links_path.parent]
    if vercel_site:
        search_dirs.append(vercel_site.parent)
    for d in search_dirs:
        # generate_out.json — contains {"stock_lines": [...]}
        gen_out = d / "generate_out.json"
        if gen_out.is_file():
            try:
                gdata = json.loads(gen_out.read_text(encoding="utf-8", errors="replace"))
                for sl in (gdata.get("stock_lines") or []):
                    if isinstance(sl, str):
                        _scan_extra_source(sl)
                print(f"    [+] Scanned {gen_out.name}: {len(extra_slug_lines)} extra slugs so far")
            except Exception as e:
                print(f"    [!] generate_out.json read error: {e}")
        # secure_pass_stock*.csv
        for csv_path in sorted(d.glob("secure_pass_stock*.csv")):
            try:
                _scan_extra_source(csv_path.read_text(encoding="utf-8", errors="replace"))
                print(f"    [+] Scanned {csv_path.name}: {len(extra_slug_lines)} extra slugs so far")
            except Exception as e:
                print(f"    [!] {csv_path.name} read error: {e}")

    # ── Step 3: build reslug plan ──────────────────────────────────────────────
    print(f"\n[*] Building reslug plan...")

    class SlugJob:
        __slots__ = ("pdf_path", "full_url", "gid", "old_slug", "new_slug_val",
                     "new_full_url", "links_idx", "match_method",
                     "html_path", "text_fields", "extra_append_line")

    jobs: list[SlugJob] = []
    for pdf_path, full_url, gid, old_slug in pdf_info:
        ns = new_slug()
        new_full_url = re.sub(
            r"/tickets/\d+/[^/\s]+",
            f"/tickets/{gid}/{ns}",
            full_url,
        )

        # Primary match: viewer URL slug in links.txt
        idxs   = slug_to_idx.get(old_slug, [])
        method = "slug"

        # Fallback 1: section/row/seat from PDF filename in links.txt
        if not idxs:
            fn_srs = parse_filename_srs(pdf_path.stem)
            sec, row, seat = fn_srs["section"], fn_srs["row"], fn_srs["seat"]
            idxs = srs_match_idxs(parsed_rows, sec, row, seat)
            method = f"filename S={sec} R={row} seat={seat}" if idxs else "none"

        # Fallback 2: find in generate_out.json / stock CSVs → will APPEND to links.txt
        extra_line: str | None = None
        if not idxs and old_slug in extra_slug_lines:
            raw_extra = extra_slug_lines[old_slug]
            # Replace old slug with new slug in the line
            extra_line = raw_extra.replace(old_slug, ns)
            if not extra_line.endswith("\n"):
                extra_line += "\n"
            method = "extra-source-append"

        # Find HTML file in vercel site
        html_path: Path | None = None
        if vercel_site:
            cand = vercel_site / "tickets" / gid / f"{old_slug}.html"
            if cand.is_file():
                html_path = cand

        # Skip entirely if HTML not found locally — keep URL and PDF unchanged
        if html_path is None:
            print(f"    [skip] {pdf_path.name} — HTML not found locally, leaving unchanged")
            continue

        hint_core = ""
        if idxs:
            hint_core = (parsed_rows.get(idxs[0], {}).get("event_name") or "").strip()
        elif old_slug in extra_slug_lines:
            _pl = parse_links_line(extra_slug_lines[old_slug])
            hint_core = ((_pl.get("event_name") or "").strip()) if _pl else ""
        hint_core = hint_core or event_hint_from_pdf_stem(pdf_path.stem)

        try:
            _hp_chunk = html_path.read_text(encoding="utf-8", errors="replace")[:400_000]
        except OSError:
            _hp_chunk = ""
        if _hp_chunk and not html_chunk_matches_event_hint(hint_core, _hp_chunk):
            print(
                f"    [skip] {pdf_path.name} — tickets/{gid}/{old_slug}.html title does not match "
                f"event {hint_core!r} (wrong pass page — regenerate viewer for this seat)"
            )
            continue

        text_fields = extract_text_fields_from_pdf(pdf_path)
        if idxs:
            enrich_fields_from_parsed_links_row(parsed_rows.get(idxs[0]), text_fields)
        elif old_slug in extra_slug_lines:
            enrich_fields_from_parsed_links_row(
                parse_links_line(extra_slug_lines[old_slug]),
                text_fields,
            )

        j = SlugJob()
        j.pdf_path          = pdf_path
        j.full_url          = full_url
        j.gid               = gid
        j.old_slug          = old_slug
        j.new_slug_val      = ns
        j.new_full_url      = new_full_url
        j.links_idx         = idxs
        j.match_method      = method
        j.html_path         = html_path
        j.text_fields       = text_fields
        j.extra_append_line = extra_line
        jobs.append(j)

    if not jobs:
        sys.exit("[!] Nothing to process.")

    matched   = sum(1 for j in jobs if j.links_idx)
    unmatched = len(jobs) - matched
    print(f"    {matched} matched in links.txt, {unmatched} unmatched")

    # ── Preview ────────────────────────────────────────────────────────────────
    print(f"\n[{'DRY RUN' if args.dry_run else '*'}] Plan ({len(jobs)} ticket(s)):\n")
    for j in jobs:
        print(f"  PDF      : {j.pdf_path.name}")
        print(f"  Old URL  : {j.full_url}  →  new slug: {j.new_slug_val}")
        if j.html_path:
            print(f"  HTML     : tickets/{j.gid}/{j.old_slug}.html  →  {j.new_slug_val}.html")
        else:
            print(f"  HTML     : [not found locally — skipped]")
        if j.links_idx:
            print(f"  links.txt: {len(j.links_idx)} line(s) updated via [{j.match_method}]")
        elif j.extra_append_line:
            print(f"  links.txt: 1 line APPENDED from extra source  [{j.match_method}]")
        else:
            print(f"  links.txt: [!] NO MATCH anywhere (slug={j.old_slug})")
        print()

    # ── Safety: detect collisions before writing anything ─────────────────────
    # Each links.txt line index must appear in AT MOST ONE job.
    # Deduplicate within each job first, then check cross-job collisions.
    seen_idxs: dict[int, str] = {}   # idx → pdf name that claimed it
    safe_jobs: list[SlugJob] = []
    for j in jobs:
        # Deduplicate within this job (guards against SRS returning same idx twice)
        unique_idxs = list(dict.fromkeys(j.links_idx))
        safe_idxs = []
        for idx in unique_idxs:
            if idx in seen_idxs:
                print(f"  [!] COLLISION: line {idx+1} claimed by "
                      f"{seen_idxs[idx]} and {j.pdf_path.name} — skipping for {j.pdf_path.name}")
            else:
                seen_idxs[idx] = j.pdf_path.name
                safe_idxs.append(idx)
        j.links_idx = safe_idxs
        safe_jobs.append(j)
    jobs = safe_jobs

    total_lines_to_change = sum(len(j.links_idx) for j in jobs)
    total_lines_to_append = sum(1 for j in jobs if j.extra_append_line and not j.links_idx)
    total_lines_in_file   = len(raw_lines)
    if total_lines_to_change == 0 and total_lines_to_append == 0 and not any(j.html_path for j in jobs):
        print("\n[!] Nothing matched — aborting. No files touched.")
        return

    print(f"\n[SAFETY CHECK]")
    print(f"  Total lines in links file   : {total_lines_in_file}")
    print(f"  Lines that WILL be changed  : {total_lines_to_change}  "
          f"({100*total_lines_to_change/max(1,total_lines_in_file):.1f}% of file)")
    print(f"  Lines that WILL be appended : {total_lines_to_append}  (found in extra sources)")
    print(f"  Lines that will NOT change  : {total_lines_in_file - total_lines_to_change}")
    if total_lines_to_change > len(jobs) * 2:
        print(f"  [!] WARNING: more lines matched than expected "
              f"({total_lines_to_change} for {len(jobs)} PDFs) — review carefully")

    if args.dry_run:
        print("\n[*] Dry run complete — nothing written.")
        print("    Run with --confirm to apply.")
        return

    print(f"\n  Proceeding with {total_lines_to_change} change(s)...\n")

    # ── Backup links.txt ───────────────────────────────────────────────────────
    if not args.no_backup:
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = links_path.with_suffix(links_path.suffix + f".bak_{ts}")
        shutil.copy2(links_path, bak)
        print(f"[*] Backup: {bak}")

    # ── Locate deliveries JSONL ────────────────────────────────────────────────
    deliveries_jsonl: Path | None = None
    for cand in [
        links_path.parent / "tm_viewer_deliveries.jsonl",
        *(
            [vercel_site.parent / "tm_viewer_deliveries.jsonl"]
            if vercel_site else []
        ),
    ]:
        if cand.is_file():
            deliveries_jsonl = cand
            break

    # Locate registry
    reg_path: Path | None = None
    if vercel_site:
        cand = vercel_site / "tm_viewer_link_registry.json"
        if cand.is_file():
            reg_path = cand

    # ── Execute jobs ───────────────────────────────────────────────────────────
    new_lines = list(raw_lines)

    for j in jobs:
        print(f"[*] {j.pdf_path.name}")

        # 1. New slug pass + invalidate old slug page (buyers on old links see notice)
        if j.html_path and j.html_path.is_file():
            new_html_path = rotate_slug_html_files(
                j.html_path, j.old_slug, j.new_slug_val
            )
            print(
                f"    [+] HTML: {j.old_slug}.html invalidated, "
                f"new pass → {new_html_path.name}"
            )
        else:
            print(f"    [-] HTML file not found — skipped")

        # 2. Update registry JSON
        if reg_path:
            changed = update_registry(reg_path, j.old_slug, j.new_slug_val, j.gid)
            print(f"    [{'+'if changed else '-'}] Registry: {'updated' if changed else 'no match found'}")

        # 3. Update deliveries JSONL
        if deliveries_jsonl:
            old_url_base = j.full_url.rstrip("/")
            new_url_base = j.new_full_url.rstrip("/")
            n = update_deliveries_jsonl(deliveries_jsonl, j.old_slug, j.new_slug_val,
                                        old_url_base, new_url_base)
            print(f"    [{'+'if n else '-'}] Deliveries JSONL: {n} line(s) updated")

        # 4. Update links.txt in-memory — ONLY the exact matched lines, nothing else
        if j.links_idx:
            changed_links = 0
            for idx in j.links_idx:
                parsed_ln = parse_links_line(new_lines[idx])
                if not parsed_ln:
                    continue
                old_lk = parsed_ln["link"]
                if j.old_slug in old_lk:
                    # Viewer URL already in link — swap only the slug portion
                    new_lk = old_lk.replace(j.old_slug, j.new_slug_val)
                else:
                    # SRS fallback match: old link is a TM/other URL, replace it
                    # entirely with the new viewer URL
                    suffix = ".html" if old_lk.lower().endswith(".html") else ""
                    new_lk = j.new_full_url.rstrip("/") + suffix
                # GUARD: only write if the new line is actually different
                rebuilt = rebuild_links_line(parsed_ln, new_lk)
                if rebuilt != new_lines[idx]:
                    new_lines[idx] = rebuilt
                    changed_links += 1
            print(f"    [+] links.txt: {changed_links}/{len(j.links_idx)} line(s) updated via [{j.match_method}]")
        elif j.extra_append_line:
            # Line found in extra source — append with new slug to links.txt
            new_lines.append(j.extra_append_line)
            print(f"    [+] links.txt: appended 1 new line from extra source")
        else:
            print(f"    [-] links.txt: no match anywhere — HTML/registry still updated")

        # 5. Regenerate PDF
        if _HAS_GEN:
            tf = j.text_fields
            # Fallback: try to build fields from links.txt parsed line
            # (re-parse from new_lines since they were updated)
            ev_name = tf.get("event_name") or j.pdf_path.stem
            when    = tf.get("when", "")
            where   = tf.get("where", "")
            seats   = tf.get("seats", "")
            event_id= tf.get("event_id", "")
            contact = args.contact or tf.get("contact", "support@tixx.pw")
            new_url = j.new_full_url

            # Save old PDF as .bak
            bak_pdf = j.pdf_path.with_suffix(".pdf.bak")
            shutil.copy2(j.pdf_path, bak_pdf)

            try:
                generate_pdf(
                    event_name=ev_name,
                    when=when,
                    where=where,
                    seats=seats,
                    event_id=event_id,
                    url=new_url,
                    contact=contact,
                    out_path=j.pdf_path,
                )
                print(f"    [+] PDF regenerated: {j.pdf_path.name}")
                bak_pdf.unlink(missing_ok=True)
            except Exception as e:
                print(f"    [!] PDF generation failed: {e} — restoring backup", file=sys.stderr)
                shutil.copy2(bak_pdf, j.pdf_path)
                bak_pdf.unlink(missing_ok=True)
        else:
            print(f"    [-] PDF not regenerated (reportlab/qrcode not installed)")

    # ── Write links.txt ────────────────────────────────────────────────────────
    links_path.write_text("".join(new_lines), encoding="utf-8")
    print(f"\n[+] links.txt saved ({len(new_lines)} lines) → {links_path}")
    print(f"[+] Done — {len(jobs)} ticket(s) reslugged.")


if __name__ == "__main__":
    main()
