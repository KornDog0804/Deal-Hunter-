#!/usr/bin/env python3
import os
import re
import json
import time
import requests
from difflib import SequenceMatcher
from typing import Optional, Dict
from urllib.parse import quote

DISCOGS_API_BASE = "https://api.discogs.com"
DISCOGS_TOKEN = os.getenv("DISCOGS_TOKEN")

HEADERS = {
    "User-Agent": "KorndogDealHunter/1.0 +https://korndogrecords.com",
    "Accept": "application/json",
}

def set_discogs_token(token: str):
    global DISCOGS_TOKEN
    DISCOGS_TOKEN = token

def clean_text(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"\[[^]]*\]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def fuzzy_match(a: str, b: str) -> float:
    a, b = clean_text(a), clean_text(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 0.92
    return SequenceMatcher(None, a, b).ratio()

def split_discogs_title(full_title: str):
    """
    Discogs search often returns: Artist - Album Title
    """
    full_title = full_title or ""
    if " - " in full_title:
        artist, title = full_title.split(" - ", 1)
        return artist.strip(), title.strip()
    return "", full_title.strip()

def discogs_get(path: str, params: Optional[Dict] = None) -> Optional[Dict]:
    if not DISCOGS_TOKEN:
        print("Missing DISCOGS_TOKEN")
        return None

    params = params or {}
    params["token"] = DISCOGS_TOKEN

    try:
        url = f"{DISCOGS_API_BASE}{path}"
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)

        if r.status_code == 429:
            print("Discogs rate limited. Sleeping 60 seconds.")
            time.sleep(60)
            r = requests.get(url, headers=HEADERS, params=params, timeout=15)

        r.raise_for_status()
        return r.json()

    except Exception as e:
        print(f"Discogs API error on {path}: {e}")
        return None

def validate_discogs_match(source_data: Dict, discogs_result: Dict) -> Dict:
    source_artist = source_data.get("artist", "")
    source_title = source_data.get("title", "")

    result_full_title = discogs_result.get("title", "")
    result_artist, result_title = split_discogs_title(result_full_title)

    title_score = fuzzy_match(source_title, result_title)
    artist_score = fuzzy_match(source_artist, result_artist)

    confidence = round((title_score * 0.65) + (artist_score * 0.35), 4)

    is_valid = (
        title_score >= 0.72 and artist_score >= 0.60
    ) or confidence >= 0.78

    return {
        "is_valid": is_valid,
        "confidence": confidence,
        "reason": "matched" if is_valid else "low_confidence",
        "discogs_artist": result_artist,
        "discogs_title": result_title,
    }

def search_discogs(artist: str, title: str) -> Optional[Dict]:
    query = f"{artist} {title}".strip()

    data = discogs_get("/database/search", {
        "q": query,
        "type": "release",
        "format": "Vinyl",
        "per_page": 10,
    })

    results = data.get("results", []) if data else []
    if not results:
        return None

    source = {"artist": artist, "title": title}

    scored = []
    for item in results:
        validation = validate_discogs_match(source, item)
        scored.append((validation["confidence"], item, validation))

    scored.sort(key=lambda x: x[0], reverse=True)

    best_confidence, best_item, best_validation = scored[0]
    best_item["_validation"] = best_validation
    return best_item

def get_release_stats(release_id: int) -> Dict:
    release = discogs_get(f"/releases/{release_id}") or {}

    lowest_price = 0
    num_for_sale = 0
    community_have = 0
    community_want = 0

    if isinstance(release.get("lowest_price"), (int, float)):
        lowest_price = release.get("lowest_price", 0)

    community = release.get("community", {}) or {}
    community_have = community.get("have", 0)
    community_want = community.get("want", 0)

    # Some Discogs responses include this at release level
    if isinstance(release.get("num_for_sale"), int):
        num_for_sale = release.get("num_for_sale", 0)

    return {
        "discogs_lowest": lowest_price or 0,
        "discogs_num_for_sale": num_for_sale or 0,
        "discogs_have": community_have or 0,
        "discogs_want": community_want or 0,
    }

def enrich_with_discogs(deal: Dict, cache: Optional[Dict] = None) -> Dict:
    cache = cache or {}

    artist = deal.get("artist", "").strip()
    title = deal.get("title", "").strip()
    cache_key = f"{artist}|{title}"

    if cache_key in cache:
        deal.update(cache[cache_key])
        return deal

    result = search_discogs(artist, title)

    if not result:
        enriched = {
            "discogs_found": False,
            "discogs_match_confidence": 0.0,
            "discogs_match_reason": "not_found",
            "discogs_url": "",
        }
        deal.update(enriched)
        cache[cache_key] = enriched
        return deal

    validation = result.get("_validation") or validate_discogs_match(deal, result)

    if not validation["is_valid"]:
        enriched = {
            "discogs_found": False,
            "discogs_match_confidence": validation["confidence"],
            "discogs_match_reason": validation["reason"],
            "discogs_url": "",
        }
        deal.update(enriched)
        cache[cache_key] = enriched
        return deal

    release_id = result.get("id")
    stats = get_release_stats(release_id) if release_id else {}

    discogs_url = result.get("uri", "")
    if discogs_url and discogs_url.startswith("/"):
        discogs_url = f"https://www.discogs.com{discogs_url}"

    enriched = {
        "discogs_found": True,
        "discogs_match_confidence": validation["confidence"],
        "discogs_match_reason": "matched",
        "discogs_artist": validation.get("discogs_artist", ""),
        "discogs_title": validation.get("discogs_title", ""),
        "discogs_release_id": release_id,
        "discogs_url": discogs_url,
        **stats,
    }

    deal.update(enriched)
    cache[cache_key] = enriched
    return deal

if __name__ == "__main__":
    set_discogs_token("YOUR_TOKEN_HERE")

    test_deal = {
        "artist": "Metallica",
        "title": "Master of Puppets",
        "price": 25.00,
    }

    cache = {}
    result = enrich_with_discogs(test_deal, cache)
    print(json.dumps(result, indent=2))
