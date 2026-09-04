// static/js/runqueue.js — Preview/Submit as BACKGROUND JOBS (queue + visibility).
//
// Checkpoint 2 of Option B. Instead of a live browser connection (which died when you
// left the detail page), Preview/Submit is enqueued as a server-side job. The drawer
// POLLS that job and replays its log -- so progress survives navigating away AND a full
// page refresh. A small global "Runs" badge shows what's running/queued from any screen.
//
// Reuses _runPanel() and _logLineEl() from submit.js (loaded before this file). The
// verdict parsing/rendering mirrors submit.js's finish() -- kept here so the job poller
// is self-contained and the live SSE wrapper in submit.js stays untouched.

// _lastActiveAt: when a job was last running or queued. The badge uses it to
// linger for a couple of minutes after the last one ends -- see rqRenderBadge.
const RQ = { timer:null, watchSku:null, watchJob:null, watchSt:null, globalTimer:null,
             _jobs:[], _panelOpen:false, _lastActiveAt:0 };

function _rqNewState(){ return {lines:[], verdict:null, summary:null, warnings:"", notSubmitted:[], sawStart:false, seen:0, titleShown:false}; }

// PARSE ONE log line into state `st` (no rendering -- rendering happens in rqWatch,
// against the CURRENT panel element, so a drawer re-render can never orphan the log).
function _rqParseLine(st, d, sku){
  d = (d==null) ? "" : String(d);
  st.lines.push(d);
  if(d.indexOf("[busy]")>=0){ st.verdict={kind:"busy", raw:d}; }
  if(d.startsWith("[start]")){ st.sawStart=true; }
  const sm=d.match(/complete\s*--\s*ok:\s*(\d+)\s+errors?:\s*(\d+)\s+skipped:\s*(\d+)/i);
  if(sm){ st.summary={ok:parseInt(sm[1]), errors:parseInt(sm[2]), skipped:parseInt(sm[3])}; }
  const _isProse=/none of the requested|only publishes|fix any flagged errors|then click approve|not processed|were NOT (?:submitted|processed)|not found in this tab|^\s*accounting:/i.test(d);
  if(_isProse){ st.notSubmitted.push(d.trim()); }
  if(!_isProse && d.indexOf(sku)>=0){
    const low=d.toLowerCase();
    let m=d.match(/(\d+)\s+(?:error|issue)\(s\)/i);
    if(m){ st.verdict={kind:"error", n:parseInt(m[1]), raw:d}; }
    else if(low.indexOf("not live")>=0 || low.indexOf("api call failed")>=0 || low.indexOf("api_error")>=0){ st.verdict={kind:"error", n:0, raw:d}; }
    else if(low.indexOf("missing")>=0 && low.indexOf("skip")>=0){ st.verdict={kind:"missing", raw:d}; }
    else if(low.indexOf("api_ready")>=0 || low.indexOf("preview clean")>=0){ st.verdict={kind:"ok_preview", raw:d}; }
    // ACCEPTED IS NOT PUBLISHED, AND THE ORDER OF THESE TWO IS THE WHOLE POINT.
    //
    // The generator's success line is "SUBMITTED -- accepted by Amazon (live
    // shortly)". It contains the word "live", so a single test for "live" matched
    // it and the drawer printed "Published live to Amazon" over a row whose status
    // said SUBMITTED -- the app contradicting itself on one screen. "submitted" is
    // therefore tested FIRST, and only the verify run's "now LIVE (BUYABLE)" line
    // reaches ok_live.
    else if(low.indexOf("submitted")>=0){ st.verdict={kind:"ok_submit_pending", raw:d}; }
    else if(low.indexOf("live")>=0){ st.verdict={kind:"ok_live", raw:d}; }
    const wm=d.match(/warnings?:\s*(.+)$/i); if(wm) st.warnings=wm[1];
  }
  if(d.toLowerCase().indexOf("no seller_id")>=0) st.verdict={kind:"nocreds", raw:d};
  { const dl=d.toLowerCase();
    if(/getaddrinfo failed|failed to resolve|nameresolutionerror|max retries exceeded|connectionerror|transporterror|errno 11002|temporary failure in name resolution|connection timed out|handshake operation timed out/.test(dl)){
      st.verdict={kind:"network", raw:d};
    } }
}

// Render the FINAL verdict. mode = "preview"|"submit".
function _rqFinish(st, P, sku, mode){
  if(!P) return;
  const verdict=st.verdict, summary=st.summary, warnings=st.warnings, lines=st.lines;
  if(!st.sawStart){
    if(verdict && verdict.kind==="busy"){ P.verdict.innerHTML='<span class="rwarn">A previous Preview/Submit is still finishing. It will start automatically when that one ends.</span>'; return; }
    P.verdict.innerHTML='<span class="rbad">✗ The run didn’t start. Check that the generator script is reachable.</span>'; return;
  }
  if(mode === "submit" && summary && summary.ok === 0 && (!verdict || verdict.kind !== "error")){
    const _why = esc((st.notSubmitted.join(" ") || "The run finished without publishing this listing.").replace(/\s+/g, " ").trim());
    const _gated = /api_error|status\s*'|only publishes/i.test(_why);
    P.verdict.innerHTML='<div class="rbad">✗ Nothing was submitted — this listing was NOT sent to Amazon.</div>'
      + '<div class="rmsg"><b>The app’s own words:</b></div><div class="ramz">'+_why+'</div>'
      + (_gated
          ? '<div class="rhint"><b>Why:</b> Submit only publishes rows whose status is <b>API_READY</b> or <b>APPROVED</b>. This row is still marked <b>API_ERROR</b> from an earlier failed check.<br><b>Do this:</b> Preview to re-check → Approve → Submit.</div>'
          : '<div class="rhint">Fix what’s flagged above, then Preview → Approve → Submit.</div>');
    return;
  }
  if(verdict && verdict.kind==="network"){
    P.verdict.innerHTML='<div class="rbad">✗ Network problem — couldn’t reach Google/Amazon to run this.</div>'
      +'<div class="rmsg">Your computer failed a DNS lookup, so the app never got to validate the listing. This is a connection issue, not a problem with the listing.</div>'
      +'<div class="rhint"><b>Try this:</b> Preview again; turn off any VPN/proxy; run <code>ipconfig /flushdns</code>; or switch DNS to <code>1.1.1.1</code>.</div>';
    return;
  }
  if(!verdict){ P.verdict.innerHTML='<span class="rwarn">Finished, but no result line was found for this SKU. Open the log below to read exactly what happened.</span>'; return; }
  if(verdict.kind==="nocreds"){ P.verdict.innerHTML='<span class="rbad">✗ No SP-API credentials for this account/marketplace.</span> Add them in the account editor before publishing.'; return; }
  if(verdict.kind==="missing"){
    P.verdict.innerHTML='<div class="rbad">✗ This row is missing a SKU or Product Type.</div>'
      +'<div class="ramz">'+esc(verdict.raw.trim())+'</div>'
      +'<div class="rhint">Fill both <b>SKU</b> and <b>Product Type</b>, then Preview again.</div>';
    return;
  }
  if(verdict.kind==="error"){
    if(/timed out|timeout|read operation|TIMED OUT/i.test(String(verdict.raw||""))){
      P.verdict.innerHTML='<div class="rbad">✗ The validation call to Amazon timed out.</div>'
        +'<div class="rmsg">This is <b>not</b> a problem with your listing — the call to Amazon’s UK/EU endpoint was too slow. The app already retried automatically.</div>'
        +'<div class="rhint">Preview again; turn off any VPN/proxy; or switch DNS to <code>1.1.1.1</code>.</div>';
      return;
    }
    let _eLines=lines.filter(x=>/\[E\]/.test(x))
                     .map(x=>x.replace(/^[^[]*\[E\]\s*/,"").replace(/\s+/g," ").trim())
                     .filter(Boolean);
    // FALLBACK: if no [E]-prefixed line survived (e.g. the generator's re-verify phrasing
    // or a line-wrapped message), pull the error-bearing lines so the reason is NEVER just
    // a bare "errors: 1" count. The full text is also in the row's Notes + the log below.
    if(!_eLines.length){
      _eLines=lines.filter(x=>/rejected|conflict|catalogue|catalog|does not match|not live|is invalid|not a valid|required but missing|cannot be added/i.test(x))
                   .map(x=>x.replace(/^\s*[-•]\s*/,"").replace(/^\s*row\s+\d+\s+\S+:\s*/i,"").replace(/\s+/g," ").trim())
                   .filter(Boolean);
    }
    const _eText=_eLines.join("  •  ");
    const _allText=lines.join(" ");
    const _row=(typeof ROWS!=="undefined"&&ROWS.find)?ROWS.find(x=>String(x.sku)===String(sku)):null;
    const _ctx={barcode:(_row&&_row.barcode)||"", sku:sku, productType:(_row&&_row.product_type)||""};
    if(typeof renderAmazonErrors==="function"){
      const _t=renderAmazonErrors(_eLines.length?_eLines:[_allText], _eText||_allText||verdict.raw, _ctx);
      if(_t.matched){
        P.verdict.innerHTML='<div class="rbad">✗ Amazon did NOT accept this listing — '+(verdict.n||_eLines.length||"")+' issue(s).</div>'+_t.html;
        return;
      }
    }
    const msg=esc(_eText||verdict.raw.replace(/^.*error\(s\)\)?/i,"").trim()||verdict.raw);
    P.verdict.innerHTML='<div class="rbad">✗ Amazon did NOT accept this listing — '+(verdict.n||"")+' issue(s).</div>'
      +'<div class="rmsg"><b>Amazon’s response, word for word:</b></div><div class="ramz">'+msg+'</div>'
      +'<div class="rhint">Click <b>Suggest missing fields</b> above to fill what Amazon flagged, then Preview again.</div>';
    return;
  }
  if(verdict.kind==="ok_preview"){
    P.verdict.innerHTML='<div class="rgood">✓ Amazon accepted this listing — no missing or invalid fields.</div>'
      +(warnings?('<div class="rwarn">Non-blocking warnings: '+esc(warnings)+'</div>'):'<div class="rmsg">No extra boxes need filling. It’s ready to submit.</div>');
    return;
  }
  // The wording comes from liststatus.js, beside the status vocabulary it
  // describes, so the sentence can never again say "live" about a row the rest of
  // the app files as SUBMITTED. "ok_submit" is still accepted as the old name.
  if(verdict.kind==="ok_live"){ P.verdict.innerHTML=lsVerdictHtml("ok_live", warnings); return; }
  if(verdict.kind==="ok_submit_pending" || verdict.kind==="ok_submit"){
    P.verdict.innerHTML=lsVerdictHtml("ok_submit_pending", warnings);
    return;
  }
}

// Refresh THIS row's stored data after a run so the drawer shows fresh notes/status.
function _rqRefreshRow(sku){
  setTimeout(async ()=>{
    try{
      const j = await (await fetch(acctUrl("/row?sku="+encodeURIComponent(sku)))).json();
      if(j && j.ok && j.row){
        const idx = ROWS.findIndex(x=>String(x.sku)===String(sku));
        if(idx>=0){ ROWS[idx] = {...ROWS[idx], ...j.row}; }
        if(String(DRAWER_SKU)===String(sku)){
          const host=document.getElementById("fulldata_"+sid(sku));
          const fresh=ROWS.find(x=>String(x.sku)===String(sku));
          if(host && fresh){ host.innerHTML=fullData(fresh); setTimeout(()=>{ if(typeof bulletMeter==='function') bulletMeter(); }, 40); }
        }
      }
    }catch(e){}
  }, 800);
}

// ---- enqueue + watch --------------------------------------------------------
// mode: "api" (Preview) | "api_submit" (Submit)
function rqEnqueue(sku, mode, minimal){
  if(!sku) return;
  const P=_runPanel(sku);
  if(P){ P.show((mode==="api_submit"?"Submitting ":"Previewing ")+sku+" …"); P.verdict.innerHTML='<span class="rspin"></span> Queuing…'; }
  // NO DRAWER OPEN -> SHOW THE RUNS PANEL, so there is something to watch.
  // Otherwise the only sign a submit is happening is one toast that fades, and
  // the badge that appears is easy to miss and disappears again the moment the
  // queue empties. This is the same panel the badge opens; it is simply opened
  // for you, because you have just asked for the thing it reports on.
  else if(typeof rqTogglePanel === "function" && !RQ._panelOpen){
    try{ rqTogglePanel(); }catch(e){}
  }
  window.RUN_STREAMING=true;
  fetch("/preview/enqueue",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({sku:sku, mode:mode, minimal:!!minimal})})
    .then(r=>r.json()).then(r=>{
      if(!r||!r.ok){ if(P) P.verdict.innerHTML='<span class="rbad">✗ Couldn’t queue: '+esc((r&&r.error)||"unknown")+'</span>'; return; }
      rqGlobalPollNow();
      rqWatch(sku, r.job);
    }).catch(e=>{ if(P) P.verdict.innerHTML='<span class="rbad">✗ Couldn’t queue: '+esc(String(e))+'</span>'; });
}

// Watch a sku's job in the OPEN drawer: render its current log, poll until terminal.
// Called on enqueue AND on openDrawer (to re-attach after navigation / refresh).
// PARSE (into st) and RENDER (into the CURRENT panel) are separated: the panel element
// is re-resolved every tick and the log re-rendered in full if the drawer was rebuilt --
// so a schema-reload re-render can never leave the log appended to a detached (invisible)
// panel. The full server-side job.log is always the source of truth.
function rqWatch(sku, jobId){
  rqStopWatch();
  /* IT NO LONGER NEEDS A DRAWER TO WATCH.
   *
   *     "when i submit the approved row from drafts i see no progress or log
   *      what happened to that listing"
   *
   * This returned here when there was no runpanel_<sku> element -- and that
   * element lives INSIDE THE OPEN DRAWER. So submitting from a row, with the
   * drawer shut, stopped the watcher before it began, and everything after this
   * line was skipped:
   *
   *   - no progress and no log, which is what was reported;
   *   - no terminal verdict, so nothing ever said whether Amazon took it;
   *   - _rqRefreshRow never ran, so the row itself did not update either;
   *   - and avSubmitted() never started, so the auto-verify clock that re-asks
   *     Amazon at 5, 10 and 15 minutes never began. A listing submitted from
   *     the list was simply not being followed.
   *
   * The panel is one place to RENDER, not a precondition for watching. Every
   * render below is already guarded by `if(P)`; the loop now runs either way,
   * and the terminal branch reports through a toast when there is no panel to
   * write into.
   */
  const st=_rqNewState();
  RQ.watchSku=sku; RQ.watchJob=jobId||null; RQ.watchSt=st; RQ.watchEl=null; RQ.rendered=0;
  const tick=async ()=>{
    if(RQ.watchSku!==sku) return;   // stopped watching / switched drawer
    let j=null;
    try{
      const url="/preview/job?sku="+encodeURIComponent(sku)+(RQ.watchJob?("&job="+encodeURIComponent(RQ.watchJob)):"");
      j=(await (await fetch(url)).json()).job;
    }catch(e){ RQ.timer=setTimeout(tick,1500); return; }
    if(RQ.watchSku!==sku) return;
    if(!j){ RQ.timer=setTimeout(tick,1300); return; }
    RQ.watchJob=j.id;
    const mode = j.mode==="api_submit" ? "submit" : "preview";
    // PARSE any new log lines into st (pure -- no DOM writes)
    const log=j.log||[];
    for(let i=st.seen;i<log.length;i++){ _rqParseLine(st, log[i], sku); }
    st.seen=log.length;
    if(st.lines.length>0) st.sawStart=true;   // any output -> the run demonstrably STARTED
    // RENDER into the CURRENT panel element (re-render the whole log if it was rebuilt)
    const P=_runPanel(sku);
    if(P){
      const el=document.getElementById("runpanel_"+sid(sku));
      if(RQ.watchEl!==el){ RQ.watchEl=el; RQ.rendered=0; P.show((mode==="submit"?"Submitting ":"Previewing ")+sku+" …"); }
      for(let i=RQ.rendered;i<st.lines.length;i++){ P.log.appendChild(_logLineEl(st.lines[i])); }
      if(st.lines.length>RQ.rendered){ P.log.scrollTop=P.log.scrollHeight; RQ.rendered=st.lines.length; }
      if(j.status==="queued"){ P.verdict.innerHTML='<span class="rspin"></span> Queued — starts when the current run finishes.'; }
      else if(j.status==="running"){ P.verdict.innerHTML='<span class="rspin"></span> Running… <span class="cc">'+esc(String(st.lines.length))+' log line(s)</span>'; }
    }
    if(j.status==="queued" || j.status==="running"){ RQ.timer=setTimeout(tick,1200); return; }
    // terminal
    if(P){
      if(j.status==="cancelled" && !st.sawStart){ P.verdict.innerHTML='<span class="rwarn">Cancelled before it ran.</span>'; }
      else { _rqFinish(st, P, sku, mode); }
    }else{
      // NO PANEL TO WRITE INTO, so it is said out loud instead. Without this a
      // submit from the list ended in silence -- the badge vanishes the moment
      // the queue empties, and nothing else on the screen changes fast enough
      // to notice.
      _rqSayOutcome(st, sku, mode, j.status);
    }
    // AMAZON ACCEPTED IT -- START THE CLOCK.
    //
    // Amazon publishes 5-30 minutes after accepting, and until now the ONLY thing
    // that noticed was the user pressing Sync at the right moment. autoverify.js
    // re-asks Amazon at 5 and 10 minutes and warns at 15, driving the generator's
    // existing verify mode. Started from the JOB's terminal state (not the panel)
    // so it runs whether or not the drawer is still open.
    if(mode==="submit" && st.verdict
       && (st.verdict.kind==="ok_submit_pending" || st.verdict.kind==="ok_submit")
       && typeof avSubmitted==="function"){
      try{ avSubmitted(sku); }catch(e){}
    }
    window.RUN_STREAMING=false;   // the watched run is done -> let the views refresh again
    _rqRefreshRow(sku);
    rqGlobalPollNow();
    RQ.watchSku=null; RQ.timer=null;
  };
  tick();
}

/* WHAT HAPPENED, IN ONE SENTENCE, WHEN THERE IS NOWHERE TO PUT THE LOG.
 *
 * _rqFinish writes a paragraph and a hint into the drawer's verdict box. This
 * is the same information for the case where the drawer is not open: the ONE
 * thing worth interrupting somebody for, with a way to the detail.
 *
 * IT READS THE SAME PARSED STATE _rqFinish DOES -- st.verdict, st.summary,
 * st.notSubmitted -- rather than looking at the log again, so the two cannot
 * come to different conclusions about the same run (CLAUDE.md Rule 12).
 *
 * "Amazon accepted it" is deliberately NOT "it is live": Amazon publishes 5-30
 * minutes later, autoverify.js is already following it, and saying live here
 * would be a claim nobody has checked.
 */
function _rqSayOutcome(st, sku, mode, status){
  if(typeof toast !== "function") return;
  const what = (mode === "submit" ? "Submit" : "Preview") + " · " + sku;
  if(status === "cancelled" && !st.sawStart){ toast(what + " — cancelled before it ran."); return; }
  if(!st.sawStart){ toast(what + " — the run did not start."); return; }
  const v = st.verdict, s = st.summary;
  if(mode === "submit" && s && s.ok === 0 && (!v || v.kind !== "error")){
    toast(what + " — NOT sent to Amazon. "
      + (st.notSubmitted.join(" ").replace(/\s+/g, " ").trim().slice(0, 140)
         || "Open the listing to see why."));
    return;
  }
  if(!v){ toast(what + " — finished. Open the listing to read the log."); return; }
  if(v.kind === "nocreds"){ toast(what + " — no SP-API credentials for this account."); return; }
  if(v.kind === "network"){ toast(what + " — could not reach Amazon. A connection problem, not the listing."); return; }
  if(v.kind === "missing"){ toast(what + " — the row is missing a SKU or a Product Type."); return; }
  if(v.kind === "error"){
    const first = (st.lines || []).filter(x => /\[E\]/.test(x))
      .map(x => x.replace(/^[^[]*\[E\]\s*/, "").replace(/\s+/g, " ").trim())[0];
    toast(what + " — Amazon refused. " + (first ? first.slice(0, 140)
      : "Open the listing to see what it said."));
    return;
  }
  if(v.kind === "ok_submit_pending" || v.kind === "ok_submit"){
    toast(what + " — Amazon accepted it. It usually appears in 5-30 minutes; "
      + "the app is checking.");
    return;
  }
  toast(what + " — finished. Open the listing for the detail.");
}

// Stop WATCHING (on closeDrawer). Does NOT stop the server job -- it keeps running.
function rqStopWatch(){ if(RQ.timer){ clearTimeout(RQ.timer); RQ.timer=null; } RQ.watchSku=null; RQ.watchSt=null; RQ.watchJob=null; RQ.watchEl=null; RQ.rendered=0; }

// Called from openDrawer(sku): if a job exists for this sku, re-attach and show it.
function rqAttach(sku){ rqWatch(sku, null); }

// ---- global "Runs" badge + panel -------------------------------------------
function rqBadgeEl(){
  let el=document.getElementById("rqbadge");
  if(!el){ el=document.createElement("div"); el.id="rqbadge"; el.className="rqbadge"; el.title="Preview/Submit runs"; el.onclick=rqTogglePanel; document.body.appendChild(el); }
  return el;
}
/* THE BADGE OUTLIVES THE RUN, for a couple of minutes.
 *
 * It used to vanish the instant the queue emptied -- so a submit that finished
 * while you were reading something else left NOTHING on the screen, and no way
 * back to the log. "I see no progress or log what happened to that listing" is
 * partly that: the answer existed, on a badge that had already gone.
 *
 * It now stays for two minutes after the last job ends, saying how it went, and
 * clicking it opens the same panel with the last fifteen runs in it. Two
 * minutes because this is a notice, not a status bar: the Runs list is still
 * reachable afterwards from a job's own listing, and a badge that never leaves
 * is one nobody reads.
 */
const RQ_BADGE_LINGER_MS = 120000;

function rqRenderBadge(counts){
  const el=rqBadgeEl();
  const run=(counts&&counts.running)||0, q=(counts&&counts.queued)||0;
  if(run+q>0){
    RQ._lastActiveAt = Date.now();
    el.style.display="inline-flex";
    el.className="rqbadge";
    el.innerHTML='<span class="rqdot"></span>&nbsp;'+run+' running'+(q?(' · '+q+' queued'):'');
    return;
  }
  // Nothing active. Linger only if something ran recently AND we know how it
  // went -- a badge saying "0 running" would be worse than none.
  const since = RQ._lastActiveAt ? (Date.now() - RQ._lastActiveAt) : Infinity;
  const recent = (RQ._jobs||[]).filter(j => j.status==="done" || j.status==="error"
                                         || j.status==="cancelled");
  if(since < RQ_BADGE_LINGER_MS && recent.length){
    const bad = recent.filter(j => j.status==="error").length;
    el.style.display="inline-flex";
    el.className = "rqbadge" + (bad ? " bad" : " ok");
    el.innerHTML = bad
      ? ('<span class="rqdot"></span>&nbsp;' + bad + ' failed — open')
      : ('<span class="rqdot"></span>&nbsp;finished — open');
    if(RQ._panelOpen) rqRenderPanel();
    return;
  }
  el.style.display="none";
  el.className="rqbadge";
  if(RQ._panelOpen) rqRenderPanel();
}
async function rqGlobalPollNow(){
  try{
    const j=await (await fetch("/preview/jobs")).json();
    if(j&&j.ok){
      RQ._jobs=j.jobs||[];
      rqRenderBadge(j.counts);
      if(RQ._panelOpen) rqRenderPanel();
      // ALL-DONE transition (active went from >0 to 0): auto-collapse + unfreeze + refresh.
      const active=((j.counts&&j.counts.running)||0)+((j.counts&&j.counts.queued)||0);
      if(active>0 && RQ._allDoneTimer){ clearTimeout(RQ._allDoneTimer); RQ._allDoneTimer=null; }
      if(RQ._prevActive>0 && active===0 && !RQ._allDoneTimer){ rqScheduleAllDone(); }
      RQ._prevActive=active;
      // TRUE while anything is running or queued, or while the panel is open
      // and being watched. Otherwise this slows and stops: it used to loop
      // every three seconds for ever, whether or not there was a job.
      return active > 0 || !!RQ._panelOpen;
    }
  }catch(e){}
  return false;
}
// 5s after the last job finishes: collapse the Runs panel to the badge, drop the
// streaming lock, and refresh the listings so no run state is left bleeding on top.
function rqScheduleAllDone(){
  if(RQ._allDoneTimer) clearTimeout(RQ._allDoneTimer);
  RQ._allDoneTimer=setTimeout(function(){
    RQ._allDoneTimer=null;
    RQ._panelOpen=false;
    const p=document.getElementById("rqpanel"); if(p) p.style.display="none";
    window.RUN_STREAMING=false;
    if(typeof loadRows==="function"){ try{ loadRows(); }catch(e){} }
  }, 5000);
}
function rqStartGlobal(){
  if(!RQ.globalTimer){
    RQ.globalTimer = altaPoller({name: "runqueue", every: 3000,
                                 idleEvery: 20000, tick: rqGlobalPollNow});
  }
  RQ.globalTimer.wake();
}
function rqTogglePanel(){
  RQ._panelOpen=!RQ._panelOpen;
  let p=document.getElementById("rqpanel");
  if(!RQ._panelOpen){ if(p) p.style.display="none"; return; }
  if(!p){ p=document.createElement("div"); p.id="rqpanel"; p.className="rqpanel"; document.body.appendChild(p); }
  p.style.display="block"; rqRenderPanel();
}
function rqClosePanel(){ RQ._panelOpen=false; const p=document.getElementById("rqpanel"); if(p) p.style.display="none"; }
function rqRenderPanel(){
  const p=document.getElementById("rqpanel"); if(!p) return;
  const jobs=(RQ._jobs||[]).slice(0,15);
  p.innerHTML='<div class="rqpanel-h"><span>Preview / Submit runs</span>'
    + '<span class="rqpanel-btns">'
    +   '<button class="rqmin" title="Collapse to the Runs badge" onclick="rqClosePanel()">–</button>'
    +   '<button class="rqx" title="Close (jobs keep running; click the Runs badge to reopen)" onclick="rqClosePanel()">✕</button>'
    + '</span></div>'
    + (jobs.length? jobs.map(j=>{
        const st=j.status, cls=(st==="running")?"run":(st==="queued")?"q":(st==="done")?"ok":(st==="cancelled")?"c":"err";
        const active=(st==="queued"||st==="running");
        return '<div class="rqrow" onclick="rqOpenJob(\''+esc(String(j.sku))+'\')">'
          +'<span class="rqst '+cls+'">'+esc(st)+'</span>'
          +'<span class="rqsku">'+esc(String(j.label||j.sku))+'</span>'
          +'<span class="rqmode">'+esc(j.mode==="api_submit"?"submit":"preview")+'</span>'
          +(active?'<button class="rqstop" title="Cancel" onclick="event.stopPropagation();rqStopJob(\''+esc(String(j.id))+'\')">✕</button>':'')
          +'</div>';
      }).join("") : '<div class="rqempty">No recent runs.</div>');
}
/* Clicking a run in the queue opens the listing it is for.
 *
 * Through openListing, which is the one function that decides WHERE a listing
 * opens -- the product page when this app holds a draft, the live optimiser
 * when it does not. It called openDrawer directly, which was one of the six
 * ways the side drawer could appear:
 *
 *     "These are completely different UIs showing the same data ... the user
 *      doesn't know which one will appear when."
 */
function rqOpenJob(sku){
  if(typeof openListing === "function"){ try{ openListing(sku); }catch(e){} }
  else if(typeof openDrawer === "function"){ try{ openDrawer(sku); }catch(e){} }
}
function rqStopJob(jobId){ fetch("/preview/stop",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({job:jobId})}).then(()=>rqGlobalPollNow()).catch(()=>{}); }

if(document.readyState!=="loading"){ rqStartGlobal(); }
else { document.addEventListener("DOMContentLoaded", rqStartGlobal); }
