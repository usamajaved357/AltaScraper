// static/js/core_util.js -- the helpers every screen uses: text escaping, the
// toast, and the status badge words. Moved word for word out of listings.js
// (Milestone 4, 28 Sep 2026), where they had grown up although nothing about
// them is about listings. Loaded immediately before listings.js, so everything
// that could call them before still can.

function esc(s){return (s==null?"":String(s)).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}

/* A stored cell that reads exactly "None" is a Python None that was written
   out as four characters, not something anyone typed. There are 361 of them in
   this database -- 193 in compliance notes, 168 in the VOC source -- and every
   one of them gets shown, concatenated, or searched as though it meant
   something. It is what made the IP panel say "forbidden phrase — compatible
   with None".
   ONLY when it is the whole value: a note that genuinely reads "None — operates
   at 240 V AC mains" is a real sentence and must survive. */
function _noneless(v){
  const s = String(v == null ? "" : v).trim();
  return /^(none|null|nan|undefined)$/i.test(s) ? "" : String(v == null ? "" : v);
}

/* ONE LINE AT THE FOOT OF THE SCREEN, for 640 call sites. What changed
 * (master audit, UX #7 -- "errors travel through one weak toast"):
 *   - a failure is styled as one, and stays up long enough to read;
 *   - a long message gets time in proportion to its length (1.8 s was the same
 *     for "Saved" and for a two-sentence refusal from Amazon);
 *   - the element is a live region (templates/dashboard.html), so it is read
 *     out, not only shown. */
// Guessed from the wording for the 640 existing call sites; a caller that
// KNOWS it is reporting a failure says so: toast(msg, {err: true}).
// (UI review, Milestone 6: "Stopped tracking B0..." and "... 0 failed" are
// successes; "That is not a cost." is a failure.)
const _TOAST_ERR = /^(could not|couldn.t|can.t|cannot|failed|error|refused|not saved|nothing (was )?saved|that\b.*\b(is not|isn.t))/i;
function toast(m, opts){
  const t = document.getElementById("toast");
  if(!t) return;
  const s = String(m == null ? "" : m);
  const isErr = (opts && typeof opts.err === "boolean") ? opts.err
    : (_TOAST_ERR.test(s.trim())
       || (/\b(failed|refused|error:)/i.test(s) && !/\b0 failed\b/i.test(s)));
  t.textContent = s;
  t.classList.toggle("err", isErr);
  // A failure interrupts; anything else waits its turn.
  t.setAttribute("aria-live", isErr ? "assertive" : "polite");
  t.classList.add("show");
  const ms = Math.min(9000, Math.max(isErr ? 4500 : 1800, 1200 + s.length * 45));
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove("show"), ms);
}

function badgeClass(s){return ["APPROVED","NEEDS_REVIEW","IP_HOLD","COMPLIANCE_HOLD","ERROR","API_READY","API_ERROR","LIVE","PARENT"].includes(s)?("b-"+s):"b-none";}

/* TWO DIFFERENT THINGS STOP A LISTING, and they are not fixed the same way.
 *
 *   BLOCKED  -- this app's own IP or compliance check stopped it BEFORE
 *               anything was sent. Nothing has reached Amazon. You fix it by
 *               changing a rule or the listing, then re-scanning.
 *   REFUSED  -- it WAS sent and Amazon rejected it. Amazon has said something
 *               specific about it, and that message is what you act on.
 *
 * The screen already tells them apart in words ("held by a compliance or IP
 * check" vs "listings Amazon refused") and then sent BOTH counts to the same
 * filter, which is isHold -- the union. So clicking "3 listings Amazon
 * refused" showed those 3 plus all 25 compliance holds: a number you click
 * that does not show you that number, which is the same complaint that got the
 * live tiles fixed ("clicking only 1 button draws a border on all 3").
 *
 * isHold stays as the union, because the "Blocked or errored" tile genuinely
 * wants both and several callers rely on it. The two halves are now nameable
 * separately, from one definition each (rule 12). */
function isRefusedByAmazon(s){ return s==="ERROR"||s==="API_ERROR"; }
function isBlockedByOurChecks(s){ return s==="IP_HOLD"||s==="COMPLIANCE_HOLD"; }
function isHold(s){ return isBlockedByOurChecks(s) || isRefusedByAmazon(s); }
