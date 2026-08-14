/* listingimages.js — a listing's images, in one place.
 *
 * WHAT WAS MISSING
 * The app generated images and filed them under each SKU, but there was no way
 * to SEE a listing's images from the listing, choose which one is the main, or
 * upload your own. The images existed and were unreachable.
 *
 * RULE 12 FIRST
 * "Make this the main image" was implemented FOUR times before this file:
 *   autofix.js  uploadMainImage()   POST /edit  main_product_image_locator
 *   autofix.js  applyGen()          POST /edit  main_product_image_locator
 *   miles_template.js milesApply()  POST /edit  main_product_image_locator
 *   settings.js genApply()          POST /edit  main_product_image_locator
 * Four copies of one rule, each with slightly different messages and follow-up.
 * setMainImage() below is the one implementation and those four now call it, so
 * this panel is a fifth CALLER rather than a fifth copy.
 *
 * DRAFTS vs LIVE
 * On a draft, choosing a main image writes it to the row and the next
 * Preview/Submit carries it — nothing is sent to Amazon by picking.
 * On a live listing, "Push to Amazon" patches the live listing, and that button
 * is gated on the `publish` permission server-side. So a Lister can choose and
 * stage images all day; only someone who may publish makes them live. Staged and
 * immediate are the same two buttons, which is why both exist.
 */

/* ---- the ONE way to set a listing's main image -------------------------- */
/* Returns true on success. Callers do their own messaging where they need
 * something specific; the shared behaviour (write the row, refresh the grid) is
 * here so it cannot drift between the five entry points. */
async function setMainImage(sku, url, opts){
  opts = opts || {};
  if(!sku || !url){ toast("Nothing to set"); return false; }
  try{
    const r = await fetch("/edit", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku:sku, target:"attr",
                           key:"main_product_image_locator", value:url})});
    const j = await r.json();
    if(!j || !j.ok){
      toast("Could not set the main image: " + ((j && j.error) || "unknown"));
      return false;
    }
    if(opts.quiet !== true) toast(opts.message || "Main image set ✓");
    if(opts.reload !== false && typeof loadRows === "function") loadRows();
    return true;
  }catch(e){
    toast("Could not set the main image: " + ((e && e.message) || e));
    return false;
  }
}

/* ---- the panel ---------------------------------------------------------- */
let IMGLIB = {sku:"", files:[], main:"", live:false};

function _ilEsc(s){
  return String(s == null ? "" : s).replace(/[&<>"]/g, function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];
  });
}

/* Which image is this listing's main right now? Read from whatever the row
 * already holds, so the panel agrees with what a Submit would actually send. */
function _ilCurrentMain(sku){
  const r = (typeof ROWS !== "undefined" && ROWS || []).find(function(x){
    return String(x.sku) === String(sku);
  });
  if(!r) return "";
  if(r.main_product_image_locator) return String(r.main_product_image_locator);
  if(r.main_image) return String(r.main_image);
  try{
    const a = JSON.parse(r.attributes_json || r["Attributes JSON"] || "{}");
    return String(a.main_product_image_locator || "");
  }catch(e){ return ""; }
}

async function openImageLibrary(sku, isLive){
  IMGLIB = {sku:sku, files:[], main:_ilCurrentMain(sku), live:!!isLive,
            showAll:false, otherCount:0};
  let host = document.getElementById("imglibwrap");
  if(!host){
    host = document.createElement("div");
    host.id = "imglibwrap";
    host.className = "modalwrap";
    host.style.zIndex = "120";
    host.innerHTML = '<div class="modal" style="max-width:860px"><div id="imglibbody"></div></div>';
    host.addEventListener("click", function(e){ if(e.target === host) closeImageLibrary(); });
    document.body.appendChild(host);
  }
  host.classList.add("open");
  _ilRender('<div class="cc" style="padding:20px"><span class="genspin"></span> Loading this listing\'s images…</div>');
  await _ilLoad();
}

// THIS listing's images by default, every listing's on request.
//
// Showing the whole library by default would mean scrolling past other products
// to find the one in front of you, and makes it easy to set another product's
// photo as this one's main image by accident. But sometimes the image you want
// IS filed under a sibling SKU -- a variation, or a re-listed item -- so the
// whole library is one click away, and every tile from another SKU is labelled
// with the SKU it belongs to.
async function _ilLoad(){
  const all = !!IMGLIB.showAll;
  _ilRender('<div class="cc" style="padding:20px"><span class="genspin"></span> Loading '
            + (all ? "every listing's images" : "this listing's images") + '…</div>');
  try{
    const url = all ? "/media/list"
                    : "/media/list?sku=" + encodeURIComponent(IMGLIB.sku);
    const j = await (await fetch(url)).json();
    if(!j || !j.ok){ _ilRender('<div class="cc" style="padding:20px;color:var(--red)">'
        + _ilEsc((j && j.error) || "Could not load images") + "</div>"); return; }
    const folders = j.folders || [];
    if(all){
      // This SKU first, then the rest alphabetically, each tile tagged with its
      // owner so nothing is picked from the wrong product by mistake.
      const mine = folders.filter(function(f){ return String(f.sku) === String(IMGLIB.sku); });
      const others = folders.filter(function(f){ return String(f.sku) !== String(IMGLIB.sku); })
                            .sort(function(a, b){ return String(a.sku) < String(b.sku) ? -1 : 1; });
      IMGLIB.files = [];
      mine.concat(others).forEach(function(fo){
        (fo.files || []).forEach(function(f){
          IMGLIB.files.push(Object.assign({}, f, {owner: fo.sku}));
        });
      });
      IMGLIB.otherCount = others.reduce(function(n, f){ return n + (f.files || []).length; }, 0);
    } else {
      const folder = folders[0];
      IMGLIB.files = (folder && folder.files) || [];
      IMGLIB.otherCount = 0;
    }
    _ilDraw();
  }catch(e){
    _ilRender('<div class="cc" style="padding:20px;color:var(--red)">' + _ilEsc(String(e)) + "</div>");
  }
}

async function ilToggleAll(){
  IMGLIB.showAll = !IMGLIB.showAll;
  await _ilLoad();
}

function closeImageLibrary(){
  const h = document.getElementById("imglibwrap");
  if(h) h.classList.remove("open");
}

function _ilRender(html){
  const b = document.getElementById("imglibbody");
  if(b) b.innerHTML = html;
}

function _ilDraw(){
  const sku = IMGLIB.sku;
  // Group as the library stores them: the SKU root is main/concept work,
  // "secondary" and "aplus/..." are their own shelves. Same grouping /media/list
  // already returns, so the panel cannot disagree with the folder on disk.
  const groups = {};
  IMGLIB.files.forEach(function(f){
    const g = f.group || "main";
    (groups[g] = groups[g] || []).push(f);
  });

  let h = '<div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">'
        + '<div style="font-weight:600;font-size:15px">Images</div>'
        + '<div class="cc" style="font-size:12px">' + _ilEsc(sku) + '</div>'
        + '<span class="spacer" style="flex:1"></span>'
        + '<button class="db-chip" onclick="closeImageLibrary()">Close</button></div>';

  h += '<div class="cc" style="font-size:11.5px;margin-bottom:10px">'
     + 'Choosing a main image writes it to this listing. Nothing reaches Amazon '
     + 'until you Submit — or, for a listing that is already live, until you '
     + 'press <b>Push to Amazon</b>.</div>';

  h += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">'
     + '<button class="db-chip" onclick="ilToggleAll()">'
     + (IMGLIB.showAll ? '<i class="ti ti-photo"></i> Show only this listing\'s images'
                       : '<i class="ti ti-library-photo"></i> Show every listing\'s images')
     + '</button>'
     + '<span class="cc" style="font-size:11px">'
     + (IMGLIB.showAll
         ? ('Showing the whole library' + (IMGLIB.otherCount
              ? ' — ' + IMGLIB.otherCount + ' image' + (IMGLIB.otherCount===1?'':'s')
                + ' belong to other listings and are labelled'
              : ''))
         : 'Showing only ' + _ilEsc(sku))
     + '</span></div>';

  // upload your own
  h += '<div style="border:1px dashed #2f3a4d;border-radius:8px;padding:10px;margin-bottom:14px">'
     + '<b style="font-size:12.5px">Upload your own image</b>'
     + '<div class="cc" style="font-size:11px;margin:4px 0 8px">'
     + 'Saved to this listing\'s folder and hosted publicly so Amazon can fetch it.</div>'
     + '<input type="file" accept="image/*" id="il_upload" '
     + 'onchange="ilUpload(this)" style="font-size:12px">'
     + '<span id="il_upstatus" class="cc" style="font-size:11px;margin-left:8px"></span></div>';

  if(!IMGLIB.files.length){
    h += '<div class="empty" style="padding:24px">No images stored for this listing yet.'
       + '<div class="cc" style="margin-top:6px;font-size:11.5px">'
       + 'Generate some in Image Studio, or upload one above.</div></div>';
    _ilRender(h);
    return;
  }

  Object.keys(groups).sort().forEach(function(g){
    h += '<div style="font-size:11.5px;font-weight:600;margin:12px 0 6px;opacity:.85">'
       + _ilEsc(g === "main" ? "Main / concepts" : g) + '</div>'
       + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px">';
    groups[g].forEach(function(f){
      const isMain = IMGLIB.main && (IMGLIB.main === f.url
                     || String(IMGLIB.main).indexOf(f.name) >= 0);
      h += '<div style="border:1px solid ' + (isMain ? "var(--ok)" : "var(--line)")
         + ';border-radius:8px;overflow:hidden;background:var(--panel)">'
         + '<img src="' + _ilEsc(f.url) + '" loading="lazy" '
         + 'style="width:100%;height:120px;object-fit:contain;background:#0d1220;display:block">'
         + '<div style="padding:6px 7px">'
         + '<div class="cc" style="font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" '
         + 'title="' + _ilEsc(f.name) + '">' + _ilEsc(f.name) + '</div>'
         // Whose image this is, whenever it is not this listing's. Without it,
         // "Use as main" on a sibling SKU's photo looks identical to the right one.
         + ((f.owner && String(f.owner) !== String(sku))
             ? '<div style="font-size:10px;color:var(--warn);white-space:nowrap;overflow:hidden;'
               + 'text-overflow:ellipsis" title="' + _ilEsc(f.owner) + '">from '
               + _ilEsc(f.owner) + '</div>'
             : '')
         + '<div class="cc" style="font-size:10px;opacity:.7">'
         + (f.width ? (f.width + "×" + f.height) : "") + '</div>'
         + (isMain
             ? '<div style="font-size:10.5px;color:var(--ok);font-weight:600;margin-top:4px">✓ main image</div>'
             // jsArg, not JSON.stringify: the latter emits DOUBLE quotes, which
             // closed this onclick attribute and left the handler as `ilSetMain(`.
             // The button rendered perfectly and did nothing when pressed.
             : '<button class="db-chip" style="margin-top:4px;font-size:10.5px" '
               + 'onclick="ilSetMain(' + jsArg(f.url) + ')">Use as main</button>')
         // ALWAYS offered. This used to be hidden unless IMGLIB.live was true --
         // a flag the caller guesses from whatever the row happens to hold, and
         // which is false for a live listing whose catalogue has not been loaded
         // yet. So the one control that chooses a slot was invisible on listings
         // that were perfectly live, with nothing on screen to say why.
         //
         // Whether a listing is on Amazon is Amazon's answer, not ours: pressing
         // this reads the real listing, and if Amazon does not have it the reply
         // says exactly that. A wrong guess that HIDES a control is worse than a
         // request that comes back with a clear no.
         + '<button class="db-chip" style="margin-top:4px;font-size:10.5px;'
           + 'background:var(--accent);color:#fff;border-color:var(--accent)" '
           + 'title="Choose which image this is on Amazon — main, PT1-PT8 or the '
           + 'variation swatch — and send it" '
           + 'onclick="ilPushThis(' + jsArg(f.url) + ')">Send to Amazon…</button>'
         + '</div></div>';
    });
    h += '</div>';
  });

  // Push to Amazon: only meaningful for a listing that is already live. The
  // server gates it on `publish` regardless of what is drawn here.
  // The picker and its status line always exist; only the standing "push the
  // main image" button below is about a listing already known to be live.
  h += '<span id="il_pushstatus" class="cc" style="font-size:11.5px"></span>'
     + '<div id="il_slotpick"></div>';
  if(IMGLIB.live){
    h += '<div style="margin-top:16px;border-top:1px solid #26303f;padding-top:12px">'
       + '<button class="db-chip" style="background:var(--accent);color:#fff;border-color:var(--accent)" '
       + 'onclick="ilPushLive()">Push main image to the live Amazon listing</button>'
       // The status line and the picker host live ABOVE, outside this block, so
       // there is exactly one of each. Two elements sharing an id means
       // getElementById quietly picks the first and the other never updates.
       + '<div class="cc" style="font-size:11px;margin-top:6px">'
       + 'Updates only that one image on Amazon — no full resubmit. Amazon takes a '
       + 'few minutes to show it. Use <b>Send to Amazon…</b> on an image above to '
       + 'choose which slot it goes in (main, PT1–PT8, swatch).</div></div>';
  }
  _ilRender(h);
}

async function ilSetMain(url){
  const ok = await setMainImage(IMGLIB.sku, url, {message:"Main image set ✓", reload:true});
  if(ok){ IMGLIB.main = url; _ilDraw(); }
}

function ilUpload(inp){
  const f = inp && inp.files && inp.files[0];
  const st = document.getElementById("il_upstatus");
  if(!f) return;
  if(!/^image\//.test(f.type || "")){
    if(st) st.textContent = "That is not an image file.";
    inp.value = ""; return;
  }
  const rd = new FileReader();
  rd.onload = async function(){
    if(st) st.innerHTML = '<span class="genspin"></span> uploading…';
    try{
      const up = await (await fetch("/media/upload", {method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:IMGLIB.sku, data:rd.result, name:f.name, kind:"main"})})).json();
      if(!up || !up.ok){
        if(st) st.textContent = "Upload failed: " + ((up && up.error) || "unknown");
        return;
      }
      // Prefer the PUBLIC Drive url: Amazon has to fetch the image over the open
      // internet, and a /media/... path is only reachable from inside this app.
      const pub = up.drive_direct_url || up.url || "";
      if(up.drive_direct_url){
        await setMainImage(IMGLIB.sku, pub, {message:"Uploaded and set as main ✓"});
        IMGLIB.main = pub;
      }else{
        if(st) st.textContent = "Uploaded. Set this account's Drive folder to make it "
                              + "reachable by Amazon" + (up.drive_error ? (" (" + up.drive_error + ")") : "") + ".";
      }
      await openImageLibrary(IMGLIB.sku, IMGLIB.live);   // re-read the folder
    }catch(e){
      if(st) st.textContent = "Upload error: " + ((e && e.message) || e);
    }finally{ if(inp) inp.value = ""; }
  };
  rd.readAsDataURL(f);
}

// Push ONE image, named. Getting an image onto Amazon used to be two separate
// steps -- "Use as main", then "Push main image" -- with nothing saying they had
// to be done in that order, so picking an image and pressing push sent whatever
// the main image happened to be already. This does both, and says which image it
// is sending.
// WHICH SLOT. Amazon has eighteen image attributes on a live listing, not one,
// and the rules differ per slot: a lifestyle shot is fine as PT3 and gets the
// listing suppressed as MAIN. The slots come from the product type's own schema,
// with what is already in each, so replacing one is never a surprise.
async function ilPushThis(url){
  if(!url) return;
  const st = document.getElementById("il_pushstatus");
  if(st) st.innerHTML = '<span class="genspin"></span> reading this listing\'s image slots…';
  let j;
  try{ j = await (await fetch("/listing/image_slots?sku="+encodeURIComponent(IMGLIB.sku))).json(); }
  catch(e){ if(st) st.innerHTML = '<span style="color:var(--red)">'+_ilEsc(String(e))+'</span>'; return; }
  if(!j || !j.ok){
    if(st) st.innerHTML = '<span style="color:var(--red)">'+_ilEsc((j&&j.error)||"Could not read the slots")+'</span>';
    return;
  }
  if(!j.checked || !(j.slots||[]).length){
    if(st) st.innerHTML = '<span style="color:var(--warn)">'+_ilEsc(j.note||"No slots to send to")+'</span>';
    return;
  }
  IMGLIB.slots = j.slots;
  IMGLIB.isChild = !!j.is_variation_child;
  IMGLIB.pending = url;
  // What the app made this image for, from the folder it filed it in.
  IMGLIB.pendingMadeAs = ((IMGLIB.files||[]).find(function(f){ return f.url===url; })||{}).group || "";
  if(st) st.innerHTML = "";
  _ilSlotPicker(url);
}

function _ilSlotPicker(url){
  const host = document.getElementById("il_slotpick");
  if(!host) return;
  let h = '<div style="border:1px solid #26303f;border-radius:8px;padding:12px;margin:10px 0">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
    + '<b style="font-size:12.5px">Which image is this?</b>'
    + '<span style="flex:1"></span>'
    + '<button class="db-chip" onclick="ilSlotCancel()">Cancel</button></div>'
    + '<img src="'+_ilEsc(url)+'" style="max-height:90px;border-radius:6px;'
    + 'background:#0d1220;display:block;margin-bottom:8px">';

  // An image the app generated as a SECONDARY or an A+ module cannot become the
  // main image: those are made under rules that allow text, graphics and
  // lifestyle scenes, which are the things Amazon suppresses a listing for on
  // the main image. Shown but disabled, with the reason — hiding it entirely
  // would just look like the main slot was missing.
  const madeAs = String(IMGLIB.pendingMadeAs || "");
  const blocked = (madeAs.indexOf("secondary") === 0)
                    ? "the app generated this as a secondary image"
                    : (madeAs.indexOf("aplus") === 0)
                        ? "this is an A+ module image" : "";

  (IMGLIB.slots||[]).forEach(function(s){
    const no = (s.key === "main_product_image_locator" && blocked) ? blocked : "";
    h += '<div style="display:flex;gap:9px;align-items:flex-start;font-size:11.5px;'
      +  'padding:7px 0;border-top:1px solid #1c2531'+(no?';opacity:.55':'')+'">'
      +  '<div style="min-width:120px"><b>'+_ilEsc(s.label)+'</b>'
      +  (s.occupied ? '<div style="font-size:10px;color:var(--warn)">has an image</div>'
                     : '<div class="cc" style="font-size:10px">empty</div>')
      +  '</div>'
      +  '<div style="flex:1" class="cc">'
      +  (no ? '<b style="color:var(--warn)">Not allowed — '+_ilEsc(no)
             + ', and Amazon suppresses listings whose main image carries text or '
             + 'a scene. Use a PT slot.</b>'
           : _ilEsc(s.help||""))
      +  '</div>'
      +  (no ? '<button class="db-chip" disabled title="'+_ilEsc(no)+'">Send</button>'
            : '<button class="db-chip" onclick="ilSlotSend('+jsArg(s.key)+')">Send</button>')
      +  '</div>';
  });
  h += '</div>';
  host.innerHTML = h;
  host.scrollIntoView({behavior:"smooth", block:"nearest"});
}

function ilSlotCancel(){
  const host = document.getElementById("il_slotpick");
  if(host) host.innerHTML = "";
  IMGLIB.pending = "";
}

async function ilSlotSend(slotKey){
  const url = IMGLIB.pending;
  const slot = (IMGLIB.slots||[]).find(s => s.key === slotKey) || {};
  // Every warning, spelled out, at the moment of the decision. Replacing an
  // occupied slot is the one that matters most: Amazon keeps no copy of what
  // was there.
  let msg = "Send this image as " + (slot.label || slotKey) + "?\n\n" + (slot.help || "");
  if(slot.occupied) msg += "\n\nThis slot ALREADY has an image. Sending replaces "
                         + "it, and Amazon does not keep the old one.";
  if(slot.key === "swatch_product_image_locator" && !IMGLIB.isChild){
    msg += "\n\nThis listing is not part of a variation family, so a swatch would "
         + "have nowhere to show.";
  }
  msg += "\n\nAmazon fetches the image itself and usually shows it within a few minutes.";
  if(!confirm(msg)) return;

  const st = document.getElementById("il_pushstatus");
  if(st) st.innerHTML = '<span class="genspin"></span> sending…';
  try{
    const j = await (await fetch("/listing/image_push",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({confirmed:true, sku:IMGLIB.sku, slot:slotKey, url:url,
                           made_as:(IMGLIB.pendingMadeAs||"")})})).json();
    if(!j.ok){
      if(st) st.innerHTML = '<span style="color:var(--red)">'+_ilEsc(j.error||"failed")+'</span>';
      return;
    }
    ilSlotCancel();
    if(st) st.innerHTML = '<span style="color:var(--ok)">✓ sent as '
                        + _ilEsc(slot.label||slotKey)+' — '+_ilEsc(j.note||"")+'</span>';
    // The app's own main-image copy only tracks MAIN, so only update it for that.
    if(slotKey === "main_product_image_locator"){
      await setMainImage(IMGLIB.sku, url, {quiet:true});
      IMGLIB.main = url;
    }
    await openImageLibrary(IMGLIB.sku, IMGLIB.live);
  }catch(e){
    if(st) st.innerHTML = '<span style="color:var(--red)">'+_ilEsc(String(e))+'</span>';
  }
}

async function ilPushLive(){
  const st = document.getElementById("il_pushstatus");
  const r = (typeof ROWS !== "undefined" && ROWS || []).find(function(x){
    return String(x.sku) === String(IMGLIB.sku);
  });
  if(!IMGLIB.main){
    if(st) st.innerHTML = '<span style="color:var(--warn)">Pick an image first — '
                        + 'use “Send to Amazon” on the one you want.</span>';
    return;
  }
  if(st) st.innerHTML = '<span class="genspin"></span> sending to Amazon…';
  try{
    const j = await (await fetch("/listing/push_image", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({confirmed:true, sku:IMGLIB.sku,
        image_url: IMGLIB.main || "",
        marketplace:(typeof WS_MARKET !== "undefined" ? WS_MARKET : ""),
        product_type:((r && r.product_type) || ""),
        id:(typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id) || ""})})).json();
    if(j && j.ok){
      if(st) st.innerHTML = '<span style="color:var(--ok)">✓ sent ('
                          + _ilEsc(j.status || "accepted") + ')</span>';
    }else{
      const extra = (j && j.issues && j.issues.length)
        ? (" — " + j.issues.map(function(i){ return (i.message || i.code || ""); }).join("; ")) : "";
      if(st) st.innerHTML = '<span style="color:var(--red)">'
        + _ilEsc(((j && j.error) || "failed") + extra) + '</span>';
    }
  }catch(e){
    if(st) st.innerHTML = '<span style="color:var(--red)">' + _ilEsc(String(e)) + '</span>';
  }
}
