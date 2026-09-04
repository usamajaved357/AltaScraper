// static/js/liststatus.js — ONE definition of what a listing's STATUS WORD means.
//
// WHY THIS FILE EXISTS (CLAUDE.md Rule 12).
//
// "Is this listing published?" was answered independently in three places, and
// they did not agree with each other:
//
//   static/js/listings.js      isPublishedRow()   -> "LIVE" only
//   static/js/miles_template.js _PUBLISHED_STATES -> {"LIVE","SUBMITTED"}
//   domain/barcode_clash.py     _LIVE             -> ("LIVE","SUBMITTED","ACTIVE")
//
// So the app believed a SUBMITTED row WAS published when deciding whether Amazon
// had deleted it, and WAS published when checking barcode clashes, but was NOT
// published when deciding which tab it belonged in. That last one is why a
// listing Amazon had accepted sat in Drafts looking like it had never been sent.
//
// The two questions are genuinely different and they now have different names:
//
//   lsWasSentToAmazon(r)   did WE hand this to Amazon?         LIVE or SUBMITTED
//   lsIsPublished(r)       is it live now, as far as we know?  LIVE, or in
//                                                              Amazon's catalogue
//
// Conflating them is what caused the bug; naming them apart is the fix. Anything
// that needs either answer calls this file. Nothing re-implements it.
//
// THE WORDING LIVES HERE TOO, deliberately. The other half of the same defect was
// the drawer printing "Published live to Amazon" over a row whose status said
// SUBMITTED -- the status word and the sentence describing it had drifted apart
// because they were written in different files. Keeping them in one file makes
// that drift impossible: change the vocabulary and the sentence is right there.
//
// Loaded BEFORE listings.js (see templates/dashboard.html) so every caller has it.

// ---- the vocabulary --------------------------------------------------------
// Amazon publishes ASYNCHRONOUSLY: putListingsItem returns ACCEPTED and the
// listing appears 5-30 minutes later. SUBMITTED is that gap, and it is an honest
// state -- not a draft, not yet live. See amazon_listing_generator.py:7261-7291.
const LS_LIVE      = "LIVE";
const LS_SUBMITTED = "SUBMITTED";
// FOUR STATUSES, and these are the two new ones.
//
// QUEUED    uploaded or typed in, waiting to be generated. The row exists in
//           the listings store with a real SKU and almost nothing else on it.
// GENERATED the generator has filled it in. It replaced NEEDS_REVIEW, APPROVED,
//           API_READY, IP_HOLD and COMPLIANCE_HOLD -- see
//           scripts/migrate_statuses.py.
//
// NOTHING BLOCKS ANY MORE. The two _HOLD statuses used to stop a listing being
// submitted; what they were protecting against is now a WARNING on the row
// (listing/warnings.py) and Submit is always available. A listing with five
// warnings and one with none are both GENERATED.
const LS_QUEUED    = "QUEUED";
const LS_GENERATED = "GENERATED";

// Statuses meaning "this app handed this listing to Amazon". Amazon cannot tell a
// deleted listing from one that never existed -- getListingsItem answers NOT_FOUND
// for both -- so only these rows may be read as "deleted" when Amazon says NOT_FOUND.
const LS_SENT_STATES = new Set([LS_LIVE, LS_SUBMITTED]);

function lsNorm(v){ return String(v == null ? "" : v).trim().toUpperCase(); }
function lsStatusOf(r){ return lsNorm(r && r.status); }

// Did we send it? (LIVE or SUBMITTED)
function lsWasSentToAmazon(r){ return LS_SENT_STATES.has(lsStatusOf(r)); }

// Does the stored word itself say LIVE?
function lsSaysLive(r){ return lsStatusOf(r) === LS_LIVE; }

// Is the stored word SUBMITTED? (accepted by Amazon, publication pending)
function lsSaysSubmitted(r){ return lsStatusOf(r) === LS_SUBMITTED; }

// Waiting to be generated: uploaded or typed in, nothing made from it yet.
function lsIsQueued(r){ return lsStatusOf(r) === LS_QUEUED; }

// The generator has filled it in. Ready to submit whenever you decide -- there
// is no separate "approved" step and no hold that can stop it.
function lsIsGenerated(r){ return lsStatusOf(r) === LS_GENERATED; }

/* HOW MANY THINGS ARE WRONG WITH THIS LISTING, and how badly.
 *
 * The warnings live on the row as a list of {type, severity, message, details};
 * dashboard._card parses whatever was stored into a list, so a screen never has
 * to. Returns {n, high, medium, low} -- counts only, because the card wants a
 * number and the drawer wants the messages.
 */
function lsWarnings(r){
  const list = (r && Array.isArray(r.warnings)) ? r.warnings : [];
  const out = {n: list.length, high: 0, medium: 0, low: 0, list: list};
  list.forEach(function(w){
    const s = String((w && w.severity) || "low").toLowerCase();
    if(out[s] === undefined) out.low++; else out[s]++;
  });
  return out;
}

/* The same warnings, counted by TYPE as well as severity.
 *
 * WHY THIS EXISTS. The product page's Checks rail showed Restricted, Compliance
 * and Claim risks as three green ticks while the Compliance tab listed two HIGH
 * warnings underneath them -- "the indicators are lying". The rail was reading
 * three different row fields (r.restricted.matched, r.viability.matched,
 * r.claim_flags) and the tab was reading r.warnings, so the two could not agree
 * and nothing made them.
 *
 * One reader now, beside lsWarnings and sharing its parse, because a second
 * copy of "what counts as a compliance warning" is how they drifted apart in
 * the first place (CLAUDE.md Rule 12).
 *
 * Returns {type: {n, high, medium, low, worst}} where `worst` is "high",
 * "medium", "low" or "" -- "" meaning this type has no warnings at all, which
 * is the only state that earns a green tick.
 */
function lsWarnTypes(r){
  const out = {};
  ((r && Array.isArray(r.warnings)) ? r.warnings : []).forEach(function(w){
    const t = String((w && w.type) || "other").toLowerCase();
    let s = String((w && w.severity) || "low").toLowerCase();
    if(s !== "high" && s !== "medium") s = "low";
    const e = out[t] || (out[t] = {n: 0, high: 0, medium: 0, low: 0, worst: ""});
    e.n++; e[s]++;
    // Worst wins: one HIGH among five lows is a red light, not an amber one.
    if(e.worst !== "high") e.worst = (s === "high") ? "high"
                                   : (e.worst === "medium" ? "medium" : s);
  });
  return out;
}

/* The colour one check should be, from any number of warning types.
 *
 * high -> red, medium -> amber, low or none -> green. Low is deliberately GREEN
 * and not amber: "no barcode provided" is a low warning on nearly every draft,
 * and a rail that is permanently amber tells you nothing on the day something
 * real appears.
 */
function lsCheckTone(types, keys){
  let worst = "";
  (keys || []).forEach(function(k){
    const e = (types || {})[k];
    if(!e) return;
    if(e.worst === "high") worst = "high";
    else if(e.worst === "medium" && worst !== "high") worst = "medium";
  });
  return worst === "high" ? "bad" : (worst === "medium" ? "warn" : "ok");
}

/* How many warnings these types account for, for the label. */
function lsCheckCount(types, keys){
  let n = 0;
  (keys || []).forEach(function(k){ n += (((types || {})[k]) || {}).n || 0; });
  return n;
}

// Does AMAZON'S OWN fetched catalogue list this row?
//
// Uses _matchableAsin (listings.js), never r.asin: on an app row that field is the
// COMPETITOR reference out of the SKU (price_days_ASIN), so matching it would
// declare our draft published merely because the competitor's listing exists.
function lsInLiveCatalogue(r){
  const items = (typeof LIVE_ITEMS !== "undefined" && LIVE_ITEMS) ? LIVE_ITEMS : [];
  if(!items.length) return false;
  const s = lsNorm(r && r.sku);
  if(s){
    const skus = new Set(items.map(x => lsNorm(x && x.sku)).filter(Boolean));
    if(skus.has(s)) return true;
  }
  const a = (typeof _matchableAsin === "function") ? _matchableAsin(r) : "";
  if(a){
    const asins = new Set(items.map(x => lsNorm(x && x.asin)).filter(Boolean));
    if(asins.has(a)) return true;
  }
  return false;
}

// Is this row published on Amazon, and therefore NOT a draft?
//
// Published means the store says LIVE, or a Sync has loaded Amazon's catalogue and
// Amazon itself lists the SKU or ASIN. This is the body that used to live in
// listings.js as isPublishedRow(); that name still exists there and calls this.
function lsIsPublished(r){
  if(lsSaysLive(r)) return true;
  return lsInLiveCatalogue(r);
}

// Sent to Amazon, and Amazon has not confirmed it yet.
//
// This is the state that had no name and therefore no place on screen: the row was
// filed under Drafts, which reads as "never sent". It gets its own group now --
// see submittedGroupHtml() in autoverify.js.
function lsIsWaitingOnAmazon(r){
  return lsSaysSubmitted(r) && !lsInLiveCatalogue(r);
}

/* WHAT THE WARNING MARK SAYS ON HOVER. One sentence, one place.
 *
 *     "The '1 warning' / '2 warnings' text is redundant -- the warning icons
 *      already show the count. Remove the text line entirely."
 *
 * The words came off the screen; they had to go somewhere, and hover is where
 * the messages already were. Three views draw that mark -- the card's badge,
 * the detailed row's chip and the product page's hero -- and they were about to
 * grow three slightly different tooltips (CLAUDE.md Rule 12), which is how one
 * view comes to list four messages and another one.
 *
 * Takes the object lsWarnings() returns: {n, high, medium, list}.
 */
function lsWarnTip(w){
  if(!w || !w.n) return "";
  const worst = w.high ? "high" : (w.medium ? "medium" : "low");
  return String(w.n) + " warning" + (w.n === 1 ? "" : "s")
    + " (worst: " + worst + ")\n"
    + (w.list || []).slice(0, 4).map(function(x){
        return "• " + String((x && x.message) || "");
      }).join("\n")
    + ((w.list || []).length > 4 ? "\n• …and " + (w.list.length - 4) + " more" : "");
}

// ---- the wording -----------------------------------------------------------
// What the drawer says when a run finishes. Kept beside the vocabulary above so a
// change to one cannot silently leave the other lying.
//
// kind:
//   "ok_submit_pending" -> Amazon ACCEPTED it; it is not live yet
//   "ok_live"           -> Amazon has CONFIRMED it live
function lsVerdictHtml(kind, warnings){
  const _esc = (typeof esc === "function") ? esc : (x => String(x == null ? "" : x));
  const warn = warnings ? ('<div class="rwarn">Warnings: ' + _esc(warnings) + '</div>') : "";
  if(kind === "ok_live"){
    return '<div class="rgood">✓ Published live to Amazon.</div>'
         + (warn || '<div class="rmsg">Amazon has confirmed this listing is live on your account.</div>');
  }
  // ACCEPTED, NOT PUBLISHED. The old text here read "Published live to Amazon /
  // The listing is now live on your account" -- printed off the generator's own
  // "SUBMITTED -- accepted by Amazon (live shortly)" line, which says the
  // opposite. Both sentences were on screen at once.
  return '<div class="rgood">✓ Accepted by Amazon.</div>'
       + warn
       + '<div class="rmsg">Amazon has taken this listing and is publishing it now — '
       + 'usually live within <b>5–30 minutes</b>. It is <b>not live yet</b>.</div>'
       + '<div class="rhint">You do not need to do anything. It is filed under '
       + '<b>Submitted — waiting on Amazon</b>, and this app re-checks Amazon '
       + 'automatically after 5 and 10 minutes, moving it to <b>Live on Amazon</b> '
       + 'as soon as Amazon confirms it.</div>';
}
