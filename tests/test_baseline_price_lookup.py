"""price_lookup under Phase 1 strict matching.

Changed vs the baseline commit (intentional, per Phase 1):
  * discogs_search no longer returns results[0] for unrelated releases
  * cache entries need the strict-matcher schema to be reused
  * decision ladder thresholds are UNCHANGED for exact/strong matches
"""
import io
import json

import price_lookup as pl


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_urlopen(payload):
    def _open(req, timeout=0):
        return _Resp(json.dumps(payload).encode())
    return _open


def _entry(sell, status="exact", conf=0.95):
    return {"found": True, "schema": pl.CACHE_SCHEMA, "match_status": status,
            "match_confidence": conf, "match_reasons": ["catno_match"],
            "suggested_sell_price": sell, "lowest_price": sell, "release_id": 1,
            "discogs_url": "https://www.discogs.com/release/1",
            "cached_at": pl.datetime.now().isoformat()}


CFG = {"use_net_for_decisions": False,
       "fx": {"rates_to_usd": {"USD": 1.0}},
       "profiles": {"domestic_us": {"shipping": {"mode": "per_item", "amount_usd": 0.0},
                                    "sales_tax_pct": 0.0, "import_duty_pct": 0.0, "import_tax_pct": 0.0,
                                    "brokerage_flat_usd": 0.0, "purchase_fee_pct": 0.0,
                                    "purchase_fee_flat_usd": 0.0}},
       "resale": {"marketplace_fee_pct": 0.0, "payment_fee_pct": 0.0, "payment_fee_flat_usd": 0.0,
                  "outbound_shipping_usd": 0.0, "packaging_usd": 0.0}}


def _run(deal, entry, cfg=CFG):
    ident = pl.dm.extract_identifiers(deal)
    cache = {pl.cache_key(deal["artist"], deal["title"], ident): entry}
    return pl.enrich_deals_with_prices([deal], cache, cfg=cfg)[0]


# --- the old hazards, now closed -------------------------------------------

def test_unrelated_results_no_longer_accepted(monkeypatch):
    payload = {"results": [
        {"id": 111, "title": "Someone Else - Other Album"},
        {"id": 222, "title": "Another Person - Different Record"},
    ]}
    monkeypatch.setattr(pl.urllib.request, "urlopen", _fake_urlopen(payload))
    monkeypatch.setattr(pl.time, "sleep", lambda s: None)
    assert pl.discogs_search("Men At Work", "Business As Usual") is None


def test_cache_key_separates_pressings():
    jp = pl.dm.extract_identifiers({"artist": "Men At Work", "title": "Business As Usual",
                                    "catalog_number": "25·3P-379", "country": "Japan", "year": 1982})
    us = pl.dm.extract_identifiers({"artist": "Men At Work", "title": "Business As Usual",
                                    "catalog_number": "FC 37978", "country": "US", "year": 1982})
    assert pl.cache_key("Men At Work", "Business As Usual", jp) != pl.cache_key("Men At Work", "Business As Usual", us)
    assert pl.cache_key("A", "T") == "a::t"      # plain retail keys unchanged


def test_old_schema_cache_entries_are_not_trusted():
    old = {"found": True, "suggested_sell_price": 99.0, "cached_at": pl.datetime.now().isoformat()}
    assert pl.is_cache_fresh(old) is False
    assert pl.is_cache_fresh(_entry(10.0)) is True


# --- unchanged decision ladder (exact/strong matches) ----------------------

def test_decision_ladder_thresholds_unchanged():
    for sell, cost, want in [(30.0, 20.0, "BUY NOW"), (24.0, 20.0, "BUY LIGHT"),
                             (20.5, 20.0, "WATCH"), (15.0, 20.0, "PASS")]:
        out = _run({"artist": "A", "title": "T", "price": cost, "buy_score": 80}, _entry(sell))
        assert out["decision"] == want, (sell, cost)


# --- new Phase 1 behavior ---------------------------------------------------

def test_valuation_is_labelled_estimate_not_sold():
    out = _run({"artist": "A", "title": "T", "price": 20.0, "buy_score": 80}, _entry(30.0))
    assert out["valuation_is_estimate"] is True and out["valuation_verified_sold"] is False
    assert out["valuation_basis"] == "discogs_asking_price"
    assert "not verified sold" in out["valuation_label"]
    assert out["discogs_match_status"] == "exact" and out["discogs_found"] is True


def test_title_only_match_can_never_be_buy_now():
    out = _run({"artist": "A", "title": "T", "price": 20.0, "buy_score": 80},
               _entry(60.0, status="title_only", conf=0.5))
    assert out["decision"] == "BUY LIGHT"
    assert "not verified" in out["decision_note"]


def test_ambiguous_or_unmatched_applies_no_valuation():
    for status in ("ambiguous", "none"):
        deal = {"artist": "A", "title": "T", "price": 20.0, "buy_score": 80,
                "suggested_sale_price": 27.99, "decision": "BUY NOW"}
        entry = {"found": False, "schema": pl.CACHE_SCHEMA, "match_status": status,
                 "cached_at": pl.datetime.now().isoformat()}
        out = _run(deal, entry)
        assert "discogs_sell_price" not in out
        assert out["suggested_sale_price"] == 27.99 and out["decision"] == "BUY NOW"  # Brain untouched
        assert out["discogs_match_status"] == status


def test_net_profit_fields_added_without_changing_gross_margin():
    cfg = json.loads(json.dumps(CFG))
    cfg["resale"].update(marketplace_fee_pct=10.0, outbound_shipping_usd=3.0)
    out = _run({"artist": "A", "title": "T", "price": 20.0, "buy_score": 80}, _entry(40.0), cfg)
    assert out["expected_margin_dollars"] == 20.0                # gross, as before
    assert out["landed_cost_usd"] == 20.0
    assert out["net_profit_usd"] == 40.0 - 4.0 - 3.0 - 20.0 == 13.0
    assert out["roi_percent"] == 65.0 and out["cost_inputs_complete"] is True


def test_net_thresholds_only_apply_when_enabled():
    cfg = json.loads(json.dumps(CFG))
    cfg["resale"]["outbound_shipping_usd"] = 12.0                # eats the profit
    cfg["decision"] = {"min_net_profit_usd": 5.0, "min_roi_percent": 25.0}
    deal = {"artist": "A", "title": "T", "price": 20.0, "buy_score": 80}
    assert _run(dict(deal), _entry(30.0), cfg)["decision"] == "BUY NOW"          # disabled: unchanged
    cfg["use_net_for_decisions"] = True
    assert _run(dict(deal), _entry(30.0), cfg)["decision"] == "WATCH"


def test_lookup_deal_end_to_end_with_fake_discogs(monkeypatch):
    jp = {"id": 1001, "title": "Men At Work - Business As Usual", "year": "1982", "country": "Japan",
          "label": ["Epic"], "catno": "25·3P-379", "format": ["Vinyl", "LP"], "uri": "/release/1001"}
    us = dict(jp, id=1002, country="US", label=["Columbia"], catno="FC 37978")
    monkeypatch.setattr(pl, "discogs_price_stats", lambda rid: {
        "release_id": rid, "suggested_sell_price": 25.0, "lowest_price": 20.0,
        "discogs_url": "https://www.discogs.com/release/%d" % rid})
    monkeypatch.setattr(pl.time, "sleep", lambda s: None)
    deal = {"artist": "Men At Work", "title": "Business As Usual", "catalog_number": "25·3P-379",
            "label": "Epic", "country": "Japan", "year": 1982, "price": 20.0}
    cache = {}
    entry = pl.lookup_deal(deal, cache, http_get=lambda params: {"results": [us, jp]})
    assert entry["found"] and entry["release_id"] == 1001 and entry["match_status"] == "exact"
    # Only the US pressing exists -> nothing valued, never the wrong pressing.
    cache2 = {}
    entry2 = pl.lookup_deal(deal, cache2, http_get=lambda params: {"results": [us]})
    assert entry2["found"] is False and entry2["match_status"] == "none"


def test_one_failing_lookup_does_not_stop_the_run(monkeypatch):
    def boom(deal, cache, http_get=None):
        if deal["title"] == "Bad":
            raise RuntimeError("discogs exploded")
        return _entry(30.0)
    monkeypatch.setattr(pl, "lookup_deal", boom)
    deals = [{"artist": "A", "title": "Bad", "price": 10.0, "buy_score": 90},
             {"artist": "A", "title": "Good", "price": 10.0, "buy_score": 80}]
    out = pl.enrich_deals_with_prices(deals, {}, cfg=CFG)
    assert out[1].get("discogs_found") is True and "discogs_found" not in out[0]


def test_runtime_budget_stops_cleanly(monkeypatch):
    monkeypatch.setattr(pl, "MAX_RUNTIME_SECONDS", -1)           # budget already exhausted
    called = []
    monkeypatch.setattr(pl, "lookup_deal", lambda d, c, h=None: called.append(1) or _entry(30.0))
    out = pl.enrich_deals_with_prices([{"artist": "A", "title": "T", "price": 10.0, "buy_score": 90}], {}, cfg=CFG)
    assert called == [] and "discogs_found" not in out[0]
