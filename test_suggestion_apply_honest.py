# -*- coding: utf-8 -*-
"""Two writes that named no account, one of which also reported success blind
(bug round, 30 Sep 2026; docs/known-issues.md "Activity log").

  * autofix.js applySuggestion posted a bare /edit (no account -- Rule 14) and
    marked the row "Applied" whatever the server said. It now goes through the
    shared editField (Rule 12) with the account the action started in, and
    only a confirmed save is marked applied; "Apply all" counts failures.
  * howworks.js setStatus posted /approve with no account.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def truthy(label, cond):
    if not cond:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if cond else "FAIL"))


def fn(src, name):
    m = re.search(r"async function " + name + r"\(.*?\n\}", src, re.S)
    return m.group(0) if m else ""


A = open(os.path.join(HERE, "static", "js", "autofix.js"), encoding="utf-8").read()
apply_ = fn(A, "applySuggestion")
truthy("applySuggestion saves through the shared editField", "editField(sku, 'attr', field, val" in apply_)
truthy("  no bare /edit post left in it", "fetch('/edit'" not in apply_)
truthy("  a refused save is not marked Applied",
       "if(!res || !res.ok)" in apply_ and apply_.index("if(!res || !res.ok)") < apply_.index("\\u2713 Applied"))
all_ = fn(A, "applyAllSuggestions")
truthy("Apply all pins the account it started in", "acctId()" in all_ and ", acct))" in all_)
truthy("  and reports how many were not applied", "not applied" in all_)
H = open(os.path.join(HERE, "static", "js", "howworks.js"), encoding="utf-8").read()
st = fn(H, "setStatus")
truthy("setStatus names its account on /approve", "acctBody({sku,status})" in st)

print("\nFAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
