// static/js/listings_selection.js -- ticking rows and the batch actions that act on them. Moved word for word out of listings.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

function toggleSelect(sku, on){
  if(on) SELECTED.add(String(sku)); else SELECTED.delete(String(sku));
  // EVERY ELEMENT FOR THIS SKU, in whichever view is on screen. Both the card
  // and the table row carry data-sku, so one lookup serves both and a tick
  // looks like a tick either way.
  //
  // This looked for '.lcard', a class that does not exist anywhere in the app
  // -- cards are '.tile' -- so it had never matched and ticking a card only
  // appeared to work because something else redrew the list afterwards.
  document.querySelectorAll('[data-sku="' + CSS.escape(String(sku)) + '"]')
    .forEach(function(el){
      if(el.classList.contains("tile")) el.classList.toggle("sel", on);
      if(el.tagName === "TR") el.classList.toggle("rowon", on);
      const box = el.querySelector('input[type=checkbox]');
      if(box) box.checked = on;
    });
  updateSelBar();
}
/* WHAT IS ACTUALLY ON SCREEN, asked of the screen.
 *
 *     "i am not able to select all the listings by clicking on that white
 *      button ... only 2 listings are allowed to be selected when i select the
 *      live on amazon tab"
 *
 * Both of those are one bug. selectAllVisible walked ROWS -- the listings this
 * app holds -- while the Live on Amazon tab draws TWO collections: the app rows
 * Amazon confirmed, and LIVE_ITEMS, which is Amazon's own catalogue and is most
 * of that view. On the account this was reported from, two rows were in both
 * and everything else existed only in the catalogue, so "Select all" ticked
 * two listings out of a screenful and looked broken.
 *
 * Re-deriving the list here is what caused it: render() decides what to draw
 * from LIST_SOURCE, the filter, the dedupe between the two collections and the
 * live/claimed/gone split, and any second attempt at that answer is a copy that
 * can disagree -- and did. So this ASKS THE GRID. Every selectable listing is
 * drawn with a data-sku, whichever collection it came from, so reading them
 * back cannot drift from what a person can see.
 */
function visibleSelectableSkus(){
  const out = [], seen = new Set();
  document.querySelectorAll('#grid [data-sku]').forEach(function(el){
    // Only things that offer a tick. A container may carry data-sku for the
    // drawer without being selectable.
    if(!el.querySelector('input[type=checkbox]')) return;
    const s = String(el.getAttribute('data-sku') || "").trim();
    if(s && !seen.has(s)){ seen.add(s); out.push(s); }
  });
  return out;
}

function selectAllVisible(on){
  const skus = visibleSelectableSkus();
  // NOTHING DRAWN YET is not the same as nothing to select, and silently doing
  // nothing is exactly how this read as a dead button before.
  if(!skus.length){
    if(on && typeof toast === "function"){
      toast("Nothing on screen to select yet — let the list finish loading.");
    }
    return;
  }
  skus.forEach(function(s){
    if(on) SELECTED.add(s); else SELECTED.delete(s);
  });
  render(); updateSelBar();
}
function clearSelection(){ SELECTED.clear(); render(); updateSelBar(); }

/* HOW MANY OF THE SELECTION IS NOT ON THIS SCREEN.
 *
 *     "i selected 36 listings by going to first filter and select all and then
 *      set the handling time ... as 2 day handling time and got this message
 *      why"
 *
 * Because 46 were sent, not 36. SELECTED survives a change of tab and of
 * filter -- deliberately, so a selection can be built across pages -- and
 * selectAllVisible ADDS to it. Ten rows ticked in an earlier view were still in
 * it, so "select all" on a 36-listing tile acted on 46, and the reply's numbers
 * only made sense against a total he had never been shown: 13 saved + 33 with
 * no row = 46, and 36 pushed + 10 not live = 46.
 *
 * The selection is not narrowed -- carrying one across pages is the point of
 * it. It is COUNTED, so the bar says what is really about to happen.
 */
function selectedOffScreen(){
  if(typeof visibleSelectableSkus !== "function") return 0;
  let here;
  try{ here = new Set(visibleSelectableSkus()); }catch(e){ return 0; }
  if(!here.size) return 0;                 // nothing drawn yet: say nothing
  let n = 0;
  SELECTED.forEach(s => { if(!here.has(String(s))) n++; });
  return n;
}

/* The sentence every bulk action says when the selection reaches past the view.
 *
 * ONE SENTENCE, NOT FOUR. Handling, stock, price, Delete, Auto-fix and the GTIN
 * exemption all read the same SELECTED set and all inherit the same surprise.
 * Delete now removes a live listing FROM AMAZON and the exemption is a
 * declaration about the products, so this matters most on the two that cannot
 * be taken back -- and a copy of the warning per caller is how one of them ends
 * up without it (CLAUDE.md Rule 12).
 *
 * Returns "" when the selection is entirely on screen, so a caller can
 * concatenate it unconditionally.
 */
function selectionScopeNote(verb){
  const off = (typeof selectedOffScreen === "function") ? selectedOffScreen() : 0;
  if(!off) return "";
  return off + " of them " + (off === 1 ? "is" : "are") + " not in the view you "
       + "are looking at — a selection is kept as you move between tabs and "
       + "filters. Cancel and press Clear if that is not what you meant"
       + (verb ? (" before " + verb) : "") + ".\n\n";
}

function updateSelBar(){
  const bar=document.getElementById('selbar'); if(!bar) return;
  const n=SELECTED.size;
  bar.style.display = n? 'flex':'none';
  const cnt=document.getElementById('selcount');
  if(cnt){
    const off = selectedOffScreen();
    cnt.textContent = n + ' selected' + (off ? (' · ' + off + ' not in this view') : '');
    cnt.title = off
      ? ('A selection is kept as you move between tabs and filters, so ' + off
         + ' of these ' + (off === 1 ? 'is' : 'are') + ' not on screen now. '
         + 'Everything selected is acted on. Press Clear to start again.')
      : '';
  }
  // THE COUNT ON THE SUBMIT BUTTON, updated here because this is already the one
  // function that reacts to the selection changing. A second listener would be a
  // second answer to "how many are selected" (Rule 12), and the two would
  // disagree the first time either was touched.
  //
  // The NUMBER matters on this button and on no other in the bar: it is the one
  // that publishes to Amazon, and "Submit selected (23)" when you believed you
  // had ticked three is the moment to notice — a selection survives moving
  // between tabs, so the number and the screen genuinely can differ.
  const sub = document.getElementById('selsubmit');
  if(sub){
    sub.innerHTML = '<i class="ti ti-cloud-upload"></i> Submit selected ('
                  + n + ')';
  }
}
function selectedSkus(){ return Array.from(SELECTED); }

/* WHICH OF THESE HAS A DRAFT HERE, AND WHICH IS ONLY ON AMAZON.
 *
 * The Live view mixes two kinds of listing and always has: rows this app holds
 * a draft of, and rows that exist only in Amazon's catalogue. Until now only
 * the first kind could be ticked, so the question never came up.
 *
 * It comes up the moment both can be ticked. The bulk bar holds two families of
 * action and they want opposite halves of the selection:
 *
 *   about the DRAFT      Approve, Hold, Delete, Auto-fix, Regenerate copy
 *   about the LISTING    handling time, stock, price -- Amazon is the only place
 *                        these exist, so an Amazon-only row is a fine target
 *
 * Without this split a draft action posts every catalogue SKU to a route that
 * cannot find it and reports "46 failed" -- which reads as a broken app rather
 * than as forty-six listings that were never drafts. Nothing is destroyed by it
 * (/approve and /delete both answer "row not found"), but the message is a lie
 * about what happened.
 *
 * ONE DEFINITION, called by all of them (CLAUDE.md Rule 12). ROWS is the app's
 * own list, which is exactly what "holds a draft of" means.
 */
function splitByDraft(skus){
  const have = new Set((typeof ROWS !== "undefined" && ROWS ? ROWS : [])
                       .map(r => String(r.sku || "").trim()).filter(Boolean));
  const drafts = [], amazonOnly = [];
  (skus || []).forEach(function(s){
    (have.has(String(s).trim()) ? drafts : amazonOnly).push(s);
  });
  return {drafts: drafts, amazonOnly: amazonOnly};
}

/* The sentence a draft action shows when part of the selection was not a draft.
 * Written once so all four say the same thing, and returns "" when there is
 * nothing to say -- the ordinary all-drafts case stays silent.
 */
function _draftOnlyNote(amazonOnly, verb){
  if(!amazonOnly.length) return "";
  return `\n\n${amazonOnly.length} of them are on Amazon but have no draft here, `
       + `so there is nothing to ${verb}. They will be left alone.\n`
       + `(Press Sync to pull a listing in as a draft first.)`;
}

async function batchGenerate(kind){
  const skus=selectedSkus();
  if(!skus.length){ toast("Select some listings first"); return; }
  // Batch COPY regeneration runs through the generator with a --skus filter.
  // If your generator build doesn't have --skus yet, it will report that.
  if(!await uiConfirm("Regenerate listing copy for "+skus.length+" selected SKU(s)?\nThis reruns the generator scoped to just these SKUs.")) return;
  // THE navTo("generate") THAT WAS HERE IS GONE, and it was wrong before the
  // screen was retired: #log and #genui both live on the LISTINGS page, so
  // jumping to Generate hid the very output this function then wrote into. You
  // pressed Regenerate on selected rows and were taken to a screen showing
  // nothing. Staying put is both the fix and what the retirement requires --
  // there is no "generate" section to navigate to any more.
  //
  // THROUGH runMode, THE ONE PLACE A RUN IS STARTED. This opened its own
  // EventSource, and so missed everything runMode does:
  //   * it sent no account, so /run/regen rebuilt the copy on whichever account
  //     the server last had open -- the bug runMode was fixed for;
  //   * it never set ES, so the Stop entry in the run menu (genflow.js asks ES)
  //     never appeared while it ran;
  //   * and a second press while one was streaming started a second run,
  //     because runMode's "a run is already streaming" refusal is keyed on ES.
  // Not genflowGenerate(): that generates the upload QUEUE and ignores the
  // selection. It is itself a thin wrapper over runMode, which is what matters.
  if(typeof runMode === "function") runMode("regen", skus);
  else toast("Could not start: the run controls did not load — reload the page.");
}

async function batchAutoGenerate(kind){
  // Bulk one-click: strategize + generate in the BACKGROUND. Does NOT open the
  // studio — the floating status bar shows progress, results auto-save to each
  // product's media library, and it keeps running on any page. kind defaults to
  // 'secondary'; pass 'aplus' for the A+ button.
  kind=kind||"secondary";
  const skus=selectedSkus();
  if(!skus.length){ toast("Select some listings first"); return; }
  const per=(kind==="aplus")?7:7; // 7 secondary or up to 7 A+ modules
  const n=skus.length;
  if(!await uiConfirm("Auto-generate "+(kind==="aplus"?"A+ modules":"secondary images")+" for "+n+
              " product"+(n>1?"s":"")+" (~"+(n*per)+" images). The strategist proposes ideas and "+
              "generates them all in the background. You can keep working. Continue?")) return;

  const liveSel = (LIST_SOURCE==='live' || LIST_SOURCE==='all');
  toast("Designing concepts for each product…");
  // Strategize SEPARATELY for EACH product using its own reference image, so
  // every product gets concepts tailored to ITSELF — no shared/mixed set.
  let jobs=[];
  let skipped=[];
  for(let si=0; si<skus.length; si++){
    const sku=skus[si];
    const it=_itemForSku(sku);
    const ref=_refImgForItem(it);
    if(!ref){ skipped.push(sku); continue; }
    let concepts=[];
    try{
      const sj=await (await fetch("/genimage/strategize",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({product_image:ref,
          product_images:(typeof _refCandidates==="function"?_refCandidates(it):[ref]),
          title:(it&&it.title)||"", kind:kind,
          n:per, text_provider:(window.AI_TEXT||null)})})).json();
      if(!sj.ok){ toast("Strategist failed for "+sku+": "+(sj.error||"unknown")); continue; }
      concepts=sj.concepts||[];
    }catch(e){ toast("Strategist error for "+sku+": "+e); continue; }
    if(!concepts.length){ continue; }
    const asin=liveSel?_asinForSku(sku):"";
    concepts.forEach((c,ci)=>{
      const code=(kind==="aplus")
        ? ("APLUS"+String(ci+1).padStart(2,"0"))
        : ("PT"+String(ci+1).padStart(2,"0"));
      jobs.push({sku:sku, ref:ref, label:sku+" · "+(c.title||code),
        asin:asin, img_code:code,
        payload:{ product_image:ref, title:(it&&it.title)||"", kind:kind,
          concept:c.concept||"", art_direction:c.art_direction||"",
          fidelity:"high", tier:"basic",
          text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null) }});
    });
  }
  if(skipped.length){ toast(skipped.length+" product(s) skipped — no reference image: "+skipped.join(", ")); }
  if(!jobs.length){ toast("Nothing to generate — no products had reference images or concepts."); return; }

  // 3) submit as a background batch — no studio window, status bar tracks it
  try{
    const r=await (await fetch("/genimage/start_batch",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({kind:"concept", jobs:jobs, label:(kind==="aplus"?"A+ ":"Secondary ")+"× "+n+" product"+(n>1?"s":"")})})).json();
    if(!r.ok){ toast("Could not start: "+(r.error||"unknown")); return; }
    GEN_ACTIVE_JOB=r.job;
    toast("Started "+jobs.length+" image(s) in the background.");
    openGenPanel();
    startGenStatusPoll();
  }catch(e){ toast("Error: "+e); }
}
