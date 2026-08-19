// static/js/imagelibrary.js — the Image Library as its own page.
//
//     "make the image library work on its own as a separate page, i should not
//      have to go from one page to another to just create images"
//
// The library has always been a modal over Listings, opened from a row. That is
// right when you are already looking at a row and want its pictures. It is
// wrong as the place you go to WORK on images, because every SKU means going
// back to Listings, finding the row, and opening it again — which is exactly
// the round trip being complained about.
//
// So this page holds the SAME library, inline, with a product picker above it.
// Not a copy of it: listingimages.js renders into this page's container instead
// of its modal (ilRenderInto), so there is ONE library and every improvement to
// it lands in both places (CLAUDE.md Rule 12). The row button still opens the
// modal, unchanged — that workflow was not asked to move.

let IMGP = { items: [], q: "", sku: "", loading: false, note: "" };

function _imgpQs() { return (typeof scopeQs === "function") ? scopeQs() : ""; }

function imgpRender() {
  const box = document.getElementById("imgp_picker");
  if (!box) return;

  let items = IMGP.items || [];
  if (IMGP.q) {
    const q = IMGP.q.toLowerCase();
    items = items.filter(function (r) {
      return (r.sku || "").toLowerCase().indexOf(q) >= 0 ||
             (r.asin || "").toLowerCase().indexOf(q) >= 0 ||
             (r.title || "").toLowerCase().indexOf(q) >= 0;
    });
  }

  let html =
    '<div class="imgp-bar">' +
    '<input class="ed" id="imgp_q" placeholder="Find a product — SKU, ASIN or title…" ' +
    'style="flex:1;min-width:200px" value="' + esc(IMGP.q) +
    '" oninput="imgpSearch(this.value)">' +
    '<span class="cc" style="font-size:11.5px">' + items.length + " of " +
    (IMGP.items || []).length + " products</span>" +
    "</div>";

  if (IMGP.note) {
    html += '<div class="sresfail">' + esc(IMGP.note) + "</div>";
  } else if (!items.length) {
    html += '<div class="cc" style="padding:12px;font-size:12.5px">' +
      (IMGP.loading ? "Loading products…" : "No products match.") + "</div>";
  } else {
    html += '<div class="imgp-list">';
    // Capped, and it says so. A picker of four hundred rows is a scrollbar
    // nobody uses; the search box is the way through it.
    items.slice(0, 60).forEach(function (r) {
      const on = (String(r.sku) === String(IMGP.sku)) ? " on" : "";
      html += '<div class="imgp-row' + on + '" onclick="imgpPick(' +
        jsArg(String(r.sku)) + ')">' +
        (r.img ? '<img src="' + esc(r.img) + '" loading="lazy" alt="">'
               : '<span class="imgp-noimg"><i class="ti ti-photo-off"></i></span>') +
        '<div class="imgp-meta">' +
        '<div class="imgp-t">' + esc((r.title || r.sku || "").slice(0, 58)) + "</div>" +
        '<div class="cc" style="font-size:10.5px">' + esc(r.sku || "") +
        (r.asin ? " · " + esc(r.asin) : "") + "</div></div></div>";
    });
    html += "</div>";
    if (items.length > 60) {
      html += '<div class="cc" style="font-size:11px;padding:6px 2px">Showing 60 of ' +
        items.length + " — narrow it with the search box.</div>";
    }
  }
  box.innerHTML = html;
}

function imgpSearch(v) {
  IMGP.q = v || "";
  imgpRender();
}

async function imgpPick(sku) {
  IMGP.sku = String(sku || "");
  imgpRender();
  const head = document.getElementById("imgp_which");
  const row = (IMGP.items || []).find(function (r) { return String(r.sku) === IMGP.sku; }) || {};
  if (head) {
    head.innerHTML = IMGP.sku
      ? "<b>" + esc(row.title || IMGP.sku) + "</b>" +
        '<span class="cc" style="font-size:11.5px"> · ' + esc(IMGP.sku) +
        (row.asin ? " · " + esc(row.asin) : "") + "</span>"
      : "";
  }
  // THE SAME LIBRARY, drawn into this page instead of its modal. Not a second
  // implementation — every fix to the library lands here too.
  if (typeof ilRenderInto === "function") ilRenderInto("imgp_lib");
  if (typeof openImageLibrary === "function") {
    await openImageLibrary(IMGP.sku, !!row.live);
  }
}

// THE SAME PICKER THE IMAGE STUDIO USES.
//
// This page grew its own list first; the Studio then needed the identical
// thing. Two copies would have drifted the first time either changed how a
// product is chosen, and the symptom is two screens disagreeing about what this
// account sells. One component now (CLAUDE.md Rule 12) -- and it fetches once
// and is shared, so opening both pages is one wait rather than two.
async function imgpLoad(force) {
  IMGP.loading = true; IMGP.note = ""; imgpRender();
  await ppLoad(force);
  IMGP.items = PPICK.items;
  IMGP.note = PPICK.error || "";
  IMGP.loading = false;
  imgpRender();
}

function imagelibOnOpen() {
  // The picker is the page; the library fills in once a product is chosen.
  if (!IMGP.items.length) imgpLoad();
  else imgpRender();
  const lib = document.getElementById("imgp_lib");
  if (lib && !IMGP.sku) {
    lib.innerHTML = '<div class="cc" style="padding:26px;text-align:center;' +
      'font-size:12.5px">Pick a product on the left to see and make its images.' +
      "<br>Everything the row button opened is here — without leaving the page." +
      "</div>";
  }
}

// LEAVING THIS PAGE MUST HAND THE LIBRARY BACK TO ITS MODAL.
//
// Otherwise the next time somebody presses the images button on a Listings row,
// the library renders into a container on a screen they are no longer looking
// at, and the modal opens empty. Found by thinking about what happens second,
// which is where this class of bug always is.
function imagelibOnLeave() {
  if (typeof ilRenderInto === "function") ilRenderInto("");
}
