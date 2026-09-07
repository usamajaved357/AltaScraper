/* static/js/cogsmode.js -- where the stock cost on the Sales page comes from.
 *
 * IT SITS DIRECTLY UNDER THE PROFIT CARD because that is the card it explains.
 * A profit with uncosted units in it is knowingly higher than the truth, and the
 * way to fix it should be one click from the wrong number rather than on a
 * screen nobody thinks to open.
 *
 * THE TWO MODE BUTTONS ARE GONE, AND THIS IS WHY.
 *
 *     "i still see cost from supplier and cost in the sku thing on the top of
 *      the graph on the sales page"
 *
 * This bar offered a choice between "Supplier price at the time of the order"
 * and "Price in the SKU". Neither is a source any more:
 *
 *     "lets remove the cogs from sku things entirely, lets keep it simple, if
 *      the cogs of the sku are set by the user by bulk upload or one by one per
 *      sku, consider them for profit calculation, if those cogs are filled and
 *      also a person has put in the cogs per order in the all orders page,
 *      consider those cogs for profit calculation for all the orders"
 *
 * domain/order_cogs.resolve() accepts `mode` and IGNORES it -- proven by
 * measurement, not by reading: asked with tracked, sku and a nonsense string it
 * returns the same (7.5, 'manual') every time.
 *
 * SO THE CONTROL WAS WORSE THAN DEAD, IT WAS WRONG. jack_uk is stored as
 * `cogs_mode: tracked`, so its Sales page showed "Supplier price at the time of
 * the order" ticked -- a statement about how that account's profit is worked
 * out that had stopped being true. A toggle that does nothing is clutter; a
 * toggle that misdescribes the arithmetic is a reason to trust a wrong number.
 *
 * What replaces it is not a control but a SENTENCE: the two places a cost can
 * come from, in the order they are tried. Both buttons that DO something --
 * type a cost, upload a sheet -- are kept, because they were always the useful
 * half of this bar.
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
    // A STATEMENT, NOT A CHOICE. There is nothing to pick between any more --
    // see the note at the top of this file.
    + '<span class="cc" style="font-size:12px">a cost you set against the order,'
    + ' else a cost you set against the product</span>'
    + '<span class="spacer" style="flex:1"></span>'
    // Both ways in, because one suits ten products and the other suits three
    // hundred, and the owner has said they want to do both at different times.
    + '<button class="db-chip" onclick="cogsGoToListings()">'
    + '<i class="ti ti-pencil"></i> Set costs by hand</button>'
    + (typeof cogsUploadOpen === "function"
        ? '<button class="db-chip" onclick="cogsUploadOpen()">'
          + '<i class="ti ti-upload"></i> Upload a cost sheet</button>' : '')
    // Re-costing is still worth offering: typing a cost does NOT move orders
    // that were already costed, deliberately, so that last month's profit does
    // not shift under you. This is how you ask for it when you do want it.
    + '<button class="db-chip" onclick="cogsRefreeze()">'
    + '<i class="ti ti-refresh"></i> Work costs out again</button>'
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
    + '<br>Nothing is read out of a SKU name or a supplier price any more. A'
    + ' product with no cost set against it has <b>no</b> cost — not a cost of'
    + ' zero — so its profit is left blank rather than counted as pure margin.'
    + '</div>'
    + '</div>';
}

/* cogsModeSet() IS GONE. It POSTed a costing mode that nothing reads any more --
 * see the note at the top of this file. The /cogs/mode endpoint still answers,
 * because removing a route is a separate decision from removing a control, but
 * nothing in the app now asks it to CHANGE anything. */

async function cogsRefreeze(){
  const s = (typeof SALES !== "undefined" && SALES.data) ? SALES.data : null;
  if(!s || !s.start || !s.end){ toast("Open a period first."); return; }
  toast("Working out costs again…");
  const j = await _sFetch("/cogs/refreeze", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({start: s.start, end: s.end, force: true,
                          account: _sAcct(),
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
