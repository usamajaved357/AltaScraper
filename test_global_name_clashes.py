"""Two files, one name, and the second one wins silently.

FOUND IN A BROWSER, NOT IN A TEST. The revenue calculator was added as
`function rcOpen(sku, price)` in static/js/revenue.js. static/js/dashboard.js
has had `window.rcOpen = function(){...}` for the paste-a-listing modal all
along, and it assigns at load time -- so it replaced the new one, and pressing
"Calculate revenue" on a listing opened the paste dialog instead. No error, no
warning, nothing in any log: the click did something, just not the thing.

Every one of this app's forty-odd browser files shares ONE global scope. That is
how it is built and this file does not argue with it -- it just makes a name
collision fail here rather than in front of the owner.

WHAT IT DOES NOT DO is demand zero clashes. Several are deliberate: a function
declared once and re-assigned on window by the same file, a shim that overrides
a default. The check is that the set does not GROW -- the known ones are listed
by name, so adding a clash means adding it here on purpose, and a clash that
disappears has to be removed from the list.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-60s %s" % (label, "OK" if ok else "FAIL\n      got  = %r\n      want = %r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


JSDIR = os.path.join(HERE, "static", "js")

# A top-level `function name(` -- column zero, so a nested one does not count --
# and a top-level `window.name = function`.
TOP_FN = re.compile(r"^function\s+([A-Za-z_$][\w$]*)\s*\(", re.M)
WIN_FN = re.compile(r"window\.([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?function", re.M)
TOP_LET = re.compile(r"^(?:let|var|const)\s+([A-Za-z_$][\w$]*)", re.M)


def owners():
    """{name: [files that define it at the top level]}"""
    out = {}
    for f in sorted(os.listdir(JSDIR)):
        if not f.endswith(".js"):
            continue
        src = io.open(os.path.join(JSDIR, f), encoding="utf-8").read()
        # Comments quote other files' function names constantly; strip them or
        # every explanation counts as a definition.
        src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        src = "\n".join(l.split("//")[0] for l in src.splitlines())
        for rx in (TOP_FN, WIN_FN, TOP_LET):
            for m in rx.finditer(src):
                out.setdefault(m.group(1), set()).add(f)
    return {k: sorted(v) for k, v in out.items() if len(v) > 1}


print("=== no two files own the same global name ===")
clashes = owners()

# THE KNOWN ONES, each with why it is allowed to stay. Anything not on this list
# is a new collision and fails.
ALLOWED = {
    # A DELIBERATE WRAPPER, and it says so where it is written: shell.js takes
    # miles_template.js's setListSource, calls it, and adds altaSyncUrl() so the
    # address bar follows the source switch. The source switch has no business
    # knowing about the address bar. Load order makes it safe and the comment
    # there says which file must come first.
    "setListSource": ["miles_template.js", "shell.js"],
    # TWO IDENTICAL FOUR-LINE HTML ESCAPERS. Not a hazard the way the two above
    # were -- the bodies are character-for-character the same, so whichever wins
    # behaves the same -- but it is the same logic in two places (Rule 12) and
    # worth collapsing into the shared one the rest of the app uses when either
    # file is next opened.
    "_aiEsc": ["aiusage.js", "amazonimages.js"],
}

unexpected = {k: v for k, v in clashes.items() if k not in ALLOWED}
for name in sorted(unexpected):
    print("      %-28s %s" % (name, ", ".join(unexpected[name])))
check("no unexpected clashes", sorted(unexpected), [])
# AND THE ALLOWED ONES MUST STILL BE REAL. A name that stops clashing has to
# come off the list, or the list becomes a place where explanations rot.
for name, files in sorted(ALLOWED.items()):
    check("  still allowed, and still clashing: " + name,
          clashes.get(name), files)

print("\n=== the one that was silently doing nothing ===")
# permSetGroup existed twice with DIFFERENT signatures -- a group title here, a
# group id there -- and users.js loads second, so the Permissions screen's
# group buttons were calling the Users screen's function with the wrong kind of
# argument. It found no element and returned. Nothing happened, no error.
PERM = io.open(os.path.join(JSDIR, "permissions.js"), encoding="utf-8").read()
USERS = io.open(os.path.join(JSDIR, "users.js"), encoding="utf-8").read()
truthy("users.js keeps permSetGroup", "function permSetGroup(gid, level)" in USERS)
truthy("  and the permissions screen has its own name",
       "function permDraftSetGroup(" in PERM)
truthy("  which its own buttons call", "permDraftSetGroup(" in PERM)
# At column zero -- the comment above the fix names the other function, which is
# the record of what went wrong and must not be read as the thing itself.
check("  and it no longer defines the clashing one",
      re.search(r"^function permSetGroup\s*\(", PERM, re.M) is not None, False)

# AND THE ONE THAT WAS FOUND IN A BROWSER, pinned by name so the fix cannot be
# undone by someone renaming the new panel back.
print("\n=== the collision this file was written for ===")
REV = io.open(os.path.join(JSDIR, "revenue.js"), encoding="utf-8").read()
DASH = io.open(os.path.join(JSDIR, "dashboard.js"), encoding="utf-8").read()
truthy("dashboard.js still owns rcOpen for the paste modal",
       "window.rcOpen" in DASH)
truthy("  and the revenue panel does not use that name",
       "function rcOpen" not in REV and "window.rcOpen" not in REV)
truthy("  it is revOpen", "function revOpen(" in REV)
LR = io.open(os.path.join(JSDIR, "listrow_detailed.js"), encoding="utf-8").read()
truthy("  and the row calls the renamed one", "revOpen(" in LR and "rcOpen(" not in LR)
# The CSS prefix was taken too: .rc-modal is the paste dialog's.
CSS = io.open(os.path.join(HERE, "static", "css", "revenue.css"), encoding="utf-8").read()
check("the stylesheet does not reuse the .rc- prefix either",
      re.search(r"\.rc[-\w]", CSS) is not None, False)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
