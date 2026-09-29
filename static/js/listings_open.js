// static/js/listings_open.js -- opening a listing, the drawer, the row menu and the generate panel. Moved word for word out of listings.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

/* CLICKING A LISTING OPENS IT. Which view that is, is decided here and nowhere
 * else -- the tile image, the tile body, the table row and the Review button
 * all come through this one function, so they can never disagree.
 *
 * The full-screen page is the answer for a click on the listing itself: it is
 * where the editing work happens. The DRAWER IS NOT RETIRED -- it stays the
 * quick look, and everything that opens it directly still does:
 *
 *     the tile menu's "Edit details"        listings.js
 *     the compliance / claim / copy badges  listings.js -- straight to the
 *                                           panel that explains the badge
 *     the run queue re-attaching to a job   runqueue.js
 *     auto-fix and the Miles template       autofix.js, miles_template.js
 *                                           re-rendering an open drawer
 *
 * and the product page carries an expand control back the other way.
 *
 * Falls back to the drawer if pdp.js has not loaded, so a failure to fetch one
 * file cannot make the listings grid unclickable. */
/* CLICKING A LISTING -- ANY LISTING -- OPENS IT. ONE DECISION, ONE PLACE.
 *
 *     "when i click on many listings on live on amazon page inside all
 *      listings page, a message appears the listing is not on this screen, i
 *      should be able to open all the listings"
 *
 * Exactly right, and the cause was that the decision had two homes. The live
 * TILE and the live TABLE row called openLiveListing(), which asks whether this
 * app holds a draft first and sends the ones it does not to the live optimiser.
 * The DETAILED view's row, its warning chip and its product cell called
 * openListing() straight, which went to pdpOpen(), which is built from a row in
 * ROWS and refuses when there is none -- "That listing is not on this screen."
 * So the same listing opened from one view and refused from another.
 *
 * Measured on nestwell_goods: 18 of the 62 SKUs Amazon reports have no row in
 * this app at all -- made in Seller Central, made by another tool, or their
 * draft was deleted. Those are the ones that refused, which is why it was
 * "many listings" and not one.
 *
 * Now openListing() itself asks. Every caller -- and there are eight, across
 * three files -- gets the same answer (CLAUDE.md Rule 12), and there is no
 * route left that can reach pdpOpen with a SKU it cannot draw.
 *
 * `asin` is optional and is only a hint for the optimiser. It is looked up from
 * Amazon's own catalogue when not given, NEVER taken from r.asin: on a row this
 * app generated, r.asin is the COMPETITOR reference embedded in the SKU, and
 * opening the optimiser on a competitor's ASIN would be worse than refusing.
 */
/* EVERY LISTING OPENS THE SAME PAGE.
 *
 *     "Most live listings open the 'Optimize live listing' modal instead of the
 *      PDP overlay. Only listings that were originally created by this app open
 *      the PDP. ... Fix: ALL listings open the PDP overlay regardless of
 *      origin. A listing synced from Amazon is still a listing you manage."
 *
 * The condition was `hasDraftRow(s)`, and it was the right condition for a page
 * that could only be built from a row. It no longer is: pdpOpen draws a listing
 * with no draft from Amazon's own catalogue and attributes -- see
 * pdpCatalogueRow -- so there is nothing left for the branch to protect.
 *
 * Measured: 7 of jack_uk's 47 live SKUs and 18 of nestwell_goods' 62 have no
 * row here, which is why it was "most live listings" and not a few.
 *
 * The Optimize modal is not gone; it is no longer AUTOMATIC. It carries the
 * Custom AI Rewrite, and it stays on the button that says so -- in the product
 * page's own sidebar, and in the row's overflow menu -- where it is a thing you
 * chose rather than a different UI you were given.
 */
function openListing(sku, asin){
  const s = String(sku || "");
  if(!s) return;
  if(typeof pdpOpen === "function"){ pdpOpen(s); return; }
  openDrawer(s);
}

/* This account's OWN ASIN for a SKU, from Amazon's catalogue. "" when the
 * catalogue has not been loaded or does not have it -- the optimiser takes the
 * SKU alone, so an empty ASIN costs nothing and a wrong one would cost a lot. */
function liveAsinFor(sku){
  const s = String(sku || "");
  if(!s || typeof LIVE_ITEMS === "undefined" || !LIVE_ITEMS) return "";
  const hit = LIVE_ITEMS.find(x => String(x && x.sku) === s);
  return (hit && String(hit.asin || "")) || "";
}

/* CLICKING A ROW IN THE LIVE VIEW.
 *
 * A live listing opens the full-screen product page, the same as a draft --
 * asked for directly:
 *
 *     "When I click a LIVE listing row, it should open the same full-screen
 *      PDP overlay that drafts use."
 *
 * WITH ONE FALLBACK THAT IS NOT OPTIONAL. The live view is the account's
 * catalogue as Amazon holds it, and some of those listings have no row in this
 * app at all -- they were made in Seller Central, or by another tool, or their
 * draft was deleted. The product page is built from a row: pdpOpen() looks the
 * SKU up in ROWS and refuses when it is not there. Sending every live click
 * straight to it would leave those listings unopenable, which is worse than
 * what they had.
 *
 * So: a listing this app knows opens the product page; one it does not still
 * opens optimizeLive(), which exists precisely to pull a listing down from
 * Amazon when there is nothing local to show. Nothing is taken away.
 *
 * optimizeLive stays reachable from inside the product page as well -- it is
 * the "Optimize live copy" action in the sidebar -- because the Custom AI
 * Rewrite and Diagnose features live there and are worth keeping.
 */
/* DOES THIS APP HOLD A DRAFT FOR THIS SKU?
 *
 * Amazon's catalogue and this app's listings table are two different sets, and
 * the overlap is not total: MEASURED on nestwell_goods, 18 of the 62 SKUs
 * Amazon reports have no row here at all -- listings made in Seller Central, or
 * by another tool, or whose draft was deleted. `floating_Duck` is one of them.
 *
 * Nothing that EDITS a listing can work on those: /edit finds a row by SKU and
 * correctly refuses when there is none. So every screen that offers an edit has
 * to ask this first, and it is one function because two answers to "is this
 * ours to edit" is how a control comes to be offered where it cannot work
 * (CLAUDE.md Rule 12).
 */
function hasDraftRow(sku){
  const s = String(sku || "");
  if(!s || typeof ROWS === "undefined" || !ROWS) return false;
  return ROWS.some(r => String(r.sku) === s);
}

/* The live view's own name for the same gesture. Kept because it is written
 * into the tile and table markup, and because it has the catalogue's ASIN to
 * hand; it decides nothing of its own any more. */
function openLiveListing(asin, sku){
  openListing(sku, asin);
}

/* Open a listing ON A PARTICULAR TAB.
 *
 * The compliance chip, the claim chip and the "no copy yet" chip all used to
 * open the drawer, where everything was one scrolling column, so landing at the
 * top was the same as landing anywhere. The product page has tabs, and a chip
 * that says "3 documents Amazon can request" should land on the tab that lists
 * them rather than on the title field.
 *
 * The tab is a preference, not a requirement: a listing with no draft goes to
 * the live optimiser, which has no tabs, and that is still the right place. */
function openListingAt(sku, tab){
  openListing(sku);
  if(typeof pdpTab === "function" && typeof PDP_SKU !== "undefined"
     && String(PDP_SKU) === String(sku)){
    pdpTab(tab);
  }
}

/* ONE PRODUCT DETAIL VIEW. THE FULL-PAGE ONE.
 *
 *     "The app has TWO different product detail views that appear in different
 *      contexts ... These are completely different UIs showing the same data.
 *      This is confusing -- the user doesn't know which one will appear when.
 *      Fix: pick ONE."
 *
 * THE REDIRECT IS HERE RATHER THAN AT THE CALL SITES, and that is the whole
 * point. openDrawer is called from eighteen places across five files, and only
 * six of them are a user opening something -- the other twelve are re-render
 * guards shaped `if(DRAWER_SKU === sku) openDrawer(sku)`, which redraw a drawer
 * that is ALREADY open after a schema load, a run finishing, or a mirror
 * arriving. Editing eighteen call sites would mean finding all eighteen and
 * getting all eighteen right; closing the one door they all go through means a
 * nineteenth caller written next month is closed too (CLAUDE.md Rule 12).
 *
 * The guards become harmless on their own: DRAWER_SKU is never set now, so
 * `DRAWER_SKU === sku` is never true and none of them fires.
 *
 * NOTHING IS DELETED. The drawer's builders are shared with the product page --
 * _fullDataParts, dwTitleParts, dwBulletCards and the byte budget are the same
 * code drawing both -- so removing the component would take the page's own
 * contents with it. What is removed is the ROUTE to it.
 *
 * AND THE FALLBACK STAYS A FALLBACK. If pdp.js has not loaded there is no
 * full-page view to send anyone to, and a listing that opens nothing at all is
 * worse than one that opens the old panel. openListing() has always relied on
 * this, so the condition is "is there a product page to use", not "always".
 */
function openDrawer(sku, jumpGen){
  if(typeof pdpOpen === "function"){
    pdpOpen(sku);
    return;
  }
  const r=ROWS.find(x=>String(x.sku)===String(sku));
  if(!r) return;
  // Multi-tab: make sure the workspace's active tab matches THIS card's tab before any
  // edit/approve/push (all of which target the active tab). Without this, editing a card
  // from a non-active tab could hit a duplicate SKU on the wrong tab.
  ensureCardTab(sku);
  DRAWER_SKU=sku;
  const dw=document.getElementById("drawer");
  const body=document.getElementById("drawerbody");
  body.innerHTML=drawerContent(r);
  dw.classList.add("open");
  document.getElementById("drawerscrim").classList.add("open");
  // THE DRAWER ITSELF NO LONGER SCROLLS -- its middle section does, so that the
  // header and the footer can stay put. dwScroller() is the one place that
  // answers "which element scrolls", so this and the jump below cannot drift.
  { const s=dwScroller(); if(s) s.scrollTop=0; }
  // Re-attach to any BACKGROUND Preview/Submit job for this SKU: replays its log into
  // the run panel and resumes polling if still running. This is what makes progress
  // survive navigating away and coming back (and a full page refresh).
  if(typeof rqAttach==="function"){ setTimeout(function(){ if(DRAWER_SKU===sku) rqAttach(sku); }, 60); }
  // If this product type's schema (allowed values + nested sub-fields like ghs /
  // battery) isn't loaded yet, fetch it then re-render -- otherwise required
  // nested fields render as flat boxes (or not at all) and you can't see the
  // dropdowns Amazon needs. This is what made flagged fields invisible.
  if(r.product_type && typeof loadSchemas==="function" && !(SCHEMAS[r.product_type] && (SCHEMAS[r.product_type].attrs||[]).length)){
    loadSchemas([r.product_type], false, rowMkt(r)).then(()=>{
      if(DRAWER_SKU===sku){ body.innerHTML=drawerContent(r); var sv=sid(sku);
        if(typeof rqAttach==="function"){ setTimeout(function(){ if(DRAWER_SKU===sku) rqAttach(sku); }, 60); }
        setTimeout(function(){ if(typeof bulletMeter==='function') bulletMeter(); }, 60); }
    }).catch(()=>{});
  }
  // ASK AMAZON WHAT IT HOLDS FOR THIS SKU, for a listing that is actually on
  // Amazon. One call, cached per SKU for the life of the page, so reopening the
  // same drawer costs nothing; drawer_attributes.js redraws the attribute block
  // itself when the answer lands (and only if this drawer is still open).
  // Deliberately NOT awaited: the drawer is already on screen, and a slow
  // SP-API call must never be what the person is waiting for.
  if(typeof lvEnsure==="function") lvEnsure(r);
  // populate the (always-visible) image panel's model dropdowns + run the
  // connection check, once the drawer is in place
  var sidv=sid(sku);
  setTimeout(function(){ initGenPanel(sidv); if(typeof initMilesPanel==='function') initMilesPanel(sidv); if(typeof bulletMeter==='function') bulletMeter(); }, 120);
  if(jumpGen){ setTimeout(function(){ _dwJumpToGen(sidv); }, 280); }
}

/* SCROLL TO THE IMAGE GENERATOR, OPENING ITS FOLD FIRST.
 *
 * The generator now lives inside a collapsed <details>. A closed details has
 * no laid-out height, so offsetTop reads 0 and the drawer scrolls to the top
 * instead of to the panel -- which looks exactly like the button doing
 * nothing. Open it, then measure.
 *
 * Written once because two callers want it: openDrawer(sku, jumpGen) and
 * openGenPanelInDrawer(). */
function _dwJumpToGen(sidv){
  var anchor=document.getElementById('genimg_'+sidv);
  if(!anchor) return false;
  var fold=anchor.closest('details');
  if(fold && !fold.open) fold.open=true;
  var sc=dwScroller();
  if(sc){
    var top=anchor.getBoundingClientRect().top - sc.getBoundingClientRect().top + sc.scrollTop;
    sc.scrollTo({top: Math.max(0, top - 12), behavior:'smooth'});
  }
  return true;
}
// Shared OpenRouter connection tester: NEVER hangs (12s timeout) and writes a
// clear, specific status into the given diag element so the user knows exactly
// what's wrong (missing key / bad key / discovery / network / app unreachable).
async function _orTestInto(diag){
  if(!diag) return null;
  diag.className='gendiag'; diag.textContent='Checking OpenRouter connection…';
  let t=null;
  try{
    const ctrl=new AbortController();
    const timer=setTimeout(()=>ctrl.abort(), 12000);   // 12s hard cap, no infinite hang
    let resp;
    try{ resp=await fetch('/ai/test',{signal:ctrl.signal}); }
    finally{ clearTimeout(timer); }
    t=await resp.json();
  }catch(e){
    diag.className='gendiag bad';
    diag.textContent = (e&&e.name==='AbortError')
      ? '\u2717 OpenRouter check timed out (12s). Likely a slow or blocked connection to openrouter.ai — check your internet/VPN, then reopen this panel.'
      : '\u2717 Could not reach the app to test OpenRouter (is the app still running?).';
    return null;
  }
  if(t&&t.ok){
    diag.className='gendiag ok';
    diag.textContent='\u2713 OpenRouter ready \u2014 image model: '+(t.image_model||'?')+' ('+(t.image_count||0)+' image models available)';
  } else {
    diag.className='gendiag bad';
    const stage=(t&&t.stage)||'';
    const base='\u2717 '+((t&&t.error)||'OpenRouter not ready');
    const tip = stage==='key'     ? ' \u2014 add your real openrouter_api_key to config.json and restart the app.'
              : stage==='discover'? ' \u2014 the key was found but OpenRouter rejected it or returned no models. Check the key is valid/active at openrouter.ai/keys.'
              :                     ' \u2014 reopen this panel to retry.';
    diag.textContent=base+tip;
  }
  return t;
}
async function initGenPanel(sidv){
  var s=await loadAISettings();
  // If the cached settings have no image models yet (discovery hadn't finished
  // on first page load), force a fresh discovery so the dropdowns populate.
  if(!s || !s.ok || !(s.image_models && s.image_models.length)){
    try{
      AISET=null;
      s=await (await fetch('/ai/settings?refresh=1')).json();
      AISET=s;
    }catch(e){}
  }
  if(s&&s.ok){
    fillModelSelect(document.getElementById('gentai_'+sidv), s.text_models, s.select.prompt_enhance);
    fillModelSelect(document.getElementById('geniai_'+sidv), s.image_models, s.select.image_generate);
  }
  var diag=document.getElementById('gendiag_'+sidv);
  await _orTestInto(diag);
}
function closeDrawer(){
  DRAWER_SKU=null;
  window.RUN_STREAMING=false;
  if(ES){ try{ES.close();}catch(e){} ES=null; }
  // Stop WATCHING any background Preview/Submit job -- but DON'T stop the job itself.
  // It keeps running on the server; reopening the drawer re-attaches to its progress.
  if(typeof rqStopWatch==="function") rqStopWatch();
  document.getElementById("drawer").classList.remove("open");
  document.getElementById("drawerscrim").classList.remove("open");
}
function tileMenu(ev, sku, row, live, ownAsin){
  ev.stopPropagation();
  closeTileMenu();
  // THE ROW'S ACTIONS, NAMED. What used to be a row of icon buttons (see
  // rowActions) is the top of this menu; the conditions are the ones those
  // buttons had. APPROVE IS FOR DRAFTS -- on a live listing there is nothing to
  // approve. OPTIMIZE / COMPARE / ADD VARIANT are for live listings -- nothing
  // to compare a draft against, no live listing to hang a variant off. The
  // live flag comes from the caller, which knows (a catalogue tile has no app
  // row for isAmazonLive() to read).
  if(live === undefined){
    const _r = (typeof ROWS !== "undefined" && ROWS || []).filter(function(x){ return String(x.sku) === String(sku); })[0];
    // Not in ROWS: a catalogue listing, which is live -- never offer Approve on it.
    live = _r ? isAmazonLive(_r) : true;
  }
  const _acts = (live ? "" :
      `<button onclick="closeTileMenu();toast('Approving…');setStatus(${jsArg(sku)},'APPROVED',this)" title="Mark this draft ready to send to Amazon"><i class="ti ti-check"></i> Approve</button>`)
    + `<button onclick="closeTileMenu();openStudioSingle(${jsArg(sku)})" title="Creative ideas, prompt and image AI"><i class="ti ti-photo"></i> Image Studio</button>`
    + `<button onclick="closeTileMenu();openImageLibrary(${jsArg(sku)}, ${live ? "true" : "false"})" title="Upload your own, pick one from the library, or set the main image"><i class="ti ti-library-photo"></i> Images</button>`
    + (live
        ? `<button onclick="closeTileMenu();optimizeLive(${jsArg(ownAsin||'')},${jsArg(sku)})" title="Pull the live copy from Amazon so you can rewrite and push it"><i class="ti ti-sparkles"></i> Optimize copy</button>`
        + `<button onclick="closeTileMenu();syncForSku(${jsArg(sku)})" title="Compare with Amazon's live copy, field by field"><i class="ti ti-arrows-exchange"></i> Compare with Amazon</button>`
        + `<button onclick="closeTileMenu();addVariant(${jsArg(sku)})" title="Add another colour or size of this product, from an eBay link"><i class="ti ti-binary-tree"></i> Add variant</button>`
        : "")
    + `<div class="tmsep"></div>`;
  const m=document.createElement("div"); m.className="tilemenu"; m.id="tilemenu";
  m.innerHTML=_acts + `
    <button onclick="setStatus(${jsArg(sku)},'NEEDS_REVIEW',this);closeTileMenu()"><i class="ti ti-player-pause"></i> Hold</button>
    <button onclick="askAbout(${jsArg(sku)});closeTileMenu()"><i class="ti ti-message-circle"></i> Ask Claude</button>
    <button onclick="openListing(${jsArg(sku)});closeTileMenu()"><i class="ti ti-edit"></i> Edit details</button>
    <button class="danger" onclick="delRow(${jsArg(sku)},${row},this);closeTileMenu()"><i class="ti ti-trash"></i> Delete</button>`;
  document.body.appendChild(m);
  const _op=ev.target.closest("button");
  const rect=_op.getBoundingClientRect();
  m.style.top=(rect.bottom+4)+"px";
  m.style.left=Math.max(8, Math.min(rect.left, window.innerWidth-m.offsetWidth-8))+"px";
  // Opens UPWARDS when there is no room below (the last rows of the table).
  if(rect.bottom + 4 + m.offsetHeight > window.innerHeight - 8)
    m.style.top=Math.max(8, rect.top - 4 - m.offsetHeight)+"px";
  if(typeof uiMenuKeys==="function") uiMenuKeys(m, _op, closeTileMenu);
  setTimeout(()=>document.addEventListener("click",closeTileMenu,{once:true}),0);
}
function closeTileMenu(){ const m=document.getElementById("tilemenu"); if(m) m.remove(); }

/* THE DRAWER'S OVERFLOW: everything that was demoted off the action bar.
 *
 * Same .tilemenu component the card already uses, so this is one menu style in
 * the app rather than a second one invented for the drawer.
 *
 * None of these was deleted. Each failed the "does something else already do
 * this?" test as a FRONT-ROW control, not as a capability:
 *
 *   Refresh dropdowns   openDrawer fetches a missing schema by itself. This is
 *                       for the rarer case where Amazon CHANGED the type, and it
 *                       is the only way to clear a stale one.
 *   Pull live images    Sync does the whole account; this does one row.
 *   Push image to live  the Image Library does this, and shows you what you are
 *   Upload main image   pushing first.
 *   Delete              destructive, and it sat between Ask Claude and the edge.
 */
/* The Miles template panel in a dialog, for the ⋯ menu. The same panel and the
 * same start-up the drawer gives it (milesTemplatePanel / initMilesPanel), so
 * nothing about how it works changed -- only where it opens. */
async function openMilesTemplate(sku){
  if(typeof milesTemplatePanel !== "function") return;
  const sidv = sid(sku);
  const done = _dlgOpen({title: "Miles template — " + sku,
                         html: milesTemplatePanel(sku, sidv),
                         buttons: [{label: "Close", value: true, primary: true}],
                         cancelValue: null});
  setTimeout(function(){
    if(typeof initMilesPanel === "function"){ try{ initMilesPanel(sidv); }catch(e){} }
  }, 60);
  await done;
}

function drawerMore(ev, sku, row, isLive){
  ev.stopPropagation();
  closeTileMenu();
  // WHERE THE MENU IS ANCHORED, WORKED OUT BEFORE ANYTHING IS BUILT.
  //
  //     "The three-dot button at the end of each listing row does nothing when
  //      clicked."
  //
  // It threw. This read `ev.target.closest("button")` and then that element's
  // rectangle -- and in the detailed row the dots are an <i>, not a <button>,
  // so closest() returned null and the next line was a TypeError on null. The
  // menu had already been appended by then, so what actually happened was worse
  // than nothing: a position:fixed menu with no top or left, parked at its
  // static position below the page, and the click-away listener never installed
  // because the throw came first.
  //
  // currentTarget is the element the handler is ON, whatever kind of element
  // that is, so this works for the drawer's button and the row's icon alike --
  // one menu, not a second one for rows that are not buttons (Rule 12). The
  // rect is taken FIRST so a failure to find an anchor cannot leave a menu
  // stranded in the DOM.
  const anchor = ev.currentTarget
              || (ev.target && ev.target.closest && ev.target.closest("button"))
              || ev.target;
  if(!anchor || !anchor.getBoundingClientRect) return;
  const rect = anchor.getBoundingClientRect();

  // OUR ASIN, NEVER THE COMPETITOR'S. A SKU is price_days_ASIN and that ASIN is
  // the product this listing was researched FROM (CLAUDE.md Rule 1). rowAsin is
  // the one place that tells the two apart, so "View on Amazon" cannot end up
  // opening somebody else's listing.
  const _r = (typeof ROWS !== "undefined")
    ? ROWS.find(x => String(x.sku) === String(sku)) : null;
  const _a = (_r && typeof rowAsin === "function") ? (rowAsin(_r) || {}) : {};
  const ourAsin = _a.own || "";
  // OPENED FROM THE PRODUCT PAGE THAT "EDIT LISTING" WOULD OPEN, it does nothing
  // but redraw the page you are on -- so it is left out there. From a list row
  // or the drawer it is still the first item, and still the way in.
  const onItsOwnPage = (typeof PDP_SKU !== "undefined")
                    && String(PDP_SKU || "") === String(sku);

  const m = document.createElement("div");
  m.className = "tilemenu"; m.id = "tilemenu";
  m.innerHTML =
    // THE FIRST THING THE MENU OFFERS IS THE THING IT IS FOR. Asked for by name
    // -- "Edit listing, View on Amazon, Delete, Duplicate, Copy ASIN" -- and
    // three of those already existed somewhere; these are the ways to them.
    //
    // NO "DUPLICATE". Nothing in this app copies a listing: there is no
    // function, no route and no SKU-minting path that takes an existing row.
    // A menu item that opened a listing you did not ask for, or silently did
    // nothing, would be worse than its absence (Rule 4).
    (onItsOwnPage ? ""
      : `<button onclick="closeTileMenu();openListing(${jsArg(sku)})" title="Open this listing to edit it"><i class="ti ti-edit"></i> Edit listing</button>`)
    + (ourAsin
        ? `<button onclick="closeTileMenu();window.open(${jsArg(_dpUrl(ourAsin))},'_blank','noopener')" title="Open ${esc(ourAsin)} on Amazon in a new tab"><i class="ti ti-external-link"></i> View on Amazon</button>`
          + `<button onclick="uiCopy(${jsArg(ourAsin)},'ASIN copied');closeTileMenu()" title="Copy ${esc(ourAsin)} to the clipboard"><i class="ti ti-copy"></i> Copy ASIN</button>`
        // NOT LIVE YET MEANS NO ASIN OF ITS OWN, and that is a fact worth
        // saying rather than two items quietly missing from the menu.
        : `<button disabled title="This listing is not on Amazon yet, so it has no ASIN of its own. The ASIN in the SKU is the competitor product it was researched from."><i class="ti ti-external-link"></i> No ASIN yet</button>`)
    + `<button onclick="refreshSchemaFor(${jsArg(sku)});closeTileMenu()" title="Re-fetch Amazon's allowed values for this product type. Use it when a dropdown is missing an option you know exists — it does NOT touch your listing's own data."><i class="ti ti-refresh"></i> Refresh dropdown options</button>`
    + `<button onclick="openImageLibrary(${jsArg(sku)}, ${isLive ? "true" : "false"});closeTileMenu()" title="Every image this listing has: upload your own, pick the main one, push one live"><i class="ti ti-library-photo"></i> Image library</button>`
    + (isLive
        ? `<button onclick="pullLiveRow(${jsArg(sku)},this);closeTileMenu()" title="Fetch this listing's real images from Amazon and replace the generation-time ones. Sync does this for every listing at once."><i class="ti ti-cloud-download"></i> Pull live images</button>`
        + `<button onclick="pushImageLive(${jsArg(sku)},this);closeTileMenu()" title="Send the current main image to the live Amazon listing — the image only, no resubmit"><i class="ti ti-cloud-upload"></i> Push main image live</button>`
        : "")
    // THE MILES TEMPLATE, moved off the product page's Safety & Compliance tab
    // on the owner's redesign (niche, rarely used). Only where the workspace
    // has the harvest feature -- the same gate the fold had.
    + ((window.WS_FEATURES && window.WS_FEATURES.indexOf("harvest") >= 0
        && typeof milesTemplatePanel === "function")
        ? `<button onclick="closeTileMenu();openMilesTemplate(${jsArg(sku)})" title="The Miles Lubricants template for this listing"><i class="ti ti-template"></i> Miles template</button>`
        : "")
    + `<button class="danger" onclick="delRow(${jsArg(sku)},${row||0},this);closeTileMenu()"><i class="ti ti-trash"></i> Delete listing</button>`;
  document.body.appendChild(m);
  m.style.top = (rect.bottom + 4) + "px";
  // RIGHT-ALIGNED TO THE BUTTON. The drawer is pinned to the right edge, so a
  // menu laid out leftwards from here would open off the screen.
  m.style.left = Math.max(8, Math.min(rect.right - 232,
                                      window.innerWidth - 240)) + "px";
  if(typeof uiMenuKeys === "function") uiMenuKeys(m, ev.currentTarget, closeTileMenu);
  setTimeout(() => document.addEventListener("click", closeTileMenu, {once: true}), 0);
}
function openGenPanelInDrawer(sku){
  try{
    var sidv=sid(sku);
    if(!_dwJumpToGen(sidv)){ toast("Image panel not found \u2014 try reopening the drawer"); return; }
    initGenPanel(sidv);
  }catch(e){ toast("Could not open image panel: "+e); }
}
function openGenFromHead(sku){ openStudioSingle(sku); }

function _fileToDataURL(file){
  return new Promise(function(res,rej){
    var fr=new FileReader(); fr.onload=function(){res(fr.result);}; fr.onerror=rej; fr.readAsDataURL(file);
  });
}
async function uploadRef(input, sku, sidv){
  var file=input.files&&input.files[0]; if(!file) return;
  var st=document.getElementById('genstatus_'+sidv); if(st) st.textContent='Uploading reference…';
  try{
    var dataUrl=await _fileToDataURL(file);
    var res=await fetch('/media/upload',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:sku,data:dataUrl,name:file.name,kind:'ref'})});
    var j=await res.json();
    if(!j.ok){ if(st) st.textContent='Upload failed: '+(j.error||''); return; }
    var fld=document.getElementById('genraw_'+sidv); if(fld) fld.value=j.url;
    if(st) st.innerHTML='<span style="color:var(--ok)">\u2713 Reference uploaded \u2014 saved to this SKU\u2019s media folder.</span>';
  }catch(e){ if(st) st.textContent='Upload error: '+e; }
}
