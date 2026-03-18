# -*- coding: utf-8 -*-

from affiliate import build_amazon_link

AMAZON_THRESHOLD = 2.00  # how close Amazon must be to win
WALMART_THRESHOLD = 2.00

def is_amazon(link):
    return "amazon.com" in link.lower()

def is_walmart(link):
    return "walmart.com" in link.lower()

def clean_key(deal):
    artist = (deal.get("artist", "") or "").lower().strip()
    title = (deal.get("title", "") or "").lower().strip()

    # remove junk like (2LP), [Deluxe], etc
    import re
    title = re.sub(r"\([^)]*\)", "", title)
    title = re.sub(r"\[[^\]]*\]", "", title)

    return f"{artist}|{title.strip()}"

def group_deals(deals):
    grouped = {}

    for deal in deals:
        key = clean_key(deal)
        grouped.setdefault(key, []).append(deal)

    return grouped

def choose_best(deals):
    # filter valid prices
    valid = [d for d in deals if d.get("price", 0) > 0]

    if not valid:
        return deals[0]

    # sort cheapest first
    valid.sort(key=lambda x: x["price"])
    cheapest = valid[0]

    amazon = next((d for d in valid if is_amazon(d.get("link", ""))), None)
    walmart = next((d for d in valid if is_walmart(d.get("link", ""))), None)

    # AMAZON WINS if close enough
    if amazon:
        diff = amazon["price"] - cheapest["price"]
        if diff <= AMAZON_THRESHOLD:
            return amazon

    # WALMART WINS if close enough
    if walmart:
        diff = walmart["price"] - cheapest["price"]
        if diff <= WALMART_THRESHOLD:
            return walmart

    # otherwise cheapest wins (KornDog Find territory)
    return cheapest

def apply_best_links(deals):
    grouped = group_deals(deals)
    final = []

    for key, group in grouped.items():
        best = choose_best(group)

        # determine label
        label = "STANDARD"
        if not is_amazon(best.get("link", "")) and not is_walmart(best.get("link", "")):
            label = "KORNDOG FIND"

        best["best_label"] = label
        best["buy_link"] = best.get("link", "")

        # ALWAYS generate Amazon backup link
        best["amazon_link"] = build_amazon_link(best)

        final.append(best)

    return final
