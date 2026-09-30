// static/js/listings_ppc.js -- the advertising and economics line on a row. Moved word for word out of listings.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

/* THE WARNING-COUNT MARK IS GONE FROM THE LIST. _warnChip was here.
 *
 *     "there is still a symbol saying 1 warning worst: medium. i dont want this
 *      symbol at all, i already have 3 symbols for restricted compliance and
 *      claims risk, i will maintain those"
 *
 * It was a FOURTH marker on a card that already carries three, and the three it
 * sat beside are the ones that name what is actually wrong: .tileflag
 * (restricted / blocked), claimBadge (claims risk) and the compliance shield in
 * the table. "1 warning" named nothing -- you had to hover it to find out
 * whether it was a duplicate barcode or a missing product type, and by then the
 * three symbols beside it had usually already said so.
 *
 * NOTHING IS LOST, only un-duplicated. lsWarnings still decides the counts, the
 * status filters still use them, and every message is still listed in full in
 * the Safety & Compliance tab (_dwWarnings). What went is the badge, in all
 * four places that drew it: this one, the table cell (_warnCell), the detailed
 * row's chip (listrow_detailed.js) and the product page's hero (pdp.js).
 *
 * ONE RULE FROM THAT BADGE OUTLIVES IT, and it is why this paragraph stays.
 * ANYTHING PUT INSIDE .tileimg MUST BE position:absolute. That box is
 * `display:flex`, so an unpositioned span becomes a FLEX ITEM BESIDE THE <img>
 * and the picture is squeezed sideways to make room for it. That is what the
 * reported "images are broken on the first few cards" was -- the first few were
 * the ones with warnings, and the badge was a .tilefact, which is inline-flex.
 * .tiledot, .tilesel, .tileflag, .tileclaim and .tileinactive are all
 * positioned; _queuedChip was the other exception and was moved out to the
 * facts line instead.
 */

/* MARGIN, ROI AND PROFIT, on one line.
 *
 *     "Margin/ROI/Profit line: coloured badge -- green if positive, red if
 *      negative."
 *
 * ALL THREE COME OFF NUMBERS THE ROW ALREADY CARRIES. r.profit is the stored
 * figure the generator worked out with the real fee; margin is that over the
 * price and ROI is it over the cost. Neither ratio re-derives a FEE -- which is
 * the thing that must have one owner (Rule 12) -- they divide two numbers that
 * are already on the card.
 *
 * NOTHING IS SHOWN WITHOUT A PROFIT FIGURE. A margin computed from a missing
 * cost would be the "item that appears to cost nothing looks infinitely
 * profitable" mistake in another form; the line is simply absent, and the row
 * still has its price and its cost above.
 */
/* ================= PER-ASIN ADVERTISING ============================
 *
 * What advertising cost for THIS product over the last 30 days, on the card
 * that shows the product. From ads_daily via /ads/by-asin -- one query for the
 * whole screen, fetched once and cached, never one call per row.
 *
 * IT IS KEYED ON OUR ASIN, NEVER THE COMPETITOR'S.
 * Every row carries two: the ASIN embedded in its SKU, which is a COMPETITOR
 * reference used to pull product data while generating, and the account's own
 * live ASIN. Advertising is bought against ours. rowAsin() already owns that
 * distinction and returns {own, source}; only `own` is used here. Using the
 * source ASIN would attach a competitor's product code to our spend and read as
 * "this listing cost £34" on a listing that has never been advertised.
 *
 * ABSENT IS NOT ZERO. An ASIN with no row in the reply was never advertised in
 * the window, and the line is not drawn at all. A product that WAS advertised
 * and returned nothing shows its spend with a dash for ACOS -- that one is
 * worth seeing, because it is money that bought nothing.
 */
var PPC_BY_ASIN = null;        // null = not loaded yet, {} = loaded and empty
var PPC_META = {connected: false, note: "", start: "", end: ""};
var PPC_KEY = "";              // which account+marketplace PPC_BY_ASIN is for
var PPC_LOADING = false;

function _ppcKey(){
  const a = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
            ? CUR_ACCOUNT.id : "";
  const m = (typeof WS_MARKET !== "undefined" && WS_MARKET) ? WS_MARKET : "";
  return a + "|" + m;
}

async function loadPpcByAsin(){
  const key = _ppcKey();
  try{
    const a = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
              ? CUR_ACCOUNT.id : "";
    const m = (typeof WS_MARKET !== "undefined" && WS_MARKET) ? WS_MARKET : "";
    const r = await fetch("/ads/by-asin?days=30"
      + (m && m !== "__all__" ? "&marketplace=" + encodeURIComponent(m) : "")
      + (a ? "&account_id=" + encodeURIComponent(a) : ""));
    const j = await r.json();
    // A REPLY FOR THE KEY WE ASKED FOR ONLY. Landing after a switch, it was
    // stored under the NEW key and shown on the new account's shared ASINs
    // (master audit S7). Drop it; the next card asks again for the right key.
    if(_ppcKey() !== key) return;
    PPC_BY_ASIN = (j && j.ok && j.asins) ? j.asins : {};
    PPC_META = {connected: !!(j && j.connected), note: (j && j.note) || "",
                start: (j && j.start) || "", end: (j && j.end) || ""};
  }catch(e){
    // Never fatal. The listings page has to render with or without advertising.
    if(_ppcKey() !== key) return;
    PPC_BY_ASIN = {};
  }
  PPC_KEY = key;
}

/* Fetched ONCE per account+marketplace, lazily, from the first card that asks.
 *
 * Deliberately not wired into the page's load sequence: the advertising figures
 * are decoration on a screen whose job is listings, and making the listings wait
 * on an advertising query would trade something that matters for something that
 * does not. The first pass draws without them, the reply lands, and one
 * re-render fills them in.
 *
 * The key guard is what stops it looping and what makes a workspace switch
 * refetch: once loaded, PPC_BY_ASIN is non-null for that key and no card asks
 * again until the key changes. */
function _ppcEnsure(){
  if(PPC_LOADING) return;
  if(PPC_BY_ASIN !== null && PPC_KEY === _ppcKey()) return;
  PPC_LOADING = true;
  loadPpcByAsin().then(function(){
    PPC_LOADING = false;
    try{ if(typeof render === "function") render(); }catch(e){}
  });
}

function ppcFor(r){
  if(!PPC_BY_ASIN) return null;
  // Only the figures of the account and marketplace on screen: after a switch
  // the old map stayed until the refetch landed, so B's cards showed A's ad
  // spend on shared ASINs (review, 30 Sep 2026).
  if(PPC_KEY !== _ppcKey()) return null;
  const a = (typeof rowAsin === "function") ? (rowAsin(r) || {}).own : "";
  if(!a) return null;
  return PPC_BY_ASIN[String(a).trim().toUpperCase()] || null;
}

function _ppcLine(r){
  _ppcEnsure();
  const p = ppcFor(r);
  if(!p) return "";
  const spend = Number(p.spend);
  if(!isFinite(spend) || spend <= 0) return "";
  const cur = (typeof CUR_SYMBOL !== "undefined") ? CUR_SYMBOL : "";
  const acos = (p.acos === null || p.acos === undefined) ? null : Number(p.acos);
  // The same bands the profit chip uses, read the other way round: a LOW ACOS is
  // good. Spend that returned nothing is the worst case and is never green.
  const tone = acos === null ? "tone-bad"
             : (acos <= 25 ? "tone-ok" : (acos <= 50 ? "tone-warn" : "tone-bad"));
  const bits = ["ad spend " + cur + spend.toFixed(2)];
  bits.push(acos === null ? "no ad sales" : "ACOS " + acos.toFixed(1) + "%");
  if(p.ad_orders) bits.push(p.ad_orders + (p.ad_orders === 1 ? " order" : " orders"));
  const tip = "Sponsored Products, last 30 days (" + PPC_META.start + " to "
    + PPC_META.end + "), for this listing's own ASIN.\n"
    + "Spend " + cur + spend.toFixed(2)
    + " · clicks " + (p.clicks == null ? "—" : p.clicks)
    + " · ad sales " + cur + Number(p.ad_sales || 0).toFixed(2)
    + (acos === null
        ? "\nThis product was advertised and returned no attributed sales."
        : "\nACOS = ad spend ÷ ad sales.");
  return '<div style="margin-top:4px"><span class="profchip ' + tone + '" title="'
       + esc(tip) + '"><i class="ti ti-speakerphone"></i> ' + esc(bits.join(" · "))
       + '</span></div>';
}

function _econLine(r){
  const p = Number(String(r.profit == null ? "" : r.profit).replace(/[^0-9.\-]/g, ""));
  if(!isFinite(p) || String(r.profit || "").trim() === "") return "";
  const price = Number(String(r.price == null ? "" : r.price).replace(/[^0-9.\-]/g, ""));
  const c = (typeof cogsOf === "function") ? cogsOf(r) : {cost: null};
  const cost = (c && c.cost != null) ? Number(c.cost) : null;
  const cur = (typeof CUR_SYMBOL !== "undefined") ? CUR_SYMBOL : "";
  const margin = (isFinite(price) && price > 0) ? (p / price * 100) : null;
  const roi = (cost != null && cost > 0) ? (p / cost * 100) : null;
  const bits = [];
  if(margin != null) bits.push("margin " + margin.toFixed(1) + "%");
  if(roi != null)    bits.push("ROI " + roi.toFixed(1) + "%");
  bits.push(cur + p.toFixed(2));
  // THE SAME CHIP THE LIVE TILE USES, with the same thresholds.
  //
  //     "Cards are inconsistently formatted -- some show different fields,
  //      different arrangements."
  //
  // They did, and this was one of them: a card built from an app row and a card
  // built from Amazon's catalogue sit side by side in the same grid on the Live
  // tab, and the second has always shown its profit as a .profchip while the
  // first showed nothing at all. Adding a THIRD look here would have made it
  // worse. Same class, same wording, same margin bands (liveTile: 25% and 10%),
  // so the only thing that differs between the two cards is where the number
  // came from -- which is what the tooltip is for.
  const tone = margin == null ? "" : (margin >= 25 ? "tone-ok"
                                    : (margin >= 10 ? "tone-warn" : "tone-bad"));
  return `<div style="margin-top:5px"><span class="profchip ${tone}"`
       + ` title="From the profit stored on this listing — worked out when it was`
       + ` generated, with Amazon's fee rather than a flat percentage.`
       + ` Margin = profit ÷ price · ROI = profit ÷ what the stock cost.">`
       + esc(bits.join(" · ")) + `</span></div>`;
}
