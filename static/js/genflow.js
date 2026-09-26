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
  // THE DROP ZONE ITSELF, drawn here.
  //
  // inputupload.js renders into whatever container it is given, and the only
  // thing that ever gave it one was shell.js's sec==="generate" branch. When the
  // markup moved to this page that branch stopped running, so #inputupload was
  // an EMPTY DIV: the panel opened, the queue loaded under it, and there was
  // nowhere to drop a file. Nothing threw -- an empty container is not an error
  // -- which is exactly why it needs drawing from the code that opens the panel
  // rather than from a section hook that may or may not fire.
  //
  // Once, not on every open: the zone holds the last upload's result card, and
  // redrawing would wipe the report saying what a file just did.
  try{
    if(typeof inputUploadPanel === "function"){
      const iu = document.getElementById("inputupload");
      if(iu && !iu.innerHTML.trim()) iu.innerHTML = inputUploadPanel();
    }
  }catch(e){}
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

/* ===== THE DEMOTED RUN ACTIONS =====
 *
 * Retry holds, Export, Preview, Submit and Stop were a permanent bar of six on
 * the generate screen. The spec calls them "rarely used but should not be
 * deleted", and it is right on both counts -- Preview is the only way to check
 * a draft against Amazon WITHOUT sending it, and Stop is the only way to end a
 * run -- so they are behind one button rather than gone.
 *
 * It reuses the .tilemenu the listing rows already use: the same element, the
 * same class, the same dismiss-on-next-click. A second dropdown implementation
 * would be a second thing to style and a second thing to get wrong (Rule 12).
 *
 * EVERY ITEM HERE CALLS THE FUNCTION IT ALWAYS CALLED. Nothing about what these
 * five DO changes; only where you press them.
 */
/* ONE TOOLBAR DROPDOWN, used by the ⋯ menu and by Costs ▾.
 *
 * Opening, placing and dismissing a menu was written out inside
 * genflowRunMenu. The redesign added a second toolbar dropdown (Costs ▾), and a
 * second copy of this would be a second thing to get wrong (Rule 12) -- so the
 * mechanics live here and both menus pass in only their buttons.
 *
 * Same element id as before, so only one toolbar menu is ever open and
 * closeRunMenu() closes whichever it is.
 */
function openToolbarMenu(ev, html){
  ev.stopPropagation();
  closeRunMenu();
  if(typeof closeTileMenu === "function") closeTileMenu();
  const m = document.createElement("div");
  m.className = "tilemenu";
  m.id = "runmenu";
  m.innerHTML = html;
  document.body.appendChild(m);
  const btn = ev.target.closest("button");
  const rect = btn.getBoundingClientRect();
  m.style.top = (rect.bottom + 4) + "px";
  // Kept on screen: a menu at the end of the toolbar would otherwise hang off
  // the right edge of the page.
  m.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - m.offsetWidth - 8)) + "px";
  setTimeout(function(){
    document.addEventListener("click", closeRunMenu, {once: true});
  }, 0);
}

/* The buttons of a <template> in dashboard.html, as HTML. The markup stays in
 * the template (HTML belongs in templates/), and "" if it is missing, so a menu
 * never throws over one absent group. */
function _tplHtml(id){
  const t = document.getElementById(id);
  return t ? t.innerHTML : "";
}

/* A toolbar dropdown whose buttons are entirely one template (Costs ▾). */
function toolbarMenu(ev, tplId){
  openToolbarMenu(ev, _tplHtml(tplId));
}

function genflowRunMenu(ev){
  // Stop is only offered while something is running -- an enabled Stop with
  // nothing to stop is a button that does nothing, which is worse than absent.
  //
  // ASKED OF THE STREAM, not of a button. This read #stopbtn's disabled state,
  // and #stopbtn lived on the Generate screen -- which has now gone, so that
  // test would have been permanently false and Stop would never have appeared
  // again. ES is the EventSource itself (declared in howworks.js, shared scope):
  // non-null exactly while a run is streaming, which is the thing being asked
  // about rather than a button that happens to reflect it.
  const running = (typeof ES !== "undefined") && !!ES;
  // The tools moved off the toolbar first, the run actions in the middle, and
  // the one destructive action last (templates in dashboard.html).
  const tools = _tplHtml("tpl_more_tools"), danger = _tplHtml("tpl_more_danger");
  openToolbarMenu(ev,
      (tools ? tools + '<div class="tmsep"></div>' : '')
    + '<button onclick="closeRunMenu();runMode(\'retry\')"'
    + ' title="Re-run the products that were held or refused last time. Writes into this app only."'
    + '><i class="ti ti-refresh"></i> Retry holds</button>'
    + '<button onclick="closeRunMenu();runMode(\'export\')"'
    + ' title="Download the drafts as an Amazon flat file (.xlsm). Sends nothing."'
    + '><i class="ti ti-file-spreadsheet"></i> Export .xlsm</button>'
    + '<button onclick="closeRunMenu();runMode(\'api\')"'
    + ' title="Check the drafts against Amazon and show what it says. Creates nothing."'
    + '><i class="ti ti-eye-check"></i> Preview against Amazon</button>'
    + '<button class="danger" onclick="closeRunMenu();submitLive()"'
    + ' title="Publish to Amazon. Shows the destination account and asks first."'
    + '><i class="ti ti-cloud-upload"></i> Submit · go live</button>'
    + (running
        ? '<button class="danger" onclick="closeRunMenu();stopRun()"'
          + '><i class="ti ti-player-stop"></i> Stop the run</button>'
        : '')
    + (danger ? '<div class="tmsep"></div>' + danger : ''));
}

function closeRunMenu(){
  const m = document.getElementById("runmenu");
  if(m) m.remove();
}

/* GENERATE. runMode('generate') in submit.js is the one place a run is started
 * and the one place the stream is opened; this only refuses to start an empty
 * one, which otherwise spends a request to be told there was nothing to do. */
function genflowGenerate(){
  const n = (typeof IQ !== "undefined" && IQ && IQ.rows) ? IQ.rows.length : 0;
  if(!n){
    if(typeof toast === "function"){
      toast("Nothing queued — press Upload template and drop a spreadsheet first.");
    }
    return;
  }
  if(typeof runMode === "function") runMode("generate");
}
