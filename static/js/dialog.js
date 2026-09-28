/* static/js/dialog.js — the app's own alert, confirm and prompt.
 *
 *     "No browser alert(), prompt(), or confirm() dialogs ANYWHERE in the app.
 *      Every interaction uses inline inputs, modals, or toast notifications."
 *
 * WHY THIS IS NOT COSMETIC. A native dialog is not just white; it is a
 * different thing from the app in ways that lose work:
 *
 *   * it blocks the whole page, so a background poll finishing mid-decision
 *     cannot repaint and the screen behind it goes stale
 *   * Chrome puts "This page says:" above it, so every message the app writes
 *     is prefixed with a warning the app did not write
 *   * a second one from a timer while the first is open is silently dropped,
 *     which is how a confirmation can simply never appear
 *   * prompt() gives one unlabelled line: no units, no current value shown as
 *     anything but pre-filled text, no way to say "£" or "days"
 *   * on a phone several browsers suppress them entirely
 *
 * THREE FUNCTIONS, ONE IMPLEMENTATION (CLAUDE.md Rule 12). Ninety-three call
 * sites across twenty-five files used the native three. They now call these,
 * which are the same shapes -- so a call site changes by adding `await` and
 * nothing else -- and every one of them is drawn by the code below.
 *
 * THEY ARE PROMISES, and that is the one real difference. The native versions
 * stop JavaScript dead until answered, which nothing in a browser can do
 * without freezing the page. So `if (!confirm(x)) return;` becomes
 * `if (!await uiConfirm(x)) return;` and the function it sits in becomes
 * async. A call site that forgets the await gets a Promise, which is truthy,
 * so a confirmation would always pass -- test_no_native_dialogs.py checks for
 * exactly that.
 */
"use strict";

let _DLG_OPEN = null;
let _DLG_SEQ = 0;           // unique ids for aria-labelledby

function _dlgEsc(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/* A native dialog's message is plain text with newlines. Almost every call
 * site was written that way, so the text is escaped and the blank lines become
 * paragraphs -- which is what those newlines were being used for. */
function _dlgBody(message) {
  const paras = String(message == null ? "" : message).split(/\n\s*\n/);
  return paras.map(function (p) {
    return '<p style="margin:0 0 9px;font-size:12.5px;line-height:1.6;'
      + 'white-space:pre-wrap">' + _dlgEsc(p.trim()) + "</p>";
  }).join("");
}

/* The shell every one of the three uses. `buttons` is drawn right-to-left in
 * the order given, and whichever is pressed resolves with its `value`. */
/* KEEP TAB INSIDE `container` -- the one focus trap (CLAUDE.md Rule 12): the
 * app's dialogs below and the product page overlay (pdp.js) both call this.
 * Only VISIBLE, enabled controls count, so a hidden tab panel is skipped.
 * Returns true when it moved focus. */
function uiTrapTab(e, container) {
  if (!container || e.key !== "Tab") return false;
  const f = Array.prototype.slice.call(container.querySelectorAll(
    'button,input,textarea,select,summary,a[href],[tabindex]:not([tabindex="-1"]),' +
    '[contenteditable]:not([contenteditable="false"])'))
    .filter(function (el) {
      return !el.disabled && (el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    });
  if (!f.length) { e.preventDefault(); return true; }
  const a = document.activeElement;
  const i = f.indexOf(a);
  // Focus INSIDE the container but not in the list (an editable area, a custom
  // widget): the browser's own Tab order is right there -- only the ends wrap
  // (D3 review: Tab out of the PDP's title editor jumped to "Back").
  if (i === -1 && container.contains(a) && a !== container) return false;
  if (e.shiftKey && (i <= 0)) { e.preventDefault(); f[f.length - 1].focus(); return true; }
  if (!e.shiftKey && (i === -1 || i === f.length - 1)) { e.preventDefault(); f[0].focus(); return true; }
  return false;
}

/* Is focus inside a layer drawn OVER the page (a modal, the chat, a menu, a
 * popover, the drawer)? The product page's trap stands aside for these, so
 * a layer opened on top of it keeps its own keyboard (D3 review). */
function uiFocusInLayer(except) {
  const a = document.activeElement;
  if (!a || a === document.body) return false;
  const layer = a.closest && a.closest(
    '.uidlg-wrap,.modalwrap,.chatwrap,.tilemenu,.uiinline,#drawer,.rev,[role="dialog"],[role="menu"]');
  return !!layer && layer !== except && !(except && except.contains(layer));
}

function _dlgOpen(o) {
  return new Promise(function (resolve) {
    // Only one at a time. A second one while the first is open would stack two
    // overlays and trap the page behind both -- which is the native behaviour
    // this replaces, and it was never the desirable half of it.
    if (_DLG_OPEN) { try { _DLG_OPEN.close(null); } catch (e) { /* gone */ } }

    // WHERE FOCUS WAS, to give it back (Milestone 12, audit section 14: the
    // dialog had no focus return, so a keyboard user was dropped at the top of
    // the page after every confirmation).
    const opener = document.activeElement;
    const tid = "uidlg_t" + (++_DLG_SEQ);
    const wrap = document.createElement("div");
    wrap.className = "uidlg-wrap";
    wrap.innerHTML =
      '<div class="uidlg" role="dialog" aria-modal="true"'
      + (o.title ? ' aria-labelledby="' + tid + '"' : ' aria-label="Message"') + '>'
      + (o.title ? '<div class="uidlg-h" id="' + tid + '">' + _dlgEsc(o.title) + "</div>" : "")
      + '<div class="uidlg-b">' + (o.html || _dlgBody(o.message)) + "</div>"
      + '<div class="uidlg-f">'
      + (o.buttons || []).map(function (b, i) {
          return '<button type="button" data-i="' + i + '" class="db-chip'
            + (b.tone === "go" ? " go" : b.tone === "risk" ? " risk" : "")
            + '">' + _dlgEsc(b.label) + "</button>";
        }).join("")
      + "</div></div>";
    document.body.appendChild(wrap);

    let done = false;
    const close = function (value) {
      if (done) return;
      done = true;
      _DLG_OPEN = null;
      document.removeEventListener("keydown", onKey, true);
      wrap.remove();
      if (opener && opener.focus && document.contains(opener)) {
        try { opener.focus(); } catch (e) { /* gone */ }
      }
      resolve(value);
    };
    const onKey = function (e) {
      if (e.key === "Escape") { e.preventDefault(); close(o.cancelValue); }
      // TAB STAYS INSIDE. aria-modal says the page behind is inert; without
      // this, Tab walked straight out into it (audit section 14: no focus trap).
      else if (e.key === "Tab") { uiTrapTab(e, wrap); }
      // Enter accepts, but NEVER from inside a textarea, where it is a newline.
      else if (e.key === "Enter" && e.target.tagName !== "TEXTAREA") {
        const ok = (o.buttons || []).filter(function (b) { return b.primary; })[0];
        if (ok) { e.preventDefault(); accept(ok); }
      }
    };
    const accept = function (b) {
      // A button may read the inputs and refuse -- returning undefined means
      // "not valid, stay open", which is how a prompt rejects a bad number
      // without throwing the typed value away.
      const v = b.value === undefined ? undefined : b.value;
      if (typeof b.take === "function") {
        const got = b.take(wrap);
        if (got === undefined) return;
        close(got);
        return;
      }
      close(v);
    };

    wrap.querySelectorAll(".uidlg-f button").forEach(function (el) {
      el.onclick = function () { accept(o.buttons[+el.dataset.i]); };
    });
    // Clicking the dark surround cancels, like tapping outside a sheet.
    wrap.onclick = function (e) { if (e.target === wrap) close(o.cancelValue); };
    document.addEventListener("keydown", onKey, true);
    _DLG_OPEN = { close: close };

    const first = wrap.querySelector("input,textarea,select")
               || wrap.querySelector(".uidlg-f button:last-child");
    if (first) { try { first.focus(); first.select && first.select(); } catch (e) { /* ok */ } }
  });
}

/* Say something. Resolves when it is dismissed. */
function uiAlert(message, opts) {
  const o = opts || {};
  return _dlgOpen({
    title: o.title || "",
    message: message,
    cancelValue: undefined,
    buttons: [{ label: o.ok || "OK", tone: "go", primary: true, value: undefined }]
  });
}

/* Ask yes or no. Resolves true or false — never a Promise-shaped truthy thing
 * by accident, because the caller must await it to get a boolean at all. */
function uiConfirm(message, opts) {
  const o = opts || {};
  return _dlgOpen({
    title: o.title || "",
    message: message,
    cancelValue: false,
    buttons: [
      { label: o.cancel || "Cancel", value: false },
      { label: o.ok || "Yes", tone: o.danger ? "risk" : "go", primary: true,
        value: true }
    ]
  });
}

/* Ask for a value. Resolves the string, or null if cancelled — the same
 * contract prompt() had, so `if (v === null) return;` still reads correctly.
 *
 * It can do what prompt() could not: label the box, put a unit beside it, and
 * show a hint under it. Those are `opts.label`, `opts.prefix`, `opts.hint`.
 */
function uiPrompt(message, value, opts) {
  const o = opts || {};
  const id = "uidlg_in";
  const box = o.multiline
    ? '<textarea id="' + id + '" rows="' + (o.rows || 5) + '" '
      + 'style="width:100%">' + _dlgEsc(value == null ? "" : value) + "</textarea>"
    : '<div style="display:flex;align-items:center;gap:6px">'
      + (o.prefix ? '<span class="cc" style="font-size:13px">'
                    + _dlgEsc(o.prefix) + "</span>" : "")
      + '<input id="' + id + '" type="' + (o.type || "text") + '" '
      + (o.min != null ? 'min="' + o.min + '" ' : "")
      + (o.max != null ? 'max="' + o.max + '" ' : "")
      + (o.step ? 'step="' + o.step + '" ' : "")
      + (o.placeholder ? 'placeholder="' + _dlgEsc(o.placeholder) + '" ' : "")
      + 'value="' + _dlgEsc(value == null ? "" : value) + '" '
      + 'style="flex:1;min-width:0">'
      + (o.suffix ? '<span class="cc" style="font-size:12px">'
                    + _dlgEsc(o.suffix) + "</span>" : "")
      + "</div>";
  return _dlgOpen({
    title: o.title || "",
    cancelValue: null,
    html: _dlgBody(message)
      + (o.label ? '<label class="cc" style="font-size:11.5px;display:block;'
                   + 'margin:10px 0 4px" for="' + id + '">'
                   + _dlgEsc(o.label) + "</label>" : '<div style="height:8px"></div>')
      + box
      + (o.hint ? '<div class="cc" style="font-size:11px;margin-top:6px;'
                  + 'line-height:1.5">' + _dlgEsc(o.hint) + "</div>" : ""),
    buttons: [
      { label: o.cancel || "Cancel", value: null },
      { label: o.ok || "Save", tone: "go", primary: true,
        take: function (wrap) {
          const el = wrap.querySelector("#" + id);
          return el ? el.value : null;
        } }
    ]
  });
}

/* ======================================================================
 * AN INPUT WHERE THE BUTTON IS.
 *
 *     "Replace with an inline input that appears right where the button is"
 *
 * A modal is right when the decision needs the page's whole attention. Setting
 * one number on one row does not: the row you are setting it FOR is the
 * context, and covering it with an overlay takes that context away at the
 * moment you need it.
 *
 * So this opens a small panel anchored to the button, keeps the row visible
 * behind it, and saves without redrawing anything but the row.
 *
 * `onSave(value)` may return a string to show as an error and stay open, or
 * anything else to close. It is awaited, so it can be the fetch itself.
 * ====================================================================== */
function uiInline(anchor, o) {
  const opts = o || {};
  document.querySelectorAll(".uiinline").forEach(function (n) { n.remove(); });
  if (!anchor) return Promise.resolve(null);

  const pop = document.createElement("div");
  pop.className = "uiinline";
  pop.innerHTML =
    (opts.title ? '<div class="uiinline-h">' + _dlgEsc(opts.title) + "</div>" : "")
    + '<div style="display:flex;align-items:center;gap:6px">'
    + (opts.prefix ? '<span class="cc" style="font-size:12.5px">'
                     + _dlgEsc(opts.prefix) + "</span>" : "")
    + '<input class="uiinline-in" type="' + (opts.type || "text") + '" '
    + (opts.min != null ? 'min="' + opts.min + '" ' : "")
    + (opts.max != null ? 'max="' + opts.max + '" ' : "")
    + (opts.step ? 'step="' + opts.step + '" ' : "")
    + (opts.placeholder ? 'placeholder="' + _dlgEsc(opts.placeholder) + '" ' : "")
    + 'value="' + _dlgEsc(opts.value == null ? "" : opts.value) + '">'
    + (opts.suffix ? '<span class="cc" style="font-size:12px">'
                     + _dlgEsc(opts.suffix) + "</span>" : "")
    + '<button type="button" class="db-chip go uiinline-ok">'
    + _dlgEsc(opts.ok || "Save") + "</button>"
    + "</div>"
    + (opts.hint ? '<div class="uiinline-hint">' + _dlgEsc(opts.hint) + "</div>" : "")
    + '<div class="uiinline-err" style="display:none"></div>'
    // CLEARING IS A DIFFERENT ACT FROM SAVING NOTHING, and it needs its own
    // button. An empty box saved is ambiguous -- it could be a slip -- so the
    // way to turn a setting off says so.
    + (opts.clearable
        ? '<button type="button" class="uiinline-clear">'
          + _dlgEsc(opts.clearLabel || "Turn this off") + "</button>"
        : "");
  document.body.appendChild(pop);

  // Anchored under the button, nudged left if it would run off the edge.
  const r = anchor.getBoundingClientRect();
  const w = pop.offsetWidth || 260;
  let left = r.left + window.scrollX;
  if (left + w > window.innerWidth - 10) left = window.innerWidth - w - 10;
  pop.style.left = Math.max(8, left) + "px";
  pop.style.top = (r.bottom + window.scrollY + 5) + "px";

  const input = pop.querySelector(".uiinline-in");
  const err = pop.querySelector(".uiinline-err");
  input.focus();
  input.select();

  return new Promise(function (resolve) {
    let done = false;
    const close = function (v) {
      if (done) return;
      done = true;
      document.removeEventListener("click", away, true);
      document.removeEventListener("keydown", onKey, true);
      pop.remove();
      resolve(v);
    };
    const save = async function (raw) {
      err.style.display = "none";
      if (typeof opts.onSave === "function") {
        const msg = await opts.onSave(raw);
        if (typeof msg === "string" && msg) {
          err.textContent = msg;
          err.style.display = "block";
          input.focus();
          return;
        }
      }
      close(raw);
    };
    pop.querySelector(".uiinline-ok").onclick = function () { save(input.value); };
    const clr = pop.querySelector(".uiinline-clear");
    if (clr) clr.onclick = function () { save(""); };
    const onKey = function (e) {
      if (e.key === "Escape") { e.preventDefault(); close(null); }
      else if (e.key === "Enter") { e.preventDefault(); save(input.value); }
    };
    // Clicking anywhere else closes WITHOUT saving. Registered on the next
    // tick so the click that opened it does not immediately close it.
    const away = function (e) { if (!pop.contains(e.target)) close(null); };
    document.addEventListener("keydown", onKey, true);
    setTimeout(function () {
      document.addEventListener("click", away, true);
    }, 0);
  });
}

/* THE OLDER MODALS (.modalwrap: accounts, sync, users, AI settings, the PPC
 * builders, and a few made on the fly) had no dialog role, no focus trap and no
 * focus return (design system, accessibility; UI inventory 28 Sep 2026). Rather
 * than edit every opener, one watcher here: when a .modalwrap becomes open it is
 * named a modal dialog and focus moves inside; while open, Tab stays inside
 * (uiTrapTab, the same trap as above); when it closes or is removed, focus goes
 * back to what had it. Batched to one check per animation frame. */
(function () {
  if (typeof document === "undefined" || typeof MutationObserver === "undefined") return;
  function isOpen(m) {
    // ACTUALLY ON SCREEN: a modal left .open inside a screen that was hidden
    // keeps display:flex itself, and trapping Tab in it blocked the whole app
    // (D3 review).
    return m.classList.contains("open") && getComputedStyle(m).display !== "none"
      && m.getClientRects().length > 0;
  }
  function opened(m) {
    if (m._a11yOpen) return;
    m._a11yOpen = { opener: document.activeElement };
    const panel = m.querySelector(".modal") || m;
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    if (!panel.getAttribute("aria-label") && !panel.getAttribute("aria-labelledby")) {
      const h = panel.querySelector("h1,h2,h3,h4,.modalh");
      panel.setAttribute("aria-label", (h && h.textContent.trim().slice(0, 80)) || "Dialog");
    }
    setTimeout(function () {
      if (m.contains(document.activeElement)) return;
      const f = m.querySelector('input:not([type=hidden]),select,textarea,button,a[href],[tabindex]:not([tabindex="-1"])');
      if (f) { try { f.focus({ preventScroll: true }); } catch (e) { /* ok */ } }
    }, 0);
  }
  function closed(m) {
    const st = m._a11yOpen;
    m._a11yOpen = null;
    if (st && st.opener && st.opener.focus && document.contains(st.opener)) {
      try { st.opener.focus({ preventScroll: true }); } catch (e) { /* gone */ }
    }
  }
  let queued = false;
  function scan() {
    queued = false;
    document.querySelectorAll(".modalwrap").forEach(function (m) {
      if (isOpen(m)) opened(m); else if (m._a11yOpen) closed(m);
    });
  }
  const obs = new MutationObserver(function (records) {
    for (let i = 0; i < records.length; i++) {
      const r = records[i];
      // A modal REMOVED while open (the ones built on the fly) gives focus back.
      for (let j = 0; j < r.removedNodes.length; j++) {
        const n = r.removedNodes[j];
        if (n && n._a11yOpen) closed(n);
      }
    }
    if (!queued) { queued = true; requestAnimationFrame(scan); }
  });
  function start() {
    obs.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["class", "style"] });
    scan();
  }
  if (document.body) start(); else document.addEventListener("DOMContentLoaded", start);
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Tab" || e.defaultPrevented || document.querySelector(".uidlg-wrap")) return;
    const open = Array.prototype.filter.call(document.querySelectorAll(".modalwrap"), isOpen);
    if (!open.length) return;
    // The TOPMOST by stacking order, as escape.js decides it -- not the last
    // in the page.
    open.sort(function (x, y) {
      return (parseInt(getComputedStyle(y).zIndex, 10) || 0) - (parseInt(getComputedStyle(x).zIndex, 10) || 0);
    });
    uiTrapTab(e, open[0]);
  });
})();
