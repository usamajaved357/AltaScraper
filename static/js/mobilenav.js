// ============ THE MENU ON A PHONE ============
//
// "i want you to match the mobile version of the orbit view as mine, see how
//  the side bar appear and everything else."
//
// Orbit at 390px wide parks its 284px sidebar at x:-300 and opens it with one
// 40x40 button labelled "Open menu". That is a drawer, and this file is the
// twelve lines of behaviour a drawer needs. The looks are entirely in
// static/css/mobile.css -- nothing here sets a style, it only adds and removes
// one class on <body>, so there is exactly one place to change how it moves.
//
// This is deliberately NOT part of sidebar.js. That file owns the DESKTOP
// fold-to-a-rail, which is a different control answering a different question
// ("give me back 156px of a wide screen" versus "get out of the way of my
// whole screen"). They share the same element and nothing else, and putting
// both in one file is how one ends up quietly undoing the other.

const MNAV_BREAKPOINT = 860;   // must match the @media in mobile.css

function mnavIsPhone(){
  return window.matchMedia("(max-width: " + MNAV_BREAKPOINT + "px)").matches;
}

function mnavIsOpen(){
  return document.body.classList.contains("navopen");
}

function mnavSet(open){
  document.body.classList.toggle("navopen", !!open);
  const b = document.getElementById("navburger");
  if(b){
    b.setAttribute("aria-expanded", open ? "true" : "false");
    b.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    b.title = open ? "Close the menu" : "Open the menu";
    // The icon has to change or the button reads as "open" while the menu is
    // already open, which is the single most common fault in a drawer.
    b.innerHTML = '<i class="ti ti-' + (open ? "x" : "menu-2") + '"></i>';
  }
  const s = document.querySelector(".navscrim");
  if(s) s.setAttribute("aria-hidden", open ? "false" : "true");
}

function mnavOpen(){  mnavSet(true);  }
function mnavClose(){ mnavSet(false); }
function mnavToggle(){ mnavSet(!mnavIsOpen()); }

document.addEventListener("DOMContentLoaded", function(){
  mnavSet(false);   // writes the label and the icon, so the markup carries neither

  const scrim = document.querySelector(".navscrim");
  if(scrim) scrim.addEventListener("click", mnavClose);

  // Choosing a destination closes the menu. On a desktop the menu stays put
  // because there is room for it; on a phone it is covering the thing you just
  // asked to see, and leaving it there means every single navigation costs a
  // second tap somewhere else.
  //
  // Delegated from the sidebar rather than bound per item: the nav gains rows
  // (Repricer, ASIN Monitor, Import seller) and per-item binding would silently
  // miss whichever was added last.
  const side = document.querySelector("#workspace .sidebar");
  if(side){
    side.addEventListener("click", function(ev){
      if(!mnavIsPhone() || !mnavIsOpen()) return;
      const t = ev.target;
      if(!t || !t.closest) return;
      // Only things that GO somewhere. The account switcher and the
      // marketplace picker open their own menus inside the sidebar, and
      // closing the drawer under them would shut the menu you just opened.
      if(t.closest(".navitem, .backlink")) mnavClose();
    });
  }

  // Escape closes it, like every other overlay in the app.
  document.addEventListener("keydown", function(ev){
    if(ev.key === "Escape" && mnavIsOpen()) mnavClose();
  });

  // Rotating to landscape, or a tablet growing past the breakpoint, leaves
  // body.navopen set -- which on a desktop layout means `overflow:hidden` on
  // the body and a page that cannot scroll, with nothing on screen to explain
  // why. Drop the state the moment the drawer stops existing.
  try{
    window.matchMedia("(max-width: " + MNAV_BREAKPOINT + "px)")
          .addEventListener("change", function(e){ if(!e.matches) mnavClose(); });
  }catch(e){
    // Older Safari has addListener and not addEventListener.
    try{
      window.matchMedia("(max-width: " + MNAV_BREAKPOINT + "px)")
            .addListener(function(e){ if(!e.matches) mnavClose(); });
    }catch(e2){}
  }
});
