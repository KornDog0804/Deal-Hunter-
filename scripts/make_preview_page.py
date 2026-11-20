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
  const v = vrow(d)
  if(v){
    const ok = v.verified, net = v.net
    let h2 = `<span class="pill ${ok?"ok":"warn"}">${esc(v.status.replace("_"," "))} ${Math.round((v.confidence||0)*100)}%</span><span class="pill dim">Prod: ${esc(prod)}</span>`
    if(prod==="BUY NOW") h2 += `<span class="pill ${ok&&net>=5&&v.roi>=25?"ok":"bad"}">${ok&&net>=5&&v.roi>=25?"BUY NOW holds":"Preview: WATCH"}</span>`
    if(net!==undefined) h2 += `<br>Landed $${v.landed.toFixed(2)} &middot; resale est. $${v.resale.toFixed(2)} <small>(Discogs asking${v.lowest_ask?", low ask $"+v.lowest_ask.toFixed(2):""})</small><br>Net ${net>=0?"+":""}$${net.toFixed(2)} &middot; ROI ${v.roi}% <small>${v.inputs_complete?"":"(inbound shipping/tax unset)"}</small>`
    else h2 += `<br><small>${ok?"No resale estimate":"Not a verified pressing: no valuation shown"}</small>`
    return `<div class="pv">${h2}</div>`
  }
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

# ---- validated results: summary panel, filters, per-card validated values ----
rep('<div class="tabs">', """<div class="pvBanner" id="pvSummary"></div>
<div class="pvFilters" id="pvFilters">
  <label>Min net $<input id="fNet" type="number" step="1" inputmode="decimal" placeholder="5"></label>
  <label>Min ROI %<input id="fRoi" type="number" step="1" inputmode="decimal" placeholder="25"></label>
  <label>Max price $<input id="fMaxP" type="number" step="1" inputmode="decimal" placeholder="any"></label>
  <label>Match<select id="fMatch"><option value="">Any</option><option value="verified">Verified (exact/strong)</option><option value="title_only">Title only (unverified)</option><option value="ambiguous">Ambiguous</option><option value="none">Unmatched</option><option value="not_validated">Not validated</option></select></label>
  <label>Load results<input id="fFile" type="file" accept=".json" multiple></label>
</div>
<div class="tabs">""")
rep("</style>", """
.pvFilters{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}
.pvFilters label{font-size:11px;opacity:.85;display:flex;flex-direction:column;gap:3px}
.pvFilters input,.pvFilters select{padding:9px;border-radius:10px;border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.06);color:inherit;font-size:14px}
.pvGrid{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;margin-top:8px}
.pvGrid div{background:rgba(255,255,255,.06);border-radius:10px;padding:8px}.pvGrid b{display:block;font-size:20px;color:#fff}
</style>""")
rep("let PV = {providers:[],overlay:{},gate_on:false}", """let PV = {providers:[],overlay:{},gate_on:false}
let VAL = {}, VSUM = null, VORD = []
function vrow(d){ return VAL[d.link] }
function pvVals(d){
  const v = vrow(d), o = PV.overlay[d.link] || {}
  if(v) return {match: v.status, verified: !!v.verified, net: v.net, roi: v.roi, src: "validated"}
  if(VSUM) return {match: "not_validated", verified:false, net: undefined, roi: undefined, src: "none"}
  return {match: o.legacy ? "legacy" : "not_validated", verified:false, net: o.net, roi: o.roi, src: "legacy"}
}
function pvPass(d){
  const x = pvVals(d), n = id => { const t = document.getElementById(id).value; return t === "" ? null : Number(t) }
  const net = n("fNet"), roi = n("fRoi"), maxp = n("fMaxP"), m = document.getElementById("fMatch").value
  if(net !== null && !(x.net !== undefined && x.net >= net)) return false
  if(roi !== null && !(x.roi !== undefined && x.roi >= roi)) return false
  if(maxp !== null && !(number(d.price) > 0 && number(d.price) <= maxp)) return false
  if(m === "verified" && !x.verified) return false
  if(m && m !== "verified" && x.match !== m) return false
  return true
}
function renderSummary(){
  const el = document.getElementById("pvSummary")
  if(!VSUM){
    el.innerHTML = "<b>Validation not run yet.</b> No live Discogs results are loaded, so the numbers on cards are legacy-cache estimates (unvalidated). Run the GitHub workflow, then load <b>validation_results.json</b> and <b>validation_summary.json</b> with “Load results” below."
    return
  }
  const s = VSUM, v = s.verified_only || {}, t = s.thresholds || {}
  const c = (n,l) => `<div><b>${Number(n||0).toLocaleString()}</b>${l}</div>`
  el.innerHTML = `<b>Live Discogs validation</b> ${s.complete?"(complete)":"(partial: "+s.unique_pressings_done+" of "+s.unique_pressings_total+" pressings)"} &middot; ${esc((s.generated_at||"").slice(0,16))}<br><small>Resale = Discogs asking-price estimate, not sold prices. Profit/ROI below count VERIFIED matches only.</small>
  <div class="pvGrid">${c(s.listings_scanned,"records scanned")}${c(s.verified_pressing_matches,"verified pressing matches")}${c(s.with_resale_estimate,"with resale estimate")}${c(s.title_only_unverified,"title-only (unverified)")}${c(s.ambiguous,"ambiguous")}${c(s.unmatched,"unmatched")}${c(v.net_ge_min,"net ≥ $"+t.min_net_usd)}${c(v.roi_ge_min,"ROI ≥ "+t.min_roi_percent+"%")}${c(v.both,"meet both")}${c(s.prod_buy_now_verified_and_profitable,"prod BUY NOW that qualify")}</div>`
}
document.addEventListener("DOMContentLoaded", ()=>{
  ["fNet","fRoi","fMaxP","fMatch"].forEach(id => document.getElementById(id).addEventListener("input", ()=>{ currentPage = 1; render() }))
  document.getElementById("fFile").addEventListener("change", async e => {
    for(const f of e.target.files){
      try{
        const j = JSON.parse(await f.text())
        if(Array.isArray(j) && j.length && j[0].records !== undefined) VORD = j
        else if(Array.isArray(j)) { VAL = {}; j.forEach(r => { if(r.link) VAL[r.link] = r }) }
        else if(j.listings_total !== undefined) VSUM = j
      }catch(err){ console.error(err) }
    }
    renderSummary(); currentPage = 1; render()
  })
})
""")
rep("    const q = qualityOf(d)\n    const score = scoreOf(d)", "    if(!pvPass(d)) return false\n    const q = qualityOf(d)\n    const score = scoreOf(d)")

rep("<title>KornDog Deal Hunter</title>", "<title>KornDog Deal Hunter (PREVIEW)</title>")
open("preview/index.html", "w").write(s)
for f in ["live_deals.json","buy_signals.json","mini_vinyl_deals.json","collectibles_deals.json","olivia_deals.json","style.css"]:
    shutil.copy(f, "preview/"+f)
print("ok")
