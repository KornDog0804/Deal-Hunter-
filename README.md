# Korndog Deal Hunter Starter

This is a free starter build for your deal-hunting brain.

## Files
- `artists.json` -> artist priority tiers
- `rules.json` -> scoring weights and thresholds
- `filters.json` -> positive and ignore keywords
- `sources.json` -> stores and alert sources to watch
- `sample_deals.json` -> example deals to test against the brain
- `scorer.py` -> scores sample deals and writes `scored_deals.json`

## Run it
```bash
python scorer.py
```

## What it does
- gives artist-fit points
- boosts variants, anniversary editions, exclusives
- downranks junk
- gives Sound of Vinyl and other trusted alerts a boost
- treats vinyl as the main format

## Next upgrades
1. replace `sample_deals.json` with real scraped deals
2. add affiliate link fields
3. compare against Discogs / retailer averages
4. publish results to a simple webpage or dashboard
