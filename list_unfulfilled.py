"""List unfulfilled Aug 21-31 orders: INVOICE | EMAIL:PASSWORD | BARCODES,BARCODES"""
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from fulfill_victory_live import (
    OKAYSEC_PATH,
    clean_barcode,
    clean_section,
    find_barcode,
    load_session,
    search_orders,
)
from vl_auth import APP_BASE

BASE = APP_BASE
OUT_PATH = Path(__file__).resolve().parent / "unfulfilled_aug21_31.txt"


def norm_bc(bc):
    if bc is None:
        return None
    return clean_barcode(str(bc).strip())


def section_variants(section):
    sc = clean_section(section)
    variants = {sc, sc.upper()}
    raw = str(section or "").strip().upper()
    if raw.startswith("SEC") and len(raw) > 3:
        variants.add(raw[3:])
    if sc.upper().startswith("C") and len(sc) > 1 and sc[1:].isdigit():
        variants.add(sc[1:])
    else:
        variants.add(f"C{sc}")
    # FLOOR4 vs FLOOR 4 / Upper Concourse 210 → 210
    m = re.match(r"^(\d+)$", sc)
    if m:
        variants.add(m.group(1))
    if re.match(r"^floor?\d+$", raw.replace(" ", "").lower()):
        variants.add(re.sub(r"^floor?", "", raw.replace(" ", ""), flags=re.I))
    for abbr, full in (
        ("BALC", "BALCONY"),
        ("BAL", "BALCONY"),
        ("ORCH", "ORCHESTRA"),
        ("ORCHESTRA", "ORCH"),
        ("FLR", "FLOOR"),
        ("FLOOR", "FLR"),
        ("MEZZ", "MEZZANINE"),
        ("MEZZANINE", "MEZZ"),
        ("LAWN", "LAWN"),
        ("PIT", "PIT"),
        ("GENADM", "GA"),
        ("GENADM", "GENADM"),
        ("GENERAL", "GA"),
        ("GAX1", "GA"),
        ("GAX1", "GAX1"),
        ("GA1", "GA"),
        ("GA01", "GA"),
        ("GA01", "GA1"),
        ("LAWN1", "LAWN"),
        ("LAWN1", "LAWN1"),
        ("LOGE", "LOGE"),
        ("RES", "RES"),
    ):
        if raw == abbr or sc.upper() == abbr:
            variants.add(clean_section(full))
            variants.add(clean_section(abbr))
    # TERR06 / TERR25 → also match numeric tail
    m_terr = re.match(r"^TERR(\d+)$", raw)
    if m_terr:
        variants.add(m_terr.group(1))
        variants.add(clean_section(raw))
    return variants


def parse_event_date(val):
    val = str(val).strip()
    for fmt in (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%b %d %Y",
        "%b %d, %Y",
    ):
        try:
            return datetime.strptime(val[:19] if "T" in fmt else val, fmt).date()
        except ValueError:
            continue
    if "T" in val:
        try:
            return datetime.fromisoformat(val.replace("Z", "")).date()
        except ValueError:
            pass
    return None


def prep_df(df):
    df = df.copy()
    df["_sec"] = df["Section"].astype(str).apply(clean_section)
    df["_row"] = df["Row"].astype(str).str.strip().str.upper()
    df["_seat"] = df["Seat"].astype(str).str.strip()
    df["_bc"] = df["Barcodes"].astype(str).str.strip().apply(norm_bc)
    df["_edate"] = df["Event Date"].apply(parse_event_date)
    df["_venue"] = df["Venue"].astype(str).str.lower()
    return df


def seat_match(df, section, row, seat, event_date=None, venue=None, event_name=None):
    seat_s = str(seat).strip()
    row_u = str(row).upper()
    variants = section_variants(section)

    mask = df["_sec"].isin(variants) & (df["_row"] == row_u) & (df["_seat"] == seat_s)
    hits = df[mask]
    if len(hits) == 0 and event_date is not None:
        # e.g. VL "BALC" vs DB "Balcony"
        hits = df[(df["_row"] == row_u) & (df["_seat"] == seat_s) & (df["_edate"] == event_date)]
    if len(hits) > 1 and "_fulfill_file" in hits.columns:
        ff = hits[hits["_fulfill_file"].fillna(0).astype(int) == 1]
        if len(ff) >= 1:
            hits = ff
    if len(hits) == 1:
        return hits.iloc[0]
    if len(hits) > 1 and event_name and "Event Name" in hits.columns:
        en = str(event_name).lower()
        if en:
            def _name_ok(val: object) -> bool:
                v = str(val or "").lower()
                if not v:
                    return False
                return en[:14] in v or v[:14] in en

            named = hits[hits["Event Name"].apply(_name_ok)]
            if len(named) == 1:
                return named.iloc[0]
            if len(named) > 1:
                hits = named
    if len(hits) > 1 and event_date is not None:
        dated = hits[hits["_edate"] == event_date]
        if len(dated) == 1:
            return dated.iloc[0]
        if len(dated) > 1:
            return dated.iloc[0]
    if len(hits) >= 1:
        if venue:
            v = venue.lower()
            for _, r in hits.iterrows():
                if v[:8] in r["_venue"] or r["_venue"][:8] in v:
                    return r
        return hits.iloc[0]
    return None


def lookup_okaysec(section, row, seat, df, order=None):
    event_date = parse_event_date(order.get("ProductionDateTime") or "") if order else None
    venue = order.get("VenueName") if order else None

    hit = seat_match(df, section, row, seat, event_date, venue)
    if hit is not None:
        return norm_bc(hit["Barcodes"]), hit["Email"], hit["Password"]

    bc, _ = find_barcode(section, row, seat, df)
    if bc:
        hits = df[df["_bc"] == norm_bc(bc)]
        if len(hits):
            r = hits.iloc[0]
            return norm_bc(r["Barcodes"]), r["Email"], r["Password"]

    # fuzzy: same venue + event date + row/seat, any section variant overlap
    if order and event_date and venue:
        v = venue.lower()
        fuzzy = df[
            (df["_edate"] == event_date)
            & (df["_row"] == str(row).upper())
            & (df["_seat"] == str(seat).strip())
            & df["_venue"].str.contains(v.split()[0][:6], na=False)
        ]
        if len(fuzzy):
            r = fuzzy.iloc[0]
            return norm_bc(r["Barcodes"]), r["Email"], r["Password"]
    return None, None, None


def is_unfulfilled(order, tickets):
    btn = order.get("ButtonToShow")
    status = (order.get("OrderStatus") or {}).get("Key")
    msg = (order.get("StatusMessage") or "").lower()
    if btn == "mobileTransfer" and status == "Fulfilled":
        return False
    if any(not t.get("Barcode") for t in tickets):
        return True
    if btn == "mobile":
        return True
    if "not matched" in msg or "unable to transfer" in msg or "purchase manag" in msg:
        return True
    return status != "Fulfilled"


def get_barcodes_and_creds(order, tickets, df):
    barcodes = []
    creds = []
    for t in tickets:
        sec = t.get("Section") or order.get("Section")
        row = t.get("Row") or order.get("Row")
        seat = t.get("Seat")

        ok_bc, email, password = lookup_okaysec(sec, row, seat, df, order)
        if ok_bc:
            bc = ok_bc
        elif t.get("Barcode"):
            bc = norm_bc(t.get("Barcode"))
            hits = df[df["_bc"] == bc]
            if len(hits):
                email, password = hits.iloc[0]["Email"], hits.iloc[0]["Password"]
        else:
            bc = None

        if bc:
            barcodes.append(str(bc))
        if email and password:
            creds.append(f"{email}:{password}")

    unique_creds = list(dict.fromkeys(creds))
    cred_str = unique_creds[0] if len(unique_creds) == 1 else (" / ".join(unique_creds) if unique_creds else "NO_MATCH")
    bc_str = ",".join(barcodes) if barcodes else "NO_BARCODES"
    return cred_str, bc_str


def main():
    session = load_session()
    session.headers["Accept"] = "application/json"
    df = prep_df(pd.read_csv(OKAYSEC_PATH, sep="\t", on_bad_lines="skip"))
    orders = search_orders(session)

    lines = []
    for o in orders:
        if not o.get("IsMobileEnabled"):
            continue
        rid = o["RexOrderId"]
        try:
            ma = session.get(
                f"{BASE}/api/orders/mobileAttributes",
                params={"sellOrderId": rid},
                timeout=20,
            ).json()["Data"]
        except Exception:
            continue
        tickets = ma.get("Tickets", [])
        if not tickets or not is_unfulfilled(o, tickets):
            continue

        inv = o.get("InvoiceNumber") or "N/A"
        cred_str, bc_str = get_barcodes_and_creds(o, tickets, df)
        lines.append(f"{inv} | {cred_str} | {bc_str}")

    lines.sort(key=lambda x: x.split(" | ", 1)[0])
    text = "\n".join(lines)
    OUT_PATH.write_text(text + ("\n" if text else ""), encoding="utf-8")
    print(f"Unfulfilled orders: {len(lines)}\n")
    print(text)


if __name__ == "__main__":
    main()
