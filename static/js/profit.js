/* static/js/profit.js -- keep the profit on a row in step with its price.
 *
 *     "the listing was saying that the profit in this item is 1.76 and so i
 *      changed the selling price by 3 pounds but the app was not able to change
 *      the profit calculation at the glance at the same moment in mili seconds,
 *      the profit remained the same value as it was before"
 *
 * WHY IT DID NOT MOVE. r.profit is a STORED figure. The generator worked it out
 * once, when the listing was written, and wrote it into a column -- listings.js
 * says so where it draws it: "r.profit is the stored figure the generator
 * worked out with the real fee". Changing the price wrote the new price to the
 * row and left that column alone, so the number beside it went on describing a
 * price that no longer existed. Margin and ROI are derived from it, so all
 * three were stale together.
 *
 * WHY THE ARITHMETIC IS NOT DONE HERE. Profit is price minus cost minus what
 * Amazon takes, and "what Amazon takes" is the part that is easy to get wrong:
 * it is a three-tier resolver (what Amazon actually took on settled orders,
 * else Amazon's own quote, else this account's MEASURED referral rate -- never
 * a flat 15%). That lives in domain/amazon_fees.py and is reached through
 * /listing/revenue, which routes/revenue_routes.py exists to be the one caller
 * of. A second copy in JavaScript would drift from it the first time a fee rule
 * changed, and would drift silently, because both would look plausible
 * (CLAUDE.md Rule 12).
 *
 * SO IT ASKS, AND IT IS FAST ENOUGH TO. /listing/revenue makes NO Amazon call --
 * its own docstring: "the drawer can be dragged through a dozen prices without
 * spending a single SP-API call". It reads a stored quote and a measured rate.
 * That is a local round trip, which is what "at the glance" needs.
 *
 * NOTHING IS WRITTEN. This updates the figure ON SCREEN. The stored column is
 * the generator's, and rewriting it from here would put a second author on a
 * column one thing owns.
 */

/* One in flight per SKU. Typing a price fires an edit per blur, and an older
 * reply landing after a newer one would paint the previous price's profit
 * against the current price -- the same out-of-order fault the barcode check
 * guards against. */
const _PROFIT_SEQ = {};

/* The figures a row shows for money, recomputed at `price`.
 *
 * Returns the reply, or null. Never throws: a listing whose cost is unknown has
 * no profit to show, and that is an answer, not a failure.
 */
async function profitAt(sku, price){
  if(!sku) return null;
  const seq = (_PROFIT_SEQ[sku] = (_PROFIT_SEQ[sku] || 0) + 1);
  const p = String(price == null ? "" : price).replace(/[^0-9.\-]/g, "");
  if(p === "") return null;
  let url = "/listing/revenue?sku=" + encodeURIComponent(sku)
          + "&price=" + encodeURIComponent(p);
  const r = (typeof ROWS !== "undefined" && ROWS.find)
    ? ROWS.find(x => String(x.sku) === String(sku)) : null;
  const mkt = (typeof rowMkt === "function" && r) ? rowMkt(r) : "";
  if(mkt) url += "&mkt=" + encodeURIComponent(mkt);
  /* THE COST THE SCREEN IS SHOWING, sent for the same reason the price is.
   *
   * cogsOf() is the one place that decides what cost a row displays, and it
   * still falls back to the SKU's price prefix. The SERVER stopped doing that
   * -- "lets remove the cogs from sku things entirely" -- so on this account it
   * resolves a cost for 1 row out of 86 while the screen shows one on 85.
   *
   * Without sending it, every recomputed profit on those 85 rows would come
   * back blank while the cost box beside it still read 9.99: the price would
   * change, the profit would vanish, and the two numbers on one line would be
   * answering different questions. The route uses this ONLY when it has no cost
   * of its own, so a cost actually set by the owner always wins.
   *
   * That the two disagree at all is the real defect and it is not fixed here --
   * fixing it means deciding whether 85 rows should stop showing a cost, which
   * is the owner's call, not a side effect of a profit refresh.
   */
  try{
    const c = (typeof cogsOf === "function" && r) ? cogsOf(r) : null;
    if(c && c.cost !== null && c.cost !== undefined && Number(c.cost) > 0)
      url += "&cost=" + encodeURIComponent(String(c.cost));
  }catch(e){}
  try{
    const j = await (await fetch(
      (typeof acctUrl === "function") ? acctUrl(url) : url)).json();
    if(seq !== _PROFIT_SEQ[sku]) return null;      // a newer price overtook this
    return (j && j.ok) ? j : null;
  }catch(e){ return null; }
}

/* Put the new figure on the row and redraw wherever it is showing.
 *
 * `net` is what /listing/revenue calls it, and its docstring is emphatic that
 * net proceeds is not profit and is not called profit -- it excludes ads,
 * storage and returns. The row's `profit` column has always meant the same
 * thing (price less cost less Amazon's cut), so this is the same quantity under
 * the name the row already uses, not a redefinition.
 */
async function profitRefresh(sku, price){
  const r = (typeof ROWS !== "undefined" && ROWS.find)
    ? ROWS.find(x => String(x.sku) === String(sku)) : null;
  if(!r) return;
  const before = r.profit;
  const j = await profitAt(sku, price);
  if(!j) return;
  // NO COST KNOWN MEANS NO PROFIT, and the row already handles a blank by
  // hiding the whole margin/ROI line rather than printing zeroes. An item that
  // appears to cost nothing looks infinitely profitable -- listrow_detailed.js
  // says exactly that where it draws the cost.
  r.profit = (j.net === null || j.net === undefined) ? "" : String(j.net);
  // Kept for the tooltip and the fee line, which read them if they are there.
  if(j.fees_total !== undefined) r.fees_total = j.fees_total;
  if(j.cost !== undefined && j.cost !== null) r.cogs = j.cost;
  if(String(before || "") === String(r.profit || "")) return;   // nothing moved
  _profitRepaint(sku);
}

function _profitRepaint(sku){
  // Whichever of the three places is showing this listing. Each already knows
  // how to draw a row from ROWS, so none of them needs telling what changed.
  try{
    if(typeof PDP_SKU !== "undefined" && String(PDP_SKU) === String(sku)
       && typeof pdpHeroRefresh === "function"){ pdpHeroRefresh(sku); return; }
    if(typeof DRAWER_SKU !== "undefined" && String(DRAWER_SKU) === String(sku)
       && typeof _rebuildDrawerData === "function"){ _rebuildDrawerData(sku); return; }
    if(typeof render === "function") render();
  }catch(e){}
}
