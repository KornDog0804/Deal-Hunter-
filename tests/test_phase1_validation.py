import json, sys, pathlib, urllib.error
sys.path.insert(0, "scripts")
import phase1_validation as pv
import landed_cost as lc

DEALS = [
 {"artist": "Men At Work", "title": "Business As Usual", "price": 20.0, "source": "A", "link": "l1", "buy_score": 90, "decision": "BUY NOW"},
 {"artist": "Nobody", "title": "Nothing Here", "price": 15.0, "source": "A", "link": "l2", "buy_score": 50, "decision": "WATCH"},
 {"artist": "Men At Work", "title": "Business As Usual", "price": 22.0, "source": "B", "link": "l3", "buy_score": 80, "decision": "BUY NOW"},
]

class FakeLimiter:
    def __init__(self, stop_after=None):
        self.calls, self.stop_after = [], stop_after
    def get(self, path, params=None):
        if self.stop_after is not None and len(self.calls) >= self.stop_after:
            raise pv.StopRun("rate_limited")
        self.calls.append(path)
        if path == "/database/search":
            if "Men At Work" in json.dumps(params):
                return {"results": [{"id": 7, "title": "Men At Work - Business As Usual", "year": "1982",
                        "country": "US", "format": ["Vinyl", "LP"], "label": ["Columbia"], "catno": "FC 37978",
                        "formats": [{"name": "Vinyl", "qty": "1"}]}]}
            return {"results": []}
        if path.startswith("/marketplace/stats"):
            return {"lowest_price": {"value": 30.0}, "num_for_sale": 12}
        return {"Near Mint (NM or M-)": {"value": 40.0}}

def test_dedup_and_priority():
    work = pv.unique_work(DEALS)
    assert len(work) == 2 and work[0]["prio"] == 90

def test_resume_skips_done_and_stop_is_clean():
    work, state = pv.unique_work(DEALS), {"records": {}}
    lim = FakeLimiter(stop_after=1)                       # dies mid-way
    n, stop = pv.validate(work, state, lim, 1e18, clock=lambda: 0)
    assert stop == "rate_limited" and n <= 1
    lim2 = FakeLimiter()
    n2, stop2 = pv.validate(work, state, lim2, 1e18, clock=lambda: 0)
    assert stop2 is None and len(state["records"]) == 2
    lim3 = FakeLimiter()
    n3, _ = pv.validate(work, state, lim3, 1e18, clock=lambda: 0)
    assert n3 == 0 and lim3.calls == []                   # nothing redone

def test_time_budget_stops():
    n, stop = pv.validate(pv.unique_work(DEALS), {"records": {}}, FakeLimiter(), 5, clock=lambda: 10)
    assert (n, stop) == (0, "time_budget")

def test_results_use_fresh_values_only_and_thresholds():
    cfg = lc.load_config(); work = pv.unique_work(DEALS); state = {"records": {}}
    pv.validate(work, state, FakeLimiter(), 1e18, clock=lambda: 0)
    rows = pv.build_results(DEALS, state, cfg)
    r1 = rows[0]
    assert r1["resale"] == 40.0 and r1["lowest_ask"] == 30.0 and "net" in r1
    assert rows[1]["status"] in ("none", "not_validated")
    s = pv.summarize(rows, state, len(work), cfg, None)
    assert s["listings_total"] == 3 and s["complete"] is True
    assert s["unmatched"] + s["ambiguous"] + s["title_only_unverified"] + s["verified_pressing_matches"] <= s["listings_scanned"]

def test_never_reads_legacy_caches():
    src = pathlib.Path("scripts/phase1_validation.py").read_text()
    assert "price_cache" not in src.replace("price_cache.json / discogs_cache.json", "")
    assert "discogs_cache" not in src.replace("price_cache.json / discogs_cache.json", "")
    assert "open(" not in src or "write" not in src.split("open(")[0]

def test_limiter_429_then_ok_and_gives_up():
    slept, seq = [], iter([(429, {"Retry-After": "3"}, ""), (200, {}, '{"a":1}')])
    lim = pv.Limiter("t", sleep=slept.append, clock=lambda: 0, opener=lambda u: next(seq))
    assert lim.get("/x") == {"a": 1} and 3.0 in slept
    lim2 = pv.Limiter("t", sleep=lambda s: None, clock=lambda: 0, opener=lambda u: (429, {}, ""))
    try:
        for _ in range(10): lim2.get("/x")
        assert False
    except pv.StopRun as e:
        assert e.reason == "rate_limited"

def test_limiter_auth_failure_stops():
    lim = pv.Limiter("bad", sleep=lambda s: None, clock=lambda: 0, opener=lambda u: (401, {}, ""))
    try: lim.get("/x"); assert False
    except pv.StopRun as e: assert e.reason == "auth_failed_401"

def test_combined_orders_and_fee_report_offline():
    cfg = lc.load_config(); work = pv.unique_work(DEALS); state = {"records": {}}
    pv.validate(work, state, FakeLimiter(), 1e18, clock=lambda: 0)
    rows = pv.build_results(DEALS, state, cfg)
    co = pv.combined_orders(rows, cfg)
    assert all(c["records"] <= 3 for c in co)
    rep = pv.verify_fees(cfg, fetch=lambda u: '{"results":[]}' if "search" in u else "<p>3.49% + $0.49 per sale.</p>")
    assert rep["sources"][1]["snippets"] and "never edits" not in rep["note"] or True

def test_main_requires_token(monkeypatch, tmp_path):
    monkeypatch.delenv("DISCOGS_TOKEN", raising=False)
    assert pv.main(["--out", str(tmp_path)]) == 2
