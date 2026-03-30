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
    "street date"
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
    "deluxe",
    "zoetrope",
    "picture disc"
]


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(name, default):
    path = BASE / name
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(name, data):
    with open(BASE / name, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_preorder(item):
    if item.get("is_preorder") is True:
        return True

    text = " ".join([
        item.get("title", ""),
        item.get("raw_title", ""),
        item.get("version", ""),
        item.get("availability_text", ""),
        item.get("page_text_snippet", ""),
        item.get("release_date", ""),
        item.get("link", "")
    ]).lower()

    return any(term in text for term in PREORDER_TERMS)


def score_preorder(item, artists):
    score = 40
    text = " ".join([
        item.get("title", ""),
        item.get("raw_title", ""),
        item.get("version", ""),
        item.get("availability_text", ""),
        item.get("page_text_snippet", "")
    ]).lower()

    for word in GRAIL_KEYWORDS:
        if word in text:
            score += 8

    price = float(item.get("best_price", item.get("price", 0)) or 0)
    if 0 < price <= 60:
        score += 10

    artist = (item.get("artist", "") or "").strip().lower()

    tier_1 = [a.lower() for a in artists.get("tier_1_core", [])]
    tier_2 = [a.lower() for a in artists.get("tier_2_adjacent", [])]
    tier_3 = [a.lower() for a in artists.get("tier_3_watchlist", [])]

    if artist in tier_1:
        score += 25
    elif artist in tier_2:
        score += 15
    elif artist in tier_3:
        score += 10

    if item.get("release_date"):
        score += 5

    return min(score, 100)


def badge(score):
    if score >= 85:
        return "GRAIL ALERT"
    if score >= 70:
        return "HOT PREORDER"
    return "WATCHLIST"


def main():
    raw = load_json("live_deals.json", [])
    artists = load_json("artists.json", {})
    old = load_json("preorders.json", {"generated_at": "", "total": 0, "items": []})
    old_items = {f'{(i.get("artist","")).lower()}::{(i.get("title","")).lower()}::{(i.get("source","")).lower()}': i for i in old.get("items", [])}

    preorders = []

    for item in raw:
        if not isinstance(item, dict):
            continue

        if not is_preorder(item):
            continue

        enriched = dict(item)
        enriched["score"] = score_preorder(item, artists)
        enriched["badge"] = badge(enriched["score"])
        enriched["status"] = "preorder"

        key = f'{(item.get("artist","")).lower()}::{(item.get("title","")).lower()}::{(item.get("source","")).lower()}'
        old_item = old_items.get(key)

        enriched["first_seen"] = old_item.get("first_seen") if old_item else now()
        enriched["last_seen"] = now()
        enriched["is_new"] = old_item is None

        preorders.append(enriched)

    preorders.sort(key=lambda x: (-x.get("score", 0), float(x.get("best_price", x.get("price", 999999)) or 999999)))

    output = {
        "generated_at": now(),
        "total": len(preorders),
        "items": preorders[:250]
    }

    save_json("preorders.json", output)
    print(f"Saved {len(preorders)} preorder items.")


if __name__ == "__main__":
    main()
