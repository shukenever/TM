#!/usr/bin/env python3
"""Stagefront: login (proxy), list unfulfilled sales, match email:pw + barcodes from VL/SF/neutral DBs.

Outputs:
  exports/sf_unfulfilled_<stamp>.txt  — human lines
  exports/sf_unfulfilled_<stamp>.js   — module.exports = [{ email, password, barcodes, ... }]

Auth:
  STAGEFRONT_USER (default Fouad.Mahmoud) + STAGEFRONT_PASSWORD + --login
  Optional: --remember-har portal.stagefront.com.har (2FA remember-browser, no OTP)
  Proxy: STAGEFRONT_PROXY or vl_auth FlashProxy (always used).

Stock (seat → barcode + email:pw):
  Default --stock both = TM work checker /fulfill DB + VL inventory (pull DBs first).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for SF_PKG in (ROOT / "stagefront_pricing", ROOT / "ticketmaster" / "stagefront_pricing"):
    if SF_PKG.is_dir():
        sys.path.insert(0, str(SF_PKG))
        break
sys.path.insert(0, str(ROOT))

import vl_auth  # noqa: E402
from list_unfulfilled import prep_df, seat_match, section_variants, parse_event_date  # noqa: E402
from ticketmaster.vl_fulfill_service import load_vl_stock_df  # noqa: E402
from tm_worker_fulfill_stock import load_tm_worker_fulfill_stock_df  # noqa: E402

sys.path.insert(0, str(ROOT / "ticketmaster"))
import bot as tm_bot  # noqa: E402
from vl_stock import event_date_to_iso  # noqa: E402

from auth import cookie_from_har  # type: ignore  # noqa: E402
from client import StagefrontClient, StagefrontConfig  # type: ignore  # noqa: E402


def _parse_proxy(raw: str) -> str:
    import urllib.parse

    raw = (raw or "").strip()
    if not raw:
        return ""
    if raw.startswith("http"):
        return raw
    parts = raw.split(":")
    if len(parts) >= 4:
        host, port, user = parts[0], parts[1], parts[2]
        password = ":".join(parts[3:])
        return (
            f"http://{urllib.parse.quote(user, safe='')}:"
            f"{urllib.parse.quote(password, safe='')}@{host}:{port}"
        )
    return raw


def _default_proxy() -> str:
    env = os.environ.get("STAGEFRONT_PROXY", "").strip()
    if env:
        return _parse_proxy(env)
    raw = f"{vl_auth.PROXY_HOST}:{vl_auth.PROXY_PORT}:{vl_auth.PROXY_USER}:{vl_auth.PROXY_PASS}"
    return _parse_proxy(raw)


DEFAULT_SF_USER = os.environ.get("STAGEFRONT_USER", "Fouad.Mahmoud").strip()


def _remember_cookie_from_har(har_path: Path) -> str:
    """Extract .AspNet.TwoFactorRememberBrowser from a portal HAR export."""
    text = har_path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"\.AspNet\.TwoFactorRememberBrowser=([^;\s\"]+)", text)
    return m.group(0) if m else ""


def _connect_sf(args: argparse.Namespace) -> StagefrontClient:
    proxy = _parse_proxy(args.proxy) if args.proxy else _default_proxy()
    if not proxy:
        raise SystemExit("Set STAGEFRONT_PROXY or vl_auth proxy env")
    cfg = StagefrontConfig(proxy_url=proxy, company_name=(args.company or "").strip() or None)
    client = StagefrontClient(cfg)

    cookie = os.environ.get("STAGEFRONT_COOKIE", "").strip()
    har = (args.har or "").strip()
    if har:
        cookie = cookie_from_har(ROOT / har if not Path(har).is_file() else har)

    user = (args.user or os.environ.get("STAGEFRONT_USER") or DEFAULT_SF_USER).strip()
    password = args.password or os.environ.get("STAGEFRONT_PASSWORD", "")

    remember = os.environ.get("STAGEFRONT_REMEMBER_BROWSER", "").strip()
    rh = (args.remember_har or "").strip()
    if rh:
        hp = ROOT / rh if not Path(rh).is_file() else Path(rh)
        if hp.is_file():
            remember = _remember_cookie_from_har(hp) or remember

    use_login = bool(args.login or password)
    if use_login:
        if not user or not password:
            raise SystemExit("Set STAGEFRONT_PASSWORD (and optional STAGEFRONT_USER) with --login")
        if remember:
            client.seed_remember_browser(remember)
            print("Seeded 2FA remember-browser cookie")
        print(f"Logging in as {user!r} via proxy…")
        needs_2fa = client.login(user, password)
        if needs_2fa:
            otp = (args.otp or os.environ.get("STAGEFRONT_2FA_CODE", "")).strip()
            if otp:
                client.verify_two_factor(otp)
            elif sys.stdin.isatty():
                client.login_interactive(user, password)
            else:
                raise SystemExit(
                    "2FA required — set STAGEFRONT_2FA_CODE=... or run in a terminal for OTP prompt"
                )
    elif cookie:
        client.set_cookie(cookie)
    else:
        raise SystemExit("Set STAGEFRONT_PASSWORD + --login, or STAGEFRONT_COOKIE, or --har")

    client.ensure_api_session()
    return client


def _sf_event_iso(raw: str) -> str:
    return (event_date_to_iso(raw) or str(raw or "").strip())[:10]


def _is_sale_unfulfilled(row: dict) -> bool:
    status = str(row.get("Sale_Status") or row.get("sale_status") or "").strip().lower()
    if any(x in status for x in ("complete", "delivered", "fulfilled", "transferred", "closed")):
        if "pending" not in status and "incomplete" not in status:
            return False
    completed = row.get("Completed_Date") or row.get("completed_date")
    if completed and str(completed).strip() not in ("", "null", "None"):
        # Still unfulfilled if status says pending despite a date (SF quirk)
        if "pending" not in status and "awaiting" not in status:
            return False
    nb = int(row.get("Num_Barcodes") or row.get("num_barcodes") or 0)
    pdfs = int(row.get("PdfsAttached") or row.get("pdfs_attached") or row.get("Num_PDFs") or 0)
    if nb > 0 or pdfs > 0:
        return False
    if "pending" in status or "awaiting" in status or "incomplete" in status:
        return True
    if not status or status in ("tickets pending", "open", "new"):
        return True
    # No barcodes/PDFs and not clearly complete
    if not completed:
        return True
    return False


def _fetch_sales(client: StagefrontClient, company: str) -> list[dict]:
    rows = client.query_sales(
        company,
        sale_from="01/01/2020",
        sale_to="12/31/2030",
    )
    if rows:
        return rows
    return client.query_fulfillment(company)


def _dedupe_sales(rows: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for row in rows:
        inv = int(row.get("Invoice_ID") or row.get("invoice_id") or 0)
        lid = int(row.get("Listing_ID") or row.get("listing_id") or 0)
        sf = int(row.get("Seat_From") or row.get("seat_from") or 0)
        st = int(row.get("Seat_Thru") or row.get("seat_thru") or sf)
        key = (inv, lid, sf, st)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _seats_for_sale(row: dict) -> list[str]:
    sfrom = int(row.get("Seat_From") or row.get("seat_from") or 0)
    sthr = int(row.get("Seat_Thru") or row.get("seat_thru") or sfrom)
    qty = int(row.get("Quantity") or row.get("quantity") or 1)
    if sfrom and sthr and sthr >= sfrom:
        return [str(n) for n in range(sfrom, sthr + 1)]
    if sfrom:
        return [str(sfrom)]
    return [str(i + 1) for i in range(max(1, qty))]


def _event_name_ok(sale_name: str, stock_name: object) -> bool:
    en = str(sale_name or "").strip().lower()
    v = str(stock_name or "").strip().lower()
    if not en or not v:
        return False
    if en[:14] in v or v[:14] in en:
        return True
    tokens = [t for t in re.split(r"[^a-z0-9]+", en) if len(t) >= 3][:4]
    return bool(tokens) and sum(1 for t in tokens if t in v) >= max(1, len(tokens) - 1)


def _row_compatible(want: str, have: str) -> bool:
    w, h = str(want or "").strip().upper(), str(have or "").strip().upper()
    if not w or not h:
        return True
    if w == h:
        return True
    if w in ("GA", "GEN", "GENADM", "G", "GA0") and (h.startswith("GA") or h.startswith("G")):
        return True
    if w.startswith("GA") and h.startswith("GA"):
        return True
    if len(w) >= 2 and (h.startswith(w) or w.startswith(h)):
        return True
    return False


def _sf_hit_ok(
    hit,
    *,
    event_date: str | None,
    section: str,
    row: str,
    seat: str,
) -> bool:
    """Stagefront: require exact event date + section/row/seat (no wrong-night stock)."""
    if hit is None:
        return False
    ed = parse_event_date(str(event_date or "")[:10]) if event_date else None
    if ed is not None:
        hed = hit.get("_edate") if hasattr(hit, "get") else None
        if hed is None and hasattr(hit, "__getitem__"):
            hed = parse_event_date(str(hit.get("Event Date") or ""))
        if hed != ed:
            return False
    seat_s = str(seat).strip()
    if str(hit.get("_seat") or hit.get("Seat") or "").strip() != seat_s:
        return False
    row_u = str(row or "").strip().upper()
    have_row = str(hit.get("_row") or hit.get("Row") or "").strip().upper()
    if not _row_compatible(row_u, have_row):
        return False
    variants = section_variants(section)
    sec = str(hit.get("_sec") or hit.get("Section") or "")
    from fulfill_victory_live import clean_section

    if clean_section(sec) not in variants and sec not in variants:
        return False
    return True


def _pick_stock_hit(hits, *, event_name: str, venue: str):
    if hits is None or len(hits) == 0:
        return None
    if len(hits) == 1:
        return hits.iloc[0]
    if event_name and "Event Name" in hits.columns:
        named = hits[hits["Event Name"].apply(lambda v: _event_name_ok(event_name, v))]
        if len(named) == 1:
            return named.iloc[0]
        if len(named) > 1:
            hits = named
    if venue and "_venue" in hits.columns:
        v = venue.lower()
        for _, r in hits.iterrows():
            sv = str(r.get("_venue") or "")
            if v[:8] in sv or sv[:8] in v:
                return r
    return hits.iloc[0]


def _seat_match_sf(stock_df, section, row, seat, *, event_date, venue, event_name):
    ed = parse_event_date(str(event_date)[:10]) if event_date else None
    hit = seat_match(
        stock_df,
        section,
        row,
        seat,
        event_date=ed,
        venue=venue or None,
        event_name=event_name or None,
    )
    if hit is not None and _sf_hit_ok(hit, event_date=event_date, section=section, row=row, seat=seat):
        return hit

    seat_s = str(seat).strip()
    row_u = str(row).strip().upper()
    variants = section_variants(section)

    mask = stock_df["_sec"].isin(variants) & (stock_df["_seat"] == seat_s)
    if ed is not None:
        mask &= stock_df["_edate"] == ed
    hits = stock_df[mask]
    if len(hits):
        if row_u:
            relaxed = hits[hits["_row"].apply(lambda r: _row_compatible(row_u, r))]
            if len(relaxed):
                hits = relaxed
        picked = _pick_stock_hit(hits, event_name=event_name or "", venue=venue or "")
        if picked is not None and _sf_hit_ok(
            picked, event_date=event_date, section=section, row=row, seat=seat
        ):
            return picked

    return None


def _seat_display(section: str, row: str, seat: str) -> str:
    sec = str(section or "").strip()
    rw = str(row or "").strip()
    st = str(seat or "").strip()
    if sec and rw:
        return f"Sec {sec} Row {rw} Seat {st}"
    if sec:
        return f"Sec {sec} Seat {st}"
    return f"Seat {st}"


def _match_sale(stock_df, row: dict) -> tuple[str, str, list[tuple[str, str]], list[str], str]:
    """Return email, password, [(seat_label, barcode), ...], all_barcodes, match_note."""
    section = str(row.get("Section") or row.get("section") or "")
    rw = str(row.get("Row") or row.get("row") or "")
    ed = _sf_event_iso(str(row.get("Event_Date") or row.get("event_date") or ""))
    venue = str(row.get("Venue_Name") or row.get("venue_name") or "")
    event = str(row.get("Event_Name") or row.get("event_name") or "")

    emails: list[str] = []
    passwords: list[str] = []
    seat_pairs: list[tuple[str, str]] = []
    seat_emails: list[str] = []

    for seat in _seats_for_sale(row):
        seat_label = _seat_display(section, rw, seat)
        bc = ""
        em_seat = ""
        hits = _seat_match_sf(
            stock_df,
            section,
            rw,
            seat,
            event_date=ed or None,
            venue=venue,
            event_name=event,
        )
        if hits is not None:
            em_seat = str(hits.get("Email") or hits.get("email") or "").strip()
            pw = str(hits.get("Password") or hits.get("password") or "").strip()
            hit_bc = tm_bot._fulfill_clean_barcode(
                str(hits.get("_bc") or hits.get("Barcodes") or hits.get("barcode") or "").strip()
            )
            if em_seat:
                emails.append(em_seat)
                seat_emails.append(em_seat)
            if pw:
                passwords.append(pw)
            if hit_bc and hit_bc.lower() not in ("nan", "none"):
                bc = hit_bc
        seat_pairs.append((seat_label, bc))

    # One purchasing account per invoice — drop barcodes if seats disagree
    if seat_emails and len(set(seat_emails)) > 1:
        seat_pairs = [(lbl, "") for lbl, _ in seat_pairs]
        emails = [seat_emails[0]]

    email = emails[0] if emails else ""
    password = passwords[0] if passwords else ""
    uniq_bc: list[str] = []
    seen_bc: set[str] = set()
    for _, b in seat_pairs:
        if b and b not in seen_bc:
            seen_bc.add(b)
            uniq_bc.append(b)

    has_bc = any(b for _, b in seat_pairs)
    note = "ok" if email and has_bc else ("partial" if email or has_bc else "no_db_match")
    return email, password, seat_pairs, uniq_bc, note


def _load_valids(path: Path) -> dict[str, str]:
    """email (lower) -> full email:password line from valids.txt."""
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        em = line.split(":", 1)[0].strip().lower()
        if em:
            out[em] = line
    return out


def _apply_valids(records: list[dict], valids: dict[str, str]) -> None:
    for rec in records:
        em = str(rec.get("email") or "").strip().lower()
        if em and em in valids:
            rec["valid_cred"] = valids[em]
            rec["is_valid_account"] = True
        else:
            rec["valid_cred"] = ""
            rec["is_valid_account"] = False


def _js_export_records(records: list[dict]) -> list[dict]:
    """Valid accounts get creds; others barcodes + seat_pairs only."""
    out: list[dict] = []
    for rec in records:
        row: dict = {
            "invoice_id": rec.get("invoice_id"),
            "event": rec.get("event"),
            "event_date": rec.get("event_date"),
            "section": rec.get("section"),
            "row": rec.get("row"),
            "barcodes": rec.get("barcodes") or [],
            "seat_pairs": rec.get("seat_pairs") or [],
        }
        if rec.get("is_valid_account") and rec.get("valid_cred"):
            row["emailPassword"] = rec["valid_cred"]
        out.append(row)
    return out


def _format_export_blocks(records: list[dict]) -> list[str]:
    """Human export: invoice + account (valids.txt only), then SEAT | BARCODE lines."""
    lines: list[str] = []
    for rec in records:
        inv = rec.get("invoice_id") or ""
        cred = rec.get("valid_cred") or ""
        lines.append(f"{inv} | {cred}")
        for seat_label, bc in rec.get("seat_pairs") or []:
            lines.append(f"{seat_label} | {bc or ''}")
        lines.append("")
    return lines


def _sale_summary(row: dict) -> dict:
    inv = int(row.get("Invoice_ID") or 0)
    return {
        "invoice_id": inv,
        "sale_date": str(row.get("Sale_Date") or "")[:19],
        "sale_status": str(row.get("Sale_Status") or ""),
        "listing_id": int(row.get("Listing_ID") or 0),
        "event": str(row.get("Event_Name") or ""),
        "event_date": _sf_event_iso(str(row.get("Event_Date") or "")),
        "venue": str(row.get("Venue_Name") or ""),
        "section": str(row.get("Section") or ""),
        "row": str(row.get("Row") or ""),
        "seat_from": int(row.get("Seat_From") or 0),
        "seat_thru": int(row.get("Seat_Thru") or 0),
        "qty": int(row.get("Quantity") or 1),
        "exchange": str(row.get("Exchange_Name") or ""),
        "num_barcodes": int(row.get("Num_Barcodes") or 0),
    }


def _load_stock_df(mode: str) -> pd.DataFrame:
    import pandas as pd

    mode = (mode or "both").strip().lower()
    if mode == "vl":
        return load_vl_stock_df()
    if mode == "both":
        a = load_tm_worker_fulfill_stock_df()
        b = load_vl_stock_df()
        if len(a) and len(b):
            return prep_df(pd.concat([a, b], ignore_index=True))
        return a if len(a) else b
    return load_tm_worker_fulfill_stock_df()


def main() -> int:
    ap = argparse.ArgumentParser(description="Export Stagefront unfulfilled sales with DB creds + barcodes")
    ap.add_argument("--login", action="store_true", help="Password login (needs STAGEFRONT_PASSWORD)")
    ap.add_argument("--user", default="", help=f"Portal username (default {DEFAULT_SF_USER})")
    ap.add_argument("--password", default="", help="Portal password (prefer STAGEFRONT_PASSWORD env)")
    ap.add_argument("--otp", default="", help="Email 2FA code (or STAGEFRONT_2FA_CODE env)")
    ap.add_argument(
        "--remember-har",
        default="portal.stagefront.com3.har",
        help="HAR with 2FA remember cookie (use '' to skip)",
    )
    ap.add_argument("--har", default="", help="Optional: API session cookie from HAR instead of login")
    ap.add_argument("--proxy", default="", help="Override proxy host:port:user:pass")
    ap.add_argument("--company", default="", help="Stagefront company name")
    ap.add_argument("--out-dir", default=str(ROOT / "exports"))
    ap.add_argument("--include-all-open", action="store_true", help="Also export sales with empty status if no PDF/bc")
    ap.add_argument(
        "--pull-stock",
        action="store_true",
        help="Pull tm_worker_collector.db + vl_inventory.db from VPS before export",
    )
    ap.add_argument(
        "--stock",
        default="both",
        choices=("tm-worker", "vl", "both"),
        help="Stock source (default: TM work checker + VL inventory)",
    )
    ap.add_argument(
        "--from-js",
        default="",
        help="Rebuild export from prior .js (use with --rematch to re-apply strict stock match)",
    )
    ap.add_argument(
        "--rematch",
        action="store_true",
        help="With --from-js: re-match seats/barcodes from stock (exact event date)",
    )
    ap.add_argument(
        "--valids",
        default=str(ROOT / "valids.txt"),
        help="Valid purchasing accounts (email:pw); only these get creds in .txt / accounts file",
    )
    args = ap.parse_args()

    valids_path = Path(args.valids)
    if not valids_path.is_file() and (ROOT / "valids.txt").is_file():
        valids_path = ROOT / "valids.txt"
    valids = _load_valids(valids_path)
    if valids:
        print(f"Loaded {len(valids)} valid accounts from {valids_path.name}")

    from_js = (args.from_js or "").strip()
    if from_js:
        js_in = Path(from_js)
        if not js_in.is_file():
            js_in = ROOT / from_js
        if not js_in.is_file():
            raise SystemExit(f"--from-js not found: {args.from_js}")
        text = js_in.read_text(encoding="utf-8")
        marker = "module.exports = "
        i = text.find(marker)
        if i < 0:
            raise SystemExit("invalid --from-js file (no module.exports)")
        records = json.loads(text[i + len(marker) :].rstrip().rstrip(";").strip())
        if args.rematch:
            print(f"Rematching {len(records)} sales (strict date/section)…", flush=True)
            stock_df = _load_stock_df(args.stock)
            matched = partial = no_match = 0
            rematched: list[dict] = []
            for rec in records:
                row_d = {
                    "Section": rec.get("section") or "",
                    "Row": rec.get("row") or "",
                    "Seat_From": int(rec.get("seat_from") or 0),
                    "Seat_Thru": int(rec.get("seat_thru") or 0),
                    "Quantity": int(rec.get("qty") or 1),
                    "Event_Date": rec.get("event_date") or "",
                    "Event_Name": rec.get("event") or "",
                    "Venue_Name": rec.get("venue") or "",
                }
                email, password, seat_pairs, barcodes, note = _match_sale(stock_df, row_d)
                if note == "ok":
                    matched += 1
                elif note == "partial":
                    partial += 1
                else:
                    no_match += 1
                cred = f"{email}:{password}" if email and password else (email or "")
                rematched.append(
                    {
                        "email": email,
                        "password": password,
                        "barcodes": barcodes,
                        "seat_pairs": seat_pairs,
                        "emailPassword": cred,
                        "invoice_id": rec.get("invoice_id"),
                        "sale_date": rec.get("sale_date"),
                        "sale_status": rec.get("sale_status"),
                        "listing_id": rec.get("listing_id"),
                        "event": rec.get("event"),
                        "event_date": rec.get("event_date"),
                        "venue": rec.get("venue"),
                        "section": rec.get("section"),
                        "row": rec.get("row"),
                        "seat_from": rec.get("seat_from"),
                        "seat_thru": rec.get("seat_thru"),
                        "qty": rec.get("qty"),
                        "exchange": rec.get("exchange"),
                        "num_barcodes": rec.get("num_barcodes"),
                        "match": note,
                    }
                )
            records = rematched
            print(f"Rematch: ok={matched} partial={partial} no_db_match={no_match}", flush=True)
        else:
            for rec in records:
                if "seat_pairs" not in rec and rec.get("barcodes"):
                    rec["seat_pairs"] = []
                if "match" not in rec:
                    rec["match"] = "ok" if rec.get("barcodes") else "partial"
            matched = sum(1 for r in records if r.get("match") == "ok")
            partial = sum(1 for r in records if r.get("match") == "partial")
            no_match = sum(1 for r in records if r.get("match") == "no_db_match")
        _apply_valids(records, valids)
        company = "Cash Resale Tickets (Fouad Mahmoud)"
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        txt_path = out_dir / f"sf_unfulfilled_{stamp}.txt"
        js_path = out_dir / f"sf_unfulfilled_{stamp}.js"
        header = [
            f"# Stagefront unfulfilled · {datetime.now().isoformat(timespec='seconds')}",
            f"# company={company!r} · unfulfilled={len(records)} · valids={len(valids)}",
            "# PURCHASING_ACCOUNT on invoice line only when email is in valids.txt",
            "#",
            "# INVOICE_ID | PURCHASING_ACCOUNT",
            "# SEAT | BARCODE",
            "# ---",
            "",
        ]
        txt_path.write_text("\n".join(header + _format_export_blocks(records)), encoding="utf-8")
        js_export = _js_export_records(records)
        js_path.write_text(
            "module.exports = " + json.dumps(js_export, indent=2, ensure_ascii=False) + ";\n",
            encoding="utf-8",
        )
        ep_lines = sorted(
            {r["valid_cred"] for r in records if r.get("is_valid_account") and r.get("valid_cred")}
        )
        accounts_path = out_dir / f"sf_unfulfilled_{stamp}_accounts.txt"
        accounts_path.write_text("\n".join(ep_lines) + ("\n" if ep_lines else ""), encoding="utf-8")
        print(f"Rebuilt from {js_in.name} · valids in export: {len(ep_lines)}")
        print("Wrote:", txt_path)
        print("Wrote:", js_path)
        print("Wrote:", accounts_path)
        return 0

    if args.pull_stock:
        import subprocess

        deploy = ROOT / "deploy"
        subprocess.run(
            [sys.executable, str(deploy / "pull_tm_worker_collector.py"), "--skip-okaysec"],
            check=False,
            cwd=str(deploy),
        )
        subprocess.run(
            [
                sys.executable,
                str(deploy / "vl_bot_pull.py"),
                "data/vl_inventory.db",
                str(ROOT / "data" / "vl_inventory.db"),
            ],
            check=False,
            cwd=str(deploy),
        )

    print(f"Loading stock (--stock {args.stock})…")
    stock_df = _load_stock_df(args.stock)
    print(f"  stock rows: {len(stock_df)}")

    client = _connect_sf(args)
    company = client.resolve_company()
    print(f"Stagefront company: {company!r}")

    raw_sales = _fetch_sales(client, company)
    sales = _dedupe_sales(raw_sales)
    print(f"Sales pulled: {len(sales)} (raw {len(raw_sales)})")

    unfulfilled = [s for s in sales if _is_sale_unfulfilled(s)]
    print(f"Unfulfilled (no PDF/barcode / pending status): {len(unfulfilled)}")

    records: list[dict] = []
    matched = 0
    partial = 0
    no_match = 0

    for row in unfulfilled:
        meta = _sale_summary(row)
        email, password, seat_pairs, barcodes, note = _match_sale(stock_df, row)
        if note == "ok":
            matched += 1
        elif note == "partial":
            partial += 1
        else:
            no_match += 1
        cred = f"{email}:{password}" if email and password else (email or "")
        records.append(
            {
                "email": email,
                "password": password,
                "barcodes": barcodes,
                "seat_pairs": seat_pairs,
                "emailPassword": cred,
                **meta,
                "match": note,
            }
        )

    _apply_valids(records, valids)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_path = out_dir / f"sf_unfulfilled_{stamp}.txt"
    js_path = out_dir / f"sf_unfulfilled_{stamp}.js"

    header = [
        f"# Stagefront unfulfilled · {datetime.now().isoformat(timespec='seconds')}",
        f"# company={company!r} · unfulfilled={len(unfulfilled)} · valids={len(valids)}",
        "# PURCHASING_ACCOUNT on invoice line only when email is in valids.txt",
        "#",
        "# INVOICE_ID | PURCHASING_ACCOUNT",
        "# SEAT | BARCODE",
        "# ---",
        "",
    ]
    txt_path.write_text("\n".join(header + _format_export_blocks(records)), encoding="utf-8")

    js_export = _js_export_records(records)
    js_body = (
        "// Stagefront unfulfilled — valids.txt get emailPassword; others barcodes + seat_pairs only\n"
        f"// {matched}/{len(unfulfilled)} ok · {partial} partial · {no_match} no_db_match\n"
        "module.exports = "
        + json.dumps(js_export, indent=2, ensure_ascii=False)
        + ";\n"
    )
    js_path.write_text(js_body, encoding="utf-8")

    # Simple email:password list (one combo per line, for support / login)
    ep_lines = sorted(
        {r["valid_cred"] for r in records if r.get("is_valid_account") and r.get("valid_cred")}
    )
    accounts_path = out_dir / f"sf_unfulfilled_{stamp}_accounts.txt"
    accounts_path.write_text("\n".join(ep_lines) + ("\n" if ep_lines else ""), encoding="utf-8")

    print(f"ok={matched}/{len(unfulfilled)} · partial={partial} · no_db_match={no_match}")
    print("Wrote:", txt_path)
    print("Wrote:", js_path)
    print("Wrote:", accounts_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
