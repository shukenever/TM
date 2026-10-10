#!/usr/bin/env python3
"""
StubHub worker Telegram bot.

work1 — worm.rip inboxes (email + recovery phrase) for StubHub listing.
work3 — log into ticket apps from admin queue; confirm section/row/seat.
work2 — /next lists events work3 confirmed; uses worm accounts from work1.
Admin — /importqueue (ticket_stock txt), /export snapshot, mail on worm inboxes.

Admin:
  /role <telegram_id> work1|work2|work3|off
  /workers
  /del <id>
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import time
import zipfile
from pathlib import Path

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import stubhub_capture as capture
import stubhub_db as db
import stubhub_listings as listings
import stubhub_sale_notify as sale_notify
import stubhub_worm as worm

ROOT = Path(__file__).resolve().parent
CFG_PATH = Path(os.environ.get("SH_BOT_CONFIG") or ROOT / "stubhub_bot.config.json")

DEFAULT_BOT_TOKEN = "8743432465:AAFjFdE8E3pAwhVcpXFOO9G9kbH1b7WCvs0"
DEFAULT_ADMIN_IDS = "7550227847"
PAGE_SIZE = 5
POLL_SECONDS = 120


def _load_cfg() -> dict:
    if CFG_PATH.is_file():
        try:
            return json.loads(CFG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


CFG = _load_cfg()
BOT_TOKEN = os.environ.get("SH_BOT_TOKEN") or CFG.get("bot_token") or DEFAULT_BOT_TOKEN
ADMIN_IDS = {
    int(x)
    for x in str(os.environ.get("SH_ADMIN_IDS") or CFG.get("admin_ids") or DEFAULT_ADMIN_IDS).split(",")
    if str(x).strip().isdigit()
}
POLL_SECONDS = int(CFG.get("mail_poll_seconds") or POLL_SECONDS)
worm.configure(CFG.get("worm_api_key"), CFG.get("worm_api_base"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("stubhub_bot")

_POLL_LOCK = asyncio.Lock()


def _admin(uid: int) -> bool:
    return uid in ADMIN_IDS


def _role(uid: int) -> str | None:
    if _admin(uid):
        return "admin"
    row = db.get_worker(uid)
    if not row:
        return None
    return str(row["role"])


def _can_add(uid: int) -> bool:
    return _role(uid) in ("admin", "work1")


def _can_list(uid: int) -> bool:
    return _role(uid) in ("admin", "work2")


def _can_capture(uid: int) -> bool:
    return _role(uid) in ("admin", "work3")


def _private(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type == "private")


def _touch(update: Update) -> int | None:
    user = update.effective_user
    if not user:
        return None
    name = " ".join(p for p in (user.first_name, user.last_name) if p).strip()
    db.touch_user(user.id, user.username or "", name)
    return user.id


def _chunks(text: str, size: int = 3800) -> list[str]:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text:
        return ["(empty)"]
    if len(text) <= size:
        return [text]
    return [text[i : i + size] for i in range(0, len(text), size)]


def _counts_line() -> str:
    c = db.counts()
    return f"Left (free): {c['free']} | Used: {c['used']} | Total: {c['total']}"


def _cred(row: dict) -> str:
    phrase = str(row.get("recovery_phrase") or "").strip()
    if phrase:
        return f"{row['email']}\nphrase: {phrase}"
    return str(row["email"])


def _fmt_account(row: dict) -> str:
    lines = [
        f"#{row['id']} {str(row['status']).upper()}",
        _cred(row),
    ]
    if row.get("event"):
        lines.append(f"event: {row['event']}")
    who = row.get("created_by") or ""
    lines.append(f"added: {row['created_at']} by {who}")
    if row.get("status") == "used":
        lines.append(f"used: {row.get('used_at') or ''} by {row.get('used_by') or ''}")
    if row.get("login_error"):
        err = str(row["login_error"])
        if len(err) > 180:
            err = err[:180] + "..."
        lines.append(f"mail error: {err}")
    return "\n".join(lines)


def _dump_text() -> str:
    rows = db.list_accounts()
    parts = ["StubHub accounts", _counts_line(), ""]
    if not rows:
        parts.append("(none)")
    for row in rows:
        parts.append(_fmt_account(row))
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def _page_text(status: str, page: int) -> tuple[str, InlineKeyboardMarkup | None]:
    rows = db.list_accounts(status=status)
    title = "Free accounts" if status == "free" else "Used accounts"
    if not rows:
        return f"{title}\n{_counts_line()}\n\nNone.", None
    pages = max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    chunk = rows[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    body = "\n\n".join(_fmt_account(r) for r in chunk)
    text = f"{title}  {page + 1}/{pages}\n{_counts_line()}\n\n{body}"
    buttons: list[list[InlineKeyboardButton]] = []
    if status == "free":
        for row in chunk:
            buttons.append(
                [InlineKeyboardButton(f"Mark #{row['id']} used", callback_data=f"use:{row['id']}")]
            )
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("Prev", callback_data=f"pg:{status}:{page - 1}"))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton("Next", callback_data=f"pg:{status}:{page + 1}"))
    if nav:
        buttons.append(nav)
    markup = InlineKeyboardMarkup(buttons) if buttons else None
    return text, markup


def _help(role: str | None) -> str:
    base = (
        "StubHub accounts bot\n"
        "/id — your telegram id\n"
        "/cancel — stop the current prompt\n"
    )
    if role == "admin":
        return (
            base
            + "\nAdmin\n"
            "/role <id> work1 — account maker (worm inboxes)\n"
            "/role <id> work2 — lister (StubHub)\n"
            "/role <id> work3 — login / seat capture\n"
            "/role <id> off\n"
            "/workers\n"
            "/importqueue — ticket_stock .txt → work3 capture queue\n"
            "/queue — capture + listing queue stats\n"
            "/requeue <capture_id> — put failed/assigned job back to pending\n"
            "/export — full DB snapshot for admin\n"
            "/clearlistings confirm — wipe all lister seats (pending + listed)\n"
            "/add — email, then recovery phrase\n"
            "/accs — full database\n"
            "/free  /used  /stats\n"
            "/info <id>   /find <email>\n"
            "/use <id> <event>\n"
            "/reset <id> — mark free again\n"
            "/setphrase <id> <phrase>\n"
            "/del <id>\n"
            "/import — legacy listing dump + PDF zip (optional)\n"
            "/next — lister queue (after work3 confirms seats)\n"
            "/mobile — the mobile ticket file\n"
            "\nBoth the email and the phrase are required.\n"
            "This bot does not generate inboxes.\n"
            "Every new email is sent here with subject, mailbox, phrase, and body."
        )
    if role == "work1":
        return (
            base
            + "\nYou make accounts.\n"
            "/add\n"
            "1. Send the worm.rip email\n"
            "2. Send the recovery phrase\n"
            "Both are saved together. Email alone is not enough.\n"
            "\nThis bot only checks that inbox. It does not create one.\n"
            "/mine — accounts you added\n"
            "/info <id>   /find <email>\n"
            "Listers are notified as soon as an account is saved."
        )
    if role == "work2":
        return (
            base
            + "\nYou list tickets.\n"
            "/accs — full database (free, used, left)\n"
            "/stats\n"
            "/free — unused accounts\n"
            "/used\n"
            "/info <id>   /find <email>\n"
            "/use <id> <event name>\n"
            "Or tap Mark used, then send the event name.\n"
            "/next — next confirmed event (section/row/seat from work3).\n"
            "Tap Listed, then send the worm account email + recovery phrase.\n"
            "Skip passes it. Mobile ticket saves that event on its own.\n"
        )
    if role == "work3":
        return (
            base
            + "\nYou log into ticket apps and capture seats.\n"
            "/capture — next account from the admin queue\n"
            "Reply with seats, then tap Confirm.\n"
            "Format:\n"
            "section: 109\nrow: C\nseats: 15,16,17\n"
            "or one line per seat: 109 | C | 15\n"
            "/cancel — release current job"
        )
    return (
        base
        + "\nYou are not assigned yet. Send your /id to the admin.\n"
        "work1 = worm accounts · work3 = seat capture · work2 = list on StubHub"
    )


async def _send(bot, chat_id: int, text: str) -> bool:
    parts = _chunks(text)
    for i, part in enumerate(parts):
        try:
            await bot.send_message(chat_id, part)
        except Exception as exc:
            log.warning("send to %s failed: %s", chat_id, exc)
            return False
        if i + 1 < len(parts):
            await asyncio.sleep(0.25)
    return True


async def _notify_admins(bot, text: str) -> bool:
    ok = True
    for admin_id in sorted(ADMIN_IDS):
        if not await _send(bot, admin_id, text):
            ok = False
    return ok


def _mobile_record(rows: list[dict], uid: int, name: str) -> str:
    body = listings.format_event(rows, 0)
    lines = [ln for ln in body.split("\n") if not ln.startswith("Left in queue:")]
    who = f"{uid} {name}".strip()
    return f"MOBILE TICKET\n{db._now()}\nby: {who}\n" + "\n".join(lines)


def _list_keyboard(listing_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Listed", callback_data=f"ls:ok:{listing_id}"),
                InlineKeyboardButton("Skip", callback_data=f"ls:skip:{listing_id}"),
            ],
            [
                InlineKeyboardButton(
                    "This is a mobile ticket",
                    callback_data=f"ls:mob:{listing_id}",
                )
            ],
        ]
    )


async def _send_event_pdfs(message, rows: list) -> None:
    for raw in rows:
        row = dict(raw)
        if not row.get("pdf_name"):
            continue
        path = db.listing_pdf_path(int(row["id"]))
        if not path.is_file():
            continue
        filename = listings.seat_pdf_filename(
            row["event_name"], row["section"], row["row_name"], row["seat"]
        )
        with path.open("rb") as handle:
            await message.reply_document(document=handle, filename=filename)


async def _show_next_listing(message, context: ContextTypes.DEFAULT_TYPE, uid: int) -> None:
    skip = [int(i) for i in (context.user_data.get("list_skip") or [])]
    rows = db.claim_next_event(uid, skip)
    if not rows and skip:
        await message.reply_text(
            "No more new events. Skipped ones are still in the queue. Send /next to see them again."
        )
        context.user_data["list_skip"] = []
        return
    if not rows:
        counts = db.listing_counts()
        await message.reply_text(f"Queue is empty. Listed seats: {counts['listed']}")
        return
    counts = db.listing_counts()
    await _send_event_pdfs(message, rows)
    await message.reply_text(
        listings.format_event([dict(r) for r in rows], counts["pending_events"]),
        reply_markup=_list_keyboard(int(rows[0]["id"])),
    )


def _read_pdf_zip(raw: bytes) -> tuple[dict[str, tuple[str, bytes]], str | None]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return {}, "That file is not a zip."
    files: dict[str, tuple[str, bytes]] = {}
    with zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/").rsplit("/", 1)[-1]
            if not name or name.startswith(".") or name.startswith("__"):
                continue
            if not name.lower().endswith(".pdf"):
                continue
            key = listings.pdf_key_from_filename(name)
            if not key:
                continue
            files[key] = (name, zf.read(info))
    if not files:
        return {}, "The zip has no PDFs."
    return files, None


def _clip_lines(lines: list[str], limit: int = 12) -> str:
    if len(lines) <= limit:
        return "\n".join(lines)
    extra = len(lines) - limit
    return "\n".join(lines[:limit]) + f"\n… and {extra} more"


async def _try_finish_import(update: Update, context: ContextTypes.DEFAULT_TYPE, *, force: bool = False) -> None:
    text = context.user_data.get("import_text")
    files: dict = context.user_data.setdefault("import_pdfs", {})
    if not text or not files:
        have = []
        need = []
        if text:
            have.append("text")
        else:
            need.append("the .txt")
        if files:
            have.append(f"{len(files)} PDF(s)")
        else:
            need.append("a .zip of PDFs")
        await update.message.reply_text(
            f"Got the {' and '.join(have)}. Still need {' and '.join(need)}.\n"
            "You can send more than one zip. PDF name: Event Name Section Row Seat.pdf"
        )
        return
    rows = listings.parse_listing_dump(text)
    if not rows:
        context.user_data.pop("import_text", None)
        await update.message.reply_text(
            "No seats in that text. It needs ACCOUNT, EVENT, and Sec / Row / Seat lines."
        )
        return
    missing_now = [
        f"{row['event_name']} {row['section']} {row['row_name']} {row['seat']}"
        for row in rows
        if listings.pdf_key(row["event_name"], row["section"], row["row_name"], row["seat"]) not in files
    ]
    if missing_now and not force:
        await update.message.reply_text(
            f"PDFs so far: {len(files)}. Still missing {len(missing_now)} of {len(rows)}.\n"
            "Send the next zip, or /done to import what is here."
        )
        return
    context.user_data.pop("import_wait", None)
    context.user_data.pop("import_text", None)
    context.user_data.pop("import_pdfs", None)
    added, skipped = db.insert_listings(rows)
    saved, missing, unused = db.attach_seat_pdfs(rows, files)
    counts = db.listing_counts()
    parts = [
        f"Imported {added} seat(s). Already in queue: {skipped}.",
        f"PDFs matched: {saved} of {len(rows)}.",
        f"Pending {counts['pending_events']} event(s) · {counts['pending']} seat(s) · Listed {counts['listed']}",
    ]
    if missing:
        parts.append("No PDF for:\n" + _clip_lines(missing))
    if unused:
        parts.append("Zip PDFs with no matching seat:\n" + _clip_lines(unused))
    await update.message.reply_text("\n".join(parts))
    if added:
        note = (
            f"{counts['pending_events']} event(s) in the queue. "
            "/next shows one event and sends the seat PDFs."
        )
        for worker in db.list_workers("work2"):
            await _send(context.bot, int(worker["telegram_id"]), note)


async def on_import_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.document or not _private(update):
        return
    if not update.effective_user or not _admin(update.effective_user.id):
        return
    name = update.message.document.file_name or ""
    lower = name.lower()
    tg_file = await update.message.document.get_file()
    raw = bytes(await tg_file.download_as_bytearray())
    if context.user_data.get("queue_import_wait") and _admin(update.effective_user.id):
        if not lower.endswith(".txt"):
            await update.message.reply_text("Send a .txt export (tab ticket_stock or readable blocks).")
            return
        context.user_data.pop("queue_import_wait", None)
        text_body = raw.decode("utf-8", errors="replace")
        rows = capture.parse_import_file(text_body)
        if not rows:
            await update.message.reply_text(
                "No rows parsed.\n"
                "Send ticket_stock .txt (tab) OR *_readable.txt blocks:\n"
                "email:pass | app | event | date | venue"
            )
            return
        added, skipped = db.insert_capture_jobs(rows)
        cc = db.capture_counts()
        await update.message.reply_text(
            f"Capture queue: +{added} new, {skipped} duplicate skipped.\n"
            f"pending {cc['pending']} · tell work3 to /capture"
        )
        for worker in db.list_workers("work3"):
            await _send(
                context.bot,
                int(worker["telegram_id"]),
                f"Admin added {added} capture job(s). /capture to start.",
            )
        return
    if not context.user_data.get("import_wait"):
        return
    if lower.endswith(".txt"):
        context.user_data["import_text"] = raw.decode("utf-8", errors="replace")
        await _try_finish_import(update, context)
        return
    if lower.endswith(".zip"):
        found, err = _read_pdf_zip(raw)
        if err:
            await update.message.reply_text(err)
            return
        files = context.user_data.setdefault("import_pdfs", {})
        files.update(found)
        await update.message.reply_text(f"Zip added. {len(files)} PDF(s) so far.")
        await _try_finish_import(update, context)
        return
    await update.message.reply_text("Send the .txt and zip files of one PDF per seat.")


async def done_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    if not _admin(update.effective_user.id) or not context.user_data.get("import_wait"):
        return
    await _try_finish_import(update, context, force=True)


async def import_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    if not _admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    context.user_data.pop("add_step", None)
    context.user_data.pop("await_event", None)
    context.user_data.pop("import_text", None)
    context.user_data.pop("import_pdfs", None)
    context.user_data["import_wait"] = True
    await update.message.reply_text(
        "Legacy import (bypasses work3): ACCOUNT/EVENT dump + PDF zips.\n"
        "For the normal pipeline use /importqueue (ticket_stock txt) instead.\n\n"
        "Send the .txt and zip files. PDF name: Event Name Section Row Seat.pdf\n"
        "/done imports once ready. /cancel stops."
    )


async def _list_email_step(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    email = text.strip().lower()
    if "@" not in email or " " in email:
        await update.message.reply_text("Send the account email.")
        return
    row = db.get_account_by_email(email)
    if not row:
        await update.message.reply_text("No created account with that email. Check /free and send it again.")
        return
    if row["status"] != "free":
        await update.message.reply_text(f"{row['email']} is already {row['status']}. Send a free account.")
        return
    context.user_data["list_account_id"] = int(row["id"])
    context.user_data["list_ask"] = "phrase"
    await update.message.reply_text(f"Send the recovery phrase for {row['email']}.")


async def _list_phrase_step(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    account_id = context.user_data.get("list_account_id")
    listing_id = context.user_data.get("list_id")
    if not account_id or not listing_id:
        context.user_data.pop("list_ask", None)
        await update.message.reply_text("Send /next and tap Listed again.")
        return
    account = db.get_account(int(account_id))
    if not account or account["status"] != "free":
        context.user_data["list_ask"] = "email"
        context.user_data.pop("list_account_id", None)
        await update.message.reply_text("That account is no longer free. Send another email.")
        return
    if _norm_phrase(text) != _norm_phrase(str(account.get("recovery_phrase") or "")):
        await update.message.reply_text("That phrase does not match this account. Send the recovery phrase again.")
        return
    uid = update.effective_user.id
    anchor = db.get_listing(int(listing_id)) or {}
    if not anchor.get("event_name"):
        context.user_data.pop("list_ask", None)
        context.user_data.pop("list_id", None)
        context.user_data.pop("list_account_id", None)
        await update.message.reply_text("That event is gone. Send /next.")
        return
    event = f"{anchor['event_name']} | {anchor['event_date']}"
    used = db.mark_used(int(account_id), uid, event[:300])
    if used != "ok":
        context.user_data["list_ask"] = "email"
        context.user_data.pop("list_account_id", None)
        await update.message.reply_text("Could not use that account. Send another email.")
        return
    rows = db.mark_event_listed(int(listing_id), uid, int(account_id))
    context.user_data.pop("list_ask", None)
    context.user_data.pop("list_id", None)
    context.user_data.pop("list_account_id", None)
    if not rows:
        await update.message.reply_text("Account saved as used, but that event was already moved on. Send /next.")
        return
    saved = db.get_account(int(account_id)) or account
    name = " ".join(
        p for p in (update.effective_user.first_name, update.effective_user.last_name) if p
    ).strip()
    counts = db.listing_counts()
    first = rows[0]
    seat_lines = [
        f"Sec {r['section']}   Row {r['row_name']}   Seat {r['seat']}"
        for r in rows
    ]
    await _notify_admins(
        context.bot,
        "LISTED\n"
        f"#{saved['id']} {saved['email']}\n"
        f"phrase: {saved.get('recovery_phrase') or ''}\n"
        f"EVENT:  {first['event_name']}\n"
        f"DATE:   {first['event_date']}\n"
        f"VENUE:  {first['venue']}\n"
        + "\n".join(seat_lines)
        + f"\nby: {uid} {name}\n"
        f"left: {counts['pending_events']}",
    )
    await update.message.reply_text(
        f"Listed on {saved['email']}\n"
        f"{first['event_name']}\n"
        f"{len(rows)} seat(s)"
    )
    await _show_next_listing(update.message, context, uid)


def _capture_keyboard(job_id: int, has_seats: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Enter seats (reply in chat)", callback_data=f"cap:seats:{job_id}")],
    ]
    if has_seats:
        rows.append([InlineKeyboardButton("Confirm → lister queue", callback_data=f"cap:ok:{job_id}")])
    rows.append(
        [
            InlineKeyboardButton("Can't login", callback_data=f"cap:fail:{job_id}"),
            InlineKeyboardButton("Release job", callback_data=f"cap:rel:{job_id}"),
        ]
    )
    return InlineKeyboardMarkup(rows)


async def _show_capture_job(message, uid: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Claim or resume job; return False if queue empty."""
    job = db.claim_capture_job(uid)
    if not job:
        return False
    context.user_data["capture_job_id"] = int(job["id"])
    seats = db.get_capture_seats(int(job["id"]))
    await message.reply_text(
        capture.format_job_card(job, seats),
        reply_markup=_capture_keyboard(int(job["id"]), bool(seats)),
    )
    return True


async def capture_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    uid = _touch(update)
    if uid is None or not _can_capture(uid):
        await update.message.reply_text("Seat capture is for work3 (and admin).")
        return
    context.user_data.pop("capture_ask", None)
    if not await _show_capture_job(update.message, uid, context):
        cc = db.capture_counts()
        await update.message.reply_text(
            f"Capture queue empty.\n"
            f"pending {cc['pending']} · assigned {cc['assigned']} · confirmed {cc['confirmed']}"
        )


async def importqueue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    if not _admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    context.user_data.pop("import_wait", None)
    context.user_data["queue_import_wait"] = True
    await update.message.reply_text(
        "Send ticket_stock .txt (tab) OR *_readable.txt (email:pass | app | event…).\n"
        "Work3 will log in and confirm section/row/seat before listers see the event.\n"
        "/cancel to stop."
    )


async def queue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    uid = _touch(update)
    role = _role(uid) if uid else None
    if role not in ("admin", "work2", "work3"):
        await update.message.reply_text("Not assigned.")
        return
    cc = db.capture_counts()
    lc = db.listing_counts()
    lines = [
        "Pipeline",
        f"Capture: pending {cc['pending']} · in progress {cc['assigned']} · "
        f"confirmed {cc['confirmed']} · failed {cc['failed']}",
        f"Lister queue: {lc['pending_events']} event(s), {lc['pending']} seat(s) pending · "
        f"{lc['listed']} listed",
        f"Worm accounts: {_counts_line()}",
    ]
    if role == "admin":
        lines.append("")
        lines.append("work1 → worm /add · admin /importqueue · work3 /capture · work2 /next")
    await update.message.reply_text("\n".join(lines))


async def requeue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    if not _admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /requeue <capture_job_id>")
        return
    job_id = int(context.args[0])
    result = db.requeue_capture_job(job_id)
    if result == "missing":
        await update.message.reply_text(f"No capture job #{job_id}.")
    elif result == "locked":
        await update.message.reply_text(f"#{job_id} is already confirmed (in lister history).")
    else:
        cc = db.capture_counts()
        await update.message.reply_text(
            f"#{job_id} back to pending.\nCapture pending: {cc['pending']}"
        )


async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    if not _admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    text = db.admin_export_snapshot()
    buf = io.BytesIO(text.encode("utf-8"))
    await update.message.reply_document(
        document=InputFile(buf, filename="stubhub_admin_export.txt"),
        caption="Accounts + capture queue + listing counts",
    )


async def clearlistings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    if not _admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    counts = db.listing_counts()
    if not context.args or context.args[0].lower() != "confirm":
        await update.message.reply_text(
            "This deletes every lister seat in the database "
            "(pending and listed). Worm accounts and the work3 capture queue stay.\n\n"
            f"Now: {counts['total']} seat(s) "
            f"({counts['pending']} pending · {counts['listed']} listed · "
            f"{counts['pending_events']} event(s) in /next queue).\n\n"
            "To proceed: /clearlistings confirm"
        )
        return
    result = db.clear_all_listings()
    await update.message.reply_text(
        f"Listings cleared.\n"
        f"Removed {result['deleted']} seat(s) "
        f"({result['pending']} pending · {result['listed']} listed).\n"
        f"Lister queue: {db.listing_counts()['total']} seat(s) left."
    )
    await _notify_admins(
        context.bot,
        f"CLEAR LISTINGS by admin {update.effective_user.id}\n"
        f"deleted {result['deleted']} seat(s)",
    )


async def on_capture_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not update.effective_user:
        return
    uid = update.effective_user.id
    if not _can_capture(uid):
        await query.answer("work3 only.", show_alert=True)
        return
    parts = query.data.split(":")
    if len(parts) != 3 or parts[0] != "cap" or not parts[2].isdigit():
        await query.answer()
        return
    action, job_id = parts[1], int(parts[2])
    job = db.get_capture_job(job_id)
    if not job or int(job.get("assigned_to") or 0) != uid or job["status"] != "assigned":
        await query.answer("Job not yours or already closed.", show_alert=True)
        return
    if action == "seats":
        await query.answer()
        context.user_data["capture_ask"] = "seats"
        context.user_data["capture_job_id"] = job_id
        if query.message:
            await query.message.reply_text(
                f"CAPTURE #{job_id} — send seats for qty {job['qty_expected']}:\n\n"
                "section: 109\nrow: C\nseats: 15,16\n\n"
                "or per line:\n109 | C | 15"
            )
        return
    if action == "rel":
        db.release_capture_job(job_id, uid)
        context.user_data.pop("capture_ask", None)
        context.user_data.pop("capture_job_id", None)
        await query.answer("Released")
        if query.message:
            await query.message.edit_text(f"Released capture #{job_id}.")
        return
    if action == "fail":
        db.fail_capture_job(job_id, uid, "login failed")
        context.user_data.pop("capture_ask", None)
        context.user_data.pop("capture_job_id", None)
        await query.answer("Marked failed")
        name = " ".join(
            p for p in (update.effective_user.first_name, update.effective_user.last_name) if p
        ).strip()
        await _notify_admins(
            context.bot,
            f"CAPTURE FAIL #{job_id}\n{job['email']}\n{job['event_name']}\nby {uid} {name}",
        )
        if query.message:
            await query.message.edit_text(f"Marked #{job_id} as login failed.")
        return
    if action == "ok":
        seats = db.get_capture_seats(job_id)
        if not seats:
            await query.answer("Enter seats first.", show_alert=True)
            return
        added, skipped, cerr = db.confirm_capture_job(job_id, uid)
        if cerr:
            await query.answer(cerr[:180], show_alert=True)
            return
        context.user_data.pop("capture_ask", None)
        context.user_data.pop("capture_job_id", None)
        counts = db.listing_counts()
        await query.answer("Sent to listers")
        name = " ".join(
            p for p in (update.effective_user.first_name, update.effective_user.last_name) if p
        ).strip()
        seat_lines = [
            f"{s['section']} / {s['row_name']} / {s['seat']}" for s in seats
        ]
        await _notify_admins(
            context.bot,
            "CAPTURE CONFIRMED\n"
            f"#{job_id} {job['email']}\n"
            f"{job['event_name']} | {job['event_date']}\n"
            + "\n".join(seat_lines)
            + f"\nlistings +{added} (dup {skipped}) · pending events {counts['pending_events']}\n"
            f"by {uid} {name}",
        )
        for worker in db.list_workers("work2"):
            await _send(
                context.bot,
                int(worker["telegram_id"]),
                f"New seats ready ({added} added). /next — {job['event_name'][:80]}",
            )
        if query.message:
            await query.message.edit_text(
                f"Confirmed #{job_id} → lister queue (+{added} seats, {skipped} dup)."
            )
            if not await _show_capture_job(query.message, uid, context):
                cc = db.capture_counts()
                await query.message.reply_text(
                    f"Queue empty. pending {cc['pending']} confirmed {cc['confirmed']}"
                )
        return
    await query.answer()


async def mobile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    if not _admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    path = db.MOBILE_PATH
    if not path.is_file() or path.stat().st_size == 0:
        await update.message.reply_text("No mobile tickets saved yet.")
        return
    with path.open("rb") as handle:
        await update.message.reply_document(document=handle, filename="mobile_tickets.txt")


async def next_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    uid = _touch(update)
    if uid is None or not _can_list(uid):
        await update.message.reply_text("Listers only.")
        return
    await _show_next_listing(update.message, context, uid)


async def on_listing_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not update.effective_user:
        return
    uid = update.effective_user.id
    if not _can_list(uid):
        await query.answer("Listers only.", show_alert=True)
        return
    parts = query.data.split(":")
    if len(parts) != 3 or not parts[2].isdigit():
        await query.answer()
        return
    action, listing_id = parts[1], int(parts[2])
    if action == "ok":
        await query.answer()
        context.user_data["list_ask"] = "email"
        context.user_data["list_id"] = listing_id
        context.user_data.pop("list_account_id", None)
        if query.message:
            await query.message.reply_text(
                "Which account did you list this on?\n"
                "Send the email of an account that was created here.\n"
                "/cancel to stop."
            )
        return
    if action == "skip":
        released = db.release_event(listing_id, uid)
        if not released:
            await query.answer("Already moved on.", show_alert=True)
            return
        await query.answer("Skipped")
        skipped = [int(i) for i in (context.user_data.get("list_skip") or [])]
        for rid in released:
            if rid not in skipped:
                skipped.append(rid)
        context.user_data["list_skip"] = skipped[-400:]
        if query.message:
            await query.message.edit_text("Skipped. Next event:")
            await _show_next_listing(query.message, context, uid)
        return
    if action == "mob":
        log.info("mobile tap listing=%s uid=%s", listing_id, uid)
        rows = db.mark_event_mobile(listing_id, uid)
        if not rows:
            missed = db.get_listing(listing_id)
            log.info(
                "mobile tap missed listing=%s uid=%s status=%s",
                listing_id,
                uid,
                (missed or {}).get("status"),
            )
            await query.answer("That event is not pending anymore.", show_alert=True)
            return
        await query.answer("Saved as mobile ticket")
        if context.user_data.get("list_id") == listing_id:
            context.user_data.pop("list_ask", None)
            context.user_data.pop("list_id", None)
            context.user_data.pop("list_account_id", None)
        name = " ".join(
            p for p in (update.effective_user.first_name, update.effective_user.last_name) if p
        ).strip()
        text = _mobile_record([dict(r) for r in rows], uid, name)
        db.append_mobile_ticket(text)
        sent = await _notify_admins(context.bot, text)
        log.info("mobile alert sent=%s admins=%s file=%s", sent, sorted(ADMIN_IDS), db.MOBILE_PATH)
        if query.message:
            note = "Admin notified." if sent else "Saved, but the admin message failed to send."
            await query.message.reply_text(f"{note}\n\n{text}")
            await query.message.edit_text("Saved as a mobile ticket. Next event:")
            await _show_next_listing(query.message, context, uid)
        return


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not _private(update):
        return
    uid = _touch(update)
    if uid is None:
        return
    await update.message.reply_text(_help(_role(uid)))


async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    user = update.effective_user
    _touch(update)
    await update.message.reply_text(f"Your id: {user.id}\nRole: {_role(user.id) or 'none'}")


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not _private(update):
        return
    context.user_data.pop("await_event", None)
    context.user_data.pop("add_step", None)
    context.user_data.pop("add_email", None)
    context.user_data.pop("add_api_phrase", None)
    context.user_data.pop("import_wait", None)
    context.user_data.pop("import_text", None)
    context.user_data.pop("import_pdfs", None)
    context.user_data.pop("list_ask", None)
    context.user_data.pop("list_id", None)
    context.user_data.pop("list_account_id", None)
    context.user_data.pop("queue_import_wait", None)
    context.user_data.pop("capture_ask", None)
    jid = context.user_data.pop("capture_job_id", None)
    if jid and update.effective_user and _can_capture(update.effective_user.id):
        db.release_capture_job(int(jid), update.effective_user.id)
    await update.message.reply_text("Cancelled.")


async def role_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    if not _admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    if len(context.args) != 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /role <telegram_id> work1|work2|work3|off")
        return
    tid = int(context.args[0])
    raw = context.args[1].lower().replace("_", "")
    if raw in ("work1", "1", "maker"):
        role = "work1"
    elif raw in ("work2", "2", "lister", "list"):
        role = "work2"
    elif raw in ("work3", "3", "capture", "login", "capturer"):
        role = "work3"
    elif raw in ("off", "none", "remove", "del"):
        role = None
    else:
        await update.message.reply_text("Role must be work1, work2, work3, or off.")
        return
    db.set_role(tid, role)
    if role == "work1":
        note = (
            "You are work1 (make accounts).\n"
            "/add\n"
            "The bot asks for the email, then the recovery phrase.\n"
            "Both are required. Listers are notified when it is saved."
        )
    elif role == "work2":
        note = (
            "You are work2 (list on StubHub).\n"
            "/next — events work3 already confirmed (section/row/seat).\n"
            "Tap Listed, then worm email + recovery phrase.\n"
            "/accs — worm accounts work1 created.\n"
            "You are pinged when seats are confirmed or a new worm account is added."
        )
    elif role == "work3":
        note = (
            "You are work3 (login + seat capture).\n"
            "/capture — next job from admin queue.\n"
            "Send section/row/seats, then Confirm → listers get /next."
        )
    else:
        note = "Your StubHub bot access was removed."
    try:
        await context.bot.send_message(tid, note)
        ping = "They were notified."
    except Exception as exc:
        log.info("role ping %s failed: %s", tid, exc)
        ping = "Saved, but they have not started the bot, so I could not message them."
    label = role or "off"
    await update.message.reply_text(f"{tid} set to {label}. {ping}")


async def workers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    if not _admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    rows = db.list_workers()
    if not rows:
        await update.message.reply_text("No workers yet. /role <id> work1|work2|work3")
        return
    lines = []
    for row in rows:
        name = row.get("full_name") or ""
        user = f"@{row['username']}" if row.get("username") else ""
        lines.append(f"{row['role']}  {row['telegram_id']}  {name} {user}".rstrip())
    await update.message.reply_text("Workers\n" + "\n".join(lines))


async def accs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    uid = _touch(update)
    if uid is None or not _can_list(uid):
        await update.message.reply_text("Account database is for listers (work2) and admin.")
        return
    buf = io.BytesIO(_dump_text().encode("utf-8"))
    await update.message.reply_document(
        document=InputFile(buf, filename="stubhub_accounts.txt"),
        caption=_counts_line(),
    )
    text, markup = _page_text("free", 0)
    await update.message.reply_text(text, reply_markup=markup)


async def free_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_page(update, "free", 0)


async def used_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_page(update, "used", 0)


async def _send_page(update: Update, status: str, page: int) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    uid = _touch(update)
    if uid is None or not _can_list(uid):
        await update.message.reply_text("That is for listers (work2) and admin.")
        return
    text, markup = _page_text(status, page)
    await update.message.reply_text(text, reply_markup=markup)


async def mine_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    uid = _touch(update)
    if uid is None or not _can_add(uid):
        await update.message.reply_text("That is for account makers.")
        return
    rows = db.list_accounts(created_by=uid)
    if not rows:
        await update.message.reply_text("You have not added any accounts yet.\nUse /add")
        return
    body = "\n\n".join(_fmt_account(r) for r in rows[-30:])
    await _send(context.bot, uid, f"Your accounts ({len(rows)})\n\n{body}")


async def use_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    uid = _touch(update)
    if uid is None or not _can_list(uid):
        await update.message.reply_text("Only listers can mark an account used.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /use <id> <event name>")
        return
    account_id = int(context.args[0])
    event = " ".join(context.args[1:]).strip()
    if not event:
        row = db.get_account(account_id)
        if not row:
            await update.message.reply_text(f"No account #{account_id}.")
            return
        if row["status"] != "free":
            await update.message.reply_text(f"#{account_id} is already {row['status']}.")
            return
        context.user_data["await_event"] = account_id
        await update.message.reply_text(
            f"Send the event name for #{account_id} ({row['email']}).\n/cancel to stop."
        )
        return
    await _finish_use(update, context, account_id, event)


async def _finish_use(update: Update, context: ContextTypes.DEFAULT_TYPE, account_id: int, event: str) -> None:
    if not update.effective_user or not update.message:
        return
    uid = update.effective_user.id
    event = event.strip()
    if not event:
        await update.message.reply_text("Send the event name.")
        return
    result = db.mark_used(account_id, uid, event[:300])
    context.user_data.pop("await_event", None)
    if result == "missing":
        await update.message.reply_text(f"No account #{account_id}.")
        return
    if result == "used":
        await update.message.reply_text(f"#{account_id} is already used.")
        return
    row = db.get_account(account_id) or {"email": "?", "id": account_id}
    name = " ".join(
        p for p in (update.effective_user.first_name, update.effective_user.last_name) if p
    ).strip()
    await update.message.reply_text(
        f"#{account_id} marked used\n{row['email']}\nevent: {event[:300]}\n{_counts_line()}"
    )
    await _notify_admins(
        context.bot,
        f"LISTED #{account_id}\n{row['email']}\nevent: {event[:300]}\nby: {uid} {name}\n{_counts_line()}",
    )


async def del_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    if not _admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /del <id>")
        return
    account_id = int(context.args[0])
    if db.delete_account(account_id):
        await update.message.reply_text(f"Deleted #{account_id}.\n{_counts_line()}")
    else:
        await update.message.reply_text(f"No account #{account_id}.")


async def on_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.from_user:
        return
    if not _private(update) or not _can_list(query.from_user.id):
        await query.answer("Listers only.")
        return
    await query.answer()
    parts = query.data.split(":")
    if len(parts) != 3 or parts[0] != "pg" or parts[1] not in ("free", "used") or not parts[2].isdigit():
        return
    text, markup = _page_text(parts[1], int(parts[2]))
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except Exception as exc:
        log.info("page edit failed: %s", exc)


async def on_use_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.from_user or not query.message:
        return
    if not _private(update) or not _can_list(query.from_user.id):
        await query.answer("Listers only.")
        return
    account_id_s = query.data.split(":", 1)[1]
    if not account_id_s.isdigit():
        await query.answer()
        return
    account_id = int(account_id_s)
    row = db.get_account(account_id)
    if not row:
        await query.answer("Missing account")
        return
    if row["status"] != "free":
        await query.answer("Already used")
        return
    await query.answer()
    context.user_data["await_event"] = account_id
    await query.message.reply_text(
        f"Send the event name for #{account_id} ({row['email']}).\n/cancel to stop."
    )


def _norm_phrase(text: str) -> str:
    return " ".join((text or "").lower().split())


def _preview(body: str, limit: int = 420) -> str:
    text = (body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return "(empty body)"
    lines = []
    for raw in text.split("\n"):
        line = " ".join(raw.split())
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if len(line) > 140:
            line = line[:140] + "..."
        lines.append(line)
    clipped = "\n".join(lines).strip()
    if len(clipped) <= limit:
        return clipped
    cut = clipped[:limit].rsplit(" ", 1)[0].rstrip()
    return (cut or clipped[:limit]).rstrip() + "..."


def _mail_text(row: dict, msg: dict) -> str:
    subject = str(msg.get("subject") or "")
    body = str(msg.get("body") or "")
    from_addr = str(msg.get("from") or "")
    if sale_notify.is_sale_email(subject, body, from_addr):
        hints = sale_notify.parse_sale_hints(subject, body)
        inv = db.listings_for_worm_account(int(row["id"]))
        return sale_notify.format_sale_alert(row, msg, inv, hints)
    return sale_notify.format_generic_mail(
        row,
        msg,
        _preview(body),
    )


def _can_see_account(uid: int, row: dict) -> bool:
    if _admin(uid) or _can_list(uid):
        return True
    return _can_add(uid) and int(row.get("created_by") or 0) == uid


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text or not _private(update):
        return
    uid = _touch(update)
    if uid is None:
        return
    text = update.message.text.strip()
    if context.user_data.get("queue_import_wait") and _admin(uid):
        context.user_data.pop("queue_import_wait", None)
        rows = capture.parse_import_file(text)
        if not rows:
            await update.message.reply_text(
                "No rows parsed.\n"
                "Paste ticket_stock .txt (tab) OR *_readable.txt blocks."
            )
            return
        added, skipped = db.insert_capture_jobs(rows)
        cc = db.capture_counts()
        await update.message.reply_text(
            f"Capture queue: +{added} new, {skipped} duplicate skipped.\n"
            f"pending {cc['pending']} · tell work3 to /capture"
        )
        for worker in db.list_workers("work3"):
            await _send(
                context.bot,
                int(worker["telegram_id"]),
                f"Admin added {added} capture job(s). /capture to start.",
            )
        return
    if context.user_data.get("import_wait") and _admin(uid):
        context.user_data["import_text"] = text
        await _try_finish_import(update, context)
        return
    if context.user_data.get("capture_ask") == "seats" and _can_capture(uid):
        job_id = int(context.user_data.get("capture_job_id") or 0)
        job = db.get_capture_job(job_id) if job_id else None
        if not job or int(job.get("assigned_to") or 0) != uid:
            context.user_data.pop("capture_ask", None)
            await update.message.reply_text("No active capture job. /capture")
            return
        seats, err = capture.parse_seat_reply(text, int(job["qty_expected"] or 1))
        if err and not seats:
            await update.message.reply_text(err)
            return
        if err:
            await update.message.reply_text(err)
        db.save_capture_seats(job_id, seats)
        await update.message.reply_text(
            capture.format_job_card(job, seats) + "\n\nTap Confirm when correct.",
            reply_markup=_capture_keyboard(job_id, True),
        )
        return
    if context.user_data.get("list_ask") == "email" and _can_list(uid):
        await _list_email_step(update, context, text)
        return
    if context.user_data.get("list_ask") == "phrase" and _can_list(uid):
        await _list_phrase_step(update, context, text)
        return
    step = context.user_data.get("add_step")
    if step == "email":
        await _add_email_step(update, context, text)
        return
    if step == "phrase":
        await _add_phrase_step(update, context, text)
        return
    pending = context.user_data.get("await_event")
    if pending:
        await _finish_use(update, context, int(pending), text)
        return
    role = _role(uid)
    if role == "work1":
        await update.message.reply_text("Use /add. It asks for the email, then the recovery phrase.")
        return
    if role == "work3":
        await update.message.reply_text("Use /capture for the next login job.")
        return
    if role is None:
        await update.message.reply_text(_help(None))


async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    uid = _touch(update)
    if uid is None or not _can_add(uid):
        await update.message.reply_text("Only account makers can add.")
        return
    context.user_data.pop("await_event", None)
    context.user_data["add_step"] = "email"
    context.user_data.pop("add_email", None)
    context.user_data.pop("add_api_phrase", None)
    await update.message.reply_text("Send the worm.rip email.\n/cancel to stop.")


async def _add_email_step(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    if not update.message:
        return
    parsed = worm.parse_account_line(text.splitlines()[0])
    if not parsed or parsed[1]:
        await update.message.reply_text("Send only the email. The phrase is next.\n/cancel to stop.")
        return
    email_addr = parsed[0]
    try:
        info = await asyncio.to_thread(worm.get_inbox, email_addr)
    except worm.WormError as exc:
        if exc.status == 404:
            await update.message.reply_text(
                f"{email_addr} is not on worm.rip yet.\nGenerate it in the gen bot, then send the email again."
            )
        else:
            await update.message.reply_text(f"Lookup failed: {exc}")
        return
    existing = db.get_account_by_email(email_addr)
    if existing:
        await update.message.reply_text(f"{email_addr} is already #{existing['id']}. Send a different email.")
        return
    context.user_data["add_email"] = email_addr
    context.user_data["add_api_phrase"] = str((info or {}).get("recovery_phrase") or "").strip()
    context.user_data["add_step"] = "phrase"
    await update.message.reply_text(f"Send the recovery phrase for {email_addr}.\n/cancel to stop.")


async def _add_phrase_step(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    if not update.message or not update.effective_user:
        return
    phrase = " ".join(text.split())
    if len(phrase.split()) < 2:
        await update.message.reply_text("Send the full recovery phrase.\n/cancel to stop.")
        return
    email_addr = str(context.user_data.get("add_email") or "")
    api_phrase = str(context.user_data.get("add_api_phrase") or "")
    if api_phrase and _norm_phrase(phrase) != _norm_phrase(api_phrase):
        await update.message.reply_text("That phrase does not match this inbox. Send the recovery phrase from the gen bot.")
        return
    stored = api_phrase or phrase
    uid = update.effective_user.id
    row = db.add_account(email_addr, stored, uid)
    context.user_data.pop("add_step", None)
    context.user_data.pop("add_email", None)
    context.user_data.pop("add_api_phrase", None)
    if row is None:
        await update.message.reply_text(f"{email_addr} is already saved.")
        return
    name = " ".join(p for p in (update.effective_user.first_name, update.effective_user.last_name) if p).strip()
    await update.message.reply_text(
        f"Saved #{row['id']}\n{_cred(row)}\n{_counts_line()}\nMonitoring started."
    )
    await _notify_admins(
        context.bot,
        f"ACCOUNT SAVED #{row['id']}\n{_cred(row)}\nby: {uid} {name}\n{_counts_line()}\nMonitoring started.",
    )
    async with _POLL_LOCK:
        sent = await _forward_unseen(context.application, row, limit=25)
    listers = db.list_workers("work2")
    ping = (
        f"New account #{row['id']}\n{_cred(row)}\n\n{_counts_line()}\n"
        f"It is in the monitoring database.\n/use {row['id']} <event> after you list."
    )
    notified = 0
    for worker in listers:
        if await _send(context.bot, int(worker["telegram_id"]), ping):
            notified += 1
    await update.message.reply_text(f"Listers notified: {notified}/{len(listers)}")
    if sent:
        await update.message.reply_text(f"Sent {sent} new email(s) since the last sync.")


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    uid = _touch(update)
    if uid is None or _role(uid) is None:
        await update.message.reply_text("You are not assigned.")
        return
    counts = db.listing_counts()
    cc = db.capture_counts()
    await update.message.reply_text(
        _counts_line()
        + f"\nListings pending {counts['pending_events']} event(s), {counts['pending']} seat(s) · listed {counts['listed']}"
        + f"\nCapture queue pending {cc['pending']} · assigned {cc['assigned']} · confirmed {cc['confirmed']} · failed {cc['failed']}"
    )


async def info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    uid = _touch(update)
    if uid is None or _role(uid) is None:
        await update.message.reply_text("You are not assigned.")
        return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /info <id>")
        return
    row = db.get_account(int(context.args[0]))
    if not row or not _can_see_account(uid, row):
        await update.message.reply_text("No account with that id.")
        return
    await update.message.reply_text(_fmt_account(row))


async def find_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    uid = _touch(update)
    if uid is None or _role(uid) is None:
        await update.message.reply_text("You are not assigned.")
        return
    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text("Usage: /find <email or id>")
        return
    rows = [r for r in db.find_accounts(query) if _can_see_account(uid, r)]
    if not rows:
        await update.message.reply_text("No match.")
        return
    body = "\n\n".join(_fmt_account(r) for r in rows[:10])
    extra = f"\n\nShowing 10 of {len(rows)}." if len(rows) > 10 else ""
    await _send(context.bot, uid, body + extra)


async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    if not _admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /reset <id>")
        return
    account_id = int(context.args[0])
    if db.reset_account(account_id) != "ok":
        await update.message.reply_text(f"No account #{account_id}.")
        return
    row = db.get_account(account_id)
    await update.message.reply_text(f"#{account_id} is free again.\n{_counts_line()}")
    if row:
        await _notify_admins(context.bot, f"RESET #{account_id}\n{_cred(row)}\n{_counts_line()}")


async def setphrase_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not _private(update):
        return
    if not _admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setphrase <id> <phrase>")
        return
    account_id = int(context.args[0])
    phrase = " ".join(context.args[1:]).strip()
    if not db.set_phrase(account_id, phrase):
        await update.message.reply_text(f"No account #{account_id}.")
        return
    row = db.get_account(account_id)
    await update.message.reply_text(f"Phrase updated.\n{_fmt_account(row)}" if row else "Phrase updated.")


async def _forward_unseen(app: Application, row: dict, limit: int = 25) -> int:
    seen = await asyncio.to_thread(db.seen_ids, int(row["id"]))
    result = await asyncio.wait_for(
        asyncio.to_thread(
            worm.fetch_new,
            row["email"],
            synced_at=int(row.get("synced_at") or 0),
            seen=seen,
            limit=limit,
        ),
        timeout=60,
    )
    if not result["ok"]:
        db.note_login_error(row["id"], result["error"] or "worm check failed")
        if db.claim_login_alert(row["id"], result["error"] or "worm check failed"):
            await _notify_admins(
                app.bot,
                f"Worm check failed #{row['id']}\n{_cred(row)}\n{result['error']}",
            )
        return 0
    if db.clear_login_alert(row["id"]) and int(row.get("synced_at") or 0):
        await _notify_admins(app.bot, f"Worm inbox ok again #{row['id']} {row['email']}")
    messages = result["messages"]
    if not messages:
        db.mark_sync(int(row["id"]), result.get("mark_ids") or [], int(result["cursor"]))
        return 0
    sent_ids: list[str] = []
    for msg in messages:
        if not await _notify_admins(app.bot, _mail_text(row, msg)):
            log.warning("admin notify failed for #%s msg %s", row["id"], msg["id"])
            break
        sent_ids.append(str(msg["id"]))
        await asyncio.sleep(0.35)
    if len(sent_ids) == len(messages):
        db.mark_sync(int(row["id"]), sent_ids, int(result["cursor"]))
    else:
        db.mark_sync(int(row["id"]), sent_ids, int(row.get("synced_at") or 0))
    fresh = db.get_account(int(row["id"]))
    if fresh:
        row.update(fresh)
    return len(sent_ids)


async def _poll_account(app: Application, row: dict) -> None:
    await _forward_unseen(app, row, limit=40)


async def _mail_loop(app: Application) -> None:
    await asyncio.sleep(8)
    while True:
        started = time.monotonic()
        try:
            async with _POLL_LOCK:
                rows = db.list_accounts()
                log.info("mail poll %s mailbox(es)", len(rows))
                for row in rows:
                    try:
                        await _poll_account(app, row)
                    except Exception as exc:
                        log.warning("poll #%s %s: %s", row.get("id"), row.get("email"), exc)
                        err = str(exc)[:500]
                        db.note_login_error(int(row["id"]), err)
                        if db.claim_login_alert(int(row["id"]), err):
                            await _notify_admins(
                                app.bot,
                                f"Worm check failed #{row['id']}\n{_cred(row)}\n{err}",
                            )
        except Exception:
            log.exception("mail loop")
        delay = POLL_SECONDS - (time.monotonic() - started)
        await asyncio.sleep(max(5, delay))


async def post_init(app: Application) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Help"),
            BotCommand("id", "Your telegram id"),
            BotCommand("add", "Add email then phrase"),
            BotCommand("accs", "Account database"),
            BotCommand("stats", "Free, used, left"),
            BotCommand("free", "Unused accounts"),
            BotCommand("used", "Used accounts"),
            BotCommand("info", "One account"),
            BotCommand("find", "Find by email or id"),
            BotCommand("use", "Mark account used"),
            BotCommand("mine", "Accounts you added"),
            BotCommand("next", "Next seat to list"),
            BotCommand("mobile", "Mobile ticket file"),
            BotCommand("import", "Import listing block"),
            BotCommand("importqueue", "Import ticket_stock for work3"),
            BotCommand("queue", "Pipeline stats"),
            BotCommand("capture", "Work3: next login job"),
            BotCommand("export", "Admin DB export"),
            BotCommand("cancel", "Cancel the current prompt"),
        ]
    )
    app.bot_data["mail_task"] = asyncio.create_task(_mail_loop(app))
    log.info("mail poll every %ss, admins=%s", POLL_SECONDS, sorted(ADMIN_IDS))


async def post_shutdown(app: Application) -> None:
    task = app.bot_data.get("mail_task")
    if task:
        task.cancel()


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("Set SH_BOT_TOKEN or stubhub_bot.config.json bot_token")
    db.init_db()
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(False)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", start_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("role", role_cmd))
    app.add_handler(CommandHandler("workers", workers_cmd))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("accs", accs_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("free", free_cmd))
    app.add_handler(CommandHandler("used", used_cmd))
    app.add_handler(CommandHandler("info", info_cmd))
    app.add_handler(CommandHandler("find", find_cmd))
    app.add_handler(CommandHandler("mine", mine_cmd))
    app.add_handler(CommandHandler("use", use_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CommandHandler("setphrase", setphrase_cmd))
    app.add_handler(CommandHandler("del", del_cmd))
    app.add_handler(CommandHandler("import", import_cmd))
    app.add_handler(CommandHandler("importqueue", importqueue_cmd))
    app.add_handler(CommandHandler("queue", queue_cmd))
    app.add_handler(CommandHandler("requeue", requeue_cmd))
    app.add_handler(CommandHandler("capture", capture_cmd))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CommandHandler("clearlistings", clearlistings_cmd))
    app.add_handler(CommandHandler("done", done_cmd))
    app.add_handler(CommandHandler("next", next_cmd))
    app.add_handler(CommandHandler("mobile", mobile_cmd))
    app.add_handler(CallbackQueryHandler(on_page, pattern=r"^pg:"))
    app.add_handler(CallbackQueryHandler(on_use_button, pattern=r"^use:"))
    app.add_handler(CallbackQueryHandler(on_listing_button, pattern=r"^ls:"))
    app.add_handler(CallbackQueryHandler(on_capture_button, pattern=r"^cap:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(filters.Document.ALL, on_import_file))
    log.info("StubHub bot starting")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
