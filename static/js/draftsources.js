/* static/js/draftsources.js -- a draft's suppliers, on the drafts page.
 *
 *     "on draft the sources should stay on the drafts page but should display
 *      the handling time, the carrier info and delivery time and source price
 *      and source name etc same as repricer shows it, in the same format"
 *
 * IT DRAWS NOTHING OF ITS OWN. _ordSourcesHtml (static/js/orders.js) is the one
 * renderer the order panel and the repricer both use, and this hands it the same
 * block shape from the same server function. "The same format" is therefore not
 * a layout copied to look alike -- which would drift the first time either was
 * touched -- it is the same code drawing the same data (CLAUDE.md Rule 12).
 *
 * THE SUPPLIERS ARE NOT BEING TRACKED YET, and the panel says so. They are
 * attached to a draft: the repricer does not price them and no order can show
 * them, because both ask for stage=live. When Amazon confirms the listing
 * BUYABLE, source_repo.promote_to_live flips these same rows -- with every
 * price check already taken -- and they appear on those screens instead.
 *
 * NOTHING HERE ASKS EBAY. The route reads the last stored check, so each line
 * carries its own checked_at and the panel can say how old it is instead of
 * implying it is live.
 */

const DRAFT_SRC = {};        // sku -> {state, options, summary, note, error}

function dsGet(sku){ return DRAFT_SRC[String(sku || "")] || null; }

/* Ask once per SKU, including for a past failure -- a listing with no suppliers
 * must not re-ask on every re-render of the row it sits in. */
function dsEnsure(r){
  if(!r || !r.sku) return;
  const sku = String(r.sku);
  if(DRAFT_SRC[sku]) return;
  DRAFT_SRC[sku] = {state: "loading", options: [], summary: {}, note: ""};
  let url = "/listing/sources?sku=" + encodeURIComponent(sku);
  const mkt = (typeof rowMkt === "function") ? rowMkt(r) : "";
  if(mkt) url += "&mkt=" + encodeURIComponent(mkt);
  // THE PRICE THIS DRAFT IS GOING TO BE LISTED AT, so the profit column answers
  // about the price on screen rather than about nothing. Without it the
  // suppliers still list and only profit/margin/ROI are absent, which
  // options_for already leaves as null rather than printing a zero.
  const px = String(r.price == null ? "" : r.price).replace(/[^0-9.]/g, "");
  if(px) url += "&price=" + encodeURIComponent(px);
  // A LISTING THAT HAS JUST GONE LIVE is mid-flip: its stage may already be
  // live while the row on screen still says otherwise. Asking for `all` there
  // means the panel never blanks during the gap.
  const live = (typeof isAmazonLive === "function") ? isAmazonLive(r) : false;
  if(live) url += "&stage=all";

  fetch((typeof acctUrl === "function") ? acctUrl(url) : url)
    .then(res => res.json())
    .then(j => {
      DRAFT_SRC[sku] = (j && j.ok)
        ? {state: "ok", options: j.options || [], summary: j.summary || {},
           note: j.note || "", tracked: !!j.tracked}
        : {state: "error", options: [], summary: {}, note: "",
           error: (j && j.error) || "could not read the suppliers"};
    })
    .catch(e => {
      DRAFT_SRC[sku] = {state: "error", options: [], summary: {}, note: "",
                        error: String((e && e.message) || e)};
    })
    .then(() => {
      // Only redraw if this SKU is still the one on screen, in either view.
      const onDrawer = (typeof DRAWER_SKU !== "undefined") && String(DRAWER_SKU) === sku;
      const onPdp    = (typeof PDP_SKU !== "undefined") && String(PDP_SKU) === sku;
      if(onDrawer && typeof _rebuildDrawerData === "function") _rebuildDrawerData(sku);
      else if(onPdp && typeof pdpRebuild === "function") pdpRebuild(sku);
    });
}

/* Throw the cached answer away and ask again. */
function dsRefresh(sku){
  sku = String(sku);
  delete DRAFT_SRC[sku];
  const r = (typeof ROWS !== "undefined" && ROWS.find)
    ? ROWS.find(x => String(x.sku) === sku) : null;
  if(!r) return;
  dsEnsure(r);
  if(typeof _rebuildDrawerData === "function") _rebuildDrawerData(sku);
}

/* The panel. "" when there is nothing worth a heading. */
function draftSourcesHtml(r){
  if(!r || !r.sku) return "";
  const sku = String(r.sku);
  const D = dsGet(sku);
  if(!D){ dsEnsure(r); return _dsShell(sku, '<div class="ds-wait">Reading the suppliers…</div>'); }
  if(D.state === "loading")
    return _dsShell(sku, '<div class="ds-wait">Reading the suppliers…</div>');
  if(D.state === "error")
    return _dsShell(sku, '<div class="ds-err">Could not read the suppliers: '
      + _dsEsc(D.error || "") + '</div>');
  if(!(D.options || []).length){
    // NOT AN ERROR AND NOT A GAP TO FILL IN SILENCE. A draft generated from one
    // link has one supplier; a draft generated before supplier columns existed
    // has none. Both are ordinary, and saying so beats an empty box.
    return _dsShell(sku,
      '<div class="ds-none">No suppliers are recorded for this listing yet. '
      + 'Add a Source URL, Supplier 2 or Supplier 3 to its row and generate '
      + 'again, and they will be listed here.</div>');
  }
  const body = (typeof _ordSourcesHtml === "function")
    ? _ordSourcesHtml({options: D.options, summary: D.summary}, "")
    : '<div class="ds-err">The supplier renderer is not loaded.</div>';
  const note = D.note
    ? '<div class="ds-note"><i class="ti ti-info-circle"></i> ' + _dsEsc(D.note) + '</div>'
    : "";
  return _dsShell(sku, note + body);
}

function _dsShell(sku, inner){
  return '<div class="ds-wrap"><div class="ds-head">'
    + '<b>Suppliers</b>'
    + '<button class="ds-refresh" onclick="dsRefresh(' + _dsArg(sku) + ')">refresh</button>'
    + '</div>' + inner + '</div>';
}

function _dsEsc(s){
  return (typeof esc === "function") ? esc(s)
    : String(s == null ? "" : s).replace(/[&<>"]/g,
        c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
}
function _dsArg(s){ return "'" + String(s || "").replace(/'/g, "\\'") + "'"; }
