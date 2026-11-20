"""
Manual importer for sources the scraper cannot read (Phase 2: Record City Japan).

You paste/export rows into a CSV; this turns them into deal records in the SAME shape the
validator already understands, then the normal strict Discogs matcher + landed-cost model
judge them. Nothing here touches production files: output goes to --out (default imports/).

CSV columns (header row required; only artist, title, price are mandatory):
  artist,title,price,currency,url,barcode,catno,label,year,country,condition,
  obi,edition,format,quantity,shop,notes
- currency   default JPY. A JPY->USD rate must be set in cost_config.json (fx.rates_to_usd.JPY),
             otherwise every row is reported with missing fx_rate:JPY (cost INCOMPLETE).
- condition  new/sealed rows are valued like new copies. Anything else (e.g. "VG+") is flagged
             for hand check, because the Discogs estimate assumes near-mint.
- barcode/catno are what let a Japanese pressing become an exact match. A Japanese catalog
  number is NOT guessed from the title; leave blank if the listing does not show it.
- Japanese pressings are different Discogs releases from US/EU ones: country defaults to Japan
  so a US pressing can never be silently accepted as the match.
Usage: python3 scripts/manual_import.py rows.csv [--out imports] [--shop "Record City Japan"]
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import product_identifiers as pid  # noqa: E402

COLS = ("artist", "title", "price", "currency", "url", "barcode", "catno", "label", "year", "country",
        "condition", "obi", "edition", "format", "quantity", "shop", "notes")


def _clean(v):
    return str(v or "").strip()


def row_to_deal(row, default_shop="Record City Japan", default_currency="JPY", default_country="Japan"):
    """One CSV row -> (deal | None, problem | None)."""
    artist, title = _clean(row.get("artist")), _clean(row.get("title"))
    if not artist or not title:
        return None, "missing artist or title"
    try:
        price = float(_clean(row.get("price")).replace(",", "").replace("¥", "").replace("$", ""))
    except ValueError:
        return None, "price is not a number"
    if price <= 0:
        return None, "price must be > 0"
    cur = (_clean(row.get("currency")) or default_currency).upper()
    barcode_raw = _clean(row.get("barcode"))
    barcode = pid.normalize_barcode(barcode_raw)
    if barcode_raw and not barcode:
        return None, "barcode %r is not a valid UPC/EAN (check digit fails); fix it or leave it blank" % barcode_raw
    ident = {}
    if barcode:
        ident["barcode"] = barcode
    if _clean(row.get("catno")):
        ident["catno"] = _clean(row.get("catno"))
    edition = " ".join(x for x in (_clean(row.get("edition")),
                                   "OBI" if _clean(row.get("obi")).lower() in ("1", "y", "yes", "true", "obi") else "") if x)
    raw = "%s - %s%s" % (artist, title, (" (%s)" % edition) if edition else "")
    deal = {
        "artist": artist, "title": title + ((" (%s)" % edition) if edition else ""), "raw_title": raw,
        "price": price, "currency": cur, "source": _clean(row.get("shop")) or default_shop,
        "source_type": "manual_import", "link": _clean(row.get("url")),
        "format": _clean(row.get("format")) or "vinyl", "condition": _clean(row.get("condition")),
        "country": _clean(row.get("country")) or default_country,
        "cost_profile": "international" if cur != "USD" or default_country.lower() != "us" else "domestic_us",
        "quantity": int(float(_clean(row.get("quantity")) or 1)),
        "notes": _clean(row.get("notes")),
    }
    if ident:
        deal["identifiers"] = ident
        deal.update({k: v for k, v in (("barcode", barcode), ("catalog_number", ident.get("catno"))) if v})
    for k in ("label", "year"):
        if _clean(row.get(k)):
            deal[k] = _clean(row.get(k))
    return deal, None


def import_csv(path, **kw):
    deals, problems = [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            d, why = row_to_deal(row, **kw)
            if d:
                deals.append(d)
            else:
                problems.append({"line": i, "problem": why, "row": dict(row)})
    return deals, problems


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", default="imports")
    ap.add_argument("--shop", default="Record City Japan")
    a = ap.parse_args(argv)
    deals, problems = import_csv(a.csv, default_shop=a.shop)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "import_deals.json").write_text(json.dumps(deals, indent=1, ensure_ascii=False))
    (out / "import_problems.json").write_text(json.dumps(problems, indent=1, ensure_ascii=False))
    print("imported %d rows, %d rejected (see %s)" % (len(deals), len(problems), out / "import_problems.json"))
    return 0 if deals else 1


if __name__ == "__main__":
    sys.exit(main())
