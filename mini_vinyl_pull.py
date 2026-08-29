#!/usr/bin/env python3

import json
import urllib.parse
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "mini_vinyl_deals.json"

AMAZON_TAG = "korndog20-20"

SYSTEMS = [
    {
        "system": "Tiny Vinyl",
        "query": "Tiny Vinyl records player",
        "kind": "records + player",
    },
    {
        "system": "MGA Miniverse Real Music",
        "query": "MGA Miniverse Real Music vinyl record player",
        "kind": "records + player + accessories",
    },
    {
        "system": "Mini Brands Really Works Vinyl",
        "query": "Mini Brands Really Works Vinyl",
        "kind": "records + player + playset",
    },
]


def amazon_url(query):
    return (
        "https://www.amazon.com/s?"
        f"k={urllib.parse.quote_plus(query)}"
        f"&tag={AMAZON_TAG}"
    )


def walmart_url(query):
    return (
        "https://www.walmart.com/search?"
        f"q={urllib.parse.quote_plus(query)}"
    )


def target_url(query):
    return (
        "https://www.target.com/s?"
        f"searchTerm={urllib.parse.quote_plus(query)}"
    )


STORES = [
    ("Amazon", amazon_url),
    ("Walmart", walmart_url),
    ("Target", target_url),
]


def main():
    deals = []

    for entry in SYSTEMS:
        for store, url_builder in STORES:
            link = url_builder(entry["query"])

            deals.append({
                "artist": entry["system"],
                "title": f'{entry["system"]} at {store}',
                "raw_title": f'{entry["system"]} at {store}',
                "source": store,
                "source_type": "mini_vinyl_catalog",
                "mini_system": entry["system"],
                "product_type": entry["kind"],
                "price": 0,
                "image": "",
                "link": link,
                "availability_text": "Browse all current results",
                "mini_vinyl": True,
            })

    OUT.write_text(
        json.dumps(deals, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"✅ MINI VINYL: {len(deals)} catalog feeds written")
    print(f"✅ {OUT.name}")

    for d in deals:
        print(
            f'{d["source"]:7} | '
            f'{d["mini_system"]}: '
            f'{d["link"]}'
        )


if __name__ == "__main__":
    main()
