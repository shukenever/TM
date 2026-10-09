"""Telegram conversation: worker listing flow on Victory Live."""
from __future__ import annotations

import asyncio
import html
import logging
import time
from datetime import date, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from vl_inventory_db import (
    clear_rm_pending,
    credit_listing_payout,
    enqueue_rm_pending,
    get_stockfrom_session,
    record_listing,
)
from vl_listing_api import (
    ListingTicket,
    ManualProduction,
    create_mapped_listing,
    filter_productions_by_date,
    lookup_rm_group_once,
    nudge_rm_sync,
    open_listing_session,
    parse_user_event_date,
    production_event_date,
    publish_rm_group,
    search_manual_productions,
    sort_productions,
)
from vl_inventory_sync import load_session, validate_session

log = logging.getLogger("vl_inventory_bot")
_RM_TASKS: set[asyncio.Task] = set()
_LISTING_USER_LOCKS: dict[int, asyncio.Lock] = {}


def _listing_user_lock(user_id: int) -> asyncio.Lock:
    lock = _LISTING_USER_LOCKS.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _LISTING_USER_LOCKS[user_id] = lock
    return lock

(
    S_NAME,
    S_PICK,
    S_PICK_DATE,
    S_SECTION,
    S_ROW,
    S_QTY,
    S_SEAT,
    S_LIST,
    S_COST,
    S_FACE,
    S_CONFIRM,
) = range(11)

_AWAIT_BY_STATE = {
    S_NAME: "name",
    S_PICK: "pick",
    S_PICK_DATE: "pick_date",
    S_SECTION: "section",
    S_ROW: "row",
    S_QTY: "qty",
    S_SEAT: "seat",
    S_LIST: "list",
    S_COST: "cost",
    S_FACE: "face",
    S_CONFIRM: "confirm",
}

PAGE_SIZE = 6
CB_PICK = "vl_lp"
CB_PAGE = "vl_lpg"
CB_SORT = "vl_lso"
CB_CHOOSE_DATE = "vl_ldt"
CB_CLEAR_DATE = "vl_ldc"
CB_CONFIRM = "vl_lcf"
CB_CANCEL = "vl_lx"


RM_WAIT_SEC = 600
RM_POLL_SEC = 15
RM_NUDGE_SEC = 90
RM_RECOVERY_SEC = 240

_SUPERVISED_LISTER_TELEGRAM_ID = 8239115988
_SUPERVISED_LISTER_MIN_EVENT_DATE = date(2026, 11, 19)
_SUPERVISED_LISTER_WARNING = (
    "🚨 You are heavily supervised madarchod ka bacha, "
    "Do not try to list for before november 19"
)


def _supervised_lister_min_event_date(user_id: int | None) -> date | None:
    if user_id == _SUPERVISED_LISTER_TELEGRAM_ID:
        return _SUPERVISED_LISTER_MIN_EVENT_DATE
    return None


def _production_allowed_for_lister(user_id: int | None, prod: ManualProduction) -> bool:
    min_day = _supervised_lister_min_event_date(user_id)
    if min_day is None:
        return True
    return production_event_date(prod) >= min_day


async def _send_supervised_lister_warning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = None
    if update.message:
        chat_id = update.message.chat_id
    elif update.callback_query and update.callback_query.message:
        chat_id = update.callback_query.message.chat_id
    elif update.effective_chat:
        chat_id = update.effective_chat.id
    if chat_id is None:
        return
    await context.bot.send_message(chat_id=chat_id, text=_SUPERVISED_LISTER_WARNING)


def _apply_supervised_hit_filter(store: dict, hits: list[ManualProduction]) -> list[ManualProduction]:
    cutoff_s = store.get("supervised_cutoff")
    if not cutoff_s:
        return hits
    min_day = date.fromisoformat(str(cutoff_s))
    return [h for h in hits if production_event_date(h) >= min_day]


def _seat_span(ticket: ListingTicket) -> str:
    end = ticket.start_seat + ticket.quantity - 1
    if end == ticket.start_seat:
        return str(ticket.start_seat)
    return f"{ticket.start_seat}-{end}"


def _listing_block(prod: ManualProduction, ticket: ListingTicket, po_id: int) -> str:
    return (
        f"{html.escape(prod.label())}\n"
        f"Sec {html.escape(ticket.section)} / Row {html.escape(ticket.row)} "
        f"seats {html.escape(_seat_span(ticket))} · qty {ticket.quantity}\n"
        f"List ${ticket.list_price:.2f} · Cost ${ticket.cost_price:.2f} · Face ${ticket.face_value:.2f}\n"
        f"PO <b>AP-{po_id}</b> · In-hand {ticket.in_hand_date.isoformat()}"
    )


def build_listing_conversation(
    *,
    can_use,
    use_proxy: bool,
    client_po_profile_id: int,
    profile_name: str,
    affiliate_group_id: int,
    admin_ids: set[int],
    listing_payout_usd: float,
) -> tuple[ConversationHandler, MessageHandler, CallbackQueryHandler, object]:
    def _sync_list_await(context: ContextTypes.DEFAULT_TYPE, state: int) -> None:
        if state == ConversationHandler.END:
            context.user_data.pop("vl_list_await", None)
        elif state in _AWAIT_BY_STATE:
            context.user_data["vl_list_await"] = _AWAIT_BY_STATE[state]

    async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        context.user_data.pop("vl_list", None)
        context.user_data.pop("vl_list_await", None)
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("Listing cancelled.")
        elif update.message:
            await update.message.reply_text("Listing cancelled.")
        return ConversationHandler.END

    async def start_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not update.effective_user or not can_use(update.effective_user.id):
            if update.message:
                await update.message.reply_text("Unauthorized.")
            return ConversationHandler.END
        uid = update.effective_user.id
        async with _listing_user_lock(uid):
            context.user_data.pop("stockfrom_await", None)
            context.user_data.pop("stockfrom_lo", None)
            context.user_data.pop("stockfrom_pending", None)
            context.user_data["vl_list"] = {}
            context.user_data["vl_list_await"] = "name"
            min_ev = _supervised_lister_min_event_date(uid)
            if min_ev is not None:
                context.user_data["vl_list"]["supervised_cutoff"] = min_ev.isoformat()
            args = [str(a).strip() for a in (context.args or []) if str(a).strip()]
            if args:
                result = await on_name(update, context)
                _sync_list_await(context, result)
                return ConversationHandler.END
        await update.message.reply_text(
            "Victory Live listing — step 1/9\n"
            "Type the event name to search (e.g. <code>harry styles</code>)\n"
            "Or: <code>/list amanda marshall</code>",
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    def _store(context: ContextTypes.DEFAULT_TYPE) -> dict:
        return context.user_data.setdefault("vl_list", {})

    def _rebuild_hits(store: dict) -> list[ManualProduction]:
        all_hits = [ManualProduction(**r) for r in store.get("hits_all") or []]
        day_s = store.get("date_filter")
        if day_s:
            day = date.fromisoformat(day_s)
            view = filter_productions_by_date(all_hits, day)
        else:
            view = list(all_hits)
        view = _apply_supervised_hit_filter(store, view)
        asc = store.get("sort_asc", True)
        return sort_productions(view, ascending=asc)

    def _sync_hits(store: dict) -> list[ManualProduction]:
        hits = _rebuild_hits(store)
        store["hits"] = [h.__dict__ for h in hits]
        return hits

    def _pick_header(store: dict, hits: list[ManualProduction]) -> str:
        total = len(store.get("hits_all") or [])
        q = html.escape(str(store.get("query") or ""))
        asc = store.get("sort_asc", True)
        order = "oldest → newest" if asc else "newest → oldest"
        lines = [f"Found <b>{total}</b> for <b>{q}</b>"]
        if store.get("date_filter"):
            lines.append(f"Date filter: <b>{html.escape(store['date_filter'])}</b> — <b>{len(hits)}</b> show(s)")
        else:
            lines.append(f"Showing all — sorted {order}")
        lines.append("Pick an event (or Choose date / toggle sort):")
        page = int(store.get("page") or 0)
        start = page * PAGE_SIZE
        chunk = hits[start : start + PAGE_SIZE]
        if chunk:
            lines.append("")
            for h in chunk:
                lines.append(html.escape(h.label()))
        return "\n".join(lines)

    def _pick_keyboard(store: dict) -> InlineKeyboardMarkup:
        hits = [ManualProduction(**r) for r in store.get("hits") or []]
        page = int(store.get("page") or 0)
        start = page * PAGE_SIZE
        chunk = hits[start : start + PAGE_SIZE]
        rows = []
        for i, h in enumerate(chunk):
            idx = start + i
            rows.append(
                [InlineKeyboardButton(h.button_label(), callback_data=f"{CB_PICK}:{idx}")]
            )
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("« Prev", callback_data=f"{CB_PAGE}:{page - 1}"))
        if start + PAGE_SIZE < len(hits):
            nav.append(InlineKeyboardButton("Next »", callback_data=f"{CB_PAGE}:{page + 1}"))
        if nav:
            rows.append(nav)
        asc = store.get("sort_asc", True)
        sort_btn = "Sort: newest first" if asc else "Sort: oldest first"
        rows.append(
            [
                InlineKeyboardButton(sort_btn, callback_data=f"{CB_SORT}:toggle"),
                InlineKeyboardButton("Choose date", callback_data=CB_CHOOSE_DATE),
            ]
        )
        if store.get("date_filter"):
            rows.append([InlineKeyboardButton("Clear date filter", callback_data=CB_CLEAR_DATE)])
        rows.append([InlineKeyboardButton("Cancel", callback_data=CB_CANCEL)])
        return InlineKeyboardMarkup(rows)

    async def _show_pick_screen(message_or_query, store: dict, *, edit: bool) -> None:
        hits = _sync_hits(store)
        text = _pick_header(store, hits)
        kb = _pick_keyboard(store)
        if not hits:
            text += "\n\nNo events on that date — try another date or clear filter."
        if edit and hasattr(message_or_query, "edit_message_text"):
            await message_or_query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        elif edit:
            await message_or_query.edit_message_reply_markup(reply_markup=kb)
        else:
            await message_or_query.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

    async def on_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not update.message or not update.effective_user or not can_use(update.effective_user.id):
            return ConversationHandler.END
        q = (update.message.text or "").strip()
        if len(q) < 2:
            await update.message.reply_text("Need at least 2 characters. Try again or /cancel.")
            return S_NAME
        msg = await update.message.reply_text("Searching Victory Live…")
        try:
            s = await asyncio.to_thread(load_session, use_proxy)
            from vl_auth import enable_session_http_logging, probe_egress_public_ip, proxy_status_for_log

            egress_ip = await asyncio.to_thread(probe_egress_public_ip)
            log.info(
                "/list egress probe %s public_ip=%s (new CONNECT on 96 proxy; VL search may reuse tunnel #1)",
                proxy_status_for_log(),
                egress_ip,
            )
            await asyncio.to_thread(enable_session_http_logging, s)
            await asyncio.to_thread(validate_session, s)
            hits = await asyncio.to_thread(search_manual_productions, s, q)
            log.info("/list searchProductions done hits=%d query=%r", len(hits), q)
        except Exception as exc:
            await msg.edit_text(f"Search failed: {html.escape(str(exc))}", parse_mode=ParseMode.HTML)
            return S_NAME
        if not hits:
            await msg.edit_text("No events found. Try another name or /cancel.")
            return S_NAME
        store = _store(context)
        uid = update.effective_user.id
        min_ev = _supervised_lister_min_event_date(uid)
        if min_ev is not None:
            store["supervised_cutoff"] = min_ev.isoformat()
        else:
            store.pop("supervised_cutoff", None)
        store["hits_all"] = [h.__dict__ for h in hits]
        store["query"] = q
        store["page"] = 0
        store["sort_asc"] = True
        store.pop("date_filter", None)
        view = _sync_hits(store)
        if min_ev is not None and not view:
            await msg.edit_text(
                "No events on or after 2026-11-19 for that search. Try another name or /cancel."
            )
            return S_NAME
        await msg.edit_text(
            _pick_header(store, view),
            reply_markup=_pick_keyboard(store),
            parse_mode=ParseMode.HTML,
        )
        return S_PICK

    def _hits(context: ContextTypes.DEFAULT_TYPE) -> list[ManualProduction]:
        raw = context.user_data.get("vl_list", {}).get("hits") or []
        return [ManualProduction(**r) for r in raw]

    async def on_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        q = update.callback_query
        await q.answer()
        store = _store(context)
        page = int(q.data.split(":")[1])
        store["page"] = max(0, page)
        hits = [ManualProduction(**r) for r in store.get("hits") or []]
        await q.edit_message_text(
            _pick_header(store, hits),
            reply_markup=_pick_keyboard(store),
            parse_mode=ParseMode.HTML,
        )
        return S_PICK

    async def on_sort(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        q = update.callback_query
        await q.answer()
        store = _store(context)
        store["sort_asc"] = not store.get("sort_asc", True)
        store["page"] = 0
        hits = _sync_hits(store)
        await q.edit_message_text(
            _pick_header(store, hits),
            reply_markup=_pick_keyboard(store),
            parse_mode=ParseMode.HTML,
        )
        return S_PICK

    async def on_choose_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        q = update.callback_query
        await q.answer()
        await q.edit_message_text(
            "Send the <b>event date</b> to filter results.\n\n"
            "Examples:\n"
            "• <code>21 01 2027</code> (day month year)\n"
            "• <code>01/21/2027</code> (US)\n"
            "• <code>2027-01-21</code>\n\n"
            "/cancel to abort",
            parse_mode=ParseMode.HTML,
        )
        _sync_list_await(context, S_PICK_DATE)
        return S_PICK_DATE

    async def on_clear_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        q = update.callback_query
        await q.answer()
        store = _store(context)
        store.pop("date_filter", None)
        store["page"] = 0
        hits = _sync_hits(store)
        await q.edit_message_text(
            _pick_header(store, hits),
            reply_markup=_pick_keyboard(store),
            parse_mode=ParseMode.HTML,
        )
        _sync_list_await(context, S_PICK)
        return S_PICK

    async def on_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not update.message:
            return S_PICK_DATE
        text = (update.message.text or "").strip()
        try:
            day = parse_user_event_date(text)
        except ValueError:
            await update.message.reply_text(
                "Invalid date. Try <code>21 01 2027</code> or <code>01/21/2027</code>",
                parse_mode=ParseMode.HTML,
            )
            return S_PICK_DATE
        uid = update.effective_user.id if update.effective_user else None
        min_ev = _supervised_lister_min_event_date(uid)
        if min_ev is not None and day < min_ev:
            await _send_supervised_lister_warning(update, context)
            return S_PICK_DATE
        store = _store(context)
        store["date_filter"] = day.isoformat()
        store["page"] = 0
        hits = _sync_hits(store)
        await update.message.reply_text(
            _pick_header(store, hits),
            reply_markup=_pick_keyboard(store),
            parse_mode=ParseMode.HTML,
        )
        return S_PICK

    async def on_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        q = update.callback_query
        await q.answer()
        idx = int(q.data.split(":")[1])
        hits = _hits(context)
        if idx < 0 or idx >= len(hits):
            await q.edit_message_text("Stale selection — /list again.")
            return ConversationHandler.END
        prod = hits[idx]
        uid = q.from_user.id if q.from_user else None
        if not _production_allowed_for_lister(uid, prod):
            await _send_supervised_lister_warning(update, context)
            await q.edit_message_text(
                "That event is not allowed for your account. Pick another or /list again.",
            )
            _sync_list_await(context, S_PICK)
            return S_PICK
        store = _store(context)
        store["prod"] = prod.__dict__
        await q.edit_message_text(
            f"Selected:\n<b>{html.escape(prod.label())}</b>\n\n"
            "Step 2/9 — send <b>section</b> (e.g. 111):",
            parse_mode=ParseMode.HTML,
        )
        _sync_list_await(context, S_SECTION)
        return S_SECTION

    async def on_section(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not update.message:
            return S_SECTION
        store = _store(context)
        if not store.get("prod"):
            await update.message.reply_text("Pick an event from the buttons above first.")
            return S_PICK
        sec = (update.message.text or "").strip()
        if not sec:
            await update.message.reply_text("Section required.")
            return S_SECTION
        store["section"] = sec
        await update.message.reply_text("Step 3/9 — send <b>row</b>:", parse_mode=ParseMode.HTML)
        return S_ROW

    async def on_row(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not update.message:
            return S_ROW
        row = (update.message.text or "").strip()
        if not row:
            await update.message.reply_text("Row required.")
            return S_ROW
        _store(context)["row"] = row
        await update.message.reply_text(
            "Step 4/9 — send <b>quantity</b> (how many tickets):",
            parse_mode=ParseMode.HTML,
        )
        return S_QTY

    async def on_qty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not update.message:
            return S_QTY
        text = (update.message.text or "").strip()
        try:
            qty = int(text)
        except ValueError:
            await update.message.reply_text("Send quantity as one number, e.g. <code>2</code>.", parse_mode=ParseMode.HTML)
            return S_QTY
        if qty < 1:
            await update.message.reply_text("Quantity must be at least 1.")
            return S_QTY
        _store(context)["quantity"] = qty
        await update.message.reply_text(
            "Step 5/9 — send <b>first seat</b> (e.g. <code>1</code>):",
            parse_mode=ParseMode.HTML,
        )
        return S_SEAT

    async def on_seat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not update.message:
            return S_SEAT
        text = (update.message.text or "").strip()
        try:
            start_seat = int(text)
        except ValueError:
            await update.message.reply_text("Send the first seat as one number, e.g. <code>1</code>.", parse_mode=ParseMode.HTML)
            return S_SEAT
        if start_seat < 0:
            await update.message.reply_text("Seat must be 0 or higher.")
            return S_SEAT
        _store(context)["start_seat"] = start_seat
        await update.message.reply_text(
            "Step 6/9 — send <b>list price</b> (e.g. <code>345</code>):",
            parse_mode=ParseMode.HTML,
        )
        return S_LIST

    def _parse_money(text: str) -> float:
        return float((text or "").strip().replace(",", "").replace("$", ""))

    async def on_list_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not update.message:
            return S_LIST
        try:
            list_p = _parse_money(update.message.text or "")
        except ValueError:
            await update.message.reply_text("Send list price as one number, e.g. <code>345</code>.", parse_mode=ParseMode.HTML)
            return S_LIST
        if list_p < 0:
            await update.message.reply_text("List price must be 0 or higher.")
            return S_LIST
        _store(context)["list_price"] = list_p
        await update.message.reply_text(
            "Step 7/9 — send <b>cost</b> (e.g. <code>125</code>):",
            parse_mode=ParseMode.HTML,
        )
        return S_COST

    async def on_cost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not update.message:
            return S_COST
        try:
            cost_p = _parse_money(update.message.text or "")
        except ValueError:
            await update.message.reply_text("Send cost as one number, e.g. <code>125</code>.", parse_mode=ParseMode.HTML)
            return S_COST
        if cost_p < 0:
            await update.message.reply_text("Cost must be 0 or higher.")
            return S_COST
        _store(context)["cost_price"] = cost_p
        await update.message.reply_text(
            "Step 8/9 — send <b>face</b> (e.g. <code>125</code>):",
            parse_mode=ParseMode.HTML,
        )
        return S_FACE

    async def on_face(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not update.message:
            return S_FACE
        try:
            face = _parse_money(update.message.text or "")
        except ValueError:
            await update.message.reply_text("Send face as one number, e.g. <code>125</code>.", parse_mode=ParseMode.HTML)
            return S_FACE
        if face < 0:
            await update.message.reply_text("Face must be 0 or higher.")
            return S_FACE
        store = _store(context)
        list_p = float(store["list_price"])
        cost_p = float(store["cost_price"])
        store["face_value"] = face
        prod = ManualProduction(**store["prod"])
        uid = update.effective_user.id if update.effective_user else None
        if not _production_allowed_for_lister(uid, prod):
            await _send_supervised_lister_warning(update, context)
            await update.message.reply_text(
                "That event is not allowed for your account. /list again and pick another event.",
            )
            return ConversationHandler.END
        store["in_hand_date"] = (production_event_date(prod) - timedelta(days=2)).isoformat()
        summary = (
            f"<b>Confirm listing</b>\n"
            f"{html.escape(prod.label())}\n"
            f"Sec {html.escape(store['section'])} / Row {html.escape(store['row'])} "
            f"seat {store['start_seat']} qty {store['quantity']}\n"
            f"List ${list_p:.2f} · Cost ${cost_p:.2f} · Face ${face:.2f}\n"
            f"In-hand (IHD): <b>2 days before event</b> ({store['in_hand_date']})\n"
            f"Profile: consign → MAP → share to default marketplaces"
        )
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Submit", callback_data=f"{CB_CONFIRM}:yes"),
                    InlineKeyboardButton("Cancel", callback_data=CB_CANCEL),
                ]
            ]
        )
        await update.message.reply_text(summary, reply_markup=kb, parse_mode=ParseMode.HTML)
        return S_CONFIRM

    async def on_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        q = update.callback_query
        await q.answer()
        if not q.data.endswith(":yes"):
            await q.edit_message_text("Cancelled.")
            return ConversationHandler.END
        store = context.user_data.get("vl_list") or {}
        try:
            prod = ManualProduction(**store["prod"])
        except (KeyError, TypeError, ValueError):
            await q.edit_message_text("Session expired — /list again.")
            return ConversationHandler.END
        uid = q.from_user.id if q.from_user else None
        if not _production_allowed_for_lister(uid, prod):
            await _send_supervised_lister_warning(update, context)
            await q.edit_message_text(
                "Listing blocked for that event date. Pick another event or /list again.",
            )
            return ConversationHandler.END
        try:
            ticket = ListingTicket(
                section=str(store["section"]),
                row=str(store["row"]),
                start_seat=int(store["start_seat"]),
                quantity=int(store["quantity"]),
                list_price=float(store["list_price"]),
                cost_price=float(store["cost_price"]),
                face_value=float(store["face_value"]),
                in_hand_date=date.fromisoformat(store["in_hand_date"]),
            )
        except (KeyError, TypeError, ValueError):
            await q.edit_message_text("Session expired — /list again.")
            return ConversationHandler.END

        log.info(
            "listing submit section=%s row=%s seat=%s qty=%s list=%s cost=%s face=%s ihd=%s event=%s",
            ticket.section,
            ticket.row,
            ticket.start_seat,
            ticket.quantity,
            ticket.list_price,
            ticket.cost_price,
            ticket.face_value,
            ticket.in_hand_date.isoformat(),
            prod.label(),
        )
        await q.edit_message_text("Submitting to Victory Live…")
        try:
            created = await asyncio.to_thread(
                create_mapped_listing,
                prod,
                ticket,
                client_po_profile_id=client_po_profile_id,
                profile_name=profile_name,
                use_proxy=use_proxy,
            )
        except Exception as exc:
            log.exception("listing submit failed")
            await q.edit_message_text(
                f"Listing failed:\n{html.escape(str(exc))}",
                parse_mode=ParseMode.HTML,
            )
            context.user_data.pop("vl_list", None)
            return ConversationHandler.END

        po_id = int(created["primary_purchase_order_id"])
        tg_uid = q.from_user.id if q.from_user else 0
        log.info(
            "listing created po=%s user=%s event=%s",
            po_id,
            tg_uid,
            prod.label(),
        )
        if tg_uid:
            record_listing(
                po_id=po_id,
                telegram_id=tg_uid,
                list_price=ticket.list_price,
                quantity=ticket.quantity,
                cost_price=ticket.cost_price,
                section=ticket.section,
                row_name=ticket.row,
                event_label=prod.label(),
                prod=store.get("prod") or prod.__dict__,
                ticket={
                    "section": ticket.section,
                    "row": ticket.row,
                    "start_seat": ticket.start_seat,
                    "quantity": ticket.quantity,
                    "list_price": ticket.list_price,
                    "cost_price": ticket.cost_price,
                    "face_value": ticket.face_value,
                    "in_hand_date": ticket.in_hand_date.isoformat(),
                },
            )
        await q.edit_message_text(
            f"<b>Listing successful</b>\n"
            f"{_listing_block(prod, ticket, po_id)}\n\n"
            f"Checking Revenue Manager every {RM_POLL_SEC} seconds for up to "
            f"{RM_WAIT_SEC // 60} minutes.\n"
            f"You can /list another one now.",
            parse_mode=ParseMode.HTML,
        )
        user = update.effective_user
        chat_id = q.message.chat_id if q.message else (user.id if user else 0)
        user_id = user.id if user else 0
        username = (user.username or "") if user else ""
        context.user_data.pop("vl_list", None)
        task = asyncio.create_task(
            _watch_rm(
                context.bot,
                chat_id,
                user_id,
                username,
                prod,
                ticket,
                po_id,
            ),
            name=f"vl-rm-{po_id}",
        )
        _RM_TASKS.add(task)
        task.add_done_callback(_RM_TASKS.discard)
        return ConversationHandler.END

    async def _watch_rm(bot, chat_id: int, user_id: int, username: str, prod, ticket, po_id: int) -> None:
        block = _listing_block(prod, ticket, po_id)
        who = f"<code>{user_id}</code>"
        if username:
            who += f" @{html.escape(username)}"

        def _queue_pending(reason: str) -> None:
            enqueue_rm_pending(
                po_id=po_id,
                telegram_id=user_id,
                chat_id=chat_id,
                username=username or "",
                prod=prod.__dict__,
                ticket={
                    "section": ticket.section,
                    "row": ticket.row,
                    "start_seat": ticket.start_seat,
                    "quantity": ticket.quantity,
                    "list_price": ticket.list_price,
                    "cost_price": ticket.cost_price,
                    "face_value": ticket.face_value,
                    "in_hand_date": ticket.in_hand_date.isoformat(),
                },
                reason=reason,
            )

        async def _publish_and_notify(session, rm_group: dict) -> None:
            published = await asyncio.to_thread(
                publish_rm_group,
                session,
                prod,
                ticket,
                rm_group,
                affiliate_group_id=affiliate_group_id,
            )
            credit = await asyncio.to_thread(
                credit_listing_payout,
                user_id,
                po_id,
                listing_payout_usd,
            )
            markets = ", ".join(html.escape(m) for m in (published.get("marketplaces") or [])) or "shared"
            pay = ""
            if credit.get("credited"):
                pay = (
                    f"\n+${float(credit['amount_usd']):.2f} · "
                    f"balance <b>${float(credit['balance_usd']):.2f}</b>"
                )
            log.info(
                "listing live po=%s tg=%s shared=%s credited=%s",
                po_id,
                published.get("ticket_group_id"),
                published.get("is_shared"),
                credit.get("credited"),
            )
            await bot.send_message(
                chat_id,
                f"<b>Live in Revenue Manager</b>\n{block}\n"
                f"TG <code>{published.get('ticket_group_id')}</code>\n"
                f"{markets}{pay}",
                parse_mode=ParseMode.HTML,
            )
            clear_rm_pending(po_id)

        async def _poll_until(deadline: float, session, *, nudge: bool) -> tuple[dict | None, object]:
            found: dict | None = None
            last_nudge = 0.0
            while True:
                try:
                    found = await asyncio.to_thread(
                        lookup_rm_group_once,
                        session,
                        prod,
                        ticket,
                        affiliate_group_id=affiliate_group_id,
                    )
                except Exception:
                    log.exception("RM poll failed po=%s", po_id)
                    found = None
                    try:
                        session = await asyncio.to_thread(open_listing_session, use_proxy)
                    except Exception:
                        log.exception("RM session refresh failed po=%s", po_id)
                if found:
                    return found, session
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                now = time.monotonic()
                if nudge and now - last_nudge >= RM_NUDGE_SEC:
                    last_nudge = now
                    try:
                        await asyncio.to_thread(
                            nudge_rm_sync,
                            session,
                            prod,
                            ticket,
                            po_id,
                        )
                    except Exception:
                        log.exception("RM nudge failed po=%s", po_id)
                await asyncio.sleep(min(RM_POLL_SEC, remaining))
            return None, session

        group = None
        try:
            session = await asyncio.to_thread(open_listing_session, use_proxy)
            deadline = time.monotonic() + RM_WAIT_SEC
            group, session = await _poll_until(deadline, session, nudge=True)

            if not group:
                log.info("RM miss after %ss po=%s — final IHD+remap", RM_WAIT_SEC, po_id)
                try:
                    await asyncio.to_thread(nudge_rm_sync, session, prod, ticket, po_id)
                except Exception:
                    log.exception("final RM nudge failed po=%s", po_id)
                group, session = await _poll_until(
                    time.monotonic() + RM_RECOVERY_SEC,
                    session,
                    nudge=False,
                )

            if group:
                await _publish_and_notify(session, group)
                return

            log.info("RM miss after recovery po=%s", po_id)
            await bot.send_message(
                chat_id,
                f"<b>Not in Revenue Manager yet</b>\n{block}\n\n"
                f"Waited {RM_WAIT_SEC // 60} min + recovery. Admin has been alerted.\n"
                f"Balance was not added.",
                parse_mode=ParseMode.HTML,
            )
            alert = (
                f"<b>VL listing missing from Revenue Manager</b>\n"
                f"Worker: {who}\n{block}"
            )
            for admin_id in admin_ids:
                try:
                    await bot.send_message(admin_id, alert, parse_mode=ParseMode.HTML)
                except Exception:
                    log.exception("admin alert failed id=%s po=%s", admin_id, po_id)
            _queue_pending("missing")
        except Exception as exc:
            log.exception("RM watch failed po=%s", po_id)
            recovered = False
            try:
                session = await asyncio.to_thread(open_listing_session, use_proxy)
                try:
                    await asyncio.to_thread(nudge_rm_sync, session, prod, ticket, po_id)
                except Exception:
                    log.exception("RM crash nudge failed po=%s", po_id)
                group, session = await _poll_until(
                    time.monotonic() + RM_RECOVERY_SEC,
                    session,
                    nudge=True,
                )
                if group:
                    await _publish_and_notify(session, group)
                    recovered = True
            except Exception:
                log.exception("RM crash recovery failed po=%s", po_id)
            if recovered:
                return
            try:
                await bot.send_message(
                    chat_id,
                    f"<b>Revenue Manager check failed</b>\n{block}\n\n"
                    f"{html.escape(str(exc))}\nAdmin has been alerted.\n"
                    f"Balance was not added.",
                    parse_mode=ParseMode.HTML,
                )
                for admin_id in admin_ids:
                    try:
                        await bot.send_message(
                            admin_id,
                            f"<b>VL Revenue Manager check crashed</b>\n"
                            f"Worker: {who}\n{block}\n\n{html.escape(str(exc))}",
                            parse_mode=ParseMode.HTML,
                        )
                    except Exception:
                        log.exception("admin alert failed id=%s po=%s", admin_id, po_id)
                _queue_pending("crash")
            except Exception:
                log.exception("failed to report RM watch error po=%s", po_id)

    async def listing_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Text steps for /list (user_data; works with concurrent_updates)."""
        if context.user_data.get("specific_fulfill_await"):
            return
        if context.user_data.get("stockfrom_await"):
            return
        uid = update.effective_user.id if update.effective_user else 0
        if uid and get_stockfrom_session(uid):
            return
        if not update.message or not update.message.text or not update.effective_user:
            return
        if update.message.text.startswith("/"):
            return
        uid = update.effective_user.id
        if not can_use(uid):
            return
        async with _listing_user_lock(uid):
            step = context.user_data.get("vl_list_await")
            if not step:
                return
            if step in ("pick", "confirm"):
                return
            handlers = {
                "name": on_name,
                "pick_date": on_date_input,
                "section": on_section,
                "row": on_row,
                "qty": on_qty,
                "seat": on_seat,
                "list": on_list_price,
                "cost": on_cost,
                "face": on_face,
            }
            fn = handlers.get(step)
            if not fn:
                return
            log.info("vl_list text step=%s user=%s", step, uid)
            result = await fn(update, context)
            _sync_list_await(context, result)
        raise ApplicationHandlerStop()

    async def listing_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Pick-screen buttons (Next/Prev/sort/event) when conv state was not updated."""
        q = update.callback_query
        if not q or not q.data or not q.from_user:
            return
        if context.user_data.get("stockfrom_await"):
            return
        if not q.data.startswith("vl_l"):
            return
        if not can_use(q.from_user.id):
            return
        if not context.user_data.get("vl_list") and not context.user_data.get("vl_list_await"):
            return
        data = q.data
        result: int = ConversationHandler.END
        if data.startswith(f"{CB_PAGE}:"):
            result = await on_page(update, context)
        elif data.startswith(f"{CB_PICK}:"):
            result = await on_pick(update, context)
        elif data.startswith(f"{CB_SORT}:"):
            result = await on_sort(update, context)
        elif data == CB_CHOOSE_DATE:
            result = await on_choose_date(update, context)
        elif data == CB_CLEAR_DATE:
            result = await on_clear_date(update, context)
        elif data.startswith(f"{CB_CONFIRM}:"):
            result = await on_confirm(update, context)
        elif data == CB_CANCEL:
            result = await cancel(update, context)
        else:
            return
        log.info("vl_list callback data=%s user=%s", data, q.from_user.id)
        if result != ConversationHandler.END:
            _sync_list_await(context, result)
        else:
            context.user_data.pop("vl_list_await", None)
        raise ApplicationHandlerStop()

    conv = ConversationHandler(
        entry_points=[CommandHandler("list", start_list)],
        name="vl_listing",
        states={
            S_PICK: [
                CallbackQueryHandler(on_pick, pattern=f"^{CB_PICK}:"),
                CallbackQueryHandler(on_page, pattern=f"^{CB_PAGE}:"),
                CallbackQueryHandler(on_sort, pattern=f"^{CB_SORT}:"),
                CallbackQueryHandler(on_choose_date, pattern=f"^{CB_CHOOSE_DATE}$"),
                CallbackQueryHandler(on_clear_date, pattern=f"^{CB_CLEAR_DATE}$"),
                CallbackQueryHandler(cancel, pattern=f"^{CB_CANCEL}$"),
            ],
            S_CONFIRM: [
                CallbackQueryHandler(on_confirm, pattern=f"^{CB_CONFIRM}:"),
                CallbackQueryHandler(cancel, pattern=f"^{CB_CANCEL}$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
        per_user=True,
        per_chat=True,
        per_message=False,
    )
    text_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, listing_text_router, block=True)
    callback_handler = CallbackQueryHandler(listing_callback_router, pattern=r"^vl_l", block=False)
    return conv, text_handler, callback_handler, cancel
