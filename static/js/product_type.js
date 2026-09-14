/* static/js/product_type.js — Amazon's product types, from the listing screens.
 *
 *     "i see a very limited products type to select from the pdp in the app"
 *     "fix the product types from amazon, and build the search"
 *
 * TWO THINGS, both asking Amazon rather than a list the app keeps:
 *
 *   ptSearchBox   under the product-type box on a listing. Click into it and it
 *                 asks Amazon what a product with THIS TITLE is (measured: the
 *                 camping table's title returns exactly TABLE); type words and it
 *                 searches Amazon's product types for them instead.
 *
 *   ptFixDrafts   the toolbar button. Every unsent draft with a competitor ASIN
 *                 is checked against that ASIN's type in Amazon's catalogue,
 *                 and the differences are SHOWN before anything is saved.
 *
 * NOTHING HERE WRITES A FIELD ITSELF. A chosen type is saved by editField, the
 * one function that writes a listing field (Rule 12), exactly as picking from
 * the dropdown always did. The server routes are routes/product_type_routes.py.
 */

const PT_SEARCH_CACHE = {};      // "mkt|title|q" -> reply, for this page load

function _ptMkt(r){
  try{ if(typeof rowMkt === "function") return rowMkt(r); }catch(e){}
  return (typeof WS_MARKET !== "undefined" && WS_MARKET) ? String(WS_MARKET).toUpperCase() : "UK";
}

function ptSearchBox(sku, r){
  const id = "ptsx_" + sid(sku);
  return '<div class="ptsx" style="margin-top:6px">'
    + '<input id="' + id + '" class="ed" type="text" autocomplete="off" style="width:100%"'
    + ' placeholder="Search Amazon’s product types (click for suggestions from the title)"'
    + ' onfocus="ptSearchFocus(\'' + esc(sku) + '\')"'
    + ' oninput="ptSearchInput(\'' + esc(sku) + '\')">'
    + '<div id="' + id + '_out" class="cc" style="font-size:12px;margin-top:4px"></div>'
    + '</div>';
}

function _ptRow(sku){
  return (typeof ROWS !== "undefined") ? ROWS.find(x => String(x.sku) === String(sku)) : null;
}

async function _ptSearch(sku, title, q){
  const out = document.getElementById("ptsx_" + sid(sku) + "_out");
  if(!out) return;
  const r = _ptRow(sku) || {};
  const mkt = _ptMkt(r);
  const key = mkt + "|" + (title || "") + "|" + (q || "");
  out.textContent = "Asking Amazon…";
  let j = PT_SEARCH_CACHE[key];
  if(!j){
    try{
      const url = acctUrl("/product_types/search?marketplace=" + encodeURIComponent(mkt)
        + (title ? "&title=" + encodeURIComponent(title) : "")
        + (q ? "&q=" + encodeURIComponent(q) : ""));
      j = await (await fetch(url)).json();
    }catch(e){
      j = {ok:false, error:"could not reach the app"};
    }
    if(j && j.ok) PT_SEARCH_CACHE[key] = j;
  }
  // The box may have been re-typed while this was out; only paint the latest.
  const box = document.getElementById("ptsx_" + sid(sku));
  if(box && q && box.value.trim() !== q) return;
  if(!j || !j.ok){
    out.innerHTML = (j && j.status === "denied") || (j && j.denied)
      ? "Amazon does not let this account search its product types, so only the list above is available."
      : "Couldn’t search Amazon: " + esc((j && j.error) || "unknown error");
    return;
  }
  if(!(j.types || []).length){
    out.textContent = title ? "Amazon had no suggestion for this title — type some words instead."
                            : "Amazon has no product type matching those words.";
    return;
  }
  const cur = String(r.product_type || "").toUpperCase();
  out.innerHTML = (title ? "Amazon suggests for this title: " : "Amazon’s product types: ")
    + j.types.slice(0, 30).map(t =>
        '<button type="button" class="db-chip' + (t.name === cur ? " go" : "") + '"'
        + ' style="margin:2px 4px 2px 0" title="' + esc(t.display_name) + '"'
        + ' onclick="ptPick(\'' + esc(sku) + '\',\'' + esc(t.name) + '\')">'
        + esc(t.name) + (t.name === cur ? " ✓" : "") + '</button>'
      ).join("");
}

function ptSearchFocus(sku){
  const box = document.getElementById("ptsx_" + sid(sku));
  if(box && box.value.trim()) return;           // they are searching words
  const r = _ptRow(sku) || {};
  const title = String(r.title || "").trim();
  if(title) _ptSearch(sku, title, "");
}

let _PT_TIMER = null;
function ptSearchInput(sku){
  clearTimeout(_PT_TIMER);
  _PT_TIMER = setTimeout(function(){
    const box = document.getElementById("ptsx_" + sid(sku));
    const q = box ? box.value.trim() : "";
    if(q.length >= 2) _ptSearch(sku, "", q);
    else if(!q) ptSearchFocus(sku);
  }, 450);
}

/* Choosing a suggestion is choosing it in the dropdown: the same select, the
 * same onchange, so the save, the warning and the schema reload are the ones
 * that already exist. */
function ptPick(sku, name){
  const sel = document.getElementById("pt_" + sid(sku));
  if(!sel) return;
  if(![...sel.options].some(o => o.value === name)){
    const o = document.createElement("option");
    o.value = name; o.textContent = name;
    sel.insertBefore(o, sel.firstChild);
  }
  sel.value = name;
  sel.dispatchEvent(new Event("change"));
}

// ---- the toolbar button ------------------------------------------------------

async function ptFixDrafts(){
  const aid = (typeof acctId === "function") ? acctId() : "";
  if(!aid){ toast("Open an account first"); return; }
  let cancelled = false;
  _dlgOpen({title:"Fix product types from Amazon",
            html:'<div id="ptfix_prog" style="font-size:12.5px">Finding drafts…</div>',
            cancelValue:null, buttons:[{label:"Cancel", value:null}]})
    .then(function(){ cancelled = true; });
  const prog = t => { const el = document.getElementById("ptfix_prog"); if(el) el.textContent = t; };

  let drafts = [];
  try{
    const j = await (await fetch(acctUrl("/product_types/drafts"))).json();
    if(!j.ok) throw new Error(j.error || "refused");
    drafts = j.drafts || [];
  }catch(e){
    await uiAlert("Couldn’t list the drafts: " + e.message);
    return;
  }
  if(!drafts.length){
    await uiAlert("No unsent drafts with a competitor ASIN in this account — nothing to check.");
    return;
  }

  // A few drafts per request, per marketplace. The verdicts come back decided
  // -- listing/product_type.compare() is the one definition of "change".
  const byMkt = {};
  drafts.forEach(d => {
    const m = d.marketplace || _ptMkt({});
    (byMkt[m] = byMkt[m] || []).push(d);
  });
  const rows = [];
  let done = 0, denied = false;
  for(const mkt of Object.keys(byMkt)){
    const list = byMkt[mkt];
    for(let i = 0; i < list.length; i += 15){
      if(cancelled) return;
      prog("Asking Amazon about " + drafts.length + " draft(s)… " + done + " done");
      const batch = list.slice(i, i + 15);
      let j;
      try{
        j = await (await fetch("/product_types/lookup", {method:"POST",
          headers:{"Content-Type":"application/json"},
          body: JSON.stringify(acctBody({marketplace: mkt, skus: batch.map(d => d.sku)}))})).json();
      }catch(e){ j = {ok:false, error:"could not reach the app"}; }
      if(j.ok){
        (j.rows || []).forEach(r => rows.push(r));
        if(j.denied) denied = true;
      }else{
        if(j.denied) denied = true;
        batch.forEach(d => rows.push({sku:d.sku, title:d.title, asin:d.asin,
          current:d.product_type, amazon:"", verdict:"not_checked", why:j.error || "failed"}));
      }
      done += batch.length;
    }
  }
  if(cancelled) return;
  const changes = rows.filter(r => r.verdict === "change");
  const same = rows.filter(r => r.verdict === "same").length;
  const unchecked = rows.filter(r => r.verdict === "not_checked");

  let html = '<p style="margin:0 0 8px;font-size:12.5px">Checked ' + rows.length
    + ' unsent draft(s) against their competitor ASIN in Amazon’s catalogue.</p>'
    + '<p style="margin:0 0 8px;font-size:12.5px"><b>' + changes.length + '</b> to change'
    + ' · ' + same + ' already right · ' + unchecked.length + ' couldn’t check</p>';
  if(denied){
    html += '<p style="margin:0 0 8px;font-size:12px" class="cwarn">Amazon refused this account’s catalogue access, so those drafts were not checked and will not be changed.</p>';
  }
  if(changes.length){
    html += '<div style="max-height:40vh;overflow-y:auto;font-size:12px;border-top:1px solid var(--line2)">'
      + changes.map(r => '<div style="padding:5px 0;border-bottom:1px solid var(--line2)">'
          + '<div style="font-family:monospace">' + esc(r.sku) + '</div>'
          + '<div class="cc">' + esc(String(r.title || "").slice(0, 70)) + '</div>'
          + '<div>' + esc(r.current || "(blank)") + ' → <b>' + esc(r.amazon) + '</b></div></div>'
        ).join("") + '</div>'
      + '<p style="margin:8px 0 0;font-size:12px" class="cc">A different type can ask for different details. Run Preview on these afterwards to see what Amazon needs.</p>';
  }
  if(unchecked.length && !denied){
    html += '<details style="margin-top:8px;font-size:12px"><summary>Couldn’t check (' + unchecked.length + ')</summary>'
      + unchecked.map(r => '<div>' + esc(r.sku) + ' — ' + esc(r.why) + '</div>').join("") + '</details>';
  }
  const go = await _dlgOpen({title:"Fix product types from Amazon", html:html, cancelValue:false,
    buttons: changes.length
      ? [{label:"Cancel", value:false}, {label:"Apply " + changes.length + " change(s)", tone:"go", primary:true, value:true}]
      : [{label:"Close", tone:"go", primary:true, value:false}]});
  if(!go) return;

  let ok = 0; const failed = [];
  for(const r of changes){
    const j = await editField(r.sku, "col", "Product Type", r.amazon);
    if(j && j.ok) ok++; else failed.push(r.sku + ": " + ((j && j.error) || "save failed"));
  }
  try{
    await fetch("/product_types/recheck", {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify(acctBody({}))});
  }catch(e){ /* the saves stand; warnings catch up on the next generate */ }
  if(typeof refreshView === "function"){ try{ refreshView(); }catch(e){} }
  await uiAlert("Changed " + ok + " product type(s)."
    + (failed.length ? "\n\nNot saved:\n" + failed.join("\n") : ""));
}
