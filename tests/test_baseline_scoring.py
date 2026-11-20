"""BASELINE: stage-2 scoring, dedupe and Buyer Brain outputs must not drift.

Digests were captured from the pre-change code over the committed live_deals.json
(2,569 deals). Phase 1 must leave these byte-for-byte identical.
"""
import hashlib
import json

import buyer_brain as bb
import live_pull as lp

STAGE2_DIGEST = "c1de0c68a30a6824c8f1da7ba99df86a944916a1dda2d94e83b8b10829ccf81a"
BRAIN_DIGEST = "5ff35dc4e64e9364e0e0fa14eb42fee420d4475e7776251b8b2da6a8c3b1cef9"

SAMPLE = {
    "artist": "Test Band",
    "title": "Test Album (Splatter Vinyl) Limited Exclusive",
    "raw_title": "Test Band - Test Album (Splatter Vinyl) Limited Exclusive",
    "price": 18.99, "source": "Rollin Records", "source_type": "shopify_store",
    "version": "splatter", "link": "https://x.com/p/1",
}


def _deals():
    return json.load(open("live_deals.json"))


def test_score_deal_golden():
    assert lp.score_deal(SAMPLE) == (84, ["exclusive", "limited", "splatter", "under-$20"])


def test_release_key_golden():
    assert lp.release_key_for(SAMPLE) == "test band::test album splatter limited exclusive"


def test_stage2_digest_over_real_deals():
    deduped = lp.dedupe_deals([dict(d) for d in _deals()])
    enriched = lp.enrich_deals(deduped)
    rows = [(x.get("release_key"), x.get("score"), tuple(x.get("signals", [])),
             x.get("deal_quality")) for x in enriched]
    assert len(enriched) == 2569
    assert hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest() == STAGE2_DIGEST


def test_buyer_brain_digest_over_real_deals():
    enriched = lp.enrich_deals(lp.dedupe_deals([dict(d) for d in _deals()]))
    rows = []
    for x in enriched[:300]:
        y = bb.enrich_deal(dict(x))
        rows.append((y.get("buy_score"), y.get("decision"),
                     y.get("suggested_sale_price"), y.get("expected_margin_dollars")))
    assert hashlib.sha256(json.dumps(rows, default=str).encode()).hexdigest() == BRAIN_DIGEST


def test_buyer_brain_sample_golden():
    y = bb.enrich_deal(dict(SAMPLE))
    assert (y["inventory_lane"], y["suggested_sale_price"], y["expected_margin_dollars"],
            y["buy_score"], y["decision"]) == ("Trend / Hype", 31.99, 13.0, 93, "BUY NOW")


def test_dedupe_collapses_same_url_keeps_cheapest():
    a = dict(SAMPLE, price=20.0, link="https://x.com/p/1?utm=a")
    b = dict(SAMPLE, price=15.0, link="https://x.com/p/1")
    out = lp.dedupe_deals([a, b])
    assert len(out) == 1 and out[0]["price"] == 15.0
