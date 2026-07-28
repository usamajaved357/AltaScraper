/* Opt-in new dashboard (Stage 1). Additive: the classic UI is the untouched default.
   A client-side flag (localStorage ALTA_NEW_UI, default OFF) + the header "New UI" toggle
   flip between them instantly. Renders real data from /dashboard/summary. */
(function(){ "use strict";
  var KEY = "ALTA_NEW_UI";
  function on(){ return localStorage.getItem(KEY) === "1"; }
  function _esc(s){ return (typeof esc === "function") ? esc(s) : String(s==null?"":s); }
  function _toast(m){ if(typeof toast === "function") toast(m); }

  window.toggleNewUI = function(v){ localStorage.setItem(KEY, v ? "1" : "0"); applyNewUI(); };

  function applyNewUI(){
    var sw = document.getElementById("newui_switch");
    var grid = document.getElementById("wsgrid");
    var hd = document.getElementById("homehd");
    var nd = document.getElementById("newdash");
    if(!nd) return;
    var isOn = on();
    if(sw) sw.checked = isOn;
    if(isOn){
      if(grid) grid.style.display = "none";
      if(hd){ hd.style.display = "none"; }
      nd.style.display = "block";
      renderDashboard();
    } else {
      if(grid) grid.style.display = "";
      if(hd){ hd.style.display = ""; hd.textContent = "Workspaces"; }
      nd.style.display = "none";
    }
  }
  window.applyNewUI = applyNewUI;

  // "Open full queue" etc. reveal the classic workspaces grid (Stage 2 adds a unified queue).
  function showClassicGrid(){
    var grid = document.getElementById("wsgrid");
    var hd = document.getElementById("homehd");
    var nd = document.getElementById("newdash");
    if(nd) nd.style.display = "none";
    if(grid) grid.style.display = "";
    if(hd){ hd.style.display = ""; hd.innerHTML = '<span style="cursor:pointer;color:var(--accent)" onclick="applyNewUI()">← Dashboard</span> &middot; Workspaces'; }
  }
  window.showClassicGrid = showClassicGrid;

  function greeting(){
    var h = new Date().getHours();
    return h < 12 ? "Good morning" : (h < 18 ? "Good afternoon" : "Good evening");
  }

  function enterByLabel(label, sku){
    try{
      var accs = (typeof ACCOUNTS !== "undefined" && ACCOUNTS) || [];
      var a = accs.find(function(x){ return (x.label||x.id) === label; });
      if(a && typeof enterAccount === "function"){
        enterAccount(a.id);
        if(sku && typeof openDrawer === "function"){
          setTimeout(function(){ try{ openDrawer(sku); }catch(e){} }, 1300);
        }
        return;
      }
    }catch(e){}
    showClassicGrid();
    _toast("Open the workspace to see this listing.");
  }
  window.dbEnter = enterByLabel;

  function n(v){ return (v===null || v===undefined) ? "—" : v; }

  function renderDashboard(){
    var nd = document.getElementById("newdash");
    if(!nd) return;
    nd.innerHTML = '<div class="cc" style="color:var(--muted);padding:20px 0">Loading overview…</div>';
    fetch("/dashboard/summary").then(function(r){ return r.json(); }).then(function(d){
      if(!d || !d.ok){ nd.innerHTML = '<div class="db-card db-warn-red">Could not load the overview: '+_esc((d&&d.error)||"unknown")+'</div>'; return; }
      var c = d.counts || {};
      var need = d.need_you_total || 0;
      var subline = "Across " + n(d.accounts_count) + " account" + (d.accounts_count===1?"":"s") + " · " +
        (need > 0 ? '<span class="db-warn-amber">' + need + " thing" + (need===1?"":"s") + " need you</span>"
                  : '<span class="db-ok">nothing needs you right now</span>') +
        " · everything else is running";

      var metrics =
        '<div class="db-metrics">' +
          card(c.review, "Need review", "db-warn-amber", "review") +
          card(c.blocked, "Blocked", "db-warn-red", "blocked") +
          card(c.ready, "Ready to submit", "db-ok", "ready") +
          card(c.live, "Live", "", "live") +
        '</div>';

      // Needs you first
      var items = (d.needs_you || []).map(function(it){
        var pill = it.status === "Blocked" ? "blocked" : "review";
        var rc = it.status === "Blocked" ? "db-warn-red" : "";
        return '<div class="db-item" onclick="dbEnter('+js(it.account)+','+js(it.sku)+')">' +
          '<div style="flex:1;min-width:0"><p class="db-title">'+_esc(it.title)+'</p>' +
          '<p class="db-reason '+rc+'">'+_esc((it.account?it.account+" · ":"")+ (it.reason||""))+'</p></div>' +
          '<span class="db-pill '+pill+'">'+_esc(it.status)+'</span></div>';
      }).join("");
      if(!items) items = '<div class="db-ok" style="padding:9px 0;font-size:13px">✓ Nothing needs you right now</div>';
      var more = d.needs_you_more > 0 ? '<div class="db-item" style="cursor:pointer" onclick="showClassicGrid()"><span class="cc" style="color:var(--muted);font-size:12px">See all '+d.needs_you_more+' more →</span></div>' : "";
      var needsCard = '<div class="db-card"><p class="db-h"><i class="ti ti-bell db-warn-amber"></i> Needs you first</p>'+items+more+'</div>';

      // Compliance watch
      var cm = d.compliance || {};
      var flaggedNow = (cm.prohibited_current||0) + (cm.gated_current||0);
      var compCard = '<div class="db-card"><p class="db-h"><i class="ti ti-shield-half" style="color:var(--accent)"></i> Compliance watch</p>' +
        '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:10px"><span style="font-size:22px;font-weight:600" class="'+(cm.prohibited_current?"db-warn-red":"")+'">'+n(flaggedNow)+'</span><span class="cc" style="color:var(--muted);font-size:12px">flagged now (live scan — no weekly history yet)</span></div>' +
        kv("Prohibited (no path)", cm.prohibited_current, "db-warn-red") +
        kv("Gated / restricted (needs docs)", cm.gated_current, "db-warn-amber") +
        kv("Reference categories", cm.reference_categories, "") +
        kv("Confirmed from your history", cm.confirmed_history, "") +
        '<button class="db-chip" style="margin-top:12px;width:100%;justify-content:center" onclick="rcOpen()"><i class="ti ti-search"></i> Check a product before sourcing</button></div>';

      // Sync + account health
      var srows = (d.sync || []).map(function(s){
        var col = s.dot==="green"?"#7fd99a":(s.dot==="red"?"#ef9a9a":(s.dot==="amber"?"#e3b768":"var(--muted)"));
        var tail = s.note ? (" · " + s.note) : (s.last_sync ? (" · synced " + s.last_sync) : " · not synced yet");
        return '<div style="display:flex;align-items:center;gap:8px;font-size:12px;line-height:2"><span class="db-dot" style="background:'+col+'"></span> '+_esc(s.account)+(s.marketplace?" ("+_esc(s.marketplace)+")":"")+_esc(tail)+'</div>';
      }).join("");
      if(!srows) srows = '<div class="cc" style="color:var(--muted);font-size:12px">No accounts configured.</div>';
      var syncCard = '<div class="db-card"><p class="db-h"><i class="ti ti-refresh db-ok"></i> Sync + account health</p>'+srows+'</div>';

      // Quick actions
      var actions = '<div class="db-actions">' +
        '<button class="db-chip" onclick="showClassicGrid()"><i class="ti ti-list"></i> Open full queue</button>' +
        '<button class="db-chip" onclick="showClassicGrid();"><i class="ti ti-plus"></i> New listing</button>' +
        '<button class="db-chip" onclick="showClassicGrid();"><i class="ti ti-chart-bar"></i> PPC</button>' +
        '<button class="db-chip" onclick="dbSyncHint()"><i class="ti ti-refresh"></i> Sync all</button>' +
        '</div>';

      var blockedNote = d.blocked_partial ? '<p class="db-note">Blocked counts stored holds only for now; the restricted-checker’s block lands in Stage 3.</p>' : "";
      var missNote = (d.missing_accounts && d.missing_accounts.length) ? '<p class="db-note">Could not read: '+_esc(d.missing_accounts.join(", "))+' — shown as —.</p>' : "";

      nd.innerHTML =
        '<p class="db-greet">'+greeting()+', Talha</p>' +
        '<p class="db-sub">'+subline+'</p>' +
        metrics +
        '<div class="db-grid2">'+needsCard+compCard+'</div>' +
        '<div class="db-grid2">'+syncCard+'<div class="db-card"><p class="db-h"><i class="ti ti-bolt" style="color:var(--accent)"></i> Quick actions</p>'+actions+'</div></div>' +
        blockedNote + missNote;
    }).catch(function(e){
      nd.innerHTML = '<div class="db-card db-warn-red">Overview failed to load: '+_esc(String(e))+'</div>';
    });
  }
  window.renderDashboard = renderDashboard;

  function card(v, label, cls, state){
    return '<div class="db-metric" onclick="dbMetric('+js(state)+','+js(label)+')"><p class="n '+cls+'">'+n(v)+'</p><p class="l">'+_esc(label)+'</p></div>';
  }
  function kv(label, v, cls){
    return '<div class="db-kv"><span>'+_esc(label)+'</span><span class="'+cls+'">'+n(v)+'</span></div>';
  }
  function js(s){ return JSON.stringify(String(s==null?"":s)); }

  window.dbMetric = function(state, label){
    // Filtered queue is Stage 2; for now reveal the workspaces so the user can open one.
    _toast(label + ": the filtered queue arrives in Stage 2 — open a workspace for now.");
    showClassicGrid();
  };
  window.dbSyncHint = function(){ _toast("Sync lives in each workspace’s Sync panel (per account)."); };

  /* ---- Shape-1 modal ---- */
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
        if(!d.matched){
          res.innerHTML='<div class="rc-clear"><b>No known restriction matched.</b><div class="cc" style="color:#9ec9ad;margin-top:4px">'+_esc(d.message||"")+'</div></div>';
          return;
        }
        var html = d.matches.map(function(m){
          var tierl = (m.tier||"").toLowerCase();
          var cls = tierl==="prohibited" ? "prohibited" : (tierl==="gated" ? "gated" : "restricted");
          var docs = (m.docs||[]).length ? '<div class="cc" style="margin-top:6px"><b>Docs needed:</b> '+_esc(m.docs.join("; "))+'</div>' : "";
          var act = (m.action==="BLOCK") ? '<span class="rc-badge prohibited">BLOCK — see why</span>' : '<span class="rc-badge '+cls+'">WARN</span>';
          return '<div class="rc-match '+cls+'">' +
            '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">'+act+' <b>'+_esc(m.label)+'</b>'+
            '<span class="rc-src">'+_esc(m.source||"")+'</span></div>'+
            '<div class="cc" style="margin-top:5px">'+_esc(m.reason||"")+ (m.regulator?(' · '+_esc(m.regulator)):"")+'</div>'+docs+'</div>';
        }).join("");
        html += '<div class="cc db-note">'+_esc(d.caveat||"")+'</div>';
        res.innerHTML = html;
      }).catch(function(e){ res.innerHTML='<div class="db-warn-red">Check failed: '+_esc(String(e))+'</div>'; });
  };

  document.addEventListener("DOMContentLoaded", function(){
    try{ applyNewUI(); }catch(e){}
  });
})();
