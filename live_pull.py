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
    {"name": "Rollin Records", "source_type": "indie_store", "url": "https://rollinrecs.com/collections/vinyl-records"},
    {"name": "Sound of Vinyl", "source_type": "trusted_store", "url": "https://thesoundofvinyl.us/collections/exclusive"},
    {"name": "uDiscover Music", "source_type": "trusted_store", "url": "https://shop.udiscovermusic.com/collections/vinyl"},
    {"name": "Deep Discount", "source_type": "trusted_store", "url": "https://www.deepdiscount.com/music/vinyl"},
    {"name": "Fearless Records", "source_type": "label_store", "url": "https://fearlessrecords.com/collections/music"},
    {"name": "Rise Records", "source_type": "label_store", "url": "https://riserecords.com/collections/music"},
    {"name": "Ride Records", "source_type": "indie_store", "url": "https://riderecords.com/collections/all"},
    {"name": "Merchbar", "source_type": "marketplace", "url": "https://www.merchbar.com/vinyl-records"}
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
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read().decode("utf-8", "ignore")

def clean(text):
    text = html.unescape(text or "")
    text = text.replace("–", "-").replace("|", "-")
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"\s+", " ", text).strip()
    return text

def normalize_name(text):
    text = clean(text).lower()
    text = text.replace("&", "and")
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

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

def extract_links(html_text, base):
    raw_links = re.findall(r'href="([^"]+)"', html_text, re.IGNORECASE)
    found = []

    valid_markers = [
        "/products/",
        "/product/",
        "/p/",
        "/item/",
        "/records/",
        "/vinyl/",
        "/music/"
    ]

    blocked_markers = [
        "/collections/",
        "/search",
        "/cart",
        "/account",
        "/pages/",
        "#"
    ]

    for href in raw_links:
        href = href.split("?")[0].strip()
        if not href:
            continue

        full = urljoin(base, href)

        if any(b in full for b in blocked_markers):
            continue

        if any(v in full for v in valid_markers):
            if full not in found:
                found.append(full)

    return found[:80]

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
            if not img:
                continue
            if any(x in img.lower() for x in [".jpg", ".jpeg", ".png", ".webp", "cdn", "images"]):
                return urljoin(base, img)

    return ""

def looks_like_garbage(text):
    t = (text or "").strip().lower()

    if len(t) < 4:
        return True

    if re.fullmatch(r"[a-z0-9]{6,}", t):
        return True

    if t in {"unknown title", "product", "vinyl"}:
        return True

    return False

def parse_from_slug(link):
    slug = link.rstrip("/").split("/")[-1]
    slug = slug.replace("-", " ")
    slug = clean(slug).lower()
    slug = re.sub(
        r"\b(vinyl|lp|2lp|1lp|edition|limited|exclusive|colored|color|disc|picture|anniversary|collector'?s|stereo|version|black|standard|record|records)\b",
        "",
        slug,
        flags=re.I
    )
    slug = re.sub(r"\s+", " ", slug).strip()
    return slug

def infer_artist_title(raw_title, link):
    title = clean(raw_title)
    slug = parse_from_slug(link)

    for pattern, artist, album in SLUG_PATTERNS:
        if re.search(pattern, slug, re.I):
            return artist, album

    parts = [p.strip() for p in title.split(" - ") if p.strip()]

    if len(parts) >= 2:
        return parts[0], parts[1]

    if len(parts) == 1 and parts[0]:
        words = parts[0].split()
        if len(words) >= 4:
            return "Unknown Artist", parts[0]

    return "Unknown Artist", title

def should_skip_link(link):
    ll = (link or "").lower()
    if " cd" in ll or "-cd" in ll or ll.endswith("/cd"):
        return True
    return False

def dedupe_deals(deals):
    seen = {}
    for d in deals:
        key = f'{normalize_name(d["artist"])}::{normalize_name(d["title"])}::{normalize_name(d["source"])}'
        if key not in seen:
            seen[key] = d
            continue

        old = seen[key]
        if (d.get("price", 0) or 0) < (old.get("price", 999999) or 999999):
            seen[key] = d

    return list(seen.values())

def build():
    deals = []

    for source in SOURCES:
        try:
            html_text = fetch(source["url"])
            links = extract_links(html_text, source["url"])
            print(f'{source["name"]}: found {len(links)} links')

            for link in links:
                try:
                    if should_skip_link(link):
                        continue

                    page = fetch(link)
                    raw_title = extract_title(page)
                    image = extract_image(page, link)

                    if is_banned(f"{raw_title} {link}"):
                        continue

                    price = extract_price(page)
                    if price <= 0:
                        continue

                    artist, album = infer_artist_title(raw_title, link)

                    if looks_like_garbage(album):
                        continue

                    if re.search(r"\bcd\b", f"{artist} {album} {link}", re.I):
                        continue

                    if not artist_allowed(artist, album):
                        continue

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

                except Exception as e:
                    print(f"Skipping product {link}: {e}")

        except Exception as e:
            print(f'Skipping source {source["name"]}: {e}')

    return dedupe_deals(deals)

if __name__ == "__main__":
    data = build()
    with open(BASE / "live_deals.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(data)} live deals to live_deals.json")
