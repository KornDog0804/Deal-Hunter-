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
rep('<button class="tab" data-view="olivia">', '<button class="tab" data-view="verified">\n  ✅ VERIFIED DEALS\n</button>\n\n<button class="tab" data-view="unverified">\n  🔎 UNVERIFIED OPPORTUNITIES\n</button>\n\n<button class="tab" data-view="health">\n  🩺 HEALTH\n</button>\n\n<button class="tab" data-view="olivia">')
rep("let liveDeals = []", "let liveDeals = []\nlet PV = {providers:[],overlay:{},gate_on:false}\n"
 """
function pvBlock(d){
  const o = PV.overlay[d.link]
  if(!o) return ""
  const prod = o.p
  const after = (prod==="BUY NOW" && !o.g) ? "WATCH" : prod
  const v = vrow(d)
  if(v){
    const ok = v.verified, net = v.net, lk = v.tier==="likely"
    const pass = net!==undefined && net>=5 && v.roi>=25
    let h2 = `<span class="pill ${ok?"ok":lk?"warn":"dim"}">${ok?"Verified":lk?"Likely":esc(v.status.replace("_"," "))} ${Math.round((v.confidence||0)*100)}%</span><span class="pill dim">Prod: ${esc(prod)}</span>`
    if(prod==="BUY NOW") h2 += ok ? `<span class="pill ${pass?"ok":"bad"}">${pass?"BUY NOW holds":"Preview: WATCH"}</span>` : `<span class="pill bad">Preview: ${lk&&pass?"BUY LIGHT":"WATCH"}</span>`
    if(v.manual_check && v.manual_check.length) h2 += `<br><span class="pill warn">⚑ verify by hand: ${v.manual_check.map(esc).join("; ")}</span>`
    if(ok) h2 += `<br><span class="pill ${v.recommendation_eligible?"ok":"dim"}">${v.recommendation_eligible?"eligible for a buy recommendation (auto-buy is off)":"not eligible for recommendation"}</span>`
    if(v.thin_market) h2 += `<br><span class="pill bad">⚠ thin market: only ${v.market_depth} cop${v.market_depth==1?"y":"ies"} for sale, one ask is not a market price</span>`
    const idu = v.identifiers_used || {}, idk = Object.keys(idu)
    h2 += `<br><small>IDs from store: ${idk.length ? idk.map(k=>esc(k)+" "+esc(String(idu[k]))).join(", ") : "none"}${idu.sku&&!idu.catno?" (SKU is a store code, not a catalog number)":""}</small>`
    if(v.suspect) h2 += `<br><span class="pill bad">⚠ ROI over 300%: probably a wrong match, check by hand</span>`
    if(net!==undefined) h2 += `<br>Landed $${v.landed.toFixed(2)} &middot; ${lk?"Lowest Asking Price Estimate":"resale est."} $${v.resale.toFixed(2)} <small>(${lk?"cheapest current Discogs ask across possible pressings, not a guaranteed resale value"+(v.floor_wide?", prices vary widely":""):"Discogs price guide NM"+(v.lowest_ask?", low ask $"+v.lowest_ask.toFixed(2):"")}${v.market_depth!=null?", "+v.market_depth+" for sale":""})</small><br>${esc(v.net_label||"Net")} ${net>=0?"+":""}$${net.toFixed(2)} &middot; ROI ${v.roi}% <small>${v.inputs_complete?"":"(missing costs counted as $0: "+(v.missing||[]).join(", ")+")"}</small>${v.cost_certainty?`<br><small>Known: customer shipping, postage, packaging, Discogs 9%, PayPal 3.49%+$0.49. Estimated: resale price. Missing: ${(v.cost_certainty.missing||[]).length?v.cost_certainty.missing.join(", "):"none"}</small>`:""}${lk?"<br><small>Pressing unverified: cannot be BUY NOW</small>":""}`
    else h2 += `<br><small>${ok?"No resale estimate":"No usable Discogs price: no valuation shown"}</small>`
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
function coveragePanel(){
  const rows = Object.entries(COV).sort((a,b)=>b[1].pct_any_strong_id-a[1].pct_any_strong_id)
  const tot = rows.reduce((t,[n,c])=>t+c.listings,0), bc = rows.reduce((t,[n,c])=>t+c.barcode,0)
  return `<div class="pv"><b>Identifier coverage by provider</b> <small>(${tot} listings probed; ${bc} with a valid UPC/EAN)</small>` + rows.map(([n,c])=>`<br>${esc(n)}: ${c.listings} listings &middot; barcode ${c.barcode} (${c.pct_barcode}%) &middot; SKU only ${c.sku_only} &middot; catalog# ${c.labelled_catno} <small>${esc(c.status)}${c.via?" ("+esc(c.via)+")":""}</small>`).join("") + `<br><small>A SKU is a store code. It is never treated as a confirmed catalog number.</small></div>`
}
function healthPanel(){
  const p = PV.providers, ok = p.filter(x=>x.status==="ok").length
  const rows = p.map(x=>`<div class="hrow"><div><div class="n">${esc(x.name)}</div>${x.errors.map(e=>`<div class="e">${esc(e)}</div>`).join("")}</div>
    <div><span class="pill ${x.status==="ok"?"ok":"bad"}" style="padding:2px 8px;border-radius:99px;font-size:11px;background:${x.status==="ok"?"#12391f":"#43181b"};color:${x.status==="ok"?"#7be3a0":"#ff8d94"}">${x.status==="ok"?x.listings+" listings":x.status}</span></div></div>`).join("")
  const bn = Object.values(PV.overlay).filter(o=>o.p==="BUY NOW")
  const F = PV.fees
  const feeHtml = F ? `<div class="pv"><b>Fees (verified ${esc(F.verified.checked)})</b><br>Discogs: <b>${F.marketplace_fee_pct}%</b> on item + shipping (Discogs help center).<br>PayPal Checkout: <b>${F.payment_fee_pct}% + $${F.payment_fee_flat_usd}</b>, verified on PayPal's official US merchant-fee page (updated May 19, 2026). Standard cards are 2.99% + $0.49 and Pay Later 4.99% + $0.49, so ${F.payment_fee_pct}% is the conservative default. International surcharges are not modelled.</div>` : ""
  const covHtml = COV ? coveragePanel() : `<div class="pv"><b>Identifier coverage</b><br><small>Not loaded yet: run the sample workflow and load identifier_coverage.json.</small></div>`
  const cmpHtml = CMP ? `<div class="pv"><b>Sample: old vs new matching</b> (${CMP.sample_size} listings)<br>Verified before: <b>${CMP.old_verified}</b> &rarr; now: <b>${CMP.new_verified}</b><br><small>${Object.entries(CMP.transitions).slice(0,12).map(([k,n])=>esc(k)+": "+n).join("<br>")}</small></div>` : ""
  const shipHtml = PV.inbound ? `<div class="pv"><b>Inbound shipping by provider</b> <small>(official store pages, checked ${esc(Object.values(PV.inbound.providers).map(x=>x.verified_on).filter(Boolean).sort().pop()||"never")}; unconfirmed values stay unset and are flagged as missing costs)</small>` + Object.entries(PV.inbound.providers).map(([n,x])=>`<br>${esc(n)}: ${x.status==="threshold_confirmed"||x.status==="rates_confirmed" ? `<b>${x.flat_usd!=null?"$"+x.flat_usd+" flat":"rate not published"}${x.free_over_usd!=null?", free over $"+x.free_over_usd:""}</b> <a href="${esc(x.source_url)}" target="_blank" rel="noopener">source</a> <small>${esc(x.verified_on)}</small>` : x.status==="not_published" ? `<small>store publishes no rate or threshold (checked ${esc(x.verified_on)})</small>` : `<small>not verified yet</small>`}`).join("") + `</div>` : ""
  const ordHtml = VORD.length ? `<div class="pv"><b>Best 3-record order per provider</b> <small>(likely/floor prices, suspect rows excluded)</small>` + VORD.slice().sort((a,b)=>b.net_profit_usd-a.net_profit_usd).slice(0,12).map(o=>`<br>${esc(o.source)}: ${o.records} rec &middot; net $${o.net_profit_usd.toFixed(2)} &middot; ROI ${o.roi_percent}% <small>(singles would total $${o.sum_of_single_nets_usd.toFixed(2)})</small>`).join("") + `</div>` : ""
  return `${feeHtml}${shipHtml}${covHtml}${cmpHtml}${ordHtml}<div class="hpanel"><div class="pv"><b>Providers: ${ok} of ${p.length} returned listings</b> (from last production run log)<br>
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
rep('  <option value="artist">Artist A-Z</option>\n</select>', '  <option value="artist">Artist A-Z</option>\n  <option value="net">Highest net profit</option>\n  <option value="roi">Highest ROI</option>\n  <option value="invest">Lowest investment</option>\n</select>')
rep("function render(){\n  const data = filtered()", "function render(){\n  if(view===\"health\"){ document.getElementById(\"pvViewNote\").style.display=\"none\"; $(\"resultCount\").textContent=\"Provider health\"; $(\"paginationTop\").innerHTML=\"\"; $(\"paginationBottom\").innerHTML=\"\"; $(\"grid\").innerHTML=healthPanel(); return }\n  const data = filtered()")
rep("    populateSources()\n    updateStats()", "    try{ const pr = await fetch(`preview_data.json?t=${Date.now()}`); if(pr.ok) PV = await pr.json() }catch(e){ console.error(e) }\n    try{ const [a,b,c,f] = await Promise.all(['validation_results.json','validation_summary.json','combined_orders.json','fee_verification.json'].map(u=>fetch(u))); if(a.ok&&b.ok){ (await a.json()).forEach(r=>{ if(r.link) VAL[r.link]=r }); VSUM = await b.json() } if(c.ok) VORD = await c.json(); if(f.ok) FEE = await f.json() }catch(e){ console.error(e) }\n    try{ const [cv,cm] = await Promise.all(['identifier_coverage.json','sample_comparison.json'].map(u=>fetch(u))); if(cv.ok) COV = await cv.json(); if(cm.ok) CMP = await cm.json() }catch(e){ console.error(e) }\n    renderSummary()\n    populateSources()\n    updateStats()")

# ---- validated results: summary panel, filters, per-card validated values ----
rep('<div class="tabs">', """<div class="pvBanner" id="pvSummary"></div>
<div class="pvBanner" id="pvViewNote" style="display:none"></div>
<div class="pvFilters" id="pvFilters">
  <label>Min net $<input id="fNet" type="number" step="1" inputmode="decimal" placeholder="5"></label>
  <label>Min ROI %<input id="fRoi" type="number" step="1" inputmode="decimal" placeholder="25"></label>
  <label>Max purchase budget $<input id="fMaxP" type="number" step="1" inputmode="decimal" placeholder="any"></label>
  <label>Match<select id="fMatch"><option value="">Any</option><option value="verified">Verified (exact/strong)</option><option value="likely">Unverified: Lowest Asking Price Estimate</option><option value="title_only">Title only (unverified)</option><option value="ambiguous">Ambiguous</option><option value="none">Unmatched</option><option value="not_validated">Not validated</option></select></label>
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
let VAL = {}, VSUM = null, VORD = [], FEE = null, COV = null, CMP = null
function vrow(d){ return VAL[d.link] }
function pvVals(d){
  const v = vrow(d), o = PV.overlay[d.link] || {}
  if(v) return {match: v.status, verified: !!v.verified, likely: v.tier==="likely", net: v.net, roi: v.roi, src: "validated"}
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
  if(m === "likely" && !x.likely) return false
  if(m && m !== "verified" && m !== "likely" && x.match !== m) return false
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
  el.innerHTML = `<b>${s.sample?"SAMPLE RUN: "+s.unique_pressings_total+" pressings, new matcher. All other listings are not validated yet.":"Live Discogs validation"}</b> ${s.complete?"(complete)":"(partial: "+s.unique_pressings_done+" of "+s.unique_pressings_total+" pressings)"} &middot; ${esc((s.generated_at||"").slice(0,16))}<br><small>Resale = Discogs asking-price estimate, not sold prices. Profit/ROI below count VERIFIED matches only.</small>
  <div class="pvGrid">${c(s.listings_scanned,"records scanned")}${c(s.verified_pressing_matches,"verified pressing matches")}${c(s.with_resale_estimate,"with resale estimate")}${c(s.title_only_unverified,"title-only (unverified)")}${c(s.ambiguous,"ambiguous")}${c(s.unmatched,"unmatched")}${c(v.net_ge_min,"net ≥ $"+t.min_net_usd)}${c(v.roi_ge_min,"ROI ≥ "+t.min_roi_percent+"%")}${c(v.both,"meet both")}${c((s.likely_tier||{}).count,"unverified w/ Lowest Asking Price Est.")}${c((s.likely_tier||{}).net_ge_min,"likely: net ≥ $"+t.min_net_usd)}${c((s.likely_tier||{}).both,"likely: meet both")}${c((s.likely_tier||{}).thin_market,"thin market (&lt;3 copies for sale)")}${c((s.likely_tier||{}).both_excluding_suspect,"…minus thin/suspect")}${c(s.incomplete_cost_rows,"valuations with incomplete costs")}${c(s.verified_manual_check,"verified: check by hand")}${c(s.recommendation_eligible,"recommendation-eligible")}${c(s.recommendation_eligible_meeting_thresholds,"eligible + meet both")}${c(s.prod_buy_now_verified_and_profitable,"prod BUY NOW that qualify")}</div>`
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
        else if(j.audit_pairs !== undefined) CMP = j
        else if(j && typeof j === 'object' && Object.values(j)[0] && Object.values(j)[0].listings !== undefined) COV = j
      }catch(err){ console.error(err) }
    }
    renderSummary(); currentPage = 1; render()
  })
})
""")
rep("    const q = qualityOf(d)\n    const score = scoreOf(d)", "    if(!pvPass(d)) return false\n    if(view === \"verified\" && !pvVals(d).verified) return false\n    if(view === \"unverified\" && !(pvVals(d).likely || pvVals(d).match === \"title_only\")) return false\n    const q = qualityOf(d)\n    const score = scoreOf(d)")
rep("  return data\n}", "  const _n = d => ((vrow(d)||{}).net) ?? -1e9, _r = d => ((vrow(d)||{}).roi) ?? -1e9, _i = d => ((vrow(d)||{}).landed) ?? (number(d.price) > 0 ? number(d.price) : 1e9)\n  if(sort === \"net\") data.sort((a,b) => _n(b) - _n(a))\n  else if(sort === \"roi\") data.sort((a,b) => _r(b) - _r(a))\n  else if(sort === \"invest\") data.sort((a,b) => _i(a) - _i(b))\n  else if(view === \"verified\" || view === \"unverified\") data.sort((a,b) => _n(b) - _n(a))\n  return data\n}")
rep("  const totalItems = data.length\n", "  const totalItems = data.length\n  const vn = document.getElementById(\"pvViewNote\")\n  if(view === \"verified\"){ vn.style.display = \"\"; vn.innerHTML = \"<b>Verified deals</b>: exact/strong Discogs pressing match (barcode or catalog number plus corroboration). Priced from the Discogs price guide. Sorted by net profit. \" + (totalItems ? \"\" : \"<br>None yet: stores rarely publish barcodes or catalog numbers. Unverified opportunities are on the next tab.\") }\n  else if(view === \"unverified\"){ vn.style.display = \"\"; vn.innerHTML = \"<b>Unverified opportunities</b>: the album is on Discogs but the exact pressing is not confirmed. Valued at the <b>Lowest Asking Price Estimate</b> (cheapest current ask), which is not a guaranteed resale value. Can never be BUY NOW. Check the pressing by hand before buying.\" }\n  else vn.style.display = \"none\"\n")

rep("<title>KornDog Deal Hunter</title>", "<title>KornDog Deal Hunter (PREVIEW)</title>")
open("preview/index.html", "w").write(s)
import os, glob
for f in glob.glob(os.path.join(os.environ.get("VALIDATION_DIR", "/nonexistent"), "*.json")):
    if os.path.basename(f) not in ("state.json","identifiers_by_link.json","baseline_results.json"): shutil.copy(f, "preview/" + os.path.basename(f))
for f in ["live_deals.json","buy_signals.json","mini_vinyl_deals.json","collectibles_deals.json","olivia_deals.json","style.css"]:
    shutil.copy(f, "preview/"+f)
print("ok")
