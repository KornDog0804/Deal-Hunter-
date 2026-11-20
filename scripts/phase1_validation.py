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
import likely_tier as lt

API = "https://api.discogs.com"
UA = "KornDogDealHunterValidation/1.0 +https://korndogrecords.com"
MIN_INTERVAL = 1.1          # authenticated limit is 60/min -> stay under it
SCHEMA = 5
MIN_MARKET_DEPTH_DEFAULT = 3   # fewer Discogs listings than this = thin market: one ask is not a market price
SUSPECT_ROI = 300.0   # ROI above this is far more likely a wrong match than a real deal: flag for manual check


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


def fetch_lowest_ask(limiter, release_id):
    st = limiter.get("/marketplace/stats/%s" % release_id, {"curr_abbr": "USD"}) or {}
    low = st.get("lowest_price")
    if isinstance(low, dict):
        low = low.get("value")
    return round(float(low), 2) if low else None


def fetch_ask_depth(limiter, release_id):
    """(lowest ask, number of copies for sale) for one release."""
    st = limiter.get("/marketplace/stats/%s" % release_id, {"curr_abbr": "USD"}) or {}
    low = st.get("lowest_price")
    if isinstance(low, dict):
        low = low.get("value")
    return (round(float(low), 2) if low else None), st.get("num_for_sale")


def add_likely_floor(limiter, res, rec):
    """Option B: value unverified-but-found albums at the Lowest Asking Price Estimate across plausible pressings.
    Also records how many copies are for sale on the release that sets that price (market depth)."""
    depth = {}
    if res["status"] == "ambiguous":
        ids = [i for i in (res.get("tied_ids") or [])][: lt.MAX_TIED_LOOKUPS]
        asks = {}
        for i in ids:
            asks[i], depth[i] = fetch_ask_depth(limiter, i)
    elif res["status"] == "title_only" and res.get("release_id"):
        asks = {res["release_id"]: rec.get("lowest_price")}
        depth = {res["release_id"]: rec.get("num_for_sale")}
    else:
        return
    f = lt.floor_estimate(asks)
    if f:
        floor_id = min((i for i, v in asks.items() if v and float(v) > 0), key=lambda i: float(asks[i]))
        rec.update(tier="likely", floor_estimate=f["floor"], floor_spread=f["spread"],
                   floor_wide=f["wide"], floor_ids=f["ids"], floor_depth=depth.get(floor_id))


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
                   "reasons": res["reasons"][:4],
                   "rejected": [str(x)[:140] for x in (res.get("rejected") or [])[:2]], "release_id": res["release_id"],
                   "tied_ids": res["tied_ids"][:5],
                   **{k: res.get(k) for k in ("matched_artist", "matched_title", "matched_label",
                                              "matched_catno", "matched_country", "matched_year")}}
            if res["status"] in dm.VALUABLE_STATUSES and res["release_id"]:
                rec.update(fetch_stats(limiter, res["release_id"]))
            add_likely_floor(limiter, res, rec)
        except StopRun as e:
            return n, e.reason
        done[w["key"]] = rec
        n += 1
        if save and n % 25 == 0:
            save()
    return n, None


def manual_check_reasons(row, rec):
    """Verified matches that must still be confirmed by hand before anyone trusts them."""
    why = []
    if str(row.get("artist") or "").strip().lower() in ("", "unknown artist"):
        why.append("listing has no artist")
    got = set(rec.get("reasons") or [])
    if row.get("status") == "strong" and not (got & {"barcode_match", "catno_match"}) \
            and not (row.get("identifiers_used") or {}).get("barcode"):
        why.append("matched on label/year only, no barcode or catalog number")
    cond = str(row.get("condition") or "").strip().lower()
    if cond and cond not in ("new", "sealed", "mint", "m", "nm", "near mint"):
        why.append("used/graded copy (%s): Discogs estimate assumes near-mint" % cond)
    if "barcode_shared_resolved" in got:
        why.append("barcode shared by several releases, resolved by other evidence")
    return why


def build_results(deals, state, cfg, min_depth=None):
    """Join validated records back onto deals; compute net profit / ROI per deal."""
    rows = []
    if min_depth is None:
        min_depth = int((cfg.get("decision") or {}).get("min_market_depth") or MIN_MARKET_DEPTH_DEFAULT)
    for d in deals:
        try:
            price = float(d.get("price") or 0)
        except (TypeError, ValueError):
            price = 0.0
        ident_now = dm.extract_identifiers(d)
        cur = str(d.get("currency") or "USD").upper()
        cost_profile = d.get("cost_profile") or "domestic_us"
        sku_provider = None if cost_profile != "domestic_us" else d.get("source")   # store shipping tables are US-domestic only
        row = {"link": d.get("link"), "source": d.get("source"), "price": price,
               "currency": cur, "cost_profile": cost_profile, "condition": d.get("condition"),
               "artist": d.get("artist"), "title": d.get("title"), "raw_title": d.get("raw_title"),
               "_key": dm.identity_key(ident_now),
               "identifiers_used": {k: ident_now.get(k) for k in ("barcode", "sku", "catno", "label", "year") if ident_now.get(k)},
               "prod_decision": d.get("decision"), "status": "not_validated"}
        if price > 0 and d.get("artist") and d.get("title"):
            rec = state["records"].get(dm.identity_key(dm.extract_identifiers(d)))
            if rec:
                row.update(status=rec["status"], confidence=rec["confidence"],
                           release_id=rec.get("release_id"), reasons=rec.get("reasons", []),
                           matched_title=rec.get("matched_title"), rejected=rec.get("rejected", []), matched_label=rec.get("matched_label"),
                           matched_year=rec.get("matched_year"), matched_country=rec.get("matched_country"),
                           verified=rec["status"] in dm.DECISION_GRADE_STATUSES)
                est = rec.get("resale_estimate") or 0
                if not row["verified"]:                       # Likely tier: floor price only
                    est = rec.get("floor_estimate") or 0
                    row["tier"] = "likely" if est > 0 else "unverified"
                    if est > 0:
                        row.update(floor_wide=rec.get("floor_wide"), floor_spread=rec.get("floor_spread"))
                else:
                    row["tier"] = "verified"
                if est > 0:
                    r = lc.estimate_net_profit(price, est, cur, cfg, cost_profile, provider=sku_provider)
                    low = rec.get("lowest_price") or 0
                    depth = rec.get("num_for_sale") if row["tier"] == "verified" else rec.get("floor_depth")
                    thin = depth is not None and depth < min_depth
                    row.update(resale=est, lowest_ask=low, landed=r["landed_cost_usd"],
                               net=r["net_profit_usd"], roi=r["roi_percent"],
                               suspect=r["roi_percent"] > SUSPECT_ROI,
                               market_depth=depth, thin_market=thin, depth_unknown=depth is None,
                               valuation_label=("Lowest Asking Price Estimate" if row["tier"] == "likely"
                                                else "Discogs price-guide estimate (NM)"),
                               inbound_shipping_basis=r.get("inbound_shipping_basis"),
                               cost_certainty=r.get("cost_certainty"),
                               inputs_complete=r["inputs_complete"], missing=r["missing_inputs"])
                    row["needs_review"] = bool(row["suspect"] or thin)
                    row["cost_status"] = "complete" if r["inputs_complete"] else "incomplete"
                    row["net_label"] = ("Estimated net" if r["inputs_complete"]
                                        else "Estimated net, INCOMPLETE costs (not confirmed profit)")
                    if low > 0:
                        row["net_at_lowest_ask"] = lc.estimate_net_profit(price, low, cur, cfg, cost_profile, provider=sku_provider)["net_profit_usd"]
        if row.get("verified"):
            row["manual_check"] = manual_check_reasons(row, rec)
        row["recommendation_eligible"] = bool(
            row.get("verified") and "net" in row and not row.get("needs_review") and not row.get("manual_check")
            and not row.get("depth_unknown"))
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
    likely = [r for r in scanned if r.get("tier") == "likely"]
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
        "likely_tier": dict(thresholds(likely), count=len(likely),
                            wide_spread=sum(1 for r in likely if r.get("floor_wide")),
                            suspect_roi_over_300=sum(1 for r in likely if r.get("suspect")),
                            thin_market=sum(1 for r in likely if r.get("thin_market")),
                            both_excluding_suspect=sum(1 for r in likely if r.get("net", 0) >= min_net and r.get("roi", 0) >= min_roi and not r.get("needs_review"))),
        "verified_thin_market": sum(1 for r in verified if r.get("thin_market")),
        "verified_both_excluding_review": sum(1 for r in verified if r.get("net", 0) >= min_net and r.get("roi", 0) >= min_roi and not r.get("needs_review")),
        "market_depth_unknown": sum(1 for r in scanned if r.get("depth_unknown")),
        "incomplete_cost_rows": sum(1 for r in scanned if r.get("cost_status") == "incomplete"),
        "verified_manual_check": sum(1 for r in verified if r.get("manual_check")),
        "recommendation_eligible": sum(1 for r in scanned if r.get("recommendation_eligible")),
        "recommendation_eligible_meeting_thresholds": sum(
            1 for r in scanned if r.get("recommendation_eligible") and r.get("net", 0) >= min_net and r.get("roi", 0) >= min_roi),
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
                               ((" -> " + str(r.get("matched_title"))) if r.get("matched_title") else "") +
                               ((" | rej: " + " / ".join(r["rejected"])) if r.get("rejected") else "")))
    return {"reason_counts": {k: dict(v.most_common(6)) for k, v in reasons.items()}, "samples": samples}


def combined_orders(rows, cfg, max_records=3):
    """Per provider: best basket of up to `max_records` records sold as ONE order.
    Uses verified records and Likely-tier (floor) records; suspect (ROI > 300%) rows are excluded."""
    by = {}
    for r in rows:
        if r.get("tier") in ("verified", "likely") and "net" in r and not r.get("needs_review") and r["resale"] > r["price"]:
            by.setdefault(r["source"], []).append(r)
    out = []
    for src, rs in sorted(by.items()):
        rs.sort(key=lambda r: r["resale"] - r["price"], reverse=True)
        basket = rs[:max_records]
        o = lc.estimate_order_profit([{"price": r["price"], "resale": r["resale"]} for r in basket], cfg, provider=src)
        out.append({"source": src, "links": [r["link"] for r in basket],
                    "basis": "verified" if all(r["tier"] == "verified" for r in basket) else "likely_floor",
                    **o, "sum_of_single_nets_usd": round(sum(r["net"] for r in basket), 2)})
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


# --------------------------------------------------------------------------
# representative sample + old-vs-new comparison
# --------------------------------------------------------------------------

STRATA_QUOTA = [("has_barcode", 30), ("paren_title", 40), ("variant_title", 40),
                ("old_unmatched", 30), ("old_title_only", 20), ("old_ambiguous", 20)]


def merge_identifiers(deals, by_link):
    """Attach probe identifiers (barcode / SKU / labelled text) to listings by product link. Additive only."""
    n = 0
    for d in deals:
        ids = (by_link or {}).get(d.get("link"))
        if ids:
            merged = dict(d.get("identifiers") or {})
            for k, v in ids.items():
                merged.setdefault(k, v)
            d["identifiers"] = merged
            n += 1
    return n


def select_sample(deals, baseline_rows, n=200, seed=7, min_per_provider=3):
    """
    Deterministic stratified sample of UNIQUE pressings (what the matcher actually looks up):
    listings with barcodes, parenthetical edition titles, coloured/limited variants, and titles the old
    run left unmatched / title-only / ambiguous, then topped up round-robin so every provider is present.
    """
    import random
    rng = random.Random(seed)
    old = {r.get("link"): r for r in (baseline_rows or [])}
    cands = {}
    for d in deals:
        try:
            if float(d.get("price") or 0) <= 0 or not d.get("artist") or not d.get("title"):
                continue
        except (TypeError, ValueError):
            continue
        ident = dm.extract_identifiers(d)
        key = dm.identity_key(ident)
        o = old.get(d.get("link")) or {}
        tags = set()
        if ident.get("barcode"):
            tags.add("has_barcode")
        if "(" in str(d.get("raw_title") or ""):
            tags.add("paren_title")
        if ident.get("variants"):
            tags.add("variant_title")
        st = o.get("status")
        if st == "none":
            tags.add("old_unmatched")
        elif st == "title_only":
            tags.add("old_title_only")
        elif st == "ambiguous":
            tags.add("old_ambiguous")
        c = cands.setdefault(key, {"key": key, "ident": ident, "deal": d, "tags": set()})
        c["tags"] |= tags
    pool = sorted(cands.values(), key=lambda c: c["key"])
    chosen, seen = [], set()

    def take(c, why):
        if c["key"] not in seen and len(chosen) < n:
            seen.add(c["key"]); chosen.append(dict(c, why=why))

    for tag, quota in STRATA_QUOTA:
        group = [c for c in pool if tag in c["tags"] and c["key"] not in seen]
        rng.shuffle(group)
        for c in group[:quota]:
            take(c, tag)
    by_src = {}
    for c in pool:
        by_src.setdefault(c["deal"].get("source"), []).append(c)
    for src in sorted(by_src, key=str):                       # every provider gets a minimum presence
        have = sum(1 for c in chosen if c["deal"].get("source") == src)
        rest = [c for c in by_src[src] if c["key"] not in seen]
        rng.shuffle(rest)
        for c in rest[:max(0, min_per_provider - have)]:
            take(c, "provider_minimum")
    rest = [c for c in pool if c["key"] not in seen]
    rng.shuffle(rest)
    for c in rest:                                             # fill any remainder at random
        take(c, "random_fill")
    return chosen


def compare_old_new(sample, old_rows, new_rows):
    """Old (previous full run) vs new (this run) for exactly the sampled listings, plus the pairs to audit by hand."""
    from collections import Counter
    old = {r.get("link"): r for r in (old_rows or [])}
    new = {r.get("link"): r for r in new_rows}
    keyset = {c["key"] for c in sample}
    trans, pairs = Counter(), []
    old_v = new_v = 0
    for r in new_rows:
        d_key = r.get("_key")
        if d_key not in keyset:
            continue
        o = old.get(r["link"]) or {}
        os_, ns = o.get("status", "not_in_old_run"), r["status"]
        trans["%s -> %s" % (os_, ns)] += 1
        old_v += 1 if os_ in dm.DECISION_GRADE_STATUSES else 0
        new_v += 1 if ns in dm.DECISION_GRADE_STATUSES else 0
        changed = (os_ != ns) or (o.get("release_id") != r.get("release_id"))
        if ns in ("exact", "strong", "title_only") and (changed or ns != "title_only"):
            pairs.append({"source": r["source"], "listing": "%s - %s" % (r["artist"], r["title"]), "raw_title": r.get("raw_title"),
                          "link": r["link"], "new_status": ns, "new_match": r.get("matched_title"), "new_label": r.get("matched_label"),
                          "new_year": r.get("matched_year"), "new_country": r.get("matched_country"), "new_release_id": r.get("release_id"),
                          "reasons": r.get("reasons"), "old_status": os_, "old_release_id": o.get("release_id"),
                          "identifiers": r.get("identifiers_used")})
    return {"sample_size": len(sample), "old_verified": old_v, "new_verified": new_v,
            "transitions": dict(trans.most_common()), "audit_pairs": pairs}


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
    ap.add_argument("--sample", type=int, default=None, help="validate a stratified sample of N unique pressings instead of everything")
    ap.add_argument("--identifiers", default=None, help="identifiers_by_link.json from provider_probe.py")
    ap.add_argument("--baseline", default=None, help="validation_results.json from the previous full run, for old-vs-new")
    a = ap.parse_args(argv)

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("DISCOGS_TOKEN", "")
    if not token:
        print("DISCOGS_TOKEN is not set: cannot call Discogs. Nothing validated.", file=sys.stderr)
        return 2
    cfg = lc.load_config()
    deals = json.loads(Path(a.deals).read_text())
    deals = deals if isinstance(deals, list) else deals.get("deals", [])
    if a.identifiers and Path(a.identifiers).exists():
        print("identifiers merged into %d listings" % merge_identifiers(deals, json.loads(Path(a.identifiers).read_text())))
    sample = None
    if a.sample:
        base = json.loads(Path(a.baseline).read_text()) if a.baseline and Path(a.baseline).exists() else []
        sample = select_sample(deals, base, a.sample)
        keep = {c["key"] for c in sample}
        work = [w for w in unique_work(deals) if w["key"] in keep]
        print("sample: %d unique pressings; strata: %s" % (len(work), {t: sum(1 for c in sample if c["why"] == t) for t, _ in STRATA_QUOTA}))
    else:
        base = []
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
    if sample is not None:
        keep = {c["key"] for c in sample}
        rows = [r for r in rows if r.get("_key") in keep]
        cmp_ = compare_old_new(sample, base, rows)
        atomic_write(out / "sample_comparison.json", cmp_)
        atomic_write(out / "sample_selection.json", [{"key": c["key"], "why": c["why"], "source": c["deal"].get("source"),
                                                      "listing": "%s - %s" % (c["deal"].get("artist"), c["deal"].get("title"))} for c in sample])
        print("OLD verified %d -> NEW verified %d on %d sampled listings" % (cmp_["old_verified"], cmp_["new_verified"], len(rows)))
        summ = summarize(rows, state, len(work), cfg, stop)
        summ["sample"] = True
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
            print("  ", x[:260])
    if stop in ("auth_failed_401", "auth_failed_403"):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
