// ============ ASIN MONITOR — tracking list (Stage 2) ============
// Standalone competitor/hijacker watch, separate from listing generation. This stage is
// the tracking list only: add/remove ASINs, each with a label and which EU marketplaces to
// check. The hourly checker + alerts + history come in Stage 3/4.

let MON_EU = ["UK","DE","FR","IT","ES","NL","PL","SE","BE","IE"];
let MON_LIST = [];

function monitorOnOpen(){ loadMonitorList(); }

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
      + `<td><button class="monrm" title="Stop tracking this ASIN" onclick="removeMonitorAsin('${esc(String(r.id))}','${esc(r.asin)}')"><i class="ti ti-trash"></i></button></td>`
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
