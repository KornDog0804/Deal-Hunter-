"""
'Likely' valuation tier (Option B): the album is found on Discogs but the exact pressing
cannot be verified from a retail listing. Value it conservatively at the FLOOR: the lowest
current asking price across the plausible pressings. Pure functions, no network.

A floor is an estimate of what the cheapest comparable copy is listed for. It is not a sold
price and not a verified pressing, so a Likely deal can never earn BUY NOW.
"""

LIKELY_LABEL = "Likely - pressing unverified; floor estimate (lowest Discogs ask)"
WIDE_SPREAD = 2.0          # priciest/cheapest ask ratio above which we flag "prices vary widely"
MAX_TIED_LOOKUPS = 4       # cap extra API calls per ambiguous pressing


def floor_estimate(asks):
    """asks: {release_id: lowest_ask_usd or None}. Returns None when no usable price."""
    vals = {i: float(p) for i, p in (asks or {}).items() if p and float(p) > 0}
    if not vals:
        return None
    lo, hi = min(vals.values()), max(vals.values())
    return {"floor": round(lo, 2), "spread": round(hi / lo, 2), "wide": hi / lo > WIDE_SPREAD,
            "ids": sorted(vals), "count": len(vals)}
