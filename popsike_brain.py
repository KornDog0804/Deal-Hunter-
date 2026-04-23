"""
Real Popsike.com Scraper
Pulls actual eBay sold prices for vinyl records from popsike.com
Replaces fake_popsike_lookup() in popsike_brain.py
"""

import urllib.request
import urllib.parse
import time
import random
import re
import json
from datetime import datetime
from typing import Dict, Any, Optional, List

# ─────────────────────────────────────────────────────────────────
# POPSIKE SCRAPER
# ─────────────────────────────────────────────────────────────────

POPSIKE_BASE = "https://www.popsike.com"

# User agents to rotate
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
]


def fetch_popsike(url: str, retries: int = 3, delay: float = 2.0) -> Optional[str]:
    """
    Fetch a page from Popsike with rate limiting and retries.
    Returns HTML content or None if all retries fail.
    """
    for attempt in range(retries):
        try:
            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "identity",
                "Connection": "keep-alive",
                "Referer": POPSIKE_BASE,
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.read().decode("utf-8", "ignore")
        except Exception as e:
            print(f"[Popsike] Fetch failed (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    return None


def search_popsike(artist: str, title: str) -> Optional[str]:
    """
    Search Popsike for a record.
    Returns the search results page HTML or None if fetch fails.
    """
    # Build search query
    query = f"{artist} {title}".strip()
    search_url = f"{POPSIKE_BASE}/search.php?q={urllib.parse.quote_plus(query)}"
    
    print(f"[Popsike] Searching: {query}")
    return fetch_popsike(search_url, retries=2, delay=1.5)


def parse_popsike_results(html: str) -> List[Dict[str, Any]]:
    """
    Parse Popsike search results HTML.
    Extract sold listings with prices and dates.
    Returns list of dicts with price, date, quantity info.
    """
    listings = []
    
    if not html:
        return listings
    
    # Pattern: sold listings typically have price and date info
    # Popsike format varies, so we look for common patterns
    
    # Pattern 1: Price in dollar format
    price_pattern = r'\$(\d+(?:\.\d{2})?)'
    
    # Pattern 2: Date patterns (various formats)
    date_patterns = [
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',  # MM/DD/YYYY or DD-MM-YYYY
        r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}(?:,? \d{4})?)',  # Month DD, YYYY
    ]
    
    # Split HTML into potential listing blocks
    # Popsike typically has divs or rows for each listing
    listing_blocks = re.split(r'<(?:tr|div)[^>]*class="[^"]*(?:row|item|listing)[^"]*"[^>]*>', html)
    
    for block in listing_blocks[1:]:  # Skip first empty split
        try:
            # Extract price
            price_match = re.search(price_pattern, block)
            if not price_match:
                continue
            
            price = float(price_match.group(1))
            if price <= 0:
                continue
            
            # Extract date
            date_str = None
            for date_pat in date_patterns:
                date_match = re.search(date_pat, block, re.IGNORECASE)
                if date_match:
                    date_str = date_match.group(1)
                    break
            
            listings.append({
                "price": price,
                "date": date_str or "unknown",
            })
        except Exception as e:
            print(f"[Popsike] Parse error on block: {e}")
            continue
    
    return listings


def calculate_popsike_stats(listings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate average price, last price, and result count from listings.
    """
    if not listings:
        return {
            "found": False,
            "avg_price": 0.0,
            "last_price": 0.0,
            "result_count": 0,
            "last_sale_date": None,
        }
    
    prices = [l["price"] for l in listings if l.get("price", 0) > 0]
    
    if not prices:
        return {
            "found": False,
            "avg_price": 0.0,
            "last_price": 0.0,
            "result_count": len(listings),
            "last_sale_date": None,
        }
    
    avg_price = sum(prices) / len(prices)
    last_price = prices[-1] if prices else 0.0  # Most recent
    
    # Get most recent date if available
    dates = [l.get("date") for l in listings if l.get("date")]
    last_date = dates[-1] if dates else None
    
    return {
        "found": True,
        "avg_price": round(avg_price, 2),
        "last_price": round(last_price, 2),
        "result_count": len(listings),
        "last_sale_date": last_date,
    }


def real_popsike_lookup(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Real Popsike lookup that pulls actual eBay sold prices.
    
    Returns dict with:
    {
        "found": bool,
        "avg_price": float,
        "last_price": float,
        "result_count": int,
        "last_sale_date": str,
        "search_query": str,
    }
    """
    artist = str(record.get("artist", "")).strip()
    title = str(record.get("title", "")).strip()
    
    if not artist or not title:
        return {
            "found": False,
            "avg_price": 0.0,
            "last_price": 0.0,
            "result_count": 0,
            "last_sale_date": None,
            "search_query": f"{artist} {title}".strip(),
        }
    
    # Search Popsike
    search_html = search_popsike(artist, title)
    
    if not search_html:
        print(f"[Popsike] No results for {artist} - {title}")
        return {
            "found": False,
            "avg_price": 0.0,
            "last_price": 0.0,
            "result_count": 0,
            "last_sale_date": None,
            "search_query": f"{artist} {title}",
        }
    
    # Parse results
    listings = parse_popsike_results(search_html)
    
    if not listings:
        print(f"[Popsike] No sold listings parsed for {artist} - {title}")
        return {
            "found": False,
            "avg_price": 0.0,
            "last_price": 0.0,
            "result_count": 0,
            "last_sale_date": None,
            "search_query": f"{artist} {title}",
        }
    
    # Calculate stats
    stats = calculate_popsike_stats(listings)
    stats["search_query"] = f"{artist} {title}"
    
    if stats["found"]:
        print(f"[Popsike] Found {stats['result_count']} sold listings | "
              f"Avg: ${stats['avg_price']:.2f} | Last: ${stats['last_price']:.2f}")
    
    return stats


# ─────────────────────────────────────────────────────────────────
# INTEGRATION WITH POPSIKE_BRAIN.PY
# ─────────────────────────────────────────────────────────────────

"""
HOW TO USE THIS IN popsike_brain.py:

1. At the top of popsike_brain.py, replace the import:

   OLD:
   def fake_popsike_lookup(record: Dict[str, Any]) -> Dict[str, Any]:
       # stub code...

   NEW:
   from popsike_scraper import real_popsike_lookup

2. In enrich_candidates_with_lookup(), replace the function call:

   OLD:
   popsike_result = fake_popsike_lookup(candidate)

   NEW:
   popsike_result = real_popsike_lookup(candidate)
   time.sleep(random.uniform(1.0, 2.0))  # Rate limit between requests

That's it. The rest of the pipeline stays the same.

RATE LIMITING:
- Popsike has no strict rate limit, but be respectful
- Add 1-2 second delays between searches
- Don't hammer with 100s of requests rapidly
- Current setup does ~1-2 per second max

FALLBACK:
- If Popsike search fails, returns found=False
- Pipeline treats it as "no match" and moves on
- Discogs data stays as primary signal
"""


# ─────────────────────────────────────────────────────────────────
# TEST
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_records = [
        {
            "artist": "Sleep Token",
            "title": "Caramel",
            "price": 49.99,
        },
        {
            "artist": "Erra",
            "title": "Augment",
            "price": 24.99,
        },
    ]
    
    for record in test_records:
        print(f"\n{'=' * 60}")
        print(f"Testing: {record['artist']} - {record['title']}")
        print(f"{'=' * 60}")
        
        result = real_popsike_lookup(record)
        print(f"\nResult:")
        print(json.dumps(result, indent=2))
        
        # Rate limit between requests
        time.sleep(2.0)
