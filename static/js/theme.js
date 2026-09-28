// static/js/theme.js -- dark or light, remembered per browser.
//
// Loaded in <head>, BEFORE the page paints, so a saved choice never flashes the
// other theme first. The tokens (static/css/foundations.css) switch on
// <html data-theme="dark|light">; dark is the default (design package, Direction A).
//
// The toggle itself lives in the top bar (shell). Until every screen has had its
// light-theme pass, `altaThemeLightReady` stays false and the stored choice is
// only honoured when it is "dark" -- a half-finished light theme is worse than none.
(function () {
  var KEY = "alta_theme";
  var LIGHT_READY = false;          // flipped when the light-theme QA pass is done
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
})();
