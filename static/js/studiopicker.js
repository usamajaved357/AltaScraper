// static/js/studiopicker.js — the Image Studio picks its own product.
//
//     "i wanted the image studio as a separate page and wanted to work it as a
//      separate page, i should not have to go to another screen to generate
//      image to complete the image gen pipeline. the image studio page all
//      alone should be able to do it"
//
// The Studio's empty state said, in so many words, "Open Listings and press the
// photo button" — which IS the round trip. It was a screen that could only be
// entered from somewhere else, carrying state somewhere else had set up.
//
// Now it fills STUDIO itself, from the shared product picker, and everything
// downstream — main images, secondary sets, A+ modules, the concept
// strategist — works exactly as it did when Listings handed it over. Nothing in
// the pipeline changed; it just no longer needs a chauffeur.
//
// LISTINGS STILL WORKS THE OLD WAY. Selecting rows there and pressing the photo
// button sets STUDIO and opens this screen, untouched. That workflow is right
// when you are already looking at the rows, and it was not asked to move.

let SPICK = { q: "", open: false };

function studioPickerRender() {
  const box = document.getElementById("studio_picker");
  if (!box) return;
  const cur = (typeof STUDIO !== "undefined" && STUDIO && STUDIO.skus
               && STUDIO.skus.length === 1) ? STUDIO.skus[0] : "";
  ppRender("studio_picker_list", {
    q: SPICK.q, selected: cur,
    onSearchName: "studioPickerSearch",
    pickName: "studioPickerChoose",
  });
}

function studioPickerSearch(v) {
  SPICK.q = v || "";
  studioPickerRender();
}

// Set STUDIO up exactly as Listings does, so everything downstream is unchanged.
function studioPickerChoose(it) {
  if (!it) return;
  try {
    const brand = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT)
      ? ((CUR_ACCOUNT.brands && CUR_ACCOUNT.brands.length)
         ? CUR_ACCOUNT.brands[0] : (CUR_ACCOUNT.label || ""))
      : "";
    STUDIO = {
      skus: [it.sku],
      // The SAME shape Listings builds, including the attributes -- they are
      // the FACTS the A+ and secondary generators are built from, and the
      // Research ASIN handoff had to be fixed for dropping exactly these.
      items: [{ sku: it.sku, title: it.title, asin: it.asin,
                source_image: it.img, images: it.img ? [it.img] : [],
                attributes: it.attributes || {} }],
      brand: brand,
      manualRef: it.img || "",
      recipes: [], results: {},
    };
    SPICK.open = false;
    studioPickerRender();
    if (typeof renderStudio === "function") {
      if (typeof loadRecipes === "function") {
        loadRecipes().then(function () { try { renderStudio(); } catch (e) {} });
      } else {
        renderStudio();
      }
    }
    if (typeof studioLoadModels === "function") studioLoadModels();
    if (typeof loadStudioInstructions === "function") loadStudioInstructions();
  } catch (e) {
    if (typeof toast === "function") toast("Could not open that product: " + e);
  }
}

// Called when the Image Studio screen opens.
//
// NAMED SEPARATELY, and that is not cosmetic. genimage.js already defines
// imagestudioOnOpen(), and this file loads AFTER it -- so calling mine the same
// thing would have silently replaced the existing one and quietly stopped the
// studio re-rendering what Listings had handed it. Nothing would have thrown;
// the screen would just have been blank on the path that used to work.
//
// So this ADDS the picker and then calls the original, which still owns
// everything about drawing the studio itself.
async function studioPickerOnOpen() {
  const box = document.getElementById("studio_picker");
  if (box && !document.getElementById("studio_picker_list")) {
    box.innerHTML =
      '<div class="imgp-left" style="position:static;max-height:none;margin-bottom:12px">' +
      '<div style="font-weight:600;font-size:12.5px;padding:0 2px 6px">' +
      "Which product?</div>" +
      '<div id="studio_picker_list"></div></div>';
  }
  await ppLoad();
  studioPickerRender();
  // Anything already set up by Listings or Research ASIN stays exactly as it
  // was -- this screen adds a way IN, it does not take one over. The original
  // handler is what knows how to draw it.
  if (typeof imagestudioOnOpen === "function") {
    try { imagestudioOnOpen(); } catch (e) {}
  }
}
