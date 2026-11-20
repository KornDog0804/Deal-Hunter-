"""Phase 1: landed cost, fees, net profit, ROI."""
import landed_cost as lc

CFG = {
    "fx": {"rates_to_usd": {"USD": 1.0, "JPY": 0.0070}, "buffer_pct": 2.0},
    "profiles": {
        "domestic_us": {"shipping": {"mode": "per_item", "amount_usd": 4.0}, "sales_tax_pct": 0.0,
                        "import_duty_pct": 0.0, "import_tax_pct": 0.0, "brokerage_flat_usd": 0.0,
                        "purchase_fee_pct": 0.0, "purchase_fee_flat_usd": 0.0},
        "international": {"shipping": {"mode": "per_order_allocated", "order_shipping_usd": 12.0,
                                       "order_total_usd": 60.0, "allocation": "by_price"},
                          "sales_tax_pct": 0.0, "import_duty_pct": 5.0, "import_tax_pct": 0.0,
                          "brokerage_flat_usd": 2.0, "purchase_fee_pct": 3.0, "purchase_fee_flat_usd": 0.0},
    },
    "resale": {"marketplace_fee_pct": 10.0, "payment_fee_pct": 3.0, "payment_fee_flat_usd": 0.5,
               "outbound_shipping_usd": 5.0, "packaging_usd": 1.0, "assumed": []},
}


def test_usd_item_with_known_shipping():
    r = lc.compute_landed_cost(20.0, "USD", CFG, "domestic_us")
    assert r["landed_cost_usd"] == 24.0 and r["missing_inputs"] == []


def test_yen_converted_with_fx_buffer():
    r = lc.compute_landed_cost(2980, "JPY", CFG, "domestic_us")
    assert r["components"]["item_usd"] == round(2980 * 0.0070 * 1.02, 2)


def test_missing_fx_rate_is_reported_not_guessed():
    cfg = {"fx": {"rates_to_usd": {"USD": 1.0, "JPY": None}}, "profiles": CFG["profiles"]}
    r = lc.compute_landed_cost(2980, "JPY", cfg, "domestic_us")
    assert "fx_rate:JPY" in r["missing_inputs"] and r["components"]["item_usd"] == 0.0


def test_shipping_has_no_hidden_default():
    cfg = {"fx": CFG["fx"], "profiles": {"domestic_us": {"shipping": {"mode": "per_item", "amount_usd": None}}}}
    r = lc.compute_landed_cost(10.0, "USD", cfg, "domestic_us")
    assert "shipping.amount_usd" in r["missing_inputs"]


def test_combined_order_shipping_allocated_by_price():
    # $20 of a $60 order carries one third of the $12 quote.
    r = lc.compute_landed_cost(20.0, "USD", CFG, "international")
    assert r["components"]["shipping_usd"] == 4.0
    assert r["components"]["import_duty_usd"] == round((20.0 + 4.0) * 0.05, 2)
    assert r["components"]["purchase_fee_usd"] == 0.6
    assert r["components"]["brokerage_usd"] == 2.0


def test_equal_allocation_and_missing_count():
    cfg = {"fx": CFG["fx"], "profiles": {"x": {"shipping": {"mode": "per_order_allocated",
           "order_shipping_usd": 9.0, "allocation": "equal", "item_count": 3}}}}
    assert lc.compute_landed_cost(10.0, "USD", cfg, "x")["components"]["shipping_usd"] == 3.0
    cfg["profiles"]["x"]["shipping"]["item_count"] = None
    assert "shipping.item_count" in lc.compute_landed_cost(10.0, "USD", cfg, "x")["missing_inputs"]


def test_net_profit_and_roi():
    r = lc.estimate_net_profit(20.0, 50.0, "USD", CFG, "domestic_us")
    fees = 50 * 0.10 + 50 * 0.03 + 0.5          # 7.0
    assert r["resale_fees_usd"] == 7.0 and r["outbound_costs_usd"] == 6.0
    assert r["net_profit_usd"] == round(50 - fees - 6.0 - 24.0, 2) == 13.0
    assert r["roi_percent"] == round(13.0 / 24.0 * 100, 1)
    assert r["inputs_complete"] is True
    assert "not verified sold" in r["valuation_basis"]


def test_incomplete_inputs_flag_result():
    cfg = dict(CFG, resale=dict(CFG["resale"], outbound_shipping_usd=None))
    r = lc.estimate_net_profit(20.0, 50.0, "USD", cfg, "domestic_us")
    assert r["inputs_complete"] is False and "resale.outbound_shipping_usd" in r["missing_inputs"]


def test_default_config_file_loads_and_flags_unset_inputs():
    cfg = lc.load_config()
    r = lc.estimate_net_profit(2980, 40.0, "JPY", cfg, "international")
    assert r["inputs_complete"] is False
    assert "fx_rate:JPY" in r["missing_inputs"]
    assert cfg["use_net_for_decisions"] is False


def test_thresholds():
    good = {"net_profit_usd": 10.0, "roi_percent": 40.0}
    assert lc.passes_net_thresholds(good, {"decision": {"min_net_profit_usd": 5, "min_roi_percent": 25}})
    assert not lc.passes_net_thresholds({"net_profit_usd": 2.0, "roi_percent": 40.0},
                                        {"decision": {"min_net_profit_usd": 5, "min_roi_percent": 25}})
