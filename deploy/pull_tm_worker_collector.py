#!/usr/bin/env python3
"""Download TM WORKER BOT collector.db from VPS via vl_bot_receiver /api/exec."""
from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
CFG = json.loads((BASE / "vl_bot.config.json").read_text(encoding="utf-8"))
HOST = str(CFG.get("host") or "104.194.11.195")
PORT = int(CFG.get("port") or 65000)

REMOTE_DB = r"C:\Users\Administrator\Desktop\TM WORKER BOT\bot_data\collector.db"
STAGED_REL = "data/tm_worker_collector.db"
REMOTE_OKAY = r"C:\Users\Administrator\Desktop\TM WORKER BOT\okaysec.txt"
REMOTE_OKAY2 = r"C:\Users\Administrator\Desktop\ticket management bot\okaysec.txt"
ROOT = str(CFG.get("root_dir") or r"C:\Users\Administrator\Desktop\ticket management bot")


def _exec(command: str, timeout: int = 600) -> dict:
    url = f"http://{HOST}:{PORT}/api/exec"
    body = json.dumps({"command": command, "timeout": timeout}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout + 30) as resp:
        return json.loads(resp.read().decode())


def stage_and_pull(remote: str, staged_rel: str, local: Path) -> bool:
    """Copy large files into deploy root on VPS, then GET /api/read (exec stdout is capped)."""
    staged = f"{ROOT}\\{staged_rel.replace('/', chr(92))}"
    copy_cmd = f'copy /Y "{remote}" "{staged}"'
    data = _exec(copy_cmd)
    if not data.get("ok") or data.get("exit_code") not in (0, 1):
        print(data, file=sys.stderr)
        return False
    q = urllib.parse.urlencode({"path": staged_rel.replace("\\", "/"), "encoding": "base64"})
    url = f"http://{HOST}:{PORT}/api/read?{q}"
    with urllib.request.urlopen(url, timeout=600) as resp:
        payload = json.loads(resp.read().decode())
    if not payload.get("ok"):
        print(payload, file=sys.stderr)
        return False
    raw = base64.b64decode(payload.get("content") or "")
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(raw)
    print(f"Wrote {local} ({len(raw)} bytes) from {remote}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out-db",
        default=str(BASE.parent / "ticketmaster" / "bot_data" / "tm_worker_collector.db"),
    )
    ap.add_argument("--out-okaysec", default=str(BASE.parent / "okaysec_tm_worker.txt"))
    ap.add_argument("--skip-okaysec", action="store_true")
    args = ap.parse_args()
    ok = stage_and_pull(REMOTE_DB, STAGED_REL, Path(args.out_db))
    if not args.skip_okaysec:
        for remote in (REMOTE_OKAY, REMOTE_OKAY2, str(Path(ROOT) / "okaysec.txt")):
            if stage_and_pull(remote, "data/okaysec_staged.txt", Path(args.out_okaysec)):
                break
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
