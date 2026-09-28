"""A loop that WRITES for an account takes that account once, before it starts.

acctBody()/acctUrl() read the open account afresh on every call. Inside a loop
that awaits each request, a switch part-way sent the remaining writes to the
NEW account's same-SKU listing -- stock pushed to Amazon, bullets, product
types, images cleared (28 Sep 2026: listrow_edit, autofix, product_type,
drawer_attributes, miles_template). The fix everywhere is the same: take the
account (or the screen scope) once, name it on every write (acctBodyFor), or
stop when the screen moves (screenStillIn).

This scans every loop in static/js for an awaited write that reads the account
fresh, and fails on any not pinned. Read-only loops are listed by name with the
reason they are allowed.
"""
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Loops that await per-account requests but WRITE nothing, or check the account
# themselves -- each judged by reading it (28 Sep 2026).
ALLOWED = {
    ("product_type.js", "Asking Amazon about"): "read-only lookups; the apply step is pinned",
    ("miles_template.js", "user moved on"): "checks CUR_ACCOUNT/WS_MARKET itself each pass",
}

WRITE = re.compile(r'acctBody\(|editField\(|fetch\("/(edit|delete|approve|hold|stock|price|'
                   r'sourcing|live|row|media)')
PINNED = ("acctBodyFor", "screenStillIn", "_srcStillIn", "pin",
          ", acct)")      # editField(..., acct): the explicit pinned account


def loops(src):
    for m in re.finditer(r'\b(for|while)\s*\(', src):
        i = src.find("{", m.end())
        if i < 0:
            continue
        d, j = 0, i
        while j < len(src):
            if src[j] == "{":
                d += 1
            elif src[j] == "}":
                d -= 1
                if d == 0:
                    break
            j += 1
        yield src[:m.start()].count("\n") + 1, src[i:j]


bad = []
for fp in sorted(glob.glob(os.path.join(HERE, "static", "js", "*.js"))):
    name = os.path.basename(fp)
    src = open(fp, encoding="utf-8").read()
    for line, body in loops(src):
        if "await" not in body or not WRITE.search(body):
            continue
        if any(p in body for p in PINNED):
            continue
        if any(name == f and marker in body for (f, marker) in ALLOWED):
            continue
        bad.append("%s:%d" % (name, line))

ok = not bad
print("  %-66s %s" % ("every awaited write loop pins its account",
                      "OK" if ok else "FAIL got=%r" % bad))
print("\nFAILURES: %d" % (0 if ok else 1))
sys.exit(0 if ok else 1)
