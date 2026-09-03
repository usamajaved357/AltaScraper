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

/* sku -> whatever /listing/live_metrics knew about it. Every field is optional;
 * anything absent draws as "--". */
let LISTING_METRICS = {};
let LR_COVERAGE = {};        // how many days the window could actually speak for
let LR_LAST_FETCH = 0;       // epoch seconds of the newest cached SP-API answer
let LR_ERRORS = {};          // {group: why} when Amazon refused
let LR_LOADING = false;
let LR_ASKED = "";           // the SKU set already requested, so we ask once

function lrMetrics(sku){ return LISTING_METRICS[String(sku)] || null; }

/* ASK FOR THE NUMBERS, ONCE PER SET OF ROWS.
 *
 * Called from the renderer, so the view fetches only when it is actually being
 * looked at -- switching to the table or the cards costs nothing.
 *
 * WITHOUT fetch=1 by default. That form reads this app's own database and never
 * calls Amazon, so it is fast and free and works with SP-API down. `force`
 * adds fetch=1 and is what the Refresh button sends; a page render must never
 * spend a catalogue call per listing.
 */
async function lrLoadMetrics(rows, force){
  const skus = (rows || []).map(r => String(r.sku)).filter(Boolean);
  if(!skus.length) return;
  const key = skus.slice().sort().join(",");
  if(!force && (LR_LOADING || key === LR_ASKED)) return;
  LR_ASKED = key; LR_LOADING = true;
  try{
    // A cap matching the route's own, so the URL cannot grow past what a
    // server will accept on a large catalogue.
    const ask = skus.slice(0, 400);
    let url = "/listing/live_metrics?skus=" + encodeURIComponent(ask.join(","));
    if(force) url += "&fetch=1";
    const j = await (await fetch(typeof acctUrl === "function" ? acctUrl(url) : url)).json();
    if(j && j.ok){
      LISTING_METRICS = j.metrics || {};
      LR_COVERAGE = j.coverage || {};
      LR_LAST_FETCH = j.last_updated || 0;
      LR_ERRORS = j.errors || {};
    } else {
      LR_ERRORS = {all: (j && j.error) || "could not read the metrics"};
    }
  }catch(e){
    LR_ERRORS = {all: String((e && e.message) || e)};
  }finally{
    LR_LOADING = false;
    if(typeof render === "function") render();
  }
}

/* The Refresh button: throw the cached Amazon answers away and ask again. */
async function lrRefreshMetrics(){
  if(typeof toast === "function") toast("Refreshing metrics from Amazon…");
  try{
    await fetch("/listing/metrics_forget", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify((typeof acctBody === "function") ? acctBody({}) : {})});
  }catch(e){}
  const rows = (typeof ROWS !== "undefined") ? ROWS : [];
  await lrLoadMetrics(rows, true);
  const bad = Object.keys(LR_ERRORS || {});
  if(typeof toast === "function"){
    toast(bad.length ? ("Amazon refused: " + LR_ERRORS[bad[0]]) : "Metrics updated");
  }
}

/* "2 hours ago", or "" when nothing has ever been fetched. */
function lrAgo(epochSeconds){
  const t = Number(epochSeconds || 0);
  if(!t) return "";
  const s = Math.max(0, Math.floor(Date.now()/1000 - t));
  if(s < 90) return "just now";
  const m = Math.floor(s/60);
  if(m < 60) return m + " minute" + (m === 1 ? "" : "s") + " ago";
  const h = Math.floor(m/60);
  if(h < 48) return h + " hour" + (h === 1 ? "" : "s") + " ago";
  return Math.floor(h/24) + " days ago";
}

/* The line above the rows: where these numbers came from and how fresh.
 *
 * It says what the window ACTUALLY covered, not what was asked for -- a "last
 * 30 days" total built from four days of data is not one, and there is no way
 * to tell by looking at it. */
function lrMetricsBar(){
  const cov = LR_COVERAGE || {};
  const bits = [];
  if(LR_LOADING) bits.push('<span class="lr-loading">reading…</span>');
  if(cov.sales_days != null && cov.days){
    bits.push(cov.sales_days >= cov.days
      ? ('sales &amp; traffic: ' + cov.days + ' days')
      : ('<span class="lr-part" title="Amazon has only reported ' + cov.sales_days
         + ' of the last ' + cov.days + ' days. The totals cover what exists, not the full window.">'
         + 'sales &amp; traffic: ' + cov.sales_days + ' of ' + cov.days + ' days</span>'));
  }
  if(cov.stock_last) bits.push('stock as of ' + esc(cov.stock_last));
  const ago = lrAgo(LR_LAST_FETCH);
  if(ago) bits.push('Amazon figures: ' + esc(ago));

  const errs = Object.keys(LR_ERRORS || {});
  const errHtml = errs.length
    ? '<div class="lr-err"><i class="ti ti-alert-triangle"></i> Amazon did not answer for '
      + errs.map(esc).join(", ") + ' — <span class="prod-dim">'
      + esc(String(LR_ERRORS[errs[0]]).slice(0, 160)) + '</span>. The figures below are '
      + 'this app’s own records; the missing ones show as dashes.</div>'
    : "";

  return '<div class="lr-metricsbar">'
    + '<span class="lr-bits">' + bits.join(' <span class="lr-dot">·</span> ') + '</span>'
    + '<button class="lr-refresh" onclick="lrRefreshMetrics()" title="Ask Amazon again for sales rank, competitive price and FBA stock. The rest is read from this app’s own database and is always current.">'
    + '<i class="ti ti-refresh"></i> Refresh metrics</button>'
    + '</div>' + errHtml;
}

/* A number, or the dash Amazon uses when it has none. NEVER a zero standing in
 * for "unknown" -- "0 units sold" and "we have not looked" are different facts
 * and the whole point of this block is to tell you which one you are reading. */
function lrVal(v, opts){
  opts = opts || {};
  // The mockup's em dash, in its own grey, so an absent figure reads as absent
  // rather than as a very short number.
  if(v === null || v === undefined || v === "") return '<span class="dash">—</span>';
  let s = String(v);
  if(opts.money) s = (typeof CUR_SYMBOL !== "undefined" ? CUR_SYMBOL : "") + s;
  if(opts.comma) s = String(v).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return esc(s);
}

function lrDataRow(label, valHtml, cls){
  return '<div class="d-row"><span class="d-label">' + esc(label) + '</span>'
       + '<span class="d-val' + (cls ? " " + cls : "") + '">' + valHtml + '</span></div>';
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
  // The date the listing was last worked on. date_processed is what the
  // generator stamps; updated_at is the row's own. Neither is invented here.
  const d = r.date_processed || r.updated_at || r.created_at || "";
  const made = (r.created_at && r.created_at !== d) ? r.created_at : "";
  const badge = (st === "LIVE")
    ? '<span class="status-live">' + esc(st) + '</span>'
    : '<span class="status-badge'
      + (st === "SUBMITTED" ? " sent" : st === "QUEUED" ? " queued"
         : st === "PARENT" ? " parent" : "")
      + '">' + esc(st || "—") + '</span>';
  return badge
       + '<div class="status-date">' + (d ? esc(lrDate(d)) : "")
       +   (made ? "<br>" + esc(lrDate(made)) : "") + '</div>'
       + lrAmazonSaid(r);
}

/* WHAT AMAZON SAID ABOUT THE LAST SUBMIT, on the row.
 *
 *     "what amazon has to say about the listing submitted, was it a api error
 *      or some other error"
 *
 * THE VERDICT COMES FROM THE STATUS, NEVER FROM READING THE PROSE (Rule 4).
 * The generator writes one of three states, each with a sentence beside it:
 *
 *     API_ERROR   Amazon rejected it, synchronously, with reasons
 *     SUBMITTED   Amazon accepted it; it publishes in ~5-30 minutes
 *     API_READY   a Preview passed -- validated, never sent
 *
 * The note is shown as the WORDS, on hover, because that is where Amazon's own
 * messages ended up ("API SUBMIT REJECTED by Amazon (3 error(s)): ..."). The
 * symbol and the colour come from the status; only the explanation comes from
 * the text, and a note that cannot be parsed still shows -- it is Amazon's
 * sentence either way.
 */
function lrAmazonSaid(r){
  const raw = String((r && r.status) || "").toUpperCase().replace(/[\s-]+/g, "_");
  const note = String((r && r.notes) || "").trim();
  let tone = "", icon = "", words = "";
  if(raw === "API_ERROR"){
    tone = "bad"; icon = "ti-alert-octagon";
    // The COUNT is out of our own note, which we wrote; the MESSAGE is
    // Amazon's and is quoted rather than interpreted.
    const m = note.match(/\((\d+)\s+error/i);
    words = m ? ("Amazon rejected — " + m[1] + " error" + (m[1] === "1" ? "" : "s"))
              : "Amazon rejected it";
  } else if(raw === "SUBMITTED"){
    tone = "wait"; icon = "ti-clock";
    words = /Amazon warnings/i.test(note) ? "Accepted, with warnings"
                                          : "Accepted — publishing";
  } else if(raw === "API_READY"){
    tone = "ok"; icon = "ti-circle-check";
    words = "Preview passed — not sent yet";
  } else {
    return "";
  }
  return '<div class="lr-amz ' + tone + '" title="' + esc(note || words) + '">'
       + '<i class="ti ' + icon + '"></i><span>' + esc(words) + '</span></div>';
}

/* THE THREE RISK SYMBOLS.
 *
 *     "i want a symbol telling me that if some listing has compliance
 *      requirements or a restricted item is it. or there are claims risk in
 *      the item content."
 *
 * Restricted, Compliance and Claims, in that order, always all three -- a
 * symbol that appears only when there is trouble cannot be told apart from one
 * that failed to draw. Grey is "nothing here", amber a medium warning, red a
 * high one.
 *
 * Through liststatus.js's lsWarnTypes/lsCheckTone, which is what the product
 * page's Checks rail uses, so a row and the page it opens cannot disagree about
 * whether a listing is restricted (Rule 12). The row's own verdicts count too:
 * listing/restricted.py writes r.restricted and never a warning row, so reading
 * only the warnings would go quiet about it.
 */
function lrRisks(r){
  const wt = (typeof lsWarnTypes === "function") ? lsWarnTypes(r) : {};
  const tone = (typeof lsCheckTone === "function") ? lsCheckTone
             : function(){ return "ok"; };
  const bits = [
    {keys: ["restricted", "restricted_product", "prohibited"],
     hit: !!(r.restricted && r.restricted.matched && r.restricted.matched.length),
     icon: "ti-ban", name: "Restricted product",
     none: "Not a restricted product"},
    {keys: ["compliance_risk", "hazmat", "documents_required"],
     hit: !!(r.viability && r.viability.matched && r.viability.matched.length),
     icon: "ti-file-description", name: "Compliance requirements",
     none: "No compliance requirements found"},
    {keys: ["ip_risk", "claim_risk", "unsupported_claim"],
     hit: ((r.claim_flags || []).length > 0),
     icon: "ti-quote", name: "Claim risk in the content",
     none: "No claim risks in the content"}
  ];
  return '<div class="lr-risks">' + bits.map(function(b){
    let t = tone(wt, b.keys);
    if(t === "ok" && b.hit) t = "warn";
    const cls = (t === "bad") ? "bad" : (t === "warn" ? "warn" : "none");
    const n = (typeof lsCheckCount === "function") ? lsCheckCount(wt, b.keys) : 0;
    const title = (cls === "none") ? b.none
                : (b.name + (n ? " — " + n + " warning" + (n === 1 ? "" : "s") : ""));
    return '<span class="lr-risk ' + cls + '" title="' + esc(title) + '">'
         + '<i class="ti ' + b.icon + '"></i></span>';
  }).join("") + '</div>';
}

/* IS THIS BARCODE ALREADY ON ANOTHER LISTING?
 *
 *     "if 1 ean was used in a listing already in my sellercentral active status
 *      ... show me outside that this listing holds a ean which is already
 *      present in this item or asin."
 *
 * CLAUDE.md Rule 1 is explicit: a barcode already on another listing must be
 * REPORTED, not sent and hoped for -- Amazon matches the code to the ASIN that
 * owns it and refuses to create a second product. Measured on the owner's own
 * data, sixteen barcodes were on more than one listing.
 *
 * NOTHING IS WORKED OUT HERE. listing/warnings.py already answers it, twice
 * over, and both answers name what the clash is with:
 *
 *     barcode_live_on_amazon   the EAN is on a LIVE Amazon listing -> live_asin
 *     duplicate_barcode        another draft in this app has it -> existing_sku
 *
 * so this prints what those carry. A second implementation here would be a
 * fourth place deciding what a duplicate is (Rule 12).
 */
function lrEanClash(r){
  const list = (r && Array.isArray(r.warnings)) ? r.warnings : [];
  const hit = list.filter(function(w){
    const t = String((w && w.type) || "");
    return t === "barcode_live_on_amazon" || t === "duplicate_barcode";
  });
  if(!hit.length) return "";
  const w = hit[0] || {};
  const d = w.details || w;
  const asin = d.live_asin || d.asin || "";
  const sku = d.existing_sku || "";
  const where = asin ? ("ASIN " + asin) : (sku ? ("SKU " + sku) : "another listing");
  return '<div class="lr-eanclash" title="' + esc(String(w.message || "")) + '">'
       + '<i class="ti ti-alert-triangle"></i>'
       + '<span>This EAN is already on ' + esc(where)
       + '. Amazon will refuse a second listing for it.</span></div>';
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
    ? 'ASIN <a class="asin-link" href="' + esc(typeof _dpUrl === "function" ? _dpUrl(a.own) : "#")
      + '" target="_blank" rel="noopener" onclick="event.stopPropagation()"'
      + ' title="Open your listing on Amazon">' + esc(a.own) + '</a>'
    : (a.source
        ? '<span class="prod-dim" title="This listing is not live on Amazon yet, so it has no ASIN of its own. '
          + esc(a.source) + ' is the competitor product it was researched from — not your listing.">'
          + 'not live yet · from ' + esc(a.source) + '</span>'
        : '<span class="prod-dim">no ASIN</span>');

  // A BARCODE ANOTHER LISTING OWNS IS COLOURED WHERE IT IS READ, as well as
  // being spelled out underneath. Rule 1 asks for it to be reported; a red
  // number and a sentence are the report.
  const clash = lrEanClash(r);
  return '<div class="prod-wrap">'
    + '<div class="prod-img">'
    +   (urls && urls.length
        ? '<img src="' + esc(urls[0]) + '" loading="lazy" onerror="this.remove()">'
        : '<i class="ti ti-photo"></i>')
    + '</div>'
    + '<div>'
    +   '<div class="prod-title" title="' + esc(r.title || "") + '">'
    +     (esc(r.title || "") || '<span class="prod-dim">(no title)</span>') + '</div>'
    +   '<div class="prod-meta">' + asinBit
    +     '<br>SKU <span class="sku">' + esc(r.sku || "") + '</span>'
          // THE BRAND, asked for and already on the row. It is the one field a
          // listing cannot go up without under Rule 1's own-brand model, so a
          // row that has none says so rather than leaving the line out.
    +     '<br>Brand ' + (r.brand ? '<strong>' + esc(r.brand) + '</strong>'
                                  : '<span class="prod-dim">not set</span>')
    +     (r.barcode
            ? '<br>EAN <strong class="prod-ean' + (clash ? " clash" : "") + '">'
              + esc(r.barcode) + '</strong>'
            : '<br>EAN <span class="prod-dim">none</span>')
    +     '<br>Condition <strong>New</strong>'
    +   '</div>'
    +   clash
    +   lrRisks(r)
    +   (w.n ? '<div class="prod-warn" onclick="event.stopPropagation();openListing(\''
             + esc(r.sku) + '\')"><i class="ti ti-alert-triangle"></i> '
             + w.n + ' warning' + (w.n === 1 ? '' : 's') + '</div>' : "")
    + '</div>'
    + '</div>';
}

/* Performance, last 30 days. Empty until Phase 2 fills LISTING_METRICS.
 *
 * A listing that has never been to Amazon has no performance to report and
 * says so, rather than showing four dashes that look like a failed lookup. */
function lrPerf(r){
  const sent = (typeof lsWasSentToAmazon === "function") ? lsWasSentToAmazon(r) : false;
  if(!sent) return '<div class="d-none">Not yet live</div>';
  const m = lrMetrics(r.sku) || {};
  return lrDataRow("Sales", lrVal(m.sales, {money:true}))
    + lrDataRow("Units sold", lrVal(m.units))
    + lrDataRow("Page views", lrVal(m.views, {comma:true}))
    + lrDataRow("Sales rank",  lrVal(m.rank,  {comma:true}))
    + (m.rank_category ? '<div class="d-cat">(' + esc(m.rank_category) + ')</div>' : "");
}

/* Inventory -- and the handling time, which the mockup has no column for.
 *
 *     "i want my handling days displayed in this page which the mockup does not
 *      have, but the current app has it"
 *
 * It goes here because this is the fulfilment block, and it is drawn by
 * listings.js's own _handCell so the number AND its label are the card view's.
 * That label is the point: the app holds handling_days (what we intend to
 * promise) and Amazon returns handling_time (what the shopfront promises right
 * now), and _handCell is the one place that decides which wins and says which
 * it showed. A second copy here could print the draft's plan in front of a live
 * listing as though it were fact (Rule 12).
 */
function lrInv(r){
  const sent = (typeof lsWasSentToAmazon === "function") ? lsWasSentToAmazon(r) : false;
  const hand = (typeof _handCell === "function") ? _handCell(r) : "";
  const handBlock = hand
    ? '<div class="d-hand"><span class="d-label">Handling</span>' + hand + '</div>'
    : "";
  if(!sent) return '<div class="d-none">' + lrVal(null) + '</div>' + handBlock;
  const m = lrMetrics(r.sku) || {};
  const oos = (v) => (v === 0 || v === "0") ? "red" : "";
  const fba = m.fulfilment || m.fulfillment || "";
  return lrDataRow("On-hand",   lrVal(m.on_hand),   oos(m.on_hand))
    + (fba ? '<div class="d-cat">(' + esc(fba) + ')</div>' : "")
    + lrDataRow("Available", lrVal(m.available), oos(m.available))
    + lrDataRow("Inbound",   lrVal(m.inbound))
    + lrDataRow("Reserved",  lrVal(m.reserved))
    + handBlock;
}

/* Pricing. Price, cost and profit come off the row and are known NOW; the buy
 * box and the lowest price come from Amazon and wait for Phase 2. */
/* DID WE WIN THE BUY BOX?
 *
 * buy_box_pct is Amazon's own figure: the share of page views over the window
 * during which our offer held the featured slot. It is NOT "are we winning
 * right now", and the two must not be dressed as the same thing -- 52% over a
 * month says something quite different from a live yes.
 *
 * So: a full 100% is reported as holding it, a flat 0% as not, and anything in
 * between is shown as the percentage it actually is. Absent stays absent.
 */
function lrBuyBox(m){
  const p = (m || {}).buybox_pct;
  if(p === null || p === undefined) return "";
  if(p >= 99.5)
    return '<div class="bb win" title="Amazon reported our offer in the featured slot for effectively all of the window."><i class="ti ti-circle-check"></i> Featured offer</div>';
  if(p <= 0.5)
    return '<div class="bb lose" title="Amazon reported our offer was never in the featured slot over the window."><i class="ti ti-circle-x"></i> Not winning</div>';
  return '<div class="bb part" title="The share of page views over the window during which our offer held the featured slot. Not a live reading.">'
       + '<i class="ti ti-circle-half-2"></i> Featured ' + Math.round(p) + '% of views</div>';
}

/* The currency Amazon prices this row in. UK sells in GBP and US in USD, and
 * the prefix on the box has to be the marketplace's, not whichever symbol the
 * screen happens to be showing totals in. */
function lrCur(r){
  const mkt = String((typeof rowMkt === "function" ? rowMkt(r) : "")
                     || (r && r.marketplace) || "").toUpperCase();
  if(mkt === "US" || mkt === "USA") return "USD";
  if(["DE", "FR", "IT", "ES", "NL", "SE", "PL", "BE"].indexOf(mkt) >= 0) return "EUR";
  return "GBP";
}

/* An editable price box. Saves through /edit like every other field, via
 * saveEdit() -- the one function that writes a field (Rule 12), which also
 * handles the saved/err styling and keeps ROWS in step. */
function lrPriceBox(r, key, value, title){
  const v = String(value == null ? "" : value).replace(/[^0-9.\-]/g, "");
  return '<div class="price-input-wrap" title="' + esc(title || "") + '">'
       + '<span class="cur">' + esc(lrCur(r)) + '</span>'
       + '<input type="text" value="' + esc(v) + '" inputmode="decimal"'
       +   ' onclick="event.stopPropagation()"'
       +   ' onkeydown="if(event.key===\'Enter\'){event.preventDefault();this.blur();}"'
       +   ' onchange="saveEdit(this,\'' + esc(r.sku) + '\',\'col\',\'' + esc(key) + '\')">'
       + '</div>';
}

function lrPricing(r){
  const m = lrMetrics(r.sku) || {};
  const cur = (typeof CUR_SYMBOL !== "undefined") ? CUR_SYMBOL : "";
  const cost  = (typeof _dwCost === "function") ? _dwCost(r) : "";
  const pnum  = String(r.profit == null ? "" : r.profit).replace(/[^0-9.\-]/g, "");
  const pneg  = pnum !== "" && parseFloat(pnum) < 0;

  return lrPriceBox(r, "Our Price (GBP)", r.price, "The price on the listing")
    + lrDataRow("Cost",   cost ? esc(cost) : lrVal(null))
    + lrDataRow("Profit", pnum ? esc(cur + pnum) : lrVal(null), pneg ? "red" : "green")
    + lrBuyBox(m)
    // What the market charges NOW, from getCompetitivePricing -- a different
    // question from listings.buy_box_price, which is the competitor's price
    // captured when the listing was generated and may be months old.
    + (m.buy_box_price != null
        ? lrDataRow("Competitive", esc(cur + m.buy_box_price)) : "")
    + (m.offer_count != null
        ? lrDataRow("Offers", lrVal(m.offer_count)) : "");
}

/* ESTIMATED FEES -- what Amazon takes out of this price.
 *
 * From the three-tier fee system: the settled rate measured on this product's
 * own orders where it has any, Amazon's own quote where it does not, and the
 * account's measured average as a last resort. `fee_basis` says which, and it
 * is printed rather than hidden -- "18.38% from your sales" and "15.00% quoted"
 * are different degrees of certainty about the same number.
 *
 * Nothing is worked out here. The row carries what /listing/live_metrics
 * returned, and an absent figure is a dash.
 */
function lrFees(r){
  const m = lrMetrics(r.sku) || {};
  const cur = (typeof CUR_SYMBOL !== "undefined") ? CUR_SYMBOL : "";
  const total = m.fees_total != null ? m.fees_total
              : (m.fees != null ? m.fees : null);
  const rate = (m.fee_rate != null) ? (Number(m.fee_rate) * 100) : null;
  const basis = String(m.fee_basis || "");
  const word = basis === "actual" ? "from your sales"
             : basis === "quoted" ? "quoted by Amazon"
             : basis ? "estimated" : "";
  return lrDataRow("Total fees", total != null ? esc(cur + total) : lrVal(null))
    + (m.fba_fee != null ? lrDataRow("FBA fee", esc(cur + m.fba_fee))
       : (m.referral_fee != null ? lrDataRow("Referral", esc(cur + m.referral_fee)) : ""))
    + (rate != null
        ? '<div class="fee-basis">' + rate.toFixed(2).replace(/\.00$/, "") + '% '
          + esc(word) + '</div>'
        : "")
    + '<span class="fee-link" onclick="event.stopPropagation();openListing(\''
    + esc(r.sku) + '\')">Calculate revenue</span>';
}

/* ONE LISTING, AS A DETAILED ROW.
 *
 * Clicking it opens the listing exactly as the card and the table row do --
 * through openListing(), the one function that decides which view that is. */
function detailedRow(r, isChild){
  const sel = (typeof SELECTED !== "undefined") && SELECTED.has(String(r.sku));
  return '<tr class="inv-row' + (sel ? " sel" : "") + (isChild ? " var-child" : "")
    + '" data-sku="' + esc(r.sku) + '"'
    + ' onclick="openListing(\'' + esc(r.sku) + '\')">'
    + '<td class="col-cb" onclick="event.stopPropagation()">'
    +   ((typeof rowSelectBox === "function") ? rowSelectBox(r) : "") + '</td>'
    + '<td class="col-status">' + lrStatus(r) + '</td>'
    + '<td class="col-product">' + lrProduct(r) + '</td>'
    + '<td class="col-perf">' + lrPerf(r) + '</td>'
    + '<td class="col-inv">' + lrInv(r) + '</td>'
    + '<td class="col-price" onclick="event.stopPropagation()">' + lrPricing(r) + '</td>'
    + '<td class="col-fees">' + lrFees(r) + '</td>'
    + '<td class="col-actions" onclick="event.stopPropagation()">'
    +   ((typeof rowActions === "function") ? rowActions(r, "dotb") : "") + '</td>'
    + '</tr>';
}

/* The column header, with the mockup's sub-labels under each name.
 *
 * NO STAR COLUMN, and that is deliberate. The mockup has a favourite toggle;
 * this app has no favourite -- there is no such field on a row, in the listings
 * table or in any route. A star that lit up and then forgot itself on the next
 * render would be a control that lies about having saved something, which is
 * worse than not having one (CLAUDE.md Rule 4). It is one column and a database
 * field away if it is wanted.
 */
function detailedHead(rows){
  const all = rows || [];
  const allSel = all.length && (typeof SELECTED !== "undefined")
                 && all.every(x => SELECTED.has(String(x.sku)));
  const th = function(cls, name, sub){
    return '<th class="' + cls + '">' + name
         + (sub ? '<span class="th-sub">' + sub + '</span>' : "") + '</th>';
  };
  return '<thead class="inv-head"><tr>'
    + '<th class="col-cb"><input type="checkbox" class="rowsel"' + (allSel ? " checked" : "")
    +   ' title="Select every row shown" onchange="event.stopPropagation();selectAllVisible(this.checked)"></th>'
    + th("col-status", "Listing status", "and what Amazon said")
    + th("col-product", "Product details", "brand, identifiers, risks")
    + th("col-perf", "Performance", "last 30 days")
    + th("col-inv", "Inventory", "and handling time")
    + th("col-price", "Pricing", "editable")
    + th("col-fees", "Estimated fees", "per unit")
    + '<th class="col-actions"></th>'
    + '</tr></thead>';
}

/* ═══ THE SORT BAR ═══════════════════════════════════════════════════════
 *
 * "1 – 25 of 130", a sort picker, and the filter icon. The count is the rows
 * this view was handed -- not a page of them, because this view does not
 * paginate: the grid above it decides what is shown and this reports it.
 * Saying "1 – 25 of 130" over 130 drawn rows would be a made-up number.
 */
let LR_SORT = "";

function lrSortBar(rows){
  const n = (rows || []).length;
  const opts = [["", "Default"],
                ["created_new", "Date created: newest"],
                ["created_old", "Date created: oldest"],
                ["price_low", "Price: low to high"],
                ["price_high", "Price: high to low"],
                ["title_az", "Title A-Z"]];
  return '<div class="lr-sortbar">'
    + '<span class="lr-count">' + (n ? ("1 – " + n + " of " + n) : "No listings")
    +   '</span>'
    + '<span>Sort by: '
    +   '<select onchange="lrSetSort(this.value)">'
    +     opts.map(function(o){
            return '<option value="' + o[0] + '"'
                 + (LR_SORT === o[0] ? " selected" : "") + '>' + o[1] + '</option>';
          }).join("")
    +   '</select></span>'
    + '</div>';
}

function lrSetSort(v){
  LR_SORT = String(v || "");
  if(typeof render === "function") render();
}

/* Sorting is done on a COPY. The array this view is handed belongs to the grid,
 * and reordering it in place would silently reorder the table and card views
 * too. */
function lrSortRows(rows){
  const out = (rows || []).slice();
  const num = v => parseFloat(String(v == null ? "" : v).replace(/[^0-9.\-]/g, ""));
  const when = r => new Date(r.created_at || r.date_processed || 0).getTime() || 0;
  if(LR_SORT === "created_new") out.sort((a, b) => when(b) - when(a));
  else if(LR_SORT === "created_old") out.sort((a, b) => when(a) - when(b));
  else if(LR_SORT === "price_low")
    out.sort((a, b) => (num(a.price) || Infinity) - (num(b.price) || Infinity));
  else if(LR_SORT === "price_high")
    out.sort((a, b) => (num(b.price) || -Infinity) - (num(a.price) || -Infinity));
  else if(LR_SORT === "title_az")
    out.sort((a, b) => String(a.title || "").localeCompare(String(b.title || "")));
  return out;
}

/* ═══ VARIATION FAMILIES ══════════════════════════════════════════════════
 *
 * Amazon groups a variation family under one parent that is not itself
 * buyable, with the children carrying the colour, the size, the price and the
 * stock. This view shows the same shape: a "Variations (N)" row you expand.
 *
 * THE GROUPING IS NOT WORKED OUT HERE. domain/families.py already answers it,
 * from Amazon's own `relationships` block, and it is careful in ways worth not
 * repeating: it reads BOTH directions (a child naming its parent and a parent
 * naming its children), because either half can be missing when a SKU has not
 * been enriched or Amazon throttled one call; and it keeps orphans -- a child
 * whose parent is not in this account -- as their own group rather than
 * dropping them. /variations/families serves it from the stored snapshot, so
 * this costs nothing and needs no new route (Rule 12).
 *
 * NOTHING IS GUESSED. A listing whose family is unknown is drawn as a flat row,
 * which is what the brief asks for and what honesty requires: SKUs that merely
 * look alike are not a family, and an invented parent would be a claim about
 * Amazon's catalogue that nobody made.
 *
 * MEASURED, 31 Aug 2026: there are currently NO families on any of the three
 * connected accounts -- 89 listings, all singles, with relationships known for
 * 85 of them. So every row is flat today by fact, not by failure, and this code
 * is what makes the day a family appears show up correctly.
 */

let LR_FAMILIES = null;      // {parentSku: {parent, children:[sku], theme}} or null
let LR_FAM_ASKED = false;
let LR_OPEN_FAMS = {};       // parentSku -> true when expanded

async function lrLoadFamilies(){
  if(LR_FAM_ASKED) return;
  LR_FAM_ASKED = true;
  try{
    const url = "/variations/families";
    const j = await (await fetch(typeof acctUrl === "function" ? acctUrl(url) : url)).json();
    if(!j || !j.ok){ LR_FAMILIES = {}; return; }
    const map = {};
    (j.families || []).forEach(function(f){
      const ps = String(f.parent_sku || "");
      if(!ps) return;
      map[ps] = {
        parent: f.parent || null,
        theme: String(f.theme || ""),
        children: (f.children || []).map(c => String((c && c.sku) || c)).filter(Boolean),
      };
    });
    LR_FAMILIES = map;
  }catch(e){
    // A families lookup that fails leaves every row flat, which is the correct
    // fallback: it is what the screen showed before, and it never invents a
    // grouping it could not confirm.
    LR_FAMILIES = {};
  }finally{
    if(typeof render === "function") render();
  }
}

/* Split rows into families and singles, preserving the incoming order.
 *
 * A family only forms when its children are actually ON THIS SCREEN -- the
 * listings page filters, and a family whose children were filtered out must not
 * appear as an empty group claiming "Variations (4)". */
function lrGroupRows(rows){
  const fams = LR_FAMILIES;
  if(!fams || !Object.keys(fams).length) return {groups: [], flat: rows || []};
  const bySku = {};
  (rows || []).forEach(r => { bySku[String(r.sku)] = r; });

  const claimed = new Set();
  const groups = [];
  Object.keys(fams).forEach(function(ps){
    const f = fams[ps];
    const kids = (f.children || []).map(s => bySku[s]).filter(Boolean);
    if(!kids.length) return;                       // nothing of it is on screen
    const parentRow = bySku[ps] || null;
    kids.forEach(k => claimed.add(String(k.sku)));
    if(parentRow) claimed.add(ps);
    groups.push({parent_sku: ps, parent: f.parent, parentRow: parentRow,
                 theme: f.theme, children: kids});
  });
  const flat = (rows || []).filter(r => !claimed.has(String(r.sku)));
  return {groups: groups, flat: flat};
}

/* The parent row: the family, its count, and NO performance or pricing.
 *
 * Deliberately bare. A parent is not buyable -- it has no price, no stock and
 * no sales of its own -- so a block of dashes across it would read as missing
 * data rather than as "this is a container". Amazon shows it the same way. */
function lrFamilyRow(g){
  const open = !!LR_OPEN_FAMS[g.parent_sku];
  const p = g.parent || {};
  const title = String(p.title || (g.parentRow && g.parentRow.title) || "");
  const asin = String(p.asin || (g.parentRow && g.parentRow.asin) || "");
  const img = (g.parentRow && typeof _rowImages === "function")
              ? (_rowImages(g.parentRow) || [])[0] : "";
  // The parent spans the data columns rather than filling them with dashes: it
  // is a container, not a product, and Amazon draws it the same way.
  return '<tr class="var-parent' + (open ? " open" : "") + '"'
    + ' onclick="lrToggleFamily(\'' + esc(g.parent_sku) + '\')">'
    + '<td class="col-cb" onclick="event.stopPropagation()"></td>'
    + '<td class="col-status">'
    +   '<span class="var-toggle' + (open ? " open" : "") + '">'
    +     '<i class="ti ti-chevron-right"></i></span> '
    +   '<span class="var-count">Variations (' + g.children.length + ')</span>'
    + '</td>'
    + '<td colspan="6">'
    +   '<div class="prod-wrap">'
    +     '<span class="var-img">'
    +       (img ? '<img src="' + esc(img) + '" loading="lazy" onerror="this.remove()">'
                 : '<i class="ti ti-photo"></i>')
    +     '</span>'
    +     '<div>'
    +       '<span class="var-family">'
    +         (esc(title) || '(variation family)') + '</span>'
    +       '<div class="var-meta">'
    +         (asin ? 'Parent ASIN ' + esc(asin) + ' · ' : '')
    +         'Parent SKU ' + esc(g.parent_sku)
    +         (g.theme ? ' · varies by '
                        + esc(String(g.theme).replace(/_/g, " ").toLowerCase()) : '')
    +       '</div>'
    +     '</div>'
    +   '</div>'
    + '</td>'
    + '</tr>';
}

function lrToggleFamily(parentSku){
  const k = String(parentSku);
  if(LR_OPEN_FAMS[k]) delete LR_OPEN_FAMS[k]; else LR_OPEN_FAMS[k] = true;
  if(typeof render === "function") render();
}

function lrExpandAll(open){
  LR_OPEN_FAMS = {};
  if(open){
    const g = lrGroupRows((typeof ROWS !== "undefined") ? ROWS : []);
    g.groups.forEach(x => { LR_OPEN_FAMS[x.parent_sku] = true; });
  }
  if(typeof render === "function") render();
}

/* A block of listings in this view: one header, then the rows. */
function detailedBlock(rows){
  if(!rows || !rows.length) return "";
  // Ask for the numbers and the families the first time this view draws. Not
  // awaited: the rows are drawn now with whatever is known, and each re-renders
  // when it lands. A local read is quick, but the screen should not wait on it.
  lrLoadMetrics(rows);
  lrLoadFamilies();

  const g = lrGroupRows(rows);
  // Families first, then everything that belongs to none -- the way Amazon
  // orders them, and it keeps the groups from being lost among 200 flat rows.
  // The sort applies to the loose rows: a family's children are ordered by the
  // family, and pulling them apart by price would stop it being one.
  const body = g.groups.map(function(fam){
      return lrFamilyRow(fam)
        + (LR_OPEN_FAMS[fam.parent_sku]
            ? fam.children.map(c => detailedRow(c, true)).join("")
            : "");
    }).join("")
    + lrSortRows(g.flat).map(r => detailedRow(r)).join("");

  return '<div class="card lrwrap">'
       + lrMetricsBar()
       + (g.groups.length ? lrFamilyControls(g.groups) : "")
       + lrSortBar(rows)
       + '<table class="inv-table">' + detailedHead(rows)
       +   '<tbody>' + body + '</tbody></table>'
       + '</div>';
}

/* Expand all / collapse all, shown only when there is something to expand. */
function lrFamilyControls(groups){
  const openN = groups.filter(g => LR_OPEN_FAMS[g.parent_sku]).length;
  const willOpen = openN < groups.length;
  // BOTH ICON NAMES ARE WRITTEN OUT IN FULL, not built by concatenation.
  // test_http_perf.py scans every icon class the app asks for and checks it
  // exists in the subset font, because a missing one renders as an empty box
  // with no error anywhere. A class assembled at runtime from a prefix plus a
  // direction is invisible to that scan, so both are spelled out -- the check
  // stays able to do its job rather than being handed an exception.
  // (The comment avoids writing such a prefix literally, because the scan reads
  // comments too and would record it as another half-name.)
  const btn = willOpen
    ? '<i class="ti ti-chevrons-down"></i> Expand all'
    : '<i class="ti ti-chevrons-up"></i> Collapse all';
  return '<div class="lr-famctl">'
    + '<span class="prod-dim">' + groups.length + ' variation famil'
    + (groups.length === 1 ? 'y' : 'ies') + '</span>'
    + '<button class="lr-refresh" onclick="lrExpandAll(' + willOpen + ')">'
    + btn + '</button></div>';
}
