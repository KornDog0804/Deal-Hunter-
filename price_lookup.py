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

import discogs_matcher as dm
import landed_cost as lc

BASE = Path(__file__).resolve().parent

DISCOGS_TOKEN = os.environ.get("DISCOGS_TOKEN", "")
CACHE_FILE = BASE / "price_cache.json"
CACHE_TTL_DAYS = 7
# v1 cache entries came from the old matcher (which could accept results[0]).
# They are never reused; they are simply looked up again under strict matching.
CACHE_SCHEMA = 2
DEALS_FILE = BASE / "live_deals.json"

# Only look up deals the Brain scored highly
MIN_SCORE_FOR_LOOKUP = 45  # WATCH and above
MAX_LOOKUPS_PER_RUN = 350  # safety cap
# Strict matching can need a second search per listing, and the workflow times out at
# 30 minutes. Stop cleanly before that; unprocessed deals are picked up on the next run
# (their cache entries are still stale, so they sort to the front again).
MAX_RUNTIME_SECONDS = int(os.environ.get("PRICE_LOOKUP_MAX_SECONDS", str(25 * 60)))

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


def cache_key(artist, title, ident=None):
    """
    Normalize artist+title into a stable cache key. When the listing carries
    pressing identifiers (catalog number, label, country, year) they are part of
    the key, so a Japan pressing never shares a slot with a US pressing.
    """
    def norm(s):
        s = (s or "").lower().strip()
        s = re.sub(r'[^a-z0-9\s]', '', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s
    key = f"{norm(artist)}::{norm(title)}"
    suffix = dm.pressing_suffix(ident) if ident else ""
    return key + ("::" + suffix if suffix else "")


def is_cache_fresh(entry):
    """Fresh = written by the strict matcher (schema) and inside the TTL."""
    if entry.get("schema") != CACHE_SCHEMA:
        return False
    ts = entry.get("cached_at", "")
    if not ts:
        return False
    try:
        cached_dt = datetime.fromisoformat(ts)
        return datetime.now() - cached_dt < timedelta(days=CACHE_TTL_DAYS)
    except Exception:
        return False


def discogs_http_get(params):
    """One /database/search call (injected into the matcher). Returns dict or None."""
    query = urllib.parse.urlencode(dict(params, token=DISCOGS_TOKEN))
    url = f"https://api.discogs.com/database/search?{query}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        time.sleep(1.1)  # rate limit
        return data
    except urllib.error.HTTPError as e:
        if e.code == 429:
            log("[Discogs] Rate limited, sleeping 5s...")
            time.sleep(5)
        else:
            log(f"[Discogs] Search HTTP {e.code}")
        return None
    except Exception as e:
        log(f"[Discogs] Search error: {e}")
        return None


def match_deal(deal, http_get=None):
    """Strictly match a listing to ONE Discogs release. Returns (ident, result)."""
    ident = dm.extract_identifiers(deal)
    return ident, dm.search_and_match(ident, http_get or discogs_http_get)


def discogs_search(artist, title):
    """
    Back-compat helper: release id, or None. Unlike the old version this NEVER
    returns an unrelated first result; ambiguous or unmatched -> None.
    """
    ident = dm.extract_identifiers({"artist": artist, "title": title})
    result = dm.search_and_match(ident, discogs_http_get)
    return result["release_id"] if result["status"] in dm.VALUABLE_STATUSES else None


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


def lookup_deal(deal, cache, http_get=None):
    """
    Look up the market price for a deal under strict release matching.
    Returns the cache entry. Ambiguous / unmatched listings are cached as
    not-found WITH the reason, so we neither retry daily nor guess.
    """
    artist = (deal.get("artist", "") or "").strip()
    title = (deal.get("title", "") or "").strip()
    ident = dm.extract_identifiers(deal)
    key = cache_key(artist, title, ident)

    if key in cache and is_cache_fresh(cache[key]):
        return cache[key]

    result = dm.search_and_match(ident, http_get or discogs_http_get)

    entry = {
        "artist": artist,
        "title": title,
        "found": False,
        "schema": CACHE_SCHEMA,
        "cached_at": datetime.now().isoformat(),
        "match_status": result["status"],
        "match_confidence": result["confidence"],
        "match_reasons": result["reasons"],
        "tied_ids": result["tied_ids"],
    }

    if result["status"] in dm.VALUABLE_STATUSES and result["release_id"]:
        stats = discogs_price_stats(result["release_id"])
        time.sleep(1.1)  # Rate limit
        if stats:
            entry["found"] = True
            entry.update(stats)
            for field in ("matched_artist", "matched_title", "matched_label",
                          "matched_catno", "matched_country", "matched_year"):
                entry[field] = result.get(field)

    cache[key] = entry
    return entry


ESTIMATE_LABEL = "Estimate - Discogs asking prices, not verified sold prices"


def _apply_valuation(deal, entry, cfg):
    """Write one matched valuation onto a deal (all labelled as an estimate)."""
    cost = deal.get("price", 0) or 0
    sell_price = entry.get("suggested_sell_price", 0)
    status = entry.get("match_status", dm.NONE)

    deal["discogs_sell_price"] = sell_price
    deal["discogs_lowest"] = entry.get("lowest_price", 0)
    deal["discogs_price_nm"] = entry.get("price_nm", 0)
    deal["discogs_price_mint"] = entry.get("price_mint", 0)
    deal["discogs_price_vgplus"] = entry.get("price_vgplus", 0)
    deal["discogs_num_for_sale"] = entry.get("num_for_sale", 0)
    deal["discogs_url"] = entry.get("discogs_url", "")
    deal["discogs_found"] = True
    deal["discogs_release_id"] = entry.get("release_id")

    # Match provenance + honest labelling of what the number is.
    deal["discogs_match_status"] = status
    deal["discogs_match_confidence"] = entry.get("match_confidence", 0.0)
    deal["discogs_match_reasons"] = entry.get("match_reasons", [])
    deal["discogs_matched_title"] = entry.get("matched_title", "")
    deal["discogs_matched_catno"] = entry.get("matched_catno", "")
    deal["discogs_matched_country"] = entry.get("matched_country", "")
    deal["discogs_matched_year"] = entry.get("matched_year")
    deal["valuation_is_estimate"] = True
    deal["valuation_verified_sold"] = False
    deal["valuation_basis"] = "discogs_asking_price"
    deal["valuation_label"] = ESTIMATE_LABEL

    # Override Brain's markup-based sale price with the (estimated) market price
    deal["suggested_sale_price"] = sell_price

    if cost > 0:
        real_margin = round(sell_price - cost, 2)
        real_margin_pct = round((real_margin / cost) * 100, 2)
        deal["expected_margin_dollars"] = real_margin
        deal["expected_margin_percent"] = real_margin_pct

        # Same ladder as before ...
        if real_margin >= 8:
            deal["decision"] = "BUY NOW"
        elif real_margin >= 4:
            deal["decision"] = "BUY LIGHT"
        elif real_margin >= 0:
            deal["decision"] = "WATCH"
        else:
            deal["decision"] = "PASS"
            deal["why_buy"] = f"Negative margin (${real_margin:.2f}) based on Discogs estimate"

        # ... but an unverified pressing can never earn BUY NOW.
        if status not in dm.DECISION_GRADE_STATUSES and deal["decision"] == "BUY NOW":
            deal["decision"] = "BUY LIGHT"
            deal["decision_note"] = "Capped at BUY LIGHT: Discogs pressing not verified (title-only match)."

        # Landed cost / net profit (additive fields; decisions use them only if enabled).
        calc = lc.estimate_net_profit(cost, sell_price, "USD", cfg, "domestic_us")
        deal["landed_cost_usd"] = calc["landed_cost_usd"]
        deal["net_profit_usd"] = calc["net_profit_usd"]
        deal["roi_percent"] = calc["roi_percent"]
        deal["cost_inputs_complete"] = calc["inputs_complete"]
        deal["cost_missing_inputs"] = calc["missing_inputs"]
        deal["cost_assumed_inputs"] = calc["assumed_inputs"]

        if cfg.get("use_net_for_decisions") and deal["decision"] in ("BUY NOW", "BUY LIGHT"):
            if not lc.passes_net_thresholds(calc, cfg):
                deal["decision"] = "WATCH"
                deal["decision_note"] = "Net profit/ROI below configured thresholds."


def enrich_deals_with_prices(deals, cache, http_get=None, cfg=None):
    """
    Enrich deals with Discogs market ESTIMATES under strict release matching.
    Only processes deals above MIN_SCORE_FOR_LOOKUP.
    """
    cfg = cfg if cfg is not None else lc.load_config()
    started = time.time()
    lookups_done = 0
    enriched = 0
    skipped_cached = 0
    skipped_low_score = 0
    unmatched = 0
    ambiguous = 0

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

        if time.time() - started > MAX_RUNTIME_SECONDS:
            log(f"[PriceLookup] Hit runtime budget ({MAX_RUNTIME_SECONDS}s), stopping cleanly")
            break

        artist = (deal.get("artist", "") or "").strip()
        title = (deal.get("title", "") or "").strip()
        key = cache_key(artist, title, dm.extract_identifiers(deal))

        try:
            if key in cache and is_cache_fresh(cache[key]):
                entry = cache[key]
                skipped_cached += 1
            else:
                entry = lookup_deal(deal, cache, http_get)
                lookups_done += 1
                if lookups_done % 25 == 0:
                    log(f"[PriceLookup] Progress: {lookups_done} lookups done...")
        except Exception as e:  # one bad listing must not stop the run
            log(f"[PriceLookup] lookup failed for '{artist} - {title}': {e}")
            continue

        status = (entry or {}).get("match_status", dm.NONE)
        if entry and entry.get("found") and entry.get("suggested_sell_price", 0) > 0:
            _apply_valuation(deals[idx], entry, cfg)
            enriched += 1
        else:
            deals[idx]["discogs_match_status"] = status
            if status == dm.AMBIGUOUS:
                ambiguous += 1
            else:
                unmatched += 1

    log(f"\n[PriceLookup] Summary:")
    log(f"  Lookups performed: {lookups_done}")
    log(f"  Cache hits: {skipped_cached}")
    log(f"  Skipped (low score): {skipped_low_score}")
    log(f"  Deals enriched with estimated prices: {enriched}")
    log(f"  Ambiguous (no valuation applied): {ambiguous}")
    log(f"  Unmatched (no valuation applied): {unmatched}")

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
            
