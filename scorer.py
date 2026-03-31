import json
from pathlib import Path

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

    if artist_name in tier_1:
        return "tier_1_core", 50
    if artist_name in tier_2:
        return "tier_2_adjacent", 25
    if artist_name in tier_3:
        return "tier_3_watchlist", 10

    return "other", 5


def bucket_match(item):
    artist = normalize_text(item.get("artist", ""))
    keyword_list = ensure_list(item.get("keywords", []))

    text = " ".join([
        str(item.get("artist", "")),
        str(item.get("title", "")),
        str(item.get("raw_title", "")),
        str(item.get("version", "")),
        str(item.get("availability_text", "")),
        str(item.get("page_text_snippet", "")),
        " ".join(str(k) for k in keyword_list)
    ]).lower()

    best_bucket = "none"
    best_score = 0

    for bucket_name, bucket_data in taste_profile.get("core_buckets", {}).items():
        score = 0

        for bucket_artist in bucket_data.get("artists", []):
            if normalize_text(bucket_artist) == artist:
                score += 20

        for keyword in bucket_data.get("keywords", []):
            if normalize_text(keyword) in text:
                score += 3

        if score > best_score:
            best_score = score
            best_bucket = bucket_name

    return best_bucket, best_score


def positive_keyword_points(item):
    title = normalize_text(item.get("title", ""))
    raw_title = normalize_text(item.get("raw_title", ""))
    version = normalize_text(item.get("version", ""))
    page = normalize_text(item.get("page_text_snippet", ""))
    joined = " ".join([title, raw_title, version, page])

    positives = filters.get("positive_keywords", [])
    score = 0

    for kw in positives:
        if normalize_text(kw) in joined:
            score += 6

    return min(score, 24)


def downrank_points(item):
    text = " ".join([
        str(item.get("title", "")),
        str(item.get("raw_title", "")),
        str(item.get("version", "")),
        str(item.get("availability_text", "")),
        str(item.get("page_text_snippet", ""))
    ]).lower()

    score = 0
    for kw in filters.get("downrank_keywords", []):
        if normalize_text(kw) in text:
            score -= 8

    return score


def collector_points(item):
    keyword_list = ensure_list(item.get("keywords", []))

    text = " ".join([
        str(item.get("title", "")),
        str(item.get("raw_title", "")),
        str(item.get("version", "")),
        str(item.get("availability_text", "")),
        str(item.get("page_text_snippet", "")),
        " ".join(str(k) for k in keyword_list)
    ]).lower()

    score = 0
    for word in taste_profile.get("collector_keywords", []):
        if normalize_text(word) in text:
            score += 4

    return min(score, 20)


def resale_points(item):
    preorder_terms = ensure_list(item.get("preorder_terms", []))

    text = " ".join([
        str(item.get("title", "")),
        str(item.get("raw_title", "")),
        str(item.get("version", "")),
        str(item.get("availability_text", "")),
        str(item.get("page_text_snippet", "")),
        str(item.get("release_date", "")),
        " ".join(str(k) for k in preorder_terms)
    ]).lower()

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
    text = " ".join([
        str(item.get("title", "")),
        str(item.get("raw_title", "")),
        str(item.get("version", ""))
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


def score_item(item):
    try:
        title = item.get("title", "") or ""
        version = item.get("version", "") or ""
        keywords = ensure_list(item.get("keywords", []))

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


def main():
    try:
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
        skipped_non_dict = 0
        skipped_empty = 0

        for item in items:
            if not isinstance(item, dict):
                skipped_non_dict += 1
                continue

            scored = score_item(item)
            if not scored:
                skipped_empty += 1
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
        print(f"Skipped non-dict: {skipped_non_dict}")
        print(f"Skipped low/ignored/bad: {skipped_empty}")

        for r in results[:20]:
            print(
                f"{r.get('artist', 'Unknown')} - {r.get('title', 'Unknown')}: "
                f"{r.get('total', 0)} | {r.get('decision', 'UNKNOWN')} | "
                f"{r.get('best_source', r.get('source', 'Unknown'))} @ "
                f"{r.get('best_price', r.get('price', 0))}"
            )

    except Exception as e:
        print(f"💀 MAIN CRASH: {e}")
        raise


if __name__ == "__main__":
    main()
