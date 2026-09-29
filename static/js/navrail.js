// static/js/navrail.js -- the always-visible icon rail (Direction A, prototype A).
//
//     "yes aways visible but you can addthe option to hide but use new ddesign
//      from the mockup we decided"                     (owner, 29 Sep 2026)
//
// A 64px column on the left of every screen, one button per destination with
// its icon and a short name under it (prototypes/design-review/A-cockpit.html).
// It REPLACES nothing: the full menu (the overlay sidebar, with the account and
// marketplace pickers) is still one press away -- the rail's own "Menu" button
// and the top-left hamburger both open it.
//
// BUILT FROM THE SIDEBAR, NOT A SECOND COPY OF IT (CLAUDE.md Rule 12). Home is
// the sidebar's Home item; every other button is a .navgroup of the sidebar,
// named by its data-rail attribute. Pressing one opens a small menu of that
// group's screens, and choosing one CLICKS THE SIDEBAR'S OWN ITEM -- so
// routing, permissions (an item hidden from a person is hidden here too) and
// the active highlight are exactly the sidebar's. A screen added to the sidebar
// appears here by itself.
//
// ALWAYS SHOWN, NO HIDE (owner, 30 Sep 2026: "i dont want that option to hide
// sidebar and show side bar, i am okay with the small symbols"). A group's
// screens open when the pointer RESTS on its button ("the side menu bar should
// show the different subpages after the cursor is hover over it") -- a click
// still opens it too, for touch screens and the keyboard. On a phone
// (<= 860px, MNAV_BREAKPOINT) the rail is not drawn at all: the phone keeps its
// drawer (the owner's mobile layout, matched to Orbit).

// Anyone who used the old Hide gets the rail back: the preference is gone.
function _nrForgetHidden(){
  try{ localStorage.removeItem("alta_navrail"); }catch(e){}
  document.body.classList.remove("railoff");
}
function _nrEsc(s){ return (typeof esc === "function") ? esc(String(s == null ? "" : s)) : String(s == null ? "" : s); }

// Visible to this person: not display:none on the item itself (permissions and
// per-account items such as Supplier Import hide them that way).
function _nrShown(el){
  return !!el && el.style.display !== "none" && !el.hidden;
}

function _nrIcon(el){
  const i = el && el.querySelector("i.ti");
  if(!i) return "ti-point";
  const c = Array.prototype.find.call(i.classList, function(k){ return k.indexOf("ti-") === 0; });
  return c || "ti-point";
}

// The words of an item, without the badge numbers inside it.
function _nrLabel(el){
  const c = el.cloneNode(true);
  c.querySelectorAll("span[id$='_badge'], .navmbadge").forEach(function(b){ b.remove(); });
  return (c.textContent || "").replace(/\s+/g, " ").trim();
}

function _nrHtml(){
  let h = '';
  const home = document.querySelector('#workspace .sidebar .navitem[data-sec="home"]');
  if(_nrShown(home)){
    h += '<button type="button" class="nr-btn" data-nr="home" onclick="navRailGo(\'home\')"'
       + ' title="' + _nrEsc(home.getAttribute("title") || "Home") + '">'
       + '<i class="ti ti-home" aria-hidden="true"></i><span>Home</span></button>';
  }
  document.querySelectorAll("#workspace .sidebar .navgroup[data-rail]").forEach(function(g){
    const name = g.getAttribute("data-grp") || "";
    const kids = Array.prototype.filter.call(g.querySelectorAll(".navkids .navitem"), _nrShown);
    if(!kids.length) return;                       // nothing this person may open
    const master = g.querySelector(".navmaster");
    h += '<button type="button" class="nr-btn" data-nr="' + _nrEsc(name) + '"'
       + ' aria-haspopup="menu" aria-expanded="false"'
       + ' onclick="navRailOpen(event,' + jsArg(name) + ')"'
       + ' title="' + _nrEsc(master ? _nrLabel(master) : name) + '">'
       + '<i class="ti ' + _nrEsc(_nrIcon(master)) + '" aria-hidden="true"></i>'
       + '<span>' + _nrEsc(g.getAttribute("data-rail")) + '</span>'
       + '<b class="nr-badge" data-nrb="' + _nrEsc(name) + '"></b></button>';
  });
  h += '<span class="nr-sp"></span>'
     + '<button type="button" class="nr-btn" data-nr="-menu" onclick="navRailClose();mnavOpen()" title="The full menu, with the account and marketplace (Ctrl+B)">'
     + '<i class="ti ti-menu-2" aria-hidden="true"></i><span>Menu</span></button>';
  return h;
}

/* Rebuilt only when the buttons would differ, and focus is put back on the
 * same button: a keyboard user on the rail keeps their place when a badge
 * elsewhere in the sidebar changes (design-system.md section 8). */
function navRailBuild(){
  const rail = document.getElementById("navrail");
  if(!rail) return;
  const h = _nrHtml();
  if(rail._nrHtml !== h){
    const f = document.activeElement;
    const key = (f && rail.contains(f)) ? f.getAttribute("data-nr") : null;
    rail.innerHTML = h;
    rail._nrHtml = h;
    if(key){
      const again = rail.querySelector('.nr-btn[data-nr="' + key + '"]');
      if(again) again.focus({preventScroll: true});
    }
  }
  navRailSync();
}

function navRailGo(sec){
  navRailClose();
  if(typeof navTo === "function") navTo(sec);
}

/* Which button holds the screen you are on, and the badges a group carries
 * (stock and monitor alerts): the same numbers navgroups.js sums for a shut
 * group, so the rail never says something the menu does not. */
function navRailSync(sec){
  const rail = document.getElementById("navrail");
  if(!rail) return;
  const cur = sec || (typeof CUR_SEC !== "undefined" ? CUR_SEC : "");
  const grp = cur === "home" ? "home" : (typeof navGroupOf === "function" ? navGroupOf(cur) : "");
  rail.querySelectorAll(".nr-btn[data-nr]").forEach(function(b){
    const on = b.getAttribute("data-nr") === grp;
    b.classList.toggle("on", on);
    if(on) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  rail.querySelectorAll(".nr-badge").forEach(function(dot){
    const g = document.querySelector('.navgroup[data-grp="' + dot.getAttribute("data-nrb") + '"]');
    let total = 0, any = false;
    if(g) g.querySelectorAll(".navkids .navitem span[id$='_badge']").forEach(function(b){
      if(b.style.display === "none") return;
      any = true;
      const n = parseInt((b.textContent || "").replace(/[^0-9]/g, ""), 10);
      if(!isNaN(n)) total += n;
    });
    dot.style.display = any ? "" : "none";
    dot.textContent = total > 0 ? String(total) : "";
  });
}

function navRailClose(){
  const m = document.getElementById("nrfly");
  if(m) m.remove();
  document.querySelectorAll("#navrail .nr-btn[aria-expanded='true']").forEach(function(b){
    b.setAttribute("aria-expanded", "false");
  });
}

/* The group's screens, as a menu beside the rail. Choosing one presses the
 * sidebar's own item (see the top of this file). Pressing the same button
 * again shuts it; pressing another group's button swaps to that group. */
function navRailOpen(ev, name, hover){
  const btn = (ev && ev.currentTarget && ev.currentTarget.nodeType === 1) ? ev.currentTarget
            : document.querySelector('#navrail .nr-btn[data-nr="' + name + '"]');
  const wasOpen = btn && btn.getAttribute("aria-expanded") === "true";
  if(wasOpen && hover) return;              // already showing: resting on it changes nothing
  navRailClose();
  if(wasOpen) return;
  const g = document.querySelector('.navgroup[data-grp="' + name + '"]');
  if(!g || !btn) return;
  const kids = Array.prototype.filter.call(g.querySelectorAll(".navkids .navitem"), _nrShown);
  const cur = (typeof CUR_SEC !== "undefined") ? CUR_SEC : "";
  const m = document.createElement("div");
  m.id = "nrfly";
  m.className = "nr-fly";
  m.setAttribute("aria-label", g.getAttribute("data-rail") || name);
  m.innerHTML = '<div class="nr-fly-h">' + _nrEsc(g.getAttribute("data-rail") || name) + '</div>'
    + kids.map(function(k, i){
        const sec = k.getAttribute("data-sec") || "";
        return '<button type="button" data-i="' + i + '"' + (sec && sec === cur ? ' class="on"' : '') + '>'
          + '<i class="ti ' + _nrEsc(_nrIcon(k)) + '" aria-hidden="true"></i>'
          + _nrEsc(_nrLabel(k)) + '</button>';
      }).join("");
  m.addEventListener("click", function(e){
    const b = e.target.closest && e.target.closest("button[data-i]");
    if(!b) return;
    const k = kids[+b.getAttribute("data-i")];
    navRailClose();
    if(k) k.click();
  });
  document.body.appendChild(m);
  const r = btn.getBoundingClientRect();
  const top = Math.max(48, Math.min(r.top, window.innerHeight - m.offsetHeight - 8));
  m.style.top = top + "px";
  btn.setAttribute("aria-expanded", "true");
  // Opened by a click or a key: the keyboard moves into the menu. Opened by
  // the pointer resting there: focus stays put, or merely passing over the
  // rail would pull the page's focus away.
  if(!hover && typeof uiMenuKeys === "function") uiMenuKeys(m, btn, navRailClose);
  m.addEventListener("mouseenter", _nrHoverKeep);
  m.addEventListener("mouseleave", _nrHoverLeave);
}

/* OPEN ON HOVER. A short pause before opening, so sweeping the pointer down
 * the rail does not flash every menu; a longer one before closing, so the
 * pointer can travel from the button across to the menu beside it. */
let _nrOpenT = 0, _nrCloseT = 0;
function _nrHoverKeep(){ clearTimeout(_nrCloseT); }
function _nrHoverLeave(){
  clearTimeout(_nrOpenT);
  clearTimeout(_nrCloseT);
  _nrCloseT = setTimeout(navRailClose, 350);
}
function _nrHoverInit(){
  const rail = document.getElementById("navrail");
  if(!rail) return;
  rail.addEventListener("mouseover", function(e){
    const b = e.target.closest && e.target.closest(".nr-btn");
    if(!b) return;
    _nrHoverKeep();
    clearTimeout(_nrOpenT);
    if(b.getAttribute("aria-haspopup") !== "menu"){      // Home, Menu: no sub-pages
      _nrOpenT = setTimeout(navRailClose, 150);
      return;
    }
    const name = b.getAttribute("data-nr");
    _nrOpenT = setTimeout(function(){ navRailOpen({currentTarget: b}, name, true); }, 120);
  });
  rail.addEventListener("mouseleave", _nrHoverLeave);
}

/* ONE outside-click listener for the life of the page. A listener per menu
 * outlived its menu and shut the NEXT one the moment it opened. A click on a
 * rail button is the button's own business (navRailOpen swaps or shuts). */
function _nrOutside(e){
  const m = document.getElementById("nrfly");
  if(!m) return;
  const t = e.target;
  if(m.contains(t) || (t.closest && t.closest("#navrail"))) return;
  navRailClose();
}

/* THE RAIL FOLLOWS THE SIDEBAR WHEN IT CHANGES. Permissions arrive after load
 * (items are hidden then), Supplier Import appears per account, and the alert
 * badges are rewritten by their screens -- each is a change to the sidebar's
 * markup, so one watcher on it keeps the rail true without every one of those
 * places having to know the rail exists. Coalesced to one rebuild per frame;
 * the rail itself is outside the sidebar, so rebuilding it cannot re-trigger. */
let _nrPending = 0;
function _nrSoon(){
  if(_nrPending) return;
  _nrPending = requestAnimationFrame(function(){
    _nrPending = 0;
    if(!document.getElementById("nrfly")) navRailBuild();   // never under an open menu
    else navRailSync();
  });
}

document.addEventListener("DOMContentLoaded", function(){
  _nrForgetHidden();
  navRailBuild();
  _nrHoverInit();
  document.addEventListener("click", _nrOutside);
  const side = document.querySelector("#workspace .sidebar");
  if(side && typeof MutationObserver === "function"){
    new MutationObserver(_nrSoon).observe(side, {subtree: true, childList: true,
      characterData: true, attributes: true, attributeFilter: ["style", "hidden"]});
  }
});
