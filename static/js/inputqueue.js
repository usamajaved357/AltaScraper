// ===================== THE PRODUCT QUEUE =====================
// What the generator will turn into listings, editable here.
//
// WHY THIS REPLACED A READ-ONLY SHEET VIEWER
// The Generate screen used to show the Google input sheet and nothing more --
// you could look at it, and to change anything you left the app, opened Google,
// edited, came back and pressed Import. The queue itself already lived in the
// database; only the way IN was still a spreadsheet.
//
// So the spreadsheet is optional now rather than merely imported. Paste the
// links here and press Generate. Import from a sheet still works, unchanged,
// for anyone who prefers it -- and both fill the SAME queue, so a workspace can
// be fed either way or both, and the generator neither knows nor cares which.
//
// Nothing here reaches Amazon. This is the list of things to make, not the
// making of them.

let IQ = {rows: [], busy: false, editing: null};

function _iqEsc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// The columns the queue actually has, in the order they matter when you are
// adding a product by hand rather than reading a spreadsheet.
const IQ_COLS = [
  {k:"ebay_url",       t:"Source link",  ph:"eBay item link — where you buy it", wide:1},
  {k:"amazon_url",     t:"Amazon / ASIN", ph:"Competitor ASIN or link (optional)"},
  {k:"item_name",      t:"Name",         ph:"What it is (optional)", wide:1},
  {k:"source_cost",    t:"Cost",         ph:"9.99", num:1},
  {k:"selling_price",  t:"Sell at",      ph:"auto", num:1},
  {k:"handling_time",  t:"Days",         ph:"3", num:1},
  {k:"upc",            t:"Barcode",      ph:"only a real one", num:0},
];

async function inputQueueLoad(){
  const body = document.getElementById("inputsheet_body");
  if(!body) return;
  body.innerHTML = '<div class="cc" style="padding:16px;opacity:.7">'
    + '<span class="genspin"></span> Loading the queue…</div>';
  try{
    const j = await (await fetch("/input/rows")).json();
    IQ.rows = (j && j.rows) || [];
  }catch(e){
    body.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">'
      + _iqEsc(String(e)) + '</div>';
    return;
  }
  inputQueueRender();
}

function _iqField(c, val, id){
  const v = _iqEsc(val || "");
  return '<input data-col="'+c.k+'" data-id="'+(id||"")+'" value="'+v+'" '
       + 'placeholder="'+_iqEsc(c.ph||"")+'" '
       + (id ? 'onchange="inputQueueSave('+id+',this)" ' : '')
       + 'style="width:100%;box-sizing:border-box;padding:5px 7px;font-size:11.5px;'
       + 'border:1px solid var(--line,#2a2f3a);border-radius:6px;'
       + 'background:var(--bg,#0e1116);color:inherit'
       + (c.num ? ';text-align:right' : '') + '">';
}

function inputQueueRender(){
  const body = document.getElementById("inputsheet_body");
  const meta = document.getElementById("inputsheet_meta");
  if(!body) return;
  if(meta){
    const bySheet = IQ.rows.filter(r => (r.source||"") === "sheet").length;
    const byHand  = IQ.rows.length - bySheet;
    meta.textContent = IQ.rows.length + " queued"
      + (IQ.rows.length ? " · " + byHand + " added here, " + bySheet + " from a sheet" : "");
  }

  let h = '<div style="padding:10px 12px">';

  // ---- add a product -------------------------------------------------
  // The brand card, not a full accent outline. A bright border says "this is
  // the important thing on the page", and on a screen whose important thing is
  // Generate, an add-form outlined in the accent colour outshouts it. The
  // emphasis belongs on the button, which already has it.
  h += '<div class="panelcard" style="margin-bottom:12px">'
    +  '<p class="paneltitle" style="font-size:12.5px;line-height:18px;margin-bottom:7px">'
    +  '<i class="ti ti-plus"></i> Add a product</p>'
    +  '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:7px">';
  IQ_COLS.forEach(function(c){
    h += '<div'+(c.wide?' style="grid-column:span 2"':'')+'>'
      +  '<div class="cc" style="font-size:10px;margin-bottom:2px">'+_iqEsc(c.t)+'</div>'
      +  '<input id="iq_new_'+c.k+'" placeholder="'+_iqEsc(c.ph||"")+'" '
      +  'onkeydown="if(event.key===\'Enter\')inputQueueAdd()" '
      +  'style="width:100%;box-sizing:border-box;padding:6px 8px;font-size:12px;'
      +  'border:1px solid var(--line,#2a2f3a);border-radius:6px;'
      +  'background:var(--bg,#0e1116);color:inherit'+(c.num?';text-align:right':'')+'">'
      +  '</div>';
  });
  h += '</div>'
    +  '<div style="display:flex;gap:8px;align-items:center;margin-top:9px;flex-wrap:wrap">'
    +  '<button class="db-chip primary" onclick="inputQueueAdd()">'
    +  '<i class="ti ti-plus"></i> Add to the queue</button>'
    +  '<span class="cc" style="font-size:11px">Then press <b>Generate</b> above. '
    +  'Leave <b>Sell at</b> empty and the app prices it from the cost and Amazon’s fees.</span>'
    +  '</div></div>';

  // ---- what is queued -------------------------------------------------
  if(!IQ.rows.length){
    h += '<div class="cc" style="padding:18px;border:1px dashed #2a3446;border-radius:8px;'
      +  'font-size:12.5px">Nothing queued yet. Add a product above, or bring in a '
      +  'spreadsheet with <b>Import from sheet</b> — both fill the same queue.</div>';
    body.innerHTML = h + '</div>';
    return;
  }

  h += '<div style="overflow-x:auto"><table class="kv" style="width:100%;min-width:760px">'
    +  '<thead><tr>';
  IQ_COLS.forEach(function(c){
    h += '<th style="text-align:left;font-size:10.5px;padding:5px 6px;white-space:nowrap">'
      +  _iqEsc(c.t)+'</th>';
  });
  h += '<th style="width:34px"></th></tr></thead><tbody>';
  IQ.rows.forEach(function(r){
    h += '<tr data-iqrow="'+r.id+'">';
    IQ_COLS.forEach(function(c){
      h += '<td style="padding:3px 4px'+(c.wide?';min-width:190px':'')+'">'
        +  _iqField(c, r[c.k], r.id)+'</td>';
    });
    h += '<td style="padding:3px 4px;text-align:center">'
      +  '<button class="ib" title="Remove this product from the queue" '
      +  'onclick="inputQueueDelete('+r.id+')" style="color:var(--red)">'
      +  '<i class="ti ti-trash"></i></button></td></tr>';
  });
  h += '</tbody></table></div>';
  h += '<div class="cc" style="font-size:11px;margin-top:8px">'
    +  'Changes save as you leave each box. Nothing here has been sent anywhere — '
    +  'this is the list of things to make.</div>';
  body.innerHTML = h + '</div>';
}

async function inputQueueAdd(){
  const p = {};
  IQ_COLS.forEach(function(c){
    const el = document.getElementById("iq_new_"+c.k);
    p[c.k] = (el && el.value || "").trim();
  });
  try{
    const j = await (await fetch("/input/add",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(p)})).json();
    if(!j.ok){ toast(j.error||"Could not add it"); return; }
    IQ_COLS.forEach(function(c){
      const el = document.getElementById("iq_new_"+c.k);
      if(el) el.value = "";
    });
    toast("Added — "+(j.count||0)+" queued");
    inputQueueLoad();
  }catch(e){ toast(String(e)); }
}

async function inputQueueSave(id, el){
  if(!el) return;
  const col = el.getAttribute("data-col");
  const body = {id: id};
  body[col] = el.value;
  el.style.borderColor = "var(--accent)";
  try{
    const j = await (await fetch("/input/update",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body)})).json();
    // Green on saved, red on refused -- an edit that silently did not stick is
    // the worst outcome for a field the generator is about to read.
    el.style.borderColor = j && j.ok ? "var(--ok,#8fd694)" : "var(--red)";
    if(!(j && j.ok)) toast(j.error||"That change did not save");
    setTimeout(function(){ el.style.borderColor = "var(--line,#2a2f3a)"; }, 1200);
  }catch(e){
    el.style.borderColor = "var(--red)";
    toast(String(e));
  }
}

async function inputQueueDelete(id){
  const row = IQ.rows.filter(r => r.id === id)[0] || {};
  const what = row.item_name || row.ebay_url || row.competitor_asin || ("row " + id);
  if(!await uiConfirm("Remove this from the queue?\n\n" + what
              + "\n\nIt is only removed from the list of things to make — nothing "
              + "already generated is touched.")) return;
  try{
    const j = await (await fetch("/input/delete",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:id})})).json();
    if(!j.ok){ toast(j.error||"Could not remove it"); return; }
    inputQueueLoad();
  }catch(e){ toast(String(e)); }
}

async function inputQueueImport(btn){
  if(btn){ btn.disabled = true; btn.innerHTML = '<span class="genspin"></span> importing…'; }
  try{
    const j = await (await fetch("/input/import",{method:"POST",
      headers:{"Content-Type":"application/json"}, body:"{}"})).json();
    if(!j.ok){ toast(j.error||"Could not import"); return; }
    toast("Imported "+(j.read||0)+" rows — "+(j.added||0)+" new, "+(j.updated||0)+" updated");
    inputQueueLoad();
  }catch(e){ toast(String(e)); }
  finally{ if(btn){ btn.disabled=false; btn.innerHTML='<i class="ti ti-table-import"></i> Import from sheet'; } }
}

function filterInputSheet(){
  const q = ((document.getElementById("inputsheet_filter")||{}).value||"")
              .toLowerCase().trim();
  const rows = document.querySelectorAll("[data-iqrow]");
  Array.prototype.forEach.call(rows, function(tr){
    if(!q){ tr.style.display=""; return; }
    let hay = "";
    Array.prototype.forEach.call(tr.querySelectorAll("input"), function(i){
      hay += " " + i.value.toLowerCase();
    });
    tr.style.display = hay.indexOf(q) >= 0 ? "" : "none";
  });
}

// The old name, kept so the Refresh button and anything else that called it
// keeps working.
function loadInputSheet(){ return inputQueueLoad(); }
