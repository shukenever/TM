"""Section-min undercut band (3–5% below portal MinPrice)."""

from __future__ import annotations


def band_from_minimum(section_min: float, pct_min: float, pct_max: float) -> tuple[float, float]:
    """Return (lowest_ok_price, highest_ok_price) for N% under section minimum."""
    hi = pct_min if pct_min <= pct_max else pct_max
    lo = pct_max if pct_min <= pct_max else pct_min
    highest = round(section_min * (1.0 - hi / 100.0), 2)
    lowest = round(section_min * (1.0 - lo / 100.0), 2)
    return lowest, highest


def price_in_band(
    price: float,
    section_min: float,
    pct_min: float,
    pct_max: float,
    tolerance: float = 0.02,
) -> bool:
    low, high = band_from_minimum(section_min, pct_min, pct_max)
    return (low - tolerance) <= price <= (high + tolerance) and price < section_min


def pct_under_min(price: float, section_min: float) -> float | None:
    if section_min <= 0:
        return None
    return round((1.0 - price / section_min) * 100.0, 2)
