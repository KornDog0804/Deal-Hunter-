# KornDog Deal Hunter

Private buying intelligence system for KornDog Records (Bowling Green, KY).

Scrapes 20+ vinyl stores on a schedule, scores deals, and surfaces buy signals — so I know what to buy, when to buy it, and what it's worth before anyone else does.

---

## What It Does

- Pulls live inventory from 20+ stores every 6 hours via GitHub Actions
- Filters deals against my artist whitelist
- Scores deals by format, keywords, and price signals
- Tracks upcoming vinyl releases from my target artists
- Outputs clean JSON files ready for my private dashboard

---

## Output Files

| File | What It Is |
|------|-----------|
| `live_deals.json` | All deals pulled from all sources |
| `buy_signals.json` | Whitelist-only deals sorted by score — my shopping list |
| `upcoming_releases.json` | This week's releases from artists I track |
| `debug_live_pull.txt` | Full scrape log for debugging |

---

## Sources

**Shopify stores:** Rollin Records, Sound of Vinyl, uDiscover, Fearless, Rise Records, Brooklyn Vegan, Revolver, Newbury Comics, Craft Recordings, MNRK Heavy, Equal Vision, Rhino, Interscope, SharpTone, Rock Metal Fan Nation, Sumerian, Solid State, IndieMerchstore, Hopeless, Pirates Press

**MerchNOW stores:** Pure Noise, Trust Records, Spinefarm, InVogue, Thriller Records, Hopeless Records

**Other:** Deep Discount, Walmart, Merchbar, Hot Topic, UNFD

---

## Files

| File | Purpose |
|------|---------|
| `live_pull.py` | Main scraper — runs all sources and writes output JSON |
| `artist_whitelist.json` | Artists I track and prioritize |
| `slug_patterns.json` | URL pattern matching helpers |
| `.github/workflows/run-deal-hunter.yml` | GitHub Actions schedule |

---

## Schedule

Runs automatically 3x per day: 7am, 1pm, 7pm Central.
Trigger manually anytime from the Actions tab.

---

*KornDog Records — Vinyl Therapy Never Dies.*
