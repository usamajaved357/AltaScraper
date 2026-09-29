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

# A WRITE AFTER A DIALOG. The account is read when the request is SENT, which is
# after the person answered -- so it is noted before the dialog and the write is
# refused if it changed (lvPushChanges pushes to Amazon; two are deletes).
DIALOG = re.compile(r'await\s+(uiConfirm|uiAlert|uiPrompt|confirm)\(')
DIALOG_OK = {("product_type.js", "ptFixDrafts"): "its summary alert follows the pinned loop"}
bad2 = []
for fp in sorted(glob.glob(os.path.join(HERE, "static", "js", "*.js"))):
    name = os.path.basename(fp)
    src = open(fp, encoding="utf-8").read()
    for m in DIALOG.finditer(src):
        tail = src[m.end():m.end() + 1500]
        cut = re.search(r'\n(async )?function ', tail)
        if cut:
            tail = tail[:cut.start()]
        if not WRITE.search(tail):
            continue
        fns = re.findall(r'(?:async\s+)?function\s+(\w+)', src[:m.start()])
        fn = fns[-1] if fns else "?"
        body = src[src.rfind("function " + fn, 0, m.start()):m.end() + len(tail)]
        if any(p in body for p in PINNED + ("_pinAcct",)):
            continue
        if (name, fn) in DIALOG_OK:
            continue
        bad2.append("%s %s()" % (name, fn))
ok2 = not bad2
print("  %-66s %s" % ("every write after a dialog checks the account first",
                      "OK" if ok2 else "FAIL got=%r" % bad2))
fails = (0 if ok else 1) + (0 if ok2 else 1)
print("\nFAILURES: %d" % fails)
sys.exit(1 if fails else 0)
