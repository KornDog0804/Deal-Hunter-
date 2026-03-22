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
    {"name": "Pure Noise Records", "source_type": "merchnow_store", "url": "https://purenoise.merchnow.com/collections/music"}
]

POSITIVE_KEYWORDS = [
    "colored", "exclusive", "limited", "anniversary", "deluxe",
    "zoetrope", "picture disc", "splatter", "variant", "2lp", "1lp",
    "marble", "smush", "quad", "opaque", "clear"
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

def should_skip(title, link):
    blob = f"{title} {link}".lower()

    if is_banned(blob):
        return True

    if " cd" in blob or "-cd" in blob or "/cd" in blob:
        return True

    return False

def parse_from_slug(link):
    slug = link.rstrip("/").split("/")[-1]
    slug = clean(slug.replace("-", " ")).lower()
    slug = re.sub(
        r"\b(vinyl|lp|2lp|1lp|edition|limited|exclusive|colored|color|disc|picture|anniversary|collector'?s|stereo|version|black|standard|record|records)\b",
        "",
        slug,
        flags=re.I
    )
    slug = re.sub(r"\s+", " ", slug).strip()
    return slug

def infer_artist_title(raw_title, link, vendor=""):
    title = clean(raw_title)
    slug = parse_from_slug(link)

    for pattern, artist, album in SLUG_PATTERNS:
        if re.search(pattern, slug, re.I):
            return artist, album

    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]

    if vendor:
        return clean(vendor), title

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
        valid_markers = ["/product/", "/products/", "/p/", "/item/"]
    else:
        valid_markers = ["/products/", "/product/", "/p/", "/item/"]

    for href in raw_links:
        href = href.split("?")[0].strip()
        if not href:
            continue

        full = urljoin(base, href)

        if any(b in full for b in blocked_markers):
            continue

        if any(v in full for v in valid_markers):
            if full not in links:
                links.append(full)

    return links[:120]

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
                return title

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
            if img and any(x in img.lower() for x in [".jpg", ".jpeg", ".png", ".webp", "cdn", "images"]):
                return urljoin(base, img)

    return ""

def fetch_shopify_products(store_root):
    try:
        url = store_root.rstrip("/") + "/products.json?limit=250"
        data = fetch(url)
        parsed = json.loads(data)
        return parsed.get("products", [])
    except Exception as e:
        log(f"Shopify fetch failed: {store_root} | {e}")
        return []

def build_shopify_deals(source):
    deals = []
    products = fetch_shopify_products(source["url"])
    log(f'{source["name"]}: {len(products)} products via Shopify JSON')

    kept = 0

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

            if "cd" in title_lower or "cassette" in title_lower:
                continue

            if product_type and all(x not in product_type for x in ["vinyl", "record", "lp"]):
                if any(x in product_type for x in ["shirt", "hoodie", "poster", "hat", "slipmat", "bundle"]):
                    continue

            variants = p.get("variants", []) or []
            if not variants:
                continue

            valid_variant = None
            for v in variants:
                price = normalize_price(v.get("price", 0))
                vtitle = clean(v.get("title", "")).lower()
                if price > 0 and "cd" not in vtitle and "cassette" not in vtitle:
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

            link = f'{source["url"].rstrip("/")}/products/{handle}'
            artist, album = infer_artist_title(title, link, vendor=vendor)

            if looks_like_garbage(album):
                continue

            if not artist_allowed(artist, album):
                continue

            image = ""
            imgs = p.get("images", []) or []
            if imgs:
                image = imgs[0].get("src", "")

            keywords = keyword_hits(f"{title} {link}")

            version_parts = keywords[:]
            if "2lp" in title_lower and "2lp" not in version_parts:
                version_parts.append("2lp")
            if "1lp" in title_lower and "1lp" not in version_parts:
                version_parts.append("1lp")

            deals.append({
                "artist": artist,
                "title": album,
                "price": price,
                "source": source["name"],
                "source_type": source["source_type"],
                "link": link,
                "image": image,
                "keywords": keywords,
                "deal_quality": "good" if price < 40 else "normal",
                "demand": "steady",
                "format": "vinyl",
                "version": " ".join(version_parts) if version_parts else "standard"
            })
            kept += 1

        except Exception as e:
            log(f'{source["name"]}: skipped Shopify product | {e}')

    log(f'{source["name"]}: kept {kept} Shopify items')
    return deals

def build_html_deals(source):
    deals = []

    try:
        html_text = fetch(source["url"])
        links = extract_links(html_text, source["url"], source.get("source_type", "catalog_store"))
        log(f'{source["name"]}: found {len(links)} HTML links')

        kept = 0
        for link in links:
            try:
                page = fetch(link)
                raw_title = extract_title(page)

                if should_skip(raw_title, link):
                    continue

                price = extract_price(page)
                if price <= 0:
                    continue

                artist, album = infer_artist_title(raw_title, link)

                if looks_like_garbage(album):
                    continue

                if not artist_allowed(artist, album):
                    continue

                image = extract_image(page, link)
                keywords = keyword_hits(f"{raw_title} {link}")

                version_parts = keywords[:]
                if "2lp" in link.lower() and "2lp" not in version_parts:
                    version_parts.append("2lp")
                if "1lp" in link.lower() and "1lp" not in version_parts:
                    version_parts.append("1lp")

                deals.append({
                    "artist": artist,
                    "title": album,
                    "price": price,
                    "source": source["name"],
                    "source_type": source["source_type"],
                    "link": link,
                    "image": image,
                    "keywords": keywords,
                    "deal_quality": "good" if price < 40 else "normal",
                    "demand": "steady",
                    "format": "vinyl",
                    "version": " ".join(version_parts) if version_parts else "standard"
                })
                kept += 1

            except Exception as e:
                log(f'{source["name"]}: skipping product {link} | {e}')

        log(f'{source["name"]}: kept {kept} HTML items')

    except Exception as e:
        log(f'{source["name"]}: HTML source failed | {e}')

    return deals

def dedupe_deals(deals):
    seen = {}
    for d in deals:
        key = f'{(d["artist"] or "").lower()}::{(d["title"] or "").lower()}::{(d["source"] or "").lower()}'
        if key not in seen:
            seen[key] = d
        else:
            if d["price"] < seen[key]["price"]:
                seen[key] = d
    return list(seen.values())

def build():
    deals = []

    for source in SOURCES:
        if source["source_type"] == "shopify_store":
            deals.extend(build_shopify_deals(source))
        else:
            deals.extend(build_html_deals(source))

    return dedupe_deals(deals)

if __name__ == "__main__":
    data = build()

    with open(BASE / "live_deals.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    with open(BASE / "debug_live_pull.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(DEBUG))

    log(f"Wrote {len(data)} deals to live_deals.json")
