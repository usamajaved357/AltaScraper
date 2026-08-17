/* static/js/cogsmode.js -- how this account works out what its stock cost.
 *
 * WHY THIS EXISTS
 * The two costing modes were built as working endpoints and never given a
 * control, so there was no way to choose between them and no way to find where
 * costs are entered at all: "i dont see an option to enter cogs, we had 2
 * toggles but i dont see it". A setting nobody can reach is a setting that does
 * not exist.
 *
 * It sits directly under the Profit card because that is the card it explains.
 * A profit with uncosted units in it is knowingly higher than the truth, and the
 * way to fix it should be one click from the wrong number rather than on a
 * screen nobody thinks to open.
 *
 * THE TWO MODES, in the owner's own words:
 *
 *   Supplier price   the repricer checks each source every couple of hours and
 *                    an order is costed at THE PRICE IN FORCE WHEN IT ARRIVED --
 *                    "the price ... 12am to 2am was 7 gbp ... i received an
 *                    order in between 12 to 2", so that order costs 7 whatever
 *                    the price did afterwards.
 *
 *   SKU price        the cost written into the SKU by the generator, overridden
 *                    by a cost typed against the product, applying to every
 *                    order past and future.
 */

let COGSMODE = {mode: "", explain: {}, busy: false};

async function cogsModeLoad(){
  const host = document.getElementById("sales_cogsbar");
  if(!host) return;
  let j = null;
  try{ j = await _sFetch("/cogs/mode"); }catch(e){ return; }
  if(j === null) return;                       // workspace moved on
  if(!j || !j.ok){ host.innerHTML = ""; return; }
  COGSMODE.mode = j.mode;
  COGSMODE.explain = j.explain || {};
  cogsModeDraw();
}

function cogsModeDraw(){
  const host = document.getElementById("sales_cogsbar");
  if(!host) return;
  const sum = (typeof SALES !== "undefined" && SALES.data) ? SALES.data : null;
  const op = sum ? sum.order_profit : null;
  const missing = op ? (op.missing_units || 0) : 0;
  const units = op ? (op.units || 0) : 0;

  const btn = function(mode, label){
    const on = (COGSMODE.mode === mode);
    return '<button class="db-chip' + (on ? " on" : "") + '"'
         + ' style="' + (on ? "border-color:var(--accent);color:var(--accent)" : "") + '"'
         + ' title="' + _sEsc(COGSMODE.explain[mode] || "") + '"'
         + ' onclick="cogsModeSet(' + jsArg(mode) + ')">'
         + (on ? '<i class="ti ti-check"></i> ' : '') + _sEsc(label) + '</button>';
  };

  // The warning first and in the warning colour, because it is the reason
  // anybody is reading this bar at all.
  let warn = "";
  if(missing > 0){
    warn = '<div style="color:var(--warn);font-size:12px;margin-bottom:6px">'
         + '<i class="ti ti-alert-triangle"></i> '
         + missing + ' of ' + units + ' units have no cost recorded, so the '
         + 'Profit above is higher than the truth.'
         + (op && (op.missing_skus || []).length
             ? ' <span class="cc">' + _sEsc((op.missing_skus || []).slice(0, 3).join(", "))
               + ((op.missing_skus || []).length > 3 ? " and others" : "") + '</span>'
             : '')
         + '</div>';
  }

  host.innerHTML =
      '<div style="border:1px solid var(--line);border-radius:10px;padding:10px 12px;'
    + 'margin:0 0 12px;background:var(--panel)">'
    + warn
    + '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12.5px">'
    + '<b>Stock cost</b>'
    + btn("tracked", "Supplier price at the time of the order")
    + btn("sku", "Price in the SKU")
    + '<span class="spacer" style="flex:1"></span>'
    // Both ways in, because one suits ten products and the other suits three
    // hundred, and the owner has said they want to do both at different times.
    + '<button class="db-chip" onclick="cogsGoToListings()">'
    + '<i class="ti ti-pencil"></i> Set costs by hand</button>'
    + (typeof cogsUploadOpen === "function"
        ? '<button class="db-chip" onclick="cogsUploadOpen()">'
          + '<i class="ti ti-upload"></i> Upload a cost sheet</button>' : '')
    + '</div>'
    + '<div class="cc" style="font-size:11px;margin-top:5px">'
    + _sEsc(COGSMODE.explain[COGSMODE.mode] || "")
    + '</div>'
    // WHERE COSTS ACTUALLY LIVE, said once, here.
    //
    // "i am confused to where put the cogs there are alof of sections asking
    //  for cogs now" -- and there are three screens that mention cost. Only ONE
    // of them stores anything: the COGS column on Listings. This bar's two
    // buttons both go there, the cost sheet is the same column in bulk, and the
    // Repricer only ever reads. None of that was written down anywhere, so three
    // mentions looked like three places to keep in step.
    + '<div class="cc" style="font-size:11px;margin-top:6px;padding-top:6px;'
    + 'border-top:1px solid var(--line);line-height:1.5">'
    + '<i class="ti ti-info-circle"></i> <b>There is one place costs are kept</b>'
    + ' — the COGS column on the Listings screen. Both buttons above go there;'
    + ' the cost sheet is the same column, filled in a spreadsheet. The Repricer,'
    + ' the Orders profit column and this page all read from it and never store'
    + ' a cost of their own.'
    + '</div>'
    + '</div>';
}

async function cogsModeSet(mode){
  if(COGSMODE.busy || mode === COGSMODE.mode) return;
  COGSMODE.busy = true;
  try{
    const j = await _sFetch("/cogs/mode", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({mode: mode, account_id: _sAcct(),
                            marketplace: (typeof WS_MARKET !== "undefined" ? WS_MARKET : "")})});
    if(j === null) return;
    if(!j || !j.ok){ toast((j && j.error) || "Could not change that"); return; }
    COGSMODE.mode = j.mode;
    cogsModeDraw();
    // COSTS ALREADY WORKED OUT ARE LEFT ALONE by design -- that is what stops
    // last month's profit moving. Changing the mode is therefore not enough on
    // its own, so the re-costing is offered rather than done silently.
    if(confirm("Costing changed to \"" + mode + "\".\n\n"
             + "Orders already costed keep what they were given, so last "
             + "month's profit does not move on its own.\n\n"
             + "Work the costs out again for the period on screen?")){
      await cogsRefreeze();
    }
  }finally{
    COGSMODE.busy = false;
  }
}

async function cogsRefreeze(){
  const s = (typeof SALES !== "undefined" && SALES.data) ? SALES.data : null;
  if(!s || !s.start || !s.end){ toast("Open a period first."); return; }
  toast("Working out costs again…");
  const j = await _sFetch("/cogs/refreeze", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({start: s.start, end: s.end, force: true,
                          account_id: _sAcct(),
                          marketplace: (typeof WS_MARKET !== "undefined" ? WS_MARKET : "")})});
  if(j === null) return;
  if(!j || !j.ok){ toast((j && j.error) || "Could not re-cost that period"); return; }
  toast("Costed " + (j.priced || 0) + " line(s)"
        + (j.unpriced ? ", " + j.unpriced + " still have no cost" : ""));
  if(typeof salesReload === "function") salesReload();
}

/* Costs are typed on the Listings screen, against the product, where the SKU
 * and the price are already in front of you. Sending someone there beats
 * building a second editor that would drift from the first. */
function cogsGoToListings(){
  if(typeof navTo === "function") navTo("listings");
  toast("Click a product's cost cell to set what it cost you.");
}
