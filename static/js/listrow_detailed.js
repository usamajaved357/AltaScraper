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
 *     drawerMore(...) the overflow menu behind the three dots. NOT rowActions,
 *                     which draws seven buttons in a strip: this view shows one
 *                     control and puts everything behind it. rowActions is
 *                     unchanged and still used by the table and card views.
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
// The server has answered at least once, so LR_LAST_FETCH means something.
// Without this, "nobody has ever fetched" (0) and "we have not asked yet" (0)
// are the same value, and lrAutoRefresh has to tell them apart: the first is
// the stalest state there is and the second must not act at all.
let LR_ANSWERED = false;
// The SKUs already asked about. A SET, not the last key -- see lrLoadMetrics.
let LR_ASKED = new Set();

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

  // WHY THIS REMEMBERS SKUs AND NOT "THE LAST SET ASKED FOR".
  //
  //     "the page is blinking when i place my cursor over the item also the
  //      featured offer and many more things on that page are blinking"
  //
  // The page was redrawing itself perpetually, and hovering just made it
  // visible. This held ONE key -- the sorted SKUs of the last set it fetched --
  // and one screen draws SEVERAL blocks: miles_template.js calls listBlock()
  // separately for queued, drafts, claimed and gone, and each one reaches
  // detailedBlock() with a DIFFERENT set of rows.
  //
  // So the key alternated, for ever:
  //
  //     render -> block A: key A is new    -> fetch -> render
  //            -> block B: key B is not A  -> fetch -> render
  //            -> block A: key A is not B  -> fetch -> render  ...
  //
  // Every reply called render(), which rebuilt every block, which asked again.
  // A set of SKUs cannot alternate: once a SKU has been asked about it stays
  // asked about, so the second block finds nothing new and the loop stops on
  // the first pass.
  const need = force ? skus : skus.filter(s => !LR_ASKED.has(s));
  // NOTHING NEW MEANS NOTHING HAPPENS -- no fetch, and no render either. A
  // render here would restart the cycle by itself.
  if(!need.length) return;
  if(LR_LOADING) return;      // one in flight; the next draw picks up the rest
  LR_LOADING = true;
  if(force) LR_ASKED = new Set();
  need.forEach(s => LR_ASKED.add(s));
  try{
    // A cap matching the route's own, so the URL cannot grow past what a
    // server will accept on a large catalogue.
    const ask = need.slice(0, 400);
    let url = "/listing/live_metrics?skus=" + encodeURIComponent(ask.join(","));
    if(force) url += "&fetch=1";
    const j = await (await fetch(typeof acctUrl === "function" ? acctUrl(url) : url)).json();
    if(j && j.ok){
      // MERGED, not replaced. Several blocks contribute their own SKUs, and
      // assigning the reply would throw away whatever the previous block had
      // just learned -- which is the same alternation in another form.
      LISTING_METRICS = Object.assign({}, LISTING_METRICS, j.metrics || {});
      LR_COVERAGE = j.coverage || {};
      LR_LAST_FETCH = j.last_updated || 0;
      LR_ERRORS = j.errors || {};
      LR_ANSWERED = true;
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

/* The Refresh button: throw the cached Amazon answers away and ask again.
 *
 * `quiet` suppresses the two toasts, and nothing else. The automatic refresh
 * below calls THIS function rather than carrying a copy of it (CLAUDE.md
 * Rule 12) -- a second "ask Amazon again" that drifted from this one is how a
 * screen ends up with two refreshes that disagree about what they cleared. */
async function lrRefreshMetrics(quiet){
  const say = function(m){ if(!quiet && typeof toast === "function") toast(m); };
  say("Refreshing metrics from Amazon…");
  try{
    await fetch("/listing/metrics_forget", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify((typeof acctBody === "function") ? acctBody({}) : {})});
  }catch(e){}
  const rows = (typeof ROWS !== "undefined") ? ROWS : [];
  await lrLoadMetrics(rows, true);
  const bad = Object.keys(LR_ERRORS || {});
  say(bad.length ? ("Amazon refused: " + LR_ERRORS[bad[0]]) : "Metrics updated");
}

/* ═══ THE REFRESH THAT NOBODY HAS TO PRESS ════════════════════════════════
 *
 *     "Instead of adding a visible button, auto-refresh in the background."
 *
 * The button exists (lrMetricsBar) but its bar is display:none from the density
 * pass, so as things stood there was NO way to ask Amazon again -- the rank,
 * competitive price and FBA stock on this screen could only ever be as fresh as
 * the last time something else happened to fetch them.
 *
 * WHAT IT DOES NOT DO: it does not forget the cache. lrRefreshMetrics(true)
 * would, and that is right for a person who does not believe what is on screen,
 * but wrong for a timer -- forgetting makes every group stale by definition, so
 * a 20-hourly forget would re-fetch rank, pricing and stock for the whole
 * catalogue every time. This sends fetch=1 and lets the server's own TTLs
 * (data/metrics_cache.py: 4h pricing, 4h FBA, 24h rank) decide what is actually
 * due. Usually that is nothing, and the call costs one local read.
 *
 * TWO CLOCKS, AND BOTH MUST AGREE:
 *
 *   - the SERVER's, LR_LAST_FETCH -- when Amazon was really last asked. This is
 *     the one that says whether the figures are old, and it is shared by every
 *     browser and machine looking at this account.
 *   - this BROWSER's, in localStorage -- a cooldown, so a tab reopened twenty
 *     times in an afternoon does not fire twenty refreshes while Amazon is
 *     refusing and the server clock consequently never moves.
 *
 * NO CLAIM IS MADE ABOUT THROTTLING. Every SP-API call counts against a rate
 * limit; there is no free one. The reason this is cheap is the TTL check above,
 * not a property of the endpoint.
 */
const LR_AUTO_HOURS = 20;
let LR_AUTO_TRIED = false;          // once per page load, whatever else happens

function _lrAutoKey(){
  const id = (typeof acctId === "function" && acctId()) || "";
  return "alta_lr_auto_refresh:" + id;
}

/* Ask Amazon again if it has been LR_AUTO_HOURS since anyone did.
 * Returns true if a refresh was started -- for the test, and for the caller
 * that wants to know whether the screen is about to change under it. */
function lrAutoRefresh(){
  if(LR_AUTO_TRIED) return false;
  // Nothing has come back from the server yet, so the server clock is unknown.
  // Wait for the next draw rather than guessing that "unknown" means "old".
  if(LR_LOADING || !LR_ANSWERED) return false;
  LR_AUTO_TRIED = true;

  const gapMs = LR_AUTO_HOURS * 60 * 60 * 1000;
  // LR_LAST_FETCH === 0 is "Amazon has never been asked about this account",
  // which is stale by any reading, so it falls through to the fetch.
  if(LR_LAST_FETCH && Date.now() - Number(LR_LAST_FETCH) * 1000 < gapMs){
    return false;
  }

  let mine = 0;
  try{ mine = parseInt(localStorage.getItem(_lrAutoKey()) || "0", 10) || 0; }
  catch(e){}                          // private mode, or storage turned off
  if(Date.now() - mine < gapMs) return false;
  try{ localStorage.setItem(_lrAutoKey(), String(Date.now())); }catch(e){}

  const rows = (typeof ROWS !== "undefined") ? ROWS : [];
  lrLoadMetrics(rows, true);
  return true;
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
  // MONEY HAS TWO DECIMALS. Seen in a browser: a stored fee of 2.4 printed as
  // "£2.4" beside a "£5.26" and a "£1.99" in the same column -- a price with one
  // decimal reads as a different KIND of number from the ones around it, and in
  // a column of money it reads as a truncation. The database stores a float, so
  // 2.40 and 2.4 are the same value and only the printing was wrong.
  if(opts.money){
    const n = Number(v);
    s = (typeof CUR_SYMBOL !== "undefined" ? CUR_SYMBOL : "")
      + (isFinite(n) ? n.toFixed(2) : String(v));
  }
  if(opts.comma) s = String(v).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return esc(s);
}

/* An amount, always to two decimals, for the places that build their own string
 * instead of going through lrVal -- the fee lines and the featured price. One
 * formatter, so a column cannot hold "£2.4" and "£5.26" at once. */
function lrMoney(v){
  if(v === null || v === undefined || v === "") return lrVal(null);
  return lrVal(v, {money: true});
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
/* IS THIS LISTING ON AMAZON? Not "does the stored word say so".
 *
 *     "Some listings on the 'Live on Amazon' filtered view show status
 *      GENERATED instead of LIVE or ACTIVE. This makes no sense."
 *
 * It does not, and the answer already existed. isActuallyLive() matches the
 * row's SKU and our own ASIN against Amazon's catalogue, and _shownStatus()
 * wraps it -- both in listings.js, both used by the table view and by the count
 * tiles above the list since long before this view was built. This view was the
 * one place still reading r.status raw, which is why the tiles could say LIVE
 * over a row labelled GENERATED.
 *
 * NOT A NEW RULE HERE. The brief proposes "if the listing has an ASIN and is in
 * the catalogue, override the displayed status" -- which is what isActuallyLive
 * does. Writing it again in this file would be a fourth opinion about what LIVE
 * means (Rule 12), and it would be the one that disagreed first.
 */
function lrShownStatus(r){
  const raw = (typeof _shownStatus === "function") ? _shownStatus(r)
                                                   : ((r && r.status) || "");
  return (typeof lsNorm === "function") ? lsNorm(raw)
                                        : String(raw || "").toUpperCase();
}

/* Is it on Amazon, by any reading? Either the catalogue has it, or we sent it
 * and Amazon has not published it yet. This is the gate for "has this listing
 * anything to report" -- performance, stock, fees. */
function lrOnAmazon(r){
  if(typeof isAmazonLive === "function" && isAmazonLive(r)) return true;
  return (typeof lsWasSentToAmazon === "function") ? lsWasSentToAmazon(r) : false;
}

function lrStatus(r){
  const st = lrShownStatus(r);
  // THE STORED WORD, WHEN IT DISAGREES. Amazon's answer is the one shown, but
  // "this app's record still says GENERATED" is a real fact with a real cause --
  // the listing went live and nothing wrote the status back, which a Sync
  // fixes. Silently showing LIVE would hide the stale record; showing GENERATED
  // would be wrong. So: the truth, with the disagreement named on hover.
  const stored = (typeof lsStatusOf === "function") ? lsStatusOf(r)
                                                    : String(r.status||"").toUpperCase();
  const stale = (st !== stored) ? stored : "";
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
       + (stale
           ? '<div class="status-stale" title="Amazon has this listing, so it is '
             + 'live. This app’s own record still says ' + esc(stale)
             + ' — nothing wrote the status back after it published. A Sync '
             + 'corrects it; nothing is wrong with the listing.">'
             + 'we still record ' + esc(stale) + '</div>'
           : "")
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
/* THE PICTURE, FROM BOTH PLACES IT CAN BE.
 *
 *     "Many items have blank image squares. The image data exists in the
 *      database or LIVE_ITEMS. Check both sources."
 *
 * _rowImages(r) reads the row's OWN attributes -- the draft's
 * main_product_image_locator. _liveImageFor(r) reads what Amazon holds for the
 * live listing out of LIVE_ITEMS, which is where the dual-source fix in
 * routes/live_routes.py puts the picture it found in either summaries.mainImage
 * or attributes.main_product_image_locator.
 *
 * Amazon's wins when it exists: it is what a shopper is actually looking at.
 * Both helpers are listings.js's, so this reads no field either of them does
 * not already own (Rule 12).
 */
function lrImage(r){
  const live = (typeof _liveImageFor === "function") ? (_liveImageFor(r) || "") : "";
  if(live) return live;
  const own = (typeof _rowImages === "function") ? (_rowImages(r) || []) : [];
  return own.length ? own[0] : "";
}

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
  const img = lrImage(r);
  return '<div class="prod-wrap">'
    + '<div class="prod-img">'
    +   (img
        ? '<img src="' + esc(img) + '" loading="lazy" onerror="this.remove()">'
        : '<i class="ti ti-photo"></i>')
    + '</div>'
    + '<div>'
        // THE TITLE OPENS THE LISTING. It was plain text beside a row that was
        // already clickable, so the one thing that looks like the product's
        // name was the one thing that did not behave like a link.
    +   '<div class="prod-title" title="' + esc(r.title || "") + '"'
    +     ' onclick="event.stopPropagation();openListing(\'' + esc(r.sku) + '\')">'
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
  // "NOT YET LIVE" IS A CLAIM ABOUT AMAZON, so it is answered by Amazon.
  //
  //     "Most listings on the Live on Amazon page show 'Not yet live' in the
  //      Performance column. This is wrong -- these are live products with real
  //      sales data."
  //
  // This read lsWasSentToAmazon(), which is `status is LIVE or SUBMITTED` --
  // the stored word again, and the same root as the GENERATED badge above. A
  // listing published outside this app, or one whose status was never written
  // back, was told it had not been published. lrOnAmazon asks the catalogue
  // first and falls back to the stored word only when there is no catalogue to
  // ask (before the first Sync, or on the Drafts tab).
  //
  // Once past this gate every figure is a dash when unknown -- see lrVal. A
  // dash says "we have not been told"; "Not yet live" says "there is nothing to
  // tell", and only one of those was ever true here.
  if(!lrOnAmazon(r)) return '<div class="d-none">Not yet live</div>';
  const m = lrMetrics(r.sku) || {};
  // THE RANK'S OWN CATEGORY FIRST, the row's second.
  //
  //     "Amazon shows the category in parentheses under the sales rank number
  //      -- like '45,230 (Home & Kitchen)'. If unknown, don't show anything."
  //
  // A sales rank is always a rank WITHIN a category, and metrics_routes caches
  // the pair together: _rank_for stores {rank, category} from the same answer.
  // So when there is a rank, the category shown is the one that rank belongs
  // to -- printing the row's own shop category beside somebody else's rank
  // would put a number under a heading it was not measured in.
  //
  // listings.amazon_category is the fallback, and it is worth having: it is
  // known for drafts that have never had a rank at all.
  const cat = String(m.category || r.amazon_category || r.subcategory || "").trim();
  return lrDataRow("Sales", lrVal(m.sales, {money:true}))
    + lrDataRow("Units sold", lrVal(m.units))
    + lrDataRow("Page views", lrVal(m.views, {comma:true}))
    + lrDataRow("Sales rank",  lrVal(m.rank,  {comma:true}))
    + (cat ? '<div class="d-cat">(' + esc(cat) + ')</div>' : "");
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
/* THE HANDLING TIME, EDITABLE -- but only the half of it that is ours.
 *
 *     "The handling time is displayed but not clickable/editable. Make it an
 *      inline editable field."
 *
 * TWO NUMBERS LIVE HERE and only one of them can be typed. handling_days is
 * what this app holds -- a column in _EDITABLE_COLS, ours to change.
 * handling_time is what Amazon is promising buyers right now, and it is a
 * reading, not a setting: typing over it here would not change the shopfront.
 *
 * So the box edits ours, and _handCell is kept underneath on a live listing
 * because that is the one place that compares the two and says when they
 * disagree -- a listing promising two days while the plan says five is a late
 * dispatch, and that comparison is not reimplemented here (Rule 12).
 */
function lrHandRow(r){
  const live = (typeof isAmazonLive === "function") ? isAmazonLive(r) : false;
  const ours = r.handling_days;
  const box = '<div class="d-row"><span class="d-label">Handling</span>'
    + '<span class="d-val">'
    + lrEditBox({sku: r.sku, field: "handling",
                 value: (ours === null || ours === undefined) ? "" : String(ours),
                 cls: "lr-hand", placeholder: "—",
                 title: "Days to dispatch, as this app holds it. Saved here, not "
                      + "sent to Amazon — the listing's own handling time is "
                      + "changed on Amazon."})
    + '<span class="lr-unit">d</span></span></div>';
  // Amazon's own figure, and the disagreement flag, only where there can be one.
  const amz = (live && typeof _handCell === "function") ? _handCell(r) : "";
  return box + (amz ? '<div class="d-hand">' + amz + '</div>' : "");
}

/* CAN THIS LISTING'S STOCK BE TYPED?
 *
 *     "For FBM listings, the Available quantity should be editable inline (FBA
 *      listings stay read-only since Amazon controls stock)."
 *
 * ONLY WHEN THE CHANNEL IS KNOWN AND SAYS MERCHANT. stock_daily.fulfillment
 * carries DEFAULT / MFN for merchant-fulfilled and AMAZON for FBA -- but it is
 * also "" when nothing has been read yet, and an empty string is NOT a merchant
 * listing, it is an unanswered question. An editable box on an unknown channel
 * would be a control that offers something the server then refuses
 * (push_quantity declines a listing with no fulfillment_availability, which is
 * how FBA presents), and a refusal after the fact is worse than a box that was
 * never offered.
 *
 * MEASURED: all 100 SKUs with a stock reading on this account are DEFAULT, so
 * this is the ordinary case here and FBA is the exception.
 */
function lrCanEditQty(r, m){
  const ff = String((m && (m.fulfillment || m.fulfilment)) || "").toUpperCase();
  if(ff === "DEFAULT" || ff === "MFN") return true;
  return false;
}

/* The Available line: a box on a merchant listing, a reading on anything else.
 *
 * UNLIKE THE OTHER THREE, SAVING THIS GOES TO AMAZON. Stock has no column in
 * this app on purpose -- routes/handling_routes.stock_bulk_update spells out
 * why: Amazon is the authority on it, and a number recorded here would be a
 * second, immediately-stale copy for every other screen to read. So the box
 * patches the live listing, and both the tooltip here and the bar at the foot
 * of the screen say so before anything is pressed. */
function lrAvailRow(r, m, oos){
  if(!lrCanEditQty(r, m)){
    const ff = String((m && (m.fulfillment || m.fulfilment)) || "").toUpperCase();
    const why = ff
      ? "Amazon holds this stock (" + ff + "), so it is not set from here."
      : "This listing's fulfilment channel has not been read yet, so this app "
        + "cannot tell whether the stock is Amazon's or yours. Sync to find out.";
    return '<div class="d-row"><span class="d-label">Available</span>'
      + '<span class="d-val ' + oos(m.available) + '">'
      + '<span class="lr-ro" title="' + esc(why) + '">' + lrVal(m.available)
      + '</span></span></div>';
  }
  return '<div class="d-row"><span class="d-label">Available</span>'
    + '<span class="d-val">'
    + lrEditBox({sku: r.sku, field: "qty", cls: "lr-qty",
                 value: (m.available === null || m.available === undefined)
                        ? "" : String(m.available),
                 placeholder: "—",
                 title: "Units you can sell. Saving this CHANGES THE LIVE "
                      + "LISTING ON AMAZON — 0 stops it selling."})
    + '</span></div>';
}

/* ONE TEMPLATE PER CHANNEL, NOT A MIXTURE.
 *
 *     "Some listings show the full breakdown (On-hand, Available, Inbound,
 *      Unfulfillable, Reserved) while others show only '— Handling 2d'. ...
 *      Never show a mix -- pick the right template based on fulfillment
 *      channel."
 *
 * The mixture had TWO causes and the brief names only one of them:
 *
 *   THE CHANNEL. Inbound, Reserved and Unfulfillable are facts about stock in
 *   an Amazon warehouse. On a merchant-fulfilled listing there is no such
 *   warehouse, so those three lines were three dashes that mean "not
 *   applicable" printed in the place where a dash means "not known" -- the one
 *   distinction this whole block exists to keep.
 *
 *   THE GATE ABOVE THEM. The "— Handling 2d" rows were not a different channel
 *   at all: they were rows this function had decided were not on Amazon, using
 *   the stored status (see lrPerf for the same root). So one listing's stock
 *   was hidden and its neighbour's shown for a reason that had nothing to do
 *   with fulfilment.
 *
 * Three templates, and the third is not a failure to choose -- it is the honest
 * answer when the channel has not been read yet, which is different from both.
 */
function lrInvChannel(m){
  const ff = String((m && (m.fulfillment || m.fulfilment)) || "").toUpperCase();
  if(ff === "DEFAULT" || ff === "MFN") return "merchant";
  if(ff) return "amazon";           // AMAZON, AFN, or anything else Amazon says
  return "unknown";
}

function lrInv(r){
  const handBlock = lrHandRow(r);
  // Same gate as the Performance column, for the same reason: a listing
  // published outside this app, or one whose status was never written back, is
  // still on Amazon and still has stock.
  if(!lrOnAmazon(r)) return '<div class="d-none">' + lrVal(null) + '</div>' + handBlock;
  const m = lrMetrics(r.sku) || {};
  const oos = (v) => (v === 0 || v === "0") ? "red" : "";
  const chan = lrInvChannel(m);

  if(chan === "merchant"){
    // WHAT WE HOLD AND HOW FAST WE SHIP IT. No on-hand line beside available:
    // for a merchant listing the quantity on the offer IS the available
    // quantity, and printing it twice under two names invites the reader to
    // look for a difference that cannot exist.
    return lrAvailRow(r, m, oos)
      + '<div class="d-cat" title="You hold and dispatch this stock. Amazon '
      + 'stores none of it, so there is no inbound, reserved or unfulfillable '
      + 'to report.">(merchant fulfilled)</div>'
      + handBlock;
  }
  if(chan === "amazon"){
    return lrDataRow("On-hand",   lrVal(m.on_hand),   oos(m.on_hand))
      + '<div class="d-cat" title="Amazon holds and ships this stock.">(Amazon fulfilled)</div>'
      + lrAvailRow(r, m, oos)
      + lrDataRow("Inbound",   lrVal(m.inbound))
      // UNFULFILLABLE IS RED WHEN THERE IS ANY. Stock Amazon holds and will not
      // sell -- damaged, expired, defective -- and it looks like inventory on
      // every other screen.
      + lrDataRow("Unfulfillable", lrVal(m.unfulfillable),
                  (m.unfulfillable ? "red" : ""))
      + lrDataRow("Reserved",  lrVal(m.reserved))
      + handBlock;
  }
  // NOT A CHANNEL, A GAP. Whatever stock figure arrived is still shown -- it is
  // real -- but the lines that only make sense for one channel are not drawn
  // for a listing we cannot place in either.
  return lrAvailRow(r, m, oos)
    + '<div class="d-cat" title="This listing’s fulfilment channel has not been '
    + 'read yet, so the warehouse figures — inbound, reserved, unfulfillable — '
    + 'are not shown: they would be dashes meaning ‘not applicable’ next to '
    + 'dashes meaning ‘not known’. Sync reads it.">(channel not read yet)</div>'
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
/* THE FEATURED OFFER: THE PRICE FIRST, THE SHARE SECOND.
 *
 *     "The pricing column shows 'Featured 83% of views' -- this is the Buy Box
 *      win percentage. Amazon's Manage Inventory page shows the actual Featured
 *      Offer price."
 *
 * Both are worth having and they answer different questions. The PRICE is what
 * a shopper pays in the featured slot right now -- CompetitivePriceId "1"'s
 * LandedPrice, price plus shipping, from getCompetitivePricing (see
 * api/amazon_metrics.competitive_price). The SHARE is how much of the last
 * window our offer held that slot. One is a live number about the market, the
 * other is a historic number about us, and neither substitutes for the other.
 *
 * IT IS NOT NECESSARILY OUR PRICE. Whoever holds the slot sets it; the share
 * beneath says how often that was us. So it is labelled "Featured offer" --
 * Amazon's own word for the slot -- and never "our price".
 *
 * It moved up here from a line called "Competitive" further down the block,
 * which is the same figure under a name that did not say what it was.
 */
function lrBuyBox(m, cur){
  m = m || {};
  const sym = cur || ((typeof CUR_SYMBOL !== "undefined") ? CUR_SYMBOL : "");
  const price = (m.buy_box_price != null)
    ? '<div class="d-row"><span class="d-label">Featured offer</span>'
      + '<span class="d-val" title="What a shopper pays in the featured slot now '
      + '— price plus delivery, whoever is holding it. From Amazon’s competitive '
      + 'pricing, refreshed at most every 4 hours.">' + lrMoney(m.buy_box_price)
      + '</span></div>'
    // A DASH, NOT SILENCE. This line was drawn only when the figure existed, so
    // a listing Amazon had not been asked about looked identical to one with no
    // featured offer at all.
    : '<div class="d-row"><span class="d-label">Featured offer</span>'
      + '<span class="d-val" title="Amazon has not been asked for this listing’s '
      + 'featured price yet. It arrives on the next refresh.">'
      + lrVal(null) + '</span></div>';

  const p = m.buybox_pct;
  let share = "";
  if(p !== null && p !== undefined){
    share = (p >= 99.5)
      ? '<div class="bb win" title="Amazon reported our offer in the featured slot for effectively all of the window."><i class="ti ti-circle-check"></i> Ours, all of the window</div>'
      : (p <= 0.5)
        ? '<div class="bb lose" title="Amazon reported our offer was never in the featured slot over the window."><i class="ti ti-circle-x"></i> Never ours</div>'
        : '<div class="bb part" title="The share of page views over the window during which our offer held the featured slot. Not a live reading.">'
          + '<i class="ti ti-circle-half-2"></i> Ours for ' + Math.round(p) + '% of views</div>';
  }
  return price + share;
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

/* An editable price box.
 *
 * IT USED TO SAVE THE INSTANT YOU LOOKED AWAY -- onchange straight into
 * saveEdit(). That worked, and was the problem:
 *
 *     "When you change a price in the inline input box and click elsewhere,
 *      nothing happens."
 *
 * Nothing VISIBLE happened. The write had already gone, with no way to take it
 * back and nothing on the row to say it had. The box is now staged instead:
 * lrEditBox holds the change, marks itself, and the bar at the foot of the
 * screen saves or discards every held change at once. The endpoint is
 * unchanged -- see listrow_edit.js, which still posts to /edit.
 */
function lrPriceBox(r, key, value, title){
  const v = String(value == null ? "" : value).replace(/[^0-9.\-]/g, "");
  return '<div class="price-input-wrap" title="' + esc(title || "") + '">'
       + '<span class="cur">' + esc(lrCur(r)) + '</span>'
       + lrEditBox({sku: r.sku, field: "price", value: v,
                    title: title || "The price on the listing"})
       + '</div>';
}

/* THE REPRICER'S FLOOR AND CEILING, under the price, where Amazon puts them.
 *
 *     "Show the minimum price field under the price input box ... Same for
 *      maximum price."
 *
 * THEY DO NOT LIVE ON THE LISTING. min_price and max_price are the repricer's
 * rule for a SKU, in sourcing_rules -- there is no such column on a listing row
 * and no route on this screen that returns one. So the box shows a value only
 * when the repricer's own rules happen to be loaded in the page (SRC_ROW_RULES,
 * which the Repricer screen fills), and otherwise says NOTHING RATHER THAN
 * NOTHING-MEANING-NONE: an empty box under the word "Min" reads as "no floor
 * is set", and a listing that has a floor of 18.24 would be showing the
 * opposite of the truth.
 *
 * Typing in it saves through /sourcing/rules, the route the Repricer screen
 * already uses (Rule 12).
 */
function lrRule(sku){
  try{
    if(typeof SRC_ROW_RULES !== "undefined" && SRC_ROW_RULES)
      return SRC_ROW_RULES[String(sku)] || null;
  }catch(e){}
  return null;
}

/* FETCH THE FLOORS ONCE, SO THE BOXES CAN SHOW WHAT IS ACTUALLY SET.
 *
 * The comment above used to end "no route on this screen that returns one".
 * There is now: /sourcing/rules_all, which reads the rules table and stops --
 * NOT /sourcing/list, which re-prices every enrolled SKU against every supplier
 * to answer a question about a stored number.
 *
 * IT FILLS SRC_ROW_RULES, the Repricer's own global, with the Repricer's own
 * shape (repo.rule_for: the account default with the SKU's override over it).
 * A second, thinner store beside it would be a rule object that was complete on
 * one screen and partial on another, and the Repricer's dialogs open pre-filled
 * from this -- a partial copy would silently offer the wrong defaults and save
 * them (Rule 12).
 *
 * IT DOES NOT OVERWRITE what the Repricer has already loaded, for the same
 * reason: that copy carries the runtime additions source_run makes.
 *
 * MEASURED: 3 SKUs on this account have a rule row at all, one of which carries
 * a floor and none a ceiling. So most rows will still show a dash -- but now it
 * is a dash meaning "none is set", which is the truth, rather than one meaning
 * "not loaded here".
 */
let LR_RULES_ASKED = false;
// Answered, so an absent rule can be reported as "none is set" rather than as
// "we have not looked" -- the same distinction the dashes elsewhere on this row
// are built around.
let LR_RULES_LOADED = false;

async function lrLoadRules(){
  if(LR_RULES_ASKED) return;
  LR_RULES_ASKED = true;
  if(typeof SRC_ROW_RULES === "undefined") return;   // sourcing.js not loaded
  try{
    // _srcUrl, the same stamper every other /sourcing call uses -- it sends the
    // account AND the marketplace, which this route scopes on. acctUrl sends
    // only the account, and a rule is per marketplace.
    const url = (typeof _srcUrl === "function") ? _srcUrl("/sourcing/rules_all")
                                                : "/sourcing/rules_all";
    const j = await (await fetch(url)).json();
    if(!j || !j.ok) return;
    LR_RULES_LOADED = true;
    let added = 0;
    Object.keys(j.rules || {}).forEach(function(sku){
      if(SRC_ROW_RULES[sku] === undefined){ SRC_ROW_RULES[sku] = j.rules[sku]; added++; }
    });
    if(added && typeof render === "function") render();
  }catch(e){}
}

function lrRuleBox(r, key, label, title){
  const rule = lrRule(r.sku);
  if(!rule){
    // TWO REASONS FOR A DASH, AND THEY ARE NOT THE SAME. Before the rules land
    // this screen genuinely does not know; after they land, a SKU with no rule
    // row is one the repricer is not tracking, which IS an answer.
    const why = LR_RULES_LOADED
      ? "The repricer is not tracking this SKU, so it has no "
        + label.toLowerCase() + ". Enrol it in the Repricer to set one."
      : "Reading the repricer's rules…";
    return '<div class="d-row"><span class="d-label">' + esc(label) + '</span>'
         + '<span class="d-val dash" title="' + esc(why) + '">—</span></div>';
  }
  const v = rule[key];
  return '<div class="price-input-wrap small" title="' + esc(title) + '">'
       + '<span class="cur">' + esc(label) + '</span>'
       + '<input type="text" inputmode="decimal" value="'
       +   esc(v == null ? "" : String(v)) + '"'
       +   ' onclick="event.stopPropagation()"'
       +   ' onkeydown="if(event.key===\'Enter\'){event.preventDefault();this.blur();}"'
       +   ' onchange="lrSaveRule(\'' + esc(r.sku) + '\',\'' + key + '\',this)">'
       + '</div>';
}

function lrFloorCeiling(r){
  return lrRuleBox(r, "min_price", "Min", "The lowest the repricer may go")
       + lrRuleBox(r, "max_price", "Max", "The highest the repricer may go");
}

/* Save one repricer rule field. Through /sourcing/rules, which validates the
 * number and refuses a margin target that cannot be reached -- this screen does
 * not second-guess any of that. */
async function lrSaveRule(sku, key, el){
  const raw = String(el.value || "").trim();
  const val = raw === "" ? null : parseFloat(raw);
  if(raw !== "" && !isFinite(val)){ toast("That is not a number."); return; }
  const body = {sku: sku, rule: {}};
  body.rule[key] = val;
  try{
    const j = await (await fetch("/sourcing/rules", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify((typeof _srcBody === "function") ? _srcBody(body) : body)
    })).json();
    if(!j || !j.ok){ toast("Could not save: " + ((j && j.error) || "")); return; }
    const rule = lrRule(sku);
    if(rule) rule[key] = val;
    toast(val == null ? "Cleared" : "Saved");
  }catch(e){ toast("Could not save: " + e); }
}

/* THE COST, EDITABLE, WITHOUT A SECOND OPINION ABOUT WHAT IT IS.
 *
 *     "The Cost value is displayed as plain text. It should be an editable
 *      input like the price field."
 *
 * cogsOf() decides what the cost IS and where it came from -- a figure typed by
 * the owner, or one read off the SKU's price prefix, or nothing known. That
 * resolution is not repeated here (Rule 12); this only draws the box and
 * labels the source, because "9.18 because you typed it" and "9.18 because the
 * SKU says so" behave differently when the box is cleared.
 *
 * THE BOX IS EMPTY WHEN NOTHING IS KNOWN, with the placeholder saying so.
 * Pre-filling it with 0.00 would be the exact mistake cogs.js was built to
 * avoid: an item that appears to cost nothing looks infinitely profitable.
 */
function lrCostRow(r){
  const c = (typeof cogsOf === "function") ? cogsOf(r) : {cost: null, source: ""};
  const known = c.cost !== null && c.cost !== undefined;
  const tip = c.source === "manual"
    ? "Your own figure — it beats what the SKU says. Empty it to go back to the SKU."
    : (c.source === "sku"
        ? "Read from the SKU's price prefix. Type here to override it."
        : "No cost known for this SKU. Every profit figure on this row depends on it.");
  return '<div class="d-row"><span class="d-label">Cost</span>'
    + '<span class="d-val">'
    + '<span class="cur">' + esc((typeof CUR_SYMBOL !== "undefined") ? CUR_SYMBOL : "") + '</span>'
    + lrEditBox({sku: r.sku, field: "cost", cls: "lr-cost",
                 value: known ? Number(c.cost).toFixed(2) : "",
                 placeholder: "not set", title: tip})
    + (c.source === "manual"
        ? '<span class="lr-src" title="You typed this">•</span>' : "")
    + '</span></div>';
}

function lrPricing(r){
  const m = lrMetrics(r.sku) || {};
  const cur = (typeof CUR_SYMBOL !== "undefined") ? CUR_SYMBOL : "";
  const pnum  = String(r.profit == null ? "" : r.profit).replace(/[^0-9.\-]/g, "");
  const pneg  = pnum !== "" && parseFloat(pnum) < 0;

  return lrPriceBox(r, "Our Price (GBP)", r.price, "The price on the listing")
    + lrFloorCeiling(r)
    + lrCostRow(r)
    + lrDataRow("Profit", pnum ? lrMoney(pnum) : lrVal(null), pneg ? "red" : "green")
    + lrBuyBox(m, cur)
    // BUSINESS PRICE. IT IS NOT A MISSING FEATURE -- IT IS NOT AVAILABLE.
    //
    //     "i am not able to set the business price of the item through the all
    //      listing page screen"
    //
    // MEASURED, against Amazon's own schemas rather than guessed (Rule 4):
    // across all 98 product-type schemas this app has cached for these
    // accounts, there is no business_price attribute, and
    // purchasable_offer.audience has exactly one allowed value -- "ALL". There
    // is no B2B audience to price for, so a box here would collect a number
    // Amazon would refuse.
    //
    // That is an enrolment, not a bug: B2B pricing needs Amazon Business, in
    // Seller Central. This line used to offer a "Set" link that opened the
    // product page, which cannot set one either -- a control that promised
    // something nothing in the app could do.
    + '<div class="bb biz" title="A separate price for Amazon Business buyers. '
    + 'Amazon’s own schema for this account offers no business audience — every '
    + 'product type this app has read allows only the standard one — so there is '
    + 'nowhere to put one. It becomes available once the account is enrolled in '
    + 'Amazon Business in Seller Central.">'
    + '<i class="ti ti-info-circle"></i> Business price: account not enrolled</div>'
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
  // THE ROW ALREADY CARRIES A FEE. listings.amazon_fees and .fee_source are
  // real columns the generator fills; the metrics route returns neither. So the
  // row answers first and the metrics only fill what it cannot -- rather than a
  // column of dashes sitting over a figure the app already had (Rule 12).
  const rowFee = String(r.amazon_fees == null ? "" : r.amazon_fees)
                   .replace(/[^0-9.\-]/g, "");
  const total = rowFee !== "" ? rowFee
              : (m.fees_total != null ? m.fees_total
                 : (m.fees != null ? m.fees : null));
  const rate = (m.fee_rate != null) ? (Number(m.fee_rate) * 100) : null;
  const basis = String(m.fee_basis || r.fee_source || "");
  const word = basis === "actual" ? "from your sales"
             : basis === "quoted" ? "quoted by Amazon"
             : basis ? esc(basis) : "";
  return lrDataRow("Total fees", lrMoney(total))
    + (m.fba_fee != null ? lrDataRow("FBA fee", lrMoney(m.fba_fee))
       : (m.referral_fee != null ? lrDataRow("Referral", lrMoney(m.referral_fee)) : ""))
    + (rate != null
        ? '<div class="fee-basis">' + rate.toFixed(2).replace(/\.00$/, "") + '% '
          + esc(word) + '</div>'
        : "")
    // IT OPENS A PANEL, NOT A PAGE.
    //
    //     "Currently clicking 'Calculate revenue' navigates to the product
    //      detail page. Amazon opens a side drawer."
    //
    // Navigating away is the wrong answer to "what does this one make?" -- you
    // lose the list, the filter and the scroll to read four numbers, then have
    // to find your way back to compare it with the row beneath. The price is
    // passed so the panel opens on the price you were looking at.
    + '<span class="fee-link" onclick="event.stopPropagation();revOpen(\''
    + esc(r.sku) + '\',\'' + esc(String(r.price == null ? "" : r.price)
                                   .replace(/[^0-9.]/g, "")) + '\')"'
    + ' title="What this unit earns at a given price — Amazon’s cut and the '
    + 'stock cost, without leaving the list">Calculate revenue</span>';
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
        // EVERYTHING ELSE LIVES BEHIND THE THREE DOTS.
        //
        //     "There are too many buttons visible on each row -- Image Library,
        //      Image refs, Optimize listing, Variation, etc. Hide ALL of them
        //      under the three-dot menu."
        //
        // rowActions() draws seven buttons in a strip and is shared with the
        // table and the card views, so it is not changed -- those two are not
        // being redesigned (Rule 7). This view simply does not call it. The
        // dots open drawerMore(), the overflow menu that already exists and
        // already holds these actions, so nothing is reimplemented (Rule 12).
    + '<td class="col-actions" onclick="event.stopPropagation()">'
    +   '<i class="ti ti-dots act-dots" title="Everything else"'
    +   ' onclick="drawerMore(event,\'' + esc(r.sku) + '\',' + (r.row || 0) + ','
    +   ((typeof isAmazonLive === "function" && isAmazonLive(r)) ? "true" : "false")
    +   ')"></i></td>'
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
  // The repricer's floors and ceilings, so the Min and Max boxes can show what
  // is set rather than saying they are not loaded on this screen.
  lrLoadRules();
  // A RE-RENDER BUILDS FRESH BOXES FROM SAVED DATA, so anything typed and not
  // yet saved would vanish out of the inputs while the bar went on counting it.
  // Scheduled rather than called: this function returns a STRING, and the boxes
  // do not exist until the caller has put it in the page.
  if(typeof lrEditRestore === "function") setTimeout(lrEditRestore, 0);
  // And, at most once a page load and once every 20 hours, ask Amazon again for
  // the figures only Amazon has. Cheap and silent when nothing is due; see
  // lrAutoRefresh for why it is not lrRefreshMetrics(). It runs AFTER the local
  // read above so the server's own "when did anyone last ask" is known.
  lrAutoRefresh();

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
