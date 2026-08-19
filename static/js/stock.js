/* ============ THE STOCK COCKPIT ============
 *
 *   "now start building the inventory feature same like orbit in our app"
 *
 * Orbit's Inventory Cockpit, rebuilt on this app's own data. The arithmetic and
 * every rule live in domain/inventory_view.py; nothing is worked out here. This
 * file draws what the server sends and nothing else -- which is why the headline
 * and the table can never disagree, a fault this app has had to fix on three
 * other screens.
 *
 * WHAT IS THE SAME AS ORBIT, AND WHAT IS NOT
 *
 * Same: the shape of the screen (a banner that states the one urgent fact, then
 * four counts, then a per-SKU ledger), the five state names in Orbit's own order
 * -- safe, watch, order soon, order now, stockout likely -- and its measured
 * card sizes, weights and colours (see .stk- in dashboard.css).
 *
 * Not the same, deliberately: Orbit's headline unit is "network units = FBA +
 * AWD + 3PL + verified inbound". Measured across all six accounts on 18 Aug
 * 2026, this seller has ZERO FBA units -- everything is merchant-fulfilled and
 * bought from an eBay supplier when an order lands. Copying those four columns
 * would give three permanently empty ones and a fourth whose heading lies.
 *
 * So the question changes to the one that matters here: when an order arrives,
 * can it be sourced before the promise is broken? The repricer has been
 * recording every supplier's dispatch time for weeks, so that is answerable --
 * and it is something Orbit cannot do at all, having no supplier data.
 */

let STOCK = {rows: [], cockpit: null, counts: {}, legend: [], filter: "",
             q: "", sort: "status", dir: 1, loading: false};

function _skEsc(s){
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function _skSym(){
  try{ return (typeof CUR_SYMBOL !== "undefined" && CUR_SYMBOL) || ""; }
  catch(e){ return ""; }
}
/* `ccy` is optional and only used where a figure may not be in the account's own
   currency -- Amazon settles a refund in the marketplace's currency, and the
   money-back page can show two at once. Everywhere else the account symbol is
   right and passing nothing keeps it. */
function _skMoney(v, ccy){
  if(v === null || v === undefined || v === "") return "—";
  const sym = ccy ? _skCcySym(ccy) : _skSym();
  return sym + Number(v).toLocaleString(undefined,
    {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
function _skCcySym(cc){
  // One map, in static/js/money.js. This copy rendered Canadian dollars as "$"
  // where weekly.js rendered them "C$" -- on a screen showing both markets that
  // is the difference between a readable figure and a wrong one (Rule 12).
  return (typeof curSymbol === "function") ? curSymbol(cc, _skSym()) : (cc ? cc + " " : _skSym());
}
/* Orbit writes big money as "$141K". Same rule: thousands get a K, and only
   above 10,000 -- "9.4K" hides more than it saves. */
function _skShort(v){
  if(v === null || v === undefined) return "—";
  const n = Number(v);
  if(Math.abs(n) >= 10000) return _skSym() + (n / 1000).toFixed(0) + "K";
  return _skMoney(n);
}
function _skNum(v){
  return (v === null || v === undefined) ? "—"
       : Number(v).toLocaleString();
}
function _skDate(iso){
  if(!iso) return "—";
  // Built by hand rather than with toLocaleDateString, which follows the
  // machine's locale -- a server set to another language prints a month name
  // the owner does not read. Same rule as domain/order_sources.py.
  const m = ["Jan","Feb","Mar","Apr","May","Jun",
             "Jul","Aug","Sep","Oct","Nov","Dec"];
  const p = String(iso).split("-");
  if(p.length !== 3) return String(iso);
  return Number(p[2]) + " " + (m[Number(p[1]) - 1] || "?");
}
/* The state's css class. The server sends Orbit's words ("order soon"); the
   stylesheet wants one token. */
const _SK_CLS = {"safe": "safe", "watch": "watch", "order soon": "soon",
                 "order now": "now", "stockout likely": "out",
                 "unknown": "unknown"};

function stockOnOpen(){ if(!STOCK.rows.length) stockLoad(); }

async function stockLoad(force){
  const host = document.getElementById("stockwrap");
  if(!host) return;
  if(STOCK.loading) return;
  STOCK.loading = true;
  if(force || !STOCK.rows.length) host.innerHTML = _skSkeleton();
  let j = null;
  try{
    const qs = [];
    try{
      if(typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
        qs.push("id=" + encodeURIComponent(CUR_ACCOUNT.id));
      if(typeof WS_MARKET !== "undefined" && WS_MARKET && WS_MARKET !== "__all__")
        qs.push("marketplace=" + encodeURIComponent(WS_MARKET));
    }catch(e){}
    j = await (await fetch("/inventory/stock"
      + (qs.length ? "?" + qs.join("&") : ""))).json();
  }catch(e){
    host.innerHTML = '<div class="odp-note warn" style="padding:14px">'
      + 'Could not load the stock view: ' + _skEsc(String(e)) + '</div>';
    STOCK.loading = false;
    return;
  }finally{ STOCK.loading = false; }

  if(!j || !j.ok){
    host.innerHTML = '<div class="odp-note warn" style="padding:14px">'
      + _skEsc((j && j.error) || "Could not load the stock view") + '</div>';
    return;
  }
  STOCK.rows = j.rows || [];
  STOCK.cockpit = j.cockpit || null;
  STOCK.counts = j.counts || {};
  STOCK.legend = j.legend || [];
  STOCK.note = j.note || "";
  STOCK.assumedLead = j.assumed_lead_days;
  STOCK.toOrder = j.to_order || [];
  STOCK.forecast = j.forecast || [];
  STOCK.horizon = j.horizon_days || 30;
  stockRender();
}

/* The loading state is the shape of the real thing, so nothing jumps when the
   data lands. Orbit shimmers its skeletons (_skeletonShimmer_guoor_1); so does
   this, and both stop under prefers-reduced-motion. */
function _skSkeleton(){
  const card = '<div class="stk-card"><div class="stk-skel" style="height:12px;'
             + 'width:70%"></div><div class="stk-skel" style="height:24px;'
             + 'width:50%"></div><div class="stk-skel" style="height:11px;'
             + 'width:85%"></div></div>';
  return '<div class="stock">'
    + '<div class="stk-banner"><div class="stk-bannermain">'
    + '<div class="stk-skel" style="height:11px;width:120px;margin-bottom:8px"></div>'
    + '<div class="stk-skel" style="height:32px;width:60%;margin-bottom:8px"></div>'
    + '<div class="stk-skel" style="height:13px;width:80%"></div></div>'
    + '<div class="stk-bannercards">' + card + card + card + '</div></div>'
    + '<div class="stk-grid">' + card + card + card + card + '</div></div>';
}

/* ============ THE PAGES ============
 *
 *   "i want each and every feature and page about the inventory and ppc, of
 *    orbit into my app"
 *
 * Orbit splits inventory across tabs -- Overview, Forecasting, Actions -- and
 * this screen had all three stacked in one scroll. On a phone that is four
 * screens of scrolling before the product table, and the banner at the top
 * stops being the first thing you see, which was its whole job.
 *
 * The banner and the cockpit cards stay ABOVE the tabs on every page, because
 * "what is about to run out" is context for all three, not a page of its own.
 *
 * Tab state lives in STOCK so a redraw keeps it. It is deliberately NOT in the
 * URL: this is one screen, and a link to a tab that only exists after data
 * loads would open on an empty page.
 */
const STK_TABS = [
  {k: "overview", t: "Overview", i: "ti-list-details",
   d: "Every product, what you have, and how fast it is going."},
  {k: "actions", t: "What to order", i: "ti-shopping-cart-plus",
   d: "How many to buy, and the last day to order it."},
  {k: "forecast", t: "If nothing changes", i: "ti-chart-line",
   d: "Units short and cost to cover, at today's rate."},
  // THE PACE, MEASURED PROPERLY. Its own tab because it answers a different
  // question from "what do I have": how fast does this really sell, counting
  // only the days it was there to be sold.
  {k: "coverage", t: "Real pace & cover", i: "ti-gauge",
   d: "How fast each product sells on the days it is IN STOCK, and how long "
      + "what you have will last at that rate."},
  {k: "money", t: "Money back", i: "ti-receipt-refund",
   d: "Units Amazon lost, damaged or over-charged you for."},
];

function stockTab(k){
  STOCK.tab = k;
  stockRender();
  // The tabs sit under a banner that can be tall. Jumping to them means the
  // page you just chose is the thing you are looking at.
  const el = document.getElementById("stk_tabbar");
  if(el && el.scrollIntoView) el.scrollIntoView({block: "start", behavior: "smooth"});
}

function _skTabBar(){
  const cur = STOCK.tab || "overview";
  return '<div class="stk-tabbar" id="stk_tabbar" role="tablist">'
    + STK_TABS.map(function(t){
        return '<button class="stk-tab' + (t.k === cur ? " on" : "") + '" '
             + 'role="tab" aria-selected="' + (t.k === cur) + '" '
             + 'title="' + _skEsc(t.d) + '" '
             + 'onclick="stockTab(' + jsArg(t.k) + ')">'
             + '<i class="ti ' + t.i + '"></i> ' + _skEsc(t.t) + '</button>';
      }).join("")
    + '</div>';
}

function stockRender(){
  const host = document.getElementById("stockwrap");
  if(!host) return;
  const c = STOCK.cockpit;
  if(!c){ host.innerHTML = ""; return; }
  if(!STOCK.rows.length){
    host.innerHTML = '<div class="odp-note" style="padding:16px;'
      + 'border:1px dashed var(--line);border-radius:10px">'
      + _skEsc(STOCK.note || "Nothing to show yet.") + '</div>';
    return;
  }
  const tab = STOCK.tab || "overview";
  let body;
  if(tab === "actions")        body = _skOrderList();
  else if(tab === "forecast")  body = _skForecast();
  else if(tab === "coverage")  body = _skCoverage();
  else if(tab === "money")     body = _skMoneyBack();
  else                         body = _skFilters() + _skLedger();
  host.innerHTML = '<div class="stock">' + _skBanner(c) + _skCards(c)
                 + _skTabBar() + body + _skFooter(c) + '</div>';
}

/* THE BANNER. One fact, in the largest type on the screen.
 *
 * Orbit leads with "141 critical ASINs need action". The same idea, but it says
 * the PRODUCT and the DATE when there is one, because "5 need action" sends you
 * looking and "AltaboltaVoo Ceiling Fan runs out today" does not. */
function _skBanner(c){
  const crit = c.critical || 0, out = c.out_now || 0;
  const n = c.next_stockout;
  let head, cls, sub;
  // ALREADY OUT LEADS, because it is a fact rather than a forecast and there is
  // nothing left to plan -- the listing is unbuyable now.
  if(out > 0){
    head = out + " product" + (out === 1 ? " is" : "s are") + " out of stock";
    cls = "bad";
  }else if(crit > 0){
    head = crit + " product" + (crit === 1 ? "" : "s") + " need"
         + (crit === 1 ? "s" : "") + " ordering";
    cls = "bad";
  }else if(c.covered_skus){
    head = "Nothing needs ordering";
    cls = "ok";
  }else{
    head = "Not enough sales to judge yet";
    cls = "";
  }
  if(n && n.already_out){
    sub = "<b>" + _skEsc(n.title || n.sku) + "</b> is showing zero and still "
        + "selling — it cannot be bought right now."
        + (out > 1 ? " It is the fastest-selling of the " + out + "." : "");
  }else if(n){
    sub = "Next to run out: <b>" + _skEsc(n.title || n.sku) + "</b> on <b>"
        + _skDate(n.date) + "</b>"
        + (n.cover_days !== null && n.cover_days !== undefined
            ? " — about " + n.cover_days + " days of cover left." : ".");
  }else{
    sub = "No product has both a quantity and sales in the last "
        + (c.window_days || 30) + " days, so nothing can be projected yet.";
  }
  return '<div class="stk-banner">'
    + '<div class="stk-bannermain">'
    +   '<div class="stk-eyebrow">Stock cockpit</div>'
    +   '<h3 class="stk-headline ' + cls + '">' + _skEsc(head) + '</h3>'
    +   '<p class="stk-sub">' + sub + '</p>'
    + '</div>'
    + '<div class="stk-bannercards">'
    +   _skCard("risk", "Revenue at risk", _skShort(c.at_risk_value),
               _skNum(c.at_risk_units) + " units at risk",
               "A forecast, not a settled figure. For every product that runs "
             + "out before more can arrive, the sales it would have made "
             + "during the gap: velocity x days short x selling price. It is "
             + "not the value of the product — losing three days of sales is "
             + "not losing the product.")
    +   _skCard("good", "Stock at cost", _skShort(c.value_at_cost),
               _skNum(c.listed_units) + " units · "
             + (c.uncosted_skus ? c.uncosted_skus + " with no cost"
                                : "every product costed"),
               "What the stock on your listings cost you. Orbit's rule: "
             + "displayed units x resolved cost per unit. A product with no "
             + "cost recorded contributes nothing and is counted separately "
             + "rather than treated as free.")
    +   _skCard("good", "Avg cover",
               (c.avg_cover_days === null ? "—" : c.avg_cover_days + "d"),
               c.covered_skus + " product" + (c.covered_skus === 1 ? "" : "s")
             + " with sales",
               "How many days the stock lasts at the current rate, averaged. "
             + "Only over products that HAVE a rate — averaging in the ones "
             + "nobody buys would describe products you are not selling.")
    + '</div></div>';
}

function _skCard(kind, label, value, sub, help){
  return '<div class="stk-card ' + kind + '"'
    + (help ? ' title="' + _skEsc(help) + '"' : '') + '>'
    + '<span class="lbl">' + _skEsc(label)
    + (help ? ' <i class="ti ti-info-circle" style="opacity:.5"></i>' : '')
    + '</span>'
    + '<span class="val">' + value + '</span>'
    + '<span class="sub">' + sub + '</span></div>';
}

function _skCards(c){
  return '<div class="stk-grid">'
    + _skCard("info", "Listed units", _skNum(c.listed_units),
             c.skus + " product" + (c.skus === 1 ? "" : "s"),
             "The quantity on your Amazon listings. NOT a warehouse count — "
           + "these are merchant-fulfilled, so this is what has been PROMISED "
           + "to Amazon, and the stock itself is bought when an order lands.")
    + _skCard("cost", "Stock at cost", _skMoney(c.value_at_cost),
             c.valued_skus + " of " + c.skus + " priced",
             "Sum of units x cost per unit, over the products that have a "
           + "cost recorded. Set the rest on the Costs sheet.")
    + _skCard("risk", "Need ordering", _skNum(c.critical),
             "order now or already out",
             "Products whose cover is shorter than the time it takes to get "
           + "more from the supplier. These are the ones that will break a "
           + "delivery promise.")
    + _skCard("risk", "Review queue", _skNum(c.review_queue),
             "rows with something missing",
             "Orbit's phrase: rows that are not fully safe and therefore "
           + "deserve operator review. Here that means a missing cost, "
           + "quantity, supplier or sales history — each one weakens the "
           + "decision the row is asking you to make.")
    + '</div>';
}

/* Filter by state. The counts sit on the buttons so the shape of the catalogue
   is readable without opening anything. */
function _skFilters(){
  const order = ["stockout likely", "order now", "order soon", "watch", "safe",
                 "unknown"];
  let h = '<div class="stk-filters">'
    + '<button class="stk-fbtn' + (STOCK.filter ? "" : " on") + '" '
    + 'onclick="stockFilter(\'\')">All<span class="n">'
    + STOCK.rows.length + '</span></button>';
  order.forEach(function(k){
    const n = STOCK.counts[k] || 0;
    if(!n) return;
    const meaning = (STOCK.legend.find(function(x){ return x.key === k; })
                     || {}).meaning || "";
    // jsArg(), not JSON.stringify: the app's own helper, because a stringified
    // value pasted into a double-quoted attribute closes the attribute. There
    // is a test that refuses this pattern anywhere in the app, and it caught
    // this line.
    h += '<button class="stk-fbtn' + (STOCK.filter === k ? " on" : "") + '" '
      + 'title="' + _skEsc(meaning) + '" '
      + 'onclick="stockFilter(' + jsArg(k) + ')">'
      + _skEsc(k) + '<span class="n">' + n + '</span></button>';
  });
  h += '<span style="flex:1"></span>'
    + '<input class="ed" id="stk_q" placeholder="Search SKU, ASIN or name…" '
    + 'value="' + _skEsc(STOCK.q) + '" oninput="stockSearch(this.value)" '
    + 'style="width:230px;padding:5px 10px;font-size:12px">'
    + '</div>';
  return h;
}

function stockFilter(k){ STOCK.filter = k; stockRender(); }
function stockSearch(v){
  STOCK.q = v || "";
  // Only the table is redrawn, so the caret stays where it is.
  const t = document.getElementById("stk_ledger");
  if(t) t.outerHTML = _skLedger();
}
function stockSort(col){
  if(STOCK.sort === col) STOCK.dir = -STOCK.dir;
  else { STOCK.sort = col; STOCK.dir = 1; }
  const t = document.getElementById("stk_ledger");
  if(t) t.outerHTML = _skLedger();
}

function _skVisible(){
  const q = (STOCK.q || "").trim().toLowerCase();
  let rows = STOCK.rows.filter(function(r){
    if(STOCK.filter && r.status !== STOCK.filter) return false;
    if(!q) return true;
    return (String(r.sku) + " " + String(r.asin) + " " + String(r.title))
             .toLowerCase().indexOf(q) >= 0;
  });
  const key = STOCK.sort, dir = STOCK.dir;
  const ORDER = ["safe", "watch", "order soon", "order now", "stockout likely",
                 "unknown"];
  rows = rows.slice().sort(function(a, b){
    let x, y;
    if(key === "status"){ x = ORDER.indexOf(a.status); y = ORDER.indexOf(b.status); }
    else if(key === "product"){
      x = String(a.title || a.sku).toLowerCase();
      y = String(b.title || b.sku).toLowerCase();
    }else{
      // A missing number sorts LAST whichever way the column is pointing: an
      // unknown cover is not the shortest cover, and putting it at the top of
      // "most urgent" would be inventing an emergency.
      x = a[key]; y = b[key];
      if(x === null || x === undefined) return 1;
      if(y === null || y === undefined) return -1;
    }
    if(x < y) return -dir;
    if(x > y) return dir;
    return 0;
  });
  return rows;
}

function _skHead(col, label, cls){
  const on = STOCK.sort === col;
  return '<th class="' + (cls || "") + '" onclick="stockSort(' + jsArg(col) + ')">'
    + _skEsc(label)
    + (on ? '<span class="dir">' + (STOCK.dir > 0 ? "▲" : "▼") + '</span>' : '')
    + '</th>';
}

function _skLedger(){
  const rows = _skVisible();
  let h = '<div id="stk_ledger" class="card" style="padding:0;overflow:hidden">'
        + '<table class="stk-table"><thead><tr>'
        + _skHead("product", "Product")
        + _skHead("listed_qty", "Units", "r")
        + _skHead("velocity", "Sold / day", "r")
        + _skHead("cover_days", "Cover", "r")
        + _skHead("lead_days", "Restock", "r")
        + _skHead("value_at_cost", "Value", "r")
        + _skHead("status", "Status")
        + '</tr></thead><tbody>';
  if(!rows.length){
    h += '<tr><td colspan="7" class="cc" style="padding:20px;text-align:center">'
      + 'Nothing matches that.</td></tr>';
  }
  rows.forEach(function(r){
    const cls = _SK_CLS[r.status] || "unknown";
    // The bar compares cover against the restock time -- the ratio the status
    // is decided on -- so the colour and the length always agree with the chip.
    const ratio = (r.cover_days !== null && r.cover_days !== undefined
                   && r.lead_days) ? (r.cover_days / r.lead_days) : null;
    const pct = ratio === null ? 0 : Math.max(4, Math.min(100, ratio / 3 * 100));
    const barCol = ratio === null ? "var(--line)"
                 : ratio >= 3 ? "#34d399" : ratio >= 2 ? "#fde047"
                 : ratio >= 1.5 ? "#fbbf24" : "#f87171";
    h += '<tr>'
      + '<td><div class="stk-prod">'
      +   (r.img ? thumbImg(r.img, 34, {cls: "stk-thumb", alt: ""})
                 : '<div class="stk-thumb"></div>')
      +   '<div class="stk-pname"><b title="' + _skEsc(r.title) + '">'
      +   _skEsc(r.title || "(no title)") + '</b>'
      +   '<span>' + _skEsc(r.sku) + '</span></div></div></td>'
      + '<td class="r stk-num">' + _skNum(r.listed_qty) + '</td>'
      + '<td class="r stk-num">'
      +   (r.velocity === null || r.velocity === undefined ? '<span class="cc">—</span>'
            : Number(r.velocity).toFixed(2)
              + (r.provisional ? ' <span class="cc" title="Its whole sales '
                 + 'history is inside this window, so the daily rate is thin. '
                 + 'Two sales in three days is not 0.67 a day sustained.">new</span>'
                 : ''))
      + '</td>'
      + '<td class="r stk-num">'
      +   (r.cover_days === null ? '<span class="cc">—</span>'
            : r.cover_days + 'd')
      +   '<div class="stk-bar"><i style="width:' + pct + '%;background:'
      +   barCol + '"></i></div></td>'
      + '<td class="r stk-num" title="'
      +   (r.lead_known
            ? 'The fastest supplier that can actually be bought from: '
              + r.dispatch_days + ' days to dispatch plus a '
              + r.buffer_days + ' day buffer.'
            : 'No supplier is tracked for this SKU, so ' + STOCK.assumedLead
              + ' days is assumed. Add one in the Repricer for a real figure.')
      +   '">' + r.lead_days + 'd'
      +   (r.lead_known ? '' : '<span class="cc">?</span>') + '</td>'
      + '<td class="r stk-num">' + _skMoney(r.value_at_cost) + '</td>'
      + '<td><span class="stk-chip ' + cls + '">' + _skEsc(r.status) + '</span>'
      +   (r.already_out
            ? '<div style="font-size:10px;margin-top:3px;color:#fca5a5">'
              + 'out now</div>'
            : (r.runs_out && (r.status === "order now"
                              || r.status === "stockout likely")
                ? '<div class="cc" style="font-size:10px;margin-top:3px">out '
                  + _skDate(r.runs_out) + '</div>' : ''))
      +   ((r.gaps || []).length
            ? '<div class="stk-gap">' + _skEsc(r.gaps.join(" · ")) + '</div>'
            : '')
      + '</td></tr>';
  });
  return h + '</tbody></table></div>';
}

/* WHAT TO ORDER. Orbit's Actions tab, quoted: "Primary execution system of
 * record for Steven inventory actions."
 *
 * Orbit's version can EXECUTE behind approval gates. This one only ever
 * proposes: it is a list to work from, and nothing on this page places an
 * order, messages a supplier or touches Amazon.
 *
 * It sits above the ledger because it is the answer, and the ledger is the
 * working. Somebody opening this screen wants to know what to buy.
 */
function _skOrderList(){
  const rows = STOCK.toOrder || [];
  if(!rows.length) return "";
  let spend = 0, known = true;
  rows.forEach(function(r){
    if(r.spend === null || r.spend === undefined) known = false;
    else spend += r.spend;
  });
  let h = '<div class="card" style="padding:0;overflow:hidden;margin-bottom:14px">'
    + '<div style="padding:11px 14px;border-bottom:1px solid var(--line);'
    + 'display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
    + '<b style="font-size:12.5px">What to order</b>'
    + '<span class="infodot" title="Enough to cover the restock time plus '
    + STOCK.horizon + ' days of selling, less what is already listed. This is a '
    + 'suggestion — nothing here places an order or contacts a supplier.">i</span>'
    + '<span class="cc" style="font-size:11.5px">' + rows.length + ' product'
    + (rows.length === 1 ? '' : 's') + (known || spend
        ? ' · about ' + _skMoney(spend) + (known ? '' : ' of the priced ones')
        : '') + '</span>'
    + '<span style="flex:1"></span>'
    + '<a class="db-chip" style="text-decoration:none" '
    + 'href="/inventory/order-list.csv' + _skScopeQs() + '" '
    + 'title="The full list as a spreadsheet, to work from or send on.">'
    + '<i class="ti ti-download"></i> Export</a>'
    + '</div>'
    + '<table class="stk-table"><thead><tr>'
    + '<th>Product</th><th class="r">Order</th><th class="r">At cost</th>'
    + '<th class="r">Order by</th><th>Why</th></tr></thead><tbody>';
  rows.forEach(function(r){
    h += '<tr><td><div class="stk-prod">'
      + (r.img ? thumbImg(r.img, 34, {cls: "stk-thumb", alt: ""})
               : '<div class="stk-thumb"></div>')
      + '<div class="stk-pname"><b title="' + _skEsc(r.title) + '">'
      + _skEsc(r.title || r.sku) + '</b><span>' + _skEsc(r.sku) + '</span>'
      + '</div></div></td>'
      + '<td class="r stk-num"><b>' + _skNum(r.units) + '</b>'
      + (r.provisional ? '<div class="cc" style="font-size:10px" title="Its '
        + 'whole sales history is inside the 30-day window, so the rate behind '
        + 'this number is thin.">rate is provisional</div>' : '')
      + '</td>'
      + '<td class="r stk-num">' + _skMoney(r.spend)
      + (r.spend === null || r.spend === undefined
          ? '<div class="stk-gap">no cost set</div>' : '') + '</td>'
      + '<td class="r stk-num">'
      // ALREADY LATE IS NOT A DEADLINE. Showing a date in the past as though it
      // were something to plan for is worse than saying the gap is unavoidable.
      + (r.late
          ? '<span style="color:#fca5a5">already late</span>'
          : (r.order_by ? _skDate(r.order_by) : '<span class="cc">—</span>'))
      + '</td>'
      + '<td class="cc" style="font-size:11px">' + _skEsc(r.why)
      + (r.lead_known ? '' : ' <span title="No supplier is tracked for this '
        + 'SKU, so ' + STOCK.assumedLead + ' days is assumed.">(restock time '
        + 'assumed)</span>') + '</td></tr>';
  });
  return h + '</tbody></table></div>';
}

/* MONEY BACK. Orbit's Reimbursements page, in the version that is true here.
 *
 * Most of Amazon's reimbursement categories are FBA -- units lost or damaged in
 * a warehouse. There are zero FBA units on any of these accounts, so a page
 * listing them would be theatre. What happens on every account is a refund, and
 * a refund has arithmetic Amazon publishes.
 *
 * IT FILES NOTHING, and the page says so. Every row shows the whole sum so it
 * can be checked rather than believed, and typed into a Seller Central case by
 * a person who has decided to.
 */
/* HOW FAST IT REALLY SELLS.
 *
 * The pace here is the mean over the days the product was IN STOCK, not over
 * the calendar. A product that sold thirty units while out of stock for twenty
 * days is not selling one a day -- it is selling three a day and losing two
 * thirds of the month, and every figure downstream inherits that difference.
 *
 * Amazon keeps no stock history for a merchant-fulfilled seller, so the app
 * records it on every catalogue refresh. That means this starts empty and
 * fills a day at a time, and it says so rather than showing a confident pace
 * built on three days.
 */
function _skCoverage(){
  const c = STOCK.coverage;
  if(!c){
    if(!STOCK.coverageAsked){ STOCK.coverageAsked = true; _skCoverageLoad(); }
    return '<div class="cc" style="padding:16px">Working out the real pace…</div>';
  }
  if(c.error){
    return '<div class="odp-note warn" style="padding:14px">'
         + _skEsc(c.error) + '</div>';
  }
  const n = c.counts || {};
  const hist = c.history || {};
  let h = "";
  if(typeof uiSource === "function"){
    h += uiSource([
      {k: "Stock from", v: "the live catalogue, recorded on each refresh"},
      {k: "Sales from", v: "your own orders, by SKU"},
      {k: "Window", v: (c.start && c.end) ? (c.start + " → " + c.end) : ""},
      {k: "History", v: hist.days ? (hist.days + " day(s), from " + hist.first)
                                  : "none yet"},
    ], "The pace counts only the days a product was IN STOCK. Amazon keeps no "
     + "stock history for a merchant-fulfilled seller, so this one is ours and "
     + "starts the day recording started.");
  }
  if(typeof uiStats === "function"){
    h += uiStats([
      {label: "Out of stock", value: n.out_of_stock || 0,
       tone: (n.out_of_stock ? "bad" : ""),
       note: (n.out_of_stock ? "nothing sellable right now" : "none")},
      {label: "Will run short", value: n.needs_attention || 0,
       tone: (n.needs_attention ? "warn" : ""),
       note: "at the pace they actually sell"},
      {label: "Covered", value: n.ok || 0, note: "for the next 30 days"},
      {label: "Days of history", value: hist.days || 0,
       tone: ((hist.days || 0) < 7 ? "warn" : ""),
       note: (hist.days ? "recorded since " + _skEsc(hist.first || "")
                        : "recording starts on the next refresh")},
    ]);
  }
  // A ZERO WITH NO DENOMINATOR IS NOT AN ANSWER, and neither is a pace with no
  // history behind it. Both notes are shown, always.
  h += '<div class="cc" style="font-size:11.5px;line-height:1.55;max-width:790px;'
    + 'margin:0 0 12px">' + _skEsc(c.note || "") + " " + _skEsc(c.gap_is_not_a_po || "")
    + "</div>";

  const rows = c.rows || [];
  if(!rows.length){
    return h + '<div class="odp-note" style="padding:14px">Nothing recorded yet. '
      + 'Stock levels are captured each time the live catalogue refreshes.</div>';
  }

  let t = '<div style="overflow-x:auto"><table class="stk-table"><thead><tr>'
    + '<th>Product</th><th>Have</th><th>In stock</th>'
    + '<th>Pace / day</th><th>Trend</th><th>30-day demand</th>'
    + '<th>Cover</th><th>Short by</th><th>Status</th></tr></thead><tbody>';
  const LABEL = {out_of_stock: "Out of stock", needs_attention: "Will run short",
                 unknown: "Not enough history", ok: "Covered"};
  const TONE = {out_of_stock: "off", needs_attention: "warn",
                unknown: "unk", ok: "ok"};
  rows.forEach(function(r){
    t += '<tr title="' + _skEsc(r.why || "") + '">'
      + '<td><b>' + _skEsc(r.sku) + '</b></td>'
      + '<td>' + (r.on_hand === null ? '<span class="cc">—</span>' : r.on_hand) + '</td>'
      + '<td>' + (r.in_stock_rate === null ? '<span class="cc">—</span>'
                                           : r.in_stock_rate + '%')
      + (r.oos_days ? '<div class="cc" style="font-size:10.5px">' + r.oos_days
                      + ' day(s) out</div>' : '')
      + '</td>'
      // The pace carries the number of days it was computed over, because a
      // rate from eight days and one from ninety are not the same claim.
      + '<td>' + (r.pace_30d === null ? '<span class="cc">not yet</span>'
                                      : '<b>' + r.pace_30d + '</b>')
      + (r.pace_30d !== null ? '<div class="cc" style="font-size:10.5px">over '
                               + r.pace_30d_days + ' in-stock day(s)</div>' : '')
      + '</td>'
      + '<td>' + (r.velocity_trend_pct === null ? '<span class="cc">—</span>'
          : '<span style="color:' + (r.velocity_trend_pct >= 0 ? 'var(--ok)' : 'var(--red)')
            + '">' + (r.velocity_trend_pct > 0 ? '+' : '') + r.velocity_trend_pct
            + '%</span>') + '</td>'
      + '<td>' + (r.forecast_demand_30d === null ? '<span class="cc">—</span>'
                                                 : r.forecast_demand_30d) + '</td>'
      + '<td>' + (r.days_of_cover === null ? '<span class="cc">—</span>'
                                           : r.days_of_cover + 'd') + '</td>'
      + '<td>' + (r.stock_gap_30d === null || r.stock_gap_30d <= 0
                  ? '<span class="cc">—</span>'
                  : '<b style="color:var(--warn)">' + r.stock_gap_30d + '</b>') + '</td>'
      + '<td><span class="ld-pill ' + (TONE[r.status] || "unk") + '">'
      + _skEsc(LABEL[r.status] || r.status) + '</span></td></tr>';
  });
  t += '</tbody></table></div>';

  return h + ((typeof uiPanel === "function")
    ? uiPanel("Every product, worst first",
        "The pace is measured over the days each product was in stock. A "
        + "product out of stock for most of the month has a HIGHER real pace "
        + "than the calendar suggests, not a lower one.", t)
    : t);
}

async function _skCoverageLoad(){
  try{
    const j = await (await fetch("/inventory/coverage" + _skScopeQs())).json();
    STOCK.coverage = (j && j.ok) ? j
      : {error: (j && j.error) || "Could not work out coverage."};
  }catch(e){
    STOCK.coverage = {error: "Could not work out coverage: " + e};
  }
  if((STOCK.tab || "overview") === "coverage") stockRender();
}

function _skMoneyBack(){
  // ONE RENDERER, TWO PLACES. This check has its own page now
  // (static/js/reimbursements.js) and the tab draws the SAME block, because two
  // copies of one arithmetic disagree the day either is corrected
  // (CLAUDE.md Rule 12). The tab keeps its place: money owed is a fact about
  // stock as much as about money, and it was found here first.
  if(typeof rbHtml === "function" && typeof rbLoad === "function"){
    if(!RB.data && !RB.loading && !RB.asked){ RB.asked = true; rbLoad(); }
    return '<div style="padding:2px 0">'
         + '<div class="cc" style="font-size:11.5px;margin:0 0 8px">'
         + 'This also has its own page — <a href="#" onclick="return navGo(event,'
         + "'reimbursements')" + '">Reimbursements</a>.</div>'
         + rbHtml() + '</div>';
  }

  const m = STOCK.moneyBack;
  if(!m){
    // Fetched the first time this page is opened rather than with the screen:
    // it is a database read nobody pays for until they ask for it.
    if(!STOCK.moneyBackAsked){ STOCK.moneyBackAsked = true; _skMoneyLoad(); }
    return '<div class="card" style="padding:16px" class="cc">Checking the '
         + 'settled orders…</div>';
  }
  if(m.error){
    return '<div class="odp-note warn" style="padding:14px">'
         + _skEsc(m.error) + '</div>';
  }

  const head = '<div style="padding:11px 14px;border-bottom:1px solid var(--line)">'
    + '<b style="font-size:12.5px">Money Amazon owes back</b>'
    + '<span class="infodot" title="' + _skEsc(m.rule || "") + ' This page finds '
    + 'and shows the arithmetic. It never files a claim — that is a decision you '
    + 'make in Seller Central with the figures in front of you.">i</span></div>';

  // A ZERO WITH NO DENOMINATOR IS NOT AN ANSWER. "Nothing owed" means one thing
  // when 200 refunds were examined and something else entirely when none were.
  const scope = '<div class="odp-note" style="padding:9px 14px;border-top:0">'
    + 'Checked ' + _skNum(m.refunds_checked || 0) + ' refunded order'
    + ((m.refunds_checked === 1) ? '' : 's') + ' out of '
    + _skNum(m.orders_checked || 0) + ' Amazon has settled. '
    + _skEsc(m.rule || '') + '</div>';

  if(!m.count){
    return '<div class="card" style="padding:0;overflow:hidden;margin-bottom:14px">'
      + head
      + '<div style="padding:16px 14px">'
      + (m.refunds_checked
          ? '<b style="color:var(--ok)">Nothing owed.</b> Amazon kept less than '
            + 'its own cap on every refund it has settled here.'
          : '<b>No refunds have settled yet</b>, so there is nothing to check. '
            + 'This page fills in as Amazon settles orders.')
      + '</div>' + scope + '</div>';
  }

  const owed = Object.keys(m.owed_by_currency || {}).map(function(cc){
    return _skMoney(m.owed_by_currency[cc], cc);
  }).join(" + ");

  let h = '<div class="card" style="padding:0;overflow:hidden;margin-bottom:14px">'
    + head
    + '<div style="padding:12px 14px;border-bottom:1px solid var(--line)">'
    + '<span class="stk-eyebrow">Candidates</span>'
    + '<div class="stk-headline is-warn">' + _skEsc(owed) + ' across '
    + _skNum(m.count) + ' order' + (m.count === 1 ? '' : 's') + '</div>'
    + '<div class="stk-sub">Called candidates on purpose: Amazon has exceptions '
    + 'this cannot see — a promotional fee, a category minimum, a refund settled '
    + 'across two events. Check the sum before you raise a case.</div></div>'
    + '<table class="stk-table"><thead><tr>'
    + '<th>Order</th><th>Settled</th><th class="r">Sale</th>'
    + '<th class="r">Refunded</th><th class="r">Fee taken</th>'
    + '<th class="r">Given back</th><th class="r">May keep</th>'
    + '<th class="r">Owed</th></tr></thead><tbody>';

  (m.candidates || []).forEach(function(c){
    h += '<tr title="' + _skEsc(c.why) + '">'
      + '<td class="stk-num">' + _skEsc(c.order_id) + '</td>'
      + '<td class="cc">' + _skEsc(c.posted_date || '') + '</td>'
      + '<td class="r stk-num">' + _skMoney(c.principal, c.currency) + '</td>'
      + '<td class="r stk-num">' + _skMoney(c.refunded, c.currency)
      + (c.share_pct < 99.5
          ? '<div class="stk-gap">' + c.share_pct + '% of it</div>' : '')
      + '</td>'
      + '<td class="r stk-num">' + _skMoney(c.fee_on_refunded_part, c.currency) + '</td>'
      + '<td class="r stk-num">' + _skMoney(c.returned, c.currency) + '</td>'
      + '<td class="r stk-num">' + _skMoney(c.allowed_to_keep, c.currency) + '</td>'
      + '<td class="r stk-num"><b style="color:#fbbf24">'
      + _skMoney(c.owed, c.currency) + '</b></td></tr>';
  });
  return h + '</tbody></table>' + scope + '</div>';
}

async function _skMoneyLoad(){
  try{
    const j = await (await fetch("/inventory/money-back" + _skScopeQs())).json();
    STOCK.moneyBack = (j && j.ok) ? j
      : {error: (j && j.error) || "Could not read the settled orders."};
  }catch(e){
    STOCK.moneyBack = {error: "Could not read the settled orders: " + e};
  }
  if((STOCK.tab || "overview") === "money") stockRender();
}

/* PROJECTED BURN. Orbit's Forecasting tab, quoted: "Projects future inventory
 * burn by combining current stock, forecast demand, and dated inbound
 * arrivals."
 *
 * There is no inbound here, so it combines the two things that do exist. It is
 * a straight line at the current rate and says so -- pretending to a seasonal
 * model on thirty days of history would be inventing precision.
 */
function _skForecast(){
  const f = STOCK.forecast || [];
  if(!f.length || !f.some(function(x){ return x.units_selling; })) return "";
  let h = '<div class="card" style="padding:0;overflow:hidden;margin-bottom:14px">'
    + '<div style="padding:11px 14px;border-bottom:1px solid var(--line)">'
    + '<b style="font-size:12.5px">If nothing changes</b>'
    + '<span class="infodot" title="A straight line at the rate each product '
    + 'has been selling for the last 30 days. Not a seasonal forecast — there '
    + 'is not enough history for one, and pretending otherwise would be '
    + 'inventing precision.">i</span></div>'
    + '<table class="stk-table"><thead><tr>'
    + '<th>Over</th><th class="r">Units sold</th><th class="r">Short by</th>'
    + '<th class="r">Products short</th><th class="r">Cost to cover</th>'
    + '</tr></thead><tbody>';
  f.forEach(function(r){
    h += '<tr><td><b>' + r.days + ' days</b></td>'
      + '<td class="r stk-num">' + _skNum(r.units_selling) + '</td>'
      + '<td class="r stk-num"' + (r.units_short ? ' style="color:#fbbf24"' : '')
      + '>' + _skNum(r.units_short) + '</td>'
      + '<td class="r stk-num">' + _skNum(r.skus_short) + '</td>'
      + '<td class="r stk-num">' + _skMoney(r.cost_to_cover)
      + (r.cost_complete ? '' : '<div class="stk-gap">priced ones only</div>')
      + '</td></tr>';
  });
  return h + '</tbody></table></div>';
}

// This was the CAREFUL copy -- it read CUR_ACCOUNT and dropped "__all__" where
// daily.js and weekly.js did neither. Now it is the shared one, so those two get
// the same care instead of the app having two answers to one question
// (CLAUDE.md Rule 12). See static/js/scopeq.js.
function _skScopeQs(){ return (typeof scopeQs === "function") ? scopeQs() : ""; }

function _skFooter(c){
  return '<div class="odp-note" style="margin-top:10px">'
    + 'As at ' + _skDate(c.as_at) + '. Sales are the last ' + c.window_days
    + ' days. Cover is the listed quantity divided by that rate; a product is '
    + 'flagged when its cover is shorter than the time its supplier takes to '
    + 'send more. Nothing here changes anything on Amazon.'
    + '</div>';
}
