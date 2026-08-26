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
function _dlgOpen(o) {
  return new Promise(function (resolve) {
    // Only one at a time. A second one while the first is open would stack two
    // overlays and trap the page behind both -- which is the native behaviour
    // this replaces, and it was never the desirable half of it.
    if (_DLG_OPEN) { try { _DLG_OPEN.close(null); } catch (e) { /* gone */ } }

    const wrap = document.createElement("div");
    wrap.className = "uidlg-wrap";
    wrap.innerHTML =
      '<div class="uidlg" role="dialog" aria-modal="true">'
      + (o.title ? '<div class="uidlg-h">' + _dlgEsc(o.title) + "</div>" : "")
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
      resolve(value);
    };
    const onKey = function (e) {
      if (e.key === "Escape") { e.preventDefault(); close(o.cancelValue); }
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
