/* The "Check a product before sourcing" modal (Shape 1).

   This file used to also hold the opt-in navy #altui overlay and its ALTA_NEW_UI
   toggle. That experiment is gone: the Orbit design system is now the app's only
   style, so there is nothing left to toggle between. Everything the overlay owned
   -- toggleNewUI, applyNewUI, altShowClassic, renderDashboard and the dbEnter /
   dbMetric / dbEnterId jump helpers -- was removed together with the #altui markup
   and altui.css. Nothing outside that block called any of it.

   The /dashboard/summary endpoint it read is untouched, per the brief's "do not
   change any Python". It is simply no longer called from here. */
(function(){ "use strict";
  function _esc(s){ return (typeof esc === "function") ? esc(s) : String(s==null?"":s); }

  /* ---- Shape-1 modal (unchanged behaviour) ---- */
  window.rcOpen = function(){ var m=document.getElementById("rc_modal"); if(m){ m.classList.add("show"); var t=document.getElementById("rc_text"); if(t) t.focus(); } };
  window.rcClose = function(){ var m=document.getElementById("rc_modal"); if(m) m.classList.remove("show"); };
  window.rcRun = function(){
    var text=(document.getElementById("rc_text")||{}).value||"";
    var mkt=(document.getElementById("rc_mkt")||{}).value||"UK";
    var res=document.getElementById("rc_res");
    if(!text.trim()){ if(res) res.innerHTML='<div class="cc db-warn-amber">Paste a product title or description first.</div>'; return; }
    if(res) res.innerHTML='<div class="cc" style="color:var(--muted)">Checking…</div>';
    fetch("/restricted/check",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:text,marketplace:mkt})})
      .then(function(r){return r.json();}).then(function(d){
        if(!d||!d.ok){ res.innerHTML='<div class="db-warn-red">Check failed: '+_esc((d&&d.error)||"unknown")+'</div>'; return; }
        var sv = d.sourcing_viability || {matched:false, risks:[]};
        var html = "";
        /* 1. RESTRICTED / GATED — can I create this listing at all? */
        if(d.matched){
          html += (d.matches||[]).map(function(m){
            var tierl=(m.tier||"").toLowerCase();
            var cls = tierl==="prohibited"?"prohibited":(tierl==="gated"?"gated":"restricted");
            var docs=(m.docs||[]).length?'<div class="cc" style="margin-top:6px"><b>Docs needed:</b> '+_esc(m.docs.join("; "))+'</div>':"";
            var act=(m.action==="BLOCK")?'<span class="rc-badge prohibited">BLOCK — see why</span>':'<span class="rc-badge '+cls+'">WARN</span>';
            return '<div class="rc-match '+cls+'"><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">'+act+' <b>'+_esc(m.label)+'</b><span class="rc-src">'+_esc(m.source||"")+'</span></div><div class="cc" style="margin-top:5px">'+_esc(m.reason||"")+(m.regulator?(' · '+_esc(m.regulator)):"")+'</div>'+docs+'</div>';
          }).join("");
        } else {
          html += '<div class="rc-clear"><b>No known restriction matched.</b><div class="cc" style="color:var(--ok);margin-top:4px">'+_esc(d.message||"")+'</div></div>';
        }
        /* 2. SOURCING VIABILITY — a DIFFERENT question: nothing may block this
              listing today, yet Amazon can demand safety documents months later.
              The patio heater passed every restriction check and still cost us
              the ASIN, so this block is shown even when section 1 is clear. */
        if(sv.matched && (sv.risks||[]).length){
          html += '<div class="cc" style="margin-top:12px;font-weight:600">Sourcing viability — documents Amazon will likely request later</div>';
          html += (sv.risks||[]).map(function(r){
            var cls = (r.risk==="HIGH")?"prohibited":"gated";
            var docs=(r.docs||[]).length?'<div class="cc" style="margin-top:6px"><b>Docs you would need:</b> '+_esc(r.docs.join("; "))+'</div>':"";
            var sig=(r.signals||[]).length?'<div class="cc" style="margin-top:4px;color:var(--muted)">Detected: '+_esc(r.signals.join("; "))+'</div>':"";
            return '<div class="rc-match '+cls+'"><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><span class="rc-badge '+cls+'">'+_esc(r.risk||"")+' RISK</span> <b>'+_esc(r.label)+'</b><span class="rc-src">'+_esc(r.id||"")+'</span></div><div class="cc" style="margin-top:5px">'+_esc(r.reason||"")+(r.regulator?(' · '+_esc(r.regulator)):"")+'</div>'+sig+docs+'<div class="cc" style="margin-top:6px">As a reseller you probably cannot provide these.</div></div>';
          }).join("");
          html += '<div class="cc db-note">'+_esc(sv.caveat||"")+'</div>';
        } else if(!d.matched){
          html += '<div class="cc db-note">'+_esc(sv.message||"")+'</div>';
        }
        html += '<div class="cc db-note">'+_esc(d.caveat||"")+'</div>';
        res.innerHTML = html;
      }).catch(function(e){ res.innerHTML='<div class="db-warn-red">Check failed: '+_esc(String(e))+'</div>'; });
  };

})();
