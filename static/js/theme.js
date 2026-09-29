// static/js/theme.js -- dark or light, remembered per browser.
//
// Loaded in <head>, BEFORE the page paints, so a saved choice never flashes the
// other theme first. The tokens (static/css/foundations.css) switch on
// <html data-theme="dark|light">; dark is the default (design package, Direction A).
//
// The switch lives in the top bar (#themebtn). Light is offered since 29 Sep 2026,
// when every colour moved onto the shared tokens and palette.css (owner's decision).
// LIGHT_READY stays as the one switch that would withdraw it.
(function () {
  var KEY = "alta_theme";
  var LIGHT_READY = true;           // owner, 29 Sep 2026; light-theme pass: active/ui-direction-a-2026-09-29.md
  function read() {
    try { return localStorage.getItem(KEY) || ""; } catch (e) { return ""; }
  }
  function apply(t) {
    var theme = (t === "light" && LIGHT_READY) ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", theme);
    return theme;
  }
  apply(read());
  window.altaTheme = {
    get: function () { return document.documentElement.getAttribute("data-theme") || "dark"; },
    set: function (t) {
      try { localStorage.setItem(KEY, t === "light" ? "light" : "dark"); } catch (e) { /* private window */ }
      return apply(t);
    },
    toggle: function () { return this.set(this.get() === "light" ? "dark" : "light"); },
    lightReady: function () { return LIGHT_READY; },
  };

  // THE SWITCH IN THE TOP BAR (#themebtn). Its icon shows the theme you would
  // switch TO, like every sun/moon control. The chart series keep their locked
  // hues in both themes (foundations.css, data visualisation); the resize event
  // lets anything that sized itself redraw.
  function paint() {
    var b = document.getElementById("themebtn");
    if (!b) return;
    if (!LIGHT_READY) { b.style.display = "none"; return; }
    var light = window.altaTheme.get() === "light";
    b.innerHTML = '<i class="ti ti-' + (light ? "moon" : "sun") + '" aria-hidden="true"></i>';
    b.title = light ? "Switch to the dark theme" : "Switch to the light theme";
    // The label says what pressing it does; no aria-pressed as well, or a
    // screen reader hears "switch to dark, pressed" (ui review).
    b.setAttribute("aria-label", b.title);
  }
  window.altaThemeToggleBtn = function () {
    window.altaTheme.toggle();
    paint();
    try { window.dispatchEvent(new Event("resize")); } catch (e) { /* old browser */ }
  };
  document.addEventListener("DOMContentLoaded", paint);
})();
