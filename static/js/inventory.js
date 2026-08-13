// ---------- Inventory section ----------
async function invRunBuild(){
  const resBox = document.getElementById("inv_result");
  const pl3 = document.getElementById("inv_pl3");
  const sales = document.getElementById("inv_sales");
  const yoy = document.getElementById("inv_yoy");
  const pd = document.getElementById("inv_pd");
  if(!pl3.files || !pl3.files[0]){ resBox.innerHTML='<div style="color:var(--red);font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">3PL stock CSV is required.</div>'; return; }
  if(!sales.files || !sales.files[0]){ resBox.innerHTML='<div style="color:var(--red);font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">Daily sales CSV is required.</div>'; return; }
  resBox.innerHTML='<div class="cc"><span class="genspin"></span> Pulling FBA inventory from SP-API + computing replenishment for every SKU…</div>';
  const fd = new FormData();
  fd.append("pl3_file", pl3.files[0]);
  fd.append("sales_file", sales.files[0]);
  if(yoy.files && yoy.files[0]) fd.append("yoy_file", yoy.files[0]);
  if(pd.files && pd.files[0]) fd.append("pd_file", pd.files[0]);
  fd.append("target_normal_days", document.getElementById("inv_normal").value || "85");
  fd.append("reorder_cycle_days", document.getElementById("inv_reorder").value || "5");
  fd.append("target_long_days", document.getElementById("inv_long").value || "110");
  fd.append("marketplace", WS_MARKET || "UK");
  fd.append("cycle_label", document.getElementById("inv_cycle").value || "");
  try{
    const j = await (await fetch("/inventory/build",{method:"POST", body:fd})).json();
    if(!j.ok){
      resBox.innerHTML='<div style="color:var(--red);font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">'+esc(j.error||"build failed")+'</div>';
      return;
    }
    const s = j.summary || {};
    const c = j.sku_coverage || {};
    let html = '<div style="padding:12px;border:1px solid var(--line);border-radius:8px">';
    html += '<div style="font-weight:600;margin-bottom:8px;color:var(--ok)">✓ Replenishment sheet built</div>';
    html += '<div style="display:flex;gap:14px;flex-wrap:wrap;font-size:12px;margin-bottom:10px">';
    html += '<div><b>'+j.row_count+'</b> SKUs total</div>';
    html += '<div><b style="color:#ffd76b">'+(s.replenish_yes||0)+'</b> flagged for replenishment</div>';
    html += '<div><b style="color:var(--ok)">'+(s.units_flagged||0)+'</b> units to reorder</div>';
    if(s.stockout_risk_skus){
      html += '<div><b style="color:var(--red)">'+s.stockout_risk_skus+'</b> stockout-risk SKUs (DOS &lt; 14)</div>';
    }
    html += '</div>';
    html += '<div style="font-size:11px;opacity:.75;margin-bottom:10px">SKU coverage — FBA (SP-API): '+(c.in_fba||0)+' · 3PL upload: '+(c.in_3pl||0)+' · Sales upload: '+(c.in_sales||0);
    if(c.in_yoy) html += ' · YoY: '+c.in_yoy;
    if(c.in_pd) html += ' · PD: '+c.in_pd;
    html += ' · Union: <b>'+(c.union||0)+'</b></div>';
    if(j.warnings && j.warnings.length){
      html += '<div style="margin-top:8px;padding:8px;border-radius:6px;background:#241a10;border:1px solid #4d3712;color:var(--warn);font-size:11px">';
      html += '<b>SP-API warnings:</b><br>' + j.warnings.map(esc).join("<br>");
      html += '</div>';
    }
    html += '<div style="margin-top:12px"><a href="'+j.download_url+'" download="'+j.filename+'" class="mktbtn on" style="display:inline-block;text-decoration:none;padding:8px 14px">⬇ Download replenishment xlsx</a></div>';
    html += '</div>';
    resBox.innerHTML = html;
  }catch(e){
    resBox.innerHTML='<div style="color:var(--red);font-size:12px;padding:8px">Request failed: '+esc(String(e))+'</div>';
  }
}

// ---------- v2 inventory handler (SP-API auto-fetch, 4-bucket classification) ----------
async function inv2Run(){
  const resBox = document.getElementById("inv2_result");
  const acctId = (CUR_ACCOUNT && CUR_ACCOUNT.id) || "";
  if(!acctId){
    resBox.innerHTML = '<div style="color:var(--red);font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">No workspace/account selected. Pick one from the sidebar first.</div>';
    return;
  }
  resBox.innerHTML = '<div class="cc"><span class="genspin"></span> Running inventory model — fetching FBA + sales from SP-API (5-15 min if cache is stale, instant if cached)…</div>';

  const fd = new FormData();
  fd.append("account_id", acctId);
  fd.append("marketplace", WS_MARKET || "US");
  fd.append("target_normal_dos",       document.getElementById("inv2_normal").value  || "85");
  fd.append("reorder_cycle_days",      document.getElementById("inv2_reorder").value || "5");
  fd.append("target_long_horizon_dos", document.getElementById("inv2_long").value    || "110");
  fd.append("sales_window_days",       document.getElementById("inv2_window").value  || "30");
  fd.append("cache_hours",             document.getElementById("inv2_cache").value   || "6");
  fd.append("force_refresh",           document.getElementById("inv2_force").checked ? "true" : "false");
  const three_pl_file = document.getElementById("inv2_3pl");
  if(three_pl_file.files && three_pl_file.files[0]) fd.append("three_pl_file", three_pl_file.files[0]);

  try{
    const j = await (await fetch("/inventory/v2/run",{method:"POST", body:fd})).json();
    if(!j.ok){
      resBox.innerHTML = '<div style="color:var(--red);font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">'+esc(j.error||"run failed")+'</div>';
      return;
    }
    const s = j.summary || {};
    let html = '<div style="padding:12px;border:1px solid var(--line);border-radius:8px">';
    html += '<div style="font-weight:600;margin-bottom:8px;color:var(--ok)">✓ Inventory model complete</div>';

    // Bucket counts
    html += '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px;font-size:12px">';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#1c3a1c;color:#8adca0;border:1px solid #2a7a2a">ACTIVE '+(s.active||0)+'</div>';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#3a3a1c;color:#ffe066;border:1px solid #7a7a2a">NEW_LAUNCH '+(s.new_launch||0)+'</div>';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#3a2f1a;color:#ffce7a;border:1px solid #7a5a2a">DORMANT '+(s.dormant||0)+'</div>';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#3a1f1f;color:var(--red);border:1px solid #7a2a2a">DEAD '+(s.dead||0)+'</div>';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#1c2a3a;color:#8ac0ff;border:1px solid #2a5a7a">Total '+(s.total_skus||0)+'</div>';
    html += '</div>';

    // Reorder summary
    html += '<div style="display:flex;gap:14px;flex-wrap:wrap;font-size:12px;margin-bottom:10px">';
    html += '<div><b style="color:#ffd76b">'+(s.fba_reorder_count||0)+'</b> SKUs need FBA reorder</div>';
    html += '<div><b>'+Math.round(s.total_fba_units_needed||0).toLocaleString()+'</b> total FBA units</div>';
    if(s.three_pl_reorder_count) html += '<div><b>'+s.three_pl_reorder_count+'</b> SKUs need 3PL reorder</div>';
    html += '</div>';

    // Data sources
    html += '<div style="font-size:11px;opacity:.75;margin-bottom:10px;line-height:1.5">';
    html += '<b>FBA source:</b> '+esc(j.fba_source||"")+'<br>';
    html += '<b>Velocity source:</b> '+esc(j.velocity_source||"");
    html += '</div>';

    // Sample alerts
    if(j.alerts_sample && j.alerts_sample.length){
      html += '<div style="margin-top:8px;padding:8px;border-radius:6px;background:#241a10;border:1px solid #4d3712;color:var(--warn);font-size:11px">';
      html += '<b>Sample alerts (first 10):</b>';
      html += '<ul style="margin:6px 0 0 18px">';
      j.alerts_sample.forEach(a=>{
        html += '<li>'+esc(a.sku)+' — '+esc(a.alert)+'</li>';
      });
      html += '</ul></div>';
    }
    if(j.three_pl_warnings && j.three_pl_warnings.length){
      html += '<div style="margin-top:8px;padding:8px;border-radius:6px;background:#241a10;border:1px solid #4d3712;color:var(--warn);font-size:11px">';
      html += '<b>3PL CSV warnings:</b><br>'+j.three_pl_warnings.map(esc).join("<br>");
      html += '</div>';
    }
    html += '<div style="margin-top:12px"><a href="'+j.download_url+'" download="'+j.filename+'" class="mktbtn on" style="display:inline-block;text-decoration:none;padding:8px 14px">⬇ Download inventory xlsx</a></div>';
    html += '</div>';
    resBox.innerHTML = html;

    // Refresh the sidebar alert badge
    invBadgeRefresh();
  }catch(e){
    resBox.innerHTML = '<div style="color:var(--red);font-size:12px;padding:8px">Request failed: '+esc(String(e))+'</div>';
  }
}

// Polls /inventory/v2/alerts and updates the sidebar red badge
async function invBadgeRefresh(){
  const badge = document.getElementById("inv_badge");
  if(!badge) return;
  const acctId = (CUR_ACCOUNT && CUR_ACCOUNT.id) || "";
  if(!acctId){ badge.style.display="none"; return; }
  try{
    const j = await (await fetch("/inventory/v2/alerts?account_id="+encodeURIComponent(acctId))).json();
    const n = j.count || 0;
    if(n > 0){
      badge.textContent = n;
      badge.style.display = "inline-block";
    } else {
      badge.style.display = "none";
    }
  }catch(e){ /* silent */ }
}
// ---------- /Inventory section ----------

// ---------------------------------------------------------------------------
// RUN LOG PANEL -- batched appends with a hard line cap.
//
// Why: every incoming line used to create a <div> AND read log.scrollHeight,
// which forces the browser to re-lay-out the whole panel. With thousands of
// lines that got slow enough that the browser stopped collecting the stream,
// which back-pressured all the way down the chain and froze the generator
// mid-print. Batching + capping keeps appends cheap no matter how long the run.
const LOG_MAX_LINES   = 3000;   // panel keeps the most recent N lines
const LOG_MAX_PENDING = 5000;   // safety net if the tab is backgrounded
let _logPending=[], _logTimer=0;

function _logFlush(log){
  _logTimer=0;
  if(!_logPending.length) return;
  const frag=document.createDocumentFragment();
  for(const item of _logPending){
    const div=document.createElement("div");
    div.className=item[0]; div.textContent=item[1];
    frag.appendChild(div);
  }
  _logPending.length=0;
  log.appendChild(frag);
  while(log.childElementCount>LOG_MAX_LINES) log.removeChild(log.firstChild);
  log.scrollTop=log.scrollHeight;   // one layout read per batch, not per line
}

function _logPush(log, cls, txt){
  _logPending.push([cls,txt]);
  if(_logPending.length>LOG_MAX_PENDING)
    _logPending.splice(0,_logPending.length-LOG_MAX_PENDING);
  // setTimeout (not requestAnimationFrame) so a backgrounded tab still drains.
  if(!_logTimer) _logTimer=setTimeout(()=>_logFlush(log),120);
}

function _logReset(){
  _logPending.length=0;
  if(_logTimer){ clearTimeout(_logTimer); _logTimer=0; }
}

// ---------------------------------------------------------------------------
// RUN HEALTH BADGE
//
// Deliberately does NOT read the log stream. The log travels down the same pipe
// that has twice jammed and frozen a run; a frozen log looks exactly like a
// quiet one. This polls /run/health, which combines the generator's heartbeat
// file with a real "is the process alive" check -- neither of which a jammed
// pipe can fake. So the badge stays truthful even when the log has stopped dead.
let _rhTimer=0, _rhLastState="";

function _rhRender(h){
  const box=document.getElementById("runhealth");
  if(!box) return;
  const label={RUNNING:"RUNNING",STALLED:"STUCK",STOPPED:"STOPPED",IDLE:"NOT RUNNING"};
  const cls ={RUNNING:"rh-running",STALLED:"rh-stalled",STOPPED:"rh-stopped",IDLE:"rh-idle"};
  box.style.display = (h.state==="IDLE" && !h.total) ? "none" : "flex";
  box.className = "runhealth " + (cls[h.state]||"rh-idle");
  document.getElementById("rh_state").textContent  = label[h.state]||h.state;
  document.getElementById("rh_detail").textContent = h.detail||"";
  // The stack dump is only meaningful while a stuck process still exists.
  document.getElementById("rh_why").style.display = (h.state==="STALLED")?"block":"none";
  if(h.state==="STALLED" && _rhLastState!=="STALLED")
    toast("Run looks stuck — no activity for a while");
  _rhLastState=h.state;
}

async function _rhPoll(){
  try{
    const r=await fetch("/run/health",{cache:"no-store"});
    _rhRender(await r.json());
  }catch(e){ /* dashboard unreachable; leave the last known state on screen */ }
}

function startRunHealth(){
  if(_rhTimer) return;
  _rhPoll();
  _rhTimer=setInterval(_rhPoll,3000);
}

async function whyStuck(){
  const log=document.getElementById("log");
  const btn=document.getElementById("rh_why");
  if(btn){ btn.disabled=true; btn.textContent="Looking…"; }
  try{
    const r=await fetch("/run/stack",{cache:"no-store"});
    const j=await r.json();
    const text = j.dump || j.error || "no answer";
    _logPush(log,"start","----- WHY IS IT STUCK (process "+(j.pid||"?")+") -----");
    text.split("\n").forEach(ln=>_logPush(log,"l",ln));
    _logPush(log,"start","----- end -----");
    _logFlush(log);
    log.style.display="block";
  }catch(e){
    toast("Could not read the stack: "+e);
  }finally{
    if(btn){ btn.disabled=false; btn.textContent="Why is it stuck?"; }
  }
}

document.addEventListener("DOMContentLoaded",startRunHealth);

function runMode(mode, skus){
  if(ES){toast("A run is already streaming");return;}
  const log=document.getElementById("log");
  _logReset();
  log.style.display="block"; log.textContent="";
  startRunHealth();
  let url="/run/"+mode;
  // Generate-only: pass the row selection (value + type). Empty -> generate all.
  if(mode==="generate"){
    const valEl=document.getElementById("gensel_value");
    const typeEl=document.getElementById("gensel_type");
    const val=(valEl&&valEl.value||"").trim();
    if(val){
      const params=new URLSearchParams();
      params.set("select", val);
      // when a URL is pasted the dropdown is disabled; send 'auto' so the server auto-detects
      params.set("select_type", (typeEl&&!typeEl.disabled)? typeEl.value : "auto");
      url += "?"+params.toString();
    }
  }
  // Preview/Submit: if specific SKUs are passed (the user's SELECTION), scope the
  // run to exactly those. Empty -> the server's default (all approved/ready rows).
  if((mode==="api"||mode==="api_submit") && skus && skus.length){
    url += (url.indexOf("?")>=0?"&":"?")+"skus="+encodeURIComponent(skus.join(","));
  }
  ES=new EventSource(url);
  showStop(true);
  ES.onmessage=e=>{
    const cls = e.data.startsWith("[start]")?"start":e.data.startsWith("[done]")?"done":"l";
    _logPush(log, cls, e.data);
  };
  ES.addEventListener("end",()=>{_logFlush(log);ES.close();ES=null;showStop(false);loadRows();toast("Run finished");});
  ES.onerror=()=>{if(ES){_logFlush(log);ES.close();ES=null;showStop(false);loadRows();}};
}
