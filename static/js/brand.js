// ======================= WHICH BRAND IS THIS? =======================
//
// ONE ANSWER, ASKED IN NINE PLACES.
//
//     "no asin in the screenshot opens a product some shows the brand name and
//      some do not show the brand name, i want the brand name to be displayed
//      in all"
//
// A card showed a brand when the row happened to carry one and showed nothing
// when it did not -- so an empty space meant "this listing has no brand", which
// is never true. Every listing this app makes goes out under one of the
// account's own registered brands (that is the whole business: new products
// under our own names, never a me-too offer on somebody else's ASIN). If the
// row does not name one, the account's default is the one Amazon will actually
// receive, so that is what the card should say -- marked as the default rather
// than presented as a fact about the row.
//
// WHY A FILE OF ITS OWN. This expression:
//
//     CUR_ACCOUNT.brands && CUR_ACCOUNT.brands.length
//       ? CUR_ACCOUNT.brands[0] : (CUR_ACCOUNT.label || "")
//
// was written out by hand in asinresearch.js, genimage.js (twice),
// miles_template.js, pastelisting.js and studiopicker.js. Six copies of one
// rule, which is six places to fix when the rule changes and six chances for
// them to disagree about what a listing is branded -- on the one field that
// decides whether Amazon accepts the listing at all. Rule 12: extract first,
// then change the one copy.
//
// THIS MIRRORS resolve_account_brand() IN amazon_listing_generator.py. The
// server is still the authority -- it is the thing that talks to Amazon, and it
// re-decides this on submit and can override the row. This is the screen's copy
// of the same rule so the card shows what the server will send, instead of
// showing a blank and letting the user find out at submit time.

/* The account's own default brand: its first registered trademark, or failing
   that its label. "" when no account is open. */
function accountBrand(){
  try{
    if(typeof CUR_ACCOUNT === "undefined" || !CUR_ACCOUNT) return "";
    if(CUR_ACCOUNT.brands && CUR_ACCOUNT.brands.length) return CUR_ACCOUNT.brands[0];
    return CUR_ACCOUNT.label || "";
  }catch(e){ return ""; }
}

/* Every brand this account may use. The card uses it to tell "the row names one
   of ours" apart from "the row names something we are not registered for",
   which is the case worth flagging -- Amazon rejects it, and the server
   substitutes the account brand and says so. */
function accountBrands(){
  try{
    if(typeof CUR_ACCOUNT === "undefined" || !CUR_ACCOUNT) return [];
    return (CUR_ACCOUNT.brands || []).filter(Boolean);
  }catch(e){ return []; }
}

/* What this row is branded, and how confident that is.
 *
 *   {name, from: "row" | "account" | "", ours: bool}
 *
 * from:"row"     the row says so
 * from:"account" the row is blank, so this is the account default that will be
 *                sent -- the caller should show it as a default, not as fact
 * ours:false     the row names a brand this account is not registered for. Not
 *                hidden and not silently corrected here: the card marks it and
 *                the server decides on submit. */
function rowBrand(r){
  const row = String((r && (r.brand || r.brand_name)) || "").trim();
  const mine = accountBrands();
  if(row){
    // Case-insensitive: "altaboltavoo" and "AltaboltaVoo" are the same
    // trademark, and treating them as different is how an approved brand gets
    // flagged as unknown.
    const lc = row.toLowerCase();
    const hit = mine.some(function(b){ return String(b).toLowerCase() === lc; });
    return {name: row, from: "row", ours: hit || !mine.length};
  }
  const def = accountBrand();
  return {name: def, from: def ? "account" : "", ours: true};
}
