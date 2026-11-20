"""BASELINE: documents how price_lookup behaves BEFORE Phase 1.

The two `legacy_*` tests pin the hazards Phase 1 removes (first-result fallback,
cache keyed by artist+title only). They are rewritten in the Phase 1 commit.
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


def test_legacy_first_result_fallback_accepts_unrelated_release(monkeypatch):
    # Discogs returns two UNRELATED releases. Old code still returns the first id.
    payload = {"results": [
        {"id": 111, "title": "Someone Else - Other Album"},
        {"id": 222, "title": "Another Person - Different Record"},
    ]}
    monkeypatch.setattr(pl.urllib.request, "urlopen", _fake_urlopen(payload))
    assert pl.discogs_search("Men At Work", "Business As Usual") == 111  # HAZARD


def test_legacy_cache_key_ignores_pressing_identity():
    # A Japan pressing and a US pressing of the same title share one cache slot.
    assert pl.cache_key("Men At Work", "Business As Usual") == pl.cache_key("Men At Work", "Business As Usual")


def _entry(sell, found=True):
    return {"found": found, "suggested_sell_price": sell, "lowest_price": sell,
            "discogs_url": "https://www.discogs.com/release/1"}


def test_decision_ladder_thresholds(monkeypatch):
    cases = [(30.0, 20.0, "BUY NOW"), (24.0, 20.0, "BUY LIGHT"),
             (20.5, 20.0, "WATCH"), (15.0, 20.0, "PASS")]
    for sell, cost, want in cases:
        deal = {"artist": "A", "title": "T", "price": cost, "buy_score": 80}
        cache = {pl.cache_key("A", "T"): dict(_entry(sell), cached_at=pl.datetime.now().isoformat())}
        out = pl.enrich_deals_with_prices([deal], cache)
        assert out[0]["decision"] == want, (sell, cost)
