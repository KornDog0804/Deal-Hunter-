# -*- coding: utf-8 -*-
import json
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent

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
    "releases on",
    "release date",
    "available on",
    "street date",
    "expected to ship",
    "available beginning",
    "will ship",
    "ready to ship on",
]

NEGATIVE_PREORDER_TERMS = [
    "in stock",
    "shipping now",
    "ready to ship",
    "ships immediately",
    "available now",
    "add to cart now",
]

GRAIL_KEYWORDS = [
    "limited",
    "exclusive",
    "numbered",
    "splatter",
    "marble",
    "colored",
    "variant",
    "box set",
    "boxset",
    "deluxe",
    "zoetrope",
    "picture disc",
    "anniversary",
    "first pressing",
    "first time on vinyl",
    "indie exclusive",
    "retail exclusive",
]

HARD_BLOCK_TERMS = [
    "digital album",
    "digital download",
    "mp3",
    "streaming",
    "sold out",
    "sorry sold out",
    "out of stock",
    "unavailable",
    "cassette",
    "cd",
    "compact disc",
    "shirt",
    "hoodie",
    "tee",
    "poster",
    "slipmat",
    "book",
    "blu-ray",
    "dvd",
    "funko",
    "toy",
    "figure",
]

MAX_PREORDERS = 250


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(name, default):
    path = BASE / name
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(name, data):
    with open(BASE / name, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def normalize_text(value) -> str:
    return str(value or "").strip().lower()


def safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def ensure_list(value):
    if isinstance(value, list):
        return value
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return list(value)
    except Exception:
        return []


def joined_text(item) -> str:
    return " ".join([
        str(item.get("artist", "")),
        str(item.get("title", "")),
        str(item.get("raw_title", "")),
        str(item.get("version", "")),
        str(item.get("availability_text", "")),
        str(item.get("page_text_snippet", "")),
        str(item.get("release_date", "")),
        str(item.get("link", "")),
        " ".join(str(x) for x in ensure_list(item.get("keywords", []))),
        " ".join(str(x) for x in ensure_list(item.get("preorder_terms", []))),
    ]).lower()


def is_blocked(item) -> bool:
    text = joined_text(item)

    for term in HARD_BLOCK_TERMS:
        if term in text:
            return True

    fmt = normalize_text(item.get("format", ""))
    if fmt and fmt != "vinyl":
        return True

    price = safe_float(item.get("best_price", item.get("price", 0)), 0.0)
    if price <= 0:
        return True

    return False


def is_preorder(item) -> bool:
    if item.get("is_preorder") is True:
        return True

    text = joined_text(item)

    if any(term in text for term in NEGATIVE_PREORDER_TERMS):
        return False

    return any(term in text for term in PREORDER_TERMS)


def artist_bonus(item, artists) -> int:
    artist = normalize_text(item.get("artist", ""))

    tier_1 = [normalize_text(a) for a in artists.get("tier_1_core", [])]
    tier_2 = [normalize_text(a) for a in artists.get("tier_2_adjacent", [])]
    tier_3 = [normalize_text(a) for a in artists.get("tier_3_watchlist", [])]

    def match(pool):
        return any(name and (artist == name or name in artist or artist in name) for name in pool)

    if match(tier_1):
        return 25
    if match(tier_2):
        return 15
    if match(tier_3):
        return 10
    return 0


def grail_points(item) -> int:
    text = joined_text(item)
    score = 0

    for word in GRAIL_KEYWORDS:
        if word in text:
            score += 6

    if item.get("release_date"):
        score += 5

    price = safe_float(item.get("best_price", item.get("price", 0)), 0.0)
    if 0 < price <= 25:
        score += 12
    elif 25 < price <= 40:
        score += 8
    elif 40 < price <= 60:
        score += 5

    return score


def score_preorder(item, artists) -> int:
    existing = safe_float(item.get("total", item.get("score", 0)), 0.0)

    # If scorer.py already gave us a real score, use it as the spine.
    if existing > 0:
        score = int(existing)
    else:
        score = 40 + artist_bonus(item, artists) + grail_points(item)

    # True preorder boost
    score += 12

    # Extra lift for strong collector signals
    text = joined_text(item)
    if "exclusive" in text:
        score += 5
    if "limited" in text:
        score += 5
    if "numbered" in text:
        score += 4

    return min(int(score), 100)


def badge(score: int) -> str:
    if score >= 90:
        return "GRAIL ALERT"
    if score >= 75:
        return "HOT PREORDER"
    return "WATCHLIST"


def dedupe_preorders(items):
    unique = {}

    for item in items:
        artist = normalize_text(item.get("artist", ""))
        title = normalize_text(item.get("title", ""))
        key = f"{artist}::{title}"

        if key not in unique:
            unique[key] = item
            continue

        current = unique[key]
        current_score = safe_float(current.get("score", 0), 0)
        new_score = safe_float(item.get("score", 0), 0)

        if new_score > current_score:
            unique[key] = item
        elif new_score == current_score:
            current_price = safe_float(current.get("best_price", current.get("price", 999999)), 999999)
            new_price = safe_float(item.get("best_price", item.get("price", 999999)), 999999)
            if new_price < current_price:
                unique[key] = item

    return list(unique.values())


def main():
    artists = load_json("artists.json", {})
    old = load_json("preorders.json", {"generated_at": "", "total": 0, "items": []})

    # Prefer scored_deals.json so preorder selection uses the real engine first.
    scored = load_json("scored_deals.json", None)
    raw = load_json("live_deals.json", [])

    if isinstance(scored, list) and scored:
        source_items = scored
        print(f"Using scored_deals.json as preorder source: {len(source_items)} items")
    else:
        source_items = raw
        print(f"Using live_deals.json as preorder source: {len(source_items)} items")

    old_items = {
        f'{normalize_text(i.get("artist", ""))}::{normalize_text(i.get("title", ""))}::{normalize_text(i.get("source", ""))}': i
        for i in old.get("items", [])
        if isinstance(i, dict)
    }

    preorders = []
    blocked = 0
    rejected = 0

    for item in source_items:
        if not isinstance(item, dict):
            continue

        if is_blocked(item):
            blocked += 1
            continue

        if not is_preorder(item):
            rejected += 1
            continue

        enriched = dict(item)
        enriched["is_preorder"] = True
        enriched["score"] = score_preorder(enriched, artists)
        enriched["badge"] = badge(enriched["score"])
        enriched["status"] = "preorder"

        key = (
            f'{normalize_text(item.get("artist", ""))}::'
            f'{normalize_text(item.get("title", ""))}::'
            f'{normalize_text(item.get("source", ""))}'
        )
        old_item = old_items.get(key)

        enriched["first_seen"] = old_item.get("first_seen") if old_item else now()
        enriched["last_seen"] = now()
        enriched["is_new"] = old_item is None

        # Normalize commonly-used fields for the site.
        enriched["best_price"] = safe_float(
            enriched.get("best_price", enriched.get("price", 0)),
            0.0
        )
        enriched["buy_link"] = enriched.get("buy_link", enriched.get("link", ""))
        enriched["best_source"] = enriched.get("best_source", enriched.get("source", "Unknown"))
        enriched["amazon_link"] = enriched.get("amazon_link", "")

        preorders.append(enriched)

    print(f"Raw preorder candidates: {len(preorders)}")
    print(f"Blocked: {blocked}")
    print(f"Rejected as non-preorder: {rejected}")

    preorders = dedupe_preorders(preorders)
    print(f"After dedupe: {len(preorders)}")

    preorders.sort(
        key=lambda x: (
            -safe_float(x.get("score", 0), 0),
            safe_float(x.get("best_price", x.get("price", 999999)), 999999),
            normalize_text(x.get("artist", "")),
            normalize_text(x.get("title", "")),
        )
    )

    output = {
        "generated_at": now(),
        "total": len(preorders),
        "items": preorders[:MAX_PREORDERS]
    }

    save_json("preorders.json", output)
    print(f"Saved {len(preorders[:MAX_PREORDERS])} preorder items.")


if __name__ == "__main__":
    main()
