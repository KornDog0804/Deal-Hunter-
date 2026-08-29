#!/usr/bin/env python3

import json
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent
OUT = BASE / "mini_vinyl_deals.json"

AMAZON_TAG = "korndog20-20"


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


def row(
    system,
    title,
    source,
    product_type,
    link,
    price=0,
    image="",
    availability="Browse current listing",
    source_type="mini_vinyl_product",
    compatibility="",
):
    return {
        "artist": system,
        "title": title,
        "raw_title": title,
        "source": source,
        "source_type": source_type,
        "mini_system": system,
        "product_type": product_type,
        "price": price,
        "image": image,
        "link": link,
        "availability_text": availability,
        "compatibility": compatibility,
        "mini_vinyl": True,
    }


def catalog_rows():
    systems = [
        (
            "Tiny Vinyl",
            "Tiny Vinyl records player",
            "records + player + accessories",
        ),
        (
            "MGA Miniverse Real Music",
            "MGA Miniverse Real Music vinyl record player",
            "records + player + record shop",
        ),
        (
            "Mini Brands Really Works Vinyl",
            "Mini Brands Really Works Vinyl",
            "records + player + playset",
        ),
    ]

    stores = [
        ("Amazon", amazon_url),
        ("Walmart", walmart_url),
        ("Target", target_url),
    ]

    rows = []

    for system, query, kind in systems:
        for source, builder in stores:
            rows.append(
                row(
                    system=system,
                    title=f"{system} • Browse All at {source}",
                    source=source,
                    product_type=kind,
                    link=builder(query),
                    price=0,
                    availability="Browse all current results",
                    source_type="mini_vinyl_catalog",
                )
            )

    return rows


def verified_products():
    return [

        # =====================================================
        # TINY VINYL
        # =====================================================

        row(
            system="Tiny Vinyl",
            title="BTS • SWIM / NORMAL • Tiny Vinyl 4-inch",
            source="Target",
            product_type="RECORD",
            link=(
                "https://www.target.com/p/"
                "bts-tiny-vinyl-edition-swim-normal-target-exclusive-"
                "vinyl-4-inch/-/A-95177700"
            ),
            price=14.99,
            availability="Target • verified listing",
            compatibility="Tiny Vinyl ecosystem",
        ),

        row(
            system="Tiny Vinyl",
            title="Tiny Vinyl Player • Black",
            source="Target",
            product_type="PLAYER",
            link=target_url("Tiny Vinyl Player Black"),
            price=49.99,
            availability="Target • verified listing",
            compatibility="Tiny Vinyl ecosystem",
        ),

        row(
            system="Tiny Vinyl",
            title="Tiny Vinyl Crate",
            source="Target",
            product_type="ACCESSORY",
            link=target_url("Tiny Vinyl Crate"),
            price=19.99,
            availability="Target • verified listing",
            compatibility="Tiny Vinyl ecosystem",
        ),

        row(
            system="Tiny Vinyl",
            title="Tiny Vinyl 2x2 Frame",
            source="Target",
            product_type="ACCESSORY",
            link=target_url("Tiny Vinyl 2x2 Frame"),
            price=14.99,
            availability="Target • verified listing",
            compatibility="Tiny Vinyl ecosystem",
        ),

        # =====================================================
        # MGA MINIVERSE REAL MUSIC
        # =====================================================

        row(
            system="MGA Miniverse Real Music",
            title="Real Music Mystery Blind Pack • 4 Playable Mini Records",
            source="Target",
            product_type="RECORD PACK",
            link=(
                "https://www.target.com/p/"
                "mga-39-s-miniverse-real-music-blind-pack-mini-playable-"
                "vinyl-records-4-vinyl-records-per-pack-sleeve-and-keychain-"
                "britney-spears-elton-john-tlc/-/A-94992679"
            ),
            price=11.99,
            availability="Target • verified listing",
            compatibility="MGA Miniverse Real Music only",
        ),

        row(
            system="MGA Miniverse Real Music",
            title="Real Music Record Player • Beethoven Record Included",
            source="Target",
            product_type="PLAYER",
            link=(
                "https://www.target.com/p/"
                "mga-39-s-miniverse-real-music-record-player-mini-"
                "collectibles-mini-playable-record-player-featuring-"
                "beethoven/-/A-94992685"
            ),
            price=21.99,
            availability="Target • verified listing",
            compatibility="MGA Miniverse Real Music only",
        ),

        row(
            system="MGA Miniverse Real Music",
            title="Real Music Record Shop • Deluxe Display Set",
            source="Target",
            product_type="PLAYSET",
            link=(
                "https://www.target.com/p/"
                "mga-39-s-miniverse-record-shop/-/A-94992694"
            ),
            price=29.99,
            availability="Target • verified listing",
            compatibility="MGA Miniverse Real Music collection",
        ),

        row(
            system="MGA Miniverse Real Music",
            title="Real Music Mystery Blind Ball • 4 Mini Records",
            source="Walmart",
            product_type="RECORD PACK",
            link=(
                "https://www.walmart.com/ip/18863214092"
            ),
            price=11.97,
            availability="Walmart • verified listing",
            compatibility="MGA Miniverse Real Music only",
        ),

        row(
            system="MGA Miniverse Real Music",
            title="Real Music Record Player",
            source="Walmart",
            product_type="PLAYER",
            link=(
                "https://www.walmart.com/ip/18859357645"
            ),
            price=21.88,
            availability="Walmart • verified listing",
            compatibility="MGA Miniverse Real Music only",
        ),

        row(
            system="MGA Miniverse Real Music",
            title="Real Music Record Shop • Deluxe Display Set",
            source="Walmart",
            product_type="PLAYSET",
            link=(
                "https://www.walmart.com/ip/18863164471"
            ),
            price=29.99,
            availability="Walmart • verified listing",
            compatibility="MGA Miniverse Real Music collection",
        ),

        # =====================================================
        # ZURU MINI BRANDS REALLY WORKS VINYL
        # =====================================================

        row(
            system="Mini Brands Really Works Vinyl",
            title="Really Works Vinyl Capsule Series 1 • 4 Playable Records",
            source="Target",
            product_type="RECORD PACK",
            link=(
                "https://www.target.com/p/"
                "mini-brands-vinyls-capsule-s1-mini-figure/"
                "-/A-1012178109"
            ),
            price=9.99,
            availability="Target • verified listing",
            compatibility="ZURU Mini Brands Really Works Vinyl only",
        ),

        row(
            system="Mini Brands Really Works Vinyl",
            title="Really Works Vinyl Capsule Series 1 • 4 Playable Records",
            source="Walmart",
            product_type="RECORD PACK",
            link=(
                "https://www.walmart.com/ip/20509110863"
            ),
            price=9.97,
            availability="Walmart • verified listing",
            compatibility="ZURU Mini Brands Really Works Vinyl only",
        ),

        row(
            system="Mini Brands Really Works Vinyl",
            title="Really Works Vinyl Playset • Working Mini Record Player",
            source="Walmart",
            product_type="PLAYER / PLAYSET",
            link=(
                "https://www.walmart.com/ip/19117814163"
            ),
            price=19.97,
            availability="Walmart • verified listing",
            compatibility="ZURU Mini Brands Really Works Vinyl only",
        ),
    ]


def dedupe(rows):
    seen = set()
    out = []

    for item in rows:
        key = (
            item.get("source", "").lower(),
            item.get("link", "").lower(),
        )

        if key in seen:
            continue

        seen.add(key)
        out.append(item)

    return out


def main():
    deals = catalog_rows()
    deals.extend(verified_products())
    deals = dedupe(deals)

    payload = deals

    OUT.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    products = [
        x for x in deals
        if x["source_type"] == "mini_vinyl_product"
    ]

    catalogs = [
        x for x in deals
        if x["source_type"] == "mini_vinyl_catalog"
    ]

    print("=" * 60)
    print("🔬 KORNDOG MINI VINYL HUNTER")
    print("=" * 60)

    print("TOTAL:", len(deals))
    print("PRODUCTS:", len(products))
    print("CATALOG DOORS:", len(catalogs))

    print(
        "SYSTEMS:",
        len({
            x["mini_system"]
            for x in deals
        }),
    )

    print(
        "STORES:",
        len({
            x["source"]
            for x in deals
        }),
    )

    print()

    for item in products:
        price = (
            f'${item["price"]:.2f}'
            if item["price"]
            else "Browse"
        )

        print(
            f'{item["source"]:7} | '
            f'{price:8} | '
            f'{item["product_type"]:16} | '
            f'{item["title"]}'
        )

    print()
    print(f"✅ WROTE {OUT.name}")
    print(
        "UPDATED:",
        datetime.now(timezone.utc).isoformat(),
    )


if __name__ == "__main__":
    main()
