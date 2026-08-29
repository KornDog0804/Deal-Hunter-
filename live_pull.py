# -*- coding: utf-8 -*-
import json
import re
import html
import time
import random
import os
import urllib.request
import urllib.parse
from urllib.parse import urljoin
from pathlib import Path
try:
    from buyer_brain import apply_buyer_brain
except Exception as e:
    print(f"buyer_brain import failed: {e}")
    def apply_buyer_brain(data):
        return data
try:
    from popsike_brain import (
        load_popsike_cache,
        save_popsike_cache,
        evaluate_records_for_popsike,
        enrich_candidates_with_lookup,
    )
except Exception as e:
    print(f"popsike_brain import failed: {e}")

try:
    from discogs_lookup_integration import enrich_candidates_with_discogs_lookup
except Exception as e:
    print(f"discogs_lookup_integration import failed: {e}")
    def enrich_candidates_with_discogs_lookup(candidates, cache=None):
        return candidates

BASE = Path(__file__).resolve().parent

def load_sources_from_json(json_file="sources.json"):
    """Load sources from external JSON config file."""
    try:
        if os.path.exists(json_file):
            with open(json_file, 'r') as f:
                data = json.load(f)
                return data.get("sources", [])
        else:
            log(f"WARNING: {json_file} not found, using fallback")
            return []
    except Exception as e:
        log(f"ERROR loading sources.json: {e}")
        return []

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Linux; Android 16; Pixel 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
]
_ua_index = 0

AMAZON_TAG = "korndog20-20"

WALMART_BROWSE_URLS = [
    "https://www.walmart.com/browse/music/vinyl-records/4104_1205481",
    "https://www.walmart.com/browse/music/vinyl-records/4104_1205481?page=2",
    "https://www.walmart.com/browse/music/vinyl-records/4104_1205481?page=3",
    "https://www.walmart.com/browse/music/vinyl-records/4104_1205481?page=4",
    "https://www.walmart.com/browse/music/vinyl-records/4104_1205481?page=5",
    "https://www.walmart.com/browse/rock-music-cd-vinyl/4104_4118",
    "https://www.walmart.com/browse/rock-music-cd-vinyl/4104_4118?page=2",
    "https://www.walmart.com/browse/rock-music-cd-vinyl/4104_4118?page=3",
    "https://www.walmart.com/browse/rock-music-cd-vinyl/4104_4118?page=4",
]

# ─────────────────────────────────────────────────────────────────
# AMAZON + TARGET CATALOG SCRAPERS
# ─────────────────────────────────────────────────────────────────

# ─── URLS ───────────────────────────────────────────────────────
AMAZON_BROWSE_URLS = [
    "https://www.amazon.com/Best-Sellers-Vinyl-Records/zgbs/music/71838931",
    "https://www.amazon.com/Best-Sellers-Vinyl-Records/zgbs/music/71838931?pg=2",
    "https://www.amazon.com/gp/new-releases/music/71838931",
    "https://www.amazon.com/gp/new-releases/music/71838931?pg=2",
    "https://www.amazon.com/gp/movers-and-shakers/music/71838931",
    "https://www.amazon.com/s?k=vinyl+records&i=popular&rh=n%3A71838931",
    "https://www.amazon.com/s?k=vinyl+lp+record&i=popular&rh=n%3A71838931&page=2",
]

TARGET_BROWSE_URLS = [
    "https://redsky.target.com/redsky_aggregations/v1/web/plp_search_v2?key=9f36aeafbe60771e321a7cc95a78140772ab3e96&channel=WEB&keyword=vinyl+records&count=24&offset=0&pricing_store_id=911&visitor_id=deal_hunter",
    "https://redsky.target.com/redsky_aggregations/v1/web/plp_search_v2?key=9f36aeafbe60771e321a7cc95a78140772ab3e96&channel=WEB&keyword=vinyl+records&count=24&offset=24&pricing_store_id=911&visitor_id=deal_hunter",
    "https://www.target.com/s?searchTerm=vinyl+records&Nao=0",
    "https://www.target.com/s?searchTerm=vinyl+records&Nao=24",
]

# ─── FETCH FUNCTIONS ────────────────────────────────────────────
def amazon_fetch(url, retries=3, delay=2):
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 16; Pixel 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Upgrade-Insecure-Requests": "1",
        "Referer": "https://www.amazon.com/",
        "DNT": "1",
        "Connection": "keep-alive",
    }
    return fetch(url, retries=retries, delay=delay, extra_headers=headers)


def target_fetch(url, retries=3, delay=2):
    is_api = "redsky.target.com" in url
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 16; Pixel 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json, text/html,*/*" if is_api else "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Referer": "https://www.target.com/",
        "Origin": "https://www.target.com",
        "DNT": "1",
        "Connection": "keep-alive",
    }
    return fetch(url, retries=retries, delay=delay, extra_headers=headers)

# ─── ROBOT WALL DETECTION ───────────────────────────────────────
def amazon_robot_wall(page_html):
    t = (page_html or "").lower()
    return any(m in t for m in [
        "to discuss automated access",
        "sorry, we just need to make sure",
        "enter the characters you see below",
        "api-services-support@amazon.com",
        "/captcha/", "robot check",
    ])


def target_robot_wall(page_html):
    t = (page_html or "").lower()
    return any(m in t for m in [
        "access to this page has been denied",
        "perimeterx", "px-captcha", "are you a human",
    ])

# ─── AMAZON EXTRACTION & BUILDER ────────────────────────────────
def extract_amazon_candidates(page_html):
    results = []
    
    # JSON-LD blocks
    for block in re.findall(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', page_html, re.S | re.I):
        try:
            data = json.loads(block)
            items = data if isinstance(data, list) else [data]
            for item in items:
                name = item.get("name", "")
                if name and looks_like_real_vinyl(name):
                    url = item.get("url", "")
                    asin_m = re.search(r'/dp/([A-Z0-9]{10})', url)
                    asin = asin_m.group(1) if asin_m else ""
                    price_obj = item.get("offers", {})
                    price = normalize_price(price_obj.get("price", 0)) if isinstance(price_obj, dict) else 0.0
                    results.append({
                        "title": clean(name), "asin": asin,
                        "link": f"https://www.amazon.com/dp/{asin}?tag={AMAZON_TAG}" if asin else url,
                        "price": price, "image": ""
                    })
        except Exception:
            pass
    
    # ASIN + title patterns
    for pat in [
        r'"asin"\s*:\s*"([A-Z0-9]{10})".*?"title"\s*:\s*"([^"]{4,250})"',
        r'data-asin="([A-Z0-9]{10})"[^>]*>.*?(?:aria-label|alt)="([^"]{4,250})"',
        r'/dp/([A-Z0-9]{10})[^"]*"[^>]*>.*?<span[^>]*>([^<]{4,250})</span>',
    ]:
        for groups in re.findall(pat, page_html, re.I | re.S):
            asin, title = groups[0], groups[1]
            title = clean(title)
            if title and looks_like_real_vinyl(title):
                results.append({
                    "title": title, "asin": asin,
                    "link": f"https://www.amazon.com/dp/{asin}?tag={AMAZON_TAG}",
                    "price": 0.0, "image": ""
                })
    
    # Span title fallback
    for title in re.findall(r'<span[^>]*class="[^"]*(?:a-text-normal|a-size-base-plus|a-size-medium|zg-text-center-align)[^"]*"[^>]*>([^<]{10,250})</span>', page_html, re.I):
        title = clean(title)
        if title and looks_like_real_vinyl(title):
            results.append({
                "title": title, "asin": "",
                "link": f"https://www.amazon.com/s?k={urllib.parse.quote_plus(title + ' vinyl')}&tag={AMAZON_TAG}",
                "price": 0.0, "image": ""
            })
    
    return results


def build_amazon_catalog(source):
    deals = []
    seen = set()
    robot_walls = 0
    pages_hit = 0
    
    for url in AMAZON_BROWSE_URLS:
        try:
            time.sleep(random.uniform(1.0, 2.5))
            page_html = amazon_fetch(url)
            pages_hit += 1
        except Exception as e:
            log(f'Amazon: failed {url} | {e}')
            continue
        
        if not page_html:
            continue
        
        if amazon_robot_wall(page_html):
            robot_walls += 1
            log(f'Amazon: robot wall (CAPTCHA) on {url}')
            continue
        
        candidates = extract_amazon_candidates(page_html)
        log(f'Amazon: found {len(candidates)} candidate vinyl items')
        
        for c in candidates:
            raw_title = c["title"]
            if should_skip(raw_title, c["link"]):
                continue
            
            key = raw_title.lower().strip()
            if key in seen:
                continue
            seen.add(key)
            
            artist, album = "Unknown Artist", raw_title
            if " - " in raw_title:
                parts = raw_title.split(" - ", 1)
                artist = parts[0].strip()
                album = re.sub(r'\[.*?\]', '', parts[1].strip()).strip()
            
            if not artist_allowed(artist, album):
                continue
            
            deals.append({
                "artist": artist,
                "title": album,
                "raw_title": raw_title,
                "price": normalize_price(c.get("price", 0)),
                "source": "Amazon",
                "source_type": source["source_type"],
                "link": c.get("link", ""),
                "image": c.get("image", ""),
                "keywords": keyword_hits(raw_title),
                "deal_quality": "catalog",
                "demand": "broad",
                "format": "vinyl",
                "version": "standard",
                "availability_text": "",
                "page_text_snippet": raw_title,
            })
    
    deduped = dedupe_source_items(deals)
    
    # If no deals found, provide catalog portal fallback
    if len(deduped) == 0:
        log("Amazon: No vinyl products found, adding catalog portal fallback")
        deduped = [{
            "artist": "Amazon Catalog",
            "title": "Amazon Vinyl Records",
            "raw_title": "Amazon Vinyl Records Catalog",
            "price": 0.01,
            "source": "Amazon",
            "source_type": source["source_type"],
            "link": f"https://www.amazon.com/s?k=vinyl+records&i=popular&rh=n%3A71838931&tag={AMAZON_TAG}",
            "image": "",
            "keywords": ["vinyl", "catalog"],
            "deal_quality": "catalog",
            "demand": "broad",
            "format": "vinyl",
            "version": "catalog",
            "availability_text": "Click link to browse Amazon catalog",
            "page_text_snippet": "Amazon vinyl catalog portal.",
        }]
    
    SOURCE_STATUS[source["name"]] = f"{len(deduped)} items | pages: {pages_hit} | robot walls: {robot_walls}"
    log(f'Amazon: kept {len(deduped)}')
    return deduped

# ─── TARGET EXTRACTION & BUILDER ────────────────────────────────
def extract_target_candidates_from_api(json_text):
    results = []
    try:
        data = json.loads(json_text)
        products = data.get("data", {}).get("search", {}).get("products", [])
        for product in products:
            try:
                item = product.get("item", product)
                tcin = str(item.get("tcin", "") or product.get("tcin", ""))
                title = item.get("product_description", {}).get("title", "") or product.get("title", "")
                title = clean(title)
                
                if not title or not looks_like_real_vinyl(title):
                    continue
                
                price_obj = product.get("price", {}) or item.get("price", {})
                price = 0.0
                if isinstance(price_obj, dict):
                    price_str = price_obj.get("formatted_current_price", "0").replace("$", "").replace(",", "")
                    price = normalize_price(price_str)
                    if price <= 0:
                        price = normalize_price(price_obj.get("current_retail", 0))
                
                link = f"https://www.target.com/p/-/A-{tcin}" if tcin else ""
                results.append({
                    "title": title,
                    "tcin": tcin,
                    "link": link,
                    "price": price,
                    "image": ""
                })
            except Exception:
                continue
    except Exception:
        pass
    return results


def extract_target_candidates_from_html(page_html):
    results = []
    
    # JSON blocks in HTML
    for blob in re.findall(r'<script[^>]+type="application/json"[^>]*>(.*?)</script>', page_html, re.S):
        try:
            for tcin, title in re.findall(r'"tcin"\s*:\s*"(\d{6,10})".*?"title"\s*:\s*"([^"]{4,250})"', blob, re.I | re.S):
                title = clean(title)
                if title and looks_like_real_vinyl(title):
                    results.append({
                        "title": title,
                        "tcin": tcin,
                        "link": f"https://www.target.com/p/-/A-{tcin}",
                        "price": 0.0,
                        "image": ""
                    })
        except Exception:
            pass
    
    # Link + title patterns
    for tcin, title in re.findall(r'<a[^>]+href="/p/[^"]*-/A-(\d+)"[^>]*>([^<]{4,250})</a>', page_html, re.I):
        title = clean(title)
        if title and looks_like_real_vinyl(title):
            results.append({
                "title": title,
                "tcin": tcin,
                "link": f"https://www.target.com/p/-/A-{tcin}",
                "price": 0.0,
                "image": ""
            })
    
    return results


def build_target_catalog(source):
    deals = []
    seen = set()
    robot_walls = 0
    pages_hit = 0
    api_success = False
    
    for url in TARGET_BROWSE_URLS:
        try:
            time.sleep(random.uniform(1.0, 2.0))
            page_text = target_fetch(url)
            pages_hit += 1
        except Exception as e:
            log(f'Target: failed {url} | {e}')
            continue
        
        if not page_text:
            continue
        
        if target_robot_wall(page_text):
            robot_walls += 1
            log(f'Target: robot wall on {url}')
            continue
        
        is_api = "redsky.target.com" in url
        if is_api:
            candidates = extract_target_candidates_from_api(page_text)
            if candidates:
                api_success = True
        else:
            candidates = extract_target_candidates_from_html(page_text)
        
        log(f'Target: found {len(candidates)} candidate vinyl items')
        
        for c in candidates:
            raw_title = c["title"]
            if should_skip(raw_title, c["link"]):
                continue
            
            key = raw_title.lower().strip()
            if key in seen:
                continue
            seen.add(key)
            
            artist, album = "Unknown Artist", raw_title
            if " - " in raw_title:
                parts = raw_title.split(" - ", 1)
                artist = parts[0].strip()
                album = parts[1].strip()
            
            if not artist_allowed(artist, album):
                continue
            
            deals.append({
                "artist": artist,
                "title": album,
                "raw_title": raw_title,
                "price": normalize_price(c.get("price", 0)),
                "source": "Target",
                "source_type": source["source_type"],
                "link": c.get("link", ""),
                "image": c.get("image", ""),
                "keywords": keyword_hits(raw_title),
                "deal_quality": "catalog",
                "demand": "broad",
                "format": "vinyl",
                "version": "standard",
                "availability_text": "",
                "page_text_snippet": raw_title,
            })
    
    deduped = dedupe_source_items(deals)
    
    # If no deals found, provide catalog portal fallback
    if len(deduped) == 0:
        log("Target: No vinyl products found, adding catalog portal fallback")
        deduped = [{
            "artist": "Target Catalog",
            "title": "Target Vinyl Records",
            "raw_title": "Target Vinyl Records Catalog",
            "price": 0.01,
            "source": "Target",
            "source_type": source["source_type"],
            "link": "https://www.target.com/s?searchTerm=vinyl+records",
            "image": "",
            "keywords": ["vinyl", "catalog"],
            "deal_quality": "catalog",
            "demand": "broad",
            "format": "vinyl",
            "version": "catalog",
            "availability_text": "Click link to browse Target catalog",
            "page_text_snippet": "Target vinyl catalog portal.",
        }]
    
    SOURCE_STATUS[source["name"]] = f"{len(deduped)} items | pages: {pages_hit} | robot walls: {robot_walls} | api: {'yes' if api_success else 'no'}"
    log(f'Target: kept {len(deduped)}')
    return deduped

# ─────────────────────────────────────────────────────────────────
# END AMAZON + TARGET SCRAPERS
# ─────────────────────────────────────────────────────────────────


HOT_TOPIC_SEARCH_URL = "https://www.hottopic.com/search?q=vinyl"
MERCHBAR_SEARCH_URL = "https://www.merchbar.com/vinyl-records"
DEEPDISCOUNT_SEARCH_URLS = [
    "https://www.deepdiscount.com/search?mod=AP&cr=vinyl",
    "https://www.deepdiscount.com/music/vinyl",
    "https://www.deepdiscount.com/music/vinyl/new-releases",
    "https://www.deepdiscount.com/featured-vinyl/b141496",
]

SOURCES = load_sources_from_json("sources.json")
if not SOURCES:
    log("CRITICAL: No sources loaded from sources.json!")

POSITIVE_KEYWORDS = [
    "colored", "exclusive", "limited", "anniversary", "deluxe",
    "zoetrope", "picture disc", "splatter", "variant", "2lp", "1lp",
    "marble", "smush", "quad", "opaque", "clear", "smoke", "translucent"
]

BANNED_KEYWORDS = [
    "christmas", "xmas", "holiday", "jingle", "santa", "let it snow",
    "wonderful christmastime", "war is over", "dean martin",
    "jackson 5", "bobby helms", "snowed in"
]

BAD_PRODUCT_TERMS = [
    "shirt", "hoodie", "tank top", "tee", "poster", "slipmat", "cassette",
    "cd", "compact disc", "beanie", "hat", "jacket", "bundle", "book",
    "kindle", "blu-ray", "dvd", "toy", "figure", "funko",
    "digital", "digital album", "digital download", "mp3", "download",
    "earbuds", "headphones", "airpods", "sticker", "patch", "pin",
    "pullover", "crewneck", "long sleeve", "t-shirt", "shorts", "socks",
    "turntable", "record player", "cleaner", "cleaning kit",
    "speaker", "stylus", "needle", "receiver", "drawstring bag", "wall flag", "flag", "tote", "bag"
]

DEBUG = []
SOURCE_STATUS = {}

# Optional legacy files. If absent, no problem.
ARTIST_CONFIG = {}
SLUG_PATTERNS = []
if (BASE / "artist_whitelist.json").exists():
    try:
        ARTIST_CONFIG = json.loads((BASE / "artist_whitelist.json").read_text(encoding="utf-8"))
    except Exception:
        ARTIST_CONFIG = {}
if (BASE / "slug_patterns.json").exists():
    try:
        SLUG_PATTERNS = json.loads((BASE / "slug_patterns.json").read_text(encoding="utf-8"))
    except Exception:
        SLUG_PATTERNS = []


def log(msg):
    print(msg)
    DEBUG.append(msg)


def next_ua():
    global _ua_index
    ua = USER_AGENTS[_ua_index % len(USER_AGENTS)]
    _ua_index += 1
    return ua


def fetch(url, retries=2, delay=2, extra_headers=None):
    extra_headers = extra_headers or {}
    for attempt in range(retries + 1):
        try:
            headers = {
                "User-Agent": next_ua(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "identity",
                "Connection": "keep-alive",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            }
            headers.update(extra_headers)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", "ignore")
        except Exception as e:
            if attempt < retries:
                log(f"  -> retry {attempt + 1}/{retries} for {url} | {e}")
                time.sleep(delay)
            else:
                raise


def walmart_fetch(url, retries=3, delay=2):
    mobile_headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 16; Pixel 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Upgrade-Insecure-Requests": "1",
        "Referer": "https://www.walmart.com/",
    }
    return fetch(url, retries=retries, delay=delay, extra_headers=mobile_headers)


def clean(text):
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("–", "-").replace("|", "-")
    text = text.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", text).strip()


def normalize_price(value):
    try:
        value = float(value)
    except Exception:
        return 0.0
    if value <= 0:
        return 0.0
    if value >= 1000:
        value = value / 100.0
    return round(value, 2)


def is_banned(text):
    t = (text or "").lower()
    return any(b in t for b in BANNED_KEYWORDS)


def contains_bad_product_terms(text):
    """
    Match whole product terms instead of arbitrary substrings.
    """
    t = clean(text or "").lower()

    for term in BAD_PRODUCT_TERMS:
        term = clean(term).lower()

        if not term:
            continue

        pattern = (
            r"(?<![a-z0-9])"
            + re.escape(term).replace(r"\ ", r"\s+")
            + r"(?![a-z0-9])"
        )

        if re.search(pattern, t, re.I):
            return True

    return False



def is_sold_out(text):
    t = (text or "").lower()
    return any(term in t for term in [
        "sold out",
        "sorry sold out",
        "out of stock",
        "currently unavailable",
        "unavailable",
        "not available",
    ])


def artist_allowed(artist, title=""):
    # Lane change: no taste filtering anymore.
    hay = f"{artist} {title}".lower()
    blocked = [str(b).lower().strip() for b in ARTIST_CONFIG.get("blocked_artists", [])]
    if any(b in hay for b in blocked if b):
        return False
    return True



def keyword_hits(text):
    t = (text or "").lower()
    return [k for k in POSITIVE_KEYWORDS if k in t]


def looks_like_garbage(text):
    t = (text or "").strip().lower()
    if len(t) < 3:
        return True
    if t in {"unknown title", "product"}:
        return True
    return False


def should_skip(title, link):
    blob = f"{title} {link}".lower()
    if is_banned(blob):
        return True
    if contains_bad_product_terms(blob):
        return True
    return False


def looks_like_real_vinyl(text):
    t = (text or "").lower()
    if any(bad in t for bad in [
        "compact disc", "cassette", "turntable", "record player", "cleaner",
        "cleaning kit", "slipmat", "speaker", "book", "kindle", "audiobook",
        "poster", "shirt", "toy", "funko", "earbuds", "headphones",
        "vinyl gloves", "vinyl flooring"
    ]):
        return False
    return any(good in t for good in [
        "vinyl", " 1lp", " 2lp", " lp", "record"
    ])


def looks_like_amazon_link(link):
    """
    Reject accidental Amazon links found while scraping another retailer.
    """
    try:
        host = urllib.parse.urlparse(link or "").netloc.lower()
    except Exception:
        return False

    return (
        host == "amazon.com"
        or host.endswith(".amazon.com")
        or host == "amzn.to"
        or host.endswith(".amzn.to")
    )



def clean_store_title(title):
    text = clean(title)
    junk_patterns = [
        r"\s*-\s*Music\s*&\s*Performance\s*-\s*Vinyl\s*$",
        r"\s*-\s*Vinyl\s*(?:Record|LP|Album)?\s*$",
        r"\s*-\s*Walmart\.com\s*$",
        r"\s*-\s*Shopify\s*$",
        r"\s*-\s*Newbury Comics\s*$",
        r"\s*-\s*Brooklyn Vegan\s*$",
        r"\s*-\s*Revolver\s*$",
        r"\s*-\s*Rise Records\s*$",
        r"\s*-\s*Fearless Records\s*$",
        r"\s*-\s*Sound of Vinyl\s*$",
        r"\s*-\s*uDiscover Music\s*$",
        r"\s*-\s*DeepDiscount\.com\s*$",
        r"\s*-\s*Merchbar\s*$",
        r"\s*-\s*Target\s*$",
        r"\s*-\s*Hot Topic\s*$",
        r"\s*-\s*Rhino\s*$",
        r"\s*-\s*Interscope Records\s*$",
        r"\s*-\s*Sumerian Records\s*$",
        r"\s*-\s*Solid State Records\s*$",
        r"\s*-\s*UNFD\s*$",
        r"\s*-\s*SharpTone Records\s*$",
        r"\s*-\s*Pure Noise Records?\s*$",
        r"\s*-\s*Rollin Records\s*$",
        r"\s*-\s*MNRK Heavy\s*$",
        r"\s*-\s*Rock Metal Fan Nation\s*$",
        r"\s*-\s*Millions of Records\s*$",
        r"\s*-\s*IndieMerchstore\s*$",
        r"\s*-\s*Deep Discount\s*$",
        r"\s*-\s*Amazon\s*$",
        r"\s*-\s*Walmart\s*$",
    ]
    for pattern in junk_patterns:
        text = re.sub(pattern, "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" -")



def parse_from_slug(link):
    slug = link.rstrip("/").split("/")[-1]
    slug = clean(slug.replace("-", " ")).lower()
    slug = re.sub(
        r"\b(vinyl|lp|2lp|1lp|edition|limited|exclusive|colored|color|disc|picture|anniversary|collectors?|stereo|version|black|standard|record|records|performance|music|translucent|clear|smoke|splatter|etched|zoetrope)\b",
        "",
        slug,
        flags=re.I
    )
    return re.sub(r"\s+", " ", slug).strip()



def split_artist_album_from_title(title):
    title = clean_store_title(title)
    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "", title



STORE_VENDOR_NAMES = {
    "mnrk heavy",
    "interscope records",
    "sumerian records",
    "trust records",
    "fearless records",
    "rise records",
    "sharptone records",
    "pure noise records",
    "hopeless records",
    "craft recordings",
    "equal vision",
    "rhino",
    "solid state records",
    "rock metal fan nation",
    "brooklyn vegan",
    "revolver",
    "newbury comics",
    "sound of vinyl",
    "udiscover music",
    "rollin records",
    "pirates press records",
    "indiemerchstore",
    "thriller records",
    "unfd",
}


def load_known_artists():
    artists = set()

    # Main Korndog artist intelligence file.
    artists_file = BASE / "artists.json"

    if artists_file.exists():
        try:
            data = json.loads(artists_file.read_text(encoding="utf-8"))

            if isinstance(data, dict):
                for values in data.values():
                    if isinstance(values, list):
                        for artist in values:
                            artist = clean(artist)

                            if artist:
                                artists.add(artist)

            elif isinstance(data, list):
                for artist in data:
                    artist = clean(artist)

                    if artist:
                        artists.add(artist)

        except Exception as e:
            log(f"[Artists] Failed to load artists.json: {e}")

    # Legacy whitelist still contains many verified identities.
    whitelist_file = BASE / "artist_whitelist.json"

    if whitelist_file.exists():
        try:
            data = json.loads(
                whitelist_file.read_text(encoding="utf-8")
            )

            for artist in data.get("allowed_artists", []):
                artist = clean(artist)

                if artist:
                    artists.add(artist)

        except Exception as e:
            log(f"[Artists] Failed to load artist_whitelist.json: {e}")

    # Never allow store / label names to become artists.
    cleaned = set()

    for artist in artists:
        low = artist.lower().strip()

        if low in STORE_VENDOR_NAMES:
            continue

        if low in {
            "unknown artist",
            "amazon",
            "walmart",
            "target",
        }:
            continue

        if len(artist) < 2:
            continue

        cleaned.add(artist)

    log(f"[Artists] Loaded {len(cleaned)} trusted artists")

    return cleaned



KNOWN_ARTISTS = load_known_artists()

# Verified artists needed by stores such as Hot Topic that expose
# artist + album as one fused product title.
KNOWN_ARTISTS.update({
    "My Chemical Romance",
    "Motionless In White",
    "Evanescence",
    "The Warning",
    "Widespread Panic",
    "KATSEYE",
    "Adéla",
})

# Final verified identity corrections.
KNOWN_ARTISTS.discard("Murder by Death")
KNOWN_ARTISTS.add("Dave Grusin")
KNOWN_ARTISTS.add("The Devil Wears Prada")


def match_known_artist_prefix(title):
    value = clean(title)
    low = value.lower()

    for artist in sorted(KNOWN_ARTISTS, key=len, reverse=True):
        artist_low = artist.lower()

        if low == artist_low:
            return artist

        if low.startswith(artist_low + " "):
            return artist

        if low.startswith(artist_low + ":"):
            return artist

        if low.startswith(artist_low + " -"):
            return artist

    return ""


def match_known_artist_in_description(text):
    """
    Recover an artist from product-local description text only when
    the wording strongly identifies that artist.
    """
    value = clean(re.sub(r"<[^>]+>", " ", text or ""))
    low = value.lower()

    if not low:
        return ""

    for artist in sorted(KNOWN_ARTISTS, key=len, reverse=True):
        artist = clean(artist)

        if len(artist) < 3:
            continue

        a = artist.lower()
        escaped = re.escape(a)

        strong_patterns = [
            r"^" + escaped + r"(?:['’]s|\b)",
            r"\b" + escaped + r"['’]s\s+(?:album|record|release|debut|sophomore)",
            r"\b(?:band|artist)\s+" + escaped + r"\b",
            r"\bfrom\s+(?:the\s+band\s+)?" + escaped + r"\b",
            r"\brecord\s+from\s+" + escaped + r"\b",
            r"\balbum\s+by\s+" + escaped + r"\b",
        ]

        if any(re.search(pattern, low, re.I) for pattern in strong_patterns):
            return artist

    return ""


def strip_vinyl_suffix(title):
    text = clean(title)

    patterns = [
        r"\s+Hot Topic Exclusive\s*$",
        r"\s+(?:Triple|Double|Single)\s+Vinyl\s+LP\s*$",
        r"\s+Vinyl\s+EP\s*$",
        r"\s+Vinyl\s+LP\s*$",
        r"\s+Vinyl\s*$",
        r"\s+2LP\s*$",
        r"\s+LP\s*$",
    ]

    changed = True

    while changed:
        changed = False

        for pattern in patterns:
            newer = re.sub(pattern, "", text, flags=re.I).strip()

            if newer != text:
                text = newer
                changed = True

    return text


def clean_album_identity(title):
    text = strip_vinyl_suffix(title)
    text = clean(text)

    # Example after artist-prefix recovery:
    # 'SPIT' LP (Leopard Print Vinyl)
    quoted = re.match(
        r"""^['’‘"](.+?)['’‘"]\s+(?:LP|2LP)(?:\s+.*)?$""",
        text,
        re.I,
    )

    if quoted:
        return clean(quoted.group(1))

    # Remove simple wrapping quotes.
    text = re.sub(
        r"""^['’‘"](.+?)['’‘"]$""",
        r"\1",
        text,
    )

    return clean(text).strip(" '\"’‘")


def vendor_is_artist_candidate(vendor, source_name=""):
    vendor = clean(vendor)
    low = vendor.lower()

    if not vendor:
        return False

    if low in STORE_VENDOR_NAMES:
        return False

    if low == clean(source_name).lower():
        return False

    if low in {
        "vinyl",
        "music",
        "records",
        "record label",
        "merchandise",
        "merch",
    }:
        return False

    return True

def infer_artist_title(raw_title, link, vendor="", source_name=""):
    title = clean_store_title(raw_title)

    # Retailers sometimes prepend merchandising text before the artist.
    # Example: ** PRE-ORDER 10/23 ** Amy Winehouse
    title = re.sub(
        r"^\s*\*{0,3}\s*PRE[- ]?ORDER"
        r"(?:\s+\d{1,2}/\d{1,2})?"
        r"\s*\*{0,3}\s*",
        "",
        title,
        flags=re.I,
    ).strip()
    slug = parse_from_slug(link)
    vendor = clean(vendor)
    source_lower = clean(source_name).lower()

    for pattern_row in SLUG_PATTERNS:
        try:
            pattern, artist, album = pattern_row

            if re.search(pattern, slug, re.I):
                return artist, album

        except Exception:
            pass

    # Label-store style:
    # KITTIE 'SPIT' LP
    # DOGMA 'DOGMA' LP
    quoted = re.match(
        r"^\\s*(.+?)\\s+['\\\"]([^'\\\"]+)['\\\"](?:\\s+.*)?$",
        title,
        re.I,
    )

    if quoted:
        artist = clean(quoted.group(1))
        album = clean(quoted.group(2))

        if artist and album:
            return artist, album

    split_artist, split_album = split_artist_album_from_title(title)

    if split_artist and split_album:
        return split_artist, split_album

    # Try longest known artist prefix.
    known_artist = match_known_artist_prefix(title)

    if known_artist:
        album = title[len(known_artist):].strip(" :-")
        album = clean_album_identity(album)

        if album:
            return known_artist, album

    # Only trust vendor when it is not the store / record label.
    if vendor_is_artist_candidate(vendor, source_name):
        return vendor, title

    return "Unknown Artist", title



def detect_format(title="", product_type="", page_text=""):
    title_l = (title or "").lower()
    product_type_l = (product_type or "").lower()
    page_text_l = (page_text or "").lower()

    hard_bad_blob = f"{title_l} {product_type_l}"
    if contains_bad_product_terms(hard_bad_blob):
        return "other"

    if any(x in hard_bad_blob for x in ["cassette", "cd", "compact disc"]):
        if "vinyl" not in hard_bad_blob and " lp" not in hard_bad_blob and "record" not in hard_bad_blob:
            return "other"

    blob = f"{title_l} {product_type_l} {page_text_l[:1500]}"
    vinyl_markers = [
        " vinyl", "vinyl ", " vinyl ",
        " lp", "lp ", "2lp", "1lp",
        '12"', '7"', "record", "records"
    ]

    if any(x in blob for x in vinyl_markers):
        return "vinyl"
    if "cassette" in blob:
        return "cassette"
    if "cd" in blob or "compact disc" in blob:
        return "cd"
    return "other"



def extract_links(html_text, base, source_type="shopify_store"):
    raw_links = re.findall(r'href="([^"]+)"', html_text, re.IGNORECASE)
    links = []
    blocked_markers = [
        "/collections/", "/search", "/cart", "/account",
        "/pages/", "/policies/", "/blogs/", "#",
        "javascript:", "mailto:", "tel:"
    ]

    if source_type in {"shopify_store", "merchnow_store", "unfd_store"}:
        valid_markers = ["/products/", "/product/"]
    elif source_type in {"catalog_store", "merchbar_store", "hottopic_store", "millions_store"}:
        valid_markers = [
            "/product/", "/products/", "/p/", "/item/",
            "/ip/", "/dp/", "/vinyl", "/album", "/record", "/albums/"
        ]
    else:
        valid_markers = ["/products/", "/product/", "/p/", "/item/", "/ip/", "/albums/"]

    for href in raw_links:
        href = href.strip()
        if not href:
            continue
        full = urljoin(base, href)
        if any(b in full for b in blocked_markers):
            continue
        if any(v in full.lower() for v in valid_markers):
            if full not in links:
                links.append(full)

    return links[:800]


def extract_title(html_text):
    patterns = [
        r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="twitter:title"[^>]+content="([^"]+)"',
        r'<meta[^>]+property="product:title"[^>]+content="([^"]+)"',
        r'<h1[^>]*>(.*?)</h1>',
        r'"product_title"\s*:\s*"([^"]+)"',
        r'"name"\s*:\s*"([^"]+)"',
        r'"title"\s*:\s*"([^"]+)"',
        r"<title>(.*?)</title>"
    ]
    for p in patterns:
        m = re.search(p, html_text, re.I | re.S)
        if m:
            title = clean(m.group(1))
            if title and len(title) > 2:
                return clean_store_title(title)
    return "Unknown Title"


def extract_price(html_text):
    patterns = [
        r'property="product:price:amount"[^>]+content="(\d+\.\d{2})"',
        r'content="(\d+\.\d{2})"[^>]+property="product:price:amount"',
        r'"price"\s*:\s*"?(\\?\d+\.\d{2})"?',
        r'"amount"\s*:\s*"?(\\?\d+\.\d{2})"?',
        r'"currentPrice"\s*:\s*\{"price"\s*:\s*(\d+\.\d{2}|\d+)',
        r'"salePrice"\s*:\s*"?(\\?\d+\.\d{2})"?',
        r'"offerPrice"\s*:\s*"?(\\?\d+\.\d{2})"?',
        r'"price"\s*:\s*(\d+\.\d{2}|\d+)',
        r'\$(\d+\.\d{2})',
        r'\$(\d+)'
    ]
    for p in patterns:
        m = re.search(p, html_text, re.I)
        if m:
            raw = m.group(1).replace("\\", "")
            return normalize_price(raw)
    return 0.0


def extract_image(html_text, base):
    patterns = [
        r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="twitter:image"[^>]+content="([^"]+)"',
        r'"featured_image"\s*:\s*"([^"]+)"',
        r'"image"\s*:\s*"([^"]+)"',
        r'<img[^>]+src="([^"]+)"'
    ]
    for p in patterns:
        matches = re.findall(p, html_text, re.I | re.S)
        for img in matches:
            img = clean(img)
            if img and any(x in img.lower() for x in [".jpg", ".jpeg", ".png", ".webp", ".gif", "cdn", "images"]):
                return urljoin(base, img)
    return ""


def build_version_parts(text_blob, title_lower="", link_lower=""):
    keywords = keyword_hits(text_blob)
    version_parts = keywords[:]
    for token in ["2lp", "1lp"]:
        if token in title_lower and token not in version_parts:
            version_parts.append(token)
        if token in link_lower and token not in version_parts:
            version_parts.append(token)
    return keywords, version_parts



def fetch_shopify_products(source_url):
    url = source_url.rstrip("/")
    base_match = re.match(r'(https?://[^/]+)', url)
    if not base_match:
        return [], ""

    base = base_match.group(1)
    endpoints = []

    if "/collections/" in url:
        endpoints.append(url + "/products.json?limit=250")

    endpoints += [
        base + "/products.json?limit=250",
        base + "/collections/all/products.json?limit=250",
        base + "/collections/vinyl/products.json?limit=250",
        base + "/collections/music/products.json?limit=250",
        base + "/collections/records/products.json?limit=250",
    ]

    seen = set()
    deduped = []
    for endpoint in endpoints:
        if endpoint not in seen:
            seen.add(endpoint)
            deduped.append(endpoint)

    for endpoint in deduped:
        try:
            data = fetch(endpoint)
            parsed = json.loads(data)
            products = parsed.get("products", [])
            if products:
                log(f"  ✓ {endpoint} -> {len(products)} products")
                return products, endpoint
        except Exception as e:
            log(f"  ✗ {endpoint} -> {e}")

    return [], ""


def build_shopify_deals(source):
    deals = []
    products, endpoint_used = fetch_shopify_products(source["url"])
    log(f'{source["name"]}: {len(products)} products via Shopify JSON')

    if not products:
        SOURCE_STATUS[source["name"]] = "0 products - endpoint may have changed"
        return []

    kept = 0

    for p in products:
        try:
            title = clean(p.get("title", ""))
            if not title:
                continue

            vendor = clean(p.get("vendor", ""))
            product_type = clean(p.get("product_type", "")).lower()
            title_lower = title.lower()
            tags = p.get("tags", "")
            tags_text = ", ".join(tags) if isinstance(tags, list) else str(tags or "")

            if should_skip(title, ""):
                continue
            if contains_bad_product_terms(f"{title} {product_type} {tags_text}"):
                continue

            variants = p.get("variants", []) or []
            if not variants:
                continue

            valid_variant = None
            for v in variants:
                price = normalize_price(v.get("price", 0))
                vtitle = clean(v.get("title", "")).lower()
                if not contains_bad_product_terms(vtitle):
                    valid_variant = v
                    break

            if not valid_variant:
                continue

            price = normalize_price(valid_variant.get("price", 0))

            handle = p.get("handle", "")
            if not handle:
                continue

            base_match = re.match(r'(https?://[^/]+)', source["url"])
            base_url = base_match.group(1) if base_match else source["url"]
            link = base_url + "/products/" + handle

            artist, album = infer_artist_title(title, link, vendor=vendor, source_name=source["name"])

            if looks_like_garbage(album):
                continue
            if contains_bad_product_terms(f"{artist} {album}"):
                continue
            if not artist_allowed(artist, album):
                continue

            imgs = p.get("images", []) or []
            image = imgs[0].get("src", "") if imgs else ""

            body_html = p.get("body_html", "") or ""
            variant_title = clean(valid_variant.get("title", "") or "")

            # Some label stores use the label itself as Shopify vendor.
            # Recover the real artist from strong product-description wording.
            if (
                artist == "Unknown Artist"
                or clean(artist).lower() in STORE_VENDOR_NAMES
            ):
                description_artist = match_known_artist_in_description(body_html)

                if description_artist:
                    artist = description_artist

                    prefix_artist = match_known_artist_prefix(title)

                    if prefix_artist:
                        album = clean_album_identity(
                            title[len(prefix_artist):].strip(" :-")
                        )
                    else:
                        album = clean_album_identity(title)

            if is_sold_out(f"{title} {body_html} {variant_title}"):
                continue

            fmt = detect_format(title=title, product_type=product_type, page_text=f"{body_html} {tags_text}")
            if fmt != "vinyl":
                continue

            keywords, version_parts = build_version_parts(
                f"{title} {link} {variant_title}",
                title_lower=title_lower,
                link_lower=link.lower()
            )

            deals.append({
                "artist": artist,
                "title": album,
                "raw_title": title,
                "price": price,
                "source": source["name"],
                "source_type": source["source_type"],
                "link": link,
                "image": image,
                "keywords": keywords,
                "deal_quality": "catalog",
                "demand": "broad",
                "format": fmt,
                "version": " ".join(version_parts) if version_parts else "standard",
                "availability_text": variant_title,
                "page_text_snippet": clean(body_html)[:1000],
                "endpoint_used": endpoint_used,
            })
            kept += 1

        except Exception as e:
            log(f'{source["name"]}: skipped Shopify product | {e}')

    SOURCE_STATUS[source["name"]] = f"{kept} deals"
    log(f'{source["name"]}: kept {kept}')
    return deals



def source_specific_links(page_html, source):
    source_type = source.get("source_type", "")

    if source_type == "merchbar_store":
        patterns = [
            r'href="(/albums/[^"]+)"',
            r'href="(/vinyl-records/[^"]+)"',
            r'href="(/product/[^"]+)"',
        ]
        links = []
        for pattern in patterns:
            for href in re.findall(pattern, page_html, re.I):
                full = urljoin("https://www.merchbar.com", href)
                if full not in links:
                    links.append(full)
        return links[:600]

    if source_type == "hottopic_store":
        patterns = [
            r'href="([^"]+/product/[^"]+)"',
            r'href="(/product/[^"]+)"',
        ]
        links = []
        for pattern in patterns:
            for href in re.findall(pattern, page_html, re.I):
                full = urljoin("https://www.hottopic.com", href)
                if "/product/" in full.lower() and full not in links:
                    links.append(full)
        return links[:400]

    if source_type == "millions_store":
        patterns = [
            r'href="(/products/[^"]+)"',
            r'href="([^"]+/products/[^"]+)"',
        ]
        links = []
        for pattern in patterns:
            for href in re.findall(pattern, page_html, re.I):
                full = urljoin("https://www.millionsofrecords.com", href)
                if full not in links:
                    links.append(full)
        return links[:500]

    if source_type == "unfd_store":
        patterns = [
            r'href="(/products/[^"]+)"',
            r'href="([^"]+/products/[^"]+)"',
        ]
        links = []
        for pattern in patterns:
            for href in re.findall(pattern, page_html, re.I):
                full = urljoin("https://usa.24hundred.net", href)
                if full not in links:
                    links.append(full)
        return links[:500]

    return extract_links(page_html, source.get("url", ""), source_type=source_type)


def build_html_deals(source):
    deals = []
    try:
        html_text = fetch(source["url"])
        links = source_specific_links(html_text, source)
        log(f'{source["name"]}: found {len(links)} HTML links')

        kept = 0
        source_name = (source.get("name") or "").lower()

        for link in links:
            try:
                page = fetch(link)

                if looks_like_amazon_link(link):
                    continue

                raw_title = extract_title(page)

                # Hot Topic pages contain availability language for store
                # pickup and other widgets. Only use strong structured
                # out-of-stock evidence there.
                if "hot topic" in source_name:
                    page_lower = page.lower()

                    hot_topic_out = (
                        'data-isoutofstock="true"' in page_lower
                        or '"availability":"https://schema.org/outofstock"' in page_lower
                        or '"availability": "https://schema.org/outofstock"' in page_lower
                        or "schema.org/outofstock" in page_lower
                    )

                    if hot_topic_out:
                        continue
                elif is_sold_out(page):
                    continue
                if should_skip(raw_title, link):
                    continue

                if "merchbar" in source_name and "vinyl records" in raw_title.lower():
                    continue
                if "hot topic" in source_name and "music & vinyl" in raw_title.lower():
                    continue

                price = extract_price(page)
                artist, album = infer_artist_title(raw_title, link, source_name=source["name"])

                if looks_like_garbage(album):
                    continue
                if contains_bad_product_terms(f"{artist} {album}"):
                    continue
                if not artist_allowed(artist, album):
                    continue

                fmt = detect_format(title=raw_title, product_type="", page_text=page[:3500])
                if fmt != "vinyl":
                    continue

                image = extract_image(page, link)

                keywords, version_parts = build_version_parts(
                    f"{raw_title} {link}",
                    title_lower=raw_title.lower(),
                    link_lower=link.lower()
                )

                deals.append({
                    "artist": artist,
                    "title": album,
                    "raw_title": raw_title,
                    "price": price,
                    "source": source["name"],
                    "source_type": source["source_type"],
                    "link": link,
                    "image": image,
                    "keywords": keywords,
                    "deal_quality": "catalog",
                    "demand": "broad",
                    "format": fmt,
                    "version": " ".join(version_parts) if version_parts else "standard",
                    "availability_text": "",
                    "page_text_snippet": clean(page)[:1000],
                })
                kept += 1

            except Exception as e:
                log(f'{source["name"]}: skipping product {link} | {e}')

        SOURCE_STATUS[source["name"]] = f"{kept} deals"
        log(f'{source["name"]}: kept {kept}')

    except Exception as e:
        SOURCE_STATUS[source["name"]] = f"FAILED: {e}"
        log(f'{source["name"]}: HTML source failed | {e}')

    return deals



def build_unfd(source):
    deals = build_shopify_deals({
        "name": source["name"],
        "source_type": "shopify_store",
        "url": source["url"],
    })
    if deals:
        SOURCE_STATUS[source["name"]] = f"{len(deals)} deals"
        return deals

    log(f'{source["name"]}: Shopify path empty, trying HTML fallback')
    return build_html_deals(source)



def build_millions(source):
    deals = build_html_deals(source)
    SOURCE_STATUS[source["name"]] = f"{len(deals)} deals"
    return deals



def build_deepdiscount(source):
    deals = []
    seen_links = set()

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    opener.addheaders = [
        ("User-Agent", random.choice(USER_AGENTS)),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"),
        ("Accept-Language", "en-US,en;q=0.9"),
        ("Cache-Control", "no-cache"),
        ("Pragma", "no-cache"),
        ("Upgrade-Insecure-Requests", "1"),
        ("Referer", "https://www.deepdiscount.com/"),
        ("DNT", "1"),
        ("Connection", "keep-alive"),
    ]

    def dd_sleep():
        time.sleep(random.uniform(0.8, 1.8))

    def dd_fetch(url, retries=3):
        nonlocal opener
        for _ in range(retries):
            try:
                with opener.open(url, timeout=25) as resp:
                    html_text = resp.read().decode("utf-8", "ignore")
                    log(f"Deep Discount fetch: {url}")
                    return html_text
            except Exception as e:
                log(f"Deep Discount fetch error: {url} | {e}")
                dd_sleep()
        return ""

    def is_real_dd_product_url(url):
        low = url.lower().split("?", 1)[0].rstrip("/")
        if not low.startswith("https://www.deepdiscount.com/"):
            return False
        path = re.sub(r"^https?://[^/]+", "", low).strip("/")
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2:
            return False
        last = parts[-1]
        return bool(re.fullmatch(r"\d{8,14}", last))

    def extract_dd_links(page_html):
        links = set()
        hrefs = re.findall(r'href="([^"]+)"', page_html, re.I)
        for href in hrefs:
            full = urljoin("https://www.deepdiscount.com", href)
            low = full.lower()
            if any(bad in low for bad in [
                "javascript:", "mailto:", "tel:", "#", "/cart", "/account", "/help"
            ]):
                continue
            if is_real_dd_product_url(full):
                links.add(full)
        return list(links)[:1200]

    _ = dd_fetch("https://www.deepdiscount.com/")
    time.sleep(random.uniform(0.8, 1.8))
    _ = dd_fetch("https://www.deepdiscount.com/music/vinyl")
    time.sleep(random.uniform(0.8, 1.8))

    for page_url in DEEPDISCOUNT_SEARCH_URLS:
        page_html = dd_fetch(page_url)
        if not page_html:
            continue

        links = extract_dd_links(page_html)
        log(f'{source["name"]}: found {len(links)} product links from {page_url}')

        for link in links:
            if link in seen_links:
                continue
            seen_links.add(link)

            time.sleep(random.uniform(0.8, 1.8))
            product_html = dd_fetch(link)
            if not product_html:
                continue
            if is_sold_out(product_html):
                continue

            raw_title = extract_title(product_html)
            if not raw_title or should_skip(raw_title, link):
                continue

            price = extract_price(product_html)
            fmt = detect_format(title=raw_title, product_type="", page_text=product_html[:3500])
            if fmt != "vinyl":
                continue

            artist, album = infer_artist_title(raw_title, link, source_name=source["name"])
            if looks_like_garbage(album):
                continue
            if contains_bad_product_terms(f"{artist} {album}"):
                continue
            if not artist_allowed(artist, album):
                continue

            image = extract_image(product_html, link)
            keywords, version_parts = build_version_parts(
                f"{raw_title} {link}",
                title_lower=raw_title.lower(),
                link_lower=link.lower()
            )

            deals.append({
                "artist": artist,
                "title": album,
                "raw_title": raw_title,
                "price": price,
                "source": source["name"],
                "source_type": source["source_type"],
                "link": link,
                "image": image,
                "keywords": keywords,
                "deal_quality": "catalog",
                "demand": "broad",
                "format": fmt,
                "version": " ".join(version_parts) if version_parts else "standard",
                "availability_text": "",
                "page_text_snippet": clean(product_html)[:1000],
            })

    deduped = dedupe_source_items(deals)
    SOURCE_STATUS[source["name"]] = f"{len(deduped)} deals"
    log(f'{source["name"]}: kept {len(deduped)}')
    return deduped



def walmart_robot_wall(page_html):
    t = (page_html or "").lower()
    return any(marker in t for marker in [
        "robot or human",
        "/blocked?",
        "press & hold",
        "verify you are human",
        "perimeterx",
        "px-captcha"
    ])



def clean_walmart_title(text):
    text = clean(text)
    text = re.sub(r"\s+\$[\d\.,]+.*$", "", text).strip()
    return text



def extract_walmart_candidates_from_json_blob(blob_text):
    results = []

    # 1. name + canonical url + image + price style objects
    pattern_objects = re.findall(
        r'"name":"([^"]{4,250})".{0,800}?"canonicalUrl":"([^"]+)".{0,800}?(?:"price":(?:(?:\{"price":)?(\d+(?:\.\d+)?)))?',
        blob_text,
        re.I | re.S
    )
    for name, canonical, price in pattern_objects:
        title = clean_walmart_title(name)
        if not title or not looks_like_real_walmart_vinyl(title):
            continue
        results.append({
            "title": title,
            "link": urljoin("https://www.walmart.com", canonical),
            "price": normalize_price(price or 0),
            "image": ""
        })

    # 2. productName + usItemId + image + price
    pattern_objects_2 = re.findall(
        r'"productName":"([^"]{4,250})".{0,600}?"usItemId":"?(\d{5,20})"?',
        blob_text,
        re.I | re.S
    )
    for name, item_id in pattern_objects_2:
        title = clean_walmart_title(name)
        if not title or not looks_like_real_walmart_vinyl(title):
            continue
        results.append({
            "title": title,
            "link": f"https://www.walmart.com/ip/{item_id}",
            "price": 0.0,
            "image": ""
        })

    # 3. image alts and aria labels fallback
    fallback_patterns = [
        r'"imageAlt":"([^"]{4,250})"',
        r'aria-label="([^"]{4,250})"',
        r'<img[^>]+alt="([^"]{4,250})"',
        r'"title":"([^"]{4,250})"',
        r'"name":"([^"]{4,250})"',
    ]
    for pat in fallback_patterns:
        for match in re.findall(pat, blob_text, re.I):
            title = clean_walmart_title(match)
            if not title or not looks_like_real_walmart_vinyl(title):
                continue
            results.append({
                "title": title,
                "link": f"https://www.walmart.com/search?q={urllib.parse.quote_plus(title)}",
                "price": 0.0,
                "image": ""
            })

    return results



def build_walmart_catalog(source):
    deals = []
    seen = set()
    robot_walls = 0
    pages_hit = 0

    for url in WALMART_BROWSE_URLS:
        try:
            time.sleep(random.uniform(0.8, 1.6))
            page_html = walmart_fetch(url)
            pages_hit += 1
        except Exception as e:
            log(f'Walmart: failed {url} | {e}')
            continue

        if not page_html:
            continue

        if walmart_robot_wall(page_html):
            robot_walls += 1
            log(f'Walmart: robot wall on {url}')
            continue

        candidates = extract_walmart_candidates_from_json_blob(page_html)
        log(f'Walmart: found {len(candidates)} candidate vinyl items from {url}')

        for c in candidates:
            raw_title = c["title"]
            if should_skip(raw_title, c["link"]):
                continue

            key = raw_title.lower().strip()
            if key in seen:
                continue
            seen.add(key)

            deals.append({
                "artist": "Walmart Vinyl",
                "title": raw_title,
                "raw_title": raw_title,
                "price": normalize_price(c.get("price", 0)),
                "source": "Walmart",
                "source_type": source["source_type"],
                "link": c.get("link") or f"https://www.walmart.com/search?q={urllib.parse.quote_plus(raw_title)}",
                "image": c.get("image", ""),
                "keywords": keyword_hits(raw_title),
                "deal_quality": "catalog",
                "demand": "broad",
                "format": "vinyl",
                "version": "standard",
                "availability_text": "",
                "page_text_snippet": raw_title,
            })

    # Hard fallback if every page got blocked
    if not deals and robot_walls >= max(1, pages_hit // 2):
        log("Walmart: browse pages were blocked, adding hard catalog portal fallback")
        deals.append({
            "artist": "Walmart",
            "title": "Walmart Vinyl Records Catalog",
            "raw_title": "Walmart Vinyl Records Catalog",
            "price": 0.01,
            "source": "Walmart",
            "source_type": source["source_type"],
            "link": "https://www.walmart.com/browse/music/vinyl-records/4104_1205481",
            "image": "",
            "keywords": ["vinyl", "catalog"],
            "deal_quality": "catalog",
            "demand": "broad",
            "format": "vinyl",
            "version": "catalog",
            "availability_text": "",
            "page_text_snippet": "Fallback Walmart vinyl catalog portal because browse pages hit robot walls on runner.",
        })

    deduped = dedupe_source_items(deals)
    SOURCE_STATUS[source["name"]] = f"{len(deduped)} deals | pages: {pages_hit} | robot walls: {robot_walls}"
    log(f'Walmart: kept {len(deduped)}')
    return deduped



def derive_amazon_only(deals):
    amazon_link = (
        f"https://www.amazon.com/s?"
        f"k={urllib.parse.quote_plus('vinyl records')}"
        f"&tag={AMAZON_TAG}"
    )

    derived = [{
        "artist": "Amazon",
        "title": "Amazon Vinyl Records Catalog",
        "raw_title": "Amazon Vinyl Records Catalog",
        "price": 0.0,
        "source": "Amazon",
        "source_type": "affiliate_catalog_portal",
        "link": amazon_link,
        "image": "",
        "keywords": ["vinyl", "catalog"],
        "deal_quality": "catalog",
        "quality": "catalog",
        "demand": "broad",
        "format": "vinyl",
        "version": "catalog",
        "availability_text": "Browse Amazon vinyl records",
        "page_text_snippet": (
            "Amazon vinyl catalog portal using the "
            "Korndog Records Amazon Associates tag."
        ),
        "score": 0,
        "signals": ["catalog"],
    }]

    SOURCE_STATUS["Amazon"] = "1 catalog portal"

    log("Amazon: exposing 1 affiliate vinyl catalog portal")

    return derived




def dedupe_source_items(items):
    seen = {}
    for item in items:
        key = f'{(item.get("artist", "") or "").lower().strip()}::{(item.get("title", "") or "").lower().strip()}::{(item.get("source", "") or "").lower().strip()}'
        current = seen.get(key)
        if not current:
            seen[key] = item
            continue

        old_price = normalize_price(current.get("price", 0))
        new_price = normalize_price(item.get("price", 0))

        # Prefer real product page over search page
        current_link = str(current.get("link", ""))
        new_link = str(item.get("link", ""))
        current_is_search = "/search?" in current_link
        new_is_search = "/search?" in new_link

        if current_is_search and not new_is_search:
            seen[key] = item
            continue

        if new_price > 0 and (old_price <= 0 or new_price < old_price):
            seen[key] = item

    return list(seen.values())



def scrape_source(source):
    stype = source.get("source_type", "")
    name = source.get("name", "Unknown")

    if stype == "deepdiscount_store":
        return build_deepdiscount(source)

    if stype == "walmart_catalog_source":
        return build_walmart_catalog(source)

    if stype == "amazon_catalog_source":
        # Amazon is intentionally converted to a single portal
        # by derive_amazon_only().
        SOURCE_STATUS[name] = "1 catalog portal after main scrape"
        return []

    if stype == "target_catalog_source":
        return build_target_catalog(source)

    if stype == "unfd_store":
        return build_unfd(source)

    if stype == "millions_store":
        return build_millions(source)

    if stype in {
        "merchbar_store",
        "hottopic_store",
        "html_store",
        "catalog_store",
    }:
        return build_html_deals(source)

    if stype == "amazon_affiliate_source":
        SOURCE_STATUS[name] = "1 catalog portal after main scrape"
        return []

    if stype == "popsike_source":
        SOURCE_STATUS[name] = "enrichment-only source"
        return []

    if stype == "merchnow_store":
        deals = build_shopify_deals(source)

        if not deals:
            log(
                f"{name}: Merchnow JSON empty, "
                "trying HTML fallback"
            )

            deals = build_html_deals(source)

        return deals

    if stype == "shopify_store":
        deals = build_shopify_deals(source)

        if not deals:
            log(
                f"{name}: Shopify JSON empty, "
                "trying HTML fallback"
            )

            deals = build_html_deals(source)

        return deals

    log(f'{name}: unknown source_type "{stype}" - skipping')

    SOURCE_STATUS[name] = (
        f'SKIPPED (unknown type: {stype})'
    )

    return []



def normalize_identity_text(value):
    text = clean(value or "").lower()
    text = re.sub(r"\b(vinyl|records?|lp|2lp|1lp)\b", " ", text, flags=re.I)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()
def normalized_product_url(link):
    """
    Produce a stable product identity URL while dropping query strings
    and fragments. The same Shopify product appearing through two source
    lanes then collapses safely.
    """
    try:
        parsed = urllib.parse.urlparse(link or "")
        host = parsed.netloc.lower().replace("www.", "")
        path = parsed.path.rstrip("/").lower()
        return f"{host}{path}"
    except Exception:
        return (link or "").lower().strip()
def release_key_for(deal):
    artist = normalize_identity_text(deal.get("artist", ""))
    title = normalize_identity_text(deal.get("title", ""))

    if not artist:
        artist = "unknown"

    if not title:
        title = normalize_identity_text(deal.get("raw_title", ""))

    return f"{artist}::{title}"
def score_deal(deal):
    """
    KornDog Deal Hunter catalog score.

    This is deliberately conservative. A high score means the listing has
    meaningful buying signals, not merely that it exists.
    """
    score = 30
    signals = []

    blob = " ".join([
        str(deal.get("raw_title", "") or ""),
        str(deal.get("title", "") or ""),
        str(deal.get("version", "") or ""),
        " ".join(deal.get("keywords", []) or []),
        str(deal.get("availability_text", "") or ""),
    ]).lower()

    price = normalize_price(deal.get("price", 0))

    boosts = [
        ("exclusive", 20, "exclusive"),
        ("limited", 14, "limited"),
        ("pre-order", 15, "preorder"),
        ("preorder", 15, "preorder"),
        ("splatter", 8, "splatter"),
        ("marble", 7, "marble"),
        ("zoetrope", 12, "zoetrope"),
        ("picture disc", 7, "picture-disc"),
        ("anniversary", 8, "anniversary"),
        ("deluxe", 6, "deluxe"),
        ("colored vinyl", 5, "colored-vinyl"),
        ("colour vinyl", 5, "colored-vinyl"),
        ("translucent", 5, "colored-vinyl"),
        ("clear vinyl", 5, "colored-vinyl"),
    ]

    seen_signals = set()

    for needle, points, signal in boosts:
        if needle in blob and signal not in seen_signals:
            score += points
            signals.append(signal)
            seen_signals.add(signal)

    if "2lp" in blob or "double vinyl" in blob or "double lp" in blob:
        score += 4
        signals.append("2lp")

    # Useful retail-price bands. Do not pretend price alone proves a deal.
    if 0 < price <= 20:
        score += 12
        signals.append("under-$20")
    elif price <= 25 and price > 0:
        score += 8
        signals.append("under-$25")
    elif price <= 30 and price > 0:
        score += 4
        signals.append("under-$30")

    if deal.get("version") == "catalog":
        score = 0
        signals = ["catalog-portal"]

    return min(score, 100), list(dict.fromkeys(signals))
def enrich_deals(deals):
    enriched = []

    for deal in deals:
        row = dict(deal)
        row["release_key"] = release_key_for(row)

        score, signals = score_deal(row)
        row["score"] = score
        row["signals"] = signals

        if score >= 90:
            row["deal_quality"] = "buy"
        elif score >= 75:
            row["deal_quality"] = "strong"
        elif score >= 55:
            row["deal_quality"] = "watch"
        elif row.get("version") != "catalog":
            row["deal_quality"] = "catalog"

        enriched.append(row)

    return enriched

def dedupe_deals(deals):
    """
    Collapse the exact same retailer product when it was discovered through
    multiple lanes such as a store root plus its vinyl collection.

    Different retailer links and genuinely different variants remain intact.
    """
    seen_urls = {}
    fallback_seen = {}

    for d in deals:
        link_key = normalized_product_url(d.get("link", ""))

        # Catalog portals remain independent.
        if d.get("version") == "catalog":
            portal_key = f"portal::{d.get('source', '').lower()}"
            if portal_key not in fallback_seen:
                fallback_seen[portal_key] = d
            continue

        if link_key and "/" in link_key:
            if link_key not in seen_urls:
                seen_urls[link_key] = d
            else:
                current = seen_urls[link_key]
                new_price = normalize_price(d.get("price", 0))
                old_price = normalize_price(current.get("price", 0))

                if new_price > 0 and (old_price <= 0 or new_price < old_price):
                    seen_urls[link_key] = d
            continue

        key = (
            f'{normalize_identity_text(d.get("artist", ""))}::'
            f'{normalize_identity_text(d.get("title", ""))}::'
            f'{(d.get("source", "") or "").lower().strip()}'
        )

        if key not in fallback_seen:
            fallback_seen[key] = d

    return list(seen_urls.values()) + list(fallback_seen.values())



def build():
    deals = []
    real_source_deals = []

    for source in SOURCES:
        stype = source.get("source_type", "")

        if stype in {
            "amazon_affiliate_source",
            "amazon_catalog_source",
            "popsike_source",
        }:
            continue

        log(f"\n{'=' * 50}")
        log(
            f"Scraping: {source['name']} "
            f"({source['source_type']})"
        )
        log(f"{'=' * 50}")

        pulled = scrape_source(source)

        deals.extend(pulled)
        real_source_deals.extend(pulled)

    # Exactly one Amazon portal.
    deals.extend(
        derive_amazon_only(real_source_deals)
    )

    # Exact product dedupe.
    deals = dedupe_deals(deals)

    # Stage 2 intelligence:
    # release key, signals, score and quality.
    deals = enrich_deals(deals)

    # --------------------------------------------------------
    # FINAL PRODUCT / IDENTITY SANITIZER
    # --------------------------------------------------------
    cleaned_deals = []

    for deal in deals:
        raw = clean(
            deal.get("raw_title")
            or deal.get("title")
            or ""
        )

        source = clean(
            deal.get("source", "")
        )

        blob = raw.lower()

        # Hard merchandise firewall.
        non_record_terms = {
            "slip mat",
            "slipmat",
            "turntable mat",
            "record cleaning mat",
        }

        if any(
            term in blob
            for term in non_record_terms
        ):
            log(
                f"[FinalFilter] merchandise rejected: "
                f"{source} | {raw}"
            )
            continue

        # Repair The Devil Wears Prada listings where stores
        # expose the artist and album as one giant product title.
        if (
            "the devil wears prada" in blob
            and "dear love" in blob
        ):
            deal["artist"] = "The Devil Wears Prada"
            deal["title"] = "Dear Love: A Beautiful Discord"

        # Craft's Murder by Death release is Dave Grusin's
        # soundtrack, not the band Murder by Death.
        if (
            source.lower() == "craft recordings"
            and "murder by death" in blob
        ):
            deal["artist"] = "Dave Grusin"
            deal["title"] = "Murder by Death"

        cleaned_deals.append(deal)

    # Refresh release keys and Stage 2 scoring after repairs.
    deals = enrich_deals(cleaned_deals)

    log(
        f"[Stage2] {len(deals)} normalized "
        "vinyl listings"
    )

    return deals




# ── UPCOMING VINYL SCRAPER ─────────────────────────────────────────────────────

def fetch_upcoming_vinyl():
    import html as _html
    import re as _re
    import urllib.parse as _urlparse

    page_url = "https://upcomingvinyl.com/this-week"

    try:
        html_text = fetch(
            page_url,
            retries=2,
            delay=3,
        )
    except Exception as e:
        log(
            f"[UpcomingVinyl] Fetch failed: {e}"
        )
        return []

    if not html_text:
        log("[UpcomingVinyl] Empty response")
        return []

    log(
        f"[UpcomingVinyl] Got "
        f"{len(html_text)} bytes"
    )

    def artist_slug(value):
        value = str(value or "").lower()

        value = _re.sub(
            r"[^a-z0-9]+",
            "-",
            value,
        )

        return value.strip("-")

    artist_map = []

    ambiguous_single_word_artists = {
        "joe",
    }

    for artist in KNOWN_ARTISTS:
        slug = artist_slug(artist)

        if len(slug) < 2:
            continue

        # Avoid prefix collisions such as:
        # Joe -> Joe Holmes
        if slug in ambiguous_single_word_artists:
            continue

        artist_map.append(
            (slug, artist)
        )

    artist_map.sort(
        key=lambda x: len(x[0]),
        reverse=True,
    )

    # Match /record/... links regardless of whether they
    # are absolute or relative.
    hrefs = _re.findall(
        r'href\s*=\s*["\\\']([^"\\\']*/record/[^"\\\'?#]+)["\\\']',
        html_text,
        flags=_re.I,
    )

    # Some frameworks embed route strings in JSON/script data.
    hrefs.extend(
        _re.findall(
            r'["\\\'](/record/[A-Za-z0-9%._~+\-]+)["\\\']',
            html_text,
            flags=_re.I,
        )
    )

    log(
        f"[UpcomingVinyl] Found "
        f"{len(hrefs)} raw record URLs"
    )

    upcoming = []
    seen = set()

    for href in hrefs:
        href = _html.unescape(
            href.strip()
        )

        absolute = _urlparse.urljoin(
            page_url,
            href,
        )

        parsed = _urlparse.urlparse(
            absolute
        )

        if "/record/" not in parsed.path:
            continue

        slug = parsed.path.split(
            "/record/",
            1,
        )[-1].strip("/")

        slug = _urlparse.unquote(
            slug
        ).lower()

        if not slug:
            continue

        matched_artist = None
        matched_slug = None

        for a_slug, artist in artist_map:
            if (
                slug == a_slug
                or slug.startswith(
                    a_slug + "-"
                )
            ):
                matched_artist = artist
                matched_slug = a_slug
                break

        if not matched_artist:
            continue

        remainder = slug[
            len(matched_slug):
        ].strip("-")

        # UpcomingVinyl occasionally appends internal numeric IDs.
        remainder = _re.sub(
            r"-\d{7,}$",
            "",
            remainder,
        )

        title = remainder.replace(
            "-",
            " ",
        ).strip()

        if title:
            title = " ".join(
                word.upper()
                if word.lower()
                in {"lp", "ep", "rsd"}
                else word.capitalize()
                for word in title.split()
            )
        else:
            title = matched_artist

        key = (
            matched_artist.lower(),
            slug,
        )

        if key in seen:
            continue

        seen.add(key)

        upcoming.append({
            "artist": matched_artist,
            "title": title,
            "label": "",
            "source": "Upcoming Vinyl",
            "source_url": absolute,
            "link": absolute,
            "type": "upcoming_release",
        })

        log(
            f"[UpcomingVinyl] MATCH: "
            f"{matched_artist} | {title}"
        )

    upcoming.sort(
        key=lambda x: (
            x.get(
                "artist",
                "",
            ).lower(),
            x.get(
                "title",
                "",
            ).lower(),
        )
    )

    log(
        f"[UpcomingVinyl] Total Korndog "
        f"matches: {len(upcoming)}"
    )

    return upcoming



# ── r/VINYLRELEASES SCRAPER ───────────────────────────────────────────────────

def _fetch_reddit_raw(endpoints, max_attempts=3):
    """Try multiple Reddit endpoints with browser-like headers to bypass 403s. Returns raw text."""
    browser_headers_options = [
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, application/json, text/html, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity",
            "Referer": "https://www.google.com/",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        },
        {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity",
            "Connection": "keep-alive",
        },
    ]

    for endpoint in endpoints:
        for attempt in range(max_attempts):
            headers = browser_headers_options[attempt % len(browser_headers_options)]
            try:
                req = urllib.request.Request(endpoint, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read().decode("utf-8", "ignore")
                log(f"[r/VinylReleases] Success on {endpoint}")
                return raw, endpoint
            except urllib.error.HTTPError as e:
                log(f"[r/VinylReleases] HTTP {e.code} on {endpoint} (attempt {attempt + 1})")
                if e.code == 429:
                    time.sleep(5)
                else:
                    time.sleep(1.5)
            except Exception as e:
                log(f"[r/VinylReleases] Error on {endpoint}: {e}")
                time.sleep(1.5)

    return None, None


def _parse_reddit_rss(xml_text):
    """Parse Reddit RSS feed into a list of post dicts that mimic the JSON API structure."""
    posts = []

    entry_blocks = re.findall(r'<entry>(.*?)</entry>', xml_text, re.S)

    for entry in entry_blocks:
        try:
            title_m = re.search(r'<title[^>]*>(.*?)</title>', entry, re.S)
            title = html.unescape(title_m.group(1)).strip() if title_m else ""

            link_m = re.search(r'<link[^>]+href="([^"]+)"', entry)
            reddit_url = link_m.group(1) if link_m else ""

            pub_m = re.search(r'<published>(.*?)</published>', entry, re.S)
            published = pub_m.group(1).strip() if pub_m else ""

            content_m = re.search(r'<content[^>]*>(.*?)</content>', entry, re.S)
            content = html.unescape(content_m.group(1)) if content_m else ""

            flair = ""
            flair_m = re.match(r'^\[([^\]]+)\]\s*', title)
            if flair_m:
                flair = flair_m.group(1).strip()
                title = title[flair_m.end():].strip()

            store_url = ""
            link_matches = re.findall(r'href="(https?://[^"]+)"', content, re.I)
            for link in link_matches:
                low = link.lower()
                if "reddit.com" in low or "redd.it" in low or "redditstatic" in low:
                    continue
                store_url = link
                break

            posts.append({
                "title": title,
                "reddit_url": reddit_url,
                "store_url": store_url,
                "flair": flair,
                "published": published,
                "content_snippet": re.sub(r'<[^>]+>', ' ', content)[:500],
            })
        except Exception as e:
            log(f"[r/VinylReleases] Parse error on entry: {e}")
            continue

    return posts


def fetch_vinyl_releases():
    """
    Scrape r/VinylReleases/new via Reddit's public RSS feed.
    Returns a list of deal dicts ready to merge into live_deals.json.
    """
    endpoints = [
        "https://www.reddit.com/r/VinylReleases/new/.rss?limit=50",
        "https://old.reddit.com/r/VinylReleases/new/.rss?limit=50",
        "https://www.reddit.com/r/VinylReleases/.rss?limit=50",
    ]

    deals = []
    raw_xml, used_endpoint = _fetch_reddit_raw(endpoints)

    if not raw_xml:
        log(f"[r/VinylReleases] All endpoints failed — skipping")
        return deals

    log(f"\n{'=' * 50}")
    log(f"[r/VinylReleases] Fetched RSS from {used_endpoint}")
    log(f"{'=' * 50}")

    try:
        posts = _parse_reddit_rss(raw_xml)
        log(f"[r/VinylReleases] Parsed {len(posts)} posts from RSS")

        for p in posts:
            title = p.get("title", "")
            if not title:
                continue

            flair = p.get("flair", "")
            reddit_url = p.get("reddit_url", "")
            store_url = p.get("store_url", "")
            content_snippet = p.get("content_snippet", "")

            price_val = 0.0
            price_match = re.search(r'\$(\d+(?:\.\d{2})?)', title)
            if price_match:
                price_val = normalize_price(price_match.group(1))

            release_type = ""
            type_keywords = {
                "restock": "Restock",
                "pre-order": "Pre-Order",
                "preorder": "Pre-Order",
                "new release": "New Release",
                "deal": "Deal",
                "sale": "Sale",
                "price drop": "Price Drop",
                "rsd": "Record Store Day",
                "limited": "Limited",
                "expired": "Expired",
            }
            check_text = f"{flair} {title}".lower()
            for keyword, label in type_keywords.items():
                if keyword in check_text:
                    release_type = label
                    break

            if release_type == "Expired" or "[expired]" in title.lower():
                continue

            if is_banned(title):
                continue
            if contains_bad_product_terms(title):
                continue

            artist, album = "Unknown Artist", title
            if " - " in title:
                parts = title.split(" - ", 1)
                artist = parts[0].strip()
                album = parts[1].strip()
                album = re.sub(r'\[.*?\]', '', album).strip()
                album = re.sub(r'\(.*?edition.*?\)', '', album, flags=re.I).strip()

            deals.append({
                "artist": artist,
                "title": album,
                "raw_title": title,
                "price": price_val,
                "source": "r/VinylReleases",
                "source_type": "reddit_scraper",
                "link": store_url or reddit_url,
                "reddit_url": reddit_url,
                "image": "",
                "keywords": keyword_hits(title),
                "deal_quality": "community",
                "demand": "broad",
                "format": "vinyl",
                "version": "standard",
                "availability_text": flair,
                "page_text_snippet": content_snippet,
                "reddit_score": 0,
                "reddit_upvote_ratio": 0,
                "release_type": release_type,
                "timestamp": 0,
            })

        log(f"[r/VinylReleases] {len(deals)} deals after filtering")

    except Exception as e:
        log(f"[r/VinylReleases] Parse error: {e}")

    return deals


# ── NTFY PUSH NOTIFICATIONS ──────────────────────────────────────────────────

def send_deal_hunter_notification(total_deals, reddit_deals=None, upcoming_count=0, buy_signal_count=0):
    """
    Send a push notification summary via ntfy.sh.
    Install the ntfy app on your phone and subscribe to your topic.
    """
    NTFY_TOPIC = "korndog-deals"

    from datetime import datetime

    try:
        now = datetime.now().strftime("%I:%M %p")

        lines = [f"Deal Hunter ran at {now}"]
        lines.append(f"Total deals: {total_deals}")

        if reddit_deals:
            lines.append(f"Reddit drops: {len(reddit_deals)}")

        if upcoming_count > 0:
            lines.append(f"Upcoming releases: {upcoming_count}")
        if buy_signal_count > 0:
            lines.append(f"Buy signals: {buy_signal_count}")

        if reddit_deals:
            top_reddit = sorted(reddit_deals, key=lambda x: x.get("reddit_score", 0), reverse=True)[:3]
            if top_reddit:
                lines.append("")
                lines.append("Hot drops:")
                for r in top_reddit:
                    rt = r.get("raw_title", "")[:80]
                    price = f" (${r['price']:.2f})" if r.get("price", 0) > 0 else ""
                    lines.append(f"  {rt}{price}")

        message = "\n".join(lines)

        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Title": "Deal Hunter Update",
                "Priority": "default",
                "Tags": "cd,shopping_cart",
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.getcode()

        if status == 200:
            log(f"[ntfy] Notification sent successfully")
        else:
            log(f"[ntfy] WARNING: status {status}")

    except Exception as e:
        log(f"[ntfy] ERROR (non-fatal): {e}")


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    data = build()
    data = apply_buyer_brain(data)
    
    log("\n" + "=" * 50)
    log("ENRICHING WITH DISCOGS MINT PRICING")
    log("=" * 50)
    
    try:
        cache = {}
        cache_file = BASE / "discogs_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                log(f"[Discogs] Loaded cache with {len(cache)} entries")
            except Exception as e:
                log(f"[Discogs] Cache load failed, starting fresh: {e}")
                cache = {}
        
        vinyl_records = [d for d in data if d.get("format") == "vinyl"]
        log(f"[Discogs] Enriching {len(vinyl_records)} vinyl records with Mint pricing...")
        
        data = enrich_candidates_with_discogs_lookup(vinyl_records, cache=cache)
        
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        log(f"[Discogs] Cache saved ({len(cache)} entries)")
        log(f"[Discogs] Enrichment complete!")
        
    except Exception as e:
        log(f"[Discogs] ERROR: {e}")
        import traceback
        log(traceback.format_exc())

    log("\n" + "=" * 50)
    log("SCRAPING r/VINYLRELEASES")
    log("=" * 50)
    try:
        reddit_deals = fetch_vinyl_releases()
    except Exception as e:
        log(f"[r/VinylReleases] Fatal error: {e}")
        reddit_deals = []

    data.extend(reddit_deals)
    data = dedupe_deals(data)

    with open(BASE / "live_deals.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    log("\n" + "=" * 50)
    log("SCRAPING UPCOMING VINYL RELEASES")
    log("=" * 50)
    try:
        upcoming = fetch_upcoming_vinyl()
    except Exception as e:
        log(f"[UpcomingVinyl] Fatal error: {e}")
        upcoming = []
    with open(BASE / "upcoming_releases.json", "w", encoding="utf-8") as f:
        json.dump(upcoming, f, indent=2, ensure_ascii=False)
    log(f"[UpcomingVinyl] {len(upcoming)} whitelist matches saved to upcoming_releases.json")

    # ========================================================
    # REAL BUY SIGNAL GATE
    #
    # Stage 2 decides whether the product is interesting
    # enough to enter the buying shortlist.
    #
    # Buyer Brain then contributes store economics and lane.
    # ========================================================

    buy_signals = []

    for deal in data:
        artist = clean(deal.get("artist", ""))
        title = clean(deal.get("title", ""))

        try:
            price = float(deal.get("price", 0) or 0)
        except Exception:
            price = 0.0

        try:
            stage2_score = int(
                deal.get("score", 0) or 0
            )
        except Exception:
            stage2_score = 0

        try:
            buyer_score = int(
                deal.get("buy_score", 0) or 0
            )
        except Exception:
            buyer_score = 0

        quality = (
            deal.get("quality")
            or deal.get("deal_quality")
            or "catalog"
        )

        # Portals belong in live_deals, never buy signals.
        if deal.get("source_type") in {
            "affiliate_catalog_portal",
            "catalog_portal",
        }:
            continue

        # No fake buy signals with no actual price.
        if price <= 0:
            continue

        # Artist sanity.
        if not artist_allowed(artist, title):
            continue

        if artist.lower() in STORE_VENDOR_NAMES:
            continue

        # Stage 2 is the admission gate.
        if stage2_score < 55:
            continue

        buy_signals.append({
            "artist": artist,
            "title": title,
            "raw_title": deal.get(
                "raw_title",
                title,
            ),
            "price": price,
            "source": deal.get("source", ""),
            "source_type": deal.get(
                "source_type",
                "",
            ),
            "link": deal.get("link", ""),
            "image": deal.get("image", ""),

            # Stage 2 intelligence.
            "score": stage2_score,
            "stage2_score": stage2_score,
            "quality": quality,
            "signals": deal.get(
                "signals",
                [],
            ),
            "release_key": deal.get(
                "release_key",
                "",
            ),
            "version": deal.get(
                "version",
                "standard",
            ),
            "format": deal.get(
                "format",
                "vinyl",
            ),

            # Buyer Brain intelligence.
            "buyer_score": buyer_score,
            "inventory_lane": deal.get(
                "inventory_lane",
                "",
            ),
            "customer_lanes": deal.get(
                "customer_lanes",
                [],
            ),
            "decision": (
                deal.get("decision")
                or deal.get("buy_decision")
                or ""
            ),
            "recommended_qty": deal.get(
                "recommended_qty",
                deal.get("qty", 0),
            ),
            "sale_price": deal.get(
                "sale_price",
                deal.get(
                    "estimated_sale_price",
                    0,
                ),
            ),
            "margin_dollars": deal.get(
                "margin_dollars",
                0,
            ),
            "store_fit": deal.get(
                "store_fit",
                "",
            ),
            "why_buy": deal.get(
                "why_buy",
                "",
            ),
            "shelf_placement": deal.get(
                "shelf_placement",
                "",
            ),

            # Discogs intelligence.
            "discogs_mint_price": deal.get(
                "discogs_mint_price",
                0,
            ),
            "discogs_lowest": deal.get(
                "discogs_lowest",
                0,
            ),
            "discogs_num_for_sale": deal.get(
                "discogs_num_for_sale",
                0,
            ),
        })

    buy_signals.sort(
        key=lambda x: (
            x.get("score", 0),
            x.get("buyer_score", 0),
        ),
        reverse=True,
    )

    with open(
        BASE / "buy_signals.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            buy_signals,
            f,
            indent=2,
            ensure_ascii=False,
        )

    log(
        f"[BuySignals] {len(buy_signals)} "
        "qualified signals saved"
    )

    log("\n" + "=" * 50)
    log("SOURCE STATUS SUMMARY")
    log("=" * 50)
    for source_name, status in SOURCE_STATUS.items():
        log(f"  {source_name}: {status}")

    source_summary = {}
    for item in data:
        src = item.get("source", "Unknown")
        source_summary[src] = source_summary.get(src, 0) + 1

    log("----- SOURCE SUMMARY -----")
    for src, count in sorted(source_summary.items(), key=lambda x: x[0].lower()):
        log(f"{src}: {count}")

    with open(BASE / "debug_live_pull.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(DEBUG))

    log(f"\nWrote {len(data)} total live deals")

    send_deal_hunter_notification(
        total_deals=len(data),
        reddit_deals=reddit_deals,
        upcoming_count=len(upcoming),
        buy_signal_count=len(buy_signals),
    )
