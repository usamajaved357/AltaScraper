"""The repricer guide states every rule, in lists rather than paragraphs.

    "have you updated the logic in the how it works button on repricer and
     mention everything how it works and what are the rules in a format easy to
     understand and not in paragraphs but in words"

TWO REQUIREMENTS, AND THE SECOND ONE IS TESTABLE.

Everything: the guide had been overtaken by the questions actually asked this
week -- that a target is a FLOOR and will therefore lower a price, that a SKU
cannot be armed without a minimum price, that the 15% is a setting and not
Amazon's quote, that the 20% is a safety floor and not a target, and the new
bulk "Hold at today's price". None of that was in it.

Not paragraphs: a guide is read to find ONE rule, not from start to finish, and
a rule buried mid-sentence in a block of prose cannot be found by scanning. So
the prose blocks are measured here -- not just "does it mention X", which a wall
of text would also pass.
"""
import json
import os
import re
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
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


PROBE = r"""
const fs = require("fs"), vm = require("vm");
globalThis.window = globalThis;
globalThis.document = {getElementById: () => null, createElement: () => ({}),
  body: {appendChild(){}}, addEventListener(){}};
globalThis.addEventListener = function(){};
vm.runInThisContext(fs.readFileSync("static/js/guide.js", "utf8"));
const g = GUIDES.repricer;
console.log(JSON.stringify({
  title: g.title, lead: g.lead,
  steps: g.steps.map(s => ({n: s.n, h: s.h, b: s.b})),
  notes: g.notes,
  // The helpers must actually produce a list, not a string that looks like one.
  listSample: _gl(["one", "two"]),
  tableSample: _gt([["a", "b"]])
}));
"""

try:
    fd, path = tempfile.mkstemp(suffix=".js", dir=HERE)
    os.write(fd, PROBE.encode("utf-8"))
    os.close(fd)
    r = subprocess.run(["node", path], capture_output=True, text=True,
                       encoding="utf-8", cwd=HERE)
    os.unlink(path)
    if r.returncode != 0:
        print("  FAIL guide.js threw:", (r.stderr or "")[:400])
        raise SystemExit(1)
    G = json.loads(r.stdout.strip().splitlines()[-1])
except FileNotFoundError:
    print("  (node is not on this machine -- not exercised)")
    raise SystemExit(0)

ALL = G["lead"] + " " + " ".join(s["h"] + " " + s["b"] for s in G["steps"]) \
    + " " + " ".join(G["notes"])

print("=== it is built from lists, not prose ===")
truthy("the list helper makes a real <ul>", "<li" in G["listSample"])
truthy("the table helper makes a real <table>", "<tr>" in G["tableSample"])
check("every step uses a list or a table",
      [s["n"] for s in G["steps"] if "<li" not in s["b"] and "<tr>" not in s["b"]],
      [])

# THE MEASUREMENT THAT MAKES "not in paragraphs" MEAN SOMETHING. Strip the
# markup, then look at the runs of plain text BETWEEN tags: a bullet is short, a
# paragraph is not. 300 characters is roughly four lines on this modal's width.
def longest_prose(html):
    worst = 0
    for chunk in re.split(r"<[^>]+>", html):
        t = " ".join(chunk.split())
        worst = max(worst, len(t))
    return worst


for s in G["steps"]:
    n = longest_prose(s["b"])
    check("step %s has no block over 300 chars (longest %d)" % (s["n"], n),
          n <= 300, True)
for i, note in enumerate(G["notes"]):
    n = longest_prose(note)
    check("note %d has no block over 340 chars (longest %d)" % (i + 1, n),
          n <= 340, True)

print("\n=== every rule that was asked about this week is in it ===")
RULES = [
    ("a target is a floor and can LOWER a price", "come <b>down</b>"),
    ("  and how to stop that", "Hold the price at"),
    ("the bulk hold exists", "Hold at today's price"),
    ("  and says a cheaper supplier means margin", "more margin, not a lower price"),
    ("  and that it cannot hold you at a loss", "never hold you at a loss"),
    ("no arming without a minimum price", "no SKU can be armed without it"),
    ("three switches, not one", "Three switches"),
    ("the 15% is a setting, not Amazon's quote", "setting, not Amazon"),
    ("  and what it varies by", "varies by category"),
    ("the 20% safety floor is not a target", "safety floor is not a target"),
    ("the price is built forwards from the supplier", "your cost"),
    ("  and the floors are taken at their highest", "highest"),
    ("no readable supplier means no change", "no price, and nothing changes"),
    ("why a SKU is not being repriced", "Why a SKU is not being repriced"),
    ("  pointing at the per-row answer", "Why?"),
    ("margin is over what the customer pays", "CUSTOMER pays"),
    ("ROI is over what you paid", "WHAT YOU PAID"),
    ("the chips are explained", "would go out of stock"),
    ("  including the cost drift one", "cost on record"),
    ("the roi chip is what an order would earn now", "RIGHT NOW"),
]
for label, needle in RULES:
    truthy(label, needle in ALL)

print("\n=== and it still says what it will not do ===")
truthy("tracking changes nothing on Amazon", "changes nothing on Amazon" in ALL)
truthy("nothing is added that was not entered",
       "Nothing is added that you did not enter" in ALL)
truthy("the 4-hour and change-cap limits are stated",
       "4 hours" in ALL and "change cap" in ALL)

print("\n=== the button still opens this guide ===")
SJS = open(os.path.join("static", "js", "sourcing.js"), encoding="utf-8").read()
truthy("the repricer's button asks for it", "openGuide('repricer')" in SJS
       or 'openGuide(\\\'repricer\\\')' in SJS)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
