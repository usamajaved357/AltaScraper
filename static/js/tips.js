/* static/js/tips.js -- make the ⓘ marks actually say their statement.
 *
 *     "see there are I circular marks everywhere in the app including the ppc
 *      analytics page, they should show some statements"
 *
 * THEY ALREADY CARRIED THE STATEMENT. Every one of these marks is rendered with
 * a title="..." holding two or three sentences explaining how a figure is
 * worked out -- what the fee rate is measured from, why a profit is blank, what
 * an opportunity score is made of. The problem was never missing text; it was
 * that title="" is the browser's native tooltip:
 *
 *   * it waits about a second before it appears, so an ordinary hover shows
 *     nothing and the mark reads as decoration;
 *   * it draws in the operating system's style, which on a dark panel is a pale
 *     little box that plainly is not part of the page;
 *   * it flattens newlines and truncates long text on some platforms, and these
 *     statements are long on purpose.
 *
 * So the text is MOVED to a data-tip attribute, which dashboard.css draws as a
 * proper bubble. Moved rather than copied: leaving the title in place shows the
 * native tooltip on top of the styled one, which is worse than either alone.
 *
 * WHY A PASS OVER THE DOM RATHER THAN CHANGING EVERY CALL SITE.
 * There are dozens of these marks across listings, sales, orders, the PPC
 * screens and the P&L, rendered by a dozen different files. Rewriting each one
 * is how half of them end up subtly different, and any new one added later
 * would go back to the native tooltip without anyone noticing. One pass over
 * the marks means a mark written the ordinary way is right by default.
 *
 * SCOPED TO THE HELP MARKS, NOT EVERY title IN THE APP. Plenty of elements have
 * a legitimate native tooltip -- a truncated product name, a table cell, a
 * disabled button explaining itself -- and hijacking all of them would be a
 * large behavioural change nobody asked for. Three classes, listed below, are
 * the ones that exist to explain a figure.
 */

/* The marks that exist to carry an explanation. `.infodot` is the app-wide one,
   `.ppc-i` the ⓘ on the PPC screens, `.ppc-q` the ? on their summary cells. */
const ALTA_TIP_SEL = ".infodot[title], .ppc-i[title], .ppc-q[title],"
                   + " [data-tip-src][title]";

function altaTips(root){
  let host;
  try{
    host = (root && root.querySelectorAll) ? root : document;
  }catch(e){ return; }
  let marks;
  try{ marks = host.querySelectorAll(ALTA_TIP_SEL); }
  catch(e){ return; }

  for(let i = 0; i < marks.length; i++){
    const el = marks[i];
    const txt = el.getAttribute("title");
    if(!txt) continue;
    el.setAttribute("data-tip", txt);
    // REMOVED, not kept. Both attributes present means both tooltips appear,
    // the native one on a delay, on top of the styled one.
    el.removeAttribute("title");
    // Reachable by keyboard, so the statement is not mouse-only. These are
    // spans, which take no focus without this.
    if(!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "0");
    if(!el.hasAttribute("role")) el.setAttribute("role", "note");
    altaTipEdge(el);
  }
}

/* KEEP THE BUBBLE ON SCREEN. It is centred on the mark by default, so a mark in
 * the first or last column of a wide table would hang half of its statement off
 * the side -- and a tooltip you have to scroll sideways to read is worse than
 * the native one it replaced. Measured against the viewport at the moment the
 * mark is laid out; re-measured on resize by altaTipsWatch below. */
function altaTipEdge(el){
  try{
    const r = el.getBoundingClientRect();
    const w = window.innerWidth || document.documentElement.clientWidth || 0;
    el.classList.remove("tip-l", "tip-r");
    // Half the widest the bubble is allowed to be, plus a little air.
    const half = 180;
    if(r.left < half) el.classList.add("tip-l");
    else if(w - r.right < half) el.classList.add("tip-r");
  }catch(e){}
}

/* Re-run after a redraw. Every screen in this app rebuilds its panels with
 * innerHTML, which throws away the data-tip attributes along with the elements,
 * so this has to happen again after each render rather than once at startup.
 *
 * A MutationObserver rather than a call in every renderer, for the same reason
 * the pass exists at all: a screen added later gets it without remembering to.
 * Debounced, because innerHTML on a big table fires a great many mutations and
 * running the pass on each one would be the slowest thing on the page. */
let _ALTA_TIP_T = null;
function altaTipsWatch(){
  try{
    altaTips(document);
    if(typeof MutationObserver !== "function") return;
    const obs = new MutationObserver(function(){
      if(_ALTA_TIP_T) clearTimeout(_ALTA_TIP_T);
      _ALTA_TIP_T = setTimeout(function(){ altaTips(document); }, 60);
    });
    obs.observe(document.body, {childList: true, subtree: true});
    window.addEventListener("resize", function(){
      const m = document.querySelectorAll("[data-tip]");
      for(let i = 0; i < m.length; i++) altaTipEdge(m[i]);
    });
  }catch(e){}
}

if(typeof document !== "undefined"){
  if(document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", altaTipsWatch);
  }else{
    altaTipsWatch();
  }
}
