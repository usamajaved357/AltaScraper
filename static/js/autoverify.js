// static/js/autoverify.js — after a submit, ask Amazon again, on a schedule.
//
// THE PROBLEM THIS SOLVES.
//
// A submit returns ACCEPTED and the row is written SUBMITTED. Amazon then
// publishes asynchronously, 5-30 minutes later. The ONLY thing that ever turned
// SUBMITTED into LIVE was _reverifyLiveStatus() in miles_template.js, and its only
// caller was syncLive() -- the Sync button. So the row left Drafts when, and only
// when, the user happened to press Sync late enough. Press it two minutes after
// submitting and Amazon still says "not yet", nothing flips, and nothing tells you
// to come back later. Recorded in routes/listing_routes.py:108-110 as a listing
// that read "SUBMITTED" on screen for a fortnight.
//
// So the app now does the asking itself, on the schedule the owner specified:
//
//     5 minutes  -> re-check Amazon
//     10 minutes -> re-check Amazon (if still not live)
//     15 minutes -> stop checking and SAY SO, rather than wait silently
//
// NOTHING NEW TALKS TO AMAZON. This drives the generator's EXISTING verify mode
// (/run/api_verify, amazon_listing_generator.py:7086-7134), scoped with ?skus= to
// the one listing. That path is read-only against Amazon and only ever promotes a
// row to LIVE on a BUYABLE/DISCOVERABLE answer; it never downgrades on a failure.
// This file schedules it. It does not re-implement any of it.
//
// The schedule SURVIVES A REFRESH (localStorage) because Amazon's 5-30 minutes is
// longer than a person keeps a tab still, and a schedule that only worked while
// you watched it would just be the Sync button again.

// The owner's schedule, in milliseconds. Times are measured from the submit.
const AV_CHECKS  = [5 * 60 * 1000, 10 * 60 * 1000];   // re-check Amazon at 5 and 10 min
const AV_WARN_AT = 15 * 60 * 1000;                    // still not live -> say so
const AV_TICK    = 30 * 1000;                         // how often we look at the clock
const AV_KEY     = "autoverify_pending";

// ---- and then it stopped asking, for ever -----------------------------------
//
//     "i see that the listings submitted yesterday are still sitting in the
//      draft page and not in live if that was accepted or rejected i should
//      know the reason"
//
// The schedule above is the whole of what this file used to do, and it runs out.
// Two checks inside the first ten minutes, one warning at fifteen, and then
// nothing -- not the next hour, not the next day, not on a reload. A listing
// submitted yesterday was asked about twice while it was minutes old and has
// been sitting untouched ever since, which is exactly what was reported.
//
// The 5/10/15 schedule is right for a listing you just submitted and are
// watching. It is not an answer for one that is a day old, because by then the
// question has changed: not "has it appeared yet" but "what happened to it".
//
// So opening the listings screen re-asks about every SUBMITTED listing that
// Amazon has not confirmed, however old. That is bounded three ways, because it
// is the only automatic thing here that is not tied to an action you took:
//   * a per-SKU cooldown, so returning to the screen twice in a minute asks once
//   * a cap per load, so an account with fifty pending listings does not open
//     fifty streams
//   * the same run lock as everything else, so it never fights a Preview/Submit
//
// WHY THIS SURFACES A REASON. The verify run already records Amazon's own words
// -- amazon_listing_generator.py writes "RE-VERIFIED -- not yet confirmed live;
// Amazon still shows N issue(s): ..." into the row's Notes. That text existed
// all along and nothing was ever running to produce it. Once it does, the
// Submitted group prints it (see avWaitedFor).
const AV_STALE_COOLDOWN = 10 * 60 * 1000;   // don't re-ask the same SKU sooner
const AV_STALE_MAX      = 15;               // most to check on one screen open
const AV_SEEN_KEY       = "autoverify_lastcheck";

let AV_TIMER = null;
let AV_BUSY  = false;

// ---- the pending list (persisted) ------------------------------------------
// [{sku, account, at, done:[checkIndex...], warned:bool}]
function avLoad(){
  try{
    const raw = localStorage.getItem(AV_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? arr : [];
  }catch(e){ return []; }
}
function avSave(list){
  try{ localStorage.setItem(AV_KEY, JSON.stringify(list || [])); }catch(e){}
}
function avAccountId(){
  try{
    return (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT) ? String(CUR_ACCOUNT.id || "") : "";
  }catch(e){ return ""; }
}

// Called when a submit is ACCEPTED by Amazon (runqueue.js, terminal state).
function avSubmitted(sku){
  if(!sku) return;
  const list = avLoad();
  const s = String(sku);
  const acc = avAccountId();
  // Re-submitting the same listing restarts its clock rather than stacking a
  // second schedule on it.
  const rest = list.filter(e => !(String(e.sku) === s && String(e.account || "") === acc));
  rest.push({sku: s, account: acc, at: Date.now(), done: [], warned: false});
  avSave(rest);
  avStart();
}

// The entries for the account currently on screen. A submit on one account must
// never draw a "waiting" banner on another one's listings.
function avPendingHere(){
  const acc = avAccountId();
  return avLoad().filter(e => String(e.account || "") === acc);
}
function avEntryFor(sku){
  const s = String(sku || "");
  return avPendingHere().find(e => String(e.sku) === s) || null;
}
function avForget(sku, account){
  const s = String(sku || ""), acc = String(account == null ? avAccountId() : account);
  avSave(avLoad().filter(e => !(String(e.sku) === s && String(e.account || "") === acc)));
}

// ---- has it gone live? -----------------------------------------------------
// Answered from the rows already on screen, through the shared helper -- so this
// agrees with the tab filter and the group headings by construction.
function avRowIsLive(sku){
  try{
    const r = (typeof ROWS !== "undefined" && ROWS.find)
      ? ROWS.find(x => String(x.sku) === String(sku)) : null;
    if(!r) return false;
    return (typeof lsIsPublished === "function") ? lsIsPublished(r) : false;
  }catch(e){ return false; }
}

// ---- ask Amazon ------------------------------------------------------------
// Drives the generator's existing verify mode for ONE sku. Resolves true if that
// run reported the listing now live.
function avRunVerify(sku){
  return new Promise(function(resolve){
    // A Preview/Submit is streaming right now. Don't fight it for the run lock --
    // this is a background check with no deadline; the next tick will do it.
    if(typeof ES !== "undefined" && ES){ resolve(null); return; }
    let flipped = false, es;
    const q = "/run/api_verify?skus=" + encodeURIComponent(sku);
    const url = (typeof acctUrl === "function") ? acctUrl(q) : q;
    try{ es = new EventSource(url); }
    catch(e){ resolve(null); return; }
    ES = es;                                  // hold the run lock while verifying
    es.onmessage = function(e){ if(/now LIVE/i.test(e.data || "")) flipped = true; };
    let settled = false;
    const finish = function(){
      if(settled) return; settled = true;
      try{ es.close(); }catch(_){}
      if(ES === es) ES = null;
      resolve(flipped);
    };
    es.addEventListener("end", finish);
    es.onerror = finish;
    setTimeout(finish, 120000);               // safety: never hold the lock for ever
  });
}

// ---- the clock -------------------------------------------------------------
async function avTick(){
  if(AV_BUSY) return;
  const all = avLoad();
  if(!all.length){ avStop(); return; }
  // Only act on the account being looked at: the verify run is scoped to the
  // active account, so running it for another account's SKU would ask the wrong
  // Amazon account about a listing it has never heard of.
  const acc = avAccountId();
  if(!acc) return;
  const now = Date.now();
  AV_BUSY = true;
  try{
    for(const e of all.filter(x => String(x.account || "") === acc)){
      // Already live (a Sync, a manual re-verify, or an earlier tick got there
      // first) -> nothing left to wait for.
      if(avRowIsLive(e.sku)){ avForget(e.sku, e.account); _avRepaint(); continue; }
      const elapsed = now - Number(e.at || 0);
      let due = -1;
      for(let i = 0; i < AV_CHECKS.length; i++){
        if(elapsed >= AV_CHECKS[i] && (e.done || []).indexOf(i) < 0){ due = i; break; }
      }
      if(due >= 0){
        // Mark it attempted BEFORE the call, not after: a check that throws or
        // times out must not re-fire on every tick for ever.
        const list = avLoad();
        const cur = list.find(x => String(x.sku) === String(e.sku)
                                && String(x.account || "") === String(e.account || ""));
        if(cur){ cur.done = (cur.done || []).concat([due]); avSave(list); }
        const flipped = await avRunVerify(e.sku);
        if(flipped === null){ continue; }          // couldn't run; try next tick
        if(typeof loadRows === "function"){ try{ await loadRows(); }catch(_){} }
        if(flipped || avRowIsLive(e.sku)){
          avForget(e.sku, e.account);
          if(typeof toast === "function") toast(e.sku + " is now live on Amazon");
        }
        _avRepaint();
        continue;
      }
      // PAST THE DEADLINE AND STILL NOT LIVE. Say it once, plainly, and stop
      // checking -- a silent wait is what this whole file exists to end.
      if(elapsed >= AV_WARN_AT && !e.warned){
        const list = avLoad();
        const cur = list.find(x => String(x.sku) === String(e.sku)
                                && String(x.account || "") === String(e.account || ""));
        if(cur){ cur.warned = true; avSave(list); }
        if(typeof toast === "function"){
          toast("Amazon hasn't published " + e.sku + " yet — this is unusual, check Seller Central");
        }
        _avRepaint();
      }
    }
  } finally {
    AV_BUSY = false;
  }
}

function _avRepaint(){ try{ if(typeof render === "function") render(); }catch(e){} }

// ---- the ones the schedule has already given up on -------------------------

// When each SKU was last asked about, so returning to the screen does not re-ask
// immediately. Keyed by account so two accounts' SKUs cannot collide.
function avSeenLoad(){
  try{
    const raw = localStorage.getItem(AV_SEEN_KEY);
    const o = raw ? JSON.parse(raw) : {};
    return (o && typeof o === "object") ? o : {};
  }catch(e){ return {}; }
}
function avSeenSave(o){
  try{ localStorage.setItem(AV_SEEN_KEY, JSON.stringify(o || {})); }catch(e){}
}
function avSeenKey(sku){ return avAccountId() + "::" + String(sku || ""); }
function avAskedRecently(sku){
  const t = Number(avSeenLoad()[avSeenKey(sku)] || 0);
  return t > 0 && (Date.now() - t) < AV_STALE_COOLDOWN;
}
function avMarkAsked(sku){
  const o = avSeenLoad();
  o[avSeenKey(sku)] = Date.now();
  avSeenSave(o);
}

/* Every row we sent to Amazon that Amazon has not confirmed.
 *
 * lsIsWaitingOnAmazon (liststatus.js) is the one definition of that state --
 * SUBMITTED, and not in the catalogue Amazon returned. Asking it here rather
 * than testing r.status is what keeps this agreeing with the group heading and
 * the tab filter (CLAUDE.md Rule 12).
 */
function avWaitingRows(){
  if(typeof ROWS === "undefined" || !ROWS || !ROWS.filter) return [];
  if(typeof lsIsWaitingOnAmazon !== "function") return [];
  return ROWS.filter(r => r && r.sku && lsIsWaitingOnAmazon(r));
}

let AV_STALE_RUNNING = false;

/* Ask Amazon again about the listings the schedule has stopped chasing.
 *
 * Called when the listings finish loading. Serial on purpose: these run through
 * the same single run lock as a Preview, so firing them together would mean
 * every one after the first bailing out.
 */
async function avCheckStaleOnLoad(){
  if(AV_STALE_RUNNING) return;
  if(!avAccountId()) return;
  const due = avWaitingRows()
    .filter(r => !avAskedRecently(r.sku))
    .slice(0, AV_STALE_MAX);
  if(!due.length) return;
  AV_STALE_RUNNING = true;
  let flippedAny = false;
  try{
    for(const r of due){
      // Marked BEFORE the call, exactly as the scheduled path does: a check that
      // throws must not re-fire on the next load for ever.
      avMarkAsked(r.sku);
      const flipped = await avRunVerify(r.sku);
      if(flipped === null) continue;         // a run was in progress; leave it
      if(flipped) flippedAny = true;
    }
    // One reload for the whole batch, not one per listing.
    if(typeof loadRows === "function"){ try{ await loadRows(); }catch(_){} }
    if(flippedAny && typeof toast === "function"){
      toast("Amazon confirmed listings that were waiting — moved to Live");
    }
    _avRepaint();
  } finally {
    AV_STALE_RUNNING = false;
  }
}

function avStart(){
  if(AV_TIMER) return;
  AV_TIMER = setInterval(function(){
    // Don't poll Amazon for a tab nobody is looking at; the elapsed times are
    // absolute, so a backgrounded tab simply catches up when it returns.
    if(document.hidden) return;
    avTick();
  }, AV_TICK);
}
function avStop(){ if(AV_TIMER){ clearInterval(AV_TIMER); AV_TIMER = null; } }

// ---- the group on screen ---------------------------------------------------
// "Submitted — waiting on Amazon": the listings that HAVE been sent and are not
// live yet. Filed under Drafts they read as never-sent, which is the confusion
// this group removes.
/* WHAT AMAZON ACTUALLY SAID ABOUT THIS SKU, if anything.
 *
 * The verify run writes its answer into the row's Notes -- "RE-VERIFIED -- not
 * yet confirmed live; Amazon still shows 2 issue(s): ...". That sentence has
 * been written for as long as the verify mode has existed and has never been
 * shown anywhere: the group printed "sent 4 min ago" and nothing else, so a
 * listing Amazon was refusing looked exactly like one still in the queue.
 *
 * Returns "" when there is no recorded answer, which is the honest state before
 * the first re-check comes back.
 */
function avAmazonSaid(sku){
  let r = null;
  try{
    r = (typeof ROWS !== "undefined" && ROWS.find)
      ? ROWS.find(x => String(x && x.sku) === String(sku)) : null;
  }catch(e){ r = null; }
  const note = String((r && r.notes) || "");
  if(!/RE-VERIFI/i.test(note)) return "";
  // The part after the marker is Amazon's own reason; the marker itself is
  // bookkeeping and says nothing to a reader.
  const said = note.replace(/^.*?RE-VERIFIED\s*--\s*/i, "").trim();
  return said || "";
}

function avWaitedFor(sku){
  const _esc = (typeof esc === "function") ? esc : (x => String(x == null ? "" : x));
  const said = avAmazonSaid(sku);
  const e = avEntryFor(sku);

  // AMAZON'S OWN WORDS WIN. Whatever the clock says, a recorded answer is the
  // thing that was actually asked for -- "if that was accepted or rejected i
  // should know the reason".
  if(said){
    const bad = /issue|error|refus|reject|fail/i.test(said);
    return '<span style="color:' + (bad ? 'var(--red)' : 'var(--ink2)') + '" '
         + 'title="Amazon\'s own answer, recorded by the last check">'
         + (bad ? 'Amazon: ' : 'Amazon: ') + _esc(said) + '</span>';
  }

  if(!e){
    // Sent, nothing recorded back yet, and no live clock -- typically a listing
    // from a previous day, which the on-load check is about to ask about.
    return '<span class="cc">sent — waiting on Amazon’s answer; '
         + 'this app is re-checking.</span>';
  }
  const mins = Math.max(0, Math.round((Date.now() - Number(e.at || 0)) / 60000));
  if(e.warned){
    return '<span style="color:var(--red)">Amazon hasn’t published yet — this is '
         + 'unusual, check Seller Central.</span>';
  }
  return '<span class="cc">sent ' + (mins < 1 ? "just now" : (mins + " min ago"))
       + ' — Amazon usually publishes within 5–30 min.</span>';
}

function submittedGroupHtml(rows){
  if(!rows || !rows.length) return "";
  const n = rows.length;
  const anyWarned = rows.some(function(r){
    const e = avEntryFor(r && r.sku); return !!(e && e.warned);
  });
  const block = (typeof listBlock === "function") ? listBlock(rows) : "";
  const lines = rows.map(function(r){
    const w = avWaitedFor(r && r.sku);
    return w ? ('<div style="margin-top:4px">' + ((typeof esc === "function") ? esc(String(r.sku)) : String(r.sku)) + ' — ' + w + '</div>') : "";
  }).join("");
  return '<div class="srcgroup">Submitted — waiting on Amazon</div>'
    + '<div class="cc" style="margin:-4px 0 12px;font-size:12px;line-height:1.6">'
    + n + ' listing' + (n > 1 ? 's have' : ' has') + ' been <b>accepted by Amazon</b> and '
    + (n > 1 ? 'are' : 'is') + ' not live yet. Amazon publishes in its own time, usually '
    + 'within 5–30 minutes. This app re-checks just after submitting, and again '
    + 'every time you open this screen, moving '
    + (n > 1 ? 'them' : 'it') + ' to <b>Live on Amazon</b> as soon as Amazon confirms. '
    + 'Whatever Amazon says is shown beside each one below.'
    + lines
    // ALWAYS OFFERED, not only after the 15-minute warning. The button was
    // hidden behind a flag that a listing older than one session never has, so
    // the listings most in need of a manual check were the ones that could not
    // be checked.
    + '<div style="margin-top:8px"><button class="mktbtn" onclick="avCheckStaleNow()">'
    + '<i class="ti ti-refresh"></i> Ask Amazon now</button>'
    + (anyWarned
        ? '<span class="cc" style="margin-left:8px">Amazon is taking longer than '
          + 'usual — Seller Central will have the detail.</span>'
        : "")
    + '</div>'
    + '</div>'
    + block;
}

/* The button's version of the same check: ignore the cooldown, ask now. */
function avCheckStaleNow(){
  const rows = avWaitingRows();
  if(!rows.length){
    if(typeof toast === "function") toast("Nothing is waiting on Amazon");
    return;
  }
  const o = avSeenLoad();
  rows.forEach(r => { delete o[avSeenKey(r.sku)]; });
  avSeenSave(o);
  if(typeof toast === "function"){
    toast("Asking Amazon about " + rows.length + " listing(s)…");
  }
  avCheckStaleOnLoad();
}

// Pick the schedule back up after a page refresh.
if(document.readyState !== "loading"){ if(avLoad().length) avStart(); }
else{ document.addEventListener("DOMContentLoaded", function(){ if(avLoad().length) avStart(); }); }
