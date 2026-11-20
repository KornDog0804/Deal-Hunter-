#!/usr/bin/env python3
"""
Phase 1 live Discogs validation. READ-ONLY with respect to the repo.

 * Matches every unique listing with the NEW strict matcher (discogs_matcher).
 * NEVER reads price_cache.json / discogs_cache.json / the deals' own Discogs fields:
   every valuation here is fetched fresh, so legacy cached values cannot contaminate it.
 * Respects Discogs rate limits (>=1.1 s between calls, honours X-Discogs-Ratelimit-Remaining,
   Retry-After and 429) and stops cleanly when it hits the time budget or keeps being limited.
 * Resumable: progress lives in <out>/state.json. Re-run with the same --out and it skips
   everything already done. The workflow restores/saves that file between runs.
 * Writes ONLY into --out (default validation_out/). No repo file is modified.
"""
import argparse, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import discogs_matcher as dm
import landed_cost as lc

API = "https://api.discogs.com"
UA = "KornDogDealHunterValidation/1.0 +https://korndogrecords.com"
MIN_INTERVAL = 1.1          # authenticated limit is 60/min -> stay under it
SCHEMA = 2


class StopRun(Exception):
    """Raised to end the run early but cleanly (rate limited, auth problem, outage)."""
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class Limiter:
    def __init__(self, token, min_interval=MIN_INTERVAL, sleep=time.sleep, clock=time.monotonic, opener=None):
        self.token, self.min_interval = token, min_interval
        self.sleep, self.clock = sleep, clock
        self.opener = opener or self._open
        self.last = 0.0
        self.calls = 0
        self.consecutive_fail = 0
        self.rate_limited = 0

    def _open(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "ignore")

    def get(self, path, params=None):
        """GET api.discogs.com{path}. Returns parsed JSON, or None for 404 / no data."""
        q = dict(params or {}, token=self.token)
        url = "%s%s?%s" % (API, path, urllib.parse.urlencode(q))
        for attempt in range(4):
            wait = self.min_interval - (self.clock() - self.last)
            if wait > 0:
                self.sleep(wait)
            self.last = self.clock()
            self.calls += 1
            try:
                status, headers, body = self.opener(url)
            except urllib.error.HTTPError as e:
                status, headers, body = e.code, dict(e.headers or {}), ""
            except Exception:
                self.consecutive_fail += 1
                if self.consecutive_fail >= 8:
                    raise StopRun("network_unavailable")
                self.sleep(2 ** attempt)
                continue
            self.consecutive_fail = 0
            if status == 429:
                self.rate_limited += 1
                if self.rate_limited >= 6:
                    raise StopRun("rate_limited")
                self.sleep(float(headers.get("Retry-After", 60)))
                continue
            if status in (401, 403):
                raise StopRun("auth_failed_%d" % status)
            if status == 404:
                return None
            if status >= 500:
                self.sleep(2 ** attempt)
                continue
            rem = headers.get("X-Discogs-Ratelimit-Remaining")
            if rem is not None and str(rem).isdigit() and int(rem) <= 2:
                self.sleep(60)
            try:
                return json.loads(body)
            except ValueError:
                return None
        return None


def fetch_stats(limiter, release_id):
    """Asking-price evidence for one release (estimates, NOT sold prices)."""
    out = {}
    st = limiter.get("/marketplace/stats/%s" % release_id, {"curr_abbr": "USD"}) or {}
    low = st.get("lowest_price")
    if isinstance(low, dict):
        low = low.get("value")
    if low:
        out["lowest_price"] = round(float(low), 2)
    out["num_for_sale"] = st.get("num_for_sale")
    sug = limiter.get("/marketplace/price_suggestions/%s" % release_id) or {}
    for label, key in (("Mint (M)", "price_mint"), ("Near Mint (NM or M-)", "price_nm"),
                       ("Very Good Plus (VG+)", "price_vgplus"), ("Very Good (VG)", "price_vg")):
        v = (sug.get(label) or {}).get("value")
        if v:
            out[key] = round(float(v), 2)
    # same ladder production uses, so the numbers are comparable (NM > Mint > VG+ > lowest ask)
    est = out.get("price_nm") or out.get("price_mint") or out.get("price_vgplus") or out.get("lowest_price") or 0.0
    out["resale_estimate"] = round(est, 2)
    return out


def unique_work(deals, min_price=0.01):
    """One work item per distinct pressing identity, highest-priority first."""
    work = {}
    for d in deals:
        try:
            price = float(d.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if price < min_price or not d.get("artist") or not d.get("title"):
            continue
        ident = dm.extract_identifiers(d)
        key = dm.identity_key(ident)
        w = work.setdefault(key, {"key": key, "ident": ident, "prio": 0.0})
        w["prio"] = max(w["prio"], float(d.get("buy_score") or d.get("score") or 0))
    return sorted(work.values(), key=lambda w: (-w["prio"], w["key"]))


def validate(work, state, limiter, deadline, limit=None, save=None, clock=time.monotonic):
    """Process undone work items. Returns (processed_this_run, stop_reason|None)."""
    done = state["records"]
    n = 0
    for w in work:
        if w["key"] in done and done[w["key"]].get("schema") == SCHEMA:
            continue
        if clock() >= deadline:
            return n, "time_budget"
        if limit is not None and n >= limit:
            return n, "limit"
        try:
            res = dm.search_and_match(w["ident"], lambda p: limiter.get("/database/search", p))
            rec = {"schema": SCHEMA, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "status": res["status"], "confidence": res["confidence"],
                   "reasons": res["reasons"][:4], "release_id": res["release_id"],
                   "tied_ids": res["tied_ids"][:5],
                   **{k: res.get(k) for k in ("matched_artist", "matched_title", "matched_label",
                                              "matched_catno", "matched_country", "matched_year")}}
            if res["status"] in dm.VALUABLE_STATUSES and res["release_id"]:
                rec.update(fetch_stats(limiter, res["release_id"]))
        except StopRun as e:
            return n, e.reason
        done[w["key"]] = rec
        n += 1
        if save and n % 25 == 0:
            save()
    return n, None


def build_results(deals, state, cfg):
    """Join validated records back onto deals; compute net profit / ROI per deal."""
    rows = []
    for d in deals:
        try:
            price = float(d.get("price") or 0)
        except (TypeError, ValueError):
            price = 0.0
        row = {"link": d.get("link"), "source": d.get("source"), "price": price,
               "artist": d.get("artist"), "title": d.get("title"),
               "prod_decision": d.get("decision"), "status": "not_validated"}
        if price > 0 and d.get("artist") and d.get("title"):
            rec = state["records"].get(dm.identity_key(dm.extract_identifiers(d)))
            if rec:
                row.update(status=rec["status"], confidence=rec["confidence"],
                           release_id=rec.get("release_id"), reasons=rec.get("reasons", []),
                           matched_title=rec.get("matched_title"), matched_label=rec.get("matched_label"),
                           matched_year=rec.get("matched_year"), matched_country=rec.get("matched_country"),
                           verified=rec["status"] in dm.DECISION_GRADE_STATUSES)
                est = rec.get("resale_estimate") or 0
                if est > 0:
                    r = lc.estimate_net_profit(price, est, "USD", cfg, "domestic_us")
                    low = rec.get("lowest_price") or 0
                    row.update(resale=est, lowest_ask=low, landed=r["landed_cost_usd"],
                               net=r["net_profit_usd"], roi=r["roi_percent"],
                               inputs_complete=r["inputs_complete"], missing=r["missing_inputs"])
                    if low > 0:
                        row["net_at_lowest_ask"] = lc.estimate_net_profit(price, low, "USD", cfg, "domestic_us")["net_profit_usd"]
        rows.append(row)
    return rows


def summarize(rows, state, work_total, cfg, stop_reason):
    dec = cfg.get("decision") or {}
    min_net, min_roi = float(dec.get("min_net_profit_usd") or 5), float(dec.get("min_roi_percent") or 25)
    scanned = [r for r in rows if r["status"] != "not_validated"]
    cnt = lambda s: sum(1 for r in scanned if r["status"] == s)
    def thresholds(sel):
        n = [r for r in sel if "net" in r]
        a = [r for r in n if r["net"] >= min_net]
        b = [r for r in n if r["roi"] >= min_roi]
        return {"valued": len(n), "net_ge_min": len(a), "roi_ge_min": len(b),
                "both": sum(1 for r in a if r["roi"] >= min_roi)}
    verified = [r for r in scanned if r.get("verified")]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "complete": len([k for k, v in state["records"].items() if v.get("schema") == SCHEMA]) >= work_total,
        "stop_reason": stop_reason,
        "unique_pressings_total": work_total,
        "unique_pressings_done": len([1 for v in state["records"].values() if v.get("schema") == SCHEMA]),
        "listings_total": len(rows),
        "listings_scanned": len(scanned),
        "verified_pressing_matches": len(verified),
        "exact": cnt("exact"), "strong": cnt("strong"),
        "title_only_unverified": cnt("title_only"),
        "ambiguous": cnt("ambiguous"), "unmatched": cnt("none"),
        "with_resale_estimate": sum(1 for r in scanned if "net" in r),
        "thresholds": {"min_net_usd": min_net, "min_roi_percent": min_roi},
        "verified_only": thresholds(verified),
        "including_unverified_title_only": thresholds([r for r in scanned if r["status"] in dm.VALUABLE_STATUSES]),
        "prod_buy_now": sum(1 for r in rows if r["prod_decision"] == "BUY NOW"),
        "prod_buy_now_verified_and_profitable": sum(
            1 for r in verified if r["prod_decision"] == "BUY NOW" and r.get("net", -1) >= min_net and r.get("roi", -1) >= min_roi),
    }


def diagnostics(rows, per_status=6):
    """Why listings did not verify: reason counts + a few readable samples per status."""
    from collections import Counter
    reasons, samples = {}, {}
    for r in rows:
        st = r["status"]
        if st in ("not_validated", "exact", "strong"):
            continue
        reasons.setdefault(st, Counter())[(r.get("reasons") or ["-"])[0]] += 1
        if len(samples.setdefault(st, [])) < per_status:
            samples[st].append("%s - %s | %s" % (r.get("artist"), r.get("title"),
                               "; ".join(r.get("reasons", [])[:2]) +
                               ((" -> " + str(r.get("matched_title"))) if r.get("matched_title") else "")))
    return {"reason_counts": {k: dict(v.most_common(6)) for k, v in reasons.items()}, "samples": samples}


def combined_orders(rows, cfg, max_records=3):
    """Per provider: best basket of up to `max_records` VERIFIED records sold as one order."""
    by = {}
    for r in rows:
        if r.get("verified") and "net" in r and r["resale"] > r["price"]:
            by.setdefault(r["source"], []).append(r)
    out = []
    for src, rs in sorted(by.items()):
        rs.sort(key=lambda r: r["resale"] - r["price"], reverse=True)
        basket = rs[:max_records]
        o = lc.estimate_order_profit([{"price": r["price"], "resale": r["resale"]} for r in basket], cfg)
        out.append({"source": src, "links": [r["link"] for r in basket], **o,
                    "sum_of_single_nets_usd": round(sum(r["net"] for r in basket), 2)})
    return out


def verify_fees(cfg, fetch=None):
    """Fetch current fee wording and compare to cost_config. Report only; never edits config."""
    def default_fetch(url):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", "ignore")
    fetch = fetch or default_fetch
    report = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sources": []}
    chan = (cfg.get("resale", {}).get("channels", {}).get("discogs", {}))
    report["config"] = {k: chan.get(k) for k in ("marketplace_fee_pct", "fee_base", "payment_fee_pct", "payment_fee_flat_usd")}
    urls = [("discogs_help_search",
             "https://support.discogs.com/api/v2/help_center/articles/search.json?query=seller%20fees"),
            ("paypal_fees", "https://www.paypal.com/us/business/paypal-business-fees")]
    for name, url in urls:
        entry = {"name": name, "url": url, "ok": False, "snippets": []}
        try:
            text = fetch(url)
            if name == "discogs_help_search":
                for a in json.loads(text).get("results", [])[:8]:
                    plain = re.sub(r"<[^>]+>", " ", a.get("body") or "")
                    for m in re.finditer(r"[^.]*\b\d+(?:\.\d+)?\s*%[^.]*\.", plain):
                        s = " ".join(m.group(0).split())
                        if re.search(r"fee|commission", s, re.I):
                            entry["snippets"].append({"article": a.get("title"), "url": a.get("html_url"), "text": s[:220]})
            else:
                plain = re.sub(r"<[^>]+>", " ", text)
                for m in re.finditer(r"[^.]{0,80}\b\d+(?:\.\d+)?\s*%\s*\+\s*\$\d+(?:\.\d+)?[^.]{0,60}", plain):
                    entry["snippets"].append({"text": " ".join(m.group(0).split())[:200]})
            entry["ok"] = True
            entry["snippets"] = entry["snippets"][:12]
        except Exception as e:
            entry["error"] = str(e)[:160]
        report["sources"].append(entry)
    found = " ".join(s["text"] for e in report["sources"] for s in e["snippets"])
    report["config_values_seen_in_source_text"] = {
        "marketplace_fee_pct": ("%g%%" % chan.get("marketplace_fee_pct")) in found if chan.get("marketplace_fee_pct") is not None else None,
        "payment_fee_pct": ("%g%%" % chan.get("payment_fee_pct")) in found if chan.get("payment_fee_pct") is not None else None,
    }
    report["note"] = "Report only. Review the snippets and confirm in your Discogs seller dashboard before changing cost_config.json."
    return report


def atomic_write(path, obj):
    tmp = str(path) + ".tmp"
    Path(tmp).write_text(json.dumps(obj, separators=(",", ":")))
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--deals", default="live_deals.json")
    ap.add_argument("--out", default="validation_out")
    ap.add_argument("--max-minutes", type=float, default=300)
    ap.add_argument("--limit", type=int, default=None, help="max NEW pressings to look up this run")
    ap.add_argument("--skip-fee-check", action="store_true")
    a = ap.parse_args(argv)

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("DISCOGS_TOKEN", "")
    if not token:
        print("DISCOGS_TOKEN is not set: cannot call Discogs. Nothing validated.", file=sys.stderr)
        return 2
    cfg = lc.load_config()
    deals = json.loads(Path(a.deals).read_text())
    work = unique_work(deals)
    sp = out / "state.json"
    state = json.loads(sp.read_text()) if sp.exists() else {"records": {}}
    state.setdefault("records", {})
    limiter = Limiter(token)
    save = lambda: atomic_write(sp, state)
    deadline = time.monotonic() + a.max_minutes * 60
    print("unique pressings: %d, already done: %d" % (len(work), sum(1 for w in work if w["key"] in state["records"])))
    n, stop = validate(work, state, limiter, deadline, a.limit, save)
    save()
    rows = build_results(deals, state, cfg)
    summ = summarize(rows, state, len(work), cfg, stop)
    summ["looked_up_this_run"] = n
    summ["api_calls_this_run"] = limiter.calls
    atomic_write(out / "validation_results.json", rows)
    atomic_write(out / "validation_summary.json", summ)
    atomic_write(out / "combined_orders.json", combined_orders(rows, cfg))
    if not a.skip_fee_check:
        atomic_write(out / "fee_verification.json", verify_fees(cfg))
    diag = diagnostics(rows)
    atomic_write(out / "diagnostics.json", diag)
    print(json.dumps(summ, indent=1))
    print("\n=== WHY NOT VERIFIED ===")
    for st, c in diag["reason_counts"].items():
        print(st, c)
    for st, lst in diag["samples"].items():
        print("--", st)
        for x in lst:
            print("  ", x[:150])
    if stop in ("auth_failed_401", "auth_failed_403"):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
