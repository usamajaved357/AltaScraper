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
  UK: {flag: "🇬🇧", name: "United Kingdom", short: "UK", symbol: "£", ccy: "GBP"},
  US: {flag: "🇺🇸", name: "United States",  short: "USA", symbol: "$", ccy: "USD"},
  CA: {flag: "🇨🇦", name: "Canada",         short: "CA", symbol: "$", ccy: "CAD"},
  MX: {flag: "🇲🇽", name: "Mexico",         short: "MX", symbol: "$", ccy: "MXN"},
  BR: {flag: "🇧🇷", name: "Brazil",         short: "BR", symbol: "R$", ccy: "BRL"},
  DE: {flag: "🇩🇪", name: "Germany",        short: "DE", symbol: "€", ccy: "EUR"},
  FR: {flag: "🇫🇷", name: "France",         short: "FR", symbol: "€", ccy: "EUR"},
  IT: {flag: "🇮🇹", name: "Italy",          short: "IT", symbol: "€", ccy: "EUR"},
  ES: {flag: "🇪🇸", name: "Spain",          short: "ES", symbol: "€", ccy: "EUR"},
  NL: {flag: "🇳🇱", name: "Netherlands",    short: "NL", symbol: "€", ccy: "EUR"},
  BE: {flag: "🇧🇪", name: "Belgium",        short: "BE", symbol: "€", ccy: "EUR"},
  IE: {flag: "🇮🇪", name: "Ireland",        short: "IE", symbol: "€", ccy: "EUR"},
  SE: {flag: "🇸🇪", name: "Sweden",         short: "SE", symbol: "kr", ccy: "SEK"},
  PL: {flag: "🇵🇱", name: "Poland",         short: "PL", symbol: "zł", ccy: "PLN"},
  TR: {flag: "🇹🇷", name: "Türkiye",        short: "TR", symbol: "₺", ccy: "TRY"},
  AE: {flag: "🇦🇪", name: "United Arab Emirates", short: "AE", symbol: "AED", ccy: "AED"},
  SA: {flag: "🇸🇦", name: "Saudi Arabia",   short: "SA", symbol: "SAR", ccy: "SAR"},
  EG: {flag: "🇪🇬", name: "Egypt",          short: "EG", symbol: "EGP", ccy: "EGP"},
  IN: {flag: "🇮🇳", name: "India",          short: "IN", symbol: "₹", ccy: "INR"},
  JP: {flag: "🇯🇵", name: "Japan",          short: "JP", symbol: "¥", ccy: "JPY"},
  SG: {flag: "🇸🇬", name: "Singapore",      short: "SG", symbol: "$", ccy: "SGD"},
  AU: {flag: "🇦🇺", name: "Australia",      short: "AU", symbol: "$", ccy: "AUD"},
  // Not a country: the app's own name for "every marketplace at once".
  __all__: {flag: "🌐", name: "All marketplaces", short: "All", symbol: "", ccy: ""},
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
function mktSymbol(code){ return mktInfo(code).symbol; }
// The ISO currency code ("GBP"), for the top bar's account context (design
// system: account + marketplace + currency always visible). "" when unknown.
function mktCcy(code){ return mktInfo(code).ccy || ""; }

// "🇬🇧 UK" — the pair used on buttons and chips, where the flag alone is too
// small to identify at a glance and the code alone is what we had before.
function mktChip(code){
  const m = mktInfo(code);
  return m.flag + " " + m.short;
}
