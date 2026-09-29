/* static/js/pdp_images.js -- the product page's Images tab.
 *
 * ITS OWN FILE, not another thousand lines in pdp.js (CLAUDE.md Rule 7). pdp.js
 * calls pdpImagesTab(row) and knows nothing else about any of this.
 *
 * WHAT THIS SCREEN IS FOR
 * Amazon does not take "some images". It takes one picture per named SLOT --
 * MAIN, PT01..PT08, SWATCH -- and which slots exist differs by product type. So
 * the question is never "what images do I have", it is "what goes in each
 * slot", and the old tab could not answer it: it drew a row of thumbnails from
 * the source listing and left the rest to Submit.
 *
 * Four sections, top to bottom, in the order the job is done:
 *
 *   1  SLOTS         what Amazon will take for THIS product type, and what is
 *                    in each one now. Empty ones are the work.
 *   2  SOURCE        the competitor/supplier photographs already on the row.
 *   3  LIBRARY       what Image Studio has made, or been given, for this SKU.
 *   4  UPLOAD        a file from the computer.
 *
 * Two to four are the places a picture comes FROM; one is where it goes. Drag
 * from any of them onto a slot, or use the slot picker on the thumbnail.
 *
 * THE SLOTS COME FROM THE SCHEMA, NEVER FROM A LIST HERE (Rule 4)
 * /listing/image_slots reads getDefinitionsProductType and returns the image
 * attributes that type actually declares. A slot this app invented would be
 * rejected on Submit with a message about an attribute nobody recognises. If
 * the schema cannot be read the section says so and offers nothing, rather than
 * offering nine slots and hoping.
 *
 * NOTHING HERE IS A NEW ENDPOINT (Rule 12)
 *   /listing/image_slots   which slots exist, and what is in them live
 *   /edit  target=attr     assign a URL to a slot on the draft
 *   /media/list            the library
 *   /media/upload          save a file from the computer
 *   /media/delete          remove one from the library
 * All four already existed and are used by other screens; this is a different
 * arrangement of them, not a second implementation.
 *
 * ASSIGNING WRITES TO THE DRAFT, WHICH IS WHAT SUBMIT SENDS. It does not push
 * to Amazon. A live listing's slots are shown as Amazon holds them, and
 * changing one still goes through Submit like every other field -- one way for
 * a change to reach Amazon, not two.
 */

/* THE OWNER'S REDESIGN (PDP_REDESIGN_SPEC.md, 26 Sep 2026) turned the four
 * numbered sections into three plain ones:
 *
 *   SLOTS        a status line ("X of N slots filled"), Push to Amazon and
 *                Upload image beside it, and the slots as a 4-column grid with
 *                a × on each filled one. Upload now goes STRAIGHT into the next
 *                empty slot -- the numbered "Upload from your computer" section
 *                and the red "Remove main image" button are gone; the × is how
 *                a picture comes out.
 *   PICTURES     one horizontal strip with tabs -- eBay (N), Amazon (N), Library
 *                (N). Click a picture and it fills the NEXT EMPTY slot; "Fill
 *                empty slots" does that for every picture in the tab. No
 *                dropdown, no assign button. Drag onto a slot still works.
 *   GENERATE     four preset buttons (pdp_imagegen.js).
 *
 * THE NUMBER OF SLOTS IS STILL THE SCHEMA'S, not a fixed eight (Rule 4 -- see
 * below). The spec drew eight (Main, PT01-PT06, Swatch); a product type that
 * allows PT07 and PT08 gets them, and one that allows fewer is not offered a
 * slot Amazon would refuse.
 *
 * "NEXT EMPTY" is Main, then the numbered slots in order. The swatch is never
 * filled automatically: it is a colour sample, not a gallery picture, and a
 * product photo in it would be wrong. It can still be dragged on to.
 */

/* Per-SKU state. Rebuilt on open; nothing here survives a page load. */
let PDPI = {sku: "", slots: [], live: false, checked: false, note: "",
            productType: "", library: [], loading: false, err: "",
            dragUrl: "", comp: null, compTab: "ebay", compLoading: false};

/* ---- reading the row --------------------------------------------------- */

/* The draft's own slot assignments: {slot_key: url}.
 *
 * From r.attributes, which is what /edit writes and what Submit reads. NOT from
 * _rowImages(): that flattens the same attributes into an ordered list for a
 * thumbnail strip, and a list cannot say which slot a picture is in -- which is
 * the whole question here.
 */
function _pdpiAssigned(r){
  const out = {};
  let a = (r && r.attributes) || null;
  if(!a){
    try{ a = JSON.parse((r && r.attrs) || "{}"); }catch(e){ a = {}; }
  }
  Object.keys(a || {}).forEach(function(k){
    if(!/image_locator|image_url/i.test(k)) return;
    const v = a[k];
    const url = (typeof v === "string") ? v
              : (v && v.media_location) || (v && v.value)
              || (Array.isArray(v) && v.length ? (v[0].media_location || v[0].value || v[0]) : "");
    if(url) out[k] = String(url);
  });
  return out;
}

/* Every picture the row carries, whatever slot it is in. Section 2's stock. */
function _pdpiSourceImages(r){
  const seen = {}, out = [];
  const add = function(u, why){
    u = String(u || "").trim();
    if(!u || seen[u]) return;
    seen[u] = 1; out.push({url: u, why: why});
  };
  (typeof _rowImages === "function" ? _rowImages(r) : []).forEach(function(u){
    add(u, "on the listing");
  });
  // The eBay/supplier photograph the draft was built from, when the row still
  // carries it separately from the attributes.
  ["source_image", "image", "img", "main_image"].forEach(function(k){
    if(r && r[k]) add(r[k], "from the source listing");
  });
  return out;
}

/* ---- loading ----------------------------------------------------------- */

function _pdpiEmpty(sku, productType){
  return {sku: String(sku || ""), slots: [], live: false, checked: false,
          note: "", productType: String(productType || ""), library: [],
          loading: false, err: "", dragUrl: "", comp: null, compTab: "ebay",
          compLoading: false,
          // The account and marketplace this state was loaded for (pdpContext,
          // pdp.js). The same SKU in another context is another listing.
          ctx: (typeof pdpContext === "function") ? pdpContext() : ""};
}

/* Forget the tab's state. shell.js calls this (through pdpLeaveContext) when
 * the account or marketplace changes. A load still in flight then writes into
 * the object it started with, not into this new one (see `mine` below). */
function pdpImagesForget(){ PDPI = _pdpiEmpty("", ""); }

async function pdpImagesLoad(sku, productType){
  PDPI = _pdpiEmpty(sku, productType);
  PDPI.loading = true;
  PDPI.compLoading = true;
  const mine = PDPI;
  _pdpiPaint();
  // The calls are independent -- the slot list from Amazon's schema, the
  // library from disk, the competitor's pictures from eBay and the catalogue --
  // so none waits on another. The slots are what the tab cannot draw without;
  // the competitor strip fills in when it arrives.
  _pdpiLoadCompetitor().then(function(){ if(PDPI === mine) _pdpiPaint(); });
  await Promise.all([_pdpiLoadSlots(), _pdpiLoadLibrary()]);
  if(PDPI !== mine) return;                  // another listing or context since
  PDPI.loading = false;
  _pdpiPaint();
}

/* The competitor's pictures, from /listing/competitor_images: eBay and Amazon
 * kept apart, each with its own reason when it could not be read. */
async function _pdpiLoadCompetitor(){
  // WRITES GO TO THE STATE THIS LOAD STARTED WITH. Comparing the SKU was not
  // enough: after an account switch the same SKU is reopened for the other
  // account, and the old account's answer would have landed in it.
  const mine = PDPI;
  const sku = mine.sku;
  mine.compLoading = true;
  try{
    const url = "/listing/competitor_images?sku=" + encodeURIComponent(sku)
              + ((typeof acctId === "function" && acctId())
                  ? "&account=" + encodeURIComponent(acctId()) : "");
    const j = await (await fetch(url)).json();
    if(PDPI !== mine) return;                // another listing or context meanwhile
    mine.comp = (j && j.ok) ? j
      : {ebay: [], amazon: [], ebay_error: (j && j.error) || "could not read",
         amazon_error: (j && j.error) || "could not read"};
    // Start on whichever tab has pictures, eBay first as the generator does.
    if(!(mine.comp.ebay || []).length && (mine.comp.amazon || []).length) mine.compTab = "amazon";
  }catch(e){
    if(PDPI === mine) mine.comp = {ebay: [], amazon: [], ebay_error: String(e), amazon_error: String(e)};
  }finally{
    if(PDPI === mine) mine.compLoading = false;
  }
}

async function _pdpiLoadSlots(){
  const mine = PDPI;
  try{
    const qs = "sku=" + encodeURIComponent(mine.sku)
             + (mine.productType ? "&product_type=" + encodeURIComponent(mine.productType) : "");
    const j = await (await fetch("/listing/image_slots?" + qs)).json();
    if(PDPI !== mine) return;
    if(!j || !j.ok){ mine.err = (j && j.error) || "could not read the slots"; return; }
    mine.slots = j.slots || [];
    mine.live = !!j.live;
    mine.checked = !!j.checked;
    mine.note = j.note || "";
    if(j.product_type) mine.productType = j.product_type;
  }catch(e){ if(PDPI === mine) mine.err = String(e); }
}

async function _pdpiLoadLibrary(){
  const mine = PDPI;
  try{
    const j = await (await fetch("/media/list?sku=" + encodeURIComponent(mine.sku))).json();
    if(PDPI !== mine) return;
    // THE SHAPE /media/list ACTUALLY RETURNS, read off the route rather than
    // assumed:
    //
    //   {ok: true, folders: [{sku, count, files: [{name, url, width, height,
    //                                              bytes, made_at, group}]}]}
    //
    // The first draft of this read j.items and would have shown an empty
    // library for ever, which is the same shape of bug as the thumbnail that
    // read only summaries.mainImage -- a guess at somebody else's payload.
    const out = [];
    ((j && j.folders) || []).forEach(function(g){
      ((g && g.files) || []).forEach(function(f){
        if(f && f.url){
          out.push({url: String(f.url),
                    name: f.name || String(f.url).split("/").pop(),
                    group: f.group || ""});
        }
      });
    });
    mine.library = out;
  }catch(e){ if(PDPI === mine) mine.library = []; }
}

/* RE-READ THE LIBRARY FROM OUTSIDE THIS FILE -- for the AI generator (doGen in
 * autofix.js), which saves each result into this SKU's media folder. Only the
 * tab's own upload and delete re-read it, so a generated picture did not appear
 * in "Image library" until a different listing was opened. A no-op unless this
 * tab is showing that SKU; repaints #pdpimages only, which does not contain the
 * generator, so a preview still being looked at is left alone. */
async function pdpImagesLibraryReload(sku){
  if(!PDPI.sku || PDPI.sku !== String(sku || "")) return;
  await _pdpiLoadLibrary();
  _pdpiPaint();
}

/* ---- assigning --------------------------------------------------------- */

/* Put one URL in one slot on the DRAFT, through the same /edit every other
 * field uses. Empty url clears the slot. */
async function pdpImgAssign(slotKey, url, opts){
  opts = opts || {};
  const sku = PDPI.sku;
  if(!sku || !slotKey) return false;
  try{
    const body = (typeof acctBody === "function")
      ? acctBody({sku: sku, target: "attr", key: slotKey, value: url || ""})
      : {sku: sku, target: "attr", key: slotKey, value: url || ""};
    const ctx = (typeof pdpContext === "function") ? pdpContext() : "";
    const j = await (await fetch("/edit", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)})).json();
    if(!j || !j.ok){ toast("Could not assign: " + ((j && j.error) || "unknown")); return false; }
    // The server saved it to the account named when it was sent. If the
    // account or marketplace has changed since, the row in ROWS with this SKU
    // is ANOTHER account's: leave it alone (pdpContext, pdp.js).
    if(typeof pdpContext === "function" && pdpContext() !== ctx) return true;
    // Keep the row in step the way saveEdit does, so the hero and the strip
    // redraw from the same values without a reload.
    const r = (typeof ROWS !== "undefined" && ROWS)
            ? ROWS.find(function(x){ return String(x.sku) === String(sku); }) : null;
    if(r){
      r.attributes = r.attributes || {};
      if(!url) delete r.attributes[slotKey]; else r.attributes[slotKey] = url;
      try{
        const a = JSON.parse(r.attrs || "{}");
        if(!url) delete a[slotKey]; else a[slotKey] = url;
        r.attrs = JSON.stringify(a);
      }catch(e){}
    }
    // `quiet` for a batch (Fill empty slots, a generated set): one toast and
    // one redraw at the end, not one per slot.
    if(!opts.quiet){
      toast(url ? ("Put in " + _pdpiSlotName(slotKey)) : "Slot cleared");
      if(typeof pdpRender === "function") pdpRender();
    }
    return true;
  }catch(e){ toast("Could not assign: " + e); return false; }
}

function pdpImgClear(slotKey){ pdpImgAssign(slotKey, ""); }

/* ---- next empty slot ---------------------------------------------------- */

/* The slots a picture may be put into AUTOMATICALLY, in order: Main, then
 * the numbered slots in order. The swatch is left out (see the note at the
 * top). The slots themselves are whatever the schema declared. */
function _pdpiGallerySlots(){
  const rank = function(k){
    if(k === "main_product_image_locator") return 0;
    const m = /^other_product_image_locator_(\d+)$/.exec(k);
    return m ? Number(m[1]) : 999;
  };
  return (PDPI.slots || [])
    .filter(function(s){ return rank(s.key) < 999; })
    .sort(function(a, b){ return rank(a.key) - rank(b.key); });
}

/* Empty means nothing in the draft AND nothing Amazon is showing there: a slot
 * that says "on Amazon" is not free, and filling it would replace a live
 * picture without anyone deciding to. */
function _pdpiEmptySlots(){
  const assigned = _pdpiAssignedNow();
  return _pdpiGallerySlots().filter(function(s){ return !assigned[s.key] && !s.current; });
}

/* Put one picture in the next empty slot. */
async function pdpImgFillNext(url){
  const free = _pdpiEmptySlots();
  if(!free.length){
    toast("Every slot is full — take a picture out with its × first.");
    return;
  }
  await pdpImgAssign(free[0].key, url);
}

/* Put every picture in the current tab into the empty slots, in order. A
 * picture already in a slot is skipped, so pressing it twice does not fill the
 * listing with copies. */
async function pdpImgFillAll(){
  const assigned = _pdpiAssignedNow();
  const inUse = {};
  Object.keys(assigned).forEach(function(k){ inUse[assigned[k]] = 1; });
  const pics = _pdpiStripPictures().filter(function(u){ return !inUse[u]; });
  const free = _pdpiEmptySlots();
  if(!free.length){ toast("Every slot is full — nothing to fill."); return; }
  if(!pics.length){ toast("No pictures here that are not already in a slot."); return; }
  let n = 0;
  for(let i = 0; i < free.length && i < pics.length; i++){
    if(await pdpImgAssign(free[i].key, pics[i], {quiet: true})) n++;
  }
  toast(n + " slot" + (n === 1 ? "" : "s") + " filled.");
  if(typeof pdpRender === "function") pdpRender();
}

function pdpImgCompTab(t){ PDPI.compTab = t; _pdpiPaint(); }

/* The pictures the strip is showing now. */
function _pdpiStripPictures(){
  if(PDPI.compTab === "library"){
    return (PDPI.library || []).map(function(f){ return f.url; });
  }
  const c = PDPI.comp || {};
  return (PDPI.compTab === "amazon" ? c.amazon : c.ebay) || [];
}

/* WHAT A SLOT IS CALLED ON SCREEN -- the one place (Rule 12).
 *
 * The slot picker and the slot cards read `s.name || s.key`, but
 * /listing/image_slots sends `label`, never `name` (listing/images.py), so
 * both showed the raw attribute key: "main_product_image_locator". The
 * families Seller Central names are named its way -- Main, PT01..PTnn,
 * Swatch; anything else the product type defines keeps the label the server
 * gave it (its schema title), and the key only when there is none. */
function _pdpiSlotName(key){
  key = String(key || "");
  if(key === "main_product_image_locator") return "Main";
  if(key === "swatch_product_image_locator") return "Swatch";
  const m = /^other_product_image_locator_(\d+)$/.exec(key);
  if(m) return "PT" + (m[1].length < 2 ? "0" + m[1] : m[1]);
  const s = (PDPI.slots || []).find(function(x){ return x.key === key; });
  return (s && (s.label || s.name)) || key;
}

/* The slot picker on a thumbnail. Only slots this product type HAS, and the
 * occupied ones say so rather than being hidden -- replacing a picture is a
 * legitimate thing to want, and a dropdown that silently omits the slot you
 * are looking for is worse than one that warns. */
/* _pdpiSlotOptions() removed with the card view: nothing calls it any more. */

function _pdpiAssignedNow(){
  const r = (typeof pdpRow === "function") ? pdpRow() : null;
  return r ? _pdpiAssigned(r) : {};
}

/* pdpImgPick() removed with the card view: nothing calls it any more. */

/* ---- drag and drop ----------------------------------------------------- */

function pdpImgDragStart(ev, url){
  PDPI.dragUrl = String(url || "");
  try{ ev.dataTransfer.setData("text/plain", PDPI.dragUrl);
       ev.dataTransfer.effectAllowed = "copy"; }catch(e){}
}
function pdpImgDragOver(ev){
  ev.preventDefault();
  try{ ev.dataTransfer.dropEffect = "copy"; }catch(e){}
  if(ev.currentTarget && ev.currentTarget.classList) ev.currentTarget.classList.add("over");
}
function pdpImgDragLeave(ev){
  if(ev.currentTarget && ev.currentTarget.classList) ev.currentTarget.classList.remove("over");
}
function pdpImgDrop(ev, slotKey){
  ev.preventDefault();
  if(ev.currentTarget && ev.currentTarget.classList) ev.currentTarget.classList.remove("over");
  let url = "";
  try{ url = ev.dataTransfer.getData("text/plain"); }catch(e){}
  url = url || PDPI.dragUrl;
  if(url) pdpImgAssign(slotKey, url);
}

/* ---- upload ------------------------------------------------------------ */

async function pdpImgUpload(input){
  const f = input && input.files && input.files[0];
  if(!f) return;
  if(!/^image\//.test(f.type || "")){ toast("That is not an image file."); return; }
  const reader = new FileReader();
  reader.onload = async function(){
    try{
      const j = await (await fetch("/media/upload", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({sku: PDPI.sku, data: reader.result,
                              name: f.name, kind: "ref"})})).json();
      if(!j || !j.ok || !j.url){
        toast("Upload failed: " + ((j && j.error) || "unknown")); return;
      }
      // STRAIGHT INTO THE NEXT EMPTY SLOT (the redesign merged upload into the
      // slots). With none free it waits in the Library tab, and says so.
      await _pdpiLoadLibrary();
      if(_pdpiEmptySlots().length){
        await pdpImgFillNext(j.url);
      }else{
        PDPI.compTab = "library";
        toast("Uploaded. Every slot is full, so it is in Library — take one out to use it.");
        _pdpiPaint();
      }
    }catch(e){ toast("Upload failed: " + e); }
  };
  reader.readAsDataURL(f);
  input.value = "";
}

function pdpImgDropUpload(ev){
  ev.preventDefault();
  if(ev.currentTarget && ev.currentTarget.classList) ev.currentTarget.classList.remove("over");
  const f = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0];
  if(!f) return;
  pdpImgUpload({files: [f], value: ""});
}

async function pdpImgLibDelete(url){
  // The account this was opened for, noted BEFORE the dialog below: if it
  // changed meanwhile (back/forward), nothing is sent (confirm-then-write audit).
  const _pinAcct = (typeof acctId === "function") ? acctId() : "";
  // uiConfirm, not the browser's confirm(). A native dialog freezes the whole
  // tab, cannot be styled, and says the page's hostname above the question --
  // on a screen the rest of which is this app's own. test_no_native_dialogs.py
  // has been failing on these two calls; they are the only ones left in the app.
  if(!await uiConfirm("Delete this image from the app's library? It is not "
            + "removed from Amazon, and any slot using it keeps the address.",
            {danger: true, ok: "Delete"})) return;
  try{
    if(typeof acctId === "function" && acctId() !== _pinAcct){
      if(typeof toast === "function") toast("The account changed while this was open, so nothing was done.");
      return;
    }
    const j = await (await fetch("/media/delete", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({url: url})})).json();
    if(!j || !j.ok){ toast("Could not delete: " + ((j && j.error) || "")); return; }
    await _pdpiLoadLibrary();
    _pdpiPaint();
  }catch(e){ toast("Could not delete: " + e); }
}

/* Take a source picture off the listing entirely: clear every slot holding it. */
/* pdpImgDropSource() removed with the card view: nothing calls it any more. */

/* ---- drawing ----------------------------------------------------------- */

function _pdpiSection(title, sub, body, right){
  return '<div class="pdpi-sec"><div class="pdpi-sechead">'
       + '<span class="pdpi-sect">' + esc(title) + '</span>'
       + (sub ? '<span class="pdpi-secsub">' + esc(sub) + '</span>' : "")
       + (right ? '<span class="pdpi-secright">' + right + '</span>' : "")
       + '</div>' + body + '</div>';
}

/* "X of N slots filled · these go live when you submit", with Push to Amazon
 * and Upload image beside it.
 *
 * PUSH TO AMAZON is pushImageLive (listings.js) -- the existing single-image
 * push of the MAIN picture to a live listing. It is offered only on a live
 * listing; on a draft there is nothing to push to, and everything in the slots
 * goes with Submit. */
function _pdpiStatusLine(){
  const all = PDPI.slots || [];
  const assigned = _pdpiAssignedNow();
  const filled = all.filter(function(s){ return assigned[s.key] || s.current; }).length;
  const push = PDPI.live
    ? '<button class="pdpi-btn" onclick="pushImageLive(' + jsArg(PDPI.sku) + ',this)"'
      + ' title="Send the main image to the live Amazon listing now — the image only, no resubmit">'
      + '<i class="ti ti-cloud-upload"></i> Push to Amazon</button>'
    : "";
  return '<div class="pdpi-status" title="Assigning writes to the draft — what Submit '
    + 'will send. It does not push to Amazon; only Push to Amazon does, for the main image.">'
    + '<i class="ti ti-photo"></i>'
    + '<span>' + filled + ' of ' + all.length + ' slots filled · '
    + (PDPI.live ? 'changes go live when you submit' : 'these go live when you submit')
    + '</span><span class="pdpi-grow"></span>' + push
    + '<label class="pdpi-btn" title="Upload a picture from your computer into the next empty slot">'
    +   '<i class="ti ti-upload"></i> Upload image'
    +   '<input type="file" accept="image/*" style="display:none" onchange="pdpImgUpload(this)">'
    + '</label></div>';
}

function _pdpiSlotsHtml(){
  if(PDPI.err){
    return '<div class="pdpi-note bad">' + esc(PDPI.err) + '</div>';
  }
  if(!PDPI.checked){
    return '<div class="pdpi-note bad">'
         + esc(PDPI.note || "This product type's schema could not be read, so "
                          + "which image slots Amazon allows is unknown. "
                          + "Nothing is guessed at here.")
         + '</div>';
  }
  if(!(PDPI.slots || []).length){
    return '<div class="pdpi-note">' + esc(PDPI.note
         || "This product type declares no image slots at all.") + '</div>';
  }
  const assigned = _pdpiAssignedNow();
  return _pdpiStatusLine() + '<div class="pdpi-slots">' + PDPI.slots.map(function(s){
    const draft = assigned[s.key] || "";
    const liveUrl = s.current || "";
    const url = draft || liveUrl;
    const onlyLive = !draft && !!liveUrl;
    return '<div class="pdpi-slot' + (url ? " filled" : "") + '"'
      + ' ondragover="pdpImgDragOver(event)" ondragleave="pdpImgDragLeave(event)"'
      + ' ondrop="pdpImgDrop(event,' + jsArg(s.key) + ')">'
      + '<div class="pdpi-slotimg">'
      +   (url ? '<img src="' + esc(url) + '" loading="lazy" onerror="this.remove()">'
               : '<i class="ti ti-plus"></i><span class="pdpi-empty">empty</span>')
      + '</div>'
      + '<div class="pdpi-slotname">' + esc(_pdpiSlotName(s.key)) + '</div>'
      + (onlyLive ? '<div class="pdpi-slotlive"><i class="ti ti-cloud"></i> on Amazon</div>' : "")
      // THE × IS HOW A PICTURE COMES OUT (it replaced the red "Remove main
      // image" button). Only on a draft value: Amazon's own picture is not the
      // draft's to clear -- a new one in the slot replaces it on Submit.
      + (draft ? '<button class="pdpi-slotx" title="Take this picture out of the slot"'
                 + ' onclick="pdpImgClear(' + jsArg(s.key) + ')"><i class="ti ti-x"></i></button>' : "")
      + '</div>';
  }).join("") + '</div>';
}

/* A URL inside an onclick attribute, quoted safely. */
// ONE escaper for a value inside an inline handler: jsArg, in users.js (Rule 12,
// Milestone 2). This name is kept for its callers.
function _pdpiArg(s){ return jsArg(s || ""); }

/* One ~72px picture in the strip. Click fills the next empty slot; it can also
 * be dragged onto a particular slot. No caption -- the long filenames went. */
function _pdpiThumb(url, extra){
  return '<div class="pdpi-thumb" draggable="true" title="Click to put it in the next empty slot, or drag it onto one"'
    + ' ondragstart="pdpImgDragStart(event,' + _pdpiArg(url) + ')"'
    + ' onclick="pdpImgFillNext(' + _pdpiArg(url) + ')">'
    + '<img src="' + esc(url) + '" loading="lazy"'
    +   ' onerror="this.parentNode.classList.add(\'bad\');this.remove()">'
    + (extra || "")
    + '</div>';
}

function _pdpiStripHtml(){
  const c = PDPI.comp || {};
  const tabs = [["ebay", "eBay", (c.ebay || []).length],
                ["amazon", "Amazon", (c.amazon || []).length],
                ["library", "Library", (PDPI.library || []).length]];
  const tabHtml = '<div class="pdpi-tabs">' + tabs.map(function(t){
    return '<button class="pdpi-tab' + (PDPI.compTab === t[0] ? " on" : "") + '"'
         + ' onclick="pdpImgCompTab(' + jsArg(t[0]) + ')">' + t[1]
         + ' <span class="pdpi-tabn">' + (PDPI.compLoading && t[0] !== "library" ? "…" : t[2]) + '</span></button>';
  }).join("") + '<span class="pdpi-grow"></span>'
    + '<button class="pdpi-btn" onclick="pdpImgFillAll()" title="Put these pictures into the empty slots, in order">'
    + '<i class="ti ti-layout-grid-add"></i> Fill empty slots</button></div>';

  const pics = _pdpiStripPictures();
  let body;
  if(PDPI.compTab !== "library" && PDPI.compLoading){
    body = '<div class="pdpi-note">Reading the competitor’s pictures…</div>';
  } else if(!pics.length){
    const why = PDPI.compTab === "library"
      ? "Nothing in the library for this SKU yet. Uploads and generated images land here."
      : ((PDPI.compTab === "amazon" ? c.amazon_error : c.ebay_error) || "No pictures from this source.");
    body = '<div class="pdpi-note">' + esc(why) + '</div>';
  } else {
    body = '<div class="pdpi-strip">' + pics.map(function(u){
      // A LIBRARY picture can be deleted from the app; a competitor's cannot.
      return _pdpiThumb(u, PDPI.compTab === "library"
        ? '<button class="pdpi-del" title="Delete from the app\'s library"'
          + ' onclick="event.stopPropagation();pdpImgLibDelete(' + _pdpiArg(u) + ')">'
          + '<i class="ti ti-trash"></i></button>' : "");
    }).join("") + '</div>';
  }
  return tabHtml + body
    + '<div class="pdpi-hint">Click an image → it fills the next empty slot. '
    + 'Or “Fill empty slots” to assign them all.</div>';
}


/* Repaint just this tab, without redrawing the whole page under it. */
function _pdpiPaint(){
  const host = document.getElementById("pdpimages");
  if(!host) return;
  const r = (typeof pdpRow === "function") ? pdpRow() : null;
  if(!r) return;
  host.innerHTML = _pdpiBody(r);
}

function _pdpiBody(r){
  if(PDPI.loading){
    return '<div class="pdpi-note">Reading this product type\'s image slots…</div>';
  }
  return _pdpiSection("Your slots", "what Amazon takes for "
                      + (PDPI.productType || "this product type"), _pdpiSlotsHtml())
       + _pdpiSection("Competitor pictures", "", _pdpiStripHtml());
}

/* THE ENTRY POINT pdp.js CALLS. Returns the tab's HTML immediately and loads
 * the slots behind it, because the schema call is a live Amazon read and a tab
 * that waits on it is a tab that looks broken for two seconds.
 *
 * The generator (pdp_imagegen.js) sits OUTSIDE #pdpimages, so repainting the
 * slots after an assignment never wipes instructions being typed or a run in
 * progress. */
function pdpImagesTab(r){
  const sku = String((r && r.sku) || "");
  const pt = String((r && (r.product_type || r.productType)) || "");
  const gen = (typeof pdpImgGenSection === "function") ? pdpImgGenSection(r) : "";
  // A different listing, OR the same SKU in another account / marketplace
  // (pdpContext): either way what is held is not this listing's.
  if(PDPI.sku !== sku
     || (typeof pdpContext === "function" && PDPI.ctx !== pdpContext())){
    setTimeout(function(){ pdpImagesLoad(sku, pt); }, 0);
    return '<div id="pdpimages" class="pdpi">'
         + '<div class="pdpi-note">Reading this product type\'s image slots…</div>'
         + '</div>' + gen;
  }
  return '<div id="pdpimages" class="pdpi">' + _pdpiBody(r) + '</div>' + gen;
}
