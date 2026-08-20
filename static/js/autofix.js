// ---- AI sourced suggestions for missing fields ----
function _srcBadge(src){
  var map={
    'eBay':['var(--ok-bg)','var(--ok)','eBay source'],
    'Amazon competitor (SP-API)':['var(--accent-bg)','var(--accent2)','Amazon competitor'],
    'AI knowledge':['var(--ai-bg2)','var(--ai)','AI knowledge'],
    'AI inference':['var(--warn-bg)','var(--warn)','AI inference'],
    'none':['var(--red-bg)','var(--red)','no source']
  };
  var m=map[src]||map['AI inference'];
  return '<span class="srcbadge" style="background:'+m[0]+';color:'+m[1]+'">'+m[2]+'</span>';
}
function _confBadge(c){
  if(!c) return '';
  var col=c==='high'?'var(--ok)':(c==='medium'?'var(--warn)':'var(--ink2)');
  return '<span class="confbadge" style="color:'+col+'">'+esc(c)+'</span>';
}
async function suggestFields(sku){
  var box=document.getElementById('suggestbox_'+sid(sku));
  if(!box) return;
  box.innerHTML='<div class="gendiag"><span class="genspin"></span> Checking eBay \u2192 Amazon competitor \u2192 search \u2192 AI for the missing fields\u2026</div>';
  try{
    var res=await fetch('/suggest',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:sku})});
    var j=await res.json();
    if(!j.ok){ box.innerHTML='<div class="gendiag bad">\u2717 '+esc(j.error||'failed')+'</div>'; return; }
    if(!j.suggestions || !j.suggestions.length){
      // The /suggest endpoint only knows fields Amazon flagged in a PRIOR Preview
      // (read from Notes). But the schema also has its own required list, and a
      // required field can be EMPTY while unflagged -- that's the field with a
      // star. Cross-check the schema so the message doesn't contradict the stars.
      var _emptyReq = [];
      try{
        var r=(ROWS||[]).find(function(x){return String(x.sku)===String(sku);});
        var pt=(r&&r.product_type)||"";
        var sc=SCHEMAS[pt]||{}; var reqL=sc.req||[];
        var a=(r&&r.attributes)||{};
        reqL.forEach(function(k){
          // consider the field "filled" if it has a value directly OR any of its
          // dotted sub-keys has a value (nested fields like dangerous goods).
          var direct=(k in a)&&String(a[k]).trim()!=="";
          var nested=Object.keys(a).some(function(kk){return kk.indexOf(k+".")===0 && String(a[kk]).trim()!=="";});
          if(!direct && !nested) _emptyReq.push(k);
        });
      }catch(e){}
      if(_emptyReq.length){
        box.innerHTML='<div class="gendiag" style="color:var(--warn)">\u2605 '+_emptyReq.length+' required field'+(_emptyReq.length>1?'s':'')+' still need a value (marked with \u2605 below): <b>'+_emptyReq.map(function(x){return esc(x.replace(/_/g," "));}).join(", ")+'</b>.<br><span class="cc">Amazon hasn\u2019t flagged these yet \u2014 fill them now, or click Preview API to confirm exactly what\u2019s required.</span></div>';
      } else {
        box.innerHTML='<div class="gendiag ok">\u2713 No missing required fields detected. (If Amazon flagged some, click Preview API first so they\u2019re known.)</div>';
      }
      return;
    }
    var rows=j.suggestions.map(function(s){
      var sidv=sid(sku)+'__'+sid(s.field);
      if(s._code_owned){
        // Compliance field the app fills automatically on Preview -- show as an
        // info card with NO editable box and NO Apply button, so the user knows
        // it's handled and won't try to fill it by hand.
        return '<div class="sgrow applied" id="sg_'+sidv+'">'+
          '<div class="sghead"><span class="sgfield">'+esc(s.field)+'</span>'+
          '<span class="srcbadge" style="background:#13371f;border-color:#1f7a3a;color:var(--ok)">auto-filled on Preview</span></div>'+
          (s.note?'<div class="sgnote">'+esc(s.note)+'</div>':'')+
        '</div>';
      }
      return '<div class="sgrow" id="sg_'+sidv+'">'+
        '<div class="sghead"><span class="sgfield">'+esc(s.field)+'</span>'+_srcBadge(s.source)+_confBadge(s.confidence)+'</div>'+
        '<textarea class="ed sgval" id="sgval_'+sidv+'">'+esc(s.value||'')+'</textarea>'+
        (s.note?'<div class="sgnote">'+esc(s.note)+'</div>':'')+
        '<div class="sgacts"><button class="sgapply" onclick="applySuggestion(\''+esc(sku)+'\',\''+esc(s.field)+'\',\''+sidv+'\')">Apply this</button></div>'+
      '</div>';
    }).join('');
    box.innerHTML='<div class="sgtop"><b>Suggested values</b> <span class="cc">each tagged with where it came from</span>'+
      '<button class="sgall" onclick="applyAllSuggestions(\''+esc(sku)+'\')">Apply all</button></div>'+rows;
  }catch(e){ box.innerHTML='<div class="gendiag bad">\u2717 '+esc(String(e))+'</div>'; }
}
async function applySuggestion(sku, field, sidv){
  var ta=document.getElementById('sgval_'+sidv);
  var val=ta?ta.value:'';
  var btn=document.querySelector('#sg_'+sidv+' .sgapply');
  if(btn){ btn.disabled=true; btn.textContent='Applying…'; }
  try{
    await fetch('/edit',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:sku,target:'attr',key:field,value:val})});
    var rowEl=document.getElementById('sg_'+sidv);
    if(rowEl){ rowEl.classList.add('applied'); }
    if(btn){ btn.textContent='\u2713 Applied'; }
    // reflect immediately in the open drawer so scrolling down shows the value
    // (single-apply previously only saved server-side and never refreshed UI).
    try{
      // 1) update the in-memory row so the value persists in the UI model
      var r=(ROWS||[]).find(function(x){return String(x.sku)===String(sku);});
      if(r){ r.attributes=r.attributes||{}; r.attributes[field]=val; }
      // 2) re-render the open drawer's full-data section so the filled value is
      //    visible when you scroll down (single-apply used to never refresh it).
      if(DRAWER_SKU && String(DRAWER_SKU)===String(sku) && typeof fullData==='function'){
        var fr=(ROWS||[]).find(function(x){return String(x.sku)===String(DRAWER_SKU);});
        var host=document.getElementById('fulldata_'+sid(DRAWER_SKU));
        if(host && fr){ host.innerHTML=fullData(fr); }
      }
    }catch(e){}
  }catch(e){ if(btn){ btn.disabled=false; btn.textContent='Apply this'; } toast('Could not apply: '+e); }
}
async function applyAllSuggestions(sku){
  var box=document.getElementById('suggestbox_'+sid(sku));
  if(!box) return;
  var rows=box.querySelectorAll('.sgrow:not(.applied)');
  for(var i=0;i<rows.length;i++){
    var id=rows[i].id.replace('sg_','');
    var field=rows[i].querySelector('.sgfield').textContent;
    await applySuggestion(sku, field, id);
  }
  toast('Applied all suggestions');
  loadRows();
}

// ============================================================================
// AUTO-FIX LOOP: Suggest → Apply → Preview → check errors → repeat until clean
// or progress stalls. Max 8 rounds. Reports back through a floating status box.
//
// TRACE CAPTURE: every round records the AI's suggestions (field + value +
// source + confidence), which values were actually applied to the sheet, the
// full Amazon error banner (verbatim [E] lines), and the changed error set.
// A "Copy trace" button dumps the whole diagnostic to the clipboard as a
// pasteable block for handing to Claude in this chat -- so you can share the
// exact sequence of what happened per round instead of reconstructing it.
// ============================================================================
window.AUTOFIX_STATE = null;

// ============================================================================
// AUTO-FIX NOW RUNS ON THE SERVER, NOT IN THIS BROWSER
// ============================================================================
// This used to be a `while` loop right here: /suggest -> /edit -> /run/api, round
// after round, in the tab. So it only ran while this tab was executing JavaScript --
// locking the screen, sleeping the laptop, closing the tab or being signed out KILLED
// it mid-batch, and you came back to a half-finished run with no progress shown.
//
// The loop now lives on the server (dashboard.py :: _run_autofix_bg). These functions
// only START it and POLL it. So:
//   * it keeps running when nobody is watching;
//   * ANY signed-in browser sees the same live progress (it is SERVER state, not tab
//     state) -- including a different device, or you after signing back in;
//   * it runs to completion unless you press Stop.
// Identical behaviour locally and on Render: there is no browser dependency left.
let AF_POLL = null;

function autoFixLoop(sku){ if(sku) _afStart([sku]); }     // per-listing button
function bulkAutoFix(){                                    // toolbar button (N selected)
  const skus = (typeof selectedSkus === "function") ? selectedSkus() : [];
  if(!skus.length){ toast("Select some listings first"); return; }
  _afStart(skus);
}

async function _afStart(skus){
  try{
    const j = await (await fetch("/autofix/start", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({skus: skus})})).json();
    if(!j.ok){
      if(j.running){ toast("An auto-fix run is already going — showing it."); _afAttach(); return; }
      toast("Could not start auto-fix: " + (j.error || "unknown"));
      return;
    }
    _afPanel();
    _afPollStart();
  }catch(e){ toast("Could not start auto-fix: " + e); }
}

async function _afStopJob(){
  try{
    await fetch("/autofix/stop", {method:"POST", headers:{"Content-Type":"application/json"}, body:"{}"});
    toast("Stopping — it will halt after the current step.");
  }catch(e){ toast("Could not stop: " + e); }
}

function _afPollStart(){
  if(AF_POLL) clearInterval(AF_POLL);
  _afTick();
  AF_POLL = setInterval(_afTick, 2000);
}

async function _afTick(){
  let j;
  try{ j = await (await fetch("/autofix/state")).json(); }
  catch(e){ return; }                       // a network blip must not kill the panel
  const job = j && j.job;
  if(!job) return;
  window.AF_JOB = job;
  _afRender(job);
  if(job.status !== "running"){
    if(AF_POLL){ clearInterval(AF_POLL); AF_POLL = null; }
    try{ loadRows(); }catch(e){}
    try{ _autoFixSaveLog("server", _afTraceText(job), (job.skus||[]).length + " skus"); }catch(e){}
  }
}

// On every page load -- including a fresh sign-in on any device -- attach to whatever
// run is already in progress, so progress is never invisible just because nobody was
// watching when it started.
async function _afAttach(){
  try{
    const j = await (await fetch("/autofix/state")).json();
    // Only pop the panel open for work that is STILL RUNNING. /autofix/state also
    // returns the last finished job (so the poller can show a final result), and we
    // must not resurrect that on every page load.
    if(j && j.ok && j.job && j.job.status === "running"){
      window.AF_JOB = j.job;
      _afPanel();
      _afRender(j.job);
      _afPollStart();
    }
  }catch(e){}
}
window.addEventListener("DOMContentLoaded", function(){ setTimeout(_afAttach, 900); });

/* THE BOX AN AUTO-FIX RUN DRAWS INTO -- movable, and foldable to its title.
 *
 *     "when i am running auto fix a tab appears on the screen and it is not
 *      minimizable or floatable, it hides the content behind it"
 *
 * It was 620px wide and up to 80% of the screen tall, pinned to the bottom
 * right at z-index 9999, and the only control was a ✕ that DESTROYED it -- so
 * the choice was "cover the listings you are trying to look at" or "lose sight
 * of the run". Now it folds to its title bar and can be dragged anywhere, and
 * where you put it is remembered.
 *
 * Written once and used by all three panels (the job panel, the single-SKU
 * panel and the batch panel), which were three copies of the same inline style
 * string (CLAUDE.md Rule 12).
 */
const _AF_BOX_KEY = "alta.autofixBox";

function _afBoxState(){
  try{ return JSON.parse(localStorage.getItem(_AF_BOX_KEY) || "{}") || {}; }
  catch(e){ return {}; }
}
function _afBoxSave(patch){
  try{
    localStorage.setItem(_AF_BOX_KEY, JSON.stringify(
      Object.assign(_afBoxState(), patch || {})));
  }catch(e){}
}

/* Create (or replace) the panel element, positioned where it was left. */
function _afBox(width){
  let el = document.getElementById("autofix_panel");
  if(el) el.remove();
  el = document.createElement("div");
  el.id = "autofix_panel";
  const s = _afBoxState();
  // A saved position is only honoured if it is still ON the screen -- a box
  // dragged to the edge of a wide monitor must not vanish on a laptop.
  const onScreen = (typeof s.left === "number" && typeof s.top === "number"
                    && s.left > -40 && s.top > -10
                    && s.left < window.innerWidth - 120
                    && s.top < window.innerHeight - 40);
  el.style.cssText = "position:fixed;width:" + width + "px;max-height:80vh;"+
    (onScreen ? ("left:" + s.left + "px;top:" + s.top + "px;")
              : "bottom:20px;right:20px;")+
    "background:#141b2b;border:1px solid #3b4d70;border-radius:10px;padding:12px;"+
    "box-shadow:0 8px 24px rgba(0,0,0,0.5);z-index:9999;font-size:12px;color:#e8eaed;"+
    "display:flex;flex-direction:column;gap:8px";
  if(s.min) el.classList.add("af-min");
  return el;
}

/* The header: drag handle, the caller's buttons, then fold and close. */
function _afHead(titleHtml, buttonsHtml){
  const folded = _afBoxState().min;
  return '<div class="af-head" onmousedown="_afDragStart(event)" '+
      'style="display:flex;justify-content:space-between;align-items:center;'+
      'font-weight:600;gap:10px">'+
      '<span id="af_title" style="overflow:hidden;text-overflow:ellipsis;'+
        'white-space:nowrap">' + titleHtml + '</span>'+
      '<div style="display:flex;gap:8px;align-items:center">'+
        buttonsHtml +
        '<button onclick="afBoxFold(event)" id="af_foldbtn" title="Fold this box '+
          'down to its title — the run keeps going" style="background:none;'+
          'color:#e8eaed;border:none;cursor:pointer;font-size:15px;line-height:1">'+
          (folded ? "▣" : "—") + '</button>'+
      '</div>'+
    '</div>';
}

function afBoxFold(ev){
  if(ev && ev.stopPropagation) ev.stopPropagation();
  const el = document.getElementById("autofix_panel");
  if(!el) return;
  const folded = el.classList.toggle("af-min");
  _afBoxSave({min: folded});
  const b = document.getElementById("af_foldbtn");
  if(b) b.textContent = folded ? "▣" : "—";
}

function _afDragStart(ev){
  // A press on a button is a press on that button, not the start of a drag.
  if(ev.target && ev.target.closest && ev.target.closest("button")) return;
  const el = document.getElementById("autofix_panel");
  if(!el) return;
  ev.preventDefault();
  const r = el.getBoundingClientRect();
  const dx = ev.clientX - r.left, dy = ev.clientY - r.top;
  // Switch from bottom/right anchoring to left/top so the box follows exactly.
  el.style.bottom = "auto"; el.style.right = "auto";
  function move(e){
    const left = Math.max(0, Math.min(window.innerWidth - 80, e.clientX - dx));
    const top  = Math.max(0, Math.min(window.innerHeight - 32, e.clientY - dy));
    el.style.left = left + "px"; el.style.top = top + "px";
  }
  function up(e){
    document.removeEventListener("mousemove", move);
    document.removeEventListener("mouseup", up);
    const rr = el.getBoundingClientRect();
    _afBoxSave({left: Math.round(rr.left), top: Math.round(rr.top)});
  }
  document.addEventListener("mousemove", move);
  document.addEventListener("mouseup", up);
}

function _afPanel(){
  const el = _afBox(620);
  el.innerHTML =
    _afHead("✦ Auto-fix",
      '<button onclick="_afCopyTrace()" style="background:#5b3fb8;color:#fff;border:none;'+
        'padding:4px 10px;border-radius:6px;cursor:pointer;font-size:11px">📋 Copy trace</button>'+
      '<button id="af_stopbtn" onclick="_afStopJob()" style="background:var(--red-line);color:var(--red);'+
        'border:1px solid #7a3030;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:11px">'+
        '■ Stop</button>'+
      '<button onclick="document.getElementById(\'autofix_panel\').remove()" title="Close this box '+
        '(the run KEEPS going on the server)" style="background:none;color:#e8eaed;border:none;'+
        'cursor:pointer;font-size:16px">✕</button>')+
    '<div id="af_status" style="color:var(--accent2)"></div>'+
    '<div id="af_bar" style="height:6px;background:#22293a;border-radius:4px;overflow:hidden">'+
      '<div id="af_barfill" style="height:100%;width:0%;background:#4a8cff;transition:width .3s"></div>'+
    '</div>'+
    '<div style="color:var(--ink3);font-size:11px">This runs on the server — you can lock your screen, '+
      'close this box, or sign out. It keeps going until it finishes or you press Stop.</div>'+
    '<div id="af_steps" style="overflow:auto;max-height:30vh;font-family:ui-monospace,monospace;'+
      'font-size:11px;background:#0f131a;border-radius:6px;padding:8px;white-space:pre-wrap"></div>'+
    '<div id="af_results" style="overflow:auto;max-height:26vh"></div>';
  document.body.appendChild(el);
}

function _afRender(job){
  if(!document.getElementById("autofix_panel")) return;   // the user closed the box
  const t = document.getElementById("af_title");
  const s = document.getElementById("af_status");
  const f = document.getElementById("af_barfill");
  const st = document.getElementById("af_steps");
  const rs = document.getElementById("af_results");
  const sb = document.getElementById("af_stopbtn");
  const sum = job.summary || {};
  const pct = job.total ? Math.round((job.done / job.total) * 100) : 0;

  if(t) t.textContent = "✦ Auto-fix — " + job.done + " / " + job.total + " listing(s)";
  if(f) f.style.width = pct + "%";
  if(sb) sb.style.display = (job.status === "running") ? "" : "none";

  if(s){
    if(job.status === "running"){
      s.innerHTML = '<span class="genspin"></span> ' +
        (job.current ? ("Working on <b>" + esc(job.current) + "</b>" +
                        (job.current_round ? (" · round " + job.current_round) : "")) : "Starting…");
    } else if(job.status === "stopped"){
      s.innerHTML = '<span style="color:var(--warn)">■ Stopped by you.</span>';
    } else if(job.status === "error"){
      s.innerHTML = '<span style="color:var(--red)">✗ ' + esc(job.error || "failed") + '</span>';
    } else {
      s.innerHTML = '<span style="color:var(--ok)">✓ Finished.</span>';
    }
    s.innerHTML += ' <span style="color:var(--ink3)">cleared ' + (sum.cleared||0) +
                   ' · stuck ' + (sum.stuck||0) + ' · failed ' + (sum.failed||0) +
                   ((sum.not_run) ? (' · not run ' + sum.not_run) : '') + '</span>';
  }
  if(st){
    st.textContent = (job.steps || []).slice(-60).join("\n");
    st.scrollTop = st.scrollHeight;
  }
  if(rs){
    rs.innerHTML = (job.results || []).map(function(r){
      const col = r.outcome === "cleared" ? "var(--ok)" : (r.outcome === "stuck" ? "var(--warn)" : "var(--red)");
      const mark = r.outcome === "cleared" ? "✓" : (r.outcome === "stuck" ? "▲" : "✗");
      return '<div style="border-top:1px solid #22293a;padding:6px 2px">'+
             '<span style="color:'+col+';font-weight:700">'+mark+' '+esc(r.sku)+'</span> '+
             '<span style="color:var(--ink3)">('+esc(r.outcome)+', '+(r.rounds||[]).length+' round(s))</span>'+
             (r.diagnosis ? ('<div style="color:var(--ink2);margin-top:2px">'+esc(r.diagnosis)+'</div>') : '')+
             '</div>';
    }).join("");
  }
}

function _afTraceText(job){
  const L = [];
  L.push("=== AUTO-FIX (server) ===");
  L.push("Started: " + (job.started_at || ""));
  L.push("Account: " + (job.account_id || ""));
  L.push("Status:  " + job.status + (job.error ? (" — " + job.error) : ""));
  const s = job.summary || {};
  L.push("Summary: cleared=" + (s.cleared||0) + " · stuck=" + (s.stuck||0) +
         " · failed=" + (s.failed||0) + " · not run=" + (s.not_run||0) +
         "   (of " + job.total + ")");
  L.push("");
  (job.results || []).forEach(function(r, i){
    L.push("################################################################");
    L.push("# " + (i+1) + ". " + r.sku + "  ->  " + r.outcome);
    L.push("################################################################");
    if(r.diagnosis) L.push("DIAGNOSIS: " + r.diagnosis);
    (r.rounds || []).forEach(function(rd){
      L.push("");
      L.push("-- round " + rd.round + " --");
      (rd.suggestions || []).forEach(function(x){
        L.push("   suggest " + x.field + " = " + String(x.value).slice(0,80) +
               (x.code_owned ? "   [code-owned]" : "   [" + (x.source||"") + "]"));
      });
      (rd.applied || []).forEach(function(x){ L.push("   APPLIED " + x.field); });
      (rd.skipped || []).forEach(function(x){ L.push("   skipped " + x.field + " — " + x.reason); });
      L.push("   PREVIEW: " + rd.verdict +
             ((rd.error_fields||[]).length ? ("  flagged: " + rd.error_fields.join(", ")) : ""));
      if(rd.diagnosis) L.push("   " + rd.diagnosis);
    });
    L.push("");
  });
  L.push("=== END ===");
  return L.join("\n");
}

function _afCopyTrace(){
  const job = window.AF_JOB;
  if(!job){ toast("Nothing to copy yet"); return; }
  const txt = _afTraceText(job);
  try{ navigator.clipboard.writeText(txt); toast("Trace copied"); }
  catch(e){ toast("Copy failed"); }
}

// Runs one Preview and returns a verdict object. Also appends every stream line
// to roundEntry.preview_raw_lines so the trace has the full Amazon response
// for that round.
function _autoFixPreview(sku, panel, roundEntry){
  return new Promise(function(resolve){
    const url = '/run/api?skus='+encodeURIComponent(sku)+_minParam();
    const es = new EventSource(url);
    let verdict = null;
    let errorFields = [];
    let sawStart = false;
    let done = false;
    function finish(v){
      if(done) return; done=true;
      try{ es.close(); }catch(e){}
      v.errorFields = errorFields;
      resolve(v);
    }
    es.onmessage = function(e){
      const d = e.data || '';
      if(panel) panel.log(d);
      if(roundEntry) roundEntry.preview_raw_lines.push(d);
      if(d.indexOf('[start]') === 0) sawStart = true;
      // parse [E] field markers -- track ALL, not just first-per-line, in case
      // multiple errors share one message
      const mm = d.match(/\[E\]\s*([a-z0-9_.]+)/g);
      if(mm){
        mm.forEach(function(x){
          const m2 = x.match(/\[E\]\s*([a-z0-9_.]+)/);
          if(m2 && errorFields.indexOf(m2[1]) < 0) errorFields.push(m2[1]);
        });
      }
      // detect final verdict lines
      if(d.indexOf(sku) >= 0){
        const low = d.toLowerCase();
        let m = d.match(/(\d+)\s+error\(s\)/i);
        if(m){ verdict = {kind:'error', n:parseInt(m[1]), raw:d}; }
        else if(low.indexOf('missing') >= 0 && low.indexOf('skip') >= 0){ verdict = {kind:'missing', raw:d}; }
        else if(low.indexOf('api_ready') >= 0 || low.indexOf('preview clean') >= 0){ verdict = {kind:'ok_preview', raw:d}; }
        else if(low.indexOf('api call failed') >= 0 || low.indexOf('api_error') >= 0){ verdict = {kind:'error', n:0, raw:d}; }
      }
      if(d.toLowerCase().indexOf('no seller_id') >= 0) verdict = {kind:'nocreds', raw:d};
      if(d.indexOf('[done]') === 0 || d.indexOf('[busy]') >= 0){
        if(d.indexOf('[busy]') >= 0 && !verdict) verdict = {kind:'busy', raw:d};
        finish(verdict || {kind:'unknown', raw:d});
      }
      if(/getaddrinfo failed|failed to resolve|nameresolutionerror/i.test(d)){
        verdict = {kind:'network', raw:d};
      }
    };
    es.onerror = function(){
      // EventSource fires onerror on server-side stream end too, so treat this
      // as "the stream is done"; use whatever verdict we've collected so far.
      if(!done) finish(verdict || {kind: sawStart ? 'unknown' : 'network', raw:'stream ended'});
    };
    setTimeout(function(){
      if(!done) finish(verdict || {kind:'timeout', raw:'exceeded 5 minutes'});
    }, 5*60*1000);
  });
}

// Build a plain-text trace of the whole loop, ready to paste to Claude.
function _autoFixTraceText(state){
  const lines = [];
  lines.push('=== AUTO-FIX TRACE ===');
  lines.push('SKU: '+state.sku);
  lines.push('Started: '+state.startedAt);
  lines.push('Rounds run: '+state.trace.length+' / '+8);
  lines.push('');
  state.trace.forEach(function(r){
    lines.push('---- ROUND '+r.round+' ('+r.started_at+') ----');
    lines.push('');
    lines.push('SUGGESTIONS FROM AI ('+r.suggestions.length+' total):');
    if(r.suggestions.length === 0){
      lines.push('  (none)');
    } else {
      r.suggestions.forEach(function(s){
        const tag = s.code_owned ? '[CODE-OWNED]' : '[AI]';
        lines.push('  '+tag+' '+s.field+' = '+JSON.stringify(s.value)+
                    '  (source: '+(s.source||'-')+', confidence: '+(s.confidence||'-')+')');
        if(s.note) lines.push('    note: '+s.note);
      });
    }
    lines.push('');
    lines.push('APPLIED TO SHEET ('+r.applied.length+'):');
    if(r.applied.length === 0){
      lines.push('  (none applied)');
    } else {
      r.applied.forEach(function(a){
        lines.push('  ✓ '+a.field+' = '+JSON.stringify(a.value)+'  (from: '+(a.source||'-')+')');
      });
    }
    if(r.skipped.length){
      lines.push('');
      lines.push('SKIPPED ('+r.skipped.length+'):');
      r.skipped.forEach(function(x){
        lines.push('  ✗ '+x.field+' — '+x.reason);
      });
    }
    lines.push('');
    // Distinguish "the Preview ran and told us nothing" from "the Preview never ran".
    // Both used to print `VERDICT: null` + `(no stream lines received)`, which reads
    // like Amazon returned nothing when in fact we never asked it.
    lines.push('PREVIEW VERDICT: '+(r.preview_skipped
      ? 'not run — the loop stopped before previewing (nothing new to apply)'
      : r.preview_verdict));
    if(r.preview_error_fields && r.preview_error_fields.length){
      lines.push('Amazon flagged ('+r.preview_error_fields.length+'): '+
                  r.preview_error_fields.join(', '));
    }
    lines.push('');
    lines.push(r.preview_skipped
      ? 'PREVIEW STREAM: (Preview was not run this round — see the previous round for Amazon’s last response)'
      : 'PREVIEW STREAM (full Amazon response, verbatim):');
    // Include EVERY raw line, not a filtered subset. Filtering was hiding
    // parser mismatches (e.g. verdict `unknown` with an empty filtered view
    // when the stream actually did contain success/error lines the parser
    // failed to recognise). The full stream lets us see what Amazon sent
    // vs what our parser did with it, without which "unknown outcome"
    // diagnoses are un-debuggable.
    const raw_all = r.preview_raw_lines || [];
    if(raw_all.length){
      raw_all.forEach(function(x){ lines.push('  | '+x); });
    } else if(!r.preview_skipped){
      lines.push('  (no stream lines received — Amazon returned nothing, or the stream died)');
    }
    lines.push('');
    if(r.diagnosis){
      lines.push('DIAGNOSIS: '+r.diagnosis);
      lines.push('');
    }
  });
  lines.push('=== END TRACE ===');
  return lines.join('\n');
}

// Persist an auto-fix trace to the server (a timestamped file) so a page refresh can't
// lose it -- the on-screen trace is otherwise browser-memory only. Fire-and-forget.
function _autoFixSaveLog(kind, text, note){
  if(!text) return;
  try{
    fetch('/autofix/save_log', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({kind:kind, text:text,
        account:(window.CUR_ACCOUNT&&window.CUR_ACCOUNT.id)||'', note:note||''})})
      .then(function(r){ return r.json(); })
      .then(function(j){ if(j&&j.ok&&j.file){ toast('Auto-fix log saved ✓'); } })
      .catch(function(){});
  }catch(e){}
}

async function _autoFixCopyTrace(){
  const state = window._AUTOFIX_LAST_STATE || window.AUTOFIX_STATE;
  if(!state){ toast('No auto-fix trace to copy'); return; }
  const text = _autoFixTraceText(state);
  try{
    await navigator.clipboard.writeText(text);
    toast('Trace copied — paste into Claude chat');
  }catch(e){
    // Clipboard API can fail in non-secure contexts; fall back to a prompt
    const w = window.open('', '_blank', 'width=700,height=500');
    if(w){
      w.document.title = 'Auto-fix trace';
      w.document.body.innerHTML = '<pre style="font:12px ui-monospace,Consolas,monospace;padding:12px;white-space:pre-wrap">'+
        text.replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</pre>';
    } else {
      prompt('Copy the trace below:', text);
    }
  }
}

// A no-op panel used when autoFixLoop runs inside a bulk batch. The batch has
// its own panel; we just need the API surface (show/step/log/etc.) so
// autoFixLoop's calls are harmless.
function _autoFixNullPanel(){
  const noop = function(){};
  return {show:noop, step:noop, log:noop, done:noop, stop:noop, fail:noop, renderTrace:noop};
}

// Floating progress panel with an in-panel trace view + Copy button
function _autoFixPanel(sku, state){
  const el = _afBox(560);          // movable + foldable, see _afBox
  el.innerHTML =
    _afHead("✦ Auto-fix: " + esc(sku),
      '<button id="autofix_copy" onclick="_autoFixCopyTrace()" '+
        'style="background:#5b3fb8;color:#fff;border:none;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:11px">'+
        '📋 Copy trace</button>'+
      '<button onclick="if(window.AUTOFIX_STATE)window.AUTOFIX_STATE.cancelled=true;'+
        'document.getElementById(\'autofix_panel\').remove()" '+
        'style="background:none;color:#e8eaed;border:none;cursor:pointer;font-size:16px">✕</button>')+
    '<div id="autofix_status" style="color:var(--accent2)"></div>'+
    '<div style="display:flex;gap:6px;font-size:10px">'+
      '<button onclick="document.getElementById(\'autofix_traceview\').style.display=\'none\';document.getElementById(\'autofix_log\').style.display=\'block\'" '+
        'style="background:#0d1220;border:1px solid #263145;color:#e8eaed;padding:3px 8px;border-radius:4px;cursor:pointer">Live log</button>'+
      '<button onclick="document.getElementById(\'autofix_log\').style.display=\'none\';document.getElementById(\'autofix_traceview\').style.display=\'block\'" '+
        'style="background:#0d1220;border:1px solid #263145;color:#e8eaed;padding:3px 8px;border-radius:4px;cursor:pointer">Round-by-round trace</button>'+
    '</div>'+
    '<div id="autofix_log" style="background:#0d1220;border:1px solid #263145;border-radius:6px;'+
      'padding:6px 8px;font-family:ui-monospace,Consolas,monospace;font-size:10px;'+
      'max-height:280px;overflow:auto;flex:1"></div>'+
    '<div id="autofix_traceview" style="display:none;background:#0d1220;border:1px solid #263145;border-radius:6px;'+
      'padding:6px 8px;font-family:ui-monospace,Consolas,monospace;font-size:10px;'+
      'max-height:280px;overflow:auto;flex:1;white-space:pre-wrap"></div>';
  document.body.appendChild(el);
  window._AUTOFIX_LAST_STATE = state;   // keep after the loop ends so Copy still works
  return {
    show: function(msg){
      const s = document.getElementById('autofix_status');
      if(s) s.innerHTML = '<span class="genspin"></span> '+esc(msg);
    },
    step: function(msg){
      const s = document.getElementById('autofix_status');
      if(s) s.innerHTML = '<span class="genspin"></span> '+esc(msg);
    },
    log: function(line){
      const l = document.getElementById('autofix_log');
      if(l){ l.textContent += line+'\n'; l.scrollTop = l.scrollHeight; }
    },
    done: function(msg){
      const s = document.getElementById('autofix_status');
      if(s) s.innerHTML = '<span style="color:var(--ok)">'+esc(msg)+'</span>';
    },
    stop: function(msg){
      const s = document.getElementById('autofix_status');
      if(s) s.innerHTML = '<span style="color:var(--warn)">⚠ '+esc(msg)+'</span>';
    },
    fail: function(msg){
      const s = document.getElementById('autofix_status');
      if(s) s.innerHTML = '<span style="color:var(--red)">✗ '+esc(msg)+'</span>';
    },
    renderTrace: function(){
      const t = document.getElementById('autofix_traceview');
      if(t) t.textContent = _autoFixTraceText(state);
    },
  };
}

// ============================================================================
// BULK AUTO-FIX: run autoFixLoop sequentially across every selected SKU.
// Sequential (not parallel) because each Preview call hits SP-API and Amazon
// rate-limits per-seller; running 20 in parallel would trip 429s and slow
// everything down. A shared trace records every SKU's rounds so one Copy
// button gives you the whole batch's diagnostic to paste to Claude.
// ============================================================================
window.BULK_AUTOFIX = null;

// (the old in-browser bulkAutoFix loop lived here; auto-fix now runs on the
//  server -- see the AUTO-FIX NOW RUNS ON THE SERVER section above)

// Build one large trace text covering every SKU in the batch, ready to paste
// to Claude in one message.
function _bulkAutoFixTraceText(batch){
  const lines = [];
  lines.push('=== BULK AUTO-FIX BATCH TRACE ===');
  lines.push('Started: '+batch.startedAt);
  lines.push('SKUs: '+batch.skus.length);
  const _accounted = batch.summary.ok + batch.summary.stuck + batch.summary.failed +
                     (batch.summary.not_run || 0);
  lines.push('Summary: cleared='+batch.summary.ok+
              ' · stuck='+batch.summary.stuck+
              ' · failed='+batch.summary.failed+
              (batch.summary.not_run ? ' · not run (cancelled)='+batch.summary.not_run : '') +
              (_accounted !== batch.skus.length
                ? '   [!] '+(batch.skus.length-_accounted)+' SKU(s) unaccounted for — this is a bug'
                : ''));
  lines.push('');
  batch.per_sku_states.forEach(function(s, idx){
    lines.push('################################################################');
    lines.push('# SKU '+(idx+1)+' of '+batch.skus.length+': '+(s.sku||'(unknown)'));
    lines.push('################################################################');
    if(s.error){
      lines.push('LOOP ERROR: '+s.error);
      lines.push('');
      return;
    }
    if(!s.trace){
      lines.push('(no trace captured)');
      lines.push('');
      return;
    }
    // Reuse the single-SKU trace formatter
    lines.push(_autoFixTraceText(s));
    lines.push('');
  });
  lines.push('=== END BATCH TRACE ===');
  return lines.join('\n');
}

async function _bulkAutoFixCopyTrace(){
  const batch = window.BULK_AUTOFIX;
  if(!batch){ toast('No batch trace to copy'); return; }
  const text = _bulkAutoFixTraceText(batch);
  try{
    await navigator.clipboard.writeText(text);
    toast('Batch trace copied — paste into Claude chat');
  }catch(e){
    const w = window.open('', '_blank', 'width=800,height=600');
    if(w){
      w.document.title = 'Bulk auto-fix trace';
      w.document.body.innerHTML = '<pre style="font:12px ui-monospace,Consolas,monospace;padding:12px;white-space:pre-wrap">'+
        text.replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</pre>';
    } else {
      prompt('Copy the trace below:', text);
    }
  }
}

function _bulkAutoFixPanel(batch){
  // Reuse the same slot as single-SKU panel so we never have two on screen
  const el = _afBox(620);          // movable + foldable, see _afBox
  el.innerHTML =
    _afHead("✦ Batch Auto-fix (" + batch.skus.length + " SKU"
              + (batch.skus.length === 1 ? "" : "s") + ")",
      '<button onclick="_bulkAutoFixCopyTrace()" '+
        'style="background:#5b3fb8;color:#fff;border:none;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:11px">'+
        '📋 Copy batch trace</button>'+
      '<button onclick="if(window.BULK_AUTOFIX)window.BULK_AUTOFIX.cancelled=true;'+
        'if(window.AUTOFIX_STATE)window.AUTOFIX_STATE.cancelled=true;'+
        'document.getElementById(\'autofix_panel\').remove()" '+
        'style="background:none;color:#e8eaed;border:none;cursor:pointer;font-size:16px" '+
        'title="Cancel batch and close">✕</button>')+
    '<div id="bulk_autofix_status" style="color:var(--accent2)"></div>'+
    '<div id="bulk_autofix_summary" style="font-size:11px;color:#bfc7d5"></div>'+
    '<div id="bulk_autofix_traceview" style="background:#0d1220;border:1px solid #263145;border-radius:6px;'+
      'padding:6px 8px;font-family:ui-monospace,Consolas,monospace;font-size:10px;'+
      'max-height:400px;overflow:auto;flex:1;white-space:pre-wrap"></div>';
  document.body.appendChild(el);
  return {
    show: function(msg){
      const s = document.getElementById('bulk_autofix_status');
      if(s) s.innerHTML = '<span class="genspin"></span> '+esc(msg);
    },
    step: function(msg){
      const s = document.getElementById('bulk_autofix_status');
      if(s) s.innerHTML = '<span class="genspin"></span> '+esc(msg);
      const sm = document.getElementById('bulk_autofix_summary');
      if(sm) sm.textContent = 'Progress: '+batch.summary.ok+' cleared · '+
                              batch.summary.stuck+' stuck · '+batch.summary.failed+' failed';
    },
    done: function(msg){
      const s = document.getElementById('bulk_autofix_status');
      if(s) s.innerHTML = '<span style="color:var(--ok)">✓ '+esc(msg)+'</span>';
    },
    stop: function(msg){
      const s = document.getElementById('bulk_autofix_status');
      if(s) s.innerHTML = '<span style="color:var(--warn)">⚠ '+esc(msg)+'</span>';
    },
    renderTrace: function(){
      const t = document.getElementById('bulk_autofix_traceview');
      if(t) t.textContent = _bulkAutoFixTraceText(batch);
    },
  };
}

function roCell(v){ return `<span class="ro">${esc(v==null?"":String(v))}</span>`; }
// Suggested Amazon browse-node IDs per product type (mirrors the generator's
// PT_DEFAULT_NODE). Used only to offer a sensible default; the field stays optional.
const PT_NODE_MAP = {
  "HEALTH_PERSONAL_CARE":"66280031", "BEAUTY":"18918424031", "KITCHEN":"3187111031",
  "HOME":"3579745031", "COOKWARE_SET":"11715891", "LAMP":"10709381",
  "HARDWARE":"1938668031", "SPORT_TARGET":"26971320031"
};
function PT_NODE_DEFAULT(){
  let pt="";
  try{ pt = (window.OPT_CURRENT&&OPT_CURRENT.product_type) || (window.OPT_EDIT_ROW&&OPT_EDIT_ROW.product_type) || ""; }catch(e){}
  return PT_NODE_MAP[(pt||"").toUpperCase()] || "";
}
// Product Type control: defaults to Amazon's catalogue-assigned type (the
// ground truth). The static list is still selectable, but choosing anything
// other than the Amazon-assigned type shows a clear warning, because that's
// what causes "product type not allowed" rejections.
function productTypeCell(sku, r){
  const amazonPT = String(r.product_type||"").trim();   // assigned by get_catalog_item
  // option list = the Amazon type first (always), then the static list
  const opts = [];
  if(amazonPT) opts.push(amazonPT);
  (PTYPES||[]).forEach(p=>{ if(p && opts.indexOf(p)<0) opts.push(p); });
  const wid="pt_"+sid(sku);
  let h=`<select id="${wid}" class="ed" onchange="onProductTypeChange(this,'${esc(sku)}','${esc(amazonPT)}')">`;
  if(!amazonPT) h+=`<option value="" selected>—</option>`;
  opts.forEach(o=>{
    const isAmz = (o===amazonPT);
    h+=`<option value="${esc(o)}"${o===amazonPT?" selected":""}>${esc(o)}${isAmz?" (Amazon-assigned)":""}</option>`;
  });
  h+=`</select>`;
  h+=`<div id="${wid}_warn" class="cwarn" style="display:none"></div>`;
  return h;
}
function onProductTypeChange(sel, sku, amazonPT){
  const warn=document.getElementById("pt_"+sid(sku)+"_warn");
  const chosen=sel.value;
  if(warn){
    if(amazonPT && chosen && chosen!==amazonPT){
      warn.style.display="block";
      warn.innerHTML="⚠ Amazon assigned this product the type <b>"+esc(amazonPT)+"</b>. "
        +"Listing it as <b>"+esc(chosen)+"</b> may be rejected. Only change this if you are certain.";
    } else { warn.style.display="none"; warn.innerHTML=""; }
  }
  // save via the normal column path
  saveEdit(sel, sku, "col", "Product Type");
  // refresh the schema for the newly chosen type so the fields update
  if(typeof loadSchemas==="function"){ var _r=ROWS.find(x=>String(x.sku)===String(sku)); loadSchemas([chosen], true, _r?rowMkt(_r):WS_MARKET).then(()=>{ if(DRAWER_SKU===sku) openDrawer(sku); }); }
}
function editCell(sku,target,key,value,opts,multiline){
  const cur=(value==null?"":String(value));
  // recommended_browse_nodes is a single Amazon category NODE ID (a number), not a
  // pick-list — Amazon never ships the full node tree as an enum. Force a free-text
  // input so users aren't stuck with an empty/irrelevant dropdown.
  const isBrowseNode = /(^|\.)recommended_browse_nodes$|(^|\.)browse_node/.test(key||"");
  if(isBrowseNode){
    const def=(typeof PT_NODE_DEFAULT==="function")?PT_NODE_DEFAULT():"";
    const ph = def?("e.g. "+def+" (suggested for this type) — optional"):"e.g. 66280031 — optional";
    return `<input class="ed" value="${esc(cur)}" placeholder="${esc(ph)}" onchange="saveEdit(this,'${esc(sku)}','${target}','${esc(key)}')">`
      + (def&&!cur?`<div class="cc" style="font-size:11px;margin-top:3px">Leave blank to let Amazon auto-assign the category, or use the suggested node <a href="#" onclick="(function(e){e.preventDefault();var i=e.target.closest('td').querySelector('input');i.value='${esc(def)}';i.dispatchEvent(new Event('change'));})(event)">${esc(def)}</a>.</div>`:"");
  }
  if(opts&&opts.length){
    let h=`<select class="ed" onchange="saveEdit(this,'${esc(sku)}','${target}','${esc(key)}')">`;
    h+=`<option value=""${cur===""?" selected":""}>—</option>`;
    if(cur&&!opts.includes(cur)) h+=`<option value="${esc(cur)}" selected>${esc(cur)} (current)</option>`;
    opts.forEach(o=>{h+=`<option value="${esc(o)}"${o===cur?" selected":""}>${esc(o)}</option>`;});
    return h+`</select>`;
  }
  if(multiline) return `<textarea class="ed" rows="3" onchange="saveEdit(this,'${esc(sku)}','${target}','${esc(key)}')">${esc(cur)}</textarea>`;
  return `<input class="ed" value="${esc(cur)}" onchange="saveEdit(this,'${esc(sku)}','${target}','${esc(key)}')">`;
}
function edRow(label,ctrl,hint,prov,sub,req,softReq,del){ const provHtml = (typeof prov==='string') ? srcBadge(prov) : (prov?iBtnEntry(prov):""); const reqHtml = softReq ? '<span class="reqsoft" title="The schema lists this as required, but Amazon\u2019s last Preview accepted the listing WITHOUT it. Fill it only if a later Preview flags it.">\u2606 schema-listed</span>' : (req?'<span class="reqstar" title="Required by Amazon">\u2605</span>':""); const delHtml = !del ? "" : (del.locked ? `<button class="cdel afdel dis" disabled title="Amazon requires this field \u2014 it can\u2019t be deleted (deleting it would fail on Preview/Submit)">\u2715</button>` : `<button class="cdel afdel" title="Delete this field from the listing" onclick="clearField('${esc(del.sku)}','${del.target}','${esc(del.key)}')">\u2715</button>`); return `<tr class="${hint?'flaggedrow':''}${sub?' subrow':''}"><td class="k">${sub?'<span class="subarrow">\u21b3</span> ':''}${esc(_cleanLabel(label))}${reqHtml}${provHtml}${delHtml}${hint?` <span class="fixhint">\u26a0 ${esc(hint)}</span>`:""}</td><td class="v">${ctrl}</td></tr>`; }
function _cleanLabel(s){ s=String(s==null?"":s); s=s.replace(/&nbsp;/g,"").replace(/\u21b3/g,"").replace(/[._]/g," ").trim(); return s.charAt(0).toUpperCase()+s.slice(1); }
function wideRow(label,ctrl){ return `<tr><td colspan="2" class="wcell"><div class="wlab">${esc(label)}</div>${ctrl}</td></tr>`; }
function ccount(el, cid, limit){
  const c=document.getElementById(cid); if(!c) return;
  const useBytes = el.getAttribute && el.getAttribute("data-bytes")==="1";
  const warnAt = parseInt((el.getAttribute&&el.getAttribute("data-warn"))||"0",10)||0;
  const n = useBytes ? (function(){try{return new Blob([el.value]).size;}catch(e){return el.value.length;}})() : el.value.length;
  const unit = useBytes ? " bytes" : " chars";
  c.textContent=n+(limit?(' / '+limit):'')+unit;
  const over = limit && n>limit;
  const warn = warnAt && n>warnAt && !over;
  c.classList.toggle('over', !!over);
  c.classList.toggle('warn', !!warn);
}
// Combined indexing meter: Amazon indexes only the FIRST ~1,000 BYTES across ALL
// 5 bullets COMBINED (not per bullet). Show how much of that budget is used.
function bulletMeter(){
  const meter=document.getElementById('bulletIdxMeter'); if(!meter) return;
  let total=0;
  for(let i=1;i<=5;i++){
    const ta=document.querySelector('textarea[data-bkt="bullet'+i+'"]');
    if(ta){ try{ total+=new Blob([ta.value]).size; }catch(e){ total+=ta.value.length; } }
  }
  const cap=1000;
  const pct=Math.min(100, Math.round(total/cap*100));
  const over=total>cap;
  meter.innerHTML='<div class="idxbar"><div class="idxfill'+(over?' over':'')+'" style="width:'+pct+'%"></div></div>'
    +'<span class="idxlbl'+(over?' over':'')+'">'+total+' / '+cap+' bytes indexed across all 5 bullets'
    +(over?' — content past 1,000 bytes is NOT indexed (still shown to shoppers)':'')+'</span>';
}
// byte length (UTF-8) — Amazon counts backend search terms + bullet indexing in BYTES, not chars
function byteLen(s){ try{ return new Blob([String(s==null?"":s)]).size; }catch(e){ return String(s==null?"":s).length; } }
// Approx file size of a data: URL (base64 -> bytes) as a human string.
function dataUrlSize(durl){
  try{
    const i=String(durl).indexOf(",");
    const b64=i>=0?String(durl).slice(i+1):String(durl);
    const bytes=Math.floor(b64.length*3/4);
    if(bytes>=1048576) return (bytes/1048576).toFixed(1)+" MB";
    if(bytes>=1024) return Math.round(bytes/1024)+" KB";
    return bytes+" B";
  }catch(e){ return ""; }
}
// Attach a small "WxH · size" label under a freshly generated image. Reads the
// image's real natural dimensions once it loads. Call from the img onload.
function imgMetaLabel(imgEl, durl){
  try{
    const w=imgEl.naturalWidth||0, h=imgEl.naturalHeight||0;
    const size=durl?dataUrlSize(durl):"";
    const txt=(w&&h)?(w+"\u00d7"+h+" px"+(size?(" \u00b7 "+size):"")):(size||"");
    let cap=imgEl.parentElement&&imgEl.parentElement.querySelector(".imgmeta");
    if(!cap){ cap=document.createElement("div"); cap.className="imgmeta"; imgEl.insertAdjacentElement("afterend",cap); }
    cap.textContent=txt;
  }catch(e){}
}
function contentRow(label, sku, colKey, value, limit, opts){
  opts = opts||{};
  const cur=(value==null?"":String(value));
  const cid="cc_"+Math.random().toString(36).slice(2,8);
  const lim=limit||0;
  const useBytes = !!opts.bytes;
  const n = useBytes ? byteLen(cur) : cur.length;
  // soft warn threshold (e.g. title 75-char hard cap inside a 200 system max)
  const warnAt = opts.warnAt||0;
  const over = lim && n>lim;
  const warn = warnAt && n>warnAt && !over;
  const unit = useBytes ? " bytes" : " chars";
  const counter=`<span class="cc${over?' over':(warn?' warn':'')}" id="${cid}">${n}${lim?' / '+lim:''}${unit}</span>`;
  const idx = opts.indexNote ? `<span class="idxnote" title="${esc(opts.indexTip||'')}">${esc(opts.indexNote)}</span>` : "";
  const warnmsg = opts.warnMsg && (warn||over) ? `<div class="cwarn">⚠ ${esc(opts.warnMsg)}</div>` : "";
  const rows = opts.rows||3;
  const tgt = opts.target||"col";
  const ta=`<textarea class="ed" rows="${rows}" data-bkt="${esc(opts.bucket||'')}" data-bytes="${useBytes?1:0}" data-warn="${warnAt}" data-lim="${lim}" oninput="ccount(this,'${cid}',${lim});bulletMeter()" onchange="saveEdit(this,'${esc(sku)}','${tgt}','${esc(colKey)}')">${esc(cur)}</textarea>`;
  return `<tr><td colspan="2" class="wcell"><div class="wlab">${esc(label)} ${counter} ${idx}${opts.controls?(' '+opts.controls):''}</div>${warnmsg}${ta}</td></tr>`;
}
function edRowReq(label,ctrl,hint){ return `<tr class="reqrow"><td class="k"><span class="klabel">${esc(label)}<span class="reqstar" title="Required by Amazon">\u2605</span></span> <span class="reqtag">needs value</span>${hint?`<span class="fixhint">\u26a0 ${esc(hint)}</span>`:""}</td><td class="v">${ctrl}</td></tr>`; }
function sid(s){ return String(s).replace(/[^a-zA-Z0-9]/g,"_"); }
function parseMissing(notes){
  // pull field names Amazon's preview flagged as "required but missing" (ground truth)
  if(!notes) return [];
  const out=[];
  String(notes).split(";").forEach(p=>{
    const m=p.match(/\[E\]\s+(\S+)\s+.*required but missing/i);
    if(m && m[1]) out.push(m[1]);
  });
  return out;
}
const AXIS_FIELD={width:"item_width",depth:"item_depth",height:"item_height",length:"item_length"};
// Plain-English, value-specific guidance shown UNDER the flagged field so the
// user knows exactly what to enter. Keyed by Amazon attribute name. Generic
// errors fall through to the phrasing matchers below; only known fields get a
// precise instruction here. Sub-field errors (e.g. hazmat.aspect) inherit the
// parent's hint, and the hazmat parent also carries the full instruction.
// The attribute names that mean "whose product is this". None of them is
// editable here -- see renderAttr for why. Kept beside SPECIFIC_HINT because
// both answer the same question: what does this field actually want.
const BRAND_KEYS=["brand","brand_name","manufacturer"];

const SPECIFIC_HINT={
  hazmat:"Lithium battery item. Aspect = united_nations_regulatory_id, Value = UN3481 (battery packed in equipment).",
  contains_battery_or_cell:"App fills this automatically on Preview (Yes / true to match Amazon's list). You don't need to type here.",
  batteries_included:"Pick Yes / No from the list (not the word True).",
  batteries_required:"Pick Yes / No from the list (not the word True).",
  battery_installation_device_type:"For a LITHIUM battery, Amazon requires not_installed (installed_in_equipment is rejected for lithium). Other valid values: installed_in_vehicle, installed_in_vessel. The word Flashlight is NOT accepted.",
  wattage:"Enter a number AND pick the Wattage Unit (e.g. watts) — or remove wattage entirely.",
  warranty_description:"Type the warranty text, e.g. 1 Year Manufacturer Warranty.",
  special_feature:"Enter each feature as its own value (this is the singular field Amazon wants, not Special features).",
  model_name:"Enter the model name / number for this product.",
  supplier_declared_dg_hz_regulation:"Is this product hazardous/dangerous to ship? For a normal non-chemical, non-battery item (e.g. a hand tool) choose \u201cnot_applicable\u201d. Only pick a regulation (e.g. for lithium batteries or chemicals) if the product actually contains one.",
  lithium_battery_packaging:"Battery is inside the device — choose batteries_contained_in_equipment."
};
// Per-sub-field guidance for nested compliance attributes (key = "parent.subpath").
const SUBFIELD_HINT={
  "hazmat.aspect":"Choose united_nations_regulatory_id.",
  "hazmat.value":"Type UN3481 (lithium-ion battery packed with equipment).",
  "hazmat.united_nations_regulatory_id":"Type UN3481."
};
function parseFlagged(notes, isValidField, sink){
  // {field: hint} for every fixable attribute issue Amazon flagged in the last preview.
  // Maps composite dimension errors (item_depth_width_height) to the editable axis field.
  // isValidField(name) (optional): a predicate that returns true only for names that are
  // real attributes in the fetched product-type schema. When supplied, any extracted token
  // that fails it is NOT turned into an editable field -- its raw text is pushed to `sink`
  // (an array) to be shown as plain prose instead. This is the second guard: a regex must
  // never be the only thing between Amazon's human message and a rendered form field.
  const out={};
  if(!notes) return out;
  String(notes).split(";").forEach(seg=>{
    // CASE-SENSITIVE ON PURPOSE (no /i): real Amazon attribute names are ALWAYS lowercase
    // snake_case (item_type_keyword, part_number). With /i the [a-z] class also matched the
    // capitalised first word of Amazon's PROSE ("The Listing data...", "Your offer...") and
    // rendered "The"/"Your" as phantom input fields. The leading [a-z] now anchors to a real
    // lowercase attribute token only.
    const m=seg.match(/\[[EW]\]\s+([a-z][a-z0-9_]+)\s+([\s\S]*)/);   // skips non-attribute "fields" like a bare barcode number
    if(!m) return;
    const field=m[1].toLowerCase(), msg=m[2];
    // Second guard: the token looks lowercase but isn't a real schema attribute -> don't make
    // a field for it; surface Amazon's message as plain text.
    if(typeof isValidField==="function" && !isValidField(field)){
      if(sink) sink.push(seg.trim());
      return;
    }
    if(/required but missing/i.test(msg)){ if(!out[field]) out[field]="required"; return; }
    let mm=msg.match(/at least '([^']+)'\s+(\w+)\s+for '([^']+)'/i);
    if(mm){ out[AXIS_FIELD[mm[3].toLowerCase()]||field]="must be at least "+mm[1]+" "+mm[2]; return; }
    mm=msg.match(/at most '([^']+)'\s+(\w+)\s+for '([^']+)'/i);
    if(mm){ out[AXIS_FIELD[mm[3].toLowerCase()]||field]="must be at most "+mm[1]+" "+mm[2]; return; }
    mm=msg.match(/must be at least '([^']+)'\s*(\w+)?/i);
    if(mm){ out[field]="must be at least "+mm[1]+(mm[2]?(" "+mm[2]):""); return; }
    // SPECIFIC, ACTIONABLE HINT for the common compliance offenders, so the box
    // tells the user exactly WHAT to enter (not just "choose a value"). Overrides
    // the generic phrasing below. Falls through to generic/catch-all if unknown.
    if(SPECIFIC_HINT[field]){ out[field]=SPECIFIC_HINT[field]; return; }
    if(/not a valid value|approved value|select an approved/i.test(msg)){ out[field]="choose an allowed value"; return; }
    if(/does not have the expected value|expected value|unexpected value|invalid value|not.*expected/i.test(msg)){ out[field]="choose an allowed value"; return; }
    if(/less than the minimum|greater than the maximum|out of range/i.test(msg)){ out[field]="value out of allowed range"; return; }
    // CATCH-ALL: any other error Amazon flagged on a real attribute still gets a
    // visible box, so a field is NEVER silently dropped from the editor just
    // because its error phrasing is new. (This is what hid `hazmat` before.)
    if(!out[field]) out[field]="Amazon flagged this — review the value";
    return;
  });
  return out;
}
function addField(sku, pt, sel){
  const k=sel.value; if(!k) return;
  const sc=SCHEMAS[pt]||{opts:{}}; const opts=(sc.opts||{}); const subs=(sc.subs||{});
  const tb=document.getElementById("added_"+sid(sku));
  if(!tb){ sel.value=""; return; }
  if(tb.querySelector('tr[data-fk="'+k+'"]')){ sel.value=""; return; }
  const sf=subs[k];
  if(sf&&sf.length){
    const head=document.createElement("tr");
    head.setAttribute("data-fk",k); head.className="subhead";
    head.innerHTML='<td class="k" colspan="2"><b>'+k.replace(/_/g," ")+'</b></td>';
    tb.appendChild(head);
    sf.forEach(s=>{
      const full=k+"."+s.path;
      const tr=document.createElement("tr");
      tr.className='subrow';
      tr.innerHTML='<td class="k"><span class="subarrow">\u21b3</span> '+esc(_cleanLabel(s.label))+'</td><td class="v">'+editCell(sku,"attr",full,"",(s.enum&&s.enum.length?s.enum:null))+'</td>';
      tb.appendChild(tr);
    });
  }else{
    const tr=document.createElement("tr");
    tr.setAttribute("data-fk",k);
    tr.innerHTML='<td class="k">'+k.replace(/_/g," ")+'</td><td class="v">'+editCell(sku,"attr",k,"",opts[k]||null)+'</td>';
    tb.appendChild(tr);
  }
  for(let i=sel.options.length-1;i>=0;i--){ if(sel.options[i].value===k) sel.remove(i); }
  sel.value="";
}
const COLMAP={"Title":"title","Description (HTML)":"description","Search Terms / KW":"search_terms",
  "Our Price (GBP)":"price","Brand":"brand","UPC":"barcode","Handling Days":"handling_days","Product Type":"product_type"};
function updateLocalCol(r,key,value){
  if(key in COLMAP){ r[COLMAP[key]]=value; return; }
  const m=key.match(/^Bullet (\d)$/); if(m){ r.bullets=r.bullets||[]; r.bullets[+m[1]-1]=value; }
}
async function saveEdit(el,sku,target,key){
  const value=el.value; el.classList.remove("saved","err"); el.classList.add("saving");
  try{
    const res=await fetch("/edit",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku,target,key,value})});
    const j=await res.json(); el.classList.remove("saving");
    if(j.ok){ el.classList.add("saved"); toast("Saved ✓"); setTimeout(()=>el.classList.remove("saved"),1000);
      const r=ROWS.find(x=>x.sku===sku);
      if(r){ if(target==="attr"){ r.attributes=r.attributes||{};
               if(String(value).trim()==="") delete r.attributes[key]; else r.attributes[key]=value; }
             else updateLocalCol(r,key,value); }
    } else { el.classList.add("err"); toast("Save failed: "+(j.error||"")); }
  }catch(e){ el.classList.remove("saving"); el.classList.add("err"); toast("Save failed: "+e); }
}

// ============================================================================
// FULL EDITOR -- field delete + bullet management (Seller-Central-style)
// ============================================================================
// Rebuild just the drawer's full-data block after a structural edit (delete /
// add / reorder), without touching the run panel above it.
function _rebuildDrawerData(sku){
  const r=ROWS.find(x=>String(x.sku)===String(sku));
  const host=document.getElementById("fulldata_"+sid(sku));
  if(host && r){ host.innerHTML=fullData(r); setTimeout(()=>{ if(typeof bulletMeter==='function') bulletMeter(); }, 40); }
}
// Delete/clear a field. Attributes -> the key is REMOVED; columns/content -> the cell
// is blanked. `refresh` rebuilds the block so a deleted attribute row disappears.
async function clearField(sku, target, key, refresh){
  if(!confirm("Delete '"+key+"' from this listing?")) return;
  try{
    const j=await (await fetch("/edit",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku, target, key, value:""})})).json();
    if(!j || !j.ok){ toast("Delete failed: "+((j&&j.error)||"unknown")); return; }
    const r=ROWS.find(x=>String(x.sku)===String(sku));
    if(r){ if(target==="attr"){ r.attributes=r.attributes||{}; delete r.attributes[key]; }
           else if(typeof updateLocalCol==="function") updateLocalCol(r,key,""); }
    toast("Deleted ✓");
    if(refresh!==false) _rebuildDrawerData(sku);
  }catch(e){ toast("Delete failed: "+e); }
}

// ---- bullets (stored as sheet columns "Bullet 1".."Bullet 5", Amazon max 5) ----
const MAX_BULLETS=5;
// Persist the whole bullet set: write all 5 columns (blank the unused) so the sheet
// exactly matches the array -- this is what makes reorder / remove-and-compact stick.
async function _saveBullets(sku, bullets){
  const arr=(bullets||[]).slice(0, MAX_BULLETS);
  for(let i=0;i<MAX_BULLETS;i++){
    await fetch("/edit",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku, target:"col", key:"Bullet "+(i+1), value:(arr[i]||"")})});
  }
  const r=ROWS.find(x=>String(x.sku)===String(sku));
  if(r) r.bullets=arr;
}
function bulletControls(sku, i, total){
  const up   = i>0        ? `<button class="bctl" title="Move up" onclick="moveBullet('${esc(sku)}',${i},-1)">↑</button>` : `<button class="bctl dis" disabled>↑</button>`;
  const down = i<total-1  ? `<button class="bctl" title="Move down" onclick="moveBullet('${esc(sku)}',${i},1)">↓</button>`  : `<button class="bctl dis" disabled>↓</button>`;
  const del  = `<button class="bctl del" title="Delete this bullet" onclick="removeBullet('${esc(sku)}',${i})">✕</button>`;
  return `<span class="bctls">${up}${down}${del}</span>`;
}
async function addBullet(sku){
  const r=ROWS.find(x=>String(x.sku)===String(sku)); if(!r) return;
  r.bullets=r.bullets||[];
  if(r.bullets.length>=MAX_BULLETS){ toast("Amazon allows a maximum of 5 bullet points"); return; }
  r.bullets.push("");
  await _saveBullets(sku, r.bullets);
  _rebuildDrawerData(sku);
}
async function removeBullet(sku, i){
  const r=ROWS.find(x=>String(x.sku)===String(sku)); if(!r||!r.bullets) return;
  if((r.bullets[i]||"").trim() && !confirm("Delete bullet "+(i+1)+"?")) return;
  r.bullets.splice(i,1);                         // remove AND compact -> no empty slot
  await _saveBullets(sku, r.bullets);
  _rebuildDrawerData(sku);
}
async function moveBullet(sku, i, dir){
  const r=ROWS.find(x=>String(x.sku)===String(sku)); if(!r||!r.bullets) return;
  const j=i+dir; if(j<0||j>=r.bullets.length) return;
  const t=r.bullets[i]; r.bullets[i]=r.bullets[j]; r.bullets[j]=t;
  await _saveBullets(sku, r.bullets);
  _rebuildDrawerData(sku);
}
// Schema-state diagnostic strip. The #1 reason flagged boxes render without
// dropdowns (or look "empty/shrunk") is that the LIVE Amazon schema for this
// product type failed to load in the browser -- so enums is empty and every
// field falls back to a plain text box. This makes that state visible and gives
// a one-click reload, instead of silently looking broken.
function schemaDiag(pt, nEnum, nAttrs, nSubs, missing, flagged, a){
  if(!pt) return "";
  const loaded = !!(SCHEMAS[pt] && (SCHEMAS[pt].attrs||[]).length);
  const flaggedKeys=Object.keys(flagged||{});
  const SS=(SCHEMAS[pt]||{});
  const hasList=(k)=>{
    if(SS.opts && SS.opts[k] && SS.opts[k].length) return true;        // top-level dropdown
    const sf=(SS.subs||{})[k];                                          // nested: any sub-field with a list
    if(sf && sf.some(s=>s.enum && s.enum.length)) return true;
    return false;
  };
  const noDropdown=flaggedKeys.filter(k=>!hasList(k));
  if(loaded && nEnum>0){
    // healthy: schema loaded with enums. Tiny unobtrusive confirmation.
    let note="";
    if(flaggedKeys.length && noDropdown.length){
      note=`<div style="font-size:11px;color:#c9a227;margin-top:4px">${noDropdown.length} flagged field(s) have no preset list from Amazon (${noDropdown.map(esc).join(", ")}) — these are free-text: type the value Amazon expects.</div>`;
    }
    return `<div class="schemadiag ok">Amazon schema loaded for <b>${esc(pt)}</b> · ${nEnum} field(s) with dropdown values, ${nAttrs} total, ${nSubs} nested.${note}</div>`;
  }
  // unhealthy: schema not loaded / empty -> THIS is why boxes look broken
  return `<div class="schemadiag bad">
    <b>⚠ Amazon's value lists for “${esc(pt)}” haven't loaded in this view.</b>
    That's why flagged fields show as plain boxes without dropdowns. The listing data is still editable, but the allowed-value menus are missing.
    <div style="margin-top:6px">
      <button class="ghost" onclick="reloadSchemaNow('${esc(pt)}')"><i class="ti ti-refresh"></i> Reload Amazon values now</button>
      <button class="ghost" onclick="dumpSchemaState('${esc(pt)}')"><i class="ti ti-bug"></i> Show what loaded</button>
    </div>
    <div id="schemadump_${sid(pt)}" style="font-size:11px;color:#9bb;margin-top:6px;white-space:pre-wrap"></div>
  </div>`;
}
async function reloadSchemaNow(pt){
  toast("Reloading Amazon values for "+pt+"…");
  try{
    var _r = DRAWER_SKU ? ROWS.find(x=>String(x.sku)===String(DRAWER_SKU)) : null;
    var _mkt = _r ? rowMkt(_r) : WS_MARKET;
    if(typeof loadSchemas==="function"){ await loadSchemas([pt], true, _mkt); }
    if(DRAWER_SKU){ const fr=ROWS.find(x=>String(x.product_type)===String(pt)&&String(x.sku)===String(DRAWER_SKU)) || ROWS.find(x=>String(x.sku)===String(DRAWER_SKU)); const host=document.getElementById("fulldata_"+sid(DRAWER_SKU)); if(host&&fr){ host.innerHTML=fullData(fr); } }
    const s=SCHEMAS[pt]||{};
    const n=(s.opts?Object.keys(s.opts).length:0);
    toast(n>0?("Loaded "+n+" value lists ✓"):"Still empty — Amazon schema call returned nothing. Check the app's terminal for an SP-API error.");
  }catch(e){ toast("Reload failed: "+(e&&e.message||e)); }
}
async function dumpSchemaState(pt){
  const el=document.getElementById("schemadump_"+sid(pt));
  var _r = DRAWER_SKU ? ROWS.find(x=>String(x.sku)===String(DRAWER_SKU)) : null;
  var _mkt = _r ? rowMkt(_r) : WS_MARKET;
  let txt="listing marketplace: "+(_mkt||"(none)")+"\nclient SCHEMAS["+pt+"]: ";
  const s=SCHEMAS[pt];
  if(!s){ txt+="NOT LOADED\n"; } else {
    txt+= (s.attrs||[]).length+" attrs, "+(s.opts?Object.keys(s.opts).length:0)+" enums, "+(s.subs?Object.keys(s.subs).length:0)+" nested\n";
  }
  // also ask the server directly so we can compare
  try{
    const j=await (await fetch("/schema/"+encodeURIComponent(pt)+"?refresh=1"+(_mkt?("&mkt="+encodeURIComponent(_mkt)):""))).json();
    if(j.ok){ txt+="server /schema ("+(j.marketplace||"?")+"): "+(j.attrs||[]).length+" attrs, "+Object.keys(j.enums||{}).length+" enums, "+Object.keys(j.subfields||{}).length+" nested\n";
      txt+="enum fields: "+Object.keys(j.enums||{}).slice(0,30).join(", ");
    } else { txt+="server /schema ERROR: "+(j.error||"unknown")+"\n"; }
  }catch(e){ txt+="server /schema fetch failed: "+(e&&e.message||e); }
  if(el) el.textContent=txt;
}
function fullData(r){
  try{
    return _fullDataInner(r);
  }catch(err){
    // Never let a render error silently collapse the drawer into empty boxes.
    // Show what failed so it can be fixed instead of guessed at.
    return `<details open><summary>Full listing data</summary>
      <div style="background:#3a1212;border:1px solid #6b2222;border-radius:8px;padding:12px;margin:8px 0">
        <b style="color:var(--red)">This listing's detail view hit an error while rendering.</b>
        <div style="font-size:12px;color:#ffb3b3;margin-top:6px">${esc(String(err&&err.message||err))}</div>
        <div style="font-size:11px;color:#c98;margin-top:8px">The raw data is still below so you can read/edit it.</div>
        <pre class="raw" style="display:block;margin-top:8px">${esc(JSON.stringify(r,null,2))}</pre>
      </div></details>`;
  }
}
function _fullDataInner(r){
  const sku=r.sku;
  const sc=SCHEMAS[r.product_type]||{opts:{},req:[],attrs:[],subs:{},titles:{}};
  const enums=sc.opts||{}, reqList=sc.req||[], allAttrs=sc.attrs||[];
  const titles=sc.titles||{};
  // Amazon's REAL field label (matches Seller Central) -> falls back to prettified key
  const lbl=(k)=> titles[k] || _cleanLabel(String(k));
  const idRows=[
    edRow("Product type", productTypeCell(sku, r), "Amazon-assigned from the catalogue. Changing it can cause rejection."),
    edRow("SKU", roCell(r.sku)),
    edRow("Brand", editCell(sku,"col","Brand",r.brand), null, (rowProvenance(r)||{}).brand),
    edRow("Condition", roCell("New")),
    edRow("Category", roCell((r.category||r.amazon_category||"")+(r.subcategory?(" › "+r.subcategory):""))),
    edRow("Browse node(s)", roCell((r.attributes||{}).recommended_browse_nodes||(r.attributes||{}).browse_node||"—")),
    edRow("Barcode / GTIN", editCell(sku,"col","UPC",r.barcode)),
    (function(){
       // Currency follows the ACTIVE workspace marketplace (reliable), with a
       // per-row override if the row itself carries a marketplace.
       var rowMkt = String(r._marketplace||(r.attributes||{}).marketplace||"").toUpperCase();
       var mkt = rowMkt || String(WS_MARKET||"").toUpperCase() || "UK";
       var cur = (mkt==="US"||mkt==="CA"||mkt==="MX") ? "$"
               : (mkt==="EU"||["DE","FR","IT","ES","NL"].indexOf(mkt)>=0) ? "\u20ac" : "\u00a3";
       var raw=String(r.price==null?"":r.price);
       var num=raw.replace(/[^0-9.\-]/g,"");            // strip any currency -> number only
       return edRow("Price ("+cur+")", '<span class="curlbl">'+cur+'</span>'+editCell(sku,"col","Our Price (GBP)",num));
    })(),
    edRow("List price", roCell((function(){var lp=(r.attributes||{}).list_price; return lp?String(lp).replace(/[^0-9.\-]/g,"")||"—":"—";})())),
    edRow("Quantity — blank = default 10", editCell(sku,"attr","fulfillment_quantity",(r.attributes||{}).fulfillment_quantity||"")),
    (function(){
       var rowMkt = String(r._marketplace||(r.attributes||{}).marketplace||"").toUpperCase();
       var mkt = rowMkt || String(WS_MARKET||"").toUpperCase() || "UK";
       var cur = (mkt==="US"||mkt==="CA"||mkt==="MX") ? "$"
               : (mkt==="EU"||["DE","FR","IT","ES","NL"].indexOf(mkt)>=0) ? "\u20ac" : "\u00a3";
       var pnum=String(r.profit==null?"":r.profit).replace(/[^0-9.\-]/g,"");
       return edRow("Profit ("+cur+")", roCell(pnum?(cur+pnum):"—"));
    })(),
    edRow("Handling days", editCell(sku,"col","Handling Days",r.handling_days)),
    edRow("Shipping group", roCell(SHIP)),
  ].join("");
  const a=r.attributes||{};
  const IMGRE=/^(main_product_image_locator|other_product_image_locator_\d+)$/;
  const imgUrls=Object.keys(a).filter(k=>IMGRE.test(k)).sort().map(k=>a[k]).filter(Boolean);
  const HIDEKEYS=new Set([...Object.keys(a).filter(k=>IMGRE.test(k)),"fulfillment_quantity"]);
  // The product identifier is edited ONLY via the single "Barcode / GTIN" box above
  // (the UPC column, which the builder actually sends to Amazon). Never render these as
  // separate editor fields -- two barcode boxes that can silently diverge is exactly what
  // confused the user ("External Product ID" showing a stale/leftover value).
  const _BARCODE_HANDLED=new Set(["externally_assigned_product_identifier","standard_product_id","merchant_suggested_asin","sku","supplier_declared_has_product_identifier_exemption"]);
  const _AHIDE=new Set(["_provenance","provenance"]); const aKeys=Object.keys(a).filter(k=>!HIDEKEYS.has(k) && !_BARCODE_HANDLED.has(String(k).split(".")[0]));
  // fields the script fills itself (structural / identity / dimensions) -- never shown as needs-value
  const EXCLUDE_REQ=new Set(["item_name","bullet_point","product_description","generic_keyword","purchasable_offer","fulfillment_availability","brand","condition_type","merchant_shipping_group","supplier_declared_has_product_identifier_exemption","externally_assigned_product_identifier","list_price","manufacturer","model_number","part_number","item_dimensions","item_package_dimensions","item_depth_width_height","item_length_width_height","website_shipping_weight","recommended_browse_nodes","browse_node","browse_nodes"]);
  // required-but-missing = schema top-level required UNION the fields Amazon's last preview flagged
  // Validate every field name Amazon's message yields against the product-type SCHEMA we
  // already fetched, BEFORE it can become an input box. If the schema didn't load we can't
  // validate, so we don't drop anything (the /i removal above still stops the phantom words).
  const _schemaLoaded=(allAttrs||[]).length>0;
  const _axisTargets=new Set(Object.values(AXIS_FIELD));            // item_width/depth/height/length
  const _structOK=new Set(["item_depth_width_height","item_length_width_height"]);
  const isRealAttr=f=>{
    if(!_schemaLoaded) return true;
    const top=String(f).split(".")[0];
    return (allAttrs.indexOf(top)>=0) || !!enums[top] || !!(sc.subs||{})[top]
        || ((reqList||[]).indexOf(top)>=0) || !!AXIS_FIELD[top]
        || _axisTargets.has(top) || _structOK.has(top);
  };
  const _plainNotes=[];                  // Amazon prose that isn't a real field -> shown as text
  const flagged=parseFlagged(r.notes, isRealAttr, _plainNotes);   // {field: hint} from Amazon's last preview (required / min-max / invalid)
  const flaggedKeys=Object.keys(flagged);
  const reqUnion=new Set([...(reqList||[]), ...flaggedKeys]);
  // A field Amazon EXPLICITLY flagged must ALWAYS show a box, even if it's in
  // EXCLUDE_REQ (our "script fills it" assumption) -- Amazon is overriding us.
  // Only EXCLUDE_REQ filters the schema-required list, never the flagged list.
  const missing=[...reqUnion].filter(k=>{
    if(!k) return false;
    if(_BARCODE_HANDLED.has(String(k).split(".")[0])) return false; // barcode = the single box above
    if(k in a) return false;                       // already has a value
    if(flagged[k]) return true;                    // Amazon flagged it -> ALWAYS show
    if(EXCLUDE_REQ.has(k)) return false;           // script fills it (and not flagged)
    if(k.endsWith("_image_locator")) return false; // images optional
    return true;
  }).sort();
  const _prov=rowProvenance(r);
  const subs=sc.subs||{};
  // FALLBACK nested structure: when the live schema didn't load, sc.subs is empty
  // and nested fields would collapse to flat boxes (losing the structure AND the
  // "filling this requires its sub-fields" note). Rebuild the nesting from (a) any
  // dotted keys already in the data (e.g. "battery.cell_composition") and (b) a
  // known map of common Amazon nested fields. This makes the structure + note show
  // ALL the time, regardless of whether Amazon's value lists loaded this view.
  const KNOWN_NESTED={
    battery:["cell_composition","average_life","weight","charge_time","capacity"],
    hazmat:["aspect","value"],
    wattage:["value","unit"],
    unit_count:["value","type"],
    item_length:["value","unit"],
    item_width:["value","unit"],
    item_height:["value","unit"],
    item_weight:["value","unit"],
    package_weight:["value","unit"],
    voltage:["value","unit"],
    item_dimensions:["length","width","height"],
    supplier_declared_dg_hz_regulation:["value"]
  };
  function _fallbackSubs(){
    const out={};
    // (a) from dotted keys in the data
    Object.keys(a).forEach(function(key){
      const dot=key.indexOf(".");
      if(dot>0){
        const parent=key.slice(0,dot), child=key.slice(dot+1);
        if(!out[parent]) out[parent]=[];
        if(!out[parent].some(s=>s.path===child)) out[parent].push({path:child,label:child.replace(/_/g," "),enum:null});
      }
    });
    // (b) from the known map -- only add a parent that the data/attrs actually reference
    Object.keys(KNOWN_NESTED).forEach(function(parent){
      const referenced = (parent in a) || aKeys.indexOf(parent)>=0 ||
                         Object.keys(a).some(k=>k.indexOf(parent+".")===0) ||
                         (reqList||[]).indexOf(parent)>=0;
      if(referenced && !out[parent]){
        out[parent]=KNOWN_NESTED[parent].map(c=>({path:c,label:c.replace(/_/g," "),enum:null}));
      }
    });
    return out;
  }
  const fbSubs=_fallbackSubs();
  // merged view: prefer the real schema subs; fall back to reconstructed ones
  const subsView=Object.assign({}, fbSubs, subs);
  // Render ONE attribute. If schema says it's a nested object (battery,
  // maximum_speed, item_dimensions, ...), expand into its real sub-field boxes;
  // each sub-field saves flat as "<field>.<path>".
  const renderAttr=(k,isMissing)=>{
    // THE BRAND IS SET IN ONE PLACE, AND THIS IS NOT IT.
    //
    //     "why do i have 2 places in the listing tab to put a brand name, i
    //      thought it should be 1"
    //
    // Correct, and the second box was worse than redundant: it was a box you
    // could type into whose value was then DISCARDED. build_api_attributes
    // takes the brand from the listing's own Brand column, checked against the
    // account's registered brands (see resolve_account_brand) -- never from an
    // attribute typed here, because every source this editor draws on belongs
    // to somebody else and one of them once supplied brand='YL'.
    //
    // So this shows where the brand actually comes from instead of pretending
    // to accept one.
    if(BRAND_KEYS.indexOf(String(k).toLowerCase()) >= 0){
      const shown = esc(String(r.brand || r.Brand || "").trim() || "not set");
      return '<tr><td class="k">' + esc(lbl(k)) + '</td><td class="v">'
        + '<div class="cc" style="font-size:11.5px;line-height:1.5">'
        + '<b>' + shown + '</b> — taken from this listing’s <b>Brand</b> '
        + 'field, not typed here. It must be one of the brands registered on '
        + 'this account; if it is not, the account’s first brand is sent '
        + 'instead and the run says so. Add a brand under '
        + '<b>Manage accounts ▸ Brands</b>.'
        + '</div></td></tr>';
    }
    const sf=subsView[k];
    // A field is "required" for star purposes if the schema lists it OR Amazon's
    // preview flagged it (conditionally required, e.g. hazmat on a battery item).
    const _schemaReq = (reqList||[]).indexOf(k)>=0;
    const isReqParent = _schemaReq || !!isMissing;
    // HONESTY: the schema's static required list is broader than what Amazon's
    // live validation actually enforces. If a clean Preview already ran for this
    // listing (status API_READY / "PREVIEW clean") and did NOT flag this field,
    // then a hard red "Required" star is misleading -- Amazon accepted it without
    // it. Show a SOFTER marker in that case so the user isn't sent chasing a
    // field Amazon didn't ask for (e.g. dangerous goods on a manual tool).
    const _cleanPrev = (String(r.status||"").toUpperCase()==="API_READY")
                       || /PREVIEW clean/i.test(String(r.notes||""));
    const _amazonFlagged = !!isMissing || !!flagged[k];
    const _schemaOnly = _schemaReq && !_amazonFlagged && _cleanPrev;
    const reqMark = _amazonFlagged
      ? '<span class="reqstar" title="Amazon flagged this in Preview — it must be filled">\u2605</span>'
      : (_schemaOnly
          ? '<span class="reqsoft" title="The schema lists this as required, but Amazon\u2019s last Preview accepted the listing WITHOUT it. Fill it only if a later Preview flags it.">\u2606 schema-listed</span>'
          : (isReqParent ? '<span class="reqstar" title="Required by Amazon">\u2605</span>' : ''));
    if(sf&&sf.length){
      // Specific parent instruction (e.g. hazmat) shown right on the group header
      // so the user sees WHAT to enter at the field, not just in the top red box.
      const headHint = isMissing ? (SPECIFIC_HINT[k] || "fill the sub-fields below") : null;
      // ALWAYS-ON guidance for multi-level (nested) fields: a parent like this is
      // usually optional, BUT the moment you put a value in it, Amazon makes its
      // sub-fields required -- leaving any blank then throws an error. This note
      // prevents the "why did filling one box create new errors?" surprise.
      const nestNote = isReqParent
        ? ""   // already required -> the star + headHint already say to fill it
        : `<span class="nesthint" title="This field is optional. But if you enter a value here, Amazon will require ALL its sub-fields below to be filled too — otherwise it errors. Leave the whole group blank if you don't need it.">\u2139 optional — but filling this makes its sub-fields required</span>`;
      const head=`<tr class="subhead${isMissing?' flaggedrow':''}"><td class="k" colspan="2"><b>${esc(lbl(k))}</b>${reqMark}${headHint?` <span class="fixhint">\u26a0 ${esc(headHint)}</span>`:''}${nestNote}</td></tr>`;
      const rows=sf.map(s=>{
        const full=k+"."+s.path;                 // flat dot-key in Attributes JSON
        const val=(full in a)?a[full]:"";
        const sHasEnum=!!(s.enum&&s.enum.length);
        // Per-sub-field guidance for the known compliance fields.
        const subKey=(k+"."+s.path).toLowerCase();
        let sHint = isMissing ? (sHasEnum?"choose an allowed value":"type the value Amazon expects") : null;
        if(isMissing && SUBFIELD_HINT[subKey]) sHint = SUBFIELD_HINT[subKey];
        return edRow(titles[full]||s.label, editCell(sku,"attr",full,val,(sHasEnum?s.enum:null)), sHint, _prov&&_prov[full], true);
      }).join("");
      return head+rows;
    }
    const isReq = ((reqList||[]).indexOf(k)>=0) || !!isMissing;
    // same honesty rule as the nested head: a schema-required field that a clean
    // Preview didn't flag shows a soft marker, not a hard "required" star.
    const _flatAmazonFlagged = !!isMissing || !!flagged[k];
    const _flatSchemaOnly = ((reqList||[]).indexOf(k)>=0) && !_flatAmazonFlagged && _cleanPrev;
    // Accurate hint: if Amazon gives an allowed-value list -> dropdown ("choose
    // a value"); if not -> free text, so tell the user to type what Amazon wants
    // rather than showing the misleading "choose an allowed value".
    const hasEnum = !!(enums[k] && enums[k].length);
    const baseHint = flagged[k] || "";
    const missHint = hasEnum
      ? (baseHint || "choose an allowed value")
      : (/required/i.test(baseHint) ? "required — type the value Amazon expects"
                                    : "type the value Amazon expects (free text)");
    return isMissing
      ? edRowReq(lbl(k), editCell(sku,"attr",k,"",enums[k]||null), missHint)
      : edRow(lbl(k), editCell(sku,"attr",k,a[k],enums[k]||null), flagged[k], _prov&&_prov[k], false, isReq, _flatSchemaOnly, {sku:sku, target:"attr", key:k, locked:isReq});
  };
  // skip flat dot-keys that belong to a nested group (rendered under their head)
  const isSubKey=k=>k.includes(".")&&subsView[k.split(".")[0]];
  // parents whose sub-values are already filled (so head + sub-rows still show)
  const filledParents=[...new Set(aKeys.filter(isSubKey).map(k=>k.split(".")[0]))]
      .filter(p=>!aKeys.includes(p)&&!missing.includes(p));
  const presentTop=aKeys.filter(k=>!_AHIDE.has(k)&&!isSubKey(k));
  const attrRows=presentTop.map(k=>renderAttr(k,false)).join("")
    + filledParents.map(k=>renderAttr(k,false)).join("")
    + missing.map(k=>renderAttr(k,true)).join("");
  // every other schema field the user MAY fill (optional) -> add-on demand picker
  const addable=allAttrs.filter(k=>!(k in a) && !missing.includes(k) && !EXCLUDE_REQ.has(k) && !k.endsWith("_image_locator")).sort();
  const sidv=sid(sku);
  const addCtrl = addable.length ? `<div class="addfield">
      <select onchange="addField('${esc(sku)}','${esc(r.product_type)}',this)">
        <option value="">+ add another field (${addable.length} optional available)…</option>
        ${addable.map(k=>`<option value="${esc(k)}">${esc(lbl(k))}</option>`).join("")}
      </select>
      <table class="kv" id="added_${sidv}"></table>
      <div class="hint">Pick any field to add and fill — saves automatically.</div>
    </div>` : "";
  // ---- CONTENT FIELDS with 2026 limits + indexing depth indicators ----------
  // Title: 200 system max, but a 75-char HARD CAP lands Jul 27 2026 (all cats
  //        except media). Mobile truncates ~70. Fully indexed, highest weight.
  // Bullets: 500 each, but only the first ~1,000 BYTES across all 5 COMBINED are
  //          indexed -> a shared byte meter sits above the bullets.
  // Description: 2,000 incl HTML, indexed but LOWEST weight of visible fields.
  // Item Highlights: 125, new structured field, own A10 weight.
  // Backend search terms: 249 BYTES (not chars); one byte over de-indexes ALL.
  const titleOpts={ warnAt:75, warnMsg:"Amazon's 75-char hard cap applies from 27 Jul 2026 (all categories except media). Front-load the first ~70 chars — mobile truncates there.", indexNote:"fully indexed · highest weight", indexTip:"Title carries the most A10 search weight. Mobile shows ~70-80 chars, so put the most important words first." };
  const bulletOptsFor=(i)=>({ bucket:"bullet"+i, indexNote:(i===1?"first 1,000 bytes (all 5 combined) indexed":""), indexTip:"Amazon indexes only the first ~1,000 bytes across ALL five bullets combined — not per bullet. See the meter above." });
  const descOpts={ indexNote:"indexed · lowest weight", indexTip:"The description is indexed but weighted lowest of the visible fields. Won't save past 2,000 chars (HTML included)." };
  const highlightOpts={ target:"attr", indexNote:"indexed · own weight", indexTip:"Item Highlights is a structured field shown with the title in search and on the PDP. Carries its own A10 weight (2026)." };
  const backendOpts={ bytes:true, warnAt:249, warnMsg:"Backend search terms are measured in BYTES. One byte over 249 silently de-indexes the ENTIRE field — keep it at or under 249.", indexNote:"249-byte cap · de-index risk", indexTip:"Counted in bytes, not characters. Going one byte over 249 removes the whole field from search." };
  const bulletMeterRow = `<tr><td colspan="2" class="wcell"><div id="bulletIdxMeter" class="bulletmeter"></div></td></tr>`;
  const itemHi = (r.attributes||{}).item_type_keyword===undefined ? "" : "";
  const _highlightVal = (function(){ try{ return (r.attributes||{}).item_highlights || r.item_highlights || ""; }catch(e){ return ""; } })();
  // ✕ delete control for a content field (blanks the cell; bullets get their own controls)
  const cDel=(target,key)=>`<button class="cdel" title="Delete this field" onclick="clearField('${esc(sku)}','${target}','${esc(key)}')">✕</button>`;
  const cRows=[
      contentRow("Backend search terms", sku, "Search Terms / KW", r.search_terms, 249, Object.assign({}, backendOpts, {controls:cDel("col","Search Terms / KW")})),
      contentRow("Title", sku, "Title", r.title, 200, titleOpts),
      contentRow("Item Highlights", sku, "item_highlights", _highlightVal, 125, Object.assign({}, highlightOpts, {controls:cDel("attr","item_highlights")}))
    ]
    .concat([bulletMeterRow])
    .concat((function(){
        var bl=(r.bullets||[]); var total=bl.length;
        var rows=bl.map(function(b,i){
          return contentRow("Bullet "+(i+1), sku, "Bullet "+(i+1), b, 500,
                            Object.assign({}, bulletOptsFor(i+1), {controls: bulletControls(sku,i,total)}));
        });
        if(total<MAX_BULLETS){
          rows.push('<tr><td colspan="2" class="wcell"><button class="addbulletbtn" onclick="addBullet(\''+esc(sku)+'\')">+ Add bullet ('+total+'/5)</button></td></tr>');
        }
        return rows;
      })())
    .concat([contentRow("Description", sku, "Description (HTML)", r.description, 2000, descOpts)]).join("");
  const rid="raw_"+Math.random().toString(36).slice(2,8);
  const nEnum=Object.keys(enums).length;
  const hasAttrs=aKeys.length||missing.length;
  const nFix=missing.length + Object.keys(flagged).filter(k=>k in a).length;
  const attrHdr=nFix?` — ${nFix} field(s) flagged by Amazon — fix the highlighted ones`:(hasAttrs?'':' — none yet');
  const st=(r.status||"").toUpperCase();
  const reqNote = missing.length
    ? `<div class="reqnote">Amazon reveals required fields in <b>stages</b> — fill the highlighted box(es) above, then click <b>Preview (API)</b> again. More required fields may appear after each Preview; repeat until Preview reports no errors.</div>`
    : (["API_READY","API_ERROR","LIVE"].includes(st) ? ""
        : `<div class="reqnote">Required fields are revealed by Amazon's validation, not upfront. Click <b>Preview (API)</b> to check this row — any required fields will appear here as highlighted boxes.</div>`);
  const rememberBtn = (aKeys.length||missing.length)
    ? `<button class="rememberbtn" onclick="saveDefault('${esc(sku)}','${esc(r.product_type)}',this)">★ Remember these as defaults for all ${esc(r.product_type||"this type")} listings</button>`
    : "";
  const isBrandRow = !r.asin || (r.sku && /^[A-Za-z]/.test(String(r.sku)) && !/_\d+Days_/.test(String(r.sku)));
  const imgLabel = isBrandRow ? "Images — from brand catalogue" : "Images — from competitor (eBay priority)";
  const _mainIsLocal = imgUrls.length && !/^https?:\/\//i.test(String(imgUrls[0]||""));
  const _imgWarn = _mainIsLocal
    ? `<div class="hint" style="color:var(--warn);margin-top:4px">⚠ The main image is a LOCAL file Amazon can't fetch — it will block submission. Remove it (submit without an image) or set a public https URL.</div>`
    : "";
  const _imgActions = imgUrls.length
    ? `<div style="margin-top:6px;display:flex;gap:8px">
         <button class="suggestbtn" style="background:#2a1414;border-color:var(--red-line);color:var(--red)" onclick="clearMainImage('${esc(sku)}')" title="Remove the main image URL so the listing can be created without an image (add one later in Seller Central)"><i class="ti ti-photo-off"></i> Remove main image</button>
       </div>`
    : "";
  const imgBlock = (imgUrls.length
    ? `<div class="kvsec">${imgLabel}</div><div class="imgrow">${imgUrls.map((u,i)=>`<div class="thumbwrap"><a href="${esc(u)}" target="_blank" title="${i===0?'MAIN image':'additional #'+i}"><img class="thumb" src="${esc(u)}" loading="lazy"><span class="thumbcap">${i===0?'main':'#'+i}</span></a><button class="thumbedit" title="Edit this image (AI changes only what you ask)" onclick="editListingImage('${esc(sku)}','${esc(u)}',${i})"><i class="ti ti-wand"></i></button></div>`).join("")}</div>${_imgWarn}${_imgActions}`
    : `<div class="kvsec">Images</div><div class="hint">No image captured for this row.</div>`)
    + `<div class="genimg" id="genimg_${sidv}">
        <div class="kvsec" style="color:var(--ai);margin-top:12px"><i class="ti ti-sparkles"></i> AI image generation</div>
        <div class="genpanel" id="genpanel_${sidv}" style="display:block">
          <div class="gendiag" id="gendiag_${sidv}">Checking OpenRouter connection…</div>
          <div class="genrow">
            <span class="cc">Reference image:</span>
            <input class="ed geninput" id="genraw_${sidv}" style="flex:1"
                   value="${esc(imgUrls[0]||'')}"
                   placeholder="${isBrandRow?'brand/product image URL':'eBay source image (auto)'}">
            <label class="uploadbtn" title="Upload a reference image from your computer">
              <i class="ti ti-upload"></i> Upload
              <input type="file" accept="image/*" style="display:none" onchange="uploadRef(this,'${esc(sku)}','${sidv}')">
            </label>
          </div>
          ${isBrandRow?`<label class="cc"><input type="checkbox" id="genusebrand_${sidv}"> use brand-saved reference image instead</label>`:''}
          <textarea class="ed geninput" id="genbrief_${sidv}" rows="2"
            placeholder="Your command: how should the image look? e.g. 'premium studio shot, soft shadow, blue mirror lens variant'"></textarea>
          <div class="genrow">
            <span class="cc">Prompt AI:</span>
            <select class="ed" id="gentai_${sidv}" style="width:auto"></select>
            <span class="cc">Image AI:</span>
            <select class="ed" id="geniai_${sidv}" style="width:auto"></select>
            <a class="browsemodels sm" href="https://openrouter.ai/models?output_modalities=image" target="_blank" rel="noopener" title="See all image models on OpenRouter"><i class="ti ti-external-link"></i> all image models</a>
          </div>
          <div class="genrow">
            <button class="genimgbtn" id="genbtn_${sidv}" onclick="doGen('${esc(sku)}','${sidv}')">Generate</button>
            <span class="cc" id="genstatus_${sidv}"></span>
          </div>
          <details id="genpromptwrap_${sidv}" style="display:none"><summary class="cc">view detailed prompt the AI wrote</summary><pre class="genprompt" id="genprompt_${sidv}"></pre></details>
          <div id="genresult_${sidv}"></div>
        </div>
      </div>`
      + ((window.WS_FEATURES&&window.WS_FEATURES.indexOf('harvest')>=0)
         ? milesTemplatePanel(sku, sidv) : "");
  // COMPLETE submission view: every attribute key, no exclusions, read-only,
  // so the user sees everything that will be sent to Amazon (browse nodes,
  // dimensions, compliance flags, image locators, prices -- the lot).
  const allSubKeys=Object.keys(a).filter(k=>k!=="_provenance"&&k!=="provenance").sort();
  const fmtVal=v=>{ if(v==null) return ""; if(typeof v==="object") return esc(JSON.stringify(v)); return esc(String(v)); };
  const fullSubRows=allSubKeys.map(k=>`<tr><td class="k">${esc(k.replace(/_/g," "))}</td><td class="v"><span class="ro">${fmtVal(a[k])}</span></td></tr>`).join("");
  const fullSubBlock=allSubKeys.length
    ? `<details class="suball"><summary class="kvsec" style="cursor:pointer">Complete submission data — everything sent to Amazon (${allSubKeys.length} fields, read-only)</summary>
        <table class="kv">${fullSubRows}</table></details>`
    : "";
  // Amazon messages that don't name a real schema attribute (catalogue-conflict prose,
  // "The Listing data...", "Your offer...") -> shown as plain text, NEVER as input fields.
  const plainNoteBlock=(_plainNotes&&_plainNotes.length)
    ? `<div class="amzprose" style="margin:6px 0;padding:8px 10px;border:1px solid var(--bd,#555);border-radius:6px">
         <b>Amazon message</b> <span class="cc">(not an editable field — no attribute to fix here)</span><br>
         ${_plainNotes.map(esc).join("<br>")}</div>`
    : "";
  return `<details open><summary>Full listing data — click any value to edit; saves automatically${nEnum?'. Dropdowns = Amazon allowed values':''}</summary>
    ${imgBlock}
    <div class="kvsec">Identity &amp; offer</div><table class="kv">${idRows}</table>
    <div class="kvsec">Attributes${attrHdr}</div>${schemaDiag(r.product_type, nEnum, allAttrs.length, Object.keys(subs).length, missing, flagged, a)}${(typeof howWorks==="function")?howWorks('required_fields'):""}${hasAttrs?`<table class="kv">${attrRows}</table>`:''}${plainNoteBlock}${reqNote}${addCtrl}${rememberBtn}
    <div class="kvsec">Content</div>${(typeof howWorks==="function")?howWorks('content_index'):""}<table class="kv">${cRows}</table>
    ${fullSubBlock}
    <span class="rawtoggle" onclick="var e=document.getElementById('${rid}');e.style.display=(e.style.display==='block'?'none':'block')">show / hide raw JSON</span>
    <pre class="raw" id="${rid}">${esc(JSON.stringify(a,null,2))}</pre>
    ${ (window.SHOW_PAYLOAD_VIEWER===true && r.api_payload && String(r.api_payload).trim())
       ? `<details class="payloadbox"><summary class="kvsec" style="cursor:pointer">\ud83d\udce6 Exact payload sent to Amazon (literal API body from last Preview/Submit, read-only)</summary>
            <div class="payloadnote">This is the verbatim JSON the app sent to Amazon on the last Preview or Submit for this SKU — every word, exactly as transmitted. It does not affect anything; it is for visibility only. You can hide this section in Settings.</div>
            <pre class="raw payloadraw" id="pl_${sidv}">${esc(String(r.api_payload))}</pre>
            <button class="linkbtn" onclick="navigator.clipboard&&navigator.clipboard.writeText(document.getElementById('pl_${sidv}').textContent);toast&&toast('Payload copied')">Copy payload</button>
          </details>`
       : "" }
  </details>`;
}
var AISET=null;
async function loadAISettings(){
  if(AISET) return AISET;
  try{ AISET=await (await fetch('/ai/settings')).json(); }catch(e){ AISET={ok:false}; }
  if(AISET&&AISET.admin){ window.LOGIC_VISIBLE = !!AISET.admin.show_logic && !AISET.admin.preview_as_user; }
  return AISET;
}
function fillModelSelect(sel, models, chosen){
  if(!sel) return;
  sel.innerHTML=(models||[]).map(function(m){
    return '<option value="'+esc(m.id)+'"'+(m.id===chosen?' selected':'')+'>'+esc(m.name||m.id)+'</option>';
  }).join('');
}
async function toggleGen(sidv){
  var p=document.getElementById('genpanel_'+sidv);
  if(p) p.style.display = (p.style.display==='none'?'block':'none');
  var s=await loadAISettings();
  if(!s || !s.ok || !(s.image_models && s.image_models.length)){
    try{ AISET=null; s=await (await fetch('/ai/settings?refresh=1')).json(); AISET=s; }catch(e){}
  }
  if(s&&s.ok){
    fillModelSelect(document.getElementById('gentai_'+sidv), s.text_models, s.select.prompt_enhance);
    fillModelSelect(document.getElementById('geniai_'+sidv), s.image_models, s.select.image_generate);
  }
  // quick connectivity check so the user knows BEFORE generating whether the key works
  var diag=document.getElementById('gendiag_'+sidv);
  if(diag && p && p.style.display!=='none'){
    await _orTestInto(diag);
  }
}
async function doGen(sku, sidv){
  var r=ROWS.find(x=>String(x.sku)===String(sku));
  var title=r?(r.title||''):'';
  var ref=(document.getElementById('genraw_'+sidv)||{}).value||'';
  var brief=(document.getElementById('genbrief_'+sidv)||{}).value||'';
  var tprov=(document.getElementById('gentai_'+sidv)||{}).value||'';
  var iprov=(document.getElementById('geniai_'+sidv)||{}).value||'';
  var useBrand=document.getElementById('genusebrand_'+sidv);
  if(useBrand&&useBrand.checked){ ref='__BRAND_REF__'; }
  var st=document.getElementById('genstatus_'+sidv);
  var btn=document.getElementById('genbtn_'+sidv);
  if(btn){ btn.disabled=true; btn.textContent='Generating…'; }
  if(st){ st.innerHTML='<span class="genspin"></span> Stage 1: writing prompt… then creating image. This can take 30\u201390s \u2014 please wait.'; }
  // elapsed-time ticker so the user sees it IS working
  var t0=Date.now();
  var ticker=setInterval(function(){
    if(st){ var s=Math.round((Date.now()-t0)/1000); var base=st.getAttribute('data-base')||'Working'; st.innerHTML='<span class="genspin"></span> '+base+' \u2014 '+s+'s elapsed'; }
  }, 1000);
  if(st) st.setAttribute('data-base','Generating image');
  try{
    var res=await fetch('/genimage',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({brief:brief,reference_image:ref,title:title,text_provider:tprov,image_provider:iprov})});
    var j=await res.json();
    clearInterval(ticker);
    if(btn){ btn.disabled=false; btn.textContent='Generate'; }
    if(!j.ok){
      if(st) st.innerHTML='<span style="color:var(--red)">\u2717 Failed ('+(j.stage||'')+'): '+esc(j.error||'unknown')+'</span>';
      if(j.detailed_prompt){ var pw=document.getElementById('genpromptwrap_'+sidv); var pp=document.getElementById('genprompt_'+sidv); if(pw&&pp){pw.style.display='block'; pp.textContent=j.detailed_prompt;} }
      return;
    }
    if(st) st.innerHTML='<span style="color:var(--ok)">\u2713 Done ('+esc(j.text_provider||'')+' \u2192 '+esc(j.image_provider||'')+') \u2014 review below.</span>';
    var pw=document.getElementById('genpromptwrap_'+sidv); var pp=document.getElementById('genprompt_'+sidv);
    if(pw&&pp){ pw.style.display='block'; pp.textContent=j.detailed_prompt||''; }
    var out=document.getElementById('genresult_'+sidv);
    if(out){
      var _dimtxt=(j.width&&j.height)?(j.width+'×'+j.height+' px'):'';
      var _sztxt=(j.bytes)?_fmtBytes(j.bytes):'';
      var _meta=(_dimtxt||_sztxt)?('<div class="cc" style="margin:4px 0">'+esc([_dimtxt,_sztxt].filter(Boolean).join(' · '))+'</div>'):'';
      out.innerHTML='<div class="genpreview"><img src="'+j.data_url+'">'+_meta+
        '<div class="cc" id="gendrive_'+sidv+'" style="margin:2px 0;color:var(--ok)"></div>'+
        '<div class="genrow">'+
        '<button class="genimgbtn apply" onclick="applyGen(\''+esc(sku)+'\',\''+sidv+'\')">Use as main image</button>'+
        '<button class="genimgbtn" onclick="document.getElementById(\'genresult_'+sidv+'\').innerHTML=\'\'">Discard</button></div></div>';
      out.dataset.img=j.data_url;
    }
    // auto-save the generation into this SKU's media folder (builds the library)
    // AND auto-push to Drive (server does this for kind=generated), then show the link.
    try{
      var sv=await fetch('/media/upload',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({sku:sku,data:j.data_url,kind:'generated'})});
      var svj=await sv.json();
      if(svj.ok && out){
        out.dataset.savedurl=svj.url;
        var dr=document.getElementById('gendrive_'+sidv);
        if(dr){
          if(svj.drive_direct_url){
            dr.innerHTML='\u2713 Saved to Drive \u2014 <a href="'+esc(svj.drive_view_url||svj.drive_direct_url)+'" target="_blank">open</a> '+
              '<span class="cc" style="color:var(--ink3)">(Amazon-ready link saved)</span>';
            out.dataset.driveurl=svj.drive_direct_url;
          } else {
            var _de = svj.drive_error ? (' Reason: '+esc(svj.drive_error)) : '';
            dr.innerHTML='<span class="cc" style="color:var(--warn)">Saved locally, but NOT uploaded to Drive.'+_de+'</span>';
          }
        }
      }
    }catch(e){}
  }catch(e){
    clearInterval(ticker);
    if(btn){ btn.disabled=false; btn.textContent='Generate'; }
    if(st) st.innerHTML='<span style="color:var(--red)">\u2717 Error: '+esc(String(e))+'</span>';
  }
}
function uploadMainImage(sku, inp){
  // Upload a LOCAL image as this listing's main image. Chains two existing routes:
  //  1) /media/upload (kind:'main') -> saves + auto-pushes to Drive, returns a
  //     PUBLIC drive_direct_url Amazon can fetch.
  //  2) /edit -> writes that public URL onto the row's main_product_image_locator,
  //     so the next Preview/Submit sends YOUR clean image instead of the source one.
  const f = inp && inp.files && inp.files[0];
  if(!f){ return; }
  if(!/^image\//.test(f.type||"")){ toast("Please choose an image file"); inp.value=""; return; }
  const rd = new FileReader();
  rd.onload = async () => {
    toast("Uploading main image…");
    try{
      const up = await (await fetch("/media/upload",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:sku, data:rd.result, name:f.name, kind:"main"})})).json();
      if(!up || !up.ok){ toast("Upload failed: "+((up&&up.error)||"unknown")); return; }
      const pub = up.drive_direct_url || "";
      if(!pub){ toast("Uploaded, but no public URL"+(up.drive_error?(" ("+up.drive_error+")"):"")+". Set the account's Drive folder so Amazon can fetch it."); return; }
      // ONE implementation of "make this the main image" (listingimages.js).
      await setMainImage(sku, pub,
        {message:"Main image set ✓ — Preview/Submit to send it to Amazon"});
    }catch(e){ toast("Upload error: "+((e&&e.message)||e)); }
    finally { if(inp) inp.value=""; }
  };
  rd.readAsDataURL(f);
}
async function pushImageLive(sku, btn){
  var r=(ROWS||[]).find(x=>String(x.sku)===String(sku));
  if(!r){ toast('Listing not found'); return; }
  if(!confirm("Send the current main image to the LIVE Amazon listing for "+sku+"?\n\nThis updates ONLY the main image on Amazon (no full resubmit). Amazon must be able to fetch the image, so it will be uploaded to your Drive and made public if it isn't already.")) return;
  var old = btn?btn.textContent:'';
  if(btn){ btn.disabled=true; btn.textContent='Pushing…'; }
  try{
    var res=await fetch('/listing/push_image',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({confirmed:true, sku:sku,
        marketplace:(typeof WS_MARKET!=='undefined'?WS_MARKET:''),
        product_type:(r.product_type||''),
        id:(CUR_ACCOUNT&&CUR_ACCOUNT.id)||''})});
    var j=await res.json();
    if(j.ok){
      toast('✓ Image sent to Amazon ('+(j.status||'accepted')+'). Amazon takes a few minutes to show it.');
    } else {
      var extra = (j.issues&&j.issues.length)?(' — '+j.issues.map(function(i){return (i.message||i.code||'');}).join('; ')):'';
      toast('Could not push image: '+(j.error||'unknown')+extra);
    }
  }catch(e){ toast('Push failed: '+e); }
  finally{ if(btn){ btn.disabled=false; btn.textContent=old||'Push image to live'; } }
}
async function applyGen(sku, sidv){
  var out=document.getElementById('genresult_'+sidv);
  var dataUrl=out?out.dataset.img:'';
  if(!dataUrl){ toast('No generated image to apply'); return; }
  // prefer the saved file URL (real hosted path) over the inline data URL
  var savedUrl=out?out.dataset.savedurl:'';
  var useUrl=savedUrl||dataUrl;
  // ONE implementation of "make this the main image" (listingimages.js).
  await setMainImage(sku, useUrl,
    {message: savedUrl ? 'Set as main image (saved to media)' : 'Set as main image'});
}
