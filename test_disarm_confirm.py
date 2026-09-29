"""Disarming the repricer asks first, like arming and stopping tracking do.

Design package (owner-approved): '"Armed -- disarm" and "Stop tracking" ask for
confirmation, because both stop automatic pricing.' Stop tracking already asked;
disarm, single and bulk, went straight through.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
JS = open(os.path.join(HERE, "static", "js", "sourcing.js"), encoding="utf-8").read()
fails = []


def truthy(label, cond):
    print("  %-72s %s" % (label, "OK" if cond else "FAIL"))
    if not cond:
        fails.append(label)


def body(name):
    i = JS.index("async function %s(" % name)
    j = JS.index("\nasync function ", i + 10)
    return JS[i:j]


one = body("sourcingArm")
truthy("single disarm asks (srcConfirm guarded by !live)",
       re.search(r"if\(!live && !await srcConfirm\(", one) is not None)
truthy("  and the verb on the button is Disarm", 'confirm: "Disarm"' in one)
truthy("  the account is fixed before the question", one.index("_srcScopeNow()") < one.index("srcConfirm("))
truthy("  and checked after it", "_srcStillIn(scope)" in one)
truthy("  and the write names that account", "_srcBody({sku:sku, live:!!live}, scope)" in one)

bulk = body("sourcingBulkArm")
truthy("bulk disarm asks", re.search(r"\}else\{[\s\S]{0,120}await uiConfirm\(", bulk) is not None)
truthy("  with Disarm on the button", 'ok: "Disarm"' in bulk)

if fails:
    raise SystemExit("FAILED: %d" % len(fails))
print("\nall disarm confirmation checks passed")
