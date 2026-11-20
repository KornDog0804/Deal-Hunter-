import copy
import landed_cost as lc

CFG = lc.load_config()


def cfg_with(provider_rule, default=None):
    c = copy.deepcopy(CFG)
    c["inbound_shipping"] = {"default": default or {"flat_usd": None, "per_additional_usd": 0.0, "free_over_usd": None},
                             "providers": {"Store A": provider_rule}}
    c["profiles"]["domestic_us"]["sales_tax_pct"] = 0.0
    return c


def test_unknown_provider_shipping_is_flagged_missing():
    r = lc.estimate_net_profit(20.0, 40.0, cfg=cfg_with({"flat_usd": None}), provider="Store A")
    assert r["inbound_shipping_basis"] == "profile" or r["inbound_shipping_basis"] == "unknown"
    assert "shipping.amount_usd" in r["missing_inputs"]


def test_flat_rate_applies():
    r = lc.estimate_net_profit(20.0, 40.0, cfg=cfg_with({"flat_usd": 5.0}), provider="Store A")
    assert r["cost_components"]["shipping_usd"] == 5.0 and "shipping.amount_usd" not in r["missing_inputs"]


def test_free_shipping_threshold_single_item():
    r = lc.estimate_net_profit(60.0, 90.0, cfg=cfg_with({"flat_usd": 5.0, "free_over_usd": 50.0}), provider="Store A")
    assert r["cost_components"]["shipping_usd"] == 0.0 and r["inbound_shipping_basis"] == "free_threshold"


def test_combined_order_can_cross_free_threshold_and_ships_once():
    cfg = cfg_with({"flat_usd": 5.0, "free_over_usd": 50.0})
    items = [{"price": 30.0, "resale": 60.0}, {"price": 30.0, "resale": 60.0}]
    one = lc.estimate_net_profit(30.0, 60.0, cfg=cfg, provider="Store A")
    both = lc.estimate_order_profit(items, cfg, provider="Store A")
    assert one["cost_components"]["shipping_usd"] == 5.0
    assert both["inbound_shipping_basis"] == "free_threshold"
    assert both["landed_cost_usd"] == 60.0            # no shipping at all on the $60 order


def test_combined_order_without_threshold_pays_once():
    cfg = cfg_with({"flat_usd": 5.0})
    both = lc.estimate_order_profit([{"price": 30.0, "resale": 60.0}, {"price": 30.0, "resale": 60.0}], cfg, provider="Store A")
    assert both["landed_cost_usd"] == 65.0


def test_cost_certainty_lists_missing():
    r = lc.estimate_net_profit(20.0, 40.0, cfg=cfg_with({"flat_usd": None}), provider="Store A")
    assert "shipping.amount_usd" in r["cost_certainty"]["missing"]
    assert any("Lowest Asking" in x for x in r["cost_certainty"]["estimated"])


def test_shipped_config_lists_all_42_providers():
    assert len(CFG["inbound_shipping"]["providers"]) == 42
