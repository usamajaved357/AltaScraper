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
function _switchMenu(anchor, items, onPick){
  _closeSwitchMenu();
  const el = document.createElement("div");
  el.className = "switchmenu";
  el.innerHTML = items.map(function(it, i){
    return '<button class="switchopt' + (it.on ? " on" : "") + '" data-i="' + i + '">'
      + (it.icon ? '<span class="ic">' + it.icon + '</span>' : "")
      + '<span class="lbl">' + esc(it.label) + '</span>'
      + (it.note ? '<span class="note">' + esc(it.note) + '</span>' : "")
      + (it.on ? '<i class="ti ti-check"></i>' : "")
      + '</button>';
  }).join("") || '<div class="switchempty">Nothing to choose from.</div>';

  const r = anchor.getBoundingClientRect();
  el.style.left = Math.round(r.left) + "px";
  el.style.top = Math.round(r.bottom + 4) + "px";
  el.style.minWidth = Math.round(r.width) + "px";
  document.body.appendChild(el);
  _SWITCH_MENU = el;

  el.addEventListener("click", function(ev){
    const b = ev.target.closest(".switchopt");
    if(!b) return;
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

/* The account list. Every account, plus the cross-account dropshipping
   workspace and a way to reach the grid where accounts are added. */
function openAccountSwitch(ev){
  if(ev) ev.stopPropagation();
  const anchor = document.getElementById("nav_acctswitch");
  if(!anchor) return;
  const cur = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT) ? CUR_ACCOUNT.id : "";
  const items = (ACCOUNTS || []).map(function(a){
    // Say which are connected: a draft-only account cannot do half the screens,
    // and finding that out after switching is a wasted move.
    return {kind: "acct", id: a.id, label: a.label || a.id, on: a.id === cur,
            icon: '<i class="ti ti-building-store"></i>',
            note: a.has_creds ? "" : "draft-only"};
  });
  items.push({kind: "drop", label: "Dropshipping", on: !cur,
              icon: '<i class="ti ti-shopping-cart"></i>', note: "cross-account"});
  items.push({kind: "manage", label: "Manage accounts…",
              icon: '<i class="ti ti-settings"></i>'});
  _switchMenu(anchor, items, function(it){
    if(it.kind === "acct") enterAccount(it.id);
    else if(it.kind === "drop") enterDropshipping();
    else goHome();
  });
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
  if(!mkts.length){
    toast("No marketplaces detected for this account yet. Open Account & sheets to detect them.");
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
  _switchMenu(anchor, items, function(it){ switchAccountMarket(it.id); });
}

/* Keep the two rows showing what is actually open. Called after every switch,
   so the sidebar can never disagree with the screen. */
function renderSwitchRows(){
  const al = document.getElementById("nav_acct_label");
  const mf = document.getElementById("nav_mkt_flag");
  const ml = document.getElementById("nav_mkt_label");
  const mrow = document.getElementById("nav_mktswitch");
  const a = (typeof CUR_ACCOUNT !== "undefined") ? CUR_ACCOUNT : null;
  if(al) al.textContent = a ? (a.label || a.id) : "Dropshipping";
  const m = (typeof WS_MARKET !== "undefined") ? WS_MARKET : "";
  if(mf) mf.textContent = m ? mktFlag(m) : "🌐";
  if(ml) ml.textContent = m ? mktName(m) : "No marketplace";
  // The dropshipping workspace has no marketplace of its own, so the row is
  // dimmed rather than offering a choice that does not exist.
  if(mrow) mrow.style.opacity = a ? "" : ".45";
}
