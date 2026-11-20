#!/usr/bin/env python3
"""
Recompute profit/ROI/flags for a finished validation run under the CURRENT cost_config.json,
without calling Discogs again (every Discogs-derived number - match, release, resale estimate,
market depth - is taken as-is from the results). Used after editing shipping/tax settings.
Usage: recompute_results.py <results_dir> [--out DIR]
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import landed_cost as lc
from scripts import phase1_validation as pv


def recompute_rows(rows, cfg, min_depth=None):
    if min_depth is None:
        min_depth = int((cfg.get("decision") or {}).get("min_market_depth") or pv.MIN_MARKET_DEPTH_DEFAULT)
    for r in rows:
        if "resale" not in r:
            continue
        prof = r.get("cost_profile") or "domestic_us"
        x = lc.estimate_net_profit(r["price"], r["resale"], r.get("currency") or "USD", cfg, prof,
                                   provider=r.get("source") if prof == "domestic_us" else None)
        depth = r.get("market_depth")
        thin = depth is not None and depth < min_depth
        r.update(landed=x["landed_cost_usd"], net=x["net_profit_usd"], roi=x["roi_percent"],
                 suspect=x["roi_percent"] > pv.SUSPECT_ROI, thin_market=thin,
                 inbound_shipping_basis=x.get("inbound_shipping_basis"), cost_certainty=x.get("cost_certainty"),
                 inputs_complete=x["inputs_complete"], missing=x["missing_inputs"],
                 cost_status="complete" if x["inputs_complete"] else "incomplete",
                 net_label="Estimated net" if x["inputs_complete"] else "Estimated net, INCOMPLETE costs (not confirmed profit)")
        r["needs_review"] = bool(r["suspect"] or thin)
        r["recommendation_eligible"] = bool(r.get("verified") and not r["needs_review"] and not r.get("manual_check")
                                            and not r.get("depth_unknown"))
    for r in rows:
        r.setdefault("recommendation_eligible", False)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    d, out = Path(a.dir), Path(a.out or a.dir)
    out.mkdir(parents=True, exist_ok=True)
    cfg = lc.load_config()
    rows = recompute_rows(json.loads((d / "validation_results.json").read_text()), cfg)
    old = json.loads((d / "validation_summary.json").read_text())
    summ = pv.summarize(rows, {"records": {}}, old.get("unique_pressings_total", 0), cfg, old.get("stop_reason"))
    for k in ("complete", "stop_reason", "unique_pressings_total", "unique_pressings_done", "looked_up_this_run",
              "api_calls_this_run", "sample"):
        if k in old:
            summ[k] = old[k]
    summ["recomputed_with_config_at"] = summ["generated_at"]
    (out / "validation_results.json").write_text(json.dumps(rows))
    (out / "validation_summary.json").write_text(json.dumps(summ, indent=1))
    (out / "combined_orders.json").write_text(json.dumps(pv.combined_orders(rows, cfg), indent=1))
    print("recomputed %d rows; incomplete-cost rows: %s; eligible: %s" % (
        len(rows), summ["incomplete_cost_rows"], summ["recommendation_eligible"]))


if __name__ == "__main__":
    main()
