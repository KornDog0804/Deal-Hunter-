#!/usr/bin/env python3
"""
Provider identifier probe. READ-ONLY: fetches public pages, writes only into --out.

For every provider in sources.json it measures which product identifiers are really exposed:
  Shopify/Merchnow  -> products.json variants: barcode, sku (is the sku a valid GTIN? or just a store code?),
                       plus labelled barcode/catno/label/year in the description.
  HTML / other      -> up to --html-sample product pages taken from live_deals.json: JSON-LD gtin/sku/mpn + labelled text.
Outputs:
  identifier_coverage.json   per-provider counts and percentages
  identifiers_by_link.json   product link -> identifiers (merged into listings by the validation harness)
A retailer SKU is recorded as a SKU only. It is never promoted to a catalogue number here.
"""
import argparse, json, re, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import product_identifiers as pid

UA = "Mozilla/5.0 (compatible; KornDogDealHunterProbe/1.0)"


def http_get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def shopify_products(url, fetch):
    base = re.match(r"(https?://[^/]+)", url).group(1)
    cands = ([url.rstrip("/") + "/products.json?limit=250"] if "/collections/" in url else []) + [
        base + "/products.json?limit=250", base + "/collections/all/products.json?limit=250",
        base + "/collections/vinyl/products.json?limit=250"]
    for ep in cands:
        try:
            prods = json.loads(fetch(ep)).get("products", [])
            if prods:
                return base, prods
        except Exception:
            continue
    return base, []


def _blank():
    return {"listings": 0, "barcode": 0, "barcode_from_sku": 0, "sku_only": 0, "labelled_catno": 0,
            "labelled_label": 0, "labelled_year": 0, "jsonld_gtin": 0, "jsonld_mpn": 0, "any_strong_id": 0}


def _tally(c, ids):
    c["listings"] += 1
    if ids.get("barcode"):
        c["barcode"] += 1
        if ids.get("barcode_source") == "sku":
            c["barcode_from_sku"] += 1
        if ids.get("barcode_source") == "jsonld":
            c["jsonld_gtin"] += 1
    if ids.get("sku") and not ids.get("barcode"):
        c["sku_only"] += 1
    if ids.get("mpn"):
        c["jsonld_mpn"] += 1
    for k, f in (("catno", "labelled_catno"), ("label", "labelled_label"), ("year", "labelled_year")):
        if ids.get(k):
            c[f] += 1
    if ids.get("barcode") or ids.get("catno"):
        c["any_strong_id"] += 1


def probe_shopify(src, fetch):
    base, prods = shopify_products(src["url"], fetch)
    cov, by_link = _blank(), {}
    for p in prods:
        handle = p.get("handle")
        variants = p.get("variants") or []
        if not handle or not variants:
            continue
        ids = pid.from_shopify(p, variants[0], p.get("body_html", ""))
        ids.pop("vendor", None)
        _tally(cov, ids)
        by_link[base + "/products/" + handle] = ids
    cov["status"] = "ok" if prods else "no_products"
    return cov, by_link


def probe_html(src, links, fetch, sample):
    cov, by_link = _blank(), {}
    for link in links[:sample]:
        try:
            page = fetch(link)
        except Exception:
            continue
        ids = pid.from_jsonld(page)
        for k, v in pid.mine_text(re.sub(r"<[^>]+>", " ", page)[:20000]).items():
            ids.setdefault(k, v)
        _tally(cov, ids)
        by_link[link] = ids
    cov["status"] = "ok" if cov["listings"] else "no_pages"
    return cov, by_link


def run(sources, live_deals, fetch, html_sample=6, sleep=0.3):
    coverage, by_link = {}, {}
    for s in sources:
        name, st = s["name"], s.get("source_type", "")
        try:
            if st in ("shopify_store", "merchnow_store"):
                cov, links = probe_shopify(s, fetch)
                if cov["status"] != "ok":      # same HTML fallback the scraper uses
                    own = [d["link"] for d in live_deals if d.get("source") == name and d.get("link")]
                    cov, links = probe_html(s, own, fetch, html_sample)
                    cov["via"] = "html_fallback"
            else:
                own = [d["link"] for d in live_deals if d.get("source") == name and d.get("link")]
                cov, links = probe_html(s, own, fetch, html_sample)
                cov["via"] = "html_sample"
        except Exception as e:
            cov, links = dict(_blank(), status="error: %s" % e), {}
        cov["source_type"] = st
        n = cov["listings"] or 1
        cov["pct_barcode"] = round(100.0 * cov["barcode"] / n, 1)
        cov["pct_any_strong_id"] = round(100.0 * cov["any_strong_id"] / n, 1)
        coverage[name] = cov
        by_link.update(links)
        time.sleep(sleep)
    return coverage, by_link


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="validation_out")
    ap.add_argument("--html-sample", type=int, default=6)
    a = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    sources = json.loads((root / "sources.json").read_text())["sources"]
    live = json.loads((root / "live_deals.json").read_text())
    live = live if isinstance(live, list) else live.get("deals", [])
    cov, by_link = run(sources, live, http_get, a.html_sample)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "identifier_coverage.json").write_text(json.dumps(cov, indent=1))
    (out / "identifiers_by_link.json").write_text(json.dumps(by_link))
    tot = sum(c["listings"] for c in cov.values()) or 1
    print("providers=%d listings_probed=%d with_barcode=%d (%.1f%%) any_strong_id=%d" % (
        len(cov), tot, sum(c["barcode"] for c in cov.values()),
        100.0 * sum(c["barcode"] for c in cov.values()) / tot, sum(c["any_strong_id"] for c in cov.values())))
    for n, c in sorted(cov.items()):
        print("  %-24s %-14s n=%-4d barcode=%-4d sku_only=%-4d catno=%-3d %s" % (
            n, c["source_type"], c["listings"], c["barcode"], c["sku_only"], c["labelled_catno"], c["status"]))


if __name__ == "__main__":
    main()
