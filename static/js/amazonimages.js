// ============ WHAT IS ACTUALLY ON AMAZON, SLOT BY SLOT ============
//
// "i have send 2 images to amazon as pt1 and pt2, but i did not received a
//  confirmation that it was sent and how can i verify if the images are sent
//  inside the app, is there any option to see the uploaded images to amazon in
//  the app, and it should be truth, only reflect images in the app when the
//  images actually reflects on the pdp"
//
// There was no such option. You could send to a slot and the dropdown would
// afterwards say "— has one", which is the app telling you a slot is occupied
// without showing you by what. Sending an image and then having to open Seller
// Central to find out whether it arrived is not a feature that finished.
//
// WHAT "TRUTH" MEANS HERE, EXACTLY, because it is not one thing:
//
//   The SLOT images come from Amazon's getListingsItem attributes -- the URL
//   Amazon has on record for that slot. If PT1 shows your image, Amazon
//   accepted it into PT1.
//
//   The SHOPPER image comes from the same call's `summaries.mainImage` -- the
//   rendition Amazon actually serves on the product page. It is re-hosted and
//   re-rendered, so its URL never matches the one that was submitted even when
//   it IS the same photograph.
//
//   The ISSUES come from the listing itself. An image Amazon took and then
//   rejected shows up there and nowhere else, so they are shown beside the
//   slots rather than on some other screen.
//
// Both are labelled for what they are. Calling either one "the image on the
// PDP" on its own would be the app claiming more than it can see.

// `justSent` is the slot the last send went to, so the panel can tell APART the
// image you have this minute put there from the eight that were already on the
// listing.
//
// Without it the panel is a wall of nine filled slots that appears the moment
// you send one, and it reads as "it sent all of them" -- which is exactly how it
// was read: "when i clicked on send to amazon on 1 button it sent all the images
// to amazon instead of sending only 1 image".
//
// It did not. Checked on ALTA-SLASHER-800-PARENT: 1 of 16 slots filled before,
// one image sent to other_product_image_locator_1, 2 of 16 after, exactly one
// slot changed. Both send paths build a single patch -- listing/images.build_patch
// for the slot picker and _build_patches({"main_image": ...}) for the older
// button. Neither can send more than one. The panel was telling the truth and
// saying it badly.
let AIMG = {sku: "", state: "", data: null, err: "", justSent: ""};

function _aiEsc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// The slot's name as it is spoken about -- MAIN, PT1, SWATCH -- rather than as
// Amazon spells it. One place, because the grid and the sentence above it both
// name slots and naming the same slot two ways in one panel is worse than either.
function _aiTag(key){
  return String(key || "")
    .replace("main_product_image_locator", "MAIN")
    .replace("other_product_image_locator_", "PT")
    .replace("swatch_product_image_locator", "SWATCH")
    .replace(/_/g, " ");
}

// Load, or reload, what Amazon holds for one SKU.
async function amazonImagesLoad(sku, force){
  if(!sku) return;
  if(AIMG.sku === sku && AIMG.state === "ready" && !force) return;
  if(AIMG.state === "loading") return;
  // A different listing wipes it: "you just sent this" belongs to one SKU.
  if(AIMG.sku !== sku) AIMG.justSent = "";
  AIMG.sku = sku; AIMG.state = "loading"; AIMG.err = "";
  amazonImagesRender();
  try{
    const j = await (await fetch("/listing/image_slots?sku="
                                 + encodeURIComponent(sku))).json();
    // A NEWER SKU MAY HAVE BEEN OPENED while this was in flight. Painting this
    // answer onto that listing would show one product's images under another's
    // name, which is the one mistake this panel exists to prevent.
    if(AIMG.sku !== sku) return;
    if(!j || !j.ok){
      AIMG.state = "failed";
      AIMG.err = (j && j.error) || "Amazon would not answer";
    } else if(!j.checked){
      AIMG.state = "failed";
      AIMG.err = j.note || "This product type's image slots could not be read";
    } else {
      AIMG.data = j; AIMG.state = "ready";
    }
  }catch(e){
    if(AIMG.sku !== sku) return;
    AIMG.state = "failed"; AIMG.err = String(e);
  }
  amazonImagesRender();
}

function amazonImagesRefresh(){
  amazonImagesLoad(AIMG.sku, true);
}

function amazonImagesRender(){
  const host = document.getElementById("aimg_panel");
  if(!host) return;
  host.innerHTML = amazonImagesHtml();
}

function amazonImagesHtml(){
  if(AIMG.state === "loading"){
    return '<div class="cc" style="font-size:11.5px;padding:10px">'
         + '<span class="genspin"></span> asking Amazon what it holds for '
         + _aiEsc(AIMG.sku) + '…</div>';
  }
  if(AIMG.state === "failed"){
    // NOT dressed up as "no images". A listing that could not be read and a
    // listing with an empty gallery look identical on screen unless one of them
    // says so, and only one of them means "try again".
    return '<div class="cc" style="font-size:11.5px;padding:10px;'
         + 'border:1px solid var(--red-line);background:var(--red-bg);border-radius:6px">'
         + '<i class="ti ti-alert-triangle"></i> Could not read this listing’s '
         + 'images from Amazon: ' + _aiEsc(AIMG.err)
         + ' <button class="db-chip" style="margin-left:6px" '
         + 'onclick="amazonImagesRefresh()">Try again</button></div>';
  }
  const d = AIMG.data;
  if(!d) return "";
  const slots = d.slots || [];
  const filled = slots.filter(function(s){ return s.current; });

  let h = '<div class="panelcard" style="margin-bottom:12px">'
    + '<div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;'
    + 'margin-bottom:8px">'
    + '<span style="font-size:13px;font-weight:600">On Amazon now</span>'
    + '<span class="cc" style="font-size:11.5px">'
    + filled.length + ' of ' + slots.length + ' slots filled'
    // SAID IN WORDS, not left to be inferred from a grid. "9 filled" right after
    // you sent one is the sentence that needs completing.
    + (AIMG.justSent
        ? ' — you have just sent <b>one</b>, to '
          + _aiEsc(_aiTag(AIMG.justSent)) + '. The rest were already here.'
        : '')
    + '</span><span style="flex:1"></span>'
    + '<button class="db-chip" onclick="amazonImagesRefresh()" title="'
    + 'Read the listing from Amazon again. A slot you have just sent to can take '
    + 'a few minutes to show here.">'
    + '<i class="ti ti-refresh"></i> Re-read from Amazon</button></div>';

  // WHAT SHOPPERS SEE, kept apart from the slots and labelled as a different
  // thing. Amazon re-hosts and re-renders the main image, so its URL never
  // matches what was submitted even when it is the same photograph -- showing
  // them side by side without saying that invites "these do not match".
  if(d.shopper_image){
    h += '<div style="display:flex;gap:10px;align-items:center;margin-bottom:10px;'
      +  'padding-bottom:10px;border-bottom:1px solid var(--line2)">'
      +  '<img src="' + _aiEsc(d.shopper_image) + '" alt="" loading="lazy" '
      +  'style="width:56px;height:56px;object-fit:contain;background:var(--sidebar);'
      +  'border-radius:6px">'
      +  '<div style="min-width:0"><div style="font-size:12px;font-weight:600">'
      +  'The picture on the product page</div>'
      +  '<div class="cc" style="font-size:11px;line-height:1.45">'
      +  'Amazon’s own rendition, from the listing summary. This is what a '
      +  'shopper sees. Its address will never match the one you sent, because '
      +  'Amazon re-hosts and re-sizes it.</div></div></div>';
  }

  if(d.issues && d.issues.length){
    // An image Amazon accepted and then rejected appears here and nowhere else.
    h += '<div style="font-size:11.5px;margin-bottom:10px;padding:8px 10px;'
      +  'border:1px solid var(--warn-line);background:var(--warn-bg);border-radius:6px">'
      +  '<b>Amazon has something to say about this listing</b>'
      +  '<ul style="margin:5px 0 0 16px;padding:0;line-height:1.5">'
      +  d.issues.map(function(i){
           return '<li>' + _aiEsc(i.message || "")
                + (i.severity ? ' <span class="cc">(' + _aiEsc(i.severity) + ')</span>' : '')
                + '</li>'; }).join("")
      +  '</ul></div>';
  }

  h += '<div style="display:flex;gap:9px;flex-wrap:wrap">';
  slots.forEach(function(s){
    const tag = _aiTag(s.key);
    const mine = (AIMG.justSent && s.key === AIMG.justSent);
    h += '<div style="width:96px">'
      + (s.current
          ? '<a href="' + _aiEsc(s.current) + '" target="_blank" rel="noopener" '
            + 'title="Open the full-size image Amazon holds for ' + _aiEsc(tag) + '">'
            + '<img src="' + _aiEsc(s.current) + '" alt="" loading="lazy" '
            + 'style="width:96px;height:96px;object-fit:contain;background:var(--sidebar);'
            + 'border-radius:6px;border:1px solid '
            + (mine ? 'var(--ok,#8fd694);box-shadow:0 0 0 1px var(--ok,var(--ok-line))'
                    : '#26303f') + '"></a>'
          : '<div style="width:96px;height:96px;border-radius:6px;'
            + 'background:var(--sidebar);border:1px dashed var(--line2);display:flex;'
            + 'align-items:center;justify-content:center">'
            + '<span class="cc" style="font-size:10px">empty</span></div>')
      + '<div style="font-size:10px;margin-top:4px;font-weight:600">'
      + _aiEsc(tag) + '</div>'
      + '<div class="cc" style="font-size:9.5px;line-height:1.3'
      + (mine ? ';color:var(--ok,var(--ok))' : '') + '">'
      + (mine ? 'you just sent this'
              : (s.current ? 'was already here' : 'nothing sent'))
      + '</div></div>';
  });
  h += '</div>';

  if(!filled.length){
    h += '<div class="cc" style="font-size:11.5px;margin-top:9px">'
      +  'Amazon holds no images for this listing yet. If you have just sent '
      +  'some, give it a few minutes and press Re-read.</div>';
  }
  return h + '</div>';
}
