// ---------- Inventory section ----------
//
// invRunBuild() USED TO LIVE HERE and has been removed. It was the first
// version of this screen: it asked for four CSV uploads and read the element
// ids inv_pl3, inv_sales, inv_yoy, inv_pd, inv_normal, inv_reorder, inv_long,
// inv_cycle and inv_result.
//
// None of those ids exist. The template carries the v2 set -- inv2_normal,
// inv2_reorder, inv2_long, inv2_window, inv2_result -- and the only button on
// the screen calls inv2Run(). So invRunBuild was reachable from nowhere, and
// had it ever been reached it would have thrown on the first null.
//
// Found by a sweep for element ids the JS asks for and no template provides.
// Deleting it rather than leaving it means the next such sweep is quiet, and a
// quiet sweep is one whose noise means something.
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
    const h=await r.json();
    _rhRender(h);
    // TRUE only while a run is actually going. An idle generator does not get
    // more interesting for being asked about every three seconds, and this was
    // asking for ever -- 19 of the 84 requests during one Listings load.
    const st=String((h&&h.state)||"").toLowerCase();
    return !!(h && h.running) || st==="running" || st==="busy" || st==="starting";
  }catch(e){
    /* dashboard unreachable; leave the last known state on screen */
    return false;
  }
}

function startRunHealth(){
  if(_rhTimer) return;
  _rhTimer = altaPoller({name: "run-health", every: 3000, idleEvery: 20000,
                         tick: _rhPoll});
  _rhTimer.wake();
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
  // Reset on a fresh click, so the one automatic retry is per press and a
  // genuinely stuck account cannot loop.
  if(!runMode._inRetry) runMode._retried=false;
  runMode._inRetry=false;
  _logReset();
  log.style.display="block"; log.textContent="";
  startRunHealth();
  let url="/run/"+mode;
  // WHICH ACCOUNT, SENT FROM THE SCREEN YOU ARE LOOKING AT.
  //
  // This used to send nothing, and the server chose the account from a single
  // process-wide variable. That variable is not per browser and not per tab: it
  // is whatever was selected LAST by anything at all, and it is restored from
  // disk after a restart. So pressing Generate while looking at Jack Reacherd
  // ran the generator against Nestwell Goods -- Nestwell's credentials,
  // Nestwell's sheet -- with the screen still saying Jack Reacherd throughout.
  // The account is now named by the page that has the human on it, and the
  // server refuses if the two disagree rather than quietly preferring its own.
  const _runParams=new URLSearchParams();
  if(typeof CUR_ACCOUNT!=="undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id){
    _runParams.set("account_id", CUR_ACCOUNT.id);
  }
  if(typeof WS_MARKET!=="undefined" && WS_MARKET){
    _runParams.set("marketplace", WS_MARKET);
  }
  // Generate-only: pass the row selection (value + type). Empty -> generate all.
  if(mode==="generate"){
    const valEl=document.getElementById("gensel_value");
    const typeEl=document.getElementById("gensel_type");
    const val=(valEl&&valEl.value||"").trim();
    if(val){
      _runParams.set("select", val);
      // when a URL is pasted the dropdown is disabled; send 'auto' so the server auto-detects
      _runParams.set("select_type", (typeEl&&!typeEl.disabled)? typeEl.value : "auto");
    }
  }
  // Preview/Submit: if specific SKUs are passed (the user's SELECTION), scope the
  // run to exactly those. Empty -> the server's default (all approved/ready rows).
  if((mode==="api"||mode==="api_submit") && skus && skus.length){
    _runParams.set("skus", skus.join(","));
  }
  const _qs=_runParams.toString();
  if(_qs) url += "?"+_qs;
  ES=new EventSource(url);
  showStop(true);
  ES.onmessage=e=>{
    // The server refused because its idea of the open account had drifted from
    // this page's. Put it right using the SAME select call the account picker
    // uses -- which also resets the sheet, tab and marketplace that go with the
    // account -- then run once more. Setting the account id alone would leave
    // the previous account's sheet ids in place, which is the other half of the
    // same bug: a run for one account writing into another's sheet.
    if(e.data.indexOf("[error] ACCOUNT_MISMATCH")===0 && !runMode._retried){
      runMode._retried=true;
      if(ES){ES.close();ES=null;}
      showStop(false);
      _logPush(log,"l","[fix] Re-selecting this account and retrying…");
      fetch("/accounts/select",{method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({id:(CUR_ACCOUNT&&CUR_ACCOUNT.id)||"",
                             marketplace:(typeof WS_MARKET!=="undefined"?WS_MARKET:"")})})
        .then(()=>{ runMode._inRetry=true; runMode(mode,skus); })
        .catch(()=>{ toast("Could not reselect the account — reload the page."); });
      return;
    }
    const cls = e.data.startsWith("[start]")?"start":e.data.startsWith("[done]")?"done":"l";
    _logPush(log, cls, e.data);
  };
  ES.addEventListener("end",()=>{_logFlush(log);ES.close();ES=null;showStop(false);loadRows();toast("Run finished");});
  // A STREAM THAT NEVER OPENED MUST SAY SO.
  //
  // This closed everything down and told nobody. EventSource fires onerror both
  // when a live stream drops AND when the connection never opened at all -- and
  // it deliberately gives no status code, so a 500 from the server looked
  // exactly like a finished run: the log stayed empty, the Stop button went
  // away, and the screen offered no reason.
  //
  // Which is what a NameError in /run/generate looked like for as long as it
  // was there: press Generate, watch nothing happen, with no way to tell
  // whether it had run and found nothing or had never started. If the stream
  // closes without having delivered a single line, that is not a run, and the
  // log says so rather than staying blank.
  ES.onerror=()=>{
    if(!ES) return;
    const emptyRun = !log.textContent.trim();
    _logFlush(log); ES.close(); ES=null; showStop(false); loadRows();
    if(emptyRun){
      _logPush(log, "l", "[error] The run did not start — the server closed the "
             + "connection before sending anything. This is usually a fault on "
             + "the server rather than something you did; check /diag, and the "
             + "app log for the failing request.");
      _logFlush(log);
      toast("The run did not start");
    }
  };
}