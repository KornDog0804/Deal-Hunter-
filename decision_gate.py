# -*- coding: utf-8 -*-
"""
decision_gate.py - may this listing be called BUY NOW?

BUY NOW is only trustworthy when ALL of these hold:
  * the listing has a real price
  * a Discogs valuation exists AND its release match is exact/strong (pressing verified)
  * the landed-cost / resale inputs are complete (nothing assumed-as-zero)
  * the inventory is live (not carried forward from a failed provider)

Every deal gets `buy_now_blockers` + `buy_now_gate_pass` (report-only). Decisions are
changed only when cost_config.json -> decision_safety.enforce_buy_now_gate is true.
"""

import landed_cost as lc

DEFAULT_SAFETY = {
    "enforce_buy_now_gate": False,
    "required_match_statuses": ["exact", "strong"],
    "require_complete_cost_inputs": True,
    "block_stale_inventory": True,
}


def blockers(deal, cfg=None):
    cfg = cfg if cfg is not None else lc.load_config()
    safety = dict(DEFAULT_SAFETY, **(cfg.get("decision_safety") or {}))
    out = []

    try:
        price = float(deal.get("price") or 0)
    except (TypeError, ValueError):
        price = 0.0
    if price <= 0:
        out.append("price_missing")

    status = deal.get("discogs_match_status")
    if not deal.get("discogs_sell_price"):
        out.append("no_discogs_valuation" if status in (None, "") else "no_discogs_valuation(%s)" % status)
    elif status not in safety["required_match_statuses"]:
        out.append("pressing_unverified(%s)" % status)

    if safety["require_complete_cost_inputs"]:
        if deal.get("cost_inputs_complete") is False:
            out.append("cost_inputs_incomplete")
        elif "cost_inputs_complete" not in deal:
            out.append("cost_inputs_unknown")

    if safety["block_stale_inventory"] and deal.get("stale_inventory"):
        out.append("stale_inventory")
    return out


def apply_gate(deal, cfg=None):
    """Annotate the deal; downgrade BUY NOW -> WATCH only when enforcement is on."""
    cfg = cfg if cfg is not None else lc.load_config()
    safety = dict(DEFAULT_SAFETY, **(cfg.get("decision_safety") or {}))
    found = blockers(deal, cfg)
    deal["buy_now_blockers"] = found
    deal["buy_now_gate_pass"] = not found
    if safety["enforce_buy_now_gate"] and found and deal.get("decision") == "BUY NOW":
        deal["decision_before_gate"] = "BUY NOW"
        deal["decision"] = "WATCH"
        deal["decision_note"] = "BUY NOW blocked: " + ", ".join(found)
    return deal
