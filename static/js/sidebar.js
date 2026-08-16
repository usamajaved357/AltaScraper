// ============ THE SIDEBAR FOLDS AWAY ============
//
// "also make the sidebar hideable like in amazon"
//
// Seller Central folds its menu to a rail of icons rather than hiding it
// outright, and that is the right shape: a menu that disappears completely
// leaves nothing to navigate WITH, so getting back to it means hunting for the
// control that brings it back. Folded, every destination is still one click
// away -- it just stops spending 210px of a 1500px screen on words you already
// know.
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
    btn.innerHTML = '<i class="ti ti-layout-sidebar-' + (on ? "right" : "left")
                  + '-collapse"></i><span>Hide menu</span>';
    btn.title = (on ? "Show the menu" : "Hide the menu") + " (Ctrl+B)";
    btn.setAttribute("aria-expanded", on ? "false" : "true");
  }
  if(remember !== false){
    try{ localStorage.setItem(NAVMINI_KEY, on ? "1" : "0"); }catch(e){}
  }
  // Charts size themselves to their container, and the container just changed
  // width by 156px. Without this they keep the old width until the next redraw,
  // which on the Sales screen is the next time you touch a control.
  try{ window.dispatchEvent(new Event("resize")); }catch(e){}
}

function toggleSidebar(){ setSidebarMini(!navMiniOn()); }

/* Restore the remembered state. Called from the shell once the workspace is on
   screen -- doing it at parse time would run before #workspace exists. */
function initSidebarMini(){
  let want = false;
  try{ want = localStorage.getItem(NAVMINI_KEY) === "1"; }catch(e){}
  setSidebarMini(want, false);
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
