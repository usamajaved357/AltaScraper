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
  const id = acctId();
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
  return u + (u.indexOf("?") >= 0 ? "&" : "?") + "account=" + encodeURIComponent(id);
}
