import json
from pathlib import Path

BASE = Path(__file__).resolve().parent

def load_json(filename: str):
    with open(BASE / filename, "r", encoding="utf-8") as f:
        return json.load(f)

# Optional helper
try:
    from deal_selector import apply_best_links
except Exception:
    def apply_best_links(items):
        return items

artists = load_json("artists.json")
rules = load_json("rules.json")
filters = load_json("filters.json")

def artist_tier(artist_name: str) -> str:
    artist_name = (artist_name or "").lower().strip()
    for tier, names in artists.items():
        lowered = [n.lower().strip() for n in names]
        if artist_name in lowered:
            return tier
    return "other"

def pressing_points(keywords, version_text):
    weights = rules["weights"]["pressing"]
    text = " ".join((keywords or []) + [version_text or ""]).lower()
    score = 0

    for key, pts in weights.items():
        if key == "standard_black":
            continue
        if key.replace("_", " ") in text:
            score = max(score, pts)

    return score

def contains_ignore_keywords(title, version_text, keywords):
    haystack = " ".join([
        title or "",
        version_text or "",
        * (keywords or [])
    ]).lower()

    return any(k.lower() in haystack for k in filters.get("ignore_keywords", []))

def special_format_bonus(item):
    fmt = (item.get("format", "") or "").lower()
    text = " ".join(item.get("keywords", []) + [item.get("version", "")]).lower()

    if fmt == "vinyl":
        return rules["preferred_formats"]["vinyl"]["base_priority"]

    if fmt == "cd":
        needs = filters.get("cd_special_keywords", [])
        return 1 if any(k in text for k in needs) else 0

    if fmt == "cassette":
        needs = filters.get("cassette_special_keywords", [])
        return 1 if any(k in text for k in needs) else 0

    return 0

def score_item(item):
    title = item.get("title", "") or ""
    version = item.get("version", "") or ""
    keywords = item.get("keywords", []) or []

    if contains_ignore_keywords(title, version, keywords):
        return {
            "total": 0,
            "decision": "IGNORE",
            "breakdown": {"ignored": True}
        }

    tier = artist_tier(item.get("artist", ""))
    artist_points = rules["weights"]["artist_fit"].get(tier, 0)
    version_points = pressing_points(keywords, version)
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

def safe_price(value):
    try:
        return float(value)
    except Exception:
        return 0.0

def main():
    live_path = BASE / "live_deals.json"
    sample_path = BASE / "sample_deals.json"

    if live_path.exists():
        raw_items = load_json("live_deals.json")
        source_file = "live_deals.json"
    elif sample_path.exists():
        raw_items = load_json("sample_deals.json")
        source_file = "sample_deals.json"
    else:
        raw_items = []
        source_file = "none"

    if not isinstance(raw_items, list):
        raw_items = []

    print(f"Loaded {len(raw_items)} raw items from {source_file}")

    # Pick best links / best prices first if helper exists
    items = apply_best_links(raw_items)

    results = []
    for item in items:
        if not isinstance(item, dict):
            continue

        scored = score_item(item)
        merged = {**item, **scored}

        # Skip useless rows that still sneak through
        if merged.get("decision") == "IGNORE":
            continue

        title = (merged.get("title", "") or "").strip().lower()
        artist = (merged.get("artist", "") or "").strip().lower()

        if not title or title in {"unknown title", "vinyl", "product"}:
            continue

        if artist in {"", "unknown"} and len(title) < 4:
            continue

        results.append(merged)

    # Best stuff first
    results.sort(
        key=lambda r: (
            -(r.get("total", 0) or 0),
            safe_price(r.get("best_price", r.get("price", 0))),
            (r.get("artist", "") or "").lower(),
            (r.get("title", "") or "").lower(),
        )
    )

    out_path = BASE / "scored_deals.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Scored deals written to {out_path}")
    print(f"Final saved deals: {len(results)}")

    for r in results[:25]:
        print(
            f"{r.get('artist', 'Unknown')} - {r.get('title', 'Unknown')}: "
            f"{r.get('total', 0)} => {r.get('decision', 'UNKNOWN')} | "
            f"Best: {r.get('best_source', r.get('source', 'Unknown'))} @ "
            f"{r.get('best_price', r.get('price', 0))}"
        )

if __name__ == "__main__":
    main()
