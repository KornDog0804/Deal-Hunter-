# -*- coding: utf-8 -*-
import json
import re
import html
import time
import urllib.request
from urllib.parse import urljoin
from pathlib import Path

BASE = Path(__file__).resolve().parent

# Rotate user agents to reduce blocks
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
]
_ua_index = 0

def next_ua():
    global _ua_index
    ua = USER_AGENTS[_ua_index % len(USER_AGENTS)]
    _ua_index += 1
    return ua

# ── SOURCES ──────────────────────────────────────────────────────────────────
# source_type options:
#   shopify_store   → hits /products.json (fast, reliable)
#   merchnow_store  → Merchnow-hosted Shopify (same endpoint, different base)
#   catalog_store   → HTML scrape fallback
#   js_store        → JS-rendered, skipped until we have an API
# ─────────────────────────────────────────────────────────────────────────────
SOURCES = [
    # ── Shopify Stores ────────────────────────────────────────────────────────
    {"name": "Rollin Records",        "source_type": "shopify_store", "url": "https://rollinrecs.com"},
    {"name": "Rollin Preorders",      "source_type": "shopify_store", "url": "https://rollinrecs.com/collections/pre-orders"},
    {"name": "Sound of Vinyl",        "source_type": "shopify_store", "url": "https://thesoundofvinyl.us"},
    {"name": "uDiscover Music",       "source_type": "shopify_store", "url": "https://shop.udiscovermusic.com"},
    {"name": "Fearless Records",      "source_type": "shopify_store", "url": "https://fearlessrecords.com"},
    {"name": "Rise Records",          "source_type": "shopify_store", "url": "https://riserecords.com"},
    {"name": "Rise All",              "source_type": "shopify_store", "url": "https://riserecords.com/collections/all"},
    {"name": "Brooklyn Vegan",        "source_type": "shopify_store", "url": "https://shop.brooklynvegan.com"},
    {"name": "Revolver",              "source_type": "shopify_store", "url": "https://shop.revolvermag.com"},
    {"name": "Newbury Comics",        "source_type": "shopify_store", "url": "https://www.newburycomics.com"},
    {"name": "Newbury Preorders",     "source_type": "shopify_store", "url": "https://www.newburycomics.com/collections/pre-orders"},
    {"name": "Craft Recordings",      "source_type": "shopify_store", "url": "https://craftrecordings.com"},
    {"name": "MNRK Heavy",            "source_type": "shopify_store", "url": "https://mnrkheavy.com"},
    {"name": "Equal Vision",          "source_type": "shopify_store", "url": "https://equalvision.com"},
    {"name": "Rhino",                 "source_type": "shopify_store", "url": "https://store.rhino.com"},
    {"name": "Interscope Records",    "source_type": "shopify_store", "url": "https://interscope.com"},
    {"name": "SharpTone Records",     "source_type": "shopify_store", "url": "https://sharptonerecords.co"},
    {"name": "Rock Metal Fan Nation", "source_type": "shopify_store", "url": "https://rockmetalfannation.com"},
    {"name": "Sumerian Records",      "source_type": "shopify_store", "url": "https://sumerianrecords.com"},
    {"name": "Solid State Records",   "source_type": "shopify_store", "url": "https://solidstaterecords.com"},
    {"name": "UNFD",                  "source_type": "shopify_store", "url": "https://store.unfd.com.au"},

    # ── Merchnow Stores (Shopify under the hood) ──────────────────────────────
    {"name": "Pure Noise Records",    "source_type": "merchnow_store", "url": "https://purenoise.merchnow.com"},

    # ── HTML Catalog Stores ───────────────────────────────────────────────────
    {"name": "Deep Discount",         "source_type": "catalog_store", "url": "https://www.deepdiscount.com/music/vinyl"},
    {"name": "Merchbar",              "source_type": "catalog_store", "url": "https://www.merchbar.com/vinyl-records"},

    # ── JS-Rendered (skipped until affiliate/open API is ready) ──────────────
    {"name": "Walmart",               "source_type": "js_store",      "url": "https://www.walmart.com/browse/music/vinyl-records/4104_1205481_4104_1044819"},
    {"name": "Target",                "source_type": "js_store",      "url": "https://www.target.com/c/vinyl-records-music-movies-books/-/N-yz7nt"},
    {"name": "Hot Topic",             "source_type": "js_store",      "url": "https://www.hottopic.com/pop-culture/shop-by-license/music/vinyl/"},
]

# ── KEYWORDS ─────────────────────────────────────────────────────────────────
POSITIVE_KEYWORDS = [
    "colored", "exclusive", "limited", "anniversary", "deluxe",
    "zoetrope", "picture disc", "splatter", "variant", "2lp", "1lp",
    "marble", "smush", "quad", "opaque", "clear", "smoke", "translucent"
]

PREORDER_TERMS = [
    "preorder", "pre-order", "pre order", "presale", "pre-sale", "pre sale",
    "coming soon", "ships on", "ships by", "release date", "releases on",
    "available on", "street date", "expected to ship", "available beginning",
    "will ship", "ready to ship on", "product-template-preorder",
    "data-preorder", "inventory_policy\":\"continue"
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
    "digital", "digital album", "digital download", "mp3", "download"
]

DEBUG = []
SOURCE_STATUS = {}


# ── LOGGING ──────────────────────────────────────────────────────────────────
def log(msg):
    print(msg)
    DEBUG.append(msg)


def load_json(name):
    with open(BASE / name, "r", encoding="utf-8") as f:
        return json.load(f)


ARTIST_CONFIG = load_json("artist_whitelist.json")
SLUG_PATTERNS = load_json("slug_patterns.json")

ENFORCE_ARTIST_WHITELIST = ARTIST_CONFIG.get("enforce_artist_whitelist", True)
ALLOWED = [a.lower().strip() for a in ARTIST_CONFIG.get("allowed_artists", [])]
BLOCKED = [a.lower().strip() for a in ARTIST_CONFIG.get("blocked_artists", [])]


# ── FETCH WITH RETRY ─────────────────────────────────────────────────────────
def fetch(url, retries=2, delay=2):
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": next_ua(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "identity",
                "Connection": "keep-alive",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", "ignore")
        except Exception as e:
            if attempt < retries:
                log(f"  → retry {attempt + 1}/{retries} for {url} | {e}")
                time.sleep(delay)
            else:
                raise


# ── TEXT HELPERS ─────────────────────────────────────────────────────────────
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


def is_sold_out(text):
    t = (text or "").lower()
    return any(term in t for term in [
        "sold out", "sorry sold out", "out of stock",
        "currently unavailable", "unavailable", "not available"
    ])


def looks_like_amazon_link(url):
    u = (url or "").lower()
    return "amazon.com" in u or "amzn.to" in u


def artist_allowed(artist, title=""):
    hay = f"{artist} {title}".lower()
    if any(b in hay for b in BLOCKED):
        return False
    if not ENFORCE_ARTIST_WHITELIST:
        return True
    return any(a in hay for a in ALLOWED)


def keyword_hits(text):
    t = (text or "").lower()
    return [k for k in POSITIVE_KEYWORDS if k in t]


def looks_like_garbage(text):
    t = (text or "").strip().lower()
    if len(t) < 3:
        return True
    if t in {"unknown title", "product", "vinyl"}:
        return True
    if re.fullmatch(r"[a-z0-9]{6,}", t):
        return True
    return False


def contains_bad_product_terms(text):
    t = (text or "").lower()
    return any(term in t for term in BAD_PRODUCT_TERMS)


def should_skip(title, link):
    blob = f"{title} {link}".lower()
    if is_banned(blob):
        return True
    if contains_bad_product_terms(blob):
        return True
    return False


# ── TITLE CLEANING ────────────────────────────────────────────────────────────
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
    ]
    for pattern in junk_patterns:
        text = re.sub(pattern, "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" -")
    return text


def parse_from_slug(link):
    slug = link.rstrip("/").split("/")[-1]
    slug = clean(slug.replace("-", " ")).lower()
    slug = re.sub(
        r"\b(vinyl|lp|2lp|1lp|edition|limited|exclusive|colored|color|disc|picture|anniversary|collectors?|stereo|version|black|standard|record|records|performance|music|translucent|clear|smoke|splatter|etched|zoetrope)\b",
        "", slug, flags=re.I
    )
    return re.sub(r"\s+", " ", slug).strip()


def split_artist_album_from_title(title):
    title = clean_store_title(title)
    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "", title


def infer_artist_title(raw_title, link, vendor="", source_name=""):
    title = clean_store_title(raw_title)
    slug = parse_from_slug(link)
    vendor = clean(vendor)

    for pattern, artist, album in SLUG_PATTERNS:
        if re.search(pattern, slug, re.I):
            return artist, album

    split_artist, split_album = split_artist_album_from_title(title)
    if split_artist and split_album:
        if not contains_bad_product_terms(split_artist) and not looks_like_garbage(split_album):
            return split_artist, split_album

    if vendor and vendor.lower() not in {"vinyl", "music", "records"}:
        if not contains_bad_product_terms(vendor) and not looks_like_garbage(title):
            return vendor, title

    if len(slug.split()) >= 3:
        return "Unknown Artist", slug.title()

    return "Unknown Artist", title


# ── PREORDER + RELEASE DATE ───────────────────────────────────────────────────
def detect_preorder_signals(text):
    t = (text or "").lower()
    hits = [term for term in PREORDER_TERMS if term in t]
    date_patterns = [
        r"release date[:\s]*[a-z]+\s+\d{1,2},\s+\d{4}",
        r"releases on[:\s]*[a-z]+\s+\d{1,2},\s+\d{4}",
        r"ships (?:on|by)?[:\s]*[a-z]+\s+\d{1,2},?\s+\d{4}",
        r"available (?:on)?[:\s]*[a-z]+\s+\d{1,2},?\s+\d{4}",
        r"\b\d{4}-\d{2}-\d{2}\b"
    ]
    if any(re.search(p, t) for p in date_patterns):
        if "release date" not in hits:
            hits.append("release date pattern")
    return {"is_preorder": bool(hits), "preorder_terms": hits}


def extract_release_date(text):
    text = clean(text)
    patterns = [
        r"(?:release date|releases on|ships on|ships by|available on|street date)\s*:?\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"(?:release date|releases on|ships on|ships by|available on|street date)\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        r"(?:release date|releases on|ships on|ships by|available on|street date)\s*:?\s*(\d{4}-\d{2}-\d{2})"
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return clean(m.group(1))
    return ""


# ── HTML EXTRACTION ───────────────────────────────────────────────────────────
def extract_links(html_text, base, source_type="shopify_store"):
    raw_links = re.findall(r'href="([^"]+)"', html_text, re.IGNORECASE)
    links = []
    blocked_markers = [
        "/collections/", "/search", "/cart", "/account",
        "/pages/", "/policies/", "/blogs/", "#", "javascript:"
    ]
    if source_type in {"shopify_store", "merchnow_store"}:
        valid_markers = ["/products/"]
    elif source_type == "catalog_store":
        valid_markers = ["/product/", "/products/", "/p/", "/item/", "/ip/", "/dp/", "/music/vinyl", "/vinyl", "/album"]
    else:
        valid_markers = ["/products/", "/product/", "/p/", "/item/", "/ip/"]

    for href in raw_links:
        href = href.strip()
        if not href:
            continue
        full = urljoin(base, href)
        if any(b in full for b in blocked_markers):
            continue
        if any(v in full for v in valid_markers):
            if full not in links:
                links.append(full)
    return links[:300]


def extract_title(html_text):
    patterns = [
        r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="twitter:title"[^>]+content="([^"]+)"',
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


# ── SHOPIFY FETCH ─────────────────────────────────────────────────────────────
def fetch_shopify_products(source_url):
    """
    Smart Shopify endpoint resolver.
    Handles both base store URLs and collection-specific URLs.
    """
    url = source_url.rstrip("/")

    # Extract base domain
    base_match = re.match(r'(https?://[^/]+)', url)
    if not base_match:
        return []
    base = base_match.group(1)

    # Build ordered list of endpoints to try
    endpoints = []

    if "/collections/" in url:
        # Collection-specific: try that collection's JSON first
        endpoints.append(url + "/products.json?limit=250")

    # Always try base store endpoints as fallback
    endpoints += [
        base + "/products.json?limit=250",
        base + "/collections/all/products.json?limit=250",
        base + "/collections/vinyl/products.json?limit=250",
        base + "/collections/music/products.json?limit=250",
        base + "/collections/records/products.json?limit=250",
    ]

    # Dedupe
    seen = set()
    deduped = []
    for e in endpoints:
        if e not in seen:
            seen.add(e)
            deduped.append(e)

    for endpoint in deduped:
        try:
            data = fetch(endpoint)
            parsed = json.loads(data)
            products = parsed.get("products", [])
            if products:
                log(f"  ✓ {endpoint} → {len(products)} products")
                return products
        except Exception as e:
            log(f"  ✗ {endpoint} → {e}")

    return []


# ── SHOPIFY DEAL BUILDER ──────────────────────────────────────────────────────
def build_shopify_deals(source):
    deals = []
    products = fetch_shopify_products(source["url"])
    log(f'{source["name"]}: {len(products)} products via Shopify JSON')

    if not products:
        SOURCE_STATUS[source["name"]] = "0 products — endpoint may have changed"
        return []

    kept = 0
    preorder_kept = 0

    for p in products:
        try:
            title = clean(p.get("title", ""))
            if not title:
                continue

            vendor = clean(p.get("vendor", ""))
            product_type = clean(p.get("product_type", "")).lower()
            title_lower = title.lower()

            if should_skip(title, ""):
                continue

            if product_type and any(x in product_type for x in BAD_PRODUCT_TERMS):
                continue

            variants = p.get("variants", []) or []
            if not variants:
                continue

            valid_variant = None
            for v in variants:
                price = normalize_price(v.get("price", 0))
                vtitle = clean(v.get("title", "")).lower()
                if price > 0 and not contains_bad_product_terms(vtitle):
                    valid_variant = v
                    break

            if not valid_variant:
                continue

            price = normalize_price(valid_variant.get("price", 0))
            if price <= 0:
                continue

            handle = p.get("handle", "")
            if not handle:
                continue

            # Always build product link from base domain
            base_match = re.match(r'(https?://[^/]+)', source["url"])
            base_url = base_match.group(1) if base_match else source["url"]
            link = f'{base_url}/products/{
