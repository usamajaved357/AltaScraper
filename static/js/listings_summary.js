// static/js/listings_summary.js -- what counts as live, and the summary tiles. Moved word for word out of listings.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

// Is this row live ON AMAZON? Amazon's catalog is the ONLY authority whenever we
// have it. A "LIVE" in the sheet is a claim, not proof: the sheet is written by
// this app, it is never re-read from Amazon, and a misrouted tab once put another
// account's "LIVE" rows straight into the Live on Amazon group. So when the live
// catalog is loaded, a row counts as live only if Amazon returned its SKU or ASIN.
//
// Without the catalog (the Drafts view never fetches it) we fall back to the
// sheet's own claim -- and render() labels that group as unverified, rather than
// captioning it "Live on Amazon".
//
// Must return the SAME answer for render() (grouping) and summary() (counting),
// or the top bar disagrees with the grid.
/* Has AMAZON confirmed this row is live?
 *
 * THE GATE IS WHETHER WE HAVE AMAZON'S ANSWER, NOT WHICH TAB IS OPEN.
 *
 *     "when i go to live on amazon section i see the asin B0HCVFW53Y and
 *      B0HCVTDFNW as live and when i go to drafts it showed me the both as
 *      drafts; ready to send"
 *
 * This used to read:
 *
 *     if(liveGroupShown) return <does Amazon list it?>
 *     return norm(r.status)==="LIVE"
 *
 * -- so on the Drafts view it stopped asking Amazon and answered from the
 * stored status word instead. The same listing was therefore live on one tab
 * and a ready-to-send draft on the other, and the app was confident about both.
 * Two answers to one question, decided by which button you last pressed.
 *
 * The gate made sense once, because the catalogue was only ever fetched for the
 * Live and All views. It is fetched on every view now (see shell.js), so the
 * honest condition is simply: if Amazon's catalogue is loaded, Amazon decides.
 * The stored word is the fallback for BEFORE the first sync only -- which is
 * the one case where the app genuinely has nothing better, and where calling a
 * row not-live would slander a listing nobody has asked Amazon about yet.
 *
 * A row whose stored word says LIVE while the loaded catalogue does not list it
 * is deliberately NOT live here. That state has its own name and its own
 * display -- isClaimedLiveOnly(), "not confirmed by Amazon" -- and folding it
 * into "live" is what hid it.
 *
 * liveGroupShown is kept because callers still pass it and one passes an
 * explicit true; it now forces the catalogue answer rather than selecting it.
 */
function isActuallyLive(r, liveCatSkus, liveCatAsins, liveGroupShown){
  const norm = v => String(v||"").trim().toUpperCase();
  // _matchableAsin, not r.asin: on an app row that field is the COMPETITOR
  // reference from the SKU, and matching it against our own catalogue can only
  // produce a false positive -- declaring our draft live because somebody
  // else's listing exists. The SKU match below is the authoritative one.
  const s=norm(r.sku), a=_matchableAsin(r);
  const haveAmazon = liveGroupShown
                  || (typeof _liveCatalogLoaded==="function" && _liveCatalogLoaded())
                  || (liveCatSkus && liveCatSkus.size) || (liveCatAsins && liveCatAsins.size);
  if(haveAmazon) return !!((s && liveCatSkus.has(s)) || (a && liveCatAsins.has(a)));
  return norm(r.status)==="LIVE";
}

// Has Amazon's live catalog actually been fetched for the account+marketplace in view?
// LIVE_STORE holds a cache entry (even an empty one) only AFTER a Sync completes for
// that key. Before that, LIVE_ITEMS is empty simply because we never asked -- which is
// NOT the same as "Amazon returned nothing". Callers that draw a negative conclusion
// ("not confirmed by Amazon") must gate on this, or they slander live listings as dead
// before the first Sync.
function _liveCatalogLoaded(){
  try{
    return (typeof LIVE_STORE!=="undefined") && (typeof _liveKey==="function")
           && (LIVE_STORE[_liveKey()]!==undefined);
  }catch(e){ return false; }
}

// The sheet SAYS this row is live, but Amazon's catalog does not list it.
// Only meaningful once the catalog is loaded -- we cannot call a LIVE row "not
// confirmed by Amazon" until we have actually asked Amazon (i.e. a Sync has run).
// Before that, this returns false so those rows fall back to the sheet's own claim
// and the alarming "Not confirmed by Amazon" group never appears pre-Sync.
function isClaimedLiveOnly(r, liveCatSkus, liveCatAsins, liveGroupShown){
  const norm = v => String(v||"").trim().toUpperCase();
  if(!liveGroupShown) return false;
  if(!_liveCatalogLoaded()) return false;
  return norm(r.status)==="LIVE" && !isActuallyLive(r, liveCatSkus, liveCatAsins, liveGroupShown);
}

// Is this row published on Amazon, and therefore NOT a draft?
//
// The Drafts view hides these, so the counters above the list have to agree
// about which they are -- they did not, which is what made the top of the
// screen describe a different set of listings from the list underneath it.
// Reported as: "it shows total listings 86 ... and live 12, what do it mean by
// live, in drafts". The list was showing 74 and the tiles were counting 86.
//
// Published means the store says LIVE, or a Sync has loaded Amazon's catalogue
// and Amazon itself lists the SKU or ASIN.
//
// THE BODY NOW LIVES IN static/js/liststatus.js (CLAUDE.md Rule 12). It was one of
// THREE separate answers to "is this published" -- this one counting only LIVE,
// miles_template.js's _PUBLISHED_STATES counting LIVE and SUBMITTED, and
// barcode_clash.py counting LIVE, SUBMITTED and ACTIVE. A row Amazon had accepted
// was therefore "published" to one of them and "a draft" to another, which is how
// a submitted listing came to sit in Drafts reading as if it had never been sent.
// The name stays here because everything on this screen calls it; the rule it
// applies is defined once, next to the two questions it had been confused with
// (lsWasSentToAmazon vs lsIsPublished).
function isPublishedRow(r){ return lsIsPublished(r); }

// Build the SKU/ASIN sets once per render -- reused by summary()
function _liveCatSetsForCurrentView(){
  const norm = v => String(v||"").trim().toUpperCase();
  return {
    skus:  new Set((LIVE_ITEMS||[]).map(it=>norm(it.sku)).filter(Boolean)),
    asins: new Set((LIVE_ITEMS||[]).map(it=>norm(it.asin)).filter(Boolean)),
    liveGroupShown: (LIST_SOURCE==="live" || LIST_SOURCE==="all"),
  };
}

function summary(){
  renderTabFilter();                             // keep the tab filter row in sync
  const c={QUEUED:0,GENERATED:0,SUBMITTED:0,
           APPROVED:0,API_READY:0,NEEDS_REVIEW:0,HOLD:0,ERROR:0,LIVE:0};
  const sets = _liveCatSetsForCurrentView();
  // Counts reflect the ACTIVE tab filter: "All tabs" counts everything, a specific
  // tab counts only that tab's rows. Blank placeholder rows are excluded so the
  // "N listings" total agrees with the grid (which hides them) and the tab pills.
  const _allTabRows = ROWS.filter(tabPass)
                       .filter(r=> (typeof isEmptyRow!=="function") || !isEmptyRow(r))
                       .filter(r=> !DUP_ONLY || isDuplicate(r));
  // COUNT WHAT THE LIST BELOW ACTUALLY SHOWS.
  //
  // On the Drafts view the list hides published rows, but these tiles counted
  // every row -- so the screen said "86 listings" and "12 live" above a list of
  // 74 drafts, and a "Live" tile on a screen that shows no live listings. It
  // was reported, fairly, as making no sense.
  //
  // The published rows are not forgotten: they are named underneath, with a way
  // to go and see them.
  const _draftsView = draftsView();
  const _hiddenLive = _draftsView ? _allTabRows.filter(isPublishedRow) : [];
  const _tabRows = _draftsView
                 ? _allTabRows.filter(r=>!isPublishedRow(r))
                 : _allTabRows;
  _tabRows.forEach(r=>{
    // FIX: reclassify HOLD/NEEDS_REVIEW/etc. as LIVE if the row's SKU/ASIN
    // matches the Amazon catalog. Without this the top-bar shows a stale
    // "N on hold" count for rows that already went live on Amazon but never
    // had their stored status updated from a pre-submit HOLD.
    if(isActuallyLive(r, sets.skus, sets.asins, sets.liveGroupShown)){
      c.LIVE++;
      return;
    }
    // THE FOUR STATUSES. QUEUED and GENERATED are what the flow uses now; the
    // rest are kept because a database that has not been migrated yet still
    // holds them, and a row counted into nothing disappears off the screen
    // without saying so.
    if(r.status==="QUEUED")c.QUEUED++;
    else if(r.status==="GENERATED")c.GENERATED++;
    else if(r.status==="SUBMITTED")c.SUBMITTED++;
    else if(r.status==="APPROVED")c.APPROVED++;
    else if(r.status==="API_READY")c.API_READY++;
    else if(r.status==="LIVE")c.LIVE++;
    else if(r.status==="NEEDS_REVIEW")c.NEEDS_REVIEW++;
    else if(r.status==="IP_HOLD"||r.status==="COMPLIANCE_HOLD")c.HOLD++;
    else if(r.status==="ERROR"||r.status==="API_ERROR")c.ERROR++;
  });
  // include live Amazon listings in the counts when they're part of the view.
  // Deduplicate: a catalog tile whose SKU/ASIN already matched an app row above
  // has already been counted as LIVE -- don't count it twice.
  const norm = v => String(v||"").trim().toUpperCase();
  // Worked out ONCE. It was filtered twice with the same predicate to build the
  // two sets, and the count of it was then not taken at all -- which is how the
  // total below came to leave these rows out.
  const _liveAppRows = _tabRows.filter(r=>isActuallyLive(r, sets.skus, sets.asins, sets.liveGroupShown));
  const alreadyCountedSkus  = new Set(_liveAppRows.map(r=>norm(r.sku)).filter(Boolean));
  // _matchableAsin, not r.asin: this set EXCLUDES catalogue items from the
  // count, so seeding it with competitor ASINs risks dropping a genuinely live
  // listing out of the total -- the undercount version of the same mistake.
  const alreadyCountedAsins = new Set(_liveAppRows.map(_matchableAsin).filter(Boolean));
  const liveCount = ((LIST_SOURCE==='live'||LIST_SOURCE==='all')
                     ? (LIVE_ITEMS||[]).filter(it=>{
                         const s=norm(it.sku), a=norm(it.asin);
                         if(s && alreadyCountedSkus.has(s))  return false;
                         if(a && alreadyCountedAsins.has(a)) return false;
                         return true;
                       }).length
                     : 0);
  c.LIVE += liveCount;
  // TOTAL IS WHAT THE LIST BELOW IT ACTUALLY CONTAINS.
  //
  // In the Live view this was liveCount -- the catalogue items left AFTER the
  // ones matching an app row were removed. But the list shows both: the app's
  // own rows that Amazon confirmed live, and then the catalogue-only ones. So
  // the total counted the second group and not the first, and on nestwell_goods
  // read "TOTAL LISTINGS 43" directly above "LIVE 55" -- a total smaller than
  // one of its own parts, which is how it was noticed.
  let total = _tabRows.length;
  if(LIST_SOURCE==='live'){
    total = _liveAppRows.length + liveCount;
    // In the Live view every row IS live, so the LIVE tile counts the same set
    // the total does. It was counting app rows whose STATUS says LIVE across the
    // whole tab -- including ones this view is not showing -- so it could exceed
    // the total sitting next to it, which is the pair of numbers that got
    // reported ("43 total listings and 55 live listings").
    c.LIVE = total;
  }
  else if(LIST_SOURCE==='all') total = _tabRows.length + liveCount;
  // Orbit's four metric tiles replace the old one-line text summary. Each is
  // clickable and filters the list to that status -- the count was always the
  // question "which ones need me?", and it now answers it in one click instead
  // of sending you to the dropdown.
  //
  // The counts below the tiles (errors, preview-ready, duplicates) are kept as a
  // quiet line: they matter, but not enough to spend one of four tiles on, and
  // dropping them would lose information the old summary gave you.
  const _cur = (typeof FILTER !== "undefined") ? FILTER : "all";
  // ONE CARD, DEFINED ONCE (CLAUDE.md Rule 12).
  //
  //     "the sizing and the theme of the repricer page is nice, i want this to
  //      be applied on all listings page and the catalog page"
  //
  // This used to build its own .metric -- centred, 22px, no bar -- while the
  // Catalog built .ui-stat and the Repricer built .rp-mc. Three cards, three
  // sizes, three alignments, on three screens that do the same job. It now
  // calls the shared uiStat() in pageui.js, and the look lives in
  // static/css/datatable.css. Nothing about WHAT the tiles count has changed.
  //
  // `share` draws the bar along the bottom: the count as a fraction of the
  // total beside it. "12 blocked" reads differently out of 20 than out of 400,
  // and the number alone cannot say which. Passed only for the subsets -- the
  // total is the whole, and a permanently full bar states nothing.
  const tile = (n, label, filter, tone) => {
    const whole = Number(total) || 0;
    const cnt = Number(n);
    const sub = tone !== undefined;
    return uiStat({
      value: n,
      label: label,
      on: _cur === filter,
      onclick: "metricFilter('" + filter + "')",
      title: "Show only these",
      // No hint line under the number: removed on the owner's
      // instruction (27 Sep 2026) -- the cards are already clickable, and the
      // hover title says what they do.
      share: (sub && !_pending && whole > 0 && isFinite(cnt))
        ? Math.min(1, cnt / whole) : null,
      barColor: tone,
    });
  };
  const extras = [];
  // A COUNT WITH NO NOUN IS NOT A FACT.
  //
  //     "i see a text is written 25 on hold, what is this and why is it
  //      written like this"
  //
  // Fair. "25 on hold" named no thing, gave no reason, and could not be
  // clicked -- so it was a number you could neither understand nor act on.
  // Both now say what they are counting, why those rows are stopped, and take
  // you to them.
  // EACH COUNT GOES TO ITS OWN LIST. Both of these used to pass 'holds', which
  // is the UNION -- so clicking a count of 3 showed 28 rows. See isHold.
  // THE TWO RED COUNTS ARE GONE, at the owner's request.
  //
  //     "2 listings Amazon refused · 52 held by a compliance or IP check
  //      re-check them the app shows me this message on the all listing page,
  //      i donot want to know how many of the listings show this status so
  //      please remove it"
  //
  // They were:
  //     `${c.ERROR} listing(s) Amazon refused`        -> metricFilter('refused')
  //     `${c.HOLD} held by a compliance or IP check`  -> metricFilter('blocked')
  //     `re-check them`                               -> rescanFlags()
  //
  // NOTHING WAS LOST WITH THEM, which was checked before deleting rather than
  // assumed. rescanFlags() has its own toolbar button ("Re-check flags",
  // templates/dashboard.html), and both filters remain reachable from the
  // status tabs -- so the capability stayed and only the running total went.
  //
  // Why he is right about the total specifically: a count of held listings is a
  // number you cannot act on. It says how many rows carry a verdict without
  // saying which rows, or which rule, and it sat above a list those rows were
  // already in. The per-listing flag on the row itself says the same thing
  // where it can be acted on.
  // "N ALREADY LIVE ON AMAZON, NOT SHOWN HERE" IS GONE, at the owner's request.
  //
  //     "i dont need this message, i know that when a listing is live on amazon
  //      it will be removed from draft"
  //
  // It was written to answer "where did my listing go", and it did -- but it
  // answered it every single time the Drafts list was drawn, to somebody who
  // has since learned the answer. A permanent line explaining a rule you
  // already know is noise, and this one sat directly above the counts that do
  // need reading.
  //
  // NOTHING IS HIDDEN THAT WAS NOT HIDDEN BEFORE: the Live on Amazon tab is a
  // click away and is where those rows have always been. `_hiddenLive` is still
  // computed above -- it is what excludes them from the Drafts list -- so this
  // is the sentence going, not the behaviour.
  if(countDuplicateSkus()>0){
    extras.push(`<span class="dupsum" onclick="toggleDupOnly()" title="Show only the duplicate copies so you can delete the extras"><i class="ti ti-copy"></i> ${countDuplicateSkus()} duplicate SKU${countDuplicateSkus()>1?'s':''} across tabs</span>`);
  }
  const _sumHost = document.getElementById("summary");

  // THE TILES ANSWER WHAT THE VIEW CAN ANSWER.
  //
  // On the LIVE view three of the four said nothing. "Total listings 45" and
  // "Live 45" are the same number by definition -- everything in this list is
  // live -- and "Ready to submit 0" cannot ever be anything else, because a
  // listing that is already on Amazon has been submitted. Reported as: "45
  // total listings and 45 live listings and 0 ready to send listings, do it
  // makess sense?"
  //
  // It does not, so the live view gets tiles about LIVE listings: how many
  // Amazon is not currently showing, how many have no cost (which is what makes
  // every profit figure wrong), and how many have run out.
  // A COUNT OF ZERO IS A CLAIM. While the drafts are still in flight, ROWS is
  // empty and every one of these tiles confidently reports 0 -- four wrong
  // numbers above a grid that is about to fill. An em-dash says "not yet",
  // which is the truth for the second it lasts.
  //
  //     "selvora dont have zero drafts but why was that error message
  //      appearing ... why that 1 sec gap is there"
  const _pending = (typeof _rowsStillComing === "function") && _rowsStillComing();
  const _n = v => _pending ? "—" : v;
  let tiles;
  if(_draftsView){
    // THE FOUR STATUSES, in the order a listing passes through them.
    //
    // "Needs review", "Ready to submit" and "Blocked or errored" are gone with
    // the statuses behind them. There is no blocked tile any more BECAUSE
    // NOTHING BLOCKS: what used to stop a listing is a warning on it now, and
    // that is counted separately below rather than as a status, because a
    // listing with a warning is not in a different state -- it is generated,
    // and someone should look at it.
    //
    // NEEDS_REVIEW is folded into Generated so a database that has not been
    // migrated yet still shows its rows somewhere rather than counting them
    // into nothing.
    //
    // THE FOURTH TILE IS APPROVED, NOT LIVE.
    //
    //     "on the all listings page and draft page inside it i see there are 4
    //      filter boxes, Queued, Generated, Submitted, Live. It does not make
    //      sense to keep the live filter on the drafts page, so please replace
    //      the live filter in the draft page with approved filter"
    //
    // Right, and for a stronger reason than it reads: this view REMOVES
    // published rows before counting anything (_tabRows above drops
    // isPublishedRow), so the Live tile was counting live listings in a set
    // that has had the live listings taken out of it. It could only ever say 0,
    // and clicking it could only ever empty the grid. The listings it claimed
    // to count are on the Live on Amazon tab, which the line under the tiles
    // already offers.
    //
    // Approved answers a question this view CAN answer and is the step between
    // Generated and Submitted: the ones you have said yes to and not yet sent.
    // APPROVED and API_READY both count, matching passFilter('approved')
    // exactly, and they come OUT of Generated -- a listing must not be counted
    // in two tiles above one list.
    const _gen = c.GENERATED + c.NEEDS_REVIEW + c.HOLD + c.ERROR;
    const _approved = c.APPROVED + c.API_READY;
    // "Drafts", not "Generated" -- the same word the row badge uses now
    // (liststatus.js maps GENERATED -> DRAFT), so the tile and the rows it
    // counts say the same thing. GENERATED named the step that produced the
    // row, which is of no interest to anyone reading the screen.
    //
    // THE LABEL ONLY. The third argument is the filter key and stays
    // "generated": it is what metricFilter() sends and what passFilter() and
    // the status dropdown's <option value> both match on, so renaming it would
    // break the click rather than relabel it.
    //
    // NOTE THE AMBIGUITY THIS CREATES, since it is deliberate and chosen: the
    // TAB is also called Drafts and is wider -- it holds queued, generated and
    // submitted rows together -- while this tile counts only the generated
    // ones (plus the three unmigrated words folded in above). So "Drafts 12"
    // can sit inside a Drafts tab showing 30 rows. The owner asked for the
    // tile to match the badge, and matching the badge is the more useful of
    // the two consistencies: the badge is on every row you read.
    tiles = tile(_n(c.QUEUED), "Queued", "queued", "var(--ink3)")
          + tile(_n(_gen), "Drafts", "generated", "var(--gold)")
          + tile(_n(_approved), "Approved", "approved", "var(--ok)")
          + tile(_n(c.SUBMITTED), "Submitted", "submitted", "var(--ok)");
  }else{
    // THREE OF THESE FOUR TILES USED TO SEND THE SAME FILTER.
    //
    //     "when i click on not showing status button a green border appears
    //      around only this button but when i click on any one of the button
    //      from no cost set, out of stock or live listings button. clicking
    //      only 1 button draws a border on all 3"
    //
    // Live listings, No cost set and Out of stock all passed "all". The tile
    // lights up when its filter equals the current one, so pressing any of the
    // three lit all three -- and since "all" means no filter, none of them
    // hid anything either. One defect, both symptoms.
    //
    // Each has its own filter now, and the COUNT and the FILTER read the same
    // predicate (liveItemIs), so a tile can never say 9 and then show 40.
    const live = (typeof LIVE_ITEMS !== "undefined" && LIVE_ITEMS) ? LIVE_ITEMS : [];
    tiles = tile(total, "Live listings", "live_all")
          + tile(live.filter(it => liveItemIs(it, "live_notshowing")).length,
                 "Not showing", "live_notshowing", "var(--red)")
          + tile(live.filter(it => liveItemIs(it, "live_nocost")).length,
                 "No cost set", "live_nocost", "var(--gold)")
          + tile(live.filter(it => liveItemIs(it, "live_oos")).length,
                 "Out of stock", "live_oos", "var(--red)");
  }

  _sumHost.innerHTML =
    `<div class="ui-stats">` + tiles + `</div>`
    // margin:0. It was `-6px 0 12px`: a negative top to close the gap under the
    // cards, and 12px below. The cards' own 12px bottom margin is gone now
    // (#summary .ui-stats in dashboard.css), so the negative would pull this
    // line ON TOP of them and the 12px would put back the gap that was just
    // removed. A small top margin keeps it off the cards without reopening it.
    + (extras.length ? `<div class="cc" style="margin:4px 0 0">${extras.join(" &nbsp;·&nbsp; ")}</div>` : "");
  // NO MIGRATION NOTICE HERE, AND NEVER AGAIN.
  //
  //     "Bring in whatever is left automatically right now, then remove this
  //      banner entirely. It should never appear again. ... We are fully on the
  //      database now."
  //
  // A notice used to sit here whenever ROWS_SOURCE.from_sheet was above zero:
  // "N of these listings are still only in the Google Sheet", with a button to
  // check what would be brought in. The listings read now performs that import
  // itself when it finds such rows -- see the auto-import in /rows_all and
  // domain/sheet_migration.py -- so by the time this screen draws, there is
  // nothing left for a person to authorise.
  //
  // Numbers count into place, but only the ones that actually changed --
  // see altaCountMetrics. This runs on every render, including a filter click,
  // and animating an unchanged figure would say "this just moved" about
  // something that did not.
  if(typeof altaCountMetrics === "function") altaCountMetrics(_sumHost);
}
