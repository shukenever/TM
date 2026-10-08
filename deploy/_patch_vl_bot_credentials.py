#!/usr/bin/env python3
"""Set vl_username / vl_password on VPS bot config (not in manifest sync).

Usage (from deploy/):
  set VL_CRED_USER=you@example.com
  set VL_CRED_PASS=your-password
  python _patch_vl_bot_credentials.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vl_bot_sender import HOST, _post

ROOT = r"C:\Users\Administrator\Desktop\ticket management bot"
user = (os.environ.get("VL_CRED_USER") or "").strip()
password = os.environ.get("VL_CRED_PASS")
if not user or not password:
    print("Set VL_CRED_USER and VL_CRED_PASS", file=sys.stderr)
    raise SystemExit(2)

script = f"""
import json
from pathlib import Path
p = Path(r"{ROOT}") / "vl_inventory_bot.config.json"
cfg = json.loads(p.read_text(encoding="utf-8"))
cfg["vl_username"] = {json.dumps(user)}
cfg["vl_password"] = {json.dumps(password)}
p.write_text(json.dumps(cfg, indent=2) + "\\n", encoding="utf-8")
print("patched vl_username on VPS config")
""".strip()
import base64

b64 = base64.b64encode(script.encode()).decode()
cmd = f'python -c "import base64; exec(base64.b64decode(\'{b64}\').decode())"'
r = _post(HOST, "/api/exec", {"command": cmd, "timeout": 60, "cwd": ROOT})
print(json.dumps(r, indent=2))
