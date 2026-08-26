"""No browser alert(), prompt() or confirm() anywhere in the app.

    "GENERAL RULE: No browser alert(), prompt(), or confirm() dialogs ANYWHERE
     in the app. Every interaction uses inline inputs, modals, or toast
     notifications."

WHY THIS IS NOT COSMETIC. A native dialog is not merely white; it is a
different thing from the app in ways that lose work:

  * it blocks the whole page, so a background poll finishing mid-decision
    cannot repaint and the screen behind it goes stale
  * Chrome prefixes it with "This page says:", so every message the app writes
    arrives with a warning the app did not write
  * a second one raised from a timer while the first is open is silently
    dropped -- which is how a confirmation can simply never appear
  * prompt() gives one unlabelled line: no units, no currency symbol, no hint
  * several mobile browsers suppress them outright

THE TRAP THIS TEST EXISTS FOR. uiConfirm returns a PROMISE. A Promise is
truthy, so a call site that forgets the await --

    if (!uiConfirm("Delete everything?")) return;    // WRONG

-- never returns, and the destructive branch runs every time without anyone
being asked. That is strictly worse than the native dialog it replaced, and it
is invisible in review. So every boolean use of uiConfirm must be awaited, and
this checks it.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


JSDIR = os.path.join("static", "js")
FILES = sorted(f for f in os.listdir(JSDIR) if f.endswith(".js"))


def code_lines(path):
    """Every line that is not a comment. Comments MAY name the native three --
    the notes explaining why they were replaced have to be able to say so."""
    out = []
    for i, line in enumerate(io.open(path, encoding="utf-8").read().split("\n"), 1):
        s = line.strip()
        if s.startswith("//") or s.startswith("*") or s.startswith("/*"):
            continue
        out.append((i, line))
    return out


print("=== the three replacements exist, in one file ===")
DLG = io.open(os.path.join(JSDIR, "dialog.js"), encoding="utf-8").read()
for fn in ("uiAlert", "uiConfirm", "uiPrompt", "uiInline"):
    truthy("dialog.js defines %s()" % fn, "function %s(" % fn in DLG)
truthy("  and they are built by one shared opener", "function _dlgOpen(" in DLG)
# uiPrompt kept prompt()'s contract so `if (v === null) return;` still reads
# correctly at every call site that was converted.
truthy("uiPrompt still resolves null when cancelled", "cancelValue: null" in DLG)
truthy("uiConfirm resolves false when cancelled", "cancelValue: false" in DLG)
# Only one may be open. Two stacked overlays trap the page behind both, which
# is the native behaviour being replaced and was never the good half of it.
truthy("only one dialog is open at a time", "if (_DLG_OPEN)" in DLG)
truthy("Escape closes", 'e.key === "Escape"' in DLG)
truthy("  and Enter does NOT accept from inside a textarea",
       'e.target.tagName !== "TEXTAREA"' in DLG)

print("\n=== the page carries it, before anything that calls it ===")
HTML = io.open(os.path.join("templates", "dashboard.html"), encoding="utf-8").read()
truthy("dashboard.html loads dialog.js", "/static/js/dialog.js" in HTML)
truthy("  and its stylesheet", "/static/css/dialog.css" in HTML)
# BEFORE every other screen's script. They call these at load time in a couple
# of places, and a helper defined after its first caller is a crash on boot.
_dlg = HTML.index("/static/js/dialog.js")
for other in ("sourcing.js", "handling.js", "listings.js", "settings.js"):
    truthy("  loaded before %s" % other, _dlg < HTML.index("/static/js/" + other))

print("\n=== not one native dialog is left ===")
NATIVE = re.compile(r"(?<![\w.$])(alert|confirm|prompt)\s*\(")
offenders = []
for fn in FILES:
    if fn == "dialog.js":
        continue                      # it is allowed to name what it replaces
    for i, line in code_lines(os.path.join(JSDIR, fn)):
        for m in NATIVE.finditer(line):
            offenders.append("%s:%d  %s" % (fn, i, line.strip()[:70]))
check("no alert/confirm/prompt in any screen's code", offenders, [])

print("\n=== and every use of them is awaited ===")
# The whole reason this file exists. A bare uiConfirm in a boolean position is
# a confirmation that always passes.
BARE = re.compile(r"(?<!await )(?<![\w.$])(uiConfirm|uiPrompt|uiAlert)\s*\(")
unawaited = []
for fn in FILES:
    if fn == "dialog.js":
        continue
    for i, line in code_lines(os.path.join(JSDIR, fn)):
        for m in BARE.finditer(line):
            # `return uiConfirm(...)` hands the promise on, which is correct;
            # so does passing it to .then. Everything else must await.
            head = line[:m.start()].rstrip()
            if head.endswith("return") or head.endswith("=>"):
                continue
            unawaited.append("%s:%d  %s" % (fn, i, line.strip()[:70]))
check("no bare uiConfirm/uiPrompt/uiAlert", unawaited, [])

print("\n=== an await needs an async function around it ===")
# Proven by parsing, not by reading: `await` outside an async function is a
# SyntaxError, so if node accepts the file every await is properly enclosed.
import subprocess
broken = []
for fn in FILES:
    try:
        r = subprocess.run(["node", "--check", os.path.join(JSDIR, fn)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            broken.append("%s: %s" % (fn, (r.stderr or "").strip()[:90]))
    except FileNotFoundError:
        print("  (node is not on this machine -- parse half not exercised)")
        broken = None
        break
if broken is not None:
    check("every screen's JavaScript parses", broken, [])

print("\n=== the inline editor, for the ones that should not be modal ===")
# "Replace with an inline input that appears right where the button is."
# A modal is right when the decision needs the whole page's attention; setting
# one number on one row does not, and covering the row takes away the context
# you need to choose the number.
SRC = io.open(os.path.join(JSDIR, "sourcing.js"), encoding="utf-8").read()
truthy("the floor is edited inline", "uiInline(btn" in SRC)
truthy("  and so is the held price",
       SRC.count("uiInline(btn") >= 2)
truthy("  anchored to the button that opened it", "anchor.getBoundingClientRect" in DLG)
truthy("  and clearing is its own button, not an empty box",
       "clearable:" in SRC and "uiinline-clear" in DLG)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
