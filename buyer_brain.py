# -*- coding: utf-8 -*-
"""
buyer_brain.py

KornDog Buyer Brain V1
Post-processing intelligence layer for Deal Hunter.

This file does NOT replace your scrapers.
It enriches already-pulled deal records with store-buyer logic:
- inventory lane
- customer lanes
- demand / turn speed
- suggested sale price
- expected margin
- buy score
- decision
- recommended quantity
- why_buy summary
"""

import re
from typing import Any, Dict, List


MAINSTREAM_ARTISTS = [
    "fleetwood mac", "beatles", "taylor swift", "nirvana", "metallica",
    "eagles", "pink floyd", "michael jackson", "prince", "lana del rey",
    "kendrick lamar", "tyler the creator", "mac miller", "billie eilish",
    "journey", "queen", "acdc", "guns n roses", "red hot chili peppers",
    "led zeppelin", "stevie nicks", "adele", "abba", "bon jovi",
    "the cure", "depeche mode", "foo fighters", "linkin park",
    "the weeknd", "olivia rodrigo", "sabrina carpenter", "billy joel",
    "elton john", "creedence clearwater revival", "tom petty", "boston",
    "foreigner", "reo speedwagon", "eurythmics", "phil collins",
]

KORNDOG_IDENTITY_ARTISTS = [
    "sleep token", "erra", "polaris", "currents", "wage war", "dayseeker",
    "memphis may fire", "the ghost inside", "boundaries", "thornhill",
    "eidola", "dance gavin dance", "korn", "slipknot", "limp bizkit",
    "system of a down", "pantera", "deftones", "tool", "breaking benjamin",
    "three days grace", "seether", "atreyu", "killswitch engage",
    "a day to remember", "three 6 mafia", "project pat", "ugk",
    "8ball", "mjg", "juicy j", "pimp c", "bun b", "trick daddy",
    "ozzy osbourne", "judas priest", "journey", "monster magnet",
    "nothing more", "incubus", "sevendust", "black label society",
]

FAST_TURN_ARTISTS = [
    "fleetwood mac", "beatles", "nirvana", "metallica", "taylor swift",
    "mac miller", "tyler the creator", "kendrick lamar", "lana del rey",
    "queen", "eagles", "pink floyd", "journey", "linkin park",
    "sleep token", "korn", "deftones", "ozzy osbourne", "sevendust",
]

TREND_HINTS = [
    "anniversary", "deluxe", "limited", "exclusive", "colored", "splatter",
    "zoetrope", "picture disc", "new release", "preorder", "pre-order",
    "rsd", "record store day", "indie exclusive", "webstore exclusive",
    "spotify fans first", "urban outfitters exclusive", "target exclusive",
    "walmart exclusive", "amazon exclusive"
]

COLLECTOR_HINTS = [
    "limited", "exclusive", "colored", "splatter", "zoetrope", "picture disc",
    "numbered", "import", "deluxe", "anniversary", "gatefold", "opaque",
    "clear vinyl", "smoke", "translucent", "red vinyl", "blue vinyl",
    "green vinyl", "purple vinyl", "marble", "swirl", "tri-color",
    "a-side b-side", "etched", "foil", "alternate cover"
]

GIFTABLE_HINTS = [
    "greatest hits", "best of", "soundtrack", "holiday", "classic",
    "anniversary", "deluxe", "essential", "icon", "legacy"
]

SOURCE_CONFIDENCE = {
    "shopify_store": 9,
    "merchnow_store": 8,
    "unfd_store": 8,
    "deepdiscount_store": 7,
    "merchbar_store": 6,
    "hottopic_store": 6,
    "millions_store": 6,
    "walmart_catalog_source": 5,
    "amazon_catalog_source": 5,
    "target_catalog_source": 5,
    "reddit_scraper": 6,
    "community": 6,
}

MAINSTREAM_GENRE_HINTS = [
    "classic rock", "pop", "greatest hits", "best of", "soundtrack",
    "hip hop", "rap", "alternative", "grunge", "arena rock", "country"
]

IDENTITY_GENRE_HINTS = [
    "metalcore", "post-hardcore", "nu metal", "southern rap",
    "post grunge", "alt metal", "hard rock", "emotional heavy"
]

TREASURE_HINTS = [
    "soundtrack", "import", "jazz", "ambient", "experimental",
    "library music", "obscure", "rare", "colored", "limited", "live"
]


def norm(value: Any) -> str:
    return str(value or "").strip().lower()


def clean_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def safe_price(value: Any) -> float:
    try:
        return round(float(value), 2)
    except Exception:
        return 0.0


def contains_any(text: str, values: List[str]) -> bool:
    text_n = norm(text)
    return any(v in text_n for v in values if v)


def count_hits(text: str, values: List[str]) -> int:
    text_n = norm(text)
    return sum(1 for v in values if v and v in text_n)


def joined_text(item: Dict[str, Any]) -> str:
    keywords = item.get("keywords", [])
    if not isinstance(keywords, list):
        keywords = []

    parts = [
        str(item.get("artist", "")),
        str(item.get("title", "")),
        str(item.get("raw_title", "")),
        str(item.get("source", "")),
        str(item.get("source_type", "")),
        str(item.get("version", "")),
        str(item.get("availability_text", "")),
        str(item.get("page_text_snippet", "")),
        " ".join(str(k) for k in keywords),
    ]
    return clean_spaces(" ".join(parts)).lower()


def source_confidence(item: Dict[str, Any]) -> int:
    return SOURCE_CONFIDENCE.get(norm(item.get("source_type", "")), 5)


def detect_exclusive_heat(item: Dict[str, Any]) -> int:
    text = joined_text(item)
    heat = 0

    if contains_any(text, ["exclusive"]):
        heat += 4
    if contains_any(text, ["limited"]):
        heat += 3
    if contains_any(text, ["splatter", "zoetrope", "picture disc", "marble", "swirl"]):
        heat += 2
    if contains_any(text, ["import", "numbered", "etched", "gatefold"]):
        heat += 1

    return heat


def classify_inventory_lane(item: Dict[str, Any]) -> str:
    text = joined_text(item)
    artist = norm(item.get("artist", ""))

    if contains_any(artist, KORNDOG_IDENTITY_ARTISTS) or contains_any(text, IDENTITY_GENRE_HINTS):
        return "Korndog Identity"

    if contains_any(artist, MAINSTREAM_ARTISTS) or contains_any(text, MAINSTREAM_GENRE_HINTS):
        return "Bread & Butter"

    if contains_any(text, TREND_HINTS):
        return "Trend / Hype"

    if contains_any(text, TREASURE_HINTS) or detect_exclusive_heat(item) >= 5:
        return "Treasure Hunt"

    return "Bread & Butter"


def classify_customer_lanes(item: Dict[str, Any]) -> List[str]:
    text = joined_text(item)
    artist = norm(item.get("artist", ""))
    lanes: List[str] = []

    if contains_any(artist, KORNDOG_IDENTITY_ARTISTS) or contains_any(text, IDENTITY_GENRE_HINTS):
        lanes.extend(["Heavy Crowd", "Collector"])

    if contains_any(artist, MAINSTREAM_ARTISTS):
        lanes.extend(["Casual Nostalgia Buyer", "Gift Buyer"])

    if any(x in text for x in ["kendrick", "tyler", "mac miller", "three 6 mafia", "project pat", "ugk", "8ball", "mjg"]):
        lanes.append("Rap Buyer")

    if any(x in text for x in ["lana del rey", "taylor swift", "billie eilish", "fleetwood mac", "stevie nicks", "olivia rodrigo", "sabrina carpenter"]):
        lanes.append("Pop / Indie Buyer")

    if any(x in text for x in ["limited", "exclusive", "splatter", "zoetrope", "picture disc", "import", "numbered"]):
        lanes.append("Collector")

    if any(x in text for x in GIFTABLE_HINTS):
        lanes.append("Gift Buyer")

    if not lanes:
        lanes.append("General Vinyl Buyer")

    return sorted(set(lanes))


def demand_level(item: Dict[str, Any]) -> str:
    text = joined_text(item)
    artist = norm(item.get("artist", ""))

    score = 0
    if contains_any(artist, MAINSTREAM_ARTISTS):
        score += 4
    if contains_any(artist, FAST_TURN_ARTISTS):
        score += 3
    if contains_any(text, TREND_HINTS):
        score += 2
    if contains_any(artist, KORNDOG_IDENTITY_ARTISTS):
        score += 2
    if "greatest hits" in text or "best of" in text:
        score += 1

    if score >= 7:
        return "High"
    if score >= 3:
        return "Medium"
    return "Low"


def turn_speed(item: Dict[str, Any]) -> str:
    text = joined_text(item)
    artist = norm(item.get("artist", ""))

    score = 0
    if contains_any(artist, FAST_TURN_ARTISTS):
        score += 4
    if contains_any(artist, MAINSTREAM_ARTISTS):
        score += 3
    if contains_any(text, ["preorder", "pre-order", "new release", "anniversary"]):
        score += 2
    if contains_any(text, ["limited", "exclusive"]):
        score += 1
    if contains_any(text, ["greatest hits", "best of", "soundtrack"]):
        score += 1

    if score >= 6:
        return "Fast"
    if score >= 3:
        return "Medium"
    return "Slow"


def estimate_sale_price(item: Dict[str, Any], lane: str) -> float:
    cost = safe_price(item.get("price", 0))
    text = joined_text(item)

    if cost <= 0:
        return 0.0

    markup = 1.35

    if lane == "Bread & Butter":
        markup = 1.35
    elif lane == "Korndog Identity":
        markup = 1.45
    elif lane == "Trend / Hype":
        markup = 1.50
    elif lane == "Treasure Hunt":
        markup = 1.55

    if contains_any(text, ["limited", "exclusive"]):
        markup += 0.10
    if contains_any(text, ["splatter", "zoetrope", "picture disc", "import", "numbered"]):
        markup += 0.08
    if contains_any(text, ["preorder", "pre-order"]):
        markup += 0.05
    if contains_any(text, ["greatest hits", "best of"]):
        markup += 0.03

    sale_price = round(cost * markup, 2)

    if sale_price >= 10:
        sale_price = round(int(sale_price) + 0.99, 2)

    return sale_price


def recommend_qty(item: Dict[str, Any], lane: str, decision: str) -> int:
    if decision == "PASS":
        return 0

    demand = demand_level(item)
    speed = turn_speed(item)

    if lane == "Bread & Butter":
        if demand == "High" and speed == "Fast":
            return 3
        if demand in {"High", "Medium"}:
            return 2
        return 1

    if lane == "Korndog Identity":
        if demand == "High":
            return 2
        return 1

    if lane == "Trend / Hype":
        if demand == "High":
            return 2
        return 1

    if lane == "Treasure Hunt":
        return 1

    return 1


def compute_buy_score(item: Dict[str, Any], lane: str, sale_price: float) -> int:
    cost = safe_price(item.get("price", 0))
    text = joined_text(item)
    conf = source_confidence(item)

    score = 0

    score += conf * 4

    if cost > 0 and sale_price > 0:
        margin = sale_price - cost
        margin_pct = (margin / cost) * 100 if cost else 0

        if margin >= 15:
            score += 25
        elif margin >= 10:
            score += 18
        elif margin >= 6:
            score += 12
        elif margin >= 3:
            score += 6

        if margin_pct >= 60:
            score += 15
        elif margin_pct >= 40:
            score += 10
        elif margin_pct >= 25:
            score += 5

    if lane == "Bread & Butter":
        score += 14
    elif lane == "Korndog Identity":
        score += 12
    elif lane == "Trend / Hype":
        score += 11
    elif lane == "Treasure Hunt":
        score += 8

    if contains_any(text, ["limited", "exclusive"]):
        score += 8
    if contains_any(text, ["splatter", "zoetrope", "picture disc", "import", "numbered"]):
        score += 5
    if contains_any(text, ["preorder", "pre-order", "new release", "anniversary"]):
        score += 5
    if contains_any(text, ["greatest hits", "best of", "soundtrack"]):
        score += 3

    demand = demand_level(item)
    speed = turn_speed(item)

    if demand == "High":
        score += 12
    elif demand == "Medium":
        score += 6

    if speed == "Fast":
        score += 10
    elif speed == "Medium":
        score += 5

    return min(score, 100)


def decision_from_score(score: int, margin_dollars: float) -> str:
    if score >= 80 and margin_dollars >= 8:
        return "BUY NOW"
    if score >= 65 and margin_dollars >= 5:
        return "BUY LIGHT"
    if score >= 45:
        return "WATCH"
    return "PASS"


def store_fit(item: Dict[str, Any], lane: str) -> str:
    if lane == "Bread & Butter":
        return "High Traffic"
    if lane == "Korndog Identity":
        return "Brand Builder"
    if lane == "Trend / Hype":
        return "Attention Grabber"
    if lane == "Treasure Hunt":
        return "Crate Digger Candy"
    return "General"


def why_buy(item: Dict[str, Any], lane: str, margin_dollars: float, decision: str) -> str:
    text = joined_text(item)
    parts = [lane]

    if margin_dollars >= 10:
        parts.append("strong dollar margin")
    elif margin_dollars >= 5:
        parts.append("solid margin")
    elif margin_dollars > 0:
        parts.append("light margin")

    speed = turn_speed(item)
    if speed == "Fast":
        parts.append("fast mover")
    elif speed == "Medium":
        parts.append("steady mover")

    if contains_any(text, ["limited", "exclusive"]):
        parts.append("collector appeal")
    if contains_any(text, ["preorder", "pre-order", "new release"]):
        parts.append("fresh release energy")
    if contains_any(text, ["greatest hits", "best of", "soundtrack"]):
        parts.append("easy shelf appeal")

    parts.append(decision.lower())
    return ", ".join(parts)


def shelf_placement(item: Dict[str, Any], lane: str, decision: str) -> str:
    if decision == "PASS":
        return "Do Not Stock"

    if lane == "Bread & Butter":
        return "Main Floor"
    if lane == "Korndog Identity":
        return "Feature Wall"
    if lane == "Trend / Hype":
        return "Front Table"
    if lane == "Treasure Hunt":
        return "Collector Bin"

    return "Main Floor"


def enrich_deal(item: Dict[str, Any]) -> Dict[str, Any]:
    deal = dict(item)

    lane = classify_inventory_lane(deal)
    customers = classify_customer_lanes(deal)
    sale_price = estimate_sale_price(deal, lane)
    cost = safe_price(deal.get("price", 0))
    margin_dollars = round(sale_price - cost, 2) if cost > 0 and sale_price > 0 else 0.0
    margin_percent = round((margin_dollars / cost) * 100, 2) if cost > 0 else 0.0
    score = compute_buy_score(deal, lane, sale_price)
    decision = decision_from_score(score, margin_dollars)
    qty = recommend_qty(deal, lane, decision)

    deal["inventory_lane"] = lane
    deal["customer_lanes"] = customers
    deal["turn_speed"] = turn_speed(deal)
    deal["demand_level"] = demand_level(deal)
    deal["source_confidence"] = source_confidence(deal)
    deal["suggested_sale_price"] = sale_price
    deal["expected_margin_dollars"] = margin_dollars
    deal["expected_margin_percent"] = margin_percent
    deal["buy_score"] = score
    deal["decision"] = decision
    deal["recommend_qty"] = qty
    deal["store_fit"] = store_fit(deal, lane)
    deal["why_buy"] = why_buy(deal, lane, margin_dollars, decision)
    deal["shelf_placement"] = shelf_placement(deal, lane, decision)

    return deal


def apply_buyer_brain(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for item in data:
        try:
            enriched.append(enrich_deal(item))
        except Exception:
            enriched.append(item)
    return enriched
