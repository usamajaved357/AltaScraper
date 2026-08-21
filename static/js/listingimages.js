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
      body:JSON.stringify(acctBody({sku:sku, target:"attr",
                           key:"main_product_image_locator", value:url}))});
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

/* WHEN AN IMAGE WAS MADE, in the shortest form that is still unambiguous.
 *
 * "3 hours ago" for anything today, because that is how you tell this
 * morning's attempt from the retry; a real date beyond that, because "14 days
 * ago" is a worse way of saying 6 August. The full timestamp is on the tooltip
 * either way, so nothing is lost to the rounding.
 *
 * made_at is a unix second from the file's own mtime (routes/media_routes.py).
 */
function _ilWhen(secs){
  const t = Number(secs) * 1000;
  if(!isFinite(t) || t <= 0) return "";
  const d = new Date(t), now = new Date();
  const mins = Math.round((now - d) / 60000);
  let s;
  if(mins < 1) s = "just now";
  else if(mins < 60) s = mins + " min ago";
  else if(mins < 60 * 24 && d.toDateString() === now.toDateString())
    s = Math.round(mins / 60) + "h ago";
  else s = d.toLocaleDateString(undefined, {day: "numeric", month: "short"})
         + " " + d.toLocaleTimeString(undefined, {hour: "2-digit", minute: "2-digit"});
  return '<span title="' + _ilEsc(d.toLocaleString()) + '">' + _ilEsc(s) + "</span>";
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

/* WHERE THE LIBRARY DRAWS ITSELF.
 *
 *   "make the image library work on its own as a separate page, i should not
 *    have to go from one page to another to just create images"
 *
 * It has always been a modal over Listings, opened per SKU. That is right when
 * you are already looking at a row and want its pictures; it is wrong as the
 * place you go to WORK on images, because every SKU means going back to
 * Listings, finding the row, and opening it again.
 *
 * So the library can now render into a page instead. Set the host id and it
 * draws there; leave it and it is the modal exactly as before. The modal is
 * still the default deliberately -- the row button is a real workflow and
 * changing it was not asked for.
 */
let _IL_HOST = "";

function ilRenderInto(elementId){
  _IL_HOST = elementId || "";
}

/* The element the library's markup goes into: the page host when one is set,
   the modal's own body otherwise. One function, so nothing has to remember. */
function _ilBody(){
  if(_IL_HOST){
    const p = document.getElementById(_IL_HOST);
    if(p) return p;
  }
  return document.getElementById("imglibbody");
}

async function openImageLibrary(sku, isLive){
  IMGLIB = {sku:sku, files:[], main:_ilCurrentMain(sku), live:!!isLive,
            showAll:false, otherCount:0,
            // The slots are loaded ONCE per opening and kept here. Every tile
            // shows a dropdown of them, so they have to exist before the grid is
            // useful -- but not before it is VISIBLE, which is why this loads
            // alongside the images rather than in front of them.
            slots:null, slotsState:"", slotsErr:"", isChild:false};
  // On a page host there is no modal to build or open -- the container is
  // already on screen and staying there.
  if(!_IL_HOST){
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
  }
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
    // WHAT TO DO, not just that there is nothing. Measured across the accounts:
    // nestwell_goods and selvora_limited have ZERO image files on disk, while
    // jack_uk has 75 that all load -- so "I cannot see the thumbnails" on those
    // accounts was a screen with nothing to show, saying so in six words and
    // offering no way forward.
    h += (typeof uiEmpty === "function"
      ? uiEmpty("No images stored for this workspace yet",
          "Every image this app generates or you upload is filed here under its "
          + "SKU. Nothing has been made for this account yet — open a listing and "
          + "use <b>Image Studio</b> to create one, or upload your own from the "
          + "listing's image button.",
          '<button class="db-chip" onclick="closeImageLibrary();'
          + 'if(typeof navTo===\'function\')navTo(\'imagestudio\')">'
          + '<i class="ti ti-sparkles"></i> Open Image Studio</button>')
      : '<div class="empty" style="padding:24px">No images stored for '
        + '<b>this workspace</b> yet.</div>');
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
           ? '<img src="' + _ilEsc(typeof thumbUrl==="function"?thumbUrl(cover.url,160):cover.url) + '" loading="lazy" '
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

/* KEEP THE READER WHERE THEY WERE.
 *
 *     "everytime i click on send to amazon the full page reloads again, very
 *      strange behavior it is"
 *
 * Nothing reloads -- there is no form on this page and no location call in this
 * flow. What happens is that a successful send calls openImageLibrary() again,
 * which rebuilds the entire panel from scratch. Everything flashes, every tile
 * is replaced, and the view jumps back to the top. From the outside that is
 * indistinguishable from a page reload, and it happens at the worst moment:
 * right after an action, when you want to see what changed.
 *
 * Rebuilding IS correct -- the slot you just filled is now occupied and every
 * "has one" label has to change. What was wrong was throwing away the reader's
 * position along with the markup. */
function _ilRender(html){
  const b = _ilBody();
  if(!b) return;
  // The panel scrolls inside itself on some layouts and moves the window on
  // others, so both are captured and both restored.
  const top = b.scrollTop, wtop = window.scrollY;
  b.innerHTML = html;
  if(top) b.scrollTop = top;
  if(wtop) window.scrollTo(0, wtop);
}

/* THE SHELVES INSIDE A SKU FOLDER, named and explained.
 *
 * The folder on disk is the only place an image's KIND is recorded -- there is
 * no image record anywhere, /media/list re-derives it from the directory name --
 * so these are the labels for what is genuinely there. The requirements differ
 * per shelf and getting them wrong is a rejected submission, which is why each
 * one carries its own line rather than leaving "aplus/premium/mobile" to be
 * interpreted.
 *
 * Amazon's rules, as at August 2026:
 *   MAIN         pure white background (RGB 255,255,255), product filling
 *                ~85% of the frame, no text, no props, no logos.
 *   SECONDARY    PT01-PT08. Text, graphics and lifestyle are all allowed.
 *   A+ BASIC     one asset per module; it is scaled for both desktop and
 *                mobile, so there is nothing to supply twice.
 *   A+ PREMIUM   the modules render at different sizes on desktop and on
 *                mobile, and one asset cannot serve both.
 */
const _IL_SHELF = {
  "main": {title: "Main / concepts",
           note: "Pure white background, product about 85% of the frame, no "
               + "text or props. This is the photo shoppers see in search."},
  "secondary": {title: "Secondary images (PT01–PT08)",
                note: "Text, graphics and lifestyle shots are all allowed here. "
                    + "Up to eight."},
  "aplus/basic": {title: "A+ content — Basic",
                  note: "One asset per module. Amazon scales it for desktop and "
                      + "mobile, so nothing is needed twice."},
  "aplus/premium": {title: "A+ content — Premium",
                    note: "Premium modules render at different sizes on desktop "
                        + "and mobile. Anything left here has not been marked as "
                        + "either."},
  "aplus/premium/desktop": {title: "A+ Premium — desktop",
                            note: "The wide desktop rendering of each premium "
                                + "module."},
  "aplus/premium/mobile": {title: "A+ Premium — mobile",
                           note: "The mobile rendering. A separate asset, not a "
                               + "crop of the desktop one."},
};

/* Shelves in the order a listing is built, not alphabetically. Alphabetical put
   "aplus/basic" above "main", which is the reverse of how anyone works. */
const _IL_SHELF_ORDER = ["main", "secondary", "aplus/basic", "aplus/premium",
                         "aplus/premium/desktop", "aplus/premium/mobile"];
function _ilGroupOrder(keys){
  const known = _IL_SHELF_ORDER.filter(function(k){ return keys.indexOf(k) >= 0; });
  // Anything the app does not have a name for still gets drawn, after the
  // known shelves. A folder made by hand must never make images disappear.
  const rest = keys.filter(function(k){ return _IL_SHELF_ORDER.indexOf(k) < 0; }).sort();
  return known.concat(rest);
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

  // WHAT IS ALREADY ON AMAZON, above the library rather than below it.
  //
  // "how can i verify if the images are sent inside the app, is there any option
  //  to see the uploaded images to amazon in the app"
  //
  // There was not. You could send to a slot and afterwards the dropdown would
  // say "— has one", which tells you a slot is occupied without showing you by
  // what. This panel reads the listing back from Amazon and shows every slot
  // with the picture Amazon actually holds in it. It is drawn first because
  // "what is there now" is the question you have before "what shall I send".
  //
  // Its own file, static/js/amazonimages.js -- it is a new thing, not more of
  // this one (CLAUDE.md Rule 7).
  h += _ilLastSendBanner();
  h += '<div id="aimg_panel"></div>';

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

  _ilGroupOrder(Object.keys(groups)).forEach(function(g){
    const lbl = _IL_SHELF[g] || {};
    h += '<div style="margin:14px 0 6px">'
       + '<div style="font-size:11.5px;font-weight:600;opacity:.9">'
       + _ilEsc(lbl.title || g)
       + ' <span class="cc" style="font-weight:400">(' + groups[g].length + ')</span>'
       + '</div>'
       // WHAT THE SHELF IS FOR, in one line. The folder names alone ("secondary",
       // "aplus/premium/mobile") say where an image sits, not what Amazon wants
       // in it -- and premium A+ needing a separate desktop and mobile asset is
       // exactly the thing nobody knows until a submission is rejected.
       + (lbl.note ? '<div class="cc" style="font-size:10.5px;margin-top:2px">'
                     + _ilEsc(lbl.note) + '</div>' : '')
       + '</div>'
       + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px">';
    groups[g].forEach(function(f){
      const isMain = IMGLIB.main && (IMGLIB.main === f.url
                     || String(IMGLIB.main).indexOf(f.name) >= 0);
      const idx = tileNo++;
      const ptIndex = isMain ? 0 : (++ptNo);
      h += '<div style="border:1px solid ' + (isMain ? "var(--ok)" : "var(--line)")
         + ';border-radius:8px;overflow:hidden;background:var(--panel)">'
         + '<img src="' + _ilEsc(typeof thumbUrl==="function"?thumbUrl(f.url,160):f.url) + '" loading="lazy" '
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
         + (f.width ? (f.width + "×" + f.height) : "")
         // WHEN IT WAS MADE. Asked for directly, and it is the fact that turns
         // a wall of near-identical images into a history you can read: which
         // came first, which was the retry, which is the one from this morning.
         + (f.made_at ? (f.width ? " · " : "") + _ilWhen(f.made_at) : "")
         + '</div>'
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
       + '<button class="db-chip btn-primary" '
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
  // Fills itself in behind the library, so opening the library is not made to
  // wait on a call to Amazon.
  if(typeof amazonImagesLoad === "function") amazonImagesLoad(sku);
  else if(typeof amazonImagesRender === "function") amazonImagesRender();
}

// WHAT WAS JUST SENT, AND THE RECEIPT FOR IT.
//
// Drawn as part of the panel, so rebuilding the panel cannot destroy it -- which
// is precisely what used to happen. Carries Amazon's submission id, because that
// is the only thing that identifies the request afterwards, and it is dismissible
// rather than permanent.
function _ilLastSendBanner(){
  const s = IMGLIB.lastSend;
  if(!s) return "";
  return '<div style="border:1px solid #26403a;background:#10231f;border-radius:6px;'
    + 'padding:9px 11px;margin-bottom:12px;display:flex;gap:10px;align-items:center">'
    + '<img src="' + _ilEsc(typeof thumbUrl==="function"?thumbUrl(s.url,64):s.url) + '" alt="" style="width:38px;height:38px;'
    + 'object-fit:contain;background:#0d1220;border-radius:5px;flex:0 0 38px">'
    + '<div style="min-width:0;flex:1">'
    + '<div style="font-size:12px;font-weight:600">'
    + '<i class="ti ti-check"></i> Sent to Amazon as ' + _ilEsc(s.slot) + '</div>'
    + '<div class="cc" style="font-size:11px;line-height:1.45">'
    + _ilEsc(s.note || 'Amazon usually shows a new image within a few minutes.')
    + (s.submission_id
        ? ' Amazon’s reference: <code style="font-size:10px">'
          + _ilEsc(s.submission_id) + '</code>.'
        : '')
    + ' It appears in <b>On Amazon now</b> below once Amazon has taken it.'
    + '</div></div>'
    + '<button class="db-chip" onclick="ilDismissSend()" title="Hide this">'
    + 'Dismiss</button></div>';
}
function ilDismissSend(){ IMGLIB.lastSend = null; _ilDraw(); }

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

// THE PICTURES EITHER SIDE OF THE ONE YOU OPENED.
//
//     "allow me to swich between images within the folder of the sku by the
//      arrows as we have an option in the google drive"
//
// The viewer took ONE url and knew nothing about where it came from, so opening
// a picture, closing it, and opening the next was the only way through a folder
// of twelve. It now optionally takes the whole list and which one you clicked.
//
// Deliberately backwards compatible: called with two arguments it behaves
// exactly as before, no arrows, because it is the shared viewer for BOTH
// galleries (Rule 12) and the other one has no list to give it.
let _IL_SET = { items: [], i: 0 };

function ilPreview(url, name, items, index){
  if(!url) return;
  ilPreviewClose();
  // Normalise the list: [{url, name}] or plain urls, either is accepted so a
  // caller does not have to reshape its own data to use this.
  const list = Array.isArray(items) ? items.map(function(it){
    return (typeof it === "string") ? {url: it, name: it.split("/").pop()}
                                    : {url: it.url, name: it.name || (it.url||"").split("/").pop()};
  }).filter(function(x){ return x.url; }) : [];
  let at = (typeof index === "number") ? index
         : list.findIndex(function(x){ return x.url === url; });
  if(at < 0) at = 0;
  _IL_SET = { items: list, i: at };
  const many = list.length > 1;

  const el = document.createElement("div");
  el.id = "ilpreview";
  el.style.cssText = "position:fixed;inset:0;z-index:400;background:rgba(6,9,15,.92);"
    + "display:flex;align-items:center;justify-content:center;flex-direction:column;"
    + "gap:10px;padding:26px;cursor:zoom-out";
  el.innerHTML =
      (many ? '<button class="ilnav ilprev" title="Previous (left arrow)" '
            + 'onclick="event.stopPropagation();ilStep(-1)">'
            + '<i class="ti ti-chevron-left"></i></button>' : '')
    + (many ? '<button class="ilnav ilnext" title="Next (right arrow)" '
            + 'onclick="event.stopPropagation();ilStep(1)">'
            + '<i class="ti ti-chevron-right"></i></button>' : '')
    + '<img id="ilpreviewimg" src="' + _ilEsc(url) + '" alt="' + _ilEsc(name || "") + '" '
    + 'style="max-width:94vw;max-height:82vh;object-fit:contain;border-radius:8px;'
    + 'background:#0d1220;box-shadow:0 18px 60px rgba(0,0,0,.6);cursor:default">'
    + '<div style="display:flex;gap:8px;align-items:center;max-width:94vw">'
    + (many ? '<span class="cc" id="ilpreviewcount" style="font-size:11.5px;'
            + 'white-space:nowrap">' + (at + 1) + ' of ' + list.length + '</span>' : '')
    + '<span class="cc" id="ilpreviewname" style="font-size:11.5px;overflow:hidden;'
    + 'text-overflow:ellipsis;white-space:nowrap">' + _ilEsc(name || "") + '</span>'
    + '<button class="db-chip" id="ilpreviewdl" onclick="event.stopPropagation();ilDownloadOne('
    + jsArg(url) + ',' + jsArg(name || "image") + ')">'
    + '<i class="ti ti-download"></i> Download</button>'
    + '<button class="db-chip" id="ilpreviewopen" onclick="event.stopPropagation();window.open('
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

// Move to the picture n places away, WITHOUT rebuilding the viewer.
//
// Swapping the src rather than tearing the overlay down and putting a new one
// up is what makes this feel like Drive: the frame stays put, only the picture
// changes. Rebuilding would flash the backdrop on every arrow press.
//
// It STOPS at the ends rather than wrapping. Wrapping means you can never tell
// whether you have seen everything, which is the one thing a folder viewer has
// to be clear about.
function ilStep(n){
  const set = _IL_SET;
  if(!set || !set.items || set.items.length < 2) return;
  const to = set.i + n;
  if(to < 0 || to >= set.items.length) return;
  set.i = to;
  const it = set.items[to];
  const img = document.getElementById("ilpreviewimg");
  if(img){ img.src = it.url; img.alt = it.name || ""; }
  const nm = document.getElementById("ilpreviewname");
  if(nm) nm.textContent = it.name || "";
  const ct = document.getElementById("ilpreviewcount");
  if(ct) ct.textContent = (to + 1) + " of " + set.items.length;
  // The buttons carry the url in their onclick, so they have to move too --
  // otherwise Download quietly saves the picture you were looking at three
  // arrows ago, which is worse than having no button.
  const dl = document.getElementById("ilpreviewdl");
  if(dl) dl.setAttribute("onclick", "event.stopPropagation();ilDownloadOne("
    + jsArg(it.url) + "," + jsArg(it.name || "image") + ")");
  const op = document.getElementById("ilpreviewopen");
  if(op) op.setAttribute("onclick", "event.stopPropagation();window.open("
    + jsArg(it.url) + ",'_blank')");
  // Grey out the arrow that can no longer do anything.
  const prev = document.querySelector("#ilpreview .ilprev");
  const next = document.querySelector("#ilpreview .ilnext");
  if(prev) prev.classList.toggle("off", to <= 0);
  if(next) next.classList.toggle("off", to >= set.items.length - 1);
}

function _ilPreviewKey(ev){
  // The arrow keys, because that is how anyone actually moves through a folder
  // of pictures. Handled before Escape so the two cannot interfere.
  if(ev.key === "ArrowLeft" || ev.key === "ArrowRight"){
    ev.stopPropagation();
    ev.preventDefault();
    ilStep(ev.key === "ArrowLeft" ? -1 : 1);
    return;
  }
  // Escape closes the PREVIEW and stops there. Without this the same key would
  // reach the library behind it and shut both, so a glance at one picture would
  // cost you the panel you were working in.
  if(ev.key === "Escape"){
    ev.stopPropagation();
    ilPreviewClose();
  }
}

function ilPreviewClose(){
  _IL_SET = { items: [], i: 0 };
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
    +  'background:var(--accent);color:var(--accent-bg);border-color:var(--accent)" '
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
    // THE CONFIRMATION HAS TO SURVIVE THE REDRAW.
    //
    // "i have send 2 images to amazon as pt1 and pt2, but i did not received a
    //  confirmation that it was sent"
    //
    // It was written into #il_pushstatus and then openImageLibrary() below
    // rebuilt the whole panel, destroying the element about a tenth of a second
    // later. The message existed for less time than it takes to read. So it is
    // remembered here and drawn as part of the panel instead of into it.
    IMGLIB.lastSend = {slot: (slot.label || slotKey), url: url,
                       submission_id: (j.submission_id || ""),
                       note: (j.note || "")};
    if(st) st.innerHTML = '<span style="color:var(--ok)">✓ sent as '
                        + _ilEsc(slot.label||slotKey)+' — '+_ilEsc(j.note||"")+'</span>';
    // The app's own main-image copy only tracks MAIN, so only update it for that.
    if(slotKey === "main_product_image_locator"){
      await setMainImage(IMGLIB.sku, url, {quiet:true});
      IMGLIB.main = url;
    }
    await openImageLibrary(IMGLIB.sku, IMGLIB.live);
    // And read the listing back, so the slot filling in is something you WATCH
    // rather than something you are told. Forced, because the panel caches.
    if(typeof amazonImagesLoad === "function"){
      // Told WHICH slot, so the panel can mark the one image you just sent apart
      // from the ones that were already on the listing.
      if(typeof AIMG !== "undefined" && AIMG) AIMG.justSent = slotKey;
      amazonImagesLoad(IMGLIB.sku, true);
    }
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
