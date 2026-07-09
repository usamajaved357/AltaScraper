// ---- AI sourced suggestions for missing fields ----
function _srcBadge(src){
  var map={
    'eBay':['#10301f','#74e0a3','eBay source'],
    'Amazon competitor (SP-API)':['#15233a','#9cc1ff','Amazon competitor'],
    'AI knowledge':['#2a2440','#c8b6ff','AI knowledge'],
    'AI inference':['#2e2510','#e3b768','AI inference'],
    'none':['#2e1414','#ef9a9a','no source']
  };
  var m=map[src]||map['AI inference'];
  return '<span class="srcbadge" style="background:'+m[0]+';color:'+m[1]+'">'+m[2]+'</span>';
}
function _confBadge(c){
  if(!c) return '';
  var col=c==='high'?'#7fd99a':(c==='medium'?'#e3b768':'#9aa3b2');
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
        box.innerHTML='<div class="gendiag" style="color:#e3b768">\u2605 '+_emptyReq.length+' required field'+(_emptyReq.length>1?'s':'')+' still need a value (marked with \u2605 below): <b>'+_emptyReq.map(function(x){return esc(x.replace(/_/g," "));}).join(", ")+'</b>.<br><span class="cc">Amazon hasn\u2019t flagged these yet \u2014 fill them now, or click Preview API to confirm exactly what\u2019s required.</span></div>';
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
          '<span class="srcbadge" style="background:#13371f;border-color:#1f7a3a;color:#7fdca0">auto-filled on Preview</span></div>'+
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

async function autoFixLoop(sku){
  if(!sku) return;
  if(window.AUTOFIX_STATE && window.AUTOFIX_STATE.sku === sku){
    toast('Auto-fix already running for this SKU'); return;
  }
  const MAX_ROUNDS = 8;
  const state = {sku:sku, round:0, prevErrors:null, stopped:false, cancelled:false,
                  trace: [], startedAt: new Date().toISOString()};
  window.AUTOFIX_STATE = state;
  window._AUTOFIX_LAST_STATE = state;   // set NOW so bulkAutoFix can read it back regardless of which panel path we take

  // If we're inside a bulk batch, DON'T create our own panel -- the batch panel
  // is already on screen and using the same DOM slot ('autofix_panel'). We
  // still capture the full trace in `state` so the batch panel can render it,
  // but skip the per-SKU floating box to avoid destroying the batch UI.
  const insideBulk = !!(window.BULK_AUTOFIX && !window.BULK_AUTOFIX.done);
  const panel = insideBulk ? _autoFixNullPanel() : _autoFixPanel(sku, state);
  if(!insideBulk){
    panel.show('Auto-fix started for '+sku);
  }

  try{
    while(state.round < MAX_ROUNDS && !state.cancelled){
      state.round++;
      const roundEntry = {
        round: state.round,
        started_at: new Date().toISOString(),
        suggestions: [],
        applied: [],
        skipped: [],
        preview_verdict: null,
        preview_error_fields: [],
        preview_raw_lines: [],
        diagnosis: '',
      };
      state.trace.push(roundEntry);
      panel.step('Round '+state.round+' of '+MAX_ROUNDS+' — asking AI for suggestions…');

      // --- 1. Get suggestions from AI ---
      let sugRes;
      try{
        sugRes = await fetch('/suggest',{method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({sku:sku})});
        sugRes = await sugRes.json();
      }catch(e){
        roundEntry.diagnosis = '/suggest network error: '+String(e);
        panel.fail('Round '+state.round+': /suggest failed — see trace');
        panel.renderTrace();
        break;
      }
      if(!sugRes.ok){
        // If the error mentions "sku not found" it means the row isn't in the
        // current worksheet -- usually because the user switched account
        // workspaces (or the app was restarted) after ticking this SKU.
        // Explain that plainly so the trace tells the user what to fix.
        const errRaw = String(sugRes.error || 'no error field');
        const isMissing = /sku not found|not in.*view|not in.*sheet/i.test(errRaw);
        roundEntry.diagnosis = isMissing
          ? ('SKU not visible in current workspace. This usually means you switched '+
              'account workspaces (or the app restarted) after ticking this SKU. '+
              'Click into the correct account workspace first, then try again. '+
              '(Raw: '+errRaw+')')
          : ('/suggest returned ok=false: '+errRaw);
        panel.fail('Round '+state.round+': '+(isMissing ? 'SKU not in current workspace' : 'suggestion API error')+' — see trace');
        panel.renderTrace();
        break;
      }
      // Capture EVERY suggestion (both code_owned info cards and AI-fillable ones)
      // so the trace shows exactly what the system chose per field.
      roundEntry.suggestions = (sugRes.suggestions||[]).map(function(s){
        return {
          field: s.field, value: s.value || '', source: s.source || '',
          confidence: s.confidence || '', note: s.note || '',
          code_owned: !!s._code_owned,
        };
      });
      const suggestions = (sugRes.suggestions||[]).filter(function(s){ return !s._code_owned; });
      panel.step('Round '+state.round+': got '+suggestions.length+' AI suggestions ('+
                 (roundEntry.suggestions.length-suggestions.length)+' code-owned)');

      // --- 2. Apply each suggestion ---
      for(let i=0;i<suggestions.length;i++){
        const s = suggestions[i];
        if(!s.value){
          roundEntry.skipped.push({field:s.field, reason:'empty AI value'});
          continue;
        }
        try{
          const editRes = await fetch('/edit',{method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({sku:sku, target:'attr', key:s.field, value:s.value})});
          const editJson = await editRes.json();
          if(editJson.ok){
            roundEntry.applied.push({field:s.field, value:s.value, source:s.source});
          } else {
            const err = String(editJson.error || 'unknown');
            roundEntry.skipped.push({field:s.field, reason:'edit failed: '+err});
            // If the sheet says the SKU doesn't exist, all further edits in this
            // round WILL fail identically -- abort the loop immediately with a
            // clear diagnosis instead of grinding through every suggestion.
            if(/sku not found|not in.*sheet|not in.*view/i.test(err)){
              roundEntry.diagnosis = 'SKU not visible in current workspace at edit time. '+
                                      'The row was found by /suggest but had disappeared by /edit -- '+
                                      'this usually means you switched workspaces mid-run or a '+
                                      'concurrent submit moved the row. Click into the correct '+
                                      'account workspace and retry.';
              panel.fail('Round '+state.round+': SKU disappeared from workspace between /suggest and /edit — see trace');
              panel.renderTrace();
              // Break out of BOTH the inner apply loop and the outer round loop
              window._AUTOFIX_STOP = true;
              break;
            }
          }
        }catch(e){
          roundEntry.skipped.push({field:s.field, reason:'edit exception: '+String(e)});
        }
      }
      if(window._AUTOFIX_STOP){ window._AUTOFIX_STOP = false; break; }
      panel.step('Round '+state.round+': applied '+roundEntry.applied.length+
                 ' / skipped '+roundEntry.skipped.length);

      // Count code-owned suggestions: these DON'T get "applied" (nothing to
      // apply -- the generator fills them itself when Preview runs), but they
      // ARE progress. If the current round applied 0 AI values but flagged
      // code-owned fields exist, running Preview WILL fill them via the
      // generator's compliance block. So don't stop when the only work left
      // is code-owned -- Preview is what actually resolves those.
      const codeOwnedCount = roundEntry.suggestions.filter(function(s){ return s.code_owned; }).length;
      if(roundEntry.applied.length === 0 && codeOwnedCount === 0 && state.round > 1){
        roundEntry.diagnosis = 'Nothing new to apply after round 1 and no code-owned fields to fill. AI has no more suggestions.';
        panel.stop('Round '+state.round+': nothing new to apply. Stopping.');
        panel.renderTrace();
        break;
      }

      // --- 3. Run Preview and capture EVERY line ---
      panel.step('Round '+state.round+': running Preview…');
      const verdict = await _autoFixPreview(sku, panel, roundEntry);
      roundEntry.preview_verdict = verdict.kind;
      roundEntry.preview_error_fields = verdict.errorFields || [];
      roundEntry.preview_verdict_raw = verdict.raw || '';

      if(state.cancelled){ break; }

      // --- 4. Interpret verdict ---
      if(verdict.kind === 'ok_preview'){
        roundEntry.diagnosis = 'Amazon accepted the Preview. Ready to Submit.';
        panel.done('✓ Round '+state.round+': Amazon accepted Preview. Ready to Submit!');
        panel.renderTrace();
        loadRows();
        break;
      }

      if(verdict.kind === 'network' || verdict.kind === 'nocreds' ||
          verdict.kind === 'busy' || verdict.kind === 'timeout'){
        roundEntry.diagnosis = 'Environment issue ('+verdict.kind+') — not a listing problem.';
        panel.fail('Round '+state.round+': '+verdict.kind+' — see trace');
        panel.renderTrace();
        break;
      }

      if(verdict.kind === 'error'){
        const errKey = (verdict.errorFields||[]).slice().sort().join('|');
        roundEntry.diagnosis = 'Amazon flagged '+verdict.n+' error(s) on fields: '+
                                (verdict.errorFields||[]).join(', ');
        panel.step('Round '+state.round+': Amazon flagged '+verdict.n+' error(s) on: '+
                   (verdict.errorFields||[]).join(', '));
        if(state.prevErrors && state.prevErrors === errKey){
          roundEntry.diagnosis += ' — IDENTICAL to previous round, no progress.';
          panel.stop('Round '+state.round+': Same errors as last round. Auto-fix cannot resolve these. Stopped.');
          panel.renderTrace();
          break;
        }
        state.prevErrors = errKey;
        panel.renderTrace();   // incremental render so user sees progress
        continue;
      }

      roundEntry.diagnosis = 'Unclear outcome ('+verdict.kind+'). Stopped for safety.';
      panel.fail('Round '+state.round+': unclear outcome — see trace');
      panel.renderTrace();
      break;
    }
    if(state.round >= MAX_ROUNDS && !state.cancelled){
      panel.stop('Hit max rounds ('+MAX_ROUNDS+'). Stopped. Review trace to see the loop pattern.');
      panel.renderTrace();
    }
  } finally {
    window.AUTOFIX_STATE = null;
    // Skip the per-SKU sheet refresh when running inside a batch -- the batch
    // wrapper calls loadRows() once at the very end. Doing it per SKU would
    // hit /rows 20+ times in a bulk run.
    if(!(window.BULK_AUTOFIX && !window.BULK_AUTOFIX.done)){
      loadRows();
      // persist the trace so a page refresh can't lose it (single runs only; a batch saves once)
      try{ _autoFixSaveLog('single', _autoFixTraceText(state), state.sku); }catch(e){}
    }
  }
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
    lines.push('PREVIEW VERDICT: '+r.preview_verdict);
    if(r.preview_error_fields && r.preview_error_fields.length){
      lines.push('Amazon flagged ('+r.preview_error_fields.length+'): '+
                  r.preview_error_fields.join(', '));
    }
    lines.push('');
    lines.push('PREVIEW STREAM (full Amazon response, verbatim):');
    // Include EVERY raw line, not a filtered subset. Filtering was hiding
    // parser mismatches (e.g. verdict `unknown` with an empty filtered view
    // when the stream actually did contain success/error lines the parser
    // failed to recognise). The full stream lets us see what Amazon sent
    // vs what our parser did with it, without which "unknown outcome"
    // diagnoses are un-debuggable.
    const raw_all = r.preview_raw_lines || [];
    if(raw_all.length){
      raw_all.forEach(function(x){ lines.push('  | '+x); });
    } else {
      lines.push('  (no stream lines received)');
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
  let el = document.getElementById('autofix_panel');
  if(el){ el.remove(); }
  el = document.createElement('div');
  el.id = 'autofix_panel';
  el.style.cssText = 'position:fixed;bottom:20px;right:20px;width:560px;max-height:80vh;'+
    'background:#141b2b;border:1px solid #3b4d70;border-radius:10px;padding:12px;'+
    'box-shadow:0 8px 24px rgba(0,0,0,0.5);z-index:9999;font-size:12px;color:#e8eaed;'+
    'display:flex;flex-direction:column;gap:8px';
  el.innerHTML =
    '<div style="display:flex;justify-content:space-between;align-items:center;font-weight:600">'+
      '<span>✦ Auto-fix: '+esc(sku)+'</span>'+
      '<div style="display:flex;gap:8px;align-items:center">'+
        '<button id="autofix_copy" onclick="_autoFixCopyTrace()" '+
          'style="background:#5b3fb8;color:#fff;border:none;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:11px">'+
          '📋 Copy trace</button>'+
        '<button onclick="if(window.AUTOFIX_STATE)window.AUTOFIX_STATE.cancelled=true;this.parentElement.parentElement.parentElement.remove()" '+
        'style="background:none;color:#e8eaed;border:none;cursor:pointer;font-size:16px">✕</button>'+
      '</div>'+
    '</div>'+
    '<div id="autofix_status" style="color:#9cc1ff"></div>'+
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
      if(s) s.innerHTML = '<span style="color:#74e0a3">'+esc(msg)+'</span>';
    },
    stop: function(msg){
      const s = document.getElementById('autofix_status');
      if(s) s.innerHTML = '<span style="color:#e3b768">⚠ '+esc(msg)+'</span>';
    },
    fail: function(msg){
      const s = document.getElementById('autofix_status');
      if(s) s.innerHTML = '<span style="color:#e0696b">✗ '+esc(msg)+'</span>';
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

async function bulkAutoFix(){
  const skus = selectedSkus();
  if(!skus.length){ toast("Nothing selected — tick some listings first"); return; }
  if(window.BULK_AUTOFIX && !window.BULK_AUTOFIX.done){
    toast("A batch auto-fix is already running"); return;
  }

  // PRE-FLIGHT: verify every selected SKU is actually in the current workspace.
  // The batch UI persists SELECTED across page-loads and Flask restarts, so it's
  // possible to tick SKUs on Account A, switch to Account B (or restart Flask
  // which resets active_account to default), and end up asking Amazon about
  // rows that aren't visible to the current worksheet. Without this check the
  // /suggest and /edit endpoints just 404 with cryptic 'sku not found in
  // current view' messages -- the batch trace shows those but doesn't explain
  // WHY, which wastes the user's time.
  //
  // The current view rows are already loaded into ROWS as of the last
  // loadRows() call. Cross-check locally before hitting the network.
  const inView = new Set((ROWS || []).map(r => String(r.sku || "")));
  const missing = skus.filter(s => !inView.has(String(s)));
  if(missing.length){
    const inViewCount = skus.length - missing.length;
    const msg = "⚠ "+missing.length+" of "+skus.length+" selected SKU(s) are NOT in the current workspace view:\n\n" +
                 missing.slice(0, 10).join("\n") +
                 (missing.length > 10 ? "\n  ...and "+(missing.length-10)+" more" : "") +
                 "\n\nThis usually means you switched account workspaces (or the app restarted) after ticking them. " +
                 "The auto-fix loop can't Suggest/Apply/Preview rows it can't see.\n\n" +
                 (inViewCount > 0
                   ? "Continue anyway with the "+inViewCount+" SKU(s) still in view?"
                   : "None of the selected SKUs are in this view. Please click into the correct account workspace first and re-tick.");
    if(inViewCount === 0){ alert(msg); return; }
    if(!confirm(msg)) return;
    // Filter to just the SKUs actually visible
    for(let i = skus.length - 1; i >= 0; i--){
      if(!inView.has(String(skus[i]))) skus.splice(i, 1);
    }
  }

  if(!confirm("Run Auto-fix on "+skus.length+" selected listing(s)?\n\n"+
              "Each SKU will loop through Suggest→Apply→Preview until Amazon accepts "+
              "or the loop can\u2019t make progress. This is sequential (one at a time) "+
              "so it may take a few minutes.")) return;

  const batch = {
    skus: skus, done: false, cancelled: false, startedAt: new Date().toISOString(),
    per_sku_states: [],    // one autoFix state per SKU
    current_idx: -1,
    summary: {ok: 0, stuck: 0, failed: 0},
  };
  window.BULK_AUTOFIX = batch;

  const panel = _bulkAutoFixPanel(batch);
  panel.show("Batch auto-fix: "+skus.length+" listing(s)");

  try{
    for(let i=0; i<skus.length; i++){
      if(batch.cancelled){ break; }
      batch.current_idx = i;
      const sku = skus[i];
      panel.step("["+(i+1)+"/"+skus.length+"] "+sku+" — running…");

      // Run the single-SKU loop and capture its state into the batch trace.
      // The single-SKU loop already stores state on window.AUTOFIX_STATE and
      // window._AUTOFIX_LAST_STATE so we can read it back when it finishes.
      window.AUTOFIX_STATE = null;
      try{
        await autoFixLoop(sku);
      }catch(e){
        batch.summary.failed++;
        batch.per_sku_states.push({sku: sku, error: String(e)});
        panel.step("["+(i+1)+"/"+skus.length+"] "+sku+" — CRASHED: "+String(e));
        panel.renderTrace();
        continue;
      }
      // autoFixLoop finished — pull the final state
      const finalState = window._AUTOFIX_LAST_STATE;
      if(finalState && finalState.sku === sku){
        batch.per_sku_states.push(finalState);
        // Judge the outcome from the last round's verdict (trace may be empty
        // if the loop bailed before completing any round -- e.g. /suggest 500)
        const lastRound = (finalState.trace && finalState.trace.length)
                          ? finalState.trace[finalState.trace.length-1]
                          : null;
        if(lastRound && lastRound.preview_verdict === 'ok_preview'){
          batch.summary.ok++;
        } else if(lastRound && lastRound.preview_verdict === 'error'){
          batch.summary.stuck++;
        } else {
          batch.summary.failed++;
        }
      } else {
        batch.summary.failed++;
        batch.per_sku_states.push({sku: sku, error: "no state captured"});
      }
      panel.renderTrace();
    }
    batch.done = true;
    if(batch.cancelled){
      panel.stop("Cancelled after "+batch.current_idx+" of "+skus.length+" SKU(s). "+
                  "Cleared: "+batch.summary.ok+" · stuck: "+batch.summary.stuck+" · failed: "+batch.summary.failed);
    } else {
      panel.done("Batch complete. Cleared: "+batch.summary.ok+
                 " · stuck: "+batch.summary.stuck+" · failed: "+batch.summary.failed);
    }
    panel.renderTrace();
  } finally {
    loadRows();
    // persist the full batch trace so a page refresh can't lose it
    try{ if(batch) _autoFixSaveLog('batch', _bulkAutoFixTraceText(batch), (batch.skus||[]).length+' skus'); }catch(e){}
  }
}

// Build one large trace text covering every SKU in the batch, ready to paste
// to Claude in one message.
function _bulkAutoFixTraceText(batch){
  const lines = [];
  lines.push('=== BULK AUTO-FIX BATCH TRACE ===');
  lines.push('Started: '+batch.startedAt);
  lines.push('SKUs: '+batch.skus.length);
  lines.push('Summary: cleared='+batch.summary.ok+
              ' · stuck='+batch.summary.stuck+
              ' · failed='+batch.summary.failed);
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
  let el = document.getElementById('autofix_panel');
  if(el){ el.remove(); }
  el = document.createElement('div');
  el.id = 'autofix_panel';
  el.style.cssText = 'position:fixed;bottom:20px;right:20px;width:620px;max-height:80vh;'+
    'background:#141b2b;border:1px solid #3b4d70;border-radius:10px;padding:12px;'+
    'box-shadow:0 8px 24px rgba(0,0,0,0.5);z-index:9999;font-size:12px;color:#e8eaed;'+
    'display:flex;flex-direction:column;gap:8px';
  el.innerHTML =
    '<div style="display:flex;justify-content:space-between;align-items:center;font-weight:600">'+
      '<span>✦ Batch Auto-fix ('+batch.skus.length+' SKU'+(batch.skus.length===1?'':'s')+')</span>'+
      '<div style="display:flex;gap:8px;align-items:center">'+
        '<button onclick="_bulkAutoFixCopyTrace()" '+
          'style="background:#5b3fb8;color:#fff;border:none;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:11px">'+
          '📋 Copy batch trace</button>'+
        '<button onclick="if(window.BULK_AUTOFIX)window.BULK_AUTOFIX.cancelled=true;if(window.AUTOFIX_STATE)window.AUTOFIX_STATE.cancelled=true;this.parentElement.parentElement.parentElement.remove()" '+
          'style="background:none;color:#e8eaed;border:none;cursor:pointer;font-size:16px" title="Cancel batch and close">✕</button>'+
      '</div>'+
    '</div>'+
    '<div id="bulk_autofix_status" style="color:#9cc1ff"></div>'+
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
      if(s) s.innerHTML = '<span style="color:#74e0a3">✓ '+esc(msg)+'</span>';
    },
    stop: function(msg){
      const s = document.getElementById('bulk_autofix_status');
      if(s) s.innerHTML = '<span style="color:#e3b768">⚠ '+esc(msg)+'</span>';
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
function edRow(label,ctrl,hint,prov,sub,req,softReq){ const provHtml = (typeof prov==='string') ? srcBadge(prov) : (prov?iBtnEntry(prov):""); const reqHtml = softReq ? '<span class="reqsoft" title="The schema lists this as required, but Amazon\u2019s last Preview accepted the listing WITHOUT it. Fill it only if a later Preview flags it.">\u2606 schema-listed</span>' : (req?'<span class="reqstar" title="Required by Amazon">\u2605</span>':""); return `<tr class="${hint?'flaggedrow':''}${sub?' subrow':''}"><td class="k">${sub?'<span class="subarrow">\u21b3</span> ':''}${esc(_cleanLabel(label))}${reqHtml}${provHtml}${hint?` <span class="fixhint">\u26a0 ${esc(hint)}</span>`:""}</td><td class="v">${ctrl}</td></tr>`; }
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
  return `<tr><td colspan="2" class="wcell"><div class="wlab">${esc(label)} ${counter} ${idx}</div>${warnmsg}${ta}</td></tr>`;
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
function parseFlagged(notes){
  // {field: hint} for every fixable attribute issue Amazon flagged in the last preview.
  // Maps composite dimension errors (item_depth_width_height) to the editable axis field.
  const out={};
  if(!notes) return out;
  String(notes).split(";").forEach(seg=>{
    const m=seg.match(/\[[EW]\]\s+([a-z][a-z0-9_]+)\s+([\s\S]*)/i);   // skips non-attribute "fields" like a bare barcode number
    if(!m) return;
    const field=m[1].toLowerCase(), msg=m[2];
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
        <b style="color:#ff8a8a">This listing's detail view hit an error while rendering.</b>
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
  const flagged=parseFlagged(r.notes);   // {field: hint} from Amazon's last preview (required / min-max / invalid)
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
      : edRow(lbl(k), editCell(sku,"attr",k,a[k],enums[k]||null), flagged[k], _prov&&_prov[k], false, isReq, _flatSchemaOnly);
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
  const cRows=[
      contentRow("Backend search terms", sku, "Search Terms / KW", r.search_terms, 249, backendOpts),
      contentRow("Title", sku, "Title", r.title, 200, titleOpts),
      contentRow("Item Highlights", sku, "item_highlights", _highlightVal, 125, highlightOpts)
    ]
    .concat([bulletMeterRow])
    .concat((r.bullets||[]).map((b,i)=>contentRow("Bullet "+(i+1), sku, "Bullet "+(i+1), b, 500, bulletOptsFor(i+1))))
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
    ? `<div class="hint" style="color:#e3b768;margin-top:4px">⚠ The main image is a LOCAL file Amazon can't fetch — it will block submission. Remove it (submit without an image) or set a public https URL.</div>`
    : "";
  const _imgActions = imgUrls.length
    ? `<div style="margin-top:6px;display:flex;gap:8px">
         <button class="suggestbtn" style="background:#2a1414;border-color:#5c2424;color:#ff8a8a" onclick="clearMainImage('${esc(sku)}')" title="Remove the main image URL so the listing can be created without an image (add one later in Seller Central)"><i class="ti ti-photo-off"></i> Remove main image</button>
       </div>`
    : "";
  const imgBlock = (imgUrls.length
    ? `<div class="kvsec">${imgLabel}</div><div class="imgrow">${imgUrls.map((u,i)=>`<div class="thumbwrap"><a href="${esc(u)}" target="_blank" title="${i===0?'MAIN image':'additional #'+i}"><img class="thumb" src="${esc(u)}" loading="lazy"><span class="thumbcap">${i===0?'main':'#'+i}</span></a><button class="thumbedit" title="Edit this image (AI changes only what you ask)" onclick="editListingImage('${esc(sku)}','${esc(u)}',${i})"><i class="ti ti-wand"></i></button></div>`).join("")}</div>${_imgWarn}${_imgActions}`
    : `<div class="kvsec">Images</div><div class="hint">No image captured for this row.</div>`)
    + `<div class="genimg" id="genimg_${sidv}">
        <div class="kvsec" style="color:#c8b6ff;margin-top:12px"><i class="ti ti-sparkles"></i> AI image generation</div>
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
  return `<details open><summary>Full listing data — click any value to edit; saves automatically${nEnum?'. Dropdowns = Amazon allowed values':''}</summary>
    ${imgBlock}
    <div class="kvsec">Identity &amp; offer</div><table class="kv">${idRows}</table>
    <div class="kvsec">Attributes${attrHdr}</div>${schemaDiag(r.product_type, nEnum, allAttrs.length, Object.keys(subs).length, missing, flagged, a)}${(typeof howWorks==="function")?howWorks('required_fields'):""}${hasAttrs?`<table class="kv">${attrRows}</table>`:''}${reqNote}${addCtrl}${rememberBtn}
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
      if(st) st.innerHTML='<span style="color:#ef9a9a">\u2717 Failed ('+(j.stage||'')+'): '+esc(j.error||'unknown')+'</span>';
      if(j.detailed_prompt){ var pw=document.getElementById('genpromptwrap_'+sidv); var pp=document.getElementById('genprompt_'+sidv); if(pw&&pp){pw.style.display='block'; pp.textContent=j.detailed_prompt;} }
      return;
    }
    if(st) st.innerHTML='<span style="color:#7fd99a">\u2713 Done ('+esc(j.text_provider||'')+' \u2192 '+esc(j.image_provider||'')+') \u2014 review below.</span>';
    var pw=document.getElementById('genpromptwrap_'+sidv); var pp=document.getElementById('genprompt_'+sidv);
    if(pw&&pp){ pw.style.display='block'; pp.textContent=j.detailed_prompt||''; }
    var out=document.getElementById('genresult_'+sidv);
    if(out){
      var _dimtxt=(j.width&&j.height)?(j.width+'×'+j.height+' px'):'';
      var _sztxt=(j.bytes)?_fmtBytes(j.bytes):'';
      var _meta=(_dimtxt||_sztxt)?('<div class="cc" style="margin:4px 0">'+esc([_dimtxt,_sztxt].filter(Boolean).join(' · '))+'</div>'):'';
      out.innerHTML='<div class="genpreview"><img src="'+j.data_url+'">'+_meta+
        '<div class="cc" id="gendrive_'+sidv+'" style="margin:2px 0;color:#86d0a8"></div>'+
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
              '<span class="cc" style="color:#8a93a6">(Amazon-ready link saved)</span>';
            out.dataset.driveurl=svj.drive_direct_url;
          } else {
            var _de = svj.drive_error ? (' Reason: '+esc(svj.drive_error)) : '';
            dr.innerHTML='<span class="cc" style="color:#e3b768">Saved locally, but NOT uploaded to Drive.'+_de+'</span>';
          }
        }
      }
    }catch(e){}
  }catch(e){
    clearInterval(ticker);
    if(btn){ btn.disabled=false; btn.textContent='Generate'; }
    if(st) st.innerHTML='<span style="color:#ef9a9a">\u2717 Error: '+esc(String(e))+'</span>';
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
      const sv = await (await fetch("/edit",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:sku, target:"attr", key:"main_product_image_locator", value:pub})})).json();
      if(sv && sv.ok){ toast("Main image set ✓ — Preview/Submit to send it to Amazon"); loadRows(); }
      else { toast("Image hosted but couldn't save to the row: "+((sv&&sv.error)||"")); }
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
  try{
    await fetch('/edit',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:sku,target:'attr',key:'main_product_image_locator',value:useUrl})});
    toast(savedUrl?'Set as main image (saved to media)':'Set as main image');
    loadRows();
  }catch(e){ toast('Could not apply: '+e); }
}
