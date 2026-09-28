// static/js/listings_search.js -- search, filters and matching rows to the live catalogue. Moved word for word out of listings.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

// esc: moved to static/js/core_util.js (Milestone 4), loaded just before this file.

// _noneless: moved to static/js/core_util.js (Milestone 4), loaded just before this file.
// _TOAST_ERR + toast: moved to static/js/core_util.js (Milestone 4), loaded just before this file.

// badgeClass: moved to static/js/core_util.js (Milestone 4), loaded just before this file.
// isRefusedByAmazon, isBlockedByOurChecks, isHold: moved to static/js/core_util.js (Milestone 4), loaded just before this file.

// GONE: the sheet-tab filter. A spreadsheet had tabs and this let you look at
// one of them; the app's own database does not, and there is nothing left for
// this to filter. Reported twice -- "why do i still see tabs in the listings
// page when i am not using any sheets", then "i still see tabs displayed at the
// header of the screen in listings".
//
// It was already hidden whenever fewer than two tabs came back, which is why it
// did not show on a clean account -- but any row still carrying a tab_gid from
// the spreadsheet era brought the whole strip back. Hidden-unless is not gone.
function tabPass(r){ return true; }             // kept: still called from a card path
// FIND ONE LISTING BY WHAT IS PRINTED ON IT.
//
//     "let me search the listing using the sku, asin, or a ean used in it in
//      the app"
//
// There was a status filter and no way to find a single product at all. On an
// account with 85 listings the only way to reach one was to scroll, and the
// three things you actually have in your hand when you go looking are its SKU
// (off a label), its ASIN (off Seller Central) or its barcode (off the box).
//
// The SKU carries the competitor ASIN inside it (price_days_ASIN), so searching
// an ASIN finds both the listing whose own ASIN it is AND any listing built
// from it as a reference. That is a feature, not a collision: they are both
// answers to "show me the thing to do with B0XXXXXXXX".
let SEARCH_Q = "";

function _sq(v){ return String(v == null ? "" : v).toLowerCase(); }

function matchesSearch(r){
  const q = SEARCH_Q.trim().toLowerCase();
  if(!q) return true;
  // Digits only for the barcode, so "5060 5415 10005" off a box finds the
  // listing that stores it as 5060541510005.
  const qDigits = q.replace(/\D/g, "");
  // OUR OWN ASIN, WHICH IS NOT IN THE ROW.
  //
  //     "searching for ASIN B0HHSBPW8H returns 0 matches but the listing
  //      exists on Amazon and was submitted through this app"
  //
  // It did, and the row for it was there the whole time. A draft row's `asin`
  // is the COMPETITOR reference out of its SKU (13.02_3Days_B0D25XZLMJ); the
  // ASIN Amazon gave the listing when it published -- B0HHSBPW8H, the one
  // printed in Seller Central and the only one the owner has in hand -- lives
  // in the live catalogue, keyed by SKU. So the one identifier you actually go
  // looking with was the one field the search could not see.
  //
  // ownLiveAsin() is the existing lookup for exactly this and is asked here so
  // there is one answer to "which ASIN is ours" (Rule 12).
  const own = (typeof ownLiveAsin === "function") ? ownLiveAsin(r) : "";
  // `barcode` and `ean` are what a LIVE CATALOGUE item calls its identifiers;
  // `upc` is what an app row calls its. Both shapes go through this one
  // predicate now, so the Live view and the Drafts view cannot disagree about
  // what counts as a match.
  // ORDER IS PRESENTATION ONLY -- every field below is tried, so this is a
  // list and not a precedence. It is written with `r.asin, r.competitor_asin`
  // and `r.upc, r.title` adjacent because test_listings_asin.py and
  // test_bookmarks_and_search.js read those two pairs out of this source to
  // prove the source ASIN and the title are still searched. Splitting the pairs
  // up broke both tests while changing no behaviour at all, which is a bad
  // trade: the pairs cost nothing to keep and the tests are how anyone later
  // finds out they dropped a field.
  const fields = [r.sku, r.asin, r.competitor_asin, own,
                  r.upc, r.title, r.ean, r.barcode, r.brand,
                  r.model_number, r.source_url];
  for(const f of fields){
    if(!f) continue;
    const s = _sq(f);
    if(s.indexOf(q) >= 0) return true;
    if(qDigits.length >= 6 && s.replace(/\D/g, "").indexOf(qDigits) >= 0) return true;
  }
  // EVERY WORD SOMEWHERE, IN ANY ORDER.
  //
  // The title search above is a strict substring, so it finds a product only
  // if you type the words in the order Amazon happens to have them in. "garden
  // hose 50ft" finds the hose; "50ft garden hose" finds nothing, and there is
  // no way to tell from the outside which one you guessed.
  //
  // Nobody remembers a title word for word. They remember two or three words
  // about the thing. So a multi-word search matches when EVERY word appears
  // somewhere in the listing -- which is strict enough that two words still
  // narrow 85 listings to one or two, and forgiving enough that the order does
  // not have to be right.
  //
  // Single words are left to the substring pass above, deliberately: it
  // already matches inside a word ("fol" finds Folding and Foldable), and this
  // pass would not add anything.
  //
  // THE RULE ITSELF NOW LIVES IN static/js/textsearch.js and the campaigns
  // search asks the same function (CLAUDE.md Rule 12). It was written out here
  // and nowhere else, so when the Campaign Analytics box needed it the choice
  // was a second copy or one shared answer -- and two ideas of what searching
  // means is exactly how one screen quietly stops finding what the other does.
  //
  // The FIELD LIST above stays here, where it belongs and where
  // test_listings_asin.py and test_bookmarks_and_search.js read it from.
  if(typeof altaSearchMatch === "function"){
    if(altaSearchMatch(q, fields)) return true;
  }else{
    const words = q.split(/\s+/).filter(w => w.length > 1);
    if(words.length > 1){
      const hay = fields.map(_sq).join(" ");
      if(words.every(w => hay.indexOf(w) >= 0)) return true;
    }
  }
  // The attributes blob, so an EAN stored only inside the payload is still
  // findable -- that is where a barcode ends up once a listing is built.
  if(qDigits.length >= 6){
    try{
      const blob = String(r.attributes_json || r["Attributes JSON"] || "");
      if(blob && blob.replace(/\D/g, "").indexOf(qDigits) >= 0) return true;
    }catch(e){}
  }
  return false;
}

function setSearch(v){
  SEARCH_Q = v || "";
  render();
}

/* WHAT A LIVE TILE MEANS, in one place.
 *
 * Read by the tile that COUNTS them and by the filter that HIDES the rest, so
 * a tile saying 9 cannot then show 40. Takes an item from the Amazon catalogue
 * (LIVE_ITEMS), which is where status, quantity and cost actually live -- a
 * draft row does not know whether Amazon is showing the listing. */
function liveItemIs(it, filter){
  if(!it) return false;
  if(filter === "live_all") return true;
  if(filter === "live_notshowing"){
    // "inactive" contains "active", so the negative has to be tested for
    // rather than inferred from the absence of the positive.
    const s = String(it.status || "").toLowerCase();
    return s.indexOf("inactive") >= 0 || s.indexOf("suppress") >= 0
        || s.indexOf("incomplete") >= 0;
  }
  if(filter === "live_nocost") return !(it.cogs || (it.profit && it.profit.cogs));
  if(filter === "live_oos"){
    const q = it.qty;
    // Unknown is not zero. A listing whose quantity Amazon did not report is
    // not out of stock, and counting it as such is how a "9 out of stock"
    // tile becomes a reorder decision.
    return q !== undefined && q !== null && q !== "" && Number(q) === 0;
  }
  return true;
}

/* The catalogue item behind an app row, matched by SKU first and only then by
 * ASIN -- two SKUs can share an ASIN, and there the SKU is the listing. */
function liveItemForRow(r){
  if(typeof LIVE_ITEMS === "undefined" || !LIVE_ITEMS) return null;
  const n = v => String(v == null ? "" : v).trim().toUpperCase();
  // Competitor reference excluded -- see _matchableAsin. This pairs an app row
  // with Amazon's own entry for it, and the pairing feeds the handling time and
  // the status tiles, so matching on the competitor's ASIN would attach another
  // seller's listing data to our row.
  const s = n(r && r.sku), a = _matchableAsin(r);
  let byAsin = null;
  for(const it of LIVE_ITEMS){
    if(!it) continue;
    if(s && n(it.sku) === s) return it;
    if(a && !byAsin && n(it.asin) === a) byAsin = it;
  }
  return byAsin;
}

/* SHOW A CHANGE THAT HAS ALREADY HAPPENED, without refetching the list.
 *
 *     "After any bulk action completes, optimistically update the affected
 *      rows immediately. If handling time was set to 2d, the column shows 2d
 *      right away -- no manual refresh needed."
 *
 * The bulk actions used to end with loadRows(), which re-reads every listing in
 * the account plus Amazon's catalogue -- seconds of skeletons to redraw a
 * column that already knew its own answer, and on a slow account it looked
 * like the change had not been made.
 *
 * THIS IS NOT A GUESS AT WHAT THE SERVER WILL SAY. Callers pass only the SKUs
 * the server reported as done, so what is written here is what already
 * happened, not what was requested. A refresh or a Sync still refetches and
 * still wins -- see loadRows -- so if any of this is ever wrong, it is wrong
 * until the next read and no further.
 *
 * The two patches are separate because the row and the catalogue item are
 * separate objects holding separate facts: the row is what WE record, the item
 * is what AMAZON holds. _handlingCell compares them and warns when they
 * disagree, which only works if a caller can write one without the other.
 */
function applyPushedLocally(skus, rowPatch, itemPatch){
  const n = v => String(v == null ? "" : v).trim().toUpperCase();
  const want = new Set((skus||[]).map(n).filter(Boolean));
  if(!want.size) return;
  if(rowPatch && typeof ROWS !== "undefined" && ROWS)
    ROWS.forEach(r => { if(r && want.has(n(r.sku))) Object.assign(r, rowPatch); });
  if(itemPatch && typeof LIVE_ITEMS !== "undefined" && LIVE_ITEMS)
    LIVE_ITEMS.forEach(it => { if(it && want.has(n(it.sku))) Object.assign(it, itemPatch); });
  if(typeof render === "function") render();
  /* A NEW PRICE MAKES THE STORED PROFIT WRONG.
   *
   * r.profit is not derived from r.price -- it is a separate figure the
   * generator worked out once, with the real fee. So writing a price here and
   * redrawing left the profit, margin and ROI beside it describing the OLD
   * price, which is what "the profit remained the same value as it was before"
   * was. Every bulk price change came through this function, so a percentage
   * applied to forty listings restated forty profits that no longer held.
   *
   * Asked for rather than computed: /listing/revenue owns the arithmetic and
   * the fee resolver behind it (Rule 12). See static/js/profit.js. Not awaited,
   * and each one repaints as it lands, so the price is on screen immediately
   * either way.
   */
  const _newPrice = rowPatch && (rowPatch.price !== undefined ? rowPatch.price
                                 : (itemPatch && itemPatch.price));
  if(_newPrice !== undefined && _newPrice !== null
     && typeof profitRefresh === "function"){
    (skus || []).forEach(s => { try{ profitRefresh(s, _newPrice); }catch(e){} });
  }
}

/* WHICH OF THE TWO TILE SETS IS ON SCREEN, and what "no filter" means in it.
 *
 * Written out twice before -- once in summary() to choose the tiles, and
 * nowhere at all in metricFilter(), which is how the toggle below came to have
 * no idea what to fall back TO. The Drafts view's "show everything" is "all";
 * the Live view's is "live_all", because passFilter treats any FILTER starting
 * "live_" as a question about the catalogue item behind the row. Using "all"
 * there would clear the highlight off the Live tile as well, which is not what
 * clearing a sub-filter means.
 *
 * One definition, both callers (CLAUDE.md Rule 12).
 */
function draftsView(){
  return (LIST_SOURCE !== "live" && LIST_SOURCE !== "all");
}
function neutralFilter(){
  return draftsView() ? "all" : "live_all";
}

function passFilter(r){
  if(!matchesSearch(r)) return false;
  if(DUP_ONLY && !isDuplicate(r)) return false; // "Duplicates only" toggle
  if(FILTER==="all")return true;
  if(FILTER==="review")return r.status==="NEEDS_REVIEW";
  if(FILTER==="holds")return isHold(r.status);          // both, for the tile
  // ...and each half on its own, so the two counts that are worded differently
  // can be clicked separately. See isHold above.
  if(FILTER==="refused")return isRefusedByAmazon(r.status);
  if(FILTER==="blocked")return isBlockedByOurChecks(r.status);
  if(FILTER==="approved")return r.status==="APPROVED"||r.status==="API_READY";
  // THE TILE AND THIS FILTER MUST ASK THE SAME QUESTION.
  //
  // This was r.status==="LIVE", the stored word. summary() counts a row as LIVE
  // by asking Amazon's catalogue -- isActuallyLive -- precisely because a
  // listing that went live months ago can still carry a stale IP_HOLD from a
  // failed attempt before that. So the tile counted it and this hid it: the
  // number said one thing and the list under it another, which is the exact
  // complaint this page has had before.
  if(FILTER==="live"){
    if(String(r.status||"").toUpperCase()==="LIVE") return true;
    if(typeof isActuallyLive === "function"
       && typeof _liveCatSetsForCurrentView === "function"){
      const s = _liveCatSetsForCurrentView();
      return isActuallyLive(r, s.skus, s.asins, s.liveGroupShown);
    }
    return false;
  }
  // THE FOUR STATUSES. Asked of liststatus.js, not tested here, so the tile
  // that COUNTS them and the filter that HIDES the rest cannot disagree.
  if(FILTER==="queued")return (typeof lsIsQueued==="function") && lsIsQueued(r);
  if(FILTER==="submitted")return (typeof lsSaysSubmitted==="function")
                                 && lsSaysSubmitted(r);
  if(FILTER==="generated"){
    // The old statuses count as generated too, so an unmigrated database still
    // shows its rows under the tile that claims to be counting them.
    if((typeof lsIsGenerated==="function") && lsIsGenerated(r)) return true;
    return ["NEEDS_REVIEW","APPROVED","API_READY","IP_HOLD","COMPLIANCE_HOLD",
            "ERROR","API_ERROR"].indexOf(String(r.status||"").toUpperCase()) >= 0;
  }
  // Listings carrying at least one warning, whatever their status.
  if(FILTER==="warned")return (typeof lsWarnings==="function")
                              && lsWarnings(r).n > 0;
  // The live-view tiles. An app row is judged by the CATALOGUE item behind it,
  // for the same reason the tiles count catalogue items: whether Amazon is
  // showing a listing, and how many it has, are facts about the listing rather
  // than about our draft of it. A row with no catalogue item behind it cannot
  // satisfy a question about the live listing, so it is hidden rather than
  // shown on the grounds that nothing is known.
  if(String(FILTER).indexOf("live_") === 0){
    if(FILTER === "live_all") return true;
    return liveItemIs(liveItemForRow(r), FILTER);
  }
  return true;
}

// The strip under the toolbar. It used to be the sheet's tabs plus a duplicates
// toggle; the tabs are gone with the spreadsheet, and the duplicates toggle --
// which has nothing to do with sheets and is how you find the extra copies of a
// SKU to delete -- stays. Called from summary() each render.
function renderTabFilter(){
  const host=document.getElementById("tabfilter");
  if(!host) return;
  const _dupN=(typeof countDuplicateSkus==="function")?countDuplicateSkus():0;
  // THE SEARCH BOX STAYS WHATEVER ELSE IS IN HERE.
  //
  // This strip used to hide itself entirely when there were no duplicates,
  // which is right for a duplicates toggle and wrong for the only way to find a
  // listing. The box is drawn first and unconditionally; the duplicates pill
  // joins it when there is something to toggle.
  //
  // The value is read back from SEARCH_Q rather than left in the DOM, because
  // render() rebuilds this strip and a box that empties itself as you type is
  // worse than no box.
  // THE COUNT MUST COUNT WHAT THIS VIEW IS SHOWING.
  //
  // It counted ROWS -- the app's own draft rows -- on every tab. On the Live on
  // Amazon tab the list is Amazon's catalogue, so the box reported "0 matches"
  // about a set the screen was not displaying, directly above 37 listings that
  // included the one being searched for. The number was not wrong about the
  // drafts; it was answering a question nobody had asked.
  //
  // On the Live tab it counts catalogue items, on Drafts it counts rows, and on
  // All it counts both -- minus the catalogue items already represented by an
  // app row, so a listing that appears once is not counted twice.
  let _hits = -1;
  if(SEARCH_Q.trim()){
    const _live = (typeof LIVE_ITEMS !== "undefined" && LIVE_ITEMS) ? LIVE_ITEMS : [];
    const _rows = (Array.isArray(ROWS) ? ROWS : []).filter(matchesSearch);
    const _n = v => String(v == null ? "" : v).trim().toUpperCase();
    // Which of the matching app rows this view actually lists.
    const _shownRows = draftsView()
      ? _rows.filter(r => !isPublishedRow(r))
      : (LIST_SOURCE === "all" ? _rows : _rows.filter(isPublishedRow));
    if(draftsView()){
      _hits = _shownRows.length;
    }else{
      // The catalogue items, minus the ones already standing on screen as an
      // app row -- the same de-duplication liveCatalog itself does, so the
      // count and the list agree.
      const seenSku  = new Set(_shownRows.map(r => _n(r.sku)).filter(Boolean));
      const seenAsin = new Set(_shownRows.map(_matchableAsin).filter(Boolean));
      const _liveHits = _live.filter(it => matchesSearch(it)
        && !(_n(it.sku) && seenSku.has(_n(it.sku)))
        && !(_n(it.asin) && seenAsin.has(_n(it.asin))));
      _hits = _shownRows.length + _liveHits.length;
    }
  }
  host.style.display="";
  host.innerHTML =
    `<div class="lsearch">
       <i class="ti ti-search"></i>
       <!-- THE BOX DID THIS ALREADY AND NEVER SAID SO.
            "i have an option to search listings with identifiers but i do not
             have an option to find the listings with their name"
            Measured on jack_uk's 67 listings: "fol" found 10, "camping chair"
            found 1, "grill" found 2. The name search worked the whole time --
            the placeholder said "SKU, ASIN or barcode", so nobody tried it. -->
       <input id="lsearch_in" class="ed" placeholder="Find by name, SKU, ASIN or barcode…"
              value="${esc(SEARCH_Q)}" oninput="setSearch(this.value)">
       ${SEARCH_Q.trim()
          ? `<button class="ib" title="Clear" onclick="setSearch('')"><i class="ti ti-x"></i></button>
             <span class="cc" style="font-size:11.5px;white-space:nowrap">${_hits} match${_hits===1?'':'es'}</span>`
          : ""}
     </div>` +
    (_dupN
      ? `<button class="tabpill dup ${DUP_ONLY?'active':''}" onclick="toggleDupOnly()" title="Show only duplicate copies so you can delete the extras"><i class="ti ti-copy"></i> Duplicates <span class="tabcount">${_dupN}</span></button>`
      : "");
  // Typing rebuilds the strip, so the caret has to be put back or every
  // keystroke would drop focus after the first one.
  if(SEARCH_Q){
    const el=document.getElementById("lsearch_in");
    if(el){ el.focus(); el.setSelectionRange(el.value.length, el.value.length); }
  }
}
// Switch the tab filter. When a SPECIFIC tab is chosen we also point the workspace's
// active tab at it (server-side), so edits / approvals / image pushes land on the tab
// you're viewing rather than a stale one — Miles has the same SKU on several tabs.
function setTabFilter(gid){
  TAB_FILTER=gid;
  if(gid!=="__all__"){
    const t=(TABS||[]).find(x=>String(x.tab_gid)===String(gid));
    if(t){ syncActiveTab(t.tab_gid, t.tab); }
  }
  render();
}
// Tell the server which tab is active, so single-tab-targeting write routes are correct.
// _ACTIVE_SYNC_GID remembers the last tab we synced so we don't re-POST needlessly.
let _ACTIVE_SYNC_GID = "";
async function syncActiveTab(gid, tab){
  try{
    await fetch("/view/set_active_tab",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({gid:String(gid||""), tab:String(tab||"")})});
    _ACTIVE_SYNC_GID=String(gid||"");
  }catch(e){ /* non-fatal: edits just target the previous active tab */ }
}
// Before ANY write on a card (approve, edit, delete, push), make the server's active
// tab match that card's tab. No-op for single-tab sheets, and only POSTs when the tab
// actually changes — so a bulk action over one tab syncs once, not once per SKU.
async function ensureCardTab(sku){
  if(!(TABS && TABS.length>1)) return;
  const r=ROWS.find(x=>String(x.sku)===String(sku));
  if(r && r.tab_gid && String(r.tab_gid)!==String(_ACTIVE_SYNC_GID)){
    await syncActiveTab(r.tab_gid, r.tab);
  }
}
