// static/js/money.js — one currency-code to symbol map.
//
// There were FOUR, in salescharts.js, stock.js, weekly.js and a fifth idea of
// it in listings.js, and they had already disagreed: two rendered Canadian
// dollars as "$" and one as "C$", which on a screen showing both markets is the
// difference between a readable figure and a wrong one.
//
// Found while adding a fifth. Three new screens (Trackers, Leading Indicators,
// Product Catalog) had been written against a variable called CURRENCY_SYMBOL
// that HAS NEVER EXISTED anywhere in this app, so all three were quietly
// printing money with no symbol at all — 540.91 where it should say £540.91.
// CLAUDE.md Rule 12: extract the one that exists, then use it everywhere.
//
// AN UNKNOWN CODE RETURNS THE CODE, not a guessed symbol. "SGD 40.00" is
// correct and readable; picking "$" for it would be a different currency
// presented as though it were the same one.

const CUR_SYMBOLS = {
  GBP: "£", USD: "$", EUR: "€", JPY: "¥",
  // Distinguished on purpose. A screen that can show two dollar markets must
  // not render them both as "$" — that is the disagreement the four copies
  // already had.
  CAD: "C$", AUD: "A$", SGD: "S$", NZD: "NZ$",
  SEK: "kr", PLN: "zł", AED: "AED ", INR: "₹",
  MXN: "MX$", BRL: "R$", TRY: "₺", SAR: "SAR ", EGP: "EGP ",
  CHF: "CHF ", NOK: "kr", DKK: "kr", CZK: "Kč", HUF: "Ft",
};

// The symbol for a currency CODE. `fallback` is used only when no code was
// given at all — an unrecognised code returns itself, because showing the code
// is honest where guessing a symbol is not.
function curSymbol(code, fallback) {
  const c = String(code || "").trim().toUpperCase();
  if (!c) {
    if (fallback) return fallback;
    // The workspace's own symbol, which listings.js keeps in step with the
    // marketplace. Last resort, and still better than a bare number.
    return (typeof CUR_SYMBOL !== "undefined" && CUR_SYMBOL) ? CUR_SYMBOL : "";
  }
  return CUR_SYMBOLS[c] || (c + " ");
}

// Money as a person reads it: symbol, thousands separators, two decimals.
// Returns the dash for "not known" rather than 0.00, because a missing figure
// and a figure of zero are different answers and only one of them is a fact.
function curMoney(v, code, fallback) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (isNaN(n)) return "—";
  return curSymbol(code, fallback) +
    n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
