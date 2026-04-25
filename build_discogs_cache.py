#!/usr/bin/env python3
"""
Build Discogs Cache - Enriches live_deals.json using discogs_integration library.
Simple, robust wrapper around the ChatGPT library.
"""

import os
import json
import sys
import time
from discogs_integration import enrich_with_discogs

print("🎯 Starting Discogs Enrichment (ChatGPT Library Version)", flush=True)

# Load deals
try:
    with open('live_deals.json', 'r') as f:
        deals = json.load(f)
    print(f"✅ Loaded {len(deals)} deals", flush=True)
except Exception as e:
    print(f"❌ Error loading live_deals.json: {e}", flush=True)
    sys.exit(1)

# Load existing cache
cache = {}
try:
    with open('discogs_cache.json', 'r') as f:
        cache = json.load(f)
    print(f"✅ Loaded {len(cache)} cached entries", flush=True)
except FileNotFoundError:
    print("📝 Starting with fresh cache", flush=True)
except Exception as e:
    print(f"⚠️  Error loading cache: {e}", flush=True)

# Process deals
enriched_count = 0
start_time = time.time()

print(f"\n⏳ Processing {len(deals)} records...", flush=True)

for i, deal in enumerate(deals):
    enrich_with_discogs(deal, cache)
    
    if deal.get('discogs_found'):
        enriched_count += 1
    
    # Progress update every 100 deals
    if (i + 1) % 100 == 0:
        elapsed = time.time() - start_time
        rate = (i + 1) / elapsed if elapsed > 0 else 0
        pct = int((i + 1) / len(deals) * 100)
        print(f"⏳ {i + 1:4d}/{len(deals)} ({pct:3d}%) | Enriched: {enriched_count:4d} | {rate:.1f} deals/sec", flush=True)

# Save enriched deals
try:
    with open('live_deals.json', 'w') as f:
        json.dump(deals, f, indent=2)
    print(f"\n✅ Saved {len(deals)} enriched deals to live_deals.json", flush=True)
except Exception as e:
    print(f"❌ Error saving live_deals.json: {e}", flush=True)
    sys.exit(1)

# Save cache
try:
    with open('discogs_cache.json', 'w') as f:
        json.dump(cache, f, indent=2)
    print(f"✅ Saved {len(cache)} cache entries to discogs_cache.json", flush=True)
except Exception as e:
    print(f"❌ Error saving cache: {e}", flush=True)
    sys.exit(1)

total_time = time.time() - start_time

print(f"\n🎉 Discogs Enrichment Complete!")
print(f"   Total deals: {len(deals)}")
print(f"   Enriched with Discogs: {enriched_count}")
print(f"   Match rate: {(enriched_count/len(deals)*100):.1f}%")
print(f"   Cache size: {len(cache)}")
print(f"   Total time: {total_time:.1f}s", flush=True)
