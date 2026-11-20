"""Derive preview/index.html from index.html (branding/layout untouched) + preview overlay. Read-only on source files."""
import shutil
s = open("index.html").read()
def rep(a, b, n=1):
    global s
    assert s.count(a) >= 1, a[:50]
    s = s.replace(a, b, n)

css = """
.pvBanner{background:#2a1a00;border:1px solid #f5a623;color:#ffd99a;padding:10px 14px;border-radius:12px;margin:10px 0;font-size:13px;line-height:1.45}
.pvBanner b{color:#fff}
.pv{margin-top:8px;padding:8px 10px;border-radius:10px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);font-size:12px;line-height:1.5}
.pv .pill{display:inline-block;padding:2px 8px;border-radius:99px;font-weight:700;font-size:11px;margin-right:4px}
.pv .ok{background:#12391f;color:#7be3a0}.pv .warn{background:#3d2e08;color:#ffd166}.pv .bad{background:#43181b;color:#ff8d94}.pv .dim{background:#2b2f3a;color:#aab}
.pv small{opacity:.75}
.hpanel{grid-column:1/-1}
.hrow{display:flex;justify-content:space-between;gap:8px;padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.08);font-size:13px}
.hrow .n{font-weight:600}.hrow .e{font-size:11px;opacity:.7;word-break:break-all}
"""
rep("</style>", css + "</style>")
rep('<div class="shell">', '<div class="shell">\n<div class="pvBanner" id="pvBanner"><b>PREVIEW &middot; branch phase1-valuation-accuracy.</b> Real inventory snapshot, not production. Match status, net profit and BUY NOW gate shown are computed offline; live Discogs was not reachable, so Discogs figures are <b>legacy cache, unvalidated</b>.</div>')
rep('<button class="tab" data-view="olivia">', '<button class="tab" data-view="health">\n  🩺 HEALTH\n</button>\n\n<button class="tab" data-view="olivia">')
rep("let liveDeals = []", "let liveDeals = []\nlet PV = {providers:[],overlay:{},gate_on:false}\n"
 """
function pvBlock(d){
  const o = PV.overlay[d.link]
  if(!o) return ""
  const prod = o.p
  const after = (prod==="BUY NOW" && !o.g) ? "WATCH" : prod
  let h = `<span class="pill ${prod==="BUY NOW"&&!o.g?"warn":"dim"}">Prod: ${esc(prod)}</span>`
  if(prod==="BUY NOW") h += `<span class="pill ${o.g?"ok":"bad"}">${o.g?"BUY NOW holds":"Preview: "+after}</span>`
  h += `<span class="pill dim">Match: ${o.legacy?"legacy cache (unvalidated)":"not checked"}</span>`
  if(o.b && o.b.length) h += `<br><small>Blockers: ${o.b.map(esc).join(", ")}</small>`
  if(o.net!==undefined){
    h += `<br>Landed $${o.lc.toFixed(2)} &middot; resale est. $${o.rs.toFixed(2)} <small>(Discogs asking, estimate)</small><br>`+
         `Net ${o.net>=0?"+":""}$${o.net.toFixed(2)} &middot; ROI ${o.roi}% <small>${o.inc?"":"(cost inputs incomplete: "+o.miss+" unset)"}</small>`
  }else{
    h += `<br><small>Net profit/ROI: needs a Discogs valuation</small>`
  }
  return `<div class="pv">${h}</div>`
}
function healthPanel(){
  const p = PV.providers, ok = p.filter(x=>x.status==="ok").length
  const rows = p.map(x=>`<div class="hrow"><div><div class="n">${esc(x.name)}</div>${x.errors.map(e=>`<div class="e">${esc(e)}</div>`).join("")}</div>
    <div><span class="pill ${x.status==="ok"?"ok":"bad"}" style="padding:2px 8px;border-radius:99px;font-size:11px;background:${x.status==="ok"?"#12391f":"#43181b"};color:${x.status==="ok"?"#7be3a0":"#ff8d94"}">${x.status==="ok"?x.listings+" listings":x.status}</span></div></div>`).join("")
  const bn = Object.values(PV.overlay).filter(o=>o.p==="BUY NOW")
  return `<div class="hpanel"><div class="pv"><b>Providers: ${ok} of ${p.length} returned listings</b> (from last production run log)<br>
   <small>"failed/empty" = no listings attributed to that source name; some retry then fall back to a shared feed. Not a live re-check.</small><br><br>
   <b>BUY NOW gate:</b> ${bn.filter(o=>o.g).length} of ${bn.length} production BUY NOWs pass (gate ${PV.gate_on?"enforced":"report-only in production config"}). Most are assumed-markup recommendations with no Discogs valuation or complete cost inputs.</div>${rows}</div>`
}
""")
rep("function card(d){", "function card(d){", 1)
rep('''          <div class="market">
            ${discogsText(d)}
            ${buyerScore > 0
              ? `<br>Buyer Brain ${buyerScore}`
              : ""}
          </div>

        </div>
''', '''          <div class="market">
            ${discogsText(d)}
            ${buyerScore > 0
              ? `<br>Buyer Brain ${buyerScore}`
              : ""}
          </div>

        </div>
        ${pvBlock(d)}
''')
rep("function render(){\n  const data = filtered()", "function render(){\n  if(view===\"health\"){ $(\"resultCount\").textContent=\"Provider health\"; $(\"paginationTop\").innerHTML=\"\"; $(\"paginationBottom\").innerHTML=\"\"; $(\"grid\").innerHTML=healthPanel(); return }\n  const data = filtered()")
rep("    populateSources()\n    updateStats()", "    try{ const pr = await fetch(`preview_data.json?t=${Date.now()}`); if(pr.ok) PV = await pr.json() }catch(e){ console.error(e) }\n    populateSources()\n    updateStats()")
rep("<title>KornDog Deal Hunter</title>", "<title>KornDog Deal Hunter (PREVIEW)</title>")
open("preview/index.html", "w").write(s)
for f in ["live_deals.json","buy_signals.json","mini_vinyl_deals.json","collectibles_deals.json","olivia_deals.json","style.css"]:
    shutil.copy(f, "preview/"+f)
print("ok")
