#!/usr/bin/env python3
"""Serve tm-vercel-site (or TM_SITE_ROOT) on port 8593."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

os.environ.setdefault("PORT", "8593")
# VPS example:
#   set TM_SITE_ROOT=C:\Users\Administrator\Desktop\Stubhub\stubhub\tm.bz
#   python serve_8593.py

from local_dev_server import main

if __name__ == "__main__":
    main()
