#!/usr/bin/env python3

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "collectibles_deals.json"

AMAZON_TAG = "korndog20-20"

UA = (
    "Mozilla/5.0 (Linux; Android 17) "
    "AppleWebKit/537.36 Chrome/140 Safari/537.36"
)


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
    category,
    title,
    source,
    link,
    product_type="FUNKO",
    franchise="",
    character="",
    price=0,
    compare_at_price=0,
    image="",
    exclusive=False,
    chase=False,
    preorder=False,
    sold_out=False,
    clearance=False,
    sale=False,
    availability="Browse current listings",
    source_type="collectible_product",
):
    deal = False
    discount_pct = 0

    try:
        if compare_at_price and price:
            discount_pct = round(
                ((compare_at_price - price) / compare_at_price) * 100
            )
            deal = discount_pct > 0
    except Exception:
        pass

    # A sale collection is not automatically a great deal.
    # Reserve DEAL for an actual markdown, explicit clearance,
    # or an unusually cheap available Funko.
    low_price_deal = (
        category == "FUNKO"
        and price > 0
        and price <= 8.00
    )

    if clearance or low_price_deal:
        deal = True

    amazing_deal = bool(
        clearance
        or discount_pct >= 30
        or (
            category == "FUNKO"
            and price > 0
            and price <= 7.00
        )
    )

    return {
        "category": category,
        "title": title,
        "raw_title": title,
        "source": source,
        "source_type": source_type,
        "product_type": product_type,
        "franchise": franchise,
        "character": character,
        "price": price,
        "compare_at_price": compare_at_price,
        "discount_pct": discount_pct,
        "image": image,
        "link": link,
        "exclusive": exclusive,
        "chase": chase,
        "preorder": preorder,
        "sold_out": sold_out,
        "clearance": clearance,
        "sale": sale,
        "deal": deal,
        "amazing_deal": amazing_deal,
        "availability_text": availability,
        "collectible": True,
    }


def fetch(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
        },
    )

    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="ignore")


def clean_html(value):
    value = re.sub(r"<[^>]+>", " ", str(value or ""))
    value = value.replace("&amp;", "&")
    value = value.replace("&#39;", "'")
    value = value.replace("&quot;", '"')
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def money(value):
    if value in (None, "", False):
        return 0

    try:
        n = float(value)
    except Exception:
        return 0

    # Shopify .js endpoints sometimes return cents.
    if n >= 1000 and float(n).is_integer():
        n = n / 100

    return round(n, 2)


def looks_like_funko(product):
    title = str(product.get("title", "")).lower()
    vendor = str(product.get("vendor", "")).lower()
    product_type = str(product.get("product_type", "")).lower()

    tags = product.get("tags", "")

    if isinstance(tags, list):
        tags = " ".join(map(str, tags))

    tags = str(tags).lower()

    haystack = " ".join([
        title,
        vendor,
        product_type,
        tags,
    ])

    return any(x in haystack for x in [
        "funko",
        "pop!",
        "bitty pop",
        "vinyl soda",
        "funko soda",
        "mystery minis",
        "mystery mini",
        "rewind",
    ])


def brads_product_row(product, collection_hint=""):
    title = clean_html(product.get("title", ""))

    handle = str(
        product.get("handle", "")
    ).strip()

    if not handle:
        return None

    if not looks_like_funko(product):
        return None

    link = (
        "https://www.bradstoys.com/products/"
        + urllib.parse.quote(handle)
    )

    variants = product.get("variants") or []

    prices = []
    compare_prices = []
    available = False

    for variant in variants:
        price = money(variant.get("price"))

        if price > 0:
            prices.append(price)

        compare = money(
            variant.get("compare_at_price")
        )

        if compare > 0:
            compare_prices.append(compare)

        if variant.get("available") is True:
            available = True

    price = min(prices) if prices else 0

    compare_at = (
        max(compare_prices)
        if compare_prices
        else 0
    )

    images = product.get("images") or []
    image = ""

    if images:
        first = images[0]

        if isinstance(first, dict):
            image = str(
                first.get("src", "")
            )
        elif isinstance(first, str):
            image = first

    if not image:
        image_obj = product.get("image")

        if isinstance(image_obj, dict):
            image = str(
                image_obj.get("src", "")
            )
        elif isinstance(image_obj, str):
            image = image_obj

    tags = product.get("tags", "")

    if isinstance(tags, list):
        tags = " ".join(map(str, tags))

    low = " ".join([
        title,
        str(tags),
        str(product.get("product_type", "")),
        collection_hint,
    ]).lower()

    chase = "chase" in low

    preorder = (
        "pre-order" in low
        or "preorder" in low
        or "pre order" in low
    )

    exclusive = "exclusive" in low

    # Being present in Brad's Funko Sale collection
    # means SALE, not necessarily CLEARANCE.
    sale = (
        collection_hint == "funko-sale"
        or " sale " in f" {low} "
    )

    # Only use CLEARANCE when Brad's explicitly says it.
    clearance = "clearance" in low

    sold_out = not available

    availability = (
        "Sold Out"
        if sold_out
        else "Brad's Toys • available"
    )

    return row(
        category="FUNKO",
        title=title,
        source="Brad's Toys",
        link=link,
        product_type=(
            product.get("product_type")
            or "FUNKO"
        ),
        price=price,
        compare_at_price=compare_at,
        image=image,
        exclusive=exclusive,
        chase=chase,
        preorder=preorder,
        sold_out=sold_out,
        clearance=clearance,
        sale=sale,
        availability=availability,
        source_type="collectible_product",
    )


def fetch_json(url):
    text = fetch(url)
    return json.loads(text)


def brads_json_collection(
    collection,
    max_pages=30,
):
    out = []

    for page in range(1, max_pages + 1):
        url = (
            "https://www.bradstoys.com/"
            f"collections/{collection}/"
            "products.json"
            f"?limit=250&page={page}"
        )

        try:
            data = fetch_json(url)
        except Exception as e:
            print(
                "Brad's JSON failed:",
                collection,
                page,
                e,
            )
            break

        products = data.get("products") or []

        print(
            f"Brad's {collection} JSON page "
            f"{page}: {len(products)} products"
        )

        if not products:
            break

        added = 0

        for product in products:
            item = brads_product_row(
                product,
                collection_hint=collection,
            )

            if item:
                out.append(item)
                added += 1

        print(
            f"  ↳ {added} Funko rows"
        )

        if len(products) < 250:
            break

    return out


def brads_all_funko():
    """
    Brad's /collections/all/funko does not expose
    products.json, but its HTML collection pages
    expose product handles. Shopify's product .js
    endpoint then gives us structured product data.
    """

    out = []
    handles = set()

    for page in range(1, 60):
        url = (
            "https://www.bradstoys.com/"
            "collections/all/funko"
            f"?page={page}"
        )

        try:
            html = fetch(url)
        except Exception as e:
            print(
                "Brad's all/funko page failed:",
                page,
                e,
            )
            break

        found = re.findall(
            r'href=["\']/products/'
            r'([^"\'?#/]+)',
            html,
            flags=re.I,
        )

        found = list(
            dict.fromkeys(found)
        )

        fresh = [
            handle
            for handle in found
            if handle not in handles
        ]

        print(
            f"Brad's all/funko page {page}: "
            f"{len(found)} handles, "
            f"{len(fresh)} new"
        )

        if not found:
            break

        if page > 1 and not fresh:
            break

        for handle in fresh:
            handles.add(handle)

        # Collection pages normally contain fewer
        # products on their last page.
        if len(found) < 5:
            break

    print(
        "Brad's unique Funko handles:",
        len(handles),
    )

    for n, handle in enumerate(
        sorted(handles),
        1,
    ):
        url = (
            "https://www.bradstoys.com/products/"
            f"{urllib.parse.quote(handle)}.js"
        )

        try:
            product = fetch_json(url)
        except Exception as e:
            print(
                "Brad's product JSON failed:",
                handle,
                e,
            )
            continue

        item = brads_product_row(
            product,
            collection_hint="all-funko",
        )

        if item:
            out.append(item)

        if n % 50 == 0:
            print(
                f"  ↳ processed {n}/"
                f"{len(handles)} products"
            )

    return out


def brads_products():
    out = []

    print()
    print(
        "===== BRAD'S FULL FUNKO COLLECTION ====="
    )

    try:
        out.extend(
            brads_all_funko()
        )
    except Exception as e:
        print(
            "Brad's full collection failed:",
            e,
        )

    print()
    print(
        "===== BRAD'S FUNKO SALE JSON ====="
    )

    try:
        out.extend(
            brads_json_collection(
                "funko-sale",
                max_pages=30,
            )
        )
    except Exception as e:
        print(
            "Brad's sale failed:",
            e,
        )

    print()
    print(
        "===== BRAD'S EXCLUSIVES JSON ====="
    )

    try:
        out.extend(
            brads_json_collection(
                "brads-toys-exclusives",
                max_pages=10,
            )
        )
    except Exception as e:
        print(
            "Brad's exclusives failed:",
            e,
        )

    # Deduplicate Brad's rows before returning.
    unique = []
    seen = set()

    for item in out:
        link = item.get("link", "").lower()

        if not link or link in seen:
            continue

        seen.add(link)
        unique.append(item)

    print()
    print(
        "✅ BRAD'S UNIQUE FUNKO PRODUCTS:",
        len(unique),
    )

    return unique


def funko_catalog_rows():
    return [
        row(
            "FUNKO",
            "Funko Pop! • Browse All",
            "Funko.com",
            "https://funko.com/new-featured/pop/",
            product_type="POP",
            source_type="collectible_catalog",
        ),
        row(
            "FUNKO",
            "Funko Exclusives • Browse All",
            "Funko.com",
            "https://funko.com/new-featured/exclusives/",
            product_type="EXCLUSIVE",
            exclusive=True,
            source_type="collectible_catalog",
        ),
        row(
            "FUNKO",
            "Funko Preorders • Browse All",
            "Funko.com",
            "https://funko.com/new-featured/pre-order/",
            product_type="PREORDER",
            preorder=True,
            source_type="collectible_catalog",
        ),
        row(
            "FUNKO",
            "Funko Chance of Chase • Browse All",
            "Funko.com",
            "https://funko.com/new-featured/chance-of-chase/",
            product_type="CHASE",
            chase=True,
            source_type="collectible_catalog",
        ),
        row(
            "FUNKO",
            "Funko Pop! • Amazon",
            "Amazon",
            amazon_url("Funko Pop"),
            source_type="collectible_catalog",
        ),
        row(
            "FUNKO",
            "Funko Pop! • Walmart",
            "Walmart",
            walmart_url("Funko Pop"),
            source_type="collectible_catalog",
        ),
        row(
            "FUNKO",
            "Funko Pop! • Target",
            "Target",
            target_url("Funko Pop"),
            source_type="collectible_catalog",
        ),
        row(
            "FUNKO",
            "Funko Pop! • Brad's Toys",
            "Brad's Toys",
            "https://www.bradstoys.com/collections/all/funko",
            source_type="collectible_catalog",
        ),
        row(
            "FUNKO",
            "Funko Sale • Brad's Toys",
            "Brad's Toys",
            "https://www.bradstoys.com/collections/funko-sale",
            clearance=True,
            source_type="collectible_catalog",
        ),
        row(
            "FUNKO",
            "Brad's Toys Exclusives",
            "Brad's Toys",
            "https://www.bradstoys.com/collections/brads-toys-exclusives",
            exclusive=True,
            source_type="collectible_catalog",
        ),
    ]


def dedupe(rows):
    out = []
    seen = set()

    for x in rows:
        key = (
            str(x.get("source", "")).lower(),
            str(x.get("link", "")).lower(),
        )

        if key in seen:
            continue

        seen.add(key)
        out.append(x)

    return out


def main():
    data = []

    data.extend(funko_catalog_rows())

    print("=" * 60)
    print("👹 HARVESTING BRAD'S TOYS FUNKO")
    print("=" * 60)

    try:
        data.extend(brads_products())
    except Exception as e:
        print("Brad's fatal error:", e)

    data = dedupe(data)

    OUT.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    products = [
        x for x in data
        if x["source_type"] == "collectible_product"
    ]

    catalogs = [
        x for x in data
        if x["source_type"] == "collectible_catalog"
    ]

    print()
    print("=" * 60)
    print("🧸 KORNDOG COLLECTIBLES")
    print("=" * 60)

    print("TOTAL:", len(data))
    print("PRODUCTS:", len(products))
    print("CATALOGS:", len(catalogs))
    print("CHASE:", sum(bool(x.get("chase")) for x in data))
    print("EXCLUSIVE:", sum(bool(x.get("exclusive")) for x in data))
    print("PREORDER:", sum(bool(x.get("preorder")) for x in data))
    print("CLEARANCE:", sum(bool(x.get("clearance")) for x in data))
    print("SOLD OUT:", sum(bool(x.get("sold_out")) for x in data))

    amazon = [
        x for x in data
        if x["source"] == "Amazon"
    ]

    assert all(
        "tag=korndog20-20" in x["link"]
        for x in amazon
    )

    print("✅ Amazon affiliate tag preserved")
    print(f"✅ wrote {OUT.name}")


if __name__ == "__main__":
    main()
