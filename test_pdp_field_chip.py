# -*- coding: utf-8 -*-
"""Clicking a field Amazon names takes you to it -- including product_type.

    "I Ran autofix but i still see this message 1 warning -- Amazon accepted this,
     with notes ... your product type has been updated from HOME to PILLOW ...
     product_type Amazon code 18367 ... and when i click on product type written
     in this message it says amazon named product type but this listing has no
     such field"

Amazon's code 18367 names `product_type` in attributeNames. The warning draws it
as a button that calls pdpGoToField. That function switched to the Details tab
and searched ONLY the attribute rows (.pdp-attr-label) -- and product_type is not
an attribute. It is a property of the listing, drawn by productTypeCell in the
Identity section, which the product page shows on the OFFER tab. So the lookup
could not succeed for it, and the page said the field did not exist on a page
that has it.

These checks RUN pdpGoToField in node against a stand-in page, rather than
grepping for the new words -- a fix in the wrong place would pass a grep.
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
    print("  %s  %s%s" % ("ok  " if cond else "FAIL", name, "" if cond else "   " + detail))
    if not cond:
        FAILS.append(name)


def read(*p):
    with open(os.path.join(HERE, *p), encoding="utf-8") as fh:
        return fh.read()


PDP = read("static", "js", "pdp.js")
AF = read("static", "js", "autofix.js")
PT = read("static", "js", "product_type.js")
CSS = read("static", "css", "pdp.css")

# ------------------------------------------------------------ where it lives
print("== the product type control really is on the Offer tab ==")
check("the Offer tab draws the Identity section",
      bool(re.search(r'PDP_TAB === "offer"\)\{\s*tab = p\.offerOnly \+ p\.identityOnly', PDP)))
check("  the Identity section is built from idRows",
      'secIdentityOnly = dwSection("Identity", _ptTag, idRows)' in AF)
check("  and idRows carries the product type control",
      'dwFieldRow("Product type", productTypeCell(sku, r)' in AF)
check("  whose dropdown id is pt_ + sid(sku)", 'const wid="pt_"+sid(sku);' in AF)
check("  and whose type search id is ptsx_ + sid(sku)",
      'document.getElementById("ptsx_" + sid(sku))' in PT)
check("the highlight also styles a field row, not only an attribute row",
      ".dw2-fr.pdp-hit" in CSS)

# ------------------------------------------------------------- behaviour
print("\n== the chip goes to the field (pdpGoToField, run in node) ==")
start = PDP.find("const PDP_FIELD_HOME")
end = PDP.find("/* WHOSE DATA THIS IS", start)
check("found the function to run", start > 0 and end > start)

HARNESS = r"""
var PDP_TAB = "details", PDP_SKU = "SKU-1", renders = 0;
var toasts = [], focused = [], hits = [];
var ELEMENTS = {}, LABELS = [];
function pdpRender(){ renders++; }
function sid(s){ return String(s).replace(/[^A-Za-z0-9]/g, "_"); }
function toast(m){ toasts.push(m); }
function setTimeout(fn){ fn(); }            // run the deferred lookup now
function el(id, isInput, rowName){
  var row = rowName ? {classList:{add:function(){ hits.push(rowName); }, remove:function(){}},
                       scrollIntoView:function(){}} : null;
  return {id:id, classList:{add:function(){ hits.push(id); }, remove:function(){}},
          scrollIntoView:function(){},
          focus:function(){ focused.push(id); },
          matches:function(){ return !!isInput; },
          querySelector:function(){ return null; },
          closest:function(){ return row; }};
}
var document = {
  getElementById: function(id){ return ELEMENTS[id] || null; },
  querySelectorAll: function(){ return LABELS; }
};
function reset(tab){ PDP_TAB = tab; renders = 0; toasts = []; focused = []; hits = [];
                     ELEMENTS = {}; LABELS = []; }
function out(k, v){ console.log(k + "=" + JSON.stringify(v)); }

__CODE__

// 1. THE REPORTED CLICK: product_type, from the Details tab where the warning is.
reset("details");
ELEMENTS["ptsx_SKU_1"] = el("ptsx_SKU_1", true, "identity-row");
ELEMENTS["pt_SKU_1"] = el("pt_SKU_1", true, "identity-row");
pdpGoToField("product_type");
out("c1_tab", PDP_TAB); out("c1_renders", renders);
out("c1_focused", focused); out("c1_hits", hits); out("c1_toasts", toasts.length);

// 2. No search box drawn: the dropdown is used instead.
reset("details");
ELEMENTS["pt_SKU_1"] = el("pt_SKU_1", true, "identity-row");
pdpGoToField("product_type");
out("c2_focused", focused); out("c2_toasts", toasts.length);

// 3. An ordinary ATTRIBUTE still goes to Details, exactly as before.
reset("offer");
var box = {focus:function(){ focused.push("size-input"); }};
var row = {classList:{add:function(){ hits.push("size-row"); }, remove:function(){}},
           scrollIntoView:function(){}, querySelector:function(){ return box; }};
LABELS = [{getAttribute:function(){ return "size"; }, closest:function(){ return row; }}];
pdpGoToField("size");
out("c3_tab", PDP_TAB); out("c3_focused", focused); out("c3_toasts", toasts.length);

// 4. A field that genuinely is not there is still SAID, not silently ignored.
reset("details");
pdpGoToField("no_such_attribute");
out("c4_toasts", toasts.length);
"""

node = None
for cand in ("node", "node.exe"):
    try:
        subprocess.run([cand, "--version"], capture_output=True, timeout=30)
        node = cand
        break
    except Exception:
        continue

if not node:
    check("node is available to run pdp.js", False, "install Node.js")
elif start > 0 and end > start:
    code = PDP[start:end]
    fd, tmp = tempfile.mkstemp(suffix=".js", prefix="_pdp_chip_")
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(HARNESS.replace("__CODE__", code))
        p = subprocess.run([node, tmp], capture_output=True, text=True,
                           encoding="utf-8", timeout=60)
        got = {}
        for line in (p.stdout or "").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                got[k] = v
        if not got:
            check("pdp.js ran in node", False, (p.stderr or "")[:400])
        else:
            check("product_type switches to the Offer tab", got.get("c1_tab") == '"offer"',
                  got.get("c1_tab", ""))
            check("  re-drawing the page once so the control exists", got.get("c1_renders") == "1")
            check("  focuses the TYPE SEARCH box, where a type is chosen",
                  got.get("c1_focused") == '["ptsx_SKU_1"]', got.get("c1_focused", ""))
            check("  highlights the row it sits in", got.get("c1_hits") == '["identity-row"]',
                  got.get("c1_hits", ""))
            check("  and no longer claims there is no such field", got.get("c1_toasts") == "0")
            check("without a search box, the dropdown is used",
                  got.get("c2_focused") == '["pt_SKU_1"]' and got.get("c2_toasts") == "0",
                  got.get("c2_focused", ""))
            check("an ordinary attribute still goes to Details",
                  got.get("c3_tab") == '"details"', got.get("c3_tab", ""))
            check("  and is still found and focused",
                  got.get("c3_focused") == '["size-input"]' and got.get("c3_toasts") == "0",
                  got.get("c3_focused", ""))
            check("a field that really is missing is still said out loud",
                  got.get("c4_toasts") == "1")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

print()
if FAILS:
    print("%d FAILED" % len(FAILS))
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("all checks passed")
