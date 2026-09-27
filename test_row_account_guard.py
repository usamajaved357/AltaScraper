"""/rows and /rows_all must refuse an account the user may not open.

auth/guard.py checks every request that NAMES an account against the user's
workspace list. `account` was added to the names it reads precisely so that
/rows_all?account= would be checked (see the WORKSPACE_PARAMS comment: "four
handlers read it ... routes/listing_routes.py:807 /rows_all?account=").

But a separate list exempts some paths whose `id` means something other than an
account, and it is matched with p.startswith(ex). "/row" is on it -- so
"/rows" and "/rows_all" are exempt too, by accident of spelling, and a user
restricted to one company could read another company's listings by naming it.

Measured here with the real guard.check() (no app, no data).

Run: py -3.11 test_row_account_guard.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auth import guard, users  # noqa: E402

FAIL = []


def check(label, got, want):
    ok = got == want
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))
    if not ok:
        FAIL.append(label)


def user(workspaces, role="lister"):
    return {"id": "u", "email": "x@example.com", "name": "X", "active": True,
            "role": role, "workspaces": list(workspaces),
            "features": {f: "edit" for f in users.FEATURES},
            "permissions": ["edit"]}


VA = user(["nestwell_goods"])                     # may open one account only
BOSS = user([users.ALL_WORKSPACES], "owner")

print("== naming ANOTHER account on the listing reads is refused ==")
for path in ("/rows_all", "/rows"):
    check("GET %s?account=jack_uk" % path,
          guard.check(path, "GET", VA, None, {"account": "jack_uk"})[0], False)
    check("  and the other spellings (?account_id=)",
          guard.check(path, "GET", VA, None, {"account_id": "jack_uk"})[0], False)
check("GET /row?sku=X&account=jack_uk",
      guard.check("/row", "GET", VA, None, {"sku": "X", "account": "jack_uk"})[0], False)

print("\n== their OWN account, and no account, still work ==")
for path in ("/rows_all", "/rows"):
    check("GET %s?account=nestwell_goods" % path,
          guard.check(path, "GET", VA, None, {"account": "nestwell_goods"})[0], True)
    check("GET %s with no account" % path,
          guard.check(path, "GET", VA, None, {})[0], True)
check("GET /row?sku=X&account=nestwell_goods",
      guard.check("/row", "GET", VA, None, {"sku": "X", "account": "nestwell_goods"})[0], True)

print("\n== the exemption is for the paths it names, not every path that starts the same ==")
check("/rows_all is not exempt from the workspace check",
      guard.named_workspace("/rows_all", {"account": "jack_uk"}, None), "jack_uk")
check("/rows is not exempt either",
      guard.named_workspace("/rows", {"account": "jack_uk"}, None), "jack_uk")

print("\n== an owner is unaffected ==")
check("owner GET /rows_all?account=jack_uk",
      guard.check("/rows_all", "GET", BOSS, None, {"account": "jack_uk"})[0], True)

print("\n%d failed" % len(FAIL))
for f in FAIL:
    print("  -", f)
sys.exit(1 if FAIL else 0)
