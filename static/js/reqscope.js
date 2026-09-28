// ============ WHICH ACCOUNT IS THIS REQUEST ABOUT? ============
//
// Every request that finds a row BY SKU has to say whose row it means.
//
// The server finds a SKU inside whatever workspace IT currently has selected.
// That is remembered state, and the browser's idea of the open account and the
// server's can differ for a moment on every account switch -- a request sent
// before the switch lands is answered for the previous account, and a reply
// arriving after it is painted over the new one. That is not hypothetical: it
// is the bug that showed one account's listings under another's name, and the
// one that showed another company's order lines and buyer postcodes.
//
// /rows_all was fixed by making the browser NAME the account and the server
// REFUSE a disagreement rather than answer. /row, /edit, /delete and
// /live/pull_row are reached from the same screen, one keystroke later, and had
// no such check. These two helpers are how they get one.
//
// WHY A HELPER AND NOT SIXTEEN HAND-EDITS. There were sixteen call sites across
// eight files. Written out by hand, the seventeenth forgets -- and the failure
// is silent, because a request with no account is deliberately still served
// (that is what lets the guard ship before every caller is taught). So the
// thing that is easy to write is the thing that is correct: acctBody(...) and
// acctUrl(...) are shorter than what they replace.
//
// HOW BIG WAS THE HOLE, REALLY. Measured before writing this: 282 rows across
// five accounts, 282 distinct SKUs, none shared between two accounts. So today
// a stale account yields "sku not found", not the wrong row -- a latent hazard,
// not an active leak. It is still worth closing: two of the four routes are
// WRITES (one is a DELETE that can fall back to a bare row NUMBER), and nothing
// keeps SKUs unique -- they are price_days_ASIN, so two accounts sourcing the
// same product at the same price collide.

/* The account the browser believes is open, or "" before one is chosen. */
function acctId(){
  try{
    if(typeof CUR_ACCOUNT === "undefined" || !CUR_ACCOUNT) return "";
    return String(CUR_ACCOUNT.id || "");
  }catch(e){ return ""; }
}

/* Stamp a POST body with the open account.
 *
 *     body: JSON.stringify(acctBody({sku, target, key, value}))
 *
 * Adds nothing when no account is open, so the request behaves exactly as it
 * did before -- the server treats a missing account as "said nothing" and
 * serves it. An account that IS named and disagrees is refused. */
function acctBody(obj){
  return acctBodyFor(obj, acctId());
}

/* Stamp a POST body with a GIVEN account -- the one a bulk action started in.
 *
 *     const pin = acctId();                 // once, before the loop
 *     for(...){
 *       if(acctId() !== pin) break;         // switched part-way: stop
 *       fetch(url, {body: JSON.stringify(acctBodyFor({sku}, pin))});
 *     }
 *
 * acctBody() reads the account afresh on every call, so a loop built on it
 * sent every SKU after an account switch to the NEW account's same-SKU rows --
 * a GTIN declaration, an arm, a delete on Amazon (master audit S1, 28 Sep
 * 2026). A loop takes the account once and names it on every request. */
function acctBodyFor(obj, id){
  if(!id) return obj || {};
  return Object.assign({}, obj || {}, {account: id});
}

/* Stamp a GET url with the open account.
 *
 *     await fetch(acctUrl("/row?sku=" + encodeURIComponent(sku)))
 *
 * Picks ? or & by looking at the url, so it is safe on a path with or without
 * an existing query string. */
function acctUrl(url){
  const id = acctId();
  if(!id) return url;
  const u = String(url || "");
  // Already names one: leave it -- that caller chose deliberately, and two
  // account= values would be read differently by different routes.
  if(/[?&]account=/.test(u)) return u;
  return u + (u.indexOf("?") >= 0 ? "&" : "?") + "account=" + encodeURIComponent(id);
}

// ============ PATHS THAT FOLLOW THE TAB, NOT THE SERVER ============
//
// These routes answered for the SERVER'S open account -- one for every tab,
// owned by whichever tab switched last. With two tabs open, the image library
// showed the other account's pictures, an upload was filed under it, and
// Variations read (and could push to) it. Found by the two-tab check in
// tools/browser_smoke.py (28 Sep 2026).
//
// The server now reads the account a request names (domain/request_account
// .current). Naming it at ~40 call sites by hand is how the forty-first
// forgets, so it is done here, once, for the paths listed and nothing else: a
// url that already names an account is left alone. A trailing "/" means every
// path under it. The permission guard checks the named account as usual.
const ACCT_SCOPED_PATHS = [
  "/media/list", "/media/upload", "/media/zip", "/media/delete",
  "/genimage/", "/variations/", "/run/health",
  "/listing/image_slots", "/listing/image_push", "/listing/push_image",
  // Added by the full two-tab audit (28 Sep 2026): callers that sent no
  // account at all, so the server's open one was used -- Ads keys saved,
  // queue rows written, Drive uploads, Miles runs, variants queued, sync.
  "/settings/ads", "/settings/ads/", "/input/", "/drive/", "/miles/", "/miles_template/render",
  "/sync/", "/variant/", "/agent/", "/submit/target", "/submit/precheck",
  "/dup_check",
];
/* ...and the tab's MARKETPLACE with it, unless the url already names one. The
 * server otherwise uses the marketplace last picked in ANY tab: the account
 * followed this tab while the country followed another, and Variations could
 * publish to the wrong country's listings (two-tab review). "All marketplaces"
 * is not a country and is not sent. */
function acctMktUrl(url){
  const u = String(url || "");
  if(/[?&]marketplace=/.test(u)) return u;
  let m = "";
  try{ m = (typeof WS_MARKET !== "undefined" && WS_MARKET) ? String(WS_MARKET) : ""; }catch(e){}
  if(!m || m === "__all__") return u;
  return u + (u.indexOf("?") >= 0 ? "&" : "?") + "marketplace=" + encodeURIComponent(m);
}
function acctScopedPath(url){
  const u = String(url || "");
  if(u.charAt(0) !== "/" || /[?&]account=/.test(u)) return false;
  const path = u.split("?")[0];
  return ACCT_SCOPED_PATHS.some(function(p){
    return p.charAt(p.length - 1) === "/" ? path.indexOf(p) === 0 : path === p;
  });
}
(function(){
  if(typeof window === "undefined" || !window.fetch || window.fetch._acctScoped) return;
  const _orig = window.fetch.bind(window);
  const _scoped = function(input, init){
    try{ if(typeof input === "string" && acctScopedPath(input)) input = acctMktUrl(acctUrl(input)); }
    catch(e){ /* never let the stamp stop the request */ }
    return _orig(input, init);
  };
  _scoped._acctScoped = true;
  window.fetch = _scoped;
})();
