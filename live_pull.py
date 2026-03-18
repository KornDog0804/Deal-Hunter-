# -*- coding: utf-8 -*-
import json
import re
import urllib.request
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

SOURCES = [
    {
        "name": "Sound of Vinyl",
        "source_type": "trusted_store",
        "url": "https://thesoundofvinyl.us/collections/exclusive"
    },
    {
        "name": "uDiscover Music",
        "source_type": "trusted_store",
        "url": "https://shop.udiscovermusic.com/collections/vinyl"
    }
]

POSITIVE_KEYWORDS = [
    "colored", "exclusive", "limited", "anniversary", "deluxe",
    "zoetrope", "picture disc", "splatter", "variant", "2lp"
]

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def extract_product_links(html, base_url):
    # Pull /products/... links
    matches = re.findall(r'href="([^"]*/products/[^"]+)"', html, re.IGNORECASE)
    full_links = []
    for m in matches:
        full = urljoin(base_url, m.split("?")[0])
        if full not in full_links:
            full_links.append(full)
    return full_links[:12]

def extract_title(html):
    og = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html, re.IGNORECASE)
    if og:
        return og.group(1).strip()
    title = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if title:
        return re.sub(r"\s+", " ", title.group(1)).strip()
    return "Unknown Title"

def extract_price(html):
    # Try common patterns
    patterns = [
        r'"price"\s*:\s*"?(\\d+\\.\\d{2})"?',
        r'\$\\s?(\\d+\\.\\d{2})',
    ]
    for pattern in patterns:
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except:
                pass
    return 0.0

def infer_artist_title(raw_title):
    cleaned = raw_title.replace("|", "-").replace("–", "-")
    parts = [p.strip() for p in cleaned.split(" - ") if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "Unknown Artist", cleaned

def keyword_hits(text):
    text = text.lower()
    return [k for k in POSITIVE_KEYWORDS if k in text]

def build_live_deals():
    deals = []

    for source in SOURCES:
        try:
            html = fetch(source["url"])
            product_links = extract_product_links(html, source["url"])

            for link in product_links:
                try:
                    product_html = fetch(link)
                    raw_title = extract_title(product_html)
                    price = extract_price(product_html)
                    artist, title = infer_artist_title(raw_title)
                    text_blob = f"{raw_title} {link}"
                    keywords = keyword_hits(text_blob)

                    deal = {
                        "artist": artist,
                        "title": title,
                        "price": price,
                        "source": source["name"],
                        "source_type": source["source_type"],
                        "link": link,
                        "keywords": keywords,
                        "deal_quality": "good" if price and price < 40 else "normal",
                        "demand": "steady"
                    }

                    deals.append(deal)
                except Exception as e:
                    print(f"Skipping product {link}: {e}")

        except Exception as e:
            print(f"Skipping source {source['name']}: {e}")

    return deals

if __name__ == "__main__":
    deals = build_live_deals()
    with open("live_deals.json", "w", encoding="utf-8") as f:
        json.dump(deals, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(deals)} live deals to live_deals.json")
