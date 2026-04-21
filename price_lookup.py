# -*- coding: utf-8 -*-
"""
price_lookup.py — Discogs Real Market Price Enrichment for Deal Hunter

Queries Discogs marketplace stats for BUY NOW / BUY LIGHT deals.
Caches results in price_cache.json (7-day TTL).
Updates live_deals.json with real median/low/high sale prices.

Requires: DISCOGS_TOKEN environment variable (personal access token)
Rate limit: 60 req/min — we throttle to 1 req/sec to stay safe.

Usage:
  python price_lookup.py                    # enrich live_deals.json in place
  DISCOGS_TOKEN=xxx python price_lookup.py  # pass token via env
"""

import json
import os
import re
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parent

DISCOGS_TOKEN = os.environ.get("DISCOGS_TOKEN", "")
CACHE_FILE = BASE / "price_cache.json"
CACHE_TTL_DAYS = 7
DEALS_FILE = BASE / "live_deals.json"

# Only look up deals the Brain scored highly
MIN_SCORE_FOR_LOOKUP = 45  # WATCH and above
MAX_LOOKUPS_PER_RUN = 350  # safety cap (~6 min at 1/sec)

USER_AGENT = "KornDogDealHunter/1.0 +https://korndogrecords.com"

DEBUG = []


def log(msg):
    print(msg)
    DEBUG.append(msg)


def load_cache():
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def cache_key(artist, title):
    """Normalize artist+title into a stable cache key."""
    def norm(s):
        s = (s or "").lower().strip()
        s = re.sub(r'[^a-z0-9\s]', '', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s
    return f"{norm(artist)}::{norm(title)}"


def is_cache_fresh(entry):
    """Check if a cache entry is still within TTL."""
    ts = entry.get("cached_at", "")
    if not ts:
        return False
    try:
        cached_dt = datetime.fromisoformat(ts)
        return datetime.now() - cached_dt < timedelta(days=CACHE_TTL_DAYS)
    except Exception:
        return False


def discogs_search(artist, title):
    """
    Search Discogs for a release and return the best match's release_id.
    Uses the /database/search endpoint.
    """
    query = f"{artist} {title}".strip()
    if not query or query.lower() in ("unknown artist", "unknown title"):
        return None

    # Clean up query — remove common noise
    query = re.sub(r'\b(vinyl|lp|2lp|1lp|record|exclusive|limited|colored|splatter)\b', '', query, flags=re.I)
    query = re.sub(r'\s+', ' ', query).strip()

    params = urllib.parse.urlencode({
        "q": query,
        "type": "release",
        "format": "Vinyl",
        "per_page": 5,
        "token": DISCOGS_TOKEN,
    })

    url = f"https://api.discogs.com/database/search?{params}"

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))

        results = data.get("results", [])
        if not results:
            return None

        # Try to find the best match
        artist_lower = (artist or "").lower().strip()
        title_lower = (title or "").lower().strip()

        for result in results:
            r_title = (result.get("title", "") or "").lower()
            # Discogs format: "Artist - Title"
            if artist_lower and artist_lower in r_title:
                return result.get("id")
            if title_lower and title_lower in r_title:
                return result.get("id")

        # Fallback: return first result
        return results[0].get("id")

    except urllib.error.HTTPError as e:
        if e.code == 429:
            log(f"[Discogs] Rate limited, sleeping 5s...")
            time.sleep(5)
        else:
            log(f"[Discogs] Search HTTP {e.code} for '{query}'")
        return None
    except Exception as e:
        log(f"[Discogs] Search error for '{query}': {e}")
        return None


def discogs_price_stats(release_id):
    """
    Get marketplace price statistics for a Discogs release.
    Uses /marketplace/price_suggestions/{release_id} and
    /marketplace/stats/{release_id}.
    """
    if not release_id:
        return None

    stats = {}

    # Method 1: Community market stats (num_for_sale, lowest_price)
    try:
        url = f"https://api.discogs.com/marketplace/stats/{release_id}?curr_abbr=USD&token={DISCOGS_TOKEN}"
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))

        lowest = data.get("lowest_price", {})
        if isinstance(lowest, dict):
            stats["lowest_price"] = round(float(lowest.get("value", 0)), 2)
        elif isinstance(lowest, (int, float)):
            stats["lowest_price"] = round(float(lowest), 2)

        stats["num_for_sale"] = data.get("num_for_sale", 0)

    except Exception as e:
        log(f"[Discogs] Stats error for release {release_id}: {e}")

    time.sleep(1.1)  # Rate limit safety

    # Method 2: Price suggestions (median by condition)
    try:
        url = f"https://api.discogs.com/marketplace/price_suggestions/{release_id}?token={DISCOGS_TOKEN}"
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))

        # Discogs returns suggested prices by condition grade
        for condition in ["Mint (M)", "Near Mint (NM or M-)", "Very Good Plus (VG+)", "Very Good (VG)"]:
            entry = data.get(condition, {})
            if isinstance(entry, dict) and entry.get("value"):
                price = round(float(entry["value"]), 2)
                if condition == "Mint (M)":
                    stats["price_mint"] = price
                elif "Near Mint" in condition:
                    stats["price_nm"] = price
                elif "Very Good Plus" in condition:
                    stats["price_vgplus"] = price
                elif "Very Good" in condition:
                    stats["price_vg"] = price

    except urllib.error.HTTPError as e:
        if e.code == 404:
            log(f"[Discogs] No price suggestions for release {release_id}")
        elif e.code == 429:
            log(f"[Discogs] Rate limited on price suggestions, sleeping 5s...")
            time.sleep(5)
        else:
            log(f"[Discogs] Price suggestions HTTP {e.code} for release {release_id}")
    except Exception as e:
        log(f"[Discogs] Price suggestions error for release {release_id}: {e}")

    if not stats:
        return None

    # Compute a realistic "sell at" price
    # Priority: NM price > Mint price > VG+ price > lowest listed
    sell_at = (
        stats.get("price_nm") or
        stats.get("price_mint") or
        stats.get("price_vgplus") or
        stats.get("lowest_price") or
        0.0
    )

    stats["suggested_sell_price"] = round(sell_at, 2)
    stats["release_id"] = release_id
    stats["discogs_url"] = f"https://www.discogs.com/release/{release_id}"

    return stats


def lookup_deal(deal, cache):
    """
    Look up real market price for a deal. Returns updated cache entry or None.
    """
    artist = (deal.get("artist", "") or "").strip()
    title = (deal.get("title", "") or "").strip()
    key = cache_key(artist, title)

    # Check cache first
    if key in cache and is_cache_fresh(cache[key]):
        return cache[key]

    # Search Discogs
    release_id = discogs_search(artist, title)
    time.sleep(1.1)  # Rate limit

    if not release_id:
        # Cache the miss so we don't re-query
        cache[key] = {
            "artist": artist,
            "title": title,
            "found": False,
            "cached_at": datetime.now().isoformat(),
        }
        return cache[key]

    # Get price stats
    stats = discogs_price_stats(release_id)
    time.sleep(1.1)  # Rate limit

    entry = {
        "artist": artist,
        "title": title,
        "found": True,
        "cached_at": datetime.now().isoformat(),
    }

    if stats:
        entry.update(stats)
    else:
        entry["found"] = False

    cache[key] = entry
    return entry


def enrich_deals_with_prices(deals, cache):
    """
    Enrich deals with real Discogs market prices.
    Only processes deals above MIN_SCORE_FOR_LOOKUP.
    """
    lookups_done = 0
    enriched = 0
    skipped_cached = 0
    skipped_low_score = 0

    # Sort by buy_score descending so best deals get looked up first
    scored_deals = sorted(
        enumerate(deals),
        key=lambda x: x[1].get("buy_score", 0),
        reverse=True
    )

    for idx, deal in scored_deals:
        score = deal.get("buy_score", 0)

        if score < MIN_SCORE_FOR_LOOKUP:
            skipped_low_score += 1
            continue

        if lookups_done >= MAX_LOOKUPS_PER_RUN:
            log(f"[PriceLookup] Hit max lookups cap ({MAX_LOOKUPS_PER_RUN}), stopping")
            break

        artist = (deal.get("artist", "") or "").strip()
        title = (deal.get("title", "") or "").strip()
        key = cache_key(artist, title)

        # Use cache if fresh
        if key in cache and is_cache_fresh(cache[key]):
            entry = cache[key]
            skipped_cached += 1
        else:
            entry = lookup_deal(deal, cache)
            lookups_done += 1
            if lookups_done % 25 == 0:
                log(f"[PriceLookup] Progress: {lookups_done} lookups done...")

        # Apply real prices to the deal
        if entry and entry.get("found"):
            sell_price = entry.get("suggested_sell_price", 0)
            cost = deal.get("price", 0) or 0

            if sell_price > 0:
                deals[idx]["discogs_sell_price"] = sell_price
                deals[idx]["discogs_lowest"] = entry.get("lowest_price", 0)
                deals[idx]["discogs_price_nm"] = entry.get("price_nm", 0)
                deals[idx]["discogs_price_mint"] = entry.get("price_mint", 0)
                deals[idx]["discogs_price_vgplus"] = entry.get("price_vgplus", 0)
                deals[idx]["discogs_num_for_sale"] = entry.get("num_for_sale", 0)
                deals[idx]["discogs_url"] = entry.get("discogs_url", "")

                # Override Brain's fake sale price with real market data
                deals[idx]["suggested_sale_price"] = sell_price

                if cost > 0:
                    real_margin = round(sell_price - cost, 2)
                    real_margin_pct = round((real_margin / cost) * 100, 2) if cost > 0 else 0
                    deals[idx]["expected_margin_dollars"] = real_margin
                    deals[idx]["expected_margin_percent"] = real_margin_pct

                    # Upgrade/downgrade decision based on real margin
                    if real_margin >= 8:
                        deals[idx]["decision"] = "BUY NOW"
                    elif real_margin >= 4:
                        deals[idx]["decision"] = "BUY LIGHT"
                    elif real_margin >= 0:
                        deals[idx]["decision"] = "WATCH"
                    else:
                        deals[idx]["decision"] = "PASS"
                        deals[idx]["why_buy"] = f"Negative margin (${real_margin:.2f}) based on Discogs data"

                enriched += 1

    log(f"\n[PriceLookup] Summary:")
    log(f"  Lookups performed: {lookups_done}")
    log(f"  Cache hits: {skipped_cached}")
    log(f"  Skipped (low score): {skipped_low_score}")
    log(f"  Deals enriched with real prices: {enriched}")

    return deals


def main():
    if not DISCOGS_TOKEN:
        log("[PriceLookup] ERROR: DISCOGS_TOKEN not set. Add it as a GitHub secret.")
        return

    # Load deals
    if not DEALS_FILE.exists():
        log(f"[PriceLookup] ERROR: {DEALS_FILE} not found. Run live_pull.py first.")
        return

    deals = json.loads(DEALS_FILE.read_text(encoding="utf-8"))
    if not isinstance(deals, list):
        log("[PriceLookup] ERROR: live_deals.json is not a list")
        return

    log(f"[PriceLookup] Loaded {len(deals)} deals")
    log(f"[PriceLookup] Cache TTL: {CACHE_TTL_DAYS} days")
    log(f"[PriceLookup] Min score for lookup: {MIN_SCORE_FOR_LOOKUP}")

    # Count eligible deals
    eligible = sum(1 for d in deals if d.get("buy_score", 0) >= MIN_SCORE_FOR_LOOKUP)
    log(f"[PriceLookup] Eligible deals (score >= {MIN_SCORE_FOR_LOOKUP}): {eligible}")

    # Load cache
    cache = load_cache()
    log(f"[PriceLookup] Cache entries: {len(cache)}")

    # Enrich
    deals = enrich_deals_with_prices(deals, cache)

    # Save updated deals
    with open(DEALS_FILE, "w", encoding="utf-8") as f:
        json.dump(deals, f, indent=2, ensure_ascii=False)
    log(f"[PriceLookup] Updated {DEALS_FILE}")

    # Save cache
    save_cache(cache)
    log(f"[PriceLookup] Cache saved ({len(cache)} entries)")

    # Save debug log
    with open(BASE / "debug_price_lookup.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(DEBUG))


if __name__ == "__main__":
    main()
            
