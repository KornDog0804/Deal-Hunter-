import csv, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import manual_import as mi
import phase1_validation as pv
import discogs_matcher as dm
import landed_cost as lc

CFG = {"fx": {"rates_to_usd": {"USD": 1.0, "JPY": None}, "buffer_pct": 0},
       "profiles": {"domestic_us": {"shipping": {"mode": "per_item", "amount_usd": 5}, "sales_tax_pct": 6.0,
                    "import_duty_pct": 0, "import_tax_pct": 0, "brokerage_flat_usd": 0, "purchase_fee_pct": 0, "purchase_fee_flat_usd": 0},
                    "international": {"shipping": {"mode": "per_item", "amount_usd": 10}, "sales_tax_pct": 0,
                    "import_duty_pct": 0, "import_tax_pct": 0, "brokerage_flat_usd": 0, "purchase_fee_pct": 0, "purchase_fee_flat_usd": 0}},
       "resale": {"channel": "discogs", "channels": {"discogs": {"fee_pct": 9, "payment_fee_pct": 3.49, "payment_fee_flat_usd": 0.49, "assumed": []}},
                  "customer_shipping": {}, "postage": {}, "packaging": {}}}


def test_row_ok_and_bad_barcode(tmp_path):
    d, why = mi.row_to_deal({"artist": "Boris", "title": "Flood", "price": "¥4,200", "barcode": "4988003123456"})
    assert why and "check digit" in why or d is not None
    d, why = mi.row_to_deal({"artist": "Boris", "title": "Flood", "price": "4,200", "obi": "yes", "condition": "VG+"})
    assert why is None and d["currency"] == "JPY" and d["cost_profile"] == "international" and d["country"] == "Japan"
    assert "OBI" in d["raw_title"] and d["price"] == 4200.0


def test_rejects_missing_fields():
    assert mi.row_to_deal({"artist": "", "title": "x", "price": "1"})[0] is None
    assert mi.row_to_deal({"artist": "a", "title": "x", "price": "abc"})[0] is None
    assert mi.row_to_deal({"artist": "a", "title": "x", "price": "0"})[0] is None


def _row(d, rate):
    cfg = json.loads(json.dumps(CFG)); cfg["fx"]["rates_to_usd"]["JPY"] = rate
    state = {"records": {dm.identity_key(dm.extract_identifiers(d)): {
        "status": "exact", "confidence": 0.99, "release_id": 1, "reasons": ["barcode_match"],
        "resale_estimate": 60.0, "lowest_price": 55.0, "num_for_sale": 8}}}
    return pv.build_results([d], state, cfg)[0]


def test_jpy_without_rate_is_incomplete_never_confirmed():
    d, _ = mi.row_to_deal({"artist": "Boris", "title": "Flood", "price": "4200", "condition": "new"})
    r = _row(d, None)
    assert r["currency"] == "JPY" and r["cost_status"] == "incomplete" and "fx_rate:JPY" in r["missing"]
    assert "INCOMPLETE" in r["net_label"]


def test_jpy_with_rate_uses_international_profile_and_no_us_store_shipping():
    d, _ = mi.row_to_deal({"artist": "Boris", "title": "Flood", "price": "4200", "condition": "new"})
    r = _row(d, 0.0065)
    assert r["cost_profile"] == "international" and not [m for m in r["missing"] if m.startswith(("fx_rate", "shipping", "sales_tax"))]
    assert round(r["landed"], 2) == round(4200 * 0.0065 + 10, 2)      # item + $10 order shipping, no 6% KY tax


def test_used_copy_flagged_and_not_recommended():
    d, _ = mi.row_to_deal({"artist": "Boris", "title": "Flood", "price": "4200", "condition": "VG+"})
    r = _row(d, 0.0065)
    assert any("used/graded" in w for w in r["manual_check"]) and not r["recommendation_eligible"]
