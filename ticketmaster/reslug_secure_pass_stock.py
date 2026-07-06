#!/usr/bin/env python3
"""
Reslug ALL tm-vercel-site pass HTML files (rotate slug; old link → invalidation page).

Also updates secure_pass_stock.csv + all links.txt / links files (every URL on each line).
Writes full map + updated stock lines to timestamped .txt files.

Skips:
  - sold_secure.txt / sold.txt / archive (stubby sold)
  - exceptions / exceptions.txt (leave those slugs untouched)
  - Already-invalidated stub HTML pages

Default: DRY RUN. Pass --confirm to apply.

Usage (from tm.bz):
  python reslug_secure_pass_stock.py
  python reslug_secure_pass_stock.py --confirm
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Import shared reslug helpers (same module as PDF reslug flow)
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from reslug_tickets import (  # noqa: E402
    INVALIDATED_LINK_MESSAGE,
    new_slug,
    parse_links_line,
    rebuild_links_line,
    rotate_slug_html_files,
    _RE_VIEWER_URL,
    _slug_from_url_str,
)

_PUBLIC_GATEWAYS = ("https://tixx.cc", "https://tixx.pw", "https://tixx.lol")
_PUBLIC_BASE = (
    __import__("os").environ.get("TM_VIEWER_PUBLIC_BASE")
    or __import__("os").environ.get("TM_VIEWER_GATEWAY_PUBLIC_BASE")
    or __import__("os").environ.get("TM_VIEWER_SITE_ORIGIN")
    or "https://tixx.cc"
).rstrip("/")
# Stock CSV often has …/slug,TM (comma before TM column bleeds into URL regex).
_SLUG_TAIL = r"(?:\.html)?(?:,TM|,tm)?"


@dataclass(frozen=True)
class StubbyLayout:
    """stubhub data root + tm.bz ops folder (VPS layout)."""
    root: Path          # CLI --stubby-dir / cwd
    data_dir: Path      # secure_pass_stock, sold_*, exceptions
    site_dir: Path      # links, deliveries, tm-vercel-site parent
    stock_path: Path
    vercel_site: Path


def _count_nonempty_lines(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        return sum(1 for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip())
    except OSError:
        return 0


def resolve_stubby_layout(root: Path, script_dir: Path) -> StubbyLayout:
    """
    VPS: tm.bz holds passes/links; parent stubhub holds bot stock + sold logs.
    Works when root is tm.bz, stubhub, or script_dir (tm.bz copy).
    """
    root = root.resolve()
    script_dir = script_dir.resolve()

    # Prefer script location when it is the tm.bz ops folder.
    if (script_dir / "tm-vercel-site" / "tickets").is_dir():
        site_dir = script_dir
        data_dir = script_dir.parent
    elif (root / "tm-vercel-site" / "tickets").is_dir():
        site_dir = root
        data_dir = root.parent
    elif (root / "tm.bz" / "tm-vercel-site" / "tickets").is_dir():
        data_dir = root
        site_dir = root / "tm.bz"
    else:
        site_dir = root
        data_dir = root

    vercel_site = site_dir / "tm-vercel-site"
    if not vercel_site.is_dir():
        for cand in (
            root / "tm-vercel-site",
            root / "tm.bz" / "tm-vercel-site",
            script_dir / "tm-vercel-site",
            data_dir / "tm.bz" / "tm-vercel-site",
        ):
            if cand.is_dir() and (cand / "tickets").is_dir():
                vercel_site = cand
                site_dir = cand.parent
                break

    parent_stock = data_dir / "secure_pass_stock.csv"
    site_stock = site_dir / "secure_pass_stock.csv"
    if parent_stock.is_file() and site_stock.is_file():
        # Bot stock is almost always the larger file at stubhub root.
        stock_path = parent_stock if _count_nonempty_lines(parent_stock) >= _count_nonempty_lines(site_stock) else site_stock
    elif parent_stock.is_file():
        stock_path = parent_stock
    elif site_stock.is_file():
        stock_path = site_stock
    else:
        stock_path = parent_stock

    return StubbyLayout(
        root=root,
        data_dir=data_dir,
        site_dir=site_dir,
        stock_path=stock_path,
        vercel_site=vercel_site,
    )


_DEFAULT_STUBBY_CANDIDATES = [
    Path(__import__("os").environ.get("STUBBY_BASE_DIR", "").strip() or ""),
    Path(r"C:\Users\Administrator\Desktop\Stubhub\stubhub"),
    _SCRIPT_DIR.parent,
]


def _default_stubby_dir() -> Path:
    # Script copied into tm.bz on VPS → default to that folder.
    if (_SCRIPT_DIR / "tm-vercel-site").is_dir():
        return _SCRIPT_DIR
    for cand in _DEFAULT_STUBBY_CANDIDATES:
        if not cand:
            continue
        tm_bz = cand / "tm.bz"
        if tm_bz.is_dir() and (tm_bz / "tm-vercel-site").is_dir():
            return tm_bz
        if cand.is_dir():
            return cand
    return _SCRIPT_DIR


@dataclass
class LinksFileBundle:
    path: Path
    lines: list[str]
    slug_idx: dict[str, list[int]]


def find_all_stock_files(site_dir: Path, data_dir: Path) -> list[Path]:
    """Every secure_pass_stock.csv under stubhub + tm.bz (deduped)."""
    seen: set[str] = set()
    out: list[Path] = []
    for p in (
        data_dir / "secure_pass_stock.csv",
        site_dir / "secure_pass_stock.csv",
    ):
        if not p.is_file():
            continue
        key = str(p.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def find_all_links_files(site_dir: Path, data_dir: Path) -> list[Path]:
    """Every links / links.txt under tm.bz and stubhub (deduped)."""
    seen: set[str] = set()
    out: list[Path] = []
    for p in (
        site_dir / "links",
        site_dir / "links.txt",
        data_dir / "links",
        data_dir / "links.txt",
    ):
        if not p.is_file():
            continue
        key = str(p.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def load_links_bundle(path: Path) -> LinksFileBundle:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    return LinksFileBundle(path=path, lines=lines, slug_idx=index_lines_by_slug(lines))


def find_links_file(site_dir: Path) -> Path | None:
    for cand in (site_dir / "links", site_dir / "links.txt"):
        if cand.is_file():
            return cand
    return None


def find_deliveries_jsonl(site_dir: Path, vercel_site: Path) -> Path | None:
    for cand in (
        site_dir / "tm_viewer_deliveries.jsonl",
        vercel_site.parent / "tm_viewer_deliveries.jsonl",
    ):
        if cand.is_file():
            return cand
    return None

_TIXX_HOST_RE = re.compile(r"https?://(?:tixx\.cc|tixx\.pw|tixx\.lol)/tickets/", re.I)


def _extract_urls(text: str) -> set[str]:
    out: set[str] = set()
    for m in _RE_VIEWER_URL.finditer(text):
        u = m.group(0).rstrip(".,)")
        u = re.sub(r"\.html$", "", u, flags=re.I)
        out.add(u)
    return out


def load_sold_url_set(stubby_dir: Path) -> set[str]:
    sold: set[str] = set()
    for name in ("sold_secure.txt", "sold.txt", "securetemp.txt"):
        p = stubby_dir / name
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        sold |= _extract_urls(text)
        # sold_secure also embeds full stock lines — keep substring slug match via URLs
    archive = stubby_dir / "secure_pass_email_archive.jsonl"
    if archive.is_file():
        try:
            for line in archive.read_text(encoding="utf-8", errors="replace").splitlines():
                sold |= _extract_urls(line)
        except OSError:
            pass
    return sold


def load_exceptions(data_dir: Path, site_dir: Path, script_dir: Path) -> list[str]:
    rules: list[str] = []
    seen: set[str] = set()
    for p in (
        data_dir / "exceptions",
        data_dir / "exceptions.txt",
        site_dir / "exceptions",
        site_dir / "exceptions.txt",
        script_dir / "exceptions",
        script_dir / "exceptions.txt",
    ):
        key = str(p.resolve()).lower()
        if key in seen or not p.is_file():
            continue
        seen.add(key)
        try:
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                rules.append(s)
        except OSError:
            continue
    return rules


def public_ticket_urls(gid: str, slug: str) -> list[str]:
    return [f"{base}/tickets/{gid}/{slug}" for base in _PUBLIC_GATEWAYS]


def is_invalidated_pass_html(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            chunk = fh.read(4096)
    except OSError:
        return True
    low = chunk.lower()
    return (
        "link invalidated" in low
        or "this link is no longer valid" in low
        or "your barcode has been killed" in low
        or "cancelled our parternship" in low
        or INVALIDATED_LINK_MESSAGE[:40].lower() in low
    )


def iter_live_pass_html(vercel_site: Path) -> list[tuple[str, str, Path]]:
    """(gid, slug, html_path) for every pass file under tickets/."""
    root = vercel_site / "tickets"
    if not root.is_dir():
        return []
    found: list[tuple[str, str, Path]] = []
    for gid_dir in sorted(root.iterdir(), key=lambda p: p.name):
        if not gid_dir.is_dir():
            continue
        gid = gid_dir.name
        for html in sorted(gid_dir.glob("*.html")):
            if html.name.startswith("."):
                continue
            found.append((gid, html.stem, html))
    return found


def normalize_slug(slug: str) -> str:
    s = (slug or "").strip().rstrip(".,)")
    if s.upper().endswith(",TM"):
        s = s[:-3].rstrip()
    return s


def slug_gid_from_url(url: str) -> tuple[str, str] | None:
    pair = _slug_from_url_str(url)
    if not pair:
        return None
    gid, slug = pair
    return gid, normalize_slug(slug)


def canonical_ticket_url(gid: str, slug: str) -> str:
    return f"{_PUBLIC_BASE}/tickets/{gid}/{slug}"


def index_lines_by_slug(lines: list[str]) -> dict[str, list[int]]:
    idx_map: dict[str, list[int]] = {}
    for idx, line in enumerate(lines):
        for url in _extract_urls(line):
            pair = slug_gid_from_url(url)
            if pair:
                _, slug = pair
                idx_map.setdefault(slug, []).append(idx)
                # Also index raw slug if regex captured ,TM suffix.
                raw = _slug_from_url_str(url)
                if raw and raw[1] != slug:
                    idx_map.setdefault(raw[1], []).append(idx)
    return idx_map


def matches_skip_rule(
    slug: str,
    gid: str,
    rules: list[str],
    *,
    extra_text: str = "",
) -> str | None:
    blob = f"{extra_text} {gid} {slug} ".lower()
    urls = " ".join(public_ticket_urls(gid, slug)).lower()
    slug_l = slug.lower()
    for rule in rules:
        r = rule.strip()
        if not r:
            continue
        rl = r.lower()
        if rl == slug_l or rl in blob or rl in urls:
            return r
    return None


def slug_marked_sold(gid: str, slug: str, sold_urls: set[str]) -> bool:
    for u in public_ticket_urls(gid, slug):
        if u in sold_urls:
            return True
    return slug in sold_urls


def replace_slug_in_text(text: str, gid: str, old_slug: str, new_slug_val: str) -> str:
    """Replace every tickets/<gid>/<old_slug> URL or path segment in text."""
    old_slug = normalize_slug(old_slug)
    if old_slug not in text:
        return text
    gid_esc = re.escape(gid)
    old_esc = re.escape(old_slug)
    tail = _SLUG_TAIL
    before = text
    text = re.sub(
        rf"(https?://[^\s\"'<>\[\]]+/tickets/{gid_esc}/){old_esc}{tail}",
        rf"\g<1>{new_slug_val}",
        text,
        flags=re.I,
    )
    text = re.sub(
        rf"/tickets/{gid_esc}/{old_esc}{tail}",
        f"/tickets/{gid}/{new_slug_val}",
        text,
        flags=re.I,
    )
    if text == before:
        # Stock URL gid may differ from HTML folder gid — still replace matching slug.
        text = re.sub(
            rf"(https?://[^\s\"'<>\[\]]+/tickets/\d+/){old_esc}{tail}",
            rf"\g<1>{new_slug_val}",
            text,
            flags=re.I,
        )
        text = re.sub(
            rf"/tickets/\d+/{old_esc}{tail}",
            lambda m: re.sub(old_esc, new_slug_val, m.group(0), count=1, flags=re.I),
            text,
            flags=re.I,
        )
    return text


def line_contains_ticket_slug(line: str, gid: str, old_slug: str) -> bool:
    old_slug = normalize_slug(old_slug)
    if old_slug not in line:
        return False
    if re.search(
        rf"/tickets/{re.escape(gid)}/{re.escape(old_slug)}{_SLUG_TAIL}",
        line,
        re.I,
    ):
        return True
    return bool(
        re.search(
            rf"/tickets/\d+/{re.escape(old_slug)}{_SLUG_TAIL}",
            line,
            re.I,
        )
    )


def line_idxs_for_slug(
    lines: list[str],
    gid: str,
    old_slug: str,
    slug_idx: dict[str, list[int]],
) -> list[int]:
    old_slug = normalize_slug(old_slug)
    found: set[int] = set(slug_idx.get(old_slug, []))
    for idx, line in enumerate(lines):
        if line_contains_ticket_slug(line, gid, old_slug):
            found.add(idx)
    return sorted(found)


def apply_slug_to_line(line: str, gid: str, old_slug: str, new_slug_val: str) -> str:
    """Rewrite one stock/links line — every embedded ticket URL gets the new slug."""
    old_slug = normalize_slug(old_slug)
    if not line_contains_ticket_slug(line, gid, old_slug):
        return line
    if line.endswith("\r\n"):
        ending, core = "\r\n", line[:-2]
    elif line.endswith("\n"):
        ending, core = "\n", line[:-1]
    else:
        ending, core = "", line
    stripped = core.strip()
    parsed = parse_links_line(stripped)
    new_canonical = canonical_ticket_url(gid, new_slug_val)
    if parsed:
        new_link = replace_slug_in_text(parsed.get("link") or "", gid, old_slug, new_slug_val)
        if not new_link.startswith("http"):
            new_link = new_canonical
        elif _PUBLIC_BASE.lower() not in new_link.lower():
            new_link = new_canonical
        core = replace_slug_in_text(
            rebuild_links_line(parsed, new_link).rstrip("\n"),
            gid,
            old_slug,
            new_slug_val,
        )
    else:
        core = replace_slug_in_text(core, gid, old_slug, new_slug_val)
    core = replace_slug_in_text(core, gid, old_slug, new_slug_val)
    return core + ending


def update_generate_out_data(
    data: dict,
    gid: str,
    old_slug: str,
    new_slug_val: str,
) -> int:
    stock_lines = data.get("stock_lines")
    if not isinstance(stock_lines, list):
        return 0
    changed = 0
    for i, item in enumerate(stock_lines):
        if not isinstance(item, str):
            continue
        updated = apply_slug_to_line(item + "\n", gid, old_slug, new_slug_val).rstrip("\n")
        if updated != item:
            stock_lines[i] = updated
            changed += 1
    return changed


def write_full_map(
    path: Path,
    jobs: list,
    skipped_log: list[str],
    data_dir: Path,
    site_dir: Path,
    confirm: bool,
) -> None:
    with path.open("w", encoding="utf-8") as fh:
        fh.write(f"reslug_full_map @ {datetime.now().isoformat()}\n")
        fh.write(f"data_dir={data_dir}\n")
        fh.write(f"site_dir={site_dir}\n")
        fh.write(f"html_jobs={len(jobs)} confirm={confirm}\n\n")
        if skipped_log:
            fh.write("=== SKIPPED (unchanged) ===\n")
            for line in skipped_log:
                fh.write(line + "\n")
            fh.write("\n")
        fh.write("=== RESLUGGED ===\n")
        for j in jobs:
            fh.write(f"RESLUG {j.old_slug} -> {j.new_slug}\n")
            fh.write(f"  OLD {j.old_url}\n")
            fh.write(f"  NEW {j.new_url}\n")
            fh.write(f"  HTML tickets/{j.gid}/{j.old_slug}.html\n")


def replace_slug_in_url(url: str, gid: str, old_slug: str, new_slug_val: str) -> str:
    return replace_slug_in_text(url, gid, old_slug, new_slug_val)


@dataclass(frozen=True)
class SlugMapEntry:
    gid: str
    old_slug: str
    new_slug: str
    old_url: str
    new_url: str


def filter_slug_map_by_local_html(
    vercel_site: Path,
    by_slug: dict[str, SlugMapEntry],
) -> tuple[dict[str, SlugMapEntry], int]:
    """Keep only mappings whose new slug has a live pass file on this machine."""
    if not vercel_site.is_dir():
        return by_slug, 0
    kept: dict[str, SlugMapEntry] = {}
    skipped = 0
    for old, entry in by_slug.items():
        new_path = vercel_site / "tickets" / entry.gid / f"{entry.new_slug}.html"
        if not new_path.is_file() or is_invalidated_pass_html(new_path):
            skipped += 1
            continue
        kept[old] = entry
    return kept, skipped


def batch_sync_lines_with_map(
    lines: list[str],
    by_slug: dict[str, SlugMapEntry],
) -> tuple[list[str], int, list[str], int]:
    """One pass per line: replace mapped slugs. Never removes lines — unchanged lines stay as-is."""
    out: list[str] = []
    changed_lines: list[str] = []
    hits = 0
    skipped_slug_hits = 0
    for line in lines:
        nl = line
        touched: set[str] = set()
        for url in _extract_urls(line):
            pair = slug_gid_from_url(url)
            if not pair:
                continue
            _, slug = pair
            if slug in touched:
                continue
            entry = by_slug.get(slug)
            if not entry:
                if slug:  # URL in line but not in allowed map
                    skipped_slug_hits += 1
                continue
            touched.add(slug)
            nl = apply_slug_to_line(nl, entry.gid, entry.old_slug, entry.new_slug)
        if nl != line:
            hits += 1
            changed_lines.append(nl.rstrip("\n"))
        out.append(nl)
    return out, hits, changed_lines, skipped_slug_hits


def jobs_to_slug_map(jobs: list) -> dict[str, SlugMapEntry]:
    m: dict[str, SlugMapEntry] = {}
    for j in jobs:
        old = normalize_slug(j.old_slug)
        m[old] = SlugMapEntry(
            gid=j.gid,
            old_slug=old,
            new_slug=j.new_slug,
            old_url=j.old_url,
            new_url=j.new_url,
        )
    return m


def entries_to_slug_map(entries: list[SlugMapEntry]) -> dict[str, SlugMapEntry]:
    m: dict[str, SlugMapEntry] = {}
    for e in entries:
        m[normalize_slug(e.old_slug)] = e
    return m


def parse_reslug_map(path: Path) -> list[SlugMapEntry]:
    entries: list[SlugMapEntry] = []
    cur_old_slug = ""
    cur_new_slug = ""
    cur_gid = ""
    cur_old_url = ""
    cur_new_url = ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return entries
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("RESLUG ") and " -> " in s:
            part = s[7:].strip()
            cur_old_slug, cur_new_slug = part.split(" -> ", 1)
            cur_old_slug = normalize_slug(cur_old_slug.strip())
            cur_new_slug = normalize_slug(cur_new_slug.strip())
        elif s.startswith("OLD "):
            cur_old_url = s[4:].strip()
            pair = slug_gid_from_url(cur_old_url)
            if pair:
                cur_gid, cur_old_slug = pair
        elif s.startswith("NEW "):
            cur_new_url = s[4:].strip()
            pair = slug_gid_from_url(cur_new_url)
            if pair:
                cur_gid, cur_new_slug = pair
            if cur_old_slug and cur_new_slug and cur_gid:
                entries.append(
                    SlugMapEntry(
                        gid=cur_gid,
                        old_slug=cur_old_slug,
                        new_slug=cur_new_slug,
                        old_url=cur_old_url.rstrip("/"),
                        new_url=cur_new_url.rstrip("/") or canonical_ticket_url(cur_gid, cur_new_slug),
                    )
                )
    return entries


def find_latest_reslug_map(site_dir: Path) -> Path | None:
    maps = sorted(site_dir.glob("reslug_full_map_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    return maps[0] if maps else None


def repair_stock_and_links(
    layout: StubbyLayout,
    map_path: Path,
    *,
    confirm: bool,
    no_backup: bool,
    require_local_html: bool = True,
) -> None:
    entries = parse_reslug_map(map_path)
    if not entries:
        sys.exit(f"[!] No RESLUG entries parsed from {map_path}")

    stock_path = layout.stock_path
    data_dir = layout.data_dir
    site_dir = layout.site_dir
    vercel_site = layout.vercel_site
    stock_files = find_all_stock_files(site_dir, data_dir)
    if not stock_files:
        stock_files = [stock_path]

    links_bundles: list[LinksFileBundle] = []
    for lp in find_all_links_files(site_dir, data_dir):
        links_bundles.append(load_links_bundle(lp))

    by_slug = entries_to_slug_map(entries)
    skipped_no_html = 0
    if require_local_html:
        by_slug, skipped_no_html = filter_slug_map_by_local_html(vercel_site, by_slug)

    print(f"[*] Repair from map : {map_path}")
    print(f"[*] Map entries     : {len(entries)}")
    if require_local_html:
        print(f"[*] Local new HTML  : {len(by_slug)} (skipped {skipped_no_html} — no live pass on this machine)")
        print(f"[*] Safety          : stock lines are NEVER deleted; unmapped slugs stay unchanged")
    else:
        print(f"[!] --repair-ignore-local-html: updating from map without checking pass files")
    for sf in stock_files:
        nlines = 0
        if sf.is_file():
            nlines = sum(1 for ln in sf.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip())
        print(f"[*] Stock file      : {sf} ({nlines} lines)")
    for b in links_bundles:
        print(f"[*] Links file      : {b.path} ({len(b.lines)} lines)")

    stock_bundles: list[tuple[Path, list[str], int, list[str]]] = []
    total_stock_hits = 0
    total_unchanged_with_old_slug = 0
    for sf in stock_files:
        if not sf.is_file():
            continue
        lines = sf.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        new_lines, hits, changed, _skip = batch_sync_lines_with_map(lines, by_slug)
        unchanged = len(lines) - hits
        stock_bundles.append((sf, new_lines, hits, changed))
        total_stock_hits += hits
        total_unchanged_with_old_slug += unchanged
        print(f"    {sf.name}: {hits} line(s) to update, {unchanged} left unchanged")

    links_hits = 0
    updated_links: list[str] = []
    for bundle in links_bundles:
        new_lines, hits, changed, _skip = batch_sync_lines_with_map(bundle.lines, by_slug)
        bundle.lines = new_lines
        links_hits += hits
        for c in changed:
            updated_links.append(f"{bundle.path.name}: {c}")

    print(f"\n[*] Total stock lines to update : {total_stock_hits}")
    print(f"[*] Total stock lines unchanged : {total_unchanged_with_old_slug} (kept as-is, not removed)")
    print(f"[*] Total links lines to update : {links_hits}")

    if not confirm:
        print("\n[*] Dry run — re-run with --confirm --repair-stock to apply.")
        return

    if not no_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        for sf, _, _, _ in stock_bundles:
            shutil.copy2(sf, sf.with_suffix(f".csv.bak_repair_{ts}"))
        for b in links_bundles:
            shutil.copy2(b.path, b.path.parent / f"{b.path.name}.bak_repair_{ts}")

    all_changed_stock: list[str] = []
    for sf, new_lines, _, changed in stock_bundles:
        sf.write_text("".join(new_lines), encoding="utf-8")
        all_changed_stock.extend(changed)
        print(f"[+] Stock repaired : {sf}")
    for b in links_bundles:
        b.path.write_text("".join(b.lines), encoding="utf-8")
        print(f"[+] Links repaired : {b.path}")

    out = site_dir / f"repair_stock_lines_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    out.write_text(
        "\n".join(all_changed_stock) if all_changed_stock else "(no stock lines changed)",
        encoding="utf-8",
    )
    print(f"[+] Log            : {out}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Reslug all tm-vercel-site pass HTML + sync secure_pass_stock.csv"
    )
    ap.add_argument(
        "--stubby-dir",
        type=Path,
        default=_default_stubby_dir(),
        help="tm.bz folder (default: script dir or auto-detected tm.bz)",
    )
    ap.add_argument("--vercel-site", type=Path, default=None, help="Override tm-vercel-site path")
    ap.add_argument("--links-file", type=Path, default=None, help="Optional links.txt to sync")
    ap.add_argument(
        "--confirm",
        action="store_true",
        help="Apply changes (default is dry-run only)",
    )
    ap.add_argument("--no-backup", action="store_true", help="Skip .bak backup of stock CSV")
    ap.add_argument(
        "--repair-stock",
        nargs="?",
        const="auto",
        default=None,
        metavar="MAP_TXT",
        help="Fix stock/links URLs from reslug_full_map (HTML already reslugged). Use latest map or path.",
    )
    ap.add_argument(
        "--repair-ignore-local-html",
        action="store_true",
        help="With --repair-stock: update stock even if new pass HTML is missing locally (default: skip those)",
    )
    ap.add_argument(
        "--skip-barcode-backfill",
        action="store_true",
        help="After reslug: do not scrape pass HTML for barcodes into stock CSV",
    )
    ap.add_argument(
        "--barcode-backfill-only",
        action="store_true",
        help="Only inject barcodes + normalize tixx.cc URLs in stock CSV (no HTML reslug)",
    )
    args = ap.parse_args()

    layout = resolve_stubby_layout(args.stubby_dir.expanduser(), _SCRIPT_DIR)
    if args.vercel_site:
        layout = StubbyLayout(
            root=layout.root,
            data_dir=layout.data_dir,
            site_dir=layout.site_dir,
            stock_path=layout.stock_path,
            vercel_site=args.vercel_site.expanduser().resolve(),
        )

    if args.barcode_backfill_only:
        _run_barcode_backfill(layout, confirm=args.confirm, no_backup=args.no_backup)
        return

    if args.repair_stock is not None:
        if args.repair_stock == "auto":
            map_path = find_latest_reslug_map(layout.site_dir)
            if not map_path:
                sys.exit("[!] No reslug_full_map_*.txt in tm.bz — pass path to --repair-stock")
        else:
            map_path = Path(args.repair_stock).expanduser().resolve()
        repair_stock_and_links(
            layout,
            map_path,
            confirm=args.confirm,
            no_backup=args.no_backup,
            require_local_html=not args.repair_ignore_local_html,
        )
        return

    stock_path = layout.stock_path
    raw_lines: list[str] = []
    if stock_path.is_file():
        raw_lines = stock_path.read_text(encoding="utf-8", errors="replace").splitlines(
            keepends=True
        )
    else:
        print(f"[!] No stock CSV at {stock_path} — will still reslug HTML passes")

    vercel_site = layout.vercel_site
    if not vercel_site.is_dir() or not (vercel_site / "tickets").is_dir():
        sys.exit(f"[!] tm-vercel-site not found: {vercel_site}")

    data_dir = layout.data_dir
    site_dir = layout.site_dir

    links_bundles: list[LinksFileBundle] = []
    if args.links_file:
        lp = args.links_file.expanduser().resolve()
        if lp.is_file():
            links_bundles.append(load_links_bundle(lp))
    else:
        for lp in find_all_links_files(site_dir, data_dir):
            links_bundles.append(load_links_bundle(lp))

    stock_slug_idx = index_lines_by_slug(raw_lines)

    sold_urls = load_sold_url_set(data_dir)
    exc_rules = load_exceptions(data_dir, site_dir, _SCRIPT_DIR)
    exc_path = next(
        (p for p in (
            site_dir / "exceptions",
            site_dir / "exceptions.txt",
            data_dir / "exceptions",
            data_dir / "exceptions.txt",
        ) if p.is_file()),
        None,
    )
    print(f"[*] Run from         : {layout.root}")
    print(f"[*] Data dir (stock) : {data_dir}")
    print(f"[*] Site dir (tm.bz) : {site_dir}")
    print(f"[*] Stock file       : {stock_path} ({len(raw_lines)} lines)")
    print(f"[*] Vercel site      : {vercel_site}")
    print(f"[*] Sold URL guard   : {len(sold_urls)} URL(s)")
    print(f"[*] Exceptions file  : {exc_path or '(none)'} ({len(exc_rules)} rules)")
    if links_bundles:
        for b in links_bundles:
            print(f"[*] links file       : {b.path} ({len(b.lines)} lines)")
    else:
        print("[*] links file       : (none found)")

    generate_out_paths: list[Path] = []
    for cand in (site_dir / "generate_out.json", data_dir / "generate_out.json"):
        if cand.is_file() and cand not in generate_out_paths:
            generate_out_paths.append(cand)
    if generate_out_paths:
        print(f"[*] generate_out     : {', '.join(str(p) for p in generate_out_paths)}")

    all_html = iter_live_pass_html(vercel_site)
    print(f"[*] HTML passes found: {len(all_html)}")

    deliveries_jsonl = find_deliveries_jsonl(site_dir, vercel_site)
    if deliveries_jsonl:
        print(f"[*] deliveries       : {deliveries_jsonl}")
    reg_path = vercel_site / "tm_viewer_link_registry.json"

    class Job:
        __slots__ = (
            "gid",
            "old_slug",
            "new_slug",
            "old_url",
            "new_url",
            "html_path",
            "stock_idxs",
            "links_idxs",
        )

    jobs: list[Job] = []
    skip_sold = 0
    skip_exc = 0
    skip_already_invalid = 0
    skipped_log: list[str] = []
    html_total = len(all_html)
    scan_start = time.monotonic()

    for i, (gid, old_slug, html_path) in enumerate(all_html):
        if i and i % 5000 == 0:
            elapsed = time.monotonic() - scan_start
            print(f"  ... scanned {i}/{html_total} HTML ({elapsed:.0f}s)")

        if is_invalidated_pass_html(html_path):
            skip_already_invalid += 1
            if skip_already_invalid <= 200:
                skipped_log.append(f"SKIP already-invalidated | tickets/{gid}/{old_slug}.html")
            continue

        if slug_marked_sold(gid, old_slug, sold_urls):
            skip_sold += 1
            if skip_sold <= 200:
                skipped_log.append(f"SKIP sold | {old_slug} | tickets/{gid}/{old_slug}.html")
            continue

        exc = matches_skip_rule(old_slug, gid, exc_rules)
        if exc:
            skip_exc += 1
            if skip_exc <= 200:
                skipped_log.append(f"SKIP exception ({exc}) | {old_slug} | tickets/{gid}/{old_slug}.html")
            continue

        ns = new_slug()
        while (vercel_site / "tickets" / gid / f"{ns}.html").exists():
            ns = new_slug()

        old_url = f"https://tixx.cc/tickets/{gid}/{old_slug}"
        new_url = f"https://tixx.cc/tickets/{gid}/{ns}"

        j = Job()
        j.gid = gid
        j.old_slug = old_slug
        j.new_slug = ns
        j.old_url = old_url
        j.new_url = new_url
        j.html_path = html_path
        j.stock_idxs = line_idxs_for_slug(raw_lines, gid, old_slug, stock_slug_idx)
        j.links_idxs = {
            b.path: line_idxs_for_slug(b.lines, gid, old_slug, b.slug_idx)
            for b in links_bundles
        }
        jobs.append(j)

    print(f"  HTML scan done in {time.monotonic() - scan_start:.0f}s")

    print(f"\n[*] Plan: {len(jobs)} HTML pass(es) to reslug")
    print(f"    skip exceptions (left as-is) : {skip_exc}")
    print(f"    skip sold/archive            : {skip_sold}")
    print(f"    skip already invalidated     : {skip_already_invalid}")
    stock_lines_hit = sum(
        len(line_idxs_for_slug(raw_lines, j.gid, j.old_slug, stock_slug_idx)) for j in jobs
    )
    links_lines_hit = sum(
        sum(len(line_idxs_for_slug(b.lines, j.gid, j.old_slug, b.slug_idx)) for b in links_bundles)
        for j in jobs
    )
    print(f"    stock lines to update        : {stock_lines_hit}")
    print(f"    links lines to update        : {links_lines_hit}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    map_path = site_dir / f"reslug_full_map_{ts}.txt"
    stock_out_path = site_dir / f"reslug_updated_stock_lines_{ts}.txt"
    links_out_path = site_dir / f"reslug_updated_links_lines_{ts}.txt"
    report_path = data_dir / f"reslug_report_{ts}.txt"

    if not jobs:
        print("\n[*] Nothing to reslug.")
        write_full_map(report_path, jobs, skipped_log, data_dir, site_dir, args.confirm)
        print(f"[*] Report: {report_path}")
        if not args.skip_barcode_backfill:
            _run_barcode_backfill(layout, confirm=args.confirm, no_backup=args.no_backup)
        return

    preview_n = min(20, len(jobs))
    print(f"\n[{'DRY RUN' if not args.confirm else 'APPLY'}] First {preview_n}:\n")
    for j in jobs[:preview_n]:
        print(f"  {j.old_slug} → {j.new_slug}  (stock lines: {len(j.stock_idxs)})")
        print(f"    {j.old_url}")
        print(f"    {j.new_url}")

    if len(jobs) > preview_n:
        print(f"  ... and {len(jobs) - preview_n} more")

    print(f"\n[*] Writing full map ({len(jobs)} jobs) → {map_path.name} ...")
    write_full_map(map_path, jobs, skipped_log, data_dir, site_dir, args.confirm)
    shutil.copy2(map_path, report_path)

    if not args.confirm:
        print("\n[*] Dry run — no files modified.")
        print("    Re-run with --confirm to apply.")
        print(f"[*] Map:    {map_path}")
        print(f"[*] Report: {report_path}")
        _apply_reslug_transfer_state(layout, jobs, confirm=False)
        if not args.skip_barcode_backfill:
            _run_barcode_backfill(layout, confirm=False, no_backup=args.no_backup)
        return

    if not args.no_backup:
        bak_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if stock_path.is_file():
            shutil.copy2(stock_path, stock_path.with_suffix(f".csv.bak_{bak_ts}"))
        for b in links_bundles:
            shutil.copy2(b.path, b.path.parent / f"{b.path.name}.bak_{bak_ts}")
        for gp in generate_out_paths:
            shutil.copy2(gp, gp.with_name(f"generate_out.json.bak_{bak_ts}"))
        if reg_path.is_file():
            shutil.copy2(reg_path, reg_path.with_name(f"tm_viewer_link_registry.json.bak_{bak_ts}"))

    new_stock_lines = list(raw_lines)
    updated_stock_lines: list[str] = []
    updated_links_lines: list[str] = []
    ok = 0
    fail = 0

    # Load sidecar files once (not per job — that was the 1-hour bottleneck).
    reg_text: str | None = None
    if reg_path.is_file():
        reg_text = reg_path.read_text(encoding="utf-8", errors="replace")

    deliveries_lines: list[str] | None = None
    if deliveries_jsonl and deliveries_jsonl.is_file():
        deliveries_lines = deliveries_jsonl.read_text(encoding="utf-8", errors="replace").splitlines(
            keepends=True
        )

    gen_out_data: dict[Path, dict] = {}
    for gp in generate_out_paths:
        try:
            gen_out_data[gp] = json.loads(gp.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            pass

    apply_start = time.monotonic()
    job_total = len(jobs)
    print(f"\n[*] Applying {job_total} reslugs (HTML + batch text updates)...")

    for i, j in enumerate(jobs):
        if i and i % 500 == 0:
            elapsed = time.monotonic() - apply_start
            rate = i / elapsed if elapsed > 0 else 0
            eta = (job_total - i) / rate if rate > 0 else 0
            print(f"  ... {i}/{job_total} ({elapsed:.0f}s elapsed, ~{eta:.0f}s left)")

        try:
            rotate_slug_html_files(j.html_path, j.old_slug, j.new_slug)

            if reg_text is not None:
                old_path = f"tickets/{j.gid}/{j.old_slug}.html"
                new_path = f"tickets/{j.gid}/{j.new_slug}.html"
                reg_text = reg_text.replace(old_path, new_path)
                reg_text = replace_slug_in_text(reg_text, j.gid, j.old_slug, j.new_slug)

            if deliveries_lines is not None:
                for li, dline in enumerate(deliveries_lines):
                    if j.old_slug in dline:
                        deliveries_lines[li] = replace_slug_in_text(
                            dline, j.gid, j.old_slug, j.new_slug
                        )

            for data in gen_out_data.values():
                update_generate_out_data(data, j.gid, j.old_slug, j.new_slug)

            for idx in line_idxs_for_slug(new_stock_lines, j.gid, j.old_slug, stock_slug_idx):
                old_ln = new_stock_lines[idx]
                new_ln = apply_slug_to_line(old_ln, j.gid, j.old_slug, j.new_slug)
                if new_ln != old_ln:
                    new_stock_lines[idx] = new_ln
                    updated_stock_lines.append(new_ln.rstrip("\n"))

            for bundle in links_bundles:
                for idx in line_idxs_for_slug(bundle.lines, j.gid, j.old_slug, bundle.slug_idx):
                    old_ln = bundle.lines[idx]
                    new_ln = apply_slug_to_line(old_ln, j.gid, j.old_slug, j.new_slug)
                    if new_ln != old_ln:
                        bundle.lines[idx] = new_ln
                        updated_links_lines.append(f"{bundle.path.name}: {new_ln.rstrip()}")

            ok += 1
        except Exception as e:
            fail += 1
            print(f"  [!] {j.old_slug} failed: {e}")

    print(f"  Apply done in {time.monotonic() - apply_start:.0f}s")

    # Safety net: batch-sync ALL stock + links from slug map (fixes missed index rows).
    print(f"\n[*] Batch-syncing stock + links from {len(jobs)} slug mappings...")
    slug_map = jobs_to_slug_map(jobs)
    slug_map, skip_html = filter_slug_map_by_local_html(vercel_site, slug_map)
    if skip_html:
        print(f"    (skipped {skip_html} map entries — new pass HTML not on this machine)")
    stock_files = find_all_stock_files(site_dir, data_dir)
    if not stock_files:
        stock_files = [stock_path]
    updated_stock_lines = []
    total_stock_hits = 0
    for sf in stock_files:
        if sf.resolve() == stock_path.resolve():
            lines_in = new_stock_lines
        elif sf.is_file():
            lines_in = sf.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        else:
            continue
        synced, hits, changed, _ = batch_sync_lines_with_map(lines_in, slug_map)
        total_stock_hits += hits
        updated_stock_lines.extend(changed)
        sf.write_text("".join(synced), encoding="utf-8")
        print(f"    {sf.name}: {hits} line(s) synced")
    for bundle in links_bundles:
        synced, hits, changed, _ = batch_sync_lines_with_map(bundle.lines, slug_map)
        bundle.lines = synced
        for c in changed:
            updated_links_lines.append(f"{bundle.path.name}: {c}")
        print(f"    {bundle.path.name}: {hits} line(s) synced")

    if reg_text is not None:
        reg_path.write_text(reg_text, encoding="utf-8")
    _apply_reslug_transfer_state(
        layout, jobs, confirm=True, no_backup=args.no_backup
    )
    if deliveries_lines is not None and deliveries_jsonl:
        deliveries_jsonl.write_text("".join(deliveries_lines), encoding="utf-8")
    for gp, data in gen_out_data.items():
        gp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for bundle in links_bundles:
        bundle.path.write_text("".join(bundle.lines), encoding="utf-8")

    summary = (
        f"\ndone ok={ok} fail={fail}\n"
        f"stock_lines_updated={total_stock_hits}\n"
        f"links_lines_updated={len(updated_links_lines)}\n"
    )
    with map_path.open("a", encoding="utf-8") as fh:
        fh.write(summary)
    with report_path.open("a", encoding="utf-8") as fh:
        fh.write(summary)

    stock_out_path.write_text(
        "\n".join(updated_stock_lines) if updated_stock_lines else "(no stock lines matched)",
        encoding="utf-8",
    )
    links_out_path.write_text(
        "\n".join(updated_links_lines) if updated_links_lines else "(no links lines matched)",
        encoding="utf-8",
    )

    print(f"\n[+] Reslugged {ok} HTML pass(es), {fail} failed")
    for sf in stock_files:
        if sf.is_file():
            print(f"[+] Stock CSV     : {sf}")
    for bundle in links_bundles:
        print(f"[+] Links synced  : {bundle.path}")
    print(f"[+] Full map      : {map_path}")
    print(f"[+] Stock lines   : {stock_out_path}")
    print(f"[+] Links lines   : {links_out_path}")
    print(f"[+] Report        : {report_path}")

    if not args.skip_barcode_backfill:
        _run_barcode_backfill(layout, confirm=args.confirm, no_backup=args.no_backup)


def _discover_transfer_state_paths(site_dir: Path, data_dir: Path) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for cand in (
        site_dir / "tm_viewer_transfer_state.json",
        data_dir / "tm_viewer_transfer_state.json",
        site_dir / "tm-vercel-site" / "tm_viewer_transfer_state.json",
        site_dir.parent / "tm_viewer_transfer_state.json",
    ):
        if not cand.is_file():
            continue
        try:
            key = str(cand.resolve())
        except OSError:
            key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        out.append(cand)
    return out


def _reslug_one_transfer_row(row: dict, old_slug: str, new_slug: str) -> dict:
    if not isinstance(row, dict):
        return row
    out = dict(row)
    for key in ("buyer_pass_slug",):
        v = str(out.get(key) or "")
        if v == old_slug:
            out[key] = new_slug
    bpu = str(out.get("buyer_pass_url") or "")
    if old_slug and old_slug in bpu:
        out["buyer_pass_url"] = bpu.replace(old_slug, new_slug)
    hist = out.get("buyer_pass_history")
    if isinstance(hist, list):
        nh: list = []
        for h in hist:
            if not isinstance(h, dict):
                nh.append(h)
                continue
            hh = dict(h)
            hs = str(hh.get("buyer_pass_slug") or "")
            if hs == old_slug:
                hh["buyer_pass_slug"] = new_slug
            hu = str(hh.get("buyer_pass_url") or "")
            if old_slug and old_slug in hu:
                hh["buyer_pass_url"] = hu.replace(old_slug, new_slug)
            nh.append(hh)
        out["buyer_pass_history"] = nh
    return out


def _reslug_transfer_state_for_jobs(
    transfer_data: dict,
    jobs: list,
) -> tuple[dict, int]:
    """Move transfer rows from old slug keys to new slug keys (keeps pass_public_base + buyer tokens)."""
    if not transfer_data or not jobs:
        return transfer_data, 0
    data = dict(transfer_data)
    moved = 0
    for j in jobs:
        old_key = f"tickets/{j.gid}/{j.old_slug}.html"
        new_key = f"tickets/{j.gid}/{j.new_slug}.html"
        found_key = None
        for k in list(data.keys()):
            if str(k).replace("\\", "/").lower() == old_key.lower():
                found_key = k
                break
        if not found_key:
            continue
        row = _reslug_one_transfer_row(data.pop(found_key), j.old_slug, j.new_slug)
        data[new_key] = row
        moved += 1
    return data, moved


def _apply_reslug_transfer_state(
    layout: StubbyLayout,
    jobs: list,
    *,
    confirm: bool,
    no_backup: bool = False,
) -> None:
    ts_paths = _discover_transfer_state_paths(layout.site_dir, layout.data_dir)
    if not ts_paths:
        return
    merged: dict = {}
    for p in ts_paths:
        try:
            raw = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            if isinstance(raw, dict):
                merged.update(raw)
        except (OSError, json.JSONDecodeError):
            continue
    if not merged:
        return
    new_data, moved = _reslug_transfer_state_for_jobs(merged, jobs)
    if moved:
        print(f"[*] Transfer state: {moved} row(s) remapped to new slug keys")
    if not confirm:
        if moved:
            print("    (dry run — transfer state not written)")
        return
    if moved <= 0:
        return
    text = json.dumps(new_data, indent=2, ensure_ascii=False) + "\n"
    bak_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    for p in ts_paths:
        try:
            if not no_backup and p.is_file():
                shutil.copy2(p, p.with_name(f"{p.name}.bak_{bak_ts}"))
            p.write_text(text, encoding="utf-8")
        except OSError as e:
            print(f"[!] transfer state write failed {p}: {e}")


def _run_barcode_backfill(layout: StubbyLayout, *, confirm: bool, no_backup: bool) -> None:
    root = layout.root
    ops_path = root
    for cand in (root, root.parent, Path(__file__).resolve().parent.parent):
        if (cand / "secure_pass_stock_ops.py").is_file():
            ops_path = cand
            break
    if str(ops_path) not in sys.path:
        sys.path.insert(0, str(ops_path))
    try:
        from secure_pass_stock_ops import (
            PassBarcodeIndex,
            backfill_stock_barcodes,
            build_checker_barcode_index_for_layout,
            print_backfill_report,
        )
    except ImportError as e:
        print(f"[!] barcode backfill skipped - secure_pass_stock_ops import failed: {e}")
        return

    stock_files = find_all_stock_files(layout.site_dir, layout.data_dir)
    if not stock_files:
        stock_files = [layout.stock_path]

    checker_idx, _all_sources = build_checker_barcode_index_for_layout(
        layout.site_dir,
        layout.data_dir,
    )
    if not checker_idx and not _all_sources:
        print(
            "[!] No upcoming/pm/hits/tickets dumps in Data_for_recovery — HTML scrape only",
            flush=True,
        )

    pass_index = PassBarcodeIndex.build(layout.vercel_site / "tickets")

    for sf in stock_files:
        if not sf.is_file():
            continue
        rep = backfill_stock_barcodes(
            sf,
            layout.vercel_site,
            confirm=confirm,
            public_base=_PUBLIC_BASE,
            no_backup=no_backup,
            checker_idx=checker_idx,
            pass_index=pass_index,
        )
        print_backfill_report(rep, sf, dry_run=not confirm)


if __name__ == "__main__":
    main()
