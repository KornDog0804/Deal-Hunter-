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
    {"name": "Walmart", "source_type": "big_box", "url": "https://www.walmart.com/browse/music/vinyl-records"},
    {"name": "Best Buy", "source_type": "big_box", "url": "https://www.bestbuy.com/site/searchpage.jsp?st=vinyl"},
    {"name": "Deep Discount", "source_type": "trusted_store", "url": "https://www.deepdiscount.com/music/vinyl"}
]

def load_json(name):
    with open(BASE / name, "r", encoding="utf-8") as f:
        return json.load(f)

ARTIST_CONFIG = load_json("artist_whitelist.json")
SLUG_PATTERNS = load_json("slug_patterns.json")

ALLOWED = {a.lower() for a in ARTIST_CONFIG["allowed_artists"]}
BLOCKED = {a.lower() for a in ARTIST_CONFIG["blocked_artists"]}

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    return urllib.request.urlopen(req).read().decode("utf-8", "ignore")

def clean(t):
    return re.sub(r"\s+", " ", html.unescape(t or "")).strip()

def extract_links(html_text, base):
    links = re.findall(r'href="([^"]+)"', html_text)
    return [urljoin(base, l.split("?")[0]) for l in links if "/products/" in l][:50]

def extract_title(html_text):
    for p in [
        r'property="og:title" content="([^"]+)"',
        r'<title>(.*?)</title>',
        r'<h1[^>]*>(.*?)</h1>'
    ]:
        m = re.search(p, html_text, re.I)
        if m:
            return clean(m.group(1))
    return "Unknown Title"

def extract_price(html_text):
    m = re.search(r"\$(\d+\.\d{2})", html_text)
    return float(m.group(1)) if m else 0

def extract_image(html_text, base):
    for p in [
        r'property="og:image" content="([^"]+)"',
        r'<img[^>]+src="([^"]+)"'
    ]:
        m = re.search(p, html_text, re.I)
        if m:
            return urljoin(base, m.group(1))
    return ""

def allowed(artist):
    a = artist.lower()
    if any(b in a for b in BLOCKED):
        return False
    return any(x in a for x in ALLOWED)

def parse_title(title):
    parts = title.split(" - ")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "Unknown", title

def build():
    deals = []

    for s in SOURCES:
        try:
            html = fetch(s["url"])
            links = extract_links(html, s["url"])

            for link in links:
                try:
                    page = fetch(link)

                    title_raw = extract_title(page)
                    artist, album = parse_title(title_raw)

                    if not allowed(artist):
                        continue

                    price = extract_price(page)
                    if price <= 0:
                        continue

                    image = extract_image(page, link)

                    deals.append({
                        "artist": artist,
                        "title": album,
                        "price": price,
                        "source": s["name"],
                        "link": link,
                        "image": image
                    })

                except:
                    continue

        except:
            continue

    return deals

if __name__ == "__main__":
    data = build()
    with open("live_deals.json", "w") as f:
        json.dump(data, f, indent=2)
