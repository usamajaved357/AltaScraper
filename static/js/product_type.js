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
//
//     "i selected 64 listings and clicked on fix product types it shows check 2
//      unsent draft(s) ... 2 already right 0 couldn't check"
//
// It read the whole account whatever was ticked, dropped every draft with no
// competitor ASIN and every submitted one, and never said so -- so 62 left out
// read as "2 already right". Now it takes the ticked listings, asks Amazon's
// product-type search about a draft with no ASIN by its title, lets you include
// submitted listings on purpose, and names every listing it leaves out and why.
// The list and the reasons are decided on the server
// (listing/product_type.candidates); this only shows them and asks.

const PT_SKIP_WHY = {
  on_amazon:      "already live on Amazon — its type is Amazon’s now",
  submitted:      "already submitted to Amazon — left out",
  parent:         "a variation parent, not a product",
  queued:         "not generated yet",
  nothing_to_ask: "no competitor ASIN and no title — nothing to ask Amazon about",
  not_found:      "ticked, but not a draft in this account",
};

/* The listings left out, grouped by reason, in the order the reasons first
 * appear. Pure, so it can be run without a page. */
function ptSkipGroups(skipped){
  const order = [], groups = {};
  (skipped || []).forEach(function(s){
    const k = (s && s.reason) || "other";
    if(!groups[k]){ groups[k] = []; order.push(k); }
    groups[k].push(s);
  });
  return order.map(function(k){ return {reason: k, why: PT_SKIP_WHY[k] || k, items: groups[k]}; });
}

/* A change is ticked for you only when there is ONE answer: the competitor
 * ASIN's type, or a title search that came back with a single type. When the
 * search offered several, you choose -- nothing is chosen on your behalf. */
function ptPreticked(r){
  if(!r || r.verdict !== "change") return false;
  if(r.method === "title") return (r.options || []).length <= 1;
  return true;
}

/* Read the results dialog: the ticked rows, each with the type chosen for it. */
function ptReadChoices(wrap, changes){
  const out = [];
  const rows = wrap ? wrap.querySelectorAll(".ptfix-row") : [];
  Array.prototype.forEach.call(rows, function(row){
    const tick = row.querySelector(".ptfix-tick");
    if(!tick || !tick.checked) return;
    const base = (changes || [])[+row.getAttribute("data-i")];
    if(!base) return;
    const pick = row.querySelector(".ptfix-pick");
    const value = pick ? String(pick.value || "").trim().toUpperCase() : String(base.amazon || "");
    if(!value) return;
    out.push(Object.assign({}, base, {amazon: value}));
  });
  return out;
}

function _ptSkipHtml(skipped){
  const groups = ptSkipGroups(skipped);
  if(!groups.length) return "";
  const n = (skipped || []).length;
  return '<details style="margin-top:8px;font-size:12px"' + (n <= 12 ? " open" : "") + '>'
    + '<summary><b>' + n + '</b> left out, and why</summary>'
    + groups.map(function(g){
        return '<div style="margin:6px 0 2px"><b>' + g.items.length + '</b> — ' + esc(g.why) + '</div>'
          + '<div class="cc" style="font-family:monospace;font-size:11px;line-height:1.5">'
          + g.items.map(function(s){ return esc(s.sku); }).join("<br>") + '</div>';
      }).join("")
    + '</details>';
}

async function _ptList(skus, includeSubmitted){
  try{
    const j = await (await fetch("/product_types/drafts", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify(acctBody({skus: skus || [], include_submitted: !!includeSubmitted}))})).json();
    if(!j || !j.ok) throw new Error((j && j.error) || "refused");
    return {drafts: j.drafts || [], skipped: j.skipped || []};
  }catch(e){
    await uiAlert("Couldn’t list the drafts: " + e.message);
    return null;
  }
}

async function ptFixDrafts(){
  const aid = (typeof acctId === "function") ? acctId() : "";
  if(!aid){ toast("Open an account first"); return; }

  // THE LISTINGS YOU TICKED, when there are any -- otherwise the whole account.
  const picked = (typeof selectedSkus === "function") ? selectedSkus() : [];
  let listing = await _ptList(picked, false);
  if(!listing) return;

  // SUBMITTED LISTINGS ONLY ON PURPOSE. They are left out by default -- Amazon
  // holds them -- but "your product type has been updated" is the note Amazon
  // attaches when it accepts one, so bringing the app's type into line with
  // Amazon's is a reason to include them. Asked, never assumed.
  let includeSubmitted = false;
  const subs = listing.skipped.filter(function(s){ return s.reason === "submitted"; });
  if(subs.length){
    includeSubmitted = !!(await _dlgOpen({title:"Fix product types from Amazon",
      html:'<p style="margin:0 0 8px;font-size:12.5px"><b>' + subs.length + '</b> of '
        + (picked.length ? "the listings you ticked" : "this account’s listings") + ' '
        + (subs.length === 1 ? "is" : "are") + ' already <b>submitted</b> to Amazon.</p>'
        + '<p style="margin:0;font-size:12.5px" class="cc">They are left out unless you include them. '
        + 'Include them when Amazon has warned that it changed their product type, so this app’s '
        + 'type matches Amazon’s.</p>',
      cancelValue:false,
      buttons:[{label:"Leave them out", value:false},
               {label:"Include them", tone:"go", primary:true, value:true}]}));
    if(includeSubmitted){
      listing = await _ptList(picked, true);
      if(!listing) return;
    }
  }
  const drafts = listing.drafts, skipped = listing.skipped;
  if(!drafts.length){
    await _dlgOpen({title:"Fix product types from Amazon",
      html:'<p style="margin:0 0 8px;font-size:12.5px">Nothing to check'
        + (picked.length ? " among the " + picked.length + " listing(s) you ticked" : " in this account") + '.</p>'
        + _ptSkipHtml(skipped),
      cancelValue:null, buttons:[{label:"Close", tone:"go", primary:true, value:null}]});
    return;
  }

  let cancelled = false;
  _dlgOpen({title:"Fix product types from Amazon",
            html:'<div id="ptfix_prog" style="font-size:12.5px">Asking Amazon…</div>',
            cancelValue:null, buttons:[{label:"Cancel", value:null}]})
    .then(function(){ cancelled = true; });
  const prog = t => { const el = document.getElementById("ptfix_prog"); if(el) el.textContent = t; };

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
          body: JSON.stringify(acctBody({marketplace: mkt, skus: batch.map(d => d.sku),
                                         include_submitted: includeSubmitted}))})).json();
      }catch(e){ j = {ok:false, error:"could not reach the app"}; }
      if(j.ok){
        (j.rows || []).forEach(r => rows.push(r));
        if(j.denied) denied = true;
      }else{
        if(j.denied) denied = true;
        batch.forEach(d => rows.push({sku:d.sku, title:d.title, asin:d.asin, method:d.method,
          current:d.product_type, amazon:"", verdict:"not_checked", why:j.error || "failed", options:[]}));
      }
      done += batch.length;
    }
  }
  if(cancelled) return;
  const changes = rows.filter(r => r.verdict === "change");
  const same = rows.filter(r => r.verdict === "same").length;
  const unchecked = rows.filter(r => r.verdict === "not_checked");
  const byAsin = rows.filter(r => r.method !== "title").length;
  const byTitle = rows.length - byAsin;

  let html = '<p style="margin:0 0 8px;font-size:12.5px">'
    + (picked.length ? "You ticked <b>" + picked.length + "</b> listing(s). " : "")
    + 'Checked <b>' + rows.length + '</b>: ' + byAsin + ' by competitor ASIN, '
    + byTitle + ' by title (Amazon’s product-type search).</p>'
    + '<p style="margin:0 0 8px;font-size:12.5px"><b>' + changes.length + '</b> to change'
    + ' · ' + same + ' already right · ' + unchecked.length + ' couldn’t check'
    + ' · ' + skipped.length + ' left out</p>';
  if(denied){
    html += '<p style="margin:0 0 8px;font-size:12px" class="cwarn">Amazon refused this account’s access for some of these, so they were not checked and will not be changed.</p>';
  }
  if(changes.length){
    html += '<div style="max-height:40vh;overflow-y:auto;font-size:12px;border-top:1px solid var(--line2)">'
      + changes.map(function(r, i){
          const opts = r.options || [];
          const choose = (r.method === "title" && opts.length > 1)
            ? '<select class="ptfix-pick" style="font-size:12px" onchange="this.closest(\'.ptfix-row\').querySelector(\'.ptfix-tick\').checked=true">'
              + opts.map(o => '<option value="' + esc(o) + '"' + (o === r.amazon ? " selected" : "") + '>' + esc(o) + '</option>').join("")
              + '</select>'
            : '<b>' + esc(r.amazon) + '</b>';
          return '<label class="ptfix-row" data-i="' + i + '" style="display:flex;gap:8px;padding:5px 0;border-bottom:1px solid var(--line2)">'
            + '<input type="checkbox" class="ptfix-tick"' + (ptPreticked(r) ? " checked" : "") + '>'
            + '<span style="flex:1"><span style="font-family:monospace">' + esc(r.sku) + '</span>'
            + ' <span class="cc">' + (r.method === "title" ? "· suggested from title" : "· from ASIN " + esc(r.asin || "")) + '</span>'
            + '<div class="cc">' + esc(String(r.title || "").slice(0, 70)) + '</div>'
            + '<div>' + esc(r.current || "(blank)") + ' → ' + choose + '</div></span></label>';
        }).join("") + '</div>'
      + '<p style="margin:8px 0 0;font-size:12px" class="cc">Title suggestions are Amazon’s best guess — check them. '
      + 'Where Amazon offered several types, pick one and tick the row. Nothing is saved until you press Apply. '
      + 'A different type can ask for different details: run Preview on these afterwards.</p>';
  }
  if(unchecked.length){
    html += '<details style="margin-top:8px;font-size:12px"><summary>Couldn’t check (' + unchecked.length + ')</summary>'
      + unchecked.map(r => '<div>' + esc(r.sku) + ' — ' + esc(r.why) + '</div>').join("") + '</details>';
  }
  html += _ptSkipHtml(skipped);
  const chosen = await _dlgOpen({title:"Fix product types from Amazon", html:html, cancelValue:null,
    buttons: changes.length
      ? [{label:"Cancel", value:null},
         {label:"Apply ticked changes", tone:"go", primary:true,
          take: function(wrap){
            const got = ptReadChoices(wrap, changes);
            if(!got.length){ toast("Tick at least one change"); return undefined; }
            return got;
          }}]
      : [{label:"Close", tone:"go", primary:true, value:null}]});
  if(!chosen || !chosen.length) return;

  let ok = 0; const failed = [];
  for(const r of chosen){
    const j = await editField(r.sku, "col", "Product Type", r.amazon);
    if(j && j.ok) ok++; else failed.push(r.sku + ": " + ((j && j.error) || "save failed"));
  }
  try{
    await fetch("/product_types/recheck", {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify(acctBody({}))});
  }catch(e){ /* the saves stand; warnings catch up on the next generate */ }
  if(typeof refreshView === "function"){ try{ refreshView(); }catch(e){} }
  // The warnings on each listing's page are Amazon's reply to its LAST Preview or
  // Submit, and only a new one replaces them -- say so, or a saved fix looks
  // like a failed one ("it says it is fixed 33 but ... that error message still").
  await uiAlert("Changed " + ok + " product type(s)."
    + (failed.length ? "\n\nNot saved:\n" + failed.join("\n") : "")
    + (ok ? "\n\nAmazon's old warnings stay on these listings until they are previewed again. "
          + "Tick them and press Preview on the selection bar to refresh them all at once." : ""));
}
