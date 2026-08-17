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
            showAll:false, otherCount:0,
            // The slots are loaded ONCE per opening and kept here. Every tile
            // shows a dropdown of them, so they have to exist before the grid is
            // useful -- but not before it is VISIBLE, which is why this loads
            // alongside the images rather than in front of them.
            slots:null, slotsState:"", slotsErr:"", isChild:false};
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
  // Not awaited: the grid is usable while the slots are still coming. Reading
  // them costs one call to Amazon per opening, so it happens once here rather
  // than once per image the way the old "Send as…" button did it.
  _ilEnsureSlots();
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
      // FOLDERS, not one long scroll of everything.
      //
      // Flattening every listing's images into a single grid meant hundreds of
      // tiles from dozens of products, and the only thing separating them was a
      // small label. Folders open as their own screen, the way folders do
      // everywhere else, and you come back out with Back.
      //
      // This SKU first, then the rest alphabetically.
      const mine = folders.filter(function(f){ return String(f.sku) === String(IMGLIB.sku); });
      const others = folders.filter(function(f){ return String(f.sku) !== String(IMGLIB.sku); })
                            .sort(function(a, b){ return String(a.sku) < String(b.sku) ? -1 : 1; });
      IMGLIB.folders = mine.concat(others);
      IMGLIB.otherCount = others.reduce(function(n, f){ return n + (f.files || []).length; }, 0);
      if(IMGLIB.openFolder){
        const fo = IMGLIB.folders.filter(function(f){
          return String(f.sku) === String(IMGLIB.openFolder); })[0];
        IMGLIB.files = (fo && fo.files || []).map(function(f){
          return Object.assign({}, f, {owner: fo.sku}); });
        _ilDraw();
      } else {
        IMGLIB.files = [];
        _ilDrawFolders();
      }
      // "No images stored for this account yet" is a claim about the WHOLE disk,
      // made from a listing of ONE folder. When images had been generated into a
      // different workspace, that sentence read as "your images were deleted" --
      // and after a deployment that is what it was taken to mean. So whenever
      // the whole library is on screen, also ask what else is on the disk, and
      // say what is really there instead of implying there is nothing.
      _ilElsewhere();
      return;
    }
    IMGLIB.openFolder = "";
    IMGLIB.folders = null;
    const folder = folders[0];
    IMGLIB.files = (folder && folder.files) || [];
    IMGLIB.otherCount = 0;
    _ilDraw();
  }catch(e){
    _ilRender('<div class="cc" style="padding:20px;color:var(--red)">' + _ilEsc(String(e)) + "</div>");
  }
}

async function ilToggleAll(){
  IMGLIB.showAll = !IMGLIB.showAll;
  IMGLIB.openFolder = "";        // always land on the folder list, not inside one
  await _ilLoad();
}

// ---- the folder list, which is its own screen ---------------------------
async function ilOpenFolder(sku){
  IMGLIB.openFolder = sku;
  await _ilLoad();
}
async function ilCloseFolder(){
  IMGLIB.openFolder = "";
  await _ilLoad();
}

function _ilDrawFolders(){
  const list = IMGLIB.folders || [];
  let h = '<div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">'
        + '<p class="paneltitle" style="font-size:15px;line-height:22px">'
        + '<i class="ti ti-library-photo"></i> Image library</p>'
        + '<div class="cc" style="font-size:12px">' + list.length + ' product'
        + (list.length === 1 ? '' : 's') + '</div>'
        + '<span class="spacer" style="flex:1"></span>'
        + '<button class="db-chip" onclick="ilToggleAll()">'
        + '<i class="ti ti-photo"></i> Back to ' + _ilEsc(IMGLIB.sku) + '</button>'
        + '<button class="db-chip" onclick="closeImageLibrary()">Close</button></div>';
  h += '<div class="cc" style="font-size:11.5px;margin-bottom:12px">'
     + 'One folder per product. Open one to see its images, set a main image, '
     + 'send one to Amazon, or download the lot.</div>';

  // Filled in by _ilElsewhere() once the disk has answered. It sits ABOVE the
  // empty state on purpose: "there is nothing here" and "they are in the next
  // workspace along" is a different message from "there is nothing here".
  h += '<div id="il_elsewhere"></div>';

  if(!list.length){
    h += '<div class="empty" style="padding:24px">No images stored for '
       + '<b>this workspace</b> yet.</div>';
    _ilRender(h); return;
  }

  h += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px">';
  list.forEach(function(fo){
    const files = fo.files || [];
    const cover = files[0];
    const isMine = String(fo.sku) === String(IMGLIB.sku);
    h += '<div onclick="ilOpenFolder(' + jsArg(fo.sku) + ')" '
       + 'style="border:1px solid ' + (isMine ? 'var(--accent)' : 'var(--line)')
       + ';border-radius:10px;overflow:hidden;background:var(--panel);cursor:pointer">'
       + (cover
           ? '<img src="' + _ilEsc(cover.url) + '" loading="lazy" '
             + 'style="width:100%;height:110px;object-fit:contain;background:#0d1220;display:block">'
           : '<div style="height:110px;background:#0d1220;display:flex;align-items:center;'
             + 'justify-content:center"><i class="ti ti-folder" style="font-size:34px;opacity:.5"></i></div>')
       + '<div style="padding:7px 9px">'
       + '<div style="font-size:11.5px;font-weight:600;white-space:nowrap;overflow:hidden;'
       + 'text-overflow:ellipsis" title="' + _ilEsc(fo.sku) + '">'
       + '<i class="ti ti-folder"></i> ' + _ilEsc(fo.sku) + '</div>'
       + '<div class="cc" style="font-size:10.5px">' + files.length + ' image'
       + (files.length === 1 ? '' : 's')
       + (isMine ? ' · this listing' : '') + '</div>'
       + '<button class="db-chip" style="margin-top:5px;font-size:10.5px" '
       + 'onclick="event.stopPropagation();ilDownloadAll(' + jsArg(fo.sku) + ')">'
       + '<i class="ti ti-download"></i> Download all</button>'
       + '</div></div>';
  });
  h += '</div>';
  _ilRender(h);
}

// ---- downloads ----------------------------------------------------------
// One image: a plain link with `download`, which is what the attribute is for.
// A whole folder: ONE zip from the server. Twenty separate downloads means
// twenty save dialogs, and a browser blocks most of them as unwanted popups
// after the first two or three -- so "download all" would appear to half-work.
function ilDownloadOne(url, name){
  const a = document.createElement("a");
  a.href = url;
  a.download = name || "image";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function ilDownloadAll(sku){
  const s = sku || IMGLIB.openFolder || IMGLIB.sku;
  if(!s){ toast("No folder to download."); return; }
  toast("Preparing the zip…");
  window.location.href = "/media/zip?sku=" + encodeURIComponent(s);
}

function closeImageLibrary(){
  const h = document.getElementById("imglibwrap");
  if(h) h.classList.remove("open");
}

/* Images that exist on the disk but not in THIS workspace.
 *
 * The library lists one folder -- the open workspace's -- which is right, since
 * accounts must not see each other's work. The cost is that an empty screen
 * cannot tell you whether the images are gone or merely filed elsewhere, and
 * those two need opposite responses. This asks the server about the whole disk
 * and says which one it is.
 */
async function _ilElsewhere(){
  const box = document.getElementById("il_elsewhere");
  if(!box) return;
  let j = null;
  try{ j = await (await fetch("/media/recover/survey")).json(); }catch(e){ return; }
  if(!j || !j.ok) return;
  IMGLIB.survey = j;

  const here = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT) ? String(CUR_ACCOUNT.id || "") : "";
  const other = (j.locations || []).filter(function(l){ return String(l.account_id || "") !== here; });
  const total = other.reduce(function(n, l){ return n + (l.images || 0); }, 0);

  // The disk verdict matters even when nothing is misfiled: it is the
  // difference between "safe" and "this will happen again on the next deploy".
  const disk = j.disk || {};
  let warn = "";
  if(disk.verdict === "EPHEMERAL"){
    warn = '<div style="border:1px solid var(--red);border-radius:10px;padding:10px 12px;'
         + 'margin-bottom:10px;font-size:12.5px">'
         + '<b style="color:var(--red)">This server does not keep files between deployments.</b><br>'
         + 'Generated images are written to <code>' + _ilEsc(disk.data_dir || "") + '</code>, which is '
         + 'wiped every time the app is redeployed. Mount a disk at that path in Render and '
         + 'images will survive. Until then, download anything you want to keep.</div>';
  }
  if(!total){ box.innerHTML = warn; return; }

  const rows = other.map(function(l){
    const name = l.account_id ? l.account_id : "no workspace (shared folder)";
    return '<div style="display:flex;align-items:center;gap:8px;padding:5px 0">'
         + '<div style="flex:1"><b>' + _ilEsc(name) + '</b> — ' + l.images + ' image'
         + (l.images === 1 ? '' : 's') + ' across ' + (l.skus || []).length + ' product'
         + ((l.skus || []).length === 1 ? '' : 's')
         + (l.orphaned ? ' <span style="color:var(--red)">· no workspace shows these</span>' : '')
         + '</div>'
         + (here ? '<button class="db-chip" onclick="ilBringHere(' + jsArg(String(l.account_id || "")) + ')">'
                 + 'Move into ' + _ilEsc(here) + '</button>' : '')
         + '</div>';
  }).join("");

  box.innerHTML = warn
    // .panelcard: the same border, radius and background the other screens use,
    // named rather than retyped. Three copies of "1px solid var(--line)" is
    // three places to change when the card changes, and they never all get
    // changed.
    + '<div class="panelcard" style="margin-bottom:12px;font-size:12.5px">'
    + '<b>' + total + ' image' + (total === 1 ? ' is' : 's are') + ' on this server but filed '
    + 'under another workspace.</b> Nothing was lost — the library only ever shows the '
    + 'workspace you have open. Moving them here makes them visible in this account.'
    + rows + '</div>';
}

/* Move another location's images into the open workspace. Shows exactly what
 * will move and asks first: this is a file move on the server, and the whole
 * point of the screen is that the owner has already been frightened once. */
async function ilBringHere(fromId){
  const here = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT) ? String(CUR_ACCOUNT.id || "") : "";
  if(!here){ toast("Open an account workspace first."); return; }
  let dry = null;
  try{
    dry = await (await fetch("/media/recover/move", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({from: fromId, to: here, dry_run: true})})).json();
  }catch(e){ toast("Could not reach the server."); return; }
  if(!dry || !dry.ok){ toast((dry && dry.error) || "Could not read that folder."); return; }
  if(!dry.moved){ toast("Nothing to move."); return; }

  const label = fromId || "the shared folder";
  if(!confirm("Move " + dry.moved + " image" + (dry.moved === 1 ? "" : "s") + " from "
              + label + " into " + here + "?\n\nNothing is deleted. Any file that would "
              + "clash with one already here is kept under a new name.")) return;

  let res = null;
  try{
    res = await (await fetch("/media/recover/move", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({from: fromId, to: here, dry_run: false})})).json();
  }catch(e){ toast("The move failed."); return; }
  if(!res || !res.ok){ toast((res && res.error) || "The move failed."); return; }
  toast("Moved " + res.moved + " image" + (res.moved === 1 ? "" : "s")
        + (res.renamed ? " (" + res.renamed + " renamed to avoid overwriting)" : "") + ".");
  _ilLoad();
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

  // Inside a folder opened from the library, the way out is Back -- not the
  // toggle that dumps you at the top of everything.
  const inFolder = !!IMGLIB.openFolder;
  const shown = inFolder ? IMGLIB.openFolder : sku;
  let h = '<div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;flex-wrap:wrap">'
        + (inFolder
            ? '<button class="db-chip" onclick="ilCloseFolder()">'
              + '<i class="ti ti-arrow-left"></i> All folders</button>'
            : '')
        // .paneltitle, the same name Sales, Traffic and the rest use for the
        // heading of a panel -- rather than a weight and a size typed inline
        // here and typed slightly differently everywhere else.
        + '<p class="paneltitle" style="font-size:15px;line-height:22px">'
        + (inFolder ? '<i class="ti ti-folder-open"></i> ' : '') + 'Images</p>'
        + '<div class="cc" style="font-size:12px">' + _ilEsc(shown) + '</div>'
        + '<span class="spacer" style="flex:1"></span>'
        + (IMGLIB.files.length
            ? '<button class="db-chip" onclick="ilDownloadAll()" '
              + 'title="Every image in this folder, as one zip">'
              + '<i class="ti ti-download"></i> Download all ('
              + IMGLIB.files.length + ')</button>'
            : '')
        + '<button class="db-chip" onclick="closeImageLibrary()">Close</button></div>';

  h += '<div class="cc" style="font-size:11.5px;margin-bottom:10px">'
     + 'Choosing a main image writes it to this listing. Nothing reaches Amazon '
     + 'until you Submit — or, for a listing that is already live, until you '
     + 'press <b>Push to Amazon</b>.</div>';

  h += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">'
     + '<button class="db-chip" onclick="ilToggleAll()">'
     + (IMGLIB.showAll ? '<i class="ti ti-photo"></i> Just this listing'
                       : '<i class="ti ti-library-photo"></i> Browse all products')
     + '</button>'
     + '<span class="cc" style="font-size:11px">'
     + (inFolder
         ? 'Inside ' + _ilEsc(IMGLIB.openFolder)
         : 'Showing only ' + _ilEsc(sku))
     + '</span></div>';

  // upload your own
  h += '<div style="border:1px dashed #2f3a4d;border-radius:8px;padding:10px;margin-bottom:14px">'
     + '<b style="font-size:12.5px">Upload your own image</b>'
     + '<div class="cc" style="font-size:11px;margin:4px 0 8px">'
     + 'Saved to this listing\'s folder and hosted publicly so Amazon can fetch it.</div>'
     // THE ONE WHITE THING ON A DARK SCREEN. A bare file input is drawn by the
     // browser in its own colours, so "Choose File" arrived as a light grey
     // button in the middle of the panel and read as a rendering fault. The
     // input still does the work -- it is simply moved off-screen and driven by
     // a label, which is what a <label for> is for, so the keyboard and screen
     // reader behaviour are unchanged.
     + '<input type="file" accept="image/*" id="il_upload" class="visually-hidden" '
     + 'onchange="ilUpload(this)">'
     + '<label class="db-chip" for="il_upload" style="cursor:pointer">'
     + '<i class="ti ti-upload"></i> Choose an image</label>'
     + '<span id="il_upstatus" class="cc" style="font-size:11px;margin-left:8px"></span></div>';

  if(!IMGLIB.files.length){
    h += '<div class="empty" style="padding:24px">No images stored for this listing yet.'
       + '<div class="cc" style="margin-top:6px;font-size:11.5px">'
       + 'Generate some in Image Studio, or upload one above.</div></div>';
    _ilRender(h);
    return;
  }

  // Counted across ALL groups, in the order the tiles are drawn, because the
  // defaults are about what the user SEES first, not about which folder the app
  // happened to file an image in. The main image does not consume a PT number.
  let tileNo = 0, ptNo = 0;

  Object.keys(groups).sort().forEach(function(g){
    h += '<div style="font-size:11.5px;font-weight:600;margin:12px 0 6px;opacity:.85">'
       + _ilEsc(g === "main" ? "Main / concepts" : g) + '</div>'
       + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px">';
    groups[g].forEach(function(f){
      const isMain = IMGLIB.main && (IMGLIB.main === f.url
                     || String(IMGLIB.main).indexOf(f.name) >= 0);
      const idx = tileNo++;
      const ptIndex = isMain ? 0 : (++ptNo);
      h += '<div style="border:1px solid ' + (isMain ? "var(--ok)" : "var(--line)")
         + ';border-radius:8px;overflow:hidden;background:var(--panel)">'
         + '<img src="' + _ilEsc(f.url) + '" loading="lazy" '
         + 'onclick="ilPreview(' + jsArg(f.url) + ',' + jsArg(f.name) + ')" '
         + 'title="Click to view full size" '
         + 'style="width:100%;height:120px;object-fit:contain;background:#0d1220;'
         + 'display:block;cursor:zoom-in">'
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
         // THE SLOT IS ON THE TILE, ALREADY CHOSEN.
         //
         // It was a "Send as…" button that read the listing and then asked. Two
         // reports came out of that: "i do not have option here to send an image
         // as pt1 or pt2 or pt3 ... or swch image", and then "i should have a
         // button under the image like a dropdown menu which asks me to select
         // the image type". A choice you cannot see until after you commit to
         // making it is not a choice anybody finds.
         + _ilTileSlotPicker(idx, f, isMain, ptIndex)
         // Saving one image was "right-click, Save as, find it again". A link
         // with `download` is what the attribute exists for.
         + '<button class="db-chip" style="margin-top:4px;font-size:10.5px" '
           + 'title="Save this image" '
           + 'onclick="ilDownloadOne(' + jsArg(f.url) + ',' + jsArg(f.name) + ')">'
           + '<i class="ti ti-download"></i> Download</button>'
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
       + 'few minutes to show it. To place an image in a particular slot, use the '
       + 'dropdown under it and press <b>Send to Amazon</b>. Which slots exist is '
       + 'read from that product type on Amazon, so a type with no swatch will not '
       + 'offer one.</div></div>';
  }
  _ilRender(h);
  // After the markup exists, not during: the notes read the selects.
  _ilSlotNotesAll();
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
// SEEING THE IMAGE, FULL SIZE.
//
// "in the image library there is no previewer of the images which opens the
//  images over the screen like in drive when clicked over the image"
//
// The tiles are 120px tall and object-fit:contain, so a 4096px image was being
// judged at three per cent of its size -- which is no way to decide whether a
// picture is good enough to put on a listing. Clicking one now opens it over
// everything at its real proportions.
//
// Its own layer above the library modal rather than a third modal: this has to
// open FROM a modal that is already open, and stacking modals means the Escape
// key, the backdrop click and the scroll lock all have to agree about which one
// is on top.
let _IL_PREVIEW = null;

function ilPreview(url, name){
  if(!url) return;
  ilPreviewClose();
  const el = document.createElement("div");
  el.id = "ilpreview";
  el.style.cssText = "position:fixed;inset:0;z-index:400;background:rgba(6,9,15,.92);"
    + "display:flex;align-items:center;justify-content:center;flex-direction:column;"
    + "gap:10px;padding:26px;cursor:zoom-out";
  el.innerHTML =
      '<img src="' + _ilEsc(url) + '" alt="' + _ilEsc(name || "") + '" '
    + 'style="max-width:94vw;max-height:82vh;object-fit:contain;border-radius:8px;'
    + 'background:#0d1220;box-shadow:0 18px 60px rgba(0,0,0,.6);cursor:default">'
    + '<div style="display:flex;gap:8px;align-items:center;max-width:94vw">'
    + '<span class="cc" style="font-size:11.5px;overflow:hidden;text-overflow:ellipsis;'
    + 'white-space:nowrap">' + _ilEsc(name || "") + '</span>'
    + '<button class="db-chip" onclick="event.stopPropagation();ilDownloadOne('
    + jsArg(url) + ',' + jsArg(name || "image") + ')">'
    + '<i class="ti ti-download"></i> Download</button>'
    + '<button class="db-chip" onclick="event.stopPropagation();window.open('
    + jsArg(url) + ',\'_blank\')"><i class="ti ti-external-link"></i> Open</button>'
    + '<button class="db-chip" onclick="ilPreviewClose()">Close</button>'
    + '</div>';
  // Clicking the picture itself must not close it -- that is where a person
  // clicks to look closer, and having it vanish under the cursor is the one
  // thing a viewer must not do.
  el.addEventListener("click", function(ev){
    if(ev.target === el) ilPreviewClose();
  });
  document.body.appendChild(el);
  _IL_PREVIEW = el;
  document.addEventListener("keydown", _ilPreviewKey);
}

function _ilPreviewKey(ev){
  // Escape closes the PREVIEW and stops there. Without this the same key would
  // reach the library behind it and shut both, so a glance at one picture would
  // cost you the panel you were working in.
  if(ev.key === "Escape"){
    ev.stopPropagation();
    ilPreviewClose();
  }
}

function ilPreviewClose(){
  document.removeEventListener("keydown", _ilPreviewKey);
  if(_IL_PREVIEW && _IL_PREVIEW.parentNode){
    _IL_PREVIEW.parentNode.removeChild(_IL_PREVIEW);
  }
  _IL_PREVIEW = null;
}

// THE SLOT IS A CHOICE YOU MAKE, NOT A QUESTION YOU ARE ASKED AFTERWARDS.
//
// This used to be: press "Send as…", wait while the listing is read, then pick
// from a list that appears at the bottom of the panel. Every image needed the
// same three steps, the slots were re-read each time, and nothing on a tile said
// where that image was going to end up. Asked for as "i should have a button
// under the image like a dropdown menu which asks me to select the image type".
//
// So the slots load ONCE when the library opens, and every tile carries its own
// dropdown, already set to the slot that image is most likely meant for.
async function _ilEnsureSlots(force){
  if(IMGLIB.slotsState === "loading") return;
  if(IMGLIB.slots && !force) return;
  IMGLIB.slotsState = "loading";
  IMGLIB.slotsErr = "";
  _ilRedrawGrid();
  let j = null, err = "";
  try{ j = await (await fetch("/listing/image_slots?sku="
                              + encodeURIComponent(IMGLIB.sku))).json(); }
  catch(e){ err = String(e); }
  if(j && j.ok && j.checked && (j.slots||[]).length){
    IMGLIB.slots = j.slots;
    IMGLIB.isChild = !!j.is_variation_child;
    IMGLIB.slotsState = "ready";
  }else{
    // Whether this listing is ON Amazon is Amazon's answer, not ours -- a draft
    // that was never submitted has no slots to read, and saying so plainly beats
    // an empty dropdown that looks broken.
    IMGLIB.slots = null;
    IMGLIB.slotsState = "failed";
    IMGLIB.slotsErr = (j && (j.error || j.note)) || err
                      || "Could not read this listing's image slots";
  }
  _ilRedrawGrid();
}

// Only redraw when the grid is what is on screen. Opening a folder swaps the
// panel for a different view, and repainting the grid underneath it would throw
// the user back out of wherever they were.
function _ilRedrawGrid(){
  if(document.getElementById("il_pushstatus")) _ilDraw();
}

// The one rule about what may become the MAIN image, asked in both places that
// offer the choice. An image the app generated as a secondary or an A+ module is
// made under rules that ALLOW text, graphics and lifestyle scenes -- the exact
// things Amazon suppresses a listing for when they appear on the main image.
function _ilBlockedMain(group){
  const madeAs = String(group || "");
  if(madeAs.indexOf("secondary") === 0) return "the app generated this as a secondary image";
  if(madeAs.indexOf("aplus") === 0) return "this is an A+ module image";
  return "";
}

// Which slot a tile starts on. The main image defaults to the main slot; every
// other image takes the next free PT in the order they are shown, so a library
// of five secondaries comes up as PT1 to PT5 without anybody choosing anything.
// Asked for as "the default selected option should be pt1 for first image ...
// and next image should have the selected option as pt2 and so on".
function _ilDefaultSlot(isMain, ptIndex){
  const slots = IMGLIB.slots || [];
  if(!slots.length) return "";
  const has = function(k){ return slots.some(function(s){ return s.key === k; }); };
  if(isMain && has("main_product_image_locator")) return "main_product_image_locator";
  const want = "other_product_image_locator_" + ptIndex;
  if(has(want)) return want;
  // More images than the type has PT slots. Fall back to the last PT rather than
  // to the main slot, which is the one that gets a listing suppressed.
  const pts = slots.filter(function(s){
    return /^other_product_image_locator_\d+$/.test(s.key); });
  return pts.length ? pts[pts.length - 1].key : slots[0].key;
}

function _ilTileSlotPicker(idx, f, isMain, ptIndex){
  if(IMGLIB.slotsState === "loading"){
    return '<div class="cc" style="font-size:10px;margin-top:5px">'
         + '<span class="genspin"></span> reading slots…</div>';
  }
  if(!IMGLIB.slots || !IMGLIB.slots.length){
    return '<button class="db-chip" style="margin-top:4px;font-size:10.5px;width:100%" '
         + 'title="' + _ilEsc(IMGLIB.slotsErr || "") + '" '
         + 'onclick="_ilEnsureSlots(true)">'
         + (IMGLIB.slotsState === "failed" ? "Slots unavailable — retry"
                                           : "Read image slots") + '</button>';
  }
  const def = _ilDefaultSlot(isMain, ptIndex);
  const blocked = _ilBlockedMain(f.group);
  let h = '<select class="ed" id="il_slot_' + idx + '" '
        + 'style="width:100%;margin-top:5px;font-size:10.5px;padding:3px 4px" '
        + 'onchange="ilSlotNote(' + idx + ')">';
  (IMGLIB.slots || []).forEach(function(s){
    const no = (s.key === "main_product_image_locator" && blocked);
    h += '<option value="' + _ilEsc(s.key) + '"'
      +  (s.key === def && !no ? " selected" : "")
      +  (no ? " disabled" : "") + '>'
      +  _ilEsc(s.label)
      +  (s.occupied ? " — has one" : "")
      +  (no ? " — not allowed" : "")
      +  '</option>';
  });
  h += '</select>'
    +  '<div id="il_slotnote_' + idx + '" class="cc" style="font-size:9.5px;'
    +  'margin-top:3px;line-height:1.35"></div>'
    +  '<button class="db-chip" style="margin-top:4px;font-size:10.5px;width:100%;'
    +  'background:var(--accent);color:#fff;border-color:var(--accent)" '
    +  'onclick="ilSendTile(' + idx + ',' + jsArg(f.url) + ',' + jsArg(f.group || "") + ')">'
    +  '<i class="ti ti-cloud-upload"></i> Send to Amazon</button>';
  return h;
}

// What the chosen slot means, under the chosen slot. The old flow put this in a
// list you only saw after clicking; here it is beside the control while you are
// still deciding, which is the moment it is worth anything.
function ilSlotNote(idx){
  const sel = document.getElementById("il_slot_" + idx);
  const host = document.getElementById("il_slotnote_" + idx);
  if(!sel || !host) return;
  const s = (IMGLIB.slots || []).find(function(x){ return x.key === sel.value; }) || {};
  // Terse on purpose. On a live listing every gallery slot is occupied, so the
  // full "sending replaces it and Amazon keeps no copy" sentence appeared on all
  // ten tiles at once and became wallpaper. The full warning is still in the
  // confirmation you get on the way out, which is where it can be read once and
  // actually stop you.
  host.innerHTML = (s.occupied
      ? '<span style="color:var(--warn)">replaces what is in it now</span> · '
      : '<span style="color:var(--ok)">empty</span> · ')
    + _ilEsc(s.help || "");
}

// Every tile's note, after a draw. Set here rather than inline in the markup so
// there is one place that decides what the note says.
function _ilSlotNotesAll(){
  (IMGLIB.slots || []).length && document.querySelectorAll('[id^="il_slot_"]')
    .forEach(function(el){
      const idx = String(el.id).replace("il_slot_", "");
      if(/^\d+$/.test(idx)) ilSlotNote(Number(idx));
    });
}

async function ilSendTile(idx, url, group){
  const sel = document.getElementById("il_slot_" + idx);
  if(!sel || !sel.value || !url) return;
  IMGLIB.pending = url;
  IMGLIB.pendingMadeAs = group || "";
  await ilSlotSend(sel.value);
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
    IMGLIB.pending = "";
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
                        + 'use “Send as…” on the one you want.</span>';
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
