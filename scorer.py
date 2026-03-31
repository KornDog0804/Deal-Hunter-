import json

# LOAD CONFIGS
from config import (
    positive_keywords,
    ignore_keywords,
    downrank_keywords,
    tier_1_core,
    tier_2_adjacent,
    tier_3_watchlist
)

def score_item(item):
    title = (item.get("title") or "").lower()
    artist = (item.get("artist") or "").lower()
    price = float(item.get("price") or 0)

    score = 0

    # 🚫 HARD IGNORE (ONLY TRUE GARBAGE)
    if any(kw in title for kw in ignore_keywords):
        return None

    # 🎯 TASTE MATCHING (NOT FILTERING)
    if any(a.lower() in artist for a in tier_1_core):
        score += 50
    elif any(a.lower() in artist for a in tier_2_adjacent):
        score += 25
    elif any(a.lower() in artist for a in tier_3_watchlist):
        score += 10
    else:
        score += 5  # keep unknowns alive 👀

    # 🔥 KEYWORD BOOSTS
    for kw in positive_keywords:
        if kw in title:
            score += 10

    # 📉 DOWNRANK (NOT DELETE)
    for kw in downrank_keywords:
        if kw in title:
            score -= 10

    # 💿 FORMAT BOOSTS
    if "vinyl" in title:
        score += 5

    if "preorder" in title:
        score += 8

    if "limited" in title:
        score += 15

    if "exclusive" in title:
        score += 12

    # 💰 PRICE LOGIC (FLIP MODE)
    if price > 0:
        if price < 25:
            score += 15
        elif price < 40:
            score += 8
        elif price > 60:
            score += 5  # premium pieces

    # 🧠 FINAL FILTER (LIGHT TOUCH)
    if score < 10:
        return None

    item["score"] = score
    return item


def main():
    with open("live_deals.json", "r") as f:
        data = json.load(f)

    items = data.get("items", [])

    scored = []

    for item in items:
        result = score_item(item)
        if result:
            scored.append(result)

    # SORT BY SCORE
    scored.sort(key=lambda x: x["score"], reverse=True)

    output = {
        "generated_at": data.get("generated_at", ""),
        "total": len(scored),
        "items": scored[:200]  # cap for sanity
    }

    with open("scored_deals.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"🔥 Scored Deals: {len(scored)}")


if __name__ == "__main__":
    main()
