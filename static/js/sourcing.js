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
  try{ j = await (await fetch("/sourcing/list")).json(); }
  catch(e){ body.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">Could not load: '+_sesc(String(e))+'</div>'; return; }
  if(!j || !j.ok){
    body.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">'+_sesc((j&&j.error)||"Could not load")+'</div>';
    return;
  }
  SRC_ROWS = j.rows || [];
  SRC_RULE = j.rule || j.defaults || {};
  sourcingRender(j);
}

function sourcingRender(j){
  const body = document.getElementById("srcbody");
  const c = j.counts || {};
  let h = "";

  // The standing statement of what this screen is NOT doing. It sits at the top
  // rather than in a footnote because "is this live?" is the only question that
  // really matters while it is being set up.
  h += '<div class="cc" style="font-size:12px;margin:2px 0 12px;padding:9px 11px;'
    +  'border:1px solid #26403a;background:#10231f;border-radius:6px">'
    +  '<b>Dry run.</b> Nothing here changes a live listing. The app reads your '
    +  'suppliers every 4 hours, works out what it would do, and writes it down. '
    +  'Read this for a while before it is armed &mdash; if a decision looks wrong '
    +  'here, it would have been wrong on Amazon.</div>';

  h += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">'
    +  '<button class="db-chip" onclick="sourcingCheckNow(this)">'
    +  '<i class="ti ti-refresh"></i> Re-read suppliers now</button>'
    +  '<button class="db-chip" onclick="sourcingAddPrompt()">'
    +  '<i class="ti ti-plus"></i> Enrol a SKU</button>'
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
      headers:{"Content-Type":"application/json"}, body:"{}"})).json();
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

async function sourcingAddPrompt(){
  const sku = prompt("Which SKU should the repricer watch?\n\nIt will only ever "
                   + "touch SKUs you enrol here, one at a time.");
  if(!sku) return;
  try{
    const j = await (await fetch("/sourcing/enrol",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku:sku.trim()})})).json();
    if(!j.ok){ toast(j.error||"Could not enrol"); return; }
    toast("Enrolled in dry run"); sourcingLoad();
  }catch(e){ toast(String(e)); }
}

async function sourcingUnenrol(sku){
  if(!confirm("Stop watching "+sku+"? Its suppliers and history are kept.")) return;
  try{
    const j = await (await fetch("/sourcing/enrol",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku:sku, enrolled:false})})).json();
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
      body:JSON.stringify({sku:sku, url:url.trim()})})).json();
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
      body:JSON.stringify({source_id:sid})})).json();
    if(!j.ok){ toast(j.error||"failed"); return; }
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}
