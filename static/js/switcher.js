// ============ ACCOUNT AND MARKETPLACE, FROM THE SIDEBAR ============
//
// "i thought the plan should be to remove our current home page and integrate
//  the features of the home page on the same page where we see listings and
//  other things same like orbit"
//
// Orbit has no landing page. You arrive on a working screen, and the brand and
// the marketplace are two rows in the sidebar that open a list. Ours had a
// separate grid of workspace cards whose only job was choosing an account, so
// every session began on a screen with no work on it.
//
// The home grid still EXISTS -- it is where accounts are added and edited, and
// it is one click away under Tools. What changes is that it is no longer the
// place you land, and no longer the only way to switch.
//
// Measured off Orbit's sidebar: the marketplace row is a nav item 34px tall,
// 8/16 padding, 14px/500, in gold (rgb(251,191,36)) when it is the live one,
// with the country's flag beside it.

let _SWITCH_MENU = null;

/* One menu implementation for both rows. Two would drift -- and this one has to
   close on an outside click, on Escape, and on choosing something, which is
   three chances to only fix one of them. */
function _switchMenu(anchor, items, onPick, opts){
  opts = opts || {};
  _closeSwitchMenu();
  const el = document.createElement("div");
  el.className = "switchmenu";
  // A HEADING, because the menu has two levels now and "United Kingdom /
  // United States" with no name above it does not say WHOSE marketplaces
  // these are -- on an app that shows three limited companies.
  const head = opts.title
    ? '<div class="switchhead">' + esc(opts.title) + '</div>' : "";
  el.innerHTML = head + (items.map(function(it, i){
    return '<button class="switchopt' + (it.on ? " on" : "")
      + (it.disabled ? " off" : "") + '" data-i="' + i + '"'
      // Disabled rather than absent: "Amazon has this account in the UK and
      // not in Germany" is a fact worth seeing, and a row that is simply
      // missing says nothing at all.
      + (it.disabled ? " disabled" : "") + '>'
      + (it.icon ? '<span class="ic">' + it.icon + '</span>' : "")
      + '<span class="lbl">' + esc(it.label) + '</span>'
      + (it.note ? '<span class="note">' + esc(it.note) + '</span>' : "")
      + (it.on ? '<i class="ti ti-check"></i>' : "")
      // BOTH, ON THE OPEN ACCOUNT. The tick says "this is the one you are in";
      // the chevron says "and there is more inside it". Suppressing the chevron
      // on the open account would hide the drill-down from the one account
      // whose marketplaces you are most likely to want to change.
      + (it.drill ? '<i class="ti ti-chevron-right"></i>' : "")
      + '</button>';
  }).join("") || '<div class="switchempty">Nothing to choose from.</div>');

  // A MENU THAT THROWS LEAVES ITSELF IN THE DOM, unpositioned and with no way
  // to close it -- the exact shape of the three-dot bug in listings.js. So an
  // anchor that cannot be measured falls back to the top-left corner rather
  // than taking the menu down with it.
  let r = {left: 8, top: 8, bottom: 8, right: 8, width: 0, height: 0};
  try{
    if(anchor && anchor.getBoundingClientRect) r = anchor.getBoundingClientRect();
  }catch(e){}
  el.style.left = Math.round(r.left) + "px";
  el.style.top = Math.round(r.bottom + 4) + "px";
  el.style.minWidth = Math.round(r.width) + "px";
  document.body.appendChild(el);
  _SWITCH_MENU = el;
  // KEPT ON SCREEN. The header chip sits near the left, but the sidebar row is
  // at the bottom of a tall drawer and this menu is now taller than it was --
  // measured after appending, because until then it has no height.
  try{
    const b = el.getBoundingClientRect();
    if(b.right > window.innerWidth - 8){
      el.style.left = Math.max(8, window.innerWidth - 8 - b.width) + "px";
    }
    if(b.bottom > window.innerHeight - 8){
      // Above the anchor instead, unless there is no room there either -- in
      // which case pinned to the top, where it can at least scroll.
      const above = Math.round(r.top - 4 - b.height);
      el.style.top = (above >= 8 ? above : 8) + "px";
      if(above < 8) el.style.maxHeight = (window.innerHeight - 16) + "px";
    }
  }catch(e){}

  el.addEventListener("click", function(ev){
    const b = ev.target.closest(".switchopt");
    if(!b || b.disabled) return;
    const it = items[Number(b.dataset.i)];
    _closeSwitchMenu();
    if(it && onPick) onPick(it);
  });
  // Deferred, or the click that OPENED the menu closes it again immediately.
  setTimeout(function(){
    document.addEventListener("mousedown", _switchOutside);
    document.addEventListener("keydown", _switchEsc);
  }, 0);
}

function _switchOutside(ev){
  if(_SWITCH_MENU && !_SWITCH_MENU.contains(ev.target)) _closeSwitchMenu();
}
function _switchEsc(ev){ if(ev.key === "Escape") _closeSwitchMenu(); }

function _closeSwitchMenu(){
  document.removeEventListener("mousedown", _switchOutside);
  document.removeEventListener("keydown", _switchEsc);
  if(_SWITCH_MENU && _SWITCH_MENU.parentNode) _SWITCH_MENU.parentNode.removeChild(_SWITCH_MENU);
  _SWITCH_MENU = null;
}

/* The account list. Every account, and a way to reach the grid where accounts
   are added.
 *
 * THE DROPSHIPPING WORKSPACE IS GONE, and it should never have outlived the
 * business model. It was the app's original no-account mode -- "eBay → Amazon
 * arbitrage" -- and CLAUDE.md rule 1 is explicit that this app does not do
 * that: it creates NEW listings under the owner's own brands, and the
 * competitor ASIN is a reference for product data and nothing else. A workspace
 * whose subtitle contradicts the first rule in the file is a place for work to
 * go wrong.
 *
 * Removed here and on the home screen. The internal `or "dropshipping"` string
 * a few routes still fall back to is NOT this: it is the id used when no
 * account is open at all, and it keeps those routes from dividing by a null
 * account. Nothing can reach it from the interface any more. */
/* WHERE THE MENU HANGS FROM. The header chip when it is on screen, the sidebar
 * row otherwise -- one menu, two places it can be opened from, and it has to
 * appear under whichever was actually pressed. This used to be hardcoded to the
 * sidebar row, so opening it from the header chip put the menu on the far side
 * of the screen from the button that opened it (and, with the sidebar shut,
 * measured a hidden element).
 *
 * ev.currentTarget first, for exactly the reason drawerMore now does it: it is
 * the element the handler is on, whichever that turns out to be. */
function _switchAnchor(ev, fallbackId){
  const t = ev && (ev.currentTarget
                   || (ev.target && ev.target.closest && ev.target.closest("button,.navitem")));
  if(t && t.getBoundingClientRect){
    const r = t.getBoundingClientRect();
    if(r.width || r.height) return t;      // on screen, so it can be measured
  }
  return document.getElementById(fallbackId);
}

function openAccountSwitch(ev){
  if(ev) ev.stopPropagation();
  const anchor = _switchAnchor(ev, "nav_acctswitch");
  if(!anchor) return;
  const cur = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT) ? CUR_ACCOUNT.id : "";
  const items = (ACCOUNTS || []).map(function(a){
    // Say which are connected: a draft-only account cannot do half the screens,
    // and finding that out after switching is a wasted move.
    //
    // AND HOW MANY MARKETPLACES IT SELLS IN, because the next thing this menu
    // does is ask you to pick one.
    const n = (a.marketplaces || []).length;
    const note = !a.has_creds ? "draft-only"
               : (n > 1 ? (n + " marketplaces")
                        : (n === 1 ? mktName(a.marketplaces[0]) : ""));
    return {kind: "acct", id: a.id, label: a.label || a.id, on: a.id === cur,
            icon: '<i class="ti ti-building-store"></i>', note: note,
            // Only an account with somewhere to go drills down.
            drill: n > 1};
  });
  items.push({kind: "manage", label: "Manage accounts…",
              icon: '<i class="ti ti-settings"></i>'});
  _switchMenu(anchor, items, function(it){
    if(it.kind === "manage"){ goHome(); return; }
    // TWO LEVELS, AND THE SECOND ONE IS SKIPPED WHEN IT WOULD BE A LIST OF ONE.
    //
    //     "Level 1 -- Account list ... Level 2 -- When an account is clicked,
    //      show its marketplaces."
    //
    // Amazon's switcher works that way because a seller account really does
    // span several countries. Most of these accounts sell in one, and making
    // somebody choose from a list with a single entry is a click that answers
    // nothing -- so the drill-down happens where there is genuinely a choice
    // and is skipped where there is not.
    if(it.drill){ openMarketSwitchFor(it.id, anchor); return; }
    enterAccount(it.id);
  }, {title: "Switch account"});
}

/* Level two: the marketplaces of ONE account, named rather than assumed.
 *
 * WHAT "NEEDS REGISTRATION" MAY AND MAY NOT SAY. a.marketplaces is what
 * detectMarketplaces() found by asking Amazon -- so it is the registered set,
 * and anything absent from it is genuinely not registered. But an account that
 * has NEVER been detected has an empty list, and calling every country "needs
 * registration" from that would be inventing a measurement (Rule 4). So the
 * greyed rows are drawn only when there is a detected list to subtract from,
 * and an undetected account is offered the detection instead.
 *
 * The greyed list is the majors, not all 22 in marketplaces.js: a dropdown
 * listing twenty countries nobody sells in buries the two that matter.
 */
const _SWITCH_MAJORS = ["UK", "US", "DE", "FR", "IT", "ES", "CA", "AU", "JP"];

function openMarketSwitchFor(accountId, anchor){
  const a = (ACCOUNTS || []).filter(function(x){ return x.id === accountId; })[0];
  if(!a){ enterAccount(accountId); return; }
  const isCur = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT)
                && CUR_ACCOUNT.id === a.id;
  const mkts = a.marketplaces || [];
  const items = [];
  // Back, first, because a drill-down with no way out is a trap.
  items.push({kind: "back", label: "All accounts", icon: '<i class="ti ti-arrow-left"></i>'});
  mkts.forEach(function(m){
    items.push({kind: "mkt", id: m, label: mktName(m), icon: mktFlag(m),
                on: isCur && m === WS_MARKET,
                note: (a.default_marketplace === m) ? "default · registered"
                                                    : "registered"});
  });
  if(mkts.length > 1){
    items.push({kind: "mkt", id: "__all__", label: "All marketplaces", icon: "🌐",
                on: isCur && WS_MARKET === "__all__", note: "slower — fetches each"});
  }
  // The ones this account is NOT in. Only meaningful because the list above was
  // measured; see the note on this function.
  if(mkts.length){
    _SWITCH_MAJORS.forEach(function(m){
      if(mkts.indexOf(m) >= 0) return;
      items.push({kind: "none", label: mktName(m), icon: mktFlag(m),
                  note: "needs registration", disabled: true});
    });
  }
  items.push({kind: "detect", label: mkts.length ? "Re-detect marketplaces"
                                                 : "Detect marketplaces",
              icon: '<i class="ti ti-radar"></i>',
              note: "asks Amazon which this account sells in"});
  _switchMenu(anchor, items, function(it){
    if(it.kind === "back"){ openAccountSwitch({currentTarget: anchor,
                                               stopPropagation: function(){}}); return; }
    if(it.kind === "detect"){ detectMarketplaces(a.id); return; }
    if(it.kind === "none") return;             // disabled; nothing to switch to
    // SWITCHING ACCOUNT AND MARKETPLACE IS ONE ACT from here. Picking Germany
    // under Selvora while Nestwell is open has to do both, or the screen would
    // show Selvora's marketplace over Nestwell's listings.
    // enterAccountAt already does both, in that order, and is what the URL
    // router uses to open /w/<account>/<section> on a given marketplace.
    if(!isCur) enterAccountAt(a.id, it.id);
    else switchAccountMarket(it.id);
  }, {title: a.label || a.id});
}

/* The marketplace list for the open account, each with its flag. */
function openMarketSwitch(ev){
  if(ev) ev.stopPropagation();
  const anchor = document.getElementById("nav_mktswitch");
  if(!anchor) return;
  const a = (typeof CUR_ACCOUNT !== "undefined") ? CUR_ACCOUNT : null;
  if(!a){
    toast("Open an account first — the dropshipping workspace has no marketplace of its own.");
    return;
  }
  const mkts = (a.marketplaces && a.marketplaces.length) ? a.marketplaces : [];
  // Detecting them is an ACTION, not an error. This used to be a dead end that
  // sent you to another screen to press a button that also lived in the
  // marketplace strip in the toolbar -- and when that duplicate strip was
  // removed, this was the only way left to reach it.
  if(!mkts.length){
    _switchMenu(anchor, [{kind: "detect", label: "Detect marketplaces",
                          icon: '<i class="ti ti-radar"></i>',
                          note: "asks Amazon which this account sells in"}],
                function(){ detectMarketplaces(a.id); });
    return;
  }
  const items = mkts.map(function(m){
    return {kind: "mkt", id: m, label: mktName(m), on: m === WS_MARKET,
            icon: mktFlag(m),
            note: (a.default_marketplace === m) ? "default" : ""};
  });
  items.push({kind: "mkt", id: "__all__", label: "All marketplaces",
              on: WS_MARKET === "__all__", icon: "🌐",
              note: "slower — fetches each"});
  // The two things the old toolbar strip could do that a plain list cannot.
  // They came with it when it was removed rather than being dropped: setting a
  // default was reachable from nowhere else at all.
  if(WS_MARKET && WS_MARKET !== "__all__" && a.default_marketplace !== WS_MARKET){
    items.push({kind: "default", label: "Set " + mktName(WS_MARKET) + " as default",
                icon: "☆", note: "opens here next time"});
  }
  items.push({kind: "detect", label: "Re-detect marketplaces",
              icon: '<i class="ti ti-refresh"></i>'});
  _switchMenu(anchor, items, function(it){
    if(it.kind === "default") setDefaultMarketplace();
    else if(it.kind === "detect") detectMarketplaces(a.id);
    else switchAccountMarket(it.id);
  });
}

/* Keep the two rows showing what is actually open. Called after every switch,
   so the sidebar can never disagree with the screen. */
function renderSwitchRows(){
  const al = document.getElementById("nav_acct_label");
  const mf = document.getElementById("nav_mkt_flag");
  const ml = document.getElementById("nav_mkt_label");
  const mrow = document.getElementById("nav_mktswitch");
  const a = (typeof CUR_ACCOUNT !== "undefined") ? CUR_ACCOUNT : null;
  // "No account" rather than the name of the workspace that used to be here.
  // It is also the more useful thing to read: the screens below behave
  // differently with nothing open, and this row is where you find that out.
  const name = a ? (a.label || a.id) : "No account open";
  if(al) al.textContent = name;
  // AND THE HEADER CHIP, from the same line that writes the sidebar row.
  //
  // The sidebar is a drawer now, so its account row is behind a click; the chip
  // in the app bar is the one that is always on screen. Written HERE rather
  // than by a second listener, so the two cannot end up naming different
  // companies -- which on an app that shows three limited companies through one
  // screen is the mistake worth designing out (CLAUDE.md Rule 12).
  const hdr = document.getElementById("appbar_acct_label");
  if(hdr) hdr.textContent = name;
  const m = (typeof WS_MARKET !== "undefined") ? WS_MARKET : "";
  if(mf) mf.textContent = m ? mktFlag(m) : "🌐";
  if(ml) ml.textContent = m ? mktName(m) : "No marketplace";
  // The dropshipping workspace has no marketplace of its own, so the row is
  // dimmed rather than offering a choice that does not exist.
  if(mrow) mrow.style.opacity = a ? "" : ".45";
}
