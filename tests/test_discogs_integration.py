"""Phase 1: the cache-builder Discogs path (discogs_integration.py) is strict too."""
import discogs_integration as di

JP = {"id": 1001, "title": "Men At Work - Business As Usual", "year": "1982", "country": "Japan",
      "label": ["Epic"], "catno": "25·3P-379", "format": ["Vinyl", "LP"], "uri": "/release/1001"}
US = dict(JP, id=1002, country="US", label=["Columbia"], catno="FC 37978", uri="/release/1002")
JUNK = {"id": 9, "title": "Someone Else - Other Album", "year": "2001", "country": "US",
        "label": ["X"], "catno": "X1", "format": ["Vinyl", "LP"], "uri": "/release/9"}

DEAL = {"artist": "Men At Work", "title": "Business As Usual", "catalog_number": "25·3P-379",
        "label": "Epic", "country": "Japan", "year": 1982, "price": 20.0}


def _patch(monkeypatch, results):
    monkeypatch.setattr(di, "discogs_get", lambda path, params=None:
                        {"results": results} if path == "/database/search" else {})
    monkeypatch.setattr(di, "_stale_relookups", 0)


def test_exact_pressing_found_and_labeled(monkeypatch):
    _patch(monkeypatch, [JUNK, US, JP])
    out = di.enrich_with_discogs(dict(DEAL), {})
    assert out["discogs_found"] and out["discogs_release_id"] == 1001
    assert out["discogs_match_status"] == "exact"
    assert out["valuation_is_estimate"] is True and out["valuation_verified_sold"] is False


def test_japan_pressing_never_valued_against_us_pressing(monkeypatch):
    _patch(monkeypatch, [US, JUNK])
    out = di.enrich_with_discogs(dict(DEAL), {})
    assert out["discogs_found"] is False and out["discogs_match_status"] == "none"


def test_unrelated_first_result_is_not_accepted(monkeypatch):
    _patch(monkeypatch, [JUNK])
    out = di.enrich_with_discogs({"artist": "Men At Work", "title": "Business As Usual"}, {})
    assert out["discogs_found"] is False


def test_pressing_specific_cache_key(monkeypatch):
    _patch(monkeypatch, [JP])
    cache = {}
    di.enrich_with_discogs(dict(DEAL), cache)
    di.enrich_with_discogs({"artist": "Men At Work", "title": "Business As Usual"}, cache)
    assert len(cache) == 2                                   # not one shared slot


def test_stale_cache_entry_is_relooked_up_within_budget(monkeypatch):
    _patch(monkeypatch, [JP])
    key = "men at work|business as usual|cat=253P379|lbl=epic|cty=japan|yr=1982"
    cache = {key: {"discogs_found": True, "discogs_release_id": 1002, "discogs_url": "wrong"}}
    out = di.enrich_with_discogs(dict(DEAL), cache)
    assert out["discogs_release_id"] == 1001 and cache[key]["matcher_schema"] == di.MATCHER_SCHEMA


def test_stale_entries_beyond_budget_are_not_trusted(monkeypatch):
    _patch(monkeypatch, [JP])
    monkeypatch.setattr(di, "STALE_RELOOKUP_BUDGET", 0)
    key = "men at work|business as usual|cat=253P379|lbl=epic|cty=japan|yr=1982"
    cache = {key: {"discogs_found": True, "discogs_release_id": 1002}}
    out = di.enrich_with_discogs(dict(DEAL), cache)
    assert out["discogs_found"] is False and out["discogs_match_reason"] == "stale_cache_pending_refresh"
