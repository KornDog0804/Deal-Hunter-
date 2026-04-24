# =====================================================
# DISCOGS REAL API LOOKUP INTEGRATION
# With Match Validation - Filters Bad Matches
# =====================================================

import urllib.request
import urllib.error
import urllib.parse
import json
import time
import math
import difflib
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone

# Your token from environment or hardcoded (use env var in production!)
DISCOGS_TOKEN = "pQZkNeqJhFJrNaYCiHkalTRbZIuqGqDohKryLQwk"
DISCOGS_API_BASE = "https://api.discogs.com"

# Match confidence thresholds
MIN_TITLE_MATCH = 0.70  # 70% fuzzy match on title
MIN_ARTIST_MATCH = 0.75  # 75% fuzzy match on artist

# Rate limit tracking (60-second moving window)
class DiscogRateLimiter:
    def __init__(self, max_per_minute: int = 240):
        self.max_per_minute = max_per_minute
        self.remaining = max_per_minute
        self.reset_time = None
    
    def update_from_headers(self, headers: dict) -> None:
        """Update state from Discogs response headers."""
        try:
            remaining_str = headers.get("X-Discogs-Ratelimit-Remaining", "").strip()
            if remaining_str:
                self.remaining = int(remaining_str)
        except Exception:
            pass
    
    def should_sleep(self) -> float:
        """Return sleep duration in seconds, or 0 if we can proceed."""
        if self.remaining > 10:  # Keep 10 requests as buffer
            return 0.0
        # If under 10, back off for 0.5 seconds
        return 0.5
    
    def is_available(self) -> bool:
        """Check if we can make a request."""
        return self.remaining > 0


_rate_limiter = DiscogRateLimiter()


def fuzzy_match(source: str, target: str) -> float:
    """
    Calculate similarity ratio between two strings (0.0 to 1.0).
    Higher = better match.
    """
    if not source or not target:
        return 0.0
    
    # Normalize: lowercase, strip whitespace
    s = str(source).lower().strip()
    t = str(target).lower().strip()
    
    # Quick exact match
    if s == t:
        return 1.0
    
    # Fuzzy match using difflib
    ratio = difflib.SequenceMatcher(None, s, t).ratio()
    return ratio


def validate_discogs_match(
    source_artist: str,
    source_title: str,
    discogs_result: Dict[str, Any],
) -> Tuple[bool, float, str]:
    """
    Validate if Discogs result matches the source record.
    
    Returns (is_valid, confidence, reason)
    - is_valid: True if match is confident enough
    - confidence: 0.0-1.0 score
    - reason: human-readable explanation
    """
    if not discogs_result:
        return False, 0.0, "no_result"
    
    discogs_title = discogs_result.get("title", "").strip()
    discogs_artist = discogs_result.get("basic_information", {}).get("artists", [{}])[0].get("name", "").strip()
    
    if not discogs_title:
        return False, 0.0, "no_title"
    
    # Title match is critical
    title_match = fuzzy_match(source_title, discogs_title)
    
    # Artist match is secondary (helps validate)
    artist_match = 1.0  # Default to high confidence if no artist provided
    if source_artist:
        artist_match = fuzzy_match(source_artist, discogs_artist)
    
    # Combined confidence: weight title higher (60%) than artist (40%)
    combined_confidence = (title_match * 0.6) + (artist_match * 0.4)
    
    # Decision logic
    if title_match < MIN_TITLE_MATCH:
        reason = f"title_mismatch ({title_match:.0%})"
        return False, combined_confidence, reason
    
    if source_artist and artist_match < MIN_ARTIST_MATCH:
        reason = f"artist_weak ({artist_match:.0%})"
        # Return True but with lower confidence (still valid, just weak artist match)
        return True, combined_confidence, reason
    
    reason = "matched"
    return True, combined_confidence, reason


def discogs_fetch(endpoint: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict]]:
    """
    Fetch from Discogs API with rate limit awareness.
    Returns (data_dict, response_headers) or (None, None) on error.
    """
    global _rate_limiter
    
    sleep_time = _rate_limiter.should_sleep()
    if sleep_time > 0:
        time.sleep(sleep_time)
    
    url = f"{DISCOGS_API_BASE}{endpoint}?token={DISCOGS_TOKEN}"
    
    try:
        headers = {
            "User-Agent": "KornDogDealHunter/1.0 (+http://korndogrecords.com)",
            "Accept": "application/json",
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            
            # Extract response headers for rate limit tracking
            response_headers = dict(resp.headers)
            _rate_limiter.update_from_headers(response_headers)
            
            return data, response_headers
    
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(f"[Discogs] Rate limited! Sleeping 30s...")
            time.sleep(30)
            return None, None
        if e.code == 404:
            return None, None
        print(f"[Discogs] HTTP {e.code}: {e.reason}")
        return None, None
    
    except Exception as e:
        print(f"[Discogs] Fetch error: {e}")
        return None, None


def search_discogs(artist: str, title: str) -> Optional[Dict[str, Any]]:
    """
    Search Discogs for a record.
    Returns the first matching result or None.
    """
    query = f"{artist} {title}".strip()
    search_url = f"/database/search?q={urllib.parse.quote(query)}&type=release"
    
    try:
        data, _ = discogs_fetch(search_url)
    except Exception:
        data = None
    
    if not data or "results" not in data:
        return None
    
    results = data.get("results", [])
    if not results:
        return None
    
    # Return first result (usually best match)
    return results[0]


def get_release_details(release_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetch full release details from Discogs.
    Returns dict with price_suggestions and other metadata.
    """
    details_url = f"/releases/{release_id}"
    
    try:
        data, _ = discogs_fetch(details_url)
    except Exception:
        data = None
    
    return data


def extract_mint_price(release_data: Dict[str, Any]) -> Tuple[float, Optional[str]]:
    """
    Extract Mint (M) condition price from release data.
    Returns (price, condition_found)
    Fallback: NM > VG+ > VG if Mint unavailable.
    """
    if "price_suggestions" not in release_data:
        return 0.0, None
    
    suggestions = release_data.get("price_suggestions", {})
    
    # Priority order: Mint, Near Mint, Very Good+, Very Good
    priority_conditions = [
        ("Mint (M)", "Mint (M)"),
        ("Near Mint (NM or M-)", "Near Mint (NM)"),
        ("Very Good Plus (VG+)", "Very Good Plus (VG+)"),
        ("Very Good (VG)", "Very Good (VG)"),
    ]
    
    for api_key, display_name in priority_conditions:
        if api_key in suggestions:
            price_obj = suggestions[api_key]
            if isinstance(price_obj, dict):
                value = price_obj.get("value", 0.0)
            else:
                value = float(price_obj) if price_obj else 0.0
            
            if value > 0:
                return float(value), display_name
    
    return 0.0, None


def extract_lowest_price(release_data: Dict[str, Any]) -> float:
    """Extract lowest active listing price."""
    lowest = release_data.get("lowest_price", 0.0)
    return float(lowest) if lowest else 0.0


def extract_num_for_sale(release_data: Dict[str, Any]) -> int:
    """Extract number of listings available."""
    num = release_data.get("num_for_sale", 0)
    return int(num) if num else 0


def real_discogs_lookup(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Real Discogs lookup with MATCH VALIDATION.
    Only returns high-confidence matches.
    
    Returns dict with:
    {
        "found": bool,
        "match_confidence": float,      # 0.0-1.0
        "match_reason": str,            # why match succeeded/failed
        "discogs_mint_price": float,    # Only if found=True
        "discogs_mint_condition": str,
        "discogs_lowest": float,
        "discogs_num_for_sale": int,
        "discogs_release_id": int,
        "search_query": str,
    }
    """
    artist = str(record.get("artist", "")).strip()
    title = str(record.get("title", "")).strip()
    
    if not artist or not title:
        return {
            "found": False,
            "match_confidence": 0.0,
            "match_reason": "missing_metadata",
            "search_query": f"{artist} {title}".strip(),
        }
    
    # Search for the record
    search_result = search_discogs(artist, title)
    
    if not search_result:
        return {
            "found": False,
            "match_confidence": 0.0,
            "match_reason": "no_search_results",
            "search_query": f"{artist} {title}",
        }
    
    # VALIDATE the match before proceeding
    is_valid, confidence, reason = validate_discogs_match(
        artist, title, search_result
    )
    
    if not is_valid:
        # Match confidence too low, reject this result
        return {
            "found": False,
            "match_confidence": confidence,
            "match_reason": reason,
            "search_query": f"{artist} {title}",
        }
    
    release_id = search_result.get("id")
    if not release_id:
        return {
            "found": False,
            "match_confidence": confidence,
            "match_reason": "no_release_id",
            "search_query": f"{artist} {title}",
        }
    
    # Fetch full details
    release_data = get_release_details(release_id)
    
    if not release_data:
        return {
            "found": False,
            "match_confidence": confidence,
            "match_reason": "no_release_details",
            "discogs_release_id": release_id,
            "search_query": f"{artist} {title}",
        }
    
    # Extract pricing
    mint_price, mint_condition = extract_mint_price(release_data)
    lowest_price = extract_lowest_price(release_data)
    num_for_sale = extract_num_for_sale(release_data)
    
    # Fallback: if no Mint price but lowest exists, use lowest as reference
    if mint_price <= 0 and lowest_price > 0:
        mint_price = lowest_price
        mint_condition = "Lowest Listed"
    
    return {
        "found": mint_price > 0 or lowest_price > 0,
        "match_confidence": confidence,
        "match_reason": reason,
        "discogs_mint_price": mint_price,
        "discogs_mint_condition": mint_condition or "No pricing",
        "discogs_lowest": lowest_price,
        "discogs_num_for_sale": num_for_sale,
        "discogs_release_id": release_id,
        "discogs_title_match": search_result.get("title", ""),
        "search_query": f"{artist} {title}",
    }


def enrich_candidates_with_discogs_lookup(
    candidates: List[Dict[str, Any]],
    cache: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Enrich all candidates with REAL Discogs Mint pricing.
    Uses match validation to filter bad matches.
    """
    enriched_results: List[Dict[str, Any]] = []
    
    for idx, candidate in enumerate(candidates):
        # Build base scoring (this stays the same)
        base_result = {
            "base_score": candidate.get("base_score", 0),
            "lane": candidate.get("lane", "PASS"),
            "rarity_keyword_count": candidate.get("rarity_keyword_count", 0),
            "source_normalized": candidate.get("source_normalized", ""),
            "search_blob": candidate.get("search_blob", ""),
            "breakdown": candidate.get("breakdown", {}),
        }
        
        # Check cache first
        cache_key = f"{candidate.get('artist', '')}::{candidate.get('title', '')}"
        discogs_result = None
        
        if cache and cache_key in cache:
            cached = cache[cache_key]
            discogs_result = cached
        else:
            # Do the real lookup
            discogs_result = real_discogs_lookup(candidate)
            
            # Update cache
            if cache is not None:
                cache[cache_key] = discogs_result
        
        # Apply Discogs enrichment (with validation)
        enriched = apply_discogs_enrichment(candidate, base_result, discogs_result)
        merged = {**candidate, **enriched}
        enriched_results.append(merged)
        
        # Progress indicator
        if (idx + 1) % 50 == 0:
            print(f"[Discogs] Processed {idx + 1}/{len(candidates)} records...")
    
    return enriched_results


def apply_discogs_enrichment(
    record: Dict[str, Any],
    base_result: Dict[str, Any],
    discogs_result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Apply Discogs score boost to base score.
    Only boosts if match confidence is high.
    """
    enriched = dict(base_result)
    enriched["discogs_checked"] = True
    enriched["discogs_found"] = discogs_result.get("found", False)
    enriched["discogs_boost"] = 0
    enriched["discogs_match_confidence"] = discogs_result.get("match_confidence", 0.0)
    enriched["discogs_match_reason"] = discogs_result.get("match_reason", "unknown")
    enriched["final_score"] = int(base_result["base_score"])
    enriched["final_lane"] = base_result["lane"]
    
    # Copy Discogs data
    enriched["discogs_mint_price"] = discogs_result.get("discogs_mint_price", 0.0)
    enriched["discogs_mint_condition"] = discogs_result.get("discogs_mint_condition", "")
    enriched["discogs_lowest"] = discogs_result.get("discogs_lowest", 0.0)
    enriched["discogs_num_for_sale"] = discogs_result.get("discogs_num_for_sale", 0)
    enriched["discogs_release_id"] = discogs_result.get("discogs_release_id", 0)
    
    if not discogs_result.get("found"):
        # No valid match found
        return enriched
    
    # Only apply boost if confidence is reasonable
    confidence = discogs_result.get("match_confidence", 0.0)
    if confidence < 0.70:  # Too low, don't boost
        return enriched
    
    current_price = float(record.get("price", 0.0))
    mint_price = discogs_result.get("discogs_mint_price", 0.0)
    lowest_price = discogs_result.get("discogs_lowest", 0.0)
    num_for_sale = discogs_result.get("discogs_num_for_sale", 0)
    
    boost = 0
    
    # MINT PRICE UPSIDE (primary signal)
    if current_price > 0 and mint_price > 0:
        ratio = mint_price / current_price
        if ratio >= 3.0:
            boost += 30  # Huge deal
        elif ratio >= 2.0:
            boost += 25  # Excellent deal
        elif ratio >= 1.5:
            boost += 18  # Very good deal
        elif ratio >= 1.2:
            boost += 10  # Good deal
        elif ratio >= 0.95:
            boost += 2   # Fair
        else:
            boost -= 20  # Overpriced
    
    # STOCK SIGNAL (supply = demand indicator)
    if num_for_sale >= 50:
        boost -= 5  # Saturated market
    elif num_for_sale >= 20:
        boost -= 2  # Adequate supply
    elif num_for_sale <= 3:
        boost += 8  # Rare/scarce
    
    # CONFIDENCE MULTIPLIER
    # High confidence (>0.85) = full boost
    # Medium confidence (0.70-0.85) = 50% boost
    if confidence < 0.85:
        boost = int(boost * 0.5)
    
    final_score = int(base_result["base_score"] + boost)
    final_lane = lane_from_discogs_score(final_score)
    
    enriched["discogs_boost"] = boost
    enriched["final_score"] = final_score
    enriched["final_lane"] = final_lane
    
    return enriched


def lane_from_discogs_score(score: int) -> str:
    """Determine buy lane from final Discogs-enriched score."""
    if score >= 90:
        return "TREASURE"
    if score >= 75:
        return "BUY NOW"
    if score >= 60:
        return "BUY LIGHT"
    if score >= 40:
        return "WATCH"
    return "PASS"
