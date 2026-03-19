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
    },
    {
        "name": "Walmart",
        "source_type": "big_box",
        "url": "https://www.walmart.com/browse/music/vinyl-records/4104_1205481_4104_1044819"
    },
    {
        "name": "Best Buy",
        "source_type": "big_box",
        "url": "https://www.bestbuy.com/site/searchpage.jsp?st=vinyl"
    },
    {
        "name": "Deep Discount",
        "source_type": "trusted_store",
        "url": "https://www.deepdiscount.com/music/vinyl"
    },
    {
        "name": "Acoustic Sounds",
        "source_type": "audiophile_store",
        "url": "https://store.acousticsounds.com/index.cfm?get=results&searchtext=vinyl"
    },
    {
        "name": "Merchbar",
        "source_type": "marketplace",
        "url": "https://www.merchbar.com/vinyl-records"
    },
    {
        "name": "Fearless Records",
        "source_type": "label_store",
        "url": "https://fearlessrecords.com/collections/music"
    },
    {
        "name": "Rise Records",
        "source_type": "label_store",
        "url": "https://riserecords.com/collections/music"
    },
    {
        "name": "Ride Records",
        "source_type": "indie_store",
        "url": "https://riderecords.com/collections/all"
    }
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

# ===== JOEY TASTE FILTER =====
# Set to True to only keep artists that fit your collection / site / taste.
ENFORCE_ARTIST_WHITELIST = True

ALLOWED_ARTISTS = {
    "a perfect circle",
    "ac/dc",
    "all-american rejects",
    "the all-american rejects",
    "beastie boys",
    "blessthefall",
    "blink-182",
    "bob seger",
    "bob seger & the silver bullet band",
    "bullet for my valentine",
    "dance gavin dance",
    "fall out boy",
    "hanson",
    "i prevail",
    "john lennon",
    "mariah carey",
    "mötley crüe",
    "motley crue",
    "nelly furtado",
    "new found glory",
    "nirvana",
    "pantera",
    "phantogram",
    "pj harvey",
    "paul mccartney",
    "paul mccartney & wings",
    "rihanna",
    "rush",
    "sleep token",
    "something corporate",
    "spinal tap",
    "styx",
    "sum 41",
    "thrice",
    "tears for fears",
    "the who",
    "wings",
    "yellowcard"
}

# Artists you explicitly do NOT want even if they slip through
BLOCKED_ARTISTS = {
    "bobby helms",
    "dean martin",
    "joan osborne",
    "neil diamond"
}

SLUG_PATTERNS = [
    (r"^the all american rejects move along", "The All-American Rejects", "Move Along"),
    (r"^the all american rejects the all american rejects", "The All-American Rejects", "The All-American Rejects"),
    (r"^sum 41 all killer no filler", "Sum 41", "All Killer No Filler"),
    (r"^sum 41 does this look infected", "Sum 41", "Does This Look Infected?"),
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
    (r"^joan osborne relish", "Joan Osborne", "Relish"),
    (r"^phantogram voices", "Phantogram", "Voices"),
    (r"^a perfect circle mer de noms", "A Perfect Circle", "Mer de Noms"),
    (r"^hanson middle of nowhere", "Hanson", "Middle Of Nowhere"),
    (r"^rush moving pictures", "Rush", "Moving Pictures"),
    (r"^rihanna good girl gone bad", "Rihanna", "Good Girl Gone Bad"),
    (r"^nirvana in utero", "Nirvana", "In Utero"),
    (r"^mariah carey charmbracelet", "Mariah Carey", "Charmbracelet"),
    (r"^paul mccartney new", "Paul McCartney", "NEW"),
    (r"^yellowcard ocean avenue", "Yellowcard", "Ocean Avenue"),
    (r"^wings wings at the speed of sound", "Wings", "Wings At The Speed Of Sound"),
    (r"^styx circling from above", "Styx", "Circling From Above"),
    (r"^john lennon imagine", "John Lennon", "Imagine"),
    (r"^fall out boy believers never die", "Fall Out Boy", "Believers Never Die"),
    (r"^pj harvey to bring you my love", "PJ Harvey", "To Bring You My Love"),
    (r"^neil diamond hot august night iii", "Neil Diamond", "Hot August Night III"),
    (r"^john coltrane blue train", "John Coltrane", "Blue Train"),
    (r"^paul mccartney wings band on the run", "Paul McCartney & Wings", "Band On The Run"),
]

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def clean_text(text):
    text = html.unescape(text or "")
    text = text.replace("–", "-").replace("|", "-")
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"\s+", " ", text).strip()
    return text

def normalize_name(name):
    name = clean_text(name).lower().strip()
    name = name.replace("&", "and")
    name = re.sub(r"\s+", " ", name)
    return name

def artist_allowed(artist):
    artist_norm = normalize_name(artist)

    if artist_norm in BLOCKED_ARTISTS:
        return False

    if not ENFORCE_ARTIST_WHITELIST:
        return True

    return artist_norm in ALLOWED_ARTISTS

def is_banned(text):
    text = (text or "").lower()
    return any(bad in text for bad in BANNED_KEYWORDS)

def keyword_hits(text):
    text = (text or "").lower()
    return [k for k in POSITIVE_KEYWORDS if k in text]

def normalize_album_text(text):
    text = clean_text(text)
    text = re.sub(r"\s+-\s+uDiscover Music$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+-\s+The Sound of Vinyl$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+-\s+Walmart\.com$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+-\s+Best Buy$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+-\s+Merchbar$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bLimited Edition\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bCollector'?s Edition\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bCrystal Clear\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bColor Vinyl\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bColored\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bExclusive\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bVinyl Edition\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bStereo Version\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text).strip(" -")
    return text

def parse_from_link(link):
    slug = link.rstrip("/").split("/")[-1]
    slug = slug.replace("-", " ")
    slug = clean_text(slug)
    slug = re.sub(
        r"\b(vinyl|lp|2lp|1lp|edition|limited|exclusive|colored|color|disc|picture|anniversary|collector'?s|stereo|version|black|standard)\b",
        "",
        slug,
        flags=re.IGNORECASE
    )
    slug = re.sub(r"\s{2,}", " ", slug).strip()
    return slug

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

def extract_title_rise(html_text):
    patterns = [
        r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="twitter:title"[^>]+content="([^"]+)"',
        r'<h1[^>]*>(.*?)</h1>',
        r'"product_title"\s*:\s*"([^"]+)"',
        r'"name"\s*:\s*"([^"]+)"'
    ]

    for pattern in patterns:
        m = re.search(pattern, html_text, re.IGNORECASE | re.DOTALL)
        if m:
            title = clean_text(m.group(1))
            if title:
                return title
    return None

def extract_title_generic(html_text):
    patterns = [
        r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="twitter:title"[^>]+content="([^"]+)"',
        r'<h1[^>]*>(.*?)</h1>',
        r"<title>(.*?)</title>",
        r'"name"\s*:\s*"([^"]+)"'
    ]

    for pattern in patterns:
        m = re.search(pattern, html_text, re.IGNORECASE | re.DOTALL)
        if m:
            title = clean_text(m.group(1))
            if title:
                return title

    return "Unknown Title"

def extract_title(html_text, source_name=None):
    if source_name == "Rise Records":
        better = extract_title_rise(html_text)
        if better:
            return better

    return extract_title_generic(html_text)

def extract_price(html_text):
    patterns = [
        r'"price"\s*:\s*"?(\\d+\.\d{2})"?',
        r'"amount"\s*:\s*"?(\\d+\.\d{2})"?',
        r'content="(\d+\.\d{2})"\s*[^>]*property="product:price:amount"',
        r'property="product:price:amount"\s*content="(\d+\.\d{2})"',
        r'"currentPrice"\s*:\s*\{"price"\s*:\s*(\d+\.\d{2}|\d+)',
        r'"price"\s*:\s*(\d+\.\d{2}|\d+)',
        r'\$(\d+\.\d{2})',
        r'\$(\d+)'
    ]

    for pattern in patterns:
        m = re.search(pattern, html_text, re.IGNORECASE)
        if m:
            try:
                return normalize_price(m.group(1))
            except Exception:
                pass

    return 0.0

def looks_like_garbage_title(title):
    title = (title or "").strip()

    if len(title) < 4:
        return True

    if re.fullmatch(r"[a-z0-9]{6,}", title.lower()):
        return True

    if re.search(r"\b(cd|cp)\b$", title.lower()):
        return True

    return False

def infer_artist_title(raw_title, link):
    title = normalize_album_text(raw_title)
    slug = clean_text(parse_from_link(link))

    for pattern, artist, album in SLUG_PATTERNS:
        if re.search(pattern, slug, re.IGNORECASE):
            return artist, album

    parts = [p.strip() for p in title.split(" - ") if p.strip()]

    if len(parts) >= 3:
        if parts[0].lower() == parts[1].lower():
            return parts[0], normalize_album_text(parts[2])

        if any(store in parts[-1].lower() for store in [
            "udiscover music", "the sound of vinyl", "walmart.com", "best buy", "merchbar"
        ]):
            return parts[0], normalize_album_text(parts[1])

    if len(parts) >= 2 and parts[0].lower() != parts[1].lower():
        return parts[0], normalize_album_text(parts[1])

    if len(slug.split()) >= 2:
        return "Unknown Artist", normalize_album_text(title if title != "Unknown Title" else slug)

    return "Unknown Artist", normalize_album_text(title)

def extract_product_links(html_text, base_url):
    raw_links = re.findall(r'href="([^"]+)"', html_text, re.IGNORECASE)
    full_links = []

    for href in raw_links:
        href = href.split("?")[0]
        full = urljoin(base_url, href)

        if any(x in full for x in ["/products/", "/ip/", "/site/", "/p/"]):
            if full not in full_links:
                full_links.append(full)

    return full_links[:40]

def should_skip_link(link):
    link_lower = (link or "").lower()

    if " cd" in link_lower or "-cd" in link_lower or link_lower.endswith("/cd"):
        return True

    return False

def build_live_deals():
    deals = []

    for source in SOURCES:
        try:
            collection_html = fetch(source["url"])
            product_links = extract_product_links(collection_html, source["url"])

            for link in product_links:
                try:
                    if should_skip_link(link):
                        continue

                    product_html = fetch(link)
                    raw_title = extract_title(product_html, source["name"])
                    text_blob = f"{raw_title} {link}"

                    if is_banned(text_blob):
                        continue

                    price = extract_price(product_html)
                    artist, title = infer_artist_title(raw_title, link)
                    keywords = keyword_hits(text_blob)

                    if looks_like_garbage_title(title):
                        continue

                    if price <= 0:
                        continue

                    if re.search(r"\bcd\b", f"{title} {link}", re.IGNORECASE):
                        continue

                    if not artist_allowed(artist):
                        continue

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
                        "deal_quality": "good" if price < 40 else "normal",
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
