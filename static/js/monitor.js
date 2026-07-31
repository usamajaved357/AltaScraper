// ============ ASIN MONITOR — tracking list (Stage 2) ============
// Standalone competitor/hijacker watch, separate from listing generation. This stage is
// the tracking list only: add/remove ASINs, each with a label and which EU marketplaces to
// check. The hourly checker + alerts + history come in Stage 3/4.

let MON_EU = ["UK","DE","FR","IT","ES","NL","PL","SE","BE","IE"];
let MON_LIST = [];

function monitorOnOpen(){ loadMonitorList(); loadMonitorAlerts(); }

// ---- alerts / status / manual check ----------------------------------------
const MON_ALERT_META = {
  new_seller:    {icon:"ti-user-plus",   cls:"na", label:"New seller"},
  seller_removed:{icon:"ti-user-minus",  cls:"sr", label:"Seller left"},
  price_change:  {icon:"ti-tag",         cls:"pc", label:"Price change"},
  buybox_change: {icon:"ti-award",       cls:"bb", label:"Buy Box changed"},
};

async function loadMonitorAlerts(){
  const host = document.getElementById("mon_alerts");
  try{
    const j = await (await fetch("/monitor/alerts")).json();
    if(!j || !j.ok){ return; }
    updateMonBadge(j.unread||0);
    renderMonStatus(j.status||{});
    if(!host) return;
    const al = j.alerts || [];
    if(!al.length){
      host.innerHTML = '<div class="cc" style="padding:10px 2px;opacity:.7">No alerts yet. When a new seller appears on a tracked ASIN, it shows here.</div>';
      return;
    }
    host.innerHTML = al.map(monAlertCard).join("");
  }catch(e){ /* alerts are additive */ }
}

function monAlertCard(a){
  const m = MON_ALERT_META[a.type] || {icon:"ti-bell", cls:"", label:a.type};
  const seller = a.seller_name
    ? `${esc(a.seller_name)} <span class="cc">(${esc(a.seller_id||"")})</span>`
    : `<span class="cc">${esc(a.seller_id||"unknown seller")}</span>`;
  const fb = (a.feedback_pct!==null && a.feedback_pct!==undefined)
    ? ` · ${esc(String(a.feedback_pct))}% (${esc(String(a.feedback_count||0))})` : "";
  const price = (a.price!==null && a.price!==undefined)
    ? ` · ${esc(String(a.price))} ${esc(a.currency||"")} ${a.fba?"(FBA)":"(FBM)"}` : "";
  const store = a.storefront ? ` · <a href="${esc(a.storefront)}" target="_blank" rel="noopener">storefront ↗</a>` : "";
  return `<div class="monalert ${m.cls} ${a.read?'read':''}">
    <div class="ma-ic"><i class="ti ${m.icon}"></i></div>
    <div class="ma-body">
      <div class="ma-top"><b>${esc(m.label)}</b> · <span class="ma-asin">${esc(a.asin||"")}</span>
        <span class="monchip">${esc(a.marketplace||"")}</span>
        ${a.label?`<span class="cc">${esc(a.label)}</span>`:''}
        <span class="spacer"></span><span class="cc ma-ts">${esc(a.ts||"")}</span></div>
      <div class="ma-mid">Seller: ${seller}${fb}${price}${store}</div>
      ${a.detail?`<div class="cc ma-det">${esc(a.detail)}</div>`:''}
    </div></div>`;
}

function renderMonStatus(st){
  const el = document.getElementById("mon_status"); if(!el) return;
  if(st.running){ el.innerHTML = '<span class="genspin"></span> checking…'; return; }
  if(st.last_run){
    const okTxt = st.last_run_ok===false ? ' <span style="color:#e3b768">(some checks failed — see terminal)</span>' : '';
    el.innerHTML = `Last check: ${esc(st.last_run)} · ${esc(String(st.checks||0))} call(s)${okTxt}`;
  } else { el.textContent = "Not run yet — runs hourly while the app is open."; }
}

function updateMonBadge(n){
  const b = document.getElementById("mon_badge"); if(!b) return;
  if(n>0){ b.textContent = n>99?"99+":String(n); b.style.display=""; }
  else { b.style.display="none"; b.textContent=""; }
}

async function monCheckNow(){
  const btn = document.getElementById("mon_checkbtn");
  if(btn){ btn.disabled = true; }
  try{
    const j = await (await fetch("/monitor/check_now",{method:"POST"})).json();
    if(!j || !j.ok){ toast("Could not start: "+((j&&j.error)||"unknown")); return; }
    toast("Checking tracked ASINs now…");
    // poll a few times while it runs
    let n=0; const iv=setInterval(async ()=>{
      await loadMonitorAlerts();
      const s = await (await fetch("/monitor/status")).json();
      if((!s.status || !s.status.running) || ++n>40){ clearInterval(iv); if(btn) btn.disabled=false; }
    }, 3000);
  }catch(e){ toast("Check error: "+e); if(btn) btn.disabled=false; }
}

async function monMarkAllRead(){
  try{
    await fetch("/monitor/alerts/read",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
    loadMonitorAlerts();
  }catch(e){}
}

// ---- offer history viewer (Stage 4) ----------------------------------------
let MON_NAMES = {};
function _monSellerLabel(sid, mkt){
  if(!sid) return '<span class="cc">—</span>';
  const nm = MON_NAMES[sid+"::"+mkt];
  const link = `https://www.amazon.${_monTld(mkt)}/sp?seller=${encodeURIComponent(sid)}`;
  const inner = nm ? `${esc(nm)} <span class="cc">(${esc(sid)})</span>` : esc(sid);
  return `<a href="${link}" target="_blank" rel="noopener">${inner}</a>`;
}
function _monTld(mkt){
  const m={UK:"co.uk",GB:"co.uk",DE:"de",FR:"fr",IT:"it",ES:"es",NL:"nl",PL:"pl",SE:"se",BE:"com.be",IE:"ie"};
  return m[String(mkt||"").toUpperCase()]||"co.uk";
}
function _lowestLanded(offers){
  const vals=(offers||[]).map(o=>o.landed).filter(v=>v!==null&&v!==undefined);
  return vals.length?Math.min.apply(null,vals):null;
}

async function openMonHistory(asin, label){
  if(document.getElementById("monhistwrap")) closeMonHistory();
  const dlg=document.createElement("div");
  dlg.className="modalwrap open"; dlg.id="monhistwrap"; dlg.style.zIndex="130";
  dlg.innerHTML=`<div class="modal" style="max-width:900px;position:relative">
    <button class="x" onclick="closeMonHistory()">×</button>
    <h3><i class="ti ti-history"></i> Offer history — <span class="ma-asin">${esc(asin)}</span>${label?` <span class="cc">${esc(label)}</span>`:''}</h3>
    <div id="monhist_body"><div class="cc" style="padding:14px"><span class="genspin"></span> Loading…</div></div>
  </div>`;
  document.body.appendChild(dlg);
  try{
    const j=await (await fetch("/monitor/history?asin="+encodeURIComponent(asin))).json();
    const body=document.getElementById("monhist_body"); if(!body) return;
    if(!j || !j.ok){ body.innerHTML='<div class="cc" style="color:#e0696b;padding:14px">'+esc((j&&j.error)||"could not load")+'</div>'; return; }
    MON_NAMES = j.names || {};
    const hist = j.history || {};
    const keys = Object.keys(hist).sort();
    if(!keys.length){ body.innerHTML='<div class="cc" style="padding:14px;opacity:.75">No checks recorded yet for this ASIN. Hit “Check now”, then open this again.</div>'; return; }
    body.innerHTML = keys.map(k=>{
      const mkt = k.split("::")[1]||"";
      const snaps = (hist[k]||[]).slice().reverse();   // newest first
      let rows = snaps.map(s=>{
        const bb = _monSellerLabel(s.buybox_seller, mkt);
        const low = _lowestLanded(s.offers);
        const sellerCount = (s.seller_count!=null?s.seller_count:(s.sellers||[]).length);
        const cur = ((s.offers||[])[0]||{}).currency||"";
        return `<tr>
          <td class="cc">${esc(s.ts||"")}</td>
          <td style="text-align:center">${esc(String(sellerCount))}${s.total_offer_count&&s.total_offer_count>sellerCount?` <span class="cc">/${esc(String(s.total_offer_count))}</span>`:''}</td>
          <td>${low!=null?esc(String(low))+" "+esc(cur):'<span class="cc">—</span>'}</td>
          <td>${bb}</td>
          <td>${_monSnapSellers(s, mkt)}</td>
        </tr>`;
      }).join("");
      return `<div class="monhist-mkt"><div class="monhist-h"><span class="monchip">${esc(mkt)}</span> ${snaps.length} check(s)</div>
        <div style="overflow-x:auto"><table class="monhisttable">
          <thead><tr><th>When</th><th>Sellers</th><th>Lowest</th><th>Buy Box</th><th>Who was present</th></tr></thead>
          <tbody>${rows}</tbody></table></div></div>`;
    }).join("");
  }catch(e){ const body=document.getElementById("monhist_body"); if(body) body.innerHTML='<div class="cc" style="color:#e0696b;padding:14px">Error: '+esc(String(e))+'</div>'; }
}
function _monSnapSellers(s, mkt){
  const ids = (s.sellers||[]);
  if(!ids.length) return '<span class="cc">—</span>';
  const bb = s.buybox_seller;
  return ids.slice(0,12).map(id=>{
    const nm = MON_NAMES[id+"::"+mkt];
    const cls = (id===bb)?'monhs bb':'monhs';
    return `<span class="${cls}" title="${esc(nm||id)}">${esc(nm? nm.slice(0,14) : id)}</span>`;
  }).join(" ") + (ids.length>12?` <span class="cc">+${ids.length-12}</span>`:"");
}
function closeMonHistory(){ const w=document.getElementById("monhistwrap"); if(w) w.remove(); }

// Global badge poll so the nav count stays fresh even when not on the section.
async function refreshMonBadge(){
  try{
    const j = await (await fetch("/monitor/status")).json();
    if(j && j.ok) updateMonBadge(j.unread||0);
  }catch(e){}
}
setInterval(refreshMonBadge, 120000);
setTimeout(refreshMonBadge, 8000);

async function loadMonitorList(){
  const host = document.getElementById("mon_list");
  if(host) host.innerHTML = '<div class="cc" style="padding:14px;opacity:.7"><span class="genspin"></span> Loading tracked ASINs…</div>';
  try{
    const j = await (await fetch("/monitor/list")).json();
    if(!j || !j.ok){ if(host) host.innerHTML = '<div class="cc" style="color:#e0696b;padding:14px">Could not load: '+esc((j&&j.error)||"unknown")+'</div>'; return; }
    MON_EU = j.eu_marketplaces || MON_EU;
    MON_LIST = j.asins || [];
    renderMonitorMarketPicker();
    renderMonitorList();
  }catch(e){ if(host) host.innerHTML = '<div class="cc" style="color:#e0696b;padding:14px">Error: '+esc(String(e))+'</div>'; }
}

// The EU marketplace checkboxes on the add form (default: all ticked).
function renderMonitorMarketPicker(){
  const box = document.getElementById("mon_markets");
  if(!box) return;
  box.innerHTML = MON_EU.map(m =>
    `<label class="monmkt"><input type="checkbox" value="${esc(m)}" checked> ${esc(m)}</label>`
  ).join("");
}
function _monSelectedMarkets(){
  const box = document.getElementById("mon_markets");
  if(!box) return [];
  return Array.prototype.slice.call(box.querySelectorAll("input:checked")).map(i=>i.value);
}
function monMarketsAll(on){
  const box = document.getElementById("mon_markets"); if(!box) return;
  box.querySelectorAll("input[type=checkbox]").forEach(i=>{ i.checked = !!on; });
}

function renderMonitorList(){
  const host = document.getElementById("mon_list");
  if(!host) return;
  if(!MON_LIST.length){
    host.innerHTML = '<div class="cc" style="padding:16px;opacity:.7">No ASINs tracked yet. Add one above to start watching it for new sellers.</div>';
    return;
  }
  let html = '<table class="montable"><thead><tr>'
    + '<th>ASIN</th><th>Label</th><th>Marketplaces</th><th>Condition</th><th>Added</th><th></th>'
    + '</tr></thead><tbody>';
  MON_LIST.forEach(r=>{
    const mkts = (r.marketplaces||[]);
    const mkChips = mkts.length===MON_EU.length
      ? '<span class="monchip all">all EU</span>'
      : mkts.map(m=>`<span class="monchip">${esc(m)}</span>`).join(" ");
    html += '<tr>'
      + `<td><a href="https://www.amazon.co.uk/dp/${esc(r.asin)}" target="_blank" rel="noopener" class="monasin">${esc(r.asin)}</a></td>`
      + `<td>${esc(r.label||"")||'<span class="cc">—</span>'}</td>`
      + `<td>${mkChips}</td>`
      + `<td>${esc(r.condition||"New")}</td>`
      + `<td class="cc">${esc(r.added_at||"")}</td>`
      + `<td style="white-space:nowrap">`
      +   `<button class="monhist" title="View offer history for this ASIN" onclick="openMonHistory('${esc(r.asin)}','${esc((r.label||'').replace(/'/g,""))}')"><i class="ti ti-history"></i></button> `
      +   `<button class="monrm" title="Stop tracking this ASIN" onclick="removeMonitorAsin('${esc(String(r.id))}','${esc(r.asin)}')"><i class="ti ti-trash"></i></button>`
      + `</td>`
      + '</tr>';
  });
  html += '</tbody></table>';
  host.innerHTML = html;
  const c = document.getElementById("mon_count");
  if(c) c.textContent = MON_LIST.length + " ASIN" + (MON_LIST.length!==1?"s":"") + " tracked";
}

async function addMonitorAsin(){
  const asinEl = document.getElementById("mon_asin");
  const labelEl = document.getElementById("mon_label");
  const asin = (asinEl&&asinEl.value||"").trim().toUpperCase();
  const label = (labelEl&&labelEl.value||"").trim();
  const markets = _monSelectedMarkets();
  if(!asin){ toast("Enter an ASIN"); if(asinEl) asinEl.focus(); return; }
  if(!/^[A-Z0-9]{10}$/.test(asin)){ toast("ASIN must be 10 letters/digits, e.g. B0XXXXXXXX"); return; }
  if(!markets.length){ toast("Pick at least one marketplace"); return; }
  const btn = document.getElementById("mon_addbtn");
  if(btn){ btn.disabled = true; }
  try{
    const j = await (await fetch("/monitor/add",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({asin, label, marketplaces:markets, condition:"New"})})).json();
    if(!j || !j.ok){ toast("Add failed: "+((j&&j.error)||"unknown")); return; }
    toast(j.updated ? ("Updated "+asin) : ("Now tracking "+asin));
    if(asinEl) asinEl.value = "";
    if(labelEl) labelEl.value = "";
    monMarketsAll(true);
    loadMonitorList();
  }catch(e){ toast("Add error: "+e); }
  finally{ if(btn) btn.disabled = false; }
}

async function removeMonitorAsin(id, asin){
  if(!confirm("Stop tracking "+(asin||"this ASIN")+"?")) return;
  try{
    const j = await (await fetch("/monitor/remove",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id, asin})})).json();
    if(!j || !j.ok){ toast("Remove failed: "+((j&&j.error)||"unknown")); return; }
    toast("Stopped tracking "+(asin||""));
    loadMonitorList();
  }catch(e){ toast("Remove error: "+e); }
}
