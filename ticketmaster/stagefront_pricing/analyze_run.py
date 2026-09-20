"""After a pricing run: verify portal prices vs section MinPrice 3–5% band."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

try:
    from .pricing_math import band_from_minimum, pct_under_min, price_in_band
except ImportError:
    from pricing_math import band_from_minimum, pct_under_min, price_in_band

log = logging.getLogger("stagefront.analyze")

RESULTS = Path(__file__).resolve().parent / "autopricer_results.jsonl"
REPORT = Path(__file__).resolve().parent / "pricing_audit.json"


def load_results(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or RESULTS
    if not p.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def audit_results(
    rows: list[dict[str, Any]],
    pct_min: float = 3.0,
    pct_max: float = 5.0,
) -> dict[str, Any]:
    ok = above_min = out_of_band = no_min = 0
    bad: list[dict[str, Any]] = []
    for r in rows:
        if r.get("status") not in ("ok", "priced_only", "rules_failed"):
            continue
        sec_min = r.get("section_min_used") or r.get("market_low")
        price = r.get("portal_price_after") or r.get("target_price")
        if not sec_min or not price:
            no_min += 1
            continue
        sec_min = float(sec_min)
        price = float(price)
        if price >= sec_min:
            above_min += 1
            bad.append({**r, "issue": "at_or_above_section_min"})
        elif price_in_band(price, sec_min, pct_min, pct_max):
            ok += 1
        else:
            out_of_band += 1
            bad.append(
                {
                    **r,
                    "issue": "outside_3_5_pct_band",
                    "actual_pct_under": pct_under_min(price, sec_min),
                    "expected_band": band_from_minimum(sec_min, pct_min, pct_max),
                }
            )
    return {
        "total_checked": len(rows),
        "ok_in_3_5_pct_band": ok,
        "at_or_above_section_min": above_min,
        "out_of_band": out_of_band,
        "missing_min_or_price": no_min,
        "pct_min": pct_min,
        "pct_max": pct_max,
        "bad_samples": bad[:100],
    }


def run_audit(pct_min: float = 3.0, pct_max: float = 5.0) -> dict[str, Any]:
    rows = load_results()
    report = audit_results(rows, pct_min, pct_max)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log.info(
        "audit: ok=%d above_min=%d out_of_band=%d missing=%d (see %s)",
        report["ok_in_3_5_pct_band"],
        report["at_or_above_section_min"],
        report["out_of_band"],
        report["missing_min_or_price"],
        REPORT,
    )
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_audit()
