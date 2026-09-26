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
       + 'border:1px solid var(--line,var(--line2));border-radius:6px;'
       + 'background:var(--bg,var(--panel2));color:inherit'
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

  // THE "ADD A PRODUCT" FORM WAS HERE, and was removed on the owner's
  // instruction (27 Sep 2026: "Remove the entire form at the bottom ... Delete
  // the whole section"). Products reach the queue by the spreadsheet drop zone
  // above. The /input/add route is left in place; nothing on this screen calls
  // it any more.

  // EMPTY: NOTHING AT ALL. The whole queue card -- its header controls
  // (filter, refresh, clear, generate now, "Check again") and its body -- is
  // hidden while nothing is queued, and comes back the moment something is
  // (.iq-empty, genflow.css). The one-line empty-queue message that stood in
  // for it was removed on the owner's instruction (27 Sep 2026): the drop zone
  // above already says what to do.
  const wrap = document.getElementById("inputsheetwrap");
  if(wrap) wrap.classList.toggle("iq-empty", !IQ.rows.length);
  if(!IQ.rows.length){
    body.innerHTML = "";
    return;
  }

  let h = '<div style="padding:10px 12px">';

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

/* inputQueueAdd() -- the "Add a product" form's submit -- went with the form
 * (the owner's instruction, 27 Sep 2026). */

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

// ---- REPLACED BY /input/upload (CSV/Excel) ---------------------------------
//
// Kept, commented, rather than deleted, so it can be restored by removing the
// comment markers. Its button is gone from the toolbar above the queue and its
// endpoint is commented out in routes/input_routes.py, so left live it would be
// a function calling a route that answers 404.
//
// Products reach this queue two ways now: the form below, and a CSV or Excel
// file dropped on the zone above it (static/js/inputupload.js).
//
// async function inputQueueImport(btn){
//   if(btn){ btn.disabled = true; btn.innerHTML = '<span class="genspin"></span> importing…'; }
//   try{
//     const j = await (await fetch("/input/import",{method:"POST",
//       headers:{"Content-Type":"application/json"}, body:"{}"})).json();
//     if(!j.ok){ toast(j.error||"Could not import"); return; }
//     toast("Imported "+(j.read||0)+" rows — "+(j.added||0)+" new, "+(j.updated||0)+" updated");
//     inputQueueLoad();
//   }catch(e){ toast(String(e)); }
//   finally{ if(btn){ btn.disabled=false; btn.innerHTML='<i class="ti ti-table-import"></i> Import from sheet'; } }
// }

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
