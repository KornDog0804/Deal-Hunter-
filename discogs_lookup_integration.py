#!/usr/bin/env python3
"""
Discogs Lookup Integration with Match Validation & URL Capture
Enriches live deals with Discogs Mint pricing, confidence scoring, and marketplace URLs.
"""

import requests
import json
from difflib import SequenceMatcher
from typing import Optional, Dict, Any
from urllib.parse import quote

DISCOGS_TOKEN = None
DISCOGS_API_BASE = "https://api.discogs.com"

def set_discogs_token(token: str):
    """Set the Discogs API token."""
    global DISCOGS_TOKEN
    DISCOGS_TOKEN = token

def fuzzy_match(s1: str, s2: str) -> float:
    """Returns similarity score 0.0-1.0."""
    s1 = (s1 or "").lower().strip()
    s2 = (s2 or "").lower().strip()
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1, s2).ratio()

def validate_discogs_match(source_data: Dict, discogs_result: Dict) -> Dict:
    """
    Validate Discogs match against source data.
    Returns: {
        'is_valid': bool,
        'confidence': float (0.0-1.0),
        'reason': str
    }
    """
    source_title = (source_data.get('title') or "").lower().strip()
    source_artist = (source_data.get('artist') or "").lower().strip()
    
    discogs_title = (discogs_result.get('title') or "").lower().strip()
    discogs_artist = (discogs_result.get('artists_sort') or "").lower().strip()
    
    # Fuzzy match thresholds
    title_match = fuzzy_match(source_title, discogs_title)
    artist_match = fuzzy_match(source_artist, discogs_artist)
    
    # Combined confidence: title 60%, artist 40%
    confidence = (title_match * 0.6) + (artist_match * 0.4)
    
    # Decision logic
    is_valid = (title_match >= 0.70 and artist_match >= 0.75) or confidence >= 0.80
    
    return {
        'is_valid': is_valid,
        'confidence': confidence,
        'reason': 'matched' if is_valid else 'low_confidence'
    }

def get_discogs_marketplace_url(release_id: int, title: str) -> str:
    """
    Build Discogs marketplace URL for a release.
    Example: https://www.discogs.com/release/123456-Artist-Title
    """
    if not release_id:
        return ""
    # Create URL-safe title slug
    title_slug = quote((title or "").replace(' ', '-').lower())
    return f"https://www.discogs.com/release/{release_id}-{title_slug}"

def search_discogs(artist: str, title: str) -> Optional[Dict]:
    """
    Search Discogs API for a record.
    Returns the top result or None if not found.
    """
    if not DISCOGS_TOKEN:
        return None
    
    try:
        query = f"{artist} {title}"
        url = f"{DISCOGS_API_BASE}/database/search"
        params = {
            'q': query,
            'type': 'release',
            'token': DISCOGS_TOKEN,
            'per_page': 5
        }
        
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get('results'):
            return data['results'][0]
        return None
    except Exception as e:
        print(f"Discogs search error: {e}")
        return None

def enrich_with_discogs(deal: Dict, cache: Optional[Dict] = None) -> Dict:
    """
    Enrich a deal with Discogs data.
    Uses cache if available to avoid redundant API calls.
    """
    if cache is None:
        cache = {}
    
    artist = deal.get('artist', '')
    title = deal.get('title', '')
    cache_key = f"{artist}|{title}"
    
    # Check cache first
    if cache_key in cache:
        cached_data = cache[cache_key]
        deal.update(cached_data)
        return deal
    
    # Search Discogs
    discogs_result = search_discogs(artist, title)
    
    if not discogs_result:
        # No match found
        deal.update({
            'discogs_found': False,
            'discogs_match_confidence': 0.0,
            'discogs_match_reason': 'not_found',
            'discogs_url': ''
        })
        cache[cache_key] = {
            'discogs_found': False,
            'discogs_match_confidence': 0.0,
            'discogs_match_reason': 'not_found',
            'discogs_url': ''
        }
        return deal
    
    # Validate match
    validation = validate_discogs_match(deal, discogs_result)
    
    if not validation['is_valid']:
        deal.update({
            'discogs_found': False,
            'discogs_match_confidence': validation['confidence'],
            'discogs_match_reason': validation['reason'],
            'discogs_url': ''
        })
        cache[cache_key] = {
            'discogs_found': False,
            'discogs_match_confidence': validation['confidence'],
            'discogs_match_reason': validation['reason'],
            'discogs_url': ''
        }
        return deal
    
    # Get mint pricing from marketplace
    try:
        release_id = discogs_result.get('id')
        marketplace_url = f"{DISCOGS_API_BASE}/releases/{release_id}/stats"
        resp = requests.get(marketplace_url, params={'token': DISCOGS_TOKEN}, timeout=10)
        resp.raise_for_status()
        stats = resp.json()
        
        mint_price = stats.get('price', {}).get('value', 0)
        lowest_price = stats.get('lowest_price', {}).get('value', 0)
        num_for_sale = stats.get('num_for_sale', 0)
        
    except Exception as e:
        print(f"Discogs stats error: {e}")
        mint_price = 0
        lowest_price = 0
        num_for_sale = 0
    
    # Build Discogs URL
    discogs_url = get_discogs_marketplace_url(
        discogs_result.get('id'),
        discogs_result.get('title', '')
    )
    
    # Update deal
    enriched_data = {
        'discogs_found': True,
        'discogs_match_confidence': validation['confidence'],
        'discogs_match_reason': validation['reason'],
        'discogs_mint_price': mint_price,
        'discogs_lowest': lowest_price,
        'discogs_num_for_sale': num_for_sale,
        'discogs_url': discogs_url
    }
    
    deal.update(enriched_data)
    cache[cache_key] = enriched_data
    
    return deal

if __name__ == '__main__':
    # Test
    set_discogs_token('YOUR_TOKEN_HERE')
    test_deal = {
        'artist': 'Metallica',
        'title': 'Master of Puppets',
        'price': 25.00
    }
    result = enrich_with_discogs(test_deal)
    print(json.dumps(result, indent=2))
