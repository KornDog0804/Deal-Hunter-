#!/usr/bin/env python3
import os
import re
import json
import time
import requests
from difflib import SequenceMatcher
from typing import Optional, Dict, Tuple

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

def search_discogs(artist: str, title: str) -> Optional[Dict]:
    artist = str(artist or "").strip()
    title = str(title or "").strip()

    if not title:
        return None

    queries = []

    if artist:
        queries.append({"artist": artist, "release_title": title})
        queries.append({"q": f"{artist} {title}"})

    queries.append({"q": title})

    best = None

    for query_params in queries:
        params = {
            **query_params,
            "type": "release",
            "format": "Vinyl",
            "per_page": 10,
        }

        data = discogs_get("/database/search", params)
        results = data.get("results", []) if data else []

        for item in results:
            validation = validate_discogs_match(artist, title, item)

            scored_item = {
                "confidence": validation["confidence"],
                "item": item,
                "validation": validation,
            }

            if best is None or scored_item["confidence"] > best["confidence"]:
                best = scored_item

        if best and best["confidence"] >= 0.86:
            break

    if not best:
        return None

    item = best["item"]
    item["_validation"] = best["validation"]
    return item

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
        "discogs_mint_price": mint_price,
        "discogs_lowest": lowest_price,
        "discogs_num_for_sale": num_for_sale,
        "discogs_have": have,
        "discogs_want": want,
    }

def enrich_with_discogs(deal: Dict, cache: Optional[Dict] = None) -> Dict:
    cache = cache if cache is not None else {}

    artist, title = get_discogs_search_parts(deal)

    cache_key = f"{clean_text(artist)}|{clean_text(title)}"

    if cache_key in cache:
        deal.update(cache[cache_key])
        return deal

    if not title:
        enriched = {
            "discogs_found": False,
            "discogs_match_confidence": 0.0,
            "discogs_match_reason": "missing_title",
            "discogs_url": "",
            "discogs_mint_price": 0,
            "discogs_lowest": 0,
            "discogs_num_for_sale": 0,
        }
        deal.update(enriched)
        cache[cache_key] = enriched
        return deal

    result = search_discogs(artist, title)

    if not result:
        enriched = {
            "discogs_found": False,
            "discogs_match_confidence": 0.0,
            "discogs_match_reason": "not_found",
            "discogs_url": "",
            "discogs_mint_price": 0,
            "discogs_lowest": 0,
            "discogs_num_for_sale": 0,
        }
        deal.update(enriched)
        cache[cache_key] = enriched
        return deal

    validation = result.get("_validation") or validate_discogs_match(artist, title, result)

    if not validation["is_valid"]:
        enriched = {
            "discogs_found": False,
            "discogs_match_confidence": validation["confidence"],
            "discogs_match_reason": validation["reason"],
            "discogs_url": "",
            "discogs_mint_price": 0,
            "discogs_lowest": 0,
            "discogs_num_for_sale": 0,
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
    set_discogs_token(os.getenv("DISCOGS_TOKEN") or "YOUR_TOKEN_HERE")

    test_deal = {
        "artist": "WARNER",
        "title": "TYPE O NEGATIVE - BLOODY KISSES: SUSPENDED IN DUSK 2LP (Viridian Void Vinyl)",
        "price": 41.99,
    }

    cache = {}
    result = enrich_with_discogs(test_deal, cache)
    print(json.dumps(result, indent=2))
