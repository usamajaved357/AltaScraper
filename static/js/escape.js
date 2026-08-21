/* static/js/escape.js -- Escape closes whatever is open, everywhere.
 *
 * FOUND BY USING THE APP RATHER THAN READING IT. Clicking a product row opens
 * the listing drawer -- the biggest overlay in this app -- and Escape did
 * nothing. The only ways out were the ✕ or a click on the scrim behind it. A
 * browser automating the screen sat there pressing Escape while the scrim
 * quietly swallowed every click aimed at the page underneath, which is exactly
 * what a person does with the mouse before working out that the key does not
 * work here.
 *
 * It works everywhere else: the palette, the image library, the price editor,
 * the guide, the mobile menu, the account switcher and every inline cell editor
 * all listen for it. Eight overlays honoured the key and the two biggest did
 * not, so the rule a person learns in the first minute -- "Escape gets me out"
 * -- was true except when it mattered most.
 *
 * ONE HANDLER, TOPMOST FIRST. Overlays stack: a modal can open over the drawer.
 * Closing the bottom one while the top is still up would leave the top with
 * nothing behind it, so this closes the topmost thing it can find and stops.
 * z-index decides what "topmost" means, read off the element rather than
 * guessed, because several modals set their own.
 *
 * IT NEVER FIGHTS A HANDLER THAT ALREADY EXISTS. Anything that listens for
 * Escape itself calls preventDefault, and this checks defaultPrevented first --
 * so the palette still closes itself, an open cell editor still cancels its own
 * edit, and this only acts when nothing else did.
 *
 * AND NOT WHILE TYPING INTO A FORM. Escape in a text box means "undo what I am
 * typing" to the control that owns it. The inline editors rely on that.
 */

function _escOpenLayers(){
  const seen = [];
  const add = function(el, close){
    if(!el) return;
    const cs = getComputedStyle(el);
    if(cs.display === "none" || cs.visibility === "hidden") return;
    const r = el.getBoundingClientRect();
    if(r.width < 2 || r.height < 2) return;
    const z = parseInt(cs.zIndex, 10);
    seen.push({el: el, z: isFinite(z) ? z : 0, close: close});
  };
  // The listing drawer, by its own scrim -- the drawer itself is always in the
  // document and only carries a class, so the scrim is what says it is open.
  try{
    const scrim = document.getElementById("drawerscrim");
    if(scrim && scrim.classList.contains("open")
       && typeof closeDrawer === "function"){
      add(scrim, closeDrawer);
    }
  }catch(e){}
  // Every modal, however it was built: the markup ones and the ones created at
  // run time both end up as .modalwrap.open.
  try{
    document.querySelectorAll(".modalwrap.open").forEach(function(m){
      add(m, function(){
        m.classList.remove("open");
        // Created on the fly? Then removing the class leaves an invisible
        // element on top of the page forever.
        if(!m.id || m.parentNode === document.body){
          if(m.dataset && m.dataset.keep === "1") return;
          if(m.getAttribute("data-built") === "1" && m.remove) m.remove();
        }
      });
    });
  }catch(e){}
  seen.sort(function(a, b){ return b.z - a.z; });
  return seen;
}

document.addEventListener("keydown", function(ev){
  if(ev.key !== "Escape") return;
  // Something nearer the event already dealt with it.
  if(ev.defaultPrevented) return;
  const t = ev.target;
  const tag = t && t.tagName ? t.tagName.toUpperCase() : "";
  if(tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT"
     || (t && t.isContentEditable)) return;
  const layers = _escOpenLayers();
  if(!layers.length) return;
  ev.preventDefault();
  try{ layers[0].close(); }catch(e){}
});
