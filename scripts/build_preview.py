"""Build preview/ data offline from committed files. No network, no writes outside preview/.
Overlay = per-deal gate result + landed cost/net/ROI where a (legacy, UNVALIDATED) resale estimate exists."""
import json, re, shutil, sys
sys.path.insert(0, ".")
import landed_cost, decision_gate, price_lookup
cfg = landed_cost.load_config()
deals = json.load(open("live_deals.json"))
cache = json.load(open("price_cache.json"))
src = [s["name"] for s in json.load(open("sources.json"))["sources"]]

# provider health parsed from the last production run log
log = open("debug_live_pull.txt").read().split("\n")
health, cur = {}, None
for ln in log:
    m = re.match(r"Scraping: (.+) \((.+)\)", ln)
    if m: cur = m.group(1); health.setdefault(cur, {"type": m.group(2), "kept": None, "errors": []}); continue
    m = re.match(r"(.+): kept (\d+)", ln)
    if m and m.group(1) in health: health[m.group(1)]["kept"] = int(m.group(2)); continue
    if cur and "✗" in ln: health[cur]["errors"].append(ln.strip()[:160])
counts = {}
for d in deals: counts[d.get("source")] = counts.get(d.get("source"), 0) + 1
prov = []
for n in src:
    h = health.get(n)
    c = counts.get(n, 0)
    status = "ok" if c else ("failed" if h and h["errors"] else "empty")
    if h is None: status = "not in log" if not c else "ok"
    prov.append({"name": n, "listings": c, "status": status, "errors": (h or {}).get("errors", [])[:2]})

ov, n_net = {}, 0
for i, d in enumerate(deals):
    x = json.loads(json.dumps(d)); decision_gate.apply_gate(x, cfg)
    e = cache.get(price_lookup.cache_key(d.get("artist", ""), d.get("title", "")))
    o = {"p": x["decision"], "b": x.get("buy_now_blockers", []), "g": x.get("buy_now_gate_pass", False)}
    sp = (e or {}).get("suggested_sell_price") or 0
    price = d.get("price")
    if e and e.get("found"): o["legacy"] = True
    if price and sp > 0:
        r = landed_cost.estimate_net_profit(price, sp, "USD", cfg, "domestic_us")
        o.update(lc=r["landed_cost_usd"], rs=sp, net=r["net_profit_usd"], roi=r["roi_percent"], inc=r["inputs_complete"], miss=len(r["missing_inputs"])); n_net += 1
    ov[d.get("link") or str(i)] = o
json.dump({"providers": prov, "overlay": ov, "gate_on": cfg["decision_safety"]["enforce_buy_now_gate"]}, open("preview/preview_data.json", "w"), separators=(",", ":"))
bn = sum(1 for o in ov.values() if o["p"] == "BUY NOW"); gp = sum(1 for o in ov.values() if o["p"] == "BUY NOW" and o["g"])
print(len(prov), "providers;", sum(p["status"] == "ok" for p in prov), "ok;", n_net, "with net;", "BUY NOW", bn, "gate-pass", gp)
