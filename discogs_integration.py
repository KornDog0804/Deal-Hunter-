#!/usr/bin/env python3
import os
import re
import json
import time
import requests
from difflib import SequenceMatcher
from typing import Optional, Dict, Tuple

import discogs_matcher as dm

DISCOGS_API_BASE = "https://api.discogs.com"
DISCOGS_TOKEN = os.getenv("DISCOGS_TOKEN")

HEADERS = {
    "User-Agent": "KorndogDealHunter/1.0 +https://korndogrecords.com",
    "Accept": "application/json",
}

COMMON_LABELS = {
    "warner", "warner records", "reprise", "atlantic", "rhino",
    "sony", "columbia", "epic", "rca", "legacy",
    "universal", "interscope", "geffen", "capitol",
    "republic", "island", "def jam", "roadrunner",
    "nuclear blast", "metal blade", "rise records",
    "fearless records", "sumerian", "e1", "bmg",
    "craft recordings", "concord", "music on vinyl",
    "hopeless records", "revolver", "sharp tone", "sharptone",
    "pure noise records", "solid state records", "mnrk heavy",
    "equal vision", "brooklyn vegan", "newbury comics",
}

BAD_TITLE_JUNK = [
    "limited edition", "indie exclusive", "exclusive",
    "colored vinyl", "colour vinyl", "color vinyl",
    "vinyl", "lp", "2lp", "3lp", "4lp",
    "preorder", "pre-order", "import",
    "clear", "splatter", "swirl", "smoke",
    "red vinyl", "blue vinyl", "green vinyl", "yellow vinyl",
    "white vinyl", "black vinyl", "purple vinyl", "orange vinyl",
]

# Cache entries written before strict matching (no "matcher_schema") are not trusted:
# they may hold an unrelated or wrong-pressing release. They are re-looked-up, but only
# up to a per-run budget so a big stale cache cannot stall the scheduled job.
MATCHER_SCHEMA = 4
STALE_RELOOKUP_BUDGET = int(os.getenv("DISCOGS_RELOOKUP_BUDGET", "800"))
_stale_relookups = 0

def set_discogs_token(token: str):
    global DISCOGS_TOKEN
    DISCOGS_TOKEN = token

def clean_text(value: str) -> str:
    value = str(value or "").lower()
    value = value.replace("&amp;", " and ")
    value = value.replace("&", " and ")
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"\[[^]]*\]", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def clean_title_for_search(value: str) -> str:
    value = str(value or "")
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"\[[^]]*\]", " ", value)

    cleaned = clean_text(value)

    for junk in BAD_TITLE_JUNK:
        cleaned = cleaned.replace(clean_text(junk), " ")

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

def fuzzy_match(a: str, b: str) -> float:
    a = clean_text(a)
    b = clean_text(b)

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    if a in b or b in a:
        return 0.92

    return SequenceMatcher(None, a, b).ratio()

def split_artist_title(value: str) -> Tuple[str, str]:
    value = str(value or "").strip()

    if " - " in value:
        artist, title = value.split(" - ", 1)
        return artist.strip(), title.strip()

    if " – " in value:
        artist, title = value.split(" – ", 1)
        return artist.strip(), title.strip()

    return "", value

def is_label(value: str) -> bool:
    return clean_text(value) in COMMON_LABELS

def get_discogs_search_parts(deal: Dict) -> Tuple[str, str]:
    artist = str(deal.get("artist") or "").strip()
    title = str(deal.get("title") or "").strip()
    raw_title = str(deal.get("raw_title") or "").strip()

    # If title itself contains "Artist - Album", split it.
    raw_artist, raw_album = split_artist_title(raw_title)
    title_artist, title_album = split_artist_title(title)

    # If artist is actually a record label, replace it.
    if not artist or is_label(artist):
        for candidate in [
            raw_artist,
            title_artist,
            deal.get("band"),
            deal.get("performer"),
            deal.get("main_artist"),
            deal.get("artist_name"),
        ]:
            candidate = str(candidate or "").strip()
            if candidate and not is_label(candidate):
                artist = candidate
                break

    # Prefer cleaner album title if the field has artist/title mashed together.
    if title_artist and title_album:
        title = title_album
    elif raw_artist and raw_album and clean_text(raw_artist) == clean_text(artist):
        title = raw_album

    title = clean_title_for_search(title)

    return artist.strip(), title.strip()

def discogs_get(path: str, params: Optional[Dict] = None) -> Optional[Dict]:
    if not DISCOGS_TOKEN:
        print("Missing DISCOGS_TOKEN", flush=True)
        return None

    params = params or {}
    params["token"] = DISCOGS_TOKEN

    try:
        url = f"{DISCOGS_API_BASE}{path}"
        response = requests.get(url, headers=HEADERS, params=params, timeout=20)

        if response.status_code == 429:
            print("Discogs rate limited. Sleeping 60 seconds.", flush=True)
            time.sleep(60)
            response = requests.get(url, headers=HEADERS, params=params, timeout=20)

        response.raise_for_status()
        return response.json()

    except Exception as e:
        print(f"Discogs API error on {path}: {e}", flush=True)
        return None

def validate_discogs_match(source_artist: str, source_title: str, discogs_result: Dict) -> Dict:
    result_full_title = discogs_result.get("title", "")
    result_artist, result_title = split_artist_title(result_full_title)

    title_score = fuzzy_match(source_title, result_title)
    artist_score = fuzzy_match(source_artist, result_artist)

    confidence = round((title_score * 0.68) + (artist_score * 0.32), 4)

    is_valid = (
        title_score >= 0.68 and artist_score >= 0.55
    ) or confidence >= 0.76

    return {
        "is_valid": is_valid,
        "confidence": confidence,
        "reason": "matched" if is_valid else "low_confidence",
        "discogs_artist": result_artist,
        "discogs_title": result_title,
        "title_score": title_score,
        "artist_score": artist_score,
    }

def search_discogs(artist: str, title: str, deal: Optional[Dict] = None) -> Optional[Dict]:
    """
    Strict release search. Returns None when nothing was searchable, otherwise a
    result dict carrying `_validation`. `is_valid` is True only for an exact,
    strong or title_only match; ambiguous / unmatched listings are NEVER resolved
    by picking a first or "best fuzzy" result.
    """
    artist = str(artist or "").strip()
    title = str(title or "").strip()
    if not title:
        return None

    ident = dm.extract_identifiers(deal or {"artist": artist, "title": title})
    ident["artist"] = artist or ident["artist"]
    ident["title"] = dm.title_core(title) or ident["title"]

    res = dm.search_and_match(ident, lambda params: discogs_get("/database/search", dict(params)))
    valid = res["status"] in dm.VALUABLE_STATUSES and bool(res["release_id"])
    return {
        "id": res["release_id"],
        "uri": res["uri"],
        "title": "%s - %s" % (res["matched_artist"], res["matched_title"]),
        "_validation": {
            "is_valid": valid,
            "confidence": res["confidence"],
            "reason": res["status"] if not valid else "matched",
            "match_status": res["status"],
            "match_reasons": res["reasons"],
            "discogs_artist": res["matched_artist"],
            "discogs_title": res["matched_title"],
            "title_score": None,
            "artist_score": None,
        },
        "_ident": ident,
    }

def get_release_stats(release_id: int) -> Dict:
    release = discogs_get(f"/releases/{release_id}") or {}

    lowest_price = release.get("lowest_price") or 0
    num_for_sale = release.get("num_for_sale") or 0

    community = release.get("community", {}) or {}
    have = community.get("have", 0)
    want = community.get("want", 0)

    # Discogs does not reliably return true "mint" pricing.
    # So this gives the board a usable comp value without lying.
    mint_price = lowest_price or 0

    return {
        "discogs_mint_price": mint_price,      # legacy key: this is the lowest ASKING price
        "discogs_lowest": lowest_price,
        "discogs_num_for_sale": num_for_sale,
        "discogs_have": have,
        "discogs_want": want,
        "valuation_is_estimate": True,
        "valuation_verified_sold": False,
        "valuation_basis": "discogs_asking_price",
        "valuation_label": "Estimate - Discogs asking prices, not verified sold prices",
    }

def enrich_with_discogs(deal: Dict, cache: Optional[Dict] = None) -> Dict:
    global _stale_relookups
    cache = cache if cache is not None else {}

    artist, title = get_discogs_search_parts(deal)
    ident = dm.extract_identifiers(deal)

    cache_key = f"{clean_text(artist)}|{clean_text(title)}"
    suffix = dm.pressing_suffix(ident)
    if suffix:
        cache_key += "|" + suffix

    cached = cache.get(cache_key)
    if cached is not None:
        if cached.get("matcher_schema") == MATCHER_SCHEMA:
            deal.update(cached)
            return deal
        # Stale (pre-strict-matching) entry: never trust it.
        if _stale_relookups >= STALE_RELOOKUP_BUDGET:
            deal.update({
                "discogs_found": False,
                "discogs_match_status": dm.NONE,
                "discogs_match_confidence": 0.0,
                "discogs_match_reason": "stale_cache_pending_refresh",
                "discogs_url": "",
                "discogs_mint_price": 0,
                "discogs_lowest": 0,
                "discogs_num_for_sale": 0,
            })
            return deal
        _stale_relookups += 1

    def _store(enriched):
        enriched["matcher_schema"] = MATCHER_SCHEMA
        deal.update(enriched)
        cache[cache_key] = enriched
        return deal

    if not title:
        return _store({
            "discogs_found": False, "discogs_match_status": dm.NONE,
            "discogs_match_confidence": 0.0, "discogs_match_reason": "missing_title",
            "discogs_url": "", "discogs_mint_price": 0, "discogs_lowest": 0,
            "discogs_num_for_sale": 0,
        })

    result = search_discogs(artist, title, deal)
    validation = (result or {}).get("_validation") or {}

    if not result or not validation.get("is_valid"):
        return _store({
            "discogs_found": False,
            "discogs_match_status": validation.get("match_status", dm.NONE),
            "discogs_match_confidence": validation.get("confidence", 0.0),
            "discogs_match_reason": validation.get("reason", "not_found"),
            "discogs_url": "", "discogs_mint_price": 0, "discogs_lowest": 0,
            "discogs_num_for_sale": 0,
        })

    release_id = result.get("id")
    stats = get_release_stats(release_id) if release_id else {}

    discogs_url = result.get("uri", "")
    if discogs_url and discogs_url.startswith("/"):
        discogs_url = f"https://www.discogs.com{discogs_url}"

    return _store({
        "discogs_found": True,
        "discogs_match_status": validation["match_status"],
        "discogs_match_confidence": validation["confidence"],
        "discogs_match_reason": "matched",
        "discogs_match_reasons": validation["match_reasons"],
        "discogs_artist": validation.get("discogs_artist", ""),
        "discogs_title": validation.get("discogs_title", ""),
        "discogs_release_id": release_id,
        "discogs_url": discogs_url,
        **stats,
    })

if __name__ == "__main__":
    set_discogs_token(os.getenv("DISCOGS_TOKEN") or "YOUR_TOKEN_HERE")

    test_deal = {
        "artist": "WARNER",
        "title": "TYPE O NEGATIVE - BLOODY KISSES: SUSPENDED IN DUSK 2LP (Viridian Void Vinyl)",
        "price": 41.99,
    }

    cache = {}
    result = enrich_with_discogs(test_deal, cache)
    print(json.dumps(result, indent=2))
