# run_preorders.py
import json
import re
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent

PREORDER_TERMS = [
    "preorder", "pre-order", "pre order",
    "presale", "pre sale",
    "coming soon",
    "ships on", "releases on", "release date"
]

GRAIL_KEYWORDS = [
    "limited", "exclusive", "numbered",
    "splatter", "marble", "colored",
    "variant", "box set", "deluxe"
]

def now():
    return datetime.utcnow().isoformat()

def load_json(name):
    with open(BASE / name, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(name, data):
    with open(BASE / name, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def is_preorder(item):
    text = f"{item.get('title','')} {item.get('version','')} {item.get('link','')}".lower()
    return any(term in text for term in PREORDER_TERMS)

def score_preorder(item):
    score = 0
    text = f"{item.get('title','')} {item.get('version','')}".lower()

    # base preorder boost
    score += 40

    # grail keywords
    for word in GRAIL_KEYWORDS:
        if word in text:
            score += 10

    # price sweet spot
    price = float(item.get("price", 0) or 0)
    if price and price <= 50:
        score += 10

    # artist tiers boost (reuse your system lightly)
    artist = (item.get("artist","") or "").lower()
    if artist:
        if artist in [a.lower() for a in load_json("artists.json").get("tier_1_core", [])]:
            score += 25
        elif artist in [a.lower() for a in load_json("artists.json").get("tier_2_adjacent", [])]:
            score += 15
        elif artist in [a.lower() for a in load_json("artists.json").get("tier_3_watchlist", [])]:
            score += 10

    return min(score, 100)

def badge(score):
    if score >= 85:
        return "GRAIL ALERT"
    if score >= 70:
        return "HOT PREORDER"
    return "WATCHLIST"

def main():
    try:
        raw = load_json("live_deals.json")
    except:
        raw = []

    preorders = []

    for item in raw:
        if not isinstance(item, dict):
            continue

        if not is_preorder(item):
            continue

        s = score_preorder(item)

        enriched = dict(item)
        enriched["score"] = s
        enriched["badge"] = badge(s)
        enriched["status"] = "preorder"
        enriched["detected_at"] = now()

        preorders.append(enriched)

    preorders.sort(key=lambda x: -x.get("score", 0))

    output = {
        "generated_at": now(),
        "total": len(preorders),
        "items": preorders[:200]  # keep top 200 only
    }

    save_json("preorders.json", output)

    print(f"Saved {len(preorders)} preorder items")

if __name__ == "__main__":
    main()
