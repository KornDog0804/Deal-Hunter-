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
    "7\""
]

AMAZON_FRIENDLY_ARTISTS = {
    "ac/dc",
    "a perfect circle",
    "beastie boys",
    "blink-182",
    "bob seger",
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

def normalize_key(text):
    text = (text or "").lower().strip()
    text = text.replace("&", "and")
    text = re.sub(r"[^a-z0-9\s-]", "", text)
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
        low = word.lower().strip()
        if low in COMMON_WORDS_TO_STRIP:
            continue
        words.append(word)

    text = " ".join(words)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def should_show_amazon_option(item: dict) -> bool:
    artist = normalize_key(item.get("artist", ""))
    title = normalize_key(item.get("title", ""))
    version = normalize_key(item.get("version", ""))
    source = normalize_key(item.get("source", ""))

    # If already Amazon, always allow
    link = (item.get("link", "") or "").lower()
    if "amazon.com" in link:
        return True

    # Hide for highly niche / custom variants that Amazon usually won't have
    niche_terms = [
        "zoetrope",
        "etched",
        "b side",
        "exclusive",
        "splatter",
        "starburst",
        "smush",
        "marble",
        "limited to",
        "12 ",
        "7 "
    ]
    hay = f"{title} {version}"
    if any(term in hay for term in niche_terms):
        return False

    # Prefer Amazon only for artists that are mainstream enough
    if artist in AMAZON_FRIENDLY_ARTISTS:
        return True

    # Otherwise hide it
    return False

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

    query_parts = [artist, title, "vinyl"]
    query = "+".join(part.strip().replace(" ", "+") for part in query_parts if part.strip())

    if not query:
        return ""

    return f"https://www.amazon.com/s?k={query}&tag={AMAZON_TAG}"

def choose_best_group_item(items):
    # Lowest price wins. If tied, prefer non-Amazon original source.
    sorted_items = sorted(
        items,
        key=lambda x: (
            float(x.get("price", 999999) or 999999),
            1 if "amazon" in (x.get("source", "") or "").lower() else 0
        )
    )
    return sorted_items[0]

def apply_best_links(raw_items):
    grouped = defaultdict(list)

    for item in raw_items:
        artist = normalize_key(item.get("artist", ""))
        title = normalize_key(item.get("title", ""))
        if not artist or not title:
            continue
        grouped[(artist, title)].append(item)

    final_items = []

    for _, items in grouped.items():
        best = choose_best_group_item(items)
        best_price = float(best.get("price", 0) or 0)
        best_source = best.get("source", "Unknown")
        buy_link = best.get("link", "")
        amazon_link = build_amazon_link(best)

        label = "KORNDOG FIND"
        if "amazon.com" in buy_link.lower():
            label = "AMAZON PICK"
        elif "walmart.com" in buy_link.lower():
            label = "WALMART PICK"

        merged = dict(best)
        merged["all_store_options"] = [
            {
                "source": item.get("source", "Unknown"),
                "price": float(item.get("price", 0) or 0),
                "link": item.get("link", "")
            }
            for item in sorted(items, key=lambda x: float(x.get("price", 999999) or 999999))
        ]
        merged["best_price"] = best_price
        merged["best_source"] = best_source
        merged["buy_link"] = buy_link
        merged["best_label"] = label
        merged["amazon_link"] = amazon_link

        final_items.append(merged)

    return final_items
