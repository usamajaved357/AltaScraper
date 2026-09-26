// static/js/genflow.js -- the generation flow, folded above the drafts it makes.
//
//     "Redesign the listing generator page to remove clutter, clean up the
//      generation flow, and eliminate raw log/paragraph dumps. One page, three
//      collapsible sections that flow top to bottom."
//
// WHAT THIS FILE IS, AND MORE IMPORTANTLY WHAT IT IS NOT.
//
// It is the OPEN/CLOSE and the two buttons on the queue's header. That is all.
// It owns no upload, no validation, no queue rendering, no progress parsing and
// no generator call, because every one of those already exists and works:
//
//     inputupload.js   the drop zone, .csv/.tsv/.xlsx, and the error card that
//                      names the headers your file actually had
//     inputqueue.js    the queue table and the add-a-product form in it
//     genplan.js       the pre-flight "N to generate / N already made"
//     submit.js        the one EventSource, via runMode()
//     genui.js         the progress panel that replaced the raw log
//
// Re-implementing any of them here would be a second opinion about work that is
// already right (CLAUDE.md Rule 12), so this delegates to all five and adds
// nothing but the fold and the wiring.
//
// WHY THE QUEUE IS NOT EMPTIED BY AN UPLOAD.
// inputupload.js states the rule it was built to: "Uploads ADD. A second file
// adds to the first; nothing here can empty the queue." That is the safe way
// round -- dropping a second spreadsheet cannot silently discard the first
// one's rows -- so opening the panel does not clear anything either. Emptying
// is genflowClearQueue(), which asks first and says how many.

const GENFLOW = {open: false};

function _gfEl(){ return document.getElementById("genflow"); }

/* Reflect the panel's state on the toolbar button, so the button says whether
 * the thing it controls is open rather than leaving you to look. */
function _gfSyncBtn(){
  const b = document.getElementById("genflow_btn");
  if(!b) return;
  b.classList.toggle("on", !!GENFLOW.open);
}

function genflowOpen(){
  const el = _gfEl();
  if(!el) return;
  el.hidden = false;
  GENFLOW.open = true;
  _gfSyncBtn();
  // The queue and the pre-flight count are both read fresh on open. Neither
  // costs an Amazon or an AI call -- /input/rows reads this app's own table and
  // /run/plan runs the generator's duplicate rule -- and a stale count is
  // exactly the thing that would make the panel lie about what Generate does.
  try{ if(typeof inputQueueLoad === "function") inputQueueLoad(); }catch(e){}
  try{ if(typeof genplanLoad === "function") genplanLoad(); }catch(e){}
  try{ el.scrollIntoView({block: "nearest", behavior: "smooth"}); }catch(e){}
}

function genflowClose(){
  const el = _gfEl();
  if(!el) return;
  el.hidden = true;
  GENFLOW.open = false;
  _gfSyncBtn();
}

function genflowToggle(){
  if(GENFLOW.open) genflowClose(); else genflowOpen();
}

/* EMPTY THE QUEUE -- the deliberate click that an upload deliberately is not.
 *
 * It asks with the COUNT in the question, because "Clear queue?" and "Remove 64
 * products?" are different questions and only the second one can be answered.
 * Generated listings are not touched: this removes what is waiting to be made,
 * not what has been made. */
async function genflowClearQueue(){
  const n = (typeof IQ !== "undefined" && IQ && IQ.rows) ? IQ.rows.length : 0;
  if(!n){
    if(typeof toast === "function") toast("The queue is already empty.");
    return;
  }
  const ok = await uiConfirm("Remove all " + n + " product" + (n === 1 ? "" : "s")
    + " waiting to be generated?\n\nListings you have already generated are not "
    + "touched — this only empties the list of things still to make.");
  if(!ok) return;
  try{
    const r = await fetch("/input/clear" + (typeof scopeQs === "function" ? scopeQs() : ""),
                          {method: "POST", headers: {"Content-Type": "application/json"},
                           body: "{}"});
    const j = await r.json();
    if(!j || j.ok === false){
      if(typeof toast === "function") toast("Could not empty the queue: " + ((j && j.error) || "unknown"));
      return;
    }
    // THE SERVER'S COUNT, not the one this screen happened to be showing. They
    // differ whenever the queue changed since the last render, and the number in
    // a confirmation of something irreversible should be what actually happened.
    const gone = (j.removed == null) ? n : j.removed;
    if(typeof toast === "function") toast("Queue emptied — " + gone + " removed");
    if(typeof inputQueueLoad === "function") inputQueueLoad();
    if(typeof genplanLoad === "function") genplanLoad();
  }catch(e){
    if(typeof toast === "function") toast("Could not empty the queue: " + e);
  }
}

/* GENERATE. runMode('generate') in submit.js is the one place a run is started
 * and the one place the stream is opened; this only refuses to start an empty
 * one, which otherwise spends a request to be told there was nothing to do. */
function genflowGenerate(){
  const n = (typeof IQ !== "undefined" && IQ && IQ.rows) ? IQ.rows.length : 0;
  if(!n){
    if(typeof toast === "function"){
      toast("Nothing queued — drop a template above, or add a product, first.");
    }
    return;
  }
  if(typeof runMode === "function") runMode("generate");
}
