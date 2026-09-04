/* diag.js -- the app tells you when its deployment is wrong.
 *
 * Until now a broken deployment was silent: listings looked empty, sessions
 * dropped, and the only way to find out why was to open the hosting dashboard
 * and read logs. This asks /diag once on load and, if anything is actually
 * wrong, puts a bar at the top of the page saying so in plain English.
 *
 * It stays quiet when everything is fine. A warning that is always on screen
 * stops being read.
 */
(function () {
  var LAST = null;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function bar() {
    var el = document.getElementById("diag_bar");
    if (el) return el;
    el = document.createElement("div");
    el.id = "diag_bar";
    el.style.cssText =
      "position:sticky;top:0;z-index:900;display:none;padding:10px 14px;" +
      "background:var(--red-bg);border-bottom:1px solid var(--red-line);color:var(--red);" +
      "font-size:12.5px;line-height:1.5";
    document.body.insertBefore(el, document.body.firstChild);
    return el;
  }

  function show(d) {
    var bad = (d.checks || []).filter(function (c) { return !c.ok; });
    var errs = ((d.recent || {}).errors) || [];
    if (!bad.length && !errs.length) { bar().style.display = "none"; return; }

    var h = "";
    if (bad.length) {
      h += '<b>This deployment has ' + bad.length +
           ' configuration problem' + (bad.length > 1 ? "s" : "") + ':</b><ul style="margin:6px 0 0 18px">';
      bad.forEach(function (c) {
        h += "<li><b>" + esc(c.name) + "</b> — " + esc(c.detail) +
             (c.why ? '<br><span style="opacity:.8">' + esc(c.why) + "</span>" : "") + "</li>";
      });
      h += "</ul>";
    }
    if (errs.length) {
      h += (bad.length ? '<div style="margin-top:8px">' : "<div>") +
           "<b>" + errs.length + " server error" + (errs.length > 1 ? "s" : "") +
           " since the last restart.</b> Most recent: " +
           esc(errs[0].method + " " + errs[0].path) + " — " +
           esc(errs[0].kind + ": " + errs[0].message) + "</div>";
    }
    h += '<div style="margin-top:8px">' +
         '<button id="diag_copy" style="font-size:11px;padding:4px 10px;cursor:pointer">' +
         "Copy full diagnostics</button> " +
         '<a href="/diag" target="_blank" style="font-size:11px;color:var(--red);margin-left:8px">Open /diag</a> ' +
         '<button id="diag_hide" style="font-size:11px;padding:4px 10px;margin-left:8px;cursor:pointer">' +
         "Hide until next visit</button></div>";

    var el = bar();
    el.innerHTML = h;
    el.style.display = "block";

    var cp = document.getElementById("diag_copy");
    if (cp) cp.onclick = copyAll;
    var hd = document.getElementById("diag_hide");
    if (hd) hd.onclick = function () {
      el.style.display = "none";
      try { sessionStorage.setItem("diag_hidden", "1"); } catch (e) {}
    };
  }

  /* One block of text with the configuration, the background-sync state and the
   * recent errors, already stripped of anything credential-shaped by the server.
   * Built server-side so what gets pasted is what the server actually saw. */
  function copyAll() {
    var txt = (LAST && LAST.text) || "no diagnostics loaded";
    var ta = document.createElement("textarea");
    ta.value = txt;
    ta.style.cssText = "position:fixed;left:-9999px;top:0";
    document.body.appendChild(ta);
    ta.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(ta);
    if (typeof toast === "function") {
      toast(ok ? "Diagnostics copied — paste them into the chat"
               : "Could not copy; open /diag and copy from there");
    }
  }

  function load() {
    fetch("/diag", { headers: { Accept: "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (!j || !j.ok) return;          // not signed in, or not permitted
        LAST = j;
        var hidden = false;
        try { hidden = sessionStorage.getItem("diag_hidden") === "1"; } catch (e) {}
        if (!hidden) show(j);
      })
      .catch(function () { /* diagnostics must never break the page */ });
  }

  window.diagCopy = copyAll;         // so it can be triggered from the console
  window.diagReload = load;
  window.addEventListener("DOMContentLoaded", function () { setTimeout(load, 1200); });
})();
