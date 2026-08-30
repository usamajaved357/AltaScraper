/* static/js/pdp.js -- the full-screen product detail page.
 *
 * The drawer is a 520px column beside the grid. Real editing work -- reading a
 * description while checking the bullets, filling twenty attributes, comparing
 * against what Amazon holds -- is cramped in it. This is the same listing with
 * room: copy on the left, context on the right, attributes full width below.
 *
 * IT BUILDS ALMOST NOTHING. Every block on this page is the block the drawer
 * already draws, arranged differently:
 *
 *     _fullDataParts(r)   images, bullets, description, search terms,
 *                         highlights, identity, attributes, the folds
 *     dwTitleParts(r)     the title editor, its counter, its 27 Jul 2026 cap
 *     _dwWarnings(r)      the warnings card, severity-coloured
 *
 * That is deliberate and it is the whole design (CLAUDE.md Rule 12). Those
 * blocks carry behaviour that is invisible until it is missing: the shared byte
 * budget across five bullets, the 249-byte search-terms cliff that de-indexes a
 * listing silently, the required stars, the nested sub-field boxes, the
 * live-vs-Amazon tags, and one save path through saveEdit. A second set of
 * editors here would drift from those, and the drift would only show up when
 * this page let something through that the drawer stopped.
 *
 * THE LISTINGS GRID IS NEVER TORN DOWN. This is an overlay above it, not a
 * section swap, which is what makes "back preserves filters and scroll" true by
 * construction rather than by remembering to save and restore them. Nothing is
 * re-fetched and nothing is re-rendered when you come back.
 */

let PDP_SKU = "";
/* Where the grid was when you left it. The grid keeps its DOM -- it is hidden,
 * not emptied -- so its filters, its Drafts/Live/All switch and every expanded
 * row survive on their own. Scroll does NOT: hiding the element collapses the
 * page's height and the browser clamps scrollTop to zero. The sidebar is
 * position:sticky and the WINDOW is what scrolls (dashboard.css:331), so this
 * is the one number that has to be carried by hand. */
let PDP_BACK_SCROLL = 0;

function pdpRow(){
  if(!PDP_SKU || typeof ROWS === "undefined") return null;
  return ROWS.find(x => String(x.sku) === String(PDP_SKU)) || null;
}

function pdpIsOpen(){ return !!PDP_SKU; }

/* ---- open / close ------------------------------------------------------ */

function pdpOpen(sku){
  sku = String(sku || "");
  const r = (typeof ROWS !== "undefined") ? ROWS.find(x => String(x.sku) === sku) : null;
  if(!r){ if(typeof toast === "function") toast("That listing is not on this screen."); return; }
  if(!PDP_SKU){                                  // entering from the grid, not
    try{ PDP_BACK_SCROLL = window.scrollY || 0; }catch(e){ PDP_BACK_SCROLL = 0; }
  }                                              // moving between listings
  PDP_SKU = sku;
  // The drawer and this page are two views of one listing; having both open
  // means two title boxes saving to the same cell.
  if(typeof closeDrawer === "function"){ try{ closeDrawer(); }catch(e){} }

  const host = document.getElementById("pdp");
  if(host){ host.style.display = "block"; }
  document.body.classList.add("pdp-on");
  pdpRender();
  try{ window.scrollTo(0, 0); }catch(e){}

  // The product type's schema drives the attribute dropdowns and the nested
  // sub-field boxes. openDrawer fetches it on demand for exactly this reason;
  // without it the fields render as flat text boxes with no allowed values.
  if(r.product_type && typeof loadSchemas === "function"
     && !(SCHEMAS[r.product_type] && (SCHEMAS[r.product_type].attrs||[]).length)){
    loadSchemas([r.product_type], false, (typeof rowMkt==="function")?rowMkt(r):"")
      .then(() => { if(PDP_SKU === sku) pdpRender(); }).catch(() => {});
  }
  // What Amazon currently holds, for the live/differs/only tags.
  if(typeof lvEnsure === "function") lvEnsure(r);

  if(typeof altaSyncUrl === "function") altaSyncUrl();
}

/* Back to the grid. The grid was never unmounted, so its filters, its source
 * switch and its scroll position are all still exactly where they were. */
function pdpClose(){
  if(!PDP_SKU) return;
  PDP_SKU = "";
  const host = document.getElementById("pdp");
  if(host){ host.style.display = "none"; host.innerHTML = ""; }
  document.body.classList.remove("pdp-on");
  if(typeof altaSyncUrl === "function") altaSyncUrl();
  // After the grid is visible again, not before -- scrolling a hidden element
  // sets nothing.
  try{ window.scrollTo(0, PDP_BACK_SCROLL || 0); }catch(e){}
}

/* ---- render ------------------------------------------------------------ */

/* The status word, in the four-status vocabulary liststatus.js owns. Colours
 * follow the mockup: QUEUED grey, GENERATED blue, SUBMITTED amber, LIVE green.
 * The WORD comes from lsStatusOf so this page can never disagree with the card
 * and the table about what a listing's status is. */
function pdpStatusBadge(r){
  const st = (typeof lsStatusOf === "function") ? lsStatusOf(r)
                                                : String(r.status||"").toUpperCase();
  const cls = st === "LIVE" ? "live" : st === "SUBMITTED" ? "sent"
            : st === "GENERATED" ? "gen" : st === "QUEUED" ? "queued" : "other";
  return '<span class="pdp-badge ' + cls + '">' + esc(st || "—") + '</span>';
}

function pdpRender(){
  const host = document.getElementById("pdp");
  const r = pdpRow();
  if(!host) return;
  if(!r){ pdpClose(); return; }

  const sku = String(r.sku);
  const ro  = !!window.WS_READONLY;
  // NEVER LET A RENDER ERROR COLLAPSE THE PAGE INTO NOTHING. fullData() has
  // guarded the drawer this way since a thrown builder turned it into empty
  // boxes with no clue why; this page is built from the same builders, so it
  // can fail the same way. Show what broke and the raw row, so the listing is
  // still readable and the fault is fixable rather than guessed at.
  let tp, p;
  try{
    tp = dwTitleParts(r, "pdptitlec_" + sid(sku));
    p  = _fullDataParts(r);
  }catch(err){
    host.innerHTML = '<div class="pdp"><div class="pdp-top"><div class="pdp-topl">'
      + '<button class="pdp-back" onclick="pdpClose()">'
      + '<i class="ti ti-arrow-left"></i> Back to listings</button>'
      + '<span class="pdp-sku">' + esc(sku) + '</span></div></div>'
      + '<div class="pdp-card" style="border-color:#6b2222;background:#2a1212">'
      + '<b style="color:#F09595">This listing’s page hit an error while rendering.</b>'
      + '<div style="font-size:12px;color:#ffb3b3;margin-top:6px">'
      + esc(String((err && err.message) || err)) + '</div>'
      + '<div style="font-size:11px;color:#c98;margin-top:8px">The drawer may still '
      + 'open it — and the raw data is below either way.</div>'
      + '<pre class="raw" style="display:block;margin-top:8px">'
      + esc(JSON.stringify(r, null, 2)) + '</pre></div></div>';
    return;
  }
  const asin = (typeof rowAsin === "function") ? (rowAsin(r)||{}) : {};
  const shownAsin = asin.own || asin.source || r.asin || "";

  const top = '<div class="pdp-top">'
    + '<div class="pdp-topl">'
    +   '<button class="pdp-back" onclick="pdpClose()">'
    +     '<i class="ti ti-arrow-left"></i> Back to listings</button>'
    +   pdpStatusBadge(r)
    +   (shownAsin ? '<span class="pdp-asin">' + esc(shownAsin) + '</span>' : "")
    +   '<span class="pdp-sku">' + esc(sku) + '</span>'
    + '</div>'
    + '<div class="pdp-topr">'
    // THE SAME THREE ACTIONS THE DRAWER'S FOOTER RUNS, calling the same
    // functions. Preview and Auto-fix and Submit are not reimplemented here.
    +   '<button onclick="previewOne(\'' + esc(sku) + '\')" title="Check this listing against Amazon. Nothing is sent."><i class="ti ti-eye"></i> Preview</button>'
    +   '<button onclick="autoFixLoop(\'' + esc(sku) + '\')" title="Suggest, apply, preview — repeatedly, until there are no errors left or it stops making progress (max 8 rounds)."><i class="ti ti-wand"></i> Auto-fix</button>'
    +   (ro
        ? '<span class="pdp-ro"><i class="ti ti-lock"></i> Read-only workspace</span>'
        : '<button class="primary" onclick="submitOne(\'' + esc(sku) + '\')" title="Publish ONLY this listing live"><i class="ti ti-upload"></i> Submit</button>')
    + '</div></div>';

  // LEFT -- the copy. Title, images and bullets share one card, as the mockup
  // draws them; the inner sections keep their own headers as sub-labels and
  // their card chrome is dropped by .pdp-group in the stylesheet.
  const left = '<div class="pdp-col left">'
    + '<div class="pdp-card pdp-group">'
    +   '<div class="pdp-cardhead">Listing content'
    +     '<span class="pdp-cardright">' + tp.count + tp.indexTag + '</span></div>'
    +   tp.editor + tp.warnNote
    +   p.images + p.bullets + p.highlights
    + '</div>'
    + p.desc
    + p.search
    + '</div>';

  // RIGHT -- the context. Warnings first and loudest, as the mockup has it.
  const right = '<div class="pdp-col right">'
    + ((typeof _dwWarnings === "function") ? _dwWarnings(r) : "")
    + p.identity
    + '<div class="pdp-card pdp-group">'
    +   '<div class="pdp-cardhead">Compliance and checks</div>'
    +   p.folds
    + '</div>'
    + '</div>';

  host.innerHTML = '<div class="pdp">' + top
    + '<div class="pdp-cols">' + left + right + '</div>'
    + '<div class="pdp-wide" id="pdpattrs_' + sid(sku) + '">' + p.attrs + '</div>'
    + '</div>';

  // The bullets' shared byte budget is measured from the DOM once the cards
  // exist -- the same call openDrawer makes, for the same reason.
  setTimeout(function(){ if(typeof bulletMeter === "function") bulletMeter(); }, 40);
}

/* Redraw after a structural edit (a field deleted, an optional one added, a
 * live value copied in). Mirrors _rebuildDrawerData; called from it, so there
 * is one place that decides a listing view is stale. */
function pdpRebuild(sku){
  if(PDP_SKU && String(PDP_SKU) === String(sku)) pdpRender();
}

/* ---- the address ------------------------------------------------------- */

/* /w/<workspace>/listing/<sku>. Built here rather than in shell.js because the
 * workspace half of it is altaPathFor's business and the sku half is this
 * page's. Returns "" when there is no address to give. */
function pdpPath(){
  if(!PDP_SKU) return "";
  if(typeof ACTIVE_WS === "undefined" || !ACTIVE_WS || ACTIVE_WS.brand === "new") return "";
  const slug = String(ACTIVE_WS.key || "") || "default";
  return "/w/" + encodeURIComponent(slug) + "/listing/" + encodeURIComponent(PDP_SKU);
}

/* Reopen from an address. Called by the router once the workspace is open and
 * ROWS have been loaded; returns false when the SKU is not on this screen, so
 * the router can say so instead of showing an empty page. */
function pdpOpenFromUrl(sku){
  sku = String(sku || "");
  if(!sku) return false;
  const r = (typeof ROWS !== "undefined") ? ROWS.find(x => String(x.sku) === sku) : null;
  if(!r) return false;
  pdpOpen(sku);
  return true;
}
