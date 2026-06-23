"""Load reslug_full_map_*.txt (old slug → new pass) for shop + pass server."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_RE_VIEWER = re.compile(
    r"(https?://[^/]+)/tickets/(\d+)/([^\s\"'<>\[\]/\.]+)",
    re.I,
)


@dataclass(frozen=True)
class SlugMapEntry:
    gid: str
    old_slug: str
    new_slug: str


def normalize_slug(slug: str) -> str:
    s = (slug or "").strip().rstrip(".,)")
    if s.upper().endswith(",TM"):
        s = s[:-3].rstrip()
    return s


def _slug_gid_from_url(url: str) -> tuple[str, str] | None:
    m = _RE_VIEWER.search((url or "").strip())
    if not m:
        return None
    return m.group(2), normalize_slug(m.group(3))


def parse_reslug_map(path: Path) -> list[SlugMapEntry]:
    entries: list[SlugMapEntry] = []
    cur_old_slug = ""
    cur_new_slug = ""
    cur_gid = ""
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
            pair = _slug_gid_from_url(s[4:].strip())
            if pair:
                cur_gid, cur_old_slug = pair
        elif s.startswith("NEW "):
            pair = _slug_gid_from_url(s[4:].strip())
            if pair:
                cur_gid, cur_new_slug = pair
            if cur_old_slug and cur_new_slug and cur_gid:
                entries.append(
                    SlugMapEntry(
                        gid=cur_gid,
                        old_slug=cur_old_slug,
                        new_slug=cur_new_slug,
                    )
                )
    return entries


def find_latest_reslug_map(*dirs: Path) -> Path | None:
    best: Path | None = None
    best_m = 0.0
    for d in dirs:
        if not d.is_dir():
            continue
        try:
            matches = list(d.glob("reslug_full_map_*.txt"))
            matches.extend(p for p in d.glob("reslug_full_map_*") if p.is_file() and p not in matches)
        except OSError:
            continue
        for p in matches:
            try:
                mt = p.stat().st_mtime
            except OSError:
                continue
            if mt > best_m:
                best_m = mt
                best = p
    return best


_CACHE: dict[str, tuple[float, dict[str, str]]] = {}


def entries_to_redirects(entries: list[SlugMapEntry]) -> dict[str, str]:
    out: dict[str, str] = {}
    for e in entries:
        out[e.old_slug] = f"tickets/{e.gid}/{e.new_slug}.html"
    return out


def load_reslug_redirects(*search_dirs: Path) -> dict[str, str]:
    """Return old_slug → ``tickets/<gid>/<new>.html`` from the newest reslug_full_map."""
    map_path = find_latest_reslug_map(*search_dirs)
    if not map_path:
        return {}
    key = str(map_path)
    try:
        st = map_path.stat().st_mtime
    except OSError:
        return {}
    cached = _CACHE.get(key)
    if cached and cached[0] == st:
        return cached[1]
    out = entries_to_redirects(parse_reslug_map(map_path))
    _CACHE[key] = (st, out)
    return out


def merge_slug_redirects(*maps: dict[str, str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for m in maps:
        if m:
            merged.update(m)
    return merged


def rewrite_viewer_link(link: str, redirects: dict[str, str]) -> str:
    m = _RE_VIEWER.search(link or "")
    if not m or not redirects:
        return link
    slug = normalize_slug(m.group(3))
    rel = redirects.get(slug)
    if not rel:
        return link
    mm = re.match(r"tickets/(\d+)/([^/]+?)(?:\.html)?$", rel.replace("\\", "/"), re.I)
    if not mm:
        return link
    gid, new_slug = mm.group(1), normalize_slug(mm.group(2))
    return f"{m.group(1)}/tickets/{gid}/{new_slug}"


def redirect_rel_path(slug: str, redirects: dict[str, str]) -> str:
    return (redirects.get(normalize_slug(slug)) or "").strip()


def redirect_target_path(root: Path, slug: str, redirects: dict[str, str]) -> Path | None:
    rel = redirect_rel_path(slug, redirects)
    if not rel:
        return None
    if not rel.lower().endswith(".html"):
        rel = f"{rel}.html"
    try:
        cand = (root / rel).resolve()
        cand.relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return cand if cand.is_file() else None
