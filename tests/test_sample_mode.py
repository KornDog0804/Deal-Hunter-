import json
from scripts import phase1_validation as pv


def deal(i, src, raw, artist="A", title=None, **kw):
    d = {"link": "https://x/%d" % i, "source": src, "price": 20.0, "artist": artist + str(i),
         "title": title or ("Album %d" % i), "raw_title": raw}
    d.update(kw)
    return d


def make(n_src=5, per=12):
    out, i = [], 0
    for s in range(n_src):
        for k in range(per):
            i += 1
            raw = "Album %d (Deluxe)" % i if k % 4 == 0 else "Album %d Red Vinyl" % i if k % 4 == 1 else "Album %d" % i
            out.append(deal(i, "Store%d" % s, raw))
    return out


def test_sample_is_deterministic_and_covers_every_provider():
    deals = make()
    a = pv.select_sample(deals, [], n=30, seed=1)
    b = pv.select_sample(deals, [], n=30, seed=1)
    assert [c["key"] for c in a] == [c["key"] for c in b]
    assert len(a) == 30 and len({c["key"] for c in a}) == 30
    assert {c["deal"]["source"] for c in a} == {"Store%d" % i for i in range(5)}


def test_sample_includes_parenthetical_variant_and_barcode_strata():
    deals = make()
    deals[2]["identifiers"] = {"barcode": "081227890988"}
    whys = {c["why"] for c in pv.select_sample(deals, [], n=40, seed=1)}
    assert {"paren_title", "variant_title", "has_barcode"} <= whys


def test_merge_identifiers_is_additive():
    d = [{"link": "L", "identifiers": {"sku": "S1"}}, {"link": "M"}]
    n = pv.merge_identifiers(d, {"L": {"sku": "OTHER", "barcode": "081227890988"}})
    assert n == 1 and d[0]["identifiers"] == {"sku": "S1", "barcode": "081227890988"} and "identifiers" not in d[1]


def test_compare_lists_audit_pairs():
    deals = make(1, 3)
    sample = pv.select_sample(deals, [], n=3, seed=1)
    keyed = [{"link": d["link"], "source": d["source"], "artist": d["artist"], "title": d["title"], "status": "exact",
              "_key": c["key"], "release_id": 5, "matched_title": "T"} for d, c in zip(deals, sample)]
    # map rows to the right keys regardless of ordering
    keys = {c["deal"]["link"]: c["key"] for c in sample}
    for r in keyed:
        r["_key"] = keys[r["link"]]
    old = [{"link": r["link"], "status": "none"} for r in keyed]
    out = pv.compare_old_new(sample, old, keyed)
    assert out["old_verified"] == 0 and out["new_verified"] == 3 and len(out["audit_pairs"]) == 3
    assert out["transitions"] == {"none -> exact": 3}


def test_thin_market_flagged_and_excluded_from_review_free_count():
    import landed_cost as lc
    cfg = lc.load_config()
    deals = [{"link": "L", "source": "Rhino", "price": 20.0, "artist": "A", "title": "T"}]
    from discogs_matcher import extract_identifiers, identity_key
    key = identity_key(extract_identifiers(deals[0]))
    state = {"records": {key: {"status": "title_only", "confidence": 0.5, "release_id": 1, "tier": "likely",
                               "floor_estimate": 100.0, "floor_depth": 1, "reasons": []}}}
    row = pv.build_results(deals, state, cfg)[0]
    assert row["thin_market"] is True and row["needs_review"] is True
    assert row["valuation_label"] == "Lowest Asking Price Estimate"


def _row(status, artist, reasons, depth=10, ids=None, price=20.0, resale=60.0):
    import landed_cost as lc
    from discogs_matcher import extract_identifiers, identity_key
    cfg = lc.load_config()
    d = {"link": "L", "source": "Rhino", "price": price, "artist": artist, "title": "T"}
    state = {"records": {identity_key(extract_identifiers(d)): {
        "status": status, "confidence": 0.9, "release_id": 1, "reasons": reasons, "resale_estimate": resale,
        "num_for_sale": depth}}}
    return pv.build_results([d], state, cfg)[0]


def test_unknown_shipping_is_labelled_incomplete_not_confirmed():
    row = _row("exact", "Korn", ["barcode_match"])
    assert row["cost_status"] == "incomplete" and "INCOMPLETE" in row["net_label"]


def test_unknown_artist_and_label_only_strong_need_manual_check():
    assert _row("strong", "Unknown Artist", ["barcode_match"])["manual_check"]
    assert _row("strong", "Sleep Token", ["year_match", "label_match"])["manual_check"]
    assert not _row("exact", "Korn", ["barcode_match"])["manual_check"]


def test_thin_or_manual_rows_are_not_recommendation_eligible():
    assert _row("exact", "Korn", ["barcode_match"])["recommendation_eligible"] is True
    assert _row("exact", "Korn", ["barcode_match"], depth=1)["recommendation_eligible"] is False
    assert _row("strong", "Unknown Artist", ["barcode_match"])["recommendation_eligible"] is False
