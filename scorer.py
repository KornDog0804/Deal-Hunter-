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
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# pull in your real repo files
artists = load_json("artists.json", {})
filters = load_json("filters.json", {})
taste_profile = load_json("taste_profile.json", {
    "core_buckets": {},
    "collector_keywords": [],
    "resale_priority_keywords": []
})


def normalize_text(value: str) -> str:
    return (value or "").lower().strip()


def safe_price(value):
    try:
        return float(value)
    except Exception:
        return 0.0


def contains_ignore_keywords(title, version_text, keywords):
    haystack = " ".join([
        title or "",
        version_text or "",
        *(keywords or [])
    ]).lower()

    return any(k.lower() in haystack for k in filters.get("ignore_keywords", []))


def artist_tier_points(artist_name: str) -> tuple[str, int]:
    artist_name = normalize_text(artist_name)

    tier_1 = [normalize_text(n) for n in artists.get("tier_1_core", [])]
    tier_2 = [normalize_text(n) for n in artists.get("tier_2_adjacent", [])]
    tier_3 = [normalize_text(n) for n in artists.get("tier_3_watchlist", [])]

    if artist_name in tier_1:
        return "tier_1_core", 50
    if artist_name in tier_2:
        return "tier_2_adjacent", 25
    if artist_name in tier_3:
        return "tier_3_watchlist", 10

    return "other", 5


def bucket_match(item) -> tuple[str, int]:
    artist = normalize_text(item.get("artist", ""))
    text = " ".join([
        item.get("artist", ""),
        item.get("title", ""),
        item.get("raw_title", ""),
        item.get("version", ""),
        item.get("availability_text", ""),
        item.get("page_text_snippet", ""),
        " ".join(item.get("keywords", []) or [])
    ]).lower()

    best_bucket = "none"
    best_score = 0

    for bucket_name, bucket_data in taste_profile.get("core_buckets", {}).items():
        score = 0

        for bucket_artist in bucket_data.get("artists", []):
            if normalize_text(bucket_artist) == artist:
                score += 20

        for keyword in bucket_data.get("keywords", []):
            if keyword.lower() in text:
                score += 3

        if score > best_score:
            best_score = score
            best_bucket = bucket_name

    return best_bucket, best_score


def positive_keyword_points(item) -> int:
    title = normalize_text(item.get("title", ""))
    raw_title = normalize_text(item.get("raw_title", ""))
    version = normalize_text(item.get("version", ""))
    page = normalize_text(item.get("page_text_snippet", ""))
    joined = " ".join([title, raw_title, version, page])

    positives = filters.get("positive_keywords", [])
    score = 0

    for kw in positives:
        if kw.lower() in joined:
            score += 6

    return min(score, 24)


def downrank_points(item) -> int:
    text = " ".join([
        item.get("title", ""),
        item.get("raw_title", ""),
        item.get("version", ""),
        item.get("availability_text", ""),
        item.get("page_text_snippet", "")
    ]).lower()

    score = 0
    for kw in filters.get("downrank_keywords", []):
        if kw.lower() in text:
            score -= 8

    return score


def collector_points(item) -> int:
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
            score += 4

    return min(score, 20)


def resale_points(item) -> int:
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
            score += 4

    if item.get("is_preorder"):
        score += 10

    price = safe_price(item.get("best_price", item.get("price", 0)))
    if 0 < price < 25:
        score += 15
    elif 25 <= price < 40:
        score += 8
    elif price > 60:
        score += 5

    return min(score, 30)


def format_points(item) -> int:
    text = " ".join([
        item.get("title", ""),
        item.get("raw_title", ""),
        item.get("version", "")
    ]).lower()

    score = 0

    if "vinyl" in text:
        score += 5

    if "limited" in text:
        score += 15

    if "exclusive" in text:
        score += 12

    if "preorder" in text or "pre-order" in text:
        score += 8

    if item.get("format", "").lower() == "vinyl":
        score += 5

    return score


def source_points(item) -> int:
    source_type = normalize_text(item.get("source_type", ""))
    if source_type == "shopify_store":
        return 5
    if source_type == "catalog_store":
        return 2
    if source_type == "merchnow_store":
        return 4
    return 0


def score_item(item):
    title = item.get("title", "") or ""
    version = item.get("version", "") or ""
    keywords = item.get("keywords", []) or []

    if contains_ignore_keywords(title, version, keywords):
        return None

    tier_name, tier_score = artist_tier_points(item.get("artist", ""))
    bucket_name, bucket_score = bucket_match(item)

    total = (
        tier_score
        + bucket_score
        + positive_keyword_points(item)
        + collector_points(item)
        + resale_points(item)
        + format_points(item)
        + source_points(item)
        + downrank_points(item)
    )

    if total < 10:
        return None

    decision = "LOW KEY"
    if total >= 85:
        decision = "POST / BUY / MOVE FAST"
    elif total >= 60:
        decision = "POST IF CONTENT-WORTHY"
    elif total >= 35:
        decision = "PERSONAL CALL"

    merged = dict(item)
    merged["total"] = total
    merged["score"] = total
    merged["decision"] = decision
    merged["breakdown"] = {
        "artist_tier": tier_name,
        "artist_points": tier_score,
        "bucket_name": bucket_name,
        "bucket_points": bucket_score,
        "positive_points": positive_keyword_points(item),
        "collector_points": collector_points(item),
        "resale_points": resale_points(item),
        "format_points": format_points(item),
        "source_points": source_points(item),
        "downrank_points": downrank_points(item)
    }

    return merged


def main():
    live_path = BASE / "live_deals.json"

    if not live_path.exists():
        print("❌ live_deals.json not found")
        raise SystemExit(1)

    raw_items = load_json("live_deals.json", [])

    # your live_pull writes a LIST, not {"items": [...]}
    if not isinstance(raw_items, list):
        print("❌ live_deals.json is not a list")
        raise SystemExit(1)

    print(f"Loaded {len(raw_items)} raw items from live_deals.json")

    # apply your existing link/grouping logic
    items = apply_best_links(raw_items)

    results = []
    for item in items:
        if not isinstance(item, dict):
            continue

        scored = score_item(item)
        if not scored:
            continue

        title = normalize_text(scored.get("title", ""))
        artist = normalize_text(scored.get("artist", ""))

        if not title or title in {"unknown title", "vinyl", "product"}:
            continue

        if artist in {"", "unknown"} and len(title) < 4:
            continue

        results.append(scored)

    results.sort(
        key=lambda r: (
            -(r.get("total", 0) or 0),
            -int(bool(r.get("is_preorder"))),
            safe_price(r.get("best_price", r.get("price", 0))),
            normalize_text(r.get("artist", "")),
            normalize_text(r.get("title", ""))
        )
    )

    with open(BASE / "scored_deals.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"🔥 Scored Deals: {len(results)}")

    for r in results[:20]:
        print(
            f"{r.get('artist', 'Unknown')} - {r.get('title', 'Unknown')}: "
            f"{r.get('total', 0)} | {r.get('decision', 'UNKNOWN')} | "
            f"{r.get('best_source', r.get('source', 'Unknown'))} @ "
            f"{r.get('best_price', r.get('price', 0))}"
        )


if __name__ == "__main__":
    main()
