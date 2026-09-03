// ============ THE SIDEBAR FOLDS AWAY ============
//
// "also make the sidebar hideable like in amazon"
//
// FOLDED, IT IS A HAMBURGER AND NOTHING ELSE. Owner's decision, 27 Aug 2026:
//
//     "when the sidebar is collapsed, it currently shows a vertical strip of
//      icons. This takes up space and looks cluttered. Instead: when collapsed,
//      show ONLY a hamburger menu icon (☰) at the top left -- exactly like
//      Amazon Seller Central does. The icon strip approach is removed."
//
// It used to fold to a rail of icons, on the argument that a menu which
// disappears leaves nothing to navigate WITH. That argument does not hold here:
// the hamburger stays, in the corner, which is where every app that does this
// puts it -- so there is always something to open the menu with. What the rail
// actually cost was 54px of every screen for a column of unlabelled glyphs.
//
// _navFillTitles is kept even though nothing is now shown to hover: the titles
// are the accessible names of the items when the menu is OPEN too, and several
// screens' rows carry a real explanation in that attribute.
//
// The state is remembered per browser, because a person who wants the room
// wants it every time, not once.

const NAVMINI_KEY = "alta_navmini";

/* The labels are bare text nodes -- <div class="navitem"><i></i> Listings</div>
   has no element around the word. Folded, the text is collapsed to font-size 0,
   which leaves an icon with no name unless something says what it is. So the
   name is copied into the title attribute before it disappears.

   Read from the DOM at fold time rather than from a list written here: the nav
   gains items (Repricer, ASIN Monitor, Import seller) and a hardcoded map would
   be a second copy of the menu, silently missing whatever was added last. */
function _navFillTitles(){
  document.querySelectorAll("#workspace .sidebar .navitem").forEach(function(el){
    if(el.getAttribute("data-navtitle")) return;      // done already
    // textContent, not innerText: the item may be hidden mid-fold, and innerText
    // returns "" for anything not being rendered.
    const label = (el.textContent || "").replace(/\s+/g, " ").trim();
    if(!label) return;
    el.setAttribute("data-navtitle", "1");
    // Never overwrite a title someone wrote on purpose -- several of these carry
    // a real explanation, which beats the bare label.
    if(!el.getAttribute("title")) el.setAttribute("title", label);
  });
}

function navMiniOn(){
  return document.getElementById("workspace")
      && document.getElementById("workspace").classList.contains("navmini");
}

function setSidebarMini(on, remember){
  const ws = document.getElementById("workspace");
  if(!ws) return;
  if(on) _navFillTitles();
  ws.classList.toggle("navmini", !!on);
  const btn = document.getElementById("navtoggle");
  if(btn){
    // THE THREE LINES, ALWAYS, and the word underneath them tells you what
    // pressing it will do.
    //
    //     "in the app i see that there is an option to expand or hide that side
    //      bar but i want it to behave like amazon, a SIDE Bar when clicked on
    //      3 lines it expands the side bar and when clicked [again it hides]"
    //
    // Two things were wrong. The icon was a sidebar-collapse glyph that changed
    // direction, which nobody reads as "the menu button" -- Amazon, Seller
    // Central and every app that has one use a hamburger, and it does not
    // change shape. And the label said "Hide menu" in BOTH states, so once the
    // menu was hidden the only control on screen still offered to hide it.
    btn.innerHTML = '<i class="ti ti-menu-2"></i><span>'
                  + (on ? "Show menu" : "Hide menu") + '</span>';
    btn.title = (on ? "Show the menu" : "Hide the menu") + " (Ctrl+B)";
    btn.setAttribute("aria-expanded", on ? "false" : "true");
    btn.setAttribute("aria-label", on ? "Show the menu" : "Hide the menu");
  }
  if(remember !== false){
    try{ localStorage.setItem(NAVMINI_KEY, on ? "1" : "0"); }catch(e){}
  }
  // Charts size themselves to their container, and the container just changed
  // width by 156px. Without this they keep the old width until the next redraw,
  // which on the Sales screen is the next time you touch a control.
  try{ window.dispatchEvent(new Event("resize")); }catch(e){}
}

/* ONE MENU, ONE STATE.
 *
 *     "i want sidebar overlay"
 *
 * The sidebar is a drawer at every width now (static/css/mobile.css), so the
 * desktop fold this file was written for has nothing left to fold: there is no
 * in-flow sidebar to give 156px back from, and the page is full width whether
 * the menu is open or shut.
 *
 * So this button -- which sits INSIDE the drawer -- closes it, and Ctrl+B
 * toggles it, both through mnavToggle(). Two functions writing two different
 * classes onto two different elements for one menu is how one ends up quietly
 * undoing the other, which is the reason mobilenav.js gives for having been
 * kept separate in the first place. That reason has now expired: there is one
 * behaviour, so there is one owner of it.
 *
 * setSidebarMini() and the navmini class are left in place and unused rather
 * than deleted, and the remembered preference is now CLEARED on load -- see
 * initSidebarMini below for the bug that made that necessary.
 */
function toggleSidebar(){
  if(typeof mnavToggle === "function"){ mnavToggle(); return; }
  setSidebarMini(!navMiniOn());      // mobilenav.js absent: the old behaviour
}

/* THE REMEMBERED FOLD IS THROWN AWAY, and this is a bug I shipped.
 *
 *     "click it -> sidebar opens with ALL nav items visible immediately (no
 *      'Show menu' text, no empty drawer)"
 *
 * Anyone who had ever folded the old desktop sidebar has alta_navmini = "1" in
 * localStorage. This function read it back and set `navmini` on #workspace,
 * and dashboard.css:450 says:
 *
 *     #workspace.navmini .sidebar>*:not(.navtoggle){display:none}
 *
 * so the drawer opened with every item hidden and nothing in it but the toggle
 * -- a menu containing the words "Show menu" and nothing else. The override I
 * added to mobile.css alongside the drawer LOSES on specificity: that selector
 * carries an id and three classes (:not(.navtoggle) counts), mine carried an id
 * and two.
 *
 * So the preference is removed rather than read. It is not a preference any
 * more: there is no in-flow sidebar to fold, and nothing in the app can set it
 * again. Removing it also means a person who folded the menu once, months ago,
 * is not still living with the consequence.
 *
 * The CSS override is kept as well, with !important, because this only helps
 * the load path -- anything that sets the class later would hide the drawer
 * again, and one of the two fixes alone leaves that door open.
 */
function initSidebarMini(){
  try{ localStorage.removeItem(NAVMINI_KEY); }catch(e){}
  setSidebarMini(false, false);
}

// Ctrl+B, the shortcut every editor and Seller Central itself uses for this.
// Ignored while typing, or a search box would fold the menu instead of taking
// the letter.
document.addEventListener("keydown", function(ev){
  if(!(ev.ctrlKey || ev.metaKey) || ev.altKey || ev.shiftKey) return;
  if(String(ev.key).toLowerCase() !== "b") return;
  const t = ev.target;
  const tag = t && t.tagName ? t.tagName.toUpperCase() : "";
  if(tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT"
     || (t && t.isContentEditable)) return;
  ev.preventDefault();
  toggleSidebar();
});

document.addEventListener("DOMContentLoaded", initSidebarMini);
