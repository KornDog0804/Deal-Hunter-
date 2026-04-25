#!/usr/bin/env python3
"""
Build Discogs Cache - OPTIMIZED for speed and reliability.
Relaxed matching thresholds, minimal delays, aggressive timeout handling.
"""

import os
import json
import time
import requests
from typing import Dict, Any
from difflib import SequenceMatcher
from urllib.parse import quote

DISCOGS_TOKEN = os.getenv('DISCOGS_TOKEN')
DISCOGS_API_BASE = "https://api.discogs.com"
REQUEST_DELAY = 0.3  # Fast delays
REQUEST_TIMEOUT = 5  # Aggressive timeout

print("🎯 Starting Discogs Cache Builder (OPTIMIZED)...")

def fuzzy_match(s1: str, s2: str) -> float:
    """Returns similarity score 0.0-1.0."""
    s1 = (s1 or "").lower().strip()
    s2 = (s2 or "").lower().strip()
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1, s2).ratio()

def validate_discogs_match(source_data: Dict, discogs_result: Dict) -> Dict:
    """Validate Discogs match against source data. RELAXED thresholds."""
    source_title = (source_data.get('title') or "").lower().strip()
    source_artist = (source_data.get('artist') or "").lower().strip()
    
    discogs_title = (discogs_result.get('title') or "").lower().strip()
    discogs_artist = (discogs_result.get('artists_sort') or "").lower().strip()
    
    title_match = fuzzy_match(source_title, discogs_title)
    artist_match = fuzzy_match(source_artist, discogs_artist)
    
    confidence = (title_match * 0.6) + (artist_match * 0.4)
    
    # Relaxed: 60% title + 65% artist, OR 70% combined
    is_valid = (title_match >= 0.60 and artist_match >= 0.65) or confidence >= 0.70
    
    return {
        'is_valid': is_valid,
        'confidence': confidence,
        'reason': 'matched' if is_valid else 'low_confidence'
    }

def get_discogs_marketplace_url(release_id: int, title: str) -> str:
    """Build Discogs marketplace URL."""
    if not release_id:
        return ""
    title_slug = quote((title or "").replace(' ', '-').lower())
    return f"https://www.discogs.com/release/{release_id}-{title_slug}"

def search_discogs(artist: str, title: str) -> Dict[str, Any]:
    """Search Discogs API with aggressive timeout."""
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
        
        time.sleep(REQUEST_DELAY)
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get('results'):
            return data['results'][0]
        return None
    except Exception as e:
        return None

def get_discogs_stats(release_id: int) -> Dict[str, Any]:
    """Get Discogs marketplace stats."""
    if not DISCOGS_TOKEN:
        return {}
    
    try:
        url = f"{DISCOGS_API_BASE}/releases/{release_id}/stats"
        time.sleep(REQUEST_DELAY)
        resp = requests.get(url, params={'token': DISCOGS_TOKEN}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {}

def enrich_deal(deal: Dict, cache: Dict) -> tuple:
    """Enrich a deal with Discogs data."""
    artist = deal.get('artist', '')
    title = deal.get('title', '')
    cache_key = f"{artist}|{title}"
    
    # Check cache first
    if cache_key in cache:
        deal.update(cache[cache_key])
        return deal, False
    
    # Search Discogs
    result = search_discogs(artist, title)
    
    if not result:
        enriched = {
            'discogs_found': False,
            'discogs_match_confidence': 0.0,
            'discogs_match_reason': 'not_found',
            'discogs_url': ''
        }
        deal.update(enriched)
        cache[cache_key] = enriched
        return deal, False
    
    # Validate match
    validation = validate_discogs_match(deal, result)
    
    if not validation['is_valid']:
        enriched = {
            'discogs_found': False,
            'discogs_match_confidence': validation['confidence'],
            'discogs_match_reason': validation['reason'],
            'discogs_url': ''
        }
        deal.update(enriched)
        cache[cache_key] = enriched
        return deal, False
    
    # Get stats
    release_id = result.get('id')
    stats = get_discogs_stats(release_id)
    
    mint_price = stats.get('price', {}).get('value', 0) if stats else 0
    lowest_price = stats.get('lowest_price', {}).get('value', 0) if stats else 0
    num_for_sale = stats.get('num_for_sale', 0) if stats else 0
    
    discogs_url = get_discogs_marketplace_url(
        discogs_result=result.get('id'),
        title=result.get('title', '')
    )
    
    enriched = {
        'discogs_found': True,
        'discogs_match_confidence': validation['confidence'],
        'discogs_match_reason': validation['reason'],
        'discogs_mint_price': mint_price,
        'discogs_lowest': lowest_price,
        'discogs_num_for_sale': num_for_sale,
        'discogs_url': discogs_url
    }
    
    deal.update(enriched)
    cache[cache_key] = enriched
    return deal, True

def main():
    if not DISCOGS_TOKEN:
        print("❌ DISCOGS_TOKEN not set!")
        return
    
    # Load deals
    try:
        with open('live_deals.json', 'r') as f:
            deals = json.load(f)
        print(f"✅ Loaded {len(deals)} deals")
    except Exception as e:
        print(f"❌ Error loading deals: {e}")
        return
    
    # Load cache
    cache = {}
    try:
        with open('discogs_cache.json', 'r') as f:
            cache = json.load(f)
        print(f"✅ Loaded {len(cache)} cached entries")
    except FileNotFoundError:
        print("📝 Starting with fresh cache")
    
    # Process deals
    enriched_count = 0
    start_time = time.time()
    
    for i, deal in enumerate(deals):
        deal, was_enriched = enrich_deal(deal, cache)
        if was_enriched:
            enriched_count += 1
        
        # Progress every 100 deals
        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            pct = ((i + 1) / len(deals)) * 100
            print(f"⏳ {i + 1}/{len(deals)} ({pct:.0f}%) | Enriched: {enriched_count} | {rate:.1f} deals/sec")
    
    # Save results
    try:
        with open('live_deals.json', 'w') as f:
            json.dump(deals, f, indent=2)
        print(f"✅ Saved {len(deals)} deals")
    except Exception as e:
        print(f"❌ Error saving deals: {e}")
        return
    
    try:
        with open('discogs_cache.json', 'w') as f:
            json.dump(cache, f, indent=2)
        print(f"✅ Saved {len(cache)} cache entries")
    except Exception as e:
        print(f"❌ Error saving cache: {e}")
        return
    
    total_time = time.time() - start_time
    
    print(f"\n🎉 Complete!")
    print(f"   Deals: {len(deals)}")
    print(f"   Enriched: {enriched_count}")
    print(f"   Cache size: {len(cache)}")
    print(f"   Time: {total_time:.1f}s")

if __name__ == '__main__':
    main()
