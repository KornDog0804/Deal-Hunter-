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
    {"name": "Rollin Preorders", "source_type": "shopify_store", "url": "https://rollinrecs.com/collections/pre-orders"},
    {"name": "Sound of Vinyl", "source_type": "shopify_store", "url": "https://thesoundofvinyl.us"},
    {"name": "uDiscover Music", "source_type": "shopify_store", "url": "https://shop.udiscovermusic.com"},
    {"name": "Fearless Records", "source_type": "shopify_store", "url": "https://fearlessrecords.com"},
    {"name": "Rise Records", "source_type": "shopify_store", "url": "https://riserecords.com"},
    {"name": "Rise All", "source_type": "shopify_store", "url": "https://riserecords.com/collections/all"},
    {"name": "Brooklyn Vegan", "source_type": "shopify_store", "url": "https://shop.brooklynvegan.com"},
    {"name": "Revolver", "source_type": "shopify_store", "url": "https://shop.revolvermag.com"},
    {"name": "Newbury Comics", "source_type": "shopify_store", "url": "https://www.newburycomics.com"},
    {"name": "Newbury Preorders", "source_type": "shopify_store", "url": "https://www.newburycomics.com/collections/pre-orders"},
    {"name": "Craft Recordings", "source_type": "shopify_store", "url": "https://craftrecordings.com"},
    {"name": "MNRK Heavy", "source_type": "shopify_store", "url": "https://mnrkheavy.com"},
    {"name": "Equal Vision", "source_type": "shopify_store", "url": "https://equalvision.com"},
    {"name": "Hot Topic", "source_type": "catalog_store", "url": "https://www.hottopic.com/pop-culture/shop-by-license/music/vinyl/"},
{"name": "Pure Noise Records", "source_type": "shopify_store", "url": "https://purenoise.merchnow.com/collections/music"},
{"name": "Rhino", "source_type": "shopify_store", "url": "https://store.rhino.com"},
{"name": "Rhino Music", "source_type": "shopify_store", "url": "https://store.rhino.com/en/rhino-store/music/"},
{"name": "Interscope Records", "source_type": "shopify_store", "url": "https://interscope.com"},
{"name": "Interscope Music", "source_type": "shopify_store", "url": "https://interscope.com/collections/music"},
{"name": "SharpTone Records", "source_type": "shopify_store", "url": "https://sharptonerecords.co"},
{"name": "SharpTone Music", "source_type": "shopify_store", "url": "https://sharptonerecords.co/collections/music"},
{"name": "Rock Metal Fan Nation", "source_type": "shopify_store", "url": "https://rockmetalfannation.com"},
{"name": "Rock Metal Fan Nation Music", "source_type": "shopify_store", "url": "https://rockmetalfannation.com/collections/music"}

    {"name": "Deep Discount", "source_type": "catalog_store", "url": "https://www.deepdiscount.com/music/vinyl"},
    {"name": "Merchbar", "source_type": "catalog_store", "url": "https://www.merchbar.com/vinyl-records"},
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
    "ships by",
    "release date",
    "releases on",
    "available on",
    "street date",
    "expected to ship",
    "available beginning",
    "will ship",
    "ready to ship on",
    "product-template-preorder",
    "data-preorder",
    "inventory_policy\":\"continue"
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
    "kindle", "blu-ray", "dvd", "toy", "figure", "funko",
    "digital", "digital album", "digital download", "mp3", "download"
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


def is_sold_out(text):
    t = (text or "").lower()
    sold_terms = [
        "sold out",
        "sorry sold out",
        "out of stock",
        "currently unavailable",
        "unavailable",
        "not available"
    ]
    return any(term in t for term in sold_terms)


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
        r"\s*-\s*DeepDiscount\.com\s*$",
        r"\s*-\s*Merchbar\s*$"
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
        "/policies/",
        "/blogs/",
        "#",
        "javascript:"
    ]

    if source_type in {"shopify_store", "merchnow_store"}:
        valid_markers = ["/products/"]
    elif source_type == "catalog_store":
        valid_markers = [
            "/product/",
            "/products/",
            "/p/",
            "/item/",
            "/ip/",
            "/music/vinyl"
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

        if any(v in full for v in valid_markers):
            if full not in links:
                links.append(full)

    return links[:300]


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

    return {
        "is_preorder": bool(hits),
        "preorder_terms": hits
    }


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


def fetch_shopify_products(store_root):
    tried = []

    for suffix in [
        "/products.json?limit=250",
        "/collections/all/products.json?limit=250"
    ]:
        try:
            url = store_root.rstrip("/") + suffix
            tried.append(url)
            data = fetch(url)
            parsed = json.loads(data)
            products = parsed.get("products", [])
            if products:
                return products
        except Exception:
            pass

    log(f"Shopify fetch failed: {store_root} | tried: {tried}")
    return []


def build_version_parts(text_blob, title_lower="", link_lower=""):
    keywords = keyword_hits(text_blob)
    version_parts = keywords[:]

    for token in ["2lp", "1lp"]:
        if token in title_lower and token not in version_parts:
            version_parts.append(token)
        if token in link_lower and token not in version_parts:
            version_parts.append(token)

    return keywords, version_parts


def build_shopify_deals(source):
    deals = []
    products = fetch_shopify_products(source["url"])
    log(f'{source["name"]}: {len(products)} products via Shopify JSON')

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

            link = f'{source["url"].rstrip("/")}/products/{handle}'
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
                body_html,
                variant_title,
                handle,
                str(valid_variant.get("inventory_policy", "")),
                str(valid_variant.get("inventory_management", "")),
                str(valid_variant.get("option1", "")),
                str(valid_variant.get("option2", "")),
                str(valid_variant.get("option3", ""))
            ])

            if is_sold_out(combined_blob):
                continue

            preorder_info = detect_preorder_signals(combined_blob)
            release_date = extract_release_date(combined_blob)

            keywords, version_parts = build_version_parts(
                f"{title} {link} {variant_title} {body_html}",
                title_lower=title_lower,
                link_lower=link.lower()
            )

            deal = {
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
                "format": "vinyl",
                "version": " ".join(version_parts) if version_parts else "standard",
                "availability_text": variant_title,
                "page_text_snippet": clean(body_html)[:1000],
                "release_date": release_date,
                "is_preorder": preorder_info["is_preorder"],
                "preorder_terms": preorder_info["preorder_terms"]
            }

            deals.append(deal)
            kept += 1
            if deal["is_preorder"]:
                preorder_kept += 1

        except Exception as e:
            log(f'{source["name"]}: skipped Shopify product | {e}')

    log(f'{source["name"]}: kept {kept} Shopify items | preorders flagged: {preorder_kept}')
    return deals


def build_html_deals(source):
    deals = []

    try:
        html_text = fetch(source["url"])
        links = extract_links(html_text, source["url"], source.get("source_type", "catalog_store"))
        log(f'{source["name"]}: found {len(links)} HTML links')

        kept = 0
        preorder_kept = 0

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

                image = extract_image(page, link)
                preorder_info = detect_preorder_signals(page)
                release_date = extract_release_date(page)

                keywords, version_parts = build_version_parts(
                    f"{raw_title} {link} {page[:3000]}",
                    title_lower=raw_title.lower(),
                    link_lower=link.lower()
                )

                deal = {
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
                    "format": "vinyl",
                    "version": " ".join(version_parts) if version_parts else "standard",
                    "availability_text": "",
                    "page_text_snippet": clean(page)[:1000],
                    "release_date": release_date,
                    "is_preorder": preorder_info["is_preorder"],
                    "preorder_terms": preorder_info["preorder_terms"]
                }

                deals.append(deal)
                kept += 1
                if deal["is_preorder"]:
                    preorder_kept += 1

            except Exception as e:
                log(f'{source["name"]}: skipping product {link} | {e}')

        log(f'{source["name"]}: kept {kept} HTML items | preorders flagged: {preorder_kept}')

    except Exception as e:
        log(f'{source["name"]}: HTML source failed | {e}')

    return deals


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

    preorder_count = sum(1 for item in data if item.get("is_preorder"))
    log(f"Wrote {len(data)} deals to live_deals.json | preorder flagged: {preorder_count}")
