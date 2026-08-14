// ===================== WHAT EACH SCREEN ALREADY HAS =====================
//
// "when i click on a tab in some other app it takes some time to load at the
// first time like 1 second but when something loads and i come back to that
// same page again, it never loads again, the data is already loaded."
//
// The app was reloading every screen on every visit. Not because anything was
// lost -- the rendered content is still sitting in its panel, hidden rather
// than destroyed -- but because navTo() called each screen's loader every time,
// which threw the rendered content away and started a spinner. Coming back to
// Sales meant waiting for Sales again, having already waited for it once.
//
// So this file answers ONE question: does this screen need loading, or is what
// is already on it good enough? Nothing else changes -- no screen's loader is
// rewritten, no data is copied anywhere, and every Refresh button still does
// exactly what it did.
//
// THE PART THAT MATTERS MORE THAN THE SPEED
// A remembered screen is remembered FOR ONE ACCOUNT AND ONE MARKETPLACE. This
// app has already shipped three separate bugs where one account's data appeared
// under another's name, and a naive cache is the fourth. So the record is keyed
// by account and marketplace, switching either forgets everything, and the
// panels are emptied on the way out -- an empty panel for a moment is correct,
// another account's numbers are not.

const SCREEN_SEEN = {};        // "section::account::marketplace" -> when it loaded

// After this long, a revisit reloads. Not a correctness rule -- the Refresh
// buttons and the account switch are what guarantee freshness -- just a limit
// on how old a figure can silently be. Ten minutes is well inside how often
// Amazon's own numbers move.
const SCREEN_MAX_AGE_MS = 10 * 60 * 1000;

// The container each screen fills. Emptied when the account changes so no panel
// can show the previous account's contents, even for a frame. The toolbars live
// in the page itself and are deliberately NOT touched.
const SCREEN_BODIES = {
  sales:        ["sales_cards", "sales_charts", "sales_breakdown", "sales_range", "sales_today"],
  finance:      ["finbody"],
  orders:       ["ordbody"],
  returns:      ["retbody"],
  aiusage:      ["aiu_body"],
  variations:   ["varbody"],
  sourcing:     ["srcbody", "srcpick"],
  sellerimport: ["simpbody"],
  monitor:      ["mon_list", "mon_alerts"],
  inventory:    ["inv2_result"],
  ppc:          [],   // a chat log: clearing it would throw away the conversation
};

function _screenKey(sec){
  const acct = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT)
               ? String(CUR_ACCOUNT.id || "") : "";
  const mkt = (typeof WS_MARKET !== "undefined") ? String(WS_MARKET || "") : "";
  return sec + "::" + acct + "::" + mkt;
}

// Should this screen load now? True the first time, and again once what is on
// it is old. False means: what is already rendered is this account's, and
// recent, so show it instantly.
function screenNeedsLoad(sec){
  const at = SCREEN_SEEN[_screenKey(sec)];
  if(!at) return true;
  return (Date.now() - at) > SCREEN_MAX_AGE_MS;
}

// Called once a screen has actually rendered something.
function screenLoaded(sec){
  SCREEN_SEEN[_screenKey(sec)] = Date.now();
}

// Force one screen to load next time it is opened -- for anything that changes
// the data underneath it (a sync, a submit, a price change).
function screenStale(sec){
  delete SCREEN_SEEN[_screenKey(sec)];
}

// THE ACCOUNT CHANGED. Forget everything and empty every panel.
//
// Both halves are necessary. Forgetting alone would leave the previous
// account's content on screen until the new load finished -- which is exactly
// the bug that made Jack Reacherd show Green Haven's listings. Emptying alone
// would leave the screen blank but marked as loaded.
function screenForgetAll(){
  for(const k in SCREEN_SEEN){ delete SCREEN_SEEN[k]; }
  for(const sec in SCREEN_BODIES){
    (SCREEN_BODIES[sec] || []).forEach(function(id){
      const el = document.getElementById(id);
      if(el) el.innerHTML = "";
    });
  }
}
