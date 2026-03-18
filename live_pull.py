# -*- coding: utf-8 -*-
import json
import re
import html
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
    "zoetrope", "picture disc", "splatter", "variant", "2lp", "1lp"
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
    "bobby helms"
]

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def extract_product_links(html_text, base_url):
    matches = re.findall(r'href="([^"]*/products/[^"]+)"', html_text, re.IGNORECASE)
    full_links = []
    for m in matches:
        full = urljoin(base_url, m.split("?")[0])
        if full not in full_links:
            full_links.append(full)
    return full_links[:20]

def extract_title(html_text):
    og = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html_text, re.IGNORECASE)
    if og:
        return html.unescape(og.group(1).strip())

    title = re.search(r"<title>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
    if title:
        return html.unescape(re.sub(r"\s+", " ", title.group(1)).strip())

    return "Unknown Title"

def extract_price(html_text):
    patterns = [
        r'"price"\s*:\s*"?(\\d+\.\d{2})"?',
        r'"amount"\s*:\s*"?(\\d+\.\d{2})"?',
        r'content="(\d+\.\d{2})"\s*[^>]*property="product:price:amount"',
        r'property="product:price:amount"\s*content="(\d+\.\d{2})"',
        r'\$(\d+\.\d{2})',
        r'\$(\d+)'
    ]

    for pattern in patterns:
        m = re.search(pattern, html_text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                pass

    return 0.0

def keyword_hits(text):
    text = text.lower()
    return [k for k in POSITIVE_KEYWORDS if k in text]

def is_banned(text):
    text = text.lower()
    return any(bad in text for bad in BANNED_KEYWORDS)

def clean_text(text):
    text = html.unescape(text)
    text = text.replace("–", "-").replace("|", "-")
    text = re.sub(r"\s+", " ", text).strip()
    return text

def parse_from_link(link):
    slug = link.rstrip("/").split("/")[-1]
    slug = slug.replace("-", " ")
    slug = clean_text(slug)

    # Remove obvious store fluff
    slug = re.sub(r"\b(vinyl|lp|2lp|1lp|edition|limited|exclusive|colored|color|disc|picture|anniversary)\b", "", slug, flags=re.IGNORECASE)
    slug = re.sub(r"\s+", " ", slug).strip()

    return slug

def infer_artist_title(raw_title, link):
    title = clean_text(raw_title)
    link_text = parse_from_link(link)

    # Good pattern: Artist - Album
    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    if len(parts) >= 2:
        artist = parts[0]
        album = parts[1]

        if artist.lower() != album.lower():
            return artist, album

    # Fallback to slug parsing for known bad cases
    slug = clean_text(link_text)

    patterns = [
        (r"^the all american rejects move along", "The All-American Rejects", "Move Along"),
        (r"^sum 41 all killer no filler", "Sum 41", "All Killer No Filler"),
        (r"^nelly furtado loose", "Nelly Furtado", "Loose"),
        (r"^new found glory sticks and stones", "New Found Glory", "Sticks And Stones"),
        (r"^beastie boys root down", "Beastie Boys", "Root Down"),
        (r"^blink 182 dude ranch", "blink-182", "Dude Ranch"),
        (r"^bob seger the silver bullet band night moves", "Bob Seger & The Silver Bullet Band", "Night Moves"),
        (r"^stillwater stillwater", "Stillwater", "Stillwater"),
        (r"^something corporate north", "Something Corporate", "North"),
        (r"^thrice the artist in the ambulance", "Thrice", "The Artist In The Ambulance"),
        (r"^the who sell out", "The Who", "Sell Out"),
        (r"^tears for fears songs from the big chair", "Tears For Fears", "Songs From The Big Chair"),
        (r"^spinal tap this is spinal tap", "Spinal Tap", "This Is Spinal Tap"),
        (r"^spinal tap break like the wind", "Spinal Tap", "Break Like The Wind"),
        (r"^joan osborne relish", "Joan Osborne", "Relish")
    ]

    for pattern, artist, album in patterns:
        if re.search(pattern, slug, re.IGNORECASE):
            return artist, album

    # Last fallback
    return "Unknown Artist", title

def build_live_deals():
    deals = []

    for source in SOURCES:
        try:
            collection_html = fetch(source["url"])
            product_links = extract_product_links(collection_html, source["url"])

            for link in product_links:
                try:
                    product_html = fetch(link)
                    raw_title = extract_title(product_html)
                    text_blob = f"{raw_title} {link}"

                    if is_banned(text_blob):
                        continue

                    price = extract_price(product_html)
                    artist, title = infer_artist_title(raw_title, link)
                    keywords = keyword_hits(text_blob)

                    # Use slug-enhanced version labeling
                    version_parts = keywords[:]
                    if "2lp" in link.lower() and "2lp" not in version_parts:
                        version_parts.append("2lp")
                    if "1lp" in link.lower() and "1lp" not in version_parts:
                        version_parts.append("1lp")

                    deal = {
                        "artist": artist,
                        "title": title,
                        "price": price,
                        "source": source["name"],
                        "source_type": source["source_type"],
                        "link": link,
                        "keywords": keywords,
                        "deal_quality": "good" if price and price < 40 else "normal",
                        "demand": "steady",
                        "format": "vinyl",
                        "version": " ".join(version_parts) if version_parts else "standard"
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
