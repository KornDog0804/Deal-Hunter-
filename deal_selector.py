# -*- coding: utf-8 -*-
import re
from affiliate import build_amazon_link

AMAZON_THRESHOLD = 2.00
WALMART_THRESHOLD = 2.00

def is_amazon(link):
    return "amazon.com" in (link or "").lower()

def is_walmart(link):
    return "walmart.com" in (link or "").lower()

def normalize_title_for_grouping(title):
    title = (title or "").lower().strip()
    title = re.sub(r"\([^)]*\)", "", title)
    title = re.sub(r"\[[^\]]*\]", "", title)
    title = re.sub(r"\b(2lp|1lp|picture disc|exclusive|limited|anniversary|colored|zoetrope|standard)\b", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title

def normalize_artist_for_grouping(artist):
    artist = (artist or "").lower().strip()
    artist = re.sub(r"\s+", " ", artist).strip()
    return artist

def grouping_key(deal):
    artist = normalize_artist_for_grouping(deal.get("artist", ""))
    title = normalize_title_for_grouping(deal.get("title", ""))
    return f"{artist}|{title}"

def group_deals(deals):
    grouped = {}
    for deal in deals:
        key = grouping_key(deal)
        grouped.setdefault(key, []).append(deal)
    return grouped

def choose_best_deal(group):
    valid = [d for d in group if isinstance(d.get("price"), (int, float)) and d.get("price", 0) > 0]

    if not valid:
        chosen = group[0].copy()
        chosen["best_price"] = 0
        chosen["best_source"] = chosen.get("source", "Unknown")
        chosen["buy_link"] = chosen.get("link", "")
        chosen["best_label"] = "KORNDOG FIND"
        chosen["amazon_link"] = build_amazon_link(chosen)
        chosen["all_sources"] = [
            {
                "source": d.get("source", "Unknown"),
                "price": d.get("price", 0),
                "link": d.get("link", ""),
                "version": d.get("version", "standard")
            }
            for d in group
        ]
        return chosen

    valid.sort(key=lambda x: x["price"])
    cheapest = valid[0]

    amazon_candidate = next((d for d in valid if is_amazon(d.get("link", ""))), None)
    walmart_candidate = next((d for d in valid if is_walmart(d.get("link", ""))), None)

    chosen = cheapest

    if amazon_candidate:
        if amazon_candidate["price"] - cheapest["price"] <= AMAZON_THRESHOLD:
            chosen = amazon_candidate
    elif walmart_candidate:
        if walmart_candidate["price"] - cheapest["price"] <= WALMART_THRESHOLD:
            chosen = walmart_candidate

    result = chosen.copy()
    result["best_price"] = chosen.get("price", 0)
    result["best_source"] = chosen.get("source", "Unknown")
    result["buy_link"] = chosen.get("link", "")
    result["amazon_link"] = build_amazon_link(chosen)

    if is_amazon(result["buy_link"]):
        result["best_label"] = "AMAZON PICK"
    elif is_walmart(result["buy_link"]):
        result["best_label"] = "WALMART PICK"
    else:
        result["best_label"] = "KORNDOG FIND"

    result["all_sources"] = [
        {
            "source": d.get("source", "Unknown"),
            "price": d.get("price", 0),
            "link": d.get("link", ""),
            "version": d.get("version", "standard")
        }
        for d in sorted(valid, key=lambda x: x.get("price", 999999))
    ]

    return result

def apply_best_links(deals):
    grouped = group_deals(deals)
    final = []

    for _, group in grouped.items():
        best = choose_best_deal(group)
        final.append(best)

    return final
