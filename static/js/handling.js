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
// of rules: take the selected listings, test the change on ONE first, show
// Amazon's own reply, and only then send the rest. That shape is not decoration
// -- it is what stops a wrong number reaching a whole catalogue.
//
//   handling time   fulfillment_availability.lead_time_to_ship_max_days
//   stock           fulfillment_availability.quantity      <- same attribute
//   price           purchasable_offer, by a percentage
//
// STOCK AND HANDLING TIME ARE THE SAME AMAZON ATTRIBUTE, which is why they are
// one module on the server too: Amazon replaces the whole array on a patch, so
// two independent writers would each undo the other's field.
//
// PRICE IS DIFFERENT IN ONE IMPORTANT WAY and does not use the test-one shape.
// A percentage is not a price -- it is a different number on every listing --
// so there is nothing to approve until each one has been worked out. It previews
// every listing, shows the table, and then sends THOSE FIGURES rather than the
// percentage again.

// ---- Bulk handling-time update (sheet + live Amazon push) --------------------
// Set lead_time_to_ship_max_days on many listings at once. Works on the SELECTED
// listings (use "Select all" for everything in view). Updates the sheet's handling
// column where it exists AND pushes the value live to Amazon per SKU. The first live
// push is done as a single-SKU TEST so you see Amazon's reply before the rest go.

function _handlingSkus(){
  // selected listings, or (if none selected) every real listing in the current view
  let skus = (typeof selectedSkus==="function") ? selectedSkus() : [];
  if(skus.length) return skus;
  const vis = (ROWS||[]).filter(r=> (typeof passFilter!=="function"||passFilter(r))
                                  && !(typeof isEmptyRow==="function" && isEmptyRow(r)));
  return vis.map(r=>String(r.sku||"").trim()).filter(Boolean);
}

async function _handlingPost(body){
  const res = await fetch("/handling/bulk_update",{method:"POST",
    headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
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
  if(!confirm(`Set handling time to ${days} day(s) on ${skus.length} ${usingAll?'listing(s) in this view':'selected listing(s)'}?\n\n`
             +`This saves it here AND pushes the change live to Amazon. I'll test on ONE listing first, then do the rest.`)) return;

  const btn = document.getElementById("handlingbtn");
  if(btn){ btn.disabled=true; btn.dataset._t=btn.textContent; btn.textContent="Testing…"; }
  const _done=()=>{ if(btn){ btn.disabled=false; btn.textContent=btn.dataset._t||"Set handling time"; } };

  try{
    // --- 1) single-listing safety test (real push of the first SKU) ---
    toast("Testing handling-time push on 1 listing…");
    const t = await _handlingPost({skus:[skus[0]], days, push:true, test_one:true});
    const tr = (t && t.result) || {};
    if(!t || !t.ok){
      const msg = (tr.error || (t && t.error) || "unknown error");
      // NOT_FOUND on the test SKU just means that one isn't live yet — let the user proceed
      // to update the sheet + push the ones that ARE live.
      const notLive = /no listing with this sku|not_found/i.test(msg);
      if(notLive){
        if(!confirm(`The first listing (${skus[0]}) isn't live on Amazon yet, so there was nothing to push there.\n\n`
                   +`Continue anyway? The sheet handling value will be set on all ${skus.length}, and the push will apply to whichever ARE live.`)){ _done(); return; }
      } else {
        alert(`Handling-time test failed on ${skus[0]}:\n\n${msg}\n\nNothing was changed in bulk. Fix this, then try again.`);
        _done(); return;
      }
    } else {
      const before = (tr.before===null||tr.before===undefined) ? "(none)" : tr.before;
      if(!confirm(`Test succeeded on ${skus[0]} (handling ${before} → ${days} day(s) on Amazon).\n\n`
                 +`Apply to the remaining ${skus.length-1} listing(s) and update the sheet?`)){ _done(); return; }
    }

    // --- 2) full run: sheet + push for all selected ---
    if(btn) btn.textContent="Updating…";
    toast(`Updating handling time on ${skus.length} listing(s)…`);
    const j = await _handlingPost({skus, days, push:true, sheet:true});
    if(!j || j.ok===false && !j.push_results){ toast("Update failed: "+((j&&j.error)||"unknown")); _done(); return; }

    const sheetN = (j.sheet_updated||[]).length;
    const okN = j.pushed_ok||0, failArr = (j.push_results||[]).filter(r=>!r.ok);
    const notLive = failArr.filter(r=>/no listing with this sku|not_found/i.test(r.error||"")).length;
    const realFail = failArr.length - notLive;
    let msg = `Handling time set to ${days} day(s).`;
    msg += `\n• Sheet updated: ${sheetN}`;
    if(j.sheet_has_column===false) msg += " (no handling column on these tabs — sheet skipped)";
    msg += `\n• Pushed live to Amazon: ${okN}`;
    if(notLive) msg += `\n• Not live yet (draft — will apply on submit): ${notLive}`;
    if(realFail) msg += `\n• Failed: ${realFail} (see details below)`;
    if(realFail){
      const lines = failArr.filter(r=>!/no listing with this sku|not_found/i.test(r.error||""))
                           .slice(0,8).map(r=>`  – ${r.sku}: ${r.error||"error"}`).join("\n");
      msg += `\n\n${lines}`;
    }
    alert(msg);
    toast(`Handling time updated (${okN} live, ${sheetN} in sheet)`);
    if(typeof loadRows==="function") loadRows();
  }catch(e){
    toast("Handling update failed: "+e);
  }finally{
    _done();
  }
}


// ---- Bulk stock quantity ----------------------------------------------------
//
// Same shape as handling time, and deliberately so: one listing is pushed first
// and Amazon's answer shown before the rest go. Stock is the one of the three
// where a wrong number has a customer consequence rather than a reporting one --
// promise units you do not have and the orders still arrive.
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

  if(!confirm(`Set stock to ${qty} unit(s) on ${skus.length} ${usingAll?'listing(s) in this view':'selected listing(s)'}?\n\n`
    + (qty===0
        ? `0 units takes them off sale — the listings stay, but nobody can buy them.\n\n`
        : ``)
    + `This pushes the change live to Amazon. I'll test on ONE listing first, then do the rest.\n\n`
    + `FBA listings will be refused: their stock is whatever is in Amazon's warehouse.`)) return;

  const btn = document.getElementById("stockbtn");
  if(btn){ btn.disabled=true; btn.dataset._t=btn.textContent; btn.textContent="Testing…"; }
  const _done=()=>{ if(btn){ btn.disabled=false; btn.textContent=btn.dataset._t||"Set stock"; } };
  const post = (body)=> fetch("/stock/bulk_update",{method:"POST",
      headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)}).then(r=>r.json());

  try{
    toast("Testing the stock change on 1 listing…");
    const t = await post({skus:[skus[0]], qty, test_one:true});
    const tr = (t && t.result) || {};
    if(!t || !t.ok){
      const msg = (tr.error || (t && t.error) || "unknown error");
      // A SKU that is FBA, or not live yet, says nothing about the others --
      // so it offers to carry on rather than stopping the whole run.
      const skippable = /no seller-fulfilled stock|no listing with this sku|not_found/i.test(msg);
      if(skippable){
        if(!confirm(`The first listing (${skus[0]}) could not take a stock change:\n\n${msg}\n\n`
                   +`Continue with the other ${skus.length-1}? Each one is reported separately.`)){ _done(); return; }
      } else {
        alert(`The stock test failed on ${skus[0]}:\n\n${msg}\n\nNothing was changed in bulk. Fix this, then try again.`);
        _done(); return;
      }
    } else {
      const before = (tr.before===null||tr.before===undefined) ? "(none)" : tr.before;
      if(!confirm(`Test succeeded on ${skus[0]} (stock ${before} → ${qty} on Amazon).\n\n`
                 +`Apply to the remaining ${skus.length-1} listing(s)?`)){ _done(); return; }
    }

    if(btn) btn.textContent="Updating…";
    toast(`Setting stock on ${skus.length} listing(s)…`);
    const j = await post({skus, qty});
    const okN = (j && j.pushed_ok) || 0;
    const failArr = ((j && j.push_results)||[]).filter(r=>!r.ok);
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
    alert(msg);
    toast(`Stock updated on ${okN} listing(s)`);
    if(typeof loadRows==="function") loadRows();
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
  const body = ()=>({ id: (typeof CUR_ACCOUNT!=="undefined" && CUR_ACCOUNT) ? CUR_ACCOUNT.id : "",
                      marketplace: (typeof WS_MARKET!=="undefined") ? WS_MARKET : "" });

  try{
    toast(`Reading the current price of ${skus.length} listing(s) from Amazon…`);
    const p = await fetch("/listing/price/percent_preview",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(Object.assign(body(), {skus, percent: pct}))}).then(r=>r.json());
    if(!p || !p.ok){ alert("Could not work out the new prices:\n\n"+((p&&p.error)||"unknown error")); _done(); return; }

    const rows = p.rows || [], skipped = p.skipped || [];
    if(!rows.length){
      alert("None of the selected listings could be repriced.\n\n"
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
    if(!confirm(ask)){ _done(); return; }

    let allowBelow = false;
    if(below.length){
      allowBelow = confirm(`Price those ${below.length} listing(s) below their floor anyway?\n\n`
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
    alert(msg);
    toast(`${(j&&j.changed)||0} price(s) changed`);
    if(typeof loadRows==="function") loadRows();
  }catch(e){
    toast("Price change failed: "+e);
  }finally{
    _done();
  }
}
