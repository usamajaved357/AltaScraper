/* A thumbnail grid should not download full-size originals.
 *
 * A generated image is 4096 x 4096 and about 2 MB, and the image grids draw
 * them at 64-160px, dozens at a time. thumbUrl() already shrinks Amazon's CDN
 * links -- it rewrites the filename to ._SL320_. -- but it returned a local
 * /media path untouched, because nothing on our side answered a size request.
 *
 * Measured against the running app on a real 4096x4096 file:
 *
 *     original     2,010,349 bytes
 *     ?w=160           8,573 bytes   0.4%
 *     ?w=320          27,519 bytes   1.4%
 *     ?w=640          82,606 bytes   4.1%
 *
 * WHAT THIS DOES NOT CLAIM. It was NOT shown that this is the cause of "I
 * cannot see the thumbnails" -- two attempts to reproduce that in a headless
 * browser measured lazy-loading state and not a fault. This is a real and
 * measured reduction in what the grids download; whether it is the reported
 * symptom is still open.
 */
"use strict";
const fs = require("fs");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(62) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const read = p => fs.readFileSync("D:/AltaScraper/" + p, "utf8");
const THUMBS = read("static/js/thumbs.js");
const MEDIA = read("routes/media_routes.py");

// thumbUrl is a pure function; run the real one.
const ctx = {};
new Function("exports", THUMBS + "\nexports.thumbUrl = thumbUrl;")(ctx);
const t = ctx.thumbUrl;

console.log("== local media asks for a size ==");
// The buckets are _thumbBucket's, unchanged: <=80 -> 160, <=160 -> 320,
// <=320 -> 640. They are doubled for retina, which is why an 88px tile asks
// for 320 and not 160.
check("a 44px table row asks for the 160 bucket",
      t("/media/_acct/jack_uk/SKU/generated_1.jpg", 44),
      "/media/_acct/jack_uk/SKU/generated_1.jpg?w=160");
check("an 88px tile asks for 320", t("/media/x/y.jpg", 88), "/media/x/y.jpg?w=320");
check("a 160px tile asks for 320", t("/media/x/y.jpg", 160), "/media/x/y.jpg?w=320");
check("a 300px panel asks for 640", t("/media/x/y.jpg", 300), "/media/x/y.jpg?w=640");
// Above the buckets there is nothing to gain -- serve the original.
check("a full-size view is left alone", t("/media/x/y.jpg", 900), "/media/x/y.jpg");
check("an existing query string is respected",
      t("/media/x/y.jpg?v=2", 88), "/media/x/y.jpg?v=2&w=320");

console.log("\n== everything else behaves exactly as before ==");
check("an Amazon CDN link still gets its _SL bucket",
      t("https://m.media-amazon.com/images/I/abc.jpg", 44),
      "https://m.media-amazon.com/images/I/abc._SL160_.jpg");
check("a CDN link that already carries a size is untouched",
      t("https://m.media-amazon.com/images/I/abc._SL75_.jpg", 88),
      "https://m.media-amazon.com/images/I/abc._SL75_.jpg");
// EBAY IS NO LONGER A FOREIGN HOST. It was, and being left alone meant a
// draft's source picture was fetched at s-l1600 -- 115.9 KB measured against
// the live CDN -- to be drawn at 56px in a table row or 358px on a card.
// eBay names the size in the FILE rather than in a directive, so the rule is
// different from Amazon's but the arithmetic is the same one.
check("an eBay link is sized down to what is drawn",
      t("https://i.ebayimg.com/images/g/abc/s-l1600.jpg", 88),
      "https://i.ebayimg.com/images/g/abc/s-l400.jpg");
check("  a table row asks for less again",
      t("https://i.ebayimg.com/images/g/abc/s-l1600.jpg", 44),
      "https://i.ebayimg.com/images/g/abc/s-l225.jpg");
// A PICTURE IS ONLY EVER MADE SMALLER. Asking for more than what was stored
// would upscale somebody else's photo.
check("  one already smaller than needed is left alone",
      t("https://i.ebayimg.com/images/g/abc/s-l225.jpg", 358),
      "https://i.ebayimg.com/images/g/abc/s-l225.jpg");
// AND A SHAPE THIS RULE HAS NOT MET IS NOT GUESSED AT.
check("  an eBay URL of an unfamiliar shape is untouched",
      t("https://i.ebayimg.com/images/g/abc/photo.jpg", 88),
      "https://i.ebayimg.com/images/g/abc/photo.jpg");
check("a genuinely foreign host is untouched",
      t("https://drive.google.com/thumb/abc.jpg", 88),
      "https://drive.google.com/thumb/abc.jpg");
check("a data URI is untouched", t("data:image/png;base64,AAA", 88),
      "data:image/png;base64,AAA");
check("an empty value is untouched", t("", 88), "");
check("null is safe", t(null, 88), "");

console.log("\n== the server side ==");
truthy("media_serve reads ?w=", /request\.args\.get\("w"\)/.test(MEDIA));
truthy("  and only serves the sizes it caches",
       /_THUMB_SIZES = \(160, 320, 640\)/.test(MEDIA));
// A path is user data. "../../config.json" is a valid-looking relpath.
truthy("  a path outside the media root cannot be resized",
       /if not src\.startswith\(root\)/.test(MEDIA));
truthy("  a small file is served as-is rather than re-encoded",
       /os\.path\.getsize\(src\) < 60 \* 1024/.test(MEDIA));
// Replacing an image must replace its thumbnail, not serve yesterday's.
truthy("  the cache key includes the source's modification time",
       /getmtime\(src\)/.test(MEDIA));
// A resize failing must never cost you the picture.
truthy("  any failure falls back to the original",
       /except Exception:[\s\S]{0,200}send_from_directory\(_media_root\(\), relpath\)/.test(MEDIA));

console.log("\n== the grids actually ask for the small one ==");
for(const [file, needle] of [
      ["static/js/imagelibrary.js", "thumbUrl(r.img, 88)"],
      ["static/js/settings.js", "thumbUrl(f.img,64)"],
      ["static/js/listingimages.js", "thumbUrl(cover.url,160)"]]){
  truthy(file.split("/").pop() + " routes its grid through thumbUrl",
         read(file).indexOf(needle) >= 0);
}
// The full-size viewer must NOT be shrunk -- that is the one place the original
// is the point.
truthy("the full-size preview still loads the original",
       /id="ilpreviewimg" src="' \+ _ilEsc\(url\)/.test(read("static/js/listingimages.js")));

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
