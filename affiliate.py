# -*- coding: utf-8 -*-

AMAZON_TAG = "korndog20-20"

def build_amazon_link(deal):
    artist = deal.get("artist", "").strip()
    title = deal.get("title", "").strip()
    source_link = deal.get("link", "").strip()

    query = f"{artist} {title} vinyl".strip().replace(" ", "+")

    # If it's already an Amazon link, attach your tag
    if "amazon.com" in source_link:
        if "tag=" in source_link:
            return source_link
        joiner = "&" if "?" in source_link else "?"
        return f"{source_link}{joiner}tag={AMAZON_TAG}"

    # Otherwise build an Amazon search link
    return f"https://www.amazon.com/s?k={query}&tag={AMAZON_TAG}"
