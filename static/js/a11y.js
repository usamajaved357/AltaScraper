// static/js/a11y.js -- a clickable thing that is not a <button> still works
// from the keyboard.
//
// WHY. The master audit (28 Sep 2026, section 14) counted ~102 clickable
// div/span/tr elements with onclick and no role or tab stop -- including the
// account and marketplace switchers in the sidebar, which a keyboard user could
// therefore never reach. A native <button> gets Enter and Space for free; a div
// gets nothing.
//
// THE RULE. Mark the element role="button" tabindex="0" in the markup (so it is
// announced as a button and can be tabbed to); this one listener then turns
// Enter and Space on it into a click. One handler for all of them, rather than
// an onkeydown written out on each (CLAUDE.md Rule 12). Milestone 12.
(function () {
  if (typeof document === "undefined" || !document.addEventListener) return;
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" && e.key !== " " && e.key !== "Spacebar") return;
    const el = e.target;
    if (!el || !el.getAttribute) return;
    if (el.getAttribute("role") !== "button") return;
    const tag = (el.tagName || "").toUpperCase();
    // Real controls already do this themselves; doing it twice would click twice.
    // An <a> only does it itself when it HAS an href; a role="button" link
    // without one ("Back to listings") did nothing on Enter (D3 review).
    if (tag === "BUTTON" || (tag === "A" && el.hasAttribute("href")) || tag === "INPUT"
        || tag === "TEXTAREA" || tag === "SELECT") return;
    e.preventDefault();          // Space would otherwise scroll the page
    el.click();
  });
})();
