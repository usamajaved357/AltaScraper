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
// A sheet of costs. The FILE is sent; it is not parsed here.
//
// THERE USED TO BE A SECOND PARSER IN THIS FILE, and it read the wrong column.
// It looked for a cost under any of several names and the last of them was
// `price` -- which on an Amazon listings export is the SELLING price. Uploading
// one set every SKU's cost to what it sells for, so every product on the
// account showed a loss of roughly its own Amazon fee, silently and with no
// error anywhere. domain/cogs.COST_COLS does not accept a bare `price`, and
// never did; only the browser copy did.
//
// It was also the weaker reader in every other way: no spreadsheets, no
// currency symbols, no thousands separator, and it could not see whether a SKU
// matched anything on the account. domain/source_bulk.read_table does all of
// that and is what /cogs/upload_sheet already used. One reader (Rule 12), and
// it is the one that was right.
//
// TWO PASSES OVER THE SAME FILE. The first writes nothing and comes back with
// the real counts, so the confirmation quotes the reader that is about to do
// the work rather than a second opinion about it. The second does it.
function cogsUploadOpen(){
  const inp = document.getElementById("cogs_file");
  if(inp) inp.click();
}

function _cgPost(file, dry){
  const fd = new FormData();
  fd.append("file", file);
  if(typeof acctId === "function" && acctId()) fd.append("id", acctId());
  if(dry) fd.append("dry_run", "1");
  return fetch("/cogs/upload_sheet", {method: "POST", body: fd})
    .then(function(r){ return r.json(); });
}

/* What the file would do, in the words of the rows it could not use. Shown in
 * the confirmation, because "412 costs set" and "412 rows matched nothing" look
 * identical once the dialog is gone. */
function _cgSummary(rep){
  const bits = [];
  if(rep.skipped) bits.push(rep.skipped + " row" + (rep.skipped === 1 ? "" : "s")
    + " have no cost filled in and will be left alone.");
  // unmatched is specifically an ASIN-only row whose ASIN is on nothing here --
  // there is no SKU to write the cost against, so the row cannot be used at all.
  if(rep.unmatched) bits.push(rep.unmatched + " row" + (rep.unmatched === 1 ? "" : "s")
    + " give only an ASIN that is on nothing in this account, so there is no "
    + "SKU to put a cost on.");
  // unknown_sku is different and much easier to do by accident: the SKU was
  // typed, so the cost WILL be stored -- against something that has never been
  // listed or sold here. Usually a typo, and a silent one.
  if(rep.unknown_sku) bits.push(rep.unknown_sku + " SKU"
    + (rep.unknown_sku === 1 ? " is" : "s are")
    + " not on any listing or order in this account. The cost will still be "
    + "stored, but check for a typo.");
  const bad = (rep.rows || []).filter(function(r){
    return r.status === "not a number" || r.status === "refused"; });
  if(bad.length) bits.push(bad.length + " row" + (bad.length === 1 ? "" : "s")
    + " have a cost that could not be read: " + bad.slice(0, 3).map(function(r){
        return r.sku + " (" + r.detail + ")"; }).join("; ")
    + (bad.length > 3 ? " …" : ""));
  return bits.join("\n");
}

async function cogsUploadFile(input){
  const f = input && input.files && input.files[0];
  if(!f){ return; }
  try{
    const dry = await _cgPost(f, true);
    if(!dry || !dry.ok){
      // The server names the column it could not find, which is the only
      // useful thing to say about a file it will not read.
      toast((dry && dry.error) || "That file could not be read.");
      return;
    }
    if(!dry.set){
      toast("Nothing to set from that file. " + (_cgSummary(dry)
            || "No row had a cost in it."));
      return;
    }
    const cols = dry.columns || {};
    // Said BEFORE it happens, with the numbers, and naming which columns were
    // read -- the way to notice a file whose cost column is not what you think.
    if(!confirm("Set the cost on " + dry.set + " SKU"
                + (dry.set === 1 ? "" : "s") + "?\n\n"
                + "Reading “" + (cols.cost || "cost") + "” as the cost"
                + (cols.sku ? ", matched on “" + cols.sku + "”" : "")
                + (cols.asin ? " and “" + cols.asin + "”" : "") + ".\n"
                + (_cgSummary(dry) ? "\n" + _cgSummary(dry) + "\n" : "")
                + "\nThis overrides what the SKU says for those items, on this "
                + "account only. Every profit figure in the app uses it.")){
      return;
    }
    const j = await _cgPost(f, false);
    if(!j || !j.ok){ toast((j && j.error) || "Upload failed"); return; }
    // The cells redraw from the server's own report, not from what was sent,
    // so a row the server refused does not appear on screen as though it stuck.
    (j.rows || []).forEach(function(r){
      if(r.status !== "set") return;
      const v = Number(r.detail);
      if(!isFinite(v)) return;
      String(r.sku || "").split(",").forEach(function(s){
        s = s.trim(); if(s) COGS_LOCAL[s] = v;
      });
    });
    toast(j.note || ("Set " + j.set + " cost(s)"));
    if(typeof loadRows === "function") loadRows();
  }catch(e){ toast(String(e)); }
  finally{ input.value = ""; }
}
