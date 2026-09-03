/* static/js/revenue.js -- what one unit earns, in a panel beside the list.
 *
 *     "Currently clicking 'Calculate revenue' navigates to the product detail
 *      page. Amazon opens a side drawer with a Revenue Calculator."
 *
 * It did, and navigating away is the wrong answer to "what does this one make?"
 * -- you lose the list, the filter and the scroll to read four numbers, and
 * then have to find your way back to compare it with the row underneath.
 *
 * ═══ WHAT THIS FILE DOES NOT DO ════════════════════════════════════════════
 *
 * IT COMPUTES NOTHING. Every figure comes from /listing/revenue, which reads
 * the three-tier fee resolver (domain/amazon_fees), the cost resolver
 * (domain/cogs) and the 30-day metrics -- the same three the row above it uses.
 * A calculator that did its own arithmetic in the browser would be a second
 * opinion about a fee, and it would be the one people believed because it is
 * the one with "Revenue Calculator" written on it (CLAUDE.md Rule 12).
 *
 * IT CALLS AMAZON NOT AT ALL. The fee tiers are read from what is stored, so
 * dragging the price through a dozen values costs nothing and works with SP-API
 * down. Asking Amazon for this product's own fee is a different button, on the
 * Repricer, and it stays there.
 *
 * ═══ WHY THE BRIEF'S ROW LIST IS SHORTER HERE ══════════════════════════════
 *
 * The brief asks for Storage cost, Fulfilment cost and Miscellaneous. This app
 * holds none of the three per unit -- there is no storage table, no per-unit
 * fulfilment cost for a merchant listing, and no miscellaneous field anywhere.
 * Drawing three boxes that are always empty would suggest the figures below
 * account for them. They do not, and the panel says so in one line rather than
 * pretending with three inputs (Rule 4).
 */

let RC_SKU = "";
let RC_DATA = null;
let RC_BUSY = false;
let RC_TIMER = null;

/* Open the calculator for one listing. `price` seeds the box so the panel opens
 * on the price you were looking at rather than on zero. */
function rcOpen(sku, price){
  RC_SKU = String(sku || "");
  if(!RC_SKU) return;
  let host = document.getElementById("revcalc");
  if(!host){
    host = document.createElement("aside");
    host.id = "revcalc";
    host.className = "rc";
    document.body.appendChild(host);
    // The scrim is a sibling, not a parent: a click on it closes, a click
    // inside the panel must not.
    const scrim = document.createElement("div");
    scrim.id = "revscrim";
    scrim.className = "rc-scrim";
    scrim.onclick = rcClose;
    document.body.insertBefore(scrim, host);
  }
  document.getElementById("revscrim").classList.add("in");
  host.classList.add("in");
  RC_DATA = null;
  rcRender(price);
  rcFetch(price);
  document.addEventListener("keydown", _rcEsc);
}

function _rcEsc(ev){
  if(ev.key !== "Escape") return;
  // Not while a number is being typed -- Escape in a box should abandon the
  // box, not the panel.
  const t = ev.target;
  if(t && t.tagName === "INPUT"){ t.blur(); return; }
  rcClose();
}

function rcClose(){
  const host = document.getElementById("revcalc");
  const scrim = document.getElementById("revscrim");
  if(host) host.classList.remove("in");
  if(scrim) scrim.classList.remove("in");
  document.removeEventListener("keydown", _rcEsc);
  if(RC_TIMER){ clearTimeout(RC_TIMER); RC_TIMER = null; }
  RC_SKU = "";
}

/* Ask the server. DEBOUNCED, because this is wired to oninput: typing "24.99"
 * is five keystrokes and would otherwise be five requests, the last four of
 * which describe prices nobody meant. */
function rcAsk(){
  if(RC_TIMER) clearTimeout(RC_TIMER);
  RC_TIMER = setTimeout(function(){ RC_TIMER = null; rcFetch(); }, 260);
  // The inputs keep their own values; only the figures below them are stale.
  const host = document.getElementById("revcalc");
  if(host) host.classList.add("stale");
}

async function rcFetch(seedPrice){
  const sku = RC_SKU;
  if(!sku) return;
  const price = (seedPrice !== undefined && seedPrice !== null)
    ? seedPrice : _rcVal("rc_price");
  const ship = _rcVal("rc_ship");
  RC_BUSY = true;
  try{
    let url = "/listing/revenue?sku=" + encodeURIComponent(sku)
            + "&price=" + encodeURIComponent(price === "" ? "0" : price)
            + "&shipping=" + encodeURIComponent(ship === "" ? "0" : ship);
    if(typeof acctUrl === "function") url = acctUrl(url);
    const j = await (await fetch(url)).json();
    // A LATER OPEN WINS. Closing and reopening on another listing while this
    // was in flight would otherwise paint the first one's figures under the
    // second one's name.
    if(RC_SKU !== sku) return;
    RC_DATA = j && j.ok ? j : {error: (j && j.error) || "could not work it out"};
  }catch(e){
    if(RC_SKU !== sku) return;
    RC_DATA = {error: String((e && e.message) || e)};
  }finally{
    RC_BUSY = false;
  }
  rcRender();
}

function _rcVal(id){
  const el = document.getElementById(id);
  return el ? String(el.value || "").trim() : "";
}

function _rcMoney(v, cur){
  if(v === null || v === undefined || v === "") return '<span class="dash">—</span>';
  const n = Number(v);
  return esc((cur || "") + (isFinite(n) ? n.toFixed(2) : String(v)));
}

function rcRender(seedPrice){
  const host = document.getElementById("revcalc");
  if(!host) return;
  const d = RC_DATA || {};
  const cur = (typeof CUR_SYMBOL !== "undefined") ? CUR_SYMBOL : "";
  const r = (typeof ROWS !== "undefined")
    ? ROWS.find(x => String(x.sku) === RC_SKU) : null;
  const title = (r && r.title) ? r.title : RC_SKU;

  // The boxes keep whatever is in them across a re-render -- the panel redraws
  // on every reply and rebuilding them from the server's echo would fight the
  // cursor on the third keystroke.
  const priceNow = (seedPrice !== undefined && seedPrice !== null)
    ? String(seedPrice)
    : (_rcVal("rc_price") || (d.price != null ? String(d.price) : ""));
  const shipNow = _rcVal("rc_ship") || (d.shipping ? String(d.shipping) : "");

  const feeLines = ((d.fees || {}).lines || []).map(function(l){
    // CHARGED AND NOT-CHARGED BOTH SHOWN. A fee you are not paying is
    // information -- "FBA 0.00, you post this yourself" answers a question
    // that a missing row leaves open. breakdown_for returns `charged` for
    // exactly this; the dimming is the only difference.
    return '<div class="rc-row' + (l.charged ? "" : " off") + '" title="'
      + esc(l.note || l.why || "") + '">'
      + '<span class="rc-k">' + esc(l.label) + '</span>'
      + '<span class="rc-v">' + (l.charged ? _rcMoney(l.amount, cur)
                                           : '<span class="dash">—</span>')
      + '</span></div>';
  }).join("");

  host.innerHTML =
      '<div class="rc-head">'
    +   '<div class="rc-title" title="' + esc(title) + '">' + esc(title) + '</div>'
    +   '<button class="rc-x" onclick="rcClose()" title="Close (Esc)">'
    +     '<i class="ti ti-x"></i></button>'
    + '</div>'
    + '<div class="rc-sku">' + esc(RC_SKU)
    +   (d.asin ? ' · ASIN ' + esc(d.asin) : "")
    + '</div>'

    + (d.error
        ? '<div class="rc-err"><i class="ti ti-alert-triangle"></i> ' + esc(d.error) + '</div>'
        : "")

    // ---- what the buyer pays -----------------------------------------
    + '<div class="rc-sec">What the buyer pays</div>'
    + '<div class="rc-row"><span class="rc-k">Item price</span>'
    +   '<span class="rc-v"><span class="rc-cur">' + esc(cur) + '</span>'
    +   '<input id="rc_price" class="rc-in" inputmode="decimal" value="'
    +   esc(priceNow) + '" oninput="rcAsk()"></span></div>'
    + '<div class="rc-row"><span class="rc-k">Delivery charged</span>'
    +   '<span class="rc-v"><span class="rc-cur">' + esc(cur) + '</span>'
    +   '<input id="rc_ship" class="rc-in" inputmode="decimal" placeholder="0.00" value="'
    +   esc(shipNow) + '" oninput="rcAsk()"></span></div>'
    // WHY THIS LINE EXISTS AND IS NOT JUST THE PRICE. Amazon's referral fee is
    // charged on the total the buyer paid, postage included -- a calculator
    // that took the item price alone understates the fee on every order with
    // delivery on it.
    + '<div class="rc-row total" title="Amazon charges its referral fee on this '
    +   'total, not on the item price alone.">'
    +   '<span class="rc-k">Sales price</span>'
    +   '<span class="rc-v">' + _rcMoney(d.gross, cur) + '</span></div>'

    // ---- what Amazon takes -------------------------------------------
    + '<div class="rc-sec">What Amazon takes'
    +   (d.fees && d.fees.basis
        ? '<span class="rc-basis" title="' + esc((d.fees.detail || ""))
          + '">' + esc(_rcBasis(d.fees.basis)) + '</span>' : "")
    + '</div>'
    + (feeLines || '<div class="rc-none">Nothing worked out yet.</div>')
    + '<div class="rc-row total"><span class="rc-k">Amazon’s cut</span>'
    +   '<span class="rc-v neg">' + _rcMoney(d.fees_total, cur) + '</span></div>'

    // ---- what it cost you --------------------------------------------
    + '<div class="rc-sec">What it cost you</div>'
    + '<div class="rc-row" title="' + esc(_rcCostWhy(d)) + '">'
    +   '<span class="rc-k">Unit cost</span>'
    +   '<span class="rc-v">' + _rcMoney(d.cost, cur)
    +   (d.cost_source ? ' <span class="rc-src">' + esc(d.cost_source) + '</span>' : "")
    +   '</span></div>'

    // ---- the answer ---------------------------------------------------
    + '<div class="rc-sec">What is left</div>'
    + '<div class="rc-row big' + (_rcNeg(d.net) ? " neg" : "") + '">'
    +   '<span class="rc-k">Net proceeds</span>'
    +   '<span class="rc-v">' + _rcMoney(d.net, cur) + '</span></div>'
    + '<div class="rc-row' + (_rcNeg(d.net) ? " neg" : "") + '">'
    +   '<span class="rc-k">Net margin</span>'
    +   '<span class="rc-v">'
    +   (d.margin_pct == null ? '<span class="dash">—</span>'
                              : esc(Number(d.margin_pct).toFixed(1) + "%"))
    +   '</span></div>'
    + (d.units_30d != null
        ? '<div class="rc-row"><span class="rc-k">Sold, last 30 days</span>'
          + '<span class="rc-v">' + esc(String(d.units_30d)) + ' units'
          + (d.net != null && Number(d.units_30d) > 0
              ? ' · ' + _rcMoney(Number(d.net) * Number(d.units_30d), cur)
              : "")
          + '</span></div>'
        : "")

    // ---- WHAT THIS NUMBER IS NOT --------------------------------------
    // The single most important line in the panel. "Net proceeds" is what
    // arrives minus Amazon's cut minus the unit cost, and nothing else: this
    // app holds no per-unit postage label, ad spend, storage or returns cost,
    // so they cannot be in it. A figure called "profit" with four costs
    // silently missing is worse than one that names what it left out.
    + '<div class="rc-note">Amazon’s cut and what the stock cost, and nothing '
    +   'else. Postage you buy, ads, storage and returns are not in this — '
    +   'this app holds no per-unit figure for any of them.</div>'
    + (d.cost == null
        ? '<div class="rc-note warn"><i class="ti ti-alert-triangle"></i> '
          + 'No cost is known for this SKU, so there is no net figure. Set one '
          + 'in the Cost box on the row.</div>'
        : "");
  host.classList.remove("stale");
}

function _rcNeg(v){ return v != null && Number(v) < 0; }

function _rcBasis(b){
  // The three tiers, in words. The panel is read on its own, and "actual"
  // means nothing without them.
  if(b === "actual") return "measured on this product’s own sales";
  if(b === "quoted") return "Amazon’s own quote";
  return "this account’s measured rate";
}

function _rcCostWhy(d){
  if(d.cost == null) return "No cost known for this SKU.";
  if(d.cost_source === "manual") return "You typed this, so it beats the SKU.";
  if(d.cost_source === "sku") return "Read from the SKU’s price prefix.";
  return "";
}
