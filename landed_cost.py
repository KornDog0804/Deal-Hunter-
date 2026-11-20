# -*- coding: utf-8 -*-
"""
landed_cost.py - configurable landed cost, resale fees, net profit and ROI.

No network access. All inputs come from cost_config.json (or a dict passed in).
Nothing is assumed silently: any input that is null/unset is counted as 0 AND
reported in `missing_inputs`; placeholder values are reported in `assumed_inputs`.
`inputs_complete` is True only when nothing is missing, so callers (Phase 2) can
refuse a BUY NOW when the numbers are not trustworthy.
"""

import json
import os
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "cost_config.json"


def load_config(path=None):
    """Load config. DEAL_HUNTER_COST_CONFIG selects an alternate file (isolated test mode)."""
    p = Path(path or os.environ.get("DEAL_HUNTER_COST_CONFIG") or CONFIG_PATH)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _use(value, name, missing):
    """Return a number for the math; record the name if the config left it null."""
    n = _num(value)
    if n is None:
        missing.append(name)
        return 0.0
    return n


def to_usd(amount, currency, cfg, missing=None):
    """Convert to USD, applying the configured FX buffer. Missing rate -> reported."""
    missing = missing if missing is not None else []
    cur = (currency or "USD").upper()
    amount = _num(amount) or 0.0
    if cur == "USD":
        return amount          # no conversion, so no FX buffer either
    rate = _num(((cfg.get("fx") or {}).get("rates_to_usd") or {}).get(cur))
    if rate is None:
        missing.append("fx_rate:%s" % cur)
        return 0.0
    buffer_pct = _num((cfg.get("fx") or {}).get("buffer_pct")) or 0.0
    return amount * rate * (1.0 + buffer_pct / 100.0)


def allocate_shipping(item_price_usd, ship_cfg, missing):
    """
    Shipping for one item. Modes:
      per_item             -> amount_usd applies to this item
      per_order_allocated  -> one quoted order shipping split across items,
                              'by_price' (share of order_total_usd) or 'equal'.
    There is deliberately no built-in default price.
    """
    mode = (ship_cfg or {}).get("mode", "per_item")
    if mode == "per_item":
        return _use((ship_cfg or {}).get("amount_usd"), "shipping.amount_usd", missing)
    quote = _use((ship_cfg or {}).get("order_shipping_usd"), "shipping.order_shipping_usd", missing)
    if (ship_cfg or {}).get("allocation", "by_price") == "equal":
        count = _num((ship_cfg or {}).get("item_count"))
        if not count or count <= 0:
            missing.append("shipping.item_count")
            return 0.0
        return quote / count
    order_total = _num((ship_cfg or {}).get("order_total_usd"))
    if not order_total or order_total <= 0:
        missing.append("shipping.order_total_usd")
        return 0.0
    return quote * (item_price_usd / order_total)


def compute_landed_cost(price, currency="USD", cfg=None, profile="domestic_us", overrides=None):
    """Item price -> landed cost in USD, with a full component breakdown."""
    cfg = cfg if cfg is not None else load_config()
    prof = dict((cfg.get("profiles") or {}).get(profile) or {})
    prof.update(overrides or {})
    missing = []

    item_usd = to_usd(price, currency, cfg, missing)
    shipping = allocate_shipping(item_usd, prof.get("shipping"), missing)
    purchase_fee = (item_usd * _use(prof.get("purchase_fee_pct"), "purchase_fee_pct", missing) / 100.0
                    + _use(prof.get("purchase_fee_flat_usd"), "purchase_fee_flat_usd", missing))
    taxable = item_usd + shipping
    sales_tax = taxable * _use(prof.get("sales_tax_pct"), "sales_tax_pct", missing) / 100.0
    duty = taxable * _use(prof.get("import_duty_pct"), "import_duty_pct", missing) / 100.0
    import_tax = (taxable + duty) * _use(prof.get("import_tax_pct"), "import_tax_pct", missing) / 100.0
    brokerage = _use(prof.get("brokerage_flat_usd"), "brokerage_flat_usd", missing)

    total = item_usd + shipping + purchase_fee + sales_tax + duty + import_tax + brokerage
    return {
        "landed_cost_usd": round(total, 2),
        "components": {
            "item_usd": round(item_usd, 2), "shipping_usd": round(shipping, 2),
            "purchase_fee_usd": round(purchase_fee, 2), "sales_tax_usd": round(sales_tax, 2),
            "import_duty_usd": round(duty, 2), "import_tax_usd": round(import_tax, 2),
            "brokerage_usd": round(brokerage, 2),
        },
        "missing_inputs": sorted(set(missing)),
    }


def _resale_settings(cfg, channel=None):
    """Channel block merged over any flat legacy keys in cfg['resale']."""
    r = dict(cfg.get("resale") or {})
    chan = channel or r.get("channel")
    merged = {k: v for k, v in r.items() if k not in ("channels", "channel")}
    merged.update(((r.get("channels") or {}).get(chan)) or {})
    return merged


def _tier(block, n, name, missing):
    """Tiered per-order amount: base covers `included_records`, each extra record adds
    `per_additional_record_usd`. A null base counts as 0 and is reported as missing;
    a null per-additional only matters (and is reported) when n exceeds the included count."""
    inc = int(_num(block.get("included_records")) or 1)
    base = _use(block.get("base_usd"), "resale.%s.base_usd" % name, missing)
    extra = max(0, n - inc)
    add = 0.0
    if extra:
        add = extra * _use(block.get("per_additional_record_usd"),
                           "resale.%s.per_additional_record_usd" % name, missing)
    return base + add


def compute_resale_costs(resale_price, cfg=None, channel=None, n_records=1):
    """
    Fees on the sale of ONE ORDER of `n_records` records (default 1 = single record).
    Each charge is applied exactly once:
      * marketplace fee: % of (item [+ buyer-paid shipping]) with min/max, once per order
      * payment processing: % of the total paid + a flat per-ORDER fee, once. Separate
        charge from the marketplace fee.
      * buyer-paid shipping is revenue (credited in estimate_net_profit); outbound
        postage and packaging are costs, each counted once, each independently configurable
        (resale.postage / resale.packaging / resale.customer_shipping tier blocks; legacy
        flat keys buyer_paid_shipping_usd / outbound_shipping_usd / packaging_usd still work).
    """
    cfg = cfg if cfg is not None else load_config()
    r = _resale_settings(cfg, channel)
    missing = []
    price = _num(resale_price) or 0.0
    n = max(1, int(n_records or 1))

    if isinstance(r.get("customer_shipping"), dict):
        buyer_ship = _tier(r["customer_shipping"], n, "customer_shipping", missing)
    elif "buyer_paid_shipping_usd" in r:
        buyer_ship = _use(r.get("buyer_paid_shipping_usd"), "resale.buyer_paid_shipping_usd", missing)
    else:
        buyer_ship = 0.0
    total_paid = price + buyer_ship

    fee_base = total_paid if r.get("fee_base", "item") == "item_plus_shipping" else price
    mkt = fee_base * _use(r.get("marketplace_fee_pct"), "resale.marketplace_fee_pct", missing) / 100.0
    if mkt > 0:
        lo, hi = _num(r.get("marketplace_fee_min_usd")), _num(r.get("marketplace_fee_max_usd"))
        mkt = min(max(mkt, lo if lo is not None else mkt), hi if hi is not None else mkt)
    pay = (total_paid * _use(r.get("payment_fee_pct"), "resale.payment_fee_pct", missing) / 100.0
           + _use(r.get("payment_fee_flat_usd"), "resale.payment_fee_flat_usd", missing))
    if isinstance(r.get("postage"), dict):
        postage = _tier(r["postage"], n, "postage", missing)
    else:
        postage = _use(r.get("outbound_shipping_usd"), "resale.outbound_shipping_usd", missing)
    if isinstance(r.get("packaging"), dict):
        packaging = _tier(r["packaging"], n, "packaging", missing)
    else:
        packaging = _use(r.get("packaging_usd"), "resale.packaging_usd", missing)
    outbound = postage + packaging
    assumed = [a for a in (r.get("assumed") or []) if r.get(a) is not None]
    return {"resale_fees_usd": round(mkt + pay, 2), "marketplace_fee_usd": round(mkt, 2),
            "payment_fee_usd": round(pay, 2), "buyer_paid_shipping_usd": round(buyer_ship, 2),
            "postage_usd": round(postage, 2), "packaging_usd": round(packaging, 2),
            "outbound_costs_usd": round(outbound, 2),
            "missing_inputs": sorted(set(missing)), "assumed_inputs": assumed}


def estimate_order_profit(items, cfg=None, profile="domestic_us", channel=None):
    """
    Combined-order profitability: `items` = [{"price", "currency", "resale"}, ...]
    bought in ONE purchase and sold in ONE order. Inbound shipping (profile
    shipping.amount_usd) is charged once for the purchase; the sale side uses the tiered
    customer shipping / postage / packaging for len(items) records.
    """
    cfg = cfg if cfg is not None else load_config()
    n = len(items)
    landed_total, missing, resale_total = 0.0, [], 0.0
    for i, it in enumerate(items):
        ov = None if i == 0 else {"shipping": {"mode": "per_item", "amount_usd": 0.0}}
        lc = compute_landed_cost(it["price"], it.get("currency", "USD"), cfg, profile, ov)
        landed_total += lc["landed_cost_usd"]
        missing += lc["missing_inputs"]
        resale_total += _num(it.get("resale")) or 0.0
    rc = compute_resale_costs(resale_total, cfg, channel, n_records=n)
    net = (resale_total + rc["buyer_paid_shipping_usd"] - rc["resale_fees_usd"]
           - rc["outbound_costs_usd"] - landed_total)
    missing = sorted(set(missing + rc["missing_inputs"]))
    return {"records": n, "landed_cost_usd": round(landed_total, 2),
            "resale_total_usd": round(resale_total, 2), **{k: rc[k] for k in (
                "resale_fees_usd", "marketplace_fee_usd", "payment_fee_usd",
                "buyer_paid_shipping_usd", "postage_usd", "packaging_usd", "outbound_costs_usd")},
            "net_profit_usd": round(net, 2),
            "roi_percent": round(net / landed_total * 100.0, 1) if landed_total > 0 else 0.0,
            "missing_inputs": missing, "inputs_complete": not missing}


def estimate_net_profit(price, resale_estimate, currency="USD", cfg=None,
                        profile="domestic_us", overrides=None, channel=None):
    """
    Full picture for one purchase.

    `resale_estimate` is an ESTIMATE (Discogs asking-price based), never a verified
    sold price; the output carries that label so it travels with the number.
    """
    cfg = cfg if cfg is not None else load_config()
    landed = compute_landed_cost(price, currency, cfg, profile, overrides)
    resale = compute_resale_costs(resale_estimate, cfg, channel)
    est = _num(resale_estimate) or 0.0

    net = (est + resale["buyer_paid_shipping_usd"] - resale["resale_fees_usd"]
           - resale["outbound_costs_usd"] - landed["landed_cost_usd"])
    roi = (net / landed["landed_cost_usd"] * 100.0) if landed["landed_cost_usd"] > 0 else 0.0
    missing = sorted(set(landed["missing_inputs"] + resale["missing_inputs"]))
    return {
        "landed_cost_usd": landed["landed_cost_usd"],
        "cost_components": landed["components"],
        "resale_estimate_usd": round(est, 2),
        "resale_fees_usd": resale["resale_fees_usd"],
        "marketplace_fee_usd": resale["marketplace_fee_usd"],
        "payment_fee_usd": resale["payment_fee_usd"],
        "buyer_paid_shipping_usd": resale["buyer_paid_shipping_usd"],
        "outbound_costs_usd": resale["outbound_costs_usd"],
        "net_profit_usd": round(net, 2),
        "roi_percent": round(roi, 1),
        "missing_inputs": missing,
        "assumed_inputs": resale["assumed_inputs"],
        "inputs_complete": not missing,
        "valuation_basis": "estimate: Discogs asking prices, not verified sold prices",
    }


def passes_net_thresholds(result, cfg=None):
    """Used only when cost_config.use_net_for_decisions is true."""
    cfg = cfg if cfg is not None else load_config()
    d = cfg.get("decision") or {}
    return (result["net_profit_usd"] >= (_num(d.get("min_net_profit_usd")) or 0.0)
            and result["roi_percent"] >= (_num(d.get("min_roi_percent")) or 0.0))
