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
    "colored","exclusive","limited","anniversary","deluxe",
    "zoetrope","picture disc","splatter","variant","2lp","1lp",
    "marble","smush","quad","opaque","clear","smoke","translucent"
]

PREORDER_TERMS = [
    "preorder","pre-order","pre order","presale","pre-sale","pre sale",
    "coming soon","ships on","releases on","release date","available on","street date"
]

BANNED_KEYWORDS = [
    "christmas","xmas","holiday","jingle","santa","let it snow",
    "wonderful christmastime","war is over","dean martin",
    "jackson 5","bobby helms","snowed in"
]

BAD_PRODUCT_TERMS = [
    "shirt","hoodie","tank top","tee","poster","slipmat","cassette",
    "cd","compact disc","beanie","hat","jacket","bundle","book",
    "kindle","blu-ray","dvd","toy","figure","funko"
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
    except:
        return 0.0
    if value >= 1000:
        value = value / 100.0
    return round(value, 2)

def extract_links(html_text, base, source_type="shopify_store"):
    raw_links = re.findall(r'href="([^"]+)"', html_text, re.IGNORECASE)
    links = []

    valid_markers = ["/products/","/product/","/p/","/item/","/ip/"]

    for href in raw_links:
        full = urljoin(base, href)
        if any(v in full for v in valid_markers):
            if full not in links:
                links.append(full)

    return links[:150]

def extract_title(html_text):
    m = re.search(r"<title>(.*?)</title>", html_text, re.I)
    if m:
        return clean(m.group(1))
    return "Unknown Title"

def extract_price(html_text):
    m = re.search(r"\$(\d+\.\d{2})", html_text)
    if m:
        return float(m.group(1))
    return 0.0

# ✅ FIXED FUNCTION
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
            if img and any(x in img.lower() for x in [
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".gif",
                "cdn",
                "images"
            ]):
                return urljoin(base, img)

    return ""

def is_preorder(html_text):
    text = html_text.lower()
    return any(term in text for term in PREORDER_TERMS)

def run():
    results = []

    for source in SOURCES:
        try:
            log(f"Scanning {source['name']}...")
            html_text = fetch(source["url"])
            links = extract_links(html_text, source["url"], source["source_type"])

            for link in links:
                try:
                    page = fetch(link)

                    if not is_preorder(page):
                        continue

                    title = extract_title(page)
                    price = extract_price(page)
                    image = extract_image(page, link)

                    results.append({
                        "artist": "Unknown",
                        "title": title,
                        "price": price,
                        "image": image,
                        "link": link,
                        "store": source["name"],
                        "type": "preorder"
                    })

                except Exception as e:
                    log(f"Error parsing {link}: {e}")

        except Exception as e:
            log(f"Error scanning {source['name']}: {e}")

    with open(BASE / "preorders.json", "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": "",
            "total": len(results),
            "items": results
        }, f, indent=2)

    log(f"Done. Found {len(results)} preorders.")

if __name__ == "__main__":
    run()
