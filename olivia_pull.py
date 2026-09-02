#!/usr/bin/env python3

from pathlib import Path
import html
import json
import re
import unicodedata
import urllib.request
import urllib.parse

BASE = Path(__file__).resolve().parent

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 16; Pixel 10) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Mobile Safari/537.36"
    ),
    "Accept": "application/json,text/html,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

# ------------------------------------------------------------
# OLIVIA CHRISTMAS RADAR
# ------------------------------------------------------------

INTERESTS = {
    "DELTARUNE": [
        "deltarune",
        "delta rune",
    ],
    "UNDERTALE": [
        "undertale",
        "under tale",
    ],
    "HATSUNE MIKU": [
        "hatsune miku",
        "初音ミク",
        "vocaloid",
        "miku",
    ],
    "THE LIVING TOMBSTONE": [
        "the living tombstone",
        "living tombstone",
    ],
    "MITSKI": [
        "mitski",
    ],
    "POKEMON": [
        "pokemon",
        "pokémon",
        "pokemon center",
        "pikachu",
        "eevee",
    ],
    "FIVE NIGHTS AT FREDDY'S": [
        "five nights at freddy",
        "five nights at freddys",
        "five nights at freddy's",
        "fnaf",
        "freddy fazbear",
    ],
}

VINYL_WORDS = (
    "vinyl",
    "record",
    "lp",
    "soundtrack",
)

COLLECTIBLE_WORDS = (
    "funko",
    "pop!",
    "plush",
    "figure",
    "collectible",
    "statue",
    "pin",
    "keychain",
    "acrylic",
    "standee",
    "poster",
    "book",
    "game",
    "collector",
    "music box",
)

def clean(value):
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalized(value):
    value = clean(value)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        ch for ch in value
        if not unicodedata.combining(ch)
    )
    return value.lower()


def price(value):
    try:
        p = float(value)
        return round(p, 2) if p > 0 else 0.0
    except Exception:
        return 0.0


def fetch(url):
    req = urllib.request.Request(
        url,
        headers=HEADERS,
    )
    with urllib.request.urlopen(
        req,
        timeout=30,
    ) as resp:
        return resp.read().decode(
            "utf-8",
            "ignore",
        )


def fetch_json(url):
    return json.loads(fetch(url))


def read_json(name):
    path = BASE / name

    if not path.exists():
        return []

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        return data if isinstance(data, list) else []

    except Exception:
        return []


def matches(text):
    hay = normalized(text)
    hits = []

    for label, needles in INTERESTS.items():
        for needle in needles:
            if normalized(needle) in hay:
                hits.append(label)
                break

    return list(dict.fromkeys(hits))


def product_type_for(text, fallback="COLLECTIBLE"):
    hay = normalized(text)

    def has(term):
        return re.search(
            r"(?<![a-z0-9])"
            + re.escape(term)
            + r"(?![a-z0-9])",
            hay,
            re.I,
        ) is not None

    # Specific physical product types must win BEFORE
    # generic words such as "vinyl" or "record".
    if has("slipmat") or has("slip mat"):
        return "SLIPMAT"

    if has("coaster") or has("coasters"):
        return "ACCESSORY"

    if has("poster") or has("posters"):
        return "POSTER"

    if has("funko") or "pop!" in hay:
        return "FUNKO"

    if has("plush") or has("plushes"):
        return "PLUSH"

    if (
        has("figure")
        or has("figurine")
        or has("figurines")
        or has("statue")
    ):
        return "FIGURE"

    if has("book") or has("artbook"):
        return "BOOK"

    if has("pin") or has("pins"):
        return "PIN"

    if has("keychain"):
        return "KEYCHAIN"

    if has("sticker") or has("stickers"):
        return "STICKER"

    if has("ornament"):
        return "ORNAMENT"

    if has("magnet") or has("magnets"):
        return "MAGNET"

    if (
        has("shirt")
        or has("tee")
        or has("t-shirt")
        or has("hoodie")
        or has("jacket")
        or has("sweatpants")
        or has("socks")
        or has("scarf")
        or has("scarves")
        or has("hat")
        or has("tank top")
    ):
        return "APPAREL"

    # Actual records come after accessory checks.
    if (
        has("vinyl")
        or has("vinyl lp")
        or has("lp")
        or has("record")
        or has("soundtrack vinyl")
    ):
        return "VINYL"

    if (
        has("game")
        or has("standard edition")
        or has("collector's edition")
        or has("collectors edition")
        or has("nintendo switch")
        or has("playstation")
        or has("pc edition")
    ):
        return "GAME"

    # Clean up retailer-specific category names.
    fallback_map = {
        "T-SHIRTS": "APPAREL",
        "T-SHIRT": "APPAREL",
        "BOTTOMS": "APPAREL",
        "SWEATPANTS": "APPAREL",
        "HATS": "APPAREL",
        "SOCKS": "APPAREL",
        "SCARVES": "APPAREL",
        "FIGURINES": "FIGURE",
        "GAMES": "GAME",
        "BOOKS": "BOOK",
        "POSTERS": "POSTER",
        "LAPEL PINS": "PIN",
        "MUSIC": "MUSIC",
        "HOME & OFFICE": "HOME & OFFICE",
    }

    cleaned_fallback = clean(fallback or "COLLECTIBLE").upper()

    return fallback_map.get(
        cleaned_fallback,
        cleaned_fallback,
    )


def normalize_existing(row, origin):
    blob = " ".join([
        str(row.get("artist", "") or ""),
        str(row.get("title", "") or ""),
        str(row.get("raw_title", "") or ""),
        str(row.get("franchise", "") or ""),
        str(row.get("character", "") or ""),
        str(row.get("category", "") or ""),
        str(row.get("product_type", "") or ""),
        str(row.get("source", "") or ""),
    ])

    hits = matches(blob)

    if not hits:
        return None

    raw_title = clean(
        row.get("raw_title")
        or row.get("title")
        or ""
    )

    artist = clean(
        row.get("artist")
        or ""
    )

    if (
        artist
        and artist.lower() not in {
            "unknown",
            "unknown artist",
        }
        and artist.lower() not in raw_title.lower()
    ):
        display_title = f"{artist} - {raw_title}"
    else:
        display_title = raw_title

    if not display_title:
        return None

    type_text = " ".join([
        raw_title,
        str(row.get("title", "") or ""),
        str(row.get("product_type", "") or ""),
        str(row.get("category", "") or ""),
    ])

    ptype = product_type_for(
        type_text,
        fallback=clean(
            row.get("product_type")
            or row.get("category")
            or "COLLECTIBLE"
        ).upper()
    )

    return {
        "category": "OLIVIA",
        "title": display_title,
        "raw_title": raw_title,
        "artist": artist,
        "source": clean(
            row.get("source")
            or "Deal Hunter"
        ),
        "source_type": clean(
            row.get("source_type")
            or origin
        ),
        "product_type": ptype,
        "franchise": hits[0],
        "character": clean(
            row.get("character")
            or ""
        ),
        "price": price(
            row.get("price", 0)
        ),
        "compare_at": price(
            row.get("compare_at", 0)
        ),
        "image": str(
            row.get("image", "")
            or ""
        ),
        "link": str(
            row.get("link", "")
            or ""
        ),
        "availability_text": clean(
            row.get("availability_text")
            or "Available"
        ),
        "exclusive": bool(
            row.get("exclusive", False)
        ),
        "chase": bool(
            row.get("chase", False)
        ),
        "preorder": bool(
            row.get("preorder", False)
            or "preorder" in normalized(blob)
            or "pre-order" in normalized(blob)
        ),
        "sale": bool(
            row.get("sale", False)
        ),
        "clearance": bool(
            row.get("clearance", False)
        ),
        "deal": bool(
            row.get("deal", False)
        ),
        "amazing_deal": bool(
            row.get("amazing_deal", False)
        ),
        "sold_out": bool(
            row.get("sold_out", False)
        ),
        "olivia_hit": True,
        "olivia_tags": hits,
        "origin_dataset": origin,
    }


def shopify_products(url):
    try:
        data = fetch_json(url)
        return data.get("products", []) or []
    except Exception as exc:
        print(
            f"  Shopify fetch failed: "
            f"{url} | {exc}"
        )
        return []


def fangamer_rows():
    print("\n===== FANGAMER =====")

    endpoints = [
        (
            "https://www.fangamer.com/"
            "collections/vinyl/products.json"
            "?limit=250"
        ),
        (
            "https://www.fangamer.com/"
            "collections/undertale/products.json"
            "?limit=250"
        ),
        (
            "https://www.fangamer.com/"
            "collections/deltarune/products.json"
            "?limit=250"
        ),
    ]

    products = []
    handles = set()

    for endpoint in endpoints:
        chunk = shopify_products(endpoint)

        print(
            f"  {endpoint} -> "
            f"{len(chunk)} products"
        )

        for p in chunk:
            handle = str(
                p.get("handle", "")
                or ""
            )

            if not handle or handle in handles:
                continue

            handles.add(handle)
            products.append(p)

    rows = []

    for p in products:
        title = clean(
            p.get("title", "")
        )

        body = clean(
            p.get("body_html", "")
        )

        tags = p.get("tags", [])

        if isinstance(tags, list):
            tags = " ".join(
                str(x) for x in tags
            )

        blob = " ".join([
            title,
            body,
            str(tags),
            clean(
                p.get("product_type", "")
            ),
        ])

        hits = matches(blob)

        if not hits:
            continue

        variants = (
            p.get("variants", [])
            or []
        )

        available_variants = [
            v for v in variants
            if v.get("available", True)
        ]

        if not available_variants:
            continue

        variant = available_variants[0]

        handle = p.get("handle", "")

        images = (
            p.get("images", [])
            or []
        )

        image = ""

        if images:
            image = str(
                images[0].get("src", "")
                or ""
            )

        type_text = " ".join([
            title,
            clean(
                p.get(
                    "product_type",
                    "",
                )
            ),
        ])

        ptype = product_type_for(
            type_text,
            fallback=clean(
                p.get(
                    "product_type",
                    "COLLECTIBLE",
                )
            ).upper()
        )

        low = normalized(blob)

        rows.append({
            "category": "OLIVIA",
            "title": title,
            "raw_title": title,
            "artist": "",
            "source": "Fangamer",
            "source_type": "olivia_direct",
            "product_type": ptype,
            "franchise": hits[0],
            "character": "",
            "price": price(
                variant.get("price", 0)
            ),
            "compare_at": price(
                variant.get(
                    "compare_at_price",
                    0,
                )
            ),
            "image": image,
            "link": (
                "https://www.fangamer.com/"
                f"products/{handle}"
            ),
            "availability_text": (
                "Available from Fangamer"
            ),
            "exclusive": (
                "exclusive" in low
            ),
            "chase": False,
            "preorder": (
                "preorder" in low
                or "pre-order" in low
            ),
            "sale": bool(
                price(
                    variant.get(
                        "compare_at_price",
                        0,
                    )
                )
                >
                price(
                    variant.get(
                        "price",
                        0,
                    )
                )
            ),
            "clearance": (
                "clearance" in low
            ),
            "deal": False,
            "amazing_deal": False,
            "sold_out": False,
            "olivia_hit": True,
            "olivia_tags": hits,
            "origin_dataset": "fangamer",
        })

    print(
        f"Fangamer Olivia hits: "
        f"{len(rows)}"
    )

    return rows


def living_tombstone_rows():
    print("\n===== THE LIVING TOMBSTONE =====")

    endpoints = [
        (
            "https://thelivingtombstone.com/"
            "collections/all/products.json"
            "?limit=250"
        ),
        (
            "https://thelivingtombstone.com/"
            "products.json?limit=250"
        ),
    ]

    products = []

    for endpoint in endpoints:
        products = shopify_products(
            endpoint
        )

        print(
            f"  {endpoint} -> "
            f"{len(products)} products"
        )

        if products:
            break

    rows = []

    for p in products:
        title = clean(
            p.get("title", "")
        )

        if not title:
            continue

        body = clean(
            p.get("body_html", "")
        )

        tags = p.get("tags", [])

        if isinstance(tags, list):
            tags = " ".join(
                str(x) for x in tags
            )

        blob = " ".join([
            title,
            body,
            str(tags),
            clean(
                p.get("product_type", "")
            ),
        ])

        variants = (
            p.get("variants", [])
            or []
        )

        available_variants = [
            v for v in variants
            if v.get("available", True)
        ]

        if not available_variants:
            continue

        variant = available_variants[0]

        images = (
            p.get("images", [])
            or []
        )

        image = ""

        if images:
            image = str(
                images[0].get("src", "")
                or ""
            )

        handle = str(
            p.get("handle", "")
            or ""
        )

        if not handle:
            continue

        low = normalized(blob)

        type_text = " ".join([
            title,
            clean(
                p.get(
                    "product_type",
                    "",
                )
            ),
        ])

        ptype = product_type_for(
            type_text,
            fallback=clean(
                p.get(
                    "product_type",
                    "COLLECTIBLE",
                )
            ).upper()
        )

        current_price = price(
            variant.get("price", 0)
        )

        compare_at = price(
            variant.get(
                "compare_at_price",
                0,
            )
        )

        rows.append({
            "category": "OLIVIA",
            "title": title,
            "raw_title": title,
            "artist": "The Living Tombstone",
            "source": "The Living Tombstone",
            "source_type": "olivia_direct",
            "product_type": ptype,
            "franchise": "THE LIVING TOMBSTONE",
            "character": "",
            "price": current_price,
            "compare_at": compare_at,
            "image": image,
            "link": (
                "https://thelivingtombstone.com/"
                f"products/{handle}"
            ),
            "availability_text": (
                "Available from official store"
            ),
            "exclusive": (
                "exclusive" in low
            ),
            "chase": False,
            "preorder": (
                "preorder" in low
                or "pre-order" in low
                or "back-order" in low
            ),
            "sale": (
                compare_at > current_price > 0
            ),
            "clearance": (
                "clearance" in low
            ),
            "deal": False,
            "amazing_deal": False,
            "sold_out": False,
            "olivia_hit": True,
            "olivia_tags": [
                "THE LIVING TOMBSTONE"
            ],
            "origin_dataset": (
                "living_tombstone"
            ),
        })

    print(
        "Living Tombstone available "
        f"products: {len(rows)}"
    )

    return rows


def dedupe(rows):
    seen = {}
    fallback = {}

    for row in rows:
        if row.get("sold_out"):
            continue

        link = str(
            row.get("link", "")
            or ""
        ).strip()

        if link:
            try:
                parsed = urllib.parse.urlparse(
                    link
                )

                key = (
                    parsed.netloc
                    .lower()
                    .replace("www.", "")
                    +
                    parsed.path
                    .rstrip("/")
                    .lower()
                )

            except Exception:
                key = link.lower()

            if key not in seen:
                seen[key] = row

            continue

        title_key = (
            normalized(
                row.get("title", "")
            ),
            normalized(
                row.get("source", "")
            ),
        )

        if title_key not in fallback:
            fallback[title_key] = row

    return (
        list(seen.values())
        +
        list(fallback.values())
    )


def main():
    rows = []

    live = read_json(
        "live_deals.json"
    )

    collectibles = read_json(
        "collectibles_deals.json"
    )

    minis = read_json(
        "mini_vinyl_deals.json"
    )

    print(
        f"Existing live vinyl: "
        f"{len(live)}"
    )

    print(
        f"Existing collectibles: "
        f"{len(collectibles)}"
    )

    print(
        f"Existing mini vinyl: "
        f"{len(minis)}"
    )

    existing_hits = 0

    for item in live:
        row = normalize_existing(
            item,
            "live_deals",
        )

        if row:
            rows.append(row)
            existing_hits += 1

    for item in collectibles:
        row = normalize_existing(
            item,
            "collectibles_deals",
        )

        if row:
            rows.append(row)
            existing_hits += 1

    for item in minis:
        row = normalize_existing(
            item,
            "mini_vinyl_deals",
        )

        if row:
            rows.append(row)
            existing_hits += 1

    print(
        "\nExisting Olivia matches: "
        f"{existing_hits}"
    )

    rows.extend(
        fangamer_rows()
    )

    rows.extend(
        living_tombstone_rows()
    )

    rows = dedupe(rows)

    # Priority ordering for Christmas browsing:
    # direct official sources first, then deals,
    # then price.
    def sort_key(row):
        direct = (
            row.get("source_type")
            == "olivia_direct"
        )

        special = bool(
            row.get("amazing_deal")
            or row.get("deal")
            or row.get("sale")
            or row.get("exclusive")
            or row.get("chase")
            or row.get("preorder")
        )

        p = price(
            row.get("price", 0)
        )

        if p <= 0:
            p = 999999

        return (
            0 if direct else 1,
            0 if special else 1,
            p,
            normalized(
                row.get("title", "")
            ),
        )

    rows.sort(
        key=sort_key
    )

    out = (
        BASE
        / "olivia_deals.json"
    )

    out.write_text(
        json.dumps(
            rows,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        "\n"
        + "=" * 50
    )

    print(
        "🎄 OLIVIA CHRISTMAS RADAR"
    )

    print(
        "=" * 50
    )

    print(
        f"TOTAL AVAILABLE HITS: "
        f"{len(rows)}"
    )

    counts = {}

    for row in rows:
        for tag in (
            row.get(
                "olivia_tags",
                [],
            )
            or []
        ):
            counts[tag] = (
                counts.get(tag, 0)
                + 1
            )

    for key in INTERESTS:
        print(
            f"{key}: "
            f"{counts.get(key, 0)}"
        )

    print(
        "\nBY SOURCE:"
    )

    sources = {}

    for row in rows:
        src = row.get(
            "source",
            "Unknown",
        )

        sources[src] = (
            sources.get(src, 0)
            + 1
        )

    for src, count in sorted(
        sources.items(),
        key=lambda x: (
            -x[1],
            x[0],
        ),
    ):
        print(
            f"  {src}: {count}"
        )

    print(
        "\nOUTPUT:"
    )

    print(out)


if __name__ == "__main__":
    main()
