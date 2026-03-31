import json
from pathlib import Path

BASE = Path(__file__).resolve().parent

try:
    from deal_selector import apply_best_links
except Exception:
    def apply_best_links(items):
        return items


def load_json(filename: str, default=None):
    path = BASE / filename
    if not path.exists():
        return {} if default is None else default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


artists = load_json("artists.json", {})
rules = load_json("rules.json", {})
filters = load_json("filters.json", {})
taste_profile = load_json("taste_profile.json", {})


def normalize_text(value: str) -> str:
    return (value or "").lower().strip()


def artist_tier(artist_name: str) -> str:
    artist_name = normalize_text(artist_name)
    for tier, names in artists.items():
        lowered = [normalize_text(n) for n in names]
        if artist_name in lowered:
            return tier
    return "other"


def pressing_points(keywords, version_text):
    weights = rules.get("weights", {}).get("pressing", {})
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
        *(keywords or [])
    ]).lower()

    return any(k.lower() in haystack for k in filters.get("ignore_keywords", []))


def special_format_bonus(item):
    fmt = (item.get("format", "") or "").lower()
    text = " ".join(item.get("keywords", []) + [item.get("version", "")]).lower()

    preferred_formats = rules.get("preferred_formats", {})

    if fmt == "vinyl":
        return preferred_formats.get("vinyl", {}).get("base_priority", 0)

    if fmt == "cd":
        needs = filters.get("cd_special_keywords", [])
        return 1 if any(k in text for k in needs) else 0

    if fmt == "cassette":
        needs = filters.get("cassette_special_keywords", [])
        return 1 if any(k in text for k in needs) else 0

    return 0


def get_bucket_match(item):
    artist = normalize_text(item.get("artist", ""))
    text = " ".join([
        item.get("artist", ""),
        item.get("title", ""),
        item.get("raw_title", ""),
        item.get("version", ""),
        item.get("page_text_snippet", ""),
        " ".join(item.get("keywords", []) or [])
    ]).lower()

    best_bucket = ""
    best_score = 0

    for bucket_name, bucket_data in taste_profile.get("core_buckets", {}).items():
        score = 0

        for bucket_artist in bucket_data.get("artists", []):
            if normalize_text(bucket_artist) == artist:
                score += 5

        for keyword in bucket_data.get("keywords", []):
            if keyword.lower() in text:
                score += 1

        if score > best_score:
            best_score = score
            best_bucket = bucket_name

    return best_bucket, best_score


def collector_points(item):
    text = " ".join([
        item.get("title", ""),
        item.get("raw_title", ""),
        item.get("version", ""),
        item.get("availability_text", ""),
        item.get("page_text_snippet", ""),
        " ".join(item.get("keywords", []) or [])
    ]).lower()

    score = 0

    for word in taste_profile.get("collector_keywords", []):
        if word.lower() in text:
            score += 1

    return min(score, 4)


def resale_points(item):
    text = " ".join([
        item.get("title", ""),
        item.get("raw_title", ""),
        item.get("version", ""),
        item.get("availability_text", ""),
        item.get("page_text_snippet", ""),
        item.get("release_date", ""),
        " ".join(item.get("preorder_terms", []) or [])
    ]).lower()

    score = 0

    for word in taste_profile.get("resale_priority_keywords", []):
        if word.lower() in text:
            score += 1

    if item.get("is_preorder"):
        score += 2

    price = safe_price(item.get("best_price", item.get("price", 0)))
    if 0 < price <= 60:
        score += 1

    return min(score, 5)


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
    artist_points = rules.get("weights", {}).get("artist_fit", {}).get(tier, 0)
    version_points = pressing_points(keywords, version)
    deal_points = rules.get("weights", {}).get("deal_quality", {}).get(item.get("deal_quality", "normal"), 0)
    demand_points = rules.get("weights", {}).get("demand", {}).get(item.get("demand", "niche"), 0)
    source_points = rules.get("weights", {}).get("source_boost", {}).get(item.get("source_type", "random"), 0)
    format_points = special_format_bonus(item)

    bucket_name, bucket_points = get_bucket_match(item)
    collector_boost = collector_points(item)
    resale_boost = resale_points(item)
    preorder_boost = 2 if item.get("is_preorder") else 0

    total = (
        artist_points
        + version_points
        + deal_points
        + demand_points
        + source_points
        + format_points
        + bucket_points
        + collector_boost
        + resale_boost
        + preorder_boost
    )

    thresholds = rules.get("decision_thresholds", {})
    if total >= thresholds.get("post_buy_move_fast", 6):
        decision = "POST / BUY / MOVE FAST"
    elif total >= thresholds.get("post_if_content_worthy", 4):
        decision = "POST IF CONTENT-WORTHY"
    elif total >= thresholds.get("personal_call", 3):
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
            "format_points": format_points,
            "bucket_name": bucket_name,
            "bucket_points": bucket_points,
            "collector_boost": collector_boost,
            "resale_boost": resale_boost,
            "preorder_boost": preorder_boost
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
        raw_items = load_json("live_deals.json", [])
        source_file = "live_deals.json"
    elif sample_path.exists():
        raw_items = load_json("sample_deals.json", [])
        source_file = "sample_deals.json"
    else:
        raw_items = []
        source_file = "none"

    if not isinstance(raw_items, list):
        raw_items = []

    print(f"Loaded {len(raw_items)} raw items from {source_file}")

    items = apply_best_links(raw_items)

    results = []
    for item in items:
        if not isinstance(item, dict):
            continue

        scored = score_item(item)
        merged = {**item, **scored}

        if merged.get("decision") == "IGNORE":
            continue

        title = normalize_text(merged.get("title", ""))
        artist = normalize_text(merged.get("artist", ""))

        if not title or title in {"unknown title", "vinyl", "product"}:
            continue

        if artist in {"", "unknown"} and len(title) < 4:
            continue

        results.append(merged)

    results.sort(
        key=lambda r: (
            -(r.get("total", 0) or 0),
            -int(bool(r.get("is_preorder"))),
            safe_price(r.get("best_price", r.get("price", 0))),
            normalize_text(r.get("artist", "")),
            normalize_text(r.get("title", ""))
        )
    )

    out_path = BASE / "scored_deals.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Scored deals written to {out_path}")
    print(f"Final saved deals: {len(results)}")

    for r in results[:25]:
        breakdown = r.get("breakdown", {})
        print(
            f"{r.get('artist', 'Unknown')} - {r.get('title', 'Unknown')}: "
            f"{r.get('total', 0)} => {r.get('decision', 'UNKNOWN')} | "
            f"Bucket: {breakdown.get('bucket_name', 'none')} | "
            f"Best: {r.get('best_source', r.get('source', 'Unknown'))} @ "
            f"{r.get('best_price', r.get('price', 0))}"
        )


if __name__ == "__main__":
    main()
