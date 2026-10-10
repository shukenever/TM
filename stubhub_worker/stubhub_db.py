"""SQLite store for the StubHub worker bot."""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "stubhub_bot.db"
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now().isoformat(timespec="minutes")


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _LOCK:
        conn = _conn()
        try:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS workers (
                    telegram_id INTEGER PRIMARY KEY,
                    role TEXT NOT NULL,
                    username TEXT,
                    full_name TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    recovery_phrase TEXT,
                    status TEXT NOT NULL DEFAULT 'free',
                    event TEXT,
                    created_by INTEGER,
                    used_by INTEGER,
                    created_at TEXT NOT NULL,
                    used_at TEXT,
                    last_since INTEGER NOT NULL DEFAULT 0,
                    synced_at INTEGER NOT NULL DEFAULT 0,
                    primed INTEGER NOT NULL DEFAULT 0,
                    login_error TEXT,
                    login_alerted INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS mail_seen (
                    account_id INTEGER NOT NULL,
                    message_id TEXT NOT NULL,
                    PRIMARY KEY (account_id, message_id)
                );
                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_email TEXT NOT NULL,
                    event_name TEXT NOT NULL,
                    event_date TEXT,
                    venue TEXT,
                    image_url TEXT,
                    section TEXT,
                    row_name TEXT,
                    seat TEXT,
                    ticket_url TEXT,
                    barcode TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    assigned_to INTEGER,
                    listed_by INTEGER,
                    listed_account_id INTEGER,
                    created_at TEXT NOT NULL,
                    listed_at TEXT,
                    pdf_name TEXT,
                    UNIQUE(account_email, event_name, section, row_name, seat)
                );
                CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status);
                CREATE TABLE IF NOT EXISTS capture_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    password TEXT NOT NULL,
                    app_login TEXT,
                    event_name TEXT NOT NULL,
                    event_date TEXT,
                    venue TEXT,
                    qty_expected INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'pending',
                    assigned_to INTEGER,
                    confirmed_by INTEGER,
                    worker_notes TEXT,
                    fail_reason TEXT,
                    created_at TEXT NOT NULL,
                    assigned_at TEXT,
                    confirmed_at TEXT,
                    UNIQUE(email COLLATE NOCASE, event_name, event_date, venue, app_login)
                );
                CREATE TABLE IF NOT EXISTS capture_seats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    seat_slot INTEGER NOT NULL,
                    section TEXT,
                    row_name TEXT,
                    seat TEXT,
                    barcode TEXT,
                    UNIQUE(job_id, seat_slot),
                    FOREIGN KEY(job_id) REFERENCES capture_jobs(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_capture_status ON capture_jobs(status);
                """
            )
            _migrate(conn)
            _ensure_synced_at(conn)
            _ensure_listing_pdf(conn)
            _ensure_listed_account(conn)
            conn.commit()
        finally:
            conn.close()


PDF_DIR = ROOT / "data" / "listing_pdfs"


def listing_pdf_path(listing_id: int) -> Path:
    return PDF_DIR / f"{int(listing_id)}.pdf"


def _ensure_listing_pdf(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(listings)")}
    if cols and "pdf_name" not in cols:
        conn.execute("ALTER TABLE listings ADD COLUMN pdf_name TEXT")


def _ensure_listed_account(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(listings)")}
    if cols and "listed_account_id" not in cols:
        conn.execute("ALTER TABLE listings ADD COLUMN listed_account_id INTEGER")


def attach_seat_pdfs(
    seats: list[dict],
    files: dict[str, tuple[str, bytes]],
) -> tuple[int, list[str], list[str]]:
    """Save one PDF per seat. files maps pdf_key -> (zip name, bytes)."""
    matched_keys: set[str] = set()
    missing: list[str] = []
    saved = 0
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        conn = _conn()
        try:
            for seat in seats:
                key = listings_key(seat)
                label = (
                    f"{seat['event_name']} {seat['section']} {seat['row_name']} {seat['seat']}"
                )
                found = files.get(key)
                if not found:
                    missing.append(label)
                    continue
                row = conn.execute(
                    """
                    SELECT id FROM listings
                    WHERE account_email=? AND event_name=? AND section=? AND row_name=? AND seat=?
                    """,
                    (
                        seat["account_email"].strip().lower(),
                        seat["event_name"],
                        seat["section"],
                        seat["row_name"],
                        seat["seat"],
                    ),
                ).fetchone()
                if row is None:
                    missing.append(label)
                    continue
                filename, data = found
                path = listing_pdf_path(int(row["id"]))
                path.write_bytes(data)
                conn.execute(
                    "UPDATE listings SET pdf_name=? WHERE id=?",
                    (filename, int(row["id"])),
                )
                matched_keys.add(key)
                saved += 1
            conn.commit()
        finally:
            conn.close()
    unused = [name for key, (name, _data) in files.items() if key not in matched_keys]
    return saved, missing, unused


def listings_key(seat: dict) -> str:
    from stubhub_listings import pdf_key

    return pdf_key(seat["event_name"], seat["section"], seat["row_name"], seat["seat"])


def _ensure_synced_at(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(accounts)")}
    if cols and "synced_at" not in cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN synced_at INTEGER NOT NULL DEFAULT 0")


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(accounts)")}
    if "password" not in cols and "imap_host" not in cols:
        return
    conn.execute("ALTER TABLE accounts RENAME TO accounts_old")
    conn.execute(
        """
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            recovery_phrase TEXT,
            status TEXT NOT NULL DEFAULT 'free',
            event TEXT,
            created_by INTEGER,
            used_by INTEGER,
            created_at TEXT NOT NULL,
            used_at TEXT,
            last_since INTEGER NOT NULL DEFAULT 0,
            primed INTEGER NOT NULL DEFAULT 0,
            login_error TEXT,
            login_alerted INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    for old in conn.execute("SELECT * FROM accounts_old").fetchall():
        keys = old.keys()
        phrase = old["recovery_phrase"] if "recovery_phrase" in keys and old["recovery_phrase"] else ""
        conn.execute(
            """
            INSERT INTO accounts (
                id, email, recovery_phrase, status, event, created_by, used_by,
                created_at, used_at, primed, login_error, login_alerted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                old["id"],
                old["email"],
                phrase,
                old["status"],
                old["event"] if "event" in keys else None,
                old["created_by"] if "created_by" in keys else None,
                old["used_by"] if "used_by" in keys else None,
                old["created_at"],
                old["used_at"] if "used_at" in keys else None,
                int(old["primed"]) if "primed" in keys else 0,
                old["login_error"] if "login_error" in keys else None,
                int(old["login_alerted"]) if "login_alerted" in keys else 0,
            ),
        )
    conn.execute("DROP TABLE accounts_old")


def _one(sql: str, params: tuple = ()) -> dict | None:
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def _all(sql: str, params: tuple = ()) -> list[dict]:
    with _LOCK:
        conn = _conn()
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()


def set_role(telegram_id: int, role: str | None, username: str = "", full_name: str = "") -> None:
    with _LOCK:
        conn = _conn()
        try:
            if not role:
                conn.execute("DELETE FROM workers WHERE telegram_id=?", (telegram_id,))
            else:
                conn.execute(
                    """
                    INSERT INTO workers (telegram_id, role, username, full_name, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(telegram_id) DO UPDATE SET
                        role=excluded.role,
                        username=COALESCE(NULLIF(excluded.username, ''), workers.username),
                        full_name=COALESCE(NULLIF(excluded.full_name, ''), workers.full_name),
                        updated_at=excluded.updated_at
                    """,
                    (telegram_id, role, username or "", full_name or "", _now()),
                )
            conn.commit()
        finally:
            conn.close()


def touch_user(telegram_id: int, username: str, full_name: str) -> None:
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                """
                UPDATE workers
                SET username=?, full_name=?, updated_at=?
                WHERE telegram_id=?
                """,
                (username or "", full_name or "", _now(), telegram_id),
            )
            conn.commit()
        finally:
            conn.close()


def get_worker(telegram_id: int) -> dict | None:
    return _one("SELECT * FROM workers WHERE telegram_id=?", (telegram_id,))


def list_workers(role: str | None = None) -> list[dict]:
    if role:
        return _all(
            "SELECT * FROM workers WHERE role=? ORDER BY role, telegram_id",
            (role,),
        )
    return _all("SELECT * FROM workers ORDER BY role, telegram_id")


def add_account(email: str, recovery_phrase: str, created_by: int) -> dict | None:
    """Insert a free account. Return None if that mailbox already exists."""
    with _LOCK:
        conn = _conn()
        try:
            try:
                cur = conn.execute(
                    """
                    INSERT INTO accounts (email, recovery_phrase, status, created_by, created_at)
                    VALUES (?, ?, 'free', ?, ?)
                    """,
                    (email, recovery_phrase or "", created_by, _now()),
                )
            except sqlite3.IntegrityError:
                conn.rollback()
                return None
            conn.commit()
            row = conn.execute("SELECT * FROM accounts WHERE id=?", (cur.lastrowid,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def get_account(account_id: int) -> dict | None:
    return _one("SELECT * FROM accounts WHERE id=?", (account_id,))


def get_account_by_email(email: str) -> dict | None:
    return _one("SELECT * FROM accounts WHERE email=? COLLATE NOCASE", (email,))


def list_accounts(status: str | None = None, created_by: int | None = None) -> list[dict]:
    sql = "SELECT * FROM accounts WHERE 1=1"
    params: list = []
    if status:
        sql += " AND status=?"
        params.append(status)
    if created_by is not None:
        sql += " AND created_by=?"
        params.append(created_by)
    sql += " ORDER BY id"
    return _all(sql, tuple(params))


def counts() -> dict[str, int]:
    rows = _all("SELECT status, COUNT(*) AS n FROM accounts GROUP BY status")
    out = {"free": 0, "used": 0, "total": 0}
    for row in rows:
        out[str(row["status"])] = int(row["n"])
        out["total"] += int(row["n"])
    return out


def reset_account(account_id: int) -> str:
    """Mark an account free again. Return ok or missing."""
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute("SELECT id FROM accounts WHERE id=?", (account_id,)).fetchone()
            if not row:
                return "missing"
            conn.execute(
                """
                UPDATE accounts
                SET status='free', event=NULL, used_by=NULL, used_at=NULL
                WHERE id=?
                """,
                (account_id,),
            )
            conn.commit()
            return "ok"
        finally:
            conn.close()


def set_phrase(account_id: int, phrase: str) -> bool:
    with _LOCK:
        conn = _conn()
        try:
            cur = conn.execute(
                "UPDATE accounts SET recovery_phrase=? WHERE id=?",
                (phrase.strip(), account_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def find_accounts(query: str) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []
    if query.isdigit():
        row = get_account(int(query))
        return [row] if row else []
    return _all(
        "SELECT * FROM accounts WHERE email LIKE ? ORDER BY id",
        (f"%{query.lower()}%",),
    )


def mark_used(account_id: int, used_by: int, event: str) -> str:
    """Return ok, missing, or used."""
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute("SELECT status FROM accounts WHERE id=?", (account_id,)).fetchone()
            if not row:
                return "missing"
            if row["status"] != "free":
                return "used"
            conn.execute(
                """
                UPDATE accounts
                SET status='used', event=?, used_by=?, used_at=?
                WHERE id=? AND status='free'
                """,
                (event.strip(), used_by, _now(), account_id),
            )
            conn.commit()
            return "ok"
        finally:
            conn.close()


def delete_account(account_id: int) -> bool:
    with _LOCK:
        conn = _conn()
        try:
            conn.execute("DELETE FROM mail_seen WHERE account_id=?", (account_id,))
            cur = conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def set_recovery_phrase(account_id: int, phrase: str) -> None:
    phrase = (phrase or "").strip()
    if not phrase:
        return
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                """
                UPDATE accounts
                SET recovery_phrase=?
                WHERE id=? AND (recovery_phrase IS NULL OR recovery_phrase='')
                """,
                (phrase, account_id),
            )
            conn.commit()
        finally:
            conn.close()


def seen_ids(account_id: int) -> set[str]:
    rows = _all("SELECT message_id FROM mail_seen WHERE account_id=?", (account_id,))
    return {str(r["message_id"]) for r in rows}


def mark_sync(account_id: int, message_ids: list[str], synced_at: int) -> None:
    """Remember mailed ids and the time of this sync. Only newer mail is sent next."""
    ids = [str(m) for m in message_ids if str(m)]
    with _LOCK:
        conn = _conn()
        try:
            if ids:
                conn.executemany(
                    "INSERT OR IGNORE INTO mail_seen (account_id, message_id) VALUES (?, ?)",
                    [(account_id, mid) for mid in ids],
                )
            conn.execute(
                """
                UPDATE accounts
                SET primed=1,
                    synced_at=CASE WHEN ? > synced_at THEN ? ELSE synced_at END
                WHERE id=?
                """,
                (int(synced_at), int(synced_at), account_id),
            )
            conn.commit()
        finally:
            conn.close()


def claim_login_alert(account_id: int, error: str) -> bool:
    """True when this caller should send the one-time failure notice."""
    with _LOCK:
        conn = _conn()
        try:
            cur = conn.execute(
                """
                UPDATE accounts
                SET login_error=?, login_alerted=1
                WHERE id=? AND login_alerted=0
                """,
                (error[:500], account_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def note_login_error(account_id: int, error: str) -> None:
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                "UPDATE accounts SET login_error=? WHERE id=?",
                (error[:500], account_id),
            )
            conn.commit()
        finally:
            conn.close()


def insert_listings(rows: list[dict]) -> tuple[int, int]:
    """Insert seats. Returns (added, skipped duplicates)."""
    added = 0
    skipped = 0
    now = _now()
    with _LOCK:
        conn = _conn()
        try:
            for row in rows:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO listings (
                        account_email, event_name, event_date, venue, image_url,
                        section, row_name, seat, ticket_url, barcode, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["account_email"].strip().lower(),
                        row["event_name"],
                        row.get("event_date") or "",
                        row.get("venue") or "",
                        row.get("image_url") or "",
                        row["section"],
                        row["row_name"],
                        row["seat"],
                        row.get("ticket_url") or "",
                        row.get("barcode") or "",
                        now,
                    ),
                )
                if cur.rowcount:
                    added += 1
                else:
                    skipped += 1
            conn.commit()
        finally:
            conn.close()
    return added, skipped


def listing_counts() -> dict[str, int]:
    with _LOCK:
        conn = _conn()
        try:
            pending = conn.execute(
                "SELECT COUNT(*) AS n FROM listings WHERE status='pending'"
            ).fetchone()["n"]
            listed = conn.execute(
                "SELECT COUNT(*) AS n FROM listings WHERE status='listed'"
            ).fetchone()["n"]
            pending_events = conn.execute(
                """
                SELECT COUNT(*) AS n FROM (
                    SELECT 1 FROM listings
                    WHERE status='pending'
                    GROUP BY account_email, event_name, event_date, venue
                )
                """
            ).fetchone()["n"]
            return {
                "pending": pending,
                "listed": listed,
                "total": pending + listed,
                "pending_events": pending_events,
            }
        finally:
            conn.close()


def _event_rows(conn: sqlite3.Connection, row: sqlite3.Row) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM listings
        WHERE status='pending'
          AND account_email=? AND event_name=? AND event_date=? AND venue=?
          AND (assigned_to IS NULL OR assigned_to=?)
        ORDER BY id
        """,
        (
            row["account_email"],
            row["event_name"],
            row["event_date"],
            row["venue"],
            row["assigned_to"],
        ),
    ).fetchall()


def claim_next_event(user_id: int, skip_ids: list[int]) -> list[sqlite3.Row]:
    """Claim every pending seat of the next event for this lister."""
    with _LOCK:
        conn = _conn()
        try:
            mine = conn.execute(
                """
                SELECT * FROM listings
                WHERE status='pending' AND assigned_to=?
                ORDER BY id LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            if mine:
                conn.execute(
                    """
                    UPDATE listings SET assigned_to=?
                    WHERE status='pending' AND assigned_to IS NULL
                      AND account_email=? AND event_name=? AND event_date=? AND venue=?
                    """,
                    (
                        user_id,
                        mine["account_email"],
                        mine["event_name"],
                        mine["event_date"],
                        mine["venue"],
                    ),
                )
                conn.commit()
                return conn.execute(
                    """
                    SELECT * FROM listings
                    WHERE status='pending' AND assigned_to=?
                      AND account_email=? AND event_name=? AND event_date=? AND venue=?
                    ORDER BY id
                    """,
                    (
                        user_id,
                        mine["account_email"],
                        mine["event_name"],
                        mine["event_date"],
                        mine["venue"],
                    ),
                ).fetchall()
            skip = {int(i) for i in skip_ids}
            rows = conn.execute(
                """
                SELECT * FROM listings
                WHERE status='pending' AND assigned_to IS NULL
                ORDER BY id
                """
            ).fetchall()
            chosen = None
            for row in rows:
                if int(row["id"]) in skip:
                    continue
                chosen = row
                break
            if chosen is None:
                return []
            conn.execute(
                """
                UPDATE listings SET assigned_to=?
                WHERE status='pending' AND assigned_to IS NULL
                  AND account_email=? AND event_name=? AND event_date=? AND venue=?
                """,
                (
                    user_id,
                    chosen["account_email"],
                    chosen["event_name"],
                    chosen["event_date"],
                    chosen["venue"],
                ),
            )
            conn.commit()
            return conn.execute(
                """
                SELECT * FROM listings
                WHERE status='pending' AND assigned_to=?
                  AND account_email=? AND event_name=? AND event_date=? AND venue=?
                ORDER BY id
                """,
                (
                    user_id,
                    chosen["account_email"],
                    chosen["event_name"],
                    chosen["event_date"],
                    chosen["venue"],
                ),
            ).fetchall()
        finally:
            conn.close()


def mark_event_listed(listing_id: int, user_id: int, account_id: int | None = None) -> list[sqlite3.Row]:
    """Mark every seat of this event that is assigned to the lister."""
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT * FROM listings WHERE id=? AND assigned_to=? AND status='pending'",
                (listing_id, user_id),
            ).fetchone()
            if row is None:
                return []
            conn.execute(
                """
                UPDATE listings
                SET status='listed', listed_by=?, listed_at=?, assigned_to=NULL,
                    listed_account_id=?
                WHERE status='pending' AND assigned_to=?
                  AND account_email=? AND event_name=? AND event_date=? AND venue=?
                """,
                (
                    user_id,
                    _now(),
                    account_id,
                    user_id,
                    row["account_email"],
                    row["event_name"],
                    row["event_date"],
                    row["venue"],
                ),
            )
            conn.commit()
            return conn.execute(
                """
                SELECT * FROM listings
                WHERE listed_by=? AND status='listed'
                  AND account_email=? AND event_name=? AND event_date=? AND venue=?
                ORDER BY id
                """,
                (
                    user_id,
                    row["account_email"],
                    row["event_name"],
                    row["event_date"],
                    row["venue"],
                ),
            ).fetchall()
        finally:
            conn.close()


def mark_event_mobile(listing_id: int, user_id: int) -> list[dict]:
    """Take this event out of the queue and return its seats."""
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT * FROM listings WHERE id=? AND status='pending'",
                (listing_id,),
            ).fetchone()
            if row is None:
                return []
            conn.execute(
                """
                UPDATE listings
                SET status='mobile', listed_by=?, listed_at=?, assigned_to=NULL
                WHERE status='pending'
                  AND account_email=? AND event_name=? AND event_date=? AND venue=?
                """,
                (
                    user_id,
                    _now(),
                    row["account_email"],
                    row["event_name"],
                    row["event_date"],
                    row["venue"],
                ),
            )
            conn.commit()
            saved = conn.execute(
                """
                SELECT * FROM listings
                WHERE status='mobile' AND listed_by=?
                  AND account_email=? AND event_name=? AND event_date=? AND venue=?
                ORDER BY id
                """,
                (
                    user_id,
                    row["account_email"],
                    row["event_name"],
                    row["event_date"],
                    row["venue"],
                ),
            ).fetchall()
            return [dict(r) for r in saved]
        finally:
            conn.close()


MOBILE_PATH = ROOT / "data" / "mobile_tickets.txt"


def append_mobile_ticket(text: str) -> None:
    with _LOCK:
        MOBILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with MOBILE_PATH.open("a", encoding="utf-8") as handle:
            handle.write(text.rstrip() + "\n\n")


def release_event(listing_id: int, user_id: int) -> list[int]:
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT * FROM listings WHERE id=? AND assigned_to=? AND status='pending'",
                (listing_id, user_id),
            ).fetchone()
            if row is None:
                return []
            ids = [
                int(r["id"])
                for r in conn.execute(
                    """
                    SELECT id FROM listings
                    WHERE status='pending' AND assigned_to=?
                      AND account_email=? AND event_name=? AND event_date=? AND venue=?
                    """,
                    (
                        user_id,
                        row["account_email"],
                        row["event_name"],
                        row["event_date"],
                        row["venue"],
                    ),
                ).fetchall()
            ]
            if not ids:
                return []
            marks = ",".join("?" * len(ids))
            conn.execute(
                f"UPDATE listings SET assigned_to=NULL WHERE id IN ({marks})",
                ids,
            )
            conn.commit()
            return ids
        finally:
            conn.close()


def claim_next_listing(user_id: int, skip_ids: list[int]) -> sqlite3.Row | None:
    """Resume this user's card, else claim the next pending seat."""
    with _LOCK:
        conn = _conn()
        try:
            mine = conn.execute(
                """
                SELECT * FROM listings
                WHERE status='pending' AND assigned_to=?
                ORDER BY id LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            if mine:
                return mine
            skip = [int(i) for i in skip_ids if str(i).isdigit() or isinstance(i, int)]
            query = """
                SELECT * FROM listings
                WHERE status='pending' AND assigned_to IS NULL
            """
            params: list = []
            if skip:
                marks = ",".join("?" * len(skip))
                query += f" AND id NOT IN ({marks})"
                params.extend(skip)
            query += " ORDER BY id LIMIT 1"
            row = conn.execute(query, params).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE listings SET assigned_to=? WHERE id=? AND status='pending'",
                (user_id, row["id"]),
            )
            conn.commit()
            return conn.execute(
                "SELECT * FROM listings WHERE id=?", (row["id"],)
            ).fetchone()
        finally:
            conn.close()


def get_listing(listing_id: int) -> dict | None:
    return _one("SELECT * FROM listings WHERE id=?", (listing_id,))


def listings_for_worm_account(account_id: int, *, limit: int = 40) -> list[dict]:
    """Seats listed on StubHub using this worm account (#accounts.id)."""
    return _all(
        """
        SELECT * FROM listings
        WHERE listed_account_id=? AND status IN ('listed', 'pending')
        ORDER BY listed_at DESC, id DESC
        LIMIT ?
        """,
        (int(account_id), int(limit)),
    )


def mark_listing_listed(listing_id: int, user_id: int) -> sqlite3.Row | None:
    """Mark pending seat listed. Returns the row, or None if it was not theirs."""
    with _LOCK:
        conn = _conn()
        try:
            cur = conn.execute(
                """
                UPDATE listings
                SET status='listed', listed_by=?, listed_at=?, assigned_to=NULL
                WHERE id=? AND status='pending' AND assigned_to=?
                """,
                (user_id, _now(), listing_id, user_id),
            )
            conn.commit()
            if cur.rowcount != 1:
                return None
            return conn.execute(
                "SELECT * FROM listings WHERE id=?", (listing_id,)
            ).fetchone()
        finally:
            conn.close()


def release_listing(listing_id: int, user_id: int) -> bool:
    with _LOCK:
        conn = _conn()
        try:
            cur = conn.execute(
                """
                UPDATE listings SET assigned_to=NULL
                WHERE id=? AND status='pending' AND assigned_to=?
                """,
                (listing_id, user_id),
            )
            conn.commit()
            return cur.rowcount == 1
        finally:
            conn.close()


def capture_counts() -> dict[str, int]:
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM capture_jobs GROUP BY status"
            ).fetchall()
            out = {"pending": 0, "assigned": 0, "confirmed": 0, "failed": 0, "total": 0}
            for r in rows:
                st = str(r["status"])
                n = int(r["n"])
                if st in out:
                    out[st] = n
                out["total"] += n
            return out
        finally:
            conn.close()


def insert_capture_jobs(rows: list[dict]) -> tuple[int, int]:
    """Insert new jobs; re-open failed/pending duplicates with fresh password/qty."""
    added = skipped = 0
    now = _now()
    with _LOCK:
        conn = _conn()
        try:
            for row in rows:
                email = row["email"].strip().lower()
                app_login = row.get("app_login") or ""
                event_name = row["event_name"]
                event_date = row.get("event_date") or ""
                venue = row.get("venue") or ""
                qty = int(row.get("qty_expected") or 1)
                password = row.get("password") or ""
                existing = conn.execute(
                    """
                    SELECT id, status FROM capture_jobs
                    WHERE email=? AND event_name=? AND event_date=? AND venue=? AND app_login=?
                    """,
                    (email, event_name, event_date, venue, app_login),
                ).fetchone()
                if existing:
                    st = str(existing["status"])
                    if st in ("confirmed", "assigned"):
                        skipped += 1
                        continue
                    conn.execute(
                        """
                        UPDATE capture_jobs
                        SET password=?, qty_expected=?, status='pending',
                            assigned_to=NULL, assigned_at=NULL, fail_reason=NULL,
                            worker_notes=NULL, confirmed_by=NULL, confirmed_at=NULL
                        WHERE id=?
                        """,
                        (password, qty, int(existing["id"])),
                    )
                    conn.execute(
                        "DELETE FROM capture_seats WHERE job_id=?",
                        (int(existing["id"]),),
                    )
                    added += 1
                    continue
                conn.execute(
                    """
                    INSERT INTO capture_jobs (
                        email, password, app_login, event_name, event_date, venue,
                        qty_expected, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (email, password, app_login, event_name, event_date, venue, qty, now),
                )
                added += 1
            conn.commit()
        finally:
            conn.close()
    return added, skipped


def requeue_capture_job(job_id: int) -> str:
    """Return ok, missing, or locked (confirmed)."""
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT id, status FROM capture_jobs WHERE id=?", (job_id,)
            ).fetchone()
            if not row:
                return "missing"
            if str(row["status"]) == "confirmed":
                return "locked"
            conn.execute(
                """
                UPDATE capture_jobs
                SET status='pending', assigned_to=NULL, assigned_at=NULL,
                    fail_reason=NULL, worker_notes=NULL
                WHERE id=?
                """,
                (job_id,),
            )
            conn.execute("DELETE FROM capture_seats WHERE job_id=?", (job_id,))
            conn.commit()
            return "ok"
        finally:
            conn.close()


def get_capture_job(job_id: int) -> dict | None:
    return _one("SELECT * FROM capture_jobs WHERE id=?", (job_id,))


def list_capture_jobs(status: str | None = None, limit: int = 500) -> list[dict]:
    sql = "SELECT * FROM capture_jobs WHERE 1=1"
    params: list = []
    if status:
        sql += " AND status=?"
        params.append(status)
    sql += " ORDER BY id LIMIT ?"
    params.append(int(limit))
    return _all(sql, tuple(params))


def claim_capture_job(user_id: int) -> dict | None:
    with _LOCK:
        conn = _conn()
        try:
            mine = conn.execute(
                """
                SELECT * FROM capture_jobs
                WHERE status='assigned' AND assigned_to=?
                ORDER BY id LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            if mine:
                return dict(mine)
            row = conn.execute(
                """
                SELECT * FROM capture_jobs
                WHERE status='pending'
                ORDER BY id LIMIT 1
                """
            ).fetchone()
            if not row:
                return None
            conn.execute(
                """
                UPDATE capture_jobs
                SET status='assigned', assigned_to=?, assigned_at=?
                WHERE id=? AND status='pending'
                """,
                (user_id, _now(), int(row["id"])),
            )
            conn.commit()
            return dict(
                conn.execute("SELECT * FROM capture_jobs WHERE id=?", (int(row["id"]),)).fetchone()
            )
        finally:
            conn.close()


def release_capture_job(job_id: int, user_id: int) -> bool:
    with _LOCK:
        conn = _conn()
        try:
            cur = conn.execute(
                """
                UPDATE capture_jobs
                SET status='pending', assigned_to=NULL, assigned_at=NULL
                WHERE id=? AND assigned_to=? AND status='assigned'
                """,
                (job_id, user_id),
            )
            conn.execute("DELETE FROM capture_seats WHERE job_id=?", (job_id,))
            conn.commit()
            return cur.rowcount == 1
        finally:
            conn.close()


def fail_capture_job(job_id: int, user_id: int, reason: str) -> bool:
    with _LOCK:
        conn = _conn()
        try:
            cur = conn.execute(
                """
                UPDATE capture_jobs
                SET status='failed', fail_reason=?, worker_notes=?, assigned_to=NULL
                WHERE id=? AND assigned_to=? AND status='assigned'
                """,
                (reason[:500], reason[:500], job_id, user_id),
            )
            conn.commit()
            return cur.rowcount == 1
        finally:
            conn.close()


def save_capture_seats(job_id: int, seats: list[dict]) -> None:
    with _LOCK:
        conn = _conn()
        try:
            conn.execute("DELETE FROM capture_seats WHERE job_id=?", (job_id,))
            for i, s in enumerate(seats, start=1):
                conn.execute(
                    """
                    INSERT INTO capture_seats (job_id, seat_slot, section, row_name, seat, barcode)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        i,
                        s.get("section") or "",
                        s.get("row_name") or "",
                        s.get("seat") or "",
                        s.get("barcode") or "",
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def get_capture_seats(job_id: int) -> list[dict]:
    return _all(
        "SELECT * FROM capture_seats WHERE job_id=? ORDER BY seat_slot",
        (job_id,),
    )


def _seats_valid_for_job(job: sqlite3.Row, seats: list[sqlite3.Row]) -> str | None:
    need = int(job["qty_expected"] or 1)
    if len(seats) != need:
        return f"Need {need} seat(s) on file, have {len(seats)}."
    for s in seats:
        if not str(s["section"] or "").strip():
            return "Every seat needs a section."
        if not str(s["row_name"] or "").strip():
            return "Every seat needs a row."
        if not str(s["seat"] or "").strip():
            return "Every seat needs a seat number."
    return None


def confirm_capture_job(job_id: int, user_id: int) -> tuple[int, int, str | None]:
    """Mark confirmed and insert listings rows. Returns (added, skipped, error)."""
    with _LOCK:
        conn = _conn()
        try:
            job = conn.execute(
                "SELECT * FROM capture_jobs WHERE id=? AND assigned_to=? AND status='assigned'",
                (job_id, user_id),
            ).fetchone()
            if not job:
                return 0, 0, "not_assigned"
            seats = conn.execute(
                "SELECT * FROM capture_seats WHERE job_id=? ORDER BY seat_slot",
                (job_id,),
            ).fetchall()
            err = _seats_valid_for_job(job, seats)
            if err:
                return 0, 0, err
            added = skipped = 0
            now = _now()
            for s in seats:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO listings (
                        account_email, event_name, event_date, venue, image_url,
                        section, row_name, seat, ticket_url, barcode, created_at
                    ) VALUES (?, ?, ?, ?, '', ?, ?, ?, '', ?, ?)
                    """,
                    (
                        job["email"],
                        job["event_name"],
                        job["event_date"] or "",
                        job["venue"] or "",
                        s["section"],
                        s["row_name"],
                        s["seat"],
                        s["barcode"] or "",
                        now,
                    ),
                )
                if cur.rowcount:
                    added += 1
                else:
                    skipped += 1
            conn.execute(
                """
                UPDATE capture_jobs
                SET status='confirmed', confirmed_by=?, confirmed_at=?
                WHERE id=?
                """,
                (user_id, now, job_id),
            )
            conn.commit()
            return added, skipped, None
        finally:
            conn.close()


def admin_export_snapshot() -> str:
    """Text dump for admin: worm accounts + capture + listings summary."""
    parts = ["=== WORM ACCOUNTS ===", ""]
    parts.append(f"Counts: {counts()}")
    for row in list_accounts()[:2000]:
        parts.append(
            f"#{row['id']} {row['status']} {row['email']} event={row.get('event') or ''}"
        )
    parts.append("")
    parts.append("=== CAPTURE QUEUE ===")
    parts.append(str(capture_counts()))
    for row in list_capture_jobs(limit=3000):
        parts.append(
            f"#{row['id']} {row['status']} {row['email']}:{row.get('password') or ''} "
            f"app={row.get('app_login') or ''} | {row['event_name']} | {row['event_date']} "
            f"qty={row['qty_expected']} assigned={row.get('assigned_to') or ''}"
        )
        if str(row["status"]) == "confirmed":
            for s in get_capture_seats(int(row["id"])):
                parts.append(
                    f"    seat {s['seat_slot']}: {s['section']} / {s['row_name']} / {s['seat']}"
                )
    parts.append("")
    parts.append("=== LISTINGS (pending seats) ===")
    parts.append(str(listing_counts()))
    for row in _all(
        "SELECT * FROM listings WHERE status='pending' ORDER BY id LIMIT 5000"
    ):
        parts.append(
            f"#{row['id']} {row['account_email']} | {row['event_name']} | "
            f"{row['section']}/{row['row_name']}/{row['seat']}"
        )
    return "\n".join(parts)


def clear_login_alert(account_id: int) -> bool:
    """True if a failure notice was previously sent and should be cleared."""
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT login_alerted FROM accounts WHERE id=?",
                (account_id,),
            ).fetchone()
            was = bool(row and row["login_alerted"])
            conn.execute(
                "UPDATE accounts SET login_error=NULL, login_alerted=0 WHERE id=?",
                (account_id,),
            )
            conn.commit()
            return was
        finally:
            conn.close()
