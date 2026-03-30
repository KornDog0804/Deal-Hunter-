# -*- coding: utf-8 -*-
import json
import re
import html
import urllib.request
from urllib.parse import urljoin
from pathlib import Path

BASE = Path(__file__).resolve().parent

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

SOURCES = [
    {"name": "Rollin Records", "source_type": "shopify_store", "url": "https://rollinrecs.com"},
    {"name": "Sound of Vinyl", "source_type": "shopify_store", "url": "https://thesoundofvinyl.us"},
    {"name": "uDiscover Music", "source_type": "shopify_store", "url": "https://shop.udiscovermusic.com"},
    {"name": "Fearless Records", "source_type": "shopify_store", "url": "https://fearlessrecords.com"},
    {"name": "Rise Records", "source_type": "shopify_store", "url": "https://riserecords.com"},
    {"name": "Brooklyn Vegan", "source_type": "shopify_store", "url": "https://shop.brooklynvegan.com"},
    {"name": "Revolver", "source_type": "shopify_store", "url": "https://shop.revolvermag.com"},
    {"name": "Newbury Comics", "source_type": "shopify_store", "url": "https://www.newburycomics.com"},
    {"name": "Craft Recordings", "source_type": "shopify_store", "url": "https://craftrecordings.com"},
    {"name": "MNRK Heavy", "source_type": "shopify_store", "url": "https://mnrkheavy.com"},
    {"name": "Equal Vision", "source_type": "shopify_store", "url": "https://equalvision.com"},

    {"name": "Deep Discount", "source_type": "catalog_store", "url": "https://www.deepdiscount.com/music/vinyl"},
    {"name": "Merchbar", "source_type": "catalog_store", "url": "https://www.merchbar.com/vinyl-records"},
    {"name": "Pure Noise Records", "source_type": "merchnow_store", "url": "https://purenoise.merchnow.com/collections/music"},

    {"name": "Walmart", "source_type": "catalog_store", "url": "https://www.walmart.com/browse/music/vinyl-records/4104_1205481_4104_1044819"}
]

POSITIVE_KEYWORDS = [
    "colored", "exclusive", "limited", "anniversary", "deluxe",
    "zoetrope", "picture disc", "splatter", "variant", "2lp", "1lp",
    "marble", "smush", "quad", "opaque", "clear", "smoke", "translucent"
]

PREORDER_TERMS = [
    "preorder",
    "pre-order",
    "pre order",
    "presale",
    "pre-sale",
    "pre sale",
    "coming soon",
    "ships on",
    "releases on",
    "release date",
    "available on",
    "street date"
]

BANNED_KEYWORDS = [
    "christmas",
    "xmas",
    "holiday",
    "jingle",
    "santa",
    "let it snow",
    "wonderful christmastime",
    "war is over",
    "dean martin",
    "jackson 5",
    "bobby helms",
    "snowed in"
]

BAD_PRODUCT_TERMS = [
    "shirt", "hoodie", "tank top", "tee", "poster", "slipmat", "cassette",
    "cd", "compact disc", "beanie", "hat", "jacket", "bundle", "book",
    "kindle", "blu-ray", "dvd", "toy", "figure", "funko"
]

DEBUG = []


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


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "ignore")


def clean(text):
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("–", "-").replace("|", "-")
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
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


def clean_store_title(title):
    text = clean(title)

    junk_patterns = [
        r"\s*-\s*Music\s*&\s*Performance\s*-\s*Vinyl\s*$",
        r"\s*-\s*Vinyl\s*$",
        r"\s*-\s*Walmart\.com\s*$",
        r"\s*-\s*Shopify\s*$",
        r"\s*-\s*Newbury Comics\s*$",
        r"\s*-\s*Brooklyn Vegan\s*$",
        r"\s*-\s*Revolver\s*$",
        r"\s*-\s*Rise Records\s*$",
        r"\s*-\s*Fearless Records\s*$",
        r"\s*-\s*Sound of Vinyl\s*$",
        r"\s*-\s*uDiscover Music\s*$",
        r"\s*-\s*DeepDiscount\.com\s*$"
    ]

    for pattern in junk_patterns:
        text = re.sub(pattern, "", text, flags=re.I)

    text = re.sub(r"\s+", " ", text).strip(" -")
    return text


def parse_from_slug(link):
    slug = link.rstrip("/").split("/")[-1]
    slug = clean(slug.replace("-", " ")).lower()
    slug = re.sub(
        r"\b(vinyl|lp|2lp|1lp|edition|limited|exclusive|colored|color|disc|picture|anniversary|collector'?s|stereo|version|black|standard|record|records|performance|music|translucent|clear|smoke|splatter|etched|zoetrope)\b",
        "",
        slug,
        flags=re.I
    )
    slug = re.sub(r"\s+", " ", slug).strip()
    return slug


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


def extract_links(html_text, base, source_type="shopify_store"):
    raw_links = re.findall(r'href="([^"]+)"', html_text, re.IGNORECASE)
    links = []

    blocked_markers = [
        "/collections/",
        "/search",
        "/cart",
        "/account",
        "/pages/",
        "#",
        "javascript:"
    ]

    if source_type in {"shopify_store", "merchnow_store"}:
        valid_markers = ["/products/"]
    elif source_type == "catalog_store":
        valid_markers = ["/product/", "/products/", "/p/", "/item/", "/ip/"]
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

    return links[:150]


def extract_title(html_text):
    patterns = [
        r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="twitter:title"[^>]+content="([^"]+)"',
        r'<h1[^>]*>(.*?)</h1>',
        r'"product_title"\s*:\s*"([^"]+)"',
        r'"name"\s*:\s*"([^"]+)"',
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
            if img and any(x in img.lower() for x in [".jpg", ".jpeg", ".
