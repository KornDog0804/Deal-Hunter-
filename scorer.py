import json
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent

try:
    from deal_selector import apply_best_links
except Exception as e:
    print(f"⚠️ deal_selector import failed: {e}")

    def apply_best_links(items):
        return items


def load_json(filename: str, default=None):
    path = BASE / filename
    if not path.exists():
        print(f"⚠️ Missing file: {filename} | using default")
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Failed loading {filename}: {e} | using default")
        return default


artists = load_json("artists.json", {}) or {}
filters = load_json("filters.json", {}) or {}
taste_profile = load_json(
    "taste_profile.json",
    {
        "core_buckets": {},
        "collector_keywords": [],
        "resale_priority_keywords": []
    }
) or {
    "core_buckets": {},
    "collector_keywords": [],
    "resale_priority_keywords": []
}


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
    "figure"
]

SOFT_DOWNRANK_TERMS = [
    "backorder",
    "preorder only",
    "mockups are not actual representations",
    "ship dates may change"
]


def normalize_text(value):
    return str(value or "").lower().strip()


def safe_price(value):
    try:
        return float(value)
    except Exception:
        return 0.0


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


def joined_text(item):
    return " ".join([
        str(item.get("artist", "")),
        str(item.get("title", "")),
        str(item.get("raw_title", "")),
        str(item.get("version", "")),
        str(item.get("availability_text", "")),
        str(item.get("page_text_snippet", "")),
        str(item.get("release_date", "")),
        " ".join(str(x) for x in ensure_list(item.get("keywords", []))),
        " ".join(str(x) for x in ensure_list(item.get("preorder_terms", [])))
    ]).lower()


def is_walmart(item):
    return normalize_text(item.get("source", "")) == "walmart"


def hard_block(item):
    if is_walmart(item):
        return False

    text = joined_text(item)

    for term in HARD_BLOCK_TERMS:
        if term in text:
            return True

    fmt = normalize_text(item.get("format", ""))
    if fmt and fmt != "vinyl":
        return True

    price = safe_price(item.get("best_price", item.get("price", 0)))
    if price <= 0:
        return True

    return False


def contains_ignore_keywords(title, version_text, keywords):
    keyword_list = ensure_list(keywords)
    haystack = " ".join([
        str(title or ""),
        str(version_text or ""),
        *[str(k) for k in keyword_list]
    ]).lower()

    return any(str(k).lower() in haystack for k in filters.get("ignore_keywords", []))


def artist_tier_points(artist_name):
    artist_name = normalize_text(artist_name)

    tier_1 = [normalize_text(n) for n in artists.get("tier_1_core", [])]
    tier_2 = [normalize_text(n) for n in artists.get("tier_2_adjacent", [])]
    tier_3 = [normalize_text(n) for n in artists.get("tier_3_watchlist", [])]

    def match(pool):
        return any(name in artist_name or artist_name in name for name in pool if name)

    if match(tier_1):
        return "tier_1_core", 50
    if match(tier_2):
        return "tier_2_adjacent", 25
    if match(tier_3):
        return "tier_3_watchlist", 10

    return "other", 5


def bucket_match(item):
    artist = normalize_text(item.get("artist", ""))
    text = joined_text(item)

    best_bucket = "none"
    best_score = 0

    for bucket_name, bucket_data in taste_profile.get("core_buckets", {}).items():
        score = 0

        for bucket_artist in bucket_data.get("artists", []):
            bucket_artist_norm = normalize_text(bucket_artist)
            if bucket_artist_norm and (bucket_artist_norm == artist or bucket_artist_norm in artist):
                score += 20

        for keyword in bucket_data.get("keywords", []):
            keyword_norm = normalize_text(keyword)
            if keyword_norm and keyword_norm in text:
                score += 3

        if score > best_score:
            best_score = score
            best_bucket = bucket_name

    return best_bucket, best_score


def positive_keyword_points(item):
    text = joined_text(item)
    positives = filters.get("positive_keywords", [])
    score = 0

    for kw in positives:
        if normalize_text(kw) in text:
            score += 6

    return min(score, 24)


def downrank_points(item):
    text = joined_text(item)
    score = 0

    for kw in filters.get("downrank_keywords", []):
        if normalize_text(kw) in text:
            score -= 8

    for kw in SOFT_DOWNRANK_TERMS:
        if kw in text:
            score -= 6

    return score


def collector_points(item):
    text = joined_text(item)
    score = 0

    for word in taste_profile.get("collector_keywords", []):
        if normalize_text(word) in text:
            score += 4

    return min(score, 20)


def resale_points(item):
    text = joined_text(item)
    score = 0

    for word in taste_profile.get("resale_priority_keywords", []):
        if normalize_text(word) in text:
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


def format_points(item):
    text = joined_text(item)
    score = 0

    if "vinyl" in text:
        score += 5
    if "limited" in text:
        score += 15
    if "exclusive" in text:
        score += 12
    if "preorder" in text or "pre-order" in text:
        score += 8
    if normalize_text(item.get("format", "")) == "vinyl":
        score += 5

    return score


def source_points(item):
    source_type = normalize_text(item.get("source_type", ""))
    if source_type == "shopify_store":
        return 5
    if source_type == "catalog_store":
        return 2
    if source_type == "merchnow_store":
        return 4
    return 0


def clean_item(item):
    item = dict(item)

    artist = str(item.get("artist", "") or "").strip()
    title = str(item.get("title", "") or "").strip()
    raw_title = str(item.get("raw_title", "") or "").strip()

    if not title or title.lower() in {"vinyl", "product"}:
        item["title"] = raw_title or "Unknown Title"

    if not artist or len(artist) > 120:
        item["artist"] = "Unknown Artist"

    item["price"] = safe_price(item.get("price", 0))
    item["best_price"] = safe_price(item.get("best_price", item["price"]))

    return item


def score_item(item):
    try:
        item = clean_item(item)

        if is_walmart(item):
            return None

        title = item.get("title", "") or ""
        version = item.get("version", "") or ""
        keywords = ensure_list(item.get("keywords", []))

        if hard_block(item):
            return None

        if contains_ignore_keywords(title, version, keywords):
            return None

        tier_name, tier_score = artist_tier_points(item.get("artist", ""))
        bucket_name, bucket_score = bucket_match(item)

        pos_points = positive_keyword_points(item)
        coll_points = collector_points(item)
        res_points = resale_points(item)
        fmt_points = format_points(item)
        src_points = source_points(item)
        dr_points = downrank_points(item)

        total = (
            tier_score
            + bucket_score
            + pos_points
            + coll_points
            + res_points
            + fmt_points
            + src_points
            + dr_points
        )

        if item.get("is_preorder"):
            total += 15

        if total < 15:
            return None

        if total >= 90:
            decision = "🚨 GRAIL / AUTO BUY"
        elif total >= 70:
            decision = "🔥 STRONG FLIP"
        elif total >= 50:
            decision = "👀 WATCH / CONTENT"
        elif total >= 35:
            decision = "🧠 PERSONAL PICK"
        else:
            decision = "LOW KEY"

        merged = dict(item)
        merged["total"] = total
        merged["score"] = total
        merged["decision"] = decision
        merged["breakdown"] = {
            "artist_tier": tier_name,
            "artist_points": tier_score,
            "bucket_name": bucket_name,
            "bucket_points": bucket_score,
            "positive_points": pos_points,
            "collector_points": coll_points,
            "resale_points": res_points,
            "format_points": fmt_points,
            "source_points": src_points,
            "downrank_points": dr_points
        }

        return merged
    except Exception as e:
        print(f"💥 score_item crash on item: {item.get('artist', 'Unknown')} - {item.get('title', 'Unknown')} | {e}")
        return None


def dedupe_best_variants(results):
    unique = {}

    for r in results:
        artist = normalize_text(r.get("artist", ""))
        title = normalize_text(r.get("title", ""))
        key = f"{artist}__{title}"

        if key not in unique:
            unique[key] = r
            continue

        current = unique[key]
        current_score = current.get("total", 0)
        new_score = r.get("total", 0)

        if new_score > current_score:
            unique[key] = r
        elif new_score == current_score:
            current_price = safe_price(current.get("best_price", current.get("price", 999999)))
            new_price = safe_price(r.get("best_price", r.get("price", 999999)))
            if new_price < current_price:
                unique[key] = r

    return list(unique.values())


def main():
    live_path = BASE / "live_deals.json"

    if not live_path.exists():
        print("❌ live_deals.json not found")
        raise SystemExit(1)

    raw_items = load_json("live_deals.json", [])

    if not isinstance(raw_items, list):
        print(f"❌ live_deals.json is not a list | type={type(raw_items)}")
        raise SystemExit(1)

    print(f"Loaded {len(raw_items)} raw items from live_deals.json")

    try:
        items = apply_best_links(raw_items)
        print(f"After apply_best_links: {len(items)} items")
    except Exception as e:
        print(f"⚠️ apply_best_links failed: {e} | falling back to raw_items")
        items = raw_items

    results = []
    blocked = 0
    walmart_skipped = 0

    for item in items:
        if not isinstance(item, dict):
            continue

        if is_walmart(item):
            walmart_skipped += 1
            continue

        if hard_block(item):
            blocked += 1
            continue

        scored = score_item(item)
        if not scored:
            continue

        results.append(scored)

    print(f"Before dedupe: {len(results)}")
    results = dedupe_best_variants(results)
    print(f"After dedupe: {len(results)}")
    print(f"Hard blocked: {blocked}")
    print(f"Walmart skipped from scoring: {walmart_skipped}")

    results.sort(
        key=lambda r: (
            -int(bool(r.get("is_preorder"))),
            -(r.get("total", 0) or 0),
            safe_price(r.get("best_price", r.get("price", 0))),
            normalize_text(r.get("artist", "")),
            normalize_text(r.get("title", ""))
        )
    )

    with open(BASE / "scored_deals.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"🔥 Scored Deals: {len(results)}")


if __name__ == "__main__":
    main()
