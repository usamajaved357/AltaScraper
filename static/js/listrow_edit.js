/* static/js/listrow_edit.js -- edit several listings, then save them together.
 *
 *     "When you change a price in the inline input box and click elsewhere,
 *      nothing happens. Amazon shows a sticky bottom bar: '3 SKUs edited |
 *      Cancel | Save all'."
 *
 * HALF OF THAT WAS ALREADY TRUE AND HALF WAS NOT, and the difference matters:
 * the price box DID save. It called saveEdit() on change, which POSTs /edit and
 * writes the app's own stored price. What it did not do was tell you it had, or
 * let you take it back -- so a mistyped price was already saved by the time you
 * looked away, and there was nothing to press to undo it.
 *
 * So this is not "make saving work". It is: HOLD the change instead of writing
 * it immediately, show what is held, and give the two buttons.
 *
 * ═══ THE ONE THING THAT DECIDES EVERYTHING ELSE ═════════════════════════════
 *
 * NOTHING HERE KNOWS HOW TO SAVE ANYTHING. Every field routes to the endpoint
 * that already owned it before this file existed (CLAUDE.md Rule 12):
 *
 *     price      /edit          "Our Price (GBP)", via saveEdit()
 *     handling   /edit          "Handling Days",   via saveEdit()
 *     cost       /cogs/set      via cogsSet() in cogs.js
 *     quantity   /stock/bulk_update  -> listing/handling.push_quantity
 *
 * The first two are one column each in _EDITABLE_COLS (dashboard.py); the third
 * is resolved server-side by domain/cogs.py; the fourth patches Amazon. A fifth
 * "save the listings row" endpoint written here would be a second opinion about
 * what a price is, and the two would drift the first time either changed.
 *
 * ═══ WHAT IS AND IS NOT SENT TO AMAZON ══════════════════════════════════════
 *
 * THREE OF THESE FOUR NEVER LEAVE THIS APP. Price, cost and handling days are
 * written to this app's own record of the listing. Stock is the exception: it
 * patches fulfillment_availability on the live Amazon listing, because there is
 * nowhere else for it to go -- Amazon is the authority on stock and this app
 * deliberately keeps no copy (see routes/handling_routes.stock_bulk_update).
 *
 * The bar SAYS which of the two a save will be, before you press it, because
 * "saved" meaning "recorded here" and "saved" meaning "changed on Amazon" are
 * not the same promise.
 */

/* {sku: {field: "typed value"}} -- only fields that differ from their original.
 * A field typed back to its original value is REMOVED, not kept as a no-op:
 * "3 SKUs edited" has to mean three listings will change. */
let LR_EDITS = {};

/* Every editable field, its label for the bar, and the thing that already knew
 * how to save it. ADDING A FIELD IS ONE ENTRY HERE plus the box that renders
 * it -- there is no second list anywhere. */
const LR_FIELDS = {
  price:    {label: "price",        live: false},
  cost:     {label: "cost",         live: false},
  handling: {label: "handling time", live: false},
  qty:      {label: "stock",        live: true},
};

function lrEditCount(){ return Object.keys(LR_EDITS).length; }

function lrEditFields(){
  let n = 0;
  for(const sku in LR_EDITS) n += Object.keys(LR_EDITS[sku]).length;
  return n;
}

/* Does anything staged go to Amazon? Decides the wording on the bar. */
function lrEditTouchesAmazon(){
  for(const sku in LR_EDITS){
    for(const f in LR_EDITS[sku]) if(LR_FIELDS[f] && LR_FIELDS[f].live) return true;
  }
  return false;
}

/* ═══ ONE EDITABLE BOX ═══════════════════════════════════════════════════════
 *
 * The original travels ON THE ELEMENT, in data-lr-orig, rather than in a
 * parallel object keyed by sku+field. The table re-renders on every filter,
 * sort and metrics reply, so a remembered original would outlive the input it
 * describes and Cancel would write a stale number into a fresh box. An
 * attribute cannot: it is destroyed with the element it belongs to.
 */
function lrEditBox(o){
  const orig = String(o.value == null ? "" : o.value);

  /* A LISTING THIS APP HOLDS NO DRAFT OF CANNOT BE EDITED, and the box is not
   * drawn for one.
   *
   *     "The Save All bar fails for some SKUs with 'no listing with this SKU in
   *      this workspace'. Example: floating_Duck."
   *
   * That SKU is real and the message is right: it is on Amazon, and there is no
   * row here to write to. MEASURED on nestwell_goods, 18 of the 62 SKUs Amazon
   * reports have no row in `listings` -- made in Seller Central, or by another
   * tool, or their draft was deleted.
   *
   * The detailed view drew them anyway, because listBlocks flattens the app's
   * rows and Amazon's catalogue into one block, and every row in that block got
   * an editable box. /edit then refused, correctly, AFTER the value was typed
   * and Save pressed.
   *
   * So the box is replaced by the value, read-only, with the reason on hover --
   * the same distinction the table view has always drawn with its "no draft
   * here" badge. A control that cannot work is worse than no control: this one
   * took a number, held it, counted it in "1 SKU edited", and then lost it.
   */
  if(o.sku && typeof hasDraftRow === "function" && !hasDraftRow(o.sku)){
    return '<span class="lr-ro" title="This listing is on Amazon and this app '
      + 'holds no draft of it, so there is nothing here to edit. Press Sync to '
      + 'pull it in, and then it can be changed like any other.">'
      + (orig === "" ? '<span class="dash">—</span>' : esc(orig)) + '</span>';
  }
  return '<input class="lr-edit' + (o.cls ? " " + o.cls : "") + '"'
    + ' type="text" inputmode="decimal"'
    + ' value="' + esc(orig) + '"'
    + ' data-lr-sku="' + esc(o.sku) + '"'
    + ' data-lr-field="' + esc(o.field) + '"'
    + ' data-lr-orig="' + esc(orig) + '"'
    + (o.placeholder ? ' placeholder="' + esc(o.placeholder) + '"' : "")
    + (o.title ? ' title="' + esc(o.title) + '"' : "")
    + ' onclick="event.stopPropagation()"'
    + ' oninput="lrEditStage(this)"'
    // Enter commits nothing -- it blurs, which is what Amazon's own boxes do.
    // The commit is Save all, once, for everything.
    + ' onkeydown="if(event.key===\'Enter\'){event.preventDefault();this.blur();}'
    +   'if(event.key===\'Escape\'){event.preventDefault();lrEditRevertOne(this);}"'
    + '>';
}

/* Record (or un-record) what is in a box. */
function lrEditStage(el){
  if(!el) return;
  const sku = el.getAttribute("data-lr-sku") || "";
  const field = el.getAttribute("data-lr-field") || "";
  const orig = el.getAttribute("data-lr-orig") || "";
  if(!sku || !field) return;
  const now = String(el.value == null ? "" : el.value);

  if(_lrSame(now, orig)){
    // TYPED BACK TO WHERE IT STARTED IS NOT AN EDIT. Without this, correcting a
    // typo leaves the SKU in the count and Save all writes the value it already
    // had -- which for stock is a real Amazon call to change nothing.
    if(LR_EDITS[sku]){
      delete LR_EDITS[sku][field];
      if(!Object.keys(LR_EDITS[sku]).length) delete LR_EDITS[sku];
    }
    el.classList.remove("dirty");
  }else{
    (LR_EDITS[sku] = LR_EDITS[sku] || {})[field] = now;
    el.classList.add("dirty");
  }
  lrEditBar();
}

/* Numerically where both are numbers, so "9.10" and "9.1" are the same price,
 * and textually otherwise -- an empty box and a "0" are never the same thing. */
function _lrSame(a, b){
  const sa = String(a).trim(), sb = String(b).trim();
  if(sa === sb) return true;
  if(sa === "" || sb === "") return false;
  const na = Number(sa), nb = Number(sb);
  return isFinite(na) && isFinite(nb) && na === nb;
}

/* Escape in one box: put that box back, leave the rest alone. */
function lrEditRevertOne(el){
  if(!el) return;
  el.value = el.getAttribute("data-lr-orig") || "";
  lrEditStage(el);
}

/* ═══ CANCEL ════════════════════════════════════════════════════════════════
 *
 *     "Cancel -> instantly reverts all modified inputs to their original
 *      values. No API call. Must be instant (milliseconds)."
 *
 * So it walks the boxes that are actually on screen and writes their own
 * data-lr-orig back. NO RE-RENDER: rebuilding the table would be slower, would
 * lose the scroll position, and would ask the metrics loader for another pass.
 */
function lrEditCancel(){
  const n = lrEditCount();
  LR_EDITS = {};
  document.querySelectorAll("input.lr-edit").forEach(function(el){
    el.value = el.getAttribute("data-lr-orig") || "";
    el.classList.remove("dirty", "saved", "err");
  });
  lrEditBar();
  if(n && typeof toast === "function") toast("Changes discarded");
}

/* ═══ SAVE ALL ══════════════════════════════════════════════════════════════
 *
 * ONE FIELD AT A TIME, AND A FAILURE STOPS NOTHING ELSE. Each save reports
 * separately, so a stock push Amazon refuses does not throw away the four
 * prices that saved fine -- and the ones that failed KEEP their edit and their
 * highlight, so the bar still shows them and they can be tried again.
 */
async function lrEditSaveAll(){
  const jobs = [];
  document.querySelectorAll("input.lr-edit.dirty").forEach(function(el){
    const sku = el.getAttribute("data-lr-sku") || "";
    const field = el.getAttribute("data-lr-field") || "";
    if(LR_EDITS[sku] && LR_EDITS[sku][field] !== undefined) jobs.push({el, sku, field});
  });
  if(!jobs.length) return;

  // STOCK IS CONFIRMED, THE REST IS NOT. Price, cost and handling are written
  // here and are undoable by typing again; a stock push changes what buyers can
  // order, on Amazon, now.
  const live = jobs.filter(j => LR_FIELDS[j.field] && LR_FIELDS[j.field].live);
  if(live.length && typeof uiConfirm === "function"){
    const ok = await uiConfirm("Set stock on Amazon for " + live.length
      + " listing" + (live.length === 1 ? "" : "s") + "? This changes what buyers "
      + "can order right now. The other changes are saved to this app only.");
    if(!ok) return;
  }

  const bar = document.getElementById("lrsavebar");
  if(bar) bar.classList.add("busy");
  let ok = 0;
  const failed = [];
  for(const j of jobs){
    j.el.classList.remove("err");
    j.el.classList.add("saving");
    let res;
    try{ res = await _lrSaveField(j.sku, j.field, String(j.el.value || "")); }
    catch(e){ res = {ok: false, error: String((e && e.message) || e)}; }
    j.el.classList.remove("saving");
    if(res && res.ok){
      ok++;
      // The saved value BECOMES the original, so this box is clean and a later
      // Cancel puts it back to what was actually saved rather than to what it
      // said when the page was drawn.
      j.el.setAttribute("data-lr-orig", String(j.el.value || ""));
      j.el.classList.remove("dirty");
      j.el.classList.add("saved");
      setTimeout(() => j.el.classList.remove("saved"), 1200);
      if(LR_EDITS[j.sku]){
        delete LR_EDITS[j.sku][j.field];
        if(!Object.keys(LR_EDITS[j.sku]).length) delete LR_EDITS[j.sku];
      }
    }else{
      j.el.classList.add("err");
      failed.push({sku: j.sku, field: j.field,
                   why: (res && res.error) || "no reason given"});
    }
  }
  if(bar) bar.classList.remove("busy");
  lrEditBar();

  if(typeof toast === "function"){
    if(!failed.length){
      toast("Saved " + ok + " change" + (ok === 1 ? "" : "s"));
    }else{
      // NAMED, not counted. "2 failed" sends you looking; the SKU and the
      // reason are what Amazon or the route actually said.
      toast(ok + " saved · " + failed.length + " failed — "
            + failed[0].sku + " " + (LR_FIELDS[failed[0].field] || {}).label
            + ": " + failed[0].why);
    }
  }
}

/* Route one field to the thing that already saved it. Returns {ok, error}. */
async function _lrSaveField(sku, field, value){
  if(field === "price")    return _lrSaveCol(sku, "Our Price (GBP)", value);
  if(field === "handling") return _lrSaveCol(sku, "Handling Days", value);
  if(field === "cost")     return _lrSaveCost(sku, value);
  if(field === "qty")      return _lrSaveQty(sku, value);
  return {ok: false, error: "no saver for " + field};
}

/* A column on the listings row, through editField() in autofix.js -- the one
 * function that posts to /edit, and the one that keeps ROWS in step so a
 * re-render does not draw the old number. dashboard.py's _EDITABLE_COLS is
 * what decides whether a column may be written at all. */
async function _lrSaveCol(sku, key, value){
  if(typeof editField !== "function")
    return {ok: false, error: "the field editor is not loaded"};
  return editField(sku, "col", key, value);
}

/* The cost. cogsSet() in cogs.js is the one caller of /cogs/set; this asks it
 * rather than posting again from here. An EMPTY box clears the override and
 * falls back to what the SKU says -- cogs.js's own rule, not a new one. */
async function _lrSaveCost(sku, value){
  if(typeof cogsSet !== "function")
    return {ok: false, error: "the cost editor is not loaded"};
  const raw = String(value || "").trim();
  const val = raw === "" ? null : Number(raw.replace(/[^0-9.]/g, ""));
  if(val !== null && (!isFinite(val) || val < 0))
    return {ok: false, error: "that is not a cost"};
  return cogsSet(sku, val);
}

/* Stock, on Amazon. /stock/bulk_update takes a list and this sends one, so the
 * validation, the 100,000 ceiling and the FBA refusal are all the route's --
 * see routes/handling_routes.py. */
async function _lrSaveQty(sku, value){
  const raw = String(value || "").trim();
  if(raw === "") return {ok: false, error: "stock cannot be blank — 0 stops selling"};
  const qty = Number(raw);
  if(!isFinite(qty) || qty < 0 || Math.floor(qty) !== qty)
    return {ok: false, error: "stock must be a whole number of units"};
  try{
    const body = (typeof acctBody === "function")
      ? acctBody({skus: [sku], qty: qty}) : {skus: [sku], qty: qty};
    const j = await (await fetch("/stock/bulk_update", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)})).json();
    if(!j || !j.ok){
      // The route answers per SKU; the first result carries Amazon's own words.
      const first = (j && (j.push_results || [])[0]) || {};
      return {ok: false, error: (first.error || (j && j.error) || "Amazon refused")};
    }
    // THE NUMBER ON SCREEN CAME FROM LISTING_METRICS, NOT FROM THE ROW. Price,
    // cost and handling all live on the row object, which their savers update,
    // so a re-render draws the new figure. Stock does not: the next render
    // would rebuild this box from the cached metrics and show the OLD quantity
    // over a listing Amazon has already changed -- the one state this whole
    // file exists to prevent. Amazon is still the authority; this is the local
    // copy of its last answer being kept in step with what we just told it.
    try{
      if(typeof LISTING_METRICS !== "undefined" && LISTING_METRICS[sku]){
        LISTING_METRICS[sku].available = qty;
      }
    }catch(e){}
    return {ok: true};
  }catch(e){ return {ok: false, error: String((e && e.message) || e)}; }
}

/* ═══ THE BAR ═══════════════════════════════════════════════════════════════
 *
 * Built once and then only updated, so typing does not rebuild a DOM node under
 * the cursor. It is removed when there is nothing staged: a bar reading
 * "0 SKUs edited" is a bar in the way.
 */
function lrEditBar(){
  const n = lrEditCount();
  let bar = document.getElementById("lrsavebar");
  if(!n){ if(bar) bar.remove(); return; }
  if(!bar){
    bar = document.createElement("div");
    bar.id = "lrsavebar";
    bar.className = "lr-savebar";
    bar.innerHTML =
        '<span class="lr-sb-n"></span>'
      + '<span class="lr-sb-what"></span>'
      + '<button class="lr-sb-cancel" onclick="lrEditCancel()">Cancel</button>'
      + '<button class="lr-sb-save" onclick="lrEditSaveAll()">Save all</button>';
    document.body.appendChild(bar);
  }
  const fields = lrEditFields();
  const nEl = bar.querySelector(".lr-sb-n");
  if(nEl){
    nEl.textContent = n + " SKU" + (n === 1 ? "" : "s") + " edited"
      + (fields > n ? " · " + fields + " fields" : "");
  }
  // SAY WHERE IT GOES. Recorded here and changed on Amazon are different
  // promises and the button is the same width for both.
  const wEl = bar.querySelector(".lr-sb-what");
  if(wEl){
    wEl.textContent = lrEditTouchesAmazon()
      ? "stock goes to Amazon; the rest is saved here"
      : "saved in this app, not sent to Amazon";
  }
}

/* A re-render throws every input away and builds new ones from the row data --
 * which is the SAVED data, so an unsaved edit would silently disappear and the
 * bar would go on claiming it existed. Called by the detailed view after it
 * draws: it re-applies what is staged to the fresh boxes. */
function lrEditRestore(){
  if(!lrEditCount()) return;
  document.querySelectorAll("input.lr-edit").forEach(function(el){
    const sku = el.getAttribute("data-lr-sku") || "";
    const field = el.getAttribute("data-lr-field") || "";
    const held = LR_EDITS[sku] && LR_EDITS[sku][field];
    if(held === undefined) return;
    el.value = held;
    el.classList.add("dirty");
  });
  lrEditBar();
}
