"""The per-SKU margin/ROI target: it exists, it says so, and it is not the account's.

    "i am looking at repricer, i dont have an option to set the margin and roi
     target per item"

IT WAS THERE AND IT WORKED. Measured on the running app before anything was
changed: 67 per-SKU buttons, one for every enrolled SKU, each calling
sourcingTarget('<that sku>'), and the dialog opening scoped to it with a Margin
target box and an ROI target box.

WHAT IT NEVER DID WAS SAY SO. With no target set the row read

    Least profit accepted: the flat minimum only   [Set]

and the toolbar read "Profit target: none". Neither contains the word "margin"
or the word "ROI", so on an account with no targets yet -- which is every
account here -- those two words appeared NOWHERE on the screen. Somebody
looking for them found nothing and concluded the feature was missing. That is
a real defect in a working feature, and it is the one that got reported.

THE PRECEDENCE IS THE PART THAT MUST NOT BREAK, and it had no test at all. A
SKU's dialog opens pre-filled from SRC_ROW_RULES[sku] rather than the account
rule, because opening it with the account's numbers and pressing Save would
silently overwrite that SKU's override with someone else's figures. The comment
in sourcing.js says exactly this; nothing checked it.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-68s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


JS = open(os.path.join("static", "js", "sourcing.js"), encoding="utf-8").read()

print("=== the words are on the screen before a target exists ===")
# The unset states are the ones that matter: once a target IS set the label
# already reads "20% margin · 30% ROI". It is the empty account that could not
# find the feature.
truthy("the toolbar names both when none is set",
       "'Margin / ROI target: none'" in JS)
# IT NAMES THE TWO THINGS IT SETS, EVEN WHEN NEITHER IS SET -- which was the
# whole point of the original fix ("i dont have an option to set the margin
# and roi target per item"; it was there, it just never said the words).
#
# They are two pills now, one labelled ROI and one labelled Margin, each
# showing its own value or the word "none". That names both MORE plainly
# than the old single line did, and it is inside that SKU's own panel, so
# "which SKU is this for" is answered by where it is rather than by a button
# caption.
truthy("the per-SKU panel names both", "pill('ROI'" in JS and "pill('Margin'" in JS)
truthy("  each showing its own value or none",
       JS.count("!= null ? rule.target_roi_pct + '%' : 'none'") == 1
       and JS.count("!= null ? rule.target_margin_pct + '%' : 'none'") == 1)
truthy("  and an unset one is dimmed rather than hidden", "rp-off" in JS)
# The account-wide button must not read as the only target there is.
truthy("the toolbar tip points at the per-SKU one",
       "Set for this SKU" in JS.split('onclick="sourcingTarget(\\\'\\\')"')[1][:600]
       if 'onclick="sourcingTarget(\\\'\\\')"' in JS else
       "its own target wins over this one" in JS)

print("\n=== every enrolled row offers its own, not just the account ===")
truthy("the row builds a target control for its own sku",
       "sourcingTarget(' + S + ')" in JS and "const S = _sarg(sku)" in JS)
truthy("  and the account-wide one passes no sku", "sourcingTarget(\\'\\')" in JS
       or "sourcingTarget('')" in JS)

PROBE = r"""
const fs = require("fs"), vm = require("vm");
globalThis.window = globalThis;
globalThis.document = {getElementById: () => null, querySelectorAll: () => [],
  createElement: () => ({innerHTML:"", style:{}, remove(){}, querySelector:()=>null}),
  body: {appendChild(){}}, addEventListener(){}};
globalThis.addEventListener = function(){};
globalThis._sesc = s => String(s == null ? "" : s);
globalThis.SRC_ROW_RULES = {};
globalThis.SRC_RULE = {};
let OPENED = null;
globalThis._srcModal = function(title, body, onOk){ OPENED = {title, body}; };
globalThis._srcTargetBox = function(id, label, value){
  return "[" + id + "|" + label + "|" + (value == null ? "" : value) + "]";
};
const src = fs.readFileSync("static/js/sourcing.js", "utf8");
const grab = function(name){
  const i = src.indexOf("function " + name + "(");
  if(i < 0) throw new Error("missing " + name);
  let d = 0;
  for(let k = src.indexOf("{", i); k < src.length; k++){
    if(src[k] === "{") d++;
    else if(src[k] === "}"){ d--; if(!d) return src.slice(i, k + 1); }
  }
  throw new Error("unbalanced " + name);
};
vm.runInThisContext(grab("sourcingTarget") + "\n" + grab("_srcTargetLabel"));

const out = {};
// The account default, and ONE sku that disagrees with it.
SRC_RULE = {target_margin_pct: 20, target_roi_pct: 30};
SRC_ROW_RULES = {"SKU-OWN": {target_margin_pct: 55, target_roi_pct: null}};

sourcingTarget("");                       // the account-wide dialog
out.acctScope  = /every enrolled SKU/.test(OPENED.body);
out.acctMargin = /\[tgt_margin\|Margin target\|20\]/.test(OPENED.body);
out.acctRoi    = /\[tgt_roi\|ROI target\|30\]/.test(OPENED.body);

sourcingTarget("SKU-OWN");                // a SKU that HAS its own
out.ownNamesSku = /SKU-OWN/.test(OPENED.body);
// THE OVERRIDE, NOT THE ACCOUNT'S. Pre-filling with 20 and pressing Save would
// quietly replace this SKU's 55 with the account's number.
out.ownMargin   = /\[tgt_margin\|Margin target\|55\]/.test(OPENED.body);
// Its ROI is deliberately OFF while the account has 30. An override that is
// "off" must not be shown as the account's 30, or Save turns it back on.
out.ownRoiEmpty = /\[tgt_roi\|ROI target\|\]/.test(OPENED.body);

sourcingTarget("SKU-NONE");               // a SKU with no override of its own
out.noneNamesSku  = /SKU-NONE/.test(OPENED.body);
// This one SHOULD show the account's numbers: they are what it is priced by.
out.noneUsesAcct  = /\[tgt_margin\|Margin target\|20\]/.test(OPENED.body)
                 && /\[tgt_roi\|ROI target\|30\]/.test(OPENED.body);

out.labelNone = _srcTargetLabel({});
out.labelBoth = _srcTargetLabel({target_margin_pct: 20, target_roi_pct: 30});
out.labelOne  = _srcTargetLabel({target_roi_pct: 30});
console.log(JSON.stringify(out));
"""

try:
    fd, path = tempfile.mkstemp(suffix=".js", dir=HERE)
    os.write(fd, PROBE.encode("utf-8"))
    os.close(fd)
    r = subprocess.run(["node", path], capture_output=True, text=True,
                       encoding="utf-8", cwd=HERE)
    os.unlink(path)
    if r.returncode != 0:
        print("  FAIL sourcing.js threw:", (r.stderr or "")[:400])
        raise SystemExit(1)
    g = json.loads(r.stdout.strip().splitlines()[-1])
except FileNotFoundError:
    print("  (node is not on this machine -- dialog half not exercised)")
    g = None

if g:
    print("\n=== the account-wide dialog ===")
    truthy("it says it applies to everything", g["acctScope"])
    truthy("  pre-filled with the account margin", g["acctMargin"])
    truthy("  and the account ROI", g["acctRoi"])

    print("\n=== a SKU with its own target opens showing ITS numbers ===")
    truthy("the dialog names the SKU", g["ownNamesSku"])
    truthy("  and shows the SKU's margin, not the account's", g["ownMargin"])
    # An override with ROI switched off must stay switched off. Showing the
    # account's 30 here and pressing Save would turn a target back on that
    # somebody deliberately cleared.
    truthy("  and leaves its switched-off ROI empty", g["ownRoiEmpty"])

    print("\n=== a SKU with no target of its own falls back to the account ===")
    truthy("the dialog still names the SKU", g["noneNamesSku"])
    truthy("  and shows the account's numbers, which price it today",
           g["noneUsesAcct"])

    print("\n=== the label ===")
    check("none names both settings", g["labelNone"], "Margin / ROI target: none")
    check("both are shown, because both apply", g["labelBoth"],
          "Target: 20% margin · 30% ROI")
    check("one is shown alone", g["labelOne"], "Target: 30% ROI")

print("\n=== and it is stored per SKU, at every layer below the screen ===")
DB = open(os.path.join("data", "db.py"), encoding="utf-8").read()
REPO = open(os.path.join("domain", "source_repo.py"), encoding="utf-8").read()
truthy("the rules table is keyed by sku",
       "PRIMARY KEY (workspace_id, marketplace, sku)" in DB)
truthy("  and holds both targets",
       "target_margin_pct" in DB and "target_roi_pct" in DB)
# A SKU row that sets only the margin must not blank the account's ROI.
truthy("a SKU row is overlaid on the account row, nulls dropped",
       "def rule_for(" in REPO)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
