// ===================== SOURCE REPRICER =====================
// What the app WOULD do to each enrolled listing, and why.
//
// The screen's whole job is to make a decision arguable before it is armed.
// So every row shows the reasoning, not just the outcome: which supplier was
// chosen, what the others were rejected for, how old the readings were, and the
// arithmetic behind the price. A number with no explanation is exactly what
// nobody should be trusting with their prices.
//
// Nothing here writes to Amazon. The buttons re-read suppliers and re-decide;
// arming the repricer is Phase D and is deliberately not reachable from here.

let SRC_ROWS = [];
let SRC_RULE = null;
let SRC_MASTER = false;     // the master switch, as the SERVER reports it

// Every /sourcing call says WHICH account and marketplace it means.
//
// It used to rely on the server's active_marketplace, which this screen never
// sets -- opening the Repricer directly left it empty, so it looked up
// jack_uk::"" , found nothing, and reported "no live listings cached" for an
// account with 55 of them. The browser already knows both; sending them removes
// the guess entirely.
function _srcScope(){
  const p = [];
  if(typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
    p.push("id=" + encodeURIComponent(CUR_ACCOUNT.id));
  if(typeof WS_MARKET !== "undefined" && WS_MARKET)
    p.push("marketplace=" + encodeURIComponent(WS_MARKET));
  return p.join("&");
}
function _srcUrl(path, extra){
  const q = [_srcScope(), extra || ""].filter(Boolean).join("&");
  return path + (q ? (path.indexOf("?") >= 0 ? "&" : "?") + q : "");
}
function _srcBody(o){
  const b = Object.assign({}, o || {});
  if(typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id) b.id = CUR_ACCOUNT.id;
  if(typeof WS_MARKET !== "undefined" && WS_MARKET) b.marketplace = WS_MARKET;
  return JSON.stringify(b);
}

function _sesc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
// An argument for an inline onclick. Single-quoted for JS, then escaped for the
// attribute -- see the same helper in users.js and the bug that made it
// necessary: JSON.stringify closes the attribute it is pasted into.
function _sarg(s){
  const js = String(s==null?"":s).replace(/\\/g,"\\\\").replace(/'/g,"\\'");
  return "'" + js.replace(/&/g,"&amp;").replace(/"/g,"&quot;")
                 .replace(/</g,"&lt;").replace(/>/g,"&gt;") + "'";
}
function _smoney(v){
  return (v==null || v==="") ? "—" : Number(v).toFixed(2);
}

function sourcingOnOpen(){ sourcingLoad(); }

async function sourcingLoad(){
  const body = document.getElementById("srcbody");
  if(!body) return;
  body.innerHTML = '<div class="cc" style="padding:16px"><span class="genspin"></span> Loading…</div>';
  let j;
  try{ j = await (await fetch(_srcUrl("/sourcing/list"))).json(); }
  catch(e){ body.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">Could not load: '+_sesc(String(e))+'</div>'; return; }
  if(!j || !j.ok){
    body.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">'+_sesc((j&&j.error)||"Could not load")+'</div>';
    return;
  }
  SRC_ROWS = j.rows || [];
  SRC_RULE = j.rule || j.defaults || {};
  // Read from the server, never remembered from the last click: whether the app
  // is currently allowed to change prices is not something to guess at.
  try{ SRC_MASTER = !!(await (await fetch(_srcUrl("/sourcing/master"))).json()).enabled; }
  catch(e){ SRC_MASTER = false; }
  sourcingRender(j);
}

async function sourcingMaster(on){
  if(on && !confirm("Turn the master switch ON?\n\nArmed SKUs will then have their "
                  + "price, stock and handling time changed on Amazon automatically. "
                  + "SKUs still in dry run are unaffected.")) return;
  try{
    const j = await (await fetch("/sourcing/master",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({enabled:!!on})})).json();
    if(!j.ok){ toast(j.error||"failed"); return; }
    toast(j.enabled ? "Master switch ON" : "Master switch off — nothing will be pushed");
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}

async function sourcingArm(sku, live){
  if(live && !confirm("Arm "+sku+"?\n\nFrom then on the app may change this listing's "
                    + "price, stock and handling time on Amazon by itself.")) return;
  try{
    const j = await (await fetch("/sourcing/arm",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku, live:!!live})})).json();
    if(!j.ok){ toast(j.error||"Could not arm"); return; }
    toast(j.note || (j.mode==="live" ? "Armed" : "Back to dry run"));
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}

async function sourcingMinPrice(sku){
  const v = prompt("Lowest price you will ever sell "+sku+" at.\n\nThis is the one "
                 + "guard that still works if a supplier's page is misread, so the "
                 + "app will not arm a SKU without it.");
  if(v===null) return;
  try{
    const j = await (await fetch("/sourcing/rules",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku, rule:{min_price: v===""? null : parseFloat(v)}})})).json();
    if(!j.ok){ toast(j.error||"failed"); return; }
    toast("Minimum price saved"); sourcingLoad();
  }catch(e){ toast(String(e)); }
}

function sourcingRender(j){
  const body = document.getElementById("srcbody");
  const c = j.counts || {};
  let h = "";

  // The standing statement of what the app is doing to real listings right now.
  // It sits at the top rather than in a footnote because "is this live?" is the
  // only question that really matters, and the answer must never be a guess.
  const live = SRC_ROWS.filter(function(r){ return r.mode==="live"; }).length;
  if(SRC_MASTER && live){
    h += '<div style="font-size:12px;margin:2px 0 12px;padding:9px 11px;'
      +  'border:1px solid #4a2323;background:#2a1212;border-radius:6px">'
      +  '<b style="color:#e88a8a">Live.</b> '+live+' SKU'+(live===1?" is":"s are")
      +  ' armed and can have their price, stock and handling time changed on '
      +  'Amazon without anyone watching. At most one change each per 4 hours, '
      +  'and never below the minimum price you set. '
      +  '<button class="db-chip" onclick="sourcingMaster(false)" '
      +  'style="margin-left:6px">Stop everything</button></div>';
  } else {
    h += '<div class="cc" style="font-size:12px;margin:2px 0 12px;padding:9px 11px;'
      +  'border:1px solid #26403a;background:#10231f;border-radius:6px">'
      +  '<b>Dry run.</b> Nothing here changes a live listing. The app reads your '
      +  'suppliers every 4 hours, works out what it would do, and writes it down. '
      +  'Read this for a while before it is armed &mdash; if a decision looks wrong '
      +  'here, it would have been wrong on Amazon.'
      +  (SRC_MASTER ? ' The master switch is on, but no SKU is armed yet.'
                     : ' The master switch is off.')
      +  '</div>';
  }

  h += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">'
    +  '<button class="db-chip" onclick="sourcingCheckNow(this)">'
    +  '<i class="ti ti-refresh"></i> Re-read suppliers now</button>'
    +  '<button class="db-chip" onclick="sourcingAddPrompt()">'
    +  '<i class="ti ti-plus"></i> Enrol a SKU</button>'
    +  '<button class="db-chip" onclick="sourcingMaster('+(SRC_MASTER?"false":"true")+')">'
    +  (SRC_MASTER ? '<i class="ti ti-lock-open"></i> Master switch: ON'
                   : '<i class="ti ti-lock"></i> Master switch: off')+'</button>'
    +  '<span class="cc" style="font-size:11.5px;align-self:center">'
    +  (c.update||0)+' would change &middot; '+(c.out_of_stock||0)+' would go out of stock &middot; '
    +  (c.none||0)+' unchanged'
    +  ((c.blocked||0) ? ' &middot; <b>'+c.blocked+' held</b>' : '')
    +  '</span></div>';

  if(j.note){
    h += '<div class="cc" style="font-size:12px;padding:10px;border:1px dashed #2a3446;border-radius:6px">'
      +  _sesc(j.note)+' Enrol a SKU above to start watching its suppliers.</div>';
    body.innerHTML = h; return;
  }

  SRC_ROWS.forEach(function(r, i){ h += sourcingRow(r, i); });
  body.innerHTML = h;
}

function _actionChip(d){
  const a = d.action;
  if(d.blocked_by) return '<span class="db-chip" style="background:#3a2f12;color:#e8c66a">held</span>';
  if(a==="update") return '<span class="db-chip" style="background:#12303a;color:#6ac7e8">would change</span>';
  if(a==="out_of_stock") return '<span class="db-chip" style="background:#3a1b1b;color:#e88a8a">would go out of stock</span>';
  return '<span class="db-chip">no change</span>';
}

function sourcingRow(r, i){
  const d = r.decision || {}, cur = r.current || {};
  const id = "srcrow_"+i;
  let h = '<div style="border:1px solid #26303f;border-radius:7px;padding:10px 12px;margin-bottom:9px">';

  h += '<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">'
    +  '<code style="font-size:12px">'+_sesc(r.sku)+'</code>'
    +  _actionChip(d)
    +  '<span style="flex:1"></span>'
    +  '<span class="cc" style="font-size:11.5px">now '+_smoney(cur.price)
    +  (cur.lead_days!=null ? ' &middot; '+cur.lead_days+'d handling' : '')
    +  '</span>';
  if(d.action==="update"){
    h += '<span style="font-size:12px;font-weight:600">&rarr; '+_smoney(d.price)
      +  (d.lead_days!=null ? ' &middot; '+d.lead_days+'d' : '')+'</span>';
  }
  h += '<button class="db-chip" onclick="sourcingToggleDetail('+_sarg(id)+')">Why?</button>'
    +  (r.mode==="live"
        ? '<button class="db-chip" style="background:#3a1b1b;color:#e88a8a" '
          + 'onclick="sourcingArm('+_sarg(r.sku)+',false)">Armed &mdash; disarm</button>'
        : '<button class="db-chip" onclick="sourcingArm('+_sarg(r.sku)+',true)">Arm</button>')
    +  '<button class="db-chip" onclick="sourcingUnenrol('+_sarg(r.sku)+')">Remove</button>'
    +  '</div>';

  // The reason line is the point of the whole screen.
  h += '<div class="cc" style="font-size:11.5px;margin-top:5px">'
    +  (d.blocked_by ? '<b style="color:#e8c66a">'+_sesc(d.blocked_by)+'</b> &mdash; ' : '')
    +  _sesc(d.reason||"")+'</div>';

  h += '<div id="'+id+'" style="display:none;margin-top:9px">';
  h += '<div class="cc" style="font-size:11px;margin-bottom:4px">Suppliers</div>';
  (r.sources||[]).forEach(function(s){
    const k = s.check || {};
    const rej = (d.rejections||[]).find(function(x){ return x.source_id===s.id; });
    const chosen = d.source_id===s.id;
    h += '<div style="display:flex;gap:8px;align-items:center;font-size:11.5px;'
      +  'padding:4px 0;border-top:1px solid #1c2531">'
      +  (chosen ? '<span class="db-chip" style="background:#12303a;color:#6ac7e8">using</span>'
                 : '<span class="db-chip" style="opacity:.55">—</span>')
      +  '<a href="'+_sesc(s.url)+'" target="_blank" rel="noopener" style="max-width:280px;'
      +  'overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+_sesc(s.label||s.url)+'</a>'
      +  '<span class="cc">'+_sesc(s.kind)+'</span>'
      +  '<span style="flex:1"></span>'
      +  '<span>'+_smoney(k.price)+' + '+(k.shipping==null?'<b style="color:#e8c66a">postage unknown</b>':_smoney(k.shipping))+'</span>'
      +  '<span class="cc">'+(k.in_stock===true?'in stock':k.in_stock===false?'out of stock':'stock unknown')+'</span>'
      +  '<span class="cc">'+(k.dispatch_days==null?'':k.dispatch_days+'d')+'</span>'
      +  (rej ? '<span class="cc" style="color:#e8c66a">'+_sesc(rej.reason)+'</span>' : '')
      +  '<button class="db-chip" onclick="sourcingRemoveSource('+s.id+')">×</button>'
      +  '</div>';
  });
  if(!(r.sources||[]).length){
    h += '<div class="cc" style="font-size:11.5px;padding:4px 0">'
      +  'No suppliers yet &mdash; nothing can be decided until one is added.</div>';
  }
  h += '<div style="margin-top:7px"><button class="db-chip" '
    +  'onclick="sourcingAddSourcePrompt('+_sarg(r.sku)+')">'
    +  '<i class="ti ti-plus"></i> Add a supplier link</button></div>';
  // The minimum price is shown whether or not it is set, because its ABSENCE is
  // the reason a SKU cannot be armed, and that has to be visible at the point of
  // trying rather than only in the error message afterwards.
  const mp = (r.rule||{}).min_price;
  h += '<div class="cc" style="font-size:11.5px;margin-top:7px">Never sell below: '
    +  (mp==null
        ? '<b style="color:#e8c66a">not set</b> — required before this SKU can be armed'
        : '<b>'+_smoney(mp)+'</b>')
    +  ' <button class="db-chip" onclick="sourcingMinPrice('+_sarg(r.sku)+')">'
    +  (mp==null?'Set':'Change')+'</button></div>';
  if(d.inputs_age_mins!=null){
    h += '<div class="cc" style="font-size:11px;margin-top:6px">Decided on a reading '
      +  Math.round(d.inputs_age_mins)+' minutes old.</div>';
  }
  h += '</div></div>';
  return h;
}

function sourcingToggleDetail(id){
  const el = document.getElementById(id);
  if(el) el.style.display = (el.style.display==="none") ? "block" : "none";
}

async function sourcingCheckNow(btn){
  if(btn){ btn.disabled=true; btn.innerHTML='<span class="genspin"></span> reading…'; }
  try{
    const j = await (await fetch("/sourcing/check",{method:"POST",
      headers:{"Content-Type":"application/json"}, body:_srcBody({})})).json();
    if(!j.ok){ toast(j.error||"Could not read the suppliers"); return; }
    const f = j.fetch || {};
    let msg = "Read "+(f.checked||0)+" supplier"+((f.checked===1)?"":"s");
    if(f.unreadable) msg += " · "+f.unreadable+" unreadable";
    if(f.ended) msg += " · "+f.ended+" ended";
    toast(f.note || msg);
    await sourcingLoad();
  }catch(e){ toast("Failed: "+((e&&e.message)||e)); }
  finally{ if(btn){ btn.disabled=false; btn.innerHTML='<i class="ti ti-refresh"></i> Re-read suppliers now'; } }
}

// Pick from what is actually on Amazon, rather than typing a SKU from memory.
// A typed SKU with a typo in it enrols a product that does not exist: the sweep
// finds no sources, the screen shows a row that never decides anything, and
// nothing anywhere says the SKU was wrong.
async function sourcingAddPrompt(){
  const host = document.getElementById("srcpick");
  if(!host) return;
  host.style.display = "block";
  host.innerHTML = '<div class="cc" style="padding:14px"><span class="genspin"></span> Loading this account\'s live listings…</div>';
  await sourcingPickerLoad("");
}

async function sourcingPickerLoad(q){
  const host = document.getElementById("srcpick");
  if(!host) return;
  let j;
  try{ j = await (await fetch(_srcUrl("/sourcing/candidates","q="+encodeURIComponent(q||"")))).json(); }
  catch(e){ host.innerHTML = '<div class="cc" style="padding:14px;color:var(--red)">'+_sesc(String(e))+'</div>'; return; }
  if(!j || !j.ok){ host.innerHTML = '<div class="cc" style="padding:14px;color:var(--red)">'+_sesc((j&&j.error)||"Could not load")+'</div>'; return; }

  let h = '<div style="border:1px solid #26303f;border-radius:8px;padding:12px;margin-bottom:12px">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
    + '<b style="font-size:13px">Enrol a listing</b>'
    + '<span class="cc" style="font-size:11px">'+j.count+' live on this account</span>'
    + '<span style="flex:1"></span>'
    + '<input id="srcpickq" placeholder="filter by SKU or title" value="'+_sesc(q||"")+'" '
    + 'oninput="sourcingPickerFilter(this.value)" style="font-size:12px;padding:4px 8px;min-width:200px">'
    + '<button class="db-chip" onclick="sourcingPickerClose()">Close</button></div>';

  if(j.note){
    h += '<div class="cc" style="font-size:12px;padding:8px">'+_sesc(j.note)+'</div></div>';
    host.innerHTML = h; return;
  }

  h += '<div style="max-height:340px;overflow:auto">';
  (j.items||[]).forEach(function(it){
    h += '<div style="display:flex;gap:9px;align-items:center;font-size:11.5px;'
      +  'padding:6px 4px;border-top:1px solid #1c2531">'
      // The product, at a glance. A SKU is "10.06_3Days_B0081ZHHTS" and a title
      // is forty words of keywords; neither says what the thing is, and
      // enrolling the wrong one reprices it against somebody else's supplier.
      +  (it.img
          ? '<img src="'+_sesc(it.img)+'" loading="lazy" alt="" '
            + 'style="width:38px;height:38px;object-fit:contain;background:#0d1220;'
            + 'border-radius:5px;flex:0 0 auto">'
          : '<span style="width:38px;height:38px;border-radius:5px;flex:0 0 auto;'
            + 'background:#0d1220;display:inline-block"></span>')
      +  '<code style="min-width:150px">'+_sesc(it.sku)+'</code>'
      +  '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" '
      +  'title="'+_sesc(it.title)+'">'+_sesc(it.title||"(no title)")+'</span>'
      +  (/AFN|AMAZON|FBA/i.test(it.fulfillment||"")
          ? '<span class="db-chip" style="opacity:.6" title="Amazon holds this stock, so the repricer leaves it alone">FBA</span>'
          : '')
      +  '<span class="cc">'+_smoney(it.price)+'</span>'
      +  (it.enrolled
          ? '<span class="db-chip" style="background:#12303a;color:#6ac7e8">enrolled'
            + (it.sources? ' · '+it.sources+' source'+(it.sources===1?'':'s') : ' · no sources yet')+'</span>'
          : '<button class="db-chip" onclick="sourcingEnrolPicked('+_sarg(it.sku)+')">Enrol</button>')
      +  '</div>';
  });
  h += '</div></div>';
  host.innerHTML = h;
}

let _srcPickTimer = null;
function sourcingPickerFilter(v){
  clearTimeout(_srcPickTimer);
  _srcPickTimer = setTimeout(function(){ sourcingPickerLoad(v); }, 200);
}
function sourcingPickerClose(){
  const host = document.getElementById("srcpick");
  if(host){ host.style.display = "none"; host.innerHTML = ""; }
}

async function sourcingEnrolPicked(sku){
  try{
    const j = await (await fetch("/sourcing/enrol",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku})})).json();
    if(!j.ok){ toast(j.error||"Could not enrol"); return; }
    toast("Enrolled in dry run — add a supplier link next");
    await sourcingPickerLoad((document.getElementById("srcpickq")||{}).value||"");
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}

async function sourcingUnenrol(sku){
  if(!confirm("Stop watching "+sku+"? Its suppliers and history are kept.")) return;
  try{
    const j = await (await fetch("/sourcing/enrol",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku, enrolled:false})})).json();
    if(!j.ok){ toast(j.error||"failed"); return; }
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}

async function sourcingAddSourcePrompt(sku){
  const url = prompt("Paste the supplier's link for "+sku+".\n\neBay links are read "
                   + "through eBay's own API. Other sites are read only if they "
                   + "publish structured product data — the app will tell you if "
                   + "it cannot read one rather than guess a price.");
  if(!url) return;
  try{
    const j = await (await fetch("/sourcing/source/add",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku, url:url.trim()})})).json();
    if(!j.ok){ toast(j.error||"Could not add"); return; }
    toast("Supplier added — press “Re-read suppliers now” to check it");
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}

async function sourcingRemoveSource(sid){
  if(!confirm("Remove this supplier?")) return;
  try{
    const j = await (await fetch("/sourcing/source/remove",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({source_id:sid})})).json();
    if(!j.ok){ toast(j.error||"failed"); return; }
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}
