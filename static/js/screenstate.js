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
  sales:        ["sales_cards", "sales_charts", "sales_breakdown", "sales_range", "sales_today",
                 "pnl_body",
                 // Found by the seeded-marker browser check (28 Sep 2026): the
                 // product picker kept A's ASINs under B. The data panels and
                 // labels Sales draws into -- never its controls.
                 "sales_grid", "sales_campaigns", "sales_camp_note",
                 "sales_note", "sales_orgppc", "sales_ppccards", "sales_week",
                 "sales_hourly", "sales_today_clock", "sales_today_delta",
                 "sales_today_key", "sales_today_note", "sales_week_delta",
                 "sales_week_key", "sales_week_note"],
  // Image library / Image studio: drawn product lists and the chosen product.
  imagelib:     ["imgp_picker", "imgp_which", "imgp_lib"],
  imagestudio:  ["studiobody", "studio_picker_list"],
  finance:      ["finbody"],
  orders:       ["ordbody"],
  returns:      ["retbody", "returns_list", "returns_detail"],
  aiusage:      ["aiu_body"],
  variations:   ["varbody"],
  sourcing:     ["srcbody", "srcpick", "srcalerts"],
  sellerimport: ["simpbody"],
  monitor:      ["mon_list", "mon_alerts"],
  inventory:    ["inv2_result", "stockwrap"],
  ppc:          [],   // a chat log: clearing it would throw away the conversation
  // Milestone 3: these screens dim their last render while loading rather than
  // clearing it, so without being listed here the previous account's figures
  // stayed on screen, faded, until the new ones arrived (master audit S4).
  hourly:       ["hrlybody"],
  traffic:      ["trafbody"],
  daily:        ["dy_body"],
  weekly:       ["wk_body"],
  leading:      ["ld_body"],
  catalog:      ["catp_body"],
  trackers:     ["trk_body"],
  alerts:       ["alr_body"],
  drppc:        ["drp_body"],
  ppcanalytics: ["ppca_body"],
  ppcterms:     ["ppct_body"],
  ppccampaigns: ["ppcc_body"],
  ppclive:      ["ppcl_body"],
  reimbursements: ["rb_body"],
  sqp:          ["sqp_body"],
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
// ---- WHICH ACCOUNT A REPLY WAS ASKED FOR (Milestone 3, 28 Sep 2026) ----
//
// A loader awaits Amazon, sometimes for many seconds. Switch account or
// marketplace in that time and the reply still arrives -- and every screen but
// Orders and Sales painted it, so account B's screen ended up showing account
// A's rows (master audit S5, proved on Finance). The same one check for all:
//
//     const sc = screenScope();                  // before the fetch
//     const j = await (await fetch(...)).json();
//     if(!screenStillIn(sc)) return;             // after EVERY await
//
// The generation moves on every screenForgetAll(), i.e. every account or
// marketplace change, so even A -> B -> A abandons the first A request.
let SCREEN_GEN = 0;
function screenScope(){
  return {
    acct: (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT)
          ? String(CUR_ACCOUNT.id || "") : "",
    mkt: (typeof WS_MARKET !== "undefined") ? String(WS_MARKET || "") : "",
    gen: SCREEN_GEN,
  };
}
function screenStillIn(sc){
  if(!sc) return false;
  const now = screenScope();
  return now.acct === sc.acct && now.mkt === sc.mkt && now.gen === sc.gen;
}

// THE DATA EACH SCREEN IS HOLDING, dropped on a switch. Emptying a panel was
// not enough: most screens keep their last reply in an object and their open
// function skips the load when it is there ("if(!RET.data)"), so reopening one
// in the new account redrew the old account's figures (master audit S4). And a
// "busy/loading" flag left set by the old account's request made the new
// account's request return early and never run. Each screen's object is reset
// here, guarded, because every one lives in its own file.
function _screenResetHeld(){
  const T = (o, f) => { try{ if(o) f(o); }catch(e){} };
  if(typeof RET   !== "undefined") T(RET,   o => { o.data = null; o.busy = false; });
  if(typeof RETL  !== "undefined") T(RETL,  o => { o.rows = []; o.statuses = {};
    o.coverage = {}; o.note = ""; o.open = null; o.detail = null; o.loading = false; });
  if(typeof HRLY  !== "undefined") T(HRLY,  o => { o.data = null; o.busy = false; });
  if(typeof TRAF  !== "undefined") T(TRAF,  o => { o.data = null; o.busy = false; });
  if(typeof STOCK !== "undefined") T(STOCK, o => { o.rows = []; o.cockpit = null;
    o.counts = {}; o.legend = []; o.coverage = null; o.coverageAsked = false;
    o.moneyBack = null; o.moneyBackAsked = false; o.loading = false; });
  if(typeof PPCV  !== "undefined") T(PPCV,  o => { o.data = null; o.loading = false; });
  if(typeof PPCA  !== "undefined") T(PPCA,  o => { o.data = null; o.loading = false; });
  if(typeof PPCT  !== "undefined") T(PPCT,  o => { o.data = null; o.loading = false; });
  if(typeof PPCC  !== "undefined") T(PPCC,  o => { o.data = null; o.loading = false; });
  if(typeof PPCL  !== "undefined") T(PPCL,  o => { o.data = null; o.asinData = {};
    o.openAsin = ""; o.loading = false; });
  if(typeof DRP   !== "undefined") T(DRP,   o => { o.status = null; o.data = null;
    o.loading = false; });
  // Dr PPC console: a plan DRAFTED in account A must never be saved into B
  // (master audit S3). Everything it holds goes, and its shell -- which names
  // the account -- is rebuilt on the next open.
  if(typeof DRPC  !== "undefined") T(DRPC,  o => { o.setup = null; o.state = null;
    o.plan = null; o.perf = null; o.act = null; o.draft = null; o.history = [];
    o.detail = {}; o.openCamp = null; o.loading = false;
    const m = document.getElementById("drpc_main"); if(m && m.remove) m.remove(); });
  if(typeof DAILY !== "undefined") T(DAILY, o => { o.data = null; o.loading = false; });
  // The shared PRODUCT PICKER (Image library, Image studio) fetched once and
  // kept the list forever -- so B's Image library listed A's products. Found by
  // the seeded-marker check in tools/browser_smoke.py (28 Sep 2026).
  if(typeof PPICK !== "undefined") T(PPICK, o => { o.items = []; o.loaded = false;
    o.loading = false; o.error = ""; });
  if(typeof IMGP  !== "undefined") T(IMGP,  o => { o.items = []; o.sku = ""; o.q = "";
    o.loading = false; o.note = ""; });
  // THE IMAGE STUDIO'S product, brand and results belong to the account they
  // were picked in; kept, B's Studio redrew A's product and its Save filed A's
  // images into B's library. Its progress poll is stopped with them (review).
  if(typeof STUDIO !== "undefined") T(STUDIO, o => { o.skus = []; o.items = [];
    o.brand = ""; o.results = {}; o.manualRef = ""; });
  try{ if(typeof STUDIO_POLL !== "undefined" && STUDIO_POLL){ clearInterval(STUDIO_POLL); STUDIO_POLL = null; } }catch(e){}
  // UNSAVED TYPED EDITS in the listing rows belong to the account they were
  // typed in. Kept, lrEditRestore put A's price/stock into B's same-SKU boxes,
  // and one Save wrote them to B -- stock to Amazon included (review).
  if(typeof LR_EDITS !== "undefined") T(LR_EDITS, o => { Object.keys(o).forEach(k => { delete o[k]; }); });
  // ...and the "N SKUs edited" bar that counted them (it lives on <body>).
  try{ if(typeof lrEditBar === "function") lrEditBar(); }catch(e){}
  if(typeof WK    !== "undefined") T(WK,    o => { o.week = null; o.weeks = [];
    o.change = {}; o.loading = false; o.fellBack = ""; });
  if(typeof PNL   !== "undefined") T(PNL,   o => { o.data = null; o.expenses = null;
    o.loading = false; });
  if(typeof RB    !== "undefined") T(RB,    o => { o.data = null; o.loading = false;
    o.asked = false; o.error = ""; });
  if(typeof FIN   !== "undefined") T(FIN,   o => { o.rows = []; o.totals = {};
    o.overhead = null; o.previous = null; o.meta = null; });
  if(typeof LEAD  !== "undefined") T(LEAD,  o => { o.data = null; o.loading = false; });
  if(typeof CATP  !== "undefined") T(CATP,  o => { o.data = null; o.loading = false; });
  if(typeof TRK   !== "undefined") T(TRK,   o => { o.rows = []; o.loading = false; });
  // REPRICER RULES AND FAMILIES, keyed by SKU (Milestone 3 review). A's floor,
  // hold price and direction were shown on B's same-SKU row -- and PRE-FILLED
  // B's dialogs, so saving one wrote A's floor into B. The "asked" flags go
  // too, or B's own would never be fetched.
  if(typeof SRC_ROW_RULES !== "undefined") T(SRC_ROW_RULES, o => { for(const k in o) delete o[k]; });
  if(typeof SRC_RULE    !== "undefined") { try{ SRC_RULE = null; }catch(e){} }
  if(typeof SRC_MASTER  !== "undefined") { try{ SRC_MASTER = false; }catch(e){} }
  if(typeof LR_RULES_ASKED  !== "undefined") { try{ LR_RULES_ASKED = false; }catch(e){} }
  if(typeof LR_RULES_LOADED !== "undefined") { try{ LR_RULES_LOADED = false; }catch(e){} }
  if(typeof LR_FAMILIES !== "undefined") { try{ LR_FAMILIES = null; }catch(e){} }
  if(typeof LR_FAM_ASKED !== "undefined") { try{ LR_FAM_ASKED = false; }catch(e){} }
  if(typeof LR_OPEN_FAMS !== "undefined") T(LR_OPEN_FAMS, o => { for(const k in o) delete o[k]; });
  // Keywords (Search Query Performance): one account's report (Milestone 3 review).
  if(typeof SQP   !== "undefined") T(SQP,   o => { o.data = null; o.note = ""; o.loading = false; });
  // The generator's input queue is the open account's (the server reads it
  // from the selected workspace) -- counting A's queue for B is the wrong answer.
  if(typeof IQ    !== "undefined") T(IQ,    o => { o.rows = []; o.busy = false; o.editing = null; });
  // SKU-KEYED CACHES (master audit S7). SKUs repeat across accounts, so each
  // of these answered account B's row with account A's figures -- and several
  // are checked BEFORE the row's own value (COGS_LOCAL) or stop the re-read
  // altogether (LIVE_MIRROR, LR_ASKED).
  if(typeof LIVE_MIRROR !== "undefined") T(LIVE_MIRROR, o => { for(const k in o) delete o[k]; });
  if(typeof COGS_LOCAL  !== "undefined") T(COGS_LOCAL,  o => { for(const k in o) delete o[k]; });
  if(typeof LISTING_METRICS !== "undefined") T(LISTING_METRICS, o => { for(const k in o) delete o[k]; });
  if(typeof LR_ASKED    !== "undefined") T(LR_ASKED,    o => o.clear());
  if(typeof LR_ERRORS   !== "undefined") T(LR_ERRORS,   o => { for(const k in o) delete o[k]; });
  if(typeof LR_COVERAGE !== "undefined") T(LR_COVERAGE, o => { for(const k in o) delete o[k]; });
  // A draft's suppliers and profit (draftsources.js), and Amazon's image slots
  // (amazonimages.js): keyed by SKU alone and never re-asked once held, so B's
  // same-SKU draft showed A's suppliers, and UK's showed after a switch to US
  // (front-end review, 29 Sep 2026).
  if(typeof DRAFT_SRC   !== "undefined") T(DRAFT_SRC,   o => { for(const k in o) delete o[k]; });
  if(typeof AIMG        !== "undefined") T(AIMG,        o => { o.sku = ""; o.state = "";
    o.data = null; o.err = ""; o.justSent = ""; });
  // `let` scalars in another file: assignable from here (one global scope).
  if(typeof LR_LOADING  !== "undefined") { try{ LR_LOADING = false; }catch(e){} }
  if(typeof LR_ANSWERED !== "undefined") { try{ LR_ANSWERED = false; }catch(e){} }
  if(typeof LR_LAST_FETCH !== "undefined") { try{ LR_LAST_FETCH = 0; }catch(e){} }
  // Schemas are Amazon's per product type AND marketplace; they were keyed by
  // product type alone, so a UK schema was drawn for a US listing.
  if(typeof SCHEMAS     !== "undefined") T(SCHEMAS,     o => { for(const k in o) delete o[k]; });
  // PPC per ASIN: null means "not loaded" there, and the key it was loaded for
  // goes too, or A -> B -> A would find the key matching and never refetch.
  if(typeof PPC_BY_ASIN !== "undefined") { try{ PPC_BY_ASIN = null; }catch(e){} }
  if(typeof PPC_KEY     !== "undefined") { try{ PPC_KEY = ""; }catch(e){} }
  if(typeof PPC_LOADING !== "undefined") { try{ PPC_LOADING = false; }catch(e){} }
}

function screenForgetAll(){
  SCREEN_GEN++;                  // every reply already on its way is now stale
  _screenResetHeld();
  for(const k in SCREEN_SEEN){ delete SCREEN_SEEN[k]; }
  for(const sec in SCREEN_BODIES){
    (SCREEN_BODIES[sec] || []).forEach(function(id){
      const el = document.getElementById(id);
      if(el) el.innerHTML = "";
    });
  }
  // AND THE ANSWERS A SCREEN IS HOLDING, not only what it has drawn.
  //
  // The Sales screen keeps replies it has already been given -- so that two
  // parts of it wanting the same figure ask Amazon once, and so a period click
  // does not re-fetch today's orders. Those are keyed by account and so cannot
  // be handed to the wrong one; this drops them anyway on the way out, because
  // "held data from the account you just left" is the one thing this function
  // exists to make impossible, and a cache is the easiest place to forget it.
  if(typeof _sForget === "function") _sForget();
  // AND ANY WORK STILL RUNNING FOR THE ACCOUNT YOU HAVE LEFT. The product-type
  // warm-up can be forty-two calls to Amazon; carried on after a switch it
  // competes with the account you have just opened for the browser's six
  // connections, which is the whole reason it is paced in the first place.
  if(typeof schemasAbandon === "function") schemasAbandon();
  // AND THE ORDERS. This one holds real customers' names, towns and postcodes,
  // and it keeps them in ORD.rows rather than only in the panel -- which
  // ordersOnOpen then reuses instead of loading ("if(!ORD.rows.length)"). So
  // emptying the panel was not enough: opening Orders in the account you just
  // switched to redrew the account you just left, PII and all.
  //
  // Also resets whose orders are asked for, back to "the workspace you have
  // open". Choosing "Every account" is a decision about one screen, not one
  // that should follow you into a different company's workspace.
  if(typeof ORD !== "undefined" && ORD){
    ORD.rows = []; ORD.summary = {}; ORD.meta = null;
    ORD.details = {}; ORD.open = ""; ORD.account = "";
    ORD.sel = new Set();                     // ticked orders were that account's
    ORD.loadId = (ORD.loadId || 0) + 1;      // abandon any load in flight
    const _oa = document.getElementById("ord_account");
    if(_oa) _oa.value = "";
  }
}
