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
             +`This updates the sheet AND pushes the change live to Amazon. I'll test on ONE listing first, then do the rest.`)) return;

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
