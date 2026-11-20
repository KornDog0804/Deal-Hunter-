import likely_tier as lt, price_lookup as pl, discogs_matcher as dm, landed_cost as lc

def test_floor_is_minimum_and_flags_wide_spread():
    f = lt.floor_estimate({1: 30.0, 2: 45.0, 3: None, 4: 0})
    assert f["floor"] == 30.0 and f["count"] == 2 and not f["wide"]
    assert lt.floor_estimate({1: 20.0, 2: 55.0})["wide"] is True
    assert lt.floor_estimate({1: None}) is None

def _cand(i, year):
    return {"id": i, "title": "Beastie Boys - Licensed to Ill", "year": str(year), "country": "US",
            "format": ["Vinyl", "LP"], "formats": [{"name": "Vinyl", "qty": "1"}], "label": ["Def Jam"], "catno": "X%d" % i}

def test_ambiguous_album_gets_floor_valuation_and_cannot_buy_now(monkeypatch):
    deal = {"artist": "Beastie Boys", "title": "Licensed to Ill 1LP", "price": 20.0, "format": "vinyl",
            "decision": "BUY NOW", "source": "S", "link": "l"}
    http = lambda params: {"results": [_cand(1, 1986), _cand(2, 1986)]}
    prices = {1: 31.0, 2: 48.0}
    entry = pl.lookup_deal(deal, {}, http_get=http, ask_fetcher=lambda rid: prices[rid])
    assert entry["match_status"] == "ambiguous" and entry["tier"] == "likely"
    assert entry["suggested_sell_price"] == 31.0                     # floor, not 48
    d = dict(deal); pl._apply_valuation(d, entry, lc.load_config())
    assert d["valuation_tier"] == "likely" and d["valuation_label"] == lt.LIKELY_LABEL
    assert d["decision"] != "BUY NOW"                                # unverified can never be BUY NOW
    assert d["valuation_is_estimate"] is True and d["valuation_verified_sold"] is False

def test_ambiguous_with_no_prices_is_not_valued():
    deal = {"artist": "Beastie Boys", "title": "Licensed to Ill", "price": 20.0, "format": "vinyl"}
    http = lambda params: {"results": [_cand(1, 1986), _cand(2, 1986)]}
    entry = pl.lookup_deal(deal, {}, http_get=http, ask_fetcher=lambda rid: None)
    assert entry["found"] is False
