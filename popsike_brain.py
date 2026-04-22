import re
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# =========================
# KORNDOG DEAL HUNTER BRAIN
# =========================

# -------------------------
# CONFIG
# -------------------------

JOEY_CORE_ARTISTS = {
    "sleep token",
    "erra",
    "polaris",
    "currents",
    "wage war",
    "dayseeker",
    "memphis may fire",
    "the ghost inside",
    "boundaries",
    "palisades",
    "bleed from within",
    "thornhill",
    "eidola",
    "dance gavin dance",
    "if not for me",
    "wind walkers",
    "awaken i am",
    "nerv",
    "make them suffer",
    "korn",
    "slipknot",
    "limp bizkit",
    "system of a down",
    "pantera",
    "deftones",
    "tool",
    "linkin park",
    "breaking benjamin",
    "three days grace",
    "incubus",
    "seether",
    "atreyu",
    "all that remains",
    "killswitch engage",
    "a day to remember",
    "attack attack!",
    "fire from the gods",
    "nothing more",
    "8ball & mjg",
    "ugk",
    "three 6 mafia",
    "project pat",
    "juicy j",
    "pimp c",
    "bun b",
    "trick daddy",
    "plies",
    "chingy",
    "lil jon",
    "usher",
    "joe",
    "tyrese",
    "lsg",
    "xscape",
    "the isley brothers",
    "earth wind and fire",
    "bill withers",
    "tony toni tone",
    "lenny williams",
    "michael jackson",
    "twista",
    "chris brown",
    "t pain",
    "journey",
    "foreigner",
    "boston",
    "heart",
    "reo speedwagon",
    "styx",
    "eagles",
    "billy squier",
    "the doobie brothers",
    "steve miller band",
    "toto",
    "tommy tutone",
    "ozzy osbourne",
    "judas priest",
    "monster magnet",
}

JOEY_ADJACENT_KEYWORDS = {
    "metalcore",
    "post-hardcore",
    "melodic hardcore",
    "alt metal",
    "nu metal",
    "rap metal",
    "hard rock",
    "southern rap",
    "dirty south",
    "r&b",
    "soul",
    "classic rock",
}

RARITY_KEYWORDS = {
    "limited",
    "numbered",
    "splatter",
    "marble",
    "swirl",
    "liquid filled",
    "zoetrope",
    "picture disc",
    "colored",
    "exclusive",
    "anniversary",
    "first press",
    "rsd",
    "record store day",
    "out of print",
    "sold out",
    "deluxe",
    "foil",
    "alt cover",
    "alternate cover",
    "hand numbered",
    "obi",
    "import",
    "variant",
}

COLLECTOR_SOURCES = {
    "sumerian records",
    "unfd",
    "sharptone records",
    "solid state records",
    "solid state vinyl",
    "pure noise records",
    "rise records",
    "rise all",
    "fearless records",
    "smartpunk records",
    "revolver",
    "newbury comics",
    "brooklyn vegan",
    "equal vision",
    "rollin records",
    "rock metal fan nation",
    "rmfn all",
    "pirates press records",
    "trust records",
    "spinefarm records",
    "invogue records",
    "thriller records",
    "hopeless records",
    "sound of vinyl",
    "udiscover music",
}

MASS_MARKET_SOURCES = {
    "amazon",
    "walmart",
    "target",
    "deep discount",
    "merchbar",
    "hot topic",
}

COMMON_PRESS_KEYWORDS = {
    "standard",
    "standard black",
    "black vinyl",
    "repress",
}

NEGATIVE_MASS_REISSUE_KEYWORDS = {
    "standard black vinyl",
    "black vinyl",
    "standard edition",
}

HOT_SIGNALS = {
    "preorder",
    "pre-order",
    "coming soon",
    "just announced",
    "sold out",
    "low stock",
    "almost gone",
    "restock",
    "rsd",
    "record store day",
}

PopsikeCache = Dict[str, Dict[str, Any]]


# -------------------------
# HELPERS
# -------------------------

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        num = float(value)
        if math.isfinite(num):
            return num
        return default
    except Exception:
        return default


def normalize_text(text: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(text or "").lower())).strip()


def normalize_source(source: Any) -> str:
    s = normalize_text(source)
    mapping = {
        "smartpunk": "smartpunk records",
        "sharptone": "sharptone records",
        "solid state vinyl": "solid state vinyl",
        "solid state": "solid state records",
        "rise all": "rise all",
        "rise records": "rise records",
        "sound of vinyl": "sound of vinyl",
        "udiscover": "udiscover music",
        "newbury": "newbury comics",
        "rmfn": "rmfn all",
        "rock metal fan nation": "rock metal fan nation",
        "pure noise": "pure noise records",
        "hopeless": "hopeless records",
        "pirates press": "pirates press records",
        "spinefarm": "spinefarm records",
        "invogue": "invogue records",
        "thriller": "thriller records",
        "unfd": "unfd",
        "amazon": "amazon",
        "walmart": "walmart",
        "target": "target",
        "deep discount": "deep discount",
        "merchbar": "merchbar",
        "hot topic": "hot topic",
        "revolver": "revolver",
        "equal vision": "equal vision",
        "rollin": "rollin records",
        "brooklyn vegan": "brooklyn vegan",
        "fearless": "fearless records",
        "sumerian": "sumerian records",
    }
    for k, v in mapping.items():
        if k in s:
            return v
    return s


def combined_text(record: Dict[str, Any]) -> str:
    fields = [
        record.get("artist", ""),
        record.get("title", ""),
        record.get("raw_title", ""),
        record.get("version", ""),
        record.get("source", ""),
        record.get("page_text_snippet", ""),
        record.get("description", ""),
        record.get("genre", ""),
        record.get("subgenre", ""),
        record.get("format", ""),
    ]
    return normalize_text(" ".join(map(str, fields)))


def count_matching_keywords(text: str, keywords: set[str]) -> int:
    count = 0
    for kw in keywords:
        if normalize_text(kw) in text:
            count += 1
    return count


def contains_any(text: str, keywords: set[str]) -> bool:
    return any(normalize_text(kw) in text for kw in keywords)


def artist_name(record: Dict[str, Any]) -> str:
    return normalize_text(record.get("artist", ""))


def price_of(record: Dict[str, Any]) -> float:
    return safe_float(record.get("price", 0.0), 0.0)


def discogs_lowest(record: Dict[str, Any]) -> float:
    return safe_float(record.get("discogs_lowest", 0.0), 0.0)


def discogs_sell_price(record: Dict[str, Any]) -> float:
    return safe_float(record.get("discogs_sell_price", 0.0), 0.0)


def is_vinyl(record: Dict[str, Any]) -> bool:
    return normalize_text(record.get("format", "vinyl")) == "vinyl"


def normalized_record_key(record: Dict[str, Any]) -> str:
    artist = normalize_text(record.get("artist", ""))
    title = normalize_text(record.get("title", ""))
    version = normalize_text(record.get("version", ""))
    return f"{artist} :: {title} :: {version}".strip(" ::")


def popsike_search_query(record: Dict[str, Any]) -> str:
    """
    Strip noisy words before searching Popsike.
    """
    artist = str(record.get("artist", "")).strip()
    title = str(record.get("title", "")).strip()

    raw = f"{artist} {title}".lower()

    strip_words = [
        "vinyl", "lp", "l.p.", "preorder", "pre-order", "ships", "shipping",
        "limited", "exclusive", "variant", "colored", "colour", "edition",
        "record store day", "rsd", "deluxe", "anniversary", "import",
        "black vinyl", "standard", "repress", "numbered",
    ]

    for word in strip_words:
        raw = raw.replace(word, " ")

    raw = re.sub(r"\b\d{1,2}/\d{1,2}\b", " ", raw)  # strip simple ship dates like 4/18
    raw = re.sub(r"\b20\d{2}\b", " ", raw)          # strip years
    raw = re.sub(r"\s+", " ", raw).strip()

    return raw or f"{artist} {title}".strip()


def infer_cache_ttl_days(record: Dict[str, Any]) -> int:
    text = combined_text(record)
    artist = artist_name(record)
    if artist in JOEY_CORE_ARTISTS or contains_any(text, {"preorder", "rsd", "sold out", "just announced"}):
        return 3
    if contains_any(text, RARITY_KEYWORDS):
        return 14
    return 30


# -------------------------
# BASE SCORING
# -------------------------

def score_price_zone(price: float) -> int:
    if price < 15:
        return 0
    if price < 25:
        return 4
    if price < 40:
        return 8
    if price < 75:
        return 12
    return 15


def score_taste_match(record: Dict[str, Any], text: str) -> int:
    artist = artist_name(record)
    if artist in JOEY_CORE_ARTISTS:
        return 20
    if contains_any(text, JOEY_ADJACENT_KEYWORDS):
        return 10
    return 0


def score_rarity(text: str) -> Tuple[int, int]:
    hits = count_matching_keywords(text, RARITY_KEYWORDS)
    return min(hits * 4, 20), hits


def score_source(source: str) -> int:
    if source in COLLECTOR_SOURCES:
        return 8
    if source in MASS_MARKET_SOURCES:
        return 1
    return 0


def score_discogs(record: Dict[str, Any], current_price: float) -> int:
    lowest = discogs_lowest(record)
    sell = discogs_sell_price(record)
    comp = max(lowest, sell)

    if comp <= 0:
        return 8

    if current_price <= 0:
        return 0

    ratio = comp / current_price

    if ratio >= 1.20:
        return 18
    if ratio >= 1.10:
        return 10
    if ratio >= 0.95:
        return 3
    return -10


def score_hype(text: str) -> int:
    score = 0

    if contains_any(text, {"preorder", "pre-order"}):
        score += 8
    if contains_any(text, {"low stock", "almost gone"}):
        score += 6
    if contains_any(text, {"just announced", "new release", "coming soon"}):
        score += 5
    if contains_any(text, {"sold out", "rsd", "record store day"}):
        score += 10

    return score


def score_negative(record: Dict[str, Any], text: str, source: str, rarity_count: int, current_price: float) -> int:
    penalty = 0

    if contains_any(text, COMMON_PRESS_KEYWORDS):
        penalty -= 8

    if source in MASS_MARKET_SOURCES and rarity_count == 0:
        penalty -= 10

    if contains_any(text, NEGATIVE_MASS_REISSUE_KEYWORDS):
        penalty -= 10

    no_margin = (
        current_price > 0 and
        discogs_lowest(record) > 0 and
        discogs_lowest(record) <= current_price
    )
    if no_margin and rarity_count == 0:
        penalty -= 12

    if rarity_count == 0 and not contains_any(text, HOT_SIGNALS) and source in MASS_MARKET_SOURCES:
        penalty -= 15

    return penalty


def lane_from_score(score: int) -> str:
    if score >= 75:
        return "BUY NOW"
    if score >= 60:
        return "BUY LIGHT"
    if score >= 40:
        return "WATCH"
    return "PASS"


def build_base_score(record: Dict[str, Any]) -> Dict[str, Any]:
    text = combined_text(record)
    source = normalize_source(record.get("source", ""))
    current_price = price_of(record)

    breakdown: Dict[str, int] = {}

    breakdown["price_zone"] = score_price_zone(current_price)
    breakdown["taste_match"] = score_taste_match(record, text)

    rarity_score, rarity_count = score_rarity(text)
    breakdown["rarity"] = rarity_score

    breakdown["source_heat"] = score_source(source)
    breakdown["discogs_signal"] = score_discogs(record, current_price)
    breakdown["hype"] = score_hype(text)
    breakdown["negative"] = score_negative(record, text, source, rarity_count, current_price)

    total = sum(breakdown.values())

    return {
        "base_score": total,
        "lane": lane_from_score(total),
        "rarity_keyword_count": rarity_count,
        "source_normalized": source,
        "search_blob": text,
        "breakdown": breakdown,
    }


# -------------------------
# POPSIKE GATEKEEPER
# -------------------------

def should_check_popsike(record: Dict[str, Any], base_result: Dict[str, Any], cache: Optional[PopsikeCache] = None) -> Tuple[bool, str]:
    """
    Decide whether Popsike should be checked for this record.
    Returns (should_check, reason)
    """
    if not is_vinyl(record):
        return False, "not_vinyl"

    current_price = price_of(record)
    artist = artist_name(record)
    text = base_result["search_blob"]
    source = base_result["source_normalized"]
    base_score = int(base_result["base_score"])
    rarity_count = int(base_result["rarity_keyword_count"])

    # Hard skip rules
    if current_price < 20:
        return False, "price_under_20"

    if source in MASS_MARKET_SOURCES and rarity_count == 0 and base_score < 65:
        return False, "mass_market_no_heat"

    if contains_any(text, COMMON_PRESS_KEYWORDS) and rarity_count == 0 and base_score < 65:
        return False, "common_repress"

    # Cache check
    if cache is not None:
        key = normalized_record_key(record)
        cached = cache.get(key)
        if cached:
            checked_at = cached.get("popsike_checked_at")
            if checked_at:
                try:
                    checked_dt = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
                    ttl_days = infer_cache_ttl_days(record)
                    if utc_now() - checked_dt < timedelta(days=ttl_days):
                        return False, "fresh_cache"
                except Exception:
                    pass

    # Trigger A: high base score
    if base_score >= 65:
        return True, "base_score_65_plus"

    # Trigger B: Joey sniper rule
    if artist in JOEY_CORE_ARTISTS and current_price >= 25:
        return True, "joey_core_artist"

    # Trigger C: 2+ rarity keywords
    if rarity_count >= 2 and current_price >= 25:
        return True, "rarity_keywords"

    # Trigger D: weak or missing Discogs
    if discogs_lowest(record) <= 0 and discogs_sell_price(record) <= 0 and base_score >= 50:
        return True, "no_discogs"

    # Trigger E: treasure lane rule
    if source in COLLECTOR_SOURCES and contains_any(text, {"liquid filled", "zoetrope", "rsd", "first press", "sold out", "numbered"}):
        return True, "collector_treasure_rule"

    # Trigger F: margin suspicion rule
    if source in COLLECTOR_SOURCES and current_price >= 20 and rarity_count >= 1:
        return True, "margin_suspicion"

    return False, "no_trigger"


# -------------------------
# POPSIKE ENRICHMENT
# -------------------------

def apply_popsike_enrichment(record: Dict[str, Any], base_result: Dict[str, Any], popsike_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Apply Popsike score boost to the base result.
    Expected popsike_result shape:
    {
        "found": True,
        "avg_price": 185.0,
        "last_price": 225.0,
        "result_count": 296,
        "last_sale_date": "2026-04-18",
        "search_query": "sleep token caramel"
    }
    """
    enriched = dict(base_result)
    enriched["popsike_checked"] = popsike_result is not None
    enriched["popsike_found"] = False
    enriched["popsike_boost"] = 0
    enriched["popsike_reason"] = "not_checked"
    enriched["final_score"] = int(base_result["base_score"])
    enriched["final_lane"] = lane_from_score(enriched["final_score"])

    if not popsike_result or not popsike_result.get("found"):
        if popsike_result is not None:
            enriched["popsike_reason"] = "no_match"
        return enriched

    current_price = price_of(record)
    avg_price = safe_float(popsike_result.get("avg_price", 0.0))
    last_price = safe_float(popsike_result.get("last_price", 0.0))
    result_count = int(safe_float(popsike_result.get("result_count", 0)))
    boost = 0

    # Upside vs current price
    if current_price > 0 and avg_price > 0:
        ratio = avg_price / current_price
        if ratio >= 2.0:
            boost += 25
        elif ratio >= 1.5:
            boost += 18
        elif ratio >= 1.2:
            boost += 10
        elif ratio >= 0.95:
            boost += 2
        else:
            boost -= 15

    # Count confidence
    if result_count >= 100:
        boost += 8
    elif result_count >= 25:
        boost += 5
    elif result_count >= 5:
        boost += 2

    # Freshness bonus
    last_sale_date = popsike_result.get("last_sale_date")
    if last_sale_date:
        try:
            sale_dt = datetime.fromisoformat(last_sale_date)
            age_days = (utc_now().date() - sale_dt.date()).days
            if age_days <= 30:
                boost += 6
            elif age_days <= 90:
                boost += 3
        except Exception:
            pass

    final_score = int(base_result["base_score"] + boost)

    final_lane = "TREASURE" if final_score >= 90 else lane_from_score(final_score)

    enriched["popsike_found"] = True
    enriched["popsike_reason"] = "matched"
    enriched["popsike_boost"] = boost
    enriched["popsike_avg_price"] = avg_price
    enriched["popsike_last_price"] = last_price
    enriched["popsike_result_count"] = result_count
    enriched["popsike_last_sale_date"] = last_sale_date
    enriched["popsike_search_query"] = popsike_result.get("search_query", "")
    enriched["final_score"] = final_score
    enriched["final_lane"] = final_lane

    return enriched


# -------------------------
# CACHE
# -------------------------

def load_popsike_cache(path: str) -> PopsikeCache:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except FileNotFoundError:
        pass
    except Exception as exc:
        print(f"[warn] Could not load Popsike cache: {exc}")
    return {}


def save_popsike_cache(path: str, cache: PopsikeCache) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False, sort_keys=True)


def update_cache_with_popsike_result(cache: PopsikeCache, record: Dict[str, Any], popsike_result: Dict[str, Any]) -> None:
    key = normalized_record_key(record)
    cache[key] = {
        "popsike_found": bool(popsike_result.get("found")),
        "popsike_last_price": safe_float(popsike_result.get("last_price", 0.0)),
        "popsike_avg_price": safe_float(popsike_result.get("avg_price", 0.0)),
        "popsike_result_count": int(safe_float(popsike_result.get("result_count", 0))),
        "popsike_last_sale_date": popsike_result.get("last_sale_date"),
        "popsike_search_query": popsike_result.get("search_query") or popsike_search_query(record),
        "popsike_checked_at": utc_now().isoformat().replace("+00:00", "Z"),
    }


# -------------------------
# PRIORITIZATION
# -------------------------

def sort_popsike_candidates(records_with_scores: List[Tuple[Dict[str, Any], Dict[str, Any], str]]) -> List[Tuple[Dict[str, Any], Dict[str, Any], str]]:
    """
    Sort candidate records for Popsike lookup.
    Each item = (record, base_result, reason)
    """
    def sort_key(item: Tuple[Dict[str, Any], Dict[str, Any], str]) -> Tuple:
        record, base_result, reason = item
        artist = artist_name(record)
        price = price_of(record)
        rarity_count = int(base_result["rarity_keyword_count"])
        joey_boost = 1 if artist in JOEY_CORE_ARTISTS else 0
        return (
            base_result["base_score"],
            joey_boost,
            rarity_count,
            price,
            1 if reason in {"joey_core_artist", "collector_treasure_rule"} else 0,
        )

    return sorted(records_with_scores, key=sort_key, reverse=True)


# -------------------------
# MAIN PIPELINE
# -------------------------

def evaluate_records_for_popsike(
    all_records: List[Dict[str, Any]],
    cache: Optional[PopsikeCache] = None,
    daily_lookup_budget: int = 250,
) -> Dict[str, Any]:
    """
    Evaluate all records.
    Returns:
    {
        "scored_records": [...],
        "popsike_candidates": [...],
        "skipped_records": [...]
    }
    """
    scored_records: List[Dict[str, Any]] = []
    candidates: List[Tuple[Dict[str, Any], Dict[str, Any], str]] = []
    skipped_records: List[Dict[str, Any]] = []

    for record in all_records:
        if not is_vinyl(record):
            continue

        base_result = build_base_score(record)
        should_check, reason = should_check_popsike(record, base_result, cache=cache)

        merged = {
            **record,
            **base_result,
            "popsike_should_check": should_check,
            "popsike_gate_reason": reason,
            "popsike_search_query": popsike_search_query(record),
        }

        scored_records.append(merged)

        if should_check:
            candidates.append((record, base_result, reason))
        else:
            skipped_records.append(merged)

    sorted_candidates = sort_popsike_candidates(candidates)[:daily_lookup_budget]

    popsike_candidates = []
    for record, base_result, reason in sorted_candidates:
        popsike_candidates.append({
            **record,
            **base_result,
            "popsike_should_check": True,
            "popsike_gate_reason": reason,
            "popsike_search_query": popsike_search_query(record),
        })

    return {
        "scored_records": scored_records,
        "popsike_candidates": popsike_candidates,
        "skipped_records": skipped_records,
    }


# -------------------------
# EXAMPLE STUB LOOKUP
# -------------------------

def fake_popsike_lookup(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Replace this with your real Popsike lookup later.
    This is a stub so the brain can run end-to-end now.
    """
    query = popsike_search_query(record)

    # Example fake match for hot Sleep Token records
    title_blob = normalize_text(f"{record.get('artist', '')} {record.get('title', '')}")
    if "sleep token" in title_blob and "caramel" in title_blob:
        return {
            "found": True,
            "avg_price": 185.0,
            "last_price": 225.0,
            "result_count": 296,
            "last_sale_date": "2026-04-18",
            "search_query": query,
        }

    return {
        "found": False,
        "search_query": query,
    }


def enrich_candidates_with_lookup(
    candidates: List[Dict[str, Any]],
    cache: Optional[PopsikeCache] = None,
) -> List[Dict[str, Any]]:
    enriched_results: List[Dict[str, Any]] = []

    for candidate in candidates:
        base_result = {
            "base_score": candidate["base_score"],
            "lane": candidate["lane"],
            "rarity_keyword_count": candidate["rarity_keyword_count"],
            "source_normalized": candidate["source_normalized"],
            "search_blob": candidate["search_blob"],
            "breakdown": candidate["breakdown"],
        }

        popsike_result = fake_popsike_lookup(candidate)
        enriched = apply_popsike_enrichment(candidate, base_result, popsike_result)
        merged = {**candidate, **enriched}
        enriched_results.append(merged)

        if cache is not None:
            update_cache_with_popsike_result(cache, candidate, popsike_result)

    return enriched_results


# -------------------------
# DEMO USAGE
# -------------------------

if __name__ == "__main__":
    sample_records = [
        {
            "artist": "Sleep Token",
            "title": "Caramel RSD 2026 Liquid Filled Vinyl LP SHIPS 4/18",
            "price": 49.99,
            "source": "Smartpunk Records",
            "format": "vinyl",
            "version": "exclusive",
            "discogs_lowest": 0,
            "discogs_sell_price": 0,
            "page_text_snippet": "limited liquid filled rsd exclusive sold out preorder",
        },
        {
            "artist": "Fleetwood Mac",
            "title": "Rumours Standard Black Vinyl",
            "price": 27.99,
            "source": "Walmart",
            "format": "vinyl",
            "version": "standard",
            "discogs_lowest": 24.99,
            "discogs_sell_price": 0,
            "page_text_snippet": "standard black vinyl repress",
        },
    ]

    cache_path = "popsike_cache.json"
    cache = load_popsike_cache(cache_path)

    result = evaluate_records_for_popsike(
        all_records=sample_records,
        cache=cache,
        daily_lookup_budget=250,
    )

    print("\n=== POPSIKE CANDIDATES ===")
    for c in result["popsike_candidates"]:
        print(
            f"- {c['artist']} | {c['title'][:60]} | "
            f"base={c['base_score']} | lane={c['lane']} | "
            f"reason={c['popsike_gate_reason']} | query={c['popsike_search_query']}"
        )

    enriched = enrich_candidates_with_lookup(result["popsike_candidates"], cache=cache)

    print("\n=== ENRICHED RESULTS ===")
    for e in enriched:
        print(
            f"- {e['artist']} | final={e['final_score']} | final_lane={e['final_lane']} | "
            f"popsike_found={e['popsike_found']} | boost={e['popsike_boost']}"
        )

    save_popsike_cache(cache_path, cache)
