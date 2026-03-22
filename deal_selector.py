import re
from collections import defaultdict

AMAZON_TAG = "korndog20-20"

COMMON_WORDS_TO_STRIP = [
    "exclusive",
    "limited",
    "edition",
    "color",
    "colored",
    "vinyl",
    "lp",
    "2lp",
    "1lp",
    "splatter",
    "zoetrope",
    "etched",
    "etching",
    "b-side",
    "bside",
    "variant",
    "pressing",
    "black",
    "clear",
    "opaque",
    "smush",
    "marble",
    "starburst",
    "with",
    "w/",
    "12\"",
    "7\"",
    "tri-stripe",
    "tri",
    "stripe",
    "blue",
    "purple",
    "red",
    "orange",
    "green",
    "pink",
    "white",
    "yellow",
    "silver",
    "gold",
    "moonlight",
    "pale"
]

AMAZON_FRIENDLY_ARTISTS = {
    "acdc",
    "a perfect circle",
    "beastie boys",
    "blink-182",
    "bob seger",
    "bob seger the silver bullet band",
    "bullet for my valentine",
    "dance gavin dance",
    "disturbed",
    "fall out boy",
    "foo fighters",
    "ghost",
    "hanson",
    "john lennon",
    "mariah carey",
    "nelly furtado",
    "new found glory",
    "nirvana",
    "pantera",
    "paul mccartney",
    "red hot chili peppers",
    "rihanna",
    "rush",
    "sevendust",
    "sleep token",
    "slipknot",
    "something corporate",
    "spinal tap",
    "styx",
    "sum 41",
    "system of a down",
    "tears for fears",
    "the all-american rejects",
    "the who",
    "thrice",
    "white lion",
    "wings",
    "yellowcard"
}

STRICT_NICHE_TERMS = [
    "zoetrope",
    "etched",
    "etching",
    "exclusive",
    "splatter",
    "starburst",
    "smush",
    "marble",
    "limited to",
    "tri-stripe",
    "tri stripe",
    "moonlight",
    "pale moonlight",
    "clear and",
    "clear &",
    "black and",
    "black &",
    "12 inch",
    "7 inch"
]

SAFE_AMAZON_TITLE_EXTRAS = {
    "ocean avenue",
    "songs from the big chair",
    "all killer no filler",
    "dude ranch",
    "night moves",
    "in utero",
    "moving pictures",
    "californication",
    "the poison",
    "home",
    "pride",
    "loose",
    "charmbracelet",
    "new",
    "sell out",
    "root down",
    "north",
    "the artist in the ambulance",
    "sticks and stones"
}

def normalize_key(text):
    text = (text or "").lower().strip()
    text = text.replace("&", "and")
    text = text.replace("’", "'")
    text = re.sub(r"[^a-z0-9\s\-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def clean_album_for_amazon(title: str) -> str:
    text = (title or "").strip()

    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = text.replace("–", " ").replace("-", " ")
    text = text.replace("/", " ")

    words = []
    for word in text.split():
        low = normalize_key(word)
        if low in COMMON_WORDS_TO_STRIP:
            continue
        words.append(word)

    text = " ".join(words)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def normalize_group_title(title: str) -> str:
    text = normalize_key(title)
    text = re.sub(r"\b(vinyl|lp|2lp|1lp|edition|limited|exclusive|colored|color|variant|splatter|zoetrope|etched|etching|black|clear|opaque|marble|smush|starburst)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def safe_float(value, default=999999.0):
    try:
        return float(value)
    except Exception:
        return default

def title_is_too_variant_heavy(item: dict) -> bool:
    title = normalize_key(item.get("title", ""))
    version = normalize_key(item.get("version", ""))
    hay = f"{title} {version}"

    if any(term in hay for term in STRICT_NICHE_TERMS):
        return True

    if re.search(r"\b7\b", hay):
        return True

    return False

def artist_is_amazon_friendly(artist: str) -> bool:
    artist = normalize_key(artist)
    return artist in AMAZON_FRIENDLY_ARTISTS

def title_is_safe_for_amazon(title: str) -> bool:
    title_key = normalize_group_title(title)
    if title_key in SAFE_AMAZON_TITLE_EXTRAS:
        return True

    # Safer default for cleaner, normal album names
    if len(title_key.split()) >= 2 and len(title_key) <= 40:
        return True

    return False

def should_show_amazon_option(item: dict) -> bool:
    source_link = (item.get("link", "") or "").lower()
    if "amazon.com" in source_link:
        return True

    artist = item.get("artist", "") or ""
    title = item.get("title", "") or ""

    if not artist_is_amazon_friendly(artist):
        return False

    if title_is_too_variant_heavy(item):
        return False

    if not title_is_safe_for_amazon(title):
        return False

    return True

def build_amazon_link(item: dict) -> str:
    source_link = (item.get("link", "") or "").strip()
    artist = (item.get("artist", "") or "").strip()
    title = clean_album_for_amazon(item.get("title", "") or "")

    if not should_show_amazon_option(item):
        return ""

    if "amazon.com" in source_link:
        if "tag=" in source_link:
            return source_link
        joiner = "&" if "?" in source_link else "?"
        return f"{source_link}{joiner}tag={AMAZON_TAG}"

    if not artist or not title:
        return ""

    query_parts = [artist, title, "vinyl"]
    query = "+".join(part.strip().replace(" ", "+") for part in query_parts if part.strip())

    if not query:
        return ""

    return f"https://www.amazon.com/s?k={query}&tag={AMAZON_TAG}"

def choose_best_group_item(items):
    # Lowest price wins. If tied, prefer trusted non-marketplace type first.
    source_rank = {
        "trusted_store": 0,
        "shopify_store": 0,
        "label_store": 1,
        "indie_store": 1,
        "audiophile_store": 1,
        "catalog_store": 2,
        "marketplace": 3,
        "big_box": 4,
        "random": 5
    }

    sorted_items = sorted(
        items,
        key=lambda x: (
            safe_float(x.get("price", 999999)),
            source_rank.get((x.get("source_type", "") or "random"), 5),
            1 if "amazon" in (x.get("source", "") or "").lower() else 0
        )
    )
    return sorted_items[0]

def build_store_options(items):
    rows = []
    seen = set()

    sorted_items = sorted(
        items,
        key=lambda x: (
            safe_float(x.get("price", 999999)),
            (x.get("source", "") or "").lower()
        )
    )

    for item in sorted_items:
        key = (
            (item.get("source", "") or "").lower().strip(),
            safe_float(item.get("price", 999999)),
            (item.get("link", "") or "").strip()
        )
        if key in seen:
            continue
        seen.add(key)

        rows.append({
            "source": item.get("source", "Unknown"),
            "price": safe_float(item.get("price", 0), 0),
            "link": item.get("link", "")
        })

    return rows

def apply_best_links(raw_items):
    grouped = defaultdict(list)

    for item in raw_items:
        artist = normalize_key(item.get("artist", ""))
        title = normalize_group_title(item.get("title", ""))

        if not artist or not title:
            continue

        grouped[(artist, title)].append(item)

    final_items = []

    for _, items in grouped.items():
        if not items:
            continue

        best = choose_best_group_item(items)
        best_price = safe_float(best.get("price", 0), 0)
        best_source = best.get("source", "Unknown")
        buy_link = best.get("link", "")
        amazon_link = build_amazon_link(best)

        label = "KORNDOG FIND"
        if "amazon.com" in buy_link.lower():
            label = "AMAZON PICK"
        elif "walmart.com" in buy_link.lower():
            label = "WALMART PICK"

        merged = dict(best)
        merged["all_store_options"] = build_store_options(items)
        merged["best_price"] = best_price
        merged["best_source"] = best_source
        merged["buy_link"] = buy_link
        merged["best_label"] = label
        merged["amazon_link"] = amazon_link

        final_items.append(merged)

    final_items.sort(
        key=lambda x: (
            -safe_float(x.get("total", 0), 0),
            safe_float(x.get("best_price", 999999))
        )
    )

    return final_items
