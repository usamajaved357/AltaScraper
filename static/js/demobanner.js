/* Sample data, said out loud. ONE implementation, used by every screen.
 *
 *   "when no data is available i want to use the placeholder data which is not
 *    real but the user has an idea how the app looks like when it has data"
 *
 * THE RULE THIS FILE EXISTS TO ENFORCE:
 *
 *     a placeholder must never be mistakable for a real figure.
 *
 * A number nobody can tell is invented is worse than an empty screen, because
 * an empty screen is at least true. So a screen showing samples gets a bar
 * across the top saying so in its first four words, and the figures underneath
 * are dimmed and italic. Both come from here rather than being written per
 * screen -- the Returns page had its own copy of this idea, and one copy is how
 * it stays honest when the sixth screen is added by somebody in a hurry.
 *
 * The server decides WHO sees samples (domain/demo_data.py). This file only
 * decides how they look, and it is driven entirely by the `demo` flag on the
 * response -- so a screen cannot accidentally mark real data as a sample, nor
 * fail to mark a sample.
 */

/* Is this server answer a sample? */
function isDemo(j){ return !!(j && j.demo); }

/* The bar. Put it above everything else on the screen. */
function demoBanner(j){
  if(!isDemo(j)) return "";
  const why = (j.demo_reason || "").toString();
  const esc = (typeof _rEsc === "function") ? _rEsc
            : (typeof esc2 === "function") ? esc2
            : function(s){ return String(s == null ? "" : s)
                .replace(/&/g,"&amp;").replace(/</g,"&lt;")
                .replace(/>/g,"&gt;").replace(/"/g,"&quot;"); };
  return '<div class="demobar">'
    + '<i class="ti ti-flask"></i>'
    + '<div><b>These are sample figures, not your data.</b> '
    + (why ? esc(why) + ' ' : '')
    + 'Everything below is invented so you can see what the screen looks like '
    + 'with a business in it. Nothing here is stored, nothing is counted, and '
    + 'it all disappears the moment a real Amazon account is connected.</div>'
    + '</div>';
}

/* Wrap a block of rendered figures so they read as samples at a glance. */
function demoWrap(j, html){
  return isDemo(j) ? '<div class="demo-dim">' + html + '</div>' : html;
}

/* Mark the <div> a screen renders into, so anything drawn later by that screen
   inherits the dimming without every call site remembering to wrap. */
function demoMark(el, j){
  if(!el) return;
  try{ el.classList.toggle("demo-dim", isDemo(j)); }catch(e){}
}
