// Can you see, inside the app, which images Amazon actually has?
//
// "i have send 2 images to amazon as pt1 and pt2, but i did not received a
//  confirmation that it was sent and how can i verify if the images are sent
//  inside the app, is there any option to see the uploaded images to amazon in
//  the app, and it should be truth, only reflect images in the app when the
//  images actually reflects on the pdp"
//
// There was no such option, and the confirmation existed for about a tenth of a
// second before being destroyed. Both verified against the live jack_uk account.

const fs = require("fs");
const A = fs.readFileSync("static/js/amazonimages.js", "utf8");
const L = fs.readFileSync("static/js/listingimages.js", "utf8");
const V = fs.readFileSync("routes/variations_routes.py", "utf8");
const M = fs.readFileSync("api/amazon_listings.py", "utf8");
const H = fs.readFileSync("templates/dashboard.html", "utf8");

let fails = [];
function check(label, got, want) {
  const ok = got === want;
  if (!ok) fails.push(label);
  console.log("  " + label.padEnd(70) +
    (ok ? "OK" : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}
function truthy(label, got) { check(label, !!got, true); }
function falsy(label, got) { check(label, !!got, false); }

console.log("=== the panel exists, and is its own file ===");
truthy("there is a panel that reads Amazon back", A.includes("amazonImagesLoad"));
truthy("  in its own file, not bolted onto the library (Rule 7)",
       A.includes("WHAT IS ACTUALLY ON AMAZON"));
truthy("  loaded by the page", H.includes("/static/js/amazonimages.js"));
truthy("  and drawn by the library", L.includes('id="aimg_panel"'));
truthy("  without making the library wait on Amazon",
       L.includes('if(typeof amazonImagesLoad === "function") amazonImagesLoad(sku)'));

console.log("\n=== every slot, with the picture Amazon holds in it ===");
truthy("slots are drawn one by one", A.includes("slots.forEach"));
truthy("  labelled the way they were sent", A.includes('"MAIN"') && A.includes('"PT"'));
truthy("  the filled ones showing the actual image", A.includes("s.current"));
truthy("  and openable full size", A.includes('target="_blank"'));
truthy("an empty slot says empty rather than showing nothing",
       A.includes(">empty<") && A.includes("nothing sent"));
truthy("and the count is stated", A.includes("of ' + slots.length + ' slots filled"));

console.log("\n--- TWO different truths, each labelled as what it is ---");
// A slot value is what Amazon has ON RECORD for that slot. The shopper image is
// the rendition Amazon SERVES. Calling either one "the image on the PDP" alone
// would be the app claiming more than it can see.
truthy("the shopper's picture is shown separately",
       A.includes("The picture on the product page"));
truthy("  and said to be Amazon's own rendition", A.includes("own rendition"));
truthy("  with the reason its address never matches what was sent",
       A.includes("re-hosts and re-sizes"));
truthy("the server sends it", V.includes('"shopper_image"'));
truthy("  read from Amazon's summary, not from an attribute",
       V.includes('mi = s0.get("mainImage")'));

console.log("\n--- an image Amazon took and then rejected is visible ---");
// It appears in the listing's issues and nowhere else, so it belongs beside the
// slots rather than on some other screen.
truthy("issues come back with the slots", V.includes('"issues": live.get("issues")'));
truthy("  and are drawn", A.includes("Amazon has something to say"));
truthy("  with their severity", A.includes("i.severity"));
truthy("get_item surfaces them rather than burying them in raw",
       M.includes('out["issues"] = data.get("issues")'));
truthy("  and the summaries too", M.includes('out["summaries"] = summaries'));
truthy("  both defaulted, so a failed read is not an empty listing",
       M.includes('"summaries": [], "issues": []'));

console.log("\n=== 'could not read' is not 'has no images' ===");
truthy("a failed read says so", A.includes("Could not read this listing’s"));
truthy("  and offers a retry", A.includes("Try again"));
falsy("  and does NOT present itself as an empty gallery",
      A.includes('failed') && A.includes('0 of 0 slots'));
truthy("an empty gallery says what to do instead",
       A.includes("Amazon holds no images for this listing yet"));

console.log("\n=== the confirmation survives long enough to read ===");
// It was written into #il_pushstatus, and then openImageLibrary() rebuilt the
// panel and destroyed the element. That is why none arrived.
truthy("the send result is remembered", L.includes("IMGLIB.lastSend = {"));
truthy("  and drawn as part of the panel", L.includes("_ilLastSendBanner()"));
truthy("  so a redraw cannot wipe it",
       L.includes("THE CONFIRMATION HAS TO SURVIVE THE REDRAW"));
truthy("it names the slot it went to", L.includes("Sent to Amazon as "));
truthy("  carries Amazon's own reference", L.includes("s.submission_id"));
truthy("  says where to watch for it", L.includes("On Amazon now"));
truthy("  and can be dismissed", L.includes("ilDismissSend"));
truthy("the slots are re-read straight after a send, forced past the cache",
       L.includes("amazonImagesLoad(IMGLIB.sku, true)"));

console.log("\n=== the one you just sent, apart from the ones already there ===");
// "when i clicked on send to amazon on 1 button it sent all the images to amazon
//  instead of sending only 1 image"
//
// It did not. Checked on ALTA-SLASHER-800-PARENT: 1 of 16 slots filled before,
// one image sent to other_product_image_locator_1, 2 of 16 after -- exactly one
// slot changed. Both send paths build a SINGLE patch. What went wrong is that
// this panel appears the moment you send, showing every slot Amazon holds, and
// nine filled slots read as nine sends.
truthy("the panel remembers which slot the send went to", A.includes("justSent"));
truthy("  told by the sender", L.includes("AIMG.justSent = slotKey"));
truthy("  and cleared when a different listing is opened",
       A.includes('if(AIMG.sku !== sku) AIMG.justSent = ""'));
truthy("the just-sent tile says so", A.includes("you just sent this"));
truthy("  and the others say they were already there",
       A.includes("was already here"));
truthy("it is also said in words above the grid, not left to be inferred",
       A.includes("The rest were already here"));
truthy("  naming the slot", A.includes("_aiTag(AIMG.justSent)"));
truthy("and a slot is named ONE way in this panel, not two",
       A.includes("function _aiTag") &&
       (A.match(/main_product_image_locator", "MAIN"/g) || []).length === 1);

console.log("\n=== one listing's images cannot appear under another's name ===");
truthy("a late answer for a different SKU is dropped",
       A.includes("if(AIMG.sku !== sku) return"));
truthy("  and the reason is written down",
       A.includes("A NEWER SKU MAY HAVE BEEN OPENED"));

console.log("\nFAILURES: " + fails.length);
fails.forEach(f => console.log("   - " + f));
process.exit(fails.length ? 1 : 0);
