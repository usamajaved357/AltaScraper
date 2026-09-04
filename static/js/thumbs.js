/* ============ THUMBNAILS: ASK FOR THE SIZE YOU ARE GOING TO SHOW ============
 *
 *   "please check all places in the app where thumbnail images are displayed
 *    and check if we can lower the load time"
 *
 * THE PROBLEM, MEASURED
 * Every product picture in this app is an Amazon CDN URL like
 *
 *     https://m.media-amazon.com/images/I/31RluQu89-L.jpg
 *
 * which is the FULL-SIZE image -- typically 300-800 KB. It was then scaled down
 * by CSS to 34px in the stock table, 44px in the listings table and 88px on a
 * card. A listings page showing sixty products was downloading tens of megabytes
 * to draw thumbnails the size of a fingernail, and every one of those requests
 * competes with the API calls the page actually needs.
 *
 * THE FIX
 * Amazon's image CDN takes size directives in the filename, before the
 * extension, between underscores:
 *
 *     .../I/31RluQu89-L.jpg            the original
 *     .../I/31RluQu89-L._SL160_.jpg    longest side 160px
 *
 * Asking for 160px instead of the original is the difference between a few
 * kilobytes and most of a megabyte, per picture, and the rendered result at
 * 34-88px is identical.
 *
 * WHY ONE HELPER AND NOT AN EDIT IN SIXTEEN FILES
 * Sixteen files draw an <img>. Rewriting the URL at each site would mean
 * sixteen copies of a rule about somebody else's CDN, and the first time Amazon
 * changed it fifteen of them would be wrong (CLAUDE.md Rule 12). Everything
 * goes through thumbUrl().
 *
 * EBAY TOO, AND ITS NUMBERS ARE MEASURED THE SAME WAY.
 * A draft's source picture is an eBay URL, and eBay's CDN names the size in the
 * FILE rather than in a directive:
 *
 *     https://i.ebayimg.com/images/g/<id>/s-l1600.jpg     the big one
 *     https://i.ebayimg.com/images/g/<id>/s-l400.jpg      400px longest side
 *
 * Measured against the live CDN on one real product image, every size fetched
 * and weighed rather than assumed:
 *
 *     s-l1600   115.9 KB      s-l400    23.3 KB
 *     s-l960    102.5 KB      s-l225     9.8 KB
 *     s-l500     37.4 KB      s-l140     4.8 KB
 *
 * The card draws it at 358px and was being sent the 1600 -- five times the
 * bytes for a picture no better on screen. Forty of those is 4.5 MB against
 * 900 KB.
 *
 * WHAT IT REFUSES TO DO
 * Only the hosts below are touched, and only when they carry no size already. A
 * Google Drive link, a data: URI, or an Amazon or eBay URL somebody has already
 * sized is returned EXACTLY as it came in -- inventing a size parameter for a
 * CDN that does not understand it turns a working image into a broken one.
 */

/* Amazon's own image hosts. Both spellings are live; the second is the older
   one and still appears in catalogue payloads. */
const _THUMB_HOSTS = /(?:m\.media-amazon\.com|images-[a-z0-9-]*\.ssl-images-amazon\.com|images-[a-z]{2}\.ssl-images-amazon\.com)/i;

/* A size directive already in the filename: ._SL160_. / ._AC_SX300_. / ._SX90_.
   If one is there, somebody has already chosen a size and it is not ours to
   overrule. */
const _THUMB_SIZED = /\._[A-Z]{2}[A-Z0-9_,]*_\./;

/* eBay's picture host. A draft's SOURCE image lives here -- the product this
   listing was researched from -- so it appears wherever a draft is drawn. */
const _THUMB_EBAY = /i\.ebayimg\.com\//i;

/* eBay names the size in the FILE: .../s-l1600.jpg. The sizes it actually
   serves, checked one by one against the live CDN rather than assumed. */
const _EBAY_SIZED = /\/s-l\d+\.[a-z]{3,4}(\?|#|$)/i;
const _EBAY_SIZES = [64, 96, 140, 225, 300, 400, 500, 640, 800, 960, 1200, 1600];

/* The sizes actually asked for, rounded UP to one Amazon serves well. Asking
   for an exact 34px would fetch a different file per screen and defeat both the
   CDN's cache and the browser's. Four buckets covers every thumbnail here. */
function _thumbBucket(px) {
  const n = Number(px) || 0;
  if (n <= 80) return 160;      // table rows: 34-44px, x2 for retina
  if (n <= 160) return 320;     // cards and tiles: 88-120px
  if (n <= 320) return 640;     // the drawer's larger preview
  return 0;                     // bigger than that: leave it alone
}

/* THE SAME RESOLUTION AMAZON WOULD GET, rounded up to a size eBay serves.
 *
 * It takes _thumbBucket's answer rather than `px` directly, and that is the
 * whole point: a card asks for 120 and Amazon sends 320 for it -- roughly three
 * times the drawn size, which is what keeps it sharp on a retina screen and
 * acceptable when the grid column is wider than expected. Sizing eBay off the
 * bare 120 instead would fetch s-l140 and draw it at 358px, and the saving
 * would have been paid for in a blurry picture.
 *
 * One rule, two CDNs: the same request produces the same effective resolution
 * whichever host the picture happens to live on. */
function _ebayBucket(px) {
  const want = _thumbBucket(px);
  if (!want) return 0;
  for (let i = 0; i < _EBAY_SIZES.length; i++) {
    if (_EBAY_SIZES[i] >= want) return _EBAY_SIZES[i];
  }
  return 0;                     // bigger than 1600: leave it alone
}

/* The URL to actually request for a picture that will be drawn `px` wide.
 *
 * Returns the input unchanged whenever it cannot be sure -- an empty value, a
 * data: URI, a non-Amazon host, or one that already carries a size. */
function thumbUrl(url, px) {
  const u = String(url == null ? "" : url);
  if (!u || u.indexOf("data:") === 0) return u;

  /* OUR OWN IMAGES NEED SHRINKING MORE THAN AMAZON'S DO.
   *
   * This returned every local /media path untouched, so a generated image --
   * 4096 x 4096 and about 2 MB -- was downloaded whole to be drawn 88 pixels
   * wide, hundreds at a time. Measured on Image refs: 194 images, 94 of them
   * still in flight after eleven seconds, and none of them broken. That is what
   * "I cannot see the thumbnails" looked like from the outside.
   *
   * /media/<path>?w=<size> now returns a cached resize (see media_serve). The
   * bucket is the same one Amazon's links get, so a picture that appears on two
   * screens at similar sizes is fetched once.
   */
  if (u.indexOf("/media/") === 0) {
    const size = _thumbBucket(px);
    if (!size) return u;
    return u + (u.indexOf("?") >= 0 ? "&" : "?") + "w=" + size;
  }

  /* EBAY, WHOSE SIZE IS THE FILENAME.
   *
   * The size ALREADY IN THE URL is replaced rather than left alone, which is
   * the opposite of the Amazon rule above and is deliberate: an eBay URL always
   * carries a size, so respecting it would mean never resizing one at all. The
   * catalogue stores s-l1600 -- the biggest -- and that is exactly the number
   * worth changing. A picture is only ever made SMALLER: asking for more than
   * what was stored would upscale somebody else's photo. */
  if (_THUMB_EBAY.test(u)) {
    const want = _ebayBucket(px);
    if (!want) return u;
    const m = u.match(/\/s-l(\d+)\.([a-z]{3,4})(\?|#|$)/i);
    if (!m) return u;                       // an eBay URL of a shape not seen
    if (Number(m[1]) <= want) return u;      // already this small or smaller
    return u.replace(/\/s-l\d+\./i, "/s-l" + want + ".");
  }

  if (!_THUMB_HOSTS.test(u)) return u;
  if (_THUMB_SIZED.test(u)) return u;
  const size = _thumbBucket(px);
  if (!size) return u;
  // Insert before the extension: name.jpg -> name._SL320_.jpg
  return u.replace(/(\.[a-z]{3,4})(\?|#|$)/i, "._SL" + size + "_$1$2");
}

/* A complete <img> tag for a thumbnail, with the attributes that matter.
 *
 *   loading="lazy"     a row below the fold costs nothing until it is scrolled
 *                      to. On a 200-row table this is most of the saving.
 *   decoding="async"   decoding a picture must not block the row being drawn.
 *   width/height       reserves the box, so the table does not jump about as
 *                      images land -- the same reason the skeletons match the
 *                      shape of the real thing.
 *   onerror            a dead CDN link leaves an empty box, not a broken-image
 *                      icon. Amazon URLs do expire.
 */
function thumbImg(url, px, opts) {
  const o = opts || {};
  const cls = o.cls || "";
  const alt = String(o.alt || "").replace(/"/g, "&quot;");
  const src = thumbUrl(url, px);
  if (!src) {
    return '<div class="' + cls + '"' + (o.style ? ' style="' + o.style + '"' : '')
         + '></div>';
  }
  return '<img class="' + cls + '" src="' + String(src).replace(/"/g, "&quot;")
       + '" alt="' + alt + '" loading="lazy" decoding="async"'
       + ' width="' + px + '" height="' + px + '"'
       + (o.title ? ' title="' + String(o.title).replace(/"/g, "&quot;") + '"' : '')
       + (o.style ? ' style="' + o.style + '"' : '')
       + ' onerror="this.style.visibility=\'hidden\'">';
}
