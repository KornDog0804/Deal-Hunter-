import copy, json
import landed_cost as lc
from scripts import recompute_results as rr


def test_recompute_applies_provider_shipping_and_keeps_discogs_fields():
    cfg = copy.deepcopy(lc.load_config())
    cfg["profiles"]["domestic_us"]["sales_tax_pct"] = 0.0
    row = {"source": "Rock Metal Fan Nation", "price": 30.0, "resale": 80.0, "verified": True, "market_depth": 10,
           "status": "exact", "release_id": 5, "manual_check": []}
    out = rr.recompute_rows([dict(row)], cfg)[0]
    assert out["release_id"] == 5 and out["landed"] == 37.99 and out["cost_status"] == "complete"
    assert out["recommendation_eligible"] is True


def test_recompute_flags_thin_and_incomplete():
    cfg = lc.load_config()
    out = rr.recompute_rows([{"source": "Rhino", "price": 30.0, "resale": 80.0, "verified": True,
                              "market_depth": 1, "manual_check": []}], cfg)[0]
    assert out["thin_market"] and not out["recommendation_eligible"] and out["cost_status"] == "incomplete"
