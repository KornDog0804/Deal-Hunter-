#!/usr/bin/env python3
"""
Build Discogs Cache - Enriches live_deals.json with Discogs marketplace data.
Includes rate limiting to respect Discogs API limits.
"""

import os
import json
import time
import requests
from typing import Dict, List, Any
from difflib import SequenceMatcher
from urllib.parse import quote

DISCOGS_TOKEN = os.getenv('DISCOGS_TOKEN')
DISCOGS_API_BASE = "https://api.discogs.com"
REQUEST_DELAY = 1.5  # Delay between requests in seconds

def fuzzy_match(s1: str, s2: str) -> float:
    """Returns similarity score 0.0-1.0."""
    s1 = (s1 or "").lower().strip()
    s2 = (s2 or "").lower().strip()
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1, s2).ratio()

def validate_discogs_match(source_data: Dict, discogs_result: Dict) -> Dict:
    """Validate Discogs match against source data."""
    source_title = (source_data.get('title') or "").lower().strip()
    source_artist = (source_data.get('artist') or "").lower().strip()
    
    discogs_title = (discogs_result.get('title') or "").lower().strip()
    discogs_artist = (discogs_result.get('artists_sort') or "").lower().strip()
    
    title_match = fuzzy_match(source_title, discogs_title)
    artist_match = fuzzy_match(source_artist, discogs_artist)
    
    confidence = (title_match * 0.6) + (artist_match * 0.4)
    is_valid = (title_match >= 0.70 and artist_match >= 0.75) or confidence >= 0.80
    
    return {
        'is_valid': is_valid,
        'confidence': confidence,
        'reason': 'matched' if is_valid else 'low_confidence'
    }

def get_discogs_marketplace_url(release_id: int, title: str) -> str:
    """Build Discogs marketplace URL for a release."""
    if not release_id:
        return ""
    title_slug = quote((title or "").replace(' ', '-').lower())
    return f"https://www.discogs.com/release/{release_id}-{title_slug}"

def search_discogs(artist: str, title: str) -> Dict[str, Any]:
    """Search Discogs API for a record with rate limiting."""
    if not DISCOGS_TOKEN:
        print("⚠️  DISCOGS_TOKEN not set")
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
        
        time.sleep(REQUEST_DELAY)  # Rate limiting
        
        resp = requests.get(url, params=params, timeout=10)
        
        if resp.status_code == 429:
            print(f"⚠️  Rate limited by Discogs. Waiting 5 seconds...")
            time.sleep(5)
            resp = requests.get(url, params=params, timeout=10)
        
        resp.raise_for_status()
        data = resp.json()
        
        if data.get('results'):
            return data['results'][0]
        return None
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Discogs search error for '{query}': {e}")
        return None

def get_discogs_stats(release_id: int) -> Dict[str, Any]:
    """Get Discogs marketplace stats with rate limiting."""
    if not DISCOGS_TOKEN:
        return {}
    
    try:
        marketplace_url = f"{DISCOGS_API_BASE}/releases/{release_id}/stats"
        
        time.sleep(REQUEST_DELAY)  # Rate limiting
        
        resp = requests.get(marketplace_url, params={'token': DISCOGS_TOKEN}, timeout=10)
        
        if resp.status_code == 429:
            print(f"⚠️  Rate limited by Discogs. Waiting 5 seconds...")
            time.sleep(5)
            resp = requests.get(marketplace_url, params={'token': DISCOGS_TOKEN}, timeout=10)
        
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Discogs stats error for release {release_id}: {e}")
        return {}

def enrich_deal_with_discogs(deal: Dict, cache: Dict, search_count: int) -> tuple:
    """Enrich a single deal with Discogs data. Returns (updated_deal, new_search_count)."""
    artist = deal.get('artist', '')
    title = deal.get('title', '')
    cache_key = f"{artist}|{title}"
    
    if cache_key in cache:
        cached_data = cache[cache_key]
        deal.update(cached_data)
        return deal, search_count
    
    discogs_result = search_discogs(artist, title)
    search_count += 1
    
    if not discogs_result:
        enriched = {
            'discogs_found': False,
            'discogs_match_confidence': 0.0,
            'discogs_match_reason': 'not_found',
            'discogs_url': ''
        }
        deal.update(enriched)
        cache[cache_key] = enriched
        return deal, search_count
    
    validation = validate_discogs_match(deal, discogs_result)
    
    if not validation['is_valid']:
        enriched = {
            'discogs_found': False,
            'discogs_match_confidence': validation['confidence'],
            'discogs_match_reason': validation['reason'],
            'discogs_url': ''
        }
        deal.update(enriched)
        cache[cache_key] = enriched
        return deal, search_count
    
    release_id = discogs_result.get('id')
    stats = get_discogs_stats(release_id)
    
    mint_price = stats.get('price', {}).get('value', 0) if stats else 0
    lowest_price = stats.get('lowest_price', {}).get('value', 0) if stats else 0
    num_for_sale = stats.get('num_for_sale', 0) if stats else 0
    
    discogs_url = get_discogs_marketplace_url(
        discogs_result.get('id'),
        discogs_result.get('title', '')
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
    
    return deal, search_count

def main():
    """Main function to build Discogs cache."""
    print("🎯 Starting Discogs Cache Builder (with rate limiting)...")
    print(f"   Request delay: {REQUEST_DELAY}s between API calls\n")
    
    if not DISCOGS_TOKEN:
        print("❌ DISCOGS_TOKEN environment variable not set!")
        return
    
    # Load live_deals.json
    try:
        with open('live_deals.json', 'r') as f:
            deals = json.load(f)
        print(f"✅ Loaded {len(deals)} deals from live_deals.json")
    except FileNotFoundError:
        print("❌ live_deals.json not found!")
        return
    except json.JSONDecodeError:
        print("❌ live_deals.json is not valid JSON!")
        return
    
    # Load existing cache
    cache = {}
    try:
        with open('discogs_cache.json', 'r') as f:
            cache = json.load(f)
        print(f"✅ Loaded {len(cache)} cached entries")
    except FileNotFoundError:
        print("📝 No existing cache, starting fresh")
    
    # Enrich deals
    enriched_count = 0
    search_count = 0
    start_time = time.time()
    
    for i, deal in enumerate(deals):
        deal, search_count = enrich_deal_with_discogs(deal, cache, search_count)
        if deal.get('discogs_found'):
            enriched_count += 1
        
        if (i + 1) % 50 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"⏳ Processed {i + 1}/{len(deals)} deals... ({rate:.1f} deals/sec, {search_count} API searches)")
    
    # Save enriched deals
    try:
        with open('live_deals.json', 'w') as f:
            json.dump(deals, f, indent=2)
        print(f"✅ Saved {len(deals)} enriched deals to live_deals.json")
    except Exception as e:
        print(f"❌ Failed to save live_deals.json: {e}")
        return
    
    # Save cache
    try:
        with open('discogs_cache.json', 'w') as f:
            json.dump(cache, f, indent=2)
        print(f"✅ Saved {len(cache)} cache entries to discogs_cache.json")
    except Exception as e:
        print(f"❌ Failed to save discogs_cache.json: {e}")
        return
    
    total_time = time.time() - start_time
    
    print(f"\n🎉 Discogs enrichment complete!")
    print(f"   Total deals: {len(deals)}")
    print(f"   Enriched with Discogs: {enriched_count}")
    print(f"   New API searches: {search_count}")
    print(f"   Cache size: {len(cache)}")
    print(f"   Total time: {total_time:.1f}s")

if __name__ == '__main__':
    main()
