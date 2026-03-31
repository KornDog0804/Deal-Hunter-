# -*- coding: utf-8 -*-
import json
import re
import html
import time
import random
import urllib.request
import http.cookiejar
from urllib.parse import urljoin
from pathlib import Path

BASE = Path(__file__).resolve().parent

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


SOURCES = [
    {"name": "Rollin Records", "source_type": "shopify_store", "url": "https://rollinrecs.com"},
    {"name": "Rollin Preorders", "source_type": "shopify_store", "url": "https://rollinrecs.com/collections/pre-orders"},
    {"name": "Sound of Vinyl", "source_type": "shopify_store", "url": "https://thesoundofvinyl.us"},
    {"name": "uDiscover Music", "source_type": "shopify_store", "url": "https://shop.udiscovermusic.com"},

    {"name": "Fearless Records", "source_type": "shopify_store", "url": "https://store.fearlessrecords.com"},
    {"name": "Fearless Vinyl", "source_type": "shopify_store", "url": "https://store.fearlessrecords.com/collections/vinyl"},

    {"name": "Rise Records", "source_type": "shopify_store", "url": "https://riserecords.com"},
    {"name": "Rise All", "source_type": "shopify_store", "url": "https://riserecords.com/collections/all"},
    {"name": "Brooklyn Vegan", "source_type": "shopify_store", "url": "https://shop.brooklynvegan.com"},
    {"name": "Revolver", "source_type": "shopify_store", "url": "https://shop.revolvermag.com"},
    {"name": "Newbury Comics", "source_type": "shopify_store", "url": "https://www.newburycomics.com"},
    {"name": "Newbury Preorders", "source_type": "shopify_store", "url": "https://www.newburycomics.com/collections/pre-orders"},
    {"name": "Craft Recordings", "source_type": "shopify_store", "url": "https://craftrecordings.com"},
    {"name": "MNRK Heavy", "source_type": "shopify_store", "url": "https://mnrkheavy.com"},
    {"name": "Equal Vision", "source_type": "shopify_store", "url": "https://equalvision.com"},
    {"name": "Rhino", "source_type": "shopify_store", "url": "https://store.rhino.com"},
    {"name": "Interscope Records", "source_type": "shopify_store", "url": "https://interscope.com"},
    {"name": "SharpTone Records", "source_type": "shopify_store", "url": "https://sharptonerecords.co"},

    {"name": "Rock Metal Fan Nation", "source_type": "shopify_store", "url": "https://rmfnvinyl.com"},
    {"name": "RMFN All", "source_type": "shopify_store", "url": "https://rmfnvinyl.com/collections/all"},

    {"name": "Sumerian Records", "source_type": "shopify_store", "url": "https://sumerianrecords.com"},
    {"name": "Solid State Records", "source_type": "shopify_store", "url": "https://solidstaterecords.store"},
    {"name": "Solid State Vinyl", "source_type": "shopify_store", "url": "https://solidstaterecords.store/collections/vinyl"},

    {"name": "UNFD", "source_type": "catalog_store", "url": "https://usa.24hundred.net/collections/unfd"},

    {"name": "Pure Noise Records", "source_type": "merchnow_store", "url": "https://purenoise.merchnow.com"},

    {"name": "Deep Discount", "source_type": "deepdiscount_store", "url": "https://www.deepdiscount.com"},
    {"name": "Millions of Records", "source_type": "shopify_store", "url": "https://www.millionsofrecords.com"},
    {"name": "IndieMerchstore", "source_type": "shopify_store", "url": "https://www.indiemerchstore.com"},
    {"name": "IndieMerchstore Preorders", "source_type": "shopify_store", "url": "https://www.indiemerchstore.com/collections/pre-orders"},
    {"name": "Merchbar", "source_type": "catalog_store", "url": "https://www.merchbar.com/vinyl-records"},
    {"name": "Hot Topic", "source_type": "catalog_store", "url": "https://www.hottopic.com/pop-culture/shop-by-license/music/vinyl/"},

    {"name": "Walmart", "source_type": "js_store", "url": "https://www.walmart.com/browse/music/vinyl-records/4104_1205481_4104_1044819"},
    {"name": "Target", "source_type": "js_store", "url": "https://www.target.com/c/vinyl-records-music-movies-books/-/N-yz7nt"},
]

POSITIVE_KEYWORDS = [
    "colored", "exclusive", "limited", "anniversary", "deluxe",
    "zoetrope", "picture disc", "splatter", "variant", "2lp", "1lp",
    "marble", "smush", "quad", "opaque", "clear", "smoke", "translucent"
]

PREORDER_STRONG_TERMS = [
    "preorder", "pre-order", "pre order",
    "presale", "pre-sale", "pre sale",
    "expected to ship",
    "ships on",
    "ships by",
    "releases on",
    "release date",
    "street date",
    "available on",
    "available beginning",
    "ready to ship on",
    "will ship"
]

PREORDER_WEAK_TERMS = [
    "coming soon",
    "inventory_policy\":\"continue",
    "data-preorder",
    "product-template-preorder"
]

PREORDER_NEGATIVE_TERMS = [
    "in stock",
    "shipping now",
    "ready to ship",
    "ships immediately",
    "available now",
    "add to cart now",
    "buy now",
    "now available"
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
    "earbuds", "headphones", "airpods", "sticker", "patch", "pin"
]

DEBUG = []
SOURCE_STATUS = {}


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
                log(f"  -> retry {attempt + 1}/{retries} for {url} | {e}")
                time.sleep(delay)
            else:
                raise


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
        "sold out",
        "sorry sold out",
        "out of stock",
        "currently unavailable",
        "unavailable",
        "not available",
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


def detect_format(title="", product_type="", page_text=""):
    blob = f"{title} {product_type} {page_text}".lower()

    if any(x in blob for x in ["cassette", "cd", "compact disc"]):
        if "vinyl" not in blob and " lp" not in blob and "record" not in blob:
            return "other"

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


def extract_release_date(text):
    text = clean(text)

    patterns = [
        r"(?:release date|releases on|ships on|ships by|available on|street date)\s*:?\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"(?:release date|releases on|ships on|ships by|available on|street date)\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        r"(?:release date|releases on|ships on|ships by|available on|street date)\s*:?\s*(\d{4}-\d{2}-\d{2})",
        r"\b([A-Za-z]+\s+\d{1,2},\s+\d{4})\b",
        r"\b(\d{4}-\d{2}-\d{2})\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return clean(m.group(1))

    return ""


def detect_preorder_signals(text, source_name="", source_url="", collection_endpoint_used=False):
    t = (text or "").lower()

    if any(term in t for term in PREORDER_NEGATIVE_TERMS):
        return {"is_preorder": False, "preorder_terms": []}

    strong_hits = [term for term in PREORDER_STRONG_TERMS if term in t]
    weak_hits = [term for term in PREORDER_WEAK_TERMS if term in t]
    release_date = extract_release_date(t)

    source_name_l = (source_name or "").lower()
    source_url_l = (source_url or "").lower()
    source_hint_preorder = (
        "preorder" in source_name_l
        or "pre-order" in source_name_l
        or "/pre-order" in source_url_l
        or "/preorder" in source_url_l
        or collection_endpoint_used
    )

    if strong_hits and release_date:
        return {"is_preorder": True, "preorder_terms": strong_hits + (["release date"] if release_date else [])}

    if source_hint_preorder and strong_hits:
        return {"is_preorder": True, "preorder_terms": strong_hits}

    if weak_hits and not strong_hits and not release_date:
        return {"is_preorder": False, "preorder_terms": []}

    return {"is_preorder": False, "preorder_terms": []}


def extract_links(html_text, base, source_type="shopify_store"):
    raw_links = re.findall(r'href="([^"]+)"', html_text, re.IGNORECASE)
    links = []
    blocked_markers = [
        "/collections/", "/search", "/cart", "/account",
        "/pages/", "/policies/", "/blogs/", "#",
        "javascript:", "mailto:", "tel:"
    ]

    if source_type in {"shopify_store", "merchnow_store"}:
        valid_markers = ["/products/", "/product/"]
    elif source_type == "catalog_store":
        valid_markers = [
            "/product/", "/products/", "/p/", "/item/",
            "/ip/", "/dp/", "/vinyl", "/album", "/record"
        ]
    else:
        valid_markers = ["/products/", "/product/", "/p/", "/item/", "/ip/"]

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

    return links[:500]


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
        return [], "", False

    base = base_match.group(1)
    endpoints = []

    if "/collections/" in url:
        endpoints.append((url + "/products.json?limit=250", True))

    endpoints += [
        (base + "/products.json?limit=250", False),
        (base + "/collections/all/products.json?limit=250", False),
        (base + "/collections/vinyl/products.json?limit=250", False),
        (base + "/collections/music/products.json?limit=250", False),
        (base + "/collections/records/products.json?limit=250", False),
    ]

    seen = set()
    deduped = []
    for endpoint, is_collection in endpoints:
        if endpoint not in seen:
            seen.add(endpoint)
            deduped.append((endpoint, is_collection))

    for endpoint, is_collection in deduped:
        try:
            data = fetch(endpoint)
            parsed = json.loads(data)
            products = parsed.get("products", [])
            if products:
                log(f"  ✓ {endpoint} -> {len(products)} products")
                return products, endpoint, is_collection
        except Exception as e:
            log(f"  ✗ {endpoint} -> {e}")

    return [], "", False


def build_shopify_deals(source):
    deals = []
    products, endpoint_used, collection_endpoint_used = fetch_shopify_products(source["url"])
    log(f'{source["name"]}: {len(products)} products via Shopify JSON')

    if not products:
        SOURCE_STATUS[source["name"]] = "0 products - endpoint may have changed"
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
            tags = p.get("tags", "")
            tags_text = ", ".join(tags) if isinstance(tags, list) else str(tags or "")

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

            image = ""
            imgs = p.get("images", []) or []
            if imgs:
                image = imgs[0].get("src", "")

            body_html = p.get("body_html", "") or ""
            variant_title = clean(valid_variant.get("title", "") or "")

            combined_blob = " ".join([
                title,
                vendor,
                product_type,
                body_html,
                variant_title,
                handle,
                tags_text,
                str(valid_variant.get("inventory_policy", "")),
                str(valid_variant.get("option1", "")),
                str(valid_variant.get("option2", "")),
                str(valid_variant.get("option3", "")),
            ])

            if is_sold_out(combined_blob):
                continue

            fmt = detect_format(title=title, product_type=product_type, page_text=f"{body_html} {tags_text}")
            if fmt != "vinyl":
                continue

            preorder_info = detect_preorder_signals(
                combined_blob,
                source_name=source["name"],
                source_url=source["url"],
                collection_endpoint_used=collection_endpoint_used
            )
            release_date = extract_release_date(combined_blob)

            keywords, version_parts = build_version_parts(
                f"{title} {link} {variant_title} {body_html} {tags_text}",
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
                "deal_quality": "good" if price < 40 else "normal",
                "demand": "steady",
                "format": fmt,
                "version": " ".join(version_parts) if version_parts else "standard",
                "availability_text": variant_title,
                "page_text_snippet": clean(body_html)[:1000],
                "release_date": release_date,
                "is_preorder": preorder_info["is_preorder"],
                "preorder_terms": preorder_info["preorder_terms"],
                "endpoint_used": endpoint_used,
            })
            kept += 1
            if preorder_info["is_preorder"]:
                preorder_kept += 1

        except Exception as e:
            log(f'{source["name"]}: skipped Shopify product | {e}')

    SOURCE_STATUS[source["name"]] = f"{kept} deals (preorders: {preorder_kept})"
    log(f'{source["name"]}: kept {kept} | preorders: {preorder_kept}')
    return deals


def build_html_deals(source):
    deals = []
    try:
        html_text = fetch(source["url"])
        links = extract_links(html_text, source["url"], source.get("source_type", "catalog_store"))
        log(f'{source["name"]}: found {len(links)} HTML links')

        kept = 0
        preorder_kept = 0
        source_name = (source.get("name") or "").lower()

        for link in links:
            try:
                page = fetch(link)

                if looks_like_amazon_link(link):
                    continue
                if is_sold_out(page):
                    continue

                raw_title = extract_title(page)
                if should_skip(raw_title, link):
                    continue

                if "merchbar" in source_name and "vinyl records" in raw_title.lower():
                    continue
                if "hot topic" in source_name and "music & vinyl" in raw_title.lower():
                    continue
                if "deep discount" in source_name and raw_title.lower() in {"vinyl", "music"}:
                    continue

                price = extract_price(page)
                if price <= 0:
                    continue

                artist, album = infer_artist_title(raw_title, link, source_name=source["name"])
                if looks_like_garbage(album):
                    continue
                if contains_bad_product_terms(f"{artist} {album}"):
                    continue
                if not artist_allowed(artist, album):
                    continue

                fmt = detect_format(title=raw_title, product_type="", page_text=page[:3000])
                if fmt != "vinyl":
                    continue

                image = extract_image(page, link)
                preorder_info = detect_preorder_signals(
                    page,
                    source_name=source["name"],
                    source_url=link,
                    collection_endpoint_used=False
                )
                release_date = extract_release_date(page)

                keywords, version_parts = build_version_parts(
                    f"{raw_title} {link} {page[:3000]}",
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
                    "deal_quality": "good" if price < 40 else "normal",
                    "demand": "steady",
                    "format": fmt,
                    "version": " ".join(version_parts) if version_parts else "standard",
                    "availability_text": "",
                    "page_text_snippet": clean(page)[:1000],
                    "release_date": release_date,
                    "is_preorder": preorder_info["is_preorder"],
                    "preorder_terms": preorder_info["preorder_terms"],
                })
                kept += 1
                if preorder_info["is_preorder"]:
                    preorder_kept += 1

            except Exception as e:
                log(f'{source["name"]}: skipping product {link} | {e}')

        SOURCE_STATUS[source["name"]] = f"{kept} deals (preorders: {preorder_kept})"
        log(f'{source["name"]}: kept {kept} | preorders: {preorder_kept}')

    except Exception as e:
        SOURCE_STATUS[source["name"]] = f"FAILED: {e}"
        log(f'{source["name"]}: HTML source failed | {e}')

    return deals


def build_deepdiscount(source):
    """
    Deep Discount needs a browser-like cookie session.
    We warm the session, crawl real vinyl pages, and then hit product pages.
    """
    deals = []
    seen_links = set()

    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
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
        time.sleep(random.uniform(1.1, 2.4))

    def dd_fetch(url, retries=3):
        nonlocal opener
        for attempt in range(retries):
            try:
                with opener.open(url, timeout=25) as resp:
                    code = getattr(resp, "status", 200)
                    html_text = resp.read().decode("utf-8", "ignore")
                    log(f"Deep Discount fetch: {url} -> {code}")
                    return html_text
            except Exception as e:
                log(f"Deep Discount fetch error: {url} | {e}")
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
                dd_sleep()
        return ""

    def extract_dd_links(page_html):
        links = set()
        patterns = [
            r'href="(/[^"]+?/p/\d+)"',
            r'href="(/[^"]+?/product/\d+)"',
            r'href="(/[^"]+?/item/\d+)"',
            r'href="(/[^"]+?/ip/\d+)"',
        ]
        for pattern in patterns:
            for href in re.findall(pattern, page_html, re.I):
                full = urljoin("https://www.deepdiscount.com", href)
                low = full.lower()
                if any(bad in low for bad in [
                    "/search",
                    "/cart",
                    "/account",
                    "/help",
                    "javascript:",
                    "mailto:",
                    "tel:",
                    "#",
                ]):
                    continue
                links.add(full)
        return list(links)

    warmup_urls = [
        "https://www.deepdiscount.com/",
        "https://www.deepdiscount.com/help",
        "https://www.deepdiscount.com/music/vinyl",
        "https://www.deepdiscount.com/music/vinyl/new-releases",
        "https://www.deepdiscount.com/featured-vinyl/b141496",
    ]

    seed_pages = [
        "https://www.deepdiscount.com/music/vinyl",
        "https://www.deepdiscount.com/music/vinyl/new-releases",
        "https://www.deepdiscount.com/featured-vinyl/b141496",
        "https://www.deepdiscount.com/search?mod=AP&cr=vinyl",
    ]

    for warm in warmup_urls:
        _ = dd_fetch(warm)
        dd_sleep()

    kept = 0
    preorder_kept = 0

    for page_url in seed_pages:
        page_html = dd_fetch(page_url)
        if not page_html:
            continue

        links = extract_dd_links(page_html)
        log(f'{source["name"]}: found {len(links)} candidate links from {page_url}')

        for link in links:
            if link in seen_links:
                continue
            seen_links.add(link)

            dd_sleep()
            product_html = dd_fetch(link)
            if not product_html:
                continue

            if is_sold_out(product_html):
                continue

            raw_title = extract_title(product_html)
            if not raw_title:
                continue

            if should_skip(raw_title, link):
                continue

            price = extract_price(product_html)
            if price <= 0:
                continue

            fmt = detect_format(title=raw_title, product_type="", page_text=product_html[:3000])
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
            preorder_info = detect_preorder_signals(
                product_html,
                source_name=source["name"],
                source_url=link,
                collection_endpoint_used=False
            )
            release_date = extract_release_date(product_html)

            keywords, version_parts = build_version_parts(
                f"{raw_title} {link} {product_html[:3000]}",
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
                "deal_quality": "good" if price < 40 else "normal",
                "demand": "steady",
                "format": fmt,
                "version": " ".join(version_parts) if version_parts else "standard",
                "availability_text": "",
                "page_text_snippet": clean(product_html)[:1000],
                "release_date": release_date,
                "is_preorder": preorder_info["is_preorder"],
                "preorder_terms": preorder_info["preorder_terms"],
            })
            kept += 1
            if preorder_info["is_preorder"]:
                preorder_kept += 1

    deduped = dedupe_source_items(deals)
    SOURCE_STATUS[source["name"]] = f"{len(deduped)} deals (preorders: {preorder_kept})"
    log(f'{source["name"]}: kept {len(deduped)} | preorders: {preorder_kept}')
    return deduped


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
        if new_price > 0 and (old_price <= 0 or new_price < old_price):
            seen[key] = item

    return list(seen.values())


def scrape_source(source):
    stype = source.get("source_type", "")

    if stype == "deepdiscount_store":
        return build_deepdiscount(source)

    if stype == "js_store":
        SOURCE_STATUS[source["name"]] = "SKIPPED (JS-rendered - needs API/headless lane)"
        log(f'{source["name"]}: SKIPPED (JS-rendered - needs API/headless lane)')
        return []

    if stype == "merchnow_store":
        deals = build_shopify_deals(source)
        if not deals:
            log(f'{source["name"]}: Merchnow JSON empty, trying HTML fallback')
            deals = build_html_deals(source)
        return deals

    if stype == "shopify_store":
        deals = build_shopify_deals(source)
        if not deals:
            log(f'{source["name"]}: Shopify JSON empty, trying HTML fallback')
            deals = build_html_deals(source)
        return deals

    if stype == "catalog_store":
        return build_html_deals(source)

    log(f'{source["name"]}: unknown source_type "{stype}" - skipping')
    SOURCE_STATUS[source["name"]] = f'SKIPPED (unknown type: {stype})'
    return []


def dedupe_deals(deals):
    seen = {}
    for d in deals:
        key = f'{(d["artist"] or "").lower().strip()}::{(d["title"] or "").lower().strip()}::{(d["source"] or "").lower().strip()}'
        if key not in seen:
            seen[key] = d
        else:
            current = seen[key]
            if d["price"] < current["price"]:
                seen[key] = d
            elif not current.get("is_preorder") and d.get("is_preorder"):
                seen[key] = d
    return list(seen.values())


def build():
    deals = []
    for source in SOURCES:
        log(f"\n{'=' * 50}")
        log(f"Scraping: {source['name']} ({source['source_type']})")
        log(f"{'=' * 50}")
        deals.extend(scrape_source(source))
    return dedupe_deals(deals)


if __name__ == "__main__":
    data = build()

    with open(BASE / "live_deals.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

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

    preorder_count = sum(1 for item in data if item.get("is_preorder"))
    live_count = sum(1 for item in data if not item.get("is_preorder"))
    log(f"\nWrote {len(data)} total deals -> {live_count} live | {preorder_count} preorders")
