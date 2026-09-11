# -*- coding: utf-8 -*-
"""Pressing "Suggest & auto-generate" must actually START the images.

    "i am trying to generate images of the listings, but app is not able to
     create secondary images, when i click on suggest and generate it suggests
     but do not starts generating and i dont see the progress of the images
     generated"

WHAT WAS WRONG. tooManyProducts() in static/js/genimage.js is an ASYNC function:
it may stop to show a message, so what it hands back is a Promise -- a note that
says "the answer is coming" -- rather than the answer. Three callers used it
without `await`:

    if(tooManyProducts(what, total)) return;

A Promise is an object, and in JavaScript every object counts as true. So that
line returned EVERY time, whatever the answer would have been, and every press
of these buttons stopped there -- silently, before any image was asked for:

    studioGenAllConcepts  "Suggest & auto-generate" and "Generate all N ideas",
                          in the main, secondary AND A+ sections
    studioRunSecondary    the secondary section's own Generate button
    studioRunAplus        the A+ section's own Generate button

The strategist's ideas still appeared, because that happens BEFORE the guard.
The generation and its progress bar never did, because they come after it. Only
a single idea's own "Generate" button kept working, because that path never
asks the question. Introduced 20 Aug 2026 (75bdac5), in the same commit that
added the guard.

THE GUARD ITSELF WAS RIGHT AND STAYS: one press makes ONE product's set. So this
file proves both halves -- one product now starts, and several products are
still stopped with the explanation. A fix that "worked" by deleting the guard
would fail here.

The behaviour checks RUN genimage.js in node, with only the network and the
screen stubbed out. Grepping for the word `await` would have passed a fix that
put it in the wrong place.

Set GENIMAGE_JS to another copy of genimage.js to run these checks against it --
that is how this file was shown to fail on the unfixed code.
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
FAILS = []


def check(name, cond, detail=""):
    if cond:
        print("  ok    %s" % name)
    else:
        print("  FAIL  %s   %s" % (name, detail))
        FAILS.append(name)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def code_only_js(src):
    """Strip // and /* */ comments, so a sentence in a comment -- including the
    one explaining this fix -- can neither pass nor fail a check."""
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", ln) for ln in src.split("\n"))


GENIMAGE = os.environ.get("GENIMAGE_JS") or os.path.join(HERE, "static", "js", "genimage.js")

# --------------------------------------------------------------- the harness
# genimage.js runs almost nothing when it loads -- five variable declarations --
# so it loads in node as it is. Only what reaches the network or the screen is
# replaced, and replaced AFTER the file, so these later declarations win.
PRELUDE = r"""
var window = {};
var __ids = {}, __qsa = {};
var document = {
  getElementById: function(id){ return __ids[id] || null; },
  querySelectorAll: function(sel){ return __qsa[sel] || []; },
  querySelector: function(sel){ return null; }
};
var LIVE_ITEMS = [], ROWS = [], CUR_ACCOUNT = null;
"""

STUBS = r"""
var __started = [], __alerts = [], __confirms = [];
function uiAlert(m){ __alerts.push(String(m)); return Promise.resolve(); }
function uiConfirm(m){ __confirms.push(String(m)); return Promise.resolve(true); }
function toast(m){}
function esc(s){ return String(s); }
// network: "does this product already have images?" -- answered "go ahead"
function confirmIfExisting(skus, kind){ return Promise.resolve(true); }
// network: the batch starter. Recording that it was REACHED is the whole test.
function studioRunBackground(kind, jobs, total){
  __started.push({kind: kind, n: jobs.length, total: total});
}
"""

CHECKS = r"""
function reset(){ __started = []; __alerts = []; __confirms = []; }
function eq(label, got, want){
  var ok = JSON.stringify(got) === JSON.stringify(want);
  console.log((ok ? "PASS " : "FAIL ") + label + (ok ? "" : "   got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
  if(!ok) process.exitCode = 1;
}
function ideas(n){
  var a = [];
  for(var i = 1; i <= n; i++) a.push({title: "Idea " + i, concept: "c" + i, art_direction: "a" + i, slot: i});
  return a;
}

(async function(){
  ROWS = [{sku: "A", img: "https://example.com/a.jpg", title: "Product A"},
          {sku: "B", img: "https://example.com/b.jpg", title: "Product B"}];

  // 1. THE REPORTED CASE: one product, secondary section, Suggest & auto-generate.
  reset();
  STUDIO.skus = ["A"]; STUDIO.concepts = ideas(7); STUDIO.conceptKind = "secondary";
  await studioGenAllConcepts(true);
  eq("secondary 'Suggest & auto-generate' STARTS", __started.length, 1);
  eq("  with all 7 ideas", __started[0] && __started[0].n, 7);
  eq("  as a concept batch (so progress is shown)", __started[0] && __started[0].kind, "concept");
  eq("  after saying how many it will make", __confirms.some(function(m){ return /7 secondary images/.test(m); }), true);

  // 2. The "Generate all N ideas" button -- same function, no auto flag.
  reset();
  await studioGenAllConcepts();
  eq("'Generate all ideas' starts too", __started.length, 1);

  // 3. The main and A+ sections go through the same function.
  reset(); STUDIO.concepts = ideas(3); STUDIO.conceptKind = "main";
  await studioGenAllConcepts(true);
  eq("main-image auto-generate starts", __started.length, 1);
  reset(); STUDIO.concepts = ideas(5); STUDIO.conceptKind = "aplus";
  await studioGenAllConcepts(true);
  eq("A+ auto-generate starts", __started.length, 1);

  // 4. THE GUARD STILL HOLDS. Two products selected: stopped, and told why.
  reset(); STUDIO.skus = ["A", "B"]; STUDIO.concepts = ideas(7); STUDIO.conceptKind = "secondary";
  await studioGenAllConcepts(true);
  eq("two products selected are still stopped", __started.length, 0);
  eq("  and the reason is shown", __alerts.some(function(m){ return /2 products selected/.test(m); }), true);

  // 5. The secondary section's own Generate button.
  reset(); STUDIO.skus = ["A"];
  __ids = {sec_mode: {value: "planned"}};
  __qsa = {".secrole:checked": [{value: "infographic"}, {value: "lifestyle"}]};
  await studioRunSecondary();
  eq("secondary Generate button starts", __started.length, 1);
  eq("  one image per chosen role", __started[0] && __started[0].n, 2);
  reset(); STUDIO.skus = ["A", "B"];
  await studioRunSecondary();
  eq("  and still refuses two products", __started.length, 0);

  // 6. The A+ section's own Generate button.
  reset(); STUDIO.skus = ["A"];
  __ids = {ap_tier: {value: "basic"}};
  __qsa = {".apmodchk:checked": [{value: "m1"}, {value: "m2"}]};
  await studioRunAplus();
  eq("A+ Generate button starts", __started.length, 1);
  eq("  one image per chosen module", __started[0] && __started[0].n, 2);
  reset(); STUDIO.skus = ["A", "B"];
  await studioRunAplus();
  eq("  and still refuses two products", __started.length, 0);
})().catch(function(e){
  console.log("FAIL the harness itself threw: " + ((e && e.stack) || e));
  process.exitCode = 1;
});
"""

print("== 1. the buttons actually start the images (genimage.js, run in node) ==")
print("   file under test: %s" % GENIMAGE)
node = None
for cand in ("node", "node.exe"):
    try:
        subprocess.run([cand, "--version"], capture_output=True, timeout=30)
        node = cand
        break
    except Exception:
        continue
if not node:
    # Not skipped quietly: this is the half of the file that proves the fix.
    check("node is available to run genimage.js", False,
          "install Node.js -- the behaviour checks cannot run without it")
else:
    src = PRELUDE + "\n" + read(GENIMAGE) + "\n" + STUBS + "\n" + CHECKS
    fd, tmp = tempfile.mkstemp(suffix=".js", prefix="_genimage_starts_")
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(src)
        p = subprocess.run([node, tmp], capture_output=True, text=True,
                           encoding="utf-8", timeout=120)
        out = (p.stdout or "").splitlines()
        for line in out:
            if line.startswith("PASS "):
                check(line[5:], True)
            elif line.startswith("FAIL "):
                check(line[5:], False)
        if not out:
            check("genimage.js ran in node", False, (p.stderr or "")[:400])
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

# ------------------------------------------------ the whole class of mistake
# The same missing word would stop any other screen the same silent way, so the
# check is not limited to genimage.js or to tooManyProducts: every function in
# static/js declared `async`, used as a condition without `await`.
print("\n== 2. no async function in static/js is used as a condition without await ==")
JS_DIR = os.path.join(HERE, "static", "js")
codes = {f: code_only_js(read(os.path.join(JS_DIR, f)))
         for f in sorted(os.listdir(JS_DIR)) if f.endswith(".js")}
async_names = set()
for c in codes.values():
    async_names.update(re.findall(r"async\s+function\s+([A-Za-z_$][\w$]*)", c))
check("found the async functions to check (%d)" % len(async_names), len(async_names) > 50)
check("  tooManyProducts is among them", "tooManyProducts" in async_names)
cond = re.compile(r"(?:\bif\s*\(|&&|\|\|)\s*!?\s*("
                  + "|".join(re.escape(n) for n in sorted(async_names, key=len, reverse=True))
                  + r")\s*\(")
bad = []
for f, c in codes.items():
    for i, line in enumerate(c.split("\n"), 1):
        if cond.search(line):
            bad.append("%s:%d: %s" % (f, i, line.strip()[:120]))
check("every one is awaited where it is tested", not bad, "\n        " + "\n        ".join(bad))

print()
if FAILS:
    print("%d FAILED" % len(FAILS))
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("all checks passed")
