import json
from pathlib import Path
from deal_selector import apply_best_links

BASE = Path(__file__).resolve().parent

def load_json(filename: str):
    with open(BASE / filename, "r", encoding="utf-8") as f:
        return json.load(f)

artists = load_json("artists.json")
rules = load_json("rules.json")
filters = load_json("filters.json")

def artist_tier(artist_name: str) -> str:
    for tier, names in artists.items():
        if artist_name.lower() in [n.lower() for n in names]:
            return tier
    return "other"

def pressing_points(keywords, version_text):
    weights = rules["weights"]["pressing"]
    text = " ".join(keywords + [version_text]).lower()
    score = 0
    for key, pts in weights.items():
        if key == "standard_black":
            continue
        if key.replace("_", " ") in text:
            score = max(score, pts)
    return score

def contains_ignore_keywords(title, version_text, keywords):
    haystack = " ".join([title, version_text] + keywords).lower()
    return any(k.lower() in haystack for k in filters["ignore_keywords"])

def special_format_bonus(item):
    fmt = item.get("format", "").lower()
    text = " ".join(item.get("keywords", []) + [item.get("version", "")]).lower()

    if fmt == "vinyl":
        return rules["preferred_formats"]["vinyl"]["base_priority"]

    if fmt == "cd":
        needs = filters["cd_special_keywords"]
        return 1 if any(k in text for k in needs) else 0

    if fmt == "cassette":
        needs = filters["cassette_special_keywords"]
        return 1 if any(k in text for k in needs) else 0

    return 0

def score_item(item):
    if contains_ignore_keywords(item.get("title", ""), item.get("version", ""), item.get("keywords", [])):
        return {
            "total": 0,
            "decision": "IGNORE",
            "breakdown": {"ignored": True}
        }

    tier = artist_tier(item.get("artist", ""))
    artist_points = rules["weights"]["artist_fit"].get(tier, 0)
    version_points = pressing_points(item.get("keywords", []), item.get("version", ""))
    deal_points = rules["weights"]["deal_quality"].get(item.get("deal_quality", "normal"), 0)
    demand_points = rules["weights"]["demand"].get(item.get("demand", "niche"), 0)
    source_points = rules["weights"]["source_boost"].get(item.get("source_type", "random"), 0)
    format_points = special_format_bonus(item)

    total = artist_points + version_points + deal_points + demand_points + source_points + format_points

    thresholds = rules["decision_thresholds"]
    if total >= thresholds["post_buy_move_fast"]:
        decision = "POST / BUY / MOVE FAST"
    elif total >= thresholds["post_if_content_worthy"]:
        decision = "POST IF CONTENT-WORTHY"
    elif total >= thresholds["personal_call"]:
        decision = "PERSONAL CALL"
    else:
        decision = "IGNORE"

    return {
        "total": total,
        "decision": decision,
        "breakdown": {
            "artist_tier": tier,
            "artist_points": artist_points,
            "version_points": version_points,
            "deal_points": deal_points,
            "demand_points": demand_points,
            "source_points": source_points,
            "format_points": format_points
        }
    }

def main():
    if (BASE / "live_deals.json").exists():
        raw_items = load_json("live_deals.json")
    else:
        raw_items = load_json("sample_deals.json")

    items = apply_best_links(raw_items)

    results = []
    for item in items:
        scored = score_item(item)
        results.append({**item, **scored})

    out_path = BASE / "scored_deals.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("Scored deals written to", out_path)
    for r in results:
        print(
            f"{r['artist']} - {r['title']}: {r['total']} => {r['decision']} | "
            f"Best: {r.get('best_source', 'Unknown')} @ {r.get('best_price', 0)}"
        )

if __name__ == "__main__":
    main()
