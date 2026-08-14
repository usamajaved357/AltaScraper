// ===================== WHAT THE STOCK COST =====================
// Click the COGS cell on any row, type a number, done. Or upload a sheet and
// set hundreds at once.
//
// WHERE THE NUMBER COMES FROM, AND WHY IT IS SHOWN
// Generated SKUs carry it: {cost}_{N}Days_{ASIN}. So most rows already know
// what they cost and nothing needs typing. But 0.00 means UNKNOWN, not free --
// build_sku writes it when it had no cost to write -- and hand-made SKUs
// ("46 pcs wrench") carry none at all. Those rows have NO cost, and every
// profit figure built on them has to say so rather than quietly assuming zero,
// because an item that appears to cost nothing looks infinitely profitable and
// is precisely the item someone would then order more of.
//
// So the cell shows one of three things and they are visibly different:
//   a number in plain text      read from the SKU
//   a number with a mark        typed by you, and it beats the SKU
//   "set" in muted text         nothing known -- click to say
//
// One resolver decides, server-side (domain/cogs.py). This is the way IN to it,
// not a second opinion about it.

function _cgEsc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// Costs typed here, so a cell can redraw without waiting for a reload.
let COGS_LOCAL = {};

function cogsOf(row){
  const sku = String((row && row.sku) || "");
  if(COGS_LOCAL[sku] !== undefined) return {cost: COGS_LOCAL[sku], source: "manual"};
  if(row && row.cogs !== undefined && row.cogs !== null && row.cogs !== "")
    return {cost: Number(row.cogs), source: row.cogs_source || "sku"};
  // Fall back to reading it off the SKU exactly as the server does: everything
  // before the first underscore, and only if it is a number ABOVE zero.
  const first = sku.split("_")[0];
  const v = Number(first);
  if(first && isFinite(v) && v > 0) return {cost: v, source: "sku"};
  return {cost: null, source: ""};
}

function cogsCell(row){
  const sku = String((row && row.sku) || "");
  const c = cogsOf(row);
  const sym = (typeof CUR_SYMBOL !== "undefined" && CUR_SYMBOL) || "";
  let inner;
  if(c.cost === null){
    inner = '<span class="cc" style="font-size:11px;opacity:.7">set</span>';
  }else{
    inner = '<span>' + _cgEsc(sym) + Number(c.cost).toFixed(2) + '</span>'
          + (c.source === "manual"
              ? '<span title="You typed this, so it beats what the SKU says" '
                + 'style="color:var(--accent);font-size:9px;vertical-align:super">•</span>'
              : '');
  }
  return '<td class="cogscell" style="white-space:nowrap;cursor:text" '
       + 'title="' + (c.source === "manual" ? "Your own figure — click to change"
                      : c.source === "sku" ? "Read from the SKU — click to override"
                      : "No cost known for this SKU — click to set one")
       + '" onclick="event.stopPropagation();cogsEdit(this,' + jsArg(sku) + ')">'
       + inner + '</td>';
}

function cogsEdit(td, sku){
  if(!td || td.querySelector("input")) return;
  const c = cogsOf({sku: sku, cogs: COGS_LOCAL[sku]});
  const was = td.innerHTML;
  td.innerHTML = '<input type="text" value="'
    + (c.cost === null ? "" : Number(c.cost).toFixed(2)) + '" '
    + 'placeholder="0.00" style="width:74px;padding:3px 5px;font-size:11.5px;'
    + 'text-align:right;border:1px solid var(--accent);border-radius:5px;'
    + 'background:var(--bg,#0e1116);color:inherit">';
  const inp = td.querySelector("input");
  inp.focus(); inp.select();

  let done = false;
  const finish = async function(save){
    if(done) return;
    done = true;
    if(!save){ td.innerHTML = was; return; }
    const raw = String(inp.value || "").trim();
    // EMPTY CLEARS THE OVERRIDE rather than setting zero. "I do not know" and
    // "it is free" are different answers and only one of them is ever true.
    const val = raw === "" ? null : Number(raw.replace(/[^0-9.]/g, ""));
    if(val !== null && (!isFinite(val) || val < 0)){
      toast("That is not a cost."); td.innerHTML = was; return;
    }
    td.innerHTML = '<span class="cc" style="font-size:11px">saving…</span>';
    try{
      const j = await (await fetch("/cogs/set",{method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:sku, cost:val})})).json();
      if(!j || !j.ok){ toast((j&&j.error)||"Could not save that cost"); td.innerHTML = was; return; }
      if(val === null) delete COGS_LOCAL[sku]; else COGS_LOCAL[sku] = val;
      // Redraw just this cell; the whole table does not need rebuilding.
      const fresh = document.createElement("tbody");
      fresh.innerHTML = "<tr>" + cogsCell({sku: sku, cogs: COGS_LOCAL[sku],
                                           cogs_source: val === null ? "" : "manual"}) + "</tr>";
      const cell = fresh.querySelector("td");
      if(cell) td.innerHTML = cell.innerHTML;
      toast(val === null ? "Cleared — back to what the SKU says"
                         : "Cost set for " + sku);
    }catch(e){ toast(String(e)); td.innerHTML = was; }
  };
  inp.addEventListener("blur", function(){ finish(true); });
  inp.addEventListener("keydown", function(ev){
    if(ev.key === "Enter"){ ev.preventDefault(); finish(true); }
    if(ev.key === "Escape"){ ev.preventDefault(); finish(false); }
  });
}

// ---- bulk ---------------------------------------------------------------
// A sheet of costs, parsed in the browser and posted as rows. CSV because it is
// what every spreadsheet exports and needs no library; the columns are found by
// NAME rather than by position, since nobody keeps them in a fixed order.
function cogsUploadOpen(){
  const inp = document.getElementById("cogs_file");
  if(inp) inp.click();
}

function _cgSplit(line){
  // Handles quoted fields containing commas, which product names invariably do.
  const out = []; let cur = "", q = false;
  for(let i = 0; i < line.length; i++){
    const ch = line[i];
    if(q){
      if(ch === '"' && line[i+1] === '"'){ cur += '"'; i++; }
      else if(ch === '"'){ q = false; }
      else cur += ch;
    }else{
      if(ch === '"') q = true;
      else if(ch === ',' || ch === '\t') { out.push(cur); cur = ""; }
      else cur += ch;
    }
  }
  out.push(cur);
  return out.map(s => s.trim());
}

async function cogsUploadFile(input){
  const f = input && input.files && input.files[0];
  if(!f) return;
  const text = await f.text();
  const lines = text.split(/\r?\n/).filter(l => l.trim());
  if(lines.length < 2){ toast("That file has no rows in it."); input.value=""; return; }

  const head = _cgSplit(lines[0]).map(h => h.toLowerCase().replace(/[^a-z]/g, ""));
  const find = function(names){
    for(const n of names){ const i = head.indexOf(n); if(i >= 0) return i; }
    return -1;
  };
  // By NAME, and accepting what people actually call these columns.
  const iSku  = find(["sku", "sellersku", "merchantsku", "msku"]);
  const iCost = find(["cost", "cogs", "costofgoods", "unitcost", "buyprice",
                      "sourcecost", "price"]);
  if(iSku < 0 || iCost < 0){
    toast("Could not find a SKU column and a cost column. The header row needs "
          + "something like 'SKU' and 'COGS'. Found: " + head.join(", "));
    input.value = ""; return;
  }

  const rows = [], bad = [];
  lines.slice(1).forEach(function(l){
    const cells = _cgSplit(l);
    const sku = (cells[iSku] || "").trim();
    const raw = (cells[iCost] || "").replace(/[^0-9.\-]/g, "").trim();
    if(!sku) return;
    const v = Number(raw);
    if(raw === "" || !isFinite(v) || v < 0){ bad.push(sku); return; }
    rows.push({sku: sku, cost: v});
  });

  if(!rows.length){
    toast("No usable rows — every cost was blank or not a number."); input.value=""; return;
  }
  // Said BEFORE it happens, with the number. A bulk overwrite of what things
  // cost changes every profit figure in the app.
  if(!confirm("Set the cost on " + rows.length + " SKU" + (rows.length===1?"":"s") + "?"
              + (bad.length ? "\n\n" + bad.length + " row(s) had no usable cost and "
                              + "will be skipped." : "")
              + "\n\nThis overrides what the SKU says for those items, on this "
              + "account only. Every profit figure in the app uses it.")){
    input.value = ""; return;
  }
  try{
    const j = await (await fetch("/cogs/upload",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({rows: rows})})).json();
    if(!j || !j.ok){ toast((j&&j.error)||"Upload failed"); return; }
    rows.forEach(function(r){ COGS_LOCAL[r.sku] = r.cost; });
    toast("Set " + (j.updated || j.count || rows.length) + " cost(s)"
          + (bad.length ? ", skipped " + bad.length : ""));
    if(typeof loadRows === "function") loadRows();
  }catch(e){ toast(String(e)); }
  finally{ input.value = ""; }
}
