#!/usr/bin/env python3
import os
import json
import sys
import time
import re
import requests
from discogs_integration import enrich_with_discogs

print("🎯 Starting Deal Cleanup + Discogs Enrichment", flush=True)

INPUT_FILE = "live_deals.json"
CACHE_FILE = "discogs_cache.json"

BAD_PRODUCT_WORDS = [
    "drawstring bag", "wall flag", "flag", "shirt", "hoodie", "hat",
    "poster", "sticker", "patch", "pin", "slipmat", "tote", "bag"
]

def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()

def get_deal_link(deal):
    keys = [
        "link", "url", "product_url", "store_url",
        "purchase_url", "source_url", "reddit_url"
    ]

    for key in keys:
        value = str(deal.get(key) or "").strip()
        if value.startswith("http"):
            return value

    blob = " ".join([
        str(deal.get("raw_title") or ""),
        str(deal.get("page_text_snippet") or ""),
        str(deal.get("description") or "")
    ])

    match = re.search(r"https?://[^\s\"'<>]+", blob)
    return match.group(0) if match else ""

def looks_like_vinyl(deal):
    blob = clean_text(" ".join([
        deal.get("artist", ""),
        deal.get("title", ""),
        deal.get("raw_title", ""),
        deal.get("format", ""),
        deal.get("version", ""),
        deal.get("page_text_snippet", "")
    ]))

    if any(word in blob for word in BAD_PRODUCT_WORDS):
        return False

    if "vinyl" in blob or "lp" in blob or "record" in blob or "2lp" in blob or "3lp" in blob:
        return True

    return clean_text(deal.get("format", "")) == "vinyl"

def link_is_alive(url):
    if not url:
        return False

    try:
        response = requests.get(
            url,
            timeout=15,
            allow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Linux; Android 16; Pixel 10) AppleWebKit/537.36 Chrome/124.0 Mobile Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

        text = response.text[:4000].lower()
        final_url = response.url.lower()

        if response.status_code >= 400:
            return False

        bad_signals = [
            "404 page not found",
            "page not found",
            "the page you requested does not exist",
            "this product is unavailable",
            "product not found"
        ]

        if any(signal in text for signal in bad_signals):
            return False

        if "/404" in final_url:
            return False

        return True

    except Exception:
        return False

def normalize_deal(deal):
    link = get_deal_link(deal)
    deal["link"] = link

    if not deal.get("format"):
        deal["format"] = "vinyl"

    return deal

# Load deals
try:
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        deals = json.load(f)
    print(f"✅ Loaded {len(deals)} deals", flush=True)
except Exception as e:
    print(f"❌ Error loading {INPUT_FILE}: {e}", flush=True)
    sys.exit(1)

# Load cache
cache = {}
try:
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)
    print(f"✅ Loaded {len(cache)} cached entries", flush=True)
except FileNotFoundError:
    print("📝 Starting with fresh Discogs cache", flush=True)
except Exception as e:
    print(f"⚠️ Error loading cache: {e}", flush=True)

cleaned_deals = []
enriched_count = 0
dead_link_count = 0
non_vinyl_count = 0
start_time = time.time()

print(f"\n⏳ Cleaning and enriching {len(deals)} records...", flush=True)

for i, deal in enumerate(deals):
    deal = normalize_deal(deal)

    if not looks_like_vinyl(deal):
        non_vinyl_count += 1
        continue

    if not link_is_alive(deal.get("link", "")):
        dead_link_count += 1
        continue

    enrich_with_discogs(deal, cache)

    if deal.get("discogs_found"):
        enriched_count += 1

    cleaned_deals.append(deal)

    if (i + 1) % 100 == 0:
        elapsed = time.time() - start_time
        rate = (i + 1) / elapsed if elapsed > 0 else 0
        pct = int((i + 1) / len(deals) * 100)
        print(
            f"⏳ {i + 1:4d}/{len(deals)} ({pct:3d}%) | "
            f"Kept: {len(cleaned_deals):4d} | "
            f"Discogs: {enriched_count:4d} | "
            f"Dead: {dead_link_count:4d} | "
            f"Non-vinyl: {non_vinyl_count:4d} | "
            f"{rate:.1f}/sec",
            flush=True
        )

# Save cleaned enriched deals
try:
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned_deals, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Saved {len(cleaned_deals)} cleaned enriched deals to {INPUT_FILE}", flush=True)
except Exception as e:
    print(f"❌ Error saving {INPUT_FILE}: {e}", flush=True)
    sys.exit(1)

# Save cache
try:
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved {len(cache)} cache entries to {CACHE_FILE}", flush=True)
except Exception as e:
    print(f"❌ Error saving cache: {e}", flush=True)
    sys.exit(1)

total_time = time.time() - start_time

print("\n🎉 Cleanup + Discogs Enrichment Complete!")
print(f"   Original deals: {len(deals)}")
print(f"   Kept vinyl deals: {len(cleaned_deals)}")
print(f"   Removed dead links: {dead_link_count}")
print(f"   Removed non-vinyl/merch: {non_vinyl_count}")
print(f"   Enriched with Discogs: {enriched_count}")
print(f"   Match rate: {(enriched_count / max(len(cleaned_deals), 1) * 100):.1f}%")
print(f"   Cache size: {len(cache)}")
print(f"   Total time: {total_time:.1f}s", flush=True)
