/* Opt-in NAVY dashboard (Stage 1). Additive: the classic UI is the untouched default.
   Flag localStorage ALTA_NEW_UI (default OFF) + the header "New UI" toggle flip between
   them. When ON, a full-screen navy overlay (#altui) renders the cross-account overview
   from real data (/dashboard/summary). All navy CSS is scoped under #altui. */
(function(){ "use strict";
  var KEY = "ALTA_NEW_UI";
  function on(){ return localStorage.getItem(KEY) === "1"; }
  function _esc(s){ return (typeof esc === "function") ? esc(s) : String(s==null?"":s); }
  function _toast(m){ if(typeof toast === "function") toast(m); }
  function js(s){ return JSON.stringify(String(s==null?"":s)); }
  function n(v){ return (v===null || v===undefined) ? "—" : v; }

  window.toggleNewUI = function(v){ localStorage.setItem(KEY, v ? "1" : "0"); applyNewUI(); };

  function applyNewUI(){
    var sw = document.getElementById("newui_switch");
    var altui = document.getElementById("altui");
    var isOn = on();
    if(sw) sw.checked = isOn;
    if(!altui) return;
    if(isOn){ altui.classList.add("show"); renderDashboard(); }
    else { altui.classList.remove("show"); }
  }
  window.applyNewUI = applyNewUI;

  // Nav items / metric tiles that need the (Stage-2) queue or (Stage-3) detail fall back to
  // the classic UI for now -- flip the flag off so the user lands in the working classic view.
  window.altShowClassic = function(){ toggleNewUI(false); };

  function greeting(){
    var h = new Date().getHours();
    return h < 12 ? "Good morning" : (h < 18 ? "Good afternoon" : "Good evening");
  }

  // needs-you click: drop to classic, open that account + its listing detail (Stage 3 brings
  // the detail view into navy).
  window.dbEnter = function(label, sku){
    toggleNewUI(false);
    try{
      var accs = (typeof ACCOUNTS !== "undefined" && ACCOUNTS) || [];
      var a = accs.find(function(x){ return (x.label||x.id) === label; });
      if(a && typeof enterAccount === "function"){
        enterAccount(a.id);
        if(sku && typeof openDrawer === "function") setTimeout(function(){ try{ openDrawer(sku); }catch(e){} }, 1300);
        return;
      }
    }catch(e){}
    _toast("Open the workspace to see this listing.");
  };
  window.dbMetric = function(label){ _toast(label + ": the filtered queue arrives in Stage 2 — opening classic listings."); altShowClassic(); };

  function renderDashboard(){
    var el = document.getElementById("alt_content");
    if(!el) return;
    el.innerHTML = '<div class="muted" style="padding:20px 0">Loading overview…</div>';
    fetch("/dashboard/summary").then(function(r){ return r.json(); }).then(function(d){
      if(!d || !d.ok){ el.innerHTML = '<div class="card c-danger">Could not load the overview: '+_esc((d&&d.error)||"unknown")+'</div>'; return; }
      var c = d.counts || {};
      var need = d.need_you_total || 0;

      // health badge (X of N healthy) from the sync dots
      var sync = d.sync || [];
      var healthy = sync.filter(function(s){ return s.dot === "green"; }).length;
      var hb = document.getElementById("alt_health");
      if(hb) hb.innerHTML = '<span style="width:6px;height:6px;border-radius:50%;background:'+(healthy===sync.length?"var(--ok)":"var(--warn)")+'"></span> '+healthy+' of '+sync.length+' healthy';

      var sub = "Across " + n(d.accounts_count) + " account" + (d.accounts_count===1?"":"s") + " · " +
        (need>0 ? '<span class="c-warn">'+need+" thing"+(need===1?"":"s")+" need you</span>" : '<span class="c-ok">nothing needs you right now</span>') +
        " · everything else is running";

      var tiles = '<div class="grid4">' +
        tile(c.review, "Need review", "c-warn") + tile(c.blocked, "Blocked", "c-danger") +
        tile(c.ready, "Ready", "c-ok") + tile(c.live, "Live", "") + '</div>';

      // Needs you first
      var items = (d.needs_you || []).map(function(it){
        var pill = it.status === "Blocked" ? "p-blocked" : "p-review";
        var rcls = it.status === "Blocked" ? "c-danger" : "muted";
        return '<div class="row" onclick="dbEnter('+js(it.account)+','+js(it.sku)+')">' +
          '<div style="flex:1;min-width:0"><p style="font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+_esc(it.title)+'</p>' +
          '<p style="font-size:11px;margin-top:2px" class="'+rcls+'">'+_esc((it.account?it.account+" · ":"")+(it.reason||""))+'</p></div>' +
          '<span class="pill '+pill+'">'+_esc(it.status)+'</span></div>';
      }).join("");
      if(!items) items = '<div class="c-ok" style="padding:9px 0;font-size:13px">✓ Nothing needs you right now</div>';
      if(d.needs_you_more>0) items += '<div class="row" onclick="altShowClassic()"><span class="muted" style="font-size:12px">See all '+d.needs_you_more+' more →</span></div>';
      var needsCard = '<div class="card"><p class="eyebrow" style="margin-bottom:10px">Needs you first</p>'+items+'</div>';

      // Compliance watch
      var cm = d.compliance || {};
      var flaggedNow = (cm.prohibited_current||0) + (cm.gated_current||0);
      var compCard = '<div class="card"><p class="eyebrow" style="margin-bottom:10px">Compliance watch</p>' +
        '<div style="display:flex;align-items:baseline;gap:7px;margin-bottom:10px"><span style="font-size:23px;font-weight:600" class="'+(cm.prohibited_current?"c-danger":"")+'">'+n(flaggedNow)+'</span><span class="muted" style="font-size:12px">flagged now · live scan (no weekly history)</span></div>' +
        kv("Prohibited (no path)", cm.prohibited_current, "c-danger") +
        kv("Gated / restricted", cm.gated_current, "c-warn") +
        kv("Reference categories", cm.reference_categories, "") +
        kv("Confirmed from your history", cm.confirmed_history, "") +
        '<button class="btn btn-primary" style="width:100%;margin-top:11px;justify-content:center" onclick="rcOpen()"><i class="ti ti-search"></i> Check a product</button></div>';

      // Sync + account health
      var srows = sync.map(function(s){
        var tail = s.note ? (" · " + s.note) : (s.last_sync ? (" · synced " + s.last_sync) : " · not synced yet");
        return '<div style="display:flex;align-items:center;gap:8px;font-size:12px;line-height:2.1"><span class="dot '+_esc(s.dot)+'"></span> '+_esc(s.account)+(s.marketplace?" ("+_esc(s.marketplace)+")":"")+_esc(tail)+'</div>';
      }).join("");
      if(!srows) srows = '<div class="muted" style="font-size:12px">No accounts configured.</div>';
      var syncCard = '<div class="card"><p class="eyebrow" style="margin-bottom:10px">Sync + account health</p>'+srows+'</div>';

      // Inventory alerts (real; omit-honest empty)
      var inv = d.inventory || {};
      var invBody;
      if(!inv.available){ invBody = '<p class="muted" style="font-size:12px">No inventory data yet — run Inventory per account to populate low-stock alerts.</p>'; }
      else if(!inv.total){ invBody = '<p class="c-ok" style="font-size:13px">✓ No low-stock alerts</p>'; }
      else {
        invBody = '<div style="display:flex;align-items:baseline;gap:7px;margin-bottom:8px"><span style="font-size:23px;font-weight:600" class="c-warn">'+inv.total+'</span><span class="muted" style="font-size:12px">SKUs need reorder</span></div>' +
          (inv.by_account||[]).map(function(b){ return '<div class="kv"><span>'+_esc(b.account)+'</span><span class="c-warn" style="font-weight:600">'+b.count+'</span></div>'; }).join("");
      }
      var invCard = '<div class="card"><p class="eyebrow" style="margin-bottom:10px">Inventory alerts</p>'+invBody+'</div>';

      var notes = "";
      if(d.blocked_partial) notes += '<p class="note">Blocked counts stored holds only for now; the restricted-checker’s block lands in Stage 3.</p>';
      if(d.missing_accounts && d.missing_accounts.length) notes += '<p class="note">Could not read: '+_esc(d.missing_accounts.join(", "))+' — shown as —.</p>';
      notes += '<p class="note">PPC 7-day performance tile omitted — no live spend/sales/ACOS data source in the app.</p>';

      el.innerHTML =
        '<h1 class="h1">'+greeting()+', Talha</h1>' +
        '<p class="muted" style="font-size:13px;margin:3px 0 16px">'+sub+'</p>' +
        tiles +
        '<div class="grid2">'+needsCard+compCard+'</div>' +
        '<div class="grid2">'+syncCard+invCard+'</div>' +
        notes;
    }).catch(function(e){ el.innerHTML = '<div class="card c-danger">Overview failed to load: '+_esc(String(e))+'</div>'; });
  }
  window.renderDashboard = renderDashboard;

  function tile(v, label, cls){
    return '<div class="tile" onclick="dbMetric('+js(label)+')"><p class="n '+cls+'">'+n(v)+'</p><p class="l">'+_esc(label)+'</p></div>';
  }
  function kv(label, v, cls){ return '<div class="kv"><span>'+_esc(label)+'</span><span class="'+cls+'" style="font-weight:600">'+n(v)+'</span></div>'; }

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
        if(!d.matched){ res.innerHTML='<div class="rc-clear"><b>No known restriction matched.</b><div class="cc" style="color:#9ec9ad;margin-top:4px">'+_esc(d.message||"")+'</div></div>'; return; }
        var html = d.matches.map(function(m){
          var tierl=(m.tier||"").toLowerCase();
          var cls = tierl==="prohibited"?"prohibited":(tierl==="gated"?"gated":"restricted");
          var docs=(m.docs||[]).length?'<div class="cc" style="margin-top:6px"><b>Docs needed:</b> '+_esc(m.docs.join("; "))+'</div>':"";
          var act=(m.action==="BLOCK")?'<span class="rc-badge prohibited">BLOCK — see why</span>':'<span class="rc-badge '+cls+'">WARN</span>';
          return '<div class="rc-match '+cls+'"><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">'+act+' <b>'+_esc(m.label)+'</b><span class="rc-src">'+_esc(m.source||"")+'</span></div><div class="cc" style="margin-top:5px">'+_esc(m.reason||"")+(m.regulator?(' · '+_esc(m.regulator)):"")+'</div>'+docs+'</div>';
        }).join("");
        html += '<div class="cc db-note">'+_esc(d.caveat||"")+'</div>';
        res.innerHTML = html;
      }).catch(function(e){ res.innerHTML='<div class="db-warn-red">Check failed: '+_esc(String(e))+'</div>'; });
  };

  document.addEventListener("DOMContentLoaded", function(){ try{ applyNewUI(); }catch(e){} });
})();
