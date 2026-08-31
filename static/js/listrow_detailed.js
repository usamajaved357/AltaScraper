/* static/js/listrow_detailed.js -- the Amazon "Manage All Inventory" row.
 *
 * A third view beside the existing table and card views, not a replacement for
 * either. Layout is docslistings-row-mockup.html's: checkbox, star, status
 * badge + date, product details, then three data blocks -- Performance,
 * Inventory, Pricing -- and a row menu.
 *
 * WHAT IT DRAWS FROM. Everything on the row comes off the row object the grid
 * already has, through the SAME helpers the other two views use:
 *
 *     rowAsin(r)      OUR asin vs the competitor's -- never confused, see below
 *     _rowImages(r)   the picture
 *     _dwCost(r)      cost: the typed COGS, else the SKU's own price prefix
 *     lsStatusOf(r)   the status word, in the four-status vocabulary
 *     lsWarnings(r)   the warning count and its severity
 *     rowSelectBox(r) the batch-actions checkbox, with its existing wiring
 *     rowActions(r)   the row menu
 *
 * so this view cannot disagree with the table about what a listing IS. It is a
 * different arrangement of the same facts (CLAUDE.md Rule 12).
 *
 * THE TWO ASINs. A SKU is price_days_ASIN and that ASIN is the COMPETITOR's --
 * the product this listing was researched from, never ours (CLAUDE.md Rule 1).
 * Our own ASIN only exists once Amazon has accepted the listing, and it arrives
 * from the live catalogue. rowAsin() is the one place that tells them apart and
 * this file never parses a SKU to get an ASIN.
 *
 * PERFORMANCE AND INVENTORY ARE EMPTY IN PHASE 1, deliberately: they read
 * LISTING_METRICS, which nothing fills yet. Amazon shows "--" for a figure it
 * does not have and so does this -- a dash is honest, a zero is a claim.
 */

/* sku -> {sales, units, views, rank, rank_category, on_hand, available,
 *         inbound, reserved, buybox, lowest_price, fetched_at}
 * Filled in Phase 2. Every field is optional; anything absent draws as "--". */
let LISTING_METRICS = {};

function lrMetrics(sku){ return LISTING_METRICS[String(sku)] || null; }

/* A number, or the dash Amazon uses when it has none. NEVER a zero standing in
 * for "unknown" -- "0 units sold" and "we have not looked" are different facts
 * and the whole point of this block is to tell you which one you are reading. */
function lrVal(v, opts){
  opts = opts || {};
  if(v === null || v === undefined || v === "") return '<span class="lr-dash">--</span>';
  let s = String(v);
  if(opts.money) s = (typeof CUR_SYMBOL !== "undefined" ? CUR_SYMBOL : "") + s;
  if(opts.comma) s = String(v).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return esc(s);
}

function lrDataRow(label, valHtml, cls){
  return '<div class="lr-data"><span class="lr-data-label">' + esc(label) + '</span>'
       + '<span class="lr-data-val' + (cls ? " " + cls : "") + '">' + valHtml + '</span></div>';
}

/* The status badge and the date under it.
 *
 * The WORD comes from liststatus.js so this view can never disagree with the
 * card and the table about a listing's status. The mockup's Amazon words
 * ("Active", "Out of stock", "Missing offer") are Amazon's inventory
 * vocabulary, not this app's four statuses -- showing "Active" for a row this
 * app calls LIVE would invent a second vocabulary for the same thing. So the
 * app's own word is shown, coloured the way the mockup colours its equivalent.
 */
function lrStatus(r){
  const st = (typeof lsStatusOf === "function") ? lsStatusOf(r)
                                                : String(r.status||"").toUpperCase();
  const cls = st === "LIVE" ? "live" : st === "SUBMITTED" ? "sent"
            : st === "GENERATED" ? "gen" : st === "QUEUED" ? "queued"
            : st === "PARENT" ? "parent" : "other";
  // The date the listing was last worked on. date_processed is what the
  // generator stamps; updated_at is the row's own. Neither is invented here.
  const d = r.date_processed || r.updated_at || r.created_at || "";
  return '<span class="lr-status">'
       + '<span class="lr-status-badge ' + cls + '">' + esc(st || "—") + '</span>'
       + (d ? '<span class="lr-status-date">' + esc(lrDate(d)) + '</span>' : "")
       + '</span>';
}

/* A date as "12 Aug 2026". Returns "" for anything unparseable rather than
 * "Invalid Date", which is what a bare toLocaleDateString would print. */
function lrDate(v){
  const s = String(v || "").trim();
  if(!s) return "";
  const d = new Date(s.length <= 10 ? (s + "T00:00:00") : s);
  if(isNaN(d.getTime())) return s.slice(0, 10);
  return d.getDate() + " " + ["Jan","Feb","Mar","Apr","May","Jun",
                              "Jul","Aug","Sep","Oct","Nov","Dec"][d.getMonth()]
       + " " + d.getFullYear();
}

/* Product details: image, title, and the identifiers under it. */
function lrProduct(r){
  const urls = (typeof _rowImages === "function") ? _rowImages(r) : [];
  const a = (typeof rowAsin === "function") ? (rowAsin(r) || {}) : {};
  const w = (typeof lsWarnings === "function") ? lsWarnings(r) : {n:0};
  // OUR asin links to the live product page. The competitor's does NOT get a
  // link that looks like ours -- it is labelled for what it is, because a
  // listing that is not live yet having a clickable "ASIN" is how someone comes
  // to believe a draft is on Amazon.
  const asinBit = a.own
    ? 'ASIN <a class="lr-asin" href="' + esc(typeof _dpUrl === "function" ? _dpUrl(a.own) : "#")
      + '" target="_blank" rel="noopener" onclick="event.stopPropagation()"'
      + ' title="Open your listing on Amazon">' + esc(a.own) + '</a>'
    : (a.source
        ? '<span class="lr-dim" title="This listing is not live on Amazon yet, so it has no ASIN of its own. '
          + esc(a.source) + ' is the competitor product it was researched from — not your listing.">'
          + 'not live yet · from ' + esc(a.source) + '</span>'
        : '<span class="lr-dim">no ASIN</span>');

  return '<span class="lr-product">'
    + '<span class="lr-img">'
    +   (urls && urls.length
        ? '<img src="' + esc(urls[0]) + '" loading="lazy" onerror="this.remove()">'
        : '<i class="ti ti-photo"></i>')
    + '</span>'
    + '<span class="lr-details">'
    +   '<div class="lr-title" title="' + esc(r.title || "") + '">'
    +     (esc(r.title || "") || '<span class="lr-dim">(no title)</span>') + '</div>'
    +   '<div class="lr-meta">' + asinBit
    +     '<br>SKU <strong>' + esc(r.sku || "") + '</strong>'
    +     (r.barcode ? '<br>EAN <strong>' + esc(r.barcode) + '</strong>' : "")
    +     '<br>Condition <strong>New</strong>'
    +     (w.n ? '<br><span class="lr-warn" onclick="event.stopPropagation();openListing(\''
             + esc(r.sku) + '\')"><i class="ti ti-alert-triangle"></i> '
             + w.n + ' warning' + (w.n === 1 ? '' : 's') + '</span>' : "")
    +   '</div>'
    + '</span></span>';
}

/* Performance, last 30 days. Empty until Phase 2 fills LISTING_METRICS.
 *
 * A listing that has never been to Amazon has no performance to report and
 * says so, rather than showing four dashes that look like a failed lookup. */
function lrPerf(r){
  const sent = (typeof lsWasSentToAmazon === "function") ? lsWasSentToAmazon(r) : false;
  if(!sent) return '<span class="lr-perf"><div class="lr-none">Not yet live</div></span>';
  const m = lrMetrics(r.sku) || {};
  return '<span class="lr-perf">'
    + lrDataRow("Sales", lrVal(m.sales, {money:true}))
    + lrDataRow("Units", lrVal(m.units))
    + lrDataRow("Views", lrVal(m.views, {comma:true}))
    + lrDataRow("Rank",  lrVal(m.rank,  {comma:true}))
    + '</span>';
}

function lrInv(r){
  const sent = (typeof lsWasSentToAmazon === "function") ? lsWasSentToAmazon(r) : false;
  if(!sent) return '<span class="lr-inv"><div class="lr-none">--</div></span>';
  const m = lrMetrics(r.sku) || {};
  const oos = (v) => (v === 0 || v === "0") ? "red" : "";
  return '<span class="lr-inv">'
    + lrDataRow("On-hand",   lrVal(m.on_hand),   oos(m.on_hand))
    + lrDataRow("Available", lrVal(m.available), oos(m.available))
    + lrDataRow("Inbound",   lrVal(m.inbound))
    + lrDataRow("Reserved",  lrVal(m.reserved))
    + '</span>';
}

/* Pricing. Price, cost and profit come off the row and are known NOW; the buy
 * box and the lowest price come from Amazon and wait for Phase 2. */
function lrPricing(r){
  const m = lrMetrics(r.sku) || {};
  const cur = (typeof CUR_SYMBOL !== "undefined") ? CUR_SYMBOL : "";
  const price = String(r.price == null ? "" : r.price).replace(/[^0-9.\-]/g, "");
  const cost  = (typeof _dwCost === "function") ? _dwCost(r) : "";
  const pnum  = String(r.profit == null ? "" : r.profit).replace(/[^0-9.\-]/g, "");
  const pneg  = pnum !== "" && parseFloat(pnum) < 0;

  let box = "";
  if(m.buybox === true)  box = '<div class="lr-buybox win"><i class="ti ti-circle-check"></i> Featured offer</div>';
  else if(m.buybox === false) box = '<div class="lr-buybox lose"><i class="ti ti-circle-x"></i> Not winning</div>';

  return '<span class="lr-pricing">'
    + lrDataRow("Price",  price ? esc(cur + price) : lrVal(null))
    + lrDataRow("Cost",   cost ? esc(cost) : lrVal(null))
    + lrDataRow("Profit", pnum ? esc(cur + pnum) : lrVal(null), pneg ? "red" : "green")
    + box
    + (m.lowest_price != null
        ? lrDataRow("Lowest", esc(cur + m.lowest_price)) : "")
    + '</span>';
}

/* ONE LISTING, AS A DETAILED ROW.
 *
 * Clicking it opens the listing exactly as the card and the table row do --
 * through openListing(), the one function that decides which view that is. */
function detailedRow(r){
  const sel = (typeof SELECTED !== "undefined") && SELECTED.has(String(r.sku));
  return '<div class="lr' + (sel ? " sel" : "") + '" data-sku="' + esc(r.sku) + '"'
    + ' onclick="openListing(\'' + esc(r.sku) + '\')">'
    + '<span class="lr-cb" onclick="event.stopPropagation()">'
    +   ((typeof rowSelectBox === "function") ? rowSelectBox(r) : "") + '</span>'
    + lrStatus(r)
    + lrProduct(r)
    + lrPerf(r)
    + lrInv(r)
    + lrPricing(r)
    + '<span class="lr-actions" onclick="event.stopPropagation()">'
    +   ((typeof rowActions === "function") ? rowActions(r, "dotb") : "") + '</span>'
    + '</div>';
}

/* The column header. One per block of rows, matching the row's own widths. */
function detailedHead(rows){
  const all = rows || [];
  const allSel = all.length && (typeof SELECTED !== "undefined")
                 && all.every(x => SELECTED.has(String(x.sku)));
  return '<div class="lr-head">'
    + '<span class="lr-cb"><input type="checkbox" class="rowsel"' + (allSel ? " checked" : "")
    +   ' title="Select every row shown" onchange="selectAllVisible(this.checked)"></span>'
    + '<span class="lr-status">Listing status</span>'
    + '<span class="lr-product">Product details</span>'
    + '<span class="lr-perf">Performance<br><span class="lr-sub">last 30 days</span></span>'
    + '<span class="lr-inv">Inventory</span>'
    + '<span class="lr-pricing">Pricing</span>'
    + '<span class="lr-actions"></span>'
    + '</div>';
}

/* A block of listings in this view: one header, then the rows. */
function detailedBlock(rows){
  if(!rows || !rows.length) return "";
  return '<div class="card lrwrap">' + detailedHead(rows)
       + rows.map(detailedRow).join("") + '</div>';
}
