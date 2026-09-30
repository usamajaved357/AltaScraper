// static/js/home.js -- HOME, the screen the app opens on (owner, 29 Sep 2026:
// "yes app should ope on the new home screen").
//
// Prototype A's queue board (prototypes/design-review/A-cockpit.html): a card
// per queue of work, each a count you can clear, and pressing one lands on the
// screen already filtered to exactly those rows. Then today's sales so far,
// then what the daily round found.
//
// NOTHING HERE IS COUNTED TWICE (CLAUDE.md Rule 12). Each number is asked of
// the code that already owns it, so a card and the screen it opens agree:
//   listings  listQueueCount(f) / liveItemIs  -- the Drafts table's own rows and test
//   orders    _ordTabCounts / _ordBuyKnown     -- the Orders tabs' own counts
//   today     /sales/today through _sFetch      -- the Sales card's shared cache
//   round     DAILY (daily.js), loaded by dailyLoad, drawn by _dyRow
// and every card is shown only to someone who may open the screen it leads to.
//
// UNKNOWN IS NEVER ZERO. A count whose data failed to load, or has not arrived,
// shows a dash or a spinner and says why -- never 0.
//
// Read-only. Nothing on this screen changes anything; every card only opens.

const HOME = {sales: null, salesErr: "", gen: 0, timer: 0, since: 0, dailyAsked: "", fresh: false};

function _hMay(sec){
  return (typeof maySeeSection !== "function") || maySeeSection(sec);
}

/* WHOSE HOME THIS IS -- an account workspace whose key IS the account every
 * request names (CUR_ACCOUNT), or nobody's. The "New brand" form and the old
 * per-view workspaces keep the previous account's data around under another
 * name; Home shows nothing for them rather than that account's numbers
 * (account-scope review, 29 Sep 2026). During a switch the two briefly
 * disagree, and Home waits. */
function _hWs(){
  if(typeof ACTIVE_WS === "undefined" || !ACTIVE_WS || !ACTIVE_WS.account || !ACTIVE_WS.key) return "";
  const cur = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT) ? String(CUR_ACCOUNT.id || "") : "";
  return cur === String(ACTIVE_WS.key) ? cur : "";
}

function _hAllMkts(){
  return typeof WS_MARKET !== "undefined" && WS_MARKET === "__all__";
}

/* The open account's live catalogue FOR THIS MARKETPLACE, or null while it has
 * not arrived: LIVE_ITEMS can still hold the previous marketplace's after a
 * switch, and a failed load never replaces it. */
function _hLiveItems(){
  try{
    if(typeof LIVE_STORE === "undefined" || typeof _liveKey !== "function") return null;
    const c = LIVE_STORE[_liveKey()];
    return (c && Array.isArray(c.items)) ? c.items : null;
  }catch(e){ return null; }
}

function _hOnHome(){
  return typeof CUR_SEC !== "undefined" && CUR_SEC === "home";
}

function homeOnOpen(){
  HOME.since = Date.now();
  homeRender();
  // A tick later, and only if Home is still the screen: opening a link to
  // another screen passes through Home first (enterAccount lands there), and
  // that must not cost three Amazon reads for a page nobody saw.
  const gen = HOME.gen;
  setTimeout(function(){ if(gen === HOME.gen && _hOnHome()) homeLoad(); }, 300);
}

function homeRefresh(){
  HOME.gen++;
  HOME.sales = null; HOME.salesErr = ""; HOME.dailyAsked = "";
  HOME.fresh = true;          // past the Sales card's one-minute cache, once
  if(typeof DAILY !== "undefined"){ DAILY.data = null; DAILY.note = ""; }
  if(typeof ORD !== "undefined"){ ORD.rows = []; ORD.loadedFor = ""; }   // ordersOnOpen reloads an empty list
  homeOnOpen();
}

/* One after the other, not all at once: today's sales, the orders list and the
 * daily round (which reads orders itself, server-side) all ask Amazon for
 * orders, and Amazon allows about one such request a minute. Sales first (its
 * cache is shared with the Sales screen), then orders; the round is started by
 * homeWatch once the orders have landed. */
async function homeLoad(){
  const gen = HOME.gen, ws = _hWs();
  if(!ws) return;                       // nobody's Home: nothing to ask for (see _hWs)
  const still = function(){ return gen === HOME.gen && ws === _hWs() && _hOnHome(); };
  // Under "All marketplaces" the live endpoints name no marketplace and the
  // server would pick one; Today asks the person to choose instead (_hToday).
  if(_hMay("sales") && !_hAllMkts() && typeof _sFetch === "function" && typeof _sScope === "function"){
    try{
      // An options object is what makes _sFetch ask again rather than reuse.
      const j = await _sFetch("/sales/today?" + _sScope(), HOME.fresh ? {} : undefined);
      HOME.fresh = false;
      if(!still() || j === null) return;
      if(j && j.ok){ HOME.sales = j; HOME.salesErr = ""; }
      else { HOME.sales = null; HOME.salesErr = (j && j.error) || "Amazon did not answer."; }
    }catch(e){ if(!still()) return; HOME.salesErr = String(e); }
    homeRender();
  }
  if(!still()) return;
  // The orders of THIS account: loaded unless already held; reloaded even while
  // another account's load is in flight (its ticket makes that safe).
  if(_hMay("orders") && typeof ORD !== "undefined" && typeof ordersOnOpen === "function"){
    const mine = ORD.rowsFor === ws;
    if(!mine || (!ORD.busy && !(ORD.loadedFor === ws))) ordersOnOpen();
  }
  homeWatch();
}

function _hOrdersSettled(){
  return typeof ORD === "undefined" || !_hMay("orders") || !ORD.busy;
}

/* While Home is on screen, keep it true to what arrives -- the listings, the
 * orders and their second pass (To buy), the live catalogue (which decides
 * published rows and the no-cost card), the round. Until every source has
 * answered or failed, and for two minutes in any case (the catalogue and the
 * second orders pass arrive late); never beyond ten. Redrawing costs nothing
 * when nothing changed (homeRender). */
function _hSettled(){
  const rows = _hRowsLoaded() || !!_hRowsErr();
  const orders = _hOrdersSettled();
  const round = !_hMay("daily") || _hAllMkts() || typeof DAILY === "undefined" || !!DAILY.data || !!DAILY.note;
  return rows && orders && round;
}

function homeWatch(){
  clearTimeout(HOME.timer);
  HOME.timer = setTimeout(function(){
    if(!_hOnHome()) return;
    const ws = _hWs();
    if(!ws){ homeRender(); if(Date.now() - HOME.since < 600000) homeWatch(); return; }
    if(_hMay("daily") && !_hAllMkts() && typeof DAILY !== "undefined" && typeof dailyLoad === "function"
       && _hOrdersSettled() && HOME.dailyAsked !== ws && !DAILY.data && !DAILY.loading){
      HOME.dailyAsked = ws;
      dailyLoad();
    }
    homeRender();
    const age = Date.now() - HOME.since;
    if(age < 600000 && (age < 120000 || !_hSettled())) homeWatch();
  }, 1500);
}

function _hRowsLoaded(){
  return (typeof ROWS_LOADED === "undefined") || !!ROWS_LOADED;
}

function _hRowsErr(){
  return (typeof window !== "undefined" && window.ROWS_ERR) ? String(window.ROWS_ERR) : "";
}

/* ---- the queues ---------------------------------------------------------- */

function _hQueues(){
  const q = [];
  if(_hMay("listings")){
    const err = _hRowsErr();
    const loaded = _hRowsLoaded() && !err;
    const L = function(f, tone, title, desc){
      q.push({kind: "list", f: f, tone: tone, title: title, desc: desc,
              n: loaded && typeof listQueueCount === "function" ? listQueueCount(f) : null,
              wait: !loaded && !err, err: err});
    };
    L("refused",  "bad", "Amazon refused",     "Listings Amazon sent back. Its reply is on each one.");
    L("blocked",  "hot", "Blocked by a check", "Stopped by our identifier or compliance checks.");
    L("review",   "hot", "Needs review",       "Drafts waiting for you to look at.");
    L("approved", "",    "Ready to submit",    "Approved, not sent to Amazon yet.");
    const live = _hLiveItems();
    if(live && live.length && typeof liveItemIs === "function"){
      q.push({kind: "list", f: "live_nocost", tone: "hot", title: "Selling with no cost",
              desc: "Live listings with no cost set, so their profit is not known.",
              n: live.filter(function(it){ return liveItemIs(it, "live_nocost"); }).length});
    }
  }
  if(_hMay("orders") && typeof ORD !== "undefined" && typeof _ordTabCounts === "function"){
    const ws = _hWs();
    // A search typed on the Orders screen narrows the list it loaded; counted,
    // it would undercount. Said, rather than shown as a smaller number.
    const searched = !!(ORD.q && String(ORD.q).trim());
    const known = ORD.loadedFor === ws && ORD.rowsFor === ws && !searched;
    const err = searched ? "the Orders screen has a search typed (\u201c" + String(ORD.q).trim() + "\u201d); clear it there to count every order"
              : (!known && ORD.rowsFor === ws && !ORD.busy && ORD.err) ? String(ORD.err) : "";
    const rows = known ? (ORD.rows || []) : [];
    const c = _ordTabCounts(rows);
    const buyKnown = typeof _ordBuyKnown === "function" ? _ordBuyKnown(rows) : true;
    const O = function(tab, tone, title, desc, extraKnown){
      q.push({kind: "order", f: tab, tone: tone, title: title, desc: desc,
              n: (known && extraKnown !== false) ? c[tab] : null,
              wait: !known && !err, err: err});
    };
    O("problem",  "bad", "Order problems", "Late, cancel requested, or a delivery that failed.");
    O("tobuy",    "hot", "To buy",         "Orders you post yourself that nobody has marked as bought.", buyKnown);
    O("dispatch", "hot", "To dispatch",    "Orders still to send.");
    O("tracking", "",    "Needs tracking", "Sent in the last few days with no tracking recorded here.");
  }
  return q;
}

function homeGo(kind, f){
  if(kind === "list"){
    // The count was taken with no search and every duplicate, so the table
    // is opened the same way (listQueueCount).
    if(typeof SEARCH_Q !== "undefined") SEARCH_Q = "";
    if(typeof DUP_ONLY !== "undefined") DUP_ONLY = false;
    if(typeof navTo === "function") navTo("listings");
    if(String(f).indexOf("live_") === 0){
      if(typeof setListSource === "function" && typeof LIST_SOURCE !== "undefined" && LIST_SOURCE !== "live")
        setListSource("live");
    }else if(typeof draftsView === "function" && !draftsView() && typeof setListSource === "function"){
      setListSource("drafts");
    }
    // metricFilter, so the status dropdown moves with it; it would turn a
    // filter that is already on OFF, so it is only asked to change one.
    if(typeof FILTER === "undefined" || String(FILTER) !== String(f)){
      if(typeof metricFilter === "function") metricFilter(f);
      else if(typeof setFilterVal === "function") setFilterVal(f);
    }else if(typeof render === "function") render();
  }else if(kind === "order"){
    // The count is over every channel with no order held open (_ordTabCounts).
    if(typeof ORD !== "undefined"){ ORD.channel = ""; ORD.open = ""; }
    if(typeof navTo === "function") navTo("orders");
    if(typeof ordersSetTab === "function") ordersSetTab(f);
  }else if(kind === "sec" && typeof navTo === "function"){
    navTo(f);
  }
  if(typeof altaSyncUrl === "function") altaSyncUrl();
}

function _hCard(x){
  const n = x.n;
  const unknown = (n === null || n === undefined);
  const why = x.err ? "Could not be read: " + x.err : (x.wait ? "Still loading" : "Not known");
  const shown = unknown
    ? '<span class="hm-n muted" title="' + esc(why) + '">'
      + (x.wait ? '<span class="genspin" aria-hidden="true"></span>' : '&mdash;') + '</span>'
    : '<span class="hm-n">' + n + '</span>';
  const tone = (!unknown && n > 0 && x.tone) ? " " + x.tone : "";
  return '<button type="button" class="hm-card' + tone + '" data-hk="' + esc(x.kind + ":" + x.f) + '"'
    + ' onclick="homeGo(' + jsArg(x.kind) + ',' + jsArg(x.f) + ')"'
    + ' aria-label="' + esc(x.title + ": " + (unknown ? why : n)) + '">'
    + shown + '<b class="hm-t">' + esc(x.title) + '</b>'
    + '<span class="hm-d">' + esc(x.desc) + '</span></button>';
}

// A failed source is said once, under the cards -- not once per card.
function _hQueueErrors(q){
  const seen = {};
  q.forEach(function(x){
    if(x.err) seen[x.kind === "list" ? "Listings" : "Orders"] = x.err;
  });
  return Object.keys(seen).map(function(k){
    if(typeof uiError !== "function")
      return '<div class="hm-err">' + esc(k + " could not be read: " + seen[k]) + '</div>';
    return k === "Listings"
      ? uiError("Listings could not be read", seen[k], "homeRefresh", "home")
      : uiError("Orders could not be read", seen[k], "homeRefresh", "home");
  }).join("");
}

/* ---- today ----------------------------------------------------------------- */

function _hMoney(v, cur){
  return (typeof _sNum === "function") ? _sNum(v, "money", cur)
       : (v === null || v === undefined || v === "" ? "—" : String(v));
}

function _hAsAt(iso){
  const t = Date.parse(iso || "");
  if(isNaN(t)) return "";
  try{ return new Date(t).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"}); }catch(e){ return ""; }
}

function _hToday(){
  if(!_hMay("sales")) return "";
  let body;
  if(_hAllMkts()){
    body = '<div class="hm-part"><i class="ti ti-world" aria-hidden="true"></i> Today\u2019s sales are read one marketplace at a time. Choose a marketplace to see them here, or open Sales for every marketplace together.</div>'
      + '<div class="hm-foot"><a href="#" onclick="homeGo(\'sec\',\'sales\');return false">Open Sales</a></div>';
  }else if(HOME.sales){
    const t = HOME.sales.today || {};
    const stats = [
      {l: "Sales so far", v: _hMoney(t.revenue, t.currency)},
      {l: "Orders", v: (t.orders == null ? "—" : String(t.orders))},
      {l: "Units", v: (t.units == null ? "—" : String(t.units))},
    ];
    if(t.pending) stats.push({l: "Awaiting a price", v: String(t.pending)});
    body = '<div class="hm-stats">' + stats.map(function(s){
        return '<div class="hm-stat"><span class="hm-sl">' + esc(s.l) + '</span><span class="hm-sv">' + esc(s.v) + '</span></div>';
      }).join("") + '</div>'
      + '<div class="hm-foot">' + (_hAsAt(HOME.sales.as_at) ? 'As at ' + esc(_hAsAt(HOME.sales.as_at)) + '. ' : '')
      + '<a href="#" onclick="homeGo(\'sec\',\'sales\');return false">Open Sales</a></div>';
  }else if(HOME.salesErr){
    // Never drawn as zero: "Amazon would not tell us" is not "no sales".
    body = (typeof uiError === "function")
      ? uiError("Today’s sales could not be read", HOME.salesErr, "homeRefresh", "home")
      : '<div class="hm-err">' + esc(HOME.salesErr) + '</div>';
  }else{
    body = '<div class="hm-loading"><span class="genspin" aria-hidden="true"></span> Asking Amazon for today’s orders…</div>';
  }
  return '<section class="hm-sec"><h3 class="hm-h">Today</h3>' + body + '</section>';
}

/* ---- the round ------------------------------------------------------------- */

function _hRound(){
  if(!_hMay("daily") || typeof DAILY === "undefined") return "";
  if(_hAllMkts()){
    return '<section class="hm-sec"><h3 class="hm-h">Needs attention today</h3>'
      + '<div class="hm-part"><i class="ti ti-world" aria-hidden="true"></i> The daily round checks one marketplace at a time. Choose a marketplace to run it here.</div></section>';
  }
  const open = '<a href="#" onclick="homeGo(\'sec\',\'daily\');return false">Open the daily round</a>';
  let body;
  if(DAILY.data){
    const all = DAILY.data.checks || [];
    const off = all.filter(function(c){ return c.status === "off"; });
    const unk = all.filter(function(c){ return c.status === "unknown"; }).length;
    // THE ONES THAT NORMALLY RUN, BY NAME. Six checks can never run from this
    // app (marked `always` by domain/daily_check.unavailable); a check that
    // usually works and could not today -- the order list refused, say -- was
    // lost inside that fixed count. Those are named, so "could not check the
    // orders" is never read as "no orders to worry about".
    const failed = all.filter(function(c){ return c.status === "unknown" && !c.always; });
    const failedLine = failed.length
      ? '<b>Could not check today:</b> ' + esc(failed.map(function(c){ return c.title; }).join(", ")) + '. '
      : '';
    const unkLine = unk ? failedLine + unk + ' check' + (unk === 1 ? '' : 's') + ' could not be run &mdash; look at '
                        + (unk === 1 ? 'it' : 'those') + ' by hand.' : '';
    // Never green while something could not be looked at (daily.js's rule).
    if(off.length && typeof _dyRow === "function"){
      body = off.map(_dyRow).join("")
        + (unk ? '<div class="hm-part"><i class="ti ti-help-circle" aria-hidden="true"></i> ' + unkLine + '</div>' : '');
    }else if(failed.length){
      body = '<div class="hm-part"><i class="ti ti-alert-triangle" aria-hidden="true"></i> ' + unkLine
        + ' Nothing else the round checked needs you.</div>';
    }else if(unk){
      body = '<div class="hm-part"><i class="ti ti-help-circle" aria-hidden="true"></i> Nothing the round could check needs you, but '
        + unkLine + '</div>';
    }else{
      body = '<div class="hm-ok"><i class="ti ti-circle-check" aria-hidden="true"></i> Nothing the round checks needs you right now.</div>';
    }
    body += '<div class="hm-foot">' + open + '</div>';
  }else if(DAILY.note){
    body = (typeof uiError === "function") ? uiError("The daily round could not run", DAILY.note, "homeRefresh", "home")
         : '<div class="hm-err">' + esc(DAILY.note) + '</div>';
  }else if(!_hOrdersSettled()){
    body = '<div class="hm-loading"><span class="genspin" aria-hidden="true"></span> Waiting for the orders, then the daily round runs…</div>';
  }else{
    body = '<div class="hm-loading"><span class="genspin" aria-hidden="true"></span> Running the daily round…</div>';
  }
  return '<section class="hm-sec"><h3 class="hm-h">Needs attention today</h3>' + body + '</section>';
}

/* Written only when it would change, with focus put back on the same card, so
 * the redraws while data arrives never take a keyboard user's place. */
function homeRender(){
  const host = document.getElementById("home_body");
  if(!host) return;
  const name = (typeof ACTIVE_WS !== "undefined" && ACTIVE_WS) ? (ACTIVE_WS.label || ACTIVE_WS.key || "") : "";
  const mkt = (typeof WS_MARKET !== "undefined" && WS_MARKET && WS_MARKET !== "__all__") ? WS_MARKET : "";
  const sub = document.getElementById("home_sub");
  const subTxt = [name, mkt].filter(Boolean).join(" · ");
  if(sub && sub.textContent !== subTxt) sub.textContent = subTxt;
  if(!_hWs()){
    // Nobody's Home (see _hWs): a switch still settling, or a workspace that
    // is not one account. Neither may show the previous account's numbers.
    const settling = typeof ACTIVE_WS !== "undefined" && ACTIVE_WS && ACTIVE_WS.account;
    const msg = settling
      ? '<div class="hm-loading"><span class="genspin" aria-hidden="true"></span> Opening the account\u2026</div>'
      : (typeof uiEmpty === "function" ? uiEmpty("Home shows one account", "Open an account from the account switcher to see its queues.")
         : '<div class="empty">Open an account to see its queues.</div>');
    if(host._hmHtml !== msg || !host.childElementCount){ host.innerHTML = msg; host._hmHtml = msg; }
    return;
  }
  const q = _hQueues();
  const cards = q.length
    ? '<div class="hm-queue" role="list">' + q.map(function(x){ return '<div role="listitem">' + _hCard(x) + '</div>'; }).join("") + '</div>'
      + _hQueueErrors(q)
    : (typeof uiEmpty === "function" ? uiEmpty("Nothing here for you to open.")
       : '<div class="empty">Nothing here for you to open.</div>');
  const html = '<section class="hm-sec"><h3 class="hm-h">Your queues</h3>' + cards + '</section>'
    + _hToday() + _hRound();
  if(host._hmHtml === html && host.childElementCount) return;   // emptied by a switch: draw
  const f = document.activeElement;
  const key = (f && host.contains(f)) ? f.getAttribute("data-hk") : null;
  host.innerHTML = html;
  host._hmHtml = html;
  if(key){
    const again = host.querySelector('[data-hk="' + key.replace(/"/g, '\\"') + '"]');
    if(again) again.focus({preventScroll: true});
  }
}
