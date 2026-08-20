/* static/js/bookmarks.js -- pin the screens you actually use.
 *
 *     "give me a bookmark bar like amazon on the top where i can bookmark the
 *      pages i use frequently"
 *
 * Seller Central has one and it is the only part of that interface nobody
 * complains about, for a simple reason: this app has forty-odd screens and any
 * one person uses six of them. The sidebar has to list all forty; this lists
 * the six.
 *
 * WHY IT REMEMBERS, AND WHERE
 *
 * localStorage, PER ACCOUNT. Two things follow from that and both are
 * deliberate:
 *
 *   - it is the browser's, not the server's. A bookmark is a preference about
 *     how somebody works, not data about the business, and it has no business
 *     in config.json or the database.
 *   - it is keyed by account. The screens worth pinning in a live trading
 *     account are not the ones worth pinning in a draft-only one, and a bar
 *     that followed you between them would be wrong in both.
 *
 * IT ADDS NO SCREEN OF ITS OWN. Every entry is a section that already exists
 * and is already reachable; this is a shortcut, never a new destination. The
 * label comes from the nav item itself, so a screen that is renamed is renamed
 * here too and the two cannot drift.
 */
var BMK = {items: [], open: false};

function _bmkKey(){
  var acct = "";
  try{
    acct = (typeof ACTIVE_WS !== "undefined" && ACTIVE_WS && ACTIVE_WS.key)
      ? String(ACTIVE_WS.key) : "";
  }catch(e){}
  return "alta_bookmarks::" + (acct || "_none");
}

function _bmkLoad(){
  try{
    var raw = localStorage.getItem(_bmkKey());
    BMK.items = raw ? (JSON.parse(raw) || []) : [];
  }catch(e){ BMK.items = []; }
  if(!Array.isArray(BMK.items)) BMK.items = [];
}

function _bmkSave(){
  try{ localStorage.setItem(_bmkKey(), JSON.stringify(BMK.items)); }catch(e){}
}

function _bmkEsc(s){
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* THE NAME AND ICON COME FROM THE NAV ITEM, not from a list kept here. A second
 * list would be a second opinion about what a screen is called, and it would be
 * wrong the first time a screen was renamed. */
function _bmkNavInfo(sec){
  var a = document.querySelector('.navitem[data-sec="' + sec + '"]');
  if(!a) return null;
  var icon = a.querySelector("i");
  return {
    sec: sec,
    label: (a.textContent || sec).trim(),
    icon: icon ? icon.className : "ti ti-bookmark"
  };
}

/* Which section is on screen right now, so the star knows what it would pin. */
function _bmkCurrent(){
  try{
    var on = document.querySelector(".navitem.active[data-sec]");
    if(on) return on.getAttribute("data-sec");
  }catch(e){}
  return "";
}

function bmkIsPinned(sec){
  return BMK.items.some(function(x){ return x.sec === sec; });
}

function bmkToggle(sec){
  sec = sec || _bmkCurrent();
  if(!sec) return;
  if(bmkIsPinned(sec)){
    BMK.items = BMK.items.filter(function(x){ return x.sec !== sec; });
  }else{
    var info = _bmkNavInfo(sec);
    // A section with no nav item is not pinnable: there would be nothing to
    // name it and nowhere for the click to go.
    if(!info) return;
    BMK.items.push(info);
  }
  _bmkSave();
  bmkRender();
}

function bmkGo(sec){
  if(typeof navTo === "function") navTo(sec);
  if(typeof altaSyncUrl === "function") altaSyncUrl();
  bmkRender();
}

function bmkRender(){
  var host = document.getElementById("bmkbar");
  if(!host) return;
  var cur = _bmkCurrent();
  var pinned = bmkIsPinned(cur);
  var canPin = !!(cur && _bmkNavInfo(cur));

  var h = "";
  if(BMK.items.length){
    h += BMK.items.map(function(b){
      var on = (b.sec === cur) ? " on" : "";
      return '<button class="bmkchip' + on + '" onclick="bmkGo(' + jsArg(b.sec) + ')" '
        + 'title="' + _bmkEsc(b.label) + '">'
        + '<i class="' + _bmkEsc(b.icon) + '"></i>'
        + '<span>' + _bmkEsc(b.label) + '</span>'
        + '<i class="ti ti-x bmkx" title="Remove from bookmarks" '
        + 'onclick="event.stopPropagation();bmkToggle(' + jsArg(b.sec) + ')"></i>'
        + '</button>';
    }).join("");
  }else{
    // An empty bar that says nothing looks like a broken bar. It says what it
    // is for and how to fill it, once, and then never again.
    h += '<span class="cc bmkhint">Pin the screens you use most — press the '
       + '<i class="ti ti-bookmark"></i> on any page.</span>';
  }

  // The star for the page you are on, at the end, so the bar reads
  // left-to-right as "your pages, then add this one".
  if(canPin){
    h += '<button class="bmkadd' + (pinned ? " on" : "") + '" '
      + 'onclick="bmkToggle()" title="'
      + (pinned ? "Remove this page from your bookmarks"
                : "Bookmark this page") + '">'
      + '<i class="ti ti-bookmark' + (pinned ? "-filled" : "") + '"></i></button>';
  }
  host.innerHTML = h;
  host.style.display = "";
}

/* Called on every navigation and on every account switch: the bar is per
 * account, so switching accounts must reload it rather than repaint the last
 * one's pins. */
function bmkRefresh(){
  _bmkLoad();
  bmkRender();
}

document.addEventListener("DOMContentLoaded", function(){
  _bmkLoad();
  bmkRender();
});
