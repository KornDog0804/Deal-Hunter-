"""Validation items 9-11: BUY NOW safety, net-profit test mode, stale inventory."""
import json
from datetime import datetime, timedelta, timezone

import decision_gate as dg
import landed_cost as lc
import live_pull as lp
import price_lookup as pl

FULL_COST = {"fx": {"rates_to_usd": {"USD": 1.0}},
             "profiles": {"domestic_us": {"shipping": {"mode": "per_item", "amount_usd": 3.0},
                                          "sales_tax_pct": 0.0, "import_duty_pct": 0.0, "import_tax_pct": 0.0,
                                          "brokerage_flat_usd": 0.0, "purchase_fee_pct": 0.0,
                                          "purchase_fee_flat_usd": 0.0}},
             "resale": {"marketplace_fee_pct": 9.0, "payment_fee_pct": 3.49, "payment_fee_flat_usd": 0.49,
                        "fee_base": "item_plus_shipping", "buyer_paid_shipping_usd": 4.0,
                        "outbound_shipping_usd": 4.0, "packaging_usd": 1.0},
             "decision": {"min_net_profit_usd": 5.0, "min_roi_percent": 25.0},
             "decision_safety": {"enforce_buy_now_gate": False}}


def _entry(sell, status):
    return {"found": True, "schema": pl.CACHE_SCHEMA, "match_status": status, "match_confidence": 0.9,
            "match_reasons": [], "suggested_sell_price": sell, "lowest_price": sell, "release_id": 1,
            "discogs_url": "u", "cached_at": datetime.now().isoformat()}


def _run(deal, entry, cfg):
    cache = {pl.cache_key(deal["artist"], deal["title"], pl.dm.extract_identifiers(deal)): entry}
    return pl.enrich_deals_with_prices([deal], cache, cfg=cfg)[0]


# ---- fee model: official numbers, nothing double counted --------------------

def test_fees_applied_once_with_buyer_shipping_credit():
    r = lc.estimate_net_profit(20.0, 50.0, "USD", FULL_COST, "domestic_us")
    total_paid = 50.0 + 4.0
    mkt = round(total_paid * 0.09, 2)                       # 4.86, once
    pay = round(total_paid * 0.0349 + 0.49, 2)              # 2.37, once, separate charge
    assert r["marketplace_fee_usd"] == mkt and r["payment_fee_usd"] == pay
    assert r["resale_fees_usd"] == round(mkt + pay, 2)
    # revenue: item + buyer-paid shipping; costs: landed (20+3), fees, postage 4 + packaging 1
    assert r["net_profit_usd"] == round(50 + 4 - mkt - pay - 5.0 - 23.0, 2)


def test_marketplace_fee_respects_min_and_max():
    cfg = json.loads(json.dumps(FULL_COST))
    cfg["resale"].update(marketplace_fee_pct=9.0, marketplace_fee_min_usd=0.10, marketplace_fee_max_usd=150.0,
                         buyer_paid_shipping_usd=0.0)
    assert lc.compute_resale_costs(5000.0, cfg)["marketplace_fee_usd"] == 150.0
    assert lc.compute_resale_costs(0.50, cfg)["marketplace_fee_usd"] == 0.10


def test_channel_switch_removes_marketplace_fee():
    cfg = lc.load_config()                                  # real shipped config
    d = lc.compute_resale_costs(40.0, cfg, channel="discogs")["marketplace_fee_usd"]
    o = lc.compute_resale_costs(40.0, cfg, channel="own_site")["marketplace_fee_usd"]
    assert d > 0 and o == 0.0


def test_shipped_config_uses_paypal_published_rate():
    ch = lc.load_config()["resale"]["channels"]["discogs"]
    assert ch["payment_fee_pct"] == 3.49 and ch["payment_fee_flat_usd"] == 0.49


# ---- item 9: net-profit thresholds in isolated test mode ---------------------

def test_env_override_selects_isolated_config(monkeypatch, tmp_path):
    f = tmp_path / "test_cost.json"
    f.write_text(json.dumps(dict(FULL_COST, use_net_for_decisions=True)))
    monkeypatch.setenv("DEAL_HUNTER_COST_CONFIG", str(f))
    assert lc.load_config()["use_net_for_decisions"] is True
    monkeypatch.delenv("DEAL_HUNTER_COST_CONFIG")
    assert lc.load_config()["use_net_for_decisions"] is False   # shipped config untouched


def test_net_threshold_matrix_in_test_mode():
    cfg = dict(json.loads(json.dumps(FULL_COST)), use_net_for_decisions=True)
    base = {"artist": "A", "title": "T", "buy_score": 80}
    # (cost, sell, expected decision)
    for cost, sell, want in [(10.0, 60.0, "BUY NOW"),     # big net + ROI
                             (30.0, 41.0, "WATCH"),       # gross +11 but net/ROI below threshold
                             (30.0, 28.0, "PASS")]:       # negative gross margin
        out = _run(dict(base, price=cost), _entry(sell, "exact"), cfg)
        assert out["decision"] == want, (cost, sell, out["decision"], out.get("net_profit_usd"))


# ---- item 10: no misleading BUY NOW -----------------------------------------

def test_unverified_pressing_never_buy_now_even_if_profitable():
    out = _run({"artist": "A", "title": "T", "price": 10.0, "buy_score": 80}, _entry(80.0, "title_only"), FULL_COST)
    assert out["decision"] != "BUY NOW"


def test_ambiguous_listing_reports_blockers_and_enforced_gate_downgrades():
    deal = {"artist": "A", "title": "T", "price": 10.0, "decision": "BUY NOW", "buy_score": 90,
            "discogs_match_status": "ambiguous"}
    cfg = dict(FULL_COST, decision_safety={"enforce_buy_now_gate": True})
    dg.apply_gate(deal, cfg)
    assert deal["decision"] == "WATCH" and "no_discogs_valuation(ambiguous)" in deal["buy_now_blockers"]
    assert deal["decision_before_gate"] == "BUY NOW"


def test_gate_is_report_only_by_default():
    deal = {"artist": "A", "title": "T", "price": 10.0, "decision": "BUY NOW"}
    dg.apply_gate(deal, FULL_COST)
    assert deal["decision"] == "BUY NOW" and deal["buy_now_gate_pass"] is False


def test_missing_cost_inputs_and_price_block_buy_now():
    cfg = json.loads(json.dumps(FULL_COST))
    cfg["resale"]["outbound_shipping_usd"] = None               # unset -> incomplete
    out = _run({"artist": "A", "title": "T", "price": 10.0, "buy_score": 80}, _entry(60.0, "exact"), cfg)
    assert out["cost_inputs_complete"] is False and "cost_inputs_incomplete" in out["buy_now_blockers"]
    no_price = {"artist": "A", "title": "T", "price": 0, "decision": "BUY NOW"}
    assert "price_missing" in dg.blockers(no_price, FULL_COST)


def test_fully_verified_deal_passes_the_gate():
    out = _run({"artist": "A", "title": "T", "price": 10.0, "buy_score": 80}, _entry(60.0, "exact"), FULL_COST)
    assert out["buy_now_gate_pass"] is True and out["buy_now_blockers"] == []


def test_stale_inventory_blocked():
    assert "stale_inventory" in dg.blockers({"price": 10, "stale_inventory": True}, FULL_COST)


# ---- item 11: failed provider keeps last good inventory ---------------------

def _prev(tmp_path, deals):
    (tmp_path / "live_deals.json").write_text(json.dumps(deals))


def _src(n):
    return {"name": n, "source_type": "shopify_store", "url": "https://x.invalid"}


def test_failed_provider_inventory_is_carried_forward_and_flagged(monkeypatch, tmp_path):
    prev = [{"source": "Broken", "artist": "A", "title": "T1", "price": 9.0, "link": "l1"},
            {"source": "Healthy", "artist": "B", "title": "T2", "price": 9.0, "link": "l2"}]
    _prev(tmp_path, prev)
    monkeypatch.setattr(lp, "SOURCES", [_src("Broken"), _src("Healthy")])
    monkeypatch.setattr(lp, "FAILED_SOURCES", ["Broken"])
    monkeypatch.setattr(lp, "SOURCE_STATUS", {"Broken": "FAILED: x"})
    fresh = [{"source": "Healthy", "artist": "B", "title": "T2", "price": 8.0, "link": "l2", "version": "standard"}]
    out = lp.carry_forward_stale_inventory(list(fresh), base=tmp_path)
    stale = [d for d in out if d.get("stale_inventory")]
    assert [d["title"] for d in stale] == ["T1"] and stale[0]["stale_since"]
    assert [d for d in out if d["source"] == "Healthy"][0]["price"] == 8.0   # fresh data wins, not duplicated
    assert len([d for d in out if d["source"] == "Healthy"]) == 1


def test_stale_inventory_expires_after_max_age(monkeypatch, tmp_path):
    old = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=lp.STALE_MAX_HOURS + 1)).isoformat()
    _prev(tmp_path, [{"source": "Broken", "artist": "A", "title": "T1", "price": 9.0,
                      "stale_inventory": True, "stale_since": old}])
    monkeypatch.setattr(lp, "SOURCES", [_src("Broken")])
    monkeypatch.setattr(lp, "FAILED_SOURCES", ["Broken"])
    monkeypatch.setattr(lp, "SOURCE_STATUS", {"Broken": "FAILED: x"})
    assert lp.carry_forward_stale_inventory([], base=tmp_path) == []


def test_healthy_run_carries_nothing_forward(monkeypatch, tmp_path):
    _prev(tmp_path, [{"source": "Healthy", "artist": "B", "title": "T2", "price": 9.0}])
    monkeypatch.setattr(lp, "SOURCES", [_src("Healthy")])
    monkeypatch.setattr(lp, "FAILED_SOURCES", [])
    monkeypatch.setattr(lp, "SOURCE_STATUS", {})
    fresh = [{"source": "Healthy", "artist": "B", "title": "T2", "price": 8.0, "version": "standard"}]
    assert lp.carry_forward_stale_inventory(list(fresh), base=tmp_path) == fresh


def test_notification_can_be_disabled(monkeypatch):
    monkeypatch.setenv("DEAL_HUNTER_DISABLE_NOTIFY", "1")
    def boom(*a, **k):
        raise AssertionError("network call attempted")
    monkeypatch.setattr(lp.urllib.request, "urlopen", boom)
    lp.send_deal_hunter_notification(10)            # must return without touching the network
