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

/* Per-SKU state. Rebuilt on open; nothing here survives a page load. */
let PDPI = {sku: "", slots: [], live: false, checked: false, note: "",
            productType: "", library: [], loading: false, err: "",
            dragUrl: ""};

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

async function pdpImagesLoad(sku, productType){
  PDPI = {sku: String(sku || ""), slots: [], live: false, checked: false,
          note: "", productType: String(productType || ""), library: [],
          loading: true, err: "", dragUrl: ""};
  _pdpiPaint();
  // The two calls are independent -- the slot list from Amazon's schema and the
  // library from disk -- so neither waits on the other.
  await Promise.all([_pdpiLoadSlots(), _pdpiLoadLibrary()]);
  PDPI.loading = false;
  _pdpiPaint();
}

async function _pdpiLoadSlots(){
  try{
    const qs = "sku=" + encodeURIComponent(PDPI.sku)
             + (PDPI.productType ? "&product_type=" + encodeURIComponent(PDPI.productType) : "");
    const j = await (await fetch("/listing/image_slots?" + qs)).json();
    if(!j || !j.ok){ PDPI.err = (j && j.error) || "could not read the slots"; return; }
    PDPI.slots = j.slots || [];
    PDPI.live = !!j.live;
    PDPI.checked = !!j.checked;
    PDPI.note = j.note || "";
    if(j.product_type) PDPI.productType = j.product_type;
  }catch(e){ PDPI.err = String(e); }
}

async function _pdpiLoadLibrary(){
  try{
    const j = await (await fetch("/media/list?sku=" + encodeURIComponent(PDPI.sku))).json();
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
    PDPI.library = out;
  }catch(e){ PDPI.library = []; }
}

/* ---- assigning --------------------------------------------------------- */

/* Put one URL in one slot on the DRAFT, through the same /edit every other
 * field uses. Empty url clears the slot. */
async function pdpImgAssign(slotKey, url){
  const sku = PDPI.sku;
  if(!sku || !slotKey) return;
  try{
    const body = (typeof acctBody === "function")
      ? acctBody({sku: sku, target: "attr", key: slotKey, value: url || ""})
      : {sku: sku, target: "attr", key: slotKey, value: url || ""};
    const j = await (await fetch("/edit", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)})).json();
    if(!j || !j.ok){ toast("Could not assign: " + ((j && j.error) || "unknown")); return; }
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
    toast(url ? ("Assigned to " + _pdpiSlotName(slotKey)) : "Slot cleared");
    if(typeof pdpRender === "function") pdpRender();
  }catch(e){ toast("Could not assign: " + e); }
}

function pdpImgClear(slotKey){ pdpImgAssign(slotKey, ""); }

function _pdpiSlotName(key){
  const s = (PDPI.slots || []).find(function(x){ return x.key === key; });
  return (s && (s.name || s.label)) || key;
}

/* The slot picker on a thumbnail. Only slots this product type HAS, and the
 * occupied ones say so rather than being hidden -- replacing a picture is a
 * legitimate thing to want, and a dropdown that silently omits the slot you
 * are looking for is worse than one that warns. */
function _pdpiSlotOptions(url){
  const assigned = _pdpiAssignedNow();
  let h = '<option value="">Assign to slot…</option>';
  (PDPI.slots || []).forEach(function(s){
    const holder = assigned[s.key];
    const taken = holder && holder !== url;
    h += '<option value="' + esc(s.key) + '">' + esc(s.name || s.key)
       + (taken ? " (replace)" : "") + '</option>';
  });
  return h;
}

function _pdpiAssignedNow(){
  const r = (typeof pdpRow === "function") ? pdpRow() : null;
  return r ? _pdpiAssigned(r) : {};
}

function pdpImgPick(sel, url){
  const slot = sel && sel.value;
  if(!slot) return;
  sel.value = "";
  pdpImgAssign(slot, url);
}

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
      toast("Uploaded — now assign it to a slot.");
      await _pdpiLoadLibrary();
      _pdpiPaint();
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
  // uiConfirm, not the browser's confirm(). A native dialog freezes the whole
  // tab, cannot be styled, and says the page's hostname above the question --
  // on a screen the rest of which is this app's own. test_no_native_dialogs.py
  // has been failing on these two calls; they are the only ones left in the app.
  if(!await uiConfirm("Delete this image from the app's library? It is not "
            + "removed from Amazon, and any slot using it keeps the address.",
            {danger: true, ok: "Delete"})) return;
  try{
    const j = await (await fetch("/media/delete", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({url: url})})).json();
    if(!j || !j.ok){ toast("Could not delete: " + ((j && j.error) || "")); return; }
    await _pdpiLoadLibrary();
    _pdpiPaint();
  }catch(e){ toast("Could not delete: " + e); }
}

/* Take a source picture off the listing entirely: clear every slot holding it. */
async function pdpImgDropSource(url){
  const assigned = _pdpiAssignedNow();
  const keys = Object.keys(assigned).filter(function(k){ return assigned[k] === url; });
  if(!keys.length){ toast("That picture is not in any slot."); return; }
  if(!await uiConfirm("Remove this picture from " + keys.length + " slot"
            + (keys.length === 1 ? "" : "s") + "? The picture stays in the "
            + "library; only this listing's slots are cleared.",
            {ok: "Remove"})) return;
  for(let i = 0; i < keys.length; i++) await pdpImgAssign(keys[i], "");
}

/* ---- drawing ----------------------------------------------------------- */

function _pdpiSection(n, title, sub, body){
  return '<div class="pdpi-sec"><div class="pdpi-sechead">'
       + '<span class="pdpi-secn">' + n + '</span>'
       + '<span class="pdpi-sect">' + esc(title) + '</span>'
       + (sub ? '<span class="pdpi-secsub">' + esc(sub) + '</span>' : "")
       + '</div>' + body + '</div>';
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
  return '<div class="pdpi-slots">' + PDPI.slots.map(function(s){
    const draft = assigned[s.key] || "";
    const liveUrl = s.current || "";
    const url = draft || liveUrl;
    const onlyLive = !draft && !!liveUrl;
    return '<div class="pdpi-slot' + (url ? " filled" : "") + '"'
      + ' ondragover="pdpImgDragOver(event)" ondragleave="pdpImgDragLeave(event)"'
      + ' ondrop="pdpImgDrop(event,\'' + esc(s.key) + '\')">'
      + '<div class="pdpi-slotimg">'
      +   (url ? '<img src="' + esc(url) + '" loading="lazy" onerror="this.remove()">'
               : '<i class="ti ti-photo-plus"></i>')
      + '</div>'
      + '<div class="pdpi-slotname">' + esc(s.name || s.key) + '</div>'
      + (onlyLive ? '<div class="pdpi-slotlive">on Amazon</div>' : "")
      + (draft ? '<button class="pdpi-slotx" title="Take this picture out of '
                 + 'the slot" onclick="pdpImgClear(\'' + esc(s.key) + '\')">'
                 + '<i class="ti ti-x"></i></button>' : "")
      + '</div>';
  }).join("") + '</div>'
  + (PDPI.live ? "" : '<div class="pdpi-note">'
      + 'This listing is not on Amazon yet, so no slot can show what Amazon '
      + 'holds — what you assign here is what Submit will send.</div>');
}

function _pdpiThumb(url, caption, extra){
  return '<div class="pdpi-thumb" draggable="true"'
    + ' ondragstart="pdpImgDragStart(event,' + _pdpiArg(url) + ')">'
    + '<div class="pdpi-thumbimg"><img src="' + esc(url) + '" loading="lazy"'
    +   ' onerror="this.parentNode.innerHTML=\'<i class=&quot;ti ti-photo-off&quot;></i>\'"></div>'
    + '<div class="pdpi-thumbcap">' + esc(caption || "") + '</div>'
    + '<select class="pdpi-pick" onchange="pdpImgPick(this,' + _pdpiArg(url) + ')">'
    +   _pdpiSlotOptions(url) + '</select>'
    + (extra || "")
    + '</div>';
}

/* A URL inside an onclick attribute, quoted safely. */
function _pdpiArg(s){
  return "'" + String(s || "").replace(/\\/g, "\\\\").replace(/'/g, "\\'")
                              .replace(/"/g, "&quot;") + "'";
}

function _pdpiSourceHtml(r){
  const imgs = _pdpiSourceImages(r);
  if(!imgs.length){
    return '<div class="pdpi-note">No source pictures on this row.</div>';
  }
  return '<div class="pdpi-row">' + imgs.map(function(im){
    return _pdpiThumb(im.url, im.why,
      '<button class="pdpi-del" title="Take this picture out of every slot it '
      + 'is in" onclick="pdpImgDropSource(' + _pdpiArg(im.url) + ')">'
      + '<i class="ti ti-trash"></i></button>');
  }).join("") + '</div>';
}

function _pdpiLibraryHtml(){
  if(!(PDPI.library || []).length){
    return '<div class="pdpi-note">Nothing in the library for this SKU yet. '
         + 'Image Studio saves here, and so does the upload below.</div>';
  }
  return '<div class="pdpi-row">' + PDPI.library.map(function(f){
    return _pdpiThumb(f.url, f.name,
      '<button class="pdpi-del" title="Delete from the app\'s library" '
      + 'onclick="pdpImgLibDelete(' + _pdpiArg(f.url) + ')">'
      + '<i class="ti ti-trash"></i></button>');
  }).join("") + '</div>';
}

function _pdpiUploadHtml(){
  return '<label class="pdpi-drop" ondragover="pdpImgDragOver(event)"'
    + ' ondragleave="pdpImgDragLeave(event)" ondrop="pdpImgDropUpload(event)">'
    + '<i class="ti ti-cloud-upload"></i>'
    + '<span>Drop an image here, or click to choose one</span>'
    + '<input type="file" accept="image/*" style="display:none"'
    +   ' onchange="pdpImgUpload(this)">'
    + '</label>';
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
  return _pdpiSection(1, "Image slots", "what Amazon takes for "
                      + (PDPI.productType || "this product type"),
                      _pdpiSlotsHtml())
       + _pdpiSection(2, "Source pictures", "from the listing this was built from",
                      _pdpiSourceHtml(r))
       + _pdpiSection(3, "Image library", "made or saved by this app",
                      _pdpiLibraryHtml())
       + _pdpiSection(4, "Upload from your computer", "",
                      _pdpiUploadHtml());
}

/* THE ENTRY POINT pdp.js CALLS. Returns the tab's HTML immediately and loads
 * the slots behind it, because the schema call is a live Amazon read and a tab
 * that waits on it is a tab that looks broken for two seconds. */
function pdpImagesTab(r){
  const sku = String((r && r.sku) || "");
  const pt = String((r && (r.product_type || r.productType)) || "");
  if(PDPI.sku !== sku){
    setTimeout(function(){ pdpImagesLoad(sku, pt); }, 0);
    return '<div id="pdpimages" class="pdpi">'
         + '<div class="pdpi-note">Reading this product type\'s image slots…</div>'
         + '</div>';
  }
  return '<div id="pdpimages" class="pdpi">' + _pdpiBody(r) + '</div>';
}
