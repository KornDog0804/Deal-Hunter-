import copy, landed_cost as lc

def cfg():
    c = copy.deepcopy(lc.load_config())
    c["profiles"]["domestic_us"]["shipping"]["amount_usd"] = 0.0
    c["profiles"]["domestic_us"]["sales_tax_pct"] = 0.0
    return c

def test_customer_shipping_tiers():
    c = cfg()
    for n, want in [(1, 7.99), (3, 7.99), (4, 8.49), (5, 8.99)]:
        r = lc.compute_resale_costs(40, c, n_records=n)
        assert r["buyer_paid_shipping_usd"] == want

def test_postage_packaging_independent():
    c = cfg(); c["resale"]["postage"]["base_usd"] = 9.0
    r = lc.compute_resale_costs(40, c)
    assert (r["postage_usd"], r["packaging_usd"], r["outbound_costs_usd"]) == (9.0, 1.5, 10.5)
    c["resale"]["packaging"]["base_usd"] = 0.0
    assert lc.compute_resale_costs(40, c)["outbound_costs_usd"] == 9.0

def test_extra_record_postage_flagged_only_over_included():
    c = cfg()
    assert "resale.postage.per_additional_record_usd" not in lc.compute_resale_costs(40, c, n_records=3)["missing_inputs"]
    assert "resale.postage.per_additional_record_usd" in lc.compute_resale_costs(40, c, n_records=4)["missing_inputs"]

def test_single_record_math_by_hand():
    c = cfg()
    r = lc.estimate_net_profit(20, 40, "USD", c, "domestic_us")
    paid = 40 + 7.99
    fees = paid * 0.09 + paid * 0.0349 + 0.49           # marketplace + payment, each once
    want = 40 + 7.99 - fees - 7.0 - 1.5 - 20
    assert abs(r["net_profit_usd"] - want) < 0.02

def test_combined_beats_singles_via_shared_costs():
    c = cfg()
    items = [{"price": 20, "resale": 40}] * 3
    order = lc.estimate_order_profit(items, c)
    single = lc.estimate_net_profit(20, 40, "USD", c, "domestic_us")["net_profit_usd"]
    assert order["records"] == 3 and order["net_profit_usd"] > 3 * single   # one postage/box/flat fee
    assert order["buyer_paid_shipping_usd"] == 7.99 and order["postage_usd"] == 7.0

def test_inbound_shipping_charged_once_per_purchase():
    c = cfg(); c["profiles"]["domestic_us"]["shipping"]["amount_usd"] = 6.0
    order = lc.estimate_order_profit([{"price": 20, "resale": 40}] * 2, c)
    assert order["landed_cost_usd"] == 46.0
