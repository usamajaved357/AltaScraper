// ---- What a listing PROMISES THE BUYER, changed on many listings at once -----
//
//     "i dont have any option to update the quantity of the items ... i want to
//      select the products of which i want to update the quantity and then
//      select it like we set handling time for many items at once"
//
//     "increasing the seller price should be allowed to be updated by
//      percentage. e.g. increase or decrease the selling price by this percent."
//
// Three bulk actions live in this file because they share one shape and one set
// of rules: take the selected listings, ask ONCE, and send them all.
//
//   handling time   fulfillment_availability.lead_time_to_ship_max_days
//   stock           fulfillment_availability.quantity      <- same attribute
//   price           purchasable_offer, by a percentage
//
// STOCK AND HANDLING TIME ARE THE SAME AMAZON ATTRIBUTE, which is why they are
// one module on the server too: Amazon replaces the whole array on a patch, so
// two independent writers would each undo the other's field.
//
// ONE CONFIRMATION, NOT TWO.
//
//     "Remove the test-then-apply pattern. One confirmation only ... All
//      selected updated at once. No 'test on one first' dialog. No second
//      confirmation. If Amazon rejects one, show the error for that one and
//      continue with the rest."
//
// Handling time and stock each used to push the FIRST selected listing for
// real, show Amazon's reply, and ask again before sending the other n-1. The
// stated reason was that it stopped a wrong number reaching a whole catalogue.
// It did not: the number was already on Amazon by the time the second dialog
// appeared, so the "test" was the first write of the run, not a rehearsal of
// it. What it actually bought was one listing's worth of warning in exchange
// for two dialogs on every bulk action -- and it made the first selected SKU
// special, so a run that stopped there left the catalogue half-changed with no
// record of which half.
//
// The protection that matters is the one that survived: the server sends each
// SKU separately and reports each separately, so one Amazon refusal never
// stops the rest. Those per-listing errors are still shown, which is the thing
// the test-one dialog was really for.
//
// PRICE IS DIFFERENT IN ONE IMPORTANT WAY and never had the test-one shape.
// A percentage is not a price -- it is a different number on every listing --
// so there is nothing to approve until each one has been worked out. It previews
// every listing, shows the table, and then sends THOSE FIGURES rather than the
// percentage again. That preview IS its single confirmation, so it is unchanged.

// ---- Bulk handling-time update (saved here + live Amazon push) ---------------
// Set lead_time_to_ship_max_days on many listings at once. Works on the SELECTED
// listings (use "Select all" for everything in view). Saves the handling value
// here AND pushes it live to Amazon per SKU. Every selected listing goes in one
// run; each one's result is reported separately.

function _handlingSkus(){
  // selected listings, or (if none selected) every real listing in the current view
  let skus = (typeof selectedSkus==="function") ? selectedSkus() : [];
  if(skus.length) return skus;
  // "EVERY LISTING IN THIS VIEW" IS ASKED OF THE VIEW.
  //
  // This re-derived it from ROWS + passFilter, which is the same mistake
  // selectAllVisible was making: the Live tab draws Amazon's catalogue as well,
  // and none of that is in ROWS. So "Select all then Set stock" covered 48
  // listings while "Set stock with nothing selected" quietly covered 2 -- the
  // same button, the same screen, two different scopes, neither stated.
  // visibleSelectableSkus (listings.js) reads back what is actually drawn, and
  // is the one definition of that answer (CLAUDE.md Rule 12).
  if(typeof visibleSelectableSkus === "function"){
    const onScreen = visibleSelectableSkus();
    if(onScreen.length) return onScreen;
  }
  const vis = (ROWS||[]).filter(r=> (typeof passFilter!=="function"||passFilter(r))
                                  && !(typeof isEmptyRow==="function" && isEmptyRow(r)));
  return vis.map(r=>String(r.sku||"").trim()).filter(Boolean);
}

/* WHICH ACCOUNT THIS IS ABOUT, sent with every one of the three.
 *
 * The server used to decide, from _state["active_account_id"] -- one variable
 * for the whole process, set by whichever browser tab last switched account.
 * With several tabs open (there are four in the screenshot this was found from)
 * a stock or handling push from one tab landed on whatever the other tab had
 * selected. The price action already named its account; these two did not, so
 * the same bar had two different ideas of whose listings it was changing.
 *
 * Written once here and used by all three, so they cannot drift apart again
 * (CLAUDE.md Rule 12). The server refuses a marketplace it cannot work out
 * rather than assuming UK -- see _push_target in routes/handling_routes.py.
 */
function _handlingScope(){
  return {
    id: (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT) ? CUR_ACCOUNT.id : "",
    marketplace: (typeof WS_MARKET !== "undefined" && WS_MARKET !== "__all__")
                   ? WS_MARKET : ""
  };
}

async function _handlingPost(body){
  const res = await fetch("/handling/bulk_update",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(Object.assign(_handlingScope(), body))});
  return res.json();
}

async function bulkHandling(){
  const inp = document.getElementById("handlingdays");
  const raw = inp ? String(inp.value||"").trim() : "";
  if(raw===""){ toast("Enter a handling time (days) first"); if(inp) inp.focus(); return; }
  const days = parseInt(raw, 10);
  if(isNaN(days) || days<0 || days>30){ toast("Handling time must be a whole number, 0–30 days"); return; }
  const skus = _handlingSkus();
  if(!skus.length){ toast("Select some listings first (or use Select all)"); return; }

  const usingAll = !((typeof selectedSkus==="function") && selectedSkus().length);
  if(!await uiConfirm(`Set handling time to ${days} day(s) on ${skus.length} ${usingAll?'listing(s) in this view':'selected listing(s)'}?\n\n`
             +`This saves it here AND pushes the change live to Amazon. Any listing Amazon refuses is reported on its own; the rest still go.`)) return;

  const btn = document.getElementById("handlingbtn");
  if(btn){ btn.disabled=true; btn.dataset._t=btn.textContent; btn.textContent="Updating…"; }
  const _done=()=>{ if(btn){ btn.disabled=false; btn.textContent=btn.dataset._t||"Set handling time"; } };

  try{
    toast(`Updating handling time on ${skus.length} listing(s)…`);
    const j = await _handlingPost({skus, days, push:true, sheet:true});
    if(!j || j.ok===false && !j.push_results){ toast("Update failed: "+((j&&j.error)||"unknown")); _done(); return; }

    const savedSkus = j.sheet_updated||[];
    const savedN = savedSkus.length;
    const results = j.push_results||[];
    const okN = j.pushed_ok||0, failArr = results.filter(r=>!r.ok);
    const notLive = failArr.filter(r=>/no listing with this sku|not_found/i.test(r.error||"")).length;
    const realFail = failArr.length - notLive;
    let msg = `Handling time set to ${days} day(s).`;
    msg += `\n• Saved: ${savedN}`;
    // WHY SOME WERE NOT SAVED, in the server's own words rather than a guess
    // here. It used to say "nowhere to record it" for every reason there was,
    // including a bug that stopped it from ever looking for the column -- so
    // "Pushed live to Amazon: 36 / Saved: 0" read like the listings were at
    // fault. sheet_note now distinguishes an error, a missing column, and a
    // listing this app simply has no draft of.
    if(j.sheet_note) msg += ` — ${j.sheet_note}`;
    msg += `\n• Pushed live to Amazon: ${okN}`;
    if(notLive) msg += `\n• Not live yet (will apply on submit): ${notLive}`;
    if(realFail) msg += `\n• Failed: ${realFail} (see details below)`;
    if(realFail){
      const lines = failArr.filter(r=>!/no listing with this sku|not_found/i.test(r.error||""))
                           .slice(0,8).map(r=>`  – ${r.sku}: ${r.error||"error"}`).join("\n");
      msg += `\n\n${lines}`;
    }
    await uiAlert(msg);
    toast(`Handling time updated (${okN} live, ${savedN} saved)`);
    // THE COLUMN SHOWS THE NEW NUMBER NOW, and shows it for exactly the
    // listings that got it. What we RECORD and what AMAZON holds are two
    // different fields on the row (see _handlingCell) and they are written
    // from two different answers here -- the save list and the push results --
    // so a listing that saved but was refused by Amazon still draws the
    // "we hold 2d, Amazon promises 5d" warning it should.
    applyPushedLocally(savedSkus.length ? savedSkus : skus, {handling_days: days}, null);
    applyPushedLocally(results.filter(r=>r.ok).map(r=>r.sku),
                       {handling_time: days}, {handling: days});
  }catch(e){
    toast("Handling update failed: "+e);
  }finally{
    _done();
  }
}


/* ONE LISTING, FROM ITS OWN PAGE.
 *
 *     "Handling time editable on EVERY listing, including the ones that are
 *      live on Amazon."
 *
 * The Offer tab's Handling days box saves through /edit, which finds a listing
 * BY ITS ROW IN THIS APP and returns 404 no_row when there isn't one. Measured
 * on his own accounts: 7 of jack_uk's 47 live SKUs and 18 of nestwell_goods' 62
 * have no row here -- made in Seller Central, made by another tool, or their
 * draft was deleted. On those the box accepted a number and then said "save
 * refused", which reads as a broken button rather than a fact about the
 * listing.
 *
 * This is the path for exactly those. It goes through _handlingPost, the same
 * one call the bulk bar uses (CLAUDE.md Rule 12) -- one endpoint, one
 * validation, one account scope, one set of words for what happened.
 *
 * IT ASKS FIRST, and it says what it is about to do. A blur-save cannot be the
 * control here: for a listing with no row the only place the number can go is
 * AMAZON, and sending a promise to customers is not something a text box should
 * do quietly on the way past. Everywhere else the field still saves on blur,
 * because there the value lands in this app and nowhere else.
 */
async function setHandlingOne(sku, days, opts){
  sku = String(sku || "").trim();
  opts = opts || {};
  if(!sku){ toast("No listing to update"); return false; }
  const n = parseInt(String(days).trim(), 10);
  if(isNaN(n) || n < 0 || n > 30){
    toast("Handling time must be a whole number, 0–30 days");
    return false;
  }
  if(!opts.silent){
    const ok = await uiConfirm(
      `Set handling time to ${n} day(s) on ${sku}?\n\n`
      + `This app holds no draft of this listing, so there is nowhere here to `
      + `record it — the change goes straight to Amazon, and shoppers see the `
      + `new dispatch promise.`);
    if(!ok) return false;
  }
  try{
    const j = await _handlingPost({skus:[sku], days:n, push:true, sheet:true});
    const res = (j && j.push_results || [])[0];
    if(!j || (j.ok === false && !j.push_results)){
      toast("Update failed: " + ((j && j.error) || "unknown"));
      return false;
    }
    if(res && !res.ok){
      // NOT LIVE is not a failure -- it is a listing Amazon has never seen,
      // and the number will go with it when it is submitted.
      if(/no listing with this sku|not_found/i.test(res.error || "")){
        toast("Not live on Amazon yet — this will apply when it is submitted");
        return false;
      }
      await uiAlert(`Amazon refused the change on ${sku}:\n\n${res.error || "error"}`);
      return false;
    }
    toast(`Handling time set to ${n} day(s) on Amazon`);
    // Same two fields, from the same two answers, as the bulk path: what we
    // RECORD and what AMAZON holds are different columns on the row.
    if(typeof applyPushedLocally === "function"){
      const saved = j.sheet_updated || [];
      if(saved.length) applyPushedLocally(saved, {handling_days: n}, null);
      applyPushedLocally([sku], {handling_time: n}, {handling: n});
    }
    // THE CACHED COPY OF WHAT AMAZON HOLDS IS NOW ONE EDIT OUT OF DATE, and for
    // a listing with no row that cache is the ONLY source the page has -- a
    // redraw would put the old number back into the box that just changed it.
    //
    // Patched rather than refetched. lvRefresh drops the entry and asks again,
    // which is right when we do not know the answer; here the push has just
    // told us, and a refetch would blank the page for a second to be told the
    // same thing. Written through lvGet, the accessor that module already
    // exposes, rather than by reaching into LIVE_ATTRS from here.
    const lv = (typeof lvGet === "function") ? lvGet(sku) : null;
    if(lv && lv.values){
      lv.values["fulfillment_availability.lead_time_to_ship_max_days"] = String(n);
    }
    if(typeof pdpRebuild === "function") pdpRebuild(sku);
    return true;
  }catch(e){
    toast("Handling update failed: " + e);
    return false;
  }
}

/* The box in the Offer tab hands its value over. Separate from the function
 * above so the button has something to call with no arguments to get wrong. */
async function setHandlingFromBox(sku, id){
  const el = document.getElementById(id);
  if(!el) return;
  const before = el.dataset._was;
  const ok = await setHandlingOne(sku, el.value);
  if(!ok && before !== undefined) el.value = before;
  else el.dataset._was = el.value;
}


// ---- Bulk stock quantity ----------------------------------------------------
//
// Same shape as handling time, and deliberately so: one confirmation, then
// every selected listing, each reported on its own. Stock is the one of the
// three where a wrong number has a customer consequence rather than a
// reporting one -- promise units you do not have and the orders still arrive --
// so the confirmation still spells out what 0 units does and that FBA listings
// will be refused. That warning is BEFORE anything is sent, which is where a
// warning is worth having.
//
// NOT WRITTEN ANYWHERE LOCALLY. Handling time has a column in the sheet because
// it is a decision the owner keeps; stock is a fact about the warehouse that
// Amazon is the authority on, and a copy here would be stale the moment
// something sells.

async function bulkQuantity(){
  const inp = document.getElementById("stockqty");
  const raw = inp ? String(inp.value||"").trim() : "";
  if(raw===""){ toast("Enter a stock quantity first"); if(inp) inp.focus(); return; }
  if(!/^\d+$/.test(raw)){ toast("Stock must be a whole number of units"); return; }
  const qty = parseInt(raw, 10);
  if(qty > 100000){ toast("Over 100,000 units — check for an extra digit"); return; }

  const skus = _handlingSkus();
  if(!skus.length){ toast("Select some listings first (or use Select all)"); return; }
  const usingAll = !((typeof selectedSkus==="function") && selectedSkus().length);

  if(!await uiConfirm(`Set stock to ${qty} unit(s) on ${skus.length} ${usingAll?'listing(s) in this view':'selected listing(s)'}?\n\n`
    + (qty===0
        ? `0 units takes them off sale — the listings stay, but nobody can buy them.\n\n`
        : ``)
    + `This pushes the change live to Amazon. Any listing Amazon refuses is reported on its own; the rest still go.\n\n`
    + `FBA listings will be refused: their stock is whatever is in Amazon's warehouse.`)) return;

  const btn = document.getElementById("stockbtn");
  if(btn){ btn.disabled=true; btn.dataset._t=btn.textContent; btn.textContent="Updating…"; }
  const _done=()=>{ if(btn){ btn.disabled=false; btn.textContent=btn.dataset._t||"Set stock"; } };
  const post = (body)=> fetch("/stock/bulk_update",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(Object.assign(_handlingScope(), body))}).then(r=>r.json());

  try{
    toast(`Setting stock on ${skus.length} listing(s)…`);
    const j = await post({skus, qty});
    const okN = (j && j.pushed_ok) || 0;
    const results = ((j && j.push_results)||[]);
    const failArr = results.filter(r=>!r.ok);
    const fba = failArr.filter(r=>/no seller-fulfilled stock/i.test(r.error||"")).length;
    const notLive = failArr.filter(r=>/no listing with this sku|not_found/i.test(r.error||"")).length;
    const realFail = failArr.length - fba - notLive;
    let msg = `Stock set to ${qty} unit(s).`;
    msg += `\n• Changed on Amazon: ${okN}`;
    if(fba)     msg += `\n• FBA — stock is in Amazon's warehouse, not ours to set: ${fba}`;
    if(notLive) msg += `\n• Not live on Amazon yet: ${notLive}`;
    if(realFail){
      msg += `\n• Failed: ${realFail}`;
      const lines = failArr
        .filter(r=>!/no seller-fulfilled stock|no listing with this sku|not_found/i.test(r.error||""))
        .slice(0,8).map(r=>`  – ${r.sku}: ${r.error||"error"}`).join("\n");
      msg += `\n\n${lines}`;
    }
    await uiAlert(msg);
    toast(`Stock updated on ${okN} listing(s)`);
    // Only the ones Amazon actually took. Stock is not recorded here at all --
    // Amazon is the authority on it (see the note above this function) -- so
    // there is nothing to write on the app row, only on the catalogue item the
    // "Out of stock" tile and its filter both read.
    applyPushedLocally(results.filter(r=>r.ok).map(r=>r.sku), null, {qty: qty});
  }catch(e){
    toast("Stock update failed: "+e);
  }finally{
    _done();
  }
}


// ---- Bulk price change, by percentage ---------------------------------------
//
// WHY THIS ONE PREVIEWS INSTEAD OF TESTING ONE.
//
// "+10%" is a different number on every listing, so there is nothing to approve
// until each has been worked out -- which needs Amazon's current price for each
// SKU, one read apiece. Testing a single listing would prove nothing about the
// other forty. So every listing is worked out first, the table is shown, and
// then EXACTLY those figures are sent. Re-applying the percentage at send time
// would mean approving a table and dispatching different numbers, off prices
// that may have moved in between -- the repricer runs against these same
// listings.

function _pctFmt(n){ return (n>0?"+":"") + Number(n).toFixed(2).replace(/\.00$/,"") + "%"; }

async function bulkPricePercent(){
  const inp = document.getElementById("pricepct");
  const raw = inp ? String(inp.value||"").trim() : "";
  if(raw===""){ toast("Enter a percentage — 10 to raise, -5 to lower"); if(inp) inp.focus(); return; }
  const pct = Number(raw);
  if(!isFinite(pct) || pct===0){ toast("Enter a percentage other than zero"); return; }
  if(pct <= -90 || pct > 500){ toast("Between -90% and +500% — anything else is almost certainly a typo"); return; }

  const skus = _handlingSkus();
  if(!skus.length){ toast("Select some listings first (or use Select all)"); return; }

  const btn = document.getElementById("pricepctbtn");
  if(btn){ btn.disabled=true; btn.dataset._t=btn.textContent; btn.textContent="Working it out…"; }
  const _done=()=>{ if(btn){ btn.disabled=false; btn.textContent=btn.dataset._t||"Change price %"; } };
  // The same scope the other two now send -- one definition (Rule 12). This was
  // the copy they were missing; it is no longer a copy.
  const body = _handlingScope;

  try{
    toast(`Reading the current price of ${skus.length} listing(s) from Amazon…`);
    const p = await fetch("/listing/price/percent_preview",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(Object.assign(body(), {skus, percent: pct}))}).then(r=>r.json());
    if(!p || !p.ok){ await uiAlert("Could not work out the new prices:\n\n"+((p&&p.error)||"unknown error")); _done(); return; }

    const rows = p.rows || [], skipped = p.skipped || [];
    if(!rows.length){
      await uiAlert("None of the selected listings could be repriced.\n\n"
            + skipped.slice(0,10).map(s=>`• ${s.sku}: ${s.why}`).join("\n"));
      _done(); return;
    }

    // THE TABLE IS THE APPROVAL. Every listing that would change, with what it
    // is now and what it becomes -- not a count.
    const sym = (typeof CUR_SYMBOL!=="undefined" && CUR_SYMBOL) ? CUR_SYMBOL : "";
    const show = rows.slice(0, 25).map(r =>
      `  ${r.sku}\n      ${sym}${r.current.toFixed(2)} → ${sym}${r.new.toFixed(2)}`
      + (r.below_floor ? `   ⚠ below its ${sym}${Number(r.floor).toFixed(2)} floor` : "")
    ).join("\n");
    const below = rows.filter(r=>r.below_floor);
    let ask = `Change the price of ${rows.length} listing(s) by ${_pctFmt(pct)}?\n\n${show}`;
    if(rows.length > 25) ask += `\n  …and ${rows.length-25} more`;
    if(skipped.length){
      ask += `\n\n${skipped.length} listing(s) will be left alone:\n`
           + skipped.slice(0,5).map(s=>`  – ${s.sku}: ${s.why}`).join("\n");
    }
    if(below.length){
      // NOT A ROUNDING WARNING. Below the floor means every unit sold loses
      // money against the profit rule this account set.
      ask += `\n\n⚠ ${below.length} of them would go BELOW the price at which they `
           + `still make money. Those will be refused unless you say otherwise.`;
    }
    ask += `\n\nNothing has been sent yet.`;
    if(!await uiConfirm(ask)){ _done(); return; }

    let allowBelow = false;
    if(below.length){
      allowBelow = await uiConfirm(`Price those ${below.length} listing(s) below their floor anyway?\n\n`
        + `OK  — send them too, knowingly under the profit rule (clearance).\n`
        + `Cancel — send the other ${rows.length-below.length} and leave those alone.`);
    }

    if(btn) btn.textContent="Sending…";
    toast(`Sending ${rows.length} price change(s)…`);
    const j = await fetch("/listing/price/percent_apply",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(Object.assign(body(), {
        rows: rows.map(r=>({sku:r.sku, new:r.new})),
        percent: pct, confirmed: true, below_floor_ok: allowBelow}))}).then(r=>r.json());

    let msg = `Price changed by ${_pctFmt(pct)}.`;
    msg += `\n• Changed on Amazon: ${(j&&j.changed)||0}`;
    const fails = (j && j.failures) || [];
    if(fails.length){
      const floorN = fails.filter(f=>f.below_floor).length;
      if(floorN) msg += `\n• Left alone (below their floor): ${floorN}`;
      const other = fails.filter(f=>!f.below_floor);
      if(other.length){
        msg += `\n• Failed: ${other.length}\n\n`
             + other.slice(0,8).map(f=>`  – ${f.sku}: ${f.error||"error"}`).join("\n");
      }
    }
    msg += `\n\nAmazon usually shows a new price within a few minutes.`;
    await uiAlert(msg);
    toast(`${(j&&j.changed)||0} price(s) changed`);
    if(typeof loadRows==="function") loadRows();
  }catch(e){
    toast("Price change failed: "+e);
  }finally{
    _done();
  }
}
