// ---------- Inventory section ----------
async function invRunBuild(){
  const resBox = document.getElementById("inv_result");
  const pl3 = document.getElementById("inv_pl3");
  const sales = document.getElementById("inv_sales");
  const yoy = document.getElementById("inv_yoy");
  const pd = document.getElementById("inv_pd");
  if(!pl3.files || !pl3.files[0]){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">3PL stock CSV is required.</div>'; return; }
  if(!sales.files || !sales.files[0]){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">Daily sales CSV is required.</div>'; return; }
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
      resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">'+esc(j.error||"build failed")+'</div>';
      return;
    }
    const s = j.summary || {};
    const c = j.sku_coverage || {};
    let html = '<div style="padding:12px;border:1px solid var(--line);border-radius:8px">';
    html += '<div style="font-weight:600;margin-bottom:8px;color:#7fdca0">✓ Replenishment sheet built</div>';
    html += '<div style="display:flex;gap:14px;flex-wrap:wrap;font-size:12px;margin-bottom:10px">';
    html += '<div><b>'+j.row_count+'</b> SKUs total</div>';
    html += '<div><b style="color:#ffd76b">'+(s.replenish_yes||0)+'</b> flagged for replenishment</div>';
    html += '<div><b style="color:#7fdca0">'+(s.units_flagged||0)+'</b> units to reorder</div>';
    if(s.stockout_risk_skus){
      html += '<div><b style="color:#e0696b">'+s.stockout_risk_skus+'</b> stockout-risk SKUs (DOS &lt; 14)</div>';
    }
    html += '</div>';
    html += '<div style="font-size:11px;opacity:.75;margin-bottom:10px">SKU coverage — FBA (SP-API): '+(c.in_fba||0)+' · 3PL upload: '+(c.in_3pl||0)+' · Sales upload: '+(c.in_sales||0);
    if(c.in_yoy) html += ' · YoY: '+c.in_yoy;
    if(c.in_pd) html += ' · PD: '+c.in_pd;
    html += ' · Union: <b>'+(c.union||0)+'</b></div>';
    if(j.warnings && j.warnings.length){
      html += '<div style="margin-top:8px;padding:8px;border-radius:6px;background:#241a10;border:1px solid #4d3712;color:#e3b768;font-size:11px">';
      html += '<b>SP-API warnings:</b><br>' + j.warnings.map(esc).join("<br>");
      html += '</div>';
    }
    html += '<div style="margin-top:12px"><a href="'+j.download_url+'" download="'+j.filename+'" class="mktbtn on" style="display:inline-block;text-decoration:none;padding:8px 14px">⬇ Download replenishment xlsx</a></div>';
    html += '</div>';
    resBox.innerHTML = html;
  }catch(e){
    resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px">Request failed: '+esc(String(e))+'</div>';
  }
}

// ---------- v2 inventory handler (SP-API auto-fetch, 4-bucket classification) ----------
async function inv2Run(){
  const resBox = document.getElementById("inv2_result");
  const acctId = (CUR_ACCOUNT && CUR_ACCOUNT.id) || "";
  if(!acctId){
    resBox.innerHTML = '<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">No workspace/account selected. Pick one from the sidebar first.</div>';
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
      resBox.innerHTML = '<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">'+esc(j.error||"run failed")+'</div>';
      return;
    }
    const s = j.summary || {};
    let html = '<div style="padding:12px;border:1px solid var(--line);border-radius:8px">';
    html += '<div style="font-weight:600;margin-bottom:8px;color:#7fdca0">✓ Inventory model complete</div>';

    // Bucket counts
    html += '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px;font-size:12px">';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#1c3a1c;color:#8adca0;border:1px solid #2a7a2a">ACTIVE '+(s.active||0)+'</div>';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#3a3a1c;color:#ffe066;border:1px solid #7a7a2a">NEW_LAUNCH '+(s.new_launch||0)+'</div>';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#3a2f1a;color:#ffce7a;border:1px solid #7a5a2a">DORMANT '+(s.dormant||0)+'</div>';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#3a1f1f;color:#ff8a8a;border:1px solid #7a2a2a">DEAD '+(s.dead||0)+'</div>';
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
      html += '<div style="margin-top:8px;padding:8px;border-radius:6px;background:#241a10;border:1px solid #4d3712;color:#e3b768;font-size:11px">';
      html += '<b>Sample alerts (first 10):</b>';
      html += '<ul style="margin:6px 0 0 18px">';
      j.alerts_sample.forEach(a=>{
        html += '<li>'+esc(a.sku)+' — '+esc(a.alert)+'</li>';
      });
      html += '</ul></div>';
    }
    if(j.three_pl_warnings && j.three_pl_warnings.length){
      html += '<div style="margin-top:8px;padding:8px;border-radius:6px;background:#241a10;border:1px solid #4d3712;color:#e3b768;font-size:11px">';
      html += '<b>3PL CSV warnings:</b><br>'+j.three_pl_warnings.map(esc).join("<br>");
      html += '</div>';
    }
    html += '<div style="margin-top:12px"><a href="'+j.download_url+'" download="'+j.filename+'" class="mktbtn on" style="display:inline-block;text-decoration:none;padding:8px 14px">⬇ Download inventory xlsx</a></div>';
    html += '</div>';
    resBox.innerHTML = html;

    // Refresh the sidebar alert badge
    invBadgeRefresh();
  }catch(e){
    resBox.innerHTML = '<div style="color:#e0696b;font-size:12px;padding:8px">Request failed: '+esc(String(e))+'</div>';
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

function runMode(mode, skus){
  if(ES){toast("A run is already streaming");return;}
  const log=document.getElementById("log");
  log.style.display="block"; log.textContent="";
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
    const div=document.createElement("div"); div.className=cls; div.textContent=e.data;
    log.appendChild(div); log.scrollTop=log.scrollHeight;
  };
  ES.addEventListener("end",()=>{ES.close();ES=null;showStop(false);loadRows();toast("Run finished");});
  ES.onerror=()=>{if(ES){ES.close();ES=null;showStop(false);loadRows();}};
}
