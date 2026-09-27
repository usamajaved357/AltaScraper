// ===================== MARKETPLACES, WITH THEIR FLAGS =====================
//
// One definition of "what does UK mean" for the whole app: the flag, the name a
// person would say, and the currency symbol. It was written out in three
// different places -- the home cards said "UK · DE · IE", the switcher said
// "UK", and the currency symbol was worked out with an inline ternary in two
// files that had already drifted apart on the euro countries.
//
// Flags are EMOJI, not images: no file to fetch, no CDN to depend on, and they
// scale with the text. The app already refuses to load anything from a host it
// does not control.

const MARKETPLACES = {
  UK: {flag: "🇬🇧", name: "United Kingdom", short: "UK", currency: "GBP", symbol: "£"},
  US: {flag: "🇺🇸", name: "United States",  short: "USA", currency: "USD", symbol: "$"},
  CA: {flag: "🇨🇦", name: "Canada",         short: "CA", currency: "CAD", symbol: "$"},
  MX: {flag: "🇲🇽", name: "Mexico",         short: "MX", currency: "MXN", symbol: "$"},
  BR: {flag: "🇧🇷", name: "Brazil",         short: "BR", currency: "BRL", symbol: "R$"},
  DE: {flag: "🇩🇪", name: "Germany",        short: "DE", currency: "EUR", symbol: "€"},
  FR: {flag: "🇫🇷", name: "France",         short: "FR", currency: "EUR", symbol: "€"},
  IT: {flag: "🇮🇹", name: "Italy",          short: "IT", currency: "EUR", symbol: "€"},
  ES: {flag: "🇪🇸", name: "Spain",          short: "ES", currency: "EUR", symbol: "€"},
  NL: {flag: "🇳🇱", name: "Netherlands",    short: "NL", currency: "EUR", symbol: "€"},
  BE: {flag: "🇧🇪", name: "Belgium",        short: "BE", currency: "EUR", symbol: "€"},
  IE: {flag: "🇮🇪", name: "Ireland",        short: "IE", currency: "EUR", symbol: "€"},
  SE: {flag: "🇸🇪", name: "Sweden",         short: "SE", currency: "SEK", symbol: "kr"},
  PL: {flag: "🇵🇱", name: "Poland",         short: "PL", currency: "PLN", symbol: "zł"},
  TR: {flag: "🇹🇷", name: "Türkiye",        short: "TR", currency: "TRY", symbol: "₺"},
  AE: {flag: "🇦🇪", name: "United Arab Emirates", short: "AE", currency: "AED", symbol: "AED"},
  SA: {flag: "🇸🇦", name: "Saudi Arabia",   short: "SA", currency: "SAR", symbol: "SAR"},
  EG: {flag: "🇪🇬", name: "Egypt",          short: "EG", currency: "EGP", symbol: "EGP"},
  IN: {flag: "🇮🇳", name: "India",          short: "IN", currency: "INR", symbol: "₹"},
  JP: {flag: "🇯🇵", name: "Japan",          short: "JP", currency: "JPY", symbol: "¥"},
  SG: {flag: "🇸🇬", name: "Singapore",      short: "SG", currency: "SGD", symbol: "$"},
  AU: {flag: "🇦🇺", name: "Australia",      short: "AU", currency: "AUD", symbol: "$"},
  // Not a country: the app's own name for "every marketplace at once".
  __all__: {flag: "🌐", name: "All marketplaces", short: "All", symbol: ""},
};

// An unknown code is shown as itself with a neutral globe rather than dropped.
// Amazon adds marketplaces, and a code this file has not met yet is a reason to
// show something plain, not to show nothing.
function mktInfo(code){
  const k = String(code || "").trim().toUpperCase();
  return MARKETPLACES[k] || MARKETPLACES[code] ||
         {flag: "🏳", name: k || "Unknown", short: k || "?", symbol: ""};
}

function mktFlag(code){ return mktInfo(code).flag; }
function mktName(code){ return mktInfo(code).name; }
function mktShort(code){ return mktInfo(code).short; }
// THE SYMBOL COMES FROM money.js's ONE MAP when it is loaded. This table had
// its own column and it disagreed: Canada, Mexico, Singapore and Australia were
// all a bare "$" here and "C$"/"MX$"/"S$"/"A$" in money.js -- two dollar markets
// on one screen shown the same (master audit A8, Milestone 5). The `symbol`
// column stays only as the fallback for this file loaded on its own.
function mktSymbol(code){
  const m = mktInfo(code);
  if(m.currency && typeof CUR_SYMBOLS !== "undefined" && CUR_SYMBOLS[m.currency])
    return String(CUR_SYMBOLS[m.currency]).trim();
  return m.symbol;
}
// The ISO currency code of a marketplace ("CA" -> "CAD"), or "".
function mktCurrency(code){ return mktInfo(code).currency || ""; }

// "🇬🇧 UK" — the pair used on buttons and chips, where the flag alone is too
// small to identify at a glance and the code alone is what we had before.
function mktChip(code){
  const m = mktInfo(code);
  return m.flag + " " + m.short;
}
